"""Actual layout SVD fitting, provenance checks and bounded abstention."""

from copy import deepcopy
from dataclasses import replace
import json
import shutil

import numpy as np
import pytest

from tests.test_rc_control_layout_dataset import roster
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_layout_learning as learning
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    RCControlCandidatePolicy,
)


def train(cases, root, **kwargs):
    return learning.train_control_layout_policy(
        cases,
        source_revision="a" * 40,
        output_directory=root,
        history_limits=FiberFrameHistoryLimits(1, 1),
        material_limits=FiberFrameMaterialHistoryLimits(1, 1, 1),
        **kwargs,
    )


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    base = tmp_path_factory.mktemp("layout-policy")
    cases = roster(base)
    allowed = {c.model.canonical_model_checksum for c in cases if c.split == "train"}
    calls = []
    original = study.api.analyze_bounded_rc_fiber_direct_control

    def guarded(model, *args, **kwargs):
        assert model.canonical_model_checksum in allowed
        calls.append(model.canonical_model_checksum)
        return original(model, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", guarded)
        policy, report = train(cases, base / "training")
    assert len(calls) == 4  # two primary paths plus two fresh verification paths
    return cases, base / "training", policy, report


def test_actual_train_only_policy_roundtrip_and_unseen_prediction(actual):
    cases, root, policy, report = actual
    assert report["sample_count"] == 2
    assert report["fit"]["status"] == "completed"
    assert report["evaluation_paths_executed"] == 0
    assert (
        report["wall_ns"]
        >= report["label_generation_wall_ns"] + report["fit"]["wall_ns"]
    )
    assert report["independent_physical_validation"] is False
    assert report["net_savings_proved"] is False
    restored = learning.RCControlLayoutPolicy((root / "policy.json").read_text())
    assert restored.policy_hash == policy.policy_hash
    result = restored.predict(cases[2].model, cases[2].request)
    assert result["abstained"] is False
    assert result["physical_result_authority"] is False
    assert result["uncertainty_calibrated"] is False
    assert result["joint_geometry_history_generalization"] is False
    exported = restored.to_dict()
    exported["weights"][0][0] = 99
    assert restored.to_dict()["weights"][0][0] != 99
    with pytest.raises(ValueError, match="profile or identity"):
        RCControlCandidatePolicy((root / "policy.json").read_text())


@pytest.mark.parametrize(
    "target,reason",
    [(0, "training_model_seen"), (3, "outside_training_feature_bounds")],
)
def test_seen_or_out_of_bounds_models_abstain(actual, target, reason):
    cases, _, policy, _ = actual
    result = policy.predict(cases[target].model, cases[target].request)
    assert result["abstained"] is True
    assert result["performance"] is None
    assert result["reason"] == reason


def test_changed_history_abstains_without_solving(actual, monkeypatch):
    cases, _, policy, _ = actual

    def forbidden(*args, **kwargs):
        raise AssertionError("prediction must not solve")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    request = replace(
        cases[2].request, targets_m=tuple(v * 1.1 for v in cases[2].request.targets_m)
    )
    assert (
        policy.predict(cases[2].model, request)["reason"]
        == "control_or_fixed_model_context_mismatch"
    )


@pytest.mark.parametrize(
    "change", ["duplicate", "boolean", "weight_shape", "old_schema", "hash"]
)
def test_policy_rejects_ambiguous_or_malformed_values(actual, change):
    _, _, policy, _ = actual
    p = policy.to_dict()
    if change == "duplicate":
        raw = '{"ridge":999,' + study._bytes(p).decode()[1:]
    else:
        if change == "boolean":
            p["ridge"] = True
        elif change == "weight_shape":
            p["weights"].pop()
        elif change == "old_schema":
            p["schema_version"] = "experimental-rc-control-candidate-policy.v1"
        else:
            p["weights"][0][0] += 1
        if change != "hash":
            p["policy_hash"] = study._sha(
                study._bytes({k: v for k, v in p.items() if k != "policy_hash"})
            )
        raw = study._bytes(p).decode()
    with pytest.raises(ValueError):
        learning.RCControlLayoutPolicy(raw)


@pytest.mark.parametrize(
    "change", ["original_bytes", "target", "unknown_work", "partial", "path"]
)
def test_original_labels_are_checked_before_fit(actual, tmp_path, monkeypatch, change):
    cases, source, _, _ = actual
    labels = json.loads((source / "labels/labels.json").read_bytes())

    def generated(*args, output_directory, **kwargs):
        shutil.copytree(source / "labels", output_directory)
        value = deepcopy(labels)
        if change == "original_bytes":
            ref = value["cases"][0]["row"]["artifacts"]["result"]
            path = output_directory / "train-00" / ref["path"]
            path.write_bytes(path.read_bytes() + b" ")
        elif change == "target":
            value["cases"][0]["row"]["performance"]["maximum_translation_m"] *= 2
        elif change == "unknown_work":
            value["cases"][0]["row"]["invocations"][0]["unknown_execution_work"] = True
        elif change == "partial":
            value["status"] = "blocked"
        else:
            value["samples"]["path"] = "../policy.json"
        return value

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid label bytes must not reach fit")

    monkeypatch.setattr(learning, "generate_control_layout_training_labels", generated)
    monkeypatch.setattr(learning, "_candidate_fit_parameters", forbidden)
    root = tmp_path / "training"
    with pytest.raises(ValueError):
        train(cases, root)
    assert not (root / "fit-started.json").exists()
    assert not (root / "policy.json").exists()
    assert (
        json.loads((root / "training-failed.json").read_bytes())["fit_started"] is False
    )


def test_holdout_geometry_does_not_change_fitted_parameters(actual, tmp_path):
    _, _, policy, _ = actual
    changed = roster(tmp_path, holdout=(7.0, 4.1))
    second, _ = train(changed, tmp_path / "training")
    for key in ("weights", "mean", "scale", "target_scale", "minimum", "maximum"):
        np.testing.assert_array_equal(policy.to_dict()[key], second.to_dict()[key])


def test_fit_interruption_retains_outcome_and_no_policy(actual, tmp_path, monkeypatch):
    cases, source, _, _ = actual

    def generated(*args, output_directory, **kwargs):
        shutil.copytree(source / "labels", output_directory)
        return json.loads((output_directory / "labels.json").read_bytes())

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(learning, "generate_control_layout_training_labels", generated)
    monkeypatch.setattr(learning, "_candidate_fit_parameters", interrupt)
    root = tmp_path / "training"
    with pytest.raises(KeyboardInterrupt):
        train(cases, root)
    result = json.loads((root / "fit-outcome.json").read_bytes())
    assert result["status"] == "interrupted"
    assert result["unknown_fit_work_until_outcome"] is True
    assert not (root / "policy.json").exists()


@pytest.mark.parametrize("ridge", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_fit_controls_reject_before_output(actual, tmp_path, ridge):
    cases, _, _, _ = actual
    root = tmp_path / "training"
    with pytest.raises(ValueError, match="ridge"):
        train(cases, root, ridge=ridge)
    assert not root.exists()


def test_invalid_limits_reject_before_output(actual, tmp_path):
    cases, _, _, _ = actual
    root = tmp_path / "training"
    with pytest.raises(ValueError, match="typed"):
        learning.train_control_layout_policy(
            cases,
            source_revision="a" * 40,
            output_directory=root,
            history_limits={},
            material_limits=FiberFrameMaterialHistoryLimits(1, 1, 1),
        )
    assert not root.exists()
