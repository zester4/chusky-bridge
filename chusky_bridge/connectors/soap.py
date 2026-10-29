import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from chusky_bridge.config import settings
from chusky_bridge.connectors.base import (
    BaseConnector,
    ConnectorError,
    jsonable,
    require_arguments,
    validate_identifiers,
)


def resolve_wsdl_path(configured: str, base_dir: str) -> Path:
    """WSDLs are loaded from a mounted directory only. Clients and manifests cannot fetch arbitrary URLs."""
    base = Path(base_dir).resolve()
    candidate = (base / configured).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        raise ConnectorError("WSDL file not found in the approved WSDL directory")
    return candidate


def endpoint_addresses(client: Any) -> list[str]:
    addresses: list[str] = []
    for service in client.wsdl.services.values():
        for port in service.ports.values():
            addresses.append(port.binding_options["address"])
    return addresses


def check_service_hosts(addresses: list[str], allowed_hosts: set[str]) -> None:
    """A WSDL can point its endpoints anywhere. Every endpoint host must be explicitly allowlisted."""
    for address in addresses:
        host = urlsplit(address).hostname
        if not host or host not in allowed_hosts:
            raise ConnectorError("WSDL endpoint host is not in the allowlist")


class SoapConnector(BaseConnector):
    """SOAP/WSDL adapter for PeopleSoft Integration Broker, Siebel, Temenos, Infor Lawson,
    Guidewire-style services, and any WSDL-described system. WS-Security UsernameToken is supported."""

    connector_type = "soap"
    secret_field = "password"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._wsdl = resolve_wsdl_path(config["wsdl_path"], settings.wsdl_dir)
        self._allowed_hosts = set(config.get("allowed_hosts", []))
        if not self._allowed_hosts:
            raise ConnectorError("allowed_hosts must list every service host")

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if not op.get("soap_operation") or not str(op["soap_operation"]).replace("_", "").isalnum():
            raise ConnectorError(f"{name}: soap_operation must be a plain operation name")
        validate_identifiers(op.get("parameters", []), "parameter")
        if not connection.get("wsdl_path") or not connection.get("allowed_hosts"):
            raise ConnectorError(f"{name}: connection needs wsdl_path and allowed_hosts")

    def _client(self) -> Any:
        from zeep import Client
        from zeep.transports import Transport
        from zeep.wsse.username import UsernameToken

        wsse = None
        if self.config.get("username") and self.config.get("password"):
            wsse = UsernameToken(self.config["username"], self.config["password"])
        timeout = int(self.config.get("timeout_seconds", 10))
        try:
            client = Client(
                wsdl=str(self._wsdl),
                transport=Transport(timeout=timeout, operation_timeout=timeout),
                wsse=wsse,
            )
        except Exception as exc:
            raise ConnectorError("WSDL could not be loaded") from exc
        check_service_hosts(endpoint_addresses(client), self._allowed_hosts)
        return client

    def health_check(self) -> dict[str, Any]:
        self._client()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        names = op.get("parameters", [])
        require_arguments(names, arguments)
        client = self._client()
        method = getattr(client.service, op["soap_operation"], None)
        if method is None:
            raise ConnectorError("SOAP operation not found in WSDL")
        try:
            result = method(**{name: arguments[name] for name in names})
        except Exception as exc:  # SOAP faults can echo internals; never surface them
            raise ConnectorError("SOAP call failed") from exc

        from zeep.helpers import serialize_object

        data = json.loads(json.dumps(jsonable(serialize_object(result)), default=str))
        return {"status": "success", "operation": operation, "data": data}
