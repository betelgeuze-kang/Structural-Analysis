"""Tests for MGT surface shell bending/drilling tangent evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_surface_shell_bending_tangent_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_surface_shell_bending_tangent.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_shell_bending_tangent.py"),
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
    assert payload["schema_version"] == "mgt-surface-shell-bending-tangent.v1"
    assert payload["status"] == "ready"
    assert payload["surface_shell_bending_drilling_smoke_ready"] is True
    assert payload["surface_shell_transverse_pressure_smoke_ready"] is True
    assert payload["surface_shell_full_bending_tangent_ready"] is False
    mesh = payload["mesh_fingerprint"]
    assert mesh["surface_element_count"] > 7000
    assert mesh["assembled_triangle_count"] >= mesh["surface_element_count"]
    assert mesh["active_shell_dof_count"] > 25000
    coverage = payload["surface_material_coverage"]
    assert coverage["thickness_policy"] == "source_mgt_thickness_rows_by_plate_section_id"
    assert coverage["source_plate_thickness_coverage_pct"] == 100.0
    assert coverage["thickness_max_m"] >= coverage["thickness_min_m"] > 0.0
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert payload["equilibrium_metrics"]["relative_residual_inf"] <= 5.0e-8
    assert payload["anisotropy"]["mode"] == "isotropic"
    assert payload["anisotropy"]["orthotropic_ratio_d22_over_d11"] == 1.0
    opening = payload["opening_source_inventory"]
    assert opening["current_source_opening_marker_count"] == 0
    assert opening["current_source_opening_noop_ready"] is True
    assert opening["generic_opening_cutout_runtime_ready"] is False


def test_mgt_surface_shell_bending_tangent_orthotropic_smoke(tmp_path: Path) -> None:
    out = tmp_path / "mgt_surface_shell_bending_tangent_ortho.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_shell_bending_tangent.py"),
            "--material-anisotropy",
            "orthotropic",
            "--orthotropic-ratio",
            "0.5",
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
    aniso = payload["anisotropy"]
    assert aniso["mode"] == "orthotropic"
    assert aniso["orthotropic_ratio_d22_over_d11"] == 0.5
    assert aniso["d22_scaled"] is True
    assert aniso["poisson_coupling_d12_d21_scaled"] is True
    assert aniso["shear_block_d66_unscaled"] is True
    # Same tangent smoke; residual gate still satisfied
    assert payload["equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3


def test_mgt_surface_shell_bending_tangent_orthotropic_invalid_ratio(tmp_path: Path) -> None:
    out = tmp_path / "mgt_surface_shell_bending_tangent_invalid.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_shell_bending_tangent.py"),
            "--material-anisotropy",
            "orthotropic",
            "--orthotropic-ratio",
            "1.5",
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "orthotropic_ratio" in proc.stderr or "1.5" in proc.stderr
