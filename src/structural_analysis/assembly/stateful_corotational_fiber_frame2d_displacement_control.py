"""Transactional direct displacement control for corotational fiber frames.

The controlled free translational coordinate and the proportional load factor
are solved together.  Every trial is assembled from one immutable accepted
checkpoint; a step commits the complete material/frame state only after the
equilibrium, control, and correction gates all pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DAssembly,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    VECTOR_MATRIX_BACKEND,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-direct-displacement-control.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE = (
    "dense-augmented-consistent-direct-displacement-control.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA = (
    "[R_f(q,lambda);w*(q_control-q_target)]=0"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_LOAD_COLUMN = (
    "dR_f/dlambda=S_f*(K_fp*ubar_p-F_ref_f)"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH = canonical_hash(
    {
        "equilibrium": RESIDUAL_FORMULA,
        "augmented_residual": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA
        ),
        "load_factor_column": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_LOAD_COLUMN
        ),
        "tangent": "material_plus_geometric_consistent",
    }
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY = (
    "This internal candidate solves a bounded connected planar corotational fiber "
    "frame by dense augmented Newton with one free translational control DOF, a "
    "proportional reference-load factor, consistent material-plus-geometric "
    "tangents, proportional prescribed-support coupling, line search, exact failed "
    "step rollback, and accepted-checkpoint restart. It does not promote the unified "
    "public API, native sparse execution, follower or distributed loads, member "
    "releases or offsets, external Level 2 validation, design authority, or release "
    "readiness."
)


def _finite(value: Any, *, name: str, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized) or (positive and normalized <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return normalized


def _exact_float64_equal(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left, dtype="<f8")
    right_array = np.ascontiguousarray(right, dtype="<f8")
    return left_array.shape == right_array.shape and (
        left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


def _free_generalized_coordinates(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> np.ndarray:
    physical = np.asarray(checkpoint.global_displacements, dtype=np.float64)
    generalized = physical / problem.physical_coordinate_scale
    return np.ascontiguousarray(
        generalized[list(problem.free_global_dofs)],
        dtype=np.float64,
    )


def _controlled_free_index(
    problem: StatefulCorotationalFiberFrame2DProblem,
    control_global_dof: int,
) -> int:
    if type(control_global_dof) is not int:
        raise ValueError("control_global_dof must be an integer")
    if control_global_dof not in problem.free_global_dofs:
        raise ValueError("control_global_dof must be a free global DOF")
    if control_global_dof % 3 not in (0, 1):
        raise ValueError("control_global_dof must be translational UX or UY")
    return problem.free_global_dofs.index(control_global_dof)


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlConfig:
    residual_tolerance: float = 1.0e-10
    control_tolerance_m: float = 1.0e-12
    increment_tolerance_m: float = 1.0e-12
    load_factor_increment_tolerance: float = 1.0e-12
    maximum_iterations: int = 40
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    )
    load_factor_coordinate_scale_m: float = 1.0e-3
    matrix_backend: str = VECTOR_MATRIX_BACKEND

    def __post_init__(self) -> None:
        for name in (
            "residual_tolerance",
            "control_tolerance_m",
            "increment_tolerance_m",
            "load_factor_increment_tolerance",
            "load_factor_coordinate_scale_m",
        ):
            object.__setattr__(
                self,
                name,
                _finite(getattr(self, name), name=name, positive=True),
            )
        if (
            type(self.maximum_iterations) is not int
            or self.maximum_iterations < 0
            or self.maximum_iterations > 200
        ):
            raise ValueError("maximum_iterations must be an integer in [0, 200]")
        if not isinstance(self.line_search_alphas, tuple) or not (
            self.line_search_alphas
        ):
            raise ValueError("line_search_alphas must be a non-empty tuple")
        normalized_alphas: list[float] = []
        previous = math.inf
        for raw in self.line_search_alphas:
            alpha = _finite(raw, name="line_search alpha", positive=True)
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized_alphas.append(alpha)
            previous = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized_alphas))
        if self.matrix_backend != VECTOR_MATRIX_BACKEND:
            raise ValueError(
                "direct displacement control currently supports only the dense backend"
            )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlAssembly:
    frame_assembly: StatefulCorotationalFiberFrame2DAssembly
    augmented_coordinates_m: np.ndarray
    augmented_residual_kn: np.ndarray
    augmented_jacobian_kn_per_m: np.ndarray
    load_factor_residual_derivative_kn: np.ndarray
    control_error_m: float
    control_reference_m: float
    control_equation_scale_kn_per_m: float


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlStepProblem:
    problem: StatefulCorotationalFiberFrame2DProblem
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    control_global_dof: int
    target_control_displacement_m: float
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig

    def __post_init__(self) -> None:
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            self.problem,
            self.accepted_checkpoint,
        )
        _controlled_free_index(self.problem, self.control_global_dof)
        target = _finite(
            self.target_control_displacement_m,
            name="target_control_displacement_m",
        )
        object.__setattr__(self, "target_control_displacement_m", target)
        if type(self.config) is not (
            StatefulCorotationalFiberFrame2DDisplacementControlConfig
        ):
            raise ValueError("config type is invalid")
        accepted = self.initial_free_displacements_m()[self.control_free_index]
        if target == accepted:
            raise ValueError("target control displacement must differ from the parent")

    @property
    def control_free_index(self) -> int:
        return _controlled_free_index(self.problem, self.control_global_dof)

    @property
    def case_id(self) -> str:
        return (
            f"{self.problem.case_id}@direct-control-dof={self.control_global_dof}"
            f"@target={self.target_control_displacement_m:.12g}"
        )

    def initial_free_displacements_m(self) -> np.ndarray:
        return _free_generalized_coordinates(self.problem, self.accepted_checkpoint)

    def initial_augmented_coordinates_m(self) -> np.ndarray:
        free = self.initial_free_displacements_m()
        return np.concatenate(
            (
                free,
                np.asarray(
                    [
                        self.accepted_checkpoint.load_factor
                        * self.config.load_factor_coordinate_scale_m
                    ],
                    dtype=np.float64,
                ),
            )
        )

    def assemble(
        self,
        augmented_coordinates_m: Any,
    ) -> StatefulCorotationalFiberFrame2DDisplacementControlAssembly:
        try:
            coordinates = np.asarray(augmented_coordinates_m, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("augmented coordinates contain invalid values") from exc
        free_count = len(self.problem.free_global_dofs)
        if coordinates.shape != (free_count + 1,) or not np.all(
            np.isfinite(coordinates)
        ):
            raise ValueError("augmented coordinates have invalid shape or values")
        free = coordinates[:-1]
        load_factor = (
            float(coordinates[-1]) / self.config.load_factor_coordinate_scale_m
        )
        frame = assemble_stateful_corotational_fiber_frame2d(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=load_factor,
            trial_free_coordinates_m=free,
        )
        load_derivative = self.load_factor_residual_derivative_kn(frame)
        parent_control = self.initial_free_displacements_m()[self.control_free_index]
        control_reference = max(
            abs(self.target_control_displacement_m),
            abs(self.target_control_displacement_m - parent_control),
            1.0e-6,
        )
        control_scale = self.problem.reference_force_scale() / control_reference
        control_error = float(
            free[self.control_free_index] - self.target_control_displacement_m
        )
        residual = np.concatenate(
            (
                frame.residual_kn,
                np.asarray([control_scale * control_error], dtype=np.float64),
            )
        )
        jacobian = np.zeros((free_count + 1, free_count + 1), dtype=np.float64)
        jacobian[:-1, :-1] = frame.jacobian_kn_per_m
        jacobian[:-1, -1] = load_derivative / self.config.load_factor_coordinate_scale_m
        jacobian[-1, self.control_free_index] = control_scale
        return StatefulCorotationalFiberFrame2DDisplacementControlAssembly(
            frame_assembly=frame,
            augmented_coordinates_m=coordinates.copy(),
            augmented_residual_kn=residual,
            augmented_jacobian_kn_per_m=jacobian,
            load_factor_residual_derivative_kn=load_derivative,
            control_error_m=control_error,
            control_reference_m=control_reference,
            control_equation_scale_kn_per_m=control_scale,
        )

    def load_factor_residual_derivative_kn(
        self,
        frame_assembly: StatefulCorotationalFiberFrame2DAssembly,
    ) -> np.ndarray:
        free_dofs = self.problem.free_global_dofs
        prescribed_dofs = tuple(
            dof for dof, _value in self.problem.prescribed_displacements
        )
        physical_derivative = -self.problem.reference_external_load_vector().copy()
        if prescribed_dofs:
            terminal = self.problem.prescribed_displacement_vector(1.0)
            physical_derivative += (
                frame_assembly.consistent_tangent_global[
                    np.ix_(range(self.problem.global_dof_count), prescribed_dofs)
                ]
                @ terminal[list(prescribed_dofs)]
            )
        scale = self.problem.physical_coordinate_scale[list(free_dofs)]
        return np.ascontiguousarray(
            scale * physical_derivative[list(free_dofs)],
            dtype=np.float64,
        )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlSolution:
    status: str
    augmented_coordinates_m: np.ndarray
    free_displacements_m: np.ndarray
    load_factor: float
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    line_search_history: list[dict[str, Any]] = field(default_factory=list)
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)


def _relative_equilibrium(
    step_problem: StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    assembly: StatefulCorotationalFiberFrame2DDisplacementControlAssembly,
) -> float:
    residual = assembly.frame_assembly.residual_kn
    return float(np.linalg.norm(residual, ord=np.inf)) / (
        step_problem.problem.reference_force_scale()
    )


def _merit(
    step_problem: StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    assembly: StatefulCorotationalFiberFrame2DDisplacementControlAssembly,
) -> float:
    return max(
        _relative_equilibrium(step_problem, assembly),
        abs(assembly.control_error_m) / assembly.control_reference_m,
    )


def _blocked_solution(
    step_problem: StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    coordinates: np.ndarray,
    history: list[dict[str, Any]],
    line_search_history: list[dict[str, Any]],
    *,
    detail: str,
) -> StatefulCorotationalFiberFrame2DDisplacementControlSolution:
    free = coordinates[:-1].copy()
    load_factor = (
        float(coordinates[-1]) / step_problem.config.load_factor_coordinate_scale_m
    )
    return StatefulCorotationalFiberFrame2DDisplacementControlSolution(
        status="blocked",
        augmented_coordinates_m=coordinates.copy(),
        free_displacements_m=free,
        load_factor=load_factor,
        metrics={
            "case_id": step_problem.case_id,
            "control_mode": "direct_displacement_control",
            "terminal_reason": detail,
            "solver_executed": bool(history),
            "contract_pass": False,
            "residual_gate_passed": False,
            "control_gate_passed": False,
            "increment_gate_passed": False,
            "regularization_used": False,
            "fallback_used": False,
            "matrix_backend": VECTOR_MATRIX_BACKEND,
            "profile": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE
            ),
        },
        convergence_history=history,
        line_search_history=line_search_history,
        unsupported_features=[
            {
                "kind": "direct_displacement_control_solver_blocked",
                "detail": detail,
                "guard_outcome": "blocked",
            }
        ],
    )


def solve_stateful_corotational_fiber_frame2d_displacement_control(
    step_problem: StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
) -> StatefulCorotationalFiberFrame2DDisplacementControlSolution:
    """Solve one target control coordinate and proportional load factor together."""

    if type(step_problem) is not (
        StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    ):
        raise ValueError("step_problem type is invalid")
    config = step_problem.config
    coordinates = step_problem.initial_augmented_coordinates_m()
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []

    for iteration in range(config.maximum_iterations + 1):
        assembly = step_problem.assemble(coordinates)
        relative_residual = _relative_equilibrium(step_problem, assembly)
        residual_gate = relative_residual <= config.residual_tolerance
        control_gate = abs(assembly.control_error_m) <= config.control_tolerance_m
        try:
            correction = np.linalg.solve(
                assembly.augmented_jacobian_kn_per_m,
                -assembly.augmented_residual_kn,
            )
        except np.linalg.LinAlgError:
            return _blocked_solution(
                step_problem,
                coordinates,
                history,
                line_search_history,
                detail=(
                    "singular_augmented_jacobian_at_terminal_gate"
                    if residual_gate and control_gate
                    else "singular_augmented_jacobian"
                ),
            )
        if correction.shape != coordinates.shape or not np.all(np.isfinite(correction)):
            return _blocked_solution(
                step_problem,
                coordinates,
                history,
                line_search_history,
                detail="invalid_augmented_correction",
            )
        free_correction = correction[:-1]
        load_correction = float(correction[-1]) / config.load_factor_coordinate_scale_m
        free_increment = float(np.linalg.norm(free_correction, ord=np.inf))
        increment_gate = bool(
            free_increment <= config.increment_tolerance_m
            and abs(load_correction) <= config.load_factor_increment_tolerance
        )
        if residual_gate and control_gate and increment_gate:
            history.append(
                {
                    "iteration": iteration,
                    "load_factor": (
                        float(coordinates[-1]) / config.load_factor_coordinate_scale_m
                    ),
                    "relative_equilibrium_residual": relative_residual,
                    "control_error_m": assembly.control_error_m,
                    "free_increment_abs_m": free_increment,
                    "load_factor_increment_abs": abs(load_correction),
                    "line_search_alpha": 1.0,
                    "residual_gate_passed": True,
                    "control_gate_passed": True,
                    "increment_gate_passed": True,
                    "accepted": True,
                }
            )
            break

        merit_before = _merit(step_problem, assembly)
        selected: np.ndarray | None = None
        selected_alpha = 0.0
        attempts: list[dict[str, Any]] = []
        best_merit = merit_before
        for alpha in config.line_search_alphas:
            trial_coordinates = coordinates + alpha * correction
            trial = step_problem.assemble(trial_coordinates)
            trial_merit = _merit(step_problem, trial)
            accepted = trial_merit < merit_before
            attempts.append(
                {
                    "alpha": alpha,
                    "trial_load_factor": (
                        float(trial_coordinates[-1])
                        / config.load_factor_coordinate_scale_m
                    ),
                    "trial_relative_equilibrium_residual": _relative_equilibrium(
                        step_problem,
                        trial,
                    ),
                    "trial_control_error_m": trial.control_error_m,
                    "trial_merit": trial_merit,
                    "accepted": accepted,
                }
            )
            if accepted:
                selected = trial_coordinates
                selected_alpha = alpha
                break
            if trial_merit < best_merit:
                best_merit = trial_merit
                selected = trial_coordinates
                selected_alpha = alpha
        line_search_history.append(
            {
                "iteration": iteration,
                "selected_alpha": selected_alpha,
                "attempt_count": len(attempts),
                "attempts": attempts,
            }
        )
        actual_free_increment = (
            0.0
            if selected is None
            else float(np.linalg.norm(selected[:-1] - coordinates[:-1], ord=np.inf))
        )
        history.append(
            {
                "iteration": iteration,
                "load_factor": (
                    float(coordinates[-1]) / config.load_factor_coordinate_scale_m
                ),
                "relative_equilibrium_residual": relative_residual,
                "control_error_m": assembly.control_error_m,
                "free_increment_abs_m": actual_free_increment,
                "load_factor_increment_abs": abs(load_correction * selected_alpha),
                "line_search_alpha": selected_alpha,
                "residual_gate_passed": residual_gate,
                "control_gate_passed": control_gate,
                "increment_gate_passed": increment_gate,
                "accepted": selected is not None,
            }
        )
        if selected is None or selected_alpha == 0.0:
            return _blocked_solution(
                step_problem,
                coordinates,
                history,
                line_search_history,
                detail="line_search_failed_to_reduce_augmented_merit",
            )
        coordinates = selected
        if iteration == config.maximum_iterations:
            return _blocked_solution(
                step_problem,
                coordinates,
                history,
                line_search_history,
                detail="maximum_iterations_exceeded",
            )
    else:
        return _blocked_solution(
            step_problem,
            coordinates,
            history,
            line_search_history,
            detail="iteration_loop_exhausted",
        )

    final = step_problem.assemble(coordinates)
    final_relative = _relative_equilibrium(step_problem, final)
    final_free_increment = float(history[-1]["free_increment_abs_m"])
    final_load_increment = float(history[-1]["load_factor_increment_abs"])
    load_factor = float(coordinates[-1]) / config.load_factor_coordinate_scale_m
    contract_pass = bool(
        final_relative <= config.residual_tolerance
        and abs(final.control_error_m) <= config.control_tolerance_m
        and final_free_increment <= config.increment_tolerance_m
        and final_load_increment <= config.load_factor_increment_tolerance
    )
    metrics = {
        "case_id": step_problem.case_id,
        "control_mode": "direct_displacement_control",
        "control_global_dof": step_problem.control_global_dof,
        "control_free_index": step_problem.control_free_index,
        "target_control_displacement_m": (step_problem.target_control_displacement_m),
        "final_control_displacement_m": float(
            coordinates[step_problem.control_free_index]
        ),
        "control_error_m": final.control_error_m,
        "solved_load_factor": load_factor,
        "residual_kn": final.frame_assembly.residual_kn.tolist(),
        "relative_residual": final_relative,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "augmented_formula": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA
        ),
        "augmented_formula_hash": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH
        ),
        "load_factor_column_formula": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_LOAD_COLUMN
        ),
        "tangent_definition": "material_plus_geometric_consistent",
        "globalization": "backtracking_augmented_merit_line_search",
        "terminal_reason": "equilibrium_control_and_increment_converged",
        "solver_executed": True,
        "iteration_count": len(history),
        "linear_solve_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["line_search_alpha"] < 1.0
            for row in history
            if row["iteration"] < len(history) - 1
        ),
        "residual_tolerance": config.residual_tolerance,
        "control_tolerance_m": config.control_tolerance_m,
        "increment_tolerance_m": config.increment_tolerance_m,
        "load_factor_increment_tolerance": (config.load_factor_increment_tolerance),
        "final_free_increment_abs_m": final_free_increment,
        "final_load_factor_increment_abs": final_load_increment,
        "residual_gate_passed": final_relative <= config.residual_tolerance,
        "control_gate_passed": (
            abs(final.control_error_m) <= config.control_tolerance_m
        ),
        "increment_gate_passed": bool(
            final_free_increment <= config.increment_tolerance_m
            and final_load_increment <= config.load_factor_increment_tolerance
        ),
        "regularization_used": False,
        "fallback_used": False,
        "matrix_backend": VECTOR_MATRIX_BACKEND,
        "stiffness_storage": "numpy_dense_augmented_ndarray",
        "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE,
        "contract_pass": contract_pass,
    }
    return StatefulCorotationalFiberFrame2DDisplacementControlSolution(
        status="ready" if contract_pass else "blocked",
        augmented_coordinates_m=coordinates.copy(),
        free_displacements_m=coordinates[:-1].copy(),
        load_factor=load_factor,
        metrics=metrics,
        convergence_history=history,
        line_search_history=line_search_history,
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlStepResult:
    status: str
    committed: bool
    parent_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    trial_solution: StatefulCorotationalFiberFrame2DDisplacementControlSolution
    trial_assembly: StatefulCorotationalFiberFrame2DAssembly
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "committed": self.committed,
            "parent_checkpoint": self.parent_checkpoint.to_dict(),
            "accepted_checkpoint": self.accepted_checkpoint.to_dict(),
            "trial_solution": {
                "status": self.trial_solution.status,
                "metrics": dict(self.trial_solution.metrics),
                "convergence_history": self.trial_solution.convergence_history,
                "line_search_history": self.trial_solution.line_search_history,
                "unsupported_features": self.trial_solution.unsupported_features,
            },
            "trial_assembly": self.trial_assembly.to_dict(),
            "metrics": dict(self.metrics),
        }


def solve_stateful_corotational_fiber_frame2d_displacement_control_step(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    control_global_dof: int,
    target_control_displacement_m: float,
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig | None = None,
) -> StatefulCorotationalFiberFrame2DDisplacementControlStepResult:
    """Solve and atomically commit one direct displacement-control target."""

    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        accepted_checkpoint,
    )
    parent_bytes = accepted_checkpoint.canonical_bytes()
    parent_element_bytes = tuple(
        state.canonical_bytes() for state in accepted_checkpoint.element_states
    )
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=accepted_checkpoint,
        control_global_dof=control_global_dof,
        target_control_displacement_m=target_control_displacement_m,
        config=(
            StatefulCorotationalFiberFrame2DDisplacementControlConfig()
            if config is None
            else config
        ),
    )
    solution = solve_stateful_corotational_fiber_frame2d_displacement_control(
        step_problem
    )
    trial = assemble_stateful_corotational_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=solution.load_factor,
        trial_free_coordinates_m=solution.free_displacements_m,
    )
    parent_immutable = bool(
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
        and tuple(
            state.canonical_bytes() for state in accepted_checkpoint.element_states
        )
        == parent_element_bytes
    )
    parent_binding = bool(
        trial.parent_checkpoint_hash == accepted_checkpoint.state_hash
        and all(
            row.response.parent_state_hash == state.state_hash
            for row, state in zip(
                trial.member_assemblies,
                accepted_checkpoint.element_states,
                strict=True,
            )
        )
    )
    solver_assembly_binding = bool(
        _exact_float64_equal(
            solution.free_displacements_m,
            trial.generalized_coordinates_m[list(problem.free_global_dofs)],
        )
        and _exact_float64_equal(
            solution.metrics.get("residual_kn", ()),
            trial.residual_kn,
        )
        and solution.load_factor == trial.target_load_factor
    )
    control_index = _controlled_free_index(problem, control_global_dof)
    control_gate = bool(
        abs(
            solution.free_displacements_m[control_index]
            - step_problem.target_control_displacement_m
        )
        <= step_problem.config.control_tolerance_m
    )
    solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("control_gate_passed") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and parent_immutable
        and parent_binding
        and solver_assembly_binding
        and control_gate
    )
    if solver_contract:
        next_checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=solution.load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            global_displacements=tuple(
                float(value) for value in trial.global_displacements
            ),
            element_states=trial.trial_element_states,
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem,
            next_checkpoint,
        )
        committed = True
        rollback_exact: bool | None = None
    else:
        next_checkpoint = accepted_checkpoint
        committed = False
        rollback_exact = bool(
            next_checkpoint is accepted_checkpoint
            and next_checkpoint.canonical_bytes() == parent_bytes
            and tuple(
                state.canonical_bytes() for state in next_checkpoint.element_states
            )
            == parent_element_bytes
        )
    return StatefulCorotationalFiberFrame2DDisplacementControlStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=next_checkpoint,
        trial_solution=solution,
        trial_assembly=trial,
        metrics={
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_SCHEMA_VERSION
            ),
            "profile": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE
            ),
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "augmented_formula_hash": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH
            ),
            "control_mode": "direct_displacement_control",
            "control_global_dof": control_global_dof,
            "target_control_displacement_m": (
                step_problem.target_control_displacement_m
            ),
            "solved_load_factor": solution.load_factor,
            "parent_checkpoint_hash": accepted_checkpoint.state_hash,
            "accepted_checkpoint_hash_after": next_checkpoint.state_hash,
            "parent_checkpoint_immutable": parent_immutable,
            "section_and_element_parent_binding_passed": parent_binding,
            "solver_assembly_coordinate_residual_binding_passed": (
                solver_assembly_binding
            ),
            "control_coordinate_gate_passed": control_gate,
            "solver_contract_pass": solver_contract,
            "residual_gate_passed": solution.metrics.get("residual_gate_passed"),
            "control_gate_passed": solution.metrics.get("control_gate_passed"),
            "increment_gate_passed": solution.metrics.get("increment_gate_passed"),
            "regularization_used": False,
            "fallback_used": False,
            "committed": committed,
            "rollback_exact": rollback_exact,
        },
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlPathResult:
    status: str
    control_global_dof: int
    target_control_displacements_m: tuple[float, ...]
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    steps: tuple[StatefulCorotationalFiberFrame2DDisplacementControlStepResult, ...] = (
        field(default_factory=tuple)
    )

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_SCHEMA_VERSION
            ),
            "status": self.status,
            "contract_pass": self.contract_pass,
            "control_global_dof": self.control_global_dof,
            "target_control_displacements_m": list(self.target_control_displacements_m),
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "claim_boundary": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
            ),
        }


def run_stateful_corotational_fiber_frame2d_displacement_control_path(
    problem: StatefulCorotationalFiberFrame2DProblem,
    control_displacements_m: Iterable[float],
    *,
    control_global_dof: int,
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig | None = None,
) -> StatefulCorotationalFiberFrame2DDisplacementControlPathResult:
    """Run a strictly monotone displacement target path until one step fails."""

    _controlled_free_index(problem, control_global_dof)
    targets = tuple(
        _finite(value, name="control displacement") for value in control_displacements_m
    )
    if not targets:
        raise ValueError("control_displacements_m must be non-empty")
    if len(targets) > 255:
        raise ValueError("control_displacements_m exceeds the bounded path length")
    first = initial_checkpoint or (
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, first)
    control_index = _controlled_free_index(problem, control_global_dof)
    accepted_control = _free_generalized_coordinates(problem, first)[control_index]
    direction = math.copysign(1.0, targets[0] - accepted_control)
    if targets[0] == accepted_control or any(
        direction * (right - left) <= 0.0
        for left, right in zip(
            (accepted_control, *targets[:-1]),
            targets,
            strict=True,
        )
    ):
        raise ValueError(
            "control_displacements_m must advance strictly in one direction"
        )
    solver_config = config or (
        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    )
    accepted = first
    rows: list[StatefulCorotationalFiberFrame2DDisplacementControlStepResult] = []
    for target in targets:
        step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            problem,
            accepted,
            control_global_dof=control_global_dof,
            target_control_displacement_m=target,
            config=solver_config,
        )
        rows.append(step)
        if not step.committed:
            return StatefulCorotationalFiberFrame2DDisplacementControlPathResult(
                status="blocked",
                control_global_dof=control_global_dof,
                target_control_displacements_m=targets,
                initial_checkpoint=first,
                final_checkpoint=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_checkpoint
    return StatefulCorotationalFiberFrame2DDisplacementControlPathResult(
        status="ready",
        control_global_dof=control_global_dof,
        target_control_displacements_m=targets,
        initial_checkpoint=first,
        final_checkpoint=accepted,
        steps=tuple(rows),
    )


def finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check(
    step_problem: StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    *,
    displacement_step_m: float = 1.0e-7,
    load_factor_step: float = 1.0e-7,
) -> dict[str, Any]:
    """Check both augmented Jacobian blocks against parent-bound central differences."""

    if type(step_problem) is not (
        StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    ):
        raise ValueError("step_problem type is invalid")
    displacement_step = _finite(
        displacement_step_m,
        name="displacement_step_m",
        positive=True,
    )
    load_step = _finite(
        load_factor_step,
        name="load_factor_step",
        positive=True,
    )
    parent = step_problem.accepted_checkpoint
    parent_bytes = parent.canonical_bytes()
    center_coordinates = step_problem.initial_augmented_coordinates_m()
    center = step_problem.assemble(center_coordinates)
    direction = np.arange(
        1,
        len(step_problem.problem.free_global_dofs) + 1,
        dtype=np.float64,
    )
    direction /= np.linalg.norm(direction)
    forward_coordinates = center_coordinates.copy()
    backward_coordinates = center_coordinates.copy()
    forward_coordinates[:-1] += displacement_step * direction
    backward_coordinates[:-1] -= displacement_step * direction
    forward = step_problem.assemble(forward_coordinates)
    backward = step_problem.assemble(backward_coordinates)
    finite_displacement = (
        forward.frame_assembly.residual_kn - backward.frame_assembly.residual_kn
    ) / (2.0 * displacement_step)
    analytic_displacement = center.frame_assembly.jacobian_kn_per_m @ direction
    load_coordinate_step = (
        load_step * step_problem.config.load_factor_coordinate_scale_m
    )
    load_forward_coordinates = center_coordinates.copy()
    load_backward_coordinates = center_coordinates.copy()
    load_forward_coordinates[-1] += load_coordinate_step
    load_backward_coordinates[-1] -= load_coordinate_step
    load_forward = step_problem.assemble(load_forward_coordinates)
    load_backward = step_problem.assemble(load_backward_coordinates)
    finite_load = (
        load_forward.frame_assembly.residual_kn
        - load_backward.frame_assembly.residual_kn
    ) / (2.0 * load_step)
    analytic_load = center.load_factor_residual_derivative_kn
    displacement_error = float(
        np.linalg.norm(finite_displacement - analytic_displacement, ord=np.inf)
    )
    load_error = float(np.linalg.norm(finite_load - analytic_load, ord=np.inf))
    parent_binding = bool(
        all(
            row.frame_assembly.parent_checkpoint_hash == parent.state_hash
            for row in (
                center,
                forward,
                backward,
                load_forward,
                load_backward,
            )
        )
        and parent.canonical_bytes() == parent_bytes
    )
    return {
        "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE,
        "parent_checkpoint_hash": parent.state_hash,
        "parent_binding_passed": parent_binding,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "augmented_formula_hash": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH
        ),
        "displacement_direction": direction.tolist(),
        "finite_difference_displacement_column_kn_per_m": (
            finite_displacement.tolist()
        ),
        "analytic_displacement_column_kn_per_m": analytic_displacement.tolist(),
        "displacement_column_max_abs_error_kn_per_m": displacement_error,
        "finite_difference_load_factor_column_kn": finite_load.tolist(),
        "analytic_load_factor_column_kn": analytic_load.tolist(),
        "load_factor_column_max_abs_error_kn": load_error,
    }


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_LOAD_COLUMN",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DDisplacementControlAssembly",
    "StatefulCorotationalFiberFrame2DDisplacementControlConfig",
    "StatefulCorotationalFiberFrame2DDisplacementControlPathResult",
    "StatefulCorotationalFiberFrame2DDisplacementControlSolution",
    "StatefulCorotationalFiberFrame2DDisplacementControlStepProblem",
    "StatefulCorotationalFiberFrame2DDisplacementControlStepResult",
    "finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check",
    "run_stateful_corotational_fiber_frame2d_displacement_control_path",
    "solve_stateful_corotational_fiber_frame2d_displacement_control",
    "solve_stateful_corotational_fiber_frame2d_displacement_control_step",
]
