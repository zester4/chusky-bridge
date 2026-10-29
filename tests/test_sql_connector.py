from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.sql_server import SqlServerConnector

OPERATIONS = {
    "get_detail": {
        "mode": "stored_procedure",
        "procedure": "dbo.usp_mcp_GetPurchaseOrderDetail",
        "parameters": ["po_number"],
        "read_only": True,
    },
    "raw_sql": {"mode": "raw_sql", "procedure": "dbo.x", "parameters": [], "read_only": True},
    "injected_name": {
        "mode": "stored_procedure",
        "procedure": "dbo.x; DROP TABLE users",
        "parameters": [],
        "read_only": True,
    },
}


def _connector_with_fake_cursor():
    cursor = MagicMock()
    cursor.description = [("po_number", None)]
    cursor.fetchmany.return_value = [("PO-1",)]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    connector = SqlServerConnector(
        {"connection_string": "unused", "max_rows": 5, "timeout_seconds": 3, "operations": OPERATIONS}
    )

    @contextmanager
    def fake_connect():
        yield conn

    connector._connect = fake_connect
    return connector, cursor


def test_executes_stored_procedure_with_bound_parameters():
    connector, cursor = _connector_with_fake_cursor()
    result = connector.execute("get_detail", {"po_number": "PO-1"})
    cursor.execute.assert_called_once_with("EXEC dbo.usp_mcp_GetPurchaseOrderDetail ?", "PO-1")
    assert result["rows"] == [{"po_number": "PO-1"}] and result["row_count"] == 1


def test_unknown_operation_rejected():
    connector, _ = _connector_with_fake_cursor()
    with pytest.raises(ConnectorError, match="unknown operation"):
        connector.execute("drop_everything", {})


def test_raw_sql_mode_rejected():
    connector, cursor = _connector_with_fake_cursor()
    with pytest.raises(ConnectorError, match="only stored_procedure"):
        connector.execute("raw_sql", {})
    cursor.execute.assert_not_called()


def test_invalid_procedure_name_rejected_at_runtime():
    connector, cursor = _connector_with_fake_cursor()
    with pytest.raises(ConnectorError, match="invalid procedure name"):
        connector.execute("injected_name", {})
    cursor.execute.assert_not_called()


def test_invalid_procedure_name_rejected_at_registration():
    with pytest.raises(ConnectorError):
        SqlServerConnector.validate_operation("injected_name", OPERATIONS["injected_name"], {})


def test_missing_argument_rejected():
    connector, cursor = _connector_with_fake_cursor()
    with pytest.raises(ConnectorError, match="missing arguments"):
        connector.execute("get_detail", {})
    cursor.execute.assert_not_called()
