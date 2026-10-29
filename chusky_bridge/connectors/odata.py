import json
import math
import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers
from chusky_bridge.connectors.safe_http import HttpOrigin, encode_segment

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_OPERATORS = {"eq": "eq", "ne": "ne", "gt": "gt", "ge": "ge", "lt": "lt", "le": "le"}


def odata_literal(value: Any) -> str:
    """Render a value as an OData literal. Strings are quoted with embedded quotes doubled."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConnectorError("non-finite number in filter")
        return repr(value)
    if isinstance(value, str):
        if len(value) > 1000:
            raise ConnectorError("filter value too long")
        return "'" + value.replace("'", "''") + "'"
    raise ConnectorError("unsupported filter value type")


def build_filter(filters: list[dict[str, Any]], arguments: dict[str, Any]) -> str | None:
    clauses = [f"{f['field']} {_OPERATORS[f['op']]} {odata_literal(arguments[f['parameter']])}" for f in filters]
    return " and ".join(clauses) or None


def normalize_odata(data: Any) -> list[Any]:
    """Accept OData v4 ({value: [...]}), v2 ({d: {results: [...]}}), and single entities."""
    if isinstance(data, dict):
        if isinstance(data.get("value"), list):
            return data["value"]
        if "d" in data:
            inner = data["d"]
            if isinstance(inner, dict) and isinstance(inner.get("results"), list):
                return inner["results"]
            return [inner]
        return [data]
    return []


class ODataConnector(BaseConnector):
    """OData v2/v4 adapter for SAP Gateway, Dynamics 365, NetSuite-style services, and similar.

    Entity sets, fields, and operators are allowlisted in the manifest. Filter values are
    escaped as OData literals. Clients never supply raw $filter strings.
    """

    connector_type = "odata"
    secret_field = "api_key"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.http = HttpOrigin.from_config(config, extra_headers={"Accept": "application/json"})

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        entity = str(op.get("entity_set") or "")
        if not _IDENT.match(entity):
            raise ConnectorError(f"{name}: invalid entity_set")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        key = op.get("key_parameter")
        if key is not None and key not in params:
            raise ConnectorError(f"{name}: key_parameter must be a declared parameter")
        for field in op.get("select") or []:
            if not _IDENT.match(str(field)):
                raise ConnectorError(f"{name}: invalid select field {field!r}")
        for f in op.get("filters") or []:
            if not _IDENT.match(str(f.get("field", ""))):
                raise ConnectorError(f"{name}: invalid filter field")
            if f.get("parameter") not in params:
                raise ConnectorError(f"{name}: filter parameter must be declared")
            if f.get("op") not in _OPERATORS:
                raise ConnectorError(f"{name}: unsupported filter operator")

    def health_check(self) -> dict[str, Any]:
        self.http.request("GET", "/$metadata", params={"$format": "json"})
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        entity = op["entity_set"]
        max_rows = self.max_rows

        if op.get("key_parameter"):
            path = f"/{entity}({encode_segment(odata_literal(arguments[op['key_parameter']]))})"
            params: dict[str, str] = {"$format": "json"}
        else:
            path = f"/{entity}"
            params = {"$format": "json", "$top": str(max_rows)}
            clauses = []
            for f in op.get("filters") or []:
                clauses.append(f"{f['field']} {_OPERATORS[f['op']]} {odata_literal(arguments[f['parameter']])}")
            if clauses:
                params["$filter"] = " and ".join(clauses)
            if op.get("select"):
                params["$select"] = ",".join(op["select"])

        _, _, raw = self.http.request("GET", path, params=params)
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ConnectorError("upstream returned invalid JSON") from exc
        rows = normalize_odata(data)[:max_rows]
        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}
