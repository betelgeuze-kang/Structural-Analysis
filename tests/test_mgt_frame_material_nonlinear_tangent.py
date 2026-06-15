"""Tests for bounded frame material nonlinear tangent evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_frame_material_nonlinear_tangent import (  # noqa: E402
    _apply_local_direction,
    _stress_axial_correction_global_with_tangent,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import FrameElement  # noqa: E402


def test_mgt_frame_material_nonlinear_tangent_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_frame_material_nonlinear_tangent.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_frame_material_nonlinear_tangent.py"),
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
    assert payload["schema_version"] == "mgt-frame-material-nonlinear-tangent.v1"
    assert payload["status"] == "ready"
    assert payload["frame_material_nonlinear_tangent_ready"] is True
    assert payload["service_load_material_state_ready"] is True
    assert payload["controlled_probe_material_state_ready"] is True
    assert payload["local_constitutive_tangent_fd_consistency_ready"] is True
    assert payload["bounded_material_tangent_global_smoke_ready"] is True
    assert payload["global_smoke_solver_uses_per_element_material_tangent"] is True
    assert payload["full_material_nonlinear_newton_equilibrium"] is False
    mesh = payload["mesh_fingerprint"]
    assert mesh["line_elements_solved"] > 1000
    assert mesh["line_elements_solved"] + mesh["skipped_short_or_degenerate_count"] == mesh["raw_line_element_count"]
    service = payload["service_material_state_summary"]
    probe = payload["controlled_probe_material_state_summary"]
    assert service["element_count"] == mesh["line_elements_solved"]
    assert probe["element_count"] == mesh["line_elements_solved"]
    assert probe["nonlinear_tangent_element_count"] > 0
    assert probe["min_tangent_ratio"] < 0.98
    fd = payload["local_constitutive_tangent_fd_consistency"]
    assert fd["constitutive_tangent_fd_consistency_pass"] is True
    assert fd["row_count"] > mesh["line_elements_solved"]
    assert fd["eligible_row_count"] > 10000
    assert fd["max_relative_error"] <= fd["relative_error_tolerance"]
    assert fd["max_absolute_error_mpa"] <= fd["absolute_error_tolerance_mpa"]
    assert fd["bounded_solver_tangent_row_count"] > 0
    global_fd = payload["global_axial_stress_correction_fd_consistency"]
    assert payload["global_axial_stress_correction_fd_consistency_ready"] is True
    assert global_fd["global_stress_correction_fd_consistency_pass"] is True
    assert global_fd["eligible_row_count"] > 7000
    assert global_fd["max_relative_error"] <= global_fd["relative_error_tolerance"]
    assert global_fd["max_absolute_error_n_per_m"] <= global_fd["absolute_error_tolerance_n_per_m"]
    assert payload["material_tangent_smoke_equilibrium"]["tangent_reduction_element_count"] > 0
    assert payload["material_tangent_smoke_equilibrium"]["residual_inf_n"] <= 1.0e-3
    strengths = payload["material_strength_inventory"]
    assert any(row["family"] == "STEEL" and row["inferred_strength_mpa"] == 235.0 for row in strengths.values())
    assert any(row["family"] == "CONC" and row["inferred_strength_mpa"] == 40.0 for row in strengths.values())
    assert payload["weakest_probe_elements"]


def test_stress_axial_correction_global_tangent_matches_fd() -> None:
    elem = FrameElement(elem_id=1, node_i=0, node_j=1, section_id=1, material_id=1, length_m=2.0)
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float64)
    section_props = {1: {"A_m2": 0.01, "Iy_m4": 1.0e-4, "Iz_m4": 1.0e-4, "J_m4": 1.0e-5}}
    material_props = {1: {"type": "STEEL", "name": "Q235", "E_kN_per_m2": 210000000.0, "poisson": 0.3}}
    u = np.zeros(12, dtype=np.float64)
    u[6] = 0.004
    correction, tangent, meta = _stress_axial_correction_global_with_tangent(
        elem=elem,
        node_xyz=node_xyz,
        u=u,
        section_props=section_props,
        material_props=material_props,
    )
    assert meta["state_tag"] == "steel_plastic_hardening"
    assert np.max(np.abs(correction)) > 0.0
    assert np.max(np.abs(tangent)) > 0.0

    direction = np.zeros(12, dtype=np.float64)
    direction[0] = -1.0
    direction[6] = 1.0
    eps = 1.0e-7
    plus_u = _apply_local_direction(u=u, elem=elem, local_direction=direction, scale=eps)
    minus_u = _apply_local_direction(u=u, elem=elem, local_direction=direction, scale=-eps)
    plus, _plus_tangent, _plus_meta = _stress_axial_correction_global_with_tangent(
        elem=elem,
        node_xyz=node_xyz,
        u=plus_u,
        section_props=section_props,
        material_props=material_props,
    )
    minus, _minus_tangent, _minus_meta = _stress_axial_correction_global_with_tangent(
        elem=elem,
        node_xyz=node_xyz,
        u=minus_u,
        section_props=section_props,
        material_props=material_props,
    )
    fd_jvp = (plus - minus) / (2.0 * eps)
    analytic_jvp = tangent @ direction
    np.testing.assert_allclose(fd_jvp, analytic_jvp, rtol=1.0e-7, atol=1.0e-3)
