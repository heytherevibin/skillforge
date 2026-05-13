"""Tests for route policy loading and merge."""
from __future__ import annotations

import pytest

from app.main import Skill, init_db
from app.route_policies import load_route_policies_config, merge_policy_includes


@pytest.fixture
def skill_alpha() -> Skill:
    return Skill(
        name="alpha-skill",
        title="Alpha",
        description="test",
        body="body",
        source="bundled",
    )


def test_merge_adds_on_regex_match(tmp_path, skill_alpha, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES", raising=False)
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_FILE", raising=False)
    con = init_db(tmp_path / "x.db")
    policies = {"rules": [{"if_text_matches": r"(?i)oauth", "include": ["alpha-skill"]}]}
    by_name = {skill_alpha.name: skill_alpha}
    merged, audit = merge_policy_includes(
        "Fix OAuth callback",
        ["other-skill"],
        policies,
        by_name,
        con,
        "",
        max_active=7,
    )
    assert merged[0] == "other-skill"
    assert "alpha-skill" in merged
    assert any(r.get("effect") == "added" for r in audit)


def test_merge_unknown_skill_audited(tmp_path, skill_alpha, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES", raising=False)
    con = init_db(tmp_path / "y.db")
    policies = {"rules": [{"if_text_matches": "auth", "include": ["missing"]}]}
    by_name = {skill_alpha.name: skill_alpha}
    merged, audit = merge_policy_includes(
        "auth bug",
        [],
        policies,
        by_name,
        con,
        "",
        max_active=7,
    )
    assert merged == []
    assert any(r.get("effect") == "unknown_skill" for r in audit)


def test_merge_respects_max_active(tmp_path, skill_alpha, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES", raising=False)
    con = init_db(tmp_path / "z.db")
    policies = {"rules": [{"if_text_matches": "x", "include": ["alpha-skill"]}]}
    by_name = {skill_alpha.name: skill_alpha}
    picked = ["a", "b", "c", "d", "e", "f", "g"]
    merged, audit = merge_policy_includes(
        "x",
        picked,
        policies,
        by_name,
        con,
        "",
        max_active=7,
    )
    assert len(merged) == 7
    assert "alpha-skill" not in merged
    assert any(r.get("effect") == "skipped_max_active" for r in audit)


def test_load_from_project_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES", raising=False)
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_FILE", raising=False)
    p = tmp_path / "skillforge-policies.json"
    p.write_text(
        '{"rules": [{"if_text_matches": "hi", "include": ["z"]}]}',
        encoding="utf-8",
    )
    root = str(tmp_path)
    cfg = load_route_policies_config(root)
    assert len(cfg.get("rules") or []) == 1


def test_load_inline_env_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "SKILLFORGE_ROUTE_POLICIES",
        '{"rules": [{"if_text_matches": "a", "include": ["b"]}]}',
    )
    cfg = load_route_policies_config(None)
    assert cfg["rules"][0]["include"] == ["b"]


def test_invalid_regex_recorded(tmp_path, skill_alpha, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES", raising=False)
    con = init_db(tmp_path / "r.db")
    policies = {"rules": [{"if_text_matches": "(bad[regex", "include": ["alpha-skill"]}]}
    by_name = {skill_alpha.name: skill_alpha}
    _m, audit = merge_policy_includes(
        "x",
        [],
        policies,
        by_name,
        con,
        "",
        max_active=7,
    )
    assert any(r.get("effect") == "invalid_regex" for r in audit)
