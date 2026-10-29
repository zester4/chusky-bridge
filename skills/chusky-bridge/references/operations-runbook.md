# Operations runbook (summary)

Full procedures: `docs/operations.md`. Troubleshooting table: `docs/troubleshooting.md`.

## Start and check

```bash
chusky-bridge check-config            # required settings and production rules
alembic upgrade head                  # migrations, before the API starts
uvicorn chusky_bridge.main:app --host 0.0.0.0 --port 8000
curl -s localhost:8000/healthz        # liveness
curl -s localhost:8000/readyz         # readiness (database)
```

## Health and state

- `POST /v1/connectors/{name}/health` runs the adapter's health check and stores the result.
- `GET /v1/admin/connectors/health` reads the stored results.
- `POST /v1/connectors/{name}/disable` stops all calls to a connector. `/enable` restores it.
- `PATCH /v1/tools/{id}` with `{"enabled": false}` stops one tool.

## Approvals

- `GET /v1/approvals?status=pending`
- `POST /v1/approvals/{id}/approve` with `{"reason": "<ticket>"}`
- `POST /v1/approvals/{id}/reject` with `{"reason": "..."}`

## Investigate

- Find the `X-Request-ID` from the caller or the response. Search JSON logs by `request_id`.
- `GET /v1/admin/audit?decision=error&limit=100`
- Metrics: `chusky_tool_calls_total{decision}` and `chusky_tool_call_seconds{connector_type}`.

## Emergency

1. Set `CHUSKY_ENABLE_WRITE_TOOLS=false` and redeploy. This stops all new writes.
2. Disable affected connectors.
3. Rotate affected secrets in the store and at the source.
4. Pull the audit trail for the window and preserve it.

## Deploy

1. Build the image from `Dockerfile` (or a derived image with drivers).
2. Run migrations as a separate job.
3. Roll out replicas; `/readyz` gates traffic.
4. Run each connector's health check and one read call per tool.
5. Keep write tools off until the approval flow has passed in production.

## Do not

- Do not set `CHUSKY_ENV=development` in production. It creates tables at startup.
- Do not put secrets in `.env` on production hosts.
- Do not expose `/metrics` publicly.
- Do not run the API as root.
