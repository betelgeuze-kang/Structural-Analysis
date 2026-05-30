"""Tests for ML multi-objective honesty status."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ml_status_reports_not_started() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/ml_multi_objective_status_test.json"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"), "--output-json", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "not_started"
    assert payload["multi_objective_pareto_wired"] is False
