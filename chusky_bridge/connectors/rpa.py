"""Desktop UI automation for applications with no programmatic interface.

This is the last-resort adapter. It runs only steps declared in a manifest, against selectors
declared in the connection (never selectors supplied by an agent). Read-only operations may
only read and assert. Clicking or typing requires a write operation, which requires approval.
The default driver uses pywinauto (UI Automation backend) and runs on Windows only.
"""

import re
from typing import Any, Protocol

from chusky_bridge.connectors.base import BaseConnector, ConnectorError, require_arguments, validate_identifiers

ACTIONS = frozenset({"click", "type", "read", "expect"})
WRITE_ACTIONS = frozenset({"click", "type"})
_SELECTOR = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_PRINTABLE = re.compile(r"^[\x20-\x7e]*$")
MAX_TEXT = 500


class UiDriver(Protocol):
    def attach(self, title_pattern: str) -> None: ...
    def find(self, selector: dict[str, Any]) -> Any: ...
    def click(self, element: Any) -> None: ...
    def type_text(self, element: Any, text: str) -> None: ...
    def text(self, element: Any) -> str: ...
    def close(self) -> None: ...


class PywinautoDriver:
    """Default driver. Requires pywinauto on Windows."""

    def __init__(self) -> None:
        try:
            import pywinauto  # noqa: F401
        except ImportError as exc:
            raise ConnectorError("the UI automation driver (pywinauto) is not installed") from exc
        self._window = None

    def attach(self, title_pattern: str) -> None:
        from pywinauto import Application

        app = Application(backend="uia").connect(title_re=title_pattern)
        self._window = app.window(title_re=title_pattern)

    def find(self, selector: dict[str, Any]) -> Any:
        criteria = {k: v for k, v in selector.items() if k in {"control_type", "title", "auto_id"}}
        return self._window.child_window(**criteria).wrapper_object()

    def click(self, element: Any) -> None:
        element.click_input()

    def type_text(self, element: Any, text: str) -> None:
        element.set_edit_text(text)

    def text(self, element: Any) -> str:
        return str(element.window_text())

    def close(self) -> None:
        self._window = None


class RpaConnector(BaseConnector):
    connector_type = "rpa"
    secret_field = None

    def __init__(self, config: dict[str, Any], driver_factory: Any = None):
        super().__init__(config)
        self._driver_factory = driver_factory or PywinautoDriver

    @classmethod
    def validate_operation(cls, name: str, op: dict[str, Any], connection: dict[str, Any]) -> None:
        selectors = connection.get("selectors") or {}
        if not connection.get("application"):
            raise ConnectorError("connection needs application (window title pattern)")
        for sel_name, spec in selectors.items():
            if not _SELECTOR.match(sel_name) or not isinstance(spec, dict):
                raise ConnectorError(f"invalid selector name {sel_name!r}")
            if not (spec.get("title") or spec.get("auto_id")):
                raise ConnectorError(f"selector {sel_name} needs title or auto_id")
        params = op.get("parameters", [])
        validate_identifiers(params, "parameter")
        steps = op.get("steps") or []
        if not steps:
            raise ConnectorError(f"{name}: a flow needs steps")
        read_only = op.get("read_only") is True
        used: set[str] = set()
        for index, step in enumerate(steps, start=1):
            action = step.get("action")
            if action not in ACTIONS:
                raise ConnectorError(f"{name}: step {index} has unknown action")
            if read_only and action in WRITE_ACTIONS:
                raise ConnectorError(f"{name}: read_only flows may not click or type (step {index})")
            if step.get("selector") not in selectors:
                raise ConnectorError(f"{name}: step {index} references an undefined selector")
            if action == "type":
                if step.get("parameter") not in params:
                    raise ConnectorError(f"{name}: step {index} must type a declared parameter")
                used.add(step["parameter"])
            if action == "expect":
                text = str(step.get("text", ""))
                if not text or len(text) > 200 or not _PRINTABLE.match(text):
                    raise ConnectorError(f"{name}: step {index} needs a short printable expect text")
            if action == "read" and not _SELECTOR.match(str(step.get("as", ""))):
                raise ConnectorError(f"{name}: step {index} needs an output name 'as'")
        if set(params) - used:
            raise ConnectorError(f"{name}: parameters {sorted(set(params) - used)} are never used")

    def health_check(self) -> dict[str, Any]:
        driver = self._driver_factory()
        try:
            driver.attach(self.config["application"])
        except Exception as exc:
            raise ConnectorError("application window not found") from exc
        finally:
            driver.close()
        return {"status": "healthy"}

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(operation)
        require_arguments(op.get("parameters", []), arguments)
        selectors = self.config.get("selectors") or {}
        outputs: dict[str, str] = {}
        driver = self._driver_factory()
        try:
            try:
                driver.attach(self.config["application"])
            except Exception as exc:
                raise ConnectorError("application window not found") from exc
            for index, step in enumerate(op["steps"], start=1):
                try:
                    element = driver.find(selectors[step["selector"]])
                    action = step["action"]
                    if action == "click":
                        driver.click(element)
                    elif action == "type":
                        text = str(arguments[step["parameter"]])
                        if not _PRINTABLE.match(text) or len(text) > MAX_TEXT:
                            raise ConnectorError("value is not printable or too long")
                        driver.type_text(element, text)
                    elif action == "read":
                        outputs[step["as"]] = driver.text(element)[:MAX_TEXT]
                    elif action == "expect" and step["text"] not in driver.text(element):
                        raise ConnectorError(f"expected text not found at step {index}")
                except ConnectorError:
                    raise
                except Exception as exc:
                    raise ConnectorError(f"UI step {index} failed") from exc
        finally:
            driver.close()
        return {"status": "success", "operation": operation, "outputs": outputs}
