# Web CI operations

How to actually operate the two CI lanes and finish the priority-1 cleanup.
Items marked **(repo admin)** are GitHub settings that must be done in the web
UI / API — they cannot be done from a code PR.

## Two lanes

| Lane | Workflow | Runner | Scope |
| --- | --- | --- | --- |
| Frontend / web | `.github/workflows/frontend-web-ci.yml` | `ubuntu-24.04` | `prototype/**`, `src/**`, `tests/frontend/**`, dependency manifests/config surfaces |
| Heavy / solver | `.github/workflows/nightly-heavy-solver.yml` | policy-controlled self-hosted / GPU | large benchmarks, GPU/HIP, full validation |

## 1. Frontend runner and toolchain policy

Frontend Web CI is fixed to GitHub-hosted `ubuntu-24.04`, Node `24.20.0`, and
npm `11.19.0`. Do not replace the runner with `ubuntu-latest` or an unreviewed
self-hosted label. The workflow first rejects alternate package-manager and
`.npmrc` surfaces, then performs this fail-closed sequence:

1. Copy only `package.json` and `package-lock.json` into an isolated directory.
2. Run sanitized `npm ci --ignore-scripts --engine-strict
   --registry=https://registry.npmjs.org/` with user/global config set to
   `/dev/null` and proxy/cafile overrides removed.
3. Run zero-vulnerability `npm audit`, then `npm audit signatures`.
4. Install the repository copy with the same sanitized policy.
5. Run build, contracts, and browser checks; Playwright uses
   `npx --no-install`.

This policy is a dependency integrity gate, not license, SBOM, signing, or
release authority.

## 2. Make Frontend Web CI a required check (repo admin)

1. Repo → **Settings → Branches → Branch protection rules** for `main`.
2. Enable **Require status checks to pass before merging**.
3. Add the **`frontend`** job from `Frontend Web CI` as required.
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

## 4. Manual fallback (no GitHub-hosted runners yet)

If the variable is not set and the self-hosted runner is down, verify frontend
PRs locally / in a Codespace and attach logs — see
`docs/ai/checklists/frontend-web-pr-review.md`.

```bash
audit_config="$(mktemp -d)"
trap 'rm -rf -- "$audit_config"' EXIT
ln -s /dev/null "$audit_config/user.npmrc"
ln -s /dev/null "$audit_config/global.npmrc"
npm_clean() {
  env -i PATH="$PATH" \
    NPM_CONFIG_USERCONFIG="$audit_config/user.npmrc" \
    NPM_CONFIG_GLOBALCONFIG="$audit_config/global.npmrc" \
    NPM_CONFIG_CACHE=/tmp/structural-frontend-npm-cache \
    npm "$@"
}
npm_clean ci --ignore-scripts --engine-strict \
  --registry=https://registry.npmjs.org/ --strict-ssl=true \
  --include=prod --include=dev --include=optional --include=peer
npm_clean audit --json --audit-level=info \
  --registry=https://registry.npmjs.org/ --strict-ssl=true \
  --include=prod --include=dev --include=optional --include=peer
npm_clean audit signatures --json \
  --registry=https://registry.npmjs.org/ --strict-ssl=true \
  --include=prod --include=dev --include=optional --include=peer
npm run build
npm run verify:frontend-contract
npm run verify:workbench-prototype-dom-contract
npx --no-install playwright install chromium
npm run verify:frontend-browser-smoke -- --mode minimal
npm run verify:workbench-prototype-browser-smoke
```
