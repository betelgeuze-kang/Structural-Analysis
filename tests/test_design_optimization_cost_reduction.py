from __future__ import annotations

import numpy as np

from implementation.phase1.design_optimization.candidate_generation import (
    _constructability_hard_gate,
    build_action_block_report,
)
from implementation.phase1.design_optimization_env import ACTION_INDEX_V2, DesignOptimizationConfig, hydrate_state_constructability_fields
from implementation.phase1.run_design_optimization_cost_reduction import (
    _apply_cost_reduction_viewer_enrichment,
    _apply_cost_reduction_reverse_sync,
    _build_cost_reduction_reverse_sync_rows,
    _build_cost_reduction_viewer_enrichment,
    _budget_stage_b_defaults,
    _overlay_action_masks_from_dataset,
    _aggregate_no_cost_gain_explain_rows,
    _refine_action_masks_for_current_state,
    run_cost_reduction_only,
)
from implementation.phase1.design_optimization.reporting import rejected_reason


def _demo_state() -> dict[str, np.ndarray]:
    return {
        "group_ids": np.asarray(["G0", "G1"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.020, 0.016], dtype=np.float64),
        "max_dcr": np.asarray([0.24, 0.22], dtype=np.float64),
        "congestion": np.asarray([0.20, 0.15], dtype=np.float64),
        "lap_splice": np.asarray([0.10, 0.08], dtype=np.float64),
        "anchorage": np.asarray([0.25, 0.22], dtype=np.float64),
        "detailing": np.asarray([0.10, 0.05], dtype=np.float64),
        "detailing_quality": np.asarray([0.90, 0.88], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.30, 0.25], dtype=np.float64),
        "constructability_score": np.asarray([0.40, 0.35], dtype=np.float64),
        "group_cost_proxy": np.asarray([1200.0, 1100.0], dtype=np.float64),
        "member_type": np.asarray(["column", "beam"], dtype="<U16"),
        "zone_label": np.asarray(["transfer", "core"], dtype="<U16"),
        "semantic_group": np.asarray(["G-T1", ""], dtype="<U16"),
        "story_band": np.asarray([0, 1], dtype=np.int32),
        "repair_influence": np.asarray([1.35, 1.10], dtype=np.float64),
        "combination_match_score": np.asarray([0.92, 0.85], dtype=np.float64),
        "combination_risk": np.asarray([1.04, 1.08], dtype=np.float64),
        "thickness_scale": np.asarray([1.0, 1.0], dtype=np.float64),
        "robustness_margin": np.asarray([0.25, 0.25], dtype=np.float64),
        "global_drift_pct": np.asarray([1.2], dtype=np.float64),
        "global_residual_drift_pct": np.asarray([0.25], dtype=np.float64),
        "action_mask": np.asarray([[True, True], [True, True]], dtype=np.bool_),
    }


def test_cost_reduction_blocks_when_input_not_feasible(monkeypatch) -> None:
    def _solver(**kwargs):
        return {
            "violation_score": 100.0,
            "feasible": False,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 1.25,
            "max_drift_pct": 2.4,
            "residual_drift_pct": 0.8,
            "residual_top_displacement_m": 0.02,
            "static_top_displacement_m": 0.01,
            "static_converged": True,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": 2300.0,
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_cost_reduction._solver_stage_state",
        _solver,
    )
    result = run_cost_reduction_only(
        state=_demo_state(),
        cfg=DesignOptimizationConfig(max_iterations=4),
        ndtha_step_count=32,
        max_iterations=4,
    )
    assert result["blocked"] is True
    assert result["block_reason"] == "ERR_NOT_FEASIBLE"
    assert result["accepted"] == []


def test_budget_stage_b_defaults_match_budgeted_runner_intent() -> None:
    assert _budget_stage_b_defaults("low") == (8, 2)
    assert _budget_stage_b_defaults("medium") == (16, 4)
    assert _budget_stage_b_defaults("high") == (32, 8)


def test_cost_reduction_reduces_cost_when_input_feasible(monkeypatch) -> None:
    def _solver(*, state, cfg, step_count):
        rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
        total = float(np.sum(rebar))
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.95 + max(0.0, 0.032 - total) * 1.5,
            "max_drift_pct": 1.5,
            "residual_drift_pct": 0.2,
            "residual_top_displacement_m": 0.01,
            "static_top_displacement_m": 0.01,
            "static_converged": True,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_cost_reduction._solver_stage_state",
        _solver,
    )
    result = run_cost_reduction_only(
        state=_demo_state(),
        cfg=DesignOptimizationConfig(rebar_step=0.002, max_iterations=4),
        ndtha_step_count=32,
        max_iterations=4,
    )
    assert result["blocked"] is False
    assert len(result["accepted"]) >= 1
    assert float(result["final_solver"]["cost_proxy"]) < float(result["baseline_solver"]["cost_proxy"])
    assert bool(result["final_solver"]["feasible"]) is True


def test_cost_reduction_batch_select_accepts_multiple_candidates(monkeypatch) -> None:
    def _solver(*, state, cfg, step_count):
        rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
        total = float(np.sum(rebar))
        return {
            "violation_score": 0.0,
            "feasible": True,
            "collapsed": False,
            "converged_all_steps": True,
            "max_dcr": 0.90 + max(0.0, 0.034 - total) * 1.2,
            "max_drift_pct": 1.4,
            "residual_drift_pct": 0.18,
            "residual_top_displacement_m": 0.01,
            "static_top_displacement_m": 0.01,
            "static_converged": True,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
            "cost_proxy": float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64))),
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_cost_reduction._solver_stage_state",
        _solver,
    )
    result = run_cost_reduction_only(
        state=_demo_state(),
        cfg=DesignOptimizationConfig(rebar_step=0.002, max_iterations=1),
        ndtha_step_count=32,
        max_iterations=1,
    )
    assert result["blocked"] is False
    assert len(result["accepted"]) >= 2


def test_no_cost_gain_explain_rows_classify_zero_delta() -> None:
    cfg = DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.03)
    blocked_rows = [
        {
            "group_id": "G0",
            "story_band": 0,
            "zone_label": "transfer",
            "member_type": "column",
            "semantic_group": "G-T1",
            "priority": 12.0,
            "max_dcr": 0.94,
            "action_name": "rebar_down",
            "block_reason": "no_cost_gain",
            "detail": "trial_cost=2300.0;current_cost=2300.0;projected_cost_delta=0.000000",
        }
    ]
    rows = _aggregate_no_cost_gain_explain_rows(
        blocked_rows=blocked_rows,
        state=_demo_state(),
        cfg=cfg,
    )
    assert len(rows) == 1
    assert rows[0]["dominant_block_cause"] == "zero_projected_cost_delta"
    assert int(rows[0]["zero_projected_cost_delta_count"]) == 1


def test_overlay_action_masks_from_dataset_restores_constructability_fields(tmp_path) -> None:
    state = _demo_state()
    state["action_mask_extended"] = np.asarray([[True] * 6, [True] * 6], dtype=np.bool_)
    dataset_path = tmp_path / "design_optimization_dataset.npz"
    np.savez_compressed(
        dataset_path,
        unique_group_ids=np.asarray(["G0", "G1"], dtype="<U8"),
        group_index_per_member=np.asarray([0, 1], dtype=np.int32),
        rebar_ratio=np.asarray([0.020, 0.016], dtype=np.float64),
        max_dcr=np.asarray([0.92, 0.88], dtype=np.float64),
        congestion_index=np.asarray([0.28, 0.21], dtype=np.float64),
        lap_splice_ratio=np.asarray([0.10, 0.08], dtype=np.float64),
        anchorage_complexity=np.asarray([0.25, 0.22], dtype=np.float64),
        detailing_violation_ratio=np.asarray([0.30, 0.25], dtype=np.float64),
        detailing_quality=np.asarray([0.85, 0.82], dtype=np.float64),
        volume_m3=np.asarray([1.0, 1.0], dtype=np.float64),
        steel_mass_kg=np.asarray([1.0, 1.0], dtype=np.float64),
        thickness_scale=np.asarray([1.0, 1.0], dtype=np.float64),
        robustness_margin=np.asarray([0.2, 0.2], dtype=np.float64),
        multi_hazard_margin=np.asarray([0.2, 0.2], dtype=np.float64),
        member_types=np.asarray(["column", "beam"], dtype="<U16"),
        zone_labels=np.asarray(["transfer", "core"], dtype="<U16"),
        semantic_groups=np.asarray(["G-T1", ""], dtype="<U16"),
        section_names=np.asarray(["S1", "S2"], dtype="<U16"),
        section_signatures=np.asarray(["SG1", "SG2"], dtype="<U16"),
        member_governing_clause=np.asarray(["C1", "C2"], dtype="<U16"),
        story_band_index=np.asarray([0, 1], dtype=np.int32),
        group_parent_id=np.asarray(["G0", "G1"], dtype="<U8"),
        group_family_key=np.asarray(["G0", "G1"], dtype="<U8"),
        group_variance_score=np.asarray([0.1, 0.1], dtype=np.float64),
        group_merge_similarity_score=np.asarray([0.9, 0.9], dtype=np.float64),
        combination_match_score=np.asarray([0.92, 0.85], dtype=np.float64),
        combination_risk_scale=np.asarray([1.04, 1.08], dtype=np.float64),
        constructability_score=np.asarray([0.41, 0.27], dtype=np.float64),
        detailing_complexity_score=np.asarray([0.33, 0.26], dtype=np.float64),
        anchorage_complexity_score=np.asarray([0.22, 0.18], dtype=np.float64),
        splice_burden_score=np.asarray([0.12, 0.10], dtype=np.float64),
        overdesign_margin_score=np.asarray([0.18, 0.14], dtype=np.float64),
        material_reduction_potential_score=np.asarray([0.35, 0.31], dtype=np.float64),
        action_mask=np.asarray([[True, True], [True, True]], dtype=np.bool_),
        action_mask_extended=np.asarray([[True] * 6, [True] * 6], dtype=np.bool_),
    )
    overlaid = _overlay_action_masks_from_dataset(state=state, dataset_npz_path=dataset_path)
    assert np.allclose(np.asarray(overlaid["constructability_score"], dtype=np.float64), np.asarray([0.41, 0.27], dtype=np.float64))
    assert np.allclose(np.asarray(overlaid["detailing_complexity_score"], dtype=np.float64), np.asarray([0.33, 0.26], dtype=np.float64))


def test_hydrate_state_constructability_fields_backfills_missing_scores() -> None:
    reference_state = _demo_state()
    current_state = {k: np.asarray(v).copy() for k, v in reference_state.items()}
    current_state.pop("constructability_score", None)
    current_state.pop("detailing_complexity_score", None)
    current_state["thickness_scale"] = np.asarray([1.0, 0.96], dtype=np.float64)
    current_state["detailing_quality"] = np.asarray([0.90, 0.82], dtype=np.float64)
    hydrated = hydrate_state_constructability_fields(state=current_state, reference_state=reference_state)
    assert "constructability_score" in hydrated
    assert "detailing_complexity_score" in hydrated
    assert np.asarray(hydrated["constructability_score"], dtype=np.float64).shape[0] == 2
    assert np.asarray(hydrated["detailing_complexity_score"], dtype=np.float64).shape[0] == 2


def test_refine_action_masks_enables_connection_detailing_for_beam_core_targets() -> None:
    state = _demo_state()
    state["multi_hazard_margin"] = np.asarray([0.0, 0.0], dtype=np.float64)
    state["action_mask_extended"] = np.asarray([[False] * 6, [False] * 6], dtype=np.bool_)
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((2, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.03),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[1, ACTION_INDEX_V2["connection_detailing_down"]]) is True
    assert bool(mask_v2[1, ACTION_INDEX_V2["detailing_down"]]) is False


def test_refine_action_masks_rescues_connection_detailing_for_low_quality_high_complexity_targets() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["B0"], dtype="<U8"),
        "member_type": np.asarray(["beam"], dtype="<U16"),
        "zone_label": np.asarray(["core"], dtype="<U16"),
        "story_band": np.asarray([0], dtype=np.int32),
        "max_dcr": np.asarray([0.0], dtype=np.float64),
        "detailing_quality": np.asarray([0.55], dtype=np.float64),
        "detailing": np.asarray([1.0], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.674], dtype=np.float64),
        "constructability_score": np.asarray([0.4515], dtype=np.float64),
        "robustness_margin": np.asarray([0.84696], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.04),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[0, ACTION_INDEX_V2["connection_detailing_down"]]) is True
    assert bool(mask_v2[0, ACTION_INDEX_V2["detailing_down"]]) is False


def test_refine_action_masks_enables_perimeter_frame_for_perimeter_columns() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["C0"], dtype="<U8"),
        "member_type": np.asarray(["column"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter"], dtype="<U16"),
        "story_band": np.asarray([5], dtype=np.int32),
        "max_dcr": np.asarray([0.92], dtype=np.float64),
        "rebar_ratio": np.asarray([0.020], dtype=np.float64),
        "thickness_scale": np.asarray([1.0], dtype=np.float64),
        "detailing_quality": np.asarray([0.85], dtype=np.float64),
        "detailing": np.asarray([0.20], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.24], dtype=np.float64),
        "constructability_score": np.asarray([0.22], dtype=np.float64),
        "robustness_margin": np.asarray([0.12], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.03),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[0, ACTION_INDEX_V2["perimeter_frame_down"]]) is True


def test_refine_action_masks_rescues_perimeter_frame_for_low_quality_perimeter_columns() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["C0"], dtype="<U8"),
        "member_type": np.asarray(["column"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter"], dtype="<U16"),
        "story_band": np.asarray([5], dtype=np.int32),
        "max_dcr": np.asarray([-0.61], dtype=np.float64),
        "detailing_quality": np.asarray([0.55], dtype=np.float64),
        "detailing": np.asarray([1.0], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.6596], dtype=np.float64),
        "constructability_score": np.asarray([0.4779], dtype=np.float64),
        "robustness_margin": np.asarray([0.6881], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.04),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[0, ACTION_INDEX_V2["perimeter_frame_down"]]) is True


def test_refine_action_masks_rescues_rebar_down_for_core_column_under_high_detail_pressure() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["C0"], dtype="<U8"),
        "member_type": np.asarray(["column"], dtype="<U16"),
        "zone_label": np.asarray(["core"], dtype="<U16"),
        "story_band": np.asarray([5], dtype=np.int32),
        "max_dcr": np.asarray([-0.44], dtype=np.float64),
        "rebar_ratio": np.asarray([0.020], dtype=np.float64),
        "detailing_quality": np.asarray([0.56], dtype=np.float64),
        "detailing": np.asarray([1.0], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.67], dtype=np.float64),
        "constructability_score": np.asarray([0.45], dtype=np.float64),
        "robustness_margin": np.asarray([0.70], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.04),
    )
    mask = np.asarray(refined["action_mask"], dtype=np.bool_)
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask[0, 0]) is True
    assert bool(mask_v2[0, ACTION_INDEX_V2["rebar_down"]]) is True


def test_refine_action_masks_rescues_detailing_down_for_high_detail_pressure_wall() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["W0"], dtype="<U8"),
        "member_type": np.asarray(["wall"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter"], dtype="<U16"),
        "story_band": np.asarray([8], dtype=np.int32),
        "max_dcr": np.asarray([0.0], dtype=np.float64),
        "detailing_quality": np.asarray([0.55], dtype=np.float64),
        "detailing": np.asarray([1.0], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.66], dtype=np.float64),
        "constructability_score": np.asarray([0.45], dtype=np.float64),
        "robustness_margin": np.asarray([0.68], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.04),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[0, ACTION_INDEX_V2["detailing_down"]]) is True


def test_refine_action_masks_rescues_detailing_down_for_perimeter_wall_relief_band() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["W1"], dtype="<U8"),
        "member_type": np.asarray(["wall"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter"], dtype="<U16"),
        "story_band": np.asarray([8], dtype=np.int32),
        "max_dcr": np.asarray([0.0], dtype=np.float64),
        "detailing_quality": np.asarray([1.10], dtype=np.float64),
        "detailing": np.asarray([0.9831374017351755], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.6491451890758084], dtype=np.float64),
        "constructability_score": np.asarray([0.41467847248584905], dtype=np.float64),
        "robustness_margin": np.asarray([1.15], dtype=np.float64),
        "action_mask": np.asarray([[False, False]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[False] * 6], dtype=np.bool_),
    }
    action_names_v2 = np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48")
    state["action_mask_v2"] = np.zeros((1, len(action_names_v2)), dtype=np.bool_)
    state["action_names_v2"] = action_names_v2
    refined = _refine_action_masks_for_current_state(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.04),
    )
    mask_v2 = np.asarray(refined["action_mask_v2"], dtype=np.bool_)
    assert bool(mask_v2[0, ACTION_INDEX_V2["detailing_down"]]) is True


def test_block_report_uses_group_specific_actions_for_slab() -> None:
    state = {
        **_demo_state(),
        "group_ids": np.asarray(["S0"], dtype="<U8"),
        "member_type": np.asarray(["slab"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter"], dtype="<U16"),
        "story_band": np.asarray([3], dtype=np.int32),
        "semantic_group": np.asarray([""], dtype="<U16"),
        "rebar_ratio": np.asarray([0.018], dtype=np.float64),
        "max_dcr": np.asarray([0.12], dtype=np.float64),
        "congestion": np.asarray([0.18], dtype=np.float64),
        "lap_splice": np.asarray([0.06], dtype=np.float64),
        "anchorage": np.asarray([0.10], dtype=np.float64),
        "detailing": np.asarray([0.08], dtype=np.float64),
        "detailing_quality": np.asarray([0.84], dtype=np.float64),
        "detailing_complexity_score": np.asarray([0.22], dtype=np.float64),
        "constructability_score": np.asarray([0.30], dtype=np.float64),
        "group_cost_proxy": np.asarray([900.0], dtype=np.float64),
        "repair_influence": np.asarray([1.0], dtype=np.float64),
        "combination_match_score": np.asarray([0.92], dtype=np.float64),
        "combination_risk": np.asarray([1.01], dtype=np.float64),
        "thickness_scale": np.asarray([1.0], dtype=np.float64),
        "action_mask": np.asarray([[True, True]], dtype=np.bool_),
        "action_mask_extended": np.asarray([[True] * 6], dtype=np.bool_),
        "action_names_v2": np.asarray(list(ACTION_INDEX_V2.keys()), dtype="<U48"),
        "action_mask_v2": np.ones((1, len(ACTION_INDEX_V2)), dtype=np.bool_),
    }
    rows = build_action_block_report(
        state=state,
        cfg=DesignOptimizationConfig(rebar_step=0.002, thickness_step=0.01, detailing_step=0.03),
        ndtha_step_count=8,
        solver_stage_state_fn=lambda **kwargs: {
            "feasible": True,
            "collapsed": False,
            "max_dcr": 0.12,
            "cost_proxy": float(np.sum(np.asarray(kwargs["state"]["group_cost_proxy"], dtype=np.float64))),
            "max_drift_pct": 0.5,
            "residual_drift_pct": 0.05,
        },
        local_dcr_update_fn=lambda **kwargs: np.asarray(kwargs["state"]["max_dcr"], dtype=np.float64),
        max_groups=1,
    )
    action_names = {str(row.get("action_name", "")) for row in rows}
    assert "connection_detailing_down" not in action_names
    assert "slab_thickness_down" in action_names


def test_constructability_hard_gate_blocks_high_detailing_without_enough_improvement() -> None:
    blocked = _constructability_hard_gate(
        side_effects={
            "current_detailing_complexity": 0.63,
            "trial_detailing_complexity": 0.621,
            "current_congestion": 0.28,
            "trial_congestion": 0.27,
            "current_constructability": 0.35,
            "trial_constructability": 0.342,
            "current_anchorage_complexity": 0.24,
            "trial_anchorage_complexity": 0.24,
            "current_splice_burden": 0.14,
            "trial_splice_burden": 0.14,
        }
    )
    allowed = _constructability_hard_gate(
        side_effects={
            "current_detailing_complexity": 0.63,
            "trial_detailing_complexity": 0.54,
            "current_congestion": 0.28,
            "trial_congestion": 0.25,
            "current_constructability": 0.35,
            "trial_constructability": 0.27,
            "current_anchorage_complexity": 0.24,
            "trial_anchorage_complexity": 0.21,
            "current_splice_burden": 0.14,
            "trial_splice_burden": 0.12,
        }
    )

    assert blocked is not None
    assert str(blocked["reason"]) == "detailing_not_improved_enough"
    assert allowed is None


def test_rejected_reason_maps_constructability_hard_gate_prefixes() -> None:
    assert rejected_reason({"block_reason": "constructability_hard_gate:detailing_ratio_above_hard_limit"}) == "rejected_detailing_hard_gate"
    assert rejected_reason({"block_reason": "constructability_hard_gate:congestion_above_hard_limit"}) == "rejected_congestion_hard_gate"


def test_cost_reduction_viewer_enrichment_prefers_row_provenance_matches(tmp_path) -> None:
    dataset = {
        "unique_group_ids": np.asarray(["G0"], dtype="<U8"),
        "group_index_per_member": np.asarray([0, 0], dtype=np.int32),
        "member_ids": np.asarray(["27441", "27441"], dtype="<U16"),
        "member_types": np.asarray(["column", "column"], dtype="<U16"),
        "zone_labels": np.asarray(["perimeter", "perimeter"], dtype="<U16"),
        "semantic_groups": np.asarray(["", ""], dtype="<U16"),
        "story_band_index": np.asarray([5, 5], dtype=np.int32),
        "member_governing_clause": np.asarray(["KDS-MOMENT-Y-001", "KDS-MOMENT-Y-001"], dtype="<U32"),
        "member_governing_combo": np.asarray(["gLCB1", "gLCB1"], dtype="<U16"),
    }
    csv_path = tmp_path / "row_provenance.csv"
    csv_path.write_text(
        "\n".join(
            [
                "combination_name,row_index,viewer_row_ref,member_id,case_id,member_type,clause_label,baseline_focus_member_id,viewer_results_card,viewer_results_series_index,viewer_row_url,viewer_slice_url",
                "gLCB1,49,gLCB1::49::C-TST-003::C-TST-003,C-TST-003,C-TST-003,column,KDS-MOMENT-Y-001,27441,envelope,0,file:///viewer?row=49,file:///viewer?subset=1",
            ]
        ),
        encoding="utf-8",
    )

    enrichment = _build_cost_reduction_viewer_enrichment(
        dataset=dataset,
        row_provenance_report_path=None,
        row_provenance_csv_path=csv_path,
    )

    assert enrichment["G0"]["baseline_focus_member_id"] == "27441"
    assert enrichment["G0"]["member_id"] == "C-TST-003"
    assert enrichment["G0"]["case_id"] == "C-TST-003"
    assert enrichment["G0"]["combination_name"] == "gLCB1"
    assert enrichment["G0"]["viewer_row_ref"] == "gLCB1::49::C-TST-003::C-TST-003"
    assert enrichment["G0"]["recommended_results_card"] == "envelope"
    assert enrichment["G0"]["recommended_results_series_index"] == 0


def test_apply_cost_reduction_viewer_enrichment_fills_missing_fields_from_dataset() -> None:
    enrichment = {
        "G0": {
            "baseline_focus_member_id": "27441",
            "member_id": "27441",
            "case_id": "27441",
            "combination_name": "SVC_DRIFT",
            "recommended_results_card": "envelope",
            "recommended_results_card_label": "Envelope",
            "recommended_results_series_index": 1,
            "recommended_results_series_label": "Final drift",
            "recommended_results_reason_label": "governing drift/serviceability signal prefers final drift envelope",
            "viewer_row_ref": "",
            "viewer_row_url": "",
            "viewer_slice_url": "",
        }
    }

    rows = _apply_cost_reduction_viewer_enrichment(
        rows=[
            {
                "group_id": "G0",
                "action_name": "wall_thickness_down",
                "action_family": "wall_thickness",
                "member_type": "wall",
            }
        ],
        enrichment_by_group=enrichment,
    )

    assert rows[0]["baseline_focus_member_id"] == "27441"
    assert rows[0]["member_id"] == "27441"
    assert rows[0]["case_id"] == "27441"
    assert rows[0]["combination_name"] == "SVC_DRIFT"
    assert rows[0]["recommended_results_card"] == "envelope"
    assert rows[0]["recommended_results_series_index"] == 1
    assert rows[0]["recommended_results_series_label"] == "Final drift"


def test_apply_cost_reduction_viewer_enrichment_falls_back_to_group_index() -> None:
    enrichment = {
        "__group_index__:204": {
            "baseline_focus_member_id": "9001",
            "member_id": "9001",
            "case_id": "9001",
            "combination_name": "KDS_ULS_2",
            "recommended_results_card": "envelope",
            "recommended_results_card_label": "Envelope",
            "recommended_results_series_index": 0,
            "recommended_results_series_label": "Envelope drift",
            "recommended_results_reason_label": "default cost-reduction review opens the envelope response first",
            "viewer_row_ref": "",
            "viewer_row_url": "",
            "viewer_slice_url": "",
        }
    }

    rows = _apply_cost_reduction_viewer_enrichment(
        rows=[
            {
                "group_id": "state-only-group-id",
                "group_index": 204,
                "action_name": "rebar_down",
                "action_family": "rebar",
                "member_type": "wall",
            }
        ],
        enrichment_by_group=enrichment,
    )

    assert rows[0]["baseline_focus_member_id"] == "9001"
    assert rows[0]["combination_name"] == "KDS_ULS_2"


def test_build_cost_reduction_reverse_sync_rows_emits_results_explorer_urls() -> None:
    rows = _build_cost_reduction_reverse_sync_rows(
        rows=[
            {
                "group_id": "S04:perimeter:nogroup:beam:SB900X600",
                "group_index": 42,
                "story_band": 4,
                "zone_label": "perimeter",
                "member_type": "beam",
                "action_name": "beam_section_down",
                "baseline_focus_member_id": "B-4201",
                "member_id": "B-4201",
                "case_id": "B-4201",
                "combination_name": "KDS_ULS_2",
                "recommended_results_card": "envelope",
                "recommended_results_series_index": 1,
                "selected_in_final_loop": True,
                "selected_event_index": 2,
                "projected_cost_delta": 12.5,
                "max_dcr": 0.94,
            }
        ]
    )

    assert rows[0]["reverse_sync_row_ref"] == "cost_reduction::2::42::B-4201::beam_section_down"
    assert rows[0]["viewer_overlay_row_id"] == "overlay_row::2::42::B-4201::beam_section_down"
    assert "../visualization/structural_optimization_viewer.html?" in str(rows[0]["viewer_row_url"])
    assert "overlay_member_id=B-4201" in str(rows[0]["viewer_row_url"])
    assert "overlay_group_index=42" in str(rows[0]["viewer_row_url"])
    assert "overlay_row_id=overlay_row%3A%3A2%3A%3A42%3A%3AB-4201%3A%3Abeam_section_down" in str(rows[0]["viewer_row_url"])
    assert "results_card=envelope" in str(rows[0]["viewer_row_url"])
    assert "overlay_focus=group" in str(rows[0]["viewer_slice_url"])


def test_apply_cost_reduction_reverse_sync_fills_row_urls_by_group() -> None:
    reverse_sync_rows = _build_cost_reduction_reverse_sync_rows(
        rows=[
            {
                "group_id": "G0",
                "group_index": 7,
                "story_band": 3,
                "zone_label": "core",
                "member_type": "wall",
                "action_name": "wall_thickness_down",
                "baseline_focus_member_id": "9001",
                "member_id": "9001",
                "combination_name": "SVC_DRIFT",
                "recommended_results_card": "envelope",
                "recommended_results_series_index": 1,
                "selected_in_final_loop": True,
                "selected_event_index": 1,
                "projected_cost_delta": 4.5,
                "max_dcr": 0.88,
            }
        ]
    )
    rows = _apply_cost_reduction_reverse_sync(
        rows=[
            {
                "group_id": "G0",
                "group_index": 7,
                "action_name": "wall_thickness_down",
                "baseline_focus_member_id": "9001",
                "member_id": "9001",
            }
        ],
        reverse_sync_rows=reverse_sync_rows,
    )

    assert rows[0]["viewer_row_url"]
    assert rows[0]["viewer_slice_url"]
    assert rows[0]["viewer_overlay_row_id"] == "overlay_row::1::7::9001::wall_thickness_down"
    assert rows[0]["reverse_sync_row_ref"] == "cost_reduction::1::7::9001::wall_thickness_down"
