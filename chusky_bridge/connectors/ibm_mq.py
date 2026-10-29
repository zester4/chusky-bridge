import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments

_QUEUE = re.compile(r"^[A-Za-z0-9._/]{1,48}$")
MAX_MESSAGES = 100
MAX_BODY_CHARS = 4000


def _text(body: Any) -> str:
    if isinstance(body, (bytes, bytearray)):
        return bytes(body).decode("utf-8", errors="replace")[:MAX_BODY_CHARS]
    return str(body)[:MAX_BODY_CHARS]


class IbmMqConnector(BaseConnector):
    """IBM MQ browse adapter. Opens queues with MQOO_BROWSE and reads with MQGMO_BROWSE_FIRST and
    MQGMO_BROWSE_NEXT, so messages are inspected but never removed. Requires the MQ client
    libraries and pymqi on the runtime. Use a dedicated MQ user with browse-only authority."""

    connector_type = "ibm_mq"
    secret_field = "password"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "browse" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: ibm_mq operations must be mode 'browse' and read_only")
        if not _QUEUE.match(str(op.get("queue") or "")):
            raise ConnectorError(f"{name}: invalid queue name")
        if op.get("parameters", []) != ["max_messages"]:
            raise ConnectorError(f"{name}: browse takes exactly the parameter max_messages")
        for key in ("queue_manager", "channel", "conn_name"):
            if not connection.get(key):
                raise ConnectorError(f"{name}: connection needs {key}")

    @contextmanager
    def _qmgr(self) -> Iterator[tuple[Any, Any]]:
        try:
            import pymqi
        except ImportError as exc:
            raise ConnectorError("IBM MQ client (pymqi and the MQ client libraries) is not installed") from exc
        try:
            qmgr = pymqi.connect(
                self.config["queue_manager"],
                self.config["channel"],
                self.config["conn_name"],
                self.config.get("username"),
                self.config.get("password"),
            )
        except pymqi.MQMIError as exc:
            raise ConnectorError("queue manager connection failed") from exc
        try:
            yield pymqi, qmgr
        finally:
            qmgr.disconnect()

    def health_check(self) -> dict[str, Any]:
        with self._qmgr():
            pass
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(["max_messages"], arguments)
        limit = max(1, min(int(arguments["max_messages"]), MAX_MESSAGES, self.max_rows))
        rows: list[dict[str, Any]] = []

        with self._qmgr() as (mq, qmgr):
            cmqc = mq.CMQC
            try:
                queue = mq.Queue(qmgr, op["queue"], cmqc.MQOO_BROWSE | cmqc.MQOO_FAIL_IF_QUIESCING)
            except mq.MQMIError as exc:
                raise ConnectorError("queue could not be opened for browse") from exc
            try:
                gmo = mq.GMO()
                gmo.Options = cmqc.MQGMO_BROWSE_FIRST | cmqc.MQGMO_NO_WAIT
                while len(rows) < limit:
                    md = mq.MD()
                    try:
                        body = queue.get(None, md, gmo)
                    except mq.MQMIError as exc:
                        if exc.comp == cmqc.MQCC_FAILED and exc.reason == cmqc.MQRC_NO_MSG_AVAILABLE:
                            break
                        raise ConnectorError("browse failed") from exc
                    rows.append(
                        {
                            "message_id": bytes(md.MsgId).hex(),
                            "put_date": str(getattr(md, "PutDate", "")),
                            "put_time": str(getattr(md, "PutTime", "")),
                            "body": _text(body),
                        }
                    )
                    gmo.Options = cmqc.MQGMO_BROWSE_NEXT | cmqc.MQGMO_NO_WAIT
            finally:
                queue.close()

        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}
