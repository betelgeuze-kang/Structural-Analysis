# Constant-load RC durable chunks and preload-bound receipts

Source `5f73252c2fbe0c20ae1e8a504b498110fb15182b` connects the constant-load
[public API and CLI](rc-constant-load-public-path-20260910.md) to the existing
single-host durable service and dispatcher. This completes that transport slice,
not independent experimental validation or the complete Structural Analysis roadmap.

## Request, state and cost correspondence

The existing `structural-analysis-job-request.v3` envelope now accepts the v2
constant-load direct-control configuration when `result_contract` explicitly names
`bounded-rc-fiber-job-result.v2`. Proportional v1 configuration continues to require
its v1 result. JSON Schema and the pure Python decoder enforce the correspondence.
The request carries the same node-bound FX/FY/MZ constants in kN/kN m as the public
API. Both use one shared pattern resolver, including undeclared-node rejection.
The previous explicit durable rejection is replaced by actual v2 support.

Constant-load result and checkpoint wrappers use v2 schemas and
`bounded_rc_fiber_durable_chunk_execution.v2`. Its resume identity is separate from
the proportional profile. The service compiles and checks the connected model and
free translational control without numerical execution. Target-to-target reversal
checks remain at input; the initial direction depends on a real preload and is
checked by the worker against its accepted origin. A zero first target is therefore
valid when the preload has a nonzero control displacement, and is tested as such.

Each successful receipt binds both the preload-result hash and preload-checkpoint
state hash. All compact prefix receipts must bind the preload retained by the final
native restart. The cumulative API validator checks the original preload attempt,
its parent and accepted state, its solver metrics, its recovered response identity
and assembly hash. Lateral response epochs start at two. Rehashed alterations of
preload work, ancestry, response, earlier receipts and lateral epoch numbering reject.

Completed progress still counts lateral targets, excluding preload. The number of
core attempts for an API invocation is `completed lateral prefix + 1`: the worker
runs preload and the preceding prefix afresh before its new suffix. Its mandatory
verification performs a separate full source execution. Both are charged, and API
reservation counts remain distinct from core-attempt counts. Preload, prefix and
suffix work must sum to the reported total. Pure service validation makes no
additional solver calls and remains a structural check of trusted-worker records.

Failed preloads remain original invocation outcomes, including unknown Newton
counters. They produce no accepted progress or checkpoint. Budget exhaustion on a
later claim leaves the prior durable checkpoint reference and original bytes
unchanged and makes no extra numerical calls. This is verified against the reopened
service's failed job state and checkpoint readback.

## Proportionate tests

The final five-file public/durable selection passes **182 tests in 32.38 s**,
including **17 new constant-load durable tests**. The shared real fixture executes
both full and three-part paths; tampering tests reuse its results with numerical
calls forbidden. Existing proportional service/worker coverage still passes.
The two changed Python source modules pass mypy; Ruff and diff checks pass.
Initial review corrected one static `Any | None` annotation and ordinary test
formatting/unused-import issues. No numerical failure was repaired by changing
loads or tolerances.

The real fixture counts six preload and twelve lateral calls across the three
chunks, matching all six analysis/verification records. It compares the full
physical history and terminal native bytes against a separate one-chunk run.
Additional real tests cover failed preload, the nonzero preloaded origin and
reservation exhaustion. Caller revision fields in tests are declarations, not
proof of an independent source build.

## Separate fresh-process observation

A committed-source observation uses the authored public 3 m RC cantilever, constant
-600 kN axial force and three lateral targets `[-1e-5, -2e-5, 1e-5] m`. It launches
one process for the full job, three separate processes for successive durable
chunks, and one process for an intentionally nonconvergent -30,000 kN preload with
one allowed Newton iteration. Each process constructs its own service instance;
no live Python objects cross a chunk boundary.

| Path | API reservations | Actual preload calls | Actual lateral calls | Outcome |
| --- | ---: | ---: | ---: | --- |
| One full chunk | 2 | 2 | 6 | succeeded, 3 targets |
| Three reopened chunks | 6 | 6 | 12 | checkpointed at 1 and 2, then succeeded at 3 |
| Deliberately failed preload | 2 | 2 | 0 | failed, 0 targets and no checkpoint |

Full and split jobs have exactly matching preload responses, complete lateral
response histories, terminal responses, physical model bindings and native
terminal checkpoint bytes. Their requests, progress receipts, timings and complete
wrapper hashes are intentionally different; whole wrapper equality is not claimed.

The original invocation records count **28 core attempts**, **52 known Newton
iterations and 52 known linear solves**, and **two attempts with unknown counters**.
The two unknown attempts are the failed preload and its explicit verification.
Observed function-boundary call counts independently equal the attempt total.
There are 26 accepted calls and two retained failures, not 28 successful solves.
The coordinator handles the expected failed-job outcome, so its process exit zero
must not be interpreted as a successful structural job.

Per-call solver intervals, per-chunk worker intervals, original API/verification
timings and parent process times are retained in the
[machine summary](rc-constant-load-durable-20260910.summary.json) and original
invocation records. Worker intervals exclude interpreter/import startup and final
report writing, but include service, storage and export work. This single
instrumented shared-host observation proves no repeated speed benefit.

All **1,341 tracked Python/schema files** match Git before and after execution.
All five child processes and the observer finish before sealing the service stores,
original requests/checkpoints/results/evidence, logs and scripts at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-durable-cybslpqe`.
The packet contains **91 files / 3,374,612 bytes**, inventory SHA-256
`c08294d15c379c6adce9033bad84bb3eab8e1f11dc3fc2f8f9dc4a8acb01b535`.
Opening these service stores for additional work requires fresh copies; the sealed
originals must remain unchanged.

Workbench's current reader accepts the v1 result/restart layout and still needs v2
preload inspection and material-history integration. Execution-topology buffers,
long histories beyond the current 255-target scope, U3 source/model correspondence,
external corpus admission, licensing and independent experimental validation remain
open. Hosted acceptance and the complete roadmap are not closed by these local
results. No protected receipt or tolerance is promoted.
