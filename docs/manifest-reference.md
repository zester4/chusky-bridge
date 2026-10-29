# Manifest reference

A manifest is one YAML file that describes one system and its operations. Each operation becomes
one MCP tool. Manifests are validated at registration. A manifest that fails validation is not stored.

## Top-level structure

```yaml
connector:            # required
  name: ibm_i_customers
  type: odbc
  version: 0.1.0      # MAJOR.MINOR.PATCH
  status: active      # active | template

connection:           # adapter-specific, no inline secrets
  secret_ref: ibm_i_customers_db

operations:           # at least one
  get_customer_by_number:
    # common fields + adapter-specific fields
```

## `connector`

| Field | Rules |
|---|---|
| `name` | Lowercase letters, digits, `_`, `-`. 2 to 63 characters. Unique per tenant |
| `type` | One of the adapter types in [adapters.md](adapters.md) |
| `version` | Semantic version of the manifest |
| `status` | `active` loads and serves tools. `template` validates but never activates |

## `connection`

Adapter-specific settings such as hosts, ports, dialects, timeouts, and allowlists.

Credentials are never placed here. Any of these keys is refused: `password`, `connection_string`,
`api_key`, `token`, `secret`, `dsn`, `passwd`, `sasl_password`. Use `secret_ref` instead. The
reference is resolved at runtime from the configured secret provider.

## `operations.<name>`

Operation names: lowercase, start with a letter, 3 to 64 characters, verb first (`get_order_status`).

### Common fields

| Field | Required | Meaning |
|---|---|---|
| `description` | no | Shown to agents. Up to 500 characters. Write it as a plain statement of what the tool does |
| `mode` | depends on adapter | Operation kind for the adapter (`select`, `browse`, `read`, `query`, ...) |
| `parameters` | no | Ordered list of argument names (lowercase identifiers). Every declared parameter must be used |
| `input_schema` | recommended | JSON Schema for arguments. The server always adds `additionalProperties: false` |
| `risk_level` | no (default `low`) | `low`, `medium`, or `high`. High requires approval |
| `read_only` | no (default `true`) | `false` makes the operation a write |
| `requires_approval` | required for writes | Must be `true` when `read_only` is `false` |
| `required_scopes` | yes | Scopes a caller must hold. Name the business capability: `erp.purchase_orders.read` |

Writes must set `read_only: false` and `requires_approval: true`. High-risk operations must require approval.

### Adapter-specific fields

| Adapter | Fields |
|---|---|
| `odbc` | `mode: select`, `query` (single SELECT with `:name` placeholders matching `parameters`) |
| `sql_server` | `mode: stored_procedure`, `procedure`, `parameters` (call order) |
| `postgres` | `mode: function`, `read_only: true`, `function`, `parameters` |
| `rest` | `method`, `path_template` (with `{param}` placeholders) |
| `odata` | `mode: read` (with `key_parameter`) or `mode: list`; `entity_set`; optional `select`, `filters` (`{field, parameter, op}`) |
| `fhir` | `mode: read` (parameter `id`) or `mode: search` (`resource`, `search_parameters`) |
| `soap` | `soap_operation` (WSDL operation name) |
| `sftp` | `mode: list_files` (parameter `pattern`) or `mode: read_file` (parameter `filename`, `format`, `delimiter`, `layout`, `record_tag`); optional `directory` |
| `kafka` | `mode: peek`, `topic`, parameters exactly `[partition, offset, max_messages]` |
| `sap_rfc` | `function_module`, `rfc_names`, optional `commit_function` (writes) |
| `ibm_mq` | `mode: browse`, `queue`, parameters exactly `[max_messages]` |
| `rabbitmq` | `mode: peek`, `queue`, parameters exactly `[max_messages]` |
| `queue_gateway` | `mode: browse` (`queue`, `[max_messages]`) or `mode: send` (`queue`, `[body]`, approval required) |
| `tn3270` | `mode: transaction`, `steps` (fill, press, expect, read) |
| `rpa` | `steps` (click, type, read, expect) referencing connection selectors |
| `opcua` | `mode: read`, `nodes` (tag to node ID), no parameters |
| `dicom` | `mode: find`, `query_keys` (argument to DICOM keyword), `return_keys` |
| `mllp` | `mode: query`, `template` (HL7 segments with `{param}` placeholders), parameters matching the placeholders |
| `swift` | Same as `rest`, with `method`, `path_template`; submissions must be high risk with approval |
| `modbus` | `mode: read_registers`, `function` (holding or input), `address`, `count`, `unit`, optional `scale`, `offset` |

### Adapter connection fields (summary)

| Adapter | Required connection fields |
|---|---|
| `odbc` | `secret_ref`; optional `sql_dialect` (sqlglot dialect), `timeout_seconds`, `max_rows` |
| `sql_server` | `secret_ref` |
| `postgres` | `secret_ref` (DSN) |
| `rest` / `odata` / `fhir` | `base_url` (https), `auth_scheme` (`bearer`, `basic`, `header`), `secret_ref`; optional `username`, `auth_header`, `client_cert_path`, `client_key_path`, `ca_bundle_path`, `health_path` (rest) |
| `soap` | `wsdl_path` (file in `CHUSKY_WSDL_DIR`), `allowed_hosts`; optional `username` and `secret_ref` for WS-Security |
| `sftp` | `host`, `username`, `root_directory`, `host_key_sha256`, `secret_ref`; optional `port`, `max_file_bytes` |
| `kafka` | `bootstrap_servers`, `allowed_topics`; optional `security_protocol`, `sasl_mechanism`, `username`, `secret_ref` |
| `sap_rfc` | `ashost`, `sysnr`, `client`, `user`, `secret_ref`; optional `lang` |
| `ibm_mq` | `queue_manager`, `channel`, `conn_name`; optional `username`, `secret_ref` |
| `rabbitmq` | `host`, `allowed_queues`; optional `port`, `tls`, `virtual_host`, `username`, `secret_ref` |
| `queue_gateway` | `kind` (`jms` or `msmq`), `base_url` (https), `secret_ref` |
| `tn3270` | `host`, `port`, `tls: true`, `fields` (name to row, col, length); optional `username`, `secret_ref` |
| `rpa` | `application` (window title pattern), `selectors` (name to `control_type`, `title` or `auto_id`) |
| `opcua` | `endpoint` (opc.tcp), `security_policy`, `security_mode`, `client_cert_path`, `client_key_path`; optional `username`, `secret_ref` |
| `dicom` | `ae_title`, `peer_ae_title`, `host`, `port`, `allowed_hosts` |
| `mllp` | `host`; optional `port` (2575), `tls` (default true), `ca_bundle_path`, `allow_plaintext` |
| `swift` | `base_url`, `client_cert_path`, `client_key_path` (both required), `secret_ref` |
| `modbus` | `host`; optional `port` (502) |

## Worked example

```yaml
connector:
  name: oracle_ebs_orders
  type: odbc
  version: 1.0.0
  status: active

connection:
  secret_ref: oracle_ebs_readonly_db
  sql_dialect: oracle
  timeout_seconds: 10
  max_rows: 100

operations:
  get_order_status:
    description: Return status for one order number. Read-only.
    mode: select
    query: "SELECT ORDER_NUMBER, ORDER_STATUS, LAST_UPDATE_DATE FROM APPS.XX_MCP_ORDER_STATUS_V WHERE ORDER_NUMBER = :order_number"
    parameters: [order_number]
    input_schema:
      type: object
      properties:
        order_number: {type: string, pattern: "^[A-Z0-9-]{3,30}$"}
      required: [order_number]
    risk_level: low
    read_only: true
    requires_approval: false
    required_scopes: [ebs.orders.read]
```

## Versioning

Changing any operation changes its `definition_hash`. The tool's version increases and the tool is
disabled until a reviewer re-enables it. Changing the connection does not affect tools, but it takes
effect on the next call.
