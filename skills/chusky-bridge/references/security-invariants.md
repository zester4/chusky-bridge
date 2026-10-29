# Security invariants

These must hold after every change. A change that breaks one needs a security review and an ADR.
Each invariant names the code that enforces it and the test that proves it.

## I1. Agents cannot choose the upstream target

Hosts, URLs, SQL statements, procedure names, function names, node IDs, terminal keys, screen fields,
Modbus addresses, Kafka topics, and queue names come from the manifest, never from arguments.

- Enforced by: each adapter's `execute` reads targets from `self.config` or the operation; arguments are used only as values.
- Tests: `test_kafka.py::test_topic_outside_allowlist_refused`, `test_mllp_mq_queue.py::test_rabbitmq_queue_allowlist_enforced`, `test_terminal_ui_industrial.py::test_unlisted_aid_key_rejected_at_registration`.

## I2. Secrets never leave the secret store boundary

Values are resolved per call, placed in the adapter's config, and used for authentication only.

- Enforced by: `vault.py`, `build_connector`, `redaction.redact`, `_run` (returns only redacted results).
- Tests: `test_files_vault_config.py` (provider behavior); `test_terminal_ui_industrial.py::test_transaction_fills_reads_and_hides_secret`.
- Check: a secret-looking key anywhere in a result is replaced with `[REDACTED]`.

## I3. Every call has exactly one final audit decision

Decisions: `executed`, `denied`, `pending_approval`, `error`. Every early return and exception path writes one.

- Enforced by: `execute_tool` and `execute_approved` in `mcp/tool_executor.py`.
- Review: when you add a branch to the executor, add its audit call.

## I4. Writes run once, after approval, by someone else

- The approval is bound to `tool.version`. A change to the operation invalidates it.
- `claim_for_execution` locks the row and transitions `approved` to `executed` once.
- `assert_can_decide` blocks self-approval.
- Tests: `test_approval_flow.py`.

## I5. Reads cannot write

- `read_only` operations are refused at registration if they click, type, press keys, send, or write.
- Enforced by: `RpaConnector.validate_operation`, `OdbcConnector.validate_operation` (SELECT only), `SapRfcConnector` (write path requires approval), `IbmMqConnector` (browse only), `RabbitMqConnector` (peek only), `DicomConnector` (C-FIND only), `ModbusConnector` (read only), `OpcUaConnector` (read only).

## I6. Production never starts insecure

- `require_server_config`: production refuses the `env` provider and non-https public URLs.
- Tests: `test_files_vault_config.py::test_production_*`.

## I7. Unsafe manifests never activate

- Every adapter validates its operations at registration. The CLI and CI run the same checks.
- Tests: adapter test modules, one per rule.

## I8. Inputs are bounded

- Schema validation with `additionalProperties: false`.
- Byte caps: HTTP, SFTP, MLLP, tool results (`CHUSKY_MAX_TOOL_RESPONSE_BYTES`).
- Row caps: `max_rows`, `max_messages`, `_count` for FHIR.
- Timeouts on every network operation.

## I9. Outbound network is pinned and allowlisted

- HTTP: https origin pinned; redirects off; private addresses refused unless explicitly allowed.
- SOAP: WSDL from an approved directory; every endpoint host allowlisted.
- SFTP: host key pinned, compared in constant time.
- DICOM: host in `allowed_hosts`.
- Tests: `test_safe_http.py`, `test_sftp.py`, `test_soap.py`.

## I10. Files are read only from approved directories

- `files.resolve_approved_file` refuses absolute paths, `..`, and symlink escapes.
- Used for WSDLs, mTLS certificates, CA bundles, and OPC UA certificates.
- Tests: `test_files_vault_config.py::test_escapes_are_refused`, `test_symlink_escape_refused`.

## I11. Inputs cannot inject protocol syntax

- SQL: sqlglot-validated single SELECT; values bound.
- HL7: values escaped; control characters refused.
- 3270: values must be printable and fit the field.
- OData: string literals with quotes doubled.
- Path segments: percent-encoded as single segments.

## I12. Errors are generic to callers

- Adapters raise `ConnectorError` with short text and chain the cause with `from exc`.
- Tool results carry `message`, never a traceback.

## I13. Weak transports are opt-in and visible

- Plaintext MLLP and terminal connections need `allow_plaintext: true`.
- OPC UA refuses `None` security.
- Modbus has no authentication: documented as needing a segregated network.

## Review checklist for any change

- [ ] Does any new code path accept a target from arguments? (I1)
- [ ] Can a secret reach a result, log line, error message, or audit row? (I2)
- [ ] Does every branch write exactly one audit decision? (I3)
- [ ] Can a write run without approval, or twice? (I4)
- [ ] Can a read-only operation change anything? (I5)
- [ ] Does validation run at registration as well as at runtime? (I7)
- [ ] Is every new input bounded in size and time? (I8)
- [ ] Is every new outbound destination pinned or allowlisted? (I9)
- [ ] Is every new file read from an approved directory? (I10)
- [ ] Is every new value escaped for its protocol? (I11)
