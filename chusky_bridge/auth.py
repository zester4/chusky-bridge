import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from chusky_bridge.config import settings

ADMIN_SCOPE = "chusky.admin"


class AuthError(Exception):
    """Safe to show to callers."""


@dataclass(frozen=True)
class Identity:
    tenant_id: uuid.UUID
    user_id: str
    agent_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


# Set by the /mcp middleware for the duration of one request.
identity_var: ContextVar["Identity | None"] = ContextVar("chusky_identity", default=None)

_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwt_jwks_url, cache_keys=True)
    return _jwks_client


def verify_token(token: str) -> Identity:
    """Validate signature, issuer, audience, expiry, and required claims."""
    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.jwt_algorithms,
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid or expired token") from exc
    except Exception as exc:  # JWKS fetch failures and similar
        raise AuthError("token could not be verified") from exc

    try:
        tenant_id = uuid.UUID(str(claims.get("tenant_id", "")))
    except ValueError as exc:
        raise AuthError("missing or invalid tenant_id claim") from exc

    return Identity(
        tenant_id=tenant_id,
        user_id=str(claims["sub"]),
        agent_id=str(claims.get("azp") or claims.get("client_id") or "unknown-agent"),
        scopes=frozenset(str(claims.get("scope", "")).split()),
    )


def current_identity(authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return verify_token(authorization[7:].strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_admin(identity: Identity = Depends(current_identity)) -> Identity:
    if not identity.has_scope(ADMIN_SCOPE):
        raise HTTPException(status_code=403, detail="admin scope required")
    return identity
