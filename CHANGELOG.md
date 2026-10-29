# Changelog

All notable changes are recorded here. The project follows semantic versioning.

## 1.0.0

First release under the name Chusky Bridge (formerly BridgeOS).

- Renamed the package to `chusky_bridge`, the CLI to `chusky-bridge`, and all environment variables to the `CHUSKY_` prefix.
- Adapters: `odbc`, `sql_server`, `postgres`, `rest`, `odata`, `fhir`, `soap`, `sftp`, `kafka`, `sap_rfc` (with approval-gated writes), `ibm_mq`, `rabbitmq`, `queue_gateway` (JMS and MSMQ), `tn3270`, `rpa`, `opcua`, `dicom`, `mllp`, `swift`, `modbus`.
- Secret providers: environment (development), HashiCorp Vault KV v2, AWS Secrets Manager.
- Mutual TLS for HTTP-based adapters, from an approved certificate directory.
- Redis-backed rate limiting for multi-replica deployments.
- Structured JSON logs with request IDs, Prometheus metrics, `/healthz`, `/readyz`, and `/metrics`.
- Alembic migrations with an initial schema.
- Connector health and enable/disable endpoints.
- System catalog of 180+ named products.
- CI: lint, format, tests, manifest validation, migration rendering, and image build.
- Agent skill and reference documentation under `skills/` and `docs/`.

## 0.x (BridgeOS)

Internal prototypes: the core policy engine, approval flow, audit log, MCP server, and the first SQL, REST, and SFTP adapters.
