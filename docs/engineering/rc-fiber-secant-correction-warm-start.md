# RC-fiber secant-correction warm starts

The opt-in v3 policy learns a correction to the accepted-history secant initial
guess. It reuses the existing model-conditioned inputs, accepted target samples,
Newton guard, rollback and full result verification. It does not produce an
engineering response or replace the solver.

This document describes the API and measurement contracts. It contains no v3
performance observation, independent validation result or speedup claim. See
[the design experiment guide](rc-fiber-design-experiments.md) for the existing
collection, runtime-suite and fresh-process workflows.

## Select v3 explicitly

The Python study API is:

```python
from structural_analysis.benchmark.fiber_frame_learning_study import (
    run_fiber_frame_learning_study,
)

result = run_fiber_frame_learning_study(
    cases,  # Caller-supplied FiberFrameWarmStartDataCase objects.
    source_revision=source_revision,
    model_conditioning=True,
    learning_target="secant_correction",
    ridge=1e-6,
    ood_margin=0.1,
)
```

`learning_target` defaults to `"parent_increment"`. Omitting it preserves the
existing v1 study when `model_conditioning=False`, and the existing conditioned
v2 study when `model_conditioning=True`. The secant target requires the exact
boolean `True`; it is not enabled by changing a policy version label.

| Learning request | Exact `learning_configuration` fields | Study / policy |
| --- | --- | --- |
| `rc-fiber-learning-process-request.v1` | `ridge`, `ood_margin` | Existing v1 |
| `rc-fiber-learning-process-request.v2` | `ridge`, `ood_margin`, `model_conditioning: true` | Existing conditioned v2 |
| `rc-fiber-learning-process-request.v3` | `ridge`, `ood_margin`, `model_conditioning: true`, `learning_target: "secant_correction"` | Secant-correction v3 |

The v3 request keeps the existing complete `cases` and
`benchmark_configuration` objects. Each case includes its model file, public
solver configuration, `case_id`, `project_id`, `geometry_family_id`,
`load_history_id` and `split`. Unknown fields, missing flags and a v3 request
declaring `parent_increment` are rejected. v1/v2 requests do not accept the new
target field. `policy_file` is not a learning-request field: this workload fits
its own policy once.

The existing preparation example still writes a v1 request. To create a separate
v3 request without modifying that example or its authored models:

```bash
PYTHONPATH=src python3 examples/prepare_rc_fiber_learning_process.py \
  --output-directory /tmp/rc-fiber-secant-inputs
python3 - <<'PY'
import json
from pathlib import Path

inputs = Path('/tmp/rc-fiber-secant-inputs')
request = json.loads((inputs / 'request.json').read_text(encoding='utf-8'))
request['schema_version'] = 'rc-fiber-learning-process-request.v3'
request['learning_configuration'] = {
    'ridge': 1e-6,
    'ood_margin': 0.1,
    'model_conditioning': True,
    'learning_target': 'secant_correction',
}
with (inputs / 'request-secant.json').open('x', encoding='utf-8') as stream:
    json.dump(request, stream, indent=2, allow_nan=False)
    stream.write('\n')
PY
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_runtime_process \
  --workload learning-study \
  --request /tmp/rc-fiber-secant-inputs/request-secant.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --output-directory /tmp/rc-fiber-secant-resources
```

Use new input/output directories and replace `FULL_GIT_COMMIT_SHA` with the full
source revision being run. Preparation performs no solve. The learning command
does perform label generation, fitting and repeated frozen evaluation. The
example is one locally constructed section-width family with declared split
IDs; this conversion does not make it an independent project corpus or change
its tolerances, load steps, warmups or repetition counts. A declared revision
is not source attestation.

## Baseline, units and learned target

Let `q_p` and `q_prev` be the parent and previous accepted free **solver
coordinates**, and let their load factors be `λ_p` and `λ_prev`. For a target
`λ_t`, the raw baseline is:

```text
q_secant = q_p + ((λ_t - λ_p) / (λ_p - λ_prev)) * (q_p - q_prev)
```

The checked input requires `λ_t > λ_p` and, when previous history is present,
`0 <= λ_prev < λ_p`. Unequal load spacing is retained in the ratio. Computation
uses the existing runtime secant's solver-coordinate operation order.

When previous history is absent, `q_secant = q_p`. This includes genesis and an
otherwise valid input with a positive parent load but unavailable previous
history. Missing history does not establish that the parent is genesis. The
actual parent coordinates are used; they are not replaced with a zero vector.

For the per-input coordinate scale `s`, physical coordinates are `q * s`:
translations are metres and rotations are radians. Translation scale is `1`;
rotation scale is `1 / L`, where `L` is the model's
`rotation_coordinate_scale_m`. The sample's scale is checked against that
model feature and its ordered free DOFs. Static model features retain their
own units: lengths in m, fiber areas in m², forces in kN and moments in kN·m.

Training derives the correction from the original accepted target:

```text
physical_correction = (q_accepted - q_secant) * s
q_proposed = q_secant + predicted_physical_correction / s
```

The correction target uses the raw secant baseline, before any runtime guard or
damping. Zero correction preserves the baseline coordinates, including signed
zero. This is a proposal property; it does not assert equality of entire runtime
reports, guard receipts or subsequent checkpoint bytes between strategies.

## Original samples and train-only fitting

The lower-level APIs are in
`structural_analysis.ai.fiber_frame_secant_correction_warm_start_learning`:

- `train_fiber_frame_secant_correction_warm_start_policy(samples, *, ridge, ood_margin)`;
- `FiberFrameSecantCorrectionWarmStartPolicy`;
- `decode_fiber_frame_secant_correction_warm_start_policy(payload)`.

Collection, dataset and sample schemas remain their conditioned v2 versions.
They still contain original accepted coordinates and parent/previous bindings.
The trainer derives correction arrays in memory without rewriting sample
targets or hashes. It checks current sample contents against their stored
identities and records the original sorted train sample hashes in the policy.

Physical split preflight and model-feature preparation run before label
generation. Project, geometry-family, load-history, physical-model and checkpoint
identities cannot cross the enforced train/validation/holdout boundaries. These
checks establish consistency of the supplied identities, not external provenance.
All three splits are required, with at least two training samples.

Only train rows determine normalization, feature ranges, target scales and ridge
weights. Validation/holdout inputs and labels do not fit those values. Training
rows must share the ordered free-DOF layout, model feature names and
topology/material context. Different supported geometry, loads and rotation
length scales may vary through explicit features. The feature profile remains
`rc-fiber-warm-start-model-geometry-load.v1`; the target change does not add
response-dependent static features or broaden the supported solver domain.

The artifact schema is `fiber-frame-secant-correction-warm-start-policy.v3`, with
policy ID `research-model-conditioned-ridge-secant-correction-warm-start` and
version `v3`. Its hash binds the explicit `baseline_contract` and
`prediction_target` as well as weights, preprocessing and train membership.
The training and study schemas are respectively
`fiber-frame-secant-correction-warm-start-training-result.v3` and
`fiber-frame-learned-runtime-study.v3`. Existing v1/v2 artifacts remain separately
decoded; relabeling their weights as v3 is rejected.

## Abstention, verification and frozen evaluation

Missing or inconsistent model metadata, context/layout mismatch, out-of-range
features and nonfinite inference return a parent-coordinate proposal with
`ood=True` and uncertainty `1`. The runtime discards that proposal and retains
its reference solve path. This abstention does not substitute a secant guess.
Malformed core input/history is rejected by input validation and the runtime's
inference-failure handling. The range indicator is not a calibrated probability.

An in-range correction supplies only an initial guess. Existing residual guards,
damping, rollback, accepted-parent recovery and full source/result verification
remain required. The policy grants no physical result authority, external
verification or production promotion.

The study declares the target and hyperparameters before collection. Before
evaluation it checks the exact v3 policy type, strict decoded artifact, training
report profile, original train membership, dataset report and requested ridge/OOD
settings. It then reuses that same frozen policy through the validation/holdout
cases, warmups and measured repetitions. Evaluation checks both the stored
artifact hash and full policy bytes; changing contents while retaining a cached
hash cannot produce a ready study.

The saved-policy runtime and per-strategy process loaders also decode v3 without
fitting. Their existing request formats need no new target flag because the
saved artifact already binds its target. These are warm-start policy paths;
candidate-ranking policies have a separate contract.

## Costs, failures and evidence limits

The learning worker writes `study.json`, `resources.json` and `manifest.json`.
The study is v3; the existing learning-process resource/manifest and phase-recorder
v1 schemas remain unchanged. Resource records bind the exact serialized study
bytes. CPU/RSS/I/O sidecars stay outside policy and numerical identities.

| Observation | Included scope |
| --- | --- |
| `data_generation_wall_ns` | Collection for all splits, including evaluation labels and physical validation. Model feature preflight is a nested subset, not an additional charge. |
| `training_wall_ns` | The trainer's internal interval, including correction construction and fitting. |
| `training_attempt_wall_ns` | The entire v3 training attempt, training-report conversion, strict policy decoding and pre-evaluation freeze checks. Internal training time is a nested subset. |
| `evaluation_wall_ns` | The frozen runtime suite plus report conversion and policy-byte checks, including its warmups, guards/recovery, full path checks and reference episode verification. |
| `resources.study_phases` | Separate caller-owned CPU/wall intervals for collection, training attempt and evaluation; excludes interphase setup and final study assembly/hashing. |
| Whole worker resources | Process CPU, observed worker wall and available post-exec Linux peak RSS through the declared study persistence boundary, with input reads and report encoding/write/flush/fsync reported separately. |

`study_wall_ns` ends before the final cost footer and study hash are assembled;
the enclosing worker workload includes the returned study construction and its
request-profile checks. Parent process timing additionally covers launch/wait
according to the existing process manifest. Do not add nested interval totals
or historical training costs twice. The amortization numerator is full data
generation plus the entire training attempt; offline evaluation is separate.

Input I/O counts bounded file reads, excluding decode/parse/hash work. Report
I/O counts its emitted bytes and write/flush/fsync interval. These are not
physical disk traffic counters. Resource-sidecar and manifest I/O are outside
the declared worker measurements. All learning phases and runtime strategies
share that worker address space, so per-phase/per-strategy peak RSS is
unavailable; its peak cannot be subtracted or summed to derive those values.

Blocked collection skips training/evaluation. Failed training and evaluation
retain attempted intervals, while unexecuted costs remain null. A valid blocked
study may retain measured work. A ready study with invalid clocks does not
establish a ready measurement, and malformed or detached resource records do
not receive measurement credit.

Algebraic and synthetic pipeline checks cover target arithmetic, artifact
binding, dispatch and accounting. They do not establish solver accuracy,
independent-project generalization, calibrated uncertainty, robust speedup or
construction savings. Any later performance comparison needs its own retained
source/input identities, full validation, failure denominators and equivalent
cost scopes. Conditional reuse projections are not observed break-even runs.
