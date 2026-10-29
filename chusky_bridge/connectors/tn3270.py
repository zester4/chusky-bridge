"""IBM 3270 and 5250 terminal transactions with field-level control.

Agents never send keystrokes. A manifest defines a fixed sequence of steps (fill named fields,
press allowlisted AID keys, check for expected screen text, read named fields). The driver
behind the terminal is pluggable. The default driver uses py3270 and an x3270 installation.
Validate it in a lab before production use, because emulator APIs differ between versions.
"""

import re
from typing import Any, Protocol

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers

ALLOWED_AIDS = frozenset({"ENTER", "CLEAR"} | {f"PF{n}" for n in range(1, 25)} | {"PA1", "PA2", "PA3"})
ACTIONS = frozenset({"fill", "press", "expect", "read"})
SOURCES = frozenset({"parameter", "username", "secret", "literal"})
_PRINTABLE = re.compile(r"^[\x20-\x7e]*$")
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class TerminalDriver(Protocol):
    def connect(self, host: str, port: int, tls: bool) -> None: ...
    def fill(self, row: int, col: int, text: str) -> None: ...
    def read(self, row: int, col: int, length: int) -> str: ...
    def press(self, aid: str) -> None: ...
    def screen_text(self) -> str: ...
    def close(self) -> None: ...


class Py3270Driver:
    """Default driver. Requires the py3270 package and an x3270 binary on the runtime."""

    def __init__(self) -> None:
        try:
            from py3270 import Emulator
        except ImportError as exc:
            raise ConnectorError("the 3270 driver (py3270 and x3270) is not installed") from exc
        self._em = Emulator(visible=False)

    def connect(self, host: str, port: int, tls: bool) -> None:
        self._em.connect(f"{host}:{port}" if not tls else f"L:{host}:{port}")

    def fill(self, row: int, col: int, text: str) -> None:
        self._em.move_to(row, col)
        self._em.send_string(text)

    def read(self, row: int, col: int, length: int) -> str:
        return self._em.string_get(row, col, length)

    def press(self, aid: str) -> None:
        if aid == "ENTER":
            self._em.send_enter()
        elif aid == "CLEAR":
            self._em.send_clear()
        elif aid.startswith("PF"):
            self._em.send_pf(int(aid[2:]))
        else:
            self._em.send_pa(int(aid[2:]))

    def screen_text(self) -> str:
        return "\n".join(self._em.get_screen_lines())

    def close(self) -> None:
        self._em.terminate()


class Tn3270Connector(BaseConnector):
    connector_type = "tn3270"
    secret_field = "password"

    def __init__(self, config: dict[str, Any], driver_factory: Any = None):
        super().__init__(config)
        self._driver_factory = driver_factory or Py3270Driver

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        if op.get("mode") != "transaction":
            raise ConnectorError(f"{name}: tn3270 mode must be 'transaction'")
        if not connection.get("host") or not connection.get("port"):
            raise ConnectorError(f"{name}: connection needs host and port")
        if connection.get("tls") is not True and connection.get("allow_plaintext") is not True:
            raise ConnectorError(f"{name}: TLS is required (set tls: true)")
        fields = connection.get("fields") or {}
        for field_name, spec in fields.items():
            if not _FIELD.match(field_name):
                raise ConnectorError(f"{name}: invalid field name {field_name!r}")
            if not all(isinstance(spec.get(k), int) for k in ("row", "col", "length")) or spec["length"] <= 0:
                raise ConnectorError(f"{name}: field {field_name} needs integer row, col and length")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        used_params: set[str] = set()
        steps = op.get("steps") or []
        if not steps:
            raise ConnectorError(f"{name}: a transaction needs steps")
        for index, step in enumerate(steps, start=1):
            action = step.get("action")
            if action not in ACTIONS:
                raise ConnectorError(f"{name}: step {index} has unknown action")
            if action in {"fill", "read"} and step.get("field") not in fields:
                raise ConnectorError(f"{name}: step {index} references an undefined field")
            if action == "fill":
                source = step.get("source")
                if source not in SOURCES:
                    raise ConnectorError(f"{name}: step {index} has an invalid source")
                if source == "parameter":
                    if step.get("parameter") not in params:
                        raise ConnectorError(f"{name}: step {index} references an undeclared parameter")
                    used_params.add(step["parameter"])
                if source == "literal":
                    value = str(step.get("value", ""))
                    if not _PRINTABLE.match(value) or len(value) > fields[step["field"]]["length"]:
                        raise ConnectorError(f"{name}: literal in step {index} is not printable or too long")
            if action == "press" and step.get("aid") not in ALLOWED_AIDS:
                raise ConnectorError(f"{name}: step {index} uses a key that is not allowed")
            if action == "expect":
                text = str(step.get("text", ""))
                if not text or len(text) > 80 or not _PRINTABLE.match(text):
                    raise ConnectorError(f"{name}: step {index} needs a short printable expect text")
            if action == "read" and not _FIELD.match(str(step.get("as", ""))):
                raise ConnectorError(f"{name}: step {index} needs an output name 'as'")
        if set(params) - used_params:
            raise ConnectorError(f"{name}: parameters {sorted(set(params) - used_params)} are never used")

    def health_check(self) -> dict[str, Any]:
        driver = self._driver_factory()
        try:
            driver.connect(self.config["host"], int(self.config["port"]), bool(self.config.get("tls", True)))
        except Exception as exc:
            raise ConnectorError("terminal connection failed") from exc
        finally:
            driver.close()
        return {"status": "healthy"}

    def _value(self, step: dict[str, Any], arguments: dict[str, Any]) -> str:
        source = step["source"]
        if source == "parameter":
            value = str(arguments[step["parameter"]])
        elif source == "username":
            value = str(self.config.get("username", ""))
        elif source == "secret":
            value = str(self.config.get("password", ""))
        else:
            value = str(step.get("value", ""))
        if not _PRINTABLE.match(value):
            raise ConnectorError("value contains characters that cannot be typed on a 3270 screen")
        return value

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        fields = self.config.get("fields") or {}
        outputs: dict[str, str] = {}
        driver = self._driver_factory()
        try:
            try:
                driver.connect(self.config["host"], int(self.config["port"]), bool(self.config.get("tls", True)))
            except Exception as exc:
                raise ConnectorError("terminal connection failed") from exc
            for index, step in enumerate(op["steps"], start=1):
                action = step["action"]
                try:
                    if action == "fill":
                        spec = fields[step["field"]]
                        value = self._value(step, arguments)
                        if len(value) > spec["length"]:
                            raise ConnectorError(f"value too long for field at step {index}")
                        driver.fill(spec["row"], spec["col"], value)
                    elif action == "press":
                        driver.press(step["aid"])
                    elif action == "expect":
                        if step["text"] not in driver.screen_text():
                            raise ConnectorError(f"expected screen marker not found at step {index}")
                    elif action == "read":
                        spec = fields[step["field"]]
                        outputs[step["as"]] = driver.read(spec["row"], spec["col"], spec["length"]).strip()
                except ConnectorError:
                    raise
                except Exception as exc:
                    raise ConnectorError(f"terminal step {index} failed") from exc
        finally:
            driver.close()
        return {"status": "success", "operation": operation, "outputs": outputs}
