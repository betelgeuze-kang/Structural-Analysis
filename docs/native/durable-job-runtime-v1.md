# Bounded Durable Job Runtime v1

## Closed profile

This slice reaches C5 only for the tracked single-host serial-FP64 CPU nonlinear-NDTHA request.
Rust `structural-runtime` owns the durable state machine and artifact custody; C++ remains the
numerical owner through ABI v1.5. The implemented states are `queued`, `running`, `checkpointed`,
`succeeded`, `failed`, and `cancelled`.

Every transition is a canonical full-state JSON event in a contiguous append-only revision chain.
Each event binds the prior event hash and its own SHA-256. Requests, checkpoints, ResultIR,
ReportIR, and report source are immutable content-addressed blobs. A process-wide filesystem lock
serializes local mutations and is released by the operating system if a process exits. Worker
leases store only a hash of a random token; an expired lease is reconciled to `queued`,
`checkpointed`, or `cancelled` before the next claim.

Event time is monotonic per job: a caller clock regression is clamped to the latest committed
timestamp, and each new lease expires relative to that committed transition time. Revision and
hash-chain order, rather than wall-clock uniqueness, define the authoritative event sequence.

Completion does not trust worker-provided result bytes. The runtime restores the supplied terminal
checkpoint through C++, regenerates ResultIR and ReportIR, and requires exact byte equality before
publishing the terminal event. A corrupt event chain or blob fails closed. Interrupted create-new
temporary names are ignored as uncommitted state, while committed revision gaps are rejected.

## Public local workflow

~~~bash
structural-cli job submit request.json --store jobs --idempotency-key case-1
structural-cli job poll JOB_ID --store jobs
structural-cli job work-once --store jobs --worker-id worker-1 --step-budget 2
structural-cli job work-once --store jobs --worker-id worker-2
structural-cli job export JOB_ID --store jobs --output-dir result
structural-cli job cancel JOB_ID --store jobs
structural-cli job recover --store jobs
~~~

`work-once` claims at most one job. An active solve publishes its validated checkpoint and releases
the lease; another process can claim and resume it. A terminal solve atomically binds the terminal
checkpoint, ResultIR, ReportIR, and Markdown source. Export creates a new directory and never
overwrites an existing destination. Its self-hashed receipt binds the terminal event and all four
artifacts.

The clean-environment CLI test removes the entire child environment, including `PATH`, and starts
each lifecycle action as a separate process. A two-step checkpoint/restart export is byte-identical
to the direct synchronous checkpoint, ResultIR, ReportIR, and report source. Focused runtime tests
also cover idempotency conflict, concurrent claim with one winner, stale-token rejection, process
reopen after lease expiry, cancellation acknowledgement, interrupted temporary files, corrupt blob
failure atomicity, and forged report rejection.

## Authority boundary

This is a local filesystem queue, not a multi-tenant service. It does not provide identity,
authorization, tenant isolation, general network/API compatibility, distributed consensus,
distributed worker claims, remote object storage, or release authority. Only the bounded CPU
NDTHA profile is executable. A separate C5 slice now exposes this exact store through a loopback,
single-tenant, static-role HTTP API; it does not broaden the durable runtime claim. HIP C2,
additional solver families, broader service/API migration, Workbench integration, and C6 Python removal
remain open. See `docs/native/job-service-api-v1.md`.
