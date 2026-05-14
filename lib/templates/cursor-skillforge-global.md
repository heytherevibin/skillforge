---
description: Route SKILL.md context via Skillforge MCP (/skillforge). Configure the skillforge server in ~/.cursor/mcp.json — run skillforge mcp config for JSON.
---

# Skillforge — route SKILL.md context (MCP)

Global **`/skillforge`** command. Use the **skillforge** MCP server (configure in **`~/.cursor/mcp.json`** or your host; run **`skillforge mcp config`** for a JSON snippet; **`skillforge mcp config --companion`** for conversation-aware routing env). For local checks: **`skillforge health`** (preflight), **`skillforge route-eval`** (embedding routing smoke tests), and **`skillforge weights export|import`** (backup learned weights). **`route_skills`** responses can include **`_meta.feedback_effect`** (how thumbs / uses bias ranking for picked skills).

## Do this

1. **`route_skills`** (MCP): pass **`project_root`** as the **current workspace root** (absolute path) so SQLite lives in **`<workspace>/.skillforge/`**. Pass the **user's task** as **`prompt`**. Reuse **`session_id`** across turns when the tool returns one.

   - **`host`** routing (default when **`SKILLFORGE_ROUTER_MODE`** is unset): call once **without** **`picked_names`** (shortlist only); then call again with **`picked_names`** (exact catalog ids) to load skill context.
   - Pass **`conversation`** on **both** host calls when **`SKILLFORGE_ROUTER_CONV_MAX_TURNS` > 0** (recent turns as **`{role, content}`**). Prefer **`skillforge mcp config --companion`** so the server honors transcript context.

2. **Use the returned skill text** in your answer.

3. **Project-specific lists:** run **`materialize_project`** in a repo (after **`route_skills`**) to write **`.cursor/commands/skillforge.md`**, **`.cursor/rules/skillforge.mdc`**, and **`docs/SKILLFORGE-PRD.md`** with the latest **`skill_names`**.

<!-- skillforge-managed vPACKAGE_VERSION — remove this line to stop auto-updates from `skillforge install` -->
