# Getting started

This guide takes you from a clean checkout to an agent calling a read-only tool against a system.

## 1. Prerequisites

- Python 3.11 or later, or Docker
- PostgreSQL 14 or later
- An OIDC identity provider that issues JWTs with `sub`, `tenant_id`, and `scope` claims, and an admin scope named `chusky.admin`
- Network access from the Bridge to the target system

## 2. Configure

```bash
cp .env.example .env
```

Set at minimum:

- `CHUSKY_DATABASE_URL`
- `CHUSKY_JWT_JWKS_URL`, `CHUSKY_JWT_ISSUER`, `CHUSKY_JWT_AUDIENCE`
- `CHUSKY_PUBLIC_BASE_URL` (the URL MCP clients reach)

Development can use the `env` secret provider. Production must use `vault` or `aws`. See
[configuration.md](configuration.md).

## 3. Install and check

```bash
pip install -e ".[dev]"
chusky-bridge check-config
chusky-bridge validate connectors_manifests/templates
pytest -q
```

## 4. Run

With Docker:

```bash
docker compose up --build
```

Or locally, after applying migrations:

```bash
export CHUSKY_DATABASE_URL=postgresql://chusky:chusky@localhost:5432/chusky
alembic upgrade head
uvicorn chusky_bridge.main:app --reload
```

Check it is alive and ready:

```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/readyz
```

## 5. Register a connector

Pick a template, copy it, and fill in the discovered names. The walkthrough is in
[connecting-a-system.md](connecting-a-system.md). Then:

```bash
export TOKEN=<admin token with chusky.admin scope>
curl -s -X POST localhost:8000/v1/connectors \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"manifest_yaml\": $(python -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' my_connector.yaml)}"
```

The response lists the connector. Its operations are now tools, disabled until you enable them.

## 6. Test the connection and enable a tool

```bash
curl -s -X POST localhost:8000/v1/connectors/ibm_i_customers/health -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/v1/tools -H "Authorization: Bearer $TOKEN"
curl -s -X PATCH localhost:8000/v1/tools/<tool-id> -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"enabled": true}'
```

Enabling a tool does not grant anyone access. Users still need the tool's `required_scopes`.

## 7. Call it from an agent

Point an MCP client at `https://<host>/mcp` with a user token that carries the required scopes.
The agent calls `chusky_list_tools`, then `chusky_call_tool` with the connector name, tool name,
and arguments. Read-only tools return results immediately. Write tools return `pending_approval`
until a reviewer approves them through `POST /v1/approvals/{id}/approve`.

## 8. Confirm the audit trail

```bash
curl -s "localhost:8000/v1/admin/audit?limit=20" -H "Authorization: Bearer $TOKEN"
```

Every call appears with its decision, redacted arguments, and request ID.
