from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings are read from CHUSKY_<NAME> environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHUSKY_", extra="ignore")

    env: Literal["development", "staging", "production"] = "development"
    public_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    log_json: bool = True
    metrics_enabled: bool = True

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    jwt_jwks_url: str = ""
    jwt_issuer: str = ""
    jwt_audience: str = "chusky-bridge-mcp"
    jwt_algorithms: list[str] = ["RS256", "ES256"]

    secret_vault_provider: Literal["env", "vault", "aws"] = "env"
    vault_addr: str = ""
    vault_token: str = ""
    vault_mount: str = "secret"
    vault_prefix: str = "chusky"
    aws_region: str = ""
    aws_secret_prefix: str = "chusky/"

    max_tool_response_bytes: int = 100_000
    default_query_timeout_seconds: int = 10
    enable_write_tools: bool = False
    approval_ttl_seconds: int = 900
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_per_minute: int = 60

    wsdl_dir: str = "/etc/chusky-bridge/wsdl"
    cert_dir: str = "/etc/chusky-bridge/certs"
    catalog_path: str = ""

    bootstrap_tenant_name: str = "default"
    manifest_dir: str = "connectors_manifests"
    load_manifests_on_start: bool = True


settings = Settings()


def require_server_config() -> None:
    """Fail fast at API startup. Production also refuses environment-variable secrets."""
    missing = [name for name in ("database_url", "jwt_jwks_url", "jwt_issuer") if not getattr(settings, name)]
    if missing:
        raise RuntimeError(f"missing required configuration: {', '.join(missing)}")
    if settings.env == "production":
        if settings.secret_vault_provider == "env":
            raise RuntimeError("production requires CHUSKY_SECRET_VAULT_PROVIDER=vault or aws")
        if not settings.public_base_url.startswith("https://"):
            raise RuntimeError("production requires an https CHUSKY_PUBLIC_BASE_URL")
