"""Secret resolution. Connectors reference secrets by name; values never appear in manifests.

Providers:
  env    development only. Reads CHUSKY_SECRET_<REF>.
  vault  HashiCorp Vault KV v2 at <vault_mount>/data/<vault_prefix>/<ref>, field "value".
  aws    AWS Secrets Manager secret named <aws_secret_prefix><ref>, SecretString.
"""

import os
import re
from typing import Any

import httpx

from chusky_bridge.config import settings


class SecretNotFound(LookupError):
    """Always raised with a generic message. Never includes the secret or its value."""


_REF = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
# Test seams. Production leaves these as None.
_vault_transport: httpx.BaseTransport | None = None
_aws_client: Any = None


def get_secret(ref: str) -> str:
    if not _REF.match(ref):
        raise SecretNotFound("invalid secret reference")
    provider = settings.secret_vault_provider
    if provider == "env":
        return _from_env(ref)
    if provider == "vault":
        return _from_vault(ref)
    if provider == "aws":
        return _from_aws(ref)
    raise SecretNotFound("secret provider is not supported")


def _from_env(ref: str) -> str:
    value = os.environ.get("CHUSKY_SECRET_" + ref.upper())
    if not value:
        raise SecretNotFound("secret is not configured")
    return value


def _from_vault(ref: str) -> str:
    if not settings.vault_addr or not settings.vault_token:
        raise SecretNotFound("vault is not configured")
    if not settings.vault_addr.startswith("https://"):
        raise SecretNotFound("vault address must use https")
    url = f"{settings.vault_addr.rstrip('/')}/v1/{settings.vault_mount}/data/{settings.vault_prefix}/{ref}"
    try:
        with httpx.Client(timeout=5.0, transport=_vault_transport, follow_redirects=False) as client:
            response = client.get(url, headers={"X-Vault-Token": settings.vault_token})
        response.raise_for_status()
        value = response.json()["data"]["data"]["value"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise SecretNotFound("secret could not be read from vault") from exc
    if not isinstance(value, str) or not value:
        raise SecretNotFound("secret is empty")
    return value


def _from_aws(ref: str) -> str:
    try:
        client = _aws_client or _build_aws_client()
        response = client.get_secret_value(SecretId=f"{settings.aws_secret_prefix}{ref}")
    except Exception as exc:
        raise SecretNotFound("secret could not be read from AWS Secrets Manager") from exc
    value = response.get("SecretString")
    if not value:
        raise SecretNotFound("secret is empty")
    return value


def _build_aws_client() -> Any:
    import boto3

    return boto3.client("secretsmanager", region_name=settings.aws_region or None)
