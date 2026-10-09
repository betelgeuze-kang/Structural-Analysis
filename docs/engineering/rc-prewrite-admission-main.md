# RC publication before-write admission

Checkpoint and completion publication validate job ownership, the active lease,
progress, request/result bindings, recorded invocations and pure RC contracts
before writing new artifact bytes. Validation and persistence hold the existing
SQLite writer transaction. The lease clock is read after acquiring that lock,
after validation, and after each artifact write before committing the transition.
Slow validation or storage must not authorize publication with an expired lease.

This adapts the existing `bc8a1897575723c9f4fc9e6a90f99fa634479139` implementation
to the current main service. Current checkpoint publication releases the lease;
the tests explicitly reclaim the checkpointed job before a continuation. This
does not introduce the donor branch's lease-retaining checkpoint mode or its
other job profiles. The synthetic admission fixtures prohibit numerical calls;
the separate actual RC worker suite checks solver-backed continuation.

Predictable rejection leaves the previous payload inventory and durable state
unchanged. Real I/O failure or lease expiry after a successful write may leave
immutable unreferenced bytes. Such bytes are preserved; this change provides no
garbage collection, storage quota or rollback of filesystem writes. The next
payload-budget integration must count these retained bytes and admit a complete
result/evidence union before its first write. SQLite/WAL, memory, inode usage and
cross-store activation need separate boundaries.

Tests cover rejection precedence, mutable-input snapshots, accepted reopen and
deduplication, corrupt existing artifacts, fsync failure, expiry during validation
or persistence, pending invocation accounting, and competing heartbeat/claim
transactions. These are software checks, not specimen or release qualification.
