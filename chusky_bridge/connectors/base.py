import datetime
import decimal
import math
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class ConnectorError(Exception):
    """Safe to surface to agents. Must never contain credentials or raw upstream bodies."""


def validate_identifiers(names: list[str], label: str) -> None:
    for name in names:
        if not isinstance(name, str) or not IDENT.match(name):
            raise ConnectorError(f"invalid {label} name: {name!r}")


def require_arguments(names: list[str], arguments: dict[str, Any]) -> None:
    missing = [name for name in names if name not in arguments]
    if missing:
        raise ConnectorError(f"missing arguments: {', '.join(missing)}")


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


def tabular_result(operation: str, columns: list[str], rows: list, max_rows: int) -> dict[str, Any]:
    data = [{col: jsonable(val) for col, val in zip(columns, row, strict=False)} for row in rows[:max_rows]]
    return {"status": "success", "operation": operation, "row_count": len(data), "rows": data}


class BaseConnector(ABC):
    """Contract every adapter implements.

    validate_operation runs at registration, so unsafe manifests never activate.
    execute runs per call with already-validated, schema-checked arguments.
    """

    connector_type: ClassVar[str] = ""
    # Config key that receives the resolved secret (from secret_ref).
    secret_field: ClassVar[str | None] = None

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        """Raise ConnectorError for unsafe or malformed operations. The default accepts everything."""
        return None

    @property
    def max_rows(self) -> int:
        return int(self.config.get("max_rows", 100))

    def _operation(self, name: str) -> dict[str, Any]:
        operations = self.config.get("operations", {})
        if name not in operations:
            raise ConnectorError("unknown operation")
        return operations[name]

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return health without exposing credentials."""

    @abstractmethod
    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one named operation."""
