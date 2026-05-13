"""Tests for conversation-aware route text, skill cards, and hybrid helpers."""
from __future__ import annotations

import numpy as np
import pytest

from app.main import Skill, parse_skill_md
from app.routing_signals import (
    build_route_query_text,
    host_pick_shortlist_lines,
    keyword_overlap_scores,
    normalize_minmax,
    skill_routing_card,
)


def test_build_route_query_legacy(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTER_CONV_MAX_TURNS", "0")
    out = build_route_query_text("hello", [{"role": "user", "content": "prev"}])
    assert out == "hello"


def test_build_route_query_merges_turns(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTER_CONV_MAX_TURNS", "2")
    monkeypatch.setenv("SKILLFORGE_ROUTER_CONV_MSG_CHARS", "80")
    conv = [
        {"role": "user", "content": "first msg"},
        {"role": "assistant", "content": "reply"},
    ]
    out = build_route_query_text("current ask", conv)
    assert "user: first msg" in out
    assert "assistant: reply" in out
    assert "Current user message:" in out
    assert out.endswith("current ask")


def test_skill_routing_card_includes_triggers() -> None:
    s = Skill(
        name="x",
        title="X Skill",
        description="does things",
        body="",
        source="bundled",
        triggers="when foo",
        anti_triggers="not bar",
    )
    card = skill_routing_card(s)
    assert "X Skill" in card
    assert "Triggers: when foo" in card
    assert "Anti-triggers: not bar" in card


def test_normalize_minmax() -> None:
    a = np.array([1.0, 3.0, 5.0])
    assert np.allclose(normalize_minmax(a), [0.0, 0.5, 1.0])
    flat = np.array([2.0, 2.0, 2.0])
    assert np.allclose(normalize_minmax(flat), [0.0, 0.0, 0.0])


def test_keyword_overlap_scores() -> None:
    cards = ["alpha beta gamma", "foo bar"]
    q = "beta search"
    sc = keyword_overlap_scores(q, cards)
    assert sc[0] > sc[1]


def test_host_pick_shortlist_lines_basic() -> None:
    facets = [
        {
            "name": "alpha-skill",
            "title": "Alpha",
            "cosine_similarity": 0.42,
            "description_preview": "Does alpha testing patterns for flaky CI.",
        }
    ]
    md, rows = host_pick_shortlist_lines(
        prompt="fix flaky tests",
        route_query="fix flaky tests",
        facet_rows=facets,
        max_candidates=5,
        line_chars=90,
    )
    assert "alpha-skill" in md
    assert "fix flaky" in md
    assert len(rows) == 1
    assert rows[0]["name"] == "alpha-skill"
    assert rows[0]["id"] == "alpha-skill"
    assert rows[0]["rank"] == 1


def test_normalize_host_picked_main() -> None:
    from app.main import Skill, normalize_host_picked_names

    a = Skill(name="a", title="A", description="", body="", source="bundled")
    b = Skill(name="b", title="B", description="", body="", source="bundled")
    by_name = {"a": a, "b": b}
    assert normalize_host_picked_names(["b", "a", "b", "unknown"], by_name, 1) == ["b"]
    assert normalize_host_picked_names([], by_name, 7) == []


def test_parse_skill_triggers(tmp_path) -> None:
    md = tmp_path / "my-skill" / "SKILL.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "---\nname: Nice\ndescription: Desc\ntriggers: when testing\n"
        "anti_triggers: never for prod\n---\n\n# Body\n",
        encoding="utf-8",
    )
    s = parse_skill_md(md, "bundled")
    assert s is not None
    assert s.triggers == "when testing"
    assert s.anti_triggers == "never for prod"
