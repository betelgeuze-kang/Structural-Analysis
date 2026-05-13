#!/usr/bin/env python3
"""Run a solver-validated constrained optimization loop on the design dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from design_optimization.artifacts import (
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    SOLVER_LOOP_REPORT_JSON,
    SOLVER_LOOP_STATE_NPZ,
)
from design_optimization.artifact_writers import write_stage_report
from design_optimization.io import load_json as _load_json, load_npz as _load_npz, write_state_npz as _write_state_npz
from design_objective_calibration import apply_objective_calibration, apply_objective_profile
from design_optimization_env import (
    DesignOptimizationConfig,
    aggregate_group_state,
    apply_group_action,
    evaluate_stage_state,
    hydrate_state_constructability_fields,
    project_group_cost_proxy,
    run_two_stage_search,
)
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    RustNonlinearNdthaConfig,
    solve_nonlinear_frame,
    solve_nonlinear_frame_ndtha,
)


def solver_backends_gpu_strict(solver: dict[str, object]) -> bool:
    backend_static = str(solver.get("backend_static", "")).strip().lower()
    backend_ndtha = str(solver.get("backend_ndtha", "")).strip().lower()
    if not backend_static or not backend_ndtha:
        return False
    if "cpu" in backend_static or "cpu" in backend_ndtha:
        return False
    return True
def _build_story_model_from_state(state: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    story_band = np.asarray(state["story_band"], dtype=np.int32)
    rebar_ratio = np.asarray(state["rebar_ratio"], dtype=np.float64)
    max_dcr = np.asarray(state["max_dcr"], dtype=np.float64)
    repair = np.asarray(state["repair_influence"], dtype=np.float64)
    congestion = np.asarray(state["congestion"], dtype=np.float64)
    detailing = np.asarray(state["detailing"], dtype=np.float64)
    zones = np.asarray(state["zone_label"])
    combination_risk = np.asarray(state.get("combination_risk", np.ones_like(rebar_ratio)), dtype=np.float64)
    combination_match = np.asarray(state.get("combination_match_score", np.ones_like(rebar_ratio)), dtype=np.float64)
    semantic_groups = np.asarray(state.get("semantic_group", np.asarray([""] * rebar_ratio.size)), dtype="<U96")

    n_story = int(np.max(story_band)) + 1 if story_band.size else 1
    story_h = np.full(n_story, 3.5, dtype=np.float64)
    base_k = np.linspace(420000.0, 165000.0, n_story, dtype=np.float64)
    base_mass = np.linspace(1.65e6, 0.72e6, n_story, dtype=np.float64)
    base_axial = np.linspace(1.35e7, 2.10e6, n_story, dtype=np.float64)

    story_k = np.zeros(n_story, dtype=np.float64)
    story_mass = np.zeros(n_story, dtype=np.float64)
    story_axial = np.zeros(n_story, dtype=np.float64)
    story_yield = np.zeros(n_story, dtype=np.float64)
    floor_load = np.zeros(n_story, dtype=np.float64)

    for band in range(n_story):
        idx = np.where(story_band == band)[0]
        if idx.size == 0:
            idx = np.asarray([max(0, band - 1)], dtype=np.int32)
        weights = 1.0 + np.maximum(combination_risk[idx] - 1.0, 0.0) + (np.asarray([1.0 if str(v).strip() else 0.0 for v in semantic_groups[idx]], dtype=np.float64) * 0.20)
        weights = np.maximum(weights, 1.0e-6)
        rebar = float(np.average(rebar_ratio[idx], weights=weights))
        dcr = float(np.max(max_dcr[idx]))
        inf = float(np.average(repair[idx], weights=weights))
        cong = float(np.average(congestion[idx], weights=weights))
        detail = float(np.average(detailing[idx], weights=weights))
        combo_risk = float(np.average(combination_risk[idx], weights=weights))
        combo_match = float(np.average(combination_match[idx], weights=weights))
        zone = str(zones[idx[0]]).strip().lower() if idx.size else "intermediate"

        zone_scale = {
            "transfer": 1.22,
            "core": 1.10,
            "perimeter": 0.94,
            "intermediate": 1.0,
        }.get(zone, 1.0)

        stiffness_scale = np.clip((0.52 + 16.5 * rebar) * zone_scale * (0.92 + 0.08 * inf) * (1.0 + 0.30 * max(combo_risk - 1.0, 0.0)), 0.50, 3.40)
        degradation = 1.0 + 0.16 * dcr + 0.05 * cong + 0.03 * detail + 0.06 * max(1.0 - combo_match, 0.0)
        story_k[band] = float(base_k[band] * stiffness_scale / degradation)
        story_mass[band] = float(base_mass[band] * (0.96 + 0.04 * zone_scale))
        story_axial[band] = float(base_axial[band] * (0.94 + 0.06 * zone_scale))
        story_yield[band] = float(story_h[band] * np.clip((0.011 + 0.42 * rebar) * (1.0 + 0.08 * max(combo_risk - 1.0, 0.0)), 0.006, 0.036))
        floor_load[band] = float(story_axial[band] * 0.085)

    story_damp = 0.055 * np.sqrt(np.maximum(story_k, 1.0) * 1000.0 * np.maximum(story_mass, 1.0))
    return {
        "story_k_n_per_m": story_k,
        "story_h_m": story_h,
        "story_axial_n": story_axial,
        "story_yield_drift_m": story_yield,
        "story_mass_kg": story_mass,
        "story_damping_n_s_per_m": story_damp.astype(np.float64),
        "floor_load_base_n": floor_load,
    }


def _solver_repair_priority(state: dict[str, np.ndarray], cfg: DesignOptimizationConfig) -> np.ndarray:
    max_dcr = np.asarray(state["max_dcr"], dtype=np.float64)
    repair = np.asarray(state["repair_influence"], dtype=np.float64)
    detailing = np.asarray(state["detailing"], dtype=np.float64)
    rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    combo_risk = np.asarray(state.get("combination_risk", np.ones_like(rebar)), dtype=np.float64)
    combo_match = np.asarray(state.get("combination_match_score", np.ones_like(rebar)), dtype=np.float64)
    semantic = np.asarray(state.get("semantic_group", np.asarray([""] * rebar.size)), dtype="<U96")
    headroom = (float(cfg.max_rebar_ratio) - rebar) / max(float(cfg.max_rebar_ratio) - float(cfg.min_rebar_ratio), 1.0e-9)
    headroom = np.clip(headroom, 0.05, 1.0)
    semantic_bonus = np.asarray([1.10 if str(v).strip() else 1.0 for v in semantic], dtype=np.float64)
    dcr_excess = np.maximum(max_dcr - float(cfg.dcr_limit), 0.0) + 0.35 * max_dcr
    priority = (1.0 + dcr_excess) * repair * (1.0 + detailing) * (1.0 + 0.90 * np.maximum(combo_risk - 1.0, 0.0)) * (1.0 + 0.25 * np.maximum(1.0 - combo_match, 0.0))
    priority *= semantic_bonus * headroom
    return np.asarray(priority, dtype=np.float64)


def _apply_group_steps(
    *,
    state: dict[str, np.ndarray],
    group_index: int,
    steps: int,
    direction: int,
    cfg: DesignOptimizationConfig,
    action_name: str,
) -> dict[str, np.ndarray]:
    updated_rebar = np.asarray(state["rebar_ratio"], dtype=np.float64).copy()
    updated_thickness = np.asarray(state.get("thickness_scale", np.ones_like(updated_rebar)), dtype=np.float64).copy()
    updated_detailing = np.asarray(state.get("detailing_quality", np.ones_like(updated_rebar)), dtype=np.float64).copy()
    for _ in range(max(int(steps), 0)):
        next_updated = apply_group_action(
            rebar_ratio=updated_rebar,
            action_mask=np.asarray(state["action_mask"], dtype=np.bool_),
            group_index=int(group_index),
            direction=int(direction),
            cfg=cfg,
            action_name=str(action_name),
            action_mask_extended=np.asarray(state.get("action_mask_extended", np.ones((updated_rebar.size, 6), dtype=np.bool_)), dtype=np.bool_),
            thickness_scale=updated_thickness,
            detailing_quality=updated_detailing,
        )
        next_rebar = np.asarray(next_updated["rebar_ratio"], dtype=np.float64)
        next_thickness = np.asarray(next_updated["thickness_scale"], dtype=np.float64)
        next_detailing = np.asarray(next_updated["detailing_quality"], dtype=np.float64)
        if (
            np.allclose(next_rebar, updated_rebar)
            and np.allclose(next_thickness, updated_thickness)
            and np.allclose(next_detailing, updated_detailing)
        ):
            break
        updated_rebar = next_rebar
        updated_thickness = next_thickness
        updated_detailing = next_detailing
    return {
        "rebar_ratio": updated_rebar,
        "thickness_scale": updated_thickness,
        "detailing_quality": updated_detailing,
    }


def _local_dcr_update(
    *,
    state: dict[str, np.ndarray],
    group_index: int,
    delta: float,
    local_gain: float,
) -> np.ndarray:
    current = np.asarray(state["max_dcr"], dtype=np.float64)
    updated = current.copy()
    zones = np.asarray(state["zone_label"])
    member_types = np.asarray(state["member_type"])
    stories = np.asarray(state["story_band"], dtype=np.int32)
    semantics = np.asarray(state.get("semantic_group", np.asarray([""] * current.size)), dtype="<U96")
    gi = int(group_index)
    same_story = stories == stories[gi]
    same_zone_type = (zones == zones[gi]) & (member_types == member_types[gi])
    same_semantic = np.asarray([str(v).strip() == str(semantics[gi]).strip() and str(v).strip() != "" for v in semantics], dtype=np.bool_)
    related = same_story | same_zone_type | same_semantic
    updated[related] = np.maximum(
        0.0,
        updated[related] - float(delta) * float(local_gain) * 0.22,
    )
    updated[gi] = max(0.0, float(updated[gi]) - float(delta) * float(local_gain))
    return updated


def _deterministic_ag(dt_s: float, step_count: int) -> np.ndarray:
    t = np.arange(step_count, dtype=np.float64) * float(dt_s)
    ag = (
        0.016 * np.sin(2.0 * np.pi * 1.15 * t) * np.exp(-0.010 * t)
        + 0.006 * np.sin(2.0 * np.pi * 2.80 * t + 0.35) * np.exp(-0.020 * t)
        + 0.003 * np.sin(2.0 * np.pi * 5.10 * t + 1.00)
    )
    return ag.astype(np.float64)


def _response_array(response: dict[str, object], key: str, *, dtype) -> np.ndarray:
    value = response.get(key, [])
    if value is None:
        return np.asarray([], dtype=dtype)
    return np.asarray(value, dtype=dtype).reshape(-1)


def _solver_stage_state(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    dt_s: float = 0.02,
    step_count: int = 240,
) -> dict[str, object]:
    story = _build_story_model_from_state(state)
    static_cfg = RustNonlinearFrameConfig()
    ndtha_cfg = RustNonlinearNdthaConfig(
        dt_s=float(dt_s),
        newmark_beta=0.25,
        newmark_gamma=0.5,
        tolerance=1.0e-5,
        max_step_iterations=14,
        adaptive_load_decay=0.84,
        damping_force_cap_ratio=0.60,
        newton_max_iter=90,
        line_search_decay=0.5,
        line_search_min=0.03125,
        hardening_ratio=0.18,
        pdelta_factor=1.0,
        collapse_drift_threshold_pct=max(float(cfg.drift_limit_pct) * 1.08, 2.1),
        residual_settle_steps=48,
        residual_settle_relax=0.22,
        residual_velocity_decay=0.30,
        residual_plastic_retention=0.18,
    )
    ag = _deterministic_ag(dt_s=float(dt_s), step_count=int(step_count))
    static = solve_nonlinear_frame(
        story_k_n_per_m=story["story_k_n_per_m"],
        story_h_m=story["story_h_m"],
        story_axial_n=story["story_axial_n"],
        story_yield_drift_m=story["story_yield_drift_m"],
        floor_load_n=story["floor_load_base_n"],
        cfg=static_cfg,
        keep_device_artifacts=True,
    )
    ndtha = solve_nonlinear_frame_ndtha(
        story_k_n_per_m=story["story_k_n_per_m"],
        story_h_m=story["story_h_m"],
        story_axial_n=story["story_axial_n"],
        story_yield_drift_m=story["story_yield_drift_m"],
        story_mass_kg=story["story_mass_kg"],
        story_damping_n_s_per_m=story["story_damping_n_s_per_m"],
        floor_load_base_n=story["floor_load_base_n"],
        ag_g=ag,
        cfg=ndtha_cfg,
        keep_device_artifacts=True,
    )
    static_runtime = static.get("runtime") if isinstance(static.get("runtime"), dict) else {}
    ndtha_runtime = ndtha.get("runtime") if isinstance(ndtha.get("runtime"), dict) else {}
    solver_drift = float(abs(ndtha.get("max_drift_ratio_pct", 0.0) or 0.0))
    residual_drift = float(abs(ndtha.get("residual_drift_ratio_pct", 0.0) or 0.0))
    residual_top = float(abs(ndtha.get("residual_top_displacement_m", 0.0) or 0.0))
    state_for_eval = {k: np.asarray(v).copy() for k, v in state.items()}
    state_for_eval["global_drift_pct"] = np.asarray([solver_drift], dtype=np.float64)
    state_for_eval["global_residual_drift_pct"] = np.asarray([residual_drift], dtype=np.float64)
    stage_eval = evaluate_stage_state(state=state_for_eval, cfg=cfg)
    hard_penalty = 0.0
    if bool(ndtha.get("collapsed", False)):
        hard_penalty += 1.0e6
    if not bool(ndtha.get("converged_all_steps", False)):
        hard_penalty += 1.0e5
    violation = float(stage_eval.violation_score + hard_penalty)
    hard_feasible = bool(
        hard_penalty <= 0.0
        and float(np.max(np.asarray(state["max_dcr"], dtype=np.float64))) <= float(cfg.dcr_limit) + 1.0e-9
        and float(solver_drift) <= float(cfg.drift_limit_pct) + 1.0e-9
        and float(residual_drift) <= float(cfg.residual_drift_limit_pct) + 1.0e-9
    )
    return {
        "violation_score": float(violation),
        "feasible": bool(hard_feasible),
        "soft_violation_score": float(stage_eval.violation_score),
        "collapsed": bool(ndtha.get("collapsed", False)),
        "converged_all_steps": bool(ndtha.get("converged_all_steps", False)),
        "max_dcr": float(np.max(np.asarray(state["max_dcr"], dtype=np.float64))),
        "max_drift_pct": float(solver_drift),
        "residual_drift_pct": float(residual_drift),
        "residual_top_displacement_m": float(residual_top),
        "static_top_displacement_m": float(static.get("top_displacement_m", 0.0)),
        "static_converged": bool(static.get("converged", False)),
        "backend_static": str(static_runtime.get("main_loop_backend", static.get("backend", ""))),
        "backend_ndtha": str(ndtha_runtime.get("main_loop_backend", ndtha.get("backend", ""))),
        "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
    }


def run_solver_constrained_loop(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int = 240,
    target_dcr_margin: float = 0.0,
    per_group_escalation_cap: int = 16,
) -> dict[str, object]:
    proposal = run_two_stage_search(state=state, cfg=cfg)
    current_state = {k: np.asarray(v).copy() for k, v in state.items()}
    baseline_solver = _solver_stage_state(state=current_state, cfg=cfg, step_count=ndtha_step_count)
    current_solver = dict(baseline_solver)
    accepted_stage1: list[dict[str, object]] = []
    accepted_stage2: list[dict[str, object]] = []
    rebar_ratio = np.asarray(current_state["rebar_ratio"], dtype=np.float64)
    escalation_used = np.zeros_like(rebar_ratio, dtype=np.int32)
    target_max_dcr = max(float(cfg.dcr_limit) - float(target_dcr_margin), 0.10)
    low_budget_mode = bool(int(cfg.max_iterations) <= 16 or int(ndtha_step_count) <= 96)
    initial_repair_steps = 2 if low_budget_mode else 1
    extra_step_candidates = (8, 6, 4, 2, 1) if low_budget_mode else (5, 4, 3, 2, 1)
    dcr_step_candidates = (12, 10, 8, 6, 4, 2, 1) if low_budget_mode else (8, 6, 4, 2, 1)
    low_budget_gain = 1.22 if low_budget_mode else 1.0

    for step in proposal["repair_history"]:
        gi = int(step["group_index"])
        trial_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
        action_name = str(step.get("action_name", "rebar_up"))
        step_update = _apply_group_steps(
            state=current_state,
            group_index=gi,
            steps=initial_repair_steps,
            direction=1,
            cfg=cfg,
            action_name=action_name,
        )
        trial_state["rebar_ratio"] = np.asarray(step_update["rebar_ratio"], dtype=np.float64)
        trial_state["thickness_scale"] = np.asarray(step_update["thickness_scale"], dtype=np.float64)
        trial_state["detailing_quality"] = np.asarray(step_update["detailing_quality"], dtype=np.float64)
        trial_state = {
            **trial_state,
            **{
                "max_dcr": np.asarray(
                    np.asarray(current_state["max_dcr"], dtype=np.float64)
                    - (trial_state["rebar_ratio"] - np.asarray(current_state["rebar_ratio"], dtype=np.float64)) * 18.0,
                    dtype=np.float64,
                ),
                "group_cost_proxy": project_group_cost_proxy(
                    state=current_state,
                    rebar_ratio=np.asarray(trial_state["rebar_ratio"], dtype=np.float64),
                    thickness_scale=np.asarray(trial_state["thickness_scale"], dtype=np.float64),
                    detailing_quality=np.asarray(trial_state["detailing_quality"], dtype=np.float64),
                ),
            },
        }
        trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
        if float(trial_solver["violation_score"]) + 1.0e-9 < float(current_solver["violation_score"]):
            current_state = trial_state
            current_solver = trial_solver
            escalation_used[gi] += 1
            accepted_stage1.append(
                {
                    "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                    "action_name": action_name,
                    "group_index": gi,
                    "violation_score": float(trial_solver["violation_score"]),
                    "max_drift_pct": float(trial_solver["max_drift_pct"]),
                    "residual_drift_pct": float(trial_solver["residual_drift_pct"]),
                }
            )

    extra_stage1: list[dict[str, object]] = []
    for _ in range(min(int(cfg.max_iterations), 12)):
        if bool(current_solver["feasible"]):
            break
        priority = _solver_repair_priority(current_state, cfg)
        ranked = np.argsort(-priority)
        best: tuple[dict[str, np.ndarray], dict[str, object], int, int] | None = None
        best_improvement = 0.0
        current_rebar = np.asarray(current_state["rebar_ratio"], dtype=np.float64)
        for gi in ranked[: min(12 if low_budget_mode else 8, ranked.size)]:
            gi = int(gi)
            remaining_cap = int(max(0, int(per_group_escalation_cap) - int(escalation_used[gi])))
            if remaining_cap <= 0:
                continue
            for steps in extra_step_candidates:
                steps = min(int(steps), remaining_cap)
                if steps <= 0:
                    continue
                for action_name in ("rebar_up", "thickness_up", "detailing_up"):
                    trial_update = _apply_group_steps(
                        state=current_state,
                        group_index=gi,
                        steps=int(steps),
                        direction=1,
                        cfg=cfg,
                        action_name=action_name,
                    )
                    trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
                    if (
                        np.allclose(trial_rebar, current_rebar)
                        and np.allclose(np.asarray(trial_update["thickness_scale"], dtype=np.float64), np.asarray(current_state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64))
                        and np.allclose(np.asarray(trial_update["detailing_quality"], dtype=np.float64), np.asarray(current_state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64))
                    ):
                        continue
                    delta = np.asarray(trial_rebar - current_rebar, dtype=np.float64)
                    trial_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
                    trial_state["rebar_ratio"] = trial_rebar
                    trial_state["thickness_scale"] = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
                    trial_state["detailing_quality"] = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
                    trial_state["max_dcr"] = np.asarray(
                        np.asarray(current_state["max_dcr"], dtype=np.float64)
                        - delta * (
                            26.0 * low_budget_gain
                            + 4.0 * np.asarray(current_state["repair_influence"], dtype=np.float64)
                            + 3.5 * np.asarray(current_state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)
                            + 2.0 * np.asarray(current_state["detailing"], dtype=np.float64)
                        ),
                        dtype=np.float64,
                    )
                    trial_state["group_cost_proxy"] = project_group_cost_proxy(
                        state=current_state,
                        rebar_ratio=trial_rebar,
                        thickness_scale=np.asarray(trial_update["thickness_scale"], dtype=np.float64),
                        detailing_quality=np.asarray(trial_update["detailing_quality"], dtype=np.float64),
                    )
                    trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
                    improvement = float(current_solver["violation_score"]) - float(trial_solver["violation_score"])
                    if improvement > best_improvement + 1.0e-9:
                        best = (trial_state, trial_solver, gi, int(steps), action_name)
                        best_improvement = float(improvement)
                        if bool(trial_solver["feasible"]):
                            break
                if best is not None and bool(best[1]["feasible"]):
                    break
            if best is not None and bool(best[1]["feasible"]):
                break
        if best is None:
            break
        current_state, current_solver, gi, steps, action_name = best
        escalation_used[gi] += int(steps)
        extra_stage1.append(
            {
                "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                "group_index": int(gi),
                "action_name": str(action_name),
                "steps": int(steps),
                "violation_score": float(current_solver["violation_score"]),
                "max_drift_pct": float(current_solver["max_drift_pct"]),
                "residual_drift_pct": float(current_solver["residual_drift_pct"]),
            }
        )

    dcr_stage1: list[dict[str, object]] = []
    for _ in range(min(int(cfg.max_iterations), 8)):
        if bool(current_solver["feasible"]) or float(current_solver["max_dcr"]) <= float(target_max_dcr) + 1.0e-9:
            break
        current_rebar = np.asarray(current_state["rebar_ratio"], dtype=np.float64)
        current_dcr = np.asarray(current_state["max_dcr"], dtype=np.float64)
        combo_risk = np.asarray(current_state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)
        repair = np.asarray(current_state["repair_influence"], dtype=np.float64)
        detail = np.asarray(current_state["detailing"], dtype=np.float64)
        semantic = np.asarray(current_state.get("semantic_group", np.asarray([""] * current_rebar.size)), dtype="<U96")
        dcr_priority = np.maximum(current_dcr - float(cfg.dcr_limit), 0.0) * (
            1.0 + 0.60 * np.maximum(combo_risk - 1.0, 0.0)
        ) * (1.0 + 0.25 * repair + 0.12 * detail) * np.asarray([1.08 if str(v).strip() else 1.0 for v in semantic], dtype=np.float64)
        ranked = np.argsort(-dcr_priority)
        best: tuple[dict[str, np.ndarray], dict[str, object], int, int] | None = None
        best_max_dcr = float(current_solver["max_dcr"])
        for gi in ranked[: min(10 if low_budget_mode else 6, ranked.size)]:
            gi = int(gi)
            if float(current_dcr[gi]) <= float(target_max_dcr) + 1.0e-9:
                continue
            remaining_cap = int(max(0, int(per_group_escalation_cap) - int(escalation_used[gi])))
            if remaining_cap <= 0:
                continue
            for steps in dcr_step_candidates:
                steps = min(int(steps), remaining_cap)
                if steps <= 0:
                    continue
                for action_name in ("rebar_up", "thickness_up", "detailing_up"):
                    trial_update = _apply_group_steps(
                        state=current_state,
                        group_index=gi,
                        steps=int(steps),
                        direction=1,
                        cfg=cfg,
                        action_name=action_name,
                    )
                    trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
                    if (
                        np.allclose(trial_rebar, current_rebar)
                        and np.allclose(np.asarray(trial_update["thickness_scale"], dtype=np.float64), np.asarray(current_state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64))
                        and np.allclose(np.asarray(trial_update["detailing_quality"], dtype=np.float64), np.asarray(current_state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64))
                    ):
                        continue
                    delta = np.asarray(trial_rebar - current_rebar, dtype=np.float64)
                    trial_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
                    trial_state["rebar_ratio"] = trial_rebar
                    trial_state["thickness_scale"] = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
                    trial_state["detailing_quality"] = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
                    local_gain = float(
                        42.0 * low_budget_gain
                        + 6.0 * float(current_state["repair_influence"][gi])
                        + 5.0 * float(current_state.get("combination_risk", np.ones_like(current_rebar))[gi])
                        + 3.0 * float(current_state["detailing"][gi])
                    )
                    trial_state["max_dcr"] = _local_dcr_update(
                        state=current_state,
                        group_index=gi,
                        delta=float(delta[gi]),
                        local_gain=float(local_gain),
                    )
                    trial_state["group_cost_proxy"] = project_group_cost_proxy(
                        state=current_state,
                        rebar_ratio=trial_rebar,
                        thickness_scale=np.asarray(trial_update["thickness_scale"], dtype=np.float64),
                        detailing_quality=np.asarray(trial_update["detailing_quality"], dtype=np.float64),
                    )
                    trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
                    drift_guard = max(float(cfg.drift_limit_pct), float(current_solver["max_drift_pct"])) + (0.12 if low_budget_mode else 0.0)
                    residual_guard = max(float(cfg.residual_drift_limit_pct), float(current_solver["residual_drift_pct"])) + (0.04 if low_budget_mode else 0.0)
                    if (
                        float(trial_solver["max_dcr"]) + 1.0e-9 < float(best_max_dcr)
                        and float(trial_solver["max_drift_pct"]) <= drift_guard + 1.0e-9
                        and float(trial_solver["residual_drift_pct"]) <= residual_guard + 1.0e-9
                        and not bool(trial_solver["collapsed"])
                    ):
                        best = (trial_state, trial_solver, gi, int(steps), action_name)
                        best_max_dcr = float(trial_solver["max_dcr"])
                        if float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                            break
                if best is not None and float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                    break
                if best is not None and float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                    break
        if best is None:
            break
        current_state, current_solver, gi, steps, action_name = best
        escalation_used[gi] += int(steps)
        dcr_stage1.append(
            {
                "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                "group_index": int(gi),
                "action_name": str(action_name),
                "steps": int(steps),
                "max_dcr": float(current_solver["max_dcr"]),
                "max_drift_pct": float(current_solver["max_drift_pct"]),
                "residual_drift_pct": float(current_solver["residual_drift_pct"]),
            }
        )

    dcr_stage1_final: list[dict[str, object]] = []
    if low_budget_mode and float(current_solver["max_dcr"]) > float(target_max_dcr) + 1.0e-9:
        for _ in range(4):
            if float(current_solver["max_dcr"]) <= float(target_max_dcr) + 1.0e-9:
                break
            current_rebar = np.asarray(current_state["rebar_ratio"], dtype=np.float64)
            current_dcr = np.asarray(current_state["max_dcr"], dtype=np.float64)
            ranked = np.argsort(-current_dcr)
            best: tuple[dict[str, np.ndarray], dict[str, object], int, int] | None = None
            best_max_dcr = float(current_solver["max_dcr"])
            for gi in ranked[: min(6, ranked.size)]:
                gi = int(gi)
                if float(current_dcr[gi]) <= float(target_max_dcr) + 1.0e-9:
                    continue
                remaining_cap = int(max(0, int(per_group_escalation_cap) + 4 - int(escalation_used[gi])))
                if remaining_cap <= 0:
                    continue
                for steps in (4, 3, 2, 1):
                    steps = min(int(steps), remaining_cap)
                    if steps <= 0:
                        continue
                    for action_name in ("rebar_up", "thickness_up", "detailing_up"):
                        trial_update = _apply_group_steps(
                            state=current_state,
                            group_index=gi,
                            steps=int(steps),
                            direction=1,
                            cfg=cfg,
                            action_name=action_name,
                        )
                        trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
                        if (
                            np.allclose(trial_rebar, current_rebar)
                            and np.allclose(np.asarray(trial_update["thickness_scale"], dtype=np.float64), np.asarray(current_state.get("thickness_scale", np.ones_like(current_rebar)), dtype=np.float64))
                            and np.allclose(np.asarray(trial_update["detailing_quality"], dtype=np.float64), np.asarray(current_state.get("detailing_quality", np.ones_like(current_rebar)), dtype=np.float64))
                        ):
                            continue
                        delta = np.asarray(trial_rebar - current_rebar, dtype=np.float64)
                        trial_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
                        trial_state["rebar_ratio"] = trial_rebar
                        trial_state["thickness_scale"] = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
                        trial_state["detailing_quality"] = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
                        local_gain = float(
                            58.0 * low_budget_gain
                            + 8.0 * float(current_state["repair_influence"][gi])
                            + 6.0 * float(current_state.get("combination_risk", np.ones_like(current_rebar))[gi])
                            + 4.0 * float(current_state["detailing"][gi])
                        )
                        trial_state["max_dcr"] = _local_dcr_update(
                            state=current_state,
                            group_index=gi,
                            delta=float(delta[gi]),
                            local_gain=float(local_gain),
                        )
                        trial_state["group_cost_proxy"] = project_group_cost_proxy(
                            state=current_state,
                            rebar_ratio=trial_rebar,
                            thickness_scale=np.asarray(trial_update["thickness_scale"], dtype=np.float64),
                            detailing_quality=np.asarray(trial_update["detailing_quality"], dtype=np.float64),
                        )
                        trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
                        drift_guard = max(float(cfg.drift_limit_pct), float(current_solver["max_drift_pct"])) + 0.18
                        residual_guard = max(float(cfg.residual_drift_limit_pct), float(current_solver["residual_drift_pct"])) + 0.06
                        if (
                            float(trial_solver["max_dcr"]) + 1.0e-9 < float(best_max_dcr)
                            and float(trial_solver["max_drift_pct"]) <= drift_guard + 1.0e-9
                            and float(trial_solver["residual_drift_pct"]) <= residual_guard + 1.0e-9
                            and not bool(trial_solver["collapsed"])
                        ):
                            best = (trial_state, trial_solver, gi, int(steps), action_name)
                            best_max_dcr = float(trial_solver["max_dcr"])
                            if float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                                break
                    if best is not None and float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                        break
                if best is not None and float(best_max_dcr) <= float(target_max_dcr) + 1.0e-9:
                    break
            if best is None:
                break
            current_state, current_solver, gi, steps, action_name = best
            escalation_used[gi] += int(steps)
            dcr_stage1_final.append(
                {
                    "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                    "group_index": int(gi),
                    "action_name": str(action_name),
                    "steps": int(steps),
                    "max_dcr": float(current_solver["max_dcr"]),
                    "max_drift_pct": float(current_solver["max_drift_pct"]),
                    "residual_drift_pct": float(current_solver["residual_drift_pct"]),
                }
            )

    stage2_candidates = list(proposal["cost_reduction_history"])
    if not stage2_candidates:
        cost_order = np.argsort(-np.asarray(current_state["group_cost_proxy"], dtype=np.float64))
        stage2_candidates = [{"group_index": int(gi)} for gi in cost_order[:96].tolist()]

    if bool(current_solver["feasible"]) and float(current_solver["violation_score"]) + 1.0e-9 < float(baseline_solver["violation_score"]):
        for step in stage2_candidates:
            gi = int(step["group_index"])
            action_name = str(step.get("action_name", "rebar_down"))
            trial_update = apply_group_action(
                rebar_ratio=np.asarray(current_state["rebar_ratio"], dtype=np.float64),
                action_mask=np.asarray(current_state["action_mask"], dtype=np.bool_),
                group_index=gi,
                direction=-1,
                cfg=cfg,
                action_name=action_name,
                action_mask_extended=np.asarray(current_state.get("action_mask_extended", np.ones((np.asarray(current_state["rebar_ratio"]).size, 6), dtype=np.bool_)), dtype=np.bool_),
                thickness_scale=np.asarray(current_state.get("thickness_scale", np.ones_like(np.asarray(current_state["rebar_ratio"], dtype=np.float64))), dtype=np.float64),
                detailing_quality=np.asarray(current_state.get("detailing_quality", np.ones_like(np.asarray(current_state["rebar_ratio"], dtype=np.float64))), dtype=np.float64),
            )
            trial_rebar = np.asarray(trial_update["rebar_ratio"], dtype=np.float64)
            if np.allclose(trial_rebar, np.asarray(current_state["rebar_ratio"], dtype=np.float64)):
                continue
            trial_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
            trial_state["rebar_ratio"] = trial_rebar
            trial_state["thickness_scale"] = np.asarray(trial_update["thickness_scale"], dtype=np.float64)
            trial_state["detailing_quality"] = np.asarray(trial_update["detailing_quality"], dtype=np.float64)
            trial_state["max_dcr"] = np.asarray(
                np.asarray(current_state["max_dcr"], dtype=np.float64)
                + (np.asarray(current_state["rebar_ratio"], dtype=np.float64) - trial_rebar) * 1.6,
                dtype=np.float64,
            )
            trial_state["group_cost_proxy"] = project_group_cost_proxy(
                state=current_state,
                rebar_ratio=trial_rebar,
                thickness_scale=np.asarray(trial_update["thickness_scale"], dtype=np.float64),
                detailing_quality=np.asarray(trial_update["detailing_quality"], dtype=np.float64),
            )
            trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count)
            if (
                True
                and float(trial_solver["cost_proxy"]) + 1.0e-9 < float(current_solver["cost_proxy"])
                and float(trial_solver["violation_score"]) <= float(current_solver["violation_score"]) + 25.0
                and float(trial_solver["max_dcr"]) <= float(current_solver["max_dcr"]) + 0.02
                and float(trial_solver["max_drift_pct"]) <= float(current_solver["max_drift_pct"]) + 0.05
                and (not bool(current_solver["feasible"]) or bool(trial_solver["feasible"]))
                and not bool(trial_solver["collapsed"])
            ):
                current_state = trial_state
                current_solver = trial_solver
                accepted_stage2.append(
                    {
                        "group_id": str(np.asarray(current_state["group_ids"])[gi]),
                        "action_name": action_name,
                        "group_index": gi,
                        "cost_proxy": float(trial_solver["cost_proxy"]),
                        "max_drift_pct": float(trial_solver["max_drift_pct"]),
                        "residual_drift_pct": float(trial_solver["residual_drift_pct"]),
                    }
                )

    return {
        "baseline_solver": baseline_solver,
        "final_solver": current_solver,
        "accepted_stage1": accepted_stage1,
        "accepted_stage1_extra": extra_stage1,
        "accepted_stage1_dcr": dcr_stage1,
        "accepted_stage1_dcr_final": dcr_stage1_final,
        "accepted_stage2": accepted_stage2,
        "proposed_stage1": list(proposal["repair_history"]),
        "proposed_stage2": stage2_candidates,
        "baseline_cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        "final_cost_proxy": float(current_solver["cost_proxy"]),
        "cost_reduction_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64)) - float(current_solver["cost_proxy"])),
        "baseline_violation_score_heuristic": float(proposal["baseline_violation_score"]),
        "final_violation_score_heuristic": float(proposal["final_violation_score"]),
        "final_state": current_state,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dataset-npz",
        default=DATASET_NPZ,
    )
    p.add_argument(
        "--out",
        default=SOLVER_LOOP_REPORT_JSON,
    )
    p.add_argument("--rebar-step", type=float, default=0.002)
    p.add_argument("--thickness-step", type=float, default=0.01)
    p.add_argument("--detailing-step", type=float, default=0.03)
    p.add_argument("--min-rebar-ratio", type=float, default=0.004)
    p.add_argument("--max-rebar-ratio", type=float, default=0.08)
    p.add_argument("--max-iterations", type=int, default=16)
    p.add_argument("--dcr-limit", type=float, default=1.0)
    p.add_argument("--drift-limit-pct", type=float, default=2.0)
    p.add_argument("--residual-drift-limit-pct", type=float, default=0.5)
    p.add_argument("--ndtha-step-count", type=int, default=96)
    p.add_argument("--target-dcr-margin", type=float, default=0.0)
    p.add_argument("--per-group-escalation-cap", type=int, default=8)
    p.add_argument(
        "--objective-calibration-report",
        default=OBJECTIVE_CALIBRATION_REPORT_JSON,
    )
    p.add_argument("--objective-profile", default="balanced_practice")
    p.add_argument(
        "--state-out",
        default=SOLVER_LOOP_STATE_NPZ,
    )
    args = p.parse_args()

    dataset = _load_npz(Path(args.dataset_npz))
    state = aggregate_group_state(dataset)
    cfg = DesignOptimizationConfig(
        rebar_step=float(args.rebar_step),
        thickness_step=float(args.thickness_step),
        detailing_step=float(args.detailing_step),
        min_rebar_ratio=float(args.min_rebar_ratio),
        max_rebar_ratio=float(args.max_rebar_ratio),
        max_iterations=int(args.max_iterations),
        dcr_limit=float(args.dcr_limit),
        drift_limit_pct=float(args.drift_limit_pct),
        residual_drift_limit_pct=float(args.residual_drift_limit_pct),
    )
    calibration_report = _load_json(Path(args.objective_calibration_report))
    cfg = apply_objective_calibration(cfg, calibration_report)
    cfg = apply_objective_profile(cfg, profile_name=str(args.objective_profile))
    result = run_solver_constrained_loop(
        state=state,
        cfg=cfg,
        ndtha_step_count=int(args.ndtha_step_count),
        target_dcr_margin=float(args.target_dcr_margin),
        per_group_escalation_cap=int(args.per_group_escalation_cap),
    )
    baseline_solver = result["baseline_solver"]
    final_solver = result["final_solver"]
    repair_actions_applied: list[str] = []
    for rows in (
        result["accepted_stage1"],
        result.get("accepted_stage1_extra", []),
        result.get("accepted_stage1_dcr", []),
        result.get("accepted_stage1_dcr_final", []),
        result["accepted_stage2"],
    ):
        for row in rows:
            action_name = str(row.get("action_name", "")).strip()
            if action_name and action_name not in repair_actions_applied:
                repair_actions_applied.append(action_name)
    final_state = hydrate_state_constructability_fields(
        state=result["final_state"],
        reference_state=state,
    )
    _write_state_npz(Path(args.state_out), final_state)
    write_stage_report(
        Path(args.out),
        run_id="phase1-design-optimization-solver-loop",
        summary={
            "baseline_cost_proxy": float(result["baseline_cost_proxy"]),
            "final_cost_proxy": float(result["final_cost_proxy"]),
            "cost_reduction_proxy": float(result["cost_reduction_proxy"]),
            "baseline_violation_score_heuristic": float(result["baseline_violation_score_heuristic"]),
            "final_violation_score_heuristic": float(result["final_violation_score_heuristic"]),
            "baseline_violation_score_solver": float(baseline_solver["violation_score"]),
            "final_violation_score_solver": float(final_solver["violation_score"]),
            "baseline_max_drift_pct": float(baseline_solver["max_drift_pct"]),
            "final_max_drift_pct": float(final_solver["max_drift_pct"]),
            "baseline_residual_drift_pct": float(baseline_solver["residual_drift_pct"]),
            "final_residual_drift_pct": float(final_solver["residual_drift_pct"]),
            "baseline_max_dcr": float(baseline_solver["max_dcr"]),
            "final_max_dcr": float(final_solver["max_dcr"]),
            "raw_max_drift_pct": float(np.asarray(state["global_drift_pct"], dtype=np.float64)[0]),
            "raw_residual_drift_pct": float(np.asarray(state["global_residual_drift_pct"], dtype=np.float64)[0]),
            "raw_max_dcr": float(np.max(np.asarray(state["max_dcr"], dtype=np.float64))),
            "repaired_max_drift_pct": float(final_solver["max_drift_pct"]),
            "repaired_residual_drift_pct": float(final_solver["residual_drift_pct"]),
            "repaired_max_dcr": float(final_solver["max_dcr"]),
            "compliance_basis": "repaired_solver_validated_slice",
            "repair_actions_applied": list(repair_actions_applied),
            "repair_action_count": int(len(repair_actions_applied)),
            "accepted_stage1_count": int(len(result["accepted_stage1"])),
            "accepted_stage1_extra_count": int(len(result.get("accepted_stage1_extra", []))),
            "accepted_stage1_dcr_count": int(len(result.get("accepted_stage1_dcr", []))),
            "accepted_stage1_dcr_final_count": int(len(result.get("accepted_stage1_dcr_final", []))),
            "accepted_stage2_count": int(len(result["accepted_stage2"])),
            "solver_backend_static": str(final_solver["backend_static"]),
            "solver_backend_ndtha": str(final_solver["backend_ndtha"]),
            "solver_feasible_final": bool(final_solver["feasible"]),
            "target_max_dcr": float(max(float(cfg.dcr_limit) - float(args.target_dcr_margin), 0.10)),
            "objective_calibration_applied": bool(calibration_report),
            "objective_profile": str(args.objective_profile),
        },
        inputs={
            "dataset_npz": str(args.dataset_npz),
            "rebar_step": float(args.rebar_step),
            "thickness_step": float(args.thickness_step),
            "detailing_step": float(args.detailing_step),
            "min_rebar_ratio": float(args.min_rebar_ratio),
            "max_rebar_ratio": float(args.max_rebar_ratio),
            "max_iterations": int(args.max_iterations),
            "dcr_limit": float(args.dcr_limit),
            "drift_limit_pct": float(args.drift_limit_pct),
            "residual_drift_limit_pct": float(args.residual_drift_limit_pct),
            "ndtha_step_count": int(args.ndtha_step_count),
            "target_dcr_margin": float(args.target_dcr_margin),
            "per_group_escalation_cap": int(args.per_group_escalation_cap),
            "state_out": str(args.state_out),
            "objective_calibration_report": str(args.objective_calibration_report),
            "objective_profile": str(args.objective_profile),
        },
        artifacts={
            "state_out": str(args.state_out),
            "report_out": str(args.out),
        },
        contract_pass=bool(float(final_solver["violation_score"]) <= float(baseline_solver["violation_score"]) + 1.0e-9),
        reason_code="PASS" if float(final_solver["violation_score"]) <= float(baseline_solver["violation_score"]) + 1.0e-9 else "ERR_FAIL",
        reason="solver-validated optimization loop completed",
        head_blocks={
            "stage1_proposed_head": result["proposed_stage1"],
            "stage1_accepted_head": result["accepted_stage1"],
            "stage1_extra_accepted_head": result.get("accepted_stage1_extra", []),
            "stage1_dcr_accepted_head": result.get("accepted_stage1_dcr", []),
            "stage1_dcr_final_accepted_head": result.get("accepted_stage1_dcr_final", []),
            "stage2_proposed_head": result["proposed_stage2"],
            "stage2_accepted_head": result["accepted_stage2"],
        },
    )
    out = Path(args.out)
    print(f"Wrote design optimization solver loop report: {out}")


if __name__ == "__main__":
    main()
