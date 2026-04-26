#!/usr/bin/env python3
"""Project whether the current release is ready to start external benchmark submission."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

DEFAULT_RELEASE_GAP_REPORT = Path("implementation/phase1/release/release_gap_report.json")
DEFAULT_COMMERCIAL_READINESS_REPORT = Path("implementation/phase1/commercial_readiness_report.json")
DEFAULT_TPU_HFFB_BENCHMARK_REPORT = Path("implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json")
DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json"
)
DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json"
)
DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_refresh_alignment_report.json"
)
DEFAULT_OUT = Path("implementation/phase1/release/external_benchmark_submission_readiness.json")

REASONS = {
    "PASS_START_NOW_FULL": "Current release is ready for a full external benchmark submission package.",
    "PASS_START_NOW_LIMITED": "Current release is ready to start external performance benchmarking now, but reviewer queue closure should precede the final external submission package.",
    "ERR_ARCHITECTURE_BLOCKERS": "Core architecture or benchmark coverage blockers remain before external benchmark submission should start.",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else payload


def _label(values: list[str]) -> str:
    return ", ".join(values)


def _truthy(report: dict[str, Any]) -> bool:
    if "contract_pass" in report:
        return bool(report.get("contract_pass", False))
    if "all_pass" in report:
        return bool(report.get("all_pass", False))
    if "pass" in report:
        return bool(report.get("pass", False))
    return False


def build_submission_readiness(
    release_gap_payload: dict[str, Any],
    commercial_readiness_payload: dict[str, Any],
    tpu_hffb_benchmark_payload: dict[str, Any],
    peer_spd_hinge_benchmark_payload: dict[str, Any],
    peer_spd_hinge_fixture_regression_payload: dict[str, Any],
    peer_spd_hinge_alignment_payload: dict[str, Any],
) -> dict[str, Any]:
    gap_summary = _summary(release_gap_payload)
    commercial_summary = _summary(commercial_readiness_payload)
    commercial_checks = commercial_readiness_payload.get("checks") if isinstance(commercial_readiness_payload.get("checks"), dict) else {}

    core_holdouts_closed = bool(
        gap_summary.get("panel_zone_3d_clash_ready", False)
        and gap_summary.get("pbd_dynamic_hinge_refresh_ready", False)
        and gap_summary.get("foundation_optimization_ready", False)
        and gap_summary.get("wind_tunnel_raw_mapping_ready", False)
    )
    diversified_benchmark_gates_pass = bool(
        _truthy(tpu_hffb_benchmark_payload)
        and _truthy(peer_spd_hinge_benchmark_payload)
        and _truthy(peer_spd_hinge_fixture_regression_payload)
        and _truthy(peer_spd_hinge_alignment_payload)
    )
    commercial_readiness_pass = bool(_truthy(commercial_readiness_payload))
    commercial_readiness_real_source_pass = bool(commercial_checks.get("real_source_pass", False))
    commercial_readiness_gpu_strict_pass = bool(commercial_checks.get("gpu_strict_pass", False))
    commercial_ready = bool(
        commercial_readiness_pass and commercial_readiness_real_source_pass and commercial_readiness_gpu_strict_pass
    )
    evidence_model = str(gap_summary.get("mgt_export_evidence_model", "") or "")
    audit_boundary_ready = bool(
        evidence_model
        in {
            "direct_patch_plus_audit_review_manifest",
            "direct_patch_plus_zero_touch_verification_manifest",
        }
        and int(gap_summary.get("mgt_export_instruction_sidecar_change_count", 0) or 0) == 0
    )
    pending_review_count = int(gap_summary.get("mgt_export_audit_review_queue_pending_count", 0) or 0)
    overdue_review_count = int(gap_summary.get("mgt_export_audit_review_followup_overdue_item_count", 0) or 0)
    open_revision_count = int(gap_summary.get("mgt_export_audit_review_resolution_open_revision_count", 0) or 0)
    queue_clean = overdue_review_count == 0
    resolution_clear = open_revision_count == 0
    queue_closed = pending_review_count == 0 and resolution_clear
    panel_validation_boundary = str(gap_summary.get("panel_zone_validation_boundary", "") or "")
    external_validation_boundary_only = panel_validation_boundary == "external_validation_only"
    panel_zone_validation_advisory_only = external_validation_boundary_only
    panel_zone_validation_advisory_label = (
        "panel_zone_external_validation_only_boundary" if panel_zone_validation_advisory_only else "none"
    )

    blockers: list[str] = []
    cautions: list[str] = []
    next_actions: list[str] = []

    if not core_holdouts_closed:
        blockers.append("core_holdouts_not_closed")
        next_actions.append("close remaining panel/hinge/foundation/wind release holdouts")
    if not diversified_benchmark_gates_pass:
        blockers.append("diversified_benchmark_gates_not_green")
        next_actions.append("green TPU HFFB and PEER SPD benchmark gates together")
    if not commercial_ready:
        blockers.append("commercial_readiness_not_green")
        next_actions.append("green commercial readiness with real-source and GPU-strict checks")
    if not audit_boundary_ready:
        blockers.append("mgt_export_not_audit_only_boundary")
        next_actions.append("remove remaining manual sidecar dependence from MGT export")
    if not queue_clean:
        blockers.append("audit_review_queue_has_overdue_items")
        next_actions.append("clear overdue review packets before external submission")
    if not resolution_clear:
        blockers.append("audit_review_resolution_has_open_revisions")
        next_actions.append("close open revision-cycle packets before full external submission")
    if external_validation_boundary_only:
        cautions.append("panel_zone_external_validation_only_boundary")
    if pending_review_count > 0:
        cautions.append(f"audit_review_queue_pending={pending_review_count}")
        next_actions.append("close pending audit-review packets before final external submission package")

    if blockers:
        reason_code = "ERR_ARCHITECTURE_BLOCKERS"
        recommended_start_mode = "wait_for_blockers"
        recommended_submission_scope = "hold_external_submission"
        contract_pass = False
    elif queue_closed:
        reason_code = "PASS_START_NOW_FULL"
        recommended_start_mode = "start_now_full_external_submission"
        recommended_submission_scope = "full_external_submission_package"
        contract_pass = True
    else:
        reason_code = "PASS_START_NOW_LIMITED"
        recommended_start_mode = "start_now_limited_external_benchmark"
        recommended_submission_scope = "component_and_system_performance_benchmark_with_review_boundary"
        contract_pass = True

    evidence_parts = [
        f"core_holdouts_closed={core_holdouts_closed}",
        f"diversified_benchmarks={diversified_benchmark_gates_pass}",
        f"commercial_ready={commercial_ready}",
        f"audit_boundary={audit_boundary_ready}:{evidence_model}",
        f"pending_review={pending_review_count}",
        f"overdue_review={overdue_review_count}",
        f"open_revision={open_revision_count}",
        f"panel_validation_boundary={panel_validation_boundary or 'n/a'}",
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "checks": {
            "core_holdouts_closed": core_holdouts_closed,
            "diversified_benchmark_gates_pass": diversified_benchmark_gates_pass,
            "commercial_readiness_pass": commercial_readiness_pass,
            "commercial_readiness_real_source_pass": commercial_readiness_real_source_pass,
            "commercial_readiness_gpu_strict_pass": commercial_readiness_gpu_strict_pass,
            "commercial_ready": commercial_ready,
            "mgt_export_audit_only_boundary_ready": audit_boundary_ready,
            "audit_review_queue_clean": queue_clean,
            "audit_review_queue_closed": queue_closed,
            "audit_review_resolution_clear": resolution_clear,
            "panel_zone_external_validation_boundary_only": external_validation_boundary_only,
            "panel_zone_validation_advisory_only": panel_zone_validation_advisory_only,
        },
        "summary": {
            "recommended_start_mode": recommended_start_mode,
            "recommended_submission_scope": recommended_submission_scope,
            "ready_to_start_now": bool(contract_pass),
            "ready_to_start_full_submission_now": bool(reason_code == "PASS_START_NOW_FULL"),
            "core_holdouts_closed": core_holdouts_closed,
            "diversified_benchmark_gates_pass": diversified_benchmark_gates_pass,
            "commercial_readiness_pass": commercial_readiness_pass,
            "commercial_readiness_real_source_pass": commercial_readiness_real_source_pass,
            "commercial_readiness_gpu_strict_pass": commercial_readiness_gpu_strict_pass,
            "mgt_export_audit_only_boundary_ready": audit_boundary_ready,
            "mgt_export_evidence_model": evidence_model,
            "audit_review_queue_pending_count": pending_review_count,
            "audit_review_queue_overdue_item_count": overdue_review_count,
            "audit_review_resolution_open_revision_count": open_revision_count,
            "panel_zone_validation_boundary": panel_validation_boundary,
            "external_validation_boundary_only": external_validation_boundary_only,
            "panel_zone_validation_advisory_only": panel_zone_validation_advisory_only,
            "panel_zone_validation_advisory_label": panel_zone_validation_advisory_label,
            "blocker_count": int(len(blockers)),
            "blockers": blockers,
            "blocker_label": _label(blockers) if blockers else "none",
            "caution_count": int(len(cautions)),
            "cautions": cautions,
            "caution_label": _label(cautions) if cautions else "none",
            "next_actions": next_actions,
            "evidence": ", ".join(evidence_parts),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-gap-report", default=str(DEFAULT_RELEASE_GAP_REPORT))
    parser.add_argument("--commercial-readiness-report", default=str(DEFAULT_COMMERCIAL_READINESS_REPORT))
    parser.add_argument("--tpu-hffb-benchmark-report", default=str(DEFAULT_TPU_HFFB_BENCHMARK_REPORT))
    parser.add_argument("--peer-spd-hinge-benchmark-report", default=str(DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT))
    parser.add_argument(
        "--peer-spd-hinge-fixture-regression-report",
        default=str(DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT),
    )
    parser.add_argument("--peer-spd-hinge-alignment-report", default=str(DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_submission_readiness(
        _load_json(Path(args.release_gap_report)),
        _load_json(Path(args.commercial_readiness_report)),
        _load_json(Path(args.tpu_hffb_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_fixture_regression_report)),
        _load_json(Path(args.peer_spd_hinge_alignment_report)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote external benchmark submission readiness report: {out_path}")


if __name__ == "__main__":
    main()
