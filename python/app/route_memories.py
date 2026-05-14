"""Governed operator memories fused into the embedding routing query (Phase 2).

Rows are scoped by ``user_id`` and optional ``project_scope`` (normalized `''` = user-global vs
resolved path). Enable with ``SKILLFORGE_ROUTE_MEMORY``; cap with ``SKILLFORGE_ROUTE_MEMORY_MAX_*``.
Optional ``SKILLFORGE_ROUTE_MEMORY_DEDUP`` coalesces re-appends of the same normalized body.
Optional ``SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS`` sorts/ranks by softened importance.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def ensure_route_memory_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS route_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            project_scope TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            skill_hint TEXT NOT NULL DEFAULT '',
            importance INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            expires_at REAL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_route_memories_lookup "
        "ON route_memories(user_id, project_scope, importance DESC, created_at DESC)"
    )
    con.commit()


def normalize_project_scope(project_root: str | None) -> str:
    pr = (project_root or "").strip()
    if not pr:
        return ""
    try:
        return str(Path(pr).expanduser().resolve())
    except OSError:
        return pr


def route_memory_enabled() -> bool:
    return os.getenv("SKILLFORGE_ROUTE_MEMORY", "").strip().lower() in ("1", "true", "yes", "on")


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "")


def route_memory_dedup_enabled() -> bool:
    return _env_truthy("SKILLFORGE_ROUTE_MEMORY_DEDUP", "0")


def memory_importance_half_life_days() -> float | None:
    raw = os.getenv("SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS", "").strip()
    if not raw:
        return None
    try:
        h = float(raw)
    except ValueError:
        return None
    if h <= 0:
        return None
    return h


def _max_chars() -> int:
    try:
        return max(0, int(os.getenv("SKILLFORGE_ROUTE_MEMORY_MAX_CHARS", "1200")))
    except ValueError:
        return 1200


def _max_rows() -> int:
    try:
        n = int(os.getenv("SKILLFORGE_ROUTE_MEMORY_MAX_ROWS", "8"))
    except ValueError:
        return 8
    return max(1, min(n, 50))


def _default_ttl_days() -> float | None:
    raw = os.getenv("SKILLFORGE_ROUTE_MEMORY_DEFAULT_TTL_DAYS", "").strip()
    if not raw:
        return None
    try:
        d = float(raw)
    except ValueError:
        return None
    return d if d > 0 else None


def normalize_body_for_dedup(body: str) -> str:
    """Collapse whitespace for dedup key (trim + split join). Case-sensitive."""
    return " ".join((body or "").strip().split())


def memory_effective_importance(stored: int, *, created_at: float, now: float) -> float:
    """``importance × 2^(-age_days / H)``; identity when half-life unset."""
    h = memory_importance_half_life_days()
    imp = float(stored)
    if h is None:
        return imp
    age_days = max(0.0, (float(now) - float(created_at)) / 86400.0)
    return imp * (2.0 ** (-age_days / h))


def route_memory_cap_snapshot() -> dict[str, Any]:
    """Expose env caps for MCP ``get_router_status`` / operator introspection."""
    return {
        "fusion_env_enabled": route_memory_enabled(),
        "max_chars": _max_chars(),
        "max_rows": _max_rows(),
        "default_ttl_days": _default_ttl_days(),
        "dedup_enabled": route_memory_dedup_enabled(),
        "importance_half_life_days": memory_importance_half_life_days(),
    }


def compact_route_memory_for_event(meta: dict[str, Any] | None, *, max_ids: int = 32) -> dict[str, Any]:
    """Subset for persisted ``route`` / ``host_shortlist`` events (replay-friendly)."""
    if not isinstance(meta, dict):
        return {}
    mids = meta.get("memory_ids")
    ids_out: Any = mids
    if isinstance(mids, list) and len(mids) > max_ids:
        ids_out = mids[:max_ids]
    return {
        "schema": "route_memory_event/1",
        "enabled": bool(meta.get("enabled")),
        "applied": bool(meta.get("applied")),
        "rows_used": int(meta.get("rows_used") or 0),
        "chars": int(meta.get("chars") or 0),
        "truncated": bool(meta.get("truncated")),
        "memory_ids": ids_out,
        "importance_decay_active": bool(meta.get("importance_decay_active")),
    }


def cleanup_expired_route_memories(con: sqlite3.Connection, *, now: float | None = None) -> int:
    t = float(now if now is not None else time.time())
    con.execute(
        "DELETE FROM route_memories WHERE expires_at IS NOT NULL AND expires_at < ?",
        (t,),
    )
    row = con.execute("SELECT changes()").fetchone()
    n = int(row[0]) if row else 0
    con.commit()
    return n


def _find_duplicate_memory_id(
    con: sqlite3.Connection,
    *,
    user_id: str,
    project_scope_norm: str,
    body_key: str,
    now: float,
) -> str | None:
    uid = (user_id or "").strip()
    scope = project_scope_norm or ""
    cur = con.execute(
        """
        SELECT id, body FROM route_memories
        WHERE user_id = ?
          AND project_scope = ?
          AND (expires_at IS NULL OR expires_at >= ?)
        """,
        (uid, scope, float(now)),
    )
    for r in cur.fetchall():
        if normalize_body_for_dedup(str(r[1])) == body_key:
            return str(r[0])
    return None


def fetch_active_memories_for_route(
    con: sqlite3.Connection,
    *,
    user_id: str,
    project_scope_norm: str,
    now: float,
    limit: int,
) -> list[tuple[str, str, int, float, float | None]]:
    """Rows: (id, body, importance, created_at, expires_at)."""
    uid = (user_id or "").strip()
    scope = project_scope_norm or ""
    halflife = memory_importance_half_life_days()
    pool = int(limit)
    if halflife is not None:
        pool = min(200, max(pool, pool * 25))

    cur = con.execute(
        """
        SELECT id, body, importance, created_at, expires_at
        FROM route_memories
        WHERE user_id = ?
          AND (expires_at IS NULL OR expires_at >= ?)
          AND (project_scope = '' OR project_scope = ?)
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
        """,
        (uid, float(now), scope, int(pool)),
    )
    rows = [
        (
            str(r[0]),
            str(r[1]),
            int(r[2]),
            float(r[3]),
            float(r[4]) if r[4] is not None else None,
        )
        for r in cur.fetchall()
    ]
    if halflife is None:
        return rows[: int(limit)]

    rows.sort(
        key=lambda x: memory_effective_importance(x[2], created_at=x[3], now=now),
        reverse=True,
    )
    return rows[: int(limit)]


def merge_operator_memories_into_route_query(
    route_query: str,
    con: sqlite3.Connection,
    *,
    user_id: str,
    project_root: str | None,
    now: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Append bounded memory slice before policy ``project_notes`` merge. Schema ``route_memory_fusion/1``."""
    stub: dict[str, Any] = {
        "schema": "route_memory_fusion/1",
        "enabled": False,
        "applied": False,
        "rows_used": 0,
        "chars": 0,
        "memory_ids": [],
        "truncated": False,
        "importance_decay_active": False,
    }
    h_days = memory_importance_half_life_days()
    if h_days is not None:
        stub["importance_half_life_days"] = round(h_days, 4)
        stub["importance_decay_active"] = True

    if not route_memory_enabled():
        return route_query, stub

    ensure_route_memory_schema(con)
    t = float(now if now is not None else time.time())
    cleanup_expired_route_memories(con, now=t)

    max_c = _max_chars()
    if max_c <= 0:
        stub["enabled"] = True
        stub["note"] = "max_chars<=0 skips fusion"
        return route_query, stub

    scope = normalize_project_scope(project_root)
    rows = fetch_active_memories_for_route(
        con,
        user_id=user_id,
        project_scope_norm=scope,
        now=t,
        limit=_max_rows(),
    )
    stub["enabled"] = True
    if not rows:
        return route_query, stub

    parts: list[str] = []
    ids_out: list[str] = []
    used = 0
    truncated = False
    budget_left = max_c

    for mid, body, imp, created_at_ts, _exp in rows:
        body_s = body.strip()
        if not body_s:
            continue
        eff = memory_effective_importance(imp, created_at=created_at_ts, now=t)
        p_show = round(eff, 3) if stub["importance_decay_active"] else float(imp)
        frag = body_s if not parts else f"- {body_s}"
        show_p = imp != 0 or (stub["importance_decay_active"] and abs(p_show) > 1e-9)
        if show_p:
            frag = f"[p={p_show:g}] {frag}"
        need = len(frag) + (1 if parts else 0)
        if need > budget_left:
            truncated = True
            if budget_left > 32:
                clip = frag[: max(0, budget_left - 1)] + "…"
                parts.append(clip)
                ids_out.append(mid)
                used += 1
            break
        parts.append(frag)
        ids_out.append(mid)
        budget_left -= need
        used += 1

    blob = "\n".join(parts) if parts else ""
    if not blob:
        stub["applied"] = False
        return route_query, stub

    block = (
        "Operator routing memories:\n"
        f"{blob}\n\n"
        f"{route_query}"
    )
    stub["applied"] = True
    stub["rows_used"] = used
    stub["chars"] = len(blob)
    stub["memory_ids"] = ids_out
    stub["truncated"] = truncated
    stub["project_scope_filter"] = scope or "(global-only)"
    return block, stub


def memory_append(
    con: sqlite3.Connection,
    *,
    user_id: str,
    project_root: str | None,
    body: str,
    skill_hint: str = "",
    importance: int = 0,
    ttl_days: float | None = None,
    now: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Insert or upsert when dedup finds same normalized body. Returns (memory_id, append_meta)."""
    ensure_route_memory_schema(con)
    t = float(now if now is not None else time.time())
    cleanup_expired_route_memories(con, now=t)

    txt = (body or "").strip()
    if not txt:
        raise ValueError("body is required")

    scope = normalize_project_scope(project_root)
    key = normalize_body_for_dedup(txt)
    meta_append: dict[str, Any] = {"dedup": False, "updated": False}

    ttl = ttl_days if ttl_days is not None else _default_ttl_days()
    exp: float | None = None
    if ttl is not None and ttl > 0:
        exp = t + float(ttl) * 86400.0

    hint = (skill_hint or "").strip()
    imp_new = int(importance)

    if route_memory_dedup_enabled() and key:
        dup_id = _find_duplicate_memory_id(
            con, user_id=user_id, project_scope_norm=scope, body_key=key, now=t
        )
        if dup_id:
            meta_append["dedup"] = True
            meta_append["updated"] = True
            row = con.execute(
                "SELECT importance, expires_at, skill_hint FROM route_memories WHERE id = ?",
                (dup_id,),
            ).fetchone()
            prev_imp = int(row[0]) if row else 0
            prev_exp = float(row[1]) if row and row[1] is not None else None
            prev_hint = str(row[2] or "") if row else ""
            merged_hint = hint if hint else prev_hint
            imp_use = max(prev_imp, imp_new)
            exp_use = exp
            if prev_exp is not None:
                if exp_use is None:
                    exp_use = prev_exp
                else:
                    exp_use = max(prev_exp, exp_use)
            con.execute(
                """
                UPDATE route_memories
                SET body = ?, skill_hint = ?, importance = ?, created_at = ?, expires_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    txt,
                    merged_hint,
                    imp_use,
                    t,
                    exp_use,
                    dup_id,
                    (user_id or "").strip(),
                ),
            )
            con.commit()
            meta_append["merged_importance"] = imp_use
            return dup_id, meta_append

    mid = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO route_memories (id, user_id, project_scope, body, skill_hint, importance, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            (user_id or "").strip(),
            scope,
            txt,
            hint,
            imp_new,
            t,
            exp,
        ),
    )
    con.commit()
    return mid, meta_append


def memory_list(
    con: sqlite3.Connection,
    *,
    user_id: str,
    project_root: str | None,
    limit: int = 25,
    include_expired: bool = False,
    now: float | None = None,
) -> list[dict[str, Any]]:
    ensure_route_memory_schema(con)
    t = float(now if now is not None else time.time())
    scope = normalize_project_scope(project_root)
    uid = (user_id or "").strip()
    lim = max(1, min(int(limit), 500))
    halflife = memory_importance_half_life_days()

    if include_expired:
        cur = con.execute(
            """
            SELECT id, project_scope, body, skill_hint, importance, created_at, expires_at
            FROM route_memories
            WHERE user_id = ? AND (project_scope = '' OR project_scope = ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (uid, scope, lim),
        )
    else:
        cur = con.execute(
            """
            SELECT id, project_scope, body, skill_hint, importance, created_at, expires_at
            FROM route_memories
            WHERE user_id = ?
              AND (project_scope = '' OR project_scope = ?)
              AND (expires_at IS NULL OR expires_at >= ?)
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            """,
            (uid, scope, t, lim),
        )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        ct = float(r[5])
        imp = int(r[4])
        row = {
            "id": r[0],
            "project_scope": r[1],
            "body": r[2],
            "skill_hint": r[3],
            "importance": imp,
            "effective_importance": round(memory_effective_importance(imp, created_at=ct, now=t), 6)
            if halflife is not None
            else None,
            "created_at": ct,
            "expires_at": float(r[6]) if r[6] is not None else None,
        }
        out.append(row)
    if halflife is not None:
        out.sort(key=lambda z: float(z["effective_importance"] or z["importance"]), reverse=True)
    return out


def memory_delete(con: sqlite3.Connection, *, user_id: str, memory_id: str) -> bool:
    ensure_route_memory_schema(con)
    con.execute(
        "DELETE FROM route_memories WHERE id = ? AND user_id = ?",
        ((memory_id or "").strip(), (user_id or "").strip()),
    )
    row = con.execute("SELECT changes()").fetchone()
    n = int(row[0]) if row else 0
    con.commit()
    return n > 0


def memory_prune_expired(con: sqlite3.Connection, *, now: float | None = None) -> int:
    ensure_route_memory_schema(con)
    return cleanup_expired_route_memories(con, now=now)
