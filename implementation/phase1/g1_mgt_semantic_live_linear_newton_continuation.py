#!/usr/bin/env python3
"""Fail-closed load continuation for the linear-reference G1 LIVE slice.

This module exercises accepted/trial state handling, an exact sparse tangent,
line search, adaptive load stepping, rollback, and restart checkpoints.  The
bound adapter residual is currently linear and reference-geometry based, so
the result is deliberately not nonlinear G1 closure evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import struct
from typing import Any

import numpy as np


LINEAR_NEWTON_SCHEMA_VERSION = (
    "g1-mgt-semantic-live-linear-newton-continuation.v1"
)
LINEAR_NEWTON_CHECKPOINT_SCHEMA_VERSION = (
    "g1-mgt-semantic-live-linear-newton-checkpoint.v1"
)
LINEAR_NEWTON_SOLVER_PROFILE = (
    "scipy-splu-colamd-state-invariant-cpu-diagnostic.v1"
)


class LinearReferenceNewtonContractError(ValueError):
    """Stable fail-closed configuration, checkpoint, or solver error."""


def _finite_vector(
    values: Any,
    *,
    name: str,
    dimension: int | None = None,
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise LinearReferenceNewtonContractError(
            f"{name} must be a finite one-dimensional vector"
        )
    if dimension is not None and array.size != dimension:
        raise LinearReferenceNewtonContractError(
            f"{name} dimension mismatch"
        )
    return np.array(array, dtype=np.float64, copy=True)


def _binary_hash(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values, dtype="<f8")
    return "sha256:" + hashlib.sha256(
        canonical.tobytes(order="C")
    ).hexdigest()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LinearReferenceNewtonConfig:
    target_load_factor: float = 1.0
    initial_load_increment: float = 0.25
    minimum_load_increment: float = 0.0625
    maximum_load_increment: float = 0.5
    successful_step_growth: float = 2.0
    failed_step_reduction: float = 0.5
    maximum_attempt_count: int = 16
    maximum_newton_iterations: int = 4
    residual_tolerance_n: float = 5.0e-4
    increment_tolerance_m: float = 1.0e-8
    tangent_solve_residual_tolerance_n: float = 5.0e-4
    armijo_decrease: float = 1.0e-4
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
    )

    def __post_init__(self) -> None:
        finite_positive = {
            "target_load_factor": self.target_load_factor,
            "initial_load_increment": self.initial_load_increment,
            "minimum_load_increment": self.minimum_load_increment,
            "maximum_load_increment": self.maximum_load_increment,
            "successful_step_growth": self.successful_step_growth,
            "residual_tolerance_n": self.residual_tolerance_n,
            "increment_tolerance_m": self.increment_tolerance_m,
            "tangent_solve_residual_tolerance_n": (
                self.tangent_solve_residual_tolerance_n
            ),
            "armijo_decrease": self.armijo_decrease,
        }
        for name, value in finite_positive.items():
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise LinearReferenceNewtonContractError(
                    f"{name} must be positive"
                )
        if self.minimum_load_increment > self.initial_load_increment:
            raise LinearReferenceNewtonContractError(
                "minimum_load_increment exceeds initial_load_increment"
            )
        if self.initial_load_increment > self.maximum_load_increment:
            raise LinearReferenceNewtonContractError(
                "initial_load_increment exceeds maximum_load_increment"
            )
        if not (
            math.isfinite(float(self.failed_step_reduction))
            and 0.0 < self.failed_step_reduction < 1.0
        ):
            raise LinearReferenceNewtonContractError(
                "failed_step_reduction must be in (0, 1)"
            )
        if self.successful_step_growth < 1.0:
            raise LinearReferenceNewtonContractError(
                "successful_step_growth must be at least one"
            )
        if self.maximum_attempt_count < 1:
            raise LinearReferenceNewtonContractError(
                "maximum_attempt_count must be positive"
            )
        if self.maximum_newton_iterations < 1:
            raise LinearReferenceNewtonContractError(
                "maximum_newton_iterations must be positive"
            )
        if not 0.0 < self.armijo_decrease < 1.0:
            raise LinearReferenceNewtonContractError(
                "armijo_decrease must be in (0, 1)"
            )
        if not self.line_search_alphas:
            raise LinearReferenceNewtonContractError(
                "line_search_alphas must be non-empty"
            )
        previous = math.inf
        for alpha in self.line_search_alphas:
            if (
                not math.isfinite(float(alpha))
                or alpha <= 0.0
                or alpha > 1.0
                or alpha >= previous
            ):
                raise LinearReferenceNewtonContractError(
                    "line_search_alphas must strictly decrease in (0, 1]"
                )
            previous = float(alpha)

    def path_contract_payload(self) -> dict[str, Any]:
        """Return restart-stable controls, excluding the final target."""

        return {
            "schema_version": LINEAR_NEWTON_SCHEMA_VERSION,
            "solver_profile": LINEAR_NEWTON_SOLVER_PROFILE,
            "initial_load_increment": self.initial_load_increment,
            "minimum_load_increment": self.minimum_load_increment,
            "maximum_load_increment": self.maximum_load_increment,
            "successful_step_growth": self.successful_step_growth,
            "failed_step_reduction": self.failed_step_reduction,
            "maximum_newton_iterations": self.maximum_newton_iterations,
            "residual_tolerance_n": self.residual_tolerance_n,
            "increment_tolerance_m": self.increment_tolerance_m,
            "tangent_solve_residual_tolerance_n": (
                self.tangent_solve_residual_tolerance_n
            ),
            "armijo_decrease": self.armijo_decrease,
            "line_search_alphas": list(self.line_search_alphas),
        }


def _path_contract_hash(problem: Any, config: LinearReferenceNewtonConfig) -> str:
    return _canonical_hash(
        {
            **config.path_contract_payload(),
            "case_id": str(problem.case_id),
            "equation_count": int(problem.equation_count),
            "state_invariant_tangent_contract": str(
                problem.state_invariant_tangent_contract
            ),
        }
    )


def _checkpoint_state_hash(
    *,
    case_id: str,
    path_contract_hash: str,
    step_index: int,
    load_factor: float,
    free_displacements_m: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    digest.update(case_id.encode("utf-8"))
    digest.update(path_contract_hash.encode("ascii"))
    digest.update(struct.pack("<Qd", int(step_index), float(load_factor)))
    digest.update(
        np.ascontiguousarray(
            free_displacements_m,
            dtype="<f8",
        ).tobytes(order="C")
    )
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True)
class LinearReferenceNewtonCheckpoint:
    schema_version: str
    case_id: str
    path_contract_hash: str
    step_index: int
    load_factor: float
    free_displacements_m: np.ndarray
    state_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != LINEAR_NEWTON_CHECKPOINT_SCHEMA_VERSION:
            raise LinearReferenceNewtonContractError(
                "checkpoint schema_version is invalid"
            )
        if not str(self.case_id).strip():
            raise LinearReferenceNewtonContractError(
                "checkpoint case_id is required"
            )
        if not str(self.path_contract_hash).startswith("sha256:"):
            raise LinearReferenceNewtonContractError(
                "checkpoint path_contract_hash is invalid"
            )
        if self.step_index < 0:
            raise LinearReferenceNewtonContractError(
                "checkpoint step_index must be nonnegative"
            )
        if not math.isfinite(float(self.load_factor)):
            raise LinearReferenceNewtonContractError(
                "checkpoint load_factor must be finite"
            )
        vector = _finite_vector(
            self.free_displacements_m,
            name="checkpoint.free_displacements_m",
        )
        vector.setflags(write=False)
        object.__setattr__(self, "free_displacements_m", vector)
        expected_hash = _checkpoint_state_hash(
            case_id=self.case_id,
            path_contract_hash=self.path_contract_hash,
            step_index=self.step_index,
            load_factor=self.load_factor,
            free_displacements_m=vector,
        )
        if self.state_hash != expected_hash:
            raise LinearReferenceNewtonContractError(
                "checkpoint state_hash mismatch"
            )

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "equation_count": int(self.free_displacements_m.size),
            "displacement_inf_m": float(
                np.linalg.norm(self.free_displacements_m, ord=np.inf)
            ),
            "displacement_data_hash": _binary_hash(
                self.free_displacements_m
            ),
            "state_hash": self.state_hash,
        }


def create_linear_reference_newton_checkpoint(
    *,
    problem: Any,
    path_contract_hash: str,
    step_index: int,
    load_factor: float,
    free_displacements_m: np.ndarray,
) -> LinearReferenceNewtonCheckpoint:
    vector = _finite_vector(
        free_displacements_m,
        name="free_displacements_m",
        dimension=int(problem.equation_count),
    )
    return LinearReferenceNewtonCheckpoint(
        schema_version=LINEAR_NEWTON_CHECKPOINT_SCHEMA_VERSION,
        case_id=str(problem.case_id),
        path_contract_hash=path_contract_hash,
        step_index=int(step_index),
        load_factor=float(load_factor),
        free_displacements_m=vector,
        state_hash=_checkpoint_state_hash(
            case_id=str(problem.case_id),
            path_contract_hash=path_contract_hash,
            step_index=int(step_index),
            load_factor=float(load_factor),
            free_displacements_m=vector,
        ),
    )


@dataclass(frozen=True)
class LinearReferenceNewtonResult:
    status: str
    terminal_reason: str
    case_id: str
    path_contract_hash: str
    config: LinearReferenceNewtonConfig
    initial_checkpoint: LinearReferenceNewtonCheckpoint
    final_checkpoint: LinearReferenceNewtonCheckpoint
    checkpoints: tuple[LinearReferenceNewtonCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    tangent_consistency_audit: dict[str, Any]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LINEAR_NEWTON_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "solver_profile": LINEAR_NEWTON_SOLVER_PROFILE,
            "operator_classification": (
                "state_invariant_linear_reference_geometry"
            ),
            "config": {
                **self.config.path_contract_payload(),
                "target_load_factor": self.config.target_load_factor,
                "maximum_attempt_count": (
                    self.config.maximum_attempt_count
                ),
            },
            "initial_checkpoint": self.initial_checkpoint.descriptor(),
            "final_checkpoint": self.final_checkpoint.descriptor(),
            "checkpoints": [row.descriptor() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "tangent_consistency_audit": self.tangent_consistency_audit,
            "metrics": self.metrics,
            "claims": {
                "zero_state_initial_policy": True,
                "actual_mgt_semantic_live_load": bool(
                    self.case_id
                    == "g1_real_mgt_load_coupled_arc_length_adapter"
                ),
                "state_invariant_linear_reference_tangent": True,
                "adaptive_load_stepping": bool(self.attempts),
                "line_search_history_recorded": bool(self.attempts),
                "displacement_state_commit": bool(
                    self.metrics["displacement_state_commit_count"]
                ),
                "failed_step_rollback_exact": bool(
                    self.metrics["failed_step_rollback_exercised"]
                    and self.metrics["rollback_exact"]
                ),
                "restart_checkpoint_contract": True,
                "restart_checkpoint_consumed": bool(
                    self.metrics["restart_checkpoint_consumed"]
                ),
                "full_load_linear_reference_checkpoint": bool(
                    self.status == "ready"
                    and self.config.target_load_factor >= 1.0 - 1.0e-12
                    and self.final_checkpoint.load_factor >= 1.0 - 1.0e-12
                ),
                "nonlinear_current_tangent": False,
                "quadratic_convergence": False,
                "material_state_commit_rollback": False,
                "full_arc_length_continuation": False,
                "production_matrix_free_krylov": False,
                "g1_full_load_checkpoint": False,
                "g1_full_building_closure": False,
            },
            "blockers_remaining": [
                "linear_reference_geometry_operator_only",
                "nonlinear_current_tangent_not_connected",
                "quadratic_convergence_not_demonstrated",
                "material_state_commit_rollback_not_connected",
                "actual_failed_step_rollback_not_exercised"
                if not self.metrics["failed_step_rollback_exercised"]
                else "nonlinear_failed_step_rollback_not_demonstrated",
                "arc_length_branch_not_executed",
                "production_matrix_free_krylov_not_connected",
                "production_rocm_hip_nonlinear_parity_not_verified",
                "g1_full_load_checkpoint_not_created",
            ],
            "claim_boundary": (
                "This continuation starts from zero and reaches the requested "
                "LIVE load with an exact sparse Jacobian only for the current "
                "linear reference-geometry adapter residual. It exercises "
                "Newton control flow, line search, displacement-state commit, "
                "rollback support, and restart hashes, but it is not a "
                "material/geometric nonlinear path, quadratic-convergence "
                "proof, production Krylov/HIP result, G1 checkpoint, or G1 "
                "closure."
            ),
        }


def _validate_restart_checkpoint(
    checkpoint: LinearReferenceNewtonCheckpoint,
    *,
    problem: Any,
    path_contract_hash: str,
    config: LinearReferenceNewtonConfig,
) -> None:
    if checkpoint.case_id != str(problem.case_id):
        raise LinearReferenceNewtonContractError(
            "checkpoint case_id does not match problem"
        )
    if checkpoint.path_contract_hash != path_contract_hash:
        raise LinearReferenceNewtonContractError(
            "checkpoint path contract does not match"
        )
    if checkpoint.free_displacements_m.size != int(problem.equation_count):
        raise LinearReferenceNewtonContractError(
            "checkpoint equation_count does not match"
        )
    residual = problem.residual_free_n(
        np.asarray(checkpoint.free_displacements_m, dtype=np.float64),
        float(checkpoint.load_factor),
    )
    if float(np.linalg.norm(residual, ord=np.inf)) > (
        config.residual_tolerance_n
    ):
        raise LinearReferenceNewtonContractError(
            "checkpoint equilibrium residual gate failed"
        )


def _tangent_consistency_row(
    *,
    problem: Any,
    tangent_n_per_m: Any,
    displacements_m: np.ndarray,
    load_factor: float,
    direction_m: np.ndarray,
) -> dict[str, Any]:
    csr_action_kn = np.asarray(
        tangent_n_per_m @ direction_m,
        dtype=np.float64,
    ) / 1000.0
    finite_difference_action_kn = np.asarray(
        problem.consistent_state_tangent_action_kn_per_m(
            displacements_m,
            load_factor,
            direction_m,
        ),
        dtype=np.float64,
    )
    difference = csr_action_kn - finite_difference_action_kn
    error_inf_kn = float(np.linalg.norm(difference, ord=np.inf))
    reference_inf_kn = max(
        float(np.linalg.norm(csr_action_kn, ord=np.inf)),
        1.0e-30,
    )
    relative_error = error_inf_kn / reference_inf_kn
    gate = bool(error_inf_kn <= 1.0e-4 or relative_error <= 5.0e-8)
    return {
        "load_factor": float(load_factor),
        "direction_hash": _binary_hash(direction_m),
        "csr_action_inf_kn": float(
            np.linalg.norm(csr_action_kn, ord=np.inf)
        ),
        "finite_difference_action_inf_kn": float(
            np.linalg.norm(finite_difference_action_kn, ord=np.inf)
        ),
        "error_inf_kn": error_inf_kn,
        "relative_error": relative_error,
        "absolute_tolerance_kn": 1.0e-4,
        "relative_tolerance": 5.0e-8,
        "gate_passed": gate,
    }


def _attempt_load_step(
    *,
    problem: Any,
    factorization: Any,
    tangent_n_per_m: Any,
    accepted: LinearReferenceNewtonCheckpoint,
    target_load_factor: float,
    config: LinearReferenceNewtonConfig,
    path_contract_hash: str,
) -> tuple[bool, LinearReferenceNewtonCheckpoint | None, dict[str, Any]]:
    accepted_vector = np.asarray(
        accepted.free_displacements_m,
        dtype=np.float64,
    )
    accepted_hash_before = accepted.state_hash
    trial = np.array(accepted_vector, dtype=np.float64, copy=True)
    history: list[dict[str, Any]] = []
    failure = "maximum_newton_iterations_exhausted"
    converged = False

    for iteration in range(1, config.maximum_newton_iterations + 1):
        residual_n = _finite_vector(
            problem.residual_free_n(trial, target_load_factor),
            name="residual_free_n",
            dimension=int(problem.equation_count),
        )
        residual_inf_n = float(np.linalg.norm(residual_n, ord=np.inf))
        right_hand_side_n = -residual_n
        correction_m = _finite_vector(
            factorization.solve(right_hand_side_n),
            name="newton_correction_m",
            dimension=int(problem.equation_count),
        )
        correction_inf_m = float(
            np.linalg.norm(correction_m, ord=np.inf)
        )
        linear_residual_n = np.asarray(
            tangent_n_per_m @ correction_m - right_hand_side_n,
            dtype=np.float64,
        )
        linear_residual_inf_n = float(
            np.linalg.norm(linear_residual_n, ord=np.inf)
        )
        row: dict[str, Any] = {
            "iteration": iteration,
            "trial_state_hash": _binary_hash(trial),
            "residual_inf_n": residual_inf_n,
            "correction_inf_m": correction_inf_m,
            "tangent_solve_explicit_residual_inf_n": (
                linear_residual_inf_n
            ),
            "tangent_solve_residual_gate_passed": bool(
                linear_residual_inf_n
                <= config.tangent_solve_residual_tolerance_n
            ),
            "line_search": [],
        }
        if linear_residual_inf_n > (
            config.tangent_solve_residual_tolerance_n
        ):
            row["converged"] = False
            row["failure"] = "tangent_solve_explicit_residual_gate_failed"
            history.append(row)
            failure = str(row["failure"])
            break
        if (
            residual_inf_n <= config.residual_tolerance_n
            and correction_inf_m <= config.increment_tolerance_m
        ):
            row["converged"] = True
            row["failure"] = None
            row["correction_committed"] = False
            history.append(row)
            converged = True
            failure = "equilibrium_and_increment_gates_passed"
            break

        accepted_line_search = False
        for alpha in config.line_search_alphas:
            candidate = trial + float(alpha) * correction_m
            candidate_residual_n = _finite_vector(
                problem.residual_free_n(candidate, target_load_factor),
                name="candidate_residual_free_n",
                dimension=int(problem.equation_count),
            )
            candidate_residual_inf_n = float(
                np.linalg.norm(candidate_residual_n, ord=np.inf)
            )
            sufficient_decrease = bool(
                candidate_residual_inf_n <= config.residual_tolerance_n
                or candidate_residual_inf_n
                <= residual_inf_n
                * (1.0 - config.armijo_decrease * float(alpha))
            )
            row["line_search"].append(
                {
                    "alpha": float(alpha),
                    "candidate_residual_inf_n": (
                        candidate_residual_inf_n
                    ),
                    "sufficient_decrease": sufficient_decrease,
                    "candidate_state_hash": _binary_hash(candidate),
                }
            )
            if sufficient_decrease:
                trial = candidate
                row["accepted_alpha"] = float(alpha)
                row["accepted_residual_inf_n"] = (
                    candidate_residual_inf_n
                )
                row["correction_committed"] = True
                accepted_line_search = True
                break
        row["converged"] = False
        row["failure"] = None if accepted_line_search else (
            "line_search_no_sufficient_decrease"
        )
        history.append(row)
        if not accepted_line_search:
            failure = "line_search_no_sufficient_decrease"
            break

    if converged:
        checkpoint = create_linear_reference_newton_checkpoint(
            problem=problem,
            path_contract_hash=path_contract_hash,
            step_index=accepted.step_index + 1,
            load_factor=target_load_factor,
            free_displacements_m=trial,
        )
        final_residual_inf_n = float(
            np.linalg.norm(
                problem.residual_free_n(trial, target_load_factor),
                ord=np.inf,
            )
        )
        return True, checkpoint, {
            "start_load_factor": float(accepted.load_factor),
            "target_load_factor": float(target_load_factor),
            "accepted": True,
            "terminal_reason": failure,
            "newton_iterations": len(history),
            "history": history,
            "final_residual_inf_n": final_residual_inf_n,
            "residual_gate_passed": bool(
                final_residual_inf_n <= config.residual_tolerance_n
            ),
            "increment_gate_passed": True,
            "accepted_state_hash_before": accepted_hash_before,
            "accepted_state_hash_after": checkpoint.state_hash,
            "rollback_performed": False,
            "rollback_exact": True,
        }

    rollback_exact = bool(
        accepted.state_hash == accepted_hash_before
        and np.array_equal(
            accepted.free_displacements_m,
            accepted_vector,
        )
    )
    return False, None, {
        "start_load_factor": float(accepted.load_factor),
        "target_load_factor": float(target_load_factor),
        "accepted": False,
        "terminal_reason": failure,
        "newton_iterations": len(history),
        "history": history,
        "final_residual_inf_n": (
            float(history[-1]["residual_inf_n"]) if history else None
        ),
        "residual_gate_passed": False,
        "increment_gate_passed": False,
        "accepted_state_hash_before": accepted_hash_before,
        "accepted_state_hash_after": accepted.state_hash,
        "rejected_trial_state_hash": _binary_hash(trial),
        "rollback_performed": True,
        "rollback_exact": rollback_exact,
    }


def run_linear_reference_newton_continuation(
    *,
    problem: Any,
    config: LinearReferenceNewtonConfig | None = None,
    checkpoint: LinearReferenceNewtonCheckpoint | None = None,
) -> LinearReferenceNewtonResult:
    """Run adaptive load-controlled Newton from zero or a checked restart."""

    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import splu

    config = config or LinearReferenceNewtonConfig()
    if str(problem.initial_state_policy) != "zero_state":
        raise LinearReferenceNewtonContractError(
            "problem initial_state_policy must be zero_state"
        )
    tangent_contract = str(problem.state_invariant_tangent_contract)
    if tangent_contract == "unavailable":
        raise LinearReferenceNewtonContractError(
            "state-invariant tangent is unavailable"
        )
    tangent_n_per_m = csr_matrix(
        problem.state_invariant_tangent_free_csr_n_per_m(),
        dtype=np.float64,
        copy=True,
    )
    tangent_n_per_m.sort_indices()
    if tangent_n_per_m.shape != (
        int(problem.equation_count),
        int(problem.equation_count),
    ):
        raise LinearReferenceNewtonContractError(
            "state-invariant tangent dimension mismatch"
        )
    if not np.all(np.isfinite(tangent_n_per_m.data)):
        raise LinearReferenceNewtonContractError(
            "state-invariant tangent contains non-finite values"
        )
    path_contract_hash = _path_contract_hash(problem, config)
    if checkpoint is None:
        initial_displacements = _finite_vector(
            problem.initial_free_displacements_m(),
            name="initial_free_displacements_m",
            dimension=int(problem.equation_count),
        )
        if (
            float(problem.initial_load_factor()) != 0.0
            or float(np.linalg.norm(initial_displacements, ord=np.inf)) != 0.0
        ):
            raise LinearReferenceNewtonContractError(
                "zero_state problem must start at u=0 and load_factor=0"
            )
        accepted = create_linear_reference_newton_checkpoint(
            problem=problem,
            path_contract_hash=path_contract_hash,
            step_index=0,
            load_factor=0.0,
            free_displacements_m=initial_displacements,
        )
    else:
        _validate_restart_checkpoint(
            checkpoint,
            problem=problem,
            path_contract_hash=path_contract_hash,
            config=config,
        )
        accepted = checkpoint
    initial_checkpoint = accepted
    if accepted.load_factor > config.target_load_factor + 1.0e-12:
        raise LinearReferenceNewtonContractError(
            "checkpoint load_factor exceeds target_load_factor"
        )

    try:
        factorization = splu(
            tangent_n_per_m.tocsc(),
            permc_spec="COLAMD",
        )
    except RuntimeError as exc:
        raise LinearReferenceNewtonContractError(
            "state-invariant sparse tangent factorization failed"
        ) from exc

    checkpoints = [accepted]
    attempts: list[dict[str, Any]] = []
    load_increment = min(
        config.initial_load_increment,
        max(config.target_load_factor - accepted.load_factor, 0.0),
    )
    terminal_reason = "target_load_factor_reached"

    while (
        accepted.load_factor < config.target_load_factor - 1.0e-12
        and len(attempts) < config.maximum_attempt_count
    ):
        if load_increment < config.minimum_load_increment - 1.0e-15:
            terminal_reason = "minimum_load_increment_exhausted"
            break
        target = min(
            config.target_load_factor,
            accepted.load_factor + load_increment,
        )
        success, candidate, attempt = _attempt_load_step(
            problem=problem,
            factorization=factorization,
            tangent_n_per_m=tangent_n_per_m,
            accepted=accepted,
            target_load_factor=target,
            config=config,
            path_contract_hash=path_contract_hash,
        )
        attempt["attempt_index"] = len(attempts) + 1
        attempt["requested_load_increment"] = float(load_increment)
        attempts.append(attempt)
        if success:
            assert candidate is not None
            accepted = candidate
            checkpoints.append(accepted)
            load_increment = min(
                config.maximum_load_increment,
                load_increment * config.successful_step_growth,
            )
        else:
            if not bool(attempt["rollback_exact"]):
                raise LinearReferenceNewtonContractError(
                    "failed-step rollback was not exact"
                )
            load_increment *= config.failed_step_reduction
    else:
        if accepted.load_factor < config.target_load_factor - 1.0e-12:
            terminal_reason = "maximum_attempt_count_exhausted"

    final_residual_inf_n = float(
        np.linalg.norm(
            problem.residual_free_n(
                accepted.free_displacements_m,
                accepted.load_factor,
            ),
            ord=np.inf,
        )
    )
    reached_target = bool(
        accepted.load_factor >= config.target_load_factor - 1.0e-12
    )
    all_accepted_gates = all(
        bool(row["residual_gate_passed"])
        and bool(row["increment_gate_passed"])
        for row in attempts
        if bool(row["accepted"])
    )
    rollback_exact = all(bool(row["rollback_exact"]) for row in attempts)
    status = (
        "ready"
        if reached_target
        and final_residual_inf_n <= config.residual_tolerance_n
        and all_accepted_gates
        and rollback_exact
        else "partial"
    )
    if status == "ready":
        terminal_reason = "target_load_factor_reached"

    direction = (
        problem.full_unit_zero_state_predictor_free_m()
        if getattr(problem, "zero_state_predictor_free_m", None) is not None
        else np.linspace(
            1.0,
            2.0,
            int(problem.equation_count),
            dtype=np.float64,
        )
    )
    tangent_rows = [
        _tangent_consistency_row(
            problem=problem,
            tangent_n_per_m=tangent_n_per_m,
            displacements_m=np.asarray(
                initial_checkpoint.free_displacements_m,
                dtype=np.float64,
            ),
            load_factor=initial_checkpoint.load_factor,
            direction_m=direction,
        ),
        _tangent_consistency_row(
            problem=problem,
            tangent_n_per_m=tangent_n_per_m,
            displacements_m=np.asarray(
                accepted.free_displacements_m,
                dtype=np.float64,
            ),
            load_factor=accepted.load_factor,
            direction_m=direction,
        ),
    ]
    tangent_consistency_audit = {
        "rows": tangent_rows,
        "all_gates_passed": all(
            bool(row["gate_passed"]) for row in tangent_rows
        ),
        "maximum_error_inf_kn": max(
            float(row["error_inf_kn"]) for row in tangent_rows
        ),
        "maximum_relative_error": max(
            float(row["relative_error"]) for row in tangent_rows
        ),
    }
    if not tangent_consistency_audit["all_gates_passed"]:
        status = "partial"
        terminal_reason = "tangent_consistency_gate_failed"

    accepted_attempts = [row for row in attempts if bool(row["accepted"])]
    failed_attempts = [row for row in attempts if not bool(row["accepted"])]
    line_search_rows = [
        line_row
        for attempt in attempts
        for history_row in attempt["history"]
        for line_row in history_row["line_search"]
    ]
    metrics = {
        "target_load_factor": config.target_load_factor,
        "final_load_factor": accepted.load_factor,
        "target_load_factor_reached": reached_target,
        "attempt_count": len(attempts),
        "accepted_step_count": len(accepted_attempts),
        "failed_step_count": len(failed_attempts),
        "failed_step_rollback_exercised": bool(failed_attempts),
        "rollback_exact": rollback_exact,
        "checkpoint_count": len(checkpoints),
        "restart_checkpoint_consumed": checkpoint is not None,
        "final_residual_inf_n": final_residual_inf_n,
        "residual_gate_passed": bool(
            final_residual_inf_n <= config.residual_tolerance_n
        ),
        "all_accepted_increment_gates_passed": all_accepted_gates,
        "line_search_candidate_count": len(line_search_rows),
        "minimum_accepted_line_search_alpha": min(
            (
                float(history_row["accepted_alpha"])
                for attempt in accepted_attempts
                for history_row in attempt["history"]
                if "accepted_alpha" in history_row
            ),
            default=None,
        ),
        "maximum_tangent_solve_explicit_residual_inf_n": max(
            (
                float(
                    history_row[
                        "tangent_solve_explicit_residual_inf_n"
                    ]
                )
                for attempt in attempts
                for history_row in attempt["history"]
            ),
            default=0.0,
        ),
        "fallback_count": 0,
        "regularization_count": 0,
        "material_state_commit_count": 0,
        "displacement_state_commit_count": len(accepted_attempts),
        "convergence_classification": (
            "one_correction_linear_operator"
        ),
        "quadratic_convergence_claim": False,
        "nonlinear_current_tangent_claim": False,
        "production_solver_claim": False,
    }
    return LinearReferenceNewtonResult(
        status=status,
        terminal_reason=terminal_reason,
        case_id=str(problem.case_id),
        path_contract_hash=path_contract_hash,
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        tangent_consistency_audit=tangent_consistency_audit,
        metrics=metrics,
    )


__all__ = [
    "LINEAR_NEWTON_CHECKPOINT_SCHEMA_VERSION",
    "LINEAR_NEWTON_SCHEMA_VERSION",
    "LINEAR_NEWTON_SOLVER_PROFILE",
    "LinearReferenceNewtonCheckpoint",
    "LinearReferenceNewtonConfig",
    "LinearReferenceNewtonContractError",
    "LinearReferenceNewtonResult",
    "create_linear_reference_newton_checkpoint",
    "run_linear_reference_newton_continuation",
]
