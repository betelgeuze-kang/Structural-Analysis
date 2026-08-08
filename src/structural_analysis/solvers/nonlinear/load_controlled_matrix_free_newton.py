"""Load-controlled Newton continuation with a matrix-free state solver."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthLoadCoupledStateTangentProblem,
    VectorArcLengthStateTangentSolver,
    VectorArcLengthTangentSolve,
)


LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION = (
    "load-controlled-matrix-free-newton-continuation.v1"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_VERSION = (
    "load-controlled-matrix-free-newton-checkpoint.v1"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE = (
    "accepted_trial_load_controlled_matrix_free_newton.v1"
)
ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION = (
    "adaptive-load-controlled-matrix-free-newton-continuation.v1"
)
ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE = (
    "adaptive-accepted-trial-load-controlled-matrix-free-newton.v1"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY = (
    "This solver performs fixed-target load-controlled Newton steps with an "
    "external current-state tangent solver, independent linear-residual replay, "
    "strict residual-decrease line search, accepted/trial separation, and "
    "a residual-plus-increment acceptance gate, and checkpoint restart. It does "
    "not by itself establish an arc-length branch, "
    "material-state commit/rollback, a production Krylov backend, HIP parity, "
    "full-corotational frame behavior, or G1 closure."
)
PHYSICAL_RESIDUAL_MERIT_PROFILE = "half_squared_physical_residual_l2.v1"


class LoadControlledMatrixFreeNewtonError(ValueError):
    """Fail-closed continuation configuration or checkpoint error."""


@dataclass(frozen=True)
class LoadControlledMatrixFreeNewtonConfig:
    target_load_factors: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)
    residual_tolerance_inf_kn: float = 5.0e-5
    increment_absolute_tolerance_inf_m: float = 1.0e-10
    increment_relative_tolerance: float = 1.0e-4
    tangent_solve_residual_tolerance_inf_kn: float = 1.0e-7
    maximum_newton_iterations: int = 4
    maximum_line_search_backtracks: int = 6
    line_search_reduction: float = 0.5
    minimum_line_search_alpha: float = 1.0 / 64.0

    def __post_init__(self) -> None:
        targets = tuple(float(value) for value in self.target_load_factors)
        if (
            not targets
            or not all(math.isfinite(value) and value > 0.0 for value in targets)
            or any(
                targets[index] <= targets[index - 1]
                for index in range(1, len(targets))
            )
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "target_load_factors must be finite, positive, and increasing"
            )
        object.__setattr__(self, "target_load_factors", targets)
        for name, value in (
            ("residual_tolerance_inf_kn", self.residual_tolerance_inf_kn),
            (
                "increment_absolute_tolerance_inf_m",
                self.increment_absolute_tolerance_inf_m,
            ),
            (
                "increment_relative_tolerance",
                self.increment_relative_tolerance,
            ),
            (
                "tangent_solve_residual_tolerance_inf_kn",
                self.tangent_solve_residual_tolerance_inf_kn,
            ),
            ("minimum_line_search_alpha", self.minimum_line_search_alpha),
        ):
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise LoadControlledMatrixFreeNewtonError(
                    f"{name} must be finite and positive"
                )
        if (
            type(self.maximum_newton_iterations) is not int
            or self.maximum_newton_iterations < 1
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "maximum_newton_iterations must be a positive integer"
            )
        if (
            type(self.maximum_line_search_backtracks) is not int
            or self.maximum_line_search_backtracks < 0
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "maximum_line_search_backtracks must be a nonnegative integer"
            )
        if (
            not math.isfinite(float(self.line_search_reduction))
            or not 0.0 < self.line_search_reduction < 1.0
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "line_search_reduction must be between zero and one"
            )
        minimum_reachable_alpha = self.line_search_reduction ** (
            self.maximum_line_search_backtracks
        )
        if self.minimum_line_search_alpha > 1.0 or (
            self.minimum_line_search_alpha
            > minimum_reachable_alpha + 1.0e-15
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "minimum_line_search_alpha is incompatible with backtracking"
            )

    def path_contract_payload(self) -> dict[str, Any]:
        return {
            "target_load_factors": list(self.target_load_factors),
            "residual_tolerance_inf_kn": self.residual_tolerance_inf_kn,
            "increment_absolute_tolerance_inf_m": (
                self.increment_absolute_tolerance_inf_m
            ),
            "increment_relative_tolerance": (
                self.increment_relative_tolerance
            ),
            "tangent_solve_residual_tolerance_inf_kn": (
                self.tangent_solve_residual_tolerance_inf_kn
            ),
            "maximum_newton_iterations": self.maximum_newton_iterations,
            "maximum_line_search_backtracks": (
                self.maximum_line_search_backtracks
            ),
            "line_search_reduction": self.line_search_reduction,
            "minimum_line_search_alpha": self.minimum_line_search_alpha,
            "accepted_trial_policy": "immutable_accepted_copy_trial_then_commit",
            "line_search_merit": PHYSICAL_RESIDUAL_MERIT_PROFILE,
            "line_search_acceptance": (
                "strict_physical_merit_and_residual_inf_decrease"
            ),
            "step_acceptance": "residual_and_absolute_or_relative_increment",
        }


def _default_adaptive_step_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(target_load_factors=(1.0,))


@dataclass(frozen=True)
class AdaptiveLoadControlledMatrixFreeNewtonConfig:
    target_load_factor: float = 1.0
    initial_step_size: float = 1.0
    minimum_step_size: float = 0.125
    maximum_step_size: float = 1.0
    failed_step_reduction: float = 0.5
    fast_step_growth: float = 2.0
    fast_newton_solve_threshold: int = 1
    maximum_attempt_count: int = 16
    step_config: LoadControlledMatrixFreeNewtonConfig = field(
        default_factory=_default_adaptive_step_config
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("target_load_factor", self.target_load_factor),
            ("initial_step_size", self.initial_step_size),
            ("minimum_step_size", self.minimum_step_size),
            ("maximum_step_size", self.maximum_step_size),
            ("failed_step_reduction", self.failed_step_reduction),
            ("fast_step_growth", self.fast_step_growth),
        ):
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise LoadControlledMatrixFreeNewtonError(
                    f"{name} must be finite and positive"
                )
        if self.minimum_step_size > self.initial_step_size:
            raise LoadControlledMatrixFreeNewtonError(
                "minimum_step_size cannot exceed initial_step_size"
            )
        if self.initial_step_size > self.maximum_step_size:
            raise LoadControlledMatrixFreeNewtonError(
                "initial_step_size cannot exceed maximum_step_size"
            )
        if not 0.0 < self.failed_step_reduction < 1.0:
            raise LoadControlledMatrixFreeNewtonError(
                "failed_step_reduction must be between zero and one"
            )
        if self.fast_step_growth < 1.0:
            raise LoadControlledMatrixFreeNewtonError(
                "fast_step_growth must be at least one"
            )
        if (
            type(self.fast_newton_solve_threshold) is not int
            or self.fast_newton_solve_threshold < 0
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "fast_newton_solve_threshold must be nonnegative"
            )
        if (
            type(self.maximum_attempt_count) is not int
            or self.maximum_attempt_count < 1
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "maximum_attempt_count must be positive"
            )
        if self.step_config.target_load_factors != (
            float(self.target_load_factor),
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "step_config target must match target_load_factor"
            )

    def path_contract_payload(self) -> dict[str, Any]:
        return {
            "target_load_factor": self.target_load_factor,
            "initial_step_size": self.initial_step_size,
            "minimum_step_size": self.minimum_step_size,
            "maximum_step_size": self.maximum_step_size,
            "failed_step_reduction": self.failed_step_reduction,
            "fast_step_growth": self.fast_step_growth,
            "fast_newton_solve_threshold": (
                self.fast_newton_solve_threshold
            ),
            "maximum_attempt_count": self.maximum_attempt_count,
            "step_config": self.step_config.path_contract_payload(),
            "accepted_trial_policy": (
                "immutable_accepted_checkpoint_trial_then_commit_or_rollback"
            ),
            "failed_step_policy": "exact_rollback_then_step_reduction",
        }


def _finite_vector(values: Any, *, name: str, dimension: int) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise LoadControlledMatrixFreeNewtonError(
            f"{name} must be a finite FP64 vector"
        ) from exc
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise LoadControlledMatrixFreeNewtonError(
            f"{name} must be a finite FP64 vector with shape ({dimension},)"
        )
    return np.ascontiguousarray(vector, dtype=np.float64)


def _path_contract_hash(
    *,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    solver: VectorArcLengthStateTangentSolver,
    config: LoadControlledMatrixFreeNewtonConfig,
    predictor_direction_m: np.ndarray,
) -> str:
    return canonical_hash(
        {
            "profile": LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE,
            "case_id": str(problem.case_id),
            "equation_count": int(predictor_direction_m.size),
            "solver_profile": str(solver.profile),
            "solver_contract_hash": str(solver.contract_hash),
            "predictor_direction_data_hash": array_data_hash(
                predictor_direction_m
            ),
            "config": config.path_contract_payload(),
        }
    )


def _adaptive_path_contract_hash(
    *,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    solver: VectorArcLengthStateTangentSolver,
    config: AdaptiveLoadControlledMatrixFreeNewtonConfig,
    predictor_direction_m: np.ndarray,
) -> str:
    return canonical_hash(
        {
            "profile": ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE,
            "case_id": str(problem.case_id),
            "equation_count": int(predictor_direction_m.size),
            "solver_profile": str(solver.profile),
            "solver_contract_hash": str(solver.contract_hash),
            "predictor_direction_data_hash": array_data_hash(
                predictor_direction_m
            ),
            "config": config.path_contract_payload(),
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
    return canonical_hash(
        {
            "schema_version": (
                LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_VERSION
            ),
            "case_id": case_id,
            "path_contract_hash": path_contract_hash,
            "step_index": step_index,
            "load_factor": load_factor,
            "free_displacements_data_hash": array_data_hash(
                free_displacements_m
            ),
        }
    )


@dataclass(frozen=True)
class LoadControlledMatrixFreeNewtonCheckpoint:
    schema_version: str
    case_id: str
    path_contract_hash: str
    step_index: int
    load_factor: float
    free_displacements_m: np.ndarray
    state_hash: str

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_VERSION
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint schema_version is invalid"
            )
        if not str(self.case_id).strip():
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint case_id is required"
            )
        if not str(self.path_contract_hash).startswith("sha256:"):
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint path_contract_hash is invalid"
            )
        if type(self.step_index) is not int or self.step_index < 0:
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint step_index must be nonnegative"
            )
        if not math.isfinite(float(self.load_factor)):
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint load_factor must be finite"
            )
        vector = np.ascontiguousarray(
            np.asarray(self.free_displacements_m, dtype=np.float64)
        )
        if vector.ndim != 1 or not np.all(np.isfinite(vector)):
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint displacement vector must be finite"
            )
        vector.setflags(write=False)
        object.__setattr__(self, "free_displacements_m", vector)
        expected_hash = _checkpoint_state_hash(
            case_id=str(self.case_id),
            path_contract_hash=str(self.path_contract_hash),
            step_index=self.step_index,
            load_factor=float(self.load_factor),
            free_displacements_m=vector,
        )
        if self.state_hash != expected_hash:
            raise LoadControlledMatrixFreeNewtonError(
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
            "displacement_data_hash": array_data_hash(
                self.free_displacements_m
            ),
            "state_hash": self.state_hash,
        }


def create_load_controlled_matrix_free_newton_checkpoint(
    *,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    path_contract_hash: str,
    step_index: int,
    load_factor: float,
    free_displacements_m: np.ndarray,
) -> LoadControlledMatrixFreeNewtonCheckpoint:
    dimension = int(np.asarray(free_displacements_m).size)
    vector = _finite_vector(
        free_displacements_m,
        name="free_displacements_m",
        dimension=dimension,
    )
    return LoadControlledMatrixFreeNewtonCheckpoint(
        schema_version=(
            LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_VERSION
        ),
        case_id=str(problem.case_id),
        path_contract_hash=str(path_contract_hash),
        step_index=int(step_index),
        load_factor=float(load_factor),
        free_displacements_m=vector,
        state_hash=_checkpoint_state_hash(
            case_id=str(problem.case_id),
            path_contract_hash=str(path_contract_hash),
            step_index=int(step_index),
            load_factor=float(load_factor),
            free_displacements_m=vector,
        ),
    )


def _residual_kn(
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    displacements_m: np.ndarray,
    load_factor: float,
) -> np.ndarray:
    return _finite_vector(
        problem.residual_kn(displacements_m, load_factor),
        name="residual_kn",
        dimension=displacements_m.size,
    )


def _physical_residual_merit(residual_kn: np.ndarray) -> float:
    """Return 1/2 ||R||_2^2 for the declared physical residual in kN."""

    residual = np.asarray(residual_kn, dtype=np.float64)
    merit = 0.5 * float(np.dot(residual, residual))
    if not math.isfinite(merit):
        raise LoadControlledMatrixFreeNewtonError(
            "physical residual merit must be finite"
        )
    return merit


def _validate_tangent_solve(
    *,
    solve: VectorArcLengthTangentSolve,
    solver: VectorArcLengthStateTangentSolver,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    displacements_m: np.ndarray,
    load_factor: float,
    right_hand_side_kn: np.ndarray,
    tolerance_inf_kn: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if type(solve) is not VectorArcLengthTangentSolve:
        raise LoadControlledMatrixFreeNewtonError(
            "state tangent solver returned an invalid result type"
        )
    if solve.profile != solver.profile or solve.contract_hash != solver.contract_hash:
        raise LoadControlledMatrixFreeNewtonError(
            "state tangent solver binding mismatch"
        )
    solution = _finite_vector(
        solve.solution_free,
        name="tangent_solution_m",
        dimension=right_hand_side_kn.size,
    )
    action = _finite_vector(
        problem.consistent_state_tangent_action_kn_per_m(
            displacements_m,
            load_factor,
            solution,
        ),
        name="independent_tangent_action_kn",
        dimension=right_hand_side_kn.size,
    )
    explicit_residual = action - right_hand_side_kn
    explicit_inf = float(np.linalg.norm(explicit_residual, ord=np.inf))
    gate_passed = bool(solve.contract_pass and explicit_inf <= tolerance_inf_kn)
    return solution, {
        "profile": solve.profile,
        "contract_hash": solve.contract_hash,
        "contract_pass": bool(solve.contract_pass),
        "terminal_reason": str(solve.terminal_reason),
        "solution_data_hash": array_data_hash(solution),
        "independent_explicit_residual_data_hash": array_data_hash(
            explicit_residual
        ),
        "independent_explicit_residual_inf_kn": explicit_inf,
        "independent_explicit_residual_tolerance_inf_kn": tolerance_inf_kn,
        "independent_explicit_residual_gate_passed": gate_passed,
        "receipt": dict(solve.receipt),
    }


def _attempt_step(
    *,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    solver: VectorArcLengthStateTangentSolver,
    config: LoadControlledMatrixFreeNewtonConfig,
    path_contract_hash: str,
    predictor_direction_m: np.ndarray,
    accepted: LoadControlledMatrixFreeNewtonCheckpoint,
    target_load_factor: float,
) -> tuple[
    bool,
    LoadControlledMatrixFreeNewtonCheckpoint | None,
    dict[str, Any],
]:
    accepted_hash_before = accepted.state_hash
    trial = np.asarray(accepted.free_displacements_m, dtype=np.float64).copy()
    trial += (
        float(target_load_factor) - float(accepted.load_factor)
    ) * predictor_direction_m
    predictor_state_hash = array_data_hash(trial)
    history: list[dict[str, Any]] = []
    failure: str | None = None
    last_increment_inf_m = 0.0
    last_relative_increment = 0.0
    last_increment_source = "predictor_no_newton_correction"

    for newton_iteration in range(config.maximum_newton_iterations + 1):
        residual = _residual_kn(problem, trial, target_load_factor)
        residual_inf = float(np.linalg.norm(residual, ord=np.inf))
        residual_merit = _physical_residual_merit(residual)
        residual_gate_passed = bool(
            residual_inf <= config.residual_tolerance_inf_kn
        )
        absolute_increment_gate_passed = bool(
            last_increment_inf_m
            <= config.increment_absolute_tolerance_inf_m
        )
        relative_increment_gate_passed = bool(
            last_relative_increment <= config.increment_relative_tolerance
        )
        increment_gate_passed = bool(
            absolute_increment_gate_passed
            or relative_increment_gate_passed
        )
        convergence_gate_passed = bool(
            residual_gate_passed and increment_gate_passed
        )
        history_row: dict[str, Any] = {
            "newton_iteration": newton_iteration,
            "trial_state_data_hash": array_data_hash(trial),
            "residual_data_hash": array_data_hash(residual),
            "residual_inf_kn": residual_inf,
            "physical_residual_merit_half_l2_squared_kn2": residual_merit,
            "physical_residual_merit_profile": (
                PHYSICAL_RESIDUAL_MERIT_PROFILE
            ),
            "residual_gate_passed": residual_gate_passed,
            "last_increment_source": last_increment_source,
            "last_increment_inf_m": last_increment_inf_m,
            "last_relative_increment": last_relative_increment,
            "absolute_increment_gate_passed": (
                absolute_increment_gate_passed
            ),
            "relative_increment_gate_passed": (
                relative_increment_gate_passed
            ),
            "increment_gate_passed": increment_gate_passed,
            "convergence_gate_passed": convergence_gate_passed,
        }
        if convergence_gate_passed:
            history.append(history_row)
            checkpoint = create_load_controlled_matrix_free_newton_checkpoint(
                problem=problem,
                path_contract_hash=path_contract_hash,
                step_index=accepted.step_index + 1,
                load_factor=target_load_factor,
                free_displacements_m=trial,
            )
            return True, checkpoint, {
                "target_load_factor": float(target_load_factor),
                "accepted": True,
                "terminal_reason": (
                    "residual_and_increment_tolerances_satisfied"
                ),
                "predictor_state_data_hash": predictor_state_hash,
                "newton_solve_count": sum(
                    "tangent_solve" in row for row in history
                ),
                "history": history,
                "accepted_state_hash_before": accepted_hash_before,
                "accepted_state_hash_after": checkpoint.state_hash,
                "rollback_performed": False,
                "rollback_exact": True,
            }
        if newton_iteration == config.maximum_newton_iterations:
            history.append(history_row)
            failure = "maximum_newton_iterations_exhausted"
            break

        solve = solver.solve_at_state(
            problem,
            np.array(trial, dtype=np.float64, copy=True),
            -residual,
            load_factor=float(target_load_factor),
            solve_id=(
                f"load-{target_load_factor:.12g}-newton-"
                f"{newton_iteration + 1}"
            ),
        )
        correction, solve_meta = _validate_tangent_solve(
            solve=solve,
            solver=solver,
            problem=problem,
            displacements_m=trial,
            load_factor=target_load_factor,
            right_hand_side_kn=-residual,
            tolerance_inf_kn=(
                config.tangent_solve_residual_tolerance_inf_kn
            ),
        )
        history_row["tangent_solve"] = solve_meta
        history_row["accepted_iterate_tangent_refresh"] = {
            "performed": True,
            "linearization_state_data_hash": array_data_hash(trial),
            "load_factor": float(target_load_factor),
            "same_state_used_for_independent_action_replay": True,
        }
        correction_inf_m = float(
            np.linalg.norm(correction, ord=np.inf)
        )
        correction_relative_increment = float(
            correction_inf_m
            / max(
                float(np.linalg.norm(trial, ord=np.inf)),
                config.increment_absolute_tolerance_inf_m,
            )
        )
        history_row["correction_inf_m"] = correction_inf_m
        history_row["correction_relative_increment"] = (
            correction_relative_increment
        )
        history_row["correction_increment_gate_passed"] = bool(
            correction_inf_m <= config.increment_absolute_tolerance_inf_m
            or correction_relative_increment
            <= config.increment_relative_tolerance
        )
        if not solve_meta["independent_explicit_residual_gate_passed"]:
            history.append(history_row)
            failure = "tangent_solve_explicit_residual_gate_failed"
            break
        if (
            residual_gate_passed
            and history_row["correction_increment_gate_passed"]
        ):
            history_row["last_increment_source"] = (
                "computed_converged_newton_correction_not_applied"
            )
            history_row["last_increment_inf_m"] = correction_inf_m
            history_row["last_relative_increment"] = (
                correction_relative_increment
            )
            history_row["absolute_increment_gate_passed"] = bool(
                correction_inf_m
                <= config.increment_absolute_tolerance_inf_m
            )
            history_row["relative_increment_gate_passed"] = bool(
                correction_relative_increment
                <= config.increment_relative_tolerance
            )
            history_row["increment_gate_passed"] = True
            history_row["convergence_gate_passed"] = True
            history_row["accepted_without_applying_converged_correction"] = (
                True
            )
            history.append(history_row)
            checkpoint = create_load_controlled_matrix_free_newton_checkpoint(
                problem=problem,
                path_contract_hash=path_contract_hash,
                step_index=accepted.step_index + 1,
                load_factor=target_load_factor,
                free_displacements_m=trial,
            )
            return True, checkpoint, {
                "target_load_factor": float(target_load_factor),
                "accepted": True,
                "terminal_reason": (
                    "residual_and_increment_tolerances_satisfied"
                ),
                "predictor_state_data_hash": predictor_state_hash,
                "newton_solve_count": sum(
                    "tangent_solve" in row for row in history
                ),
                "history": history,
                "accepted_state_hash_before": accepted_hash_before,
                "accepted_state_hash_after": checkpoint.state_hash,
                "rollback_performed": False,
                "rollback_exact": True,
            }

        line_search_rows: list[dict[str, Any]] = []
        accepted_candidate: np.ndarray | None = None
        alpha = 1.0
        for backtrack in range(config.maximum_line_search_backtracks + 1):
            if alpha < config.minimum_line_search_alpha - 1.0e-15:
                break
            candidate = trial + alpha * correction
            candidate_residual = _residual_kn(
                problem,
                candidate,
                target_load_factor,
            )
            candidate_inf = float(
                np.linalg.norm(candidate_residual, ord=np.inf)
            )
            candidate_merit = _physical_residual_merit(candidate_residual)
            physical_merit_decreases = bool(candidate_merit < residual_merit)
            residual_inf_decreases = bool(candidate_inf < residual_inf)
            decreases = bool(
                physical_merit_decreases and residual_inf_decreases
            )
            line_search_rows.append(
                {
                    "backtrack_index": backtrack,
                    "alpha": float(alpha),
                    "candidate_state_data_hash": array_data_hash(candidate),
                    "candidate_residual_data_hash": array_data_hash(
                        candidate_residual
                    ),
                    "candidate_residual_inf_kn": candidate_inf,
                    "parent_physical_residual_merit_half_l2_squared_kn2": (
                        residual_merit
                    ),
                    "candidate_physical_residual_merit_half_l2_squared_kn2": (
                        candidate_merit
                    ),
                    "physical_residual_merit_profile": (
                        PHYSICAL_RESIDUAL_MERIT_PROFILE
                    ),
                    "strict_physical_merit_decrease": (
                        physical_merit_decreases
                    ),
                    "strict_residual_inf_decrease": residual_inf_decreases,
                    "strict_residual_decrease": decreases,
                }
            )
            if decreases:
                accepted_candidate = candidate
                break
            alpha *= config.line_search_reduction
        history_row["line_search"] = line_search_rows
        history_row["accepted_line_search_alpha"] = (
            float(line_search_rows[-1]["alpha"])
            if accepted_candidate is not None
            else None
        )
        history.append(history_row)
        if accepted_candidate is None:
            failure = "line_search_residual_decrease_failed"
            break
        accepted_increment = accepted_candidate - trial
        last_increment_inf_m = float(
            np.linalg.norm(accepted_increment, ord=np.inf)
        )
        accepted_state_inf_m = float(
            np.linalg.norm(accepted_candidate, ord=np.inf)
        )
        last_relative_increment = float(
            last_increment_inf_m
            / max(
                accepted_state_inf_m,
                config.increment_absolute_tolerance_inf_m,
            )
        )
        last_increment_source = "accepted_line_search_newton_correction"
        trial = accepted_candidate

    rollback_exact = bool(accepted.state_hash == accepted_hash_before)
    return False, None, {
        "target_load_factor": float(target_load_factor),
        "accepted": False,
        "terminal_reason": failure or "step_failed",
        "predictor_state_data_hash": predictor_state_hash,
        "newton_solve_count": sum("tangent_solve" in row for row in history),
        "history": history,
        "accepted_state_hash_before": accepted_hash_before,
        "accepted_state_hash_after": accepted.state_hash,
        "rejected_trial_state_data_hash": array_data_hash(trial),
        "rollback_performed": True,
        "rollback_exact": rollback_exact,
    }


@dataclass(frozen=True)
class LoadControlledMatrixFreeNewtonResult:
    status: str
    terminal_reason: str
    case_id: str
    path_contract_hash: str
    solver_profile: str
    solver_contract_hash: str
    config: LoadControlledMatrixFreeNewtonConfig
    initial_checkpoint: LoadControlledMatrixFreeNewtonCheckpoint
    final_checkpoint: LoadControlledMatrixFreeNewtonCheckpoint
    checkpoints: tuple[LoadControlledMatrixFreeNewtonCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    @property
    def final_free_displacements_m(self) -> np.ndarray:
        return np.array(
            self.final_checkpoint.free_displacements_m,
            dtype=np.float64,
            copy=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "solver_profile": self.solver_profile,
            "solver_contract_hash": self.solver_contract_hash,
            "config": self.config.path_contract_payload(),
            "initial_checkpoint": self.initial_checkpoint.descriptor(),
            "final_checkpoint": self.final_checkpoint.descriptor(),
            "checkpoints": [row.descriptor() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "metrics": dict(self.metrics),
            "claims": {
                "load_controlled_matrix_free_newton_path": bool(
                    self.metrics["contract_pass"]
                ),
                "current_state_tangent_solver": True,
                "accepted_iterate_tangent_refresh": bool(
                    self.metrics["accepted_iterate_tangent_refresh_count"]
                    == self.metrics["tangent_solve_count"]
                ),
                "line_search_physical_merit": True,
                "fallback_zero": bool(
                    self.metrics["fallback_count"] == 0
                    and self.metrics["regularization_count"] == 0
                ),
                "accepted_trial_displacement_state": True,
                "residual_and_increment_acceptance_gate": True,
                "failed_step_rollback_exact": bool(
                    self.metrics["failed_step_count"] > 0
                    and self.metrics["rollback_exact"]
                ),
                "checkpoint_restart_consumed": bool(
                    self.metrics["restart_checkpoint_consumed"]
                ),
                "material_state_commit_rollback": False,
                "arc_length_branch": False,
                "production_matrix_free_krylov": False,
                "rocm_hip_parity": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY,
        }


def _validate_restart_checkpoint(
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint,
    *,
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    path_contract_hash: str,
    config: LoadControlledMatrixFreeNewtonConfig,
    equation_count: int,
) -> None:
    if checkpoint.case_id != str(problem.case_id):
        raise LoadControlledMatrixFreeNewtonError(
            "checkpoint case_id mismatch"
        )
    if checkpoint.path_contract_hash != path_contract_hash:
        raise LoadControlledMatrixFreeNewtonError(
            "checkpoint path_contract_hash mismatch"
        )
    if checkpoint.free_displacements_m.size != equation_count:
        raise LoadControlledMatrixFreeNewtonError(
            "checkpoint equation_count mismatch"
        )
    allowed_loads = (0.0, *config.target_load_factors)
    matching_indices = [
        index
        for index, value in enumerate(allowed_loads)
        if math.isclose(
            checkpoint.load_factor,
            value,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ]
    if len(matching_indices) != 1 or checkpoint.step_index != matching_indices[0]:
        raise LoadControlledMatrixFreeNewtonError(
            "checkpoint step/load binding mismatch"
        )


def load_controlled_matrix_free_newton_continuation(
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    solver: VectorArcLengthStateTangentSolver,
    *,
    config: LoadControlledMatrixFreeNewtonConfig | None = None,
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint | None = None,
    predictor_direction_m: np.ndarray | None = None,
) -> LoadControlledMatrixFreeNewtonResult:
    """Run fixed-target load steps with fail-closed current-tangent solves."""

    config = config or LoadControlledMatrixFreeNewtonConfig()
    initial_displacements = np.asarray(
        problem.initial_free_displacements_m(),
        dtype=np.float64,
    )
    if initial_displacements.ndim != 1:
        raise LoadControlledMatrixFreeNewtonError(
            "problem initial displacement must be one-dimensional"
        )
    equation_count = int(initial_displacements.size)
    initial_displacements = _finite_vector(
        initial_displacements,
        name="initial_free_displacements_m",
        dimension=equation_count,
    )
    predictor_source = (
        problem.full_unit_zero_state_predictor_free_m()
        if predictor_direction_m is None
        else predictor_direction_m
    )
    predictor = _finite_vector(
        predictor_source,
        name="predictor_direction_m",
        dimension=equation_count,
    )
    if float(np.linalg.norm(predictor, ord=np.inf)) <= 0.0:
        raise LoadControlledMatrixFreeNewtonError(
            "predictor direction must be nonzero"
        )
    path_contract_hash = _path_contract_hash(
        problem=problem,
        solver=solver,
        config=config,
        predictor_direction_m=predictor,
    )
    if checkpoint is None:
        if (
            not math.isclose(
                float(problem.initial_load_factor()),
                0.0,
                rel_tol=0.0,
                abs_tol=0.0,
            )
            or float(np.linalg.norm(initial_displacements, ord=np.inf)) != 0.0
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "continuation without a checkpoint must start at zero state"
            )
        accepted = create_load_controlled_matrix_free_newton_checkpoint(
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
            equation_count=equation_count,
        )
        accepted = checkpoint
    initial_checkpoint = accepted
    checkpoints = [accepted]
    attempts: list[dict[str, Any]] = []
    terminal_reason = "target_load_factor_reached"

    for target_load_factor in config.target_load_factors:
        if target_load_factor <= accepted.load_factor + 1.0e-12:
            continue
        success, candidate, attempt = _attempt_step(
            problem=problem,
            solver=solver,
            config=config,
            path_contract_hash=path_contract_hash,
            predictor_direction_m=predictor,
            accepted=accepted,
            target_load_factor=target_load_factor,
        )
        attempt["attempt_index"] = len(attempts) + 1
        attempts.append(attempt)
        if not success:
            if not attempt["rollback_exact"]:
                raise LoadControlledMatrixFreeNewtonError(
                    "failed step did not preserve the accepted checkpoint"
                )
            terminal_reason = str(attempt["terminal_reason"])
            break
        assert candidate is not None
        accepted = candidate
        checkpoints.append(accepted)

    final_residual = _residual_kn(
        problem,
        accepted.free_displacements_m,
        accepted.load_factor,
    )
    final_residual_inf = float(np.linalg.norm(final_residual, ord=np.inf))
    target_reached = bool(
        math.isclose(
            accepted.load_factor,
            config.target_load_factors[-1],
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    )
    tangent_rows = [
        row["tangent_solve"]
        for attempt in attempts
        for row in attempt["history"]
        if "tangent_solve" in row
    ]
    tangent_history_rows = [
        row
        for attempt in attempts
        for row in attempt["history"]
        if "tangent_solve" in row
    ]
    line_search_rows = [
        candidate
        for attempt in attempts
        for row in attempt["history"]
        for candidate in row.get("line_search", [])
    ]
    failed_attempts = [row for row in attempts if not row["accepted"]]
    accepted_attempts = [row for row in attempts if row["accepted"]]
    accepted_terminal_rows = [
        row["history"][-1] for row in accepted_attempts
    ]
    fallback_count = sum(
        int(row["receipt"].get("fallback_count", 0))
        for row in tangent_rows
    )
    regularization_count = sum(
        int(row["receipt"].get("regularization_count", 0))
        for row in tangent_rows
    )
    maximum_checkpoint_residual_inf = max(
        (
            float(
                np.linalg.norm(
                    _residual_kn(
                        problem,
                        row.free_displacements_m,
                        row.load_factor,
                    ),
                    ord=np.inf,
                )
            )
            for row in checkpoints
        ),
        default=0.0,
    )
    contract_pass = bool(
        target_reached
        and final_residual_inf <= config.residual_tolerance_inf_kn
        and maximum_checkpoint_residual_inf
        <= config.residual_tolerance_inf_kn
        and all(
            row["independent_explicit_residual_gate_passed"]
            for row in tangent_rows
        )
        and all(
            row["convergence_gate_passed"]
            and row["residual_gate_passed"]
            and row["increment_gate_passed"]
            for row in accepted_terminal_rows
        )
        and all(row["rollback_exact"] for row in failed_attempts)
        and fallback_count == 0
        and regularization_count == 0
    )
    metrics = {
        "contract_pass": contract_pass,
        "equation_count": equation_count,
        "target_load_factor": config.target_load_factors[-1],
        "final_load_factor": accepted.load_factor,
        "target_load_factor_reached": target_reached,
        "accepted_step_count": len(accepted_attempts),
        "failed_step_count": len(failed_attempts),
        "checkpoint_count": len(checkpoints),
        "tangent_solve_count": len(tangent_rows),
        "accepted_iterate_tangent_refresh_count": sum(
            bool(row.get("accepted_iterate_tangent_refresh", {}).get("performed"))
            for row in tangent_history_rows
        ),
        "physical_merit_line_search_candidate_count": len(
            line_search_rows
        ),
        "physical_merit_profile": PHYSICAL_RESIDUAL_MERIT_PROFILE,
        "maximum_tangent_solve_iterations": max(
            (
                int(row["receipt"].get("iteration_count", 0))
                for row in tangent_rows
            ),
            default=0,
        ),
        "maximum_independent_tangent_residual_inf_kn": max(
            (
                float(row["independent_explicit_residual_inf_kn"])
                for row in tangent_rows
            ),
            default=0.0,
        ),
        "maximum_checkpoint_residual_inf_kn": (
            maximum_checkpoint_residual_inf
        ),
        "final_residual_inf_kn": final_residual_inf,
        "maximum_accepted_increment_inf_m": max(
            (
                float(row["last_increment_inf_m"])
                for row in accepted_terminal_rows
            ),
            default=0.0,
        ),
        "maximum_accepted_relative_increment": max(
            (
                float(row["last_relative_increment"])
                for row in accepted_terminal_rows
            ),
            default=0.0,
        ),
        "residual_and_increment_acceptance_gate": bool(
            accepted_terminal_rows
            and all(
                row["convergence_gate_passed"]
                for row in accepted_terminal_rows
            )
        ),
        "maximum_line_search_backtrack_count": max(
            (
                len(row.get("line_search", [])) - 1
                for attempt in attempts
                for row in attempt["history"]
                if "line_search" in row
            ),
            default=0,
        ),
        "minimum_accepted_line_search_alpha": min(
            (
                float(row["accepted_line_search_alpha"])
                for attempt in attempts
                for row in attempt["history"]
                if row.get("accepted_line_search_alpha") is not None
            ),
            default=1.0,
        ),
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "rollback_exact": bool(
            all(row["rollback_exact"] for row in failed_attempts)
        ),
        "restart_checkpoint_consumed": checkpoint is not None,
        "production_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "g1_full_building_closure_claim": False,
    }
    return LoadControlledMatrixFreeNewtonResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        case_id=str(problem.case_id),
        path_contract_hash=path_contract_hash,
        solver_profile=str(solver.profile),
        solver_contract_hash=str(solver.contract_hash),
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


@dataclass(frozen=True)
class AdaptiveLoadControlledMatrixFreeNewtonResult:
    status: str
    terminal_reason: str
    case_id: str
    path_contract_hash: str
    solver_profile: str
    solver_contract_hash: str
    config: AdaptiveLoadControlledMatrixFreeNewtonConfig
    initial_checkpoint: LoadControlledMatrixFreeNewtonCheckpoint
    final_checkpoint: LoadControlledMatrixFreeNewtonCheckpoint
    checkpoints: tuple[LoadControlledMatrixFreeNewtonCheckpoint, ...]
    attempts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    @property
    def final_free_displacements_m(self) -> np.ndarray:
        return np.array(
            self.final_checkpoint.free_displacements_m,
            dtype=np.float64,
            copy=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION
            ),
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "case_id": self.case_id,
            "path_contract_hash": self.path_contract_hash,
            "solver_profile": self.solver_profile,
            "solver_contract_hash": self.solver_contract_hash,
            "config": self.config.path_contract_payload(),
            "initial_checkpoint": self.initial_checkpoint.descriptor(),
            "final_checkpoint": self.final_checkpoint.descriptor(),
            "checkpoints": [row.descriptor() for row in self.checkpoints],
            "attempts": list(self.attempts),
            "metrics": dict(self.metrics),
            "claims": {
                "adaptive_load_controlled_matrix_free_newton_path": bool(
                    self.metrics["contract_pass"]
                ),
                "failed_step_reduction_exercised": bool(
                    self.metrics["failed_step_reduction_count"] > 0
                ),
                "failed_step_rollback_exact": bool(
                    self.metrics["failed_step_count"] > 0
                    and self.metrics["rollback_exact"]
                ),
                "residual_and_increment_acceptance_gate": bool(
                    self.metrics[
                        "residual_and_increment_acceptance_gate"
                    ]
                ),
                "checkpoint_restart_consumed": bool(
                    self.metrics["restart_checkpoint_consumed"]
                ),
                "fallback_zero": bool(
                    self.metrics["fallback_count"] == 0
                    and self.metrics["regularization_count"] == 0
                ),
                "material_state_commit_rollback": False,
                "arc_length_branch": False,
                "production_matrix_free_krylov": False,
                "rocm_hip_parity": False,
                "g1_full_building_closure": False,
            },
            "claim_boundary": (
                "This adaptive wrapper retries failed fixed-load Newton steps "
                "only after exact accepted-checkpoint rollback and bounded step "
                "reduction. Every committed step retains the current-tangent, "
                "explicit linear-residual, nonlinear residual, and increment "
                "gates of the load-controlled core. It does not establish an "
                "arc-length branch, material-state commit/rollback, production "
                "Krylov or HIP parity, full-corotational frame behavior, or G1 "
                "closure."
            ),
        }


def adaptive_load_controlled_matrix_free_newton_continuation(
    problem: VectorArcLengthLoadCoupledStateTangentProblem,
    solver: VectorArcLengthStateTangentSolver,
    *,
    config: AdaptiveLoadControlledMatrixFreeNewtonConfig | None = None,
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint | None = None,
    predictor_direction_m: np.ndarray | None = None,
) -> AdaptiveLoadControlledMatrixFreeNewtonResult:
    """Run adaptive fixed-load steps with exact failed-step rollback."""

    config = config or AdaptiveLoadControlledMatrixFreeNewtonConfig()
    initial_displacements = np.asarray(
        problem.initial_free_displacements_m(),
        dtype=np.float64,
    )
    if initial_displacements.ndim != 1:
        raise LoadControlledMatrixFreeNewtonError(
            "problem initial displacement must be one-dimensional"
        )
    equation_count = int(initial_displacements.size)
    initial_displacements = _finite_vector(
        initial_displacements,
        name="initial_free_displacements_m",
        dimension=equation_count,
    )
    predictor_source = (
        problem.full_unit_zero_state_predictor_free_m()
        if predictor_direction_m is None
        else predictor_direction_m
    )
    predictor = _finite_vector(
        predictor_source,
        name="predictor_direction_m",
        dimension=equation_count,
    )
    if float(np.linalg.norm(predictor, ord=np.inf)) <= 0.0:
        raise LoadControlledMatrixFreeNewtonError(
            "predictor direction must be nonzero"
        )
    path_contract_hash = _adaptive_path_contract_hash(
        problem=problem,
        solver=solver,
        config=config,
        predictor_direction_m=predictor,
    )
    if checkpoint is None:
        if (
            not math.isclose(
                float(problem.initial_load_factor()),
                0.0,
                rel_tol=0.0,
                abs_tol=0.0,
            )
            or float(np.linalg.norm(initial_displacements, ord=np.inf)) != 0.0
        ):
            raise LoadControlledMatrixFreeNewtonError(
                "adaptive continuation without a checkpoint must start at zero"
            )
        accepted = create_load_controlled_matrix_free_newton_checkpoint(
            problem=problem,
            path_contract_hash=path_contract_hash,
            step_index=0,
            load_factor=0.0,
            free_displacements_m=initial_displacements,
        )
    else:
        if checkpoint.case_id != str(problem.case_id):
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint case_id mismatch"
            )
        if checkpoint.path_contract_hash != path_contract_hash:
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint path_contract_hash mismatch"
            )
        if checkpoint.free_displacements_m.size != equation_count:
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint equation_count mismatch"
            )
        if not 0.0 <= checkpoint.load_factor <= config.target_load_factor:
            raise LoadControlledMatrixFreeNewtonError(
                "checkpoint load factor is outside the adaptive path"
            )
        accepted = checkpoint

    initial_checkpoint = accepted
    checkpoints = [accepted]
    attempts: list[dict[str, Any]] = []
    step_size = min(config.initial_step_size, config.maximum_step_size)
    terminal_reason = "maximum_attempt_count_exhausted"
    load_tolerance = float(
        16.0
        * np.finfo(np.float64).eps
        * max(1.0, abs(config.target_load_factor))
    )

    for attempt_index in range(1, config.maximum_attempt_count + 1):
        remaining = config.target_load_factor - accepted.load_factor
        if remaining <= load_tolerance:
            terminal_reason = "target_load_factor_reached"
            break
        attempted_step_size = min(step_size, remaining)
        target_load_factor = min(
            config.target_load_factor,
            accepted.load_factor + attempted_step_size,
        )
        accepted_before = accepted
        success, candidate, attempt = _attempt_step(
            problem=problem,
            solver=solver,
            config=config.step_config,
            path_contract_hash=path_contract_hash,
            predictor_direction_m=predictor,
            accepted=accepted_before,
            target_load_factor=target_load_factor,
        )
        attempt.update(
            {
                "attempt_index": attempt_index,
                "attempted_step_size": float(attempted_step_size),
                "accepted_load_factor_before": float(
                    accepted_before.load_factor
                ),
                "accepted_step_index_before": int(
                    accepted_before.step_index
                ),
            }
        )
        if success:
            assert candidate is not None
            accepted = candidate
            checkpoints.append(accepted)
            grew = bool(
                attempt["newton_solve_count"]
                <= config.fast_newton_solve_threshold
                and accepted.load_factor
                < config.target_load_factor - load_tolerance
            )
            if grew:
                step_size = min(
                    config.maximum_step_size,
                    attempted_step_size * config.fast_step_growth,
                )
            else:
                step_size = attempted_step_size
            attempt.update(
                {
                    "outcome": "committed",
                    "step_reduced": False,
                    "step_grew": grew,
                    "accepted_load_factor_after": float(
                        accepted.load_factor
                    ),
                    "accepted_step_index_after": int(accepted.step_index),
                    "next_step_size": float(step_size),
                }
            )
        else:
            if not attempt["rollback_exact"]:
                raise LoadControlledMatrixFreeNewtonError(
                    "failed adaptive step did not preserve the checkpoint"
                )
            reduced_step = attempted_step_size * config.failed_step_reduction
            attempt.update(
                {
                    "outcome": "rolled_back",
                    "step_reduced": True,
                    "step_grew": False,
                    "accepted_load_factor_after": float(
                        accepted.load_factor
                    ),
                    "accepted_step_index_after": int(accepted.step_index),
                    "next_step_size": float(reduced_step),
                }
            )
            attempts.append(attempt)
            if reduced_step + load_tolerance < config.minimum_step_size:
                terminal_reason = "minimum_step_size_exhausted"
                break
            step_size = reduced_step
            continue
        attempts.append(attempt)
    else:
        terminal_reason = "maximum_attempt_count_exhausted"

    target_reached = bool(
        abs(accepted.load_factor - config.target_load_factor)
        <= load_tolerance
    )
    if target_reached:
        terminal_reason = "target_load_factor_reached"
    final_residual = _residual_kn(
        problem,
        accepted.free_displacements_m,
        accepted.load_factor,
    )
    final_residual_inf = float(np.linalg.norm(final_residual, ord=np.inf))
    accepted_attempts = [row for row in attempts if row["accepted"]]
    failed_attempts = [row for row in attempts if not row["accepted"]]
    tangent_rows = [
        row["tangent_solve"]
        for attempt in attempts
        for row in attempt["history"]
        if "tangent_solve" in row
    ]
    fallback_count = sum(
        int(row["receipt"].get("fallback_count", 0))
        for row in tangent_rows
    )
    regularization_count = sum(
        int(row["receipt"].get("regularization_count", 0))
        for row in tangent_rows
    )
    accepted_terminal_rows = [
        row["history"][-1] for row in accepted_attempts
    ]
    maximum_checkpoint_residual_inf = max(
        (
            float(
                np.linalg.norm(
                    _residual_kn(
                        problem,
                        row.free_displacements_m,
                        row.load_factor,
                    ),
                    ord=np.inf,
                )
            )
            for row in checkpoints
        ),
        default=0.0,
    )
    increment_gate_passed = bool(
        accepted_terminal_rows
        and all(
            row["convergence_gate_passed"]
            and row["residual_gate_passed"]
            and row["increment_gate_passed"]
            for row in accepted_terminal_rows
        )
    )
    rollback_exact = bool(
        all(row["rollback_exact"] for row in failed_attempts)
    )
    contract_pass = bool(
        target_reached
        and final_residual_inf
        <= config.step_config.residual_tolerance_inf_kn
        and maximum_checkpoint_residual_inf
        <= config.step_config.residual_tolerance_inf_kn
        and increment_gate_passed
        and all(
            row["independent_explicit_residual_gate_passed"]
            for row in tangent_rows
        )
        and rollback_exact
        and fallback_count == 0
        and regularization_count == 0
    )
    metrics = {
        "contract_pass": contract_pass,
        "equation_count": equation_count,
        "target_load_factor": config.target_load_factor,
        "final_load_factor": accepted.load_factor,
        "target_load_factor_reached": target_reached,
        "attempt_count": len(attempts),
        "accepted_step_count": len(accepted_attempts),
        "failed_step_count": len(failed_attempts),
        "failed_step_reduction_count": sum(
            bool(row["step_reduced"]) for row in attempts
        ),
        "fast_step_growth_count": sum(
            bool(row["step_grew"]) for row in attempts
        ),
        "checkpoint_count": len(checkpoints),
        "tangent_solve_count": len(tangent_rows),
        "maximum_tangent_solve_iterations": max(
            (
                int(row["receipt"].get("iteration_count", 0))
                for row in tangent_rows
            ),
            default=0,
        ),
        "maximum_independent_tangent_residual_inf_kn": max(
            (
                float(row["independent_explicit_residual_inf_kn"])
                for row in tangent_rows
            ),
            default=0.0,
        ),
        "maximum_checkpoint_residual_inf_kn": (
            maximum_checkpoint_residual_inf
        ),
        "final_residual_inf_kn": final_residual_inf,
        "maximum_accepted_increment_inf_m": max(
            (
                float(row["last_increment_inf_m"])
                for row in accepted_terminal_rows
            ),
            default=0.0,
        ),
        "maximum_accepted_relative_increment": max(
            (
                float(row["last_relative_increment"])
                for row in accepted_terminal_rows
            ),
            default=0.0,
        ),
        "residual_and_increment_acceptance_gate": increment_gate_passed,
        "minimum_attempted_step_size": min(
            (float(row["attempted_step_size"]) for row in attempts),
            default=0.0,
        ),
        "maximum_attempted_step_size": max(
            (float(row["attempted_step_size"]) for row in attempts),
            default=0.0,
        ),
        "maximum_line_search_backtrack_count": max(
            (
                len(row.get("line_search", [])) - 1
                for attempt in attempts
                for row in attempt["history"]
                if "line_search" in row
            ),
            default=0,
        ),
        "minimum_accepted_line_search_alpha": min(
            (
                float(row["accepted_line_search_alpha"])
                for attempt in accepted_attempts
                for row in attempt["history"]
                if row.get("accepted_line_search_alpha") is not None
            ),
            default=1.0,
        ),
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "rollback_exact": rollback_exact,
        "restart_checkpoint_consumed": checkpoint is not None,
        "production_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "g1_full_building_closure_claim": False,
    }
    return AdaptiveLoadControlledMatrixFreeNewtonResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        case_id=str(problem.case_id),
        path_contract_hash=path_contract_hash,
        solver_profile=str(solver.profile),
        solver_contract_hash=str(solver.contract_hash),
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=accepted,
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


__all__ = [
    "ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE",
    "ADAPTIVE_LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_VERSION",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CLAIM_BOUNDARY",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_PROFILE",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION",
    "AdaptiveLoadControlledMatrixFreeNewtonConfig",
    "AdaptiveLoadControlledMatrixFreeNewtonResult",
    "LoadControlledMatrixFreeNewtonCheckpoint",
    "LoadControlledMatrixFreeNewtonConfig",
    "LoadControlledMatrixFreeNewtonError",
    "LoadControlledMatrixFreeNewtonResult",
    "adaptive_load_controlled_matrix_free_newton_continuation",
    "create_load_controlled_matrix_free_newton_checkpoint",
    "load_controlled_matrix_free_newton_continuation",
]
