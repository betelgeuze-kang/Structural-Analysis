# Local priced RC candidate comparison browser observation

On 2026-09-08 the transferred mobile session verified both preserved M4 bundles
through actual Chromium display and download. The producer files were not
regenerated, rewritten or reanalyzed. This closes the pending local priced browser
integration check; it does not close independent numerical validation, licensed
corpus provenance, hosted CI, engineering approval or the overall roadmap.

## Sources and procedure

- Producer commit: `721448282d594f19fc4b2ce3158b369c579418dc`.
- Frontend source: `848dc44b0d487aabc96719dd2f259b2c23d669eb`.
- Trusted Node: `v24.20.0`, checked by `trusted-frontend-runtime.mjs`.
- Chromium: `141.0.7390.37`, headless at 1440 by 1080 pixels.
- Inputs: `/tmp/structural-search-source.6yxuk7/local-search/learned/` and
  adjacent `deterministic/`, each containing `manifest.json` and `comparison.json`.
- Driver, receipt, panel screenshots and downloads:
  `/tmp/structural-priced-browser.Gfekca/`. Run the retained `verify.mjs` from the
  repository root with the trusted Node after building the frontend.

The local HTTP server served the unchanged producer bytes at same-origin URLs
alongside the built frontend. Only the supported `designComparisonUrl` runtime
configuration was injected. The normal provider performed byte-length/hash and
schema/source/result/quantity/price checks before rendering. The driver asserted
each row's quantities, estimate, reduction, response, selected attribute, model
checksum and terminal limit status, then clicked the normal export control.
Both source files in both arms were byte-identical before and after the check.
Additional solver requests: zero.

| Arm | Raw manifest SHA-256 | Raw report SHA-256 |
| --- | --- | --- |
| learned | `e0ff557803b1408222844ac6817e1f67786ebfd1480d8224a325a4e32689d6df` | `dcaf6e2ff8e652dbbbd5790d915e5620b6d8ec39ab750f0438182bbfaf2a591d` |
| deterministic | `ee0e2394bff407f3ae45facbcc5c82323954558a242837d84fbd290d222dffb7` | `d77be54105864513c685a33a7d89a38d2a8034e8bbbf9430e293edef9e196843` |

These hashes identify local files; they are not signatures or independent receipts.
The receipt timestamp is `2026-09-07T23:17:58.970Z` (2026-09-08 KST).

## Observed display and export

The common declared price table uses 100 per cubic metre of concrete and 1 per
kilogram of authored longitudinal rebar, with currency `KRW` and source
`Synthetic integration prices; not a quote`. Its identity is
`sha256:408aebb318328ba798d81a1f2c81b5c8aca6b095fe6020e527f3534986f218bc`.

| Arm / candidate | Concrete (m3) | Rebar (kg) | Fixture estimate | Displayed reduction | Terminal screen | Selected |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| both / baseline | 0.72 | 72.9108 | 144.9108 | 0 | pass | deterministic only |
| learned / near_limit | 0.711 | 72.9108 | 144.0108 | 0.9 | pass | yes |
| deterministic / narrow | 0.648 | 72.9108 | 137.7108 | 7.2 | fail | no |

All four displayed rows were full-reference verified, including the alternative
that fails the caller-declared terminal screen. Its lower estimate did not grant
selection. Translation and fiber-strain displays also matched the producer's
values at the UI's scientific-notation precision. The model/price identities and
scope exclusions were visible in the captured panels.

For both downloads, `physical_design_comparison.report` and `.manifest` were
deep-equal to parsed producer JSON. The enclosing Workbench export is
reserialized JSON, so this is exact parsed-value equality, not a claim that its
bytes equal either original Python file. Original report raw-byte integrity was
checked separately against the manifest.

This single synthetic candidate search does not establish general selection
quality or performance. The fixture reduction is not real construction savings.
The original artificial training split, online/oracle request accounting and
independent-corpus limitations remain unchanged.

## Verification findings and limits

The initial full Workbench E2E run returned 141 passed and one failed: an old
Compare-section locator matched both the benchmark empty state and the new
physical comparison empty state. The test now checks each panel explicitly and
requires zero benchmark and physical candidate rows when unconfigured.
The complete `scripts/verify-workbench-v2-e2e.mjs --workers=2` rerun passed:
TypeScript, Vite build, viewer-delivery contract and **142 tests in 47.7 seconds**.
Its log is `workbench-e2e.log` in the retained temporary artifact directory.

The first temporary HTTP harness returned the app HTML for a missing auxiliary
viewer script, causing `Unexpected token '<'` after the learned table and export
assertions passed. The harness now returns HTTP 404 for missing static files.
Both completed priced checks had no page script exceptions. Auxiliary evidence,
MIDAS sample and drawing files were still absent and returned 404; those requests
are recorded in `receipt.json`. No auxiliary data or deployment completeness is
claimed. No viewer source or protected evidence was changed for this check.

The temporary artifacts remain local and are not independently retained evidence.
The overall Python full suite and hosted checks at the eventual PR head remain
separate pending checks; earlier focused results are recorded in the handoff.
