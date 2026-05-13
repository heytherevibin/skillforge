# Troubleshooting

## MCP tools never appear / connection dies immediately

**Check:**

1. **Restart** Cursor / Claude / VS Code after editing **`mcp.json`** (**hot reload seldom enough**).
2. Confirm **nothing else** wraps stdout (debug prints, rogue **`console.log`** forks); **`skillforge mcp`** forbids chatter on stdout.
3. Bump package version (**`npm view @heytherevibin/skillforge version`** vs local git tag) — mismatched semver often means stale binary.
4. Run **`skillforge health --quick`** locally to prove venv + skill tree viability.

## **`skillforge agent` Missing `openai`**

Upgrade managed deps:

```bash
skillforge install
```

(or manually **`pip install -r`** against **`~/.skillforge/venv`**).

Validate env profile too:

```bash
skillforge config validate
```

## Route policies silently empty

Malformed **`SKILLFORGE_ROUTE_POLICIES`** JSON or unreadable **`SKILLFORGE_ROUTE_POLICIES_FILE`** now prints **`[skillforge] …`** on **stderr** and falls back to **no regex rules**.

**Instruction:** **`skillforge explain_route`** / inspect logs · fix JSON · re-run.

## NPM publish / **`EOTP`** in GitHub Actions

Release workflow requires a **Granular NPM token with Bypass 2FA** — see **[RELEASING.md](../RELEASING.md)**.

Re-run **`Skillforge release`** after rotating **`NPM_TOKEN`**.

## Tag mismatches (**`release.yml`** guard)

 **`vX.Y.Z` tag must equal `package.json`** **`version`**. Bump semver, push **`main`**, then re-tag (**`git tag -d`** / **`git push :refs/tags/...`** if you need to re-cut).

---

Need more?

- Diagnostics bundle: MCP **`capabilities`**, **`get_router_status`**.
- Security expectations: **[SECURITY.md](../SECURITY.md)**.
- Broader changelog context: **[CHANGELOG.md](../CHANGELOG.md)**.
