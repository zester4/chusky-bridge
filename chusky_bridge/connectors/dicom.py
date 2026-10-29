from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, jsonable, require_arguments

QUERY_KEYWORDS = frozenset(
    {
        "PatientID",
        "PatientName",
        "AccessionNumber",
        "StudyDate",
        "StudyInstanceUID",
        "ModalitiesInStudy",
        "StudyDescription",
    }
)
PENDING_STATUSES = frozenset({0xFF00, 0xFF01})


def _status_code(status: Any) -> int:
    try:
        return int(status.Status)
    except AttributeError:
        return int(status["Status"])


class DicomConnector(BaseConnector):
    """DICOM study-level C-FIND against an allowlisted PACS or modality. Read-only by definition:
    the adapter sends C-FIND only. It never sends C-STORE, C-MOVE, or C-GET. Requires pynetdicom and pydicom."""

    connector_type = "dicom"
    secret_field = None

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "find" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: dicom operations must be mode 'find' and read_only")
        query_keys = op.get("query_keys") or {}
        if not query_keys:
            raise ConnectorError(f"{name}: define query_keys")
        for arg, keyword in query_keys.items():
            if keyword not in QUERY_KEYWORDS:
                raise ConnectorError(f"{name}: keyword {keyword} is not on the query allowlist")
            if arg not in op.get("parameters", []):
                raise ConnectorError(f"{name}: query argument {arg} must be a declared parameter")
        for keyword in op.get("return_keys") or []:
            if keyword not in QUERY_KEYWORDS:
                raise ConnectorError(f"{name}: return keyword {keyword} is not on the allowlist")
        for key in ("ae_title", "peer_ae_title", "host", "port"):
            if not connection.get(key):
                raise ConnectorError(f"{name}: connection needs {key}")
        if connection.get("host") not in (connection.get("allowed_hosts") or []):
            raise ConnectorError(f"{name}: host must be listed in allowed_hosts")

    def _associate(self) -> Any:
        try:
            from pynetdicom import AE
            from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind
        except ImportError as exc:
            raise ConnectorError("the DICOM network stack (pynetdicom) is not installed") from exc
        ae = AE(ae_title=self.config["ae_title"])
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        assoc = ae.associate(self.config["host"], int(self.config["port"]), ae_title=self.config["peer_ae_title"])
        if not assoc.is_established:
            raise ConnectorError("DICOM association was rejected or timed out")
        return assoc

    def health_check(self) -> dict[str, Any]:
        assoc = self._associate()
        assoc.release()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        try:
            from pydicom.dataset import Dataset
        except ImportError as exc:
            raise ConnectorError("the DICOM library (pydicom) is not installed") from exc

        query = Dataset()
        query.QueryRetrieveLevel = "STUDY"
        for arg, keyword in (op.get("query_keys") or {}).items():
            setattr(query, keyword, str(arguments[arg]))
        for keyword in op.get("return_keys") or []:
            if not hasattr(query, keyword):
                setattr(query, keyword, "")

        assoc = self._associate()
        rows: list[dict[str, Any]] = []
        try:
            for status, identifier in assoc.send_c_find(query, query_model="S"):
                if status is None:
                    raise ConnectorError("DICOM C-FIND returned no status")
                code = _status_code(status)
                if code in PENDING_STATUSES and identifier is not None and len(rows) < self.max_rows:
                    rows.append(
                        {kw: jsonable(str(getattr(identifier, kw, ""))) for kw in (op.get("return_keys") or [])}
                    )
                elif code not in PENDING_STATUSES and code != 0x0000:
                    raise ConnectorError(f"DICOM C-FIND failed with status 0x{code:04X}")
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("DICOM query failed") from exc
        finally:
            assoc.release()
        return {"status": "success", "operation": operation, "row_count": len(rows), "rows": rows}
