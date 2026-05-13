"""Terminal routing — same pipeline as MCP ``route_skills`` (for scripting and parity checks)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.main import build_router_and_skills, init_db, run_route_turn


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
    p.add_argument("--json-meta", action="store_true", help="Print routing metadata as JSON on stderr after output.")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    text = " ".join(args.prompt_parts).strip() or args.prompt.strip()
    if not text:
        print("skillforge route: provide a prompt (positional words or --prompt).", file=sys.stderr)
        return 2

    pr = (args.project_root or "").strip() or None
    db_path = resolve_orchestrator_db(pr)
    con = init_db(db_path)

    router, skills = await asyncio.to_thread(build_router_and_skills, log=True, log_prefix="[skillforge-route]")
    session_id = args.session_id.strip() or None
    user_id = args.user_id.strip()

    try:
        result = await run_route_turn(
            con,
            router,
            text,
            conversation=[],
            user_id=user_id,
            session_id=session_id,
        )
    finally:
        con.close()

    picked_names = result["picked_names"]
    reasoning = result["reasoning"]
    sid = result["session_id"]

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
            }
            (d / "last_route.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
        except OSError:
            pass

    blocks = [
        f"# Skillforge — routed {len(picked_names)} skill(s)",
        f"_DB:_ `{db_path}`",
        f"_Reasoning: {reasoning}_" if reasoning else "",
        "",
    ]
    for n in picked_names:
        s = skills.get(n)
        if s:
            blocks.append(f"---\n## Skill: {s.name}\n\n{s.body}\n")
    if not picked_names:
        blocks.append("_No skills matched this prompt closely enough to load._")
    print("\n".join(b for b in blocks if b is not None))

    if args.json_meta:
        meta = {
            "picked": picked_names,
            "reasoning": reasoning,
            "session_id": sid,
            "user_id": user_id,
            "rerouted": result["rerouted"],
            "change_pct": round(result["change"] * 100, 1),
            "route_ms": round(result["route_ms"], 1),
            "orchestrator_db": str(db_path),
        }
        print(json.dumps(meta, indent=2), file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
