#!/usr/bin/env python3
"""Run a deterministic constrained-search baseline on the design optimization dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from design_optimization_env import (
    DesignOptimizationConfig,
    aggregate_group_state,
    run_two_stage_search,
)


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    data = np.load(path)
    return {str(key): data[key] for key in data.files}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dataset-npz",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz",
    )
    p.add_argument(
        "--out",
        default="implementation/phase1/release/design_optimization/design_optimization_baseline_report.json",
    )
    p.add_argument("--rebar-step", type=float, default=0.002)
    p.add_argument("--min-rebar-ratio", type=float, default=0.004)
    p.add_argument("--max-rebar-ratio", type=float, default=0.08)
    p.add_argument("--max-iterations", type=int, default=48)
    p.add_argument("--dcr-limit", type=float, default=1.0)
    p.add_argument("--drift-limit-pct", type=float, default=2.0)
    p.add_argument("--residual-drift-limit-pct", type=float, default=0.5)
    args = p.parse_args()

    dataset = _load_npz(Path(args.dataset_npz))
    state = aggregate_group_state(dataset)
    cfg = DesignOptimizationConfig(
        rebar_step=float(args.rebar_step),
        min_rebar_ratio=float(args.min_rebar_ratio),
        max_rebar_ratio=float(args.max_rebar_ratio),
        max_iterations=int(args.max_iterations),
        dcr_limit=float(args.dcr_limit),
        drift_limit_pct=float(args.drift_limit_pct),
        residual_drift_limit_pct=float(args.residual_drift_limit_pct),
    )
    result = run_two_stage_search(state=state, cfg=cfg)

    baseline_cost = float(result["baseline_cost"])
    final_cost = float(result["final_cost"])
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-design-optimization-baseline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "dataset_npz": str(args.dataset_npz),
            "rebar_step": float(args.rebar_step),
            "min_rebar_ratio": float(args.min_rebar_ratio),
            "max_rebar_ratio": float(args.max_rebar_ratio),
            "max_iterations": int(args.max_iterations),
            "dcr_limit": float(args.dcr_limit),
            "drift_limit_pct": float(args.drift_limit_pct),
            "residual_drift_limit_pct": float(args.residual_drift_limit_pct),
        },
        "summary": {
            "group_count": int(np.asarray(state["group_ids"]).shape[0]),
            "baseline_cost_proxy": float(baseline_cost),
            "final_cost_proxy": float(final_cost),
            "cost_reduction_proxy": float(baseline_cost - final_cost),
            "baseline_violation_score": float(result["baseline_violation_score"]),
            "final_violation_score": float(result["final_violation_score"]),
            "feasible_after_repair": bool(result["feasible_after_repair"]),
            "final_max_dcr": float(result["final_max_dcr"]),
            "final_drift_pct": float(result["final_drift_pct"]),
            "final_residual_drift_pct": float(result["final_residual_drift_pct"]),
            "iteration_count_stage1": int(result["iteration_count_stage1"]),
            "iteration_count_stage2": int(result["iteration_count_stage2"]),
        },
        "stage1_actions_head": list(result["repair_history"][:32]),
        "stage2_actions_head": list(result["cost_reduction_history"][:32]),
        "contract_pass": bool(float(result["final_violation_score"]) <= float(result["baseline_violation_score"]) + 1.0e-9),
        "reason_code": "PASS" if float(result["final_violation_score"]) <= float(result["baseline_violation_score"]) + 1.0e-9 else "ERR_FAIL",
        "reason": "design optimization baseline completed",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote design optimization baseline report: {out}")


if __name__ == "__main__":
    main()
