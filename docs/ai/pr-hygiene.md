# PR & branch hygiene (web track)

Cleanup checklist for the web track. The web surface landed on `main` through the
integration PR (#22), the cloud-CI fixes (#27), the AI-contract work (#25/#26),
and the workbench-v2 hardening line (#30 evidence-bundle, #31 case samples,
#32 commercial UX).

> Closing PRs and deleting branches must be done in the GitHub UI (the agent
> cannot close/delete or change repo settings). This doc is the checklist for it.

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

Example: `web/workbench-case-samples`, `web/evidence-bundle-hardening`.

## 2. Merge status (workbench-v2 line)

| PR | branch | state |
| --- | --- | --- |
| #30 | `web/evidence-bundle-hardening` | merged to `main` |
| #31 | `web/workbench-case-samples` | merged to `main` |
| #32 | `web/commercial-ux-realignment` | merged to `main` |
| #33 | `web/workbench-polish` | merged to `main` |
| (this) | `web/compare-and-live` | compare table + live sample + usage guide + this doc |

The merged branches above are safe to delete on GitHub. Local copies are removed
as each merges.

## 3. Branches to delete (merged or superseded)

Safe to delete on GitHub (Branches → trash) after confirming the PR is
closed/merged and the content is on `main`:

- Workbench-v2 hardening line (merged via #30/#31/#32/#33):
  `web/evidence-bundle-hardening`, `web/workbench-case-samples`,
  `web/commercial-ux-realignment`, `web/workbench-polish`
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
- The hygiene branch itself, once this doc is on `main`:
  `docs/pr-hygiene-and-stale-cleanup` (PR #29 was never merged; this doc
  supersedes it).

## 4. PRs to close (verify state in the UI first)

- **#2** — old prototype PR; superseded.
- **#29** — original hygiene plan; superseded by this doc landing via
  `web/workbench-polish`. Close as superseded once merged.
- **Evidence-console stack PRs** (the `#3`–`#8` line, if still open) — replaced
  by the workbench-v2 surface; close as superseded.
- **Per-PR web-track PRs** integrated by #22 (e.g. #15–#20 if still open) —
  close as "integrated via #22".
- **Cloud-CI fix PRs** superseded by #27 (e.g. #23, #24 if still open).

Rule of thumb: if the branch is in the delete list above and its content is on
`main`, close the PR with a note pointing to the integrating commit/PR.

## 5. PR #28 (large evidence PR) — do NOT merge as-is

A large evidence PR should not be merged from a web/mobile context. Decompose it
into small, reviewable, surface-scoped PRs:

1. `evidence/bundle-builder` — publishable bundle builder + manifest only
   (no readiness-number changes). **Landed** as part of #30
   (`scripts/build-workbench-evidence-bundle.mjs` + contract test).
2. `evidence/source-copy-separation` — keep protected source evidence separate
   from the public copy; no edits to protected originals. Documented in
   `docs/ai/evidence-bundle.md` (#30).
3. `evidence/ui-mismatch` — UI surfacing of source-commit mismatch / MISSING.
   **Landed** (EvidenceReaderPanel mismatch/missing markers).
4. (separate, NOT on web) protected-evidence regeneration at a single commit —
   requires the local/GPU/full-test environment.

Each piece must keep: originals untouched, single-commit gate, no inferred
readiness.

## 6. Do NOT do from the web/mobile environment

These need a local / GPU / large-test environment and are out of scope here:

- full-load nonlinear solver changes; ROCm/HIP backend; material Newton tangent
- running large benchmarks directly
- manual edits to protected evidence; changing release-readiness numbers
- merging a large evidence PR (#28) as-is
- changing numerical tolerances
