"""Tests for proxy/solver divergence gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGES = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
)


def test_proxy_gate_writes_report_on_release_changes() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/proxy_solver_divergence_gate_test.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_proxy_solver_divergence_gate.py"),
        "--changes-json",
        str(CHANGES),
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["change_count"] > 0
    assert report["schema_version"] == "proxy-solver-divergence-gate.v1"


def test_analyze_changes_flags_high_dcr() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from run_proxy_solver_divergence_gate import analyze_changes  # noqa: E402

    report = analyze_changes(
        {
            "changes": [
                {
                    "group_id": "g1",
                    "cost_proxy_delta": -10.0,
                    "drift_before_pct": 1.0,
                    "drift_after_pct": 1.0,
                    "governing_member_governing_dcr_after": 1.4,
                }
            ]
        },
        max_governing_dcr_after=1.35,
    )
    assert report["divergence_count"] >= 1
