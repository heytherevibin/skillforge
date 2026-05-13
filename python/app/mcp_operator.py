"""Shared logic for MCP operator/observability tools (read-only SQLite + env snapshots)."""
from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.main import Router
from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION
from app.npm_pkg_version import published_package_version
from app.project_index import ensure_project_index_schema
from app.routing_signals import host_pick_max_candidates

# MCP events_recent caps (keep LLM-visible text bounded; `_meta.rows` retains JSON payloads).
EVENTS_META_ROW_CAP = 100
EVENTS_MARKDOWN_PREVIEW_MAX_LINES = 150

# Keep insertion order aligned with MCPServer.handle_tools_list (`app/mcp_server.py`).
MCP_PUBLISHED_TOOL_NAMES: tuple[str, ...] = (
    "route_skills",
    "search_skills",
    "explain_route",
    "get_skill",
    "list_skills",
    "skill_feedback",
    "disable_skill",
    "skill_referenced",
    "materialize_project",
    "skillforge_bootstrap",
    "capabilities",
    "get_router_status",
    "project_index_status",
    "weights_snapshot",
    "events_recent",
)


def _truthy(env_name: str, default: str = "0") -> bool:
    return os.getenv(env_name, default).strip().lower() not in ("0", "false", "no", "")


def build_router_status_dict(router: Router | None, *, skill_count: int) -> dict[str, Any]:
    """JSON-serializable operator snapshot for get_router_status."""
    from app import main as m

    r = router
    rl = getattr(r, "router_llm", None) if r else None
    backend = "none"
    if rl is not None:
        backend = getattr(rl, "backend_name", "unknown")
    anth_ok = bool(r and r.anthropic is not None)
    return {
        "skillforge_router_mode": m.SKILLFORGE_ROUTER_MODE,
        "top_k_candidates": m.TOP_K_CANDIDATES,
        "max_active_skills": m.MAX_ACTIVE_SKILLS,
        "reroute_threshold": m.REROUTE_THRESHOLD,
        "embed_model": m.EMBED_MODEL,
        "router_model": m.ROUTER_MODEL,
        "anthropic_available": anth_ok,
        "router_llm_backend": backend,
        "router_llm_active": bool(rl is not None),
        "context_mode": r.context_mode if r else m.SKILLFORGE_CONTEXT_MODE,
        "router_hybrid": r._hybrid_mode if r else m.ROUTER_HYBRID_MODE,
        "router_hybrid_alpha": round(m.ROUTER_HYBRID_ALPHA, 4),
        "haiku_rerank_enabled": _truthy("SKILLFORGE_HAIKU_RERANK", "0"),
        "skills_loaded_count": skill_count,
        "host_pick_max": host_pick_max_candidates(top_k_cap=m.TOP_K_CANDIDATES),
        "pick_diversify_enabled": _truthy("SKILLFORGE_PICK_DIVERSIFY", "0"),
        "pick_max_per_source": os.getenv("SKILLFORGE_PICK_MAX_PER_SOURCE", "2").strip(),
        "route_ambiguity_disabled": _truthy("SKILLFORGE_ROUTE_AMBIGUITY_DISABLE", "0"),
        "mcp_server_semver": published_package_version(),
    }


def format_capabilities_markdown(bundle: dict[str, Any]) -> str:
    return (
        "# Skillforge — capabilities (session bootstrap)\n\n"
        "Single JSON bundle: MCP response schema, package semver, tool names, progressive loading hints, "
        "and `router_snapshot` (same payload shape as `get_router_status`).\n\n```json\n"
        f"{json.dumps(bundle, indent=2)}\n```"
    )


def build_capabilities_bundle(router: Router | None, *, skill_count: int) -> dict[str, Any]:
    """Session-start bundle: versioning + advertised tools + router env snapshot."""
    return {
        "bundle_version": "1",
        "mcp_response_schema_version": MCP_RESPONSE_SCHEMA_VERSION,
        "package_semver": published_package_version(),
        "mcp_tools": list(MCP_PUBLISHED_TOOL_NAMES),
        "progressive_loading": {
            "get_skill_formats": ["card", "summary", "full"],
            "note": "`card`: routing-card text only; see `get_skill.format`. `summary|full`: SKILL.md excerpts.",
        },
        "replay_cli": {"command": "skillforge replay [--session-id=…] [--user=…] [--json]"},
        "user_env_profile": {
            "file": "~/.skillforge/env",
            "path_command": "skillforge config path",
            "init_command": "skillforge config init [--force]",
            "validate_command": "skillforge config validate",
        },
        "tools_command": {"command": "skillforge tools … [--json] · skillforge tools -h (MCP parity subcommands)"},
        "route_cli_hints": {
            "interactive_tty": "-i or SKILLFORGE_ROUTE_INTERACTIVE=1 after host-mode shortlist",
            "json_stdout": "--json (phases host_shortlist_prompt · host_shortlist_static · context · explain_only)",
            "explain_flags": "--explain · --explain-only",
        },
        "tips_command": "skillforge tips",
        "standalone_agent": {"command": "skillforge agent [--prompt TEXT] (--base-url, --model)"},
        "manifest": {
            "strict_catalog_env": "SKILLFORGE_SKILL_MANIFEST_STRICT",
            "lint_command": "skillforge skills lint [paths]",
        },
        "router_snapshot": build_router_status_dict(router, skill_count=skill_count),
    }


def project_index_status_dict(con: sqlite3.Connection) -> dict[str, Any]:
    ensure_project_index_schema(con)
    cur = con.execute("SELECT COUNT(*) FROM project_chunks")
    chunk_count = int(cur.fetchone()[0])
    cur = con.execute("SELECT COUNT(DISTINCT path) FROM project_chunks")
    file_count = int(cur.fetchone()[0])
    meta: dict[str, Any] = {
        "chunk_count": chunk_count,
        "distinct_paths": file_count,
    }
    cur = con.execute("SELECT key, value FROM project_index_meta")
    raw_meta = {row[0]: row[1] for row in cur.fetchall()}
    embed_model = raw_meta.get("embed_model")
    if embed_model:
        meta["embed_model"] = embed_model
    edim = raw_meta.get("embedding_dim")
    if edim:
        meta["embedding_dim"] = edim
    ts = raw_meta.get("last_index_ts")
    if ts:
        try:
            ft = float(ts)
            meta["last_index_ts"] = ft if math.isfinite(ft) else None
        except ValueError:
            meta["last_index_ts"] = None
    stats_raw = raw_meta.get("last_index_stats")
    if stats_raw:
        try:
            meta["last_index_stats"] = json.loads(stats_raw)
        except json.JSONDecodeError:
            meta["last_index_stats"] = None
    return meta


def events_recent_rows(
    con: sqlite3.Connection,
    *,
    limit: int,
    user_id: str = "",
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    uid = user_id.strip()
    if event_type and str(event_type).strip():
        et = str(event_type).strip()
        cur = con.execute(
            "SELECT ts, session_id, event_type, payload FROM events "
            "WHERE user_id = ? AND event_type = ? ORDER BY ts DESC LIMIT ?",
            (uid, et, lim),
        )
    else:
        cur = con.execute(
            "SELECT ts, session_id, event_type, payload FROM events "
            "WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
            (uid, lim),
        )
    rows: list[dict[str, Any]] = []
    for ts, sid, et_, payload in cur.fetchall():
        row: dict[str, Any] = {
            "ts": float(ts) if ts is not None else None,
            "session_id": sid,
            "event_type": et_,
        }
        if payload:
            try:
                row["payload"] = json.loads(payload)
            except json.JSONDecodeError:
                row["payload"] = payload
        else:
            row["payload"] = None
        rows.append(row)
    return rows


def format_router_status_markdown(snapshot: dict[str, Any]) -> str:
    lines = ["# Skillforge — router status", ""]
    for k, v in snapshot.items():
        lines.append(f"- **{k}:** `{v}`")
    return "\n".join(lines)


def format_project_index_markdown(snapshot: dict[str, Any], root: Path) -> str:
    lines = [
        "# Skillforge — project index",
        "",
        f"**Orchestrator DB root:** `{root}`",
        f"**Chunk rows:** `{snapshot.get('chunk_count', 0)}`",
        f"**Distinct paths:** `{snapshot.get('distinct_paths', 0)}`",
    ]
    if snapshot.get("embed_model"):
        lines.append(f"**Embed model (at index):** `{snapshot['embed_model']}`")
    if snapshot.get("embedding_dim"):
        lines.append(f"**Embedding dim:** `{snapshot['embedding_dim']}`")
    if snapshot.get("last_index_ts") is not None:
        lines.append(f"**Last index unix ts:** `{snapshot['last_index_ts']}`")
    stats = snapshot.get("last_index_stats")
    if isinstance(stats, dict) and stats:
        lines.extend(["", "## Last index run", "```json", json.dumps(stats, indent=2), "```"])
    return "\n".join(lines)


def format_events_markdown(
    rows: list[dict[str, Any]],
    *,
    preview_max_lines: int = EVENTS_MARKDOWN_PREVIEW_MAX_LINES,
) -> str:
    lines = [f"# Skillforge — recent events ({len(rows)} rows)", ""]
    cap_lines = max(1, preview_max_lines)
    display = rows[:cap_lines]
    for r in display:
        et = r.get("event_type") or "?"
        sid = (r.get("session_id") or "-")[:12]
        ts = r.get("ts")
        preview = ""
        p = r.get("payload")
        if isinstance(p, dict):
            if et == "route":
                preview = str(p.get("picked") or p.get("picked_names") or "")[:160]
            elif et == "host_shortlist":
                preview = f"candidates={len(p.get('candidates') or [])}"
            elif et == "feedback":
                preview = f"skill={p.get('skill')}"
            else:
                preview = json.dumps(p)[:120]
        lines.append(f"- **{ts}** `{et}` session=`{sid}` {preview}".strip())
    if len(rows) > len(display):
        lines.append("")
        lines.append(
            f"_Markdown preview truncated ({len(display)} of {len(rows)} rows). "
            f"Use `_meta.rows` (cap {EVENTS_META_ROW_CAP} JSON rows) for structured payloads._"
        )
    return "\n".join(lines)
