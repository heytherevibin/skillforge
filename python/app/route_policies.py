"""Pluggable route policies: regex on prompt → force-include skill names.

Load order (first file that exists / first successful parse wins for env):

1. ``SKILLFORGE_ROUTE_POLICIES`` — JSON object inline (e.g. ``{\"rules\":[...]}``).
2. ``SKILLFORGE_ROUTE_POLICIES_FILE`` — path to a JSON file.
3. ``<project_root>/.skillforge/policies.json``
4. ``<project_root>/skillforge-policies.json``

Rule shape::

    {
      "rules": [
        {
          "if_text_matches": "(?i)(auth|oauth|jwt|password)",
          "include": ["security-review"]
        }
      ]
    }

``if_text_matches`` is passed to ``re.search`` (``re.DOTALL``). ``include`` is a skill
name or list of names. Forced skills are appended after router picks until
``MAX_ACTIVE_SKILLS`` is reached.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


def load_route_policies_config(project_root: str | None) -> dict[str, Any]:
    """Return a dict with key ``rules`` (list). Empty rules if nothing configured."""
    raw_env = os.getenv("SKILLFORGE_ROUTE_POLICIES", "").strip()
    if raw_env:
        try:
            data = json.loads(raw_env)
            return data if isinstance(data, dict) else {"rules": []}
        except json.JSONDecodeError:
            return {"rules": []}

    paths: list[Path] = []
    path_env = os.getenv("SKILLFORGE_ROUTE_POLICIES_FILE", "").strip()
    if path_env:
        paths.append(Path(path_env).expanduser())
    if project_root:
        pr = Path(project_root).expanduser().resolve()
        paths.append(pr / ".skillforge" / "policies.json")
        paths.append(pr / "skillforge-policies.json")

    for p in paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {"rules": []}
            except (OSError, json.JSONDecodeError):
                continue
    return {"rules": []}


def merge_policy_includes(
    prompt: str,
    picked_names: list[str],
    policies: dict[str, Any],
    by_name: dict[str, Any],
    con: sqlite3.Connection,
    user_id: str,
    *,
    max_active: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Append policy-driven skills after ``picked_names`` without duplicates.

    Returns (merged_pick_list, audit_rows for events / explain_route).
    """
    # Local import avoids circular import at module load time.
    from app.main import get_skill_weight

    rules = policies.get("rules") if isinstance(policies, dict) else None
    if not isinstance(rules, list):
        rules = []

    audit: list[dict[str, Any]] = []
    merged = list(picked_names)
    extras: list[str] = []

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        pat = rule.get("if_text_matches") or rule.get("pattern") or ""
        if not isinstance(pat, str) or not pat.strip():
            continue
        try:
            matched = bool(re.search(pat, prompt, flags=re.DOTALL))
        except re.error:
            audit.append({"pattern": pat, "effect": "invalid_regex"})
            continue
        if not matched:
            continue

        inc = rule.get("include")
        if isinstance(inc, str):
            inc = [inc]
        if not isinstance(inc, list):
            continue

        for name in inc:
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if name not in by_name:
                audit.append({"pattern": pat, "skill": name, "effect": "unknown_skill"})
                continue
            _w, disabled = get_skill_weight(con, name, user_id=user_id)
            if disabled:
                audit.append({"pattern": pat, "skill": name, "effect": "disabled"})
                continue
            if name in merged or name in extras:
                audit.append({"pattern": pat, "skill": name, "effect": "already_in_list"})
                continue
            extras.append(name)
            audit.append({"pattern": pat, "skill": name, "effect": "added"})

    for n in extras:
        if len(merged) >= max_active:
            audit.append({"skill": n, "effect": "skipped_max_active", "max": max_active})
            break
        if n not in merged:
            merged.append(n)

    return merged, audit
