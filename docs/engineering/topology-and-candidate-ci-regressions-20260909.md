# Topology arithmetic and candidate browser CI regressions

This follow-up starts at `0113110186d6cd22c9ce3995e8a031556f02b50f`.
That head passes
[engine-v2-contract](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482321/job/102278770267),
both canonical-contract runs
([first](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291478766/job/102278759379),
[second](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482319/job/102278770017)),
and the [four-way determinism aggregate](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482397/job/102280954676).
These hosted results support the preceding
[golden/SBOM correction](planar-stable-kinematics-goldens-20260909.md) at that head.
They do not establish a full CI, independent validation or current-main pass.

This slice changes three topology tests and four candidate browser test files.
Production physics, material history thresholds, solver/benchmark gates,
candidate loading, strict parsing, hashes and original fixtures are unchanged.

## Topology: fixed-source comparison before changing expectations

The current-head [topology run](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482383/job/102278770109)
reports the same three failed and 409 passed tests as the prior head, in
1,204.52 seconds. Two fresh processes run the original
composite, fixed-local-axis and updated-axis benchmark builders on frozen current
source and an intervention that restores only the old
`corotational_frame2d_basic.py` from main `4de4e3f55`.
Each snapshot contains the same 563 source files. The intervention reproduces all
three old numerical expectations; current source reproduces all three reported
differences. Every original builder contract passes, each original full/replay
path is byte-exact within its variant, and both source inventories remain exact.

The composite benchmark still commits all 60 targets, with tensile evolution at
steps 6–20, compressive evolution at 38–40 and steel plastic evolution at 19–20.
At step 60, the old calculation gives four concrete fibers tensile-damage
increments above the existing `1e-15` reporting threshold, with maximum
`1.5543122344752192e-15`. The stable calculation gives five one-ULP changes of
`1.1102230246251565e-16`, with zero threshold crossings. All 60 sets of original
parent/child fiber states are retained, and their predicates were recomputed from
those states. The test's exact evolution list therefore becomes 6–20. The
threshold is unchanged. Repeating the external load after compression is not
used as proof of identical material history. Final damaged/plastified state
counts, irreversibility, dissipation and mixed-material checks remain.

The fixed-axis maximum residual changes from `1.2132765903061227e-09` to
`1.2144880656705936e-09 kN`; maximum balance error changes from
`1.2132801430198015e-09` to `1.2144916183842724e-09 kN`. Tests now require
nonnegative finite metrics within the existing `3e-8 kN` acceptance limits and
explicitly pin those limits to `3e-8`. They no longer prescribe the rounding
digits of a converged residual. Original response, force transformation,
ancestry, replay and energy checks remain.

The updated-axis geometric split evaluates `fl(fl(F + L) - F) - L`. Its norm is
`8.881784197001252e-16 kN/m` instead of exact zero. The new assertion uses
`2 * gamma_(n+4) * (norm(F) + norm(L))`, with `u = 2^-53`,
`gamma_k = k*u/(1-k*u)` and nine **global** DOFs. The budget covers three
arithmetic operations, the absolute row sum and reported component-norm rounding
for this normal-float case. The bound is `7.807724310740089e-14 kN/m`, and the
test also retains the producer's `1e-8 kN/m` cap. Material/geometric tangent,
finite-difference, symmetry and objectivity gates are unchanged.

All three focused modules pass **26 tests in 76.13 seconds**; Ruff and diff checks
pass. The saved-data audit passes **1,286 checks / zero errors**, without numerical
calls. An independent read-only review confirms the saved fiber predicates and
dimensional rounding bound. A final comment-only edit clarifies the rounding of
the displayed damage increment.

The diagnostic executes six original builders, 14 path calls and six direct
forced-step calls, retaining 540 committed path steps. Updated-axis builders
include their original paired fixed-axis path. Current and intervention worker
costs are 79.990184096 and 78.840394757 seconds. The subsequent pytest run executes
the original builders and additional standalone exercises again; it has no
instrumented total solver-call count. These are internal correctness runs with
observation/export overhead, not repeated speed or independent physics evidence.
Both use Linux CPython 3.10.12, NumPy 1.26.4/SciPy 1.12.0, Haswell and single
BLAS/OMP/MKL threads. The initial snapshot preparation rejected the archive's
root directory before extraction; that zero-solve error and its narrow fix are
recorded separately.

## Candidate review: wait for the actual loading boundary

At head `011311018`, the
[pull-request frontend job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291482401/job/102278770368)
and [push frontend job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34291478800/job/102278760369)
each have ten failures waiting five seconds for a candidate `verified`/`invalid`
panel. The pull-request job also has a separate extended-sparse mobile wait
failure. The global 120-second test timeout does not extend locator assertions.

The original candidate review succeeds locally with its 72-file, 16,768,526-byte
fixture. Deliberate sixfold CPU throttling retains the same bytes and reaches
`verified` at approximately 9.1 seconds, after about 7.98 seconds in `loading`.
Corrupted bytes reach `invalid` with the original byte-length diagnostic. This
demonstrates legitimate loading beyond the old five-second assertion; the hosted
logs lack terminal DOM state, so the precise hosted delay mechanism is not proven.

The shared test helper waits up to 60 seconds only for candidate loading to end,
then immediately asserts the first observed terminal status with its diagnostic.
Unexpected invalid/error states fail immediately rather than being retried until
they become verified. Later UI, source, quantity, history and original-byte
download assertions keep their original bounds. No global timeout or production
loader/validation policy is changed.

Two new browser regressions hold the real suite response for 5.5 seconds, once
with intact bytes and once with corruption. Both require no physical rows or
downloads while loading, followed by either the original verified export bytes
or the actual invalid diagnostic with no rows/downloads. Deferred work is released
and its promise collected even when an assertion fails.

The candidate suites pass **17 browser tests with three workers in 1.5 minutes**.
After tightening failure cleanup, the two delayed cases pass again in 27.9
seconds. Type checking, Vite build and production delivery checks pass; the
production Workbench asset hash and checked fixture/loader sources are unchanged.
These groups overlap. The separate, unmodified extended-sparse desktop/mobile/
tamper tests pass three cases in 18.7 seconds, but its hosted mobile failure
remains unreproduced and is not declared fixed by this change.

All three diagnostic browser pages retain an unrelated `Unexpected token '<'`
error from an optional iframe script receiving the static HTML fallback. Candidate
requests have no transport failures and their terminal outcomes are directly
observed. This is not a clean whole-application browser claim. No numerical solver
was run by the browser work.

## Retention and remaining work

The topology bundle is sealed at
`/tmp/structural-topology-stable-diagnostic.ou6jfafs`: **1,170 files /
389,460,393 bytes**, excluding its 250,876-byte inventory. Inventory SHA-256 is
`19a40dccac2a71d55cb408c71d5da928ca8ce3efe92dda9b5e4988d4398ecac2`.
A separate fresh process verifies the complete file set and all hashes; its
receipt is outside the root at the same path plus `-seal-verification.json`.

The browser bundle is sealed at `/tmp/structural-frontend-loading-ci.nW5cVFqy`:
**35 files / 25,289,103 bytes**. Inventory SHA-256 is
`f68eb287ee11c8da02af70408afa1250faa8d7f3dcf91ec6075902ae321ac993`.
Its separate fresh-process byte verification also passes. These unsigned local
bundles retain original logs, observed outputs, input/source identities, tests
and measurement boundaries; they are not published in full on GitHub. A
[concise machine summary](topology-and-candidate-ci-regressions-20260909.summary.json)
records the relevant results and identities.

New exact-head hosted checks remain required. Full-pytest materialization and
legacy-evidence failures are separate investigations; a test suite skipped after
preparation failure has no full-suite result. Broader M1–M5/P1–P3 work, independent
validation, current-main R1, separate R2 and external licensing/hardware/owner
dependencies remain open.
