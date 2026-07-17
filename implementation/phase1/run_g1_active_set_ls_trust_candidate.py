#!/usr/bin/env python3
"""Non-promoting active-set least-squares trust candidate for G1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import numpy as np
from scipy.sparse.linalg import lsmr

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_g1_true_newton_reference_candidate import (  # noqa: E402
    CHECKPOINT_SCHEMA,
    _max_abs,
    _translation_metrics,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    ENGINE_VERSION,
    PRODUCTIZATION,
    _git_head,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "g1-active-set-ls-trust-candidate.v1"
DEFAULT_OUT = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.json"
)
DEFAULT_OUT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)

AssembleResidual = Callable[
    [np.ndarray],
    tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]],
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _top_free_rows(residual: np.ndarray, max_rows: int) -> np.ndarray:
    residual = np.asarray(residual, dtype=np.float64)
    count = min(max(int(max_rows), 1), int(residual.size))
    rows = np.argpartition(np.abs(residual), -count)[-count:]
    return rows[np.argsort(-np.abs(residual[rows]))].astype(np.int64)


def _active_set_direction(
    *,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
    active_rows: np.ndarray,
    dof_count: int,
    trust_radius_m: float,
    max_iterations: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    active_rows = np.asarray(active_rows, dtype=np.int64)
    k_ff = stiffness[free_idx, :][:, free_idx]
    active_matrix = k_ff[active_rows, :]
    active_residual = np.asarray(residual, dtype=np.float64)[active_rows]
    solve_result = lsmr(
        active_matrix,
        -active_residual,
        atol=1.0e-12,
        btol=1.0e-12,
        maxiter=max(int(max_iterations), 1),
    )
    raw_free = np.asarray(solve_result[0], dtype=np.float64)
    raw_inf = _max_abs(raw_free)
    trust_radius = float(trust_radius_m)
    trust_scale = 1.0
    if raw_inf > trust_radius > 0.0:
        trust_scale = trust_radius / raw_inf
    free_direction = raw_free * trust_scale
    direction = np.zeros(int(dof_count), dtype=np.float64)
    direction[free_idx] = free_direction
    active_linear_residual = (
        np.asarray(active_matrix @ free_direction, dtype=np.float64) + active_residual
    )
    return direction, {
        "active_row_count": int(active_rows.size),
        "raw_direction_inf_m": raw_inf,
        "trust_radius_m": trust_radius,
        "trust_scale": trust_scale,
        "direction_inf_m": _max_abs(direction),
        "active_linear_residual_inf_n": _max_abs(active_linear_residual),
        "solver": "scipy_lsmr_active_set_cpu_diagnostic",
        "solver_stats": {
            "istop": int(solve_result[1]),
            "iteration_count": int(solve_result[2]),
            "normr": float(solve_result[3]),
            "normar": float(solve_result[4]),
            "norma": float(solve_result[5]),
            "condition_estimate": float(solve_result[6]),
            "normx": float(solve_result[7]),
            "max_iterations": int(max_iterations),
        },
    }


def run_active_set_ls_trust_iterations(
    *,
    assemble_residual: AssembleResidual,
    u0: np.ndarray,
    max_steps: int = 8,
    active_row_count: int = 8,
    active_row_counts: tuple[int, ...] | None = None,
    trust_radius_m: float = 1.0e-8,
    max_lsmr_iterations: int = 128,
    alpha_values: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125),
    residual_gate_n: float = 5.0e-4,
) -> dict[str, Any]:
    u = np.asarray(u0, dtype=np.float64).copy()
    (
        initial_k,
        _initial_f,
        initial_free,
        initial_residual,
        initial_rhs,
        _initial_meta,
    ) = assemble_residual(u)
    _ = initial_k
    initial_inf = _max_abs(initial_residual)
    initial_rhs_inf = _max_abs(initial_rhs)
    history: list[dict[str, Any]] = []
    stop_reason = "max_steps"
    free_stable = np.asarray(initial_free, dtype=np.int64)
    active_row_count_schedule = tuple(
        int(value)
        for value in (
            active_row_counts if active_row_counts is not None else (active_row_count,)
        )
        if int(value) > 0
    )
    if not active_row_count_schedule:
        active_row_count_schedule = (int(active_row_count),)
    for step in range(int(max_steps)):
        stiffness, _f_ext, free, residual, rhs, _meta = assemble_residual(u)
        free = np.asarray(free, dtype=np.int64)
        residual = np.asarray(residual, dtype=np.float64)
        rhs = np.asarray(rhs, dtype=np.float64)
        residual_before = _max_abs(residual)
        if residual_before <= float(residual_gate_n):
            stop_reason = "residual_gate_passed"
            break
        if free.shape != free_stable.shape or not np.array_equal(free, free_stable):
            stop_reason = "free_dof_set_changed"
            break
        direction_attempts: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        best_direction: np.ndarray | None = None
        best_attempt: dict[str, Any] | None = None
        for active_count in active_row_count_schedule:
            active_rows = _top_free_rows(residual, active_count)
            try:
                direction, direction_meta = _active_set_direction(
                    stiffness=stiffness,
                    free=free,
                    residual=residual,
                    active_rows=active_rows,
                    dof_count=int(u.size),
                    trust_radius_m=float(trust_radius_m),
                    max_iterations=int(max_lsmr_iterations),
                )
            except Exception as exc:  # noqa: BLE001
                direction_attempts.append(
                    {
                        "active_row_count": int(active_count),
                        "active_rows": [int(row) for row in active_rows.tolist()],
                        "direction_status": "blocked",
                        "reason": f"{exc.__class__.__name__}: {exc}",
                        "candidate_rows": [],
                    }
                )
                continue
            if _max_abs(direction) <= 0.0:
                direction_attempts.append(
                    {
                        "active_row_count": int(active_count),
                        "active_rows": [int(row) for row in active_rows.tolist()],
                        "direction_status": "blocked",
                        "reason": "zero_direction",
                        "direction": direction_meta,
                        "candidate_rows": [],
                    }
                )
                continue
            candidate_rows: list[dict[str, Any]] = []
            attempt_best: dict[str, Any] | None = None
            for alpha in alpha_values:
                alpha_float = float(alpha)
                trial_u = u + alpha_float * direction
                (
                    _trial_k,
                    _trial_f,
                    trial_free,
                    trial_residual,
                    trial_rhs,
                    _trial_meta,
                ) = assemble_residual(trial_u)
                trial_free = np.asarray(trial_free, dtype=np.int64)
                trial_residual = np.asarray(trial_residual, dtype=np.float64)
                trial_stable = bool(
                    trial_free.shape == free.shape and np.array_equal(trial_free, free)
                )
                trial_inf = _max_abs(trial_residual)
                active_trial_inf = _max_abs(trial_residual[active_rows])
                row = {
                    "alpha": alpha_float,
                    "free_dof_set_stable": trial_stable,
                    "direct_residual_inf_n": trial_inf,
                    "active_residual_inf_n": active_trial_inf,
                    "direct_relative_residual_inf": trial_inf
                    / max(_max_abs(trial_rhs), 1.0),
                    "improvement_inf_n": residual_before - trial_inf,
                    "active_improvement_inf_n": _max_abs(residual[active_rows])
                    - active_trial_inf,
                    "residual_gate_passed": trial_inf <= float(residual_gate_n),
                }
                candidate_rows.append(row)
                if trial_stable and trial_inf < residual_before:
                    if attempt_best is None or trial_inf < float(
                        attempt_best["direct_residual_inf_n"]
                    ):
                        attempt_best = row
            attempt = {
                "active_row_count": int(active_count),
                "active_rows": [int(row) for row in active_rows.tolist()],
                "direction_status": "ready",
                "direction": direction_meta,
                "candidate_rows": candidate_rows,
                "best_candidate": attempt_best or {},
            }
            direction_attempts.append(attempt)
            if attempt_best is not None:
                if best is None or float(attempt_best["direct_residual_inf_n"]) < float(
                    best["direct_residual_inf_n"]
                ):
                    best = attempt_best
                    best_direction = direction
                    best_attempt = attempt
        if best is None:
            history.append(
                {
                    "iteration": step,
                    "residual_before_n": residual_before,
                    "direction_attempts": direction_attempts,
                    "accepted": False,
                }
            )
            stop_reason = "no_candidate_descent"
            break
        alpha = float(best["alpha"])
        if best_direction is None or best_attempt is None:
            stop_reason = "direction_selection_failed"
            break
        u = u + alpha * best_direction
        history.append(
            {
                "iteration": step,
                "residual_before_n": residual_before,
                "residual_after_n": float(best["direct_residual_inf_n"]),
                "residual_reduction_n": residual_before
                - float(best["direct_residual_inf_n"]),
                "residual_reduction_ratio": (
                    residual_before - float(best["direct_residual_inf_n"])
                )
                / max(residual_before, 1.0e-30),
                "selected_active_row_count": int(best_attempt["active_row_count"]),
                "active_rows": best_attempt["active_rows"],
                "direction": best_attempt["direction"],
                "candidate_rows": best_attempt["candidate_rows"],
                "direction_attempts": direction_attempts,
                "accepted": True,
                "accepted_alpha": alpha,
            }
        )
    _final_k, _final_f, final_free, final_residual, final_rhs, _final_meta = (
        assemble_residual(u)
    )
    final_residual = np.asarray(final_residual, dtype=np.float64)
    final_rhs = np.asarray(final_rhs, dtype=np.float64)
    final_inf = _max_abs(final_residual)
    if final_inf <= float(residual_gate_n):
        stop_reason = "residual_gate_passed"
    return {
        "history": history,
        "final_state": u,
        "final_free": np.asarray(final_free, dtype=np.int64),
        "final_residual": final_residual,
        "final_rhs": final_rhs,
        "summary": {
            "initial_residual_n": initial_inf,
            "final_residual_n": final_inf,
            "initial_relative_residual_inf": initial_inf / max(initial_rhs_inf, 1.0),
            "final_relative_residual_inf": final_inf / max(_max_abs(final_rhs), 1.0),
            "total_reduction_n": initial_inf - final_inf,
            "total_reduction_ratio": (initial_inf - final_inf)
            / max(initial_inf, 1.0e-30),
            "residual_gate_n": float(residual_gate_n),
            "residual_gate_passed": bool(final_inf <= float(residual_gate_n)),
            "steps_taken": len([row for row in history if row.get("accepted") is True]),
            "stop_reason": stop_reason,
            "active_row_count_schedule": [
                int(value) for value in active_row_count_schedule
            ],
        },
    }


def _write_checkpoint(
    *,
    path: Path,
    load_scale: float,
    displacement_u: np.ndarray,
    final_residual: np.ndarray,
    final_rhs: np.ndarray,
    steps_taken: int,
    residual_gate_n: float,
    frame_tangent_source: str,
    shell_pressure_load_path_policy: str,
) -> dict[str, Any]:
    residual_inf = _max_abs(final_residual)
    rhs_inf = _max_abs(final_rhs)
    translation = _translation_metrics(displacement_u)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray(CHECKPOINT_SCHEMA),
        source_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(float(load_scale), dtype=np.float64),
        displacement_u=np.asarray(displacement_u, dtype=np.float64),
        residual_inf_n=np.asarray(residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            residual_inf / max(rhs_inf, 1.0), dtype=np.float64
        ),
        max_translation_m=np.asarray(
            translation["max_translation_m"], dtype=np.float64
        ),
        accepted_iteration_count=np.asarray(int(steps_taken), dtype=np.int64),
        accepted_history_count=np.asarray(int(steps_taken), dtype=np.int64),
        residual_gate_n=np.asarray(float(residual_gate_n), dtype=np.float64),
        residual_gate_passed=np.asarray(bool(residual_inf <= float(residual_gate_n))),
        frame_tangent_source=np.asarray(frame_tangent_source),
        shell_pressure_load_path_policy=np.asarray(shell_pressure_load_path_policy),
        active_set_ls_candidate_only=np.asarray(True),
        promotes_g1_closure=np.asarray(False),
        checkpoint_claim_boundary=np.asarray(
            "non_promoting_active_set_ls_trust_checkpoint_candidate"
        ),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": CHECKPOINT_SCHEMA,
        "load_scale": float(load_scale),
        "dof_count": int(np.asarray(displacement_u).size),
        "direct_residual_inf_n": residual_inf,
        "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_iteration_count": int(steps_taken),
        "accepted_history_count": int(steps_taken),
        "residual_gate_n": float(residual_gate_n),
        "residual_gate_passed": bool(residual_inf <= float(residual_gate_n)),
        "frame_tangent_source": frame_tangent_source,
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Loadable active-set LS trust checkpoint candidate only. It does not "
            "close G1 without direct residual, material Newton, full-mesh, and "
            "production ROCm/HIP gates."
        ),
    }


def run_g1_active_set_ls_trust_candidate(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    shell_pressure_load_path_policy: str = "all_components",
    output_json: Path = DEFAULT_OUT,
    output_final_checkpoint_npz: Path | None = DEFAULT_OUT_NPZ,
    max_steps: int = 8,
    active_row_count: int = 8,
    active_row_counts: tuple[int, ...] | None = None,
    trust_radius_m: float = 1.0e-8,
    max_lsmr_iterations: int = 128,
    alpha_values: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125),
    residual_gate_n: float = 5.0e-4,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=str(shell_pressure_load_path_policy),
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    result = run_active_set_ls_trust_iterations(
        assemble_residual=assemble_residual,
        u0=u0,
        max_steps=max_steps,
        active_row_count=active_row_count,
        active_row_counts=active_row_counts,
        trust_radius_m=trust_radius_m,
        max_lsmr_iterations=max_lsmr_iterations,
        alpha_values=alpha_values,
        residual_gate_n=residual_gate_n,
    )
    final_checkpoint = None
    if output_final_checkpoint_npz is not None:
        final_checkpoint = _write_checkpoint(
            path=Path(output_final_checkpoint_npz),
            load_scale=float(setup_meta.get("load_scale") or 0.0),
            displacement_u=np.asarray(result["final_state"], dtype=np.float64),
            final_residual=np.asarray(result["final_residual"], dtype=np.float64),
            final_rhs=np.asarray(result["final_rhs"], dtype=np.float64),
            steps_taken=int(result["summary"]["steps_taken"]),
            residual_gate_n=float(residual_gate_n),
            frame_tangent_source=str(
                setup_meta.get("frame_tangent_source") or "force_based_residual_tangent"
            ),
            shell_pressure_load_path_policy=str(shell_pressure_load_path_policy),
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "status": (
            "candidate_created" if result["summary"]["steps_taken"] > 0 else "review"
        ),
        "promotes_g1_closure": False,
        "load_scale": setup_meta.get("load_scale"),
        "checkpoint_npz": str(checkpoint_npz),
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "strategy": {
            "mode": "iterative_active_set_global_least_squares_trust",
            "active_row_count": int(active_row_count),
            "active_row_count_schedule": [
                int(value)
                for value in (
                    active_row_counts
                    if active_row_counts is not None
                    else (active_row_count,)
                )
            ],
            "trust_radius_m": float(trust_radius_m),
            "max_lsmr_iterations": int(max_lsmr_iterations),
            "alpha_values": [float(value) for value in alpha_values],
            "selection_metric": "direct_residual_inf_descent",
        },
        "summary": result["summary"],
        "history": result["history"],
        "output_final_checkpoint": final_checkpoint,
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Non-promoting active-set LS trust candidate. It may lower the current "
            "full-load residual frontier but does not close G1, material Newton "
            "breadth, full-mesh equilibrium, or production ROCm/HIP residency."
        ),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(_json_text(payload), encoding="utf-8")
    return payload


def _parse_float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in str(value).split(",") if item.strip())


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in str(value).split(",") if item.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--shell-pressure-load-path-policy", default="all_components")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-final-checkpoint-npz", type=Path, default=DEFAULT_OUT_NPZ
    )
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--active-row-count", type=int, default=8)
    parser.add_argument(
        "--active-row-counts",
        default="",
        help="Optional comma-separated active row count schedule; overrides --active-row-count.",
    )
    parser.add_argument("--trust-radius-m", type=float, default=1.0e-8)
    parser.add_argument("--max-lsmr-iterations", type=int, default=128)
    parser.add_argument("--alpha-values", default="1,0.5,0.25,0.125,0.0625,0.03125")
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_g1_active_set_ls_trust_candidate(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        shell_pressure_load_path_policy=str(args.shell_pressure_load_path_policy),
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        max_steps=int(args.max_steps),
        active_row_count=int(args.active_row_count),
        active_row_counts=(
            _parse_int_tuple(args.active_row_counts)
            if str(args.active_row_counts).strip()
            else None
        ),
        trust_radius_m=float(args.trust_radius_m),
        max_lsmr_iterations=int(args.max_lsmr_iterations),
        alpha_values=_parse_float_tuple(args.alpha_values),
        residual_gate_n=float(args.residual_gate_n),
    )
    summary = payload["summary"]
    print(
        "g1-active-set-ls-trust-candidate:",
        payload["status"],
        f"initial={summary.get('initial_residual_n')}",
        f"final={summary.get('final_residual_n')}",
        f"steps={summary.get('steps_taken')}",
        f"gate={summary.get('residual_gate_passed')}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
