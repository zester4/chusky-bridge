import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connector_tenant_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    connector_type = Column(String(40), nullable=False)
    manifest_version = Column(String(40), nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    manifest = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    health_status = Column(String(20), nullable=True)
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("connector_id", "name", name="uq_tool_connector_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_id = Column(UUID(as_uuid=True), ForeignKey("connectors.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=False, default="")
    input_schema = Column(JSON, nullable=False)
    risk_level = Column(String(10), nullable=False, default="low")
    requires_approval = Column(Boolean, nullable=False, default=False)
    read_only = Column(Boolean, nullable=False, default=True)
    required_scopes = Column(JSON, nullable=False, default=list)
    definition_hash = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    connector_id = Column(UUID(as_uuid=True), nullable=False)
    tool_id = Column(UUID(as_uuid=True), nullable=False)
    tool_version = Column(Integer, nullable=False)
    requester_user_id = Column(String(255), nullable=False)
    agent_id = Column(String(255), nullable=False)
    arguments = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    approver_user_id = Column(String(255), nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(64), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(String(255), nullable=False)
    agent_id = Column(String(255), nullable=False)
    connector_id = Column(UUID(as_uuid=True), nullable=True)
    tool_id = Column(UUID(as_uuid=True), nullable=True)
    tool_version = Column(Integer, nullable=True)
    approval_id = Column(UUID(as_uuid=True), nullable=True)
    arguments = Column(JSON, nullable=False)
    decision = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    upstream_status = Column(String(40), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    result_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
