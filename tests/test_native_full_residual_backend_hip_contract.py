from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_full_residual_backend_hip.py"
SPEC = importlib.util.spec_from_file_location(
    "check_native_full_residual_backend_hip", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
hip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hip
SPEC.loader.exec_module(hip)
DEVICE_LIB_PATH = ROOT / hip.DEFAULT_DEVICE_LIB_PATH


def _receipt(root: Path) -> dict[str, object]:
    architecture = "gfx1030"
    return {
        "schema_version": "native-full-residual-backend-hip-receipt.v1",
        "backend": "amd_rocm_hip",
        "device_id": 0,
        "device_name": "synthetic full-residual contract device",
        "architecture": architecture,
        "runtime_version": 60032831,
        "driver_version": 60032831,
        "compiler_version": "contract compiler",
        "compiled_architectures": architecture,
        "kernel_source_sha256": hip.expected_source_sha256(root),
        "device_library_sha256": hip.expected_device_library_sha256(
            DEVICE_LIB_PATH, architecture
        ),
        "operator_h2d_bytes": 4096,
        "eval_h2d_bytes": 256,
        "eval_d2h_bytes": 128,
        "operator_h2d_transfer_count": 10,
        "eval_h2d_transfer_count": 1,
        "eval_d2h_transfer_count": 1,
        "operator_synchronization_count": 1,
        "eval_synchronization_count": 1,
        "kernel_launch_count": 4,
        "device_buffer_bytes": 4480,
        "vram_total_bytes": 16 * 1024 * 1024 * 1024,
        "vram_free_before_bytes": 15 * 1024 * 1024 * 1024,
        "vram_free_after_bytes": 15 * 1024 * 1024 * 1024 - 4480,
        "max_residual_absolute_error": 0.0,
        "fallback_count": 0,
        "fp64": True,
        "deterministic": True,
        "operator_device_resident": True,
        "eval_buffers_reused": True,
        "cpu_hip_parity": True,
        "hip_repeat_bitwise": True,
        "single_entry_symbol": "sa_get_api_v1",
        "parity_pass": True,
    }


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _copy_static_contract(tmp_path: Path) -> None:
    relatives = {
        *hip.REQUIRED_TOKENS,
        "native/cpp/src/hip/full_residual_hip.hpp",
    }
    for relative in relatives:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_full_residual_hip_source_bound_candidate(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, _receipt(ROOT))

    report = hip.check(ROOT, receipt, DEVICE_LIB_PATH, False)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["receipt_valid"] is True
    assert report["authoritative_c2"] is False
    assert report["implementation_status"] == "C2 candidate"


def test_full_residual_receipt_rejects_identity_fallback_and_residency_drift(
    tmp_path: Path,
) -> None:
    _copy_static_contract(tmp_path)
    payload = _receipt(tmp_path)
    payload["kernel_source_sha256"] = "0" * 64
    payload["fallback_count"] = 1
    payload["operator_device_resident"] = False
    receipt = tmp_path / "receipt.json"
    _write_receipt(receipt, payload)

    report = hip.check(tmp_path, receipt, DEVICE_LIB_PATH, False)

    assert report["contract_pass"] is False
    assert "full_residual_hip_kernel_source_sha256_mismatch" in report["blockers"]
    assert "full_residual_hip_receipt_value_invalid:fallback_count" in report["blockers"]
    assert (
        "full_residual_hip_receipt_value_invalid:operator_device_resident"
        in report["blockers"]
    )


def test_full_residual_promotion_requires_protected_runner_context(
    tmp_path: Path, monkeypatch
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
    blocked = hip.check(ROOT, receipt, DEVICE_LIB_PATH, True)
    assert blocked["contract_pass"] is False
    assert blocked["authoritative_c2"] is False
    assert "full_residual_hip_approval_not_github_actions" in blocked["blockers"]

    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    approved = hip.check(ROOT, receipt, DEVICE_LIB_PATH, True)
    assert approved["contract_pass"] is True, approved["blockers"]
    assert approved["authoritative_c2"] is True
    assert approved["approval_context"]["github_sha"] == head
