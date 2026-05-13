"""Replay SQLite events chronologically for a session or window (CLI debugging).

Not a deterministic 're-invoke routing' sandbox — timelines are reconstructed from persisted events."""

from __future__ import annotations

import argparse
import json
import sqlite3

from app.db_paths import resolve_orchestrator_db


def _replay_rows(
    con: sqlite3.Connection,
    *,
    session_id: str | None,
    user_id: str,
    newest_first_snapshot: bool,
    limit: int,
) -> list[tuple[float, str | None, str | None, str | None]]:
    uid = (user_id or "").strip()
    lim = max(1, min(int(limit), 5000))

    cur: sqlite3.Cursor
    if session_id and session_id.strip():
        sid = session_id.strip()
        cur = con.execute(
            """
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ? AND session_id = ?
            ORDER BY ts ASC
            LIMIT ?
            """,
            (uid, sid, lim),
        )
    else:
        order = "DESC" if newest_first_snapshot else "ASC"
        cur = con.execute(
            f"""
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ?
            ORDER BY ts {order}
            LIMIT ?
            """,
            (uid, lim),
        )
    rows = [(float(ts), sid, et, payload) for ts, sid, et, payload in cur.fetchall()]
    return rows


def _format_human(ts: float, sid: str | None, et: str | None, payload_raw: str | None) -> str:
    payload: dict[str, object] | str = {}
    if payload_raw:
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = payload_raw
    sid_short = ((sid or "-")[:12]) if sid else "-"
    bullet = f"- ts={ts:.3f}  session={sid_short}  event={et or '?'} "
    if et == "route" and isinstance(payload, dict):
        picked = payload.get("picked_names") or payload.get("picked") or ""
        bullet += f" picked={picked!r}"
        if payload.get("host_pick_shortlist"):
            bullet += " [shortlist]"
    elif isinstance(payload, dict):
        js = json.dumps(payload, ensure_ascii=False)
        bullet += js[:260]
        if len(js) > 260:
            bullet += "…"
    else:
        bullet += str(payload)[:260]
    return bullet


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay orchestrator SQLite events as a chronological timeline.")
    ap.add_argument(
        "--project-root",
        default="",
        help="Workspace root (uses <root>/.skillforge/orchestrator.db)",
    )
    ap.add_argument("--session-id", default="", help="If set, only events for this session_id (chrono ASC)")
    ap.add_argument(
        "--user",
        default="",
        metavar="USER_ID",
        help="Logical MCP user namespace (matches SKILLFORGE_MCP_USER_ID)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max rows (default 200, max 5000). Per-session replay uses chronological ASC.",
    )
    ap.add_argument(
        "--newest-first",
        action="store_true",
        help="Without --session-id, take the newest slice (DESC) instead of oldest ASC snapshot",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON array [{ts,session_id,event_type,payload}, …]",
    )
    args = ap.parse_args()

    db_path = resolve_orchestrator_db((args.project_root or "").strip() or None)
    if not db_path.exists():
        print(f"No database yet: {db_path}")
        raise SystemExit(1)

    con = sqlite3.connect(str(db_path))
    sess = (args.session_id or "").strip() or None
    rows_raw = _replay_rows(
        con,
        session_id=sess,
        user_id=args.user,
        newest_first_snapshot=bool(args.newest_first),
        limit=args.limit,
    )
    con.close()

    if args.json:
        out: list[dict[str, object]] = []
        for ts, sid, et, pay in rows_raw:
            try:
                parsed: object = json.loads(pay) if pay else {}
            except json.JSONDecodeError:
                parsed = pay or ""
            out.append({"ts": ts, "session_id": sid, "event_type": et, "payload": parsed})
        print(json.dumps(out, indent=2))
        return

    print(f"# skillforge replay  db={db_path}")
    sess_display = sess if sess else "(all sessions)"
    print(f"# user_id={args.user!r} session_filter={sess_display!r} rows={len(rows_raw)}")
    for ts, sid, et, pay in rows_raw:
        print(_format_human(ts, sid, et, pay))


if __name__ == "__main__":
    main()
