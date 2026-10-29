from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity, require_admin
from chusky_bridge.connectors import build_connector
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.db import get_session
from chusky_bridge.mcp.manifest import Manifest, ManifestError, parse_manifest
from chusky_bridge.models import Connector
from chusky_bridge.schemas import ConnectorCreate, ConnectorOut
from chusky_bridge.services import register_manifest

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


def _tenant_connector(session: Session, identity: Identity, name: str) -> Connector:
    connector = session.scalar(
        select(Connector).where(Connector.tenant_id == identity.tenant_id, Connector.name == name)
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return connector


@router.get("", response_model=list[ConnectorOut])
def list_connectors(identity: Identity = Depends(require_admin), session: Session = Depends(get_session)):
    return session.scalars(
        select(Connector).where(Connector.tenant_id == identity.tenant_id).order_by(Connector.name)
    ).all()


@router.post("", status_code=201, response_model=ConnectorOut)
def register(
    body: ConnectorCreate,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        parsed = parse_manifest(body.manifest_yaml)
        return register_manifest(session, identity.tenant_id, parsed)
    except ManifestError as exc:
        raise HTTPException(status_code=422, detail=f"invalid manifest: {exc}") from exc


@router.post("/{name}/health")
def run_health_check(
    name: str,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    connector = _tenant_connector(session, identity, name)
    detail = None
    try:
        implementation = build_connector(Manifest.model_validate(connector.manifest))
        status = str(implementation.health_check().get("status", "unknown"))
    except ConnectorError as exc:
        status, detail = "unhealthy", str(exc)
    except Exception as exc:
        status, detail = "unhealthy", f"health check error ({type(exc).__name__})"
    connector.health_status = status
    connector.last_health_check_at = datetime.now(UTC)
    session.commit()
    return {"connector": name, "health": status, "detail": detail}


@router.post("/{name}/disable", response_model=ConnectorOut)
def disable(name: str, identity: Identity = Depends(require_admin), session: Session = Depends(get_session)):
    connector = _tenant_connector(session, identity, name)
    connector.status = "disabled"
    session.commit()
    return connector


@router.post("/{name}/enable", response_model=ConnectorOut)
def enable(name: str, identity: Identity = Depends(require_admin), session: Session = Depends(get_session)):
    connector = _tenant_connector(session, identity, name)
    connector.status = "active"
    session.commit()
    return connector
