"""MCP initialize stores clientInfo for materialize hosts inference."""

from __future__ import annotations

from app.mcp_server import MCPServer


def test_handle_initialize_records_client_info() -> None:
    s = MCPServer()
    s.handle_initialize(
        {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "cursor-ai", "title": "Workspace"},
        }
    )
    assert s._mcp_client_name == "cursor-ai"
    assert s._mcp_client_title == "Workspace"


def test_handle_initialize_missing_client_info_resets() -> None:
    s = MCPServer()
    s.handle_initialize({"clientInfo": {"name": "cursor-temp"}})
    assert s._mcp_client_name == "cursor-temp"
    s.handle_initialize({})
    assert s._mcp_client_name == ""
    assert s._mcp_client_title == ""
