# Configuration

Every setting is read from the environment as `CHUSKY_<NAME>` or from a `.env` file. Values are
validated at startup. Invalid values stop the process with a clear error.

## Core

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_ENV` | `development` | `development`, `staging`, or `production`. Production enforces the rules listed below |
| `CHUSKY_PUBLIC_BASE_URL` | `http://localhost:8000` | Public URL. Must be `https://` in production |
| `CHUSKY_LOG_LEVEL` | `INFO` | Standard Python log level |
| `CHUSKY_LOG_JSON` | `true` | JSON logs. Set `false` for human-readable local output |
| `CHUSKY_METRICS_ENABLED` | `true` | Expose `/metrics` |
| `CHUSKY_DATABASE_URL` | empty | PostgreSQL URL. Required to serve the API |
| `CHUSKY_REDIS_URL` | `redis://localhost:6379/0` | Used when rate limiting is `redis` |

## Identity

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_JWT_JWKS_URL` | empty | JWKS endpoint of your identity provider. Required to serve |
| `CHUSKY_JWT_ISSUER` | empty | Expected `iss` claim. Required to serve |
| `CHUSKY_JWT_AUDIENCE` | `chusky-bridge-mcp` | Expected `aud` claim |
| `CHUSKY_JWT_ALGORITHMS` | `["RS256","ES256"]` | Accepted signing algorithms (JSON list) |

Tokens need `sub`, `tenant_id` (UUID), and `scope` (space-separated). The admin scope is `chusky.admin`.

## Secrets

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_SECRET_VAULT_PROVIDER` | `env` | `env`, `vault`, or `aws`. Production refuses `env` |
| `CHUSKY_SECRET_<REF>` | n/a | Development only. Value for `secret_ref: <ref>` |
| `CHUSKY_VAULT_ADDR` | empty | Vault URL. Must be `https://` |
| `CHUSKY_VAULT_TOKEN` | empty | Vault token with read access to the prefix |
| `CHUSKY_VAULT_MOUNT` | `secret` | KV v2 mount |
| `CHUSKY_VAULT_PREFIX` | `chusky` | Path prefix; secret `<ref>` lives at `<mount>/data/<prefix>/<ref>`, field `value` |
| `CHUSKY_AWS_REGION` | SDK default | Region for Secrets Manager |
| `CHUSKY_AWS_SECRET_PREFIX` | `chusky/` | Name prefix; secret `<ref>` is `<prefix><ref>` |

## Behavior and limits

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_ENABLE_WRITE_TOOLS` | `false` | Global switch for write tools. Keep off until approvals are tested |
| `CHUSKY_APPROVAL_TTL_SECONDS` | `900` | How long an approval request stays valid |
| `CHUSKY_MAX_TOOL_RESPONSE_BYTES` | `100000` | Maximum size of a tool result returned to an agent |
| `CHUSKY_RATE_LIMIT_BACKEND` | `memory` | `memory` (one process) or `redis` (shared across replicas) |
| `CHUSKY_RATE_LIMIT_PER_MINUTE` | `60` | Calls per minute per tenant, connector, tool, and user |

## Files

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_WSDL_DIR` | `/etc/chusky-bridge/wsdl` | Only directory from which WSDL files are loaded |
| `CHUSKY_CERT_DIR` | `/etc/chusky-bridge/certs` | Only directory from which client certificates, keys, and CA bundles are loaded |
| `CHUSKY_CATALOG_PATH` | repository `systems/catalog.yaml` | Override the system catalog |

## Workers

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_HEALTH_INTERVAL_SECONDS` | `300` | Seconds between health sweeps in `chusky_bridge.workers.sync_worker` |

## Startup and manifests

| Variable | Default | Purpose |
|---|---|---|
| `CHUSKY_BOOTSTRAP_TENANT_NAME` | `default` | Tenant that startup manifests load into |
| `CHUSKY_MANIFEST_DIR` | `connectors_manifests` | Directory of active manifests loaded at startup |
| `CHUSKY_LOAD_MANIFESTS_ON_START` | `true` | Load manifests when the API starts |

## Production rules

Startup fails in production when:

- `CHUSKY_DATABASE_URL`, `CHUSKY_JWT_JWKS_URL`, or `CHUSKY_JWT_ISSUER` is empty
- `CHUSKY_SECRET_VAULT_PROVIDER` is `env`
- `CHUSKY_PUBLIC_BASE_URL` does not start with `https://`

Run `chusky-bridge check-config` to see the same checks without starting the server.
