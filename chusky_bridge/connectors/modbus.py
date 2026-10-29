from typing import Any

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, jsonable


class ModbusConnector(BaseConnector):
    """Modbus TCP register reads for industrial devices. Read-only: no coils, no writes.
    Register addresses, counts, and unit IDs are fixed in the manifest. Modbus has no authentication,
    so deploy it only on a segregated OT network with a gateway that restricts source addresses."""

    connector_type = "modbus"
    secret_field = None

    def __init__(self, config: dict[str, Any], client_factory: Any = None):
        super().__init__(config)
        self._client_factory = client_factory

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "read_registers" or op.get("read_only") is not True:
            raise ConnectorError(f"{name}: modbus operations must be mode 'read_registers' and read_only")
        if op.get("parameters"):
            raise ConnectorError(f"{name}: modbus reads take no parameters")
        if op.get("function", "holding") not in ("holding", "input"):
            raise ConnectorError(f"{name}: function must be holding or input")
        address, count, unit = op.get("address"), op.get("count"), op.get("unit", 1)
        if not isinstance(address, int) or not 0 <= address <= 65535:
            raise ConnectorError(f"{name}: address must be 0-65535")
        if not isinstance(count, int) or not 1 <= count <= 125:
            raise ConnectorError(f"{name}: count must be 1-125")
        if not isinstance(unit, int) or not 0 <= unit <= 247:
            raise ConnectorError(f"{name}: unit must be 0-247")
        if not connection.get("host"):
            raise ConnectorError(f"{name}: connection needs host")

    def _client(self) -> Any:
        if self._client_factory:
            return self._client_factory(self.config)
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as exc:
            raise ConnectorError("the Modbus client (pymodbus) is not installed") from exc
        return ModbusTcpClient(
            self.config["host"],
            port=int(self.config.get("port", 502)),
            timeout=float(self.config.get("timeout_seconds", 5)),
        )

    def health_check(self) -> dict[str, Any]:
        client = self._client()
        try:
            if not client.connect():
                raise ConnectorError("Modbus connection failed")
        finally:
            client.close()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        client = self._client()
        if not client.connect():
            raise ConnectorError("Modbus connection failed")
        try:
            read = (
                client.read_input_registers
                if op.get("function", "holding") == "input"
                else client.read_holding_registers
            )
            response = read(op["address"], count=op["count"], slave=op.get("unit", 1))
            if response.isError():
                raise ConnectorError("Modbus device returned an error")
            scale = float(op.get("scale", 1))
            offset = float(op.get("offset", 0))
            raw = [int(r) for r in response.registers]
            values = [jsonable(r * scale + offset) for r in raw]
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("Modbus read failed") from exc
        finally:
            client.close()
        return {
            "status": "success",
            "operation": operation,
            "address": op["address"],
            "raw": raw,
            "values": values,
        }
