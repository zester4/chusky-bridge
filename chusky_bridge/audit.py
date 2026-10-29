import uuid

from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity
from chusky_bridge.models import AuditEvent
from chusky_bridge.redaction import redact


def record_event(
    session: Session,
    *,
    request_id: str,
    identity: Identity,
    decision: str,
    connector_id: uuid.UUID | None = None,
    tool_id: uuid.UUID | None = None,
    tool_version: int | None = None,
    approval_id: uuid.UUID | None = None,
    arguments: dict | None = None,
    reason: str | None = None,
    upstream_status: str | None = None,
    duration_ms: int | None = None,
    result_summary: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        request_id=request_id,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        agent_id=identity.agent_id,
        connector_id=connector_id,
        tool_id=tool_id,
        tool_version=tool_version,
        approval_id=approval_id,
        arguments=redact(arguments or {}),
        decision=decision,
        reason=reason,
        upstream_status=upstream_status,
        duration_ms=duration_ms,
        result_summary=result_summary[:500] if result_summary else None,
    )
    session.add(event)
    session.commit()
    return event
