#!/usr/bin/env python3
"""Non-promoting repeated scaled-LSMR accepted-step chain probe for G1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    FRAME_TANGENT_SOURCE_FORCE_BASED,
    FRAME_TANGENT_SOURCE_CHOICES,
    SHELL_PRESSURE_LOAD_PATH_POLICIES,
)
from run_g1_mgt_sparse_direct_physical_line_search_smoke import (
    DIRECTION_SOLVERS,
    run_g1_mgt_sparse_direct_physical_line_search_smoke,
)


SCHEMA_VERSION = "g1-mgt-sparse-direct-scaled-lsmr-chain-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_INITIAL_CHECKPOINT = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_chain_probe.json"
DEFAULT_STEP_PREFIX = PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_chain_step"


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _step_summary(payload: dict[str, Any], *, step_index: int) -> dict[str, Any]:
    line_search = payload.get("line_search_preview") or {}
    output_checkpoint = payload.get("output_final_checkpoint") or {}
    return {
        "step_index": int(step_index),
        "status": str(payload.get("status") or ""),
        "reason_code": str(payload.get("reason_code") or ""),
        "line_search_status": str(line_search.get("status") or ""),
        "accepted_alpha": _as_float(line_search.get("accepted_alpha")),
        "residual_before_n": _as_float(line_search.get("residual_before_n")),
        "residual_after_n": _as_float(line_search.get("residual_after_n")),
        "residual_reduction_ratio": _as_float(
            line_search.get("residual_reduction_ratio")
        ),
        "output_checkpoint_written": output_checkpoint.get("written") is True,
        "output_checkpoint_path": str(output_checkpoint.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "output_checkpoint_residual_gate_passed": (
            output_checkpoint.get("residual_gate_passed") is True
        ),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
    }


def summarize_chain(
    *,
    step_payloads: list[dict[str, Any]],
    initial_checkpoint: Path,
    max_steps: int,
    jvp_eps: float | None = None,
    residual_gate_n: float = 5.0e-4,
) -> dict[str, Any]:
    steps = [
        _step_summary(payload, step_index=index + 1)
        for index, payload in enumerate(step_payloads)
    ]
    finite_pairs = [
        (
            step["residual_before_n"],
            step["residual_after_n"],
        )
        for step in steps
        if step["residual_before_n"] is not None
        and step["residual_after_n"] is not None
    ]
    after_values = [after for _before, after in finite_pairs]
    all_step_descents = all(after < before for before, after in finite_pairs)
    monotonic_after = all(
        later <= earlier
        for earlier, later in zip(after_values, after_values[1:])
    )
    ready_steps = [
        step
        for step in steps
        if step["status"] == "ready"
        and step["line_search_status"] == "ready"
    ]
    written_steps = [
        step for step in steps if step["output_checkpoint_written"] is True
    ]
    initial_residual = finite_pairs[0][0] if finite_pairs else None
    final_residual = (
        steps[-1]["output_checkpoint_direct_residual_inf_n"] if steps else None
    )
    if final_residual is None and finite_pairs:
        final_residual = finite_pairs[-1][1]
    total_reduction = (
        initial_residual - final_residual
        if initial_residual is not None and final_residual is not None
        else None
    )
    step_reductions = [
        before - after
        for before, after in finite_pairs
        if before is not None and after is not None
    ]
    last_step_reduction = step_reductions[-1] if step_reductions else None
    final_gate_gap = (
        final_residual - float(residual_gate_n)
        if final_residual is not None
        else None
    )
    estimated_steps_to_gate = (
        int((final_gate_gap + last_step_reduction - 1.0e-30) // last_step_reduction)
        if final_gate_gap is not None
        and final_gate_gap > 0.0
        and last_step_reduction is not None
        and last_step_reduction > 0.0
        else None
    )
    gate_passed = (
        bool(final_residual <= float(residual_gate_n))
        if final_residual is not None
        else False
    )
    stalled_for_gate = bool(
        not gate_passed
        and estimated_steps_to_gate is not None
        and estimated_steps_to_gate > max(1000, int(max_steps) * 100)
    )
    gate_assessment = (
        "gate_passed"
        if gate_passed
        else "stalled_for_gate"
        if stalled_for_gate
        else "descent_but_gate_not_closed"
    )
    recommended_next_action = (
        "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
        if stalled_for_gate
        else "continue_scaled_lsmr_chain_or_compare_operator_variant"
        if not gate_passed
        else "promote_only_after_full_material_mesh_hip_gates"
    )
    latest_checkpoint = steps[-1]["output_checkpoint_path"] if steps else ""
    status = (
        "ready"
        if steps
        and len(ready_steps) == len(steps)
        and len(written_steps) == len(steps)
        and all_step_descents
        and monotonic_after
        else "review"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reason_code": "PASS" if status == "ready" else "CHAIN_NOT_FULLY_READY",
        "promotes_g1_closure": False,
        "is_smoke_only": True,
        "initial_checkpoint_npz": Path(initial_checkpoint).as_posix(),
        "max_steps": int(max_steps),
        "jvp_eps": _as_float(jvp_eps),
        "step_count": len(steps),
        "ready_step_count": len(ready_steps),
        "checkpoint_written_step_count": len(written_steps),
        "monotonic_residual_descent": bool(
            steps and all_step_descents and monotonic_after
        ),
        "initial_residual_n": initial_residual,
        "final_residual_n": final_residual,
        "residual_gate_n": float(residual_gate_n),
        "final_residual_gate_passed": gate_passed,
        "final_residual_gate_gap_n": final_gate_gap,
        "final_residual_over_gate": (
            final_residual / max(float(residual_gate_n), 1.0e-30)
            if final_residual is not None
            else None
        ),
        "gate_convergence_assessment": gate_assessment,
        "recommended_next_action": recommended_next_action,
        "total_reduction_n": total_reduction,
        "total_reduction_ratio": (
            total_reduction / max(initial_residual, 1.0e-30)
            if total_reduction is not None and initial_residual is not None
            else None
        ),
        "last_step_reduction_n": last_step_reduction,
        "last_step_reduction_ratio": (
            last_step_reduction / max(finite_pairs[-1][0], 1.0e-30)
            if last_step_reduction is not None and finite_pairs
            else None
        ),
        "mean_step_reduction_n": (
            sum(step_reductions) / len(step_reductions)
            if step_reductions
            else None
        ),
        "max_step_reduction_n": max(step_reductions) if step_reductions else None,
        "estimated_steps_to_gate_at_last_reduction": estimated_steps_to_gate,
        "latest_checkpoint_path": latest_checkpoint,
        "latest_checkpoint_residual_gate_passed": (
            steps[-1]["output_checkpoint_residual_gate_passed"] if steps else False
        ),
        "steps": steps,
        "claim_boundary": (
            "Non-promoting repeated scaled-LSMR accepted-step chain only. It "
            "does not close G1 without residual gate, full-mesh nonlinear "
            "equilibrium, material Newton breadth, and production ROCm/HIP proof."
        ),
    }


def run_chain_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    initial_checkpoint_npz: Path = DEFAULT_INITIAL_CHECKPOINT,
    max_steps: int = 3,
    load_scale: float = 1.0,
    frame_tangent_source: str = FRAME_TANGENT_SOURCE_FORCE_BASED,
    shell_pressure_load_path_policy: str = "structural_components_only",
    direction_solver: str = "scaled_lsmr",
    gmres_maxiter: int = 32,
    jvp_eps: float | None = None,
    residual_gate_n: float = 5.0e-4,
    output_json: Path = DEFAULT_OUT,
    step_prefix: Path = DEFAULT_STEP_PREFIX,
) -> dict[str, Any]:
    current_checkpoint = Path(initial_checkpoint_npz)
    step_payloads: list[dict[str, Any]] = []
    for index in range(1, max(0, int(max_steps)) + 1):
        step_json = Path(f"{step_prefix}_{index:02d}_probe.json")
        step_npz = Path(f"{step_prefix}_{index:02d}_candidate.npz")
        payload = run_g1_mgt_sparse_direct_physical_line_search_smoke(
            mgt_model=mgt_model,
            checkpoint_npz=current_checkpoint,
            direction_solver=direction_solver,
            load_scale=load_scale,
            frame_tangent_source=frame_tangent_source,
            shell_pressure_load_path_policy=shell_pressure_load_path_policy,
            gmres_maxiter=gmres_maxiter,
            jvp_eps=float(jvp_eps) if jvp_eps is not None else 1.0e-6,
            output_json=step_json,
            output_final_checkpoint_npz=step_npz,
        )
        step_payloads.append(payload)
        output_checkpoint = payload.get("output_final_checkpoint") or {}
        if (
            payload.get("status") != "ready"
            or (payload.get("line_search_preview") or {}).get("status") != "ready"
            or output_checkpoint.get("written") is not True
        ):
            break
        current_checkpoint = Path(str(output_checkpoint.get("path") or step_npz))
    chain = summarize_chain(
        step_payloads=step_payloads,
        initial_checkpoint=initial_checkpoint_npz,
        max_steps=max_steps,
        jvp_eps=jvp_eps,
        residual_gate_n=residual_gate_n,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(chain, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return chain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument(
        "--initial-checkpoint-npz",
        type=Path,
        default=DEFAULT_INITIAL_CHECKPOINT,
    )
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument(
        "--frame-tangent-source",
        choices=FRAME_TANGENT_SOURCE_CHOICES,
        default=FRAME_TANGENT_SOURCE_FORCE_BASED,
    )
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=SHELL_PRESSURE_LOAD_PATH_POLICIES,
        default="structural_components_only",
    )
    parser.add_argument(
        "--direction-solver",
        choices=list(DIRECTION_SOLVERS),
        default="scaled_lsmr",
    )
    parser.add_argument("--gmres-maxiter", type=int, default=32)
    parser.add_argument(
        "--jvp-eps",
        type=float,
        default=None,
        help="Optional central-difference epsilon forwarded to each sparse-direct smoke step.",
    )
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--step-prefix", type=Path, default=DEFAULT_STEP_PREFIX)
    args = parser.parse_args()
    payload = run_chain_probe(
        mgt_model=args.mgt_model,
        initial_checkpoint_npz=args.initial_checkpoint_npz,
        max_steps=args.max_steps,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        direction_solver=args.direction_solver,
        gmres_maxiter=args.gmres_maxiter,
        jvp_eps=args.jvp_eps,
        residual_gate_n=args.residual_gate_n,
        output_json=args.output_json,
        step_prefix=args.step_prefix,
    )
    print(
        "g1-mgt-sparse-direct-scaled-lsmr-chain-probe: "
        f"status={payload['status']} steps={payload['step_count']} "
        f"final={payload['final_residual_n']} "
        f"monotonic={payload['monotonic_residual_descent']} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
