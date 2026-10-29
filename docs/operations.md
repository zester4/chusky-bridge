# Operations runbook

Routine and incident procedures for on-call and platform operators. Replace `$API` with the internal
base URL and `$TOKEN` with an admin token.

## Daily

- Check the dashboard for error rate, `denied` decisions, and p95 latency per adapter (`chusky_tool_call_seconds`).
- Review `pending_approval` requests older than one hour: `GET /v1/approvals?status=pending`.
- Check connector health: `GET /v1/admin/connectors/health`. Investigate anything other than `healthy`.

## Weekly

- Review `denied` audit events for patterns: repeated scope failures, unknown tools, rate limits.
- Review enabled tools against the current business need. Disable anything unused.
- Confirm backups restore in the staging environment.

## Monthly

- Rotate service credentials for connectors that the policy requires.
- Review the approval log: who approved what, and whether approvers were independent.
- Review the catalog entries you have verified and re-test one per adapter type.

## Common tasks

### Register or update a connector

```bash
curl -s -X POST $API/v1/connectors -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"manifest_yaml\": $(python -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' manifest.yaml)}"
```

Updating an operation disables its tool until someone re-enables it. Expect that, and tell the
business owner.

### Disable a connector immediately

```bash
curl -s -X POST $API/v1/connectors/<name>/disable -H "Authorization: Bearer $TOKEN"
```

Disabling stops every tool call to the connector at once. It does not change tool states, so
`enable` restores them.

### Turn writes on for a tenant

Writes are controlled platform-wide by `CHUSKY_ENABLE_WRITE_TOOLS`. Changing it requires a
redeploy. Enable it only after the approval flow has been verified in production.

### Approve a pending action

```bash
curl -s -X POST $API/v1/approvals/<id>/approve -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"reason": "Ticket CHG-1234"}'
```

Record the change ticket in `reason`. Approving runs the action once. A second approve call returns
`409`.

### Reject a pending action

```bash
curl -s -X POST $API/v1/approvals/<id>/reject -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"reason": "Not authorized"}'
```

### Investigate a specific call

Every response carries `X-Request-ID`. Search the logs for that ID, then the audit table:

```bash
curl -s "$API/v1/admin/audit?limit=50&decision=error" -H "Authorization: Bearer $TOKEN"
```

Logs are JSON lines with `request_id`, `level`, and `message`.

### Rotate a secret

1. Create the new credential in the target system. Keep the old one valid.
2. Write the new value to Vault (`secret/chusky/<ref>`, field `value`) or AWS (`chusky/<ref>`).
3. Run the connector's health check: `POST /v1/connectors/<name>/health`.
4. Revoke the old credential in the target system.

No restart is needed. Connectors read their secrets on each call.

### Rotate the admin or identity signing keys

Identity provider keys rotate in the provider. The Bridge caches JWKS through PyJWT's key client and
picks up new keys on the next unknown `kid`. Confirm after rotation with a fresh token.

### Add a system safely

Follow [connecting-a-system.md](connecting-a-system.md). Never add a system directly to production
without a non-production run.

## Incidents

### Suspected credential exposure

1. Disable the affected connectors: `POST /v1/connectors/<name>/disable`.
2. Rotate the affected secrets (see above) and revoke the old ones at the source.
3. Pull the audit trail for the window: `GET /v1/admin/audit`. Export it from the database.
4. Check the logs for the secret value. A match means a redaction bug: treat it as a security defect and file a report under SECURITY.md.
5. Revoke tokens of the agents involved and review their tool access.

### Unauthorized write suspected

1. Disable write tools at the platform level by setting `CHUSKY_ENABLE_WRITE_TOOLS=false` and redeploying.
2. Pull `executed` audit events with `approval_id` values. Compare each approval's approver and requester.
3. Work with the owner of the target system to confirm the state of the data.
4. Open an incident record. Preserve the database state before any correction.

### Upstream system outage

Symptoms: `error` decisions with `upstream` messages, rising latency, health `unhealthy`.

1. Confirm the system is down (not the network path): run the health check and check the target's status page.
2. Leave the connector active. Tool calls fail fast and the audit trail stays complete.
3. Tell the agent owners which tools are unavailable.
4. When the system recovers, rerun the health check.

### Bridge overload

Symptoms: elevated latency, `rate limit exceeded` decisions from one caller.

1. Identify the caller from the audit log. Confirm whether the traffic is legitimate.
2. Reduce that caller's scope or revoke its token if the traffic is not expected.
3. If the load is legitimate, add replicas. Switch to `CHUSKY_RATE_LIMIT_BACKEND=redis` for consistent limits across replicas.

### Database unavailable

`/readyz` returns `503`. The load balancer removes the instance from rotation. Restore the database
or fail over, then confirm `/readyz` returns `200`. Calls during the outage fail; nothing is
executed without an audit record, because the audit write must succeed for the call to complete in
the executor path.

## Backup and restore

- The PostgreSQL database holds tenants, connectors, tool definitions, approvals, and the audit log.
- Secrets live in Vault or AWS, backed up by that system. They are not in the database.
- Restore to a staging database, run `alembic current` to confirm the revision, and then run `/readyz`.

## Maintenance windows

- Connector edits during a window are safe. Disabling connectors during a target system's maintenance avoids noisy errors.
- Migrations run before the new version is deployed. Migrations must be backward compatible for one release.
