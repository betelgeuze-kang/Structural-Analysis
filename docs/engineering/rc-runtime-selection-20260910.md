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

## Completed frozen observation

The fixed two-ridge grid now completes all eight withheld-training-case fits,
32 full paths and **7,744 numerical calls / 37,376 Newton iterations and linear
solves**. All 24 full-history comparisons pass; each reference/fresh-reference
pair has exact history and terminal-checkpoint bytes. All original target
sequences remain unchanged. No validation/holdout path executes and no label is
regenerated. The source snapshot's 439 files match Git
`664f128896dc08eeb3337264881fa2d869badc4e`.

| Ridge | Equal-case mean proposal/secant path-time ratio | Genuine proposal rows |
| --- | ---: | ---: |
| 10,000 | 1.328413 | 241 |
| 1,000,000 | 1.325443 | 241 |

Both candidates are slower under the declared score, so **secant remains
selected**. There is no selected learned ridge, final refit or promoted policy.
At both ridges only train-b has learned proposals; all other cases abstain to
the original reference path. Train-b is 12.26% and 12.37% slower than secant.
The [initial-iteration diagnostic](rc-first-iterate-diagnostic-20260910.md)
records the first candidate's additional iterations without claiming causality
from different parent states. These are single-run internal tuning observations
on a shared host, not repeated independent evaluation or amortized net savings.

## Original-record and arithmetic verification

A separate terminal-process audit reconstructs all eight training partitions,
train-only preprocessing arrays and policy identities. Its ridge-stationarity
check has maximum relative residual `6.829939e-15`; it performs no new fit.
It reconstructs 1,936 stored proposal decisions and their committed material
snapshots, checks all original step reservations/outcomes and parent chains,
reopens all 32 terminal native states, and recomputes all candidate scores and
the final selection.

The audit replays 7,744 accepted assemblies and responses with the frozen solver,
charging 650,496 material integrations separately. A separate rational-assembly
helper checks 7,744 assemblies, 46,464 sections and 15,488 members. Its 100-digit
material checks cover 650,496 stresses and preserve the native branch/state
results. These arithmetic implementations do not provide a new experiment,
external solver qualification or independent physical calibration. No Newton
path is rerun by the auditor.

The numerical parent takes 2,875.369819 s; the worker takes 2,875.134822 s through
reports, with 2,874.478499 s CPU and 369,100 KiB peak RSS. The auditor takes
1,113.018635 s internally, 1,111.231353 s CPU and 433,072 KiB peak RSS; its parent
interval is 1,113.278082 s. The supervisor's wait is separate and must not be
added again as numerical work. Original generation remains 2,904 calls / 13,815
Newton counts and 1,045.632469 s across its original generation paths, with the
other historical selection/research costs retained separately.

The adapted auditor's fold-file name was corrected during preparation to avoid
shadowing by inner step-file names. The retained deployed audit completes on its
first execution with exit zero. The earlier diagnostics, their original hashes,
auditor adaptation, all input/source inventories and process outcomes are kept.

All numerical and audit processes are terminal. The packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-runtime-selection-1blqipjy`
is sealed after rereading **47,071 files / 2,734,483,787 bytes** exactly. Inventory
SHA-256 is `4175ee8c66f8c51aa6fcceb38c2538e9c596cd4afbf0e6fe81e70c5293d2aaa2`.
See the [machine summary](rc-runtime-selection-20260910.summary.json) for the full
fold scores, cost records, arithmetic audit and seal. The pre-existing initial
live-state fields are historical snapshots, not current process status.

M3 learned net savings, external data/model correspondence, broader independent
solver verification, Workbench candidate-search integration and the full roadmap
remain incomplete. The negative candidate outcome is retained as evidence for
changing the learning strategy rather than promoting either tested ridge.
