"""Tests for the validated shadow ML surrogate checkpoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _build_temp_checkpoint(tmp_path: Path) -> tuple[dict[str, object], Path]:
    state_npz = tmp_path / "design_optimization_state.npz"
    checkpoint_dir = tmp_path / "checkpoint"
    productization_dir = tmp_path / "productization"
    row_count = 60
    np.savez_compressed(
        state_npz,
        group_ids=np.asarray([f"clean-checkout-group-{index:03d}" for index in range(row_count)]),
        max_dcr=np.full(row_count, 0.8),
        member_story_drift_contribution_pct=np.full(row_count, 0.05),
        group_cost_proxy=np.full(row_count, 1_000.0),
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ml_surrogate_checkpoint.py"),
            "--state-npz",
            str(state_npz),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--productization-dir",
            str(productization_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    manifest = json.loads(
        (productization_dir / "ml_surrogate_checkpoint_manifest.json").read_text(encoding="utf-8")
    )
    return manifest, productization_dir


def test_build_ml_surrogate_checkpoint_current_lane(tmp_path: Path) -> None:
    manifest, _productization_dir = _build_temp_checkpoint(tmp_path)
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


def test_ml_status_and_contracts_promote_only_shadow_solver_gated_checkpoint(tmp_path: Path) -> None:
    manifest, productization_dir = _build_temp_checkpoint(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(productization_dir / "ml_multi_objective_status.json"),
            "--pareto-archive-json",
            str(PRODUCTIZATION / "optimization_pareto_research_archive.json"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PHASE1_ML_SURROGATE_OPT_IN": "1",
            "PHASE1_ML_SURROGATE_CHECKPOINT": str(manifest["checkpoint_path"]),
        },
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    status = json.loads(
        (productization_dir / "ml_multi_objective_status.json").read_text(encoding="utf-8")
    )
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
            str(productization_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    contracts = json.loads(
        (productization_dir / "ai_engine_productization_contracts.json").read_text(encoding="utf-8")
    )
    inference = json.loads(
        (productization_dir / "ai_inference_runtime_receipt.json").read_text(encoding="utf-8")
    )
    assert contracts["status"] == "production_ai_ready"
    assert inference["status"] == "ready"
    assert inference["fallback_reason"] == "solver_replay_required_for_final_promotion"
