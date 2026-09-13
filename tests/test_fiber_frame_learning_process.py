"""Fresh-process study accounting; synthetic splits are not independent evidence."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameRuntimeBenchmarkConfig,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


def _digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _request_file(tmp_path):
    example = (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_bytes()
    rows = []
    for index, split in enumerate(("train", "validation", "holdout")):
        payload = json.loads(example)
        payload["sections"][0]["width_m"] = 0.4 + index * 0.001
        model_path = tmp_path / f"model-{index}.json"
        model_path.write_text(json.dumps(payload))
        rows.append(
            {
                "case_id": f"case-{index}",
                "model_file": model_path.name,
                "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
                "project_id": f"project-{index}",
                "geometry_family_id": f"geometry-{index}",
                "load_history_id": f"history-{index}",
                "split": split,
            }
        )
    request = {
        "schema_version": "rc-fiber-learning-process-request.v1",
        "cases": rows,
        "benchmark_configuration": asdict(
            FiberFrameRuntimeBenchmarkConfig(repetitions=1, warmup_repetitions=0)
        ),
        "learning_configuration": {"ridge": 1e-6, "ood_margin": 0.1},
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return path


def test_real_fresh_process_charges_entire_study_and_binds_source_model_report_bytes(
    tmp_path, monkeypatch
):
    request = _request_file(tmp_path)
    # A caller's directory must not redirect the worker to another checkout.
    shadow = tmp_path / "structural_analysis"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('wrong checkout imported')")
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_learning_process(
        request, source_revision=REVISION, output_directory=output
    )
    assert manifest["schema_version"] == "rc-fiber-learning-process-manifest.v1"
    assert manifest["status"] == "ready"
    assert manifest["worker_exit_code"] == 0
    assert manifest["fresh_python_process"] is True
    assert manifest["worker_measurements_available"] is True
    assert json.loads((output / "manifest.json").read_bytes()) == manifest

    raw = (output / "study.json").read_bytes()
    study = json.loads(raw)
    resources = json.loads((output / "resources.json").read_bytes())
    assert resources["schema_version"] == "rc-fiber-learning-process-resources.v1"
    assert resources["worker_pid"] == manifest["worker_pid"] != os.getpid()
    assert resources["source_revision"] == study["source_revision"] == REVISION
    assert resources["status"] == study["status"] == "ready"
    assert resources["study_status"] == study["status"]
    assert resources["measurement_contract_pass"] is True
    assert resources["study_sha256"] == _digest(raw)
    assert (
        resources["study_byte_length"] == resources["report_bytes_written"] == len(raw)
    )
    assert "suite_sha256" not in resources
    assert "suite_byte_length" not in resources
    assert "suite.json" not in manifest["artifacts"]

    collection = study["data_collection"]
    assert collection["dataset_complete"] is True
    assert collection["case_count"] == 3
    assert collection["failed_case_count"] == 0
    assert collection["sample_count"] == 6
    assert collection["source_revision"] == REVISION
    assert {row["split"]: row["sample_count"] for row in collection["cases"]} == {
        "train": 2,
        "validation": 2,
        "holdout": 2,
    }
    inputs = {Path(row["path"]): row for row in resources["inputs"]}
    assert set(inputs) == {request, *(tmp_path / f"model-{i}.json" for i in range(3))}
    for path, observation in inputs.items():
        data = path.read_bytes()
        assert observation["sha256"] == _digest(data)
        assert observation["byte_length"] == len(data)
        assert observation["read_wall_ns"] > 0
    assert resources["input_bytes_read"] == sum(
        row["byte_length"] for row in inputs.values()
    )
    for index, case in enumerate(collection["cases"]):
        model_path = tmp_path / f"model-{index}.json"
        model = load_neutral_json_bytes(
            model_path.read_bytes(), source_path=str(model_path)
        )
        assert case["canonical_model_checksum"] == model.canonical_model_checksum
        assert case["input_checksum"] == model.input_checksum
    for binding in collection["sample_source_bindings"]:
        assert binding["source_revision"] == REVISION
        case = next(
            row for row in collection["cases"] if row["case_id"] == binding["case_id"]
        )
        assert binding["canonical_model_checksum"] == case["canonical_model_checksum"]
        assert binding["input_checksum"] == case["input_checksum"]

    train_hashes = sorted(
        row["sample_hash"] for row in collection["samples"] if row["split"] == "train"
    )
    assert study["training"]["policy"]["training_sample_hashes"] == train_hashes
    evaluation = study["evaluation"]
    assert {row["case_id"] for row in evaluation["cases"]} == {"case-1", "case-2"}
    assert evaluation["coverage"]["fully_verified_run_count"] == 6
    assert evaluation["coverage"]["verified_reference_episode_count"] == 2
    assert evaluation["coverage"]["unsuccessful_case_ids"] == []

    assert (
        0
        < resources["workload_cpu_process_time_ns"]
        <= resources["cpu_process_time_ns"]
    )
    assert 0 < resources["workload_wall_ns"] < manifest["launch_to_exit_wall_ns"]
    assert resources["input_read_wall_ns"] > 0
    assert resources["report_encode_wall_ns"] > 0
    assert resources["report_write_flush_fsync_wall_ns"] > 0
    if sys.platform == "linux":
        assert resources["peak_memory_bytes"] > 0
    else:
        assert resources["peak_memory_bytes"] is None
    assert resources["per_strategy_peak_memory_bytes"] is None
    assert resources["per_phase_peak_memory_bytes"] is None
    phases = resources["study_phases"]
    assert phases["schema_version"] == "fiber-frame-learning-study-phase-runtime.v1"
    assert phases["study_started"] is True
    assert phases["measurement_contract_pass"] is True
    assert phases["local_timing_evidence_eligible"] is True
    assert set(phases["phases"]) == {
        "data_collection",
        "training_attempt",
        "evaluation",
    }
    for name, phase in phases["phases"].items():
        assert phase["status"] == "completed", name
        assert 0 < phase["wall_ns"] <= resources["workload_wall_ns"]
        assert (
            0
            <= phase["cpu_process_time_ns"]
            <= resources["workload_cpu_process_time_ns"]
        )
        assert phase["reason"] is None
        assert phase["exception_type"] is None
        assert phase["measurement_errors"] == []
    assert (
        sum(phase["wall_ns"] for phase in phases["phases"].values())
        <= resources["workload_wall_ns"]
    )
    assert (
        sum(phase["cpu_process_time_ns"] for phase in phases["phases"].values())
        <= resources["workload_cpu_process_time_ns"]
    )
    assert phases["per_phase_peak_memory_bytes"] is None
    assert phases["physical_validation_claimed"] is False
    assert phases["generalized_speedup_claimed"] is False
    assert resources["gpu_time_ns"] is None
    for key in (
        "resource_sidecar_io_included",
        "source_revision_is_attestation",
        "independent_hardware_validation",
        "generalized_speedup_claimed",
    ):
        assert resources[key] is False
    assert study["claims"]["training_uses_only_train_targets"] is True
    for key in (
        "hyperparameters_selected_using_holdout",
        "independent_project_generalization_verified",
        "blind_prediction_verified",
        "generalized_speedup_claimed",
        "production_promotion_eligible",
    ):
        assert study["claims"][key] is False
    assert (
        collection["claim_boundary"]["split_labels_prove_independent_projects"] is False
    )
    for name, artifact in manifest["artifacts"].items():
        data = (output / name).read_bytes()
        assert artifact == {"byte_length": len(data), "sha256": _digest(data)}

    # Validate corruption against the same completed run without regenerating
    # labels or refitting a model for each metadata-only mutation.
    for mutation in (
        "missing_phase",
        "detached_schema",
        "boolean_timing",
        "promoted_physical_flag",
        "phase_cpu_exceeds_whole_workload",
    ):
        altered = deepcopy(resources)
        phases = altered["study_phases"]
        if mutation == "missing_phase":
            del phases["phases"]["evaluation"]
        elif mutation == "detached_schema":
            phases["schema_version"] = "unbound-phase-runtime.v1"
        elif mutation == "boolean_timing":
            phases["phases"]["training_attempt"]["wall_ns"] = True
        elif mutation == "promoted_physical_flag":
            phases["physical_validation_claimed"] = True
        else:
            phases["phases"]["training_attempt"]["cpu_process_time_ns"] = (
                altered["workload_cpu_process_time_ns"] + 1
            )
        assert (
            process._resource_validation_failure(
                altered,
                manifest["worker_pid"],
                REVISION,
                manifest["artifacts"]["study.json"],
                profile=process._LEARNING,
            )
            == "worker_resources_contract_invalid"
        ), mutation


@pytest.mark.parametrize(
    "mutation",
    [
        "runtime_schema",
        "policy_file",
        "missing_identity",
        "split",
        "ridge",
        "extra_learning_key",
    ],
)
def test_invalid_learning_request_preserves_failure_without_downstream_credit(
    tmp_path, mutation
):
    request = _request_file(tmp_path)
    document = json.loads(request.read_bytes())
    if mutation == "runtime_schema":
        document["schema_version"] = "rc-fiber-runtime-process-request.v1"
    elif mutation == "policy_file":
        document["policy_file"] = None
    elif mutation == "missing_identity":
        del document["cases"][0]["geometry_family_id"]
    elif mutation == "split":
        document["cases"][0]["split"] = "test"
    elif mutation == "ridge":
        document["learning_configuration"]["ridge"] = -1
    else:
        document["learning_configuration"]["holdout_tuning"] = True
    request.write_text(json.dumps(document))
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_learning_process(
        request, source_revision=REVISION, output_directory=output
    )
    failure = json.loads((output / "failure.json").read_bytes())
    assert manifest["schema_version"] == "rc-fiber-learning-process-manifest.v1"
    assert manifest["status"] == "blocked"
    assert manifest["worker_exit_code"] == 3
    assert manifest["worker_measurements_available"] is False
    assert failure["stage"] == "input_contract"
    assert failure["measurement_contract_pass"] is False
    assert "study.json" not in manifest["artifacts"]
    assert "resources.json" not in manifest["artifacts"]
    assert not (output / "study.json").exists()
    assert not (output / "resources.json").exists()


def _no_op_phase_receipt(statuses):
    """Structural telemetry fixture only; no study or numerical workload runs."""
    from structural_analysis.benchmark.fiber_frame_learning_study import (
        FiberFrameLearningStudyPhaseRecorder,
    )

    recorder = FiberFrameLearningStudyPhaseRecorder()
    recorder._begin_study()
    for name, status in zip(
        ("data_collection", "training_attempt", "evaluation"), statuses, strict=True
    ):
        if status == "skipped":
            continue
        try:
            with recorder._observe(name) as row:
                if status == "blocked":
                    row.update(status="blocked", reason="fixture_blocked")
                elif status == "exception":
                    raise RuntimeError("fixture_exception")
        except RuntimeError:
            assert status == "exception"
    payload = recorder.to_dict()
    assert payload["physical_validation_claimed"] is False
    return payload


def _enclosing_phase_resource(study_status):
    return {
        "study_status": study_status,
        "workload_wall_ns": 10**12,
        "workload_cpu_process_time_ns": 10**12,
    }


@pytest.mark.parametrize(
    "phase_name", ["data_collection", "training_attempt", "evaluation"]
)
@pytest.mark.parametrize("mutation", ["missing", "skipped"])
def test_fast_phase_prefix_ready_rejects_missing_or_skipped_phase(phase_name, mutation):
    payload = _no_op_phase_receipt(("completed", "completed", "completed"))
    enclosing = _enclosing_phase_resource("ready")
    assert process._study_phases_valid(payload, enclosing)
    if mutation == "missing":
        del payload["phases"][phase_name]
    else:
        payload["phases"][phase_name].update(
            status="skipped",
            reason="phase_not_reached",
            wall_ns=None,
            cpu_process_time_ns=None,
        )
    assert payload["measurement_contract_pass"] is True
    assert not process._study_phases_valid(payload, enclosing)


@pytest.mark.parametrize(
    "statuses",
    [
        ("blocked", "completed", "skipped"),
        ("exception", "skipped", "completed"),
        ("completed", "skipped", "completed"),
    ],
)
def test_fast_phase_prefix_blocked_rejects_execution_after_stop(statuses):
    payload = _no_op_phase_receipt(statuses)
    assert payload["measurement_contract_pass"] is True
    assert not process._study_phases_valid(
        payload, _enclosing_phase_resource("blocked")
    )


@pytest.mark.parametrize("collection_status", ["blocked", "exception"])
def test_fast_phase_prefix_retains_blocked_collection_and_skipped_downstream(
    collection_status,
):
    payload = _no_op_phase_receipt((collection_status, "skipped", "skipped"))
    assert process._study_phases_valid(payload, _enclosing_phase_resource("blocked"))
    assert payload["measurement_contract_pass"] is True
    assert payload["phases"]["data_collection"]["wall_ns"] >= 0
    assert payload["phases"]["data_collection"]["cpu_process_time_ns"] >= 0
    for name in ("training_attempt", "evaluation"):
        row = payload["phases"][name]
        assert row["status"] == "skipped"
        assert row["wall_ns"] is row["cpu_process_time_ns"] is None
