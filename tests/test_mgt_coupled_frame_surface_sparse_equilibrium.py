"""Tests for coupled frame + surface sparse MGT equilibrium evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_coupled_frame_surface_sparse_equilibrium_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_coupled_frame_surface_sparse_equilibrium.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_coupled_frame_surface_sparse_equilibrium.py"),
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
    assert payload["schema_version"] == "mgt-coupled-frame-surface-sparse-equilibrium.v1"
    assert payload["status"] == "ready"
    assert payload["coupled_frame_surface_sparse_equilibrium_ready"] is True
    assert payload["coupled_frame_surface_nonlinear_equilibrium"] is False
    assert payload["surface_shell_full_bending_tangent_ready"] is False
    mesh = payload["mesh_fingerprint"]
    assert mesh["line_elements_solved"] > 5000
    assert mesh["surface_element_count"] > 7000
    assert mesh["assembled_triangle_count"] >= mesh["surface_element_count"]
    assert mesh["coupled_stiffness_nnz"] >= mesh["frame_stiffness_nnz"]
    assert mesh["coupled_stiffness_nnz"] > 400000
    assert mesh["active_dof_count"] > 30000
    assert mesh["free_dof_count"] > 25000
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 5.0e-2
    assert payload["equilibrium_metrics"]["relative_residual_inf"] <= 2.0e-8
    assert payload["equilibrium_metrics"]["frame_gravity_load_scale"] == 0.01
    assert payload["equilibrium_metrics"]["max_translation_m"] <= 5.0
    offset = payload["beam_end_offset_support"]
    assert offset["rigid_end_offset_transform_applied"] is True
    assert offset["applied_element_count"] >= 700
    assert offset["max_abs_offset_m"] >= 0.5
    assert payload["runtime_metrics"]["backend"] == "scipy_sparse_spsolve_cpu_coupled_frame_surface"
    coverage = payload["surface_material_coverage"]
    assert coverage["thickness_policy"] == "source_mgt_thickness_rows_by_plate_section_id"
    assert coverage["source_plate_thickness_coverage_pct"] == 100.0
