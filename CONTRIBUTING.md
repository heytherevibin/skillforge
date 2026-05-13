# Contributing

Thanks for helping improve skillforge.

## How to contribute

1. **Fork** the repository and create a branch from `main`.
2. Make focused changes; match existing style in the touched files.
3. Run local checks before pushing:
   ```bash
   node --check bin/cli.js && node --check lib/packs.js
   npm test
   ```
4. Open a **pull request** into `main` with a clear description of the change and why.

Pull requests should pass the **CI** workflow (see [RELEASING.md](RELEASING.md)).

## Branch protection (maintainers)

For an “enterprise-style” mainline, enable in GitHub: **Settings → Branches → Add rule** for `main`:

- Require a pull request before merging
- Require status checks to pass before merging (add **CI** / `verify`)
- Optionally: require reviews, disallow force pushes

This is configured in the GitHub UI; it is not stored in this repo.

## Releases

Maintainers: follow [RELEASING.md](RELEASING.md) for version bumps, tags, **`NPM_TOKEN`**, and npm **2FA**.

## Code of conduct

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report problems to the maintainers.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.
