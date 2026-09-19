# Nonlinear grouped warm-start runtime campaign: secant retained

The frozen-source campaign at `3793d49ff656b8b98843f920651fc1e10568bec7`
completed all 18 predeclared folds: three distinct synthetic geometry/history
groups × two ridge values × three counterbalanced repetitions. Every fold's full
history comparison passed. **No learned correction was proposed**, and secant
remains selected. No reserved validation or holdout solver path was executed.

| Ridge | Equal-case mean proposed-path / secant time | Actual learned proposals | Selection |
| --- | ---: | ---: | --- |
| 10,000 | 1.008555 | 0 | Not eligible |
| 1,000,000 | 1.006389 | 0 | Not eligible |

These are ratios for the complete proposal/fallback path including input capture,
range checks, numerical attempts, recovery and intermediate I/O. They exclude
label generation and fitting. They are not net-benefit ratios. Small ratios below
one in some repetitions cannot establish learned acceleration when no learned
proposal was used. No full-training winning-policy refit or promotion occurred.

## Physical scope and group exclusion

Three L-frame training models have horizontal/vertical lengths (2.0, 1.5),
(3.0, 2.5) and (4.0, 3.1) m. Each uses 12 prescribed displacement targets, different
reversal amplitude ratios, the same supported RC material laws, 12 concrete
layers, and a constant 20 kN vertical force at N3. The existing small-displacement
formulation, numerical tolerances and full-response acceptance remain unchanged.
This is internal same-engine nonlinear evidence, not physical validation or a
material-field convergence demonstration.

Original label generation completed nine reference/secant/fresh-reference paths,
producing 33 noninitial training pairs. Maximum reference material histories were:

| Case | Tensile damage | Compressive damage | Steel accumulated plastic strain |
| --- | ---: | ---: | ---: |
| A | 0.9986799412 | 0 | 0.00007878050 |
| B | 0.9716118491 | 0 | 0 |
| C | 0.9040842619 | 0 | 0 |

Every fold policy's stored training-sample hashes exactly match the complement
of the complete excluded group. Six fold fits completed, each with 22 original
samples. The three repeated runs reuse that fit and are not independent cases.
Declared scenario IDs are not authenticated independent project provenance.

## Why no policy was selected

The immutable geometry range gate rejected A and C in all 12 corresponding folds.
B passed that necessary gate in six folds but abstained on every target. The first
target has insufficient accepted history; all 11 later targets violate 4–14
material/history feature ranges. A post-hoc audit of the actual stored proposal
contexts confirms this for the first repetition of each fitted policy.

For example, at B's -3 mm target, a concrete energy-density feature is
`1.0670515064e-5 MJ/m³`, compared with training high `9.7600214713e-6` and allowed
slack `1.7480547382e-7`. Other energy-history features lie above or below their
training ranges. This is not evidence that widening a threshold is safe. The
existing thresholds were retained. Geometry interpolation alone did not provide
coverage of the accepted material histories.

The practical next experiment needs better **training-history coverage within
separate geometry groups**, or a separately versioned representation with its
own comparisons. Reusing the reserved outputs to select that experiment would
spend the evaluation boundary; those solver outputs remain unobserved here.

## Full observed cost and original failure

| Phase | Known core calls | Newton iterations / linear solves | Recorded parent wall time |
| --- | ---: | ---: | ---: |
| Initial failed-protocol label study | 45 | 277 | 20.478 s |
| Amended label generation + initial fit | 117 | 634 | 44.495 s |
| Amended runtime selection, 72 paths + 6 fits | 936 | 4,932 | 335.713 s |

The amended campaign's enclosing wall time is 380.270 s before final outcome
write. Initial failure work is retained separately: total known work across both
attempts is 1,098 core calls and 5,843 Newton iterations/linear solves. Later
inventory hashing and post-hoc audits are outside these execution clocks.
Single-process repetitions used `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`
on one shared host; no dedicated-host or hardware-general speed claim is made.

The initial protocol stopped B/C after preload because its three-reversal budget
did not include the reversal from the preloaded displacement to the first target.
The amended protocol permits four reversals and links the original failed plan.
An exact comparison confirms that all five case models, target values and other
request fields, ridge choices, repetition counts, budgets and arithmetic settings
are otherwise unchanged. See [protocol and tests](rc-deferred-evaluation-20260920.md).

## Preserved evidence

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-grouped-runtime-v2-lcuta7ac`.
All 465 frozen source files match both their SHA-256 manifest and exact Git blobs.
The terminal packet inventory covers 7,122 files / 368,855,118 bytes, excluding
regenerable `__pycache__` directories; its SHA-256 is
`52001663e39f2bc9dec58dfa252ab95d3aa46aa9a995b1bae1ffe677f441a33e`.

[Audited summary](rc-grouped-runtime-campaign-20260920.summary.json) and
[range diagnostics](rc-grouped-runtime-abstention-20260920.summary.json) preserve
case repeats, counts, costs and feature violations. The standalone auditors
perform no fits or solver calls. Their receipt/identity checks do not replace
independent replay, provenance or physical validation.
