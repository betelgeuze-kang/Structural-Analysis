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

## Quantity/response delta follow-up

The subsequent implementation review found that the report's validated physical
deltas were exported but not displayed. Commit `6e54814a3` adds concrete, rebar,
terminal-translation and terminal-fiber-strain changes beside their totals. The
labels explicitly use candidate minus baseline; estimate reduction retains the
opposite direction. Price absence does not remove verified physical differences.
An unverified baseline leaves all differences unavailable even if the candidate
has its own valid quantities and response. Neither sign is labeled as an
engineering improvement. Three new mutation checks reject forged physical deltas;
three browser cases exercise priced, unpriced and unavailable-baseline states.

Commit `6fa9154fb` also wraps report and price identities inside the comparison
panel on narrow screens. A mobile probe found that the existing diagnostic table
elsewhere in Workbench still expands the document to 633 pixels at a 390-pixel
viewport. The focused regression checks the physical comparison panel itself,
including its focusable horizontally scrollable table; it does not assert that
the entire application layout is fixed.

The final full Workbench rerun passed TypeScript, build, viewer delivery and
**148 tests in 48.2 seconds**. Both unchanged real priced bundles then passed
Chromium checks at consumer `6fa9154fbed1b8d6d791245de383f661c3967899`, including
their signed physical deltas, parsed export equality and mobile panel containment.
The learned candidate showed concrete change -0.009 m3, translation change
4.571e-7 m and strain change 3.004e-8 at display precision. The deterministic
narrow candidate showed -0.072 m3, 3.937e-6 m and 2.588e-7 respectively; its terminal
screen still failed and baseline remained selected. Each panel had client and
scroll widths of 360 pixels and right edge 376 at viewport width 390.

Retained artifacts: `/tmp/structural-roadmap-review.fp0gJ8/`, containing
`verify-priced-deltas.mjs`, final `receipt.json`, both downloads, desktop/mobile
screenshots and `workbench-e2e-final.log`. `diagnostic-mobile-overflow.json` came
from an intermediate diagnostic probe without the final containment assertion
and is not the acceptance receipt. Final receipt timestamp:
`2026-09-07T23:29:53.501Z`. Producer hashes, bytes, price limitations, missing
auxiliary files and zero additional solver requests are unchanged.

## Local full-suite preparation finding

`PYTHONPATH=src python3 -m pytest --maxfail=5` collected 7,149 tests, then stopped
with **5 failed, 256 passed, 3 skipped in 183.27 seconds**. Four failures in
`test_build_bounded_planar_external_linear_case_package.py` and one in
`test_build_bounded_planar_external_modal_buckling_case_package.py` required absent
generated package directories under `artifacts/vv/`. These directories are ignored
outputs, not deleted tracked files. `.github/workflows/python-test-collection.yml`
materializes them alongside other exact-source/protected replay artifacts before
its full shards; that preparation was not performed here.

This attempt used the unprepared implementation checkout while frontend-only
commits advanced HEAD, so it cannot serve as an immutable exact-head verification.
Its logs and JUnit report are `pytest-full.log` and `pytest-full.xml` in the same
temporary directory. Python sources were not changed during the attempt. The
finding does not establish remaining tests would pass, and no protected evidence
was rewritten to turn it into a passing run. Run the approved hosted prepared
workflow at the final PR head for the full-suite gate.
