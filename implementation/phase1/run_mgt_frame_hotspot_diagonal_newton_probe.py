#!/usr/bin/env python3
"""Promote a gate-eligible diagonal Newton correction on frame residual hotspots."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    SCHEMA_VERSION as DIRECT_SCHEMA_VERSION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_residual_jacobian_consistency_probe import (  # noqa: E402
    _component_breakdown,
    _hotspot_diagonal_newton_sweep,
    _hotspot_signed_displacement_sweep,
    _max_abs,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-frame-hotspot-diagonal-newton-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_frame_hotspot_diagonal_newton_probe.json"
DEFAULT_CHECKPOINT_OUT = (
    PRODUCTIZATION / "mgt_frame_hotspot_diagonal_newton_probe_final_checkpoint.npz"
)


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


def _write_checkpoint(
    *,
    path: Path,
    source_checkpoint_npz: Path,
    checkpoint_meta: dict[str, Any],
    u0: np.ndarray,
    final_u: np.ndarray,
    base_residual: np.ndarray,
    final_residual: np.ndarray,
    rhs: np.ndarray,
    loaded_state_history: np.ndarray | None,
    loaded_residual_history: np.ndarray | None,
    accepted_state_rows: list[np.ndarray] | None = None,
    accepted_residual_rows: list[np.ndarray] | None = None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    state_rows: list[np.ndarray] = []
    if (
        loaded_state_history is not None
        and loaded_state_history.ndim == 2
        and loaded_state_history.shape[1] == final_u.size
    ):
        state_rows = [np.asarray(row, dtype=np.float64).copy() for row in loaded_state_history]
    if not state_rows or not _same_state_exact(state_rows[-1], u0):
        state_rows.append(np.asarray(u0, dtype=np.float64).copy())

    residual_rows: list[np.ndarray] = []
    if (
        loaded_residual_history is not None
        and loaded_residual_history.ndim == 2
        and loaded_residual_history.shape[1] == final_residual.size
    ):
        residual_rows = [
            np.asarray(row, dtype=np.float64).copy() for row in loaded_residual_history
        ]
    while len(residual_rows) < len(state_rows):
        residual_rows.append(np.asarray(base_residual, dtype=np.float64).copy())

    new_states = accepted_state_rows or [np.asarray(final_u, dtype=np.float64)]
    new_residuals = accepted_residual_rows or [np.asarray(final_residual, dtype=np.float64)]
    for state_row, residual_row in zip(new_states, new_residuals, strict=False):
        state_arr = np.asarray(state_row, dtype=np.float64).copy()
        residual_arr = np.asarray(residual_row, dtype=np.float64).copy()
        if state_rows and _same_state_exact(state_rows[-1], state_arr):
            if residual_rows:
                residual_rows[-1] = residual_arr
            else:
                residual_rows.append(residual_arr)
            continue
        state_rows.append(state_arr)
        residual_rows.append(residual_arr)

    if not state_rows or not _same_state_exact(state_rows[-1], final_u):
        state_rows.append(np.asarray(final_u, dtype=np.float64).copy())
        residual_rows.append(np.asarray(final_residual, dtype=np.float64).copy())
    elif residual_rows:
        residual_rows[-1] = np.asarray(final_residual, dtype=np.float64).copy()

    state_history = np.vstack(state_rows)
    residual_history = np.vstack(residual_rows)
    final_residual_inf = _max_abs(final_residual)
    rhs_inf = _max_abs(rhs)
    translation = _translation_metrics(final_u)
    load_scale = float(checkpoint_meta["load_scale"])
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        source_schema_version=np.asarray(DIRECT_SCHEMA_VERSION),
        promotion_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(load_scale, dtype=np.float64),
        displacement_u=np.asarray(final_u, dtype=np.float64),
        residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(final_residual_inf / max(rhs_inf, 1.0)),
        max_translation_m=np.asarray(translation["max_translation_m"], dtype=np.float64),
        accepted_state_history_u=state_history,
        accepted_residual_history=residual_history,
        accepted_history_count=np.asarray(state_history.shape[0], dtype=np.int64),
        source_checkpoint_path=np.asarray(str(source_checkpoint_npz)),
    )
    return {
        "path": str(path),
        "schema": "mgt-direct-residual-newton-state.v1",
        "load_scale": load_scale,
        "dof_count": int(final_u.size),
        "direct_residual_inf_n": final_residual_inf,
        "direct_relative_residual_inf": final_residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_history_count": int(state_history.shape[0]),
        "source_checkpoint_path": str(source_checkpoint_npz),
    }


def _diagonal_hotspot_correction_vector(
    *,
    sweep: dict[str, Any],
    dof_count: int,
) -> np.ndarray:
    correction = np.zeros(int(dof_count), dtype=np.float64)
    for row in sweep.get("selected_corrections", []):
        if not isinstance(row, dict):
            continue
        global_dof = int(row.get("global_dof", -1))
        if 0 <= global_dof < correction.size:
            correction[global_dof] = float(row.get("unit_alpha_correction_m") or 0.0)
    return correction


def _signed_hotspot_direction_vector(
    *,
    top_rows: list[dict[str, Any]],
    dof_count: int,
) -> np.ndarray:
    direction = np.zeros(int(dof_count), dtype=np.float64)
    for row in top_rows:
        if str(row.get("dominant_component") or "") != "frame":
            continue
        if str(row.get("dof") or "") not in {"ux", "uy", "uz"}:
            continue
        global_dof = int(row.get("global_dof", -1))
        if 0 <= global_dof < direction.size:
            residual_value = float(row.get("residual_n") or 0.0)
            direction[global_dof] = -float(np.sign(residual_value) or 1.0)
    direction_inf = _max_abs(direction)
    if direction_inf > 0.0:
        direction /= direction_inf
    return direction


def _block_lstsq_hotspot_correction_vector(
    *,
    sweep: dict[str, Any],
    dof_count: int,
) -> np.ndarray:
    correction = np.zeros(int(dof_count), dtype=np.float64)
    for row in sweep.get("support_corrections", []):
        if not isinstance(row, dict):
            continue
        global_dof = int(row.get("global_dof", -1))
        if 0 <= global_dof < correction.size:
            correction[global_dof] = float(row.get("correction_m") or 0.0)
    return correction


def _truncated_svd_coefficients(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    max_condition: float = 1.0e8,
) -> tuple[np.ndarray, dict[str, Any]]:
    a = np.asarray(matrix, dtype=np.float64)
    b = np.asarray(rhs, dtype=np.float64)
    column_count = int(a.shape[1]) if a.ndim == 2 else 0
    if a.ndim != 2 or b.ndim != 1 or a.shape[0] != b.shape[0] or column_count == 0:
        return np.zeros(column_count, dtype=np.float64), {
            "solve_method": "truncated_svd",
            "rank": 0,
            "singular_values": [],
            "reason": "invalid_or_empty_system",
        }
    u_svd, singular_values, vh = np.linalg.svd(a, full_matrices=False)
    spectral = float(np.max(singular_values)) if singular_values.size else 0.0
    cutoff = spectral / max(float(max_condition), 1.0) if spectral > 0.0 else 0.0
    keep = np.asarray(
        [(float(value) > cutoff and float(value) > 0.0) for value in singular_values],
        dtype=bool,
    )
    rank = int(np.count_nonzero(keep))
    if rank:
        projected = u_svd[:, keep].T @ b
        coeffs = vh[keep, :].T @ (projected / singular_values[keep])
    else:
        coeffs = np.zeros(column_count, dtype=np.float64)
    residual_vector = a @ coeffs - b
    return np.asarray(coeffs, dtype=np.float64), {
        "solve_method": "truncated_svd",
        "rank": rank,
        "singular_values": [float(value) for value in singular_values.tolist()],
        "svd_max_condition": float(max_condition),
        "svd_effective_cutoff": float(cutoff),
        "linear_residual_l2_n": float(np.linalg.norm(residual_vector))
        if residual_vector.size
        else 0.0,
    }


def _hotspot_block_lstsq_sweep(
    *,
    u: np.ndarray,
    stiffness: Any,
    free: np.ndarray,
    top_rows: list[dict[str, Any]],
    assemble_residual: Any,
    alpha_values: tuple[float, ...],
    relative_increment_tolerance: float = 1.0e-4,
    residual_tolerance_n: float = 1.0e-3,
    max_rows: int = 8,
    support_columns_per_row: int = 8,
    svd_max_condition: float = 1.0e8,
    include_gate_limited_alpha: bool = False,
) -> dict[str, Any]:
    base_u = np.asarray(u, dtype=np.float64)
    free_idx = np.asarray(free, dtype=np.int64)
    _base_k, _base_f, base_free, base_residual, base_rhs, _base_meta = assemble_residual(
        base_u
    )
    base_free_idx = np.asarray(base_free, dtype=np.int64)
    free_stable = bool(
        base_free_idx.shape == free_idx.shape and np.array_equal(base_free_idx, free_idx)
    )
    if not free_stable:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "base_free_dof_set_changed",
            "candidate_rows": [],
            "best_candidate": {},
            "best_gate_eligible_candidate": {},
        }
    local_row_by_global = {
        int(global_dof): int(local_row)
        for local_row, global_dof in enumerate(free_idx.tolist())
    }
    selected_rows: list[dict[str, Any]] = []
    selected_local_rows: list[int] = []
    seen: set[int] = set()
    for row in top_rows:
        if str(row.get("dominant_component") or "") != "frame":
            continue
        if str(row.get("dof") or "") not in {"ux", "uy", "uz"}:
            continue
        global_dof = int(row.get("global_dof", -1))
        if global_dof < 0 or global_dof in seen or global_dof not in local_row_by_global:
            continue
        selected_rows.append(row)
        selected_local_rows.append(int(local_row_by_global[global_dof]))
        seen.add(global_dof)
        if len(selected_rows) >= max(int(max_rows), 0):
            break
    if not selected_local_rows:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "no_frame_translation_hotspot_rows",
            "candidate_rows": [],
            "best_candidate": {},
            "best_gate_eligible_candidate": {},
        }
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
    target_rows = np.asarray(selected_local_rows, dtype=np.int64)
    support: set[int] = set(int(row) for row in target_rows.tolist())
    selected_nodes = {
        int(free_idx[int(row)]) // 6
        for row in target_rows.tolist()
        if 0 <= int(row) < int(free_idx.size)
    }
    for local_col, global_dof in enumerate(free_idx.tolist()):
        if int(global_dof) // 6 in selected_nodes and int(global_dof) % 6 in {0, 1, 2}:
            support.add(int(local_col))
    for target_row in target_rows.tolist():
        start = int(k_ff.indptr[int(target_row)])
        end = int(k_ff.indptr[int(target_row) + 1])
        cols = k_ff.indices[start:end]
        vals = np.abs(k_ff.data[start:end])
        if cols.size:
            take = min(max(int(support_columns_per_row), 0), int(cols.size))
            if take:
                strongest = np.argpartition(vals, -take)[-take:]
                support.update(int(cols[index]) for index in strongest.tolist())
    support_cols = np.asarray(sorted(support), dtype=np.int64)
    if support_cols.size == 0:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "empty_support",
            "candidate_rows": [],
            "best_candidate": {},
            "best_gate_eligible_candidate": {},
        }
    submatrix = k_ff[target_rows, :][:, support_cols].toarray()
    target_rhs = -np.asarray(base_residual, dtype=np.float64)[target_rows]
    coeffs, solve_meta = _truncated_svd_coefficients(
        submatrix,
        target_rhs,
        max_condition=svd_max_condition,
    )
    correction = np.zeros_like(base_u)
    support_corrections: list[dict[str, Any]] = []
    for local_col, coeff in zip(support_cols.tolist(), coeffs.tolist(), strict=False):
        global_dof = int(free_idx[int(local_col)])
        correction[global_dof] = float(coeff)
        support_corrections.append(
            {
                "local_col": int(local_col),
                "global_dof": global_dof,
                "node_index": int(global_dof // 6),
                "dof_index": int(global_dof % 6),
                "correction_m": float(coeff),
            }
        )
    correction_inf = _max_abs(correction)
    if correction_inf <= 0.0:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "zero_block_lstsq_correction",
            "target_rows": [int(row) for row in target_rows.tolist()],
            "support_corrections": support_corrections,
            "linear_solve": solve_meta,
            "candidate_rows": [],
            "best_candidate": {},
            "best_gate_eligible_candidate": {},
        }
    base_residual_inf = _max_abs(base_residual)
    base_rhs_inf = _max_abs(base_rhs)
    max_abs_u = max(_max_abs(base_u), 1.0e-12)
    sweep_alpha_values = [float(value) for value in alpha_values]
    if include_gate_limited_alpha and correction_inf > 0.0:
        gate_alpha = (
            float(relative_increment_tolerance) * max_abs_u / correction_inf * (1.0 - 1.0e-12)
        )
        if gate_alpha > 0.0 and all(
            abs(gate_alpha - value) > max(abs(gate_alpha), 1.0) * 1.0e-12
            for value in sweep_alpha_values
        ):
            sweep_alpha_values.append(gate_alpha)
    sweep_alpha_values = sorted(set(sweep_alpha_values), reverse=True)
    candidate_rows: list[dict[str, Any]] = []
    for alpha in sweep_alpha_values:
        alpha_float = float(alpha)
        trial_u = base_u + alpha_float * correction
        _trial_k, _trial_f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
            trial_u
        )
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        trial_free_stable = bool(
            trial_free_idx.shape == base_free_idx.shape
            and np.array_equal(trial_free_idx, base_free_idx)
        )
        residual_inf = _max_abs(trial_residual)
        rhs_inf = _max_abs(trial_rhs)
        relative_increment = abs(alpha_float) * correction_inf / max_abs_u
        candidate_rows.append(
            {
                "alpha": alpha_float,
                "free_dof_set_stable": trial_free_stable,
                "direct_residual_inf_n": residual_inf,
                "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "improvement_inf_n": base_residual_inf - residual_inf,
                "relative_improvement": (base_residual_inf - residual_inf)
                / max(base_residual_inf, 1.0),
                "relative_increment": relative_increment,
                "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                "relative_increment_gate_passed": relative_increment
                <= float(relative_increment_tolerance),
            }
        )
    best_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    best_gate_eligible_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    return {
        "enabled": True,
        "evaluated": True,
        "direction": "block_lstsq_on_frame_translation_hotspots",
        "selected_hotspot_row_count": int(len(selected_rows)),
        "target_rows": [int(row) for row in target_rows.tolist()],
        "target_global_dofs": [int(free_idx[int(row)]) for row in target_rows.tolist()],
        "support_size": int(support_cols.size),
        "support_columns_per_row": int(support_columns_per_row),
        "include_gate_limited_alpha": bool(include_gate_limited_alpha),
        "base_direct_residual_inf_n": base_residual_inf,
        "base_relative_residual_inf": base_residual_inf / max(base_rhs_inf, 1.0),
        "correction_inf_m": correction_inf,
        "linear_solve": solve_meta,
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "residual_tolerance_n": float(residual_tolerance_n),
        "support_corrections": support_corrections,
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate,
        "best_gate_eligible_candidate": best_gate_eligible_candidate,
    }


def run_mgt_frame_hotspot_diagonal_newton_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    output_final_checkpoint_npz: Path | None = DEFAULT_CHECKPOINT_OUT,
    alpha_values: tuple[float, ...] = (1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.001),
    step_values: tuple[float, ...] = (1.0e-10, 3.0e-10, 1.0e-9),
    max_rows: int = 8,
    max_promotions: int = 1,
    promotion_mode: str = "diagonal_newton",
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
    block_lstsq_support_columns_per_row: int = 8,
    block_lstsq_svd_max_condition: float = 1.0e8,
    block_lstsq_include_gate_limited_alpha: bool = False,
    write_progress_artifacts: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    checkpoint_meta, loaded_u, loaded_state_history, loaded_residual_history = _load_checkpoint(
        checkpoint_npz
    )
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    if not np.allclose(u0, loaded_u):
        raise ValueError("checkpoint displacement mismatch between loaders")
    current_u = np.asarray(u0, dtype=np.float64).copy()
    promotion_passes: list[dict[str, Any]] = []
    accepted_state_rows: list[np.ndarray] = []
    accepted_residual_rows: list[np.ndarray] = []
    last_sweep: dict[str, Any] = {}
    last_component_breakdown: dict[str, Any] = {}
    initial_component_breakdown: dict[str, Any] = {}
    initial_residual = np.asarray([], dtype=np.float64)
    initial_rhs = np.asarray([], dtype=np.float64)
    previous_free: np.ndarray | None = None
    final_free_stable = True
    stop_reason = "max_promotions_exhausted"
    promotion_mode = str(promotion_mode)
    if promotion_mode not in {"diagonal_newton", "signed_displacement", "block_lstsq"}:
        raise ValueError(f"unsupported promotion_mode: {promotion_mode}")

    for pass_index in range(max(int(max_promotions), 0)):
        stiffness, _f_ext, free, residual, rhs, meta = assemble_residual(
            current_u,
            include_component_forces=True,
        )
        free_idx = np.asarray(free, dtype=np.int64)
        if previous_free is not None:
            final_free_stable = bool(
                free_idx.shape == previous_free.shape and np.array_equal(free_idx, previous_free)
            )
            if not final_free_stable:
                stop_reason = "free_dof_set_changed_before_pass"
                break
        previous_free = free_idx.copy()
        residual = np.asarray(residual, dtype=np.float64)
        rhs = np.asarray(rhs, dtype=np.float64)
        if pass_index == 0:
            initial_residual = residual.copy()
            initial_rhs = rhs.copy()
        component_forces = meta.pop("component_forces", {})
        component_breakdown = _component_breakdown(
            component_forces=component_forces if isinstance(component_forces, dict) else {},
            free=free_idx,
            residual=residual,
            rhs=rhs,
        )
        if pass_index == 0:
            initial_component_breakdown = component_breakdown
        last_component_breakdown = component_breakdown
        if promotion_mode == "diagonal_newton":
            sweep = _hotspot_diagonal_newton_sweep(
                u=current_u,
                stiffness=stiffness,
                free=free_idx,
                top_rows=component_breakdown.get("top_rows", []),
                assemble_residual=assemble_residual,
                alpha_values=alpha_values,
                relative_increment_tolerance=relative_increment_tolerance,
                residual_tolerance_n=residual_tolerance_n,
                max_rows=max_rows,
            )
        elif promotion_mode == "signed_displacement":
            sweep = _hotspot_signed_displacement_sweep(
                u=current_u,
                free=free_idx,
                top_rows=component_breakdown.get("top_rows", []),
                assemble_residual=assemble_residual,
                step_values=step_values,
                relative_increment_tolerance=relative_increment_tolerance,
                residual_tolerance_n=residual_tolerance_n,
            )
        else:
            sweep = _hotspot_block_lstsq_sweep(
                u=current_u,
                stiffness=stiffness,
                free=free_idx,
                top_rows=component_breakdown.get("top_rows", []),
                assemble_residual=assemble_residual,
                alpha_values=alpha_values,
                relative_increment_tolerance=relative_increment_tolerance,
                residual_tolerance_n=residual_tolerance_n,
                max_rows=max_rows,
                support_columns_per_row=block_lstsq_support_columns_per_row,
                svd_max_condition=block_lstsq_svd_max_condition,
                include_gate_limited_alpha=block_lstsq_include_gate_limited_alpha,
            )
        last_sweep = sweep
        base_residual_inf = _max_abs(residual)
        promotion_candidate = sweep.get("best_gate_eligible_candidate")
        promotion_candidate = promotion_candidate if isinstance(promotion_candidate, dict) else {}
        candidate_residual_inf = float(
            promotion_candidate.get("direct_residual_inf_n") or float("inf")
        )
        if not promotion_candidate or candidate_residual_inf >= base_residual_inf:
            stop_reason = "no_gate_eligible_descent"
            break

        if promotion_mode == "diagonal_newton":
            correction = _diagonal_hotspot_correction_vector(
                sweep=sweep,
                dof_count=current_u.size,
            )
            scale_value = float(promotion_candidate["alpha"])
            correction_inf = _max_abs(correction)
            trial_u = current_u + scale_value * correction
            step_m = None
            alpha = scale_value
        elif promotion_mode == "signed_displacement":
            correction = _signed_hotspot_direction_vector(
                top_rows=component_breakdown.get("top_rows", []),
                dof_count=current_u.size,
            )
            step_m = float(promotion_candidate["step_m"])
            alpha = None
            correction_inf = abs(step_m) * _max_abs(correction)
            trial_u = current_u + step_m * correction
        else:
            correction = _block_lstsq_hotspot_correction_vector(
                sweep=sweep,
                dof_count=current_u.size,
            )
            scale_value = float(promotion_candidate["alpha"])
            correction_inf = _max_abs(correction)
            trial_u = current_u + scale_value * correction
            step_m = None
            alpha = scale_value
        if correction_inf <= 0.0:
            stop_reason = "zero_hotspot_correction"
            break
        _trial_k, _trial_f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
            trial_u
        )
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        trial_free_stable = bool(
            trial_free_idx.shape == free_idx.shape and np.array_equal(trial_free_idx, free_idx)
        )
        trial_residual = np.asarray(trial_residual, dtype=np.float64)
        trial_rhs = np.asarray(trial_rhs, dtype=np.float64)
        trial_residual_inf = _max_abs(trial_residual)
        pass_row = {
            "pass_index": pass_index,
            "base_direct_residual_inf_n": base_residual_inf,
            "candidate_direct_residual_inf_n": candidate_residual_inf,
            "actual_direct_residual_inf_n": trial_residual_inf,
            "direct_relative_residual_inf": trial_residual_inf / max(_max_abs(trial_rhs), 1.0),
            "improvement_inf_n": base_residual_inf - trial_residual_inf,
            "relative_improvement": (base_residual_inf - trial_residual_inf)
            / max(base_residual_inf, 1.0),
            "alpha": alpha,
            "step_m": step_m,
            "relative_increment": float(promotion_candidate.get("relative_increment") or 0.0),
            "relative_increment_gate_passed": bool(
                promotion_candidate.get("relative_increment_gate_passed")
            ),
            "residual_gate_passed": trial_residual_inf <= float(residual_tolerance_n),
            "free_dof_set_stable": trial_free_stable,
            "selected_hotspot_row_count": sweep.get("selected_hotspot_row_count"),
            "correction_inf_m": correction_inf,
        }
        if not trial_free_stable:
            promotion_passes.append(pass_row)
            final_free_stable = False
            stop_reason = "free_dof_set_changed_after_trial"
            break
        if trial_residual_inf >= base_residual_inf:
            promotion_passes.append(pass_row)
            stop_reason = "actual_candidate_not_descent"
            break
        promotion_passes.append(pass_row)
        current_u = trial_u
        accepted_state_rows.append(current_u.copy())
        accepted_residual_rows.append(trial_residual.copy())
        if (
            write_progress_artifacts
            and output_json is not None
            and output_final_checkpoint_npz is not None
        ):
            progress_checkpoint_meta = _write_checkpoint(
                path=output_final_checkpoint_npz,
                source_checkpoint_npz=checkpoint_npz,
                checkpoint_meta=checkpoint_meta,
                u0=u0,
                final_u=current_u,
                base_residual=np.asarray(initial_residual, dtype=np.float64),
                final_residual=np.asarray(trial_residual, dtype=np.float64),
                rhs=np.asarray(trial_rhs, dtype=np.float64),
                loaded_state_history=loaded_state_history,
                loaded_residual_history=loaded_residual_history,
                accepted_state_rows=accepted_state_rows,
                accepted_residual_rows=accepted_residual_rows,
            )
            progress_payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "partial",
                "direct_residual_newton_ready": False,
                "checkpoint": checkpoint_meta,
                "base_direct_residual": {
                    "direct_residual_inf_n": _max_abs(initial_residual),
                    "direct_relative_residual_inf": _max_abs(initial_residual)
                    / max(_max_abs(initial_rhs), 1.0),
                    "rhs_inf_n": _max_abs(initial_rhs),
                },
                "final_direct_residual": {
                    "direct_residual_inf_n": trial_residual_inf,
                    "direct_relative_residual_inf": trial_residual_inf
                    / max(_max_abs(trial_rhs), 1.0),
                    "rhs_inf_n": _max_abs(trial_rhs),
                    "free_dof_set_stable": trial_free_stable,
                    "improvement_inf_n": _max_abs(initial_residual) - trial_residual_inf,
                    "relative_improvement": (
                        _max_abs(initial_residual) - trial_residual_inf
                    )
                    / max(_max_abs(initial_residual), 1.0),
                },
                "promotion_mode": promotion_mode,
                "promoted_to_final_state": True,
                "promotion_count": len(promotion_passes),
                "max_promotions": int(max_promotions),
                "stop_reason": "progress_artifact_after_accepted_pass",
                "promotion_passes": promotion_passes,
                "promotion_candidate": {
                    "alpha": pass_row["alpha"],
                    "step_m": pass_row["step_m"],
                    "direct_residual_inf_n": pass_row["actual_direct_residual_inf_n"],
                    "direct_relative_residual_inf": pass_row[
                        "direct_relative_residual_inf"
                    ],
                    "improvement_inf_n": pass_row["improvement_inf_n"],
                    "relative_improvement": pass_row["relative_improvement"],
                    "relative_increment": pass_row["relative_increment"],
                    "residual_gate_passed": pass_row["residual_gate_passed"],
                    "relative_increment_gate_passed": pass_row[
                        "relative_increment_gate_passed"
                    ],
                },
                "output_final_checkpoint": progress_checkpoint_meta,
                "runtime_metrics": {"total_seconds": time.perf_counter() - started},
                "claim_boundary": (
                    "Progress artifact written after an accepted promotion pass. "
                    "This is not final nonlinear residual closure."
                ),
                "blockers": [
                    "direct_residual_gate_not_closed",
                    "global_consistent_newton_or_load_path_required",
                ],
            }
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(
                json.dumps(progress_payload, indent=2, ensure_ascii=False, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
        if trial_residual_inf <= float(residual_tolerance_n):
            stop_reason = "direct_residual_gate_closed"
            break
    else:
        if int(max_promotions) <= 0:
            stop_reason = "max_promotions_zero"

    if initial_residual.size == 0:
        _k0, _f0, free0, initial_residual, initial_rhs, meta0 = assemble_residual(
            current_u,
            include_component_forces=True,
        )
        previous_free = np.asarray(free0, dtype=np.int64)
        component_forces0 = meta0.pop("component_forces", {})
        initial_component_breakdown = _component_breakdown(
            component_forces=component_forces0 if isinstance(component_forces0, dict) else {},
            free=previous_free,
            residual=np.asarray(initial_residual, dtype=np.float64),
            rhs=np.asarray(initial_rhs, dtype=np.float64),
        )
        last_component_breakdown = initial_component_breakdown
    _final_k, _final_f, final_free, final_residual, final_rhs, final_meta = assemble_residual(current_u)
    final_free_idx = np.asarray(final_free, dtype=np.int64)
    final_free_stable = bool(
        final_free_stable
        and previous_free is not None
        and final_free_idx.shape == previous_free.shape
        and np.array_equal(final_free_idx, previous_free)
    )
    base_residual_inf = _max_abs(initial_residual)
    final_residual_inf = _max_abs(final_residual)
    promoted = bool(promotion_passes and promotion_passes[-1]["actual_direct_residual_inf_n"] < base_residual_inf)
    promotion_candidate = (
        {
            "alpha": promotion_passes[-1]["alpha"],
            "step_m": promotion_passes[-1]["step_m"],
            "direct_residual_inf_n": promotion_passes[-1]["actual_direct_residual_inf_n"],
            "direct_relative_residual_inf": promotion_passes[-1][
                "direct_relative_residual_inf"
            ],
            "improvement_inf_n": promotion_passes[-1]["improvement_inf_n"],
            "relative_improvement": promotion_passes[-1]["relative_improvement"],
            "relative_increment": promotion_passes[-1]["relative_increment"],
            "residual_gate_passed": promotion_passes[-1]["residual_gate_passed"],
            "relative_increment_gate_passed": promotion_passes[-1][
                "relative_increment_gate_passed"
            ],
        }
        if promotion_passes
        else {}
    )
    output_checkpoint_meta = None
    if output_final_checkpoint_npz is not None and promoted and final_free_stable:
        output_checkpoint_meta = _write_checkpoint(
            path=output_final_checkpoint_npz,
            source_checkpoint_npz=checkpoint_npz,
            checkpoint_meta=checkpoint_meta,
            u0=u0,
            final_u=current_u,
            base_residual=np.asarray(initial_residual, dtype=np.float64),
            final_residual=np.asarray(final_residual, dtype=np.float64),
            rhs=np.asarray(final_rhs, dtype=np.float64),
            loaded_state_history=loaded_state_history,
            loaded_residual_history=loaded_residual_history,
            accepted_state_rows=accepted_state_rows,
            accepted_residual_rows=accepted_residual_rows,
        )
    ready = bool(
        promoted
        and final_residual_inf <= residual_tolerance_n
        and bool(promotion_candidate.get("relative_increment_gate_passed"))
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "partial",
        "direct_residual_newton_ready": ready,
        "checkpoint": checkpoint_meta,
        "base_direct_residual": {
            "direct_residual_inf_n": base_residual_inf,
            "direct_relative_residual_inf": base_residual_inf / max(_max_abs(initial_rhs), 1.0),
            "rhs_inf_n": _max_abs(initial_rhs),
        },
        "final_direct_residual": {
            "direct_residual_inf_n": final_residual_inf,
            "direct_relative_residual_inf": final_residual_inf / max(_max_abs(final_rhs), 1.0),
            "rhs_inf_n": _max_abs(final_rhs),
            "free_dof_set_stable": final_free_stable,
            "improvement_inf_n": base_residual_inf - final_residual_inf,
            "relative_improvement": (base_residual_inf - final_residual_inf)
            / max(base_residual_inf, 1.0),
        },
        "component_breakdown": initial_component_breakdown,
        "last_component_breakdown": last_component_breakdown,
        "frame_hotspot_diagonal_newton_sweep": (
            last_sweep if promotion_mode == "diagonal_newton" else {}
        ),
        "frame_hotspot_signed_displacement_sweep": (
            last_sweep if promotion_mode == "signed_displacement" else {}
        ),
        "frame_hotspot_block_lstsq_sweep": (
            last_sweep if promotion_mode == "block_lstsq" else {}
        ),
        "promotion_mode": promotion_mode,
        "promoted_to_final_state": promoted,
        "promotion_count": len(promotion_passes),
        "max_promotions": int(max_promotions),
        "stop_reason": stop_reason,
        "promotion_passes": promotion_passes,
        "promotion_candidate": promotion_candidate,
        "output_final_checkpoint": output_checkpoint_meta,
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Promotes only a relative-increment-gate-eligible correction on frame-dominant "
            "translation residual hotspots. This is an incremental frontier advance, not "
            "full nonlinear residual closure."
        ),
        "blockers": []
        if ready
        else [
            "direct_residual_gate_not_closed",
            "global_consistent_newton_or_load_path_required",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-final-checkpoint-npz",
        type=Path,
        default=DEFAULT_CHECKPOINT_OUT,
    )
    parser.add_argument("--alpha-values", default="1,0.5,0.25,0.1,0.05,0.01,0.001")
    parser.add_argument("--step-values", default="1e-10,3e-10,1e-9")
    parser.add_argument("--max-rows", type=int, default=8)
    parser.add_argument("--max-promotions", type=int, default=1)
    parser.add_argument("--block-lstsq-support-columns-per-row", type=int, default=8)
    parser.add_argument("--block-lstsq-svd-max-condition", type=float, default=1.0e8)
    parser.add_argument("--block-lstsq-include-gate-limited-alpha", action="store_true")
    parser.add_argument("--write-progress-artifacts", action="store_true")
    parser.add_argument(
        "--promotion-mode",
        choices=("diagonal_newton", "signed_displacement", "block_lstsq"),
        default="diagonal_newton",
    )
    args = parser.parse_args(argv)
    payload = run_mgt_frame_hotspot_diagonal_newton_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        alpha_values=tuple(
            float(value.strip())
            for value in str(args.alpha_values).split(",")
            if value.strip()
        ),
        step_values=tuple(
            float(value.strip())
            for value in str(args.step_values).split(",")
            if value.strip()
        ),
        max_rows=int(args.max_rows),
        max_promotions=int(args.max_promotions),
        promotion_mode=str(args.promotion_mode),
        block_lstsq_support_columns_per_row=int(
            args.block_lstsq_support_columns_per_row
        ),
        block_lstsq_svd_max_condition=float(args.block_lstsq_svd_max_condition),
        block_lstsq_include_gate_limited_alpha=bool(
            args.block_lstsq_include_gate_limited_alpha
        ),
        write_progress_artifacts=bool(args.write_progress_artifacts),
    )
    print(
        "mgt-frame-hotspot-diagonal-newton:",
        payload["status"],
        f"base={payload['base_direct_residual']['direct_residual_inf_n']}",
        f"final={payload['final_direct_residual']['direct_residual_inf_n']}",
        "->",
        args.output_json,
    )
    return 0 if payload.get("direct_residual_newton_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
