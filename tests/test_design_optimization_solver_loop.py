from __future__ import annotations

import numpy as np

from implementation.phase1.design_optimization_env import DesignOptimizationConfig
from implementation.phase1.run_design_optimization_solver_loop import run_solver_constrained_loop


def _demo_state() -> dict[str, np.ndarray]:
    return {
        "group_ids": np.asarray(["G0", "G1"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.012, 0.010], dtype=np.float64),
        "thickness_scale": np.asarray([1.00, 0.96], dtype=np.float64),
        "detailing_quality": np.asarray([0.88, 0.82], dtype=np.float64),
        "max_dcr": np.asarray([1.10, 0.98], dtype=np.float64),
        "congestion": np.asarray([0.20, 0.15], dtype=np.float64),
        "lap_splice": np.asarray([0.10, 0.08], dtype=np.float64),
        "anchorage": np.asarray([0.25, 0.22], dtype=np.float64),
        "detailing": np.asarray([0.30, 0.25], dtype=np.float64),
        "robustness_margin": np.asarray([0.22, 0.28], dtype=np.float64),
        "multi_hazard_margin": np.asarray([0.24, 0.26], dtype=np.float64),
        "wind_residual_drift_pct": np.asarray([0.03], dtype=np.float64),
        "ssi_residual_drift_pct": np.asarray([0.02], dtype=np.float64),
        "group_cost_proxy": np.asarray([1200.0, 1100.0], dtype=np.float64),
        "member_type": np.asarray(["column", "beam"], dtype="<U16"),
        "zone_label": np.asarray(["transfer", "core"], dtype="<U16"),
        "semantic_group": np.asarray(["G-T1", ""], dtype="<U16"),
        "story_band": np.asarray([0, 1], dtype=np.int32),
        "repair_influence": np.asarray([1.35, 1.10], dtype=np.float64),
        "combination_match_score": np.asarray([0.82, 0.65], dtype=np.float64),
        "combination_risk": np.asarray([1.18, 1.32], dtype=np.float64),
        "global_drift_pct": np.asarray([2.6], dtype=np.float64),
        "global_residual_drift_pct": np.asarray([0.9], dtype=np.float64),
        "action_mask": np.asarray([[True, True], [True, True]], dtype=np.bool_),
        "action_mask_extended": np.asarray(
            [
                [True, True, True, True, True, True],
                [True, True, True, True, True, True],
            ],
            dtype=np.bool_,
        ),
        "action_names": np.asarray(
            [
                "rebar_down",
                "rebar_up",
                "thickness_down",
                "thickness_up",
                "detailing_down",
                "detailing_up",
            ],
            dtype="<U32",
        ),
    }


def test_solver_loop_reduces_violation(monkeypatch) -> None:
    def _static_solver(**kwargs):
        k = np.asarray(kwargs["story_k_n_per_m"], dtype=np.float64)
        return {
            "backend": "rocm_torch_hip_mainloop",
            "converged": True,
            "top_displacement_m": float(4.0e5 / max(np.sum(k), 1.0)),
        }

    def _ndtha_solver(**kwargs):
        k = np.asarray(kwargs["story_k_n_per_m"], dtype=np.float64)
        stiffness = float(np.sum(k))
        drift = float(8.5e5 / max(stiffness, 1.0))
        residual = float(drift * 0.22)
        return {
            "backend": "rocm_torch_hip_mainloop",
            "collapsed": False,
            "converged_all_steps": True,
            "residual_drift_ratio_pct": residual,
            "residual_top_displacement_m": residual * 0.12,
            "response": {
                "drift_ratio_pct": [drift * 0.6, drift],
                "top_displacement_m": [0.01, 0.02],
            },
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_solver_loop.solve_nonlinear_frame",
        _static_solver,
    )
    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_solver_loop.solve_nonlinear_frame_ndtha",
        _ndtha_solver,
    )

    result = run_solver_constrained_loop(
        state=_demo_state(),
        cfg=DesignOptimizationConfig(max_iterations=6),
        ndtha_step_count=32,
    )
    assert float(result["final_solver"]["violation_score"]) <= float(result["baseline_solver"]["violation_score"])
    accepted_total = (
        len(result["accepted_stage1"])
        + len(result.get("accepted_stage1_extra", []))
        + len(result.get("accepted_stage1_dcr", []))
        + len(result.get("accepted_stage1_dcr_final", []))
    )
    assert accepted_total >= 1
    action_names = {
        entry.get("action_name")
        for bucket in (
            result["accepted_stage1"],
            result.get("accepted_stage1_extra", []),
            result.get("accepted_stage1_dcr", []),
            result.get("accepted_stage1_dcr_final", []),
        )
        for entry in bucket
    }
    assert action_names
    assert action_names.issubset({"rebar_up", "thickness_up", "detailing_up"})
    assert "accepted_stage1_extra" in result
