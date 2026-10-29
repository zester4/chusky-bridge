import logging
import os
import time
from datetime import UTC, datetime

from sqlalchemy import select

from chusky_bridge.connectors import build_connector
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.db import SessionLocal
from chusky_bridge.mcp.manifest import Manifest
from chusky_bridge.models import Connector

log = logging.getLogger("chusky-bridge.health")
INTERVAL_SECONDS = int(os.environ.get("CHUSKY_HEALTH_INTERVAL_SECONDS", "300"))


def run_health_checks_once() -> dict[str, str]:
    """Check every active connector and persist the result. Errors are logged by type only."""
    session = SessionLocal()
    results: dict[str, str] = {}
    try:
        for connector in session.scalars(select(Connector).where(Connector.status == "active")).all():
            try:
                implementation = build_connector(Manifest.model_validate(connector.manifest))
                status = str(implementation.health_check().get("status", "unknown"))
            except ConnectorError as exc:
                status = "unhealthy"
                log.warning("connector %s unhealthy: %s", connector.name, exc)
            except Exception as exc:
                status = "unhealthy"
                log.error("connector %s health check failed (%s)", connector.name, type(exc).__name__)
            connector.health_status = status
            connector.last_health_check_at = datetime.now(UTC)
            results[f"{connector.tenant_id}/{connector.name}"] = status
        session.commit()
    finally:
        session.close()
    return results


def run_forever() -> None:
    while True:
        log.info("health sweep: %s", run_health_checks_once())
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
