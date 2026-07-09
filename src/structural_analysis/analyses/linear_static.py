"""Single authoritative CPU linear-static analysis entry point."""

from __future__ import annotations

from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.linear.static import (
    LinearStaticSolution,
    solve_linear_static,
    solve_linear_static_sparse,
)

AUTHORITATIVE_CPU_SOLVER_ID = "authoritative_cpu_linear_fea_3d_v1"
SUPPORTED_MATRIX_BACKENDS = {
    "numpy_linalg_solve_dense",
    "scipy_sparse_spsolve_cpu",
}


def run_authoritative_linear_static(
    model: CanonicalModel,
    *,
    tolerance: float,
    matrix_backend: str,
    load_case: str | None = None,
) -> LinearStaticSolution:
    if matrix_backend not in SUPPORTED_MATRIX_BACKENDS:
        raise ValueError(f"Unsupported authoritative CPU matrix backend: {matrix_backend}")
    if matrix_backend == "scipy_sparse_spsolve_cpu":
        return solve_linear_static_sparse(
            model,
            tolerance=tolerance,
            load_case=load_case,
        )
    return solve_linear_static(model, tolerance=tolerance, load_case=load_case)
