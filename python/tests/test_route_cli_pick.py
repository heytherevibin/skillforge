"""Parsing interactive CLI host picks."""

from __future__ import annotations

from app.route_cli_pick import parse_interactive_skill_pick


def test_parse_ranks_and_names() -> None:
    rows = [
        {"rank": 1, "name": "alpha", "id": "alpha"},
        {"rank": 2, "name": "beta", "id": "beta"},
        {"rank": 3, "name": "gamma-sk", "id": "gamma-sk"},
    ]
    out = parse_interactive_skill_pick("1, gamma-sk ", rows)
    assert out == ["alpha", "gamma-sk"]


def test_parse_quit() -> None:
    assert parse_interactive_skill_pick("q", [{}]) == []
    assert parse_interactive_skill_pick("", []) == []


def test_strip_backticks() -> None:
    rows = [{"rank": 1, "name": "x"}]
    assert parse_interactive_skill_pick("`x`", rows) == ["x"]
