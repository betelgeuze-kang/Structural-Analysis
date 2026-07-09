"""Public analysis drivers that own solver-path selection."""

from structural_analysis.analyses.linear_static import (
    AUTHORITATIVE_CPU_SOLVER_ID,
    run_authoritative_linear_static,
)

__all__ = ["AUTHORITATIVE_CPU_SOLVER_ID", "run_authoritative_linear_static"]
