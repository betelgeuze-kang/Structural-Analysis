"""Tests for load/stage and AI decision-review productization artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_load_stage_semantics_contract_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_load_stage_semantics_contract.py"),
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
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/load_stage_semantics_contract.json")
        .read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "load-stage-semantics-contract.v1"
    assert payload["typed_runtime_entities_ready"] is True
    assert payload["stage_semantics_ready"] is True
    assert payload["summary"]["combination_entity_count"] >= 1
    assert payload["summary"]["construction_stage_count"] >= 1


def test_build_ai_decision_review_artifacts_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_decision_review_artifacts.py"),
            "--productization-dir",
            str(REPO_ROOT / "implementation/phase1/release_evidence/productization"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    index = json.loads(
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/ai_decision_review_artifacts.json")
        .read_text(encoding="utf-8")
    )
    trace = json.loads(
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/ai_decision_trace_ledger.json")
        .read_text(encoding="utf-8")
    )
    queue = json.loads(
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/ai_review_queue.json")
        .read_text(encoding="utf-8")
    )
    assert index["schema_version"] == "ai-decision-review-artifacts.v1"
    assert index["policy_replay_contract_ready"] is True
    assert trace["status"] == "ready"
    assert trace["proposal_count"] == trace["source_change_count"]
    assert queue["status"] == "ready"
    assert queue["queue_item_count"] == trace["proposal_count"]
