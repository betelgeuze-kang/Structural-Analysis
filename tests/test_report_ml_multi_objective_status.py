"""Tests for ML multi-objective honesty status."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ml_status_reports_research_archive_when_pareto_present() -> None:
    pareto_out = REPO_ROOT / "implementation/phase1/release_evidence/productization/optimization_pareto_research_archive_test.json"
    changes = REPO_ROOT / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_pareto_research_archive.py"),
            "--changes-json",
            str(changes),
            "--output-json",
            str(pareto_out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/ml_multi_objective_status_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(out),
            "--pareto-archive-json",
            str(pareto_out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PHASE1_ML_SURROGATE_DISABLE": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "research_archive_ready"
    assert payload["research_pareto_archive_ready"] is True
    assert payload["multi_objective_pareto_wired"] is False
    assert payload["production_ml_wired"] is False
