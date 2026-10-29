# Troubleshooting

## Startup

**`RuntimeError: missing required configuration: database_url, ...`**
The server needs `CHUSKY_DATABASE_URL`, `CHUSKY_JWT_JWKS_URL`, and `CHUSKY_JWT_ISSUER`. Run `chusky-bridge check-config`.

**`RuntimeError: production requires CHUSKY_SECRET_VAULT_PROVIDER=vault or aws`**
Production refuses environment-variable secrets. Configure Vault or AWS.

**`RuntimeError: production requires an https CHUSKY_PUBLIC_BASE_URL`**
Set the public URL to the https address that clients use.

**`/readyz` returns 503**
The database does not answer `SELECT 1`. Check the URL, the network path, credentials, and that migrations were applied. The logs show the connection error type without the URL.

**Migration fails with `relation already exists`**
The database was created by `create_all` in development. Stamp it instead of migrating: `alembic stamp 0001_initial`.

## Manifests

**`422 invalid manifest: ...`**
Read the message. Common causes:

| Message | Fix |
|---|---|
| `inline secrets are not allowed in connection` | Remove the password or key; use `secret_ref` |
| `write operations must set requires_approval: true` | Add `requires_approval: true` to the write |
| `only SELECT statements are allowed` | The query is not a single SELECT. Expose a read-only view |
| `query placeholders must match declared parameters exactly` | Make the `:names` in `query` and `parameters` identical |
| `invalid procedure name` | Use `schema.name` with letters, digits, and underscores |
| `WSDL file not found in the approved WSDL directory` | Place the WSDL in `CHUSKY_WSDL_DIR` and use only its file name |
| `SFTP connections must pin host_key_sha256` | Pin the fingerprint (see below) |
| `TLS is required` | Set `tls: true`; use `allow_plaintext` only in a lab |
| `template manifests cannot be activated` | Set `connector.status: active` after discovery |
| `connector type 'x' is not implemented` | Check the spelling against [adapters.md](adapters.md) |

**Pinning an SFTP host key**

```bash
ssh-keyscan -t ed25519 sftp.example.internal 2>/dev/null | ssh-keygen -lf -E sha256 -
```

Compare the fingerprint with the value the system owner gives you through a second channel, then use
the `SHA256:...` string in `host_key_sha256`.

## Tool calls

**`tool not found or not approved`**
One of: the connector does not exist in your tenant, the connector is disabled, the tool is not
enabled, or the name is wrong. The message is deliberately general. Check `GET /v1/tools`.

**`invalid arguments at <field>`**
The arguments fail the tool's input schema. Look at the tool's `input_schema` in `chusky_list_tools`.

**`missing scopes: [...]`**
The caller's token lacks the scopes. Grant them in the identity provider. Do not add them to the tool.

**`pending_approval`**
The operation writes or is high risk. A reviewer must approve it. This is expected.

**`approved_not_executed` with a reason**
The approval succeeded but the action was not run, because the tool changed or was disabled after
approval. Request the action again.

**`rate limit exceeded; retry later`**
The caller hit the per-minute limit for that tool. Retry after a minute. If the limit is too low for
legitimate use, raise `CHUSKY_RATE_LIMIT_PER_MINUTE`.

**`upstream request failed`, `database connection failed`, `... connection failed`**
The adapter could not reach the target. Run the connector's health check. Check the network path, the
credentials, and that the target is up. The message is generic by design; the audit row and logs hold the
adapter-level reason.

**`connector credentials are not configured`**
The secret reference does not resolve. Check the secret name and provider. Run the health check.

**`SAP rejected the change; nothing was committed`**
The BAPI returned an error message. The RETURN table of the result explains it. The change was rolled back.

**`expected screen marker not found at step N` (tn3270)**
The terminal is not where the manifest expects. The screen changed, or a previous step failed. Check
the screen flow with the system owner and update the expect text.

**`value contains characters that cannot be typed on a 3270 screen`**
The value includes control characters or non-ASCII text. Clean the input at the caller.

**`WSDL endpoint host is not in the allowlist`**
The WSDL points to a host you have not allowlisted. Confirm the host with the service owner, then add
it to `allowed_hosts`. Do not add hosts you have not verified.

**`upstream host resolves to a non-public address`**
The REST host resolves to a private address. If the service is legitimately internal, set
`allow_private_network: true` for that connector and document why.

## Adapters

**`... is not installed`**
The optional driver is missing from the runtime. Install the matching extra (for example `".[mq]"`) or
build the derived image in [deployment.md](deployment.md).

**OPC UA: `OPC UA session could not be established`**
Check the endpoint URL, the security policy and mode the server offers, trust of the client certificate on the server, and the certificate's validity.

**SFTP: `SFTP host key does not match the pinned fingerprint`**
Either the host key changed (rotation or attack) or the pin is wrong. Verify the new fingerprint through
the system owner before updating the pin. Do not update the pin blindly.

**Kafka: `kafka peek failed`**
Check broker ACLs for the read user on the topic, and that the partition and offset exist.

**DICOM: `DICOM association was rejected or timed out`**
Check AE titles on both sides (the PACS must accept the Bridge's AE title) and the port.

**MLLP: `reply could not be parsed`**
The receiver returned something that is not HL7 v2 or was truncated. Capture a sample reply with the
interface team and check the response size limit.

## Logs and metrics

- Search logs by `request_id`. Each line is JSON.
- `chusky_tool_calls_total{decision=...}` counts outcomes. A rise in `error` or `denied` is the first sign of trouble.
- `chusky_tool_call_seconds{connector_type=...}` shows upstream latency by adapter.

## When in doubt

Disable the connector (`POST /v1/connectors/<name>/disable`). Investigate with the audit log. Re-enable when the cause is understood.
