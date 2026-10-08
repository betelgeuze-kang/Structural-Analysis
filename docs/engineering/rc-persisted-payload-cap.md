# Durable RC retained-payload policy

Operators can configure `DurableJobService(max_blob_payload_bytes=...)` with an
exact positive signed 64-bit integer. The first supplied limit is persisted in
SQLite independently of subsequent job transactions. Reopening without a limit
inherits it; supplying a different value rejects. Already-open cooperating
writers reread the policy under each writer transaction. HTTP clients cannot
override this operator policy in a job request.

Under the existing SQLite writer lock, admission counts actual regular-file
lengths under `blobs/sha256`, including digest-named orphans and crash-left
temporary payload files. Invalid, symlinked, special or unreadable entries reject
admission without cleanup. Existing candidate blobs must match their hash and
length. Missing distinct digests consume new capacity once. Valid no-growth
reuse is permitted even if a newly adopted cap is below the existing usage.

Every current service payload path participates: requests, RC invocation
outcomes, checkpoints, completion result/evidence, and quantity reports. The
result/evidence union is admitted before either write. A rejected report revision
preserves numerical state and older revisions. Slow inventory or dedup reads are
followed by a fresh lease check before worker publication. Later I/O failure or
expiry can leave admitted bytes; subsequent writers count them. Neither bytes
nor numerical reservations are refunded.

Capacity, inventory and persisted-policy failures return HTTP 503 while normal
authorization, idempotency, schema and lease errors retain their precedence.
Reads and transitions that require no new payload remain available. The SQLite
connection setup retries only BUSY under one 30-second monotonic deadline and
closes unsuccessful connections, allowing concurrent first policy adoption.

The supported backup preserves this database policy. Recovery tests cover
immutable limits and spent reservations, and an actual child-worker test covers
checkpoint backup, original-process SIGKILL/reaping, restored-process resume,
terminal report generation and second-backup reopen under the inherited cap.
The original worker must still be stopped before activating the restored copy.
The policy is not cross-store writer fencing.

The supported boundary is cooperating current-version writers on a trusted,
single-host filesystem. This caps retained logical payload lengths, not allocated
disk blocks, SQLite/WAL, directories/inodes, backup destinations, process memory,
CPU time or unmanaged/older writers. It does not reserve future result capacity
before computation, so a later storage rejection can consume numerical budget.
Inventory traversal occurs inside the writer lock; no performance gain is claimed.

This integrates the existing donor payload policy from
`b420885d9cf51b1192c2911740fec41ba6d058ac`, WAL setup from
`e212f2eafb110a50ac99407ed6e074d611608022`, and PR573's backup implementation.
The donor's result repository and failure-diagnostic service are absent from this
main lineage and are not added. Their tests are not counted as current coverage.
Current quantity-report persistence is explicitly included. These tests establish
software boundaries, not physical validation or release readiness.
