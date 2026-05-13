# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge?label=npm&color=blue" alt="npm version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
</p>

**Skillforge** is an adaptive **skill orchestration** layer for applications that use **Anthropic Claude**. It maintains a catalog of agent skills (`SKILL.md`), selects the few that matter for each user turn using **local embeddings** plus a **lightweight router model**, supports **mid-conversation re-routing**, optional **per-user learning**, and ships as a **single npm package** with a **Node** CLI and **Python** backend.

Use it as a **local HTTP service** (with dashboard), **terminal chat**, **stdio MCP server** for MCP-capable clients, or integrate via the **HTTP API**.

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
| **Observability** | Web dashboard and WebSocket stream for routing decisions and telemetry. |
| **Extensibility** | Custom skills, git-based **packs**, and overrides under a single user config directory. |
| **Deployment flexibility** | Same core behavior from **HTTP**, **CLI chat**, or **MCP stdio**. |

Bundled content includes **200+** curated skills (coding, security, research, frontend/backend patterns, and more). Exact counts are validated in CI.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|--------|
| **Node.js** | **>= 18** | Required for the CLI bootstrapper. Continuous integration runs on **Node 22**. |
| **Python** | **>= 3.10** | Used on the host PATH for embeddings and the FastAPI orchestrator. |
| **Anthropic API** | — | **`ANTHROPIC_API_KEY`** is required for routing and generation. |

**First run:** The CLI creates **`~/.skillforge/`**, a dedicated **Python venv**, installs Python dependencies, and caches the default embedding model (typically on the order of one to two minutes once; subsequent starts are fast).

---

## Quick start

```bash
export ANTHROPIC_API_KEY="sk-ant-…"
npx --yes @heytherevibin/skillforge
```

This starts the **HTTP server** and opens the **dashboard** (default port **8000**). Use **`skillforge chat`** for an interactive terminal session or **`skillforge mcp`** for MCP stdio mode after [global install](#installation).

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
| `skillforge` | HTTP server **and** dashboard (default browser open). |
| `skillforge start [--port=8000]` | HTTP server only. |
| `skillforge chat` | Interactive chat in the terminal. |
| `skillforge mcp` | **stdio** MCP server for external clients. |

### Model Context Protocol (MCP)

Add to your MCP host configuration (paths vary by product). Example for Claude Desktop on macOS (`claude_desktop_config.json`):

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

**MCP tools exposed**

| Tool | Purpose |
|------|---------|
| `route_skills(prompt)` | Returns bodies of routed **`SKILL.md`** files as text for client injection. |
| `list_skills()` | Catalog overview. |
| `skill_feedback(name, +1 \| -1)` | Feedback for the learning loop. |
| `disable_skill(name, true \| false)` | Toggle skills without deleting files. |

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
    → Router model (Haiku) selects final active skills
    → Skill bodies injected; response model answers (e.g. Opus)
    → Usage signals update weights (optional)
```

Re-route: when overlap between successive active sets falls below a configurable threshold, the pipeline selects a new set for the next turn. Events stream to the dashboard over **WebSocket**.

---

## Configuration

Environment variables (see also inline help and server defaults):

| Variable | Default | Role |
|----------|---------|------|
| `ANTHROPIC_API_KEY` | — | **Required** for API access. |
| `SKILLFORGE_PORT` | `8000` | HTTP listen port. |
| `SKILLFORGE_EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model id. |
| `SKILLFORGE_ROUTER_MODEL` | `claude-haiku-4-5-20251001` | Routing model. |
| `SKILLFORGE_ANSWER_MODEL` | `claude-opus-4-7` | Main response model. |
| `SKILLFORGE_TOP_K` | `15` | Embedding shortlist size. |
| `SKILLFORGE_MAX_ACTIVE` | `7` | Maximum skills injected per turn. |
| `SKILLFORGE_REROUTE_THRESHOLD` | `0.4` | Re-route sensitivity (Jaccard distance). |
| `SKILLFORGE_AUTH_TOKENS` | — | Managed by `skillforge auth`; internal use. |

---

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Primary chat; SSE stream. |
| `POST` | `/feedback` | Skill feedback for learning. |
| `POST` | `/skills/disable` | Enable/disable a skill flag. |
| `GET` | `/skills` | Catalog with stats and weights. |
| `GET` | `/events` | Recent routing events (`?limit=`). |
| `WS` | `/ws` | Live event stream (dashboard). |
| `GET` | `/` | Web dashboard. |
| `GET` | `/healthz` | Health metadata. |

Authenticated mode applies **`Bearer`** tokens as described above. Do not expose unauthenticated instances beyond trusted networks.

---

## Local data and operations

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
