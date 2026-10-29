# Contributing

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check . && ruff format --check chusky_bridge tests
pytest -q
chusky-bridge validate connectors_manifests/templates
alembic upgrade head --sql >/dev/null   # with CHUSKY_DATABASE_URL set
```

CI runs the same checks and builds the image.

## Rules that reviewers enforce

1. A change that widens what an agent can do needs a test that proves the boundary still holds.
2. New adapters follow [the adapter checklist](skills/chusky-bridge/references/adding-an-adapter.md).
3. Never accept an inline secret, a raw SQL statement, a free-form URL, or a shell command from a manifest or an agent.
4. Writes default to approval-gated. Any exception needs an ADR in `docs/adr/`.
5. Schema changes need an Alembic migration. Never edit a released migration.
6. Documentation changes ship with the code they describe.

## Commit messages

Use the imperative mood and name the component: `sftp: pin host key on reconnect`.
