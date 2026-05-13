"""Tests for MCP Phase 0 response contract (no heavy deps)."""
from __future__ import annotations

from types import SimpleNamespace

from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION, build_route_skills_meta


def test_build_route_skills_meta_basic() -> None:
    sk_a = SimpleNamespace(name="skill-a", body="alpha" * 100)
    sk_b = SimpleNamespace(name="skill-b", body="beta")
    skills_map = {"skill-a": sk_a, "skill-b": sk_b}
    cand_skill = SimpleNamespace(name="skill-a")
    result = {
        "candidates": [(cand_skill, 0.91), (sk_b, 0.5)],
        "reasoning": "test",
        "session_id": "sid-1",
        "rerouted": False,
        "change": 0.2,
        "route_ms": 12.3,
    }
    text = "# header\n\nbody"
    meta = build_route_skills_meta(
        result=result,
        picked_names=["skill-a"],
        user_id="u1",
        db_path="/tmp/db.sqlite",
        skills_map=skills_map,
        response_text=text,
    )
    assert meta["schema_version"] == MCP_RESPONSE_SCHEMA_VERSION
    assert "fusion" not in meta
    assert meta["context_items_count"] == 0
    assert meta["budget"]["chars_project_chunks"] == 0
    assert meta["budget"]["chars_context_items_total"] == meta["budget"]["chars_skill_bodies"]
    assert meta["sources"] == [
        {"kind": "skill", "ref": "skill-a", "line_start": None, "line_end": None, "score": None},
    ]
    assert meta["budget"]["chars_skill_bodies"] == 100 * len("alpha")
    assert meta["budget"]["chars_response_total"] == len(text)
    assert meta["picked"] == ["skill-a"]
    assert len(meta["candidates_preview"]) >= 1
    assert meta["candidates_preview"][0]["name"] == "skill-a"


def test_build_route_skills_meta_with_context_items() -> None:
    sk = __import__("types").SimpleNamespace(name="skill-a", body="full")
    skills_map = {"skill-a": sk}
    result = {"candidates": [], "reasoning": "r", "session_id": "s", "rerouted": False, "change": 0.0, "route_ms": 1.0}
    items = [
        {"skill": "skill-a", "path": None, "line_start": 1, "line_end": 5, "text": "chunktext", "score": 0.88},
    ]
    meta = build_route_skills_meta(
        result=result,
        picked_names=["skill-a"],
        user_id="u",
        db_path="db.sqlite",
        skills_map=skills_map,
        response_text="out",
        context_items=items,
    )
    assert meta["schema_version"] == MCP_RESPONSE_SCHEMA_VERSION
    assert meta["context_items_count"] == 1
    assert meta["sources"][0]["line_start"] == 1
    assert meta["sources"][0]["line_end"] == 5
    assert meta["budget"]["chars_skill_bodies"] == len("chunktext")
    assert meta["budget"]["chars_project_chunks"] == 0
    assert meta["budget"]["chars_context_items_total"] == len("chunktext")


def test_build_route_skills_meta_mixed_skill_and_file() -> None:
    skills_map = {}
    result = {"candidates": [], "session_id": "s", "rerouted": False, "change": 0.0, "route_ms": 1.0}
    items = [
        {"skill": "sk", "path": None, "line_start": 1, "line_end": 2, "text": "AA", "score": 0.9},
        {"skill": None, "path": "lib/x.py", "line_start": 10, "line_end": 12, "text": "BB", "score": 0.8},
    ]
    meta = build_route_skills_meta(
        result=result,
        picked_names=["sk"],
        user_id="u",
        db_path="db.sqlite",
        skills_map=skills_map,
        response_text="o",
        context_items=items,
    )
    assert meta["sources"][0]["kind"] == "skill"
    assert meta["sources"][1]["kind"] == "file"
    assert meta["sources"][1]["ref"] == "lib/x.py"
    assert meta["budget"]["chars_skill_bodies"] == 2
    assert meta["budget"]["chars_project_chunks"] == 2
    assert meta["budget"]["chars_context_items_total"] == 4


def test_build_route_skills_meta_includes_fusion() -> None:
    items = [
        {"skill": "sk", "path": None, "line_start": 1, "line_end": 2, "text": "a", "score": 0.9, "mmr_rank": 1},
    ]
    meta = build_route_skills_meta(
        result={"candidates": [], "session_id": "s", "rerouted": False, "change": 0.0, "route_ms": 1.0},
        picked_names=["sk"],
        user_id="u",
        db_path="db.sqlite",
        skills_map={},
        response_text="o",
        context_items=items,
        fusion={"enabled": True, "lambda": 0.7, "selected_count": 1},
    )
    assert meta["fusion"]["enabled"] is True
    assert meta["sources"][0].get("mmr_rank") == 1


def test_build_route_skills_meta_includes_context_redaction() -> None:
    meta = build_route_skills_meta(
        result={"candidates": [], "session_id": "s", "rerouted": False, "change": 0.0, "route_ms": 1.0},
        picked_names=[],
        user_id="u",
        db_path="db.sqlite",
        skills_map={},
        response_text="x",
        context_redaction={"enabled": True, "secret_hits": 2, "path_hits": 1},
    )
    assert meta["context_redaction"]["secret_hits"] == 2


def test_build_route_skills_meta_error_field() -> None:
    meta = build_route_skills_meta(
        result={"candidates": []},
        picked_names=[],
        user_id="",
        db_path="x.db",
        skills_map={},
        response_text="err",
        error="empty_prompt",
    )
    assert meta["error"] == "empty_prompt"
    assert meta["sources"] == []
