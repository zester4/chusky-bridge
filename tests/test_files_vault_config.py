import httpx
import pytest

from chusky_bridge import vault
from chusky_bridge.config import require_server_config, settings
from chusky_bridge.files import FileNotApproved, resolve_approved_file
from chusky_bridge.vault import SecretNotFound, get_secret


def test_approved_file_resolves_inside_base(tmp_path):
    (tmp_path / "svc.wsdl").write_text("<x/>")
    assert resolve_approved_file("svc.wsdl", str(tmp_path)).name == "svc.wsdl"


@pytest.mark.parametrize("configured", ["../secret.txt", "/etc/passwd", "sub/../../x"])
def test_escapes_are_refused(tmp_path, configured):
    with pytest.raises(FileNotApproved):
        resolve_approved_file(configured, str(tmp_path))


def test_symlink_escape_refused(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    base = tmp_path / "approved"
    base.mkdir()
    (base / "link.txt").symlink_to(outside)
    with pytest.raises(FileNotApproved):
        resolve_approved_file("link.txt", str(base))


def test_env_secret_read(monkeypatch):
    monkeypatch.setattr(settings, "secret_vault_provider", "env")
    monkeypatch.setenv("CHUSKY_SECRET_LEGACY_ERP_DB", "Driver=x;PWD=y")
    assert get_secret("legacy_erp_db") == "Driver=x;PWD=y"


def test_missing_env_secret_is_generic(monkeypatch):
    monkeypatch.setattr(settings, "secret_vault_provider", "env")
    monkeypatch.delenv("CHUSKY_SECRET_MISSING_ONE", raising=False)
    with pytest.raises(SecretNotFound, match="not configured"):
        get_secret("missing_one")


def test_invalid_reference_rejected():
    with pytest.raises(SecretNotFound):
        get_secret("Bad-Ref; drop")


def test_vault_provider_reads_kv_v2(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Vault-Token")
        return httpx.Response(200, json={"data": {"data": {"value": "s3cret"}}})

    monkeypatch.setattr(settings, "secret_vault_provider", "vault")
    monkeypatch.setattr(settings, "vault_addr", "https://vault.example.internal:8200")
    monkeypatch.setattr(settings, "vault_token", "tok")
    monkeypatch.setattr(vault, "_vault_transport", httpx.MockTransport(handler))
    assert get_secret("legacy_erp_db") == "s3cret"
    assert seen["url"].endswith("/v1/secret/data/chusky/legacy_erp_db")
    assert seen["token"] == "tok"


def test_vault_refuses_plain_http(monkeypatch):
    monkeypatch.setattr(settings, "secret_vault_provider", "vault")
    monkeypatch.setattr(settings, "vault_addr", "http://vault.internal:8200")
    monkeypatch.setattr(settings, "vault_token", "tok")
    with pytest.raises(SecretNotFound, match="https"):
        get_secret("legacy_erp_db")


def test_aws_provider_reads_secret_string(monkeypatch):
    class FakeSecrets:
        def get_secret_value(self, SecretId):
            assert SecretId == "chusky/legacy_erp_db"
            return {"SecretString": "from-aws"}

    monkeypatch.setattr(settings, "secret_vault_provider", "aws")
    monkeypatch.setattr(vault, "_aws_client", FakeSecrets())
    assert get_secret("legacy_erp_db") == "from-aws"


def _cfg(monkeypatch, **values):
    base = dict(
        env="development",
        database_url="postgresql://x",
        jwt_jwks_url="https://idp/jwks",
        jwt_issuer="https://idp",
        secret_vault_provider="env",
        public_base_url="https://bridge.example.com",
    )
    base.update(values)
    for key, value in base.items():
        monkeypatch.setattr(settings, key, value)


def test_production_refuses_env_secrets(monkeypatch):
    _cfg(monkeypatch, env="production", secret_vault_provider="env")
    with pytest.raises(RuntimeError, match="vault or aws"):
        require_server_config()


def test_production_requires_https_public_url(monkeypatch):
    _cfg(monkeypatch, env="production", secret_vault_provider="vault", public_base_url="http://bridge")
    with pytest.raises(RuntimeError, match="https"):
        require_server_config()


def test_production_with_vault_and_https_passes(monkeypatch):
    _cfg(monkeypatch, env="production", secret_vault_provider="vault")
    require_server_config()


def test_missing_database_fails(monkeypatch):
    _cfg(monkeypatch, database_url="")
    with pytest.raises(RuntimeError, match="database_url"):
        require_server_config()


def test_settings_load_chusky_prefix(monkeypatch):
    monkeypatch.setenv("CHUSKY_MAX_TOOL_RESPONSE_BYTES", "1234")
    from chusky_bridge.config import Settings

    assert Settings(database_url="x", jwt_jwks_url="x", jwt_issuer="x").max_tool_response_bytes == 1234
