"""Tests for bounded MGT shell material nonlinear tangent evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_shell_material_nonlinear_tangent_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_shell_material_nonlinear_tangent.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_shell_material_nonlinear_tangent.py"),
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
    assert payload["schema_version"] == "mgt-shell-material-nonlinear-tangent.v1"
    assert payload["status"] == "ready"
    assert payload["shell_material_nonlinear_tangent_ready"] is True
    assert payload["service_shell_material_state_ready"] is True
    assert payload["controlled_probe_shell_material_state_ready"] is True
    assert payload["local_constitutive_tangent_fd_consistency_ready"] is True
    assert payload["fixed_tangent_global_shell_jvp_consistency_ready"] is True
    assert payload["bounded_shell_material_tangent_smoke_ready"] is True
    assert payload["full_material_nonlinear_newton_equilibrium"] is False

    mesh = payload["mesh_fingerprint"]
    assert mesh["surface_element_count"] > 7000
    assert mesh["assembled_triangle_count"] >= mesh["surface_element_count"]
    assert mesh["material_tangent_shell_stiffness_nnz"] > 0

    probe = payload["controlled_probe_shell_material_state_summary"]
    assert probe["surface_element_count"] == mesh["surface_element_count"]
    assert probe["nonlinear_tangent_surface_element_count"] > 0
    assert probe["min_tangent_ratio"] < 0.98

    fd = payload["local_constitutive_tangent_fd_consistency"]
    assert fd["constitutive_tangent_fd_consistency_pass"] is True
    assert fd["eligible_row_count"] > 7000
    assert fd["max_relative_error"] <= fd["relative_error_tolerance"]

    jvp = payload["fixed_tangent_global_shell_jvp_consistency"]
    assert jvp["fixed_tangent_global_jvp_consistency_pass"] is True
    assert jvp["sample_direction_dof_count"] > 0
    assert jvp["relative_error"] <= jvp["relative_error_tolerance"]

    smoke = payload["material_tangent_shell_equilibrium"]
    assert smoke["material_tangent_override_surface_element_count"] == mesh["surface_element_count"]
    assert smoke["material_tangent_reduction_surface_element_count"] > 0
    assert smoke["residual_inf_n"] <= 1.0e-3

    consumption = payload["tangent_consumption_check"]
    assert consumption["tangent_consumption_ready"] is True
    assert consumption["stiffness_delta_nnz"] > 0
    assert consumption["stiffness_delta_inf"] > 0.0
