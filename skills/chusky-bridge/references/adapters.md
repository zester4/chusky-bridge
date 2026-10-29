# Adapter reference

Quick reference. The full description, safety notes, and verification status are in `docs/adapters.md`.

| `type` | Mode values | Required connection | Secret field | Notes |
|---|---|---|---|---|
| `odbc` | `select` | `secret_ref` | connection_string | Single SELECT, `:named` placeholders, sqlglot-validated |
| `sql_server` | `stored_procedure` | `secret_ref` | connection_string | Procedure name pattern-checked |
| `postgres` | `function` (`read_only: true`) | `secret_ref` | dsn | Server-enforced read-only sessions |
| `rest` | `method` + `path_template` | `base_url`, `secret_ref` (optional) | api_key | https origin pinned; mTLS optional |
| `odata` | `read` / `list` | `base_url`, `secret_ref` | api_key | `key_parameter`, `filters`, `select` |
| `fhir` | `read` / `search` | `base_url`, `secret_ref` | api_key | Resource allowlist; `_include` refused |
| `soap` | `soap_operation` | `wsdl_path`, `allowed_hosts` | password | WSDL in `CHUSKY_WSDL_DIR` |
| `sftp` | `list_files` / `read_file` | `host`, `username`, `root_directory`, `host_key_sha256` | password | Formats: csv, fixed_width, xml, x12, hl7v2 |
| `kafka` | `peek` | `bootstrap_servers`, `allowed_topics` | sasl_password | Params exactly partition, offset, max_messages |
| `sap_rfc` | `rfc` (`function_module`) | `ashost`, `sysnr`, `client`, `user` | passwd | Writes: approval, RETURN check, commit or rollback |
| `ibm_mq` | `browse` | `queue_manager`, `channel`, `conn_name` | password | Browse only; params exactly max_messages |
| `rabbitmq` | `peek` | `host`, `allowed_queues` | password | Requeues what it reads |
| `queue_gateway` | `browse` / `send` | `kind` (jms or msmq), `base_url` | api_key | Send requires approval |
| `tn3270` | `transaction` | `host`, `port`, `tls`, `fields` | password | Steps only; AID allowlist; TLS required |
| `rpa` | `steps` | `application`, `selectors` | none | Read-only flows cannot click or type |
| `opcua` | `read` | `endpoint`, `security_policy`, `security_mode`, certs | password | Nodes fixed; secure policy only |
| `dicom` | `find` | `ae_title`, `peer_ae_title`, `host`, `port`, `allowed_hosts` | none | C-FIND only; keyword allowlist |
| `mllp` | `query` | `host` | none | Template segments MSH/QPD/RCP; HL7 escaping; TLS default |
| `swift` | as REST | `base_url`, `client_cert_path`, `client_key_path` | api_key | mTLS mandatory; submissions high risk + approval |
| `modbus` | `read_registers` | `host` | none | Read only; address, count, unit bounded |

## Common gotchas

- `odbc` requires the placeholder set to equal `parameters` exactly. A placeholder you do not declare, or a parameter you do not use, fails registration.
- `sftp` requires `host_key_sha256`. Compute it from a verified key only.
- `soap` resolves WSDL names inside `CHUSKY_WSDL_DIR`. Absolute paths and `..` fail.
- `rest` and `odata` refuse private addresses unless `allow_private_network: true`.
- `rabbitmq` requeues messages on every peek. Expect `redelivered: true` on later reads.
- `tn3270` uses `CLEAR` and PF keys from the allowlist only. Any other key fails registration.
- `opcua` reads only nodes listed in the manifest. Agents cannot pass node IDs.
- `dicom` never sends anything but C-FIND.
- Optional drivers are imported at call time. A missing driver returns a clear error; it does not stop the server.
