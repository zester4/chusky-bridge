"""HL7 v2 over MLLP. Sends one query message and reads the reply.

Only allowlisted query message types can be sent (QBP^Q22 and QRY^A19). Agents cannot supply raw
HL7. They supply values, which are escaped per HL7 rules, and the segment template comes from the
manifest. Segments are limited to MSH, QPD, and RCP. TLS is required unless allow_plaintext is set."""

import re
import socket
import ssl
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments
from chusky_bridge.files import FileNotApproved, resolve_approved_file
from chusky_bridge.parsers import ParseError, parse_hl7v2

START = b"\x0b"
END = b"\x1c\x0d"
ALLOWED_SEGMENTS = frozenset({"MSH", "QPD", "RCP"})
ALLOWED_MESSAGE_TYPES = frozenset({"QBP^Q22", "QRY^A19"})
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,62})\}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_VALUE_CHARS = 200


def frame(message: bytes) -> bytes:
    return START + message + END


def unframe(buffer: bytes) -> bytes | None:
    if not buffer.startswith(START):
        raise ConnectorError("reply is not MLLP framed")
    end = buffer.find(END)
    if end < 0:
        return None
    return buffer[1:end]


def hl7_escape(value: str) -> str:
    """Escape HL7 delimiters so a value can never add fields, components, or segments."""
    return (
        value.replace("\\", "\\E\\")
        .replace("|", "\\F\\")
        .replace("^", "\\S\\")
        .replace("&", "\\T\\")
        .replace("~", "\\R\\")
    )


def build_message(template: str, arguments: dict[str, Any]) -> bytes:
    def substitute(match: re.Match) -> str:
        value = str(arguments[match.group(1)])
        if _CONTROL.search(value) or len(value) > MAX_VALUE_CHARS:
            raise ConnectorError("value contains control characters or is too long")
        return hl7_escape(value)

    return _PLACEHOLDER.sub(substitute, template).encode("utf-8")


class MllpConnector(BaseConnector):
    connector_type = "mllp"
    secret_field = None

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._timeout = float(config.get("timeout_seconds", 10))
        self._max_bytes = int(config.get("max_response_bytes", 100_000))

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "query" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: mllp operations must be mode 'query' and read_only")
        template = str(op.get("template") or "")
        lines = [line for line in re.split(r"\r", template) if line]
        if not lines:
            raise ConnectorError(f"{name}: a template is required")
        for line in lines:
            segment_id = line.split("|", 1)[0]
            if segment_id not in ALLOWED_SEGMENTS:
                raise ConnectorError(f"{name}: segment {segment_id!r} is not allowed")
        msh = lines[0].split("|")
        message_type = msh[8] if len(msh) > 8 else ""
        if message_type not in ALLOWED_MESSAGE_TYPES:
            raise ConnectorError(f"{name}: MSH-9 must be one of {sorted(ALLOWED_MESSAGE_TYPES)}")
        placeholders = set(_PLACEHOLDER.findall(template))
        params = set(op.get("parameters", []))
        if placeholders != params:
            raise ConnectorError(f"{name}: template placeholders must match declared parameters")
        if not connection.get("host"):
            raise ConnectorError(f"{name}: connection needs host")
        if connection.get("tls") is False and connection.get("allow_plaintext") is not True:
            raise ConnectorError(f"{name}: plaintext MLLP requires allow_plaintext: true")

    def _tls_context(self) -> ssl.SSLContext | None:
        if self.config.get("tls", True) is False:
            return None
        context = ssl.create_default_context()
        if self.config.get("ca_bundle_path"):
            try:
                from chusky_bridge.config import settings

                context.load_verify_locations(resolve_approved_file(self.config["ca_bundle_path"], settings.cert_dir))
            except (FileNotApproved, OSError) as exc:
                raise ConnectorError("CA bundle is not available in the approved directory") from exc
        return context

    def _exchange(self, message: bytes) -> bytes:
        host, port = self.config["host"], int(self.config.get("port", 2575))
        context = self._tls_context()
        try:
            raw = socket.create_connection((host, port), timeout=self._timeout)
            sock = context.wrap_socket(raw, server_hostname=host) if context else raw
        except OSError as exc:
            raise ConnectorError("MLLP connection failed") from exc
        buffer = b""
        try:
            sock.sendall(frame(message))
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > self._max_bytes:
                    raise ConnectorError("MLLP reply exceeded size limit")
                if buffer.find(END) >= 0:
                    break
        except OSError as exc:
            raise ConnectorError("MLLP exchange failed") from exc
        finally:
            sock.close()
        return buffer

    def health_check(self) -> dict[str, Any]:
        self._exchange(b"MSH|^~\\&|CHUSKY|CHUSKY|RCV|RCV|20000101000000||QBP^Q22|HC0|P|2.5")
        return {"status": "reachable"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        message = build_message(str(op["template"]), arguments)
        reply = self._exchange(message)
        payload = unframe(reply)
        if payload is None:
            raise ConnectorError("MLLP reply was incomplete")
        try:
            parsed = parse_hl7v2(payload, max_segments=self.max_rows)
        except ParseError as exc:
            raise ConnectorError(f"reply could not be parsed: {exc}") from exc
        ack = next((s for s in parsed["segments"] if s["id"] == "MSA"), None)
        return {
            "status": "success",
            "operation": operation,
            "message_type": parsed["message_type"],
            "ack_code": ack["fields"][0] if ack and ack["fields"] else None,
            "segment_count": parsed["segment_count"],
            "segments": parsed["segments"],
        }
