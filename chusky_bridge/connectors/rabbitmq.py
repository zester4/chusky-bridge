import re
import ssl
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments

_QUEUE = re.compile(r"^[A-Za-z0-9._:\-]{1,255}$")
MAX_MESSAGES = 100
MAX_BODY_CHARS = 4000


class RabbitMqConnector(BaseConnector):
    """RabbitMQ peek adapter over AMQP 0-9-1.

    AMQP has no true browse, so this uses basic_get with auto_ack off and then requeues every
    message it read. Messages return to the queue in their original order and are marked
    redelivered. Consumers should treat the redelivered flag as informational. The queue is
    checked with a passive declare, so this never creates queues."""

    connector_type = "rabbitmq"
    secret_field = "password"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "peek" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: rabbitmq operations must be mode 'peek' and read_only")
        if not _QUEUE.match(str(op.get("queue") or "")):
            raise ConnectorError(f"{name}: invalid queue name")
        if op.get("parameters", []) != ["max_messages"]:
            raise ConnectorError(f"{name}: peek takes exactly the parameter max_messages")
        if not connection.get("host"):
            raise ConnectorError(f"{name}: connection needs host")

    def _open(self) -> Any:
        try:
            import pika
        except ImportError as exc:
            raise ConnectorError("the AMQP client (pika) is not installed") from exc
        tls = bool(self.config.get("tls", True))
        ssl_options = pika.SSLOptions(ssl.create_default_context()) if tls else None
        params = pika.ConnectionParameters(
            host=self.config["host"],
            port=int(self.config.get("port", 5671 if tls else 5672)),
            virtual_host=self.config.get("virtual_host", "/"),
            credentials=pika.PlainCredentials(self.config.get("username", ""), self.config.get("password", "")),
            ssl_options=ssl_options,
            socket_timeout=float(self.config.get("timeout_seconds", 10)),
            blocked_connection_timeout=float(self.config.get("timeout_seconds", 10)),
        )
        try:
            return pika.BlockingConnection(params)
        except Exception as exc:
            raise ConnectorError("AMQP connection failed") from exc

    def health_check(self) -> dict[str, Any]:
        connection = self._open()
        connection.close()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(["max_messages"], arguments)
        queue = op["queue"]
        if queue not in self.config.get("allowed_queues", []):
            raise ConnectorError("queue is not in the allowlist for this connector")
        limit = max(1, min(int(arguments["max_messages"]), MAX_MESSAGES, self.max_rows))

        connection = self._open()
        rows: list[dict[str, Any]] = []
        try:
            channel = connection.channel()
            try:
                channel.queue_declare(queue=queue, passive=True)
            except Exception as exc:
                raise ConnectorError("queue not found") from exc
            tags: list[int] = []
            for _ in range(limit):
                method, properties, body = channel.basic_get(queue=queue, auto_ack=False)
                if method is None:
                    break
                tags.append(method.delivery_tag)
                rows.append(
                    {
                        "message_id": getattr(properties, "message_id", None),
                        "redelivered": bool(method.redelivered),
                        "body": (body or b"").decode("utf-8", errors="replace")[:MAX_BODY_CHARS],
                    }
                )
            if tags:
                channel.basic_nack(delivery_tag=tags[-1], multiple=True, requeue=True)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("peek failed") from exc
        finally:
            connection.close()

        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}
