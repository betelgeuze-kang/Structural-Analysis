# PR & branch hygiene (web track)

Cleanup plan after the web track landed on `main` via the integration PR (#22)
plus the cloud-CI fixes (#27) and the AI-contract work (#25/#26).

> Closing PRs and deleting branches must be done in the GitHub UI (the agent
> cannot close/delete). This doc is the checklist for that.

## 1. PR title / branch prefixes

Use a product-surface prefix on branches and PR titles so lanes are obvious:

| prefix | scope |
| --- | --- |
| `web/` | frontend (workbench-v2, prototype, viewer bridge, evidence reader UI) |
| `ai/` | AI contract verification / orchestration |
| `solver/` | nonlinear solver, GPU/HIP, material tangents |
| `evidence/` | release evidence artifacts + publishable bundle |
| `benchmark/` | public benchmark catalog / validation lifecycle |
| `docs/` | documentation, checklists, hygiene |

Example: `web/workbench-case-samples`, `evidence/bundle-hardening`.

## 2. Branches to delete (merged or superseded)

These were merged into `main` (web track → #22) or superseded; safe to delete
on GitHub (Branches → trash) after confirming the PR is closed/merged:

- Web track, integrated via #22:
  `feat/frontend-web-ci`, `feat/workbench-prototype-safe`,
  `feat/workbench-v2-react`, `feat/workbench-v2-evidence-reader`,
  `feat/workbench-v2-benchmark-browser`, `feat/web-track-integration-to-main`,
  `web/ci-runner-and-branch-cleanup`, `web/evidence-bundle-publisher`,
  `web/workbench-case-contract-v2`, `web/workbench-viewer-bridge`,
  `web/benchmark-validation-lifecycle`, `web/workbench-v2-e2e-and-deployment`,
  `web/cloud-integration`
- Cloud-CI fix branches, superseded by #27 / origin main:
  `web/fix-cloud-action-versions`, `web/fix-tsc-and-trigger`,
  `web/stabilize-frontend-ci`
- Earlier evidence-console stack (superseded by workbench-v2):
  `feat/evidence-console-prototype-safety`,
  `feat/evidence-console-a11y-responsive`,
  `feat/evidence-console-readiness-integration`,
  `feat/evidence-console-browser-test-contract`,
  `feat/evidence-console-react-integration`,
  `feat/evidence-console-ci-and-baseline`

## 3. PRs to close (verify state in the UI first)

- **#2** — old prototype PR; superseded.
- **Evidence-console stack PRs** (the `#3`–`#8` line, if still open) — replaced
  by the workbench-v2 surface; close as superseded.
- **Per-PR web-track PRs** that were integrated by #22 (e.g. #15–#20 if they are
  still open) — close as "integrated via #22".
- **Cloud-CI fix PRs** superseded by #27 (e.g. #23, #24 if still open).

Rule of thumb: if the branch is in the delete list above and its content is on
`main`, close the PR with a note pointing to the integrating commit/PR.

## 4. PR #28 (large evidence PR) — do NOT merge as-is

Per the do-not list, a large evidence PR should not be merged from a web/mobile
context. Decompose it into small, reviewable, surface-scoped PRs:

1. `evidence/bundle-builder` — the publishable bundle builder + manifest only
   (no readiness-number changes).
2. `evidence/source-copy-separation` — clearly separate protected source
   evidence from the public copy; no edits to protected originals.
3. `evidence/ui-mismatch` — UI surfacing of source-commit mismatch / MISSING.
4. (separate, NOT on web) any protected-evidence regeneration — requires the
   local/GPU/full-test environment.

Each piece must keep: originals untouched, single-commit gate, no inferred
readiness. Fill in concrete file lists once #28's diff is reviewed.

## 5. Do NOT do from the web/mobile environment

These need a local / GPU / large-test environment and are out of scope here:

- full-load nonlinear solver changes; ROCm/HIP backend; material Newton tangent
- running large benchmarks directly
- manual edits to protected evidence; changing release-readiness numbers
- merging a large evidence PR (#28) as-is
- changing numerical tolerances
