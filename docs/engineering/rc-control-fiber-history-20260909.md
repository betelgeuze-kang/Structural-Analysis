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
