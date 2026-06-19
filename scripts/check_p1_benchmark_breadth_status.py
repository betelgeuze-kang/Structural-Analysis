#!/usr/bin/env python3
"""Summarize P1 benchmark breadth readiness without bypassing the P0 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from check_p1_readiness_status import build_status as build_p1_readiness_status  # noqa: E402
from implementation.phase1.generate_external_benchmark_submission_readiness import (  # noqa: E402
    _load_submission_updates,
    _merge_submission_update,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


DEFAULT_COMMERCIAL_READINESS = Path("implementation/phase1/commercial_readiness_report.json")
DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS = Path(
    "implementation/phase1/release/external_benchmark_submission_readiness.json"
)
DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
)
DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
)
DEFAULT_BENCHMARK_REPORTS = (
    Path("implementation/phase1/hf_benchmark_report.json"),
    Path("implementation/phase1/hf_benchmark_report.rwth_zenodo.json"),
    Path("implementation/phase1/hf_benchmark_report.from_csv.json"),
    Path("implementation/phase1/hf_benchmark_report.atwood_open.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_pr.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_nightly.json"),
    Path("implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json"),
    Path("implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"),
)
REQUIRED_COMMERCIAL_CHECKS = (
    "real_source_pass",
    "benchmark_breadth_pass",
    "measured_dynamic_targets_pass",
    "measured_source_family_pass",
    "measured_case_count_pass",
    "accuracy_pass",
    "noise_robustness_pass",
    "ood_safety_pass",
    "gpu_strict_pass",
)
ATTACHED_EVIDENCE_STATUSES = {"attached", "verified", "closed", "signed_attached"}

RESIDUAL_HOLDOUT_QUEUE_DEFAULTS = {
    "licensed_engineer_review_required": {
        "work_item_id": "RH-001",
        "queue_name": "licensed_engineer_review_queue",
        "queue_status": "pending_review",
        "status": "open",
        "sla_hours": 72,
        "sla_label": "72h",
        "due_date": "assignment_plus_3_business_days",
        "closure_evidence_required": "signed_engineer_review_packet",
    },
    "legacy_tool_cross_validation_required": {
        "work_item_id": "RH-002",
        "queue_name": "legacy_tool_cross_validation_queue",
        "queue_status": "pending_cross_validation",
        "status": "open",
        "sla_hours": 120,
        "sla_label": "120h",
        "due_date": "assignment_plus_5_business_days",
        "closure_evidence_required": "legacy_tool_cross_validation_report",
    },
    "legal_authority_signoff_required": {
        "work_item_id": "RH-003",
        "queue_name": "legal_authority_signoff_queue",
        "queue_status": "pending_signoff",
        "status": "open",
        "sla_hours": 168,
        "sla_label": "168h",
        "due_date": "authority_submission_window",
        "closure_evidence_required": "authority_signoff_receipt_or_formal_hold",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_residual_holdout_updates(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    rows: Any = payload.get("updates", payload.get("residual_holdout_updates", payload))
    if isinstance(rows, dict) and "residual_holdout_work_items" in rows:
        rows = rows.get("residual_holdout_work_items", [])
    elif rows is payload and isinstance(payload.get("queues"), dict):
        rows = payload["queues"].get("residual_holdout_work_items", [])
    elif rows is payload:
        rows = payload.get("residual_holdout_work_items", payload)

    updates: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("work_item_id", "category_id", "id"):
                row_id = str(row.get(key, "") or "").strip()
                if row_id:
                    updates[row_id] = row
    elif isinstance(rows, dict):
        for row_id, row in rows.items():
            if isinstance(row, dict):
                updates[str(row_id)] = row
    return updates


def _status(ok: bool) -> str:
    return "ready" if ok else "blocked"


def _report_pass(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("contract_pass"), bool):
        return bool(payload["contract_pass"])
    if isinstance(payload.get("all_pass"), bool):
        return bool(payload["all_pass"])
    if isinstance(payload.get("pass"), bool):
        return bool(payload["pass"])
    return False


def _summary_line(payload: dict[str, Any], path: Path) -> str:
    direct = str(payload.get("summary_line", "") or "").strip()
    if direct:
        return direct
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    nested = str(summary.get("summary_line", "") or "").strip()
    return nested or path.name


def _commercial_gate(
    path: Path,
    residual_holdout_closure_updates: Path | None = DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
) -> dict[str, Any]:
    payload = _load_json(path)
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    grade = payload.get("grade") if isinstance(payload.get("grade"), dict) else {}
    deployment_model = payload.get("deployment_model") if isinstance(payload.get("deployment_model"), dict) else {}
    residual_holdouts = (
        payload.get("residual_holdout_categories")
        if isinstance(payload.get("residual_holdout_categories"), list)
        else []
    )
    residual_work_items = _residual_holdout_work_items(
        payload,
        residual_holdouts,
        updates=_load_residual_holdout_updates(residual_holdout_closure_updates),
    )
    missing_checks = [name for name in REQUIRED_COMMERCIAL_CHECKS if not bool(checks.get(name, False))]
    commercial_grade_pass = bool(grade.get("commercial_pass", False))
    engineer_in_loop_ready = bool(deployment_model.get("engineer_in_loop_accelerated_coverage_ready", False))
    full_replacement_ready = bool(deployment_model.get("full_commercial_replacement_ready", False))
    commercial_scope_ready = bool(commercial_grade_pass and (engineer_in_loop_ready or full_replacement_ready))
    exists = path.exists()
    ok = bool(exists and _report_pass(payload) and not missing_checks and commercial_scope_ready)
    return {
        "label": "Commercial readiness breadth",
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
        "missing_required_checks": missing_checks,
        "commercial_grade_label": str(grade.get("label", "") or ""),
        "commercial_grade_pass": commercial_grade_pass,
        "commercial_deployment_mode": str(deployment_model.get("mode", "") or ""),
        "engineer_in_loop_accelerated_coverage_ready": engineer_in_loop_ready,
        "full_commercial_replacement_ready": full_replacement_ready,
        "accelerated_coverage_target_pct_range": deployment_model.get("accelerated_coverage_target_pct_range", []),
        "residual_holdout_target_pct_range": deployment_model.get("residual_holdout_target_pct_range", []),
        "residual_holdout_category_count": len(residual_holdouts),
        "residual_holdout_work_item_count": len(residual_work_items),
        "residual_holdout_open_count": sum(1 for row in residual_work_items if not _is_residual_closed(row)),
        "residual_holdout_closure_evidence_pending_count": sum(
            1
            for row in residual_work_items
            if not _is_residual_closed(row) and str(row.get("closure_evidence_status", "") or "").lower() == "pending"
        ),
        "residual_holdout_closure_evidence_attached_count": sum(
            1
            for row in residual_work_items
            if str(row.get("closure_evidence_status", "") or "").lower() in ATTACHED_EVIDENCE_STATUSES
        ),
        "residual_holdout_last_checked_count": sum(
            1 for row in residual_work_items if str(row.get("last_checked_at_utc", "") or "").strip()
        ),
        "residual_holdout_work_items": residual_work_items,
        "residual_holdout_closure_updates_path": str(residual_holdout_closure_updates or ""),
        "residual_holdout_closure_updates_present": bool(
            residual_holdout_closure_updates and residual_holdout_closure_updates.exists()
        ),
        "commercial_scope_ready": commercial_scope_ready,
    }


def _submission_owner_action(row: dict[str, Any]) -> str:
    direct = str(row.get("submission_owner_action", "") or "").strip()
    if direct:
        return direct
    lifecycle = row.get("status_lifecycle") if isinstance(row.get("status_lifecycle"), dict) else {}
    return str(lifecycle.get("submission_owner_action", "") or "").strip()


def _submission_receipt(row: dict[str, Any]) -> str:
    direct = str(row.get("submission_receipt", "") or "").strip()
    if direct and direct != "pending":
        return direct
    return str(row.get("receipt_url", "") or row.get("submission_receipt_url", "") or "pending")


def _external_submission_queue_gate(
    path: Path,
    *,
    submission_updates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = _load_json(path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    updates = submission_updates or {}
    rows: list[dict[str, Any]] = []
    updates_applied_count = 0
    for raw_row in (payload.get("submission_queue") or []):
        if not isinstance(raw_row, dict):
            continue
        queue_id = str(raw_row.get("queue_id", "") or "").strip()
        work_item_id = str(raw_row.get("work_item_id", "") or "").strip()
        update = updates.get(queue_id) or updates.get(work_item_id) or {}
        row = raw_row
        if update:
            updates_applied_count += 1
            row = _merge_submission_update(
                raw_row,
                update,
                onepage_attestation_status=str(
                    raw_row.get("onepage_attestation_status", "")
                    or summary.get("onepage_attestation_status", "")
                    or ""
                ),
            )
        rows.append(row)
    exists = path.exists()
    queue_count = len(rows) if rows else int(summary.get("submission_queue_count", 0) or 0)
    ready_count = sum(
        1 for row in rows if str(row.get("status", "") or "") == "ready_for_full_submission"
    )
    review_pending_count = sum(
        1
        for row in rows
        if str(row.get("status", "") or "") == "ready_for_benchmark_start_final_review_pending"
    )
    blocked_count = sum(1 for row in rows if str(row.get("status", "") or "") == "blocked")
    lifecycle_ready_count = sum(
        1 for row in rows if str(row.get("submission_lifecycle_status", "") or "") == "ready_to_submit"
    )
    lifecycle_review_pending_count = sum(
        1
        for row in rows
        if str(row.get("submission_lifecycle_status", "") or "")
        == "benchmark_start_ready_review_boundary_pending"
    )
    lifecycle_blocked_count = sum(
        1 for row in rows if str(row.get("submission_lifecycle_status", "") or "") == "blocked"
    )
    receipt_pending_count = sum(
        1
        for row in rows
        if str(row.get("receipt_status", "") or row.get("submission_receipt_status", "") or "").startswith(
            "pending"
        )
    )
    required_fields_present = bool(
        rows
        and all(
            str(row.get("work_item_id", "") or "").strip()
            and str(row.get("submission_id", "") or "").strip()
            and "receipt_url" in row
            and str(row.get("submission_receipt", "") or "").strip()
            and str(row.get("receipt_status", "") or row.get("submission_receipt_status", "") or "").strip()
            and str(row.get("submission_lifecycle_status", "") or "").strip()
            and _submission_owner_action(row)
            and str(row.get("status", "") or "").strip()
            and isinstance(row.get("status_lifecycle"), dict)
            and str(row.get("closure_evidence_required", "") or "").strip()
            and str(row.get("closure_evidence_status", "") or "").strip()
            for row in rows
        )
    )
    ok = bool(exists and _report_pass(payload) and queue_count == 4 and required_fields_present and blocked_count == 0)
    return {
        "label": "External benchmark submission queue",
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
        "submission_queue_count": queue_count,
        "submission_queue_ready_count": ready_count,
        "submission_queue_review_pending_count": review_pending_count,
        "submission_queue_blocked_count": blocked_count,
        "submission_lifecycle_ready_to_submit_count": lifecycle_ready_count,
        "submission_lifecycle_review_boundary_pending_count": lifecycle_review_pending_count,
        "submission_lifecycle_blocked_count": lifecycle_blocked_count,
        "submission_receipt_attached_count": int(
            sum(1 for row in rows if _submission_receipt(row) != "pending")
        ),
        "submission_receipt_pending_count": receipt_pending_count,
        "submission_last_checked_count": int(
            sum(1 for row in rows if str(row.get("last_checked_at_utc", "") or "").strip())
        ),
        "closure_evidence_attached_count": int(
            sum(
                1
                for row in rows
                if str(row.get("closure_evidence_status", "") or "").lower() in ATTACHED_EVIDENCE_STATUSES
            )
        ),
        "onepage_attestation_status": str(summary.get("onepage_attestation_status", "") or ""),
        "required_lifecycle_fields_present": required_fields_present,
        "external_benchmark_submission_updates_applied_count": updates_applied_count,
        "submission_queue": rows,
    }


def _is_residual_closed(row: dict[str, Any]) -> bool:
    status = str(row.get("status", "") or "").lower()
    evidence_status = str(row.get("closure_evidence_status", "") or "").lower()
    return status in {"closed", "complete", "completed"} or evidence_status in ATTACHED_EVIDENCE_STATUSES


def _merge_residual_update(row: dict[str, Any], updates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    update = updates.get(str(row.get("work_item_id", "") or "")) or updates.get(str(row.get("category_id", "") or ""))
    if not update:
        return row
    merged = dict(row)
    for key in (
        "owner",
        "queue_name",
        "queue_status",
        "status",
        "sla_label",
        "due_date",
        "closure_evidence_required",
        "closure_evidence_path",
        "closure_evidence_status",
        "last_checked_at_utc",
        "closed_at_utc",
    ):
        if key in update:
            merged[key] = str(update.get(key, "") or "")
    if "sla_hours" in update:
        merged["sla_hours"] = int(update.get("sla_hours", merged.get("sla_hours", 0)) or 0)
    if "closure_evidence_status" not in update and str(merged.get("closure_evidence_path", "") or "").strip():
        merged["closure_evidence_status"] = "attached"
    return merged


def _residual_holdout_work_items(
    payload: dict[str, Any],
    residual_holdouts: list[Any],
    *,
    updates: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    updates = updates or {}
    explicit_items = payload.get("residual_holdout_work_items")
    if isinstance(explicit_items, list) and explicit_items:
        enriched: list[dict[str, Any]] = []
        for row in explicit_items:
            if not isinstance(row, dict):
                continue
            category_id = str(row.get("category_id", row.get("id", "")) or "")
            defaults = RESIDUAL_HOLDOUT_QUEUE_DEFAULTS.get(category_id, {})
            closure_evidence_path = str(row.get("closure_evidence_path", "") or "")
            item = {
                **row,
                "work_item_id": str(
                    row.get("work_item_id", "")
                    or defaults.get("work_item_id", f"RH-{len(enriched) + 1:03d}")
                ),
                "category_id": category_id,
                "owner": str(row.get("owner", "") or ""),
                "queue_name": str(row.get("queue_name", "") or defaults.get("queue_name", "residual_holdout_queue")),
                "queue_status": str(row.get("queue_status", "") or defaults.get("queue_status", "pending_review")),
                "status": str(row.get("status", "") or defaults.get("status", "open")),
                "sla_hours": int(row.get("sla_hours", defaults.get("sla_hours", 120)) or defaults.get("sla_hours", 120)),
                "sla_label": str(row.get("sla_label", "") or defaults.get("sla_label", "120h")),
                "due_date": str(row.get("due_date", "") or defaults.get("due_date", "assignment_plus_5_business_days")),
                "closure_evidence_required": str(
                    row.get("closure_evidence_required", "")
                    or defaults.get("closure_evidence_required", "owner_approved_closure_evidence")
                ),
                "closure_evidence_path": closure_evidence_path,
                "closure_evidence_status": str(
                    row.get("closure_evidence_status", "") or ("attached" if closure_evidence_path else "pending")
                ),
                "last_checked_at_utc": str(row.get("last_checked_at_utc", "") or ""),
            }
            enriched.append(_merge_residual_update(item, updates))
        return enriched

    work_items: list[dict[str, Any]] = []
    for row in residual_holdouts:
        if not isinstance(row, dict):
            continue
        category_id = str(row.get("id", "") or "")
        defaults = RESIDUAL_HOLDOUT_QUEUE_DEFAULTS.get(category_id, {})
        item = {
            "work_item_id": str(
                row.get("work_item_id", "") or defaults.get("work_item_id", f"RH-{len(work_items) + 1:03d}")
            ),
            "category_id": category_id,
            "owner": str(row.get("owner", "") or ""),
            "queue_name": str(row.get("queue_name", "") or defaults.get("queue_name", "residual_holdout_queue")),
            "queue_status": str(row.get("queue_status", "") or defaults.get("queue_status", "pending_review")),
            "status": str(row.get("status", "") or defaults.get("status", "open")),
            "sla_hours": int(row.get("sla_hours", defaults.get("sla_hours", 120)) or defaults.get("sla_hours", 120)),
            "sla_label": str(row.get("sla_label", "") or defaults.get("sla_label", "120h")),
            "due_date": str(row.get("due_date", "") or defaults.get("due_date", "assignment_plus_5_business_days")),
            "closure_evidence_required": str(
                row.get("closure_evidence_required", "")
                or defaults.get("closure_evidence_required", "owner_approved_closure_evidence")
            ),
            "closure_evidence_path": str(row.get("closure_evidence_path", "") or ""),
            "closure_evidence_status": str(
                row.get("closure_evidence_status", "")
                or ("attached" if str(row.get("closure_evidence_path", "") or "") else "pending")
            ),
            "last_checked_at_utc": str(row.get("last_checked_at_utc", "") or ""),
        }
        work_items.append(_merge_residual_update(item, updates))
    return work_items


def _benchmark_gate(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    exists = path.exists()
    ok = bool(exists and _report_pass(payload))
    return {
        "label": path.stem.replace("_", " "),
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
    }


def _read_or_build_p1(path: Path | None, publication_evidence_index: Path | None) -> dict[str, Any]:
    if path is not None:
        return _load_json(path)
    return build_p1_readiness_status(publication_evidence_index=publication_evidence_index)


def _p1_gate(payload: dict[str, Any]) -> dict[str, Any]:
    p1_execution_unblocked = bool(payload.get("p1_execution_unblocked", False))
    return {
        "label": "P1 execution prerequisite",
        "status": _status(p1_execution_unblocked),
        "ok": p1_execution_unblocked,
        "p0_core_evidence_closed": bool(payload.get("p0_core_evidence_closed", False)),
        "p1_inputs_ready": bool(payload.get("p1_inputs_ready", False)),
        "p1_execution_unblocked": p1_execution_unblocked,
        "p0_release_blocker": bool(payload.get("p0_release_blocker", True)),
    }


def build_status(
    *,
    p1_readiness_status: Path | None = None,
    publication_evidence_index: Path | None = None,
    commercial_readiness: Path = DEFAULT_COMMERCIAL_READINESS,
    external_benchmark_submission_readiness: Path = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    external_benchmark_submission_updates: Path | None = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    residual_holdout_closure_updates: Path | None = DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    benchmark_reports: list[Path] | tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    p1_payload = _read_or_build_p1(p1_readiness_status, publication_evidence_index)
    p1_gate = _p1_gate(p1_payload)
    reports = list(benchmark_reports if benchmark_reports is not None else DEFAULT_BENCHMARK_REPORTS)
    commercial_gate = _commercial_gate(
        commercial_readiness,
        residual_holdout_closure_updates=residual_holdout_closure_updates,
    )
    external_submission_updates = _load_submission_updates(external_benchmark_submission_updates)
    external_submission_gate = _external_submission_queue_gate(
        external_benchmark_submission_readiness,
        submission_updates=external_submission_updates,
    )
    evidence_gates = [commercial_gate, external_submission_gate, *[_benchmark_gate(path) for path in reports]]
    benchmark_breadth_inputs_ready = all(bool(gate["ok"]) for gate in evidence_gates)
    p1_benchmark_execution_unblocked = bool(benchmark_breadth_inputs_ready and p1_gate["p1_execution_unblocked"])
    if not benchmark_breadth_inputs_ready:
        next_action = "fix blocked P1 benchmark breadth evidence"
    elif bool(p1_gate["p0_release_blocker"]):
        next_action = "close P0-1 release publication before running P1 benchmark breadth"
    elif not bool(p1_gate["p1_inputs_ready"]):
        next_action = "fix blocked P1 readiness gates"
    else:
        next_action = "run P1 quality/fallback/benchmark breadth execution"
    pass_count = sum(1 for gate in evidence_gates if bool(gate["ok"]))
    return {
        "schema_version": "p1-benchmark-breadth-status.v1",
        **release_evidence_metadata(
            input_paths=[
                *( [p1_readiness_status] if p1_readiness_status is not None else [] ),
                *( [publication_evidence_index] if publication_evidence_index is not None else [] ),
                commercial_readiness,
                external_benchmark_submission_readiness,
                *( [external_benchmark_submission_updates] if external_benchmark_submission_updates is not None else [] ),
                *( [residual_holdout_closure_updates] if residual_holdout_closure_updates is not None else [] ),
                *reports,
            ],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_p1_readiness_commercial_benchmark_and_sidecar_receipts",
        ),
        "status": "ready" if p1_benchmark_execution_unblocked else "blocked",
        "benchmark_breadth_inputs_ready": benchmark_breadth_inputs_ready,
        "p1_benchmark_execution_unblocked": p1_benchmark_execution_unblocked,
        "p1_execution_unblocked": bool(p1_gate["p1_execution_unblocked"]),
        "p0_release_blocker": bool(p1_gate["p0_release_blocker"]),
        "publication_evidence_index": str(
            publication_evidence_index or p1_payload.get("publication_evidence_index", "")
        ),
        "summary": {
            "evidence_gate_count": len(evidence_gates),
            "evidence_gate_pass_count": pass_count,
            "benchmark_report_count": len(reports),
            "external_benchmark_submission": {
                "submission_queue_count": external_submission_gate["submission_queue_count"],
                "submission_queue_ready_count": external_submission_gate["submission_queue_ready_count"],
                "submission_queue_review_pending_count": external_submission_gate[
                    "submission_queue_review_pending_count"
                ],
                "submission_queue_blocked_count": external_submission_gate["submission_queue_blocked_count"],
                "submission_lifecycle_ready_to_submit_count": external_submission_gate[
                    "submission_lifecycle_ready_to_submit_count"
                ],
                "submission_lifecycle_review_boundary_pending_count": external_submission_gate[
                    "submission_lifecycle_review_boundary_pending_count"
                ],
                "submission_lifecycle_blocked_count": external_submission_gate[
                    "submission_lifecycle_blocked_count"
                ],
                "submission_receipt_attached_count": external_submission_gate["submission_receipt_attached_count"],
                "submission_receipt_pending_count": external_submission_gate["submission_receipt_pending_count"],
                "submission_last_checked_count": external_submission_gate["submission_last_checked_count"],
                "closure_evidence_attached_count": external_submission_gate["closure_evidence_attached_count"],
                "external_benchmark_submission_updates_path": str(external_benchmark_submission_updates or ""),
                "external_benchmark_submission_updates_present": bool(
                    external_benchmark_submission_updates and external_benchmark_submission_updates.exists()
                ),
                "external_benchmark_submission_updates_applied_count": external_submission_gate[
                    "external_benchmark_submission_updates_applied_count"
                ],
                "onepage_attestation_status": external_submission_gate["onepage_attestation_status"],
                "required_lifecycle_fields_present": external_submission_gate[
                    "required_lifecycle_fields_present"
                ],
            },
            "commercialization_scope": {
                "commercial_grade_label": commercial_gate["commercial_grade_label"],
                "commercial_deployment_mode": commercial_gate["commercial_deployment_mode"],
                "engineer_in_loop_accelerated_coverage_ready": commercial_gate[
                    "engineer_in_loop_accelerated_coverage_ready"
                ],
                "full_commercial_replacement_ready": commercial_gate["full_commercial_replacement_ready"],
                "accelerated_coverage_target_pct_range": commercial_gate[
                    "accelerated_coverage_target_pct_range"
                ],
                "residual_holdout_target_pct_range": commercial_gate["residual_holdout_target_pct_range"],
                "residual_holdout_category_count": commercial_gate["residual_holdout_category_count"],
                "residual_holdout_work_item_count": commercial_gate["residual_holdout_work_item_count"],
                "residual_holdout_open_count": commercial_gate["residual_holdout_open_count"],
                "residual_holdout_closure_evidence_pending_count": commercial_gate[
                    "residual_holdout_closure_evidence_pending_count"
                ],
                "residual_holdout_closure_evidence_attached_count": commercial_gate[
                    "residual_holdout_closure_evidence_attached_count"
                ],
                "residual_holdout_last_checked_count": commercial_gate["residual_holdout_last_checked_count"],
                "residual_holdout_closure_updates_path": commercial_gate["residual_holdout_closure_updates_path"],
                "residual_holdout_closure_updates_present": commercial_gate[
                    "residual_holdout_closure_updates_present"
                ],
                "commercial_scope_ready": commercial_gate["commercial_scope_ready"],
            },
        },
        "gates": [p1_gate, *evidence_gates],
        "next_action": next_action,
    }


def _markdown(status: dict[str, Any]) -> str:
    lines = [
        "# P1 Benchmark Breadth Status",
        "",
        f"- Benchmark inputs ready: `{bool(status['benchmark_breadth_inputs_ready'])}`",
        f"- P1 benchmark execution unblocked: `{bool(status['p1_benchmark_execution_unblocked'])}`",
        f"- P0 release blocker: `{bool(status['p0_release_blocker'])}`",
        "- P1 work slice: `quality/fallback/benchmark breadth`",
        f"- Next action: `{status['next_action']}`",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for gate in status["gates"]:
        evidence = str(gate.get("summary_line", "") or gate.get("path", ""))
        lines.append(f"| {gate['label']} | `{gate['status']}` | {evidence} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize P1 benchmark breadth readiness.")
    parser.add_argument("--p1-readiness-status", type=Path)
    parser.add_argument(
        "--publication-evidence-index",
        type=Path,
        help="Release publication evidence index used when --p1-readiness-status is omitted.",
    )
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument(
        "--external-benchmark-submission-readiness",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    )
    parser.add_argument(
        "--external-benchmark-submission-updates",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    )
    parser.add_argument(
        "--residual-holdout-closure-updates",
        type=Path,
        default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    )
    parser.add_argument(
        "--benchmark-report",
        action="append",
        type=Path,
        dest="benchmark_reports",
        help="Benchmark evidence report. Repeat to override the default report set.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument(
        "--fail-core-open",
        action="store_true",
        help="Fail only when the P0 core evidence prerequisite is open.",
    )
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = build_status(
            p1_readiness_status=args.p1_readiness_status,
            publication_evidence_index=args.publication_evidence_index,
            commercial_readiness=args.commercial_readiness,
            external_benchmark_submission_readiness=args.external_benchmark_submission_readiness,
            external_benchmark_submission_updates=args.external_benchmark_submission_updates,
            residual_holdout_closure_updates=args.residual_holdout_closure_updates,
            benchmark_reports=args.benchmark_reports,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P1 benchmark breadth status check failed: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(status), encoding="utf-8")
    print(payload if args.json else _markdown(status))
    if args.fail_core_open and not bool(status["gates"][0]["p0_core_evidence_closed"]):
        return 1
    return 1 if args.fail_blocked and not bool(status["p1_benchmark_execution_unblocked"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
