#!/usr/bin/env python3
"""Run a deterministic constrained-search baseline on the design optimization dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from cost_model import RegionalPriceTable, build_price_provenance
from design_optimization_env import (
    DesignOptimizationConfig,
    aggregate_group_state,
    run_two_stage_search,
)


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {str(key): data[key] for key in data.files}


def _unique_price_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError(f"duplicate_price_field:{key}")
        values[key] = value
    return values


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
    p.add_argument("--price-table", help="JSON RegionalPriceTable; absent means an uncalibrated cost index")
    args = p.parse_args()

    dataset = _load_npz(Path(args.dataset_npz))
    try:
        price_data = json.loads(Path(args.price_table).read_text(encoding="utf-8"), object_pairs_hook=_unique_price_fields) if args.price_table else {}
        price_table = RegionalPriceTable(**price_data)
        price_provenance = build_price_provenance(price_table)
    except (TypeError, ValueError, OSError) as exc:
        p.error(f"invalid price table: {exc}")
    state = aggregate_group_state(dataset, price_table=price_table)
    cfg = DesignOptimizationConfig(
        rebar_step=float(args.rebar_step),
        min_rebar_ratio=float(args.min_rebar_ratio),
        max_rebar_ratio=float(args.max_rebar_ratio),
        max_iterations=int(args.max_iterations),
        dcr_limit=float(args.dcr_limit),
        drift_limit_pct=float(args.drift_limit_pct),
        residual_drift_limit_pct=float(args.residual_drift_limit_pct),
    )
    search_started = perf_counter()
    result = run_two_stage_search(state=state, cfg=cfg)
    search_wall_seconds = perf_counter() - search_started

    baseline_cost = float(result["baseline_cost"])
    final_cost = float(result["final_cost"])
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-design-optimization-baseline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "dataset_npz": str(args.dataset_npz),
            "price_table": str(args.price_table) if args.price_table else None,
            "rebar_step": float(args.rebar_step),
            "min_rebar_ratio": float(args.min_rebar_ratio),
            "max_rebar_ratio": float(args.max_rebar_ratio),
            "max_iterations": int(args.max_iterations),
            "dcr_limit": float(args.dcr_limit),
            "drift_limit_pct": float(args.drift_limit_pct),
            "residual_drift_limit_pct": float(args.residual_drift_limit_pct),
        },
        "cost_basis": {
            "price_provenance": price_provenance,
            "scope": "approximate_material_quantities_only",
            "quantity_model": "sum_members_then_proportional_rebar_and_thickness_changes",
            "excluded": ["labor", "fabrication", "optimization_penalties", "compute_cost"],
            "verified_construction_savings": False,
            "monetary_savings": None,
        },
        "performance": {
            "search_wall_seconds": search_wall_seconds,
            "solver_wall_seconds": None,
            "ai_inference_seconds": None,
            "speedup": None,
            "scope": "deterministic_proxy_search_only",
        },
        "structural_verification": {
            "status": "not_run",
            "response_basis": "deterministic_search_proxy",
            "final_design_eligible": False,
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
