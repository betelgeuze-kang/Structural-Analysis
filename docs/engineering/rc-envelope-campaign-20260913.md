# Frozen envelope-admission campaign — launched 2026-09-13

This launch record is historical. The worker later stopped on a progress-file
collision after one completed slot; the remaining eight slots continue separately.
See the [preserved failure and active continuation](rc-envelope-continuation-20260913.md).

Source `c72ff7b0012d1c4a4287bde82ec1a51dbc876fb2` adds an explicit experimental
admission rule: consult the existing seed policy only when the next prescribed
target exceeds the maximum absolute target in that arm's accepted prefix. Equality
and within-envelope targets abstain through the existing secant/reference fallback.
The policy's original model/range checks and solver acceptance remain authoritative.
The public solver and default policy behavior are unchanged.

This is a manual hypothesis selected after the train-b work diagnostic, not a
learned classifier or a policy with demonstrated speedup. It may remove useful
proposals as well as costly ones. Full-path replay is needed because changing an
earlier seed can change subsequent accepted coordinates and material history.

## Frozen protocol and cost scope

The campaign retains the original complete 242-target cyclic requests. Three
cases (`train-b`, `validation`, `holdout`) each run the prescribed orders:

1. reference, secant, gated proposal;
2. secant, gated proposal, reference;
3. gated proposal, reference, secant.

Every slot adds a fresh reference path after those three arms: nine slots, 36
planned full paths and 8,712 requested target steps if all paths finish without
additional retries. These are planned counts, not completed evidence.

Train-b uses its original withheld-case fit (`fit-0001-policy.json`). Validation
and holdout use the original integrated training policy. No new fit, label
generation, automatic promotion, tolerance relaxation or shortening of history is
authorized by this experiment. Model/request/policy bytes are checked against the
original sealed native-runtime inventory. All six original declarations pass the
existing split preflight; only the three scheduled cases execute numerical paths.
These are authored development cases, not authenticated external projects or a
blind independent campaign. Train-b is tuning evidence and cannot count as the
independent evaluation of a rule chosen from its outcomes.

The proposal identity binds both the original policy hash and envelope rule.
Dynamic abstention still incurs material capture already performed before the
callback. Capture is omitted only when the existing static model gate proves that
the policy will reject the entire model. Rule, inference, fallback, recovery,
numerical retry and artifact costs remain in the recorded path intervals; static
gate setup is charged separately to the proposal score. Original historical
training costs remain a separate required expense, not free training. The parent
worker interval includes its setup and file I/O; archive export and subsequent
auditing are excluded. BLAS/OMP/MKL use one thread with Haswell OpenBLAS; the host
is not isolated.

Each admission's `consult_policy` and the worker's `consult_policy_count` represent
envelope permission. They are not counts of actual policy calls when the static
model gate rejects a case. Final auditing must distinguish these from actual
proposals and fallback decisions. No observed proposal count or runtime result is
claimed in this launch record.

## Verification and active execution

Ruff, focused mypy and **55 focused tests passed**. New tests cover equality,
reversal across a new absolute maximum, invalid/Boolean/nonfinite targets, and an
actual complete control path with gated secant proposals and secant fallback.
That small integration test validates the mechanism; it does not test learned
benefit. The numerical campaign uses the full original long requests.

The frozen source, protocol, original inputs, worker and accumulating outputs are
at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-envelope-campaign-85bqovab`.
The owned unified execution handle is `83937`; worker PID `132647` was verified
live in `train-b-r0`, with empty stderr, after launch. This directory is actively
written and must not be sealed, edited or restarted merely because observation
times out. On continuation, poll that handle or inspect the same live process and
terminal outcome before deciding whether execution has stopped.

Completion requires all nine terminal outcomes, full-history comparisons, known
work, original-source/input/record audit, and appropriate case-separated cost
accounting. A failure retains its receipts and stops the worker without automatic
retry. Until those checks finish, this is **running, unverified numerical work**.
The overall roadmap, independent validation and learned net-benefit gates remain
open.
