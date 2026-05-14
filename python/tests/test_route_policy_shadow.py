"""Tests for alternate policy embedding shortlist (shadow) comparison telemetry."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.route_policies import load_shadow_route_policies_config
from app.route_policy_shadow import attach_policy_shadow_to_route_quality


def test_load_shadow_inline_json(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", raising=False)
    monkeypatch.setenv('SKILLFORGE_ROUTE_POLICIES_SHADOW', '{"exclude_skills":["x"]}')
    cfg, prov = load_shadow_route_policies_config()
    assert cfg == {"exclude_skills": ["x"]}
    assert prov == "shadow:inline_json"


def test_load_shadow_inline_wins_over_file(monkeypatch, tmp_path) -> None:
    p = tmp_path / "shadow.json"
    p.write_text('{"exclude_skills":["from-file"]}')
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", raising=False)
    monkeypatch.setenv('SKILLFORGE_ROUTE_POLICIES_SHADOW', '{"exclude_skills":["from-inline"]}')
    monkeypatch.setenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", str(p))
    cfg, _prov = load_shadow_route_policies_config()
    assert cfg == {"exclude_skills": ["from-inline"]}


def test_load_shadow_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", raising=False)
    p = tmp_path / "shadow.json"
    p.write_text('{"routing_boosts": {"skill-a": 0.5}}')
    monkeypatch.setenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", str(p))
    cfg, prov = load_shadow_route_policies_config()
    assert cfg == {"routing_boosts": {"skill-a": 0.5}}
    assert str(p.resolve()) in prov


def test_load_shadow_missing_file(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", raising=False)
    monkeypatch.setenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", "/nonexistent/shadow-policies.json")
    cfg, prov = load_shadow_route_policies_config()
    assert cfg is None and prov is None
    assert "not found" in capsys.readouterr().err


def test_load_shadow_invalid_inline_json(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", raising=False)
    monkeypatch.setenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", '{"bad"')
    cfg, prov = load_shadow_route_policies_config()
    assert cfg is None and prov is None
    assert capsys.readouterr().err


def test_load_shadow_disabled_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", raising=False)
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE", raising=False)
    assert load_shadow_route_policies_config() == (None, None)


@pytest.mark.parametrize(
    "primary,shadow,expected_jacc",
    [
        ([{"name": "a"}, {"name": "b"}], [{"name": "b"}, {"name": "c"}], 0.3333),
        ([{"name": "a"}], [{"name": "a"}], 1.0),
    ],
)
def test_attach_policy_shadow_jaccard(primary, shadow, expected_jacc, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", raising=False)
    rqm: dict = {}
    router = MagicMock()
    router._by_name = {}
    router.shortlist_with_facets.return_value = shadow
    attach_policy_shadow_to_route_quality(
        rqm,
        router=router,
        con=None,
        route_query_base="base query",
        project_root="",
        shadow_cfg={"rules": [{}]},
        shadow_provenance="shadow:inline_json",
        user_id="u1",
        primary_facets=primary,
        compare_k_preferred=10,
    )
    ps = rqm["policy_shadow"]
    assert ps["schema"] == "policy_shadow_compare/1"
    assert ps["jaccard_topk"] == expected_jacc
    assert ps["shadow_rules_loaded"] == 1


def test_attach_skips_when_not_configured() -> None:
    rqm: dict = {}
    router = MagicMock()
    router.shortlist_with_facets = MagicMock()
    attach_policy_shadow_to_route_quality(
        rqm,
        router=router,
        con=None,
        route_query_base="x",
        project_root="",
        shadow_cfg=None,
        shadow_provenance=None,
        user_id="",
        primary_facets=[{"name": "a"}],
        compare_k_preferred=5,
    )
    assert "policy_shadow" not in rqm
    router.shortlist_with_facets.assert_not_called()


def test_shadow_reuses_base_query_notes_not_primary(monkeypatch) -> None:
    """Shadow overlays merge shadow project_notes onto base routing text — not prod merged query."""
    rqm = {}
    router = MagicMock()
    router._by_name = {}
    router.shortlist_with_facets.return_value = []

    def _shortlist(rq, *_args, **_kwargs):  # noqa: ANN001
        captured["rq"] = rq
        return []

    captured: dict[str, str] = {}
    router.shortlist_with_facets.side_effect = _shortlist
    monkeypatch.delenv("SKILLFORGE_ROUTE_POLICIES_SHADOW", raising=False)
    attach_policy_shadow_to_route_quality(
        rqm,
        router=router,
        con=None,
        route_query_base="BASE_ONLY",
        project_root="/tmp/proj",
        shadow_cfg={"project_notes": "shadow hint"},
        shadow_provenance="shadow:inline_json",
        user_id="",
        primary_facets=[{"name": "a"}],
        compare_k_preferred=5,
    )
    rq = captured.get("rq", "")
    assert rq.startswith("Project routing notes:")
    assert "shadow hint" in rq
    assert "BASE_ONLY" in rq

