"""Preflight / health checks for Skillforge (paths, catalog, optional full router load)."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from app.db_paths import resolve_orchestrator_db


def _bundled_skills_dir() -> Path:
    return Path(os.getenv("SKILLFORGE_BUNDLED_SKILLS", "./skills"))


def _user_skills_dir() -> Path:
    return Path(os.getenv("SKILLFORGE_USER_SKILLS", str(Path.home() / ".skillforge" / "skills")))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check Skillforge install paths, skill catalog, and optionally load the embedding router."
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="Skip embedding model load (fast; checks paths + skill file counts only).",
    )
    p.add_argument(
        "--project-root",
        default="",
        help="If set, also checks <root>/.skillforge/ DB path resolution.",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output on stdout.")
    return p.parse_args(argv)


def _count_skill_md(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.glob("*/SKILL.md"))


def run_health(*, quick: bool, project_root: str, json_out: bool) -> int:
    checks: list[dict] = []
    failed = False

    bundled = _bundled_skills_dir()
    user_skills = _user_skills_dir()
    bundled_n = _count_skill_md(bundled)

    b_ok = bundled.is_dir() and bundled_n > 0
    checks.append({
        "name": "bundled_skills",
        "ok": b_ok,
        "path": str(bundled.resolve()) if bundled.exists() else str(bundled),
        "skill_md_count": bundled_n,
    })
    if not b_ok:
        failed = True

    user_n = _count_skill_md(user_skills)
    u_ok = True
    u_err: str | None = None
    if not user_skills.is_dir():
        try:
            user_skills.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            u_ok = False
            u_err = str(e)
            failed = True
    checks.append({
        "name": "user_skills",
        "ok": u_ok,
        "path": str(user_skills),
        "skill_md_count": user_n,
        "error": u_err,
    })

    env_profile = Path.home() / ".skillforge" / "env"
    checks.append({
        "name": "user_env_profile",
        "ok": True,
        "path": str(env_profile),
        "present": env_profile.is_file(),
    })

    pr = (project_root or "").strip() or None
    db_path = resolve_orchestrator_db(pr)
    db_ok = True
    db_err: str | None = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(db_path))
        try:
            con.execute("SELECT 1")
        finally:
            con.close()
    except OSError as e:
        db_ok = False
        db_err = str(e)
        failed = True
    checks.append({
        "name": "orchestrator_db",
        "ok": db_ok,
        "path": str(db_path),
        "error": db_err,
    })

    router_skill_count: int | None = None
    if not quick:
        try:
            from app.main import build_router_and_skills

            _router, skills = build_router_and_skills(log=not json_out, log_prefix="[skillforge-health]")
            router_skill_count = len(skills)
            if router_skill_count <= 0:
                failed = True
            checks.append({
                "name": "router_load",
                "ok": router_skill_count > 0,
                "skill_count": router_skill_count,
                "error": None if router_skill_count and router_skill_count > 0 else "empty catalog",
            })
        except Exception as e:
            failed = True
            checks.append({
                "name": "router_load",
                "ok": False,
                "skill_count": None,
                "error": str(e),
            })

    payload = {
        "ok": not failed,
        "quick": quick,
        "checks": checks,
    }
    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        for c in checks:
            sym = "✓" if c.get("ok") else "✗"
            print(f"{sym} {c['name']}", file=sys.stderr)
            if c.get("path"):
                print(f"    path: {c['path']}", file=sys.stderr)
            if c.get("skill_md_count") is not None:
                print(f"    SKILL.md count: {c['skill_md_count']}", file=sys.stderr)
            if c.get("skill_count") is not None:
                print(f"    router skills: {c['skill_count']}", file=sys.stderr)
            if c.get("present") is not None:
                if c["present"]:
                    print(f"    present: yes", file=sys.stderr)
                else:
                    print(f"    present: no · optional (`skillforge config init`)", file=sys.stderr)
            if c.get("error"):
                print(f"    error: {c['error']}", file=sys.stderr)
        print("health: ok" if not failed else "health: failed", file=sys.stderr)

    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(
        run_health(quick=bool(args.quick), project_root=args.project_root, json_out=bool(args.json))
    )


if __name__ == "__main__":
    main()
