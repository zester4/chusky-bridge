import contextlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from chusky_bridge.connectors.base import (
    BaseConnector,
    ConnectorError,
    jsonable,
    require_arguments,
    validate_identifiers,
)

_FUNCTION_MODULE = re.compile(r"^[A-Z][A-Z0-9_]{2,59}$")
_RFC_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,59}$")
COMMIT_FUNCTION = "BAPI_TRANSACTION_COMMIT"
ROLLBACK_FUNCTION = "BAPI_TRANSACTION_ROLLBACK"


def _return_messages(result: Any) -> list[dict[str, str]]:
    """Collect BAPI RETURN messages. Handles both table and structure forms."""
    if not isinstance(result, dict):
        return []
    raw = result.get("RETURN", [])
    entries = raw if isinstance(raw, list) else [raw]
    messages = []
    for entry in entries:
        if isinstance(entry, dict):
            messages.append(
                {
                    "type": str(entry.get("TYPE", "")),
                    "id": str(entry.get("ID", "")),
                    "number": str(entry.get("NUMBER", "")),
                    "message": str(entry.get("MESSAGE", "")),
                }
            )
    return messages


class SapRfcConnector(BaseConnector):
    """SAP RFC/BAPI adapter using the SAP NW RFC SDK through pyrfc.

    Reads call a read-only function module and return its results.

    Writes are a two-step pattern: the BAPI runs, its RETURN table is checked, and then
    BAPI_TRANSACTION_COMMIT (or a rollback on any error message) finishes the unit of work. Writes
    must set requires_approval: true, so they run only after a reviewer approves them.
    The SAP RFC SDK is licensed by SAP and installed separately (docs/deployment.md)."""

    connector_type = "sap_rfc"
    secret_field = "passwd"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        fm = str(op.get("function_module") or "")
        if not _FUNCTION_MODULE.match(fm):
            raise ConnectorError(f"{name}: function_module must be an uppercase SAP function name")
        read_only = op.get("read_only") is True
        if not read_only and op.get("requires_approval") is not True:
            raise ConnectorError(f"{name}: SAP writes must set requires_approval: true")
        commit = op.get("commit_function")
        if commit is not None and not _FUNCTION_MODULE.match(str(commit)):
            raise ConnectorError(f"{name}: commit_function must be an uppercase SAP function name")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        for arg, rfc_name in (op.get("rfc_names") or {}).items():
            if arg not in params or not _RFC_NAME.match(str(rfc_name)):
                raise ConnectorError(f"{name}: invalid rfc_names mapping for {arg}")
        for key in ("ashost", "sysnr", "client", "user"):
            if not connection.get(key):
                raise ConnectorError(f"{name}: connection needs {key}")

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            import pyrfc
        except ImportError as exc:
            raise ConnectorError("the SAP RFC client (pyrfc and the SAP NW RFC SDK) is not installed") from exc
        try:
            conn = pyrfc.Connection(
                ashost=self.config["ashost"],
                sysnr=str(self.config["sysnr"]),
                client=str(self.config["client"]),
                user=self.config["user"],
                passwd=self.config["passwd"],
                lang=self.config.get("lang", "EN"),
            )
        except Exception as exc:
            raise ConnectorError("SAP connection failed") from exc
        try:
            yield conn
        finally:
            conn.close()

    def health_check(self) -> dict[str, Any]:
        with self._connect() as conn:
            conn.call("RFC_PING")
        return {"status": "healthy"}

    @staticmethod
    def _try_rollback(conn: Any) -> None:
        with contextlib.suppress(Exception):
            conn.call(ROLLBACK_FUNCTION)

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        names = op.get("parameters", [])
        require_arguments(names, arguments)
        rfc_names = op.get("rfc_names") or {}
        kwargs = {rfc_names.get(name, name.upper()): arguments[name] for name in names}
        is_write = op.get("read_only") is not True

        with self._connect() as conn:
            try:
                result = conn.call(op["function_module"], **kwargs)
            except Exception as exc:
                if is_write:
                    self._try_rollback(conn)
                raise ConnectorError("SAP call failed") from exc

            messages = _return_messages(result)
            if is_write:
                if any(m["type"] in {"E", "A"} for m in messages):
                    self._try_rollback(conn)
                    raise ConnectorError("SAP rejected the change; nothing was committed")
                try:
                    conn.call(op.get("commit_function") or COMMIT_FUNCTION, WAIT="X")
                except Exception as exc:
                    self._try_rollback(conn)
                    raise ConnectorError("SAP commit failed; the change was rolled back") from exc

        data = jsonable(result)
        if isinstance(data, dict):
            for key, value in list(data.items()):
                if isinstance(value, list):
                    data[key] = value[: self.max_rows]
        return {
            "status": "committed" if is_write else "success",
            "operation": operation,
            "result": data,
            "messages": messages[: self.max_rows],
        }
