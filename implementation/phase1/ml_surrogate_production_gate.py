#!/usr/bin/env python3
"""Opt-in gate for ML surrogate in production optimization (default off)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ml-surrogate-production-gate.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = REPO_ROOT / "implementation/phase1/release/ml_surrogate/checkpoint.pt"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(checkpoint: Path, raw: Any) -> Path:
    path = Path(str(raw or ""))
    if not path.is_absolute():
        path = checkpoint.parent / path
    return path


def probe_ml_surrogate_production_gate() -> dict[str, Any]:
    opt_in = str(os.environ.get("PHASE1_ML_SURROGATE_OPT_IN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    forced_disabled = str(os.environ.get("PHASE1_ML_SURROGATE_DISABLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    checkpoint = Path(
        str(os.environ.get("PHASE1_ML_SURROGATE_CHECKPOINT") or "")
        or DEFAULT_CHECKPOINT
    )
    checkpoint_payload = _load_json(checkpoint)
    checkpoint_ready = checkpoint_payload.get("schema_version") == "ml-surrogate-checkpoint.v1"
    artifacts = checkpoint_payload.get("artifacts") if isinstance(checkpoint_payload.get("artifacts"), dict) else {}
    dataset_card_path = _artifact_path(checkpoint, artifacts.get("dataset_card"))
    model_card_path = _artifact_path(checkpoint, artifacts.get("model_card"))
    validation_path = _artifact_path(checkpoint, artifacts.get("validation_receipt"))
    ood_path = _artifact_path(checkpoint, artifacts.get("ood_gate"))
    fallback_path = _artifact_path(checkpoint, artifacts.get("solver_fallback_receipt"))
    dataset_card = _load_json(dataset_card_path)
    model_card = _load_json(model_card_path)
    validation = _load_json(validation_path)
    ood = _load_json(ood_path)
    fallback = _load_json(fallback_path)
    dataset_card_ready = dataset_card.get("status") == "ready"
    model_card_ready = model_card.get("status") == "ready"
    validation_ready = validation.get("status") == "pass" and bool(validation.get("validation_pass"))
    ood_gate_ready = ood.get("status") == "pass" and bool(ood.get("ood_pass"))
    solver_fallback_ready = fallback.get("status") == "verified" and bool(fallback.get("solver_fallback_verified"))
    activation = (
        checkpoint_payload.get("production_activation")
        if isinstance(checkpoint_payload.get("production_activation"), dict)
        else {}
    )
    activation_enabled = bool(activation.get("enabled")) and activation.get("mode") == "shadow_with_solver_fallback"
    hard_gate_bypass_prevented = bool(
        solver_fallback_ready
        and fallback.get("hard_gate_bypass_prevented")
        and activation.get("can_change_final_design_without_solver") is False
    )
    checkpoint_validated = bool(
        checkpoint_ready
        and dataset_card_ready
        and model_card_ready
        and validation_ready
        and ood_gate_ready
        and solver_fallback_ready
        and hard_gate_bypass_prevented
    )
    wired = bool(not forced_disabled and activation_enabled and checkpoint_validated)
    if wired:
        status = "production_ready_shadow_solver_gated"
    elif forced_disabled:
        status = "disabled_by_env"
    elif checkpoint_ready and not checkpoint_validated:
        status = "checkpoint_present_validation_incomplete"
    elif opt_in:
        status = "opt_in_without_checkpoint"
    else:
        status = "disabled"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "opt_in_env": "PHASE1_ML_SURROGATE_OPT_IN",
        "checkpoint_env": "PHASE1_ML_SURROGATE_CHECKPOINT",
        "disable_env": "PHASE1_ML_SURROGATE_DISABLE",
        "opt_in_enabled": opt_in,
        "forced_disabled": forced_disabled,
        "checkpoint_path": str(checkpoint),
        "checkpoint_sha256": _sha256(checkpoint),
        "checkpoint_ready": checkpoint_ready,
        "checkpoint_validated": checkpoint_validated,
        "activation_enabled": activation_enabled,
        "dataset_card_ready": dataset_card_ready,
        "model_card_ready": model_card_ready,
        "validation_ready": validation_ready,
        "ood_gate_ready": ood_gate_ready,
        "solver_fallback_ready": solver_fallback_ready,
        "hard_gate_bypass_prevented": hard_gate_bypass_prevented,
        "dataset_card_path": str(dataset_card_path) if dataset_card_path.name else "",
        "model_card_path": str(model_card_path) if model_card_path.name else "",
        "validation_receipt_path": str(validation_path) if validation_path.name else "",
        "ood_gate_path": str(ood_path) if ood_path.name else "",
        "solver_fallback_receipt_path": str(fallback_path) if fallback_path.name else "",
        "validation_summary": validation.get("split_metrics") or {},
        "uncertainty_contract": validation.get("uncertainty_contract") or {},
        "production_ml_wired": wired,
        "status": status,
        "claim": (
            "Validated ML surrogate is wired only as shadow_with_solver_fallback; "
            "it cannot promote final structural decisions without solver/code/human gates."
        ),
    }


def try_apply_ml_surrogate_cost_adjustment(*, base_cost: float) -> tuple[float, dict[str, Any]]:
    gate = probe_ml_surrogate_production_gate()
    if not gate.get("production_ml_wired"):
        return float(base_cost), {"applied": False, "gate": gate}
    return float(base_cost), {
        "applied": False,
        "gate": gate,
        "shadow_inference_available": True,
        "note": "Validated shadow surrogate is available, but scalar cost adjustment requires feature-vector inference and solver replay.",
    }
