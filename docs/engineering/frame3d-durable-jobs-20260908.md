# Bounded Frame3D durable jobs

The existing single-host SQLite/content-addressed job service now accepts the
experimental ModelIR Frame3D direct-control path. Progress counts completed
authored targets, and a job-wide solve-attempt reservation survives worker
restarts, lease expiry, checkpoint continuation and failed-job resume. The
numerical solver and the candidate API remain the existing implementation.

The original v1 2D job request, generic v1 job view, result/evidence HTTP routes,
and default checkpoint lease release remain supported. New workers should use
`execution.job_worker.execute_job_claim` when claiming from a mixed queue; the
older 2D-only worker cannot execute a 3D claim.

## Request and execution

The exact `structural-analysis-job-request.v2` request has these fields:

| Field | Meaning |
| --- | --- |
| `operation` | `bounded_frame3d_direct_control` |
| `case_id` | Stable caller-selected identifier |
| `model` | Complete bounded ModelIR v2 document |
| `config` | Existing `bounded-frame3d-direct-control-request.v1` object |
| `source_revision` | Full lowercase Git SHA or `sha256:` identity, declared by the caller |
| `result_contract` | `bounded-frame3d-job-result.v1` |

The portable configuration includes the complete ordered target list. The
service validates the typed model/configuration without executing a solve.
Submission remains immutable, tenant-scoped and idempotency-key bound.
Source revision is a declaration, not source attestation.

For a configured service and worker identity:

```python
from structural_analysis.execution.job_worker import execute_job_claim

claim = service.claim_next(
    worker_id=worker_id, authorization_token=worker_token, lease_seconds=300,
)
if claim is not None:
    job = execute_job_claim(
        service, claim, worker_id=worker_id, authorization_token=worker_token,
        checkpoint_target_budget=2, lease_seconds=300,
    )
```

For 3D, a target budget limits newly completed authored targets in this claim.
Omit it to run the remaining path. A partial budget returns `checkpointed`;
another process can open the same service root, claim the job and continue.
Intermediate target boundaries within one claim commit while retaining the
lease. The final target publishes the complete result/evidence pair atomically.
The lease is checked before execution and again before checkpoint/result
publication. Heartbeats run between attempts; a single numerical attempt is
not interruptible and must fit the chosen lease to publish its result. Expired
workers cannot publish, and a supervisor can recover their prior checkpoint.

## Checkpoints, receipts and budget

A `bounded-frame3d-job-checkpoint.v1` wrapper binds the immutable full request,
authored target cursor, ordered prefix of per-target receipts, and exact raw API
checkpoint bytes. Each receipt retains the original one-target API result,
its actual request hash, restart-byte identity, target, source identity and
durable reservation ordinals. The wrapper never rewrites a suffix result as
though the API had executed the full job request in one invocation.

Only successful authored target boundaries are durable. A failed target may
have accepted internal cutback substeps; those interior artifacts do not
replace the last completed authored boundary. Monotonic progress comes from
the wrapper cursor, not the raw checkpoint epoch. Cyclic progress is also
checked against the core cumulative target/reversal and rolling-chain bindings.

Before every actual target solve attempt, the service atomically reserves one
ordinal against the original `maximum_path_solve_attempts`. Adaptive retries
also reserve attempts. The solver configuration is unchanged across chunks,
so its exact resume hash remains valid. Reservations remain consumed after a
crash or failed resume. A process can die after reserving and before solving;
therefore reserved attempts are a conservative upper bound, not an exact count
of completed numerical work. Exhaustion prevents another attempt even when a
new claim or process is created. SQLite budget projection, immutable limit and
reservation events are checked for agreement.

The final `bounded-frame3d-job-result.v1` retains all completed receipts and
the exact terminal raw artifact. Its validator rechecks the nested candidate
API contracts, full request/source/target bindings, checkpoint linkage,
reservation accounting and the last durable receipt prefix. Completion evidence
must contain that exact validation report. The existing outer evidence
`checkpoint_hash` still means the last durable checkpoint stored in the job
row; the separate terminal artifact belongs to the final result wrapper.

## Verification and limits

Focused local checks passed in separate runs:

- Final existing/new service regression: **67 passed in 55.68s**. The 57 new
  service cases prohibit actual solver entry and cover typed submission,
  authorization, HTTP views, global reservations, lease expiry/lock delay,
  resume, budget/event tampering and mutable checkpoint snapshot integrity.
- Actual Frame3D worker integration: **21 passed in 158.99s**, with **11 actual
  target-step calls**: ten across shared monotonic/cyclic full and split fixtures,
  plus one in the exhausted-budget case. The group checks exact terminal bytes,
  multi-target claims, rehashed cursor/source/artifact/authority/proof rejection,
  HTTP result/evidence bytes, exact report numeric types and stale-lease refusal.
  The separate blocked-result persistence test explicitly uses a synthetic API
  stub; it is not evidence of physical nonconvergence.
- Attempt-hook ordering: **4 passed in 3.19s**, zero actual Newton steps. A
  rejected reservation propagates unchanged before the next step or retry.
- Existing service/CLI/fresh-process regression: **69 passed in 104.43s**. Its
  ten existing service tests overlap the final 67-case service run; the other
  groups are 54 CLI tests and five existing persisted-process tests.
- CI ownership/quality-gate contracts: **34 passed in 0.41s**. All three new test
  files are included in the core Python and PR quality-gate inventories.

Changed Python files passed Ruff, compileall and whitespace checks. Some
correctness groups ran concurrently; these durations are not performance
evidence. A separate clean-source reproduction of actual process loss and
reopening is still pending at this implementation checkpoint.

These are local orchestration and internal consistency contracts. All nested
candidate authority fields remain unchanged: public registry and Workbench
execution are false, external V&V is zero, and independent-operator, design,
formal Level 2 and release authority are absent. Result hashes are unsigned.
The existing Workbench engineering-result parser does not yet consume this new
wrapper; read-only 3D presentation and browser integration remain follow-up
work. Running-target cancellation, a remote worker protocol for reservations,
production identity/deployment, distributed recovery, independent numerical
validation and performance claims are outside this implementation's evidence.
