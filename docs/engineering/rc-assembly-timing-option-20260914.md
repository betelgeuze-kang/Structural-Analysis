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
