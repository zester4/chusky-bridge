import functools
from pathlib import Path
from typing import Any

import yaml

from chusky_bridge.config import settings
from chusky_bridge.connectors import IMPLEMENTED_TYPES, PLANNED_TYPES

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "systems" / "catalog.yaml"
ERAS = frozenset({"legacy", "midlife", "modern"})
REQUIRED = ("name", "vendor", "category", "era", "adapter", "notes")


def _adapter_status(adapter: str) -> str:
    if adapter in IMPLEMENTED_TYPES:
        return "implemented"
    if adapter in PLANNED_TYPES:
        return "planned"
    return "not_yet_modeled"


@functools.cache
def load_catalog() -> tuple[dict[str, Any], ...]:
    path = Path(settings.catalog_path) if settings.catalog_path else DEFAULT_CATALOG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for entry in raw.get("systems", []):
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            raise ValueError(f"catalog entry {entry.get('name', '?')} is missing {missing}")
        if entry["era"] not in ERAS:
            raise ValueError(f"catalog entry {entry['name']} has an invalid era")
        rows.append(
            {
                **entry,
                "adapter_status": _adapter_status(entry["adapter"]),
                "verification": "unverified",
            }
        )
    return tuple(rows)


def search_catalog(
    *,
    q: str = "",
    category: str | None = None,
    era: str | None = None,
    adapter: str | None = None,
    adapter_status: str | None = None,
) -> list[dict[str, Any]]:
    needle = q.strip().lower()
    results = []
    for row in load_catalog():
        haystack = f"{row['name']} {row['vendor']} {row['category']} {row['adapter']} {row['notes']}".lower()
        if needle and needle not in haystack:
            continue
        if category and row["category"] != category:
            continue
        if era and row["era"] != era:
            continue
        if adapter and row["adapter"] != adapter:
            continue
        if adapter_status and row["adapter_status"] != adapter_status:
            continue
        results.append(row)
    return results
