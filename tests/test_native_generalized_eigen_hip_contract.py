from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_generalized_eigen_hip.py"
SPEC = importlib.util.spec_from_file_location(
    "check_native_generalized_eigen_hip", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
hip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hip
SPEC.loader.exec_module(hip)
DEVICE_LIB_PATH = ROOT / hip.DEFAULT_DEVICE_LIB_PATH


def _receipt(root: Path) -> dict[str, object]:
    architecture = "gfx1030"
    return {
        "schema_version": "native-generalized-eigen-hip-receipt.v1",
        "backend": "amd_rocm_hip",
        "device_id": 0,
        "device_name": "synthetic generalized-eigen contract device",
        "architecture": architecture,
        "runtime_version": 60032831,
        "driver_version": 60032831,
        "compiler_version": "contract compiler",
        "compiled_architectures": architecture,
        "kernel_source_sha256": hip.expected_source_sha256(root),
        "device_library_sha256": hip.expected_device_library_sha256(
            DEVICE_LIB_PATH, architecture
        ),
        "execution_profile": "single_thread_cyclic_jacobi_fp64.v1",
        "profile_count": 8,
        "modal_profile_count": 4,
        "buckling_profile_count": 4,
        "deterministic_repeat_count": 8,
        "numerical_failure_profile_count": 2,
        "contract_failure_profile_count": 8,
        "solve_count": 18,
        "max_eigenvalue_relative_error": 1.0e-15,
        "max_shape_absolute_error": 2.0e-15,
        "max_result_metric_absolute_error": 2.0e-15,
        "h2d_bytes": 2504,
        "d2h_bytes": 4_793_760,
        "h2d_transfer_count": 54,
        "d2h_transfer_count": 18,
        "synchronization_count": 18,
        "kernel_launch_count": 18,
        "peak_device_buffer_bytes": 267_184,
        "vram_total_bytes": 16 * 1024 * 1024 * 1024,
        "vram_free_before_bytes": 15 * 1024 * 1024 * 1024,
        "vram_free_after_alloc_bytes": 15 * 1024 * 1024 * 1024 - 267_184,
        "fallback_count": 0,
        "fp64": True,
        "deterministic": True,
        "device_resident_eigensolve": True,
        "device_result_recovery": True,
        "host_intermediate_state_transfer_count": 0,
        "host_iteration_control_transfer_count": 0,
        "numerical_status_parity": True,
        "contract_failure_parity": True,
        "parity_pass": True,
    }


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _copy_static_contract(tmp_path: Path) -> None:
    relatives = {
        *hip.REQUIRED_TOKENS,
        "native/cpp/src/hip/generalized_eigen_hip.hpp",
    }
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_generalized_eigen_hip_source_bound_candidate(
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, _receipt(ROOT))

    report = hip.check_native_generalized_eigen_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
    )

    assert report["contract_pass"] is True
    assert report["receipt_valid"] is True
    assert report["authoritative_c2"] is False
    assert report["implementation_status"] == "C2 candidate"
    assert "single-thread reference profile" in report["claim_boundary"]


def test_generalized_eigen_hip_receipt_fails_closed_on_identity_or_residency_drift(
    tmp_path: Path,
) -> None:
    _copy_static_contract(tmp_path)
    payload = _receipt(tmp_path)
    payload["kernel_source_sha256"] = "0" * 64
    payload["fallback_count"] = 1
    payload["device_result_recovery"] = False
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, payload)

    report = hip.check_native_generalized_eigen_hip(
        tmp_path,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
    )

    assert report["contract_pass"] is False
    assert (
        "generalized_eigen_hip_kernel_source_sha256_mismatch"
        in report["blockers"]
    )
    assert (
        "generalized_eigen_hip_receipt_value_invalid:fallback_count"
        in report["blockers"]
    )
    assert (
        "generalized_eigen_hip_receipt_value_invalid:device_result_recovery"
        in report["blockers"]
    )


def test_generalized_eigen_hip_promotion_requires_protected_runner_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, _receipt(ROOT))
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    environment = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "self-hosted",
        "NATIVE_HIP_APPROVAL_ENVIRONMENT": "native-hip-approved",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_SHA": head,
        "GITHUB_WORKFLOW_REF": (
            "owner/repo/.github/workflows/native-hip-dedicated.yml@refs/heads/main"
        ),
        "RUNNER_NAME": "approved-rocm-runner",
    }
    for key in environment:
        monkeypatch.delenv(key, raising=False)
    blocked = hip.check_native_generalized_eigen_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
        require_approved_runner=True,
    )
    assert blocked["contract_pass"] is False
    assert blocked["authoritative_c2"] is False
    assert (
        "generalized_eigen_hip_approval_not_github_actions"
        in blocked["blockers"]
    )

    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    approved = hip.check_native_generalized_eigen_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
        require_approved_runner=True,
    )
    assert approved["contract_pass"] is True
    assert approved["authoritative_c2"] is True
    assert approved["approval_context"]["github_sha"] == head
