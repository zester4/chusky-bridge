# ADR 0005: Every adapter validates its operations at registration

**Status:** accepted

## Context

Runtime checks alone let unsafe manifests become active until someone calls the tool. A problem found
during an incident is worse than a problem found during review.

## Decision

`validate_operation` runs for every operation when a manifest is registered, and in CI through
`chusky-bridge validate`. Runtime checks remain as a second layer. A manifest that fails validation is
never stored, so it cannot activate.

## Consequences

- Authors get precise errors early, and reviewers see the same checks the server runs.
- Adapters with dynamic behavior (for example a WSDL loaded at runtime) still need runtime checks. Both layers are kept.
