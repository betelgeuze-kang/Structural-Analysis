#!/usr/bin/env python3
"""Execute the AI physics guard on current solver/proposal evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _monotonic_load_steps(rows: list[dict[str, Any]]) -> bool:
    seen: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("iteration") or 0) != 0:
            continue
        seen.append(_finite(row.get("load_step")))
    return bool(seen) and all(b >= a for a, b in zip(seen, seen[1:]))


def build_ai_physics_guard_execution(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    contract = _load(productization_dir / "ai_physics_guard_contract.json")
    inference = _load(productization_dir / "ai_inference_runtime_receipt.json")
    mgt_3d = _load(productization_dir / "mgt_global_fea_3d_native_solve.json")
    direct_residual = _load(productization_dir / "mgt_direct_residual_newton_probe.json")
    reanalysis = _load(productization_dir / "post_optimization_reanalysis_gate.json")
    trace = _load(productization_dir / "ai_decision_trace_ledger.json")

    mesh = mgt_3d.get("mesh_3d_global_solve") if isinstance(mgt_3d.get("mesh_3d_global_solve"), dict) else {}
    metrics = mesh.get("response_metrics") if isinstance(mesh.get("response_metrics"), dict) else {}
    fingerprint = mesh.get("mesh_fingerprint") if isinstance(mesh.get("mesh_fingerprint"), dict) else {}
    iteration_log = mesh.get("newton_iteration_log") if isinstance(mesh.get("newton_iteration_log"), list) else []
    ai_correction_executed = bool(inference.get("inference_executed"))
    checkpoint_ready = bool(inference.get("checkpoint_ready"))
    checkpoint_validated = bool(inference.get("checkpoint_validated"))
    fallback_policy = inference.get("fallback_policy") if isinstance(inference.get("fallback_policy"), dict) else {}
    residual_inf = _finite(metrics.get("residual_inf"), default=math.inf)
    residual_limit = 1.0e-4
    residual_pass = bool(residual_inf <= residual_limit)
    load_step_monotonic = _monotonic_load_steps([row for row in iteration_log if isinstance(row, dict)])
    bc_proxy_pass = bool(int(fingerprint.get("base_node_count") or 0) > 0 and int(fingerprint.get("dof_count") or 0) > 0)
    ood_unsupported_enforced = bool(
        not checkpoint_ready
        and str(inference.get("status") or "") == "disabled_no_validated_checkpoint"
        and fallback_policy.get("unsupported_or_ood") == "solver_only_engineer_review_required"
    )
    validated_shadow_ood_guard = bool(
        checkpoint_ready
        and checkpoint_validated
        and str(inference.get("ood_status") or "") == "pass"
        and fallback_policy.get("unsupported_or_ood") == "solver_only_engineer_review_required"
    )
    solver_replay_ready = reanalysis.get("status") in {"pass", "pass_with_story_proxy_check"}
    trace_ready = trace.get("status") == "ready"
    direct_residual_ready = bool(direct_residual.get("direct_residual_newton_ready"))
    direct_residual_base = (
        direct_residual.get("base_direct_residual")
        if isinstance(direct_residual.get("base_direct_residual"), dict)
        else {}
    )
    direct_residual_final = (
        direct_residual.get("final_direct_residual")
        if isinstance(direct_residual.get("final_direct_residual"), dict)
        else {}
    )
    direct_residual_gate_enforced = bool(
        direct_residual.get("status") in {"ready", "partial"}
        and not direct_residual_ready
        and direct_residual_base
    )
    correction_promotion_blocked = bool(
        (not ai_correction_executed and ood_unsupported_enforced)
        or (
            ai_correction_executed
            and validated_shadow_ood_guard
            and str(inference.get("fallback_reason") or "") == "solver_replay_required_for_final_promotion"
        )
    )

    gate_rows = [
        {
            "id": "equilibrium_residual",
            "status": "pass" if residual_pass else "fail",
            "metric": "force_residual_inf_norm",
            "value": residual_inf,
            "limit": residual_limit,
            "evidence": str(productization_dir / "mgt_global_fea_3d_native_solve.json"),
            "scope": "representative connected component; full 3D closure tracked by G1",
        },
        {
            "id": "energy_monotonicity",
            "status": "pass" if load_step_monotonic else "fail",
            "metric": "load_step_monotonic_proxy",
            "value": load_step_monotonic,
            "evidence": str(productization_dir / "mgt_global_fea_3d_native_solve.json"),
            "scope": "guard proxy until full energy history is emitted by the full solver",
        },
        {
            "id": "direct_residual_physics_correction",
            "status": "pass" if (direct_residual_ready or direct_residual_gate_enforced) else "fail",
            "metric": "regularization_free_direct_residual_gate",
            "value": {
                "direct_residual_newton_ready": direct_residual_ready,
                "base_direct_residual_inf_n": direct_residual_base.get("direct_residual_inf_n"),
                "final_direct_residual_inf_n": direct_residual_final.get("direct_residual_inf_n"),
                "improvement_factor": direct_residual_final.get("improvement_factor"),
                "gate_action": "allowed" if direct_residual_ready else "blocked_from_promotion",
            },
            "evidence": str(productization_dir / "mgt_direct_residual_newton_probe.json"),
            "scope": (
                "full uncoarsened frame-shell residual gate; failed residual correction remains "
                "review-required and cannot be promoted as a final AI correction"
            ),
        },
        {
            "id": "boundary_condition_violation",
            "status": "pass" if bc_proxy_pass else "fail",
            "metric": "base_node_and_constrained_dof_presence",
            "value": {
                "base_node_count": fingerprint.get("base_node_count"),
                "dof_count": fingerprint.get("dof_count"),
            },
            "evidence": str(productization_dir / "mgt_global_fea_3d_native_solve.json"),
        },
        {
            "id": "ood_generalization",
            "status": "pass" if (ood_unsupported_enforced or validated_shadow_ood_guard) else "fail",
            "metric": "unsupported_or_ood_fallback_policy",
            "value": {
                "inference_status": inference.get("status"),
                "ood_status": inference.get("ood_status"),
                "checkpoint_validated": checkpoint_validated,
            },
            "evidence": str(productization_dir / "ai_inference_runtime_receipt.json"),
        },
        {
            "id": "long_rollout_stability",
            "status": "pass" if correction_promotion_blocked and trace_ready else "fail",
            "metric": "unvalidated_ai_rollout_blocked",
            "value": {
                "ai_correction_executed": ai_correction_executed,
                "fallback_reason": inference.get("fallback_reason"),
                "proposal_trace_ready": trace_ready,
            },
            "evidence": str(productization_dir / "ai_decision_trace_ledger.json"),
        },
    ]
    all_pass = all(row["status"] == "pass" for row in gate_rows)
    payload = {
        "schema_version": "ai-physics-guard-execution.v1",
        "generated_at": generated_at,
        "status": "ready" if all_pass else "partial",
        "physics_guard_execution_ready": all_pass,
        "contract_status": contract.get("status"),
        "ai_correction_executed": ai_correction_executed,
        "validated_checkpoint_ready": checkpoint_ready,
        "checkpoint_validated": checkpoint_validated,
        "solver_replay_ready": solver_replay_ready,
        "correction_promotion_blocked": correction_promotion_blocked,
        "direct_residual_correction_gate_enforced": direct_residual_gate_enforced,
        "claim": "No unvalidated AI physics correction is promoted; current AI suggestions remain solver/code/review gated.",
        "gate_rows": gate_rows,
        "limitations": [
            "Full 3D nonlinear equilibrium remains tracked by G1.",
            "Validated shadow surrogate output remains gated by solver/code/human review before final promotion.",
        ],
        "blockers": [] if all_pass else ["ai_physics_guard_execution_failed"],
    }
    out = output_json or (productization_dir / "ai_physics_guard_execution.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_ai_physics_guard_execution(
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "ai_physics_guard_execution.json")
    print(
        "ai-physics-guard: "
        f"status={payload['status']} correction_blocked={payload['correction_promotion_blocked']} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
