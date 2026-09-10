# Preserve secant when a control correction policy abstains

Implementation `3d4ecef4b737703717522ef385bdc6004eba56e1` adds an explicit
`proposal_abstention_strategy="secant"` option to the experimental RC control
benchmark and whole-case runtime selector. When a policy returns `None`, this
option uses the current arm's accepted-history secant estimate if available.
At the first target, or a repeated accepted target that cannot define a secant,
it uses the original reference initialization. The historical default remains
`"reference"`, and old numerical observations retain their original meaning.

This addresses a confound in the [previous runtime experiment](rc-runtime-selection-20260910.md):
when the learned policy abstained, its path used ordinary reference initialization,
while its comparison baseline used secant. The observed cost included both input
capture/inference overhead and that initialization difference. The new option
makes it possible to measure the cost of consulting a policy while preserving
the deterministic baseline on abstention. It does not prove that the learned
correction itself is beneficial.

Invalid/nonfinite proposals and inference exceptions still use the original
reference initialization. A numerically rejected seeded trial retains its original
failure/work record, requires exact rollback and retries ordinary Newton once.
No residual, increment, equilibrium, material, recovery or full-history criterion
is relaxed. Proposal-only material capture, feature extraction, policy parsing,
inference and intermediate I/O are still charged to the proposal arm; this change
does not make those costs disappear.

The input/comparison identity records the nondefault option. The selector's plan
and result record the option independently of the learned weight hash, and each
proposal entry distinguishes a learned proposal, abstention to secant, abstention
to reference and invalid proposal. Its abstention total includes both valid
fallback choices. A policy weight file alone does not identify this run strategy.

The selector's worst-case core-call reservation is also corrected. Both secant
and proposal arms can retry a failed seeded target, so reference + secant +
proposal + fresh reference require up to **six calls per target**, plus four
constant-preload calls when applicable. The old five-call bound omitted secant's
possible retry. A request that funds only that old bound now rejects before any
fit or output creation. Actual completed work is still counted from invocations.

## Completed focused checks

- 59 runtime-selection and warm-start tests pass in 58.86 s.
- 33 original-record audit, constant-load and twofold-terminal tests pass in 15.87 s.
- Ruff, the two modified benchmark modules' mypy check and `git diff --check` pass.

An actual small-path test forces all policies to abstain, then verifies that the
secant and proposal paths have identical initial estimates, complete response
histories and terminal checkpoints. It also checks that material-capture cost
remains exclusive to the proposal arm. This forced-abstention test verifies the
mechanism, not a trained speed advantage. Invalid inference and numerical rollback
are exercised in both abstention modes; the existing public API artifact bytes
remain unchanged.

The first run was 53 passed / 5 failed in 58.52 s. New tests used a wrong report
filename and tried to read detailed checkpoint fields from summary reports.
They were corrected to read original `path.json` files. The initial `ruff` shell
entry point was unavailable; `python3 -m ruff` succeeded. Final test logs are
retained in the observation packet below.

## Full experiment launched; results pending

The new worker runs from a verified copy of **445 Git-bound source/schema/test
files** at the implementation revision. Original models, full requests, policy
metadata and **964 original training rows** are copied only after checking their
sealed inventories. No validation or holdout path is executed and no new
structural label is generated.

The frozen experiment repeats the existing two-ridge grid (`10,000`, `1,000,000`)
with each of four authored training cases withheld from its fit. Each fold runs
reference, secant, the opted-in proposal strategy and a fresh reference over all
**242 targets**. Planned work is eight fits / 32 paths, nominally 7,744 core calls;
the corrected worst-case reservation is 11,616 calls. One possible final fit is
reserved only if a candidate beats the fixed improvement threshold. No policy
is automatically promoted. These are internal tuning cases, not independent
experimental campaigns or repeated hardware measurements.

The packet is currently unsealed:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-secant-abstention-fhn1qvyq`.
Its `protocol.json`, source manifest, launcher and original source inventories
record the executable plan. Original numerical parent/worker PIDs are 1073200 /
1073676; audit supervisor PID is 1073983. These are launch-time identities and
must be checked against live process state before any continuation decision.
A timeout is not permission to restart numerical work.

The supervisor waits for both original numerical processes to terminate
successfully, then launches one original-record audit. That audit reconstructs
all fit partitions, preprocessing, ridge stationarity, actual proposal/abstention
choices, full native state histories, costs and final selection. Its adaptation
from the prior sealed auditor is hash-bound. It performs no fitting or Newton
paths, but its material/assembly replays have their own recorded cost. Audit
execution and success are pending; a configured supervisor is not a passing audit.

The previous fallback experiment's timings remain historical context, not a
same-source repeated causal comparison. Current learned advantage, total net
savings, original-record audit completion, independent families, external-data
admission and full-roadmap closure remain unproved. Results must be reported
only after the original execution and its audit are checked.
