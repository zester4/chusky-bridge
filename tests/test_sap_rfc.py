from contextlib import contextmanager

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.sap_rfc import SapRfcConnector

CONNECTION = {"ashost": "sap.example", "sysnr": "00", "client": "100", "user": "SVC"}


def _op(**overrides):
    op = {
        "mode": "rfc",
        "function_module": "BAPI_MATERIAL_GET_DETAIL",
        "parameters": ["material"],
        "rfc_names": {"material": "MATERIAL"},
        "read_only": True,
    }
    op.update(overrides)
    return op


class FakeRfc:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, fm, **kwargs):
        self.calls.append((fm, kwargs))
        result = self.responses.get(fm, {})
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        pass


def _connector(monkeypatch, fake, op):
    @contextmanager
    def fake_connect(self):
        yield fake

    monkeypatch.setattr(SapRfcConnector, "_connect", fake_connect)
    return SapRfcConnector({"operations": {"op": op}, "max_rows": 5})


def test_write_without_approval_rejected():
    with pytest.raises(ConnectorError, match="requires_approval"):
        SapRfcConnector.validate_operation("create", _op(read_only=False, requires_approval=False), CONNECTION)


def test_write_with_approval_validates():
    SapRfcConnector.validate_operation(
        "create",
        _op(read_only=False, requires_approval=True, function_module="BAPI_SALESORDER_CREATEFROMDAT2"),
        CONNECTION,
    )


def test_function_module_name_must_be_sap_style():
    with pytest.raises(ConnectorError):
        SapRfcConnector.validate_operation("x", _op(function_module="drop; table"), CONNECTION)


def test_connection_needs_identity_fields():
    with pytest.raises(ConnectorError, match="needs"):
        SapRfcConnector.validate_operation("x", _op(), {"ashost": "a"})


def test_read_maps_argument_to_rfc_name(monkeypatch):
    fake = FakeRfc({"BAPI_MATERIAL_GET_DETAIL": {"MATERIAL_GENERAL_DATA": [{"MATERIAL": "M-1"}]}})
    result = _connector(monkeypatch, fake, _op()).execute("op", {"material": "M-1"})
    assert fake.calls == [("BAPI_MATERIAL_GET_DETAIL", {"MATERIAL": "M-1"})]
    assert result["status"] == "success"
    assert result["result"]["MATERIAL_GENERAL_DATA"] == [{"MATERIAL": "M-1"}]


def test_write_commits_when_return_has_no_errors(monkeypatch):
    op = _op(read_only=False, requires_approval=True, function_module="BAPI_CREATE")
    fake = FakeRfc({"BAPI_CREATE": {"RETURN": [{"TYPE": "S", "MESSAGE": "created"}]}, "BAPI_TRANSACTION_COMMIT": {}})
    result = _connector(monkeypatch, fake, op).execute("op", {"material": "M-1"})
    assert ("BAPI_TRANSACTION_COMMIT", {"WAIT": "X"}) in fake.calls
    assert result["status"] == "committed"


def test_write_rolls_back_on_business_error(monkeypatch):
    op = _op(read_only=False, requires_approval=True, function_module="BAPI_CREATE")
    fake = FakeRfc({"BAPI_CREATE": {"RETURN": [{"TYPE": "E", "MESSAGE": "credit limit exceeded"}]}})
    with pytest.raises(ConnectorError, match="nothing was committed"):
        _connector(monkeypatch, fake, op).execute("op", {"material": "M-1"})
    names = [name for name, _ in fake.calls]
    assert "BAPI_TRANSACTION_ROLLBACK" in names
    assert "BAPI_TRANSACTION_COMMIT" not in names


def test_commit_failure_rolls_back(monkeypatch):
    op = _op(read_only=False, requires_approval=True, function_module="BAPI_CREATE")
    fake = FakeRfc({"BAPI_CREATE": {"RETURN": []}, "BAPI_TRANSACTION_COMMIT": RuntimeError("boom")})
    with pytest.raises(ConnectorError, match="rolled back"):
        _connector(monkeypatch, fake, op).execute("op", {"material": "M-1"})
    assert "BAPI_TRANSACTION_ROLLBACK" in [name for name, _ in fake.calls]
