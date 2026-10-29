import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.odbc import OdbcConnector
from chusky_bridge.connectors.sql_select import bind_named, validate_select


def _op(query, params=("order_number",)):
    return {"mode": "select", "query": query, "parameters": list(params)}


def test_binds_named_parameters_positionally():
    sql, names = bind_named("SELECT a FROM t WHERE x = :x AND y = :y AND z = :x")
    assert sql == "SELECT a FROM t WHERE x = ? AND y = ? AND z = ?"
    assert names == ["x", "y", "x"]


def test_postgres_cast_not_treated_as_parameter():
    _, names = bind_named("SELECT a::text FROM t WHERE x = :x")
    assert names == ["x"]


def test_plain_select_accepted():
    validate_select("SELECT ORDER_NUMBER FROM V WHERE ORDER_NUMBER = :n", "oracle")


def test_union_of_selects_accepted():
    validate_select("SELECT a FROM t1 WHERE a = :a UNION SELECT a FROM t2 WHERE a = :a", None)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM t WHERE id = :id",
        "UPDATE t SET a = 1 WHERE id = :id",
        "INSERT INTO t (a) VALUES (:id)",
        "SELECT a INTO backup FROM t WHERE id = :id",
        "SELECT a FROM t WHERE id = :id; DROP TABLE t",
    ],
)
def test_writes_and_multiple_statements_rejected(query):
    with pytest.raises(ConnectorError):
        validate_select(query, None)


def test_row_locking_rejected():
    with pytest.raises(ConnectorError):
        validate_select("SELECT a FROM t WHERE id = :id FOR UPDATE", None)


def test_manifest_placeholders_must_match_parameters():
    with pytest.raises(ConnectorError, match="must match"):
        OdbcConnector.validate_operation("op", _op("SELECT a FROM t WHERE x = :x", params=["y"]), {})


def test_valid_operation_passes_registration():
    OdbcConnector.validate_operation("op", _op("SELECT a FROM t WHERE x = :order_number"), {"sql_dialect": "oracle"})
