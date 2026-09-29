# Durable local RC research

This additive research slice depends on PR #442. It preserves the original
solver, material laws, tolerances, external references and required CI. The first
combined local run passed 72 prior plus 28 new tests (100 total) using the verified
baseline wheel plus changes, not a full checkout or independent validation.

## Persistent reuse using the existing service

`DurableRCControlResultSession` uses the existing `DurableJobService` and RC chunk
worker. Each immutable physics key has an isolated SQLite job database and one
canonical request. This avoids claiming an unrelated queued job without changing
the shared service. There is no global index, cross-key deduplication or automatic
garbage collection in this first version. The store must be a trusted single-host
filesystem, not a shared network drive. Administrative write access is trusted;
hashes cannot authenticate a database fabricated by its local administrator.

Keys bind the complete model/provenance, constant loads, targets, solver policy,
source label, package/runtime fingerprint and chunk size. A source label is not
an execution attestation. Prices and supported response limits are separate.
Each new result is computed and freshly replay-verified by the existing worker.
A persisted hit validates immutable request, event chain, invocation outcomes,
result, checkpoint and completion report. It performs no new Newton solve and
never claims a new independent verification. Source/runtime checks remain strict;
this change measures their expense instead of weakening them.

Credentials come from trusted host configuration. Set STRUCTURAL_RC_TENANT_TOKEN
and STRUCTURAL_RC_WORKER_TOKEN out of band, at least 16 characters each. Do not
commit them or pass them on the command line. This wrapper is not a new identity
provider, arbitrary-receipt importer or remote authentication deployment.

## Pause, restart and resource accounting

`chunk_target_count` fixes each authored chunk; `max_chunks_per_call` pauses at a
committed boundary. Reopening reruns the existing exact prefix verification before
the suffix: it is not zero-cost checkpoint continuation. Active leases prevent
another process from duplicating a solve. Current-call work is restricted to its
own invocation reservations, not work another process completes during a read.
Cancelled or failed jobs are not silently retried. Abandoned unknown numerical
reservations block automatic continuation. An expired lease with no numerical
reservation may be reclaimed using the original service recovery mechanism.

Cancellation remains the existing authenticated between-chunk operation, not an
interrupt inside Newton. A final report-export failure can be retried against a
successfully published durable result. Failed/incomplete worker publication is
never accepted as a cached result. Errors and unknown work remain in the store.

Timings separate input/runtime checks, lookup, worker plus durable publication,
integrity/rescreening and original export. They exclude the final report write.
Worker times include verification/storage, not only solver kernels. Repricing a
hit has zero NEW solver calls but still incurs measured integrity and I/O costs.
Historical work is retained separately; no speed ratio is automatically granted.

## CLI and candidate batches

Use `python -m structural_analysis.benchmark.rc_control_durable_cli` with the same
model/request/experiment files as the process-local CLI, plus `--store` pointing
to protected local storage. Use a new `--output` for each invocation. Repeating
with `--max-new-model-analyses 0` permits only completed stored physics. The finite
candidate-pool cost bound is unchanged; unknown cheaper candidates still prevent
confirmation. Exit 0 means a scoped candidate-price conclusion, not design approval.

`run_local_rc_batch` evaluates independent authored models in 1-4 threads (default
1), requesting at most 17 models. It rejects duplicate physics within one batch,
retains unrequested candidates and stops new reservations on a stop event or
unknown failure. Already running chunks finish under their leases. Reporting order
is fixed, but this parallel-use mode is NOT a fair strategy benchmark. Per-thread
CPU times are not summed. No hard RAM/VRAM ceiling or BLAS thread reconfiguration
is promised; use a conservative explicit worker count. This is not price-aware
parallel cancellation or a general distributed scheduler.

## AMD discovery is not hardware qualification

`python -m structural_analysis.engine_v2_backends.local_amd_diagnostic` reads Linux
rocminfo with bounded bytes/time and checks /dev/kfd visibility/access. It reports
observed gfx agents without copying arbitrary raw output. A detected agent is
not a kernel execution, CPU/GPU parity, capacity test or speedup. All those claims
remain false. Windows is explicitly unsupported by this helper. Existing HIP
parity/benchmark runners remain the separate hardware qualification path.
No AMD device or ROCm executable was available in this development environment.
Tests cover absence and controlled subprocess errors, not actual GPU execution.

## Verification and limitations

Tests use real 600 kN preload RC solves and three reversing targets, including
fresh replay, second-interpreter reuse, chunk pause/reopen, simultaneous requests,
two independent parallel candidates, repricing/rescreening and CLI reuse. Corrupt
files, interrupted exports, cancellation/failure, lease loss and abandoned work
are explicitly tested. Synthetic lease/failure injection is not physical evidence.
No core tolerance or fixture is weakened to pass these tests.

Persistent source identity is not cross-version revalidation. There is no storage
quota/deletion UI, global multi-project queue, production identity service, network
filesystem support, generic building qualification, learned speedup or AMD speedup.
Existing scientific comparisons stay fresh. External full-CI preparation failures
remain blockers; this slice does not replace the official reference or bypass CI.
