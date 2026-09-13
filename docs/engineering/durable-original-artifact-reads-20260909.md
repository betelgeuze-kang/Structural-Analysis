# Original durable artifacts and browser readiness

Tenant-authenticated `GET /v1/jobs/{id}/request` and
`GET /v1/jobs/{id}/checkpoint` now return the exact stored original bytes. This
provides the missing input/restart reads needed by RC Workbench integration.
`DurableJobService.read_request` and `read_checkpoint` expose the same behavior
to local callers. Existing result and evidence reads remain completion-gated.

Requests are readable throughout the job lifecycle. Checkpoints expose only the
last attached artifact and remain readable after a failed or cancelled attempt.
Missing checkpoints return the existing `artifact_not_published` error; no empty
or reconstructed checkpoint is fabricated. Authentication and tenant ownership
precede blob access, and the existing 16 MiB request / 128 MiB checkpoint limits,
regular-file checks and exact length/hash validation remain enforced.

The HTTP adapter also binds the returned bytes to the job reference it read.
If a checkpoint advances between those two reads, it returns HTTP 409
`artifact_reference_changed`, requiring a fresh job view instead of combining
new bytes with an old reference. These routes are reads, accept no request body
and expose no worker lease token. They do not grant any additional numerical or
engineering authority.

## Focused verification

- **29 original-artifact tests pass, 10 deselected, in 2.21 s.** Coverage includes
  lifecycle states, the exact RC v3 request, opaque checkpoint byte preservation,
  tenant isolation, corruption/missing files/symlinks, bounds before file reads,
  unsupported route mutations and a real checkpoint-advance race.
- **65 existing RC service tests pass in 8.11 s.** These cover retained outcomes,
  budgets and existing result/evidence transport; they execute no solver.
- A complete copy of the earlier real RC split-job store is opened with the new
  service. Its request (6,073 bytes), checkpoint (118,859 bytes), result
  (65,680,274 bytes) and evidence (2,314 bytes) all return HTTP 200 with the exact
  previously retained bytes and media types. Its service integrity check passes.
  Analysis/replay entry points are guarded against calls; **zero numerical calls**
  occur. The sealed source store is not reopened or modified. This is an
  authenticated in-process adapter check, not a network or browser identity bridge.

The tests use synthetic v1 checkpoint bytes only for transport mechanics; they
do not present those bytes as solver evidence. The separate retained RC store
check uses actual original numerical artifacts without creating new numerical
evidence or resetting their costs.

## Asynchronous browser readiness

The preceding hosted `962c302` frontend failure waited five seconds for a mobile
Frame3D verified panel. At `aeeb22cb7`, a frontend lane instead passes 406/407 and
times out waiting five seconds for the extended-sparse invalid-artifact panel.
Those logs establish the readiness assertion failures, not a complete diagnosis
of hosted browser timing or a product integrity failure.

Both browser suites now use a shared helper that waits for artifact loading and
validation to reach their first terminal state. It immediately checks that state
and exposes its diagnostic when unexpected. Only this asynchronous boundary
receives a larger bounded wait; physical values, hash/download checks and normal
UI assertions keep their existing requirements. No production provider, UI or
validation gate is loosened.

The focused build and browser command passes TypeScript, the Vite build, viewer
delivery and **11 browser tests in 36.3 s** on pinned Node 24.20.0. Desktop/mobile
Frame3D and extended-sparse review and tampering cases pass. Two additional cases
hold a result response for 5.5 seconds and verify that no physical table/download
appears while loading, followed by the correct valid or invalid outcome. These
are intentional transport-delay tests, not performance measurements. Hosted
acceptance on the next commit remains pending.

Ruff, formatting and diff checks pass. Source copies are taken after testing;
this follow-up is not a frozen-source numerical observation. Logs, browser images,
source copies and the copied real store are sealed at
`/tmp/structural-original-artifacts.2jotn60w`: **28 files / 165,381,428 bytes**,
inventory SHA-256
`e2ae9730d1f71da0c423e08eb2a5fba7e8541557419e3cccfe7b4c27463bfad1`.
A fresh process rechecks the full inventory. The
[machine summary](durable-original-artifact-reads-20260909.summary.json) retains
the exact bytes, source identities and scope.

The current `aeeb22cb7` snapshot has 57 successful, 12 failed, five skipped and
two running checks; it is not final. License materialization remains blocked,
and hosted frontend/type acceptance is not inferred from local verification.
RC-specific parsing, authenticated Workbench configuration, response/material
history display, study integration and larger transport qualification remain.
The full roadmap and independent/licensing/hardware/owner dependencies stay open.
