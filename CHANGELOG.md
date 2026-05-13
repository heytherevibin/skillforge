# Changelog

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
