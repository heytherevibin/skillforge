# Changelog

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
- **Cursor (global `/skillforge`)** and **Claude Code**: on **`skillforge install`** / first-run setup, Skillforge writes **`~/.cursor/commands/skillforge.md`** and/or **`~/.claude/commands/skillforge.md`** when each environment is detected; **`skillforge hosts init`** updates both without Python setup. Opt out: **`SKILLFORGE_SKIP_CURSOR_SETUP`**, **`SKILLFORGE_SKIP_CLAUDE_CODE_SETUP`**. Force: **`SKILLFORGE_CURSOR_GLOBAL_COMMAND`**, **`SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND`**. **`--force-cursor`** replaces managed files. **Claude Desktop** remains detect-only + MCP merge hint.
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
