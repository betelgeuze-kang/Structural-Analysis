"""Explain/reporting helpers for bounded design-optimization refactor."""

from __future__ import annotations


import numpy as np

from implementation.phase1.design_optimization_env import ACTION_FAMILY_BY_NAME
from implementation.phase1.design_optimization_explain_schema import build_explain_row


def selected_reason(row: dict[str, object]) -> str:
    if float(row.get("constructability_gain", 0.0) or 0.0) > 1.0e-9:
        return "selected_constructability_gain_after_cost_pass"
    return "selected_repeat_event_after_revalidation" if int(row.get("selected_event_index", 0) or 0) > 1 else "selected_best_gain_in_batch"


def rejected_reason(row: dict[str, object]) -> str:
    legacy = str(row.get("explain_reason", row.get("block_reason", "")))
    if legacy.startswith("constructability_hard_gate:"):
        subreason = legacy.split(":", 1)[1]
        if subreason.startswith("detailing_"):
            return "rejected_detailing_hard_gate"
        if subreason.startswith("congestion_"):
            return "rejected_congestion_hard_gate"
        if subreason.startswith("constructability_"):
            return "rejected_constructability_hard_gate"
        if subreason.startswith("anchorage_"):
            return "rejected_anchorage_hard_gate"
        if subreason.startswith("splice_"):
            return "rejected_splice_hard_gate"
        return "rejected_constructability_hard_gate"
    if legacy in {"dominated_by_higher_gain_candidate_or_batch_budget", "selected_in_batch_loop_repeat"}:
        return "rejected_batch_budget_limit"
    if legacy == "illegal_by_mask":
        return "rejected_illegal_by_mask"
    if legacy == "violates_feasible_constraints":
        return "rejected_feasibility_loss"
    if legacy == "no_action_delta":
        return "rejected_no_action_delta"
    if legacy == "no_cost_gain":
        return "rejected_lower_cost_gain"
    return "rejected_lower_cost_gain"


def group_state_lookup(state: dict[str, np.ndarray], group_index: int) -> dict[str, object]:
    gi = int(group_index)
    group_count = np.asarray(state["group_ids"]).shape[0]
    return {
        "group_id": str(np.asarray(state["group_ids"])[gi]),
        "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[gi]),
        "zone_label": str(np.asarray(state["zone_label"])[gi]),
        "member_type": str(np.asarray(state["member_type"])[gi]),
        "semantic_group": str(np.asarray(state.get("semantic_group", np.asarray([""] * group_count)))[gi]),
        "section_name": str(np.asarray(state.get("section_name", np.asarray([""] * group_count)))[gi]),
        "section_signature": str(np.asarray(state.get("section_signature", np.asarray([""] * group_count)))[gi]),
        "current_max_dcr": float(np.asarray(state["max_dcr"], dtype=np.float64)[gi]),
        "current_cost": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[gi]),
        "current_congestion": float(np.asarray(state.get("congestion", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)[gi]),
        "current_detailing_complexity": float(np.asarray(state.get("detailing_complexity_score", state.get("detailing", np.zeros(group_count, dtype=np.float64))), dtype=np.float64)[gi]),
        "current_constructability": float(np.asarray(state.get("constructability_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)[gi]),
        "current_robustness_margin": float(np.asarray(state.get("robustness_margin", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)[gi]),
        "current_multi_hazard_margin": float(np.asarray(state.get("multi_hazard_margin", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)[gi]),
        "current_member_governing_dcr": float(np.asarray(state.get("member_governing_dcr", state["max_dcr"]), dtype=np.float64)[gi]),
        "current_member_governing_clause": str(np.asarray(state.get("member_governing_clause", np.asarray([""] * group_count)))[gi]),
    }


def build_explain_schema_v2_rows(
    *,
    baseline_state: dict[str, np.ndarray],
    final_state: dict[str, np.ndarray],
    blocked_rows: list[dict[str, object]],
    accepted_candidate_rows: list[dict[str, object]],
    budget_mode: str,
    objective_profile: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected_rows: list[dict[str, object]] = []
    rejected_rows: list[dict[str, object]] = []
    final_max_dcr_global = float(np.max(np.asarray(final_state["max_dcr"], dtype=np.float64)))
    baseline_cost_total = float(np.sum(np.asarray(baseline_state["group_cost_proxy"], dtype=np.float64)))
    baseline_drift = float(np.asarray(baseline_state["global_drift_pct"], dtype=np.float64)[0])
    baseline_residual = float(np.asarray(baseline_state["global_residual_drift_pct"], dtype=np.float64)[0])
    for idx, row in enumerate(accepted_candidate_rows):
        gi = int(row.get("group_index", 0) or 0)
        base = group_state_lookup(baseline_state, gi)
        action_name = str(row.get("action_name", ""))
        family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        trial_dcr = float(row.get("max_dcr", base["current_max_dcr"]) or base["current_max_dcr"])
        trial_cost_total = baseline_cost_total - float(row.get("projected_cost_delta", 0.0) or 0.0)
        payload = build_explain_row(
            candidate_id=f"cand:{idx}:{base['group_id']}:{action_name}",
            stage="stage_b",
            budget_mode=str(budget_mode),
            objective_profile=str(objective_profile),
            group_id=str(base["group_id"]),
            group_index=gi,
            story_band=int(base["story_band"]),
            zone_label=str(base["zone_label"]),
            member_type=str(base["member_type"]),
            semantic_group=str(base["semantic_group"]),
            action_name=action_name,
            action_family=family,
            selected_in_final_loop=bool(row.get("selected_in_final_loop", False)),
            selected_event_index=int(row.get("selected_event_index", 0) or 0),
            current_max_dcr=base["current_max_dcr"],
            trial_max_dcr=trial_dcr,
            final_max_dcr=final_max_dcr_global,
            current_cost=baseline_cost_total,
            trial_cost=trial_cost_total,
            delta_cost=float(row.get("projected_cost_delta", 0.0) or 0.0),
            current_drift_pct=baseline_drift,
            trial_drift_pct=float(row.get("trial_drift_pct", baseline_drift) or baseline_drift),
            current_residual_drift_pct=baseline_residual,
            trial_residual_drift_pct=float(row.get("trial_residual_drift_pct", baseline_residual) or baseline_residual),
            current_congestion=float(row.get("current_congestion", base["current_congestion"]) or base["current_congestion"]),
            trial_congestion=float(row.get("trial_congestion", base["current_congestion"]) or base["current_congestion"]),
            current_detailing_complexity=float(row.get("current_detailing_complexity", base["current_detailing_complexity"]) or base["current_detailing_complexity"]),
            trial_detailing_complexity=float(row.get("trial_detailing_complexity", base["current_detailing_complexity"]) or base["current_detailing_complexity"]),
            current_constructability=float(row.get("current_constructability", base["current_constructability"]) or base["current_constructability"]),
            trial_constructability=float(row.get("trial_constructability", base["current_constructability"]) or base["current_constructability"]),
            current_robustness_margin=base["current_robustness_margin"],
            trial_robustness_margin=base["current_robustness_margin"],
            current_multi_hazard_margin=base["current_multi_hazard_margin"],
            trial_multi_hazard_margin=base["current_multi_hazard_margin"],
            current_member_governing_dcr=base["current_member_governing_dcr"],
            trial_member_governing_dcr=trial_dcr,
            current_member_governing_clause=str(base["current_member_governing_clause"]),
            trial_member_governing_clause=str(base["current_member_governing_clause"]),
            reason_selected=selected_reason(row) if bool(row.get("selected_in_final_loop", False)) else "",
            reason_rejected=rejected_reason(row) if not bool(row.get("selected_in_final_loop", False)) else "",
            detail=str(row.get("detail", "")),
        )
        if payload["selected_in_final_loop"]:
            selected_rows.append(payload)
        else:
            rejected_rows.append(payload)
    offset = len(accepted_candidate_rows)
    for idx, row in enumerate(blocked_rows):
        if str(row.get("block_reason", "")) == "accepted_candidate":
            continue
        gi = int(row.get("group_index", 0) or 0)
        base = group_state_lookup(baseline_state, gi)
        action_name = str(row.get("action_name", ""))
        family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        payload = build_explain_row(
            candidate_id=f"rej:{offset + idx}:{base['group_id']}:{action_name}",
            stage="stage_b",
            budget_mode=str(budget_mode),
            objective_profile=str(objective_profile),
            group_id=str(base["group_id"]),
            group_index=gi,
            story_band=int(base["story_band"]),
            zone_label=str(base["zone_label"]),
            member_type=str(base["member_type"]),
            semantic_group=str(base["semantic_group"]),
            action_name=action_name,
            action_family=family,
            selected_in_final_loop=False,
            selected_event_index=0,
            current_max_dcr=base["current_max_dcr"],
            trial_max_dcr=float(row.get("trial_max_dcr", base["current_max_dcr"]) or base["current_max_dcr"]),
            final_max_dcr=final_max_dcr_global,
            current_cost=baseline_cost_total,
            trial_cost=float(row.get("trial_cost", baseline_cost_total) or baseline_cost_total),
            delta_cost=float(baseline_cost_total - float(row.get("trial_cost", baseline_cost_total) or baseline_cost_total)),
            current_drift_pct=baseline_drift,
            trial_drift_pct=float(row.get("trial_drift_pct", baseline_drift) or baseline_drift),
            current_residual_drift_pct=baseline_residual,
            trial_residual_drift_pct=float(row.get("trial_residual_drift_pct", baseline_residual) or baseline_residual),
            current_congestion=base["current_congestion"],
            trial_congestion=float(row.get("trial_congestion", base["current_congestion"]) or base["current_congestion"]),
            current_detailing_complexity=base["current_detailing_complexity"],
            trial_detailing_complexity=float(row.get("trial_detailing_complexity", base["current_detailing_complexity"]) or base["current_detailing_complexity"]),
            current_constructability=base["current_constructability"],
            trial_constructability=float(row.get("trial_constructability", base["current_constructability"]) or base["current_constructability"]),
            current_robustness_margin=base["current_robustness_margin"],
            trial_robustness_margin=base["current_robustness_margin"],
            current_multi_hazard_margin=base["current_multi_hazard_margin"],
            trial_multi_hazard_margin=base["current_multi_hazard_margin"],
            current_member_governing_dcr=base["current_member_governing_dcr"],
            trial_member_governing_dcr=base["current_member_governing_dcr"],
            current_member_governing_clause=str(base["current_member_governing_clause"]),
            trial_member_governing_clause=str(base["current_member_governing_clause"]),
            reason_selected="",
            reason_rejected=rejected_reason(row),
            detail=str(row.get("detail", "")),
        )
        rejected_rows.append(payload)
    return selected_rows, rejected_rows


__all__ = [
    "build_explain_schema_v2_rows",
    "group_state_lookup",
    "rejected_reason",
    "selected_reason",
]
