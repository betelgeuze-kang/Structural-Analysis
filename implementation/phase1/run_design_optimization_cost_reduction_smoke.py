#!/usr/bin/env python3
"""Low-fi smoke runner for cost-reduction ROCm path isolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from design_optimization.artifacts import (  # noqa: E402
    COST_REDUCTION_SMOKE_REPORT_JSON,
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    SOLVER_LOOP_LONG_STATE_NPZ,
)
from design_optimization.artifact_writers import write_design_optimization_report  # noqa: E402
from design_optimization.io import load_json as _load_json, load_npz as _load_npz  # noqa: E402
from design_objective_calibration import apply_objective_calibration, apply_objective_profile  # noqa: E402
from design_optimization_env import ACTION_INDEX_V2, DesignOptimizationConfig, apply_group_action  # noqa: E402
from run_design_optimization_cost_reduction import (  # noqa: E402
    _cost_down_actions_for_group,
    _overlay_action_masks_from_dataset,
    _refine_action_masks_for_current_state,
)
from run_design_optimization_solver_loop import _solver_stage_state, solver_backends_gpu_strict  # noqa: E402


def _select_smoke_candidate(
    *,
    state: dict[str, np.ndarray],
    requested_group_index: int | None,
    requested_action_name: str | None,
) -> dict[str, object] | None:
    group_ids = np.asarray(state.get("group_ids", np.asarray([], dtype="<U1")))
    action_mask_ext = np.asarray(
        state.get("action_mask_extended", np.zeros((group_ids.size, 6), dtype=np.bool_)),
        dtype=np.bool_,
    )
    action_alias = {
        "beam_section_up": "thickness_up",
        "beam_section_down": "thickness_down",
        "wall_thickness_up": "thickness_up",
        "wall_thickness_down": "thickness_down",
        "slab_thickness_up": "thickness_up",
        "slab_thickness_down": "thickness_down",
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
    }
    compact_action_lookup = {
        "rebar_down": 0,
        "rebar_up": 1,
        "thickness_down": 2,
        "thickness_up": 3,
        "detailing_down": 4,
        "detailing_up": 5,
    }
    candidate_groups: list[int]
    if requested_group_index is not None:
        candidate_groups = [int(requested_group_index)]
    else:
        max_dcr = np.asarray(state.get("max_dcr", np.zeros(group_ids.size, dtype=np.float64)), dtype=np.float64)
        candidate_groups = list(np.argsort(-max_dcr).astype(int))
    for gi in candidate_groups:
        if gi < 0 or gi >= group_ids.size:
            continue
        action_names = [str(requested_action_name)] if requested_action_name else _cost_down_actions_for_group(state=state, group_index=gi)
        for action_name in action_names:
            action_idx = ACTION_INDEX_V2.get(str(action_name))
            if action_idx is None or action_idx >= action_mask_ext.shape[1]:
                resolved = action_alias.get(str(action_name), str(action_name))
                action_idx = compact_action_lookup.get(resolved)
            if action_idx is None or action_idx >= action_mask_ext.shape[1]:
                continue
            if not bool(action_mask_ext[gi, int(action_idx)]):
                continue
            return {
                "group_index": int(gi),
                "group_id": str(group_ids[gi]),
                "action_name": str(action_name),
            }
    return None


def run_cost_reduction_smoke(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    dataset_npz_path: Path | None,
    ndtha_step_count: int,
    requested_group_index: int | None = None,
    requested_action_name: str | None = None,
) -> dict[str, object]:
    baseline_state = _overlay_action_masks_from_dataset(state=state, dataset_npz_path=dataset_npz_path)
    baseline_state = _refine_action_masks_for_current_state(state=baseline_state, cfg=cfg)

    baseline_started = perf_counter()
    baseline_solver = _solver_stage_state(state=baseline_state, cfg=cfg, step_count=int(ndtha_step_count))
    baseline_runtime_s = perf_counter() - baseline_started

    candidate = _select_smoke_candidate(
        state=baseline_state,
        requested_group_index=requested_group_index,
        requested_action_name=requested_action_name,
    )
    if candidate is None:
        return {
            "contract_pass": False,
            "reason_code": "ERR_NO_SMOKE_ACTION",
            "reason": "no legal cost-down action available for smoke probe",
            "summary": {
                "baseline_runtime_s": float(baseline_runtime_s),
                "baseline_feasible": bool(baseline_solver.get("feasible", False)),
                "baseline_max_dcr": float(baseline_solver.get("max_dcr", 0.0) or 0.0),
                "baseline_max_drift_pct": float(baseline_solver.get("max_drift_pct", 0.0) or 0.0),
                "baseline_residual_drift_pct": float(baseline_solver.get("residual_drift_pct", 0.0) or 0.0),
                "smoke_step_count": int(ndtha_step_count),
                "trial_action_available": False,
            },
            "trial_state": None,
            "trial_solver": None,
        }

    updated = apply_group_action(
        rebar_ratio=np.asarray(baseline_state["rebar_ratio"], dtype=np.float64),
        action_mask=np.asarray(baseline_state["action_mask"], dtype=np.bool_),
        group_index=int(candidate["group_index"]),
        direction=-1,
        cfg=cfg,
        action_name=str(candidate["action_name"]),
        action_mask_extended=np.asarray(baseline_state["action_mask_extended"], dtype=np.bool_),
        thickness_scale=np.asarray(baseline_state.get("thickness_scale", np.ones_like(np.asarray(baseline_state["rebar_ratio"], dtype=np.float64))), dtype=np.float64),
        detailing_quality=np.asarray(baseline_state.get("detailing_quality", np.ones_like(np.asarray(baseline_state["rebar_ratio"], dtype=np.float64))), dtype=np.float64),
    )
    trial_state = dict(baseline_state)
    trial_state.update(updated)

    trial_started = perf_counter()
    trial_solver = _solver_stage_state(state=trial_state, cfg=cfg, step_count=int(ndtha_step_count))
    trial_runtime_s = perf_counter() - trial_started

    gpu_strict = bool(solver_backends_gpu_strict(baseline_solver) and solver_backends_gpu_strict(trial_solver))
    contract_pass = bool(gpu_strict)
    reason_code = "PASS" if contract_pass else "ERR_CPU_BACKEND"
    reason = "baseline + single-action smoke probe completed on GPU-strict solver backends" if contract_pass else "cpu backend or fallback detected during smoke probe"
    return {
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": reason,
        "summary": {
            "smoke_step_count": int(ndtha_step_count),
            "trial_action_available": True,
            "trial_group_index": int(candidate["group_index"]),
            "trial_group_id": str(candidate["group_id"]),
            "trial_action_name": str(candidate["action_name"]),
            "baseline_runtime_s": float(baseline_runtime_s),
            "trial_runtime_s": float(trial_runtime_s),
            "baseline_feasible": bool(baseline_solver.get("feasible", False)),
            "trial_feasible": bool(trial_solver.get("feasible", False)),
            "baseline_max_dcr": float(baseline_solver.get("max_dcr", 0.0) or 0.0),
            "trial_max_dcr": float(trial_solver.get("max_dcr", 0.0) or 0.0),
            "baseline_max_drift_pct": float(baseline_solver.get("max_drift_pct", 0.0) or 0.0),
            "trial_max_drift_pct": float(trial_solver.get("max_drift_pct", 0.0) or 0.0),
            "baseline_residual_drift_pct": float(baseline_solver.get("residual_drift_pct", 0.0) or 0.0),
            "trial_residual_drift_pct": float(trial_solver.get("residual_drift_pct", 0.0) or 0.0),
            "solver_backend_static": str(trial_solver.get("backend_static", "")),
            "solver_backend_ndtha": str(trial_solver.get("backend_ndtha", "")),
            "gpu_strict_solver_backends": bool(gpu_strict),
        },
        "trial_state": trial_state,
        "trial_solver": trial_solver,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state-npz", default=SOLVER_LOOP_LONG_STATE_NPZ)
    p.add_argument("--dataset-npz", default=DATASET_NPZ)
    p.add_argument("--out", default=COST_REDUCTION_SMOKE_REPORT_JSON)
    p.add_argument("--objective-calibration-report", default=OBJECTIVE_CALIBRATION_REPORT_JSON)
    p.add_argument("--objective-profile", default="balanced_practice")
    p.add_argument("--ndtha-step-count", type=int, default=24)
    p.add_argument("--group-index", type=int, default=None)
    p.add_argument("--action-name", default=None)
    p.add_argument("--rebar-step", type=float, default=0.002)
    p.add_argument("--thickness-step", type=float, default=0.01)
    p.add_argument("--detailing-step", type=float, default=0.03)
    p.add_argument("--min-rebar-ratio", type=float, default=0.004)
    p.add_argument("--max-rebar-ratio", type=float, default=0.08)
    p.add_argument("--dcr-limit", type=float, default=1.0)
    p.add_argument("--drift-limit-pct", type=float, default=2.0)
    p.add_argument("--residual-drift-limit-pct", type=float, default=0.5)
    args = p.parse_args()

    state = _load_npz(Path(args.state_npz))
    cfg = DesignOptimizationConfig(
        rebar_step=float(args.rebar_step),
        thickness_step=float(args.thickness_step),
        detailing_step=float(args.detailing_step),
        min_rebar_ratio=float(args.min_rebar_ratio),
        max_rebar_ratio=float(args.max_rebar_ratio),
        dcr_limit=float(args.dcr_limit),
        drift_limit_pct=float(args.drift_limit_pct),
        residual_drift_limit_pct=float(args.residual_drift_limit_pct),
    )
    calibration_report = _load_json(Path(args.objective_calibration_report))
    cfg = apply_objective_calibration(cfg, calibration_report)
    cfg = apply_objective_profile(cfg, profile_name=str(args.objective_profile))

    result = run_cost_reduction_smoke(
        state=state,
        cfg=cfg,
        dataset_npz_path=Path(args.dataset_npz) if str(args.dataset_npz).strip() else None,
        ndtha_step_count=int(args.ndtha_step_count),
        requested_group_index=args.group_index,
        requested_action_name=args.action_name,
    )
    write_design_optimization_report(
        Path(args.out),
        run_id="phase1-design-optimization-cost-reduction-smoke",
        summary={
            **dict(result["summary"]),
            "objective_profile": str(args.objective_profile),
        },
        inputs={
            "state_npz": str(args.state_npz),
            "dataset_npz": str(args.dataset_npz),
            "objective_calibration_report": str(args.objective_calibration_report),
            "objective_profile": str(args.objective_profile),
            "ndtha_step_count": int(args.ndtha_step_count),
            "group_index": args.group_index,
            "action_name": args.action_name,
        },
        artifacts={"report_out": str(args.out)},
        contract_pass=bool(result["contract_pass"]),
        reason_code=str(result["reason_code"]),
        reason=str(result["reason"]),
        extra={
            "trial_solver": result["trial_solver"],
        },
    )
    print(f"Wrote design optimization cost reduction smoke report: {args.out}")


if __name__ == "__main__":
    main()
