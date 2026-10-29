# Chusky Bridge Security Specification

## Authentication

- MCP Gateway uses OAuth 2.1 authorization-code flow with PKCE.
- Access tokens must be audience-bound to Chusky Bridge.
- Validate issuer, audience, expiry, signature, and scopes on every request.
- Never use MCP access tokens as upstream-system credentials.
- The protected-resource metadata document is served at `/.well-known/oauth-protected-resource`.

## Authorization

- Authorization is enforced server-side on every tool call.
- Required token claims: `sub`, `tenant_id`, `scope`. Agent identity comes from `azp` or `client_id`.
- Apply tool-level RBAC and object-level authorization.
- Separate read and write scopes.
- Deny by default.

## Tool safety

- Every tool has a versioned definition hash. Any change to an operation bumps the version and disables the tool until re-approved.
- Tool descriptions, parameter schemas, and outputs are untrusted content.
- Inputs are validated against closed JSON schemas (`additionalProperties: false`).
- Forbidden argument keys (SQL, shell, path, URL, script) are rejected at any nesting depth.
- Upstream identifiers (procedure names, function names, path segments) are validated against strict patterns; values are always bound as parameters.
- Response size is capped by `MAX_TOOL_RESPONSE_BYTES`.
- Outputs are redacted for secret-like keys and credential-like strings.

## Destructive operations

- Write tools are disabled by default (`ENABLE_WRITE_TOOLS=false`).
- Every write operation must set `requires_approval: true`. High-risk operations must require approval.
- Approval records include arguments, requester, approver, status transitions, and decision reason.
- Requesters cannot approve their own actions.
- An approved request executes exactly once. Execution claims the row under a database lock.
- Approvals expire after `APPROVAL_TTL_SECONDS`.

## Audit

Log every decision (`denied`, `pending_approval`, `executed`, `error`):

- Request ID
- Tenant, user, agent, connector, tool, tool version
- Redacted arguments
- Authorization decision and reason
- Approval ID when applicable
- Upstream status
- Duration
- Result summary

## Secrets

- Connector credentials are referenced by `secret_ref` in manifests. Inline secrets are rejected at manifest validation.
- The MVP vault reads `CHUSKY_SECRET_<REF>` environment variables. Production should use a managed secrets manager.
- Secrets are never returned in tool output, logged, or placed in prompts.
