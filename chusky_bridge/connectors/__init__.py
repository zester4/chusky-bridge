from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError
from chusky_bridge.connectors.dicom import DicomConnector
from chusky_bridge.connectors.fhir import FhirConnector
from chusky_bridge.connectors.ibm_mq import IbmMqConnector
from chusky_bridge.connectors.kafka import KafkaConnector
from chusky_bridge.connectors.mllp import MllpConnector
from chusky_bridge.connectors.modbus import ModbusConnector
from chusky_bridge.connectors.odata import ODataConnector
from chusky_bridge.connectors.odbc import OdbcConnector
from chusky_bridge.connectors.opcua import OpcUaConnector
from chusky_bridge.connectors.postgres import PostgresConnector
from chusky_bridge.connectors.queue_gateway import QueueGatewayConnector
from chusky_bridge.connectors.rabbitmq import RabbitMqConnector
from chusky_bridge.connectors.rest import RestConnector
from chusky_bridge.connectors.rpa import RpaConnector
from chusky_bridge.connectors.sap_rfc import SapRfcConnector
from chusky_bridge.connectors.sftp import SftpConnector
from chusky_bridge.connectors.soap import SoapConnector
from chusky_bridge.connectors.sql_server import SqlServerConnector
from chusky_bridge.connectors.swift_gateway import SwiftGatewayConnector
from chusky_bridge.connectors.tn3270 import Tn3270Connector
from chusky_bridge.mcp.manifest import Manifest
from chusky_bridge.vault import SecretNotFound, get_secret

REGISTRY: dict[str, type[BaseConnector]] = {
    cls.connector_type: cls
    for cls in (
        OdbcConnector,
        SqlServerConnector,
        PostgresConnector,
        RestConnector,
        ODataConnector,
        FhirConnector,
        SoapConnector,
        SftpConnector,
        KafkaConnector,
        SapRfcConnector,
        IbmMqConnector,
        RabbitMqConnector,
        QueueGatewayConnector,
        Tn3270Connector,
        RpaConnector,
        OpcUaConnector,
        DicomConnector,
        MllpConnector,
        SwiftGatewayConnector,
        ModbusConnector,
    )
}
IMPLEMENTED_TYPES = frozenset(REGISTRY)

# Adapters that are designed but not built. Empty: every catalog adapter is now implemented.
PLANNED_TYPES: dict[str, str] = {}


def validate_manifest_operations(manifest: Manifest) -> None:
    """Run every adapter's registration checks. Raises ConnectorError on the first problem."""
    cls = REGISTRY.get(manifest.connector.type)
    if cls is None:
        raise ConnectorError(f"connector type '{manifest.connector.type}' is not implemented")
    for name, op in manifest.operations.items():
        cls.validate_operation(name, op.model_dump(), manifest.connection)


def build_connector(manifest: Manifest) -> BaseConnector:
    cls = REGISTRY.get(manifest.connector.type)
    if cls is None:
        raise ConnectorError(f"connector type '{manifest.connector.type}' is not implemented")

    config: dict[str, Any] = dict(manifest.connection)
    secret_ref = config.pop("secret_ref", None)
    if secret_ref:
        if not cls.secret_field:
            raise ConnectorError("this connector type does not take a secret")
        try:
            config[cls.secret_field] = get_secret(secret_ref)
        except SecretNotFound as exc:
            raise ConnectorError("connector credentials are not configured") from exc

    config["operations"] = {name: op.model_dump() for name, op in manifest.operations.items()}
    return cls(config)


__all__ = [
    "BaseConnector",
    "ConnectorError",
    "IMPLEMENTED_TYPES",
    "PLANNED_TYPES",
    "REGISTRY",
    "build_connector",
    "validate_manifest_operations",
]
