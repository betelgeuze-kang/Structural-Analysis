#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_coupled_frame_shell_story_eccentricity_equilibrium import (  # noqa: E402
    run_mgt_coupled_frame_shell_story_eccentricity_equilibrium,
)


def test_coupled_frame_shell_story_eccentricity_equilibrium_ready() -> None:
    payload = run_mgt_coupled_frame_shell_story_eccentricity_equilibrium()
    assert payload["schema_version"] == "mgt-coupled-frame-shell-story-eccentricity-equilibrium.v1"
    assert payload["status"] == "ready"
    assert payload["coupled_frame_shell_story_eccentricity_equilibrium_ready"] is True
    assert payload["equilibrium_summary"]["case_count"] == 4
    assert payload["equilibrium_summary"]["ready_case_count"] == 4
    assert payload["equilibrium_summary"]["max_residual_inf_n"] <= 5.0e-2
    assert payload["equilibrium_summary"]["max_relative_residual_inf"] <= 1.0e-6
    assert payload["support"]["story_eccentricity_load_generation_ready"] is True
    assert payload["support"]["global_solver_consumes_story_eccentricity_loads"] is True
    assert payload["support"]["coupled_frame_shell_story_eccentricity_solve_ready"] is True
    assert payload["support"]["full_load_nonlinear_newton_ready"] is False
    assert payload["case_rows"][0]["family"] == "seismic_accidental_eccentricity"
    assert payload["case_rows"][0]["equivalent_entry_count"] > 0


def test_coupled_frame_shell_story_eccentricity_cli(tmp_path: Path) -> None:
    out = tmp_path / "mgt_coupled_frame_shell_story_eccentricity_equilibrium.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_coupled_frame_shell_story_eccentricity_equilibrium.py"),
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
    assert payload["equilibrium_summary"]["ready_case_count"] == 4
