# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge?label=npm&color=blue" alt="npm version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
</p>

**Skillforge** is a **skill orchestration co-tool for Claude** (and other MCP hosts). It keeps a catalog of **`SKILL.md`** skills, **routes** the few that match each task using **local embeddings** and an optional **Haiku** step, and returns their bodies for **injection into the host model**. Optional **SQLite** learning improves routing over time.

**Primary interface:** **stdio MCP** (`skillforge mcp`) — add it to Claude Desktop, Cursor, or Claude Code.

**Optional:** **headless HTTP API** (`skillforge start`) for `/chat`, `/events`, and integrations. **Real-time usage:** run **`skillforge events --watch`** in a terminal (top skills, active sessions, and live **route** / **feedback** lines from SQLite).

---

## Table of contents

- [Why Skillforge](#why-skillforge)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Run modes](#run-modes)
  - [Model Context Protocol (MCP)](#model-context-protocol-mcp)
  - [Multi-user authentication](#multi-user-authentication)
- [Skills and packs](#skills-and-packs)
- [Routing pipeline](#routing-pipeline)
- [Configuration](#configuration)
- [HTTP API](#http-api)
- [Local data and operations](#local-data-and-operations)
- [Security considerations](#security-considerations)
- [Contributing and governance](#contributing-and-governance)
- [Releases and maintainers](#releases-and-maintainers)
- [License](#license)

---

## Why Skillforge

| Capability | Description |
|------------|-------------|
| **Focused context** | Injects only a small set of skill documents per turn instead of the full catalog. |
| **Hybrid routing** | Embedding shortlist plus a fast **Claude Haiku** routing step for final selection. |
| **Adaptation** | Re-routes when the conversation topic shifts (configurable threshold). |
| **Learning loop** | Optional weights from usage and explicit feedback improve routing over time. |
| **Observability** | **`skillforge events`**: snapshots of **usage** + **active sessions**, **`--watch`** for realtime; **`--verbose`** for route detail. No browser UI. |
| **Project bootstrap** | MCP tools **`materialize_project`** and **`skillforge_bootstrap`** write `.cursor/rules`, **`docs/SKILLFORGE-PRD.md`**, and a **`CLAUDE.md`** section (map **`/skillforge`** in rules to MCP tools). |
| **Extensibility** | Custom skills, git-based **packs**, and overrides under a single user config directory. |
| **Deployment flexibility** | **MCP stdio** (default story), optional **HTTP API**, dev **`skillforge chat`** harness. |

Bundled content includes **200+** curated skills (coding, security, research, frontend/backend patterns, and more). Exact counts are validated in CI.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|--------|
| **Node.js** | **>= 18** | Required for the CLI bootstrapper. Continuous integration runs on **Node 22**. |
| **Python** | **>= 3.10** | Used on the host PATH for embeddings and the FastAPI orchestrator. |
| **Anthropic API** | — | **`ANTHROPIC_API_KEY`** is required for **HTTP**, **CLI chat**, and the **full** (Haiku) router. **MCP** can run **without** it when using **embedding-only** routing (default when the key is omitted; see [MCP](#model-context-protocol-mcp)). |

**First run:** The CLI creates **`~/.skillforge/`**, a dedicated **Python venv**, installs Python dependencies, and caches the default embedding model (typically on the order of one to two minutes once; subsequent starts are fast).

---

## Quick start

```bash
npx --yes @heytherevibin/skillforge --help
```

Add Skillforge to your MCP config (see [MCP](#model-context-protocol-mcp)). No `ANTHROPIC_API_KEY` is required for **embedding-only** routing.

Optional HTTP API (e.g. for `skillforge chat`): set **`ANTHROPIC_API_KEY`**, then:

```bash
skillforge start
```

Live log (usage + routes): **`skillforge events --watch`**.

---

## Installation

**One-shot (recommended for evaluation)**

```bash
npx --yes @heytherevibin/skillforge --help
```

**Global install**

```bash
npm install -g @heytherevibin/skillforge
skillforge --help
```

Package on npm: [@heytherevibin/skillforge](https://www.npmjs.com/package/@heytherevibin/skillforge).  
Source and issues: [github.com/heytherevibin/skillforge](https://github.com/heytherevibin/skillforge).

---

## Usage

### Run modes

| Command | Purpose |
|---------|---------|
| `skillforge --help` | Recommended first step; **MCP** is the main integration. |
| `skillforge mcp` | **stdio** MCP server (Claude, Cursor, …). |
| `skillforge start [--port=8000]` | Optional **HTTP API** (no HTML or WebSocket UI). |
| `skillforge events [--watch]` | **Terminal** log: usage snapshot + routes; see **`skillforge events --help`**. |
| `skillforge route […]` | **Terminal** routing — same pipeline as MCP **`route_skills`** (loads embed model); see **`skillforge route --help`**. |
| `skillforge mcp config [--local] [--with-anthropic]` | **stdout**: JSON snippet for **`mcp.json`** (merge manually). |
| `skillforge chat` | Dev harness: HTTP client to **`POST /chat`** (needs **`start`** + API key). |

### Model Context Protocol (MCP)

You can run the MCP server **without** `ANTHROPIC_API_KEY`: routing uses **embeddings + shortlist only** (no Haiku call). The host still uses its own billing for the conversation.

| `SKILLFORGE_ROUTER_MODE` | `ANTHROPIC_API_KEY` | MCP routing |
|--------------------------|---------------------|-------------|
| *(unset)* — auto | omitted | Embedding-only (keyless) |
| *(unset)* — auto | set | Full router (Haiku) |
| `embedding` | either | Embedding-only |
| `full` | set recommended | Full router (Haiku); falls back on API errors |

Add to your MCP host configuration (paths vary by product). Example for Claude Desktop on macOS (`claude_desktop_config.json`) **without** an extra API key:

```json
{
  "mcpServers": {
    "skillforge": {
      "command": "npx",
      "args": ["-y", "@heytherevibin/skillforge", "mcp"]
    }
  }
}
```

With **Haiku** routing (uses your Anthropic key in the MCP process):

```json
{
  "mcpServers": {
    "skillforge": {
      "command": "npx",
      "args": ["-y", "@heytherevibin/skillforge", "mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

**If the server shows as connected but lists “No tools”:** the MCP host only understands **JSON-RPC on stdout**. Older Skillforge builds printed setup text to **stdout**, which breaks **`tools/list`**. Update the npm package, run **`skillforge install`** once if needed, then **fully quit and reopen** Claude / Cursor. The CLI now sends banners and pip output to **stderr** only.

**MCP tools exposed**

| Tool | Purpose |
|------|---------|
| `route_skills` | Returns routed **`SKILL.md`** bodies. Pass **`project_root`** (workspace path) for per-repo SQLite under **`.skillforge/orchestrator.db`** and learning; or set env **`SKILLFORGE_PROJECT_ROOT`**. Optional **`session_id`**, **`user_id`** / **`SKILLFORGE_MCP_USER_ID`**. |
| `list_skills` | Catalog overview; optional **`user_id`** scopes usage stats. |
| `skill_feedback` | Feedback for the learning loop; optional **`user_id`**, **`session_id`** (for `/events`). |
| `skill_referenced` | Mark a routed skill as **used** in the reply (increments **`referenced`** + weight; optional **`user_id`**). |
| `disable_skill` | Toggle skills; optional **`user_id`**. |
| `materialize_project` | Writes **`.cursor/rules/skillforge.mdc`**, **`docs/SKILLFORGE-PRD.md`**, updates **`CLAUDE.md`** (Skillforge block). Args: **`project_root`**, **`skill_names`** from **`route_skills`**. |
| `skillforge_bootstrap` | **`route_skills`** + **`materialize_project`** in one call (needs **`project_root`**). |

`/skillforge` is not registered by npm installs; add a **Cursor rule** or **CLAUDE.md** instruction so the agent calls these tools when the user asks.

Route events go to **`~/.skillforge/data/orchestrator.db`**; use **`skillforge events`** or **`GET /events`** when HTTP is running.

### Multi-user authentication

Bearer tokens isolate sessions, weights, and events when enabled:

```bash
skillforge auth add <user-id>
skillforge auth list
skillforge auth remove <user-id>
```

When any token exists, protected **HTTP API** routes require **`Authorization: Bearer <token>`**. Single-user mode applies when no tokens are configured.

---

## Skills and packs

**Bundled skills** ship inside the package. List them:

```bash
skillforge skills list
```

**Custom skill** layout: a directory containing **`SKILL.md`** with YAML frontmatter at minimum:

```yaml
---
name: my-skill
description: Clear trigger conditions—used by the router.
---
# My Skill
```

Register with `skillforge skills add ./my-skill` or copy the folder to **`~/.skillforge/skills/`**.

**Skill packs** are git repositories with a root **`skillforge.json`** manifest listing skill folder names. Install:

```bash
skillforge pack install <org/repo>
skillforge pack install https://example.com/repo.git
skillforge pack list
skillforge pack update <name>
skillforge pack remove <name>
```

---

## Routing pipeline

```
User prompt
    → Local embeddings (sentence-transformers)
    → Cosine similarity + per-user weights
    → Top-K candidates
    → Router model (Haiku) selects final active skills — *or* embedding-only mode takes top-N from candidates
    → Skill bodies injected; response model answers (e.g. Opus)
    → Usage signals update weights (optional)
```

Re-route: when overlap between successive active sets falls below a configurable threshold, the pipeline selects a new set for the next turn. Events are stored in SQLite; stream them with **`skillforge events --watch`** (or **`GET /events`** when HTTP is running).

---

## Configuration

Environment variables (see also inline help and server defaults):

| Variable | Default | Role |
|----------|---------|------|
| `ANTHROPIC_API_KEY` | — | **Required** for HTTP/CLI chat and answer streaming; **optional** for MCP if you use embedding-only routing (default when unset). |
| `SKILLFORGE_ROUTER_MODE` | *(auto)* | `full` = always use Haiku for final pick (MCP: requires key for routing). `embedding` = skip Haiku; top `SKILLFORGE_MAX_ACTIVE` from shortlist. Unset = **auto**: MCP uses embedding-only when `ANTHROPIC_API_KEY` is absent, else full. HTTP: unset or `full` uses Haiku when key is present; set `embedding` to skip Haiku on the server (answer model still needs a key). |
| `SKILLFORGE_PORT` | `8000` | HTTP listen port. |
| `SKILLFORGE_EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model id. |
| `SKILLFORGE_ROUTER_MODEL` | `claude-haiku-4-5-20251001` | Routing model. |
| `SKILLFORGE_ANSWER_MODEL` | `claude-opus-4-7` | Main response model. |
| `SKILLFORGE_TOP_K` | `15` | Embedding shortlist size. |
| `SKILLFORGE_MAX_ACTIVE` | `7` | Maximum skills injected per turn. |
| `SKILLFORGE_REROUTE_THRESHOLD` | `0.4` | Re-route sensitivity (Jaccard distance). |
| `SKILLFORGE_MCP_USER_ID` | `""` | Default logical **user id** for MCP tool calls when arguments omit `user_id` (weights, sessions, events—same SQLite namespace as HTTP `resolve_user`). |
| `SKILLFORGE_PROJECT_ROOT` | `""` | Default workspace root when MCP **`project_root`** is omitted: events/weights/sessions live in **`<root>/.skillforge/orchestrator.db`**. Prefer passing **`project_root`** on each tool call from the host. |
| `SKILLFORGE_SKILL_HOT_RELOAD` | `1` | When **`0`** / **`false`**, disable **SKILL.md** hot-reload; restart the MCP process to refresh the catalog. |
| `SKILLFORGE_WATCH_SKILLS_INTERVAL` | `30` | Seconds between background catalog checks when hot reload is on. **`0`**: no background polling and no MCP **`tools.listChanged`**; **`tools/list`** and **`tools/call`** still reload when files change. |
| `SKILLFORGE_MCP_LIST_CHANGED` | `1` | When **`0`** / **`false`**, never emit **`notifications/tools/list_changed`** (and **`listChanged`** is not advertised), even if a background interval is set. |

---

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Primary chat; SSE stream. |
| `POST` | `/feedback` | Skill feedback for learning. |
| `POST` | `/skills/disable` | Enable/disable a skill flag. |
| `GET` | `/skills` | Catalog with stats and weights. |
| `GET` | `/events` | Recent routing events (`?limit=`). |
| `GET` | `/` | JSON service hint (use **`skillforge events --watch`** for a live terminal log). |
| `GET` | `/healthz` | Health metadata (`skills_loaded`, **`live_log`** hint). |

Authenticated mode applies **`Bearer`** tokens as described above. Do not expose unauthenticated instances beyond trusted networks.

---

## Local data and operations

Optional **per-project** state (when **`project_root`** or **`SKILLFORGE_PROJECT_ROOT`** is set, or MCP passes **`project_root`** on tools):

```
<workspace>/.skillforge/
├── orchestrator.db   # SQLite for this repo (sessions, weights, events)
└── last_route.json   # Last route_skills snapshot (after a routed call)
```

Global default when no project root:

```
~/.skillforge/
├── venv/                 # Python virtual environment
├── data/orchestrator.db  # SQLite (sessions, weights, events)
├── skills/               # User-added skills
├── packs/<hash>/         # Cloned pack repositories
├── packs.json            # Pack registry
└── auth.json             # Tokens (POSIX mode 0600 when used)
```

| Command | Effect |
|---------|--------|
| `skillforge events` | Prints a **usage** snapshot and recent **`route`** / **`feedback`** rows; **`--watch`**, **`--project-root`** (per-repo DB), **`--user`**, **`--verbose`** (see **`--help`**). |
| `skillforge reset` | Clears learning state and event history in the database. |
| `skillforge install` | Re-runs bootstrap (venv and dependencies). |
| `rm -rf ~/.skillforge` | Full removal of local state and venv. |

---

## Security considerations

- Treat **`ANTHROPIC_API_KEY`** and bearer tokens as **secrets**. Prefer environment injection or secret stores, not committed files.
- For **internet-facing** deployments, use **TLS**, **reverse proxies**, and **mandatory** bearer authentication; assume an open HTTP port is reachable by untrusted clients.
- Vulnerability disclosure: see **[SECURITY.md](SECURITY.md)**.

---

## Contributing and governance

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — workflow, local checks, branch policy expectations.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — community standards.
- **[SECURITY.md](SECURITY.md)** — reporting security issues.

---

## Releases and maintainers

- **Continuous integration:** `.github/workflows/ci.yml` (push and pull request to **`main`**).
- **Release & npm publish:** **Skillforge release** workflow on **semantic tags** `v*` matching **`package.json`** **`version`** (e.g. **`v0.1.0`** ↔ **`0.1.0`**). GitHub releases are titled **`Skillforge <tag>`**.
- **Procedure and npm tokens:** **[RELEASING.md](RELEASING.md)** (granular npm access tokens, **Bypass 2FA** for CI publish where applicable).
- **License:** MIT — see **[LICENSE](LICENSE)**.

---

## License

MIT © see [LICENSE](LICENSE).
