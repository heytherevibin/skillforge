# Getting started

## 1. What you are installing

Skillforge ships as **[@heytherevibin/skillforge](https://www.npmjs.com/package/@heytherevibin/skillforge)**. The **CLI** (`skillforge`) is a **Node.js** shim that installs a **managed Python virtualenv** under **`~/.skillforge/venv`** and runs **`python -m app.…`** with a consistent environment (`PYTHONPATH`, skill dirs, DB path). You do **not** need to activate the venv by hand.

**Documentation matches this checkout's release line:** **0.11.18** (**[`package.json` `version`](../package.json)**). On npm, **`npm view @heytherevibin/skillforge version`** is the registry truth—use **`@latest`** or **`npx -y`** to stay current.

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Node.js ≥ 18** | Required to run **`npx`** / **`skillforge`**. |
| **Python ≥ 3.10** | Used on first **`skillforge install`** to create **`~/.skillforge/venv`**. |
| **Internet (first install)** | `pip install` from **`python/requirements.txt`**; embedding model download may occur once. |

## 3. Try without installing globally

Run:

```bash
npx --yes @heytherevibin/skillforge --help
```

First use may invoke **`skillforge install`** implicitly when you hit a Python-backed command (`route`, `mcp`, …). Use **`skillforge install`** explicitly if you prefer a deliberate bootstrap.

## 4. Global install (optional)

```bash
npm install -g @heytherevibin/skillforge
skillforge --help
```

Verify:

```bash
skillforge config validate   # exits 0 if ~/.skillforge/env is missing (optional file)
skillforge health --quick
```

## 5. Optional operator profile (~/.skillforge/env)

Recommended for stable API keys and tunables:

```bash
skillforge config init       # ~/.skillforge/env template (chmod 600 on Unix where supported)
skillforge config validate   # lint after edits
```

See **[Environment & configuration](environment-and-configuration.md)** for merge order versus MCP **`entry.env`**.

## 6. Wire MCP (Cursor, Claude Desktop, …)

Emit a snippet (stdout is JSON):

```bash
skillforge mcp config
skillforge mcp config --companion   # optional: fuse route_skills `conversation` into embeddings (preset env)
```

**`skillforge mcp config`** only prints JSON and does **not** provision the Python venv (**0.11.8**+); run **`skillforge install`** before **`skillforge mcp`**.

1. Copy the **`mcpServers.skillforge`** object into your host config (example: **`~/.cursor/mcp.json`**).
2. **Fully restart** the MCP host application after edits.
3. Confirm tools appear — start a session with **`capabilities`** once (bundle lists tool names + **router_snapshot**).

**Critical:** MCP uses **stdout** only for JSON-RPC. Skillforge logs to **stderr**.

## 7. Understand default routing (**host**, two-step)

If **`SKILLFORGE_ROUTER_MODE`** is unset, Skillforge defaults to **`host`**:

1. First **`route_skills`** → numbered **shortlist** (no **`picked_names`**).
2. Second call → same **`prompt`** plus **`picked_names`** (`id1,id2` or enumerated picks from the listing).

For transcript-aware shortlists, configure **`skillforge mcp config --companion`** and pass **`route_skills`** **`conversation`** (same on both host calls). CLI mirrors this: **`skillforge route`** twice, or **`skillforge route -i`** on a TTY after the shortlist. Details: **[MCP integration](mcp-integration.md#companion-preset-mcp-json)**.

## 8. Operational habits

```bash
skillforge tips                           # cheatsheet on stdout
skillforge events --watch                 # routing / feedback tail
skillforge replay --limit=20 [--json]
```

Further reading: **[CLI reference](cli-reference.md)** · **[Architecture & data](architecture-and-data.md)**.
