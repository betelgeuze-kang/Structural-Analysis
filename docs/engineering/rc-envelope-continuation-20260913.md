# Envelope campaign orchestration recovery — 2026-09-13

The original worker terminated with exit 1 after completing `train-b-r0`. The
failure was `FileExistsError` when it tried to write `active-slot.json` a second
time through the write-once `_save` helper. The second slot had not entered its
numerical benchmark. Its composition/static-gate setup files were written, but
no `train-b-r1` numerical directory existed. This is an orchestration failure,
not a failed equilibrium path or a reason to relax verification.

The first slot records four complete paths, 968 core calls, 4,069 inclusive Newton
iterations/linear solves, 49 proposals, 193 abstentions, and full-history comparison
pass. Its recorded proposal/secant path ratio is 1.022057311198266. These are the
worker's completed records; independent record/response reconstruction is still
pending. One tuning-case order does not establish a speed benefit or a general
result. The failed parent consumed 269.484319911 s; that expense must remain in
total campaign accounting rather than being erased when execution resumes.

## Preservation and correction

The terminated original packet was inventoried and made read-only:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-envelope-campaign-85bqovab`.
It contains 6,706 files / 387,751,565 bytes; inventory SHA-256
`fbf3903510a533a3074a487c671e7a377e036a0ecd201534d0aafd6a282d382f`.
The traceback, partial aggregate, completed numerical records and second-slot
setup costs are preserved. The stale `active-slot.json` is historical and cannot
be treated as proof that the old worker is still running.

The continuation uses immutable `<slot>-started.json` and `<slot>-outcome.json`
records, followed by a single final aggregate write. The actual worker loop was
executed with numerical/policy doubles through all eight remaining slots: unique
records and final aggregate were produced, and a second aggregate write was still
rejected. This checks the orchestration fix; it is not a physical or timing test.

The solver source remains `c72ff7b0012d1c4a4287bde82ec1a51dbc876fb2`, with a
source manifest identical to the original run. Policy/model/request inputs and
the frozen envelope rule remain unchanged. The completed first slot is carried
by its original report hash and **is not rerun**. Only the eight numerically
unstarted slots execute in the continuation, preserving the original nine-slot
protocol and keeping the orchestration failure visible.

## Active continuation

The new owned packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-envelope-resume-f0nrbjdg`.
Unified execution handle `38993`, worker PID `133979`, was verified live in
`train-b-r1` with empty stderr. Poll this handle on continuation; old handle
`83937` is terminal. Per-slot started/outcome records replace the old mutable
progress pointer. The active packet must remain unsealed while the worker writes.

Eight remaining slots plan 32 full paths / 7,744 target steps, in addition to the
first completed slot. They are planned counts until terminal records and audits
prove otherwise. Validation and holdout are still required; no incomplete case
is removed from the denominator. A final audit must reconstruct the source/input
bindings, decisions, whole histories, work and case-specific costs across **both**
packets and include the failed parent interval. The overall objective and all
independent-validation/net-benefit gates remain active and unclosed.

See the [machine-readable continuation binding](rc-envelope-continuation-20260913.summary.json).
