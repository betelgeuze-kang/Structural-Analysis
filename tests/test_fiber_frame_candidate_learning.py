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


def test_identity_preflight_cost_is_included_when_label_collection_fails(monkeypatch):
    case = FiberFrameWarmStartDataCase(
        "case", "project", "geometry", "history", "train", _model(),
        public_api.PublicRCFiberFrameConfig(load_steps=2),
    )
    clock = [0]
    validate = learning._validate_cases

    def measured_preflight(cases):
        validate(cases)
        clock[0] += 37

    def unavailable_features(*args, **kwargs):
        clock[0] += 11
        raise ValueError("bounded feature failure")

    def no_analysis(*args, **kwargs):
        pytest.fail("a failed feature preflight must not execute the solver")

    monkeypatch.setattr(learning, "perf_counter_ns", lambda: clock[0])
    monkeypatch.setattr(learning, "_validate_cases", measured_preflight)
    monkeypatch.setattr(learning, "candidate_preanalysis_features", unavailable_features)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", no_analysis)
    result = learning.train_fiber_frame_candidate_policy(
        [case], source_revision="a" * 40,
    )
    report = result.to_dict()
    costs = report["cost_accounting"]
    assert result.status == "blocked"
    assert costs["validation_preflight_wall_ns"] == 37
    assert costs["data_generation_wall_ns"] == 48
    assert report["cases"][0]["data_generation_wall_ns"] == 11
    assert costs["training_wall_ns"] is None
    assert costs["full_analysis_request_count"] == 0


def _serial_model(widths):
    payload = _model().canonical_payload()
    count = len(widths)
    section, member = payload["sections"][0], payload["elements"][0]
    payload["nodes"] = [
        {"id": f"N{index}", "coordinates": [3.0 * index / count, 0.0, 0.0]}
        for index in range(count + 1)
    ]
    payload["sections"] = [
        {**section, "id": f"S{index}", "width_m": width}
        for index, width in enumerate(widths)
    ]
    payload["elements"] = [
        {
            **member,
            "id": f"M{index}",
            "nodes": [f"N{index}", f"N{index + 1}"],
            "section": f"S{index}",
        }
        for index in range(count)
    ]
    payload["supports"][0]["node"] = "N0"
    payload["loads"][0]["node"] = f"N{count}"
    return load_neutral_json_bytes(json.dumps(payload).encode())


def _relabel_and_reorder(model):
    payload = model.canonical_payload()
    for kind in ("nodes", "elements", "sections", "materials"):
        mapping = {
            row["id"]: f"renamed-{kind}-{i}" for i, row in enumerate(payload[kind])
        }
        for row in payload[kind]:
            row["id"] = mapping[row["id"]]
        if kind == "nodes":
            for member in payload["elements"]:
                member["nodes"] = [mapping[node] for node in member["nodes"]]
            for row in (*payload["loads"], *payload["supports"]):
                row["node"] = mapping[row["node"]]
        elif kind == "sections":
            for member in payload["elements"]:
                member["section"] = mapping[member["section"]]
        elif kind == "materials":
            for section in payload["sections"]:
                for key in ("steel_material", "concrete_material"):
                    section[key] = mapping[section[key]]
        payload[kind].reverse()
    payload["metadata"] = {"case_id": "renamed-and-reordered"}
    payload["supports"][0]["dofs"].reverse()
    return load_neutral_json_bytes(json.dumps(payload).encode())


def test_member_features_separate_exact_aggregate_collision() -> None:
    first, second = _serial_model((0.34, 0.46)), _serial_model((0.46, 0.34))
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    first_features, first_context = learning.candidate_preanalysis_features(
        first, config
    )
    second_features, second_context = learning.candidate_preanalysis_features(
        second, config
    )
    assert first_context == second_context
    assert first_features[:11] == second_features[:11]
    assert first_features[11:] != second_features[11:]
    assert learning.candidate_model_identity(
        first
    ) != learning.candidate_model_identity(second)
    for index, width in enumerate((0.34, 0.46)):
        assert (
            first_features[learning.FEATURE_NAMES.index(f"member_{index}_width_m")]
            == width
        )


def test_heterogeneous_member_features_cover_public_fifteen_member_bound() -> None:
    widths = tuple(0.34 + index * 0.01 for index in range(15))
    features, _ = learning.candidate_preanalysis_features(
        _serial_model(widths), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert len(features) == 101
    assert features[0] == 15
    for index, width in enumerate(widths):
        assert (
            features[learning.FEATURE_NAMES.index(f"member_{index}_width_m")] == width
        )


def test_entity_relabel_and_order_preserve_features_context_and_identity() -> None:
    original = _serial_model((0.34, 0.46))
    relabeled = _relabel_and_reorder(original)
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    assert original.canonical_model_checksum != relabeled.canonical_model_checksum
    assert learning.candidate_preanalysis_features(original, config) == (
        learning.candidate_preanalysis_features(relabeled, config)
    )
    assert learning.candidate_model_identity(
        original
    ) == learning.candidate_model_identity(relabeled)
    train = FiberFrameWarmStartDataCase("a", "a", "a", "a", "train", original, config)
    holdout = FiberFrameWarmStartDataCase(
        "b", "b", "b", "b", "holdout", relabeled, config
    )
    with pytest.raises(
        learning.FiberFrameCandidateLearningError, match="split_leakage: physical_model"
    ):
        learning._validate_cases((train, holdout))


@pytest.mark.parametrize(
    "change", ["material", "integration", "layers", "support", "config"]
)
def test_member_context_binds_non_feature_physics(change) -> None:
    first, second = _serial_model((0.34, 0.46)), _serial_model((0.34, 0.46))
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    changed_config = config
    if change == "material":
        second.materials[0]["yield_stress_mpa"] += 1.0
    elif change == "integration":
        second.elements[0]["integration_order"] = 3
    elif change == "layers":
        second.sections[0]["concrete_layer_count"] = 3
    elif change == "support":
        first.loads[0]["node"] = "N1"
        second.loads[0]["node"] = "N1"
        second.supports[0]["node"] = "N2"
    else:
        changed_config = public_api.PublicRCFiberFrameConfig(load_steps=3)
    features, context = learning.candidate_preanalysis_features(first, config)
    changed_features, changed_context = learning.candidate_preanalysis_features(
        second, changed_config
    )
    assert features == changed_features
    assert context != changed_context
