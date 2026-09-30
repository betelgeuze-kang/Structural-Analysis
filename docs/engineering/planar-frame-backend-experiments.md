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

Internal accepted-history/recovery verification remains inside the public API.
The v1 cross-backend comparator does not replay raw checkpoint histories or
numerically compare every accepted epoch. Synthetic cases do not constitute
the reserved medium/large corpus, independent OpenSees/second-solver V&V, hardware
qualification, release approval, or generalized speedup evidence.

## Accepted-history comparison with request v2

Select `planar-frame-backend-experiment-request.v2` and supply
`history_tolerances` for the five existing SI groups plus `material_states`.
Each group requires finite nonnegative `absolute` and `relative` values. The
terminal `tolerances` remain separately declared. The new
`examples/planar_frame_backend_history_experiment.json` uses four load steps:

```bash
PYTHONPATH=src python3 -m structural_analysis.benchmark.planar_frame_backend_process \
  --request examples/planar_frame_backend_history_experiment.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/my-new-planar-history-experiment
```

Use a new output directory and the full source commit being run. V1 requests and
their original output/cost scopes remain supported; v1 does not accept the new
history-tolerance field. V2 workers and experiment reports have version-two
schemas, so their extra recovery work cannot be mistaken for the v1 workload.

A converged v2 worker also writes `history.json`. It reconstructs the exact
ModelIR-bound problem, loads the original canonical checkpoint bytes, and requires
genesis plus every configured target with contiguous epoch/step/parent links.
Each parent-to-child transition is reassembled using the existing engineering
recovery implementation. Dense/legacy arms retain dense state assembly; extended
sparse retains sparse state assembly. Newton is not reexecuted by this projection.
The original public execution and its validations remain required.

The reassembled global displacement and all material/element state bytes must
match the stored child exactly. Reaction partition, force scatter, member feature
equilibrium, section integration, fiber strain and physical residual gates remain
in place. Physical-to-solver coordinate conversion must round-trip; a mismatch
fails without a tolerance waiver. The final projected SI rows must be byte-exact
under canonical JSON encoding with the original public result rows.

The parent independently repeats this same local projection from the retained
model/result/checkpoint and compares the complete sidecar. Editing a middle
response and recomputing the sidecar/file hashes cannot bypass that source check.
This is internal source consistency using the same implementation, not an
independent structural solver or provenance attestation.

Comparison covers genesis displacement/material memory and every accepted step's
five SI groups and material memory. Constitutive memory preserves the original
state schema and native units (including stress/history variables); only its
derived `state_hash` field is excluded from numerical comparison. The material
group's tolerance applies to those native numeric fields; like mixed-unit SI row
groups, it is a regression policy, not an approved engineering acceptance limit.
Identifiers, integer counters, booleans, nulls, row/key membership and order remain
exact. Float comparison uses the declared symmetric absolute/relative rule, with
finite overflow handling and bounded mismatch paths. Missing/empty groups,
genesis-only data, skipped epochs and inconsistent load schedules cannot pass.
Checkpoint/state/history hash equality remains a separate observation.

`history_runtime` records the worker's attempted projection, including source
compile, checkpoint decode, all transition reassemblies, terminal binding and
history encoding/write. Its wall/CPU times are nested inside the v2 workload;
the disjoint analysis and history intervals must fit inside that workload. Failed
attempts retain elapsed cost; unexecuted phases remain null with a reason. V2
per-slot `parent_artifact_validation_*_ns` includes detached validation and the
parent's history reassembly, excluding launch/wait. Those costs and the later
comparison are included in total parent/experiment costs. Do not add a nested
phase twice or compare v1/v2 workload medians as equivalent measurement scopes.

V2 paired cost differences require both terminal and full-history matches.
`history_comparison_counts` retains expected/reported pairs and each match count,
including unavailable/failed comparisons. CLI success requires all declared slots
to converge and all required comparisons to match. Unsupported/nonconverged
results keep diagnostics and null history; they receive no complete-history
credit. Same-backend repeat identity also includes original `history.json` bytes.
