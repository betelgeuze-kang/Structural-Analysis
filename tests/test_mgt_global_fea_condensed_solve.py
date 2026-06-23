#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_condensed_solve_reports_backend_aware_status(tmp_path: Path) -> None:
    out = tmp_path / "mgt_global_fea_condensed_solve_test.json"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    env = {**os.environ, "PHASE1_FORCE_CPU_RUNTIME": "1"}
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_condensed_solve.py"),
            "--roundtrip-json",
            str(roundtrip),
            "--output-json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert out.exists(), proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["solve_mode"] == "mgt_npz_mesh_condensed_story"
    assert "not a full 3D global FEA licensed-engine replay" in payload["claim"]
    backend_values = {
        payload["static_solve"]["backend"],
        payload["ndtha_solve"]["backend"],
    }
    assert backend_values == {"rust_ffi_cpu"}
    assert payload["backend_policy"] == {
        "required_backend": "rocm_torch_hip_mainloop",
        "observed_backends": ["rust_ffi_cpu"],
        "hip_backend_ready": False,
        "cpu_fallback_non_promoting": True,
    }
    assert proc.returncode == 1
    assert payload["status"] == "warn"
    assert payload["native_solve_status"] == "condensed_global_fea_backend_blocked"
    assert "rocm_hip_backend_unavailable_or_cpu_fallback" in payload["blockers"]
