from mcp.server.fastmcp import FastMCP

from chusky_bridge.auth import identity_var
from chusky_bridge.config import settings
from chusky_bridge.db import SessionLocal
from chusky_bridge.mcp.tool_executor import ToolCallError, execute_tool
from chusky_bridge.mcp.tool_registry import list_enabled_tools

# Served at the root of the mount point, so clients connect to /mcp.
mcp = FastMCP("Chusky Bridge", streamable_http_path="/")


def _caller():
    identity = identity_var.get()
    if identity is None:
        raise ToolCallError("not authenticated")
    return identity


@mcp.tool()
def chusky_list_tools() -> dict:
    """List Chusky Bridge tools this user is approved to call."""
    identity = _caller()
    session = SessionLocal()
    try:
        tools = list_enabled_tools(session, identity)
    finally:
        session.close()
    return {
        "tools": tools,
        "policy": {
            "write_tools_enabled": settings.enable_write_tools,
            "max_response_bytes": settings.max_tool_response_bytes,
        },
    }


@mcp.tool()
def chusky_call_tool(connector_name: str, tool_name: str, arguments: dict) -> dict:
    """Call an approved Chusky Bridge tool. Arguments are schema-validated and policy-checked.

    Write or high-risk tools may return status 'pending_approval' until a reviewer acts.
    """
    try:
        return execute_tool(
            identity=_caller(),
            connector_name=connector_name,
            tool_name=tool_name,
            arguments=arguments,
        )
    except ToolCallError as exc:
        return {"status": "error", "message": str(exc)}
