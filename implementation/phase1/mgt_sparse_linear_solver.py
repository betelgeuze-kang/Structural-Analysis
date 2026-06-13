#!/usr/bin/env python3
"""Shared sparse linear solvers for equilibrium Newton steps."""

from __future__ import annotations

import time
import warnings
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, eye
from scipy.sparse.linalg import LinearOperator, gmres, spsolve
from scipy.sparse.linalg import spilu

from mgt_sparse_matrix_equilibration import (
    symmetric_sqrt_diagonal_scaling,
    unscale_solution,
)

DOF_PER_NODE = 6


def solve_sparse_regularized(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    regularization_factor: float = 1.0e-8,
) -> tuple[np.ndarray, float]:
    rhs_np = np.asarray(rhs, dtype=np.float64)
    k_csc = k_ff.tocsc()
    diag = np.asarray(k_csc.diagonal(), dtype=np.float64)
    regularization = float(regularization_factor) * max(float(np.mean(np.abs(diag))), 1.0)
    k_reg = k_csc + eye(k_csc.shape[0], format="csc") * regularization
    solution = np.asarray(spsolve(k_reg, rhs_np), dtype=np.float64)
    return solution, regularization


def solve_sparse_with_iterative_refinement(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    regularization_factor: float = 1.0e-10,
    max_refinement_iterations: int = 10,
    residual_floor_n: float = 1.0e-8,
) -> tuple[np.ndarray, float, float]:
    """Regularized solve followed by unregularized residual refinement."""
    rhs_np = np.asarray(rhs, dtype=np.float64)
    solution, regularization = solve_sparse_regularized(
        k_ff,
        rhs_np,
        regularization_factor=regularization_factor,
    )
    k_csc = k_ff.tocsc()
    k_reg = k_csc + eye(k_csc.shape[0], format="csc") * regularization
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    threshold = max(float(residual_floor_n), float(residual_floor_n) * max(rhs_inf, 1.0))
    best_solution = np.asarray(solution, dtype=np.float64)
    best_residual = np.asarray(k_csc @ best_solution - rhs_np, dtype=np.float64)
    best_residual_inf = float(np.max(np.abs(best_residual))) if best_residual.size else 0.0
    for _refine_idx in range(max(int(max_refinement_iterations), 0)):
        if best_residual_inf <= threshold:
            break
        try:
            correction = np.asarray(spsolve(k_reg, -best_residual), dtype=np.float64)
        except Exception:
            break
        candidate = best_solution + correction
        candidate_residual = np.asarray(k_csc @ candidate - rhs_np, dtype=np.float64)
        candidate_residual_inf = (
            float(np.max(np.abs(candidate_residual))) if candidate_residual.size else float("inf")
        )
        if candidate_residual_inf >= best_residual_inf:
            break
        best_solution = candidate
        best_residual = candidate_residual
        best_residual_inf = candidate_residual_inf
    return best_solution, regularization, best_residual_inf


def build_node_block_jacobi_preconditioner(
    k_ff: Any,
    *,
    free_global_dofs: np.ndarray,
) -> tuple[Any, dict[str, Any]]:
    """Build the inverse nodal-block (up to 6x6) preconditioner ONCE as a sparse matrix.

    Returns (m_csr, meta) where m_csr @ v applies the block Jacobi inverse.
    The build is fully vectorized: diagonal blocks are extracted by filtering
    COO entries whose row and column map to the same node, then inverted as a
    batched (n_blocks, 6, 6) array with the same abs-diag normalization and
    diagonal fallback as the previous per-application implementation.
    """
    build_started = time.perf_counter()
    csr = k_ff.tocsr()
    n = int(csr.shape[0])
    free = np.asarray(free_global_dofs, dtype=np.int64).reshape(-1)
    if free.size != n:
        raise ValueError(
            f"free_global_dofs size {free.size} does not match matrix dimension {n}"
        )
    node_ids = free // DOF_PER_NODE
    comps = (free % DOF_PER_NODE).astype(np.int64)
    _unique_nodes, block_of_row = np.unique(node_ids, return_inverse=True)
    n_blocks = int(_unique_nodes.size)

    coo = csr.tocoo()
    same_block = block_of_row[coo.row] == block_of_row[coo.col]
    entry_rows = coo.row[same_block]
    entry_cols = coo.col[same_block]
    entry_vals = coo.data[same_block]

    blocks = np.zeros((n_blocks, DOF_PER_NODE, DOF_PER_NODE), dtype=np.float64)
    # csr.tocoo() yields canonical (unique) entries, so direct assignment is safe.
    blocks[block_of_row[entry_rows], comps[entry_rows], comps[entry_cols]] = entry_vals

    present = np.zeros((n_blocks, DOF_PER_NODE), dtype=bool)
    present[block_of_row, comps] = True
    diag_idx = np.arange(DOF_PER_NODE)
    # Components absent from the free set get an identity diagonal so the
    # padded 6x6 block stays invertible; those rows/cols are never read back.
    block_diag = blocks[:, diag_idx, diag_idx]
    blocks[:, diag_idx, diag_idx] = np.where(present, block_diag, 1.0)

    abs_diag = np.maximum(np.abs(blocks[:, diag_idx, diag_idx]), 1.0e-12)
    scale_outer = abs_diag[:, :, None] * abs_diag[:, None, :]
    blocks_scaled = blocks / scale_outer
    singular_count = 0
    try:
        inv_scaled = np.linalg.inv(blocks_scaled)
    except np.linalg.LinAlgError:
        inv_scaled = np.empty_like(blocks_scaled)
        for block_index in range(n_blocks):
            try:
                inv_scaled[block_index] = np.linalg.inv(blocks_scaled[block_index])
            except np.linalg.LinAlgError:
                singular_count += 1
                inv_scaled[block_index] = np.diag(abs_diag[block_index])
    inv_blocks = inv_scaled / scale_outer

    # Guard against near-singular blocks: an exactly-singular block raises and
    # falls back above, but a block with condition ~1e15 silently "inverts" to
    # entries of magnitude ~1e15, which destroys GMRES (NaN breakdown observed
    # on the lambda=0.05 equilibrium tangent). Estimate the 1-norm condition of
    # the diag-normalized block and fall back to the diagonal inverse when the
    # block inverse would amplify beyond a stable bound.
    block_norm1 = np.max(np.sum(np.abs(blocks_scaled), axis=1), axis=1)
    inv_norm1 = np.max(np.sum(np.abs(inv_scaled), axis=1), axis=1)
    cond_estimate = block_norm1 * inv_norm1
    nonfinite = ~np.all(np.isfinite(inv_blocks), axis=(1, 2))
    ill_conditioned = nonfinite | ~np.isfinite(cond_estimate) | (cond_estimate > 1.0e12)
    if np.any(ill_conditioned):
        bad_indices = np.flatnonzero(ill_conditioned)
        singular_count += int(bad_indices.size)
        inv_blocks[bad_indices] = 0.0
        inv_blocks[bad_indices[:, None], diag_idx[None, :], diag_idx[None, :]] = (
            1.0 / abs_diag[bad_indices]
        )

    position = np.full((n_blocks, DOF_PER_NODE), -1, dtype=np.int64)
    position[block_of_row, comps] = np.arange(n, dtype=np.int64)
    rows_grid = np.broadcast_to(position[:, :, None], inv_blocks.shape)
    cols_grid = np.broadcast_to(position[:, None, :], inv_blocks.shape)
    valid = (rows_grid >= 0) & (cols_grid >= 0)
    m_csr = coo_matrix(
        (inv_blocks[valid], (rows_grid[valid], cols_grid[valid])),
        shape=(n, n),
    ).tocsr()
    meta = {
        "preconditioner": "node_block_jacobi_inverse",
        "block_count": n_blocks,
        "singular_block_count": int(singular_count),
        "build_seconds": time.perf_counter() - build_started,
    }
    return m_csr, meta


def _node_block_jacobi_precondition(
    k_ff: Any,
    vector: np.ndarray,
    *,
    free_global_dofs: np.ndarray,
) -> np.ndarray:
    """Apply inverse free-DOF nodal blocks (up to 6x6) with diagonal fallback.

    Backward-compatible one-shot helper. For iterative solvers, build the
    preconditioner once with build_node_block_jacobi_preconditioner and reuse it.
    """
    rhs = np.asarray(vector, dtype=np.float64).reshape(-1)
    m_csr, _meta = build_node_block_jacobi_preconditioner(
        k_ff,
        free_global_dofs=free_global_dofs,
    )
    return np.asarray(m_csr @ rhs, dtype=np.float64)


def _translation_block_jacobi_precondition(
    k_ff: Any,
    vector: np.ndarray,
    *,
    free_global_dofs: np.ndarray,
) -> np.ndarray:
    return _node_block_jacobi_precondition(
        k_ff,
        vector,
        free_global_dofs=free_global_dofs,
    )


def solve_block_jacobi_gmres(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    free_global_dofs: np.ndarray,
    tolerance_abs: float = 1.0e-6,
    tolerance_rel: float = 1.0e-4,
    max_iterations: int = 400,
    restart: int = 80,
    equilibrate: bool = True,
) -> dict[str, Any]:
    """GMRES with nodal block Jacobi preconditioner, optional equilibration."""
    started = __import__("time").perf_counter()
    csr = k_ff.tocsr()
    n = int(csr.shape[0])
    rhs_np = np.asarray(rhs, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    threshold = max(float(tolerance_abs), float(tolerance_rel) * max(rhs_inf, 1.0))
    free = np.asarray(free_global_dofs, dtype=np.int64)
    k_mat = csr
    rhs_work = rhs_np
    scale = np.ones(n, dtype=np.float64)
    equilibration_meta: dict[str, Any] = {"applied": False}
    if equilibrate:
        k_mat, rhs_work, scale, equilibration_meta = symmetric_sqrt_diagonal_scaling(csr, rhs_np)
    try:
        block_inverse, preconditioner_meta = build_node_block_jacobi_preconditioner(
            k_mat,
            free_global_dofs=free,
        )
    except Exception as exc:
        return {
            "backend": "cpu_block_jacobi_gmres",
            "converged": False,
            "breakdown": "block_jacobi_preconditioner_build_failed",
            "error_excerpt": repr(exc)[:600],
            "solve_seconds": __import__("time").perf_counter() - started,
            "equilibration": equilibration_meta,
        }

    m_op = LinearOperator(
        (n, n),
        matvec=lambda vector: block_inverse @ np.asarray(vector, dtype=np.float64),
        dtype=np.float64,
    )
    try:
        solution_scaled, info = gmres(
            k_mat,
            rhs_work,
            M=m_op,
            rtol=float(tolerance_rel),
            atol=float(tolerance_abs),
            maxiter=int(max_iterations),
            restart=int(restart),
        )
    except Exception as exc:
        return {
            "backend": "cpu_block_jacobi_gmres",
            "converged": False,
            "breakdown": "block_jacobi_gmres_failed",
            "error_excerpt": repr(exc)[:600],
            "solve_seconds": __import__("time").perf_counter() - started,
            "equilibration": equilibration_meta,
        }
    solution = unscale_solution(np.asarray(solution_scaled, dtype=np.float64), scale)
    residual = np.asarray(csr @ solution - rhs_np, dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    converged = bool(np.isfinite(residual_inf) and residual_inf <= threshold)
    return {
        "backend": "cpu_block_jacobi_gmres",
        "preconditioner": "node_block_jacobi_equilibrated"
        if equilibrate
        else "node_block_jacobi",
        "preconditioner_build_seconds": preconditioner_meta.get("build_seconds"),
        "preconditioner_singular_block_count": preconditioner_meta.get("singular_block_count"),
        "converged": converged,
        "gmres_info": int(info),
        "residual_inf_n": residual_inf,
        "solve_seconds": __import__("time").perf_counter() - started,
        "solution": solution,
        "equilibration": equilibration_meta,
    }


def solve_cpu_ilu_gmres(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    tolerance_abs: float = 1.0e-8,
    tolerance_rel: float = 1.0e-8,
    max_iterations: int = 300,
    restart: int = 50,
    drop_tol: float = 1.0e-5,
    fill_factor: float = 30.0,
    free_global_dofs: np.ndarray | None = None,
    equilibrate: bool = True,
) -> dict[str, Any]:
    """Host-only ILU-GMRES with optional equilibration and nodal block Jacobi."""
    started = __import__("time").perf_counter()
    csr = k_ff.tocsr()
    n = int(csr.shape[0])
    rhs_np = np.asarray(rhs, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    threshold = max(float(tolerance_abs), float(tolerance_rel) * max(rhs_inf, 1.0))
    k_mat = csr
    rhs_work = rhs_np
    scale = np.ones(n, dtype=np.float64)
    equilibration_meta: dict[str, Any] = {"applied": False}
    if equilibrate:
        k_mat, rhs_work, scale, equilibration_meta = symmetric_sqrt_diagonal_scaling(csr, rhs_np)
    preconditioner_name = "scipy_spilu_host"
    ilu_started = __import__("time").perf_counter()
    try:
        ilu = spilu(
            k_mat.tocsc(),
            drop_tol=float(drop_tol),
            fill_factor=float(fill_factor),
        )
    except Exception as exc:
        return {
            "backend": "cpu_ilu_gmres",
            "converged": False,
            "breakdown": "cpu_ilu_factorization_failed",
            "error_excerpt": repr(exc)[:600],
            "ilu_factorization_seconds": __import__("time").perf_counter() - ilu_started,
            "solve_seconds": __import__("time").perf_counter() - started,
            "equilibration": equilibration_meta,
        }
    ilu_seconds = __import__("time").perf_counter() - ilu_started

    def ilu_precondition(vector: np.ndarray) -> np.ndarray:
        return np.asarray(ilu.solve(np.asarray(vector, dtype=np.float64)), dtype=np.float64)

    preconditioner_build_seconds = ilu_seconds
    if free_global_dofs is not None and int(free_global_dofs.size) == n:
        block_inverse, block_meta = build_node_block_jacobi_preconditioner(
            k_mat,
            free_global_dofs=np.asarray(free_global_dofs, dtype=np.int64),
        )
        preconditioner_build_seconds += float(block_meta.get("build_seconds") or 0.0)

        def precondition(vector: np.ndarray) -> np.ndarray:
            return np.asarray(block_inverse @ ilu_precondition(vector), dtype=np.float64)

        preconditioner_name = "node_block_jacobi_plus_equilibrated_spilu_host"
    else:
        precondition = ilu_precondition
        if equilibrate:
            preconditioner_name = "equilibrated_spilu_host"

    m_op = LinearOperator((n, n), matvec=precondition, dtype=np.float64)
    try:
        solution_scaled, info = gmres(
            k_mat,
            rhs_work,
            M=m_op,
            rtol=float(tolerance_rel),
            atol=float(tolerance_abs),
            maxiter=int(max_iterations),
            restart=int(restart),
        )
    except Exception as exc:
        return {
            "backend": "cpu_ilu_gmres",
            "converged": False,
            "breakdown": "cpu_ilu_gmres_failed",
            "error_excerpt": repr(exc)[:600],
            "solve_seconds": __import__("time").perf_counter() - started,
            "equilibration": equilibration_meta,
        }
    solution = unscale_solution(np.asarray(solution_scaled, dtype=np.float64), scale)
    residual = np.asarray(csr @ solution - rhs_np, dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    converged = bool(np.isfinite(residual_inf) and residual_inf <= threshold)
    return {
        "backend": "cpu_ilu_gmres",
        "preconditioner": preconditioner_name,
        "ilu_factorization_seconds": ilu_seconds,
        "preconditioner_build_seconds": preconditioner_build_seconds,
        "converged": converged,
        "gmres_info": int(info),
        "residual_inf_n": residual_inf,
        "solve_seconds": __import__("time").perf_counter() - started,
        "solution": solution,
        "equilibration": equilibration_meta,
    }


def solve_host_ilu_device_gmres(
    k_ff: Any,
    rhs: np.ndarray,
    *,
    tolerance_abs: float = 0.0,
    tolerance_rel: float = 0.0,
    max_iterations: int = 4000,
    restart: int = 50,
    drop_tol: float = 1.0e-6,
    fill_factor: float = 20.0,
    require_convergence: bool = False,
    equilibrate: bool = True,
    free_global_dofs: np.ndarray | None = None,
    regularization_factor: float = 0.0,
) -> dict[str, Any]:
    """GMRES with host ILU preconditioner and ROCm torch sparse matvec when available."""
    import torch  # type: ignore

    if not torch.cuda.is_available():
        raise RuntimeError("No HIP GPUs are available")
    device = torch.device("cuda:0")
    started = __import__("time").perf_counter()
    csr = k_ff.tocsr()
    n = int(csr.shape[0])
    rhs_np = np.asarray(rhs, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    threshold = max(float(tolerance_abs), float(tolerance_rel) * max(rhs_inf, 1.0))
    regularization = 0.0
    if float(regularization_factor) > 0.0:
        diag = np.asarray(csr.diagonal(), dtype=np.float64)
        regularization = float(regularization_factor) * max(float(np.mean(np.abs(diag))), 1.0)
    k_mat = csr + eye(n, format="csr") * regularization if regularization > 0.0 else csr
    rhs_work = rhs_np
    scale = np.ones(n, dtype=np.float64)
    equilibration_meta: dict[str, Any] = {"applied": False}
    if equilibrate:
        k_mat, rhs_work, scale, equilibration_meta = symmetric_sqrt_diagonal_scaling(csr, rhs_np)
    base_row: dict[str, Any] = {
        "backend": "rocm_torch_sparse_host_ilu_device_gmres",
        "device": str(device),
        "converged": False,
        "solver": "gmres",
        "preconditioner": "equilibrated_scipy_spilu_host",
        "drop_tol": float(drop_tol),
        "fill_factor": float(fill_factor),
        "restart": int(restart),
        "max_iterations": int(max_iterations),
        "residual_inf_n": float("inf"),
        "rhs_inf_n": rhs_inf,
        "threshold_n": threshold,
        "cpu_solver_fallback_detected": False,
        "matvec_backend": "rocm_torch_sparse_csr",
        "preconditioner_apply_backend": "scipy_spilu_host",
        "regularization": float(regularization),
        "equilibration": equilibration_meta,
    }
    try:
        ilu = spilu(k_mat.tocsc(), drop_tol=float(drop_tol), fill_factor=float(fill_factor))
    except Exception as exc:
        row = dict(base_row)
        row.update(
            {
                "breakdown": "host_ilu_factorization_failed",
                "error_excerpt": repr(exc)[:600],
                "solve_seconds": __import__("time").perf_counter() - started,
            }
        )
        return row
    k_csr = k_mat.tocsr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        matrix = torch.sparse_csr_tensor(
            torch.as_tensor(k_csr.indptr.astype(np.int64), device=device),
            torch.as_tensor(k_csr.indices.astype(np.int64), device=device),
            torch.as_tensor(k_csr.data.astype(np.float64), device=device),
            size=k_csr.shape,
            dtype=torch.float64,
            device=device,
        )

    def matvec(vector: np.ndarray) -> np.ndarray:
        vec = torch.as_tensor(np.asarray(vector, dtype=np.float64), dtype=torch.float64, device=device)
        out = torch.sparse.mm(matrix, vec.reshape((-1, 1))).reshape((-1,))
        if hasattr(torch.cuda, "synchronize"):
            torch.cuda.synchronize()
        return np.asarray(out.detach().cpu().numpy(), dtype=np.float64)

    def ilu_precondition(vector: np.ndarray) -> np.ndarray:
        return np.asarray(ilu.solve(np.asarray(vector, dtype=np.float64)), dtype=np.float64)

    if free_global_dofs is not None and int(free_global_dofs.size) == n:
        block_inverse, block_meta = build_node_block_jacobi_preconditioner(
            k_csr,
            free_global_dofs=np.asarray(free_global_dofs, dtype=np.int64),
        )
        base_row["preconditioner_build_seconds"] = block_meta.get("build_seconds")

        def precondition(vector: np.ndarray) -> np.ndarray:
            return np.asarray(block_inverse @ ilu_precondition(vector), dtype=np.float64)

        base_row["preconditioner"] = "node_block_jacobi_plus_equilibrated_spilu_host"
    else:
        precondition = ilu_precondition

    a_op = LinearOperator((n, n), matvec=matvec, dtype=np.float64)
    m_op = LinearOperator((n, n), matvec=precondition, dtype=np.float64)
    try:
        solution_scaled, info = gmres(
            a_op,
            rhs_work,
            M=m_op,
            rtol=float(tolerance_rel) if tolerance_rel > 0.0 else 1.0e-12,
            atol=float(tolerance_abs),
            maxiter=int(max_iterations),
            restart=int(restart),
        )
    except Exception as exc:
        row = dict(base_row)
        row.update(
            {
                "breakdown": "host_ilu_device_gmres_failed",
                "error_excerpt": repr(exc)[:600],
                "solve_seconds": __import__("time").perf_counter() - started,
            }
        )
        return row
    solution = unscale_solution(np.asarray(solution_scaled, dtype=np.float64), scale)
    residual = np.asarray(csr @ solution - rhs_np, dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    converged = bool(np.isfinite(residual_inf) and residual_inf <= threshold)
    if require_convergence and not converged:
        row = dict(base_row)
        row.update(
            {
                "breakdown": "host_ilu_device_gmres_linear_residual_gate_not_met",
                "gmres_info": int(info),
                "residual_inf_n": residual_inf,
                "solve_seconds": __import__("time").perf_counter() - started,
            }
        )
        return row
    row = dict(base_row)
    row.update(
        {
            "converged": converged,
            "gmres_info": int(info),
            "residual_inf_n": residual_inf,
            "solve_seconds": __import__("time").perf_counter() - started,
            "solution": solution,
        }
    )
    return row


def _linear_solution_acceptable(
    *,
    solution: np.ndarray,
    rhs: np.ndarray,
    residual_inf: Any,
    converged: bool,
    relative_tolerance: float = 1.0e-8,
) -> bool:
    if solution.size != rhs.size or not np.all(np.isfinite(solution)):
        return False
    try:
        residual_value = float(residual_inf)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(residual_value):
        return False
    rhs_inf = float(np.max(np.abs(rhs))) if rhs.size else 0.0
    threshold = max(1.0e-8, float(relative_tolerance) * max(rhs_inf, 1.0))
    return bool(converged or residual_value <= threshold)


def solve_newton_correction(
    k_ff: Any,
    residual: np.ndarray,
    *,
    prefer_host_ilu: bool = True,
    free_global_dofs: np.ndarray | None = None,
    solver_profile: str = "production",
    direct_regularization_factor: float | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    rhs = -np.asarray(residual, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs))) if rhs.size else 0.0
    newton_relative_tolerance = 1.0e-4
    profile = str(solver_profile or "production").strip()
    if profile not in {
        "production",
        "regularized_direct",
        "block_jacobi_gmres",
        "host_ilu_device_gmres",
    }:
        raise ValueError(
            "solver_profile must be 'production', 'regularized_direct', "
            "'block_jacobi_gmres', or 'host_ilu_device_gmres'"
        )
    if profile == "regularized_direct":
        solve_started = time.perf_counter()
        regularization_factor = (
            1.0e-12
            if direct_regularization_factor is None
            else float(direct_regularization_factor)
        )
        solution, regularization, linear_residual_inf = solve_sparse_with_iterative_refinement(
            k_ff,
            rhs,
            regularization_factor=regularization_factor,
        )
        return solution, {
            "linear_solver_backend": "scipy_sparse_spsolve_cpu_regularized_refined",
            "linear_solver_profile": profile,
            "linear_solver_regularization_factor": regularization_factor,
            "linear_solver_converged": bool(np.isfinite(linear_residual_inf)),
            "linear_solver_residual_inf_n": linear_residual_inf,
            "linear_solver_regularization": regularization,
            "linear_solver_seconds": time.perf_counter() - solve_started,
            "linear_solver_direct_profile_bypassed_iterative_attempts": True,
            "linear_solver_iterative_refinement_enabled": True,
            "linear_solver_rhs_inf_n": rhs_inf,
        }
    if profile == "block_jacobi_gmres":
        if free_global_dofs is None:
            raise ValueError("block_jacobi_gmres profile requires free_global_dofs")
        row = solve_block_jacobi_gmres(
            k_ff,
            rhs,
            free_global_dofs=np.asarray(free_global_dofs, dtype=np.int64),
            tolerance_abs=1.0e-6,
            tolerance_rel=newton_relative_tolerance,
            max_iterations=240,
            restart=80,
            equilibrate=True,
        )
        solution = row.get("solution")
        if not isinstance(solution, np.ndarray):
            return np.full_like(rhs, np.nan, dtype=np.float64), {
                "linear_solver_backend": row.get("backend"),
                "linear_solver_profile": profile,
                "linear_solver_converged": False,
                "linear_solver_breakdown": row.get("breakdown"),
                "linear_solver_error_excerpt": row.get("error_excerpt"),
                "linear_solver_seconds": row.get("solve_seconds"),
                "linear_solver_rhs_inf_n": rhs_inf,
                "linear_solver_diagnostic_profile_bypassed_ilu": True,
            }
        return np.asarray(solution, dtype=np.float64), {
            "linear_solver_backend": row.get("backend"),
            "linear_solver_profile": profile,
            "linear_solver_preconditioner": row.get("preconditioner"),
            "linear_solver_converged": bool(row.get("converged")),
            "linear_solver_residual_inf_n": row.get("residual_inf_n"),
            "linear_solver_seconds": row.get("solve_seconds"),
            "linear_solver_attempt": "block_jacobi_gmres_only",
            "linear_solver_rhs_inf_n": rhs_inf,
            "linear_solver_equilibration": row.get("equilibration"),
            "linear_solver_diagnostic_profile_bypassed_ilu": True,
        }
    if profile == "host_ilu_device_gmres":
        if free_global_dofs is None:
            raise ValueError("host_ilu_device_gmres profile requires free_global_dofs")
        try:
            row = solve_host_ilu_device_gmres(
                k_ff,
                rhs,
                tolerance_abs=1.0e-6,
                tolerance_rel=newton_relative_tolerance,
                max_iterations=800,
                restart=80,
                drop_tol=1.0e-4,
                fill_factor=40.0,
                require_convergence=False,
                equilibrate=True,
                free_global_dofs=np.asarray(free_global_dofs, dtype=np.int64),
                regularization_factor=1.0e-8,
            )
        except Exception as exc:
            return np.full_like(rhs, np.nan, dtype=np.float64), {
                "linear_solver_backend": "rocm_torch_sparse_host_ilu_device_gmres",
                "linear_solver_profile": profile,
                "linear_solver_converged": False,
                "linear_solver_breakdown": "host_ilu_device_gmres_unavailable",
                "linear_solver_error_excerpt": repr(exc)[:600],
                "linear_solver_rhs_inf_n": rhs_inf,
                "linear_solver_gpu_first_profile": True,
                "linear_solver_cpu_attempt_bypassed": True,
            }
        solution = row.get("solution")
        if not isinstance(solution, np.ndarray):
            return np.full_like(rhs, np.nan, dtype=np.float64), {
                "linear_solver_backend": row.get("backend"),
                "linear_solver_profile": profile,
                "linear_solver_preconditioner": row.get("preconditioner"),
                "linear_solver_converged": False,
                "linear_solver_breakdown": row.get("breakdown")
                or "host_ilu_device_gmres_solution_missing",
                "linear_solver_error_excerpt": row.get("error_excerpt"),
                "linear_solver_seconds": row.get("solve_seconds"),
                "linear_solver_rhs_inf_n": rhs_inf,
                "linear_solver_gpu_first_profile": True,
                "linear_solver_cpu_attempt_bypassed": True,
            }
        return np.asarray(solution, dtype=np.float64), {
            "linear_solver_backend": row.get("backend"),
            "linear_solver_profile": profile,
            "linear_solver_preconditioner": row.get("preconditioner"),
            "linear_solver_converged": bool(row.get("converged")),
            "linear_solver_residual_inf_n": row.get("residual_inf_n"),
            "linear_solver_seconds": row.get("solve_seconds"),
            "linear_solver_attempt": "host_ilu_device_gmres_only",
            "linear_solver_rhs_inf_n": rhs_inf,
            "linear_solver_equilibration": row.get("equilibration"),
            "linear_solver_gpu_first_profile": True,
            "linear_solver_cpu_attempt_bypassed": True,
        }
    attempts: list[dict[str, Any]] = []
    if free_global_dofs is not None and int(free_global_dofs.size) > 0:
        attempts.append(
            {
                "label": "cpu_ilu_gmres_equilibrated_block_jacobi",
                "runner": lambda: solve_cpu_ilu_gmres(
                    k_ff,
                    rhs,
                    tolerance_abs=1.0e-6,
                    tolerance_rel=newton_relative_tolerance,
                    max_iterations=800,
                    restart=80,
                    drop_tol=1.0e-4,
                    fill_factor=40.0,
                    free_global_dofs=free_global_dofs,
                    equilibrate=True,
                ),
            }
        )
        attempts.append(
            {
                "label": "cpu_block_jacobi_gmres_equilibrated",
                "runner": lambda: solve_block_jacobi_gmres(
                    k_ff,
                    rhs,
                    free_global_dofs=np.asarray(free_global_dofs, dtype=np.int64),
                    tolerance_abs=1.0e-6,
                    tolerance_rel=newton_relative_tolerance,
                    max_iterations=800,
                    restart=80,
                    equilibrate=True,
                ),
            }
        )
    attempts.extend(
        [
            {
                "label": "cpu_ilu_gmres_equilibrated_ilu_only",
                "runner": lambda: solve_cpu_ilu_gmres(
                    k_ff,
                    rhs,
                    tolerance_abs=1.0e-6,
                    tolerance_rel=newton_relative_tolerance,
                    max_iterations=800,
                    restart=80,
                    drop_tol=1.0e-4,
                    fill_factor=60.0,
                    free_global_dofs=None,
                    equilibrate=True,
                ),
            },
        ]
    )
    if prefer_host_ilu and free_global_dofs is not None:
        attempts.append(
            {
                "label": "host_ilu_device_gmres_equilibrated_block_jacobi",
                "runner": lambda: solve_host_ilu_device_gmres(
                    k_ff,
                    rhs,
                    tolerance_abs=1.0e-6,
                    tolerance_rel=newton_relative_tolerance,
                    max_iterations=800,
                    restart=80,
                    drop_tol=1.0e-4,
                    fill_factor=40.0,
                    require_convergence=False,
                    equilibrate=True,
                    free_global_dofs=free_global_dofs,
                ),
            }
        )
    best_row: dict[str, Any] | None = None
    best_solution: np.ndarray | None = None
    best_residual = float("inf")
    for attempt in attempts:
        row = attempt["runner"]()
        solution = row.get("solution")
        if not isinstance(solution, np.ndarray):
            continue
        solution = np.asarray(solution, dtype=np.float64)
        residual_inf = float(row.get("residual_inf_n") or float("inf"))
        if not np.all(np.isfinite(solution)):
            continue
        if residual_inf < best_residual:
            best_residual = residual_inf
            best_solution = solution
            best_row = {
                **row,
                "linear_solver_attempt": attempt["label"],
            }
        if _linear_solution_acceptable(
            solution=solution,
            rhs=rhs,
            residual_inf=residual_inf,
            converged=bool(row.get("converged")),
            relative_tolerance=newton_relative_tolerance,
        ):
            return solution, {
                "linear_solver_backend": row.get("backend"),
                "linear_solver_profile": profile,
                "linear_solver_preconditioner": row.get("preconditioner"),
                "linear_solver_converged": bool(row.get("converged")),
                "linear_solver_residual_inf_n": residual_inf,
                "linear_solver_seconds": row.get("solve_seconds"),
                "linear_solver_attempt": attempt["label"],
                "linear_solver_rhs_inf_n": rhs_inf,
                "linear_solver_equilibration": row.get("equilibration"),
            }
    if best_solution is not None and best_row is not None:
        return best_solution, {
            "linear_solver_backend": best_row.get("backend"),
            "linear_solver_profile": profile,
            "linear_solver_preconditioner": best_row.get("preconditioner"),
            "linear_solver_converged": bool(best_row.get("converged")),
            "linear_solver_residual_inf_n": best_row.get("residual_inf_n"),
            "linear_solver_seconds": best_row.get("solve_seconds"),
            "linear_solver_attempt": best_row.get("linear_solver_attempt"),
            "linear_solver_rhs_inf_n": rhs_inf,
            "linear_solver_best_effort": True,
            "linear_solver_equilibration": best_row.get("equilibration"),
        }
    solution, regularization, linear_residual_inf = solve_sparse_with_iterative_refinement(
        k_ff,
        rhs,
        regularization_factor=1.0e-12,
    )
    return solution, {
        "linear_solver_backend": "scipy_sparse_spsolve_cpu_regularized_refined",
        "linear_solver_profile": profile,
        "linear_solver_converged": bool(np.isfinite(linear_residual_inf)),
        "linear_solver_residual_inf_n": linear_residual_inf,
        "linear_solver_regularization": regularization,
        "linear_solver_fallback_from_host_ilu": bool(prefer_host_ilu),
        "linear_solver_iterative_refinement_enabled": True,
        "linear_solver_rhs_inf_n": rhs_inf,
    }
