# Security model

## Assets

1. Connector credentials (database passwords, API keys, client certificates, SAP and MQ passwords).
2. Data in upstream systems, including personal, clinical, and financial records.
3. The authority to write to upstream systems.
4. The audit trail.
5. Tenant boundaries.

## Trust boundaries

| Boundary | Trusted? | Controls |
|---|---|---|
| Agent to Bridge | Not trusted. Its inputs are untrusted, including tool descriptions and returned data | Bearer token, scopes, closed schemas, policy on every call |
| Human to Bridge admin API | Trusted by role, audited | `chusky.admin` scope, tenant filter on every query |
| Manifest author to Bridge | Trusted with limits | Registration-time validation in every adapter, secrets by reference only |
| Bridge to upstream system | Trusted only through the configured path | Pinned hosts, pinned host keys, mutual TLS, read-only accounts, allowlists |
| Bridge to secret store | Trusted | Vault or AWS with least-privilege policy; production refuses env secrets |

## Threats and controls

| Threat | Control |
|---|---|
| Stolen or forged tokens | Signature, issuer, audience, expiry, and required-claim checks. Audience-bound tokens only |
| Cross-tenant access | Tenant ID from the verified token; every query filters by tenant |
| Prompt injection that asks for unlisted actions | The agent can only call enabled tools. Arguments are schema-checked and cannot name a table, URL, or SQL |
| SQL injection | Validated SELECT only (sqlglot), parameters bound, procedure and function names pattern-checked |
| Write abuse | Writes disabled by default; approval required; self-approval blocked; single execution; expiry |
| Scope creep in manifests | Tool version changes disable the tool until re-approved |
| SSRF through REST, OData, FHIR, SWIFT | Pinned origin; private, loopback, and link-local addresses refused; redirects not followed |
| SSRF through WSDL endpoints | WSDL loaded from an approved directory; every endpoint host must be allowlisted |
| Path traversal in SFTP | Single pinned root; `..` and absolute paths refused; symlink escapes refused by realpath |
| Man in the middle on SFTP | Host key pinned; trust-on-first-use is not implemented |
| Unauthenticated plaintext on terminals and MLLP | TLS required; plaintext only with an explicit `allow_plaintext` flag |
| Unsecured OPC UA sessions | Anonymous and `None` security policies refused at registration |
| Oversized responses (memory exhaustion) | Byte caps in HTTP, SFTP, MLLP, and tool results |
| Credential leakage in results or logs | Redaction of secret-like keys and bearer or password strings; secrets never returned |
| Log injection and request spoofing | Request IDs validated; JSON log formatter escapes content |
| Denial of service through tool calls | Per-tenant, per-connector, per-tool, per-user rate limits; upstream timeouts |
| Insider changing audit records | Audit rows are written by the application only; restrict direct database access and ship logs to a SIEM |
| HL7 or X12 delimiter injection | Values escaped per HL7 rules; control characters refused |
| XML entity attacks | defusedxml refuses DTDs, entity expansion, and external entities |

## Invariants

These must always hold. Any change that breaks one needs a security review and an ADR.

1. An agent cannot supply a host, URL, file path outside an approved root, SQL statement, procedure name, node ID, terminal key, or Modbus address.
2. A secret value never appears in a manifest, an API response, a tool result, an audit row, or a log line.
3. Every tool call produces exactly one final audit decision.
4. A write runs only after an approval for that exact version of the tool, by a reviewer other than the requester, and runs at most once.
5. A read-only operation cannot click, type, write, or send.
6. Production never starts with environment-variable secrets or an HTTP public URL.
7. Every connector validates its operations at registration, so a manifest that fails validation never activates.

## Defense in depth

Chusky Bridge validation is one layer. Also apply these outside the Bridge:

- Read-only database accounts with access restricted to the published views.
- Network segmentation for OT protocols (Modbus, OPC UA, MLLP), with allowlisted source addresses.
- Vendor-side restrictions on API scopes and IP addresses.
- SIEM alerting on `denied` and `error` audit decisions.
- Periodic review of enabled tools and their scopes.

## Data handling

- Results are not stored except in the audit summary, which holds only the status.
- Arguments are stored in the audit log, redacted. Do not pass secrets or unnecessary personal data as arguments.
- Clinical and financial data is restricted by scope and by the operations you choose to expose.
- Retention of `audit_events` and `approval_requests` is a deployment decision. Define it before go-live.
