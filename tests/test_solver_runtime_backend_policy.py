from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_solver_runtime_backend_policy import build_solver_runtime_backend_policy  # noqa: E402


def test_solver_runtime_backend_policy_marks_rocm_as_official_lane() -> None:
    payload = build_solver_runtime_backend_policy()

    assert payload["schema_version"] == "solver-runtime-backend-policy.v1"
    assert payload["status"] == "ready"
    assert payload["official_solver_compute_backend"] == "amd_rocm_hip"
    assert payload["official_solver_backend"] == "amd_rocm_hip"
    assert payload["official_solver_backend_family"] == "rocm_hip"
    assert payload["gpu_required_for_commercial_solver_closure"] is True
    assert payload["nvidia_smi_required"] is False
    assert payload["rocm_smi_detected"] is True
    assert payload["rocminfo_detected"] is True
    assert payload["torch_version_hip"]
    assert payload["torch_device_label_is_pytorch_rocm_compat_alias"] is True
    assert "6900 XT" in " ".join(payload["device_names"])
    assert payload["cpu_diagnostic_promotes_solver_closure"] is False
    assert payload["cpu_solver_fallback_detected"] is False
    assert payload["cpu_fallback_allowed_for_official_solver_closure"] is False
    assert payload["cpu_reference_allowed_for_validation_replay"] is True
    assert payload["rocm_sparse_probe_present"] is True
    assert payload["line_frame_rocm_sparse_solver_ready"] is True
    assert payload["rocm_sparse_solver_probe_ready"] is True
    assert payload["shell_coupled_rocm_sparse_solver_ready"] is True
    assert not payload["blockers"]


def test_solver_runtime_backend_policy_cli_writes_receipt(tmp_path: Path) -> None:
    out = tmp_path / "solver_runtime_backend_policy.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_solver_runtime_backend_policy.py"),
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
    assert payload["status"] == "ready"
    assert payload["official_solver_compute_backend"] == "amd_rocm_hip"
    assert payload["official_solver_backend"] == "amd_rocm_hip"
    assert payload["cpu_solver_fallback_detected"] is False
