"""Train-only numerical fitting and fail-closed candidate policy boundaries."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def _model(width=0.4, *, metadata="test", load=-1.0):
    path = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sections"][0]["width_m"] = width
    payload["loads"][0]["components"]["FY"] = load
    payload["metadata"]["case_id"] = metadata
    return load_neutral_json_bytes(json.dumps(payload).encode())


def _rows():
    rows = []
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    for index, (width, split) in enumerate(
        ((0.34, "train"), (0.46, "train"), (0.37, "validation"), (0.43, "holdout"))
    ):
        features, context = learning.candidate_preanalysis_features(
            _model(width), config
        )
        body = {
            "case_id": f"math-only-{index}",
            "split": split,
            "context_hash": context,
            "features": features,
            "targets": [0.001 / width, 0.0001 / width],
        }
        rows.append({**body, "sample_hash": canonical_hash(body)})
    return rows


def test_holdout_targets_and_features_do_not_change_fitted_artifact() -> None:
    rows = _rows()
    first = learning._fit(rows, 1e-6, 0.1)
    changed = deepcopy(rows)
    for row in changed:
        if row["split"] != "train":
            row["targets"] = [1e150, 1e200]
            row["features"] = tuple(1e100 for _ in learning.FEATURE_NAMES)
            row["sample_hash"] = canonical_hash({"changed": row})
    second = learning._fit(changed, 1e-6, 0.1)
    assert first.artifact_hash == second.artifact_hash
    assert first.weights == second.weights
    assert (
        learning._fit(list(reversed(rows)), 1e-6, 0.1).artifact_hash
        == first.artifact_hash
    )
    assert first.to_dict()["independent_project_generalization_verified"] is False


def test_policy_is_immutable_and_ood_context_and_geometry_never_claim_safety() -> None:
    policy = learning._fit(_rows(), 1e-6, 0.1)
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    ordinary = policy.predict(_model(0.4), config)
    assert ordinary.ood is False
    assert ordinary.maximum_translation_m > 0
    for model in (_model(0.9), _model(0.4, load=-10.0)):
        prediction = policy.predict(model, config)
        assert prediction.ood is True
        assert prediction.maximum_translation_m is None
        assert prediction.maximum_absolute_fiber_strain is None
    weights = [list(row) for row in policy.weights]
    detached = replace(policy, weights=weights)
    weights[0][0] = 999.0
    assert detached.artifact_hash == policy.artifact_hash
    with pytest.raises(FrozenInstanceError):
        detached.ood_margin = 10


def test_finite_overflow_and_nonfinite_fitted_coefficients_fail_closed() -> None:
    policy = learning._fit(_rows(), 1e-6, 0.1)
    huge = replace(
        policy,
        target_scale=(1e308, 1e308),
        weights=tuple((1e308, 1e308) for _ in policy.weights),
    )
    prediction = huge.predict(
        _model(), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert prediction.ood is True
    with pytest.raises(learning.FiberFrameCandidateLearningError, match="finite"):
        replace(policy, feature_mean=(float("nan"), *policy.feature_mean[1:]))
    rows = _rows()
    for row in rows[:2]:
        row["features"] = tuple(1e308 for _ in learning.FEATURE_NAMES)
    with pytest.raises(learning.FiberFrameCandidateLearningError, match="arithmetic"):
        learning._fit(rows, 1e-6, 0.1)


def _case(index, split, width, **labels):
    return FiberFrameWarmStartDataCase(
        f"case-{index}",
        labels.get("project_id", f"project-{index}"),
        labels.get("geometry_family_id", f"geometry-{index}"),
        labels.get("load_history_id", f"history-{index}"),
        split,
        _model(width, metadata=f"label-{index}"),
        public_api.PublicRCFiberFrameConfig(load_steps=2),
    )


@pytest.mark.parametrize(
    "field", ["project_id", "geometry_family_id", "load_history_id"]
)
def test_declared_group_cross_split_reuse_is_rejected_before_solving(
    field, monkeypatch
) -> None:
    def forbidden(*_args):
        raise AssertionError("solver must not run for leaking declarations")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    cases = [
        _case(0, "train", 0.34),
        _case(
            1,
            "validation",
            0.37,
            **{field: f"{field.removesuffix('_id').replace('_family', '')}-0"},
        ),
    ]
    # Use the exact identifier instead of relying on the presentation label.
    cases[1] = _case(1, "validation", 0.37, **{field: getattr(cases[0], field)})
    with pytest.raises(
        learning.FiberFrameCandidateLearningError, match="split_leakage"
    ):
        learning.train_fiber_frame_candidate_policy(cases, source_revision="a" * 40)


def test_metadata_relabel_cannot_turn_same_physics_into_holdout() -> None:
    cases = (_case(0, "train", 0.4), _case(1, "holdout", 0.4))
    assert (
        cases[0].model.canonical_model_checksum
        != cases[1].model.canonical_model_checksum
    )
    assert learning.candidate_model_identity(
        cases[0].model
    ) == learning.candidate_model_identity(cases[1].model)
    with pytest.raises(
        learning.FiberFrameCandidateLearningError, match="split_leakage: physical_model"
    ):
        learning.train_fiber_frame_candidate_policy(cases, source_revision="a" * 40)


def test_unsupported_training_case_remains_in_denominator_without_targets() -> None:
    model = _model()
    model.elements[0]["release_i"] = ["RZ"]
    case = FiberFrameWarmStartDataCase(
        "unsupported",
        "unsupported",
        "unsupported",
        "unsupported",
        "train",
        model,
        public_api.PublicRCFiberFrameConfig(load_steps=2),
    )
    result = learning.train_fiber_frame_candidate_policy(
        [case], source_revision="a" * 40
    )
    report = result.to_dict()
    assert result.status == "blocked"
    assert result.policy is None
    assert len(report["cases"]) == 1
    assert report["samples"] == []
    assert report["cost_accounting"]["full_analysis_request_count"] == 0
    assert report["cost_accounting"]["unknown_solver_execution_count"] == 0


def test_features_are_geometry_and_rebar_inputs_only() -> None:
    features, context = learning.candidate_preanalysis_features(
        _model(), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert len(features) == len(learning.FEATURE_NAMES)
    assert np.all(np.isfinite(features))
    assert not any(
        "strain" in name or "displacement" in name or "result" in name
        for name in learning.FEATURE_NAMES
    )
    same_features, different_context = learning.candidate_preanalysis_features(
        _model(load=-5.0), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert features == same_features
    assert context != different_context
