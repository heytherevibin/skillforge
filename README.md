# skillforge

Adaptive skill orchestrator for Claude. Plug-and-play routing layer that picks the right skills for each prompt, learns from usage, and re-routes mid-conversation.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npx -y @heytherevibin/skillforge
```

**Install globally (optional):** `npm install -g @heytherevibin/skillforge` — then run `skillforge` as below.

That's it. First run sets up a Python environment automatically (~2 min), then it's instant. Comes with 223 pre-built skills covering coding, security, research, AI engineering, content, frontend, backend, and a dozen specialized domains.

## What you get

- **Smart routing**: every prompt is matched against the skill catalog using local embeddings, then a fast Haiku call picks the final 3-7 most relevant skills. Only those get injected into the system prompt.
- **Mid-conversation re-routing**: when the topic shifts, the active skill set shifts with it.
- **Learning loop**: tracks which skills got referenced or thumbs'd. Weights bias future routing decisions per user.
- **Live dashboard**: watch routing decisions stream in, inspect learned weights, disable noisy skills.
- **Bring your own skills**: drop any `SKILL.md` folder, or install entire packs from GitHub.
- **MCP server mode**: use skillforge from Claude Desktop, Claude Code, or any other MCP-aware client — no HTTP server needed.
- **Multi-user mode**: bearer-token auth with per-user learned weights and isolated sessions.

## Run modes

```bash
skillforge                       # HTTP server + open dashboard
skillforge start [--port=8000]   # HTTP server only
skillforge chat                  # interactive chat in this terminal
skillforge mcp                   # MCP stdio server (for Claude Desktop, etc.)
```

### Using as an MCP server (Claude Desktop, Claude Code, and other MCP hosts)

Add this to your MCP config (e.g. `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "skillforge": {
      "command": "npx",
      "args": ["-y", "@heytherevibin/skillforge", "mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Restart your MCP client. Skillforge now exposes four tools:
- `route_skills(prompt)` — returns the SKILL.md bodies of the most relevant skills as text
- `list_skills()` — browse the catalog
- `skill_feedback(name, +1|-1)` — feed the learning loop
- `disable_skill(name, true|false)` — mute noisy skills

The client will call `route_skills` whenever the user's prompt could benefit from a specialized workflow, and inject the returned content into its own context.

### Multi-user mode

```bash
skillforge auth add alice
# → token: sf_xxxxxxxxxxxxxxxxxxxxxxxx

skillforge auth add bob
skillforge auth list
skillforge auth remove alice    # revoke
```

When any tokens exist, the HTTP server requires `Authorization: Bearer <token>`. Each user gets isolated:
- session state
- learned skill weights
- thumbs feedback
- event log

Switch back to single-user by removing all tokens. The same `~/.skillforge/data/orchestrator.db` holds everyone — there's no separate per-user database, just a `user_id` column that defaults to `''` for single-user.

## Skills

### Bundled
223 skills ship with the package. Browse:
```bash
skillforge skills list
```

### Adding your own
Each skill is a folder with a `SKILL.md` file:
```markdown
---
name: my-skill
description: One or two sentences. Be specific about trigger conditions — the router uses this to decide when to load your skill.
---
# My Skill
Instructions Claude follows when this skill is active.
```

Then:
```bash
skillforge skills add ./my-skill
```

Or drop the folder into `~/.skillforge/skills/` directly.

### Installing skill packs from git
A "pack" is any git repo with a `skillforge.json` manifest at the root:
```json
{
  "name": "my-team-skills",
  "version": "1.0.0",
  "skills": ["skill-one", "skill-two", "skill-three"]
}
```

Where each listed name is a folder in the same repo containing a `SKILL.md`. Install with:
```bash
skillforge pack install <user/repo>          # GitHub shorthand
skillforge pack install https://...          # full URL
skillforge pack install ./local-path         # local path
skillforge pack list
skillforge pack update <name>                # git pull + relink
skillforge pack remove <name>
```

Packs are cloned to `~/.skillforge/packs/<hash>/` and their skill folders are symlinked into `~/.skillforge/skills/`. Updates are a single `git pull`.

## How routing actually works

```
your prompt
    │
    ▼
local embeddings (sentence-transformers, ~5ms, free)
    │
    ▼
cosine similarity vs all skill descriptions + per-user learned weights
    │
    ▼
top 15 candidates ─────► Haiku router (~300ms, fractions of a cent)
                                │
                                ▼
                       final 3-7 skills picked
                                │
                                ▼
            SKILL.md bodies injected into system prompt
                                │
                                ▼
                          Opus answers
                                │
                                ▼
             detect which skills got referenced
                                │
                                ▼
               update learned weights for next time
```

Every routing decision is broadcast to the dashboard over WebSocket — you see candidates considered, skills picked, router's reasoning, and reroute flags.

## Commands reference

```
Run modes:
  skillforge                       Start HTTP server + open dashboard
  skillforge start [--port=8000]   Start HTTP server only
  skillforge chat                  Interactive chat in this terminal
  skillforge mcp                   Run as an MCP stdio server

Skills:
  skillforge skills list           List bundled and user skills
  skillforge skills add <path>     Add a local skill folder
  skillforge skills remove <name>  Remove a user-added skill

Skill packs (install from git):
  skillforge pack install <repo>   Install pack from "user/repo" or git URL
  skillforge pack list             List installed packs
  skillforge pack update <name>    Update a pack (git pull + relink)
  skillforge pack remove <name>    Uninstall a pack

Auth (multi-user mode):
  skillforge auth add <user>       Create a bearer token for a user
  skillforge auth list             List users with tokens
  skillforge auth remove <user>    Revoke all tokens for a user

Maintenance:
  skillforge reset                 Wipe learned state and event log
  skillforge install               Re-run setup
  skillforge --help                This message
```

## Requirements

- **Node.js 18+** (GitHub **CI** currently runs on **Node 22**)
- **Python 3.10+** on PATH (for the embedding model and orchestration backend)
- **Anthropic API key** in `ANTHROPIC_API_KEY`

## HTTP API

| Endpoint | What it does |
|---|---|
| `POST /chat` | Main entry. Routes skills, streams Claude response (SSE). |
| `POST /feedback` | Thumbs up/down a skill for the learning loop. |
| `POST /skills/disable` | Toggle a skill's disabled flag. |
| `GET /skills` | List all skills with usage stats and learned weights. |
| `GET /events?limit=50` | Recent routing decisions. |
| `WS /ws` | Live event stream for the dashboard. |
| `GET /` | The dashboard. |
| `GET /healthz` | Skill count + liveness. |

All endpoints except `/`, `/healthz`, and `/ws` require `Authorization: Bearer <token>` when auth is configured.

## Config (env vars)

| Var | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `SKILLFORGE_PORT` | `8000` | Server port |
| `SKILLFORGE_EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer for embeddings |
| `SKILLFORGE_ROUTER_MODEL` | `claude-haiku-4-5-20251001` | Fast model for final selection |
| `SKILLFORGE_ANSWER_MODEL` | `claude-opus-4-7` | Main response model |
| `SKILLFORGE_TOP_K` | `15` | Embedding shortlist size |
| `SKILLFORGE_MAX_ACTIVE` | `7` | Max skills loaded per turn |
| `SKILLFORGE_REROUTE_THRESHOLD` | `0.4` | Jaccard distance triggering re-route |
| `SKILLFORGE_AUTH_TOKENS` | `` | Auto-set by `auth add` command |

## File layout

```
~/.skillforge/
├── venv/                       Python virtual environment
├── data/orchestrator.db        SQLite: telemetry, weights, sessions (per-user namespaced)
├── skills/                     User skill folders (drop here, or use `skills add`)
├── packs/<hash>/               Installed pack git clones
├── packs.json                  Pack registry
└── auth.json                   Bearer token map (mode 0600)
```

`skillforge reset` wipes the database. `rm -rf ~/.skillforge` nukes everything including the venv.

## Maintainers: CI, releases, and npm

Published package: **`@heytherevibin/skillforge`** (scoped; install with `npx -y @heytherevibin/skillforge`).

- **CI** workflow runs on push/PR to `main` (and can be run manually under **Actions → CI → Run workflow**).
- **Skillforge release** workflow runs when you push a tag matching **`v*`** (e.g. `v0.1.0`). The tag **minus the `v` prefix** must exactly match the **`version` field in `package.json`**, or the job will fail. Published GitHub releases use the title **`Skillforge <tag>`** (e.g. **`Skillforge v0.1.0`**).
- Setup for **`NPM_TOKEN`**, recovering from stale tags, and local checks: [RELEASING.md](RELEASING.md).
- Contributing and branch-protection expectations: [CONTRIBUTING.md](CONTRIBUTING.md). Security contact: [SECURITY.md](SECURITY.md).

## License

MIT
