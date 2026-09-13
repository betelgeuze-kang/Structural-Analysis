# Opted-in assembly timing in full control benchmarks

`benchmark_rc_control_seed_paths` now accepts `record_assembly_timing=True`
alongside `record_assembly_work=True`. Timing without work recording, or a
nonboolean option, is rejected before output creation. The option reaches all
benchmark arms, their constant-load preload and subsequent control steps. The
request identity explicitly records enabled timing. Defaults remain untimed.

`VectorAssemblyWorkRecorder(record_wall_time=True)` uses the monotonic nanosecond
clock around the original dispatch and status bookkeeping. Returned and raised
calls retain their durations; an in-flight snapshot has an unknown total. No
coordinate, return object, exception, tolerance or numerical solve is changed.
The count-record schema keeps its existing version with optional timing fields;
untimed calls and records retain their previous shape. Timing belongs to the
observational sidecar, not the numerical step identity.

The phase summarizer validates integer nonnegative durations, scope and exact
per-invocation totals. It publishes `phase_wall_ns` only when every invocation
has a complete timed record. Untimed, mixed, missing and in-flight observations
keep total phase times null. Failed completed dispatches still contribute their
observed cost without implying a successful path. Reuse hits remain distinct
from actual dispatches; they acquire no invented saved-time credit.

Intervals exclude recorder snapshot serialization and nonassembly work, including
linear solves and recovery outside the recorded dispatch. Enclosing arm/study
times include instrumentation and summary costs. They must not be added to the
phase sums. This does not make these observations equivalent to the earlier
external wrapper's slightly wider timing interval, measure timer overhead, or
establish acceleration.

## Verification

The Newton recorder, phase summary and actual control-path selection passed
51 tests in 40.42 s. Two additional controlled-clock cases passed in 1.56 s,
checking returned/raised durations and in-flight unknown totals. Actual paths
cover timed and untimed runs with/without constant preload and both ordinary
and retained arithmetic. Original numerical step bytes match the unrecorded
baseline. Malformed options, durations, inconsistent totals and incomplete
records are covered. Ruff and diff checks pass.

No policy uses these times as a reward by default. No new independent physical
validation, learned benefit, main integration or release acceptance is claimed.
Hosted verification of this local change remains pending.

## Runtime policy selection forwarding

`run_rc_control_runtime_selection` accepts the same optional
`record_assembly_timing=True` flag and requires explicit work recording before
training or output creation. Its fixed plan and result identify enabled timing;
all full-path benchmark arms receive the option. The existing elapsed-time
selection score includes the instrumentation cost. The score formula, training
folds, acceptance checks and default untimed behavior remain unchanged.

The focused runtime-selection suite passed 65 tests in 136.03 s. Its actual
counterbalanced repeated paths cover both ordinary and reused line-search
assembly, check phase durations against invocation sums and enclosing path
time, and retain full-history, fit-reuse and secant-selection checks. Invalid
timing options are rejected before output. Ruff and diff checks passed.

Separately, published source `c1eaa5d81db6c4b092421bdff8e467044b896a65`
completed Runtime Input and Viewer CI run `34784621141` with a failure:
705 browser tests passed and one priced design-comparison browser case failed
because the verified comparison panel was not found within 5 seconds. The
separate actual HTTP suite passed all 36 tests. The detailed failure was read
from artifact `10326641095` (`workbench-v2-e2e.log`); this observation does not
establish the cause or justify changing the timeout. This published run does
not verify the local timing implementation.

## Reuse experiment command

The existing `scripts/diagnose_rc_control_line_search_reuse.py` runner exposes
`--record-assembly-timing`. It forwards the option to both baseline and reuse
arms in every repetition and records enabled timing in the study summary.
Detailed phase durations remain in each benchmark's `comparison.json` and
its original invocation outcomes. The enclosing comparison includes timer
cost; dispatch durations cannot be interpreted as total user-time savings.
Without the flag, existing runs remain untimed.

For a new, nonexistent output directory, append the flag to the existing
small, yielded-prefix or supplied-model command, for example:

```sh
PYTHONPATH=src python3 scripts/diagnose_rc_control_line_search_reuse.py \
  /tmp/rc-reuse-timed-new-study --case small --arithmetic binary64 \
  --repetitions 2 --record-assembly-timing
```

The runner continues to refuse existing output directories and requires an
even repetition count. Supplied models retain the supplied full request;
the timing option does not alter targets, preload or arithmetic selection.

The reuse-runner suite passes 28 tests in 31.84 seconds. Actual supplied-input
paths cover timed and untimed retained arithmetic, both execution orders,
constant preload, exact baseline/reuse step bytes and recorded phase totals.
Nonboolean timing rejects before output. The CLI help exposes the flag;
Ruff and diff checks pass. This does not establish learned benefit or speedup.
