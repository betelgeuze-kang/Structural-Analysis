"""Tests for the native MGT modal and buckling solver evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mgt_native_modal_buckling_solver_generates_ready_evidence(tmp_path: Path) -> None:
    out = tmp_path / "mgt_native_modal_buckling_solver.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_modal_buckling_solver.py"),
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
    assert payload["schema_version"] == "mgt-native-modal-buckling-solver.v1"
    assert payload["status"] == "ready"
    assert payload["native_solver_ready"] is True
    assert payload["benchmark_contract_pass"] is True
    assert payload["modal_solve"]["mode_count"] >= 3
    assert payload["buckling_solve"]["critical_load_factor"] > 1.0
    assert payload["matrices"]["stiffness_matrix_ready"] is True
    assert payload["matrices"]["mass_matrix_ready"] is True
    assert payload["matrices"]["geometric_stiffness_ready"] is True
