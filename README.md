# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge.svg?label=npm&logo=npm&logoColor=white&color=blue" alt="npm registry version" /></a>
  <a href="https://github.com/heytherevibin/skillforge/releases/latest"><img src="https://img.shields.io/github/v/release/heytherevibin/skillforge?sort=semver&label=github%20release&logo=github&color=purple" alt="Latest GitHub release tag" /></a>
  <a href="https://github.com/heytherevibin/skillforge/blob/main/package.json"><img src="https://img.shields.io/github/package-json/v/heytherevibin/skillforge?label=package.json%20%28main%29&logo=github" alt="package.json semver on GitHub default branch" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="GitHub Actions CI status" /></a>
</p>

**Skillforge** is a **local-first** SKILL.md orchestration layer: embeddings pick a **small routed set** per task (optional hybrid + LLM stages), SQLite stores **sessions, learned weights, and events**, optional **project RAG** augments prompts, and the **production surface** is **stdio MCP**. A **Node** CLI (**`skillforge`**) bootstraps a managed **Python venv** under **`~/.skillforge/venv`**, merges **`~/.skillforge/env`**, mirrors MCP behaviours in **`skillforge route`**, **`skillforge tools`**, **`skillforge agent`**, and exposes operator CLIs (**`health`**, **`events`**, **`weights`**).

**Semantic versions** should align across **`package.json`**, git tags (**`vX.Y.Z`**), MCP **`initialize.serverInfo.version`**, **npm tarball**, and the **GitHub Release** artifact—see [`RELEASING.md`](RELEASING.md). The **`package.json`** shield tracks **`main`**; **`npm`** / **`release`** shields track **published** artefacts and may briefly lag immediately after tagging.

---

## Documentation (start here)

| Guide | Audience |
|-------|-----------|
| [docs/README.md — index](docs/README.md) | Choose your path |
| [Getting started](docs/getting-started.md) | Install MCP + sanity checks |
| [Environment & configuration](docs/environment-and-configuration.md) | `~/.skillforge/env`, MCP host `entry.env`, and the full SKILLFORGE variable matrix |
| [MCP integration](docs/mcp-integration.md) | Router modes (**`host`**, **`auto`**, …), tools, **`_meta`** |
| [CLI reference](docs/cli-reference.md) | Subcommands (**`route`**, **`tools`**, **`agent`**, …) |
| [Architecture & data](docs/architecture-and-data.md) | Pipeline, SQLite, policies, indexing |
| [Troubleshooting](docs/troubleshooting.md) | Tools missing, npm **`EOTP`**, bad policy JSON |

**Project meta:** [`CHANGELOG.md`](CHANGELOG.md) · [`STRATEGY.md`](STRATEGY.md) · [`SECURITY.md`](SECURITY.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · [`RELEASING.md`](RELEASING.md)

---

## TL;DR — try it now

```bash
npx --yes @heytherevibin/skillforge --help
skillforge install            # provisions ~/.skillforge/venv when needed
skillforge mcp config         # stdout JSON snippet → paste into ~/.cursor/mcp.json, then restart IDE
skillforge tips && skillforge health --quick
skillforge config init        # optional ~/.skillforge/env template · skillforge config validate
```

**Default MCP routing (**`SKILLFORGE_ROUTER_MODE` unset ⇒ **`host`**) is two-step:** first **`route_skills`** shortlist · second finalize with **`picked_names`**.

---

## What ships in this repository

| Path | Purpose |
|------|---------|
| `bin/cli.js` | Node entry (`skillforge`); merges env (**`buildEnv`**) and spawns Python |
| `lib/` | Host setup, **`user-env-profile`** parser (`config validate`) |
| `python/app/` | Router, MCP server, SQLite, CLIs, contracts |
| `skills/` | Bundled SKILL.md corpus (CI minimum via `ci/bundle-gate.json`) |
| `ci/` | Node tests (**`test-user-env-profile.cjs`**), bundle gate JSON |
| `docs/` | Human-oriented guides (mirrors published npm tarball **`files`** list) |

**Tests:** **`npm test`** (Node **`--check`**) + **`cd python && pytest tests/`** in CI (**`.github/workflows/ci.yml`**).

---

## NPM package

Scoped package **`@heytherevibin/skillforge`**: **`npm install -g`** or **`npx -y`** (see badges above).

---

## License

[MIT License](LICENSE) © contributors.
