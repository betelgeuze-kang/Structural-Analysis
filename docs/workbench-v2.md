# Workbench v2 — usage guide

Workbench v2 is the default product shell for reading structural analysis cases and
their release evidence. Its design goal is an **honest evidence reader**: it
shows only what is attached, labels demo vs. live data, and never infers a
pass/fail or release-readiness verdict.

## Opening it

The repository root now opens Workbench v2. The explicit route remains available for stable deep links:

```
/
/#/workbench-v2
```

On GitHub Pages it lives under the project base path, e.g.
`https://<user>.github.io/Structural-Analysis/#/workbench-v2`.

The former all-in-one `App` is retained only as a compatibility/evidence desk at `/#/legacy`. It is not the default product shell and must not own new project, run, result, comparison, review, or export workflows. Its module is loaded lazily only after the explicit legacy route is selected; the default Workbench request graph must not download it.

## Product architecture boundary

Workbench v2 owns the project, analysis, run monitor, results, comparison, evidence, review, and export flow. Static Viewer is embedded as the specialized 3D/drawing/evidence subsystem in Model Health and keeps its independent provenance visible. Selection is synchronized through the viewer bridge, but Workbench does not reinterpret Viewer payloads as matching analysis evidence without provenance agreement.

The Viewer runtime and offline-release responsibilities are defined in [Structure Viewer module boundaries](structure-viewer-module-boundaries.md).

### Production delivery boundary

Workbench and Static Viewer are separate HTML entries in the same Vite production build. `npm run build` must emit both `dist/index.html` and `dist/src/structure-viewer/index.html`; the latter is the exact path used by the Workbench iframe and direct Viewer links. The build then runs `workbench_viewer_production_delivery_v1`, which rejects a missing Viewer entry, a Workbench SPA fallback served in its place, missing emitted assets, a Workbench bundle that no longer targets that entry, legacy ownership markers in the eager Workbench graph, or anything other than one route-loaded legacy `App` chunk.

The Workbench browser smoke also enters the iframe and requires the Viewer-only `data-si-shell="product"` marker. Merely observing a `200` response or matching the iframe `src` is not sufficient, because a generic SPA fallback can satisfy both while recursively rendering Workbench instead of Viewer. The same smoke verifies that the initial root load requests no `App-*.js` chunk and that the explicit legacy route requests exactly one.

## Data mode: Demo vs Live

A badge in the header shows the active data mode.

- **Demo** — bundled sample cases (see below). Clearly illustrative.
- **Live** — loads a published case from `evidence/workbench-case.json`
  (resolved against the app base path). If no case is published, live mode
  reports **MISSING** rather than inventing data.

Switch modes with the Provider toggle in the header.

## Durable job status

Workbench can consume the separate `structural-analysis-job-view.v1` endpoint
through the optional same-origin `VITE_JOB_STATUS_URL` build setting. The job
panel reports only queue, lease, checkpoint, publication state, and artifact
hashes. It never turns `succeeded` into a convergence verdict; convergence and
engineering values still require the referenced core result/evidence pair.

The endpoint is fetched with same-origin browser credentials and `no-store`.
Workbench rejects unknown fields, lease tokens, non-atomic result/evidence
publication, invalid hashes, impossible progress, and inconsistent resume state.
After success it fetches the referenced result/evidence endpoints, verifies
their declared byte lengths and SHA-256 digests when Web Crypto is available,
and checks the completion envelope's exact job/request/checkpoint/result binding.
For a ready nonlinear result it then accepts only the embedded, hash-bound
`corotational-fiber-frame2d-engineering-result-ir.v1` identity and authority
axes. The durable-job UI does not fall back to legacy top-level displacement,
reaction, member, section, fiber, or convergence arrays. Those compatibility
fields remain owned by the core API and cannot become Workbench solver truth.
If the endpoint is absent or invalid, the panel is explicitly **UNAVAILABLE**.
See [Durable job service and exact resume](durable-job-service.md).

### Demo cases

The demo provider offers three samples so the execution and evidence boundaries are visible:

| case | what it shows |
| --- | --- |
| Converged | analysis reaches the residual tolerance and carries explicit `converged: true` evidence |
| Analysis failed | execution terminates with `status: failed`; numerical convergence remains **UNAVAILABLE** |
| Convergence unavailable | no analysis attached — status is **not** inferred |

`failed` is an execution outcome and never implies `converged: false`.
Completed numerical non-convergence is represented separately as
`status: not_converged` with explicit `converged: false` evidence.

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
decision (pass/review/fail) with a comment. The draft is keyed by the case source
commit and remains a human note, never an automated result. Workbench reports
the exact persistence outcome instead of assuming that browser storage worked:

| UI status | Meaning |
| --- | --- |
| `Saved locally` | The exact current draft was serialized, written to localStorage, and read back successfully. |
| `Session-only` | The current validated draft remains in Workbench memory and is included in export, but was not verified in localStorage and will not survive reload. |
| `Storage unavailable` | No persisted draft could be restored because storage was inaccessible or the stored entry was invalid. |
| `Previous state retained` | A replacement failed validation or serialization; the prior validated draft remains current. |

Storage errors expose only stable error codes and paths in the persistence
receipt; browser exception messages are not rendered. Corrupted entries are
removed best-effort. The export uses the exact in-memory draft shown in Review
and includes `reviewer_draft_persistence`, so a session-only edit is neither
dropped nor mislabeled as saved.

## Export bundle

The export JSON includes provenance, source + analysis checksums, the viewer
deep link, displayed blockers, selected comparison rows, an evidence manifest
reference (commit + checksum, or unavailable), the reviewer draft, and its
persistence receipt. A claim boundary states the references are for integrity,
not a verdict.

## Local development

> The CI sandbox blocks the npm registry, so install/build/Playwright run on the
> cloud Frontend Web CI, not in the sandbox.

```bash
npm ci
npm run dev                      # local preview
npm run build                    # type-check + both production entries + delivery contract
npm run verify:workbench-viewer-delivery
npm run build:evidence-bundle -- --check   # consistency check (no write)
npm run verify:evidence-bundle-contract    # offline gate contract test
```

End-to-end specs live in `tests/frontend/workbench-v2-e2e.spec.ts` and run in the
Frontend Web CI workflow.
