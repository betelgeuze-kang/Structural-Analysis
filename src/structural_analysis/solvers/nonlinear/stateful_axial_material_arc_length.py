"""Transactional material-state bridge for vector arc-length continuation.

The reusable vector arc-length kernel owns displacement/load checkpoints, but
constitutive integration needs a new immutable parent after every accepted
physical step.  This bounded bridge therefore executes exactly one vector
arc-length attempt at a time.  A converged attempt commits the displacement,
load factor, and trial material states atomically; a rejected attempt retains
the exact accepted canonical bytes before reducing the arc length.

This module covers CPU matrix-free axial-chain material path following.  It is
not a geometric frame/shell formulation, production sparse Krylov or HIP
backend, durable checkpoint artifact format, Lee-frame receipt, or G1 closure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
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
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION,
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)
from structural_analysis.solvers.nonlinear.stateful_axial_matrix_free_newton import (
    _source_problem_contract_hash,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthConfig,
    VectorArcLengthResult,
    VectorArcLengthStateTangentSolver,
    build_vector_arc_length_path_contract_hash,
    create_vector_arc_length_checkpoint,
    vector_arc_length_continuation,
)


STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_SCHEMA_VERSION = (
    "stateful-axial-material-arc-length.v1"
)
STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-axial-material-arc-length-checkpoint.v1"
)
STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_PROFILE = (
    "accepted-material-parent-vector-arc-length-cpu-fgmres.v1"
)
STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION = (
    "assemble_stateful_axial_chain(accepted_material_parent,"
    "u_accepted+delta_u,lambda_accepted+delta_lambda)."
    "jacobian_kn_per_m*direction_m"
)
STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION = (
    "negative_partial_residual_partial_load_factor_from_current_element_"
    "tangents_external_loads_and_prescribed_displacements.v1"
)
STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This contract binds each vector arc-length attempt to one immutable "
    "accepted axial material state, uses the current consistent material "
    "tangent in every CPU FGMRES action, commits displacement/load/material "
    "state only after the equilibrium and spherical-constraint gates pass, "
    "and retains exact canonical accepted bytes before failed-step reduction. "
    "It is a bounded axial-chain material path-following integration; it does "
    "not establish geometric frame/shell nonlinear behavior, a durable "
    "serialized checkpoint, production-scale Krylov or HIP parity, Lee-frame "
    "evidence, or G1 full-building closure."
)


class StatefulAxialMaterialArcLengthError(ValueError):
    """Fail-closed stateful axial material arc-length contract error."""


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise StatefulAxialMaterialArcLengthError(f"{name} must be a finite number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise StatefulAxialMaterialArcLengthError(
            f"{name} must be a finite number"
        ) from exc
    if not math.isfinite(normalized):
        raise StatefulAxialMaterialArcLengthError(f"{name} must be a finite number")
    return normalized


def _finite_vector(values: Any, *, name: str, dimension: int) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise StatefulAxialMaterialArcLengthError(
            f"{name} must be a finite FP64 vector"
        ) from exc
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise StatefulAxialMaterialArcLengthError(
            f"{name} must be a finite FP64 vector with shape ({dimension},)"
        )
    return np.ascontiguousarray(vector, dtype=np.float64)


def _require_hash(value: Any, *, name: str) -> str:
    normalized = str(value)
    if (
        len(normalized) != 71
        or not normalized.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise StatefulAxialMaterialArcLengthError(
            f"{name} must be a canonical sha256 digest"
        )
    return normalized


def _material_state_bytes(
    state: StatefulAxialAcceptedState,
) -> tuple[bytes, ...]:
    return tuple(material.canonical_bytes() for material in state.material_states)


def _metric_weights(config: VectorArcLengthConfig, dimension: int) -> np.ndarray:
    values = (
        np.ones(dimension, dtype=np.float64)
        if config.displacement_metric_weights is None
        else _finite_vector(
            config.displacement_metric_weights,
            name="displacement_metric_weights",
            dimension=dimension,
        )
    )
    if np.any(values <= 0.0):
        raise StatefulAxialMaterialArcLengthError(
            "displacement_metric_weights must all be positive"
        )
    return values


def _validate_path_config(
    config: VectorArcLengthConfig,
    *,
    dimension: int,
) -> np.ndarray:
    if type(config.target_monitor_dof_index) is not int or not (
        0 <= config.target_monitor_dof_index < dimension
    ):
        raise StatefulAxialMaterialArcLengthError(
            "target_monitor_dof_index is outside the free displacement vector"
        )
    if type(config.target_direction) is not int or config.target_direction not in {
        -1,
        1,
    }:
        raise StatefulAxialMaterialArcLengthError("target_direction must be -1 or 1")
    _finite_scalar(
        config.target_monitor_displacement_m,
        name="target_monitor_displacement_m",
    )
    positive = {
        "initial_arc_length_m": config.initial_arc_length_m,
        "minimum_arc_length_m": config.minimum_arc_length_m,
        "maximum_arc_length_m": config.maximum_arc_length_m,
        "failed_step_reduction": config.failed_step_reduction,
        "load_factor_metric_scale_m": config.load_factor_metric_scale_m,
        "residual_tolerance_kn": config.residual_tolerance_kn,
        "tangent_solve_residual_tolerance_kn": (
            config.tangent_solve_residual_tolerance_kn
        ),
        "constraint_tolerance_m2": config.constraint_tolerance_m2,
    }
    for name, value in positive.items():
        if _finite_scalar(value, name=name) <= 0.0:
            raise StatefulAxialMaterialArcLengthError(f"{name} must be positive")
    if config.minimum_arc_length_m > config.initial_arc_length_m:
        raise StatefulAxialMaterialArcLengthError(
            "minimum_arc_length_m cannot exceed initial_arc_length_m"
        )
    if config.initial_arc_length_m > config.maximum_arc_length_m:
        raise StatefulAxialMaterialArcLengthError(
            "initial_arc_length_m cannot exceed maximum_arc_length_m"
        )
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise StatefulAxialMaterialArcLengthError(
            "failed_step_reduction must be between zero and one"
        )
    if (
        type(config.maximum_corrector_iterations) is not int
        or config.maximum_corrector_iterations < 1
        or type(config.maximum_attempt_count) is not int
        or config.maximum_attempt_count < 1
    ):
        raise StatefulAxialMaterialArcLengthError(
            "iteration and attempt limits must be positive integers"
        )
    return _metric_weights(config, dimension)


def _solver_binding_payload(
    solver_config: MatrixFreeCPUFGMRESConfig | None,
    solver_factory: Any,
    solver_factory_contract_hash: str | None,
) -> dict[str, Any]:
    if solver_factory is None:
        if solver_factory_contract_hash is not None:
            raise StatefulAxialMaterialArcLengthError(
                "solver_factory_contract_hash requires solver_factory"
            )
        resolved = solver_config or MatrixFreeCPUFGMRESConfig()
        return {
            "kind": "default_matrix_free_cpu_fgmres",
            "config": resolved.contract_payload(),
        }
    if solver_config is not None:
        raise StatefulAxialMaterialArcLengthError(
            "solver_config cannot be combined with solver_factory"
        )
    if solver_factory_contract_hash is None:
        raise StatefulAxialMaterialArcLengthError(
            "custom solver_factory requires solver_factory_contract_hash"
        )
    return {
        "kind": "custom_state_tangent_solver_factory",
        "contract_hash": _require_hash(
            solver_factory_contract_hash,
            name="solver_factory_contract_hash",
        ),
    }


def build_stateful_axial_material_arc_length_path_contract_hash(
    problem: StatefulAxialChainProblem,
    config: VectorArcLengthConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: Any = None,
    solver_factory_contract_hash: str | None = None,
) -> str:
    """Bind the physical source, path controls, and tangent-solver policy."""

    _validate_path_config(config, dimension=len(problem.free_node_indices))
    solver_binding = _solver_binding_payload(
        solver_config,
        solver_factory,
        solver_factory_contract_hash,
    )
    return canonical_hash(
        {
            "schema_version": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_SCHEMA_VERSION,
            "profile": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_PROFILE,
            "source_problem_contract_hash": _source_problem_contract_hash(problem),
            "config": asdict(config),
            "solver_binding": solver_binding,
            "equilibrium_linearization_mode": (
                VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
            ),
            "tangent_action": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION,
            "load_linearization": (
                STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION
            ),
        }
    )


@dataclass(frozen=True)
class StatefulAxialMaterialArcLengthStepProblem:
    """One material-parent-bound physical arc-length attempt."""

    problem: StatefulAxialChainProblem
    accepted_state: StatefulAxialAcceptedState
    attempt_arc_length_m: float

    def __post_init__(self) -> None:
        validate_stateful_axial_state(self.problem, self.accepted_state)
        arc_length = _finite_scalar(
            self.attempt_arc_length_m,
            name="attempt_arc_length_m",
        )
        if arc_length <= 0.0:
            raise StatefulAxialMaterialArcLengthError(
                "attempt_arc_length_m must be positive"
            )
        if not self.problem.free_node_indices:
            raise StatefulAxialMaterialArcLengthError(
                "material arc-length requires at least one free equation"
            )
        object.__setattr__(self, "attempt_arc_length_m", arc_length)

    @property
    def equation_count(self) -> int:
        return len(self.problem.free_node_indices)

    @property
    def source_problem_contract_hash(self) -> str:
        return _source_problem_contract_hash(self.problem)

    @property
    def case_id(self) -> str:
        attempt_hash = canonical_hash(
            {
                "profile": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_PROFILE,
                "source_case_id": self.problem.case_id,
                "source_problem_contract_hash": self.source_problem_contract_hash,
                "accepted_state_hash": self.accepted_state.state_hash,
                "attempt_arc_length_m": self.attempt_arc_length_m,
            }
        )
        return f"{self.problem.case_id}@material-arc-attempt={attempt_hash}"

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.equation_count, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def actual_free_displacements_m(self, displacement_increments_m: Any) -> np.ndarray:
        increments = _finite_vector(
            displacement_increments_m,
            name="displacement_increments_m",
            dimension=self.equation_count,
        )
        accepted = np.asarray(
            self.accepted_state.displacements_m,
            dtype=np.float64,
        )[list(self.problem.free_node_indices)]
        return np.ascontiguousarray(accepted + increments, dtype=np.float64)

    def actual_load_factor(self, increment_load_factor: Any) -> float:
        return float(
            self.accepted_state.load_factor
            + _finite_scalar(
                increment_load_factor,
                name="increment_load_factor",
            )
        )

    def assemble(
        self,
        displacement_increments_m: Any,
        increment_load_factor: Any,
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

    def negative_load_derivative_kn(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
    ) -> np.ndarray:
        """Return ``-partial(residual)/partial(increment_load_factor)``."""

        assembly = self.assemble(
            displacement_increments_m,
            increment_load_factor,
        )
        prescribed_slopes = np.zeros(self.problem.node_count, dtype=np.float64)
        for (
            node,
            reference_displacement,
        ) in self.problem.reference_prescribed_displacements_m:
            prescribed_slopes[node] = reference_displacement

        internal_derivative = np.zeros(
            self.problem.node_count,
            dtype=np.float64,
        )
        for element, response in zip(
            self.problem.elements,
            assembly.element_responses,
            strict=True,
        ):
            tangent_kn_per_m = _finite_scalar(
                response["tangent_kn_per_m"],
                name="element tangent_kn_per_m",
            )
            force_derivative_kn = tangent_kn_per_m * (
                prescribed_slopes[element.node_j] - prescribed_slopes[element.node_i]
            )
            internal_derivative[element.node_i] -= force_derivative_kn
            internal_derivative[element.node_j] += force_derivative_kn

        external_derivative = np.zeros(
            self.problem.node_count,
            dtype=np.float64,
        )
        for node, reference_force_kn in self.problem.reference_external_forces_kn:
            external_derivative[node] += reference_force_kn
        free = list(self.problem.free_node_indices)
        return np.ascontiguousarray(
            external_derivative[free] - internal_derivative[free],
            dtype=np.float64,
        )

    def reference_load_kn(self) -> np.ndarray:
        zero = np.zeros(self.equation_count, dtype=np.float64)
        reference = self.negative_load_derivative_kn(zero, 0.0)
        if float(np.linalg.norm(reference, ord=np.inf)) <= 0.0:
            raise StatefulAxialMaterialArcLengthError(
                "physical load-factor derivative must be nonzero"
            )
        return reference

    @property
    def reference_preconditioner_contract(self) -> str:
        return (
            "stateful-axial-material-arc-accepted-parent-reference-tangent-"
            "csr-n-per-m.v1"
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
                STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION
            ),
            "reference_load_free_n_data_hash": array_data_hash(reference_load_n),
            "residual_force_unit": "kN",
            "displacement_unit": "m",
            "tangent_action_unit": "kN/m",
            "load_factor_unit": "dimensionless",
        }


StatefulAxialMaterialArcLengthSolverFactory = Callable[
    [StatefulAxialMaterialArcLengthStepProblem],
    VectorArcLengthStateTangentSolver,
]


def _checkpoint_hash_payload(
    *,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_state: StatefulAxialAcceptedState,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    attempt_count: int,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": (
            STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ),
        "source_problem_contract_hash": source_problem_contract_hash,
        "path_contract_hash": path_contract_hash,
        "accepted_state_hash": accepted_state.state_hash,
        "current_arc_length_m": current_arc_length_m,
        "previous_tangent_displacements": (
            None
            if previous_tangent_displacements is None
            else list(previous_tangent_displacements)
        ),
        "previous_tangent_load_factor": previous_tangent_load_factor,
        "attempt_count": attempt_count,
        "last_attempt_outcome": last_attempt_outcome,
        "last_attempt_stop_reason": last_attempt_stop_reason,
    }


@dataclass(frozen=True)
class StatefulAxialMaterialArcLengthCheckpoint:
    schema_version: str
    source_problem_contract_hash: str
    path_contract_hash: str
    accepted_state: StatefulAxialAcceptedState
    current_arc_length_m: float
    previous_tangent_displacements: tuple[float, ...] | None
    previous_tangent_load_factor: float | None
    attempt_count: int
    last_attempt_outcome: str
    last_attempt_stop_reason: str
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != (
            STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ):
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint schema_version is unsupported"
            )
        _require_hash(
            self.source_problem_contract_hash,
            name="checkpoint.source_problem_contract_hash",
        )
        _require_hash(
            self.path_contract_hash,
            name="checkpoint.path_contract_hash",
        )
        if self.accepted_state.compute_state_hash() != self.accepted_state.state_hash:
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint accepted state hash validation failed"
            )
        arc_length = _finite_scalar(
            self.current_arc_length_m,
            name="checkpoint.current_arc_length_m",
        )
        if arc_length <= 0.0:
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint.current_arc_length_m must be positive"
            )
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint.attempt_count must be a non-negative integer"
            )
        if not str(self.last_attempt_outcome).strip():
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint.last_attempt_outcome is required"
            )
        if not str(self.last_attempt_stop_reason).strip():
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint.last_attempt_stop_reason is required"
            )
        tangent_displacements = self.previous_tangent_displacements
        tangent_load = self.previous_tangent_load_factor
        if (tangent_displacements is None) != (tangent_load is None):
            raise StatefulAxialMaterialArcLengthError(
                "checkpoint previous tangent fields must both be present or absent"
            )
        if tangent_displacements is not None:
            normalized = tuple(
                float(value)
                for value in _finite_vector(
                    tangent_displacements,
                    name="checkpoint.previous_tangent_displacements",
                    dimension=len(tangent_displacements),
                )
            )
            object.__setattr__(self, "previous_tangent_displacements", normalized)
            _finite_scalar(
                tangent_load,
                name="checkpoint.previous_tangent_load_factor",
            )
        payload = _checkpoint_hash_payload(
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_state=self.accepted_state,
            current_arc_length_m=arc_length,
            previous_tangent_displacements=self.previous_tangent_displacements,
            previous_tangent_load_factor=self.previous_tangent_load_factor,
            attempt_count=self.attempt_count,
            last_attempt_outcome=self.last_attempt_outcome,
            last_attempt_stop_reason=self.last_attempt_stop_reason,
        )
        expected_hash = canonical_hash(payload)
        if self.checkpoint_hash and self.checkpoint_hash != expected_hash:
            raise StatefulAxialMaterialArcLengthError("checkpoint_hash mismatch")
        if not self.checkpoint_hash:
            object.__setattr__(self, "checkpoint_hash", expected_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            **_checkpoint_hash_payload(
                source_problem_contract_hash=self.source_problem_contract_hash,
                path_contract_hash=self.path_contract_hash,
                accepted_state=self.accepted_state,
                current_arc_length_m=self.current_arc_length_m,
                previous_tangent_displacements=(self.previous_tangent_displacements),
                previous_tangent_load_factor=(self.previous_tangent_load_factor),
                attempt_count=self.attempt_count,
                last_attempt_outcome=self.last_attempt_outcome,
                last_attempt_stop_reason=self.last_attempt_stop_reason,
            ),
            "accepted_state": self.accepted_state.to_dict(),
            "checkpoint_hash": self.checkpoint_hash,
        }


def _create_checkpoint(
    *,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_state: StatefulAxialAcceptedState,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    attempt_count: int,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> StatefulAxialMaterialArcLengthCheckpoint:
    return StatefulAxialMaterialArcLengthCheckpoint(
        schema_version=(STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION),
        source_problem_contract_hash=source_problem_contract_hash,
        path_contract_hash=path_contract_hash,
        accepted_state=accepted_state,
        current_arc_length_m=current_arc_length_m,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        attempt_count=attempt_count,
        last_attempt_outcome=last_attempt_outcome,
        last_attempt_stop_reason=last_attempt_stop_reason,
    )


def validate_stateful_axial_material_arc_length_checkpoint(
    checkpoint: StatefulAxialMaterialArcLengthCheckpoint,
    problem: StatefulAxialChainProblem,
    config: VectorArcLengthConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: Any = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialMaterialArcLengthCheckpoint:
    if type(checkpoint) is not StatefulAxialMaterialArcLengthCheckpoint:
        raise StatefulAxialMaterialArcLengthError("checkpoint type is invalid")
    validate_stateful_axial_state(problem, checkpoint.accepted_state)
    expected_source_hash = _source_problem_contract_hash(problem)
    if checkpoint.source_problem_contract_hash != expected_source_hash:
        raise StatefulAxialMaterialArcLengthError(
            "checkpoint source problem contract mismatch"
        )
    expected_path_hash = build_stateful_axial_material_arc_length_path_contract_hash(
        problem,
        config,
        solver_config=solver_config,
        solver_factory=solver_factory,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )
    if checkpoint.path_contract_hash != expected_path_hash:
        raise StatefulAxialMaterialArcLengthError("checkpoint path contract mismatch")
    if checkpoint.current_arc_length_m > config.maximum_arc_length_m:
        raise StatefulAxialMaterialArcLengthError(
            "checkpoint current arc length exceeds the configured maximum"
        )
    if checkpoint.attempt_count > config.maximum_attempt_count:
        raise StatefulAxialMaterialArcLengthError(
            "checkpoint attempt count exceeds the configured budget"
        )
    dimension = len(problem.free_node_indices)
    if (
        checkpoint.previous_tangent_displacements is not None
        and len(checkpoint.previous_tangent_displacements) != dimension
    ):
        raise StatefulAxialMaterialArcLengthError(
            "checkpoint previous tangent dimension mismatch"
        )
    expected = _create_checkpoint(
        source_problem_contract_hash=checkpoint.source_problem_contract_hash,
        path_contract_hash=checkpoint.path_contract_hash,
        accepted_state=checkpoint.accepted_state,
        current_arc_length_m=checkpoint.current_arc_length_m,
        previous_tangent_displacements=(checkpoint.previous_tangent_displacements),
        previous_tangent_load_factor=(checkpoint.previous_tangent_load_factor),
        attempt_count=checkpoint.attempt_count,
        last_attempt_outcome=checkpoint.last_attempt_outcome,
        last_attempt_stop_reason=checkpoint.last_attempt_stop_reason,
    )
    if checkpoint.checkpoint_hash != expected.checkpoint_hash:
        raise StatefulAxialMaterialArcLengthError("checkpoint_hash mismatch")
    return checkpoint


@dataclass(frozen=True)
class StatefulAxialMaterialArcLengthAttempt:
    attempt_index: int
    arc_length_m: float
    outcome: str
    stop_reason: str
    parent_state: StatefulAxialAcceptedState
    accepted_state: StatefulAxialAcceptedState
    vector_result: VectorArcLengthResult
    final_assembly: StatefulAxialAssemblyState | None
    rollback_exact: bool
    material_state_changed: bool
    next_arc_length_m: float
    checkpoint: StatefulAxialMaterialArcLengthCheckpoint

    @property
    def committed(self) -> bool:
        return self.outcome == "committed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "arc_length_m": self.arc_length_m,
            "outcome": self.outcome,
            "stop_reason": self.stop_reason,
            "committed": self.committed,
            "parent_state_hash": self.parent_state.state_hash,
            "accepted_state_hash": self.accepted_state.state_hash,
            "rollback_exact": self.rollback_exact,
            "material_state_changed": self.material_state_changed,
            "next_arc_length_m": self.next_arc_length_m,
            "vector_result": self.vector_result.to_dict(),
            "final_assembly": (
                None if self.final_assembly is None else self.final_assembly.to_dict()
            ),
            "checkpoint": self.checkpoint.to_dict(),
        }


@dataclass(frozen=True)
class StatefulAxialMaterialArcLengthResult:
    status: str
    terminal_reason: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    config: VectorArcLengthConfig
    initial_checkpoint: StatefulAxialMaterialArcLengthCheckpoint
    final_checkpoint: StatefulAxialMaterialArcLengthCheckpoint
    checkpoints: tuple[StatefulAxialMaterialArcLengthCheckpoint, ...]
    attempts: tuple[StatefulAxialMaterialArcLengthAttempt, ...]
    metrics: dict[str, Any]

    @property
    def initial_state(self) -> StatefulAxialAcceptedState:
        return self.initial_checkpoint.accepted_state

    @property
    def final_state(self) -> StatefulAxialAcceptedState:
        return self.final_checkpoint.accepted_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "profile": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_PROFILE,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": self.source_problem_contract_hash,
            "path_contract_hash": self.path_contract_hash,
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "tangent_action": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION,
            "load_linearization": (
                STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION
            ),
            "config": asdict(self.config),
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": [row.to_dict() for row in self.attempts],
            "metrics": dict(self.metrics),
            "claims": {
                "stateful_material_vector_arc_length_path": bool(
                    self.metrics["contract_pass"]
                ),
                "accepted_material_parent_rebound_each_step": bool(
                    self.metrics["accepted_step_count"] > 0
                ),
                "material_state_commit_rollback": bool(
                    self.metrics["material_state_commit_rollback"]
                ),
                "failed_attempt_material_state_rollback_exact": bool(
                    self.metrics["rollback_exact"]
                ),
                "descending_load_branch_observed": bool(
                    self.metrics["descending_load_branch_observed"]
                ),
                "matrix_free_cpu_fgmres_tangent_solves": bool(
                    self.metrics["tangent_solve_count"] > 0
                ),
                "material_state_embedded_checkpoint": True,
                "durable_serialized_checkpoint": False,
                "geometric_frame_shell_arc_length": False,
                "production_matrix_free_krylov": False,
                "rocm_hip_parity": False,
                "lee_frame_benchmark": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CLAIM_BOUNDARY,
        }


def _target_reached(
    problem: StatefulAxialChainProblem,
    state: StatefulAxialAcceptedState,
    config: VectorArcLengthConfig,
) -> bool:
    free_node = problem.free_node_indices[config.target_monitor_dof_index]
    monitored = state.displacements_m[free_node]
    return bool(
        config.target_direction * (monitored - config.target_monitor_displacement_m)
        >= 0.0
    )


def _create_solver(
    step_problem: StatefulAxialMaterialArcLengthStepProblem,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None,
    solver_factory: StatefulAxialMaterialArcLengthSolverFactory | None,
) -> VectorArcLengthStateTangentSolver:
    solver = (
        create_matrix_free_cpu_fgmres_state_tangent_solver(
            step_problem,
            config=solver_config,
        )
        if solver_factory is None
        else solver_factory(step_problem)
    )
    if not str(getattr(solver, "profile", "")).strip():
        raise StatefulAxialMaterialArcLengthError(
            "state tangent solver profile is invalid"
        )
    _require_hash(
        getattr(solver, "contract_hash", ""),
        name="state tangent solver contract_hash",
    )
    return solver


def _single_attempt_config(
    config: VectorArcLengthConfig,
    *,
    current_arc_length_m: float,
    metric_weights: np.ndarray,
) -> VectorArcLengthConfig:
    return replace(
        config,
        target_monitor_displacement_m=math.nextafter(
            0.0,
            float(config.target_direction),
        ),
        initial_arc_length_m=current_arc_length_m,
        displacement_metric_weights=tuple(float(value) for value in metric_weights),
        maximum_attempt_count=1,
    )


def _single_vector_attempt(
    step_problem: StatefulAxialMaterialArcLengthStepProblem,
    *,
    config: VectorArcLengthConfig,
    metric_weights: np.ndarray,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    solver: VectorArcLengthStateTangentSolver,
) -> VectorArcLengthResult:
    local_config = _single_attempt_config(
        config,
        current_arc_length_m=step_problem.attempt_arc_length_m,
        metric_weights=metric_weights,
    )
    reference_load = step_problem.reference_load_kn()
    local_path_hash = build_vector_arc_length_path_contract_hash(
        case_id=step_problem.case_id,
        config=local_config,
        reference_load_kn=reference_load,
        displacement_metric_weights=metric_weights,
        tangent_solver_profile=str(solver.profile),
        tangent_solver_contract_hash=str(solver.contract_hash),
        tangent_solver_mode=VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
        equilibrium_linearization_mode=(
            VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        ),
    )
    origin = create_vector_arc_length_checkpoint(
        case_id=step_problem.case_id,
        path_contract_hash=local_path_hash,
        step_index=step_problem.accepted_state.step_index,
        free_displacements_m=np.zeros(
            step_problem.equation_count,
            dtype=np.float64,
        ),
        load_factor=0.0,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        current_arc_length_m=step_problem.attempt_arc_length_m,
    )
    return vector_arc_length_continuation(
        step_problem,
        config=local_config,
        resume_from=origin,
        state_tangent_solver=solver,
    )


def stateful_axial_material_arc_length_continuation(
    problem: StatefulAxialChainProblem,
    *,
    config: VectorArcLengthConfig,
    initial_state: StatefulAxialAcceptedState | None = None,
    checkpoint: StatefulAxialMaterialArcLengthCheckpoint | None = None,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: StatefulAxialMaterialArcLengthSolverFactory | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialMaterialArcLengthResult:
    """Trace an axial material path with commit/rollback per arc attempt."""

    if initial_state is not None and checkpoint is not None:
        raise StatefulAxialMaterialArcLengthError(
            "initial_state and checkpoint are mutually exclusive"
        )
    dimension = len(problem.free_node_indices)
    metric_weights = _validate_path_config(config, dimension=dimension)
    source_hash = _source_problem_contract_hash(problem)
    path_hash = build_stateful_axial_material_arc_length_path_contract_hash(
        problem,
        config,
        solver_config=solver_config,
        solver_factory=solver_factory,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )
    if checkpoint is None:
        accepted = initial_state or initial_stateful_axial_state(problem)
        validate_stateful_axial_state(problem, accepted)
        current_arc_length_m = config.initial_arc_length_m
        previous_tangent_displacements = None
        previous_tangent_load_factor = None
        cumulative_attempt_count = 0
        initial_checkpoint = _create_checkpoint(
            source_problem_contract_hash=source_hash,
            path_contract_hash=path_hash,
            accepted_state=accepted,
            current_arc_length_m=current_arc_length_m,
            previous_tangent_displacements=None,
            previous_tangent_load_factor=None,
            attempt_count=0,
            last_attempt_outcome="initial",
            last_attempt_stop_reason="initial_equilibrium_state",
        )
        restart_consumed = False
    else:
        initial_checkpoint = validate_stateful_axial_material_arc_length_checkpoint(
            checkpoint,
            problem,
            config,
            solver_config=solver_config,
            solver_factory=solver_factory,
            solver_factory_contract_hash=solver_factory_contract_hash,
        )
        accepted = initial_checkpoint.accepted_state
        current_arc_length_m = initial_checkpoint.current_arc_length_m
        previous_tangent_displacements = (
            initial_checkpoint.previous_tangent_displacements
        )
        previous_tangent_load_factor = initial_checkpoint.previous_tangent_load_factor
        cumulative_attempt_count = initial_checkpoint.attempt_count
        restart_consumed = True

    if _target_reached(problem, accepted, config):
        raise StatefulAxialMaterialArcLengthError(
            "initial or checkpoint state already reached the monitor target"
        )
    initial_monitor_node = problem.free_node_indices[config.target_monitor_dof_index]
    initial_monitor_displacement = accepted.displacements_m[initial_monitor_node]
    if (
        config.target_direction
        * (config.target_monitor_displacement_m - initial_monitor_displacement)
        <= 0.0
    ):
        raise StatefulAxialMaterialArcLengthError(
            "monitor target must lie ahead of the accepted state"
        )

    checkpoints = [initial_checkpoint]
    attempts: list[StatefulAxialMaterialArcLengthAttempt] = []
    terminal_reason = "maximum_attempt_count_exhausted"

    while cumulative_attempt_count < config.maximum_attempt_count:
        if _target_reached(problem, accepted, config):
            terminal_reason = "target_monitor_displacement_reached"
            break
        if current_arc_length_m < config.minimum_arc_length_m:
            terminal_reason = "minimum_arc_length_exhausted"
            break
        parent = accepted
        parent_bytes = parent.canonical_bytes()
        parent_material_bytes = _material_state_bytes(parent)
        step_problem = StatefulAxialMaterialArcLengthStepProblem(
            problem=problem,
            accepted_state=parent,
            attempt_arc_length_m=current_arc_length_m,
        )
        solver = _create_solver(
            step_problem,
            solver_config=solver_config,
            solver_factory=solver_factory,
        )
        vector_result = _single_vector_attempt(
            step_problem,
            config=config,
            metric_weights=metric_weights,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
            solver=solver,
        )
        if len(vector_result.attempts) != 1:
            raise StatefulAxialMaterialArcLengthError(
                "single-attempt vector kernel returned an invalid attempt count"
            )
        vector_attempt = vector_result.attempts[0]
        cumulative_attempt_count += 1
        arc_length_attempted = current_arc_length_m
        parent_unchanged = bool(
            parent.state_hash == step_problem.accepted_state.state_hash
            and parent.canonical_bytes() == parent_bytes
            and _material_state_bytes(parent) == parent_material_bytes
        )

        final_assembly: StatefulAxialAssemblyState | None = None
        commit_gate = False
        material_state_changed = False
        if vector_attempt["accepted"] is True:
            local_final = vector_result.final_checkpoint
            final_assembly = step_problem.assemble(
                np.asarray(local_final.free_displacements_m, dtype=np.float64),
                local_final.load_factor,
            )
            residual_inf_kn = float(
                np.linalg.norm(final_assembly.residual_kn, ord=np.inf)
            )
            parent_free = np.asarray(parent.displacements_m, dtype=np.float64)[
                list(problem.free_node_indices)
            ]
            trial_free = final_assembly.displacements_m[list(problem.free_node_indices)]
            displacement_increment = trial_free - parent_free
            load_increment = final_assembly.target_load_factor - parent.load_factor
            arc_residual = float(
                np.dot(
                    metric_weights * displacement_increment,
                    displacement_increment,
                )
                + (config.load_factor_metric_scale_m * load_increment) ** 2
                - arc_length_attempted**2
            )
            monitor_increment = displacement_increment[config.target_monitor_dof_index]
            commit_gate = bool(
                vector_result.status == "ready"
                and vector_result.metrics["contract_pass"] is True
                and vector_result.metrics["fallback_count"] == 0
                and vector_result.metrics["regularization_count"] == 0
                and parent_unchanged
                and final_assembly.parent_state_hash == parent.state_hash
                and residual_inf_kn <= config.residual_tolerance_kn
                and abs(arc_residual) <= config.constraint_tolerance_m2
                and config.target_direction * monitor_increment > 0.0
            )

        if commit_gate:
            assert final_assembly is not None
            local_final = vector_result.final_checkpoint
            accepted = StatefulAxialAcceptedState(
                case_id=problem.case_id,
                step_index=parent.step_index + 1,
                load_factor=float(final_assembly.target_load_factor),
                displacements_m=tuple(
                    float(value) for value in final_assembly.displacements_m
                ),
                material_states=final_assembly.trial_material_states,
            )
            previous_tangent_displacements = local_final.previous_tangent_displacements
            previous_tangent_load_factor = local_final.previous_tangent_load_factor
            material_state_changed = any(
                before.state_hash != after.state_hash
                for before, after in zip(
                    parent.material_states,
                    accepted.material_states,
                    strict=True,
                )
            )
            outcome = "committed"
            stop_reason = str(vector_attempt["stop_reason"])
            next_arc_length_m = arc_length_attempted
            rollback_exact = True
        else:
            accepted = parent
            next_arc_length_m = arc_length_attempted * config.failed_step_reduction
            outcome = "rolled_back"
            stop_reason = (
                str(vector_attempt["stop_reason"])
                if vector_attempt["accepted"] is False
                else "stateful_commit_gate_failed"
            )
            rollback_exact = bool(
                parent_unchanged
                and accepted is parent
                and accepted.state_hash == parent.state_hash
                and accepted.canonical_bytes() == parent_bytes
                and _material_state_bytes(accepted) == parent_material_bytes
            )
            current_arc_length_m = next_arc_length_m

        boundary = _create_checkpoint(
            source_problem_contract_hash=source_hash,
            path_contract_hash=path_hash,
            accepted_state=accepted,
            current_arc_length_m=next_arc_length_m,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
            attempt_count=cumulative_attempt_count,
            last_attempt_outcome=outcome,
            last_attempt_stop_reason=stop_reason,
        )
        attempt = StatefulAxialMaterialArcLengthAttempt(
            attempt_index=cumulative_attempt_count,
            arc_length_m=arc_length_attempted,
            outcome=outcome,
            stop_reason=stop_reason,
            parent_state=parent,
            accepted_state=accepted,
            vector_result=vector_result,
            final_assembly=final_assembly if commit_gate else None,
            rollback_exact=rollback_exact,
            material_state_changed=material_state_changed,
            next_arc_length_m=next_arc_length_m,
            checkpoint=boundary,
        )
        attempts.append(attempt)
        checkpoints.append(boundary)

        if not commit_gate and next_arc_length_m < config.minimum_arc_length_m:
            terminal_reason = "minimum_arc_length_exhausted"
            break
    else:
        if _target_reached(problem, accepted, config):
            terminal_reason = "target_monitor_displacement_reached"

    target_reached = _target_reached(problem, accepted, config)
    if target_reached:
        terminal_reason = "target_monitor_displacement_reached"
    committed_attempts = [row for row in attempts if row.committed]
    rejected_attempts = [row for row in attempts if not row.committed]
    accepted_states = [initial_checkpoint.accepted_state] + [
        row.accepted_state for row in committed_attempts
    ]
    monitored_displacements = [
        state.displacements_m[initial_monitor_node] for state in accepted_states
    ]
    load_factors = [state.load_factor for state in accepted_states]
    load_differences = [
        right - left for left, right in zip(load_factors, load_factors[1:])
    ]
    residual_errors = [
        float(np.linalg.norm(row.final_assembly.residual_kn, ord=np.inf))
        for row in committed_attempts
        if row.final_assembly is not None
    ]
    constraint_errors = [
        float(row.vector_result.metrics["maximum_accepted_constraint_residual_m2"])
        for row in committed_attempts
    ]
    rollback_exact = all(row.rollback_exact for row in rejected_attempts)
    monitor_monotonic = all(
        config.target_direction * (right - left) > 0.0
        for left, right in zip(
            monitored_displacements,
            monitored_displacements[1:],
        )
    )
    tangent_solve_count = sum(
        int(row.vector_result.metrics["external_tangent_solve_count"])
        for row in attempts
    )
    fallback_count = sum(
        int(row.vector_result.metrics["fallback_count"]) for row in attempts
    )
    regularization_count = sum(
        int(row.vector_result.metrics["regularization_count"]) for row in attempts
    )
    contract_pass = bool(
        target_reached
        and committed_attempts
        and rollback_exact
        and monitor_monotonic
        and tangent_solve_count > 0
        and fallback_count == 0
        and regularization_count == 0
        and max(residual_errors, default=math.inf) <= config.residual_tolerance_kn
        and max(constraint_errors, default=math.inf) <= config.constraint_tolerance_m2
    )
    metrics = {
        "contract_pass": contract_pass,
        "equation_count": dimension,
        "target_monitor_displacement_reached": target_reached,
        "run_attempt_count": len(attempts),
        "attempt_count": checkpoints[-1].attempt_count,
        "accepted_step_count": len(committed_attempts),
        "rejected_step_count": len(rejected_attempts),
        "failed_step_reduction_count": len(rejected_attempts),
        "rollback_exact": rollback_exact,
        "material_state_commit_rollback": bool(committed_attempts and rollback_exact),
        "material_state_changed_step_count": sum(
            int(row.material_state_changed) for row in committed_attempts
        ),
        "accepted_material_parent_rebind_count": len(committed_attempts),
        "tangent_solve_count": tangent_solve_count,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "maximum_accepted_residual_inf_norm_kn": max(
            residual_errors,
            default=math.inf,
        ),
        "maximum_accepted_constraint_residual_m2": max(
            constraint_errors,
            default=math.inf,
        ),
        "monitor_displacement_monotonic_in_target_direction": (monitor_monotonic),
        "descending_load_branch_observed": any(
            value < 0.0 for value in load_differences
        ),
        "maximum_load_factor": max(load_factors),
        "minimum_load_factor": min(load_factors),
        "final_load_factor": accepted.load_factor,
        "final_monitor_displacement_m": accepted.displacements_m[initial_monitor_node],
        "restart_checkpoint_consumed": restart_consumed,
        "source_problem_contract_hash": source_hash,
        "path_contract_hash": path_hash,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "claim_boundary": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CLAIM_BOUNDARY,
    }
    return StatefulAxialMaterialArcLengthResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        source_case_id=problem.case_id,
        source_problem_contract_hash=source_hash,
        path_contract_hash=path_hash,
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=checkpoints[-1],
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


def finite_difference_stateful_axial_material_arc_length_linearization_check(
    step_problem: StatefulAxialMaterialArcLengthStepProblem,
    *,
    displacement_increments_m: Any,
    increment_load_factor: float,
    direction_m: Any,
    displacement_epsilon_m: float = 1.0e-8,
    load_factor_epsilon: float = 1.0e-7,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    """Check displacement JVP and load derivative from one material parent."""

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
        raise StatefulAxialMaterialArcLengthError("direction_m must be nonzero")
    displacement_epsilon = _finite_scalar(
        displacement_epsilon_m,
        name="displacement_epsilon_m",
    )
    load_epsilon = _finite_scalar(
        load_factor_epsilon,
        name="load_factor_epsilon",
    )
    tolerance = _finite_scalar(
        relative_tolerance,
        name="relative_tolerance",
    )
    if displacement_epsilon <= 0.0 or load_epsilon <= 0.0 or tolerance <= 0.0:
        raise StatefulAxialMaterialArcLengthError(
            "finite-difference epsilons and tolerance must be positive"
        )
    load_factor = _finite_scalar(
        increment_load_factor,
        name="increment_load_factor",
    )
    parent_hash = step_problem.accepted_state.state_hash
    parent_bytes = step_problem.accepted_state.canonical_bytes()
    material_bytes = _material_state_bytes(step_problem.accepted_state)

    analytic_displacement = step_problem.consistent_state_tangent_action_kn_per_m(
        state,
        load_factor,
        direction,
    )
    displacement_forward = step_problem.residual_kn(
        state + displacement_epsilon * direction,
        load_factor,
    )
    displacement_backward = step_problem.residual_kn(
        state - displacement_epsilon * direction,
        load_factor,
    )
    finite_difference_displacement = (displacement_forward - displacement_backward) / (
        2.0 * displacement_epsilon
    )
    analytic_load = step_problem.negative_load_derivative_kn(
        state,
        load_factor,
    )
    load_forward = step_problem.residual_kn(
        state,
        load_factor + load_epsilon,
    )
    load_backward = step_problem.residual_kn(
        state,
        load_factor - load_epsilon,
    )
    finite_difference_negative_load = -(load_forward - load_backward) / (
        2.0 * load_epsilon
    )

    displacement_error = float(
        np.linalg.norm(
            analytic_displacement - finite_difference_displacement,
            ord=np.inf,
        )
    )
    displacement_scale = max(
        float(np.linalg.norm(finite_difference_displacement, ord=np.inf)),
        1.0,
    )
    load_error = float(
        np.linalg.norm(
            analytic_load - finite_difference_negative_load,
            ord=np.inf,
        )
    )
    load_scale = max(
        float(np.linalg.norm(finite_difference_negative_load, ord=np.inf)),
        1.0,
    )
    displacement_relative_error = displacement_error / displacement_scale
    load_relative_error = load_error / load_scale
    parent_unchanged = bool(
        step_problem.accepted_state.state_hash == parent_hash
        and step_problem.accepted_state.canonical_bytes() == parent_bytes
        and _material_state_bytes(step_problem.accepted_state) == material_bytes
    )
    return {
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "tangent_action": STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION,
        "load_linearization": (STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION),
        "accepted_material_parent_state_hash": parent_hash,
        "analytic_displacement_action_data_hash": array_data_hash(
            np.ascontiguousarray(analytic_displacement, dtype="<f8")
        ),
        "finite_difference_displacement_action_data_hash": array_data_hash(
            np.ascontiguousarray(finite_difference_displacement, dtype="<f8")
        ),
        "analytic_negative_load_derivative_data_hash": array_data_hash(
            np.ascontiguousarray(analytic_load, dtype="<f8")
        ),
        "finite_difference_negative_load_derivative_data_hash": array_data_hash(
            np.ascontiguousarray(finite_difference_negative_load, dtype="<f8")
        ),
        "displacement_relative_error": displacement_relative_error,
        "load_factor_relative_error": load_relative_error,
        "relative_tolerance": tolerance,
        "same_accepted_material_parent_state": parent_unchanged,
        "contract_pass": bool(
            parent_unchanged
            and displacement_relative_error <= tolerance
            and load_relative_error <= tolerance
        ),
    }


__all__ = [
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CLAIM_BOUNDARY",
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION",
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_PROFILE",
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_SCHEMA_VERSION",
    "STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION",
    "StatefulAxialMaterialArcLengthAttempt",
    "StatefulAxialMaterialArcLengthCheckpoint",
    "StatefulAxialMaterialArcLengthError",
    "StatefulAxialMaterialArcLengthResult",
    "StatefulAxialMaterialArcLengthSolverFactory",
    "StatefulAxialMaterialArcLengthStepProblem",
    "build_stateful_axial_material_arc_length_path_contract_hash",
    "finite_difference_stateful_axial_material_arc_length_linearization_check",
    "stateful_axial_material_arc_length_continuation",
    "validate_stateful_axial_material_arc_length_checkpoint",
]
