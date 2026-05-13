# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge?label=npm&color=blue" alt="npm version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
</p>

**Skillforge** is a **skill orchestration co-tool for Claude** (and other MCP hosts). It keeps a catalog of **`SKILL.md`** skills, **routes** the few that match each task using **local embeddings** and an optional **Haiku** step, and returns their bodies for **injection into the host model**. Optional **SQLite** learning improves routing over time.

**Primary interface:** **stdio MCP** (`skillforge mcp`) — add it to Claude Desktop, Cursor, or Claude Code.

**Observability:** run **`skillforge events --watch`** in a terminal (top skills, active sessions, and live **route** / **feedback** lines from SQLite).

---

## Table of contents

- [Why Skillforge](#why-skillforge)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Run modes](#run-modes)
  - [Model Context Protocol (MCP)](#model-context-protocol-mcp)
    - [MCP response contract](#mcp-response-contract)
- [Skills and packs](#skills-and-packs)
- [Routing pipeline](#routing-pipeline)
- [Configuration](#configuration)
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
| **Deployment flexibility** | **MCP stdio** as the default integration; **CLI** helpers (`route`, `events`, `index`). |

Bundled content includes **200+** curated skills (coding, security, research, frontend/backend patterns, and more). Exact counts are validated in CI.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|--------|
| **Node.js** | **>= 18** | Required for the CLI bootstrapper. Continuous integration runs on **Node 22**. |
| **Python** | **>= 3.10** | Used on the host PATH for embeddings and routing (via the CLI-spawned **venv**). |
| **Anthropic API** | — | **`ANTHROPIC_API_KEY`** enables the **full** (Haiku) router when you want it. **MCP** can run **without** it using **embedding-only** routing (default when the key is omitted; see [MCP](#model-context-protocol-mcp)). |

**First run:** The CLI creates **`~/.skillforge/`**, a dedicated **Python venv**, installs Python dependencies, and caches the default embedding model (typically on the order of one to two minutes once; subsequent starts are fast).

---

## Quick start

```bash
npx --yes @heytherevibin/skillforge --help
```

Add Skillforge to your MCP config (see [MCP](#model-context-protocol-mcp)). No `ANTHROPIC_API_KEY` is required for **embedding-only** routing.

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
| `skillforge events [--watch]` | **Terminal** log: usage snapshot + routes; see **`skillforge events --help`**. |
| `skillforge route […]` | **Terminal** routing — same pipeline as MCP **`route_skills`** (loads embed model); see **`skillforge route --help`**. |
| `skillforge mcp config [--local] [--with-anthropic]` | **stdout**: JSON snippet for **`mcp.json`** (merge manually). |

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
| `route_skills` | Returns routed **`SKILL.md`** context (chunks or full body). Pass **`project_root`** for per-repo SQLite under **`.skillforge/orchestrator.db`**. Optional **`include_project_rag`** (after **`skillforge index --project-root=…`**), **`session_id`**, **`user_id`** / **`SKILLFORGE_MCP_USER_ID`**, or env **`SKILLFORGE_PROJECT_ROOT`**. Route **`event.policy`** in SQLite logs policy merge audit when rules apply. |
| `search_skills` | Embedding-only shortlist for a **`query`** (scores + description snippets); does not run Haiku or mutate sessions. Optional **`limit`** (max 50). |
| `explain_route` | Same routing signal as **`route_skills`** without writing SQLite (**`picked_before_policy`**, **`picked_after_policy`**, shortlist facets, policy audit). For debugging. |
| `get_skill` | Fetch one catalog skill by **`skill_name`**; **`format`**: **`full`** or **`summary`**; optional **`max_chars`**. |
| `list_skills` | Catalog overview; optional **`user_id`** scopes usage stats. |
| `skill_feedback` | Feedback for the learning loop; optional **`user_id`**, **`session_id`** (stored with events). |
| `skill_referenced` | Mark a routed skill as **used** in the reply (increments **`referenced`** + weight; optional **`user_id`**). |
| `disable_skill` | Toggle skills; optional **`user_id`**. |
| `materialize_project` | Writes **`.cursor/rules/skillforge.mdc`**, **`docs/SKILLFORGE-PRD.md`**, updates **`CLAUDE.md`** (Skillforge block). Args: **`project_root`**, **`skill_names`** from **`route_skills`**. |
| `skillforge_bootstrap` | **`route_skills`** + **`materialize_project`** in one call (needs **`project_root`**). |

### MCP response contract

Structured diagnostics for tool **`route_skills`** live in **`result._meta`** (hosts may ignore or log them):

- **`schema_version`**: **`1.4`** — same as **1.3** plus optional **`context_redaction`** (`enabled`, `secret_hits`, `path_hits`) on **`route_skills`** success.
- **`sources`**: citations; each item has **`kind`** (`skill` or **`file`**), **`ref`**, **`line_start`** / **`line_end`**, **`score`**, optional **`mmr_rank`** after fusion.
- **`fusion`**: present when MMR fusion ran (**`enabled`: true**): **`lambda`**, **`budget_chars`**, **`pool_skill`**, **`pool_project`**, **`mmr_trace`**, …
- **`context_redaction`**: optional; when scrubbing is enabled, reports **`enabled`**, **`secret_hits`**, **`path_hits`** for exported context.
- **`budget`**: **`chars_skill_bodies`**, **`chars_project_chunks`**, **`chars_context_items_total`**, **`chars_response_total`**, **`est_tokens_approx`** (rough `chars/4`).
- **`candidates_preview`**: up to 15 shortlist entries **`{ name, score }`** for debugging.
- **`picked`**, **`reasoning`**, **`session_id`**, **`user_id`**, **`rerouted`**, **`change_pct`**, **`route_ms`**, **`orchestrator_db`**.

On validation errors (e.g. empty **`prompt`**), the tool returns **`isError`: true** and **`_meta.error`** (e.g. **`empty_prompt`**), still with **`schema_version`** and **`sources`: `[]`**.

`/skillforge` is not registered by npm installs; add a **Cursor rule** or **CLAUDE.md** instruction so the agent calls these tools when the user asks.

Route events go to **`~/.skillforge/data/orchestrator.db`** (or per-repo **`.skillforge/orchestrator.db`** when **`project_root`** is set); use **`skillforge events`** to inspect them.

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
triggers: When the user asks about X or mentions Y.
anti_triggers: Not for production deploy checks.
---
# My Skill
```

Optional **`triggers`** / **`anti_triggers`** strings are embedded with the summary card and shown to the Haiku router (they do not change chunk RAG, which still keys off the current user message).

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
User prompt (+ optional recent conversation for the shortlist query)
    → Local embeddings (sentence-transformers) on skill **cards** (title, description, optional triggers)
    → Cosine similarity ± hybrid keyword/BM25 fusion + per-user weights
    → Top-K candidates
    → Optional Haiku **rerank** on the shortlist (`SKILLFORGE_HAIKU_RERANK`)
    → Router model (Haiku) selects final active skills — *or* embedding-only mode takes top-N from candidates
    → Skill bodies injected; response model answers (e.g. Opus)
    → Usage signals update weights (optional)
```

Re-route: when overlap between successive active sets falls below a configurable threshold, the pipeline selects a new set for the next turn. Events are stored in SQLite; stream them with **`skillforge events --watch`**.

---

## Route policies (optional)

Rules use **`if_text_matches`** as a Python **`re.search`** pattern (with **`re.DOTALL`**) on the user **`prompt`**. **`include`** is a skill name or list of names. Matched skills are **appended** after Haiku/embedding picks until **`SKILLFORGE_MAX_ACTIVE`**.

**Load order:** env **`SKILLFORGE_ROUTE_POLICIES`** (inline JSON) → **`SKILLFORGE_ROUTE_POLICIES_FILE`** → **`<project_root>/.skillforge/policies.json`** → **`<project_root>/skillforge-policies.json`**.

Example **`.skillforge/policies.json`**:

```json
{
  "rules": [
    {
      "if_text_matches": "(?i)(auth|oauth|jwt|password|login)",
      "include": ["security-review"]
    }
  ]
}
```

---

## Configuration

Environment variables (see also inline help and server defaults):

| Variable | Default | Role |
|----------|---------|------|
| `ANTHROPIC_API_KEY` | — | **Optional** for MCP: omit for embedding-only routing (default when unset); set for **full** (Haiku) routing. |
| `SKILLFORGE_ROUTER_MODE` | *(auto)* | `full` = always use Haiku for final pick (requires key). `embedding` = skip Haiku; top `SKILLFORGE_MAX_ACTIVE` from shortlist. Unset = **auto**: embedding-only when `ANTHROPIC_API_KEY` is absent, else full. |
| `SKILLFORGE_EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model id. |
| `SKILLFORGE_ROUTER_MODEL` | `claude-haiku-4-5-20251001` | Routing model (Haiku). |
| `SKILLFORGE_TOP_K` | `15` | Embedding shortlist size. |
| `SKILLFORGE_MAX_ACTIVE` | `7` | Maximum skills injected per turn. |
| `SKILLFORGE_REROUTE_THRESHOLD` | `0.4` | Re-route sensitivity (Jaccard distance). |
| `SKILLFORGE_ROUTER_CONV_MAX_TURNS` | `0` | Include this many recent **conversation** messages in the **embedding shortlist** query (`0` = current user message only, legacy). |
| `SKILLFORGE_ROUTER_CONV_MSG_CHARS` | `320` | Max characters per message when building the shortlist query. |
| `SKILLFORGE_ROUTER_HYBRID` | `off` | `off` = dense cosine only. `keyword` = fuse with token overlap on skill cards. `bm25` = fuse with **BM25** (requires **`rank-bm25`**; falls back to keyword if missing). |
| `SKILLFORGE_ROUTER_HYBRID_ALPHA` | `0.72` | Hybrid weight on **dense** similarity (`1` = dense only; `0` = sparse only). |
| `SKILLFORGE_ROUTER_PROMPT_HISTORY_MSGS` | `8` | Max conversation turns sent to the **Haiku** router and reranker. |
| `SKILLFORGE_ROUTER_PROMPT_HISTORY_CHARS` | `360` | Max characters per turn in router / rerank prompts. |
| `SKILLFORGE_ROUTER_CATALOG_PREVIEW_CHARS` | `280` | Max characters of each skill **routing card** in the Haiku pick prompt. |
| `SKILLFORGE_HAIKU_RERANK` | `0` | Set **`1`** / **`true`** to rerank the Top-K shortlist with Haiku before the final pick (extra API call). |
| `SKILLFORGE_HAIKU_RERANK_MAX` | `SKILLFORGE_TOP_K` | Max candidates passed to the reranker. |
| `SKILLFORGE_HAIKU_RERANK_MODEL` | *(same as router)* | Model id for reranking when set; otherwise **`SKILLFORGE_ROUTER_MODEL`**. |
| `SKILLFORGE_CONTEXT_MODE` | `chunks` | `chunks` = embed **line-bounded chunks** from each picked skill body (RAG) up to **`SKILLFORGE_ROUTE_MAX_CHARS`**. `full_body` = inject entire **SKILL.md** per pick (legacy). |
| `SKILLFORGE_CHUNK_MAX_CHARS` | `1200` | Max characters per chunk (before overlap split). |
| `SKILLFORGE_CHUNK_OVERLAP` | `200` | Character overlap when hard-splitting an oversized section. |
| `SKILLFORGE_ROUTE_MAX_CHARS` | `60000` | Skill chunk char cap when **`SKILLFORGE_CONTEXT_FUSION`** is off (append path); also part of default unified budget sum when fusion is on. |
| `SKILLFORGE_PROJECT_RAG_MAX_CHARS` | `24000` | Project chunk char cap when fusion is off (append path); part of default unified budget when fusion is on. |
| `SKILLFORGE_CONTEXT_BUDGET_CHARS` | *(route + project RAG defaults)* | Single cap for **MMR-fused** skill + project context. |
| `SKILLFORGE_CONTEXT_FUSION` | `1` | **`0`** / **`false`**: disable MMR fusion; append project chunks after skills. |
| `SKILLFORGE_CONTEXT_MMR_LAMBDA` | `0.7` | MMR tradeoff: higher ⇒ query relevance; lower ⇒ diversity vs. already-selected chunks. |
| `SKILLFORGE_FUSION_POOL_SKILL` | `96` | Max skill chunks in the fusion candidate pool. |
| `SKILLFORGE_FUSION_POOL_PROJECT` | `96` | Max project chunks in the fusion candidate pool. |
| `SKILLFORGE_FUSION_FULL_BODY_PREVIEW_CHARS` | `4000` | **`SKILL.md`** prefix length for embedding full-body / fallback fusion rows. |
| `SKILLFORGE_PROJECT_RAG_MAX_CHUNKS` | `20000` | Max **project_chunks** rows loaded for one retrieval. |
| `SKILLFORGE_INDEX_MAX_FILE_BYTES` | `524288` | Skip indexing files larger than this (bytes). |
| `SKILLFORGE_INDEX_IGNORE_DIRS` | `""` | Extra comma-separated directory **basename** ignores (e.g. `out,tmp`). |
| `SKILLFORGE_REDACT_CONTEXT` | `1` | When **`1`** (default), scrub common secret shapes and (with home path scrub) exported context before MCP/CLI output and route events. |
| `SKILLFORGE_REDACT_HOME_IN_PATHS` | `1` | Replace resolved home-directory prefixes in chunk paths / DB path hints with **`[HOME]`**. |
| `SKILLFORGE_MCP_USER_ID` | `""` | Default logical **user id** for MCP tool calls when arguments omit `user_id` (weights, sessions, events). |
| `SKILLFORGE_PROJECT_ROOT` | `""` | Default workspace root when MCP **`project_root`** is omitted: events/weights/sessions live in **`<root>/.skillforge/orchestrator.db`**. Prefer passing **`project_root`** on each tool call from the host. |
| `SKILLFORGE_SKILL_HOT_RELOAD` | `1` | When **`0`** / **`false`**, disable **SKILL.md** hot-reload; restart the MCP process to refresh the catalog. |
| `SKILLFORGE_WATCH_SKILLS_INTERVAL` | `30` | Seconds between background catalog checks when hot reload is on. **`0`**: no background polling and no MCP **`tools.listChanged`**; **`tools/list`** and **`tools/call`** still reload when files change. |
| `SKILLFORGE_MCP_LIST_CHANGED` | `1` | When **`0`** / **`false`**, never emit **`notifications/tools/list_changed`** (and **`listChanged`** is not advertised), even if a background interval is set. |
| `SKILLFORGE_ROUTE_POLICIES` | `""` | Optional inline JSON policies document (see [Route policies](#route-policies-optional)). |
| `SKILLFORGE_ROUTE_POLICIES_FILE` | `""` | Path to a policies JSON file. |

---

## Local data and operations

Optional **per-project** state (when **`project_root`** or **`SKILLFORGE_PROJECT_ROOT`** is set, or MCP passes **`project_root`** on tools):

```
<workspace>/.skillforge/
├── orchestrator.db   # SQLite: sessions, weights, events, **project_chunks** (after `skillforge index`)
├── policies.json     # Optional route policies (see README)
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
```

| Command | Effect |
|---------|--------|
| `skillforge events` | Prints a **usage** snapshot and recent **`route`** / **`feedback`** rows; **`--watch`**, **`--project-root`** (per-repo DB), **`--user`**, **`--verbose`** (see **`--help`**). |
| `skillforge index` | Chunk/embed text files under **`--project-root`** into **`project_chunks`**. **`--reset`**, **`--stats-only`**, **`--quiet`** (see **`--help`**). |
| `skillforge reset` | Clears learning state and event history in the database. |
| `skillforge install` | Re-runs bootstrap (venv and dependencies). |
| `rm -rf ~/.skillforge` | Full removal of local state and venv. |

---

## Security considerations

- **Redaction is best-effort regex scrubbing**, not a guarantee. Do not paste production secrets into prompts; treat routed context like **untrusted text** until reviewed.
- Treat **`ANTHROPIC_API_KEY`** as a **secret** when you set it (e.g. for Haiku routing in MCP). Prefer environment injection or secret stores, not committed files.
- Vulnerability disclosure: see **[SECURITY.md](SECURITY.md)**.

---

## Contributing and governance

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — workflow, local checks, branch policy expectations.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — community standards.
- **[SECURITY.md](SECURITY.md)** — reporting security issues.

---

## Releases and maintainers

- **Continuous integration:** `.github/workflows/ci.yml` (push and pull request to **`main`**).
- **Release & npm publish:** **Skillforge release** runs when you push tag **`vX.Y.Z`** and **`package.json`** **`version`** is exactly **`X.Y.Z`** (e.g. **`v0.2.1`** ↔ **`0.2.1`**). That same number is what **`npm publish`** ships. GitHub releases are titled **`Skillforge <tag>`**.
- **Procedure and npm tokens:** **[RELEASING.md](RELEASING.md)** (granular npm access tokens, **Bypass 2FA** for CI publish where applicable).
- **License:** MIT — see **[LICENSE](LICENSE)**.

---

## License

MIT © see [LICENSE](LICENSE).
