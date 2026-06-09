#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_uncoarsened_boundary_global_equilibrium_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_uncoarsened_boundary_global_equilibrium.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_uncoarsened_boundary_global_equilibrium.py"),
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
    assert payload["schema_version"] == "mgt-uncoarsened-boundary-global-equilibrium.v1"
    assert payload["status"] == "ready"
    assert payload["uncoarsened_boundary_global_equilibrium_ready"] is True
    assert payload["global_frame_shell_tangent_integration_ready"] is True
    assert payload["roundtrip_policy"]["parser_coarsening"]["applied"] is False
    assert payload["mesh_fingerprint"]["node_count"] == 13047
    assert payload["mesh_fingerprint"]["elastic_link_spring_stiffness_nnz"] == 1692 * 6 * 4
    assert payload["boundary_summary"]["support_constraint_row_count"] == 8
    assert payload["boundary_summary"]["authored_support_node_count"] == 2133
    assert payload["boundary_summary"]["authored_support_restrained_dof_count"] == 7707
    assert payload["boundary_summary"]["elastic_link_row_count"] == 1692
    assert payload["boundary_summary"]["elastic_link_rows_skipped"] == 0
    assert payload["boundary_summary"]["finite_spring_component_count"] == 1692 * 6
    assert payload["support"]["solver_uses_authored_support_restraint_masks"] is True
    assert payload["support"]["solver_assembles_finite_elastic_link_springs"] is True
    assert payload["support"]["global_solver_consumes_authored_boundary_conditions"] is True
    assert payload["support"]["full_load_nonlinear_newton_ready"] is False
    assert payload["equilibrium_metrics"]["relative_residual_inf"] <= 2.0e-8
    assert payload["equilibrium_metrics"]["max_translation_m"] <= 5.0
