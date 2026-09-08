# Stable planar kinematics: golden and runtime SBOM refresh

This follow-up to source `91f75dde94ab4503606017baee4df5e461aa87a4`
corrects two stale integration inputs found by draft PR #439. It refreshes 13
bounded-planar golden values after a fixed-source causal comparison, adds two
independent high-precision kinematics regressions, and updates the runtime SBOM's
source binding and its parent hash. Local focused checks pass. Exact-head hosted
acceptance, the full canonical artifact DAG and the broader roadmap remain open.

## Original failures and causal comparison

At implementation head `7f78b4c833dc805bf54d53b7ac8e750914a51238`,
[engine-v2-contract](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34287980265/job/102267864607)
reported one bounded-planar semantic mismatch after 299 passes. The workflow used
Ubuntu 24.04, CPython 3.10.21, NumPy 1.26.4 and SciPy 1.12.0. Its Python 3.10
contract excludes 12 reference-only raw numerical goldens, so this single failure
did not demonstrate that those raw values still matched.

The diagnostic froze main `4de4e3f55aae1d267cf704cec7d7533f3a627498`,
current source `91f75dde9`, and current source with only
`src/structural_analysis/elements/corotational_frame2d_basic.py` restored from
main. The current and intervention source inventories contain the same 406
files, with exactly that one file different. Main and the intervention reproduce
identical full and replay result JSON and checkpoint bytes for both fixtures.
All original source, recovery, restart and contract gates pass.

The cause is the intended small-chord calculation introduced in
`e2f6967ec84893aa83f3e56616ede3ff7f9b4f10`, described in
[the extended sparse record](planar-frame-extended-sparse-20260908.md).
Rationalized length and relative-angle evaluation preserve tiny strains that
direct subtraction of nearly equal absolute lengths and angles loses. No solver
or physical source is changed in this follow-up. Fixtures, semantic normalization,
acceptance thresholds and all generator AST outside `EXPECTED_GOLDENS` are
unchanged; the eight binary artifact expectations also remain exact.

The alpha projection changes 42 leaves: 35 convergence-history values and seven
small member-force/section-strain/section-force values. Both versions retain four
steps and 12 convergence rows, with iterations 0, 1 and 2 at each step. Its
terminal relative residual changes from `1.3789568570616305e-10` to
`3.8203256446151127e-16`. The normalized member force difference is approximately
`5e-7 N`, and the section strain difference is approximately `6.4e-17`.
Seven alpha hashes change, including its semantic hash.

The complete Python 3.12 reference writer additionally identifies six stale
settlement raw hashes. The separate settlement intervention reproduces main's
full/replay result and checkpoint bytes exactly. The current settlement semantic
projection remains byte-identical to main under the existing normalization.
Its eight convergence rows and authored settings remain; terminal relative
residual changes from `3.631240863555263e-10` to `1.1102230246251565e-15`.
The reference writer therefore supports 13 updates in the 46-value golden set.
The replay configuration's checkpoint artifact hash necessarily changes with its
input checkpoint; only the authored physical and solver settings are unchanged.

## Independent arithmetic regression and execution scope

The two new regressions use the retained main/current alpha terminal N2
translations and the original chord `(3.8 - .2, 0)`. Their reference computes
absolute norm and angle differences with 90-digit Decimal arithmetic, without
copying the production rationalized formula. For these normal-float horizontal
inputs, `abs(dx)/L < 1e-8` and `abs(dy)/L < 1e-4`. An absolute rounding budget
`gamma_32 * (abs(dx) + dy**2/L)` is approximately `6.45e-23 m`.
Observed stable extension errors are `1.68e-25` and `3.36e-25 m`, versus direct
subtraction errors of `2.03e-16` and `2.16e-16 m`. The angle errors also meet the
separate rounding budget. These are arithmetic checks for the retained inputs,
not a universal error proof or independent structural validation.

The initial causal run uses local CPython 3.10.12, whose patch differs from CI.
The full reference writer uses an isolated CPython 3.12.14 environment with pinned
NumPy 1.26.4/SciPy 1.12.0 and recorded official wheel identities; `pip check`
passes. Both use Linux x86_64, Haswell and single BLAS/OMP/MKL threads with
`PYTHONHASHSEED=0`. Alpha raw and semantic hashes agree exactly across these two
local Python versions. This is not the hosted Ubuntu/Windows four-way receipt.

| Focused group | Result | Recorded elapsed time |
| --- | --- | --- |
| Stable kinematics, including two retained inputs | 31 passed | 1.58 s |
| Runtime packaging builder with temporary synthetic inputs | 7 passed | 0.32 s |
| Corrected golden writer/workflow and semantic-policy checks, Python 3.12 | 4 passed | 4.07 s |
| Same corrected checks, Python 3.10 | 4 passed | 5.96 s |

The Python 3.12 test compares all 46 expected values and eight binary readbacks;
Python 3.10 retains the existing 12-value raw-reference exclusion. Ruff and
`git diff --check` pass. These groups overlap and are not a full-suite pass.

The retained diagnostics and reference writer observe 14 public API calls and
14 explicit original validations. The two corrected standard-test invocations
each execute the unchanged full writer: four additional API calls, four explicit
validations and one CPU FGMRES call per invocation. Thus the source-defined total
is 22 API calls, 22 explicit validations and three FGMRES calls, including the
reference writer. The last eight API calls are identified from the unchanged
test/writer body and passing test logs, rather than added observers. Precision,
SBOM and saved-data checks execute no additional public analyses. These counts
do not enumerate internal solver operations within public validation.

Recorded process costs are 4.197142708, 4.062989763 and 4.047118115 seconds for
the three initial alpha variants; 3.941477807 seconds for the full reference
writer; and 2.138724978/1.990831064 seconds for the two settlement interventions.
Environment preparation takes 7.960359170 seconds. These diagnostic and
observer-inclusive correctness costs are not a speed comparison.

## Bounded runtime SBOM correction

The separate
[canonical-contract failure](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34287955683/job/102267788256)
reported a runtime SBOM exact-rebuild mismatch and stale downstream receipts.
The two new CLI entry points changed `pyproject.toml`; the SBOM still bound its
main-era hash. The pure SBOM producer, using actual repository-relative input
paths, now rebuilds byte-exact after excluding the generated timestamp.

Exactly three JSON scalar leaves change:

- `runtime_sbom.json`: `/generated_at` and `/source_hashes/pyproject`.
- `production_runtime_packaging_manifest.json`: `/artifacts/sbom/sha256`.

The new pyproject SHA-256 is
`ac8911e7db8e8cccb0aafa037ecc88381764ffdd2f853425472d3bbfe6e56b5b`.
All 76 components, licenses and authority fields remain unchanged. The parent
hash exactly binds the 32,069-byte SBOM with SHA-256
`62dafb38067a8b2968ed260e75bd2a9fbc196f050319b84f5e5c15c14a58636c`.
No full production-packaging builder/validator or protected artifact DAG was
executed or regenerated. This local correction does not establish downstream
receipt freshness or a hosted canonical-contract pass.

## Retained artifacts and limits

The unsigned local observation is sealed at
`/tmp/structural-planar-golden-refresh-observation.7tuz7gre`.
Its inventory covers 2,484 files and 49,951,273 bytes, excluding the 573,873-byte
inventory itself. Inventory SHA-256 is
`e71c883f2991a77722941c44c5abd2c2adaff1c1d2de27460b8d4ac8222506c9`.
A separate fresh process verifies the complete file set, sizes and hashes after
sealing; its receipt is outside the sealed root at
`/tmp/structural-planar-golden-refresh-observation.7tuz7gre-seal-verification.json`.
The saved-data audit passes 2,415 checks with zero errors in 0.095248675 seconds
and performs no new numerical calls.

The bundle retains exact source snapshots, predeclared protocols, original
results/checkpoints/projections, old and observed golden values, test logs,
precision inputs, SBOM rebuild evidence and the four-file implementation patch.
The installed reference virtual environment is excluded; preparation receipts,
wheel identities and runtime versions are retained instead. GitHub contains this
record and a [concise machine summary](planar-stable-kinematics-goldens-20260909.summary.json);
the full raw bundle remains on the local host. Prior failed CI runs and earlier
sealed RC observations retain their original statuses and source identities.

Exact-head hosted checks remain pending at publication. This evidence establishes
local source/artifact consistency and bounded arithmetic behavior. Independent
physical/cross-code validation, the full roadmap, current-main R1, separate R2
integration, and release authority remain open.
