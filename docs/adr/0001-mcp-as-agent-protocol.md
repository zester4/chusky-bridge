# ADR 0001: MCP is the agent-facing protocol

**Status:** accepted

## Context

Agents need a standard way to discover and call tools. Each agent platform was adopting the Model
Context Protocol, and a custom protocol would require custom client work on every platform.

## Decision

Chusky Bridge exposes its tools through MCP over Streamable HTTP at `/mcp`, authenticated with OAuth 2.1
bearer tokens. The protected-resource metadata is published so clients can discover the authorization server.

## Consequences

- Any MCP-capable client works without custom code.
- Authorization must be enforced on the server for every call, since clients are not trusted.
- Tool descriptions and results are treated as untrusted data by the Bridge and must be validated on the way in and redacted on the way out.
