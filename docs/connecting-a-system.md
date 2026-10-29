# Connecting a system

Every new system follows the same process, whatever its technology. The steps are the same for an
Oracle database, a SOAP service, and a mainframe file extract.

## Step 1: Find the system in the catalog

```bash
chusky-bridge catalog search "<product name>"
```

The result gives the expected adapter and its status. If the product is missing, add an entry to
`systems/catalog.yaml` before you start. Entries describe the expected route. They are not proof that
the route works.

## Step 2: Discover the supported interface with the owner

Ask the system owner, and check the vendor documentation, for the following:

- **Databases:** a read-only account, and the published views or procedures to expose. Do not expose base tables.
- **Web services:** the WSDL, OData entity sets, or REST resources, and the authentication method.
- **Files:** the SFTP directory, file naming, format (CSV, fixed-width layout, XML tag, X12, HL7), and the host key fingerprint.
- **Messaging:** the queue or topic names, and whether browse or peek is permitted.
- **Terminals:** the screen flow, field positions (row, column, length), and expected screen markers.
- **Licensing and approvals:** the vendor's terms for third-party connectivity, and who must approve the integration.

Write these down. They become the manifest.

## Step 3: Start from a template or write a manifest

Templates live in `connectors_manifests/templates/`. Copy the one closest to your system:

```bash
cp connectors_manifests/templates/ibm_i_orders_odbc.yaml my_system.yaml
```

Keep `connector.status: template` while you iterate. Replace placeholder names with the discovered
names. The field reference is in [manifest-reference.md](manifest-reference.md).

Rules to apply to every operation:

- Start every operation as read-only. Add writes only when a business owner requests them.
- Give every parameter a closed `input_schema` with a pattern or bounds.
- Give every operation `required_scopes` that name the business capability (`erp.purchase_orders.read`).
- Use the narrowest data you can. Expose a view, not a table. Expose one endpoint, not a resource tree.

## Step 4: Validate

```bash
chusky-bridge validate my_system.yaml
```

Validation runs the same checks the server runs at registration. Fix every error before continuing.

## Step 5: Provision the secret

Store the credential where the environment's secret provider reads it:

- **Vault:** `secret/chusky/<secret_ref>` with field `value`.
- **AWS:** secret named `<CHUSKY_AWS_SECRET_PREFIX><secret_ref>`.
- **Development only:** `CHUSKY_SECRET_<SECRET_REF>` in the environment.

Use a dedicated service account with the minimum privileges the operations need.

## Step 6: Activate in a non-production environment

1. Set `connector.status: active` and set the real hosts and paths.
2. Register the connector: `POST /v1/connectors`.
3. Run the health check: `POST /v1/connectors/{name}/health`. Fix any failure before continuing.
4. Enable each read-only tool: `PATCH /v1/tools/{id}` with `{"enabled": true}`.
5. Call each tool through an agent and confirm the result and the audit entry.
6. Test the failure paths: wrong argument, missing scope, unavailable system, oversized response.

## Step 7: Record the verification

Update the catalog entry in your fork or internal copy to `verified` with the product version, the
date, and the tester. The repository catalog stays unverified until someone records verification with
evidence.

## Step 8: Promote

Repeat steps 6 and 7 in production. Writes stay disabled (`CHUSKY_ENABLE_WRITE_TOOLS=false`) until a
separate approval-flow test passes in production.
