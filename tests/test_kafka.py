from types import SimpleNamespace

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.kafka import KafkaConnector, _decode


class FakeConsumer:
    def __init__(self, records):
        self.records = records
        self.assigned = None
        self.seeked = None
        self.closed = False
        self.committed = False

    def assign(self, tps):
        self.assigned = tps

    def seek(self, tp, offset):
        self.seeked = (tp, offset)

    def poll(self, timeout_ms, max_records):
        return {self.assigned[0]: self.records[:max_records]}

    def close(self):
        self.closed = True

    def commit(self, *a, **k):
        self.committed = True


def _connector():
    return KafkaConnector(
        {
            "bootstrap_servers": "k1:9093",
            "allowed_topics": ["orders.v1"],
            "max_rows": 50,
            "timeout_seconds": 1,
            "operations": {
                "peek": {
                    "mode": "peek",
                    "topic": "orders.v1",
                    "parameters": ["partition", "offset", "max_messages"],
                    "read_only": True,
                }
            },
        }
    )


def test_peek_returns_decoded_messages_and_never_commits(monkeypatch):
    records = [
        SimpleNamespace(offset=7, timestamp=123, key=b"k1", value=b'{"order": "A1"}'),
        SimpleNamespace(offset=8, timestamp=124, key=None, value=b"plain text"),
    ]
    consumer = FakeConsumer(records)
    connector = _connector()
    monkeypatch.setattr(connector, "_consumer", lambda: consumer)

    result = connector.execute("peek", {"partition": 0, "offset": 7, "max_messages": 10})

    assert result["row_count"] == 2
    assert result["rows"][0]["value"] == {"order": "A1"}
    assert result["rows"][1]["value"] == "plain text"
    assert consumer.seeked[1] == 7
    assert consumer.committed is False
    assert consumer.closed is True


def test_topic_outside_allowlist_refused(monkeypatch):
    connector = _connector()
    connector.config["operations"]["peek"]["topic"] = "payroll.v1"
    with pytest.raises(ConnectorError, match="allowlist"):
        connector.execute("peek", {"partition": 0, "offset": 0, "max_messages": 1})


def test_write_style_kafka_operation_rejected_at_registration():
    with pytest.raises(ConnectorError):
        KafkaConnector.validate_operation(
            "produce", {"mode": "produce", "topic": "t", "parameters": [], "read_only": False}, {}
        )


def test_decode_truncates_large_values():
    assert len(_decode(b"x" * 10_000)) == 4000
