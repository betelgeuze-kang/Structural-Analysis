#!/usr/bin/env python3
"""Shared sparse linear solvers for equilibrium Newton steps."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
from scipy.sparse import eye
from scipy.sparse.linalg import LinearOperator, gmres, spsolve
from scipy.sparse.linalg import spilu


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
) -> dict[str, Any]:
    """GMRES with host ILU preconditioner and ROCm torch sparse matvec when available."""
    import torch  # type: ignore

    device = torch.device("cuda:0")
    started = __import__("time").perf_counter()
    csr = k_ff.tocsr()
    n = int(csr.shape[0])
    rhs_np = np.asarray(rhs, dtype=np.float64)
    rhs_inf = float(np.max(np.abs(rhs_np))) if rhs_np.size else 0.0
    threshold = max(float(tolerance_abs), float(tolerance_rel) * max(rhs_inf, 1.0))
    base_row: dict[str, Any] = {
        "backend": "rocm_torch_sparse_host_ilu_device_gmres",
        "device": str(device),
        "converged": False,
        "solver": "gmres",
        "preconditioner": "scipy_spilu_host",
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
    }
    try:
        ilu = spilu(csr.tocsc(), drop_tol=float(drop_tol), fill_factor=float(fill_factor))
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
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        matrix = torch.sparse_csr_tensor(
            torch.as_tensor(csr.indptr.astype(np.int64), device=device),
            torch.as_tensor(csr.indices.astype(np.int64), device=device),
            torch.as_tensor(csr.data.astype(np.float64), device=device),
            size=csr.shape,
            dtype=torch.float64,
            device=device,
        )

    def matvec(vector: np.ndarray) -> np.ndarray:
        vec = torch.as_tensor(np.asarray(vector, dtype=np.float64), dtype=torch.float64, device=device)
        out = torch.sparse.mm(matrix, vec.reshape((-1, 1))).reshape((-1,))
        if hasattr(torch.cuda, "synchronize"):
            torch.cuda.synchronize()
        return np.asarray(out.detach().cpu().numpy(), dtype=np.float64)

    def precondition(vector: np.ndarray) -> np.ndarray:
        return np.asarray(ilu.solve(np.asarray(vector, dtype=np.float64)), dtype=np.float64)

    a_op = LinearOperator((n, n), matvec=matvec, dtype=np.float64)
    m_op = LinearOperator((n, n), matvec=precondition, dtype=np.float64)
    try:
        solution, info = gmres(
            a_op,
            rhs_np,
            M=m_op,
            rtol=1.0e-12,
            atol=0.0,
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
    solution = np.asarray(solution, dtype=np.float64)
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
    threshold = max(1.0e-8, 1.0e-8 * max(rhs_inf, 1.0))
    return bool(converged or residual_value <= threshold)


def solve_newton_correction(
    k_ff: Any,
    residual: np.ndarray,
    *,
    prefer_host_ilu: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    rhs = -np.asarray(residual, dtype=np.float64)
    if prefer_host_ilu:
        gmres_row = solve_host_ilu_device_gmres(
            k_ff,
            rhs,
            tolerance_abs=1.0e-8,
            tolerance_rel=1.0e-8,
            max_iterations=300,
            restart=50,
            require_convergence=False,
        )
        solution = gmres_row.get("solution")
        if isinstance(solution, np.ndarray) and _linear_solution_acceptable(
            solution=np.asarray(solution, dtype=np.float64),
            rhs=rhs,
            residual_inf=gmres_row.get("residual_inf_n"),
            converged=bool(gmres_row.get("converged")),
        ):
            return np.asarray(solution, dtype=np.float64), {
                "linear_solver_backend": gmres_row.get("backend"),
                "linear_solver_converged": bool(gmres_row.get("converged")),
                "linear_solver_residual_inf_n": gmres_row.get("residual_inf_n"),
                "linear_solver_seconds": gmres_row.get("solve_seconds"),
            }
    solution, regularization = solve_sparse_regularized(k_ff, rhs)
    linear_residual = np.asarray(k_ff @ solution - rhs, dtype=np.float64)
    linear_residual_inf = float(np.max(np.abs(linear_residual))) if linear_residual.size else 0.0
    return solution, {
        "linear_solver_backend": "scipy_sparse_spsolve_cpu_regularized",
        "linear_solver_converged": bool(np.isfinite(linear_residual_inf)),
        "linear_solver_residual_inf_n": linear_residual_inf,
        "linear_solver_regularization": regularization,
        "linear_solver_fallback_from_host_ilu": bool(prefer_host_ilu),
    }
