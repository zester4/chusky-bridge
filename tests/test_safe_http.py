import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.safe_http import HttpOrigin, assert_public_host, encode_segment


def test_loopback_host_blocked():
    with pytest.raises(ConnectorError, match="non-public"):
        assert_public_host("127.0.0.1", allow_private=False)


def test_private_range_blocked():
    with pytest.raises(ConnectorError):
        assert_public_host("10.0.0.5", allow_private=False)


def test_private_allowed_only_when_explicit():
    assert_public_host("10.0.0.5", allow_private=True)


def test_http_base_url_rejected():
    with pytest.raises(ConnectorError, match="https"):
        HttpOrigin("http://example.com", headers={})


def test_path_segment_is_encoded():
    assert encode_segment("a/b c") == "a%2Fb%20c"


@pytest.mark.parametrize("value", ["..", ".", ""])
def test_traversal_segments_rejected(value):
    with pytest.raises(ConnectorError):
        encode_segment(value)
