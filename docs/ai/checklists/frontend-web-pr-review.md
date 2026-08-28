# Frontend Web PR review checklist

Purpose: keep frontend pull requests reviewable and mergeable independently of
the heavy self-hosted Python / GPU solver CI. This implements priority 1 (web
CI path) on the fixed `ubuntu-24.04` runner:

- **CI:** GitHub-hosted Ubuntu 24.04 runs the clean-copy dependency gate, build,
  contract, and browser smoke automatically.
- **Local/Codespaces:** run the same pinned commands below and attach the
  logs/screenshots to the PR when diagnosing a CI failure.

## Manual verification (option B)

Run from the repository root with Node `24.20.0` and npm `11.19.0`. Confirm no
repository or ancestor `.npmrc`, shrinkwrap, pnpm/yarn/bun lock/config, or
workspace override exists before installing.

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
npm run build                                   # type-check + Vite multi-entry build + Workbench/Viewer delivery check
npm run verify:frontend-contract                # frontend build contract
npx --no-install playwright install chromium
npm run verify:frontend-browser-smoke -- --mode minimal
```

Attach to the PR:

- the trimmed console output of each command (pass/fail), and
- at least one screenshot of the rendered surface under review.

## Reviewer checklist

- [ ] `npm run build` passes (TypeScript type-check + Vite multi-entry build + Workbench/Viewer delivery contract).
- [ ] `verify:frontend-contract` passes.
- [ ] `verify:frontend-browser-smoke -- --mode minimal` passes (or the failure
      is understood and unrelated to this change).
- [ ] Frontend-only change: the heavy solver CI (`ci.yml`) result is **not**
      used as the merge gate. A cancelled/queued heavy job does not block this
      PR.
- [ ] If the PR touches a demo/prototype surface, mock data is clearly labelled
      and no unverified PASS / readiness claim is shown.

## Separation of concerns

- `frontend-web-ci.yml` — frontend build, contract, minimal browser smoke.
- `ci.yml` — GitHub-hosted structural-core integration gate.
- `nightly-heavy-solver.yml` — self-hosted large/GPU/HIP validation.

Frontend PRs should be judged by `Frontend Web CI` (or the manual option-B run
above), not by the heavy solver CI.
