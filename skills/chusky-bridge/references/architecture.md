# Architecture reference

Use this to find the right module before changing code.

## Request path for a tool call

```
chusky_list_tools / chusky_call_tool        chusky_bridge/mcp/server.py
  └─ identity from mcp_auth middleware       chusky_bridge/main.py, auth.py
      └─ execute_tool                        chusky_bridge/mcp/tool_executor.py
          1. load connector (active, tenant) and tool (enabled)
          2. validate arguments (jsonschema, closed)
          3. rate limit (tenant, connector, tool, user)
          4. evaluate_tool_policy            chusky_bridge/policy.py
          5a. pending: create ApprovalRequest  chusky_bridge/approvals.py
          5b. run: build_connector → adapter.execute
              chusky_bridge/connectors/__init__.py
          6. redact and bound the result     chusky_bridge/redaction.py
          7. audit + metrics                 chusky_bridge/audit.py, observability.py
```

## Where to change what

| Change | Module |
|---|---|
| A new adapter | `chusky_bridge/connectors/<name>.py` and registration in `connectors/__init__.py` |
| A shared parser | `chusky_bridge/parsers/` |
| What a manifest may contain | `chusky_bridge/mcp/manifest.py` (common fields) and the adapter's `validate_operation` (specific fields) |
| How tools are generated and versioned | `chusky_bridge/mcp/tool_registry.py` |
| Authorization rules | `chusky_bridge/policy.py` (pure function, unit-tested) |
| Approval behavior | `chusky_bridge/approvals.py`, `chusky_bridge/api/approvals.py` |
| Token validation | `chusky_bridge/auth.py` |
| Secret providers | `chusky_bridge/vault.py` |
| Files allowed for WSDLs and certificates | `chusky_bridge/files.py` |
| Rate limits | `chusky_bridge/ratelimit.py` |
| Logs and metrics | `chusky_bridge/observability.py` |
| Settings | `chusky_bridge/config.py` (every field is `CHUSKY_<NAME>`) |
| Tables | `chusky_bridge/models.py` plus a new migration in `migrations/versions/` |
| Admin HTTP surface | `chusky_bridge/api/*.py` |
| Named-system catalog | `systems/catalog.yaml` and `chusky_bridge/catalog.py` |
| CLI | `chusky_bridge/cli.py` |
| Startup manifest loading and health | `chusky_bridge/workers/` |

## Data model

- `tenants`: isolation boundary.
- `connectors`: manifest JSON, its hash, status (`active` or `disabled`), last health result.
- `tool_definitions`: one row per operation, with `definition_hash` and `version`. A change disables the tool.
- `approval_requests`: arguments, tool version, requester, approver, status, expiry.
- `audit_events`: one row per decision, with redacted arguments.

## Key invariants in code

- `BaseConnector.validate_operation` is a classmethod called at registration with the full connection.
- `BaseConnector.execute` receives only operations from the stored manifest and arguments that already passed the schema.
- `build_connector` is called per call. Secrets are resolved per call.
- `execute_approved` claims the approval row under `SELECT ... FOR UPDATE` before running.

## Dependencies by role

- Core: FastAPI, SQLAlchemy, Alembic, Pydantic Settings, PyJWT, httpx, jsonschema, sqlglot, zeep, paramiko, defusedxml, kafka-python-ng, prometheus-client, mcp (v1 line).
- Optional drivers are imported inside methods, so the core imports without them: `pyodbc`, `pyrfc`, `pymqi`, `pika`, `pymodbus`, `opcua`, `pynetdicom`, `pydicom`, `pywinauto`, `py3270`, `redis`, `boto3`.
