# Frontend Web PR review checklist

Purpose: keep frontend pull requests reviewable and mergeable independently of
the heavy self-hosted Python / GPU solver CI. This implements priority 1 (web
CI path) on the fixed `ubuntu-24.04` runner:

- **CI:** GitHub-hosted Ubuntu 24.04 runs the clean-copy dependency gate, build,
  contract, and browser smoke automatically.
- **Local/Codespaces:** run the same pinned commands below and attach the
  logs/screenshots to the PR when diagnosing a CI failure.

## Manual verification (option B)

Run from the repository root using the official Node `24.20.0` Linux x64
archive and bundled npm `11.19.0`. First match the archive to the nodejs.org
`SHASUMS256.txt` entry and the pinned executable hashes used by CI. Confirm no
repository or ancestor `.npmrc`, shrinkwrap, pnpm/yarn/bun lock/config,
`devEngines`, or workspace override exists. PATH-found `node`, `npm`, and
`npx` are not accepted. TypeScript, Vite, Playwright, and repository `.mjs`
entry files must be passed directly to that absolute Node binary inside the
documented `env -i` allowlist; `node_modules/.bin` shims are not authoritative.

```bash
trusted_node=/absolute/verified/node-v24.20.0-linux-x64/bin/node
/usr/bin/env -i PATH=/usr/bin:/bin HOME=/tmp/frontend-home \
  TMPDIR=/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  "$trusted_node" scripts/verify-frontend-smoke.mjs
```

`package.json` scripts are local conveniences only. Do not attach authority to
`npm run` output without the trusted launcher and environment isolation above.

Attach to the PR:

- the trimmed console output of each command (pass/fail), and
- at least one screenshot of the rendered surface under review.

## Reviewer checklist

- [ ] The trusted-tool clean smoke passes (clean install, audit, signatures,
      TypeScript/Vite build, and delivery contract).
- [ ] `verify:frontend-contract` passes.
- [ ] `verify:frontend-browser-smoke -- --mode minimal` passes (or the failure
      is understood and unrelated to this change).
- [ ] The always-running `frontend-required` aggregator succeeds. Repository
      administration records its branch-protection receipt after the workflow
      lands; this code change alone does not claim that setting.
- [ ] If the PR touches a demo/prototype surface, mock data is clearly labelled
      and no unverified PASS / readiness claim is shown.

## Separation of concerns

- `frontend-web-ci.yml` — frontend build, contract, minimal browser smoke.
- `ci.yml` — GitHub-hosted structural-core integration gate.
- `nightly-heavy-solver.yml` — self-hosted large/GPU/HIP validation.

Frontend PRs should be judged by `Frontend Web CI` (or the manual option-B run
above), not by the heavy solver CI.
