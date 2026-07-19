"""Adaptive load continuation with immutable accepted checkpoints and rollback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Protocol

import numpy as np

from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    NewtonRaphsonConfig,
    VectorEquilibriumProblem,
    newton_raphson_vector,
)

CONTINUATION_SCHEMA_VERSION = "structural-analysis-adaptive-continuation.v1"
CHECKPOINT_SCHEMA_VERSION = "structural-analysis-continuation-checkpoint.v1"


class VectorLoadContinuationProblem(Protocol):
    """Factory for a vector equilibrium problem at one absolute load factor."""

    case_id: str

    def initial_free_displacements_m(self) -> np.ndarray: ...

    def problem_at_load_factor(
        self,
        load_factor: float,
        accepted_free_displacements_m: np.ndarray,
    ) -> VectorEquilibriumProblem: ...


class ContinuationContractError(ValueError):
    """Fail-closed continuation configuration or checkpoint error."""


@dataclass(frozen=True)
class ContinuationCheckpoint:
    schema_version: str
    case_id: str
    step_index: int
    load_factor: float
    free_displacements_m: tuple[float, ...]
    state_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_continuation_checkpoint(self)
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "free_displacements_m": list(self.free_displacements_m),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class AdaptiveContinuationConfig:
    target_load_factor: float = 1.0
    initial_step_size: float = 0.5
    minimum_step_size: float = 0.03125
    maximum_step_size: float = 0.5
    failed_step_reduction: float = 0.5
    fast_step_growth: float = 1.5
    fast_iteration_threshold: int = 4
    maximum_attempt_count: int = 100


@dataclass(frozen=True)
class AdaptiveContinuationResult:
    status: str
    terminal_reason: str
    case_id: str
    config: AdaptiveContinuationConfig
    newton_config: NewtonRaphsonConfig
    initial_checkpoint: ContinuationCheckpoint
    final_checkpoint: ContinuationCheckpoint
    checkpoints: tuple[ContinuationCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTINUATION_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "config": {
                "target_load_factor": self.config.target_load_factor,
                "initial_step_size": self.config.initial_step_size,
                "minimum_step_size": self.config.minimum_step_size,
                "maximum_step_size": self.config.maximum_step_size,
                "failed_step_reduction": self.config.failed_step_reduction,
                "fast_step_growth": self.config.fast_step_growth,
                "fast_iteration_threshold": self.config.fast_iteration_threshold,
                "maximum_attempt_count": self.config.maximum_attempt_count,
            },
            "newton_config": {
                "residual_tolerance": self.newton_config.residual_tolerance,
                "increment_tolerance": self.newton_config.increment_tolerance,
                "max_iterations": self.newton_config.max_iterations,
                "line_search_alphas": list(self.newton_config.line_search_alphas),
                "matrix_backend": self.newton_config.matrix_backend,
            },
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "metrics": self.metrics,
        }


def _validate_finite_vector(values: Any, *, path: str) -> tuple[float, ...]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ContinuationContractError(f"{path} must be a finite one-dimensional vector")
    return tuple(float(value) for value in array)


def _checkpoint_hash(
    *,
    case_id: str,
    step_index: int,
    load_factor: float,
    free_displacements_m: tuple[float, ...],
) -> str:
    case_bytes = case_id.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(CHECKPOINT_SCHEMA_VERSION.encode("ascii"))
    digest.update(struct.pack("<Q", len(case_bytes)))
    digest.update(case_bytes)
    digest.update(struct.pack("<QdQ", step_index, load_factor, len(free_displacements_m)))
    for value in free_displacements_m:
        digest.update(struct.pack("<d", value))
    return f"sha256:{digest.hexdigest()}"


def create_continuation_checkpoint(
    *,
    case_id: str,
    step_index: int,
    load_factor: float,
    free_displacements_m: Any,
) -> ContinuationCheckpoint:
    normalized_case_id = str(case_id).strip()
    if not normalized_case_id:
        raise ContinuationContractError("case_id is required")
    if not isinstance(step_index, int) or step_index < 0:
        raise ContinuationContractError("step_index must be a non-negative integer")
    normalized_load_factor = float(load_factor)
    if not math.isfinite(normalized_load_factor) or normalized_load_factor < 0.0:
        raise ContinuationContractError("load_factor must be finite and non-negative")
    values = _validate_finite_vector(
        free_displacements_m,
        path="free_displacements_m",
    )
    return ContinuationCheckpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        case_id=normalized_case_id,
        step_index=step_index,
        load_factor=normalized_load_factor,
        free_displacements_m=values,
        state_hash=_checkpoint_hash(
            case_id=normalized_case_id,
            step_index=step_index,
            load_factor=normalized_load_factor,
            free_displacements_m=values,
        ),
    )


def validate_continuation_checkpoint(
    checkpoint: ContinuationCheckpoint,
    *,
    expected_case_id: str | None = None,
) -> ContinuationCheckpoint:
    if not isinstance(checkpoint, ContinuationCheckpoint):
        raise ContinuationContractError("checkpoint type is invalid")
    if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise ContinuationContractError("checkpoint schema_version is invalid")
    if expected_case_id is not None and checkpoint.case_id != expected_case_id:
        raise ContinuationContractError("checkpoint case_id does not match the problem")
    expected = create_continuation_checkpoint(
        case_id=checkpoint.case_id,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        free_displacements_m=checkpoint.free_displacements_m,
    )
    if checkpoint.state_hash != expected.state_hash:
        raise ContinuationContractError("checkpoint state_hash mismatch")
    return checkpoint


def _validate_config(config: AdaptiveContinuationConfig) -> None:
    numeric_positive = {
        "target_load_factor": config.target_load_factor,
        "initial_step_size": config.initial_step_size,
        "minimum_step_size": config.minimum_step_size,
        "maximum_step_size": config.maximum_step_size,
        "failed_step_reduction": config.failed_step_reduction,
        "fast_step_growth": config.fast_step_growth,
    }
    for name, value in numeric_positive.items():
        if not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ContinuationContractError(f"{name} must be finite and positive")
    if config.minimum_step_size > config.initial_step_size:
        raise ContinuationContractError("minimum_step_size cannot exceed initial_step_size")
    if config.initial_step_size > config.maximum_step_size:
        raise ContinuationContractError("initial_step_size cannot exceed maximum_step_size")
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise ContinuationContractError("failed_step_reduction must be between zero and one")
    if config.fast_step_growth < 1.0:
        raise ContinuationContractError("fast_step_growth must be at least one")
    if config.fast_iteration_threshold < 0 or config.maximum_attempt_count < 1:
        raise ContinuationContractError("iteration and attempt limits are invalid")


def adaptive_load_continuation(
    problem: VectorLoadContinuationProblem,
    *,
    config: AdaptiveContinuationConfig | None = None,
    newton_config: NewtonRaphsonConfig | None = None,
    resume_from: ContinuationCheckpoint | None = None,
) -> AdaptiveContinuationResult:
    """Reach an absolute load target using accepted-state commit/rollback semantics."""

    cfg = config or AdaptiveContinuationConfig()
    solver_cfg = newton_config or NewtonRaphsonConfig()
    _validate_config(cfg)
    if resume_from is None:
        accepted = create_continuation_checkpoint(
            case_id=problem.case_id,
            step_index=0,
            load_factor=0.0,
            free_displacements_m=problem.initial_free_displacements_m(),
        )
    else:
        accepted = validate_continuation_checkpoint(
            resume_from,
            expected_case_id=problem.case_id,
        )
    if accepted.load_factor > cfg.target_load_factor:
        raise ContinuationContractError("checkpoint load_factor exceeds target_load_factor")

    initial_checkpoint = accepted
    checkpoints = [accepted]
    attempts: list[dict[str, Any]] = []
    step_size = min(cfg.initial_step_size, cfg.maximum_step_size)
    terminal_reason = "maximum_attempt_count_exhausted"
    tolerance = float(16.0 * np.finfo(float).eps)

    for attempt_index in range(1, cfg.maximum_attempt_count + 1):
        remaining = cfg.target_load_factor - accepted.load_factor
        if remaining <= tolerance:
            terminal_reason = "target_load_factor_reached"
            break
        attempted_step_size = min(step_size, remaining)
        trial_load_factor = min(
            cfg.target_load_factor,
            accepted.load_factor + attempted_step_size,
        )
        accepted_before = accepted
        step_problem = problem.problem_at_load_factor(
            trial_load_factor,
            np.asarray(accepted_before.free_displacements_m, dtype=float),
        )
        solution = newton_raphson_vector(step_problem, config=solver_cfg)
        metrics = solution.metrics
        trial_values = _validate_finite_vector(
            solution.free_displacements_m,
            path="trial_free_displacements_m",
        )
        trial_checkpoint = create_continuation_checkpoint(
            case_id=problem.case_id,
            step_index=accepted_before.step_index + 1,
            load_factor=trial_load_factor,
            free_displacements_m=trial_values,
        )
        terminal_disposition = str(
            metrics.get(
                "terminal_disposition",
                SOLVE_FREE_EQUATIONS_DISPOSITION,
            )
        )
        no_solve_reaction_only = bool(
            solution.status == "ready"
            and metrics.get("contract_pass") is True
            and terminal_disposition == NO_SOLVE_REACTION_ONLY_DISPOSITION
            and metrics.get("solver_executed") is False
            and metrics.get("active_equation_count") == 0
            and metrics.get("assembly_contract_valid") is True
            and metrics.get("residual_norm_applicable") is False
            and metrics.get("increment_norm_applicable") is False
            and metrics.get("residual_gate_passed") is None
            and metrics.get("increment_gate_passed") is None
            and metrics.get("convergence_claim") is False
            and metrics.get("reaction_observation_only") is True
            and metrics.get("regularization_used") is False
            and metrics.get("fallback_used") is False
        )
        iterative_solver_contract = bool(
            solution.status == "ready"
            and metrics.get("contract_pass") is True
            and terminal_disposition == SOLVE_FREE_EQUATIONS_DISPOSITION
            and metrics.get("solver_executed") is True
            and metrics.get("residual_gate_passed") is True
            and metrics.get("increment_gate_passed") is True
            and metrics.get("convergence_claim") is True
            and metrics.get("regularization_used") is False
            and metrics.get("fallback_used") is False
        )
        commit_contract_pass = bool(
            no_solve_reaction_only or iterative_solver_contract
        )
        raw_relative_residual = metrics.get("relative_residual")
        attempt = {
            "attempt_index": attempt_index,
            "accepted_step_index_before": accepted_before.step_index,
            "accepted_load_factor_before": accepted_before.load_factor,
            "trial_load_factor": trial_load_factor,
            "attempted_step_size": attempted_step_size,
            "accepted_state_hash_before": accepted_before.state_hash,
            "trial_state_hash": trial_checkpoint.state_hash,
            "solver_status": solution.status,
            "solver_detail": str(metrics.get("detail", "")),
            "solver_contract_pass": bool(metrics.get("contract_pass")),
            "terminal_disposition": terminal_disposition,
            "terminal_reason": str(metrics.get("terminal_reason", "")),
            "commit_contract_pass": commit_contract_pass,
            "iterative_solver_contract_pass": iterative_solver_contract,
            "no_solve_contract_pass": no_solve_reaction_only,
            "solver_executed": bool(metrics.get("solver_executed", True)),
            "active_equation_count": int(
                metrics.get(
                    "active_equation_count",
                    len(solution.free_displacements_m),
                )
            ),
            "residual_norm_applicable": bool(
                metrics.get("residual_norm_applicable", True)
            ),
            "increment_norm_applicable": bool(
                metrics.get("increment_norm_applicable", True)
            ),
            "residual_gate_passed": metrics.get("residual_gate_passed"),
            "increment_gate_passed": metrics.get("increment_gate_passed"),
            "convergence_claim": bool(metrics.get("convergence_claim")),
            "reaction_observation_only": bool(
                metrics.get("reaction_observation_only")
            ),
            "relative_residual": (
                None
                if raw_relative_residual is None
                else float(raw_relative_residual)
            ),
            "final_increment_abs_m": metrics.get("final_increment_abs_m"),
            "iteration_count": int(
                metrics.get(
                    "iteration_count",
                    metrics.get(
                        "newton_iteration_count",
                        len(solution.convergence_history),
                    ),
                )
            ),
            "linear_solve_count": int(metrics.get("linear_solve_count", 0)),
            "line_search_step_count": int(
                metrics.get(
                    "line_search_step_count",
                    len(solution.line_search_history),
                )
            ),
            "regularization_used": bool(metrics.get("regularization_used")),
            "fallback_used": bool(metrics.get("fallback_used")),
            "convergence_history": solution.convergence_history,
            "line_search_history": solution.line_search_history,
        }
        if commit_contract_pass:
            accepted = trial_checkpoint
            checkpoints.append(accepted)
            attempt.update(
                {
                    "outcome": "committed",
                    "committed": True,
                    "rollback_exact": None,
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_load_factor_after": accepted.load_factor,
                }
            )
            if int(metrics.get("iteration_count", 0)) <= cfg.fast_iteration_threshold:
                step_size = min(
                    cfg.maximum_step_size,
                    attempted_step_size * cfg.fast_step_growth,
                )
            else:
                step_size = attempted_step_size
        else:
            rollback_exact = bool(
                accepted is accepted_before
                and accepted.state_hash == accepted_before.state_hash
                and accepted.free_displacements_m == accepted_before.free_displacements_m
                and accepted.load_factor == accepted_before.load_factor
            )
            attempt.update(
                {
                    "outcome": "rolled_back",
                    "committed": False,
                    "rollback_exact": rollback_exact,
                    "accepted_state_hash_after": accepted.state_hash,
                    "accepted_load_factor_after": accepted.load_factor,
                }
            )
            reduced_step = attempted_step_size * cfg.failed_step_reduction
            if reduced_step + tolerance < cfg.minimum_step_size:
                attempts.append(attempt)
                terminal_reason = "minimum_step_size_exhausted"
                break
            step_size = reduced_step
        attempts.append(attempt)
    else:
        terminal_reason = "maximum_attempt_count_exhausted"

    target_reached = abs(accepted.load_factor - cfg.target_load_factor) <= tolerance
    if target_reached:
        terminal_reason = "target_load_factor_reached"
    rejected_attempts = [row for row in attempts if row["outcome"] == "rolled_back"]
    committed_attempts = [row for row in attempts if row["outcome"] == "committed"]
    fallback_count = sum(bool(row["fallback_used"]) for row in attempts)
    regularization_count = sum(bool(row["regularization_used"]) for row in attempts)
    rollback_exact_all = all(row["rollback_exact"] is True for row in rejected_attempts)
    contract_pass = bool(
        target_reached
        and committed_attempts
        and rollback_exact_all
        and fallback_count == 0
        and regularization_count == 0
        and all(row["commit_contract_pass"] for row in committed_attempts)
    )
    no_solve_attempts = [
        row for row in committed_attempts if row["no_solve_contract_pass"]
    ]
    iterative_solver_attempts = [
        row
        for row in committed_attempts
        if row["iterative_solver_contract_pass"]
    ]
    metrics = {
        "contract_pass": contract_pass,
        "target_load_factor": cfg.target_load_factor,
        "final_load_factor": accepted.load_factor,
        "target_load_factor_reached": target_reached,
        "attempt_count": len(attempts),
        "accepted_step_count": len(committed_attempts),
        "rejected_attempt_count": len(rejected_attempts),
        "rollback_exact_all": rollback_exact_all,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "no_solve_reaction_only_step_count": len(no_solve_attempts),
        "iterative_solver_step_count": len(iterative_solver_attempts),
        "solver_executed_step_count": sum(
            row["solver_executed"] is True for row in committed_attempts
        ),
        "newton_convergence_claim_count": sum(
            row["convergence_claim"] is True for row in committed_attempts
        ),
        "solver_executed": any(
            row["solver_executed"] is True for row in committed_attempts
        ),
        "convergence_claim": bool(
            committed_attempts
            and all(
                row["convergence_claim"] is True
                for row in committed_attempts
            )
        ),
        "reaction_observation_only": bool(
            committed_attempts
            and all(
                row["no_solve_contract_pass"] is True
                for row in committed_attempts
            )
        ),
        "terminal_dispositions": sorted(
            {str(row["terminal_disposition"]) for row in committed_attempts}
        ),
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "checkpoint_restart_used": resume_from is not None,
        "initial_state_hash": initial_checkpoint.state_hash,
        "final_state_hash": accepted.state_hash,
    }
    return AdaptiveContinuationResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        case_id=problem.case_id,
        config=cfg,
        newton_config=solver_cfg,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )
