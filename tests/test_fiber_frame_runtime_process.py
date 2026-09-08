from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameRuntimeBenchmarkConfig,
)


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


def request_file(tmp_path: Path) -> Path:
    request = {
        "schema_version": "rc-fiber-runtime-process-request.v1",
        "cases": [
            {
                "case_id": "cantilever",
                "model_file": str(
                    ROOT / "examples/public_rc_fiber_frame_cantilever.json"
                ),
                "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
            }
        ],
        "benchmark_configuration": asdict(
            FiberFrameRuntimeBenchmarkConfig(repetitions=1, warmup_repetitions=0)
        ),
        "policy_file": None,
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return path


def test_real_fresh_process_binds_physical_suite_and_scoped_resources(
    tmp_path, monkeypatch
):
    request = request_file(tmp_path)
    shadow = tmp_path / "structural_analysis"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('wrong checkout imported')")
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_runtime_process(
        request, source_revision=REVISION, output_directory=output
    )
    resources = json.loads((output / "resources.json").read_bytes())
    raw = (output / "suite.json").read_bytes()
    suite = json.loads(raw)
    assert manifest["status"] == "ready"
    assert manifest["worker_exit_code"] == 0
    assert manifest["worker_pid"] == resources["worker_pid"] != os.getpid()
    assert manifest["fresh_python_process"] is True
    assert suite["coverage"]["fully_verified_run_count"] == 2
    assert suite["coverage"]["verified_reference_episode_count"] == 1
    assert resources["suite_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert (
        resources["suite_byte_length"] == resources["report_bytes_written"] == len(raw)
    )
    assert resources["input_bytes_read"] == sum(
        Path(row["path"]).stat().st_size for row in resources["inputs"]
    )
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
    assert resources["resource_sidecar_io_included"] is False
    assert resources["gpu_time_ns"] is None
    for key in (
        "source_revision_is_attestation",
        "independent_hardware_validation",
        "generalized_speedup_claimed",
    ):
        assert resources[key] is False
    for name, artifact in manifest["artifacts"].items():
        data = (output / name).read_bytes()
        assert artifact == {
            "byte_length": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        }


def test_existing_output_is_preserved_before_launch(tmp_path, monkeypatch):
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"preserve")
    monkeypatch.setattr(
        process.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("must not launch"),
    )
    with pytest.raises(FileExistsError):
        process.run_fiber_frame_runtime_process(
            tmp_path / "missing.json",
            source_revision=REVISION,
            output_directory=tmp_path,
        )
    assert sentinel.read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "document", ['{"cases": [], "cases": []}', '{"schema_version": NaN}', "{}"]
)
def test_invalid_request_retains_failed_worker_without_resource_credit(
    tmp_path, document
):
    request = tmp_path / "request.json"
    request.write_text(document)
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_runtime_process(
        request, source_revision=REVISION, output_directory=output
    )
    failure = json.loads((output / "failure.json").read_bytes())
    assert manifest["status"] == "blocked"
    assert manifest["worker_exit_code"] == 3
    assert manifest["worker_measurements_available"] is False
    assert failure["stage"] == "input_contract"
    assert failure["measurement_contract_pass"] is False
    assert "suite.json" not in manifest["artifacts"]


def test_timeout_reaps_only_its_worker_and_never_claims_complete_measurements(tmp_path):
    manifest = process.run_fiber_frame_runtime_process(
        request_file(tmp_path),
        source_revision=REVISION,
        output_directory=tmp_path / "result",
        timeout_seconds=0.000001,
    )
    assert manifest["status"] == "timeout"
    assert manifest["worker_exit_code"] is not None
    assert manifest["worker_measurements_available"] is False
    assert manifest["worker_pid"] != os.getpid()


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_invalid_timeout_rejected_without_output(tmp_path, timeout):
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="timeout_seconds"):
        process.run_fiber_frame_runtime_process(
            tmp_path / "missing",
            source_revision=REVISION,
            output_directory=output,
            timeout_seconds=timeout,
        )
    assert not output.exists()


def test_unknown_rss_units_remain_unavailable(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "unknown")
    assert process._peak_rss() == (
        None,
        "post_exec_process_peak_rss_not_supported_on_this_platform",
    )


@pytest.mark.parametrize(
    "status",
    ["", "VmHWM: 123 MB", "VmHWM: -1 kB", "VmHWM: 0 kB", "VmHWM: 1 kB\nVmHWM: 2 kB"],
)
def test_unverifiable_linux_peak_remains_unavailable(monkeypatch, status):
    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(process.Path, "read_text", lambda self, **kwargs: status)
    assert process._peak_rss() == (None, "post_exec_process_peak_rss_unavailable")


def test_unreadable_linux_peak_remains_unavailable(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")

    def unreadable(self, **kwargs):
        raise OSError("proc unavailable")

    monkeypatch.setattr(process.Path, "read_text", unreadable)
    assert process._peak_rss() == (None, "post_exec_process_peak_rss_unavailable")


def test_linux_peak_uses_verified_kib_units(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(
        process.Path,
        "read_text",
        lambda self, **kwargs: "Name: worker\nVmHWM:\t1234 kB\n",
    )
    peak, scope = process._peak_rss()
    assert peak == 1234 * 1024
    assert scope.startswith("linux_proc_vmhwm_post_exec_address_space_")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux exec/RSS contract")
def test_linux_peak_excludes_large_parent_allocation():
    # Load only the stdlib-only measurement module in the child, keeping this
    # check independent of solver imports and avoiding an expensive suite run.
    probe = textwrap.dedent(
        """
        import importlib.util, json, sys
        spec = importlib.util.spec_from_file_location("resource_probe", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(json.dumps(module._peak_rss()))
        """
    )
    driver = textwrap.dedent(
        """
        import json, subprocess, sys
        allocation = bytearray(96 * 1024 * 1024)
        print(subprocess.check_output(
            [sys.executable, "-c", sys.argv[1], sys.argv[2]], text=True, timeout=10
        ), end="")
        """
    )
    peak, scope = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-c",
                driver,
                probe,
                str(Path(process.__file__).resolve()),
            ],
            cwd=ROOT,
            text=True,
            timeout=15,
        )
    )
    assert 0 < peak < 72 * 1024 * 1024
    assert scope.startswith("linux_proc_vmhwm_post_exec_address_space_")


@pytest.mark.parametrize("sidecar", [b'{"worker_pid":', b'{"worker_pid": 999}'])
def test_timeout_retains_partial_artifacts_without_parsing_sidecar(
    tmp_path, monkeypatch, sidecar
):
    class PartialWorker:
        pid = 123
        stopped = False
        calls = 0

        def wait(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("worker", 1)
            return -15

        def terminate(self):
            self.stopped = True

    worker = PartialWorker()

    def launch(command, **kwargs):
        output = Path(command[-1])
        (output / "resources.json").write_bytes(sidecar)
        (output / "suite.json").write_bytes(b'{"incomplete":')
        return worker

    monkeypatch.setattr(process.subprocess, "Popen", launch)
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_runtime_process(
        tmp_path / "request.json", source_revision=REVISION, output_directory=output
    )
    assert manifest["status"] == "timeout"
    assert manifest["worker_measurements_available"] is False
    assert worker.stopped and worker.calls == 2
    assert (output / "resources.json").read_bytes() == sidecar
    assert manifest["artifacts"]["resources.json"] == {
        "byte_length": len(sidecar),
        "sha256": "sha256:" + hashlib.sha256(sidecar).hexdigest(),
    }
    assert json.loads((output / "manifest.json").read_bytes()) == manifest


def _policy_payload():
    from structural_analysis.ai.fiber_frame_warm_start_learning import (
        FiberFrameLearnedWarmStartPolicy,
    )

    return FiberFrameLearnedWarmStartPolicy(
        free_global_dofs=(3,),
        physical_coordinate_scale=(1.0,),
        feature_mean=(0.0,) * 7,
        feature_scale=(1.0,) * 7,
        feature_min=(-1.0,) * 7,
        feature_max=(1.0,) * 7,
        target_scale=(1.0,),
        weights=((0.0,),) * 8,
        training_sample_hashes=("sha256:" + "b" * 64,),
        ridge=1e-6,
        ood_margin=0.1,
    ).to_dict()


def test_policy_json_roundtrip_retains_frozen_identity():
    payload = _policy_payload()
    loaded = process._decode_policy(json.dumps(payload).encode())
    assert loaded.artifact_hash == payload["artifact_hash"]
    assert process._bytes(loaded.to_dict()) == process._bytes(payload)


@pytest.mark.parametrize("mutation", ["weights", "authority", "extra", "hash"])
def test_policy_loader_rejects_detached_or_promoted_artifacts(mutation):
    payload = _policy_payload()
    if mutation == "weights":
        payload["weights"] = [[1.0]] * 8
    elif mutation == "authority":
        payload["physical_result_authority"] = True
    elif mutation == "extra":
        payload["extra"] = "unbound"
    else:
        payload["artifact_hash"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError):
        process._decode_policy(json.dumps(payload).encode())


def test_parent_interruption_reaps_its_worker(tmp_path, monkeypatch):
    class InterruptedWorker:
        pid = 123
        stopped = False
        calls = 0

        def wait(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt()
            return -15

        def terminate(self):
            self.stopped = True

    worker = InterruptedWorker()
    monkeypatch.setattr(process.subprocess, "Popen", lambda *args, **kwargs: worker)
    with pytest.raises(KeyboardInterrupt):
        process.run_fiber_frame_runtime_process(
            tmp_path / "request.json",
            source_revision=REVISION,
            output_directory=tmp_path / "result",
        )
    assert worker.stopped
    assert worker.calls == 2
    assert not (tmp_path / "result" / "manifest.json").exists()


def _resource_payload(suite):
    return {
        "schema_version": "rc-fiber-runtime-process-resources.v1",
        "worker_pid": 123,
        "source_revision": REVISION,
        "status": "ready",
        "measurement_contract_pass": True,
        "suite_sha256": "sha256:" + hashlib.sha256(suite).hexdigest(),
        "suite_byte_length": len(suite),
        "inputs": [],
        "input_read_wall_ns": 0,
        "input_bytes_read": 0,
        "input_io_scope": "test_input_read_scope",
        "workload_wall_ns": 1,
        "workload_cpu_process_time_ns": 1,
        "workload_scope": "test_whole_suite_scope",
        "report_encode_wall_ns": 1,
        "report_write_flush_fsync_wall_ns": 1,
        "report_bytes_written": len(suite),
        "worker_observed_wall_ns": 1,
        "cpu_process_time_ns": 1,
        "process_cpu_scope": "test_worker_scope",
        "peak_memory_bytes": None,
        "peak_memory_scope_or_reason": "test_no_memory_observation",
        "per_strategy_peak_memory_bytes": None,
        "per_strategy_peak_memory_reason": "test_shared_worker",
        "gpu_time_ns": None,
        "gpu_time_reason": "test_cpu_only",
        "resource_sidecar_io_included": False,
        "source_revision_is_attestation": False,
        "independent_hardware_validation": False,
        "generalized_speedup_claimed": False,
    }


@pytest.mark.parametrize(
    "mutation,expected_reason",
    [
        ("truncated", "worker_resources_json_invalid"),
        ("null", "worker_resources_contract_invalid"),
        ("list", "worker_resources_contract_invalid"),
        ("missing_identity_field", "worker_resources_contract_invalid"),
        ("missing_measurement_field", "worker_resources_contract_invalid"),
        ("detached_pid", "worker_resource_identity_mismatch"),
        ("detached_source", "worker_resource_identity_mismatch"),
        ("detached_suite", "worker_resource_identity_mismatch"),
        ("detached_size", "worker_resource_identity_mismatch"),
        ("truthy_measurement", "worker_resources_contract_invalid"),
        ("string_measurement", "worker_resources_contract_invalid"),
        ("inconsistent_status", "worker_resources_contract_invalid"),
    ],
)
def test_non_timeout_invalid_sidecar_retains_blocked_manifest(
    tmp_path, monkeypatch, mutation, expected_reason
):
    suite = b'{"status":"ready"}\n'
    payload = _resource_payload(suite)
    exit_code = 0
    if mutation == "missing_identity_field":
        del payload["worker_pid"]
    elif mutation == "missing_measurement_field":
        del payload["cpu_process_time_ns"]
    elif mutation == "detached_pid":
        payload["worker_pid"] = 999
    elif mutation == "detached_source":
        payload["source_revision"] = "b" * 40
    elif mutation == "detached_suite":
        payload["suite_sha256"] = "sha256:" + "b" * 64
    elif mutation == "detached_size":
        payload["suite_byte_length"] += 1
    elif mutation == "truthy_measurement":
        payload["measurement_contract_pass"] = 1
    elif mutation == "string_measurement":
        payload["measurement_contract_pass"] = "true"
    elif mutation == "inconsistent_status":
        payload["status"] = "blocked"
    sidecar = process._bytes(payload)
    if mutation == "truncated":
        sidecar = b'{"worker_pid":'
        exit_code = 3
    elif mutation in {"null", "list"}:
        sidecar = b"null" if mutation == "null" else b"[]"

    class CompletedWorker:
        pid = 123

        def wait(self, **kwargs):
            return exit_code

    def launch(command, **kwargs):
        output = Path(command[-1])
        (output / "suite.json").write_bytes(suite)
        (output / "resources.json").write_bytes(sidecar)
        return CompletedWorker()

    monkeypatch.setattr(process.subprocess, "Popen", launch)
    output = tmp_path / "result"
    manifest = process.run_fiber_frame_runtime_process(
        tmp_path / "request.json", source_revision=REVISION, output_directory=output
    )
    assert manifest["status"] == "blocked"
    assert manifest["worker_exit_code"] == exit_code
    assert manifest["worker_measurements_available"] is False
    assert manifest["worker_resource_validation_failure"] == expected_reason
    assert (output / "resources.json").read_bytes() == sidecar
    assert manifest["artifacts"]["resources.json"] == {
        "byte_length": len(sidecar),
        "sha256": "sha256:" + hashlib.sha256(sidecar).hexdigest(),
    }
    assert json.loads((output / "manifest.json").read_bytes()) == manifest


def test_valid_blocked_sidecar_preserves_available_scoped_measurements():
    suite = b'{"status":"blocked"}\n'
    payload = _resource_payload(suite)
    payload.update(status="blocked", measurement_contract_pass=False)
    assert (
        process._resource_validation_failure(
            payload,
            123,
            REVISION,
            {
                "byte_length": len(suite),
                "sha256": "sha256:" + hashlib.sha256(suite).hexdigest(),
            },
        )
        is None
    )
