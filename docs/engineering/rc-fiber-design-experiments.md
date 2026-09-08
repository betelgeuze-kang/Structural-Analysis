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
analyses and requested source-history scopes verified; exit 2 can also accompany
a retained partial comparison. A
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

## Limits at every committed load step

To request a separate history screen, use `rc-fiber-design-experiment.v2` and add
a required, non-null `history_limits` object with positive finite
`maximum_translation_m` and `maximum_absolute_fiber_strain` values. Keep the
existing `candidates`, `prices` and `terminal_limits` fields. Version 1 retains
terminal-only behavior. Python callers use `FiberFrameHistoryLimits` and pass
`history_limits=` to the design comparison, candidate search, or
`FiberFrameCandidateSearchCase`. A priced selection still requires explicit
terminal limits as well as passing every requested history limit.

The public accessor is independent of design selection:

```python
from structural_analysis.api.nonlinear_fiber_frame import (
    recover_public_rc_fiber_frame_response_history,
    validate_public_rc_fiber_frame_response_history,
)

history = recover_public_rc_fiber_frame_response_history(public_result)
payload = history.to_dict()
# Optional independent call replays the retained source again:
validate_public_rc_fiber_frame_response_history(history, public_result)
```

It requires the original typed result and retained numerical source. Terminal
JSON alone cannot create verified history. The sidecar recovers epochs 1 through
the final committed epoch from original Newton displacement bytes, accepted
checkpoints and material state, with the existing J1-J5 and engineering checks.
It does not rerun truncated load paths. The initial unforced state has no accepted
transition and is explicitly excluded. The existing terminal result JSON,
numerical identity and checkpoint artifacts remain separate from the sidecar.

Every step contains displacement and fiber rows, recovery arrays and descriptors,
source bindings, and local maxima. The envelope retains the governing node/fiber
and epoch. These are maxima over positive committed static states; no between-step
extremum, cyclic/dynamic behavior, independent material validation, design-code
compliance or engineering approval follows from them.

History-requested design reports use `public-rc-fiber-design-comparison.v2` and
candidate-search reports use `fiber-frame-candidate-search-comparison.v3`. A
history failure preserves already verified terminal responses and quantities,
but removes history values and selection eligibility. An unverified baseline
history also prevents a baseline-relative selection. Terminal predictors remain
terminal predictors: their false-safe audit does not gain history-safety credit.
The separate combined-verification oracle counts retain unavailable histories.
Recovery work is included in reference/quantity and online wall times.

Workbench accepts both design-report versions. Version 2 adds committed-state
maxima and history-limit status after validating parent, step, envelope and limit
consistency within the raw-byte-bound report. The browser does not replay the
solver. Both versions export the same validated object shown in the table.

### Explicit material-memory limits

Use `rc-fiber-design-experiment.v3` with all version 2 fields plus a required
`material_history_limits` object. Its exact fields are
`maximum_steel_accumulated_plastic_strain`, `maximum_concrete_tensile_damage`
and `maximum_concrete_compressive_damage`. Each is a finite nonnegative number;
zero is allowed, and each damage limit must be at most one. Supply the intended
research screening values explicitly. No default engineering acceptance values
are supplied. The existing non-null `history_limits` is also required.

Python callers construct `FiberFrameMaterialHistoryLimits` from
`structural_analysis.benchmark.fiber_frame_design` and pass
`material_history_limits=` alongside `history_limits=` to
`compare_public_rc_fiber_frame_designs`, `compare_fiber_frame_candidate_search`
or `FiberFrameCandidateSearchCase`. The CLI command above is unchanged; point
`--experiment` at the explicit v3 document. The complete parser is
`read_design_experiment_with_material_history`, which returns candidates, prices,
terminal limits, history limits and material-history limits. Older readers
reject a v3 request rather than silently dropping its requested scope.

Material-requested M2 reports use `public-rc-fiber-design-comparison.v3` and
single candidate-search reports use `fiber-frame-candidate-search-comparison.v4`.
The immutable experiment identity includes the caller's three limits. Each
candidate retains its source-bound `constitutive_history`, separate verification
and limit statuses, and the maxima of accepted steel accumulated plastic strain,
concrete tensile damage and concrete compressive damage. These maxima cover
positive committed epochs; genesis, rejected trials and current Newton yield
events are not the screening denominator. The companion still retains genesis
and distinguishes positive stored values from increases relative to the parent.

The companion is created from the original typed result and bound to the same
model, checkpoint and already recovered response history. Its source recovery is
included in reference/quantity and online wall time, without another public
analysis request. A companion failure preserves verified terminal quantities
and response history but makes the material scope unavailable. A failed or
unavailable requested material scope cannot win; an unavailable baseline scope
blocks baseline-relative selection. Oracle combined-verification and
amortization eligibility use these same scopes. Terminal predictions do not gain
material-history safety authority.

For the fresh-process search collector, use
`rc-fiber-candidate-process-suite-request.v2` and put `material_history_limits`
in each case that requests the scope. At least one case must request it; other
cases can retain the exact v1 case fields. Material cases use v2 worker, arm and
oracle reports; nonmaterial cases retain v1 reports. The whole process suite and
portable review bundle use v2 whenever any case requests material limits.
Scheduling is unchanged: declare an even two to 32 measured repetitions and
the intended warmups. The original request bytes are retained, including legal
integer zero/one limits; typed numeric normalization is only used for semantic
plan comparison. No training or label generation is added by this option.

Workbench displays the verified stored material maxima and each declared screen
status in both standalone and selected process comparisons, and retains the
companion in their exports. Its byte and semantic checks are not a replay of the
constitutive laws or independent source authentication. Existing v1/v2 design
and v2/v3 search behavior and identities remain unchanged when the material scope
is not requested. These caller screens confer no design-code, cyclic-loading,
material-calibration or engineering-approval authority.

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

### Opt-in model-conditioned warm starts (M3)

The default remains `model_conditioning=False`: existing v1 samples, datasets,
policies and study payloads retain their contracts. Explicitly call
`run_fiber_frame_learning_study(..., model_conditioning=True)` to collect typed
model features, fit the conditioned policy once and evaluate that frozen policy.
The lower-level APIs are
`collect_fiber_frame_warm_start_data(..., model_conditioning=True)` and
`fiber_frame_conditioned_warm_start_learning.train_fiber_frame_conditioned_warm_start_policy(samples)`.
Legacy and conditioned samples cannot be mixed in one dataset or passed to the
wrong trainer.

`fiber_frame_warm_start_features.fiber_frame_warm_start_model_features(problem)`
reads immutable pre-analysis geometry, reference loads, section-fiber geometry
and the rotation-coordinate length scale. It does not read accepted targets or
evaluate a material trial. The typed `FiberFrameWarmStartModelFeatures` binds the
compiled problem hash, ordered feature names/values and context hash under
`rc-fiber-warm-start-model-geometry-load.v1`. Geometry uses metres, fiber areas use
square metres, and reference forces/moments use kN/kN·m. Context retains the actual
DOF layout, oriented member connectivity, integration/fiber-kind ordering and
material laws. Training requires one such context and feature layout; different
geometry, loads and rotation-coordinate scales remain explicit model features.

For each free coordinate, physical displacement is
`physical = solver_coordinate * physical_coordinate_scale`: translations are in
metres and rotations in radians. In particular, the rotation scale is `1 / L`,
where `L` is the model's `rotation_coordinate_scale_m`. The conditioned policy
uses physical parent/previous coordinates and learns
`(accepted_solver_coordinate - parent_solver_coordinate) * scale`. Inference
divides its predicted physical increment by the current input scale before
adding the parent solver coordinate. Thus models with `L=3` and `L=4` may share
a policy while their solver rotation coordinates differ. Each input's scale must
match its own model declaration; a shared numeric scale is not required.

Only train rows determine preprocessing, weights, target scaling and feature
ranges. Validation/holdout features and labels do not alter the fitted artifact.
Geometry/load range checks apply even at genesis, when displacement history is
zero. Missing or malformed model metadata, a different context/layout, OOD values
or nonfinite inference leave the parent-only fallback available. An in-range
proposal remains a Newton initial guess subject to the existing physical guard,
rollback and full result verification; it supplies no engineering result or
calibrated uncertainty.

Conditioned samples, datasets, collection and study reports use their respective
v2 schemas. `FiberFrameConditionedWarmStartPolicy` uses
`fiber-frame-conditioned-warm-start-policy.v2`, policy ID
`research-model-conditioned-ridge-displacement-warm-start` and version `v2`.
Its immutable `to_dict()` artifact can be restored with
`decode_fiber_frame_conditioned_warm_start_policy(payload)` without fitting.
The decoder checks exact fields, typed arrays, finite shapes, profile and hash
consistency. These hashes bind declared contents; they do not prove independent
source provenance or physical target validity.

Conditioned collection performs physical split and compiled-feature preflight
before generating labels. `model_conditioning_preflight_wall_ns` is already a
subset of `data_generation_wall_ns`; do not add it again. Every split's generated
labels remain charged. During evaluation, feature preparation is inside the
existing inference interval. The same frozen policy is reused across evaluation
cases, warmups and measured repetitions. Warmup wall time is retained separately
and excluded from per-strategy measured summaries; complete evaluation/study and
fresh-worker resource intervals include warmups, verification and reference
episode checks. No additional fit is performed between repetitions. In-process
timings do not establish separate strategy CPU or peak RSS.

Runtime benchmarks also expose `attempted_linear_solve_wall_ns` and per-attempt
linear increment call/exception counts. The optional caller-owned Newton recorder
times the existing backend, including matrix conversion and sparse diagnostic
work. `calculation_cost_accounting.linear_solve_scope` records that scope; it is
not isolated BLAS/LAPACK timing. Recorder data never enters numerical results,
checkpoint hashes or constitutive state. Reaction-only paths record zero backend
calls. An invalid instrumentation clock raises an instrumentation error rather
than being labeled as physical nonconvergence. CPU process time, peak memory and
I/O remain unmeasured by the in-process benchmark.

Material trial timing is an observed subset of assembly time. Each attempted
Newton assembly, terminal assembly and physical proposal guard records the steel
and concrete `integrate` API calls separately, including failed calls. Section
accumulation, checkpoint validation and compilation/full J1-J5 replays are outside
that subset. `calculation_cost_accounting.material_update_scope` declares these
limits. Do not add `material_update_wall_ns` to the inclusive assembly total.
The per-attempt `material_trial`, `terminal_material_trial` and per-step
`guard_material_trial` sidecars preserve counts and coverage. An unsupported
custom section retains its numerical implementation and marks coverage incomplete;
the observed subset stays visible, but the complete material total/distribution
is unavailable. A material timing error cannot become a physical warm-start
failure eligible for fallback. Numerical results, states and checkpoint identities
remain free of runtime fields; guard material timing is a sibling sidecar and does
not extend the existing guard receipt format. See
`rc-fiber-material-runtime-20260908.md` for the fixed-source repeated observation.

## Physical split and candidate feature identities

Physical training splits use the versioned
`public-rc-fiber-frame-entity-invariant-model.v1` identity. It compiles the bounded
public profile without running the solver, orders nodes by coordinates, preserves
oriented member endpoints and expands section/material references by their values.
Renaming nodes, members, sections or materials, or reordering declarations, cannot
turn a training model into a holdout. Cross-split duplicates fail before label
generation; unsupported cases still retain their public-producer diagnostics.
The authored model checksum and numerical/checkpoint hashes retain their original
meaning. This duplicate check does not prove independent project provenance or
general equivalence under rotations, translations or alternate formulations.

Candidate ranking uses the v2 member-position feature layout: 11 aggregate values
plus six section values for each of 15 canonical member slots, covering the public
16-node limit. This preserves heterogeneous section placement that averages and
sums alone lose. Material, geometry, topology, loads and solver configuration
outside those six varying section fields remain bound by the fixed context.
Candidate policy, training and search reports use v2 schemas with explicit identity
and feature profiles. Search verifies report/sample hashes, the complete policy
payload and exact train-sample membership before applying the training-overlap
guard. Legacy candidate-training artifacts require an explicitly produced v2
artifact; search does not silently migrate or refit them. These local consistency
checks are not signatures or independent target verification.
Candidate data-generation time includes the physical identity preflight;
`validation_preflight_wall_ns` is a subset of that total, including when later
feature/label collection fails. It must not be charged a second time.

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

## Per-strategy process resources

To observe each strategy in its own Python process, reuse the existing
`rc-fiber-runtime-process-request.v1` request with the separate collector:

```bash
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_strategy_process_suite \
  --request examples/public_rc_fiber_runtime_process.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/rc-fiber-strategy-process-suite
```

The Python API is
`fiber_frame_strategy_process_suite.run_fiber_frame_strategy_process_suite(request_path,
source_revision=..., output_directory=..., timeout_seconds=...)`; path arguments
accept `pathlib.Path` values. The output directory must be new. The parent writes
`report.json` using `rc-fiber-strategy-process-suite.v1`, retains frozen inputs,
and gives each strategy a directory containing `strategy.json`, `resources.json`
and `manifest.json` when those stages complete. Existing whole-suite runtime and
learning-study reports retain their separate schemas and scopes.

Workers launch sequentially in the declared reference, deterministic secant and
optional learned order. One fresh worker owns one strategy across every declared
case, warmup and measured repetition. The learned worker restores `policy_file`
once and reuses that instance throughout its batch. It verifies the frozen policy
identity without resetting or retraining it. No label collection or training runs
here; historical upfront costs require separately bound study artifacts and remain
unavailable in this experiment's accounting.

The parent freezes all input bytes before execution and compiles the inputs to
check model, coordinate, load and solver bindings. Each measured worker run uses
the existing selected-path J1-J5 and engineering verification. Warmups execute the
strategy without that additional authority replay. The parent compares complete
committed checkpoint bytes, displacement/material states and trial responses
from the workers' snapshots after checking hashes, ancestry and execution coverage.
A worker's local verification pass precedes this cross-strategy comparison;
the combined report requires both. Cases retain separate response comparisons and
timing distributions.

Resource scopes remain explicit:

- A measured run's inclusive wall/CPU interval includes execution, metadata and
  snapshot preparation, and selected-path verification. Reference workers also
  perform a separate full baseline `SolverEpisode` verification for every measured
  repetition. Its wall/CPU intervals are retained separately, and its memory is
  included in the reference worker's peak.
- Worker CPU includes imports, input processing and strategy-report persistence,
  excluding resource-sidecar emission.
  Parent CPU covers input freezing/compilation, launch/wait, artifact validation
  and comparison, ending before combined-report encoding. Parent comparison CPU
  is a subset of parent orchestration CPU; adding it again would double-count it.
- `per_strategy_peak_memory_bytes` is the whole strategy worker's observed peak,
  including imports, verification and report encoding. Unsupported/unavailable
  RSS measurement stays `null`. Independent worker peaks cannot be summed or
  subtracted, and the extra reference episode work prevents an equal-scope peak
  memory advantage claim. Per-phase peaks remain unavailable.
- Worker input byte/read-time fields cover bounded request/model/policy file API reads,
  excluding decoding, parsing and hashing. They do not measure physical disk
  traffic or all process I/O. Output encoding and write/flush/fsync fields cover
  `strategy.json`; resource-sidecar, manifest and combined-report I/O are excluded
  from those fields.

Every declared case, strategy, warmup and repetition remains in the denominator.
Blocked analyses, failed workers and timeouts preserve available artifacts and
diagnostics. Validated resource observations from completed blocked workers remain
visible as observed costs; missing measurements leave complete totals `null`.
When no worker CPU or parent comparison was observed, its value remains `null`.
Changed frozen inputs stop subsequent worker
execution. CLI exit 0 requires the combined measurement contract; exit 2 retains
a blocked comparison.

These are additional local observations, not a relabeling of historical suite
resources. The supplied revision does not switch checkouts. Hash and binding
checks establish artifact consistency, not source attestation, independent
physical validation or a general speedup guarantee.

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

The same CLI accepts the explicit conditioned request schema
`rc-fiber-learning-process-request.v2`. It keeps the complete `cases` and
`benchmark_configuration` fields and requires exactly `ridge`, `ood_margin` and
`model_conditioning: true` in `learning_configuration`. The v1 request does not
accept the new field, and a v2 request with `false` or a coerced boolean is invalid.
For example, after the preparation command above, write a separate request:

```bash
python3 - <<'PY'
import json
from pathlib import Path

inputs = Path('/tmp/rc-fiber-learning-inputs')
request = json.loads((inputs / 'request.json').read_text(encoding='utf-8'))
request['schema_version'] = 'rc-fiber-learning-process-request.v2'
request['learning_configuration']['model_conditioning'] = True
with (inputs / 'request-conditioned.json').open('x', encoding='utf-8') as stream:
    json.dump(request, stream, indent=2, allow_nan=False)
    stream.write('\n')
PY
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_runtime_process \
  --workload learning-study \
  --request /tmp/rc-fiber-learning-inputs/request-conditioned.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/rc-fiber-conditioned-learning-resources
```

The new request and output paths must not already exist. This conversion changes
only the opt-in declaration; it does not change authored models, splits, solver
tolerances or warmup/repetition counts. It supplies no observed performance
result. The conditioned worker writes a v2 study, while the existing
learning-process resource/manifest v1 schemas and their complete-study measurement
scope remain unchanged. `policy_file` is also forbidden for v2 learning requests.

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

## Repeated candidate-pool comparisons

`fiber_frame_candidate_search_suite.benchmark_fiber_frame_candidate_search_suite`
accepts one to 64 typed `FiberFrameCandidateSearchCase` declarations. Each case
fixes its baseline, candidate changes, trained policy, price basis, terminal
limits, public configuration and full-analysis budget. All inputs are detached
before any comparison starts, with a fresh model/training copy for each attempt.
Use an even `repetitions` count from 2 to 32 (default 2), and `warmups` from 0 to 5.
The round-major schedule alternates which strategy runs first within each case;
warmups do not change the measured order schedule. The standalone comparison's
`arm_order` can also be specified explicitly. Report arms stay in canonical
strategy order and `execution_order` records actual requested execution order.

```python
from structural_analysis.benchmark.fiber_frame_candidate_search_suite import (
    FiberFrameCandidateSearchCase,
    benchmark_fiber_frame_candidate_search_suite,
)

case = FiberFrameCandidateSearchCase(
    "declared-pool", baseline, candidates, training, prices, terminal_limits,
    config=config, full_analysis_budget=2, exploration_slots=1,
)
suite = benchmark_fiber_frame_candidate_search_suite(
    (case,), source_revision=source_revision,
    repetitions=2, warmups=0, oracle_audit=True,
)
report = suite.to_dict()
```

Each repetition independently freezes and executes both shortlists; the optional
oracle runs afterward on the complete declared pool, including invalid cases.
No baseline, selected-candidate or oracle solve is cached between strategies or
repetitions. Frozen ranking must agree across attempts of one case. Case reports
retain every attempt and candidate; errors retain observed call time and unknown
request counts. Contract-valid blocked selections remain in timing distributions,
while errors cannot turn a successful subset into a complete measured total.
Oracle aggregate counts describe repeated candidate observations, not distinct
physical models or independent projects.

Timing is reported per case as min/median/max/population standard deviation and
paired deterministic-minus-learned differences. No pooled cross-case speedup is
computed. Warmup costs are separate but included in total request accounting.
Historical generation/training costs are charged once per distinct validated
training report hash, with the reuse assumption explicit. Per-arm online time
charges each strategy for shared preparation; actual comparison/suite times count
that execution once. The suite wall interval includes its snapshot/binding checks,
calls and aggregation, but excludes final report encoding/I/O and prior training.
A positive paired-median amortization projection requires every measured choice
to be ready with learned material objective no worse, every warmup to be ready,
and no injected runner or clock. It is a projection of repeated reuse, not an
observed break-even or verified construction saving. CPU, peak memory, disk I/O,
independent-family generalization and between-step extrema remain outside this
suite's measurement/acceptance scope. Explicit `history_limits` adds committed
static-state envelopes to verification and candidate eligibility.

Measured producer comparisons can be exported without another solver request:

```python
comparison = suite.design_comparison("declared-pool", "learned", repetition=0)
if comparison is not None:
    write_fiber_frame_design_bundle(comparison, new_output_directory)
```

This returns a detached copy of the saved producer result for that measured arm.
An unknown case/repetition is rejected; an attempt without a producer comparison
returns `None`. Export is outside the suite measurement interval.

## Fresh processes for candidate-pool comparisons

`fiber_frame_candidate_process.run_fiber_frame_candidate_process_suite` accepts
a request path, `source_revision`, a new `output_directory`, and an optional
positive `timeout_seconds` per worker (default 3600). From a clean checkout of
the revision being evaluated, this example prepares two candidate pools and runs
two measured repetitions of each:

```bash
export RC_CANDIDATE_RUN="$(mktemp -d /tmp/rc-fiber-candidate.XXXXXX)"
PYTHONPATH=src python3 - <<'PY'
from dataclasses import asdict
import json
import os
from pathlib import Path

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate, FiberFrameMaterialPrices,
    FiberFrameSectionChange, FiberFrameTerminalLimits,
)

output = Path(os.environ["RC_CANDIDATE_RUN"])
fixtures = Path("tests/fixtures/fiber_frame_candidate_process")
for name in ("base.json", "training.json"):
    (output / name).write_bytes((fixtures / name).read_bytes())
training = json.loads((output / "training.json").read_bytes())
train_targets = [row["targets"] for row in training["samples"] if row["split"] == "train"]
limits = FiberFrameTerminalLimits(*(
    sum(row[index] for row in train_targets) / len(train_targets)
    for index in range(2)
))
cases = []
for case_id, widths in (("pool-a", (0.36, 0.395)), ("pool-b", (0.38, 0.399))):
    cases.append({
        "case_id": case_id,
        "model_file": "base.json",
        "training_file": "training.json",
        "candidates": [asdict(FiberFrameDesignCandidate(
            f"candidate-{index}", (FiberFrameSectionChange("RC1", width_m=width),)
        )) for index, width in enumerate(widths)],
        "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
        "prices": asdict(FiberFrameMaterialPrices(
            100.0, 1.0, "KRW", "2026-09-08", "synthetic example prices"
        )),
        "terminal_limits": asdict(limits),
        "history_limits": None,
        "full_analysis_budget": 2,
        "exploration_slots": 1,
    })
request = {
    "schema_version": "rc-fiber-candidate-process-suite-request.v1",
    "cases": cases, "repetitions": 2, "warmups": 0,
    "oracle_audit": False,  # True adds a later exhaustive audit for each pair.
}
(output / "request.json").write_text(json.dumps(request), encoding="utf-8")
PY
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_candidate_process \
  --request "$RC_CANDIDATE_RUN/request.json" \
  --source-revision "$(git rev-parse HEAD)" \
  --output-directory "$RC_CANDIDATE_RUN/results" \
  --timeout-seconds 3600
```

Preparation copies preserved input bytes and writes the request without solving
or training. The final CLI performs fresh full analyses. Both pools reuse one
synthetic section family; the fixture's `provenance.json` documents the earlier
labels and frozen policy. The example's prices and train-derived terminal screens
are demonstration inputs. Supply the intended price basis and limits for another
experiment. `history_limits` may instead contain both positive finite committed
translation/strain limits described above.

The request requires every shown field, one to 64 unique case IDs, even
`repetitions` in 2–32, `warmups` in 0–5, and a boolean `oracle_audit`. Model and
training paths resolve relative to the request. Full dataclass declarations keep
optional section-change fields explicit. The parent snapshots inputs and freezes
both online plans before the first worker. Each case/repetition/strategy gets a
fresh worker; online order alternates by case and repetition. Warmups have their
own slots. Each online budget includes a fresh baseline. An enabled oracle runs
after both online reports validate and never supplies labels to their selection.

The parent writes `suite.json` (`rc-fiber-candidate-process-suite.v1`), frozen
`inputs/`, and worker `requests/`. Each `workers/` slot retains `search.json`,
`resources.json`, and `manifest.json` when those stages complete, plus failure
artifacts when available. CLI exit 0 requires a ready suite; exit 2 retains an
incomplete suite. Invalid preflight requests raise before any worker launches.

- Worker workload wall/CPU covers its own preparation, ranking, full reanalysis
  and selection. Process CPU also includes imports, input processing and search
  report persistence, ending before resource-sidecar emission.
- Linux peak RSS uses the worker's post-exec `VmHWM`, including imports and report
  persistence. Missing/unsupported observations stay unavailable. Peaks are
  separate worker high-water marks, never sums, differences or per-phase peaks.
- Input bytes/read time measures bounded file API reads, excluding parsing and
  hashing. Output encoding and write/flush/fsync cover `search.json`. These fields
  exclude sidecar/manifest/parent-suite persistence and physical disk traffic.
- Parent wall/CPU includes snapshot preflight, extra predictions, launch/wait,
  validation and aggregation, ending before final suite encoding/persistence.
  Preflight is a subset; parent wall already includes waiting for workers.
  Parent and worker CPU are disjoint. Parent peak RSS remains unavailable.
  Each parent slot wall interval includes request persistence, worker launch/wait
  and that slot's artifact validation.

Historical generation/fit wall costs and request counts are charged once per
distinct validated training-report hash across all cases and repetitions. The
policy is never refitted here; historical CPU is unavailable. Failed, timed-out
and unlaunched slots remain visible. Validated partial costs remain subtotals;
unverified attempted slots retain unknown counts and prevent complete totals
where observations are missing. Per-case paired comparisons retain their stated
scope, without a pooled cross-case speedup. Hashes check local consistency, not
source attestation. This collector adds no independent physical validation,
history-prediction authority, construction-saving guarantee or design approval.

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

### Whole candidate-process review

Export a saved process experiment for Workbench with the read-only review
exporter. Use the saved `suite.json` beside its frozen inputs, requests and
worker directories, and a new output directory:

```python
from pathlib import Path
from structural_analysis.benchmark.fiber_frame_candidate_review import (
    write_fiber_frame_candidate_process_review_bundle,
)

write_fiber_frame_candidate_process_review_bundle(
    Path("candidate-process/suite.json"),
    Path("candidate-process-review"),
)
```

The CLI equivalent is
`PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_candidate_review --suite candidate-process/suite.json --output-directory candidate-process-review`.
`validate_fiber_frame_candidate_process_review_bundle(Path("candidate-process-review"))`
revalidates an exported directory, including after relocation, and returns the
checked manifest and suite.

The exporter validates frozen inputs/plans, the complete scheduled slot sequence,
worker requests and later oracle predecessors, resource/report identities,
aggregate costs and case summaries. It does not collect data, fit a policy or
start an analysis worker. Review validation costs are outside the original
experiment's recorded costs. An invalid source is rejected before publication;
the review manifest is published last in a fresh directory.

The `rc-fiber-candidate-process-review-bundle.v1` manifest binds raw `suite.json`
and maps original artifact paths to safe relative files. Original JSON path
strings are preserved. A moved copy is resolved within its copied root, without
falling back to the original absolute paths. Each valid online slot with a
physical comparison has a nested ordinary design-comparison manifest and report;
warmups are included when present. Slots with absent or invalid reports remain in
the suite with their unavailable values.

Serve the whole output directory beside Workbench on the same origin. Set
`VITE_CANDIDATE_SEARCH_PROCESS_URL` at build time, pass
`candidateSearchProcessUrl` to `WorkbenchPage`, or set runtime configuration
before loading the app:

```javascript
window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
  candidateSearchProcessUrl: '/candidate-process-review/manifest.json',
}
```

The process panel exposes shared historical training costs, measured/warmup
requests, later oracle costs and fresh-worker CPU/RSS/file-I/O observations. Case,
phase, repetition and strategy selection connects the chosen attempt to the
existing physical/quantity/price comparison. The online budget includes that
arm's baseline; it is separate from the complete experiment's training and audit
requests. Per-case paired timings and audit quality retain their scopes, and an
amortization projection is not an observed break-even run.

Browser loading checks raw byte lengths and SHA-256 before checking internal
source, slot, physical-comparison and accounting bindings. It compares stored
logical identities without regenerating Python's canonical hashes with JavaScript
number formatting. Python performs those canonical and input-plan checks before
export. Neither step replays physical analyses or attests independent provenance.
Without cryptographic integrity support, the panel supplies no verified values
or artifact downloads.

Transport limits are 64 MiB per report/artifact, 256 MiB for the loaded review,
4 MiB for the review manifest and 16 KiB for each comparison manifest. JSON
parsing rejects duplicate keys, nonfinite numbers and excessive nesting. The
browser verifies raw bytes of invalid worker artifacts as well; those bytes may
remain opaque only when the suite gives that artifact no valid-report credit.

Download buttons preserve the verified bytes of the review manifest, complete
suite and selected comparison pair. The broader Workbench JSON export records
the parsed suite and selected attempt separately from an independently configured
`designComparisonUrl`; both sources can coexist. Loading a different process URL
clears the previous review and selection while validation runs. Invalid bundles
remain unavailable, and a valid incomplete experiment remains visibly incomplete.

The actual moved Python-export-to-HTTP observation, eight comparisons and
18 original-byte downloads are documented in
`rc-fiber-candidate-process-review-20260908.md`. Keep the entire exported directory
when serving or revalidating a review; the individual raw download buttons do not
package all mapped worker/input files into a replacement bundle.
