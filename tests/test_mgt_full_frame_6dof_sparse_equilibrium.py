"""Tests for full line-element 6-DOF frame sparse MGT equilibrium evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_full_frame_6dof_sparse_equilibrium_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_full_frame_6dof_sparse_equilibrium.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_full_frame_6dof_sparse_equilibrium.py"),
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
    assert payload["schema_version"] == "mgt-full-frame-6dof-sparse-equilibrium.v1"
    assert payload["status"] == "ready"
    assert payload["full_frame_6dof_sparse_elastic_equilibrium_ready"] is True
    assert payload["full_frame_6dof_linearized_geometric_equilibrium_ready"] is True
    assert payload["full_frame_6dof_deformed_state_pdelta_equilibrium_ready"] is True
    assert payload["full_frame_6dof_nonlinear_equilibrium"] is False
    refinement = payload["linear_solver_refinement"]
    assert refinement["enabled"] is True
    assert refinement["max_iterations"] == 10
    assert refinement["strategy"] == "best_residual_iterative_refinement"
    mesh = payload["mesh_fingerprint"]
    assert mesh["line_elements_solved"] + mesh["skipped_short_or_degenerate_count"] == mesh["raw_line_element_count"]
    assert mesh["line_elements_solved"] > 1000
    assert mesh["dof_count"] == mesh["line_nodes_solved"] * 6
    assert payload["section_material_coverage"]["real_section_material_coverage_pct"] > 90.0
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert payload["geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert payload["linearized_geometric_tangent"]["positive_axial_element_count"] > 0
    path = payload["deformed_state_pdelta_path"]
    assert path["converged"] is True
    assert path["linear_solver_refinement"]["enabled"] is True
    assert path["linear_solver_refinement"]["max_iterations"] == 10
    assert path["load_scale_reached"] >= 0.5
    assert path["initial_displacement_was_seeded"] is False
    assert path["relaxation_factor"] == 1.0
    assert path["iteration_count"] <= 24
    assert path["relative_increment"] <= 1.0e-4
    assert path["convergence_increment_metric"] == "unrelaxed_fixed_point_relative_increment"
    assert path["fixed_point_increment_m"] > 0.0
    assert path["history_tail"][-1]["fixed_point_relative_increment"] == path["relative_increment"]
    offset = payload["beam_end_offset_support"]
    assert offset["rigid_end_offset_transform_applied"] is True
    assert offset["rigid_end_offset_tangent_ready"] is True
    assert offset["applied_element_count"] >= 700
    assert offset["max_abs_offset_m"] >= 0.5
    local_axis = payload["frame_local_axis_support"]
    assert local_axis["frame_angle_rows_consumed"] is True
    assert local_axis["frame_nonzero_angle_element_count"] == 150
    assert local_axis["frame_max_abs_angle_deg"] >= 90.0
    assert local_axis["solver_local_axis_roll_transform_ready"] is True
    assert local_axis["elastic_assembly_roll_transform_applied_count"] == 150
    assert payload["runtime_metrics"]["backend"] == "scipy_sparse_spsolve_cpu_6dof_frame"
    assert payload["runtime_metrics"]["linear_solver_refinement_enabled"] is True
