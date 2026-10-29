import re
from typing import Any

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.rest import RestConnector

MESSAGE_TYPE = re.compile(r"^(pacs|camt|pain)\.\d{3}\.\d{3}\.\d{2}$")


class SwiftGatewayConnector(RestConnector):
    """SWIFT messaging through a connectivity gateway you operate (for example Alliance Gateway or a
    Message Partner API). Requires SWIFT membership.

    Mutual TLS is mandatory: every call presents a client certificate from the approved certificate
    directory. Reads fetch message status. Submissions are POST operations that must be high risk and
    require approval. The gateway performs SWIFT-side validation. Chusky Bridge does not replace it."""

    connector_type = "swift"
    secret_field = "api_key"

    def __init__(self, config: dict[str, Any]):
        if not config.get("client_cert_path") or not config.get("client_key_path"):
            raise ConnectorError("SWIFT connections require mutual TLS: client_cert_path and client_key_path")
        super().__init__(config)

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        super().validate_operation(name, op, connection)
        if not connection.get("client_cert_path") or not connection.get("client_key_path"):
            raise ConnectorError(f"{name}: SWIFT connections require mutual TLS")
        is_submission = str(op.get("method") or "GET").upper() != "GET"
        if is_submission and (op.get("risk_level") != "high" or op.get("requires_approval") is not True):
            raise ConnectorError(f"{name}: SWIFT submissions must be risk_level high and require approval")
        if op.get("message_type") is not None and not MESSAGE_TYPE.match(str(op["message_type"])):
            raise ConnectorError(f"{name}: message_type must look like pacs.008.001.08")
