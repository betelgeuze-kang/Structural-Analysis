"""Direct displacement control for the bounded corotational 2D frame path."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np
from scipy.sparse import csr_matrix, hstack

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
    StatefulCorotationalFiberFrame2DLoadStepResult,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    assemble_stateful_corotational_fiber_frame2d_sparse,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    newton_raphson_vector,
)


COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-direct-displacement-control.v1"
)
COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_OPERATOR = (
    "unknowns=[uncontrolled_generalized_coordinates_m,"
    "load_factor*abs(terminal_control_generalized_m)];"
    "controlled_coordinate=target;"
    "equilibrium_on_all_free_equations;"
    "dR_dlambda=partial_load_derivative+K*d_prescribed_dlambda"
)


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _exact_float64_equal(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left, dtype="<f8")
    right_array = np.ascontiguousarray(right, dtype="<f8")
    return left_array.shape == right_array.shape and (
        left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DDisplacementControlStepAdapter:
    problem: StatefulCorotationalFiberFrame2DProblem
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    controlled_global_dof: int
    target_control_displacement: float
    terminal_control_displacement: float
    matrix_backend: str = VECTOR_MATRIX_BACKEND

    def __post_init__(self) -> None:
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            self.problem, self.accepted_checkpoint
        )
        if (
            type(self.controlled_global_dof) is not int
            or self.controlled_global_dof not in self.problem.free_global_dofs
        ):
            raise ValueError("controlled_global_dof must be a free problem DOF")
        target = _finite(
            self.target_control_displacement,
            name="target_control_displacement",
        )
        terminal = _finite(
            self.terminal_control_displacement,
            name="terminal_control_displacement",
        )
        if terminal == 0.0:
            raise ValueError("terminal_control_displacement must be nonzero")
        object.__setattr__(self, "target_control_displacement", target)
        object.__setattr__(self, "terminal_control_displacement", terminal)
        if self.matrix_backend not in {
            VECTOR_MATRIX_BACKEND,
            VECTOR_SPARSE_MATRIX_BACKEND,
        }:
            raise ValueError("matrix_backend is unsupported")

    @property
    def case_id(self) -> str:
        return (
            f"{self.problem.case_id}@control-dof={self.controlled_global_dof}"
            f"@target={self.target_control_displacement:.12g}"
        )

    @property
    def uncontrolled_free_dofs(self) -> tuple[int, ...]:
        return tuple(
            dof
            for dof in self.problem.free_global_dofs
            if dof != self.controlled_global_dof
        )

    @property
    def controlled_free_position(self) -> int:
        return self.problem.free_global_dofs.index(self.controlled_global_dof)

    @property
    def load_factor_coordinate_scale_m(self) -> float:
        physical_scale = self.problem.physical_coordinate_scale[
            self.controlled_global_dof
        ]
        return abs(self.terminal_control_displacement / physical_scale)

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        physical_scale = self.problem.physical_coordinate_scale
        parent = np.asarray(
            self.accepted_checkpoint.global_displacements, dtype=np.float64
        )
        generalized = parent / physical_scale
        values = [generalized[dof] for dof in self.uncontrolled_free_dofs]
        values.append(
            self.accepted_checkpoint.load_factor * self.load_factor_coordinate_scale_m
        )
        return np.asarray(values, dtype=np.float64)

    def decode_augmented_coordinates(
        self, augmented_coordinates_m: Any
    ) -> tuple[np.ndarray, float]:
        values = np.asarray(augmented_coordinates_m, dtype=np.float64)
        free_dofs = self.problem.free_global_dofs
        if values.shape != (len(free_dofs),) or not np.all(np.isfinite(values)):
            raise ValueError("augmented displacement-control coordinates are invalid")
        free = np.empty(len(free_dofs), dtype=np.float64)
        uncontrolled_values = values[:-1]
        uncontrolled_index = 0
        target_generalized = (
            self.target_control_displacement
            / (self.problem.physical_coordinate_scale[self.controlled_global_dof])
        )
        for index, dof in enumerate(free_dofs):
            if dof == self.controlled_global_dof:
                free[index] = target_generalized
            else:
                free[index] = uncontrolled_values[uncontrolled_index]
                uncontrolled_index += 1
        load_factor = float(values[-1] / self.load_factor_coordinate_scale_m)
        return free, load_factor

    def assemble(self, augmented_coordinates_m: np.ndarray) -> tuple[np.ndarray, Any]:
        free, load_factor = self.decode_augmented_coordinates(augmented_coordinates_m)
        uncontrolled_positions = tuple(
            index
            for index, dof in enumerate(self.problem.free_global_dofs)
            if dof != self.controlled_global_dof
        )
        if self.matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND:
            sparse_assembly = assemble_stateful_corotational_fiber_frame2d_sparse(
                self.problem,
                self.accepted_checkpoint,
                target_load_factor=load_factor,
                trial_free_coordinates_m=free,
            )
            left = sparse_assembly.jacobian_csr[:, list(uncontrolled_positions)]
            load_column = csr_matrix(
                (
                    sparse_assembly.residual_load_factor_derivative_kn
                    / self.load_factor_coordinate_scale_m
                )[:, None]
            )
            augmented = hstack((left, load_column), format="csr")
            augmented.sum_duplicates()
            augmented.eliminate_zeros()
            augmented.sort_indices()
            return sparse_assembly.residual_kn, augmented
        dense_assembly = assemble_stateful_corotational_fiber_frame2d(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=load_factor,
            trial_free_coordinates_m=free,
        )
        augmented = np.column_stack(
            (
                dense_assembly.jacobian_kn_per_m[:, list(uncontrolled_positions)],
                dense_assembly.residual_load_factor_derivative_kn
                / self.load_factor_coordinate_scale_m,
            )
        )
        return dense_assembly.residual_kn, augmented


def solve_stateful_corotational_fiber_frame2d_displacement_control_step(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    controlled_global_dof: int,
    target_control_displacement: float,
    terminal_control_displacement: float,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLoadStepResult:
    """Solve one direct-control target and atomically commit its load factor."""

    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem, accepted_checkpoint
    )
    parent_bytes = accepted_checkpoint.canonical_bytes()
    solver_config = config or NewtonRaphsonConfig()
    adapter = StatefulCorotationalFiberFrame2DDisplacementControlStepAdapter(
        problem=problem,
        accepted_checkpoint=accepted_checkpoint,
        controlled_global_dof=controlled_global_dof,
        target_control_displacement=target_control_displacement,
        terminal_control_displacement=terminal_control_displacement,
        matrix_backend=solver_config.matrix_backend,
    )
    solution = newton_raphson_vector(adapter, config=solver_config)
    free, solved_load_factor = adapter.decode_augmented_coordinates(
        solution.free_displacements_m
    )
    trial_assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=solved_load_factor,
        trial_free_coordinates_m=free,
    )
    iterative_solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("active_equation_count")
        == len(problem.free_global_dofs)
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and (
            solver_config.matrix_backend != VECTOR_SPARSE_MATRIX_BACKEND
            or solution.metrics.get("native_sparse_assembly_used") is True
        )
        and (
            solver_config.matrix_backend != VECTOR_SPARSE_MATRIX_BACKEND
            or solution.metrics.get("sparse_factorization_diagnostics_passed") is True
        )
    )
    parent_binding = bool(
        trial_assembly.parent_checkpoint_hash == accepted_checkpoint.state_hash
        and all(
            row.response.parent_state_hash == parent.state_hash
            for row, parent in zip(
                trial_assembly.member_assemblies,
                accepted_checkpoint.element_states,
                strict=True,
            )
        )
    )
    solver_assembly_binding = bool(
        _exact_float64_equal(
            free,
            trial_assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
        )
        and solved_load_factor == trial_assembly.target_load_factor
        and _exact_float64_equal(
            solution.metrics.get("residual_kn", ()), trial_assembly.residual_kn
        )
    )
    target_reached = bool(
        trial_assembly.global_displacements[controlled_global_dof]
        == adapter.target_control_displacement
    )
    parent_immutable = bool(
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
    )
    solver_contract = bool(
        iterative_solver_contract
        and parent_binding
        and solver_assembly_binding
        and target_reached
        and parent_immutable
    )
    if solver_contract:
        next_checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=solved_load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            global_displacements=tuple(
                float(value) for value in trial_assembly.global_displacements
            ),
            element_states=trial_assembly.trial_element_states,
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem, next_checkpoint
        )
        committed = True
        rollback_exact: bool | None = None
    else:
        next_checkpoint = accepted_checkpoint
        committed = False
        rollback_exact = bool(
            next_checkpoint is accepted_checkpoint
            and next_checkpoint.canonical_bytes() == parent_bytes
        )

    member_rows = trial_assembly.member_assemblies
    metrics: dict[str, Any] = {
        "schema_version": (
            COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_SCHEMA_VERSION
        ),
        "control_mode": "displacement_control",
        "control_operator": COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_OPERATOR,
        "controlled_global_dof": controlled_global_dof,
        "target_control_displacement": adapter.target_control_displacement,
        "terminal_control_displacement": adapter.terminal_control_displacement,
        "actual_control_displacement": float(
            trial_assembly.global_displacements[controlled_global_dof]
        ),
        "control_target_reached": target_reached,
        "solved_load_factor": solved_load_factor,
        "load_factor_coordinate_scale_m": adapter.load_factor_coordinate_scale_m,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "tangent_definition": "material_plus_geometric_consistent",
        "member_feature_tangent_definition": (
            "finite_rigid_arm_second_derivative_plus_dead_load_potential_plus_release_schur_condensation"
        ),
        "target_load_factor": solved_load_factor,
        "parent_checkpoint_hash": accepted_checkpoint.state_hash,
        "parent_epoch": accepted_checkpoint.epoch,
        "accepted_checkpoint_hash_after": next_checkpoint.state_hash,
        "accepted_epoch_after": next_checkpoint.epoch,
        "trial_parent_checkpoint_hash": trial_assembly.parent_checkpoint_hash,
        "section_and_element_parent_binding_passed": parent_binding,
        "solver_assembly_coordinate_residual_binding_passed": (solver_assembly_binding),
        "parent_checkpoint_immutable": parent_immutable,
        "solver_contract_pass": solver_contract,
        "iterative_solver_contract_pass": iterative_solver_contract,
        "no_solve_contract_pass": False,
        "terminal_disposition": SOLVE_FREE_EQUATIONS_DISPOSITION,
        "terminal_reason": solution.metrics.get("terminal_reason"),
        "residual_gate_passed": solution.metrics.get("residual_gate_passed"),
        "increment_gate_passed": solution.metrics.get("increment_gate_passed"),
        "regularization_used": bool(solution.metrics.get("regularization_used")),
        "fallback_used": bool(solution.metrics.get("fallback_used")),
        "matrix_backend": solution.metrics.get("matrix_backend"),
        "sparse_backend_used": bool(solution.metrics.get("sparse_backend_used")),
        "native_sparse_assembly_used": bool(
            solution.metrics.get("native_sparse_assembly_used")
        ),
        "stiffness_storage": solution.metrics.get("stiffness_storage"),
        "sparse_factorization_backend": solution.metrics.get(
            "sparse_factorization_backend"
        ),
        "sparse_factorization_count": int(
            solution.metrics.get("sparse_factorization_count", 0)
        ),
        "sparse_factorization_diagnostics_passed": solution.metrics.get(
            "sparse_factorization_diagnostics_passed"
        ),
        "sparse_factorization_max_condition_number_1": solution.metrics.get(
            "sparse_factorization_max_condition_number_1"
        ),
        "sparse_factorization_min_normalized_absolute_pivot": solution.metrics.get(
            "sparse_factorization_min_normalized_absolute_pivot"
        ),
        "sparse_factorization_max_backward_error": solution.metrics.get(
            "sparse_factorization_max_backward_error"
        ),
        "sparse_factorization_diagnostic_hashes": [
            row["diagnostic_hash"]
            for row in solution.metrics.get("sparse_factorization_diagnostics", ())
        ],
        "sparse_factorization_policy_hash": next(
            (
                row["policy"]["policy_hash"]
                for row in solution.metrics.get("sparse_factorization_diagnostics", ())
            ),
            None,
        ),
        "committed": committed,
        "rollback_exact": rollback_exact,
        "yielded_member_count": sum(
            int(row.response.yielded_integration_point_count > 0) for row in member_rows
        ),
        "damaged_member_count": sum(
            int(row.response.damaged_integration_point_count > 0) for row in member_rows
        ),
        "member_feature_count": sum(
            int(
                member.features.has_release
                or member.features.has_rigid_offset
                or member.features.has_distributed_load
            )
            for member in problem.members
        ),
        "released_end_count": sum(
            len(member.features.released_element_dofs) for member in problem.members
        ),
        "rigid_offset_end_count": sum(
            int(any(value != 0.0 for value in member.features.offset_i_global_m))
            + int(any(value != 0.0 for value in member.features.offset_j_global_m))
            for member in problem.members
        ),
        "distributed_load_member_count": sum(
            int(member.features.has_distributed_load) for member in problem.members
        ),
        "release_local_iteration_count": sum(
            row.feature_response.release_iterations for row in member_rows
        ),
        "release_equilibrium_max_abs_kn_m": max(
            (
                float(np.max(np.abs(row.feature_response.release_residual_kn_m)))
                for row in member_rows
                if row.feature_response.release_residual_kn_m.size
            ),
            default=0.0,
        ),
        "member_feature_response_hashes": [
            row.feature_response.response_hash for row in member_rows
        ],
    }
    return StatefulCorotationalFiberFrame2DLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=next_checkpoint,
        trial_solution=solution,
        trial_assembly=trial_assembly,
        metrics=metrics,
    )


def run_stateful_corotational_fiber_frame2d_displacement_control_path(
    problem: StatefulCorotationalFiberFrame2DProblem,
    target_control_displacements: Iterable[float],
    *,
    controlled_global_dof: int,
    terminal_control_displacement: float,
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLoadPathResult:
    """Advance strictly ordered control targets, retaining the last exact commit."""

    targets = tuple(
        _finite(value, name="target_control_displacement")
        for value in target_control_displacements
    )
    if not targets:
        raise ValueError("target_control_displacements must be non-empty")
    terminal = _finite(
        terminal_control_displacement, name="terminal_control_displacement"
    )
    if terminal == 0.0:
        raise ValueError("terminal_control_displacement must be nonzero")
    first = initial_checkpoint or (
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, first)
    if (
        type(controlled_global_dof) is not int
        or controlled_global_dof not in problem.free_global_dofs
    ):
        raise ValueError("controlled_global_dof must be a free problem DOF")
    start = first.global_displacements[controlled_global_dof]
    direction = math.copysign(1.0, terminal - start)
    previous = start
    for target in targets:
        if direction * (target - previous) <= 0.0:
            raise ValueError(
                "control targets must advance strictly toward the terminal"
            )
        previous = target
    accepted = first
    rows: list[StatefulCorotationalFiberFrame2DLoadStepResult] = []
    for target in targets:
        step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            problem,
            accepted,
            controlled_global_dof=controlled_global_dof,
            target_control_displacement=target,
            terminal_control_displacement=terminal,
            config=config,
        )
        rows.append(step)
        if not step.committed:
            return StatefulCorotationalFiberFrame2DLoadPathResult(
                status="blocked",
                initial_checkpoint=first,
                final_checkpoint=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_checkpoint
    return StatefulCorotationalFiberFrame2DLoadPathResult(
        status="ready",
        initial_checkpoint=first,
        final_checkpoint=accepted,
        steps=tuple(rows),
    )


__all__ = [
    "COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_OPERATOR",
    "COROTATIONAL_FIBER_FRAME_DISPLACEMENT_CONTROL_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DDisplacementControlStepAdapter",
    "run_stateful_corotational_fiber_frame2d_displacement_control_path",
    "solve_stateful_corotational_fiber_frame2d_displacement_control_step",
]
