import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from chusky_bridge.connectors.base import (
    BaseConnector,
    ConnectorError,
    require_arguments,
    tabular_result,
    validate_identifiers,
)

_FUNCTION = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")


class PostgresConnector(BaseConnector):
    """Read-only PostgreSQL adapter. Calls reviewed functions inside server-enforced read-only sessions."""

    connector_type = "postgres"
    secret_field = "dsn"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "function" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: postgres operations must be mode 'function' and read_only")
        if not _FUNCTION.match(str(op.get("function") or "")):
            raise ConnectorError(f"{name}: invalid function name")
        validate_identifiers(op.get("parameters", []), "parameter")

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        timeout = int(self.config.get("timeout_seconds", 10))
        try:
            conn = psycopg.connect(
                self.config["dsn"],
                connect_timeout=timeout,
                options=f"-c default_transaction_read_only=on -c statement_timeout={timeout * 1000}",
            )
        except psycopg.Error as exc:
            raise ConnectorError("database connection failed") from exc
        try:
            yield conn
        finally:
            conn.close()

    def health_check(self) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        if op.get("mode") != "function" or op.get("read_only") is not True:
            raise ConnectorError("only read-only function operations are allowed")
        function = op.get("function") or ""
        if not _FUNCTION.match(function):
            raise ConnectorError("invalid function name in manifest")

        names: list[str] = op.get("parameters", [])
        require_arguments(names, arguments)
        placeholders = ", ".join("%s" for _ in names)
        sql = f"SELECT * FROM {function}({placeholders})"

        with self._connect() as conn, conn.cursor() as cursor:
            try:
                cursor.execute(sql, [arguments[name] for name in names])
            except psycopg.Error as exc:
                raise ConnectorError("operation failed upstream") from exc
            columns = [column.name for column in cursor.description or []]
            rows = cursor.fetchmany(self.max_rows)

        return tabular_result(operation, columns, rows, self.max_rows)
