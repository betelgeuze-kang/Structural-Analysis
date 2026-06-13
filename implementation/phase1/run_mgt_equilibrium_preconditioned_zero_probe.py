#!/usr/bin/env python3
"""Cheap preconditioned correction probe from the zero equilibrium state."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_sparse_linear_solver import build_node_block_jacobi_preconditioner  # noqa: E402
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-equilibrium-preconditioned-zero-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_equilibrium_preconditioned_zero_probe.json"
DEFAULT_FINAL_CHECKPOINT = PRODUCTIZATION / "mgt_equilibrium_preconditioned_zero_final_checkpoint.npz"


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _float_or_inf(value: Any) -> float:
    if value is None:
        return float("inf")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("inf")
    return number if np.isfinite(number) else float("inf")


def _translation_metrics(u: np.ndarray) -> dict[str, float]:
    arr = np.asarray(u, dtype=np.float64)
    if arr.size % 6 != 0:
        return {"max_translation_m": _max_abs(arr)}
    translations = arr.reshape((-1, 6))[:, :3]
    return {
        "max_translation_m": float(np.max(np.linalg.norm(translations, axis=1)))
        if translations.size
        else 0.0
    }


def _same_state_exact(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(
        np.array_equal(
            np.asarray(left, dtype=np.float64),
            np.asarray(right, dtype=np.float64),
        )
    )


def write_preconditioned_checkpoint(
    *,
    path: Path,
    source_checkpoint_npz: Path,
    source_checkpoint_meta: dict[str, Any],
    start_u: np.ndarray,
    final_u: np.ndarray,
    start_residual: np.ndarray,
    final_residual: np.ndarray,
    final_rhs: np.ndarray,
    loaded_state_history: np.ndarray | None,
    loaded_residual_history: np.ndarray | None,
    accepted_iteration_count: int,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    start_np = np.asarray(start_u, dtype=np.float64)
    final_np = np.asarray(final_u, dtype=np.float64)
    start_residual_np = np.asarray(start_residual, dtype=np.float64)
    final_residual_np = np.asarray(final_residual, dtype=np.float64)
    final_rhs_np = np.asarray(final_rhs, dtype=np.float64)

    state_rows: list[np.ndarray] = []
    if (
        loaded_state_history is not None
        and loaded_state_history.ndim == 2
        and loaded_state_history.shape[1] == final_np.size
    ):
        state_rows = [
            np.asarray(row, dtype=np.float64).copy() for row in loaded_state_history
        ]
    if not state_rows or not _same_state_exact(state_rows[-1], start_np):
        state_rows.append(start_np.copy())
    if not _same_state_exact(state_rows[-1], final_np):
        state_rows.append(final_np.copy())

    residual_rows: list[np.ndarray] = []
    if (
        loaded_residual_history is not None
        and loaded_residual_history.ndim == 2
        and loaded_residual_history.shape[1] == final_residual_np.size
    ):
        residual_rows = [
            np.asarray(row, dtype=np.float64).copy()
            for row in loaded_residual_history
        ]
    while len(residual_rows) < max(len(state_rows) - 1, 0):
        residual_rows.append(start_residual_np.copy())
    if len(residual_rows) < len(state_rows):
        residual_rows.append(final_residual_np.copy())
    else:
        residual_rows[-1] = final_residual_np.copy()

    state_history = np.vstack(state_rows)
    residual_history = np.vstack(residual_rows)
    final_residual_inf = _max_abs(final_residual_np)
    rhs_inf = _max_abs(final_rhs_np)
    translation = _translation_metrics(final_np)
    load_scale = float(source_checkpoint_meta.get("load_scale") or 0.0)
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        source_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(load_scale, dtype=np.float64),
        displacement_u=final_np,
        residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            final_residual_inf / max(rhs_inf, 1.0),
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(translation["max_translation_m"], dtype=np.float64),
        accepted_state_history_u=state_history,
        accepted_residual_history=residual_history,
        accepted_history_count=np.asarray(state_history.shape[0], dtype=np.int64),
        accepted_iteration_count=np.asarray(int(accepted_iteration_count), dtype=np.int64),
        source_checkpoint_path=np.asarray(str(source_checkpoint_npz)),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": "mgt-direct-residual-newton-state.v1",
        "load_scale": load_scale,
        "dof_count": int(final_np.size),
        "residual_inf_n": final_residual_inf,
        "direct_residual_inf_n": final_residual_inf,
        "direct_relative_residual_inf": final_residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_iteration_count": int(accepted_iteration_count),
        "accepted_history_count": int(state_history.shape[0]),
        "source_checkpoint_path": str(source_checkpoint_npz),
    }


def diagonal_jacobi_correction(
    *,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    rhs = -np.asarray(residual, dtype=np.float64)
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
    abs_diag = np.abs(diag)
    positive = abs_diag[abs_diag > 0.0]
    floor = max(float(np.median(positive)) * 1.0e-12 if positive.size else 0.0, 1.0e-12)
    safe_diag = np.where(abs_diag >= floor, diag, np.where(diag < 0.0, -floor, floor))
    delta_free = rhs / safe_diag
    delta = np.zeros(int(stiffness.shape[0]), dtype=np.float64)
    delta[free_idx] = delta_free
    return delta, {
        "correction_mode": "diagonal_jacobi",
        "diag_abs_min": float(np.min(abs_diag)) if abs_diag.size else 0.0,
        "diag_abs_median": float(np.median(abs_diag)) if abs_diag.size else 0.0,
        "diag_abs_max": float(np.max(abs_diag)) if abs_diag.size else 0.0,
        "diag_floor": float(floor),
        "zero_or_tiny_diag_count": int(np.sum(abs_diag < floor)),
        "correction_inf_m": _max_abs(delta),
    }


def node_block_jacobi_correction(
    *,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    rhs = -np.asarray(residual, dtype=np.float64)
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
    started = time.perf_counter()
    block_inverse, block_meta = build_node_block_jacobi_preconditioner(
        k_ff,
        free_global_dofs=free_idx,
    )
    delta_free = np.asarray(block_inverse @ rhs, dtype=np.float64)
    delta = np.zeros(int(stiffness.shape[0]), dtype=np.float64)
    delta[free_idx] = delta_free
    return delta, {
        "correction_mode": "node_block_jacobi",
        "preconditioner_build_seconds": block_meta.get("build_seconds"),
        "preconditioner_total_seconds": time.perf_counter() - started,
        "preconditioner_singular_block_count": block_meta.get("singular_block_count"),
        "preconditioner_block_count": block_meta.get("block_count"),
        "correction_inf_m": _max_abs(delta),
    }


def evaluate_correction_line_search(
    *,
    base_u: np.ndarray,
    base_free: np.ndarray,
    base_residual_inf: float,
    delta: np.ndarray,
    assemble_residual: Any,
    alpha_values: tuple[float, ...],
) -> dict[str, Any]:
    base = np.asarray(base_u, dtype=np.float64)
    free0 = np.asarray(base_free, dtype=np.int64)
    rows: list[dict[str, Any]] = []
    for alpha in alpha_values:
        candidate = base + float(alpha) * np.asarray(delta, dtype=np.float64)
        _k, _f_ext, free, residual, rhs, _meta = assemble_residual(candidate)
        free_np = np.asarray(free, dtype=np.int64)
        residual_inf = _max_abs(residual)
        rhs_inf = _max_abs(rhs)
        free_stable = bool(free_np.shape == free0.shape and np.array_equal(free_np, free0))
        increment_inf = _max_abs(float(alpha) * np.asarray(delta, dtype=np.float64))
        rows.append(
            {
                "alpha": float(alpha),
                "residual_inf_n": residual_inf,
                "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "rhs_inf_n": rhs_inf,
                "free_dof_set_stable": free_stable,
                "increment_inf_m": increment_inf,
                "candidate_max_abs_displacement_m": _max_abs(candidate),
            }
        )
    best = min(
        (row for row in rows if bool(row.get("free_dof_set_stable"))),
        key=lambda row: _float_or_inf(row.get("residual_inf_n")),
        default={},
    )
    best_residual = _float_or_inf(best.get("residual_inf_n"))
    return {
        "alpha_values": [float(value) for value in alpha_values],
        "trial_rows": rows,
        "best_alpha": best.get("alpha"),
        "best_residual_inf_n": best.get("residual_inf_n"),
        "best_relative_residual_inf": best.get("relative_residual_inf"),
        "best_candidate_max_abs_displacement_m": best.get("candidate_max_abs_displacement_m"),
        "residual_descent": bool(best_residual < float(base_residual_inf)),
        "improvement_inf_n": float(base_residual_inf) - best_residual
        if np.isfinite(best_residual)
        else 0.0,
        "relative_improvement": (
            (float(base_residual_inf) - best_residual) / max(float(base_residual_inf), 1.0)
            if np.isfinite(best_residual)
            else 0.0
        ),
    }


def run_iterative_preconditioned_search(
    *,
    u0: np.ndarray,
    assemble_residual: Any,
    mode: str,
    alpha_values: tuple[float, ...],
    max_iterations: int,
) -> dict[str, Any]:
    current_u = np.asarray(u0, dtype=np.float64).copy()
    iteration_rows: list[dict[str, Any]] = []
    final_residual_inf = float("inf")
    for iteration in range(1, max(int(max_iterations), 0) + 1):
        stiffness, _f_ext, free, residual, rhs, _meta = assemble_residual(current_u)
        base_residual_inf = _max_abs(residual)
        final_residual_inf = base_residual_inf
        builder = (
            node_block_jacobi_correction
            if str(mode) == "node_block_jacobi"
            else diagonal_jacobi_correction
        )
        delta, correction_meta = builder(
            stiffness=stiffness,
            free=np.asarray(free, dtype=np.int64),
            residual=np.asarray(residual, dtype=np.float64),
        )
        trial_rows: list[dict[str, Any]] = []
        best_candidate = current_u
        best_row: dict[str, Any] = {}
        best_residual = base_residual_inf
        free0 = np.asarray(free, dtype=np.int64)
        for alpha in alpha_values:
            candidate = current_u + float(alpha) * delta
            _k, _f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(candidate)
            trial_free_np = np.asarray(trial_free, dtype=np.int64)
            free_stable = bool(
                trial_free_np.shape == free0.shape and np.array_equal(trial_free_np, free0)
            )
            residual_inf = _max_abs(trial_residual)
            rhs_inf = _max_abs(trial_rhs)
            row = {
                "alpha": float(alpha),
                "residual_inf_n": residual_inf,
                "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "free_dof_set_stable": free_stable,
                "candidate_max_abs_displacement_m": _max_abs(candidate),
            }
            trial_rows.append(row)
            if free_stable and residual_inf < best_residual:
                best_residual = residual_inf
                best_candidate = candidate
                best_row = row
        accepted = bool(best_residual < base_residual_inf)
        iteration_rows.append(
            {
                "iteration": int(iteration),
                "mode": str(mode),
                "base_residual_inf_n": base_residual_inf,
                "best_alpha": best_row.get("alpha"),
                "best_residual_inf_n": best_residual,
                "relative_improvement": (
                    (base_residual_inf - best_residual) / max(base_residual_inf, 1.0)
                ),
                "accepted": accepted,
                "correction_inf_m": correction_meta.get("correction_inf_m"),
                "trial_rows": trial_rows,
            }
        )
        if not accepted:
            break
        current_u = np.asarray(best_candidate, dtype=np.float64)
        final_residual_inf = best_residual
    return {
        "enabled": bool(max(int(max_iterations), 0) > 0),
        "mode": str(mode),
        "max_iterations": int(max_iterations),
        "alpha_values": [float(value) for value in alpha_values],
        "iteration_rows": iteration_rows,
        "accepted_iteration_count": sum(1 for row in iteration_rows if bool(row.get("accepted"))),
        "final_residual_inf_n": final_residual_inf,
        "final_max_abs_displacement_m": _max_abs(current_u),
        "residual_gate_passed": bool(final_residual_inf <= 5.0e-4),
        "_final_u": current_u,
    }


def run_mgt_equilibrium_preconditioned_zero_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    output_final_checkpoint_npz: Path | None = DEFAULT_FINAL_CHECKPOINT,
    start_mode: str = "zero",
    alpha_values: tuple[float, ...] = (0.0, 1.0, 0.5, 0.25, 0.125, 0.0625, 0.01),
    iterative_mode: str = "node_block_jacobi",
    iterative_alpha_values: tuple[float, ...] = (0.0, -1.0, -0.5, -0.25, -0.0625),
    max_iterative_corrections: int = 0,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    checkpoint_meta, _loaded_u, loaded_state_history, loaded_residual_history = _load_checkpoint(
        checkpoint_npz
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    _k_bad, _f_bad, _free_bad, bad_residual, _rhs_bad, _bad_meta = assemble_residual(u0)
    mode = str(start_mode or "zero").strip().lower()
    if mode not in {"zero", "checkpoint"}:
        raise ValueError("start_mode must be 'zero' or 'checkpoint'")
    start_u = np.zeros_like(u0) if mode == "zero" else np.asarray(u0, dtype=np.float64).copy()
    zero_started = time.perf_counter()
    stiffness, _f_ext, free, residual, rhs, meta = assemble_residual(start_u)
    zero_assembly_seconds = time.perf_counter() - zero_started
    base_residual_inf = _max_abs(residual)
    correction_rows: list[dict[str, Any]] = []
    for name, builder in (
        ("diagonal_jacobi", diagonal_jacobi_correction),
        ("node_block_jacobi", node_block_jacobi_correction),
    ):
        correction_started = time.perf_counter()
        try:
            delta, correction_meta = builder(
                stiffness=stiffness,
                free=np.asarray(free, dtype=np.int64),
                residual=np.asarray(residual, dtype=np.float64),
            )
            line_search = evaluate_correction_line_search(
                base_u=start_u,
                base_free=np.asarray(free, dtype=np.int64),
                base_residual_inf=base_residual_inf,
                delta=delta,
                assemble_residual=assemble_residual,
                alpha_values=alpha_values,
            )
            row = {
                "correction_mode": name,
                **correction_meta,
                **line_search,
                "seconds": time.perf_counter() - correction_started,
            }
        except Exception as exc:
            row = {
                "correction_mode": name,
                "failed": True,
                "error_excerpt": repr(exc)[:800],
                "seconds": time.perf_counter() - correction_started,
            }
        correction_rows.append(row)
    best_row = min(
        (
            row
            for row in correction_rows
            if row.get("best_residual_inf_n") is not None
        ),
        key=lambda row: _float_or_inf(row.get("best_residual_inf_n")),
        default={},
    )
    iterative_search = run_iterative_preconditioned_search(
        u0=start_u,
        assemble_residual=assemble_residual,
        mode=iterative_mode,
        alpha_values=iterative_alpha_values,
        max_iterations=max_iterative_corrections,
    )
    iterative_final_u = iterative_search.pop("_final_u", np.asarray(start_u, dtype=np.float64))
    iterative_final = _float_or_inf(iterative_search.get("final_residual_inf_n"))
    best_single = _float_or_inf(best_row.get("best_residual_inf_n"))
    overall_best_residual = min(best_single, iterative_final)
    overall_gate_passed = bool(overall_best_residual <= 5.0e-4)
    final_checkpoint_row: dict[str, Any] = {"written": False}
    if output_final_checkpoint_npz is not None and bool(iterative_search.get("enabled")):
        final_u_np = np.asarray(iterative_final_u, dtype=np.float64)
        _k_final, _f_final, _free_final, final_residual, final_rhs, _final_meta = (
            assemble_residual(final_u_np)
        )
        final_checkpoint_row = write_preconditioned_checkpoint(
            path=output_final_checkpoint_npz,
            source_checkpoint_npz=checkpoint_npz,
            source_checkpoint_meta=checkpoint_meta,
            start_u=start_u,
            final_u=final_u_np,
            start_residual=np.asarray(residual, dtype=np.float64),
            final_residual=np.asarray(final_residual, dtype=np.float64),
            final_rhs=np.asarray(final_rhs, dtype=np.float64),
            loaded_state_history=loaded_state_history,
            loaded_residual_history=loaded_residual_history,
            accepted_iteration_count=int(iterative_search.get("accepted_iteration_count") or 0),
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if best_row else "partial",
        "checkpoint": setup_meta.get("checkpoint"),
        "load_scale": setup_meta.get("load_scale"),
        "start_mode": mode,
        "checkpoint_residual_inf_n": _max_abs(bad_residual),
        "start_state_residual_inf_n": base_residual_inf,
        "start_state_relative_residual_inf": base_residual_inf / max(_max_abs(rhs), 1.0),
        "start_state_rhs_inf_n": _max_abs(rhs),
        "start_state_max_abs_displacement_m": _max_abs(start_u),
        "zero_state_residual_inf_n": base_residual_inf,
        "zero_state_relative_residual_inf": base_residual_inf / max(_max_abs(rhs), 1.0),
        "zero_state_rhs_inf_n": _max_abs(rhs),
        "free_dof_count": int(np.asarray(free).size),
        "zero_state_meta": {
            "physical_internal_force_model": meta.get("physical_internal_force_model"),
            "newton_tangent_model": meta.get("newton_tangent_model"),
            "equilibrium_geometry_contract": meta.get("equilibrium_geometry_contract"),
            "stiffness_unit_audit": meta.get("stiffness_unit_audit"),
        },
        "correction_rows": correction_rows,
        "iterative_search": iterative_search,
        "output_final_checkpoint": final_checkpoint_row,
        "best_correction_mode": best_row.get("correction_mode"),
        "best_residual_inf_n": best_row.get("best_residual_inf_n"),
        "best_relative_improvement": best_row.get("relative_improvement"),
        "overall_best_residual_inf_n": overall_best_residual,
        "overall_residual_gate_passed": overall_gate_passed,
        "residual_tolerance_n": 5.0e-4,
        "residual_gate_passed": bool(
            overall_gate_passed
        ),
        "runtime_metrics": {
            "setup_and_bad_checkpoint_seconds": zero_started - started,
            "zero_assembly_seconds": zero_assembly_seconds,
            "total_seconds": time.perf_counter() - started,
        },
        "claim_boundary": (
            "Diagnostic-only cheap correction from the zero state. It tests diagonal and nodal-block "
            "preconditioned one-shot directions with residual replay, but it is not full Newton closure "
            "unless the residual gate passes."
        ),
        "blockers": []
        if overall_gate_passed
        else ["preconditioned_zero_residual_gate_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=DEFAULT_FINAL_CHECKPOINT)
    parser.add_argument(
        "--start-mode",
        choices=("zero", "checkpoint"),
        default="zero",
        help="Start correction from zero displacement or from checkpoint displacement.",
    )
    parser.add_argument(
        "--alphas",
        default="0,1,0.5,0.25,0.125,0.0625,0.01",
        help="Comma-separated line-search alpha values for each cheap correction.",
    )
    parser.add_argument(
        "--iterative-mode",
        choices=("node_block_jacobi", "diagonal_jacobi"),
        default="node_block_jacobi",
    )
    parser.add_argument(
        "--iterative-alphas",
        default="0,-1,-0.5,-0.25,-0.0625",
        help="Comma-separated signed alpha values for iterative cheap correction.",
    )
    parser.add_argument("--max-iterative-corrections", type=int, default=0)
    args = parser.parse_args()
    alpha_values = tuple(
        float(value.strip())
        for value in str(args.alphas).split(",")
        if value.strip()
    )
    payload = run_mgt_equilibrium_preconditioned_zero_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        start_mode=str(args.start_mode),
        alpha_values=alpha_values,
        iterative_mode=str(args.iterative_mode),
        iterative_alpha_values=tuple(
            float(value.strip())
            for value in str(args.iterative_alphas).split(",")
            if value.strip()
        ),
        max_iterative_corrections=int(args.max_iterative_corrections),
    )
    print(
        "mgt-equilibrium-preconditioned-zero:",
        payload.get("status"),
        f"zero={payload.get('zero_state_residual_inf_n')}",
        f"best={payload.get('overall_best_residual_inf_n')}",
        "->",
        args.output_json,
    )
    return 0 if payload.get("status") == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
