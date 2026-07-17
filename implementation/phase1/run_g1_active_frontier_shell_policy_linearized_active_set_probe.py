#!/usr/bin/env python3
"""Linearized active-set probe for the G1 shell pressure policy frontier."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) in sys.path:
    sys.path.remove(str(PHASE1))
sys.path.insert(0, str(PHASE1))

from run_g1_active_set_ls_trust_candidate import (  # noqa: E402
    _active_set_direction,
    _top_free_rows,
)
from run_g1_true_newton_reference_candidate import _max_abs  # noqa: E402
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    ENGINE_VERSION,
    PRODUCTIZATION,
    _git_head,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "g1-active-frontier-shell-policy-linearized-active-set-probe.v1"
DEFAULT_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = (
    PRODUCTIZATION / "g1_active_frontier_shell_policy_linearized_active_set_probe.json"
)
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

AssembleResidual = Callable[
    [np.ndarray],
    tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]],
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in str(value).split(",") if item.strip())


def _row_descriptor(
    *, free: np.ndarray, residual: np.ndarray, row: int
) -> dict[str, Any]:
    row_index = int(row)
    global_dof = int(np.asarray(free, dtype=np.int64)[row_index])
    return {
        "reduced_row": row_index,
        "global_dof": global_dof,
        "node_index": int(global_dof // DOF_PER_NODE),
        "node_id": int(global_dof // DOF_PER_NODE) + 1,
        "dof_label": DOF_LABELS[int(global_dof % DOF_PER_NODE)],
        "residual_n": float(np.asarray(residual, dtype=np.float64)[row_index]),
    }


def run_linearized_active_set_probe(
    *,
    assemble_residual: AssembleResidual,
    u0: np.ndarray,
    active_row_counts: tuple[int, ...] = (8, 16, 32),
    trust_radius_m: float = 1.0e-8,
    max_lsmr_iterations: int = 128,
    residual_gate_n: float = 5.0e-4,
) -> dict[str, Any]:
    u = np.asarray(u0, dtype=np.float64)
    stiffness, _f_ext, free, residual, rhs, meta = assemble_residual(u)
    free = np.asarray(free, dtype=np.int64)
    residual = np.asarray(residual, dtype=np.float64)
    rhs = np.asarray(rhs, dtype=np.float64)
    residual_inf = _max_abs(residual)
    rhs_inf = _max_abs(rhs)
    dof_count = int(u.size)
    schedule = tuple(int(value) for value in active_row_counts if int(value) > 0)
    if not schedule:
        schedule = (8,)

    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for active_count in schedule:
        active_rows = _top_free_rows(residual, active_count)
        direction, direction_meta = _active_set_direction(
            stiffness=stiffness,
            free=free,
            residual=residual,
            active_rows=active_rows,
            dof_count=dof_count,
            trust_radius_m=float(trust_radius_m),
            max_iterations=int(max_lsmr_iterations),
        )
        free_direction = np.asarray(direction, dtype=np.float64)[free]
        k_ff = stiffness[free, :][:, free]
        active_matrix = k_ff[active_rows, :]
        active_before = residual[active_rows]
        linear_action = np.asarray(active_matrix @ free_direction, dtype=np.float64)
        active_after = active_before + linear_action
        before_inf = _max_abs(active_before)
        after_inf = _max_abs(active_after)
        improvement = before_inf - after_inf
        attempt = {
            "active_row_count": int(active_count),
            "active_rows": [int(row) for row in active_rows.tolist()],
            "active_row_descriptors": [
                _row_descriptor(free=free, residual=residual, row=int(row))
                for row in active_rows.tolist()
            ],
            "direction": direction_meta,
            "linear_active_residual_before_inf_n": before_inf,
            "linear_active_residual_after_inf_n": after_inf,
            "linear_active_improvement_inf_n": improvement,
            "linear_active_reduction_ratio": improvement / max(before_inf, 1.0e-30),
            "linearized_active_descent_observed": bool(improvement > 0.0),
        }
        attempts.append(attempt)
        if best is None or float(attempt["linear_active_residual_after_inf_n"]) < float(
            best["linear_active_residual_after_inf_n"]
        ):
            best = attempt

    best = best or {}
    return {
        "residual": residual,
        "rhs": rhs,
        "free": free,
        "meta": meta,
        "summary": {
            "base_residual_inf_n": residual_inf,
            "base_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
            "residual_gate_n": float(residual_gate_n),
            "base_residual_gate_passed": bool(residual_inf <= float(residual_gate_n)),
            "evaluated_active_row_count_schedule": [int(value) for value in schedule],
            "best_active_row_count": int(best.get("active_row_count") or 0),
            "best_linear_active_residual_before_inf_n": float(
                best.get("linear_active_residual_before_inf_n") or 0.0
            ),
            "best_linear_active_residual_after_inf_n": float(
                best.get("linear_active_residual_after_inf_n") or 0.0
            ),
            "best_linear_active_improvement_inf_n": float(
                best.get("linear_active_improvement_inf_n") or 0.0
            ),
            "best_linear_active_reduction_ratio": float(
                best.get("linear_active_reduction_ratio") or 0.0
            ),
            "linearized_active_descent_observed": any(
                bool(row.get("linearized_active_descent_observed")) for row in attempts
            ),
            "direct_replay_attempted": False,
            "direct_replay_required_for_candidate": True,
        },
        "attempts": attempts,
    }


def run_g1_active_frontier_shell_policy_linearized_active_set_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    shell_pressure_load_path_policy: str = "structural_components_only",
    output_json: Path = DEFAULT_OUT,
    active_row_counts: tuple[int, ...] = (8, 16, 32),
    trust_radius_m: float = 1.0e-8,
    max_lsmr_iterations: int = 128,
    residual_gate_n: float = 5.0e-4,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=str(shell_pressure_load_path_policy),
    )
    result = run_linearized_active_set_probe(
        assemble_residual=assemble_residual,
        u0=np.asarray(setup_meta["u0"], dtype=np.float64),
        active_row_counts=active_row_counts,
        trust_radius_m=trust_radius_m,
        max_lsmr_iterations=max_lsmr_iterations,
        residual_gate_n=residual_gate_n,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": setup_meta.get("load_scale"),
        "checkpoint_npz": str(checkpoint_npz),
        "mgt_model": str(mgt_path),
        "frame_tangent_source": str(
            setup_meta.get("frame_tangent_source") or "force_based_residual_tangent"
        ),
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "summary": result["summary"],
        "attempts": result["attempts"],
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Linearized active-set evidence only. It checks whether the current "
            "structural shell pressure policy tangent can reduce active residual rows. "
            "It does not replay the nonlinear direct residual, write a checkpoint, "
            "or close G1 full-load equilibrium."
        ),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=(
            "all_components",
            "attached_components_only",
            "structural_components_only",
        ),
        default="structural_components_only",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--active-row-counts", default="8,16,32")
    parser.add_argument("--trust-radius-m", type=float, default=1.0e-8)
    parser.add_argument("--max-lsmr-iterations", type=int, default=128)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_g1_active_frontier_shell_policy_linearized_active_set_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        shell_pressure_load_path_policy=str(args.shell_pressure_load_path_policy),
        output_json=args.output_json,
        active_row_counts=_parse_int_tuple(args.active_row_counts),
        trust_radius_m=float(args.trust_radius_m),
        max_lsmr_iterations=int(args.max_lsmr_iterations),
        residual_gate_n=float(args.residual_gate_n),
    )
    summary = payload["summary"]
    print(
        "g1-active-frontier-shell-policy-linearized-active-set-probe:",
        payload["status"],
        f"policy={payload.get('shell_pressure_load_path_policy')}",
        f"base={summary.get('base_residual_inf_n')}",
        f"best_linear_after={summary.get('best_linear_active_residual_after_inf_n')}",
        f"linear_descent={summary.get('linearized_active_descent_observed')}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
