"""Adaptive load continuation for the stateful corotational 2D fiber frame."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadStepResult,
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-adaptive-continuation.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-adaptive-checkpoint.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_PROFILE = (
    "dense-corotational-fiber-frame2d-consistent-newton-adaptive-load.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_MAX_BYTES = 8 * 1024 * 1024
STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CLAIM_BOUNDARY = (
    "This contract verifies bounded monotone load-factor continuation for the "
    "dense stateful corotational 2D fiber frame. It uses the existing "
    "material-plus-geometric consistent Newton step, exact failed-step "
    "rollback, deterministic cutback and fast-step growth, and source/path-"
    "bound canonical checkpoints that persist the full corotational, section, "
    "and material state plus the next step size and cumulative progress. It "
    "does not provide displacement control, arc length, follower loads, a "
    "general material codec registry, checkpoint-chain replay, production "
    "sparse or ROCm/HIP execution, external benchmark acceptance, full-"
    "building equilibrium, G1 closure, or commercial readiness."
)


class StatefulCorotationalFiberFrame2DAdaptiveError(ValueError):
    """Fail-closed adaptive configuration or checkpoint error."""


def _finite_float(value: Any, *, path: str, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(f"{path} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            f"{path} must be finite"
        ) from exc
    if not math.isfinite(normalized):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(f"{path} must be finite")
    if positive and normalized <= 0.0:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(f"{path} must be positive")
    return normalized


def _nonnegative_int(value: Any, *, path: str) -> int:
    if type(value) is not int or value < 0:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
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
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            f"{path} must be a lowercase sha256 digest"
        )
    return normalized


def _expect_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(f"{path} must be an object")
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
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            f"{path} keys mismatch: missing={missing}, extra={extra}"
        )
    return payload


def _artifact_json_bytes(payload: Any) -> bytes:
    """Canonical JSON that deliberately preserves the sign of binary64 zero."""

    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint contains a non-JSON or non-finite value"
        ) from exc


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                f"adaptive checkpoint JSON contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise StatefulCorotationalFiberFrame2DAdaptiveError(
        f"adaptive checkpoint JSON contains non-finite token {value}"
    )


def _newton_config_payload(config: NewtonRaphsonConfig) -> dict[str, Any]:
    return {
        "residual_tolerance": config.residual_tolerance,
        "increment_tolerance": config.increment_tolerance,
        "max_iterations": config.max_iterations,
        "line_search_alphas": list(config.line_search_alphas),
        "matrix_backend": config.matrix_backend,
    }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DAdaptiveConfig:
    """Bounded monotone load-factor continuation policy."""

    target_load_factor: float = 1.0
    initial_step_size: float = 1.0
    minimum_step_size: float = 0.0625
    maximum_step_size: float = 1.0
    failed_step_reduction: float = 0.5
    fast_step_growth: float = 2.0
    fast_newton_iteration_threshold: int = 6
    maximum_attempt_count: int = 32
    newton_config: NewtonRaphsonConfig = field(default_factory=NewtonRaphsonConfig)

    def __post_init__(self) -> None:
        for name in (
            "target_load_factor",
            "initial_step_size",
            "minimum_step_size",
            "maximum_step_size",
            "failed_step_reduction",
            "fast_step_growth",
        ):
            object.__setattr__(
                self,
                name,
                _finite_float(getattr(self, name), path=name, positive=True),
            )
        if self.minimum_step_size > self.initial_step_size:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "minimum_step_size cannot exceed initial_step_size"
            )
        if self.initial_step_size > self.maximum_step_size:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "initial_step_size cannot exceed maximum_step_size"
            )
        if not 0.0 < self.failed_step_reduction < 1.0:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "failed_step_reduction must be between zero and one"
            )
        if self.fast_step_growth < 1.0:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "fast_step_growth must be at least one"
            )
        if (
            type(self.fast_newton_iteration_threshold) is not int
            or self.fast_newton_iteration_threshold < 0
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "fast_newton_iteration_threshold must be non-negative"
            )
        if (
            type(self.maximum_attempt_count) is not int
            or self.maximum_attempt_count < 1
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "maximum_attempt_count must be positive"
            )
        if type(self.newton_config) is not NewtonRaphsonConfig:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "newton_config must be NewtonRaphsonConfig"
            )

    def path_contract_payload(self) -> dict[str, Any]:
        return {
            "target_load_factor": self.target_load_factor,
            "initial_step_size": self.initial_step_size,
            "minimum_step_size": self.minimum_step_size,
            "maximum_step_size": self.maximum_step_size,
            "failed_step_reduction": self.failed_step_reduction,
            "fast_step_growth": self.fast_step_growth,
            "fast_newton_iteration_threshold": (self.fast_newton_iteration_threshold),
            "maximum_attempt_count": self.maximum_attempt_count,
            "newton_config": _newton_config_payload(self.newton_config),
            "accepted_trial_policy": (
                "immutable_corotational_material_parent_then_atomic_commit"
            ),
            "failed_step_policy": (
                "exact_full_checkpoint_rollback_then_deterministic_reduction"
            ),
            "checkpoint_policy": (
                "signed_zero_preserving_json_every_attempt_source_and_path_bound"
            ),
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DAdaptiveProgress:
    """Cumulative path facts retained across exact adaptive restarts."""

    attempt_count: int = 0
    accepted_step_count: int = 0
    failed_step_count: int = 0
    failed_step_reduction_count: int = 0
    fast_step_growth_count: int = 0
    newton_iteration_count: int = 0
    linear_solve_count: int = 0
    line_search_step_count: int = 0
    iterative_solver_step_count: int = 0
    no_solve_reaction_only_step_count: int = 0
    fallback_count: int = 0
    regularization_count: int = 0
    yielded_member_step_count: int = 0
    damaged_member_step_count: int = 0
    maximum_line_search_backtrack_count: int = 0
    minimum_attempted_step_size: float = 0.0
    maximum_attempted_step_size: float = 0.0
    maximum_checkpoint_relative_residual: float = 0.0
    rollback_exact: bool = True
    residual_and_increment_acceptance_gate: bool = True
    parent_ancestry_gate: bool = True
    parent_immutable_gate: bool = True

    def __post_init__(self) -> None:
        integer_names = (
            "attempt_count",
            "accepted_step_count",
            "failed_step_count",
            "failed_step_reduction_count",
            "fast_step_growth_count",
            "newton_iteration_count",
            "linear_solve_count",
            "line_search_step_count",
            "iterative_solver_step_count",
            "no_solve_reaction_only_step_count",
            "fallback_count",
            "regularization_count",
            "yielded_member_step_count",
            "damaged_member_step_count",
            "maximum_line_search_backtrack_count",
        )
        for name in integer_names:
            _nonnegative_int(getattr(self, name), path=f"progress.{name}")
        for name in (
            "minimum_attempted_step_size",
            "maximum_attempted_step_size",
            "maximum_checkpoint_relative_residual",
        ):
            value = _finite_float(getattr(self, name), path=f"progress.{name}")
            if value < 0.0:
                raise StatefulCorotationalFiberFrame2DAdaptiveError(
                    f"progress.{name} must be non-negative"
                )
        for name in (
            "rollback_exact",
            "residual_and_increment_acceptance_gate",
            "parent_ancestry_gate",
            "parent_immutable_gate",
        ):
            if type(getattr(self, name)) is not bool:
                raise StatefulCorotationalFiberFrame2DAdaptiveError(
                    f"progress.{name} must be boolean"
                )
        if self.accepted_step_count + self.failed_step_count != self.attempt_count:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "accepted and failed counts must equal attempt_count"
            )
        if self.failed_step_reduction_count != self.failed_step_count:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "every failed step must have one reduction"
            )
        if self.fast_step_growth_count > self.accepted_step_count:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "fast_step_growth_count exceeds accepted_step_count"
            )
        if (
            self.iterative_solver_step_count + self.no_solve_reaction_only_step_count
            != self.accepted_step_count
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "accepted solver disposition counts are inconsistent"
            )
        if self.attempt_count == 0 and (
            self.minimum_attempted_step_size != 0.0
            or self.maximum_attempted_step_size != 0.0
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "empty progress must have zero attempted step-size bounds"
            )
        if (
            self.attempt_count > 0
            and self.minimum_attempted_step_size > self.maximum_attempted_step_size
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "progress attempted step-size bounds are inverted"
            )

    def to_dict(self) -> dict[str, Any]:
        return {row.name: getattr(self, row.name) for row in fields(type(self))}

    @classmethod
    def from_dict(
        cls,
        value: Any,
    ) -> StatefulCorotationalFiberFrame2DAdaptiveProgress:
        expected = {row.name for row in fields(cls)}
        payload = _expect_exact_keys(
            value,
            path="/boundary/progress",
            expected=expected,
        )
        bool_names = {
            "rollback_exact",
            "residual_and_increment_acceptance_gate",
            "parent_ancestry_gate",
            "parent_immutable_gate",
        }
        float_names = {
            "minimum_attempted_step_size",
            "maximum_attempted_step_size",
            "maximum_checkpoint_relative_residual",
        }
        normalized: dict[str, Any] = {}
        for name in expected:
            if name in bool_names:
                if type(payload[name]) is not bool:
                    raise StatefulCorotationalFiberFrame2DAdaptiveError(
                        f"/boundary/progress/{name} must be boolean"
                    )
                normalized[name] = payload[name]
            elif name in float_names:
                normalized[name] = _finite_float(
                    payload[name],
                    path=f"/boundary/progress/{name}",
                )
            else:
                normalized[name] = _nonnegative_int(
                    payload[name],
                    path=f"/boundary/progress/{name}",
                )
        return cls(**normalized)


def stateful_corotational_fiber_frame2d_adaptive_path_contract_hash(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
) -> str:
    return canonical_hash(
        {
            "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_PROFILE,
            "source_case_id": problem.case_id,
            "source_problem_contract_hash": problem.contract_hash,
            "config": config.path_contract_payload(),
        }
    )


def _adaptive_checkpoint_hash_payload(
    *,
    source_case_id: str,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    next_step_size: float,
    progress: StatefulCorotationalFiberFrame2DAdaptiveProgress,
) -> dict[str, Any]:
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION
        ),
        "source": {
            "case_id": source_case_id,
            "problem_contract_hash": source_problem_contract_hash,
        },
        "path_contract_hash": path_contract_hash,
        "boundary": {
            "accepted_checkpoint": accepted_checkpoint.to_dict(),
            "next_step_size": next_step_size,
            "progress": progress.to_dict(),
        },
    }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
    """Persisted attempt boundary including material, kinematic, and policy state."""

    schema_version: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    next_step_size: float
    progress: StatefulCorotationalFiberFrame2DAdaptiveProgress
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "checkpoint schema_version is invalid"
            )
        if not str(self.source_case_id).strip():
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
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
        if type(self.accepted_checkpoint) is not (
            StatefulCorotationalFiberFrame2DCheckpoint
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "accepted_checkpoint type is invalid"
            )
        next_step_size = _finite_float(
            self.next_step_size,
            path="checkpoint.next_step_size",
            positive=True,
        )
        object.__setattr__(self, "next_step_size", next_step_size)
        payload = _adaptive_checkpoint_hash_payload(
            source_case_id=self.source_case_id,
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_checkpoint=self.accepted_checkpoint,
            next_step_size=next_step_size,
            progress=self.progress,
        )
        computed = "sha256:" + hashlib.sha256(_artifact_json_bytes(payload)).hexdigest()
        if self.checkpoint_hash and self.checkpoint_hash != computed:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "checkpoint_hash mismatch"
            )
        if not self.checkpoint_hash:
            object.__setattr__(self, "checkpoint_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        payload = _adaptive_checkpoint_hash_payload(
            source_case_id=self.source_case_id,
            source_problem_contract_hash=self.source_problem_contract_hash,
            path_contract_hash=self.path_contract_hash,
            accepted_checkpoint=self.accepted_checkpoint,
            next_step_size=self.next_step_size,
            progress=self.progress,
        )
        payload["checkpoint_hash"] = self.checkpoint_hash
        return payload

    def to_bytes(self) -> bytes:
        return _artifact_json_bytes(self.to_dict())

    def descriptor(self) -> dict[str, Any]:
        raw = self.to_bytes()
        return {
            "schema_version": self.schema_version,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": self.source_problem_contract_hash,
            "path_contract_hash": self.path_contract_hash,
            "accepted_epoch": self.accepted_checkpoint.epoch,
            "accepted_load_factor": self.accepted_checkpoint.load_factor,
            "accepted_state_hash": self.accepted_checkpoint.state_hash,
            "next_step_size": self.next_step_size,
            "progress": self.progress.to_dict(),
            "checkpoint_hash": self.checkpoint_hash,
            "artifact_byte_length": len(raw),
            "artifact_data_hash": ("sha256:" + hashlib.sha256(raw).hexdigest()),
        }


def _load_tolerance(target_load_factor: float) -> float:
    return float(16.0 * np.finfo(np.float64).eps * max(1.0, abs(target_load_factor)))


def _checkpoint_relative_residual(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> float:
    physical = np.asarray(checkpoint.global_displacements, dtype=np.float64)
    generalized = physical / problem.physical_coordinate_scale
    free = generalized[list(problem.free_global_dofs)]
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        checkpoint,
        target_load_factor=checkpoint.load_factor,
        trial_free_coordinates_m=free,
    )
    if assembly.residual_kn.size == 0:
        return 0.0
    return float(
        np.linalg.norm(assembly.residual_kn, ord=np.inf)
        / problem.reference_force_scale()
    )


def validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
    checkpoint: StatefulCorotationalFiberFrame2DAdaptiveCheckpoint,
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
) -> StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
    if type(checkpoint) is not StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint type is invalid"
        )
    if checkpoint.source_case_id != problem.case_id:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint source case_id mismatch"
        )
    if checkpoint.source_problem_contract_hash != problem.contract_hash:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint source problem contract mismatch"
        )
    expected_path_hash = (
        stateful_corotational_fiber_frame2d_adaptive_path_contract_hash(
            problem,
            config,
        )
    )
    if checkpoint.path_contract_hash != expected_path_hash:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint path contract mismatch"
        )
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem,
        checkpoint.accepted_checkpoint,
    )
    tolerance = _load_tolerance(config.target_load_factor)
    if not (
        -tolerance
        <= checkpoint.accepted_checkpoint.load_factor
        <= config.target_load_factor + tolerance
    ):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint accepted load factor is outside the path"
        )
    if checkpoint.next_step_size > config.maximum_step_size + tolerance:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint next_step_size exceeds maximum_step_size"
        )
    if checkpoint.progress.attempt_count > config.maximum_attempt_count:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint attempt_count exceeds maximum_attempt_count"
        )
    residual = _checkpoint_relative_residual(
        problem,
        checkpoint.accepted_checkpoint,
    )
    if residual > config.newton_config.residual_tolerance:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint accepted state is not in equilibrium"
        )
    if (
        residual
        > checkpoint.progress.maximum_checkpoint_relative_residual
        + 16.0 * np.finfo(np.float64).eps
    ):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "checkpoint progress omits the accepted residual"
        )
    return checkpoint


def create_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
    *,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    next_step_size: float,
    progress: StatefulCorotationalFiberFrame2DAdaptiveProgress,
) -> StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
    checkpoint = StatefulCorotationalFiberFrame2DAdaptiveCheckpoint(
        schema_version=(
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION
        ),
        source_case_id=problem.case_id,
        source_problem_contract_hash=problem.contract_hash,
        path_contract_hash=(
            stateful_corotational_fiber_frame2d_adaptive_path_contract_hash(
                problem,
                config,
            )
        ),
        accepted_checkpoint=accepted_checkpoint,
        next_step_size=next_step_size,
        progress=progress,
    )
    return validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
        checkpoint,
        problem,
        config,
    )


def load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
    data: bytes | bytearray | memoryview,
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
) -> StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint artifact must be bytes"
        )
    raw = bytes(data)
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint artifact exceeds the bounded byte limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except StatefulCorotationalFiberFrame2DAdaptiveError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint is not valid UTF-8 JSON"
        ) from exc
    if _artifact_json_bytes(parsed) != raw:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint is not canonical JSON"
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
    if (
        payload["schema_version"]
        != STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION
    ):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint schema_version is invalid"
        )
    source = _expect_exact_keys(
        payload["source"],
        path="/source",
        expected={"case_id", "problem_contract_hash"},
    )
    boundary = _expect_exact_keys(
        payload["boundary"],
        path="/boundary",
        expected={"accepted_checkpoint", "next_step_size", "progress"},
    )
    accepted_payload = _expect_mapping(
        boundary["accepted_checkpoint"],
        path="/boundary/accepted_checkpoint",
    )
    accepted = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        _artifact_json_bytes(accepted_payload),
        problem,
    )
    checkpoint = StatefulCorotationalFiberFrame2DAdaptiveCheckpoint(
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
        next_step_size=_finite_float(
            boundary["next_step_size"],
            path="/boundary/next_step_size",
            positive=True,
        ),
        progress=(
            StatefulCorotationalFiberFrame2DAdaptiveProgress.from_dict(
                boundary["progress"]
            )
        ),
        checkpoint_hash=_require_hash(
            payload["checkpoint_hash"],
            path="/checkpoint_hash",
        ),
    )
    validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
        checkpoint,
        problem,
        config,
    )
    if checkpoint.to_bytes() != raw:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint artifact round-trip mismatch"
        )
    return checkpoint


def write_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
    checkpoint: StatefulCorotationalFiberFrame2DAdaptiveCheckpoint,
    target: str | Path,
) -> Path:
    validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
        checkpoint,
        problem,
        config,
    )
    raw = checkpoint.to_bytes()
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint artifact exceeds the bounded byte limit"
        )
    restored = load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
        raw,
        problem,
        config,
    )
    if (
        restored.accepted_checkpoint.canonical_bytes()
        != checkpoint.accepted_checkpoint.canonical_bytes()
    ):
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "accepted checkpoint changed during adaptive serialization"
        )
    path = Path(target)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint target already exists"
        ) from exc
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint could not be written"
        ) from exc
    return path


def read_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig,
    source: str | Path,
) -> StatefulCorotationalFiberFrame2DAdaptiveCheckpoint:
    path = Path(source)
    try:
        size = path.stat().st_size
        if size > (STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_MAX_BYTES):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "adaptive checkpoint artifact exceeds the bounded byte limit"
            )
        raw = path.read_bytes()
    except StatefulCorotationalFiberFrame2DAdaptiveError:
        raise
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "adaptive checkpoint could not be read"
        ) from exc
    return load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes(
        raw,
        problem,
        config,
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DAdaptiveAttempt:
    attempt_index: int
    attempted_step_size: float
    accepted_load_factor_before: float
    target_load_factor: float
    outcome: str
    step_reduced: bool
    step_grew: bool
    next_step_size: float
    resulting_checkpoint_hash: str
    step_result: StatefulCorotationalFiberFrame2DLoadStepResult

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
class StatefulCorotationalFiberFrame2DAdaptiveResult:
    status: str
    terminal_reason: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig
    initial_checkpoint: StatefulCorotationalFiberFrame2DAdaptiveCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DAdaptiveCheckpoint
    checkpoints: tuple[StatefulCorotationalFiberFrame2DAdaptiveCheckpoint, ...]
    attempts: tuple[StatefulCorotationalFiberFrame2DAdaptiveAttempt, ...]
    metrics: dict[str, Any]

    @property
    def final_state(self) -> StatefulCorotationalFiberFrame2DCheckpoint:
        return self.final_checkpoint.accepted_checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_SCHEMA_VERSION
            ),
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "profile": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_PROFILE,
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": self.source_problem_contract_hash,
            "path_contract_hash": self.path_contract_hash,
            "config": self.config.path_contract_payload(),
            "initial_checkpoint": self.initial_checkpoint.descriptor(),
            "final_checkpoint": self.final_checkpoint.descriptor(),
            "checkpoints": [row.descriptor() for row in self.checkpoints],
            "attempts": [row.to_dict() for row in self.attempts],
            "metrics": dict(self.metrics),
            "claims": {
                "adaptive_corotational_fiber_frame2d_path": bool(
                    self.metrics["contract_pass"]
                    and self.metrics["accepted_step_count"] > 0
                ),
                "consistent_material_geometric_newton_step_executed": bool(
                    self.metrics["iterative_solver_step_count"] > 0
                ),
                "failed_step_reduction_exercised": bool(
                    self.metrics["failed_step_reduction_count"] > 0
                ),
                "failed_step_full_state_rollback_exact": bool(
                    self.metrics["failed_step_count"] > 0
                    and self.metrics["rollback_exact"]
                ),
                "source_bound_persisted_checkpoint": True,
                "checkpoint_restart_consumed": bool(
                    self.metrics["restart_checkpoint_consumed"]
                ),
                "checkpoint_chain_replay": False,
                "arc_length_branch": False,
                "production_sparse_solver": False,
                "rocm_hip_parity": False,
                "external_benchmark_acceptance": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CLAIM_BOUNDARY
            ),
        }


def _step_iteration_count(
    step_result: StatefulCorotationalFiberFrame2DLoadStepResult,
) -> int:
    metrics = step_result.trial_solution.metrics
    return int(
        metrics.get(
            "newton_iteration_count",
            metrics.get(
                "iteration_count",
                len(step_result.trial_solution.convergence_history),
            ),
        )
        or 0
    )


def _updated_progress(
    progress: StatefulCorotationalFiberFrame2DAdaptiveProgress,
    *,
    step_result: StatefulCorotationalFiberFrame2DLoadStepResult,
    attempted_step_size: float,
    accepted: bool,
    step_grew: bool,
    checkpoint_relative_residual: float,
) -> StatefulCorotationalFiberFrame2DAdaptiveProgress:
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
    solution_metrics = step_result.trial_solution.metrics
    backtrack_count = max(
        (
            int(row.get("attempt_count", 0)) - 1
            for row in step_result.trial_solution.line_search_history
        ),
        default=0,
    )
    iterative = bool(accepted and step_result.metrics["iterative_solver_contract_pass"])
    no_solve = bool(accepted and step_result.metrics["no_solve_contract_pass"])
    return replace(
        progress,
        attempt_count=progress.attempt_count + 1,
        accepted_step_count=progress.accepted_step_count + int(accepted),
        failed_step_count=progress.failed_step_count + int(not accepted),
        failed_step_reduction_count=(
            progress.failed_step_reduction_count + int(not accepted)
        ),
        fast_step_growth_count=(progress.fast_step_growth_count + int(step_grew)),
        newton_iteration_count=(
            progress.newton_iteration_count + _step_iteration_count(step_result)
        ),
        linear_solve_count=(
            progress.linear_solve_count
            + int(solution_metrics.get("linear_solve_count", 0) or 0)
        ),
        line_search_step_count=(
            progress.line_search_step_count
            + int(solution_metrics.get("line_search_step_count", 0) or 0)
        ),
        iterative_solver_step_count=(
            progress.iterative_solver_step_count + int(iterative)
        ),
        no_solve_reaction_only_step_count=(
            progress.no_solve_reaction_only_step_count + int(no_solve)
        ),
        fallback_count=(
            progress.fallback_count + int(bool(step_result.metrics["fallback_used"]))
        ),
        regularization_count=(
            progress.regularization_count
            + int(bool(step_result.metrics["regularization_used"]))
        ),
        yielded_member_step_count=(
            progress.yielded_member_step_count
            + int(accepted and step_result.metrics["yielded_member_count"] > 0)
        ),
        damaged_member_step_count=(
            progress.damaged_member_step_count
            + int(accepted and step_result.metrics["damaged_member_count"] > 0)
        ),
        maximum_line_search_backtrack_count=max(
            progress.maximum_line_search_backtrack_count,
            backtrack_count,
        ),
        minimum_attempted_step_size=minimum_step,
        maximum_attempted_step_size=maximum_step,
        maximum_checkpoint_relative_residual=max(
            progress.maximum_checkpoint_relative_residual,
            checkpoint_relative_residual,
        ),
        rollback_exact=bool(
            progress.rollback_exact
            and (accepted or step_result.metrics["rollback_exact"] is True)
        ),
        residual_and_increment_acceptance_gate=bool(
            progress.residual_and_increment_acceptance_gate
            and (
                not accepted
                or step_result.metrics["no_solve_contract_pass"]
                or (
                    step_result.metrics["residual_gate_passed"] is True
                    and step_result.metrics["increment_gate_passed"] is True
                )
            )
        ),
        parent_ancestry_gate=bool(
            progress.parent_ancestry_gate
            and step_result.metrics["section_and_element_parent_binding_passed"]
        ),
        parent_immutable_gate=bool(
            progress.parent_immutable_gate
            and step_result.metrics["parent_checkpoint_immutable"]
        ),
    )


def adaptive_stateful_corotational_fiber_frame2d_continuation(
    problem: StatefulCorotationalFiberFrame2DProblem,
    *,
    config: StatefulCorotationalFiberFrame2DAdaptiveConfig | None = None,
    initial_state: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    checkpoint: StatefulCorotationalFiberFrame2DAdaptiveCheckpoint | None = None,
) -> StatefulCorotationalFiberFrame2DAdaptiveResult:
    """Run adaptive physical load steps with transactional full frame state."""

    normalized_config = config or (StatefulCorotationalFiberFrame2DAdaptiveConfig())
    if initial_state is not None and checkpoint is not None:
        raise StatefulCorotationalFiberFrame2DAdaptiveError(
            "initial_state cannot be combined with checkpoint"
        )
    path_contract_hash = (
        stateful_corotational_fiber_frame2d_adaptive_path_contract_hash(
            problem,
            normalized_config,
        )
    )
    load_tolerance = _load_tolerance(normalized_config.target_load_factor)

    if checkpoint is not None:
        accepted_boundary = (
            validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
                checkpoint,
                problem,
                normalized_config,
            )
        )
        accepted = accepted_boundary.accepted_checkpoint
        progress = accepted_boundary.progress
        step_size = accepted_boundary.next_step_size
        restart_consumed = True
    else:
        accepted = initial_state or (
            initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem,
            accepted,
        )
        if not (
            -load_tolerance
            <= accepted.load_factor
            <= normalized_config.target_load_factor + load_tolerance
        ):
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "initial accepted load factor is outside the adaptive path"
            )
        initial_residual = _checkpoint_relative_residual(problem, accepted)
        if initial_residual > normalized_config.newton_config.residual_tolerance:
            raise StatefulCorotationalFiberFrame2DAdaptiveError(
                "initial accepted state is not in equilibrium"
            )
        progress = StatefulCorotationalFiberFrame2DAdaptiveProgress(
            maximum_checkpoint_relative_residual=initial_residual
        )
        step_size = min(
            normalized_config.initial_step_size,
            normalized_config.maximum_step_size,
        )
        accepted_boundary = (
            create_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
                problem,
                normalized_config,
                accepted_checkpoint=accepted,
                next_step_size=step_size,
                progress=progress,
            )
        )
        restart_consumed = False

    initial_checkpoint = accepted_boundary
    checkpoints = [accepted_boundary]
    attempts: list[StatefulCorotationalFiberFrame2DAdaptiveAttempt] = []
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
        element_bytes_before = tuple(
            state.canonical_bytes() for state in accepted_before.element_states
        )
        step_result = solve_stateful_corotational_fiber_frame2d_load_step(
            problem,
            accepted_before,
            target_load_factor=target_load_factor,
            config=normalized_config.newton_config,
        )
        accepted_step = bool(step_result.committed)
        if accepted_step:
            accepted = step_result.accepted_checkpoint
            remaining_after = (
                normalized_config.target_load_factor - accepted.load_factor
            )
            step_grew = bool(
                _step_iteration_count(step_result)
                <= normalized_config.fast_newton_iteration_threshold
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
                step_result.accepted_checkpoint is accepted_before
                and step_result.metrics["rollback_exact"] is True
                and accepted_before.canonical_bytes() == parent_bytes_before
                and tuple(
                    state.canonical_bytes() for state in accepted_before.element_states
                )
                == element_bytes_before
            )
            if not rollback_exact:
                raise StatefulCorotationalFiberFrame2DAdaptiveError(
                    "failed adaptive step did not preserve full checkpoint bytes"
                )
            accepted = accepted_before
            next_step_size = (
                attempted_step_size * normalized_config.failed_step_reduction
            )
            step_grew = False
            outcome = "rolled_back"
            step_reduced = True

        checkpoint_residual = _checkpoint_relative_residual(problem, accepted)
        progress = _updated_progress(
            progress,
            step_result=step_result,
            attempted_step_size=attempted_step_size,
            accepted=accepted_step,
            step_grew=step_grew,
            checkpoint_relative_residual=checkpoint_residual,
        )
        accepted_boundary = (
            create_stateful_corotational_fiber_frame2d_adaptive_checkpoint(
                problem,
                normalized_config,
                accepted_checkpoint=accepted,
                next_step_size=next_step_size,
                progress=progress,
            )
        )
        checkpoints.append(accepted_boundary)
        attempts.append(
            StatefulCorotationalFiberFrame2DAdaptiveAttempt(
                attempt_index=progress.attempt_count,
                attempted_step_size=float(attempted_step_size),
                accepted_load_factor_before=float(accepted_before.load_factor),
                target_load_factor=float(target_load_factor),
                outcome=outcome,
                step_reduced=step_reduced,
                step_grew=step_grew,
                next_step_size=float(next_step_size),
                resulting_checkpoint_hash=accepted_boundary.checkpoint_hash,
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
    final_residual = _checkpoint_relative_residual(problem, accepted)
    contract_pass = bool(
        target_reached
        and progress.accepted_step_count > 0
        and final_residual <= normalized_config.newton_config.residual_tolerance
        and progress.maximum_checkpoint_relative_residual
        <= normalized_config.newton_config.residual_tolerance
        and progress.rollback_exact
        and progress.residual_and_increment_acceptance_gate
        and progress.parent_ancestry_gate
        and progress.parent_immutable_gate
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
        "final_relative_residual": final_residual,
        "restart_checkpoint_consumed": restart_consumed,
        "canonical_checkpoint_artifact_available": True,
        "corotational_checkpoint_artifact_available": True,
        "checkpoint_chain_replay_claim": False,
        "arc_length_claim": False,
        "production_sparse_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "external_benchmark_acceptance_claim": False,
        "g1_full_building_closure_claim": False,
    }
    return StatefulCorotationalFiberFrame2DAdaptiveResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        source_case_id=problem.case_id,
        source_problem_contract_hash=problem.contract_hash,
        path_contract_hash=path_contract_hash,
        config=normalized_config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=checkpoints[-1],
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_MAX_BYTES",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_PROFILE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_ADAPTIVE_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DAdaptiveAttempt",
    "StatefulCorotationalFiberFrame2DAdaptiveCheckpoint",
    "StatefulCorotationalFiberFrame2DAdaptiveConfig",
    "StatefulCorotationalFiberFrame2DAdaptiveError",
    "StatefulCorotationalFiberFrame2DAdaptiveProgress",
    "StatefulCorotationalFiberFrame2DAdaptiveResult",
    "adaptive_stateful_corotational_fiber_frame2d_continuation",
    "create_stateful_corotational_fiber_frame2d_adaptive_checkpoint",
    "load_stateful_corotational_fiber_frame2d_adaptive_checkpoint_bytes",
    "read_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact",
    "stateful_corotational_fiber_frame2d_adaptive_path_contract_hash",
    "validate_stateful_corotational_fiber_frame2d_adaptive_checkpoint",
    "write_stateful_corotational_fiber_frame2d_adaptive_checkpoint_artifact",
]
