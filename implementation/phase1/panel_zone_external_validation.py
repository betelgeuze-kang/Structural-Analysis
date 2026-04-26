from __future__ import annotations

from typing import Any


SOLVER_VERIFIED_REQUIRED_EVIDENCE = "solver_verified_3d_clash_and_anchorage_artifact"
INTERNAL_PANEL_ZONE_REQUIRED_EVIDENCE = "internal_panel_zone_3d_completion_first"
NO_REQUIRED_EVIDENCE = "none"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return False


def _int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _coverage_count(summary: dict[str, Any], key: str, default: int = 0) -> int:
    return max(_int(summary.get(key), default), 0)


def panel_zone_external_validation_artifact_closed(summary: dict[str, Any]) -> bool:
    explicit = summary.get("panel_zone_external_validation_artifact_closed")
    if explicit not in (None, ""):
        return _bool(explicit)
    if _bool(summary.get("panel_zone_true_3d_bridge_complete")):
        return True
    if _bool(summary.get("panel_zone_solver_verified_bridge_complete")):
        return True
    return _bool(summary.get("panel_zone_true_3d_clash_verified")) and _bool(
        summary.get("panel_zone_true_3d_anchorage_verified")
    )


def build_panel_zone_external_validation_provenance_surface(
    summary: dict[str, Any],
) -> dict[str, Any]:
    missing_required_sources = [
        value
        for value in (summary.get("panel_zone_missing_required_sources") or [])
        if _text(value)
    ]
    source_count = _coverage_count(summary, "panel_zone_external_validation_source_count")
    validated_source_count = _coverage_count(
        summary, "panel_zone_external_validation_validated_source_count"
    )
    exact_source_count = _coverage_count(summary, "panel_zone_external_validation_exact_source_count")
    fallback_source_count = _coverage_count(
        summary, "panel_zone_external_validation_fallback_source_count"
    )
    missing_source_count = _coverage_count(
        summary,
        "panel_zone_external_validation_missing_source_count",
        len(missing_required_sources),
    )
    unknown_source_count = _coverage_count(summary, "panel_zone_external_validation_unknown_source_count")
    candidate_member_count = _coverage_count(
        summary, "panel_zone_external_validation_candidate_member_count"
    )
    validated_member_count = _coverage_count(
        summary, "panel_zone_external_validation_validated_member_count"
    )
    exact_member_count = _coverage_count(summary, "panel_zone_external_validation_exact_member_count")
    fallback_member_count = _coverage_count(
        summary, "panel_zone_external_validation_fallback_member_count"
    )
    validated_row_count_total = _coverage_count(
        summary, "panel_zone_external_validation_validated_row_count_total"
    )
    exact_validated_row_count = _coverage_count(
        summary, "panel_zone_external_validation_exact_validated_row_count"
    )
    fallback_validated_row_count = _coverage_count(
        summary, "panel_zone_external_validation_fallback_validated_row_count"
    )
    if source_count <= 0:
        source_count = max(
            validated_source_count + missing_source_count + unknown_source_count,
            exact_source_count + fallback_source_count + missing_source_count + unknown_source_count,
            validated_source_count,
            exact_source_count + fallback_source_count,
        )
    artifact_closed = panel_zone_external_validation_artifact_closed(summary)
    coverage_complete = source_count > 0 and validated_source_count >= source_count
    exact_only = source_count > 0 and exact_source_count >= source_count and fallback_source_count == 0
    fallback_only = (
        source_count > 0 and fallback_source_count >= source_count and exact_source_count == 0
    )
    mixed = source_count > 0 and exact_source_count > 0 and fallback_source_count > 0 and coverage_complete
    if artifact_closed:
        if exact_only:
            closure_mode = "closed_exact_validated"
        elif fallback_only:
            closure_mode = "closed_fallback_validated"
        elif mixed:
            closure_mode = "closed_mixed_validated"
        elif coverage_complete:
            closure_mode = "closed_validated"
        else:
            closure_mode = "closed_without_coverage_breakdown"
    elif exact_only:
        closure_mode = "open_exact_validated"
    elif fallback_only:
        closure_mode = "open_fallback_validated"
    elif mixed:
        closure_mode = "open_mixed_validated"
    elif coverage_complete:
        closure_mode = "open_validated"
    elif validated_source_count > 0:
        closure_mode = "open_partially_validated"
    elif _text(summary.get("panel_zone_validation_boundary")) == "solver_verified":
        closure_mode = "open_boundary_only_unverified"
    else:
        closure_mode = "open_unvalidated"
    summary_label = _text(summary.get("panel_zone_external_validation_provenance_summary_label"))
    if not summary_label and source_count > 0:
        summary_label = (
            f"validated_sources={validated_source_count}/{source_count} | "
            f"exact_sources={exact_source_count}/{source_count} | "
            f"fallback_sources={fallback_source_count}/{source_count} | "
            f"missing_sources={missing_source_count}/{source_count} | "
            f"validated_members={validated_member_count}/{candidate_member_count} | "
            f"exact_members={exact_member_count}/{candidate_member_count} | "
            f"fallback_members={fallback_member_count}/{candidate_member_count} | "
            f"exact_rows={exact_validated_row_count}/{validated_row_count_total} | "
            f"fallback_rows={fallback_validated_row_count}/{validated_row_count_total}"
        )
    return {
        "artifact_closed": artifact_closed,
        "closure_mode": closure_mode,
        "source_count": source_count,
        "validated_source_count": validated_source_count,
        "exact_source_count": exact_source_count,
        "fallback_source_count": fallback_source_count,
        "missing_source_count": missing_source_count,
        "unknown_source_count": unknown_source_count,
        "candidate_member_count": candidate_member_count,
        "validated_member_count": validated_member_count,
        "exact_member_count": exact_member_count,
        "fallback_member_count": fallback_member_count,
        "validated_row_count_total": validated_row_count_total,
        "exact_validated_row_count": exact_validated_row_count,
        "fallback_validated_row_count": fallback_validated_row_count,
        "summary_label": summary_label,
    }


def normalize_panel_zone_external_validation_status_label(
    summary: dict[str, Any],
    *,
    advisory_only: bool,
    release_blocking: bool,
    status_label: str = "",
) -> str:
    normalized_status = _text(
        status_label or summary.get("panel_zone_external_validation_status_label")
    )
    coverage = build_panel_zone_external_validation_provenance_surface(summary)
    if coverage["artifact_closed"]:
        if normalized_status in {"verified", "solver_verified"}:
            return normalized_status
        return "verified"
    if normalized_status and normalized_status.endswith(
        ("_no_solver_input", "_pending_solver_input", "_after_failed_consume")
    ):
        return normalized_status
    if normalized_status in {"verified", "solver_verified"}:
        normalized_status = ""
    if coverage["closure_mode"] == "open_exact_validated":
        return "validated_exact_gap"
    if coverage["closure_mode"] == "open_fallback_validated":
        return "validated_fallback_only_gap"
    if coverage["closure_mode"] == "open_mixed_validated":
        return "mixed_exact_fallback_gap"
    if release_blocking:
        return normalized_status or "release_blocking"
    if advisory_only:
        return normalized_status or "measured_external_validation_gap"
    if _bool(summary.get("panel_zone_external_validation_pending")):
        return normalized_status or "pending_external_validation"
    if coverage["closure_mode"] == "open_partially_validated":
        return normalized_status or "measured_external_validation_gap"
    if coverage["closure_mode"] == "open_boundary_only_unverified":
        return normalized_status or "pending_external_validation"
    return normalized_status or "not_applicable"


def build_panel_zone_external_validation_required_evidence(
    summary: dict[str, Any],
    *,
    status_label: str = "",
) -> str:
    boundary = _text(summary.get("panel_zone_validation_boundary"))
    pending = bool(summary.get("panel_zone_external_validation_pending", False))
    panel_ready = bool(summary.get("panel_zone_3d_clash_ready", False))
    normalized_status = _text(
        status_label or summary.get("panel_zone_external_validation_status_label")
    ).lower()
    coverage = build_panel_zone_external_validation_provenance_surface(summary)
    internal_ready = bool(
        summary.get("panel_zone_internal_engine_complete", False)
        or coverage["validated_source_count"] > 0
        or coverage["validated_member_count"] > 0
        or coverage["validated_row_count_total"] > 0
    )

    if coverage["artifact_closed"]:
        return NO_REQUIRED_EVIDENCE
    if pending or boundary == "external_validation_only":
        return SOLVER_VERIFIED_REQUIRED_EVIDENCE
    if boundary == "solver_verified" and not coverage["artifact_closed"]:
        return SOLVER_VERIFIED_REQUIRED_EVIDENCE
    if internal_ready or panel_ready or normalized_status.endswith("_gap"):
        return SOLVER_VERIFIED_REQUIRED_EVIDENCE
    return INTERNAL_PANEL_ZONE_REQUIRED_EVIDENCE


def build_panel_zone_external_validation_summary_line(
    summary: dict[str, Any],
    *,
    status_label: str = "",
) -> str:
    normalized_status = _text(status_label or summary.get("panel_zone_external_validation_status_label")) or "not_applicable"
    boundary = _text(summary.get("panel_zone_validation_boundary")) or "open"
    coverage = build_panel_zone_external_validation_provenance_surface(summary)
    required_evidence = build_panel_zone_external_validation_required_evidence(
        summary,
        status_label=normalized_status,
    )
    summary_line = (
        f"Panel-zone external validation: {normalized_status} | "
        f"boundary={boundary} | "
        f"artifact_closed={bool(coverage['artifact_closed'])} | "
        f"closure_mode={coverage['closure_mode']} | "
        f"required_evidence={required_evidence}"
    )
    if coverage["summary_label"]:
        summary_line = f"{summary_line} | {coverage['summary_label']}"
    return summary_line


def build_panel_zone_external_validation_local_closure_surface(
    summary: dict[str, Any],
    *,
    status_label: str = "",
) -> dict[str, str]:
    coverage = build_panel_zone_external_validation_provenance_surface(summary)
    required_evidence = build_panel_zone_external_validation_required_evidence(
        summary,
        status_label=status_label,
    )
    inbox_status_mode = _text(summary.get("panel_zone_solver_verified_inbox_status_mode"))
    input_mode = _text(summary.get("panel_zone_solver_verified_input_mode_detected"))
    latest_consume_present = bool(summary.get("panel_zone_solver_verified_latest_consume_report_present", False))
    latest_consume_pass = bool(summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False))
    latest_consume_reason = _text(summary.get("panel_zone_solver_verified_latest_consume_reason_code")) or "unknown"
    recommended_action = _text(summary.get("panel_zone_solver_verified_recommended_action")) or "wait_for_solver_drop"

    if coverage["artifact_closed"]:
        return {
            "state": "closed_with_solver_verified_artifact",
            "label": "Local closeout: closed by attached solver-verified 3D artifact.",
        }
    if required_evidence != SOLVER_VERIFIED_REQUIRED_EVIDENCE:
        return {
            "state": "not_applicable",
            "label": "Local closeout: not active until the internal panel-zone 3D boundary is complete.",
        }
    if bool(summary.get("panel_zone_solver_verified_inbox_has_input", False)):
        mode_label = inbox_status_mode or input_mode or "pending_inbox_input"
        return {
            "state": "pending_solver_verified_consume",
            "label": (
                "Local closeout: solver-verified inbox input is staged and still needs consume "
                f"({mode_label})."
            ),
        }
    if latest_consume_present and latest_consume_pass:
        return {
            "state": "awaiting_release_refresh_after_successful_consume",
            "label": (
                "Local closeout: latest solver-verified consume passed, but the live panel-zone "
                "release surface still needs refresh."
            ),
        }
    if latest_consume_present:
        return {
            "state": "latest_solver_verified_consume_failed",
            "label": (
                "Local closeout: latest solver-verified consume failed "
                f"({latest_consume_reason}); boundary remains open."
            ),
        }
    return {
        "state": "awaiting_solver_verified_drop",
        "label": (
            "Local closeout: no solver-verified inbox input is present; boundary remains open "
            f"({recommended_action})."
        ),
    }
