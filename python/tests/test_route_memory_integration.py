"""Integration: run_route_turn host path observes operator memory fusion."""

from __future__ import annotations

import asyncio

from unittest.mock import MagicMock

import pytest

from app.main import Skill, init_db, run_route_turn
from app.route_memories import compact_route_memory_for_event, memory_append


@pytest.fixture
def alpha_skill() -> Skill:
    return Skill(
        name="alpha-skill",
        title="Alpha",
        description="d",
        body="b",
        source="bundled",
    )


def test_host_shortlist_includes_compact_route_memory_in_event(monkeypatch, tmp_path, alpha_skill) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY_MAX_CHARS", "900")

    import app.main as m

    monkeypatch.setattr(m, "SKILLFORGE_ROUTER_MODE", "host")

    fr = MagicMock()
    fr._by_name = {alpha_skill.name: alpha_skill}
    fr.router_llm = None
    fr.context_mode = "chunks"
    fr._hybrid_mode = "off"

    facets = [
        {
            "name": alpha_skill.name,
            "cosine_similarity": 0.71,
            "learned_weight": 1.0,
            "routing_score": 0.81,
        }
    ]

    def _facets(rq, *_a, **_k):
        assert "Operator routing memories:" in rq
        assert "Use alpha for smoke" in rq
        return facets

    fr.shortlist_with_facets = _facets

    con = init_db(tmp_path / "fuse.db")
    uid = "integration-user"
    _, _ = memory_append(con, user_id=uid, project_root=None, body="Use alpha for smoke tests", importance=4)

    async def _go():
        return await run_route_turn(
            con,
            fr,
            "run integration check",
            [],
            user_id=uid,
            dry_run=True,
        )

    out = asyncio.run(_go())
    assert out["host_pick_shortlist"] is True
    rq = out["route_query"]
    assert "Operator routing memories:" in rq
    rmem = out["route_quality"].get("route_memory")
    assert isinstance(rmem, dict)
    assert rmem.get("applied") is True
    ev = out["event"]
    assert ev["route_memory"] == compact_route_memory_for_event(rmem)
    assert ev["route_memory"].get("schema") == "route_memory_event/1"
