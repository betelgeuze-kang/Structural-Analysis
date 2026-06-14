#!/usr/bin/env python3
"""Chain cached residual/JVP multi-ridge G1 probes from a promoted checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_mgt_cached_residual_jvp_batch_probe import (  # noqa: E402
    PRODUCTIZATION,
    run_mgt_cached_residual_jvp_batch_probe,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-cached-residual-jvp-multi-ridge-controller.v1"


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


def _default_summary_path(start_followup_index: int, max_steps: int) -> Path:
    end_index = int(start_followup_index) + max(int(max_steps), 1) - 1
    return (
        PRODUCTIZATION
        / f"mgt_cached_residual_jvp_top96_multi_ridge_followup{start_followup_index}_{end_index}_controller_summary.json"
    )


def _display_path(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def run_controller(
    *,
    mgt_path: Path,
    start_checkpoint_npz: Path,
    start_followup_index: int,
    max_steps: int,
    output_summary_json: Path,
    min_relative_improvement: float,
    stop_after_no_promotion: bool,
    residual_tolerance_n: float,
    top_residual_count: int,
    max_rows: int,
    max_support_columns: int,
    alpha_values: tuple[float, ...],
    extra_ridge_factors: tuple[float, ...],
) -> dict[str, Any]:
    started = time.perf_counter()
    current_checkpoint = Path(start_checkpoint_npz)
    step_rows: list[dict[str, Any]] = []
    stop_reason = "max_steps_exhausted"
    latest_residual = None
    for offset in range(max(int(max_steps), 0)):
        followup_index = int(start_followup_index) + int(offset)
        output_json = (
            PRODUCTIZATION
            / f"mgt_cached_residual_jvp_top96_multi_ridge_followup{followup_index}_probe.json"
        )
        output_npz = (
            PRODUCTIZATION
            / f"mgt_cached_residual_jvp_top96_multi_ridge_followup{followup_index}_probe.npz"
        )
        output_checkpoint = (
            PRODUCTIZATION
            / f"mgt_cached_residual_jvp_top96_multi_ridge_followup{followup_index}_final_checkpoint.npz"
        )
        payload = run_mgt_cached_residual_jvp_batch_probe(
            mgt_path=mgt_path,
            checkpoint_npz=current_checkpoint,
            shell_pressure_load_path_policy="attached_components_only",
            output_json=output_json,
            output_npz=output_npz,
            output_final_checkpoint_npz=output_checkpoint,
            promote_gate_eligible=True,
            top_residual_count=int(top_residual_count),
            max_rows=int(max_rows),
            component_filter="all",
            selection_policy="top",
            support_columns_per_row=1,
            node_block_support=True,
            max_support_columns=int(max_support_columns),
            finite_difference_epsilon_m=1.0e-7,
            ridge_factor=1.0e-8,
            extra_ridge_factors=extra_ridge_factors,
            alpha_values=alpha_values,
            allow_negative_alphas=True,
            include_gate_limited_alpha=True,
            max_dynamic_alpha=1000000.0,
            min_relative_improvement=float(min_relative_improvement),
            residual_tolerance_n=float(residual_tolerance_n),
            relative_increment_tolerance=1.0e-4,
        )
        base_residual = float(
            payload.get("base_direct_residual", {}).get("direct_residual_inf_n")
            or 0.0
        )
        best_candidate = payload.get("best_candidate")
        best_candidate = best_candidate if isinstance(best_candidate, dict) else {}
        checkpoint_meta = payload.get("output_final_checkpoint")
        checkpoint_meta = checkpoint_meta if isinstance(checkpoint_meta, dict) else {}
        promoted = bool(payload.get("promoted_to_final_state"))
        final_residual = float(
            checkpoint_meta.get("direct_residual_inf_n")
            if promoted
            else best_candidate.get("direct_residual_inf_n", base_residual)
        )
        latest_residual = final_residual
        row = {
            "followup_index": int(followup_index),
            "probe": _display_path(output_json),
            "basis_npz": _display_path(output_npz),
            "checkpoint": _display_path(output_checkpoint) if promoted else None,
            "source_checkpoint": _display_path(current_checkpoint),
            "promoted": promoted,
            "base_direct_residual_inf_n": base_residual,
            "final_or_best_direct_residual_inf_n": final_residual,
            "improvement_inf_n": float(best_candidate.get("improvement_inf_n") or 0.0),
            "direction_source": best_candidate.get("direction_source"),
            "alpha": best_candidate.get("alpha"),
            "accepted_history_count": checkpoint_meta.get("accepted_history_count"),
        }
        step_rows.append(row)
        if final_residual <= float(residual_tolerance_n):
            stop_reason = "residual_gate_passed"
            break
        if not promoted:
            stop_reason = "no_promotion"
            if bool(stop_after_no_promotion):
                break
        else:
            current_checkpoint = output_checkpoint
    if not step_rows and max_steps <= 0:
        stop_reason = "no_steps_requested"
    promoted_rows = [row for row in step_rows if bool(row.get("promoted"))]
    total_improvement = sum(float(row.get("improvement_inf_n") or 0.0) for row in promoted_rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "start_checkpoint": _display_path(start_checkpoint_npz),
        "latest_checkpoint": _display_path(current_checkpoint),
        "latest_direct_residual_inf_n": latest_residual,
        "residual_gate_n": float(residual_tolerance_n),
        "remaining_residual_margin_to_gate_n": (
            None
            if latest_residual is None
            else max(float(latest_residual) - float(residual_tolerance_n), 0.0)
        ),
        "controller": {
            "start_followup_index": int(start_followup_index),
            "max_steps": int(max_steps),
            "stop_reason": stop_reason,
            "stop_after_no_promotion": bool(stop_after_no_promotion),
            "min_relative_improvement": float(min_relative_improvement),
            "promoted_count": int(len(promoted_rows)),
            "total_promoted_improvement_inf_n": float(total_improvement),
            "runtime_seconds": float(time.perf_counter() - started),
        },
        "configuration": {
            "top_residual_count": int(top_residual_count),
            "max_rows": int(max_rows),
            "max_support_columns": int(max_support_columns),
            "alpha_values": [float(value) for value in alpha_values],
            "extra_ridge_factors": [float(value) for value in extra_ridge_factors],
        },
        "steps": step_rows,
        "claim_boundary": (
            "Controller convenience for cached residual/JVP multi-ridge probes only. "
            "It does not claim residual gate closure or production ROCm/HIP residency."
        ),
    }
    output_summary_json.parent.mkdir(parents=True, exist_ok=True)
    output_summary_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--start-checkpoint-npz", type=Path, required=True)
    parser.add_argument("--start-followup-index", type=int, required=True)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--output-summary-json", type=Path, default=None)
    parser.add_argument("--min-relative-improvement", type=float, default=1.0e-8)
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    parser.add_argument("--top-residual-count", type=int, default=128)
    parser.add_argument("--max-rows", type=int, default=96)
    parser.add_argument("--max-support-columns", type=int, default=384)
    parser.add_argument(
        "--alpha-values",
        default=(
            "1,0.5,0.25,0.125,0.0625,0.03125,0.015625,0.0078125,"
            "0.00390625,0.001953125,0.0009765625,0.00048828125,"
            "0.000244140625,6.103515625e-05,1.52587890625e-05,"
            "3.814697265625e-06,9.5367431640625e-07,"
            "2.384185791015625e-07,5.960464477539063e-08,1e-08"
        ),
    )
    parser.add_argument(
        "--extra-ridge-factors",
        default="1e-7,1e-6,1e-5,1e-4,1e-3,1e-2,1e-1",
    )
    parser.add_argument("--continue-after-no-promotion", action="store_true")
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this controller is diagnostic and does not close G1 by itself.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_cpu_diagnostic:
        print("multi-ridge-controller: blocked diagnostic requires --allow-cpu-diagnostic")
        return 2
    output_summary_json = (
        args.output_summary_json
        if args.output_summary_json is not None
        else _default_summary_path(args.start_followup_index, args.max_steps)
    )
    payload = run_controller(
        mgt_path=args.mgt_path,
        start_checkpoint_npz=args.start_checkpoint_npz,
        start_followup_index=args.start_followup_index,
        max_steps=args.max_steps,
        output_summary_json=output_summary_json,
        min_relative_improvement=args.min_relative_improvement,
        stop_after_no_promotion=not bool(args.continue_after_no_promotion),
        residual_tolerance_n=args.residual_tolerance_n,
        top_residual_count=args.top_residual_count,
        max_rows=args.max_rows,
        max_support_columns=args.max_support_columns,
        alpha_values=_parse_float_csv(args.alpha_values),
        extra_ridge_factors=_parse_float_csv(args.extra_ridge_factors),
    )
    print(
        "multi-ridge-controller: "
        f"steps={len(payload['steps'])} "
        f"promoted={payload['controller']['promoted_count']} "
        f"latest={payload.get('latest_direct_residual_inf_n')} "
        f"stop={payload['controller']['stop_reason']} -> {output_summary_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
