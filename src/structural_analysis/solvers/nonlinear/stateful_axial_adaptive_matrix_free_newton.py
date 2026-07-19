"""Adaptive transactional material-state continuation and durable restart.

This module places an adaptive physical-load controller around the bounded
stateful axial matrix-free Newton step.  Every failed attempt must retain the
exact accepted displacement and constitutive-state bytes before the step size
is reduced.  Every attempt boundary can be persisted as canonical JSON bound
to the complete source problem, material parameters, path policy, and solver
configuration.

The implementation remains a local CPU axial-chain integration.  It does not
claim an arc-length branch, general frame/shell constitutive state, production
Krylov behavior, HIP parity, or full-building G1 closure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_axial import (
    ACCEPTED_STATE_SCHEMA_VERSION,
    StatefulAxialAcceptedState,
    StatefulAxialChainProblem,
    assemble_stateful_axial_chain,
    initial_stateful_axial_state,
    validate_stateful_axial_state,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LoadControlledMatrixFreeNewtonConfig,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    MatrixFreeCPUFGMRESConfig,
)
from structural_analysis.solvers.nonlinear.stateful_axial_matrix_free_newton import (
    StateTangentSolverFactory,
    StatefulAxialMatrixFreeLoadStepResult,
    StatefulAxialMatrixFreeNewtonError,
    _source_problem_contract_hash,
    solve_stateful_axial_matrix_free_load_step,
)


STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_SCHEMA_VERSION = (
    "stateful-axial-adaptive-matrix-free-newton.v1"
)
STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_PROFILE = (
    "adaptive-transactional-material-state-matrix-free-newton.v1"
)
STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-axial-adaptive-matrix-free-checkpoint.v1"
)
STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_FILENAME = (
    "stateful_axial_adaptive_checkpoint.json"
)
STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY = (
    "This controller retries failed physical load steps only after exact "
    "accepted displacement and material-state rollback, and persists every "
    "attempt boundary as canonical source-bound JSON. Committed steps retain "
    "the current-tangent, explicit linear-residual, nonlinear residual, "
    "increment, zero-fallback, and zero-regularization gates of the stateful "
    "axial matrix-free core. It is a bounded local CPU axial-chain path, not an "
    "arc-length branch, general frame/shell material solver, production Krylov "
    "or HIP result, or authoritative G1 full-building closure."
)


class StatefulAxialAdaptiveMatrixFreeNewtonError(StatefulAxialMatrixFreeNewtonError):
    """Fail-closed adaptive path or persisted-checkpoint contract error."""


def _default_step_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=1.0e-9,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-9,
        tangent_solve_residual_tolerance_inf_kn=1.0e-9,
        maximum_newton_iterations=8,
    )


def _finite_float(value: Any, *, path: str, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} must be a finite number"
        )
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} must be a finite number"
        ) from exc
    if not math.isfinite(normalized) or (positive and normalized <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(f"{path} must be {qualifier}")
    return normalized


def _nonnegative_int(value: Any, *, path: str) -> int:
    if type(value) is not int or value < 0:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} must be a nonnegative integer"
        )
    return value


def _require_hash(value: Any, *, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} must be a prefixed SHA-256 hash"
        )
    return value


def _expect_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} must be an object with string keys"
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
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} keys mismatch: missing={missing}, extra={extra}"
        )
    return payload


@dataclass(frozen=True)
class StatefulAxialAdaptiveMatrixFreeNewtonConfig:
    """Bounded monotone full-load continuation policy."""

    target_load_factor: float = 1.0
    initial_step_size: float = 1.0
    minimum_step_size: float = 0.125
    maximum_step_size: float = 1.0
    failed_step_reduction: float = 0.5
    fast_step_growth: float = 2.0
    fast_tangent_solve_threshold: int = 1
    maximum_attempt_count: int = 16
    step_config: LoadControlledMatrixFreeNewtonConfig = field(
        default_factory=_default_step_config
    )

    def __post_init__(self) -> None:
        for name in (
            "target_load_factor",
            "initial_step_size",
            "minimum_step_size",
            "maximum_step_size",
            "failed_step_reduction",
            "fast_step_growth",
        ):
            _finite_float(getattr(self, name), path=name, positive=True)
        if self.minimum_step_size > self.initial_step_size:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "minimum_step_size cannot exceed initial_step_size"
            )
        if self.initial_step_size > self.maximum_step_size:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "initial_step_size cannot exceed maximum_step_size"
            )
        if not 0.0 < self.failed_step_reduction < 1.0:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "failed_step_reduction must be between zero and one"
            )
        if self.fast_step_growth < 1.0:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "fast_step_growth must be at least one"
            )
        if (
            type(self.fast_tangent_solve_threshold) is not int
            or self.fast_tangent_solve_threshold < 0
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "fast_tangent_solve_threshold must be nonnegative"
            )
        if (
            type(self.maximum_attempt_count) is not int
            or self.maximum_attempt_count < 1
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "maximum_attempt_count must be positive"
            )
        if self.step_config.target_load_factors != (1.0,):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "step_config must target increment-space load factor (1.0,)"
            )

    def path_contract_payload(self) -> dict[str, Any]:
        return {
            "target_load_factor": self.target_load_factor,
            "initial_step_size": self.initial_step_size,
            "minimum_step_size": self.minimum_step_size,
            "maximum_step_size": self.maximum_step_size,
            "failed_step_reduction": self.failed_step_reduction,
            "fast_step_growth": self.fast_step_growth,
            "fast_tangent_solve_threshold": (self.fast_tangent_solve_threshold),
            "maximum_attempt_count": self.maximum_attempt_count,
            "step_config": self.step_config.path_contract_payload(),
            "accepted_trial_policy": (
                "immutable_material_parent_trial_then_atomic_commit"
            ),
            "failed_step_policy": (
                "exact_displacement_and_material_rollback_then_reduction"
            ),
            "checkpoint_policy": ("canonical_json_every_attempt_source_and_path_bound"),
        }


@dataclass(frozen=True)
class StatefulAxialAdaptiveProgress:
    """Cumulative path facts retained across durable restarts."""

    attempt_count: int = 0
    accepted_step_count: int = 0
    failed_step_count: int = 0
    failed_step_reduction_count: int = 0
    fast_step_growth_count: int = 0
    tangent_solve_count: int = 0
    accepted_matrix_free_newton_step_count: int = 0
    fallback_count: int = 0
    regularization_count: int = 0
    material_state_changed_step_count: int = 0
    maximum_line_search_backtrack_count: int = 0
    minimum_attempted_step_size: float = 0.0
    maximum_attempted_step_size: float = 0.0
    maximum_checkpoint_residual_inf_kn: float = 0.0
    rollback_exact: bool = True
    residual_and_increment_acceptance_gate: bool = True

    def __post_init__(self) -> None:
        integer_names = (
            "attempt_count",
            "accepted_step_count",
            "failed_step_count",
            "failed_step_reduction_count",
            "fast_step_growth_count",
            "tangent_solve_count",
            "accepted_matrix_free_newton_step_count",
            "fallback_count",
            "regularization_count",
            "material_state_changed_step_count",
            "maximum_line_search_backtrack_count",
        )
        for name in integer_names:
            _nonnegative_int(getattr(self, name), path=f"progress.{name}")
        for name in (
            "minimum_attempted_step_size",
            "maximum_attempted_step_size",
            "maximum_checkpoint_residual_inf_kn",
        ):
            value = _finite_float(getattr(self, name), path=f"progress.{name}")
            if value < 0.0:
                raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                    f"progress.{name} must be nonnegative"
                )
        for name in (
            "rollback_exact",
            "residual_and_increment_acceptance_gate",
        ):
            if type(getattr(self, name)) is not bool:
                raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                    f"progress.{name} must be boolean"
                )
        if self.accepted_step_count + self.failed_step_count != self.attempt_count:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "progress accepted and failed counts must equal attempt_count"
            )
        if self.failed_step_reduction_count != self.failed_step_count:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "every failed step must have one reduction"
            )
        if self.fast_step_growth_count > self.accepted_step_count:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "fast_step_growth_count exceeds accepted_step_count"
            )
        if self.accepted_matrix_free_newton_step_count > self.accepted_step_count:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "matrix-free Newton step count exceeds accepted_step_count"
            )
        if self.attempt_count == 0 and (
            self.minimum_attempted_step_size != 0.0
            or self.maximum_attempted_step_size != 0.0
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "empty progress must have zero attempted step-size bounds"
            )
        if (
            self.attempt_count > 0
            and self.minimum_attempted_step_size > self.maximum_attempted_step_size
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "progress attempted step-size bounds are inverted"
            )

    def to_dict(self) -> dict[str, Any]:
        return {row.name: getattr(self, row.name) for row in fields(type(self))}

    @classmethod
    def from_dict(cls, value: Any) -> StatefulAxialAdaptiveProgress:
        expected = {row.name for row in fields(cls)}
        payload = _expect_exact_keys(
            value,
            path="/boundary/progress",
            expected=expected,
        )
        integer_names = {
            "attempt_count",
            "accepted_step_count",
            "failed_step_count",
            "failed_step_reduction_count",
            "fast_step_growth_count",
            "tangent_solve_count",
            "accepted_matrix_free_newton_step_count",
            "fallback_count",
            "regularization_count",
            "material_state_changed_step_count",
            "maximum_line_search_backtrack_count",
        }
        bool_names = {
            "rollback_exact",
            "residual_and_increment_acceptance_gate",
        }
        normalized: dict[str, Any] = {}
        for name in expected:
            if name in integer_names:
                normalized[name] = _nonnegative_int(
                    payload[name], path=f"/boundary/progress/{name}"
                )
            elif name in bool_names:
                if type(payload[name]) is not bool:
                    raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                        f"/boundary/progress/{name} must be boolean"
                    )
                normalized[name] = payload[name]
            else:
                normalized[name] = _finite_float(
                    payload[name], path=f"/boundary/progress/{name}"
                )
        return cls(**normalized)


def _solver_contract_payload(
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None,
    solver_factory_contract_hash: str | None,
) -> dict[str, Any]:
    if solver_factory_contract_hash is not None:
        if solver_config is not None:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "solver_config cannot be combined with a custom solver factory"
            )
        return {
            "mode": "custom_state_tangent_solver_factory",
            "factory_contract_hash": _require_hash(
                solver_factory_contract_hash,
                path="solver_factory_contract_hash",
            ),
        }
    normalized = solver_config or MatrixFreeCPUFGMRESConfig()
    return {
        "mode": "default_matrix_free_cpu_fgmres",
        "config": normalized.contract_payload(),
    }


def stateful_axial_adaptive_path_contract_hash(
    problem: StatefulAxialChainProblem,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory_contract_hash: str | None = None,
) -> str:
    """Hash source, adaptive policy, inner Newton, and tangent-solver policy."""

    return canonical_hash(
        {
            "profile": STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_PROFILE,
            "source_case_id": problem.case_id,
            "source_problem_contract_hash": (_source_problem_contract_hash(problem)),
            "config": config.path_contract_payload(),
            "solver": _solver_contract_payload(
                solver_config=solver_config,
                solver_factory_contract_hash=solver_factory_contract_hash,
            ),
        }
    )


def _checkpoint_hash_payload(
    *,
    source_case_id: str,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_state: StatefulAxialAcceptedState,
    next_step_size: float,
    progress: StatefulAxialAdaptiveProgress,
) -> dict[str, Any]:
    return {
        "schema_version": (
            STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION
        ),
        "source": {
            "case_id": source_case_id,
            "problem_contract_hash": source_problem_contract_hash,
        },
        "path_contract_hash": path_contract_hash,
        "boundary": {
            "accepted_state": accepted_state.to_dict(),
            "next_step_size": next_step_size,
            "progress": progress.to_dict(),
        },
    }


@dataclass(frozen=True)
class StatefulAxialAdaptiveMatrixFreeCheckpoint:
    """Canonical persisted attempt boundary including material state."""

    schema_version: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    accepted_state: StatefulAxialAcceptedState
    next_step_size: float
    progress: StatefulAxialAdaptiveProgress
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "checkpoint schema_version is invalid"
            )
        if not str(self.source_case_id).strip():
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "checkpoint source_case_id is required"
            )
        _require_hash(
            self.source_problem_contract_hash,
            path="checkpoint.source_problem_contract_hash",
        )
        _require_hash(
            self.path_contract_hash,
            path="checkpoint.path_contract_hash",
        )
        step_size = _finite_float(
            self.next_step_size,
            path="checkpoint.next_step_size",
            positive=True,
        )
        object.__setattr__(self, "next_step_size", step_size)
        payload = _checkpoint_hash_payload(
            source_case_id=self.source_case_id,
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_state=self.accepted_state,
            next_step_size=step_size,
            progress=self.progress,
        )
        computed = canonical_hash(payload)
        if self.checkpoint_hash and self.checkpoint_hash != computed:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError("checkpoint_hash mismatch")
        if not self.checkpoint_hash:
            object.__setattr__(self, "checkpoint_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        payload = _checkpoint_hash_payload(
            source_case_id=self.source_case_id,
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_state=self.accepted_state,
            next_step_size=self.next_step_size,
            progress=self.progress,
        )
        payload["checkpoint_hash"] = self.checkpoint_hash
        return payload

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def descriptor(self) -> dict[str, Any]:
        raw = self.to_bytes()
        return {
            "schema_version": self.schema_version,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": (self.source_problem_contract_hash),
            "path_contract_hash": self.path_contract_hash,
            "accepted_step_index": self.accepted_state.step_index,
            "accepted_load_factor": self.accepted_state.load_factor,
            "accepted_state_hash": self.accepted_state.state_hash,
            "next_step_size": self.next_step_size,
            "progress": self.progress.to_dict(),
            "checkpoint_hash": self.checkpoint_hash,
            "artifact_byte_length": len(raw),
            "artifact_data_hash": sha256_prefixed(raw),
        }


def _accepted_state_residual_inf_kn(
    problem: StatefulAxialChainProblem,
    state: StatefulAxialAcceptedState,
) -> float:
    free = np.asarray(state.displacements_m, dtype=np.float64)[
        list(problem.free_node_indices)
    ]
    assembly = assemble_stateful_axial_chain(
        problem,
        state,
        target_load_factor=state.load_factor,
        trial_free_displacements_m=free,
    )
    return float(np.linalg.norm(assembly.residual_kn, ord=np.inf))


def validate_stateful_axial_adaptive_matrix_free_checkpoint(
    checkpoint: StatefulAxialAdaptiveMatrixFreeCheckpoint,
    problem: StatefulAxialChainProblem,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialAdaptiveMatrixFreeCheckpoint:
    """Validate a checkpoint against explicit source and path contracts."""

    if type(checkpoint) is not StatefulAxialAdaptiveMatrixFreeCheckpoint:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError("checkpoint type is invalid")
    expected_source_hash = _source_problem_contract_hash(problem)
    expected_path_hash = stateful_axial_adaptive_path_contract_hash(
        problem,
        config,
        solver_config=solver_config,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )
    if checkpoint.source_case_id != problem.case_id:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint source case_id mismatch"
        )
    if checkpoint.source_problem_contract_hash != expected_source_hash:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint source problem contract mismatch"
        )
    if checkpoint.path_contract_hash != expected_path_hash:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint path contract mismatch"
        )
    validate_stateful_axial_state(problem, checkpoint.accepted_state)
    load_tolerance = _load_tolerance(config.target_load_factor)
    if not (
        -load_tolerance
        <= checkpoint.accepted_state.load_factor
        <= config.target_load_factor + load_tolerance
    ):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint accepted load factor is outside the path"
        )
    if checkpoint.next_step_size > config.maximum_step_size + load_tolerance:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint next_step_size exceeds maximum_step_size"
        )
    if checkpoint.progress.attempt_count > config.maximum_attempt_count:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint attempt_count exceeds maximum_attempt_count"
        )
    residual = _accepted_state_residual_inf_kn(problem, checkpoint.accepted_state)
    residual_tolerance = config.step_config.residual_tolerance_inf_kn
    if residual > residual_tolerance:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint accepted state is not in equilibrium"
        )
    if (
        residual
        > checkpoint.progress.maximum_checkpoint_residual_inf_kn
        + 16.0 * np.finfo(np.float64).eps
    ):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint progress omits the accepted residual"
        )
    return checkpoint


def create_stateful_axial_adaptive_matrix_free_checkpoint(
    problem: StatefulAxialChainProblem,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    *,
    accepted_state: StatefulAxialAcceptedState,
    next_step_size: float,
    progress: StatefulAxialAdaptiveProgress,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialAdaptiveMatrixFreeCheckpoint:
    """Create a source-bound checkpoint from one accepted attempt boundary."""

    checkpoint = StatefulAxialAdaptiveMatrixFreeCheckpoint(
        schema_version=(STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION),
        source_case_id=problem.case_id,
        source_problem_contract_hash=(_source_problem_contract_hash(problem)),
        path_contract_hash=stateful_axial_adaptive_path_contract_hash(
            problem,
            config,
            solver_config=solver_config,
            solver_factory_contract_hash=solver_factory_contract_hash,
        ),
        accepted_state=accepted_state,
        next_step_size=next_step_size,
        progress=progress,
    )
    return validate_stateful_axial_adaptive_matrix_free_checkpoint(
        checkpoint,
        problem,
        config,
        solver_config=solver_config,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )


def _restore_material_state(
    template: Any,
    value: Any,
    *,
    path: str,
) -> Any:
    if not is_dataclass(template) or isinstance(template, type):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} material state template must be a dataclass instance"
        )
    to_dict = getattr(template, "to_dict", None)
    if not callable(to_dict):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} material state template must expose to_dict()"
        )
    expected_payload = to_dict()
    payload = _expect_exact_keys(
        value,
        path=path,
        expected=set(expected_payload),
    )
    if payload.get("schema_version") != expected_payload.get("schema_version"):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path}/schema_version does not match the problem material state"
        )
    values: dict[str, Any] = {}
    for row in fields(template):
        child_path = f"{path}/{row.name}"
        current = getattr(template, row.name)
        raw = payload[row.name]
        if is_dataclass(current) and not isinstance(current, type):
            values[row.name] = _restore_material_state(
                current,
                raw,
                path=child_path,
            )
        elif isinstance(current, float):
            values[row.name] = _finite_float(raw, path=child_path)
        elif isinstance(current, bool):
            if type(raw) is not bool:
                raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                    f"{child_path} must be boolean"
                )
            values[row.name] = raw
        elif isinstance(current, int):
            values[row.name] = _nonnegative_int(raw, path=child_path)
        elif isinstance(current, str):
            if not isinstance(raw, str):
                raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                    f"{child_path} must be text"
                )
            values[row.name] = raw
        else:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                f"{child_path} has an unsupported material-state field type"
            )
    try:
        restored = type(template)(**values)
    except (TypeError, ValueError) as exc:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} material state is invalid"
        ) from exc
    if canonical_json_bytes(restored.to_dict()) != canonical_json_bytes(payload):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            f"{path} material state hash or canonical values mismatch"
        )
    return restored


def _restore_accepted_state(
    problem: StatefulAxialChainProblem,
    value: Any,
) -> StatefulAxialAcceptedState:
    payload = _expect_exact_keys(
        value,
        path="/boundary/accepted_state",
        expected={
            "schema_version",
            "case_id",
            "step_index",
            "load_factor",
            "displacements_m",
            "material_states",
            "state_hash",
        },
    )
    if payload["schema_version"] != ACCEPTED_STATE_SCHEMA_VERSION:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "/boundary/accepted_state/schema_version is invalid"
        )
    if payload["case_id"] != problem.case_id:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "/boundary/accepted_state/case_id does not match the problem"
        )
    displacement_values = payload["displacements_m"]
    material_values = payload["material_states"]
    if not isinstance(displacement_values, list):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "/boundary/accepted_state/displacements_m must be an array"
        )
    if not isinstance(material_values, list):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "/boundary/accepted_state/material_states must be an array"
        )
    if len(displacement_values) != problem.node_count:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint displacement count does not match the problem"
        )
    if len(material_values) != len(problem.elements):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint material-state count does not match the problem"
        )
    material_states = tuple(
        _restore_material_state(
            element.material.initial_state(),
            material_value,
            path=f"/boundary/accepted_state/material_states/{index}",
        )
        for index, (element, material_value) in enumerate(
            zip(problem.elements, material_values, strict=True)
        )
    )
    try:
        restored = StatefulAxialAcceptedState(
            case_id=problem.case_id,
            step_index=_nonnegative_int(
                payload["step_index"],
                path="/boundary/accepted_state/step_index",
            ),
            load_factor=_finite_float(
                payload["load_factor"],
                path="/boundary/accepted_state/load_factor",
            ),
            displacements_m=tuple(
                _finite_float(
                    value,
                    path=(f"/boundary/accepted_state/displacements_m/{index}"),
                )
                for index, value in enumerate(displacement_values)
            ),
            material_states=material_states,
            state_hash=_require_hash(
                payload["state_hash"],
                path="/boundary/accepted_state/state_hash",
            ),
        )
        validate_stateful_axial_state(problem, restored)
    except ValueError as exc:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "/boundary/accepted_state is invalid"
        ) from exc
    if canonical_json_bytes(restored.to_dict()) != canonical_json_bytes(payload):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "accepted state hash or canonical values mismatch"
        )
    return restored


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                f"checkpoint JSON contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
    data: bytes | bytearray | memoryview,
    problem: StatefulAxialChainProblem,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialAdaptiveMatrixFreeCheckpoint:
    """Load canonical checkpoint bytes against explicit source inputs."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact must be bytes"
        )
    raw = bytes(data)
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                StatefulAxialAdaptiveMatrixFreeNewtonError(
                    f"checkpoint JSON contains non-finite token {value}"
                )
            ),
        )
    except StatefulAxialAdaptiveMatrixFreeNewtonError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact is not valid UTF-8 JSON"
        ) from exc
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
    if canonical_json_bytes(payload) != raw:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact is not canonical JSON"
        )
    if (
        payload["schema_version"]
        != STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION
    ):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact schema_version is invalid"
        )
    source = _expect_exact_keys(
        payload["source"],
        path="/source",
        expected={"case_id", "problem_contract_hash"},
    )
    boundary = _expect_exact_keys(
        payload["boundary"],
        path="/boundary",
        expected={"accepted_state", "next_step_size", "progress"},
    )
    if not isinstance(source["case_id"], str):
        raise StatefulAxialAdaptiveMatrixFreeNewtonError("/source/case_id must be text")
    checkpoint = StatefulAxialAdaptiveMatrixFreeCheckpoint(
        schema_version=payload["schema_version"],
        source_case_id=source["case_id"],
        source_problem_contract_hash=_require_hash(
            source["problem_contract_hash"],
            path="/source/problem_contract_hash",
        ),
        path_contract_hash=_require_hash(
            payload["path_contract_hash"],
            path="/path_contract_hash",
        ),
        accepted_state=_restore_accepted_state(
            problem,
            boundary["accepted_state"],
        ),
        next_step_size=_finite_float(
            boundary["next_step_size"],
            path="/boundary/next_step_size",
            positive=True,
        ),
        progress=StatefulAxialAdaptiveProgress.from_dict(boundary["progress"]),
        checkpoint_hash=_require_hash(
            payload["checkpoint_hash"],
            path="/checkpoint_hash",
        ),
    )
    validate_stateful_axial_adaptive_matrix_free_checkpoint(
        checkpoint,
        problem,
        config,
        solver_config=solver_config,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )
    if checkpoint.to_bytes() != raw:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact round-trip mismatch"
        )
    return checkpoint


def write_stateful_axial_adaptive_matrix_free_checkpoint_artifact(
    checkpoint: StatefulAxialAdaptiveMatrixFreeCheckpoint,
    target: str | Path,
) -> Path:
    """Write exact checkpoint bytes once; existing targets fail closed."""

    if type(checkpoint) is not StatefulAxialAdaptiveMatrixFreeCheckpoint:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError("checkpoint type is invalid")
    path = Path(target)
    try:
        with path.open("xb") as stream:
            stream.write(checkpoint.to_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "checkpoint artifact target already exists"
        ) from exc
    return path


def read_stateful_axial_adaptive_matrix_free_checkpoint_artifact(
    source: str | Path,
    problem: StatefulAxialChainProblem,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    *,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialAdaptiveMatrixFreeCheckpoint:
    """Read and source-validate one persisted checkpoint artifact."""

    return load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
        Path(source).read_bytes(),
        problem,
        config,
        solver_config=solver_config,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )


@dataclass(frozen=True)
class StatefulAxialAdaptiveMatrixFreeAttempt:
    attempt_index: int
    attempted_step_size: float
    accepted_load_factor_before: float
    target_load_factor: float
    outcome: str
    step_reduced: bool
    step_grew: bool
    next_step_size: float
    resulting_checkpoint_hash: str
    step_result: StatefulAxialMatrixFreeLoadStepResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "attempted_step_size": self.attempted_step_size,
            "accepted_load_factor_before": self.accepted_load_factor_before,
            "target_load_factor": self.target_load_factor,
            "outcome": self.outcome,
            "step_reduced": self.step_reduced,
            "step_grew": self.step_grew,
            "next_step_size": self.next_step_size,
            "resulting_checkpoint_hash": self.resulting_checkpoint_hash,
            "step_result": self.step_result.to_dict(),
        }


@dataclass(frozen=True)
class StatefulAxialAdaptiveMatrixFreeNewtonResult:
    status: str
    terminal_reason: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig
    initial_checkpoint: StatefulAxialAdaptiveMatrixFreeCheckpoint
    final_checkpoint: StatefulAxialAdaptiveMatrixFreeCheckpoint
    checkpoints: tuple[StatefulAxialAdaptiveMatrixFreeCheckpoint, ...]
    attempts: tuple[StatefulAxialAdaptiveMatrixFreeAttempt, ...]
    metrics: dict[str, Any]

    @property
    def final_state(self) -> StatefulAxialAcceptedState:
        return self.final_checkpoint.accepted_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_SCHEMA_VERSION
            ),
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "profile": STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_PROFILE,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": (self.source_problem_contract_hash),
            "path_contract_hash": self.path_contract_hash,
            "config": self.config.path_contract_payload(),
            "initial_checkpoint": self.initial_checkpoint.descriptor(),
            "final_checkpoint": self.final_checkpoint.descriptor(),
            "checkpoints": [row.descriptor() for row in self.checkpoints],
            "attempts": [row.to_dict() for row in self.attempts],
            "metrics": dict(self.metrics),
            "claims": {
                "adaptive_stateful_axial_matrix_free_newton_path": bool(
                    self.metrics["contract_pass"]
                    and self.metrics["accepted_step_count"] > 0
                ),
                "consistent_matrix_free_newton_step_executed": bool(
                    self.metrics["accepted_matrix_free_newton_step_count"] > 0
                ),
                "material_state_commit_rollback": bool(self.metrics["contract_pass"]),
                "failed_step_reduction_exercised": bool(
                    self.metrics["failed_step_reduction_count"] > 0
                ),
                "failed_step_material_state_rollback_exact": bool(
                    self.metrics["failed_step_count"] > 0
                    and self.metrics["rollback_exact"]
                ),
                "source_bound_canonical_checkpoint": True,
                "checkpoint_restart_consumed": bool(
                    self.metrics["restart_checkpoint_consumed"]
                ),
                "arc_length_branch": False,
                "general_frame_shell_material_newton": False,
                "production_matrix_free_krylov": False,
                "rocm_hip_parity": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": (
                STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY
            ),
        }


def _load_tolerance(target_load_factor: float) -> float:
    return float(16.0 * np.finfo(np.float64).eps * max(1.0, abs(target_load_factor)))


def _updated_progress(
    progress: StatefulAxialAdaptiveProgress,
    *,
    step_result: StatefulAxialMatrixFreeLoadStepResult,
    attempted_step_size: float,
    accepted: bool,
    step_grew: bool,
    checkpoint_residual_inf_kn: float,
) -> StatefulAxialAdaptiveProgress:
    tangent_solve_count = int(step_result.metrics["tangent_solve_count"])
    if progress.attempt_count == 0:
        minimum_step = attempted_step_size
        maximum_step = attempted_step_size
    else:
        minimum_step = min(
            progress.minimum_attempted_step_size,
            attempted_step_size,
        )
        maximum_step = max(
            progress.maximum_attempted_step_size,
            attempted_step_size,
        )
    return replace(
        progress,
        attempt_count=progress.attempt_count + 1,
        accepted_step_count=(progress.accepted_step_count + int(accepted)),
        failed_step_count=progress.failed_step_count + int(not accepted),
        failed_step_reduction_count=(
            progress.failed_step_reduction_count + int(not accepted)
        ),
        fast_step_growth_count=(progress.fast_step_growth_count + int(step_grew)),
        tangent_solve_count=(progress.tangent_solve_count + tangent_solve_count),
        accepted_matrix_free_newton_step_count=(
            progress.accepted_matrix_free_newton_step_count
            + int(accepted and tangent_solve_count > 0)
        ),
        fallback_count=(
            progress.fallback_count + int(step_result.metrics["fallback_count"])
        ),
        regularization_count=(
            progress.regularization_count
            + int(step_result.metrics["regularization_count"])
        ),
        material_state_changed_step_count=(
            progress.material_state_changed_step_count
            + int(accepted and step_result.metrics["material_state_changed"])
        ),
        maximum_line_search_backtrack_count=max(
            progress.maximum_line_search_backtrack_count,
            int(step_result.metrics["maximum_line_search_backtrack_count"]),
        ),
        minimum_attempted_step_size=minimum_step,
        maximum_attempted_step_size=maximum_step,
        maximum_checkpoint_residual_inf_kn=max(
            progress.maximum_checkpoint_residual_inf_kn,
            checkpoint_residual_inf_kn,
        ),
        rollback_exact=bool(
            progress.rollback_exact
            and (accepted or step_result.metrics["rollback_exact"] is True)
        ),
        residual_and_increment_acceptance_gate=bool(
            progress.residual_and_increment_acceptance_gate
            and (
                not accepted
                or step_result.metrics["residual_and_increment_acceptance_gate"]
            )
        ),
    )


def adaptive_stateful_axial_matrix_free_newton_continuation(
    problem: StatefulAxialChainProblem,
    *,
    config: StatefulAxialAdaptiveMatrixFreeNewtonConfig | None = None,
    initial_state: StatefulAxialAcceptedState | None = None,
    checkpoint: StatefulAxialAdaptiveMatrixFreeCheckpoint | None = None,
    solver_config: MatrixFreeCPUFGMRESConfig | None = None,
    solver_factory: StateTangentSolverFactory | None = None,
    solver_factory_contract_hash: str | None = None,
) -> StatefulAxialAdaptiveMatrixFreeNewtonResult:
    """Run adaptive physical load steps with transactional material state."""

    normalized_config = config or StatefulAxialAdaptiveMatrixFreeNewtonConfig()
    if initial_state is not None and checkpoint is not None:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "initial_state cannot be combined with checkpoint"
        )
    if solver_factory is None and solver_factory_contract_hash is not None:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "solver_factory_contract_hash requires solver_factory"
        )
    if solver_factory is not None and solver_factory_contract_hash is None:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "custom solver_factory requires solver_factory_contract_hash"
        )
    if solver_factory is not None and solver_config is not None:
        raise StatefulAxialAdaptiveMatrixFreeNewtonError(
            "solver_config cannot be combined with solver_factory"
        )
    path_contract_hash = stateful_axial_adaptive_path_contract_hash(
        problem,
        normalized_config,
        solver_config=solver_config,
        solver_factory_contract_hash=solver_factory_contract_hash,
    )
    source_hash = _source_problem_contract_hash(problem)
    load_tolerance = _load_tolerance(normalized_config.target_load_factor)

    if checkpoint is not None:
        accepted_checkpoint = validate_stateful_axial_adaptive_matrix_free_checkpoint(
            checkpoint,
            problem,
            normalized_config,
            solver_config=solver_config,
            solver_factory_contract_hash=solver_factory_contract_hash,
        )
        accepted = accepted_checkpoint.accepted_state
        progress = accepted_checkpoint.progress
        step_size = accepted_checkpoint.next_step_size
        restart_consumed = True
    else:
        accepted = initial_state or initial_stateful_axial_state(problem)
        validate_stateful_axial_state(problem, accepted)
        if not (
            -load_tolerance
            <= accepted.load_factor
            <= normalized_config.target_load_factor + load_tolerance
        ):
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "initial accepted load factor is outside the adaptive path"
            )
        initial_residual = _accepted_state_residual_inf_kn(problem, accepted)
        if initial_residual > normalized_config.step_config.residual_tolerance_inf_kn:
            raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                "initial accepted state is not in equilibrium"
            )
        progress = StatefulAxialAdaptiveProgress(
            maximum_checkpoint_residual_inf_kn=initial_residual
        )
        step_size = min(
            normalized_config.initial_step_size,
            normalized_config.maximum_step_size,
        )
        accepted_checkpoint = create_stateful_axial_adaptive_matrix_free_checkpoint(
            problem,
            normalized_config,
            accepted_state=accepted,
            next_step_size=step_size,
            progress=progress,
            solver_config=solver_config,
            solver_factory_contract_hash=solver_factory_contract_hash,
        )
        restart_consumed = False

    initial_checkpoint = accepted_checkpoint
    checkpoints = [accepted_checkpoint]
    attempts: list[StatefulAxialAdaptiveMatrixFreeAttempt] = []
    terminal_reason = "maximum_attempt_count_exhausted"

    while progress.attempt_count < normalized_config.maximum_attempt_count:
        remaining = normalized_config.target_load_factor - accepted.load_factor
        if remaining <= load_tolerance:
            terminal_reason = "target_load_factor_reached"
            break
        if step_size + load_tolerance < normalized_config.minimum_step_size:
            terminal_reason = "minimum_step_size_exhausted"
            break
        attempted_step_size = min(step_size, remaining)
        target_load_factor = min(
            normalized_config.target_load_factor,
            accepted.load_factor + attempted_step_size,
        )
        accepted_before = accepted
        parent_bytes_before = accepted_before.canonical_bytes()
        material_bytes_before = tuple(
            state.canonical_bytes() for state in accepted_before.material_states
        )
        step_result = solve_stateful_axial_matrix_free_load_step(
            problem,
            accepted_before,
            target_load_factor=target_load_factor,
            config=normalized_config.step_config,
            solver_config=solver_config,
            solver_factory=solver_factory,
        )
        accepted_step = bool(step_result.committed)
        if accepted_step:
            accepted = step_result.accepted_state
            remaining_after = (
                normalized_config.target_load_factor - accepted.load_factor
            )
            step_grew = bool(
                step_result.metrics["tangent_solve_count"]
                <= normalized_config.fast_tangent_solve_threshold
                and remaining_after > load_tolerance
            )
            if step_grew:
                next_step_size = min(
                    normalized_config.maximum_step_size,
                    attempted_step_size * normalized_config.fast_step_growth,
                )
            else:
                next_step_size = attempted_step_size
            outcome = "committed"
            step_reduced = False
        else:
            rollback_exact = bool(
                step_result.accepted_state is accepted_before
                and step_result.metrics["rollback_exact"] is True
                and accepted_before.canonical_bytes() == parent_bytes_before
                and tuple(
                    state.canonical_bytes() for state in accepted_before.material_states
                )
                == material_bytes_before
            )
            if not rollback_exact:
                raise StatefulAxialAdaptiveMatrixFreeNewtonError(
                    "failed adaptive step did not preserve material-state bytes"
                )
            accepted = accepted_before
            next_step_size = (
                attempted_step_size * normalized_config.failed_step_reduction
            )
            step_grew = False
            outcome = "rolled_back"
            step_reduced = True

        checkpoint_residual = _accepted_state_residual_inf_kn(problem, accepted)
        progress = _updated_progress(
            progress,
            step_result=step_result,
            attempted_step_size=attempted_step_size,
            accepted=accepted_step,
            step_grew=step_grew,
            checkpoint_residual_inf_kn=checkpoint_residual,
        )
        accepted_checkpoint = create_stateful_axial_adaptive_matrix_free_checkpoint(
            problem,
            normalized_config,
            accepted_state=accepted,
            next_step_size=next_step_size,
            progress=progress,
            solver_config=solver_config,
            solver_factory_contract_hash=solver_factory_contract_hash,
        )
        checkpoints.append(accepted_checkpoint)
        attempts.append(
            StatefulAxialAdaptiveMatrixFreeAttempt(
                attempt_index=progress.attempt_count,
                attempted_step_size=float(attempted_step_size),
                accepted_load_factor_before=float(accepted_before.load_factor),
                target_load_factor=float(target_load_factor),
                outcome=outcome,
                step_reduced=step_reduced,
                step_grew=step_grew,
                next_step_size=float(next_step_size),
                resulting_checkpoint_hash=(accepted_checkpoint.checkpoint_hash),
                step_result=step_result,
            )
        )
        step_size = next_step_size
        if not accepted_step and (
            step_size + load_tolerance < normalized_config.minimum_step_size
        ):
            terminal_reason = "minimum_step_size_exhausted"
            break
    else:
        terminal_reason = "maximum_attempt_count_exhausted"

    target_reached = bool(
        abs(accepted.load_factor - normalized_config.target_load_factor)
        <= load_tolerance
    )
    if target_reached:
        terminal_reason = "target_load_factor_reached"
    final_residual = _accepted_state_residual_inf_kn(problem, accepted)
    contract_pass = bool(
        target_reached
        and final_residual <= normalized_config.step_config.residual_tolerance_inf_kn
        and progress.maximum_checkpoint_residual_inf_kn
        <= normalized_config.step_config.residual_tolerance_inf_kn
        and progress.rollback_exact
        and progress.residual_and_increment_acceptance_gate
        and progress.fallback_count == 0
        and progress.regularization_count == 0
    )
    metrics = {
        "contract_pass": contract_pass,
        "target_load_factor": normalized_config.target_load_factor,
        "final_load_factor": accepted.load_factor,
        "target_load_factor_reached": target_reached,
        **progress.to_dict(),
        "checkpoint_count": progress.attempt_count + 1,
        "run_attempt_count": len(attempts),
        "run_checkpoint_count": len(checkpoints),
        "final_residual_inf_kn": final_residual,
        "restart_checkpoint_consumed": restart_consumed,
        "canonical_checkpoint_artifact_available": True,
        "production_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "g1_full_building_closure_claim": False,
    }
    return StatefulAxialAdaptiveMatrixFreeNewtonResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        source_case_id=problem.case_id,
        source_problem_contract_hash=source_hash,
        path_contract_hash=path_contract_hash,
        config=normalized_config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=checkpoints[-1],
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


__all__ = [
    "STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_FILENAME",
    "STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY",
    "STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_PROFILE",
    "STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_NEWTON_SCHEMA_VERSION",
    "StatefulAxialAdaptiveMatrixFreeAttempt",
    "StatefulAxialAdaptiveMatrixFreeCheckpoint",
    "StatefulAxialAdaptiveMatrixFreeNewtonConfig",
    "StatefulAxialAdaptiveMatrixFreeNewtonError",
    "StatefulAxialAdaptiveMatrixFreeNewtonResult",
    "StatefulAxialAdaptiveProgress",
    "adaptive_stateful_axial_matrix_free_newton_continuation",
    "create_stateful_axial_adaptive_matrix_free_checkpoint",
    "load_stateful_axial_adaptive_matrix_free_checkpoint_bytes",
    "read_stateful_axial_adaptive_matrix_free_checkpoint_artifact",
    "stateful_axial_adaptive_path_contract_hash",
    "validate_stateful_axial_adaptive_matrix_free_checkpoint",
    "write_stateful_axial_adaptive_matrix_free_checkpoint_artifact",
]
