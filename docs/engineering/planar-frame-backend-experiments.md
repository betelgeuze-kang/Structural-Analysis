# Public planar backend experiments

The reusable experiment runner executes ordered ModelIR cases across explicitly
selected public planar matrix backends. Every warmup and measured repetition gets
a fresh sequential Python process. This adds experiment coordination; it does not
change solver equations, sparse caps, convergence rules or public authority.

```bash
PYTHONPATH=src python3 -m structural_analysis.benchmark.planar_frame_backend_process \
  --request examples/planar_frame_backend_experiment.json \
  --source-revision "$(git rev-parse HEAD)" \
  --output-directory /tmp/my-new-planar-experiment \
  --timeout-seconds 180
```

The output directory must be new. The example exercises one small synthetic
portal. Add cases with their own ModelIR JSON paths and complete physical solver
configurations for a multi-case experiment. Model paths are relative to the
request file. Configuration uses the existing `PlanarFrameConfig` fields except
`matrix_backend`, which comes from each declared arm. The first backend is the
comparison baseline. Unsupported experimental controls remain diagnostic results.
No experimental control or sparse fallback is enabled by this runner.

Requests reject unknown/duplicate fields, nonfinite values, boolean counts,
duplicate case/backend identities and invalid tolerance declarations. Raw models
are copied before any worker starts. Invalid models remain preflight failures in
every requested slot. The request and all package Python/schema files are retained
alongside a content manifest. Workers import that copied tree and verify model,
configuration and source identities. The source revision is a caller label, not a
Git signature or proof of ancestry. Dependency versions, platform, Python and
loaded package sources are recorded; dependencies and the host are not vendored.
The worker requests one thread through the declared BLAS/OpenMP environment
variables. This records requested settings, not independent verification of every
native library's thread behavior.

Scheduling is phase, repetition, case, then backend. Backend order rotates by
`(case_index + repetition) % backend_count` and resets at each phase. The actual
per-case backend-position counts are reported; complete order balance requires a
multiple of the number of backends. Warmups use separate fresh workers. They do
not warm a later interpreter, although they may affect shared filesystem/OS caches.

Each slot retains stdout/stderr, phase markers, any raw result and checkpoint,
public validation, failure information and resource sidecar. Raw results and
checkpoint bytes are written before the extra public validation so an exception
there does not discard the returned result. Timeouts and crashes keep partial
files and parent elapsed time, with unavailable complete worker measurements.
Keyboard interruption terminates the current worker and keeps all later slots
as unlaunched rows. No failed slot is removed from the declared denominator.

`finished` means the coordinator or worker finished its protocol, not that every
physical solve converged. `artifact_contract_pass`, `api_entered`,
`physical_converged` and `resource_eligible` are separate fields. In particular,
public `not_run` can have a valid diagnostic contract and no physical result.
The CLI returns nonzero if any declared slot lacks a converged physical result.
All distributions include their denominators and keep valid failure costs.

Measurement scopes are deliberately separate:

- Analysis wall/CPU covers the public API, including its internal source-bound
  validation. Workload wall/CPU additionally includes explicit public validation,
  rendering, JSON encoding and result/checkpoint/report persistence.
- Worker CPU starts with the fresh process. Worker wall starts after stdlib
  imports. Both finish after artifact hashing and final source checks, before
  encoding/writing the resource sidecar. Linux peak RSS is post-exec `VmHWM` at
  that same boundary; it includes imports and retained result objects. It is not
  per-API peak memory. Other platforms keep peak memory unavailable.
- Parent launch-to-exit wall includes interpreter startup and sidecar persistence.
  Parent CPU and overall experiment wall include copying inputs/source, preflight,
  scheduling, waiting and detached result verification/comparisons before encoding
  the final experiment report. Parent CPU excludes child CPU.

The nested intervals must not be added together. RSS is neither added across
workers nor subtracted to estimate a backend allocation. Timings include neither
independent structural validation nor hosted operation. No physical disk-I/O or
native matrix-allocation total is claimed.

Five terminal SI row groups are compared using predeclared absolute and relative
tolerances, with exact identifiers, types and ordering. The example's 1e-9 values
are regression comparison parameters, not independently approved engineering
acceptance limits; a group can include more than one physical unit. Both arms
must have source/configuration-bound converged artifacts before a comparison or
paired runtime difference is available. Comparisons retain per-group differences
and mismatch paths. Whole-result canonical JSON equality, checkpoint raw-byte
equality and checkpoint state/epoch identity equality are separate from SI parity.
Same-backend repetitions also compare original result, validation and checkpoint
hash/length identities. Backend-specific result hashes can differ legitimately.

Internal accepted-history/recovery verification remains inside the unchanged
public API. The cross-backend comparator does not replay raw checkpoint histories
or numerically compare every accepted epoch. Synthetic cases do not constitute
the reserved medium/large corpus, independent OpenSees/second-solver V&V, hardware
qualification, release approval, or generalized speedup evidence.
