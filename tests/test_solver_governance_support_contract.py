"""Tests for solver governance/support evidence contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_solver_governance_support_contract_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_solver_governance_support_contract.py"),
            "--productization-dir",
            str(REPO_ROOT / "implementation/phase1/release_evidence/productization"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/solver_governance_support_contract.json")
        .read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "solver-governance-support-contract.v1"
    assert payload["status"] == "ready"
    assert payload["unsupported_state_first_report_policy"] is True
    assert "solver_derived" in payload["report_state_separation"]
    assert "proxy_derived" in payload["report_state_separation"]
    assert "ai_assisted" in payload["report_state_separation"]
    assert payload["engineer_review_workflow"]["ai_queue_item_count"] >= 1
