"""Transactional material-state bridge for matrix-free Newton load steps.

The generic load-controlled matrix-free Newton kernel owns displacement-only
checkpoints.  This module binds one of those solves to an immutable accepted
``StatefulAxialAcceptedState`` and commits the constitutive trial state only
after every nonlinear and linear gate has passed.  Failed solves retain the
exact accepted displacement and material-state bytes.

This is deliberately a bounded axial-chain integration.  It establishes the
accepted/trial material-state semantics of the reusable Newton path, not a
general frame/shell material formulation or G1 full-building closure.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, is_dataclass
import math
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialAcceptedState,
    StatefulAxialAssemblyState,
    StatefulAxialChainProblem,
    assemble_stateful_axial_chain,
    initial_stateful_axial_state,
    validate_stateful_axial_state,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LoadControlledMatrixFreeNewtonConfig,
    LoadControlledMatrixFreeNewtonResult,
    load_controlled_matrix_free_newton_continuation,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION,
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthStateTangentSolver,
)


STATEFUL_AXIAL_MATRIX_FREE_NEWTON_SCHEMA_VERSION = (
    "stateful-axial-matrix-free-newton-load-step.v1"
)
STATEFUL_AXIAL_MATRIX_FREE_LOAD_PATH_SCHEMA_VERSION = (
    "stateful-axial-matrix-free-newton-load-path.v1"
)
STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE = (
    "accepted_material_parent_increment_space_matrix_free_newton.v1"
)
STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION = (
    "assemble_stateful_axial_chain(accepted_material_parent,"
    "u_accepted+delta_u,lambda_accepted+eta*delta_lambda)."
    "jacobian_kn_per_m*direction_m"
)
STATEFUL_AXIAL_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY = (
    "This path binds every residual, consistent-tangent action, and line-search "
    "trial in one physical load step to the same immutable accepted axial "
    "material state. A new displacement and constitutive state are committed "
    "only after the matrix-free linear replay, nonlinear residual, and increment "
    "gates pass; failure retains the exact accepted canonical bytes. It is a "
    "bounded CPU axial-chain integration and does not establish adaptive step "
    "reduction, arc-length, general frame/shell material behavior, production "
    "Krylov or HIP parity, or G1 full-building closure."
)


class StatefulAxialMatrixFreeNewtonError(ValueError):
    """Fail-closed stateful axial matrix-free integration error."""


def _default_step_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=1.0e-9,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-9,
        tangent_solve_residual_tolerance_inf_kn=1.0e-9,
        maximum_newton_iterations=8,
    )


def _finite_vector(values: Any, *, name: str, dimension: int) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise StatefulAxialMatrixFreeNewtonError(
            f"{name} must be a finite FP64 vector"
        ) from exc
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise StatefulAxialMatrixFreeNewtonError(
            f"{name} must be a finite FP64 vector with shape ({dimension},)"
        )
    return np.ascontiguousarray(vector, dtype=np.float64)


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise StatefulAxialMatrixFreeNewtonError(
            f"{name} must be a finite number"
        )
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise StatefulAxialMatrixFreeNewtonError(
            f"{name} must be a finite number"
        ) from exc
    if not math.isfinite(normalized):
        raise StatefulAxialMatrixFreeNewtonError(
            f"{name} must be a finite number"
        )
    return normalized


def _material_contract_payload(material: Any) -> dict[str, Any]:
    accessor = getattr(material, "matrix_free_material_contract_payload", None)
    if callable(accessor):
        parameters = accessor()
        if not isinstance(parameters, dict):
            raise StatefulAxialMatrixFreeNewtonError(
                "matrix-free material contract payload must be an object"
            )
    elif is_dataclass(material) and not isinstance(material, type):
        parameters = asdict(material)
    else:
        raise StatefulAxialMatrixFreeNewtonError(
            "stateful material must expose canonical dataclass parameters or "
            "matrix_free_material_contract_payload()"
        )
    return {
        "type": (
            f"{type(material).__module__}.{type(material).__qualname__}"
        ),
        "parameters": parameters,
    }


def _source_problem_contract_hash(problem: StatefulAxialChainProblem) -> str:
    return canonical_hash(
        {
            "case_id": problem.case_id,
            "node_count": problem.node_count,
            "fixed_nodes": list(problem.fixed_nodes),
            "reference_external_forces_kn": [
                list(row) for row in problem.reference_external_forces_kn
            ],
            "reference_prescribed_displacements_m": [
                list(row)
                for row in problem.reference_prescribed_displacements_m
            ],
            "elements": [
                {
                    "element_id": element.element_id,
                    "node_i": element.node_i,
                    "node_j": element.node_j,
                    "length_m": element.length_m,
                    "area_m2": element.area_m2,
                    "response_kind": element.response_kind,
                    "material": _material_contract_payload(element.material),
                }
                for element in problem.elements
            ],
        }
    )


@dataclass(frozen=True)
class StatefulAxialMatrixFreeLoadStepProblem:
    """One physical load step expressed as a zero-based increment problem."""

    problem: StatefulAxialChainProblem
    accepted_state: StatefulAxialAcceptedState
    target_load_factor: float
    _case_id: str = field(init=False, repr=False)
    _source_problem_contract_hash: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        validate_stateful_axial_state(self.problem, self.accepted_state)
        target = _finite_scalar(
            self.target_load_factor,
            name="target_load_factor",
        )
        if math.isclose(
            target,
            float(self.accepted_state.load_factor),
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise StatefulAxialMatrixFreeNewtonError(
                "target_load_factor must differ from the accepted load factor"
            )
        if not self.problem.free_node_indices:
            raise StatefulAxialMatrixFreeNewtonError(
                "matrix-free Newton requires at least one free equation"
            )
        object.__setattr__(self, "target_load_factor", target)
        source_problem_contract_hash = _source_problem_contract_hash(
            self.problem
        )
        step_identity = canonical_hash(
            {
                "profile": STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE,
                "source_case_id": self.problem.case_id,
                "source_problem_contract_hash": (
                    source_problem_contract_hash
                ),
                "accepted_state_hash": self.accepted_state.state_hash,
                "accepted_load_factor": self.accepted_state.load_factor,
                "target_load_factor": target,
                "free_node_indices": list(self.problem.free_node_indices),
            }
        )
        object.__setattr__(
            self,
            "_case_id",
            f"{self.problem.case_id}@stateful-step={step_identity}",
        )
        object.__setattr__(
            self,
            "_source_problem_contract_hash",
            source_problem_contract_hash,
        )

    @property
    def case_id(self) -> str:
        return self._case_id

    @property
    def equation_count(self) -> int:
        return len(self.problem.free_node_indices)

    @property
    def source_problem_contract_hash(self) -> str:
        return self._source_problem_contract_hash

    @property
    def load_factor_delta(self) -> float:
        return self.target_load_factor - self.accepted_state.load_factor

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.equation_count, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def actual_load_factor(self, increment_load_factor: float) -> float:
        eta = _finite_scalar(
            increment_load_factor,
            name="increment_load_factor",
        )
        return float(
            self.accepted_state.load_factor + eta * self.load_factor_delta
        )

    def actual_free_displacements_m(
        self,
        displacement_increments_m: Any,
    ) -> np.ndarray:
        increment = _finite_vector(
            displacement_increments_m,
            name="displacement_increments_m",
            dimension=self.equation_count,
        )
        accepted = np.asarray(
            self.accepted_state.displacements_m,
            dtype=np.float64,
        )[list(self.problem.free_node_indices)]
        return np.ascontiguousarray(accepted + increment, dtype=np.float64)

    def assemble(
        self,
        displacement_increments_m: Any,
        increment_load_factor: float,
    ) -> StatefulAxialAssemblyState:
        return assemble_stateful_axial_chain(
            self.problem,
            self.accepted_state,
            target_load_factor=self.actual_load_factor(increment_load_factor),
            trial_free_displacements_m=self.actual_free_displacements_m(
                displacement_increments_m
            ),
        )

    def residual_kn(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
    ) -> np.ndarray:
        return np.ascontiguousarray(
            self.assemble(
                displacement_increments_m,
                increment_load_factor,
            ).residual_kn,
            dtype=np.float64,
        )

    def consistent_state_tangent_action_kn_per_m(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        direction = _finite_vector(
            direction_m,
            name="direction_m",
            dimension=self.equation_count,
        )
        assembly = self.assemble(
            displacement_increments_m,
            increment_load_factor,
        )
        return np.ascontiguousarray(
            assembly.jacobian_kn_per_m @ direction,
            dtype=np.float64,
        )

    def reference_load_kn(self) -> np.ndarray:
        zero = np.zeros(self.equation_count, dtype=np.float64)
        initial = self.residual_kn(zero, 0.0)
        target = self.residual_kn(zero, 1.0)
        return np.ascontiguousarray(initial - target, dtype=np.float64)

    def full_unit_zero_state_predictor_free_m(self) -> np.ndarray:
        zero = np.zeros(self.equation_count, dtype=np.float64)
        tangent = self.assemble(zero, 0.0).jacobian_kn_per_m
        load = self.reference_load_kn()
        try:
            predictor = np.linalg.solve(tangent, load)
        except np.linalg.LinAlgError as exc:
            raise StatefulAxialMatrixFreeNewtonError(
                "accepted-state reference tangent is singular"
            ) from exc
        predictor = _finite_vector(
            predictor,
            name="predictor_direction_m",
            dimension=self.equation_count,
        )
        if float(np.linalg.norm(predictor, ord=np.inf)) <= 0.0:
            raise StatefulAxialMatrixFreeNewtonError(
                "accepted-state predictor direction must be nonzero"
            )
        return predictor

    @property
    def reference_preconditioner_contract(self) -> str:
        return (
            "stateful-axial-accepted-parent-reference-tangent-csr-n-per-m.v1"
        )

    def reference_preconditioner_free_csr_n_per_m(self) -> csr_matrix:
        zero = np.zeros(self.equation_count, dtype=np.float64)
        tangent_kn_per_m = self.assemble(zero, 0.0).jacobian_kn_per_m
        return csr_matrix(tangent_kn_per_m * 1000.0)

    def matrix_free_current_tangent_operator_binding(self) -> dict[str, Any]:
        free_order = np.ascontiguousarray(
            self.problem.free_node_indices,
            dtype="<i8",
        )
        reference_load_n = np.ascontiguousarray(
            self.reference_load_kn() * 1000.0,
            dtype="<f8",
        )
        return {
            "schema_version": (
                MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
            ),
            "case_id": self.case_id,
            "equation_count": self.equation_count,
            "free_equation_order_data_hash": array_data_hash(free_order),
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "current_tangent_action_contract": (
                STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION
            ),
            "reference_load_free_n_data_hash": array_data_hash(
                reference_load_n
            ),
            "residual_force_unit": "kN",
            "displacement_unit": "m",
            "tangent_action_unit": "kN/m",
            "load_factor_unit": "dimensionless",
        }


StateTangentSolverFactory = Callable[
    [StatefulAxialMatrixFreeLoadStepProblem],
    VectorArcLengthStateTangentSolver,
]


@dataclass(frozen=True)
class StatefulAxialMatrixFreeLoadStepResult:
    status: str
    committed: bool
    parent_state: StatefulAxialAcceptedState
    accepted_state: StatefulAxialAcceptedState
    step_problem: StatefulAxialMatrixFreeLoadStepProblem
    newton_result: LoadControlledMatrixFreeNewtonResult
    final_assembly: StatefulAxialAssemblyState
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_AXIAL_MATRIX_FREE_NEWTON_SCHEMA_VERSION
            ),
            "status": self.status,
            "committed": self.committed,
            "profile": STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE,
            "source_case_id": self.step_problem.problem.case_id,
            "step_case_id": self.step_problem.case_id,
            "parent_state": self.parent_state.to_dict(),
            "accepted_state": self.accepted_state.to_dict(),
            "newton_result": self.newton_result.to_dict(),
            "final_assembly": self.final_assembly.to_dict(),
            "metrics": dict(self.metrics),
            "claims": {
                "consistent_residual_tangent_matrix_free_newton": bool(
                    self.metrics["solver_contract_pass"]
                ),
                "accepted_trial_material_state_separation": True,
                "material_state_commit_performed": self.committed,
                "material_state_changed": bool(
                    self.metrics["material_state_changed"]
                ),
                "failed_step_material_state_rollback_exact": bool(
                    not self.committed
                    and self.metrics["rollback_exact"]
                ),
                "current_tangent_operator_parent_bound": True,
                "residual_and_increment_acceptance_policy": True,
                "residual_and_increment_acceptance_gate_passed": bool(
                    self.metrics[
                        "residual_and_increment_acceptance_gate"
                    ]
                ),
                "adaptive_step_reduction": False,
                "arc_length_branch": False,
                "general_frame_shell_material_newton": False,
                "production_matrix_free_krylov": False,
                "rocm_hip_parity": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": (
                STATEFUL_AXIAL_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY
            ),
        }


@dataclass(frozen=True)
class StatefulAxialMatrixFreeLoadPathResult:
    status: str
    initial_state: StatefulAxialAcceptedState
    final_state: StatefulAxialAcceptedState
    steps: tuple[StatefulAxialMatrixFreeLoadStepResult, ...]

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_AXIAL_MATRIX_FREE_LOAD_PATH_SCHEMA_VERSION
            ),
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_state": self.initial_state.to_dict(),
            "final_state": self.final_state.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "metrics": {
                "step_count": len(self.steps),
                "committed_step_count": sum(
                    int(step.committed) for step in self.steps
                ),
                "tangent_solve_count": sum(
                    int(step.metrics["tangent_solve_count"])
                    for step in self.steps
                ),
                "fallback_count": sum(
                    int(step.metrics["fallback_count"])
                    for step in self.steps
                ),
                "regularization_count": sum(
                    int(step.metrics["regularization_count"])
                    for step in self.steps
                ),
                "material_state_changed_step_count": sum(
                    int(step.metrics["material_state_changed"])
                    for step in self.steps
                ),
            },
            "claims": {
                "transactional_material_state_load_path": self.contract_pass,
                "all_steps_residual_and_increment_gated": bool(
                    self.contract_pass
                    and all(
                        step.metrics[
                            "residual_and_increment_acceptance_gate"
                        ]
                        for step in self.steps
                    )
                ),
                "fallback_or_regularization_used": bool(
                    any(
                        step.metrics["fallback_count"] > 0
                        or step.metrics["regularization_count"] > 0
                        for step in self.steps
                    )
                ),
                "general_frame_shell_material_newton": False,
                "production_matrix_free_krylov": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": (
                STATEFUL_AXIAL_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY
            ),
        }


def _normalized_step_config(
    config: LoadControlledMatrixFreeNewtonConfig | None,
) -> LoadControlledMatrixFreeNewtonConfig:
    normalized = config or _default_step_config()
    if normalized.target_load_factors != (1.0,):
        raise StatefulAxialMatrixFreeNewtonError(
            "stateful increment-space step config must target exactly (1.0,)"
        )
    return normalized


def _create_solver(
    step_problem: StatefulAxialMatrixFreeLoadStepProblem,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None,
    solver_factory: StateTangentSolverFactory | None,
) -> VectorArcLengthStateTangentSolver:
    if solver_factory is not None:
        if solver_config is not None:
            raise StatefulAxialMatrixFreeNewtonError(
                "solver_config cannot be combined with solver_factory"
            )
        solver = solver_factory(step_problem)
    else:
        solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
            step_problem,
            config=solver_config,
        )
    if not str(getattr(solver, "profile", "")).strip() or not str(
        getattr(solver, "contract_hash", "")
    ).startswith("sha256:"):
        raise StatefulAxialMatrixFreeNewtonError(
            "state tangent solver factory returned an invalid solver"
        )
    return solver


def solve_stateful_axial_matrix_free_load_step(
    problem: StatefulAxialChainProblem,
    accepted_state: StatefulAxialAcceptedState,
    *,
    target_load_factor: float,
    config: LoadControlledMatrixFreeNewtonConfig | None = None,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: StateTangentSolverFactory | None = None,
) -> StatefulAxialMatrixFreeLoadStepResult:
    """Solve and atomically commit one stateful axial matrix-free load step."""

    step_config = _normalized_step_config(config)
    step_problem = StatefulAxialMatrixFreeLoadStepProblem(
        problem=problem,
        accepted_state=accepted_state,
        target_load_factor=target_load_factor,
    )
    parent_bytes_before = accepted_state.canonical_bytes()
    material_bytes_before = tuple(
        state.canonical_bytes() for state in accepted_state.material_states
    )
    solver = _create_solver(
        step_problem,
        solver_config=solver_config,
        solver_factory=solver_factory,
    )
    newton_result = load_controlled_matrix_free_newton_continuation(
        step_problem,
        solver,
        config=step_config,
    )
    final_assembly = step_problem.assemble(
        newton_result.final_free_displacements_m,
        newton_result.final_checkpoint.load_factor,
    )
    parent_unchanged = bool(
        accepted_state.state_hash == step_problem.accepted_state.state_hash
        and accepted_state.canonical_bytes() == parent_bytes_before
        and tuple(
            state.canonical_bytes()
            for state in accepted_state.material_states
        )
        == material_bytes_before
    )
    final_residual_inf_kn = float(
        np.linalg.norm(final_assembly.residual_kn, ord=np.inf)
    )
    solver_contract = bool(
        newton_result.status == "ready"
        and newton_result.metrics["contract_pass"]
        and newton_result.metrics[
            "residual_and_increment_acceptance_gate"
        ]
        and newton_result.metrics["fallback_count"] == 0
        and newton_result.metrics["regularization_count"] == 0
        and final_assembly.parent_state_hash == accepted_state.state_hash
        and final_residual_inf_kn
        <= step_config.residual_tolerance_inf_kn
        and parent_unchanged
    )
    if solver_contract:
        next_state = StatefulAxialAcceptedState(
            case_id=problem.case_id,
            step_index=accepted_state.step_index + 1,
            load_factor=float(target_load_factor),
            displacements_m=tuple(
                float(value) for value in final_assembly.displacements_m
            ),
            material_states=final_assembly.trial_material_states,
        )
        committed = True
        rollback_exact: bool | None = None
    else:
        next_state = accepted_state
        committed = False
        rollback_exact = bool(
            next_state is accepted_state
            and next_state.state_hash == accepted_state.state_hash
            and next_state.canonical_bytes() == parent_bytes_before
            and tuple(
                state.canonical_bytes()
                for state in next_state.material_states
            )
            == material_bytes_before
        )
    material_state_changed = bool(
        committed
        and any(
            before.state_hash != after.state_hash
            for before, after in zip(
                accepted_state.material_states,
                next_state.material_states,
                strict=True,
            )
        )
    )
    return StatefulAxialMatrixFreeLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_state=accepted_state,
        accepted_state=next_state,
        step_problem=step_problem,
        newton_result=newton_result,
        final_assembly=final_assembly,
        metrics={
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "current_tangent_action_contract": (
                STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION
            ),
            "accepted_material_parent_state_hash": (
                accepted_state.state_hash
            ),
            "source_problem_contract_hash": (
                step_problem.source_problem_contract_hash
            ),
            "accepted_state_hash_after": next_state.state_hash,
            "trial_assembly_parent_state_hash": (
                final_assembly.parent_state_hash
            ),
            "target_load_factor": float(target_load_factor),
            "solver_profile": str(solver.profile),
            "solver_contract_hash": str(solver.contract_hash),
            "solver_contract_pass": solver_contract,
            "residual_and_increment_acceptance_gate": bool(
                newton_result.metrics[
                    "residual_and_increment_acceptance_gate"
                ]
            ),
            "final_residual_inf_kn": final_residual_inf_kn,
            "tangent_solve_count": int(
                newton_result.metrics["tangent_solve_count"]
            ),
            "fallback_count": int(
                newton_result.metrics["fallback_count"]
            ),
            "regularization_count": int(
                newton_result.metrics["regularization_count"]
            ),
            "maximum_line_search_backtrack_count": int(
                newton_result.metrics[
                    "maximum_line_search_backtrack_count"
                ]
            ),
            "parent_state_unchanged_during_trial": parent_unchanged,
            "committed": committed,
            "material_state_changed": material_state_changed,
            "rollback_performed": not committed,
            "rollback_exact": rollback_exact,
        },
    )


def run_stateful_axial_matrix_free_load_path(
    problem: StatefulAxialChainProblem,
    load_factors: Iterable[float],
    *,
    initial_state: StatefulAxialAcceptedState | None = None,
    config: LoadControlledMatrixFreeNewtonConfig | None = None,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: StateTangentSolverFactory | None = None,
) -> StatefulAxialMatrixFreeLoadPathResult:
    """Run explicit physical load targets with material commit per step."""

    factors = tuple(
        _finite_scalar(value, name="load_factor") for value in load_factors
    )
    if not factors:
        raise StatefulAxialMatrixFreeNewtonError(
            "load_factors must be a non-empty finite sequence"
        )
    first_state = initial_state or initial_stateful_axial_state(problem)
    validate_stateful_axial_state(problem, first_state)
    accepted = first_state
    rows: list[StatefulAxialMatrixFreeLoadStepResult] = []
    for factor in factors:
        step = solve_stateful_axial_matrix_free_load_step(
            problem,
            accepted,
            target_load_factor=factor,
            config=config,
            solver_config=solver_config,
            solver_factory=solver_factory,
        )
        rows.append(step)
        if not step.committed:
            return StatefulAxialMatrixFreeLoadPathResult(
                status="blocked",
                initial_state=first_state,
                final_state=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_state
    return StatefulAxialMatrixFreeLoadPathResult(
        status="ready",
        initial_state=first_state,
        final_state=accepted,
        steps=tuple(rows),
    )


def finite_difference_stateful_axial_matrix_free_tangent_check(
    step_problem: StatefulAxialMatrixFreeLoadStepProblem,
    *,
    displacement_increments_m: Any,
    increment_load_factor: float,
    direction_m: Any,
    epsilon: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    """Compare one parent-bound tangent action with a centered residual JVP."""

    normalized_epsilon = _finite_scalar(epsilon, name="epsilon")
    if normalized_epsilon <= 0.0:
        raise StatefulAxialMatrixFreeNewtonError(
            "epsilon must be finite and positive"
        )
    normalized_relative_tolerance = _finite_scalar(
        relative_tolerance,
        name="relative_tolerance",
    )
    if normalized_relative_tolerance <= 0.0:
        raise StatefulAxialMatrixFreeNewtonError(
            "relative_tolerance must be finite and positive"
        )
    state = _finite_vector(
        displacement_increments_m,
        name="displacement_increments_m",
        dimension=step_problem.equation_count,
    )
    direction = _finite_vector(
        direction_m,
        name="direction_m",
        dimension=step_problem.equation_count,
    )
    if float(np.linalg.norm(direction, ord=np.inf)) <= 0.0:
        raise StatefulAxialMatrixFreeNewtonError(
            "direction_m must be nonzero"
        )
    parent_hash_before = step_problem.accepted_state.state_hash
    parent_bytes_before = step_problem.accepted_state.canonical_bytes()
    analytic = step_problem.consistent_state_tangent_action_kn_per_m(
        state,
        increment_load_factor,
        direction,
    )
    forward = step_problem.residual_kn(
        state + normalized_epsilon * direction,
        increment_load_factor,
    )
    backward = step_problem.residual_kn(
        state - normalized_epsilon * direction,
        increment_load_factor,
    )
    finite_difference = (forward - backward) / (
        2.0 * normalized_epsilon
    )
    difference = analytic - finite_difference
    absolute_error_inf_kn_per_m = float(
        np.linalg.norm(difference, ord=np.inf)
    )
    reference_inf_kn_per_m = max(
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error_inf_kn_per_m / reference_inf_kn_per_m
    parent_unchanged = bool(
        step_problem.accepted_state.state_hash == parent_hash_before
        and step_problem.accepted_state.canonical_bytes()
        == parent_bytes_before
    )
    return {
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "current_tangent_action_contract": (
            STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION
        ),
        "accepted_material_parent_state_hash": parent_hash_before,
        "analytic_action_data_hash": array_data_hash(
            np.ascontiguousarray(analytic, dtype="<f8")
        ),
        "finite_difference_action_data_hash": array_data_hash(
            np.ascontiguousarray(finite_difference, dtype="<f8")
        ),
        "epsilon": normalized_epsilon,
        "absolute_error_inf_kn_per_m": absolute_error_inf_kn_per_m,
        "relative_error": relative_error,
        "relative_tolerance": normalized_relative_tolerance,
        "same_accepted_material_parent_state": parent_unchanged,
        "contract_pass": bool(
            parent_unchanged
            and relative_error <= normalized_relative_tolerance
        ),
    }


__all__ = [
    "STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION",
    "STATEFUL_AXIAL_MATRIX_FREE_LOAD_PATH_SCHEMA_VERSION",
    "STATEFUL_AXIAL_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY",
    "STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE",
    "STATEFUL_AXIAL_MATRIX_FREE_NEWTON_SCHEMA_VERSION",
    "StateTangentSolverFactory",
    "StatefulAxialMatrixFreeLoadPathResult",
    "StatefulAxialMatrixFreeLoadStepProblem",
    "StatefulAxialMatrixFreeLoadStepResult",
    "StatefulAxialMatrixFreeNewtonError",
    "finite_difference_stateful_axial_matrix_free_tangent_check",
    "run_stateful_axial_matrix_free_load_path",
    "solve_stateful_axial_matrix_free_load_step",
]
