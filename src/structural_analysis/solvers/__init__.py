"""Solver namespaces for linear, modal, buckling, and nonlinear adapters."""

from structural_analysis.solvers.equation_scaling import (
    EQUATION_SCALING_6DOF_VERSION,
    EquationScaling6DOF,
    EquationScaling6DOFError,
    build_equation_scaling_6dof,
    characteristic_length_from_coordinates,
)

__all__ = [
    "EQUATION_SCALING_6DOF_VERSION",
    "EquationScaling6DOF",
    "EquationScaling6DOFError",
    "build_equation_scaling_6dof",
    "characteristic_length_from_coordinates",
]
