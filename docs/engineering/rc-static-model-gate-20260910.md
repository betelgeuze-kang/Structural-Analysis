# Omit material capture only after a proved static policy rejection

Source `6885cd7af8c24b2bf8f2dde753ce38f8ba2a4439` adds an explicit
`static_model_abstention=True` option to `run_rc_control_runtime_selection`.
It implements the one-way rejection identified by the
[static-input diagnostic](rc-static-abstention-diagnostic-20260910.md).
The option defaults to false and currently requires the material feature profile,
whose immutable model prefix is known. Other feature profiles are not silently
interpreted with that prefix.

For each fitted policy and fixed model, the selector checks the original static
feature bounds once, before executing any of that fold's paths. The policy's
margin, numerical range comparison, model/context identity and ordered feature
names are unchanged. A model that fails this necessary condition can never pass
the policy's later complete-vector condition. Only that proved rejection skips
committed material capture and `policy.propose` for the fold. It still executes
the explicit abstention strategy: reference, or secant when available with
reference otherwise. The numerical solver and accepted-result authority remain
unchanged.

No static violation grants permission to propose. The full context, dynamic
feature, material snapshot and finite-value checks still execute in that case.
If range arithmetic overflows, the gate records `not_proved` and preserves the
ordinary path. Invalid typed inputs or mismatched model/feature profiles reject;
they are not treated as successful predictions. The optimization intentionally
omits the redundant material-capture validation and serialization for a proved
abstention; it does not claim to have executed those omitted checks. Existing
numerical validation, rollback, original outputs and fresh-reference comparison
remain in place.

## Identity and cost accounting

The enabled plan/result records the option. Each fold saves a hashed
`rc-material-static-model-gate.v1` record binding policy, immutable model-feature
hash, problem/context, arithmetic/profile and the violated coordinates/bounds.
The fold outcome links its gate hash and records gate wall/CPU cost. The policy
weight file alone does not identify this execution strategy.

Gate calculation **and gate-record writing** are timed before the benchmark.
The selector adds that cost to the proposal path time for its comparison score,
while retaining the original path-only time separately. Failed or unknown paths
still have a null speed ratio. The complete outer study timer also includes fits,
all paths, comparisons and intermediate reporting. Final report writes and prior
label-generation costs keep their existing separate scope. No cost is subtracted
from an observed path or substituted with a guessed saving.

An abstaining candidate with no actual learned proposals remains ineligible for
a final learned refit, even if timing noise made its ratio look favorable. Both
seeded arms' possible retries remain in the conservative core-call reservation.
When the option is disabled, the new option/gate fields are absent and the
existing capture, inference and scoring behavior is preserved.

## Verification

The full runtime-selection test module passes **40 tests in 67.06 s**. After
adding checks of the original per-step files, the two relevant actual-path tests
pass again in **35.23 s** (38 other tests deselected). These two tests overlap the
40-test selection; they are not 42 independent tests. Ruff, formatting, scoped
mypy and diff checks pass.

The actual-path checks exercise both reference and secant abstention. They make
capture/inference calls fail the test if reached after a proved rejection. Full
response histories and terminal checkpoints are identical to the chosen baseline;
**20 pairs of original step files**, including constant preloads, are byte-equal.
Those 40 original files are retained in the observation packet. Other tests cover
non-granting static passes, missing/out-of-range dynamic inputs, context mismatch,
overflow, unresolved-gate fallback, explicit boolean options, charged setup cost,
and failed-path ineligibility. Synthetic timing values test score accounting only.

A separate, non-solving observation loads the eight actual policies from the
previous sealed diagnostic and reconstructs their original model features. All
original violated coordinates are reproduced: **six rejected folds and two
not-rejected folds**. Six original case declarations undergo existing preflight;
only four training models receive gate evaluations, with no validation/holdout
path execution. It generates no label, fit or Newton solve. The complete
observation takes 0.918561542 s internally; individual gate calls take about
2.21–2.24 ms, excluding gate-record writing in this observer. These figures are
not a measurement of saved nonlinear runtime.

## Evidence and remaining work

[Machine summary](rc-static-model-gate-20260910.summary.json) binds code, policy
records, gate outcomes and test scope. The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-static-model-gate-cwc8wzwi`:
79 files / 11,322,290 bytes, sibling inventory SHA-256
`d2c51bb0cda648c6dcd51be50d409e682c8df4ddcfb7b59fa83f72605e5d87ac`.
Input/policy bytes match their original bindings; imported project source hashes
match Git 6885cd7af. All retained files are reread and hash-checked.

The [completed 32-path study](rc-secant-abstention-20260910.md) predates this option.
It remains valid evidence for secant abstention, not an experiment with this
optimization enabled. No new 32-path speed measurement or learned benefit is
claimed here. The active learned paths' additional iterations remain unresolved;
removing known-abstention overhead does not establish useful learned initial
values, independent generalization, external physical validation or release
qualification.
