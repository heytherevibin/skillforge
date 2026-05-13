"""Smoke tests for tools_cli argument wiring (no heavy router setup)."""

from __future__ import annotations

import pytest

from app.tools_cli import build_parser
def test_tools_cli_search_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["search", "hello", "world", "--limit", "5"])
    assert ns.tool == "search"
    assert ns.query == ["hello", "world"]
    assert ns.limit == 5


def test_tools_cli_disable_polarity() -> None:
    p = build_parser()
    ns_off = p.parse_args(["disable", "--skill-name", "x", "--off"])
    assert ns_off.disabled is True
    ns_on = p.parse_args(["disable", "--skill-name", "x", "--on"])
    assert ns_on.disabled is False


def test_tools_cli_global_flags_with_subcommand() -> None:
    p = build_parser()
    ns = p.parse_args(
        ["--project-root", "/tmp/ws", "--user-id", "u1", "catalog"],
    )
    assert ns.tool == "catalog"
    assert ns.project_root == "/tmp/ws"
    assert ns.user_id == "u1"


def test_tools_cli_materialize_roots() -> None:
    p = build_parser()
    ns = p.parse_args(
        [
            "materialize",
            "--root",
            "/repo",
            "--names",
            "skill_a, skill_b",
            "--hosts",
            "both",
            "--no-merge",
        ],
    )
    assert ns.mat_root == "/repo"
    assert ns.names == "skill_a, skill_b"
    assert ns.hosts == "both"
    assert ns.no_merge is True


def test_tools_cli_router_status_hyphen_alias() -> None:
    p = build_parser()
    ns = p.parse_args(["router-status"])
    assert ns.tool == "router-status"


def test_tools_cli_feedback_thumbs_negative() -> None:
    p = build_parser()
    ns = p.parse_args(["feedback", "--skill-name", "s", "--thumbs=-1"])
    assert ns.thumbs == -1


def test_tools_cli_feedback_rejects_bad_thumbs() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["feedback", "--skill-name", "s", "--thumbs", "2"])
