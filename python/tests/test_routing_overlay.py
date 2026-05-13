"""Project routing overlay: notes, excludes, boosts."""
from __future__ import annotations

from app.route_policies import (
    build_routing_overlay_payload,
    merge_project_notes_into_route_query,
    parse_routing_overlay,
)


def test_merge_notes_requires_project_root() -> None:
    rq = merge_project_notes_into_route_query("hello", "note text", None)
    assert rq == "hello"
    rq2 = merge_project_notes_into_route_query("hello", "note text", "")
    assert rq2 == "hello"


def test_merge_notes_prepends_when_project_set() -> None:
    rq = merge_project_notes_into_route_query("task", "We use Django 5.", "/repo", max_chars=100)
    assert rq.startswith("Project routing notes:\n")
    assert "Django" in rq
    assert "task" in rq


def test_parse_routing_overlay_boost_clamp() -> None:
    ex, boosts, notes = parse_routing_overlay(
        {"routing_boosts": {"a": 9.0, "b": -9.0}},
        by_name={"a": 1, "b": 1},
    )
    assert not ex
    assert boosts["a"] == 2.0
    assert boosts["b"] == -2.0
    assert notes == ""


def test_parse_exclude_unknown_with_audit() -> None:
    audit = []
    ex, _b, _n = parse_routing_overlay(
        {"exclude_skills": ["ghost"]},
        by_name={"real": 1},
        audit_out=audit,
    )
    assert "ghost" not in ex
    assert any(a.get("effect") == "unknown_skill" for a in audit)


def test_build_payload_none_when_empty() -> None:
    assert build_routing_overlay_payload(
        project_root="",
        exclude_skills=frozenset(),
        routing_boosts={},
        project_notes_applied=False,
        project_notes_len=0,
        audit=[],
    ) is None
