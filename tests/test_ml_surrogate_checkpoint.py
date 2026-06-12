"""Tests for the validated shadow ML surrogate checkpoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def test_build_ml_surrogate_checkpoint_current_lane() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ml_surrogate_checkpoint.py"),
            "--productization-dir",
            str(PRODUCTIZATION),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    manifest = json.loads((PRODUCTIZATION / "ml_surrogate_checkpoint_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ml-surrogate-checkpoint-manifest.v1"
    assert manifest["status"] == "ready"
    assert manifest["validation_pass"] is True
    assert manifest["ood_pass"] is True
    assert manifest["solver_fallback_verified"] is True

    for key in [
        "dataset_card_path",
        "model_card_path",
        "validation_receipt_path",
        "ood_gate_path",
        "solver_fallback_receipt_path",
    ]:
        assert Path(manifest[key]).is_file()


def test_ml_status_and_contracts_promote_only_shadow_solver_gated_checkpoint() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(PRODUCTIZATION / "ml_multi_objective_status.json"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    status = json.loads((PRODUCTIZATION / "ml_multi_objective_status.json").read_text(encoding="utf-8"))
    gate = status["ml_surrogate_production_gate"]
    assert status["status"] == "production_shadow_solver_gated_ready"
    assert status["production_ml_wired"] is True
    assert gate["checkpoint_validated"] is True
    assert gate["hard_gate_bypass_prevented"] is True

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_engine_productization_contracts.py"),
            "--productization-dir",
            str(PRODUCTIZATION),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    contracts = json.loads((PRODUCTIZATION / "ai_engine_productization_contracts.json").read_text(encoding="utf-8"))
    inference = json.loads((PRODUCTIZATION / "ai_inference_runtime_receipt.json").read_text(encoding="utf-8"))
    assert contracts["status"] == "production_ai_ready"
    assert inference["status"] == "ready"
    assert inference["fallback_reason"] == "solver_replay_required_for_final_promotion"
