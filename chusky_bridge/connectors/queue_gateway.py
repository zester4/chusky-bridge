import json
import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments
from chusky_bridge.connectors.safe_http import HttpOrigin, encode_segment

KINDS = frozenset({"jms", "msmq"})
_QUEUE = re.compile(r"^[A-Za-z0-9._\-/]{1,200}$")
MAX_BODY_CHARS = 10_000
MAX_LIMIT = 100


class QueueGatewayConnector(BaseConnector):
    """JMS and MSMQ through a messaging gateway you deploy next to the broker.

    JMS brokers need a Java client and MSMQ needs Windows APIs, so neither runs natively in
    Python. The gateway exposes a small HTTPS contract that Chusky Bridge calls:

      GET  /queues/{queue}/messages?limit=N   browse, non-destructive, returns a JSON list
      POST /queues/{queue}/messages           send, body {"body": "..."}, returns {"message_id": ...}
      GET  /health                            liveness

    The gateway owns broker credentials, TLS to the broker, and browse-only authority. See
    docs/adapters.md for the full contract."""

    connector_type = "queue_gateway"
    secret_field = "api_key"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.kind = config.get("kind")
        self.http = HttpOrigin.from_config(config, extra_headers={"Accept": "application/json"})

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if connection.get("kind") not in KINDS:
            raise ConnectorError("connection kind must be 'jms' or 'msmq'")
        if not _QUEUE.match(str(op.get("queue") or "")):
            raise ConnectorError(f"{name}: invalid queue name")
        mode = op.get("mode")
        params = op.get("parameters", [])
        if mode == "browse":
            if op.get("read_only") is not True or params != ["max_messages"]:
                raise ConnectorError(f"{name}: browse must be read_only with parameter max_messages")
        elif mode == "send":
            if op.get("read_only") is not False or op.get("requires_approval") is not True or params != ["body"]:
                raise ConnectorError(f"{name}: send must require approval and take parameter body")
        else:
            raise ConnectorError(f"{name}: mode must be 'browse' or 'send'")

    def health_check(self) -> dict[str, Any]:
        self.http.request("GET", "/health")
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        queue = encode_segment(op["queue"])

        if op["mode"] == "browse":
            limit = max(1, min(int(arguments["max_messages"]), MAX_LIMIT, self.max_rows))
            _, _, raw = self.http.request("GET", f"/queues/{queue}/messages", params={"limit": str(limit)})
            messages = self._json(raw)
            if isinstance(messages, dict):
                messages = messages.get("messages", [])
            if not isinstance(messages, list):
                raise ConnectorError("gateway returned an unexpected browse payload")
            rows = messages[:limit]
            return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}

        body = str(arguments["body"])
        if len(body) > MAX_BODY_CHARS:
            raise ConnectorError("message body exceeds the size limit")
        _, _, raw = self.http.request("POST", f"/queues/{queue}/messages", json_body={"body": body})
        data = self._json(raw)
        return {
            "status": "sent",
            "operation": operation,
            "message_id": data.get("message_id") if isinstance(data, dict) else None,
        }

    @staticmethod
    def _json(raw: bytes) -> Any:
        try:
            return json.loads(raw or b"null")
        except ValueError as exc:
            raise ConnectorError("gateway returned invalid JSON") from exc
