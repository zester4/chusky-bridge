import re
from typing import Any

from chusky_bridge.parsers.errors import ParseError

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def validate_layout(layout: Any) -> list[dict[str, Any]]:
    if not isinstance(layout, list) or not layout:
        raise ParseError("fixed_width requires a non-empty layout")
    seen: set[str] = set()
    for field in layout:
        if not isinstance(field, dict):
            raise ParseError("each layout entry must be a mapping")
        name, start, length = field.get("name"), field.get("start"), field.get("length")
        if not isinstance(name, str) or not _NAME.match(name) or name in seen:
            raise ParseError(f"invalid or duplicate layout field name: {name!r}")
        if not isinstance(start, int) or start < 0:
            raise ParseError(f"layout field {name} needs a non-negative integer start")
        if not isinstance(length, int) or length <= 0:
            raise ParseError(f"layout field {name} needs a positive integer length")
        seen.add(name)
    return layout


def parse_fixed_width(data: bytes, *, layout: Any, max_rows: int = 1000) -> dict[str, Any]:
    fields = validate_layout(layout)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("file is not valid UTF-8") from exc

    records: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(records) >= max_rows:
            break
        records.append({f["name"]: line[f["start"] : f["start"] + f["length"]].strip() for f in fields})
    return {
        "format": "fixed_width",
        "columns": [f["name"] for f in fields],
        "record_count": len(records),
        "records": records,
    }
