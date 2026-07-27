"""Tests for the native MGT modal and buckling solver evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EQUATION_SCALING_FIELDS = {
    "reference_force",
    "characteristic_length",
    "translation_residual_norm",
    "rotation_residual_norm",
    "scaled_residual_norm",
    "translation_increment_norm",
    "rotation_increment_norm",
    "scaled_increment_norm",
    "scaled_tangent_condition",
    "scaling_hash",
}


def test_mgt_native_modal_buckling_solver_generates_ready_evidence(tmp_path: Path) -> None:
    out = tmp_path / "mgt_native_modal_buckling_solver.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_modal_buckling_solver.py"),
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
    assert payload["schema_version"] == "mgt-native-modal-buckling-solver.v1"
    assert payload["status"] == "ready"
    assert payload["native_solver_ready"] is True
    assert payload["benchmark_contract_pass"] is True
    assert payload["modal_solve"]["mode_count"] >= 3
    assert payload["buckling_solve"]["critical_load_factor"] > 1.0
    assert payload["matrices"]["stiffness_matrix_ready"] is True
    assert payload["matrices"]["mass_matrix_ready"] is True
    assert payload["matrices"]["geometric_stiffness_ready"] is True
    modal = payload["modal_solve"]
    assert modal["residual_gate_pass"] is True
    assert modal["final_reassembled_residual_pass"] is True
    assert modal["fallback_used"] is False
    assert modal["regularization_used"] is False
    assert all(
        set(mode["equation_scaling_6dof"]) == EQUATION_SCALING_FIELDS
        and mode["equation_scaling_6dof"]["scaled_residual_norm"] <= 1.0e-8
        for mode in modal["modes"]
    )
    buckling = payload["buckling_solve"]
    assert buckling["factor_source"] == "generalized_eigen"
    assert buckling["residual_gate_pass"] is True
    assert buckling["final_reassembled_residual_pass"] is True
    assert buckling["fallback_used"] is False
    assert buckling["regularization_used"] is False
    assert set(buckling["equation_scaling_6dof"]) == EQUATION_SCALING_FIELDS
    assert buckling["equation_scaling_6dof"]["scaled_residual_norm"] <= 1.0e-8
    comparison = payload["benchmark_contract"]
    assert comparison["equation_scaling_6dof"] is None
    assert comparison["equation_scaling_state"] == "unavailable"
    assert "do not expose equation vectors or tangents" in (
        comparison["equation_scaling_unavailable_reason"]
    )
