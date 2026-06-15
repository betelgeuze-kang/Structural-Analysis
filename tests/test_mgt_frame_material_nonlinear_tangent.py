"""Tests for bounded frame material nonlinear tangent evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


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
    assert payload["material_tangent_smoke_equilibrium"]["tangent_reduction_element_count"] > 0
    assert payload["material_tangent_smoke_equilibrium"]["residual_inf_n"] <= 1.0e-3
    strengths = payload["material_strength_inventory"]
    assert any(row["family"] == "STEEL" and row["inferred_strength_mpa"] == 235.0 for row in strengths.values())
    assert any(row["family"] == "CONC" and row["inferred_strength_mpa"] == 40.0 for row in strengths.values())
    assert payload["weakest_probe_elements"]
