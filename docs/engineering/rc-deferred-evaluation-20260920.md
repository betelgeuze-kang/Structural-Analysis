# Defer evaluation until training-only runtime selection is frozen

`run_rc_control_learning_study(..., defer_evaluation=True)` now permits original
training-label generation and the initial fit without executing validation or
holdout solver paths. The existing default remains immediate evaluation after
fitting. All cases still undergo the existing input, physical identity, measured
source, geometry and history split preflight before output creation or fitting.
Deferral does not disable any split screen or change solver acceptance criteria.

The plan and final report explicitly record `evaluation_deferred: true`. Each
reserved case retains a `not_attempted` outcome with reason
`evaluation_explicitly_deferred`, no evaluation-start receipt and no result path.
Zero evaluation work means zero attempted solver work, not successful validation.
The report still records label-generation and fit costs. No assertion is made
that callers never inspected these cases outside this invocation.

This addresses a workflow gap: the original label study previously always ran
its initial fitted policy on the evaluation cases before callers could perform
training-only runtime selection. Existing historical runs retain that chronology;
they are not retrospectively called untouched evaluation.

## Predeclared next experiment

`scripts/run_grouped_rc_runtime_campaign.py` defines three synthetic L-frame
training geometries and two reserved validation/holdout geometries. Each uses a
12-target reversal path, with peak prescribed displacements of 5–8 mm and a
constant 20 kN vertical load at N3. It uses the existing RC materials, 12 concrete
layers and terminal polishing with retained-twofold-refinement arithmetic.

The training-only selector excludes complete connected groups, compares ridge
values 10,000 and 1,000,000, and runs three counterbalanced repetitions per
withheld case/ridge. Selection requires the existing full comparisons, actual
proposals and at least 1% improvement; otherwise secant remains selected. The
selection budget allows seven fits including a possible final refit, and 1,368
core calls. Label-generation work is additional and retained separately. Fold
ratios exclude label/fit costs and are not a net-benefit claim.

Preflight identified that the initially drafted reserved length pair (3.6, 2.7)
was a scaled copy of training geometry (2.0, 1.5); the existing screen rejected it.
Before any numerical execution, that reserved pair was changed to (3.6, 2.9).
The final preflight confirms three singleton training groups and five total
cases with no solver calls. Scenario names do not authenticate independent
projects. Repeated timings on one host are not independent physical cases.

The runner must execute from a verified committed source snapshot, retain its
plan before label generation, and preserve failures. Reserved cases remain
unexecuted throughout this campaign, including after strategy selection. Any
later evaluation requires its own frozen protocol and full cost accounting.

## Verification

Across the learning and runtime-selection modules, 111 distinct checks passed
across the focused runs. The first full invocation retained an already-imported
version of one new test that incorrectly used `dataclasses.replace` on a class
with a custom constructor; that test failed before calling production code.
The corrected explicit-constructor test and the separately selected existing
full-path test both passed (2 tests, 33.50 s); the remaining full invocation
passed 109 tests in 277.71 s. Five other new deferral checks also passed in the
initial focused run. These counts are not added as independent test cases.

Actual deferred label generation produced a policy and only training-case solver
calls, with zero evaluation calls and explicit retained outcomes for both reserved
splits. The existing connected-group runtime regression now consumes deferred
labels, excludes all samples of the withheld group and passes all full-path
comparisons. Invalid deferral types and cross-split overlap fail before output.
Ruff and diff checks pass. No external dataset or experimental holdout was used.

## First campaign outcome and protocol amendment

The frozen `5d254fe14baba8978a327e81651564ade4c8a7c1` campaign terminated with
`training_failed`, preserving 45 known core calls and 277 Newton/linear solves.
Train A completed all 12 targets for reference, secant and fresh reference with
passing full-history comparisons. Train B/C completed preload but stopped at
`post_preload_preflight`. No fit or runtime selection ran; both reserved cases
retained zero evaluation calls. The process is terminal, not an unobserved live run.

Stored preload responses explain the refusal: N3 UY is approximately -0.2145,
-0.7173 and -1.6930 mm for A/B/C respectively. Moving to the first -0.5 mm target
adds a reversal for B/C before the declared cyclic path. The original request
allowed three reversals, whereas the actual preloaded-origin paths need four.
This is a protocol budget error, not failed Newton convergence.

The v2 campaign explicitly links the original failed plan and permits four
reversals while retaining all coordinates, targets, materials, loads, regression
choices, repeat counts and numerical acceptance tolerances. Original outcomes
remain under `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-grouped-runtime-kqrx7nnx`.
Any amended measurement is a new campaign and must not erase the initial cost.
