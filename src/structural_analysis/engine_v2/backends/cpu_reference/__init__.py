"""Independent FP64 CPU reference backend for Engine v2."""

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (
    CPUReferenceError,
    LinearStaticOperator,
    LinearStaticResult,
    assemble_linear_static_operator,
    solve_linear_static,
    solve_linear_static_operator,
)

__all__ = [
    "CPUReferenceError",
    "LinearStaticOperator",
    "LinearStaticResult",
    "assemble_linear_static_operator",
    "solve_linear_static",
    "solve_linear_static_operator",
]
