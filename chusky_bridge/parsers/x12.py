from typing import Any

from chusky_bridge.parsers.errors import ParseError


def parse_x12(data: bytes, *, max_segments: int = 5000) -> dict[str, Any]:
    """Parse an ASCII X12 interchange. The fixed-width ISA header declares the delimiters."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ParseError("X12 must be ASCII") from exc
    if not text.startswith("ISA") or len(text) < 106:
        raise ParseError("not an X12 interchange (missing ISA header)")

    element_sep = text[3]
    segment_term = text[105]
    segments: list[dict[str, Any]] = []
    for raw in text.split(segment_term):
        raw = raw.strip()
        if not raw:
            continue
        if len(segments) >= max_segments:
            break
        parts = raw.split(element_sep)
        segments.append({"id": parts[0], "elements": parts[1:]})

    return {
        "format": "x12",
        "segment_count": len(segments),
        "transaction_set_count": sum(1 for s in segments if s["id"] == "ST"),
        "segments": segments,
    }
