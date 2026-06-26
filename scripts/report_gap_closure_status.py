#!/usr/bin/env python3
"""Summarize gap-doc closure artifacts into a single status JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.commercial_gap_ledger_status import (  # noqa: E402
    build_commercial_gap_ledger_status,
)
from scripts.release_evidence_metadata import input_checksums  # noqa: E402


GAP_CLOSURE_INPUT_FILES = (
    "delivery_evidence_bundle.json",
    "gpu_solver_claim_receipt.json",
    "gpu_newton_certification_checklist.json",
    "commercial_solver_cross_validation.json",
    "residual_holdout_closure_updates.json",
    "design_optimization_cost_reduction_changes.json",
    "mgt_native_reanalysis_pipeline.json",
    "mgt_global_fea_condensed_solve.json",
    "mgt_global_fea_readiness_gate.json",
    "mgt_global_fea_mesh_contract_gate.json",
    "rh_closure_checklist.json",
    "rh_signed_closure_packet_template.json",
    "ml_multi_objective_status.json",
    "ai_freeze_boundary_status.json",
    "gap_ledger_evidence_audit.json",
    "commercial_gap_ledger_status.json",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _compact_ledger_requirements(rows: list[Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "ledger": row.get("ledger"),
                "status": row.get("status"),
                "closed": bool(row.get("closed")),
                "locally_closable": bool(row.get("locally_closable")),
                "blockers": list(row.get("blockers") or []),
                "next_gate": row.get("next_gate"),
                "claim_boundary": row.get("claim_boundary"),
            }
        )
    return compact


def build_gap_closure_status(productization_dir: Path | None = None) -> dict[str, Any]:
    productization = Path(productization_dir or PRODUCTIZATION)
    checksum_inputs = [
        *(productization / filename for filename in GAP_CLOSURE_INPUT_FILES),
        Path("docs/commercial-structural-solver-product-gap-ledger.md"),
        Path("docs/structural-analysis-ai-engine-gap-ledger.md"),
    ]
    bundle = _load(productization / "delivery_evidence_bundle.json")
    gpu = _load(productization / "gpu_solver_claim_receipt.json")
    gpu_newton = _load(productization / "gpu_newton_certification_checklist.json")
    crossval = _load(productization / "commercial_solver_cross_validation.json")
    rh = _load(productization / "residual_holdout_closure_updates.json")
    changes = _load(productization / "design_optimization_cost_reduction_changes.json")
    alignment = changes.get("member_alignment") if isinstance(changes.get("member_alignment"), dict) else {}
    ai_freeze_boundary = _load(productization / "ai_freeze_boundary_status.json")
    gap_ledger_evidence_audit = _load(productization / "gap_ledger_evidence_audit.json")

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
            "status": _load(productization / "mgt_native_reanalysis_pipeline.json").get("status", "missing"),
            "integrity": (_load(productization / "mgt_native_reanalysis_pipeline.json").get("mgt_integrity") or {}).get(
                "integrity_status"
            ),
            "native_solve_status": (
                (_load(productization / "mgt_native_reanalysis_pipeline.json").get("native_fea") or {}).get(
                    "native_solve_status"
                )
                or _load(productization / "mgt_global_fea_condensed_solve.json").get("native_solve_status")
            ),
            "native_fea": (_load(productization / "mgt_native_reanalysis_pipeline.json").get("native_fea") or {}).get(
                "status"
            ),
            "global_fea_readiness": _load(productization / "mgt_global_fea_readiness_gate.json").get("status"),
            "mesh_contract": _load(productization / "mgt_global_fea_mesh_contract_gate.json").get("status"),
            "roundtrip_sync": bundle.get("summary", {}).get("mgt_roundtrip_sync_status"),
            "roundtrip_parsed": bool(bundle.get("summary", {}).get("mgt_roundtrip_parsed")),
        },
        "rh_closure_checklist": {
            "status": _load(productization / "rh_closure_checklist.json").get("status"),
            "open_count": _load(productization / "rh_closure_checklist.json").get("open_count"),
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
            "status": _load(productization / "rh_signed_closure_packet_template.json").get("status"),
            "open_count": _load(productization / "rh_signed_closure_packet_template.json").get("open_count"),
        },
        "rh_signed_closure": {
            "status": _load(productization / "residual_holdout_closure_updates.json").get("rh_closure_status"),
            "actual_closure_evidence_attached": _load(productization / "residual_holdout_closure_updates.json").get(
                "actual_closure_evidence_attached"
            ),
        },
        "ml_multi_objective_a_p3": {
            "status": (_load(productization / "ml_multi_objective_status.json").get("status") or "not_started"),
            "production_ml_wired": _load(productization / "ml_multi_objective_status.json").get(
                "production_ml_wired"
            ),
            "research_pareto_archive_ready": _load(productization / "ml_multi_objective_status.json").get(
                "research_pareto_archive_ready"
            ),
            "research_pareto_front_count": _load(productization / "ml_multi_objective_status.json").get(
                "research_pareto_front_count"
            ),
        },
        "ai_freeze_boundary": {
            "status": ai_freeze_boundary.get("status", "missing"),
            "contract_pass": bool(ai_freeze_boundary.get("contract_pass") is True),
            "autonomous_ai_engine_claim": bool(ai_freeze_boundary.get("autonomous_ai_engine_claim") is True),
            "surrogate_truth_claim_frozen": bool(ai_freeze_boundary.get("surrogate_truth_claim_frozen") is True),
            "ai_training_frozen": bool(ai_freeze_boundary.get("ai_training_frozen") is True),
            "shadow_solver_gated_only": bool(ai_freeze_boundary.get("shadow_solver_gated_only") is True),
            "production_pareto_policy_claim": bool(ai_freeze_boundary.get("production_pareto_policy_claim") is True),
            "claim_boundary": ai_freeze_boundary.get("claim_boundary"),
        },
        "gap_ledger_evidence_audit": {
            "status": gap_ledger_evidence_audit.get("status", "missing"),
            "contract_pass": bool(gap_ledger_evidence_audit.get("contract_pass") is True),
            "row_count": int(gap_ledger_evidence_audit.get("row_count", 0) or 0),
            "closed_row_count": int(gap_ledger_evidence_audit.get("closed_row_count", 0) or 0),
            "nonclosed_row_count": int(gap_ledger_evidence_audit.get("nonclosed_row_count", 0) or 0),
            "closed_evidence_coverage": gap_ledger_evidence_audit.get("closed_evidence_coverage", {}),
            "nonclosed_visibility": gap_ledger_evidence_audit.get("nonclosed_visibility", {}),
            "claim_boundary": gap_ledger_evidence_audit.get("claim_boundary"),
        },
    }

    blockers = list(bundle.get("blockers") or [])
    ledger_status = build_commercial_gap_ledger_status(productization_dir=productization)
    delivery_status = str(bundle.get("status") or "missing")
    if blockers:
        delivery_status = "review_required"
    authority_holdout_status = "open" if rh_still_open else "closed"

    ledger_rows = ledger_status.get("rows", [])
    if not isinstance(ledger_rows, list):
        ledger_rows = []

    return {
        "schema_version": "gap-closure-status.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": input_checksums(checksum_inputs, repo_root=REPO_ROOT),
        "reused_evidence": False,
        "overall_status": delivery_status,
        "delivery_status": delivery_status,
        "authority_holdout_status": authority_holdout_status,
        "bundle_status": bundle.get("status"),
        "blockers": blockers,
        "full_gap_ledger_status": ledger_status.get("status"),
        "full_gap_ledger_ready": bool(ledger_status.get("full_gap_ledger_ready")),
        "full_gap_ledger_summary": ledger_status.get("summary", {}),
        "full_gap_ledger_blockers": ledger_status.get("blockers", []),
        "next_locally_closable_gaps": ledger_status.get("next_locally_closable_gaps", []),
        "pending_authority_closure": rh_still_open > 0,
        "sections": sections,
        "ledger_requirements": _compact_ledger_requirements(ledger_rows),
        "artifacts": {
            "delivery_evidence_bundle": str(productization / "delivery_evidence_bundle.json"),
            "residual_holdout_closure_updates": str(productization / "residual_holdout_closure_updates.json"),
            "commercial_gap_ledger_status": str(productization / "commercial_gap_ledger_status.json"),
            "ai_freeze_boundary_status": str(productization / "ai_freeze_boundary_status.json"),
            "gap_ledger_evidence_audit": str(productization / "gap_ledger_evidence_audit.json"),
        },
        "claim_boundary": (
            "This is a read-only rollup of gap-ledger and productization evidence status. "
            "It does not create external receipts, customer evidence, G1 full-load closure, "
            "or release readiness by itself."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--productization-dir",
        type=Path,
        default=PRODUCTIZATION,
        help="Directory containing productization evidence JSON inputs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--fail-full-closure",
        action="store_true",
        help="Exit non-zero when the commercial solver/AI gap ledgers are not fully closed.",
    )
    args = parser.parse_args()
    output_json = args.output_json or (args.productization_dir / "gap_closure_status.json")
    payload = build_gap_closure_status(productization_dir=args.productization_dir)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"gap-status: delivery={payload['delivery_status']} "
        f"authority_holdout={payload['authority_holdout_status']} "
        f"full_gap_ledger={payload['full_gap_ledger_status']} -> {output_json}"
    )
    if args.fail_full_closure and not payload.get("full_gap_ledger_ready"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
