"""Write project-local Skillforge bootstrap files (.cursor, .claude/commands, PRD, CLAUDE.md)."""
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
    """Create or update Cursor rule + command, Claude Code command, PRD stub, and CLAUDE.md section.

    merge=False skips overwriting existing `.cursor/rules/skillforge.mdc`,
    `.cursor/commands/skillforge.md`, and `.claude/commands/skillforge.md` if they already exist
    (other files still update).
    """
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

When the user invokes **Skillforge**, types **`/skillforge`** (Cursor or **Claude Code** project command), or needs deep SKILL.md guidance for this codebase:

1. Call **route_skills** with **`project_root`** set to this workspace root (so learning and SQLite live in **`.skillforge/`** here), the user's task, and optional **session_id** (reuse within a thread for reroute stats). If the host sets **`SKILLFORGE_PROJECT_ROOT`**, you can omit **project_root** on each call.

   If **`SKILLFORGE_ROUTER_MODE=host`**: first **`route_skills`** without **`picked_names`** (shortlist only); then call again with **`picked_names`** for the chosen catalog ids before continuing.
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

    cursor_cmd = root / ".cursor" / "commands" / "skillforge.md"
    _assert_under(root, cursor_cmd)
    cursor_cmd.parent.mkdir(parents=True, exist_ok=True)
    cmd_body = f"""# Skillforge — route SKILL.md context (MCP)

The user chose the **`/skillforge`** project command. Use the **skillforge** MCP server.

## Do this

1. **`route_skills`**: pass **`project_root`** as this workspace root (absolute path) so SQLite lives in **`.skillforge/`** here. Pass the **current user task** as **`prompt`**. Reuse **`session_id`** across turns in the same thread when the MCP returns one.

   - **`SKILLFORGE_ROUTER_MODE=host`**: call once **without** **`picked_names`** (shortlist in the response); then call again with **`picked_names`** (exact catalog ids) to load skill context.
   - Optional: pass **`conversation`** when recent turns should influence routing.

2. **Use the returned skill text** in your answer (summarize or follow the SKILL.md guidance as appropriate).

3. Optionally **`materialize_project`** with the same **`project_root`** and **`skill_names`** from **`route_skills`** to refresh **`.cursor/rules`**, **`.cursor/commands`**, **`.claude/commands`**, and **docs/SKILLFORGE-PRD.md**.

## Skills last materialized for this project

{skills_md}
"""
    if cursor_cmd.exists() and not merge:
        pass
    else:
        cursor_cmd.write_text(cmd_body, encoding="utf-8")
        written.append(str(cursor_cmd.relative_to(root)))

    claude_cmd = root / ".claude" / "commands" / "skillforge.md"
    _assert_under(root, claude_cmd)
    claude_cmd.parent.mkdir(parents=True, exist_ok=True)
    cc_body = f"""---
description: Use Skillforge MCP route_skills for this repo. Invoke when the user runs /skillforge or needs routed SKILL.md context.
---

# Skillforge — route SKILL.md context (MCP)

Project-local **`/skillforge`** for **Claude Code**. Use the **skillforge** MCP server.

## Do this

1. **`route_skills`**: pass **`project_root`** as this workspace root (absolute path). Pass the **current user task** as **`prompt`**. Reuse **`session_id`** when returned.

   - **`SKILLFORGE_ROUTER_MODE=host`**: shortlist first, then **`picked_names`**.

2. **Use the returned skill text** in your answer.

3. Optionally **`materialize_project`** to refresh this file and **`.cursor`** files.

## Skills last materialized for this project

{skills_md}
"""
    if claude_cmd.exists() and not merge:
        pass
    else:
        claude_cmd.write_text(cc_body, encoding="utf-8")
        written.append(str(claude_cmd.relative_to(root)))

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
- **Cursor**: use **`/skillforge`** (**`.cursor/commands/skillforge.md`**) to steer the agent through **route_skills** for this workspace.
- **Claude Code**: use **`/skillforge`** (**`.claude/commands/skillforge.md`**) the same way.
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
- In Cursor, **`/skillforge`** is **`.cursor/commands/skillforge.md`**; in **Claude Code**, **`.claude/commands/skillforge.md`** (after **materialize_project**).

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
