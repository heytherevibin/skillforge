"""Session bootstrap MCP bundle helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION
from app.mcp_operator import MCP_PUBLISHED_TOOL_NAMES, build_capabilities_bundle


def test_build_capabilities_bundle_includes_ordered_tools_and_schema() -> None:
    router = SimpleNamespace(
        anthropic=None,
        context_mode="chunks",
        _hybrid_mode="off",
        _by_name=None,
    )
    bundle = build_capabilities_bundle(router, skill_count=3)
    assert bundle["bundle_version"] == "1"
    assert bundle["mcp_response_schema_version"] == MCP_RESPONSE_SCHEMA_VERSION
    assert bundle["mcp_tools"] == list(MCP_PUBLISHED_TOOL_NAMES)
    assert bundle["progressive_loading"]["get_skill_formats"] == ["card", "summary", "full"]
    uep = bundle["user_env_profile"]
    assert uep["validate_command"] == "skillforge config validate"
    assert "path_command" in uep and "init_command" in uep
    snap = bundle["router_snapshot"]
    assert snap["skills_loaded_count"] == 3


def test_capabilities_tool_names_cover_expected_surface() -> None:
    essential = {"route_skills", "capabilities", "get_router_status", "events_recent"}
    missing = essential - set(MCP_PUBLISHED_TOOL_NAMES)
    assert not missing
