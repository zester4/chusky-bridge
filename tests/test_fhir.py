import pytest

from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.connectors.fhir import FhirConnector


def test_resource_must_be_allowlisted():
    with pytest.raises(ConnectorError, match="allowlisted"):
        FhirConnector.validate_operation("op", {"mode": "read", "resource": "Bundle", "parameters": ["id"]}, {})


def test_read_takes_only_id():
    with pytest.raises(ConnectorError):
        FhirConnector.validate_operation("op", {"mode": "read", "resource": "Patient", "parameters": ["x"]}, {})


def test_include_parameters_forbidden():
    with pytest.raises(ConnectorError, match="not allowed"):
        FhirConnector.validate_operation(
            "op",
            {
                "mode": "search",
                "resource": "Patient",
                "parameters": ["mrn"],
                "search_parameters": {"mrn": "_include"},
            },
            {},
        )


def test_valid_search_passes():
    FhirConnector.validate_operation(
        "op",
        {"mode": "search", "resource": "Patient", "parameters": ["mrn"], "search_parameters": {"mrn": "identifier"}},
        {},
    )
