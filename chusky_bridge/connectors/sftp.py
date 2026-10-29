import base64
import fnmatch
import hashlib
import hmac
import posixpath
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments
from chusky_bridge.parsers import FORMATS, ParseError, parse_payload, validate_layout

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,199}$")
_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_.\-*?]{1,120}$")
_SAFE_DIRECTORY = re.compile(r"^[A-Za-z0-9_\-/]*$")


def fingerprint_sha256(host_key: bytes) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(host_key).digest()).decode().rstrip("=")


def host_key_matches(host_key: bytes, pinned: str) -> bool:
    """Constant-time comparison against the pinned fingerprint. Trust-on-first-use is not allowed."""
    expected = pinned if pinned.startswith("SHA256:") else "SHA256:" + pinned
    return hmac.compare_digest(fingerprint_sha256(host_key).rstrip("="), expected.rstrip("="))


class SftpConnector(BaseConnector):
    """SFTP adapter for batch files: billing, ACH/NACHA, EDI, HL7 and X12 exports, CSV and fixed-width
    feeds from mainframes and midrange systems. It lists and reads files under one pinned root
    and parses them into records. It cannot write or delete."""

    connector_type = "sftp"
    secret_field = "password"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        root = str(config.get("root_directory") or "")
        if not root.startswith("/") or ".." in root.split("/"):
            raise ConnectorError("root_directory must be an absolute path without '..'")
        self._root = root.rstrip("/") or "/"
        if not config.get("host_key_sha256"):
            raise ConnectorError("host_key_sha256 must be pinned")

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        params = op.get("parameters", [])
        mode = op.get("mode")
        directory = str(op.get("directory") or "")
        if not _SAFE_DIRECTORY.match(directory) or ".." in directory:
            raise ConnectorError(f"{name}: directory must be relative and must not contain '..'")
        if mode == "list_files":
            if params not in ([], ["pattern"]):
                raise ConnectorError(f"{name}: list_files takes at most the parameter pattern")
        elif mode == "read_file":
            if params != ["filename"]:
                raise ConnectorError(f"{name}: read_file takes exactly the parameter filename")
            fmt = op.get("format")
            if fmt not in FORMATS:
                raise ConnectorError(f"{name}: format must be one of {sorted(FORMATS)}")
            try:
                if fmt == "fixed_width":
                    validate_layout(op.get("layout"))
            except ParseError as exc:
                raise ConnectorError(f"{name}: {exc}") from exc
            if fmt == "xml" and not op.get("record_tag"):
                raise ConnectorError(f"{name}: xml format needs record_tag")
        else:
            raise ConnectorError(f"{name}: sftp mode must be 'list_files' or 'read_file'")
        if not connection.get("host_key_sha256"):
            raise ConnectorError(f"{name}: connection must pin host_key_sha256")

    def _safe_join(self, directory: str, filename: str | None = None) -> str:
        parts = [self._root] + ([directory] if directory else []) + ([filename] if filename else [])
        path = posixpath.normpath(posixpath.join(*parts))
        if path != self._root and not path.startswith(self._root.rstrip("/") + "/"):
            raise ConnectorError("path escapes the approved root directory")
        return path

    @contextmanager
    def _sftp(self) -> Iterator[Any]:
        import paramiko

        transport = None
        try:
            transport = paramiko.Transport((self.config["host"], int(self.config.get("port", 22))))
            transport.start_client(timeout=int(self.config.get("timeout_seconds", 10)))
            host_key = transport.get_remote_server_key()
            if not host_key_matches(host_key.asbytes(), self.config["host_key_sha256"]):
                raise ConnectorError("SFTP host key does not match the pinned fingerprint")
            if not self.config.get("password"):
                raise ConnectorError("SFTP credentials are not configured")
            transport.auth_password(self.config["username"], self.config["password"])
            if not transport.is_authenticated():
                raise ConnectorError("SFTP authentication failed")
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                yield sftp
            finally:
                sftp.close()
        except ConnectorError:
            raise
        except (OSError, paramiko.SSHException) as exc:
            raise ConnectorError("SFTP session failed") from exc
        finally:
            if transport is not None:
                transport.close()

    def health_check(self) -> dict[str, Any]:
        with self._sftp() as sftp:
            sftp.listdir(self._root)
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        directory = str(op.get("directory") or "")
        if op["mode"] == "list_files":
            return self._list(operation, op, arguments, directory)
        return self._read(operation, op, arguments, directory)

    def _list(self, operation: str, op: dict[str, Any], arguments: dict[str, Any], directory: str) -> dict[str, Any]:
        pattern = arguments.get("pattern", "*")
        if not _SAFE_PATTERN.match(str(pattern)):
            raise ConnectorError("invalid file pattern")
        path = self._safe_join(directory)
        with self._sftp() as sftp:
            try:
                entries = sftp.listdir_attr(path)
            except OSError as exc:
                raise ConnectorError("directory not found") from exc
        rows = sorted(
            (
                {"name": e.filename, "size": e.st_size, "modified": e.st_mtime}
                for e in entries
                if not e.filename.startswith(".") and fnmatch.fnmatchcase(e.filename, pattern)
            ),
            key=lambda row: row["name"],
        )[: self.max_rows]
        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}

    def _read(self, operation: str, op: dict[str, Any], arguments: dict[str, Any], directory: str) -> dict[str, Any]:
        require_arguments(["filename"], arguments)
        filename = str(arguments["filename"])
        if not _SAFE_FILENAME.match(filename):
            raise ConnectorError("invalid filename")
        path = self._safe_join(directory, filename)
        max_bytes = int(self.config.get("max_file_bytes", 5_000_000))

        with self._sftp() as sftp:
            try:
                size = sftp.stat(path).st_size
            except OSError as exc:
                raise ConnectorError("file not found") from exc
            if size is not None and size > max_bytes:
                raise ConnectorError("file exceeds the size limit")
            with sftp.open(path, "rb") as handle:
                data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ConnectorError("file exceeds the size limit")

        options = {
            "delimiter": op.get("delimiter", ","),
            "layout": op.get("layout"),
            "record_tag": op.get("record_tag"),
        }
        try:
            parsed = parse_payload(op["format"], data, options=options, max_rows=self.max_rows)
        except ParseError as exc:
            raise ConnectorError(f"file could not be parsed as {op['format']}: {exc}") from exc
        return {"status": "success", "operation": operation, "file": filename, **parsed}
