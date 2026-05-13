# Skillforge

<p align="left">
  <a href="https://www.npmjs.com/package/@heytherevibin/skillforge"><img src="https://img.shields.io/npm/v/@heytherevibin/skillforge?label=npm&color=blue" alt="npm version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml"><img src="https://github.com/heytherevibin/skillforge/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
</p>

**Skillforge** is a **local-first orchestration layer** for agent workflows: it maintains a catalog of **`SKILL.md`** documents, **routes** a small subset per task using **embedding-first retrieval**, optional **hybrid** sparse signals and **LLM** stages, optional **project-scoped** policies and notes, and returns **structured context** for downstream models. The **primary integration** is **stdio MCP**; the **CLI** provides parity, operations, and automation hooks.

**Published version:** see **`package.json`** and the npm badge above (they should match after each release). **Change history:** [CHANGELOG.md](CHANGELOG.md). **Product direction:** [STRATEGY.md](STRATEGY.md). **Vulnerability reporting:** [SECURITY.md](SECURITY.md). **Release process:** [RELEASING.md](RELEASING.md).

---

## Table of contents

- [What Skillforge provides](#what-skillforge-provides)
- [Architecture at a glance](#architecture-at-a-glance)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Operational interfaces](#operational-interfaces)
- [Model Context Protocol (MCP)](#model-context-protocol-mcp)
- [MCP response contract](#mcp-response-contract)
- [Routing pipeline](#routing-pipeline)
- [Route policies and project overlay](#route-policies-and-project-overlay)
- [Project RAG](#project-rag)
- [Learning, weights, and portability](#learning-weights-and-portability)
- [Skills and packs](#skills-and-packs)
- [Configuration](#configuration)
- [Local data and paths](#local-data-and-paths)
- [Security](#security)
- [Contributing and governance](#contributing-and-governance)
- [License](#license)

---

## What Skillforge provides

| Area | Capability |
|------|------------|
| **Context control** | Returns only **relevant** skill (and optional project) chunks instead of an entire catalog. |
| **Routing** | Dense embeddings on skill **cards** (title, description, optional triggers); optional **keyword / BM25** fusion; optional **LLM** rerank and final pick—or **embedding-only** or **host-delegated** selection. |
| **Conversation-aware retrieval** | Recent turns can influence the **shortlist query** when enabled via environment (see [Configuration](#configuration)). |
| **Governance** | Regex **policies** to append skills after routing; **project overlay** for excludes, score boosts, and **project notes** (notes require a declared **project root**). |
| **Adaptation** | Per-user **SQLite** statistics and explicit feedback adjust routing over time (portable via **export/import**). |
| **Project grounding** | Optional **index** of repository text into the same SQLite DB used for sessions (**project RAG**). |
| **Observability** | Versioned **`_meta`** on MCP responses; route **events** in SQLite; **`skillforge events`** for operators. |
| **Reliability hooks** | **`skillforge health`** (preflight) and **`skillforge route-eval`** (fixture-driven smoke checks; used in CI). |

---

## Architecture at a glance

```
Host (Claude / Cursor / Claude Code / …)
        │  MCP JSON-RPC (stdio)
        ▼
┌───────────────────────────────────────────────────────────┐
│  skillforge mcp  →  Python: embed → shortlist → optional  │
│  LLM stages → policies/overlay → context assembly         │
└───────────────────────────────────────────────────────────┘
        │
        ├── SQLite (global ~/.skillforge or <project>/.skillforge)
        └── Optional: Anthropic API (Haiku) in-process when enabled
```

**Trust boundary:** Skillforge runs **on the operator’s machine** (or your CI runner). Prompts and retrieved text should be handled per your org’s data policy. See [Security](#security).

---

## Requirements

| Dependency | Notes |
|------------|--------|
| **Node.js** | **≥ 18** (CLI bootstrap). CI validates on **Node 22** (see `.github/workflows/ci.yml`). |
| **Python** | **≥ 3.10**; the CLI creates **`~/.skillforge/venv`** and installs `python/requirements.txt`. |
| **Anthropic API** | **Optional.** Without **`ANTHROPIC_API_KEY`**, routing stays **embedding-first** unless you delegate picks to the host. |

**First run** installs the virtualenv and Python dependencies and may download the default sentence-transformer model once; subsequent starts are typically fast.

---

## Quick start

```bash
npx --yes @heytherevibin/skillforge --help
```

Configure **MCP** in your host (see [Model Context Protocol](#model-context-protocol-mcp)). **Embedding-only** operation does not require an Anthropic key.

**Operator visibility:**

```bash
skillforge events --watch
```

**Preflight (after install):**

```bash
skillforge health --quick
```

---

## Installation

**Evaluate without global install**

```bash
npx --yes @heytherevibin/skillforge --help
```

**Global install**

```bash
npm install -g @heytherevibin/skillforge
skillforge --help
```

- **npm:** [@heytherevibin/skillforge](https://www.npmjs.com/package/@heytherevibin/skillforge)  
- **Source / issues:** [github.com/heytherevibin/skillforge](https://github.com/heytherevibin/skillforge)

---

## Operational interfaces

Skillforge is organized around a small **CLI** surface (implemented in **Node** spawning **Python** modules). Use **`skillforge <command> --help`** for flags.

| Group | Commands | Purpose |
|-------|----------|--------|
| **Core** | `mcp`, `route`, `events`, `index` | Primary routing, logs, project indexing. |
| **Reliability** | `health`, `route-eval` | Preflight checks; embedding-mode fixture evaluation (CI uses both). |
| **Learning portability** | `weights export`, `weights import` | Snapshot / restore **`skill_weights`** rows (JSON). |
| **Catalog** | `skills`, `pack` | User skills and git-backed **packs**. |
| **Setup** | `install`, `hosts init`, `reset` | Bootstrap venv, global `/skillforge` commands, wipe local DB state. |

**MCP config snippet (stdout):**

```bash
skillforge mcp config
# Optional: --local (checkout), --with-anthropic (env placeholder)
```

**Important:** MCP requires a **clean stdout** stream (JSON-RPC). Logs belong on **stderr**. If tools do not appear in the host, update the package and fully restart the host after setup.

---

## Model Context Protocol (MCP)

### Router modes (`SKILLFORGE_ROUTER_MODE`)

| Mode / default | Anthropic key | Behavior |
|----------------|---------------|----------|
| *(unset)* **auto** | optional | Embedding-first when key absent; full LLM routing when key present. |
| `embedding` | ignored for routing | No in-process LLM pick; top candidates drive selection. |
| `full` | recommended | LLM final pick; falls back per implementation on errors. |
| `host` | optional for pick | **Two-step:** first `route_skills` returns shortlist; second call passes **`picked_names`**. |

### MCP tools (summary)

| Tool | Role |
|------|------|
| `route_skills` | Main routing: **prompt**, optional **conversation**, **`project_root`**, **`include_project_rag`**, **`session_id`**, **`user_id`**, **`picked_names`** (host or override). |
| `search_skills` | Embedding shortlist for a **query** (read-only). |
| `explain_route` | Diagnostics: shortlist + picks + policy audit **without** writing sessions. |
| `get_skill`, `list_skills` | Catalog access. |
| `skill_feedback`, `skill_referenced`, `disable_skill` | Learning loop and toggles. |
| `materialize_project`, `skillforge_bootstrap` | Project file materialization (bootstrap **errors** in `host` mode by design—use two-step routing + materialize). |

Full argument lists: tool definitions in **`python/app/mcp_server.py`** (source of truth).

---

## MCP response contract

Successful **`route_skills`** responses include **`_meta`** built in **`python/app/mcp_contract.py`**. The **`schema_version`** string tracks additive JSON shape changes (hosts may rely on it for parsing).

**Authoritative version:** constant **`MCP_RESPONSE_SCHEMA_VERSION`** in **`app/mcp_contract.py`** (do not rely on this README if the two drift).

**Notable `_meta` fields (non-exhaustive):**

| Field | Description |
|-------|-------------|
| `schema_version` | Contract version string. |
| `sources`, `budget` | Chunk citations and size accounting. |
| `fusion` | Present when MMR-style fusion ran. |
| `context_redaction` | Redaction hit counts when enabled. |
| `route_quality` | Shortlist / router / policy / session telemetry for calibration. |
| `feedback_effect` | Per-pick **learned weight** snapshot (uses / thumbs / reference rate). |
| `routing_overlay` | Audit of **exclude** / **boost** / **project notes** application when configured. |
| `host_pick_shortlist`, `host_pick_candidates` | Host-pick phase payloads. |

Structured errors (e.g. empty prompt) return **`isError`: true** with **`_meta.error`** and **`schema_version`**.

---

## Routing pipeline

```
User prompt (+ optional conversation-aware routing query)
    → Encode routing query (skill cards + optional hybrid sparse signal)
    → Fuse scores + per-user weights + optional project overlay boosts
    → Shortlist (top-K)
    → Optional LLM rerank / final pick (or embedding / host selection)
    → Assemble context (skill chunks ± project chunks, optional fusion)
    → Return markdown + _meta; optional SQLite events
```

Re-routing when the active skill set changes significantly is controlled by **`SKILLFORGE_REROUTE_THRESHOLD`** (see [Configuration](#configuration)).

---

## Route policies and project overlay

### Regex policies (post-pick merge)

Rules match the user **`prompt`** with **`re.search`** (**`re.DOTALL`**). Matched **`include`** skills append after the router, capped by **`SKILLFORGE_MAX_ACTIVE`**. Audit lands on route **events** under **`policy`**.

**Load order:** **`SKILLFORGE_ROUTE_POLICIES`** (inline JSON) → **`SKILLFORGE_ROUTE_POLICIES_FILE`** → **`<project_root>/.skillforge/policies.json`** → **`<project_root>/skillforge-policies.json`**.

### Project routing overlay (same JSON document)

Optional keys alongside **`rules`**:

| Key | Aliases | Purpose |
|-----|---------|--------|
| `exclude_skills` | `host_exclude`, `denylist` | Remove skills from the embedding shortlist. |
| `routing_boosts` | `skill_boosts` | Additive score delta after learned weight (clamped; see **route_policies** module). |
| `project_notes` | `routing_notes`, `rag_notes` | Free text **prepended** to the internal routing query when **`project_root`** is set (not applied without a project root—mitigates accidental global injection from shared policy files). |

**Example fragment** (illustrative—adjust skill ids to your catalog):

```json
{
  "rules": [
    {
      "if_text_matches": "(?i)(auth|oauth|jwt)",
      "include": ["security-review"]
    }
  ],
  "project_notes": "Service stack and conventions for this repo (short, factual).",
  "routing_boosts": { "python-testing": 0.15 },
  "exclude_skills": ["legacy-skill-id"]
}
```

---

## Project RAG

1. **Index** repository text into **`<project>/.skillforge/orchestrator.db`**:

   ```bash
   skillforge index --project-root=/path/to/repo
   ```

2. Call **`route_skills`** with **`project_root`** and **`include_project_rag`** (or CLI **`--include-project-rag`**) when embeddings and schema match (see **`project_index.py`** for model/dimension guards).

Chunk caps and ignore rules are **environment-driven** (see configuration table).

---

## Learning, weights, and portability

- **Signals:** route **`uses`**, **`skill_referenced`**, **`skill_feedback`** (thumbs), and **`disable_skill`** feed **SQLite** **`skill_weights`**.
- **Transparency:** **`_meta.feedback_effect`** summarizes per-pick weight context after the route’s **`uses`** increment.
- **Portability:**

  ```bash
  skillforge weights export -o weights.json
  skillforge weights import weights.json
  ```

  Use **`--project-root`** / **`--user-id`** / **`--replace-user`** as documented in **`skillforge weights --help`** (implemented in **`python/app/weights_cli.py`**).

---

## Skills and packs

**Bundled catalog** ships inside the npm package. **CI** enforces a **minimum** bundled **`SKILL.md`** count so releases cannot silently ship an empty tree—the threshold lives in **`ci/bundle-gate.json`** (`minSkillMdFiles`); **`.github/workflows/ci.yml`** reads that file at build time.

**Custom skills:** directory with **`SKILL.md`** and YAML frontmatter (`name`, `description`; optional **`triggers`** / **`anti_triggers`**).

```bash
skillforge skills add ./path/to/skill
```

**Packs:** repositories with **`skillforge.json`**:

```bash
skillforge pack install <org/repo>
skillforge pack list
```

---

## Configuration

Environment variables tune routing, context budgets, redaction, MCP defaults, and file watchers. **Authoritative defaults and parsing** live in **`python/app/main.py`** and related modules—treat the table below as **operator reference**, not a legal spec.

| Variable | Role |
|----------|------|
| `ANTHROPIC_API_KEY` | Enables in-process **Haiku** routing / rerank when configured. |
| `SKILLFORGE_ROUTER_MODE` | `full` · `embedding` · `host` · auto. |
| `SKILLFORGE_EMBED_MODEL`, `SKILLFORGE_ROUTER_MODEL` | Model identifiers for embeddings / routing LLM. |
| `SKILLFORGE_TOP_K`, `SKILLFORGE_MAX_ACTIVE` | Shortlist size and max simultaneous skills. |
| `SKILLFORGE_REROUTE_THRESHOLD` | Re-route sensitivity (Jaccard distance). |
| `SKILLFORGE_ROUTER_CONV_MAX_TURNS`, `SKILLFORGE_ROUTER_CONV_MSG_CHARS` | Conversation-aware routing query. |
| `SKILLFORGE_ROUTER_HYBRID`, `SKILLFORGE_ROUTER_HYBRID_ALPHA` | Hybrid sparse/dense fusion. |
| `SKILLFORGE_HAIKU_RERANK`, `SKILLFORGE_HAIKU_RERANK_MAX`, `SKILLFORGE_HAIKU_RERANK_MODEL` | Optional rerank stage. |
| `SKILLFORGE_CONTEXT_MODE`, `SKILLFORGE_ROUTE_MAX_CHARS`, chunk envs | Skill body chunking vs full-body legacy. |
| `SKILLFORGE_CONTEXT_FUSION`, `SKILLFORGE_CONTEXT_BUDGET_CHARS`, `SKILLFORGE_CONTEXT_MMR_LAMBDA`, pool sizes | Skill + project **MMR** fusion. |
| `SKILLFORGE_PROJECT_RAG_MAX_CHARS`, `SKILLFORGE_PROJECT_RAG_MAX_CHUNKS` | Project chunk retrieval caps. |
| `SKILLFORGE_PROJECT_NOTES_MAX_CHARS` | Cap for **`project_notes`** prepended to routing query. |
| `SKILLFORGE_REDACT_CONTEXT`, `SKILLFORGE_REDACT_HOME_IN_PATHS` | Output redaction behavior. |
| `SKILLFORGE_MCP_USER_ID`, `SKILLFORGE_PROJECT_ROOT` | MCP defaults for user scoping and DB resolution. |
| `SKILLFORGE_ROUTE_POLICIES`, `SKILLFORGE_ROUTE_POLICIES_FILE` | Inline or file-backed policy JSON. |
| `SKILLFORGE_HOST_PICK_MAX`, `SKILLFORGE_HOST_PICK_LINE_CHARS` | Host-mode shortlist sizing / formatting. |
| Hot reload | `SKILLFORGE_SKILL_HOT_RELOAD`, `SKILLFORGE_WATCH_SKILLS_INTERVAL`, `SKILLFORGE_MCP_LIST_CHANGED`. |
| Install hooks | `SKILLFORGE_SKIP_*`, `SKILLFORGE_*_GLOBAL_COMMAND`, etc. |

---

## Local data and paths

**Per-project** (when **`project_root`** / **`SKILLFORGE_PROJECT_ROOT`** is used):

```
<workspace>/.skillforge/
├── orchestrator.db    # SQLite: sessions, weights, events, project_chunks (after index)
├── policies.json      # Optional policies + overlay (or repo-root skillforge-policies.json)
└── last_route.json    # Last CLI route snapshot (when applicable)
```

**Global default:**

```
~/.skillforge/
├── venv/
├── data/orchestrator.db
├── skills/            # User skills
└── packs/             # Pack working copies
```

| Command | Role |
|---------|------|
| `skillforge events` | Usage + recent **`route`** / **`feedback`** rows (`--watch`, `--project-root`, `--user`, `--verbose`). |
| `skillforge index` | (Re)build **`project_chunks`**. |
| `skillforge reset` | Clears learning + events in the target DB. |
| `skillforge health` | Validates paths, catalog discovery, optional deep router load. |
| `skillforge route-eval` | Runs JSON fixtures (CI). |

---

## Security

- **Redaction is best-effort.** Do not treat scrubbed output as a certified wipe of secrets.
- **Secrets:** keep **`ANTHROPIC_API_KEY`** and workspace tokens out of VCS; inject via host or OS secret stores.
- **Project notes** intentionally **do not apply** without **`project_root`** to reduce cross-talk from global policy config.
- **Disclosure:** follow **[SECURITY.md](SECURITY.md)** (private channels for undisclosed issues).

---

## Contributing and governance

| Document | Purpose |
|----------|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Workflow and local checks. |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community standards. |
| [SECURITY.md](SECURITY.md) | Reporting vulnerabilities. |
| [RELEASING.md](RELEASING.md) | Tags, **`NPM_TOKEN`**, npm **2FA** / granular tokens, CI vs release workflows. |
| [CHANGELOG.md](CHANGELOG.md) | Version-by-version changes. |
| [STRATEGY.md](STRATEGY.md) | Product direction and non-goals. |

**Continuous integration:** `.github/workflows/ci.yml` (**push** / **PR** to **`main`**).

**License:** [LICENSE](LICENSE) (MIT).
