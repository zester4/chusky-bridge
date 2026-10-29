import re
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

_PROCEDURE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$")


class SqlServerConnector(BaseConnector):
    """SQL Server adapter. Calls only named stored procedures and binds every value as a parameter."""

    connector_type = "sql_server"
    secret_field = "connection_string"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "stored_procedure":
            raise ConnectorError(f"{name}: sql_server mode must be 'stored_procedure'")
        if not _PROCEDURE.match(str(op.get("procedure") or "")):
            raise ConnectorError(f"{name}: invalid procedure name")
        validate_identifiers(op.get("parameters", []), "parameter")

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            import pyodbc
        except ImportError as exc:
            raise ConnectorError("the SQL Server driver is not installed on this runtime") from exc
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
        if op.get("mode") != "stored_procedure":
            raise ConnectorError("only stored_procedure operations are allowed")
        procedure = op.get("procedure") or ""
        if not _PROCEDURE.match(procedure):
            raise ConnectorError("invalid procedure name in manifest")

        names: list[str] = op.get("parameters", [])
        require_arguments(names, arguments)
        params = [arguments[name] for name in names]
        placeholders = ", ".join("?" for _ in params)
        sql = f"EXEC {procedure} {placeholders}".rstrip()

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.timeout = int(self.config.get("timeout_seconds", 10))
            try:
                cursor.execute(sql, *params)
            except Exception as exc:
                raise ConnectorError("operation failed upstream") from exc
            if cursor.description is None:
                return {"status": "completed", "operation": operation}
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchmany(self.max_rows)

        return tabular_result(operation, columns, rows, self.max_rows)
