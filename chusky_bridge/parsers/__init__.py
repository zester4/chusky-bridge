from typing import Any

from chusky_bridge.parsers.csv_parser import parse_csv
from chusky_bridge.parsers.errors import ParseError
from chusky_bridge.parsers.fixed_width import parse_fixed_width, validate_layout
from chusky_bridge.parsers.hl7v2 import parse_hl7v2
from chusky_bridge.parsers.x12 import parse_x12
from chusky_bridge.parsers.xml_parser import parse_xml

FORMATS = frozenset({"csv", "fixed_width", "xml", "x12", "hl7v2"})


def parse_payload(fmt: str, data: bytes, *, options: dict[str, Any], max_rows: int) -> dict[str, Any]:
    if fmt == "csv":
        return parse_csv(data, delimiter=options.get("delimiter", ","), max_rows=max_rows)
    if fmt == "fixed_width":
        return parse_fixed_width(data, layout=options["layout"], max_rows=max_rows)
    if fmt == "xml":
        return parse_xml(data, record_tag=options["record_tag"], max_records=max_rows)
    if fmt == "x12":
        return parse_x12(data, max_segments=max_rows * 10)
    if fmt == "hl7v2":
        return parse_hl7v2(data, max_segments=max_rows * 10)
    raise ParseError("unsupported format")


__all__ = [
    "FORMATS",
    "ParseError",
    "parse_csv",
    "parse_fixed_width",
    "parse_hl7v2",
    "parse_payload",
    "parse_x12",
    "parse_xml",
    "validate_layout",
]
