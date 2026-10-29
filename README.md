# Chusky Bridge

Chusky Bridge gives AI agents governed access to legacy and modern enterprise systems. It
exposes named, reviewed operations as Model Context Protocol (MCP) tools. Every call is
authenticated, authorized, schema-checked, rate-limited, approval-gated when it writes, and
audited.

An agent never receives a connection string, a raw SQL interface, a terminal session, or a
network address. It calls a tool such as `get_order_status` and gets back a bounded, redacted result.

## What it connects to

| Transport | Adapters | Typical systems |
|---|---|---|
| Databases | `odbc`, `sql_server`, `postgres` | Oracle, Db2 (LUW and for i), Informix, MySQL, SQL Server, PostgreSQL, Teradata, and any ODBC source |
| Web APIs | `rest`, `odata`, `fhir`, `soap`, `swift` | Salesforce, Guidewire, SAP S/4HANA, Dynamics 365, Epic, Oracle Health, PeopleSoft, Siebel, SWIFT gateways |
| Files and batch | `sftp` (CSV, fixed-width, XML, X12, HL7 v2) | Banking cores, ACH, EDI, mainframe extracts, HR exports |
| Messaging | `kafka`, `ibm_mq`, `rabbitmq`, `queue_gateway` (JMS, MSMQ) | Kafka, IBM MQ, RabbitMQ, TIBCO EMS, Windows MSMQ |
| SAP | `sap_rfc` (reads and approval-gated writes with commit and rollback) | SAP ECC, R/3, S/4HANA, SAP CRM, IS-U |
| Healthcare | `mllp` (HL7 v2 queries), `dicom` (study C-FIND), `fhir` | Interface engines, LIS, PACS, EHRs |
| Terminals and desktop | `tn3270` (3270 and 5250 screen transactions), `rpa` (desktop UI) | CICS, IMS, Unisys, legacy Windows applications |
| Industrial | `opcua`, `modbus` | PLCs, SCADA, historians, meters |

`systems/catalog.yaml` maps 180+ named products to the adapter that reaches each one. Query it with
`chusky-bridge catalog search <name>` or `GET /v1/catalog`. Catalog entries are unverified until a
connector is tested against that product and version.

## Core guarantees

- **No ambient access.** Agents call declared operations only. Parameters are bound, never interpolated.
- **Secrets by reference.** Manifests name secrets. Values come from Vault, AWS Secrets Manager, or (development only) environment variables.
- **Deny by default.** Scopes, tenant isolation, read-only defaults, and write gating are enforced server-side on every call.
- **Human approval for writes.** Writes and high-risk operations wait for a reviewer. Requesters cannot approve their own actions. Approved actions run exactly once.
- **Audit everything.** Every decision (`executed`, `denied`, `pending_approval`, `error`) is recorded with redacted arguments, and every request carries an ID that appears in the logs.
- **Bounded output.** Results are size-capped and redacted before they leave the service.

## Quick start

```bash
cp .env.example .env            # set the JWT settings for your identity provider
pip install -e ".[dev]"
chusky-bridge validate connectors_manifests/templates
docker compose up --build       # API on :8000, Postgres on :5432
```

Then register a connector, review its generated tools, enable them, and connect an MCP client to
`/mcp`. The full walkthrough is in [docs/getting-started.md](docs/getting-started.md).

## Documentation

- [Documentation index](docs/README.md)
- [Getting started](docs/getting-started.md)
- [Architecture](docs/architecture.md) and [security model](docs/security-model.md)
- [Connecting a system](docs/connecting-a-system.md)
- [Manifest reference](docs/manifest-reference.md) and [adapter reference](docs/adapters.md)
- [Configuration](docs/configuration.md), [API reference](docs/api-reference.md)
- [Deployment](docs/deployment.md), [operations runbook](docs/operations.md), [troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md) and [architecture decision records](docs/adr/)
- [Agent skill for building and extending this project](skills/chusky-bridge/SKILL.md)

## Status

Chusky Bridge 1.0 has a complete adapter set, a test suite of 186 tests, lint and migration checks in CI,
and an image build. Each adapter is tested against fakes for its client library. Live validation
against each target product is the responsibility of the team deploying it; see the verification
column in [docs/adapters.md](docs/adapters.md).

## License

Not yet specified. Set `license` in `pyproject.toml` and add a `LICENSE` file before distributing.
=======
