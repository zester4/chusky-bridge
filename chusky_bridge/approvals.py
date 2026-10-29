import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity
from chusky_bridge.config import settings
from chusky_bridge.models import ApprovalRequest


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class ApprovalError(Exception):
    """Safe to show to callers."""


_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset({ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}),
    ApprovalStatus.APPROVED: frozenset({ApprovalStatus.EXECUTED, ApprovalStatus.EXPIRED}),
}


def transition(current: ApprovalStatus, target: ApprovalStatus) -> ApprovalStatus:
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise ApprovalError(f"approval cannot move from {current.value} to {target.value}")
    return target


def assert_can_decide(requester_user_id: str, approver: Identity) -> None:
    if approver.user_id == requester_user_id:
        raise ApprovalError("requesters cannot approve their own actions")


def is_expired(request, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return request.expires_at is not None and request.expires_at <= now


def create_request(session: Session, *, connector, tool, identity: Identity, arguments: dict) -> ApprovalRequest:
    now = datetime.now(UTC)
    request = ApprovalRequest(
        tenant_id=identity.tenant_id,
        connector_id=connector.id,
        tool_id=tool.id,
        tool_version=tool.version,
        requester_user_id=identity.user_id,
        agent_id=identity.agent_id,
        arguments=arguments,
        status=ApprovalStatus.PENDING.value,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
    )
    session.add(request)
    session.commit()
    return request


def _load(session: Session, approval_id: uuid.UUID, tenant_id: uuid.UUID, *, lock: bool = False) -> ApprovalRequest:
    query = select(ApprovalRequest).where(
        ApprovalRequest.id == approval_id,
        ApprovalRequest.tenant_id == tenant_id,
    )
    if lock:
        query = query.with_for_update()
    request = session.scalar(query)
    if request is None:
        raise ApprovalError("approval not found")
    return request


def _expire_if_needed(session: Session, request: ApprovalRequest) -> None:
    open_states = {ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value}
    if request.status in open_states and is_expired(request):
        request.status = transition(ApprovalStatus(request.status), ApprovalStatus.EXPIRED).value
        session.commit()
        raise ApprovalError("approval has expired")


def decide(
    session: Session,
    *,
    approval_id: uuid.UUID,
    approver: Identity,
    approve: bool,
    reason: str | None = None,
) -> ApprovalRequest:
    request = _load(session, approval_id, approver.tenant_id, lock=True)
    assert_can_decide(request.requester_user_id, approver)
    _expire_if_needed(session, request)
    target = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    request.status = transition(ApprovalStatus(request.status), target).value
    request.approver_user_id = approver.user_id
    request.decision_reason = reason
    request.decided_at = datetime.now(UTC)
    session.commit()
    return request


def claim_for_execution(session: Session, approval_id: uuid.UUID, tenant_id: uuid.UUID) -> ApprovalRequest:
    """Atomically move an approved request to executed. A second claim fails."""
    request = _load(session, approval_id, tenant_id, lock=True)
    _expire_if_needed(session, request)
    request.status = transition(ApprovalStatus(request.status), ApprovalStatus.EXECUTED).value
    request.executed_at = datetime.now(UTC)
    session.commit()
    return request
