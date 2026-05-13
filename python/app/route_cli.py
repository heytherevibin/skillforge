"""Terminal routing — same pipeline as MCP ``route_skills`` (for scripting and parity checks)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.main import (
    build_router_and_skills,
    format_context_items_markdown,
    init_db,
    run_route_turn,
)
from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION, build_route_skills_meta
from app.redaction import redaction_enabled, redact_display_path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Route a prompt through Skillforge (stdio: skill bodies + metadata).")
    p.add_argument(
        "prompt_parts",
        nargs="*",
        help="Prompt text (whitespace-joined). Prefer this or use --prompt.",
    )
    p.add_argument("--prompt", "-p", default="", help="Prompt string (alternative to positional words).")
    p.add_argument(
        "--project-root",
        default="",
        help="Repo root — uses .skillforge/orchestrator.db; else SKILLFORGE_PROJECT_ROOT or global DB.",
    )
    p.add_argument("--session-id", default="", help="Stable session id (reuse across turns for reroute stats).")
    p.add_argument("--user-id", default="", help="Logical user id for weights/sessions/events.")
    p.add_argument(
        "--picked-names",
        default="",
        help="Comma-separated catalog skill ids (host pick). Skips auto router/Haiku; same as MCP picked_names.",
    )
    p.add_argument("--json-meta", action="store_true", help="Print routing metadata as JSON on stderr after output.")
    p.add_argument(
        "--include-project-rag",
        action="store_true",
        help="Append chunks from `skillforge index` (same DB as --project-root). Requires --project-root.",
    )
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    text = " ".join(args.prompt_parts).strip() or args.prompt.strip()
    if not text:
        print("skillforge route: provide a prompt (positional words or --prompt).", file=sys.stderr)
        return 2

    pr = (args.project_root or "").strip() or None
    if args.include_project_rag and not pr:
        print("skillforge route: --include-project-rag requires --project-root.", file=sys.stderr)
        return 2
    db_path = resolve_orchestrator_db(pr)
    con = init_db(db_path)
    db_disp = redact_display_path(db_path) if redaction_enabled() else str(db_path)

    router, skills = await asyncio.to_thread(build_router_and_skills, log=True, log_prefix="[skillforge-route]")
    session_id = args.session_id.strip() or None
    user_id = args.user_id.strip()

    picked_raw = (args.picked_names or "").strip()
    picked_supplied = bool(picked_raw)
    picked_list = [x.strip() for x in picked_raw.split(",") if x.strip()] if picked_raw else []

    try:
        result = await run_route_turn(
            con,
            router,
            text,
            conversation=[],
            user_id=user_id,
            session_id=session_id,
            project_root=pr,
            include_project_rag=bool(args.include_project_rag),
            picked_names_from_host=picked_list if picked_supplied else None,
            picked_names_from_host_supplied=picked_supplied,
        )
    finally:
        con.close()

    picked_names = result["picked_names"]
    reasoning = result["reasoning"]
    sid = result["session_id"]
    context_items = result.get("context_items") or []

    if pr:
        try:
            d = Path(pr).expanduser().resolve() / ".skillforge"
            d.mkdir(parents=True, exist_ok=True)
            snap = {
                "ts": time.time(),
                "session_id": sid,
                "picked": picked_names,
                "reasoning": reasoning,
                "route_ms": round(result["route_ms"], 1),
                "user_id": user_id,
                "source": "cli_route",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "context_mode": router.context_mode,
                "context_items_count": len(context_items),
                "project_rag_items_count": (result.get("event") or {}).get("project_rag_items_count", 0),
                "host_pick_shortlist": bool(result.get("host_pick_shortlist")),
            }
            (d / "last_route.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
        except OSError:
            pass

    if result.get("host_pick_shortlist"):
        response_text = ((result.get("host_pick_markdown") or "").strip() + f"\n\n---\n_session_id:_ `{sid}` · _DB:_ `{db_disp}`")
        print(response_text.strip())
    else:
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
        response_text = "\n".join(b for b in blocks if b is not None)
        print(response_text)

    if args.json_meta:
        meta = build_route_skills_meta(
            result=result,
            picked_names=picked_names,
            user_id=user_id,
            db_path=db_path,
            skills_map=skills,
            response_text=response_text,
            context_items=context_items,
            fusion=(result.get("event") or {}).get("context_fusion"),
            context_redaction=(result.get("event") or {}).get("context_redaction"),
        )
        if result.get("host_pick_shortlist"):
            meta["host_pick_shortlist"] = True
            meta["host_pick_candidates"] = result.get("host_pick_candidates") or []
        print(json.dumps(meta, indent=2), file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
