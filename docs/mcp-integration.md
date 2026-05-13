# MCP integration

Skillforge speaks **stdio MCP JSON-RPC**. Tool definitions (**name**, **`inputSchema`**, descriptions) ship from **`python/app/mcp_server.py`**.

## stdout discipline

Anything that writes stray bytes to **stdout** breaks MCP hosts. **`skillforge mcp`** never logs JSON-RPC payloads to stdout; logs go to **stderr**.

## Default routing (**host**, Skillforge ≥ 0.11.0 — use **≥ 0.11.7** if you rely on **`route-eval`** / full router init stability)

Stable **`Router`** embedding + **`_by_name`** initialization ship in **[0.11.7](../CHANGELOG.md)**; stay on **`0.11.7`** or newer for CI-aligned routing.

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
```

**Note:** Passing **`--with-anthropic`** **replaces** the emitted **`env`** object (**`--with-env`** loses); merge manually if you need both patterns.

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
| **`capabilities`** | Session bootstrap bundle (**semver**, MCP schema marker, **`mcp_tools`**, **`user_env_profile`** commands, **`router_snapshot`**). |
| **`get_router_status`** | Diagnostics snapshot (modes, hybrids, rerank hints). |
| **`project_index_status`** | Project **`project_chunks`** stats + index metadata (**`project_root`**). |
| **`weights_snapshot`** | Portable learned weights excerpt (parity with **`weights export`** CLI). |
| **`events_recent`** | Recent SQLite **`events`** rows (**bounded** **`limit`**). |

## Response **`_meta`**

Structured metadata is anchored by **`MCP_RESPONSE_SCHEMA_VERSION`** in **`app/mcp_contract.py`**. Highlights include **`route_quality`**, **`routing_overlay`**, **`feedback_effect`**, budgeting / fusion stats, **`host_pick_*`** artefacts when **`host`** mode emits shortlists.

---

**Related:** **[Environment & configuration](environment-and-configuration.md)** · **[CLI reference](cli-reference.md)**
