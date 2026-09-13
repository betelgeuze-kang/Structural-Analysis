# Authored RC history streaming with constant preload

Numerical source `f8dcfbb6af25e95e3a550558b28db94f69d9c7bc` adds
[`stream_rc_fiber_control_history`](../../src/structural_analysis/api/rc_fiber_control_history.py).
The public Python iterator yields original compact JSON bytes: one request/source
header, an optional accepted constant-load preload, and one original lateral
attempt/response/checkpoint record at a time. It retains the accepted material
state across the complete authored history without accumulating all responses.

This complements the existing local [long-history file archive](rc-long-history-archive-20260910.md).
The stream uses the current public canonical compiler and shared constant-load
and original-transition recovery mechanisms. It accepts a declared budget up to
4,096 authored targets. The existing 255-target cumulative API, durable HTTP job
contracts and Workbench remain unchanged. The bound is not proof of every model's
capacity. This observation covers the two 1,010-target cases described below.

## Original prefix replay and work

Resume requires the original header and every original prefix record in order,
as bytes. The complete request, constants, solver configuration and compiled model
identity must match. The stream repeats the preload and prefix from genesis and
compares every newly generated record against its original bytes, including the
original solver attempt and recovered response. Recomputed public hashes alone
cannot authorize a changed response. Replayed records are emitted again so a new
consumer output can retain a self-contained history.

`report` is a detached, per-invocation work snapshot. It separately counts new,
replayed and preload calls, known Newton/linear work, unknown-work calls and
response reassemblies. Preload is a subtotal and must not be added again to the
new/replay total. Across multiple invocations, earlier paused/failed reports must
also be retained and counted. The six-process observation below does that.
A core cancellation preserves its original exception and counts the started call
with unavailable work. A response recovery or replay mismatch preserves completed
core work without advancing the last emitted accepted checkpoint. A failed
preload exposes its original attempt through the error report and performs no
lateral solve. A rejected lateral attempt emits the unchanged accepted state and
stops. There are no automatic retries, cutbacks or target substitutions.

A stream is `ready` only after exhaustion, including checking for extra prior
records. Calling the iterator's `close()` at a yield reports `paused`, even after
the last requested record if exhaustion has not yet been checked. Consumers own
record framing, persistence, fsync and handling earlier incomplete outputs;
`storage_durability_verified` remains false. Hashes do not authenticate the
implementation or grant physical/design/release authority.

For example, a caller can write a new authored stream without a cumulative list:

```python
from pathlib import Path
from structural_analysis.api.rc_fiber_control_history import stream_rc_fiber_control_history
from structural_analysis.io.neutral.loader import load_neutral_json

model = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
run = stream_rc_fiber_control_history(
    model, (-(i + 1) * 1e-8 for i in range(1010)),
    control_global_dof=4,
    constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
)
iterator = iter(run)
try:
    with Path("authored-history.ndjson").open("xb") as output:
        for record in iterator:
            output.write(record + b"\n")
finally:
    iterator.close()
print(run.report)
```

This is an authored cantilever example, not a reconstruction of U3 or ARISTA.
Repeated measured displacement observations remain observations; this API does
not drop them or reinterpret them as actuator commands. Constant preload and
long-history execution do not supply missing reinforcement, material laws,
actuator/load definitions, sensor positions, source reuse rights or campaign
independence. No external experiment is admitted to training here.

## Focused verification

The final four-file selection passes **130 tests in 49.38 s**, including 35 new
stream tests, the existing constant public path, local archive and request
transport. Tests cover actual cumulative/stream response and checkpoint equality
with and without constants, 300 constant-load targets paused after 255 lateral
steps, byte-exact replay, original-prefix tampering, missing/oversized/trailing
records, real failed preload, recovery failure, cancellation costs, actual
preloaded control origin, reversal budgets, source mutation and bounded target
iteration. Ruff check/format, one-source mypy and diff checks pass.

An earlier ad hoc call passed a string to a Path-only loader and stopped before
solving. The first test run stopped on an incorrect expected legacy checkpoint
field; the assertion was corrected to `final_checkpoint`. The intermediate
29-test passing selection overlaps the final 130 and is not added to it. Tests
ran on the working tree subsequently committed unchanged; they are focused local
checks, not full hosted acceptance or independent numerical validation.

## Fresh-process 1,010-target observation

The retained plan declares monotonic and reversing authored histories on the same
public cantilever, each with 1,010 targets and constant N2 axial load -600 kN.
Each case runs a full history, a separate 255-target prefix and a fresh-process
continuation that replays the preload plus all 255 earlier targets. They are two
load histories on one authored geometry, not independent experimental campaigns.

| Case | Phase | Parent seconds | Peak RSS KiB | Core calls |
| --- | --- | ---: | ---: | ---: |
| monotonic | full | 26.102 | 103788 | 1011 |
| monotonic | prefix | 7.721 | 103828 | 256 |
| monotonic | resume | 26.009 | 104168 | 1011 |
| cyclic | full | 25.991 | 103756 | 1011 |
| cyclic | prefix | 7.630 | 103764 | 256 |
| cyclic | resume | 25.896 | 103996 | 1011 |

All six processes terminate successfully. **2,024 original header/transition
record pairs** match exactly between full and resumed outputs; **514 prefix
record pairs** also match their full-run originals. This includes both preload
records, all 2,020 lateral responses, original attempts, material states and
terminal checkpoint identities. Every successful transition is reassembled by
the stream from the original solver coordinates and parent state.

Total observed numerical work is **4,556 core calls**, comprising six preloads
and 4,550 lateral calls, including prefix replays. The original counters report
**9,112 Newton iterations and linear solves**, with zero unknown-work attempts
in these six runs. There are 4,556 verified response reassemblies and zero fits.
The six parent-process intervals sum to **119.350 s**; that includes child
startup, input loading, iteration and output, but excludes source preparation,
coordinator comparison, tests, sealing, documentation and GitHub operations.
Nested child times must not be added again. Coordinator activity shared the host;
there is no isolated-hardware speed comparison or production latency claim.

All 428 tracked Python/schema files under `src/structural_analysis` match Git
before execution and their original hashes after execution. The retained packet includes these snapshots,
original model and targets, driver, process identities, six original streams and
reports. After all processes exit, **466 files / 211132385 bytes** are inventoried
and reread exactly at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-history-stream-m1el__kd`. Inventory SHA-256: `d6acfd47878e519a58f3f2dded3da2156d3585c1961b67ff309494f5c2d79464`.
The [machine summary](rc-constant-history-stream-20260910.summary.json) retains
individual counts, byte identities, times and remaining scope.

Public experimental reconstruction and admission, independent data splits,
learned benefit over deterministic baselines with full costs, paged durable/HTTP
and Workbench integration, broader physics, current hosted/independent
verification and the full roadmap remain open. This source observation supplies
no speedup, yielding-capacity qualification, independent physical validation,
design authority or release approval.
