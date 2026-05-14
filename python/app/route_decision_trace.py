"""Routing decision tracing for MCP `_meta` and optional persisted `events` rows.

Operators set ``SKILLFORGE_ROUTE_TRACE_LEVEL``:

- ``off`` (default) — MCP responses still include correlation id on the result dict;
  optional ``decision_trace`` in `_meta` is omitted (see ``build_route_skills_meta``).
- ``compact`` — `_meta.decision_trace` with digest + shortlists + routing flags.
- ``full`` — ``compact`` fields plus ``route_quality_snapshot`` in ``decision_trace``.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def route_trace_level() -> str:
    v = os.getenv("SKILLFORGE_ROUTE_TRACE_LEVEL", "off").strip().lower()
    if v == "full":
        return "full"
    if v in ("compact", "1", "true", "yes", "on"):
        return "compact"
    return "off"


def decision_digest(
    *,
    picked_names: list[str],
    candidate_names: list[str],
    pick_path: str,
    host_shortlist_only: bool,
    dry_run: bool,
    route_ms: float,
) -> str:
    """Short stable fingerprint for correlating responses with ``events``."""

    blob = json.dumps(
        {
            "picked": list(picked_names),
            "candidates_head": list(candidate_names[:25]),
            "pick_path": pick_path,
            "host_shortlist_only": host_shortlist_only,
            "dry_run": dry_run,
            "route_ms": round(float(route_ms), 3),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_decision_trace(
    *,
    trace_id: str,
    level: str,
    dry_run: bool,
    host_shortlist_only: bool,
    pick_path: str,
    haiku_rerank_applied: bool,
    policy_rules_loaded: int,
    routing_overlay_applied: bool,
    picked_names: list[str],
    candidate_names: list[str],
    route_ms: float,
    route_quality: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if level == "off":
        return None
    digest = decision_digest(
        picked_names=picked_names,
        candidate_names=candidate_names,
        pick_path=pick_path,
        host_shortlist_only=host_shortlist_only,
        dry_run=dry_run,
        route_ms=route_ms,
    )
    out: dict[str, Any] = {
        "trace_id": trace_id,
        "digest": digest,
        "level": level,
        "dry_run": dry_run,
        "host_shortlist_only": host_shortlist_only,
        "pick_path": pick_path,
        "haiku_rerank_applied": haiku_rerank_applied,
        "policy_rules_loaded": int(policy_rules_loaded),
        "routing_overlay_applied": routing_overlay_applied,
        "candidate_names_preview": list(candidate_names[:15]),
        "picked_names": list(picked_names),
    }
    if level == "full" and isinstance(route_quality, dict):
        out["route_quality_snapshot"] = route_quality
    return out
