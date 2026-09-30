# Training-only nested ridge selection

Source `d4825c2278528dbc42dc32f242fb2b45563c8ebb` adds bounded nested
selection of an SVD ridge candidate against deterministic secant. The previous
[fixed-ridge diagnosis](rc-svd-ridge-20260910.md) showed that changing the
linear algebra alone did not resolve the large correction errors. This study
selects regularization using only the existing four authored training cases
and 964 original pairs. No validation/holdout response, new structural solve,
material integration or external experimental sample enters selection.

For each outer case, all its rows are removed. Seven ridge values from `1e-6`
through `1e6` are scored by leaving each remaining case out in turn. Every fit
recomputes its preprocessing from its own training partition. The score is the
equal-case mean of learned/secant correction MSE ratios, with each fit's training
target scales and the controlled coordinate omitted. These are **ungated
development losses**, not a simulation of runtime abstention or physical error.
Feature-range eligibility is reported separately.

A learned candidate must improve the declared score by more than 1%; otherwise
secant remains selected. Exact learned-score ties favor the larger ridge. A
zero secant loss is explicitly a tie only when learned loss is also zero;
otherwise the ratio is unavailable and cannot become an apparent improvement.
The final selection repeats inner case selection using all original training
cases. A selected learned candidate is then refitted on those rows. Secant
selection creates no artificial fitted policy. The maximum planned fit count
is checked before execution; each fit has a persisted reservation and outcome.

## Original-data observation

All **114 fits** finish: 112 inner-grid fits and two selected refits. The
full-training inner score selects ridge **10,000**, at **0.9826793992** relative
to secant: a 1.7321% reduction in this development loss. Scores at ridge 100 and
1,000,000 are 1.0694651883 and 0.9946592447 respectively; the latter does not
meet the required 1% improvement.

| Outer case | Selected method | Inner score | Outer relative loss | Learned outer rows inside fitted ranges |
| --- | --- | ---: | ---: | ---: |
| train-a | secant | 1 | 1 | not applicable |
| train-b | secant | 1 | 1 | not applicable |
| train-c | SVD ridge 10,000 | 0.9836520205 | 0.9462661927 | 0 / 241 |
| train-d | secant | 1 | 1 | not applicable |

Thus the sole learned outer selection has a better ungated loss but **no
range-eligible outer rows**. This does not establish an admitted out-of-case
runtime benefit. All four cases remain authored variations within one declared
development project. Case withholding does not create independent campaigns.

The separate original-record audit reconstructs all 114 training partitions,
sample hashes, feature means/scales/bounds and target scales, all 112 inner
scores, all four outer scores and every selection decision. It performs no
refits or structural solves. All 440 retained source/schema/test files match
Git at the numerical source revision; both copied input files match the prior
sealed SVD packet. Worker, parent and audit processes are absent before sealing.

Worker elapsed time is 11.131849 s, CPU 11.114559 s and peak RSS 342076 KiB.
The parent interval is 11.340961 s; input/source preparation precedes that
interval. Audit elapsed time is 3.989446 s, CPU 2.884229 s and peak RSS
2478668 KiB. Historical label generation, prior model investigations, selection
and future inference costs remain distinct; reusing labels does not erase their
cost. This shared-host observation does not establish exclusive hardware timing.

The final selection regression passed **40 tests in 77.58 s** before its source
commit, including actual material-learning paths. The initial test harness had
one duplicated keyword error, corrected before the passing run. Tests cover
outer-row perturbation invariance, complete case exclusion from inner/outer
fits, baseline retention, invalid input and fit-budget rejection, original-unit
history errors and interrupted-fit outcomes. Ruff, two-source mypy and diff
checks passed. These are local implementation checks.

The sealed packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-nested-selection-o06pikgv`
contains **913 files / 121854850 bytes**, inventory SHA-256
`27cd2d35345975735fc2c5ad73597a131052a581284e762532c48e0e6dfa7b64`.
All files are reread exactly; sealing takes 0.247718 s. The
[machine summary](rc-nested-selection-20260910.summary.json) retains costs,
selection outcomes, original identities and claim boundaries.

## Runtime cost correction and next observation

Source `6ea17e2fe1d3c60c4270d8e3d4f541a3488dcb4b` adds an explicit
`material_capture_scope="proposal-only"` benchmark option. Actual learning
evaluation uses this scope: the reference, secant and fresh reference avoid
extracting material feature inputs they do not consume. Training generation
retains all-arm capture where original material-state labels are required.
Default all-arm behavior and serialized identities remain unchanged.

The correction passes **33 tests in 83.90 s**, including exact capture counts
and actual retained-material learning paths; Ruff, two-source mypy and diff
checks pass. An earlier test handle was no longer available and no authoritative
result log could be recovered, so this is a separately logged confirmation run.

A frozen-policy runtime observation uses the original authored validation and
holdout inputs, four paths per case and 242 targets per path. It performs no
refitting, keeps fixed `1e-10` absolute / `1e-8` relative comparison tolerances,
and retains the existing abstention-to-reference behavior. Those reused cases
are development evaluations, not new blind experiments. The completed runtime record below supplies the terminal records and
separate original-record audit. Net learned savings,
public experiment/model correspondence, independent verification and the full
roadmap remain open.

The [completed frozen-policy runtime observation](rc-selected-runtime-20260910.md)
now retains all eight paths and their original-record audit. Fixed physical
comparisons pass, but validation remains slower than secant and OOD fully
abstains. This selection result is not promoted.
