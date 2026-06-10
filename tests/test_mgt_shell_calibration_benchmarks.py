"""Tests for MGT shell calibration benchmark evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_shell_calibration_benchmarks_are_ready(tmp_path: Path) -> None:
    out = tmp_path / "mgt_shell_calibration_benchmarks.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_shell_calibration_benchmarks.py"),
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
    assert payload["schema_version"] == "mgt-shell-calibration-benchmarks.v1"
    assert payload["status"] == "ready"
    assert payload["shell_calibration_benchmarks_ready"] is True
    assert payload["case_count"] == payload["ready_case_count"] >= 5
    cases = {row["case_id"]: row for row in payload["cases"]}
    assert cases["membrane_constant_strain_patch"]["relative_error"] <= 1.0e-10
    assert cases["membrane_rigid_body_modes"]["max_normalized_residual"] <= 1.0e-12
    assert cases["shell_transverse_shear_patch"]["relative_error"] <= 1.0e-10
    assert cases["shell_zero_shear_rigid_slope"]["normalized_energy"] <= 1.0e-12
    plate = cases["clamped_square_plate_uniform_pressure"]
    assert plate["mesh_divisions"] >= 20
    assert plate["relative_error"] <= 0.15
    assert plate["residual_inf_n"] <= 1.0e-6
