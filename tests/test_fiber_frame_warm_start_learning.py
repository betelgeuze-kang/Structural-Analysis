"""Learning must isolate targets, preserve identities, and fail closed on OOD."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameLearnedWarmStartPolicy,
    FiberFrameWarmStartLearningError,
    FiberFrameWarmStartSample,
    train_fiber_frame_warm_start_policy,
    validate_fiber_frame_warm_start_dataset,
)
from structural_analysis.benchmark.fiber_frame_runtime import FiberFrameWarmStartInput
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _hash(label: str) -> str:
    return canonical_hash({"label": label})


def _sample(index: int, split: str, load: float) -> FiberFrameWarmStartSample:
    runtime_input = FiberFrameWarmStartInput(
        problem_contract_hash=_hash(f"problem-{index}"),
        parent_checkpoint_state_hash=_hash(f"parent-{index}"),
        previous_checkpoint_state_hash=None,
        parent_load_factor=load,
        previous_load_factor=None,
        target_load_factor=load + 0.1,
        free_global_dofs=(3, 4),
        physical_coordinate_scale=(1.0, 1.0),
        parent_free_coordinates_m=(load * 0.01, load * 0.02),
        previous_free_coordinates_m=None,
    )
    return FiberFrameWarmStartSample(
        sample_id=f"sample-{index}",
        project_id=f"project-{index}",
        geometry_family_id=f"geometry-{index}",
        load_history_id=f"history-{index}",
        model_identity_hash=_hash(f"model-{index}"),
        physical_problem_identity_hash=runtime_input.problem_contract_hash,
        split=split,
        runtime_input=runtime_input,
        accepted_target_free_coordinates_m=((load + 0.1) * 0.01, (load + 0.1) * 0.02),
    )


def _samples() -> list[FiberFrameWarmStartSample]:
    return [
        _sample(0, "train", 0.1),
        _sample(1, "train", 0.2),
        _sample(2, "train", 0.3),
        _sample(3, "validation", 0.2),
        _sample(4, "holdout", 0.25),
    ]


def test_real_ridge_fit_predicts_held_out_displacement_and_records_training_time() -> (
    None
):
    samples = _samples()
    result = train_fiber_frame_warm_start_policy(samples)
    proposal = result.policy.propose(samples[-1].runtime_input)
    assert proposal.ood is False
    np.testing.assert_allclose(
        proposal.free_coordinates_m,
        samples[-1].accepted_target_free_coordinates_m,
        atol=1.0e-10,
    )
    assert result.training_wall_ns > 0
    report = result.to_dict()
    assert report["training_timing_enters_policy_identity"] is False
    assert report["dataset_report"]["declared_identity_isolation_pass"] is True
    assert report["dataset_report"]["external_provenance_verified"] is False
    assert report["dataset_report"]["physical_target_replay_verified"] is False
    assert report["policy"]["production_promotion_eligible"] is False
    assert (
        report["policy"]["uncertainty_kind"]
        == "uncalibrated_feature_range_indicator_not_probability"
    )


def test_holdout_and_validation_targets_never_change_training_artifact() -> None:
    original = _samples()
    changed = [
        replace(row, accepted_target_free_coordinates_m=(8.0e99, -9.0e99))
        if row.split != "train"
        else row
        for row in original
    ]
    first = train_fiber_frame_warm_start_policy(original)
    second = train_fiber_frame_warm_start_policy(changed)
    assert first.policy.to_dict() == second.policy.to_dict()
    assert first.dataset_report["dataset_hash"] != second.dataset_report["dataset_hash"]
    assert (
        first.policy.artifact_hash
        == train_fiber_frame_warm_start_policy(
            list(reversed(original))
        ).policy.artifact_hash
    )


@pytest.mark.parametrize(
    "field_name",
    ["project_id", "geometry_family_id", "load_history_id", "model_identity_hash"],
)
def test_cross_split_identity_reuse_is_rejected(field_name: str) -> None:
    rows = _samples()
    rows[-1] = replace(rows[-1], **{field_name: getattr(rows[0], field_name)})
    with pytest.raises(FiberFrameWarmStartLearningError, match="split_leakage"):
        validate_fiber_frame_warm_start_dataset(rows)


@pytest.mark.parametrize(
    "checkpoint_field",
    ["parent_checkpoint_state_hash", "previous_checkpoint_state_hash"],
)
def test_cross_split_checkpoint_reuse_is_rejected(checkpoint_field: str) -> None:
    rows = _samples()
    changes = {checkpoint_field: rows[0].runtime_input.parent_checkpoint_state_hash}
    if checkpoint_field == "previous_checkpoint_state_hash":
        changes.update(previous_load_factor=0.0, previous_free_coordinates_m=(0.0, 0.0))
    rows[-1] = replace(
        rows[-1], runtime_input=replace(rows[-1].runtime_input, **changes)
    )
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="split_leakage: checkpoint"
    ):
        validate_fiber_frame_warm_start_dataset(rows)


def test_cross_split_problem_reuse_and_duplicate_input_are_rejected() -> None:
    rows = _samples()
    problem_hash = rows[0].physical_problem_identity_hash
    rows[-1] = replace(
        rows[-1],
        physical_problem_identity_hash=problem_hash,
        runtime_input=replace(
            rows[-1].runtime_input, problem_contract_hash=problem_hash
        ),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="split_leakage"):
        validate_fiber_frame_warm_start_dataset(rows)
    rows = _samples()
    with pytest.raises(FiberFrameWarmStartLearningError, match="duplicate sample_id"):
        validate_fiber_frame_warm_start_dataset([*rows, rows[0]])
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="duplicate runtime input"
    ):
        validate_fiber_frame_warm_start_dataset(
            [*rows, replace(rows[0], sample_id="alias")]
        )


def test_sample_and_model_are_detached_immutable_snapshots() -> None:
    row = _samples()[0]
    mutable_parent = list(row.runtime_input.parent_free_coordinates_m)
    mutable_target = list(row.accepted_target_free_coordinates_m)
    detached = replace(
        row,
        runtime_input=replace(
            row.runtime_input, parent_free_coordinates_m=mutable_parent
        ),
        accepted_target_free_coordinates_m=mutable_target,
    )
    original_hash = detached.sample_hash
    mutable_parent[0] = 999.0
    mutable_target[0] = 999.0
    detached.to_dict()["accepted_target_free_coordinates_m"][0] = 888.0
    assert detached.sample_hash == original_hash
    assert (
        detached.runtime_input.parent_free_coordinates_m
        == row.runtime_input.parent_free_coordinates_m
    )
    policy = train_fiber_frame_warm_start_policy(_samples()).policy
    mutable_weights = [list(weight) for weight in policy.weights]
    cloned = replace(policy, weights=mutable_weights)
    mutable_weights[0][0] = 123.0
    assert cloned.artifact_hash == policy.artifact_hash
    assert cloned.weights == policy.weights
    with pytest.raises(FrozenInstanceError):
        cloned.ridge = 3.0


def test_ood_range_dimension_and_coordinate_profile_return_parent_only() -> None:
    rows = _samples()
    policy = train_fiber_frame_warm_start_policy(rows).policy
    outside = replace(rows[-1].runtime_input, target_load_factor=50.0)
    different_dimension = replace(
        rows[-1].runtime_input,
        free_global_dofs=(3,),
        parent_free_coordinates_m=(0.1,),
        physical_coordinate_scale=(1.0,),
    )
    different_scale = replace(
        rows[-1].runtime_input, physical_coordinate_scale=(2.0, 1.0)
    )
    for value in (outside, different_dimension, different_scale):
        proposal = policy.propose(value)
        assert proposal.ood is True
        assert proposal.uncertainty == 1.0
        assert proposal.free_coordinates_m == value.parent_free_coordinates_m


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "0.1", 10**1000])
def test_nonfinite_or_coerced_targets_are_rejected(bad: object) -> None:
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="finite number required"
    ):
        replace(_samples()[0], accepted_target_free_coordinates_m=(bad, 0.0))


def test_bad_shapes_previous_history_and_problem_binding_are_rejected() -> None:
    row = _samples()[0]
    with pytest.raises(FiberFrameWarmStartLearningError, match="shape"):
        replace(row, accepted_target_free_coordinates_m=(0.0,))
    with pytest.raises(FiberFrameWarmStartLearningError, match="incomplete history"):
        replace(row, runtime_input=replace(row.runtime_input, previous_load_factor=0.0))
    with pytest.raises(FiberFrameWarmStartLearningError, match="input mismatch"):
        replace(row, physical_problem_identity_hash=_hash("other"))
    with pytest.raises(
        FiberFrameWarmStartLearningError, match="one coordinate profile"
    ):
        rows = _samples()
        rows[1] = replace(
            rows[1],
            runtime_input=replace(
                rows[1].runtime_input, physical_coordinate_scale=(1.0, 2.0)
            ),
        )
        train_fiber_frame_warm_start_policy(rows)


def test_finite_input_overflow_is_rejected_during_training() -> None:
    rows = _samples()
    rows[0] = replace(
        rows[0],
        accepted_target_free_coordinates_m=(1.0e308, 1.0e308),
        runtime_input=replace(
            rows[0].runtime_input, parent_free_coordinates_m=(-1.0e308, -1.0e308)
        ),
    )
    with pytest.raises(FiberFrameWarmStartLearningError, match="overflow"):
        train_fiber_frame_warm_start_policy(rows)


def test_finite_weight_overflow_at_inference_returns_ood_parent() -> None:
    rows = _samples()
    learned = train_fiber_frame_warm_start_policy(rows).policy
    policy = replace(
        learned,
        target_scale=(1.0e308, 1.0e308),
        weights=tuple((1.0e308, 1.0e308) for _ in learned.weights),
    )
    proposal = policy.propose(rows[-1].runtime_input)
    assert proposal.ood is True
    assert (
        proposal.free_coordinates_m == rows[-1].runtime_input.parent_free_coordinates_m
    )


def test_artifact_rejects_nonfinite_coefficients_and_requires_all_splits() -> None:
    learned = train_fiber_frame_warm_start_policy(_samples()).policy
    with pytest.raises(FiberFrameWarmStartLearningError, match="finite number"):
        replace(learned, weights=tuple((float("nan"), 0.0) for _ in learned.weights))
    with pytest.raises(FiberFrameWarmStartLearningError, match="holdout required"):
        train_fiber_frame_warm_start_policy(_samples()[:-1])
    assert isinstance(learned, FiberFrameLearnedWarmStartPolicy)
