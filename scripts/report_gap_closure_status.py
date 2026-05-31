#!/usr/bin/env python3
"""Summarize gap-doc closure artifacts into a single status JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_gap_closure_status() -> dict[str, Any]:
    bundle = _load(PRODUCTIZATION / "delivery_evidence_bundle.json")
    gpu = _load(PRODUCTIZATION / "gpu_solver_claim_receipt.json")
    gpu_newton = _load(PRODUCTIZATION / "gpu_newton_certification_checklist.json")
    crossval = _load(PRODUCTIZATION / "commercial_solver_cross_validation.json")
    rh = _load(PRODUCTIZATION / "residual_holdout_closure_updates.json")
    changes = _load(PRODUCTIZATION / "design_optimization_cost_reduction_changes.json")
    alignment = changes.get("member_alignment") if isinstance(changes.get("member_alignment"), dict) else {}

    rh_updates = rh.get("updates") if isinstance(rh.get("updates"), dict) else {}
    supplementary_attached = sum(
        1
        for row in rh_updates.values()
        if isinstance(row, dict) and str(row.get("supplementary_evidence_path") or "").strip()
    )
    rh_still_open = sum(
        1 for row in rh_updates.values() if isinstance(row, dict) and str(row.get("status") or "") == "open"
    )

    sections = {
        "drawing_comparison_p1_p3": {"status": "complete", "note": "See gap doc section 1.3"},
        "member_alignment_1_4": {
            "status": "complete" if alignment.get("schema_version") else "missing",
            "alignment_status": alignment.get("alignment_status"),
        },
        "engine_e_p1_story_reanalysis": {
            "status": bundle.get("summary", {}).get("story_reanalysis_status", "missing"),
            "reanalysis_status": bundle.get("summary", {}).get("reanalysis_status"),
        },
        "engine_e_p2_commercial_crossval": {
            "status": crossval.get("status") or bundle.get("summary", {}).get("cross_validation_status", "missing"),
            "marginal_accepted": crossval.get("metric_marginal_accepted"),
            "hard_failures": crossval.get("metric_failures_hard"),
        },
        "optimization_a_p2_proxy_gate": {
            "status": "warn" if int(bundle.get("summary", {}).get("proxy_divergence_count") or 0) > 0 else "pass",
            "divergence_count": bundle.get("summary", {}).get("proxy_divergence_count"),
        },
        "eb_rh_e_p3": {
            "status": "partial",
            "supplementary_attached": supplementary_attached,
            "rh_still_open": rh_still_open,
        },
        "native_mgt_solve": {
            "status": _load(PRODUCTIZATION / "mgt_native_reanalysis_pipeline.json").get("status", "missing"),
            "integrity": (_load(PRODUCTIZATION / "mgt_native_reanalysis_pipeline.json").get("mgt_integrity") or {}).get(
                "integrity_status"
            ),
            "native_solve_status": (
                (_load(PRODUCTIZATION / "mgt_native_reanalysis_pipeline.json").get("native_fea") or {}).get(
                    "native_solve_status"
                )
                or _load(PRODUCTIZATION / "mgt_global_fea_condensed_solve.json").get("native_solve_status")
            ),
            "native_fea": (_load(PRODUCTIZATION / "mgt_native_reanalysis_pipeline.json").get("native_fea") or {}).get(
                "status"
            ),
            "global_fea_readiness": _load(PRODUCTIZATION / "mgt_global_fea_readiness_gate.json").get("status"),
            "mesh_contract": _load(PRODUCTIZATION / "mgt_global_fea_mesh_contract_gate.json").get("status"),
            "roundtrip_sync": bundle.get("summary", {}).get("mgt_roundtrip_sync_status"),
            "roundtrip_parsed": bool(bundle.get("summary", {}).get("mgt_roundtrip_parsed")),
        },
        "rh_closure_checklist": {
            "status": _load(PRODUCTIZATION / "rh_closure_checklist.json").get("status"),
            "open_count": _load(PRODUCTIZATION / "rh_closure_checklist.json").get("open_count"),
        },
        "gpu_newton_terminal": {
            "status": "not_proven" if not gpu.get("gpu_newton_terminal_proven") else "proven",
            "claim_label": gpu.get("claim_label"),
            "gpu_assist_observed": gpu.get("gpu_assist_observed"),
            "gpu_mainloop_residency_observed": gpu.get("gpu_mainloop_residency_observed"),
            "certification_status": gpu_newton.get("status"),
            "certification_blockers": gpu_newton.get("certification_blockers"),
            "backends": gpu.get("backends"),
        },
        "rh_signed_closure_template": {
            "status": _load(PRODUCTIZATION / "rh_signed_closure_packet_template.json").get("status"),
            "open_count": _load(PRODUCTIZATION / "rh_signed_closure_packet_template.json").get("open_count"),
        },
        "rh_signed_closure": {
            "status": _load(PRODUCTIZATION / "residual_holdout_closure_updates.json").get("rh_closure_status"),
            "actual_closure_evidence_attached": _load(PRODUCTIZATION / "residual_holdout_closure_updates.json").get(
                "actual_closure_evidence_attached"
            ),
        },
        "ml_multi_objective_a_p3": {
            "status": (_load(PRODUCTIZATION / "ml_multi_objective_status.json").get("status") or "not_started"),
            "production_ml_wired": _load(PRODUCTIZATION / "ml_multi_objective_status.json").get(
                "production_ml_wired"
            ),
            "research_pareto_archive_ready": _load(PRODUCTIZATION / "ml_multi_objective_status.json").get(
                "research_pareto_archive_ready"
            ),
            "research_pareto_front_count": _load(PRODUCTIZATION / "ml_multi_objective_status.json").get(
                "research_pareto_front_count"
            ),
        },
    }

    blockers = list(bundle.get("blockers") or [])
    delivery_status = str(bundle.get("status") or "missing")
    if blockers:
        delivery_status = "review_required"
    authority_holdout_status = "open" if rh_still_open else "closed"

    return {
        "schema_version": "gap-closure-status.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": delivery_status,
        "delivery_status": delivery_status,
        "authority_holdout_status": authority_holdout_status,
        "bundle_status": bundle.get("status"),
        "blockers": blockers,
        "pending_authority_closure": rh_still_open > 0,
        "sections": sections,
        "artifacts": {
            "delivery_evidence_bundle": str(PRODUCTIZATION / "delivery_evidence_bundle.json"),
            "residual_holdout_closure_updates": str(PRODUCTIZATION / "residual_holdout_closure_updates.json"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "gap_closure_status.json",
    )
    args = parser.parse_args()
    payload = build_gap_closure_status()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"gap-status: delivery={payload['delivery_status']} "
        f"authority_holdout={payload['authority_holdout_status']} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
