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

Optional **project routing overlay** (same JSON object):

- ``exclude_skills`` / ``host_exclude`` / ``denylist`` — skill ids excluded from the embedding
  shortlist (hard filter).
- ``routing_boosts`` / ``skill_boosts`` — object mapping skill id → numeric delta added to the
  routing score after learned weights (clamped to ±2).
- ``project_notes`` / ``routing_notes`` / ``rag_notes`` — free text prepended to the internal
  routing query when **project_root** is set (stack/context hints for embedding).

``project_notes`` are **not** applied without ``project_root`` to avoid global prompt injection
from shared policy files.
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


def parse_routing_overlay(
    policies: dict[str, Any] | None,
    *,
    by_name: dict[str, Any] | None = None,
    audit_out: list[dict[str, Any]] | None = None,
) -> tuple[frozenset[str], dict[str, float], str]:
    """Parse exclude list, per-skill score boosts, and project notes from policies dict."""
    policies = policies or {}
    by_name = by_name or {}
    boost_cap = 2.0

    raw_ex = policies.get("exclude_skills") or policies.get("host_exclude") or policies.get("denylist") or []
    if isinstance(raw_ex, str):
        raw_ex = [raw_ex]
    exclude: set[str] = set()
    if isinstance(raw_ex, list):
        for x in raw_ex:
            if not isinstance(x, str) or not x.strip():
                continue
            name = x.strip()
            if by_name and name not in by_name:
                if audit_out is not None:
                    audit_out.append({"kind": "exclude", "skill": name, "effect": "unknown_skill"})
                continue
            exclude.add(name)

    raw_boost = policies.get("routing_boosts") or policies.get("skill_boosts") or {}
    boosts: dict[str, float] = {}
    if isinstance(raw_boost, dict):
        for k, v in raw_boost.items():
            if not isinstance(k, str) or not k.strip():
                continue
            name = k.strip()
            if by_name and name not in by_name:
                if audit_out is not None:
                    audit_out.append({"kind": "boost", "skill": name, "effect": "unknown_skill"})
                continue
            try:
                b = float(v)
            except (TypeError, ValueError):
                if audit_out is not None:
                    audit_out.append({"kind": "boost", "skill": name, "effect": "invalid_value"})
                continue
            boosts[name] = max(-boost_cap, min(boost_cap, b))

    notes = ""
    for key in ("project_notes", "routing_notes", "rag_notes"):
        raw = policies.get(key)
        if isinstance(raw, str) and raw.strip():
            notes = raw.strip()
            break

    return frozenset(exclude), boosts, notes


def merge_project_notes_into_route_query(
    route_query: str,
    notes: str,
    project_root: str | None,
    *,
    max_chars: int | None = None,
) -> str:
    """Prefix routing query with project notes when ``project_root`` is set."""
    notes = (notes or "").strip()
    pr = (project_root or "").strip()
    if not notes or not pr:
        return route_query
    mc = max_chars
    if mc is None:
        mc = int(os.getenv("SKILLFORGE_PROJECT_NOTES_MAX_CHARS", "1200"))
    mc = max(0, mc)
    clipped = notes if len(notes) <= mc else notes[: max(0, mc - 1)] + "…"
    return f"Project routing notes:\n{clipped}\n\n{route_query}"


def build_routing_overlay_payload(
    *,
    project_root: str,
    exclude_skills: frozenset[str],
    routing_boosts: dict[str, float],
    project_notes_applied: bool,
    project_notes_len: int,
    audit: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Telemetry / MCP meta; omit when nothing configured."""
    if not exclude_skills and not routing_boosts and not project_notes_applied and not audit:
        return None
    return {
        "schema": "routing_overlay/1",
        "project_root_set": bool((project_root or "").strip()),
        "exclude_skills": sorted(exclude_skills),
        "routing_boosts": {k: round(float(v), 4) for k, v in sorted(routing_boosts.items())},
        "project_notes_applied": project_notes_applied,
        "project_notes_len": int(project_notes_len),
        "audit": list(audit),
    }


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
