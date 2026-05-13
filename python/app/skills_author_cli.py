"""Scaffold user skills (`init`) and validate SKILL manifests (`lint`)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from app.main import parse_skill_md
from app.skill_manifest import validate_skill_manifest

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")


def skill_init(slug: str) -> Path:
    if not _SAFE_NAME.match(slug):
        raise ValueError(f"Skill folder name must match {_SAFE_NAME.pattern} — got {slug!r}")

    skills_root = Path(os.getenv("SKILLFORGE_USER_SKILLS", str(Path.home() / ".skillforge" / "skills"))).expanduser().resolve()
    dest = skills_root / slug
    skill_md = dest / "SKILL.md"
    if skill_md.exists():
        raise ValueError(f"Already exists: {skill_md}")

    dest.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        f"name: {slug.replace('-', ' ').title()}\n"
        "description: One-line pitch for routing (embedding + triggers card).\n"
        "triggers: When does this skill apply?\n"
        "anti_triggers: When should an agent skip this skill?\n"
        "---\n\n"
        f"# {slug}\n\n"
        "## When to apply\n\n"
        "- …\n\n"
        "## Patterns\n\n"
        "- …\n\n"
        "## Verification\n\n"
        "- …\n\n"
        "## Outputs\n\n"
        "- Expected shape of the assistant response\n"
    )
    skill_md.write_text(body, encoding="utf-8")
    return skill_md


def skill_lint_roots(roots: list[Path]) -> int:
    """Return count of ERROR-level manifest issues."""
    errors = 0
    for root in roots:
        r = root.expanduser().resolve()
        globs = [r] if r.is_file() and r.name == "SKILL.md" else sorted(r.glob("**/SKILL.md"))
        if not globs:
            print(f"No SKILL.md found under {r}")
            errors += 1
            continue
        for md in globs:
            parsed = parse_skill_md(md, "lint")
            if not parsed:
                print(f"ERROR {md}: unreadable parse")
                errors += 1
                continue
            errs, warns = validate_skill_manifest(parsed, md)
            for w in warns:
                print(f"WARN {md}: {w}")
            for e in errs:
                print(f"ERROR {md}: {e}")
                errors += 1
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Skillforge skill authoring helpers (scaffold + manifest lint).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init",
        help="Create ~/.skillforge/skills/<slug>/SKILL.md (override SKILLFORGE_USER_SKILLS)",
    )
    p_init.add_argument("slug", help="Directory name under user skills folder (lowercase-kebab-case)")

    p_lint = sub.add_parser(
        "lint",
        help="Validate SKILL.md files (see SKILLFORGE_SKILL_MANIFEST_STRICT for load-time exclusions)",
    )
    p_lint.add_argument(
        "roots",
        nargs="*",
        default=[],
        help="Directories or SKILL.md paths (default bundled + user trees from env)",
    )

    args = ap.parse_args()

    try:
        if args.cmd == "init":
            p = skill_init(args.slug.strip().lower())
            print(f"Wrote template: {p}")
            print("(Reload MCP / hot reload to pick up the new catalog entry.)")
            return
        if args.cmd == "lint":
            roots = [Path(p) for p in args.roots] if args.roots else []
            if not roots:
                bf = Path(os.getenv("SKILLFORGE_BUNDLED_SKILLS", "./skills")).expanduser().resolve()
                usr = Path(os.getenv("SKILLFORGE_USER_SKILLS", str(Path.home() / ".skillforge" / "skills"))).expanduser()
                roots = [bf, usr]
            err_count = skill_lint_roots(roots)
            raise SystemExit(1 if err_count else 0)
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
