import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_CONNECTOR_NAME = re.compile(r"^[a-z][a-z0-9_\-]{1,62}$")
_OP_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PARAM = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SCOPE = re.compile(r"^[a-z0-9_.\-]{3,128}$")
_FORBIDDEN_CONNECTION_KEYS = frozenset(
    {"password", "connection_string", "api_key", "token", "secret", "dsn", "passwd", "sasl_password"}
)


class ManifestError(ValueError):
    """Safe to show to the person registering a connector."""


class ConnectorInfo(BaseModel):
    name: str
    type: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Literal["active", "template"] = "active"

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not _CONNECTOR_NAME.match(value):
            raise ValueError("connector name must be lowercase letters, digits, '_' or '-'")
        return value


class Operation(BaseModel):
    """Common operation fields. Adapter-specific fields (query, procedure, entity_set, layout, ...)
    are allowed through and checked by each adapter's validate_operation."""

    model_config = ConfigDict(extra="allow")

    description: str = Field(default="", max_length=500)
    mode: str = "stored_procedure"
    parameters: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    read_only: bool = True
    requires_approval: bool = False
    required_scopes: list[str] = Field(default_factory=list)

    @field_validator("parameters")
    @classmethod
    def _valid_parameters(cls, values: list[str]) -> list[str]:
        for name in values:
            if not _PARAM.match(name):
                raise ValueError(f"invalid parameter name: {name}")
        return values

    @field_validator("required_scopes")
    @classmethod
    def _valid_scopes(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("every operation must declare required_scopes")
        for scope in values:
            if not _SCOPE.match(scope):
                raise ValueError(f"invalid scope name: {scope}")
        return values

    @model_validator(mode="after")
    def _risk_rules(self) -> "Operation":
        if not self.read_only and not self.requires_approval:
            raise ValueError("write operations must set requires_approval: true")
        if self.risk_level == "high" and not self.requires_approval:
            raise ValueError("high-risk operations must require approval")
        return self


class Manifest(BaseModel):
    connector: ConnectorInfo
    connection: dict[str, Any] = Field(default_factory=dict)
    operations: dict[str, Operation]

    @field_validator("connection")
    @classmethod
    def _no_inline_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        bad = sorted(k for k in value if str(k).lower() in _FORBIDDEN_CONNECTION_KEYS)
        if bad:
            raise ValueError(f"inline secrets are not allowed in connection ({', '.join(bad)}); use secret_ref")
        return value

    @field_validator("operations")
    @classmethod
    def _valid_operations(cls, value: dict[str, Operation]) -> dict[str, Operation]:
        if not value:
            raise ValueError("a connector must define at least one operation")
        for name in value:
            if not _OP_NAME.match(name):
                raise ValueError(f"invalid operation name: {name}")
        return value


@dataclass(frozen=True)
class ParsedManifest:
    manifest: Manifest
    raw: dict[str, Any]
    hash: str


def parse_manifest(text: str) -> ParsedManifest:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError("manifest is not valid YAML") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a mapping")
    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(f"manifest validation failed: {exc.errors()[0]['msg']}") from exc
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return ParsedManifest(manifest=manifest, raw=raw, hash=hashlib.sha256(canonical.encode()).hexdigest())
