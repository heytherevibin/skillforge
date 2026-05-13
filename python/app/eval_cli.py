"""Run route quality eval fixtures (deterministic embedding routing)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
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
        help="Print one JSON object per line to stdout (cases + errors); stderr stays human.",
    )
    return p.parse_args(argv)


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
    )

    from app.route_eval_harness import evaluate_case_result

    return evaluate_case_result(result, case, defaults=defaults)


async def _async_main(args: argparse.Namespace) -> int:
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
                errs = await _run_case(con=con, router=router, case=case, defaults=defaults)
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
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
