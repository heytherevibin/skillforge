# Changelog

## 0.11.19

- **npm package layout:** **`package.json` `files`** now ship **`python/app/*.py`** and **`python/requirements.txt`** (no packaged **`python/tests/`** tree). **`.npmignore`** documents cache/editor exclusions. **`.github/workflows/release.yml`** deletes **`skills/**/tests`** and **`python/app/__pycache__`** before **`npm pack`** / **`npm publish`** so vendored SKILL test suites and bytecode caches never reach the registry tarball.
- **README:** Rewritten opener and structure for MCP-first positioning, governance, and publish semantics; **`package.json` `description`** and **`keywords`** aligned for discovery.

## 0.11.18

- **`skillforge mcp config --companion`:** Emits **`SKILLFORGE_ROUTER_CONV_MAX_TURNS=6`** and **`SKILLFORGE_ROUTER_CONV_MSG_CHARS=400`** merged into **`entry.env`** alongside **`SKILLFORGE_ROUTER_MODE`** (**`host`** when used alone or with **`--with-env`**; **`auto`** + key placeholder when combined with **`--with-anthropic`**). MCP **`route_skills`** **`conversation`** is then honored for embedding continuity; **`capabilities`** bundle documents **`mcp_companion`** workflow. Materialize **`.cursor`** / **`.claude`** **`/skillforge`** prompts stress **`session_id`** + **`conversation`** on both host-mode calls.

## 0.11.17

- **Route memory hardening:** **`route`** / **`host_shortlist`** **SQLite events** embed a compact **`route_memory`** block (`route_memory_event/1`) for replay/auditing (mirrors **`route_quality.route_memory`** subset). **`route_memory_append`** returns **`append_meta`** (dedup/upsize). Dedup (**`SKILLFORGE_ROUTE_MEMORY_DEDUP`**): re-append with whitespace-normalised same body **updates** the row (fresh **`created_at`**, **`importance=max`**, TTL extended to later expiry when both set). Soft ranking (**`SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS`**): fusion + **`route_memory_list`** sort by **`importance × 2^(-age_days/H)`** (read-time only; DB **`importance`** unchanged). Helpers: **`compact_route_memory_for_event`**. Smoke: **`python -m app.verify_route_memory_cli`**. **`tests/test_route_memory_integration.py`** exercises **`run_route_turn`** (**`host`** + mock router). Docs: **`skillforge tips`**, **`README`** (memories vs **`project_notes`**), **`architecture-and-data`**.

## 0.11.16

- **Governed routing memories:** SQLite **`route_memories`** (per **`user_id`**, **`project_scope`**, TTL) merged into the embedding **`route_query`** **before** policy **`project_notes`**, gated by **`SKILLFORGE_ROUTE_MEMORY`** (**`SKILLFORGE_ROUTE_MEMORY_MAX_CHARS`**, **`SKILLFORGE_ROUTE_MEMORY_MAX_ROWS`**, **`SKILLFORGE_ROUTE_MEMORY_DEFAULT_TTL_DAYS`**). Telemetry: **`route_quality.route_memory`** (`schema` **`route_memory_fusion/1`**). MCP tools **`route_memory_append`**, **`route_memory_list`**, **`route_memory_delete`**, **`route_memory_prune_expired`**; **`skillforge tools memory-*`** parity. **`explain_route`** uses the same fusion as **`route_skills`**. **`route_quality.policy_shadow`** base query includes memories when enabled. MCP schema **`1.11`**.

## 0.11.15

- **Learned weight half-life (opt-in):** **`SKILLFORGE_WEIGHT_HALF_LIFE_DAYS`** applies read-time freshness `2^(-age_days/H)` on stored **`skill_weights.weight`** bias (disabled skills unchanged). Default unset = legacy behavior. **`feedback_effect`** / **`get_skill_weight_detail`** add **`stored_learned_weight`** + **`decay_freshness_multiplier`** when active. See **`python/app/weight_semantics.py`**.
- **Event retention:** **`skillforge events prune --older-than-days N`** or **`--before-ts`** / **`--before`** — reports matched row count by default; **`--execute`** required to **`DELETE`**. Optional **`--vacuum`**. Shared helpers in **`python/app/events_query.py`**.
- **Replay export filters:** **`skillforge replay`** adds **`--min-ts`**, **`--max-ts`**, **`--event-types`**, **`--since-days`** (with **`--json`** or human timeline).
- **SQLite:** composite index **`idx_events_user_type_ts`** on **`events(user_id, event_type, ts)`** for filtered scans.
- **Router LLM resilience:** **`SKILLFORGE_ROUTER_LLM_RETRIES`** (default **`1`**, max **8**) with exponential backoff on retryable HTTP/SDK errors in **`AnthropicRouterLLM`** / **`OpenAIRouterLLM.complete`**.

## 0.11.14

- **Policy shadow (telemetry-only):** Set **`SKILLFORGE_ROUTE_POLICIES_SHADOW`** (inline JSON) or **`SKILLFORGE_ROUTE_POLICIES_SHADOW_FILE`** to run a second embedding **`shortlist_with_facets`** from the **base** routing query merged with **shadow** overlay (**`exclude_skills`**, **`routing_boosts`**, **`project_notes`**) — never overrides primary picks or primary policy merges. **`route_quality.policy_shadow`** records head names, **`jaccard_topk`**, and symmetric diffs (`schema`: **`policy_shadow_compare/1`**). Inline shadow env wins over file when both are set. MCP response schema **`1.10`** — see **`python/app/route_policy_shadow.py`**, **`python/app/route_policies.py`**, **`run_route_turn`**.

## 0.11.13

- **`skillforge route-eval ingest`**: Export **`route`** / **`host_shortlist`** rows from orchestrator SQLite into a **`route-eval`** fixture (`--expect-from picked|top_candidates|both|none`, `--keep-audit`, `--event-types`, `--newest-first`, `--session-id`). Prompts reproduce telemetry snippets (**≤ ~300 chars**). Implementation: **`python/app/route_eval_ingest.py`**, **`app.eval_cli ingest`**. Harness evaluation strips **`_…`** keys on cases automatically.

## 0.11.12

- **Trusted routing / enterprise observability:** Each routing turn allocates a **`routing_correlation_id`** (UUID) surfaced in MCP **`route_skills` `_meta`**, **`events`** payloads (**`route`**, **`host_shortlist`**), and the in-process result dict when persistence runs. Operators set **`SKILLFORGE_ROUTE_TRACE_LEVEL`** (`off` default, `compact`, `full`) to attach an optional MCP **`decision_trace`** (digest + shortlists; full adds **`route_quality_snapshot`**).
- **`route_skills` `dry_run`:** MCP boolean (and **`skillforge route --dry-run`**) skips **sessions**, **skill use increments**, **`events`** inserts for that call, and **`.skillforge/last_route.json`** — useful for staging. **`skillforge route-eval`** uses **`dry_run`** internally so eval does not perturb session/telemetry semantics.
- **MCP response schema:** **`1.9`** (**`routing_correlation_id`**, **`dry_run`**, **`decision_trace`**). See **`python/app/mcp_contract.py`**.

## 0.11.11

- **CLI help:** Structured help content in **`lib/help-content.js`** with **`renderHelp`** in **`lib/help-render.js`** — same plain matrix on **`skillforge --help`** (CI/script safe). **`skillforge help --ui`** (**`SKILLFORGE_HELP_UI=panels`**) renders boxed sections on TTY **`stderr`**; **`skillforge help --browse`** opens an interactive section picker (TTY only; otherwise falls back with a short notice). Covered by **`ci/test-help-render.cjs`**.

## 0.11.10

- **Setup / lifecycle:** **`--force-claude`** and **`--force-claude-code`** mirror **`--force-cursor`** (Claude Code–only + managed **`skillforge.md`** overwrite; Cursor untouched). Passing **both** **`--force-cursor`** **and** **`--force-claude`** (or **`--force-claude-code`**) now means **all hosts** + **`force`** (same as **`--hosts=all`** with overwrite semantics).

## 0.11.9

- **Setup / lifecycle:** **`--force-cursor`** now means **Cursor-only** host integration (still **forces** managed **`~/.cursor/commands/skillforge.md`** overwrite) and **does not** write Claude Code **`~/.claude/commands/skillforge.md`**. **`--hosts=cursor|claude-code|all`**, **`--only-cursor`**, **`--only-claude-code`**, **`--force-claude-code`** / **`--force-claude`** documented in **`--help`**; env overrides **`SKILLFORGE_SKIP_*`** unchanged.

## 0.11.8

- **CLI (`bin/cli.js`):** Fix **`skillforge tools <verb>`** argv forwarding (**`args.slice(1)`**) so **`app.tools_cli`** receives **`search`**, **`catalog`**, **`--json`**, and other flags (`0.11.7` accidentally dropped the verb).
- **`skillforge mcp config`:** Emits JSON immediately without implicit **`setupIfNeeded()`** (no surprise venv **`pip`** runs when pasting MCP snippets).
- **`skillforge install`:** If quiet **`pip`** fails, retry once verbosely; assert **`requirements.txt`** exists; **`ci/test-cli-shim.cjs`** guards the tools slice and **`mcp config`** bootstrap behavior.

## 0.11.7

- **Python router:** Restore **`Router.__init__`** so skill embeddings, **`_by_name`**, hybrid/BM25, and chunk indexing initialize correctly (fixes **`AttributeError: 'Router' object has no attribute '_by_name'`** in **`route-eval`** / **`run_route_turn`** when router setup was mistakenly unreachable behind the **`anthropic`** accessor).
- **Docs:** **`README`**, **`docs/`** guides, and **`RELEASING`** prose align release line **0.11.7** with **`package.json`**; MCP **`serverInfo.version`** sourcing is documented as **`python/app/npm_pkg_version.py`** (**`published_package_version()`**), not a duplicate field in **`mcp_server.py`**.

## 0.11.6

- **Documentation hub:** Added [`docs/`](docs/) with instructional guides (**[docs/README.md](docs/README.md)** lists them).
- **README refreshed:** Repo root **`README.md`** is a compact hub (**npm**, **GitHub release**, **`package.json` on main**, CI, licence badges; links into **`docs/`**).
- **npm package manifest:** **`docs/`** is included under **`files`** so published tarballs bundle the guides.
- **Hygiene:** Added repository **`.gitignore`** covering **`__pycache__`**, **`*.pyc`**, **`.pytest_cache/`**.

## 0.11.5

- **`skillforge config validate`:** Lint **`~/.skillforge/env`** (errors exit **1**, missing profile exits **0**). Parser extracted to **`lib/user-env-profile.js`** (shared semantics with merge). **`npm test`** runs **`node --test ci/test-user-env-profile.cjs`**, **`skillforge config validate`**, plus **`skillforge --help`**.
- **`skillforge mcp config --with-env`:** MCP snippet includes **`entry.env`** with **`SKILLFORGE_ROUTER_MODE=host`** (non-secret scaffold). **`--with-anthropic`** still replaces the **`env`** object entirely when both are passed.
- **`SKILLFORGE_ROUTE_POLICIES` / file policies:** **`stderr`** warning when JSON is invalid (policies ignored); tests in **`python/tests/test_route_policies.py`**.
- **README:** document **`validate`**, MCP **`--with-env`**, and that **`python -m app.*`** skips Node profile loading unless you replicate **`buildEnv`** yourself.
- **CLI:** **`node bin/cli.js --help`** (and **`-h`** as the first argument) prints the same banner as **`skillforge --help`**.
- **`capabilities` MCP bundle:** **`user_env_profile`** object with **`path_command`**, **`init_command`**, **`validate_command`**, **`file`** ( **`~/.skillforge/env`** ).

## 0.11.4

- **Operator env profile:** optional **`~/.skillforge/env`** dotenv-style file merged before **`process.env`** when spawning Python (**`skillforge config path`**, **`skillforge config init [--force]`**). Bootstrap **`SKILLFORGE_*_SKILLS`**, **`SKILLFORGE_DB_PATH`**, and **`PYTHONPATH`** still finalize last (**`bin/cli.js`**).
- **`skillforge health`** reports **`user_env_profile`** (whether **`~/.skillforge/env`** exists). **`skillforge tips`** mentions **`skillforge config`** and the README configuration section.

## 0.11.3

- **MCP operator tools (read-only):** **`get_router_status`** — env + loaded router snapshot; **`project_index_status`** — project chunk counts / last index metadata (**`project_root`** required); **`weights_snapshot`** — same JSON shape as **`skillforge weights export`**; **`events_recent`** — recent SQLite events for **`user_id`** with optional **`event_type`** filter (**`_meta.rows`** capped at 100). Implementations in **`app/mcp_operator.py`**.

## 0.11.2

- **Routing calibration (`route_quality`):** Bump inner schema to **`route_quality/2`**. **`shortlist`** adds **`ambiguous`**, **`confidence_tier`** (`high`/`medium`/`low`), **`routing_score_margin`**, **`second_routing_score`**, and **`cosine_leader_matches_routing_top`** (alias of **`top1_dense_and_fused_agree`**). Tunables: **`SKILLFORGE_ROUTE_AMBIGUITY_COS_MARGIN`** (default `0.012`), **`SKILLFORGE_ROUTE_AMBIGUITY_ROUTE_MARGIN`** (default `0.018`), **`SKILLFORGE_ROUTE_AMBIGUITY_DISABLE`**. **`router.pick_diversify`** records optional per-source thinning (below).
- **Pick diversify (opt-in):** When **`SKILLFORGE_PICK_DIVERSIFY=1`**, cap picks per **`source`** (**`bundled`** / **`user`**) via **`SKILLFORGE_PICK_MAX_PER_SOURCE`** (default **`2`**) **before** regex policy **`include`** merge. Applies to **`run_route_turn`** (MCP + CLI **`route`**) and **`explain_route`**.
- **MCP contract:** **`MCP_RESPONSE_SCHEMA_VERSION` 1.8** (additive **`_meta`** semantics; embedded **`route_quality`** v2).

## 0.11.1

- **MCP `materialize_project` / `skillforge_bootstrap`:** Default **`hosts`** is **`auto`**. Resolution order when **`hosts`** is **`auto`** or omitted: **`SKILLFORGE_MATERIALIZE_HOSTS`** (**`both`**, **`cursor`**, or **`claude_code`**) if set, else MCP **`initialize`** **`clientInfo`** name/title (substring **`cursor`** → **`cursor`**, **`claude`** → **`claude_code`**), optional **`CURSOR_AGENT`** / **`CURSOR_TRACE_ID`** hints, else **`both`**. Explicit **`hosts: cursor`**, **`claude_code`**, or **`both`** on the tool always wins. Responses add **`hosts_resolution`** (**`explicit`**, **`environment`**, or **`inferred`**) plus **`hosts_requested`**, **`mcp_client_name`**, **`mcp_client_title`** in **`materialize`** **`_meta`**.

## 0.11.0

- **Breaking (routing default):** When **`SKILLFORGE_ROUTER_MODE` is unset**, Skillforge now defaults to **`host`** (two-step **`route_skills`**: shortlist, then **`picked_names`**). Restore the previous **auto** behavior (**Haiku in-process when **`ANTHROPIC_API_KEY`** is set**, else embedding-first) with **`SKILLFORGE_ROUTER_MODE=auto`** or an empty value. Use **`embedding`** or **`full`** as before.
- **MCP config:** **`skillforge mcp config --with-anthropic`** now sets **`SKILLFORGE_ROUTER_MODE=auto`** together with the **`ANTHROPIC_API_KEY`** placeholder so the key is not ignored (default **host** mode does not call Anthropic).
- **Refactor:** **`app/router_mode.py`** — **`normalise_skillforge_router_mode`**; unit tests in **`python/tests/test_router_mode_env.py`**.
- **Docs / MCP tool text:** Describe default **host** routing and how to override (**README**, **`route_skills`** tool description).
- **Global/project `/skillforge` command:** YAML **`description`** in frontmatter (**`cursor-skillforge-global.md`**, **`claude-code-skillforge-global.md`**, **`materialize_project`** Cursor command); **`<!-- skillforge-managed … -->`** moved to EOF so Composer no longer uses the HTML marker as tooltip text.
- **`materialize_project`:** Optional **`hosts`**: **`cursor`**, **`claude_code`**, or **`both`** (default) — scaffold only the IDE folders you ask for instead of always writing **`.cursor/`** + **`.claude/`**.

## 0.10.1

- **README:** Clarify that **npm** **`latest`** and **`npm view`** are authoritative for semver; note CDN/browser cache can make the shields **npm** badge lag briefly after a publish. **Badge:** add **`cacheSeconds`** so the image URL refreshes sooner.

## 0.10.0

- **CI:** Minimum bundled **`SKILL.md`** count is configured via **`ci/bundle-gate.json`** (`minSkillMdFiles`); **`.github/workflows/ci.yml`** reads that file. The **`ci/`** directory is included in the published package **`files`** list for transparency. Health + **route-eval** step chains both commands under a single **`cd python`** so the second command does not run from **`python/python`**.
- **MCP `_meta`:** **`schema_version` 1.7** — optional **`routing_overlay`** (project exclude / boost / notes audit). **1.6** — optional **`feedback_effect`** (learned-weight transparency after each route). **1.5** — optional **`route_quality`** (shortlist, hybrid, policy/session signals). Implemented in **`app/mcp_contract.py`** (see constant **`MCP_RESPONSE_SCHEMA_VERSION`**).
- **Project routing overlay:** optional **`exclude_skills`**, **`routing_boosts`**, **`project_notes`** (and aliases) in the same JSON document as regex **`rules`** — parsed by **`app/route_policies.py`**, applied in **`Router`** shortlists; **`project_notes`** require **`project_root`** to apply.
- **Operator CLIs:** **`skillforge health`** (`python/app/health_cli.py`), **`skillforge route-eval`** (`eval_cli` + fixtures under **`python/fixtures/route_eval/`**), **`skillforge weights export|import`** (`weights_cli.py`). CI runs **health --quick** and embedding **route-eval** with **`SKILLFORGE_BUNDLED_SKILLS`** set to the workspace skills tree.
- **MCP / search & explain:** **`search_skills`** and **`explain_route`** honor the same overlay + notes as **`route_skills`**; **`explain_route`** passes explicit shortlist **`k`** into **`Router.shortlist`**.
- **Fix:** **`skillforge route`** defines **`db_disp`** before use in host-pick output (**`route_cli.py`**).

## 0.9.0

- **Host-delegated routing:** set **`SKILLFORGE_ROUTER_MODE=host`** to skip the in-process Haiku pick. First **`route_skills`** call returns a tight numbered shortlist (markdown + **`_meta.host_pick_candidates`**); second call with **`picked_names`** loads context, policies, and session **`uses`** as usual. No **`ANTHROPIC_API_KEY`** required for the pick step. Tunables: **`SKILLFORGE_HOST_PICK_MAX`**, **`SKILLFORGE_HOST_PICK_LINE_CHARS`**.
- **`picked_names`** on **`route_skills`** (optional): in **`embedding`** / **`full`** modes, supplying **`picked_names`** skips auto-pick and uses the host list (unchanged behavior, now documented).
- **`skillforge_bootstrap`** returns an error when **`SKILLFORGE_ROUTER_MODE=host`** (use two-step **`route_skills`** + **`materialize_project`**).
- **CLI:** **`skillforge route --picked-names=a,b`** mirrors MCP finalize. **`--json-meta`** includes **`host_pick_shortlist`** when applicable.
- **Cursor (global `/skillforge`)** and **Claude Code**: on **`skillforge install`** / first-run setup, Skillforge writes **`~/.cursor/commands/skillforge.md`** and/or **`~/.claude/commands/skillforge.md`** when each environment is detected; **`skillforge hosts init`** updates both without Python setup. Opt out: **`SKILLFORGE_SKIP_CURSOR_SETUP`**, **`SKILLFORGE_SKIP_CLAUDE_CODE_SETUP`**. Force: **`SKILLFORGE_CURSOR_GLOBAL_COMMAND`**, **`SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND`**. **`--force-cursor`** (since **0.11.9**): Cursor-only + overwrite managed Cursor file; use **`--force`** or **`--hosts=all`** to refresh both hosts. **Claude Desktop** remains detect-only + MCP merge hint.
- **MCP** server version **0.9.0**; **`materialize_project`** writes per-repo **`.cursor/commands`** and **`.claude/commands`** **`/skillforge`** with **`skill_names`**.

## 0.8.0

- **Smarter routing:** optional **conversation-aware** shortlist query (`SKILLFORGE_ROUTER_CONV_*`), **hybrid** retrieval (`SKILLFORGE_ROUTER_HYBRID` = `keyword` or `bm25` + `SKILLFORGE_ROUTER_HYBRID_ALPHA`), optional **Haiku rerank** (`SKILLFORGE_HAIKU_RERANK`, `SKILLFORGE_HAIKU_RERANK_MAX`, `SKILLFORGE_HAIKU_RERANK_MODEL`).
- **Skill cards:** YAML **`triggers`** / **`anti_triggers`** on **`SKILL.md`** are parsed and folded into summary embeddings and router prompts via **`app/routing_signals.py`** (`skill_routing_card`). Chunk RAG still scores on the **current** user message.
- **Dependency:** **`rank-bm25`** in `python/requirements.txt` (BM25 hybrid; optional at runtime if you use `keyword` only).

## 0.7.1

- **MCP:** **`search_skills`** (embedding shortlist + snippets), **`explain_route`** (routing diagnostics, no DB writes), **`get_skill`** (fetch one **`SKILL.md`** by name).
- **Route policies:** optional **`SKILLFORGE_ROUTE_POLICIES`**, **`SKILLFORGE_ROUTE_POLICIES_FILE`**, or **`project_root`/** `.skillforge/policies.json` / **`skillforge-policies.json`** — regex rules append **`include`** skills after the router (capped by **`SKILLFORGE_MAX_ACTIVE`**). Audit stored on route events under **`policy`**.

## 0.7.0

- **Breaking:** Removed the optional **HTTP API** (`skillforge start`), **`skillforge chat`** harness, and **`skillforge auth`** (bearer tokens were only used by HTTP). MCP (`skillforge mcp`), **`skillforge route`**, **`skillforge events`**, and **`skillforge index`** are unchanged.
- **Migration:** The CLI deletes a leftover **`~/.skillforge/auth.json`** on **every** invocation (including **`skillforge --help`**), once the file is gone the message stops.
- Dropped **FastAPI**, **uvicorn**, and direct **pydantic** / **httpx** dependencies from `python/requirements.txt` (routing still uses libraries that may bundle their own deps).

## 0.6.0

- **Phase 4 context safety (MCP meta 1.4)**: Default **secret / credential pattern redaction** and optional **home-directory stripping** on injected chunk text, relative **`path`** fields, stored route **`prompt`** snippet, **`reasoning`**, and **`orchestrator_db`** in **`_meta`**. Disable with **`SKILLFORGE_REDACT_CONTEXT=0`**; path scrub with **`SKILLFORGE_REDACT_HOME_IN_PATHS=0`**. New **[`app/redaction.py`](python/app/redaction.py)**; route events include **`context_redaction`** hit counts.

## 0.5.0

- **Phase 3 context fusion (MCP meta 1.3)**: When **`include_project_rag`** is on and the project index is non-empty, skill + project chunk **pools** are merged with **greedy MMR** under a single **`SKILLFORGE_CONTEXT_BUDGET_CHARS`** (default: route max + project RAG max). Disable with **`SKILLFORGE_CONTEXT_FUSION=0`** to keep append-only behavior.
- **Telemetry**: route events and **`_meta.fusion`** include MMR trace; each context item may carry **`mmr_rank`**, **`mmr_score`**, **`retrieval_relevance`**, **`max_sim_to_prior`**.
- New **[`app/context_fusion.py`](python/app/context_fusion.py)**; **`load_project_fusion_pool`** in **`project_index`**.

## 0.4.0

- **Phase 2 project RAG (MCP 1.2)**: **`skillforge index --project-root=…`** walks the repo (bounded file sizes, ignore dirs), chunks text files, and stores **`project_chunks`** + embeddings in **`<project>/.skillforge/orchestrator.db`** (same DB as sessions/weights).
- **MCP / CLI / HTTP**: optional **`include_project_rag`** (MCP + **`skillforge route --include-project-rag`**) appends top matching file chunks under **`SKILLFORGE_PROJECT_RAG_MAX_CHARS`**. **`_meta`**: schema **1.2**; **`sources`** may include **`kind: file`**; **`budget.chars_project_chunks`** / **`chars_context_items_total`**.

## 0.3.0

- **Phase 1 skill RAG (MCP 1.1)**: Default **`SKILLFORGE_CONTEXT_MODE=chunks`** — line-bounded chunks from each picked **`SKILL.md`** body, scored by query similarity, injected up to **`SKILLFORGE_ROUTE_MAX_CHARS`**. Set **`full_body`** for legacy whole-document injection per skill.
- **`_meta`**: schema **1.1**; **`sources`** lists chunk-level rows with **`line_start` / `line_end`** and **`score`**; **`context_items_count`**.
- New **[`app/chunking.py`](python/app/chunking.py)**; **`Router.build_context_items`**, **`format_context_items_markdown`**.

## 0.2.2

- **MCP Phase 0 contract**: **`route_skills`** success responses include versioned **`_meta`** (`schema_version` **1.0**, **`sources`**, **`budget`**, **`candidates_preview`**). Empty prompt returns **`isError`** + **`_meta.error`**. Shared builder in **`app.mcp_contract`**; **`skillforge route --json-meta`** matches.
- **Docs**: README “MCP response contract” section.

## 0.2.1

- Same code as **0.2.0**. **npm never allows reusing a version** after it has been published once—even if you **unpublish** it and only **0.1.0** remains visible. The registry still blocks **`0.2.0`**; ship **`0.2.1`** (or higher) instead.

## 0.2.0

- **`skillforge route`**: CLI parity with MCP **`route_skills`** (same `build_router_and_skills` + `run_route_turn` pipeline); optional **`--project-root`**, **`--session-id`**, **`--user-id`**, **`--json-meta`**.
- **`app.db_paths`**: **`global_db_path`** / **`resolve_orchestrator_db`** extracted for lightweight tests and reuse.
- **MCP**: **`MCPServer.setup`** now uses **`build_router_and_skills`** (single router construction path with the CLI).
- **CI**: **`pytest`** over **`python/tests/`** (no full ML install for DB path tests); **`py_compile`** includes **`db_paths.py`** and **`route_cli.py`**.

## 0.1.0

Initial public npm release: MCP stdio server, optional HTTP API, bundled skill catalog, per-project **`.skillforge/orchestrator.db`**, **`skillforge events`**, learning loop.
