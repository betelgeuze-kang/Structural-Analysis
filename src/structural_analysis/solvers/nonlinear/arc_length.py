"""Deterministic scalar spherical arc-length continuation.

This is a narrow, fail-closed path-following kernel for one displacement DOF
and one physical load parameter.  It solves equilibrium and the spherical
constraint together with a consistent 2x2 augmented Newton system.  Accepted
checkpoints are immutable; a failed corrector reduces the arc length and leaves
the accepted state hash unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Protocol


ARC_LENGTH_SCHEMA_VERSION = "structural-analysis-scalar-arc-length.v1"
ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "structural-analysis-scalar-arc-length-checkpoint.v1"
)
ARC_LENGTH_EQUILIBRIUM_FORMULA = "F_internal(displacement)-load"
ARC_LENGTH_CONSTRAINT_FORMULA = (
    "delta_displacement^2+(load_metric_scale*delta_load)^2-arc_length^2"
)


class ScalarArcLengthProblem(Protocol):
    """One-DOF equilibrium path with an exact consistent tangent."""

    case_id: str

    def initial_displacement_m(self) -> float: ...

    def initial_load_kn(self) -> float: ...

    def internal_force_kn(self, displacement_m: float) -> float: ...

    def consistent_tangent_kn_per_m(self, displacement_m: float) -> float: ...


class ArcLengthContractError(ValueError):
    """Stable fail-closed configuration or checkpoint error."""


@dataclass(frozen=True)
class ScalarArcLengthConfig:
    target_displacement_m: float = 0.45
    initial_arc_length_m: float = 0.08
    minimum_arc_length_m: float = 0.005
    maximum_arc_length_m: float = 0.08
    failed_step_reduction: float = 0.5
    load_metric_scale_m_per_kn: float = 0.002
    equilibrium_tolerance_kn: float = 1.0e-10
    constraint_tolerance_m2: float = 1.0e-12
    determinant_tolerance: float = 1.0e-18
    maximum_corrector_iterations: int = 5
    maximum_attempt_count: int = 100


@dataclass(frozen=True)
class ScalarArcLengthCheckpoint:
    schema_version: str
    case_id: str
    step_index: int
    displacement_m: float
    load_kn: float
    previous_tangent_displacement: float | None
    previous_tangent_load_kn: float | None
    current_arc_length_m: float
    state_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_scalar_arc_length_checkpoint(self)
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "step_index": self.step_index,
            "displacement_m": self.displacement_m,
            "load_kn": self.load_kn,
            "previous_tangent_displacement": self.previous_tangent_displacement,
            "previous_tangent_load_kn": self.previous_tangent_load_kn,
            "current_arc_length_m": self.current_arc_length_m,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class ScalarArcLengthResult:
    status: str
    terminal_reason: str
    case_id: str
    config: ScalarArcLengthConfig
    initial_checkpoint: ScalarArcLengthCheckpoint
    final_checkpoint: ScalarArcLengthCheckpoint
    checkpoints: tuple[ScalarArcLengthCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ARC_LENGTH_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "equilibrium_formula": ARC_LENGTH_EQUILIBRIUM_FORMULA,
            "constraint_formula": ARC_LENGTH_CONSTRAINT_FORMULA,
            "config": {
                "target_displacement_m": self.config.target_displacement_m,
                "initial_arc_length_m": self.config.initial_arc_length_m,
                "minimum_arc_length_m": self.config.minimum_arc_length_m,
                "maximum_arc_length_m": self.config.maximum_arc_length_m,
                "failed_step_reduction": self.config.failed_step_reduction,
                "load_metric_scale_m_per_kn": (
                    self.config.load_metric_scale_m_per_kn
                ),
                "equilibrium_tolerance_kn": (
                    self.config.equilibrium_tolerance_kn
                ),
                "constraint_tolerance_m2": (
                    self.config.constraint_tolerance_m2
                ),
                "determinant_tolerance": self.config.determinant_tolerance,
                "maximum_corrector_iterations": (
                    self.config.maximum_corrector_iterations
                ),
                "maximum_attempt_count": self.config.maximum_attempt_count,
            },
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "metrics": self.metrics,
        }


def _finite(value: Any, *, path: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ArcLengthContractError(f"{path} must be numeric") from exc
    if not math.isfinite(result):
        raise ArcLengthContractError(f"{path} must be finite")
    return result


def _checkpoint_hash(
    *,
    case_id: str,
    step_index: int,
    displacement_m: float,
    load_kn: float,
    previous_tangent_displacement: float | None,
    previous_tangent_load_kn: float | None,
    current_arc_length_m: float,
) -> str:
    digest = hashlib.sha256()
    case_bytes = case_id.encode("utf-8")
    digest.update(ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION.encode("ascii"))
    digest.update(struct.pack("<Q", len(case_bytes)))
    digest.update(case_bytes)
    digest.update(struct.pack("<Qddd", step_index, displacement_m, load_kn, current_arc_length_m))
    for value in (previous_tangent_displacement, previous_tangent_load_kn):
        if value is None:
            digest.update(b"\x00")
        else:
            digest.update(b"\x01")
            digest.update(struct.pack("<d", value))
    return f"sha256:{digest.hexdigest()}"


def create_scalar_arc_length_checkpoint(
    *,
    case_id: str,
    step_index: int,
    displacement_m: float,
    load_kn: float,
    previous_tangent_displacement: float | None,
    previous_tangent_load_kn: float | None,
    current_arc_length_m: float,
) -> ScalarArcLengthCheckpoint:
    normalized_case_id = str(case_id).strip()
    if not normalized_case_id:
        raise ArcLengthContractError("case_id is required")
    if isinstance(step_index, bool) or not isinstance(step_index, int) or step_index < 0:
        raise ArcLengthContractError("step_index must be a non-negative integer")
    displacement = _finite(displacement_m, path="displacement_m")
    load = _finite(load_kn, path="load_kn")
    arc_length = _finite(current_arc_length_m, path="current_arc_length_m")
    if arc_length <= 0.0:
        raise ArcLengthContractError("current_arc_length_m must be positive")
    tangent_displacement = (
        None
        if previous_tangent_displacement is None
        else _finite(
            previous_tangent_displacement,
            path="previous_tangent_displacement",
        )
    )
    tangent_load = (
        None
        if previous_tangent_load_kn is None
        else _finite(previous_tangent_load_kn, path="previous_tangent_load_kn")
    )
    if (tangent_displacement is None) != (tangent_load is None):
        raise ArcLengthContractError(
            "previous tangent displacement and load must both be present or absent"
        )
    state_hash = _checkpoint_hash(
        case_id=normalized_case_id,
        step_index=step_index,
        displacement_m=displacement,
        load_kn=load,
        previous_tangent_displacement=tangent_displacement,
        previous_tangent_load_kn=tangent_load,
        current_arc_length_m=arc_length,
    )
    return ScalarArcLengthCheckpoint(
        schema_version=ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION,
        case_id=normalized_case_id,
        step_index=step_index,
        displacement_m=displacement,
        load_kn=load,
        previous_tangent_displacement=tangent_displacement,
        previous_tangent_load_kn=tangent_load,
        current_arc_length_m=arc_length,
        state_hash=state_hash,
    )


def validate_scalar_arc_length_checkpoint(
    checkpoint: ScalarArcLengthCheckpoint,
    *,
    expected_case_id: str | None = None,
) -> ScalarArcLengthCheckpoint:
    if not isinstance(checkpoint, ScalarArcLengthCheckpoint):
        raise ArcLengthContractError("checkpoint type is invalid")
    if checkpoint.schema_version != ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION:
        raise ArcLengthContractError("checkpoint schema_version is invalid")
    if expected_case_id is not None and checkpoint.case_id != expected_case_id:
        raise ArcLengthContractError("checkpoint case_id does not match the problem")
    expected = create_scalar_arc_length_checkpoint(
        case_id=checkpoint.case_id,
        step_index=checkpoint.step_index,
        displacement_m=checkpoint.displacement_m,
        load_kn=checkpoint.load_kn,
        previous_tangent_displacement=checkpoint.previous_tangent_displacement,
        previous_tangent_load_kn=checkpoint.previous_tangent_load_kn,
        current_arc_length_m=checkpoint.current_arc_length_m,
    )
    if checkpoint.state_hash != expected.state_hash:
        raise ArcLengthContractError("checkpoint state_hash mismatch")
    return checkpoint


def _validate_config(config: ScalarArcLengthConfig) -> None:
    positive = {
        "target_displacement_m": config.target_displacement_m,
        "initial_arc_length_m": config.initial_arc_length_m,
        "minimum_arc_length_m": config.minimum_arc_length_m,
        "maximum_arc_length_m": config.maximum_arc_length_m,
        "failed_step_reduction": config.failed_step_reduction,
        "load_metric_scale_m_per_kn": config.load_metric_scale_m_per_kn,
        "equilibrium_tolerance_kn": config.equilibrium_tolerance_kn,
        "constraint_tolerance_m2": config.constraint_tolerance_m2,
        "determinant_tolerance": config.determinant_tolerance,
    }
    for name, value in positive.items():
        normalized = _finite(value, path=name)
        if normalized <= 0.0:
            raise ArcLengthContractError(f"{name} must be positive")
    if config.minimum_arc_length_m > config.initial_arc_length_m:
        raise ArcLengthContractError(
            "minimum_arc_length_m cannot exceed initial_arc_length_m"
        )
    if config.initial_arc_length_m > config.maximum_arc_length_m:
        raise ArcLengthContractError(
            "initial_arc_length_m cannot exceed maximum_arc_length_m"
        )
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise ArcLengthContractError(
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
        raise ArcLengthContractError("iteration and attempt limits must be positive")


def _predictor_tangent(
    problem: ScalarArcLengthProblem,
    checkpoint: ScalarArcLengthCheckpoint,
    *,
    load_metric_scale_m_per_kn: float,
) -> tuple[float, float, float]:
    tangent_kn_per_m = _finite(
        problem.consistent_tangent_kn_per_m(checkpoint.displacement_m),
        path="consistent_tangent_kn_per_m",
    )
    candidate_displacement = 1.0
    candidate_load = tangent_kn_per_m
    norm = math.sqrt(
        candidate_displacement**2
        + (load_metric_scale_m_per_kn * candidate_load) ** 2
    )
    candidate_displacement /= norm
    candidate_load /= norm
    if checkpoint.previous_tangent_displacement is not None:
        assert checkpoint.previous_tangent_load_kn is not None
        orientation = (
            checkpoint.previous_tangent_displacement * candidate_displacement
            + load_metric_scale_m_per_kn**2
            * checkpoint.previous_tangent_load_kn
            * candidate_load
        )
        if orientation < 0.0:
            candidate_displacement = -candidate_displacement
            candidate_load = -candidate_load
    return candidate_displacement, candidate_load, tangent_kn_per_m


def _correct_arc_length_trial(
    problem: ScalarArcLengthProblem,
    *,
    accepted: ScalarArcLengthCheckpoint,
    predictor_displacement: float,
    predictor_load_kn: float,
    arc_length_m: float,
    config: ScalarArcLengthConfig,
) -> dict[str, Any]:
    trial_displacement = accepted.displacement_m + predictor_displacement
    trial_load = accepted.load_kn + predictor_load_kn
    history: list[dict[str, Any]] = []
    stop_reason = "maximum_corrector_iterations_exhausted"
    converged = False
    equilibrium_residual = math.inf
    constraint_residual = math.inf
    for iteration in range(1, config.maximum_corrector_iterations + 1):
        equilibrium_residual = _finite(
            problem.internal_force_kn(trial_displacement) - trial_load,
            path="equilibrium_residual_kn",
        )
        delta_displacement = trial_displacement - accepted.displacement_m
        delta_load = trial_load - accepted.load_kn
        constraint_residual = (
            delta_displacement**2
            + (config.load_metric_scale_m_per_kn * delta_load) ** 2
            - arc_length_m**2
        )
        row: dict[str, Any] = {
            "iteration": iteration,
            "trial_displacement_m": trial_displacement,
            "trial_load_kn": trial_load,
            "equilibrium_residual_kn": equilibrium_residual,
            "constraint_residual_m2": constraint_residual,
        }
        if (
            abs(equilibrium_residual) <= config.equilibrium_tolerance_kn
            and abs(constraint_residual) <= config.constraint_tolerance_m2
        ):
            row.update(
                {
                    "converged": True,
                    "correction_displacement_m": 0.0,
                    "correction_load_kn": 0.0,
                }
            )
            history.append(row)
            converged = True
            stop_reason = "equilibrium_and_arc_constraint_converged"
            break
        tangent = _finite(
            problem.consistent_tangent_kn_per_m(trial_displacement),
            path="consistent_tangent_kn_per_m",
        )
        constraint_displacement = 2.0 * delta_displacement
        constraint_load = (
            2.0 * config.load_metric_scale_m_per_kn**2 * delta_load
        )
        determinant = tangent * constraint_load + constraint_displacement
        if abs(determinant) <= config.determinant_tolerance:
            row.update(
                {
                    "converged": False,
                    "correction_displacement_m": 0.0,
                    "correction_load_kn": 0.0,
                    "augmented_determinant": determinant,
                }
            )
            history.append(row)
            stop_reason = "augmented_newton_singular"
            break
        correction_displacement = (
            -equilibrium_residual * constraint_load - constraint_residual
        ) / determinant
        correction_load = (
            -tangent * constraint_residual
            + constraint_displacement * equilibrium_residual
        ) / determinant
        row.update(
            {
                "converged": False,
                "consistent_tangent_kn_per_m": tangent,
                "augmented_determinant": determinant,
                "correction_displacement_m": correction_displacement,
                "correction_load_kn": correction_load,
            }
        )
        history.append(row)
        trial_displacement += correction_displacement
        trial_load += correction_load
        if not math.isfinite(trial_displacement) or not math.isfinite(trial_load):
            stop_reason = "non_finite_corrector_state"
            break
    return {
        "converged": converged,
        "stop_reason": stop_reason,
        "trial_displacement_m": trial_displacement,
        "trial_load_kn": trial_load,
        "equilibrium_residual_kn": equilibrium_residual,
        "constraint_residual_m2": constraint_residual,
        "corrector_iteration_count": len(history),
        "corrector_history": history,
    }


def scalar_arc_length_continuation(
    problem: ScalarArcLengthProblem,
    *,
    config: ScalarArcLengthConfig | None = None,
    resume_from: ScalarArcLengthCheckpoint | None = None,
) -> ScalarArcLengthResult:
    """Follow a one-DOF equilibrium path through limit points."""

    cfg = config or ScalarArcLengthConfig()
    _validate_config(cfg)
    case_id = str(problem.case_id).strip()
    if not case_id:
        raise ArcLengthContractError("problem.case_id is required")
    if resume_from is None:
        accepted = create_scalar_arc_length_checkpoint(
            case_id=case_id,
            step_index=0,
            displacement_m=_finite(
                problem.initial_displacement_m(),
                path="initial_displacement_m",
            ),
            load_kn=_finite(problem.initial_load_kn(), path="initial_load_kn"),
            previous_tangent_displacement=None,
            previous_tangent_load_kn=None,
            current_arc_length_m=cfg.initial_arc_length_m,
        )
    else:
        accepted = validate_scalar_arc_length_checkpoint(
            resume_from,
            expected_case_id=case_id,
        )
    if accepted.displacement_m >= cfg.target_displacement_m:
        raise ArcLengthContractError(
            "checkpoint displacement must be below target_displacement_m"
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
        if accepted.displacement_m >= cfg.target_displacement_m:
            terminal_reason = "target_displacement_reached"
            break
        accepted_before = accepted
        tangent_displacement, tangent_load, accepted_tangent = _predictor_tangent(
            problem,
            accepted_before,
            load_metric_scale_m_per_kn=cfg.load_metric_scale_m_per_kn,
        )
        predictor_displacement = arc_length_m * tangent_displacement
        predictor_load = arc_length_m * tangent_load
        trial = _correct_arc_length_trial(
            problem,
            accepted=accepted_before,
            predictor_displacement=predictor_displacement,
            predictor_load_kn=predictor_load,
            arc_length_m=arc_length_m,
            config=cfg,
        )
        attempt: dict[str, Any] = {
            "attempt_index": attempt_index,
            "accepted_step_index_before": accepted_before.step_index,
            "accepted_state_hash_before": accepted_before.state_hash,
            "accepted_displacement_m_before": accepted_before.displacement_m,
            "accepted_load_kn_before": accepted_before.load_kn,
            "arc_length_m": arc_length_m,
            "accepted_consistent_tangent_kn_per_m": accepted_tangent,
            "predictor_tangent_displacement": tangent_displacement,
            "predictor_tangent_load_kn": tangent_load,
            "predictor_displacement_m": predictor_displacement,
            "predictor_load_kn": predictor_load,
            **trial,
            "regularization_used": False,
            "fallback_used": False,
        }
        if trial["converged"] is True:
            delta_displacement = (
                float(trial["trial_displacement_m"])
                - accepted_before.displacement_m
            )
            delta_load = float(trial["trial_load_kn"]) - accepted_before.load_kn
            accepted = create_scalar_arc_length_checkpoint(
                case_id=case_id,
                step_index=accepted_before.step_index + 1,
                displacement_m=float(trial["trial_displacement_m"]),
                load_kn=float(trial["trial_load_kn"]),
                previous_tangent_displacement=delta_displacement / arc_length_m,
                previous_tangent_load_kn=delta_load / arc_length_m,
                current_arc_length_m=arc_length_m,
            )
            checkpoints.append(accepted)
            attempt.update(
                {
                    "accepted": True,
                    "rollback_exact": True,
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_step_index_after": accepted.step_index,
                    "accepted_displacement_m_after": accepted.displacement_m,
                    "accepted_load_kn_after": accepted.load_kn,
                }
            )
        else:
            next_arc_length = arc_length_m * cfg.failed_step_reduction
            attempt.update(
                {
                    "accepted": False,
                    "rollback_exact": accepted.state_hash
                    == accepted_before.state_hash,
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_step_index_after": accepted.step_index,
                    "accepted_displacement_m_after": accepted.displacement_m,
                    "accepted_load_kn_after": accepted.load_kn,
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
        if accepted.displacement_m >= cfg.target_displacement_m:
            terminal_reason = "target_displacement_reached"

    accepted_attempts = [row for row in attempts if row["accepted"] is True]
    rejected_attempts = [row for row in attempts if row["accepted"] is False]
    displacements = [row.displacement_m for row in checkpoints]
    loads = [row.load_kn for row in checkpoints]
    tangents = [
        _finite(
            problem.consistent_tangent_kn_per_m(row.displacement_m),
            path="consistent_tangent_kn_per_m",
        )
        for row in checkpoints
    ]
    equilibrium_errors = [
        abs(
            _finite(
                problem.internal_force_kn(row.displacement_m) - row.load_kn,
                path="checkpoint_equilibrium_residual_kn",
            )
        )
        for row in checkpoints
    ]
    load_differences = [
        right - left for left, right in zip(loads, loads[1:])
    ]
    negative_load_indices = [
        index for index, value in enumerate(loads) if value < 0.0
    ]
    minimum_load_index = min(range(len(loads)), key=loads.__getitem__)
    limit_point_crossed = any(
        left > 0.0 and right < 0.0
        for left, right in zip(tangents, tangents[1:])
    )
    descending_load_branch = any(value < 0.0 for value in load_differences)
    rehardening_branch = bool(
        minimum_load_index < len(loads) - 1
        and any(value > 0.0 for value in load_differences[minimum_load_index:])
    )
    target_reached = accepted.displacement_m >= cfg.target_displacement_m
    all_rollback_exact = all(row["rollback_exact"] is True for row in attempts)
    gates_pass = bool(
        target_reached
        and accepted_attempts
        and all(row["converged"] is True for row in accepted_attempts)
        and all_rollback_exact
        and max(equilibrium_errors, default=math.inf)
        <= cfg.equilibrium_tolerance_kn
        and all(
            right > left
            for left, right in zip(displacements, displacements[1:])
        )
    )
    status = "ready" if gates_pass else "blocked"
    metrics = {
        "contract_pass": gates_pass,
        "target_displacement_reached": target_reached,
        "accepted_step_count": len(accepted_attempts),
        "rejected_step_count": len(rejected_attempts),
        "rollback_exact": all_rollback_exact,
        "fallback_count": 0,
        "regularization_count": 0,
        "maximum_checkpoint_equilibrium_residual_kn": max(
            equilibrium_errors,
            default=math.inf,
        ),
        "displacement_monotonic_increasing": all(
            right > left
            for left, right in zip(displacements, displacements[1:])
        ),
        "consistent_tangent_sign_change_observed": limit_point_crossed,
        "descending_load_branch_observed": descending_load_branch,
        "negative_load_branch_observed": bool(negative_load_indices),
        "rehardening_branch_observed": rehardening_branch,
        "maximum_load_kn": max(loads),
        "maximum_load_step_index": loads.index(max(loads)),
        "minimum_load_kn": min(loads),
        "minimum_load_step_index": minimum_load_index,
        "final_displacement_m": accepted.displacement_m,
        "final_load_kn": accepted.load_kn,
        "claim_boundary": (
            "This contract covers scalar one-DOF spherical arc-length only; it is "
            "not a multi-DOF frame/shell, Lee-frame, material-geometric, or HIP solver."
        ),
    }
    return ScalarArcLengthResult(
        status=status,
        terminal_reason=terminal_reason,
        case_id=case_id,
        config=cfg,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


__all__ = [
    "ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "ARC_LENGTH_CONSTRAINT_FORMULA",
    "ARC_LENGTH_EQUILIBRIUM_FORMULA",
    "ARC_LENGTH_SCHEMA_VERSION",
    "ArcLengthContractError",
    "ScalarArcLengthCheckpoint",
    "ScalarArcLengthConfig",
    "ScalarArcLengthProblem",
    "ScalarArcLengthResult",
    "create_scalar_arc_length_checkpoint",
    "scalar_arc_length_continuation",
    "validate_scalar_arc_length_checkpoint",
]
