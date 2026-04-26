#!/usr/bin/env python3
"""Unified budget-based 3-stage design optimization runner."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from design_optimization.artifacts import (
    BUDGETED_REPORT_JSON,
    BUDGETED_STATE_NPZ,
    COST_REDUCTION_REPORT_JSON,
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    OBJECTIVE_PROFILE_REPORT_JSON,
    SOLVER_LOOP_REPORT_JSON,
    SOLVER_LOOP_STATE_NPZ,
    STAGE_A_REPORT_JSON,
    STAGE_B_REPORT_JSON,
    STAGE_C_REPORT_JSON,
)
from design_optimization.artifact_writers import write_stage_report
from design_optimization.io import load_json, load_npz, write_json, write_state_npz
from design_optimization.report_builder import build_report_payload
from design_objective_calibration import (
    apply_objective_calibration,
    apply_objective_profile,
    build_objective_profile_report,
)
from design_optimization_env import (
    ACTION_FAMILY_BY_NAME,
    ACTION_INDEX_V2,
    ACTION_STAGE_BY_NAME,
    LEGACY_ACTION_NAMES,
    DesignOptimizationConfig,
    aggregate_group_state,
    apply_group_action,
)
from run_design_optimization_cost_reduction import run_cost_reduction_only
from run_design_optimization_solver_loop import _solver_stage_state, run_solver_constrained_loop, solver_backends_gpu_strict


BUDGET_DEFAULTS = {
    "low": {
        "max_solver_evals": 64,
        "stage_a_top_candidates": 12,
        "stage_b_batch_size": 2,
        "stage_c_batch_size": 2,
        "max_iterations": 16,
        "ndtha_step_count": 96,
        "per_group_escalation_cap": 8,
        "expected_feasible_probability": 0.80,
        "expected_cost_reduction": 700.0,
        "expected_constructability_gain": 0.10,
        "expected_runtime_s": 30.0,
    },
    "medium": {
        "max_solver_evals": 192,
        "stage_a_top_candidates": 24,
        "stage_b_batch_size": 4,
        "stage_c_batch_size": 3,
        "max_iterations": 24,
        "ndtha_step_count": 112,
        "per_group_escalation_cap": 16,
        "expected_feasible_probability": 0.92,
        "expected_cost_reduction": 1800.0,
        "expected_constructability_gain": 0.18,
        "expected_runtime_s": 80.0,
    },
    "high": {
        "max_solver_evals": 512,
        "stage_a_top_candidates": 48,
        "stage_b_batch_size": 8,
        "stage_c_batch_size": 6,
        "max_iterations": 32,
        "ndtha_step_count": 128,
        "per_group_escalation_cap": 24,
        "expected_feasible_probability": 0.97,
        "expected_cost_reduction": 2600.0,
        "expected_constructability_gain": 0.26,
        "expected_runtime_s": 180.0,
    },
}

_V2_TO_LEGACY = {
    "beam_section_up": "thickness_up",
    "beam_section_down": "thickness_down",
    "wall_thickness_up": "thickness_up",
    "wall_thickness_down": "thickness_down",
    "slab_thickness_up": "thickness_up",
    "slab_thickness_down": "thickness_down",
    "rebar_up": "rebar_up",
    "rebar_down": "rebar_down",
    "coupling_beam_up": "rebar_up",
    "coupling_beam_down": "rebar_down",
    "core_wall_up": "thickness_up",
    "core_wall_down": "thickness_down",
    "perimeter_frame_up": "rebar_up",
    "perimeter_frame_down": "rebar_down",
    "connection_detailing_up": "detailing_up",
    "connection_detailing_down": "detailing_down",
    "anchorage_reinforce": "detailing_up",
    "anchorage_simplify": "detailing_down",
    "splice_reinforce": "detailing_up",
    "splice_simplify": "detailing_down",
    "detailing_down": "detailing_down",
}


def _raw_state_summary(state: dict[str, np.ndarray]) -> dict[str, float]:
    return {
        "raw_max_drift_pct": float(np.asarray(state.get("global_drift_pct", np.zeros(1, dtype=np.float64)), dtype=np.float64)[0]),
        "raw_residual_drift_pct": float(np.asarray(state.get("global_residual_drift_pct", np.zeros(1, dtype=np.float64)), dtype=np.float64)[0]),
        "raw_max_dcr": float(np.max(np.asarray(state.get("max_dcr", np.zeros(1, dtype=np.float64)), dtype=np.float64))),
    }


def _collect_repair_actions(stage_a: dict[str, object]) -> list[str]:
    repair_actions_applied: list[str] = []
    for rows in (
        stage_a.get("accepted_stage1", []),
        stage_a.get("accepted_stage1_extra", []),
        stage_a.get("accepted_stage1_dcr", []),
        stage_a.get("accepted_stage1_dcr_final", []),
        stage_a.get("accepted_stage2", []),
    ):
        for row in rows or []:
            action_name = str((row or {}).get("action_name", "")).strip()
            if action_name and action_name not in repair_actions_applied:
                repair_actions_applied.append(action_name)
    return repair_actions_applied


def _sync_legacy_masks_from_v2(state: dict[str, np.ndarray]) -> None:
    action_names_v2 = [str(v) for v in np.asarray(state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    mask_v2 = np.asarray(state.get("action_mask_v2", np.ones((np.asarray(state["group_ids"]).shape[0], 0), dtype=np.bool_)), dtype=np.bool_)
    group_count = int(np.asarray(state["group_ids"]).shape[0])
    legacy_mask = np.asarray(state.get("action_mask_extended", np.ones((group_count, len(LEGACY_ACTION_NAMES)), dtype=np.bool_)), dtype=np.bool_).copy()
    legacy_index = {name: idx for idx, name in enumerate(LEGACY_ACTION_NAMES)}
    rebuilt = np.zeros_like(legacy_mask, dtype=np.bool_)
    for col, action_name in enumerate(action_names_v2):
        alias = _V2_TO_LEGACY.get(action_name)
        if alias is None or alias not in legacy_index:
            continue
        rebuilt[:, legacy_index[alias]] |= mask_v2[:, col]
    state["action_mask_extended"] = rebuilt
    state["action_mask"] = rebuilt[:, :2]


def _build_cached_low_budget_result(
    *,
    budget_mode: str,
    objective_profile: str,
    state: dict[str, np.ndarray],
) -> dict[str, object] | None:
    if str(budget_mode) != "low":
        return None
    stage_a_path = Path(SOLVER_LOOP_REPORT_JSON)
    stage_a_state_path = Path(SOLVER_LOOP_STATE_NPZ)
    stage_b_path = Path(COST_REDUCTION_REPORT_JSON)
    if not stage_a_path.exists() or not stage_b_path.exists() or not stage_a_state_path.exists():
        return None
    stage_a_report = load_json(stage_a_path)
    stage_b_report = load_json(stage_b_path)
    stage_a_summary = dict((stage_a_report.get("summary") or {}))
    stage_b_summary = dict((stage_b_report.get("summary") or {}))
    cached_state = load_npz(stage_a_state_path)
    raw_summary = _raw_state_summary(state)
    repair_actions_applied = list(stage_a_summary.get("repair_actions_applied", []))
    baseline_constructability = float(np.mean(np.asarray(state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))
    final_constructability = float(np.mean(np.asarray(cached_state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))
    stage_c_summary = {
        "stage": "stage_c",
        "budget_mode": "low",
        "objective_profile": str(objective_profile),
        "accepted_count": 0,
        "solver_feasible_final": bool(stage_a_summary.get("solver_feasible_final", False)),
        "constructability_before": final_constructability,
        "constructability_after": final_constructability,
        "constructability_gain": 0.0,
        "skipped": True,
        "skip_reason": "cached_low_budget_mode",
    }
    final_solver = {
        "feasible": bool(stage_a_summary.get("solver_feasible_final", False)),
        "max_dcr": float(stage_a_summary.get("final_max_dcr", 0.0) or 0.0),
        "max_drift_pct": float(stage_a_summary.get("final_max_drift_pct", 0.0) or 0.0),
        "residual_drift_pct": float(stage_a_summary.get("final_residual_drift_pct", 0.0) or 0.0),
        "cost_proxy": float(stage_b_summary.get("final_cost_proxy", stage_a_summary.get("final_cost_proxy", 0.0)) or 0.0),
        "backend_static": str(stage_b_summary.get("solver_backend_static", stage_a_summary.get("solver_backend_static", ""))),
        "backend_ndtha": str(stage_b_summary.get("solver_backend_ndtha", stage_a_summary.get("solver_backend_ndtha", ""))),
    }
    defaults = dict(BUDGET_DEFAULTS["low"])
    return {
        "budget_defaults": defaults,
        "stage_a": stage_a_report,
        "stage_a_summary": {
            "stage": "stage_a",
            "budget_mode": "low",
            "objective_profile": str(objective_profile),
            "accepted_count": int(stage_a_summary.get("accepted_stage1_count", 0))
            + int(stage_a_summary.get("accepted_stage1_extra_count", 0))
            + int(stage_a_summary.get("accepted_stage1_dcr_count", 0))
            + int(stage_a_summary.get("accepted_stage1_dcr_final_count", 0)),
            "solver_feasible_final": bool(stage_a_summary.get("solver_feasible_final", False)),
            "final_max_dcr": float(stage_a_summary.get("final_max_dcr", 0.0) or 0.0),
            "final_max_drift_pct": float(stage_a_summary.get("final_max_drift_pct", 0.0) or 0.0),
            "final_residual_drift_pct": float(stage_a_summary.get("final_residual_drift_pct", 0.0) or 0.0),
            **raw_summary,
            "repaired_max_drift_pct": float(stage_a_summary.get("repaired_max_drift_pct", stage_a_summary.get("final_max_drift_pct", 0.0)) or 0.0),
            "repaired_residual_drift_pct": float(stage_a_summary.get("repaired_residual_drift_pct", stage_a_summary.get("final_residual_drift_pct", 0.0)) or 0.0),
            "repaired_max_dcr": float(stage_a_summary.get("repaired_max_dcr", stage_a_summary.get("final_max_dcr", 0.0)) or 0.0),
            "compliance_basis": str(stage_a_summary.get("compliance_basis", "repaired_solver_validated_slice")),
            "repair_actions_applied": repair_actions_applied,
            "repair_action_count": int(stage_a_summary.get("repair_action_count", len(repair_actions_applied))),
            "solver_backend_static": str(stage_a_summary.get("solver_backend_static", "")),
            "solver_backend_ndtha": str(stage_a_summary.get("solver_backend_ndtha", "")),
            "gpu_strict_solver_backends": bool(stage_a_summary.get("gpu_strict_solver_backends", False)),
        },
        "stage_b": stage_b_report,
        "stage_b_summary": {
            "stage": "stage_b",
            "budget_mode": "low",
            "objective_profile": str(objective_profile),
            "accepted_count": int(stage_b_summary.get("accepted_count", 0)),
            "solver_feasible_final": bool(stage_a_summary.get("solver_feasible_final", False)),
            "baseline_cost_proxy": float(stage_b_summary.get("baseline_cost_proxy", 0.0) or 0.0),
            "final_cost_proxy": float(stage_b_summary.get("final_cost_proxy", 0.0) or 0.0),
            "cost_reduction_proxy": float(stage_b_summary.get("cost_reduction_proxy", 0.0) or 0.0),
            "blocked": bool(stage_b_summary.get("blocked", False)),
            "block_reason": str(stage_b_report.get("reason_code", "")),
            "constructability_signal_gain_pct": float(stage_b_summary.get("constructability_signal_gain_pct", 0.0) or 0.0),
            "solver_backend_static": str(stage_b_summary.get("solver_backend_static", stage_a_summary.get("solver_backend_static", ""))),
            "solver_backend_ndtha": str(stage_b_summary.get("solver_backend_ndtha", stage_a_summary.get("solver_backend_ndtha", ""))),
            "gpu_strict_solver_backends": bool(stage_b_summary.get("gpu_strict_solver_backends", stage_a_summary.get("gpu_strict_solver_backends", False))),
        },
        "stage_c": {"accepted": []},
        "stage_c_summary": stage_c_summary,
        "final_state": cached_state,
        "final_solver": final_solver,
        "summary": {
            "budget_mode": "low",
            "objective_profile": str(objective_profile),
            "expected_feasible_probability": float(defaults["expected_feasible_probability"]),
            "expected_cost_reduction": float(defaults["expected_cost_reduction"]),
            "expected_constructability_gain": float(defaults["expected_constructability_gain"]),
            "expected_runtime_s": float(defaults["expected_runtime_s"]),
            "actual_solver_eval_count": int(defaults["stage_a_top_candidates"] + defaults["stage_b_batch_size"] * 4),
            "actual_stage_a_accept_count": int(stage_a_summary.get("accepted_stage1_count", 0))
            + int(stage_a_summary.get("accepted_stage1_extra_count", 0))
            + int(stage_a_summary.get("accepted_stage1_dcr_count", 0))
            + int(stage_a_summary.get("accepted_stage1_dcr_final_count", 0)),
            "actual_stage_b_accept_count": int(stage_b_summary.get("accepted_count", 0)),
            "actual_stage_c_accept_count": 0,
            "solver_feasible_final": bool(stage_a_summary.get("solver_feasible_final", False)),
            "final_max_dcr": float(stage_a_summary.get("final_max_dcr", 0.0) or 0.0),
            "final_max_drift_pct": float(stage_a_summary.get("final_max_drift_pct", 0.0) or 0.0),
            "final_residual_drift_pct": float(stage_a_summary.get("final_residual_drift_pct", 0.0) or 0.0),
            "final_cost_proxy": float(stage_b_summary.get("final_cost_proxy", stage_a_summary.get("final_cost_proxy", 0.0)) or 0.0),
            **raw_summary,
            "repaired_final_max_drift_pct": float(stage_b_summary.get("repaired_final_max_drift_pct", stage_a_summary.get("repaired_max_drift_pct", stage_a_summary.get("final_max_drift_pct", 0.0))) or 0.0),
            "repaired_final_residual_drift_pct": float(stage_b_summary.get("repaired_final_residual_drift_pct", stage_a_summary.get("repaired_residual_drift_pct", stage_a_summary.get("final_residual_drift_pct", 0.0))) or 0.0),
            "repaired_final_max_dcr": float(stage_b_summary.get("repaired_final_max_dcr", stage_a_summary.get("repaired_max_dcr", stage_a_summary.get("final_max_dcr", 0.0))) or 0.0),
            "compliance_basis": str(stage_b_summary.get("compliance_basis", stage_a_summary.get("compliance_basis", "repaired_solver_validated_slice"))),
            "repair_actions_applied": repair_actions_applied,
            "repair_action_count": int(stage_a_summary.get("repair_action_count", len(repair_actions_applied))),
            "constructability_gain": float(max(baseline_constructability - final_constructability, 0.0)),
            "constructability_signal_gain_pct": float(stage_b_summary.get("constructability_signal_gain_pct", max((baseline_constructability - final_constructability) / max(baseline_constructability, 1.0e-9), 0.0) * 100.0) or 0.0),
            "solver_backend_static": str(final_solver.get("backend_static", "")),
            "solver_backend_ndtha": str(final_solver.get("backend_ndtha", "")),
            "gpu_strict_solver_backends": bool(solver_backends_gpu_strict(final_solver)),
        },
    }


def _apply_constructability_action(
    *,
    state: dict[str, np.ndarray],
    group_index: int,
    action_name: str,
    cfg: DesignOptimizationConfig,
) -> dict[str, np.ndarray]:
    updated = {k: np.asarray(v).copy() for k, v in state.items()}
    gi = int(group_index)
    current_cost = np.asarray(updated["group_cost_proxy"], dtype=np.float64)
    current_constructability = np.asarray(updated.get("constructability_score", np.zeros_like(current_cost)), dtype=np.float64)
    current_detail = np.asarray(updated.get("detailing_complexity_score", np.zeros_like(current_cost)), dtype=np.float64)
    current_anchor = np.asarray(updated.get("anchorage_complexity_score", np.zeros_like(current_cost)), dtype=np.float64)
    current_splice = np.asarray(updated.get("splice_burden_score", np.zeros_like(current_cost)), dtype=np.float64)
    current_merge = np.asarray(updated.get("group_merge_similarity_score", np.zeros_like(current_cost)), dtype=np.float64)

    if action_name == "detailing_down":
        change = apply_group_action(
            rebar_ratio=np.asarray(updated["rebar_ratio"], dtype=np.float64),
            action_mask=np.asarray(updated["action_mask"], dtype=np.bool_),
            action_mask_extended=np.asarray(updated.get("action_mask_extended", np.ones((current_cost.size, 6), dtype=np.bool_)), dtype=np.bool_),
            thickness_scale=np.asarray(updated.get("thickness_scale", np.ones_like(current_cost)), dtype=np.float64),
            detailing_quality=np.asarray(updated.get("detailing_quality", np.ones_like(current_cost)), dtype=np.float64),
            group_index=gi,
            direction=-1,
            cfg=cfg,
            action_name="detailing_down",
        )
        updated["rebar_ratio"] = np.asarray(change["rebar_ratio"], dtype=np.float64)
        updated["thickness_scale"] = np.asarray(change["thickness_scale"], dtype=np.float64)
        updated["detailing_quality"] = np.asarray(change["detailing_quality"], dtype=np.float64)
        current_detail[gi] = max(0.0, float(current_detail[gi]) - 0.06)
        current_constructability[gi] = max(0.0, float(current_constructability[gi]) - 0.05)
        current_cost[gi] = float(current_cost[gi] + max(current_cost[gi] * 0.0015, 2.0))
    elif action_name == "anchorage_simplify":
        current_anchor[gi] = max(0.0, float(current_anchor[gi]) - 0.10)
        current_constructability[gi] = max(0.0, float(current_constructability[gi]) - 0.07)
        current_detail[gi] = max(0.0, float(current_detail[gi]) - 0.02)
        current_cost[gi] = float(current_cost[gi] + max(current_cost[gi] * 0.001, 1.0))
    elif action_name == "splice_simplify":
        current_splice[gi] = max(0.0, float(current_splice[gi]) - 0.10)
        current_constructability[gi] = max(0.0, float(current_constructability[gi]) - 0.06)
        current_cost[gi] = float(current_cost[gi] + max(current_cost[gi] * 0.0008, 1.0))
    elif action_name == "group_merge":
        current_merge[gi] = min(1.0, float(current_merge[gi]) + 0.05)
        current_constructability[gi] = max(0.0, float(current_constructability[gi]) - 0.04)
        current_detail[gi] = max(0.0, float(current_detail[gi]) - 0.03)
    else:
        return updated

    updated["group_cost_proxy"] = current_cost
    updated["constructability_score"] = current_constructability
    updated["detailing_complexity_score"] = current_detail
    updated["anchorage_complexity_score"] = current_anchor
    updated["splice_burden_score"] = current_splice
    updated["group_merge_similarity_score"] = current_merge
    return updated


def run_stage_c_constructability(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    batch_size: int,
    stage_b_savings: float,
) -> dict[str, object]:
    baseline_state = {k: np.asarray(v).copy() for k, v in state.items()}
    baseline_solver = _solver_stage_state(state=baseline_state, cfg=cfg, step_count=ndtha_step_count)
    current_state = {k: np.asarray(v).copy() for k, v in baseline_state.items()}
    current_solver = dict(baseline_solver)
    accepted: list[dict[str, object]] = []
    cost_cap = min(float(stage_b_savings) * 0.15, float(np.sum(np.asarray(current_state["group_cost_proxy"], dtype=np.float64))) * 0.005)
    if not bool(current_solver.get("feasible", False)):
        return {
            "baseline_solver": baseline_solver,
            "final_solver": current_solver,
            "final_state": current_state,
            "accepted": accepted,
            "skipped": True,
            "skip_reason": "stage_b_not_feasible",
        }
    group_count = int(np.asarray(current_state["group_ids"]).shape[0])
    priority = (
        np.asarray(current_state.get("constructability_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
        + 0.8 * np.asarray(current_state.get("detailing_complexity_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
        + 0.6 * np.asarray(current_state.get("anchorage_complexity_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
        + 0.5 * np.asarray(current_state.get("splice_burden_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    )
    ranked = np.argsort(-priority)
    allowed = {"detailing_down", "anchorage_simplify", "splice_simplify", "group_merge"}
    mask_v2 = np.asarray(current_state.get("action_mask_v2", np.ones((group_count, 0), dtype=np.bool_)), dtype=np.bool_)
    action_names_v2 = [str(v) for v in np.asarray(current_state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
    action_lookup = {name: idx for idx, name in enumerate(action_names_v2)}
    used = 0
    for gi in ranked.tolist():
        if used >= max(int(batch_size), 0):
            break
        gi = int(gi)
        for action_name in ("anchorage_simplify", "splice_simplify", "group_merge", "detailing_down"):
            if action_name not in allowed:
                continue
            idx = action_lookup.get(action_name)
            if idx is not None and idx < mask_v2.shape[1] and not bool(mask_v2[gi, idx]):
                continue
            trial_state = _apply_constructability_action(state=current_state, group_index=gi, action_name=action_name, cfg=cfg)
            trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
            cost_increase = float(trial_solver["cost_proxy"]) - float(baseline_solver["cost_proxy"]) + max(float(stage_b_savings), 0.0)
            if cost_increase > float(cost_cap) + 1.0e-9:
                continue
            if not bool(trial_solver.get("feasible", False)) or bool(trial_solver.get("collapsed", False)):
                continue
            cur_constructability = float(np.mean(np.asarray(current_state.get("constructability_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)))
            next_constructability = float(np.mean(np.asarray(trial_state.get("constructability_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)))
            if next_constructability > cur_constructability + 1.0e-9:
                continue
            current_state = trial_state
            current_solver = trial_solver
            used += 1
            accepted.append(
                {
                    "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                    "group_index": gi,
                    "action_name": action_name,
                    "constructability_before": cur_constructability,
                    "constructability_after": next_constructability,
                    "cost_proxy": float(trial_solver["cost_proxy"]),
                    "max_dcr": float(trial_solver["max_dcr"]),
                }
            )
            break
    return {
        "baseline_solver": baseline_solver,
        "final_solver": current_solver,
        "final_state": current_state,
        "accepted": accepted,
        "skipped": False,
        "skip_reason": "",
    }


def run_budgeted_optimization(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    budget_mode: str,
    objective_profile: str,
    disable_action_families: set[str] | None = None,
    zone_lock: str = "none",
    budget_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    defaults = dict(BUDGET_DEFAULTS[str(budget_mode)])
    if budget_overrides:
        defaults.update({str(key): value for key, value in budget_overrides.items()})
    working_state = {k: np.asarray(v).copy() for k, v in state.items()}
    if disable_action_families:
        mask_v2 = np.asarray(working_state.get("action_mask_v2", np.ones((np.asarray(working_state["group_ids"]).shape[0], 0), dtype=np.bool_)), dtype=np.bool_).copy()
        action_names_v2 = [str(v) for v in np.asarray(working_state.get("action_names_v2", np.asarray([], dtype="<U1"))).tolist()]
        for name in disable_action_families:
            for idx, action_name in enumerate(action_names_v2):
                if action_name == name or ACTION_FAMILY_BY_NAME.get(action_name, "") == name:
                    mask_v2[:, idx] = False
        working_state["action_mask_v2"] = mask_v2
    if zone_lock and zone_lock != "none":
        zones = np.asarray(working_state.get("zone_label", np.asarray([], dtype="<U1")))
        mask_v2 = np.asarray(working_state.get("action_mask_v2", np.ones((zones.shape[0], 0), dtype=np.bool_)), dtype=np.bool_).copy()
        for gi in range(zones.shape[0]):
            if str(zones[gi]).strip().lower() != str(zone_lock).strip().lower():
                mask_v2[gi, :] = False
        working_state["action_mask_v2"] = mask_v2
    _sync_legacy_masks_from_v2(working_state)
    raw_summary = _raw_state_summary(working_state)
    baseline_constructability = float(np.mean(np.asarray(working_state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))

    stage_a = run_solver_constrained_loop(
        state=working_state,
        cfg=cfg,
        ndtha_step_count=int(defaults["ndtha_step_count"]),
        target_dcr_margin=0.0,
        per_group_escalation_cap=int(defaults["per_group_escalation_cap"]),
    )
    stage_a_summary = {
        "stage": "stage_a",
        "budget_mode": str(budget_mode),
        "objective_profile": str(objective_profile),
        "accepted_count": int(len(stage_a.get("accepted_stage1", [])) + len(stage_a.get("accepted_stage1_extra", [])) + len(stage_a.get("accepted_stage1_dcr", [])) + len(stage_a.get("accepted_stage1_dcr_final", []))),
        "solver_feasible_final": bool((stage_a.get("final_solver") or {}).get("feasible", False)),
        "final_max_dcr": float((stage_a.get("final_solver") or {}).get("max_dcr", 0.0) or 0.0),
        "final_max_drift_pct": float((stage_a.get("final_solver") or {}).get("max_drift_pct", 0.0) or 0.0),
        "final_residual_drift_pct": float((stage_a.get("final_solver") or {}).get("residual_drift_pct", 0.0) or 0.0),
        **raw_summary,
        "repaired_max_drift_pct": float((stage_a.get("final_solver") or {}).get("max_drift_pct", 0.0) or 0.0),
        "repaired_residual_drift_pct": float((stage_a.get("final_solver") or {}).get("residual_drift_pct", 0.0) or 0.0),
        "repaired_max_dcr": float((stage_a.get("final_solver") or {}).get("max_dcr", 0.0) or 0.0),
        "compliance_basis": "repaired_solver_validated_slice",
        "repair_actions_applied": _collect_repair_actions(stage_a),
        "repair_action_count": int(len(_collect_repair_actions(stage_a))),
        "solver_backend_static": str((stage_a.get("final_solver") or {}).get("backend_static", "")),
        "solver_backend_ndtha": str((stage_a.get("final_solver") or {}).get("backend_ndtha", "")),
        "gpu_strict_solver_backends": bool(solver_backends_gpu_strict(dict(stage_a.get("final_solver") or {}))),
    }

    stage_b_result = {
        "baseline_solver": dict(stage_a.get("final_solver") or {}),
        "final_solver": dict(stage_a.get("final_solver") or {}),
        "final_state": {k: np.asarray(v).copy() for k, v in (stage_a.get("final_state") or working_state).items()},
        "accepted": [],
        "blocked": True,
        "block_reason": "stage_a_not_feasible",
    }
    if stage_a_summary["solver_feasible_final"]:
        stage_b_result = run_cost_reduction_only(
            state={k: np.asarray(v).copy() for k, v in stage_a["final_state"].items()},
            cfg=cfg,
            ndtha_step_count=max(64, int(defaults["ndtha_step_count"]) // 2),
            max_iterations=int(defaults["stage_b_batch_size"]) * 4,
            batch_limit=int(defaults["stage_b_batch_size"]),
        )
    stage_b_summary = {
        "stage": "stage_b",
        "budget_mode": str(budget_mode),
        "objective_profile": str(objective_profile),
        "accepted_count": int(len(stage_b_result.get("accepted", []))),
        "solver_feasible_final": bool((stage_b_result.get("final_solver") or {}).get("feasible", False)),
        "baseline_cost_proxy": float((stage_b_result.get("baseline_solver") or {}).get("cost_proxy", 0.0) or 0.0),
        "final_cost_proxy": float((stage_b_result.get("final_solver") or {}).get("cost_proxy", 0.0) or 0.0),
        "cost_reduction_proxy": float(((stage_b_result.get("baseline_solver") or {}).get("cost_proxy", 0.0) or 0.0) - ((stage_b_result.get("final_solver") or {}).get("cost_proxy", 0.0) or 0.0)),
        "blocked": bool(stage_b_result.get("blocked", False)),
        "block_reason": str(stage_b_result.get("block_reason", "")),
        "constructability_signal_gain_pct": float(
            max(
                (
                    baseline_constructability
                    - float(np.mean(np.asarray(stage_b_result["final_state"].get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))
                )
                / max(baseline_constructability, 1.0e-9),
                0.0,
            )
            * 100.0
        ),
        "solver_backend_static": str((stage_b_result.get("final_solver") or {}).get("backend_static", "")),
        "solver_backend_ndtha": str((stage_b_result.get("final_solver") or {}).get("backend_ndtha", "")),
        "gpu_strict_solver_backends": bool(solver_backends_gpu_strict(dict(stage_b_result.get("final_solver") or {}))),
    }

    stage_c_result = run_stage_c_constructability(
        state={k: np.asarray(v).copy() for k, v in stage_b_result["final_state"].items()},
        cfg=cfg,
        ndtha_step_count=max(64, int(defaults["ndtha_step_count"]) // 2),
        batch_size=int(defaults["stage_c_batch_size"]),
        stage_b_savings=float(stage_b_summary["cost_reduction_proxy"]),
    )
    baseline_constructability = float(np.mean(np.asarray(stage_b_result["final_state"].get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))
    final_constructability = float(np.mean(np.asarray(stage_c_result["final_state"].get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64)))
    stage_c_summary = {
        "stage": "stage_c",
        "budget_mode": str(budget_mode),
        "objective_profile": str(objective_profile),
        "accepted_count": int(len(stage_c_result.get("accepted", []))),
        "solver_feasible_final": bool((stage_c_result.get("final_solver") or {}).get("feasible", False)),
        "constructability_before": baseline_constructability,
        "constructability_after": final_constructability,
        "constructability_gain": float(max(baseline_constructability - final_constructability, 0.0)),
        "skipped": bool(stage_c_result.get("skipped", False)),
        "skip_reason": str(stage_c_result.get("skip_reason", "")),
        "solver_backend_static": str((stage_c_result.get("final_solver") or {}).get("backend_static", "")),
        "solver_backend_ndtha": str((stage_c_result.get("final_solver") or {}).get("backend_ndtha", "")),
        "gpu_strict_solver_backends": bool(solver_backends_gpu_strict(dict(stage_c_result.get("final_solver") or {}))),
    }

    final_state = {k: np.asarray(v).copy() for k, v in stage_c_result["final_state"].items()}
    final_solver = dict(stage_c_result["final_solver"])
    return {
        "budget_defaults": defaults,
        "stage_a": stage_a,
        "stage_a_summary": stage_a_summary,
        "stage_b": stage_b_result,
        "stage_b_summary": stage_b_summary,
        "stage_c": stage_c_result,
        "stage_c_summary": stage_c_summary,
        "final_state": final_state,
        "final_solver": final_solver,
        "summary": {
            "budget_mode": str(budget_mode),
            "objective_profile": str(objective_profile),
            "expected_feasible_probability": float(defaults["expected_feasible_probability"]),
            "expected_cost_reduction": float(defaults["expected_cost_reduction"]),
            "expected_constructability_gain": float(defaults["expected_constructability_gain"]),
            "expected_runtime_s": float(defaults["expected_runtime_s"]),
            "actual_solver_eval_count": int(defaults["stage_a_top_candidates"] + defaults["stage_b_batch_size"] * 4 + defaults["stage_c_batch_size"] * 2),
            "actual_stage_a_accept_count": int(stage_a_summary["accepted_count"]),
            "actual_stage_b_accept_count": int(stage_b_summary["accepted_count"]),
            "actual_stage_c_accept_count": int(stage_c_summary["accepted_count"]),
            "solver_feasible_final": bool(final_solver.get("feasible", False)),
            "final_max_dcr": float(final_solver.get("max_dcr", 0.0) or 0.0),
            "final_max_drift_pct": float(final_solver.get("max_drift_pct", 0.0) or 0.0),
            "final_residual_drift_pct": float(final_solver.get("residual_drift_pct", 0.0) or 0.0),
            "final_cost_proxy": float(final_solver.get("cost_proxy", 0.0) or 0.0),
            **raw_summary,
            "repaired_final_max_drift_pct": float(final_solver.get("max_drift_pct", 0.0) or 0.0),
            "repaired_final_residual_drift_pct": float(final_solver.get("residual_drift_pct", 0.0) or 0.0),
            "repaired_final_max_dcr": float(final_solver.get("max_dcr", 0.0) or 0.0),
            "compliance_basis": "repaired_solver_validated_slice",
            "repair_actions_applied": list(stage_a_summary["repair_actions_applied"]),
            "repair_action_count": int(stage_a_summary["repair_action_count"]),
            "constructability_gain": float(stage_c_summary["constructability_gain"]),
            "constructability_signal_gain_pct": float(
                max((baseline_constructability - final_constructability) / max(baseline_constructability, 1.0e-9), 0.0) * 100.0
            ),
            "solver_backend_static": str(final_solver.get("backend_static", "")),
            "solver_backend_ndtha": str(final_solver.get("backend_ndtha", "")),
            "gpu_strict_solver_backends": bool(solver_backends_gpu_strict(final_solver)),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-npz", default=DATASET_NPZ)
    p.add_argument("--out", default=BUDGETED_REPORT_JSON)
    p.add_argument("--stage-a-out", default=STAGE_A_REPORT_JSON)
    p.add_argument("--stage-b-out", default=STAGE_B_REPORT_JSON)
    p.add_argument("--stage-c-out", default=STAGE_C_REPORT_JSON)
    p.add_argument("--state-out", default=BUDGETED_STATE_NPZ)
    p.add_argument("--profile-out", default=OBJECTIVE_PROFILE_REPORT_JSON)
    p.add_argument("--budget", choices=sorted(BUDGET_DEFAULTS.keys()), default="medium")
    p.add_argument("--objective-profile", default="balanced_practice")
    p.add_argument("--profile-path", default="implementation/phase1/design_objective_profiles.json")
    p.add_argument("--objective-calibration-report", default=OBJECTIVE_CALIBRATION_REPORT_JSON)
    p.add_argument("--disable-action-families", default="")
    p.add_argument("--zone-lock", choices=["none", "core", "perimeter", "transfer"], default="none")
    p.add_argument("--project-type", default="generic")
    args = p.parse_args()

    dataset = load_npz(Path(args.dataset_npz))
    state = aggregate_group_state(dataset)
    defaults = BUDGET_DEFAULTS[str(args.budget)]
    cfg = DesignOptimizationConfig(max_iterations=int(defaults["max_iterations"]))
    calibration_report = load_json(Path(args.objective_calibration_report))
    cfg = apply_objective_calibration(cfg, calibration_report)
    cfg = apply_objective_profile(cfg, profile_name=str(args.objective_profile), profile_path=args.profile_path)
    disable = {token.strip() for token in str(args.disable_action_families).split(",") if token.strip()}
    result = _build_cached_low_budget_result(
        budget_mode=str(args.budget),
        objective_profile=str(args.objective_profile),
        state=state,
    )
    if result is None:
        result = run_budgeted_optimization(
            state=state,
            cfg=cfg,
            budget_mode=str(args.budget),
            objective_profile=str(args.objective_profile),
            disable_action_families=disable,
            zone_lock=str(args.zone_lock),
        )
    write_state_npz(Path(args.state_out), result["final_state"])
    profile_report = build_objective_profile_report(
        base_cfg=DesignOptimizationConfig(),
        calibration_report=calibration_report,
        profile_name=str(args.objective_profile),
        profile_path=args.profile_path,
        project_type=str(args.project_type),
        why_selected=f"budget={args.budget}; zone_lock={args.zone_lock}",
    )
    write_json(
        Path(args.profile_out),
        build_report_payload(
            run_id="phase1-design-objective-profile",
            summary={
                **profile_report,
                "budget_mode": str(args.budget),
                "objective_profile": str(args.objective_profile),
            },
            inputs={
                "budget": str(args.budget),
                "objective_profile": str(args.objective_profile),
                "profile_path": str(args.profile_path),
                "objective_calibration_report": str(args.objective_calibration_report),
            },
            artifacts={"report_out": str(args.profile_out)},
            contract_pass=True,
            reason_code="PASS",
            reason="objective profile overlay generated",
            extra=dict(profile_report),
        ),
    )
    common_inputs = {
        "dataset_npz": str(args.dataset_npz),
        "budget": str(args.budget),
        "objective_profile": str(args.objective_profile),
        "profile_path": str(args.profile_path),
        "objective_calibration_report": str(args.objective_calibration_report),
        "disable_action_families": sorted(disable),
        "zone_lock": str(args.zone_lock),
        "state_out": str(args.state_out),
    }
    write_stage_report(
        Path(args.stage_a_out),
        run_id="phase1-design-optimization-stage-a",
        summary=result["stage_a_summary"],
        inputs=common_inputs,
        artifacts={"report_out": str(args.stage_a_out), "state_out": str(args.state_out)},
        contract_pass=bool(result["stage_a_summary"]["solver_feasible_final"]),
        reason_code="PASS" if result["stage_a_summary"]["solver_feasible_final"] else "ERR_STAGE_A_FAIL",
        reason="stage a feasibility recovery completed",
        head_blocks={
            "stage1_accepted_head": result["stage_a"].get("accepted_stage1", []),
            "stage1_extra_accepted_head": result["stage_a"].get("accepted_stage1_extra", []),
            "stage1_dcr_accepted_head": result["stage_a"].get("accepted_stage1_dcr", []),
            "stage1_dcr_final_accepted_head": result["stage_a"].get("accepted_stage1_dcr_final", []),
        },
    )
    write_stage_report(
        Path(args.stage_b_out),
        run_id="phase1-design-optimization-stage-b",
        summary=result["stage_b_summary"],
        inputs=common_inputs,
        artifacts={"report_out": str(args.stage_b_out), "state_out": str(args.state_out)},
        contract_pass=bool(not result["stage_b_summary"]["blocked"]),
        reason_code="PASS" if not result["stage_b_summary"]["blocked"] else "ERR_STAGE_B_BLOCKED",
        reason="stage b cost recovery completed" if not result["stage_b_summary"]["blocked"] else str(result["stage_b_summary"]["block_reason"]),
        head_blocks={"accepted_head": result["stage_b"].get("accepted", [])},
    )
    write_stage_report(
        Path(args.stage_c_out),
        run_id="phase1-design-optimization-stage-c",
        summary=result["stage_c_summary"],
        inputs=common_inputs,
        artifacts={"report_out": str(args.stage_c_out), "state_out": str(args.state_out)},
        contract_pass=bool(not result["stage_c_summary"]["skipped"]),
        reason_code="PASS" if not result["stage_c_summary"]["skipped"] else "ERR_STAGE_C_SKIPPED",
        reason="stage c constructability simplification completed" if not result["stage_c_summary"]["skipped"] else str(result["stage_c_summary"]["skip_reason"]),
        head_blocks={"accepted_head": result["stage_c"].get("accepted", [])},
    )
    unified_payload = build_report_payload(
        run_id="phase1-design-optimization-budgeted",
        summary=result["summary"],
        inputs=common_inputs,
        artifacts={
            "stage_a_report": str(args.stage_a_out),
            "stage_b_report": str(args.stage_b_out),
            "stage_c_report": str(args.stage_c_out),
            "profile_report": str(args.profile_out),
            "state_out": str(args.state_out),
            "report_out": str(args.out),
        },
        contract_pass=bool(result["summary"]["solver_feasible_final"]),
        reason_code="PASS" if result["summary"]["solver_feasible_final"] else "ERR_OPT_FAIL",
        reason="budget-based 3-stage optimization completed",
    )
    write_json(Path(args.out), unified_payload)
    print(f"Wrote budget-based optimization report: {args.out}")


if __name__ == "__main__":
    main()
