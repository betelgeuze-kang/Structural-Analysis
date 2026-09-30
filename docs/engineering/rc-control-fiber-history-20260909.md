# Fiber projection and native parent attribution at original force fields

The stable-stress probes retain 507 failed end-force/reaction comparisons across
the original two geometries, despite zero section-field tolerance failures.
Saved-force arithmetic identifies retained stress/load differences as the largest
ordered term at 489 values. This diagnostic resolves that term into finite fiber
projection, generalized strain evaluation, coordinate differences and native
material history at the same force fields.

For each original integration point and fiber, the diagnostic constructs three
finite inputs for each original arm: the saved binary64 fiber projection, one-round
rational projection of the saved generalized strains, and one-round rational
coordinate-to-fiber Hermite strain including both native coordinate components.
The last value avoids separately rounding axial strain and curvature. It still
rounds to binary64 before the original declared material law executes; it is not
an arbitrary-precision material input, native history update or continuum solution.

Both original native parents are evaluated at all six inputs (12 material calls
per fiber). Original endpoint responses must match completely, native parents
must remain immutable, and original generalized/fiber projections are checked.
Finite returned stresses are projected with exact rational section, geometry,
transformation and SI operations to the original member/reaction fields. Two
orders place the parent-history change before or after the strain changes. Each
order includes separate external-load and original force/section arithmetic
terms and must close exactly before serialization. Order-dependent contributions
are retained; no unique causal attribution is claimed.

The original force diagnostic first verifies full original force arithmetic,
path/step/history bindings and hashes. This diagnostic additionally verifies
step hashes and native parent chains, exact stress projection endpoints, and input
hashes before/after execution. All calls, including original arithmetic replays
and both model compilations, are counted. No section/element integration, Newton
solve or state commit is performed. Under stable-stress, each selected material
trial includes its original base-law integration; the observation harness will
count both layers separately rather than treating the nested call as free.

Seven focused tests cover an independent 100-digit Hermite expression, projection
cancellation, nonlinear interaction order, real cyclic endpoint replay with
section/element/Newton calls forbidden, and four rehashed tampering cases (fiber
strain, material state, generalized strain and local coordinates). The related
neighborhood passes 92 tests in 13.41 s. Initial two test failures were error-message
regex mismatches; the intended tampering rejections already occurred.

The observation will use the sealed stable-stress base and long reference/secant
pairs, preserving all 242 targets and fixed comparison tolerances. Both complete
pairs will be diagnosed serially in fresh source-verified processes, with input
bytes checked against the preceding sealed inventory. No new nonlinear study or
repeated timing qualification is part of this attribution. Results must guide the
next original-solver precision change; a counterfactual alone cannot qualify it.


## Completed source-bound observation

Diagnostic source `0cb963e4c30c02506898e0dd68be2b96d9746522` is frozen in
419 files, all compared to Git. Two fresh serial workers use the declared frozen
module paths and complete both original 242-target stable-stress pairs at
`de7b0d634a30921fff7c0b562cf1e0f09d1e13ed`. All original input bytes match the
preceding sealed inventory before and after diagnosis. These are replays of the
existing studies, with no new nonlinear benchmark execution.

The observation verifies 7,260 selected force-component pairs and **81,312 original
material endpoint responses**. It performs 487,872 selected stable-material trials:
418,176 concrete and 69,696 steel. Instrumented base-law entry points independently
record another 418,176 concrete and 69,696 steel calls inside those trials, for
**975,744 actual material method entries across both layers**. These are nested
calls, not 975,744 independent strain/parent combinations. Four model compilations,
968 initial original step-force replays and 968 additional exact endpoint replays
are counted separately. Section/element integration, Newton and commit counts
remain zero. Both workers terminate successfully; their whole diagnostic times
are 32.583426 s and 32.662829 s, including material calls and original record checks.

Every original endpoint response and exact force projection matches. All native
parents remain unchanged, all two-order rational decompositions close exactly,
and all 263 base / 244 long originally failed force fields remain represented.
The following counts identify the largest absolute term among those original
failures. Counts refer to the declared order, not unique causal responsibility.

| Geometry / parent order | Finite coordinates | Native parent history | Reference generalized evaluation | Candidate generalized evaluation | Force/section arithmetic | Either fiber projection | External load |
| --- | --- | --- | --- | --- | --- | --- | --- |
| base / history last | 152 | 75 | 15 | 18 | 3 | 0 | 0 |
| base / history first | 158 | 72 | 15 | 15 | 3 | 0 | 0 |
| long / history last | 156 | 50 | 16 | 12 | 10 | 0 | 0 |
| long / history first | 156 | 50 | 16 | 12 | 10 | 0 | 0 |

The base geometry's seven M2 failures have zero parent-history contribution and
finite coordinate differences are largest in both orders. M1 failures and the
reactions also contain nonzero native-history and generalized-strain evaluation
contributions. Generalized evaluation here includes separately rounding axial
strain and curvature before fiber projection; the direct-coordinate
counterfactual rounds the final fiber strain once. Final fiber projection
rounding is not the largest term at any of the failed values, although its
contribution is not generally zero. Changing that projection alone therefore has
no evidence of resolving the failures. Likewise, the finite-coordinate term
contains differences between accepted original solutions; it is not proof that
simply storing more coordinate bits will repair the solve.

The next original-solver precision work must address accepted-solution precision
at fixed native parents, assess end-to-end generalized-to-fiber evaluation, and
retain the observed sensitivity to persistent native material history. Any new
profile must run through original solve/commit/recovery and the complete fixed
physical comparisons, with whole costs included. Counterfactual endpoint values
must not replace accepted outputs. The prior stable-stress result remains 0/2
physical passes; no accepted acceleration or independent physics claim changes.

The sealed local bundle contains **436 files / 18,671,308 bytes** at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-fiber-history.i35wsok9`.
All files were reread/hash-checked, inventory SHA-256:
`78fb4a5af6780bfb6e9a5b41a897cafa124866479d6703732f522e8ad78b959f`.
The [machine summary](rc-control-fiber-history-20260909.summary.json) retains
per-member/reaction, per-order counts and maximum contributions. Earlier evidence
is unchanged. Hosted/full-suite acceptance and the full roadmap, including
independent validation, licensing, hardware, owner and R1/R2 work, remain open.
