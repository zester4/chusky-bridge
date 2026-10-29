from typing import Any

from defusedxml import ElementTree

from chusky_bridge.parsers.errors import ParseError


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml(data: bytes, *, record_tag: str, max_records: int = 1000) -> dict[str, Any]:
    """Parse with defusedxml, which rejects DTDs, entity expansion, and external entities."""
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:  # defusedxml raises several distinct error types
        raise ParseError("XML could not be parsed safely") from exc

    records: list[dict[str, str]] = []
    for element in root.iter():
        if _local(element.tag) != record_tag:
            continue
        if len(records) >= max_records:
            break
        records.append({_local(child.tag): (child.text or "").strip() for child in element})

    return {"format": "xml", "record_tag": record_tag, "record_count": len(records), "records": records}
