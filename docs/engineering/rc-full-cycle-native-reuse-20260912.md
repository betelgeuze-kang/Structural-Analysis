# Native reuse on four complete 242-target cyclic histories

The [four-geometry prefix observation](rc-multicase-native-reuse-20260912.md) now has
a full-history counterpart: all four previously declared training models execute
their **original 242-target requests**, with two reversed execution orders.
All **7,744 baseline/reuse native step pairs are byte-identical**, all **48
within-benchmark full-history comparisons pass**, and every fresh reference is
exactly repeatable. Actual Newton assembly dispatches fall from **64,476 to
49,412**, or **23.36% fewer dispatches**. This is a deterministic opt-in
optimization; it provides no learned-policy benefit evidence.

## Scope, source and observed costs

The numerical base is published commit `e94cb85dde468085f05bb42cd4bac40070f9a65a`.
All **449 copied source/schema/test files** match their Git bytes before launch
and in the final record audit. The copied runner SHA-256 is
`b762d10cfcc4e8e813fe14a288ffb90e4b274e1c9e500f18b6dd0bc4f28c3e21`.
The worktree HEAD remains fixed for all child launches. No numerical source,
request, tolerance, model, policy or acceptance criterion changes during the
experiment. No concurrent owned test run is launched during timing; the host is
still not isolated from other activity.

The original secant-abstention inventory is checked before copying the four
`train` model/request pairs. Inputs are byte-for-byte unchanged, with no prefix
selection, resampling or added loading. Validation and holdout cases are not run.
The models remain four authored geometries in one L-frame family, not four
independent experimental campaigns or new structural families.

Each case executes off/on followed by on/off. Each benchmark contains reference,
secant, a **secant proposal** and a fresh reference. Retained twofold arithmetic
is fixed for every arm. The completed work is **16 benchmarks / 64 paths /
15,488 core calls / 69,984 inclusive Newton iterations and linear solves**.
The reuse optimization does not reduce the Newton count: per-strategy paired
counts are equal, and dispatch differences close exactly against reuse hits.
All four cases contain positive accepted steel plastic strain and concrete
tensile damage. Compressive damage appears in train-a and train-c. These are
internal model states, not observed physical validation.

| Case | Baseline dispatches | Reuse dispatches | Whole benchmark time ratio | Secant path time ratio |
| --- | --- | --- | --- | --- |
| train-a | 17,248 | 13,032 | 0.831813 | 0.869325 |
| train-b | 14,656 | 11,468 | 0.857725 | 0.899738 |
| train-c | 18,260 | 13,652 | 0.820224 | 0.856732 |
| train-d | 14,312 | 11,260 | 0.861744 | 0.909398 |

Ratios are reuse/baseline sums across the two orders of that case. Whole benchmark
time includes its path execution, recording, serialization and fresh-reference
verification. The secant path timer includes proposal work, numerical attempts,
recovery and step I/O, but **excludes final path-file writing**. Neither ratio is
a pure solver-kernel speed ratio. The per-strategy analysis is added after train-a
completed; the numerical protocol and pass criteria remain unchanged.

The secant path observations are approximately **9.1–14.3% lower elapsed time**,
while whole benchmark observations are approximately **13.8–18.0% lower**.
Reference paths benefit more than secant here; reporting only the blended
benchmark would overstate the observed benefit of the secant path. Two pairs on
a nonisolated host do not establish a general speedup, an independent confidence
interval, user-interface latency reduction, or learned net benefit.

## Completion and record audit

All four original children and the parent exit 0; process termination is checked
before auditing or running tests. The parent records **4958.769 s**
for sequential study execution, including child startup and pair comparisons.
Input/source preparation precedes that timer. This research cost is not credited
as an application speed saving.

The separate source/record audit takes **12.505 s**.
It verifies frozen source bytes, unchanged requests, two declared orders,
full-history gates, native record equality, actual work/dispatch accounting and
per-strategy counters/times. It executes **zero fits and zero Newton solves**.
This is an archive consistency audit, not an independent physical solver.
No measured training data is admitted; no learned policy is trained or promoted.
The earlier binary64 baseline failure remains unresolved and is not converted
into retained-arithmetic success or hidden by this experiment.

## CI diagnostics and qualification boundary

The numerical base's [hosted run 34691397679](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34691397679)
has **522 passes / 24 modules**, no errors/failures/skips, from downloaded JUnit.
The tested PR merge is `cb69a802f58e2d1ab17ec066aec5b93eec1c001b`.
Its 9,171-byte artifact SHA-256 is
`4be2fe22d67c0cf728bf8a3301af605a00830184cda635e46c2896a62cddccd0`.
The runner experiment module itself is not in that hosted development artifact;
its previously documented 24 local tests remain separate evidence.

All four full-suite shards fail during evidence materialization, skip actual
repository test execution and leave the full aggregate failed. The latest
shard-0 raw log names `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`; it does not expose enough
detail to confirm the individual latest metric mismatches.

After numerical execution and the record audit, the
[failed-materialization diagnostic upload](ci-materialization-diagnostics-20260912.md)
is implemented and **16 focused workflow tests pass in 0.45 s**. Ruff and diff
checks pass. This does not resolve the external comparison or qualification gate;
its new hosted upload still needs direct observation.

## Evidence and reproduction

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-full-cycle-reuse-3t8qdeb7`.
Adjacent inventory: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-full-cycle-reuse-3t8qdeb7.inventory.json`.
**93,573 files / 5,228,538,860 bytes**; inventory SHA-256:
`624a88a87b87ccc1510b56919e31a2fa1c767830181e5a52ec9d50fc9dfd2bcd`.
Do not mutate the packet. Exact counters, timing scopes and per-strategy
observations are in the [summary](rc-full-cycle-native-reuse-20260912.summary.json).

`protocol.json` records the four cases, all targets, orders and cost scope;
`source-manifest.json` binds executed sources; `run.py` preserves the launcher;
`*-started.json` records each exact child command; `completion.json` records exits;
`audit.py` and `audit.log` preserve the executed audit. `current-ci/` preserves the
base run's JUnit and failure evidence. `ci-final-source/` and
`ci-diagnostics-verification.json` distinguish the later workflow/test change
from the numerical source. Earlier progress and unapplied-proposal records remain
historical snapshots, not final-state assertions.

Reproduction requires a separate checkout at the numerical base and a **new
output directory**. The launcher records arithmetic/thread settings; installed
package versions were not separately snapshotted for this local run. Use the
preserved supplied models/requests, retained arithmetic and two repetitions with the copied runner;
its recorded CLI commands show the exact options. Reproduction is a new
experiment and must not overwrite these observations.

Next work remains direct observation of the CI diagnostic artifacts, resolution
of authoritative external comparison requirements, and learned-strategy
assessment against the measured deterministic baseline. This study does not
close independent physics, licensing, owner/administrator, hardware, broader
3D/material, or complete-roadmap requirements.
