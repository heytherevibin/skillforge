"""CLI: index project files into ``<project>/.skillforge/orchestrator.db`` for project RAG."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.main import build_router_and_skills, init_db
from app.project_index import index_project, project_index_stats


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Chunk and embed text files under project_root into the per-repo orchestrator DB. "
            "Use with MCP route_skills/include_project_rag or skillforge route --include-project-rag."
        ),
    )
    p.add_argument(
        "--project-root",
        required=True,
        help="Repository root directory to index (writes .skillforge/orchestrator.db).",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Clear all project_chunks rows before re-indexing.",
    )
    p.add_argument(
        "--stats-only",
        action="store_true",
        help="Print index metadata from DB and exit (no scan/embed).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Skip progress messages on stderr from skill loading.",
    )
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    root_s = args.project_root.strip()
    if not root_s:
        print("skillforge index: --project-root is required.", file=sys.stderr)
        return 2
    root = Path(root_s).expanduser().resolve()
    db_path = resolve_orchestrator_db(str(root))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = init_db(db_path)
    try:
        if args.stats_only:
            print(json.dumps({"db": str(db_path), **project_index_stats(con)}, indent=2))
            return 0

        router, _ = await asyncio.to_thread(
            build_router_and_skills,
            log=not args.quiet,
            log_prefix="[skillforge-index]",
        )
        stats = await asyncio.to_thread(
            index_project,
            con,
            root,
            router.embed_model,
            reset=args.reset,
        )
        print(
            json.dumps(
                {"db": str(db_path), "index_state": project_index_stats(con), **stats},
                indent=2,
            )
        )
        return 0
    finally:
        con.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
