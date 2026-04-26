from __future__ import annotations

from implementation.phase1.design_objective_calibration import (
    apply_objective_calibration,
    calibrate_objective_weights,
)
from implementation.phase1.design_optimization_env import DesignOptimizationConfig


def test_objective_calibration_applies_scales() -> None:
    base_cfg = DesignOptimizationConfig()
    report = calibrate_objective_weights(
        dataset_report={
            "summary": {
                "residual_drift_pct_max_abs": 1.2,
            }
        },
        change_summary={
            "change_summary_rows": [
                {
                    "zone_label": "perimeter",
                    "member_type": "slab",
                    "changed_group_count": 2,
                    "semantic_group_count": 0,
                    "max_dcr_after_max": 0.12,
                },
                {
                    "zone_label": "core",
                    "member_type": "wall",
                    "changed_group_count": 1,
                    "semantic_group_count": 1,
                    "max_dcr_after_max": 0.96,
                },
            ]
        },
        solver_loop_report={
            "summary": {
                "baseline_max_dcr": 1.8,
                "final_max_dcr": 0.95,
            }
        },
        wind_report={"summary": {"residual_drift_pct_max_abs": 0.02}},
        ssi_report={"summary": {"ssi_residual_drift_pct_max_abs": 0.03}},
        base_cfg=base_cfg,
    )
    cfg = apply_objective_calibration(base_cfg, report)
    assert cfg.congestion_penalty_scale != base_cfg.congestion_penalty_scale
    assert cfg.detailing_complexity_penalty_scale != base_cfg.detailing_complexity_penalty_scale
    assert cfg.robustness_penalty_scale != base_cfg.robustness_penalty_scale
    assert cfg.multi_hazard_penalty_scale != base_cfg.multi_hazard_penalty_scale
