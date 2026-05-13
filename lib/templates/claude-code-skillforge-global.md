---
description: Run Skillforge MCP (route_skills) to load routed SKILL.md context. Use when the user invokes /skillforge, asks for Skillforge, or needs catalog skills for the repo.
---

<!-- skillforge-managed vPACKAGE_VERSION — remove this line to stop auto-updates from `skillforge install` -->

# Skillforge — route SKILL.md context (MCP)

Global **`/skillforge`** for **Claude Code** (same mechanism as `.claude/commands/*.md`). Configure the **skillforge** MCP server (see **`skillforge mcp config`**, project **`.mcp.json`**, or `claude mcp`). Optional: **`skillforge health`**, **`skillforge route-eval`**, **`skillforge weights export|import`**. MCP **`_meta.feedback_effect`** explains learned-ranking bias for picked skills when present.

## Do this

1. **`route_skills`** (MCP): pass **`project_root`** as the **current project root** (absolute path) so SQLite lives in **`<project>/.skillforge/`**. Pass the **user's task** as **`prompt`**. Reuse **`session_id`** across turns when the MCP returns it.

   - **`SKILLFORGE_ROUTER_MODE=host`**: first call **without** **`picked_names`** (shortlist only); second call **with** **`picked_names`**.

2. **Use the returned skill text** in your answer.

3. **Per-repo list:** run **`materialize_project`** after **`route_skills`** to refresh **`.claude/commands/skillforge.md`** and **`CLAUDE.md`**.
