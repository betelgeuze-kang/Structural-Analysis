"""Tests for AI-engine productization contract artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from implementation.phase1.build_ai_engine_productization_contracts import build_contracts


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_ai_engine_productization_contracts_writes_disabled_runtime_receipt(tmp_path: Path) -> None:
    (tmp_path / "ml_multi_objective_status.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-multi-objective-status.v1",
                "production_ml_wired": False,
                "ml_surrogate_production_gate": {
                    "checkpoint_path": str(tmp_path / "missing.pt"),
                    "checkpoint_ready": False,
                    "status": "disabled",
                },
            }
        ),
        encoding="utf-8",
    )
    payload = build_contracts(productization_dir=tmp_path)
    assert payload["schema_version"] == "ai-engine-productization-contracts.v1"
    assert payload["contracts_ready"] is True
    assert payload["production_ai_ready"] is False
    receipt = json.loads((tmp_path / "ai_inference_runtime_receipt.json").read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "ai-inference-runtime-receipt.v1"
    assert receipt["status"] == "disabled_no_validated_checkpoint"
    assert receipt["fallback_reason"] == "ml_surrogate_disabled_or_checkpoint_missing"
    assert receipt["runtime_budget_contract"]["latency_budget_ms"] == 250
    assert (
        receipt["runtime_budget_contract"]["cpu_gpu_parity_policy"]
        == "explicitly_blocked_until_validated_checkpoint"
    )
    registry = json.loads((tmp_path / "ai_model_registry.json").read_text(encoding="utf-8"))
    assert registry["registry_states"] == ["candidate", "shadow", "production", "deprecated"]
    assert "validated_production_checkpoint_missing" in registry["blockers"]


def test_build_ai_engine_productization_contracts_cli(tmp_path: Path) -> None:
    (tmp_path / "ml_multi_objective_status.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-multi-objective-status.v1",
                "production_ml_wired": False,
                "ml_surrogate_production_gate": {"checkpoint_path": str(tmp_path / "missing.pt")},
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_engine_productization_contracts.py"),
            "--productization-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "ai_engine_productization_contracts.json").is_file()
