---
name: chusky-bridge
description: Build, extend, operate, and use Chusky Bridge, a governed MCP gateway that exposes reviewed operations over legacy and modern enterprise systems (databases, REST, OData, SOAP, SAP, FHIR, HL7, DICOM, SFTP, Kafka, IBM MQ, RabbitMQ, 3270/5250, desktop RPA, OPC UA, Modbus, SWIFT). Use when adding a system or adapter, writing or validating a manifest, changing policy, approvals, secrets, migrations, or deployment, answering how the Bridge works, or reviewing a change for security.
---

# Chusky Bridge

Chusky Bridge lets AI agents call named, reviewed operations on enterprise systems through MCP.
An agent never gets a connection string, a SQL prompt, a terminal, or a URL. It gets tools.

Read this file first. Load a reference only when the task needs it.

| Task | Reference |
|---|---|
| Understand how the code is organized | [references/architecture.md](references/architecture.md) |
| Pick or configure an adapter | [references/adapters.md](references/adapters.md) |
| Write or review a manifest | [references/manifest-authoring.md](references/manifest-authoring.md) |
| Add a new adapter | [references/adding-an-adapter.md](references/adding-an-adapter.md) |
| Check a change against security rules | [references/security-invariants.md](references/security-invariants.md) |
| Run, deploy, or respond in production | [references/operations-runbook.md](references/operations-runbook.md) |
| Write or run tests and CI | [references/testing-and-ci.md](references/testing-and-ci.md) |
| Call the API or the MCP tools | [references/api-and-mcp.md](references/api-and-mcp.md) |

## Non-negotiable rules

1. **Operations, not access.** Every upstream interaction is a named operation with a closed input schema, fixed targets, and bound parameters. Never add a feature that lets a caller choose a host, URL, SQL statement, procedure name, node ID, keystroke, or file path outside an approved root.
2. **Secrets by reference.** Manifests hold `secret_ref` names. Values come from Vault or AWS Secrets Manager. Never write a credential into a manifest, test fixture, log line, result, or audit row.
3. **Writes need approval.** A write sets `read_only: false` and `requires_approval: true`. High-risk operations require approval. Do not weaken this to make a test pass.
4. **Validate at registration.** Every adapter's `validate_operation` must reject unsafe manifests before they are stored. Runtime checks are a second layer, not a substitute.
5. **Fail closed.** Unknown actions, unknown fields, unknown adapters, and unparseable input are refused.
6. **Generic errors to callers.** Adapters return short, safe messages. Driver text, SQL text, SOAP faults, and stack traces stay in the logs, and only if they carry no secrets.
7. **Tests with every rule.** A new rule needs a test that fails without it.

## Workflow for any change

1. Read the relevant reference. Read the code it names.
2. Write or update the test that states the behavior. Run it and watch it fail.
3. Make the smallest change that passes. Keep validation next to the adapter it protects.
4. Run the full check:

   ```bash
   ruff check . && ruff format --check chusky_bridge tests
   pytest -q
   chusky-bridge validate connectors_manifests/templates
   CHUSKY_DATABASE_URL=postgresql://offline/offline alembic upgrade head --sql >/dev/null
   ```

5. Update docs in the same change: `docs/` for behavior, `CHANGELOG.md` for user-visible change, an ADR in `docs/adr/` for any new decision that changes a rule above.
6. If the change alters a security rule, update `references/security-invariants.md` and `docs/security-model.md` together.

## Decision guide: which adapter

- A database with published views or procedures: `odbc` (any ODBC database) or `sql_server` (procedures only) or `postgres` (functions only).
- A web service with JSON or OData: `rest`, `odata`, `fhir` (for clinical FHIR), or `swift` (SWIFT gateway).
- A WSDL service: `soap`. Put the WSDL in the approved directory first.
- Files produced on a schedule: `sftp` with the right `format`.
- A message stream you can read from an offset: `kafka`. A queue you can browse: `ibm_mq`, `rabbitmq`, or `queue_gateway` for JMS and MSMQ.
- An SAP system: `sap_rfc`.
- HL7 v2 query and reply: `mllp`. Study-level PACS lookup: `dicom`.
- A 3270 or 5250 screen flow: `tn3270`. Last resort, a Windows application with no other route: `rpa`.
- Plant data: `opcua` for OPC UA servers, `modbus` for Modbus devices.

If none fits, do not invent a generic "any system" adapter. Write a new adapter with a clear contract and an ADR.

## Common mistakes to avoid

- Using `query` as a parameter name. It collides with the forbidden argument-key list. Use `search_text` or a specific name.
- Setting `read_only: true` on an operation that writes. The write is not blocked by the flag alone; the flag is a declaration that the policy and the adapter both rely on.
- Pinning a host key from a `ssh-keyscan` you did not verify. Verify the fingerprint through the system owner.
- Adding `allow_private_network: true` to make a test pass. Justify it in the manifest comment and in the change record.
- Editing an applied migration. Add a new one.
- Caching a secret in process memory for longer than a call. The design relies on per-call resolution so rotations take effect.
