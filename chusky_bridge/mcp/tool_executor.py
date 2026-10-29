import json
import time
import uuid
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.approvals import ApprovalError, claim_for_execution, create_request
from chusky_bridge.audit import record_event
from chusky_bridge.auth import Identity
from chusky_bridge.config import settings
from chusky_bridge.connectors import build_connector
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.db import SessionLocal
from chusky_bridge.mcp.manifest import Manifest
from chusky_bridge.models import Connector, ToolDefinition
from chusky_bridge.observability import TOOL_CALLS, TOOL_LATENCY, current_request_id
from chusky_bridge.policy import evaluate_tool_policy
from chusky_bridge.ratelimit import rate_limiter
from chusky_bridge.redaction import redact


class ToolCallError(Exception):
    """Safe to show to the calling agent."""


def _audit(
    session: Session,
    *,
    request_id: str,
    identity: Identity,
    arguments: dict[str, Any],
    decision: str,
    connector: Connector | None = None,
    tool: ToolDefinition | None = None,
    approval_id: uuid.UUID | None = None,
    reason: str | None = None,
    upstream_status: str | None = None,
    duration_ms: int | None = None,
    result_summary: str | None = None,
) -> None:
    TOOL_CALLS.labels(decision=decision).inc()
    record_event(
        session,
        request_id=request_id,
        identity=identity,
        decision=decision,
        connector_id=connector.id if connector else None,
        tool_id=tool.id if tool else None,
        tool_version=tool.version if tool else None,
        approval_id=approval_id,
        arguments=arguments,
        reason=reason,
        upstream_status=upstream_status,
        duration_ms=duration_ms,
        result_summary=result_summary,
    )


def _load_active_tool(
    session: Session, identity: Identity, connector_name: str, tool_name: str
) -> tuple[Connector, ToolDefinition]:
    connector = session.scalar(
        select(Connector).where(
            Connector.tenant_id == identity.tenant_id,
            Connector.name == connector_name,
            Connector.status == "active",
        )
    )
    if connector is None:
        raise ToolCallError("tool not found or not approved")
    tool = session.scalar(
        select(ToolDefinition).where(
            ToolDefinition.connector_id == connector.id,
            ToolDefinition.name == tool_name,
            ToolDefinition.enabled.is_(True),
        )
    )
    if tool is None:
        raise ToolCallError("tool not found or not approved")
    return connector, tool


def _validate_arguments(tool: ToolDefinition, arguments: dict[str, Any]) -> None:
    try:
        jsonschema.validate(arguments, tool.input_schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "root"
        raise ToolCallError(f"invalid arguments at {location}") from exc


def _bound_result(result: dict[str, Any]) -> dict[str, Any]:
    safe = redact(result)
    size = len(json.dumps(safe, default=str).encode())
    if size > settings.max_tool_response_bytes:
        return {"status": "truncated", "message": "result exceeded the size limit; narrow the request", "bytes": size}
    return safe


def _run(
    session: Session,
    *,
    request_id: str,
    identity: Identity,
    connector: Connector,
    tool: ToolDefinition,
    arguments: dict[str, Any],
    approval_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        implementation = build_connector(Manifest.model_validate(connector.manifest))
        result = implementation.execute(tool.name, arguments)
    except ConnectorError as exc:
        elapsed = time.monotonic() - started
        _audit(
            session,
            request_id=request_id,
            identity=identity,
            arguments=arguments,
            decision="error",
            connector=connector,
            tool=tool,
            approval_id=approval_id,
            reason=str(exc),
            duration_ms=int(elapsed * 1000),
        )
        raise ToolCallError(str(exc)) from exc

    elapsed = time.monotonic() - started
    TOOL_LATENCY.labels(connector_type=connector.connector_type).observe(elapsed)
    bounded = _bound_result(result)
    _audit(
        session,
        request_id=request_id,
        identity=identity,
        arguments=arguments,
        decision="executed",
        connector=connector,
        tool=tool,
        approval_id=approval_id,
        upstream_status=str(bounded.get("status")),
        duration_ms=int(elapsed * 1000),
        result_summary=f"status={bounded.get('status')}",
    )
    return bounded


def execute_tool(
    *,
    identity: Identity,
    connector_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Entry point for an agent tool call. Every outcome is audited and counted."""
    request_id = request_id or current_request_id()
    session = SessionLocal()
    try:
        try:
            connector, tool = _load_active_tool(session, identity, connector_name, tool_name)
            _validate_arguments(tool, arguments)
            limit_key = f"{identity.tenant_id}:{connector.name}:{tool.name}:{identity.user_id}"
            if not rate_limiter.allow(limit_key):
                _audit(
                    session,
                    request_id=request_id,
                    identity=identity,
                    arguments=arguments,
                    decision="denied",
                    connector=connector,
                    tool=tool,
                    reason="rate limit exceeded",
                )
                raise ToolCallError("rate limit exceeded; retry later")
        except ToolCallError as exc:
            _audit(
                session,
                request_id=request_id,
                identity=identity,
                arguments=arguments,
                decision="denied",
                reason=str(exc),
            )
            raise

        decision = evaluate_tool_policy(
            user_scopes=identity.scopes,
            tool_scopes=tool.required_scopes,
            tool_read_only=tool.read_only,
            tool_risk_level=tool.risk_level,
            tool_requires_approval=tool.requires_approval,
            write_tools_enabled=settings.enable_write_tools,
            arguments=arguments,
        )
        if not decision.allowed:
            _audit(
                session,
                request_id=request_id,
                identity=identity,
                arguments=arguments,
                decision="denied",
                connector=connector,
                tool=tool,
                reason=decision.reason,
            )
            raise ToolCallError(decision.reason)

        if decision.requires_approval:
            approval = create_request(session, connector=connector, tool=tool, identity=identity, arguments=arguments)
            _audit(
                session,
                request_id=request_id,
                identity=identity,
                arguments=arguments,
                decision="pending_approval",
                connector=connector,
                tool=tool,
                approval_id=approval.id,
                reason="awaiting human approval",
            )
            return {
                "status": "pending_approval",
                "approval_id": str(approval.id),
                "message": "A reviewer must approve this action before it runs.",
            }

        return _run(
            session,
            request_id=request_id,
            identity=identity,
            connector=connector,
            tool=tool,
            arguments=arguments,
        )
    finally:
        session.close()


def execute_approved(*, identity: Identity, approval_id: uuid.UUID, request_id: str | None = None) -> dict[str, Any]:
    """Run an approved action exactly once. The approver must hold the tool's scopes."""
    request_id = request_id or current_request_id()
    session = SessionLocal()
    try:
        try:
            approval = claim_for_execution(session, approval_id, identity.tenant_id)
        except ApprovalError as exc:
            raise ToolCallError(str(exc)) from exc

        connector = session.get(Connector, approval.connector_id)
        tool = session.get(ToolDefinition, approval.tool_id)
        if connector is None or tool is None or not tool.enabled or tool.version != approval.tool_version:
            _audit(
                session,
                request_id=request_id,
                identity=identity,
                arguments=approval.arguments,
                decision="denied",
                approval_id=approval.id,
                reason="tool changed or was disabled after approval",
            )
            raise ToolCallError("tool changed or was disabled after approval; request it again")

        decision = evaluate_tool_policy(
            user_scopes=identity.scopes,
            tool_scopes=tool.required_scopes,
            tool_read_only=tool.read_only,
            tool_risk_level=tool.risk_level,
            tool_requires_approval=tool.requires_approval,
            write_tools_enabled=settings.enable_write_tools,
            arguments=approval.arguments,
        )
        if not decision.allowed:
            _audit(
                session,
                request_id=request_id,
                identity=identity,
                arguments=approval.arguments,
                decision="denied",
                connector=connector,
                tool=tool,
                approval_id=approval.id,
                reason=decision.reason,
            )
            raise ToolCallError(decision.reason)

        return _run(
            session,
            request_id=request_id,
            identity=identity,
            connector=connector,
            tool=tool,
            arguments=approval.arguments,
            approval_id=approval.id,
        )
    finally:
        session.close()
