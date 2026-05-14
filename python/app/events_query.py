"""Shared SQLite ``events`` query helpers (replay export, ingest, pruning)."""

from __future__ import annotations

import sqlite3
from typing import Any


def parse_replay_event_types(raw: str | None) -> tuple[str, ...] | None:
    """Whitelist from comma-separated types. Empty/unset ⇒ ``None`` (no type filter — all rows)."""
    bits = tuple(x.strip() for x in (raw or "").split(",") if x.strip())
    return bits if bits else None


def _type_clause(event_types: tuple[str, ...] | None) -> tuple[str, list[Any]]:
    if not event_types:
        return "", []
    ph = ",".join("?" * len(event_types))
    return f" AND event_type IN ({ph})", list(event_types)


def _bounds_clause(min_ts: float | None, max_ts: float | None, params: list[Any]) -> str:
    extra = ""
    if min_ts is not None:
        extra += " AND ts >= ?"
        params.append(float(min_ts))
    if max_ts is not None:
        extra += " AND ts <= ?"
        params.append(float(max_ts))
    return extra


def fetch_events_for_replay(
    con: sqlite3.Connection,
    *,
    user_id: str,
    session_id: str | None,
    newest_first_snapshot: bool,
    limit: int,
    event_types: tuple[str, ...] | None,
    min_ts: float | None,
    max_ts: float | None,
) -> list[tuple[float, str | None, str | None, str | None]]:
    """Return rows ``(ts, session_id, event_type, payload)`` for replay / JSON export."""
    uid = (user_id or "").strip()
    lim = max(1, min(int(limit), 5000))

    tc, tparams = _type_clause(event_types)

    if session_id and session_id.strip():
        sid = session_id.strip()
        params: list[Any] = [uid, sid]
        extra = _bounds_clause(min_ts, max_ts, params)
        sql = f"""
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ? AND session_id = ?
            {extra}
            {tc}
            ORDER BY ts ASC
            LIMIT ?
        """
        cur = con.execute(sql, params + tparams + [lim])
        return [(float(ts), sidv, et, payload) for ts, sidv, et, payload in cur.fetchall()]

    order = "DESC" if newest_first_snapshot else "ASC"
    params2: list[Any] = [uid]
    extra = _bounds_clause(min_ts, max_ts, params2)
    sql = f"""
        SELECT ts, session_id, event_type, payload
        FROM events
        WHERE user_id = ?
        {extra}
        {tc}
        ORDER BY ts {order}
        LIMIT ?
    """
    cur = con.execute(sql, params2 + tparams + [lim])
    rows = [(float(ts), sidv, et, payload) for ts, sidv, et, payload in cur.fetchall()]
    if newest_first_snapshot:
        rows = list(reversed(rows))
    return rows


def count_events_before(
    con: sqlite3.Connection,
    *,
    user_id: str,
    cutoff_ts: float,
) -> int:
    cur = con.execute(
        "SELECT COUNT(*) FROM events WHERE user_id = ? AND ts < ?",
        ((user_id or "").strip(), float(cutoff_ts)),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def event_ts_bounds_for_cutoff(
    con: sqlite3.Connection,
    *,
    user_id: str,
    cutoff_ts: float,
) -> tuple[float | None, float | None]:
    """Min/max ``ts`` among rows that would match ``ts < cutoff`` for ``user_id``."""
    uid = (user_id or "").strip()
    row = con.execute(
        """
        SELECT MIN(ts), MAX(ts)
        FROM events
        WHERE user_id = ? AND ts < ?
        """,
        (uid, float(cutoff_ts)),
    ).fetchone()
    if not row or row[0] is None:
        return None, None
    return float(row[0]), float(row[1])


def delete_events_before(
    con: sqlite3.Connection,
    *,
    user_id: str,
    cutoff_ts: float,
) -> int:
    """Delete persisted events with ``user_id`` match and ``ts < cutoff``; return deleted row count."""
    uid = (user_id or "").strip()
    cutoff = float(cutoff_ts)
    con.execute(
        "DELETE FROM events WHERE user_id = ? AND ts < ?",
        (uid, cutoff),
    )
    row = con.execute("SELECT changes()").fetchone()
    n = int(row[0]) if row else 0
    con.commit()
    return n
