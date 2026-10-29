# Adding an adapter

Add an adapter only when no existing one can reach the system safely. Each adapter is a
security boundary, so the bar is high.

## Before you start

- Confirm a transport is not already covered by an existing adapter (see the table in `references/adapters.md`).
- Write a short ADR in `docs/adr/` if the adapter introduces a new kind of upstream access.
- Identify the client library. Prefer a maintained, widely used library. Check its license.
- Decide the read-only and write story. Reads are the default. Writes need approval, an explicit commit or rollback, and a test that proves the rollback path.

## Steps

### 1. Create the module

`chusky_bridge/connectors/<type>.py`:

```python
from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers


class ExampleConnector(BaseConnector):
    connector_type = "example"          # the manifest "type"
    secret_field = "api_key"            # where the resolved secret is placed, or None

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "read":
            raise ConnectorError(f"{name}: example mode must be 'read'")
        validate_identifiers(op.get("parameters", []), "parameter")
        # Every rule that protects the upstream lives here, and each one gets a test.

    def health_check(self) -> dict[str, Any]:
        ...                              # touch the system without side effects
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)  # unknown operations raise here
        require_arguments(op.get("parameters", []), arguments)
        ...                              # bind values; never format them into commands
        return {"status": "success", "operation": operation, "rows": [...]}
```

### 2. Follow the rules

- **Client libraries are imported inside methods**, so the core package imports without them. Raise `ConnectorError("... is not installed")` when the import fails.
- **Targets come from the connection.** Never accept a host, URL, path, or identifier from arguments unless it is checked against an allowlist.
- **Bind, do not format.** Use the driver's parameter binding. Use `encode_segment` for path segments. Use `hl7_escape` for HL7.
- **Bound everything.** Timeouts, row counts, byte counts, and recursion depth.
- **Errors are generic.** Wrap driver exceptions: `raise ConnectorError("operation failed upstream") from exc`. The `from exc` keeps the cause for debugging without showing it to the caller.
- **Never log or return secrets.** Check that your `repr` and error messages do not include the connection config.
- **Reads cannot write.** A `read_only` operation must not send a write, press a key, click, or type.

### 3. Register it

In `chusky_bridge/connectors/__init__.py`, import the class and add it to the tuple that builds `REGISTRY`. The registry key is the class's `connector_type`. Check that `IMPLEMENTED_TYPES` now includes it.

Add a catalog entry or update one in `systems/catalog.yaml`. Set `adapter:` to the new type.

### 4. Write tests

Create `tests/test_<type>.py`. Cover:

- Each `validate_operation` rule: one test per refusal, plus one test that a valid operation passes.
- `execute` against a fake client: happy path, missing argument, unknown operation, upstream failure, oversize response.
- The security property: an injected value cannot change the target; a secret never appears in results or error text.
- For writes: approval is required at registration; the commit and rollback paths.

Inject the client through one of the seams in `docs/development.md`.

### 5. Add a template

`connectors_manifests/templates/<type>_<purpose>.yaml`, with `status: template` and comments for each placeholder. CI validates it.

### 6. Document

- `docs/adapters.md`: a section with purpose, mode, safety, secret, requirements, and verification level.
- `docs/manifest-reference.md`: the adapter-specific fields table.
- `skills/chusky-bridge/references/adapters.md`: one row.
- `docs/system-coverage.md`: the products it reaches.
- `CHANGELOG.md`: under the next version.

### 7. Verify

```bash
ruff check . && ruff format --check chusky_bridge tests
pytest -q
chusky-bridge validate connectors_manifests/templates
```

State the verification level honestly in `docs/adapters.md`. Unit-tested against fakes is the minimum. Mark lab verification as required when the protocol or vendor behavior is not fully testable here.

## Review checklist

- [ ] No arguments control the upstream target
- [ ] Every rule in `validate_operation` has a test
- [ ] Driver exceptions are wrapped with generic messages
- [ ] No secret in results, errors, logs, or repr
- [ ] Writes require approval; rollback path tested
- [ ] Timeouts and size limits set
- [ ] Optional import fails with a clear message
- [ ] Template validates; docs and catalog updated
