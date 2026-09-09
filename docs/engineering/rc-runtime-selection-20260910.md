# Complete-path runtime selection within the original training cases

Source `664f128896dc08eeb3337264881fa2d869badc4e` implements
`run_rc_control_runtime_selection`. The preceding
[frozen selected-policy observation](rc-selected-runtime-20260910.md) reduced
its same-parent scaled seed error while increasing Newton iterations and path
time. Correction MSE therefore cannot establish the requested cost reduction.
This new selector evaluates candidate policies using the original solver's
complete withheld-training-case paths and their measured costs.

For each declared ridge, each training case is removed in full before fitting.
All preprocessing and weights come from the remaining original training rows.
The excluded case then runs independent reference, secant, proposal and fresh
reference paths. Its complete original target sequence and constant preload,
when present, are retained. Material feature capture is charged only to the
proposal path. Existing model/range abstention, numerical retry, state rollback
and fixed `1e-10` absolute / `1e-8` relative comparison rules remain in force.

Selection uses the equal-case mean of proposal/secant whole-path wall ratios.
Every comparison must pass and every invocation must have known work. A candidate
must actually propose at least once and improve the score by more than the
declared margin. Exact learned-score ties favor the greater ridge. Otherwise
secant remains selected and no final policy is manufactured. A successful
development candidate is refitted on all original training rows; it still needs
separate frozen evaluation, repetition and full training-cost accounting.

The path timing includes input extraction, inference, numerical calls and retries,
response recovery and step artifact I/O. Final path-file writes are outside those
individual path timers but inside the separately measured complete benchmark
and enclosing study times. Fit costs and the original label-generation costs
remain separate. A selected runtime candidate does not itself prove amortized
net savings, independent validation or readiness for promotion.

## Input binding and bounded execution

The existing project/geometry/history and measured-source leakage screens run
before fitting. Only cases originally declared `train` may be executed or fitted
in this selector. Validation and holdout cases enter preflight but their response
histories are not executed, read or used for selection. Whole-case exclusion
within an authored training project is explicitly internal tuning, not an
independent campaign split.

The original sample order and hashes must match the source policy. Each sample
is also checked against its supplied compiled model, solver configuration,
arithmetic, target index and accepted target prefix. Features are reconstructed
from that context, material inputs must bind the recorded native parent hash,
and the correction must match the accepted source coordinates minus its secant
seed. These consistency checks do not authenticate an absent original step file;
the source observation and its original-record audit remain required provenance.

Fit and core-call budgets are checked before output creation or fitting. The core
bound includes all four complete paths, one possible extra proposal call at every
target and every constant preload. Each fit and fold has a persisted reservation
before execution. Exceptions and interrupts preserve unfinished or unknown work;
unknown numerical work prevents continuation to another candidate. No automatic
retry of a failed observation, hidden label regeneration or policy promotion is
introduced.

## Focused verification

The final selection passes **25 tests in 36.71 s**, plus Ruff, one-source mypy
and diff checks. Its actual retained-arithmetic fixture runs four folds and
16 full paths, including initial constant loading: **80 numerical core calls**
with all physical comparisons passing. Original training generation is separate
fixture work. Tests verify that only training models execute, whole-case hashes
are excluded from their fitted policies, material input costs occur only on the
proposal arm, and constant preload work is counted.

Injected timing tests verify that measured cost determines selection, that slow,
failed, abstaining and threshold-tied candidates retain secant, and that final
refitting includes all original training rows. They also verify exclusion under
withheld-label perturbations, model/request/parent/coordinate consistency,
budget rejection before fitting/output, and accurate exception/interruption
reservations. Injected timing values are test controls, not performance evidence.

The first fixture was rejected by the existing conservative resampled-history
prefix screen before fitting. That screen was preserved; the fixture now has
distinct reversal shapes. Its initial log is retained. An earlier overlapping
22-test run passed in 36.87 s before the additional source-consistency checks.
The 964 original material-learning rows then pass a separate real-input preflight
against all four training models with no fit or structural solve.

## Frozen observation in progress

The source snapshot contains 439 source/schema/test files matching Git.
The original models, requests, 964 training rows and source policy are copied
only after verification against their sealed inventories. The declared grid
is **10,000 and 1,000,000**: the earlier training-only loss-selected ridge and
a more strongly shrunk candidate. This is a new runtime-tuning comparison, not
reuse of validation results for selection.

The plan contains **eight folds / 32 complete paths / 242 targets per path**,
with 7,744 nominal core calls and a 9,680-call bound including possible numerical
proposal retries. There are eight fold fits and at most one final selected refit.
The 1% selection margin, arithmetic, comparisons and arm order are frozen before
execution. Original label generation remains 2,904 core calls and 13,815
Newton/linear counts, with 1,045.632469 s across its recorded generation paths;
its other costs remain in the preceding source records.

The active packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-runtime-selection-1blqipjy`.
The original driver is retained as `run.py`, with `protocol.json`, the source
manifest, original input identities, tests and live fit/fold reservations.
It is **not sealed or a completed result**. The initial worker PID is `992787`
and parent PID `992334`; these identify the observed run, not proof that it is
still live at a later time. Check the original process/session and terminal
records before continuing. Do not restart merely because an observation times out.

The [machine status](rc-runtime-selection-20260910.summary.json) records the
observed state. No completed candidate score, speedup, final policy or independent
verification is claimed while it runs. The result must be audited against original
states, costs, fitted partitions and source bytes before a decision is reported.
M3 net savings, public experiment/model correspondence, wider independent solver
verification, Workbench/candidate integration and the full roadmap remain open.
