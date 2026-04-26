#!/usr/bin/env python3
"""Run a long-budget solver-validated constrained optimization loop."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from design_optimization.artifacts import (
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    SOLVER_LOOP_LONG_REPORT_JSON,
    SOLVER_LOOP_LONG_STATE_NPZ,
)
from design_optimization.artifact_writers import write_stage_report
from design_optimization.io import load_json, load_npz, write_state_npz
from design_objective_calibration import apply_objective_calibration, apply_objective_profile
from design_optimization_env import DesignOptimizationConfig, aggregate_group_state, hydrate_state_constructability_fields
from run_design_optimization_solver_loop import run_solver_constrained_loop


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dataset-npz",
        default=DATASET_NPZ,
    )
    p.add_argument(
        "--out",
        default=SOLVER_LOOP_LONG_REPORT_JSON,
    )
    p.add_argument(
        "--state-out",
        default=SOLVER_LOOP_LONG_STATE_NPZ,
    )
    p.add_argument("--rebar-step", type=float, default=0.002)
    p.add_argument("--thickness-step", type=float, default=0.01)
    p.add_argument("--detailing-step", type=float, default=0.03)
    p.add_argument("--min-rebar-ratio", type=float, default=0.004)
    p.add_argument("--max-rebar-ratio", type=float, default=0.08)
    p.add_argument("--max-iterations", type=int, default=32)
    p.add_argument("--dcr-limit", type=float, default=1.0)
    p.add_argument("--drift-limit-pct", type=float, default=2.0)
    p.add_argument("--residual-drift-limit-pct", type=float, default=0.5)
    p.add_argument("--ndtha-step-count", type=int, default=128)
    p.add_argument("--target-dcr-margin", type=float, default=0.0)
    p.add_argument("--per-group-escalation-cap", type=int, default=24)
    p.add_argument(
        "--objective-calibration-report",
        default=OBJECTIVE_CALIBRATION_REPORT_JSON,
    )
    p.add_argument("--objective-profile", default="balanced_practice")
    args = p.parse_args()

    dataset = load_npz(Path(args.dataset_npz))
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
    calibration_report = load_json(Path(args.objective_calibration_report))
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
    write_state_npz(Path(args.state_out), final_state)

    write_stage_report(
        Path(args.out),
        run_id="phase1-design-optimization-solver-loop-long",
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
        reason="long-budget solver-validated optimization loop completed",
        head_blocks={
            "stage1_proposed_head": result["proposed_stage1"],
            "stage1_accepted_head": result["accepted_stage1"],
            "stage1_extra_accepted_head": result.get("accepted_stage1_extra", []),
            "stage1_dcr_accepted_head": result.get("accepted_stage1_dcr", []),
            "stage2_proposed_head": result["proposed_stage2"],
            "stage2_accepted_head": result["accepted_stage2"],
        },
        extra={"mode": "long_budget"},
    )
    out = Path(args.out)
    print(f"Wrote long design optimization solver loop report: {out}")


if __name__ == "__main__":
    main()
