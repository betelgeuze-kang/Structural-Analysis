#!/usr/bin/env python3
"""Structured explain schema helpers for design optimization reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


EXPLAIN_SCHEMA_VERSION = "2.0"

SELECTION_REASONS = {
    "selected_best_gain_in_batch",
    "selected_constructability_gain_after_cost_pass",
    "selected_feasibility_repair",
    "selected_repeat_event_after_revalidation",
}

REJECTION_REASONS = {
    "rejected_lower_cost_gain",
    "rejected_robustness_loss",
    "rejected_detailing_penalty_increase",
    "rejected_detailing_hard_gate",
    "rejected_congestion_hard_gate",
    "rejected_constructability_hard_gate",
    "rejected_anchorage_hard_gate",
    "rejected_splice_hard_gate",
    "rejected_multi_hazard_margin_too_low",
    "rejected_same_group_family_already_selected",
    "rejected_batch_budget_limit",
    "rejected_feasibility_loss",
    "rejected_no_action_delta",
    "rejected_illegal_by_mask",
}

EXPLAIN_FIELD_ORDER = [
    "candidate_id",
    "stage",
    "budget_mode",
    "objective_profile",
    "group_id",
    "group_index",
    "story_band",
    "zone_label",
    "member_type",
    "semantic_group",
    "action_name",
    "action_family",
    "selected_in_final_loop",
    "selected_event_index",
    "current_max_dcr",
    "trial_max_dcr",
    "final_max_dcr",
    "current_cost",
    "trial_cost",
    "delta_cost",
    "current_drift_pct",
    "trial_drift_pct",
    "current_residual_drift_pct",
    "trial_residual_drift_pct",
    "current_congestion",
    "trial_congestion",
    "current_detailing_complexity",
    "trial_detailing_complexity",
    "current_constructability",
    "trial_constructability",
    "current_robustness_margin",
    "trial_robustness_margin",
    "current_multi_hazard_margin",
    "trial_multi_hazard_margin",
    "current_member_governing_dcr",
    "trial_member_governing_dcr",
    "current_member_governing_clause",
    "trial_member_governing_clause",
    "reason_selected",
    "reason_rejected",
    "detail",
]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def build_explain_row(
    *,
    candidate_id: str,
    stage: str,
    budget_mode: str,
    objective_profile: str,
    group_id: str,
    group_index: int,
    story_band: int,
    zone_label: str,
    member_type: str,
    semantic_group: str,
    action_name: str,
    action_family: str,
    selected_in_final_loop: bool,
    selected_event_index: int,
    current_max_dcr: Any,
    trial_max_dcr: Any,
    final_max_dcr: Any,
    current_cost: Any,
    trial_cost: Any,
    delta_cost: Any,
    current_drift_pct: Any,
    trial_drift_pct: Any,
    current_residual_drift_pct: Any,
    trial_residual_drift_pct: Any,
    current_congestion: Any,
    trial_congestion: Any,
    current_detailing_complexity: Any,
    trial_detailing_complexity: Any,
    current_constructability: Any,
    trial_constructability: Any,
    current_robustness_margin: Any,
    trial_robustness_margin: Any,
    current_multi_hazard_margin: Any,
    trial_multi_hazard_margin: Any,
    current_member_governing_dcr: Any,
    trial_member_governing_dcr: Any,
    current_member_governing_clause: str,
    trial_member_governing_clause: str,
    reason_selected: str = "",
    reason_rejected: str = "",
    detail: str = "",
) -> dict[str, Any]:
    row = {
        "candidate_id": str(candidate_id),
        "stage": str(stage),
        "budget_mode": str(budget_mode),
        "objective_profile": str(objective_profile),
        "group_id": str(group_id),
        "group_index": _as_int(group_index),
        "story_band": _as_int(story_band),
        "zone_label": str(zone_label),
        "member_type": str(member_type),
        "semantic_group": str(semantic_group),
        "action_name": str(action_name),
        "action_family": str(action_family),
        "selected_in_final_loop": bool(selected_in_final_loop),
        "selected_event_index": _as_int(selected_event_index),
        "current_max_dcr": _as_float(current_max_dcr),
        "trial_max_dcr": _as_float(trial_max_dcr),
        "final_max_dcr": _as_float(final_max_dcr),
        "current_cost": _as_float(current_cost),
        "trial_cost": _as_float(trial_cost),
        "delta_cost": _as_float(delta_cost),
        "current_drift_pct": _as_float(current_drift_pct),
        "trial_drift_pct": _as_float(trial_drift_pct),
        "current_residual_drift_pct": _as_float(current_residual_drift_pct),
        "trial_residual_drift_pct": _as_float(trial_residual_drift_pct),
        "current_congestion": _as_float(current_congestion),
        "trial_congestion": _as_float(trial_congestion),
        "current_detailing_complexity": _as_float(current_detailing_complexity),
        "trial_detailing_complexity": _as_float(trial_detailing_complexity),
        "current_constructability": _as_float(current_constructability),
        "trial_constructability": _as_float(trial_constructability),
        "current_robustness_margin": _as_float(current_robustness_margin),
        "trial_robustness_margin": _as_float(trial_robustness_margin),
        "current_multi_hazard_margin": _as_float(current_multi_hazard_margin),
        "trial_multi_hazard_margin": _as_float(trial_multi_hazard_margin),
        "current_member_governing_dcr": _as_float(current_member_governing_dcr),
        "trial_member_governing_dcr": _as_float(trial_member_governing_dcr),
        "current_member_governing_clause": str(current_member_governing_clause),
        "trial_member_governing_clause": str(trial_member_governing_clause),
        "reason_selected": str(reason_selected),
        "reason_rejected": str(reason_rejected),
        "detail": str(detail),
    }
    return row


def validate_explain_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mismatch_count = 0
    invalid_reason_rows = 0
    for row in rows:
        selected = bool(row.get("selected_in_final_loop", False))
        reason_selected = str(row.get("reason_selected", ""))
        reason_rejected = str(row.get("reason_rejected", ""))
        if selected:
            if not reason_selected or reason_selected not in SELECTION_REASONS:
                invalid_reason_rows += 1
            if reason_rejected:
                invalid_reason_rows += 1
        else:
            if not reason_rejected or reason_rejected not in REJECTION_REASONS:
                invalid_reason_rows += 1
            if reason_selected:
                invalid_reason_rows += 1
        current = _as_float(row.get("current_max_dcr", 0.0))
        trial = _as_float(row.get("trial_max_dcr", 0.0))
        final = _as_float(row.get("final_max_dcr", 0.0))
        if current < 0.0 or trial < 0.0 or final < 0.0:
            mismatch_count += 1
    return {
        "schema_version": EXPLAIN_SCHEMA_VERSION,
        "row_count": int(len(rows)),
        "mismatch_count": int(mismatch_count),
        "invalid_reason_rows": int(invalid_reason_rows),
        "contract_pass": bool(mismatch_count == 0 and invalid_reason_rows == 0),
    }


def write_explain_json(path: Path, *, key: str, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": EXPLAIN_SCHEMA_VERSION,
        key: rows,
        "validation": validate_explain_rows(rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_explain_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPLAIN_FIELD_ORDER)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in EXPLAIN_FIELD_ORDER})


__all__ = [
    "EXPLAIN_FIELD_ORDER",
    "EXPLAIN_SCHEMA_VERSION",
    "REJECTION_REASONS",
    "SELECTION_REASONS",
    "build_explain_row",
    "validate_explain_rows",
    "write_explain_csv",
    "write_explain_json",
]
