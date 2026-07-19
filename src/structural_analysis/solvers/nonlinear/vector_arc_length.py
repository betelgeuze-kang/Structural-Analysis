"""Deterministic multi-DOF spherical arc-length continuation.

The kernel accepts a vector internal-force operator, its consistent tangent,
and one fixed reference-load vector. Equilibrium and the spherical path
constraint are corrected with either the default dense augmented Newton solve
or two contract-bound external tangent solves through a Schur reduction. It
does not provide a frame/shell formulation or a sparse production backend.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Protocol

import numpy as np


VECTOR_ARC_LENGTH_SCHEMA_VERSION = "structural-analysis-vector-arc-length.v1"
VECTOR_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "structural-analysis-vector-arc-length-checkpoint.v1"
)
VECTOR_ARC_LENGTH_RESIDUAL_FORMULA = (
    "F_internal(free_displacements)-load_factor*reference_load"
)
VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA = (
    "delta_u^T*W*delta_u+(load_factor_metric_scale*delta_load_factor)^2"
    "-arc_length^2"
)
VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_PROFILE = (
    "numpy_dense_augmented_newton_solve.v1"
)
VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_MODE = "dense_augmented_matrix"
VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE = "materialized_tangent_matrix"
VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE = "state_tangent_operator"
VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE = (
    "proportional_reference_load"
)
VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE = (
    "load_factor_coupled_residual"
)
VECTOR_ARC_LENGTH_LOAD_COUPLED_RESIDUAL_FORMULA = (
    "problem.residual_kn(free_displacements,load_factor)"
)
VECTOR_ARC_LENGTH_LOAD_COUPLED_LINEARIZATION_FORMULA = (
    "J_u=partial_R/partial_u;load_rhs=-partial_R/partial_load_factor"
)
VECTOR_ARC_LENGTH_PROPORTIONAL_LINEARIZATION_FORMULA = (
    "J_u=partial_F_internal/partial_u;load_rhs=reference_load"
)


class VectorArcLengthEquilibriumProblem(Protocol):
    """Multi-DOF proportional-load equilibrium independent of tangent storage."""

    case_id: str

    def initial_free_displacements_m(self) -> np.ndarray: ...

    def initial_load_factor(self) -> float: ...

    def reference_load_kn(self) -> np.ndarray: ...

    def internal_force_kn(self, free_displacements_m: np.ndarray) -> np.ndarray: ...


class VectorArcLengthProblem(VectorArcLengthEquilibriumProblem, Protocol):
    """Equilibrium problem exposing a materialized consistent tangent."""

    def consistent_tangent_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray: ...


@dataclass(frozen=True)
class VectorArcLengthTangentSolve:
    """One fail-closed external consistent-tangent solve result."""

    profile: str
    contract_hash: str
    contract_pass: bool
    terminal_reason: str
    solution_free: tuple[float, ...]
    receipt: dict[str, Any]


class VectorArcLengthTangentSolver(Protocol):
    """External tangent solver used by predictor and Schur corrector paths."""

    profile: str
    contract_hash: str

    def solve(
        self,
        tangent_kn_per_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve: ...


class VectorArcLengthStateTangentProblem(
    VectorArcLengthEquilibriumProblem,
    Protocol,
):
    """Equilibrium problem exposing a matrix-free consistent-tangent action."""

    def consistent_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        direction_m: np.ndarray,
    ) -> np.ndarray: ...


class VectorArcLengthLoadCoupledStateTangentProblem(Protocol):
    """Equilibrium whose residual and displacement tangent depend on load."""

    case_id: str

    def initial_free_displacements_m(self) -> np.ndarray: ...

    def initial_load_factor(self) -> float: ...

    def reference_load_kn(self) -> np.ndarray: ...

    def residual_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray: ...

    def negative_load_derivative_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray: ...

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray: ...


class VectorArcLengthStateTangentSolver(Protocol):
    """State-bound solver that need not materialize a dense tangent matrix."""

    profile: str
    contract_hash: str

    def solve_at_state(
        self,
        problem: (
            VectorArcLengthStateTangentProblem
            | VectorArcLengthLoadCoupledStateTangentProblem
        ),
        free_displacements_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        load_factor: float,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve: ...


class VectorArcLengthContractError(ValueError):
    """Stable fail-closed configuration, operator, or checkpoint error."""


@dataclass(frozen=True)
class VectorArcLengthConfig:
    target_monitor_dof_index: int = 0
    target_monitor_displacement_m: float = 0.45
    target_direction: int = 1
    initial_arc_length_m: float = 0.08
    minimum_arc_length_m: float = 0.005
    maximum_arc_length_m: float = 0.08
    failed_step_reduction: float = 0.5
    load_factor_metric_scale_m: float = 0.002
    displacement_metric_weights: tuple[float, ...] | None = None
    residual_tolerance_kn: float = 1.0e-10
    tangent_solve_residual_tolerance_kn: float = 1.0e-10
    constraint_tolerance_m2: float = 1.0e-12
    maximum_corrector_iterations: int = 7
    maximum_attempt_count: int = 100


@dataclass(frozen=True)
class VectorArcLengthCheckpoint:
    schema_version: str
    case_id: str
    path_contract_hash: str
    step_index: int
    free_displacements_m: tuple[float, ...]
    load_factor: float
    previous_tangent_displacements: tuple[float, ...] | None
    previous_tangent_load_factor: float | None
    current_arc_length_m: float
    state_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_vector_arc_length_checkpoint(self)
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "step_index": self.step_index,
            "free_displacements_m": list(self.free_displacements_m),
            "load_factor": self.load_factor,
            "previous_tangent_displacements": (
                None
                if self.previous_tangent_displacements is None
                else list(self.previous_tangent_displacements)
            ),
            "previous_tangent_load_factor": (
                self.previous_tangent_load_factor
            ),
            "current_arc_length_m": self.current_arc_length_m,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class VectorArcLengthResult:
    status: str
    terminal_reason: str
    case_id: str
    path_contract_hash: str
    equilibrium_linearization_mode: str
    residual_formula: str
    load_linearization_formula: str
    config: VectorArcLengthConfig
    reference_load_kn: tuple[float, ...]
    displacement_metric_weights: tuple[float, ...]
    initial_checkpoint: VectorArcLengthCheckpoint
    final_checkpoint: VectorArcLengthCheckpoint
    checkpoints: tuple[VectorArcLengthCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": VECTOR_ARC_LENGTH_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "equilibrium_linearization_mode": (
                self.equilibrium_linearization_mode
            ),
            "residual_formula": self.residual_formula,
            "load_linearization_formula": self.load_linearization_formula,
            "constraint_formula": VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA,
            "config": {
                "target_monitor_dof_index": (
                    self.config.target_monitor_dof_index
                ),
                "target_monitor_displacement_m": (
                    self.config.target_monitor_displacement_m
                ),
                "target_direction": self.config.target_direction,
                "initial_arc_length_m": self.config.initial_arc_length_m,
                "minimum_arc_length_m": self.config.minimum_arc_length_m,
                "maximum_arc_length_m": self.config.maximum_arc_length_m,
                "failed_step_reduction": self.config.failed_step_reduction,
                "load_factor_metric_scale_m": (
                    self.config.load_factor_metric_scale_m
                ),
                "displacement_metric_weights": list(
                    self.displacement_metric_weights
                ),
                "residual_tolerance_kn": self.config.residual_tolerance_kn,
                "tangent_solve_residual_tolerance_kn": (
                    self.config.tangent_solve_residual_tolerance_kn
                ),
                "constraint_tolerance_m2": (
                    self.config.constraint_tolerance_m2
                ),
                "maximum_corrector_iterations": (
                    self.config.maximum_corrector_iterations
                ),
                "maximum_attempt_count": self.config.maximum_attempt_count,
            },
            "reference_load_kn": list(self.reference_load_kn),
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "metrics": self.metrics,
        }


def _finite(value: Any, *, path: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise VectorArcLengthContractError(f"{path} must be numeric") from exc
    if not math.isfinite(normalized):
        raise VectorArcLengthContractError(f"{path} must be finite")
    return normalized


def _finite_vector(
    values: Any,
    *,
    path: str,
    expected_dimension: int | None = None,
) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise VectorArcLengthContractError(
            f"{path} must be a finite one-dimensional vector"
        ) from exc
    if array.ndim != 1 or array.size < 1 or not np.all(np.isfinite(array)):
        raise VectorArcLengthContractError(
            f"{path} must be a finite non-empty one-dimensional vector"
        )
    if expected_dimension is not None and array.size != expected_dimension:
        raise VectorArcLengthContractError(
            f"{path} dimension does not match the equilibrium problem"
        )
    return np.array(array, dtype=float, copy=True)


def _finite_matrix(values: Any, *, path: str, dimension: int) -> np.ndarray:
    try:
        matrix = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise VectorArcLengthContractError(
            f"{path} must be a finite square matrix"
        ) from exc
    if matrix.shape != (dimension, dimension) or not np.all(np.isfinite(matrix)):
        raise VectorArcLengthContractError(
            f"{path} must be a finite {dimension}x{dimension} matrix"
        )
    return np.array(matrix, dtype=float, copy=True)


def _validate_hash(value: str, *, path: str) -> str:
    normalized = str(value)
    if (
        len(normalized) != 71
        or not normalized.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise VectorArcLengthContractError(f"{path} must be a sha256 digest")
    return normalized


def _resolve_metric_weights(
    config: VectorArcLengthConfig,
    *,
    dimension: int,
) -> np.ndarray:
    if config.displacement_metric_weights is None:
        return np.ones(dimension, dtype=float)
    weights = _finite_vector(
        config.displacement_metric_weights,
        path="displacement_metric_weights",
        expected_dimension=dimension,
    )
    if np.any(weights <= 0.0):
        raise VectorArcLengthContractError(
            "displacement_metric_weights must all be positive"
        )
    return weights


def _validate_config(config: VectorArcLengthConfig, *, dimension: int) -> np.ndarray:
    if (
        isinstance(config.target_monitor_dof_index, bool)
        or not isinstance(config.target_monitor_dof_index, int)
        or not 0 <= config.target_monitor_dof_index < dimension
    ):
        raise VectorArcLengthContractError(
            "target_monitor_dof_index is outside the displacement vector"
        )
    if isinstance(config.target_direction, bool) or config.target_direction not in (
        -1,
        1,
    ):
        raise VectorArcLengthContractError("target_direction must be -1 or 1")
    _finite(
        config.target_monitor_displacement_m,
        path="target_monitor_displacement_m",
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
        if _finite(value, path=name) <= 0.0:
            raise VectorArcLengthContractError(f"{name} must be positive")
    if config.minimum_arc_length_m > config.initial_arc_length_m:
        raise VectorArcLengthContractError(
            "minimum_arc_length_m cannot exceed initial_arc_length_m"
        )
    if config.initial_arc_length_m > config.maximum_arc_length_m:
        raise VectorArcLengthContractError(
            "initial_arc_length_m cannot exceed maximum_arc_length_m"
        )
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise VectorArcLengthContractError(
            "failed_step_reduction must be between zero and one"
        )
    if (
        isinstance(config.maximum_corrector_iterations, bool)
        or not isinstance(config.maximum_corrector_iterations, int)
        or config.maximum_corrector_iterations < 1
        or isinstance(config.maximum_attempt_count, bool)
        or not isinstance(config.maximum_attempt_count, int)
        or config.maximum_attempt_count < 1
    ):
        raise VectorArcLengthContractError(
            "iteration and attempt limits must be positive integers"
        )
    return _resolve_metric_weights(config, dimension=dimension)


def build_vector_arc_length_path_contract_hash(
    *,
    case_id: str,
    config: VectorArcLengthConfig,
    reference_load_kn: Any,
    displacement_metric_weights: Any,
    tangent_solver_profile: str | None = None,
    tangent_solver_contract_hash: str | None = None,
    tangent_solver_mode: str | None = None,
    equilibrium_linearization_mode: str = (
        VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
    ),
) -> str:
    """Bind a restart checkpoint to the numerical path contract."""

    normalized_case_id = str(case_id).strip()
    if not normalized_case_id:
        raise VectorArcLengthContractError("case_id is required")
    reference = _finite_vector(reference_load_kn, path="reference_load_kn")
    weights = _finite_vector(
        displacement_metric_weights,
        path="displacement_metric_weights",
        expected_dimension=reference.size,
    )
    if np.any(weights <= 0.0):
        raise VectorArcLengthContractError(
            "displacement_metric_weights must all be positive"
        )
    configured_weights = _validate_config(config, dimension=reference.size)
    if not np.array_equal(weights, configured_weights):
        raise VectorArcLengthContractError(
            "displacement_metric_weights do not match the solver configuration"
        )
    if (tangent_solver_profile is None) != (
        tangent_solver_contract_hash is None
    ):
        raise VectorArcLengthContractError(
            "external tangent solver profile and contract hash must both be present"
        )
    solver_profile = None
    solver_contract_hash = None
    solver_mode = None
    if tangent_solver_profile is not None:
        solver_profile = str(tangent_solver_profile).strip()
        if not solver_profile:
            raise VectorArcLengthContractError(
                "tangent_solver_profile must be non-empty"
            )
        assert tangent_solver_contract_hash is not None
        solver_contract_hash = _validate_hash(
            tangent_solver_contract_hash,
            path="tangent_solver_contract_hash",
        )
        solver_mode = str(
            tangent_solver_mode or VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE
        ).strip()
        if solver_mode not in {
            VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE,
            VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
        }:
            raise VectorArcLengthContractError(
                "tangent_solver_mode is unsupported"
            )
    elif tangent_solver_mode is not None:
        raise VectorArcLengthContractError(
            "tangent_solver_mode requires an external tangent solver"
        )
    normalized_equilibrium_mode = str(equilibrium_linearization_mode).strip()
    if normalized_equilibrium_mode not in {
        VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE,
        VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    }:
        raise VectorArcLengthContractError(
            "equilibrium_linearization_mode is unsupported"
        )
    digest = hashlib.sha256()
    digest.update(VECTOR_ARC_LENGTH_SCHEMA_VERSION.encode("ascii"))
    digest.update(VECTOR_ARC_LENGTH_RESIDUAL_FORMULA.encode("ascii"))
    digest.update(VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA.encode("ascii"))
    case_bytes = normalized_case_id.encode("utf-8")
    digest.update(struct.pack("<Q", len(case_bytes)))
    digest.update(case_bytes)
    digest.update(
        struct.pack(
            "<qqqq",
            config.target_monitor_dof_index,
            config.target_direction,
            config.maximum_corrector_iterations,
            config.maximum_attempt_count,
        )
    )
    for value in (
        config.target_monitor_displacement_m,
        config.initial_arc_length_m,
        config.minimum_arc_length_m,
        config.maximum_arc_length_m,
        config.failed_step_reduction,
        config.load_factor_metric_scale_m,
        config.residual_tolerance_kn,
        config.tangent_solve_residual_tolerance_kn,
        config.constraint_tolerance_m2,
    ):
        digest.update(struct.pack("<d", float(value)))
    digest.update(struct.pack("<Q", reference.size))
    for vector in (reference, weights):
        for value in vector:
            digest.update(struct.pack("<d", float(value)))
    if solver_profile is not None:
        assert solver_contract_hash is not None
        assert solver_mode is not None
        for value in (solver_profile, solver_contract_hash, solver_mode):
            encoded = value.encode("utf-8")
            digest.update(struct.pack("<Q", len(encoded)))
            digest.update(encoded)
    if (
        normalized_equilibrium_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
    ):
        for value in (
            normalized_equilibrium_mode,
            VECTOR_ARC_LENGTH_LOAD_COUPLED_RESIDUAL_FORMULA,
            VECTOR_ARC_LENGTH_LOAD_COUPLED_LINEARIZATION_FORMULA,
        ):
            encoded = value.encode("utf-8")
            digest.update(struct.pack("<Q", len(encoded)))
            digest.update(encoded)
    return f"sha256:{digest.hexdigest()}"


def _checkpoint_hash(
    *,
    case_id: str,
    path_contract_hash: str,
    step_index: int,
    free_displacements_m: tuple[float, ...],
    load_factor: float,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    current_arc_length_m: float,
) -> str:
    digest = hashlib.sha256()
    digest.update(VECTOR_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION.encode("ascii"))
    for value in (case_id, path_contract_hash):
        encoded = value.encode("utf-8")
        digest.update(struct.pack("<Q", len(encoded)))
        digest.update(encoded)
    digest.update(
        struct.pack(
            "<QddQ",
            step_index,
            load_factor,
            current_arc_length_m,
            len(free_displacements_m),
        )
    )
    for value in free_displacements_m:
        digest.update(struct.pack("<d", value))
    if previous_tangent_displacements is None:
        digest.update(b"\x00")
    else:
        digest.update(b"\x01")
        for value in previous_tangent_displacements:
            digest.update(struct.pack("<d", value))
        assert previous_tangent_load_factor is not None
        digest.update(struct.pack("<d", previous_tangent_load_factor))
    return f"sha256:{digest.hexdigest()}"


def create_vector_arc_length_checkpoint(
    *,
    case_id: str,
    path_contract_hash: str,
    step_index: int,
    free_displacements_m: Any,
    load_factor: float,
    previous_tangent_displacements: Any | None,
    previous_tangent_load_factor: float | None,
    current_arc_length_m: float,
) -> VectorArcLengthCheckpoint:
    normalized_case_id = str(case_id).strip()
    if not normalized_case_id:
        raise VectorArcLengthContractError("case_id is required")
    contract_hash = _validate_hash(
        path_contract_hash,
        path="path_contract_hash",
    )
    if (
        isinstance(step_index, bool)
        or not isinstance(step_index, int)
        or step_index < 0
    ):
        raise VectorArcLengthContractError(
            "step_index must be a non-negative integer"
        )
    displacements = _finite_vector(
        free_displacements_m,
        path="free_displacements_m",
    )
    normalized_load_factor = _finite(load_factor, path="load_factor")
    arc_length = _finite(current_arc_length_m, path="current_arc_length_m")
    if arc_length <= 0.0:
        raise VectorArcLengthContractError(
            "current_arc_length_m must be positive"
        )
    if previous_tangent_displacements is None:
        tangent_displacements = None
    else:
        tangent_array = _finite_vector(
            previous_tangent_displacements,
            path="previous_tangent_displacements",
            expected_dimension=displacements.size,
        )
        tangent_displacements = tuple(float(value) for value in tangent_array)
    tangent_load = (
        None
        if previous_tangent_load_factor is None
        else _finite(
            previous_tangent_load_factor,
            path="previous_tangent_load_factor",
        )
    )
    if (tangent_displacements is None) != (tangent_load is None):
        raise VectorArcLengthContractError(
            "previous displacement and load tangents must both be present or absent"
        )
    displacement_tuple = tuple(float(value) for value in displacements)
    state_hash = _checkpoint_hash(
        case_id=normalized_case_id,
        path_contract_hash=contract_hash,
        step_index=step_index,
        free_displacements_m=displacement_tuple,
        load_factor=normalized_load_factor,
        previous_tangent_displacements=tangent_displacements,
        previous_tangent_load_factor=tangent_load,
        current_arc_length_m=arc_length,
    )
    return VectorArcLengthCheckpoint(
        schema_version=VECTOR_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION,
        case_id=normalized_case_id,
        path_contract_hash=contract_hash,
        step_index=step_index,
        free_displacements_m=displacement_tuple,
        load_factor=normalized_load_factor,
        previous_tangent_displacements=tangent_displacements,
        previous_tangent_load_factor=tangent_load,
        current_arc_length_m=arc_length,
        state_hash=state_hash,
    )


def validate_vector_arc_length_checkpoint(
    checkpoint: VectorArcLengthCheckpoint,
    *,
    expected_case_id: str | None = None,
    expected_path_contract_hash: str | None = None,
    expected_dimension: int | None = None,
) -> VectorArcLengthCheckpoint:
    if not isinstance(checkpoint, VectorArcLengthCheckpoint):
        raise VectorArcLengthContractError("checkpoint type is invalid")
    if checkpoint.schema_version != VECTOR_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION:
        raise VectorArcLengthContractError("checkpoint schema_version is invalid")
    if expected_case_id is not None and checkpoint.case_id != expected_case_id:
        raise VectorArcLengthContractError(
            "checkpoint case_id does not match the problem"
        )
    if (
        expected_path_contract_hash is not None
        and checkpoint.path_contract_hash != expected_path_contract_hash
    ):
        raise VectorArcLengthContractError(
            "checkpoint path contract does not match the solver configuration"
        )
    if (
        expected_dimension is not None
        and len(checkpoint.free_displacements_m) != expected_dimension
    ):
        raise VectorArcLengthContractError(
            "checkpoint displacement dimension does not match the problem"
        )
    expected = create_vector_arc_length_checkpoint(
        case_id=checkpoint.case_id,
        path_contract_hash=checkpoint.path_contract_hash,
        step_index=checkpoint.step_index,
        free_displacements_m=checkpoint.free_displacements_m,
        load_factor=checkpoint.load_factor,
        previous_tangent_displacements=(
            checkpoint.previous_tangent_displacements
        ),
        previous_tangent_load_factor=checkpoint.previous_tangent_load_factor,
        current_arc_length_m=checkpoint.current_arc_length_m,
    )
    if checkpoint.state_hash != expected.state_hash:
        raise VectorArcLengthContractError("checkpoint state_hash mismatch")
    return checkpoint


def _problem_tangent(
    problem: VectorArcLengthEquilibriumProblem,
    displacements_m: np.ndarray,
) -> np.ndarray:
    tangent = getattr(problem, "consistent_tangent_kn_per_m", None)
    if not callable(tangent):
        raise VectorArcLengthContractError(
            "matrix tangent path requires consistent_tangent_kn_per_m"
        )
    return _finite_matrix(
        tangent(
            np.array(displacements_m, dtype=float, copy=True)
        ),
        path="consistent_tangent_kn_per_m",
        dimension=displacements_m.size,
    )


def _resolve_equilibrium_linearization_mode(problem: Any) -> str:
    coupled_method_names = (
        "residual_kn",
        "negative_load_derivative_kn",
        "consistent_state_tangent_action_kn_per_m",
    )
    coupled_methods_present = tuple(
        callable(getattr(problem, name, None)) for name in coupled_method_names
    )
    if any(coupled_methods_present) and not all(coupled_methods_present):
        missing = [
            name
            for name, present in zip(
                coupled_method_names,
                coupled_methods_present,
                strict=True,
            )
            if not present
        ]
        raise VectorArcLengthContractError(
            "load-coupled equilibrium contract is incomplete: "
            + ", ".join(missing)
        )
    return (
        VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        if all(coupled_methods_present)
        else VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
    )


def _problem_tangent_action(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    displacements_m: np.ndarray,
    load_factor: float,
    direction_m: np.ndarray,
    *,
    equilibrium_linearization_mode: str,
) -> np.ndarray:
    action_name = (
        "consistent_state_tangent_action_kn_per_m"
        if equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        else "consistent_tangent_action_kn_per_m"
    )
    action = getattr(problem, action_name, None)
    if not callable(action):
        raise VectorArcLengthContractError(
            f"state tangent problem must expose {action_name}"
        )
    arguments = (
        (
            np.array(displacements_m, dtype=float, copy=True),
            load_factor,
            np.array(direction_m, dtype=float, copy=True),
        )
        if equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        else (
            np.array(displacements_m, dtype=float, copy=True),
            np.array(direction_m, dtype=float, copy=True),
        )
    )
    return _finite_vector(
        action(*arguments),
        path=action_name,
        expected_dimension=displacements_m.size,
    )


def _problem_residual(
    problem: (
        VectorArcLengthEquilibriumProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    displacements_m: np.ndarray,
    load_factor: float,
    reference_load_kn: np.ndarray,
    *,
    equilibrium_linearization_mode: str,
) -> np.ndarray:
    if (
        equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
    ):
        residual = getattr(problem, "residual_kn", None)
        if not callable(residual):
            raise VectorArcLengthContractError(
                "load-coupled problem must expose residual_kn"
            )
        return _finite_vector(
            residual(
                np.array(displacements_m, dtype=float, copy=True),
                load_factor,
            ),
            path="residual_kn",
            expected_dimension=displacements_m.size,
        )
    internal = _finite_vector(
        problem.internal_force_kn(
            np.array(displacements_m, dtype=float, copy=True)
        ),
        path="internal_force_kn",
        expected_dimension=displacements_m.size,
    )
    return internal - load_factor * reference_load_kn


def _problem_load_linearization_rhs(
    problem: (
        VectorArcLengthEquilibriumProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    displacements_m: np.ndarray,
    load_factor: float,
    reference_load_kn: np.ndarray,
    *,
    equilibrium_linearization_mode: str,
) -> np.ndarray:
    if (
        equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
    ):
        return np.array(reference_load_kn, dtype=float, copy=True)
    derivative = getattr(problem, "negative_load_derivative_kn", None)
    if not callable(derivative):
        raise VectorArcLengthContractError(
            "load-coupled problem must expose negative_load_derivative_kn"
        )
    return _finite_vector(
        derivative(
            np.array(displacements_m, dtype=float, copy=True),
            load_factor,
        ),
        path="negative_load_derivative_kn",
        expected_dimension=displacements_m.size,
    )


def _validate_external_tangent_result(
    result: VectorArcLengthTangentSolve,
    *,
    solver_profile: str,
    solver_contract_hash: str,
    right_hand_side_kn: np.ndarray,
    tangent_action_kn: np.ndarray,
    explicit_residual_tolerance_kn: float,
    operator_mode: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    if type(result) is not VectorArcLengthTangentSolve:
        raise VectorArcLengthContractError(
            "external tangent solver returned an invalid result type"
        )
    if result.profile != solver_profile:
        raise VectorArcLengthContractError(
            "external tangent solve profile does not match its solver"
        )
    if result.contract_hash != solver_contract_hash:
        raise VectorArcLengthContractError(
            "external tangent solve contract hash does not match its solver"
        )
    _validate_hash(result.contract_hash, path="external_tangent_contract_hash")
    if result.contract_pass is not True:
        raise VectorArcLengthContractError(
            "external tangent solve failed: " + str(result.terminal_reason)
        )
    solution = _finite_vector(
        result.solution_free,
        path="external_tangent_solution_free",
        expected_dimension=right_hand_side_kn.size,
    )
    linear_residual = tangent_action_kn - right_hand_side_kn
    linear_residual_inf = float(np.linalg.norm(linear_residual, ord=np.inf))
    if not math.isfinite(linear_residual_inf):
        raise VectorArcLengthContractError(
            "external tangent solve produced a non-finite explicit residual"
        )
    if linear_residual_inf > explicit_residual_tolerance_kn:
        raise VectorArcLengthContractError(
            "external tangent solve failed the explicit residual gate"
        )
    if not isinstance(result.receipt, dict):
        raise VectorArcLengthContractError(
            "external tangent solve receipt must be an object"
        )
    receipt = dict(result.receipt)
    return solution, {
        "profile": result.profile,
        "contract_hash": result.contract_hash,
        "operator_mode": operator_mode,
        "terminal_reason": result.terminal_reason,
        "explicit_residual_inf_norm_kn": linear_residual_inf,
        "explicit_residual_tolerance_kn": explicit_residual_tolerance_kn,
        "receipt": receipt,
    }


def _external_tangent_solve(
    solver: VectorArcLengthTangentSolver,
    tangent_kn_per_m: np.ndarray,
    right_hand_side_kn: np.ndarray,
    *,
    solve_id: str,
    explicit_residual_tolerance_kn: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = solver.solve(
        np.array(tangent_kn_per_m, dtype=float, copy=True),
        np.array(right_hand_side_kn, dtype=float, copy=True),
        solve_id=solve_id,
    )
    if type(result) is not VectorArcLengthTangentSolve:
        raise VectorArcLengthContractError(
            "external tangent solver returned an invalid result type"
        )
    solution = _finite_vector(
        result.solution_free,
        path="external_tangent_solution_free",
        expected_dimension=right_hand_side_kn.size,
    )
    return _validate_external_tangent_result(
        result,
        solver_profile=solver.profile,
        solver_contract_hash=solver.contract_hash,
        right_hand_side_kn=right_hand_side_kn,
        tangent_action_kn=tangent_kn_per_m @ solution,
        explicit_residual_tolerance_kn=explicit_residual_tolerance_kn,
        operator_mode=VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE,
    )


def _external_state_tangent_solve(
    solver: VectorArcLengthStateTangentSolver,
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    displacements_m: np.ndarray,
    load_factor: float,
    right_hand_side_kn: np.ndarray,
    *,
    solve_id: str,
    explicit_residual_tolerance_kn: float,
    equilibrium_linearization_mode: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = solver.solve_at_state(
        problem,
        np.array(displacements_m, dtype=float, copy=True),
        np.array(right_hand_side_kn, dtype=float, copy=True),
        load_factor=load_factor,
        solve_id=solve_id,
    )
    if type(result) is not VectorArcLengthTangentSolve:
        raise VectorArcLengthContractError(
            "external tangent solver returned an invalid result type"
        )
    solution = _finite_vector(
        result.solution_free,
        path="external_tangent_solution_free",
        expected_dimension=right_hand_side_kn.size,
    )
    tangent_action = _problem_tangent_action(
        problem,
        displacements_m,
        load_factor,
        solution,
        equilibrium_linearization_mode=equilibrium_linearization_mode,
    )
    return _validate_external_tangent_result(
        result,
        solver_profile=solver.profile,
        solver_contract_hash=solver.contract_hash,
        right_hand_side_kn=right_hand_side_kn,
        tangent_action_kn=tangent_action,
        explicit_residual_tolerance_kn=explicit_residual_tolerance_kn,
        operator_mode=VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    )


def _predictor_tangent(
    problem: (
        VectorArcLengthEquilibriumProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    checkpoint: VectorArcLengthCheckpoint,
    *,
    reference_load_kn: np.ndarray,
    metric_weights: np.ndarray,
    load_factor_metric_scale_m: float,
    tangent_solver: VectorArcLengthTangentSolver | None,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None,
    tangent_solve_residual_tolerance_kn: float,
    equilibrium_linearization_mode: str,
    solve_id: str,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    displacements = np.asarray(checkpoint.free_displacements_m, dtype=float)
    load_linearization_rhs = _problem_load_linearization_rhs(
        problem,
        displacements,
        checkpoint.load_factor,
        reference_load_kn,
        equilibrium_linearization_mode=equilibrium_linearization_mode,
    )
    tangent = None
    tangent_solve_metadata = None
    if state_tangent_solver is not None:
        displacement_per_load_factor, tangent_solve_metadata = (
            _external_state_tangent_solve(
                state_tangent_solver,
                problem,
                displacements,
                checkpoint.load_factor,
                load_linearization_rhs,
                solve_id=solve_id,
                explicit_residual_tolerance_kn=(
                    tangent_solve_residual_tolerance_kn
                ),
                equilibrium_linearization_mode=(
                    equilibrium_linearization_mode
                ),
            )
        )
    else:
        tangent = _problem_tangent(problem, displacements)
    if tangent_solver is None and state_tangent_solver is None:
        assert tangent is not None
        try:
            displacement_per_load_factor = np.linalg.solve(
                tangent,
                load_linearization_rhs,
            )
        except np.linalg.LinAlgError as exc:
            raise VectorArcLengthContractError(
                "predictor consistent tangent is singular"
            ) from exc
    elif tangent_solver is not None:
        assert tangent is not None
        displacement_per_load_factor, tangent_solve_metadata = (
            _external_tangent_solve(
                tangent_solver,
                tangent,
                load_linearization_rhs,
                solve_id=solve_id,
                explicit_residual_tolerance_kn=(
                    tangent_solve_residual_tolerance_kn
                ),
            )
        )
    if not np.all(np.isfinite(displacement_per_load_factor)):
        raise VectorArcLengthContractError(
            "predictor displacement tangent is non-finite"
        )
    load_tangent = 1.0
    norm = math.sqrt(
        float(
            np.dot(
                metric_weights * displacement_per_load_factor,
                displacement_per_load_factor,
            )
        )
        + (load_factor_metric_scale_m * load_tangent) ** 2
    )
    displacement_tangent = displacement_per_load_factor / norm
    load_tangent /= norm
    orientation_dot = None
    if checkpoint.previous_tangent_displacements is not None:
        assert checkpoint.previous_tangent_load_factor is not None
        previous_displacement = np.asarray(
            checkpoint.previous_tangent_displacements,
            dtype=float,
        )
        orientation_dot = float(
            np.dot(
                metric_weights * previous_displacement,
                displacement_tangent,
            )
            + load_factor_metric_scale_m**2
            * checkpoint.previous_tangent_load_factor
            * load_tangent
        )
        if orientation_dot < 0.0:
            displacement_tangent = -displacement_tangent
            load_tangent = -load_tangent
    tangent_condition = (
        None if tangent is None else float(np.linalg.cond(tangent))
    )
    return (
        displacement_tangent,
        load_tangent,
        {
            "consistent_tangent_condition_number": (
                tangent_condition
                if tangent_condition is not None
                and math.isfinite(tangent_condition)
                else None
            ),
            "predictor_orientation_dot": orientation_dot,
            "predictor_tangent_solve": tangent_solve_metadata,
            "load_linearization_rhs_kind": (
                equilibrium_linearization_mode
            ),
        },
    )


def _correct_trial(
    problem: (
        VectorArcLengthEquilibriumProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    *,
    accepted: VectorArcLengthCheckpoint,
    predictor_displacements_m: np.ndarray,
    predictor_load_factor: float,
    reference_load_kn: np.ndarray,
    metric_weights: np.ndarray,
    arc_length_m: float,
    config: VectorArcLengthConfig,
    tangent_solver: VectorArcLengthTangentSolver | None,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None,
    equilibrium_linearization_mode: str,
    solve_id_prefix: str,
) -> dict[str, Any]:
    accepted_displacements = np.asarray(
        accepted.free_displacements_m,
        dtype=float,
    )
    trial_displacements = accepted_displacements + predictor_displacements_m
    trial_load_factor = accepted.load_factor + predictor_load_factor
    history: list[dict[str, Any]] = []
    converged = False
    stop_reason = "maximum_corrector_iterations_exhausted"
    residual = np.full(accepted_displacements.size, math.inf)
    residual_norm = math.inf
    constraint_residual = math.inf

    for iteration in range(1, config.maximum_corrector_iterations + 1):
        residual = _problem_residual(
            problem,
            trial_displacements,
            trial_load_factor,
            reference_load_kn,
            equilibrium_linearization_mode=equilibrium_linearization_mode,
        )
        load_linearization_rhs = _problem_load_linearization_rhs(
            problem,
            trial_displacements,
            trial_load_factor,
            reference_load_kn,
            equilibrium_linearization_mode=equilibrium_linearization_mode,
        )
        residual_norm = float(np.linalg.norm(residual, ord=np.inf))
        delta_displacements = trial_displacements - accepted_displacements
        delta_load_factor = trial_load_factor - accepted.load_factor
        constraint_residual = float(
            np.dot(
                metric_weights * delta_displacements,
                delta_displacements,
            )
            + (
                config.load_factor_metric_scale_m * delta_load_factor
            )
            ** 2
            - arc_length_m**2
        )
        row: dict[str, Any] = {
            "iteration": iteration,
            "trial_free_displacements_m": trial_displacements.tolist(),
            "trial_load_factor": trial_load_factor,
            "residual_kn": residual.tolist(),
            "residual_inf_norm_kn": residual_norm,
            "constraint_residual_m2": constraint_residual,
        }
        if (
            residual_norm <= config.residual_tolerance_kn
            and abs(constraint_residual) <= config.constraint_tolerance_m2
        ):
            row.update(
                {
                    "converged": True,
                    "correction_free_displacements_m": [
                        0.0 for _ in trial_displacements
                    ],
                    "correction_load_factor": 0.0,
                }
            )
            history.append(row)
            converged = True
            stop_reason = "equilibrium_and_arc_constraint_converged"
            break

        constraint_displacements = 2.0 * metric_weights * delta_displacements
        constraint_load_factor = (
            2.0
            * config.load_factor_metric_scale_m**2
            * delta_load_factor
        )
        tangent = None
        augmented = None
        augmented_condition = None
        if state_tangent_solver is None:
            tangent = _problem_tangent(problem, trial_displacements)
            augmented = np.empty(
                (trial_displacements.size + 1, trial_displacements.size + 1),
                dtype=float,
            )
            augmented[:-1, :-1] = tangent
            augmented[:-1, -1] = -load_linearization_rhs
            augmented[-1, :-1] = constraint_displacements
            augmented[-1, -1] = constraint_load_factor
            augmented_condition_value = float(np.linalg.cond(augmented))
            augmented_condition = (
                augmented_condition_value
                if math.isfinite(augmented_condition_value)
                else None
            )
        tangent_solve_metadata = None
        try:
            if tangent_solver is None and state_tangent_solver is None:
                assert augmented is not None
                right_hand_side = -np.concatenate(
                    (residual, np.asarray([constraint_residual], dtype=float))
                )
                correction = np.linalg.solve(augmented, right_hand_side)
            else:
                if state_tangent_solver is not None:
                    residual_direction, residual_solve = (
                        _external_state_tangent_solve(
                            state_tangent_solver,
                            problem,
                            trial_displacements,
                            trial_load_factor,
                            -residual,
                            solve_id=(
                                f"{solve_id_prefix}-iteration-{iteration}-residual"
                            ),
                            explicit_residual_tolerance_kn=(
                                config.tangent_solve_residual_tolerance_kn
                            ),
                            equilibrium_linearization_mode=(
                                equilibrium_linearization_mode
                            ),
                        )
                    )
                    load_direction, load_solve = (
                        _external_state_tangent_solve(
                            state_tangent_solver,
                            problem,
                            trial_displacements,
                            trial_load_factor,
                            load_linearization_rhs,
                            solve_id=(
                                f"{solve_id_prefix}-iteration-{iteration}-"
                                + (
                                    "load-linearization"
                                    if equilibrium_linearization_mode
                                    == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
                                    else "reference-load"
                                )
                            ),
                            explicit_residual_tolerance_kn=(
                                config.tangent_solve_residual_tolerance_kn
                            ),
                            equilibrium_linearization_mode=(
                                equilibrium_linearization_mode
                            ),
                        )
                    )
                else:
                    assert tangent_solver is not None
                    assert tangent is not None
                    residual_direction, residual_solve = _external_tangent_solve(
                        tangent_solver,
                        tangent,
                        -residual,
                        solve_id=(
                            f"{solve_id_prefix}-iteration-{iteration}-residual"
                        ),
                        explicit_residual_tolerance_kn=(
                            config.tangent_solve_residual_tolerance_kn
                        ),
                    )
                    load_direction, load_solve = _external_tangent_solve(
                        tangent_solver,
                        tangent,
                        load_linearization_rhs,
                        solve_id=(
                            f"{solve_id_prefix}-iteration-{iteration}-"
                            "reference-load"
                        ),
                        explicit_residual_tolerance_kn=(
                            config.tangent_solve_residual_tolerance_kn
                        ),
                    )
                schur_denominator = float(
                    np.dot(constraint_displacements, load_direction)
                    + constraint_load_factor
                )
                schur_scale = max(
                    abs(float(np.dot(constraint_displacements, load_direction))),
                    abs(constraint_load_factor),
                    1.0,
                )
                if abs(schur_denominator) <= np.finfo(float).eps * schur_scale:
                    raise VectorArcLengthContractError(
                        "external tangent Schur denominator is singular"
                    )
                correction_load_factor = float(
                    (
                        -constraint_residual
                        - np.dot(constraint_displacements, residual_direction)
                    )
                    / schur_denominator
                )
                correction_displacements = (
                    residual_direction
                    + load_direction * correction_load_factor
                )
                correction = np.concatenate(
                    (
                        correction_displacements,
                        np.asarray([correction_load_factor], dtype=float),
                    )
                )
                tangent_solve_metadata = {
                    "schur_denominator": schur_denominator,
                    "residual_solve": residual_solve,
                    "load_linearization_rhs_kind": (
                        equilibrium_linearization_mode
                    ),
                }
                tangent_solve_metadata[
                    (
                        "load_linearization_solve"
                        if equilibrium_linearization_mode
                        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
                        else "reference_load_solve"
                    )
                ] = load_solve
        except (np.linalg.LinAlgError, VectorArcLengthContractError) as exc:
            row.update(
                {
                    "converged": False,
                    "augmented_condition_number": augmented_condition,
                    "tangent_solve_metadata": tangent_solve_metadata,
                    "correction_free_displacements_m": [
                        0.0 for _ in trial_displacements
                    ],
                    "correction_load_factor": 0.0,
                }
            )
            history.append(row)
            stop_reason = (
                "augmented_newton_singular"
                if tangent_solver is None and state_tangent_solver is None
                else "external_tangent_solve_failed:" + str(exc)
            )
            break
        if not np.all(np.isfinite(correction)):
            row.update(
                {
                    "converged": False,
                    "augmented_condition_number": augmented_condition,
                    "tangent_solve_metadata": tangent_solve_metadata,
                    "correction_free_displacements_m": [
                        0.0 for _ in trial_displacements
                    ],
                    "correction_load_factor": 0.0,
                }
            )
            history.append(row)
            stop_reason = "non_finite_corrector_increment"
            break
        correction_displacements = correction[:-1]
        correction_load_factor = float(correction[-1])
        row.update(
            {
                "converged": False,
                "augmented_condition_number": augmented_condition,
                "tangent_solve_metadata": tangent_solve_metadata,
                "correction_free_displacements_m": (
                    correction_displacements.tolist()
                ),
                "correction_load_factor": correction_load_factor,
            }
        )
        history.append(row)
        trial_displacements = trial_displacements + correction_displacements
        trial_load_factor += correction_load_factor
        if (
            not np.all(np.isfinite(trial_displacements))
            or not math.isfinite(trial_load_factor)
        ):
            stop_reason = "non_finite_corrector_state"
            break

    return {
        "converged": converged,
        "stop_reason": stop_reason,
        "trial_free_displacements_m": trial_displacements.tolist(),
        "trial_load_factor": trial_load_factor,
        "residual_kn": residual.tolist(),
        "residual_inf_norm_kn": residual_norm,
        "constraint_residual_m2": constraint_residual,
        "corrector_iteration_count": len(history),
        "corrector_history": history,
    }


def _target_reached(
    checkpoint: VectorArcLengthCheckpoint,
    config: VectorArcLengthConfig,
) -> bool:
    monitored = checkpoint.free_displacements_m[
        config.target_monitor_dof_index
    ]
    return (
        config.target_direction
        * (monitored - config.target_monitor_displacement_m)
        >= 0.0
    )


def vector_arc_length_continuation(
    problem: (
        VectorArcLengthEquilibriumProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    *,
    config: VectorArcLengthConfig | None = None,
    resume_from: VectorArcLengthCheckpoint | None = None,
    tangent_solver: VectorArcLengthTangentSolver | None = None,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None = None,
) -> VectorArcLengthResult:
    """Follow a proportional or load-coupled multi-DOF equilibrium path."""

    cfg = config or VectorArcLengthConfig()
    case_id = str(problem.case_id).strip()
    if not case_id:
        raise VectorArcLengthContractError("problem.case_id is required")
    initial_displacements = _finite_vector(
        problem.initial_free_displacements_m(),
        path="initial_free_displacements_m",
    )
    dimension = initial_displacements.size
    metric_weights = _validate_config(cfg, dimension=dimension)
    equilibrium_linearization_mode = (
        _resolve_equilibrium_linearization_mode(problem)
    )
    if tangent_solver is not None and state_tangent_solver is not None:
        raise VectorArcLengthContractError(
            "matrix and state tangent solvers are mutually exclusive"
        )
    if (
        equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        and state_tangent_solver is None
    ):
        raise VectorArcLengthContractError(
            "load-coupled equilibrium requires a state tangent solver"
        )
    external_tangent_solver = (
        tangent_solver if tangent_solver is not None else state_tangent_solver
    )
    if external_tangent_solver is None:
        tangent_solver_profile = VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_PROFILE
        tangent_solver_contract_hash = None
        tangent_solver_mode = VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_MODE
    else:
        tangent_solver_profile = str(external_tangent_solver.profile).strip()
        if not tangent_solver_profile:
            raise VectorArcLengthContractError(
                "external tangent solver profile must be non-empty"
            )
        tangent_solver_contract_hash = _validate_hash(
            external_tangent_solver.contract_hash,
            path="external_tangent_solver_contract_hash",
        )
        tangent_solver_mode = (
            VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE
            if state_tangent_solver is not None
            else VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE
        )
    reference_load = _finite_vector(
        problem.reference_load_kn(),
        path="reference_load_kn",
        expected_dimension=dimension,
    )
    if float(np.linalg.norm(reference_load, ord=np.inf)) <= 0.0:
        raise VectorArcLengthContractError("reference_load_kn must be non-zero")
    initial_load_factor = _finite(
        problem.initial_load_factor(),
        path="initial_load_factor",
    )
    path_contract_hash = build_vector_arc_length_path_contract_hash(
        case_id=case_id,
        config=cfg,
        reference_load_kn=reference_load,
        displacement_metric_weights=metric_weights,
        tangent_solver_profile=(
            None
            if external_tangent_solver is None
            else tangent_solver_profile
        ),
        tangent_solver_contract_hash=tangent_solver_contract_hash,
        tangent_solver_mode=(
            None if external_tangent_solver is None else tangent_solver_mode
        ),
        equilibrium_linearization_mode=equilibrium_linearization_mode,
    )
    if resume_from is None:
        initial_residual = _problem_residual(
            problem,
            initial_displacements,
            initial_load_factor,
            reference_load,
            equilibrium_linearization_mode=(
                equilibrium_linearization_mode
            ),
        )
        if (
            float(np.linalg.norm(initial_residual, ord=np.inf))
            > cfg.residual_tolerance_kn
        ):
            raise VectorArcLengthContractError(
                "initial state does not satisfy the equilibrium tolerance"
            )
        accepted = create_vector_arc_length_checkpoint(
            case_id=case_id,
            path_contract_hash=path_contract_hash,
            step_index=0,
            free_displacements_m=initial_displacements,
            load_factor=initial_load_factor,
            previous_tangent_displacements=None,
            previous_tangent_load_factor=None,
            current_arc_length_m=cfg.initial_arc_length_m,
        )
    else:
        accepted = validate_vector_arc_length_checkpoint(
            resume_from,
            expected_case_id=case_id,
            expected_path_contract_hash=path_contract_hash,
            expected_dimension=dimension,
        )
    if _target_reached(accepted, cfg):
        raise VectorArcLengthContractError(
            "checkpoint monitor displacement already reached the target"
        )

    initial_checkpoint = accepted
    checkpoints = [accepted]
    attempts: list[dict[str, Any]] = []
    arc_length_m = min(
        accepted.current_arc_length_m,
        cfg.maximum_arc_length_m,
    )
    terminal_reason = "maximum_attempt_count_exhausted"

    for attempt_index in range(1, cfg.maximum_attempt_count + 1):
        if _target_reached(accepted, cfg):
            terminal_reason = "target_monitor_displacement_reached"
            break
        accepted_before = accepted
        try:
            (
                displacement_tangent,
                load_tangent,
                predictor_metadata,
            ) = _predictor_tangent(
                problem,
                accepted_before,
                reference_load_kn=reference_load,
                metric_weights=metric_weights,
                load_factor_metric_scale_m=(
                    cfg.load_factor_metric_scale_m
                ),
                tangent_solver=tangent_solver,
                state_tangent_solver=state_tangent_solver,
                tangent_solve_residual_tolerance_kn=(
                    cfg.tangent_solve_residual_tolerance_kn
                ),
                equilibrium_linearization_mode=(
                    equilibrium_linearization_mode
                ),
                solve_id=(
                    f"step-{accepted_before.step_index + 1}-"
                    f"attempt-{attempt_index}-predictor"
                ),
            )
        except VectorArcLengthContractError as exc:
            next_arc_length = arc_length_m * cfg.failed_step_reduction
            attempt = {
                "attempt_index": attempt_index,
                "accepted_step_index_before": accepted_before.step_index,
                "accepted_state_hash_before": accepted_before.state_hash,
                "arc_length_m": arc_length_m,
                "accepted": False,
                "converged": False,
                "stop_reason": str(exc),
                "rollback_exact": True,
                "accepted_state_hash_after": accepted_before.state_hash,
                "accepted_step_index_after": accepted_before.step_index,
                "next_arc_length_m": next_arc_length,
                "regularization_used": False,
                "fallback_used": False,
            }
            attempts.append(attempt)
            if next_arc_length < cfg.minimum_arc_length_m:
                terminal_reason = "minimum_arc_length_exhausted"
                break
            arc_length_m = next_arc_length
            continue
        predictor_displacements = arc_length_m * displacement_tangent
        predictor_load_factor = arc_length_m * load_tangent
        trial = _correct_trial(
            problem,
            accepted=accepted_before,
            predictor_displacements_m=predictor_displacements,
            predictor_load_factor=predictor_load_factor,
            reference_load_kn=reference_load,
            metric_weights=metric_weights,
            arc_length_m=arc_length_m,
            config=cfg,
            tangent_solver=tangent_solver,
            state_tangent_solver=state_tangent_solver,
            equilibrium_linearization_mode=(
                equilibrium_linearization_mode
            ),
            solve_id_prefix=(
                f"step-{accepted_before.step_index + 1}-attempt-{attempt_index}"
            ),
        )
        attempt = {
            "attempt_index": attempt_index,
            "accepted_step_index_before": accepted_before.step_index,
            "accepted_state_hash_before": accepted_before.state_hash,
            "accepted_free_displacements_m_before": list(
                accepted_before.free_displacements_m
            ),
            "accepted_load_factor_before": accepted_before.load_factor,
            "arc_length_m": arc_length_m,
            "tangent_linear_solver_profile": tangent_solver_profile,
            "tangent_linear_solver_mode": tangent_solver_mode,
            "equilibrium_linearization_mode": (
                equilibrium_linearization_mode
            ),
            "predictor_tangent_displacements": displacement_tangent.tolist(),
            "predictor_tangent_load_factor": load_tangent,
            "predictor_free_displacements_m": (
                predictor_displacements.tolist()
            ),
            "predictor_load_factor": predictor_load_factor,
            **predictor_metadata,
            **trial,
            "regularization_used": False,
            "fallback_used": False,
        }
        if trial["converged"] is True:
            trial_displacements = np.asarray(
                trial["trial_free_displacements_m"],
                dtype=float,
            )
            delta_displacements = trial_displacements - np.asarray(
                accepted_before.free_displacements_m,
                dtype=float,
            )
            delta_load_factor = (
                float(trial["trial_load_factor"])
                - accepted_before.load_factor
            )
            accepted = create_vector_arc_length_checkpoint(
                case_id=case_id,
                path_contract_hash=path_contract_hash,
                step_index=accepted_before.step_index + 1,
                free_displacements_m=trial_displacements,
                load_factor=float(trial["trial_load_factor"]),
                previous_tangent_displacements=(
                    delta_displacements / arc_length_m
                ),
                previous_tangent_load_factor=(
                    delta_load_factor / arc_length_m
                ),
                current_arc_length_m=arc_length_m,
            )
            checkpoints.append(accepted)
            attempt.update(
                {
                    "accepted": True,
                    "rollback_exact": True,
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_step_index_after": accepted.step_index,
                    "accepted_free_displacements_m_after": list(
                        accepted.free_displacements_m
                    ),
                    "accepted_load_factor_after": accepted.load_factor,
                }
            )
        else:
            next_arc_length = arc_length_m * cfg.failed_step_reduction
            attempt.update(
                {
                    "accepted": False,
                    "rollback_exact": (
                        accepted.state_hash == accepted_before.state_hash
                    ),
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_step_index_after": accepted.step_index,
                    "accepted_free_displacements_m_after": list(
                        accepted.free_displacements_m
                    ),
                    "accepted_load_factor_after": accepted.load_factor,
                    "next_arc_length_m": next_arc_length,
                }
            )
            if next_arc_length < cfg.minimum_arc_length_m:
                attempts.append(attempt)
                terminal_reason = "minimum_arc_length_exhausted"
                break
            arc_length_m = next_arc_length
        attempts.append(attempt)
    else:
        if _target_reached(accepted, cfg):
            terminal_reason = "target_monitor_displacement_reached"

    accepted_attempts = [row for row in attempts if row["accepted"] is True]
    rejected_attempts = [row for row in attempts if row["accepted"] is False]
    displacement_rows = [
        np.asarray(row.free_displacements_m, dtype=float)
        for row in checkpoints
    ]
    monitored_displacements = [
        float(row[cfg.target_monitor_dof_index])
        for row in displacement_rows
    ]
    load_factors = [row.load_factor for row in checkpoints]
    residual_errors = [
        float(
            np.linalg.norm(
                _problem_residual(
                    problem,
                    row,
                    checkpoint.load_factor,
                    reference_load,
                    equilibrium_linearization_mode=(
                        equilibrium_linearization_mode
                    ),
                ),
                ord=np.inf,
            )
        )
        for row, checkpoint in zip(displacement_rows, checkpoints)
    ]
    constraint_errors = [
        abs(float(row["constraint_residual_m2"]))
        for row in accepted_attempts
    ]
    load_differences = [
        right - left
        for left, right in zip(load_factors, load_factors[1:])
    ]
    minimum_load_index = min(
        range(len(load_factors)),
        key=load_factors.__getitem__,
    )
    monitor_monotonic = all(
        cfg.target_direction * (right - left) > 0.0
        for left, right in zip(
            monitored_displacements,
            monitored_displacements[1:],
        )
    )
    target_reached = _target_reached(accepted, cfg)
    rollback_exact = all(
        row["rollback_exact"] is True for row in attempts
    )
    gates_pass = bool(
        target_reached
        and accepted_attempts
        and rollback_exact
        and max(residual_errors, default=math.inf)
        <= cfg.residual_tolerance_kn
        and max(constraint_errors, default=math.inf)
        <= cfg.constraint_tolerance_m2
    )
    augmented_conditions = [
        float(history_row["augmented_condition_number"])
        for attempt in attempts
        for history_row in attempt.get("corrector_history", [])
        if history_row.get("augmented_condition_number") is not None
    ]
    external_tangent_solve_rows = [
        solve_metadata
        for attempt in attempts
        for solve_metadata in (
            [attempt.get("predictor_tangent_solve")]
            + [
                metadata
                for history_row in attempt.get("corrector_history", [])
                for metadata in (
                    (
                        history_row.get("tangent_solve_metadata") or {}
                    ).get("residual_solve"),
                    (
                        history_row.get("tangent_solve_metadata") or {}
                    ).get("reference_load_solve"),
                    (
                        history_row.get("tangent_solve_metadata") or {}
                    ).get("load_linearization_solve"),
                )
            ]
        )
        if solve_metadata is not None
    ]
    metrics = {
        "contract_pass": gates_pass,
        "equation_count": dimension,
        "target_monitor_displacement_reached": target_reached,
        "accepted_step_count": len(accepted_attempts),
        "rejected_step_count": len(rejected_attempts),
        "rollback_exact": rollback_exact,
        "fallback_count": 0,
        "regularization_count": 0,
        "tangent_linear_solver_profile": tangent_solver_profile,
        "tangent_linear_solver_mode": tangent_solver_mode,
        "equilibrium_linearization_mode": (
            equilibrium_linearization_mode
        ),
        "external_tangent_solver_contract_hash": (
            tangent_solver_contract_hash
        ),
        "tangent_solve_residual_tolerance_kn": (
            cfg.tangent_solve_residual_tolerance_kn
        ),
        "external_tangent_solve_count": len(external_tangent_solve_rows),
        "maximum_external_tangent_explicit_residual_inf_norm_kn": max(
            (
                float(row["explicit_residual_inf_norm_kn"])
                for row in external_tangent_solve_rows
            ),
            default=0.0,
        ),
        "maximum_checkpoint_residual_inf_norm_kn": max(
            residual_errors,
            default=math.inf,
        ),
        "maximum_accepted_constraint_residual_m2": max(
            constraint_errors,
            default=math.inf,
        ),
        "monitor_displacement_monotonic_in_target_direction": (
            monitor_monotonic
        ),
        "descending_load_branch_observed": any(
            value < 0.0 for value in load_differences
        ),
        "negative_load_factor_observed": any(
            value < 0.0 for value in load_factors
        ),
        "rehardening_load_branch_observed": bool(
            minimum_load_index < len(load_factors) - 1
            and any(
                value > 0.0
                for value in load_differences[minimum_load_index:]
            )
        ),
        "maximum_load_factor": max(load_factors),
        "minimum_load_factor": min(load_factors),
        "maximum_augmented_condition_number": max(
            augmented_conditions,
            default=0.0,
        ),
        "final_free_displacements_m": list(
            accepted.free_displacements_m
        ),
        "final_load_factor": accepted.load_factor,
        "claim_boundary": (
            "This contract covers a multi-DOF arc-length kernel with an "
            "explicitly bound equilibrium linearization and tangent "
            "linear-solver profile; it is not a frame/shell formulation, "
            "Lee-frame evidence, production material-geometric coupling, "
            "production sparse HIP parity, or G1 closure."
        ),
    }
    residual_formula = (
        VECTOR_ARC_LENGTH_LOAD_COUPLED_RESIDUAL_FORMULA
        if equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        else VECTOR_ARC_LENGTH_RESIDUAL_FORMULA
    )
    load_linearization_formula = (
        VECTOR_ARC_LENGTH_LOAD_COUPLED_LINEARIZATION_FORMULA
        if equilibrium_linearization_mode
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        else VECTOR_ARC_LENGTH_PROPORTIONAL_LINEARIZATION_FORMULA
    )
    return VectorArcLengthResult(
        status="ready" if gates_pass else "blocked",
        terminal_reason=terminal_reason,
        case_id=case_id,
        path_contract_hash=path_contract_hash,
        equilibrium_linearization_mode=equilibrium_linearization_mode,
        residual_formula=residual_formula,
        load_linearization_formula=load_linearization_formula,
        config=cfg,
        reference_load_kn=tuple(float(value) for value in reference_load),
        displacement_metric_weights=tuple(
            float(value) for value in metric_weights
        ),
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


__all__ = [
    "VECTOR_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA",
    "VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_MODE",
    "VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_PROFILE",
    "VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE",
    "VECTOR_ARC_LENGTH_LOAD_COUPLED_LINEARIZATION_FORMULA",
    "VECTOR_ARC_LENGTH_LOAD_COUPLED_RESIDUAL_FORMULA",
    "VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE",
    "VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE",
    "VECTOR_ARC_LENGTH_PROPORTIONAL_LINEARIZATION_FORMULA",
    "VECTOR_ARC_LENGTH_RESIDUAL_FORMULA",
    "VECTOR_ARC_LENGTH_SCHEMA_VERSION",
    "VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE",
    "VectorArcLengthCheckpoint",
    "VectorArcLengthConfig",
    "VectorArcLengthContractError",
    "VectorArcLengthEquilibriumProblem",
    "VectorArcLengthLoadCoupledStateTangentProblem",
    "VectorArcLengthProblem",
    "VectorArcLengthResult",
    "VectorArcLengthStateTangentProblem",
    "VectorArcLengthStateTangentSolver",
    "VectorArcLengthTangentSolve",
    "VectorArcLengthTangentSolver",
    "build_vector_arc_length_path_contract_hash",
    "create_vector_arc_length_checkpoint",
    "validate_vector_arc_length_checkpoint",
    "vector_arc_length_continuation",
]
