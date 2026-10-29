import re
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from chusky_bridge.connectors.base import ConnectorError

_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")
_FORBIDDEN = tuple(
    getattr(exp, name)
    for name in ("Insert", "Update", "Delete", "Create", "Drop", "Alter", "Command", "Into", "Lock")
    if hasattr(exp, name)
)


def bind_named(query: str) -> tuple[str, list[str]]:
    """Convert :name placeholders to positional '?' markers. Returns the names in order."""
    names: list[str] = []

    def replace(match: re.Match) -> str:
        names.append(match.group(1))
        return "?"

    return _NAMED.sub(replace, query), names


def validate_select(query: str, dialect: str | None) -> None:
    """Accept exactly one read-only SELECT. Reject DML, DDL, SELECT INTO, and row locks."""
    bound, _ = bind_named(query)
    try:
        statements = [s for s in sqlglot.parse(bound, read=dialect) if s is not None]
    except (SqlglotError, ValueError) as exc:
        raise ConnectorError(
            "query could not be parsed for the configured dialect; simplify it or set sql_dialect"
        ) from exc
    if len(statements) != 1:
        raise ConnectorError("exactly one statement is allowed")
    statement: Any = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)):
        raise ConnectorError("only SELECT statements are allowed")
    if _FORBIDDEN and statement.find(*_FORBIDDEN):
        raise ConnectorError("query contains a forbidden clause (INTO, row locking, or data modification)")
