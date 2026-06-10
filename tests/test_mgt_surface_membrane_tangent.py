"""Tests for MGT surface membrane tangent evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_surface_membrane_tangent_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_surface_membrane_tangent.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_membrane_tangent.py"),
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
    assert payload["schema_version"] == "mgt-surface-membrane-tangent.v1"
    assert payload["status"] == "ready"
    assert payload["surface_membrane_tangent_ready"] is True
    assert payload["surface_membrane_smoke_solve_ready"] is True
    assert payload["surface_shell_full_bending_tangent_ready"] is False
    mesh = payload["mesh_fingerprint"]
    assert mesh["surface_element_count"] > 7000
    assert mesh["assembled_triangle_count"] >= mesh["surface_element_count"]
    assert mesh["active_membrane_dof_count"] > 0
    coverage = payload["surface_material_coverage"]
    assert coverage["thickness_policy"] == "source_mgt_thickness_rows_by_plate_section_id"
    assert coverage["source_plate_thickness_coverage_pct"] == 100.0
    assert coverage["thickness_min_m"] > 0.0
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
