"""Bounded 6DOF-scaled arc-length continuation for stateful Frame3D.

The continuation coordinates are dimensionless: translations are divided by
one characteristic length and rotations remain in radians.  The spherical
constraint, equilibrium equations, load-factor coordinate, sparse augmented
diagnostics, and corrector line search therefore share one explicit numerical
contract.  Every trial is evaluated from one immutable accepted material
checkpoint; failed attempts reduce the radius from the exact parent bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from types import MappingProxyType
from typing import Any, Mapping, cast

import numpy as np
from scipy.sparse import bmat, csr_matrix

from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    FactorizationDiagnostic,
    StatefulCorotationalFrame3DSparseAssembly,
    StatefulCorotationalFrame3DSparseCheckpoint,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    _checkpoint_parent_signature,
    _equation_scaling,
    _linf,
    _make_checkpoint,
    _require_parent_unchanged,
    _scaled_increment_tolerance,
    _scaled_residual_tolerance,
    _solve_sparse_tangent,
    _translation_component_norm,
    assemble_stateful_corotational_frame3d_sparse,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    immutable_array,
)
from structural_analysis.materials.admissibility import (
    MaterialPathNotAdmissibleError,
)
from structural_analysis.solvers.equation_scaling import (
    EquationScaling6DOF,
    EquationScaling6DOFTransform,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    ScalableSparseFactorizationError,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationError,
)


STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE = (
    "stateful-corotational-frame3d-scaled-spherical-arc-length.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-arc-length-checkpoint.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-arc-length-result.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CLAIM_BOUNDARY = (
    "Experimental bounded sparse Frame3D spherical arc-length candidate with "
    "dimensionless 6DOF equation/coordinate scaling, one translational monitor "
    "coordinate, proportional nodal reference loading, adaptive radius, exact "
    "failed-attempt rollback, and stateful material commit. Rotational or "
    "multiple monitor constraints, non-proportional/follower loads, general "
    "member features, durable checkpoint artifact I/O, production-scale "
    "authority, independent external V&V, and release promotion remain open."
)
_ZERO_HASH = "sha256:" + "0" * 64
_RETRIABLE_ARC_FAILURE_CODES = frozenset(
    {
        "arc_length_augmented_factorization_failed",
        "arc_length_corrector_line_search_failed",
        "arc_length_corrector_maximum_iterations_exhausted",
        "arc_length_invalid_augmented_correction",
        "arc_length_predictor_factorization_failed",
        "invalid_geometry_or_material_trial",
    }
)


class StatefulCorotationalFrame3DArcLengthError(StatefulCorotationalFrame3DSparseError):
    """Fail-closed arc-length configuration, attempt, or checkpoint error."""


@dataclass(frozen=True)
class StatefulCorotationalFrame3DArcLengthConfig:
    monitor_global_dof: int
    target_monitor_displacement_m: float
    target_direction: int
    solver_config: StatefulCorotationalFrame3DSparseConfig = field(
        default_factory=StatefulCorotationalFrame3DSparseConfig
    )
    initial_arc_length: float = 5.0e-3
    minimum_arc_length: float = 1.0e-5
    maximum_arc_length: float = 1.0e-2
    failed_step_reduction_factor: float = 0.5
    successful_step_growth_factor: float = 1.25
    load_factor_metric_scale: float = 1.0e-3
    constraint_tolerance: float = 1.0e-12
    load_factor_increment_tolerance: float = 1.0e-10
    growth_iteration_threshold: int = 4
    maximum_corrector_iterations: int = 20
    maximum_attempt_count: int = 400

    def __post_init__(self) -> None:
        if type(self.monitor_global_dof) is not int:
            raise ValueError("monitor_global_dof must be an integer")
        object.__setattr__(
            self,
            "target_monitor_displacement_m",
            _finite(
                self.target_monitor_displacement_m,
                "target_monitor_displacement_m",
            ),
        )
        if type(self.target_direction) is not int or self.target_direction not in {
            -1,
            1,
        }:
            raise ValueError("target_direction must be -1 or 1")
        if type(self.solver_config) is not StatefulCorotationalFrame3DSparseConfig:
            raise ValueError(
                "solver_config must be an exact StatefulCorotationalFrame3DSparseConfig"
            )
        for name in (
            "initial_arc_length",
            "minimum_arc_length",
            "maximum_arc_length",
            "load_factor_metric_scale",
            "constraint_tolerance",
            "load_factor_increment_tolerance",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        reduction = _finite(
            self.failed_step_reduction_factor,
            "failed_step_reduction_factor",
        )
        growth = _finite(
            self.successful_step_growth_factor,
            "successful_step_growth_factor",
        )
        if not 0.0 < reduction < 1.0:
            raise ValueError("failed_step_reduction_factor must be in (0, 1)")
        if growth <= 1.0:
            raise ValueError("successful_step_growth_factor must exceed 1")
        object.__setattr__(self, "failed_step_reduction_factor", reduction)
        object.__setattr__(self, "successful_step_growth_factor", growth)
        if self.minimum_arc_length > self.initial_arc_length:
            raise ValueError("minimum_arc_length cannot exceed initial_arc_length")
        if self.initial_arc_length > self.maximum_arc_length:
            raise ValueError("initial_arc_length cannot exceed maximum_arc_length")
        for name in (
            "growth_iteration_threshold",
            "maximum_corrector_iterations",
            "maximum_attempt_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE,
            "monitor_global_dof": self.monitor_global_dof,
            "target_monitor_displacement_m": (self.target_monitor_displacement_m),
            "target_direction": self.target_direction,
            "solver_contract": self.solver_config.to_manifest(),
            "solver_contract_hash": self.solver_config.contract_hash,
            "coordinate_scaling": ("q_translation=u/L_char;q_rotation=theta"),
            "equilibrium_scaling": "R_scaled=D_R^-1*R",
            "constraint": (
                "delta_q^T*delta_q+"
                "(load_factor_metric_scale*delta_lambda)^2=arc_length^2"
            ),
            "initial_arc_length": self.initial_arc_length,
            "minimum_arc_length": self.minimum_arc_length,
            "maximum_arc_length": self.maximum_arc_length,
            "failed_step_reduction_factor": (self.failed_step_reduction_factor),
            "successful_step_growth_factor": (self.successful_step_growth_factor),
            "load_factor_metric_scale": self.load_factor_metric_scale,
            "constraint_tolerance": self.constraint_tolerance,
            "load_factor_increment_tolerance": (self.load_factor_increment_tolerance),
            "growth_iteration_threshold": self.growth_iteration_threshold,
            "maximum_corrector_iterations": (self.maximum_corrector_iterations),
            "maximum_attempt_count": self.maximum_attempt_count,
            "corrector_globalization": (
                "backtracking_scaled_equilibrium_constraint_merit.v1"
            ),
            "failed_attempt_policy": (
                "canonical_parent_rollback_then_deterministic_radius_reduction"
            ),
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DArcLengthCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    path_contract_hash: str
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    current_arc_length: float
    previous_tangent_scaled_displacements: tuple[float, ...] | None
    previous_tangent_load_factor: float | None
    attempt_count: int
    accepted_step_count: int
    rejected_step_count: int
    last_attempt_outcome: str
    last_attempt_code: str | None
    last_attempt_stop_reason: str
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "model_hash": self.model_hash,
            "path_contract_hash": self.path_contract_hash,
            "accepted_checkpoint": self.accepted_checkpoint.to_dict(),
            "current_arc_length": self.current_arc_length,
            "previous_tangent_scaled_displacements": (
                None
                if self.previous_tangent_scaled_displacements is None
                else list(self.previous_tangent_scaled_displacements)
            ),
            "previous_tangent_load_factor": (self.previous_tangent_load_factor),
            "attempt_count": self.attempt_count,
            "accepted_step_count": self.accepted_step_count,
            "rejected_step_count": self.rejected_step_count,
            "last_attempt_outcome": self.last_attempt_outcome,
            "last_attempt_code": self.last_attempt_code,
            "last_attempt_stop_reason": self.last_attempt_stop_reason,
            "checkpoint_hash": self.checkpoint_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DArcLengthStep:
    step_index: int
    arc_length: float
    monitor_global_dof: int
    monitor_displacement_m: float
    solved_load_factor: float
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    equation_scaling: EquationScaling6DOF
    augmented_scaled_condition_number: float
    constraint_residual: float
    tangent_scaled_displacements: tuple[float, ...]
    tangent_load_factor: float
    accepted_line_search_alphas: tuple[float, ...]
    convergence_checks: Mapping[str, bool]
    convergence_trace: tuple[Mapping[str, Any], ...]
    factorization_diagnostics: tuple[FactorizationDiagnostic, ...]
    reactions: tuple[tuple[int, float], ...]
    member_results: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "arc_length": self.arc_length,
            "monitor_global_dof": self.monitor_global_dof,
            "monitor_displacement_m": self.monitor_displacement_m,
            "solved_load_factor": self.solved_load_factor,
            "checkpoint": self.checkpoint.to_dict(),
            "equation_scaling": self.equation_scaling.to_dict(),
            "augmented_scaled_condition_number": (
                self.augmented_scaled_condition_number
            ),
            "condition_scope": (
                "dimensionless_augmented_equilibrium_arc_constraint_jacobian"
            ),
            "constraint_residual": self.constraint_residual,
            "tangent_scaled_displacements": list(self.tangent_scaled_displacements),
            "tangent_load_factor": self.tangent_load_factor,
            "accepted_line_search_alphas": list(self.accepted_line_search_alphas),
            "convergence_checks": dict(self.convergence_checks),
            "convergence_trace": [dict(row) for row in self.convergence_trace],
            "factorization_diagnostics": [
                row.to_manifest() for row in self.factorization_diagnostics
            ],
            "reactions": [list(row) for row in self.reactions],
            "member_results": [dict(row) for row in self.member_results],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DArcLengthAttempt:
    attempt_index: int
    arc_length: float
    outcome: str
    failure_code: str | None
    stop_reason: str
    parent_checkpoint_hash: str
    accepted_checkpoint_hash: str
    rollback_exact: bool
    next_arc_length: float
    corrector_iteration_count: int
    convergence_checks: Mapping[str, bool]
    convergence_trace: tuple[Mapping[str, Any], ...]
    boundary_checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "arc_length": self.arc_length,
            "outcome": self.outcome,
            "failure_code": self.failure_code,
            "stop_reason": self.stop_reason,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "accepted_checkpoint_hash": self.accepted_checkpoint_hash,
            "rollback_exact": self.rollback_exact,
            "next_arc_length": self.next_arc_length,
            "corrector_iteration_count": self.corrector_iteration_count,
            "convergence_checks": dict(self.convergence_checks),
            "convergence_trace": [dict(row) for row in self.convergence_trace],
            "boundary_checkpoint_hash": self.boundary_checkpoint_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DArcLengthResult:
    schema_version: str
    profile: str
    status: str
    terminal_reason: str
    model_hash: str
    path_contract_hash: str
    initial_checkpoint: StatefulCorotationalFrame3DArcLengthCheckpoint
    final_checkpoint: StatefulCorotationalFrame3DArcLengthCheckpoint
    checkpoints: tuple[StatefulCorotationalFrame3DArcLengthCheckpoint, ...]
    steps: tuple[StatefulCorotationalFrame3DArcLengthStep, ...]
    attempts: tuple[StatefulCorotationalFrame3DArcLengthAttempt, ...]
    result_hash: str
    metrics: Mapping[str, Any]
    claim_boundary: str

    @property
    def final_state_checkpoint(
        self,
    ) -> StatefulCorotationalFrame3DSparseCheckpoint:
        return self.final_checkpoint.accepted_checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "model_hash": self.model_hash,
            "path_contract_hash": self.path_contract_hash,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "steps": [row.to_dict() for row in self.steps],
            "attempts": [row.to_dict() for row in self.attempts],
            "result_hash": self.result_hash,
            "metrics": dict(self.metrics),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _ArcTrial:
    assembly: StatefulCorotationalFrame3DSparseAssembly
    scaled_coordinates: np.ndarray
    load_factor: float
    scaled_residual: np.ndarray
    scaled_residual_norm: float


@dataclass(frozen=True)
class _ArcCorrectorSelection:
    alpha: float
    scaled_coordinates: np.ndarray
    load_factor: float
    attempts: tuple[Mapping[str, Any], ...]


def stateful_corotational_frame3d_arc_length_path_contract_hash(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DArcLengthConfig,
) -> str:
    monitor_free_index = _monitor_free_index(model, config.monitor_global_dof)
    scaling = _equation_scaling(model, config.solver_config)
    return canonical_hash(
        {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE,
            "model_hash": model.model_hash,
            "config": config.to_manifest(),
            "monitor_free_index": monitor_free_index,
            "equation_scaling_hash": scaling.scaling_hash,
            "claim_boundary": (STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CLAIM_BOUNDARY),
        }
    )


def create_stateful_corotational_frame3d_arc_length_checkpoint(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DArcLengthConfig,
    *,
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    current_arc_length: float,
    previous_tangent_scaled_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    attempt_count: int,
    accepted_step_count: int,
    rejected_step_count: int,
    last_attempt_outcome: str,
    last_attempt_code: str | None,
    last_attempt_stop_reason: str,
) -> StatefulCorotationalFrame3DArcLengthCheckpoint:
    provisional = StatefulCorotationalFrame3DArcLengthCheckpoint(
        schema_version=(
            STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ),
        profile=STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE,
        model_hash=model.model_hash,
        path_contract_hash=(
            stateful_corotational_frame3d_arc_length_path_contract_hash(
                model,
                config,
            )
        ),
        accepted_checkpoint=accepted_checkpoint,
        current_arc_length=float(current_arc_length),
        previous_tangent_scaled_displacements=(previous_tangent_scaled_displacements),
        previous_tangent_load_factor=previous_tangent_load_factor,
        attempt_count=attempt_count,
        accepted_step_count=accepted_step_count,
        rejected_step_count=rejected_step_count,
        last_attempt_outcome=str(last_attempt_outcome),
        last_attempt_code=(
            None if last_attempt_code is None else str(last_attempt_code)
        ),
        last_attempt_stop_reason=str(last_attempt_stop_reason),
        checkpoint_hash=_ZERO_HASH,
    )
    checkpoint = replace(
        provisional,
        checkpoint_hash=canonical_hash(
            _arc_checkpoint_payload(provisional, include_hash=False)
        ),
    )
    return validate_stateful_corotational_frame3d_arc_length_checkpoint(
        checkpoint,
        model=model,
        config=config,
    )


def validate_stateful_corotational_frame3d_arc_length_checkpoint(
    checkpoint: StatefulCorotationalFrame3DArcLengthCheckpoint,
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DArcLengthConfig,
) -> StatefulCorotationalFrame3DArcLengthCheckpoint:
    if type(checkpoint) is not StatefulCorotationalFrame3DArcLengthCheckpoint:
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint type is invalid",
            code="arc_length_checkpoint_invalid",
        )
    if (
        checkpoint.schema_version
        != STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.profile != STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE
        or checkpoint.model_hash != model.model_hash
        or checkpoint.path_contract_hash
        != stateful_corotational_frame3d_arc_length_path_contract_hash(
            model,
            config,
        )
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint contract binding is invalid",
            code="arc_length_checkpoint_binding_invalid",
        )
    try:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            checkpoint.accepted_checkpoint,
            model=model,
            config=config.solver_config,
            require_equilibrium=True,
        )
    except StatefulCorotationalFrame3DSparseError as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            f"arc-length accepted checkpoint is invalid: {error}",
            code="arc_length_checkpoint_accepted_state_invalid",
        ) from error
    try:
        _positive(checkpoint.current_arc_length, "current_arc_length")
    except ValueError as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint radius is invalid",
            code="arc_length_checkpoint_invalid",
        ) from error
    if checkpoint.current_arc_length > config.maximum_arc_length:
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint radius exceeds the configured maximum",
            code="arc_length_checkpoint_invalid",
        )
    for name in (
        "attempt_count",
        "accepted_step_count",
        "rejected_step_count",
    ):
        value = getattr(checkpoint, name)
        if type(value) is not int or value < 0:
            raise StatefulCorotationalFrame3DArcLengthError(
                f"{name} must be a nonnegative integer",
                code="arc_length_checkpoint_invalid",
            )
    if (
        checkpoint.accepted_step_count + checkpoint.rejected_step_count
        != checkpoint.attempt_count
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint attempt counters are inconsistent",
            code="arc_length_checkpoint_invalid",
        )
    tangent = checkpoint.previous_tangent_scaled_displacements
    tangent_load = checkpoint.previous_tangent_load_factor
    if (tangent is None) != (tangent_load is None):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint tangent fields are incomplete",
            code="arc_length_checkpoint_invalid",
        )
    if tangent is not None:
        try:
            values = np.asarray(tangent, dtype=np.float64)
            tangent_load_value = _finite(
                tangent_load,
                "previous_tangent_load_factor",
            )
        except (TypeError, ValueError) as error:
            raise StatefulCorotationalFrame3DArcLengthError(
                "arc-length checkpoint tangent is invalid",
                code="arc_length_checkpoint_invalid",
            ) from error
        if values.shape != (len(model.free_dofs),) or not np.all(np.isfinite(values)):
            raise StatefulCorotationalFrame3DArcLengthError(
                "arc-length checkpoint tangent is invalid",
                code="arc_length_checkpoint_invalid",
            )
        norm_squared = float(
            np.dot(values, values)
            + (config.load_factor_metric_scale * tangent_load_value) ** 2
        )
        unit_tolerance = max(
            1.0e-10,
            100.0 * np.finfo(float).eps * len(values),
        )
        if abs(norm_squared - 1.0) > unit_tolerance:
            raise StatefulCorotationalFrame3DArcLengthError(
                "arc-length checkpoint tangent is not unit normalized",
                code="arc_length_checkpoint_invalid",
            )
    if (
        not isinstance(checkpoint.last_attempt_outcome, str)
        or checkpoint.last_attempt_outcome
        not in {"initial", "committed", "rolled_back"}
        or not isinstance(checkpoint.last_attempt_stop_reason, str)
        or not checkpoint.last_attempt_stop_reason
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint outcome metadata is required",
            code="arc_length_checkpoint_invalid",
        )
    if (
        checkpoint.last_attempt_outcome == "rolled_back"
        and (
            not isinstance(checkpoint.last_attempt_code, str)
            or not checkpoint.last_attempt_code
        )
    ) or (
        checkpoint.last_attempt_outcome != "rolled_back"
        and checkpoint.last_attempt_code is not None
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint failure code is inconsistent",
            code="arc_length_checkpoint_invalid",
        )
    if (
        (checkpoint.attempt_count == 0)
        != (checkpoint.last_attempt_outcome == "initial")
        or (checkpoint.accepted_step_count == 0 and tangent is not None)
        or (checkpoint.accepted_step_count > 0 and tangent is None)
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint lifecycle metadata is inconsistent",
            code="arc_length_checkpoint_invalid",
        )
    expected_hash = canonical_hash(
        _arc_checkpoint_payload(checkpoint, include_hash=False)
    )
    if checkpoint.checkpoint_hash != expected_hash:
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length checkpoint hash mismatch",
            code="arc_length_checkpoint_hash_mismatch",
        )
    return checkpoint


def stateful_corotational_frame3d_arc_length_continuation(
    model: StatefulCorotationalFrame3DSparseModel,
    *,
    config: StatefulCorotationalFrame3DArcLengthConfig,
    initial_state: StatefulCorotationalFrame3DSparseCheckpoint | None = None,
    checkpoint: StatefulCorotationalFrame3DArcLengthCheckpoint | None = None,
) -> StatefulCorotationalFrame3DArcLengthResult:
    """Trace a bounded material/geometric path with transactional arc attempts."""

    if type(model) is not StatefulCorotationalFrame3DSparseModel:
        raise ValueError(
            "model must be an exact StatefulCorotationalFrame3DSparseModel"
        )
    if type(config) is not StatefulCorotationalFrame3DArcLengthConfig:
        raise ValueError(
            "config must be an exact StatefulCorotationalFrame3DArcLengthConfig"
        )
    if initial_state is not None and checkpoint is not None:
        raise ValueError("initial_state cannot be combined with checkpoint")
    monitor_free_index = _monitor_free_index(
        model,
        config.monitor_global_dof,
    )
    if checkpoint is not None:
        boundary = validate_stateful_corotational_frame3d_arc_length_checkpoint(
            checkpoint,
            model=model,
            config=config,
        )
        accepted = boundary.accepted_checkpoint
    else:
        accepted = (
            initial_state
            if initial_state is not None
            else initial_stateful_corotational_frame3d_sparse_checkpoint(
                model,
                config=config.solver_config,
            )
        )
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            accepted,
            model=model,
            config=config.solver_config,
            require_equilibrium=True,
        )
        boundary = create_stateful_corotational_frame3d_arc_length_checkpoint(
            model,
            config,
            accepted_checkpoint=accepted,
            current_arc_length=config.initial_arc_length,
            previous_tangent_scaled_displacements=None,
            previous_tangent_load_factor=None,
            attempt_count=0,
            accepted_step_count=0,
            rejected_step_count=0,
            last_attempt_outcome="initial",
            last_attempt_code=None,
            last_attempt_stop_reason="initial_equilibrium_state",
        )
    initial_monitor = accepted.displacement[config.monitor_global_dof]
    if _target_reached(accepted, config):
        raise StatefulCorotationalFrame3DArcLengthError(
            "initial or checkpoint state already reached the monitor target",
            code="arc_length_target_already_reached",
        )
    if (
        config.target_direction
        * (config.target_monitor_displacement_m - initial_monitor)
        <= 0.0
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "monitor target must lie ahead of the accepted state",
            code="arc_length_target_direction_invalid",
        )

    initial_boundary = boundary
    boundaries = [boundary]
    steps: list[StatefulCorotationalFrame3DArcLengthStep] = []
    attempts: list[StatefulCorotationalFrame3DArcLengthAttempt] = []
    terminal_reason = "maximum_attempt_count_exhausted"
    nonretryable_failure = False

    while boundary.attempt_count < config.maximum_attempt_count:
        if _target_reached(accepted, config):
            terminal_reason = "target_monitor_displacement_reached"
            break
        if boundary.current_arc_length < config.minimum_arc_length:
            terminal_reason = "minimum_arc_length_exhausted"
            break
        parent = accepted
        parent_bytes = canonical_json_bytes(parent.to_dict())
        attempted_arc = boundary.current_arc_length
        try:
            step = _solve_arc_attempt(
                model=model,
                config=config,
                monitor_free_index=monitor_free_index,
                parent=parent,
                arc_length=attempted_arc,
                previous_tangent_scaled_displacements=(
                    boundary.previous_tangent_scaled_displacements
                ),
                previous_tangent_load_factor=(boundary.previous_tangent_load_factor),
            )
        except StatefulCorotationalFrame3DSparseError as error:
            rollback_exact = bool(
                parent_bytes == canonical_json_bytes(parent.to_dict())
            )
            if not rollback_exact:
                raise StatefulCorotationalFrame3DArcLengthError(
                    "failed arc-length attempt mutated its accepted parent",
                    code="parent_state_mutated",
                ) from error
            retriable = error.code in _RETRIABLE_ARC_FAILURE_CODES
            next_arc = (
                attempted_arc * config.failed_step_reduction_factor
                if retriable
                else attempted_arc
            )
            outcome = "rolled_back"
            stop_reason = str(error)
            accepted_step_count = boundary.accepted_step_count
            rejected_step_count = boundary.rejected_step_count + 1
            boundary = create_stateful_corotational_frame3d_arc_length_checkpoint(
                model,
                config,
                accepted_checkpoint=parent,
                current_arc_length=next_arc,
                previous_tangent_scaled_displacements=(
                    boundary.previous_tangent_scaled_displacements
                ),
                previous_tangent_load_factor=(boundary.previous_tangent_load_factor),
                attempt_count=boundary.attempt_count + 1,
                accepted_step_count=accepted_step_count,
                rejected_step_count=rejected_step_count,
                last_attempt_outcome=outcome,
                last_attempt_code=error.code,
                last_attempt_stop_reason=stop_reason,
            )
            attempt = StatefulCorotationalFrame3DArcLengthAttempt(
                attempt_index=boundary.attempt_count,
                arc_length=attempted_arc,
                outcome=outcome,
                failure_code=error.code,
                stop_reason=stop_reason,
                parent_checkpoint_hash=parent.checkpoint_hash,
                accepted_checkpoint_hash=parent.checkpoint_hash,
                rollback_exact=True,
                next_arc_length=next_arc,
                corrector_iteration_count=len(error.attempts),
                convergence_checks=MappingProxyType(
                    {
                        "parent_state_immutable": True,
                        "rollback_exact": True,
                        "retryable_failure": retriable,
                    }
                ),
                convergence_trace=tuple(
                    MappingProxyType(dict(row)) for row in error.attempts
                ),
                boundary_checkpoint_hash=boundary.checkpoint_hash,
            )
            attempts.append(attempt)
            boundaries.append(boundary)
            if not retriable:
                terminal_reason = error.code
                nonretryable_failure = True
                break
            if next_arc < config.minimum_arc_length:
                terminal_reason = "minimum_arc_length_exhausted"
                break
            continue

        accepted = step.checkpoint
        corrector_iterations = max(
            len(step.convergence_trace) - 1,
            0,
        )
        next_arc = attempted_arc
        if corrector_iterations <= config.growth_iteration_threshold:
            next_arc = min(
                config.maximum_arc_length,
                attempted_arc * config.successful_step_growth_factor,
            )
        boundary = create_stateful_corotational_frame3d_arc_length_checkpoint(
            model,
            config,
            accepted_checkpoint=accepted,
            current_arc_length=next_arc,
            previous_tangent_scaled_displacements=(step.tangent_scaled_displacements),
            previous_tangent_load_factor=step.tangent_load_factor,
            attempt_count=boundary.attempt_count + 1,
            accepted_step_count=boundary.accepted_step_count + 1,
            rejected_step_count=boundary.rejected_step_count,
            last_attempt_outcome="committed",
            last_attempt_code=None,
            last_attempt_stop_reason=(
                "equilibrium_constraint_increment_and_commit_gates_converged"
            ),
        )
        steps.append(step)
        attempts.append(
            StatefulCorotationalFrame3DArcLengthAttempt(
                attempt_index=boundary.attempt_count,
                arc_length=attempted_arc,
                outcome="committed",
                failure_code=None,
                stop_reason=(
                    "equilibrium_constraint_increment_and_commit_gates_converged"
                ),
                parent_checkpoint_hash=parent.checkpoint_hash,
                accepted_checkpoint_hash=accepted.checkpoint_hash,
                rollback_exact=True,
                next_arc_length=next_arc,
                corrector_iteration_count=corrector_iterations,
                convergence_checks=step.convergence_checks,
                convergence_trace=step.convergence_trace,
                boundary_checkpoint_hash=boundary.checkpoint_hash,
            )
        )
        boundaries.append(boundary)
    else:
        if _target_reached(accepted, config):
            terminal_reason = "target_monitor_displacement_reached"

    target_reached = _target_reached(accepted, config)
    load_factors = [row.accepted_checkpoint.load_factor for row in boundaries]
    load_differences = [
        right - left for left, right in zip(load_factors, load_factors[1:])
    ]
    rollback_exact = all(row.rollback_exact for row in attempts)
    failed_attempts = [row for row in attempts if row.outcome == "rolled_back"]
    scaling = _equation_scaling(model, config.solver_config)

    def maximum_observation(attribute: str) -> float | None:
        if not steps:
            return None
        return max(float(getattr(row.equation_scaling, attribute)) for row in steps)

    contract_pass = bool(
        target_reached
        and steps
        and rollback_exact
        and not nonretryable_failure
        and all(all(row.convergence_checks.values()) for row in steps)
    )
    metrics = MappingProxyType(
        {
            "contract_pass": contract_pass,
            "target_monitor_displacement_reached": target_reached,
            "attempt_count": len(attempts),
            "accepted_step_count": len(steps),
            "rejected_step_count": sum(
                row.outcome == "rolled_back" for row in attempts
            ),
            "rollback_exact": rollback_exact,
            "failed_attempt_rollback_exact": (
                all(row.rollback_exact for row in failed_attempts)
                if failed_attempts
                else None
            ),
            "adaptive_radius_reduction_used": bool(failed_attempts),
            "descending_load_branch_observed": any(
                value < 0.0 for value in load_differences
            ),
            "maximum_load_factor": max(load_factors),
            "minimum_load_factor": min(load_factors),
            "final_monitor_displacement_m": accepted.displacement[
                config.monitor_global_dof
            ],
            "final_load_factor": accepted.load_factor,
            "characteristic_length": scaling.characteristic_length,
            "reference_force": scaling.reference_force,
            "scaling_hash": scaling.scaling_hash,
            "maximum_translation_residual_norm": maximum_observation(
                "translation_residual_norm"
            ),
            "maximum_rotation_residual_norm": maximum_observation(
                "rotation_residual_norm"
            ),
            "maximum_scaled_residual_norm": maximum_observation("scaled_residual_norm"),
            "maximum_translation_increment_norm": maximum_observation(
                "translation_increment_norm"
            ),
            "maximum_rotation_increment_norm": maximum_observation(
                "rotation_increment_norm"
            ),
            "maximum_scaled_increment_norm": maximum_observation(
                "scaled_increment_norm"
            ),
            "maximum_augmented_scaled_condition_number": (
                maximum_observation("scaled_tangent_condition")
            ),
            "maximum_arc_constraint_residual": (
                max(abs(row.constraint_residual) for row in steps) if steps else None
            ),
            "regularization_count": 0,
            "fallback_count": 0,
        }
    )
    payload = {
        "schema_version": (
            STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION
        ),
        "profile": STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE,
        "status": "ready" if contract_pass else "blocked",
        "terminal_reason": terminal_reason,
        "model_hash": model.model_hash,
        "path_contract_hash": boundary.path_contract_hash,
        "initial_checkpoint_hash": initial_boundary.checkpoint_hash,
        "final_checkpoint_hash": boundary.checkpoint_hash,
        "steps": [row.to_dict() for row in steps],
        "attempts": [row.to_dict() for row in attempts],
        "metrics": dict(metrics),
        "claim_boundary": STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CLAIM_BOUNDARY,
    }
    return StatefulCorotationalFrame3DArcLengthResult(
        schema_version=(STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION),
        profile=STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE,
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        model_hash=model.model_hash,
        path_contract_hash=boundary.path_contract_hash,
        initial_checkpoint=initial_boundary,
        final_checkpoint=boundary,
        checkpoints=tuple(boundaries),
        steps=tuple(steps),
        attempts=tuple(attempts),
        result_hash=canonical_hash(payload),
        metrics=metrics,
        claim_boundary=STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CLAIM_BOUNDARY,
    )


def _solve_arc_attempt(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DArcLengthConfig,
    monitor_free_index: int,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    arc_length: float,
    previous_tangent_scaled_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
) -> StatefulCorotationalFrame3DArcLengthStep:
    solver = config.solver_config
    scaling = _equation_scaling(model, solver)
    parent_signature = _checkpoint_parent_signature(parent)
    parent_scaled = scaling.scale_increment(
        np.asarray(parent.displacement, dtype=np.float64)[list(model.free_dofs)]
    )
    reference_load = np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )[list(model.free_dofs)]
    scaled_reference_load = scaling.scale_residual(reference_load)
    parent_trial = _arc_trial(
        model=model,
        parent=parent,
        scaled_coordinates=parent_scaled,
        load_factor=parent.load_factor,
        scaling=scaling,
    )
    _require_parent_unchanged(parent, parent_signature)
    scaled_tangent = cast(
        csr_matrix,
        scaling.scale_tangent(parent_trial.assembly.tangent_free_csr),
    )
    try:
        displacement_per_load, predictor_diagnostic = _solve_sparse_tangent(
            scaled_tangent,
            scaled_reference_load,
            solver.factorization_policy,
        )
    except (SparseFactorizationError, ScalableSparseFactorizationError) as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            f"arc-length predictor factorization failed: {error.code}",
            code="arc_length_predictor_factorization_failed",
        ) from error
    if displacement_per_load.shape != parent_scaled.shape or not np.all(
        np.isfinite(displacement_per_load)
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length predictor direction is invalid",
            code="arc_length_invalid_augmented_correction",
        )
    tangent_load = 1.0
    tangent_norm = math.sqrt(
        float(np.dot(displacement_per_load, displacement_per_load))
        + (config.load_factor_metric_scale * tangent_load) ** 2
    )
    tangent_displacements = displacement_per_load / tangent_norm
    tangent_load /= tangent_norm
    orientation_dot: float | None = None
    if previous_tangent_scaled_displacements is not None:
        assert previous_tangent_load_factor is not None
        previous = np.asarray(
            previous_tangent_scaled_displacements,
            dtype=np.float64,
        )
        orientation_dot = float(
            np.dot(previous, tangent_displacements)
            + config.load_factor_metric_scale**2
            * previous_tangent_load_factor
            * tangent_load
        )
        if orientation_dot < 0.0:
            tangent_displacements = -tangent_displacements
            tangent_load = -tangent_load
    elif config.target_direction * tangent_displacements[monitor_free_index] < 0.0:
        tangent_displacements = -tangent_displacements
        tangent_load = -tangent_load

    scaled_coordinates = parent_scaled + arc_length * tangent_displacements
    load_factor = parent.load_factor + arc_length * tangent_load
    diagnostics: list[FactorizationDiagnostic] = [predictor_diagnostic]
    accepted_alphas: list[float] = []
    convergence_trace: list[Mapping[str, Any]] = []
    residual_tolerance = _scaled_residual_tolerance(solver, scaling)
    increment_tolerance = _scaled_increment_tolerance(solver, scaling)

    for iteration in range(config.maximum_corrector_iterations + 1):
        trial = _arc_trial(
            model=model,
            parent=parent,
            scaled_coordinates=scaled_coordinates,
            load_factor=load_factor,
            scaling=scaling,
        )
        _require_parent_unchanged(parent, parent_signature)
        delta_coordinates = scaled_coordinates - parent_scaled
        delta_load_factor = load_factor - parent.load_factor
        constraint_residual = _constraint_residual(
            delta_coordinates,
            delta_load_factor,
            arc_length=arc_length,
            load_factor_metric_scale=config.load_factor_metric_scale,
        )
        augmented_tangent = _augmented_tangent(
            trial,
            scaling=scaling,
            scaled_reference_load=scaled_reference_load,
            delta_coordinates=delta_coordinates,
            delta_load_factor=delta_load_factor,
            load_factor_metric_scale=config.load_factor_metric_scale,
        )
        augmented_residual = np.concatenate(
            (
                trial.scaled_residual,
                np.asarray([constraint_residual], dtype=np.float64),
            )
        )
        try:
            correction, diagnostic = _solve_sparse_tangent(
                augmented_tangent,
                -augmented_residual,
                solver.factorization_policy,
            )
        except (SparseFactorizationError, ScalableSparseFactorizationError) as error:
            raise StatefulCorotationalFrame3DArcLengthError(
                f"arc-length augmented factorization failed: {error.code}",
                code="arc_length_augmented_factorization_failed",
                attempts=convergence_trace,
            ) from error
        diagnostics.append(diagnostic)
        if correction.shape != (len(model.free_dofs) + 1,) or not np.all(
            np.isfinite(correction)
        ):
            raise StatefulCorotationalFrame3DArcLengthError(
                "arc-length augmented correction is invalid",
                code="arc_length_invalid_augmented_correction",
                attempts=convergence_trace,
            )
        coordinate_correction = correction[:-1]
        load_correction = float(correction[-1])
        physical_correction = scaling.unscale_increment(coordinate_correction)
        observation = scaling.observe(
            residual=trial.assembly.residual_free,
            increment=physical_correction,
            scaled_tangent_condition=diagnostic.condition_number_1,
        )
        residual_gate = bool(trial.scaled_residual_norm <= residual_tolerance)
        constraint_gate = bool(abs(constraint_residual) <= config.constraint_tolerance)
        increment_gate = bool(_linf(coordinate_correction) <= increment_tolerance)
        load_increment_gate = bool(
            abs(load_correction) <= config.load_factor_increment_tolerance
        )
        trace_row: dict[str, Any] = {
            "iteration": iteration,
            "load_factor": load_factor,
            "monitor_displacement_m": (
                trial.assembly.displacement[config.monitor_global_dof]
            ),
            "scaled_residual_norm": trial.scaled_residual_norm,
            "scaled_residual_tolerance": residual_tolerance,
            "constraint_residual": constraint_residual,
            "constraint_tolerance": config.constraint_tolerance,
            "scaled_increment_norm": _linf(coordinate_correction),
            "scaled_increment_tolerance": increment_tolerance,
            "load_factor_increment": load_correction,
            "load_factor_increment_tolerance": (config.load_factor_increment_tolerance),
            "equation_scaling": observation.to_dict(),
            "augmented_scaled_condition_number": (diagnostic.condition_number_1),
            "condition_scope": (
                "dimensionless_augmented_equilibrium_arc_constraint_jacobian"
            ),
            "predictor_orientation_dot": orientation_dot,
            "residual_gate_pass": residual_gate,
            "constraint_gate_pass": constraint_gate,
            "increment_gate_pass": increment_gate,
            "load_factor_increment_gate_pass": load_increment_gate,
            "accepted_line_search_alpha": None,
            "line_search_attempts": [],
            "accepted": False,
        }
        if residual_gate and constraint_gate and increment_gate and load_increment_gate:
            final = _arc_trial(
                model=model,
                parent=parent,
                scaled_coordinates=scaled_coordinates,
                load_factor=load_factor,
                scaling=scaling,
            )
            _require_parent_unchanged(parent, parent_signature)
            final_constraint = _constraint_residual(
                scaled_coordinates - parent_scaled,
                load_factor - parent.load_factor,
                arc_length=arc_length,
                load_factor_metric_scale=config.load_factor_metric_scale,
            )
            final_state_consistent = tuple(
                state.state_hash for state in final.assembly.trial_material_states
            ) == tuple(
                state.state_hash for state in trial.assembly.trial_material_states
            )
            monitor_direction = bool(
                config.target_direction
                * (
                    final.assembly.displacement[config.monitor_global_dof]
                    - parent.displacement[config.monitor_global_dof]
                )
                > 0.0
            )
            checks = MappingProxyType(
                {
                    "scaled_residual_gate": bool(
                        final.scaled_residual_norm <= residual_tolerance
                    ),
                    "arc_constraint_gate": bool(
                        abs(final_constraint) <= config.constraint_tolerance
                    ),
                    "scaled_increment_gate": increment_gate,
                    "load_factor_increment_gate": load_increment_gate,
                    "line_search_step_valid": all(
                        solver.line_search_minimum_alpha <= alpha <= 1.0
                        for alpha in accepted_alphas
                    ),
                    "material_admissibility": final_state_consistent,
                    "final_reassembled_equilibrium": bool(
                        final.assembly.assembly_hash == trial.assembly.assembly_hash
                        and final_state_consistent
                    ),
                    "parent_state_immutable": bool(
                        _checkpoint_parent_signature(parent) == parent_signature
                    ),
                    "monitor_direction_gate": monitor_direction,
                    "sparse_diagnostic_pass": bool(
                        diagnostics and all(row.contract_pass for row in diagnostics)
                    ),
                    "regularization_not_used": all(
                        not row.regularization_used for row in diagnostics
                    ),
                    "fallback_not_used": all(
                        not row.fallback_used for row in diagnostics
                    ),
                }
            )
            if not all(checks.values()):
                failed = ",".join(name for name, passed in checks.items() if not passed)
                raise StatefulCorotationalFrame3DArcLengthError(
                    f"arc-length commit contract failed: {failed}",
                    code="arc_length_commit_contract_failed",
                    attempts=convergence_trace,
                )
            trace_row["accepted"] = True
            convergence_trace.append(MappingProxyType(trace_row))
            residual = _translation_component_norm(
                final.assembly.residual_free,
                scaling.dof_labels,
            )
            checkpoint = _make_checkpoint(
                model=model,
                config=solver,
                step_index=parent.step_index + 1,
                load_factor=load_factor,
                displacement=final.assembly.displacement,
                material_states=final.assembly.trial_material_states,
                converged_iterations=iteration,
                residual_inf_norm_kn=residual,
                parent_checkpoint_hash=parent.checkpoint_hash,
            )
            validate_stateful_corotational_frame3d_sparse_checkpoint(
                checkpoint,
                model=model,
                config=solver,
                require_equilibrium=True,
            )
            accepted_delta = scaled_coordinates - parent_scaled
            accepted_load_delta = load_factor - parent.load_factor
            accepted_tangent_norm = math.sqrt(
                float(np.dot(accepted_delta, accepted_delta))
                + (config.load_factor_metric_scale * accepted_load_delta) ** 2
            )
            if not math.isfinite(accepted_tangent_norm) or accepted_tangent_norm <= 0.0:
                raise StatefulCorotationalFrame3DArcLengthError(
                    "accepted arc-length tangent is invalid",
                    code="arc_length_invalid_augmented_correction",
                    attempts=convergence_trace,
                )
            return StatefulCorotationalFrame3DArcLengthStep(
                step_index=checkpoint.step_index,
                arc_length=arc_length,
                monitor_global_dof=config.monitor_global_dof,
                monitor_displacement_m=checkpoint.displacement[
                    config.monitor_global_dof
                ],
                solved_load_factor=load_factor,
                checkpoint=checkpoint,
                equation_scaling=observation,
                augmented_scaled_condition_number=(diagnostic.condition_number_1),
                constraint_residual=final_constraint,
                tangent_scaled_displacements=tuple(
                    float(value / accepted_tangent_norm) for value in accepted_delta
                ),
                tangent_load_factor=(accepted_load_delta / accepted_tangent_norm),
                accepted_line_search_alphas=tuple(accepted_alphas),
                convergence_checks=checks,
                convergence_trace=tuple(convergence_trace),
                factorization_diagnostics=tuple(diagnostics),
                reactions=tuple(
                    (dof, float(final.assembly.reactions[dof]))
                    for dof in model.elastic_model.restrained_dofs
                ),
                member_results=tuple(
                    MappingProxyType(response.recovery_manifest())
                    for response in final.assembly.member_responses
                ),
            )
        if iteration == config.maximum_corrector_iterations:
            convergence_trace.append(MappingProxyType(trace_row))
            break
        selected = _arc_corrector_line_search(
            model=model,
            config=config,
            parent=parent,
            parent_signature=parent_signature,
            parent_scaled=parent_scaled,
            scaled_coordinates=scaled_coordinates,
            load_factor=load_factor,
            coordinate_correction=coordinate_correction,
            load_correction=load_correction,
            scaling=scaling,
            arc_length=arc_length,
            base_merit=_arc_merit(
                trial.scaled_residual_norm,
                constraint_residual,
                residual_tolerance=residual_tolerance,
                constraint_tolerance=config.constraint_tolerance,
            ),
            residual_tolerance=residual_tolerance,
        )
        trace_row["accepted_line_search_alpha"] = selected.alpha
        trace_row["line_search_attempts"] = list(selected.attempts)
        trace_row["accepted"] = True
        convergence_trace.append(MappingProxyType(trace_row))
        accepted_alphas.append(selected.alpha)
        scaled_coordinates = np.asarray(
            selected.scaled_coordinates,
            dtype=np.float64,
        ).copy()
        load_factor = selected.load_factor

    raise StatefulCorotationalFrame3DArcLengthError(
        "arc-length corrector did not converge in "
        f"{config.maximum_corrector_iterations} iterations",
        code="arc_length_corrector_maximum_iterations_exhausted",
        attempts=convergence_trace,
    )


def _arc_trial(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    scaled_coordinates: np.ndarray,
    load_factor: float,
    scaling: EquationScaling6DOFTransform,
) -> _ArcTrial:
    if (
        scaled_coordinates.shape != (len(model.free_dofs),)
        or not np.all(np.isfinite(scaled_coordinates))
        or not math.isfinite(load_factor)
    ):
        raise StatefulCorotationalFrame3DArcLengthError(
            "arc-length trial coordinates are invalid",
            code="invalid_geometry_or_material_trial",
        )
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    displacement[list(model.free_dofs)] = scaling.unscale_increment(scaled_coordinates)
    try:
        assembly = assemble_stateful_corotational_frame3d_sparse(
            model,
            parent,
            target_load_factor=load_factor,
            trial_displacement=displacement,
        )
    except MaterialPathNotAdmissibleError as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            f"unsupported_constitutive_path: {error}",
            code="unsupported_constitutive_path",
        ) from error
    except StatefulCorotationalFrame3DSparseError as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            str(error),
            code=error.code,
            attempts=error.attempts,
        ) from error
    except (ValueError, FloatingPointError) as error:
        raise StatefulCorotationalFrame3DArcLengthError(
            "invalid geometry or material arc-length trial",
            code="invalid_geometry_or_material_trial",
        ) from error
    scaled_residual = scaling.scale_residual(assembly.residual_free)
    return _ArcTrial(
        assembly=assembly,
        scaled_coordinates=immutable_array(
            scaled_coordinates,
            dtype="<f8",
        ),
        load_factor=load_factor,
        scaled_residual=immutable_array(scaled_residual, dtype="<f8"),
        scaled_residual_norm=_linf(scaled_residual),
    )


def _augmented_tangent(
    trial: _ArcTrial,
    *,
    scaling: EquationScaling6DOFTransform,
    scaled_reference_load: np.ndarray,
    delta_coordinates: np.ndarray,
    delta_load_factor: float,
    load_factor_metric_scale: float,
) -> csr_matrix:
    scaled_tangent = cast(
        csr_matrix,
        scaling.scale_tangent(trial.assembly.tangent_free_csr),
    )
    constraint_row = 2.0 * delta_coordinates
    constraint_load = 2.0 * load_factor_metric_scale**2 * delta_load_factor
    augmented = bmat(
        [
            [
                scaled_tangent,
                csr_matrix((-scaled_reference_load).reshape(-1, 1)),
            ],
            [
                csr_matrix(constraint_row.reshape(1, -1)),
                csr_matrix(np.asarray([[constraint_load]], dtype=np.float64)),
            ],
        ],
        format="csr",
        dtype=np.float64,
    )
    augmented.sum_duplicates()
    augmented.eliminate_zeros()
    augmented.sort_indices()
    return augmented


def _arc_corrector_line_search(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DArcLengthConfig,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    parent_signature: tuple[Any, ...],
    parent_scaled: np.ndarray,
    scaled_coordinates: np.ndarray,
    load_factor: float,
    coordinate_correction: np.ndarray,
    load_correction: float,
    scaling: EquationScaling6DOFTransform,
    arc_length: float,
    base_merit: float,
    residual_tolerance: float,
) -> _ArcCorrectorSelection:
    solver = config.solver_config
    attempts: list[Mapping[str, Any]] = []
    alpha = 1.0
    for line_search_iteration in range(solver.maximum_line_search_iterations):
        if alpha + 1.0e-15 < solver.line_search_minimum_alpha:
            break
        candidate_coordinates = scaled_coordinates + alpha * coordinate_correction
        candidate_load = load_factor + alpha * load_correction
        attempt: dict[str, Any] = {
            "line_search_iteration": line_search_iteration,
            "alpha": alpha,
            "trial_load_factor": candidate_load,
            "invalid_trial": False,
            "invalid_trial_code": None,
            "scaled_residual_norm": None,
            "constraint_residual": None,
            "normalized_merit": None,
            "required_normalized_merit": (
                (1.0 - solver.line_search_sufficient_decrease * alpha) * base_merit
            ),
            "accepted": False,
        }
        try:
            candidate = _arc_trial(
                model=model,
                parent=parent,
                scaled_coordinates=candidate_coordinates,
                load_factor=candidate_load,
                scaling=scaling,
            )
            _require_parent_unchanged(parent, parent_signature)
            constraint = _constraint_residual(
                candidate_coordinates - parent_scaled,
                candidate_load - parent.load_factor,
                arc_length=arc_length,
                load_factor_metric_scale=config.load_factor_metric_scale,
            )
            merit = _arc_merit(
                candidate.scaled_residual_norm,
                constraint,
                residual_tolerance=residual_tolerance,
                constraint_tolerance=config.constraint_tolerance,
            )
            attempt["scaled_residual_norm"] = candidate.scaled_residual_norm
            attempt["constraint_residual"] = constraint
            attempt["normalized_merit"] = merit
            accepted = bool(
                (
                    candidate.scaled_residual_norm <= residual_tolerance
                    and abs(constraint) <= config.constraint_tolerance
                )
                or merit <= float(attempt["required_normalized_merit"])
            )
            attempt["accepted"] = accepted
            attempts.append(MappingProxyType(attempt))
            if accepted:
                return _ArcCorrectorSelection(
                    alpha=alpha,
                    scaled_coordinates=immutable_array(
                        candidate_coordinates,
                        dtype="<f8",
                    ),
                    load_factor=candidate_load,
                    attempts=tuple(attempts),
                )
        except StatefulCorotationalFrame3DSparseError as error:
            _require_parent_unchanged(parent, parent_signature)
            attempt["invalid_trial"] = True
            attempt["invalid_trial_code"] = error.code
            attempts.append(MappingProxyType(attempt))
        alpha *= solver.line_search_reduction_factor

    invalid_codes = {
        str(row["invalid_trial_code"]) for row in attempts if bool(row["invalid_trial"])
    }
    if invalid_codes == {"unsupported_constitutive_path"}:
        raise StatefulCorotationalFrame3DArcLengthError(
            "unsupported_constitutive_path: no admissible arc-length "
            "corrector line-search step",
            code="unsupported_constitutive_path",
            attempts=attempts,
        )
    raise StatefulCorotationalFrame3DArcLengthError(
        "arc-length corrector line search failed to reduce normalized merit",
        code="arc_length_corrector_line_search_failed",
        attempts=attempts,
    )


def _constraint_residual(
    delta_coordinates: np.ndarray,
    delta_load_factor: float,
    *,
    arc_length: float,
    load_factor_metric_scale: float,
) -> float:
    return float(
        np.dot(delta_coordinates, delta_coordinates)
        + (load_factor_metric_scale * delta_load_factor) ** 2
        - arc_length**2
    )


def _arc_merit(
    scaled_residual_norm: float,
    constraint_residual: float,
    *,
    residual_tolerance: float,
    constraint_tolerance: float,
) -> float:
    return max(
        scaled_residual_norm / residual_tolerance,
        abs(constraint_residual) / constraint_tolerance,
    )


def _target_reached(
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    config: StatefulCorotationalFrame3DArcLengthConfig,
) -> bool:
    return bool(
        config.target_direction
        * (
            checkpoint.displacement[config.monitor_global_dof]
            - config.target_monitor_displacement_m
        )
        >= 0.0
    )


def _monitor_free_index(
    model: StatefulCorotationalFrame3DSparseModel,
    monitor_global_dof: int,
) -> int:
    if type(monitor_global_dof) is not int:
        raise ValueError("monitor_global_dof must be an integer")
    if monitor_global_dof not in model.free_dofs:
        raise ValueError("monitor_global_dof must be a free global DOF")
    if monitor_global_dof % 6 not in (0, 1, 2):
        raise ValueError("monitor_global_dof must be translational UX, UY, or UZ")
    return model.free_dofs.index(monitor_global_dof)


def _arc_checkpoint_payload(
    checkpoint: StatefulCorotationalFrame3DArcLengthCheckpoint,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = checkpoint.to_dict()
    if not include_hash:
        payload.pop("checkpoint_hash")
    return payload


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite number")
    return normalized


def _positive(value: Any, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


__all__ = [
    "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE",
    "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION",
    "StatefulCorotationalFrame3DArcLengthAttempt",
    "StatefulCorotationalFrame3DArcLengthCheckpoint",
    "StatefulCorotationalFrame3DArcLengthConfig",
    "StatefulCorotationalFrame3DArcLengthError",
    "StatefulCorotationalFrame3DArcLengthResult",
    "StatefulCorotationalFrame3DArcLengthStep",
    "create_stateful_corotational_frame3d_arc_length_checkpoint",
    "stateful_corotational_frame3d_arc_length_continuation",
    "stateful_corotational_frame3d_arc_length_path_contract_hash",
    "validate_stateful_corotational_frame3d_arc_length_checkpoint",
]
