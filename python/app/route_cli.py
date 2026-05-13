"""Terminal routing — same pipeline as MCP ``route_skills`` (scripting + interactive host-pick)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.explain_route import compute_explain_route
from app.main import (
    TOP_K_CANDIDATES,
    SKILLFORGE_ROUTER_MODE,
    build_router_and_skills,
    format_context_items_markdown,
    init_db,
    run_route_turn,
)
from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION, build_route_skills_meta
from app.redaction import redaction_enabled, redact_display_path
from app.route_cli_pick import parse_interactive_skill_pick


def _truthy_route_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "")


def _interactive_enabled(args: argparse.Namespace, *, stdin_tty: bool) -> bool:
    if args.no_interactive:
        return False
    if args.interactive:
        return stdin_tty
    return _truthy_route_env("SKILLFORGE_ROUTE_INTERACTIVE") and stdin_tty


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Route a prompt through Skillforge (parity with MCP route_skills).")
    p.add_argument("prompt_parts", nargs="*", help="Prompt (positional words, joined). Or use --prompt.")
    p.add_argument("--prompt", "-p", default="", help="Alternative prompt string.")
    p.add_argument("--project-root", default="", help="Workspace root → project .skillforge/orchestrator.db.")
    p.add_argument("--session-id", default="", help="Stable session id.")
    p.add_argument("--user-id", default="", help="Logical MCP user scope (weights/events).")
    p.add_argument(
        "--picked-names",
        default="",
        help="Comma-separated catalog ids — host finalize (parity with MCP picked_names).",
    )
    p.add_argument("--json-meta", action="store_true", help="Print route_meta JSON on stderr after stdout (legacy).")
    p.add_argument("--json", action="store_true", help="One JSON envelope on stdout (scripting-friendly).")
    p.add_argument(
        "--explain",
        action="store_true",
        help="Diagnostics: embedding shortlist + router hypothesis (explain_route pipeline). ",
    )
    p.add_argument(
        "--explain-only",
        action="store_true",
        help="Only diagnostics — no finalize (ignores picked-names). ",
    )
    p.add_argument("--explain-limit", type=int, default=0, metavar="N", help="explain shortlist width (≤50). ")
    p.add_argument("-i", "--interactive", action="store_true", help="TTY prompt after host-mode shortlist. ")
    p.add_argument("--no-interactive", action="store_true", help="Disable env-driven auto prompts. ")
    p.add_argument("--quiet", action="store_true", help="Less stderr chatter during bootstrap. ")
    p.add_argument("--include-project-rag", action="store_true", help="Needs --project-root. ")
    return p.parse_args(argv)


def _markdown_route(result: dict, *, sid: str, db_disp: str, router) -> str:
    picked_names = result["picked_names"]
    reasoning = result["reasoning"]
    context_items = result.get("context_items") or []
    if result.get("host_pick_shortlist"):
        return (
            (result.get("host_pick_markdown") or "").strip() + f"\n\n---\n_session_id:_ `{sid}` · _DB:_ `{db_disp}`"
        ).strip()
    blocks = [
        f"# Skillforge — routed {len(picked_names)} skill(s); context=`{router.context_mode}`",
        f"_DB:_ `{db_disp}`",
        f"_Reasoning: {reasoning}_" if reasoning else "",
        "",
    ]
    if context_items:
        blocks.append(format_context_items_markdown(context_items))
    elif not picked_names:
        blocks.append("_No skills matched this prompt closely enough to load._")
    return "\n".join(b for b in blocks if b is not None)


def _meta(result: dict, *, md_out: str, user_id: str, db_path, skills_map) -> dict:
    m = build_route_skills_meta(
        result=result,
        picked_names=list(result["picked_names"]),
        user_id=user_id,
        db_path=db_path,
        skills_map=skills_map,
        response_text=md_out,
        context_items=result.get("context_items"),
        fusion=(result.get("event") or {}).get("context_fusion"),
        context_redaction=(result.get("event") or {}).get("context_redaction"),
    )
    if result.get("host_pick_shortlist"):
        m["host_pick_shortlist"] = True
        m["host_pick_candidates"] = result.get("host_pick_candidates") or []
    return m


def _explain_lim(v: int) -> int:
    lim = TOP_K_CANDIDATES if v <= 0 else v
    return max(1, min(int(lim), 50))


def _write_last_route(rr: dict, *, pr: str | None, user_id: str, router, picks_via_interactive: list[str]) -> None:
    if not pr:
        return
    try:
        root = Path(pr).expanduser().resolve()
        (root / ".skillforge").mkdir(parents=True, exist_ok=True)
        snap = {
            "ts": time.time(),
            "session_id": rr["session_id"],
            "picked": rr["picked_names"],
            "reasoning": rr["reasoning"],
            "route_ms": round(rr["route_ms"], 1),
            "user_id": user_id,
            "source": "cli_route",
            "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
            "context_mode": router.context_mode,
            "context_items_count": len(rr.get("context_items") or []),
            "project_rag_items_count": (rr.get("event") or {}).get("project_rag_items_count", 0),
            "host_pick_shortlist": bool(rr.get("host_pick_shortlist")),
            "picked_via_interactive": picks_via_interactive,
        }
        (root / ".skillforge" / "last_route.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
    except OSError:
        pass


async def _run(args: argparse.Namespace) -> int:
    text = " ".join(args.prompt_parts).strip() or args.prompt.strip()
    if not text:
        print("skillforge route: provide a prompt.", file=sys.stderr)
        return 2

    stdin_tty = sys.stdin.isatty()
    pr = (args.project_root or "").strip() or None
    explain_only = bool(args.explain_only)
    picked_ini = "" if explain_only else (args.picked_names or "").strip()
    picks_ini = [x.strip() for x in picked_ini.split(",") if x.strip()] if picked_ini else []
    cli_picked = picked_ini != ""

    if args.include_project_rag and not pr:
        print("skillforge route: --include-project-rag requires --project-root.", file=sys.stderr)
        return 2

    tty_interactive = (
        not cli_picked
        and SKILLFORGE_ROUTER_MODE == "host"
        and stdin_tty
        and _interactive_enabled(args, stdin_tty=stdin_tty)
    )

    db_path = resolve_orchestrator_db(pr)
    con = init_db(db_path)
    db_disp = redact_display_path(db_path) if redaction_enabled() else str(db_path)
    user_id = args.user_id.strip()
    session_id_arg = args.session_id.strip() or None

    explain_md = None
    explain_meta = None
    want_diag = bool(args.explain or explain_only)

    try:
        router, skills_map = await asyncio.to_thread(
            build_router_and_skills, log=(not args.quiet), log_prefix="[skillforge-route]"
        )

        if want_diag:
            explain_md, explain_meta = await compute_explain_route(
                router,
                con,
                prompt=text,
                conversation=[],
                limit=_explain_lim(int(args.explain_limit)),
                user_id=user_id,
                project_root=pr,
                db_path=db_path,
            )
        if explain_only:
            if args.json:
                print(
                    json.dumps({
                        "tool": "skillforge-route",
                        "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                        "phase": "explain_only",
                        "explain": explain_meta,
                        "explain_markdown": explain_md or "",
                        "orchestrator_db": db_disp,
                        "prompt": text,
                    }, indent=2),
                    flush=True,
                )
            else:
                print(explain_md or "", flush=True)
            return 0

        picks_interactive_track: list[str] = []

        result = await run_route_turn(
            con,
            router,
            text,
            conversation=[],
            user_id=user_id,
            session_id=session_id_arg,
            project_root=pr,
            include_project_rag=bool(args.include_project_rag),
            picked_names_from_host=picks_ini if cli_picked else None,
            picked_names_from_host_supplied=cli_picked,
        )

        if tty_interactive and result.get("host_pick_shortlist"):
            sid = result["session_id"]
            rows = result.get("host_pick_candidates") or []
            md0 = _markdown_route(result, sid=sid, db_disp=db_disp, router=router)
            meta0 = _meta(result, md_out=md0, user_id=user_id, db_path=db_path, skills_map=skills_map)
            hint = "(ranks 1,3… or ids; empty skips finalize)"
            if args.json:
                print(
                    json.dumps({
                        "tool": "skillforge-route",
                        "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                        "phase": "host_shortlist_prompt",
                        "prompt": text,
                        "session_id": sid,
                        "route_meta": meta0,
                        "route_markdown": md0,
                        "orchestrator_db": db_disp,
                        **({"explain": explain_meta} if explain_meta else {}),
                    }, indent=2),
                    flush=True,
                )
            else:
                print(md0, flush=True)
                if explain_md:
                    print(f"\n---\n{explain_md}\n", file=sys.stderr)

            ip = ""
            try:
                ip = input("" if args.quiet else f"skillforge route {hint}: ")
            except EOFError:
                ip = ""
            chosen = parse_interactive_skill_pick(ip, rows)

            if not chosen:
                if args.json_meta:
                    print(json.dumps(meta0, indent=2), file=sys.stderr)
                return 0

            picks_interactive_track = chosen
            result = await run_route_turn(
                con,
                router,
                text,
                conversation=[],
                user_id=user_id,
                session_id=sid,
                project_root=pr,
                include_project_rag=bool(args.include_project_rag),
                picked_names_from_host=chosen,
                picked_names_from_host_supplied=True,
            )

        sid = result["session_id"]
        md_final = _markdown_route(result, sid=sid, db_disp=db_disp, router=router)
        mf = _meta(result, md_out=md_final, user_id=user_id, db_path=db_path, skills_map=skills_map)
        phase = (
            "host_shortlist_static"
            if result.get("host_pick_shortlist")
            else "context"
        )
        _write_last_route(result, pr=pr, user_id=user_id, router=router, picks_via_interactive=picks_interactive_track)

        if args.json:
            env = {
                "tool": "skillforge-route",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "phase": phase,
                "prompt": text,
                "session_id": sid,
                "route_meta": mf,
                "route_markdown": md_final,
                "orchestrator_db": db_disp,
            }
            if picks_interactive_track:
                env["picked_via_interactive"] = picks_interactive_track
            if explain_meta:
                env["explain"] = explain_meta
            print(json.dumps(env, indent=2), flush=True)
        else:
            print(md_final, flush=True)
            if args.explain and explain_md:
                print(f"\n---\n{explain_md}\n", file=sys.stderr)

        if args.json_meta:
            print(json.dumps(mf, indent=2), file=sys.stderr)

        return 0

    finally:
        con.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()

