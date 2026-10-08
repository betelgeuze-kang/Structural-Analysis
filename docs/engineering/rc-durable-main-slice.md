# Bounded RC durable worker on original main numerical code

This slice depends on the separately reviewed control/checkpoint and RC API
slices. It adds one durable RC operation to the existing single-host SQLite
service. Existing planar jobs remain supported. It does not introduce Frame3D
jobs, constant preload, pin-roller/two-fixed profiles, phase subprocess policies,
twofold/rational arithmetic, material changes, price reports or Workbench UI.

## Source extraction

The original RC worker, request/result/checkpoint contract and invocation
custody code originate from `962c302c33d83da7349c9e5871f02fa4fe272549`.
They are adapted onto main, not copied with that commit's other dependencies:

- Retain main's generic service, with RC-only request validation, immutable
  invocation budgets, outcome custody and checkpoint/result verification
- Exclude all Frame3D operation branches and request/worker imports
- Use the predecessor's solver-free strict JSON helper
- Reject unavailable `terminal_polishing` in the v3 schema, matching the API
- Keep main's existing release-on-checkpoint behavior; the worker does not
  request a new retain-lease mode
- Add a dispatcher for existing planar and RC operations only

No existing numerical source is modified. Source revision strings are caller
declarations; they do not authenticate the executing source. The trusted worker
does the numerical replay outside service transactions. The service binds and
checks retained observations without solving or deciding physical validity.

## Process-death behavior

The process regression starts from an absent store and submits the existing
two-node one-member RC cantilever with two displacement targets and chunk size
one. The first subprocess performs real analysis and fresh replay, checkpoints,
claims its next lease, reserves ordinal three and is killed with SIGKILL before
entering that next invocation. A replacement cannot claim until the lease
expires. A distinct process restores the real checkpoint and completes the
second target; the stale worker cannot heartbeat during its replacement lease.

Four real analysis/replay outcomes remain attached to five reservations. The
abandoned ordinal is explicitly unknown, never erased or counted as zero work.
This proves a crash between chunks with an abandoned reservation; it does not
claim interruption inside a numerical solve. The same test checks tenant/auth
denials, immutable-idempotent retry at the service seam, conflicting input,
new-job creation after structural change, HTTP result hashing and corruption
rejection on a copied store. No completed result or checkpoint is injected.

The other suites include explicitly labelled synthetic contract seams as well
as real numerical worker fixtures. Their passing assertions are software
evidence, not independent specimen measurements or design qualification.

## Focused checks

```sh
python -m pytest -q tests/test_durable_job_service.py tests/test_rc_fiber_job_service.py tests/test_rc_fiber_job_contract.py tests/test_rc_fiber_durable_worker.py tests/test_rc_real_process_lifecycle.py
```

The slice adds tests using conventional pytest discovery but does not change
hosted workflow selection. Explicit hosted execution must be verified separately.
Price-only report revisions and reopening/downloading from the actual Workbench
remain successor slices. Browser verification is not implied by HTTP-adapter
tests. These local single-host controls do not establish production deployment,
distributed durability, independent source authentication, release readiness,
physical validation or engineering design authority.
