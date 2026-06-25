# Web CI operations

How to actually operate the two CI lanes and finish the priority-1 cleanup.
Items marked **(repo admin)** are GitHub settings that must be done in the web
UI / API — they cannot be done from a code PR.

## Two lanes

| Lane | Workflow | Runner | Scope |
| --- | --- | --- | --- |
| Frontend / web | `.github/workflows/frontend-web-ci.yml` | GitHub-hosted *(target)* or self-hosted *(default)* | `prototype/**`, `src/**`, `tests/frontend/**`, `package*.json` |
| Heavy / solver | `.github/workflows/ci.yml` | self-hosted / GPU | Python full tests, large benchmarks, GPU/HIP, full validation |

## 1. Turn the Frontend Web CI on GitHub-hosted runners (repo admin)

The workflow already supports the switch with no edit. When policy + billing
allow GitHub-hosted runners:

1. Repo → **Settings → Secrets and variables → Actions → Variables**.
2. Add a repository (or org) variable:
   - Name: `STRUCTURAL_FRONTEND_RUNNER_LABELS`
   - Value: `["ubuntu-latest"]`
3. Re-run the latest Frontend Web CI run (or push a trivial frontend change).

This routes **only** the frontend lane to GitHub-hosted runners. The heavy
solver lane (`ci.yml`) keeps using `STRUCTURAL_ACTIONS_RUNNER_LABELS`
(self-hosted) and is unaffected. To revert, remove the variable.

Expected result: frontend PRs leave the `queued` state and run
`npm ci → build → frontend contract → DOM contract → Playwright (chromium)`.

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
npm ci
npm run build
npm run verify:frontend-contract
npm run verify:workbench-prototype-dom-contract
npx playwright install chromium
npm run verify:frontend-browser-smoke -- --mode minimal
npm run verify:workbench-prototype-browser-smoke
```
