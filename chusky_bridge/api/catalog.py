from fastapi import APIRouter, Depends, Query

from chusky_bridge.auth import Identity, current_identity
from chusky_bridge.catalog import search_catalog

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("")
def catalog(
    q: str = Query("", max_length=100),
    category: str | None = None,
    era: str | None = None,
    adapter: str | None = None,
    adapter_status: str | None = None,
    _: Identity = Depends(current_identity),
):
    """Search named legacy and modern systems and how Chusky Bridge reaches each one.
    Entries are marked verification=unverified until a connector is tested against that system."""
    rows = search_catalog(q=q, category=category, era=era, adapter=adapter, adapter_status=adapter_status)
    return {"count": len(rows), "systems": rows}
