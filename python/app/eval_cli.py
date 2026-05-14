"""Route quality eval harness + SQLite → fixture ingestion."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def _parse_run_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Evaluate route_skills-style routing against a JSON fixture "
            "(defaults to SKILLFORGE_ROUTER_MODE=embedding for stable retrieval)."
        )
    )
    p.add_argument(
        "--fixture",
        "-f",
        type=Path,
        required=True,
        help="Path to JSON fixture (cases[].prompt, expect_in_candidates, …).",
    )
    p.add_argument(
        "--router-mode",
        default="embedding",
        help="Router mode for this process (set before loading app.main). Default: embedding",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object per line to stdout (compact summary); stderr stays human.",
    )
    p.epilog = (
        "Ingest persisted route/host_shortlist telemetry into a regression fixture:\n"
        "  skillforge route-eval ingest -o fixtures/from-db.json [--user …] [--event-types …]\n"
        "  python -m app.eval_cli ingest --help"
    )
    return p.parse_args(argv)


def _parse_ingest_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Read route / host_shortlist rows from orchestrator.sqlite and emit a route-eval fixture. "
            "Prompt strings match telemetry snippets (typically ≤300 chars). "
            "Use SKILLFORGE_ROUTER_MODE=embedding when running route-eval against the output."
        )
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Destination JSON fixture path.",
    )
    p.add_argument(
        "--project-root",
        default="",
        help="Workspace root → <root>/.skillforge/orchestrator.db (default: global ~/.skillforge/data).",
    )
    p.add_argument(
        "--user",
        default="",
        metavar="USER_ID",
        help="Matches persisted events.user_id (MCP SKILLFORGE_MCP_USER_ID).",
    )
    p.add_argument(
        "--session-id",
        default="",
        help="If set, only events for this session id (chrono ASC within cap).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max events to scan after type filter (default 50, max 5000).",
    )
    p.add_argument(
        "--newest-first",
        action="store_true",
        help="Without --session-id: take globally newest slice then reverse-chronological → fixture order ASC.",
    )
    p.add_argument(
        "--event-types",
        default="route",
        metavar="CSV",
        help="Comma-separated: route and/or host_shortlist (default: route only).",
    )
    p.add_argument(
        "--candidate-window",
        type=int,
        default=22,
        help="Fixture defaults.candidate_window and expect-in-candidates truncation cap.",
    )
    p.add_argument(
        "--expect-from",
        choices=("picked", "top_candidates", "both", "none"),
        default="picked",
        help=(
            "How to derive expect_* from payload: picked=list from event; "
            "top_candidates=first heads of stored candidates[]; "
            "both=combine when available; "
            "none=prompt-only (manual)."
        ),
    )
    p.add_argument(
        "--keep-audit",
        action="store_true",
        help="Keep per-case _audit blobs (routing_correlation_id, event_ts). "
        "Otherwise strip underscore keys before writing.",
    )
    return p.parse_args(argv)


def _ingest_main(argv: list[str]) -> int:
    args = _parse_ingest_args(argv)
    from app.db_paths import resolve_orchestrator_db
    from app.route_eval_ingest import (
        build_ingested_fixture_document,
        fetch_route_like_events,
        parse_event_types_arg,
        sqlite_row_to_case,
    )

    pr = (args.project_root or "").strip() or None
    db_path = resolve_orchestrator_db(pr)
    if not db_path.exists():
        print(f"skillforge route-eval ingest: no database at {db_path}", file=sys.stderr)
        return 2

    etypes = parse_event_types_arg(args.event_types)
    sess = (args.session_id or "").strip() or None

    con = sqlite3.connect(str(db_path))
    try:
        rows = fetch_route_like_events(
            con,
            user_id=args.user,
            session_id=sess,
            limit=args.limit,
            event_types=etypes,
            newest_first=bool(args.newest_first),
        )
    finally:
        con.close()

    preview_cap = max(8, min(int(args.candidate_window), 50))
    cases: list[dict] = []
    for seq, (ts0, sid, etyp, payload) in enumerate(rows, start=1):
        maybe = sqlite_row_to_case(
            payload,
            seq=seq,
            event_ts=ts0,
            event_type=etyp,
            session_row=sid,
            expect_from=str(args.expect_from),
            preview_cap=preview_cap,
        )
        if maybe is not None:
            cases.append(maybe)

    if not cases:
        print(
            "skillforge route-eval ingest: no ingestible rows (wrong user_id? prompt empty? types filter?)",
            file=sys.stderr,
        )
        return 2

    doc = build_ingested_fixture_document(
        cases=cases,
        candidate_window=int(args.candidate_window),
        orchestrator_db=db_path,
        user_id=args.user,
        session_id=sess,
        event_types=etypes,
        include_audit_fields=bool(args.keep_audit),
    )
    out_path = args.output.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path}  cases={len(cases)}", file=sys.stderr)
    return 0


async def _run_case(
    *,
    con,
    router,
    case: dict,
    defaults: dict,
) -> list[str]:
    from app.main import run_route_turn

    prompt = (case.get("prompt") or "").strip()
    if not prompt:
        return [f"{case.get('id', '?')}: empty prompt"]

    result = await run_route_turn(
        con,
        router,
        prompt,
        conversation=[],
        user_id="__eval__",
        session_id=None,
        project_root=None,
        include_project_rag=False,
        picked_names_from_host=None,
        picked_names_from_host_supplied=False,
        dry_run=True,
    )

    from app.route_eval_harness import evaluate_case_result

    return evaluate_case_result(result, case, defaults=defaults)


async def _async_run_fixture(args: argparse.Namespace) -> int:
    fixture_path = args.fixture.expanduser().resolve()
    if not fixture_path.is_file():
        print(f"skillforge route-eval: fixture not found: {fixture_path}", file=sys.stderr)
        return 2

    os.environ["SKILLFORGE_ROUTER_MODE"] = args.router_mode.strip().lower()

    from app.route_eval_harness import load_eval_fixture
    from app.main import build_router_and_skills, init_db

    data = load_eval_fixture(fixture_path)
    defaults = data["defaults"] if isinstance(data.get("defaults"), dict) else {}
    cases = data["cases"]

    fd, tmp_name = tempfile.mkstemp(suffix=".sqlite", prefix="skillforge-eval-")
    os.close(fd)
    db_path = Path(tmp_name)
    try:
        con = init_db(db_path)
        try:
            router, _skills = await asyncio.to_thread(
                build_router_and_skills,
                log=not args.json,
                log_prefix="[skillforge-eval]",
            )
            all_errs: list[str] = []
            summaries: list[dict] = []
            for case in cases:
                if not isinstance(case, dict):
                    all_errs.append("non-dict case entry")
                    continue
                ev_case = dict(case)
                for k in tuple(ev_case.keys()):
                    if k.startswith("_"):
                        ev_case.pop(k, None)

                errs = await _run_case(con=con, router=router, case=ev_case, defaults=defaults)
                cid = case.get("id") or case.get("name") or "?"
                summaries.append({"id": cid, "ok": not errs, "errors": errs})
                all_errs.extend(errs)
                if errs and not args.json:
                    for e in errs:
                        print(e, file=sys.stderr)
                elif not errs and not args.json:
                    print(f"ok  {cid}", file=sys.stderr)

            if args.json:
                out = {"fixture": str(fixture_path), "cases": summaries, "failed": len(all_errs)}
                print(json.dumps(out, indent=2))

            return 1 if all_errs else 0
        finally:
            con.close()
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> None:
    av = argv if argv is not None else sys.argv[1:]
    if av and av[0] == "ingest":
        raise SystemExit(_ingest_main(av[1:]))
    args = _parse_run_args(av)
    raise SystemExit(asyncio.run(_async_run_fixture(args)))


if __name__ == "__main__":
    main()
