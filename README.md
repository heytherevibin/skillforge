# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge.svg?label=npm&logo=npm&logoColor=white&color=blue" alt="npm registry version" /></a>
  <a href="https://github.com/heytherevibin/skillforge/releases/latest"><img src="https://img.shields.io/github/v/release/heytherevibin/skillforge?sort=semver&label=github%20release&logo=github&color=purple" alt="Latest GitHub release tag" /></a>
  <a href="https://github.com/heytherevibin/skillforge/blob/main/package.json"><img src="https://img.shields.io/github/package-json/v/heytherevibin/skillforge?label=package.json%20%28main%29&logo=github" alt="package.json semver on GitHub default branch" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="GitHub Actions CI status" /></a>
</p>

**Runtime SKILL routing for MCP hosts.** Skillforge selects a **small, task-relevant** subset of **`SKILL.md`** (and optional indexed project text) per request so agents stay grounded without loading full catalogs.

| Capability | Detail |
|------------|--------|
| **Primary integration** | **stdio MCP** (`skillforge mcp`) for Cursor, Claude Desktop, Claude Code, and compatible JSON-RPC hosts. |
| **Default control model** | **`host`** routing: shortlist → host-chosen **`picked_names`** — no Anthropic key required for embedding-first paths. Optional **`auto`** / **`embedding`** / **`full`** when keys and policies allow. |
| **Data plane** | **SQLite** under the operator profile and per-**`project_root`** `.skillforge/`: sessions, learned weights, **auditable route events**, optional **route memories**. |
| **Operator surface** | Node **`skillforge`** CLI delegates to a managed **Python** venv; **`skillforge tools`** mirrors MCP; **`health`**, **`events`**, **`replay`**, **`weights`**, **`route-eval`** for preflight and CI. |
| **Governance** | Regex **route policies** and **`project_notes`** overlays; companion preset **`mcp config --companion`** fuses **`conversation`** into embeddings when hosts pass transcript payloads. |

**Out of scope for the core package:** hosted multi-tenant SaaS, implicit cloud sync of operator SQLite, replacing the host’s model tier. See [`STRATEGY.md`](STRATEGY.md) · [`SECURITY.md`](SECURITY.md).

---

## Documentation

| Guide | Use when |
|-------|----------|
| [Documentation index](docs/README.md) | Choosing a reading order |
| [Getting started](docs/getting-started.md) | Install, MCP JSON, first checks |
| [Environment & configuration](docs/environment-and-configuration.md) | `~/.skillforge/env`, MCP `entry.env`, full **`SKILLFORGE_*`** matrix |
| [MCP integration](docs/mcp-integration.md) | Router modes, tools, **`_meta`**, companion preset |
| [CLI reference](docs/cli-reference.md) | Every **`skillforge`** subcommand |
| [Architecture & data](docs/architecture-and-data.md) | Pipeline, SQLite, policies, project RAG |
| [Troubleshooting](docs/troubleshooting.md) | Missing tools, npm **`EOTP`**, invalid policy JSON |

**Project meta:** [`CHANGELOG.md`](CHANGELOG.md) · [`STRATEGY.md`](STRATEGY.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · [`RELEASING.md`](RELEASING.md)

---

## Quick start

```bash
npx --yes @heytherevibin/skillforge --help
skillforge install
skillforge mcp config                    # paste JSON into host (e.g. ~/.cursor/mcp.json), restart IDE
skillforge mcp config --companion        # optional: embeddings fuse route_skills `conversation` when host sends transcript
skillforge health --quick && skillforge tips
skillforge config init && skillforge config validate   # optional ~/.skillforge/env
```

Unset **`SKILLFORGE_ROUTER_MODE`** ⇒ **`host`**: **`route_skills`** once for shortlist, again with **`picked_names`** (+ same **`session_id`**; pass **`conversation`** on both calls when using **`--companion`**).

---

## Routing context: policies vs route memories

- **`project_notes`** (from **route policies** JSON — [Environment & configuration](docs/environment-and-configuration.md)): repo-scoped overlays (**`exclude_skills`**, boosts, static notes prefixed into the embedding query). Prefer committing policies with the repository so CI and teammates share routing intent.
- **Route memories** (`SKILLFORGE_ROUTE_MEMORY`, MCP **`route_memory_*`**): operator-local bullets merged **before** **`project_notes`**. Use for personal or machine-specific quirks; prefer policies for canonical org rules.

Memories do **not** sync to Skillforge-hosted cloud; backup = SQLite / **`weights export`**. See **[Architecture & data](docs/architecture-and-data.md)**.

---

## What ships on npm

Publishing is **allowlisted** in **`package.json` `files`**: runtime **`python/app/*.py`** (not the full `python/` tree — **no** pytest tree, **no** bytecode in a clean git checkout), **`python/requirements.txt`**, **`skills/`**, **`bin/`**, **`lib/`**, **`ci/`**, **`docs/`**, and project meta markdown. **[`.npmignore`](.npmignore)** documents extra exclusions (caches, editor cruft). Because npm’s `files` field does not apply **`.npmignore`** to every nested path, the **Skillforge release** workflow removes any **`skills/**/tests`** directory and **`python/app/__pycache__`** immediately before **`npm pack`** / **`npm publish`** (see **[`.github/workflows/release.yml`](.github/workflows/release.yml)**). A local **`npm pack`** from a dirty tree may still include cached **`__pycache__`** or vendored tests — use a clean clone or match the release job’s **Strip** step if you need a bit-identical tarball.

| Path | Role |
|------|------|
| `bin/cli.js` | `skillforge` entry; merges env (`buildEnv`), spawns Python |
| `lib/` | Host setup, user env profile (`skillforge config validate`) |
| `python/app/*.py` | Router, MCP server, SQLite, CLIs (allowlist — no packaged pytest tree) |
| `python/requirements.txt` | Pip install targets for **`skillforge install`** |
| `skills/` | Bundled SKILL.md corpus (see **Strip** step in release workflow for vendored **`tests/`** dirs) |
| `ci/` | Node **`--test`** harness used by **`npm test`** |
| `docs/` | Operator guides |

**Automated checks:** **`npm test`** (Node). Full Python **`pytest`** runs in repository CI (**`.github/workflows/ci.yml`**), not shipped to consumers.

---

## Install

Scoped **`@heytherevibin/skillforge`**: global **`npm install -g`** or **`npx -y`** (see badges).

**Version line:** **`0.11.19`** on **`main`** aligns **`package.json`**, git tags **`v*`**, MCP **`serverInfo.version`**, and release artefacts — **[`RELEASING.md`](RELEASING.md)**.

---

## License

[MIT License](LICENSE) © contributors.
