# Architecture

## Components

```
MCP client (agent)
      │  HTTPS + bearer token (OAuth 2.1 resource server)
      ▼
┌──────────────────────────────────────────────────────────────┐
│ Chusky Bridge (FastAPI)                                      │
│                                                              │
│  /mcp  ── auth middleware ── MCP tools                       │
│            chusky_list_tools / chusky_call_tool              │
│                    │                                         │
│                    ▼                                         │
│  Tool executor: lookup → schema → rate limit → policy        │
│        │ approval required?                                  │
│        ├── yes → approval request (pending)                  │
│        └── no  → connector (adapter) → upstream system       │
│                    │                                         │
│  Audit log ◄───────┘   Metrics, JSON logs                    │
│                                                              │
│  Admin API: connectors, tools, approvals, audit, catalog     │
└──────────────────────────────────────────────────────────────┘
      │                              │
 PostgreSQL (state, audit)     Secret provider (Vault, AWS)
```

## Modules

| Module | Responsibility |
|---|---|
| `chusky_bridge/main.py` | App factory, middleware, health, metrics, router wiring |
| `chusky_bridge/auth.py` | JWT validation (signature, issuer, audience, expiry), scopes, admin guard |
| `chusky_bridge/mcp/` | MCP server, manifest model, tool registry (generation and versioning), executor |
| `chusky_bridge/policy.py` | Pure policy decision: scopes, write gating, risk, forbidden keys, length |
| `chusky_bridge/approvals.py` | Approval state machine, self-approval block, expiry, single-execution claim |
| `chusky_bridge/connectors/` | Adapters and the registry. Each adapter validates its own operations |
| `chusky_bridge/parsers/` | CSV, fixed-width, XML (defusedxml), X12, and HL7 v2 parsers |
| `chusky_bridge/vault.py` | Secret resolution by reference |
| `chusky_bridge/files.py` | Approved-directory file resolution (WSDLs, certificates) |
| `chusky_bridge/ratelimit.py` | Token bucket (memory) and fixed window (Redis) |
| `chusky_bridge/observability.py` | JSON logging, request IDs, Prometheus metrics |
| `chusky_bridge/catalog.py` | Named-system catalog and search |
| `chusky_bridge/cli.py` | `validate`, `catalog`, `check-config`, `version` |
| `chusky_bridge/workers/` | Manifest loader at startup, health sweep worker |

## Request flow for a tool call

1. The MCP middleware verifies the bearer token and binds the caller's identity to the request context.
2. `execute_tool` loads the connector (must be `active`) and the tool (must be `enabled`). Both are scoped to the caller's tenant.
3. The arguments are validated against the tool's closed JSON schema.
4. The rate limiter checks the tenant, connector, tool, and user key.
5. The policy function decides from scopes, read-only status, risk, approval requirement, forbidden keys, and size.
6. If approval is required, an `ApprovalRequest` is stored and the call returns `pending_approval`. Otherwise the adapter runs.
7. The adapter executes one named operation. It binds values, enforces its own limits, and returns structured data.
8. The result is redacted and size-checked, then audited and returned.

## Approval flow

```
agent call ──► pending ──► approve (other user, admin scope) ──► approved ──► claim ──► executed
                 │                                                  │
                 ├──► reject ──► rejected (terminal)                 └──► expired (TTL)
                 └──► expire (TTL) ──► expired (terminal)
```

Execution claims the row under a database lock, so a second approval attempt cannot run the action again.

## Data model

| Table | Purpose |
|---|---|
| `tenants` | Isolation boundary. Every row below carries a tenant |
| `connectors` | One per registered system: manifest, hash, status, health |
| `tool_definitions` | One per operation: schema, risk, scopes, version, enabled flag |
| `approval_requests` | Pending, approved, rejected, executed, or expired writes |
| `audit_events` | Every decision, with redacted arguments and the request ID |

Schema changes are Alembic migrations in `migrations/versions/`.

## Versioning of tools

A tool's `definition_hash` covers its entire operation, including the input schema, risk, and scopes.
Any change increments `version` and disables the tool. Approvals are tied to the version they were
requested under, so an approved action cannot execute after its definition changes.

## Scaling

- The API is stateless. Run several replicas behind a load balancer.
- Use `CHUSKY_RATE_LIMIT_BACKEND=redis` when running more than one replica.
- Run the health worker as a separate process (`python -m chusky_bridge.workers.sync_worker`).
- Adapter calls are synchronous and bounded by timeouts. Scale by replica count, not by threads.
