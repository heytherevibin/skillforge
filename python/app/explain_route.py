"""Shared ``explain_route`` logic (MCP ``explain_route`` + ``skillforge route --explain``)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.main import MAX_ACTIVE_SKILLS, Router
from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION
from app.pick_diversify import diversify_picked_names
from app.redaction import redaction_enabled, redact_display_path
from app.route_policies import (
    build_routing_overlay_payload,
    load_route_policies_config,
    merge_policy_includes,
    merge_project_notes_into_route_query,
    parse_routing_overlay,
)
from app.routing_signals import build_route_query_text


def sanitize_explain_payload(explain: dict[str, Any]) -> dict[str, Any]:
    """Make explain meta JSON-safe (numpy scalars → Python floats)."""

    import numpy as np

    def _walk(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): _walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(x) for x in o]
        if isinstance(o, (str, bool, type(None))):
            return o
        if isinstance(o, (int,)):
            return o
        if isinstance(o, (float,)):
            return o
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        try:
            return float(o)
        except (TypeError, ValueError):
            return str(o)

    return _walk(explain)


async def compute_explain_route(
    router: Router,
    con: sqlite3.Connection,
    *,
    prompt: str,
    conversation: list[Any],
    limit: int,
    user_id: str,
    project_root: str | None,
    db_path: Path,
) -> tuple[str, dict[str, Any]]:
    """Return Markdown body + ``_meta`` shape matching MCP ``explain_route`` (does not touch sessions/events)."""
    policies_cfg = load_route_policies_config(project_root)
    overlay_audit: list[Any] = []
    exclude_skills, routing_boosts, project_notes = parse_routing_overlay(
        policies_cfg,
        by_name=router._by_name,
        audit_out=overlay_audit,
    )
    route_query = merge_project_notes_into_route_query(
        build_route_query_text(prompt, conversation),
        project_notes,
        project_root,
    )
    facets = router.shortlist_with_facets(
        route_query,
        con,
        k=limit,
        user_id=user_id,
        exclude_skills=exclude_skills,
        routing_boosts=routing_boosts,
    )
    candidates = router.shortlist(
        route_query,
        con,
        limit,
        user_id,
        exclude_skills=exclude_skills,
        routing_boosts=routing_boosts,
    )
    candidates = await router.rerank_candidates_haiku(route_query, conversation, candidates)
    picked_router, reasoning = await router.pick_final(
        prompt,
        conversation,
        candidates,
        route_query=route_query,
    )
    picked_before_pol, div_meta = diversify_picked_names(list(picked_router), router._by_name)
    merged, policy_audit = merge_policy_includes(
        prompt,
        picked_before_pol,
        policies_cfg,
        router._by_name,
        con,
        user_id,
        max_active=MAX_ACTIVE_SKILLS,
    )
    router_mode = "full" if router.router_llm else "embedding-only"
    notes_effective = bool(project_notes.strip() and (project_root or "").strip())
    routing_ov = build_routing_overlay_payload(
        project_root=project_root or "",
        exclude_skills=exclude_skills,
        routing_boosts=routing_boosts,
        project_notes_applied=notes_effective,
        project_notes_len=len(project_notes) if project_notes else 0,
        audit=overlay_audit,
    )
    explain_raw: dict[str, Any] = {
        "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
        "tool": "explain_route",
        "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
        "router_mode": router_mode,
        "embedding_shortlist": facets,
        "picked_router": picked_router,
        "picked_before_policy": picked_before_pol,
        "picked_after_policy": merged,
        "pick_diversify": div_meta,
        "router_reasoning": reasoning,
        "policy": {
            "rules_loaded": len(policies_cfg.get("rules") or [])
            if isinstance(policies_cfg.get("rules"), list)
            else 0,
            "audit": policy_audit,
        },
    }
    if routing_ov is not None:
        explain_raw["routing_overlay"] = routing_ov

    explain = sanitize_explain_payload(explain_raw)

    lines = [
        "# explain_route — routing diagnostics (no session writes)",
        "",
        f"**Router:** {router_mode}",
        f"**Picked (router):** {', '.join(picked_router) if picked_router else '_(none)_'}",
    ]
    if div_meta.get("applied"):
        lines.append(
            f"**After pick_diversify:** {', '.join(picked_before_pol) if picked_before_pol else '_(none)_'}"
        )
    lines.extend(
        [
            f"**After policies:** {', '.join(merged) if merged else '_(none)_'}",
            f"**Reasoning:** {reasoning}" if reasoning else "**Reasoning:** _(n/a)_",
            "",
            "## Shortlist (embedding)",
        ]
    )
    for f in facets[:15]:
        lines.append(
            f"- `{f['name']}` cos={f['cosine_similarity']} weight={f['learned_weight']} "
            f"score={f['routing_score']}"
        )
    if policy_audit:
        lines.extend(["", "## Policy audit"])
        for row in policy_audit[:30]:
            lines.append(f"- {row}")
    body = "\n".join(lines)
    return body, explain
