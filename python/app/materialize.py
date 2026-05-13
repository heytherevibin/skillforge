"""Write project-local Skillforge bootstrap files (.cursor/rules, docs PRD, CLAUDE.md block)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MARKER_START = "<!-- skillforge:auto:start -->"
MARKER_END = "<!-- skillforge:auto:end -->"


def _safe_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {raw!r}")
    return root


def _assert_under(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as e:
        raise ValueError(f"path escapes project_root: {path}") from e


def materialize_project_files(
    project_root: str,
    skill_names: list[str],
    skill_descriptions: dict[str, str],
    *,
    merge: bool = True,
) -> dict[str, Any]:
    """Create or update Cursor rule, PRD stub, and CLAUDE.md section. merge=False overwrites rule file only."""
    root = _safe_root(project_root)
    written: list[str] = []

    summaries = [
        f"- `{n}`: {(skill_descriptions.get(n) or '')[:160]}"
        for n in skill_names
    ]
    skills_md = "\n".join(summaries) if summaries else "_No skills listed._"

    cursor_rule = root / ".cursor" / "rules" / "skillforge.mdc"
    _assert_under(root, cursor_rule)
    cursor_rule.parent.mkdir(parents=True, exist_ok=True)
    mdc_body = f"""---
description: Use Skillforge MCP to route SKILL.md context for this repo
globs: []
alwaysApply: false
---

# Skillforge

When the user invokes **Skillforge**, **`/skillforge`**, or needs deep SKILL.md guidance for this codebase:

1. Call **route_skills** with **`project_root`** set to this workspace root (so learning and SQLite live in **`.skillforge/`** here), the user's task, and optional **session_id** (reuse within a thread for reroute stats). If the host sets **`SKILLFORGE_PROJECT_ROOT`**, you can omit **project_root** on each call.
2. Inject the returned skill bodies into context before continuing.
3. To refresh project files, call **materialize_project** with **project_root** set to this workspace root and **skill_names** from the last **route_skills** result.

## Skills last materialized for this project

{skills_md}
"""
    if cursor_rule.exists() and not merge:
        pass
    else:
        cursor_rule.write_text(mdc_body, encoding="utf-8")
        written.append(str(cursor_rule.relative_to(root)))

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    prd = docs_dir / "SKILLFORGE-PRD.md"
    _assert_under(root, prd)
    prd_body = f"""# Skillforge — project PRD (auto-generated stub)

Scaffold for goals and milestones. Re-run **materialize_project** after major routing or pack changes.

## Active routed skills

{skills_md}

## How to run Skillforge here

- **MCP**: configure the `skillforge` server (e.g. `npx -y @heytherevibin/skillforge mcp`). No API key required for embedding-only routing.
- **session_id**: reuse the same value across **route_skills** calls in one conversation thread.
- Re-bootstrap this project after new skills: **materialize_project** again.

## Goals

- [ ] (edit me)

## Non-goals

- [ ] (edit me)

## Milestones

- [ ] (edit me)
"""
    prd.write_text(prd_body, encoding="utf-8")
    written.append(str(prd.relative_to(root)))

    claude_md = root / "CLAUDE.md"
    skill_list = ", ".join(f"`{n}`" for n in skill_names) or "_(none)_"
    block = f"""{MARKER_START}

## Skillforge (project bootstrap)

Use [Skillforge](https://www.npmjs.com/package/@heytherevibin/skillforge) for **skill routing** via MCP.

- Call **route_skills** for the current task; reuse **session_id** within a thread.
- See **docs/SKILLFORGE-PRD.md** for the skill list and runbook.
- Map **`/skillforge`** in agent rules to the MCP tools above.

**Routed skills (last materialize):** {skill_list}

{MARKER_END}
"""
    _assert_under(root, claude_md)
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        if MARKER_START in text and MARKER_END in text:
            pattern = re.compile(
                re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
                re.DOTALL,
            )
            text = pattern.sub(block.strip(), text)
        else:
            text = text.rstrip() + "\n\n" + block
        claude_md.write_text(text, encoding="utf-8")
    else:
        claude_md.write_text(
            f"# CLAUDE.md\n\n{block}\n",
            encoding="utf-8",
        )
    written.append(str(claude_md.relative_to(root)))

    return {"written": written, "project_root": str(root), "skill_names": list(skill_names)}
