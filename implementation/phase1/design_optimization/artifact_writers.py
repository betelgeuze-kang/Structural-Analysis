"""Shared artifact writers for design-optimization reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable

from design_optimization.io import write_json
from design_optimization.report_builder import build_report_payload, build_stage_report_payload
from design_optimization_explain_schema import write_explain_csv, write_explain_json


def write_json_rows(path: str | Path, key: str, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema_version": "1.0", key: rows}, indent=2), encoding="utf-8")


def write_csv_rows(
    path: str | Path,
    *,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
    row_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = dict(row_transform(row) if row_transform is not None else row)
            writer.writerow(payload)


def write_stage_report(
    path: str | Path,
    *,
    run_id: str,
    summary: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    contract_pass: bool,
    reason_code: str,
    reason: str,
    head_blocks: dict[str, list[dict[str, Any]]] | None = None,
    schema_version: str = "2.0",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_stage_report_payload(
        run_id=run_id,
        summary=summary,
        inputs=inputs,
        artifacts=artifacts,
        contract_pass=contract_pass,
        reason_code=reason_code,
        reason=reason,
        head_blocks=head_blocks,
        schema_version=schema_version,
        extra=extra,
    )
    write_json(Path(path), payload)
    return payload


def write_design_optimization_report(
    path: str | Path,
    *,
    run_id: str,
    summary: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    contract_pass: bool,
    reason_code: str,
    reason: str,
    schema_version: str = "2.0",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_report_payload(
        run_id=run_id,
        summary=summary,
        inputs=inputs,
        artifacts=artifacts,
        contract_pass=contract_pass,
        reason_code=reason_code,
        reason=reason,
        schema_version=schema_version,
        extra=extra,
    )
    write_json(Path(path), payload)
    return payload


def write_design_change_artifacts(
    *,
    changes_json_out: str | Path,
    changes_csv_out: str | Path,
    changes_summary_json_out: str | Path,
    changes_summary_csv_out: str | Path,
    changes: list[dict[str, Any]],
    change_summary_rows: list[dict[str, Any]],
) -> None:
    write_json_rows(changes_json_out, "changes", changes)
    write_csv_rows(
        changes_csv_out,
        fieldnames=[
            "group_id",
            "group_index",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "action_name",
            "action_family",
            "before_section",
            "after_section",
            "before_rebar_ratio",
            "after_rebar_ratio",
            "rebar_ratio_delta",
            "before_thickness_scale",
            "after_thickness_scale",
            "before_detailing_quality",
            "after_detailing_quality",
            "cost_proxy_before",
            "cost_proxy_after",
            "cost_proxy_delta",
            "max_dcr_before",
            "max_dcr_after",
            "max_dcr_delta",
            "governing_member_governing_dcr_before",
            "governing_member_governing_dcr_after",
            "governing_clause",
            "drift_before_pct",
            "drift_after_pct",
            "residual_before_pct",
            "residual_after_pct",
            "before_constructability",
            "after_constructability",
            "before_detailing_complexity",
            "after_detailing_complexity",
            "constructability_delta",
            "overdesign_margin_delta",
            "selection_gate",
            "reason_selected",
        ],
        rows=changes,
    )
    write_json_rows(changes_summary_json_out, "change_summary_rows", change_summary_rows)
    write_csv_rows(
        changes_summary_csv_out,
        fieldnames=[
            "story_band",
            "zone_label",
            "member_type",
            "changed_group_count",
            "semantic_group_count",
            "rebar_ratio_delta_sum",
            "cost_proxy_delta_sum",
            "constructability_before_avg",
            "constructability_after_avg",
            "detailing_complexity_before_avg",
            "detailing_complexity_after_avg",
            "constructability_delta_sum",
            "overdesign_margin_delta_sum",
            "max_dcr_before_max",
            "max_dcr_after_max",
            "selection_gate",
        ],
        rows=change_summary_rows,
    )


def write_blocked_action_artifacts(
    *,
    blocked_actions_json_out: str | Path,
    blocked_actions_csv_out: str | Path,
    blocked_no_cost_json_out: str | Path,
    blocked_no_cost_csv_out: str | Path,
    blocked_no_cost_explain_json_out: str | Path,
    blocked_no_cost_explain_csv_out: str | Path,
    blocked_rows: list[dict[str, Any]],
    blocked_no_cost_rows: list[dict[str, Any]],
    blocked_no_cost_explain_rows: list[dict[str, Any]],
) -> None:
    write_json_rows(blocked_actions_json_out, "blocked_rows", blocked_rows)
    write_csv_rows(
        blocked_actions_csv_out,
        fieldnames=[
            "group_id",
            "group_index",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "action_family",
            "max_dcr",
            "trial_max_dcr",
            "priority",
            "action_name",
            "block_reason",
            "trial_cost",
            "trial_drift_pct",
            "trial_residual_drift_pct",
            "current_congestion",
            "trial_congestion",
            "current_detailing_complexity",
            "trial_detailing_complexity",
            "current_constructability",
            "trial_constructability",
            "current_anchorage_complexity",
            "trial_anchorage_complexity",
            "current_splice_burden",
            "trial_splice_burden",
            "constructability_gain",
            "congestion_gain",
            "detailing_gain",
            "anchorage_gain",
            "splice_gain",
            "detail",
        ],
        rows=blocked_rows,
    )
    write_json_rows(blocked_no_cost_json_out, "no_cost_gain_groups", blocked_no_cost_rows)
    write_csv_rows(
        blocked_no_cost_csv_out,
        fieldnames=[
            "group_id",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "blocked_action_count",
            "action_names",
            "priority_max",
            "max_dcr",
            "detail_examples",
        ],
        rows=blocked_no_cost_rows,
        row_transform=lambda row: {
            **dict(row),
            "action_names": "|".join(str(x) for x in row.get("action_names", [])),
            "detail_examples": " | ".join(str(x) for x in row.get("detail_examples", [])),
        },
    )
    write_json_rows(blocked_no_cost_explain_json_out, "no_cost_gain_explain_groups", blocked_no_cost_explain_rows)
    write_csv_rows(
        blocked_no_cost_explain_csv_out,
        fieldnames=[
            "group_id",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "priority_max",
            "max_dcr",
            "rebar_ratio_current",
            "thickness_scale_current",
            "detailing_quality_current",
            "rebar_min_clamp_count",
            "thickness_min_clamp_count",
            "detailing_min_clamp_count",
            "zero_projected_cost_delta_count",
            "dominant_block_cause",
            "action_names",
            "detail_examples",
        ],
        rows=blocked_no_cost_explain_rows,
        row_transform=lambda row: {
            **{k: v for k, v in dict(row).items() if k != "cause_counts"},
            "action_names": "|".join(str(x) for x in row.get("action_names", [])),
            "detail_examples": " | ".join(str(x) for x in row.get("detail_examples", [])),
        },
    )


def write_candidate_explain_artifacts(
    *,
    accepted_candidate_explain_json_out: str | Path,
    accepted_candidate_explain_csv_out: str | Path,
    candidate_explain_v2_json_out: str | Path,
    candidate_explain_v2_csv_out: str | Path,
    rejected_candidate_explain_v2_json_out: str | Path,
    rejected_candidate_explain_v2_csv_out: str | Path,
    accepted_candidate_explain_rows: list[dict[str, Any]],
    accepted_candidate_explain_rows_v2: list[dict[str, Any]],
    rejected_candidate_explain_rows_v2: list[dict[str, Any]],
) -> None:
    write_json_rows(accepted_candidate_explain_json_out, "accepted_candidate_explain_rows", accepted_candidate_explain_rows)
    write_csv_rows(
        accepted_candidate_explain_csv_out,
        fieldnames=[
            "group_id",
            "group_index",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "action_name",
            "baseline_focus_member_id",
            "member_id",
            "case_id",
            "combination_name",
            "viewer_overlay_row_id",
            "viewer_row_ref",
            "row_ref",
            "viewer_row_url",
            "viewer_slice_url",
            "reverse_sync_row_ref",
            "governing_clause_label",
            "recommended_results_card",
            "recommended_results_series_index",
            "recommended_results_card_label",
            "recommended_results_series_label",
            "recommended_results_reason_label",
            "priority",
            "max_dcr",
            "projected_cost_delta",
            "selected_in_final_loop",
            "selected_event_index",
            "current_congestion",
            "trial_congestion",
            "current_detailing_complexity",
            "trial_detailing_complexity",
            "current_constructability",
            "trial_constructability",
            "constructability_gain",
            "congestion_gain",
            "detailing_gain",
            "explain_reason",
            "detail",
        ],
        rows=accepted_candidate_explain_rows,
    )
    write_explain_json(Path(candidate_explain_v2_json_out), key="selected_candidate_rows", rows=accepted_candidate_explain_rows_v2)
    write_explain_csv(Path(candidate_explain_v2_csv_out), accepted_candidate_explain_rows_v2)
    write_explain_json(Path(rejected_candidate_explain_v2_json_out), key="rejected_candidate_rows", rows=rejected_candidate_explain_rows_v2)
    write_explain_csv(Path(rejected_candidate_explain_v2_csv_out), rejected_candidate_explain_rows_v2)


def write_reverse_sync_artifacts(
    *,
    reverse_sync_json_out: str | Path,
    reverse_sync_csv_out: str | Path,
    reverse_sync_contract_version: str,
    reverse_sync_rows: list[dict[str, Any]],
) -> None:
    selected_rows = [row for row in reverse_sync_rows if bool(row.get("selected_in_final_loop", False))]
    payload = {
        "schema_version": "1.0",
        "contract_version": str(reverse_sync_contract_version or "").strip() or "0.1.0",
        "summary": {
            "row_count": int(len(reverse_sync_rows)),
            "selected_row_count": int(len(selected_rows)),
            "event_count": int(
                len(
                    {
                        int(row.get("selected_event_index", 0) or 0)
                        for row in reverse_sync_rows
                        if int(row.get("selected_event_index", 0) or 0) > 0
                    }
                )
            ),
            "row_url_count": int(sum(1 for row in reverse_sync_rows if str(row.get("viewer_row_url", "")).strip())),
            "slice_url_count": int(sum(1 for row in reverse_sync_rows if str(row.get("viewer_slice_url", "")).strip())),
            "overlay_row_id_count": int(sum(1 for row in reverse_sync_rows if str(row.get("viewer_overlay_row_id", "")).strip())),
        },
        "reverse_sync_rows": reverse_sync_rows,
    }
    write_json(Path(reverse_sync_json_out), payload)
    write_csv_rows(
        reverse_sync_csv_out,
        fieldnames=[
            "reverse_sync_row_ref",
            "selected_in_final_loop",
            "selected_event_index",
            "group_id",
            "group_index",
            "story_band",
            "zone_label",
            "member_type",
            "semantic_group",
            "action_name",
            "action_family",
            "baseline_focus_member_id",
            "member_id",
            "case_id",
            "combination_name",
            "governing_clause_label",
            "recommended_results_card",
            "recommended_results_series_index",
            "recommended_results_card_label",
            "recommended_results_series_label",
            "recommended_results_reason_label",
            "viewer_overlay_row_id",
            "viewer_row_ref",
            "viewer_row_url",
            "viewer_slice_url",
            "row_ref",
            "projected_cost_delta",
            "max_dcr",
        ],
        rows=reverse_sync_rows,
    )


def write_cost_reduction_support_artifacts(
    *,
    changes_json_out: str | Path,
    changes_csv_out: str | Path,
    changes_summary_json_out: str | Path,
    changes_summary_csv_out: str | Path,
    blocked_actions_json_out: str | Path,
    blocked_actions_csv_out: str | Path,
    blocked_no_cost_json_out: str | Path,
    blocked_no_cost_csv_out: str | Path,
    blocked_no_cost_explain_json_out: str | Path,
    blocked_no_cost_explain_csv_out: str | Path,
    accepted_candidate_explain_json_out: str | Path,
    accepted_candidate_explain_csv_out: str | Path,
    reverse_sync_json_out: str | Path,
    reverse_sync_csv_out: str | Path,
    candidate_explain_v2_json_out: str | Path,
    candidate_explain_v2_csv_out: str | Path,
    rejected_candidate_explain_v2_json_out: str | Path,
    rejected_candidate_explain_v2_csv_out: str | Path,
    changes: list[dict[str, Any]],
    change_summary_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    blocked_no_cost_rows: list[dict[str, Any]],
    blocked_no_cost_explain_rows: list[dict[str, Any]],
    accepted_candidate_explain_rows: list[dict[str, Any]],
    reverse_sync_contract_version: str,
    reverse_sync_rows: list[dict[str, Any]],
    accepted_candidate_explain_rows_v2: list[dict[str, Any]],
    rejected_candidate_explain_rows_v2: list[dict[str, Any]],
) -> None:
    write_design_change_artifacts(
        changes_json_out=changes_json_out,
        changes_csv_out=changes_csv_out,
        changes_summary_json_out=changes_summary_json_out,
        changes_summary_csv_out=changes_summary_csv_out,
        changes=changes,
        change_summary_rows=change_summary_rows,
    )
    write_blocked_action_artifacts(
        blocked_actions_json_out=blocked_actions_json_out,
        blocked_actions_csv_out=blocked_actions_csv_out,
        blocked_no_cost_json_out=blocked_no_cost_json_out,
        blocked_no_cost_csv_out=blocked_no_cost_csv_out,
        blocked_no_cost_explain_json_out=blocked_no_cost_explain_json_out,
        blocked_no_cost_explain_csv_out=blocked_no_cost_explain_csv_out,
        blocked_rows=blocked_rows,
        blocked_no_cost_rows=blocked_no_cost_rows,
        blocked_no_cost_explain_rows=blocked_no_cost_explain_rows,
    )
    write_candidate_explain_artifacts(
        accepted_candidate_explain_json_out=accepted_candidate_explain_json_out,
        accepted_candidate_explain_csv_out=accepted_candidate_explain_csv_out,
        candidate_explain_v2_json_out=candidate_explain_v2_json_out,
        candidate_explain_v2_csv_out=candidate_explain_v2_csv_out,
        rejected_candidate_explain_v2_json_out=rejected_candidate_explain_v2_json_out,
        rejected_candidate_explain_v2_csv_out=rejected_candidate_explain_v2_csv_out,
        accepted_candidate_explain_rows=accepted_candidate_explain_rows,
        accepted_candidate_explain_rows_v2=accepted_candidate_explain_rows_v2,
        rejected_candidate_explain_rows_v2=rejected_candidate_explain_rows_v2,
    )
    write_reverse_sync_artifacts(
        reverse_sync_json_out=reverse_sync_json_out,
        reverse_sync_csv_out=reverse_sync_csv_out,
        reverse_sync_contract_version=reverse_sync_contract_version,
        reverse_sync_rows=reverse_sync_rows,
    )


__all__ = [
    "write_blocked_action_artifacts",
    "write_candidate_explain_artifacts",
    "write_cost_reduction_support_artifacts",
    "write_csv_rows",
    "write_design_optimization_report",
    "write_design_change_artifacts",
    "write_json_rows",
    "write_reverse_sync_artifacts",
    "write_stage_report",
]
