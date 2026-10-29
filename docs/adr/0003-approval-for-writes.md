# ADR 0003: Writes require approval by a second person, executed once

**Status:** accepted

## Context

An agent acting on bad or injected instructions must not be able to change business records alone.
Writes need a human decision, and that decision must be traceable.

## Decision

- Writes and high-risk operations set `requires_approval: true`. The policy engine enforces this at registration and on every call.
- An approval request stores the arguments and the tool version. The approval is bound to that version.
- Requesters cannot approve their own requests.
- Execution claims the approval row under a database lock. The action runs at most once. Approvals expire after a configurable TTL.
- The platform-wide switch `CHUSKY_ENABLE_WRITE_TOOLS` is off by default.

## Consequences

- Write latency includes human review time. Agents must handle `pending_approval`.
- Approval fatigue is a real risk. Keep the set of write operations small and review it regularly.
- SAP and terminal writes use the same approval path, plus their own commit and rollback rules.
