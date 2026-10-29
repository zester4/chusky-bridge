# Testing and CI

## The suite

- Location: `tests/`. Run `pytest -q`.
- The suite needs no database, no network, and no vendor driver. Adapters are tested through fakes.
- `tests/conftest.py` sets the minimum settings so modules import without a server.

| File | Covers |
|---|---|
| `test_policy.py` | Policy decisions |
| `test_approval_flow.py` | Approval state machine and self-approval |
| `test_tool_registry.py` | Manifest parsing, hashing, schema generation |
| `test_odbc_validation.py` | SQL validator and placeholder binding |
| `test_sql_connector.py` | Stored procedure adapter |
| `test_odata.py`, `test_fhir.py` | Filter escaping, resource allowlists |
| `test_safe_http.py` | SSRF rules, path encoding |
| `test_soap.py`, `test_sftp.py` | WSDL and host-key rules |
| `test_parsers.py` | CSV, fixed-width, XML, X12, HL7 |
| `test_sap_rfc.py` | Writes, commit, rollback |
| `test_mllp_mq_queue.py` | MLLP framing and escaping, IBM MQ, RabbitMQ, queue gateway |
| `test_terminal_ui_industrial.py` | 3270, RPA, OPC UA, DICOM, Modbus |
| `test_swift_observability_cli.py` | SWIFT rules, JSON logs, CLI, migrations render |
| `test_files_vault_config.py` | File approval, secret providers, production config |
| `test_redis_ratelimit.py`, `test_ratelimit.py` | Rate limiting |
| `test_catalog_and_templates.py` | Catalog integrity and every template validates |

## Patterns

Fake a library imported at call time:

```python
def test_something(monkeypatch):
    fake = types.ModuleType("pymqi")
    ...
    monkeypatch.setitem(sys.modules, "pymqi", fake)
```

Inject a client through a constructor seam:

```python
connector = ModbusConnector({...}, client_factory=lambda cfg: FakeClient())
```

Replace a method on an instance for HTTP:

```python
connector.http.request = lambda method, path, **kw: (200, "application/json", b"[]")
```

Test that a refusal happens, and that its message does not leak:

```python
with pytest.raises(ConnectorError, match="not allowed"):
    Adapter.validate_operation(...)
```

## Lint and format

```bash
ruff check .
ruff format --check chusky_bridge tests    # fix: ruff format chusky_bridge tests
```

Rules: E, F, W, I, B, UP, SIM. Ignored: B008 (FastAPI dependency defaults), UP007.

## CI (`.github/workflows/ci.yml`)

1. Install with `pip install -e ".[dev]"`.
2. `ruff check .` and `ruff format --check`.
3. `pytest -q`.
4. `chusky-bridge validate connectors_manifests/templates`.
5. `alembic upgrade head --sql` renders DDL offline.
6. Build the Docker image (after tests pass).

## Adding tests to CI

Add the check to `.github/workflows/ci.yml`, run it locally first, and keep it fast. A slow check goes in a separate, scheduled job.

## Lab tests (not in CI)

Adapters that depend on a vendor product must be tested against a lab instance before production:
`odbc` drivers, `sap_rfc`, `ibm_mq`, `tn3270`, `rpa`, `opcua`, `dicom`, `mllp`, `swift`, `modbus`.
Record the result in the catalog entry or the adapter's documentation with the product version and date.
