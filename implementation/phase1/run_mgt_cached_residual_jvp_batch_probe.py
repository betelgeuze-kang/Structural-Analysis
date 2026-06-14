#!/usr/bin/env python3
"""Build a cached residual-only finite-difference JVP batch for G1 probes."""

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

from mgt_cached_residual_jvp import (  # noqa: E402
    ResidualJvpBatchCache,
    build_fd_jvp_submatrix,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_frame_hotspot_diagonal_newton_probe import (  # noqa: E402
    _equilibrate_lstsq_system,
    _expand_support_to_node_blocks,
    _ridge_coefficients,
    _select_block_lstsq_target_rows,
    _write_checkpoint,
)
from run_mgt_residual_jacobian_consistency_probe import (  # noqa: E402
    _component_breakdown,
    _max_abs,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-cached-residual-jvp-batch-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_cached_residual_jvp_batch_probe.json"


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


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


def _select_support_columns(
    *,
    stiffness: Any,
    free: np.ndarray,
    target_rows: np.ndarray,
    support_columns_per_row: int,
    node_block_support: bool,
    max_support_columns: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
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
    pre_node_block_support_size = int(support_cols.size)
    if node_block_support:
        support_cols = _expand_support_to_node_blocks(support_cols, free_idx)
    pre_trim_support_size = int(support_cols.size)
    trimmed_by_limit = False
    if max_support_columns > 0 and support_cols.size > int(max_support_columns):
        k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
        submatrix = k_ff[target_rows, :][:, support_cols].toarray()
        scores = np.linalg.norm(submatrix, axis=0)
        take = min(int(max_support_columns), int(support_cols.size))
        strongest = np.argpartition(scores, -take)[-take:]
        strongest = strongest[np.argsort(-scores[strongest], kind="stable")]
        support_cols = support_cols[strongest].astype(np.int64)
        support_cols = np.asarray(sorted(set(int(col) for col in support_cols.tolist())), dtype=np.int64)
        trimmed_by_limit = True
    return support_cols, {
        "pre_node_block_support_size": pre_node_block_support_size,
        "pre_trim_support_size": pre_trim_support_size,
        "support_size": int(support_cols.size),
        "node_block_support": bool(node_block_support),
        "support_trimmed_by_limit": bool(trimmed_by_limit),
        "max_support_columns": int(max_support_columns),
    }


def _component_block_key(row: dict[str, Any], *, key_mode: str) -> str:
    dominant = str(row.get("dominant_component") or "none")
    dof = str(row.get("dof") or "none")
    mode = str(key_mode or "dominant_component")
    if mode == "dominant_component_dof":
        return f"{dominant}:{dof}"
    if mode == "dof":
        return dof
    return dominant


def _candidate_alpha_values(
    *,
    base_alpha_values: tuple[float, ...],
    direction: np.ndarray,
    base_u: np.ndarray,
    allow_negative_alphas: bool,
    include_gate_limited_alpha: bool,
    relative_increment_tolerance: float,
    max_dynamic_alpha: float,
) -> list[float]:
    values = [float(value) for value in base_alpha_values if np.isfinite(float(value))]
    if include_gate_limited_alpha:
        direction_inf = _max_abs(direction)
        if direction_inf > 0.0:
            max_abs_u = max(_max_abs(base_u), 1.0e-12)
            gate_alpha = (
                0.95
                * float(relative_increment_tolerance)
                * max_abs_u
                / direction_inf
            )
            if np.isfinite(gate_alpha) and gate_alpha > 0.0:
                limited_alpha = min(float(gate_alpha), max(float(max_dynamic_alpha), 1.0e-30))
                values.extend([limited_alpha, 0.5 * limited_alpha, 0.1 * limited_alpha])
    positive_values = sorted(
        {
            float(value)
            for value in values
            if np.isfinite(float(value)) and float(value) > 0.0
        },
        reverse=True,
    )
    if not allow_negative_alphas:
        return positive_values
    signed_values = positive_values + [-value for value in positive_values]
    return sorted(set(signed_values), reverse=True)


def _build_component_block_basis_directions(
    *,
    fd_submatrix: np.ndarray,
    target_rhs: np.ndarray,
    support_cols: np.ndarray,
    free: np.ndarray,
    selected_rows: list[dict[str, Any]],
    key_mode: str,
    ridge_factor: float,
    normalization: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matrix = np.asarray(fd_submatrix, dtype=np.float64)
    rhs = np.asarray(target_rhs, dtype=np.float64)
    supports = np.asarray(support_cols, dtype=np.int64)
    free_idx = np.asarray(free, dtype=np.int64)
    if (
        matrix.ndim != 2
        or rhs.ndim != 1
        or matrix.shape[0] != rhs.size
        or matrix.shape[1] != supports.size
        or not selected_rows
    ):
        return [], {
            "enabled": True,
            "ready": False,
            "reason": "invalid_or_empty_jvp_system",
        }

    row_count = min(int(matrix.shape[0]), len(selected_rows))
    groups: dict[str, list[int]] = {}
    for position, row in enumerate(selected_rows[:row_count]):
        key = _component_block_key(row, key_mode=key_mode)
        groups.setdefault(key, []).append(int(position))

    block_rows: list[dict[str, Any]] = []
    block_coefficients: list[np.ndarray] = []
    block_actions: list[np.ndarray] = []
    directions: list[dict[str, Any]] = []
    normalize = str(normalization or "linf")
    if normalize not in {"none", "linf"}:
        normalize = "linf"

    for key, positions in groups.items():
        group_rows = np.asarray(positions, dtype=np.int64)
        if group_rows.size == 0:
            continue
        block_matrix = matrix[group_rows, :]
        block_rhs = rhs[group_rows]
        scaled_matrix, scaled_rhs, column_scales, equilibration_meta = (
            _equilibrate_lstsq_system(block_matrix, block_rhs, mode="row_column")
        )
        scaled_coeffs, solve_meta = _ridge_coefficients(
            scaled_matrix,
            scaled_rhs,
            ridge_factor=float(ridge_factor),
        )
        coeffs = np.asarray(scaled_coeffs, dtype=np.float64) * np.asarray(
            column_scales,
            dtype=np.float64,
        )
        coeff_inf = _max_abs(coeffs)
        if coeff_inf <= 0.0:
            block_rows.append(
                {
                    "key": key,
                    "row_count": int(group_rows.size),
                    "ready": False,
                    "reason": "zero_block_correction",
                    "linear_solve": solve_meta,
                    "equilibration": equilibration_meta,
                }
            )
            continue
        normalization_scale = coeff_inf if normalize == "linf" else 1.0
        basis_coeffs = coeffs / normalization_scale
        target_action = matrix @ basis_coeffs
        block_index = len(block_coefficients)
        block_coefficients.append(np.asarray(basis_coeffs, dtype=np.float64))
        block_actions.append(np.asarray(target_action, dtype=np.float64))
        selected_block_rows = [selected_rows[int(index)] for index in group_rows.tolist()]
        block_meta = {
            "key": key,
            "row_count": int(group_rows.size),
            "ready": True,
            "basis_index": int(block_index),
            "normalization": normalize,
            "normalization_scale": float(normalization_scale),
            "coefficient_linf_before_normalization": float(coeff_inf),
            "basis_coefficient_linf": _max_abs(basis_coeffs),
            "target_action_inf_n": _max_abs(target_action),
            "linear_solve": solve_meta,
            "equilibration": equilibration_meta,
            "target_global_dofs": [
                int(row.get("global_dof", -1)) for row in selected_block_rows
            ],
            "target_dofs": [str(row.get("dof") or "") for row in selected_block_rows],
            "dominant_components": [
                str(row.get("dominant_component") or "") for row in selected_block_rows
            ],
        }
        block_rows.append(block_meta)
        directions.append(
            {
                "source": f"component_block:{key}",
                "support_coefficients": np.asarray(coeffs, dtype=np.float64),
                "meta": {
                    **block_meta,
                    "direction_kind": "component_block_direct",
                    "coefficient_linf": _max_abs(coeffs),
                },
            }
        )

    if block_coefficients:
        basis_matrix = np.column_stack(block_actions)
        scaled_basis, scaled_rhs, basis_column_scales, basis_equilibration = (
            _equilibrate_lstsq_system(basis_matrix, rhs, mode="row_column")
        )
        scaled_gamma, basis_solve_meta = _ridge_coefficients(
            scaled_basis,
            scaled_rhs,
            ridge_factor=float(ridge_factor),
        )
        gamma = np.asarray(scaled_gamma, dtype=np.float64) * np.asarray(
            basis_column_scales,
            dtype=np.float64,
        )
        combined_support_coeffs = np.zeros(int(supports.size), dtype=np.float64)
        for value, coeffs in zip(gamma.tolist(), block_coefficients, strict=False):
            combined_support_coeffs += float(value) * np.asarray(coeffs, dtype=np.float64)
        combined_action = matrix @ combined_support_coeffs
        combined_residual = combined_action - rhs
        directions.append(
            {
                "source": "component_block_basis_combined_lstsq",
                "support_coefficients": combined_support_coeffs,
                "meta": {
                    "direction_kind": "component_block_basis_combined",
                    "basis_count": int(len(block_coefficients)),
                    "basis_keys": [str(row["key"]) for row in block_rows if row.get("ready")],
                    "basis_gamma": [float(value) for value in gamma.tolist()],
                    "coefficient_linf": _max_abs(combined_support_coeffs),
                    "target_action_inf_n": _max_abs(combined_action),
                    "linear_residual_inf_n": _max_abs(combined_residual),
                    "linear_residual_l2_n": float(np.linalg.norm(combined_residual))
                    if combined_residual.size
                    else 0.0,
                    "linear_solve": basis_solve_meta,
                    "equilibration": basis_equilibration,
                },
            }
        )

    metadata = {
        "enabled": True,
        "ready": bool(block_coefficients),
        "key_mode": str(key_mode),
        "normalization": normalize,
        "ridge_factor": float(ridge_factor),
        "target_row_count": int(row_count),
        "support_size": int(supports.size),
        "support_global_dofs": [
            int(free_idx[int(col)]) for col in supports.tolist()
        ],
        "block_count": int(len(block_coefficients)),
        "blocks": block_rows,
        "direction_count": int(len(directions)),
    }
    return directions, metadata


def _torch_rocm_lstsq_probe(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    ridge_lambda: float,
) -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "attempted": False,
            "available": False,
            "reason": f"torch_import_failed:{type(exc).__name__}",
        }
    hip_version = getattr(getattr(torch, "version", None), "hip", None)
    device = "cuda" if bool(torch.cuda.is_available()) else "cpu"
    payload: dict[str, Any] = {
        "attempted": True,
        "available": True,
        "torch_version": str(getattr(torch, "__version__", "")),
        "torch_hip_version": str(hip_version) if hip_version is not None else None,
        "device": device,
        "rocm_device_available": bool(device == "cuda" and hip_version is not None),
    }
    try:
        started = time.perf_counter()
        a = torch.as_tensor(np.asarray(matrix, dtype=np.float64), device=device)
        b = torch.as_tensor(np.asarray(rhs, dtype=np.float64), device=device)
        if ridge_lambda > 0.0:
            eye = torch.eye(a.shape[1], dtype=a.dtype, device=device) * float(ridge_lambda)
            a = torch.cat([a, eye], dim=0)
            b = torch.cat([b, torch.zeros(a.shape[1], dtype=b.dtype, device=device)])
        solution = torch.linalg.lstsq(a, b).solution
        if device == "cuda":
            torch.cuda.synchronize()
        coeffs = solution.detach().cpu().numpy()
        residual = np.asarray(matrix, dtype=np.float64) @ coeffs - np.asarray(rhs, dtype=np.float64)
        payload.update(
            {
                "ok": True,
                "solve_seconds": float(time.perf_counter() - started),
                "coefficient_linf": _max_abs(coeffs),
                "linear_residual_inf_n_unscaled": _max_abs(residual),
            }
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        payload.update({"ok": False, "reason": f"{type(exc).__name__}:{exc}"})
    return payload


def _linf_minimax_coefficients(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    coefficient_bound: float = 0.0,
    equilibration: str = "column",
) -> tuple[np.ndarray, dict[str, Any]]:
    a = np.asarray(matrix, dtype=np.float64)
    b = np.asarray(rhs, dtype=np.float64)
    column_count = int(a.shape[1]) if a.ndim == 2 else 0
    if a.ndim != 2 or b.ndim != 1 or a.shape[0] != b.shape[0] or column_count == 0:
        return np.zeros(column_count, dtype=np.float64), {
            "enabled": True,
            "ready": False,
            "solve_method": "linf_minimax_linprog",
            "reason": "invalid_or_empty_system",
        }
    try:
        from scipy.optimize import linprog  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return np.zeros(column_count, dtype=np.float64), {
            "enabled": True,
            "ready": False,
            "solve_method": "linf_minimax_linprog",
            "reason": f"scipy_linprog_unavailable:{type(exc).__name__}",
        }

    equilibration_mode = str(equilibration or "column")
    if equilibration_mode not in {"none", "column", "row_column"}:
        equilibration_mode = "column"
    scaled_a, scaled_b, column_scales, equilibration_meta = _equilibrate_lstsq_system(
        a,
        b,
        mode=equilibration_mode,
    )
    row_count = int(scaled_a.shape[0])
    objective = np.zeros(column_count + 1, dtype=np.float64)
    objective[-1] = 1.0
    minus_t = -np.ones((row_count, 1), dtype=np.float64)
    a_ub = np.vstack(
        [
            np.hstack([scaled_a, minus_t]),
            np.hstack([-scaled_a, minus_t]),
        ]
    )
    b_ub = np.concatenate([scaled_b, -scaled_b])
    bound = float(coefficient_bound)
    coefficient_bounds: list[tuple[float | None, float | None]]
    if np.isfinite(bound) and bound > 0.0:
        coefficient_bounds = [(-bound, bound)] * column_count
    else:
        coefficient_bounds = [(None, None)] * column_count
    variable_bounds = coefficient_bounds + [(0.0, None)]
    started = time.perf_counter()
    try:
        result = linprog(
            objective,
            A_ub=a_ub,
            b_ub=b_ub,
            bounds=variable_bounds,
            method="highs",
        )
    except Exception as exc:  # pragma: no cover - solver dependent
        return np.zeros(column_count, dtype=np.float64), {
            "enabled": True,
            "ready": False,
            "solve_method": "linf_minimax_linprog",
            "reason": f"linprog_exception:{type(exc).__name__}:{exc}",
            "equilibration": equilibration_meta,
        }
    solve_seconds = float(time.perf_counter() - started)
    if not bool(result.success):
        return np.zeros(column_count, dtype=np.float64), {
            "enabled": True,
            "ready": False,
            "solve_method": "linf_minimax_linprog",
            "reason": "linprog_failed",
            "status": int(result.status),
            "message": str(result.message),
            "solve_seconds": solve_seconds,
            "coefficient_bound_scaled": bound if bound > 0.0 else None,
            "equilibration": equilibration_meta,
        }
    scaled_coeffs = np.asarray(result.x[:column_count], dtype=np.float64)
    coeffs = scaled_coeffs * np.asarray(column_scales, dtype=np.float64)
    residual_vector = a @ coeffs - b
    scaled_residual_vector = scaled_a @ scaled_coeffs - scaled_b
    return coeffs, {
        "enabled": True,
        "ready": True,
        "solve_method": "linf_minimax_linprog",
        "status": int(result.status),
        "message": str(result.message),
        "solve_seconds": solve_seconds,
        "objective_linf_scaled": float(result.fun),
        "coefficient_bound_scaled": bound if bound > 0.0 else None,
        "coefficient_linf_scaled": _max_abs(scaled_coeffs),
        "coefficient_linf_unscaled": _max_abs(coeffs),
        "linear_residual_inf_n_unscaled": _max_abs(residual_vector),
        "linear_residual_l2_n_unscaled": float(np.linalg.norm(residual_vector))
        if residual_vector.size
        else 0.0,
        "linear_residual_inf_scaled": _max_abs(scaled_residual_vector),
        "physical_linf_objective": bool(equilibration_mode in {"none", "column"}),
        "equilibration": equilibration_meta,
    }


def run_mgt_cached_residual_jvp_batch_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    shell_pressure_load_path_policy: str = "all_components",
    output_json: Path | None = DEFAULT_OUT,
    output_npz: Path | None = None,
    output_final_checkpoint_npz: Path | None = None,
    promote_gate_eligible: bool = False,
    top_residual_count: int = 64,
    max_rows: int = 8,
    component_filter: str = "all",
    selection_policy: str = "component_dof_round_robin",
    support_columns_per_row: int = 1,
    node_block_support: bool = True,
    max_support_columns: int = 48,
    finite_difference_epsilon_m: float = 1.0e-7,
    ridge_factor: float = 1.0e-3,
    extra_ridge_factors: tuple[float, ...] = (),
    alpha_values: tuple[float, ...] = (1.0e-6, 3.0e-7, 1.0e-7, 3.0e-8, 1.0e-8),
    allow_negative_alphas: bool = False,
    include_gate_limited_alpha: bool = False,
    max_dynamic_alpha: float = 1.0,
    min_relative_improvement: float = 0.0,
    enable_component_block_basis: bool = False,
    component_block_basis_key_mode: str = "dominant_component",
    component_block_basis_normalization: str = "linf",
    component_block_basis_ridge_factor: float | None = None,
    enable_linf_active_set: bool = False,
    linf_active_set_coeff_bound: float = 0.0,
    linf_active_set_equilibration: str = "column",
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
    enable_torch_rocm_lstsq: bool = False,
    residual_batch_replay_backend: str = "single",
    residual_batch_replay_chunk_size: int = 1,
    enable_batch_jvp_replay: bool = False,
    enable_batch_alpha_replay: bool = True,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild_hip: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=str(shell_pressure_load_path_policy),
    )
    base_u = np.asarray(setup_meta["u0"], dtype=np.float64)
    base_started = time.perf_counter()
    stiffness, f_ext, free, residual, rhs, base_meta = assemble_residual(
        base_u,
        include_component_forces=True,
    )
    base_assembly_seconds = float(time.perf_counter() - base_started)
    component_forces = base_meta.pop("component_forces", {})
    component_breakdown = _component_breakdown(
        component_forces=component_forces if isinstance(component_forces, dict) else {},
        free=np.asarray(free, dtype=np.int64),
        residual=np.asarray(residual, dtype=np.float64),
        rhs=np.asarray(rhs, dtype=np.float64),
        top_count=int(top_residual_count),
    )
    free_idx = np.asarray(free, dtype=np.int64)
    local_row_by_global = {
        int(global_dof): int(local_row)
        for local_row, global_dof in enumerate(free_idx.tolist())
    }
    selected_rows, selected_local_rows, component_counts, dof_counts = (
        _select_block_lstsq_target_rows(
            top_rows=component_breakdown.get("top_rows", []),
            local_row_by_global=local_row_by_global,
            max_rows=int(max_rows),
            component_filter=str(component_filter),
            selection_policy=str(selection_policy),
        )
    )
    target_rows = np.asarray(selected_local_rows, dtype=np.int64)
    support_cols, support_meta = _select_support_columns(
        stiffness=stiffness,
        free=free_idx,
        target_rows=target_rows,
        support_columns_per_row=int(support_columns_per_row),
        node_block_support=bool(node_block_support),
        max_support_columns=int(max_support_columns),
    )
    batch_backend = str(residual_batch_replay_backend or "single").strip()
    if batch_backend not in {"single", "cpu", "hip_full_residual"}:
        batch_backend = "single"
    batch_chunk_size = max(int(residual_batch_replay_chunk_size), 1)
    batch_residual_evaluator = getattr(assemble_residual, "evaluate_residual_batch", None)
    batch_evaluator_available = callable(batch_residual_evaluator)
    batch_replay_available = bool(
        batch_evaluator_available and batch_backend != "single" and batch_chunk_size > 1
    )
    batch_jvp_replay_enabled = bool(batch_replay_available and enable_batch_jvp_replay)
    batch_alpha_replay_enabled = bool(batch_replay_available and enable_batch_alpha_replay)
    residual_batch_replay_meta: dict[str, Any] = {
        "backend_requested": batch_backend,
        "chunk_size": int(batch_chunk_size),
        "batch_evaluator_available": bool(batch_evaluator_available),
        "enabled": bool(batch_jvp_replay_enabled or batch_alpha_replay_enabled),
        "jvp_enabled": bool(batch_jvp_replay_enabled),
        "alpha_enabled": bool(batch_alpha_replay_enabled),
        "jvp_default_disabled_reason": (
            "finite_difference_lstsq_is_sensitive_to_batch_roundoff"
            if batch_replay_available and not bool(enable_batch_jvp_replay)
            else None
        ),
        "alpha_batch_count": 0,
        "alpha_batch_state_count": 0,
        "alpha_batch_seconds": 0.0,
        "alpha_batch_fallback_count": 0,
        "backend_error": "",
    }
    cache = ResidualJvpBatchCache(
        assemble_residual=assemble_residual,
        base_u=base_u,
        base_free=free_idx,
        base_residual=np.asarray(residual, dtype=np.float64),
        reference_f_ext=np.asarray(f_ext, dtype=np.float64),
        prefer_residual_only=True,
        batch_residual_evaluator=batch_residual_evaluator if batch_jvp_replay_enabled else None,
        batch_replay_backend=batch_backend,
        hipcc=hipcc,
        force_rebuild_hip=bool(force_rebuild_hip),
    )
    jvp_started = time.perf_counter()
    fd_submatrix, jvp_rows, cache_summary = build_fd_jvp_submatrix(
        cache=cache,
        free=free_idx,
        target_rows=target_rows,
        support_cols=support_cols,
        epsilon=float(finite_difference_epsilon_m),
        batch_chunk_size=batch_chunk_size if batch_jvp_replay_enabled else 1,
    )
    jvp_seconds = float(time.perf_counter() - jvp_started)
    base_residual_np = np.asarray(residual, dtype=np.float64)
    target_rhs = -base_residual_np[target_rows] if target_rows.size else np.asarray([], dtype=np.float64)
    candidate_rows: list[dict[str, Any]] = []
    candidate_vectors: list[np.ndarray] = []
    correction_direction_rows: list[dict[str, Any]] = []
    solve_meta: dict[str, Any] = {"evaluated": False}
    correction = np.zeros_like(base_u)
    torch_rocm_probe: dict[str, Any] = {"attempted": False}
    component_block_basis_meta: dict[str, Any] = {
        "enabled": bool(enable_component_block_basis),
        "ready": False,
    }
    linf_active_set_meta: dict[str, Any] = {
        "enabled": bool(enable_linf_active_set),
        "ready": False,
    }
    base_residual_inf = _max_abs(base_residual_np)
    rhs_inf = _max_abs(np.asarray(rhs, dtype=np.float64))
    max_abs_u = max(_max_abs(base_u), 1.0e-12)

    def evaluate_direction_candidates(
        *,
        direction_source: str,
        direction: np.ndarray,
        direction_meta: dict[str, Any],
    ) -> None:
        direction_arr = np.asarray(direction, dtype=np.float64)
        correction_inf_local = _max_abs(direction_arr)
        if correction_inf_local <= 0.0:
            correction_direction_rows.append(
                {
                    "direction_source": str(direction_source),
                    "evaluated": False,
                    "reason": "zero_direction",
                    "correction_inf_m": 0.0,
                    "meta": direction_meta,
                }
            )
            return
        direction_index = len(correction_direction_rows)
        sweep_alpha_values = _candidate_alpha_values(
            base_alpha_values=alpha_values,
            direction=direction_arr,
            base_u=base_u,
            allow_negative_alphas=bool(allow_negative_alphas),
            include_gate_limited_alpha=bool(include_gate_limited_alpha),
            relative_increment_tolerance=float(relative_increment_tolerance),
            max_dynamic_alpha=float(max_dynamic_alpha),
        )
        correction_direction_rows.append(
            {
                "direction_source": str(direction_source),
                "direction_index": int(direction_index),
                "evaluated": bool(sweep_alpha_values),
                "correction_inf_m": float(correction_inf_local),
                "alpha_values": [float(value) for value in sweep_alpha_values],
                "meta": direction_meta,
            }
        )
        alpha_candidate_values: list[float] = []
        alpha_candidate_us: list[np.ndarray] = []
        for alpha in sweep_alpha_values:
            alpha_float = float(alpha)
            alpha_candidate_values.append(alpha_float)
            alpha_candidate_us.append(base_u + alpha_float * direction_arr)

        def append_candidate_row(
            *,
            alpha_float: float,
            candidate_u: np.ndarray,
            trial_free: np.ndarray,
            trial_residual: np.ndarray,
            trial_rhs: np.ndarray,
            trial_seconds: float,
            batch_meta: dict[str, Any] | None = None,
            batch_index: int | None = None,
        ) -> None:
            batch_meta = batch_meta if isinstance(batch_meta, dict) else {}
            trial_free_idx = np.asarray(trial_free, dtype=np.int64)
            trial_residual_np = np.asarray(trial_residual, dtype=np.float64)
            trial_rhs_np = np.asarray(trial_rhs, dtype=np.float64)
            free_stable = bool(
                trial_free_idx.shape == free_idx.shape
                and np.array_equal(trial_free_idx, free_idx)
            )
            residual_inf = _max_abs(trial_residual_np)
            increment = _max_abs(candidate_u - base_u)
            max_abs_candidate = max(_max_abs(candidate_u), max_abs_u, 1.0e-12)
            metrics = _translation_metrics(candidate_u)
            candidate_rows.append(
                {
                    "direction_source": str(direction_source),
                    "direction_index": int(direction_index),
                    "alpha": alpha_float,
                    "free_dof_set_stable": free_stable,
                    "residual_only_assembly": True,
                    "residual_batch_replay": bool(batch_meta),
                    "residual_batch_backend": (
                        batch_meta.get("residual_batch_backend")
                        if batch_meta
                        else "single_assemble_residual"
                    ),
                    "hip_full_residual_batch_replay": bool(
                        batch_meta.get("hip_full_residual_batch_replay", False)
                    ),
                    "batch_replay_index": batch_index,
                    "assembly_seconds": trial_seconds,
                    "direct_residual_inf_n": residual_inf,
                    "direct_relative_residual_inf": residual_inf
                    / max(_max_abs(trial_rhs_np), rhs_inf, 1.0),
                    "improvement_inf_n": base_residual_inf - residual_inf,
                    "relative_improvement": (base_residual_inf - residual_inf)
                    / max(base_residual_inf, 1.0),
                    "relative_increment": increment / max_abs_candidate,
                    "max_increment_m": increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                    "relative_increment_gate_passed": increment / max_abs_candidate
                    <= float(relative_increment_tolerance),
                }
            )
            candidate_vectors.append(np.asarray(candidate_u, dtype=np.float64).copy())

        def append_single_candidate(alpha_float: float, candidate_u: np.ndarray) -> None:
            trial_started = time.perf_counter()
            _k, _f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
                candidate_u,
                residual_only=True,
                free_override=free_idx,
                external_load_override=f_ext,
            )
            trial_seconds = float(time.perf_counter() - trial_started)
            append_candidate_row(
                alpha_float=alpha_float,
                candidate_u=candidate_u,
                trial_free=np.asarray(trial_free, dtype=np.int64),
                trial_residual=np.asarray(trial_residual, dtype=np.float64),
                trial_rhs=np.asarray(trial_rhs, dtype=np.float64),
                trial_seconds=trial_seconds,
            )

        if batch_alpha_replay_enabled and len(alpha_candidate_us) > 1:
            for chunk_start in range(0, len(alpha_candidate_us), batch_chunk_size):
                chunk_us = alpha_candidate_us[chunk_start : chunk_start + batch_chunk_size]
                chunk_alphas = alpha_candidate_values[chunk_start : chunk_start + batch_chunk_size]
                batch_started = time.perf_counter()
                try:
                    trial_residual_batch, trial_free, trial_rhs, batch_meta = batch_residual_evaluator(
                        np.asarray(chunk_us, dtype=np.float64),
                        external_load_override=f_ext,
                        free_override=free_idx,
                        backend=batch_backend,
                        hipcc=hipcc,
                        force_rebuild_hip=bool(force_rebuild_hip),
                    )
                except Exception as exc:  # pragma: no cover - recorded in probe JSON
                    residual_batch_replay_meta["backend_error"] = str(exc)
                    residual_batch_replay_meta["alpha_batch_fallback_count"] = int(
                        residual_batch_replay_meta["alpha_batch_fallback_count"]
                    ) + len(chunk_us)
                    for alpha_float, candidate_u in zip(chunk_alphas, chunk_us, strict=False):
                        append_single_candidate(
                            float(alpha_float),
                            np.asarray(candidate_u, dtype=np.float64),
                        )
                    continue
                batch_seconds = float(time.perf_counter() - batch_started)
                residual_batch_replay_meta["alpha_batch_count"] = int(
                    residual_batch_replay_meta["alpha_batch_count"]
                ) + 1
                residual_batch_replay_meta["alpha_batch_state_count"] = int(
                    residual_batch_replay_meta["alpha_batch_state_count"]
                ) + len(chunk_us)
                residual_batch_replay_meta["alpha_batch_seconds"] = float(
                    residual_batch_replay_meta["alpha_batch_seconds"]
                ) + batch_seconds
                residual_rows = np.asarray(trial_residual_batch, dtype=np.float64)
                for local_index, (alpha_float, candidate_u) in enumerate(
                    zip(chunk_alphas, chunk_us, strict=False)
                ):
                    append_candidate_row(
                        alpha_float=float(alpha_float),
                        candidate_u=np.asarray(candidate_u, dtype=np.float64),
                        trial_free=np.asarray(trial_free, dtype=np.int64),
                        trial_residual=np.asarray(residual_rows[local_index], dtype=np.float64),
                        trial_rhs=np.asarray(trial_rhs, dtype=np.float64),
                        trial_seconds=batch_seconds / max(len(chunk_us), 1),
                        batch_meta=batch_meta if isinstance(batch_meta, dict) else {},
                        batch_index=int(local_index),
                    )
        else:
            for alpha_float, candidate_u in zip(
                alpha_candidate_values,
                alpha_candidate_us,
                strict=False,
            ):
                append_single_candidate(
                    float(alpha_float),
                    np.asarray(candidate_u, dtype=np.float64),
                )

    if fd_submatrix is not None and fd_submatrix.size and support_cols.size:
        scaled_submatrix, scaled_target_rhs, column_scales, equilibration_meta = (
            _equilibrate_lstsq_system(fd_submatrix, target_rhs, mode="row_column")
        )
        scaled_coeffs, solve_meta = _ridge_coefficients(
            scaled_submatrix,
            scaled_target_rhs,
            ridge_factor=float(ridge_factor),
        )
        solve_meta["equilibration"] = equilibration_meta
        coeffs = np.asarray(scaled_coeffs, dtype=np.float64) * np.asarray(
            column_scales,
            dtype=np.float64,
        )
        unscaled_residual_vector = np.asarray(fd_submatrix, dtype=np.float64) @ coeffs - target_rhs
        solve_meta["evaluated"] = True
        solve_meta["linear_residual_inf_n_unscaled"] = _max_abs(unscaled_residual_vector)
        solve_meta["linear_residual_l2_n_unscaled"] = (
            float(np.linalg.norm(unscaled_residual_vector))
            if unscaled_residual_vector.size
            else 0.0
        )
        for local_col, coeff in zip(support_cols.tolist(), coeffs.tolist(), strict=False):
            correction[int(free_idx[int(local_col)])] = float(coeff)
        correction_inf = _max_abs(correction)
        evaluate_direction_candidates(
            direction_source="all_target_rows_lstsq",
            direction=correction,
            direction_meta={
                "direction_kind": "all_target_rows_lstsq",
                "target_row_count": int(target_rows.size),
                "support_size": int(support_cols.size),
                "linear_solve": solve_meta,
            },
        )
        evaluated_ridge_factors = {float(ridge_factor)}
        for extra_ridge in extra_ridge_factors:
            extra_ridge_float = float(extra_ridge)
            if (
                not np.isfinite(extra_ridge_float)
                or extra_ridge_float < 0.0
                or extra_ridge_float in evaluated_ridge_factors
            ):
                continue
            evaluated_ridge_factors.add(extra_ridge_float)
            extra_scaled_coeffs, extra_solve_meta = _ridge_coefficients(
                scaled_submatrix,
                scaled_target_rhs,
                ridge_factor=extra_ridge_float,
            )
            extra_solve_meta["equilibration"] = equilibration_meta
            extra_coeffs = np.asarray(extra_scaled_coeffs, dtype=np.float64) * np.asarray(
                column_scales,
                dtype=np.float64,
            )
            extra_residual_vector = (
                np.asarray(fd_submatrix, dtype=np.float64) @ extra_coeffs
                - target_rhs
            )
            extra_solve_meta["evaluated"] = True
            extra_solve_meta["linear_residual_inf_n_unscaled"] = _max_abs(
                extra_residual_vector
            )
            extra_solve_meta["linear_residual_l2_n_unscaled"] = (
                float(np.linalg.norm(extra_residual_vector))
                if extra_residual_vector.size
                else 0.0
            )
            extra_correction = np.zeros_like(base_u)
            for local_col, coeff in zip(
                support_cols.tolist(),
                extra_coeffs.tolist(),
                strict=False,
            ):
                extra_correction[int(free_idx[int(local_col)])] = float(coeff)
            evaluate_direction_candidates(
                direction_source=f"all_target_rows_lstsq_ridge_{extra_ridge_float:g}",
                direction=extra_correction,
                direction_meta={
                    "direction_kind": "all_target_rows_lstsq_extra_ridge",
                    "target_row_count": int(target_rows.size),
                    "support_size": int(support_cols.size),
                    "ridge_factor": float(extra_ridge_float),
                    "linear_solve": extra_solve_meta,
                },
            )
        if enable_linf_active_set:
            linf_coeffs, linf_active_set_meta = _linf_minimax_coefficients(
                fd_submatrix,
                target_rhs,
                coefficient_bound=float(linf_active_set_coeff_bound),
                equilibration=str(linf_active_set_equilibration),
            )
            if bool(linf_active_set_meta.get("ready")):
                linf_correction = np.zeros_like(base_u)
                for local_col, coeff in zip(
                    support_cols.tolist(),
                    np.asarray(linf_coeffs, dtype=np.float64).tolist(),
                    strict=False,
                ):
                    linf_correction[int(free_idx[int(local_col)])] = float(coeff)
                evaluate_direction_candidates(
                    direction_source="all_target_rows_linf_minimax",
                    direction=linf_correction,
                    direction_meta={
                        "direction_kind": "all_target_rows_linf_minimax",
                        "target_row_count": int(target_rows.size),
                        "support_size": int(support_cols.size),
                        "linear_solve": linf_active_set_meta,
                    },
                )
        if enable_component_block_basis:
            basis_ridge_factor = (
                float(component_block_basis_ridge_factor)
                if component_block_basis_ridge_factor is not None
                else float(ridge_factor)
            )
            basis_directions, component_block_basis_meta = (
                _build_component_block_basis_directions(
                    fd_submatrix=np.asarray(fd_submatrix, dtype=np.float64),
                    target_rhs=np.asarray(target_rhs, dtype=np.float64),
                    support_cols=np.asarray(support_cols, dtype=np.int64),
                    free=free_idx,
                    selected_rows=selected_rows,
                    key_mode=str(component_block_basis_key_mode),
                    ridge_factor=max(basis_ridge_factor, 0.0),
                    normalization=str(component_block_basis_normalization),
                )
            )
            for direction_payload in basis_directions:
                support_coefficients = np.asarray(
                    direction_payload.get("support_coefficients"),
                    dtype=np.float64,
                )
                if support_coefficients.size != support_cols.size:
                    continue
                basis_correction = np.zeros_like(base_u)
                for local_col, coeff in zip(
                    support_cols.tolist(),
                    support_coefficients.tolist(),
                    strict=False,
                ):
                    basis_correction[int(free_idx[int(local_col)])] = float(coeff)
                evaluate_direction_candidates(
                    direction_source=str(direction_payload.get("source") or "component_block"),
                    direction=basis_correction,
                    direction_meta=direction_payload.get("meta")
                    if isinstance(direction_payload.get("meta"), dict)
                    else {},
                )
        if enable_torch_rocm_lstsq:
            torch_rocm_probe = _torch_rocm_lstsq_probe(
                fd_submatrix,
                target_rhs,
                ridge_lambda=float(solve_meta.get("ridge_lambda") or 0.0),
            )
    else:
        solve_meta = {
            "evaluated": False,
            "reason": "fd_jvp_submatrix_unavailable",
        }
        correction_inf = 0.0

    best_candidate = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    best_candidate_index, best_candidate_row = best_candidate
    best_gate_candidate = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
            and float(row.get("improvement_inf_n", 0.0)) > 0.0
            and float(row.get("relative_improvement", 0.0))
            >= max(float(min_relative_improvement), 0.0)
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    best_gate_candidate_index, best_gate_candidate_row = best_gate_candidate
    output_final_checkpoint: dict[str, Any] = {
        "written": False,
        "path": str(output_final_checkpoint_npz)
        if output_final_checkpoint_npz is not None
        else None,
        "reason": (
            "not_requested"
            if output_final_checkpoint_npz is None
            else "promote_gate_eligible_disabled"
            if not promote_gate_eligible
            else "no_gate_eligible_candidate"
        ),
    }
    if (
        promote_gate_eligible
        and output_final_checkpoint_npz is not None
        and best_gate_candidate_index is not None
    ):
        final_u = candidate_vectors[int(best_gate_candidate_index)]
        _k, _f, final_free, final_residual, final_rhs, _final_meta = assemble_residual(
            final_u,
            residual_only=True,
            free_override=free_idx,
            external_load_override=f_ext,
        )
        final_free_stable = bool(
            np.asarray(final_free, dtype=np.int64).shape == free_idx.shape
            and np.array_equal(np.asarray(final_free, dtype=np.int64), free_idx)
        )
        if final_free_stable:
            checkpoint_meta, _loaded_u, state_history, residual_history = _load_checkpoint(
                checkpoint_npz
            )
            output_final_checkpoint = _write_checkpoint(
                path=output_final_checkpoint_npz,
                source_checkpoint_npz=checkpoint_npz,
                checkpoint_meta=checkpoint_meta,
                u0=base_u,
                final_u=final_u,
                base_residual=base_residual_np,
                final_residual=np.asarray(final_residual, dtype=np.float64),
                rhs=np.asarray(final_rhs, dtype=np.float64),
                loaded_state_history=state_history,
                loaded_residual_history=residual_history,
            )
            output_final_checkpoint["written"] = True
            output_final_checkpoint["source"] = "cached_residual_jvp_best_gate_candidate"
            output_final_checkpoint["alpha"] = float(
                best_gate_candidate_row.get("alpha") or 0.0
            )
        else:
            output_final_checkpoint = {
                "written": False,
                "path": str(output_final_checkpoint_npz),
                "reason": "final_free_dof_set_changed",
            }
    if output_npz is not None and fd_submatrix is not None:
        output_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            output_npz,
            schema_version=np.asarray(SCHEMA_VERSION),
            checkpoint_npz=np.asarray(str(checkpoint_npz)),
            target_rows=target_rows,
            target_global_dofs=free_idx[target_rows] if target_rows.size else np.asarray([], dtype=np.int64),
            support_cols=support_cols,
            support_global_dofs=free_idx[support_cols] if support_cols.size else np.asarray([], dtype=np.int64),
            fd_submatrix=np.asarray(fd_submatrix, dtype=np.float64),
            target_rhs=np.asarray(target_rhs, dtype=np.float64),
            correction_u=np.asarray(correction, dtype=np.float64),
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial",
        "cached_residual_jvp_batch_ready": bool(fd_submatrix is not None),
        "checkpoint": str(checkpoint_npz),
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "output_npz": str(output_npz) if output_npz is not None else None,
        "output_final_checkpoint": output_final_checkpoint,
        "promoted_to_final_state": bool(output_final_checkpoint.get("written")),
        "base_direct_residual": {
            "direct_residual_inf_n": _max_abs(base_residual_np),
            "direct_relative_residual_inf": _max_abs(base_residual_np)
            / max(_max_abs(np.asarray(rhs, dtype=np.float64)), 1.0),
            "rhs_inf_n": _max_abs(np.asarray(rhs, dtype=np.float64)),
        },
        "target_selection": {
            "top_residual_count": int(top_residual_count),
            "max_rows": int(max_rows),
            "component_filter": str(component_filter),
            "selection_policy": str(selection_policy),
            "selected_hotspot_row_count": int(len(selected_rows)),
            "selected_hotspot_dominant_component_counts": component_counts,
            "selected_hotspot_dof_counts": dof_counts,
            "target_rows": [int(row) for row in target_rows.tolist()],
            "target_global_dofs": [
                int(free_idx[int(row)]) for row in target_rows.tolist()
            ],
        },
        "support": support_meta,
        "finite_difference_jvp_batch": {
            **cache_summary,
            "jvp_seconds": jvp_seconds,
            "jvp_rows": jvp_rows,
        },
        "linear_solve": solve_meta,
        "correction_inf_m": correction_inf,
        "correction_directions": correction_direction_rows,
        "component_block_basis": component_block_basis_meta,
        "linf_active_set": linf_active_set_meta,
        "allow_negative_alphas": bool(allow_negative_alphas),
        "include_gate_limited_alpha": bool(include_gate_limited_alpha),
        "max_dynamic_alpha": float(max_dynamic_alpha),
        "extra_ridge_factors": [float(value) for value in extra_ridge_factors],
        "minimum_relative_improvement": float(max(min_relative_improvement, 0.0)),
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate_row,
        "best_gate_eligible_candidate": best_gate_candidate_row,
        "torch_rocm_lstsq_probe": torch_rocm_probe,
        "residual_batch_replay": residual_batch_replay_meta,
        "base_assembly_seconds": base_assembly_seconds,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Cached residual-JVP batch replay only. A promoted checkpoint remains an "
            "incremental frontier advance, not full nonlinear residual closure."
        ),
        "blockers": [
            "direct_residual_gate_not_closed",
            "cached_batch_is_diagnostic_not_final_newton_closure",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only"),
        default="all_components",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--output-npz", type=Path, default=None)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--promote-gate-eligible", action="store_true")
    parser.add_argument("--top-residual-count", type=int, default=64)
    parser.add_argument("--max-rows", type=int, default=8)
    parser.add_argument("--component-filter", default="all")
    parser.add_argument("--selection-policy", default="component_dof_round_robin")
    parser.add_argument("--support-columns-per-row", type=int, default=1)
    parser.add_argument("--node-block-support", action="store_true")
    parser.add_argument("--max-support-columns", type=int, default=48)
    parser.add_argument("--finite-difference-epsilon-m", type=float, default=1.0e-7)
    parser.add_argument("--ridge-factor", type=float, default=1.0e-3)
    parser.add_argument(
        "--extra-ridge-factors",
        default="",
        help=(
            "Optional comma-separated ridge factors to evaluate as extra LS "
            "directions against the same cached JVP matrix."
        ),
    )
    parser.add_argument("--alpha-values", default="1e-6,3e-7,1e-7,3e-8,1e-8")
    parser.add_argument("--allow-negative-alphas", action="store_true")
    parser.add_argument(
        "--include-gate-limited-alpha",
        action="store_true",
        help=(
            "Also evaluate per-direction alpha values capped by the relative "
            "increment gate."
        ),
    )
    parser.add_argument(
        "--max-dynamic-alpha",
        type=float,
        default=1.0,
        help="Upper clamp for dynamically generated gate-limited alpha values.",
    )
    parser.add_argument(
        "--min-relative-improvement",
        type=float,
        default=0.0,
        help=(
            "Minimum candidate relative improvement required for checkpoint "
            "promotion. Defaults to the legacy >0 behavior."
        ),
    )
    parser.add_argument("--enable-component-block-basis", action="store_true")
    parser.add_argument(
        "--component-block-basis-key-mode",
        choices=("dominant_component", "dominant_component_dof", "dof"),
        default="dominant_component",
        help="Grouping key used to build component-block residual/JVP basis vectors.",
    )
    parser.add_argument(
        "--component-block-basis-normalization",
        choices=("none", "linf"),
        default="linf",
        help="Normalize each component-block basis vector before the basis LS solve.",
    )
    parser.add_argument(
        "--component-block-basis-ridge-factor",
        type=float,
        default=None,
        help="Optional ridge factor for component-block basis solves; defaults to --ridge-factor.",
    )
    parser.add_argument(
        "--enable-linf-active-set",
        action="store_true",
        help=(
            "Add a Chebyshev/minimax direction that minimizes the selected "
            "active-row linear residual infinity norm."
        ),
    )
    parser.add_argument(
        "--linf-active-set-coeff-bound",
        type=float,
        default=0.0,
        help=(
            "Optional bound on scaled minimax coefficients. Non-positive means "
            "unbounded coefficients."
        ),
    )
    parser.add_argument(
        "--linf-active-set-equilibration",
        choices=("none", "column", "row_column"),
        default="column",
        help=(
            "Scaling mode for minimax solve. Use none/column for physical "
            "residual infinity-norm objective; row_column is row-weighted."
        ),
    )
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--enable-torch-rocm-lstsq", action="store_true")
    parser.add_argument(
        "--residual-batch-replay-backend",
        choices=("single", "cpu", "hip_full_residual"),
        default="single",
        help="Batch residual replay backend for finite-difference JVP and alpha candidates.",
    )
    parser.add_argument(
        "--residual-batch-replay-chunk-size",
        type=int,
        default=1,
        help="Chunk size for residual batch replay. Values <=1 preserve single-state replay.",
    )
    parser.add_argument(
        "--enable-batch-jvp-replay",
        action="store_true",
        help=(
            "Also use residual batch replay for finite-difference JVP columns. "
            "Disabled by default because the active LS system is roundoff-sensitive."
        ),
    )
    parser.add_argument(
        "--disable-batch-alpha-replay",
        action="store_true",
        help="Keep alpha candidate replay on the single-state residual path.",
    )
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--force-rebuild-hip", action="store_true")
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this probe is diagnostic and does not close G1 by itself.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_cpu_diagnostic:
        print("cached-residual-jvp-batch: blocked diagnostic requires --allow-cpu-diagnostic")
        return 2
    payload = run_mgt_cached_residual_jvp_batch_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        output_json=args.output_json,
        output_npz=args.output_npz,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        promote_gate_eligible=bool(args.promote_gate_eligible),
        top_residual_count=args.top_residual_count,
        max_rows=args.max_rows,
        component_filter=args.component_filter,
        selection_policy=args.selection_policy,
        support_columns_per_row=args.support_columns_per_row,
        node_block_support=args.node_block_support,
        max_support_columns=args.max_support_columns,
        finite_difference_epsilon_m=args.finite_difference_epsilon_m,
        ridge_factor=args.ridge_factor,
        extra_ridge_factors=_parse_float_csv(args.extra_ridge_factors),
        alpha_values=_parse_float_csv(args.alpha_values),
        allow_negative_alphas=bool(args.allow_negative_alphas),
        include_gate_limited_alpha=bool(args.include_gate_limited_alpha),
        max_dynamic_alpha=args.max_dynamic_alpha,
        min_relative_improvement=args.min_relative_improvement,
        enable_component_block_basis=bool(args.enable_component_block_basis),
        component_block_basis_key_mode=args.component_block_basis_key_mode,
        component_block_basis_normalization=args.component_block_basis_normalization,
        component_block_basis_ridge_factor=args.component_block_basis_ridge_factor,
        enable_linf_active_set=bool(args.enable_linf_active_set),
        linf_active_set_coeff_bound=args.linf_active_set_coeff_bound,
        linf_active_set_equilibration=args.linf_active_set_equilibration,
        residual_tolerance_n=args.residual_tolerance_n,
        relative_increment_tolerance=args.relative_increment_tolerance,
        enable_torch_rocm_lstsq=bool(args.enable_torch_rocm_lstsq),
        residual_batch_replay_backend=args.residual_batch_replay_backend,
        residual_batch_replay_chunk_size=args.residual_batch_replay_chunk_size,
        enable_batch_jvp_replay=bool(args.enable_batch_jvp_replay),
        enable_batch_alpha_replay=not bool(args.disable_batch_alpha_replay),
        hipcc=args.hipcc,
        force_rebuild_hip=bool(args.force_rebuild_hip),
    )
    print(
        "cached-residual-jvp-batch: "
        f"ready={payload['cached_residual_jvp_batch_ready']} "
        f"promoted={payload['promoted_to_final_state']} "
        f"base={payload['base_direct_residual']['direct_residual_inf_n']} "
        f"best={payload['best_candidate'].get('direct_residual_inf_n')} "
        f"runtime={payload['runtime_seconds']:.3f}s -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
