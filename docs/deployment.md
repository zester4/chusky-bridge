# Deployment

## Reference topology

```
            ┌────────────────┐
 agents ───►│ TLS gateway /  │
            │ load balancer  │
            └───────┬────────┘
                    │  (internal, https)
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   chusky-api   chusky-api   chusky-api        chusky-worker (health sweep)
        │           │           │                      │
        └───────────┴─────┬─────┴──────────────────────┘
                          ▼
                  PostgreSQL (managed, backed up)
                  Redis (optional, rate limiting)
                          │
         ┌────────────────┼──────────────────┐
         ▼                ▼                  ▼
   Vault / AWS SM    Target systems     Connectivity gateways
                     (DB, REST, SOAP,   (JMS/MSMQ, SWIFT,
                      SFTP, MQ, OT)      FHIR OAuth refresher)
```

- Run the API as at least two replicas across availability zones.
- Keep `/metrics` on an internal listener or behind network policy. The public gateway must not route it.
- Mount WSDLs read-only at `CHUSKY_WSDL_DIR` and certificates read-only at `CHUSKY_CERT_DIR`.

## Container image

The image is built from `Dockerfile`, runs as a non-root user (uid 10001), and includes a health check on `/healthz`.

```bash
docker build -t chusky-bridge:1.0.0 .
docker run --env-file .env -p 8000:8000 chusky-bridge:1.0.0
```

The base image omits vendor drivers. Build a derived image for each deployment that needs them:

```dockerfile
FROM chusky-bridge:1.0.0
USER root
RUN apt-get update && apt-get install -y unixodbc odbcinst && rm -rf /var/lib/apt/lists/*
# Install the vendor driver here (Microsoft ODBC 18, IBM i Access, Oracle Instant Client, and so on).
RUN pip install ".[odbc,mq,industrial]" --no-cache-dir
USER chusky
```

Install vendor drivers with the vendor's license terms. Do not commit them to a public image.

## Database

1. Create a PostgreSQL 14 or later database and a role that owns it.
2. Apply migrations before the first start and before each release:

   ```bash
   alembic upgrade head
   ```

   Run the migration as a separate job, not from every replica.
3. Enable automated backups and point-in-time recovery. The audit table is part of your evidence.
4. Keep the Bridge role out of other schemas and deny it superuser rights.

Development may use `CHUSKY_ENV=development`, where the API creates tables at startup. Do not use that in production.

## Secrets

| Environment | Provider | Notes |
|---|---|---|
| Development | `env` | `CHUSKY_SECRET_<REF>` in a local `.env`. Never commit it |
| Staging | `vault` or `aws` | Same as production with a separate namespace or account |
| Production | `vault` or `aws` | Enforced at startup. Use IAM or Vault policies that grant read access to the `chusky/` prefix only |

Rotate each secret on a schedule. Rotation is a value change in the store; no manifest change is needed.
Restart or wait for the next call, since connectors load their secrets per call.

## Identity provider

- Register Chusky Bridge as an API audience. Set `CHUSKY_JWT_AUDIENCE` to that audience.
- Put `tenant_id` (UUID), `sub`, and `scope` in access tokens. Name the admin scope `chusky.admin`.
- Restrict token lifetime to what your security policy requires (for example 15 minutes for user tokens).
- Use short-lived tokens for agents. Revoke them when an agent is decommissioned.

## Optional drivers

| Extra | Needs on the runtime |
|---|---|
| `odbc` | unixODBC and the vendor ODBC driver |
| `sap` | SAP NW RFC SDK (licensed from SAP) |
| `mq` | IBM MQ client libraries (for `ibm_mq`); pika needs no native libraries |
| `industrial` | None beyond Python packages |
| `dicom` | None beyond Python packages |
| `rpa` | Windows runtime with UI Automation |
| `tn3270` | x3270 binary |
| `redis` | Redis reachable from the API |
| `aws` | AWS credentials through the instance or pod role |

## Networking

- Allow egress from the Bridge only to the systems in your manifests, on the ports those manifests use.
- Use dedicated subnets for OT adapters (Modbus, OPC UA, MLLP) with explicit allow rules.
- Pin SFTP host keys, and verify them against a trusted source before you set them.

## Production checklist

- [ ] `CHUSKY_ENV=production`, and startup succeeds (`chusky-bridge check-config`)
- [ ] Vault or AWS provider configured; no `CHUSKY_SECRET_*` variables in the environment
- [ ] `CHUSKY_PUBLIC_BASE_URL` is https
- [ ] Migrations applied; backups verified with a test restore
- [ ] `CHUSKY_ENABLE_WRITE_TOOLS=false` until the approval flow has been tested end to end in production
- [ ] Rate limiting set to `redis` if running more than one replica
- [ ] `/metrics` not reachable from outside
- [ ] Log shipping configured; `denied` and `error` decisions alert
- [ ] Each connector's health check passes; each read tool called once in production with a test record
- [ ] Read-only database accounts confirmed
- [ ] SFTP host keys pinned; WSDL endpoints allowlisted; mutual TLS certificates installed
- [ ] Penetration test of `/mcp` and the admin API scheduled before go-live
- [ ] Runbook reviewed by the on-call team ([operations.md](operations.md))
