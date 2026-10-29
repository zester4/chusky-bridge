import pytest

from chusky_bridge.mcp.manifest import ManifestError, Operation, parse_manifest
from chusky_bridge.mcp.tool_registry import build_input_schema

VALID = """
connector:
  name: legacy_erp
  type: sql_server
  version: 1.0.0
connection:
  secret_ref: legacy_erp_db
operations:
  get_detail:
    mode: stored_procedure
    procedure: dbo.usp_mcp_GetPurchaseOrderDetail
    parameters: [po_number]
    read_only: true
    required_scopes: [erp.purchase_orders.read]
"""


def test_parses_valid_manifest():
    parsed = parse_manifest(VALID)
    assert parsed.manifest.connector.type == "sql_server"
    assert parsed.manifest.connector.status == "active"
    assert len(parsed.hash) == 64


def test_hash_is_stable():
    assert parse_manifest(VALID).hash == parse_manifest(VALID).hash


def test_write_operation_without_approval_rejected():
    with pytest.raises(ManifestError):
        parse_manifest(VALID.replace("read_only: true", "read_only: false"))


def test_inline_secret_rejected():
    with pytest.raises(ManifestError):
        parse_manifest(VALID.replace("secret_ref: legacy_erp_db", "password: hunter2"))


def test_high_risk_requires_approval():
    with pytest.raises(ValueError):
        Operation(risk_level="high", read_only=True, requires_approval=False, required_scopes=["erp.x.read"])


def test_operation_requires_scopes():
    with pytest.raises(ValueError):
        Operation(required_scopes=[])


def test_invalid_operation_name_rejected():
    with pytest.raises(ManifestError):
        parse_manifest(VALID.replace("get_detail:", "Get-Detail:"))


def test_adapter_specific_fields_survive_parsing():
    text = VALID.replace("mode: stored_procedure", "mode: select\n    query: 'SELECT 1 FROM t WHERE a = :a'")
    text = text.replace("type: sql_server", "type: odbc")
    text = text.replace("parameters: [po_number]", "parameters: [a]")
    parsed = parse_manifest(text)
    assert parsed.manifest.operations["get_detail"].model_dump()["query"].startswith("SELECT")


def test_generated_schema_is_closed():
    schema = build_input_schema(Operation(parameters=["po_number"], required_scopes=["erp.x.read"]))
    assert schema["additionalProperties"] is False and schema["required"] == ["po_number"]
