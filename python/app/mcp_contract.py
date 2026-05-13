"""Shared MCP response shape for ``route_skills`` (and CLI parity).

Versioned ``_meta`` with ``sources[]`` and ``budget``. Schema **1.1** adds
per-chunk ``sources`` when ``context_items`` (RAG chunks) are returned from Phase 1.
Schema **1.2** adds ``kind: file`` sources and project chunk char counts in ``budget``.
Schema **1.4** adds optional ``context_redaction`` (hit counts when scrubbing is on).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol

from app.redaction import redaction_enabled, redact_display_path


class _SkillBody(Protocol):
    name: str
    body: str


MCP_RESPONSE_SCHEMA_VERSION = "1.4"


def build_route_skills_meta(
    *,
    result: dict[str, Any],
    picked_names: list[str],
    user_id: str,
    db_path: Path | str,
    skills_map: Mapping[str, _SkillBody],
    response_text: str,
    error: str | None = None,
    context_items: list[dict[str, Any]] | None = None,
    fusion: dict[str, Any] | None = None,
    context_redaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ``_meta`` for a route_skills-style response (success or structured error)."""
    sources: list[dict[str, Any]] = []
    chars_skill = 0
    chars_project = 0

    if context_items:
        for c in context_items:
            tlen = len(c.get("text") or "")
            ref_path = c.get("path")
            if ref_path:
                row = {
                    "kind": "file",
                    "ref": ref_path,
                    "line_start": c.get("line_start"),
                    "line_end": c.get("line_end"),
                    "score": round(float(c.get("score", 0.0)), 6),
                }
                if c.get("mmr_rank") is not None:
                    row["mmr_rank"] = int(c["mmr_rank"])
                sources.append(row)
                chars_project += tlen
            else:
                row = {
                    "kind": "skill",
                    "ref": c["skill"],
                    "line_start": c.get("line_start"),
                    "line_end": c.get("line_end"),
                    "score": round(float(c.get("score", 0.0)), 6),
                }
                if c.get("mmr_rank") is not None:
                    row["mmr_rank"] = int(c["mmr_rank"])
                sources.append(row)
                chars_skill += tlen
    else:
        for n in picked_names:
            s = skills_map.get(n)
            if s is not None:
                sources.append({
                    "kind": "skill",
                    "ref": n,
                    "line_start": None,
                    "line_end": None,
                    "score": None,
                })
                chars_skill += len(s.body)

    chars_body = chars_skill + chars_project

    candidates_raw = result.get("candidates") or []
    candidates_preview: list[dict[str, Any]] = []
    for item in candidates_raw[:15]:
        if isinstance(item, tuple) and len(item) == 2:
            sk, sc = item
            name = getattr(sk, "name", None)
            if name is not None:
                candidates_preview.append({"name": name, "score": round(float(sc), 6)})

    meta: dict[str, Any] = {
        "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
        "sources": sources,
        "budget": {
            "chars_skill_bodies": chars_skill,
            "chars_project_chunks": chars_project,
            "chars_context_items_total": chars_body,
            "chars_response_total": len(response_text),
            "est_tokens_approx": max(1, len(response_text) // 4),
        },
        "picked": list(picked_names),
        "reasoning": result.get("reasoning"),
        "session_id": result.get("session_id"),
        "user_id": user_id,
        "rerouted": result.get("rerouted"),
        "change_pct": round(float(result.get("change", 0)) * 100, 1),
        "route_ms": round(float(result.get("route_ms", 0)), 1),
        "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
        "candidates_preview": candidates_preview,
        "context_items_count": len(context_items or []),
    }
    if fusion is not None and fusion.get("enabled"):
        meta["fusion"] = fusion
    if context_redaction is not None:
        meta["context_redaction"] = context_redaction
    if error:
        meta["error"] = error
    return meta
