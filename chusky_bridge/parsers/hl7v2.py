import re
from typing import Any

from chusky_bridge.parsers.errors import ParseError

_SPLIT = re.compile(r"\r\n|\r|\n")


def parse_hl7v2(data: bytes, *, max_segments: int = 5000) -> dict[str, Any]:
    """Parse one HL7 v2 message. MSH-9 (message type, e.g. ADT^A01) is returned for routing."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("HL7 v2 message must be UTF-8") from exc

    lines = [line for line in _SPLIT.split(text) if line.strip()]
    if not lines or not lines[0].startswith("MSH"):
        raise ParseError("not an HL7 v2 message (missing MSH segment)")

    field_sep = lines[0][3]
    segments: list[dict[str, Any]] = []
    for line in lines[:max_segments]:
        fields = line.split(field_sep)
        segments.append({"id": fields[0], "fields": fields[1:]})

    # For MSH, split()[1] is MSH-2 (encoding characters), so MSH-9 is index 8.
    msh = lines[0].split(field_sep)
    message_type = msh[8] if len(msh) > 8 else None
    return {
        "format": "hl7v2",
        "message_type": message_type,
        "segment_count": len(segments),
        "segments": segments,
    }
