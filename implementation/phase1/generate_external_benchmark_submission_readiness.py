#!/usr/bin/env python3
"""Project whether the current release is ready to start external benchmark submission."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
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
DEFAULT_SUBMISSION_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
)

REASONS = {
    "PASS_START_NOW_FULL": "Current release is ready for a full external benchmark submission package.",
    "PASS_START_NOW_LIMITED": "Current release is ready to start external performance benchmarking now, but reviewer queue closure should precede the final external submission package.",
    "ERR_ARCHITECTURE_BLOCKERS": "Core architecture or benchmark coverage blockers remain before external benchmark submission should start.",
}

SUBMISSION_LANE_DEFAULTS = {
    "hardest_external_10case": {
        "work_item_id": "EB-001",
        "submission_id": "p1-hardest-external-10case",
        "closure_evidence_required": "hardest_external_10case_submission_receipt",
    },
    "tpu_hffb": {
        "work_item_id": "EB-002",
        "submission_id": "p1-tpu-hffb",
        "closure_evidence_required": "tpu_hffb_submission_receipt",
    },
    "peer_spd_hinge": {
        "work_item_id": "EB-003",
        "submission_id": "p1-peer-spd-hinge",
        "closure_evidence_required": "peer_spd_hinge_submission_receipt",
    },
    "korean_public_structures": {
        "work_item_id": "EB-004",
        "submission_id": "p1-korean-public-structures",
        "closure_evidence_required": "korean_public_structures_submission_receipt_or_authority_review_hold",
    },
}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_submission_updates(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("updates", payload.get("submission_updates", payload))
        if isinstance(rows, dict) and "external_benchmark_submission_work_items" in rows:
            rows = rows.get("external_benchmark_submission_work_items", [])
        elif rows is payload and isinstance(payload.get("queues"), dict):
            rows = payload["queues"].get("external_benchmark_submission_work_items", payload["queues"])
        elif rows is payload and "queues" in payload:
            rows = payload.get("queues", payload)
        elif rows is payload:
            rows = payload.get("submission_queue", payload)
    updates: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            queue_id = str(row.get("queue_id", "") or "").strip()
            if queue_id:
                updates[queue_id] = row
    elif isinstance(rows, dict):
        for queue_id, row in rows.items():
            if isinstance(row, dict):
                updates[str(queue_id)] = row
    return updates


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


def _midas_kds_exact_row_coverage_label(summary: dict[str, Any]) -> str:
    direct = str(summary.get("midas_kds_row_provenance_exact_row_coverage_label", "") or "").strip()
    if direct:
        return direct
    exact_rows = int(summary.get("midas_kds_row_provenance_export_exact_row_count", 0) or 0)
    total_rows = int(summary.get("midas_kds_row_provenance_export_row_count", 0) or 0)
    if total_rows:
        return f"{exact_rows}/{total_rows}"
    return "0/0"


def _report_summary_line(report: dict[str, Any], *, fallback_label: str) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for key in ("summary_line", "reason", "reason_code"):
        value = str(report.get(key, "") or summary.get(key, "") or "").strip()
        if value:
            return value
    if _truthy(report):
        return f"{fallback_label}: PASS"
    return f"{fallback_label}: CHECK"


def _submission_dry_run_evidence(*parts: object) -> str:
    evidence_parts = [str(part).strip() for part in parts if str(part).strip()]
    return " | ".join(evidence_parts) if evidence_parts else "n/a"


def _submission_queue_status(*, contract_pass: bool, queue_closed: bool) -> str:
    if not contract_pass:
        return "blocked"
    if queue_closed:
        return "ready_for_full_submission"
    return "ready_for_benchmark_start_final_review_pending"


def _submission_lifecycle(
    *,
    status: str,
    onepage_attestation_status: str,
    receipt_url: str,
    closure_evidence_path: str,
) -> dict[str, Any]:
    submitted = bool(receipt_url)
    closure_evidence_attached = bool(receipt_url or closure_evidence_path)
    if status == "ready_for_full_submission":
        lifecycle_status = "ready_to_submit" if not submitted else "submitted_receipt_attached"
        owner_action = (
            "submission_receipt_attached_verify_roundtrip"
            if submitted
            else "submit_external_benchmark_package_and_attach_receipt"
        )
        receipt_status = "attached" if submitted else "pending_external_submission_receipt"
    elif status == "ready_for_benchmark_start_final_review_pending":
        lifecycle_status = "benchmark_start_ready_review_boundary_pending"
        owner_action = "start_benchmark_execution_then_close_review_boundary_before_submission"
        receipt_status = "not_due_review_boundary_pending"
    else:
        lifecycle_status = "blocked"
        owner_action = "clear_blockers_before_submission"
        receipt_status = "blocked"
    return {
        "current_status": status,
        "submission_lifecycle_status": lifecycle_status,
        "submission_owner_action": owner_action,
        "submission_receipt_status": receipt_status,
        "onepage_attestation_status": onepage_attestation_status,
        "submitted": submitted,
        "receipt_verified": submitted,
        "closure_evidence_attached": closure_evidence_attached,
        "terminal": bool(status == "blocked" or (status == "ready_for_full_submission" and submitted)),
    }


def _merge_submission_update(
    row: dict[str, Any],
    update: dict[str, Any],
    *,
    onepage_attestation_status: str,
) -> dict[str, Any]:
    if not update:
        return row

    merged = dict(row)
    for key in (
        "submission_id",
        "receipt_url",
        "submission_receipt_url",
        "submitted_at_utc",
        "last_checked_at_utc",
        "closure_evidence_path",
        "closure_evidence_status",
        "closure_evidence_required",
    ):
        if key in update:
            merged[key] = str(update.get(key, "") or "")

    update_receipt = str(update.get("submission_receipt", "") or "")
    if update_receipt == "pending":
        update_receipt = ""
    receipt_url = str(
        merged.get("receipt_url", "")
        or merged.get("submission_receipt_url", "")
        or update_receipt
    )
    closure_evidence_path = str(merged.get("closure_evidence_path", "") or "")
    submitted_at_utc = str(merged.get("submitted_at_utc", "") or "")
    if receipt_url:
        merged["receipt_url"] = receipt_url
        merged["submission_receipt_url"] = receipt_url
        merged["submission_receipt"] = receipt_url
    elif "submission_receipt" in update:
        merged["submission_receipt"] = str(update.get("submission_receipt", "") or "pending")

    if "closure_evidence_status" not in update and (receipt_url or closure_evidence_path):
        merged["closure_evidence_status"] = "attached"

    lifecycle = _submission_lifecycle(
        status=str(merged.get("status", "") or ""),
        onepage_attestation_status=onepage_attestation_status,
        receipt_url=receipt_url,
        closure_evidence_path=closure_evidence_path,
    )
    submitted = bool(receipt_url or submitted_at_utc or update.get("submitted", False))
    receipt_verified = bool(receipt_url or update.get("receipt_verified", False))
    lifecycle_status = str(
        update.get("submission_lifecycle_status", "")
        or update.get("lifecycle", "")
        or update.get("lifecycle_status", "")
        or (
            "submitted_pending_receipt"
            if submitted and not receipt_verified
            else lifecycle.get("submission_lifecycle_status", "")
        )
    )
    submission_status = str(update.get("submission_status", "") or lifecycle_status)
    receipt_status = str(
        update.get("receipt_status", "")
        or update.get("submission_receipt_status", "")
        or ("pending_external_submission_receipt" if submitted and not receipt_verified else "")
        or lifecycle.get("submission_receipt_status", "")
    )
    owner_action = str(
        update.get("submission_owner_action", "")
        or (
            "attach_external_submission_receipt"
            if submitted and not receipt_verified
            else lifecycle.get("submission_owner_action", "")
        )
    )
    lifecycle = {
        **lifecycle,
        "submission_lifecycle_status": lifecycle_status,
        "submission_owner_action": owner_action,
        "submission_receipt_status": receipt_status,
        "submitted": submitted,
        "receipt_verified": receipt_verified,
        "closure_evidence_attached": bool(
            receipt_url
            or closure_evidence_path
            or str(merged.get("closure_evidence_status", "") or "").lower() in {"attached", "verified", "closed"}
        ),
    }
    lifecycle["terminal"] = bool(lifecycle.get("terminal", False) or lifecycle["receipt_verified"])

    merged["submission_lifecycle_status"] = lifecycle_status
    merged["submission_lifecycle"] = lifecycle_status
    merged["lifecycle"] = lifecycle_status
    merged["submission_status"] = submission_status
    merged["submission_owner_action"] = owner_action
    merged["submission_receipt_status"] = receipt_status
    merged["receipt_status"] = receipt_status
    merged["status_lifecycle"] = lifecycle
    return merged


def _submission_lane_row(
    *,
    queue_id: str,
    submission_scope: str,
    owner: str,
    status: str,
    onepage_attestation: str,
    onepage_attestation_status: str,
    dry_run_evidence: str,
    blocker_label: str,
    caution_label: str,
    commercial_scope: str,
    commercial_breadth: str,
    exact_rows: str,
    gap_summary: dict[str, Any],
    submission_updates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    defaults = SUBMISSION_LANE_DEFAULTS.get(queue_id, {})
    receipt_url = str(gap_summary.get(f"{queue_id}_receipt_url", "") or "")
    closure_evidence_path = str(gap_summary.get(f"{queue_id}_closure_evidence_path", "") or "")
    submitted_at_utc = str(gap_summary.get(f"{queue_id}_submitted_at_utc", "") or "")
    closure_evidence_status = str(
        gap_summary.get(f"{queue_id}_closure_evidence_status", "")
        or ("attached" if receipt_url or closure_evidence_path else "pending")
    )
    lifecycle = _submission_lifecycle(
        status=status,
        onepage_attestation_status=onepage_attestation_status,
        receipt_url=receipt_url,
        closure_evidence_path=closure_evidence_path,
    )
    row = {
        "work_item_id": str(defaults.get("work_item_id", "")),
        "queue_id": queue_id,
        "submission_id": str(gap_summary.get(f"{queue_id}_submission_id", "") or defaults.get("submission_id", queue_id)),
        "submission_scope": submission_scope,
        "owner": owner,
        "status": status,
        "queue_status": status,
        "lifecycle_status": status,
        "submission_lifecycle_status": str(lifecycle.get("submission_lifecycle_status", "")),
        "submission_lifecycle": str(lifecycle.get("submission_lifecycle_status", "")),
        "lifecycle": str(lifecycle.get("submission_lifecycle_status", "")),
        "submission_status": str(lifecycle.get("submission_lifecycle_status", "")),
        "submission_owner_action": str(lifecycle.get("submission_owner_action", "")),
        "submission_receipt": str(receipt_url or "pending"),
        "submission_receipt_status": str(lifecycle.get("submission_receipt_status", "")),
        "receipt_status": str(lifecycle.get("submission_receipt_status", "")),
        "receipt_url": receipt_url,
        "submission_receipt_url": receipt_url,
        "submitted_at_utc": submitted_at_utc,
        "last_checked_at_utc": str(gap_summary.get(f"{queue_id}_last_checked_at_utc", "") or ""),
        "onepage_attestation": onepage_attestation,
        "onepage_attestation_status": onepage_attestation_status,
        "dry_run_evidence": dry_run_evidence,
        "closure_evidence_required": str(
            gap_summary.get(f"{queue_id}_closure_evidence_required", "")
            or defaults.get("closure_evidence_required", "external_submission_receipt")
        ),
        "closure_evidence_path": closure_evidence_path,
        "closure_evidence_status": closure_evidence_status,
        "status_lifecycle": lifecycle,
        "blocker_label": blocker_label,
        "caution_label": caution_label,
        "commercial_scope_summary_line": commercial_scope,
        "commercial_reliability_breadth_summary_line": commercial_breadth,
        "midas_kds_row_provenance_exact_row_coverage_label": exact_rows,
    }
    return _merge_submission_update(
        row,
        submission_updates.get(queue_id, {}),
        onepage_attestation_status=onepage_attestation_status,
    )


def _build_submission_queue(
    *,
    contract_pass: bool,
    queue_closed: bool,
    blockers: list[str],
    cautions: list[str],
    gap_summary: dict[str, Any],
    tpu_hffb_benchmark_payload: dict[str, Any],
    peer_spd_hinge_benchmark_payload: dict[str, Any],
    peer_spd_hinge_fixture_regression_payload: dict[str, Any],
    peer_spd_hinge_alignment_payload: dict[str, Any],
    onepage_attestation_status: str,
    submission_updates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    status = _submission_queue_status(contract_pass=contract_pass, queue_closed=queue_closed)
    blocker_label = _label(blockers) if blockers else "none"
    caution_label = _label(cautions) if cautions else "none"
    commercial_scope = str(gap_summary.get("commercial_scope_summary_line", "") or "")
    commercial_breadth = str(gap_summary.get("commercial_reliability_breadth_summary_line", "") or "")
    exact_rows = _midas_kds_exact_row_coverage_label(gap_summary)
    hardest_external_10case_evidence = str(
        gap_summary.get("hardest_external_10case_kickoff_summary_line", "") or ""
    ).strip()
    if not hardest_external_10case_evidence:
        hardest_external_10case_evidence = f"hardest_external_10case_kickoff: {status}"
    tpu_hffb_evidence = _report_summary_line(tpu_hffb_benchmark_payload, fallback_label="tpu_hffb_benchmark_gate")
    peer_spd_hinge_evidence = _submission_dry_run_evidence(
        _report_summary_line(peer_spd_hinge_benchmark_payload, fallback_label="peer_spd_hinge_benchmark_gate"),
        _report_summary_line(peer_spd_hinge_fixture_regression_payload, fallback_label="peer_spd_hinge_fixture_regression"),
        _report_summary_line(peer_spd_hinge_alignment_payload, fallback_label="peer_spd_hinge_alignment"),
    )
    korean_public_structures_evidence = _submission_dry_run_evidence(
        str(gap_summary.get("korean_source_ingest_summary_line", "") or "").strip(),
        str(gap_summary.get("korean_structural_preview_queue_summary_line", "") or "").strip(),
    )
    if korean_public_structures_evidence == "n/a":
        korean_public_structures_evidence = f"korean_public_structures: {status}"
    tracks = [
        (
            "hardest_external_10case",
            "hardest_external_benchmark_program",
            "benchmark_program_owner",
            "hardest external 10-case one-page attestation",
            hardest_external_10case_evidence,
        ),
        (
            "tpu_hffb",
            "component_wind_benchmark_submission",
            "wind_benchmark_owner",
            "TPU/HFFB component benchmark one-page attestation",
            tpu_hffb_evidence,
        ),
        (
            "peer_spd_hinge",
            "component_hinge_benchmark_submission",
            "pbd_benchmark_owner",
            "PEER/SPD hinge component one-page attestation",
            peer_spd_hinge_evidence,
        ),
        (
            "korean_public_structures",
            "korean_public_structure_release_review",
            "korean_source_owner",
            "Korean public structures provenance one-page attestation",
            korean_public_structures_evidence,
        ),
    ]
    return [
        _submission_lane_row(
            queue_id=queue_id,
            submission_scope=submission_scope,
            owner=owner,
            status=status,
            onepage_attestation=attestation,
            onepage_attestation_status=onepage_attestation_status,
            dry_run_evidence=dry_run_evidence,
            blocker_label=blocker_label,
            caution_label=caution_label,
            commercial_scope=commercial_scope,
            commercial_breadth=commercial_breadth,
            exact_rows=exact_rows,
            gap_summary=gap_summary,
            submission_updates=submission_updates,
        )
        for queue_id, submission_scope, owner, attestation, dry_run_evidence in tracks
    ]


def build_submission_readiness(
    release_gap_payload: dict[str, Any],
    commercial_readiness_payload: dict[str, Any],
    tpu_hffb_benchmark_payload: dict[str, Any],
    peer_spd_hinge_benchmark_payload: dict[str, Any],
    peer_spd_hinge_fixture_regression_payload: dict[str, Any],
    peer_spd_hinge_alignment_payload: dict[str, Any],
    submission_updates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gap_summary = _summary(release_gap_payload)
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

    queue_status = _submission_queue_status(contract_pass=contract_pass, queue_closed=queue_closed)
    onepage_attestation_status = (
        "ready_for_full_submission"
        if queue_status == "ready_for_full_submission"
        else "draft_ready_final_review_pending"
        if queue_status == "ready_for_benchmark_start_final_review_pending"
        else "blocked"
    )
    submission_queue = _build_submission_queue(
        contract_pass=contract_pass,
        queue_closed=queue_closed,
        blockers=blockers,
        cautions=cautions,
        gap_summary=gap_summary,
        tpu_hffb_benchmark_payload=tpu_hffb_benchmark_payload,
        peer_spd_hinge_benchmark_payload=peer_spd_hinge_benchmark_payload,
        peer_spd_hinge_fixture_regression_payload=peer_spd_hinge_fixture_regression_payload,
        peer_spd_hinge_alignment_payload=peer_spd_hinge_alignment_payload,
        onepage_attestation_status=onepage_attestation_status,
        submission_updates=submission_updates or {},
    )
    submission_ready_count = sum(
        1 for row in submission_queue if str(row.get("status", "") or "") == "ready_for_full_submission"
    )
    submission_review_pending_count = sum(
        1
        for row in submission_queue
        if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
    )
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
    midas_kds_preview_rows = [
        row for row in (gap_summary.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "claim_boundary": (
            "External benchmark submission readiness is a local queue/readiness projection. "
            "It does not create or attach external benchmark submission receipts; receipt "
            "closure remains governed by external_benchmark_submission_updates."
        ),
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
            "commercial_scope_summary_line": str(gap_summary.get("commercial_scope_summary_line", "") or ""),
            "commercial_reliability_breadth_summary_line": str(
                gap_summary.get("commercial_reliability_breadth_summary_line", "") or ""
            ),
            "midas_kds_row_provenance_export_summary_line": str(
                gap_summary.get("midas_kds_row_provenance_export_summary_line", "") or ""
            ),
            "midas_kds_row_provenance_export_row_count": int(
                gap_summary.get("midas_kds_row_provenance_export_row_count", 0) or 0
            ),
            "midas_kds_row_provenance_export_exact_row_count": int(
                gap_summary.get("midas_kds_row_provenance_export_exact_row_count", 0) or 0
            ),
            "midas_kds_row_provenance_exact_row_coverage_label": _midas_kds_exact_row_coverage_label(gap_summary),
            "midas_kds_row_provenance_preview_row_count": len(midas_kds_preview_rows),
            "midas_kds_row_provenance_preview_rows_present": bool(midas_kds_preview_rows),
            "midas_kds_row_provenance_preview_rows": midas_kds_preview_rows,
            "blocker_count": int(len(blockers)),
            "blockers": blockers,
            "blocker_label": _label(blockers) if blockers else "none",
            "caution_count": int(len(cautions)),
            "cautions": cautions,
            "caution_label": _label(cautions) if cautions else "none",
            "submission_queue_count": int(len(submission_queue)),
            "submission_queue_ready_count": int(submission_ready_count),
            "submission_queue_review_pending_count": int(submission_review_pending_count),
            "submission_queue_blocked_count": int(
                len(submission_queue) - submission_ready_count - submission_review_pending_count
            ),
            "submission_lifecycle_ready_to_submit_count": int(
                sum(1 for row in submission_queue if row.get("submission_lifecycle_status") == "ready_to_submit")
            ),
            "submission_lifecycle_review_boundary_pending_count": int(
                sum(
                    1
                    for row in submission_queue
                    if row.get("submission_lifecycle_status") == "benchmark_start_ready_review_boundary_pending"
                )
            ),
            "submission_lifecycle_blocked_count": int(
                sum(1 for row in submission_queue if row.get("submission_lifecycle_status") == "blocked")
            ),
            "submission_receipt_pending_count": int(
                sum(
                    1
                    for row in submission_queue
                    if str(row.get("receipt_status", "") or "").startswith("pending")
                    or str(row.get("submission_receipt_status", "") or "").startswith("pending")
                )
            ),
            "submission_receipt_attached_count": int(
                sum(1 for row in submission_queue if str(row.get("submission_receipt", "") or "") != "pending")
            ),
            "submission_last_checked_count": int(
                sum(1 for row in submission_queue if str(row.get("last_checked_at_utc", "") or "").strip())
            ),
            "closure_evidence_attached_count": int(
                sum(
                    1
                    for row in submission_queue
                    if str(row.get("closure_evidence_status", "") or "").lower() in {"attached", "verified", "closed"}
                )
            ),
            "onepage_attestation_status": onepage_attestation_status,
            "onepage_attestation_required_count": int(len(submission_queue)),
            "onepage_attestation_ready_count": int(submission_ready_count),
            "next_actions": next_actions,
            "evidence": ", ".join(evidence_parts),
        },
        "submission_queue": submission_queue,
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
    parser.add_argument("--submission-updates", default=str(DEFAULT_SUBMISSION_UPDATES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    submission_updates_path = Path(args.submission_updates) if args.submission_updates else None
    payload = build_submission_readiness(
        _load_json(Path(args.release_gap_report)),
        _load_json(Path(args.commercial_readiness_report)),
        _load_json(Path(args.tpu_hffb_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_fixture_regression_report)),
        _load_json(Path(args.peer_spd_hinge_alignment_report)),
        _load_submission_updates(submission_updates_path),
    )
    payload["artifacts"] = {
        **(payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}),
        "external_benchmark_submission_updates": str(submission_updates_path) if submission_updates_path else "",
        "external_benchmark_submission_updates_present": bool(
            submission_updates_path and submission_updates_path.exists()
        ),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote external benchmark submission readiness report: {out_path}")


if __name__ == "__main__":
    main()
