#!/usr/bin/env python3
"""Render a release-safe summary report for the real drawing private corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from implementation.phase1.real_drawing_private_corpus_report_helper import (
    build_input_artifact_freshness_check,
    build_readiness_lanes,
    build_remaining_blocker_details,
    decorate_check_items,
    summarize_readiness,
)


REPORT_SCHEMA_VERSION = "real-drawing-private-corpus-report.v1"
DEFAULT_REDACTED_MANIFEST = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")
DEFAULT_INTAKE_QUEUE = Path("tmp/real_drawing_private_corpus/model_optimization_intake_queue.json")
DEFAULT_OUT_JSON = Path("tmp/real_drawing_private_corpus/real_drawing_private_corpus_report.json")
DEFAULT_OUT_MD = Path("tmp/real_drawing_private_corpus/real_drawing_private_corpus_report.md")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _coerce_bool(value: Any) -> bool:
    return bool(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _first_int(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in mapping:
            return _coerce_int(mapping.get(key))
    return 0


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique_values.append(text)
    return unique_values


def _check_item(
    *,
    check_id: str,
    category: str,
    status: str,
    accepted: bool,
    signals: dict[str, Any],
    remaining_blockers: list[str],
    tier_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check_id": check_id,
        "category": category,
        "status": status,
        "accepted": accepted,
        "signals": signals,
        "remaining_blockers": remaining_blockers,
    }
    if tier_id is not None:
        payload["tier_id"] = tier_id
    if label is not None:
        payload["label"] = label
    return payload


def _tier_check_item(
    *,
    tier_id: str,
    label: str,
    ready_count: int,
    route_name: str,
    status_label: str,
) -> dict[str, Any]:
    accepted = ready_count > 0
    return _check_item(
        check_id=f"{tier_id}_acceptance",
        category="tier_acceptance",
        status="pass" if accepted else "blocked",
        accepted=accepted,
        tier_id=tier_id,
        label=label,
        signals={
            "ready_count": ready_count,
            "route_name": route_name,
            "status_label": status_label,
        },
        remaining_blockers=[] if accepted else [f"{tier_id}_ready_missing"],
    )


def _blocker_item(
    *,
    blocker_id: str,
    status: str,
    owner: str,
    next_action: str,
    acceptance: str,
    evidence_target: str,
) -> dict[str, str]:
    return {
        "blocker_id": blocker_id,
        "status": status,
        "owner": owner,
        "next_action": next_action,
        "acceptance": acceptance,
        "evidence_target": evidence_target,
    }


def _manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = dict(_as_dict(manifest.get("summary")))
    policy = _as_dict(manifest.get("policy"))
    total_bytes = _coerce_int(summary.get("total_bytes", 0))
    payload = {
        **summary,
        "contract_pass": _coerce_bool(manifest.get("contract_pass", False)),
        "reason_code": str(manifest.get("reason_code", "") or ""),
        "raw_redistribution_allowed": _coerce_bool(policy.get("raw_redistribution_allowed", False)),
        "release_surface_allowed": _coerce_bool(policy.get("release_surface_allowed", False)),
        "storage_boundary": str(policy.get("storage_boundary", "") or ""),
        "license_basis": str(policy.get("license_basis", "") or ""),
        "total_mb": round(total_bytes / 1_000_000, 1) if total_bytes else 0.0,
    }
    return payload


def _queue_payload(queue: dict[str, Any]) -> dict[str, Any]:
    summary = dict(_as_dict(queue.get("summary")))
    status_counts = dict(sorted(_as_dict(summary.get("status_counts")).items()))
    route_counts = dict(sorted(_as_dict(summary.get("route_counts")).items()))
    payload = {
        **summary,
        "contract_pass": _coerce_bool(queue.get("contract_pass", False)),
        "reason_code": str(queue.get("reason_code", "") or ""),
        "status_counts": status_counts,
        "route_counts": route_counts,
    }
    return payload


def _build_report(
    *,
    redacted_manifest: Path,
    intake_queue: Path,
) -> dict[str, Any]:
    manifest = _load_json(redacted_manifest)
    queue = _load_json(intake_queue)
    if manifest.get("schema_version") != "real-drawing-redacted-corpus-manifest.v1":
        raise ValueError(f"unsupported redacted manifest schema: {redacted_manifest}")
    if queue.get("schema_version") != "real-drawing-model-optimization-intake-queue.v1":
        raise ValueError(f"unsupported intake queue schema: {intake_queue}")

    manifest_summary = _manifest_payload(manifest)
    queue_summary = _queue_payload(queue)
    status_counts = _as_dict(queue_summary.get("status_counts"))
    direct_mgt_ready_count = _coerce_int(
        queue_summary.get("direct_solver_graph_ready_count", status_counts.get("solver_graph_ready", 0))
    )
    queue_rows = [row for row in (queue.get("queue") or []) if isinstance(row, dict)]
    solver_exact_ready_count = sum(1 for row in queue_rows if row.get("solver_exact") is True)
    if not queue_rows:
        solver_exact_ready_count = _coerce_int(
            queue_summary.get("solver_exact_ready_count", queue_summary.get("solver_graph_ready_count", 0))
        )
    direct_mgt_solver_exact_count = sum(
        1
        for row in queue_rows
        if row.get("solver_exact") is True and row.get("optimization_route") == "midas_mgt_direct_parser"
    )
    if not queue_rows:
        direct_mgt_solver_exact_count = _coerce_int(
            queue_summary.get("direct_mgt_solver_exact_count", direct_mgt_ready_count)
        )
    mgt_hard_tier_ready_count = _coerce_int(queue_summary.get("mgt_hard_tier_ready_count", direct_mgt_ready_count))
    mgt_hard_tier_blocked_count = _coerce_int(queue_summary.get("mgt_hard_tier_blocked_count", 0))
    mgt_hard_tier_blocked_reason_counts = _as_dict(queue_summary.get("mgt_hard_tier_blocked_reason_counts"))
    ifc_proxy_graph_ready_count = _coerce_int(
        queue_summary.get("ifc_proxy_graph_ready_count", status_counts.get("ifc_proxy_graph_ready", 0))
    )
    archive_preview_ready_count = _coerce_int(
        queue_summary.get(
            "archive_decoded_preview_bridge_ready_count",
            status_counts.get("archive_decoded_preview_bridge_ready", 0),
        )
    )
    archive_hard_tier_ready_count = _coerce_int(queue_summary.get("archive_hard_tier_ready_count", 0))
    archive_hard_tier_blocked_count = _coerce_int(queue_summary.get("archive_hard_tier_blocked_count", 0))
    archive_exact_topology_candidate_count = _coerce_int(queue_summary.get("archive_exact_topology_candidate_count", 0))
    archive_verified_geometry_preview_count = _coerce_int(queue_summary.get("archive_verified_geometry_preview_count", 0))
    archive_hard_tier_blocked_reason_counts = _as_dict(
        queue_summary.get("archive_hard_tier_blocked_reason_counts")
    )
    archive_exact_candidate_blocked_reason_counts = {
        reason: int(count or 0)
        for reason, count in archive_hard_tier_blocked_reason_counts.items()
        if "EXACT_TOPOLOGY" in str(reason or "")
    }
    archive_exact_candidate_promotion_complete = (
        archive_exact_topology_candidate_count == 0
        or (
            archive_hard_tier_ready_count >= archive_exact_topology_candidate_count
            and sum(archive_exact_candidate_blocked_reason_counts.values()) == 0
        )
    )
    proxy_or_preview_ready_count = _coerce_int(
        queue_summary.get("proxy_or_preview_ready_count", ifc_proxy_graph_ready_count + archive_preview_ready_count)
    )
    ifc_adapter_required_count = _coerce_int(queue_summary.get("ifc_adapter_required_count", 0))
    archive_adapter_required_count = _coerce_int(queue_summary.get("archive_adapter_required_count", 0))

    raw_redistribution_allowed = _coerce_bool(manifest_summary.get("raw_redistribution_allowed"))
    release_surface_allowed = _coerce_bool(manifest_summary.get("release_surface_allowed"))
    release_surface_allowed_count = _coerce_int(manifest_summary.get("release_surface_allowed_count", 0))
    manifest_contract_pass = _coerce_bool(manifest_summary.get("contract_pass"))
    queue_contract_pass = _coerce_bool(queue_summary.get("contract_pass"))
    freshness_check = build_input_artifact_freshness_check(
        manifest_generated_at=manifest.get("generated_at", ""),
        queue_generated_at=queue.get("generated_at", ""),
    )

    candidate_count_match = _coerce_int(manifest_summary.get("model_optimization_candidate_count", 0)) == _coerce_int(
        queue_summary.get("candidate_file_count", 0)
    )
    model_asset_count_match = _coerce_int(manifest_summary.get("model_optimization_asset_count", 0)) == _coerce_int(
        queue_summary.get("candidate_model_asset_count", 0)
    )
    ready_tier_sum = (
        direct_mgt_ready_count
        + ifc_proxy_graph_ready_count
        + archive_preview_ready_count
        + archive_hard_tier_ready_count
    )
    ready_count_match = ready_tier_sum == _coerce_int(queue_summary.get("optimized_drawing_generation_ready_count", 0))
    lane_sum = ready_tier_sum + ifc_adapter_required_count + archive_adapter_required_count
    lane_sum_match = lane_sum == _coerce_int(queue_summary.get("candidate_file_count", 0))
    ready_asset_count_match = _coerce_int(
        queue_summary.get("optimized_drawing_generation_ready_model_asset_count", 0)
    ) <= _coerce_int(queue_summary.get("candidate_model_asset_count", 0))

    surface_safe = (not raw_redistribution_allowed) and (not release_surface_allowed) and release_surface_allowed_count == 0
    counts_consistent = candidate_count_match and model_asset_count_match and ready_count_match and lane_sum_match and ready_asset_count_match

    if not manifest_contract_pass:
        reason_code = "ERR_MANIFEST_CONTRACT_FAILED"
    elif not queue_contract_pass:
        reason_code = "ERR_QUEUE_CONTRACT_FAILED"
    elif not surface_safe:
        reason_code = "ERR_RELEASE_SURFACE_NOT_SAFE"
    elif not counts_consistent:
        reason_code = "ERR_REPORT_COUNT_MISMATCH"
    else:
        reason_code = "PASS"

    drawing_sheet_candidate_count = _coerce_int(manifest_summary.get("drawing_sheet_candidate_count", 0))
    model_asset_count = _coerce_int(queue_summary.get("candidate_model_asset_count", 0))
    hard_solver_graph_ready_count = _coerce_int(queue_summary.get("solver_graph_ready_count", direct_mgt_ready_count))

    summary = {
        "project_count": _coerce_int(manifest_summary.get("project_count", 0)),
        "file_count": _coerce_int(manifest_summary.get("file_count", 0)),
        "total_bytes": _coerce_int(manifest_summary.get("total_bytes", 0)),
        "total_mb": manifest_summary.get("total_mb", 0.0),
        "raw_redistribution_allowed_count": _coerce_int(manifest_summary.get("raw_redistribution_allowed_count", 0)),
        "release_surface_allowed_count": release_surface_allowed_count,
        "private_only": _coerce_bool(manifest_summary.get("private_only", False)),
        "drawing_sheet_candidate_count": drawing_sheet_candidate_count,
        "model_optimization_candidate_count": _coerce_int(manifest_summary.get("model_optimization_candidate_count", 0)),
        "model_asset_count": model_asset_count,
        "direct_mgt_ready_count": direct_mgt_ready_count,
        "direct_mgt_solver_exact_count": direct_mgt_solver_exact_count,
        "solver_exact_ready_count": solver_exact_ready_count,
        "mgt_hard_tier_ready_count": mgt_hard_tier_ready_count,
        "mgt_hard_tier_blocked_count": mgt_hard_tier_blocked_count,
        "archive_hard_tier_ready_count": archive_hard_tier_ready_count,
        "archive_hard_tier_blocked_count": archive_hard_tier_blocked_count,
        "archive_exact_topology_candidate_count": archive_exact_topology_candidate_count,
        "archive_verified_geometry_preview_count": archive_verified_geometry_preview_count,
        "ifc_proxy_graph_ready_count": ifc_proxy_graph_ready_count,
        "archive_decoded_preview_bridge_ready_count": archive_preview_ready_count,
        "proxy_or_preview_ready_count": proxy_or_preview_ready_count,
        "real_data_route_ready_count": _coerce_int(queue_summary.get("optimized_drawing_generation_ready_count", 0)),
        "hard_solver_graph_ready_count": hard_solver_graph_ready_count,
        "ifc_adapter_required_count": ifc_adapter_required_count,
        "archive_adapter_required_count": archive_adapter_required_count,
        "ready_model_asset_count": _coerce_int(queue_summary.get("optimized_drawing_generation_ready_model_asset_count", 0)),
        "ready_node_count_total": _coerce_int(queue_summary.get("ready_node_count_total", 0)),
        "ready_element_count_total": _coerce_int(queue_summary.get("ready_element_count_total", 0)),
        "ready_ifc_proxy_node_count_total": _coerce_int(queue_summary.get("ready_ifc_proxy_node_count_total", 0)),
        "ready_ifc_proxy_edge_count_total": _coerce_int(queue_summary.get("ready_ifc_proxy_edge_count_total", 0)),
        "eb_rh_external_validation_status": "pending",
        "l3_claim_state": "maintained",
        "readiness_tier_note": "hard solver graph count is derived from queue rows with solver_exact=true; IFC rows are proxy graphs and archive preview rows are not hard tier unless promoted.",
    }

    report_blockers: list[str] = []
    if not manifest_contract_pass:
        report_blockers.append("manifest_contract_failed")
    if not queue_contract_pass:
        report_blockers.append("queue_contract_failed")
    if not surface_safe:
        report_blockers.append("release_surface_not_safe")
    if not counts_consistent:
        report_blockers.append("report_count_mismatch")

    tier_acceptance = [
        _tier_check_item(
            tier_id="direct_mgt",
            label="hard solver graph ready",
            ready_count=mgt_hard_tier_ready_count,
            route_name="midas_mgt_direct_parser",
            status_label="solver_graph_ready",
        ),
        _tier_check_item(
            tier_id="ifc_proxy_graph",
            label="IFC proxy graph ready",
            ready_count=ifc_proxy_graph_ready_count,
            route_name="ifc_to_structural_graph_adapter",
            status_label="ifc_proxy_graph_ready",
        ),
        _tier_check_item(
            tier_id="archive_preview_bridge",
            label="Archive preview bridge ready",
            ready_count=archive_preview_ready_count,
            route_name="midas_binary_decoded_preview_bridge",
            status_label="archive_decoded_preview_bridge_ready",
        ),
    ]

    release_surface_check = _check_item(
        check_id="release_surface_redaction",
        category="policy_gate",
        status="pass" if surface_safe else "blocked",
        accepted=surface_safe,
        signals={
            "raw_redistribution_allowed": raw_redistribution_allowed,
            "release_surface_allowed": release_surface_allowed,
            "release_surface_allowed_count": release_surface_allowed_count,
            "private_only": _coerce_bool(manifest_summary.get("private_only", False)),
        },
        remaining_blockers=[] if surface_safe else ["release_surface_not_safe"],
    )

    report_contract_check = _check_item(
        check_id="report_contract",
        category="contract",
        status="pass" if reason_code == "PASS" else "blocked",
        accepted=reason_code == "PASS",
        signals={
            "manifest_contract_pass": manifest_contract_pass,
            "queue_contract_pass": queue_contract_pass,
            "surface_safe": surface_safe,
            "counts_consistent": counts_consistent,
            "reason_code": reason_code,
        },
        remaining_blockers=report_blockers,
    )

    external_validation_status = str(summary.get("eb_rh_external_validation_status", "") or "").strip().lower()
    external_validation_check = _check_item(
        check_id="eb_rh_external_validation_hold",
        category="external_validation",
        status="pending" if external_validation_status == "pending" else "pass",
        accepted=external_validation_status != "pending",
        signals={
            "eb_rh_external_validation_status": summary.get("eb_rh_external_validation_status", ""),
        },
        remaining_blockers=["eb_rh_external_validation_hold"] if external_validation_status == "pending" else [],
    )

    ifc_hard_tier_check = _check_item(
        check_id="ifc_solver_exact_hard_tier",
        category="hard_solver_guard",
        status="blocked" if ifc_proxy_graph_ready_count > 0 else "pass",
        accepted=ifc_proxy_graph_ready_count == 0,
        signals={
            "ifc_proxy_graph_ready_count": ifc_proxy_graph_ready_count,
            "ifc_solver_exact_ready_count": 0,
        },
        remaining_blockers=(
            ["ifc_geometry_material_load_solver_exact_adapter_required"]
            if ifc_proxy_graph_ready_count > 0
            else []
        ),
    )
    mgt_hard_tier_check = _check_item(
        check_id="mgt_direct_solver_exact_hard_tier",
        category="hard_solver_guard",
        status="blocked" if mgt_hard_tier_blocked_count > 0 else "pass",
        accepted=mgt_hard_tier_blocked_count == 0,
        signals={
            "direct_mgt_ready_count": direct_mgt_ready_count,
            "mgt_hard_tier_ready_count": mgt_hard_tier_ready_count,
            "mgt_hard_tier_blocked_count": mgt_hard_tier_blocked_count,
            "blocked_reason_counts": mgt_hard_tier_blocked_reason_counts,
        },
        remaining_blockers=(
            ["mgt_direct_solver_exact_artifact_or_load_binding_required"]
            if mgt_hard_tier_blocked_count > 0
            else []
        ),
    )
    archive_hard_tier_check = _check_item(
        check_id="archive_native_solver_exact_hard_tier",
        category="hard_solver_guard",
        status="pass" if archive_exact_candidate_promotion_complete else "blocked",
        accepted=archive_exact_candidate_promotion_complete,
        signals={
            "archive_preview_ready_count": archive_preview_ready_count,
            "archive_hard_tier_ready_count": archive_hard_tier_ready_count,
            "archive_hard_tier_blocked_count": archive_hard_tier_blocked_count,
            "archive_exact_topology_candidate_count": archive_exact_topology_candidate_count,
            "archive_verified_geometry_preview_count": archive_verified_geometry_preview_count,
            "blocked_reason_counts": archive_hard_tier_blocked_reason_counts,
            "exact_candidate_blocked_reason_counts": archive_exact_candidate_blocked_reason_counts,
            "exact_candidate_promotion_complete": archive_exact_candidate_promotion_complete,
        },
        remaining_blockers=(
            ["archive_native_solver_topology_promotion_required"]
            if not archive_exact_candidate_promotion_complete
            else []
        ),
    )

    evidence_checklist = [
        report_contract_check,
        freshness_check,
        release_surface_check,
        *tier_acceptance,
        mgt_hard_tier_check,
        ifc_hard_tier_check,
        archive_hard_tier_check,
        external_validation_check,
    ]
    evidence_checklist = decorate_check_items(evidence_checklist)
    tier_acceptance = [row for row in evidence_checklist if str(row.get("category", "") or "") == "tier_acceptance"]
    mgt_hard_tier_check = next(
        (row for row in evidence_checklist if str(row.get("check_id", "") or "") == "mgt_direct_solver_exact_hard_tier"),
        mgt_hard_tier_check,
    )
    ifc_hard_tier_check = next(
        (row for row in evidence_checklist if str(row.get("check_id", "") or "") == "ifc_solver_exact_hard_tier"),
        ifc_hard_tier_check,
    )
    archive_hard_tier_check = next(
        (
            row
            for row in evidence_checklist
            if str(row.get("check_id", "") or "") == "archive_native_solver_exact_hard_tier"
        ),
        archive_hard_tier_check,
    )
    external_validation_check = next(
        (
            row
            for row in evidence_checklist
            if str(row.get("check_id", "") or "") == "eb_rh_external_validation_hold"
        ),
        external_validation_check,
    )
    report_contract_check = next(
        (row for row in evidence_checklist if str(row.get("check_id", "") or "") == "report_contract"),
        report_contract_check,
    )
    freshness_check = next(
        (row for row in evidence_checklist if str(row.get("check_id", "") or "") == "input_artifact_freshness"),
        freshness_check,
    )
    release_surface_check = next(
        (row for row in evidence_checklist if str(row.get("check_id", "") or "") == "release_surface_redaction"),
        release_surface_check,
    )

    remaining_blockers = _unique_strings(
        [
            blocker
            for item in evidence_checklist
            for blocker in item.get("remaining_blockers", [])
        ]
    )
    blocker_register = [
        _blocker_item(
            blocker_id="ifc_geometry_material_load_solver_exact_adapter_required",
            status="blocked",
            owner="hard_implementation",
            next_action="Implement IFC placement/geometry/material/section/load extraction that emits solver graph JSON/NPZ rather than entity proxy graphs.",
            acceptance="IFC rows can be promoted to solver_exact=true with nonempty nodes/elements and proxy-only notes removed.",
            evidence_target="IFC solver graph adapter report and intake queue rows",
        ),
        _blocker_item(
            blocker_id="archive_native_solver_topology_promotion_required",
            status="blocked",
            owner="hard_implementation",
            next_action="Materialize full native topology from MIDAS archive payloads and set exact_topology_promoted=true only after topology counts and member references are resolved.",
            acceptance="Archive rows can be promoted to archive_solver_graph_ready with solver_exact=true and PASS_ARCHIVE_EXACT_TOPOLOGY_PROMOTED.",
            evidence_target="midas_archive_adapter_report.json and model_optimization_intake_queue.json",
        ),
        _blocker_item(
            blocker_id="eb_rh_external_validation_hold",
            status="pending_user_skipped",
            owner="external_validation",
            next_action="Attach EB receipts and RH closure packets when external validation is resumed.",
            acceptance="EB receipt rows are attached and RH holdout closure evidence is complete.",
            evidence_target="external benchmark and residual holdout evidence sidecars",
        ),
    ]
    blocker_register = [row for row in blocker_register if row["blocker_id"] in remaining_blockers]
    readiness_lanes = build_readiness_lanes(evidence_checklist)
    remaining_blocker_details = build_remaining_blocker_details(evidence_checklist, remaining_blockers)
    readiness_summary = summarize_readiness(
        check_items=evidence_checklist,
        readiness_lanes=readiness_lanes,
        input_artifact_freshness=freshness_check,
    )

    tier_acceptance_pass_count = sum(1 for item in tier_acceptance if _coerce_bool(item.get("accepted")))
    evidence_checklist_pass_count = sum(1 for item in evidence_checklist if _coerce_bool(item.get("accepted")))
    evidence_checklist_pending_count = sum(1 for item in evidence_checklist if str(item.get("status", "") or "").lower() == "pending")
    evidence_checklist_blocked_count = sum(1 for item in evidence_checklist if str(item.get("status", "") or "").lower() == "blocked")

    summary.update(
        {
            "tier_acceptance": tier_acceptance,
            "tier_count": len(tier_acceptance),
            "tier_acceptance_pass_count": tier_acceptance_pass_count,
            "tier_acceptance_all_pass": tier_acceptance_pass_count == len(tier_acceptance),
            "evidence_checklist": evidence_checklist,
            "evidence_checklist_count": len(evidence_checklist),
            "evidence_checklist_pass_count": evidence_checklist_pass_count,
            "evidence_checklist_pending_count": evidence_checklist_pending_count,
            "evidence_checklist_blocked_count": evidence_checklist_blocked_count,
            "remaining_blockers": remaining_blockers,
            "remaining_blocker_count": len(remaining_blockers),
            "blocker_register": blocker_register,
            "blocker_register_count": len(blocker_register),
            "remaining_blocker_details": remaining_blocker_details,
            "readiness_lanes": readiness_lanes,
            "readiness_lane_count": len(readiness_lanes),
            "readiness_state": readiness_summary.get("readiness_state", "pending"),
            "readiness_lane_state_counts": readiness_summary.get("readiness_lane_state_counts", {}),
            "evidence_checklist_state_counts": readiness_summary.get("evidence_checklist_state_counts", {}),
            "readiness_summary_line": readiness_summary.get("readiness_summary_line", ""),
            "input_artifact_freshness": freshness_check,
            "input_artifact_freshness_status": readiness_summary.get("input_artifact_freshness_status", "pending"),
            "input_artifact_freshness_skew_seconds": readiness_summary.get("input_artifact_freshness_skew_seconds", -1),
            "stale_artifact_detected": readiness_summary.get("stale_artifact_detected", False),
        }
    )

    consistency = {
        "manifest_contract_pass": manifest_contract_pass,
        "queue_contract_pass": queue_contract_pass,
        "release_surface_allowed_false": not release_surface_allowed,
        "raw_redistribution_allowed_false": not raw_redistribution_allowed,
        "release_surface_allowed_count_zero": release_surface_allowed_count == 0,
        "tier_acceptance_all_pass": tier_acceptance_pass_count == len(tier_acceptance),
        "remaining_blocker_count": len(remaining_blockers),
        "candidate_count_match": candidate_count_match,
        "model_asset_count_match": model_asset_count_match,
        "ready_count_match": ready_count_match,
        "ready_asset_count_match": ready_asset_count_match,
        "lane_sum_match": lane_sum_match,
        "surface_safe": surface_safe,
        "counts_consistent": counts_consistent,
        "input_artifact_freshness_pass": freshness_check.get("status") == "pass",
        "input_artifact_freshness_pending": freshness_check.get("status") == "pending",
        "input_artifact_freshness_blocked": freshness_check.get("status") == "blocked",
        "input_artifact_freshness_skew_seconds": _coerce_int(_as_dict(freshness_check.get("signals")).get("generated_at_skew_seconds", -1)),
        "stale_artifact_detected": freshness_check.get("status") == "blocked",
    }

    surface_notes = [
        "private raw 금지",
        "release_surface_allowed=0",
        "EB/RH 외부 검증 보류",
        "L3 claim 유지",
        f"real-data route ready count={summary['real_data_route_ready_count']}",
    ]

    queue_breakdown = {
        "direct_mgt_ready_count": direct_mgt_ready_count,
        "mgt_hard_tier_ready_count": mgt_hard_tier_ready_count,
        "mgt_hard_tier_blocked_count": mgt_hard_tier_blocked_count,
        "hard_solver_graph_ready_count": hard_solver_graph_ready_count,
        "ifc_proxy_graph_ready_count": ifc_proxy_graph_ready_count,
        "archive_decoded_preview_bridge_ready_count": archive_preview_ready_count,
        "archive_hard_tier_ready_count": archive_hard_tier_ready_count,
        "archive_hard_tier_blocked_count": archive_hard_tier_blocked_count,
        "archive_exact_topology_candidate_count": archive_exact_topology_candidate_count,
        "archive_verified_geometry_preview_count": archive_verified_geometry_preview_count,
        "proxy_or_preview_ready_count": proxy_or_preview_ready_count,
        "ifc_adapter_required_count": ifc_adapter_required_count,
        "archive_adapter_required_count": archive_adapter_required_count,
        "model_asset_count": model_asset_count,
        "drawing_sheet_candidate_count": drawing_sheet_candidate_count,
    }

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_redacted_manifest": str(redacted_manifest),
        "source_intake_queue": str(intake_queue),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "manifest_summary": manifest_summary,
        "queue_summary": queue_summary,
        "summary": summary,
        "queue_breakdown": queue_breakdown,
        "consistency": consistency,
        "surface_notes": surface_notes,
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    queue_breakdown = _as_dict(report.get("queue_breakdown"))
    consistency = _as_dict(report.get("consistency"))

    def _signals_text(item: dict[str, Any]) -> str:
        signals = _as_dict(item.get("signals"))
        if not signals:
            return "n/a"
        return "; ".join(f"{key}={signals.get(key)}" for key in signals)

    def _count_text(mapping: dict[str, Any]) -> str:
        counts = _as_dict(mapping)
        return ", ".join(
            f"{key}={_coerce_int(counts.get(key, 0))}"
            for key in ("all-pass", "blocked", "pending")
        )

    tier_acceptance = [row for row in (summary.get("tier_acceptance") or []) if isinstance(row, dict)]
    evidence_checklist = [row for row in (summary.get("evidence_checklist") or []) if isinstance(row, dict)]
    readiness_lanes = [row for row in (summary.get("readiness_lanes") or []) if isinstance(row, dict)]
    remaining_blocker_details = [row for row in (summary.get("remaining_blocker_details") or []) if isinstance(row, dict)]
    blocker_register = [row for row in (summary.get("blocker_register") or []) if isinstance(row, dict)]
    tier_acceptance_rows = [
        f"| `{row.get('tier_id', '')}` / {row.get('label', '')} | {str(row.get('readiness_state', '') or '')} | {str(row.get('status', '') or '')} | "
        f"{str(row.get('exactness_policy', '') or 'n/a')} | {str(row.get('owner', '') or 'n/a')} | "
        f"{str(row.get('next_action', '') or 'n/a')} | {int(_as_dict(row.get('signals')).get('ready_count', 0) or 0)} | "
        f"{str(_as_dict(row.get('signals')).get('route_name', '') or '')} / {str(_as_dict(row.get('signals')).get('status_label', '') or '')} | "
        f"{', '.join(str(blocker) for blocker in row.get('remaining_blockers', []) if str(blocker).strip()) or 'none'} |"
        for row in tier_acceptance
    ]
    evidence_checklist_rows = [
        f"| `{row.get('check_id', '')}` | {str(row.get('readiness_state', '') or '')} | {str(row.get('status', '') or '')} | "
        f"{str(row.get('exactness_policy', '') or 'n/a')} | {str(row.get('owner', '') or 'n/a')} | "
        f"{str(row.get('next_action', '') or 'n/a')} | {_signals_text(row)} | "
        f"{', '.join(str(blocker) for blocker in row.get('remaining_blockers', []) if str(blocker).strip()) or 'none'} |"
        for row in evidence_checklist
    ]
    readiness_lane_rows = [
        f"| `{row.get('lane_id', '')}` / {row.get('label', '')} | {str(row.get('readiness_state', '') or '')} | "
        f"{str(row.get('exactness_policy', '') or 'n/a')} | {str(row.get('owner', '') or 'n/a')} | "
        f"{str(row.get('next_action', '') or 'n/a')} | "
        f"{', '.join(str(blocker) for blocker in row.get('remaining_blockers', []) if str(blocker).strip()) or 'none'} |"
        for row in readiness_lanes
    ] or ["| none |"]
    remaining_blocker_rows = [
        f"| `{row.get('blocker', '')}` | {str(row.get('state', '') or '')} | "
        f"{str(row.get('owner', '') or 'n/a')} | {str(row.get('next_action', '') or 'n/a')} |"
        for row in remaining_blocker_details
    ] or ["| none |  |  |  |"]
    blocker_register_rows = [
        f"| `{row.get('blocker_id', '')}` | {str(row.get('status', '') or '')} | "
        f"{str(row.get('owner', '') or 'n/a')} | {str(row.get('next_action', '') or 'n/a')} | "
        f"{str(row.get('acceptance', '') or 'n/a')} | {str(row.get('evidence_target', '') or 'n/a')} |"
        for row in blocker_register
    ] or ["| none |  |  |  |  |  |"]
    lines = [
        "# Real Drawing Private Corpus Report",
        "",
        f"- `contract_pass`: `{_bool_text(report.get('contract_pass'))}`",
        f"- `reason_code`: `{report.get('reason_code', '')}`",
        f"- `readiness_state`: `{summary.get('readiness_state', '')}`",
        f"- `readiness_summary_line`: `{summary.get('readiness_summary_line', '')}`",
        f"- `readiness_lane_state_counts`: `{_count_text(summary.get('readiness_lane_state_counts', {}))}`",
        f"- `evidence_checklist_state_counts`: `{_count_text(summary.get('evidence_checklist_state_counts', {}))}`",
        f"- `input_artifact_freshness_status`: `{summary.get('input_artifact_freshness_status', '')}`",
        f"- `input_artifact_freshness_skew_seconds`: `{summary.get('input_artifact_freshness_skew_seconds', -1)}`",
        f"- `stale_artifact_detected`: `{_bool_text(summary.get('stale_artifact_detected', False))}`",
        f"- `source_redacted_manifest`: `{report.get('source_redacted_manifest', '')}`",
        f"- `source_intake_queue`: `{report.get('source_intake_queue', '')}`",
        f"- `private raw 금지`: `{_bool_text(summary.get('private_only', False))}`",
        f"- `release_surface_allowed=0`: `{_bool_text(summary.get('release_surface_allowed_count', 0) == 0)}`",
        f"- `EB/RH 외부 검증 보류`: `{summary.get('eb_rh_external_validation_status', '')}`",
        f"- `L3 claim 유지`: `{summary.get('l3_claim_state', '')}`",
        f"- `real-data route ready count`: `{summary.get('real_data_route_ready_count', 0)}`",
        "",
        "## Readiness Lanes",
        "",
        "| Lane | Readiness | Policy | Owner | Next action | Blockers |",
        "|---|---|---|---|---|---|",
        *readiness_lane_rows,
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| project_count | {summary.get('project_count', 0)} |",
        f"| file_count | {summary.get('file_count', 0)} |",
        f"| total_mb | {summary.get('total_mb', 0)} |",
        f"| drawing_sheet_candidate_count | {summary.get('drawing_sheet_candidate_count', 0)} |",
        f"| model_optimization_candidate_count | {summary.get('model_optimization_candidate_count', 0)} |",
        f"| model_asset_count | {summary.get('model_asset_count', 0)} |",
        f"| readiness_state | {summary.get('readiness_state', '')} |",
        f"| readiness_lane_count | {summary.get('readiness_lane_count', 0)} |",
        f"| readiness_lane_state_counts | {_count_text(summary.get('readiness_lane_state_counts', {}))} |",
        f"| evidence_checklist_state_counts | {_count_text(summary.get('evidence_checklist_state_counts', {}))} |",
        f"| input_artifact_freshness_status | {summary.get('input_artifact_freshness_status', '')} |",
        f"| input_artifact_freshness_skew_seconds | {summary.get('input_artifact_freshness_skew_seconds', -1)} |",
        f"| stale_artifact_detected | {_bool_text(summary.get('stale_artifact_detected', False))} |",
        f"| direct_mgt_ready_count | {summary.get('direct_mgt_ready_count', 0)} |",
        f"| mgt_hard_tier_ready_count | {summary.get('mgt_hard_tier_ready_count', 0)} |",
        f"| mgt_hard_tier_blocked_count | {summary.get('mgt_hard_tier_blocked_count', 0)} |",
        f"| hard_solver_graph_ready_count | {summary.get('hard_solver_graph_ready_count', 0)} |",
        f"| ifc_proxy_graph_ready_count | {summary.get('ifc_proxy_graph_ready_count', 0)} |",
        f"| archive_decoded_preview_bridge_ready_count | {summary.get('archive_decoded_preview_bridge_ready_count', 0)} |",
        f"| archive_hard_tier_ready_count | {summary.get('archive_hard_tier_ready_count', 0)} |",
        f"| archive_hard_tier_blocked_count | {summary.get('archive_hard_tier_blocked_count', 0)} |",
        f"| archive_exact_topology_candidate_count | {summary.get('archive_exact_topology_candidate_count', 0)} |",
        f"| archive_verified_geometry_preview_count | {summary.get('archive_verified_geometry_preview_count', 0)} |",
        f"| proxy_or_preview_ready_count | {summary.get('proxy_or_preview_ready_count', 0)} |",
        f"| real_data_route_ready_count | {summary.get('real_data_route_ready_count', 0)} |",
        f"| ifc_adapter_required_count | {summary.get('ifc_adapter_required_count', 0)} |",
        f"| archive_adapter_required_count | {summary.get('archive_adapter_required_count', 0)} |",
        f"| ready_model_asset_count | {summary.get('ready_model_asset_count', 0)} |",
        f"| release_surface_allowed_count | {summary.get('release_surface_allowed_count', 0)} |",
        f"| tier_count | {summary.get('tier_count', 0)} |",
        f"| tier_acceptance_pass_count | {summary.get('tier_acceptance_pass_count', 0)} |",
        f"| tier_acceptance_all_pass | {_bool_text(summary.get('tier_acceptance_all_pass'))} |",
        f"| evidence_checklist_count | {summary.get('evidence_checklist_count', 0)} |",
        f"| evidence_checklist_pass_count | {summary.get('evidence_checklist_pass_count', 0)} |",
        f"| evidence_checklist_pending_count | {summary.get('evidence_checklist_pending_count', 0)} |",
        f"| evidence_checklist_blocked_count | {summary.get('evidence_checklist_blocked_count', 0)} |",
        f"| remaining_blocker_count | {summary.get('remaining_blocker_count', 0)} |",
        f"| blocker_register_count | {summary.get('blocker_register_count', 0)} |",
        "",
        "## Queue Breakdown",
        "",
        "| Lane | Count | Route / State |",
        "|---|---:|---|",
        f"| Direct MGT ready | {queue_breakdown.get('direct_mgt_ready_count', 0)} | `midas_mgt_direct_parser` / solver graph ready |",
        f"| MGT hard tier ready | {queue_breakdown.get('mgt_hard_tier_ready_count', 0)} | direct parser exactness guard |",
        f"| Hard solver graph ready | {queue_breakdown.get('hard_solver_graph_ready_count', 0)} | solver-exact tier only |",
        f"| IFC proxy graph ready | {queue_breakdown.get('ifc_proxy_graph_ready_count', 0)} | `ifc_to_structural_graph_adapter` / not solver-exact |",
        f"| Archive preview bridge ready | {queue_breakdown.get('archive_decoded_preview_bridge_ready_count', 0)} | `midas_binary_decoded_preview_bridge` / not solver-exact |",
        f"| Archive hard tier ready | {queue_breakdown.get('archive_hard_tier_ready_count', 0)} | promoted exact topology only |",
        f"| Archive hard tier blocked | {queue_breakdown.get('archive_hard_tier_blocked_count', 0)} | preview/candidate not promoted |",
        f"| Proxy or preview ready | {queue_breakdown.get('proxy_or_preview_ready_count', 0)} | soft intake-ready tier |",
        f"| IFC adapter required | {queue_breakdown.get('ifc_adapter_required_count', 0)} | remaining adapter pending |",
        f"| Archive adapter required | {queue_breakdown.get('archive_adapter_required_count', 0)} | remaining adapter pending |",
        f"| Model assets | {queue_breakdown.get('model_asset_count', 0)} | corpus-level total |",
        f"| Drawing sheets | {queue_breakdown.get('drawing_sheet_candidate_count', 0)} | manifest-level candidates |",
        "",
        "## Policy",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| raw_redistribution_allowed | {_bool_text(_as_dict(report.get('manifest_summary')).get('raw_redistribution_allowed', False))} |",
        f"| release_surface_allowed | {_bool_text(_as_dict(report.get('manifest_summary')).get('release_surface_allowed', False))} |",
        f"| storage_boundary | `{_as_dict(report.get('manifest_summary')).get('storage_boundary', '')}` |",
        "",
        "## Tier Acceptance",
        "",
        "| Tier | Readiness | Status | Policy | Owner | Next action | Ready | Route / State | Blockers |",
        "|---|---|---|---|---|---|---:|---|---|",
        *tier_acceptance_rows,
        "",
        "## Evidence Checklist",
        "",
        "| Check | Readiness | Status | Policy | Owner | Next action | Signals | Blockers |",
        "|---|---|---|---|---|---|---|---|",
        *evidence_checklist_rows,
        "",
        "## Remaining Blockers",
        "",
        "| Blocker | State | Owner | Next action |",
        "|---|---|---|---|",
        *remaining_blocker_rows,
        "",
        "## Blocker Register",
        "",
        "| Blocker | Status | Owner | Next action | Acceptance | Evidence target |",
        "|---|---|---|---|---|---|",
        *blocker_register_rows,
        "",
        "## Consistency",
        "",
        "| Check | Value |",
        "|---|---|",
        f"| manifest_contract_pass | {_bool_text(consistency.get('manifest_contract_pass'))} |",
        f"| queue_contract_pass | {_bool_text(consistency.get('queue_contract_pass'))} |",
        f"| release_surface_allowed_count_zero | {_bool_text(consistency.get('release_surface_allowed_count_zero'))} |",
        f"| candidate_count_match | {_bool_text(consistency.get('candidate_count_match'))} |",
        f"| model_asset_count_match | {_bool_text(consistency.get('model_asset_count_match'))} |",
        f"| ready_count_match | {_bool_text(consistency.get('ready_count_match'))} |",
        f"| ready_asset_count_match | {_bool_text(consistency.get('ready_asset_count_match'))} |",
        f"| lane_sum_match | {_bool_text(consistency.get('lane_sum_match'))} |",
        f"| input_artifact_freshness_pass | {_bool_text(consistency.get('input_artifact_freshness_pass'))} |",
        f"| input_artifact_freshness_pending | {_bool_text(consistency.get('input_artifact_freshness_pending'))} |",
        f"| input_artifact_freshness_blocked | {_bool_text(consistency.get('input_artifact_freshness_blocked'))} |",
        f"| input_artifact_freshness_skew_seconds | {consistency.get('input_artifact_freshness_skew_seconds', -1)} |",
        f"| stale_artifact_detected | {_bool_text(consistency.get('stale_artifact_detected'))} |",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redacted-manifest", type=Path, default=DEFAULT_REDACTED_MANIFEST)
    parser.add_argument("--intake-queue", type=Path, default=DEFAULT_INTAKE_QUEUE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = _build_report(redacted_manifest=args.redacted_manifest, intake_queue=args.intake_queue)
    _write_json(args.out, report)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_markdown(report))
    return 0 if bool(report.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
