# ADR 0002: Agents call named operations, never access systems

**Status:** accepted

## Context

Giving an agent a SQL client, an HTTP proxy, or a terminal session would make every enterprise system a
prompt-injection target. A single compromised prompt could read or write anything the credential can.

## Decision

Every upstream interaction is a named operation declared in a reviewed manifest. Each operation has a
closed input schema, fixed upstream targets, and bound parameters. Adapters refuse any input that would
name a host, URL, SQL, procedure, node ID, terminal key, or path outside their configuration.

## Consequences

- Reviews and audits focus on a finite, named set of operations.
- Adding a new capability requires a manifest change and a review, which is intended.
- Some legitimate use cases need a new operation rather than a free-form query. That cost is accepted.
