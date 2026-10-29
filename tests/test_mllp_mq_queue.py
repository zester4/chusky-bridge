import sys
import types
from types import SimpleNamespace

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.ibm_mq import IbmMqConnector
from chusky_bridge.connectors.mllp import MllpConnector, build_message, frame, hl7_escape, unframe
from chusky_bridge.connectors.queue_gateway import QueueGatewayConnector
from chusky_bridge.connectors.rabbitmq import RabbitMqConnector

MLLP_TEMPLATE = (
    "MSH|^~\\&|CHUSKY|CHUSKY|RCV|RCV|20260101||QBP^Q22|MSG1|P|2.5\rQPD|Q22^Find Candidates^HL70471|{q_id}\rRCP|I|10^RD"
)
MLLP_CONNECTION = {"host": "hl7.example.internal", "port": 2575, "tls": True}


def _mllp_op(template=MLLP_TEMPLATE, params=("q_id",)):
    return {"mode": "query", "template": template, "parameters": list(params), "read_only": True}


def test_frame_and_unframe_round_trip():
    assert unframe(frame(b"MSH|x")) == b"MSH|x"
    assert unframe(b"\x0bPARTIAL") is None


def test_unframed_reply_rejected():
    with pytest.raises(ConnectorError):
        unframe(b"no framing here")


def test_hl7_escape_neutralizes_delimiters():
    assert hl7_escape("A|B^C&D~E\\F") == "A\\F\\B\\S\\C\\T\\D\\R\\E\\E\\F"


def test_value_cannot_inject_segments():
    with pytest.raises(ConnectorError):
        build_message(MLLP_TEMPLATE, {"q_id": "12\rPID|evil"})


def test_build_message_escapes_values():
    message = build_message(MLLP_TEMPLATE, {"q_id": "A|B"}).decode()
    assert "QPD|Q22^Find Candidates^HL70471|A\\F\\B" in message


def test_only_allowed_message_types():
    bad = MLLP_TEMPLATE.replace("QBP^Q22", "ADT^A01")
    with pytest.raises(ConnectorError, match="MSH-9"):
        MllpConnector.validate_operation("q", _mllp_op(bad), MLLP_CONNECTION)


def test_disallowed_segment_rejected():
    bad = MLLP_TEMPLATE + "\rOBX|1|ST"
    with pytest.raises(ConnectorError, match="not allowed"):
        MllpConnector.validate_operation("q", _mllp_op(bad), MLLP_CONNECTION)


def test_plaintext_requires_explicit_allow():
    with pytest.raises(ConnectorError, match="plaintext"):
        MllpConnector.validate_operation("q", _mllp_op(), {**MLLP_CONNECTION, "tls": False})


def test_exchange_parses_ack(monkeypatch):
    ack = frame(b"MSH|^~\\&|RCV|RCV|CHUSKY|CHUSKY|2026||ACK^Q22^ACK|1|P|2.5\rMSA|AA|MSG1\r")
    connector = MllpConnector({"host": "h", "operations": {"q": _mllp_op()}})
    connector._exchange = lambda message: ack
    result = connector.execute("q", {"q_id": "12345"})
    assert result["ack_code"] == "AA"
    assert result["message_type"] == "ACK^Q22^ACK"


class FakeMQError(Exception):
    def __init__(self, comp, reason):
        super().__init__(f"MQ {comp} {reason}")
        self.comp = comp
        self.reason = reason


def _fake_pymqi(messages):
    module = types.ModuleType("pymqi")

    class CMQC:
        MQOO_BROWSE = 16
        MQOO_FAIL_IF_QUIESCING = 8192
        MQGMO_BROWSE_FIRST = 16
        MQGMO_BROWSE_NEXT = 1024
        MQGMO_NO_WAIT = 0
        MQCC_FAILED = 2
        MQRC_NO_MSG_AVAILABLE = 2033

    class QMgr:
        closed = False

        def disconnect(self):
            QMgr.closed = True

    class Queue:
        def __init__(self, qmgr, name, options):
            self.pending = list(messages)
            self.closed = False

        def get(self, descriptor, md, gmo):
            if not self.pending:
                raise FakeMQError(CMQC.MQCC_FAILED, CMQC.MQRC_NO_MSG_AVAILABLE)
            md.MsgId = b"\x01\x02"
            md.PutDate = "20260101"
            md.PutTime = "120000"
            return self.pending.pop(0)

        def close(self):
            self.closed = True

    module.CMQC = CMQC
    module.MQMIError = FakeMQError
    module.GMO = lambda: SimpleNamespace(Options=0)
    module.MD = lambda: SimpleNamespace(MsgId=b"", PutDate="", PutTime="")
    module.connect = lambda *args: QMgr()
    module.Queue = Queue
    return module


MQ_CONNECTION = {"queue_manager": "QM1", "channel": "SVR.CHAN", "conn_name": "mq.example(1414)"}


def test_mq_browse_reads_without_removing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymqi", _fake_pymqi([b"order-1", b"order-2"]))
    connector = IbmMqConnector(
        {
            **MQ_CONNECTION,
            "operations": {
                "peek": {"mode": "browse", "queue": "ORDERS.OUT", "parameters": ["max_messages"], "read_only": True}
            },
        }
    )
    result = connector.execute("peek", {"max_messages": 10})
    assert [row["body"] for row in result["rows"]] == ["order-1", "order-2"]
    assert result["rows"][0]["message_id"] == "0102"


def test_mq_browse_respects_limit(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymqi", _fake_pymqi([b"a", b"b", b"c"]))
    connector = IbmMqConnector(
        {
            **MQ_CONNECTION,
            "operations": {"peek": {"mode": "browse", "queue": "Q", "parameters": ["max_messages"], "read_only": True}},
        }
    )
    assert connector.execute("peek", {"max_messages": 2})["row_count"] == 2


def test_mq_write_style_operation_rejected():
    with pytest.raises(ConnectorError):
        IbmMqConnector.validate_operation(
            "put", {"mode": "put", "queue": "Q", "parameters": ["max_messages"], "read_only": False}, MQ_CONNECTION
        )


def _fake_pika(messages, record):
    module = types.ModuleType("pika")

    class Channel:
        def queue_declare(self, queue, passive):
            record["declared"] = (queue, passive)

        def basic_get(self, queue, auto_ack):
            if not messages:
                return None, None, None
            body = messages.pop(0)
            method = SimpleNamespace(delivery_tag=len(record.setdefault("tags", [])) + 1, redelivered=False)
            record["tags"].append(method.delivery_tag)
            return method, SimpleNamespace(message_id=f"m{method.delivery_tag}"), body

        def basic_nack(self, delivery_tag, multiple, requeue):
            record["nack"] = (delivery_tag, multiple, requeue)

    class Connection:
        def channel(self):
            return Channel()

        def close(self):
            record["closed"] = True

    module.PlainCredentials = lambda u, p: (u, p)
    module.ConnectionParameters = lambda **kw: kw
    module.SSLOptions = lambda ctx: ctx
    module.BlockingConnection = lambda params: Connection()
    return module


def test_rabbitmq_peek_requeues_everything(monkeypatch):
    record = {}
    monkeypatch.setitem(sys.modules, "pika", _fake_pika([b"one", b"two"], record))
    connector = RabbitMqConnector(
        {
            "host": "mq",
            "allowed_queues": ["orders"],
            "operations": {
                "peek": {"mode": "peek", "queue": "orders", "parameters": ["max_messages"], "read_only": True}
            },
        }
    )
    result = connector.execute("peek", {"max_messages": 5})
    assert result["row_count"] == 2
    assert record["nack"] == (2, True, True)
    assert record["closed"] is True


def test_rabbitmq_queue_allowlist_enforced(monkeypatch):
    monkeypatch.setitem(sys.modules, "pika", _fake_pika([], {}))
    connector = RabbitMqConnector(
        {
            "host": "mq",
            "allowed_queues": ["orders"],
            "operations": {
                "peek": {"mode": "peek", "queue": "payroll", "parameters": ["max_messages"], "read_only": True}
            },
        }
    )
    with pytest.raises(ConnectorError, match="allowlist"):
        connector.execute("peek", {"max_messages": 1})


def _gateway(ops):
    return QueueGatewayConnector(
        {
            "kind": "jms",
            "base_url": "https://gw.example.internal/api",
            "api_key": "k",
            "operations": ops,
            "max_rows": 10,
        }
    )


def test_gateway_send_must_require_approval():
    with pytest.raises(ConnectorError, match="approval"):
        QueueGatewayConnector.validate_operation(
            "send",
            {"mode": "send", "queue": "orders", "parameters": ["body"], "read_only": False, "requires_approval": False},
            {"kind": "jms"},
        )


def test_gateway_browse_returns_gateway_messages():
    connector = _gateway(
        {"peek": {"mode": "browse", "queue": "orders", "parameters": ["max_messages"], "read_only": True}}
    )
    connector.http.request = lambda method, path, **kw: (200, "application/json", b'[{"id": 1}, {"id": 2}]')
    assert connector.execute("peek", {"max_messages": 5})["rows"] == [{"id": 1}, {"id": 2}]


def test_gateway_send_posts_body():
    connector = _gateway(
        {
            "send": {
                "mode": "send",
                "queue": "orders",
                "parameters": ["body"],
                "read_only": False,
                "requires_approval": True,
            }
        }
    )
    calls = []

    def fake(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        return 200, "application/json", b'{"message_id": "abc"}'

    connector.http.request = fake
    result = connector.execute("send", {"body": "hello"})
    assert calls == [("POST", "/queues/orders/messages", {"body": "hello"})]
    assert result == {"status": "sent", "operation": "send", "message_id": "abc"}
