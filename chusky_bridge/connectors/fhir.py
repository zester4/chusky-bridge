import json
import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers
from chusky_bridge.connectors.safe_http import HttpOrigin, encode_segment

FHIR_RESOURCES = frozenset(
    {
        "Patient",
        "Observation",
        "Encounter",
        "Condition",
        "AllergyIntolerance",
        "MedicationRequest",
        "DiagnosticReport",
        "Practitioner",
        "Organization",
        "Appointment",
        "Coverage",
        "Immunization",
    }
)
_SEARCH_PARAM = re.compile(r"^[a-z][a-z0-9\-]{0,63}$")
_FORBIDDEN_PREFIXES = ("_include", "_revinclude", "_has", "_filter", "_graph")
MAX_PAGE = 100


class FhirConnector(BaseConnector):
    """FHIR R4 adapter. Read-by-id and search only, against allowlisted resource types.
    Search parameters are mapped from manifest arguments, so clients cannot pass _include or _has
    to pull large graphs. Epic, Oracle Health, and Meditech Expanse need their vendor's OAuth
    (SMART Backend Services) flow. This adapter expects a bearer token from that flow in api_key."""

    connector_type = "fhir"
    secret_field = "api_key"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.http = HttpOrigin.from_config(config, extra_headers={"Accept": "application/fhir+json"})

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("resource") not in FHIR_RESOURCES:
            raise ConnectorError(f"{name}: resource must be one of the allowlisted FHIR resource types")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        mode = op.get("mode")
        if mode == "read":
            if params != ["id"]:
                raise ConnectorError(f"{name}: read operations take exactly one parameter named id")
        elif mode == "search":
            mapping = op.get("search_parameters") or {}
            if not mapping:
                raise ConnectorError(f"{name}: search operations need search_parameters")
            for arg, fhir_name in mapping.items():
                if arg not in params:
                    raise ConnectorError(f"{name}: search argument {arg} must be a declared parameter")
                if not _SEARCH_PARAM.match(str(fhir_name)) or str(fhir_name).startswith(_FORBIDDEN_PREFIXES):
                    raise ConnectorError(f"{name}: search parameter {fhir_name!r} is not allowed")
        else:
            raise ConnectorError(f"{name}: fhir mode must be 'read' or 'search'")

    def health_check(self) -> dict[str, Any]:
        self.http.request("GET", "/metadata")
        return {"status": "healthy"}

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        _, _, raw = self.http.request("GET", path, params=params)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise ConnectorError("upstream returned invalid FHIR JSON") from exc

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        resource = op["resource"]

        if op["mode"] == "read":
            data = self._get(f"/{resource}/{encode_segment(arguments['id'])}")
            return {"status": "success", "operation": operation, "resource": resource, "rows": [data]}

        params = {fhir_name: str(arguments[arg]) for arg, fhir_name in (op.get("search_parameters") or {}).items()}
        params["_count"] = str(min(self.max_rows, MAX_PAGE))
        bundle = self._get(f"/{resource}", params)
        entries = bundle.get("entry", []) if isinstance(bundle, dict) else []
        rows = [entry.get("resource", {}) for entry in entries][: self.max_rows]
        return {
            "status": "success",
            "operation": operation,
            "resource": resource,
            "total": bundle.get("total") if isinstance(bundle, dict) else None,
            "row_count": len(rows),
            "rows": rows,
        }
