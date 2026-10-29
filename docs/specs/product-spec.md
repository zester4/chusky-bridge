# Chusky Bridge Product Specification

## Vision

Chusky Bridge becomes the secure integration layer between AI agents and the
systems enterprises cannot easily replace.

## Target user

Primary user: Platform / IT integration engineer.
Secondary users: Security reviewer, business-system owner, AI agent user.

## Core jobs to be done

1. Connect a legacy system without exposing its raw interface to an agent.
2. Define safe read and write operations.
3. Control which users and agents can use each operation.
4. Audit every agent-initiated action.
5. Require approval for sensitive or irreversible actions.

## MVP scope

### Must have

- Tenant and user management
- Connector registration
- SQL Server and PostgreSQL read-only connectors
- REST connector with allowlisted hosts and methods
- MCP server exposing approved tools
- OAuth 2.1 resource-server authentication
- Tool-level RBAC
- Structured audit logging
- Secret vault integration
- Tool manifest versioning
- Admin approval workflow
- Rate limits and payload-size limits

### Should have

- SOAP/WSDL connector
- SFTP/CSV connector
- Message-queue connector
- Dry-run mode for write tools
- Data-loss-prevention redaction
- Connector health checks
- Tool usage analytics

### Later

- Mainframe/3270 adapter
- Desktop RPA adapter
- Natural-language connector builder
- Marketplace of reviewed connector templates
- On-prem and air-gapped deployment

## Success metrics

- Time to first read-only tool: under 30 minutes
- Percentage of tool calls with complete audit records: 100%
- Unauthorized tool-call attempts blocked: 100%
- Secrets appearing in model context or logs: 0
- Incidents caused by unapproved destructive tool calls: 0
