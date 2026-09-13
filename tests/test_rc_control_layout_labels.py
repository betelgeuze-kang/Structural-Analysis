"""Actual train-only reference labels and failure-preserving publication."""

import json

import pytest

from tests.test_rc_control_layout_dataset import roster
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
)
from structural_analysis.benchmark.rc_control_layout_labels import (
    generate_control_layout_training_labels,
)


def generate(cases, root, **overrides):
    args = dict(
        source_revision="a" * 40,
        output_directory=root,
        history_limits=FiberFrameHistoryLimits(1e-12, 1e-12),
        material_limits=FiberFrameMaterialHistoryLimits(1, 1, 1),
    )
    return generate_control_layout_training_labels(cases, **(args | overrides))


def test_real_labels_keep_verified_infeasible_cases_and_never_execute_evaluation(
    tmp_path, monkeypatch
):
    cases = roster(tmp_path)
    allowed = {c.model.canonical_model_checksum for c in cases if c.split == "train"}
    calls = []
    for name in (
        "analyze_bounded_rc_fiber_direct_control",
        "validate_bounded_rc_fiber_direct_control_artifacts",
    ):
        original = getattr(study.api, name)

        def guarded(model, *args, _original=original, _name=name, **kwargs):
            assert model.canonical_model_checksum in allowed
            calls.append(_name)
            return _original(model, *args, **kwargs)

        monkeypatch.setattr(study.api, name, guarded)
    root = tmp_path / "labels"
    report = generate(cases, root)
    assert report["status"] == "complete"
    assert report["attempted_training_cases"] == report["verified_training_cases"] == 2
    # Each verification invokes a fresh analysis through the same public API.
    assert calls.count("analyze_bounded_rc_fiber_direct_control") == 4
    assert calls.count("validate_bounded_rc_fiber_direct_control_artifacts") == 2
    assert report["evaluation_paths_executed"] == 0
    assert report["response_policy_fitted"] is False
    assert report["independent_physical_validation"] is False
    raw = (root / report["samples"]["path"]).read_bytes()
    assert study._sha(raw) == report["samples"]["sha256"]
    samples = json.loads(raw)
    for index, (sample, wrapped) in enumerate(zip(samples, report["cases"])):
        row = wrapped["row"]
        assert row["full_reference_verification_pass"] is True
        assert row["selection_eligible"] is False
        assert sample["artifact_directory"] == f"train-{index:02d}"
        case_root = root / sample["artifact_directory"]
        request = (case_root / sample["request"]["path"]).read_bytes()
        assert study._sha(request) == sample["request"]["sha256"]
        assert json.loads(request) == cases[index].request.to_dict()
        assert sample["targets"] == [
            row["performance"][key] for key in report["targets"]
        ]
        digest = sample.pop("sample_hash")
        assert study._sha(study._bytes(sample)) == digest
        for ref in sample["artifacts"].values():
            data = (case_root / ref["path"]).read_bytes()
            assert len(data) == ref["byte_length"]
            assert study._sha(data) == ref["sha256"]


def test_analysis_failure_retains_all_attempts_without_training_matrix(
    tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("injected analysis failure")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", fail)
    root = tmp_path / "labels"
    report = generate(roster(tmp_path), root)
    assert report["status"] == "blocked"
    assert report["attempted_training_cases"] == 2
    assert report["verified_training_cases"] == 0
    assert report["samples"] is None
    assert not (root / "training-samples.json").exists()
    for wrapped in report["cases"]:
        invocation = wrapped["row"]["invocations"][0]
        assert invocation["status"] == "raised"
        assert invocation["unknown_execution_work"] is True


@pytest.mark.parametrize("raises", [False, True])
def test_rejected_verification_cannot_publish_samples(tmp_path, monkeypatch, raises):
    original = study.api.validate_bounded_rc_fiber_direct_control_artifacts

    def reject(*args, **kwargs):
        if raises:
            raise RuntimeError("injected verification failure")
        value = original(*args, **kwargs).to_dict()
        value["contract_pass"] = False
        value["errors"] = ["injected verification rejection"]
        return study.api.BoundedRCFiberDirectControlValidationReport(
            study._bytes(value)
        )

    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", reject
    )
    root = tmp_path / "labels"
    report = generate(roster(tmp_path), root)
    assert report["status"] == "blocked"
    assert report["verified_training_cases"] == 0
    assert all(len(c["row"]["invocations"]) == 2 for c in report["cases"])
    assert not (root / "training-samples.json").exists()


def test_interruption_preserves_started_receipt_without_completion(
    tmp_path, monkeypatch
):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", interrupt)
    root = tmp_path / "labels"
    with pytest.raises(KeyboardInterrupt):
        generate(roster(tmp_path), root)
    failure = json.loads((root / "failed.json").read_bytes())
    assert failure["status"] == "interrupted"
    assert failure["unknown_work_until_outcome"] is True
    assert (root / "train-00/baseline/analysis-started.json").is_file()
    assert not (root / "labels.json").exists()
    assert not (root / "training-samples.json").exists()


@pytest.mark.parametrize("invalid", ["source", "split", "limits"])
def test_preflight_rejects_before_output(tmp_path, invalid):
    cases = roster(tmp_path)
    kwargs = {}
    if invalid == "source":
        kwargs["source_revision"] = "short"
    elif invalid == "split":
        cases = cases[:-1]
    else:
        kwargs["history_limits"] = {}
    root = tmp_path / "labels"
    with pytest.raises(ValueError):
        generate(cases, root, **kwargs)
    assert not root.exists()


def test_partial_success_is_retained_but_not_published_as_complete_training(
    tmp_path, monkeypatch
):
    cases = roster(tmp_path)
    rejected = cases[1].model.canonical_model_checksum
    original = study.api.analyze_bounded_rc_fiber_direct_control

    def analyze(model, *args, **kwargs):
        if model.canonical_model_checksum == rejected:
            raise RuntimeError("second training model failed")
        return original(model, *args, **kwargs)

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", analyze)
    root = tmp_path / "labels"
    report = generate(cases, root)
    assert report["status"] == "blocked"
    assert report["verified_training_cases"] == 1
    assert report["attempted_training_cases"] == 2
    assert report["cases"][0]["row"]["full_reference_verification_pass"] is True
    assert report["cases"][1]["row"]["full_reference_verification_pass"] is False
    assert report["samples"] is None
    assert not (root / "training-samples.json").exists()
