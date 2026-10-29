import json
import re
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers

_TOPIC = re.compile(r"^[A-Za-z0-9._\-]{1,249}$")
MAX_PEEK = 100
MAX_VALUE_CHARS = 4000


def _decode(raw: Any) -> Any:
    if raw is None:
        return None
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text[:MAX_VALUE_CHARS]
    try:
        return json.loads(text)
    except ValueError:
        return text


class KafkaConnector(BaseConnector):
    """Kafka adapter, read-only. Peeks at a partition from an explicit offset without a consumer group
    and never commits offsets. It can't produce messages, change topic config, or alter consumer groups."""

    connector_type = "kafka"
    secret_field = "sasl_password"

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "peek" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: kafka operations must be mode 'peek' and read_only")
        if not _TOPIC.match(str(op.get("topic") or "")):
            raise ConnectorError(f"{name}: invalid topic name")
        params = op.get("parameters", [])
        if sorted(params) != sorted(["partition", "offset", "max_messages"]):
            raise ConnectorError(f"{name}: kafka peek takes parameters partition, offset, max_messages")
        validate_identifiers(params, "parameter")

    def _consumer(self) -> Any:
        from kafka import KafkaConsumer

        return KafkaConsumer(
            bootstrap_servers=str(self.config["bootstrap_servers"]).split(","),
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            consumer_timeout_ms=int(self.config.get("timeout_seconds", 10)) * 1000,
            security_protocol=self.config.get("security_protocol", "SASL_SSL"),
            sasl_mechanism=self.config.get("sasl_mechanism", "SCRAM-SHA-512"),
            sasl_plain_username=self.config.get("username"),
            sasl_plain_password=self.config.get("sasl_password"),
        )

    def health_check(self) -> dict[str, Any]:
        consumer = self._consumer()
        try:
            consumer.topics()
        finally:
            consumer.close()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(["partition", "offset", "max_messages"], arguments)
        topic = op["topic"]
        if topic not in self.config.get("allowed_topics", []):
            raise ConnectorError("topic is not in the allowlist for this connector")

        from kafka import TopicPartition

        partition = int(arguments["partition"])
        offset = int(arguments["offset"])
        limit = min(int(arguments["max_messages"]), MAX_PEEK, self.max_rows)
        if partition < 0 or offset < 0 or limit < 1:
            raise ConnectorError("partition and offset must be >= 0 and max_messages >= 1")

        consumer = self._consumer()
        try:
            tp = TopicPartition(topic, partition)
            consumer.assign([tp])
            consumer.seek(tp, offset)
            batch = consumer.poll(timeout_ms=int(self.config.get("timeout_seconds", 10)) * 1000, max_records=limit)
            records = batch.get(tp, [])
        except Exception as exc:
            raise ConnectorError("kafka peek failed") from exc
        finally:
            consumer.close()

        rows = [
            {
                "offset": record.offset,
                "timestamp": record.timestamp,
                "key": _decode(record.key),
                "value": _decode(record.value),
            }
            for record in records[:limit]
        ]
        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}
