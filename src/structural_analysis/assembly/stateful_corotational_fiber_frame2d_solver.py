"""Newton load control for the stateful corotational 2D fiber frame."""

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
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    assemble_stateful_corotational_fiber_frame2d_sparse,
)
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    newton_raphson_vector,
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
class StatefulCorotationalFiberFrame2DLoadStepAdapter:
    """Bind one fixed load target to one immutable accepted checkpoint."""

    problem: StatefulCorotationalFiberFrame2DProblem
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    target_load_factor: float
    matrix_backend: str = VECTOR_MATRIX_BACKEND

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@load={self.target_load_factor:.12g}"

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        scale = self.problem.physical_coordinate_scale
        global_displacements = np.asarray(
            self.accepted_checkpoint.global_displacements,
            dtype=np.float64,
        )
        generalized = global_displacements / scale
        return generalized[list(self.problem.free_global_dofs)].copy()

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, Any]:
        if self.matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND:
            sparse_assembly = assemble_stateful_corotational_fiber_frame2d_sparse(
                self.problem,
                self.accepted_checkpoint,
                target_load_factor=self.target_load_factor,
                trial_free_coordinates_m=free_displacements_m,
            )
            return sparse_assembly.residual_kn, sparse_assembly.jacobian_csr
        assembly = assemble_stateful_corotational_fiber_frame2d(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=self.target_load_factor,
            trial_free_coordinates_m=free_displacements_m,
        )
        return assembly.residual_kn, assembly.jacobian_kn_per_m


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLoadStepResult:
    status: str
    committed: bool
    parent_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    trial_solution: NewtonRaphsonVectorSolution
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
                "metrics": self.trial_solution.metrics,
                "convergence_history": self.trial_solution.convergence_history,
                "line_search_history": self.trial_solution.line_search_history,
                "unsupported_features": self.trial_solution.unsupported_features,
            },
            "trial_assembly": self.trial_assembly.to_dict(),
            "metrics": dict(self.metrics),
        }


def solve_stateful_corotational_fiber_frame2d_load_step(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLoadStepResult:
    """Solve one fixed load target and atomically commit or exactly roll back."""

    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        accepted_checkpoint,
    )
    parent_bytes = accepted_checkpoint.canonical_bytes()
    load_factor = _finite(target_load_factor, name="target_load_factor")
    solver_config = config or NewtonRaphsonConfig()
    adapter = StatefulCorotationalFiberFrame2DLoadStepAdapter(
        problem=problem,
        accepted_checkpoint=accepted_checkpoint,
        target_load_factor=load_factor,
        matrix_backend=solver_config.matrix_backend,
    )
    solution = newton_raphson_vector(
        adapter,
        config=solver_config,
    )
    trial_assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=load_factor,
        trial_free_coordinates_m=solution.free_displacements_m,
    )
    no_solve_reaction_only = bool(
        solution.metrics.get("terminal_disposition")
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and solution.metrics.get("solver_executed") is False
        and solution.metrics.get("active_equation_count") == 0
        and solution.metrics.get("assembly_contract_valid") is True
        and solution.metrics.get("convergence_claim") is False
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
            solution.free_displacements_m,
            trial_assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
        )
        and _exact_float64_equal(
            solution.metrics.get("residual_kn", ()),
            trial_assembly.residual_kn,
        )
    )
    parent_immutable = bool(
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
    )
    solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and (no_solve_reaction_only or iterative_solver_contract)
        and parent_binding
        and solver_assembly_binding
        and parent_immutable
    )
    if solver_contract:
        next_checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            global_displacements=tuple(
                float(value) for value in trial_assembly.global_displacements
            ),
            element_states=trial_assembly.trial_element_states,
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
            and next_checkpoint.state_hash == accepted_checkpoint.state_hash
            and next_checkpoint.canonical_bytes() == parent_bytes
        )
    return StatefulCorotationalFiberFrame2DLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=next_checkpoint,
        trial_solution=solution,
        trial_assembly=trial_assembly,
        metrics={
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "tangent_definition": "material_plus_geometric_consistent",
            "target_load_factor": load_factor,
            "parent_checkpoint_hash": accepted_checkpoint.state_hash,
            "parent_epoch": accepted_checkpoint.epoch,
            "accepted_checkpoint_hash_after": next_checkpoint.state_hash,
            "accepted_epoch_after": next_checkpoint.epoch,
            "trial_parent_checkpoint_hash": (trial_assembly.parent_checkpoint_hash),
            "section_and_element_parent_binding_passed": parent_binding,
            "solver_assembly_coordinate_residual_binding_passed": (
                solver_assembly_binding
            ),
            "parent_checkpoint_immutable": parent_immutable,
            "solver_contract_pass": solver_contract,
            "iterative_solver_contract_pass": iterative_solver_contract,
            "no_solve_contract_pass": no_solve_reaction_only,
            "terminal_disposition": solution.metrics.get(
                "terminal_disposition",
                SOLVE_FREE_EQUATIONS_DISPOSITION,
            ),
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
            "sparse_factorization_min_normalized_absolute_pivot": (
                solution.metrics.get(
                    "sparse_factorization_min_normalized_absolute_pivot"
                )
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
                    for row in solution.metrics.get(
                        "sparse_factorization_diagnostics", ()
                    )
                ),
                None,
            ),
            "committed": committed,
            "rollback_exact": rollback_exact,
            "yielded_member_count": sum(
                int(row.response.yielded_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
            "damaged_member_count": sum(
                int(row.response.damaged_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
        },
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLoadPathResult:
    status: str
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    steps: tuple[StatefulCorotationalFiberFrame2DLoadStepResult, ...] = field(
        default_factory=tuple
    )

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
        }


def run_stateful_corotational_fiber_frame2d_load_path(
    problem: StatefulCorotationalFiberFrame2DProblem,
    load_factors: Iterable[float],
    *,
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLoadPathResult:
    """Run fixed load targets until one fails, retaining the last commit."""

    factors = tuple(_finite(value, name="load_factor") for value in load_factors)
    if not factors:
        raise ValueError("load_factors must be non-empty")
    first = initial_checkpoint or (
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, first)
    accepted = first
    rows: list[StatefulCorotationalFiberFrame2DLoadStepResult] = []
    for factor in factors:
        step = solve_stateful_corotational_fiber_frame2d_load_step(
            problem,
            accepted,
            target_load_factor=factor,
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
    "StatefulCorotationalFiberFrame2DLoadPathResult",
    "StatefulCorotationalFiberFrame2DLoadStepAdapter",
    "StatefulCorotationalFiberFrame2DLoadStepResult",
    "run_stateful_corotational_fiber_frame2d_load_path",
    "solve_stateful_corotational_fiber_frame2d_load_step",
]
