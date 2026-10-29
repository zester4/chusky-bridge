import contextvars
import json
import logging
import sys
import uuid
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

TOOL_CALLS = Counter("chusky_tool_calls_total", "Tool call outcomes by decision", ["decision"])
TOOL_LATENCY = Histogram(
    "chusky_tool_call_seconds",
    "Upstream execution latency by adapter type",
    ["connector_type"],
)


def current_request_id() -> str:
    return request_id_var.get() or str(uuid.uuid4())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get() or None,
        }
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_output else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
