"""Synthetic v3 pipeline and frozen-artifact contracts; no solver or fit credit."""

from copy import deepcopy
from dataclasses import replace
import importlib
import json
import os
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.ai import fiber_frame_conditioned_warm_start_learning as v2
from structural_analysis.ai import fiber_frame_warm_start_data as data
from structural_analysis.ai import fiber_frame_warm_start_features as features
from structural_analysis.ai import fiber_frame_warm_start_learning as legacy
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_learning_study as study
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from tests.test_fiber_frame_conditioned_learning_process import (
    _cases,
    _stub_pipeline,
    _write_request,
)
from tests.test_fiber_frame_conditioned_warm_start_learning import _samples


REVISION = "a" * 40
REQUEST_SCHEMA = "rc-fiber-learning-process-request.v3"
STUDY_SCHEMA = "fiber-frame-learned-runtime-study.v3"
POLICY_SCHEMA = "fiber-frame-secant-correction-warm-start-policy.v3"
TARGET = "secant_correction"
CONFIGURATION = {
    "ridge": 1e-6,
    "ood_margin": 0.1,
    "model_conditioning": True,
    "learning_target": TARGET,
}


@pytest.fixture
def correction():
    return importlib.import_module(
        "structural_analysis.ai.fiber_frame_secant_correction_warm_start_learning"
    )


@pytest.fixture(autouse=True)
def no_solver_fit_or_subprocess(monkeypatch, correction):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic contract must not perform analysis, fitting, or launch")

    for owner, name in (
        (public_api, "analyze_public_rc_fiber_frame"),
        (data, "collect_fiber_frame_warm_start_data"),
        (study, "collect_fiber_frame_warm_start_data"),
        (legacy, "train_fiber_frame_warm_start_policy"),
        (study, "train_fiber_frame_warm_start_policy"),
        (v2, "train_fiber_frame_conditioned_warm_start_policy"),
        (correction, "train_fiber_frame_secant_correction_warm_start_policy"),
        (study, "benchmark_public_rc_fiber_frame_runtime_suite"),
        (process.subprocess, "Popen"),
        (np.linalg, "lstsq"),
    ):
        monkeypatch.setattr(owner, name, forbidden)


@pytest.fixture
def cases():
    # Pure ModelIR loading/compilation is allowed; no physical labels are made.
    return _cases()


def _policy(cases, correction, *, version=3):
    samples = _samples()
    runtime = samples[0].runtime_input
    model = runtime.model_features
    dofs = runtime.free_global_dofs
    count = 3 * len(dofs) + 4 + (len(model.feature_names) if version != 1 else 0)
    options = {
        "free_global_dofs": dofs,
        "feature_mean": (0.0,) * count,
        "feature_scale": (1.0,) * count,
        "feature_min": (-1.0,) * count,
        "feature_max": (1.0,) * count,
        "target_scale": (1.0,) * len(dofs),
        "weights": tuple((0.0,) * len(dofs) for _ in range(count + 1)),
        "training_sample_hashes": tuple(
            sorted(row.sample_hash for row in samples if row.split == "train")
        ),
        "ridge": CONFIGURATION["ridge"],
        "ood_margin": CONFIGURATION["ood_margin"],
    }
    if version == 1:
        return legacy.FiberFrameLearnedWarmStartPolicy(
            **options,
            physical_coordinate_scale=runtime.physical_coordinate_scale,
        )
    policy_type = (
        v2.FiberFrameConditionedWarmStartPolicy
        if version == 2
        else correction.FiberFrameSecantCorrectionWarmStartPolicy
    )
    return policy_type(
        **options,
        context_hash=model.context_hash,
        model_feature_names=model.feature_names,
    )


def _pipeline(
    monkeypatch,
    correction,
    policy,
    *,
    failure=None,
    collect_change=None,
    training_change=None,
):
    calls = []
    samples = tuple(_samples())
    dataset_report = legacy.validate_fiber_frame_warm_start_dataset(samples)
    payload = {
        "schema_version": "fiber-frame-warm-start-data-collection.v2",
        "status": "blocked" if failure == "collection" else "ready",
        "model_conditioning": True,
        "model_feature_profile": features.MODEL_FEATURE_PROFILE,
        "data_generation_wall_ns": 100,
        "model_conditioning_preflight_wall_ns": 20,
        "model_conditioning_preflight_is_subset": True,
        "blockers": ["synthetic_collection_block"] if failure == "collection" else [],
        "dataset_report": dataset_report,
    }
    if collect_change is not None:
        collect_change(payload)
    collection = data.FiberFrameWarmStartDataResult(
        payload["status"], samples, json.dumps(payload)
    )

    def collect(selected, **options):
        calls.append(("collection", options))
        assert len(selected) == 6
        return collection

    def train(selected, **options):
        calls.append(("training", options))
        assert selected is collection.samples
        if failure == "training":
            raise RuntimeError("synthetic training failure")
        training_payload = {
            "schema_version": "fiber-frame-secant-correction-warm-start-training-result.v3",
            "policy": policy.to_dict(),
            "training_wall_ns": 3,
            "dataset_report": deepcopy(dataset_report),
        }
        if training_change is not None:
            training_change(training_payload)
        return SimpleNamespace(
            policy=policy,
            training_wall_ns=3,
            to_dict=lambda: deepcopy(training_payload),
        )

    def evaluate(selected, **options):
        calls.append(("evaluation", options))
        assert [case.case_id for case in selected] == ["case-4", "case-5"]
        assert options["ai_policy"] is policy
        assert options["ai_opt_in"] is True
        if failure == "evaluation":
            raise RuntimeError("synthetic evaluation failure")
        if failure == "policy_mutation":
            object.__setattr__(
                policy, "artifact_hash", canonical_hash({"changed": True})
            )
        if failure == "unchanged_hash_mutation":
            old_hash = policy.artifact_hash
            object.__setattr__(policy, "ood_margin", policy.ood_margin + 0.1)
            assert policy.artifact_hash == old_hash
        return SimpleNamespace(
            measurement_contract_pass=failure != "evaluation_blocked",
            to_dict=lambda: {"cases": [{"case_id": "case-4"}, {"case_id": "case-5"}]},
        )

    monkeypatch.setattr(study, "collect_fiber_frame_warm_start_data", collect)
    monkeypatch.setattr(
        correction, "train_fiber_frame_secant_correction_warm_start_policy", train
    )
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", evaluate
    )
    return calls


@pytest.mark.parametrize(
    "target", [None, True, 1, {}, [], "", "parent", "SECANT_CORRECTION"]
)
def test_unknown_learning_target_is_rejected_before_collection(target):
    with pytest.raises(ValueError, match="learning_target"):
        study.run_fiber_frame_learning_study(
            (),
            source_revision=REVISION,
            model_conditioning=True,
            learning_target=target,
        )


def test_correction_requires_model_conditioning_before_collection():
    with pytest.raises(ValueError, match="requires model_conditioning"):
        study.run_fiber_frame_learning_study(
            (), source_revision=REVISION, learning_target=TARGET
        )


def test_v3_request_has_explicit_target_and_leaves_original_profiles_unchanged():
    decoded = process._decode_learning_configuration(
        deepcopy(CONFIGURATION), request_schema=REQUEST_SCHEMA
    )
    assert decoded == CONFIGURATION
    for version, config in (
        (1, {"ridge": 1e-6, "ood_margin": 0.1}),
        (2, {"ridge": 1e-6, "ood_margin": 0.1, "model_conditioning": True}),
    ):
        assert (
            process._decode_learning_configuration(
                config, request_schema=f"rc-fiber-learning-process-request.v{version}"
            )
            == config
        )


@pytest.mark.parametrize("schema", ["v1", "v2", "v4"])
def test_correction_fields_cannot_be_downgraded_or_promoted_to_unknown_request(schema):
    with pytest.raises(ValueError):
        process._decode_learning_configuration(
            CONFIGURATION, request_schema=f"rc-fiber-learning-process-request.{schema}"
        )


@pytest.mark.parametrize(
    "change",
    [
        lambda row: row.pop("learning_target"),
        lambda row: row.pop("model_conditioning"),
        *(
            lambda row, value=value: row.update(learning_target=value)
            for value in (None, True, 1, "parent_increment", "other")
        ),
        *(
            lambda row, value=value: row.update(model_conditioning=value)
            for value in (False, 1, "true", None)
        ),
        lambda row: row.update(unrecognized_profile=True),
    ],
)
def test_v3_request_flags_and_fields_are_strict(change):
    config = deepcopy(CONFIGURATION)
    change(config)
    with pytest.raises(ValueError):
        process._decode_learning_configuration(config, request_schema=REQUEST_SCHEMA)


def test_v3_pipeline_keeps_v2_collection_and_one_frozen_policy(
    cases, correction, monkeypatch
):
    policy = _policy(cases, correction)
    calls = _pipeline(monkeypatch, correction, policy)
    ticks = iter((0, 10, 20, 30, 50, 80))
    monkeypatch.setattr(study, "perf_counter_ns", ticks.__next__)
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, phase_runtime=recorder, **CONFIGURATION
    ).to_dict()
    assert [name for name, _ in calls] == ["collection", "training", "evaluation"]
    assert calls[0][1] == {"source_revision": REVISION, "model_conditioning": True}
    assert calls[1][1] == {"ridge": 1e-6, "ood_margin": 0.1}
    assert payload["schema_version"] == STUDY_SCHEMA
    assert payload["status"] == "ready"
    assert payload["learning_target"] == TARGET
    assert payload["hyperparameters_declared_before_collection"] == CONFIGURATION
    assert payload["data_collection"]["schema_version"].endswith(".v2")
    assert payload["training"]["policy"] == policy.to_dict()
    costs = payload["cost_accounting"]
    assert costs["data_generation_wall_ns"] == 100
    assert costs["training_wall_ns"] == 3
    assert costs["training_attempt_wall_ns"] == 10
    assert costs["evaluation_wall_ns"] == 20
    assert costs["study_wall_ns"] == 80
    assert costs["amortized_upfront_scope"] == (
        "data_generation_plus_entire_training_attempt_excluding_offline_evaluation"
    )
    assert "model_conditioning_preflight_wall_ns" not in costs
    assert len(payload["case_break_even"]) == 4
    assert all(
        row["data_generation_and_training_wall_ns"] == 110
        and row["projected_reuses_to_amortize_upfront_cost"] is None
        for row in payload["case_break_even"]
    )
    assert all(
        row["status"] == "completed" for row in recorder.to_dict()["phases"].values()
    )
    assert "study_phases" not in payload
    assert payload["report_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )


@pytest.mark.parametrize(
    "failure,statuses,call_count",
    [
        ("collection", ["blocked", "skipped", "skipped"], 1),
        ("training", ["completed", "exception", "skipped"], 2),
        ("evaluation", ["completed", "completed", "exception"], 3),
        ("evaluation_blocked", ["completed", "completed", "blocked"], 3),
        ("policy_mutation", ["completed", "completed", "exception"], 3),
        ("unchanged_hash_mutation", ["completed", "completed", "exception"], 3),
    ],
)
def test_v3_failures_preserve_attempted_cost_and_phase_prefix(
    cases, correction, monkeypatch, failure, statuses, call_count
):
    calls = _pipeline(
        monkeypatch, correction, _policy(cases, correction), failure=failure
    )
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, phase_runtime=recorder, **CONFIGURATION
    ).to_dict()
    assert payload["schema_version"] == STUDY_SCHEMA
    assert payload["status"] == "blocked"
    assert len(calls) == call_count
    assert [row["status"] for row in recorder.to_dict()["phases"].values()] == statuses
    costs = payload["cost_accounting"]
    assert (costs["training_attempt_wall_ns"] is None) is (call_count < 2)
    assert (costs["evaluation_wall_ns"] is None) is (call_count < 3)
    assert (costs["training_wall_ns"] is None) is (
        failure in {"collection", "training"}
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda row: row.update(
            schema_version="fiber-frame-warm-start-data-collection.v1"
        ),
        lambda row: row.update(model_conditioning=1),
        lambda row: row.update(model_feature_profile="unknown"),
    ],
)
def test_v3_collection_profile_mismatch_never_reaches_training(
    cases, correction, monkeypatch, change
):
    calls = _pipeline(
        monkeypatch, correction, _policy(cases, correction), collect_change=change
    )
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    with pytest.raises(ValueError, match="collection profile mismatch"):
        study.run_fiber_frame_learning_study(
            cases, source_revision=REVISION, phase_runtime=recorder, **CONFIGURATION
        )
    assert [name for name, _ in calls] == ["collection"]
    assert [row["status"] for row in recorder.to_dict()["phases"].values()] == [
        "exception",
        "skipped",
        "skipped",
    ]


def test_v3_phase_sidecar_never_changes_report_bytes(cases, correction, monkeypatch):
    _pipeline(monkeypatch, correction, _policy(cases, correction))
    encoded = []
    for phase in (None, study.FiberFrameLearningStudyPhaseRecorder()):
        monkeypatch.setattr(study, "perf_counter_ns", iter(range(0, 1000, 10)).__next__)
        encoded.append(
            process._bytes(
                study.run_fiber_frame_learning_study(
                    cases,
                    source_revision=REVISION,
                    phase_runtime=phase,
                    **CONFIGURATION,
                ).to_dict()
            )
        )
    assert encoded[0] == encoded[1]


def test_v3_phase_cost_includes_report_decode_and_frozen_checks_once(
    cases, correction, monkeypatch
):
    _pipeline(monkeypatch, correction, _policy(cases, correction))
    elapsed = [0]
    monkeypatch.setattr(study, "perf_counter_ns", lambda: elapsed[0])
    collect = study.collect_fiber_frame_warm_start_data
    train = correction.train_fiber_frame_secant_correction_warm_start_policy
    decode = correction.decode_fiber_frame_secant_correction_warm_start_policy
    evaluate = study.benchmark_public_rc_fiber_frame_runtime_suite

    def timed_collect(*args, **kwargs):
        result = collect(*args, **kwargs)
        elapsed[0] += 100
        return result

    def timed_train(*args, **kwargs):
        result = train(*args, **kwargs)
        elapsed[0] += 2
        original = result.to_dict
        result.training_wall_ns = 2

        def convert():
            payload = original()
            payload["training_wall_ns"] = 2
            elapsed[0] += 3
            return payload

        result.to_dict = convert
        return result

    def timed_decode(*args, **kwargs):
        result = decode(*args, **kwargs)
        elapsed[0] += 5
        return result

    def timed_evaluate(*args, **kwargs):
        result = evaluate(*args, **kwargs)
        elapsed[0] += 7
        original = result.to_dict

        def convert():
            elapsed[0] += 11
            return original()

        result.to_dict = convert
        return result

    monkeypatch.setattr(study, "collect_fiber_frame_warm_start_data", timed_collect)
    monkeypatch.setattr(
        correction, "train_fiber_frame_secant_correction_warm_start_policy", timed_train
    )
    monkeypatch.setattr(
        correction,
        "decode_fiber_frame_secant_correction_warm_start_policy",
        timed_decode,
    )
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", timed_evaluate
    )
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, **CONFIGURATION
    ).to_dict()
    assert payload["status"] == "ready"
    costs = payload["cost_accounting"]
    assert costs["data_generation_wall_ns"] == 100
    assert costs["training_wall_ns"] == 2
    assert costs["training_attempt_wall_ns"] == 2 + 3 + 5
    assert costs["evaluation_wall_ns"] == 7 + 11
    assert costs["study_wall_ns"] == 100 + 2 + 3 + 5 + 7 + 11
    assert all(
        row["data_generation_and_training_wall_ns"] == 110
        for row in payload["case_break_even"]
    )


@pytest.mark.parametrize("conditioned_mode", [False, True])
def test_explicit_parent_increment_preserves_v1_v2_default_bytes_and_clock_calls(
    cases, monkeypatch, conditioned_mode
):
    _stub_pipeline(monkeypatch, conditioned_mode=conditioned_mode)
    encoded = []
    clock_counts = []
    for extra in ({}, {"learning_target": "parent_increment"}):
        calls = []

        def clock():
            calls.append(True)
            return len(calls) * 10

        monkeypatch.setattr(study, "perf_counter_ns", clock)
        result = study.run_fiber_frame_learning_study(
            cases,
            source_revision=REVISION,
            model_conditioning=conditioned_mode,
            **extra,
        ).to_dict()
        encoded.append(process._bytes(result))
        clock_counts.append(len(calls))
    assert encoded[0] == encoded[1]
    assert clock_counts == [6, 6]
    payload = json.loads(encoded[0])
    assert payload["schema_version"] == (
        "fiber-frame-learned-runtime-study.v2"
        if conditioned_mode
        else "fiber-frame-learned-runtime-study.v1"
    )
    assert "learning_target" not in payload
    assert (
        "learning_target" not in payload["hyperparameters_declared_before_collection"]
    )


@pytest.mark.parametrize(
    "change", ["schema", "policy", "dataset", "membership", "ridge", "ood"]
)
def test_v3_training_metadata_is_bound_before_any_evaluation(
    cases, correction, monkeypatch, change
):
    policy = _policy(cases, correction)
    if change == "membership":
        policy = replace(
            policy,
            training_sample_hashes=tuple(
                sorted(canonical_hash({"detached": n}) for n in range(2))
            ),
        )
    elif change in {"ridge", "ood"}:
        policy = replace(
            policy, **{"ridge" if change == "ridge" else "ood_margin": 0.2}
        )

    def alter(payload):
        if change == "schema":
            payload["schema_version"] = (
                "fiber-frame-conditioned-warm-start-training-result.v2"
            )
        elif change == "policy":
            payload["policy"] = _policy(cases, correction, version=2).to_dict()
        elif change == "dataset":
            payload["dataset_report"]["external_provenance_verified"] = True

    calls = _pipeline(monkeypatch, correction, policy, training_change=alter)
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, phase_runtime=recorder, **CONFIGURATION
    ).to_dict()
    assert [name for name, _ in calls] == ["collection", "training"]
    assert payload["status"] == "blocked"
    assert payload["failure"]["kind"] == "learning_or_evaluation_failed"
    assert payload["failure"]["exception_type"] in {
        "ValueError",
        "FiberFrameWarmStartLearningError",
    }
    assert payload["evaluation"] is None
    assert payload["cost_accounting"]["training_attempt_wall_ns"] is not None
    assert payload["cost_accounting"]["evaluation_wall_ns"] is None
    assert [row["status"] for row in recorder.to_dict()["phases"].values()] == [
        "completed",
        "exception",
        "skipped",
    ]


def test_v2_policy_object_cannot_be_used_by_v3_training(cases, correction, monkeypatch):
    calls = _pipeline(monkeypatch, correction, _policy(cases, correction, version=2))
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, **CONFIGURATION
    ).to_dict()
    assert [name for name, _ in calls] == ["collection", "training"]
    assert payload["status"] == "blocked"
    assert payload["evaluation"] is None


@pytest.mark.parametrize("version", [1, 2, 3])
def test_frozen_process_policy_loader_preserves_every_supported_profile(
    cases, correction, version
):
    policy = _policy(cases, correction, version=version)
    raw = process._bytes(policy.to_dict())
    decoded = process._decode_policy(raw)
    assert type(decoded) is type(policy)
    assert process._bytes(decoded.to_dict()) == raw
    assert decoded.artifact_hash == policy.artifact_hash


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "fiber-frame-conditioned-warm-start-policy.v2"),
        ("schema_version", "fiber-frame-secant-correction-warm-start-policy.v4"),
        ("policy_version", "v2"),
        ("prediction_target", "next_accepted_physical_coordinate_increment_m_and_rad"),
        ("model_feature_profile", "unknown"),
    ],
)
def test_frozen_v3_loader_rejects_rehashed_profile_substitution(
    cases, correction, field, value
):
    payload = _policy(cases, correction).to_dict()
    payload[field] = value
    payload["artifact_hash"] = canonical_hash(
        {key: item for key, item in payload.items() if key != "artifact_hash"}
    )
    # Unknown schemas retain the existing legacy loader's fail-closed KeyError;
    # this check promises rejection, not a new public exception normalization.
    with pytest.raises((ValueError, KeyError)):
        process._decode_policy(process._bytes(payload))


def _v3_request(directory, cases):
    path = _write_request(directory, cases, conditioned_mode=True)
    request = json.loads(path.read_bytes())
    request.update(
        schema_version=REQUEST_SCHEMA, learning_configuration=deepcopy(CONFIGURATION)
    )
    path.write_bytes(process._bytes(request))
    return path


def _worker_study(monkeypatch, *, change=None):
    calls = []

    def run(selected, *, phase_runtime, **options):
        calls.append(options)
        assert len(selected) == 6
        phase_runtime._begin_study()
        for name in ("data_collection", "training_attempt", "evaluation"):
            with phase_runtime._observe(name):
                pass
        payload = {
            "schema_version": STUDY_SCHEMA,
            "status": "ready",
            "model_conditioning": True,
            "model_feature_profile": features.MODEL_FEATURE_PROFILE,
            "learning_target": TARGET,
            "hyperparameters_declared_before_collection": deepcopy(CONFIGURATION),
        }
        if change:
            change(payload)
        return study.FiberFrameLearningStudyResult("ready", payload)

    monkeypatch.setattr(study, "run_fiber_frame_learning_study", run)
    return calls


def test_in_process_v3_worker_passes_explicit_flags_and_keeps_existing_resource_profile(
    cases, tmp_path, monkeypatch
):
    request = _v3_request(tmp_path, cases)
    calls = _worker_study(monkeypatch)
    output = tmp_path / "output"
    output.mkdir()
    assert process._worker(request, REVISION, output, process._LEARNING) == 0
    assert len(calls) == 1
    assert {key: calls[0][key] for key in CONFIGURATION} == CONFIGURATION
    raw = (output / "study.json").read_bytes()
    resource = json.loads((output / "resources.json").read_bytes())
    assert json.loads(raw)["schema_version"] == STUDY_SCHEMA
    assert resource["schema_version"] == "rc-fiber-learning-process-resources.v1"
    assert (
        resource["study_phases"]["schema_version"]
        == "fiber-frame-learning-study-phase-runtime.v1"
    )
    assert resource["study_status"] == "ready"
    assert resource["per_phase_peak_memory_bytes"] is None
    assert resource["source_revision_is_attestation"] is False
    assert (
        process._resource_validation_failure(
            resource,
            os.getpid(),
            REVISION,
            {"sha256": process._digest(raw), "byte_length": len(raw)},
            process._LEARNING,
        )
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda row: row.update(schema_version="fiber-frame-learned-runtime-study.v2"),
        lambda row: row.pop("learning_target"),
        lambda row: row.update(learning_target="parent_increment"),
        lambda row: row.update(model_conditioning=1),
        lambda row: row.update(model_feature_profile="other"),
        lambda row: row["hyperparameters_declared_before_collection"].pop(
            "learning_target"
        ),
        lambda row: row["hyperparameters_declared_before_collection"].update(
            learning_target="parent_increment"
        ),
    ],
)
def test_worker_rejects_v3_study_profile_downgrade_without_publishing_report(
    cases, tmp_path, monkeypatch, change
):
    request = _v3_request(tmp_path, cases)
    calls = _worker_study(monkeypatch, change=change)
    output = tmp_path / "output"
    output.mkdir()
    assert process._worker(request, REVISION, output, process._LEARNING) == 3
    assert len(calls) == 1
    assert not (output / "study.json").exists()
    assert not (output / "resources.json").exists()
    failure = json.loads((output / "failure.json").read_bytes())
    assert failure["stage"] == "learning_study"
    assert failure["measurement_contract_pass"] is False
    assert all(
        row["status"] == "completed"
        for row in failure["study_phases"]["phases"].values()
    )


@pytest.mark.parametrize(
    "change", ["downgrade", "missing_target", "wrong_target", "missing_conditioning"]
)
def test_worker_rejects_invalid_v3_request_before_model_or_study(
    cases, tmp_path, monkeypatch, change
):
    from structural_analysis.io.neutral import loader

    request_path = _v3_request(tmp_path, cases)
    request = json.loads(request_path.read_bytes())
    config = request["learning_configuration"]
    if change == "downgrade":
        request["schema_version"] = "rc-fiber-learning-process-request.v2"
    elif change == "missing_target":
        config.pop("learning_target")
    elif change == "wrong_target":
        config["learning_target"] = "parent_increment"
    else:
        config.pop("model_conditioning")
    request_path.write_bytes(process._bytes(request))

    def forbidden(*args, **kwargs):
        pytest.fail("invalid request must fail before model loading or study dispatch")

    monkeypatch.setattr(loader, "load_neutral_json_bytes", forbidden)
    monkeypatch.setattr(study, "run_fiber_frame_learning_study", forbidden)
    output = tmp_path / "output"
    output.mkdir()
    assert process._worker(request_path, REVISION, output, process._LEARNING) == 3
    assert {path.name for path in output.iterdir()} == {"failure.json"}
    failure = json.loads((output / "failure.json").read_bytes())
    assert failure["stage"] == "input_contract"
    assert "study_phases" not in failure
