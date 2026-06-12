#!/usr/bin/env python3
"""Build AI-assist decision trace and review queue artifacts from optimization evidence."""

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


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_ai_decision_review_artifacts(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    changes_payload = _load(productization_dir / "design_optimization_cost_reduction_changes.json")
    blocked_payload = _load(productization_dir / "design_optimization_cost_reduction_blocked_actions.json")
    reanalysis = _load(productization_dir / "post_optimization_reanalysis_gate.json")
    proxy_gate = _load(productization_dir / "proxy_solver_divergence_gate.json")
    pareto = _load(productization_dir / "optimization_pareto_research_archive.json")
    safety = _load(productization_dir / "ai_safety_governance_contract.json")
    decision_contract = _load(productization_dir / "ai_decision_trace_contract.json")
    review_contract = _load(productization_dir / "ai_review_queue_contract.json")

    changes = [row for row in (changes_payload.get("changes") or []) if isinstance(row, dict)]
    blocked_rows = [row for row in (blocked_payload.get("blocked_rows") or []) if isinstance(row, dict)]
    blocked_by_group: dict[str, list[dict[str, Any]]] = {}
    for row in blocked_rows:
        blocked_by_group.setdefault(str(row.get("group_id") or ""), []).append(row)

    solver_replay_artifact = str(productization_dir / "post_optimization_reanalysis_gate.json")
    proxy_replay_artifact = str(productization_dir / "proxy_solver_divergence_gate.json")
    code_check_artifact = str(productization_dir / "design_optimization_cost_reduction_changes.json")
    proposal_traces: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    for index, row in enumerate(changes):
        group_id = str(row.get("group_id") or f"group:{index}")
        action_name = str(row.get("action_name") or "unknown_action")
        proposal_id = f"AI-PROP-{index + 1:04d}"
        before_state = {
            "group_id": group_id,
            "section": row.get("before_section"),
            "rebar_ratio": row.get("before_rebar_ratio"),
            "thickness_scale": row.get("before_thickness_scale"),
            "cost_proxy": row.get("cost_proxy_before"),
            "max_dcr": row.get("max_dcr_before"),
            "drift_pct": row.get("drift_before_pct"),
            "residual_pct": row.get("residual_before_pct"),
        }
        after_state = {
            "group_id": group_id,
            "section": row.get("after_section"),
            "rebar_ratio": row.get("after_rebar_ratio"),
            "thickness_scale": row.get("after_thickness_scale"),
            "cost_proxy": row.get("cost_proxy_after"),
            "max_dcr": row.get("max_dcr_after"),
            "drift_pct": row.get("drift_after_pct"),
            "residual_pct": row.get("residual_after_pct"),
        }
        reward_components = {
            "cost_proxy_delta": _finite(row.get("cost_proxy_delta")),
            "max_dcr_after": _finite(row.get("max_dcr_after")),
            "governing_dcr_after": _finite(row.get("governing_member_governing_dcr_after")),
            "drift_after_pct": _finite(row.get("drift_after_pct")),
            "residual_after_pct": _finite(row.get("residual_after_pct")),
            "constructability_delta": _finite(row.get("constructability_delta")),
            "detailing_complexity_delta": _finite(row.get("after_detailing_complexity"))
            - _finite(row.get("before_detailing_complexity")),
        }
        constraint_vector = {
            "selection_gate": row.get("selection_gate"),
            "governing_clause": row.get("governing_clause"),
            "max_governing_dcr_limit": (reanalysis.get("thresholds") or {}).get("max_governing_dcr"),
            "proxy_divergence_count": proxy_gate.get("divergence_count"),
            "story_reanalysis_status": (reanalysis.get("story_model_reanalysis") or {}).get("status"),
            "post_reanalysis_status": reanalysis.get("status"),
        }
        rejected_alternatives = [
            {
                "action_name": alt.get("action_name"),
                "block_reason": alt.get("block_reason"),
                "detail": alt.get("detail"),
            }
            for alt in blocked_by_group.get(group_id, [])
            if alt.get("action_name") != action_name
        ][:5]
        trace = {
            "proposal_id": proposal_id,
            "input_hash": _hash_payload({"group_id": group_id, "action_name": action_name, "source": row}),
            "model_or_policy_version": "deterministic-greedy-optimization-policy.v1",
            "action_id": f"{group_id}:{action_name}",
            "state_hash": _hash_payload({"before": before_state, "after": after_state}),
            "before_state_hash": _hash_payload(before_state),
            "after_state_hash": _hash_payload(after_state),
            "reward_components": reward_components,
            "constraint_vector": constraint_vector,
            "solver_replay_artifact": solver_replay_artifact,
            "proxy_replay_artifact": proxy_replay_artifact,
            "code_check_artifact": code_check_artifact,
            "rejected_alternative_ids": [f"{group_id}:{alt['action_name']}" for alt in rejected_alternatives],
            "rejected_alternatives": rejected_alternatives,
            "sensitivity": {
                "cost_delta_per_dcr_delta": (
                    reward_components["cost_proxy_delta"] / _finite(row.get("max_dcr_delta"), 1.0)
                    if abs(_finite(row.get("max_dcr_delta"))) > 1e-12
                    else None
                ),
                "drift_delta_pct": _finite(row.get("drift_after_pct")) - _finite(row.get("drift_before_pct")),
                "residual_delta_pct": _finite(row.get("residual_after_pct")) - _finite(row.get("residual_before_pct")),
            },
            "human_decision": {
                "state": "engineer_review_required",
                "reviewer": "",
                "decision_at": "",
                "note": "Automatic proposal cannot be final-report promoted before engineer review.",
            },
        }
        proposal_traces.append(trace)
        review_items.append(
            {
                "proposal_id": proposal_id,
                "queue_state": "pending_review",
                "member_or_group_id": group_id,
                "before_state_hash": trace["before_state_hash"],
                "after_state_hash": trace["after_state_hash"],
                "governing_constraint": row.get("governing_clause") or row.get("selection_gate") or "unknown",
                "confidence": "bounded_deterministic_replay",
                "unsupported_caveat": "not a licensed structural approval; engineer review required",
                "evidence_links": [
                    solver_replay_artifact,
                    proxy_replay_artifact,
                    code_check_artifact,
                ],
                "reviewer_decision": "pending",
            }
        )

    minimum_trace_fields = set(decision_contract.get("minimum_fields") or [])
    required_review_fields = set(review_contract.get("minimum_fields") or [])
    trace_complete = bool(proposal_traces) and all(
        minimum_trace_fields <= set(trace.keys()) for trace in proposal_traces
    )
    review_complete = bool(review_items) and all(required_review_fields <= set(item.keys()) for item in review_items)
    solver_replay_ready = reanalysis.get("status") in {"pass", "pass_with_story_proxy_check"}
    proxy_replay_ready = proxy_gate.get("status") == "pass"
    final_promotion_requirements = safety.get("final_report_promotion_requires") or []

    trace_payload = {
        "schema_version": "ai-decision-trace-ledger.v1",
        "generated_at": generated_at,
        "status": "ready" if trace_complete and solver_replay_ready and proxy_replay_ready else "partial",
        "proposal_count": len(proposal_traces),
        "source_change_count": len(changes),
        "trace_complete": trace_complete,
        "solver_replay_ready": solver_replay_ready,
        "proxy_replay_ready": proxy_replay_ready,
        "final_report_promotion_requires": final_promotion_requirements,
        "pareto_context": {
            "research_pareto_archive_ready": pareto.get("status") == "research_archive_ready",
            "pareto_front_count": pareto.get("pareto_front_count"),
            "production_pareto_wired": pareto.get("production_pareto_wired"),
        },
        "proposal_traces": proposal_traces,
        "blockers": [] if trace_complete and solver_replay_ready and proxy_replay_ready else ["ai_decision_trace_incomplete"],
    }
    review_payload = {
        "schema_version": "ai-review-queue.v1",
        "generated_at": generated_at,
        "status": "ready" if review_complete else "partial",
        "queue_item_count": len(review_items),
        "review_complete": review_complete,
        "grounded_answer_contract": {
            "required_fields": ["evidence_links", "confidence", "unsupported_caveat", "next_review_action"],
            "templates": [
                {
                    "question": "Which proposed optimization changes need engineer review first?",
                    "answer_grounding": "sort by governing DCR, unsupported caveat, and replay artifact status",
                    "next_review_action": "open pending_review proposal and inspect solver/code evidence links",
                },
                {
                    "question": "Why was this member or group changed?",
                    "answer_grounding": "proposal trace reward_components, constraint_vector, rejected_alternatives",
                    "next_review_action": "accept, reject, waive, or request rerun",
                },
            ],
        },
        "queue_items": review_items,
        "blockers": [] if review_complete else ["ai_review_queue_incomplete"],
    }
    index = {
        "schema_version": "ai-decision-review-artifacts.v1",
        "generated_at": generated_at,
        "status": "ready" if trace_payload["status"] == "ready" and review_payload["status"] == "ready" else "partial",
        "decision_trace_ready": trace_payload["status"] == "ready",
        "review_queue_ready": review_payload["status"] == "ready",
        "policy_replay_contract_ready": bool(trace_complete and review_complete and solver_replay_ready and proxy_replay_ready),
        "artifacts": {
            "ai_decision_trace_ledger": str(productization_dir / "ai_decision_trace_ledger.json"),
            "ai_review_queue": str(productization_dir / "ai_review_queue.json"),
        },
        "summary": {
            "proposal_count": len(proposal_traces),
            "review_queue_item_count": len(review_items),
            "blocked_action_count": len(blocked_rows),
            "solver_replay_status": reanalysis.get("status"),
            "proxy_replay_status": proxy_gate.get("status"),
        },
    }
    productization_dir.mkdir(parents=True, exist_ok=True)
    (productization_dir / "ai_decision_trace_ledger.json").write_text(
        json.dumps(trace_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (productization_dir / "ai_review_queue.json").write_text(
        json.dumps(review_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    index_out = output_json or (productization_dir / "ai_decision_review_artifacts.json")
    index_out.parent.mkdir(parents=True, exist_ok=True)
    index_out.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_ai_decision_review_artifacts(
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "ai_decision_review_artifacts.json")
    print(
        "ai-decision-review: "
        f"status={payload['status']} trace={payload['decision_trace_ready']} "
        f"queue={payload['review_queue_ready']} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
