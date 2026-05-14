"""Replay SQLite events chronologically for a session or window (CLI debugging).

Not a deterministic 're-invoke routing' sandbox — timelines are reconstructed from persisted events."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time

from app.db_paths import resolve_orchestrator_db
from app.events_query import fetch_events_for_replay, parse_replay_event_types


def _replay_rows(
    con: sqlite3.Connection,
    *,
    session_id: str | None,
    user_id: str,
    newest_first_snapshot: bool,
    limit: int,
    event_types: tuple[str, ...] | None,
    min_ts: float | None,
    max_ts: float | None,
) -> list[tuple[float, str | None, str | None, str | None]]:
    return fetch_events_for_replay(
        con,
        user_id=user_id,
        session_id=session_id,
        newest_first_snapshot=newest_first_snapshot,
        limit=limit,
        event_types=event_types,
        min_ts=min_ts,
        max_ts=max_ts,
    )


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
    ap.add_argument(
        "--min-ts",
        type=float,
        default=None,
        metavar="UNIX_TS",
        help="Only include events with ts >= this bound (inclusive).",
    )
    ap.add_argument(
        "--max-ts",
        type=float,
        default=None,
        metavar="UNIX_TS",
        help="Only include events with ts <= this bound (inclusive).",
    )
    ap.add_argument(
        "--event-types",
        default="",
        metavar="LIST",
        help="Comma-separated event_type whitelist (default: all types).",
    )
    ap.add_argument(
        "--since-days",
        type=float,
        default=None,
        metavar="N",
        help="Shorthand: set min-ts to (now − N×86400) unless --min-ts is set.",
    )
    args = ap.parse_args()

    db_path = resolve_orchestrator_db((args.project_root or "").strip() or None)
    if not db_path.exists():
        print(f"No database yet: {db_path}")
        raise SystemExit(1)

    min_ts = args.min_ts
    if min_ts is None and args.since_days is not None:
        if float(args.since_days) <= 0:
            print("--since-days must be > 0.")
            raise SystemExit(2)
        min_ts = time.time() - float(args.since_days) * 86400.0

    event_types = parse_replay_event_types(args.event_types)

    con = sqlite3.connect(str(db_path))
    sess = (args.session_id or "").strip() or None
    rows_raw = _replay_rows(
        con,
        session_id=sess,
        user_id=args.user,
        newest_first_snapshot=bool(args.newest_first),
        limit=args.limit,
        event_types=event_types,
        min_ts=min_ts,
        max_ts=args.max_ts,
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
