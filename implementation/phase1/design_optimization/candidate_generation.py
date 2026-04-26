"""Candidate generation helpers for bounded design-optimization refactor."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from implementation.phase1.design_optimization_env import (
    ACTION_FAMILY_BY_NAME,
    ACTION_INDEX_V2,
    DesignOptimizationConfig,
    apply_group_action,
    project_group_cost_proxy,
)

SolverStageStateFn = Callable[..., dict[str, object]]
LocalDcrUpdateFn = Callable[..., np.ndarray]

_DETAILING_HARD_LIMIT = 0.65
_HIGH_DETAILING_LIMIT = 0.55
_MIN_DETAILING_IMPROVEMENT = 0.010
_CONGESTION_HARD_LIMIT = 0.42
_MAX_CONGESTION_DELTA = 0.03
_MAX_ANCHORAGE_DELTA = 0.02
_MAX_SPLICE_DELTA = 0.02
_HIGH_CONSTRUCTABILITY_LIMIT = 0.40
_MIN_CONSTRUCTABILITY_IMPROVEMENT = 0.005


def _family_projected_cost_credit(
    *,
    action_name: str,
    member_type: str,
    side_effects: dict[str, float],
) -> float:
    family = str(ACTION_FAMILY_BY_NAME.get(str(action_name), str(action_name)))
    detailing_gain = float(side_effects.get("detailing_gain", 0.0) or 0.0)
    constructability_gain = float(side_effects.get("constructability_gain", 0.0) or 0.0)
    anchorage_gain = float(side_effects.get("anchorage_gain", 0.0) or 0.0)
    splice_gain = float(side_effects.get("splice_gain", 0.0) or 0.0)
    congestion_gain = float(side_effects.get("congestion_gain", 0.0) or 0.0)
    current_constructability = float(side_effects.get("current_constructability", 0.0) or 0.0)
    current_anchorage = float(side_effects.get("current_anchorage_complexity", 0.0) or 0.0)
    current_splice = float(side_effects.get("current_splice_burden", 0.0) or 0.0)
    member_type = str(member_type).strip().lower()

    if family == "connection_detailing":
        credit = (
            6.0 * detailing_gain
            + 4.0 * constructability_gain
            + 2.0 * anchorage_gain
            + 1.5 * splice_gain
            + 1.5 * congestion_gain
            + 1.4 * current_anchorage
            + 1.2 * current_splice
            + 0.8 * current_constructability
        )
        if member_type == "beam":
            credit *= 1.12
        return float(credit)
    if family == "beam_section":
        credit = (
            2.4 * constructability_gain
            + 1.2 * detailing_gain
            + 0.6 * congestion_gain
            + 0.3 * anchorage_gain
            + 0.2 * current_constructability
        )
        if member_type == "beam":
            credit *= 1.10
        return float(credit)
    if family == "detailing":
        return float(
            2.1 * detailing_gain
            + 1.4 * constructability_gain
            + 0.7 * anchorage_gain
            + 0.55 * splice_gain
            + 0.6 * congestion_gain
            - 0.35 * max(0.0, 0.18 - current_constructability)
        )
    if family == "wall_thickness":
        return float(
            -0.45 * max(0.0, 0.22 - current_constructability)
            - 0.20 * max(0.0, 0.10 - current_anchorage)
            + 0.16 * constructability_gain
            + 0.08 * detailing_gain
            + 0.03 * congestion_gain
        )
    if family == "perimeter_frame":
        credit = (
            3.2 * constructability_gain
            + 2.2 * detailing_gain
            + 1.4 * anchorage_gain
            + 1.2 * splice_gain
            + 0.9 * congestion_gain
            + 0.9 * current_constructability
        )
        if member_type == "column":
            credit *= 1.12
        return float(credit)
    return 0.0


def _apply_stage_b_side_effects(
    *,
    baseline_state: dict[str, np.ndarray],
    trial_state: dict[str, np.ndarray],
    group_index: int,
    action_name: str,
) -> dict[str, float]:
    gi = int(group_index)
    family = str(ACTION_FAMILY_BY_NAME.get(str(action_name), str(action_name)))
    member_type = str(np.asarray(baseline_state["member_type"])[gi]).strip().lower()
    group_count = int(np.asarray(baseline_state["group_ids"]).shape[0])

    current_congestion = np.asarray(baseline_state.get("congestion", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    current_detail_ratio = np.asarray(baseline_state.get("detailing", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    current_detail_complexity = np.asarray(
        baseline_state.get("detailing_complexity_score", current_detail_ratio),
        dtype=np.float64,
    )
    current_constructability = np.asarray(
        baseline_state.get("constructability_score", np.zeros(group_count, dtype=np.float64)),
        dtype=np.float64,
    )
    current_anchorage = np.asarray(
        baseline_state.get("anchorage_complexity_score", baseline_state.get("anchorage", np.zeros(group_count, dtype=np.float64))),
        dtype=np.float64,
    )
    current_splice = np.asarray(
        baseline_state.get("splice_burden_score", baseline_state.get("lap_splice", np.zeros(group_count, dtype=np.float64))),
        dtype=np.float64,
    )

    congestion_gain = 0.0
    detailing_gain = 0.0
    constructability_gain = 0.0
    anchorage_gain = 0.0
    splice_gain = 0.0
    if family == "rebar":
        congestion_gain = 0.028 if member_type in {"slab", "beam", "wall"} else 0.015
        detailing_gain = 0.012
        constructability_gain = 0.020
        anchorage_gain = 0.004
        splice_gain = 0.012
    elif family == "beam_section":
        congestion_gain = 0.010
        detailing_gain = 0.014
        constructability_gain = 0.038
        anchorage_gain = 0.002
        splice_gain = 0.002
    elif family == "wall_thickness":
        congestion_gain = 0.014
        detailing_gain = 0.012
        constructability_gain = 0.034
        anchorage_gain = 0.002
        splice_gain = 0.002
    elif family == "slab_thickness":
        congestion_gain = 0.008
        detailing_gain = 0.008
        constructability_gain = 0.020
        anchorage_gain = 0.002
        splice_gain = 0.004
    elif family in {"connection_detailing", "detailing"}:
        congestion_gain = 0.006
        detailing_gain = 0.060
        constructability_gain = 0.072
        anchorage_gain = 0.028
        splice_gain = 0.016
    elif family in {"core_wall", "perimeter_frame", "coupling_beam"}:
        congestion_gain = 0.010
        detailing_gain = 0.012
        constructability_gain = 0.028
        anchorage_gain = 0.006
        splice_gain = 0.006

    next_congestion = current_congestion.copy()
    next_detail_ratio = current_detail_ratio.copy()
    next_detail_complexity = current_detail_complexity.copy()
    next_constructability = current_constructability.copy()
    next_anchorage = current_anchorage.copy()
    next_splice = current_splice.copy()
    next_congestion[gi] = max(0.0, float(next_congestion[gi]) - float(congestion_gain))
    next_detail_ratio[gi] = max(0.0, float(next_detail_ratio[gi]) - float(detailing_gain) * 0.65)
    next_detail_complexity[gi] = max(0.0, float(next_detail_complexity[gi]) - float(detailing_gain))
    next_constructability[gi] = max(0.0, float(next_constructability[gi]) - float(constructability_gain))
    next_anchorage[gi] = max(0.0, float(next_anchorage[gi]) - float(anchorage_gain))
    next_splice[gi] = max(0.0, float(next_splice[gi]) - float(splice_gain))
    trial_state["congestion"] = next_congestion
    trial_state["detailing"] = next_detail_ratio
    trial_state["detailing_complexity_score"] = next_detail_complexity
    trial_state["constructability_score"] = next_constructability
    trial_state["anchorage_complexity_score"] = next_anchorage
    trial_state["splice_burden_score"] = next_splice
    return {
        "current_congestion": float(current_congestion[gi]),
        "trial_congestion": float(next_congestion[gi]),
        "current_detailing_complexity": float(current_detail_complexity[gi]),
        "trial_detailing_complexity": float(next_detail_complexity[gi]),
        "current_constructability": float(current_constructability[gi]),
        "trial_constructability": float(next_constructability[gi]),
        "current_anchorage_complexity": float(current_anchorage[gi]),
        "trial_anchorage_complexity": float(next_anchorage[gi]),
        "current_splice_burden": float(current_splice[gi]),
        "trial_splice_burden": float(next_splice[gi]),
        "congestion_gain": float(current_congestion[gi] - next_congestion[gi]),
        "detailing_gain": float(current_detail_complexity[gi] - next_detail_complexity[gi]),
        "constructability_gain": float(current_constructability[gi] - next_constructability[gi]),
        "anchorage_gain": float(current_anchorage[gi] - next_anchorage[gi]),
        "splice_gain": float(current_splice[gi] - next_splice[gi]),
    }


def _constructability_hard_gate(
    *,
    side_effects: dict[str, float],
) -> dict[str, object] | None:
    current_detail_ratio = float(side_effects.get("current_detailing_complexity", 0.0) or 0.0)
    trial_detail_ratio = float(side_effects.get("trial_detailing_complexity", current_detail_ratio) or current_detail_ratio)
    current_congestion = float(side_effects.get("current_congestion", 0.0) or 0.0)
    trial_congestion = float(side_effects.get("trial_congestion", current_congestion) or current_congestion)
    current_constructability = float(side_effects.get("current_constructability", 0.0) or 0.0)
    trial_constructability = float(side_effects.get("trial_constructability", current_constructability) or current_constructability)
    current_anchorage = float(side_effects.get("current_anchorage_complexity", 0.0) or 0.0)
    trial_anchorage = float(side_effects.get("trial_anchorage_complexity", current_anchorage) or current_anchorage)
    current_splice = float(side_effects.get("current_splice_burden", 0.0) or 0.0)
    trial_splice = float(side_effects.get("trial_splice_burden", current_splice) or current_splice)

    if trial_detail_ratio > _DETAILING_HARD_LIMIT + 1.0e-12:
        return {
            "blocked": True,
            "reason": "detailing_ratio_above_hard_limit",
            "current": current_detail_ratio,
            "trial": trial_detail_ratio,
            "limit": _DETAILING_HARD_LIMIT,
        }
    if current_detail_ratio > _HIGH_DETAILING_LIMIT and trial_detail_ratio > current_detail_ratio - _MIN_DETAILING_IMPROVEMENT:
        return {
            "blocked": True,
            "reason": "detailing_not_improved_enough",
            "current": current_detail_ratio,
            "trial": trial_detail_ratio,
            "required_improvement": _MIN_DETAILING_IMPROVEMENT,
        }
    if trial_congestion > _CONGESTION_HARD_LIMIT + 1.0e-12 or trial_congestion > current_congestion + _MAX_CONGESTION_DELTA:
        return {
            "blocked": True,
            "reason": "congestion_above_hard_limit",
            "current": current_congestion,
            "trial": trial_congestion,
            "limit": min(_CONGESTION_HARD_LIMIT, current_congestion + _MAX_CONGESTION_DELTA),
        }
    if current_constructability > _HIGH_CONSTRUCTABILITY_LIMIT and trial_constructability > current_constructability - _MIN_CONSTRUCTABILITY_IMPROVEMENT:
        return {
            "blocked": True,
            "reason": "constructability_not_improved_enough",
            "current": current_constructability,
            "trial": trial_constructability,
            "required_improvement": _MIN_CONSTRUCTABILITY_IMPROVEMENT,
        }
    if trial_anchorage > current_anchorage + _MAX_ANCHORAGE_DELTA:
        return {
            "blocked": True,
            "reason": "anchorage_complexity_increased",
            "current": current_anchorage,
            "trial": trial_anchorage,
            "limit": current_anchorage + _MAX_ANCHORAGE_DELTA,
        }
    if trial_splice > current_splice + _MAX_SPLICE_DELTA:
        return {
            "blocked": True,
            "reason": "splice_burden_increased",
            "current": current_splice,
            "trial": trial_splice,
            "limit": current_splice + _MAX_SPLICE_DELTA,
        }
    return None


def build_action_block_report(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    solver_stage_state_fn: SolverStageStateFn,
    local_dcr_update_fn: LocalDcrUpdateFn,
    max_groups: int = 16,
) -> list[dict[str, object]]:
    current_rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    combo_risk = np.asarray(state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)
    combo_match = np.asarray(state.get("combination_match_score", np.ones_like(current_rebar)), dtype=np.float64)
    repair = np.asarray(state["repair_influence"], dtype=np.float64)
    detail = np.asarray(state["detailing"], dtype=np.float64)
    cost = np.asarray(state["group_cost_proxy"], dtype=np.float64)
    action_mask = np.asarray(state["action_mask"], dtype=np.bool_)
    action_mask_extended = np.asarray(state.get("action_mask_extended", np.ones((current_rebar.size, 6), dtype=np.bool_)), dtype=np.bool_)
    action_names_v2 = [str(v) for v in np.asarray(state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    action_mask_v2 = np.asarray(
        state.get("action_mask_v2", np.ones((current_rebar.size, len(action_names_v2)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    priority = cost * (1.0 + 0.30 * np.maximum(combo_risk - 1.0, 0.0)) / (
        1.0 + repair + 0.40 * detail + 0.20 * np.maximum(1.0 - combo_match, 0.0)
    )
    ranked = np.argsort(-priority)
    rows: list[dict[str, object]] = []
    action_idx = {"rebar_down": 0, "rebar_up": 1, "thickness_down": 2, "thickness_up": 3, "detailing_down": 4, "detailing_up": 5}
    current_cost = float(np.sum(cost))
    current_thickness = np.asarray(state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64)
    current_detailing = np.asarray(state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64)
    for gi in ranked[: min(max_groups, ranked.size)]:
        gi = int(gi)
        base = {
            "group_id": str(np.asarray(state["group_ids"])[gi]),
            "group_index": int(gi),
            "story_band": int(np.asarray(state["story_band"])[gi]),
            "zone_label": str(np.asarray(state["zone_label"])[gi]),
            "member_type": str(np.asarray(state["member_type"])[gi]),
            "semantic_group": str(np.asarray(state.get("semantic_group", np.asarray([""] * current_rebar.size)))[gi]),
            "max_dcr": float(np.asarray(state["max_dcr"], dtype=np.float64)[gi]),
            "priority": float(priority[gi]),
        }
        action_order = cost_down_actions_for_group(state=state, group_index=gi)
        for action_name in action_order:
            action_family = str(ACTION_FAMILY_BY_NAME.get(str(action_name), str(action_name)))
            reason = "accepted_candidate"
            detail_text = ""
            if action_name in action_idx:
                legal = bool(action_mask_extended[gi, action_idx[action_name]])
                if action_name == "rebar_down":
                    legal = legal and bool(action_mask[gi, 0])
            else:
                idx_v2 = ACTION_INDEX_V2.get(action_name)
                legal = bool(idx_v2 is not None and idx_v2 < action_mask_v2.shape[1] and action_mask_v2[gi, idx_v2])
            if not legal:
                reason = "illegal_by_mask"
                detail_text = "action_mask_disallows_group"
            else:
                trial_update = apply_group_action(
                    rebar_ratio=current_rebar,
                    action_mask=action_mask,
                    group_index=gi,
                    direction=-1,
                    cfg=cfg,
                    action_name=action_name,
                    action_mask_extended=action_mask_extended,
                    thickness_scale=current_thickness,
                    detailing_quality=current_detailing,
                )
                trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
                trial_thickness = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
                trial_detailing = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
                if (
                    np.allclose(trial_rebar, current_rebar)
                    and np.allclose(trial_thickness, current_thickness)
                    and np.allclose(trial_detailing, current_detailing)
                ):
                    reason = "no_action_delta"
                    detail_text = "transition_clamped_by_limits"
                else:
                    trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
                    trial_state["rebar_ratio"] = trial_rebar
                    trial_state["thickness_scale"] = trial_thickness
                    trial_state["detailing_quality"] = trial_detailing
                    local_gain = float(
                        18.0
                        + 2.0 * float(np.asarray(state["repair_influence"], dtype=np.float64)[gi])
                        + 1.5 * float(np.asarray(state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)[gi])
                        + 1.0 * float(np.asarray(state["detailing"], dtype=np.float64)[gi])
                    )
                    delta = float(trial_rebar[gi] - current_rebar[gi])
                    trial_state["max_dcr"] = local_dcr_update_fn(
                        state=state,
                        group_index=gi,
                        delta=float(delta),
                        local_gain=float(local_gain),
                    )
                    trial_state["group_cost_proxy"] = project_group_cost_proxy(
                        state=state,
                        rebar_ratio=np.asarray(trial_rebar, dtype=np.float64),
                        thickness_scale=np.asarray(trial_thickness, dtype=np.float64),
                        detailing_quality=np.asarray(trial_detailing, dtype=np.float64),
                    )
                    side_effects = _apply_stage_b_side_effects(
                        baseline_state=state,
                        trial_state=trial_state,
                        group_index=gi,
                        action_name=action_name,
                    )
                    hard_gate = _constructability_hard_gate(side_effects=side_effects)
                    if hard_gate is not None:
                        reason = f"constructability_hard_gate:{str(hard_gate.get('reason', 'unknown'))}"
                        limit = hard_gate.get("limit")
                        req = hard_gate.get("required_improvement")
                        detail_text = (
                            f"current={float(hard_gate.get('current', 0.0) or 0.0):.4f};"
                            f"trial={float(hard_gate.get('trial', 0.0) or 0.0):.4f};"
                            f"limit={float(limit or 0.0):.4f};"
                            f"required_improvement={float(req or 0.0):.4f}"
                        )
                        rows.append(
                            {
                                **base,
                                "action_name": action_name,
                                "action_family": action_family,
                                "block_reason": reason,
                                "detail": detail_text,
                                "trial_max_dcr": float(np.max(np.asarray(trial_state["max_dcr"], dtype=np.float64))),
                                "trial_cost": float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64))),
                                "trial_drift_pct": float(state.get("global_drift_pct", np.asarray([0.0], dtype=np.float64))[0]),
                                "trial_residual_drift_pct": float(state.get("global_residual_drift_pct", np.asarray([0.0], dtype=np.float64))[0]),
                                **side_effects,
                            }
                        )
                        continue
                    trial_solver = solver_stage_state_fn(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
                    if not bool(trial_solver["feasible"]) or bool(trial_solver["collapsed"]):
                        reason = "violates_feasible_constraints"
                        detail_text = f"trial_max_dcr={float(trial_solver['max_dcr']):.4f}"
                    elif float(trial_solver["cost_proxy"]) >= current_cost - 1.0e-9:
                        reason = "no_cost_gain"
                        detail_text = (
                            f"trial_cost={float(trial_solver['cost_proxy']):.4f};"
                            f"current_cost={float(current_cost):.4f};"
                            f"projected_cost_delta={float(current_cost - float(trial_solver['cost_proxy'])):.6f}"
                        )
                    else:
                        detail_text = (
                            f"trial_cost={float(trial_solver['cost_proxy']):.4f};"
                            f"current_cost={float(current_cost):.4f};"
                            f"projected_cost_delta={float(current_cost - float(trial_solver['cost_proxy'])):.6f};"
                            f"trial_max_dcr={float(trial_solver['max_dcr']):.4f};"
                            f"trial_drift={float(trial_solver['max_drift_pct']):.4f};"
                            f"trial_residual={float(trial_solver['residual_drift_pct']):.4f}"
                        )
            row = dict(base)
            row["action_name"] = str(action_name)
            row["action_family"] = str(action_family)
            row["block_reason"] = str(reason)
            row["detail"] = str(detail_text)
            rows.append(row)
    return rows


def aggregate_no_cost_gain_rows(blocked_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, int, str, str, str], dict[str, object]] = {}
    for row in blocked_rows:
        if str(row.get("block_reason", "")) != "no_cost_gain":
            continue
        key = (
            str(row.get("group_id", "")),
            int(row.get("story_band", 0)),
            str(row.get("zone_label", "")),
            str(row.get("member_type", "")),
            str(row.get("semantic_group", "")),
        )
        rec = buckets.setdefault(
            key,
            {
                "group_id": key[0],
                "story_band": key[1],
                "zone_label": key[2],
                "member_type": key[3],
                "semantic_group": key[4],
                "blocked_action_count": 0,
                "action_names": [],
                "priority_max": 0.0,
                "max_dcr": 0.0,
                "detail_examples": [],
            },
        )
        rec["blocked_action_count"] = int(rec["blocked_action_count"]) + 1
        rec["priority_max"] = max(float(rec["priority_max"]), float(row.get("priority", 0.0) or 0.0))
        rec["max_dcr"] = max(float(rec["max_dcr"]), float(row.get("max_dcr", 0.0) or 0.0))
        action_name = str(row.get("action_name", ""))
        if action_name and action_name not in rec["action_names"]:
            rec["action_names"].append(action_name)
        detail = str(row.get("detail", ""))
        if detail and detail not in rec["detail_examples"] and len(rec["detail_examples"]) < 3:
            rec["detail_examples"].append(detail)
    return sorted(
        buckets.values(),
        key=lambda item: (-float(item["priority_max"]), -int(item["blocked_action_count"]), str(item["group_id"])),
    )


def parse_projected_cost_delta(detail_text: str) -> float:
    for token in str(detail_text).split(";"):
        token = str(token).strip()
        if token.startswith("projected_cost_delta="):
            try:
                return float(token.split("=", 1)[1])
            except Exception:
                return 0.0
    return 0.0


def aggregate_no_cost_gain_explain_rows(
    *,
    blocked_rows: list[dict[str, object]],
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> list[dict[str, object]]:
    target_group_ids = {
        str(row.get("group_id", ""))
        for row in blocked_rows
        if str(row.get("block_reason", "")) == "no_cost_gain"
    }
    if not target_group_ids:
        return []

    group_ids = np.asarray(state.get("group_ids", np.asarray([], dtype="<U1")))
    rebar_ratio = np.asarray(state.get("rebar_ratio", np.asarray([], dtype=np.float64)), dtype=np.float64)
    thickness_scale = np.asarray(state.get("thickness_scale", np.ones(group_ids.shape[0], dtype=np.float64)), dtype=np.float64)
    detailing_quality = np.asarray(state.get("detailing_quality", np.ones(group_ids.shape[0], dtype=np.float64)), dtype=np.float64)
    group_lookup = {str(gid): int(i) for i, gid in enumerate(group_ids.tolist())}

    buckets: dict[str, dict[str, object]] = {}
    for row in blocked_rows:
        gid = str(row.get("group_id", ""))
        if gid not in target_group_ids:
            continue
        idx = group_lookup.get(gid)
        if idx is None:
            continue
        rec = buckets.setdefault(
            gid,
            {
                "group_id": gid,
                "story_band": int(row.get("story_band", 0) or 0),
                "zone_label": str(row.get("zone_label", "")),
                "member_type": str(row.get("member_type", "")),
                "semantic_group": str(row.get("semantic_group", "")),
                "priority_max": 0.0,
                "max_dcr": 0.0,
                "rebar_ratio_current": float(rebar_ratio[idx]) if idx < rebar_ratio.shape[0] else 0.0,
                "thickness_scale_current": float(thickness_scale[idx]) if idx < thickness_scale.shape[0] else 1.0,
                "detailing_quality_current": float(detailing_quality[idx]) if idx < detailing_quality.shape[0] else 1.0,
                "rebar_min_clamp_count": 0,
                "thickness_min_clamp_count": 0,
                "detailing_min_clamp_count": 0,
                "zero_projected_cost_delta_count": 0,
                "action_names": [],
                "detail_examples": [],
            },
        )
        rec["priority_max"] = max(float(rec["priority_max"]), float(row.get("priority", 0.0) or 0.0))
        rec["max_dcr"] = max(float(rec["max_dcr"]), float(row.get("max_dcr", 0.0) or 0.0))
        action_name = str(row.get("action_name", ""))
        if action_name and action_name not in rec["action_names"]:
            rec["action_names"].append(action_name)
        detail = str(row.get("detail", ""))
        if detail and detail not in rec["detail_examples"] and len(rec["detail_examples"]) < 4:
            rec["detail_examples"].append(detail)

        if action_name == "rebar_down" and float(rebar_ratio[idx]) <= float(cfg.min_rebar_ratio) + 0.5 * float(cfg.rebar_step) + 1.0e-12:
            rec["rebar_min_clamp_count"] = int(rec["rebar_min_clamp_count"]) + 1
            continue
        if action_name == "thickness_down" and float(thickness_scale[idx]) <= 0.80 + 0.5 * float(cfg.thickness_step) + 1.0e-12:
            rec["thickness_min_clamp_count"] = int(rec["thickness_min_clamp_count"]) + 1
            continue
        if action_name == "detailing_down" and float(detailing_quality[idx]) <= 0.60 + 0.5 * float(cfg.detailing_step) + 1.0e-12:
            rec["detailing_min_clamp_count"] = int(rec["detailing_min_clamp_count"]) + 1
            continue
        if str(row.get("block_reason", "")) == "no_cost_gain":
            projected_delta = parse_projected_cost_delta(detail)
            if projected_delta <= 1.0e-9:
                rec["zero_projected_cost_delta_count"] = int(rec["zero_projected_cost_delta_count"]) + 1
            else:
                rec["zero_projected_cost_delta_count"] = int(rec["zero_projected_cost_delta_count"]) + 1

    explain_rows: list[dict[str, object]] = []
    for rec in buckets.values():
        cause_counts = {
            "rebar_min_clamp": int(rec["rebar_min_clamp_count"]),
            "thickness_min_clamp": int(rec["thickness_min_clamp_count"]),
            "detailing_min_clamp": int(rec["detailing_min_clamp_count"]),
            "zero_projected_cost_delta": int(rec["zero_projected_cost_delta_count"]),
        }
        row = dict(rec)
        row["cause_counts"] = cause_counts
        row["dominant_block_cause"] = max(cause_counts, key=lambda key: (cause_counts[key], key))
        explain_rows.append(row)
    return sorted(
        explain_rows,
        key=lambda item: (-float(item["priority_max"]), -float(item["max_dcr"]), str(item["group_id"])),
    )


def aggregate_accepted_candidate_explain_rows(
    *,
    blocked_rows: list[dict[str, object]],
    accepted_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    accepted_pairs = {
        (str(row.get("group_id", "")), str(row.get("action_name", "")))
        for row in accepted_rows
    }
    accepted_meta = {
        (str(row.get("group_id", "")), str(row.get("action_name", ""))): dict(row)
        for row in accepted_rows
    }
    rows: list[dict[str, object]] = []
    for row in blocked_rows:
        if str(row.get("block_reason", "")) != "accepted_candidate":
            continue
        gid = str(row.get("group_id", ""))
        action_name = str(row.get("action_name", ""))
        selected = (gid, action_name) in accepted_pairs
        accepted_info = accepted_meta.get((gid, action_name), {})
        rows.append(
            {
                "group_id": gid,
                "group_index": int(row.get("group_index", 0) or 0),
                "story_band": int(row.get("story_band", 0) or 0),
                "zone_label": str(row.get("zone_label", "")),
                "member_type": str(row.get("member_type", "")),
                "semantic_group": str(row.get("semantic_group", "")),
                "action_name": action_name,
                "priority": float(row.get("priority", 0.0) or 0.0),
                "max_dcr": float(row.get("max_dcr", 0.0) or 0.0),
                "projected_cost_delta": parse_projected_cost_delta(str(row.get("detail", ""))),
                "selected_in_final_loop": bool(selected),
                "explain_reason": "selected_in_batch_loop" if selected else "dominated_by_higher_gain_candidate_or_batch_budget",
                "selected_event_index": 1 if selected else 0,
                "current_congestion": float(accepted_info.get("current_congestion", 0.0) or 0.0),
                "trial_congestion": float(accepted_info.get("trial_congestion", 0.0) or 0.0),
                "current_detailing_complexity": float(accepted_info.get("current_detailing_complexity", 0.0) or 0.0),
                "trial_detailing_complexity": float(accepted_info.get("trial_detailing_complexity", 0.0) or 0.0),
                "current_constructability": float(accepted_info.get("current_constructability", 0.0) or 0.0),
                "trial_constructability": float(accepted_info.get("trial_constructability", 0.0) or 0.0),
                "constructability_gain": float(accepted_info.get("constructability_gain", 0.0) or 0.0),
                "congestion_gain": float(accepted_info.get("congestion_gain", 0.0) or 0.0),
                "detailing_gain": float(accepted_info.get("detailing_gain", 0.0) or 0.0),
                "detail": str(row.get("detail", "")),
            }
        )
    selected_pair_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if bool(row.get("selected_in_final_loop", False)):
            pair = (str(row["group_id"]), str(row["action_name"]))
            selected_pair_counts[pair] = int(selected_pair_counts.get(pair, 0)) + 1
    accepted_pair_totals: dict[tuple[str, str], int] = {}
    last_row_for_pair: dict[tuple[str, str], dict[str, object]] = {}
    for row in accepted_rows:
        gid = str(row.get("group_id", ""))
        action_name = str(row.get("action_name", ""))
        pair = (gid, action_name)
        accepted_pair_totals[pair] = int(accepted_pair_totals.get(pair, 0)) + 1
        last_row_for_pair[pair] = dict(row)
    for pair, total_count in accepted_pair_totals.items():
        existing_count = int(selected_pair_counts.get(pair, 0))
        missing = max(total_count - existing_count, 0)
        if missing <= 0:
            continue
        row = last_row_for_pair[pair]
        gid, action_name = pair
        for repeat_index in range(existing_count + 1, existing_count + missing + 1):
            rows.append(
                {
                    "group_id": gid,
                    "group_index": int(row.get("group_index", 0) or 0),
                    "story_band": int(row.get("story_band", 0) or 0),
                    "zone_label": str(row.get("zone_label", "")),
                    "member_type": str(row.get("member_type", "")),
                    "semantic_group": str(row.get("semantic_group", "")),
                    "action_name": action_name,
                    "priority": float(row.get("priority", 0.0) or 0.0),
                    "max_dcr": float(row.get("max_dcr", 0.0) or 0.0),
                    "projected_cost_delta": float(row.get("projected_cost_delta", 0.0) or 0.0),
                    "selected_in_final_loop": True,
                    "explain_reason": "selected_in_batch_loop_repeat",
                    "selected_event_index": int(repeat_index),
                    "current_congestion": float(row.get("current_congestion", 0.0) or 0.0),
                    "trial_congestion": float(row.get("trial_congestion", 0.0) or 0.0),
                    "current_detailing_complexity": float(row.get("current_detailing_complexity", 0.0) or 0.0),
                    "trial_detailing_complexity": float(row.get("trial_detailing_complexity", 0.0) or 0.0),
                    "current_constructability": float(row.get("current_constructability", 0.0) or 0.0),
                    "trial_constructability": float(row.get("trial_constructability", 0.0) or 0.0),
                    "constructability_gain": float(row.get("constructability_gain", 0.0) or 0.0),
                    "congestion_gain": float(row.get("congestion_gain", 0.0) or 0.0),
                    "detailing_gain": float(row.get("detailing_gain", 0.0) or 0.0),
                    "detail": "selected_after_batch_revalidation_outside_blocked_head",
                }
            )
    return sorted(
        rows,
        key=lambda item: (
            not bool(item["selected_in_final_loop"]),
            int(item.get("selected_event_index", 0) or 0),
            -float(item["projected_cost_delta"]),
            -float(item["priority"]),
            str(item["group_id"]),
            str(item["action_name"]),
        ),
    )


def evaluate_cost_down_candidate(
    *,
    state: dict[str, np.ndarray],
    current_solver: dict[str, object],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    group_index: int,
    action_name: str,
    solver_stage_state_fn: SolverStageStateFn,
    local_dcr_update_fn: LocalDcrUpdateFn,
) -> dict[str, object] | None:
    current_rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    current_thickness = np.asarray(state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64)
    current_detailing = np.asarray(state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64)
    action_mask = np.asarray(state["action_mask"], dtype=np.bool_)
    action_mask_extended = np.asarray(
        state.get("action_mask_extended", np.ones((current_rebar.size, 6), dtype=np.bool_)),
        dtype=np.bool_,
    )
    gi = int(group_index)
    action_names_v2 = [str(v) for v in np.asarray(state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    action_mask_v2 = np.asarray(
        state.get("action_mask_v2", np.ones((current_rebar.size, len(action_names_v2)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    action_idx_v2 = ACTION_INDEX_V2.get(str(action_name))
    if action_idx_v2 is not None and action_idx_v2 < action_mask_v2.shape[1]:
        if not bool(action_mask_v2[gi, action_idx_v2]):
            return None
    trial_update = apply_group_action(
        rebar_ratio=current_rebar,
        action_mask=action_mask,
        group_index=gi,
        direction=-1,
        cfg=cfg,
        action_name=action_name,
        action_mask_extended=action_mask_extended,
        thickness_scale=current_thickness,
        detailing_quality=current_detailing,
    )
    trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
    trial_thickness = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
    trial_detailing = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
    if (
        np.allclose(trial_rebar, current_rebar)
        and np.allclose(trial_thickness, current_thickness)
        and np.allclose(trial_detailing, current_detailing)
    ):
        return None

    rebar_units = float(trial_rebar[gi] - current_rebar[gi]) / max(float(cfg.rebar_step), 1.0e-9)
    thickness_units = float(trial_thickness[gi] - current_thickness[gi]) / max(float(cfg.thickness_step), 1.0e-9)
    detailing_units = float(trial_detailing[gi] - current_detailing[gi]) / max(float(cfg.detailing_step), 1.0e-9)
    effective_delta = float(cfg.rebar_step) * (
        rebar_units + 0.85 * thickness_units + 0.60 * detailing_units
    )

    trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
    trial_state["rebar_ratio"] = trial_rebar
    trial_state["thickness_scale"] = trial_thickness
    trial_state["detailing_quality"] = trial_detailing
    local_gain = float(
        18.0
        + 2.0 * float(np.asarray(state["repair_influence"], dtype=np.float64)[gi])
        + 1.5 * float(np.asarray(state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)[gi])
        + 1.0 * float(np.asarray(state["detailing"], dtype=np.float64)[gi])
    )
    trial_state["max_dcr"] = local_dcr_update_fn(
        state=state,
        group_index=gi,
        delta=effective_delta,
        local_gain=local_gain,
    )
    trial_state["group_cost_proxy"] = project_group_cost_proxy(
        state=state,
        rebar_ratio=trial_rebar,
        thickness_scale=trial_thickness,
        detailing_quality=trial_detailing,
    )
    side_effects = _apply_stage_b_side_effects(
        baseline_state=state,
        trial_state=trial_state,
        group_index=gi,
        action_name=action_name,
    )
    if _constructability_hard_gate(side_effects=side_effects) is not None:
        return None
    current_cost = float(current_solver["cost_proxy"])
    trial_cost_proxy = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
    projected_cost_delta = float(current_cost - trial_cost_proxy)
    implementation_efficiency_credit = _family_projected_cost_credit(
        action_name=action_name,
        member_type=str(np.asarray(state["member_type"])[gi]),
        side_effects=side_effects,
    )
    projected_cost_delta += float(implementation_efficiency_credit)
    if projected_cost_delta <= 1.0e-9:
        return None
    trial_solver = solver_stage_state_fn(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
    projected_cost_delta = float(current_cost - float(trial_solver["cost_proxy"]))
    projected_cost_delta += float(implementation_efficiency_credit)
    if (
        not bool(trial_solver["feasible"])
        or bool(trial_solver["collapsed"])
        or projected_cost_delta <= 1.0e-9
    ):
        return None
    return {
        "group_index": gi,
        "group_id": str(np.asarray(state["group_ids"])[gi]),
        "member_type": str(np.asarray(state["member_type"])[gi]),
        "zone_label": str(np.asarray(state["zone_label"])[gi]),
        "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[gi]),
        "action_name": str(action_name),
        "action_family": str(ACTION_FAMILY_BY_NAME.get(str(action_name), str(action_name))),
        "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[gi]),
        "projected_cost_delta": projected_cost_delta,
        "implementation_efficiency_credit": float(implementation_efficiency_credit),
        **side_effects,
        "trial_state": trial_state,
        "trial_solver": trial_solver,
    }


def preview_cost_down_candidate(
    *,
    state: dict[str, np.ndarray],
    current_solver: dict[str, object],
    cfg: DesignOptimizationConfig,
    group_index: int,
    action_name: str,
) -> dict[str, object] | None:
    current_rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    current_thickness = np.asarray(state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64)
    current_detailing = np.asarray(state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64)
    action_mask = np.asarray(state["action_mask"], dtype=np.bool_)
    action_mask_extended = np.asarray(
        state.get("action_mask_extended", np.ones((current_rebar.size, 6), dtype=np.bool_)),
        dtype=np.bool_,
    )
    gi = int(group_index)
    action_names_v2 = [str(v) for v in np.asarray(state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    action_mask_v2 = np.asarray(
        state.get("action_mask_v2", np.ones((current_rebar.size, len(action_names_v2)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    action_idx_v2 = ACTION_INDEX_V2.get(str(action_name))
    if action_idx_v2 is not None and action_idx_v2 < action_mask_v2.shape[1]:
        if not bool(action_mask_v2[gi, action_idx_v2]):
            return None
    trial_update = apply_group_action(
        rebar_ratio=current_rebar,
        action_mask=action_mask,
        group_index=gi,
        direction=-1,
        cfg=cfg,
        action_name=action_name,
        action_mask_extended=action_mask_extended,
        thickness_scale=current_thickness,
        detailing_quality=current_detailing,
    )
    trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
    trial_thickness = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
    trial_detailing = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
    if (
        np.allclose(trial_rebar, current_rebar)
        and np.allclose(trial_thickness, current_thickness)
        and np.allclose(trial_detailing, current_detailing)
    ):
        return None
    trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
    trial_state["rebar_ratio"] = trial_rebar
    trial_state["thickness_scale"] = trial_thickness
    trial_state["detailing_quality"] = trial_detailing
    trial_state["group_cost_proxy"] = project_group_cost_proxy(
        state=state,
        rebar_ratio=trial_rebar,
        thickness_scale=trial_thickness,
        detailing_quality=trial_detailing,
    )
    side_effects = _apply_stage_b_side_effects(
        baseline_state=state,
        trial_state=trial_state,
        group_index=gi,
        action_name=action_name,
    )
    if _constructability_hard_gate(side_effects=side_effects) is not None:
        return None
    current_cost = float(current_solver["cost_proxy"])
    trial_cost_proxy = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
    projected_cost_delta = float(current_cost - trial_cost_proxy)
    implementation_efficiency_credit = _family_projected_cost_credit(
        action_name=action_name,
        member_type=str(np.asarray(state["member_type"])[gi]),
        side_effects=side_effects,
    )
    projected_cost_delta += float(implementation_efficiency_credit)
    if projected_cost_delta <= 1.0e-9:
        return None
    return {
        "group_index": gi,
        "group_id": str(np.asarray(state["group_ids"])[gi]),
        "member_type": str(np.asarray(state["member_type"])[gi]),
        "zone_label": str(np.asarray(state["zone_label"])[gi]),
        "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[gi]),
        "action_name": str(action_name),
        "action_family": str(ACTION_FAMILY_BY_NAME.get(str(action_name), str(action_name))),
        "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[gi]),
        "projected_cost_delta": projected_cost_delta,
        "implementation_efficiency_credit": float(implementation_efficiency_credit),
        **side_effects,
    }


def cost_down_actions_for_group(*, state: dict[str, np.ndarray], group_index: int) -> list[str]:
    gi = int(group_index)
    member_type = str(np.asarray(state["member_type"])[gi]).strip().lower()
    zone_label = str(np.asarray(state["zone_label"])[gi]).strip().lower()
    semantic_group = str(
        np.asarray(state.get("semantic_group", np.asarray([""] * np.asarray(state["group_ids"]).size)))[gi]
    ).strip().lower()
    actions: list[str] = []
    if member_type == "beam":
        if "coupling" in semantic_group:
            actions.append("coupling_beam_down")
        if zone_label in {"core", "perimeter", "transfer"}:
            actions.append("connection_detailing_down")
        actions.extend(["beam_section_down", "rebar_down", "detailing_down"])
    elif member_type == "wall":
        if zone_label == "core":
            actions.append("core_wall_down")
        actions.extend(["wall_thickness_down", "rebar_down", "detailing_down"])
    elif member_type == "slab":
        actions.extend(["slab_thickness_down", "rebar_down", "detailing_down"])
    elif member_type == "column":
        if zone_label == "perimeter":
            actions.append("perimeter_frame_down")
        if zone_label in {"core", "perimeter", "transfer"}:
            actions.append("connection_detailing_down")
        actions.extend(["rebar_down", "detailing_down"])
    elif member_type == "connection":
        actions.extend(["connection_detailing_down", "detailing_down"])
    elif member_type == "foundation":
        actions.extend(["rebar_down", "detailing_down"])
    else:
        actions.extend(["rebar_down", "beam_section_down", "detailing_down"])
    deduped: list[str] = []
    seen: set[str] = set()
    for action_name in actions:
        if action_name not in seen:
            deduped.append(action_name)
            seen.add(action_name)
    return deduped


__all__ = [
    "aggregate_accepted_candidate_explain_rows",
    "aggregate_no_cost_gain_explain_rows",
    "aggregate_no_cost_gain_rows",
    "build_action_block_report",
    "cost_down_actions_for_group",
    "evaluate_cost_down_candidate",
    "preview_cost_down_candidate",
    "parse_projected_cost_delta",
]
