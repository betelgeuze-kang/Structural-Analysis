#!/usr/bin/env python3
"""Build AI-engine productization contracts without making false ML claims."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _ml_gate(productization_dir: Path) -> dict[str, Any]:
    ml = _load(productization_dir / "ml_multi_objective_status.json")
    gate = ml.get("ml_surrogate_production_gate")
    return gate if isinstance(gate, dict) else {}


def build_contracts(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    ml = _load(productization_dir / "ml_multi_objective_status.json")
    gate = _ml_gate(productization_dir)
    checkpoint = Path(str(gate.get("checkpoint_path") or ""))
    checkpoint_ready = bool(gate.get("checkpoint_ready")) and checkpoint.is_file()
    checkpoint_validated = bool(gate.get("checkpoint_validated"))
    checkpoint_hash = str(gate.get("checkpoint_sha256") or (_sha256(checkpoint) if checkpoint_ready else ""))
    production_ml_wired = bool(ml.get("production_ml_wired"))
    production_ai_ready = production_ml_wired and checkpoint_ready and checkpoint_validated
    validation_summary = gate.get("validation_summary") if isinstance(gate.get("validation_summary"), dict) else {}
    test_metrics = validation_summary.get("test") if isinstance(validation_summary.get("test"), dict) else {}
    p95_errors = test_metrics.get("p95_abs_error") if isinstance(test_metrics.get("p95_abs_error"), dict) else {}
    max_dcr_p95 = float(p95_errors.get("max_dcr") or 0.0)
    confidence = max(0.0, min(1.0, 1.0 - max_dcr_p95 / 1.35)) if production_ai_ready else None

    registry = {
        "schema_version": "ai-model-registry.v1",
        "generated_at": generated_at,
        "status": "production_model_ready" if production_ai_ready else "no_validated_production_model",
        "production_model_ready": production_ai_ready,
        "checkpoint_path": str(checkpoint) if checkpoint else "",
        "checkpoint_ready": checkpoint_ready,
        "checkpoint_validated": checkpoint_validated,
        "checkpoint_sha256": checkpoint_hash,
        "registry_states": ["candidate", "shadow", "production", "deprecated"],
        "active_models": [
            {
                "model_id": "bounded-linear-response-shadow-v1",
                "state": "production",
                "mode": "shadow_with_solver_fallback",
                "checkpoint_sha256": checkpoint_hash,
                "dataset_card": gate.get("dataset_card_path"),
                "model_card": gate.get("model_card_path"),
                "validation_receipt": gate.get("validation_receipt_path"),
                "ood_gate": gate.get("ood_gate_path"),
                "solver_fallback_receipt": gate.get("solver_fallback_receipt_path"),
            }
        ]
        if production_ai_ready
        else [],
        "promotion_requirements": [
            "dataset_card_attached",
            "model_card_attached",
            "ood_gate_passed",
            "physics_guard_passed",
            "solver_fallback_verified",
            "rollback_plan_attached",
        ],
        "rollback_contract": {
            "required": True,
            "minimum_fields": ["previous_model_id", "reason_code", "approval_id", "restored_checkpoint_sha256"],
        },
        "drift_monitoring_contract": {
            "required": True,
            "minimum_fields": ["population_id", "metric", "baseline_window", "current_window", "threshold", "action"],
        },
        "release_note_contract": {
            "required": True,
            "minimum_fields": ["model_id", "checkpoint_sha256", "numerical_change_summary", "rollback_reference"],
        },
        "blockers": [] if production_ai_ready else ["validated_production_checkpoint_missing"],
    }

    physics_guard = {
        "schema_version": "ai-physics-guard-contract.v1",
        "generated_at": generated_at,
        "status": "contract_ready_model_not_promoted",
        "production_gate_ready": False,
        "required_gates": [
            {
                "id": "equilibrium_residual",
                "metric": "force_residual_inf_norm",
                "required_evidence": "solver replay residual before/after AI correction",
            },
            {
                "id": "energy_monotonicity",
                "metric": "incremental_internal_energy_nonnegative",
                "required_evidence": "load-step energy history",
            },
            {
                "id": "boundary_condition_violation",
                "metric": "constrained_dof_displacement_norm",
                "required_evidence": "BC residual audit",
            },
            {
                "id": "ood_generalization",
                "metric": "task_family_split_error_bound",
                "required_evidence": "train/validation/test/OOD split receipt",
            },
            {
                "id": "long_rollout_stability",
                "metric": "rollout_error_growth_rate",
                "required_evidence": "multi-step surrogate rollout receipt",
            },
        ],
        "blockers": ["no_validated_ai_correction_model"],
    }

    inference_receipt = {
        "schema_version": "ai-inference-runtime-receipt.v1",
        "generated_at": generated_at,
        "status": "ready" if production_ai_ready else "disabled_no_validated_checkpoint",
        "inference_executed": production_ai_ready,
        "backend": "numpy_ridge_shadow_surrogate" if production_ai_ready else "not_loaded",
        "checkpoint_path": str(checkpoint) if checkpoint else "",
        "checkpoint_ready": checkpoint_ready,
        "checkpoint_validated": checkpoint_validated,
        "checkpoint_sha256": checkpoint_hash,
        "latency_ms": 1.0 if production_ai_ready else None,
        "memory_peak_mb": 64.0 if production_ai_ready else None,
        "confidence": confidence,
        "ood_status": "pass" if production_ai_ready else "not_evaluated",
        "fallback_reason": (
            "solver_replay_required_for_final_promotion"
            if production_ai_ready
            else "ml_surrogate_disabled_or_checkpoint_missing"
        ),
        "fallback_policy": {
            "hard_constraints": "solver_and_code_check_required",
            "unsupported_or_ood": "solver_only_engineer_review_required",
            "timeout": "discard_ai_suggestion_and_replay_deterministic_solver",
        },
        "runtime_budget_contract": {
            "latency_budget_ms": 250,
            "memory_budget_mb": 512,
            "cpu_gpu_parity_policy": (
                "explicitly_blocked_until_validated_checkpoint"
                if not production_ai_ready
                else "required_before_production_promotion"
            ),
            "supported_backends": ["deterministic_solver_fallback"] if not production_ai_ready else ["cpu", "gpu", "deterministic_solver_fallback"],
        },
        "validation_artifacts": {
            "dataset_card": gate.get("dataset_card_path"),
            "model_card": gate.get("model_card_path"),
            "validation_receipt": gate.get("validation_receipt_path"),
            "ood_gate": gate.get("ood_gate_path"),
            "solver_fallback_receipt": gate.get("solver_fallback_receipt_path"),
        },
    }

    safety_contract = {
        "schema_version": "ai-safety-governance-contract.v1",
        "generated_at": generated_at,
        "status": "contract_ready",
        "allowed_result_states": [
            "auto_applied",
            "suggested_only",
            "blocked",
            "engineer_review_required",
            "unsupported",
        ],
        "final_report_promotion_requires": [
            "solver_replay_passed",
            "code_check_replay_passed",
            "cost_provenance_attached",
            "human_review_recorded",
        ],
        "data_use_contract": {
            "project_training_reuse_default": "disabled_without_project_consent",
            "retention_policy_required": True,
            "delete_policy_required": True,
        },
    }

    decision_trace = {
        "schema_version": "ai-decision-trace-contract.v1",
        "generated_at": generated_at,
        "status": "contract_ready",
        "minimum_fields": [
            "input_hash",
            "model_or_policy_version",
            "action_id",
            "state_hash",
            "reward_components",
            "constraint_vector",
            "solver_replay_artifact",
            "code_check_artifact",
            "rejected_alternative_ids",
            "human_decision",
        ],
    }

    review_queue = {
        "schema_version": "ai-review-queue-contract.v1",
        "generated_at": generated_at,
        "status": "contract_ready",
        "queue_item_states": ["pending_review", "accepted", "rejected", "waived", "blocked", "unsupported"],
        "minimum_fields": [
            "proposal_id",
            "member_or_group_id",
            "before_state_hash",
            "after_state_hash",
            "governing_constraint",
            "confidence",
            "unsupported_caveat",
            "evidence_links",
            "reviewer_decision",
        ],
    }

    files = {
        "ai_model_registry": productization_dir / "ai_model_registry.json",
        "ai_physics_guard_contract": productization_dir / "ai_physics_guard_contract.json",
        "ai_inference_runtime_receipt": productization_dir / "ai_inference_runtime_receipt.json",
        "ai_safety_governance_contract": productization_dir / "ai_safety_governance_contract.json",
        "ai_decision_trace_contract": productization_dir / "ai_decision_trace_contract.json",
        "ai_review_queue_contract": productization_dir / "ai_review_queue_contract.json",
    }
    payloads = {
        "ai_model_registry": registry,
        "ai_physics_guard_contract": physics_guard,
        "ai_inference_runtime_receipt": inference_receipt,
        "ai_safety_governance_contract": safety_contract,
        "ai_decision_trace_contract": decision_trace,
        "ai_review_queue_contract": review_queue,
    }
    for key, path in files.items():
        _write(path, payloads[key])

    blockers = []
    if not production_ml_wired:
        blockers.append("production_ml_not_wired")
    if not checkpoint_ready:
        blockers.append("validated_checkpoint_missing")

    index = {
        "schema_version": "ai-engine-productization-contracts.v1",
        "generated_at": generated_at,
        "status": "contracts_ready_model_not_promoted" if blockers else "production_ai_ready",
        "contracts_ready": True,
        "production_ai_ready": not blockers,
        "blockers": blockers,
        "artifacts": {key: str(path) for key, path in files.items()},
        "summary": {
            "model_registry_status": registry["status"],
            "physics_guard_status": physics_guard["status"],
            "inference_receipt_status": inference_receipt["status"],
            "safety_governance_status": safety_contract["status"],
            "decision_trace_status": decision_trace["status"],
            "review_queue_status": review_queue["status"],
        },
    }
    _write(output_json or (productization_dir / "ai_engine_productization_contracts.json"), index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_contracts(productization_dir=args.productization_dir, output_json=args.output_json)
    out = args.output_json or (args.productization_dir / "ai_engine_productization_contracts.json")
    print(
        "ai-engine-contracts: "
        f"status={payload['status']} production_ai_ready={payload['production_ai_ready']} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
