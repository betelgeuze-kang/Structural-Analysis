"""Transactional arc-length continuation for corotational fiber frames.

The generic spherical arc-length kernel owns the predictor/corrector algebra.
This bridge binds each physical attempt to one immutable accepted
corotational/material parent, reassembles the material-plus-geometric tangent
at every trial, and commits the full frame checkpoint only after equilibrium
and arc-constraint gates pass.  Failed attempts retain the exact parent bytes
before reducing the radius.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DAssembly,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA,
    VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_MODE,
    VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_PROFILE,
    VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE,
    VectorArcLengthConfig,
    VectorArcLengthResult,
    build_vector_arc_length_path_contract_hash,
    create_vector_arc_length_checkpoint,
    vector_arc_length_continuation,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-arc-length-continuation.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-arc-length-checkpoint.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_PROFILE = (
    "dense-corotational-fiber-frame2d-spherical-arc-length.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_MAX_BYTES = 8 * 1024 * 1024
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This contract verifies bounded spherical arc-length continuation for the "
    "dense stateful corotational 2D fiber frame. Each attempt uses the actual "
    "material-plus-geometric consistent tangent, one immutable accepted "
    "section/material parent, atomic full-state commit, exact failed-attempt "
    "rollback and deterministic radius reduction. Canonical source/path-bound "
    "checkpoints persist the full corotational state, continuation direction, "
    "radius and cumulative progress. It does not establish follower loads, a "
    "general section codec registry, checkpoint-chain replay, production "
    "sparse or ROCm/HIP execution, external benchmark acceptance, full-"
    "building equilibrium, G1 closure, or commercial readiness."
)


class StatefulCorotationalFiberFrame2DArcLengthError(ValueError):
    """Fail-closed arc-length configuration or checkpoint error."""


def _finite_scalar(value: Any, *, path: str, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise StatefulCorotationalFiberFrame2DArcLengthError(f"{path} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be finite"
        ) from exc
    if not math.isfinite(normalized):
        raise StatefulCorotationalFiberFrame2DArcLengthError(f"{path} must be finite")
    if positive and normalized <= 0.0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(f"{path} must be positive")
    return normalized


def _nonnegative_int(value: Any, *, path: str) -> int:
    if type(value) is not int or value < 0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be a non-negative integer"
        )
    return value


def _require_hash(value: Any, *, path: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be a lowercase sha256 digest"
        )
    return normalized


def _finite_vector(values: Any, *, path: str, dimension: int) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be a finite FP64 vector with shape ({dimension},)"
        ) from exc
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be a finite FP64 vector with shape ({dimension},)"
        )
    return np.ascontiguousarray(vector, dtype=np.float64)


def _expect_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} must be an object"
        )
    return value


def _expect_exact_keys(
    value: Any,
    *,
    path: str,
    expected: set[str],
) -> Mapping[str, Any]:
    payload = _expect_mapping(value, path=path)
    actual = set(payload)
    if actual != expected:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            f"{path} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return payload


def _artifact_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint contains a non-JSON or non-finite value"
        ) from exc


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                f"arc-length checkpoint JSON contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise StatefulCorotationalFiberFrame2DArcLengthError(
        f"arc-length checkpoint JSON contains non-finite token {value}"
    )


def _exact_float64_equal(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left, dtype="<f8")
    right_array = np.ascontiguousarray(right, dtype="<f8")
    return left_array.shape == right_array.shape and (
        left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


def _element_state_bytes(
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> tuple[bytes, ...]:
    return tuple(state.canonical_bytes() for state in checkpoint.element_states)


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


def _reference_generalized_load(
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> np.ndarray:
    generalized = (
        problem.physical_coordinate_scale * problem.reference_external_load_vector()
    )
    return np.ascontiguousarray(
        generalized[list(problem.free_global_dofs)],
        dtype=np.float64,
    )


def _metric_weights(config: VectorArcLengthConfig, dimension: int) -> np.ndarray:
    weights = (
        np.ones(dimension, dtype=np.float64)
        if config.displacement_metric_weights is None
        else _finite_vector(
            config.displacement_metric_weights,
            path="displacement_metric_weights",
            dimension=dimension,
        )
    )
    if np.any(weights <= 0.0):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "displacement_metric_weights must all be positive"
        )
    return weights


def _validate_path_config(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
) -> np.ndarray:
    if type(config) is not VectorArcLengthConfig:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "config must be VectorArcLengthConfig"
        )
    dimension = len(problem.free_global_dofs)
    if dimension == 0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "fully constrained F=0 frames are reaction-only outcomes and cannot "
            "make an arc-length convergence claim"
        )
    if type(config.target_monitor_dof_index) is not int or not (
        0 <= config.target_monitor_dof_index < dimension
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "target_monitor_dof_index is outside the free generalized vector"
        )
    if type(config.target_direction) is not int or config.target_direction not in {
        -1,
        1,
    }:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "target_direction must be -1 or 1"
        )
    _finite_scalar(
        config.target_monitor_displacement_m,
        path="target_monitor_displacement_m",
    )
    for name in (
        "initial_arc_length_m",
        "minimum_arc_length_m",
        "maximum_arc_length_m",
        "failed_step_reduction",
        "load_factor_metric_scale_m",
        "residual_tolerance_kn",
        "tangent_solve_residual_tolerance_kn",
        "constraint_tolerance_m2",
    ):
        _finite_scalar(getattr(config, name), path=name, positive=True)
    if config.minimum_arc_length_m > config.initial_arc_length_m:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "minimum_arc_length_m cannot exceed initial_arc_length_m"
        )
    if config.initial_arc_length_m > config.maximum_arc_length_m:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "initial_arc_length_m cannot exceed maximum_arc_length_m"
        )
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "failed_step_reduction must be between zero and one"
        )
    if (
        type(config.maximum_corrector_iterations) is not int
        or config.maximum_corrector_iterations < 1
        or type(config.maximum_attempt_count) is not int
        or config.maximum_attempt_count < 1
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "iteration and attempt limits must be positive integers"
        )
    reference = _reference_generalized_load(problem)
    if float(np.linalg.norm(reference, ord=np.inf)) <= 0.0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "reference load must act on at least one free generalized equation"
        )
    return _metric_weights(config, dimension)


def _config_payload(config: VectorArcLengthConfig) -> dict[str, Any]:
    payload = asdict(config)
    if payload["displacement_metric_weights"] is not None:
        payload["displacement_metric_weights"] = list(
            payload["displacement_metric_weights"]
        )
    return payload


def stateful_corotational_fiber_frame2d_arc_length_path_contract_hash(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
) -> str:
    metric_weights = _validate_path_config(problem, config)
    return canonical_hash(
        {
            "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_PROFILE,
            "source_case_id": problem.case_id,
            "source_problem_contract_hash": problem.contract_hash,
            "config": _config_payload(config),
            "resolved_displacement_metric_weights": metric_weights.tolist(),
            "reference_generalized_load_kn": _reference_generalized_load(
                problem
            ).tolist(),
            "residual_formula": RESIDUAL_FORMULA,
            "constraint_formula": VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA,
            "tangent": "material_plus_geometric_consistent",
            "solver_profile": VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_PROFILE,
            "solver_mode": VECTOR_ARC_LENGTH_DENSE_AUGMENTED_SOLVER_MODE,
            "accepted_trial_policy": (
                "immutable_corotational_material_parent_then_atomic_commit"
            ),
            "failed_attempt_policy": (
                "exact_full_checkpoint_rollback_then_deterministic_reduction"
            ),
            "checkpoint_policy": (
                "signed_zero_preserving_json_every_attempt_source_and_path_bound"
            ),
        }
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DArcLengthStepProblem:
    """One proportional-load arc attempt bound to an immutable frame parent."""

    problem: StatefulCorotationalFiberFrame2DProblem
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    attempt_arc_length_m: float

    def __post_init__(self) -> None:
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            self.problem,
            self.accepted_checkpoint,
        )
        _finite_scalar(
            self.attempt_arc_length_m,
            path="attempt_arc_length_m",
            positive=True,
        )

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@parent={self.accepted_checkpoint.state_hash}"

    def initial_free_displacements_m(self) -> np.ndarray:
        return _free_generalized_coordinates(
            self.problem,
            self.accepted_checkpoint,
        )

    def initial_load_factor(self) -> float:
        return self.accepted_checkpoint.load_factor

    def reference_load_kn(self) -> np.ndarray:
        return _reference_generalized_load(self.problem)

    def assemble(
        self,
        free_displacements_m: Any,
        load_factor: float,
    ) -> StatefulCorotationalFiberFrame2DAssembly:
        return assemble_stateful_corotational_fiber_frame2d(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=load_factor,
            trial_free_coordinates_m=free_displacements_m,
        )

    def internal_force_kn(self, free_displacements_m: np.ndarray) -> np.ndarray:
        return self.assemble(free_displacements_m, 0.0).residual_kn.copy()

    def consistent_tangent_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        return self.assemble(
            free_displacements_m,
            self.accepted_checkpoint.load_factor,
        ).jacobian_kn_per_m.copy()


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DArcLengthProgress:
    """Cumulative acceptance facts retained across persisted restarts."""

    attempt_count: int = 0
    accepted_step_count: int = 0
    rejected_step_count: int = 0
    failed_step_reduction_count: int = 0
    dense_linear_solve_count: int = 0
    corrector_iteration_count: int = 0
    fallback_count: int = 0
    regularization_count: int = 0
    yielded_member_step_count: int = 0
    damaged_member_step_count: int = 0
    maximum_accepted_residual_inf_norm_kn: float = 0.0
    maximum_accepted_constraint_residual_m2: float = 0.0
    maximum_augmented_condition_number: float = 0.0
    maximum_load_factor: float = 0.0
    minimum_load_factor: float = 0.0
    descending_load_branch_observed: bool = False
    negative_load_factor_observed: bool = False
    rehardening_load_branch_observed: bool = False
    rollback_exact: bool = True
    equilibrium_constraint_gate: bool = True
    parent_binding_gate: bool = True
    parent_immutable_gate: bool = True
    monitor_direction_gate: bool = True

    def __post_init__(self) -> None:
        integer_names = {
            "attempt_count",
            "accepted_step_count",
            "rejected_step_count",
            "failed_step_reduction_count",
            "dense_linear_solve_count",
            "corrector_iteration_count",
            "fallback_count",
            "regularization_count",
            "yielded_member_step_count",
            "damaged_member_step_count",
        }
        boolean_names = {
            "descending_load_branch_observed",
            "negative_load_factor_observed",
            "rehardening_load_branch_observed",
            "rollback_exact",
            "equilibrium_constraint_gate",
            "parent_binding_gate",
            "parent_immutable_gate",
            "monitor_direction_gate",
        }
        for row in fields(type(self)):
            value = getattr(self, row.name)
            if row.name in integer_names:
                _nonnegative_int(value, path=f"progress.{row.name}")
            elif row.name in boolean_names:
                if type(value) is not bool:
                    raise StatefulCorotationalFiberFrame2DArcLengthError(
                        f"progress.{row.name} must be boolean"
                    )
            else:
                normalized = _finite_scalar(value, path=f"progress.{row.name}")
                if row.name.startswith("maximum_accepted_") or row.name == (
                    "maximum_augmented_condition_number"
                ):
                    if normalized < 0.0:
                        raise StatefulCorotationalFiberFrame2DArcLengthError(
                            f"progress.{row.name} must be non-negative"
                        )
        if self.accepted_step_count + self.rejected_step_count != self.attempt_count:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "accepted and rejected counts must equal attempt_count"
            )
        if self.failed_step_reduction_count != self.rejected_step_count:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "every rejected attempt must have one radius reduction"
            )
        if self.minimum_load_factor > self.maximum_load_factor:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "progress load-factor bounds are inverted"
            )

    def to_dict(self) -> dict[str, Any]:
        return {row.name: getattr(self, row.name) for row in fields(type(self))}

    @classmethod
    def from_dict(
        cls,
        value: Any,
    ) -> "StatefulCorotationalFiberFrame2DArcLengthProgress":
        expected = {row.name for row in fields(cls)}
        payload = _expect_exact_keys(
            value,
            path="/boundary/progress",
            expected=expected,
        )
        integer_names = {
            "attempt_count",
            "accepted_step_count",
            "rejected_step_count",
            "failed_step_reduction_count",
            "dense_linear_solve_count",
            "corrector_iteration_count",
            "fallback_count",
            "regularization_count",
            "yielded_member_step_count",
            "damaged_member_step_count",
        }
        boolean_names = {
            "descending_load_branch_observed",
            "negative_load_factor_observed",
            "rehardening_load_branch_observed",
            "rollback_exact",
            "equilibrium_constraint_gate",
            "parent_binding_gate",
            "parent_immutable_gate",
            "monitor_direction_gate",
        }
        normalized: dict[str, Any] = {}
        for name in expected:
            if name in integer_names:
                normalized[name] = _nonnegative_int(
                    payload[name],
                    path=f"/boundary/progress/{name}",
                )
            elif name in boolean_names:
                if type(payload[name]) is not bool:
                    raise StatefulCorotationalFiberFrame2DArcLengthError(
                        f"/boundary/progress/{name} must be boolean"
                    )
                normalized[name] = payload[name]
            else:
                normalized[name] = _finite_scalar(
                    payload[name],
                    path=f"/boundary/progress/{name}",
                )
        return cls(**normalized)


def _checkpoint_hash_payload(
    *,
    source_case_id: str,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    progress: StatefulCorotationalFiberFrame2DArcLengthProgress,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ),
        "source": {
            "case_id": source_case_id,
            "problem_contract_hash": source_problem_contract_hash,
        },
        "path_contract_hash": path_contract_hash,
        "boundary": {
            "accepted_checkpoint": accepted_checkpoint.to_dict(),
            "current_arc_length_m": current_arc_length_m,
            "previous_tangent_displacements": (
                None
                if previous_tangent_displacements is None
                else list(previous_tangent_displacements)
            ),
            "previous_tangent_load_factor": previous_tangent_load_factor,
            "progress": progress.to_dict(),
            "last_attempt_outcome": last_attempt_outcome,
            "last_attempt_stop_reason": last_attempt_stop_reason,
        },
    }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
    """Persisted attempt boundary including material and path-direction state."""

    schema_version: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    current_arc_length_m: float
    previous_tangent_displacements: tuple[float, ...] | None
    previous_tangent_load_factor: float | None
    progress: StatefulCorotationalFiberFrame2DArcLengthProgress
    last_attempt_outcome: str
    last_attempt_stop_reason: str
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint schema_version is invalid"
            )
        if not str(self.source_case_id).strip():
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint source_case_id is required"
            )
        _require_hash(
            self.source_problem_contract_hash,
            path="checkpoint.source_problem_contract_hash",
        )
        _require_hash(self.path_contract_hash, path="checkpoint.path_contract_hash")
        if type(self.accepted_checkpoint) is not (
            StatefulCorotationalFiberFrame2DCheckpoint
        ):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint accepted_checkpoint type is invalid"
            )
        arc_length = _finite_scalar(
            self.current_arc_length_m,
            path="checkpoint.current_arc_length_m",
            positive=True,
        )
        object.__setattr__(self, "current_arc_length_m", arc_length)
        tangent = self.previous_tangent_displacements
        tangent_load = self.previous_tangent_load_factor
        if (tangent is None) != (tangent_load is None):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint previous tangent fields must both be present or absent"
            )
        if tangent is not None:
            normalized_tangent = tuple(
                float(value)
                for value in _finite_vector(
                    tangent,
                    path="checkpoint.previous_tangent_displacements",
                    dimension=len(tangent),
                )
            )
            object.__setattr__(
                self,
                "previous_tangent_displacements",
                normalized_tangent,
            )
            object.__setattr__(
                self,
                "previous_tangent_load_factor",
                _finite_scalar(
                    tangent_load,
                    path="checkpoint.previous_tangent_load_factor",
                ),
            )
        if type(self.progress) is not (
            StatefulCorotationalFiberFrame2DArcLengthProgress
        ):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint progress type is invalid"
            )
        if not str(self.last_attempt_outcome).strip():
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint last_attempt_outcome is required"
            )
        if not str(self.last_attempt_stop_reason).strip():
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint last_attempt_stop_reason is required"
            )
        payload = _checkpoint_hash_payload(
            source_case_id=self.source_case_id,
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_checkpoint=self.accepted_checkpoint,
            current_arc_length_m=self.current_arc_length_m,
            previous_tangent_displacements=self.previous_tangent_displacements,
            previous_tangent_load_factor=self.previous_tangent_load_factor,
            progress=self.progress,
            last_attempt_outcome=self.last_attempt_outcome,
            last_attempt_stop_reason=self.last_attempt_stop_reason,
        )
        expected_hash = canonical_hash(payload)
        if self.checkpoint_hash and self.checkpoint_hash != expected_hash:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint_hash mismatch"
            )
        if not self.checkpoint_hash:
            object.__setattr__(self, "checkpoint_hash", expected_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            **_checkpoint_hash_payload(
                source_case_id=self.source_case_id,
                source_problem_contract_hash=self.source_problem_contract_hash,
                path_contract_hash=self.path_contract_hash,
                accepted_checkpoint=self.accepted_checkpoint,
                current_arc_length_m=self.current_arc_length_m,
                previous_tangent_displacements=(self.previous_tangent_displacements),
                previous_tangent_load_factor=self.previous_tangent_load_factor,
                progress=self.progress,
                last_attempt_outcome=self.last_attempt_outcome,
                last_attempt_stop_reason=self.last_attempt_stop_reason,
            ),
            "checkpoint_hash": self.checkpoint_hash,
        }

    def to_bytes(self) -> bytes:
        return _artifact_json_bytes(self.to_dict())


def _checkpoint_residual_inf_norm_kn(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> float:
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        checkpoint,
        target_load_factor=checkpoint.load_factor,
        trial_free_coordinates_m=_free_generalized_coordinates(
            problem,
            checkpoint,
        ),
    )
    return float(np.linalg.norm(assembly.residual_kn, ord=np.inf))


def create_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
    *,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
    progress: StatefulCorotationalFiberFrame2DArcLengthProgress,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
    checkpoint = StatefulCorotationalFiberFrame2DArcLengthCheckpoint(
        schema_version=(
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
        ),
        source_case_id=problem.case_id,
        source_problem_contract_hash=problem.contract_hash,
        path_contract_hash=(
            stateful_corotational_fiber_frame2d_arc_length_path_contract_hash(
                problem,
                config,
            )
        ),
        accepted_checkpoint=accepted_checkpoint,
        current_arc_length_m=current_arc_length_m,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        progress=progress,
        last_attempt_outcome=last_attempt_outcome,
        last_attempt_stop_reason=last_attempt_stop_reason,
    )
    return validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
        checkpoint,
        problem,
        config,
    )


def validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
    checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint,
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
) -> StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
    if type(checkpoint) is not StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint type is invalid"
        )
    metric_weights = _validate_path_config(problem, config)
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        checkpoint.accepted_checkpoint,
    )
    if checkpoint.source_case_id != problem.case_id:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint source case does not match problem"
        )
    if checkpoint.source_problem_contract_hash != problem.contract_hash:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint source problem contract mismatch"
        )
    expected_path_hash = (
        stateful_corotational_fiber_frame2d_arc_length_path_contract_hash(
            problem,
            config,
        )
    )
    if checkpoint.path_contract_hash != expected_path_hash:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint path contract mismatch"
        )
    if checkpoint.current_arc_length_m > config.maximum_arc_length_m:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint current arc length exceeds the configured maximum"
        )
    if checkpoint.progress.attempt_count > config.maximum_attempt_count:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint attempt count exceeds the configured budget"
        )
    tangent = checkpoint.previous_tangent_displacements
    if tangent is not None:
        if len(tangent) != len(problem.free_global_dofs):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint previous tangent dimension mismatch"
            )
        tangent_load = checkpoint.previous_tangent_load_factor
        assert tangent_load is not None
        tangent_norm_squared = (
            float(np.dot(metric_weights * np.asarray(tangent), tangent))
            + (config.load_factor_metric_scale_m * tangent_load) ** 2
        )
        normalized_constraint_tolerance = max(
            1.0e-8,
            config.constraint_tolerance_m2 / checkpoint.current_arc_length_m**2,
        )
        if abs(tangent_norm_squared - 1.0) > normalized_constraint_tolerance:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "checkpoint previous tangent is not unit arc length"
            )
    expected = StatefulCorotationalFiberFrame2DArcLengthCheckpoint(
        schema_version=checkpoint.schema_version,
        source_case_id=checkpoint.source_case_id,
        source_problem_contract_hash=checkpoint.source_problem_contract_hash,
        path_contract_hash=checkpoint.path_contract_hash,
        accepted_checkpoint=checkpoint.accepted_checkpoint,
        current_arc_length_m=checkpoint.current_arc_length_m,
        previous_tangent_displacements=checkpoint.previous_tangent_displacements,
        previous_tangent_load_factor=checkpoint.previous_tangent_load_factor,
        progress=checkpoint.progress,
        last_attempt_outcome=checkpoint.last_attempt_outcome,
        last_attempt_stop_reason=checkpoint.last_attempt_stop_reason,
    )
    if checkpoint.checkpoint_hash != expected.checkpoint_hash:
        raise StatefulCorotationalFiberFrame2DArcLengthError("checkpoint_hash mismatch")
    checkpoint_residual = _checkpoint_residual_inf_norm_kn(
        problem,
        checkpoint.accepted_checkpoint,
    )
    if checkpoint_residual > config.residual_tolerance_kn:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "checkpoint accepted state is not in equilibrium"
        )
    return checkpoint


def load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
    data: bytes | bytearray | memoryview,
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
) -> StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint artifact must be bytes"
        )
    raw = bytes(data)
    if len(raw) > (STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_MAX_BYTES):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint artifact exceeds the bounded byte limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except StatefulCorotationalFiberFrame2DArcLengthError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint is not valid UTF-8 JSON"
        ) from exc
    if _artifact_json_bytes(parsed) != raw:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint is not canonical JSON"
        )
    payload = _expect_exact_keys(
        parsed,
        path="/",
        expected={
            "schema_version",
            "source",
            "path_contract_hash",
            "boundary",
            "checkpoint_hash",
        },
    )
    if payload["schema_version"] != (
        STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint schema_version is invalid"
        )
    source = _expect_exact_keys(
        payload["source"],
        path="/source",
        expected={"case_id", "problem_contract_hash"},
    )
    boundary = _expect_exact_keys(
        payload["boundary"],
        path="/boundary",
        expected={
            "accepted_checkpoint",
            "current_arc_length_m",
            "previous_tangent_displacements",
            "previous_tangent_load_factor",
            "progress",
            "last_attempt_outcome",
            "last_attempt_stop_reason",
        },
    )
    accepted_payload = _expect_mapping(
        boundary["accepted_checkpoint"],
        path="/boundary/accepted_checkpoint",
    )
    accepted = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        _artifact_json_bytes(accepted_payload),
        problem,
    )
    dimension = len(problem.free_global_dofs)
    tangent_payload = boundary["previous_tangent_displacements"]
    tangent = (
        None
        if tangent_payload is None
        else tuple(
            float(value)
            for value in _finite_vector(
                tangent_payload,
                path="/boundary/previous_tangent_displacements",
                dimension=dimension,
            )
        )
    )
    tangent_load_payload = boundary["previous_tangent_load_factor"]
    tangent_load = (
        None
        if tangent_load_payload is None
        else _finite_scalar(
            tangent_load_payload,
            path="/boundary/previous_tangent_load_factor",
        )
    )
    checkpoint = StatefulCorotationalFiberFrame2DArcLengthCheckpoint(
        schema_version=str(payload["schema_version"]),
        source_case_id=str(source["case_id"]),
        source_problem_contract_hash=_require_hash(
            source["problem_contract_hash"],
            path="/source/problem_contract_hash",
        ),
        path_contract_hash=_require_hash(
            payload["path_contract_hash"],
            path="/path_contract_hash",
        ),
        accepted_checkpoint=accepted,
        current_arc_length_m=_finite_scalar(
            boundary["current_arc_length_m"],
            path="/boundary/current_arc_length_m",
            positive=True,
        ),
        previous_tangent_displacements=tangent,
        previous_tangent_load_factor=tangent_load,
        progress=StatefulCorotationalFiberFrame2DArcLengthProgress.from_dict(
            boundary["progress"]
        ),
        last_attempt_outcome=str(boundary["last_attempt_outcome"]),
        last_attempt_stop_reason=str(boundary["last_attempt_stop_reason"]),
        checkpoint_hash=_require_hash(
            payload["checkpoint_hash"],
            path="/checkpoint_hash",
        ),
    )
    validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
        checkpoint,
        problem,
        config,
    )
    if checkpoint.to_bytes() != raw:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint artifact round-trip mismatch"
        )
    return checkpoint


def write_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
    checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint,
    target: str | Path,
) -> Path:
    validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
        checkpoint,
        problem,
        config,
    )
    raw = checkpoint.to_bytes()
    restored = load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
        raw,
        problem,
        config,
    )
    if restored.accepted_checkpoint.canonical_bytes() != (
        checkpoint.accepted_checkpoint.canonical_bytes()
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "accepted checkpoint changed during arc-length serialization"
        )
    path = Path(target)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint target already exists"
        ) from exc
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint could not be written"
        ) from exc
    return path


def read_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: VectorArcLengthConfig,
    source: str | Path,
) -> StatefulCorotationalFiberFrame2DArcLengthCheckpoint:
    path = Path(source)
    try:
        size = path.stat().st_size
        if size > (STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_MAX_BYTES):
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "arc-length checkpoint artifact exceeds the bounded byte limit"
            )
        raw = path.read_bytes()
    except StatefulCorotationalFiberFrame2DArcLengthError:
        raise
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "arc-length checkpoint could not be read"
        ) from exc
    return load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
        raw,
        problem,
        config,
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DArcLengthAttempt:
    attempt_index: int
    arc_length_m: float
    outcome: str
    stop_reason: str
    parent_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    vector_result: VectorArcLengthResult
    final_assembly: StatefulCorotationalFiberFrame2DAssembly | None
    rollback_exact: bool
    material_state_changed: bool
    next_arc_length_m: float
    checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint

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
            "parent_state_hash": self.parent_checkpoint.state_hash,
            "accepted_state_hash": self.accepted_checkpoint.state_hash,
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
class StatefulCorotationalFiberFrame2DArcLengthResult:
    status: str
    terminal_reason: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    config: VectorArcLengthConfig
    initial_checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint
    checkpoints: tuple[StatefulCorotationalFiberFrame2DArcLengthCheckpoint, ...]
    attempts: tuple[StatefulCorotationalFiberFrame2DArcLengthAttempt, ...]
    metrics: dict[str, Any]

    @property
    def initial_state(self) -> StatefulCorotationalFiberFrame2DCheckpoint:
        return self.initial_checkpoint.accepted_checkpoint

    @property
    def final_state(self) -> StatefulCorotationalFiberFrame2DCheckpoint:
        return self.final_checkpoint.accepted_checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_SCHEMA_VERSION
            ),
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_PROFILE,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": self.source_problem_contract_hash,
            "path_contract_hash": self.path_contract_hash,
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "constraint_formula": VECTOR_ARC_LENGTH_CONSTRAINT_FORMULA,
            "tangent_definition": "material_plus_geometric_consistent",
            "equilibrium_linearization_mode": (
                VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
            ),
            "config": _config_payload(self.config),
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": [row.to_dict() for row in self.attempts],
            "metrics": dict(self.metrics),
            "claims": {
                "stateful_corotational_fiber_frame2d_arc_length_path": bool(
                    self.metrics["contract_pass"]
                ),
                "material_plus_geometric_consistent_tangent": bool(
                    self.metrics["dense_linear_solve_count"] > 0
                ),
                "accepted_material_parent_rebound_each_step": bool(
                    self.metrics["accepted_step_count"] > 0
                ),
                "material_state_commit_rollback": bool(
                    self.metrics["material_state_commit_rollback"]
                ),
                "failed_attempt_full_state_rollback_exact": bool(
                    self.metrics["rollback_exact"]
                ),
                "descending_load_branch_observed": bool(
                    self.metrics["descending_load_branch_observed"]
                ),
                "source_bound_persisted_checkpoint": True,
                "checkpoint_chain_replay": False,
                "external_benchmark_acceptance": False,
                "lee_frame_acceptance": False,
                "production_sparse_solver": False,
                "rocm_hip_parity": False,
                "g1_full_building_closure": False,
                "commercial_readiness": False,
            },
            "claim_boundary": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CLAIM_BOUNDARY
            ),
        }


def _target_reached(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    config: VectorArcLengthConfig,
) -> bool:
    free = _free_generalized_coordinates(problem, checkpoint)
    monitored = free[config.target_monitor_dof_index]
    return bool(
        config.target_direction * (monitored - config.target_monitor_displacement_m)
        >= 0.0
    )


def _single_attempt_config(
    config: VectorArcLengthConfig,
    *,
    accepted_monitor_coordinate_m: float,
    current_arc_length_m: float,
    metric_weights: np.ndarray,
) -> VectorArcLengthConfig:
    local_target = math.nextafter(
        accepted_monitor_coordinate_m,
        math.inf if config.target_direction > 0 else -math.inf,
    )
    return replace(
        config,
        target_monitor_displacement_m=local_target,
        initial_arc_length_m=current_arc_length_m,
        displacement_metric_weights=tuple(float(value) for value in metric_weights),
        maximum_attempt_count=1,
    )


def _single_vector_attempt(
    step_problem: StatefulCorotationalFiberFrame2DArcLengthStepProblem,
    *,
    config: VectorArcLengthConfig,
    metric_weights: np.ndarray,
    previous_tangent_displacements: tuple[float, ...] | None,
    previous_tangent_load_factor: float | None,
) -> VectorArcLengthResult:
    accepted_free = step_problem.initial_free_displacements_m()
    local_config = _single_attempt_config(
        config,
        accepted_monitor_coordinate_m=float(
            accepted_free[config.target_monitor_dof_index]
        ),
        current_arc_length_m=step_problem.attempt_arc_length_m,
        metric_weights=metric_weights,
    )
    reference_load = step_problem.reference_load_kn()
    local_path_hash = build_vector_arc_length_path_contract_hash(
        case_id=step_problem.case_id,
        config=local_config,
        reference_load_kn=reference_load,
        displacement_metric_weights=metric_weights,
        equilibrium_linearization_mode=(
            VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
        ),
    )
    origin = create_vector_arc_length_checkpoint(
        case_id=step_problem.case_id,
        path_contract_hash=local_path_hash,
        step_index=step_problem.accepted_checkpoint.step_index,
        free_displacements_m=accepted_free,
        load_factor=step_problem.accepted_checkpoint.load_factor,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        current_arc_length_m=step_problem.attempt_arc_length_m,
    )
    return vector_arc_length_continuation(
        step_problem,
        config=local_config,
        resume_from=origin,
    )


def _attempt_dense_solve_count(vector_result: VectorArcLengthResult) -> int:
    if not vector_result.attempts:
        return 0
    attempt = vector_result.attempts[0]
    predictor = int("predictor_tangent_displacements" in attempt)
    correctors = sum(
        int(row.get("converged") is False)
        for row in attempt.get("corrector_history", [])
    )
    return predictor + correctors


def _updated_progress(
    progress: StatefulCorotationalFiberFrame2DArcLengthProgress,
    *,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    accepted: StatefulCorotationalFiberFrame2DCheckpoint,
    vector_result: VectorArcLengthResult,
    final_assembly: StatefulCorotationalFiberFrame2DAssembly | None,
    committed: bool,
    rollback_exact: bool,
    equilibrium_constraint_gate: bool,
    parent_binding_gate: bool,
    parent_immutable_gate: bool,
    monitor_direction_gate: bool,
    residual_inf_norm_kn: float,
    constraint_residual_m2: float,
) -> StatefulCorotationalFiberFrame2DArcLengthProgress:
    load_increment = accepted.load_factor - parent.load_factor
    descending = bool(
        progress.descending_load_branch_observed or (committed and load_increment < 0.0)
    )
    rehardening = bool(
        progress.rehardening_load_branch_observed
        or (
            committed
            and progress.descending_load_branch_observed
            and load_increment > 0.0
        )
    )
    augmented_condition = float(
        vector_result.metrics.get("maximum_augmented_condition_number", 0.0)
    )
    corrector_count = sum(
        int(row.get("corrector_iteration_count", 0)) for row in vector_result.attempts
    )
    yielded = 0
    damaged = 0
    if committed and final_assembly is not None:
        yielded = int(
            any(
                row.response.yielded_integration_point_count > 0
                for row in final_assembly.member_assemblies
            )
        )
        damaged = int(
            any(
                row.response.damaged_integration_point_count > 0
                for row in final_assembly.member_assemblies
            )
        )
    return StatefulCorotationalFiberFrame2DArcLengthProgress(
        attempt_count=progress.attempt_count + 1,
        accepted_step_count=progress.accepted_step_count + int(committed),
        rejected_step_count=progress.rejected_step_count + int(not committed),
        failed_step_reduction_count=(
            progress.failed_step_reduction_count + int(not committed)
        ),
        dense_linear_solve_count=(
            progress.dense_linear_solve_count
            + _attempt_dense_solve_count(vector_result)
        ),
        corrector_iteration_count=(
            progress.corrector_iteration_count + corrector_count
        ),
        fallback_count=(
            progress.fallback_count
            + int(vector_result.metrics.get("fallback_count", 0))
        ),
        regularization_count=(
            progress.regularization_count
            + int(vector_result.metrics.get("regularization_count", 0))
        ),
        yielded_member_step_count=progress.yielded_member_step_count + yielded,
        damaged_member_step_count=progress.damaged_member_step_count + damaged,
        maximum_accepted_residual_inf_norm_kn=max(
            progress.maximum_accepted_residual_inf_norm_kn,
            residual_inf_norm_kn if committed else 0.0,
        ),
        maximum_accepted_constraint_residual_m2=max(
            progress.maximum_accepted_constraint_residual_m2,
            abs(constraint_residual_m2) if committed else 0.0,
        ),
        maximum_augmented_condition_number=max(
            progress.maximum_augmented_condition_number,
            augmented_condition,
        ),
        maximum_load_factor=max(progress.maximum_load_factor, accepted.load_factor),
        minimum_load_factor=min(progress.minimum_load_factor, accepted.load_factor),
        descending_load_branch_observed=descending,
        negative_load_factor_observed=bool(
            progress.negative_load_factor_observed or accepted.load_factor < 0.0
        ),
        rehardening_load_branch_observed=rehardening,
        rollback_exact=bool(progress.rollback_exact and rollback_exact),
        equilibrium_constraint_gate=bool(
            progress.equilibrium_constraint_gate and equilibrium_constraint_gate
        ),
        parent_binding_gate=bool(progress.parent_binding_gate and parent_binding_gate),
        parent_immutable_gate=bool(
            progress.parent_immutable_gate and parent_immutable_gate
        ),
        monitor_direction_gate=bool(
            progress.monitor_direction_gate and monitor_direction_gate
        ),
    )


def stateful_corotational_fiber_frame2d_arc_length_continuation(
    problem: StatefulCorotationalFiberFrame2DProblem,
    *,
    config: VectorArcLengthConfig,
    initial_state: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    checkpoint: StatefulCorotationalFiberFrame2DArcLengthCheckpoint | None = None,
) -> StatefulCorotationalFiberFrame2DArcLengthResult:
    """Trace a material/geometric frame path with transactional arc attempts."""

    if initial_state is not None and checkpoint is not None:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "initial_state cannot be combined with checkpoint"
        )
    metric_weights = _validate_path_config(problem, config)
    path_hash = stateful_corotational_fiber_frame2d_arc_length_path_contract_hash(
        problem,
        config,
    )
    if checkpoint is not None:
        boundary = validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
            checkpoint,
            problem,
            config,
        )
        accepted = boundary.accepted_checkpoint
        current_arc_length_m = boundary.current_arc_length_m
        previous_tangent_displacements = boundary.previous_tangent_displacements
        previous_tangent_load_factor = boundary.previous_tangent_load_factor
        progress = boundary.progress
        restart_consumed = True
    else:
        accepted = initial_state or (
            initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint(problem, accepted)
        initial_residual_inf_norm_kn = _checkpoint_residual_inf_norm_kn(
            problem,
            accepted,
        )
        if initial_residual_inf_norm_kn > config.residual_tolerance_kn:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "initial accepted state is not in equilibrium"
            )
        current_arc_length_m = min(
            config.initial_arc_length_m,
            config.maximum_arc_length_m,
        )
        previous_tangent_displacements = None
        previous_tangent_load_factor = None
        progress = StatefulCorotationalFiberFrame2DArcLengthProgress(
            maximum_load_factor=accepted.load_factor,
            minimum_load_factor=accepted.load_factor,
            negative_load_factor_observed=accepted.load_factor < 0.0,
        )
        boundary = create_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
            problem,
            config,
            accepted_checkpoint=accepted,
            current_arc_length_m=current_arc_length_m,
            previous_tangent_displacements=None,
            previous_tangent_load_factor=None,
            progress=progress,
            last_attempt_outcome="initial",
            last_attempt_stop_reason="initial_equilibrium_state",
        )
        restart_consumed = False

    if _target_reached(problem, accepted, config):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "initial or checkpoint state already reached the monitor target"
        )
    initial_free = _free_generalized_coordinates(problem, accepted)
    initial_monitor = initial_free[config.target_monitor_dof_index]
    if (
        config.target_direction
        * (config.target_monitor_displacement_m - initial_monitor)
        <= 0.0
    ):
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "monitor target must lie ahead of the accepted state"
        )

    initial_checkpoint = boundary
    checkpoints = [boundary]
    attempts: list[StatefulCorotationalFiberFrame2DArcLengthAttempt] = []
    terminal_reason = "maximum_attempt_count_exhausted"

    while progress.attempt_count < config.maximum_attempt_count:
        if _target_reached(problem, accepted, config):
            terminal_reason = "target_monitor_displacement_reached"
            break
        if current_arc_length_m < config.minimum_arc_length_m:
            terminal_reason = "minimum_arc_length_exhausted"
            break
        parent = accepted
        parent_bytes = parent.canonical_bytes()
        parent_element_bytes = _element_state_bytes(parent)
        parent_free = _free_generalized_coordinates(problem, parent)
        step_problem = StatefulCorotationalFiberFrame2DArcLengthStepProblem(
            problem=problem,
            accepted_checkpoint=parent,
            attempt_arc_length_m=current_arc_length_m,
        )
        vector_result = _single_vector_attempt(
            step_problem,
            config=config,
            metric_weights=metric_weights,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
        )
        if len(vector_result.attempts) != 1:
            raise StatefulCorotationalFiberFrame2DArcLengthError(
                "single-attempt vector kernel returned an invalid attempt count"
            )
        vector_attempt = vector_result.attempts[0]
        arc_length_attempted = current_arc_length_m
        parent_immutable = bool(
            parent.canonical_bytes() == parent_bytes
            and _element_state_bytes(parent) == parent_element_bytes
            and parent.compute_state_hash() == parent.state_hash
        )
        final_assembly: StatefulCorotationalFiberFrame2DAssembly | None = None
        residual_inf_norm_kn = math.inf
        constraint_residual_m2 = math.inf
        parent_binding = False
        monitor_direction = False
        commit_gate = False
        material_state_changed = False

        if vector_attempt.get("accepted") is True:
            vector_final = vector_result.final_checkpoint
            final_free = np.asarray(
                vector_final.free_displacements_m,
                dtype=np.float64,
            )
            final_assembly = step_problem.assemble(
                final_free,
                vector_final.load_factor,
            )
            residual_inf_norm_kn = float(
                np.linalg.norm(final_assembly.residual_kn, ord=np.inf)
            )
            displacement_increment = final_free - parent_free
            load_increment = vector_final.load_factor - parent.load_factor
            constraint_residual_m2 = float(
                np.dot(
                    metric_weights * displacement_increment,
                    displacement_increment,
                )
                + (config.load_factor_metric_scale_m * load_increment) ** 2
                - arc_length_attempted**2
            )
            parent_binding = bool(
                final_assembly.parent_checkpoint_hash == parent.state_hash
                and all(
                    row.response.parent_state_hash == state.state_hash
                    for row, state in zip(
                        final_assembly.member_assemblies,
                        parent.element_states,
                        strict=True,
                    )
                )
            )
            monitor_direction = bool(
                config.target_direction
                * displacement_increment[config.target_monitor_dof_index]
                > 0.0
            )
            vector_contract = bool(
                vector_result.status == "ready"
                and vector_result.metrics.get("contract_pass") is True
                and vector_result.metrics.get("fallback_count") == 0
                and vector_result.metrics.get("regularization_count") == 0
            )
            commit_gate = bool(
                vector_contract
                and parent_immutable
                and parent_binding
                and residual_inf_norm_kn <= config.residual_tolerance_kn
                and abs(constraint_residual_m2) <= config.constraint_tolerance_m2
                and monitor_direction
            )

        if commit_gate:
            assert final_assembly is not None
            vector_final = vector_result.final_checkpoint
            accepted = StatefulCorotationalFiberFrame2DCheckpoint(
                case_id=problem.case_id,
                problem_contract_hash=problem.contract_hash,
                epoch=parent.epoch + 1,
                step_index=parent.step_index + 1,
                load_factor=float(vector_final.load_factor),
                parent_state_hash=parent.state_hash,
                global_displacements=tuple(
                    float(value) for value in final_assembly.global_displacements
                ),
                element_states=final_assembly.trial_element_states,
            )
            validate_stateful_corotational_fiber_frame2d_checkpoint(
                problem,
                accepted,
            )
            previous_tangent_displacements = vector_final.previous_tangent_displacements
            previous_tangent_load_factor = vector_final.previous_tangent_load_factor
            material_state_changed = any(
                before.state_hash != after.state_hash
                for before, after in zip(
                    parent.element_states,
                    accepted.element_states,
                    strict=True,
                )
            )
            outcome = "committed"
            stop_reason = str(vector_attempt["stop_reason"])
            next_arc_length_m = arc_length_attempted
            rollback_exact = True
            equilibrium_constraint_gate = True
        else:
            accepted = parent
            next_arc_length_m = arc_length_attempted * config.failed_step_reduction
            current_arc_length_m = next_arc_length_m
            outcome = "rolled_back"
            stop_reason = (
                str(vector_attempt["stop_reason"])
                if vector_attempt.get("accepted") is False
                else "stateful_commit_gate_failed"
            )
            rollback_exact = bool(
                parent_immutable
                and accepted is parent
                and accepted.canonical_bytes() == parent_bytes
                and _element_state_bytes(accepted) == parent_element_bytes
            )
            equilibrium_constraint_gate = bool(
                vector_attempt.get("accepted") is False
                or (
                    residual_inf_norm_kn <= config.residual_tolerance_kn
                    and abs(constraint_residual_m2) <= config.constraint_tolerance_m2
                )
            )

        progress = _updated_progress(
            progress,
            parent=parent,
            accepted=accepted,
            vector_result=vector_result,
            final_assembly=final_assembly if commit_gate else None,
            committed=commit_gate,
            rollback_exact=rollback_exact,
            equilibrium_constraint_gate=equilibrium_constraint_gate,
            parent_binding_gate=(parent_binding if commit_gate else parent_immutable),
            parent_immutable_gate=parent_immutable,
            monitor_direction_gate=(monitor_direction if commit_gate else True),
            residual_inf_norm_kn=residual_inf_norm_kn,
            constraint_residual_m2=constraint_residual_m2,
        )
        boundary = create_stateful_corotational_fiber_frame2d_arc_length_checkpoint(
            problem,
            config,
            accepted_checkpoint=accepted,
            current_arc_length_m=next_arc_length_m,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
            progress=progress,
            last_attempt_outcome=outcome,
            last_attempt_stop_reason=stop_reason,
        )
        attempt = StatefulCorotationalFiberFrame2DArcLengthAttempt(
            attempt_index=progress.attempt_count,
            arc_length_m=arc_length_attempted,
            outcome=outcome,
            stop_reason=stop_reason,
            parent_checkpoint=parent,
            accepted_checkpoint=accepted,
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
        terminal_reason = "maximum_attempt_count_exhausted"

    target_reached = _target_reached(problem, accepted, config)
    if target_reached:
        terminal_reason = "target_monitor_displacement_reached"
    final_residual_inf_norm_kn = _checkpoint_residual_inf_norm_kn(problem, accepted)
    contract_pass = bool(
        target_reached
        and progress.accepted_step_count > 0
        and progress.dense_linear_solve_count > 0
        and progress.rollback_exact
        and progress.equilibrium_constraint_gate
        and progress.parent_binding_gate
        and progress.parent_immutable_gate
        and progress.monitor_direction_gate
        and progress.fallback_count == 0
        and progress.regularization_count == 0
        and progress.maximum_accepted_residual_inf_norm_kn
        <= config.residual_tolerance_kn
        and progress.maximum_accepted_constraint_residual_m2
        <= config.constraint_tolerance_m2
        and final_residual_inf_norm_kn <= config.residual_tolerance_kn
    )
    final_free = _free_generalized_coordinates(problem, accepted)
    metrics = {
        "contract_pass": contract_pass,
        "equation_count": len(problem.free_global_dofs),
        "target_monitor_displacement_reached": target_reached,
        "final_monitor_generalized_coordinate_m": float(
            final_free[config.target_monitor_dof_index]
        ),
        "final_load_factor": accepted.load_factor,
        **progress.to_dict(),
        "checkpoint_count": progress.attempt_count + 1,
        "run_attempt_count": len(attempts),
        "run_checkpoint_count": len(checkpoints),
        "final_residual_inf_norm_kn": final_residual_inf_norm_kn,
        "restart_checkpoint_consumed": restart_consumed,
        "material_state_commit_rollback": bool(
            progress.accepted_step_count > 0 and progress.rollback_exact
        ),
        "canonical_checkpoint_artifact_available": True,
        "corotational_checkpoint_artifact_available": True,
        "checkpoint_chain_replay_claim": False,
        "external_benchmark_acceptance_claim": False,
        "production_sparse_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "g1_full_building_closure_claim": False,
    }
    return StatefulCorotationalFiberFrame2DArcLengthResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        source_case_id=problem.case_id,
        source_problem_contract_hash=problem.contract_hash,
        path_contract_hash=path_hash,
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=checkpoints[-1],
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


def finite_difference_stateful_corotational_fiber_frame2d_arc_length_linearization_check(
    step_problem: StatefulCorotationalFiberFrame2DArcLengthStepProblem,
    *,
    free_displacements_m: Any,
    load_factor: float,
    direction_m: Any,
    displacement_epsilon_m: float = 1.0e-8,
    load_factor_epsilon: float = 1.0e-7,
    relative_tolerance: float = 2.0e-6,
) -> dict[str, Any]:
    """Check displacement and load derivatives from one immutable parent."""

    dimension = len(step_problem.problem.free_global_dofs)
    state = _finite_vector(
        free_displacements_m,
        path="free_displacements_m",
        dimension=dimension,
    )
    direction = _finite_vector(
        direction_m,
        path="direction_m",
        dimension=dimension,
    )
    if float(np.linalg.norm(direction, ord=np.inf)) <= 0.0:
        raise StatefulCorotationalFiberFrame2DArcLengthError(
            "direction_m must be nonzero"
        )
    displacement_epsilon = _finite_scalar(
        displacement_epsilon_m,
        path="displacement_epsilon_m",
        positive=True,
    )
    load_epsilon = _finite_scalar(
        load_factor_epsilon,
        path="load_factor_epsilon",
        positive=True,
    )
    tolerance = _finite_scalar(
        relative_tolerance,
        path="relative_tolerance",
        positive=True,
    )
    normalized_load = _finite_scalar(load_factor, path="load_factor")
    parent = step_problem.accepted_checkpoint
    parent_bytes = parent.canonical_bytes()
    center = step_problem.assemble(state, normalized_load)
    forward = step_problem.assemble(
        state + displacement_epsilon * direction,
        normalized_load,
    )
    backward = step_problem.assemble(
        state - displacement_epsilon * direction,
        normalized_load,
    )
    finite_difference_displacement = (forward.residual_kn - backward.residual_kn) / (
        2.0 * displacement_epsilon
    )
    analytic_displacement = center.jacobian_kn_per_m @ direction
    load_forward = step_problem.assemble(state, normalized_load + load_epsilon)
    load_backward = step_problem.assemble(state, normalized_load - load_epsilon)
    finite_difference_load = (load_forward.residual_kn - load_backward.residual_kn) / (
        2.0 * load_epsilon
    )
    analytic_load = -step_problem.reference_load_kn()
    displacement_error = float(
        np.linalg.norm(
            finite_difference_displacement - analytic_displacement,
            ord=np.inf,
        )
    )
    displacement_scale = max(
        float(np.linalg.norm(finite_difference_displacement, ord=np.inf)),
        float(np.linalg.norm(analytic_displacement, ord=np.inf)),
        1.0,
    )
    load_error = float(
        np.linalg.norm(finite_difference_load - analytic_load, ord=np.inf)
    )
    load_scale = max(
        float(np.linalg.norm(finite_difference_load, ord=np.inf)),
        float(np.linalg.norm(analytic_load, ord=np.inf)),
        1.0,
    )
    displacement_relative_error = displacement_error / displacement_scale
    load_relative_error = load_error / load_scale
    parent_immutable = bool(
        parent.canonical_bytes() == parent_bytes
        and parent.compute_state_hash() == parent.state_hash
        and all(
            row.parent_checkpoint_hash == parent.state_hash
            for row in (center, forward, backward, load_forward, load_backward)
        )
    )
    contract_pass = bool(
        parent_immutable
        and displacement_relative_error <= tolerance
        and load_relative_error <= tolerance
    )
    return {
        "contract_pass": contract_pass,
        "parent_checkpoint_hash": parent.state_hash,
        "same_immutable_parent": parent_immutable,
        "tangent_definition": "material_plus_geometric_consistent",
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "displacement_relative_error": displacement_relative_error,
        "load_factor_relative_error": load_relative_error,
        "relative_tolerance": tolerance,
        "analytic_displacement_directional_derivative_kn": (
            analytic_displacement.tolist()
        ),
        "finite_difference_displacement_directional_derivative_kn": (
            finite_difference_displacement.tolist()
        ),
        "analytic_load_factor_derivative_kn": analytic_load.tolist(),
        "finite_difference_load_factor_derivative_kn": (
            finite_difference_load.tolist()
        ),
    }


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_MAX_BYTES",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_PROFILE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ARC_LENGTH_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DArcLengthAttempt",
    "StatefulCorotationalFiberFrame2DArcLengthCheckpoint",
    "StatefulCorotationalFiberFrame2DArcLengthError",
    "StatefulCorotationalFiberFrame2DArcLengthProgress",
    "StatefulCorotationalFiberFrame2DArcLengthResult",
    "StatefulCorotationalFiberFrame2DArcLengthStepProblem",
    "create_stateful_corotational_fiber_frame2d_arc_length_checkpoint",
    "finite_difference_stateful_corotational_fiber_frame2d_arc_length_linearization_check",
    "load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes",
    "read_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact",
    "stateful_corotational_fiber_frame2d_arc_length_continuation",
    "stateful_corotational_fiber_frame2d_arc_length_path_contract_hash",
    "validate_stateful_corotational_fiber_frame2d_arc_length_checkpoint",
    "write_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact",
]
