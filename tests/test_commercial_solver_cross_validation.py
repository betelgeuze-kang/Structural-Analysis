"""Tests for commercial HF/LF cross-validation report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cross_validation_report_passes_sample_cases() -> None:
    cases_path = REPO_ROOT / "implementation/phase1/commercial_benchmark_cases.from_csv.json"
    out_path = REPO_ROOT / "implementation/phase1/release_evidence/commercial/cross_validation_report_test.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/report_commercial_solver_cross_validation.py"),
        "--cases-json",
        str(cases_path),
        "--output-json",
        str(out_path),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["case_count"] >= 10
    assert report["status"] in {"pass", "partial", "pass_with_marginal_metrics"}
    assert report["modal_buckling_summary"]["case_count"] == report["case_count"]


def test_compare_case_metrics_flags_large_drift_error() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from report_commercial_solver_cross_validation import compare_case_metrics  # noqa: E402

    deltas = compare_case_metrics(
        {
            "case_id": "X",
            "metrics": {
                "drift_ratio_pct": {"hf": 2.0, "lf": 1.0},
            },
        }
    )
    drift = next(row for row in deltas if row.metric == "drift_ratio_pct")
    assert drift.ok is False
    assert drift.marginal_only is False


def test_marginal_buckling_within_tolerance_band() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from report_commercial_solver_cross_validation import compare_case_metrics  # noqa: E402

    deltas = compare_case_metrics(
        {
            "case_id": "C-TST-003",
            "metrics": {"buckling_factor": {"hf": 2.1, "lf": 1.84}},
        }
    )
    buck = next(row for row in deltas if row.metric == "buckling_factor")
    assert buck.ok is False
    assert buck.marginal_only is True
