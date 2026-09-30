# Preserve historical failure review after checkpoint progress — 2026-09-14

Base source `b3b94db26fe3c176941f9646fed3b374aea7bbc6` plus the sealed patch.
The actual service retained the right diagnostic, but Workbench compared its
restart binding with the job's current checkpoint. Once a later attempt produced
a checkpoint, a valid older diagnostic was rejected as `invalid`.

## Reproduction and correction

The fixture injects one first-attempt linear-backend outage. The real worker and
service fail attempt 1 and preserve its diagnostic. With the patch removed,
attempt 2 executes one step and saves a real checkpoint. Attempt 3 consumes that
checkpoint and succeeds using the unmodified request bytes. The first failure
started without a checkpoint; the current succeeded job has a non-null checkpoint.

Before the correction, the actual desktop browser test receives `invalid`
instead of `verified` for attempt 1. The stop-after-first-failure run records one
failure and one unrun mobile case; its original log and error context are retained.
No job-view status or checkpoint reference was fabricated for this reproduction.

The service already rebuilds each diagnostic against its immutable attempt
record, including the recorded historical checkpoint. The HTTP adapter now adds
two headers derived from those verified bytes: their SHA-256 and the original
restart checkpoint hash (`none` for a no-checkpoint origin). The body remains
byte-identical. Workbench checks both headers together against the body and uses
the historical checkpoint for that historical attempt. Current-attempt reads must
still match the current job checkpoint.

Both headers absent retain the old strict behavior. Partial headers, a wrong
body digest or a checkpoint that differs from the diagnostic reject. The
[HTTP contract](../durable-job-service.md) documents the additive headers. They
are assertions from the authenticated service transport, not independent
signatures or numerical authority. Tenant/attempt authorization, source/config
checks, diagnostic-only authority and accepted-result validation are unchanged.

## Verification and scope

- Backend durability and workflow contracts: **26 passed in 7.25 s**, including
  original-byte/hash-header checks and existing authorization denials.
- Pinned Node 24 production build, including TypeScript and delivery checks: pass.
- Fresh-build actual HTTP browser suites: **22 passed in 1.4 min**. The enclosing
  runner interval is 83.803203275 seconds, not complete research lifecycle cost.
- Desktop/mobile-width positive tests exercise real checkpoint progress; four
  transport-mutation tests preserve the current verified result while refusing
  missing, partial, wrong-digest and wrong-checkpoint historical bindings.
- Existing failure-diagnostic, previous-failure and successful-retry suites remain
  included. The old synthetic changed-checkpoint direct-validator test still
  rejects when no authenticated transport binding is supplied.
- Ruff and `git diff --check` pass. The new six-case browser spec is registered in
  actual HTTP CI; hosted execution of these changes remains pending.

This closes the reproduced local no-checkpoint-to-generated-checkpoint history
problem under controlled fault injection. It is not independent physical
validation, an observed production outage, or a complete matrix of all possible
restart histories. Browser views reuse fixture jobs; 22 tests are not 22
independent structures. No numerical method, tolerance or solver authority changes.

The [receipt](checkpoint-failure-history-20260914.json) binds the base source
archive, exact patched source, runner, before/after logs, fresh-build inventory,
diagnostic attachments and screenshots. The read-only packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-checkpoint-history-spirx9k5`:
29 files, 52885047 bytes. Adjacent `.inventory.json` SHA-256:
`90af8c995c78b7727eacfa3aa682d36f2f5aafacedbdd4cc7f80c0c563c3319b`.
Every file was reread for byte length/hash before sealing. Prior sealed packets
remain unchanged.
