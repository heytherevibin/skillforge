"""Tests for route_quality telemetry (robust coercion, hybrid diagnostics)."""
from __future__ import annotations

from app.route_quality import (
    build_route_quality,
    coerce_route_float,
    policy_includes_added_count,
    top1_cosine_vs_routing_agreement,
)


def test_coerce_route_float() -> None:
    assert coerce_route_float("0.5") == 0.5
    assert coerce_route_float(None) == 0.0
    assert coerce_route_float("nope") == 0.0
    assert coerce_route_float(float("nan")) == 0.0
    assert coerce_route_float(float("inf")) == 0.0
    assert coerce_route_float(1.0, default=-1.0) == 1.0


def test_policy_includes_added_count() -> None:
    assert policy_includes_added_count(None) == 0
    assert policy_includes_added_count([{"effect": "added"}, {"effect": "skip"}, "bad", {}]) == 1


def test_top1_agreement() -> None:
    assert top1_cosine_vs_routing_agreement([]) is None
    assert top1_cosine_vs_routing_agreement([{"name": "a"}]) is None
    facets = [
        {"name": "high_route", "cosine_similarity": 0.1, "routing_score": 1.0},
        {"name": "high_cos", "cosine_similarity": 0.9, "routing_score": 0.2},
    ]
    assert top1_cosine_vs_routing_agreement(facets) is False
    facets2 = [
        {"name": "winner", "cosine_similarity": 0.9, "routing_score": 1.0},
        {"name": "lose", "cosine_similarity": 0.1, "routing_score": 0.2},
    ]
    assert top1_cosine_vs_routing_agreement(facets2) is True


def test_build_route_quality_empty_facets() -> None:
    rq = build_route_quality(
        facet_list=[],
        router_mode="auto",
        router_hybrid="off",
        picked_names=[],
        rerouted=False,
        change=float("nan"),
        policy_rules_loaded="bogus",
        policy_audit=None,
        host_picked=False,
        pick_path="embedding_top",
    )
    assert rq["shortlist"]["size"] == 0
    assert rq["shortlist"]["top_cosine_similarity"] is None
    assert rq["shortlist"]["confidence_tier"] is None
    assert rq["schema"] == "route_quality/2"
    assert rq["router"]["pick_diversify"]["applied"] is False
    assert rq["session"]["change_jaccard"] == 0.0
    assert rq["policy"]["rules_loaded"] == 0


def test_build_route_quality_malformed_metrics() -> None:
    facets = [
        {"name": "a", "cosine_similarity": "bad", "routing_score": float("nan")},
        {"name": "b", "cosine_similarity": 0.5, "routing_score": 0.2},
    ]
    rq = build_route_quality(
        facet_list=facets,
        router_mode="host",
        router_hybrid="weighted",
        picked_names=["a"],
        rerouted=True,
        change=0.25,
        policy_rules_loaded=-3,
        policy_audit=[{"effect": "added"}, {"effect": "added"}],
        host_picked=False,
        pick_path="haiku_pick",
    )
    assert rq["shortlist"]["top_cosine_similarity"] == 0.0
    assert rq["shortlist"]["top_routing_score"] == 0.0
    assert rq["shortlist"]["second_cosine_similarity"] == 0.5
    assert rq["shortlist"]["cosine_margin"] == round(-0.5, 6)
    assert rq["shortlist"]["ambiguous"] is True
    assert rq["shortlist"]["confidence_tier"] == "low"
    assert rq["shortlist"]["routing_score_margin"] == round(-0.2, 6)
    assert rq["shortlist"]["second_routing_score"] == 0.2
    assert rq["schema"] == "route_quality/2"
    assert rq["shortlist"]["top1_dense_and_fused_agree"] is False
    assert rq["policy"]["rules_loaded"] == 0
    assert rq["policy"]["includes_added"] == 2
    assert rq["picked_count"] == 1


def test_build_route_quality_hybrid_off_skips_agree() -> None:
    facets = [
        {"name": "x", "cosine_similarity": 0.1},
        {"name": "y", "cosine_similarity": 0.9},
    ]
    rq = build_route_quality(
        facet_list=facets,
        router_mode="auto",
        router_hybrid="off",
        picked_names=[],
        rerouted=False,
        change=0.0,
        policy_rules_loaded=0,
        policy_audit=[],
        host_picked=False,
        pick_path="embedding_top",
    )
    assert rq["shortlist"]["top1_dense_and_fused_agree"] is None
    assert rq["shortlist"]["cosine_leader_matches_routing_top"] is None


def test_build_route_quality_rules_loaded_ok() -> None:
    rq = build_route_quality(
        facet_list=[],
        router_mode="auto",
        router_hybrid="off",
        picked_names=[],
        rerouted=False,
        change=0.0,
        policy_rules_loaded=12,
        policy_audit=[],
        host_picked=False,
        pick_path="host_shortlist",
    )
    assert rq["policy"]["rules_loaded"] == 12


def test_build_route_quality_pick_diversify_meta() -> None:
    facets = [{"name": "x", "cosine_similarity": 0.5, "routing_score": 0.8}]
    div = {"applied": True, "dropped": ["z"], "max_per_source": 1}
    rq = build_route_quality(
        facet_list=facets,
        router_mode="auto",
        router_hybrid="off",
        picked_names=["x"],
        rerouted=False,
        change=0.0,
        policy_rules_loaded=0,
        policy_audit=[],
        host_picked=False,
        pick_path="haiku_pick",
        pick_diversify=div,
    )
    assert rq["router"]["pick_diversify"] == div


def test_build_route_quality_clear_shortlist_not_ambiguous(monkeypatch) -> None:
    facets = [
        {"name": "a", "cosine_similarity": 0.95, "routing_score": 0.9},
        {"name": "b", "cosine_similarity": 0.91, "routing_score": 0.84},
    ]
    monkeypatch.delenv("SKILLFORGE_ROUTE_AMBIGUITY_DISABLE", raising=False)
    rq = build_route_quality(
        facet_list=facets,
        router_mode="host",
        router_hybrid="keyword",
        picked_names=[],
        rerouted=False,
        change=0.0,
        policy_rules_loaded=0,
        policy_audit=[],
        host_picked=False,
        pick_path="host_shortlist",
    )
    assert rq["shortlist"]["ambiguous"] is False
    assert rq["shortlist"]["confidence_tier"] == "high"


def test_build_route_quality_ambiguity_disable_env(monkeypatch) -> None:
    facets = [
        {"name": "a", "cosine_similarity": 0.5, "routing_score": 0.9},
        {"name": "b", "cosine_similarity": 0.498, "routing_score": 0.89},
    ]
    monkeypatch.setenv("SKILLFORGE_ROUTE_AMBIGUITY_DISABLE", "1")
    rq = build_route_quality(
        facet_list=facets,
        router_mode="auto",
        router_hybrid="off",
        picked_names=[],
        rerouted=False,
        change=0.0,
        policy_rules_loaded=0,
        policy_audit=[],
        host_picked=False,
        pick_path="embedding_top",
    )
    assert rq["shortlist"]["ambiguous"] is False
    assert rq["shortlist"]["confidence_tier"] == "medium"
