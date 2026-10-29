import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.config import settings
from chusky_bridge.db import SessionLocal
from chusky_bridge.mcp.manifest import ManifestError, parse_manifest
from chusky_bridge.models import Tenant
from chusky_bridge.services import register_manifest

log = logging.getLogger("chusky-bridge.discovery")


def ensure_bootstrap_tenant(session: Session) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.name == settings.bootstrap_tenant_name))
    if tenant is None:
        tenant = Tenant(name=settings.bootstrap_tenant_name)
        session.add(tenant)
        session.commit()
    return tenant


def load_manifest_dir(directory: Path) -> list[str]:
    """Load every reviewed manifest in a directory. Planned connector types are skipped with a warning."""
    if not directory.is_dir():
        log.warning("manifest directory %s does not exist", directory)
        return []

    loaded: list[str] = []
    session = SessionLocal()
    try:
        tenant = ensure_bootstrap_tenant(session)
        for path in sorted(directory.glob("*.yaml")):
            try:
                parsed = parse_manifest(path.read_text(encoding="utf-8"))
                connector = register_manifest(session, tenant.id, parsed)
                loaded.append(connector.name)
            except ManifestError as exc:
                log.warning("skipped %s: %s", path.name, exc)
    finally:
        session.close()
    return loaded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(load_manifest_dir(Path(settings.manifest_dir)))
