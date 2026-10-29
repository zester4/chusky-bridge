from types import SimpleNamespace

import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.soap import check_service_hosts, endpoint_addresses, resolve_wsdl_path


def test_wsdl_must_live_in_approved_directory(tmp_path):
    approved = tmp_path / "wsdl"
    approved.mkdir()
    (approved / "svc.wsdl").write_text("<definitions/>")
    assert resolve_wsdl_path("svc.wsdl", str(approved)).name == "svc.wsdl"
    with pytest.raises(ConnectorError):
        resolve_wsdl_path("../etc/passwd", str(approved))
    with pytest.raises(ConnectorError):
        resolve_wsdl_path("/etc/passwd", str(approved))


def test_endpoint_hosts_must_be_allowlisted():
    with pytest.raises(ConnectorError, match="allowlist"):
        check_service_hosts(["https://evil.example.com/svc"], {"ps.example.internal"})


def test_allowlisted_endpoint_passes():
    check_service_hosts(["https://ps.example.internal/svc"], {"ps.example.internal"})


def test_endpoint_addresses_read_from_wsdl_structure():
    port = SimpleNamespace(binding_options={"address": "https://ps.example.internal/svc"})
    service = SimpleNamespace(ports={"p": port})
    client = SimpleNamespace(wsdl=SimpleNamespace(services={"s": service}))
    assert endpoint_addresses(client) == ["https://ps.example.internal/svc"]
