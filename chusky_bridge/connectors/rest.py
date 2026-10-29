import json
import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers
from chusky_bridge.connectors.safe_http import METHODS, HttpOrigin, encode_segment

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class RestConnector(BaseConnector):
    """REST adapter pinned to one HTTPS origin. Path parameters become single encoded segments.
    GET arguments go to the query string. Other methods send them as a JSON body."""

    connector_type = "rest"
    secret_field = "api_key"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.http = HttpOrigin.from_config(config, extra_headers={"Accept": "application/json"})

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        method = str(op.get("method") or "GET").upper()
        if method not in METHODS:
            raise ConnectorError(f"{name}: HTTP method not allowed")
        if method != "GET" and op.get("read_only") is True:
            raise ConnectorError(f"{name}: non-GET methods must set read_only: false")
        path = str(op.get("path_template") or "")
        if not path.startswith("/") or ".." in path:
            raise ConnectorError(f"{name}: path_template must be absolute and must not contain '..'")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        if not set(_PLACEHOLDER.findall(path)) <= set(params):
            raise ConnectorError(f"{name}: every path placeholder must be a declared parameter")

    def health_check(self) -> dict[str, Any]:
        health_path = self.config.get("health_path")
        if not health_path:
            return {"status": "not_configured"}
        self.http.request("GET", health_path)
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        method = str(op.get("method") or "GET").upper()
        names = op.get("parameters", [])
        require_arguments(names, arguments)

        path = str(op.get("path_template") or "")
        remaining: dict[str, Any] = {}
        for name in names:
            token = "{" + name + "}"
            if token in path:
                path = path.replace(token, encode_segment(arguments[name]))
            else:
                remaining[name] = arguments[name]
        if "{" in path:
            raise ConnectorError("unresolved path parameter")

        status, content_type, raw = self.http.request(method, path, params=remaining, json_body=remaining or None)
        if "json" in content_type:
            try:
                data = json.loads(raw)
            except ValueError as exc:
                raise ConnectorError("upstream returned invalid JSON") from exc
            return {"status": "success", "operation": operation, "http_status": status, "data": data}
        return {
            "status": "success",
            "operation": operation,
            "http_status": status,
            "text": raw.decode("utf-8", errors="replace"),
        }
