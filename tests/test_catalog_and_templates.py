from pathlib import Path

import pytest

from chusky_bridge.catalog import load_catalog, search_catalog
from chusky_bridge.connectors import validate_manifest_operations
from chusky_bridge.mcp.manifest import ManifestError, parse_manifest
from chusky_bridge.services import check_manifest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "connectors_manifests" / "templates").glob("*.yaml"))


def test_catalog_has_at_least_100_named_systems():
    assert len(load_catalog()) >= 100


def test_catalog_entries_are_marked_unverified():
    assert all(row["verification"] == "unverified" for row in load_catalog())


def test_catalog_adapter_status_is_derived_not_claimed():
    statuses = {row["adapter"]: row["adapter_status"] for row in load_catalog()}
    assert statuses["odbc"] == "implemented"
    assert statuses["tn3270"] == "implemented"


def test_every_catalog_adapter_is_built():
    assert all(row["adapter_status"] == "implemented" for row in load_catalog())


def test_catalog_search_finds_named_systems():
    assert any("S/4HANA" in row["name"] for row in search_catalog(q="sap"))
    assert any("Epic" in row["name"] for row in search_catalog(q="epic"))


def test_every_catalog_entry_has_valid_era():
    assert {row["era"] for row in load_catalog()} <= {"legacy", "midlife", "modern"}


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_templates_are_valid_but_not_activatable(path):
    parsed = parse_manifest(path.read_text(encoding="utf-8"))
    assert parsed.manifest.connector.status == "template"
    validate_manifest_operations(parsed.manifest)
    with pytest.raises(ManifestError, match="template"):
        check_manifest(parsed)


def test_template_count():
    assert len(TEMPLATES) >= 7
