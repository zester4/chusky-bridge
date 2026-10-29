import uuid

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCreate(BaseModel):
    manifest_yaml: str = Field(min_length=10, max_length=200_000)


class ConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    connector_type: str
    manifest_version: str
    status: str
    health_status: str | None = None


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_id: uuid.UUID
    name: str
    description: str
    risk_level: str
    requires_approval: bool
    read_only: bool
    enabled: bool
    version: int


class ToolUpdate(BaseModel):
    enabled: bool


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
