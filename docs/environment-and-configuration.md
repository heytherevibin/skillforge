# Environment & configuration

## Configuration layers (in merge order)

When you run **`skillforge <anything>`**, **Node `bin/cli.js`** builds a child **`process.env`** as follows:

1. **`~/.skillforge/env`** (optional dotenv-style file) — **`skillforge config path`**, **`init`**, **`validate`**.
2. **Current process env** — your shell, CI secrets, MCP host **`server.env`** / **`mcpServers.*.env`**.
3. **Bootstrap keys always set last by Skillforge** — at minimum **`PYTHONPATH`**, **`SKILLFORGE_BUNDLED_SKILLS`**, **`SKILLFORGE_USER_SKILLS`**, **`SKILLFORGE_DB_PATH`**, **`PYTHONUNBUFFERED=1`**.
4. **`SKILLFORGE_TRANSPORT=mcp`** is appended **only** for **`skillforge mcp`** (Python treats MCP differently from standalone CLI).

Higher layers override lower ones for overlapping keys—but built-in SKILLFORGE path keys always win over accidental values in **`~/.skillforge/env`**.

## ~/.skillforge/env (operator profile)

| Command | Purpose |
|---------|---------|
| **`skillforge config path`** | Print absolute path (`~/.skillforge/env`). |
| **`skillforge config init [--force]`** | Write commented template (`--force` overwrites). |
| **`skillforge config validate`** | Lint; **`error`** issues exit **1**; missing file exits **0**. |

**Syntax:** one **`KEY=value`** per line, optional **`export`**, **`#`** comments; variable names **`[A-Za-z_][A-Za-z0-9_]*`**; optional quotes. No shell **`${VAR}`** expansion—parser lives in **`lib/user-env-profile.js`**.

## MCP **`entry.env`** vs profile

If the IDE merges **`env`** into the **`skillforge mcp`** process, those vars sit in **layer 2** and **override** the same keys from **`~/.skillforge/env`**. Put **shared defaults** in the profile file; put **host-specific overrides** (or secrets the IDE injects exclusively) in **`mcp.json`**.

## SKILLFORGE_TRANSPORT (**MCP** only)

 **`skillforge mcp`** forces **`SKILLFORGE_TRANSPORT=mcp`**. In that mode router LLM wiring follows **Anthropic** legacy paths for MCP. Standalone CLI (no transport flag) may use **`SKILLFORGE_ROUTER_LLM_BACKEND=openai_compatible`** for OpenAI-compatible routing—see codebase **`app/main.py`** / **`app/router_llm.py`**.

## Direct Python (**advanced**)

If you bypass Node and run **`python -m app.mcp_server`**, **`~/.skillforge/env` is not read**. Either use **`skillforge mcp`** or replicate **`buildEnv()`** wiring yourself.

## Environment variable reference (operator table)

Below is reference text from the published operator docs. Defaults and parsing logic are implemented primarily in **`python/app/main.py`**, **`python/app/route_policies.py`**, **`python/app/db_paths.py`**, and MCP modules—if this table and code disagree, trust the repository.

| Variable | Role |
|----------|------|
| `ANTHROPIC_API_KEY` | Omit when **`SKILLFORGE_ROUTER_MODE`** is **`host`** (unset default) unless **`SKILLFORGE_HAIKU_RERANK`** or other modes invoke Haiku (**`skillforge mcp config --with-anthropic`** documents **`auto` + placeholder**). |
| `SKILLFORGE_ROUTER_MODE` | **`host`** (default when unset) · **`auto`** (legacy Haiku-if-key) · **`embedding`** · **`full`**. Empty string (**`=`** alone) normalises to **`auto`**. |
| `SKILLFORGE_TRANSPORT` | Set **`mcp`** by **`skillforge mcp`** only. |
| `SKILLFORGE_ROUTER_LLM_BACKEND` | Standalone/non-MCP: **`openai_compatible`** uses **`OPENAI_API_BASE`**, etc. Ignored under MCP transport. |
| `OPENAI_API_BASE`, `SKILLFORGE_OPENAI_API_BASE`, `OPENAI_API_KEY`, `SKILLFORGE_OPENAI_ROUTER_MODEL` | OpenAI-compatible router defaults. |
| `SKILLFORGE_AGENT_MODEL`, `SKILLFORGE_AGENT_API_KEY`, `SKILLFORGE_AGENT_API_BASE` | **`skillforge agent`** (**also **`OPENAI_*`** fallbacks). |
| `SKILLFORGE_EMBED_MODEL`, `SKILLFORGE_ROUTER_MODEL` | Embedding + Anthropic router model ids. |
| `SKILLFORGE_TOP_K`, `SKILLFORGE_MAX_ACTIVE` | Shortlist size and simultaneous skills cap. |
| `SKILLFORGE_REROUTE_THRESHOLD` | Re-route sensitivity (Jaccard distance). |
| `SKILLFORGE_ROUTER_CONV_MAX_TURNS`, `SKILLFORGE_ROUTER_CONV_MSG_CHARS` | Conversation fused into embedding/hybrid routing query (**0** turns = prompt-only). MCP preset: **`skillforge mcp config --companion`** (**`6`** / **`400`** defaults). Hosts should pass **`route_skills`** **`conversation`** when turns > **0**. See **[MCP integration — Companion preset](mcp-integration.md#companion-preset-mcp-json)**. |
| `SKILLFORGE_ROUTER_PROMPT_HISTORY_MSGS`, `SKILLFORGE_ROUTER_PROMPT_HISTORY_CHARS` | Conversation shown into router LLM prompts. |
| `SKILLFORGE_ROUTER_CATALOG_PREVIEW_CHARS` | Truncation in router catalog excerpts. |
| `SKILLFORGE_ROUTER_HYBRID`, `SKILLFORGE_ROUTER_HYBRID_ALPHA` | Hybrid sparse+dense (**`off`**, **`keyword`**, **`bm25`**). |
| `SKILLFORGE_HAIKU_RERANK`, `SKILLFORGE_HAIKU_RERANK_MAX`, `SKILLFORGE_HAIKU_RERANK_MODEL` | Optional rerank phase. |
| `SKILLFORGE_CONTEXT_MODE`, `SKILLFORGE_ROUTE_MAX_CHARS`, `SKILLFORGE_CHUNK_MAX_CHARS`, `SKILLFORGE_CHUNK_OVERLAP` | Chunking (**`skills`** + **`index`** reuse chunk tunables). |
| `SKILLFORGE_CONTEXT_FUSION`, `SKILLFORGE_CONTEXT_BUDGET_CHARS`, `SKILLFORGE_CONTEXT_MMR_LAMBDA`, `SKILLFORGE_FUSION_POOL_SKILL`, `SKILLFORGE_FUSION_POOL_PROJECT`, `SKILLFORGE_FUSION_FULL_BODY_PREVIEW_CHARS` | MMR fusion. |
| `SKILLFORGE_PROJECT_RAG_MAX_CHARS`, `SKILLFORGE_PROJECT_RAG_MAX_CHUNKS` | Project chunk retrieval caps. |
| `SKILLFORGE_PROJECT_NOTES_MAX_CHARS` | Cap **`project_notes`**. |
| `SKILLFORGE_REDACT_CONTEXT`, `SKILLFORGE_REDACT_HOME_IN_PATHS` | Redaction knobs. |
| `SKILLFORGE_MCP_USER_ID`, `SKILLFORGE_PROJECT_ROOT` | User scoping + DB/project resolution helpers. |
| `SKILLFORGE_MATERIALIZE_HOSTS` | Default host resolution when **`materialize_project`** **`hosts`** is **`auto`**. |
| `SKILLFORGE_ROUTE_POLICIES`, `SKILLFORGE_ROUTE_POLICIES_FILE` | Policies JSON (invalid JSON ⇒ stderr warning + empty rules — see Troubleshooting). |
| `SKILLFORGE_ROUTE_POLICIES_SHADOW`, `SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE` | Optional **shadow** policy JSON (same overlay shape as primary). When set, Skillforge runs a second embedding shortlist for comparison and attaches **`route_quality.policy_shadow`** — **does not** change primary routing or regex rule merges. Inline wins over file if both are set. Shadow uses the **pre-project-notes** embedding query (**prompt + optional operator memories**, not primary **`project_notes`**). |
| `SKILLFORGE_ROUTE_MEMORY`, `SKILLFORGE_ROUTE_MEMORY_MAX_CHARS`, `SKILLFORGE_ROUTE_MEMORY_MAX_ROWS`, `SKILLFORGE_ROUTE_MEMORY_DEFAULT_TTL_DAYS` | When **`SKILLFORGE_ROUTE_MEMORY`** is truthy, active SQLite operator memories (MCP **`route_memory_*`**) are fused into the embedding routing query before policy **`project_notes`**. Caps bound rows/chars; default TTL applies on append when **`ttl_days`** is omitted. |
| `SKILLFORGE_ROUTE_MEMORY_DEDUP` | Truthy ⇒ **`route_memory_append`** updates an existing non-expired row when **whitespace-normalised** **`body`** matches (same **`user_id`** + **`project_scope`**), refreshing **`created_at`**, **`importance=max`**, TTL extended to later **`expires_at`**. |
| `SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS` | When set (>0), fusion **`fetch`**/`merge` and **`route_memory_list`** rank by **`importance × 2^(-age_days/H)`** (read-time; stored **`importance`** unchanged). |
| `SKILLFORGE_ROUTE_TRACE_LEVEL` | **`off`** (default) \| **`compact`** \| **`full`** — adds MCP **`route_skills`** **`_meta.decision_trace`** (+ **`trace_digest`** / optional **`decision_trace`** embedded in **`events`** when **`full`**). Correlation **`routing_correlation_id`** is always returned on routed responses. |
| `SKILLFORGE_HOST_PICK_MAX`, `SKILLFORGE_HOST_PICK_LINE_CHARS` | Host-mode shortlist formatting. |
| `SKILLFORGE_ROUTE_AMBIGUITY_COS_MARGIN`, `SKILLFORGE_ROUTE_AMBIGUITY_ROUTE_MARGIN` | **`route_quality`** ambiguity heuristics. |
| `SKILLFORGE_ROUTE_AMBIGUITY_DISABLE` | Disable ambiguity tier heuristics. |
| `SKILLFORGE_PICK_DIVERSIFY`, `SKILLFORGE_PICK_MAX_PER_SOURCE` | Per-source pick thinning before policy merge. |
| `SKILLFORGE_WEIGHT_HALF_LIFE_DAYS` | When set (>0), routing applies read-time freshness on stored **`skill_weights.weight`** (see **`feedback_effect.weight_formula`**): `effective = stored × 2^(-age_days/H)`. Omit for legacy unchanged bias. |
| `SKILLFORGE_ROUTER_LLM_RETRIES` | Max attempts for **`router_llm`** Haiku/OpenAI-complete phases (default **`1`** = previous single try; capped at **8**). Exponential backoff on retryable failures. |
| Paths | **`SKILLFORGE_BUNDLED_SKILLS`**, **`SKILLFORGE_USER_SKILLS`**, **`SKILLFORGE_DB_PATH`** (normally set by CLI). |
| Skill manifests | **`SKILLFORGE_SKILL_MANIFEST_STRICT`** — invalid skills skipped at catalog load (**`skills lint`**). |
| Project index | **`SKILLFORGE_INDEX_MAX_FILE_BYTES`**, **`SKILLFORGE_INDEX_IGNORE_DIRS`**. |
| Hot reload | **`SKILLFORGE_SKILL_HOT_RELOAD`**, **`SKILLFORGE_WATCH_SKILLS_INTERVAL`**, **`SKILLFORGE_MCP_LIST_CHANGED`**. |
| Editor hooks install | **`SKILLFORGE_SKIP_CURSOR_SETUP`**, **`SKILLFORGE_SKIP_CLAUDE_CODE_SETUP`**, **`SKILLFORGE_CURSOR_GLOBAL_COMMAND`**, **`SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND`**. CLI (**0.11.10**+): **`--hosts=`** · **`--force-cursor`** · **`--force-claude`** / **`--force-claude-code`** · both force ⇒ all hosts · **`--only-cursor`** / **`--only-claude-code`** · **`--force`**. CLI (**0.11.11**+): **`skillforge help --ui`**, **`--browse`**. CLI / MCP (**0.11.12**+): **`route_skills` `dry_run`**, **`SKILLFORGE_ROUTE_TRACE_LEVEL`**, **`routing_correlation_id`**. Regression (**0.11.13**+): **`skillforge route-eval ingest`**. Policy shadow (**0.11.14**+): **`SKILLFORGE_ROUTE_POLICIES_SHADOW*`**, MCP **`1.10`**. Ops (**0.11.15**+): **`SKILLFORGE_WEIGHT_HALF_LIFE_DAYS`**, **`skillforge events prune --execute`**, **`skillforge replay`** time/type filters, **`SKILLFORGE_ROUTER_LLM_RETRIES`**, **`idx_events_user_type_ts`**. Operator memories (**0.11.16**+): **`SKILLFORGE_ROUTE_MEMORY*`**, **`route_memory_*`**, MCP **`1.11`**. Event snapshot + decay/dedup (**0.11.17**+): **`events.route_memory`**, **`SKILLFORGE_ROUTE_MEMORY_DEDUP`**, **`SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS`**, **`python -m app.verify_route_memory_cli`**. MCP companion preset (**0.11.18**+): **`skillforge mcp config --companion`**, **`capabilities.mcp_companion`**. **npm publish** tarball (**0.11.19**+): **`package.json` `files`** (**`python/app/*.py`**), **`.npmignore`**, **`release.yml`** **Strip** (**`skills/**/tests`**, **`python/app/__pycache__`**). |
| **`SKILLFORGE_MCP_SERVER_VERSION`** | Overrides **`capabilities`** / MCP reported semver (**`published_package_version()`**). |

---

**Related:** **[MCP integration](mcp-integration.md)** · **[Troubleshooting](troubleshooting.md)**
