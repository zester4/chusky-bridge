from sqlalchemy import select
from sqlalchemy.orm import Session

from chusky_bridge.connectors import IMPLEMENTED_TYPES, PLANNED_TYPES, validate_manifest_operations
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.mcp.manifest import ManifestError, ParsedManifest
from chusky_bridge.mcp.tool_registry import sync_connector_tools
from chusky_bridge.models import Connector


def check_manifest(parsed: ParsedManifest) -> None:
    """Pure checks that need no database. Raises ManifestError with a safe message."""
    info = parsed.manifest.connector
    if info.status == "template":
        raise ManifestError(
            "template manifests cannot be activated; copy the file out of templates/, "
            "fill in discovered names, and set connector.status to active"
        )
    if info.type in PLANNED_TYPES:
        raise ManifestError(f"connector type '{info.type}' is planned, not implemented: {PLANNED_TYPES[info.type]}")
    if info.type not in IMPLEMENTED_TYPES:
        raise ManifestError(f"connector type '{info.type}' is not known")
    try:
        validate_manifest_operations(parsed.manifest)
    except ConnectorError as exc:
        raise ManifestError(str(exc)) from exc


def register_manifest(session: Session, tenant_id, parsed: ParsedManifest) -> Connector:
    """Validate, create or update the connector, and regenerate its tools."""
    check_manifest(parsed)
    info = parsed.manifest.connector

    connector = session.scalar(select(Connector).where(Connector.tenant_id == tenant_id, Connector.name == info.name))
    if connector is None:
        connector = Connector(tenant_id=tenant_id, name=info.name)
        session.add(connector)

    connector.connector_type = info.type
    connector.manifest_version = info.version
    connector.manifest_hash = parsed.hash
    connector.manifest = parsed.raw
    connector.status = "active"
    session.flush()

    sync_connector_tools(session, connector, parsed)
    session.commit()
    return connector
