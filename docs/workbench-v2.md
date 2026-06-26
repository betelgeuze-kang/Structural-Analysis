# Workbench v2 — usage guide

Workbench v2 is the browser front end for reading structural analysis cases and
their release evidence. Its design goal is an **honest evidence reader**: it
shows only what is attached, labels demo vs. live data, and never infers a
pass/fail or release-readiness verdict.

## Opening it

The app uses hash routing. The workbench route is:

```
/#/workbench-v2
```

On GitHub Pages it lives under the project base path, e.g.
`https://<user>.github.io/Structural-Analysis/#/workbench-v2`.

## Data mode: Demo vs Live

A badge in the header shows the active data mode.

- **Demo** — bundled sample cases (see below). Clearly illustrative.
- **Live** — loads a published case from `evidence/workbench-case.json`
  (resolved against the app base path). If no case is published, live mode
  reports **MISSING** rather than inventing data.

Switch modes with the Provider toggle in the header.

### Demo cases

The demo provider offers three samples so each honest result state is visible:

| case | what it shows |
| --- | --- |
| Converged | analysis reaches the residual tolerance |
| Did not converge | run stalls above tolerance (`status: failed`) |
| Convergence unavailable | no analysis attached — status is **not** inferred |

### Previewing live mode locally

The published bundle path `public/evidence/` is gitignored (it is generated, not
committed). A ready sample lives at
`src/workbench-v2/model/fixtures/live-sample.workbench-case.json`. To preview
live mode locally, copy it into the served path:

```bash
mkdir -p public/evidence
cp src/workbench-v2/model/fixtures/live-sample.workbench-case.json public/evidence/workbench-case.json
```

The sample's provenance is marked `sample-not-a-release`; it demonstrates the
format, not a validated result.

## Layout (left navigation)

The commercial flow reads top-to-bottom; evidence and benchmarks sit in a
verification layer below it:

- **Project** — case + provenance (source path, commit, checksum)
- **Model Health** — embedded 3D viewer + selection inspector
- **Analysis** — solver/type and run status; demo case selector
- **Run Monitor** — recorded-vs-total iterations, residual vs tolerance
- **Results** — verdict card + log-scale residual chart
- **Compare** — reviewer-selected benchmark comparison set
- **Evidence** — read-only evidence reader (see below)
- **Benchmarks** — public benchmark catalog + validation lifecycle
- **Review** — automated verdict (always UNAVAILABLE) + human draft
- **Export** — JSON bundle of everything above

## Viewer selection

The 3D viewer and the workbench share a selection channel (both directions).
The Model Health panel shows the selected member and lets you focus an arbitrary
member id or copy a deep link for it. The case contract carries model counts
only (no member list), so member focus is a free-form tool — no member-level
data is fabricated. In demo mode the viewer shows its own sample model, so the
two provenances are kept independent and never treated as the same artifact.

## Compare

Adding benchmark rows (in Benchmarks) populates the Compare set. The table shows,
per row, whether it is accuracy-comparable, whether reference results and a
runner are present, and what is still required to compare. **No accuracy delta is
computed in the app** — real numbers come only from a run against attached
references on a registered runner.

## Evidence reader

The Evidence panel reads a published, read-only bundle. It surfaces source
commit, per-artifact checksums, and gate states; when the bundle is absent it
shows MISSING/unavailable and infers no readiness. See
[evidence bundle](ai/evidence-bundle.md) for how the bundle is built and the
single-commit rule.

## Review

The automated verdict is always UNAVAILABLE. A reviewer can record a **draft**
decision (pass/review/fail) with a comment; it is stored in the browser
(localStorage), keyed by the case source commit, and included in the export. It
is a human note, never an automated result.

## Export bundle

The export JSON includes provenance, source + analysis checksums, the viewer
deep link, displayed blockers, selected comparison rows, an evidence manifest
reference (commit + checksum, or unavailable), and the reviewer draft. A claim
boundary states the references are for integrity, not a verdict.

## Local development

> The CI sandbox blocks the npm registry, so install/build/Playwright run on the
> cloud Frontend Web CI, not in the sandbox.

```bash
npm ci
npm run dev                      # local preview
npm run build:evidence-bundle -- --check   # consistency check (no write)
npm run verify:evidence-bundle-contract    # offline gate contract test
```

End-to-end specs live in `tests/frontend/workbench-v2-e2e.spec.ts` and run in the
Frontend Web CI workflow.
