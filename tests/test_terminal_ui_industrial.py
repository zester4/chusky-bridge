import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.dicom import DicomConnector
from chusky_bridge.connectors.modbus import ModbusConnector
from chusky_bridge.connectors.opcua import OpcUaConnector
from chusky_bridge.connectors.rpa import RpaConnector
from chusky_bridge.connectors.tn3270 import Tn3270Connector

FIELDS = {
    "userid": {"row": 2, "col": 20, "length": 8},
    "password": {"row": 3, "col": 20, "length": 8},
    "custid": {"row": 6, "col": 20, "length": 10},
    "name": {"row": 8, "col": 20, "length": 20},
}
STEPS = [
    {"action": "fill", "field": "userid", "source": "username"},
    {"action": "fill", "field": "password", "source": "secret"},
    {"action": "press", "aid": "ENTER"},
    {"action": "expect", "text": "MAIN MENU"},
    {"action": "fill", "field": "custid", "source": "parameter", "parameter": "customer_id"},
    {"action": "press", "aid": "ENTER"},
    {"action": "read", "field": "name", "as": "customer_name"},
]
TN_CONNECTION = {
    "host": "cics.example.internal",
    "port": 23,
    "tls": True,
    "username": "OPER1",
    "password": "s3cret",
    "fields": FIELDS,
}


class FakeTerminal:
    def __init__(self):
        self.filled = []
        self.keys = []
        self.screen = "MAIN MENU  ENTER PF3"

    def connect(self, host, port, tls):
        self.connected = (host, port, tls)

    def fill(self, row, col, text):
        self.filled.append((row, col, text))

    def press(self, aid):
        self.keys.append(aid)
        if aid == "ENTER" and len(self.keys) == 2:
            self.screen = "CUSTOMER DETAIL"

    def read(self, row, col, length):
        return "JANE DOE            "

    def screen_text(self):
        return self.screen

    def close(self):
        self.closed = True


def _tn(op_steps=STEPS, params=("customer_id",), **overrides):
    op = {"mode": "transaction", "steps": op_steps, "parameters": list(params), "read_only": True}
    conn = {**TN_CONNECTION, **overrides}
    return conn, op


def test_transaction_fills_reads_and_hides_secret():
    terminal = FakeTerminal()
    conn, op = _tn()
    connector = Tn3270Connector({**conn, "operations": {"lookup": op}}, driver_factory=lambda: terminal)
    result = connector.execute("lookup", {"customer_id": "1001"})
    assert result["outputs"] == {"customer_name": "JANE DOE"}
    assert (3, 20, "s3cret") in terminal.filled
    assert "s3cret" not in str(result)
    assert terminal.closed is True


def test_missing_expected_screen_fails():
    terminal = FakeTerminal()
    terminal.screen = "LOGIN"
    conn, op = _tn()
    connector = Tn3270Connector({**conn, "operations": {"lookup": op}}, driver_factory=lambda: terminal)
    with pytest.raises(ConnectorError, match="expected screen"):
        connector.execute("lookup", {"customer_id": "1001"})


def test_value_longer_than_field_rejected():
    terminal = FakeTerminal()
    conn, op = _tn()
    connector = Tn3270Connector({**conn, "operations": {"lookup": op}}, driver_factory=lambda: terminal)
    with pytest.raises(ConnectorError, match="too long"):
        connector.execute("lookup", {"customer_id": "12345678901"})


def test_unlisted_aid_key_rejected_at_registration():
    conn, _ = _tn()
    bad = [{"action": "press", "aid": "PF99"}]
    with pytest.raises(ConnectorError, match="not allowed"):
        Tn3270Connector.validate_operation(
            "x", {"mode": "transaction", "steps": bad, "parameters": [], "read_only": True}, conn
        )


def test_plaintext_terminal_refused_at_registration():
    conn, op = _tn(tls=False)
    with pytest.raises(ConnectorError, match="TLS"):
        Tn3270Connector.validate_operation("x", op, conn)


def test_unused_parameter_rejected():
    conn, op = _tn(params=("customer_id", "extra"))
    with pytest.raises(ConnectorError, match="never used"):
        Tn3270Connector.validate_operation("x", op, conn)


UI_CONNECTION = {
    "application": "Order Desk*",
    "selectors": {
        "search_box": {"control_type": "Edit", "auto_id": "txtSearch"},
        "status_label": {"control_type": "Text", "auto_id": "lblStatus"},
    },
}


def test_read_only_flow_cannot_click_or_type():
    op = {"steps": [{"action": "click", "selector": "search_box"}], "parameters": [], "read_only": True}
    with pytest.raises(ConnectorError, match="read_only"):
        RpaConnector.validate_operation("x", op, UI_CONNECTION)


def test_write_flow_types_declared_parameter():
    op = {
        "steps": [
            {"action": "type", "selector": "search_box", "parameter": "order_no"},
            {"action": "click", "selector": "search_box"},
        ],
        "parameters": ["order_no"],
        "read_only": False,
        "requires_approval": True,
    }
    RpaConnector.validate_operation("x", op, UI_CONNECTION)


class FakeUi:
    def attach(self, pattern):
        self.attached = pattern

    def find(self, selector):
        return selector["auto_id"]

    def click(self, element):
        pass

    def type_text(self, element, text):
        self.typed = (element, text)

    def text(self, element):
        return "Shipped"

    def close(self):
        self.closed = True


def test_rpa_reads_status_label():
    op = {
        "steps": [
            {"action": "read", "selector": "status_label", "as": "status"},
            {"action": "expect", "selector": "status_label", "text": "Ship"},
        ],
        "parameters": [],
        "read_only": True,
    }
    ui = FakeUi()
    connector = RpaConnector({**UI_CONNECTION, "operations": {"status": op}}, driver_factory=lambda: ui)
    assert connector.execute("status", {})["outputs"] == {"status": "Shipped"}
    assert ui.attached == "Order Desk*"


def test_rpa_selector_must_be_defined():
    op = {"steps": [{"action": "read", "selector": "unknown", "as": "x"}], "parameters": [], "read_only": True}
    with pytest.raises(ConnectorError, match="undefined selector"):
        RpaConnector.validate_operation("x", op, UI_CONNECTION)


OPC_CONNECTION = {
    "endpoint": "opc.tcp://plc.example.internal:4840",
    "security_policy": "Basic256Sha256",
    "security_mode": "SignAndEncrypt",
    "client_cert_path": "client.der",
    "client_key_path": "client.pem",
}
OPC_OP = {"mode": "read", "nodes": {"temperature": "ns=2;s=Line1.Temp"}, "parameters": [], "read_only": True}


def test_opcua_refuses_unsecured_sessions():
    with pytest.raises(ConnectorError, match="secure policies"):
        OpcUaConnector.validate_operation("x", OPC_OP, {**OPC_CONNECTION, "security_policy": "None"})


def test_opcua_writes_not_supported():
    with pytest.raises(ConnectorError):
        OpcUaConnector.validate_operation("x", {**OPC_OP, "read_only": False, "mode": "write"}, OPC_CONNECTION)


def test_opcua_reads_fixed_nodes_only():
    class Node:
        def get_data_value(self):
            return SimpleNamespace(Value=SimpleNamespace(Value=72.5), SourceTimestamp=datetime(2026, 1, 1, tzinfo=UTC))

    class Client:
        def connect(self):
            self.up = True

        def get_node(self, node_id):
            assert node_id == "ns=2;s=Line1.Temp"
            return Node()

        def disconnect(self):
            self.down = True

    connector = OpcUaConnector({**OPC_CONNECTION, "operations": {"read": OPC_OP}}, client_factory=lambda cfg: Client())
    result = connector.execute("read", {})
    assert result["values"]["temperature"]["value"] == 72.5


def _fake_dicom(statuses):
    pynetdicom = types.ModuleType("pynetdicom")
    sop = types.ModuleType("pynetdicom.sop_class")
    pydicom = types.ModuleType("pydicom")
    dataset = types.ModuleType("pydicom.dataset")

    class Dataset:
        pass

    class Assoc:
        is_established = True

        def send_c_find(self, query, query_model):
            for status, identifier in statuses:
                yield SimpleNamespace(Status=status), identifier

        def release(self):
            self.released = True

    class AE:
        def __init__(self, ae_title):
            self.ae_title = ae_title

        def add_requested_context(self, context):
            pass

        def associate(self, host, port, ae_title):
            return Assoc()

    pynetdicom.AE = AE
    sop.StudyRootQueryRetrieveInformationModelFind = object()
    dataset.Dataset = Dataset
    pydicom.dataset = dataset
    return {"pynetdicom": pynetdicom, "pynetdicom.sop_class": sop, "pydicom": pydicom, "pydicom.dataset": dataset}


DICOM_CONNECTION = {
    "ae_title": "CHUSKY",
    "peer_ae_title": "PACS1",
    "host": "pacs.example.internal",
    "port": 11112,
    "allowed_hosts": ["pacs.example.internal"],
}
DICOM_OP = {
    "mode": "find",
    "query_keys": {"accession": "AccessionNumber"},
    "return_keys": ["StudyInstanceUID", "StudyDate"],
    "parameters": ["accession"],
    "read_only": True,
}


def test_dicom_find_returns_pending_matches(monkeypatch):
    identifier = SimpleNamespace(StudyInstanceUID="1.2.3", StudyDate="20260101")
    for name, module in _fake_dicom([(0xFF00, identifier), (0x0000, None)]).items():
        monkeypatch.setitem(sys.modules, name, module)
    connector = DicomConnector({**DICOM_CONNECTION, "operations": {"find": DICOM_OP}, "max_rows": 10})
    result = connector.execute("find", {"accession": "A-1"})
    assert result["rows"] == [{"StudyInstanceUID": "1.2.3", "StudyDate": "20260101"}]


def test_dicom_failure_status_raises(monkeypatch):
    for name, module in _fake_dicom([(0xC000, None)]).items():
        monkeypatch.setitem(sys.modules, name, module)
    connector = DicomConnector({**DICOM_CONNECTION, "operations": {"find": DICOM_OP}})
    with pytest.raises(ConnectorError, match="0xC000"):
        connector.execute("find", {"accession": "A-1"})


def test_dicom_keyword_allowlist():
    bad = {**DICOM_OP, "query_keys": {"accession": "PixelData"}}
    with pytest.raises(ConnectorError, match="allowlist"):
        DicomConnector.validate_operation("find", bad, DICOM_CONNECTION)


def test_dicom_host_must_be_allowlisted():
    with pytest.raises(ConnectorError, match="allowed_hosts"):
        DicomConnector.validate_operation("find", DICOM_OP, {**DICOM_CONNECTION, "allowed_hosts": []})


MODBUS_OP = {
    "mode": "read_registers",
    "address": 100,
    "count": 2,
    "unit": 1,
    "scale": 0.1,
    "parameters": [],
    "read_only": True,
}


def test_modbus_reads_and_scales_registers():
    class Response:
        registers = [100, 205]

        def isError(self):
            return False

    class Client:
        def connect(self):
            return True

        def read_holding_registers(self, address, count, slave):
            assert (address, count, slave) == (100, 2, 1)
            return Response()

        def close(self):
            self.closed = True

    connector = ModbusConnector({"host": "plc", "operations": {"read": MODBUS_OP}}, client_factory=lambda cfg: Client())
    result = connector.execute("read", {})
    assert result["raw"] == [100, 205]
    assert result["values"] == [10.0, 20.5]


def test_modbus_write_refused():
    with pytest.raises(ConnectorError):
        ModbusConnector.validate_operation(
            "w", {**MODBUS_OP, "mode": "write_registers", "read_only": False}, {"host": "plc"}
        )


def test_modbus_count_bounded():
    with pytest.raises(ConnectorError, match="count"):
        ModbusConnector.validate_operation("r", {**MODBUS_OP, "count": 500}, {"host": "plc"})
