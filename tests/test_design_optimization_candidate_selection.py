from __future__ import annotations

import numpy as np

from implementation.phase1.design_optimization.candidate_selection import (
    _augment_prefilter_with_action_families,
    _family_batched_preview_rows,
    _ordered_reserved_family_previews,
    run_cost_reduction_selection,
)
from implementation.phase1.design_optimization_env import ACTION_INDEX_V2, DesignOptimizationConfig


def _demo_state() -> dict[str, np.ndarray]:
    return {
        "group_ids": np.asarray(["S0", "B0", "W0", "C0"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.020, 0.018, 0.022, 0.016], dtype=np.float64),
        "group_cost_proxy": np.asarray([1200.0, 1100.0, 1000.0, 900.0], dtype=np.float64),
        "repair_influence": np.asarray([1.05, 1.15, 1.18, 1.10], dtype=np.float64),
        "detailing": np.asarray([0.25, 0.32, 0.30, 0.36], dtype=np.float64),
        "combination_risk": np.asarray([1.02, 1.05, 1.06, 1.04], dtype=np.float64),
        "combination_match_score": np.asarray([0.96, 0.92, 0.93, 0.90], dtype=np.float64),
        "member_type": np.asarray(["slab", "beam", "wall", "connection"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "core", "core", "transfer"], dtype="<U16"),
        "story_band": np.asarray([1, 2, 2, 3], dtype=np.int32),
        "semantic_group": np.asarray(["", "beam-core", "wall-core", "conn-x"], dtype="<U16"),
    }


def test_candidate_selection_prefers_diverse_constructability_positive_families() -> None:
    state = _demo_state()

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.93,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    action_map = {
        0: ["rebar_down"],
        1: ["beam_section_down"],
        2: ["wall_thickness_down"],
        3: ["connection_detailing_down"],
    }

    def _actions_for_group(*, state, group_index):
        return list(action_map[int(group_index)])

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        meta = candidate_defs.get((int(group_index), str(action_name)))
        if meta is None:
            return None
        return {
            "group_index": int(group_index),
            "group_id": str(np.asarray(state["group_ids"])[int(group_index)]),
            "member_type": str(np.asarray(state["member_type"])[int(group_index)]),
            "zone_label": str(np.asarray(state["zone_label"])[int(group_index)]),
            "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[int(group_index)]),
            "action_name": str(action_name),
            "action_family": str(meta["family"]),
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[int(group_index)]),
            "projected_cost_delta": float(meta["delta"]),
            "current_congestion": 0.20,
            "trial_congestion": float(0.20 - meta["congestion"]),
            "current_detailing_complexity": 0.30,
            "trial_detailing_complexity": float(0.30 - meta["detailing"]),
            "current_constructability": 0.35,
            "trial_constructability": float(0.35 - meta["constructability"]),
            "constructability_gain": float(meta["constructability"]),
            "congestion_gain": float(meta["congestion"]),
            "detailing_gain": float(meta["detailing"]),
        }

    candidate_defs = {
        (0, "rebar_down"): {"family": "rebar", "delta": 18.0, "constructability": 0.0, "congestion": 0.01, "detailing": 0.005},
        (1, "beam_section_down"): {"family": "beam_section", "delta": 14.0, "constructability": 0.060, "congestion": 0.02, "detailing": 0.02},
        (2, "wall_thickness_down"): {"family": "wall_thickness", "delta": 13.0, "constructability": 0.055, "congestion": 0.02, "detailing": 0.018},
        (3, "connection_detailing_down"): {"family": "connection_detailing", "delta": 12.0, "constructability": 0.075, "congestion": 0.01, "detailing": 0.05},
    }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        meta = candidate_defs.get((int(group_index), str(action_name)))
        if meta is None:
            return None
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][int(group_index)] -= float(meta["delta"])
        trial_solver = {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.93,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64))),
        }
        return {
            "group_index": int(group_index),
            "group_id": str(np.asarray(state["group_ids"])[int(group_index)]),
            "member_type": str(np.asarray(state["member_type"])[int(group_index)]),
            "zone_label": str(np.asarray(state["zone_label"])[int(group_index)]),
            "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[int(group_index)]),
            "action_name": str(action_name),
            "action_family": str(meta["family"]),
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[int(group_index)]),
            "projected_cost_delta": float(meta["delta"]),
            "current_congestion": 0.20,
            "trial_congestion": float(0.20 - meta["congestion"]),
            "current_detailing_complexity": 0.30,
            "trial_detailing_complexity": float(0.30 - meta["detailing"]),
            "current_constructability": 0.35,
            "trial_constructability": float(0.35 - meta["constructability"]),
            "constructability_gain": float(meta["constructability"]),
            "congestion_gain": float(meta["congestion"]),
            "detailing_gain": float(meta["detailing"]),
            "trial_state": trial_state,
            "trial_solver": trial_solver,
        }

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=3,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    accepted_families = [str(row["action_family"]) for row in result["accepted"]]
    assert result["blocked"] is False
    assert len(accepted_families) == 3
    assert "rebar" not in accepted_families
    assert set(accepted_families) == {"beam_section", "wall_thickness", "connection_detailing"}


def test_candidate_selection_penalizes_high_dcr_connection_detailing_previews() -> None:
    state = {
        "group_ids": np.asarray(["B_hi", "B_lo"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.018, 0.018], dtype=np.float64),
        "group_cost_proxy": np.asarray([1200.0, 1190.0], dtype=np.float64),
        "repair_influence": np.asarray([1.0, 1.0], dtype=np.float64),
        "detailing": np.asarray([0.35, 0.35], dtype=np.float64),
        "combination_risk": np.asarray([1.02, 1.02], dtype=np.float64),
        "combination_match_score": np.asarray([0.94, 0.94], dtype=np.float64),
        "member_type": np.asarray(["beam", "beam"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "perimeter"], dtype="<U16"),
        "story_band": np.asarray([4, 4], dtype=np.int32),
        "semantic_group": np.asarray(["", ""], dtype="<U4"),
        "max_dcr": np.asarray([0.88, 0.18], dtype=np.float64),
    }

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": float(np.max(np.asarray(state.get("max_dcr", np.asarray([0.9])), dtype=np.float64))),
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    def _actions_for_group(*, state, group_index):
        return ["connection_detailing_down"]

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        return {
            "group_index": int(group_index),
            "group_id": str(np.asarray(state["group_ids"])[int(group_index)]),
            "member_type": "beam",
            "zone_label": "perimeter",
            "story_band": 4,
            "action_name": str(action_name),
            "action_family": "connection_detailing",
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[int(group_index)]),
            "projected_cost_delta": 2.3,
            "current_congestion": 0.25,
            "trial_congestion": 0.244,
            "current_detailing_complexity": 0.33,
            "trial_detailing_complexity": 0.27,
            "current_constructability": 0.28,
            "trial_constructability": 0.208,
            "constructability_gain": 0.072,
            "congestion_gain": 0.006,
            "detailing_gain": 0.060,
        }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        preview = _preview_candidate(
            state=state,
            current_solver=current_solver,
            cfg=cfg,
            group_index=group_index,
            action_name=action_name,
        )
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][int(group_index)] -= float(preview["projected_cost_delta"])
        trial_solver = dict(_solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count))
        trial_solver["cost_proxy"] = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
        return {**preview, "trial_state": trial_state, "trial_solver": trial_solver}

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=1,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    assert result["blocked"] is False
    assert len(result["accepted"]) == 1
    assert result["accepted"][0]["group_id"] == "B_lo"


def test_prefilter_augments_connection_detailing_with_low_dcr_headroom_first() -> None:
    n = 4
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    mask = np.zeros((n, len(action_names_v2)), dtype=np.bool_)
    mask[:, ACTION_INDEX_V2["connection_detailing_down"]] = True
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "action_names_v2": action_names_v2,
        "action_mask_v2": mask,
        "max_dcr": np.asarray([0.88, 0.84, 0.22, 0.18], dtype=np.float64),
    }
    ranked = np.asarray([0, 1, 2, 3], dtype=np.int32)
    selected = [0, 1]
    augmented = _augment_prefilter_with_action_families(
        state=state,
        ranked=ranked,
        selected=selected,
        preferred_actions={"connection_detailing": "connection_detailing_down"},
        minimums={"connection_detailing": 3},
        max_groups=3,
    )
    assert augmented == [0, 1, 3]


def test_prefilter_augments_connection_detailing_with_zone_diversity() -> None:
    n = 5
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    mask = np.zeros((n, len(action_names_v2)), dtype=np.bool_)
    mask[:, ACTION_INDEX_V2["connection_detailing_down"]] = True
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "action_names_v2": action_names_v2,
        "action_mask_v2": mask,
        "max_dcr": np.asarray([0.10, 0.12, 0.14, 0.26, 0.28], dtype=np.float64),
        "zone_label": np.asarray(["perimeter", "perimeter", "perimeter", "core", "core"], dtype="<U16"),
    }
    ranked = np.asarray([0, 1, 2, 3, 4], dtype=np.int32)
    augmented = _augment_prefilter_with_action_families(
        state=state,
        ranked=ranked,
        selected=[0, 1],
        preferred_actions={"connection_detailing": "connection_detailing_down"},
        minimums={"connection_detailing": 3},
        max_groups=3,
    )
    assert augmented == [0, 1, 3]


def test_prefilter_augments_connection_detailing_prefers_low_quality_high_complexity_pressure() -> None:
    n = 4
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    mask = np.zeros((n, len(action_names_v2)), dtype=np.bool_)
    mask[:, ACTION_INDEX_V2["connection_detailing_down"]] = True
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "action_names_v2": action_names_v2,
        "action_mask_v2": mask,
        "max_dcr": np.asarray([0.18, 0.16, 0.14, 0.12], dtype=np.float64),
        "zone_label": np.asarray(["core", "core", "core", "core"], dtype="<U16"),
        "detailing_quality": np.asarray([0.90, 0.55, 0.82, 0.88], dtype=np.float64),
        "detailing": np.asarray([0.30, 1.0, 0.40, 0.35], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.25, 0.67, 0.32, 0.28], dtype=np.float64),
        "constructability_score": np.asarray([0.20, 0.45, 0.24, 0.22], dtype=np.float64),
    }
    ranked = np.asarray([0, 1, 2, 3], dtype=np.int32)
    augmented = _augment_prefilter_with_action_families(
        state=state,
        ranked=ranked,
        selected=[0],
        preferred_actions={"connection_detailing": "connection_detailing_down"},
        minimums={"connection_detailing": 2},
        max_groups=2,
    )
    assert augmented == [0, 1]


def test_prefilter_augments_connection_detailing_replaces_weaker_family_enabled_groups() -> None:
    n = 4
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    mask = np.zeros((n, len(action_names_v2)), dtype=np.bool_)
    mask[:, ACTION_INDEX_V2["connection_detailing_down"]] = True
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "action_names_v2": action_names_v2,
        "action_mask_v2": mask,
        "max_dcr": np.asarray([0.18, 0.17, 0.16, 0.15], dtype=np.float64),
        "zone_label": np.asarray(["core", "core", "core", "core"], dtype="<U16"),
        "detailing_quality": np.asarray([0.88, 0.87, 0.55, 0.56], dtype=np.float64),
        "detailing": np.asarray([0.30, 0.32, 1.0, 0.98], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.22, 0.24, 0.67, 0.65], dtype=np.float64),
        "constructability_score": np.asarray([0.18, 0.19, 0.45, 0.43], dtype=np.float64),
    }
    ranked = np.asarray([0, 1, 2, 3], dtype=np.int32)
    augmented = _augment_prefilter_with_action_families(
        state=state,
        ranked=ranked,
        selected=[0, 1],
        preferred_actions={"connection_detailing": "connection_detailing_down"},
        minimums={"connection_detailing": 2},
        max_groups=2,
    )
    assert augmented == [2, 3]


def test_candidate_selection_prefers_perimeter_frame_before_connection_when_later_batch_state_blocks_it() -> None:
    state = {
        "group_ids": np.asarray(["B0", "C0"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.018, 0.016], dtype=np.float64),
        "group_cost_proxy": np.asarray([1100.0, 900.0], dtype=np.float64),
        "repair_influence": np.asarray([1.0, 1.0], dtype=np.float64),
        "detailing": np.asarray([0.30, 0.34], dtype=np.float64),
        "combination_risk": np.asarray([1.02, 1.02], dtype=np.float64),
        "combination_match_score": np.asarray([0.94, 0.94], dtype=np.float64),
        "member_type": np.asarray(["beam", "column"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "perimeter"], dtype="<U16"),
        "story_band": np.asarray([4, 5], dtype=np.int32),
        "semantic_group": np.asarray(["", "2"], dtype="<U4"),
        "max_dcr": np.asarray([0.10, 0.22], dtype=np.float64),
    }

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.95,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    def _actions_for_group(*, state, group_index):
        return ["connection_detailing_down"] if int(group_index) == 0 else ["perimeter_frame_down"]

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        if str(action_name) == "connection_detailing_down":
            return {
                "group_index": 0,
                "group_id": "B0",
                "member_type": "beam",
                "zone_label": "perimeter",
                "story_band": 4,
                "action_name": "connection_detailing_down",
                "action_family": "connection_detailing",
                "priority": 1100.0,
                "projected_cost_delta": 3.0,
                "current_congestion": 0.25,
                "trial_congestion": 0.244,
                "current_detailing_complexity": 0.33,
                "trial_detailing_complexity": 0.27,
                "current_constructability": 0.28,
                "trial_constructability": 0.208,
                "constructability_gain": 0.072,
                "congestion_gain": 0.006,
                "detailing_gain": 0.060,
            }
        return {
            "group_index": 1,
            "group_id": "C0",
            "member_type": "column",
            "zone_label": "perimeter",
            "story_band": 5,
            "action_name": "perimeter_frame_down",
            "action_family": "perimeter_frame",
            "priority": 900.0,
            "projected_cost_delta": 48.0,
            "current_congestion": 0.35,
            "trial_congestion": 0.34,
            "current_detailing_complexity": 0.66,
            "trial_detailing_complexity": 0.648,
            "current_constructability": 0.478,
            "trial_constructability": 0.45,
            "constructability_gain": 0.028,
            "congestion_gain": 0.01,
            "detailing_gain": 0.012,
        }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        preview = _preview_candidate(
            state=state,
            current_solver=current_solver,
            cfg=cfg,
            group_index=group_index,
            action_name=action_name,
        )
        if preview is None:
            return None
        # Perimeter frame is only feasible before another family has been accepted in the same batch.
        if str(action_name) == "perimeter_frame_down" and float(current_solver["cost_proxy"]) < 2000.0:
            return None
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][int(group_index)] -= float(preview["projected_cost_delta"])
        trial_solver = dict(_solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count))
        trial_solver["cost_proxy"] = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
        return {**preview, "trial_state": trial_state, "trial_solver": trial_solver}

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=8,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    accepted_families = [str(row["action_family"]) for row in result["accepted"]]
    assert "perimeter_frame" in accepted_families


def test_candidate_selection_reserved_family_slot_finds_connection_survivor_outside_preview_eval_rows() -> None:
    group_ids = np.asarray(["B0", "B1", "B2", "B3", "B4", "B5", "C0"], dtype="<U8")
    initial_cost = np.asarray([1100.0, 1090.0, 1080.0, 1070.0, 1060.0, 1050.0, 900.0], dtype=np.float64)
    state = {
        "group_ids": group_ids,
        "rebar_ratio": np.full(group_ids.size, 0.018, dtype=np.float64),
        "group_cost_proxy": initial_cost.copy(),
        "repair_influence": np.full(group_ids.size, 1.0, dtype=np.float64),
        "detailing": np.full(group_ids.size, 0.32, dtype=np.float64),
        "combination_risk": np.full(group_ids.size, 1.02, dtype=np.float64),
        "combination_match_score": np.full(group_ids.size, 0.94, dtype=np.float64),
        "member_type": np.asarray(["beam", "beam", "beam", "beam", "beam", "beam", "column"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "perimeter", "perimeter", "perimeter", "perimeter", "core", "perimeter"], dtype="<U16"),
        "story_band": np.asarray([4, 4, 4, 4, 4, 9, 5], dtype=np.int32),
        "semantic_group": np.asarray(["", "", "", "", "", "", "2"], dtype="<U4"),
        "max_dcr": np.asarray([0.79, 0.77, 0.75, 0.73, 0.71, 0.22, 0.18], dtype=np.float64),
    }
    baseline_cost_proxy = float(np.sum(initial_cost))

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.95,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    def _actions_for_group(*, state, group_index):
        if int(group_index) == 6:
            return ["perimeter_frame_down"]
        return ["connection_detailing_down"]

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        gi = int(group_index)
        if str(action_name) == "perimeter_frame_down":
            return {
                "group_index": gi,
                "group_id": str(group_ids[gi]),
                "member_type": "column",
                "zone_label": "perimeter",
                "story_band": 5,
                "action_name": "perimeter_frame_down",
                "action_family": "perimeter_frame",
                "priority": 900.0,
                "projected_cost_delta": 48.0,
                "current_congestion": 0.35,
                "trial_congestion": 0.34,
                "current_detailing_complexity": 0.66,
                "trial_detailing_complexity": 0.648,
                "current_constructability": 0.478,
                "trial_constructability": 0.45,
                "constructability_gain": 0.028,
                "congestion_gain": 0.01,
                "detailing_gain": 0.012,
            }
        delta = 9.0 - float(gi)
        constructability_gain = 0.072
        congestion_gain = 0.006
        detailing_gain = 0.060
        if gi == 5:
            delta = 4.1
            constructability_gain = 0.014
            congestion_gain = 0.002
            detailing_gain = 0.010
        return {
            "group_index": gi,
            "group_id": str(group_ids[gi]),
            "member_type": "beam",
            "zone_label": str(np.asarray(state["zone_label"])[gi]),
            "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[gi]),
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[gi]),
            "projected_cost_delta": delta,
            "current_congestion": 0.25,
            "trial_congestion": 0.244,
            "current_detailing_complexity": 0.33,
            "trial_detailing_complexity": 0.27,
            "current_constructability": 0.28,
            "trial_constructability": 0.208,
            "constructability_gain": constructability_gain,
            "congestion_gain": congestion_gain,
            "detailing_gain": detailing_gain,
        }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        gi = int(group_index)
        preview = _preview_candidate(
            state=state,
            current_solver=current_solver,
            cfg=cfg,
            group_index=gi,
            action_name=action_name,
        )
        if preview is None:
            return None
        current_cost_proxy = float(current_solver["cost_proxy"])
        if str(action_name) == "perimeter_frame_down" and current_cost_proxy < baseline_cost_proxy:
            return None
        if str(action_name) == "connection_detailing_down" and current_cost_proxy < baseline_cost_proxy and gi != 5:
            return None
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][gi] -= float(preview["projected_cost_delta"])
        trial_solver = dict(_solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count))
        trial_solver["cost_proxy"] = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
        return {**preview, "trial_state": trial_state, "trial_solver": trial_solver}

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=6,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    accepted_families = [str(row["action_family"]) for row in result["accepted"]]
    accepted_groups = [str(row["group_id"]) for row in result["accepted"]]
    assert "perimeter_frame" in accepted_families
    assert "connection_detailing" in accepted_families
    assert "B5" in accepted_groups


def test_family_batched_preview_prefers_lower_dcr_connection_candidates_with_same_score() -> None:
    preview_rows = [
        {
            "group_id": "G_hi",
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "selection_score": 10.0,
            "projected_cost_delta": 3.0,
            "local_max_dcr": 0.88,
            "story_band": 4,
            "zone_label": "perimeter",
        },
        {
            "group_id": "G_lo",
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "selection_score": 10.0,
            "projected_cost_delta": 3.0,
            "local_max_dcr": 0.62,
            "story_band": 9,
            "zone_label": "core",
        },
    ]
    rows = _family_batched_preview_rows(
        preview_rows=preview_rows,
        total_budget=2,
        family_cap=2,
        constructability_families={"connection_detailing"},
        min_constructability_gain=0.0,
        constructability_quota=1,
        preferred_family_minimums={"connection_detailing": 1},
    )
    assert rows[0]["group_id"] == "G_lo"


def test_reserved_connection_previews_round_robin_zone_buckets() -> None:
    preview_rows = [
        {
            "group_id": "P1",
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "selection_score": 20.0,
            "projected_cost_delta": 3.0,
            "local_max_dcr": 0.10,
            "story_band": 4,
            "zone_label": "perimeter",
        },
        {
            "group_id": "P2",
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "selection_score": 19.0,
            "projected_cost_delta": 3.0,
            "local_max_dcr": 0.12,
            "story_band": 4,
            "zone_label": "perimeter",
        },
        {
            "group_id": "C1",
            "action_name": "connection_detailing_down",
            "action_family": "connection_detailing",
            "selection_score": 15.0,
            "projected_cost_delta": 3.0,
            "local_max_dcr": 0.24,
            "story_band": 9,
            "zone_label": "core",
        },
    ]
    rows = _ordered_reserved_family_previews("connection_detailing", preview_rows)
    assert [row["group_id"] for row in rows[:3]] == ["P1", "C1", "P2"]


def test_candidate_selection_uses_preview_budget_to_limit_expensive_evaluations() -> None:
    n = 10
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "rebar_ratio": np.full(n, 0.02, dtype=np.float64),
        "group_cost_proxy": np.linspace(1500.0, 500.0, n, dtype=np.float64),
        "repair_influence": np.full(n, 1.1, dtype=np.float64),
        "detailing": np.full(n, 0.3, dtype=np.float64),
        "combination_risk": np.full(n, 1.05, dtype=np.float64),
        "combination_match_score": np.full(n, 0.92, dtype=np.float64),
        "member_type": np.asarray(["slab", "beam", "wall", "connection", "beam", "wall", "slab", "connection", "beam", "wall"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "core", "core", "transfer", "core", "core", "perimeter", "transfer", "core", "core"], dtype="<U16"),
        "story_band": np.arange(n, dtype=np.int32),
        "semantic_group": np.asarray([""] * n, dtype="<U4"),
    }
    eval_counter = {"count": 0}

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.93,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    def _actions_for_group(*, state, group_index):
        return ["rebar_down", "beam_section_down", "wall_thickness_down"]

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        family = {
            "rebar_down": "rebar",
            "beam_section_down": "beam_section",
            "wall_thickness_down": "wall_thickness",
        }[str(action_name)]
        return {
            "group_index": int(group_index),
            "group_id": str(np.asarray(state["group_ids"])[int(group_index)]),
            "member_type": str(np.asarray(state["member_type"])[int(group_index)]),
            "zone_label": str(np.asarray(state["zone_label"])[int(group_index)]),
            "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[int(group_index)]),
            "action_name": str(action_name),
            "action_family": family,
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[int(group_index)]),
            "projected_cost_delta": 15.0 if family != "rebar" else 13.0,
            "current_congestion": 0.2,
            "trial_congestion": 0.18,
            "current_detailing_complexity": 0.3,
            "trial_detailing_complexity": 0.26,
            "current_constructability": 0.35,
            "trial_constructability": 0.29 if family != "rebar" else 0.34,
            "constructability_gain": 0.06 if family != "rebar" else 0.01,
            "congestion_gain": 0.02,
            "detailing_gain": 0.03,
        }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        eval_counter["count"] += 1
        preview = _preview_candidate(
            state=state,
            current_solver=current_solver,
            cfg=cfg,
            group_index=group_index,
            action_name=action_name,
        )
        if preview is None:
            return None
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][int(group_index)] -= float(preview["projected_cost_delta"])
        trial_solver = dict(_solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count))
        trial_solver["cost_proxy"] = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
        return {
            **preview,
            "trial_state": trial_state,
            "trial_solver": trial_solver,
        }

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=3,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    assert result["blocked"] is False
    assert eval_counter["count"] <= 12


def test_candidate_selection_prefilter_augments_low_priority_connection_detailing_groups() -> None:
    n = 8
    action_count = len(ACTION_INDEX_V2)
    state = {
        "group_ids": np.asarray([f"G{i}" for i in range(n)], dtype="<U8"),
        "rebar_ratio": np.full(n, 0.02, dtype=np.float64),
        "group_cost_proxy": np.asarray([2000.0, 1800.0, 1600.0, 1400.0, 1200.0, 1000.0, 800.0, 100.0], dtype=np.float64),
        "repair_influence": np.full(n, 1.05, dtype=np.float64),
        "detailing": np.full(n, 0.30, dtype=np.float64),
        "combination_risk": np.full(n, 1.02, dtype=np.float64),
        "combination_match_score": np.full(n, 0.95, dtype=np.float64),
        "member_type": np.asarray(["beam", "beam", "wall", "wall", "slab", "slab", "beam", "beam"], dtype="<U16"),
        "zone_label": np.asarray(["intermediate", "intermediate", "core", "core", "perimeter", "perimeter", "intermediate", "perimeter"], dtype="<U16"),
        "story_band": np.arange(n, dtype=np.int32),
        "semantic_group": np.asarray([""] * n, dtype="<U4"),
        "action_mask_v2": np.zeros((n, action_count), dtype=np.bool_),
    }
    state["action_mask_v2"][:3, ACTION_INDEX_V2["beam_section_down"]] = True
    state["action_mask_v2"][2:4, ACTION_INDEX_V2["wall_thickness_down"]] = True
    state["action_mask_v2"][4:6, ACTION_INDEX_V2["slab_thickness_down"]] = True
    state["action_mask_v2"][7, ACTION_INDEX_V2["connection_detailing_down"]] = True

    def _refine_masks(*, state, cfg):
        return {k: np.asarray(v).copy() for k, v in state.items()}

    def _solver_stage_state(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.93,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    def _actions_for_group(*, state, group_index):
        if int(group_index) == 7:
            return ["connection_detailing_down"]
        return ["beam_section_down"]

    def _preview_candidate(*, state, current_solver, cfg, group_index, action_name):
        if str(action_name) == "connection_detailing_down" and int(group_index) == 7:
            family = "connection_detailing"
            delta = 9.0
            constructability = 0.08
            detailing = 0.06
        elif str(action_name) == "beam_section_down":
            family = "beam_section"
            delta = 12.0
            constructability = 0.05
            detailing = 0.02
        else:
            return None
        return {
            "group_index": int(group_index),
            "group_id": str(np.asarray(state["group_ids"])[int(group_index)]),
            "member_type": str(np.asarray(state["member_type"])[int(group_index)]),
            "zone_label": str(np.asarray(state["zone_label"])[int(group_index)]),
            "story_band": int(np.asarray(state["story_band"], dtype=np.int32)[int(group_index)]),
            "action_name": str(action_name),
            "action_family": family,
            "priority": float(np.asarray(state["group_cost_proxy"], dtype=np.float64)[int(group_index)]),
            "projected_cost_delta": float(delta),
            "current_congestion": 0.20,
            "trial_congestion": 0.18,
            "current_detailing_complexity": 0.30,
            "trial_detailing_complexity": float(0.30 - detailing),
            "current_constructability": 0.35,
            "trial_constructability": float(0.35 - constructability),
            "constructability_gain": float(constructability),
            "congestion_gain": 0.02,
            "detailing_gain": float(detailing),
        }

    def _evaluate_candidate(*, state, current_solver, cfg, ndtha_step_count, group_index, action_name):
        preview = _preview_candidate(
            state=state,
            current_solver=current_solver,
            cfg=cfg,
            group_index=group_index,
            action_name=action_name,
        )
        if preview is None:
            return None
        trial_state = {k: np.asarray(v).copy() for k, v in state.items()}
        trial_state["group_cost_proxy"] = np.asarray(state["group_cost_proxy"], dtype=np.float64).copy()
        trial_state["group_cost_proxy"][int(group_index)] -= float(preview["projected_cost_delta"])
        trial_solver = dict(_solver_stage_state(state=trial_state, cfg=cfg, step_count=ndtha_step_count))
        trial_solver["cost_proxy"] = float(np.sum(np.asarray(trial_state["group_cost_proxy"], dtype=np.float64)))
        return {**preview, "trial_state": trial_state, "trial_solver": trial_solver}

    result = run_cost_reduction_selection(
        state=state,
        cfg=DesignOptimizationConfig(max_iterations=1, cost_weight=1.0, constructability_weight=1.3, congestion_weight=1.2, detailing_complexity_weight=1.3),
        ndtha_step_count=24,
        max_iterations=1,
        batch_limit=3,
        solver_stage_state_fn=_solver_stage_state,
        refine_masks_fn=_refine_masks,
        evaluate_candidate_fn=_evaluate_candidate,
        preview_candidate_fn=_preview_candidate,
        cost_down_actions_for_group_fn=_actions_for_group,
    )

    assert result["preview_supply_family_counts"].get("connection_detailing", 0) >= 1
