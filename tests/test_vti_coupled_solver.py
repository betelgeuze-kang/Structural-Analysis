from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/vti_coupled_solver.py")


def test_vti_default_contact_evidence_generates_positive_force(tmp_path: Path) -> None:
    out = tmp_path / "vti_coupled_solver_report.json"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["inputs"]["config"]["axle_offsets_m"] == [0.0, 2.5, 5.0, 7.5]
    assert payload["metrics"]["max_contact_force_n"] > 1e-6
