from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity, require_admin
from chusky_bridge.db import get_session
from chusky_bridge.models import AuditEvent, Connector

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/audit")
def search_audit(
    limit: int = Query(100, ge=1, le=500),
    decision: str | None = None,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    query = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == identity.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    if decision:
        query = query.where(AuditEvent.decision == decision)
    return [
        {
            "request_id": event.request_id,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "user_id": event.user_id,
            "agent_id": event.agent_id,
            "connector_id": str(event.connector_id) if event.connector_id else None,
            "tool_id": str(event.tool_id) if event.tool_id else None,
            "tool_version": event.tool_version,
            "approval_id": str(event.approval_id) if event.approval_id else None,
            "decision": event.decision,
            "reason": event.reason,
            "upstream_status": event.upstream_status,
            "duration_ms": event.duration_ms,
            "arguments": event.arguments,
        }
        for event in session.scalars(query).all()
    ]


@router.get("/connectors/health")
def connector_health(
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(Connector).where(Connector.tenant_id == identity.tenant_id).order_by(Connector.name)
    ).all()
    return [
        {
            "connector": row.name,
            "status": row.status,
            "health": row.health_status or "unknown",
            "last_checked_at": row.last_health_check_at.isoformat() if row.last_health_check_at else None,
        }
        for row in rows
    ]
