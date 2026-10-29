from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from chusky_bridge.connectors.base import (
    BaseConnector,
    ConnectorError,
    require_arguments,
    tabular_result,
    validate_identifiers,
)
from chusky_bridge.connectors.sql_select import bind_named, validate_select


class OdbcConnector(BaseConnector):
    """Generic ODBC adapter. Covers SQL Server, Oracle, Db2 (LUW and for i), MySQL, Informix,
    Sybase, Teradata, Firebird, Access, and any system with an ODBC driver.

    Operations are reviewed SELECT statements with named :parameters. Each SELECT is parsed
    and checked at registration. Values are always bound, never interpolated. The database
    account should also be read-only. That is defense in depth, not the only control.
    """

    connector_type = "odbc"
    secret_field = "connection_string"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "select":
            raise ConnectorError(f"{name}: odbc mode must be 'select'")
        query = op.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ConnectorError(f"{name}: query is required")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        _, names = bind_named(query)
        if sorted(set(names)) != sorted(set(params)):
            raise ConnectorError(f"{name}: query placeholders must match declared parameters exactly")
        validate_select(query, connection.get("sql_dialect"))

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            import pyodbc
        except ImportError as exc:
            raise ConnectorError("the ODBC driver (pyodbc) is not installed on this runtime") from exc
        try:
            conn = pyodbc.connect(self.config["connection_string"], timeout=int(self.config.get("timeout_seconds", 10)))
        except pyodbc.Error as exc:
            raise ConnectorError("database connection failed") from exc
        try:
            yield conn
        finally:
            conn.close()

    def health_check(self) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        if op.get("mode") != "select":
            raise ConnectorError("only select operations are allowed")
        sql, names = bind_named(op["query"])
        require_arguments(names, arguments)
        params = [arguments[name] for name in names]

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.timeout = int(self.config.get("timeout_seconds", 10))
            try:
                cursor.execute(sql, *params)
            except Exception as exc:  # driver errors vary; never echo them upstream
                raise ConnectorError("query failed upstream") from exc
            if cursor.description is None:
                raise ConnectorError("query returned no result set")
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchmany(self.max_rows)

        return tabular_result(operation, columns, rows, self.max_rows)
