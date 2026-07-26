# Durable job service and exact checkpoint resume

PR 17 adds a bounded, single-host execution service for the public
corotational nonlinear-frame path. It persists orchestration state without
becoming a source of solver truth.

## Authority boundary

The service owns only job lifecycle, authorization, immutable artifact storage,
and event integrity. `structural_analysis_core` remains the solver-truth owner.
A job can enter `succeeded` only when a trusted worker supplies both:

- a result implementing the immutable request's
  `unified-nonlinear-frame-result.v1` contract; and
- a `structural-analysis-job-completion-evidence.v1` envelope bound to the
  exact job, request hash, optional checkpoint hash, result artifact hash, and a
  passing core validation report.

Workbench displays the read-only `structural-analysis-job-view.v1` projection.
It verifies the byte length and SHA-256 of a published result/evidence pair when
Web Crypto is available. Job `succeeded` means only that the pair was published;
it is never converted into convergence, engineering acceptance, design-code
compliance, or release readiness.

## Persistence and state machine

`DurableJobService` uses SQLite in WAL mode with `synchronous=FULL` for
cross-process transactions on one shared filesystem host. Requests,
checkpoints, results, and evidence are immutable content-addressed blobs. Each
state transition appends a canonical SHA-256-linked event and updates a
revision-checked projection in the same transaction.

```text
queued ──claim──> running ──checkpoint──> checkpointed ──claim──> running
  │                 │  │                                      │
  └──cancelled      │  ├──validated result+evidence──> succeeded
                    │  └──non-retriable error────────> failed
                    └──expired lease──> queued/checkpointed

failed ──tenant retry with exact observed hashes──> queued/checkpointed
```

Worker leases are time bounded. The raw lease token is returned once to the
authorized worker and only a domain-separated digest is stored. An expired or
superseded lease cannot checkpoint, complete, fail, or renew the job.

Submission idempotency is tenant scoped and request bound. Reusing a key with
the exact request returns the original job; reusing it for different request
bytes fails with `idempotency_conflict`.

## Exact resume

`advance_nonlinear_frame_checkpoint(...)` advances only a bounded prefix of the
configured control path. It publishes no engineering result. Its resume hash
binds the canonical model, compiler and problem contracts, full load or
displacement-control target sequence, tolerances, iteration limit, and matrix
backend.

On resume, the worker:

1. verifies the persisted request artifact hash;
2. reconstructs the same canonical model and configuration;
3. recomputes and compares the resume-contract hash;
4. passes the exact checkpoint bytes to the public nonlinear API;
5. relies on that API's genesis, ancestry, target-prefix, and deterministic
   replay checks; and
6. publishes only after `validate_nonlinear_frame_result(...)` passes.

Focused verification restarts a service from the same SQLite/blob directory at
step 2 of 4, resumes the remaining two steps, and compares terminal checkpoint,
node, reaction, member, section, and fiber outputs with an uninterrupted solve.

## HTTP and application boundary

`DurableJobHttpApi` is a deterministic transport adapter. Tenant routes require
both `Authorization: Bearer ...` and `X-Structural-Tenant`; worker routes require
an authorized worker bearer credential and enforce its tenant allow-list.
`DurableJobWSGIApplication` makes the adapter mountable without adding a web
framework dependency. The composition root is
[`apps/worker/job_service_app.py`](../apps/worker/job_service_app.py).

Principal routes are:

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/v1/jobs` | idempotent immutable submission |
| `GET` | `/v1/jobs/{job_id}` | Workbench-safe job projection |
| `GET` | `/v1/jobs/{job_id}/result` | published result bytes |
| `GET` | `/v1/jobs/{job_id}/evidence` | published completion evidence |
| `POST` | `/v1/jobs/{job_id}/resume` | exact-hash retry of a failed job |
| `POST` | `/v1/jobs/{job_id}/cancel` | cancel an unleased job |
| `POST` | `/v1/worker/claims` | acquire a time-bounded lease |
| `POST` | `/v1/worker/jobs/{job_id}/{operation}` | heartbeat, checkpoint, complete, or fail |

HTTP responses use `no-store` and `nosniff`. Stable errors omit credentials,
raw platform errors, filesystem paths, and solver internals.

## Verification

```bash
PYTHONPATH=src python -m pytest -q tests/test_durable_job_service.py
PYTHONPATH=/tmp/structural-analysis-quality-tools:src \
  python -m mypy src/structural_analysis/execution
npm run build
```

The focused tests cover idempotency conflicts, tenant isolation, worker scopes,
lease expiry and stale-token rejection, service-instance reopen, partial
checkpoint/resume, uninterrupted-path equivalence, optimistic retry hashes,
completion-evidence binding, blob tamper detection, event-chain validation, HTTP
authorization, and the Workbench-safe projection schema.

## Explicit limitations

- This is one SQLite/WAL database and one shared filesystem host. It is not a
  distributed queue or consensus system.
- TLS termination, secret management, identity issuance, backups, retention,
  quotas, monitoring, and process supervision are deployment responsibilities.
- Result/evidence signatures and a signed engineering review package remain
  separate P2 gates.
- External Level 2 and published Level 3 V&V are not created by a successful
  job.
- No job state can promote release authority, and no AI policy can acquire a
  worker lease through this contract without a separately authorized identity.
