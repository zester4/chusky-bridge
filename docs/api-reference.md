# API reference

Base URL: the deployment's `CHUSKY_PUBLIC_BASE_URL`. Authenticated endpoints need
`Authorization: Bearer <token>`. Admin endpoints need the `chusky.admin` scope. Errors use the
standard FastAPI shape `{"detail": "..."}`. MCP errors are returned as tool results with
`status: error`.

## Operations (unauthenticated)

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness. Returns `{"status":"ok"}` while the process runs |
| GET | `/readyz` | Readiness. `200` when the database answers, `503` otherwise |
| GET | `/metrics` | Prometheus metrics. Expose only internally (see [deployment.md](deployment.md)) |
| GET | `/.well-known/oauth-protected-resource` | OAuth protected-resource metadata for MCP clients |

Every response carries `X-Request-ID`. Send your own `X-Request-ID` (8 to 64 letters, digits, or hyphens) to correlate logs.

## Connectors (admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/connectors` | List connectors in the caller's tenant |
| POST | `/v1/connectors` | Register or update a connector from `{"manifest_yaml": "..."}`. Validates all operations. Returns `422` with the reason on failure |
| POST | `/v1/connectors/{name}/health` | Run the adapter's health check now and store the result |
| POST | `/v1/connectors/{name}/disable` | Stop all tool calls to this connector |
| POST | `/v1/connectors/{name}/enable` | Allow tool calls again |

## Tools (admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/tools?connector_id=` | List generated tools with risk, approval, and enabled state |
| PATCH | `/v1/tools/{tool_id}` | Body `{"enabled": true|false}`. Enabling a write tool returns `409` unless writes are enabled platform-wide |

## Approvals (admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/approvals?status=pending` | List approval requests with redacted arguments |
| POST | `/v1/approvals/{id}/approve` | Approve and execute once. Body `{"reason": "..."}`. Returns the result or `approved_not_executed` with the reason |
| POST | `/v1/approvals/{id}/reject` | Reject. Terminal |

Self-approval is refused. An approver needs the tool's required scopes at execution time.

## Audit (admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/admin/audit?limit=100&decision=denied` | Recent decisions for the tenant, newest first. `limit` 1 to 500 |
| GET | `/v1/admin/connectors/health` | Stored health status per connector |

## Catalog (any authenticated user)

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/catalog?q=&category=&era=&adapter=&adapter_status=` | Search named systems. Every entry is marked `verification: unverified` |

## MCP (`/mcp`, Streamable HTTP)

Clients connect with a bearer token. Unauthenticated requests get `401` with a `WWW-Authenticate`
header that points to the protected-resource metadata.

### Tools

**`chusky_list_tools()`** returns the tools the caller may use. A tool appears only when it is enabled,
its connector is active, the caller holds all of its required scopes, and (for writes) platform writes are on.

```json
{"tools": [{"connector": "ibm_i_customers", "tool": "get_customer_by_number",
            "description": "...", "input_schema": {...}, "read_only": true,
            "risk_level": "low", "requires_approval": false}],
 "policy": {"write_tools_enabled": false, "max_response_bytes": 100000}}
```

**`chusky_call_tool(connector_name, tool_name, arguments)`** runs one tool. Possible results:

| `status` | Meaning |
|---|---|
| `success`, `completed`, `committed`, `sent` | The operation ran. Result fields depend on the adapter |
| `pending_approval` | A reviewer must approve; includes `approval_id` |
| `truncated` | The result exceeded the size limit; narrow the request |
| `error` | Refused or failed. `message` says why, without internals |

Arguments are validated against the tool's `input_schema`. Unknown fields are refused.

## Status codes

| Code | When |
|---|---|
| 200, 201 | Success |
| 401 | Missing or invalid token |
| 403 | Token lacks the admin scope |
| 404 | Not found in the caller's tenant (never reveals other tenants' records) |
| 409 | Conflict: approval already decided or expired, write tools disabled |
| 422 | Manifest or request invalid |
| 503 | Not ready (`/readyz`) |
