from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


READINESS_STATE_ALL_PASS = "all-pass"
READINESS_STATE_BLOCKED = "blocked"
READINESS_STATE_PENDING = "pending"
FRESHNESS_THRESHOLD_SECONDS = 300


CHECK_METADATA: dict[str, dict[str, str]] = {
    "report_contract": {
        "owner": "report_builder",
        "next_action": "repair manifest/queue contract issues and regenerate the report",
        "exactness_policy": "metadata_consistency",
        "readiness_lane_id": "governance",
        "label": "Report contract",
    },
    "input_artifact_freshness": {
        "owner": "report_publisher",
        "next_action": "regenerate manifest and queue from the same generation wave before publishing",
        "exactness_policy": "freshness_guard",
        "readiness_lane_id": "governance",
        "label": "Input artifact freshness",
    },
    "release_surface_redaction": {
        "owner": "release_surface_policy_owner",
        "next_action": "keep raw redistribution blocked and leave release_surface_allowed_count at zero",
        "exactness_policy": "release_surface_guard",
        "readiness_lane_id": "policy",
        "label": "Release surface redaction",
    },
    "direct_mgt_acceptance": {
        "owner": "mgt_direct_parser_owner",
        "next_action": "keep direct MGT parser green",
        "exactness_policy": "solver_exact",
        "readiness_lane_id": "direct_mgt",
        "label": "Direct MGT acceptance",
    },
    "ifc_proxy_graph_acceptance": {
        "owner": "ifc_adapter_owner",
        "next_action": "keep IFC proxy graph intake-ready; solver-exact promotion remains separate",
        "exactness_policy": "proxy_graph",
        "readiness_lane_id": "ifc_proxy_graph",
        "label": "IFC proxy graph acceptance",
    },
    "archive_preview_bridge_acceptance": {
        "owner": "archive_adapter_owner",
        "next_action": "keep archive preview bridge intake-ready; exact topology promotion remains separate",
        "exactness_policy": "decoded_preview",
        "readiness_lane_id": "archive_preview_bridge",
        "label": "Archive preview bridge acceptance",
    },
    "mgt_direct_solver_exact_hard_tier": {
        "owner": "mgt_direct_parser_owner",
        "next_action": "stabilize direct MGT parser exactness and binding artifacts",
        "exactness_policy": "solver_exact",
        "readiness_lane_id": "mgt_direct_solver_exact_hard_tier",
        "label": "MGT direct solver exact hard tier",
    },
    "ifc_solver_exact_hard_tier": {
        "owner": "ifc_adapter_owner",
        "next_action": "promote IFC proxy rows to solver-exact adapter output",
        "exactness_policy": "solver_exact",
        "readiness_lane_id": "ifc_solver_exact_hard_tier",
        "label": "IFC solver exact hard tier",
    },
    "archive_native_solver_exact_hard_tier": {
        "owner": "archive_adapter_owner",
        "next_action": "promote archive preview bridges to exact topology",
        "exactness_policy": "solver_exact",
        "readiness_lane_id": "archive_native_solver_exact_hard_tier",
        "label": "Archive native solver exact hard tier",
    },
    "eb_rh_external_validation_hold": {
        "owner": "eb_rh_validation_owner",
        "next_action": "wait for EB/RH external validation to clear the hold",
        "exactness_policy": "external_validation_hold",
        "readiness_lane_id": "eb_rh_external_validation",
        "label": "EB/RH external validation hold",
    },
}


BLOCKER_METADATA: dict[str, dict[str, str]] = {
    "manifest_contract_failed": {
        "owner": "report_builder",
        "next_action": "repair redacted manifest schema or summary before publishing",
        "state": READINESS_STATE_BLOCKED,
    },
    "queue_contract_failed": {
        "owner": "report_builder",
        "next_action": "repair intake queue schema or summary before publishing",
        "state": READINESS_STATE_BLOCKED,
    },
    "release_surface_not_safe": {
        "owner": "release_surface_policy_owner",
        "next_action": "keep raw redistribution blocked and maintain release_surface_allowed_count at zero",
        "state": READINESS_STATE_BLOCKED,
    },
    "report_count_mismatch": {
        "owner": "report_builder",
        "next_action": "regenerate manifest and queue from the same counts wave",
        "state": READINESS_STATE_BLOCKED,
    },
    "mgt_direct_solver_exact_artifact_or_load_binding_required": {
        "owner": "mgt_direct_parser_owner",
        "next_action": "stabilize direct MGT parser exactness and load binding artifacts",
        "state": READINESS_STATE_BLOCKED,
    },
    "input_artifact_freshness_unverified": {
        "owner": "report_publisher",
        "next_action": "ensure both input artifacts publish generated_at timestamps",
        "state": READINESS_STATE_PENDING,
    },
    "stale_artifact_generation_wave_mismatch": {
        "owner": "report_publisher",
        "next_action": "regenerate manifest and queue from the same generation wave before publishing",
        "state": READINESS_STATE_BLOCKED,
    },
    "ifc_geometry_material_load_solver_exact_adapter_required": {
        "owner": "ifc_adapter_owner",
        "next_action": "promote IFC proxy rows to solver-exact adapter output",
        "state": READINESS_STATE_BLOCKED,
    },
    "archive_native_solver_topology_promotion_required": {
        "owner": "archive_adapter_owner",
        "next_action": "promote archive preview bridges to exact topology",
        "state": READINESS_STATE_BLOCKED,
    },
    "eb_rh_external_validation_hold": {
        "owner": "eb_rh_validation_owner",
        "next_action": "wait for EB/RH external validation to clear the hold",
        "state": READINESS_STATE_PENDING,
    },
}


LANE_CHECK_IDS = [
    "direct_mgt_acceptance",
    "ifc_proxy_graph_acceptance",
    "archive_preview_bridge_acceptance",
    "mgt_direct_solver_exact_hard_tier",
    "ifc_solver_exact_hard_tier",
    "archive_native_solver_exact_hard_tier",
    "eb_rh_external_validation_hold",
]


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _state_from_status(status: Any) -> str:
    text = str(status or "").strip().lower()
    if text == "pass":
        return READINESS_STATE_ALL_PASS
    if text in {READINESS_STATE_BLOCKED, READINESS_STATE_PENDING}:
        return text
    return READINESS_STATE_PENDING


def _parse_generated_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _counts_text(counts: dict[str, int]) -> str:
    ordered_keys = (READINESS_STATE_ALL_PASS, READINESS_STATE_BLOCKED, READINESS_STATE_PENDING)
    return ", ".join(f"{key}={int(counts.get(key, 0))}" for key in ordered_keys)


def _decorate_check_item(item: dict[str, Any]) -> dict[str, Any]:
    check_id = str(item.get("check_id", "") or "")
    meta = CHECK_METADATA.get(check_id, {})
    payload = dict(item)
    payload.setdefault("owner", meta.get("owner", ""))
    payload.setdefault("next_action", meta.get("next_action", ""))
    payload.setdefault("exactness_policy", meta.get("exactness_policy", "n/a"))
    lane_id = meta.get("readiness_lane_id", check_id)
    if lane_id:
        payload.setdefault("readiness_lane_id", lane_id)
    payload["readiness_state"] = _state_from_status(payload.get("status"))
    if "label" not in payload and meta.get("label"):
        payload["label"] = meta["label"]
    return payload


def decorate_check_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_decorate_check_item(item) for item in items if isinstance(item, dict)]


def build_input_artifact_freshness_check(*, manifest_generated_at: Any, queue_generated_at: Any) -> dict[str, Any]:
    manifest_ts = _parse_generated_at(manifest_generated_at)
    queue_ts = _parse_generated_at(queue_generated_at)
    skew_seconds = -1
    if manifest_ts is not None and queue_ts is not None:
        skew_seconds = int(abs((queue_ts - manifest_ts).total_seconds()))

    if manifest_ts is None or queue_ts is None:
        status = READINESS_STATE_PENDING
        remaining_blockers = ["input_artifact_freshness_unverified"]
    elif skew_seconds <= FRESHNESS_THRESHOLD_SECONDS:
        status = "pass"
        remaining_blockers = []
    else:
        status = READINESS_STATE_BLOCKED
        remaining_blockers = ["stale_artifact_generation_wave_mismatch"]

    return _decorate_check_item(
        {
            "check_id": "input_artifact_freshness",
            "category": "freshness",
            "status": status,
            "accepted": status == "pass",
            "signals": {
                "manifest_generated_at": str(manifest_generated_at or ""),
                "queue_generated_at": str(queue_generated_at or ""),
                "generated_at_skew_seconds": skew_seconds,
                "freshness_threshold_seconds": FRESHNESS_THRESHOLD_SECONDS,
            },
            "remaining_blockers": remaining_blockers,
        }
    )


def build_readiness_lanes(check_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for check_id in LANE_CHECK_IDS:
        item = next((row for row in check_items if str(row.get("check_id", "") or "") == check_id), None)
        if not isinstance(item, dict):
            continue
        lanes.append(
            {
                "lane_id": str(item.get("readiness_lane_id", check_id) or check_id),
                "check_id": check_id,
                "label": str(item.get("label", "") or ""),
                "readiness_state": str(item.get("readiness_state", _state_from_status(item.get("status"))) or READINESS_STATE_PENDING),
                "status": str(item.get("status", "") or ""),
                "exactness_policy": str(item.get("exactness_policy", "") or ""),
                "owner": str(item.get("owner", "") or ""),
                "next_action": str(item.get("next_action", "") or ""),
                "signals": _as_dict(item.get("signals")),
                "remaining_blockers": [
                    str(blocker).strip()
                    for blocker in item.get("remaining_blockers", [])
                    if str(blocker).strip()
                ],
            }
        )
    return lanes


def build_remaining_blocker_details(
    check_items: list[dict[str, Any]],
    remaining_blockers: list[str],
) -> list[dict[str, Any]]:
    source_by_blocker: dict[str, dict[str, Any]] = {}
    for item in check_items:
        blockers = [
            str(blocker).strip()
            for blocker in item.get("remaining_blockers", [])
            if str(blocker).strip()
        ]
        for blocker in blockers:
            source_by_blocker.setdefault(blocker, item)

    details: list[dict[str, Any]] = []
    for blocker in remaining_blockers:
        source = source_by_blocker.get(blocker, {})
        meta = BLOCKER_METADATA.get(blocker, {})
        state = str(
            meta.get(
                "state",
                source.get("readiness_state", _state_from_status(source.get("status"))),
            )
            or READINESS_STATE_PENDING
        )
        details.append(
            {
                "blocker": blocker,
                "state": state,
                "owner": str(meta.get("owner", "") or source.get("owner", "") or ""),
                "next_action": str(meta.get("next_action", "") or source.get("next_action", "") or ""),
                "source_check_id": str(source.get("check_id", "") or ""),
                "source_check_label": str(source.get("label", "") or ""),
                "exactness_policy": str(source.get("exactness_policy", "") or ""),
            }
        )
    return details


def summarize_readiness(
    *,
    check_items: list[dict[str, Any]],
    readiness_lanes: list[dict[str, Any]],
    input_artifact_freshness: dict[str, Any],
) -> dict[str, Any]:
    evidence_state_counts = {
        READINESS_STATE_ALL_PASS: 0,
        READINESS_STATE_BLOCKED: 0,
        READINESS_STATE_PENDING: 0,
    }
    for item in check_items:
        state = str(item.get("readiness_state", READINESS_STATE_PENDING) or READINESS_STATE_PENDING)
        evidence_state_counts[state] = evidence_state_counts.get(state, 0) + 1

    lane_state_counts = {
        READINESS_STATE_ALL_PASS: 0,
        READINESS_STATE_BLOCKED: 0,
        READINESS_STATE_PENDING: 0,
    }
    for lane in readiness_lanes:
        state = str(lane.get("readiness_state", READINESS_STATE_PENDING) or READINESS_STATE_PENDING)
        lane_state_counts[state] = lane_state_counts.get(state, 0) + 1

    overall_state = (
        READINESS_STATE_BLOCKED
        if evidence_state_counts[READINESS_STATE_BLOCKED] > 0
        else READINESS_STATE_PENDING
        if evidence_state_counts[READINESS_STATE_PENDING] > 0
        else READINESS_STATE_ALL_PASS
    )
    freshness_status = str(input_artifact_freshness.get("readiness_state", READINESS_STATE_PENDING) or READINESS_STATE_PENDING)
    freshness_signals = _as_dict(input_artifact_freshness.get("signals"))
    freshness_skew = _coerce_int(freshness_signals.get("generated_at_skew_seconds", -1))

    return {
        "readiness_state": overall_state,
        "readiness_lane_count": len(readiness_lanes),
        "readiness_lane_state_counts": lane_state_counts,
        "evidence_checklist_state_counts": evidence_state_counts,
        "input_artifact_freshness_status": freshness_status,
        "input_artifact_freshness_skew_seconds": freshness_skew,
        "stale_artifact_detected": freshness_status == READINESS_STATE_BLOCKED,
        "readiness_summary_line": (
            "Real drawing private corpus readiness: "
            f"{overall_state} | lanes={_counts_text(lane_state_counts)} | checklist={_counts_text(evidence_state_counts)}"
        ),
    }
