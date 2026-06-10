#!/usr/bin/env python3
"""Build customer-facing solver governance/support contract evidence."""

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


def build_solver_governance_support_contract(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    bundle = _load(productization_dir / "delivery_evidence_bundle.json")
    validation = _load(productization_dir / "productization_delivery_evidence_validation.json")
    gap = _load(productization_dir / "commercial_gap_ledger_status.json")
    workstation = _load(REPO_ROOT / "implementation/phase1/workstation_delivery_readiness.json")
    ai_review = _load(productization_dir / "ai_review_queue.json")
    ai_trace = _load(productization_dir / "ai_decision_trace_ledger.json")
    load_stage = _load(productization_dir / "load_stage_semantics_contract.json")

    gap_rows = [row for row in (gap.get("rows") or []) if isinstance(row, dict)]
    unsupported_rows = [
        {
            "id": row.get("id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "blockers": row.get("blockers") or [],
        }
        for row in gap_rows
        if row.get("status") != "closed"
    ]
    report_state_separation = {
        "solver_derived": [
            "mgt_global_fea_3d_native_solve.json",
            "mgt_global_fea_condensed_solve.json",
            "story_model_reanalysis.json",
        ],
        "proxy_derived": [
            "proxy_solver_divergence_gate.json",
            "post_optimization_reanalysis_gate.json",
        ],
        "ai_assisted": [
            "ai_decision_trace_ledger.json",
            "ai_review_queue.json",
            "ai_inference_runtime_receipt.json",
        ],
        "unsupported_or_external": [row["id"] for row in unsupported_rows],
    }
    headline_trace_contract = {
        "required_chain": [
            "customer_report_metric",
            "viewer_surface_or_delivery_index_link",
            "evidence_json_path",
            "solver_or_proxy_run_id",
            "input_model_hash",
            "claim_boundary_label",
        ],
        "artifact_examples": {
            "delivery_bundle": str(productization_dir / "delivery_evidence_bundle.json"),
            "gap_ledger": str(productization_dir / "commercial_gap_ledger_status.json"),
            "ai_review_queue": str(productization_dir / "ai_review_queue.json"),
            "load_stage_semantics": str(productization_dir / "load_stage_semantics_contract.json"),
        },
    }
    engineer_review_workflow = {
        "states": ["pending_review", "accepted", "rejected", "waived", "blocked", "unsupported"],
        "required_before_final_report_promotion": [
            "solver_or_proxy_state_visible",
            "unsupported_state_visible",
            "engineer_review_decision",
            "evidence_links_resolve",
        ],
        "ai_queue_item_count": ai_review.get("queue_item_count"),
        "ai_trace_proposal_count": ai_trace.get("proposal_count"),
    }
    support_policy = {
        "release_note_policy_required": True,
        "numerical_change_policy_required": True,
        "audit_export_required": True,
        "retention_delete_policy_required": True,
        "external_state_confirmation_required": True,
    }

    ready = bool(
        bundle.get("status") == "ready"
        and validation.get("status") == "pass"
        and workstation.get("status") == "ready"
        and gap.get("schema_version") == "commercial-gap-ledger-status.v1"
        and ai_review.get("status") == "ready"
        and load_stage.get("status") == "ready"
    )
    payload = {
        "schema_version": "solver-governance-support-contract.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "partial",
        "governance_support_ready": ready,
        "bundle_status": bundle.get("status"),
        "validation_status": validation.get("status"),
        "workstation_delivery_status": workstation.get("status"),
        "full_gap_ledger_ready": bool(gap.get("full_gap_ledger_ready")),
        "full_gap_ledger_status": gap.get("status"),
        "unsupported_state_first_report_policy": True,
        "report_state_separation": report_state_separation,
        "headline_trace_contract": headline_trace_contract,
        "engineer_review_workflow": engineer_review_workflow,
        "support_policy": support_policy,
        "unsupported_rows": unsupported_rows,
        "blockers": [] if ready else ["solver_governance_support_contract_incomplete"],
    }
    out = output_json or (productization_dir / "solver_governance_support_contract.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_solver_governance_support_contract(
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "solver_governance_support_contract.json")
    print(
        "solver-governance-support: "
        f"status={payload['status']} unsupported_visible={len(payload['unsupported_rows'])} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
