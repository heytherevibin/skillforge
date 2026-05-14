"""Unit tests for route decision tracing helpers (no router)."""
from __future__ import annotations

import pytest

from app.route_decision_trace import (
    build_decision_trace,
    decision_digest,
    route_trace_level,
)


def test_route_trace_level_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_TRACE_LEVEL", raising=False)
    assert route_trace_level() == "off"


@pytest.mark.parametrize("raw,expected", [("compact", "compact"), ("full", "full"), ("TRUE", "compact")])
def test_route_trace_level_env(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_TRACE_LEVEL", raw)
    assert route_trace_level() == expected


def test_decision_digest_stable() -> None:
    d1 = decision_digest(
        picked_names=["a"],
        candidate_names=["a", "b"],
        pick_path="llm_pick",
        host_shortlist_only=False,
        dry_run=False,
        route_ms=10.111,
    )
    d2 = decision_digest(
        picked_names=["a"],
        candidate_names=["a", "b"],
        pick_path="llm_pick",
        host_shortlist_only=False,
        dry_run=False,
        route_ms=10.1110001,
    )
    assert d1 == d2
    assert len(d1) == 16


def test_build_decision_trace_off_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_TRACE_LEVEL", "off")
    lvl = route_trace_level()
    assert lvl == "off"
    assert (
        build_decision_trace(
            trace_id="t1",
            level="off",
            dry_run=False,
            host_shortlist_only=False,
            pick_path="x",
            haiku_rerank_applied=False,
            policy_rules_loaded=0,
            routing_overlay_applied=False,
            picked_names=["p"],
            candidate_names=["c"],
            route_ms=1.0,
            route_quality={},
        )
        is None
    )


def test_build_decision_trace_compact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_TRACE_LEVEL", "compact")
    tr = build_decision_trace(
        trace_id="corr-9",
        level="compact",
        dry_run=True,
        host_shortlist_only=False,
        pick_path="embedding_top",
        haiku_rerank_applied=False,
        policy_rules_loaded=3,
        routing_overlay_applied=True,
        picked_names=["s1"],
        candidate_names=["s1", "s2"],
        route_ms=5.25,
        route_quality={"pick_path": "embedding_top"},
    )
    assert tr is not None
    assert tr["trace_id"] == "corr-9"
    assert len(tr["digest"]) == 16
    assert tr["picked_names"] == ["s1"]
    assert tr["routing_overlay_applied"] is True
    assert tr["dry_run"] is True
    assert "route_quality_snapshot" not in tr


def test_build_decision_trace_full_includes_snap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_TRACE_LEVEL", "full")
    rq = {"v": 2}
    tr = build_decision_trace(
        trace_id="c",
        level="full",
        dry_run=False,
        host_shortlist_only=False,
        pick_path="p",
        haiku_rerank_applied=False,
        policy_rules_loaded=1,
        routing_overlay_applied=False,
        picked_names=[],
        candidate_names=["x"],
        route_ms=1.0,
        route_quality=rq,
    )
    assert tr is not None and tr.get("route_quality_snapshot") == rq
