import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, jsonable

_NODE_ID = re.compile(r"^ns=\d{1,5};[si]=[A-Za-z0-9._\-/ ]{1,200}$")
_TAG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_POLICIES = frozenset({"Basic256Sha256", "Aes128_Sha256_RsaOaep", "Aes256_Sha256_RsaPss"})
_MODES = frozenset({"Sign", "SignAndEncrypt"})


class OpcUaConnector(BaseConnector):
    """OPC UA read adapter for PLCs, SCADA servers, and historians.

    Only nodes listed in the manifest can be read. Agents cannot supply node IDs. Anonymous
    and unsecured sessions are refused, so every connection uses a signed or signed-and-encrypted
    secure channel with a client certificate. Writes are not supported."""

    connector_type = "opcua"
    secret_field = "password"

    def __init__(self, config: dict[str, Any], client_factory: Any = None):
        super().__init__(config)
        self._client_factory = client_factory

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "read" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: opcua operations must be mode 'read' and read_only")
        if op.get("parameters"):
            raise ConnectorError(f"{name}: opcua reads take no parameters; nodes are fixed in the manifest")
        nodes = op.get("nodes") or {}
        if not nodes:
            raise ConnectorError(f"{name}: define at least one node")
        for tag, node_id in nodes.items():
            if not _TAG.match(tag) or not _NODE_ID.match(str(node_id)):
                raise ConnectorError(f"{name}: invalid tag or node id for {tag!r}")
        endpoint = str(connection.get("endpoint") or "")
        if not endpoint.startswith("opc.tcp://"):
            raise ConnectorError("endpoint must start with opc.tcp://")
        if connection.get("security_policy") not in _POLICIES:
            raise ConnectorError("security_policy must be one of the approved secure policies (no None)")
        if connection.get("security_mode") not in _MODES:
            raise ConnectorError("security_mode must be Sign or SignAndEncrypt")
        if not connection.get("client_cert_path") or not connection.get("client_key_path"):
            raise ConnectorError("client_cert_path and client_key_path are required")

    def _client(self) -> Any:
        from chusky_bridge.config import settings
        from chusky_bridge.files import resolve_approved_file

        if self._client_factory:
            return self._client_factory(self.config)
        try:
            from opcua import Client
        except ImportError as exc:
            raise ConnectorError("the OPC UA client (opcua) is not installed") from exc
        cert = resolve_approved_file(self.config["client_cert_path"], settings.cert_dir)
        key = resolve_approved_file(self.config["client_key_path"], settings.cert_dir)
        client = Client(self.config["endpoint"], timeout=int(self.config.get("timeout_seconds", 10)))
        client.set_security_string(f"{self.config['security_policy']},{self.config['security_mode']},{cert},{key}")
        if self.config.get("username"):
            client.set_user(self.config["username"])
            client.set_password(self.config.get("password", ""))
        return client

    def health_check(self) -> dict[str, Any]:
        client = self._client()
        try:
            client.connect()
        except Exception as exc:
            raise ConnectorError("OPC UA session could not be established") from exc
        finally:
            client.disconnect()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        client = self._client()
        values: dict[str, Any] = {}
        try:
            client.connect()
        except Exception as exc:
            raise ConnectorError("OPC UA session could not be established") from exc
        try:
            for tag, node_id in (op.get("nodes") or {}).items():
                try:
                    node = client.get_node(node_id)
                    data_value = node.get_data_value()
                    timestamp = getattr(data_value, "SourceTimestamp", None)
                    values[tag] = {
                        "value": jsonable(data_value.Value.Value),
                        "source_timestamp": timestamp.isoformat() if timestamp else None,
                    }
                except Exception as exc:
                    raise ConnectorError(f"read failed for tag {tag}") from exc
        finally:
            client.disconnect()
        return {"status": "success", "operation": operation, "values": values}
