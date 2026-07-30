from pathlib import Path
import json
import subprocess
import sys

import pytest

REPORT = Path(
    "implementation/phase1/release/design_optimization/design_optimization_budgeted_report.json"
)
PROFILE = Path(
    "implementation/phase1/release/design_optimization/design_objective_profile_report.json"
)
DATASET = Path(
    "implementation/phase1/release/design_optimization/design_optimization_dataset.npz"
)


def _ensure_reports():
    if REPORT.exists() and PROFILE.exists():
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        if (
            report.get("summary", {}).get("objective_profile") == "cost_first"
            and profile.get("profile_name") == "cost_first"
        ):
            return
    if not DATASET.exists():
        pytest.skip(
            "legacy budgeted optimization requires the non-committed "
            "design_optimization_dataset.npz evidence input"
        )
    subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_design_optimization_budgeted.py",
            "--budget",
            "low",
            "--objective-profile",
            "cost_first",
        ],
        check=True,
    )


def test_budgeted_runner_and_profile_report_exist():
    _ensure_reports()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    summary = report["summary"]
    assert summary["budget_mode"] in {"low", "medium", "high"}
    assert "expected_feasible_probability" in summary
    assert "expected_cost_reduction" in summary
    assert "expected_constructability_gain" in summary
    assert "expected_runtime_s" in summary
    assert profile["profile_name"] == "cost_first"
    assert "final_weights" in profile
