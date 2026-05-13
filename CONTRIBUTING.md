# Contributing

Thank you for improving Skillforge.

## Workflow

1. **Fork** the repository and create a branch from **`main`**.
2. Keep changes **focused**; follow patterns in surrounding code.
3. Operator / user-facing doc changes belong in **`docs/`** (`README.md` should stay the short hub + badges). Bump **`package.json`** / **`CHANGELOG.md`** when shipping user-visible doc releases.

4. Run **local checks** before opening a PR from the **package root** (the directory that contains **`package.json`**):

   ```bash
   node --check bin/cli.js && node --check lib/packs.js && node --check lib/user-env-profile.js
   npm test
   ```

   For Python (after **`pip install -r python/requirements.txt -r python/requirements-dev.txt`** from the same directory):

   ```bash
   cd python && PYTHONPATH=. pytest tests/ -q
   ```

   When you add a new **`python/app/*.py`** module, extend the **`py_compile`** list in **`.github/workflows/ci.yml`** (authoritative source) and mirror it in **[RELEASING.md](RELEASING.md)** local checks if you maintain that snippet.

   If you **intentionally** shrink or grow the bundled **`skills/`** tree below/above the current CI minimum, update **`ci/bundle-gate.json`** (`minSkillMdFiles`) and note it in the PR—see **[RELEASING.md](RELEASING.md)**.

5. Open a **pull request** into **`main`** with:
   - What changed and **why**  
   - How you **verified** it (tests, manual MCP smoke, etc.)

PRs should pass **CI** (see [RELEASING.md](RELEASING.md)).

## Branch protection (maintainers)

For a protected **`main`**:

- Require PRs before merge  
- Require **CI** / `verify` to pass  
- Optionally require reviews and disallow force-push  

Configured in **GitHub → Settings → Branches**; not stored in-repo.

## Releases

Maintainers: [RELEASING.md](RELEASING.md) (**semver**, tags, **`NPM_TOKEN`**, npm tokens).

## Conduct & security

- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)  
- [SECURITY.md](SECURITY.md) for vulnerability reporting  
