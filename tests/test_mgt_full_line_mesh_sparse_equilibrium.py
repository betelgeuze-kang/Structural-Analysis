"""Tests for full line/beam sparse MGT equilibrium evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_full_line_mesh_sparse_equilibrium_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_full_line_mesh_sparse_equilibrium.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_full_line_mesh_sparse_equilibrium.py"),
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
    assert payload["schema_version"] == "mgt-full-line-mesh-sparse-equilibrium.v1"
    assert payload["status"] == "ready"
    assert payload["full_line_mesh_sparse_elastic_equilibrium_ready"] is True
    assert payload["full_line_mesh_linearized_geometric_equilibrium_ready"] is True
    assert payload["full_line_mesh_nonlinear_equilibrium"] is False
    mesh = payload["mesh_fingerprint"]
    assert mesh["line_elements_solved"] + mesh["skipped_short_or_degenerate_count"] == mesh["raw_line_element_count"]
    assert mesh["line_elements_solved"] > 1000
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert payload["geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert payload["linearized_geometric_tangent"]["positive_axial_element_count"] > 0
    assert payload["runtime_metrics"]["backend"] == "scipy_sparse_spsolve_cpu"
