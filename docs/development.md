# Development

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Install optional drivers only when you work on the adapters that need them. The tests do not require
any vendor driver: adapters are tested through fakes injected via `sys.modules` or constructor seams.

## Layout

```
chusky_bridge/           application package
  api/                   admin routers
  connectors/            adapters, one module per transport
  mcp/                   MCP server, manifest model, tool registry and executor
  parsers/               file and message parsers
  workers/               startup loader and health sweep
migrations/              Alembic environment and versions
connectors_manifests/    active manifests (loaded at startup)
  templates/             starting points, validated in CI
systems/catalog.yaml     named-system catalog
tests/                   pytest suite
docs/                    documentation
skills/chusky-bridge/    agent skill and references
```

## Test, lint, and check

```bash
ruff check .
ruff format --check chusky_bridge tests
pytest -q
chusky-bridge validate connectors_manifests/templates
CHUSKY_DATABASE_URL=postgresql://offline/offline alembic upgrade head --sql >/dev/null
```

Fix formatting with `ruff format chusky_bridge tests` and lint with `ruff check --fix .`.

## Writing tests

- Test the policy and validation rules with pure functions. They need no fakes.
- For adapters, test `validate_operation` for every rule it enforces, and `execute` through a fake client.
- Inject fakes in one of three ways:
  1. `monkeypatch.setitem(sys.modules, "<library>", fake_module)` for libraries imported inside a method.
  2. A constructor seam, such as `driver_factory=` or `client_factory=`, for adapters that take one.
  3. Monkeypatching an instance method, such as `connector.http.request`, for HTTP.
- Assert the negative paths: refused values, refused writes, and error messages that leak nothing.

## Database migrations

1. Change the model in `chusky_bridge/models.py`.
2. Create a revision by hand, or with `alembic revision --autogenerate -m "..."` against a database that matches the previous revision.
3. Review the generated operations. Autogenerate misses constraint names and server defaults.
4. Verify offline: `CHUSKY_DATABASE_URL=postgresql://offline/offline alembic upgrade head --sql`.
5. Verify online against a disposable PostgreSQL: `alembic upgrade head`, then `alembic downgrade base`, then `alembic upgrade head`.

Never edit a migration that has been released. Add a new one.

## Running locally

```bash
export CHUSKY_ENV=development CHUSKY_LOG_JSON=false
export CHUSKY_DATABASE_URL=postgresql://chusky:chusky@localhost:5432/chusky
export CHUSKY_JWT_JWKS_URL=... CHUSKY_JWT_ISSUER=...
export CHUSKY_SECRET_LEGACY_ERP_DB='Driver=...'
alembic upgrade head
uvicorn chusky_bridge.main:app --reload
```

## Adding an adapter

Follow [skills/chusky-bridge/references/adding-an-adapter.md](../skills/chusky-bridge/references/adding-an-adapter.md).

## Release process

1. Update `CHANGELOG.md` and the version in `pyproject.toml` and `chusky_bridge/__init__.py`.
2. Run every check above. CI must be green on `main`.
3. Tag the release: `git tag -a v<version> -m "..."`.
4. CI builds the image. Push it to your registry with the version tag and the commit SHA.
5. Deploy to staging, run the production checklist, then promote.
