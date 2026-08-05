"""Fail-closed physical residual/Jacobian directional-consistency gate.

The gate compares an accepted-state Jacobian-vector product against central
finite differences of the *same physical residual*. It is backend-neutral and
can be used by CPU or HIP workers. Passing this bounded gate does not establish
G1 full-load closure, material breadth, GPU residency, or product authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Final

import numpy as np


DIRECTIONAL_GATE_PROFILE: Final = "physical_residual_accepted_state_jacobian.v1"
DIRECTIONAL_GATE_SCHEMA_VERSION: Final = (
    "residual-jacobian-directional-consistency-receipt.v1"
)

ResidualFunction = Callable[[np.ndarray], np.ndarray]
JacobianVectorProduct = Callable[[np.ndarray, np.ndarray], np.ndarray]


class ResidualJacobianConsistencyError(ValueError):
    """Raised when the directional probe cannot be evaluated safely."""


@dataclass(frozen=True)
class DirectionalConsistencyConfig:
    relative_steps: tuple[float, ...] = (1.0e-4, 1.0e-5, 1.0e-6)
    absolute_tolerance: float = 1.0e-8
    relative_tolerance: float = 2.0e-5
    minimum_passing_step_count: int = 2
    profile: str = DIRECTIONAL_GATE_PROFILE
    residual_kind: str = "physical_residual"
    jacobian_epoch: str = "accepted_state"
    fallback_allowed: bool = False
    regularization_allowed: bool = False

    def validate(self) -> None:
        if self.profile != DIRECTIONAL_GATE_PROFILE:
            raise ResidualJacobianConsistencyError("directional_gate_profile_invalid")
        if self.residual_kind != "physical_residual":
            raise ResidualJacobianConsistencyError("physical_residual_required")
        if self.jacobian_epoch != "accepted_state":
            raise ResidualJacobianConsistencyError("accepted_state_jacobian_required")
        if self.fallback_allowed or self.regularization_allowed:
            raise ResidualJacobianConsistencyError(
                "fallback_or_regularization_forbidden"
            )
        if not self.relative_steps:
            raise ResidualJacobianConsistencyError("relative_steps_empty")
        if any(
            type(value) is bool or not math.isfinite(value) or value <= 0.0
            for value in self.relative_steps
        ):
            raise ResidualJacobianConsistencyError("relative_steps_invalid")
        if len(set(self.relative_steps)) != len(self.relative_steps):
            raise ResidualJacobianConsistencyError("relative_steps_duplicate")
        if any(
            earlier <= later
            for earlier, later in zip(self.relative_steps, self.relative_steps[1:])
        ):
            raise ResidualJacobianConsistencyError(
                "relative_steps_must_be_strictly_decreasing"
            )
        if (
            type(self.absolute_tolerance) is bool
            or not math.isfinite(self.absolute_tolerance)
            or self.absolute_tolerance < 0.0
        ):
            raise ResidualJacobianConsistencyError("absolute_tolerance_invalid")
        if (
            type(self.relative_tolerance) is bool
            or not math.isfinite(self.relative_tolerance)
            or self.relative_tolerance < 0.0
        ):
            raise ResidualJacobianConsistencyError("relative_tolerance_invalid")
        if (
            type(self.minimum_passing_step_count) is bool
            or not isinstance(self.minimum_passing_step_count, int)
            or self.minimum_passing_step_count < 1
            or self.minimum_passing_step_count > len(self.relative_steps)
        ):
            raise ResidualJacobianConsistencyError(
                "minimum_passing_step_count_invalid"
            )


@dataclass(frozen=True)
class DirectionalStepReceipt:
    relative_step: float
    physical_step: float
    finite_difference_linf: float
    jacobian_vector_product_linf: float
    absolute_error_linf: float
    relative_error_linf: float
    tolerance_limit_linf: float
    passed: bool
    residual_plus_hash: str
    residual_minus_hash: str
    finite_difference_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_step": self.relative_step,
            "physical_step": self.physical_step,
            "finite_difference_linf": self.finite_difference_linf,
            "jacobian_vector_product_linf": self.jacobian_vector_product_linf,
            "absolute_error_linf": self.absolute_error_linf,
            "relative_error_linf": self.relative_error_linf,
            "tolerance_limit_linf": self.tolerance_limit_linf,
            "passed": self.passed,
            "residual_plus_hash": self.residual_plus_hash,
            "residual_minus_hash": self.residual_minus_hash,
            "finite_difference_hash": self.finite_difference_hash,
        }


@dataclass(frozen=True)
class ResidualJacobianDirectionalReceipt:
    source_commit_sha: str
    operator_id: str
    backend_id: str
    state_hash: str
    normalized_direction_hash: str
    base_residual_hash: str
    jacobian_vector_product_hash: str
    equation_count: int
    state_scale: float
    passing_step_count: int
    required_passing_step_count: int
    best_absolute_error_linf: float
    best_relative_error_linf: float
    consistent_residual_jacobian_newton_gate_passed: bool
    steps: tuple[DirectionalStepReceipt, ...]
    config: Mapping[str, Any]
    receipt_hash: str
    schema_version: str = DIRECTIONAL_GATE_SCHEMA_VERSION
    profile: str = DIRECTIONAL_GATE_PROFILE
    numerical_authority: str = "diagnostic_only"
    product_authority: str = "none"
    claim_boundary: str = (
        "This receipt proves only bounded directional consistency between the declared "
        "physical residual and accepted-state Jacobian-vector product. It does not "
        "establish G1 full-load/full-mesh convergence, material Newton breadth, HIP "
        "device residency, fallback-zero production execution, engineering recovery, "
        "design authority, or release readiness."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "source_commit_sha": self.source_commit_sha,
            "operator_id": self.operator_id,
            "backend_id": self.backend_id,
            "state_hash": self.state_hash,
            "normalized_direction_hash": self.normalized_direction_hash,
            "base_residual_hash": self.base_residual_hash,
            "jacobian_vector_product_hash": self.jacobian_vector_product_hash,
            "equation_count": self.equation_count,
            "state_scale": self.state_scale,
            "passing_step_count": self.passing_step_count,
            "required_passing_step_count": self.required_passing_step_count,
            "best_absolute_error_linf": self.best_absolute_error_linf,
            "best_relative_error_linf": self.best_relative_error_linf,
            "consistent_residual_jacobian_newton_gate_passed": (
                self.consistent_residual_jacobian_newton_gate_passed
            ),
            "steps": [row.to_dict() for row in self.steps],
            "config": _deep_thaw(self.config),
            "numerical_authority": self.numerical_authority,
            "product_authority": self.product_authority,
            "claim_boundary": self.claim_boundary,
            "receipt_hash": self.receipt_hash,
        }


def probe_residual_jacobian_directional_consistency(
    *,
    source_commit_sha: str,
    operator_id: str,
    backend_id: str,
    accepted_state: Sequence[float] | np.ndarray,
    direction: Sequence[float] | np.ndarray,
    residual: ResidualFunction,
    jacobian_vector_product: JacobianVectorProduct,
    config: DirectionalConsistencyConfig | None = None,
) -> ResidualJacobianDirectionalReceipt:
    """Evaluate a source-bound central-difference directional consistency gate."""

    cfg = config or DirectionalConsistencyConfig()
    cfg.validate()
    if not _is_commit_sha(source_commit_sha):
        raise ResidualJacobianConsistencyError("source_commit_sha_invalid")
    if not operator_id or not backend_id:
        raise ResidualJacobianConsistencyError("operator_or_backend_id_missing")

    state = _vector(accepted_state, "accepted_state")
    raw_direction = _vector(direction, "direction")
    if state.shape != raw_direction.shape:
        raise ResidualJacobianConsistencyError("state_direction_shape_mismatch")
    direction_norm = float(np.linalg.norm(raw_direction))
    if not math.isfinite(direction_norm) or direction_norm <= 0.0:
        raise ResidualJacobianConsistencyError("direction_norm_invalid")
    normalized_direction = np.ascontiguousarray(raw_direction / direction_norm)
    normalized_direction.setflags(write=False)
    state.setflags(write=False)
    state_scale = max(1.0, float(np.linalg.norm(state, ord=np.inf)))

    base_residual = _evaluate_residual(residual, state, state.shape)
    jvp = _evaluate_jvp(
        jacobian_vector_product,
        state,
        normalized_direction,
        state.shape,
    )
    jvp_linf = float(np.linalg.norm(jvp, ord=np.inf))
    rows: list[DirectionalStepReceipt] = []
    for relative_step in cfg.relative_steps:
        physical_step = relative_step * state_scale
        plus_state = np.ascontiguousarray(
            np.asarray(state) + physical_step * normalized_direction
        )
        minus_state = np.ascontiguousarray(
            np.asarray(state) - physical_step * normalized_direction
        )
        plus_state.setflags(write=False)
        minus_state.setflags(write=False)
        residual_plus = _evaluate_residual(residual, plus_state, state.shape)
        residual_minus = _evaluate_residual(residual, minus_state, state.shape)
        finite_difference = np.ascontiguousarray(
            (residual_plus - residual_minus) / (2.0 * physical_step)
        )
        error = np.ascontiguousarray(finite_difference - jvp)
        fd_linf = float(np.linalg.norm(finite_difference, ord=np.inf))
        absolute_error = float(np.linalg.norm(error, ord=np.inf))
        scale = max(fd_linf, jvp_linf, np.finfo(np.float64).tiny)
        relative_error = absolute_error / scale
        tolerance_limit = cfg.absolute_tolerance + cfg.relative_tolerance * scale
        rows.append(
            DirectionalStepReceipt(
                relative_step=relative_step,
                physical_step=physical_step,
                finite_difference_linf=fd_linf,
                jacobian_vector_product_linf=jvp_linf,
                absolute_error_linf=absolute_error,
                relative_error_linf=relative_error,
                tolerance_limit_linf=tolerance_limit,
                passed=absolute_error <= tolerance_limit,
                residual_plus_hash=_array_hash(residual_plus),
                residual_minus_hash=_array_hash(residual_minus),
                finite_difference_hash=_array_hash(finite_difference),
            )
        )
    passing_count = sum(row.passed for row in rows)
    gate_passed = passing_count >= cfg.minimum_passing_step_count
    config_payload = MappingProxyType(
        {
            "relative_steps": tuple(cfg.relative_steps),
            "absolute_tolerance": cfg.absolute_tolerance,
            "relative_tolerance": cfg.relative_tolerance,
            "minimum_passing_step_count": cfg.minimum_passing_step_count,
            "residual_kind": cfg.residual_kind,
            "jacobian_epoch": cfg.jacobian_epoch,
            "fallback_allowed": cfg.fallback_allowed,
            "regularization_allowed": cfg.regularization_allowed,
        }
    )
    provisional = {
        "schema_version": DIRECTIONAL_GATE_SCHEMA_VERSION,
        "profile": DIRECTIONAL_GATE_PROFILE,
        "source_commit_sha": source_commit_sha,
        "operator_id": operator_id,
        "backend_id": backend_id,
        "state_hash": _array_hash(state),
        "normalized_direction_hash": _array_hash(normalized_direction),
        "base_residual_hash": _array_hash(base_residual),
        "jacobian_vector_product_hash": _array_hash(jvp),
        "equation_count": int(state.size),
        "state_scale": state_scale,
        "passing_step_count": passing_count,
        "required_passing_step_count": cfg.minimum_passing_step_count,
        "best_absolute_error_linf": min(row.absolute_error_linf for row in rows),
        "best_relative_error_linf": min(row.relative_error_linf for row in rows),
        "consistent_residual_jacobian_newton_gate_passed": gate_passed,
        "steps": [row.to_dict() for row in rows],
        "config": _deep_thaw(config_payload),
        "numerical_authority": "diagnostic_only",
        "product_authority": "none",
    }
    receipt_hash = _json_hash(provisional)
    return ResidualJacobianDirectionalReceipt(
        source_commit_sha=source_commit_sha,
        operator_id=operator_id,
        backend_id=backend_id,
        state_hash=provisional["state_hash"],
        normalized_direction_hash=provisional["normalized_direction_hash"],
        base_residual_hash=provisional["base_residual_hash"],
        jacobian_vector_product_hash=provisional[
            "jacobian_vector_product_hash"
        ],
        equation_count=int(state.size),
        state_scale=state_scale,
        passing_step_count=passing_count,
        required_passing_step_count=cfg.minimum_passing_step_count,
        best_absolute_error_linf=provisional["best_absolute_error_linf"],
        best_relative_error_linf=provisional["best_relative_error_linf"],
        consistent_residual_jacobian_newton_gate_passed=gate_passed,
        steps=tuple(rows),
        config=config_payload,
        receipt_hash=receipt_hash,
    )


def validate_directional_receipt(
    receipt: ResidualJacobianDirectionalReceipt,
) -> None:
    """Fail closed on inconsistent authority, counts, hashes, or gate truth."""

    if type(receipt) is not ResidualJacobianDirectionalReceipt:
        raise ResidualJacobianConsistencyError("receipt_type_invalid")
    if receipt.schema_version != DIRECTIONAL_GATE_SCHEMA_VERSION:
        raise ResidualJacobianConsistencyError("receipt_schema_invalid")
    if receipt.profile != DIRECTIONAL_GATE_PROFILE:
        raise ResidualJacobianConsistencyError("receipt_profile_invalid")
    if receipt.numerical_authority != "diagnostic_only":
        raise ResidualJacobianConsistencyError("numerical_authority_invalid")
    if receipt.product_authority != "none":
        raise ResidualJacobianConsistencyError("product_authority_invalid")
    passing_count = sum(row.passed for row in receipt.steps)
    if passing_count != receipt.passing_step_count:
        raise ResidualJacobianConsistencyError("passing_step_count_mismatch")
    expected_gate = passing_count >= receipt.required_passing_step_count
    if expected_gate != receipt.consistent_residual_jacobian_newton_gate_passed:
        raise ResidualJacobianConsistencyError("directional_gate_truth_mismatch")
    payload = receipt.to_dict()
    observed_hash = payload.pop("receipt_hash")
    payload.pop("claim_boundary", None)
    if observed_hash != _json_hash(payload):
        raise ResidualJacobianConsistencyError("receipt_hash_mismatch")


def _vector(value: Sequence[float] | np.ndarray, label: str) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    if array.ndim != 1 or array.size < 1:
        raise ResidualJacobianConsistencyError(f"{label}_shape_invalid")
    if not np.all(np.isfinite(array)):
        raise ResidualJacobianConsistencyError(f"{label}_nonfinite")
    return array


def _evaluate_residual(
    callback: ResidualFunction,
    state: np.ndarray,
    expected_shape: tuple[int, ...],
) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(callback(state), dtype=np.float64))
    if result.shape != expected_shape:
        raise ResidualJacobianConsistencyError("residual_shape_mismatch")
    if not np.all(np.isfinite(result)):
        raise ResidualJacobianConsistencyError("residual_nonfinite")
    return result


def _evaluate_jvp(
    callback: JacobianVectorProduct,
    state: np.ndarray,
    direction: np.ndarray,
    expected_shape: tuple[int, ...],
) -> np.ndarray:
    result = np.ascontiguousarray(
        np.asarray(callback(state, direction), dtype=np.float64)
    )
    if result.shape != expected_shape:
        raise ResidualJacobianConsistencyError("jvp_shape_mismatch")
    if not np.all(np.isfinite(result)):
        raise ResidualJacobianConsistencyError("jvp_nonfinite")
    return result


def _array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype="<f8"))
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def _json_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _is_commit_sha(value: str) -> bool:
    return (
        len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )
