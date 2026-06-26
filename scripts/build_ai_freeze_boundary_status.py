#!/usr/bin/env python3
"""Build a conservative AI freeze and shadow-only claim-boundary status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "ai_freeze_boundary_status.json"
DEVELOPER_PREVIEW_READINESS = PRODUCTIZATION / "developer_preview_readiness.json"
ML_MULTI_OBJECTIVE_STATUS = PRODUCTIZATION / "ml_multi_objective_status.json"
ML_SURROGATE_CHECKPOINT_MANIFEST = PRODUCTIZATION / "ml_surrogate_checkpoint_manifest.json"
AI_ENGINE_PRODUCTIZATION_CONTRACTS = PRODUCTIZATION / "ai_engine_productization_contracts.json"
AI_PHYSICS_GUARD_EXECUTION = PRODUCTIZATION / "ai_physics_guard_execution.json"
AI_CODE_REASONING_GUARD = PRODUCTIZATION / "ai_code_reasoning_guard.json"
AI_DECISION_TRACE_LEDGER = PRODUCTIZATION / "ai_decision_trace_ledger.json"
AI_REVIEW_QUEUE_CONTRACT = PRODUCTIZATION / "ai_review_queue_contract.json"
SCHEMA_VERSION = "ai-freeze-boundary-status.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _status_ready(payload: dict[str, Any], statuses: set[str] | None = None) -> bool:
    status = str(payload.get("status", "")).lower()
    return bool(payload.get("contract_pass") is True or status in (statuses or {"ready", "pass"}))


def build_ai_freeze_boundary_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    preview = _load_json(repo_root, DEVELOPER_PREVIEW_READINESS)
    ml_status = _load_json(repo_root, ML_MULTI_OBJECTIVE_STATUS)
    ml_manifest = _load_json(repo_root, ML_SURROGATE_CHECKPOINT_MANIFEST)
    ai_contracts = _load_json(repo_root, AI_ENGINE_PRODUCTIZATION_CONTRACTS)
    physics_guard = _load_json(repo_root, AI_PHYSICS_GUARD_EXECUTION)
    code_guard = _load_json(repo_root, AI_CODE_REASONING_GUARD)
    decision_trace = _load_json(repo_root, AI_DECISION_TRACE_LEDGER)
    review_queue = _load_json(repo_root, AI_REVIEW_QUEUE_CONTRACT)

    scope = _as_dict(preview.get("scope"))
    freeze_policy = _as_dict(scope.get("freeze_policy"))
    ml_gate = _as_dict(ml_status.get("ml_surrogate_production_gate"))
    preview_claim_boundary = str(preview.get("claim_boundary", ""))
    ml_claim = str(ml_status.get("claim") or ml_gate.get("claim") or "")
    code_claim_boundary = str(code_guard.get("claim_boundary", ""))

    ai_training_frozen = (
        freeze_policy.get("ai_training")
        == "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed"
    )
    surrogate_truth_claim_frozen = "AI/GNN/surrogate truth claims stay frozen" in preview_claim_boundary
    shadow_solver_gated_only = bool(
        ml_status.get("production_ml_wired") is True
        and ml_status.get("multi_objective_pareto_wired") is False
        and ml_gate.get("hard_gate_bypass_prevented") is True
        and "shadow_with_solver_fallback" in ml_claim
    )
    autonomous_ai_engine_claim = False
    autonomous_legal_or_design_approval_claim = False
    production_pareto_policy_claim = bool(ml_status.get("multi_objective_pareto_wired") is True)
    ai_contract_boundary_ready = bool(
        ai_contracts.get("contracts_ready") is True
        and ai_contracts.get("production_ai_ready") is True
        and _as_dict(ai_contracts.get("summary")).get("physics_guard_status") == "contract_ready_model_not_promoted"
    )
    physics_guard_ready = _status_ready(physics_guard)
    code_guard_ready = bool(
        _status_ready(code_guard)
        and "no autonomous legal approval" in code_claim_boundary
    )
    decision_trace_ready = _status_ready(decision_trace)
    review_queue_ready = str(review_queue.get("status", "")).lower() in {"contract_ready", "ready", "pass"}
    checkpoint_shadow_ready = bool(
        ml_manifest.get("status") == "ready"
        and ml_manifest.get("validation_pass") is True
        and ml_manifest.get("ood_pass") is True
        and ml_manifest.get("solver_fallback_verified") is True
    )

    checks = {
        "ai_training_frozen": ai_training_frozen,
        "surrogate_truth_claim_frozen": surrogate_truth_claim_frozen,
        "shadow_solver_gated_only": shadow_solver_gated_only,
        "autonomous_ai_engine_claim_absent": autonomous_ai_engine_claim is False,
        "autonomous_legal_or_design_approval_claim_absent": autonomous_legal_or_design_approval_claim is False,
        "production_pareto_policy_claim_absent": production_pareto_policy_claim is False,
        "ai_contract_boundary_ready": ai_contract_boundary_ready,
        "physics_guard_ready": physics_guard_ready,
        "code_guard_ready": code_guard_ready,
        "decision_trace_ready": decision_trace_ready,
        "review_queue_ready": review_queue_ready,
        "checkpoint_shadow_ready": checkpoint_shadow_ready,
    }
    blockers = [f"{key}_not_ready" for key, value in checks.items() if value is not True]
    contract_pass = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                DEVELOPER_PREVIEW_READINESS,
                ML_MULTI_OBJECTIVE_STATUS,
                ML_SURROGATE_CHECKPOINT_MANIFEST,
                AI_ENGINE_PRODUCTIZATION_CONTRACTS,
                AI_PHYSICS_GUARD_EXECUTION,
                AI_CODE_REASONING_GUARD,
                AI_DECISION_TRACE_LEDGER,
                AI_REVIEW_QUEUE_CONTRACT,
                Path("scripts/build_ai_freeze_boundary_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="ai_freeze_boundary_status_aggregates_existing_ai_guard_and_shadow_ml_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "boundary_claim_ready": contract_pass,
        "autonomous_ai_engine_claim": autonomous_ai_engine_claim,
        "autonomous_legal_or_design_approval_claim": autonomous_legal_or_design_approval_claim,
        "surrogate_truth_claim_frozen": surrogate_truth_claim_frozen,
        "ai_training_frozen": ai_training_frozen,
        "shadow_solver_gated_only": shadow_solver_gated_only,
        "production_pareto_policy_claim": production_pareto_policy_claim,
        "developer_preview_freeze_policy": freeze_policy,
        "ml_shadow_gate": {
            "status": str(ml_status.get("status", "missing")),
            "production_ml_wired": bool(ml_status.get("production_ml_wired") is True),
            "multi_objective_pareto_wired": bool(ml_status.get("multi_objective_pareto_wired") is True),
            "hard_gate_bypass_prevented": bool(ml_gate.get("hard_gate_bypass_prevented") is True),
            "checkpoint_validated": bool(ml_gate.get("checkpoint_validated") is True),
            "solver_fallback_ready": bool(ml_gate.get("solver_fallback_ready") is True),
            "claim": ml_claim,
        },
        "guard_gates": {
            "ai_contract_boundary_ready": ai_contract_boundary_ready,
            "physics_guard_ready": physics_guard_ready,
            "code_guard_ready": code_guard_ready,
            "decision_trace_ready": decision_trace_ready,
            "review_queue_ready": review_queue_ready,
            "checkpoint_shadow_ready": checkpoint_shadow_ready,
        },
        "checks": checks,
        "blockers": blockers,
        "readiness_inputs": {
            "developer_preview_readiness": DEVELOPER_PREVIEW_READINESS.as_posix(),
            "ml_multi_objective_status": ML_MULTI_OBJECTIVE_STATUS.as_posix(),
            "ml_surrogate_checkpoint_manifest": ML_SURROGATE_CHECKPOINT_MANIFEST.as_posix(),
            "ai_engine_productization_contracts": AI_ENGINE_PRODUCTIZATION_CONTRACTS.as_posix(),
            "ai_physics_guard_execution": AI_PHYSICS_GUARD_EXECUTION.as_posix(),
            "ai_code_reasoning_guard": AI_CODE_REASONING_GUARD.as_posix(),
            "ai_decision_trace_ledger": AI_DECISION_TRACE_LEDGER.as_posix(),
            "ai_review_queue_contract": AI_REVIEW_QUEUE_CONTRACT.as_posix(),
        },
        "summary_line": (
            "AI freeze boundary: "
            f"{'READY' if contract_pass else 'BLOCKED'} | shadow_solver_gated="
            f"{shadow_solver_gated_only} | autonomous_claim={autonomous_ai_engine_claim}"
        ),
        "claim_boundary": (
            "This receipt proves only the AI claim boundary and guard/freeze posture. "
            "It does not prove autonomous structural-design AI, AI solver truth, legal "
            "approval automation, production Pareto/RL policy, or commercial release. "
            "Validated ML remains shadow_with_solver_fallback and final promotion still "
            "requires deterministic solver, code-check, and human-review gates."
        ),
    }


def write_ai_freeze_boundary_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_ai_freeze_boundary_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_ai_freeze_boundary_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_ai_freeze_boundary_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"ai_freeze_boundary_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"ai_freeze_boundary_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "ai_freeze_boundary_status_mismatch"
    return True, "ai_freeze_boundary_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_ai_freeze_boundary_status(out_path=args.out)
        print(f"AI freeze boundary status check: {message}")
        return 0 if ok else 1
    payload = write_ai_freeze_boundary_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
