import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.auth import Identity
from chusky_bridge.config import settings
from chusky_bridge.mcp.manifest import Operation, ParsedManifest
from chusky_bridge.models import Connector, ToolDefinition

MAX_DESCRIPTION_CHARS = 500


def build_input_schema(op: Operation) -> dict[str, Any]:
    """Closed JSON schema for one operation. Unknown fields are always rejected."""
    if op.input_schema is not None:
        schema: dict[str, Any] = {"type": "object", **op.input_schema}
        schema["additionalProperties"] = False
        return schema
    return {
        "type": "object",
        "properties": {p: {"type": "string", "maxLength": 4000} for p in op.parameters},
        "required": list(op.parameters),
        "additionalProperties": False,
    }


def operation_hash(op: Operation) -> str:
    return hashlib.sha256(json.dumps(op.model_dump(), sort_keys=True, default=str).encode()).hexdigest()


def sync_connector_tools(session: Session, connector: Connector, parsed: ParsedManifest) -> list[ToolDefinition]:
    """Generate or update tools from manifest operations.

    Any change to an operation bumps its version and disables it until a reviewer
    re-approves it. Operations removed from the manifest are disabled.
    """
    existing = {
        tool.name: tool
        for tool in session.scalars(select(ToolDefinition).where(ToolDefinition.connector_id == connector.id))
    }
    synced: list[ToolDefinition] = []

    for name, op in parsed.manifest.operations.items():
        digest = operation_hash(op)
        tool = existing.get(name)
        if tool is None:
            tool = ToolDefinition(connector_id=connector.id, name=name, version=1, enabled=False)
            session.add(tool)
        elif tool.definition_hash != digest:
            tool.version += 1
            tool.enabled = False

        tool.description = (op.description or name)[:MAX_DESCRIPTION_CHARS]
        tool.input_schema = build_input_schema(op)
        tool.risk_level = op.risk_level
        tool.requires_approval = op.requires_approval
        tool.read_only = op.read_only
        tool.required_scopes = sorted(op.required_scopes)
        tool.definition_hash = digest
        synced.append(tool)

    for name, tool in existing.items():
        if name not in parsed.manifest.operations:
            tool.enabled = False

    return synced


def list_enabled_tools(session: Session, identity: Identity) -> list[dict[str, Any]]:
    """Tools this caller may see: enabled, scoped to them, and not write-blocked by platform policy."""
    rows = session.execute(
        select(Connector, ToolDefinition)
        .join(ToolDefinition, ToolDefinition.connector_id == Connector.id)
        .where(
            Connector.tenant_id == identity.tenant_id,
            Connector.status == "active",
            ToolDefinition.enabled.is_(True),
        )
    ).all()

    tools: list[dict[str, Any]] = []
    for connector, tool in rows:
        if not set(tool.required_scopes or []).issubset(identity.scopes):
            continue
        if not tool.read_only and not settings.enable_write_tools:
            continue
        tools.append(
            {
                "connector": connector.name,
                "tool": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "read_only": tool.read_only,
                "risk_level": tool.risk_level,
                "requires_approval": tool.requires_approval,
            }
        )
    return tools
