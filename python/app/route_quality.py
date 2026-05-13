"""Calibration metrics for route_skills MCP _meta and route events (local, no extra network)."""
from __future__ import annotations

import math
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
) -> dict[str, Any]:
    """Structured signals for operators and MCP hosts (JSON-serializable)."""
    n = len(facet_list)
    top_cos: float | None = None
    second_cos: float | None = None
    margin: float | None = None
    top_routing_score: float | None = None
    if facet_list:
        top_cos = round(coerce_route_float(facet_list[0].get("cosine_similarity")), 6)
        top_routing_score = round(coerce_route_float(facet_list[0].get("routing_score")), 6)
        if len(facet_list) > 1:
            second_cos = round(coerce_route_float(facet_list[1].get("cosine_similarity")), 6)
            margin = round(float(top_cos - second_cos), 6)

    agree = top1_cosine_vs_routing_agreement(facet_list) if router_hybrid not in ("", "off", None) else None

    try:
        prl = int(policy_rules_loaded)
    except (TypeError, ValueError):
        prl = 0
    prl = max(0, prl)

    return {
        "schema": "route_quality/1",
        "shortlist": {
            "size": n,
            "top_cosine_similarity": top_cos,
            "second_cosine_similarity": second_cos,
            "cosine_margin": margin,
            "top_routing_score": top_routing_score,
            "hybrid_mode": router_hybrid or "off",
            "top1_dense_and_fused_agree": agree,
        },
        "router": {
            "mode": router_mode,
            "pick_path": pick_path,
            "host_picked": host_picked,
            "host_shortlist_only": host_shortlist_only,
            "haiku_rerank_applied": haiku_rerank_applied,
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
