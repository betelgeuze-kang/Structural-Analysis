#!/usr/bin/env python3
"""Run cost-reduction-only optimization from a feasible solver-validated state."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np

from design_optimization.artifacts import (
    ACCEPTED_CANDIDATE_EXPLAIN_CSV,
    ACCEPTED_CANDIDATE_EXPLAIN_JSON,
    CANDIDATE_EXPLAIN_V2_CSV,
    CANDIDATE_EXPLAIN_V2_JSON,
    COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    COST_REDUCTION_BLOCKED_ACTIONS_JSON,
    COST_REDUCTION_CHANGES_CSV,
    COST_REDUCTION_CHANGES_JSON,
    COST_REDUCTION_CHANGES_SUMMARY_CSV,
    COST_REDUCTION_CHANGES_SUMMARY_JSON,
    COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    COST_REDUCTION_NO_GAIN_EXPLAIN_JSON,
    COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    COST_REDUCTION_NO_GAIN_GROUPS_JSON,
    COST_REDUCTION_REVERSE_SYNC_CSV,
    COST_REDUCTION_REVERSE_SYNC_JSON,
    COST_REDUCTION_REPORT_JSON,
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    REJECTED_CANDIDATE_EXPLAIN_V2_CSV,
    REJECTED_CANDIDATE_EXPLAIN_V2_JSON,
    SOLVER_LOOP_LONG_REPORT_JSON,
    SOLVER_LOOP_LONG_STATE_NPZ,
)
from design_optimization.artifact_writers import write_cost_reduction_support_artifacts, write_design_optimization_report
from design_objective_calibration import apply_objective_calibration, apply_objective_profile
from design_optimization.candidate_generation import (
    aggregate_accepted_candidate_explain_rows as _aggregate_accepted_candidate_explain_rows_impl,
    aggregate_no_cost_gain_explain_rows as _aggregate_no_cost_gain_explain_rows_impl,
    aggregate_no_cost_gain_rows as _aggregate_no_cost_gain_rows_impl,
    build_action_block_report as _build_action_block_report_impl,
    cost_down_actions_for_group as _cost_down_actions_for_group_impl,
    evaluate_cost_down_candidate as _evaluate_cost_down_candidate_impl,
    parse_projected_cost_delta as _parse_projected_cost_delta_impl,
    preview_cost_down_candidate as _preview_cost_down_candidate_impl,
)
from design_optimization.candidate_selection import run_cost_reduction_selection
from design_optimization.reporting import (
    build_explain_schema_v2_rows as _build_explain_schema_v2_rows_impl,
    group_state_lookup as _group_state_lookup_impl,
    rejected_reason as _rejected_reason_impl,
    selected_reason as _selected_reason_impl,
)
from design_optimization_env import (
    ACTION_FAMILY_BY_NAME,
    ACTION_INDEX_V2,
    DesignOptimizationConfig,
    aggregate_group_state,
)
from run_design_optimization_solver_loop import (
    _load_npz,
    _local_dcr_update,
    _solver_stage_state,
    solver_backends_gpu_strict,
)


DEFAULT_ROW_PROVENANCE_REPORT_JSON = "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json"
DEFAULT_ROW_PROVENANCE_CSV = "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv"
COST_REDUCTION_REVERSE_SYNC_CONTRACT_VERSION = "0.1.0"
COST_REDUCTION_VIEWER_RELATIVE_HTML = "../visualization/structural_optimization_viewer.html"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _default_results_recommendation(
    *,
    member_type: object,
    action_family: object,
    combination_name: object,
    clause_label: object,
) -> dict[str, object]:
    combo = _safe_text(combination_name).upper()
    clause = _safe_text(clause_label).upper()
    member = _safe_text(member_type).lower()
    family = _safe_text(action_family).lower()
    if any(token in combo for token in ("SEIS", "EQ", "TH", "RESP")):
        return {
            "recommended_results_card": "time-history",
            "recommended_results_card_label": "Time history",
            "recommended_results_series_index": 0,
            "recommended_results_series_label": "Displacement u",
            "recommended_results_reason_label": "governing combination indicates seismic/time-history review",
        }
    if "DRIFT" in clause or "SVC" in combo or family in {"wall_thickness", "slab_thickness"} or member in {"wall", "slab"}:
        return {
            "recommended_results_card": "envelope",
            "recommended_results_card_label": "Envelope",
            "recommended_results_series_index": 1,
            "recommended_results_series_label": "Final drift",
            "recommended_results_reason_label": "governing drift/serviceability signal prefers final drift envelope",
        }
    return {
        "recommended_results_card": "envelope",
        "recommended_results_card_label": "Envelope",
        "recommended_results_series_index": 0,
        "recommended_results_series_label": "Envelope drift",
        "recommended_results_reason_label": "default cost-reduction review opens the envelope response first",
    }


def _resolve_row_provenance_csv_path(
    *,
    row_provenance_report_path: Path | None,
    row_provenance_csv_path: Path | None,
) -> Path | None:
    if row_provenance_csv_path is not None and row_provenance_csv_path.exists():
        return row_provenance_csv_path
    if row_provenance_report_path is None or not row_provenance_report_path.exists():
        return None
    try:
        payload = _load_json(row_provenance_report_path)
    except Exception:
        return None
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    csv_path = Path(str(artifacts.get("csv", "")).strip()) if str(artifacts.get("csv", "")).strip() else None
    if csv_path is not None and csv_path.exists():
        return csv_path
    return None


def _load_row_provenance_rows(
    *,
    row_provenance_report_path: Path | None,
    row_provenance_csv_path: Path | None,
) -> list[dict[str, str]]:
    resolved_csv_path = _resolve_row_provenance_csv_path(
        row_provenance_report_path=row_provenance_report_path,
        row_provenance_csv_path=row_provenance_csv_path,
    )
    if resolved_csv_path is None:
        return []
    try:
        with resolved_csv_path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle) if isinstance(row, dict)]
    except Exception:
        return []


def _first_string_per_group(
    values: np.ndarray,
    group_index_per_member: np.ndarray,
    group_count: int,
) -> list[str]:
    out = [""] * int(group_count)
    filled = [False] * int(group_count)
    for raw_index, raw_value in zip(group_index_per_member.tolist(), values.tolist()):
        gi = int(raw_index)
        if gi < 0 or gi >= int(group_count) or filled[gi]:
            continue
        out[gi] = _safe_text(raw_value)
        filled[gi] = True
    return out


def _build_cost_reduction_viewer_enrichment(
    *,
    dataset: dict[str, Any],
    row_provenance_report_path: Path | None,
    row_provenance_csv_path: Path | None,
) -> dict[str, dict[str, object]]:
    group_ids = np.asarray(dataset.get("unique_group_ids", np.asarray([], dtype="<U1")))
    group_index_per_member = np.asarray(dataset.get("group_index_per_member", np.zeros(0, dtype=np.int32)), dtype=np.int32)
    group_count = int(group_ids.shape[0])
    if group_count == 0 or group_index_per_member.size == 0:
        return {}

    member_ids = np.asarray(dataset.get("member_ids", np.asarray([""] * group_index_per_member.shape[0], dtype="<U64")))
    member_types = np.asarray(dataset.get("member_types", np.asarray([""] * group_index_per_member.shape[0], dtype="<U32")))
    zone_labels = np.asarray(dataset.get("zone_labels", np.asarray([""] * group_index_per_member.shape[0], dtype="<U32")))
    semantic_groups = np.asarray(dataset.get("semantic_groups", np.asarray([""] * group_index_per_member.shape[0], dtype="<U96")))
    governing_clauses = np.asarray(dataset.get("member_governing_clause", np.asarray([""] * group_index_per_member.shape[0], dtype="<U128")))
    governing_combos = np.asarray(dataset.get("member_governing_combo", np.asarray([""] * group_index_per_member.shape[0], dtype="<U128")))
    story_band_values = np.asarray(dataset.get("story_band_index", np.zeros(group_index_per_member.shape[0], dtype=np.int32)), dtype=np.int32)

    focus_member_ids = _first_string_per_group(member_ids, group_index_per_member, group_count)
    member_type_per_group = _first_string_per_group(member_types, group_index_per_member, group_count)
    zone_label_per_group = _first_string_per_group(zone_labels, group_index_per_member, group_count)
    semantic_group_per_group = _first_string_per_group(semantic_groups, group_index_per_member, group_count)
    governing_clause_per_group = _first_string_per_group(governing_clauses, group_index_per_member, group_count)
    governing_combo_per_group = _first_string_per_group(governing_combos, group_index_per_member, group_count)
    story_band_per_group = np.zeros(group_count, dtype=np.int32)
    filled_story_band = np.zeros(group_count, dtype=np.bool_)
    for raw_index, raw_value in zip(group_index_per_member.tolist(), story_band_values.tolist()):
        gi = int(raw_index)
        if gi < 0 or gi >= group_count or bool(filled_story_band[gi]):
            continue
        story_band_per_group[gi] = _safe_int(raw_value, 0)
        filled_story_band[gi] = True

    rows_by_focus_member: dict[str, list[dict[str, str]]] = {}
    for row in _load_row_provenance_rows(
        row_provenance_report_path=row_provenance_report_path,
        row_provenance_csv_path=row_provenance_csv_path,
    ):
        focus_member_id = _safe_text(row.get("baseline_focus_member_id"))
        if focus_member_id:
            rows_by_focus_member.setdefault(focus_member_id, []).append(row)

    enrichment_by_group: dict[str, dict[str, object]] = {}
    for group_index, raw_group_id in enumerate(group_ids.tolist()):
        group_id = _safe_text(raw_group_id)
        focus_member_id = _safe_text(focus_member_ids[group_index] if group_index < len(focus_member_ids) else "")
        governing_clause = _safe_text(governing_clause_per_group[group_index] if group_index < len(governing_clause_per_group) else "")
        governing_combo = _safe_text(governing_combo_per_group[group_index] if group_index < len(governing_combo_per_group) else "")
        member_type = _safe_text(member_type_per_group[group_index] if group_index < len(member_type_per_group) else "")
        zone_label = _safe_text(zone_label_per_group[group_index] if group_index < len(zone_label_per_group) else "")
        semantic_group = _safe_text(semantic_group_per_group[group_index] if group_index < len(semantic_group_per_group) else "")
        row_candidates = rows_by_focus_member.get(focus_member_id, [])
        best_row: dict[str, str] | None = None
        best_score = -1
        for candidate in row_candidates:
            score = 0
            if _safe_text(candidate.get("baseline_focus_member_id")) == focus_member_id:
                score += 100
            if governing_clause and _safe_text(candidate.get("clause_label")) == governing_clause:
                score += 80
            if governing_combo and _safe_text(candidate.get("combination_name")) == governing_combo:
                score += 60
            if member_type and _safe_text(candidate.get("member_type")) == member_type:
                score += 20
            if _safe_text(candidate.get("viewer_row_ref")):
                score += 10
            if score > best_score:
                best_score = score
                best_row = candidate

        recommendation = _default_results_recommendation(
            member_type=member_type,
            action_family="",
            combination_name=(best_row or {}).get("combination_name", governing_combo),
            clause_label=(best_row or {}).get("clause_label", governing_clause),
        )
        enrichment = {
            "group_id": group_id,
            "group_index": int(group_index),
            "story_band": int(story_band_per_group[group_index]),
            "zone_label": zone_label,
            "member_type": member_type,
            "semantic_group": semantic_group,
            "baseline_focus_member_id": focus_member_id,
            "member_id": _safe_text((best_row or {}).get("member_id")) or focus_member_id,
            "case_id": _safe_text((best_row or {}).get("case_id")) or focus_member_id,
            "combination_name": _safe_text((best_row or {}).get("combination_name")) or governing_combo,
            "viewer_row_ref": _safe_text((best_row or {}).get("viewer_row_ref")),
            "row_ref": _safe_text((best_row or {}).get("viewer_row_ref")),
            "viewer_row_url": _safe_text((best_row or {}).get("viewer_row_url")),
            "viewer_slice_url": _safe_text((best_row or {}).get("viewer_slice_url")),
            "governing_clause_label": governing_clause,
            **recommendation,
        }
        if best_row is not None:
            enrichment["recommended_results_card"] = _safe_text(
                best_row.get("viewer_results_card")
            ) or str(recommendation["recommended_results_card"])
            enrichment["recommended_results_series_index"] = _safe_int(
                best_row.get("viewer_results_series_index"),
                _safe_int(recommendation["recommended_results_series_index"], 0),
            )
            if not _safe_text(enrichment["combination_name"]):
                enrichment["combination_name"] = _safe_text(best_row.get("combination_name"))
        enrichment_by_group[group_id] = enrichment
        enrichment_by_group[f"__group_index__:{group_index}"] = enrichment
    return enrichment_by_group


def _apply_cost_reduction_viewer_enrichment(
    *,
    rows: list[dict[str, object]],
    enrichment_by_group: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    enriched_rows: list[dict[str, object]] = []
    for row in rows:
        payload = dict(row)
        group_id = _safe_text(payload.get("group_id"))
        group_index = _safe_int(payload.get("group_index"), -1)
        enrichment = enrichment_by_group.get(group_id) or enrichment_by_group.get(f"__group_index__:{group_index}", {})
        action_family = _safe_text(payload.get("action_family"))
        member_type = _safe_text(payload.get("member_type")) or _safe_text(enrichment.get("member_type"))
        recommendation = _default_results_recommendation(
            member_type=member_type,
            action_family=action_family,
            combination_name=payload.get("combination_name") or enrichment.get("combination_name"),
            clause_label=payload.get("governing_clause") or payload.get("governing_clause_label") or enrichment.get("governing_clause_label"),
        )
        merged = {
            **enrichment,
            **recommendation,
            **payload,
        }
        if not _safe_text(payload.get("baseline_focus_member_id")):
            merged["baseline_focus_member_id"] = _safe_text(enrichment.get("baseline_focus_member_id"))
        if not _safe_text(payload.get("member_id")):
            merged["member_id"] = _safe_text(enrichment.get("member_id")) or _safe_text(merged.get("baseline_focus_member_id"))
        if not _safe_text(payload.get("case_id")):
            merged["case_id"] = _safe_text(enrichment.get("case_id")) or _safe_text(merged.get("member_id"))
        if not _safe_text(payload.get("combination_name")):
            merged["combination_name"] = _safe_text(enrichment.get("combination_name"))
        if not _safe_text(payload.get("viewer_row_ref")):
            merged["viewer_row_ref"] = _safe_text(enrichment.get("viewer_row_ref"))
        if not _safe_text(payload.get("row_ref")):
            merged["row_ref"] = _safe_text(merged.get("viewer_row_ref")) or _safe_text(enrichment.get("row_ref"))
        if not _safe_text(payload.get("viewer_row_url")):
            merged["viewer_row_url"] = _safe_text(enrichment.get("viewer_row_url"))
        if not _safe_text(payload.get("viewer_slice_url")):
            merged["viewer_slice_url"] = _safe_text(enrichment.get("viewer_slice_url"))
        if not _safe_text(payload.get("recommended_results_card")):
            merged["recommended_results_card"] = _safe_text(enrichment.get("recommended_results_card")) or str(recommendation["recommended_results_card"])
        merged["recommended_results_series_index"] = _safe_int(
            payload.get("recommended_results_series_index")
            if payload.get("recommended_results_series_index") not in (None, "")
            else enrichment.get("recommended_results_series_index"),
            _safe_int(recommendation["recommended_results_series_index"], 0),
        )
        if not _safe_text(payload.get("recommended_results_card_label")):
            merged["recommended_results_card_label"] = _safe_text(enrichment.get("recommended_results_card_label")) or str(recommendation["recommended_results_card_label"])
        if not _safe_text(payload.get("recommended_results_series_label")):
            merged["recommended_results_series_label"] = _safe_text(enrichment.get("recommended_results_series_label")) or str(recommendation["recommended_results_series_label"])
        if not _safe_text(payload.get("recommended_results_reason_label")):
            merged["recommended_results_reason_label"] = _safe_text(enrichment.get("recommended_results_reason_label")) or str(recommendation["recommended_results_reason_label"])
        enriched_rows.append(merged)
    return enriched_rows


def _cost_reduction_viewer_overlay_row_id(
    *,
    group_index: object,
    selected_event_index: object,
    member_id: object,
    action_name: object,
) -> str:
    return "::".join(
        [
            "overlay_row",
            str(_safe_int(selected_event_index, 0)),
            str(_safe_int(group_index, -1)),
            _safe_text(member_id).replace("::", ":"),
            _safe_text(action_name).replace("::", ":"),
        ]
    )


def _cost_reduction_reverse_sync_row_ref(
    *,
    group_index: object,
    selected_event_index: object,
    member_id: object,
    action_name: object,
) -> str:
    return "::".join(
        [
            "cost_reduction",
            str(_safe_int(selected_event_index, 0)),
            str(_safe_int(group_index, -1)),
            _safe_text(member_id).replace("::", ":"),
            _safe_text(action_name).replace("::", ":"),
        ]
    )


def _build_cost_reduction_viewer_url(
    *,
    row: dict[str, object],
    focus_mode: str,
) -> str:
    member_id = _safe_text(row.get("member_id")) or _safe_text(row.get("baseline_focus_member_id")) or _safe_text(row.get("case_id"))
    group_id = _safe_text(row.get("group_id"))
    action_name = _safe_text(row.get("action_name"))
    zone_label = _safe_text(row.get("zone_label"))
    params: dict[str, object] = {
        "source": "cost_reduction_reverse_sync",
        "focus": "results",
        "view": "core",
        "overlay_focus": _safe_text(focus_mode) or "member",
        "overlay_row_id": _safe_text(row.get("viewer_overlay_row_id")),
        "overlay_group_id": group_id,
        "overlay_group_index": _safe_int(row.get("group_index"), -1),
        "overlay_action_name": action_name,
        "overlay_story_band": _safe_int(row.get("story_band"), 0),
        "overlay_zone_label": zone_label,
        "overlay_selected_event_index": _safe_int(row.get("selected_event_index"), 0),
        "results_card": _safe_text(row.get("recommended_results_card")) or "envelope",
        "results_series_index": _safe_int(row.get("recommended_results_series_index"), 0),
        "results_companion": "checks",
        "results_detail_block": "chart",
        "interactive_detail_more": "open",
        "overlay_detail_more": "open",
        "row_ref": _safe_text(row.get("viewer_row_ref")) or _safe_text(row.get("row_ref")),
    }
    if member_id:
        params["focus_member"] = member_id
        params["member_id"] = member_id
        params["baseline_focus_member_id"] = member_id
        params["overlay_member_id"] = member_id
    case_id = _safe_text(row.get("case_id"))
    if case_id:
        params["case_id"] = case_id
    combination_name = _safe_text(row.get("combination_name"))
    if combination_name:
        params["combination"] = combination_name
        params["combination_name"] = combination_name
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if (
                (str(value).strip() and str(value) != "-1")
                or key in {"results_card", "results_series_index", "source", "focus", "view", "overlay_focus", "interactive_detail_more", "overlay_detail_more"}
            )
        }
    )
    return f"{COST_REDUCTION_VIEWER_RELATIVE_HTML}?{query}" if query else COST_REDUCTION_VIEWER_RELATIVE_HTML


def _build_cost_reduction_reverse_sync_rows(
    *,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    reverse_sync_rows: list[dict[str, object]] = []
    for row in rows:
        payload = dict(row)
        viewer_overlay_row_id = _cost_reduction_viewer_overlay_row_id(
            group_index=payload.get("group_index"),
            selected_event_index=payload.get("selected_event_index"),
            member_id=payload.get("member_id") or payload.get("baseline_focus_member_id"),
            action_name=payload.get("action_name"),
        )
        reverse_sync_row_ref = _cost_reduction_reverse_sync_row_ref(
            group_index=payload.get("group_index"),
            selected_event_index=payload.get("selected_event_index"),
            member_id=payload.get("member_id") or payload.get("baseline_focus_member_id"),
            action_name=payload.get("action_name"),
        )
        reverse_sync_payload = {
            "viewer_overlay_row_id": viewer_overlay_row_id,
            "reverse_sync_row_ref": reverse_sync_row_ref,
            "selected_in_final_loop": bool(payload.get("selected_in_final_loop", False)),
            "selected_event_index": _safe_int(payload.get("selected_event_index"), 0),
            "group_id": _safe_text(payload.get("group_id")),
            "group_index": _safe_int(payload.get("group_index"), -1),
            "story_band": _safe_int(payload.get("story_band"), 0),
            "zone_label": _safe_text(payload.get("zone_label")),
            "member_type": _safe_text(payload.get("member_type")),
            "semantic_group": _safe_text(payload.get("semantic_group")),
            "action_name": _safe_text(payload.get("action_name")),
            "action_family": _safe_text(payload.get("action_family")) or _safe_text(ACTION_FAMILY_BY_NAME.get(_safe_text(payload.get("action_name")), "")),
            "baseline_focus_member_id": _safe_text(payload.get("baseline_focus_member_id")),
            "member_id": _safe_text(payload.get("member_id")) or _safe_text(payload.get("baseline_focus_member_id")),
            "case_id": _safe_text(payload.get("case_id")) or _safe_text(payload.get("member_id")) or _safe_text(payload.get("baseline_focus_member_id")),
            "combination_name": _safe_text(payload.get("combination_name")),
            "governing_clause_label": _safe_text(payload.get("governing_clause_label")) or _safe_text(payload.get("governing_clause")),
            "recommended_results_card": _safe_text(payload.get("recommended_results_card")) or "envelope",
            "recommended_results_series_index": _safe_int(payload.get("recommended_results_series_index"), 0),
            "recommended_results_card_label": _safe_text(payload.get("recommended_results_card_label")) or "Results Explorer",
            "recommended_results_series_label": _safe_text(payload.get("recommended_results_series_label")) or "trace",
            "recommended_results_reason_label": _safe_text(payload.get("recommended_results_reason_label")) or "cost-reduction reverse sync",
            "viewer_row_ref": _safe_text(payload.get("viewer_row_ref")),
            "row_ref": _safe_text(payload.get("row_ref")) or _safe_text(payload.get("viewer_row_ref")),
            "projected_cost_delta": _safe_float(payload.get("projected_cost_delta"), 0.0),
            "max_dcr": _safe_float(payload.get("max_dcr"), 0.0),
        }
        reverse_sync_payload["viewer_row_url"] = _build_cost_reduction_viewer_url(
            row={**payload, **reverse_sync_payload},
            focus_mode="member",
        )
        reverse_sync_payload["viewer_slice_url"] = _build_cost_reduction_viewer_url(
            row={**payload, **reverse_sync_payload},
            focus_mode="group",
        )
        reverse_sync_rows.append(reverse_sync_payload)
    return reverse_sync_rows


def _apply_cost_reduction_reverse_sync(
    *,
    rows: list[dict[str, object]],
    reverse_sync_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    preferred_by_exact: dict[tuple[str, int, str, int, str], dict[str, object]] = {}
    preferred_by_group: dict[tuple[str, int], dict[str, object]] = {}
    for row in sorted(
        reverse_sync_rows,
        key=lambda item: (
            0 if bool(item.get("selected_in_final_loop", False)) else 1,
            _safe_int(item.get("selected_event_index"), 0),
            -_safe_float(item.get("projected_cost_delta"), 0.0),
        ),
    ):
        exact_key = (
            _safe_text(row.get("group_id")),
            _safe_int(row.get("group_index"), -1),
            _safe_text(row.get("action_name")),
            _safe_int(row.get("selected_event_index"), 0),
            _safe_text(row.get("member_id")) or _safe_text(row.get("baseline_focus_member_id")),
        )
        preferred_by_exact.setdefault(exact_key, row)
        group_key = (_safe_text(row.get("group_id")), _safe_int(row.get("group_index"), -1))
        preferred_by_group.setdefault(group_key, row)

    enriched_rows: list[dict[str, object]] = []
    for row in rows:
        payload = dict(row)
        exact_key = (
            _safe_text(payload.get("group_id")),
            _safe_int(payload.get("group_index"), -1),
            _safe_text(payload.get("action_name")),
            _safe_int(payload.get("selected_event_index"), 0),
            _safe_text(payload.get("member_id")) or _safe_text(payload.get("baseline_focus_member_id")),
        )
        reverse_sync = preferred_by_exact.get(exact_key)
        if reverse_sync is None:
            reverse_sync = preferred_by_group.get((_safe_text(payload.get("group_id")), _safe_int(payload.get("group_index"), -1)))
        if reverse_sync is None:
            enriched_rows.append(payload)
            continue
        if not _safe_text(payload.get("viewer_row_url")):
            payload["viewer_row_url"] = _safe_text(reverse_sync.get("viewer_row_url"))
        if not _safe_text(payload.get("viewer_slice_url")):
            payload["viewer_slice_url"] = _safe_text(reverse_sync.get("viewer_slice_url"))
        if not _safe_text(payload.get("viewer_overlay_row_id")):
            payload["viewer_overlay_row_id"] = _safe_text(reverse_sync.get("viewer_overlay_row_id"))
        if not _safe_text(payload.get("reverse_sync_row_ref")):
            payload["reverse_sync_row_ref"] = _safe_text(reverse_sync.get("reverse_sync_row_ref"))
        enriched_rows.append(payload)
    return enriched_rows


def _overlay_action_masks_from_dataset(
    *,
    state: dict[str, np.ndarray],
    dataset_npz_path: Path | None,
) -> dict[str, np.ndarray]:
    if dataset_npz_path is None or not dataset_npz_path.exists():
        return state
    dataset = _load_npz(dataset_npz_path)
    ds_group_ids = np.asarray(dataset.get("unique_group_ids", np.asarray([], dtype="<U1")))
    ds_action_mask = np.asarray(dataset.get("action_mask", np.zeros((0, 2), dtype=np.bool_)), dtype=np.bool_)
    ds_action_mask_ext = np.asarray(dataset.get("action_mask_extended", np.zeros((0, 6), dtype=np.bool_)), dtype=np.bool_)
    if ds_group_ids.size == 0:
        return state
    lookup = {str(g): i for i, g in enumerate(ds_group_ids.tolist())}
    def _alternate_group_id(gid: str) -> str | None:
        text = str(gid)
        if ":slab:" in text:
            return text.replace(":slab:", ":wall:", 1)
        if ":wall:" in text:
            return text.replace(":wall:", ":slab:", 1)
        return None
    group_index_per_member = np.asarray(dataset.get("group_index_per_member", np.zeros(0, dtype=np.int32)), dtype=np.int32)
    ds_zone_per_group = np.asarray(
        dataset.get(
            "zone_label_per_group",
            np.asarray([], dtype="<U32")
            if group_index_per_member.size == 0
            else np.asarray([""] * ds_group_ids.shape[0], dtype="<U32"),
        )
    )
    ds_semantic_per_group = np.asarray(
        dataset.get(
            "semantic_group_per_group",
            np.asarray([], dtype="<U96")
            if group_index_per_member.size == 0
            else np.asarray([""] * ds_group_ids.shape[0], dtype="<U96"),
        )
    )
    ds_section_signature_per_group = np.asarray(
        dataset.get(
            "section_signature_per_group",
            np.asarray([], dtype="<U128")
            if group_index_per_member.size == 0
            else np.asarray([""] * ds_group_ids.shape[0], dtype="<U128"),
        )
    )
    ds_story_band_per_group = np.asarray(
        dataset.get(
            "story_band_per_group",
            np.asarray([], dtype=np.int32)
            if group_index_per_member.size == 0
            else np.zeros(ds_group_ids.shape[0], dtype=np.int32),
        ),
        dtype=np.int32,
    )
    signature_lookup_raw: dict[tuple[int, str, str, str], list[int]] = {}
    if ds_group_ids.size:
        if ds_zone_per_group.size == 0 and "zone_labels" in dataset:
            zone_src = np.asarray(dataset["zone_labels"])
            ds_zone_per_group = np.asarray([""] * ds_group_ids.shape[0], dtype="<U32")
            for val, gi in zip(zone_src.tolist(), group_index_per_member.tolist()):
                gi = int(gi)
                if not str(ds_zone_per_group[gi]):
                    ds_zone_per_group[gi] = str(val)
        if ds_semantic_per_group.size == 0 and "semantic_groups" in dataset:
            semantic_src = np.asarray(dataset["semantic_groups"])
            ds_semantic_per_group = np.asarray([""] * ds_group_ids.shape[0], dtype="<U96")
            for val, gi in zip(semantic_src.tolist(), group_index_per_member.tolist()):
                gi = int(gi)
                if not str(ds_semantic_per_group[gi]):
                    ds_semantic_per_group[gi] = str(val)
        if ds_section_signature_per_group.size == 0 and "section_signatures" in dataset:
            section_src = np.asarray(dataset["section_signatures"])
            ds_section_signature_per_group = np.asarray([""] * ds_group_ids.shape[0], dtype="<U128")
            for val, gi in zip(section_src.tolist(), group_index_per_member.tolist()):
                gi = int(gi)
                if not str(ds_section_signature_per_group[gi]):
                    ds_section_signature_per_group[gi] = str(val)
        if ds_story_band_per_group.size == 0 and "story_band_index" in dataset:
            story_src = np.asarray(dataset["story_band_index"], dtype=np.int32)
            ds_story_band_per_group = np.zeros(ds_group_ids.shape[0], dtype=np.int32)
            filled = np.zeros(ds_group_ids.shape[0], dtype=np.bool_)
            for val, gi in zip(story_src.tolist(), group_index_per_member.tolist()):
                gi = int(gi)
                if not bool(filled[gi]):
                    ds_story_band_per_group[gi] = int(val)
                    filled[gi] = True
        for j in range(ds_group_ids.shape[0]):
            sig = (
                int(ds_story_band_per_group[j]) if j < ds_story_band_per_group.shape[0] else 0,
                str(ds_zone_per_group[j]) if j < ds_zone_per_group.shape[0] else "",
                str(ds_semantic_per_group[j]) if j < ds_semantic_per_group.shape[0] else "",
                str(ds_section_signature_per_group[j]) if j < ds_section_signature_per_group.shape[0] else "",
            )
            signature_lookup_raw.setdefault(sig, []).append(j)
    signature_lookup = {sig: indices[0] for sig, indices in signature_lookup_raw.items() if len(indices) == 1}
    state_group_ids = np.asarray(state.get("group_ids", np.asarray([], dtype="<U1")))
    updated = {k: np.asarray(v).copy() for k, v in state.items()}
    if state_group_ids.size == 0:
        return updated
    mask = np.asarray(updated.get("action_mask", np.zeros((state_group_ids.size, 2), dtype=np.bool_)), dtype=np.bool_)
    mask_ext = np.asarray(updated.get("action_mask_extended", np.zeros((state_group_ids.size, 6), dtype=np.bool_)), dtype=np.bool_)
    state_zone = np.asarray(updated.get("zone_label", np.asarray([""] * state_group_ids.shape[0])), dtype="<U32")
    state_semantic = np.asarray(updated.get("semantic_group", np.asarray([""] * state_group_ids.shape[0])), dtype="<U96")
    state_section_signature = np.asarray(updated.get("section_signature", np.asarray([""] * state_group_ids.shape[0])), dtype="<U128")
    state_story_band = np.asarray(updated.get("story_band", np.zeros(state_group_ids.shape[0], dtype=np.int32)), dtype=np.int32)
    for i, gid in enumerate(state_group_ids.tolist()):
        j = lookup.get(str(gid))
        if j is None:
            alt_gid = _alternate_group_id(str(gid))
            if alt_gid is not None:
                j = lookup.get(alt_gid)
        if j is None:
            j = signature_lookup.get(
                (
                    int(state_story_band[i]),
                    str(state_zone[i]),
                    str(state_semantic[i]),
                    str(state_section_signature[i]),
                )
            )
        if j is None:
            continue
        if j < ds_action_mask.shape[0]:
            mask[i, :] = ds_action_mask[j, :]
        if j < ds_action_mask_ext.shape[0]:
            mask_ext[i, :] = ds_action_mask_ext[j, :]
    group_index_per_member = np.asarray(dataset.get("group_index_per_member", np.zeros(0, dtype=np.int32)), dtype=np.int32)
    if group_index_per_member.size:
        def _mean_by_group(values: np.ndarray) -> np.ndarray:
            out = np.zeros(ds_group_ids.shape[0], dtype=np.float64)
            counts = np.zeros(ds_group_ids.shape[0], dtype=np.int32)
            for value, gi in zip(values.tolist(), group_index_per_member.tolist()):
                out[int(gi)] += float(value)
                counts[int(gi)] += 1
            counts = np.maximum(counts, 1)
            return out / counts

        def _first_by_group(values: np.ndarray) -> np.ndarray:
            out = np.empty(ds_group_ids.shape[0], dtype=values.dtype)
            filled = np.zeros(ds_group_ids.shape[0], dtype=np.bool_)
            for value, gi in zip(values.tolist(), group_index_per_member.tolist()):
                gi = int(gi)
                if not bool(filled[gi]):
                    out[gi] = value
                    filled[gi] = True
            return out

        overlay_sources: dict[str, np.ndarray] = {}
        numeric_member_fields = {
            "congestion": "congestion_index",
            "detailing": "detailing_violation_ratio",
            "constructability_score": "constructability_score",
            "detailing_complexity_score": "detailing_complexity_score",
            "anchorage_complexity_score": "anchorage_complexity_score",
            "splice_burden_score": "splice_burden_score",
            "overdesign_margin_score": "overdesign_margin_score",
            "material_reduction_potential_score": "material_reduction_potential_score",
        }
        string_group_fields = {
            "member_type": ("member_type_per_group", "member_types"),
            "zone_label": ("zone_label_per_group", "zone_labels"),
            "semantic_group": ("semantic_group_per_group", "semantic_groups"),
        }
        for target_key, source_key in numeric_member_fields.items():
            if source_key in dataset:
                overlay_sources[target_key] = _mean_by_group(np.asarray(dataset[source_key], dtype=np.float64))
        for target_key, (group_key, member_key) in string_group_fields.items():
            if group_key in dataset:
                overlay_sources[target_key] = np.asarray(dataset[group_key])
            elif member_key in dataset:
                overlay_sources[target_key] = _first_by_group(np.asarray(dataset[member_key]))
        if "story_band_index" in dataset:
            overlay_sources["story_band"] = np.asarray(
                dataset.get(
                    "story_band_per_group",
                    _first_by_group(np.asarray(dataset["story_band_index"], dtype=np.int32)),
                ),
                dtype=np.int32,
            )

        for key, source_arr in overlay_sources.items():
            target = np.asarray(updated.get(key, source_arr.copy()))
            if target.shape[0] != state_group_ids.shape[0]:
                target = source_arr.copy()
            else:
                target = target.copy()
            for i, gid in enumerate(state_group_ids.tolist()):
                j = lookup.get(str(gid))
                if j is None:
                    alt_gid = _alternate_group_id(str(gid))
                    if alt_gid is not None:
                        j = lookup.get(alt_gid)
                if j is None:
                    j = signature_lookup.get(
                        (
                            int(state_story_band[i]),
                            str(state_zone[i]),
                            str(state_semantic[i]),
                            str(state_section_signature[i]),
                        )
                    )
                if j is None or j >= source_arr.shape[0]:
                    continue
                target[i] = source_arr[j]
            updated[key] = target
    updated["action_mask"] = mask
    updated["action_mask_extended"] = mask_ext
    return updated


def _refine_action_masks_for_current_state(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> dict[str, np.ndarray]:
    updated = {k: np.asarray(v).copy() for k, v in state.items()}
    group_ids = np.asarray(updated.get("group_ids", np.asarray([], dtype="<U1")))
    if group_ids.size == 0:
        return updated
    def _coerce_1d(values: object, *, fill_value: object, dtype: object) -> np.ndarray:
        arr = np.asarray(values, dtype=dtype).reshape(-1)
        if arr.size == group_ids.size:
            return arr
        out = np.full(group_ids.size, fill_value, dtype=dtype)
        copy_n = min(arr.size, group_ids.size)
        if copy_n:
            out[:copy_n] = arr[:copy_n]
        return out
    mask_ext = np.asarray(
        updated.get("action_mask_extended", np.ones((group_ids.size, 6), dtype=np.bool_)),
        dtype=np.bool_,
    ).copy()
    max_dcr = _coerce_1d(updated.get("max_dcr", np.zeros(group_ids.size, dtype=np.float64)), fill_value=0.0, dtype=np.float64)
    rebar_ratio = _coerce_1d(updated.get("rebar_ratio", np.zeros(group_ids.size, dtype=np.float64)), fill_value=0.0, dtype=np.float64)
    thickness_scale = _coerce_1d(updated.get("thickness_scale", np.ones(group_ids.size, dtype=np.float64)), fill_value=1.0, dtype=np.float64)
    detailing_quality = _coerce_1d(updated.get("detailing_quality", np.ones(group_ids.size, dtype=np.float64)), fill_value=1.0, dtype=np.float64)
    detail_ratio = _coerce_1d(updated.get("detailing", np.zeros(group_ids.size, dtype=np.float64)), fill_value=0.0, dtype=np.float64)
    constructability_score = _coerce_1d(updated.get("constructability_score", np.zeros(group_ids.size, dtype=np.float64)), fill_value=0.0, dtype=np.float64)
    detailing_complexity_score = _coerce_1d(updated.get("detailing_complexity_score", detail_ratio), fill_value=0.0, dtype=np.float64)
    robustness_margin = _coerce_1d(updated.get("robustness_margin", np.zeros(group_ids.size, dtype=np.float64)), fill_value=0.0, dtype=np.float64)
    member_type = _coerce_1d(updated.get("member_type", np.asarray([""] * group_ids.size)), fill_value="", dtype="<U32")
    zone_label = _coerce_1d(updated.get("zone_label", np.asarray([""] * group_ids.size)), fill_value="", dtype="<U32")
    story_band = _coerce_1d(updated.get("story_band", np.zeros(group_ids.size, dtype=np.int32)), fill_value=0, dtype=np.int32)
    semantic_group = _coerce_1d(updated.get("semantic_group", np.asarray([""] * group_ids.size)), fill_value="", dtype="<U96")

    rebar_floor = float(cfg.min_rebar_ratio) + 0.5 * float(cfg.rebar_step)
    thick_floor = 0.80 + 0.5 * float(cfg.thickness_step)
    detail_floor = 0.60 + 0.5 * float(cfg.detailing_step)
    dcr_soft_caps = {
        "beam": {"rebar_down": 0.12, "thickness_down": 0.10, "detailing_down": 0.08},
        "slab": {"rebar_down": 0.18, "thickness_down": 0.15, "detailing_down": 0.10},
        "wall": {"rebar_down": 0.14, "thickness_down": 0.11, "detailing_down": 0.08},
        "column": {"rebar_down": 0.08, "thickness_down": 0.06, "detailing_down": 0.05},
        "foundation": {"rebar_down": 0.10, "thickness_down": 0.0, "detailing_down": 0.06},
        "connection": {"rebar_down": -1.0, "thickness_down": -1.0, "detailing_down": 0.04},
    }
    connection_detailing_seed = np.zeros(group_ids.size, dtype=np.bool_)
    perimeter_frame_seed = np.zeros(group_ids.size, dtype=np.bool_)

    for gi in range(group_ids.size):
        mt = str(member_type[gi]).strip().lower()
        zone = str(zone_label[gi]).strip().lower()
        sb = int(story_band[gi])
        cur_dcr = float(max_dcr[gi])
        robust = float(robustness_margin[gi])
        cur_detail = float(detail_ratio[gi])
        cur_constructability = float(constructability_score[gi])
        cur_detail_complexity = float(detailing_complexity_score[gi])
        cur_detail_quality = float(detailing_quality[gi])
        caps = dcr_soft_caps.get(mt, dcr_soft_caps["beam"])
        connection_detail_quality_ok = (
            cur_detail_quality > 0.62
            or (
                cur_detail_quality >= 0.54
                and cur_detail >= 0.95
                and cur_detail_complexity >= 0.64
                and cur_constructability >= 0.44
            )
        )
        connection_detail_pressure_ok = cur_detail < 0.86 or (
            cur_detail >= 0.95
            and cur_detail_complexity >= 0.64
            and cur_constructability >= 0.44
        )
        perimeter_frame_quality_ok = (
            cur_detail_quality > detail_floor
            or (
                cur_detail_quality >= 0.54
                and cur_detail >= 0.95
                and cur_detail_complexity >= 0.64
                and cur_constructability >= 0.46
            )
        )
        high_detail_pressure = (
            cur_detail >= 0.95
            and cur_detail_complexity >= 0.64
            and cur_constructability >= 0.44
        )
        wall_perimeter_detailing_relief = (
            mt == "wall"
            and zone == "perimeter"
            and sb >= 2
            and robust > 0.10
            and cur_dcr <= 0.98
            and cur_detail >= 0.95
            and cur_detail_complexity >= 0.64
            and cur_constructability >= 0.40
        )
        allow_core_transfer_thickness = high_detail_pressure and mt in {"beam", "column"} and zone in {"core", "transfer"}
        allow_core_rebar = high_detail_pressure and mt in {"beam", "column"} and zone == "core"

        if cur_dcr > float(cfg.dcr_limit) + 1.0e-9:
            continue
        if mt == "connection":
            if (
                cur_detail_quality > detail_floor
                and cur_dcr <= caps["detailing_down"]
                and cur_detail < 0.10
            ):
                mask_ext[gi, 4] = True
            continue

        if (
            float(rebar_ratio[gi]) > rebar_floor
            and cur_dcr <= caps["rebar_down"]
            and robust > 0.08
            and (
                allow_core_rebar
                or not (mt == "column" and zone in {"core", "transfer"})
            )
        ):
            mask_ext[gi, 0] = True
        if (
            float(thickness_scale[gi]) > thick_floor
            and caps["thickness_down"] > 0.0
            and cur_dcr <= caps["thickness_down"]
            and robust > 0.06
            and (
                allow_core_transfer_thickness
                or not (mt in {"beam", "column"} and zone == "transfer")
            )
            and (
                allow_core_transfer_thickness
                or not (mt == "beam" and zone == "core")
            )
        ):
            mask_ext[gi, 2] = True
        if (
            (cur_detail_quality > detail_floor or high_detail_pressure or wall_perimeter_detailing_relief)
            and (cur_dcr <= caps["detailing_down"] or wall_perimeter_detailing_relief)
            and (cur_detail < 0.90 or high_detail_pressure or wall_perimeter_detailing_relief)
        ):
            if not (mt in {"column", "wall"} and zone == "core" and sb <= 1):
                mask_ext[gi, 4] = True
        if (
            mt in {"beam", "column"}
            and zone in {"core", "perimeter", "transfer"}
            and robust > 0.05
            and cur_dcr <= 0.98
            and connection_detail_quality_ok
            and connection_detail_pressure_ok
            and cur_detail_complexity > 0.16
            and cur_constructability > 0.14
        ):
            mask_ext[gi, 4] = True
            connection_detailing_seed[gi] = True
        if (
            mt == "column"
            and zone == "perimeter"
            and robust > 0.07
            and cur_dcr <= 0.98
            and cur_detail_complexity > 0.18
            and cur_constructability > 0.12
            and perimeter_frame_quality_ok
        ):
            perimeter_frame_seed[gi] = True

    updated["action_mask_extended"] = mask_ext
    mask = np.asarray(updated.get("action_mask", np.zeros((group_ids.size, 2), dtype=np.bool_)), dtype=np.bool_).copy()
    mask[:, 0] = mask_ext[:, 0]
    mask[:, 1] = mask_ext[:, 1]
    updated["action_mask"] = mask
    action_names_v2 = [str(v) for v in np.asarray(updated.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    if action_names_v2:
        mask_v2 = np.asarray(
            updated.get("action_mask_v2", np.zeros((group_ids.size, len(action_names_v2)), dtype=np.bool_)),
            dtype=np.bool_,
        ).copy()
        beam_or_column_target = np.isin(member_type, np.asarray(["beam", "column"])) & np.isin(
            zone_label,
            np.asarray(["core", "perimeter", "transfer"]),
        )
        detailing_v2_mask = np.asarray(mask_ext[:, 4], dtype=np.bool_).copy()
        connection_v2_mask = np.asarray(mask_ext[:, 4], dtype=np.bool_).copy() & beam_or_column_target & connection_detailing_seed
        # Keep generic detailing for non-connection groups so connection_detailing is not swallowed by detailing.
        detailing_v2_mask[connection_v2_mask] = False

        action_mask_map: dict[str, np.ndarray] = {
            "rebar_down": np.asarray(mask_ext[:, 0], dtype=np.bool_),
            "beam_section_down": np.asarray(mask_ext[:, 2], dtype=np.bool_) & (member_type == "beam"),
            "wall_thickness_down": np.asarray(mask_ext[:, 2], dtype=np.bool_) & (member_type == "wall"),
            "slab_thickness_down": np.asarray(mask_ext[:, 2], dtype=np.bool_) & (member_type == "slab"),
            "core_wall_down": np.asarray(mask_ext[:, 2], dtype=np.bool_) & (member_type == "wall") & (zone_label == "core"),
            "coupling_beam_down": np.asarray(mask_ext[:, 2], dtype=np.bool_)
            & (member_type == "beam")
            & np.asarray(["coupling" in str(v).strip().lower() for v in semantic_group], dtype=np.bool_),
            "perimeter_frame_down": perimeter_frame_seed,
            "connection_detailing_down": connection_v2_mask,
            "detailing_down": detailing_v2_mask,
        }
        for action_name, action_values in action_mask_map.items():
            idx = ACTION_INDEX_V2.get(action_name)
            if idx is None or idx >= mask_v2.shape[1]:
                continue
            mask_v2[:, idx] = np.asarray(action_values, dtype=np.bool_)
        updated["action_mask_v2"] = mask_v2
    return updated


def _blocked_preview_family_name(row: dict[str, object]) -> str:
    action_name = str(row.get("action_name", "")).strip()
    member_type = str(row.get("member_type", "")).strip().lower()
    zone_label = str(row.get("zone_label", "")).strip().lower()
    semantic_group = str(row.get("semantic_group", "")).strip().lower()
    if action_name == "thickness_down":
        if member_type == "wall":
            return "wall_thickness"
        if member_type == "slab":
            return "slab_thickness"
        if member_type == "beam":
            return "beam_section"
        if member_type == "column":
            return "column_section"
    if action_name == "rebar_down":
        if member_type == "beam" and "coupling" in semantic_group:
            return "coupling_beam"
        if member_type == "column" and zone_label == "perimeter":
            return "perimeter_frame"
    return str(ACTION_FAMILY_BY_NAME.get(action_name, action_name))


def _build_action_block_report(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    max_groups: int = 16,
) -> list[dict[str, object]]:
    return _build_action_block_report_impl(
        state=state,
        cfg=cfg,
        ndtha_step_count=ndtha_step_count,
        solver_stage_state_fn=_solver_stage_state,
        local_dcr_update_fn=_local_dcr_update,
        max_groups=max_groups,
    )


def _aggregate_no_cost_gain_rows(blocked_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return _aggregate_no_cost_gain_rows_impl(blocked_rows)


def _parse_projected_cost_delta(detail_text: str) -> float:
    return _parse_projected_cost_delta_impl(detail_text)


def _aggregate_no_cost_gain_explain_rows(
    *,
    blocked_rows: list[dict[str, object]],
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> list[dict[str, object]]:
    return _aggregate_no_cost_gain_explain_rows_impl(
        blocked_rows=blocked_rows,
        state=state,
        cfg=cfg,
    )


def _aggregate_accepted_candidate_explain_rows(
    *,
    blocked_rows: list[dict[str, object]],
    accepted_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    return _aggregate_accepted_candidate_explain_rows_impl(
        blocked_rows=blocked_rows,
        accepted_rows=accepted_rows,
    )


def _selected_reason(row: dict[str, object]) -> str:
    return _selected_reason_impl(row)


def _rejected_reason(row: dict[str, object]) -> str:
    return _rejected_reason_impl(row)


def _group_state_lookup(state: dict[str, np.ndarray], group_index: int) -> dict[str, object]:
    return _group_state_lookup_impl(state, group_index)


def _build_explain_schema_v2_rows(
    *,
    baseline_state: dict[str, np.ndarray],
    final_state: dict[str, np.ndarray],
    blocked_rows: list[dict[str, object]],
    accepted_candidate_rows: list[dict[str, object]],
    budget_mode: str,
    objective_profile: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    return _build_explain_schema_v2_rows_impl(
        baseline_state=baseline_state,
        final_state=final_state,
        blocked_rows=blocked_rows,
        accepted_candidate_rows=accepted_candidate_rows,
        budget_mode=budget_mode,
        objective_profile=objective_profile,
    )


def _evaluate_cost_down_candidate(
    *,
    state: dict[str, np.ndarray],
    current_solver: dict[str, object],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    group_index: int,
    action_name: str,
) -> dict[str, object] | None:
    return _evaluate_cost_down_candidate_impl(
        state=state,
        current_solver=current_solver,
        cfg=cfg,
        ndtha_step_count=ndtha_step_count,
        group_index=group_index,
        action_name=action_name,
        solver_stage_state_fn=_solver_stage_state,
        local_dcr_update_fn=_local_dcr_update,
    )


def _cost_down_actions_for_group(*, state: dict[str, np.ndarray], group_index: int) -> list[str]:
    return _cost_down_actions_for_group_impl(state=state, group_index=group_index)


def _preview_cost_down_candidate(
    *,
    state: dict[str, np.ndarray],
    current_solver: dict[str, object],
    cfg: DesignOptimizationConfig,
    group_index: int,
    action_name: str,
) -> dict[str, object] | None:
    return _preview_cost_down_candidate_impl(
        state=state,
        current_solver=current_solver,
        cfg=cfg,
        group_index=group_index,
        action_name=action_name,
    )


def run_cost_reduction_only(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    max_iterations: int,
    batch_limit: int = 3,
) -> dict[str, object]:
    return run_cost_reduction_selection(
        state=state,
        cfg=cfg,
        ndtha_step_count=ndtha_step_count,
        max_iterations=max_iterations,
        batch_limit=batch_limit,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_action_masks_for_current_state,
        evaluate_candidate_fn=_evaluate_cost_down_candidate,
        preview_candidate_fn=_preview_cost_down_candidate,
        cost_down_actions_for_group_fn=_cost_down_actions_for_group,
    )


def _budget_stage_b_defaults(budget_mode: str) -> tuple[int, int]:
    budget = str(budget_mode or "").strip().lower()
    if budget == "low":
        return 8, 2
    if budget == "medium":
        return 16, 4
    return 32, 8


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--solver-loop-report",
        default=SOLVER_LOOP_LONG_REPORT_JSON,
    )
    p.add_argument(
        "--state-npz",
        default=SOLVER_LOOP_LONG_STATE_NPZ,
    )
    p.add_argument(
        "--out",
        default=COST_REDUCTION_REPORT_JSON,
    )
    p.add_argument(
        "--changes-json-out",
        default=COST_REDUCTION_CHANGES_JSON,
    )
    p.add_argument(
        "--changes-csv-out",
        default=COST_REDUCTION_CHANGES_CSV,
    )
    p.add_argument(
        "--changes-summary-json-out",
        default=COST_REDUCTION_CHANGES_SUMMARY_JSON,
    )
    p.add_argument(
        "--changes-summary-csv-out",
        default=COST_REDUCTION_CHANGES_SUMMARY_CSV,
    )
    p.add_argument(
        "--dataset-npz",
        default=DATASET_NPZ,
    )
    p.add_argument(
        "--row-provenance-report",
        default=DEFAULT_ROW_PROVENANCE_REPORT_JSON,
    )
    p.add_argument(
        "--row-provenance-csv",
        default=DEFAULT_ROW_PROVENANCE_CSV,
    )
    p.add_argument(
        "--blocked-actions-json-out",
        default=COST_REDUCTION_BLOCKED_ACTIONS_JSON,
    )
    p.add_argument(
        "--blocked-actions-csv-out",
        default=COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    )
    p.add_argument(
        "--blocked-no-cost-json-out",
        default=COST_REDUCTION_NO_GAIN_GROUPS_JSON,
    )
    p.add_argument(
        "--blocked-no-cost-csv-out",
        default=COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    )
    p.add_argument(
        "--blocked-no-cost-explain-json-out",
        default=COST_REDUCTION_NO_GAIN_EXPLAIN_JSON,
    )
    p.add_argument(
        "--blocked-no-cost-explain-csv-out",
        default=COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    )
    p.add_argument(
        "--accepted-candidate-explain-json-out",
        default=ACCEPTED_CANDIDATE_EXPLAIN_JSON,
    )
    p.add_argument(
        "--accepted-candidate-explain-csv-out",
        default=ACCEPTED_CANDIDATE_EXPLAIN_CSV,
    )
    p.add_argument(
        "--reverse-sync-json-out",
        default=COST_REDUCTION_REVERSE_SYNC_JSON,
    )
    p.add_argument(
        "--reverse-sync-csv-out",
        default=COST_REDUCTION_REVERSE_SYNC_CSV,
    )
    p.add_argument(
        "--candidate-explain-v2-json-out",
        default=CANDIDATE_EXPLAIN_V2_JSON,
    )
    p.add_argument(
        "--candidate-explain-v2-csv-out",
        default=CANDIDATE_EXPLAIN_V2_CSV,
    )
    p.add_argument(
        "--rejected-candidate-explain-v2-json-out",
        default=REJECTED_CANDIDATE_EXPLAIN_V2_JSON,
    )
    p.add_argument(
        "--rejected-candidate-explain-v2-csv-out",
        default=REJECTED_CANDIDATE_EXPLAIN_V2_CSV,
    )
    p.add_argument("--max-iterations", type=int, default=None)
    p.add_argument("--ndtha-step-count", type=int, default=64)
    p.add_argument(
        "--objective-calibration-report",
        default=OBJECTIVE_CALIBRATION_REPORT_JSON,
    )
    p.add_argument("--objective-profile", default="balanced_practice")
    p.add_argument("--budget-mode", default="high")
    p.add_argument("--batch-limit", type=int, default=None)
    p.add_argument(
        "--run-delivery-hooks",
        action="store_true",
        help="After writing changes, run member_alignment enrich + delivery evidence bundle.",
    )
    p.add_argument(
        "--baseline-json-for-delivery",
        default="implementation/phase1/open_data/midas/midas_generator_33.json",
    )
    p.add_argument(
        "--optimized-roundtrip-json-for-delivery",
        default="implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    p.add_argument(
        "--delivery-bundle-out",
        default="implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json",
    )
    args = p.parse_args()

    loop_report = _load_json(Path(args.solver_loop_report))
    inputs = loop_report.get("inputs", {}) if isinstance(loop_report.get("inputs"), dict) else {}
    cfg = DesignOptimizationConfig(
        rebar_step=float(inputs.get("rebar_step", 0.002)),
        thickness_step=float(inputs.get("thickness_step", 0.01)),
        detailing_step=float(inputs.get("detailing_step", 0.03)),
        min_rebar_ratio=float(inputs.get("min_rebar_ratio", 0.004)),
        max_rebar_ratio=float(inputs.get("max_rebar_ratio", 0.08)),
        max_iterations=int(inputs.get("max_iterations", 64)),
        dcr_limit=float(inputs.get("dcr_limit", 1.0)),
        drift_limit_pct=float(inputs.get("drift_limit_pct", 2.0)),
        residual_drift_limit_pct=float(inputs.get("residual_drift_limit_pct", 0.5)),
    )
    calibration_report = _load_json(Path(args.objective_calibration_report))
    cfg = apply_objective_calibration(cfg, calibration_report)
    cfg = apply_objective_profile(cfg, profile_name=str(args.objective_profile))
    raw_dataset = _load_npz(Path(args.dataset_npz))
    raw_state = aggregate_group_state(raw_dataset)
    state = _load_npz(Path(args.state_npz))
    state = _overlay_action_masks_from_dataset(
        state=state,
        dataset_npz_path=Path(args.dataset_npz) if str(args.dataset_npz).strip() else None,
    )
    default_max_iterations, default_batch_limit = _budget_stage_b_defaults(str(args.budget_mode))
    max_iterations = int(args.max_iterations) if args.max_iterations is not None else int(default_max_iterations)
    batch_limit = int(args.batch_limit) if args.batch_limit is not None else int(default_batch_limit)

    result = run_cost_reduction_only(
        state=state,
        cfg=cfg,
        ndtha_step_count=int(args.ndtha_step_count),
        max_iterations=max_iterations,
        batch_limit=batch_limit,
    )
    viewer_enrichment_by_group = _build_cost_reduction_viewer_enrichment(
        dataset=raw_dataset,
        row_provenance_report_path=Path(args.row_provenance_report) if _safe_text(args.row_provenance_report) else None,
        row_provenance_csv_path=Path(args.row_provenance_csv) if _safe_text(args.row_provenance_csv) else None,
    )
    result["accepted"] = _apply_cost_reduction_viewer_enrichment(
        rows=list(result["accepted"]),
        enrichment_by_group=viewer_enrichment_by_group,
    )
    baseline_solver = result["baseline_solver"]
    final_solver = result["final_solver"]
    baseline_state = result["baseline_state"]
    final_state = result["final_state"]
    gpu_strict_solver_backends = bool(solver_backends_gpu_strict(baseline_solver) and solver_backends_gpu_strict(final_solver))
    repair_action_names: list[str] = []
    for head_key in (
        "stage1_accepted_head",
        "stage1_extra_accepted_head",
        "stage1_dcr_accepted_head",
        "stage1_dcr_final_accepted_head",
        "stage2_accepted_head",
    ):
        for row in (loop_report.get(head_key) or []):
            if not isinstance(row, dict):
                continue
            action_name = str(row.get("action_name", "")).strip()
            if action_name and action_name not in repair_action_names:
                repair_action_names.append(action_name)
    blocked = bool(result["blocked"])
    changes: list[dict[str, object]] = []
    base_ids = np.asarray(baseline_state["group_ids"])
    base_rebar = np.asarray(baseline_state["rebar_ratio"], dtype=np.float64)
    base_cost = np.asarray(baseline_state["group_cost_proxy"], dtype=np.float64)
    base_dcr = np.asarray(baseline_state["max_dcr"], dtype=np.float64)
    final_rebar = np.asarray(final_state["rebar_ratio"], dtype=np.float64)
    final_cost = np.asarray(final_state["group_cost_proxy"], dtype=np.float64)
    final_dcr = np.asarray(final_state["max_dcr"], dtype=np.float64)
    base_thickness = np.asarray(baseline_state.get("thickness_scale", np.ones_like(base_rebar)), dtype=np.float64)
    final_thickness = np.asarray(final_state.get("thickness_scale", np.ones_like(final_rebar)), dtype=np.float64)
    base_detailing_q = np.asarray(baseline_state.get("detailing_quality", np.ones_like(base_rebar)), dtype=np.float64)
    final_detailing_q = np.asarray(final_state.get("detailing_quality", np.ones_like(final_rebar)), dtype=np.float64)
    base_member_type = np.asarray(baseline_state["member_type"])
    base_zone = np.asarray(baseline_state["zone_label"])
    base_story_band = np.asarray(baseline_state["story_band"], dtype=np.int32)
    base_semantic_group = np.asarray(baseline_state.get("semantic_group", np.asarray([""] * base_ids.shape[0])))
    base_section = np.asarray(baseline_state.get("section_name", np.asarray([""] * base_ids.shape[0])))
    base_gov_clause = np.asarray(baseline_state.get("member_governing_clause", np.asarray([""] * base_ids.shape[0])))
    final_gov_dcr = np.asarray(final_state.get("member_governing_dcr", final_dcr), dtype=np.float64)
    base_gov_dcr = np.asarray(baseline_state.get("member_governing_dcr", base_dcr), dtype=np.float64)
    base_constructability = np.asarray(baseline_state.get("constructability_score", np.zeros_like(base_rebar)), dtype=np.float64)
    final_constructability = np.asarray(final_state.get("constructability_score", np.zeros_like(final_rebar)), dtype=np.float64)
    base_detailing_complexity = np.asarray(
        baseline_state.get("detailing_complexity_score", baseline_state.get("detailing", np.zeros_like(base_rebar))),
        dtype=np.float64,
    )
    final_detailing_complexity = np.asarray(
        final_state.get("detailing_complexity_score", final_state.get("detailing", np.zeros_like(final_rebar))),
        dtype=np.float64,
    )
    base_overdesign = np.maximum(1.0 - base_dcr, 0.0) * np.maximum(base_cost, 1.0)
    final_overdesign = np.maximum(1.0 - final_dcr, 0.0) * np.maximum(final_cost, 1.0)
    accepted_meta_by_group: dict[str, dict[str, object]] = {}
    for row in result["accepted"]:
        accepted_meta_by_group[str(row.get("group_id", ""))] = dict(row)
    for i in range(base_ids.shape[0]):
        if (
            abs(float(final_rebar[i]) - float(base_rebar[i])) <= 1.0e-12
            and abs(float(final_thickness[i]) - float(base_thickness[i])) <= 1.0e-12
            and abs(float(final_detailing_q[i]) - float(base_detailing_q[i])) <= 1.0e-12
        ):
            continue
        accepted_meta = accepted_meta_by_group.get(str(base_ids[i]), {})
        action_family = str(accepted_meta.get("action_family", "") or "")
        action_name = str(accepted_meta.get("action_name", "") or "")
        if not action_family:
            if abs(float(final_thickness[i]) - float(base_thickness[i])) > 1.0e-12:
                action_family = "wall_thickness" if str(base_member_type[i]).strip().lower() == "wall" else "beam_section" if str(base_member_type[i]).strip().lower() == "beam" else "thickness"
            elif abs(float(final_rebar[i]) - float(base_rebar[i])) > 1.0e-12:
                action_family = "rebar"
            elif abs(float(final_detailing_q[i]) - float(base_detailing_q[i])) > 1.0e-12:
                action_family = "detailing"
        changes.append(
            {
                "group_id": str(base_ids[i]),
                "group_index": int(i),
                "story_band": int(base_story_band[i]),
                "zone_label": str(base_zone[i]),
                "member_type": str(base_member_type[i]),
                "semantic_group": str(base_semantic_group[i]),
                "action_name": str(action_name),
                "action_family": str(action_family),
                "before_section": str(base_section[i]),
                "after_section": str(base_section[i]),
                "before_rebar_ratio": float(base_rebar[i]),
                "after_rebar_ratio": float(final_rebar[i]),
                "rebar_ratio_delta": float(final_rebar[i] - base_rebar[i]),
                "before_thickness_scale": float(base_thickness[i]),
                "after_thickness_scale": float(final_thickness[i]),
                "before_detailing_quality": float(base_detailing_q[i]),
                "after_detailing_quality": float(final_detailing_q[i]),
                "cost_proxy_before": float(base_cost[i]),
                "cost_proxy_after": float(final_cost[i]),
                "cost_proxy_delta": float(final_cost[i] - base_cost[i]),
                "max_dcr_before": float(base_dcr[i]),
                "max_dcr_after": float(final_dcr[i]),
                "max_dcr_delta": float(final_dcr[i] - base_dcr[i]),
                "governing_member_governing_dcr_before": float(base_gov_dcr[i]),
                "governing_member_governing_dcr_after": float(final_gov_dcr[i]),
                "governing_clause": str(base_gov_clause[i]),
                "drift_before_pct": float(baseline_solver["max_drift_pct"]),
                "drift_after_pct": float(final_solver["max_drift_pct"]),
                "residual_before_pct": float(baseline_solver["residual_drift_pct"]),
                "residual_after_pct": float(final_solver["residual_drift_pct"]),
                "before_constructability": float(base_constructability[i]),
                "after_constructability": float(final_constructability[i]),
                "before_detailing_complexity": float(base_detailing_complexity[i]),
                "after_detailing_complexity": float(final_detailing_complexity[i]),
                "constructability_delta": float(final_constructability[i] - base_constructability[i]),
                "overdesign_margin_delta": float(final_overdesign[i] - base_overdesign[i]),
                "selection_gate": "hard_gate_pass",
                "reason_selected": str(accepted_meta.get("reason_selected", "selected_best_gain_in_batch")),
            }
        )
    changes.sort(key=lambda row: abs(float(row["cost_proxy_delta"])), reverse=True)
    summary_buckets: dict[tuple[int, str, str], dict[str, object]] = {}
    for row in changes:
        key = (int(row["story_band"]), str(row["zone_label"]), str(row["member_type"]))
        bucket = summary_buckets.setdefault(
            key,
            {
                "story_band": int(row["story_band"]),
                "zone_label": str(row["zone_label"]),
                "member_type": str(row["member_type"]),
                "changed_group_count": 0,
                "semantic_group_count": 0,
                "rebar_ratio_delta_sum": 0.0,
                "cost_proxy_delta_sum": 0.0,
                "constructability_before_sum": 0.0,
                "constructability_after_sum": 0.0,
                "detailing_complexity_before_sum": 0.0,
                "detailing_complexity_after_sum": 0.0,
                "constructability_delta_sum": 0.0,
                "overdesign_margin_delta_sum": 0.0,
                "max_dcr_before_max": 0.0,
                "max_dcr_after_max": 0.0,
                "selection_gate": "hard_gate_pass",
            },
        )
        bucket["changed_group_count"] = int(bucket["changed_group_count"]) + 1
        bucket["semantic_group_count"] = int(bucket["semantic_group_count"]) + (1 if str(row["semantic_group"]).strip() else 0)
        bucket["rebar_ratio_delta_sum"] = float(bucket["rebar_ratio_delta_sum"]) + float(row["rebar_ratio_delta"])
        bucket["cost_proxy_delta_sum"] = float(bucket["cost_proxy_delta_sum"]) + float(row["cost_proxy_delta"])
        bucket["constructability_before_sum"] = float(bucket["constructability_before_sum"]) + float(row["before_constructability"])
        bucket["constructability_after_sum"] = float(bucket["constructability_after_sum"]) + float(row["after_constructability"])
        bucket["detailing_complexity_before_sum"] = float(bucket["detailing_complexity_before_sum"]) + float(row["before_detailing_complexity"])
        bucket["detailing_complexity_after_sum"] = float(bucket["detailing_complexity_after_sum"]) + float(row["after_detailing_complexity"])
        bucket["constructability_delta_sum"] = float(bucket["constructability_delta_sum"]) + float(row["constructability_delta"])
        bucket["overdesign_margin_delta_sum"] = float(bucket["overdesign_margin_delta_sum"]) + float(row["overdesign_margin_delta"])
        bucket["max_dcr_before_max"] = max(float(bucket["max_dcr_before_max"]), float(row["max_dcr_before"]))
        bucket["max_dcr_after_max"] = max(float(bucket["max_dcr_after_max"]), float(row["max_dcr_after"]))
    for bucket in summary_buckets.values():
        denom = max(int(bucket["changed_group_count"]), 1)
        bucket["constructability_before_avg"] = float(bucket["constructability_before_sum"]) / float(denom)
        bucket["constructability_after_avg"] = float(bucket["constructability_after_sum"]) / float(denom)
        bucket["detailing_complexity_before_avg"] = float(bucket["detailing_complexity_before_sum"]) / float(denom)
        bucket["detailing_complexity_after_avg"] = float(bucket["detailing_complexity_after_sum"]) / float(denom)
        bucket.pop("constructability_before_sum", None)
        bucket.pop("constructability_after_sum", None)
        bucket.pop("detailing_complexity_before_sum", None)
        bucket.pop("detailing_complexity_after_sum", None)
    change_summary_rows = sorted(
        summary_buckets.values(),
        key=lambda item: (int(item["story_band"]), str(item["zone_label"]), str(item["member_type"])),
    )
    blocked_rows = _build_action_block_report(
        state=baseline_state,
        cfg=cfg,
        ndtha_step_count=int(args.ndtha_step_count),
        max_groups=16,
    )
    blocked_no_cost_rows = _aggregate_no_cost_gain_rows(blocked_rows)
    blocked_no_cost_explain_rows = _aggregate_no_cost_gain_explain_rows(
        blocked_rows=blocked_rows,
        state=baseline_state,
        cfg=cfg,
    )
    accepted_candidate_explain_rows = _aggregate_accepted_candidate_explain_rows(
        blocked_rows=blocked_rows,
        accepted_rows=list(result["accepted"]),
    )
    accepted_candidate_explain_rows = _apply_cost_reduction_viewer_enrichment(
        rows=accepted_candidate_explain_rows,
        enrichment_by_group=viewer_enrichment_by_group,
    )
    reverse_sync_rows = _build_cost_reduction_reverse_sync_rows(
        rows=accepted_candidate_explain_rows,
    )
    accepted_candidate_explain_rows = _apply_cost_reduction_reverse_sync(
        rows=accepted_candidate_explain_rows,
        reverse_sync_rows=reverse_sync_rows,
    )
    result["accepted"] = _apply_cost_reduction_reverse_sync(
        rows=list(result["accepted"]),
        reverse_sync_rows=reverse_sync_rows,
    )
    accepted_candidate_explain_rows_v2, rejected_candidate_explain_rows_v2 = _build_explain_schema_v2_rows(
        baseline_state=baseline_state,
        final_state=final_state,
        blocked_rows=blocked_rows,
        accepted_candidate_rows=accepted_candidate_explain_rows,
        budget_mode=str(args.budget_mode),
        objective_profile=str(args.objective_profile),
    )
    blocked_reason_counts: dict[str, int] = {}
    for row in blocked_rows:
        key = str(row.get("block_reason", ""))
        blocked_reason_counts[key] = int(blocked_reason_counts.get(key, 0)) + 1
    blocked_hard_gate_family_counts: dict[str, int] = {}
    for row in blocked_rows:
        if not str(row.get("block_reason", "")).startswith("constructability_hard_gate:"):
            continue
        family = _blocked_preview_family_name(row)
        blocked_hard_gate_family_counts[family] = int(blocked_hard_gate_family_counts.get(family, 0)) + 1
    blocked_hard_gate_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(blocked_hard_gate_family_counts.items())
    )
    blocked_illegal_by_mask_family_counts: dict[str, int] = {}
    for row in blocked_rows:
        if str(row.get("block_reason", "")) != "illegal_by_mask":
            continue
        family = _blocked_preview_family_name(row)
        blocked_illegal_by_mask_family_counts[family] = int(blocked_illegal_by_mask_family_counts.get(family, 0)) + 1
    blocked_illegal_by_mask_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(blocked_illegal_by_mask_family_counts.items())
    )
    previous_summary: dict[str, object] = {}
    out_path = Path(args.out)
    if out_path.exists():
        try:
            previous_report = _load_json(out_path)
            if isinstance(previous_report.get("summary"), dict):
                previous_summary = dict(previous_report["summary"])
        except Exception:
            previous_summary = {}
    accepted_action_family_counts: dict[str, int] = {}
    accepted_constructability_positive_count = 0
    for row in result["accepted"]:
        family = str(row.get("action_family", ACTION_FAMILY_BY_NAME.get(str(row.get("action_name", "")), str(row.get("action_name", "")))))
        accepted_action_family_counts[family] = int(accepted_action_family_counts.get(family, 0)) + 1
        if float(row.get("constructability_gain", 0.0) or 0.0) > 0.0:
            accepted_constructability_positive_count += 1
    previous_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((previous_summary.get("accepted_action_family_counts") or {}).items())
    }
    selected_action_family_delta_counts = {
        family: int(accepted_action_family_counts.get(family, 0)) - int(previous_action_family_counts.get(family, 0))
        for family in sorted(set(accepted_action_family_counts) | set(previous_action_family_counts))
    }
    selected_action_family_trend_label = ", ".join(
        f"{family}={selected_action_family_delta_counts[family]:+d}" for family in sorted(selected_action_family_delta_counts)
    )
    selected_family_mix_label = ", ".join(
        f"{family}={count}" for family, count in sorted(accepted_action_family_counts.items())
    )
    if accepted_action_family_counts:
        selected_dominant_family, selected_dominant_family_count = max(
            accepted_action_family_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
        selected_dominant_family_ratio = float(selected_dominant_family_count) / max(float(sum(accepted_action_family_counts.values())), 1.0)
    else:
        selected_dominant_family = ""
        selected_dominant_family_ratio = 0.0
    if previous_action_family_counts:
        previous_dominant_family, previous_dominant_family_count = max(
            previous_action_family_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
        previous_dominant_family_ratio = float(previous_dominant_family_count) / max(float(sum(previous_action_family_counts.values())), 1.0)
    else:
        previous_dominant_family = ""
        previous_dominant_family_ratio = 0.0
    baseline_volume = float(np.sum(np.asarray(baseline_state.get("thickness_scale", np.ones(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    final_volume = float(np.sum(np.asarray(final_state.get("thickness_scale", np.ones(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    baseline_rebar_total = float(np.sum(base_rebar))
    final_rebar_total = float(np.sum(final_rebar))
    baseline_congestion = float(np.mean(np.asarray(baseline_state.get("congestion", np.zeros(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    final_congestion = float(np.mean(np.asarray(final_state.get("congestion", np.zeros(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    baseline_detail_complexity = float(np.mean(np.asarray(baseline_state.get("detailing_complexity_score", baseline_state.get("detailing", np.zeros(base_ids.shape[0], dtype=np.float64))), dtype=np.float64)))
    final_detail_complexity = float(np.mean(np.asarray(final_state.get("detailing_complexity_score", final_state.get("detailing", np.zeros(base_ids.shape[0], dtype=np.float64))), dtype=np.float64)))
    baseline_overdesign = float(np.sum(np.maximum(1.0 - np.asarray(base_dcr, dtype=np.float64), 0.0) * np.maximum(base_cost, 1.0)))
    final_overdesign = float(np.sum(np.maximum(1.0 - np.asarray(final_dcr, dtype=np.float64), 0.0) * np.maximum(final_cost, 1.0)))
    safety_margin_retained = float(np.clip((1.0 - float(final_solver["max_dcr"])) / max(1.0 - float(baseline_solver["max_dcr"]), 1.0e-6), 0.0, 1.5))
    baseline_constructability = float(np.mean(np.asarray(baseline_state.get("constructability_score", np.zeros(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    final_constructability = float(np.mean(np.asarray(final_state.get("constructability_score", np.zeros(base_ids.shape[0], dtype=np.float64)), dtype=np.float64)))
    write_design_optimization_report(
        out_path,
        run_id="phase1-design-optimization-cost-reduction",
        summary={
            "feasible_input": bool(baseline_solver["feasible"]),
            "blocked": blocked,
            "accepted_count": int(len(result["accepted"])),
            "changed_group_count": int(len(changes)),
            "changed_summary_row_count": int(len(change_summary_rows)),
            "blocked_action_row_count": int(len(blocked_rows)),
            "blocked_no_cost_group_count": int(len(blocked_no_cost_rows)),
            "blocked_no_cost_explain_row_count": int(len(blocked_no_cost_explain_rows)),
            "accepted_candidate_explain_row_count": int(len(accepted_candidate_explain_rows)),
            "accepted_candidate_selected_count": int(sum(1 for row in accepted_candidate_explain_rows if bool(row.get("selected_in_final_loop", False)))),
            "accepted_candidate_unselected_count": int(sum(1 for row in accepted_candidate_explain_rows if not bool(row.get("selected_in_final_loop", False)))),
            "accepted_viewer_row_ref_count": int(sum(1 for row in result["accepted"] if _safe_text(row.get("viewer_row_ref")))),
            "accepted_candidate_viewer_row_ref_count": int(sum(1 for row in accepted_candidate_explain_rows if _safe_text(row.get("viewer_row_ref")))),
            "accepted_viewer_overlay_row_id_count": int(sum(1 for row in result["accepted"] if _safe_text(row.get("viewer_overlay_row_id")))),
            "accepted_candidate_viewer_overlay_row_id_count": int(sum(1 for row in accepted_candidate_explain_rows if _safe_text(row.get("viewer_overlay_row_id")))),
            "accepted_viewer_row_url_count": int(sum(1 for row in result["accepted"] if _safe_text(row.get("viewer_row_url")))),
            "accepted_candidate_viewer_row_url_count": int(sum(1 for row in accepted_candidate_explain_rows if _safe_text(row.get("viewer_row_url")))),
            "reverse_sync_row_count": int(len(reverse_sync_rows)),
            "reverse_sync_selected_row_count": int(sum(1 for row in reverse_sync_rows if bool(row.get("selected_in_final_loop", False)))),
            "accepted_candidate_recommended_results_count": int(
                sum(1 for row in accepted_candidate_explain_rows if _safe_text(row.get("recommended_results_card")))
            ),
            "candidate_explain_v2_selected_count": int(len(accepted_candidate_explain_rows_v2)),
            "candidate_explain_v2_rejected_count": int(len(rejected_candidate_explain_rows_v2)),
            "accepted_action_family_counts": {str(k): int(v) for k, v in sorted(accepted_action_family_counts.items())},
            "preview_supply_family_counts": {str(k): int(v) for k, v in sorted((result.get("preview_supply_family_counts") or {}).items())},
            "preview_evaluated_family_counts": {str(k): int(v) for k, v in sorted((result.get("preview_evaluated_family_counts") or {}).items())},
            "previous_accepted_action_family_counts": previous_action_family_counts,
            "selected_action_family_delta_counts": {str(k): int(v) for k, v in sorted(selected_action_family_delta_counts.items())},
            "selected_action_family_trend_label": str(selected_action_family_trend_label),
            "selected_family_mix_label": str(selected_family_mix_label),
            "selected_dominant_family": str(selected_dominant_family),
            "selected_dominant_family_ratio": float(selected_dominant_family_ratio),
            "previous_selected_dominant_family": str(previous_dominant_family),
            "previous_selected_dominant_family_ratio": float(previous_dominant_family_ratio),
            "accepted_constructability_positive_count": int(accepted_constructability_positive_count),
            "blocked_reason_counts": {str(k): int(v) for k, v in sorted(blocked_reason_counts.items())},
            "blocked_illegal_by_mask_family_counts": {str(k): int(v) for k, v in sorted(blocked_illegal_by_mask_family_counts.items())},
            "blocked_illegal_by_mask_family_label": str(blocked_illegal_by_mask_family_label),
            "blocked_constructability_hard_gate_family_counts": {str(k): int(v) for k, v in sorted(blocked_hard_gate_family_counts.items())},
            "blocked_constructability_hard_gate_family_label": str(blocked_hard_gate_family_label),
            "baseline_cost_proxy": float(baseline_solver["cost_proxy"]),
            "final_cost_proxy": float(final_solver["cost_proxy"]),
            "cost_reduction_proxy": float(baseline_solver["cost_proxy"] - final_solver["cost_proxy"]),
            "baseline_max_dcr": float(baseline_solver["max_dcr"]),
            "final_max_dcr": float(final_solver["max_dcr"]),
            "baseline_max_drift_pct": float(baseline_solver["max_drift_pct"]),
            "final_max_drift_pct": float(final_solver["max_drift_pct"]),
            "baseline_residual_drift_pct": float(baseline_solver["residual_drift_pct"]),
            "final_residual_drift_pct": float(final_solver["residual_drift_pct"]),
            "raw_max_drift_pct": float(np.asarray(raw_state["global_drift_pct"], dtype=np.float64)[0]),
            "raw_residual_drift_pct": float(np.asarray(raw_state["global_residual_drift_pct"], dtype=np.float64)[0]),
            "raw_max_dcr": float(np.max(np.asarray(raw_state["max_dcr"], dtype=np.float64))),
            "repaired_input_max_drift_pct": float(baseline_solver["max_drift_pct"]),
            "repaired_input_residual_drift_pct": float(baseline_solver["residual_drift_pct"]),
            "repaired_input_max_dcr": float(baseline_solver["max_dcr"]),
            "repaired_final_max_drift_pct": float(final_solver["max_drift_pct"]),
            "repaired_final_residual_drift_pct": float(final_solver["residual_drift_pct"]),
            "repaired_final_max_dcr": float(final_solver["max_dcr"]),
            "compliance_basis": "repaired_solver_validated_slice",
            "repair_actions_applied": list(repair_action_names),
            "repair_action_count": int(len(repair_action_names)),
            "concrete_usage_reduction_pct": float(max((baseline_volume - final_volume) / max(baseline_volume, 1.0e-9), 0.0) * 100.0),
            "rebar_reduction_pct": float(max((baseline_rebar_total - final_rebar_total) / max(baseline_rebar_total, 1.0e-9), 0.0) * 100.0),
            "steel_reduction_pct": float(max((baseline_rebar_total - final_rebar_total) / max(baseline_rebar_total, 1.0e-9), 0.0) * 100.0),
            "congestion_reduction_pct": float(max((baseline_congestion - final_congestion) / max(baseline_congestion, 1.0e-9), 0.0) * 100.0),
            "detailing_simplification_pct": float(max((baseline_detail_complexity - final_detail_complexity) / max(baseline_detail_complexity, 1.0e-9), 0.0) * 100.0),
            "baseline_constructability_avg": float(baseline_constructability),
            "final_constructability_avg": float(final_constructability),
            "baseline_detailing_complexity_avg": float(baseline_detail_complexity),
            "final_detailing_complexity_avg": float(final_detail_complexity),
            "constructability_signal_gain_pct": float(max((baseline_constructability - final_constructability) / max(baseline_constructability, 1.0e-9), 0.0) * 100.0),
            "overdesign_margin_reduction_pct": float(max((baseline_overdesign - final_overdesign) / max(baseline_overdesign, 1.0e-9), 0.0) * 100.0),
            "final_safety_margin_retained_pct": float(safety_margin_retained * 100.0),
            "solver_backend_static": str(final_solver["backend_static"]),
            "solver_backend_ndtha": str(final_solver["backend_ndtha"]),
            "gpu_strict_solver_backends": bool(gpu_strict_solver_backends),
            "objective_calibration_applied": bool(calibration_report),
            "objective_profile": str(args.objective_profile),
            "budget_mode": str(args.budget_mode),
        },
        inputs={
            "solver_loop_report": str(args.solver_loop_report),
            "state_npz": str(args.state_npz),
            "changes_json_out": str(args.changes_json_out),
            "changes_csv_out": str(args.changes_csv_out),
            "changes_summary_json_out": str(args.changes_summary_json_out),
            "changes_summary_csv_out": str(args.changes_summary_csv_out),
            "dataset_npz": str(args.dataset_npz),
            "row_provenance_report": str(args.row_provenance_report),
            "row_provenance_csv": str(args.row_provenance_csv),
            "blocked_actions_json_out": str(args.blocked_actions_json_out),
            "blocked_actions_csv_out": str(args.blocked_actions_csv_out),
            "blocked_no_cost_json_out": str(args.blocked_no_cost_json_out),
            "blocked_no_cost_csv_out": str(args.blocked_no_cost_csv_out),
            "blocked_no_cost_explain_json_out": str(args.blocked_no_cost_explain_json_out),
            "blocked_no_cost_explain_csv_out": str(args.blocked_no_cost_explain_csv_out),
            "accepted_candidate_explain_json_out": str(args.accepted_candidate_explain_json_out),
            "accepted_candidate_explain_csv_out": str(args.accepted_candidate_explain_csv_out),
            "reverse_sync_json_out": str(args.reverse_sync_json_out),
            "reverse_sync_csv_out": str(args.reverse_sync_csv_out),
            "max_iterations": int(max_iterations),
            "effective_max_iterations": int(max_iterations),
            "effective_batch_limit": int(batch_limit),
            "ndtha_step_count": int(args.ndtha_step_count),
            "objective_calibration_report": str(args.objective_calibration_report),
            "objective_profile": str(args.objective_profile),
            "budget_mode": str(args.budget_mode),
        },
        artifacts={
            "changes_json": str(args.changes_json_out),
            "changes_csv": str(args.changes_csv_out),
            "changes_summary_json": str(args.changes_summary_json_out),
            "changes_summary_csv": str(args.changes_summary_csv_out),
            "blocked_actions_json": str(args.blocked_actions_json_out),
            "blocked_actions_csv": str(args.blocked_actions_csv_out),
            "blocked_no_cost_json": str(args.blocked_no_cost_json_out),
            "blocked_no_cost_csv": str(args.blocked_no_cost_csv_out),
            "blocked_no_cost_explain_json": str(args.blocked_no_cost_explain_json_out),
            "blocked_no_cost_explain_csv": str(args.blocked_no_cost_explain_csv_out),
            "accepted_candidate_explain_json": str(args.accepted_candidate_explain_json_out),
            "accepted_candidate_explain_csv": str(args.accepted_candidate_explain_csv_out),
            "reverse_sync_json": str(args.reverse_sync_json_out),
            "reverse_sync_csv": str(args.reverse_sync_csv_out),
            "candidate_explain_v2_json": str(args.candidate_explain_v2_json_out),
            "candidate_explain_v2_csv": str(args.candidate_explain_v2_csv_out),
            "rejected_candidate_explain_v2_json": str(args.rejected_candidate_explain_v2_json_out),
            "rejected_candidate_explain_v2_csv": str(args.rejected_candidate_explain_v2_csv_out),
            "report_out": str(args.out),
        },
        contract_pass=bool((not blocked) and bool(final_solver["feasible"]) and float(final_solver["cost_proxy"]) <= float(baseline_solver["cost_proxy"]) + 1.0e-9 and gpu_strict_solver_backends),
        reason_code=("ERR_CPU_BACKEND" if not gpu_strict_solver_backends else ("ERR_NOT_FEASIBLE" if blocked else "PASS")),
        reason=(
            "cost-reduction-only loop completed on GPU-strict backends"
            if (not blocked) and gpu_strict_solver_backends
            else ("cpu backend or fallback detected in solver path" if not gpu_strict_solver_backends else "input state is not feasible; cost reduction blocked")
        ),
        extra={"accepted_head": list(result["accepted"][:32])},
    )
    write_cost_reduction_support_artifacts(
        changes_json_out=args.changes_json_out,
        changes_csv_out=args.changes_csv_out,
        changes_summary_json_out=args.changes_summary_json_out,
        changes_summary_csv_out=args.changes_summary_csv_out,
        blocked_actions_json_out=args.blocked_actions_json_out,
        blocked_actions_csv_out=args.blocked_actions_csv_out,
        blocked_no_cost_json_out=args.blocked_no_cost_json_out,
        blocked_no_cost_csv_out=args.blocked_no_cost_csv_out,
        blocked_no_cost_explain_json_out=args.blocked_no_cost_explain_json_out,
        blocked_no_cost_explain_csv_out=args.blocked_no_cost_explain_csv_out,
        accepted_candidate_explain_json_out=args.accepted_candidate_explain_json_out,
        accepted_candidate_explain_csv_out=args.accepted_candidate_explain_csv_out,
        reverse_sync_json_out=args.reverse_sync_json_out,
        reverse_sync_csv_out=args.reverse_sync_csv_out,
        candidate_explain_v2_json_out=args.candidate_explain_v2_json_out,
        candidate_explain_v2_csv_out=args.candidate_explain_v2_csv_out,
        rejected_candidate_explain_v2_json_out=args.rejected_candidate_explain_v2_json_out,
        rejected_candidate_explain_v2_csv_out=args.rejected_candidate_explain_v2_csv_out,
        changes=changes,
        change_summary_rows=change_summary_rows,
        blocked_rows=blocked_rows,
        blocked_no_cost_rows=blocked_no_cost_rows,
        blocked_no_cost_explain_rows=blocked_no_cost_explain_rows,
        accepted_candidate_explain_rows=accepted_candidate_explain_rows,
        reverse_sync_contract_version=COST_REDUCTION_REVERSE_SYNC_CONTRACT_VERSION,
        reverse_sync_rows=reverse_sync_rows,
        accepted_candidate_explain_rows_v2=accepted_candidate_explain_rows_v2,
        rejected_candidate_explain_rows_v2=rejected_candidate_explain_rows_v2,
    )
    out = Path(args.out)
    print(f"Wrote design optimization cost reduction report: {out}")

    if args.run_delivery_hooks:
        from run_post_cost_reduction_delivery_hooks import run_delivery_hooks

        repo_root = Path(__file__).resolve().parents[2]
        hook_result = run_delivery_hooks(
            repo_root=repo_root,
            changes_json=Path(args.changes_json_out),
            baseline_json=Path(args.baseline_json_for_delivery),
            optimized_roundtrip_json=Path(args.optimized_roundtrip_json_for_delivery),
            bundle_output=Path(args.delivery_bundle_out),
        )
        print(f"Delivery hooks: {hook_result.get('status')} -> {hook_result.get('bundle_output')}")


if __name__ == "__main__":
    main()
