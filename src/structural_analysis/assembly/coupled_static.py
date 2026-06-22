"""Narrow frame-shell-material coupled assembly seed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
    newton_raphson_vector,
)


@dataclass(frozen=True)
class FrameShellMaterialCoupledProblem:
    """Two free DOFs with frame, shell, and material-coupling tangent terms."""

    case_id: str
    frame_axial_stiffness_kn_per_m: float
    frame_axial_cubic_kn_per_m3: float
    shell_shear_stiffness_kn_per_m: float
    shell_shear_cubic_kn_per_m3: float
    material_coupling_stiffness_kn_per_m: float
    external_force_kn: tuple[float, float]
    initial_free_displacements_m: tuple[float, float]

    def reference_force_scale(self) -> float:
        return max(max(abs(force) for force in self.external_force_kn), 1.0)


@dataclass(frozen=True)
class FrameShellMaterialCoupledState:
    residual_formula: str
    free_dof_labels: tuple[str, str]
    free_displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    component_forces_kn: tuple[dict[str, Any], ...]


def default_frame_shell_material_coupled_problem() -> FrameShellMaterialCoupledProblem:
    return FrameShellMaterialCoupledProblem(
        case_id="phase2_frame_shell_material_coupled_2dof_seed",
        frame_axial_stiffness_kn_per_m=180.0,
        frame_axial_cubic_kn_per_m3=40.0,
        shell_shear_stiffness_kn_per_m=120.0,
        shell_shear_cubic_kn_per_m3=25.0,
        material_coupling_stiffness_kn_per_m=12.0,
        external_force_kn=(50.0, 20.0),
        initial_free_displacements_m=(0.0, 0.0),
    )


def assemble_frame_shell_material_coupled_state(
    problem: FrameShellMaterialCoupledProblem,
    free_displacements_m: np.ndarray,
) -> FrameShellMaterialCoupledState:
    """Assemble R=F_internal-F_external with a symmetric consistent tangent."""
    u_frame = float(free_displacements_m[0])
    u_shell = float(free_displacements_m[1])
    frame_force = (
        problem.frame_axial_stiffness_kn_per_m * u_frame
        + problem.frame_axial_cubic_kn_per_m3 * u_frame**3
    )
    shell_force = (
        problem.shell_shear_stiffness_kn_per_m * u_shell
        + problem.shell_shear_cubic_kn_per_m3 * u_shell**3
    )
    coupling_frame_force = problem.material_coupling_stiffness_kn_per_m * u_shell
    coupling_shell_force = problem.material_coupling_stiffness_kn_per_m * u_frame
    internal = np.array(
        [
            frame_force + coupling_frame_force,
            shell_force + coupling_shell_force,
        ],
        dtype=float,
    )
    external = np.array(problem.external_force_kn, dtype=float)
    jacobian = np.array(
        [
            [
                problem.frame_axial_stiffness_kn_per_m
                + 3.0 * problem.frame_axial_cubic_kn_per_m3 * u_frame**2,
                problem.material_coupling_stiffness_kn_per_m,
            ],
            [
                problem.material_coupling_stiffness_kn_per_m,
                problem.shell_shear_stiffness_kn_per_m
                + 3.0 * problem.shell_shear_cubic_kn_per_m3 * u_shell**2,
            ],
        ],
        dtype=float,
    )
    return FrameShellMaterialCoupledState(
        residual_formula=RESIDUAL_FORMULA,
        free_dof_labels=("frame_node_ux", "shell_node_uy"),
        free_displacements_m=np.array(free_displacements_m, dtype=float),
        residual_kn=internal - external,
        jacobian_kn_per_m=jacobian,
        internal_forces_kn=internal,
        external_forces_kn=external,
        component_forces_kn=(
            {
                "component": "frame_axial_material",
                "dof": "frame_node_ux",
                "force_kn": frame_force,
                "tangent_kn_per_m": jacobian[0, 0],
            },
            {
                "component": "shell_diaphragm_shear_material",
                "dof": "shell_node_uy",
                "force_kn": shell_force,
                "tangent_kn_per_m": jacobian[1, 1],
            },
            {
                "component": "frame_shell_material_coupling",
                "dofs": ["frame_node_ux", "shell_node_uy"],
                "frame_force_kn": coupling_frame_force,
                "shell_force_kn": coupling_shell_force,
                "off_diagonal_tangent_kn_per_m": problem.material_coupling_stiffness_kn_per_m,
            },
        ),
    )


def finite_difference_coupled_jacobian_check(
    problem: FrameShellMaterialCoupledProblem,
    free_displacements_m: np.ndarray,
    *,
    epsilon: float = 1.0e-7,
) -> dict[str, Any]:
    base = assemble_frame_shell_material_coupled_state(problem, free_displacements_m)
    analytic = base.jacobian_kn_per_m.copy()
    numeric = np.zeros_like(analytic)
    for dof_index in range(2):
        forward = np.array(free_displacements_m, dtype=float)
        backward = np.array(free_displacements_m, dtype=float)
        forward[dof_index] += epsilon
        backward[dof_index] -= epsilon
        forward_residual = assemble_frame_shell_material_coupled_state(problem, forward).residual_kn
        backward_residual = assemble_frame_shell_material_coupled_state(problem, backward).residual_kn
        numeric[:, dof_index] = (forward_residual - backward_residual) / (2.0 * epsilon)
    max_abs_error = float(np.max(np.abs(numeric - analytic)))
    return {
        "free_dof_count": 2,
        "finite_difference_epsilon": epsilon,
        "analytic_jacobian_kn_per_m": analytic.tolist(),
        "finite_difference_jacobian_kn_per_m": numeric.tolist(),
        "max_abs_error": max_abs_error,
        "pass": max_abs_error <= 1.0e-6,
    }


@dataclass(frozen=True)
class FrameShellMaterialCoupledNewtonAdapter:
    problem: FrameShellMaterialCoupledProblem

    @property
    def case_id(self) -> str:
        return self.problem.case_id

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.array(self.problem.initial_free_displacements_m, dtype=float)

    def assemble(self, free_displacements_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_frame_shell_material_coupled_state(
            self.problem,
            free_displacements_m,
        )
        return state.residual_kn, state.jacobian_kn_per_m


def solve_frame_shell_material_coupled(
    problem: FrameShellMaterialCoupledProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> tuple[Any, FrameShellMaterialCoupledState]:
    adapter = FrameShellMaterialCoupledNewtonAdapter(problem=problem)
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    final_state = assemble_frame_shell_material_coupled_state(
        problem,
        solution.free_displacements_m,
    )
    return solution, final_state
