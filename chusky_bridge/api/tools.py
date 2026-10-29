import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity, require_admin
from chusky_bridge.config import settings
from chusky_bridge.db import get_session
from chusky_bridge.models import Connector, ToolDefinition
from chusky_bridge.schemas import ToolOut, ToolUpdate

router = APIRouter(prefix="/v1/tools", tags=["tools"])


def _tenant_tool(session: Session, identity: Identity, tool_id: uuid.UUID) -> ToolDefinition:
    tool = session.scalar(
        select(ToolDefinition)
        .join(Connector, ToolDefinition.connector_id == Connector.id)
        .where(ToolDefinition.id == tool_id, Connector.tenant_id == identity.tenant_id)
    )
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return tool


@router.get("", response_model=list[ToolOut])
def list_tools(
    connector_id: uuid.UUID | None = None,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    query = (
        select(ToolDefinition)
        .join(Connector, ToolDefinition.connector_id == Connector.id)
        .where(Connector.tenant_id == identity.tenant_id)
        .order_by(ToolDefinition.name)
    )
    if connector_id is not None:
        query = query.where(ToolDefinition.connector_id == connector_id)
    return session.scalars(query).all()


@router.patch("/{tool_id}", response_model=ToolOut)
def set_enabled(
    tool_id: uuid.UUID,
    body: ToolUpdate,
    identity: Identity = Depends(require_admin),
    session: Session = Depends(get_session),
):
    tool = _tenant_tool(session, identity, tool_id)
    if body.enabled and not tool.read_only and not settings.enable_write_tools:
        raise HTTPException(status_code=409, detail="write tools are disabled by platform policy")
    tool.enabled = body.enabled
    session.commit()
    session.refresh(tool)
    return tool
