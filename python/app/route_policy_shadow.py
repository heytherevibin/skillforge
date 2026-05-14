"""Alternate policy embedding shortlist comparison (telemetry only).

Runs a second ``shortlist_with_facets`` against the **pre-project-notes routing query**, which matches
production: **conversation + operator memories** (when ``SKILLFORGE_ROUTE_MEMORY``) but excludes
policy ``project_notes``. When ``route_query_base`` passed from ``run_route_turn`` includes memories,
shadow comparisons stay aligned with primary routing."""

from __future__ import annotations

from typing import Any


def attach_policy_shadow_to_route_quality(
    route_quality: dict[str, Any],
    *,
    router: Any,
    con: Any,
    route_query_base: str,
    project_root: str,
    shadow_cfg: dict[str, Any] | None,
    shadow_provenance: str | None,
    user_id: str,
    primary_facets: list[dict[str, Any]],
    compare_k_preferred: int,
) -> None:
    """Mutation: add ``policy_shadow`` to ``route_quality`` when shadow config is loaded."""
    if not isinstance(shadow_cfg, dict) or not shadow_provenance:
        return
    ck = max(1, min(int(compare_k_preferred), 50))

    from app.route_policies import merge_project_notes_into_route_query, parse_routing_overlay

    exclude_s, boosts_s, notes_s = parse_routing_overlay(
        shadow_cfg, by_name=router._by_name, audit_out=None
    )
    pr = project_root.strip() if project_root else ""
    route_query_s = merge_project_notes_into_route_query(route_query_base, notes_s, pr or None)
    shadow_facets = router.shortlist_with_facets(
        route_query_s,
        con,
        k=ck,
        user_id=user_id,
        exclude_skills=exclude_s,
        routing_boosts=boosts_s,
    )

    pnames = [str(f.get("name") or "") for f in primary_facets[:ck] if f.get("name")]
    snames = [str(f.get("name") or "") for f in shadow_facets[:ck] if f.get("name")]
    set_p, set_s = set(pnames), set(snames)
    inter = set_p & set_s
    union = set_p | set_s
    jacc = (len(inter) / len(union)) if union else 1.0

    rules_n = len(shadow_cfg.get("rules") or []) if isinstance(shadow_cfg.get("rules"), list) else 0

    route_quality["policy_shadow"] = {
        "schema": "policy_shadow_compare/1",
        "compare_k": ck,
        "source": shadow_provenance,
        "primary_head": pnames,
        "shadow_head": snames,
        "jaccard_topk": round(jacc, 4),
        "only_in_primary": sorted(set_p - set_s),
        "only_in_shadow": sorted(set_s - set_p),
        "shadow_rules_loaded": rules_n,
        "overlay_note": "Shadow applies exclude_skills/boosts/project_notes to embedding shortlist only; "
        "regex rule includes merge after pick and are intentionally not mirrored here.",
    }
