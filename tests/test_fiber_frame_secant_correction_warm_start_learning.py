"""Algebraic v3 contracts; the labels here are synthetic, with no solver calls."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json

import numpy as np
import pytest

from structural_analysis.ai import fiber_frame_conditioned_warm_start_learning as v2
from structural_analysis.ai import (
    fiber_frame_secant_correction_warm_start_learning as learning,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartLearningError,
    validate_fiber_frame_warm_start_dataset,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from tests.test_fiber_frame_conditioned_warm_start_learning import _hash, _sample


def _baseline(value):
    """Independent statement of runtime's original solver-coordinate arithmetic."""
    current = np.asarray(value.parent_free_coordinates_m)
    if value.previous_free_coordinates_m is None:
        return current.copy()
    previous = np.asarray(value.previous_free_coordinates_m)
    denominator = value.parent_load_factor - value.previous_load_factor
    factor = (value.target_load_factor - value.parent_load_factor) / denominator
    return current + factor * (current - previous)


def _rows(*, zero_correction=False):
    result = []
    for index, split, length, force in (
        (0, "train", 3.0, 10.0),
        (1, "train", 4.0, 14.0),
        (2, "validation", 3.25, 11.0),
        (3, "holdout", 3.5, 12.0),
    ):
        row = _sample(index, split, length=length, force=force, load=0.4, previous=True)
        baseline = _baseline(row.runtime_input)
        correction = np.zeros(3) if zero_correction else np.asarray((1e-4, -2e-4, 3e-5))
        result.append(
            replace(
                row,
                accepted_target_free_coordinates_m=tuple(
                    baseline + correction / row.runtime_input.physical_coordinate_scale
                ),
            )
        )
    return result


@pytest.fixture
def trained():
    return learning.train_fiber_frame_secant_correction_warm_start_policy(_rows())


def _zero_policy(policy):
    return replace(
        policy,
        weights=tuple(tuple(0.0 for _ in row) for row in policy.weights),
        feature_min=tuple(-1e100 for _ in policy.feature_min),
        feature_max=tuple(1e100 for _ in policy.feature_max),
    )


def _rehash(payload):
    payload["artifact_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    return payload


def test_zero_correction_preserves_runtime_secant_bytes_and_signed_zero(trained):
    runtime = replace(
        _rows()[0].runtime_input,
        parent_load_factor=0.3,
        previous_load_factor=0.1,
        target_load_factor=0.8,
        parent_free_coordinates_m=(-0.0, 0.0, 0.123456789),
        previous_free_coordinates_m=(0.0, -0.0, 0.023456781),
    )
    expected = _baseline(runtime)
    assert np.signbit(expected[0])
    proposal = _zero_policy(trained.policy).propose(runtime)
    assert proposal.ood is False
    assert np.asarray(proposal.free_coordinates_m).tobytes() == expected.tobytes()
    assert (
        np.asarray(learning._secant_baseline(runtime)).tobytes() == expected.tobytes()
    )


@pytest.mark.parametrize("parent_load", (0.0, 0.4))
def test_missing_previous_uses_exact_parent_at_genesis_or_positive_load(
    trained, parent_load
):
    runtime = replace(
        _sample(9, "validation", load=parent_load).runtime_input,
        parent_free_coordinates_m=(-0.0, 0.02, -0.03),
    )
    proposal = _zero_policy(trained.policy).propose(runtime)
    assert proposal.ood is False
    assert (
        np.asarray(proposal.free_coordinates_m).tobytes()
        == np.asarray(runtime.parent_free_coordinates_m).tobytes()
    )


def test_exact_secant_labels_fit_zero_correction_without_relabelling_original_samples(
    monkeypatch,
):
    rows = _rows(zero_correction=True)
    before = [row.to_dict() for row in rows]
    monkeypatch.setattr(
        v2,
        "train_fiber_frame_conditioned_warm_start_policy",
        lambda *a, **k: pytest.fail("v3 delegated to relabelled v2 samples"),
    )
    result = learning.train_fiber_frame_secant_correction_warm_start_policy(rows)
    assert [row.to_dict() for row in rows] == before
    assert result.policy.training_sample_hashes == tuple(
        sorted(row.sample_hash for row in rows if row.split == "train")
    )
    assert result.dataset_report == validate_fiber_frame_warm_start_dataset(rows)
    assert not np.any(result.policy.weights)
    for row in rows:
        proposal = result.policy.propose(row.runtime_input)
        assert proposal.ood is False
        assert (
            np.asarray(proposal.free_coordinates_m).tobytes()
            == _baseline(row.runtime_input).tobytes()
        )


def test_physical_rotation_correction_fits_lengths_three_and_four(trained):
    rows = _rows()
    for row in rows:
        runtime = row.runtime_input
        proposal = trained.policy.propose(runtime)
        assert proposal.ood is False
        np.testing.assert_allclose(
            proposal.free_coordinates_m,
            row.accepted_target_free_coordinates_m,
            rtol=0,
            atol=2e-17,
        )
        physical = (
            np.asarray(proposal.free_coordinates_m) - _baseline(runtime)
        ) * runtime.physical_coordinate_scale
        np.testing.assert_allclose(physical, (1e-4, -2e-4, 3e-5), rtol=0, atol=2e-17)
    first, second = rows[0].runtime_input, rows[1].runtime_input
    assert first.physical_coordinate_scale[-1] == 1 / 3
    assert second.physical_coordinate_scale[-1] == 1 / 4
    np.testing.assert_allclose(
        trained.policy.target_scale, (1e-4, 2e-4, 3e-5), rtol=0, atol=2e-17
    )


def test_eval_data_values_order_and_training_order_never_change_fit(trained):
    changed = []
    for row in _rows():
        if row.split != "train":
            model = replace(
                row.runtime_input.model_features,
                values=(1e90, -2e90, 3e90),
                context_hash=_hash("external-context"),
            )
            runtime = replace(
                row.runtime_input,
                model_features=model,
                physical_coordinate_scale=(1.0, 1.0, 1 / 3e90),
            )
            row = replace(
                row,
                runtime_input=runtime,
                accepted_target_free_coordinates_m=(8e99, -9e99, 7e99),
            )
        changed.append(row)
    result = learning.train_fiber_frame_secant_correction_warm_start_policy(
        list(reversed(changed))
    )
    assert result.policy.to_dict() == trained.policy.to_dict()
    assert (
        result.dataset_report["dataset_hash"] != trained.dataset_report["dataset_hash"]
    )
    payload = result.to_dict()
    assert (
        payload["schema_version"]
        == "fiber-frame-secant-correction-warm-start-training-result.v3"
    )
    assert payload["training_timing_enters_policy_identity"] is False
    assert payload["dataset_report"]["physical_target_replay_verified"] is False
    assert payload["dataset_report"]["external_provenance_verified"] is False
    assert type(result.training_wall_ns) is int and result.training_wall_ns >= 0


@pytest.mark.parametrize(
    "field",
    (
        "project_id",
        "geometry_family_id",
        "load_history_id",
        "model_identity_hash",
        "physical_problem_identity_hash",
    ),
)
def test_cross_split_leakage_fails_before_fit(monkeypatch, field):
    rows = _rows()
    changes = {field: getattr(rows[0], field)}
    if field == "physical_problem_identity_hash":
        runtime = rows[-1].runtime_input
        changes["runtime_input"] = replace(
            runtime,
            problem_contract_hash=rows[0].physical_problem_identity_hash,
            model_features=replace(
                runtime.model_features,
                problem_contract_hash=rows[0].physical_problem_identity_hash,
            ),
        )
    rows[-1] = replace(rows[-1], **changes)
    monkeypatch.setattr(
        learning.np.linalg, "lstsq", lambda *a, **k: pytest.fail("leakage reached fit")
    )
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.train_fiber_frame_secant_correction_warm_start_policy(rows)


@pytest.mark.parametrize("index", (0, 3))
def test_stale_original_sample_hash_is_rejected_before_fit(monkeypatch, index):
    rows = _rows()
    row = rows[index]
    object.__setattr__(
        row,
        "accepted_target_free_coordinates_m",
        tuple(value + 1e-5 for value in row.accepted_target_free_coordinates_m),
    )
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *a, **k: pytest.fail("stale source hash reached fit"),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="stored identity"):
        learning.train_fiber_frame_secant_correction_warm_start_policy(rows)


@pytest.mark.parametrize(
    "change",
    ("missing", "context", "layout", "problem", "hash", "profile", "scale", "ood"),
)
def test_metadata_mismatch_or_ood_abstains_to_parent_not_secant(trained, change):
    runtime = _rows()[-1].runtime_input
    model = runtime.model_features
    policy = trained.policy
    if change == "missing":
        model = None
    elif change == "context":
        model = replace(model, context_hash=_hash("other-context"))
    elif change == "layout":
        model = replace(model, feature_names=tuple(reversed(model.feature_names)))
    elif change == "problem":
        model = replace(model, problem_contract_hash=_hash("other-problem"))
    elif change == "hash":
        model = replace(model)
        object.__setattr__(model, "feature_hash", "unknown")
    elif change == "profile":
        policy = replace(policy)
        object.__setattr__(policy, "model_feature_profile", "unknown")
    elif change == "scale":
        runtime = replace(runtime, physical_coordinate_scale=(1.0, 1.0, 1 / 7))
    elif change == "ood":
        runtime = replace(runtime, target_load_factor=100.0)
    runtime = replace(runtime, model_features=model)
    proposal = policy.propose(runtime)
    assert proposal.ood is True and proposal.uncertainty == 1.0
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m
    assert proposal.free_coordinates_m != tuple(_baseline(runtime))


def _overflow_input():
    return replace(
        _rows()[0].runtime_input,
        parent_load_factor=float.fromhex("0x0.0000000000001p-1022"),
        previous_load_factor=0.0,
        target_load_factor=1.0,
        parent_free_coordinates_m=(1.0, 1.0, 1.0),
        previous_free_coordinates_m=(0.0, 0.0, 0.0),
    )


def test_finite_inputs_with_overflowing_secant_factor_abstain(trained):
    runtime = _overflow_input()
    proposal = _zero_policy(trained.policy).propose(runtime)
    assert proposal.ood is True
    assert proposal.free_coordinates_m == runtime.parent_free_coordinates_m


def test_overflowing_training_baseline_is_rejected_before_fit(monkeypatch):
    rows = _rows()
    rows[0] = replace(rows[0], runtime_input=_overflow_input())
    monkeypatch.setattr(
        learning.np.linalg, "lstsq", lambda *a, **k: pytest.fail("overflow reached fit")
    )
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.train_fiber_frame_secant_correction_warm_start_policy(rows)


def test_prediction_overflow_abstains_to_parent(trained):
    policy = _zero_policy(trained.policy)
    weights = [list(row) for row in policy.weights]
    weights[-1] = [1e308] * 3
    policy = replace(
        policy, weights=tuple(tuple(row) for row in weights), target_scale=(10.0,) * 3
    )
    runtime = _rows()[0].runtime_input
    proposal = policy.propose(runtime)
    assert (
        proposal.ood is True
        and proposal.free_coordinates_m == runtime.parent_free_coordinates_m
    )


def test_decoder_is_detached_immutable_and_does_not_fit(trained, monkeypatch):
    payload = json.loads(json.dumps(trained.policy.to_dict()))
    monkeypatch.setattr(
        learning.np.linalg, "lstsq", lambda *a, **k: pytest.fail("decoder fitted")
    )
    restored = learning.decode_fiber_frame_secant_correction_warm_start_policy(payload)
    assert restored.to_dict() == trained.policy.to_dict()
    assert restored.policy_version == "v3" and restored.policy_id == learning.POLICY_ID
    assert restored.to_dict()["baseline_contract"] == learning.BASELINE_CONTRACT
    assert restored.to_dict()["prediction_target"] == learning.PREDICTION_TARGET
    payload["weights"][0][0] += 10
    restored.to_dict()["feature_mean"][0] += 10
    assert restored.to_dict() == trained.policy.to_dict()
    with pytest.raises(FrozenInstanceError):
        restored.ridge = 2


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema_version", v2.POLICY_SCHEMA),
        ("policy_version", "v2"),
        ("policy_id", "other"),
        ("model_feature_profile", "unknown"),
        ("baseline_contract", "parent_only"),
        ("prediction_target", "next_accepted_physical_coordinate_increment_m_and_rad"),
        ("physical_coordinate_conversion", "divide"),
        ("preprocessing_fit_split", "holdout"),
        ("production_promotion_eligible", 0),
        ("physical_result_authority", True),
        ("external_verification_claimed", True),
        ("ridge", True),
        ("ridge", 0.0),
        ("ood_margin", -1.0),
        ("free_global_dofs", [3, 4, True]),
        ("free_global_dofs", [3, 4, 5.0]),
        ("context_hash", "invalid"),
        (
            "model_feature_names",
            ["duplicate", "duplicate", "rotation_coordinate_scale_m"],
        ),
        ("feature_scale", [1.0]),
        ("target_scale", [1.0, 1.0, 0.0]),
        ("weights", [[1.0, 2.0, 3.0]]),
        ("training_sample_hashes", []),
    ),
)
def test_resealing_cannot_change_artifact_contract_or_types(trained, field, value):
    payload = trained.policy.to_dict()
    payload[field] = value
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_secant_correction_warm_start_policy(
            _rehash(payload)
        )


@pytest.mark.parametrize(
    "change",
    (
        "unknown",
        "missing",
        "weights",
        "hash",
        "nan",
        "inf",
        "huge_int",
        "tuple",
        "bad_source_hash",
    ),
)
def test_detached_or_malformed_artifact_rejected(trained, change):
    payload = deepcopy(trained.policy.to_dict())
    if change == "unknown":
        payload["unknown"] = None
    elif change == "missing":
        del payload["baseline_contract"]
    elif change == "weights":
        payload["weights"][0][0] += 1.0
    elif change == "hash":
        payload["artifact_hash"] = _hash("other-artifact")
    elif change == "tuple":
        payload["weights"] = tuple(payload["weights"])
    elif change == "bad_source_hash":
        payload["training_sample_hashes"][0] = "invalid"
    else:
        payload["feature_mean"][0] = {
            "nan": float("nan"),
            "inf": float("inf"),
            "huge_int": 10**1000,
        }[change]
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_secant_correction_warm_start_policy(payload)


def test_v2_and_v3_decoders_do_not_accept_each_others_artifacts(trained):
    old = v2.train_fiber_frame_conditioned_warm_start_policy(_rows()).policy
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.decode_fiber_frame_secant_correction_warm_start_policy(old.to_dict())
    with pytest.raises(FiberFrameWarmStartLearningError):
        v2.decode_fiber_frame_conditioned_warm_start_policy(trained.policy.to_dict())


@pytest.mark.parametrize(
    "field,value",
    (
        ("ridge", True),
        ("ridge", 0),
        ("ridge", float("inf")),
        ("ood_margin", -1),
        ("ood_margin", float("nan")),
    ),
)
def test_invalid_fit_knobs_fail_before_lstsq(monkeypatch, field, value):
    monkeypatch.setattr(
        learning.np.linalg, "lstsq", lambda *a, **k: pytest.fail("bad knob reached fit")
    )
    with pytest.raises(FiberFrameWarmStartLearningError):
        learning.train_fiber_frame_secant_correction_warm_start_policy(
            _rows(), **{field: value}
        )


def test_incompatible_train_context_is_rejected_before_fit(monkeypatch):
    rows = _rows()
    runtime = rows[1].runtime_input
    rows[1] = replace(
        rows[1],
        runtime_input=replace(
            runtime,
            model_features=replace(
                runtime.model_features, context_hash=_hash("different-material-law")
            ),
        ),
    )
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *a, **k: pytest.fail("incompatible context reached fit"),
    )
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="one topology/material context"
    ):
        learning.train_fiber_frame_secant_correction_warm_start_policy(rows)


def test_nonzero_physical_correction_underflow_preserves_baseline_signed_zero(trained):
    policy = _zero_policy(trained.policy)
    weights = [list(row) for row in policy.weights]
    # Rotational physical scale 1/L may exceed 1; a subnormal correction then
    # underflows during inverse conversion and must still avoid adding +0.
    weights[-1][-1] = float.fromhex("0x0.0000000000001p-1022")
    policy = replace(
        policy, weights=tuple(tuple(row) for row in weights), target_scale=(1.0,) * 3
    )
    runtime = _rows()[0].runtime_input
    runtime = replace(
        runtime,
        parent_free_coordinates_m=(0.0, 0.0, -0.0),
        previous_free_coordinates_m=(0.0, 0.0, 0.0),
        physical_coordinate_scale=(1.0, 1.0, 2.0),
        model_features=replace(runtime.model_features, values=(0.5, 10.0, 0.5)),
    )
    proposal = policy.propose(runtime)
    assert proposal.ood is False
    assert (
        np.asarray(proposal.free_coordinates_m).tobytes()
        == _baseline(runtime).tobytes()
    )
