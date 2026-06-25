# Frontend Web PR review checklist

Purpose: keep frontend pull requests reviewable and mergeable independently of
the heavy self-hosted Python / GPU solver CI. This implements priority 1 (web
CI path) and supports both runner options:

- **Option A (GitHub-hosted):** the `Frontend Web CI` workflow runs build +
  contract + minimal browser smoke automatically. When billing/policy approves
  GitHub-hosted runners, set the variable `STRUCTURAL_FRONTEND_RUNNER_LABELS` to
  `["ubuntu-latest"]`.
- **Option B (self-hosted / Codespaces, current default):** if the self-hosted
  runner is unavailable, run the steps below manually (locally or in a
  Codespace) and attach the logs/screenshots to the PR.

## Manual verification (option B)

Run from the repository root with Node `20.19.0`:

```bash
npm ci
npm run build                                   # tsc --noEmit && vite build
npm run verify:frontend-contract                # frontend build contract
npx playwright install chromium
npm run verify:frontend-browser-smoke -- --mode minimal
```

Attach to the PR:

- the trimmed console output of each command (pass/fail), and
- at least one screenshot of the rendered surface under review.

## Reviewer checklist

- [ ] `npm run build` passes (TypeScript type-check + Vite build).
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
- `ci.yml` — heavy self-hosted path: Python full tests, large benchmarks,
  GPU/HIP, full validation. Leave this as the solver/back-end gate only.

Frontend PRs should be judged by `Frontend Web CI` (or the manual option-B run
above), not by the heavy solver CI.
