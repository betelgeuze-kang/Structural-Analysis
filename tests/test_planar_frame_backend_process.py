"""Backend worker contracts; synthetic failures grant no physical authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from structural_analysis.api.planar_frame import PlanarFrameConfig
from structural_analysis.benchmark import planar_frame_backend_process as process
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40
BACKENDS = (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
)
SI_GROUPS = (
    "node_displacements",
    "support_reactions",
    "member_end_forces",
    "section_results",
    "fiber_results",
)


def _request() -> dict:
    configuration = asdict(PlanarFrameConfig(load_steps=2))
    configuration.pop("matrix_backend")
    return {
        "schema_version": "planar-frame-backend-experiment-request.v1",
        "cases": [
            {
                "case_id": "portal",
                "model_file": "model.json",
                "configuration": configuration,
            }
        ],
        "backends": list(BACKENDS),
        "repetitions": 1,
        "warmups": 0,
        "tolerances": {
            group: {"absolute": 1.0e-9, "relative": 1.0e-9} for group in SI_GROUPS
        },
    }


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_request(directory: Path, document: dict | None = None) -> Path:
    document = _request() if document is None else document
    path = directory / "request.json"
    path.write_bytes(_json_bytes(document))
    return path


@pytest.fixture(scope="module")
def observed_experiment():
    """Four tiny public API calls shared by all output mutation regressions.

    Preserve raw artifacts outside pytest's rotating temporary roots. This is
    correctness integration, with no timing comparison or independent V&V claim.
    """
    saved = os.environ.get("STRUCTURAL_PLANAR_BACKEND_TEST_ARTIFACTS")
    if saved:
        directory = Path(saved)
        output = directory / "experiment"
        return {
            "directory": directory,
            "output": output,
            "request": json.loads((output / "request.json").read_bytes()),
            "request_path": directory / "request.json",
            "originals": {
                path.name: path.read_bytes() for path in directory.glob("*.json")
            },
            "report": json.loads((output / "experiment.json").read_bytes()),
        }
    directory = Path(tempfile.mkdtemp(prefix="structural-planar-backend-tests-"))
    source = ROOT / "examples/planar_frame_rc_portal.json"
    request = _request()
    request["cases"] = []
    originals = {}
    for index, width in enumerate((0.4, 0.401)):
        model = json.loads(source.read_bytes())
        model["sections"][0]["parameters"]["width_m"] = width
        model["provenance"]["source_sha256"] = canonical_hash(
            {key: value for key, value in model.items() if key != "provenance"}
        )
        model_file = directory / f"model-{index}.json"
        model_file.write_bytes(_json_bytes(model))
        originals[model_file.name] = model_file.read_bytes()
        case = deepcopy(_request()["cases"][0])
        case.update(case_id=f"portal-{index}", model_file=model_file.name)
        request["cases"].append(case)
    request["backends"] = [BACKENDS[0], BACKENDS[2]]
    request_path = _write_request(directory, request)
    originals[request_path.name] = request_path.read_bytes()
    output = directory / "experiment"
    report = process.run_planar_frame_backend_experiment(
        request_path,
        source_revision=REVISION,
        output_directory=output,
        timeout_seconds=120,
    )
    return {
        "directory": directory,
        "output": output,
        "request": request,
        "request_path": request_path,
        "originals": originals,
        "report": report,
    }


def _changed(path: tuple, value) -> dict:
    document = _request()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return document


@pytest.mark.parametrize(
    "raw",
    (
        b"{}",
        b"[]",
        b' {"schema_version":"x","schema_version":"y"}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":1e999}',
        b"\xff",
    ),
)
def test_malformed_json_request_rejected(raw):
    with pytest.raises(ValueError):
        process._decode_request(raw)


@pytest.mark.parametrize(
    "path,value",
    (
        (("schema_version",), "planar-frame-backend-experiment-request.v2"),
        (("unknown",), True),
        (("cases",), []),
        (("cases",), {}),
        (("cases", 0, "case_id"), ""),
        (("cases", 0, "case_id"), True),
        (("cases", 0, "model_file"), ""),
        (("cases", 0, "model_file"), 1),
        (("cases", 0, "extra"), None),
        (("cases", 0, "configuration", "matrix_backend"), BACKENDS[0]),
        (("cases", 0, "configuration", "control"), "unknown"),
        (("cases", 0, "configuration", "load_steps"), True),
        (("cases", 0, "configuration", "load_steps"), 0),
        (("cases", 0, "configuration", "load_steps"), 1),
        (("cases", 0, "configuration", "load_steps"), 65),
        (("cases", 0, "configuration", "load_steps"), 1.0),
        (("cases", 0, "configuration", "maximum_iterations"), True),
        (("cases", 0, "configuration", "maximum_iterations"), 0),
        (("cases", 0, "configuration", "maximum_iterations"), 201),
        (("cases", 0, "configuration", "residual_tolerance"), True),
        (("cases", 0, "configuration", "residual_tolerance"), 0),
        (("cases", 0, "configuration", "increment_tolerance_m"), -1),
        (("backends",), []),
        (("backends",), [BACKENDS[0], BACKENDS[0]]),
        (("backends",), ["unknown"]),
        (("backends",), [True]),
        (("repetitions",), True),
        (("repetitions",), 0),
        (("repetitions",), 1.0),
        (("warmups",), True),
        (("warmups",), -1),
        (("tolerances",), {}),
        (("tolerances", "fiber_results", "absolute"), True),
        (("tolerances", "fiber_results", "absolute"), -1),
        (("tolerances", "fiber_results", "relative"), "1e-9"),
        (("tolerances", "fiber_results", "extra"), 0),
    ),
)
def test_invalid_declaration_rejected(path, value):
    with pytest.raises(ValueError):
        process._decode_request(_json_bytes(_changed(path, value)))


def test_duplicate_case_identity_and_nested_json_keys_rejected():
    document = _request()
    document["cases"].append(deepcopy(document["cases"][0]))
    with pytest.raises(ValueError):
        process._decode_request(_json_bytes(document))
    raw = _json_bytes(_request()).replace(
        b'"load_steps": 2', b'"load_steps": 2, "load_steps": 3'
    )
    with pytest.raises(ValueError):
        process._decode_request(raw)


def test_zero_comparison_tolerances_are_a_valid_explicit_contract():
    document = _request()
    document["tolerances"] = {
        group: {"absolute": 0, "relative": 0.0} for group in SI_GROUPS
    }
    assert process._decode_request(_json_bytes(document)) == document


@pytest.mark.parametrize("control", ("arc_length", "direct_displacement_control"))
def test_recognized_unsupported_controls_reach_public_not_run_contract(control):
    request = _changed(("cases", 0, "configuration", "control"), control)
    assert process._decode_request(_json_bytes(request)) == request


@pytest.mark.parametrize("literal", (b"NaN", b"Infinity", b"-Infinity", b"1e999"))
def test_nonfinite_nested_configuration_and_tolerance_rejected(literal):
    raw = _json_bytes(_request())
    for original in (b'"residual_tolerance": 1e-10', b'"absolute": 1e-09'):
        assert original in raw
        malformed = raw.replace(original, original.split(b": ")[0] + b": " + literal)
        with pytest.raises(ValueError):
            process._decode_request(malformed)


def test_schedule_rotates_each_case_round_and_restarts_rotation_for_measurement():
    request = _request()
    second = deepcopy(request["cases"][0])
    second["case_id"] = "portal-second"
    request["cases"].append(second)
    request.update(warmups=1, repetitions=2)
    slots = process._schedule(request)
    observed = [
        (row["phase"], row["repetition"], row["case_id"], row["backend"])
        for row in slots
    ]
    expected_rounds = (
        ("warmup", 0, "portal", (0, 1, 2)),
        ("warmup", 0, "portal-second", (1, 2, 0)),
        ("measurement", 0, "portal", (0, 1, 2)),
        ("measurement", 0, "portal-second", (1, 2, 0)),
        ("measurement", 1, "portal", (1, 2, 0)),
        ("measurement", 1, "portal-second", (2, 0, 1)),
    )
    assert observed == [
        (phase, repetition, case_id, BACKENDS[index])
        for phase, repetition, case_id, indices in expected_rounds
        for index in indices
    ]
    assert [row["slot_index"] for row in slots] == list(range(18))
    for index, row in enumerate(slots):
        assert row["backend_position"] == index % 3
        assert row["case_index"] == (row["case_id"] == "portal-second")
        assert set(row) == {
            "slot_index",
            "case_index",
            "case_id",
            "phase",
            "repetition",
            "backend",
            "backend_position",
        }


def test_requested_backend_order_is_preserved_and_single_backend_has_full_coverage():
    request = _request()
    request["backends"] = [BACKENDS[2], BACKENDS[0]]
    request["repetitions"] = 2
    slots = process._schedule(request)
    assert [row["backend"] for row in slots] == [
        BACKENDS[2],
        BACKENDS[0],
        BACKENDS[0],
        BACKENDS[2],
    ]
    request["backends"] = [BACKENDS[1]]
    request["warmups"] = 2
    assert [
        (row["phase"], row["repetition"], row["backend_position"])
        for row in process._schedule(request)
    ] == [
        ("warmup", 0, 0),
        ("warmup", 1, 0),
        ("measurement", 0, 0),
        ("measurement", 1, 0),
    ]


def test_invalid_public_request_cannot_launch_a_worker(tmp_path, monkeypatch):
    request_path = _write_request(tmp_path, _changed(("repetitions",), True))
    monkeypatch.setattr(
        process.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("invalid declaration launched a worker"),
    )
    with pytest.raises(ValueError):
        process.run_planar_frame_backend_experiment(
            request_path, source_revision=REVISION, output_directory=tmp_path / "out"
        )


@pytest.mark.parametrize("timeout", (0, -1, True, float("inf"), float("nan")))
def test_invalid_timeout_is_rejected_before_launch(tmp_path, monkeypatch, timeout):
    request_path = _write_request(tmp_path)
    monkeypatch.setattr(
        process.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("invalid timeout launched a worker"),
    )
    with pytest.raises(ValueError):
        process.run_planar_frame_backend_experiment(
            request_path,
            source_revision=REVISION,
            output_directory=tmp_path / "out",
            timeout_seconds=timeout,
        )


def test_existing_output_and_user_bytes_are_preserved(tmp_path, monkeypatch):
    request_path = _write_request(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "preserve.bin"
    sentinel.write_bytes(b"existing user-owned output")
    monkeypatch.setattr(
        process.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("existing output launched a worker"),
    )
    with pytest.raises(FileExistsError):
        process.run_planar_frame_backend_experiment(
            request_path, source_revision=REVISION, output_directory=output
        )
    assert sentinel.read_bytes() == b"existing user-owned output"


def _synthetic_manifest() -> tuple[dict, dict]:
    request = _request()
    slot = process._schedule(request)[0]
    case = {
        **request["cases"][0],
        "input_file": "inputs/case-0000.json",
        "input_identity": {"sha256": _sha(b"{}"), "byte_length": 2},
        "model_identity": None,
        "preflight_error": None,
    }
    sources = {"__init__.py": {"sha256": _sha(b""), "byte_length": 0}}
    return slot, {
        "schema_version": "planar-frame-backend-inputs.v1",
        "source_revision": REVISION,
        "source_revision_is_attestation": False,
        "request_identity": {
            "sha256": _sha(_json_bytes(request)),
            "byte_length": len(_json_bytes(request)),
        },
        "request": request,
        "cases": [case],
        "source_files": sources,
        "source_digest": _sha(process._bytes(sources)),
        "schedule": process._schedule(request),
        "timeout_seconds": 1,
        "thread_environment": {key: "1" for key in process.THREAD_VARIABLES},
    }


def _binding(slot, manifest, pid):
    return {
        "worker_pid": pid,
        "slot_sha256": _sha(process._bytes(slot)),
        "manifest_sha256": _sha(process._bytes(manifest)),
        "source_digest": manifest["source_digest"],
    }


def _failed_worker(directory, slot, manifest, pid):
    """Synthetic pre-analysis failure: validate transport, never physical results."""
    case = manifest["cases"][slot["case_index"]]
    (directory / "slot.json").write_bytes(process._bytes(slot))
    binding = _binding(slot, manifest, pid)
    failure = {"type": "ValueError", "message": "synthetic source rejection"}
    for name, value in {
        "started.json": binding,
        "failure.json": {"stage": "source_validation", **failure},
    }.items():
        (directory / name).write_bytes(process._bytes(value))
    resources = {
        "schema_version": "planar-frame-backend-worker.v1",
        **binding,
        "status": "worker_error",
        "stage": "source_validation",
        "error": failure,
        "api_entered": False,
        "input_identity": case["input_identity"],
        "model_identity": case["model_identity"],
        "configuration": {**case["configuration"], "matrix_backend": slot["backend"]},
        "imports": None,
        "runtime_identity": None,
        "artifacts": {
            name: {
                "sha256": _sha((directory / name).read_bytes()),
                "byte_length": (directory / name).stat().st_size,
            }
            for name in ("started.json", "failure.json")
        },
        "analysis_wall_ns": None,
        "analysis_cpu_ns": None,
        "workload_wall_ns": None,
        "workload_cpu_ns": None,
        "worker_wall_ns": 100,
        # Process CPU may exceed elapsed wall time; this is not an invalid bound.
        "worker_cpu_ns": 200,
        "peak_rss_bytes": None,
        "peak_rss_method": "post_exec_process_peak_unavailable",
        "analysis_scope": "public_api_including_internal_source_validation",
        "workload_scope": "api_explicit_public_validation_and_result_checkpoint_report_persistence",
        "worker_scope": "post_exec_cpu_and_peak_through_workload_source_checks_and_artifact_hashing_before_resource_sidecar_encoding;wall_starts_after_stdlib_imports",
        "claim_boundary": process.CLAIM_BOUNDARY,
    }
    (directory / "resources.json").write_bytes(process._bytes(resources))
    return resources


def _validate(directory, slot, manifest, pid):
    return process._validate_worker_bundle(
        directory, slot, pid, manifest, manifest["source_digest"]
    )


def test_source_failure_retains_known_cpu_without_claiming_api_or_physics(tmp_path):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    resources = _failed_worker(tmp_path, slot, manifest, pid)
    observed, result, validation = _validate(tmp_path, slot, manifest, pid)
    assert observed == resources
    assert observed["worker_cpu_ns"] > observed["worker_wall_ns"]
    assert observed["peak_rss_bytes"] is None
    assert observed["api_entered"] is False
    assert result is validation is None


@pytest.mark.parametrize(
    "field,value",
    (
        ("extra", True),
        ("worker_pid", True),
        ("worker_pid", -1),
        ("slot_sha256", "sha256:" + "0" * 64),
        ("manifest_sha256", "sha256:" + "0" * 64),
        ("source_digest", "sha256:" + "0" * 64),
        ("schema_version", "planar-frame-backend-worker.v2"),
        ("api_entered", 0),
        ("worker_wall_ns", True),
        ("worker_cpu_ns", -1),
        ("worker_cpu_ns", 200.0),
        ("analysis_wall_ns", 0),
        ("workload_cpu_ns", 0),
        ("peak_rss_bytes", True),
        ("peak_rss_bytes", 10.0),
        ("peak_rss_bytes", 0),
        ("peak_rss_method", "claimed_per_api_peak"),
        ("analysis_scope", "solver_only"),
        ("workload_scope", "solver_only"),
        ("worker_scope", "per_api_peak"),
        ("claim_boundary", "independent physical proof"),
        ("status", "finished"),
    ),
)
def test_worker_resource_fields_fail_closed(tmp_path, field, value):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    resources = _failed_worker(tmp_path, slot, manifest, pid)
    resources[field] = value
    (tmp_path / "resources.json").write_bytes(process._bytes(resources))
    with pytest.raises(ValueError):
        _validate(tmp_path, slot, manifest, pid)


@pytest.mark.parametrize(
    "identity", ("input_identity", "configuration", "model_identity")
)
def test_worker_cannot_redeclare_frozen_input_contract(tmp_path, identity):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    resources = _failed_worker(tmp_path, slot, manifest, pid)
    resources[identity] = {"changed": True}
    (tmp_path / "resources.json").write_bytes(process._bytes(resources))
    with pytest.raises(ValueError):
        _validate(tmp_path, slot, manifest, pid)


def test_timeout_reaps_owned_worker_and_retains_partial_output_without_credit(
    tmp_path, monkeypatch
):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    calls = []

    class TimedOutWorker:
        returncode = None

        def __init__(self, command, **kwargs):
            self.pid = pid
            directory = Path(command[command.index("--slot-directory") + 1])
            (directory / "entered.json").write_bytes(
                process._bytes(_binding(slot, manifest, pid))
            )
            (directory / "result.json").write_bytes(b'{"partial":')
            assert kwargs["env"]["PYTHONPATH"] == str(tmp_path / "source")
            assert all(kwargs["env"][key] == "1" for key in process.THREAD_VARIABLES)

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            if self.returncode is None:
                raise subprocess.TimeoutExpired("synthetic worker", timeout)
            return self.returncode

        def terminate(self):
            calls.append(("terminate",))
            self.returncode = -15

    monkeypatch.setattr(process.subprocess, "Popen", TimedOutWorker)
    row, result = process._run_slot(tmp_path, slot, manifest, 0.01)
    assert row["status"] == "timeout"
    assert row["api_entered"] is True
    assert row["worker_exit_code"] == -15
    assert row["artifact_contract_pass"] is row["physical_converged"] is False
    assert row["resource_eligible"] is False
    assert row["worker_resources"] is result is None
    assert row["parent_wall_ns"] >= 0
    assert calls == [("wait", 0.01), ("terminate",), ("wait", 5)]
    assert (tmp_path / row["directory"] / "result.json").read_bytes() == b'{"partial":'
    assert row["artifacts"]["result.json"]["sha256"] == _sha(b'{"partial":')


def test_actual_two_cases_two_backends_bind_raw_results_and_process_resources(
    observed_experiment,
):
    fixture = observed_experiment
    report, output = fixture["report"], fixture["output"]
    assert report["counts"] == {
        "declared": 4,
        "launched": 4,
        "api_entered": 4,
        "artifact_contract_pass": 4,
        "physical_converged": 4,
        "resource_eligible": 4,
    }, {"directory": str(output), "rows": report["rows"]}
    assert report["schedule_complete"] is True
    assert report["source_snapshot_intact"] is report["inputs_intact"] is True
    assert report["generalized_speedup_claimed"] is False
    assert report["independent_external_vv"] is report["release_eligible"] is False
    manifest = json.loads((output / "inputs-manifest.json").read_bytes())
    assert report["manifest_identity"] == {
        "sha256": _sha((output / "inputs-manifest.json").read_bytes()),
        "byte_length": (output / "inputs-manifest.json").stat().st_size,
    }
    assert manifest["source_revision"] == REVISION
    assert manifest["source_revision_is_attestation"] is False
    assert manifest["request"] == fixture["request"]
    assert manifest["schedule"] == process._schedule(fixture["request"])
    pids = [row["worker_pid"] for row in report["rows"]]
    assert len(set(pids)) == 4 and os.getpid() not in pids
    for case in manifest["cases"]:
        raw = (output / case["input_file"]).read_bytes()
        assert raw == fixture["originals"][case["model_file"]]
        assert case["input_identity"] == {"sha256": _sha(raw), "byte_length": len(raw)}
    for row, slot in zip(report["rows"], manifest["schedule"], strict=True):
        resources, result, validation = _validate(
            output / row["directory"], slot, manifest, row["worker_pid"]
        )
        assert row["status"] == resources["status"] == "finished"
        assert row["worker_exit_code"] == 0
        assert validation["artifact_contract_pass"] is True
        assert validation["engineering_result_authority"] is True
        assert result["status"] == "converged"
        assert result["release_eligible"] is False
        for unit in ("wall", "cpu"):
            assert (
                0
                < resources[f"analysis_{unit}_ns"]
                <= resources[f"workload_{unit}_ns"]
                <= resources[f"worker_{unit}_ns"]
            )
        assert 0 < resources["worker_wall_ns"] <= row["parent_wall_ns"]
        if os.uname().sysname == "Linux":
            assert resources["peak_rss_bytes"] > 0
        assert resources["configuration"]["matrix_backend"] == row["backend"]
        assert all(
            value == "1"
            for value in resources["runtime_identity"]["thread_environment"].values()
        )
    for relative, identity in manifest["source_files"].items():
        raw = (output / "source" / "structural_analysis" / relative).read_bytes()
        assert identity == {"sha256": _sha(raw), "byte_length": len(raw)}
    assert len(report["comparisons"]) == 2
    for pair in report["comparisons"]:
        assert pair["unavailable_reason"] is None
        assert pair["comparison"]["physical_si_match"] is True
        left, right = [
            report["rows"][pair[key]] for key in ("baseline_slot", "candidate_slot")
        ]
        assert (
            pair["paired_workload_wall_difference_ns"]
            == right["worker_resources"]["workload_wall_ns"]
            - left["worker_resources"]["workload_wall_ns"]
        )


def _stubbed_experiment(tmp_path, monkeypatch, mode):
    """Real parent orchestration, synthetic child transport, zero solver calls."""
    request = _request()
    request.update(backends=list(BACKENDS[:2]), repetitions=2, warmups=1)
    raw_model = (ROOT / "examples/planar_frame_rc_portal.json").read_bytes()
    model_file = tmp_path / "model.json"
    model_file.write_bytes(b"{}" if mode == "preflight" else raw_model)
    request_path = _write_request(tmp_path, request)
    raw_request = request_path.read_bytes()
    output = tmp_path / "experiment"
    calls = []
    # Source packaging is outside this parent-orchestration-only test's claim.
    monkeypatch.setattr(process, "_freeze_source", lambda directory: {})

    class Worker:
        returncode = None

        def __init__(self, command, **kwargs):
            assert mode != "preflight", "invalid model must never launch a child"
            calls.append(self)
            self.pid = os.getpid() + 10000 + len(calls)
            self.directory = Path(command[command.index("--slot-directory") + 1])
            manifest = json.loads((output / "inputs-manifest.json").read_bytes())
            slot = json.loads((self.directory / "slot.json").read_bytes())
            if mode in ("cancel", "partial"):
                (self.directory / "entered.json").write_bytes(
                    process._bytes(_binding(slot, manifest, self.pid))
                )
                (self.directory / "result.json").write_bytes(b'{"partial":')
            else:
                _failed_worker(self.directory, slot, manifest, self.pid)
            if len(calls) == 1:
                if mode == "original_changed":
                    model_file.write_bytes(b"changed after freeze")
                    request_path.write_bytes(b"changed after freeze")
                elif mode == "frozen_input_changed":
                    (output / manifest["cases"][0]["input_file"]).write_bytes(
                        b"changed frozen bytes"
                    )
                elif mode == "frozen_source_changed":
                    path = output / "source/structural_analysis/injected.py"
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b"# changed frozen source\n")
            self.terminated = False
            if mode == "manifest_deleted" and len(calls) == 6:
                (output / "inputs-manifest.json").unlink()

        def wait(self, timeout=None):
            if mode == "cancel" and not self.terminated:
                raise KeyboardInterrupt
            self.returncode = -15 if self.terminated else 0 if mode == "partial" else 1
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    monkeypatch.setattr(process.subprocess, "Popen", Worker)
    report = process.run_planar_frame_backend_experiment(
        request_path, source_revision=REVISION, output_directory=output
    )
    return report, output, calls, raw_request, raw_model


def test_cancellation_after_api_entry_preserves_denominator_and_reaps_worker(
    tmp_path, monkeypatch
):
    report, _, calls, _, _ = _stubbed_experiment(tmp_path, monkeypatch, "cancel")
    assert report["status"] == "cancelled"
    assert report["schedule_complete"] is True
    assert report["counts"]["declared"] == 6
    assert report["counts"]["launched"] == report["counts"]["api_entered"] == 1
    assert len(calls) == 1 and calls[0].terminated
    first, *remaining = report["rows"]
    assert first["status"] == "cancelled"
    assert first["worker_exit_code"] == -15
    assert first["api_entered"] is True
    assert first["resource_eligible"] is first["artifact_contract_pass"] is False
    assert len(remaining) == 5
    assert all(row["status"] == "not_launched_after_cancellation" for row in remaining)
    assert all(
        row["api_entered"] is row["resource_eligible"] is False for row in remaining
    )


@pytest.mark.parametrize("mode", ("preflight", "partial"))
def test_invalid_models_and_partial_success_exits_keep_every_planned_slot(
    tmp_path, monkeypatch, mode
):
    report, output, calls, _, _ = _stubbed_experiment(tmp_path, monkeypatch, mode)
    expected_status = "preflight_error" if mode == "preflight" else "worker_error"
    assert len(report["rows"]) == report["counts"]["declared"] == 6
    assert len(calls) == (0 if mode == "preflight" else 6)
    assert all(row["status"] == expected_status for row in report["rows"])
    for field in ("resource_eligible", "physical_converged", "artifact_contract_pass"):
        assert report["counts"][field] == 0
    for pair in report["comparisons"]:
        assert pair["comparison"] is pair["paired_workload_wall_difference_ns"] is None
        assert pair["unavailable_reason"]
    if mode == "partial":
        assert report["counts"]["api_entered"] == 6
        assert all(
            (output / row["directory"] / "result.json").read_bytes() == b'{"partial":'
            for row in report["rows"]
        )


def test_frozen_inputs_survive_original_request_and_model_changes(
    tmp_path, monkeypatch
):
    report, output, _, raw_request, raw_model = _stubbed_experiment(
        tmp_path, monkeypatch, "original_changed"
    )
    assert report["inputs_intact"] is True
    assert (output / "request.json").read_bytes() == raw_request
    assert (output / "inputs/case-0000.json").read_bytes() == raw_model
    assert report["counts"]["resource_eligible"] == 6
    assert (
        report["counts"]["api_entered"] == report["counts"]["physical_converged"] == 0
    )
    for summary in report["summaries"]:
        assert summary["declared_count"] == 2  # warmup is excluded
        costs = summary["completed_worker_resources_including_valid_failures"]
        assert costs["worker_cpu_ns"]["count"] == 2
        assert costs["worker_cpu_ns"]["median"] == 200
        assert costs["analysis_wall_ns"]["count"] == 0
        assert costs["analysis_wall_ns"]["median"] is None


@pytest.mark.parametrize(
    "mode,field",
    (
        ("frozen_input_changed", "inputs_intact"),
        ("frozen_source_changed", "source_snapshot_intact"),
    ),
)
def test_mutation_of_frozen_snapshot_invalidates_every_slot(
    tmp_path, monkeypatch, mode, field
):
    report, _, _, _, _ = _stubbed_experiment(tmp_path, monkeypatch, mode)
    assert report[field] is False
    assert report["counts"]["resource_eligible"] == 0
    assert report["counts"]["physical_converged"] == 0
    assert all(
        pair["paired_worker_cpu_difference_ns"] is None
        for pair in report["comparisons"]
    )


@pytest.mark.parametrize("changed", ("manifest", "slot"))
def test_worker_rejects_bootstrap_bytes_before_import_or_api(
    tmp_path, monkeypatch, changed
):
    slot_dir = tmp_path / "slot"
    slot_dir.mkdir()
    # Deliberately not JSON: authentication of the frozen bytes must precede parsing.
    manifest_raw, slot_raw = b"untrusted manifest bytes", b"untrusted slot bytes"
    (tmp_path / "inputs-manifest.json").write_bytes(manifest_raw)
    (slot_dir / "slot.json").write_bytes(slot_raw)
    monkeypatch.setattr(
        process,
        "_import_identity",
        lambda *args: pytest.fail("bootstrap mismatch reached imports"),
    )
    result = process._worker(
        tmp_path,
        slot_dir,
        expected_manifest_sha256=_sha(b"other")
        if changed == "manifest"
        else _sha(manifest_raw),
        expected_slot_sha256=_sha(b"other") if changed == "slot" else _sha(slot_raw),
    )
    assert result == 1
    failure = json.loads((slot_dir / "failure.json").read_bytes())
    assert failure["stage"] == "bootstrap_binding"
    assert not any(
        (slot_dir / name).exists()
        for name in ("started.json", "entered.json", "resources.json", "result.json")
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "failure_message",
        "unentered_result",
        "slot_boolean",
        "identity_float",
        "configuration_float",
        "artifact_length_float",
    ),
)
def test_rehashed_worker_metadata_cannot_rewrite_contract_types_or_phase(
    tmp_path, mutation
):
    slot, manifest = _synthetic_manifest()
    pid = os.getpid() + 10000
    resources = _failed_worker(tmp_path, slot, manifest, pid)
    if mutation == "failure_message":
        failure = json.loads((tmp_path / "failure.json").read_bytes())
        failure["message"] = "different failure than resources"
        (tmp_path / "failure.json").write_bytes(process._bytes(failure))
    elif mutation == "unentered_result":
        (tmp_path / "result.json").write_bytes(b"{}")
    elif mutation == "slot_boolean":
        declared = deepcopy(slot)
        declared["slot_index"] = False
        (tmp_path / "slot.json").write_bytes(process._bytes(declared))
    elif mutation == "identity_float":
        resources["input_identity"] = {
            **resources["input_identity"],
            "byte_length": 2.0,
        }
    elif mutation == "configuration_float":
        resources["configuration"]["load_steps"] = 2.0
    resources["artifacts"] = {
        name: {
            "sha256": _sha((tmp_path / name).read_bytes()),
            "byte_length": (tmp_path / name).stat().st_size,
        }
        for name in ("started.json", "failure.json", "result.json")
        if (tmp_path / name).exists()
    }
    if mutation == "artifact_length_float":
        resources["artifacts"]["failure.json"]["byte_length"] = float(
            resources["artifacts"]["failure.json"]["byte_length"]
        )
    (tmp_path / "resources.json").write_bytes(process._bytes(resources))
    with pytest.raises(ValueError):
        _validate(tmp_path, slot, manifest, pid)


def test_deleted_manifest_retains_report_and_invalidates_credit(tmp_path, monkeypatch):
    report, output, _, _, _ = _stubbed_experiment(
        tmp_path, monkeypatch, "manifest_deleted"
    )
    assert report["inputs_intact"] is False
    assert report["status"] == "invalidated"
    assert report["observed_manifest_identity"] is None
    assert report["manifest_identity"]["sha256"].startswith("sha256:")
    assert report["counts"]["declared"] == 6
    assert report["counts"]["resource_eligible"] == 0
    assert json.loads((output / "experiment.json").read_bytes()) == report


@pytest.mark.parametrize(
    "mutation",
    (
        "validation_bool",
        "checkpoint",
        "runtime_identity",
        "analysis_gt_workload",
        "namespace_outside",
        "namespace_wrong_name",
        "module_alias",
    ),
)
def test_actual_worker_rehashed_payloads_cannot_gain_detached_authority(
    observed_experiment, tmp_path, mutation
):
    output = observed_experiment["output"]
    row = observed_experiment["report"]["rows"][0]
    manifest = json.loads((output / "inputs-manifest.json").read_bytes())
    slot = manifest["schedule"][0]
    directory = tmp_path / "worker"
    shutil.copytree(output / row["directory"], directory)
    resources = json.loads((directory / "resources.json").read_bytes())
    if mutation == "validation_bool":
        validation = json.loads((directory / "validation.json").read_bytes())
        validation["contract_pass"] = 1
        (directory / "validation.json").write_bytes(process._bytes(validation))
    elif mutation == "checkpoint":
        (directory / "checkpoint.json").write_bytes(b"{}")
    elif mutation == "runtime_identity":
        resources["runtime_identity"]["dependencies"]["numpy"] = "forged"
    elif mutation == "namespace_outside":
        resources["imports"]["structural_analysis.schemas"] = "namespace:../schemas"
    elif mutation == "namespace_wrong_name":
        resources["imports"]["structural_analysis.schemas"] = "namespace:api"
    elif mutation == "module_alias":
        resources["imports"]["structural_analysis.api.planar_frame"] = "__init__.py"
    else:
        resources["analysis_wall_ns"] = resources["workload_wall_ns"] + 1
    for name in resources["artifacts"]:
        raw = (directory / name).read_bytes()
        resources["artifacts"][name] = {"sha256": _sha(raw), "byte_length": len(raw)}
    (directory / "resources.json").write_bytes(process._bytes(resources))
    with pytest.raises(ValueError):
        _validate(directory, slot, manifest, row["worker_pid"])


@pytest.mark.parametrize("artifact", ("checkpoint.json", "result.json"))
def test_parent_rechecks_retained_artifacts_before_comparison(
    observed_experiment, tmp_path, monkeypatch, artifact
):
    fixture = observed_experiment
    request = deepcopy(fixture["request"])
    for case in request["cases"]:
        (tmp_path / case["model_file"]).write_bytes(
            fixture["originals"][case["model_file"]]
        )
    request_path = _write_request(tmp_path, request)
    output = tmp_path / "experiment"
    monkeypatch.setattr(process, "_freeze_source", lambda directory: {})

    def cached_slot(bundle, slot, manifest, timeout):
        # Reuse real saved worker outputs solely to test parent retention logic.
        row = deepcopy(fixture["report"]["rows"][slot["slot_index"]])
        directory = bundle / row["directory"]
        shutil.copytree(fixture["output"] / row["directory"], directory)
        result = json.loads((directory / "result.json").read_bytes())
        if slot["slot_index"] == 3:
            (bundle / "slots/0000" / artifact).write_bytes(b"tampered after validation")
        return row, result

    monkeypatch.setattr(process, "_run_slot", cached_slot)
    report = process.run_planar_frame_backend_experiment(
        request_path, source_revision=REVISION, output_directory=output
    )
    assert report["counts"]["declared"] == 4
    first = report["rows"][0]
    assert first["retained_artifacts_intact"] is False
    assert (
        first["resource_eligible"]
        is first["artifact_contract_pass"]
        is first["physical_converged"]
        is False
    )
    pair = next(pair for pair in report["comparisons"] if pair["baseline_slot"] == 0)
    assert pair["comparison"] is pair["paired_workload_wall_difference_ns"] is None


@pytest.mark.parametrize("mode", ("outside", "multiple", "origin", "missing_source"))
def test_namespace_import_requires_one_exact_frozen_source_location(
    tmp_path, monkeypatch, mode
):
    package = tmp_path / "source/structural_analysis"
    public = package / "api/planar_frame.py"
    public.parent.mkdir(parents=True)
    public.write_bytes(b"# synthetic import identity only\n")
    schema = package / "schemas/model.json"
    schema.parent.mkdir()
    schema.write_bytes(b"{}")
    sources = {
        path.relative_to(package).as_posix(): {
            "sha256": _sha(path.read_bytes()),
            "byte_length": path.stat().st_size,
        }
        for path in (public, schema)
    }
    locations = [str(schema.parent)]
    if mode == "outside":
        locations = [str(tmp_path / "outside")]
    elif mode == "multiple":
        locations.append(str(tmp_path / "outside"))
    elif mode == "missing_source":
        sources.pop("schemas/model.json")
    modules = {
        "structural_analysis.api.planar_frame": SimpleNamespace(__file__=str(public)),
        "structural_analysis.schemas": SimpleNamespace(
            __file__=None,
            __path__=locations,
            __spec__=SimpleNamespace(origin="elsewhere" if mode == "origin" else None),
        ),
    }
    monkeypatch.setattr(process, "sys", SimpleNamespace(modules=modules))
    with pytest.raises(ValueError, match="namespace"):
        process._import_identity(tmp_path, sources)
