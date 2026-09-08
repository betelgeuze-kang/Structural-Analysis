# RC fiber design experiments

The experiment uses the existing bounded public serial-cantilever RC profile.
Each alternative starts at epoch zero and runs the complete configured reference
load history, J1-J5 validation and engineering recovery. An alternative changes
authored width, depth, cover, longitudinal bar count or bar area. It cannot reduce
integration points, simplify materials, or change loads to obtain a cheaper result.

## Run an explicit candidate pool

From a checkout of the source revision being evaluated:

```bash
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_design_cli \
  --model examples/public_rc_fiber_frame_cantilever.json \
  --experiment examples/public_rc_fiber_design_experiment.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --load-steps 2 \
  --output-directory /tmp/rc-fiber-design-comparison
```

The output directory must not exist. The CLI writes `comparison.json` and then
`manifest.json`, whose byte length and SHA-256 bind the exact report bytes. These
digests detect corruption; they are not signatures or source-code attestations.
The caller must supply the revision actually used. CLI exit 0 means all reference
analyses verified; exit 2 can also accompany a retained partial comparison. A
verified analysis does not establish that requested limits pass or that a design
has engineering approval.

The example deliberately has no prices or terminal limits. It produces physical
results and quantities, with no priced selection. To use a declared price basis,
set `prices` to an object containing `concrete_per_m3`, `rebar_per_kg`, `currency`
(three uppercase letters), `as_of` (YYYY-MM-DD), and `source`. Supply actual values
for the intended comparison; prices in automated tests are synthetic fixtures.

Optional `terminal_limits` contains `maximum_translation_m` and
`maximum_absolute_fiber_strain`. These are caller-declared screens of the terminal
response only, not design-code checks or limits over every historical state. The
solver still verifies the entire configured history. A failed screen cannot be
overridden by a cheaper material estimate. A missing screen or price basis leaves
selection unavailable. The baseline remains in the candidate pool, so a more
expensive alternative is not selected just because it is the only changed design.

## Quantity and estimate scope

Quantities are calculated once per physical member from its authored geometry:

- gross concrete volume = member length × section width × section depth;
- longitudinal reinforcement volume = member length × authored bar count × bar area;
- reinforcement mass = volume × declared density (default 7850 kg/m³).

Refining integration points or concrete fibers does not change member quantities.
Gross concrete volume does not deduct reinforcement displacement. Reinforcement
follows the authored straight member length. Transverse bars, laps, hooks,
anchorage, waste, formwork, labor, fabrication, transport and tax are excluded.
The result is a scoped material estimate. It is not a detailed takeoff, quote or
confirmed construction saving.

Invalid or unsupported input, numerical nonconvergence, downstream verification
failure and unexpected evaluation errors remain distinct rows. Failed rows have
no verified quantities/cost/performance comparison and cannot be selected.

## Learning and timing

`fiber_frame_runtime_suite` retains every declared benchmark case, including
failures. It checks source/model/configuration binding and each repetition's
response-history and recovery verification. Heterogeneous cases are not pooled
into one speedup claim; each case has its own timing distributions.

`fiber_frame_warm_start_data` collects pre-step inputs and the next accepted
displacement from full verified reference cases. Sample lineage binds the model,
public result, checkpoint chain, parent and target. Metadata-only relabeling does
not turn the same physical model into an independent holdout. Dataset split IDs
remain declared research identities, not proof of independent external projects.

`fiber_frame_warm_start_learning` fits displacement increments with ridge
regression using train rows only. Preprocessing, feature bounds and policy identity
exclude validation/holdout targets. Profile mismatch, out-of-range input and
nonfinite inference return an OOD proposal, allowing the existing physical guard
and baseline recovery to retain control. The range indicator is not calibrated
statistical uncertainty.

`fiber_frame_learning_study.run_fiber_frame_learning_study` combines full data
collection, a frozen train-only policy, and reference/secant/learned comparisons
on validation and holdout cases. It reports data-generation, training, evaluation
and total study time separately. Amortization counts, when positive observed
per-case savings exist, are local projections for repeated identical cases. They
are not observed break-even executions or general performance guarantees.

Runtime benchmarks also expose `attempted_linear_solve_wall_ns` and per-attempt
linear increment call/exception counts. The optional caller-owned Newton recorder
times the existing backend, including matrix conversion and sparse diagnostic
work. `calculation_cost_accounting.linear_solve_scope` records that scope; it is
not isolated BLAS/LAPACK timing. Recorder data never enters numerical results,
checkpoint hashes or constitutive state. Reaction-only paths record zero backend
calls. An invalid instrumentation clock raises an instrumentation error rather
than being labeled as physical nonconvergence. CPU process time, peak memory and
I/O remain unmeasured by the in-process benchmark.

## Fresh-process resource measurement

Run the same runtime suite in a separate Python worker to collect CPU, memory
and file I/O observations:

```bash
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_runtime_process \
  --request examples/public_rc_fiber_runtime_process.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/rc-fiber-runtime-process
```

The output directory must be new. The explicit request declares one to 64 cases,
all public solver and benchmark settings, and an optional `policy_file`. Model
and policy paths resolve relative to the request file. The example runs the
canonical cantilever twice per reference/secant arm with two load steps and no
warmups. Add cases before execution to compare their separate timing distributions.
Set `policy_file` to the complete frozen `training.policy` JSON object from a
learning study to opt into the learned arm. Its numerical fields, metadata and
artifact identity must match; the worker does not refit the policy.

The worker writes `suite.json` and `resources.json`; the parent writes
`manifest.json` last, binding their raw byte lengths and SHA-256 digests to the
worker PID and declared source revision. These are local observations, not source
attestation or independent verification. The worker imports from the calling
module's source root even when the caller's working directory contains another
package. Use the actual revision of that source; the argument does not switch
checkouts or validate an arbitrary caller declaration.

Resource fields distinguish these scopes:

- `workload_cpu_process_time_ns` and `workload_wall_ns`: the complete suite,
  including warmups, full history/recovery verification and reference episode
  checks. CPU time includes the worker's threads and excludes other processes.
- `cpu_process_time_ns`: worker process CPU through suite persistence, including
  imports and input processing, excluding resource-sidecar emission.
- `peak_memory_bytes`: whole worker peak RSS through report encoding/persistence,
  including interpreter/import overhead. Linux uses post-exec `/proc/self/status`
  `VmHWM` because `ru_maxrss` can retain parent-process history. Other platforms
  keep this value unavailable until their process-local semantics are verified.
  The arms share one worker, so `per_strategy_peak_memory_bytes` remains
  unavailable.
- `input_read_wall_ns` and `input_bytes_read`: bounded request/model/policy file
  reads, excluding decoding, hashing and parsing. These are file API observations,
  not physical disk traffic; the operating system may serve cached pages.
- `report_encode_wall_ns` and `report_write_flush_fsync_wall_ns`: suite report
  serialization and write/flush/fsync, with its exact output byte count. Resource
  sidecar and parent manifest I/O are excluded.
- `launch_to_exit_wall_ns`: parent-observed worker lifetime. Parent CPU for launch,
  wait and artifact validation is reported separately before manifest emission.

CLI exit 0 means the suite measurement contract passed; exit 2 retains a blocked
or timed-out attempt. Invalid inputs retain `failure.json` without complete
resource credit. A damaged resource sidecar retains its raw bytes in a blocked
manifest with a validation error; it cannot receive resource credit. A timeout
terminates and reaps only the launched worker; partial files stay visible. Cancellation also reaps that worker and does not write a
completed manifest. Unsupported RSS platforms keep memory unavailable with a
reason. This wrapper does not measure policy data generation/training, per-arm
peak memory, GPU work or all host I/O, and does not upgrade numerical authority.

## Full learning-study resources

To measure label generation, training and frozen evaluation together, prepare the
explicit synthetic example and select the learning workload:

```bash
PYTHONPATH=src python3 examples/prepare_rc_fiber_learning_process.py \
  --output-directory /tmp/rc-fiber-learning-inputs
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_runtime_process \
  --workload learning-study \
  --request /tmp/rc-fiber-learning-inputs/request.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/rc-fiber-learning-resources
```

Both directories must be new. Preparation changes authored RC section widths and
writes models without running the solver. The worker then charges every physical
label, including validation/holdout labels, and fits preprocessing/weights from
train samples only. The example declares two training widths (0.400/0.390 m),
validation 0.401 m and holdout 0.402 m, two load steps, two measured repetitions,
and no warmup. Its artificial group IDs exercise the integration; all four cases
belong to one synthetic family and provide no independent holdout provenance.

The request schema is `rc-fiber-learning-process-request.v1`. Each case adds
`project_id`, `geometry_family_id`, `load_history_id` and `split` to the runtime
case fields. `learning_configuration` declares `ridge` and `ood_margin` before
collection; `policy_file` is forbidden because this workload trains its own
policy. The existing runtime workload still accepts its original request schema
and frozen-policy opt-in. Both use the same worker lifecycle and failure handling.

The Python API is `run_fiber_frame_learning_process`. Its outputs are `study.json`,
`resources.json` and `manifest.json`, with distinct learning-process schemas.
Resources bind the raw study bytes through `study_sha256`/`study_byte_length`.
The study embeds original label lineage, train-only policy, frozen evaluation and
its existing wall-time/amortization accounting. Resource observations stay outside
that report and all numerical/policy identities.

`resources.study_phases.phases` separates CPU and wall intervals for:

- `data_collection`: the collection call and report conversion, including labels
  for all splits and their full physical validation;
- `training_attempt`: the entire training call, report conversion and policy
  identity capture, including a failed training attempt;
- `evaluation`: the complete repeated runtime suite, report conversion and frozen
  policy check, including recovery and reference episode checks.

The three non-overlapping intervals exclude interphase setup and final study
assembly/hashing; the outer whole-study workload and cumulative worker CPU include
those costs in their respective scopes. Input reads and study encoding/write/
flush/fsync remain separate. One process owns all phases, so only its whole peak
RSS is observed; per-phase and per-strategy memory remain unavailable. GPU work,
resource-sidecar/manifest I/O and physical disk traffic are not measured.

The caller-owned `FiberFrameLearningStudyPhaseRecorder`, passed to
`run_fiber_frame_learning_study(..., phase_runtime=...)`, is single-use. It keeps
completed, blocked, exception and skipped phase states; skipped intervals stay
null. Clock errors or regressions invalidate timing without changing the study's
physical outcome or masking a solver exception. Injected clocks are test-only.
The worker distinguishes `study_status` from its measurement contract: a ready
measurement requires both a ready study and eligible phase timings. Invalid or
detached resource records receive no measurement credit. A valid blocked study
can retain the cost of phases it actually attempted.

## Budgeted candidate selection

`fiber_frame_candidate_learning.train_fiber_frame_candidate_policy` collects full
public solver labels and fits terminal translation/strain predictors using train
cases only. Inputs contain pre-analysis section geometry and authored bars within
one fixed load/material/topology/configuration context. Changed context or feature
range is OOD, not permission to infer an authoritative physical result. Declared
group isolation and synthetic section-family studies are not independent projects.

`fiber_frame_candidate_search.compare_fiber_frame_candidate_search` requires an
explicit candidate pool, prices, terminal limits and ready training result. Each
arm's fixed full-analysis budget includes one fresh baseline; remaining requests
confirm shortlisted candidates. The deterministic ranking uses the scoped material
estimate; learned ranking uses predicted terminal feasibility and a declared
exploration allocation. Both shortlists are frozen before any online analysis or
optional exhaustive oracle. Online models may not reuse train-label physics.

Every declared candidate stays visible, including invalid/unselected candidates.
An unverified or terminal-limit-failing row cannot be the final selection. Missing
oracle evaluation leaves missed-feasible/false-safe metrics unavailable; incomplete
oracle outcomes remain explicitly unverifiable. The audit uses new full analyses
after selection and its cost is separate. Training, preparation, inference,
selection, fresh baseline/candidate requests and unknown execution counts retain
their distinct scopes. No search accuracy, generalized acceleration or confirmed
construction saving follows merely from a selected candidate.

Workbench displays verified concrete/rebar quantities and terminal response
changes alongside each total. These changes are candidate minus baseline in the
column's units; material estimate reduction uses baseline minus candidate.
Physical changes remain available without prices, while price-dependent selection
and estimate reduction remain unavailable. If either row lacks full reference
verification, its comparison changes remain unavailable. Response changes alone
are not improvement or engineering-approval claims.

To send an arm to the existing Workbench reader without another solve:

```python
comparison = search_result.design_comparison("learned")
if comparison is not None:
    manifest = write_fiber_frame_design_bundle(comparison, new_output_directory)
```

The accessor returns only the detached M2 producer result already generated by
that arm; it is not a loader that trusts arbitrary external JSON. An empty
shortlist has no comparison bundle and still retains its baseline analysis in the
search report. The outer search report also retains the complete pool and audit,
which are not part of the smaller Workbench comparison bundle.

## Workbench

Configure the optional `VITE_DESIGN_COMPARISON_URL` with the same-origin manifest
URL when building Workbench, or pass `designComparisonUrl` to `WorkbenchPage`.
The comparison is displayed only after raw byte integrity and semantic bindings
validate within its manifest and report. Its declared source identity is separate
from the active case and review envelope; this check is not source attestation or
a freshness check against the current repository HEAD. The table and JSON export
consume the same validated report. Missing, mismatched or invalid inputs remain
unavailable. The browser does not perform a structural solve or grant engineering
approval.
