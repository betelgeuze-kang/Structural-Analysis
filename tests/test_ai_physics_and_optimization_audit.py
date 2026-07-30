"""Tests for AI physics guard and optimization productization audit."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _copy_productization_inputs(tmp_path: Path, names: tuple[str, ...]) -> Path:
    productization = tmp_path / "productization"
    productization.mkdir(exist_ok=True)
    for name in names:
        shutil.copy2(PRODUCTIZATION / name, productization / name)
    return productization


def test_build_ai_physics_guard_execution_current_lane(tmp_path: Path) -> None:
    productization = _copy_productization_inputs(
        tmp_path,
        (
            "ai_physics_guard_contract.json",
            "ai_inference_runtime_receipt.json",
            "mgt_global_fea_3d_native_solve.json",
            "mgt_direct_residual_newton_probe.json",
            "post_optimization_reanalysis_gate.json",
            "ai_decision_trace_ledger.json",
        ),
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_physics_guard_execution.py"),
            "--productization-dir",
            str(productization),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((productization / "ai_physics_guard_execution.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "ai-physics-guard-execution.v1"
    assert payload["status"] == "ready"
    assert payload["correction_promotion_blocked"] is True
    assert payload["direct_residual_correction_gate_enforced"] is True
    assert all(row["status"] == "pass" for row in payload["gate_rows"])
    direct_row = next(row for row in payload["gate_rows"] if row["id"] == "direct_residual_physics_correction")
    assert direct_row["value"]["direct_residual_newton_ready"] is False
    assert direct_row["value"]["gate_action"] == "blocked_from_promotion"
    assert direct_row["value"]["final_direct_residual_inf_n"] < direct_row["value"]["base_direct_residual_inf_n"]


def test_build_optimization_productization_audit_current_lane(tmp_path: Path) -> None:
    productization = _copy_productization_inputs(
        tmp_path,
        (
            "design_optimization_cost_reduction_changes.json",
            "proxy_solver_divergence_gate.json",
            "post_optimization_reanalysis_gate.json",
            "ai_decision_trace_ledger.json",
            "ai_review_queue.json",
            "ai_code_reasoning_guard.json",
            "ai_safety_governance_contract.json",
            "optimization_pareto_research_archive.json",
            "ml_multi_objective_status.json",
        ),
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_productization_audit.py"),
            "--productization-dir",
            str(productization),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((productization / "optimization_productization_audit.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "optimization-productization-audit.v1"
    assert payload["status"] == "ready"
    assert payload["optimization_productization_ready"] is True
    assert payload["accepted_rows_have_code"] is True
    assert payload["accepted_rows_have_explicit_clause"] is False
    assert payload["missing_governing_clause_count"] == 1
    assert payload["all_rows_have_clause_or_review_guard"] is True
    assert payload["production_pareto_wired"] is True
    assert payload["ml_bypass_prevented"] is True
