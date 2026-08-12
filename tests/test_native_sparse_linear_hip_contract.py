from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_sparse_linear_hip.py"
SPEC = importlib.util.spec_from_file_location("check_native_sparse_linear_hip", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hip
SPEC.loader.exec_module(hip)
DEVICE_LIB_PATH = ROOT / hip.DEFAULT_DEVICE_LIB_PATH


def _receipt(root: Path) -> dict[str, object]:
    architecture = "gfx1030"
    return {
        "schema_version": "native-sparse-linear-hip-receipt.v1",
        "backend": "amd_rocm_hip",
        "device_id": 0,
        "device_name": "synthetic sparse contract device",
        "architecture": architecture,
        "runtime_version": 60032831,
        "driver_version": 60032831,
        "compiler_version": "contract compiler",
        "compiled_architectures": architecture,
        "kernel_source_sha256": hip.expected_source_sha256(root),
        "device_library_sha256": hip.expected_device_library_sha256(
            DEVICE_LIB_PATH, architecture
        ),
        "reduction_profile": "single_block_fixed_tree_fp64.v1",
        "profile_count": 4,
        "exact_initial_profile_count": 1,
        "failure_profile_count": 4,
        "solve_count": 13,
        "max_solution_absolute_error": 1.0e-15,
        "max_true_residual_absolute_error": 2.0e-15,
        "max_metric_absolute_error": 2.0e-15,
        "h2d_bytes": 2880,
        "d2h_bytes": 960,
        "h2d_transfer_count": 53,
        "d2h_transfer_count": 26,
        "synchronization_count": 13,
        "kernel_launch_count": 13,
        "peak_device_buffer_bytes": 768,
        "vram_total_bytes": 16 * 1024 * 1024 * 1024,
        "vram_free_before_bytes": 15 * 1024 * 1024 * 1024,
        "vram_free_after_alloc_bytes": 15 * 1024 * 1024 * 1024 - 768,
        "fallback_count": 0,
        "fp64": True,
        "deterministic": True,
        "device_resident_iterations": True,
        "host_intermediate_state_transfer_count": 0,
        "host_iteration_control_transfer_count": 0,
        "iteration_parity": True,
        "numerical_status_parity": True,
        "parity_pass": True,
    }


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _copy_static_contract(tmp_path: Path) -> None:
    relatives = {
        *hip.REQUIRED_TOKENS,
        "native/cpp/src/hip/sparse_linear_hip.hpp",
    }
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_sparse_hip_contract_and_source_bound_candidate(
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, _receipt(ROOT))

    report = hip.check_native_sparse_linear_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
    )

    assert report["contract_pass"] is True
    assert report["receipt_valid"] is True
    assert report["authoritative_c2"] is False
    assert report["implementation_status"] == "C2 candidate"
    assert "protected native-hip-approved" in report["claim_boundary"]


def test_sparse_hip_receipt_fails_closed_on_source_fallback_or_residency_drift(
    tmp_path: Path,
) -> None:
    _copy_static_contract(tmp_path)
    payload = _receipt(tmp_path)
    payload["kernel_source_sha256"] = "0" * 64
    payload["fallback_count"] = 1
    payload["device_resident_iterations"] = False
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, payload)

    report = hip.check_native_sparse_linear_hip(
        tmp_path,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
    )

    assert report["contract_pass"] is False
    assert "sparse_hip_receipt_kernel_source_sha256_mismatch" in report["blockers"]
    assert "sparse_hip_receipt_value_invalid:fallback_count" in report["blockers"]
    assert (
        "sparse_hip_receipt_value_invalid:device_resident_iterations"
        in report["blockers"]
    )


def test_sparse_hip_promotion_requires_exact_protected_runner_context(
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
    blocked = hip.check_native_sparse_linear_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
        require_approved_runner=True,
    )
    assert blocked["contract_pass"] is False
    assert blocked["authoritative_c2"] is False
    assert "sparse_hip_approval_not_github_actions" in blocked["blockers"]

    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    approved = hip.check_native_sparse_linear_hip(
        ROOT,
        receipt_path=receipt,
        device_lib_path=DEVICE_LIB_PATH,
        require_approved_runner=True,
    )
    assert approved["contract_pass"] is True
    assert approved["authoritative_c2"] is True
    assert approved["approval_context"]["github_sha"] == head
