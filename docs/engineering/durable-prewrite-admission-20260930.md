# Durable checkpoint and result admission before file storage

A rejected checkpoint or completion previously left new content-addressed files even though the job transition rolled back. The be89 baseline reproduces this with stable semantic errors, unchanged job/events/work records, and a larger blob inventory. This matters when invalid or stale worker publications repeat on a storage-constrained host.

## Publication order

The request and byte schemas, authentication, solver/native paths, invocation records and public HTTP interfaces remain unchanged. `save_checkpoint` and `complete_job` freeze caller bytes, retain media/size checks, then acquire the existing SQLite writer transaction. They validate the current tenant/worker/lease, progress, immutable request and native receipt contracts before calling `_put_blob`.

Checkpoint validation includes the existing Frame3D or RC prefix/budget checks and RC recorded invocation binding. Completion validation includes the requested result family, exact evidence artifact bindings, core authority, pure validation report and recorded invocation binding. After those checks, the service reads the clock again and checks the lease immediately before storage. It checks the lease again after every stored file, before publishing the database references.

The same writer transaction prevents a separate writer from taking over or changing progress between semantic admission and publication. WAL readers continue to see the last committed state. Validation and fsync now hold the writer lock for longer; this is a correctness tradeoff, not a throughput improvement or a numerical deadline policy.

## Rejection and failure boundaries

A deterministic admission rejection writes no checkpoint, result or evidence file. It preserves the previous verified checkpoint, job/event revisions, invocation outcomes, budget reservations and unknown work. Rejection does not repair or inspect an otherwise unreferenced submitted blob: admitted storage still uses the existing integrity, fsync, rename and dedup rules.

If validation consumes the remaining lease, the final prewrite check rejects without files. If the lease expires during a real file write, the following check rejects publication but the already renamed file may remain. Expiry during result storage stops the evidence write. Evidence-write or database-commit failures may also leave an unreferenced file; the service preserves the committed prefix and unknown reservations and does not silently delete these files.

This does not establish filesystem/SQLite failure atomicity, cumulative disk quota, process wall-time or memory limits. A same-progress checkpoint or completion with a finished lease remains rejected. Exact request retries retain their existing recovery, missing-blob repair and corruption checks.

## Verification boundary

New tests compare full blob path/byte inventory together with job/events, budget, recorded outcomes and pending reservations. Baseline failures are retained separately from corrected-source results. Lease races, expiry during pure validation and after actual fsync, I/O failure, byte snapshots, successful restart/downloads and existing legacy/Frame3D/RC worker paths are distinct checks. Synthetic service receipt fixtures exercise storage admission; they are not independent physical verification or new training evidence.

Whole affected service and worker files and actual authenticated desktop/mobile-emulated HTTP restart/download checks must pass on the final source before publication. Focused checks do not replace the exact-head hosted CI gates. Two-fixed RC durable jobs and unsupported learned v4 paths retain their existing boundaries. Independent experiment, AI net benefit, hardware and commercial release requirements remain open.
