"""Lightweight assertions for RouterLLM helpers and MCP transport snapshot."""

from __future__ import annotations

from types import SimpleNamespace

from app.mcp_operator import build_router_status_dict, build_capabilities_bundle
from app.router_llm import OpenAIRouterLLM, resolve_openai_router_defaults, transport_is_mcp


def test_resolve_openai_router_defaults_contains_base() -> None:
    base, _, _ = resolve_openai_router_defaults()
    assert "v1" in base.lower() or base.startswith("http")


def test_transport_is_mcp_false_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_TRANSPORT", raising=False)
    assert transport_is_mcp() is False


def test_transport_is_mcp_true(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_TRANSPORT", "mcp")
    assert transport_is_mcp() is True


def test_router_status_includes_router_llm_fields() -> None:
    r = SimpleNamespace(
        anthropic=None,
        router_llm=None,
        context_mode="chunks",
        _hybrid_mode="off",
    )
    snap = build_router_status_dict(r, skill_count=1)
    assert snap["router_llm_backend"] == "none"
    assert snap["router_llm_active"] is False
    assert snap["anthropic_available"] is False


def test_router_status_detects_fake_openai_router_llm(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_OPENAI_API_KEY", raising=False)

    llm = OpenAIRouterLLM(api_key="", base_url="http://localhost:11434/v1", default_model="t")
    r = SimpleNamespace(
        anthropic=None,
        router_llm=llm,
        context_mode="chunks",
        _hybrid_mode="off",
    )
    snap = build_router_status_dict(r, skill_count=1)
    assert snap["router_llm_backend"] == "openai_compatible"
    assert snap["router_llm_active"] is True


def test_capabilities_bundle_has_standalone_agent_hint() -> None:
    router = SimpleNamespace(
        anthropic=None,
        context_mode="chunks",
        _hybrid_mode="off",
        _by_name=None,
    )
    bundle = build_capabilities_bundle(router, skill_count=0)
    assert "standalone_agent" in bundle
    assert bundle["user_env_profile"]["validate_command"] == "skillforge config validate"
