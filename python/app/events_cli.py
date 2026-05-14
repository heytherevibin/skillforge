"""Print routing/events from Skillforge SQLite (terminal observability)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.events_query import count_events_before, delete_events_before, event_ts_bounds_for_cutoff


def prune_main(raw_argv: list[str]) -> None:
    """Delete rows matching ``user_id`` and ``ts < cutoff``. No deletes unless ``--execute``."""
    ap = argparse.ArgumentParser(
        prog="skillforge events prune",
        description=(
            "Preview or purge SQLite events for one logical user namespace. "
            "Pass --execute to DELETE; omit it to print matched row count only."
        ),
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--older-than-days",
        type=float,
        metavar="N",
        help="Delete events with ts strictly before (now − N×86400). N must be > 0.",
    )
    grp.add_argument(
        "--before-ts",
        "--before",
        type=float,
        dest="before_ts",
        metavar="UNIX_TS",
        help="Delete events with ts strictly before this Unix timestamp.",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Perform DELETE after preview. Omit for dry-run.",
    )
    ap.add_argument(
        "--vacuum",
        action="store_true",
        help="After DELETE, run VACUUM (locks DB; potentially slow).",
    )
    ap.add_argument("--user", default="", metavar="USER", help="Same user_id as MCP / replay (default empty).")
    ap.add_argument(
        "--project-root",
        default="",
        help="Workspace root <root>/.skillforge/orchestrator.db.",
    )

    ns = ap.parse_args(raw_argv)
    uid = ns.user.strip()
    db_path = resolve_orchestrator_db((ns.project_root or "").strip() or None)
    if not db_path.exists():
        print(f"No database yet: {db_path}")
        raise SystemExit(1)

    if ns.older_than_days is not None:
        if float(ns.older_than_days) <= 0:
            print("--older-than-days must be > 0.")
            raise SystemExit(2)
        cutoff = time.time() - float(ns.older_than_days) * 86400.0
    else:
        cutoff = float(ns.before_ts)

    con = sqlite3.connect(str(db_path))

    cnt = count_events_before(con, user_id=uid, cutoff_ts=cutoff)
    mn, mx = event_ts_bounds_for_cutoff(con, user_id=uid, cutoff_ts=cutoff)
    con.close()

    print(f"SQLite: {db_path}")
    print(
        "Match:",
        f" user_id={uid!r}",
        " AND ts",
        "<",
        f"{cutoff:.6g} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cutoff))} local)",
    )
    print(f"Rows to delete: {cnt}")
    if mn is not None and mx is not None:
        print(f"Covered ts span: [{mn:.6g} … {mx:.6g}]")
    elif cnt == 0:
        print("(no matching rows)")

    if not ns.execute:
        print("(dry-run) Re-run with --execute to DELETE these rows.")
        return

    con = sqlite3.connect(str(db_path))
    try:
        n_del = delete_events_before(con, user_id=uid, cutoff_ts=cutoff)
        print(f"Deleted {n_del} row(s).")
        if ns.vacuum:
            con.execute("VACUUM")
            print("VACUUM completed.")
    finally:
        con.close()


def _format_route_line(ts: float, sid: str | None, prev: dict, verbose: bool) -> str:
    tstr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    picked = prev.get("picked")
    sid12 = (sid or "-")[:12]
    base = f"{tstr}  route  session={sid12:12}  picked={picked}"
    ms = prev.get("route_ms")
    if ms is not None:
        base += f"  {ms}ms"
    if prev.get("rerouted"):
        base += "  reroute"
    if verbose:
        prompt = (prev.get("prompt") or "")[:120].replace("\n", " ")
        reason = (prev.get("reasoning") or "")[:100].replace("\n", " ")
        if prompt:
            base += f'\n         prompt: {prompt}{"…" if len(str(prev.get("prompt") or "")) > 120 else ""}'
        if reason:
            base += f'\n         why: {reason}'
    return base


def _print_row(ts: float, sid: str | None, et: str | None, payload: str | None, verbose: bool) -> None:
    prev = json.loads(payload) if payload else {}
    if et == "route" and isinstance(prev, dict):
        print(_format_route_line(ts, sid, prev, verbose))
        return
    extra = ""
    if et == "feedback" and isinstance(prev, dict):
        extra = f" skill={prev.get('skill')} thumbs={prev.get('thumbs')}"
    tstr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    print(f"{tstr}  {et or '?'}  session={sid or '-':12}{extra}")


def _print_snapshot(
    con: sqlite3.Connection,
    user_id: str,
    recent_minutes: float,
    *,
    db_path: Path | None = None,
) -> None:
    """Usage totals + recently active sessions (routes), for live CLI."""
    since = time.time() - recent_minutes * 60.0
    cur = con.execute(
        "SELECT skill_name, uses, referenced FROM skill_weights WHERE user_id = ? AND uses > 0 "
        "ORDER BY uses DESC LIMIT 12",
        (user_id,),
    )
    usage = cur.fetchall()
    cur = con.execute(
        """
        SELECT session_id, MAX(ts) AS mt
        FROM events
        WHERE ts >= ? AND event_type = 'route' AND user_id = ?
        GROUP BY session_id
        ORDER BY mt DESC
        LIMIT 15
        """,
        (since, user_id),
    )
    sessions = cur.fetchall()
    line = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"── [{line}] skillforge live ──")
    if db_path is not None:
        print(f"  SQLite: {db_path}")
    if usage:
        ubits = [f"{n} uses={u} ref={r}" for n, u, r in usage]
        print("  Top skills:", "; ".join(ubits))
    else:
        print("  Top skills: (no route stats yet for this user_id)")
    if sessions:
        short = [f"{(s or '-')[:10]}…" if s and len(s) > 10 else (s or "-") for s, _ in sessions]
        print(f"  Active sessions (routes in last {int(recent_minutes)}m): {len(sessions)} —", ", ".join(short))
    else:
        print(f"  Active sessions: none in last {int(recent_minutes)}m")
    print("── new events ──")


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "prune":
        prune_main(argv[1:])
        return

    ap = argparse.ArgumentParser(
        description="Skillforge event log (SQLite). Use --watch for realtime usage + routes."
    )
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--watch", action="store_true", help="Poll for new rows (default interval 2s)")
    ap.add_argument("--poll", type=float, default=2.0, help="Seconds between polls in --watch mode")
    ap.add_argument(
        "--summary-every",
        type=float,
        default=15.0,
        metavar="SEC",
        help="In --watch mode, re-print usage snapshot every SEC seconds (0 = only at start)",
    )
    ap.add_argument(
        "--recent-minutes",
        type=float,
        default=60.0,
        help="Window for 'active sessions' in snapshots (default 60)",
    )
    ap.add_argument(
        "--user",
        default="",
        help="Logical user id for stats/sessions (matches MCP SKILLFORGE_MCP_USER_ID / HTTP user). Default empty.",
    )
    ap.add_argument(
        "--project-root",
        default="",
        help="Workspace root — reads <root>/.skillforge/orchestrator.db. Default: env SKILLFORGE_PROJECT_ROOT or global DB.",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="More detail on route lines")
    args = ap.parse_args()

    pr = (args.project_root or "").strip() or None
    db_path = resolve_orchestrator_db(pr)

    if not db_path.exists():
        print("No database yet — run skillforge mcp first (or route once with this project_root).")
        print(f"  Expected: {db_path}")
        return

    if args.watch:
        con = sqlite3.connect(str(db_path))
        row = con.execute("SELECT COALESCE(MAX(ts), 0) FROM events").fetchone()
        con.close()
        last_max = float(row[0]) if row else 0.0
        summary_every = args.summary_every
        next_summary = time.monotonic()
        first = True
        try:
            while True:
                now_m = time.monotonic()
                if first or (summary_every > 0 and now_m >= next_summary):
                    con = sqlite3.connect(str(db_path))
                    _print_snapshot(con, args.user, args.recent_minutes, db_path=db_path)
                    con.close()
                    first = False
                    next_summary = now_m + summary_every
                con = sqlite3.connect(str(db_path))
                cur = con.execute(
                    "SELECT ts, session_id, event_type, payload FROM events WHERE ts > ? ORDER BY ts ASC",
                    (last_max,),
                )
                rows = cur.fetchall()
                con.close()
                for ts, sid, et, pay in rows:
                    _print_row(ts, sid, et, pay, args.verbose)
                    last_max = max(last_max, float(ts))
                time.sleep(max(0.5, args.poll))
        except KeyboardInterrupt:
            print()
    else:
        con = sqlite3.connect(str(db_path))
        _print_snapshot(con, args.user, args.recent_minutes, db_path=db_path)
        cur = con.execute(
            "SELECT ts, session_id, event_type, payload FROM events ORDER BY ts DESC LIMIT ?",
            (args.limit,),
        )
        rows = cur.fetchall()
        con.close()
        print("── recent events (newest first) ──")
        for ts, sid, et, pay in rows:
            _print_row(ts, sid, et, pay, args.verbose)


if __name__ == "__main__":
    main()
