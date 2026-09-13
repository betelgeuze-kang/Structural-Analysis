"""Algebraic, no-solver contracts for model-conditioned displacement guesses."""

from dataclasses import FrozenInstanceError, replace
import json

import numpy as np
import pytest

from structural_analysis.ai import (
    fiber_frame_conditioned_warm_start_learning as learning,
)
from structural_analysis.ai.fiber_frame_warm_start_features import (
    MODEL_FEATURE_PROFILE,
    FiberFrameWarmStartModelFeatures,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartLearningError,
    FiberFrameWarmStartSample,
)
from structural_analysis.benchmark.fiber_frame_runtime import FiberFrameWarmStartInput
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _hash(value):
    return canonical_hash({"label": value})


def _sample(index, split, *, length=3.0, force=10.0, load=0.0, previous=False):
    problem_hash = _hash(f"problem-{index}")
    features = FiberFrameWarmStartModelFeatures(
        problem_hash,
        _hash("same-material-topology-context"),
        ("member_0_length_m", "node_1_reference_fx_kn", "rotation_coordinate_scale_m"),
        (length, force, length),
    )
    scale = np.asarray((1.0, 1.0, 1.0 / length))
    physical_parent = np.asarray((0.01, 0.02, 0.003)) * load
    physical_previous = np.asarray((0.01, 0.02, 0.003)) * (load - 0.1)
    # Synthetic labels are declared physical increments, not solver observations.
    physical_delta = np.asarray((0.001, 0.002, 0.0003)) * force * 0.5
    runtime = FiberFrameWarmStartInput(
        problem_contract_hash=problem_hash,
        parent_checkpoint_state_hash=_hash(f"parent-{index}"),
        previous_checkpoint_state_hash=_hash(f"previous-{index}") if previous else None,
        parent_load_factor=load,
        previous_load_factor=load - 0.1 if previous else None,
        target_load_factor=load + 0.5,
        free_global_dofs=(3, 4, 5),
        physical_coordinate_scale=tuple(scale),
        parent_free_coordinates_m=tuple(physical_parent / scale),
        previous_free_coordinates_m=tuple(physical_previous / scale)
        if previous
        else None,
        model_features=features,
    )
    return FiberFrameWarmStartSample(
        f"sample-{index}",
        f"project-{index}",
        f"geometry-{index}",
        f"history-{index}",
        _hash(f"model-{index}"),
        problem_hash,
        split,
        runtime,
        tuple((physical_parent + physical_delta) / scale),
    )


def _samples():
    return [
        _sample(0, "train", length=3.0, force=10.0),
        _sample(1, "train", length=4.0, force=14.0),
        _sample(2, "validation", length=3.25, force=11.0),
        _sample(3, "holdout", length=3.5, force=12.0),
    ]


@pytest.fixture
def trained():
    return learning.train_fiber_frame_conditioned_warm_start_policy(_samples())


def _rehash(payload):
    payload["artifact_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    return payload


def test_genesis_model_features_distinguish_loads_and_fit_unseen_geometry(trained):
    rows = _samples()
    policy = trained.policy
    assert (
        rows[0].runtime_input.parent_free_coordinates_m
        == rows[1].runtime_input.parent_free_coordinates_m
        == (0.0, 0.0, 0.0)
    )
    assert policy.model_feature_profile == MODEL_FEATURE_PROFILE
    assert (
        policy.policy_id == "research-model-conditioned-ridge-displacement-warm-start"
    )
    assert policy.policy_version == "v2"
    assert not hasattr(policy, "physical_coordinate_scale")
    proposals = [policy.propose(row.runtime_input) for row in rows]
    assert all(proposal.ood is False for proposal in proposals)
    assert proposals[0].free_coordinates_m != proposals[1].free_coordinates_m
    np.testing.assert_allclose(
        proposals[-1].free_coordinates_m,
        rows[-1].accepted_target_free_coordinates_m,
        atol=1e-10,
        rtol=0,
    )
    assert type(trained.training_wall_ns) is int and trained.training_wall_ns >= 0
    report = trained.to_dict()
    assert (
        report["schema_version"]
        == "fiber-frame-conditioned-warm-start-training-result.v2"
    )
    assert report["training_timing_enters_policy_identity"] is False
    assert report["dataset_report"]["physical_target_replay_verified"] is False
    assert report["dataset_report"]["external_provenance_verified"] is False
    assert report["policy"]["physical_result_authority"] is False
    assert report["policy"]["production_promotion_eligible"] is False


def test_rotation_coordinates_use_scale_multiplication_and_inverse_on_prediction():
    rows = [
        _sample(0, "train", length=3.0, load=0.2, previous=True),
        _sample(1, "train", length=4.0, load=0.2, previous=True),
        _sample(2, "validation", length=3.25, load=0.2, previous=True),
        _sample(3, "holdout", length=3.5, load=0.2, previous=True),
    ]
    first, second = [row.runtime_input for row in rows[:2]]
    assert first.physical_coordinate_scale[-1] == 1 / 3
    assert second.physical_coordinate_scale[-1] == 1 / 4
    assert first.parent_free_coordinates_m[-1] == pytest.approx(3 * 0.0006)
    assert second.parent_free_coordinates_m[-1] == pytest.approx(4 * 0.0006)
    a = learning._conditioned_features(first, first.model_features)
    b = learning._conditioned_features(second, second.model_features)
    count = len(first.model_features.values)
    np.testing.assert_allclose(a[count:], b[count:], atol=1e-18, rtol=0)
    np.testing.assert_allclose(
        a[count : count + 3], (0.002, 0.004, 0.0006), atol=1e-18, rtol=0
    )
    np.testing.assert_allclose(
        a[count + 3 : count + 6], (0.001, 0.002, 0.0003), atol=1e-18, rtol=0
    )
    policy = learning.train_fiber_frame_conditioned_warm_start_policy(rows).policy
    for row in rows:
        proposal = policy.propose(row.runtime_input)
        assert proposal.ood is False
        np.testing.assert_allclose(
            proposal.free_coordinates_m,
            row.accepted_target_free_coordinates_m,
            atol=1e-14,
            rtol=0,
        )
        physical = (
            np.asarray(proposal.free_coordinates_m)
            * row.runtime_input.physical_coordinate_scale
        )
        np.testing.assert_allclose(physical, (0.007, 0.014, 0.0021), atol=1e-14, rtol=0)


def test_eval_features_targets_and_order_do_not_affect_fit_preprocessing_or_ranges(
    trained,
):
    rows = _samples()
    altered = []
    for row in rows:
        if row.split != "train":
            runtime = row.runtime_input
            features = replace(
                runtime.model_features,
                values=(1e90, -2e90, 3e90),
                context_hash=_hash("unseen-context"),
            )
            row = replace(
                row,
                runtime_input=replace(
                    runtime,
                    model_features=features,
                    physical_coordinate_scale=(1.0, 1.0, 1.0 / 3e90),
                ),
                accepted_target_free_coordinates_m=(8e99, -9e99, 7e99),
            )
        altered.append(row)
    changed = learning.train_fiber_frame_conditioned_warm_start_policy(
        list(reversed(altered))
    )
    assert changed.policy.to_dict() == trained.policy.to_dict()
    assert (
        changed.dataset_report["dataset_hash"] != trained.dataset_report["dataset_hash"]
    )
    for row in altered[2:]:
        assert changed.policy.propose(row.runtime_input).ood is True


@pytest.mark.parametrize(
    "field",
    ["project_id", "geometry_family_id", "load_history_id", "model_identity_hash"],
)
def test_cross_split_aliases_rejected_before_fit(monkeypatch, field):
    rows = _samples()
    rows[-1] = replace(rows[-1], **{field: getattr(rows[0], field)})
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *args, **kwargs: pytest.fail("leaking dataset reached fit"),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="split_leakage"):
        learning.train_fiber_frame_conditioned_warm_start_policy(rows)


@pytest.mark.parametrize("change", ["context", "layout", "dofs"])
def test_incompatible_training_profiles_rejected_before_fit(monkeypatch, change):
    rows = _samples()
    runtime = rows[1].runtime_input
    if change == "context":
        runtime = replace(
            runtime,
            model_features=replace(
                runtime.model_features, context_hash=_hash("other-material")
            ),
        )
    elif change == "layout":
        runtime = replace(
            runtime,
            model_features=replace(
                runtime.model_features,
                feature_names=(
                    "other_length_m",
                    *runtime.model_features.feature_names[1:],
                ),
            ),
        )
    else:
        runtime = replace(runtime, free_global_dofs=(6, 7, 8))
    rows[1] = replace(rows[1], runtime_input=runtime)
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *args, **kwargs: pytest.fail("bad context reached fit"),
    )
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="one topology/material context"
    ):
        learning.train_fiber_frame_conditioned_warm_start_policy(rows)


@pytest.mark.parametrize("feature_index", [0, 1, 2])
def test_genesis_geometry_and_load_ood_returns_parent_before_prediction(
    trained, feature_index
):
    runtime = _samples()[-1].runtime_input
    values = list(runtime.model_features.values)
    values[feature_index] = 1e6
    runtime = replace(
        runtime, model_features=replace(runtime.model_features, values=tuple(values))
    )
    proposal = trained.policy.propose(runtime)
    assert proposal.ood is True and proposal.uncertainty == 1.0
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "dict",
        "context",
        "layout",
        "problem",
        "hash",
        "dynamic_range",
        "dofs",
    ],
)
def test_missing_or_malformed_context_and_ood_profiles_fall_back(trained, change):
    runtime = _samples()[-1].runtime_input
    model = runtime.model_features
    if change == "missing":
        model = None
    elif change == "dict":
        model = model.to_dict()
    elif change == "context":
        model = replace(model, context_hash=_hash("other-context"))
    elif change == "layout":
        model = replace(model, feature_names=tuple(reversed(model.feature_names)))
    elif change == "problem":
        model = replace(model, problem_contract_hash=_hash("other-problem"))
    elif change == "hash":
        model = replace(model)
        object.__setattr__(model, "feature_hash", _hash("detached"))
    elif change == "dynamic_range":
        runtime = replace(runtime, target_load_factor=100.0)
    elif change == "dofs":
        runtime = replace(runtime, free_global_dofs=(6, 7, 8))
    runtime = replace(runtime, model_features=model)
    proposal = trained.policy.propose(runtime)
    assert proposal.ood is True and proposal.uncertainty == 1.0
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m


@pytest.mark.parametrize("component", [0, 1, 2])
def test_genesis_scale_contradiction_falls_back_even_when_all_features_match(
    trained, component
):
    runtime = _samples()[-1].runtime_input
    scale = list(runtime.physical_coordinate_scale)
    scale[component] *= 2.0
    changed = replace(runtime, physical_coordinate_scale=tuple(scale))
    assert changed.model_features is runtime.model_features
    # Zero parent/previous coordinates used to hide the contradictory scale
    # from the numerical feature range check, including rotation conversion.
    np.testing.assert_array_equal(
        learning._conditioned_features(changed, changed.model_features),
        learning._conditioned_features(runtime, runtime.model_features),
    )
    proposal = trained.policy.propose(changed)
    assert proposal.ood is True and proposal.uncertainty == 1.0
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m


def test_sample_and_training_reject_scale_metadata_contradiction_before_fit(
    monkeypatch,
):
    rows = _samples()
    original = rows[0]
    runtime = replace(
        original.runtime_input,
        physical_coordinate_scale=(1.0, 1.0, 1.0 / 6.0),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="coordinate scale"):
        replace(original, runtime_input=runtime)
    # Revalidate an already constructed, deliberately corrupted frozen sample;
    # the trainer must reject it even if construction checks were bypassed.
    detached = replace(original)
    object.__setattr__(detached, "runtime_input", runtime)
    rows[0] = detached
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *args, **kwargs: pytest.fail(
            "inconsistent coordinate metadata reached fit"
        ),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="coordinate scale"):
        learning.train_fiber_frame_conditioned_warm_start_policy(rows)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan"), "missing"])
def test_invalid_model_rotation_length_cannot_produce_a_prediction(trained, value):
    runtime = _samples()[-1].runtime_input
    model = replace(runtime.model_features)
    if value == "missing":
        model = replace(
            model,
            feature_names=(*model.feature_names[:-1], "undeclared_rotation_length"),
        )
    elif not np.isfinite(value):
        # The strict descriptor constructor already rejects this; exercise the
        # inference boundary against a corrupted previously typed instance too.
        object.__setattr__(model, "values", (*model.values[:-1], value))
    else:
        model = replace(model, values=(*model.values[:-1], value))
    changed = replace(runtime, model_features=model)
    proposal = trained.policy.propose(changed)
    assert proposal.ood is True and proposal.uncertainty == 1.0
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m
    with pytest.raises(FiberFrameWarmStartLearningError):
        replace(_samples()[-1], runtime_input=changed)


def test_decoder_roundtrip_is_detached_immutable_and_does_not_fit(monkeypatch, trained):
    payload = json.loads(json.dumps(trained.policy.to_dict()))
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *args, **kwargs: pytest.fail("decoder fitted policy"),
    )
    restored = learning.decode_fiber_frame_conditioned_warm_start_policy(payload)
    assert restored.to_dict() == trained.policy.to_dict()
    assert restored.propose(_samples()[-1].runtime_input) == trained.policy.propose(
        _samples()[-1].runtime_input
    )
    payload["weights"][0][0] = 999.0
    restored.to_dict()["feature_mean"][0] = -999.0
    assert restored.to_dict() == trained.policy.to_dict()
    with pytest.raises(FrozenInstanceError):
        restored.ridge = 2.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "fiber-frame-learned-warm-start-policy.v1"),
        ("policy_id", "other"),
        ("policy_version", "v1"),
        ("model_feature_profile", "other"),
        ("preprocessing_fit_split", "holdout"),
        ("physical_result_authority", True),
        ("production_promotion_eligible", 0),
        ("external_verification_claimed", True),
        ("physical_coordinate_conversion", "divide"),
        ("prediction_target", "accepted_solver_coordinates"),
        ("uncertainty_kind", "calibrated_probability"),
    ],
)
def test_rehashed_artifact_cannot_change_contract_metadata(trained, field, value):
    payload = trained.policy.to_dict()
    payload[field] = value
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_conditioned_warm_start_policy(_rehash(payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("ridge", True),
        ("ridge", 0.0),
        ("ood_margin", -1.0),
        ("free_global_dofs", [3, 4, True]),
        ("context_hash", "missing"),
        ("model_feature_names", ["duplicate", "duplicate", "rotation"]),
        ("model_feature_names", ["bad name", "force", "rotation"]),
        ("feature_scale", [1.0]),
        ("target_scale", [1.0, 1.0, 0.0]),
        ("weights", [[1.0, 2.0, 3.0]]),
        ("training_sample_hashes", []),
    ],
)
def test_rehashed_artifact_shape_types_and_ranges_are_strict(trained, field, value):
    payload = trained.policy.to_dict()
    payload[field] = value
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_conditioned_warm_start_policy(_rehash(payload))


@pytest.mark.parametrize(
    "change",
    ["unknown", "missing", "weight", "nan", "infinite", "overflow", "inverted_bounds"],
)
def test_decoder_rejects_detached_and_nonfinite_artifacts(trained, change):
    payload = trained.policy.to_dict()
    if change == "unknown":
        payload["unexpected"] = None
    elif change == "missing":
        del payload["feature_min"]
    elif change == "weight":
        payload["weights"][0][0] += 1.0
    elif change == "inverted_bounds":
        payload["feature_min"][0] = payload["feature_max"][0] + 1.0
        _rehash(payload)
    else:
        payload["feature_mean"][0] = {
            "nan": float("nan"),
            "infinite": float("inf"),
            "overflow": 10**1000,
        }[change]
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_conditioned_warm_start_policy(payload)


@pytest.mark.parametrize(
    "field", ["free_global_dofs", "weights", "model_feature_names"]
)
def test_decoder_requires_json_arrays(trained, field):
    payload = trained.policy.to_dict()
    payload[field] = tuple(payload[field])
    with pytest.raises(FiberFrameWarmStartLearningError, match="JSON arrays"):
        learning.decode_fiber_frame_conditioned_warm_start_policy(payload)


def test_decoder_rejects_rehashed_single_training_row(trained):
    payload = trained.policy.to_dict()
    payload["training_sample_hashes"] = payload["training_sample_hashes"][:1]
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_conditioned_warm_start_policy(_rehash(payload))


@pytest.mark.parametrize(
    "name,value",
    [
        ("ridge", True),
        ("ridge", 0),
        ("ridge", float("inf")),
        ("ood_margin", -1),
        ("ood_margin", float("nan")),
    ],
)
def test_invalid_training_knobs_are_rejected(name, value):
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.train_fiber_frame_conditioned_warm_start_policy(
            _samples(), **{name: value}
        )
