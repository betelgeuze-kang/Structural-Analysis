# Persistent logical payload limits

`DurableJobService` accepts an optional operator configuration,
`max_blob_payload_bytes`. It must be an exact Python integer from 1 through
`2**63 - 1`. The configuration is separate from immutable job requests, solver
settings and HTTP input. For example, an application can initialize its existing
service with:

```python
service = DurableJobService(
    root,
    tenant_tokens=tenant_tokens,
    worker_tokens=worker_tokens,
    max_blob_payload_bytes=64 * 1024 * 1024,
)
```

The first explicit value is committed as a singleton SQLite policy before any
job transaction. Omitting the argument inherits that policy on reopen. A writer
opened before adoption also reads the persisted policy at its next admission.
An identical explicit value is accepted; a conflicting value is rejected. No
policy means unlimited logical payload storage. This interface does not resize
or remove an adopted policy. Adoption below existing usage preserves all bytes
and stops further growth.

Admission holds the existing `BEGIN IMMEDIATE` writer transaction while counting
real regular-file lengths under `blobs/sha256`. Referenced blobs, digest-named
orphans and crash-left `.job-blob-*` files all consume capacity. Symlinked,
unexpected, unreadable or special-file entries reject admission without cleanup.
Existing candidate blobs must pass their byte-length and hash checks. A distinct
missing digest is charged once, including when several roles share its bytes.
No-growth reuse remains allowed above the cap when inventory and candidate
integrity are valid.

Requests, recorded RC outcomes, checkpoints, failure diagnostics and completion
publication use this shared admission. Completion preflights the result/evidence
union before writing either role. The RC result repository precomputes and
admits the complete row/artifact/manifest union, including manifest bytes; its
existing tenant limit still counts referenced snapshot bytes. Predictable root
capacity denial declines optional repository caching without invalidating the
already completed analysis. Invalid inventory, policy or existing content remains
an explicit error. Artifact roles and reader bounds are checked before any
repository publication.

Worker authorization, request binding, reservation and semantic validation retain
their existing precedence. Lease time is refreshed after potentially slow
inventory and candidate-integrity checks. Later storage failure or lease expiry
can still leave admitted immutable bytes: the next writer counts them. Durable
checkpoint state, known outcomes and unknown pending reservations retain their
existing authority. Stored bytes and spent numerical reservations are not
refunded, and there is no automatic garbage collection.

| Storage error | HTTP status | Meaning |
| --- | --- | --- |
| `blob_payload_budget_exceeded` | 503 | Planned growth exceeds the persisted logical payload cap. |
| `blob_payload_inventory_invalid` | 503 | The payload namespace cannot be counted safely. |
| `blob_payload_policy_invalid` | 503 | Persisted policy is malformed. |

The HTTP error envelope and job schemas remain unchanged. Clients cannot set a
root cap in request or execution configuration. Reads and transitions that write
no blob continue to apply their normal authorization and state rules, including
heartbeat, cancellation, expired-lease recovery and failure without a diagnostic.

The limit covers cooperating current-source writers on the existing trusted,
single-host filesystem/SQLite profile. It counts logical payload lengths, not
database/WAL bytes, allocated blocks, directories, inode use, other output roots,
process memory or whole-job execution time. Old binaries and unmanaged writers
do not enforce this policy. Inventory adds work inside the writer transaction;
this feature does not establish a performance improvement or service release
qualification.

The pre-change storage baseline records public schema-valid request growth and
an injected file-fsync failure retaining a valid result orphan. That observation
is separate from quota enforcement tests, authored RC solver regressions,
independent experiment validation and hardware evidence.
