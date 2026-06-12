"""Tests for AI input normalization and code-reasoning guard artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_ai_input_code_guard_artifacts_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_input_code_guard_artifacts.py"),
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
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/ai_input_code_guard_artifacts.json")
        .read_text(encoding="utf-8")
    )
    input_receipt = json.loads(
        (
            REPO_ROOT
            / "implementation/phase1/release_evidence/productization/ai_input_semantic_normalization_receipt.json"
        ).read_text(encoding="utf-8")
    )
    code_guard = json.loads(
        (REPO_ROOT / "implementation/phase1/release_evidence/productization/ai_code_reasoning_guard.json")
        .read_text(encoding="utf-8")
    )
    assert index["schema_version"] == "ai-input-code-guard-artifacts.v1"
    assert index["status"] == "ready"
    assert input_receipt["status"] == "ready"
    assert input_receipt["unsupported_queue"]
    assert code_guard["status"] == "ready"
    assert code_guard["governing_clause_count"] >= 1
    assert code_guard["all_rows_have_clause_or_review_guard"] is True
    assert code_guard["missing_governing_clause_count"] == 1
    assert code_guard["unsupported_clause_queue"][0]["status"] == "engineer_review_required"
    assert code_guard["hallucination_guard"]["llm_free_default"] is True
