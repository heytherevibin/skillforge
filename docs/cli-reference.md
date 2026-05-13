# CLI reference

**Entrypoint:** `bin/cli.js` (published as **`skillforge`** on npm).

All Python CLIs honour the merged environment (**`buildEnv`** in **`bin/cli.js`**). Prefer **`skillforge …`** rather than invoking **`python -m app.*`** manually unless you are developing core modules.

Run **`skillforge --help`** (or **`node bin/cli.js --help`**) for the condensed matrix; **`skillforge <cmd> --help`** forwards submodule help (**`route`**, **`agent`**, **`tools`**, …).

## Launch surface (by concern)

### Core workflows

| Command | Description |
|---------|-------------|
| **`skillforge mcp`** | Start stdio MCP server (**forces `SKILLFORGE_TRANSPORT=mcp`**). |
| **`skillforge route …`** | Same routing pipeline as MCP **`route_skills`** (TTY interactive **`-i`**, **`--json`**, **`--explain`**). |
| **`skillforge tools …`** | Subcommands mirror MCP tool handlers (**`skillforge tools -h`** enumerates verbs). **`--json`** prints raw MCP-shaped envelopes for automation. |
| **`skillforge agent …`** | Standalone OpenAI-compatible assistant loop invoking MCP-backed tool handlers (**`OPENAI_*`**, **`SKILLFORGE_AGENT_*`**). **`--help`** works before Python **`openai`** import; run **`skillforge install`** after upgrades when deps drift. |

### Workspace + catalog

| Command | Description |
|---------|-------------|
| **`skillforge index --project-root=…`** | Chunk/embed repository text · writes **`project_chunks`** per project SQLite. |
| **`skillforge skills …`** | **`list`**, **`add`**, **`remove`**, **`init`**, **`lint`** authoring helpers (**`skills_author_cli`**). |
| **`skillforge pack …`** | Install/list/update/remove git-hosted skill bundles (**`lib/packs.js`** bridge). |

### Observability / ops

| Command | Description |
|---------|-------------|
| **`skillforge events …`** | Tail SQLite routing / feedback events (**`--watch`**). |
| **`skillforge replay …`** | Timeline reconstructor across stored events (**`--session-id`**). |
| **`skillforge health …`** | Path + catalogue checks (**`--quick`** skips heavyweight embed/router load); JSON via **`--json`**. **`user_env_profile`** row notes whether **`~/.skillforge/env`** exists. |
| **`skillforge route-eval …`** | Fixture embedding harness (CI consumes **`fixtures/route_eval/*.json`**). |
| **`skillforge weights export|import …`** | Portable snapshots of **`skill_weights`**. |

### Setup / ergonomics

| Command | Description |
|---------|-------------|
| **`skillforge install`** | Provision **`~/.skillforge/venv`**, Python deps (**`requirements.txt`**), optional editor hooks (**`hosts init`** artefacts). |
| **`skillforge config path|init|validate`** | Stable **`~/.skillforge/env`** profile + linter (**`validate`** exit codes documented in env guide). |
| **`skillforge hosts init` / `skillforge cursor init`** | Write managed slash commands (**`/skillforge`**) — no Python prerequisite. |
| **`skillforge tips`** | Human-readable MCP + terminal cheat-sheet. |

## Flags worth memorising (**`skillforge route`**)

| Flag / env | Behaviour |
|------------|-----------|
| **`-i`** or **`SKILLFORGE_ROUTE_INTERACTIVE=1`** | Prompt for ranks after **`host`** shortlists (TTY only). |
| **`--json`** | Single envelope with **`phase`** markers for scripting (**`route_cli`**). |
| **`--picked-names=id1,id2`** | Implements second leg of **`host`** finalize. |

## Automation tip

Prefer **`skillforge tools <verb> … --json`** when you want identical payloads compared to MCP (great for scripted ops + CI probes).
