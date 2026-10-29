import pytest

from chusky_bridge.parsers import ParseError, parse_payload
from chusky_bridge.parsers.csv_parser import parse_csv
from chusky_bridge.parsers.fixed_width import parse_fixed_width
from chusky_bridge.parsers.hl7v2 import parse_hl7v2
from chusky_bridge.parsers.x12 import parse_x12
from chusky_bridge.parsers.xml_parser import parse_xml


def test_csv_parses_header_and_rows():
    result = parse_csv(b"id,amount\n1,10.50\n2,7\n")
    assert result["columns"] == ["id", "amount"]
    assert result["records"][1] == {"id": "2", "amount": "7"}


def test_csv_respects_row_cap():
    assert parse_csv(b"a\n1\n2\n3\n", max_rows=2)["record_count"] == 2


def test_csv_rejects_non_utf8():
    with pytest.raises(ParseError):
        parse_csv(b"\xff\xfe\x00bad")


def test_fixed_width_slices_fields():
    layout = [{"name": "acct", "start": 0, "length": 4}, {"name": "amt", "start": 4, "length": 8}]
    result = parse_fixed_width(b"0001  125.00\n0002   99.10\n", layout=layout)
    assert result["records"] == [{"acct": "0001", "amt": "125.00"}, {"acct": "0002", "amt": "99.10"}]


def test_fixed_width_rejects_bad_layout():
    with pytest.raises(ParseError):
        parse_fixed_width(b"x", layout=[{"name": "A-B", "start": 0, "length": 1}])


def test_xml_extracts_records_and_blocks_dtd():
    good = b"<root><row><id>1</id></row><row><id>2</id></row></root>"
    result = parse_xml(good, record_tag="row")
    assert [r["id"] for r in result["records"]] == ["1", "2"]

    entity_bomb = b"<!DOCTYPE x [<!ENTITY a 'boom'>]><root>&a;</root>"
    with pytest.raises(ParseError):
        parse_xml(entity_bomb, record_tag="row")


def _isa():
    values = [
        "00",
        " " * 10,
        "00",
        " " * 10,
        "ZZ",
        "SENDER".ljust(15),
        "ZZ",
        "RECEIVER".ljust(15),
        "260101",
        "1200",
        "^",
        "00501",
        "000000001",
        "0",
        "T",
        ":",
    ]
    return "ISA*" + "*".join(values) + "~"


def test_x12_parses_fixed_header_delimiters():
    isa = _isa()
    assert len(isa) == 106
    text = isa + "GS*HC*SENDER*RECEIVER*20260101*1200*1*X*005010X222A1~ST*837*0001~SE*2*0001~GE*1*1~IEA*1*000000001~"
    result = parse_x12(text.encode("ascii"))
    assert result["transaction_set_count"] == 1
    assert result["segments"][0]["id"] == "ISA"


def test_x12_rejects_non_interchange():
    with pytest.raises(ParseError):
        parse_x12(b"not an x12 file")


def test_hl7_reads_message_type_and_segments():
    msg = "MSH|^~\\&|APP|FAC|RCV|FAC2|20260101120000||ADT^A01|MSG0001|P|2.5\rPID|1||12345^^^HOSP^MR||DOE^JOHN\r"
    result = parse_hl7v2(msg.encode("utf-8"))
    assert result["message_type"] == "ADT^A01"
    assert [s["id"] for s in result["segments"]] == ["MSH", "PID"]


def test_hl7_rejects_missing_msh():
    with pytest.raises(ParseError):
        parse_hl7v2(b"PID|1||x")


def test_dispatch_routes_formats():
    result = parse_payload("csv", b"a,b\n1,2\n", options={"delimiter": ","}, max_rows=10)
    assert result["format"] == "csv"
    with pytest.raises(ParseError):
        parse_payload("cobol", b"", options={}, max_rows=1)
