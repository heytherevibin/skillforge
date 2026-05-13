# Skillforge strategy (Cursor-first)

## Product intent

Skillforge is an **npm-packaged skill orchestrator**: it routes tasks to a small set of **SKILL.md** documents (embeddings + optional Haiku) and returns their bodies for agent context. **Per-project** learning and telemetry live under **`<workspace>/.skillforge/`** when **`project_root`** (or **`SKILLFORGE_PROJECT_ROOT`**) is set; otherwise the global DB under **`~/.skillforge/data/`** is used.

## Surfaces (today)

- **MCP** (`skillforge mcp`): primary — `route_skills`, `list_skills`, feedback tools, `materialize_project`, `skillforge_bootstrap`.
- **Terminal**: `skillforge events --watch` with optional **`--project-root`**.
- **HTTP** (`skillforge start`): optional; still uses the global DB in **app_state** (not per-request project root unless extended later).

## Cursor reality

Native **`/skillforge`** in editor chat is **not** registered by this npm package. The practical pattern is **Cursor rules** (e.g. materialized **`skillforge.mdc`**) instructing the agent to call MCP tools; users may *say* `/skillforge` as shorthand.

## Near-term backlog

- Shared **`orchestrate()`** API for MCP + CLI parity.
- HTTP: optional **`project_root`** header or body for `/chat` if needed.
- Tests: MCP handshake + `resolve_orchestrator_db` behavior.

## Non-goals (v1)

- Auto-scanning every AI agent installed on the host.
- VS Code extension (unless added as a separate track).
