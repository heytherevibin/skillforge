# Skillforge — product strategy

## Mission

Skillforge is a **local, MCP-first orchestration layer** that selects a **small, relevant** subset of **`SKILL.md`** (and optional indexed project) context for each user task—so agent hosts can stay **grounded** without loading entire catalogs.

## Principles

| Principle | Implication |
|-----------|-------------|
| **Local-first** | Default data plane is **SQLite** and **stdio MCP** on the operator’s machine. |
| **Explicit trust** | Optional **LLM** stages run only when keys and modes allow; **host** mode delegates final skill choice to the MCP client. |
| **Observable** | Versioned **`_meta`**, route **events**, and operator CLIs (**`events`**, **`health`**, **`route-eval`**) support enterprise debugging and CI gates. |
| **Portable learning** | Weights and feedback are **exportable**—suitable for backup, migration, and controlled restore. |
| **Governable** | **Regex policies** and **project overlays** (exclude, boost, notes) let platform teams steer routing without forking the catalog. |

## Primary surfaces

| Surface | Role |
|---------|------|
| **MCP (`skillforge mcp`)** | Integration for Claude, Cursor, Claude Code, and other JSON-RPC MCP hosts. |
| **CLI** | Parity routing, indexing, observability, preflight, eval harness, weights I/O. |

## Integration matrix

| Host capability | Skillforge pattern |
|-----------------|---------------------|
| **Project workspace** | Pass **`project_root`** so state and optional RAG live under **`.skillforge/`**. |
| **Strict context budgets** | Tune **`SKILLFORGE_CONTEXT_*`**, **`SKILLFORGE_ROUTE_MAX_CHARS`**, and project RAG caps. |
| **No LLM keys on router** | Use **`SKILLFORGE_ROUTER_MODE=embedding`** (or omit **`ANTHROPIC_API_KEY`** in auto mode). |
| **Human-in-the-loop picks** | **`SKILLFORGE_ROUTER_MODE=host`**: shortlist first, then **`picked_names`**. |
| **Org policy** | Central **`SKILLFORGE_ROUTE_POLICIES`** / file + per-repo **`policies.json`** with overlay keys. |

## Near-term themes

- Continue tightening **parity** between MCP tools and CLI (**routing**, **meta**, **policies**).
- Expand **fixture library** for **`route-eval`** as catalog and hybrid modes evolve.
- Optional: richer **enterprise** packaging (e.g. signed SBOM, pinned base images) as downstream consumers require—tracked outside this doc when scope is agreed.

## Non-goals

- Replacing the host model or owning end-user billing for conversations.
- Implicit network egress except **optional** model APIs (Anthropic) and **pack** git clones invoked explicitly by operators.
- A hosted multi-tenant SaaS as part of the core OSS package.

## References

- **Operator documentation:** [README.md](README.md)  
- **Security posture:** [SECURITY.md](SECURITY.md)  
- **Shipping checklist:** [RELEASING.md](RELEASING.md)
