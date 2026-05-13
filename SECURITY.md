# Security policy

## Supported versions

Security fixes are applied to the **latest published release** on the default branch (**`main`**). Older release lines may not receive backports; upgrade to the current release when advisories apply.

## Reporting a vulnerability

Please **do not** open a **public** GitHub issue for undisclosed security vulnerabilities.

**Preferred:** use [GitHub Security Advisories](https://github.com/heytherevibin/skillforge/security/advisories/new) for this repository (if you have access).

**Alternative:** **Security → Report a vulnerability** on the repository, or contact maintainers through channels published on their GitHub profiles.

Include:

- Description of the issue and assessed impact  
- Steps to reproduce (if known)  
- Affected **version**, **tag**, or **commit** (if known)  

We aim to **acknowledge** valid reports within a few **business days**. Resolution timelines depend on severity and validation effort.

---

## Threat model (summary)

| Component | Exposure |
|-----------|-----------|
| **MCP stdio server** | Runs locally; accepts JSON-RPC from the parent **MCP host** process. Treat the host as part of your trust boundary. |
| **CLI** | Spawns Python modules with environment inherited from the shell; avoid untrusted **`PATH`** or wrapper scripts. |
| **SQLite databases** | Contain prompts (redacted where configured), events, embeddings metadata, and learning weights. Protect filesystem permissions and backups. |
| **Optional Anthropic API** | Outbound HTTPS when **`ANTHROPIC_API_KEY`** is set; prompts and router context may leave the machine per Anthropic’s policies. |

Skillforge does **not** implement network listening for the published OSS package (no HTTP API in current releases).

---

## Data handling & privacy

- **Redaction** (`SKILLFORGE_REDACT_*`) is **pattern-based** and **best-effort**—not a substitute for data-classification or DLP controls.  
- **Project routing notes** (`project_notes` / aliases in policies) are **prefixed** to the internal routing query only when **`project_root`** is set—reducing accidental global application from org-wide env JSON.  
- Operators should assume **route events** and **`_meta`** may contain **sensitive path fragments** unless redaction is enabled and effective for their workload.

---

## Secrets & configuration

- **Never commit** `ANTHROPIC_API_KEY`, npm **`NPM_TOKEN`**, or workspace tokens.  
- Prefer **OS secret stores**, **CI secrets**, or MCP host **env injection**.  
- Review **`policies.json`** and **`SKILLFORGE_ROUTE_POLICIES`** for **prompt injection** risk: notes influence embeddings for the declared project only, but can still steer retrieval.

---

## Supply chain & distribution

### npm

- Use **granular access tokens** with the minimum scope required; enable **Bypass 2FA** only on dedicated automation tokens when CI publishing requires it (see [RELEASING.md](RELEASING.md)).  
- Keep **2FA** enabled on maintainer accounts that own the **`@heytherevibin`** scope.  
- Review **Dependabot** / dependency updates before merge for typosquatting and breaking changes.

### CI

- Workflows run with **`contents: read`** on the default **CI** job; verify **`release.yml`** permissions when extending publish steps.  
- Prefer **pinned** major versions of third-party Actions or follow your org’s pinning policy.

---

## Runtime hardening (recommended)

- Run Skillforge on **managed workstations** or **locked-down CI agents** appropriate to your data classification.  
- Separate **production** and **development** orchestrator databases if weights or events must not mix.  
- Periodically run **`skillforge health`** and **`skillforge route-eval`** after upgrades to validate embeddings and bundled catalog integrity in your environment.

---

## Coordinated disclosure

If you are preparing **public** research or a conference talk that names Skillforge, please contact maintainers **before** the embargo date so fixes or guidance can ship alongside disclosures when appropriate.
