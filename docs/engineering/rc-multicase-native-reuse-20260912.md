# Native assembly reuse across four declared geometry prefixes

The [native reuse implementation](rc-native-assembly-reuse-20260912.md) preserves
all paired native step bytes in four previously authored training geometries.
Actual Newton assembly dispatches fall from **5,728 to 4,212** (1,516 one-use hits,
**26.47% fewer dispatches**). This is a deterministic optimization observation;
no policy is learned or credited with an advantage.

## Frozen scope and execution

Numerical source is copied and verified against published base
`34fa0ff127954fab9b7bce602a2887b6e63128b0`. The runner extension accepts an explicit model/request
pair, decodes the request before creating output, and executes its targets and
constant preload unchanged. Supplying only one path or using the wrong case mode
is rejected. Existing small/yielded-prefix modes remain available.

Input models and full requests come from the sealed secant-abstention study.
Their bytes are checked against its inventory before copying. All four `train`
cases are selected before execution; validation and holdout inputs are not run.
The sole request transformation takes the **first 16 of 242 targets**; all other
request fields stay equal. These are monotonic prefixes, with no unloading or
reversal. They are four geometries in the same authored L-frame family, not four
independent experiments or new structure families.

Each case uses retained twofold arithmetic and two predeclared orders: off/on,
then on/off. Each benchmark executes reference, secant, a secant proposal, and a
fresh reference. This yields **16 benchmarks, 64 paths, 1,024 core calls**, and
**5,656 inclusive Newton iterations/linear solves**. All **48 within-benchmark
full-prefix history comparisons pass**, and all **512 paired native step records
are byte-identical**. The fresh reference and terminal/material observations
retain their existing requirements. No tolerance or acceptance rule changes.

| Case | Member lengths, m | Last target, m | Baseline dispatches | Reuse dispatches | Reduction |
| --- | --- | --- | --- | --- | --- |
| train-a | 2.0 / 1.5 | -0.0064 | 1620 | 1184 | 26.91% |
| train-b | 3.0 / 2.5 | -0.0064 | 1260 | 932 | 26.03% |
| train-c | 1.75 / 2.5 | -0.00576 | 1580 | 1164 | 26.33% |
| train-d | 3.25 / 1.25 | -0.00704 | 1268 | 932 | 26.50% |

Accepted material records contain positive concrete tensile damage in all four
cases. Accumulated steel plastic strain is positive in train-a and train-c,
with maxima approximately 0.0001008044 and 0.0003487162; it remains zero in
train-b and train-d. These are recorded internal model states, not measured
physical validation. The tested prefix does not cover the full cyclic response.

## Timing and evidence limits

Elapsed time includes the whole benchmark: numerical work, serialization,
recording and its fresh-reference verification. Source/input preparation and the
later record audit are separate. Observed pooled reuse/baseline ratios by case
are 0.792680, 0.813655, 0.797982 and 0.812328. **The final 24-test rerun overlapped
part of train-a**, so its timing is not acceleration evidence. The other cases
have only two order-balanced pairs on a nonisolated host. No pooled cohort speedup,
independent generalization, full 242-target speedup, learned net benefit or
release qualification is claimed.

The source/record audit takes 1.973 seconds,
checks published numerical source bytes, prefix transformations, native record
pairs, full-history gates and actual dispatch/work totals. It performs zero
fits and zero Newton solves. It is an archive consistency check, not an
independent physical solver validation. No measured training rows are admitted.

The only post-launch runner edit corrects the summary's constant-load label to
reflect the supplied request. All four study inputs have no constant preload;
their executed behavior and labels are unchanged. Both executed and final
runner/test sources are preserved. The executed base SHA alone is not an
attestation for the uncommitted runner extension; use its source manifest.

## Verification and CI

The focused runner suite passes **24 tests in 18.85 seconds**, including real
native off/on execution with a supplied preload and rejection of unpaired
inputs. An initial collection error used pytest's reserved parameter `request`;
renaming it fixed collection before the study. Ruff and `git diff --check` pass.

Published base `34fa0ff` has a successful independent development
job in [run 34690570776](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34690570776):
**522 passes, zero failures/errors/skips, 24 modules**, from the downloaded JUnit
artifact. The tested PR merge is `775ccd942a5ced349cd6938a41d83db99620e809`.
Artifact 10297213396 is 9,209 bytes with SHA-256
`11acabfc89c8d7b298d8ea834888bff7f944557a3011f266343c0ce9fa4ca166`. This hosted run precedes the new runner extension.
All four full-suite shards fail at `Materialize exact current-source test evidence`
and skip actual repository test execution; the full aggregate fails. These
statuses do not diagnose the latest preparation failure's underlying cause.

## Retained packet and reproduction

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-multicase-reuse-l_6nkxwz`.
Inventory: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-multicase-reuse-l_6nkxwz.inventory.json`.
**6,754 files / 328,742,459 bytes**, inventory SHA-256
`fd8b10ab49ecb820552a0fdd22c7d95dfb410b5911f4877a5ddb2f1f2543391b`. Do not mutate the sealed
packet. The adjacent [summary](rc-multicase-native-reuse-20260912.summary.json)
contains exact counters, per-case timings and evidence identities.

`protocol.json` fixes cases, transformations, arithmetic, orders and cost scope;
`run.py` records original intake and serial execution. `original-inputs/` keeps
full source requests, `inputs/` keeps executed prefixes, `source/` keeps executed
code, and `final-source/` keeps the label correction. Each case's `*-started.json`
records its exact command. To reproduce, use the saved source with its supplied
model and request in a **new** output directory, retained arithmetic and two
repetitions. The runner refuses an existing destination. Repetition is a new
experiment, never a replacement for these observations.

Next scope remains full declared cyclic histories and independent structural
cases, with separately assessed learned benefit. The [durable job integration](rc-job-native-reuse-20260912.md)
continues to require the same source verification when reuse is enabled.

The subsequent [complete cyclic study](rc-full-cycle-native-reuse-20260912.md)
executes all 242 targets for the same four authored geometries, with separate
whole-benchmark and secant-path cost accounting.
