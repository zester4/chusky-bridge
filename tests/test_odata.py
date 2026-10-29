import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.odata import ODataConnector, build_filter, normalize_odata, odata_literal


def test_string_literal_escapes_quotes():
    assert odata_literal("O'Brien") == "'O''Brien'"


def test_injection_attempt_stays_inside_literal():
    literal = odata_literal("x' or 1 eq 1 or 'a'='a")
    assert literal == "'x'' or 1 eq 1 or ''a''=''a'"


def test_scalar_literals():
    assert odata_literal(True) == "true"
    assert odata_literal(42) == "42"


def test_non_finite_number_rejected():
    with pytest.raises(ConnectorError):
        odata_literal(float("inf"))


def test_filter_builds_from_declared_fields_only():
    flt = build_filter(
        [{"field": "SoldToParty", "parameter": "sold_to_party", "op": "eq"}],
        {"sold_to_party": "1001"},
    )
    assert flt == "SoldToParty eq '1001'"


def test_bad_field_name_rejected_at_registration():
    with pytest.raises(ConnectorError):
        ODataConnector.validate_operation(
            "op",
            {
                "entity_set": "A_SalesOrder",
                "parameters": ["x"],
                "filters": [{"field": "a eq 1 or 1", "parameter": "x", "op": "eq"}],
            },
            {},
        )


def test_unknown_operator_rejected():
    with pytest.raises(ConnectorError):
        ODataConnector.validate_operation(
            "op",
            {"entity_set": "A", "parameters": ["x"], "filters": [{"field": "f", "parameter": "x", "op": "like"}]},
            {},
        )


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"value": [{"a": 1}]}, [{"a": 1}]),
        ({"d": {"results": [{"a": 1}]}}, [{"a": 1}]),
        ({"d": {"a": 1}}, [{"a": 1}]),
        ({"a": 1}, [{"a": 1}]),
    ],
)
def test_normalizes_v4_v2_and_single_entities(payload, expected):
    assert normalize_odata(payload) == expected
