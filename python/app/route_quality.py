"""Calibration metrics for route_skills MCP _meta and route events (local, no extra network)."""
from __future__ import annotations

import math
import os
from typing import Any


def coerce_route_float(x: Any, *, default: float = 0.0) -> float:
    """Coerce to float for routing telemetry; never raises; maps NaN/inf to default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def policy_includes_added_count(audit: list[dict[str, Any]] | None) -> int:
    if not audit:
        return 0
    return sum(1 for row in audit if isinstance(row, dict) and row.get("effect") == "added")


def top1_cosine_vs_routing_agreement(facets: list[dict[str, Any]]) -> bool | None:
    """Whether the #1 by routing_score matches the skill with max cosine (hybrid diagnostic)."""
    if len(facets) < 2:
        return None
    top_route = facets[0].get("name")
    best_cos_name = max(facets, key=lambda f: coerce_route_float(f.get("cosine_similarity"))).get("name")
    if not top_route or not best_cos_name:
        return None
    return top_route == best_cos_name


def _env_float(name: str, default_str: str) -> float:
    raw = os.getenv(name, default_str).strip()
    try:
        return float(raw)
    except ValueError:
        return float(default_str)


def _compute_ambiguous_and_tier(
    *,
    n: int,
    cosine_margin: float | None,
    routing_score_margin: float | None,
) -> tuple[bool, str | None]:
    """Return (ambiguous, confidence_tier)."""
    if n == 0:
        return False, None
    if n == 1:
        return False, "high"
    ambig_off = os.getenv("SKILLFORGE_ROUTE_AMBIGUITY_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if ambig_off:
        ambiguous = False
    else:
        cos_thr = _env_float("SKILLFORGE_ROUTE_AMBIGUITY_COS_MARGIN", "0.012")
        route_thr = _env_float("SKILLFORGE_ROUTE_AMBIGUITY_ROUTE_MARGIN", "0.018")
        ambiguous = False
        if cosine_margin is not None and cosine_margin < cos_thr:
            ambiguous = True
        if routing_score_margin is not None and routing_score_margin < route_thr:
            ambiguous = True
    tier: str
    if ambiguous:
        tier = "low"
    elif cosine_margin is not None and routing_score_margin is not None:
        if cosine_margin >= 0.04 and routing_score_margin >= 0.06:
            tier = "high"
        else:
            tier = "medium"
    else:
        tier = "medium"
    return ambiguous, tier


def build_route_quality(
    *,
    facet_list: list[dict[str, Any]],
    router_mode: str,
    router_hybrid: str,
    picked_names: list[str],
    rerouted: bool,
    change: float,
    policy_rules_loaded: int,
    policy_audit: list[dict[str, Any]] | None,
    host_picked: bool,
    host_shortlist_only: bool = False,
    haiku_rerank_applied: bool = False,
    pick_path: str,
    pick_diversify: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured signals for operators and MCP hosts (JSON-serializable)."""
    n = len(facet_list)
    top_cos: float | None = None
    second_cos: float | None = None
    margin: float | None = None
    top_routing_score: float | None = None
    second_routing_score: float | None = None
    routing_score_margin: float | None = None
    if facet_list:
        top_cos = round(coerce_route_float(facet_list[0].get("cosine_similarity")), 6)
        top_routing_score = round(coerce_route_float(facet_list[0].get("routing_score")), 6)
        if len(facet_list) > 1:
            second_cos = round(coerce_route_float(facet_list[1].get("cosine_similarity")), 6)
            margin = round(float(top_cos - second_cos), 6)
            second_routing_score = round(coerce_route_float(facet_list[1].get("routing_score")), 6)
            if top_routing_score is not None and second_routing_score is not None:
                routing_score_margin = round(float(top_routing_score - second_routing_score), 6)

    agree = top1_cosine_vs_routing_agreement(facet_list) if router_hybrid not in ("", "off", None) else None
    ambiguous, confidence_tier = _compute_ambiguous_and_tier(
        n=n,
        cosine_margin=margin,
        routing_score_margin=routing_score_margin,
    )

    try:
        prl = int(policy_rules_loaded)
    except (TypeError, ValueError):
        prl = 0
    prl = max(0, prl)

    div = pick_diversify if isinstance(pick_diversify, dict) else None
    if div is None:
        div = {"applied": False, "dropped": [], "max_per_source": None}

    return {
        "schema": "route_quality/2",
        "shortlist": {
            "size": n,
            "top_cosine_similarity": top_cos,
            "second_cosine_similarity": second_cos,
            "cosine_margin": margin,
            "second_routing_score": second_routing_score,
            "routing_score_margin": routing_score_margin,
            "ambiguous": ambiguous,
            "confidence_tier": confidence_tier,
            "top_routing_score": top_routing_score,
            "hybrid_mode": router_hybrid or "off",
            "top1_dense_and_fused_agree": agree,
            "cosine_leader_matches_routing_top": agree,
        },
        "router": {
            "mode": router_mode,
            "pick_path": pick_path,
            "host_picked": host_picked,
            "host_shortlist_only": host_shortlist_only,
            "haiku_rerank_applied": haiku_rerank_applied,
            "pick_diversify": div,
        },
        "session": {
            "rerouted": rerouted,
            "change_jaccard": round(coerce_route_float(change), 4),
            "change_pct": round(coerce_route_float(change) * 100.0, 1),
        },
        "policy": {
            "rules_loaded": prl,
            "includes_added": policy_includes_added_count(policy_audit),
            "audit_size": len(policy_audit or []),
        },
        "picked_count": len(picked_names),
    }
