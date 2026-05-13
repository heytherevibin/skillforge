"""SKILL.md manifest checks (warnings + optional strict exclusion from catalog load)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SkillLike(Protocol):
    name: str
    description: str
    body: str
    triggers: str
    anti_triggers: str


_SKILL_DIR_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def skill_md_has_yaml_frontmatter(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8")[:4096]
    except OSError:
        return False
    return head.lstrip().startswith("---")


def validate_skill_manifest(skill: SkillLike, path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors justify exclusion under strict manifest mode."""
    errors: list[str] = []
    warnings: list[str] = []
    dir_name = path.parent.name
    if skill.name != dir_name:
        warnings.append(f"parsed name {skill.name!r} != dirname {dir_name!r} (unexpected)")

    if not _SKILL_DIR_PATTERN.match(dir_name):
        errors.append(f"skill directory {dir_name!r} should match {_SKILL_DIR_PATTERN.pattern}")

    body = (skill.body or "").strip()
    if len(body) < 1:
        errors.append("empty SKILL.md body after frontmatter")

    desc = (skill.description or "").strip()
    if len(desc) < 40:
        warnings.append(f"short description ({len(desc)} chars) — consider expanding frontmatter description")

    if len(desc) > 2800:
        warnings.append(f"very long description ({len(desc)} chars) — routing card may truncate awkwardly")

    if not skill_md_has_yaml_frontmatter(path):
        warnings.append("no YAML frontmatter block (---) — title/description inferred from filename/body")

    trig = ((skill.triggers or "") + (skill.anti_triggers or "")).strip()
    if len(trig) > 4000:
        warnings.append(f"very long triggers/anti_triggers ({len(trig)} chars total)")

    return errors, warnings


def skill_manifest_strict_exclusion() -> bool:
    """When true, skip skills that fail manifest *errors* (see validate_skill_manifest)."""
    import os

    raw = os.getenv("SKILLFORGE_SKILL_MANIFEST_STRICT", "0").strip().lower()
    return raw not in ("0", "false", "no", "")

