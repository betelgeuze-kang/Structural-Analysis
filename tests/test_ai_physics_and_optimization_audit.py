"""Tests for AI physics guard and optimization productization audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def test_build_ai_physics_guard_execution_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_physics_guard_execution.py"),
            "--productization-dir",
            str(PRODUCTIZATION),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((PRODUCTIZATION / "ai_physics_guard_execution.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "ai-physics-guard-execution.v1"
    assert payload["status"] == "ready"
    assert payload["correction_promotion_blocked"] is True
    assert payload["direct_residual_correction_gate_enforced"] is True
    assert all(row["status"] == "pass" for row in payload["gate_rows"])
    direct_row = next(row for row in payload["gate_rows"] if row["id"] == "direct_residual_physics_correction")
    assert direct_row["value"]["direct_residual_newton_ready"] is False
    assert direct_row["value"]["gate_action"] == "blocked_from_promotion"
    assert direct_row["value"]["final_direct_residual_inf_n"] < direct_row["value"]["base_direct_residual_inf_n"]


def test_build_optimization_productization_audit_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_productization_audit.py"),
            "--productization-dir",
            str(PRODUCTIZATION),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((PRODUCTIZATION / "optimization_productization_audit.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "optimization-productization-audit.v1"
    assert payload["status"] == "ready"
    assert payload["optimization_productization_ready"] is True
    assert payload["accepted_rows_have_code"] is True
    assert payload["accepted_rows_have_explicit_clause"] is False
    assert payload["missing_governing_clause_count"] == 1
    assert payload["all_rows_have_clause_or_review_guard"] is True
    assert payload["production_pareto_wired"] is True
    assert payload["ml_bypass_prevented"] is True
