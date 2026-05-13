# Security policy

## Supported versions

Security fixes are applied to the **latest** published minor release on the `main` branch. Older tags may not receive backports; upgrade to the current release when possible.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for undisclosed security vulnerabilities.

**Preferred:** use [GitHub Security Advisories](https://github.com/heytherevibin/skillforge/security/advisories/new) for this repository (if you have access).

**Alternative:** open a **private** report via GitHub **Security → Report a vulnerability** on the repository, or contact the maintainer through a channel they publish on their GitHub profile.

Include:

- Description of the issue and impact
- Steps to reproduce (if known)
- Affected version or commit (if known)

We aim to acknowledge valid reports within a few business days.

## npm and supply chain

- For **`NPM_TOKEN`** in GitHub Actions, use a [**granular access token**](https://docs.npmjs.com/about-access-tokens) with **read and write** to your scope and **Bypass 2FA** enabled, so **`npm publish`** does not return **`EOTP`**. Legacy automation/classic tokens are no longer available on npm as of 2025.
- Keep **2FA** enabled on the npm account that owns the `@heytherevibin` scope.
- Prefer pinning action versions or reviewing Dependabot PRs before merge.

## Runtime hardening

If you expose the HTTP server beyond **localhost**, treat it as internet-facing: use **bearer-token auth** (`skillforge auth …`), terminate TLS at a reverse proxy, and restrict network access appropriately. The default single-user setup assumes a trusted local environment.
