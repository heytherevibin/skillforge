# MCP integration

Skillforge speaks **stdio MCP JSON-RPC**. Tool definitions (**name**, **`inputSchema`**, descriptions) ship from **`python/app/mcp_server.py`**.

## stdout discipline

Anything that writes stray bytes to **stdout** breaks MCP hosts. **`skillforge mcp`** never logs JSON-RPC payloads to stdout; logs go to **stderr**.

## Default routing (**host**, Skillforge ≥ 0.11.0 — use **≥ 0.11.10** for **`--force-cursor`** / **`--force-claude`** parity; **≥ 0.11.11** adds **`skillforge help --ui`** / **`--browse`**; **≥ 0.11.12** adds **`route_skills` `dry_run`**, **`SKILLFORGE_ROUTE_TRACE_LEVEL`**, **`routing_correlation_id`** in **`_meta`**; **≥ 0.11.13** adds **`skillforge route-eval ingest`** (SQLite **`events`** → regression fixture JSON); **≥ 0.11.14** adds optional **`route_quality.policy_shadow`** and MCP schema **`1.10`** when **`SKILLFORGE_ROUTE_POLICIES_SHADOW*`** is set; **≥ 0.11.15** adds **`SKILLFORGE_WEIGHT_HALF_LIFE_DAYS`**, **`skillforge events prune`**, filtered **`skillforge replay`**, **`SKILLFORGE_ROUTER_LLM_RETRIES`**, and **`idx_events_user_type_ts`**; **≥ 0.11.16** adds **`SKILLFORGE_ROUTE_MEMORY*`**, MCP **`route_memory_*`**, **`route_quality.route_memory`**, schema **`1.11`**; **≥ 0.11.17** persists compact **`route_memory`** in **`route`**/**`host_shortlist`** **events**, optional dedup/decay knobs, **`verify_route_memory_cli`**; **≥ 0.11.18** adds MCP companion preset (**`skillforge mcp config --companion`**), **`capabilities.mcp_companion`**, and materialize/global **`/skillforge`** prompts for **`conversation`** on both host calls

Stable **`Router`** init ships in **[0.11.7](../CHANGELOG.md)**; tooling through **[0.11.10](../CHANGELOG.md)**. Help layout **[0.11.11](../CHANGELOG.md)**; routing observability **[0.11.12](../CHANGELOG.md)**; **`route-eval ingest`** **[0.11.13](../CHANGELOG.md)**; policy shadow **[0.11.14](../CHANGELOG.md)**; ops hardening (weights / retention / **`replay` filters**) **[0.11.15](../CHANGELOG.md)**; governed routing memories **[0.11.16](../CHANGELOG.md)**; event snapshots + longevity tuning **[0.11.17](../CHANGELOG.md)**; companion preset + host prompts **[0.11.18](../CHANGELOG.md)**.

When **`SKILLFORGE_ROUTER_MODE`** is **unset**:

1. First **`route_skills`** call → **numbered shortlist** (no **`picked_names`** yet).
2. Second call → same **`prompt`** plus **`picked_names`** (**`id1,id2`** or enumerated picks returned in the listing).

 **`auto`** (legacy behavior) ⇒ **`SKILLFORGE_ROUTER_MODE=auto`** or empty string (**`=`** alone). **`skillforge mcp config --with-anthropic`** emits **`SKILLFORGE_ROUTER_MODE=auto`** **and** an **`ANTHROPIC_API_KEY`** placeholder together so placeholders are not meaningless under **`host`** default routing.

### Mode reference

| **`SKILLFORGE_ROUTER_MODE`** | Behaviour (high level) |
|------------------------------|------------------------|
| **unset → treats as `host`** | Host-driven two-step routing. |
| **`host`** | Explicit two-step **shortlist → picked_names**. |
| **`auto`** | Embedding-first without key; in-process Haiku when **`ANTHROPIC_API_KEY`** set. |
| **`embedding`** | Embedding-only picks / overrides via **`picked_names`**. |
| **`full`** | Haiku-heavy paths (falls back gracefully if key absent). |

## Where to declare **`env`**

| Host | Typical manifest |
|------|------------------|
| **Cursor / VS Code MCP** | **`~/.cursor/mcp.json`** (workspace overrides possible) |
| **Claude Desktop** | **`claude_desktop_config.json`** |

Restart the MCP host whenever **`env`** or package version changes.

## **`skillforge mcp config`**

```bash
skillforge mcp config
skillforge mcp config --local
skillforge mcp config --with-anthropic    # SKILLFORGE_ROUTER_MODE=auto + key placeholder env
skillforge mcp config --with-env           # SKILLFORGE_ROUTER_MODE=host scaffold in entry.env
skillforge mcp config --companion          # + SKILLFORGE_ROUTER_CONV_MAX_TURNS=6, SKILLFORGE_ROUTER_CONV_MSG_CHARS=400
skillforge mcp config --with-env --companion
skillforge mcp config --with-anthropic --companion   # auto + key + conversation env
```

**Note:** Passing **`--with-anthropic`** **replaces** the emitted **`env`** object (**`--with-env`** loses); **`--companion`** conversation vars are still merged into whichever **`env`** branch applies.

### Companion preset (MCP JSON)

**`--companion`** adds **`SKILLFORGE_ROUTER_CONV_MAX_TURNS=6`** and **`SKILLFORGE_ROUTER_CONV_MSG_CHARS=400`** so **`route_skills`** can fuse **`conversation`** into the embedding query (ignored when turns is **0**). Without transcript payloads from the host, routing stays prompt-only — the agent must pass recent messages as **`{role, content}`** on **both** **`host`**-mode calls, reusing **`session_id`**.

The **`capabilities`** tool returns a **`mcp_companion`** object with a numbered workflow (optional **`capabilities`** bootstrap → shortlist → **`picked_names`** finalize).

## MCP tools (quick map)

Schemas + parameter docs: **`python/app/mcp_server.py`**.

| Tool | Responsibility |
|------|----------------|
| **`route_skills`** | Embed → shortlist → policies → context assembly; honours **`picked_names`**. |
| **`search_skills`** | Embedding shortlist for arbitrary query text. |
| **`explain_route`** | Routing diagnostics (shortlist audit) without heavyweight session effects. |
| **`get_skill`**, **`list_skills`** | Deterministic SKILL.md retrieval + catalog summaries. |
| **`skill_feedback`**, **`skill_referenced`**, **`disable_skill`** | Learning loop inputs. |
| **`materialize_project`** | Opinionated scaffolding for **`cursor`**, **`claude_code`**, or **`both`** with **`hosts`**: **`auto`**, **`both`**, **`cursor`**, **`claude_code`**. |
| **`skillforge_bootstrap`** | Composite route + scaffold helper (mind **`host`** shortlist caveat). |
| **`capabilities`** | Session bootstrap bundle (**semver**, MCP schema marker, **`mcp_tools`**, **`mcp_companion`** workflow, **`user_env_profile`** commands, **`router_snapshot`**). |
| **`get_router_status`** | Diagnostics snapshot (modes, hybrids, rerank hints). |
| **`project_index_status`** | Project **`project_chunks`** stats + index metadata (**`project_root`**). |
| **`weights_snapshot`** | Portable learned weights excerpt (parity with **`weights export`** CLI). |
| **`events_recent`** | Recent SQLite **`events`** rows (**bounded** **`limit`**). |

## Response **`_meta`**

Structured metadata is anchored by **`MCP_RESPONSE_SCHEMA_VERSION`** in **`app/mcp_contract.py`**. Highlights include **`route_quality`**, **`routing_overlay`**, **`feedback_effect`**, budgeting / fusion stats, **`host_pick_*`** artefacts when **`host`** mode emits shortlists.

---

**Related:** **[Environment & configuration](environment-and-configuration.md)** · **[CLI reference](cli-reference.md)**
