# RC committed-state history and candidate selection

This observation uses fixed clean source
`cc45b34495fb261c103d3d6396f35b58aa3c0c4f`. It extends the existing bounded
serial-cantilever RC reference path with separate recovery of every positive
committed static epoch. It supplies local implementation and integration
observations; it does not close independent physics or release acceptance.

## Implementation and scope

The typed public history accessor retains the original J1-J5 adapter and checks
the public configuration, canonical checkpoint bytes, model/result bindings and
exact terminal row equality. One complete adapter validation precedes independent
constitutive/engineering recovery for each epoch from original Newton coordinate
bytes and accepted parent/material state. Terminal JSON, numerical identities and
checkpoint serialization are unchanged. Serialized terminal JSON cannot establish
this retained source. The history sidecar includes source-bound step arrays,
displacement/fiber rows, maxima and governing node/fiber/epoch.

Explicit `FiberFrameHistoryLimits` enables design-report v2 and candidate-search
v3. Final candidates must pass terminal and requested history screens; a missing
baseline history prevents selection. A failed history recovery preserves verified
terminal quantities/responses but grants no history or selection credit. The
predictor still predicts terminal quantities and has no history-safety authority.
Combined oracle verification is reported separately from terminal false-safe
counts. Measured suite arms retain their producer comparisons for export without
additional analysis requests. CLI and Workbench usage is in
`rc-fiber-design-experiments.md`.

The scope is epochs 1 through the final accepted epoch. The unforced initial state
has no accepted transition and is excluded explicitly. Discrete committed-state
maxima do not verify between-step extrema, cyclic/dynamic response, independent
material behavior or design-code compliance. Early-peak reduction, recovery
failure and baseline-selection blocking are covered by contract probes, not
claimed as additional physical observations.

## Fixed-source experiment

Preserved local artifacts and driver:
`/tmp/structural-history-search-observation.1hb9j5wp/`.

```bash
PYTHONPATH=src python3 /tmp/structural-history-search-observation.1hb9j5wp/run.py \
  cc45b34495fb261c103d3d6396f35b58aa3c0c4f
```

The driver checks exact HEAD and a clean checkout before and after measurement.
No source changes or other tests ran during the interval; exclusive host access
is not asserted. Four fresh training/validation/holdout cases use widths
0.34/0.46/0.37/0.43 m in the same synthetic 3 m, FY=-1 kN, two-step family as the
earlier terminal-only observation. Only the two training cases fit the policy.
Artificial group IDs do not prove independent family provenance.

Pool A uses baseline width 0.4 m and candidates 0.36/0.395 m; pool B uses 0.405 m
and 0.38/0.399 m. Each pool runs twice with alternating arm order, no warmups,
budget two full requests per arm including a fresh baseline, one exploration
slot, and a later fresh exhaustive oracle. The training-only mean terminal
translation and strain labels set both separately typed screens:
`4.551020408163264e-5 m` and `2.991063860793252e-6`.

All four comparisons were ready. Four training requests plus 16 online requests
and 12 oracle requests total **32**, with no unknown request count. All 28 online
and oracle results passed reference and history verification with epochs `[1, 2]`.
Their terminal result and checkpoint artifact hashes match the preserved
terminal-only observation at source `412fda612`. The driver records 16 online
comparisons in `terminal-parity.json`; a post-measurement read-only check records
the 12 oracle comparisons in `oracle-terminal-parity.json`.

In these low-load cases both maxima occur at epoch 2, so the history envelope
equals the terminal metrics. This run does not demonstrate an earlier physical
peak. Twenty repeated rows pass the screens and eight `narrow` rows fail them.
Every deterministic arm retains its baseline; every learned arm selects the
verified `near-limit` candidate. Per pool, the repeated oracle records two missed
feasible candidates for deterministic and zero for learned, zero terminal
false-safe learned predictions, and zero combined-unverifiable candidates. These
are repeated observations of the declared candidates, not new independent models.

Synthetic KRW prices of 100 per m³ concrete and 1 per kg longitudinal rebar give
pool A estimates 144.9108 baseline / 144.0108 selected, and pool B 145.8108 /
144.7308. These scoped material figures are not quotes or construction savings.

## Timing and cost

History recovery and validation are included in each online/reference interval.
All times below are seconds; each strategy has two observations per pool.

| Pool | Deterministic median [min, max] | Learned median [min, max] | Paired deterministic minus learned [min, max] |
| --- | --- | --- | --- |
| A | 21.708334 [21.689103, 21.727564] | 21.754906 [21.747454, 21.762357] | -0.046572 [-0.058351, -0.034793] |
| B | 21.797513 [21.784174, 21.810852] | 21.681119 [21.622789, 21.739450] | 0.116393 [0.044724, 0.188062] |

The learned arm is slower in both A repetitions and faster in both B repetitions;
there is no consistent cross-case speedup. Pool B's 335-reuse arithmetic
amortization projection assumes the same artifact and repeated positive median
difference. It is not an observed break-even. Pool A has no positive projection.
The earlier terminal-only run had different timing signs, so these short local
measurements also provide no stable acceleration claim across runs.

Data generation is 38.911286664 s, fitting 0.001506413 s, and suite through
aggregation 304.950313449 s; their accounted total is 343.863106526 s. The outer
collection/training/suite driver records wall 344.026536638 s and CPU
344.006376600 s. That outer interval includes training report emission and suite
encoding, and excludes imports, initial protocol emission, final suite file
writes, bundle exports and post-run checks. Suite accounting excludes final
encoding/I/O and prior training. These overlapping scopes must not be added.
Peak memory, physical disk traffic, per-strategy resources and exclusive-host
conditions were not measured here.

## Bindings and verification

- Training report: `sha256:3621c88c682ca1e59fbcb1ba989abce8f15ef86e9a08cd040f68caace81a915a`.
- Frozen policy: `sha256:fd547602514b70f0bdd8d3e9ab58d63981452f2cadc32c7a17b834d29f5a06a5` (same policy identity as the earlier terminal-only observation).
- Suite report: `sha256:8e57692845d3a57e6811e5b372df32958ffddf17cfa9dd2f4b9fbf00d6d1d77f`.
- Raw suite: 7,888,855 bytes, SHA-256 `150fb570c041f3e3320c8b66cb1f6ec1dd0177fb139399043afe2be28b7f1152`.
- Raw receipt: SHA-256 `2bea024f52d5d9915b536197312e3dbfc5189cd67a7fd236a13277283adf85c8`.
- Raw driver: SHA-256 `12f4494ad1d917304e66257238748846960d3cc11253011c1f6bebdcdf4a6bce`.

Focused groups passed separately and overlap, so their counts are not summed:

- Core history: 10 tests plus one earlier-peak reduction test; existing exact
  terminal recovery: 9 tests.
- Public history/design/search/suite integration: 25 tests in 14.28 s, including
  a real retained source and explicit injected producer contract probes.
- Final public API/design/suite/CLI/CI regression: 137 tests in 51.12 s, log
  `/tmp/structural-history-final-regression.log`.
- Frontend history contracts: 72 tests; final history browser probes: 2 tests.
- Changed Python Ruff/format and `git diff --check` passed.

## Actual Workbench consumption and export

The eight actual producer bundles are preserved under
`pool-{a,b}-{0,1}-{deterministic,learned}/`. The parser from the same fixed source
accepted all eight original byte-bound reports. Chromium `141.0.7390.37`, using
Node `v24.20.0`, checked each bundle at desktop 1440×1080 and mobile 390×844:
16 viewport observations retained the producer terminal/history values, statuses
and selected candidate. Table columns remain horizontally scrollable. All 16
downloads contained report and manifest JSON objects equal to the originals.
The export envelope is reserialized; exported file bytes are not claimed equal
to the original report file. Original input bytes remained unchanged, and no
additional solver request was made.

TypeScript, Vite build and viewer-delivery checks passed. There were no JavaScript
page errors or failures for comparison bundle/built asset requests. The local
harness has no auxiliary evidence, MIDAS sample or drawing manifests; those
unrelated 404 responses remain recorded in `bad_responses`. This does not verify
a fully provisioned installation or remove the separate existing full-page
horizontal-overflow limitation outside the comparison panel.

Browser artifacts, 16 screenshots and 16 downloads are in
`/tmp/structural-history-browser.zfddueqo/`:

- `receipt.json`: 21,824 bytes, raw SHA-256
  `a73f9518f9109b44e838c75f29139e949e4aef6384cd2769c658a2ddabf6e91d`.
- `parser-receipt.json`: 2,653 bytes, raw SHA-256
  `e122c9948c790122c4198498518ee798a9a426821da71d8ec64d46fb5bc2f114`.
- `verify.log`, `pool-a-0-deterministic-mobile.png` and
  `pool-b-1-learned-desktop.png` retain representative execution/visual evidence.

Hosted exact-head/full-suite checks, independent model families, broader physical
validation and release approval remain open. No push, PR, merge or deployment
was performed for this increment.
