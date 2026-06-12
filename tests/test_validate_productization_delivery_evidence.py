"""Tests for productization delivery evidence validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from validate_productization_delivery_evidence import (  # noqa: E402
    solver_runtime_backend_policy_errors,
)


def test_validate_productization_passes_current_dir() -> None:
    out = (
        REPO_ROOT
        / "implementation/phase1/release_evidence/productization/productization_delivery_evidence_validation_test.json"
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_productization_delivery_evidence.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert not payload["files_missing"]
    policy = payload["solver_runtime_backend_policy"]
    assert policy["official_solver_compute_backend"] == "amd_rocm_hip"
    assert policy["official_solver_backend"] == "amd_rocm_hip"
    assert policy["official_solver_backend_family"] == "rocm_hip"
    assert policy["gpu_required_for_commercial_solver_closure"] is True
    assert policy["torch_device_label_is_pytorch_rocm_compat_alias"] is True
    assert policy["cpu_diagnostic_promotes_solver_closure"] is False
    assert policy["cpu_solver_fallback_detected"] is False
    assert policy["cpu_fallback_allowed_for_official_solver_closure"] is False


def test_solver_runtime_backend_policy_errors_reject_cpu_promotion() -> None:
    policy = {
        "schema_version": "solver-runtime-backend-policy.v1",
        "status": "ready",
        "official_solver_compute_backend": "cpu_scipy",
        "official_solver_backend": "cpu_scipy",
        "official_solver_backend_family": "cpu",
        "gpu_required_for_commercial_solver_closure": False,
        "nvidia_smi_required": True,
        "rocm_sparse_probe_present": False,
        "cpu_diagnostic_promotes_solver_closure": True,
        "cpu_solver_fallback_detected": True,
        "cpu_fallback_allowed_for_official_solver_closure": True,
        "cpu_reference_allowed_for_validation_replay": False,
    }

    errors = solver_runtime_backend_policy_errors(policy)

    assert "solver_runtime_backend_policy_official_backend_not_amd_rocm_hip" in errors
    assert "solver_runtime_backend_policy_official_backend_alias_not_amd_rocm_hip" in errors
    assert "solver_runtime_backend_policy_backend_family_not_rocm_hip" in errors
    assert "solver_runtime_backend_policy_gpu_not_required_for_closure" in errors
    assert "solver_runtime_backend_policy_cpu_diagnostic_can_promote_closure" in errors
    assert "solver_runtime_backend_policy_cpu_solver_fallback_detected" in errors
    assert "solver_runtime_backend_policy_cpu_fallback_can_promote_closure" in errors
