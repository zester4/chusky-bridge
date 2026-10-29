# Manifest authoring

Full field reference: `docs/manifest-reference.md`. This page is the working procedure.

## Procedure

1. **Discover.** Get the owner's sign-off on what data or actions are needed. Record the exact views, procedures, endpoints, files, queues, or screens.
2. **Start from a template.** Copy the nearest file from `connectors_manifests/templates/`. Keep `status: template` while you work.
3. **Name things for the business.** Connector: `oracle_ebs_orders`. Operation: `get_order_status`. Scope: `ebs.orders.read`.
4. **Start read-only.** Add writes only with an explicit business request.
5. **Schema every parameter.** Use `pattern` for identifiers, `maxLength` for free text, `minimum` and `maximum` for numbers, `enum` for choices.
6. **Declare scopes.** One scope per business capability. Keep scopes narrow.
7. **Validate.** `chusky-bridge validate <file>`. Fix every error.
8. **Activate in non-production.** Set `status: active`. Register, health-check, enable, call, and confirm the audit row.
9. **Hand over.** Record the owner, the scopes, the write operations (if any), and the verification evidence.

## Patterns by adapter

### Read from a view (odbc)

```yaml
operations:
  get_order_status:
    mode: select
    query: "SELECT ORDER_NUMBER, ORDER_STATUS FROM APPS.XX_MCP_ORDER_STATUS_V WHERE ORDER_NUMBER = :order_number"
    parameters: [order_number]
    input_schema:
      type: object
      properties: {order_number: {type: string, pattern: "^[A-Z0-9-]{3,30}$"}}
      required: [order_number]
    required_scopes: [ebs.orders.read]
```

### List with a filter (odata)

```yaml
operations:
  list_sales_orders_for_customer:
    mode: list
    entity_set: A_SalesOrder
    parameters: [sold_to_party]
    select: [SalesOrder, SoldToParty]
    filters: [{field: SoldToParty, parameter: sold_to_party, op: eq}]
    required_scopes: [sap.salesorders.read]
```

### Approval-gated write (sap_rfc)

```yaml
operations:
  create_sales_order:
    mode: rfc
    function_module: BAPI_SALESORDER_CREATEFROMDAT2
    parameters: [payload]
    read_only: false
    requires_approval: true
    risk_level: medium
    required_scopes: [sap.salesorders.create]
```

The adapter calls the BAPI, checks RETURN, then commits or rolls back.

### SFTP batch file (sftp)

```yaml
operations:
  read_batch_csv:
    mode: read_file
    format: csv
    delimiter: ","
    parameters: [filename]
    input_schema:
      type: object
      properties: {filename: {type: string, pattern: "^[A-Za-z0-9][A-Za-z0-9_.\\-]{0,199}$"}}
      required: [filename]
    required_scopes: [billing.batches.read]
```

### Terminal transaction (tn3270)

```yaml
connection:
  host: cics.example.internal
  port: 23
  tls: true
  username: OPER1
  secret_ref: cics_operator_password
  fields:
    userid:  {row: 2, col: 20, length: 8}
    password: {row: 3, col: 20, length: 8}
    custid:  {row: 6, col: 20, length: 10}
    name:    {row: 8, col: 20, length: 20}
operations:
  lookup_customer:
    mode: transaction
    parameters: [customer_id]
    steps:
      - {action: fill, field: userid, source: username}
      - {action: fill, field: password, source: secret}
      - {action: press, aid: ENTER}
      - {action: expect, text: MAIN MENU}
      - {action: fill, field: custid, source: parameter, parameter: customer_id}
      - {action: press, aid: ENTER}
      - {action: read, field: name, as: customer_name}
    read_only: true
    required_scopes: [cics.customers.read]
```

Terminal operations that press ENTER on a data-changing screen must be write operations with approval.

### HL7 query (mllp)

```yaml
operations:
  find_patient:
    mode: query
    template: "MSH|^~\\&|CHUSKY|CHUSKY|LIS|LAB|20260101||QBP^Q22|MSG1|P|2.5\rQPD|Q22^Find Candidates^HL70471|{patient_id}\rRCP|I|10^RD"
    parameters: [patient_id]
    read_only: true
    required_scopes: [hl7.patients.query]
```

## Rules checklist

- [ ] `connector.name` lowercase, unique in the tenant
- [ ] No credential anywhere in the file; `secret_ref` only
- [ ] Every parameter schema-bounded
- [ ] Every operation has `required_scopes`
- [ ] Writes set `read_only: false` and `requires_approval: true`
- [ ] No parameter named `sql`, `query`, `command`, `path`, `file_path`, `url`, `script`, `eval`, or `exec`
- [ ] Hosts, endpoints, and paths come from the connection, never from arguments
- [ ] `chusky-bridge validate` passes
- [ ] Owner has approved in writing; ticket reference in the commit message or PR
