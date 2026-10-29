# API and MCP reference

Full reference: `docs/api-reference.md`.

## Authentication

- Bearer JWT from the configured issuer. Required claims: `sub`, `tenant_id` (UUID), `scope` (space-separated). Admin endpoints need `chusky.admin`.
- Audience must equal `CHUSKY_JWT_AUDIENCE`. Signing algorithms are `CHUSKY_JWT_ALGORITHMS`.

## Admin endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/connectors` | Tenant connectors |
| POST | `/v1/connectors` | Body `{"manifest_yaml": "..."}`; 422 on invalid |
| POST | `/v1/connectors/{name}/health` | Runs the check, stores the result |
| POST | `/v1/connectors/{name}/disable` / `/enable` | Stops or resumes all calls |
| GET | `/v1/tools?connector_id=` | Generated tools |
| PATCH | `/v1/tools/{id}` | `{"enabled": bool}`; 409 when enabling a write while writes are off |
| GET | `/v1/approvals?status=` | Redacted arguments |
| POST | `/v1/approvals/{id}/approve` | Approve and execute once |
| POST | `/v1/approvals/{id}/reject` | Terminal |
| GET | `/v1/admin/audit?limit=&decision=` | Newest first |
| GET | `/v1/admin/connectors/health` | Stored health |
| GET | `/v1/catalog?q=&category=&era=&adapter=&adapter_status=` | Any authenticated user |

## Operations endpoints (no auth)

`/healthz` (liveness), `/readyz` (database), `/metrics` (Prometheus), `/.well-known/oauth-protected-resource`.

## MCP

Endpoint: `/mcp` (Streamable HTTP). Auth: bearer token. Unauthenticated calls get 401 with a
`WWW-Authenticate` header that points at the protected-resource metadata.

### `chusky_list_tools()`

Returns tools the caller may use. Visible only when all of these hold: the tool is enabled, its connector
is active, the caller holds every required scope, and the tool is not a write while writes are off.

### `chusky_call_tool(connector_name, tool_name, arguments)`

| Response `status` | Meaning |
|---|---|
| `success`, `completed`, `committed`, `sent` | Ran. Other fields depend on the adapter |
| `pending_approval` | Waiting for a reviewer; includes `approval_id` |
| `truncated` | Result too large; narrow the request |
| `error` | Refused or failed; `message` explains without internals |

Arguments are validated against the tool's `input_schema`. Unknown keys are refused.

## Writing an MCP client

An agent client needs to:

1. Obtain a token for a user or service principal with the scopes the tools require.
2. Connect to `/mcp` with `Authorization: Bearer <token>`.
3. Call `chusky_list_tools` and cache the schemas.
4. Call `chusky_call_tool` with arguments that match the schema.
5. Handle `pending_approval` by reporting it to the user, not by retrying in a loop.
6. Send `X-Request-ID` when it wants its calls correlated with server logs.

## Example call sequence

```
→ chusky_list_tools()
← {"tools": [{"connector": "oracle_ebs_orders", "tool": "get_order_status", ...}], ...}
→ chusky_call_tool("oracle_ebs_orders", "get_order_status", {"order_number": "SO-10023"})
← {"status": "success", "operation": "get_order_status", "row_count": 1, "rows": [...]}
```

Write example:

```
→ chusky_call_tool("sap_s4_sales", "create_sales_order", {...})
← {"status": "pending_approval", "approval_id": "3f1c...", "message": "A reviewer must approve this action before it runs."}
```
