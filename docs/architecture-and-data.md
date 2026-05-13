# Architecture & data

Skillforge stitches three layers:

1. **Node bootstrap** (**`bin/cli.js`**) — ensures **`~/.skillforge`**, wires env, forks Python.
2. **Python orchestration** (**`python/app/main.py`** + satellite modules) — embeddings, **`Router`**, policies, MCP surfaces.
3. **Filesystem catalog** (**`skills/`**) — bundled SKILL.md corpus + **`~/.skillforge/skills/`** overlays + optional **`pack`** trees.

ASCII overview:

```
MCP IDE host ──stdin/stdout JSON-RPC──► skillforge mcp ──► app.mcp_server
                                              │
CLI / systemd / CI ──► bin/cli.js ───────────────────────► app.*_cli (+ shared Router)
                                              │
SQLite stores per global (~/.skillforge/data) vs project (.skillforge) roots
sentence-transformers (default MiniLM family) ─ skill card embeddings ─► shortlists
Optional Anthropic Async client when router modes demand Haiku rerank/final picks
Standalone OpenAIRouterLLM when transport ≠ MCP AND SKILLFORGE_ROUTER_LLM_BACKEND=openai_compatible
```

### Routing stages (mental model)

```
prompt (+ optional fused conversation overlays)
→ encode embedding query (skills + hybrid sparse boosts)
→ merge learned weights / overlay boosts / exclusions (project policies)
→ top-K candidates
→ optional LLM rerank + final picks (embedding-only / Haiku / host pick / openai_compatible)
→ chunk context + optional fusion w/ project_chunks
→ markdown payload + MCP _meta auditing
→ SQLite telemetry (sessions, events, weights, optional project_chunks)
```

**Re-route guard:** **`SKILLFORGE_REROUTE_THRESHOLD`** hysteresis when picks swing hard.

### Policy + overlay ingestion

 **`load_route_policies_config`** merges:

1. **`SKILLFORGE_ROUTE_POLICIES`** (**inline JSON**) — malformed JSON ⇒ stderr warning · empty rules fallback.
2. **`SKILLFORGE_ROUTE_POLICIES_FILE`** path.
3. **`<project>/.skillforge/policies.json`**
4. **`<project>/skillforge-policies.json`**

Policy JSON optionally embeds **`rules`**, **`exclude_skills`** / boosts / **`project_notes`**. Overlay notes deliberately **never** activate without **`project_root`**.

### Data directories

#### Global (**`~/.skillforge`**)

```
~/.skillforge/
├── env                # Optional dotenv-style operator profile (config commands)
├── venv/              # Managed Python toolchain
├── data/orchestrator.db
├── skills/            # Operator-authored skills
├── packs/             # Expanded pack artefacts
├── .setup-complete    # Marker after install completes
└── ...
```

#### Per project (**`<repo>/.skillforge`** once routing/indexing attaches **`project_root`**)

```
<repo>/.skillforge/
├── orchestrator.db             # SQLite (sessions/events/weights/chunks overlay)
├── policies.json               # Optional overlays (alternate: repo-root manifest)
├── last_route.json             # Debugging snapshot from CLI routing
└── ...
```

### Learning + portability

- **`skill_weights`** table mutated by MCP **`route_skills`**, **`skill_feedback`**, etc.
- Export/import symmetry via **`skillforge weights export|import`** (JSON payloads align with MCP **`weights_snapshot`**).

### Project RAG ingestion

Steps:

```bash
skillforge index --project-root=/absolute/path/to/repo
```

Then MCP / CLI **`include_project_rag`** toggles fused retrieval guarded by **`project_index.py`** (embedding dimension mismatches skipped defensively).

### Bundled skills gate

**`ci/bundle-gate.json`** field **`minSkillMdFiles`** is the CI-enforced minimum **`skills/**/**/SKILL.md`** count (see `.github/workflows/ci.yml` → **Verify skills bundle**).
