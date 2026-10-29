import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.approvals import ApprovalError, decide
from chusky_bridge.auth import Identity, require_admin
from chusky_bridge.db import get_session
from chusky_bridge.mcp.tool_executor import ToolCallError, execute_approved
from chusky_bridge.models import ApprovalRequest
from chusky_bridge.redaction import redact
from chusky_bridge.schemas import ApprovalDecision

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


def _as_dict(request: ApprovalRequest) -> dict:
    return {
        "id": str(request.id),
        "status": request.status,
        "tool_id": str(request.tool_id),
        "tool_version": request.tool_version,
        "requester_user_id": request.requester_user_id,
        "agent_id": request.agent_id,
        "arguments": redact(request.arguments),
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
    }


@router.get("")
def list_approvals(
    status: str = "pending",
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.tenant_id == identity.tenant_id, ApprovalRequest.status == status)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    ).all()
    return [_as_dict(row) for row in rows]


@router.post("/{approval_id}/approve")
def approve(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        decide(session, approval_id=approval_id, approver=identity, approve=True, reason=body.reason)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        result = execute_approved(identity=identity, approval_id=approval_id)
    except ToolCallError as exc:
        return {"status": "approved_not_executed", "message": str(exc)}
    return {"status": "executed", "result": result}


@router.post("/{approval_id}/reject")
def reject(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        request = decide(session, approval_id=approval_id, approver=identity, approve=False, reason=body.reason)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": request.status}
