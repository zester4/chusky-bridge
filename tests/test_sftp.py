import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.sftp import SftpConnector, fingerprint_sha256, host_key_matches

KEY = b"fake-host-key-bytes"


def _connector(**overrides):
    config = {
        "host": "sftp.example.internal",
        "username": "svc",
        "root_directory": "/outbound/billing",
        "host_key_sha256": fingerprint_sha256(KEY),
        "operations": {},
    }
    config.update(overrides)
    return SftpConnector(config)


def test_host_key_matches_pinned_fingerprint():
    assert host_key_matches(KEY, fingerprint_sha256(KEY))


def test_host_key_mismatch_detected():
    assert not host_key_matches(b"attacker-key", fingerprint_sha256(KEY))


def test_fingerprint_accepts_unprefixed_pin():
    assert host_key_matches(KEY, fingerprint_sha256(KEY).removeprefix("SHA256:"))


def test_unpinned_connector_refused():
    with pytest.raises(ConnectorError, match="pinned"):
        _connector(host_key_sha256="")


def test_root_traversal_refused():
    with pytest.raises(ConnectorError):
        _connector(root_directory="/outbound/../etc")


def test_path_cannot_escape_root():
    connector = _connector()
    with pytest.raises(ConnectorError, match="escapes"):
        connector._safe_join("../../etc", "passwd")


def test_join_stays_under_root():
    assert _connector()._safe_join("", "batch.csv") == "/outbound/billing/batch.csv"


def test_read_file_requires_known_format():
    with pytest.raises(ConnectorError, match="format"):
        SftpConnector.validate_operation(
            "op",
            {"mode": "read_file", "format": "pdf", "parameters": ["filename"], "directory": ""},
            {"host_key_sha256": "SHA256:x"},
        )


def test_list_files_takes_only_pattern():
    with pytest.raises(ConnectorError):
        SftpConnector.validate_operation(
            "op", {"mode": "list_files", "parameters": ["path"], "directory": ""}, {"host_key_sha256": "SHA256:x"}
        )
