# Releasing skillforge

## CI vs Release workflows

| Workflow | File | When it runs |
|----------|------|----------------|
| **CI** | [.github/workflows/ci.yml](.github/workflows/ci.yml) | Every **push** and **pull request** to `main`; also **`workflow_dispatch`** (run manually from the Actions tab) |
| **Release** | [.github/workflows/release.yml](.github/workflows/release.yml) | When a **`v*`** tag is **pushed** to the repository (e.g. `v0.2.2`) |

In the GitHub UI, open **Actions** and look for **CI** and **Release** (not the older “publish to npm” name).

## Verify Actions without cutting a release

1. Push any commit to `main`, or open a PR targeting `main`, and confirm the **CI** workflow turns green.
2. Or go to **Actions → CI → Run workflow** (requires `workflow_dispatch` on `main`) and run against `main`.

## Publish to npm and attach a GitHub Release (happy path)

You need the **`NPM_TOKEN`** repository secret.

**npm (2025+):** Legacy “classic” tokens (including the old **Automation** type) are **gone**. Use a [**granular access token**](https://docs.npmjs.com/about-access-tokens) with **read and write** permission for **`@heytherevibin`** / `@heytherevibin/skillforge`, and enable **Bypass 2FA** on that token. Without **Bypass 2FA**, `npm publish` in GitHub Actions often fails with **`EOTP`** because CI cannot enter an authenticator code.

Create one at [npm → Access Tokens](https://www.npmjs.com/settings/~/tokens) (**Generate New Token** → **Granular Access Token**). Optionally explore [**trusted publishing** (OIDC)](https://docs.npmjs.com/trusted-publishers/) later to avoid long-lived tokens.

1. On `main`, set **`version`** in `package.json` to the version you are releasing (e.g. `0.2.2`).
2. Commit and **`git push origin main`**. Wait for **CI** to pass.
3. Create a tag whose name is **`v` + that exact version**:  
   `git tag v0.2.2 && git push origin v0.2.2`
4. Open **Actions → Release**. The job will **fail the version check** if `v0.2.2` does not match `package.json` `0.2.2`.
5. Confirm on npm: `npm view @heytherevibin/skillforge version`  
   Confirm the **GitHub Release** includes the `.tgz` asset.

Scoped packages require a **public** publish; the workflow already runs `npm publish --access public`.

## Recover if a tag exists but npm was never updated

Typical causes: the tag was created before **Release** existed on `main`, the tag was only created in the GitHub UI without a matching workflow run, or **`package.json` did not match the tag**.

**Option A — reuse the same version (re-trigger Release)**

1. Ensure `.github/workflows/release.yml` on `main` is the current one and **`package.json` `version`** matches the tag (without `v`).
2. Delete the tag locally and on the remote, then push it again so GitHub emits a new `push` event for that tag:  
   ```bash
   git tag -d v0.2.1
   git push origin :refs/tags/v0.2.1
   git tag v0.2.1
   git push origin v0.2.1
   ```

**Option B — new version (cleanest)**

1. Bump `version` in `package.json`, commit, push `main`.
2. Push a **new** tag: `v` + new version.

## Local sanity checks (before push)

```bash
node --check bin/cli.js && node --check lib/packs.js
npm test
```

Python (syntax only):

```bash
for f in python/app/main.py python/app/cli.py python/app/mcp_server.py python/app/auth.py; do python3 -m py_compile "$f"; done
```

## Troubleshooting: `EOTP` / one-time password in CI

**Symptom:** `npm error code EOTP` / “This operation requires a one-time password from your authenticator.”

**Cause:** The granular token in **`NPM_TOKEN`** does not have **Bypass 2FA** enabled (default is off), or it lacks write access to the package.

**Fix:**

1. On [npm → Access Tokens](https://www.npmjs.com/settings/~/tokens), create a **Granular Access Token** (or edit policy if npm allows): **Read and write**, scope **`@heytherevibin`**, **Bypass 2FA: on**.
2. Update **`NPM_TOKEN`** in GitHub → **Settings → Secrets and variables → Actions**.
3. Re-run the failed **Release** workflow, or delete and re-push the release tag (see “Recover if a tag exists…” above).
