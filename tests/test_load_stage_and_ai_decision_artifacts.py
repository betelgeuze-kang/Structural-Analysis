"""Tests for load/stage and AI decision-review productization artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_load_stage_semantics_contract_current_lane(tmp_path: Path) -> None:
    construction_gate = tmp_path / "construction_sequence_gate_report.json"
    construction_gate.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "summary": {
                    "stage_count": 24,
                    "case_count": 4,
                    "construction_years": 4.0,
                },
                "checks": {
                    "all_stages_converged": True,
                    "stagewise_monotonic_load_pass": True,
                    "creep_shrinkage_applied": True,
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "load_stage_semantics_contract.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_load_stage_semantics_contract.py"),
            "--productization-dir",
            str(REPO_ROOT / "implementation/phase1/release_evidence/productization"),
            "--construction-gate-json",
            str(construction_gate),
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
    assert payload["schema_version"] == "load-stage-semantics-contract.v1"
    assert payload["typed_runtime_entities_ready"] is True
    assert payload["stage_semantics_ready"] is True
    assert payload["summary"]["combination_entity_count"] >= 1
    assert payload["summary"]["construction_stage_count"] >= 1


def test_build_ai_decision_review_artifacts_current_lane(tmp_path: Path) -> None:
    source_dir = REPO_ROOT / "implementation/phase1/release_evidence/productization"
    productization_dir = tmp_path / "productization"
    productization_dir.mkdir()
    for filename in (
        "design_optimization_cost_reduction_changes.json",
        "design_optimization_cost_reduction_blocked_actions.json",
        "post_optimization_reanalysis_gate.json",
        "proxy_solver_divergence_gate.json",
        "optimization_pareto_research_archive.json",
        "ai_safety_governance_contract.json",
        "ai_decision_trace_contract.json",
        "ai_review_queue_contract.json",
    ):
        shutil.copy2(source_dir / filename, productization_dir / filename)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_decision_review_artifacts.py"),
            "--productization-dir",
            str(productization_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    index = json.loads(
        (productization_dir / "ai_decision_review_artifacts.json").read_text(
            encoding="utf-8"
        )
    )
    trace = json.loads(
        (productization_dir / "ai_decision_trace_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    queue = json.loads(
        (productization_dir / "ai_review_queue.json").read_text(encoding="utf-8")
    )
    assert index["schema_version"] == "ai-decision-review-artifacts.v1"
    assert index["policy_replay_contract_ready"] is True
    assert trace["status"] == "ready"
    assert trace["proposal_count"] == trace["source_change_count"]
    assert queue["status"] == "ready"
    assert queue["queue_item_count"] == trace["proposal_count"]
