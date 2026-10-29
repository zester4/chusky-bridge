import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from chusky_bridge.cli import main
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.swift_gateway import SwiftGatewayConnector
from chusky_bridge.observability import JsonFormatter, request_id_var

ROOT = Path(__file__).resolve().parent.parent
SWIFT_CONNECTION = {
    "base_url": "https://swift-gw.example.internal/api",
    "client_cert_path": "c.pem",
    "client_key_path": "k.pem",
}


def test_swift_requires_mutual_tls():
    with pytest.raises(ConnectorError, match="mutual TLS"):
        SwiftGatewayConnector({"base_url": "https://gw.example.internal"})


def test_swift_submission_must_be_high_risk_and_approved():
    op = {
        "method": "POST",
        "path_template": "/messages",
        "parameters": ["message"],
        "read_only": False,
        "requires_approval": True,
        "risk_level": "medium",
    }
    with pytest.raises(ConnectorError, match="high"):
        SwiftGatewayConnector.validate_operation("submit", op, SWIFT_CONNECTION)


def test_swift_high_risk_submission_validates():
    op = {
        "method": "POST",
        "path_template": "/messages",
        "parameters": ["message"],
        "read_only": False,
        "requires_approval": True,
        "risk_level": "high",
    }
    SwiftGatewayConnector.validate_operation("submit", op, SWIFT_CONNECTION)


def test_swift_message_type_format():
    op = {
        "method": "GET",
        "path_template": "/messages/{ref}",
        "parameters": ["ref"],
        "read_only": True,
        "message_type": "bogus",
    }
    with pytest.raises(ConnectorError, match="message_type"):
        SwiftGatewayConnector.validate_operation("status", op, SWIFT_CONNECTION)


def test_json_log_line_carries_request_id():
    token = request_id_var.set("req-abc-123")
    try:
        record = logging.LogRecord("chusky_bridge", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-abc-123"
    assert payload["level"] == "INFO"


def test_cli_validate_templates_passes():
    assert main(["validate", str(ROOT / "connectors_manifests" / "templates")]) == 0


def test_cli_validate_rejects_unsafe_manifest(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "connector: {name: bad_orders, type: odbc, version: 0.1.0}\n"
        "connection: {sql_dialect: oracle}\n"
        'operations:\n  purge:\n    mode: select\n    query: "DELETE FROM t WHERE id = :id"\n'
        "    parameters: [id]\n    read_only: true\n    required_scopes: [a.b.read]\n"
    )
    assert main(["validate", str(tmp_path)]) == 1


def test_cli_catalog_search_json(capsys):
    assert main(["catalog", "search", "epic", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any("Epic" in row["name"] for row in rows)


def test_cli_version(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "1.0.0"


def test_migrations_render_full_schema_offline():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "CHUSKY_DATABASE_URL": "postgresql://offline/offline"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for table in ("tenants", "connectors", "tool_definitions", "approval_requests", "audit_events"):
        assert f"CREATE TABLE {table}" in result.stdout
