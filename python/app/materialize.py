"""Write project-local Skillforge bootstrap files (.cursor, .claude/commands, PRD, CLAUDE.md)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

MARKER_START = "<!-- skillforge:auto:start -->"
MARKER_END = "<!-- skillforge:auto:end -->"


def normalize_materialize_hosts(raw: str | None) -> str:
    """Normalize MCP ``hosts`` argument: ``both`` | ``cursor`` | ``claude_code``."""
    s = (raw or "both").strip().lower().replace("-", "_")
    if s in ("both", "all", "*", ""):
        return "both"
    if s in ("cursor",):
        return "cursor"
    if s in ("claude_code", "claude"):
        return "claude_code"
    raise ValueError(f"hosts must be both, cursor, or claude_code — got {raw!r}")


def infer_materialize_hosts_from_mcp_client(
    client_name: str,
    client_title: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Best-effort host set from MCP ``initialize.params.clientInfo`` (and Cursor env hints)."""
    env = environ if environ is not None else os.environ
    blob = f"{client_name} {client_title}".lower()
    if "cursor" in blob:
        return "cursor"
    if "claude" in blob:
        return "claude_code"
    if env.get("CURSOR_TRACE_ID") or env.get("CURSOR_AGENT"):
        return "cursor"
    return "both"


def resolve_materialize_hosts_argument(
    raw: str | None,
    *,
    client_name: str = "",
    client_title: str = "",
    environ: Mapping[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Resolve MCP ``hosts``: explicit modes, or ``auto`` / omit → env then client inference."""
    envmap = environ if environ is not None else os.environ
    if raw is None:
        hosts_requested = ""
        rr = ""
    else:
        hosts_requested = str(raw).strip()
        rr = hosts_requested.lower().replace("-", "_")

    meta: dict[str, Any] = {
        "hosts_requested": hosts_requested,
        "mcp_client_name": client_name.strip(),
        "mcp_client_title": client_title.strip(),
    }

    if rr and rr != "auto":
        mode = normalize_materialize_hosts(hosts_requested)
        meta["hosts_resolution"] = "explicit"
        return mode, meta

    env_hosts = envmap.get("SKILLFORGE_MATERIALIZE_HOSTS", "").strip()
    if env_hosts:
        mode = normalize_materialize_hosts(env_hosts)
        meta["hosts_resolution"] = "environment"
        return mode, meta

    mode = infer_materialize_hosts_from_mcp_client(
        client_name, client_title, environ=envmap
    )
    meta["hosts_resolution"] = "inferred"
    return mode, meta


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
    hosts: str = "both",
) -> dict[str, Any]:
    """Create or update Cursor and/or Claude Code project stubs, docs, optional CLAUDE.md section.

    ``hosts``:
      - ``both`` (default) — Cursor rules/commands, Claude ``/skillforge``, ``docs/…``, ``CLAUDE.md``.
      - ``cursor`` — only ``.cursor/`` tree + docs (no ``.claude/``, no ``CLAUDE.md``).
      - ``claude_code`` — ``.claude/commands/``, ``docs/``, ``CLAUDE.md`` (no ``.cursor/``).

    merge=False skips overwriting existing host-specific command/rule files targeted by this run
    if they already exist (other destinations still update per ``hosts``).
    """
    mode = normalize_materialize_hosts(hosts)
    root = _safe_root(project_root)
    written: list[str] = []

    write_cursor = mode in ("both", "cursor")
    write_claude = mode in ("both", "claude_code")

    summaries = [
        f"- `{n}`: {(skill_descriptions.get(n) or '')[:160]}"
        for n in skill_names
    ]
    skills_md = "\n".join(summaries) if summaries else "_No skills listed._"

    if write_cursor:
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

   If **`host`** routing (default when **`SKILLFORGE_ROUTER_MODE`** is unset): first **`route_skills`** without **`picked_names`** (shortlist only); then call again with **`picked_names`** for the chosen catalog ids before continuing.
2. Inject the returned skill bodies into context before continuing.
3. To refresh project files, call **materialize_project** with **project_root** set to this workspace root and **skill_names** from the last **route_skills** result.

## Skills last materialized for this project

{skills_md}
"""
        if not (cursor_rule.exists() and not merge):
            cursor_rule.write_text(mdc_body, encoding="utf-8")
            written.append(str(cursor_rule.relative_to(root)))

        cursor_cmd = root / ".cursor" / "commands" / "skillforge.md"
        _assert_under(root, cursor_cmd)
        cursor_cmd.parent.mkdir(parents=True, exist_ok=True)
        cmd_body = f"""---
description: Route SKILL.md context via Skillforge MCP for this workspace (/skillforge). Use skillforge MCP route_skills.
---

# Skillforge — route SKILL.md context (MCP)

The user chose the **`/skillforge`** project command. Use the **skillforge** MCP server.

## Do this

1. **`route_skills`**: pass **`project_root`** as this workspace root (absolute path) so SQLite lives in **`.skillforge/`** here. Pass the **current user task** as **`prompt`**. Reuse **`session_id`** across turns in the same thread when the MCP returns one.

   - **`host`** routing (default when **`SKILLFORGE_ROUTER_MODE`** is unset): call once **without** **`picked_names`** (shortlist in the response); then call again with **`picked_names`** (exact catalog ids) to load skill context.
   - Optional: pass **`conversation`** when recent turns should influence routing.

2. **Use the returned skill text** in your answer (summarize or follow the SKILL.md guidance as appropriate).

3. Optionally **`materialize_project`** with the same **`project_root`** and **`skill_names`** from **`route_skills`** — use **`hosts: \"auto\"`** (default via MCP), **`\"cursor\"`**, **`\"claude_code\"`**, or **`\"both\"`** so only relevant IDE files refresh.

## Skills last materialized for this project

{skills_md}
"""
        if not (cursor_cmd.exists() and not merge):
            cursor_cmd.write_text(cmd_body, encoding="utf-8")
            written.append(str(cursor_cmd.relative_to(root)))

    if write_claude:
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

   - **`host`** routing (default when **`SKILLFORGE_ROUTER_MODE`** is unset): shortlist first, then **`picked_names`**.

2. **Use the returned skill text** in your answer.

3. Optionally **`materialize_project`** (**`hosts: \"auto\"`** (MCP default), **`\"claude_code\"`**, or **`\"both\"`**) to refresh this file.

## Skills last materialized for this project

{skills_md}
"""
        if not (claude_cmd.exists() and not merge):
            claude_cmd.write_text(cc_body, encoding="utf-8")
            written.append(str(claude_cmd.relative_to(root)))

    if write_cursor or write_claude:
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
- **Cursor**: use **`/skillforge`** (**`.cursor/commands/skillforge.md`**) after **materialize_project** with **`hosts: \"auto\"`**, **`\"cursor\"`**, or **`\"both\"`**.
- **Claude Code**: use **`/skillforge`** (**`.claude/commands/skillforge.md`**) after **materialize_project** with **`hosts: \"auto\"`**, **`\"claude_code\"`**, or **`\"both\"`**.
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

    if write_claude:
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

    return {"written": written, "project_root": str(root), "skill_names": list(skill_names), "hosts": mode}
