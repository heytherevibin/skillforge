"""Short terminal+MCP cheatsheet emitted on demand (avoid loading the full README)."""


def main() -> None:
    text = """# Skillforge — quick tips

## After install (`skillforge install` or first `npx` run)

Your machine gets `~/.skillforge/` (venv, global DB, user skills).

Stable env (keys + tunables without shell paste): **`~/.skillforge/env`** — **`skillforge config path`**, **`skillforge config init`**, **`skillforge config validate`** (see README Configuration).

## MCP (Cursor / Claude / …)

- Wire with `skillforge mcp config` (see README for JSON merge targets).
- Default routing is **host**: first `route_skills` returns a **shortlist**, second call sends `picked_names`.
- **`capabilities`** tool: one JSON bundle — schema version, tool list, router snapshot — good for session start.

## Routing memories vs policy `project_notes` (SQLite)

When **`SKILLFORGE_ROUTE_MEMORY`** is **on**, MCP **`route_memory_*`** / **`skillforge tools memory-*`** store **operator bullets** that **prepend** the embedding query **before** policy **`project_notes`**. Prefer **committed `policies.json` / env policy** for shared repo rules (`exclude_skills`, boosts, **`project_notes`**); use **memories** for personal machine quirks so you don't duplicate canon. **`SKILLFORGE_ROUTE_MEMORY_DEDUP`** updates same normalised **`body`**; **`SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS`** soft-ranks staleness **read-time**. Verify: **`PYTHONPATH=. python -m app.verify_route_memory_cli`** (`package/python`). **Hosted sync**: not shipped — SQLite only.

## Terminal (same engine as MCP)

- `skillforge route "your prompt"` — two-step **host** mode mirrors MCP (shortlist stdout, then re-run):
  `skillforge route "…"` → `skillforge route "…" --picked-names=id1,id2`
- **`skillforge route -i`** (TTY) prompts for ranks/`1,3` or skill ids after the shortlist step.
  Or set **`SKILLFORGE_ROUTE_INTERACTIVE=1`** (still requires a tty).
- **`skillforge route --json`** prints one JSON envelope (**`phase`**: `host_shortlist_prompt`, `host_shortlist_static`, `context`, `explain_only`) with `route_meta` for scripts.
- **`skillforge route --explain`** attaches routing diagnostics (**stderr** Markdown, unless `--json` embeds **`explain`**).
- **`skillforge route --explain-only`** — diagnostics only (**no finalize** / no session-heavy side effects comparable to MCP `explain_route` intent).
- **`skillforge tools …`** (**`skillforge tools -h`**): MCP-equivalent subcommands; **`--json`** emits full tool envelopes.
- **`skillforge agent`**: OpenAI-compatible chat calling the same MCP tool handlers (**`OPENAI_API_BASE`**, **`SKILLFORGE_AGENT_*`**). Run **`skillforge install`** after upgrades so **`openai`** is installed into **`~/.skillforge/venv`**.

Docs: **`package/README.md`**.
"""
    print(text, end="")


if __name__ == "__main__":
    main()
