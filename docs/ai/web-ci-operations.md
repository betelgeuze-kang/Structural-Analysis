# Web CI operations

How to actually operate the two CI lanes and finish the priority-1 cleanup.
Items marked **(repo admin)** are GitHub settings that must be done in the web
UI / API — they cannot be done from a code PR.

## Two lanes

| Lane | Workflow | Runner | Scope |
| --- | --- | --- | --- |
| Frontend / web | `.github/workflows/frontend-web-ci.yml` | `ubuntu-24.04` | every PR and merge group; stable `frontend-required` result |
| Heavy / solver | `.github/workflows/nightly-heavy-solver.yml` | policy-controlled self-hosted / GPU | large benchmarks, GPU/HIP, full validation |

## 1. Frontend runner and toolchain policy

Frontend Web CI is fixed to GitHub-hosted `ubuntu-24.04`, Node `24.20.0`, and
npm `11.19.0`. It downloads the official Linux x64 tarball directly from
nodejs.org, matches the archive against the official `SHASUMS256.txt` entry,
and checks the pinned Node and npm CLI byte hashes before any repository code
runs. Do not replace the runner with `ubuntu-latest` or an unreviewed
self-hosted label. The workflow rejects alternate package-manager and
`.npmrc` surfaces, then performs this fail-closed sequence:

1. Copy only `package.json` and `package-lock.json` into an isolated directory.
2. Run sanitized `npm ci --ignore-scripts --engine-strict
   --registry=https://registry.npmjs.org/` with user/global config set to
   `/dev/null` and proxy/cafile overrides removed.
3. Run zero-vulnerability `npm audit`, then `npm audit signatures`.
4. Install the repository copy with the same sanitized policy.
5. Invoke the installed TypeScript, Vite, and Playwright JavaScript entry
   files with the verified absolute Node binary. Repository `.mjs` contracts
   use the same `env -i` allowlist. No authoritative step resolves `node`,
   `npm`, `npx`, or a `node_modules/.bin` shim through `PATH`.

This policy is a dependency integrity gate, not license, SBOM, signing, or
release authority.

## 2. Make Frontend Web CI a required check (repo admin)

1. Repo → **Settings → Branches → Branch protection rules** for `main`.
2. Enable **Require status checks to pass before merging**.
3. After this code lands, add the stable **`frontend-required`** job from
   `Frontend Web CI` as required and retain the resulting settings receipt.
4. Do **not** add the heavy solver job as required for frontend-only changes,
   so a queued/cancelled self-hosted run never blocks a frontend merge.

## 3. Repository cleanup (repo admin)

- **Close PR #2** (superseded by the safe prototype / workbench-v2 line).
- **Delete merged stacked feature branches** once `main` has everything:
  - `feat/frontend-web-ci`, `feat/workbench-prototype-safe`,
    `feat/workbench-v2-react`, `feat/workbench-v2-evidence-reader`,
    `feat/workbench-v2-benchmark-browser`, `feat/web-track-integration-to-main`
  - (the older evidence-console stack `#3`–`#8` branches, if those PRs are closed)
- Keep `main` as the single integration branch; open future work as fresh
  branches off `main` (avoid long stacks targeting feature branches, which
  caused the earlier "only #9 reached main" issue).

## 4. Manual local diagnosis

For local diagnosis, verify the same official Node archive and pinned hashes,
then use absolute real paths for Node and `npm-cli.js`. Do not use a PATH-found
`node`, `npm`, or `npx`. The smoke script applies the same clean-copy install,
audit, signature, manifest, config, and environment isolation checks. See the
[frontend review checklist](checklists/frontend-web-pr-review.md).

```bash
trusted_node=/absolute/verified/node-v24.20.0-linux-x64/bin/node
/usr/bin/env -i PATH=/usr/bin:/bin HOME=/tmp/frontend-home \
  TMPDIR=/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  "$trusted_node" scripts/verify-frontend-smoke.mjs
```

The `package.json` scripts remain developer conveniences. Their success alone
is not dependency-audit, CI, evidence, signing, SBOM, licence, or release
authority; authoritative verification uses the sanitized absolute commands
above and in `frontend-web-ci.yml`.
