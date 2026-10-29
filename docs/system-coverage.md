# System coverage

Chusky Bridge reaches a system through a transport, not through a product-specific client. Most named
products expose the same few transports. The product-specific part is the manifest.

`systems/catalog.yaml` lists 180+ named systems with their expected adapter. Search it with:

```bash
chusky-bridge catalog search <name>
chusky-bridge catalog search --json <category>
```

Every entry is unverified until a connector has been tested against that product and version.

## Coverage by transport

| Transport | Adapter | Typical products |
|---|---|---|
| SQL views and procedures | `odbc`, `sql_server`, `postgres` | Oracle E-Business Suite, JD Edwards, Infor LN, Epicor, Sage, Dynamics GP, Tyler, CGI, Epic Clarity, DB2 for i |
| REST | `rest` | Salesforce, Oracle Fusion, Workday, UKG, ADP, Guidewire, Duck Creek, Majesco, Finacle, FLEXCUBE, Accela, Documentum, OnBase, SharePoint |
| OData | `odata` | SAP S/4HANA, SAP Business One, Dynamics 365, Dynamics NAV, IFS |
| SAP RFC/BAPI | `sap_rfc` | SAP ECC, R/3, CRM, IS-U |
| SOAP | `soap` | PeopleSoft, Siebel, Temenos T24, Infor Lawson, Manhattan, Blue Yonder, Yardi, Sage X3, Exchange EWS, TIBCO BW, Oracle Service Bus |
| FHIR | `fhir` | Epic, Oracle Health, MEDITECH Expanse, eClinicalWorks, InterSystems |
| HL7 v2 over MLLP | `mllp` | MEDITECH Magic, Sunquest, Omnicell, Mirth, Corepoint, Rhapsody, Cloverleaf |
| DICOM | `dicom` | Sectra, Agfa, Philips IntelliSpace, PACS |
| SFTP files | `sftp` | FIS, Fiserv, Jack Henry, Hogan, ACH, Fedwire and SEPA ISO 20022, NCR, MRI, UKG Kronos exports, Descartes, mainframe extracts, EDI |
| Kafka | `kafka` | Event streams |
| IBM MQ | `ibm_mq` | Mainframe and enterprise message queues |
| RabbitMQ | `rabbitmq` | AMQP-based messaging |
| JMS and MSMQ | `queue_gateway` | TIBCO EMS, ActiveMQ, Oracle AQ, Windows MSMQ |
| 3270 and 5250 | `tn3270` | CICS, IMS, Micro Focus, Unisys, IBM i 5250 |
| Desktop UI | `rpa` | VB6, Delphi, Win32 applications |
| SWIFT | `swift` | SWIFT Alliance Access through a gateway |
| OPC UA | `opcua` | Rockwell, AVEVA, Honeywell, Emerson, Yokogawa, Ignition |
| Modbus | `modbus` | Meters, drives, PLCs |

## How to get from a product to a connector

1. Find the product in the catalog and note its adapter.
2. Confirm with the vendor which interface your installation actually has (licensing and modules differ).
3. Follow [connecting-a-system.md](connecting-a-system.md).

## What is not covered

- Systems with no programmatic interface and no database access, unless UI automation is acceptable (`rpa`).
- Bulk data movement and ETL. Chusky Bridge serves bounded queries to agents. Use a data platform for bulk movement.
- Direct writes to base tables of a business system. Use the vendor's supported write path.
