# Adapter reference

Each adapter is a Python class in `chusky_bridge/connectors/`, registered by its `connector_type`.
Every adapter does four things: validates its operations at registration, executes one named
operation per call, reports health, and enforces its own limits.

**Verification levels**

- **Unit-tested:** the adapter's logic is covered by tests that use fakes for the client library.
- **Lab-verify:** the adapter depends on a vendor product or protocol detail that must be checked in a lab before production.

Every adapter is unit-tested. Live behavior depends on the product version and its configuration, so
every adapter needs lab verification against the target before production use.

## Databases

### `odbc`
**Reaches:** any database with an ODBC driver: Oracle, Db2 (LUW and for i), Informix, MySQL/MariaDB, Teradata, Sybase, Firebird, Access, HPE NonStop, Progress.
**Mode:** `select`. Operations are one SELECT statement each, with `:name` placeholders.
**Secret:** the ODBC connection string.
**Safety:** the statement is parsed with sqlglot. Exactly one SELECT is allowed. `INTO`, row locks, and any DML or DDL are refused at registration. Placeholders must match the declared parameters exactly. Values are bound through the driver.
**Requires:** `pip install ".[odbc]"` and the vendor driver (unixODBC, Oracle Instant Client, IBM i Access, Db2 CLI, and so on).
**Set `sql_dialect`** to the closest sqlglot dialect (`oracle`, `tsql`, `mysql`, `postgres`). Without it, the generic parser is used. Some vendor-specific syntax will not parse; simplify the query or use a published view.
**Verification:** unit-tested. Lab-verify the driver and the dialect for each database version.

### `sql_server`
**Reaches:** Microsoft SQL Server stored procedures.
**Mode:** `stored_procedure`, with `procedure` (schema-qualified) and `parameters` in call order.
**Secret:** connection string.
**Safety:** procedure names are pattern-checked, and values are bound as `?` parameters.
**Verification:** unit-tested. Lab-verify the procedure signatures.

### `postgres`
**Reaches:** PostgreSQL functions.
**Mode:** `function`, `read_only: true`.
**Secret:** DSN.
**Safety:** every session runs with `default_transaction_read_only=on` and a statement timeout, enforced by the server.
**Verification:** unit-tested. Lab-verify.

## Web services

### `rest`
**Reaches:** any HTTPS REST API.
**Mode:** `method` (GET, POST, PUT, PATCH, DELETE) and `path_template` with `{param}` placeholders. GET arguments become query parameters. Other methods send a JSON body.
**Auth:** `auth_scheme` `bearer`, `basic`, or `header`. Optional mutual TLS through `client_cert_path` and `client_key_path` (from `CHUSKY_CERT_DIR`).
**Safety:** a pinned HTTPS origin. Path values are percent-encoded into single segments, so `..` cannot escape. Private and loopback addresses are refused unless `allow_private_network` is set. Redirects are not followed. Responses are size-capped.
**Health:** set `health_path` to test the connection.
**Verification:** unit-tested. Lab-verify authentication and scopes against the vendor.

### `odata`
**Reaches:** OData v2 and v4 services: SAP Gateway (S/4HANA, Business One), Dynamics 365, NAV, IFS.
**Mode:** `read` (single entity by `key_parameter`) or `list` (collection with `filters` and `select`).
**Safety:** entity and field names are identifier-checked. Filter values are escaped as OData literals (embedded quotes doubled). Clients cannot submit a `$filter` string. Results are capped at `max_rows`.
**Verification:** unit-tested. Lab-verify the service path and entity names with `/IWFND/MAINT_SERVICE` (SAP) or the equivalent.

### `fhir`
**Reaches:** FHIR R4 servers: Epic, Oracle Health, MEDITECH Expanse, eClinicalWorks, InterSystems.
**Mode:** `read` (by `id`) or `search` (`search_parameters` map arguments to FHIR parameters).
**Safety:** resource types are allowlisted in code. Parameters beginning with `_include`, `_revinclude`, `_has`, `_filter`, or `_graph` are refused, so a single call cannot pull a large graph.
**Auth:** the bearer token comes from the vendor's SMART Backend Services flow. A separate job must refresh it and write it to the secret store. The adapter does not manage OAuth.
**Verification:** unit-tested. Lab-verify the vendor's app registration, scopes, and resource coverage. Clinical data needs the strictest scopes.

### `soap`
**Reaches:** WSDL-described services: PeopleSoft Integration Broker, Siebel, Temenos T24, Infor Lawson, Manhattan, Yardi, Exchange EWS.
**Mode:** `soap_operation` (name from the WSDL) with `parameters`.
**Safety:** the WSDL must be a file in `CHUSKY_WSDL_DIR`. Clients cannot point the adapter at a URL. Every endpoint host in the WSDL must appear in `allowed_hosts`, or registration fails. SOAP faults are not returned to the agent.
**Auth:** WS-Security UsernameToken with `username` and the `secret_ref` password.
**Requires:** `zeep` (installed by default).
**Verification:** unit-tested. Lab-verify the WSDL, operation names, and endpoint hosts.

### `swift`
**Reaches:** SWIFT messaging through a connectivity gateway you operate. Requires SWIFT membership.
**Mode:** read (GET status) and submission (POST). It shares the REST adapter's safety controls.
**Safety:** mutual TLS is mandatory. Submissions must be `risk_level: high` and require approval. `message_type` must look like a SWIFT ISO 20022 message type. SWIFT-side validation, sanctions screening, and BIC checks happen in the gateway, not in Chusky Bridge.
**Verification:** unit-tested. Lab-verify with the gateway and the SWIFT test environment. Review operational and legal requirements with your SWIFT provider.

## Files and batch

### `sftp`
**Reaches:** batch and file interfaces: banking cores, ACH, EDI exports, mainframe extracts, HR exports, billing feeds.
**Mode:** `list_files` (pattern match in a directory) or `read_file` (fetch and parse one file).
**Formats:** `csv` (header row), `fixed_width` (explicit layout with name, start, and length), `xml` (records by tag, parsed with defusedxml), `x12` (EDI interchanges, delimiters read from the ISA header), `hl7v2` (one message, MSH-9 returned).
**Safety:** host key pinned with `host_key_sha256`, compared in constant time. Trust-on-first-use is not implemented. Single root directory. Paths are normalized and checked against the root. Files are size-capped before they are read. Read-only: the adapter cannot write, rename, or delete.
**Verification:** unit-tested for parsers and path rules. Lab-verify the host key, the file naming, and the format against sample files from the producing system.

## Messaging

### `kafka`
**Reaches:** Apache Kafka and compatible brokers.
**Mode:** `peek` at a partition and offset.
**Safety:** no consumer group, no commits, a topic allowlist, and a message cap. Values are decoded as JSON when possible and truncated.
**Auth:** SASL over TLS (`SCRAM-SHA-512` by default).
**Requires:** `kafka-python-ng` (installed by default).
**Verification:** unit-tested. Lab-verify the broker ACLs.

### `ibm_mq`
**Reaches:** IBM MQ queue managers.
**Mode:** `browse`. The queue is opened with `MQOO_BROWSE` and read with `MQGMO_BROWSE_FIRST` and `MQGMO_BROWSE_NEXT`, so messages stay on the queue.
**Safety:** queue-name pattern, browse only, and a dedicated MQ user should hold browse-only authority.
**Requires:** `pip install ".[mq]"` and the IBM MQ client libraries.
**Verification:** unit-tested with a fake `pymqi`. Lab-verify the channel, the authority records, and the message sizes.

### `rabbitmq`
**Reaches:** RabbitMQ over AMQP 0-9-1.
**Mode:** `peek`. AMQP has no browse, so the adapter reads with `basic_get` and requeues every message it read. Requeued messages are marked `redelivered`.
**Safety:** a passive queue declare (never creates queues), a queue allowlist, TLS by default, and a message cap.
**Caveat:** consumers that depend on delivery counts will see the requeued messages. Use a dedicated queue for monitoring if that matters.
**Requires:** `pip install ".[mq]"` (pika).
**Verification:** unit-tested with a fake pika. Lab-verify the requeue behavior against your broker version.

### `queue_gateway`
**Reaches:** JMS brokers (TIBCO EMS, ActiveMQ, Oracle AQ) and Windows MSMQ, through a messaging gateway you deploy beside the broker. JMS needs a Java client and MSMQ needs Windows APIs, so neither runs natively in Python.
**Mode:** `browse` (non-destructive) and `send` (approval required).
**Gateway contract:**

```
GET  /queues/{queue}/messages?limit=N   → 200 JSON array of messages (or {"messages": [...]})
POST /queues/{queue}/messages           body {"body": "..."} → 200 {"message_id": "..."}
GET  /health                            → 200
```

Authentication is a bearer token from `secret_ref`. The gateway holds the broker credentials and TLS to the broker. Build the gateway with browse-only broker authority for `browse` operations.
**Verification:** unit-tested against the contract. The gateway is your code. Test it against the broker first.

## Terminals and desktop

### `tn3270`
**Reaches:** IBM 3270 (CICS, IMS, TSO) and 5250 (IBM i) screens, and Unisys terminal sessions where the emulator supports them.
**Mode:** `transaction`. A fixed list of steps: `fill` (a named field from a username, the secret, a parameter, or a literal), `press` (an allowlisted AID key: ENTER, CLEAR, PF1 to PF24, PA1 to PA3), `expect` (a short text marker that must appear on screen), and `read` (a named field copied to the output).
**Safety:** agents never send keystrokes. Field positions and their lengths come from the connection. A value longer than its field is refused. TLS is required unless `allow_plaintext` is set. The password is typed from the secret store and never appears in the result.
**Driver:** the default uses `py3270` and an x3270 binary. The driver interface is small, so another emulator can replace it.
**Requires:** `pip install ".[tn3270]"` and x3270 on the runtime.
**Verification:** unit-tested with a fake terminal. **Lab-verify the driver** against your emulator version. Emulator APIs and TLS prefixes differ between releases. Mark every terminal operation as high risk and require approval for any operation that presses ENTER on a screen that commits data.

### `rpa`
**Reaches:** Windows desktop applications with no programmatic interface (VB6, Delphi, Win32, Citrix-published apps where UI automation is available).
**Mode:** `steps` (click, type, read, expect) against selectors declared in the connection.
**Safety:** agents cannot supply selectors. A read-only flow cannot click or type (enforced at registration). Typed values are printable and length-capped.
**Driver:** the default uses `pywinauto` with the UI Automation backend. Windows only.
**Requires:** `pip install ".[rpa]"` on a Windows runtime.
**Caveats:** UI automation breaks when the application changes. Prefer the database behind the application whenever it is available. Run the runtime on a dedicated, locked-down machine with an audited service account.
**Verification:** unit-tested with a fake UI driver. **Lab-verify** the selectors against each application version.

## Healthcare

### `mllp`
**Reaches:** HL7 v2 interface engines and systems that answer HL7 queries over MLLP (LIS, EHR feeds, patient-index queries).
**Mode:** `query`. The manifest holds a template of HL7 segments (MSH, QPD, RCP only). Only the query types QBP^Q22 and QRY^A19 can be sent.
**Safety:** values are HL7-escaped (`|`, `^`, `&`, `~`, `\`), so they cannot add fields or segments. Control characters are refused. TLS by default. The reply is parsed and only the acknowledgement code and the segments are returned.
**Verification:** unit-tested for framing, escaping, and parsing. **Lab-verify** the query profile with the receiving system's interface team.

### `dicom`
**Reaches:** PACS and modalities that answer C-FIND at the study level.
**Mode:** `find`. Query keys and return keys come from an allowlist (PatientID, PatientName, AccessionNumber, StudyDate, StudyInstanceUID, ModalitiesInStudy, StudyDescription).
**Safety:** the adapter sends C-FIND only. It never sends C-STORE, C-MOVE, or C-GET. The host must appear in `allowed_hosts`.
**Requires:** `pip install ".[dicom]"` (pynetdicom and pydicom).
**Verification:** unit-tested with fakes. **Lab-verify** the AE titles and the association policy with the PACS administrator.

## Industrial

### `opcua`
**Reaches:** OPC UA servers on PLCs, SCADA systems, and historians (Rockwell, AVEVA, Honeywell, Emerson, Yokogawa, and others with an OPC UA server).
**Mode:** `read`. The nodes are fixed in the manifest. Agents cannot choose node IDs.
**Safety:** only the secure policies Basic256Sha256, Aes128_Sha256_RsaOaep, and Aes256_Sha256_RsaPss are accepted. Sign or SignAndEncrypt is required. A client certificate and key are required and come from `CHUSKY_CERT_DIR`. Anonymous and `None` sessions are refused. Writes are not supported.
**Requires:** `pip install ".[industrial]"` (python-opcua).
**Verification:** unit-tested with a fake client. **Lab-verify** the certificate trust and the endpoint policies with the OT team.

### `modbus`
**Reaches:** Modbus TCP devices: meters, drives, PLCs with Modbus servers.
**Mode:** `read_registers`. Holding or input registers at a fixed address, count, and unit ID. Optional linear scaling.
**Safety:** read-only. Addresses are bounded (0 to 65535), counts are 1 to 125, unit IDs are 0 to 247. Modbus has no authentication, so deploy only on a segregated OT network behind a gateway that restricts sources.
**Requires:** `pip install ".[industrial]"` (pymodbus).
**Verification:** unit-tested with a fake client. **Lab-verify** register maps and scaling against the device documentation.

## SAP

### `sap_rfc`
**Reaches:** SAP ECC, R/3, S/4HANA on-premises, SAP CRM, and IS-U, through RFC and BAPI calls.
**Mode:** read operations call a function module and return its results. Write operations call a function module, check its RETURN table, and then call `BAPI_TRANSACTION_COMMIT` (or `BAPI_TRANSACTION_ROLLBACK` on any error message or failure). Writes must require approval.
**Safety:** function names must be uppercase SAP names. Parameter names are mapped explicitly through `rfc_names`. Business messages from RETURN are returned to the agent without internal detail.
**Requires:** `pip install ".[sap]"` and the SAP NW RFC SDK, which SAP licenses and you install separately.
**Verification:** unit-tested with a fake connection. **Lab-verify** every BAPI against your release in SE37, including its commit behavior.

## Health and diagnostics

Every adapter implements `health_check`. Call it with `POST /v1/connectors/{name}/health`. A health
check that fails does not disable the connector. Disable it deliberately with `/disable`.

## Adding an adapter

See [skills/chusky-bridge/references/adding-an-adapter.md](../skills/chusky-bridge/references/adding-an-adapter.md).
