#!/usr/bin/env python3
"""Build production optimization audit evidence from solver/code/cost traces."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


def build_optimization_productization_audit(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    changes = _load(productization_dir / "design_optimization_cost_reduction_changes.json")
    proxy = _load(productization_dir / "proxy_solver_divergence_gate.json")
    reanalysis = _load(productization_dir / "post_optimization_reanalysis_gate.json")
    trace = _load(productization_dir / "ai_decision_trace_ledger.json")
    review_queue = _load(productization_dir / "ai_review_queue.json")
    code_guard = _load(productization_dir / "ai_code_reasoning_guard.json")
    safety = _load(productization_dir / "ai_safety_governance_contract.json")
    pareto = _load(productization_dir / "optimization_pareto_research_archive.json")
    ml = _load(productization_dir / "ml_multi_objective_status.json")
    cost_changes = [row for row in (changes.get("changes") or []) if isinstance(row, dict)]

    change_count = len(cost_changes)
    proposal_count = int(trace.get("proposal_count") or 0)
    review_count = int(review_queue.get("queue_item_count") or 0)
    accepted_rows_have_cost = all("cost_proxy_before" in row and "cost_proxy_after" in row for row in cost_changes)
    accepted_rows_have_explicit_clause = all(str(row.get("governing_clause") or "").strip() for row in cost_changes)
    all_rows_have_clause_or_review_guard = bool(code_guard.get("all_rows_have_clause_or_review_guard"))
    accepted_rows_have_code = bool(
        accepted_rows_have_explicit_clause
        or (
            code_guard.get("status") == "ready"
            and int(code_guard.get("change_row_count") or 0) == change_count
            and all_rows_have_clause_or_review_guard
        )
    )
    accepted_rows_have_safety = all("governing_member_governing_dcr_after" in row for row in cost_changes)
    solver_replay_ready = reanalysis.get("status") in {"pass", "pass_with_story_proxy_check"}
    proxy_replay_ready = proxy.get("status") == "pass" and int(proxy.get("divergence_count") or 0) == 0
    decision_trace_ready = trace.get("status") == "ready" and proposal_count == change_count
    review_queue_ready = review_queue.get("status") == "ready" and review_count == change_count
    pareto_ready = pareto.get("status") == "research_archive_ready" and int(pareto.get("pareto_front_count") or 0) > 0
    ml_gate = ml.get("ml_surrogate_production_gate") if isinstance(ml.get("ml_surrogate_production_gate"), dict) else {}
    ml_bypass_prevented = bool(
        (
            ml.get("production_ml_wired") is False
            and str(ml_gate.get("status") or "") in {"disabled", "disabled_by_env"}
        )
        or (
            ml.get("production_ml_wired") is True
            and bool(ml_gate.get("hard_gate_bypass_prevented"))
            and bool(ml_gate.get("solver_fallback_ready"))
            and bool(ml_gate.get("ood_gate_ready"))
        )
    )
    production_pareto_wired = bool(pareto_ready and decision_trace_ready and review_queue_ready)
    optimization_productization_ready = bool(
        change_count
        and accepted_rows_have_cost
        and accepted_rows_have_code
        and accepted_rows_have_safety
        and solver_replay_ready
        and proxy_replay_ready
        and decision_trace_ready
        and review_queue_ready
        and production_pareto_wired
        and ml_bypass_prevented
    )
    final_report_promotion_requires = [
        str(item) for item in (safety.get("final_report_promotion_requires") or []) if str(item).strip()
    ]
    payload = {
        "schema_version": "optimization-productization-audit.v1",
        "generated_at": generated_at,
        "status": "ready" if optimization_productization_ready else "partial",
        "optimization_productization_ready": optimization_productization_ready,
        "change_count": change_count,
        "accepted_rows_have_cost": accepted_rows_have_cost,
        "accepted_rows_have_explicit_clause": accepted_rows_have_explicit_clause,
        "accepted_rows_have_code": accepted_rows_have_code,
        "missing_governing_clause_count": int(code_guard.get("missing_governing_clause_count") or 0),
        "review_guarded_row_count": int(code_guard.get("review_guarded_row_count") or 0),
        "all_rows_have_clause_or_review_guard": all_rows_have_clause_or_review_guard,
        "accepted_rows_have_safety": accepted_rows_have_safety,
        "solver_replay_ready": solver_replay_ready,
        "proxy_replay_ready": proxy_replay_ready,
        "decision_trace_ready": decision_trace_ready,
        "review_queue_ready": review_queue_ready,
        "production_pareto_wired": production_pareto_wired,
        "ml_bypass_prevented": ml_bypass_prevented,
        "ml_surrogate_gate_status": ml_gate.get("status"),
        "ml_surrogate_checkpoint_validated": ml_gate.get("checkpoint_validated"),
        "final_report_promotion_requires": final_report_promotion_requires,
        "claim": (
            "Production optimization is deterministic/replayable with governed ML disabled; accepted deltas carry "
            "solver, cost, Pareto, review, and either explicit code-clause evidence or an engineer-review code guard."
        ),
        "artifacts": {
            "changes_json": str(productization_dir / "design_optimization_cost_reduction_changes.json"),
            "proxy_solver_divergence": str(productization_dir / "proxy_solver_divergence_gate.json"),
            "post_optimization_reanalysis": str(productization_dir / "post_optimization_reanalysis_gate.json"),
            "ai_decision_trace_ledger": str(productization_dir / "ai_decision_trace_ledger.json"),
            "ai_review_queue": str(productization_dir / "ai_review_queue.json"),
            "ai_code_reasoning_guard": str(productization_dir / "ai_code_reasoning_guard.json"),
            "optimization_pareto_research_archive": str(productization_dir / "optimization_pareto_research_archive.json"),
            "ml_multi_objective_status": str(productization_dir / "ml_multi_objective_status.json"),
        },
        "summary": {
            "cost_proxy_delta_sum": (reanalysis.get("change_summary") or {}).get("cost_proxy_delta_sum"),
            "max_governing_dcr_after": (reanalysis.get("change_summary") or {}).get("max_governing_dcr_after"),
            "pareto_front_count": pareto.get("pareto_front_count"),
            "proposal_count": proposal_count,
            "review_queue_item_count": review_count,
        },
        "blockers": [] if optimization_productization_ready else ["optimization_productization_audit_incomplete"],
    }
    out = output_json or (productization_dir / "optimization_productization_audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_optimization_productization_audit(
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "optimization_productization_audit.json")
    print(
        "optimization-productization-audit: "
        f"status={payload['status']} pareto_wired={payload['production_pareto_wired']} "
        f"ml_bypass_prevented={payload['ml_bypass_prevented']} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
