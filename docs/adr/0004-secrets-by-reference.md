# ADR 0004: Secrets are referenced by name and resolved at call time

**Status:** accepted

## Context

Manifests are reviewed, versioned, and sometimes shared. Credentials in them would leak into version
control, audit logs, and reviewer screenshots. Credentials in the environment are hard to rotate and
hard to scope per connector.

## Decision

- Manifests carry `secret_ref` names only. Inline secrets are refused at registration.
- Values come from a secret provider at call time: HashiCorp Vault KV v2 or AWS Secrets Manager in production. Environment variables are for development and are refused in production.
- Connectors do not cache secrets between calls, so rotation takes effect immediately.
- Secret values are never returned in results, never logged, and never stored in the audit trail.

## Consequences

- Each call reads from the secret store. Load on the store scales with tool calls. Add a short-lived cache if the store rate limits.
- A missing secret fails the call with a generic message. The operator checks the secret store.
