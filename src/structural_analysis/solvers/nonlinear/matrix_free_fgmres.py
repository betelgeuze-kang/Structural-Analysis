"""Matrix-free CPU FGMRES for state-tangent diagnostics.

The solver uses a fixed sparse reference-operator factor only as a right
preconditioner. Every Krylov operator application calls the problem's current
state-tangent action, and convergence is accepted only after an explicit raw
residual replay. The legacy factory owns a SciPy/SuperLU factor; the canonical
factory consumes an already validated backend-neutral sparse-LU factor and can
bind its binary artifact manifest. This local CPU path remains diagnostic: it
does not claim Engine v2 reduced-CSR identity, cross-platform deterministic
operator callbacks, production preconditioner readiness, or CPU/HIP parity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Callable

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.current_tangent_operator import (
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (
    CANONICAL_SPARSE_LU_APPLY_PROFILE,
    CanonicalSparseLUBinaryArtifactBundle,
    CanonicalSparseLUError,
    CanonicalSparseLUFactor,
    validate_canonical_sparse_lu_binary_artifact_bundle,
    validate_canonical_sparse_lu_binary_artifact_manifest,
    validate_canonical_sparse_lu_factor,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthLoadCoupledStateTangentProblem,
    VectorArcLengthStateTangentProblem,
    VectorArcLengthTangentSolve,
)


MATRIX_FREE_CPU_FGMRES_SCHEMA_VERSION = (
    "matrix-free-cpu-fgmres-state-tangent-solve.v1"
)
MATRIX_FREE_CPU_FGMRES_PROFILE = (
    "matrix_free_cpu_fgmres_fixed_reference_splu_diagnostic.v1"
)
MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE = (
    "right_preconditioned_fgmres_two_pass_modified_gram_schmidt_"
    "explicit_replay.v1"
)
MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE = (
    "ascending_index_python_fsum_fp64.v1"
)
MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION = (
    "matrix-free-current-state-tangent-operator-binding.v1"
)
MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE = (
    "zero_state_reference_csr_scipy_splu_colamd_fixed_right.v1"
)
MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE = (
    "matrix_free_cpu_fgmres_canonical_sparse_lu_fixed_right.v1"
)
MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE = (
    "canonical_sparse_lu_binary_artifact_fixed_right.v1"
)
MATRIX_FREE_CPU_FGMRES_CLAIM_BOUNDARY = (
    "This solve uses a fixed zero-state reference CSR LU as a right "
    "preconditioner while every Krylov matvec calls the current state-tangent "
    "action. Acceptance requires an independently replayed explicit residual. "
    "Its host recurrence uses the Engine v2 ascending-index Python fsum FP64 "
    "accumulation order. A callback may additionally bind its formula and "
    "parent arrays, but backend evaluation parity and SciPy SuperLU remain "
    "outside the cross-platform contract. It is a local CPU diagnostic, not an "
    "end-to-end cross-platform deterministic Engine v2 solve, a production-scale "
    "preconditioner result, CPU/HIP parity, a nonlinear continuation receipt, or "
    "G1 closure."
)
MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_CLAIM_BOUNDARY = (
    "This solve binds an immutable canonical sparse-LU factor, its ordered CPU "
    "apply contract, and optionally one validated binary artifact bundle to the "
    "actual current-state tangent operator identity. A callback may additionally "
    "bind its formula and parent arrays, but factor construction and backend "
    "operator evaluation parity remain outside the cross-platform contract; "
    "retained release transport, HIP triangular apply/parity, performance, a "
    "production nonlinear solver, and G1 closure are not established."
)


class MatrixFreeCPUFGMRESError(ValueError):
    """Fail-closed matrix-free FGMRES configuration or operator error."""


@dataclass(frozen=True)
class MatrixFreeCPUFGMRESConfig:
    max_iterations: int = 30
    restart_length: int = 12
    relative_tolerance_l2: float = 1.0e-9
    absolute_tolerance_l2_kn: float = 1.0e-11
    explicit_residual_tolerance_inf_kn: float = 1.0e-8
    arnoldi_breakdown_tolerance: float = 1.0e-14

    def __post_init__(self) -> None:
        if type(self.max_iterations) is not int or self.max_iterations < 1:
            raise MatrixFreeCPUFGMRESError(
                "max_iterations must be a positive integer"
            )
        if type(self.restart_length) is not int or self.restart_length < 1:
            raise MatrixFreeCPUFGMRESError(
                "restart_length must be a positive integer"
            )
        if self.restart_length > self.max_iterations:
            raise MatrixFreeCPUFGMRESError(
                "restart_length cannot exceed max_iterations"
            )
        for name, value, allow_zero in (
            ("relative_tolerance_l2", self.relative_tolerance_l2, True),
            (
                "absolute_tolerance_l2_kn",
                self.absolute_tolerance_l2_kn,
                True,
            ),
            (
                "explicit_residual_tolerance_inf_kn",
                self.explicit_residual_tolerance_inf_kn,
                False,
            ),
            (
                "arnoldi_breakdown_tolerance",
                self.arnoldi_breakdown_tolerance,
                False,
            ),
        ):
            normalized = float(value)
            if (
                not math.isfinite(normalized)
                or normalized < 0.0
                or (not allow_zero and normalized == 0.0)
            ):
                raise MatrixFreeCPUFGMRESError(
                    f"{name} must be finite and "
                    f"{'nonnegative' if allow_zero else 'positive'}"
                )
        if (
            self.relative_tolerance_l2 == 0.0
            and self.absolute_tolerance_l2_kn == 0.0
        ):
            raise MatrixFreeCPUFGMRESError(
                "at least one L2 convergence tolerance must be positive"
            )

    def contract_payload(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "restart_length": self.restart_length,
            "relative_tolerance_l2": self.relative_tolerance_l2,
            "absolute_tolerance_l2_kn": self.absolute_tolerance_l2_kn,
            "explicit_residual_tolerance_inf_kn": (
                self.explicit_residual_tolerance_inf_kn
            ),
            "arnoldi_breakdown_tolerance": (
                self.arnoldi_breakdown_tolerance
            ),
            "orthogonalization": "two_pass_modified_gram_schmidt_fp64",
            "recurrence_profile": (
                MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE
            ),
            "accumulation_profile": (
                MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
            ),
            "preconditioner_application": "fixed_right",
            "terminal_gate": "explicit_raw_residual_l2_and_inf",
        }


def _finite_vector(
    values: Any,
    *,
    name: str,
    dimension: int,
) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise MatrixFreeCPUFGMRESError(
            f"{name} must be a finite FP64 vector"
        ) from exc
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise MatrixFreeCPUFGMRESError(
            f"{name} must be a finite FP64 vector with shape ({dimension},)"
        )
    return np.ascontiguousarray(vector, dtype=np.float64)


def _stable_dot(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise MatrixFreeCPUFGMRESError("dot-product dimension mismatch")
    try:
        result = math.fsum(
            float(left[index]) * float(right[index])
            for index in range(left.size)
        )
    except OverflowError as exc:
        raise MatrixFreeCPUFGMRESError(
            "dot product overflowed"
        ) from exc
    if not math.isfinite(result):
        raise MatrixFreeCPUFGMRESError("dot product is non-finite")
    return result


def _stable_l2(values: np.ndarray) -> float:
    try:
        squared = math.fsum(
            float(values[index]) * float(values[index])
            for index in range(values.size)
        )
        result = math.sqrt(squared)
    except (OverflowError, ValueError) as exc:
        raise MatrixFreeCPUFGMRESError("L2 norm overflowed") from exc
    if not math.isfinite(result):
        raise MatrixFreeCPUFGMRESError("L2 norm is non-finite")
    return result


def _stable_linf(values: np.ndarray) -> float:
    return max(
        (abs(float(values[index])) for index in range(values.size)),
        default=0.0,
    )


def _stable_basis_update(
    cycle_start: np.ndarray,
    basis_z: np.ndarray,
    coefficients: np.ndarray,
    count: int,
) -> np.ndarray:
    candidate = np.empty_like(cycle_start)
    for row in range(cycle_start.size):
        candidate[row] = math.fsum(
            [float(cycle_start[row])]
            + [
                float(basis_z[row, column])
                * float(coefficients[column])
                for column in range(count)
            ]
        )
    if not np.all(np.isfinite(candidate)):
        raise MatrixFreeCPUFGMRESError(
            "candidate solution contains non-finite values"
        )
    return candidate


def _is_sha256(value: Any) -> bool:
    text = str(value)
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in text[7:])
    )


def _operator_binding_payload(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    *,
    case_id: str,
    equation_count: int,
) -> dict[str, Any]:
    accessor = getattr(
        problem,
        "matrix_free_current_tangent_operator_binding",
        None,
    )
    if not callable(accessor):
        payload = {
            "schema_version": (
                MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
            ),
            "status": "unbound",
            "case_id": case_id,
            "equation_count": equation_count,
        }
        return {
            **payload,
            "binding_hash": canonical_hash(payload),
        }
    raw = accessor()
    if raw is None:
        payload = {
            "schema_version": (
                MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
            ),
            "status": "unbound",
            "case_id": case_id,
            "equation_count": equation_count,
        }
        return {
            **payload,
            "binding_hash": canonical_hash(payload),
        }
    if not isinstance(raw, dict):
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding must be an object"
        )
    required = {
        "schema_version",
        "case_id",
        "equation_count",
        "free_equation_order_data_hash",
        "residual_formula_hash",
        "current_tangent_action_contract",
        "reference_load_free_n_data_hash",
        "residual_force_unit",
        "displacement_unit",
        "tangent_action_unit",
        "load_factor_unit",
    }
    contract_bound_fields = {
        "current_tangent_operator_profile",
        "current_tangent_operator_contract_hash",
        "current_tangent_operator_array_bundle_hash",
        "operator_callback_reference_evaluator",
        "operator_callback_outputs_in_contract",
    }
    raw_fields = set(raw)
    if raw_fields not in (required, required | contract_bound_fields):
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding fields are not exact"
        )
    if raw["schema_version"] != (
        MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
    ):
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding schema version is unsupported"
        )
    if str(raw["case_id"]) != case_id:
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding case_id mismatch"
        )
    if type(raw["equation_count"]) is not int or (
        raw["equation_count"] != equation_count
    ):
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding equation_count mismatch"
        )
    for name in (
        "free_equation_order_data_hash",
        "residual_formula_hash",
        "reference_load_free_n_data_hash",
    ):
        if not _is_sha256(raw[name]):
            raise MatrixFreeCPUFGMRESError(
                f"matrix-free operator binding {name} is invalid"
            )
    if not str(raw["current_tangent_action_contract"]).strip():
        raise MatrixFreeCPUFGMRESError(
            "matrix-free current tangent action contract is required"
        )
    expected_units = {
        "residual_force_unit": "kN",
        "displacement_unit": "m",
        "tangent_action_unit": "kN/m",
        "load_factor_unit": "dimensionless",
    }
    if any(raw[name] != value for name, value in expected_units.items()):
        raise MatrixFreeCPUFGMRESError(
            "matrix-free operator binding units are unsupported"
        )
    if contract_bound_fields <= raw_fields:
        for name in (
            "current_tangent_operator_contract_hash",
            "current_tangent_operator_array_bundle_hash",
        ):
            if not _is_sha256(raw[name]):
                raise MatrixFreeCPUFGMRESError(
                    f"matrix-free operator binding {name} is invalid"
                )
        if raw["current_tangent_operator_profile"] != (
            CURRENT_TANGENT_OPERATOR_PROFILE
        ):
            raise MatrixFreeCPUFGMRESError(
                "matrix-free current tangent operator profile is unsupported"
            )
        if raw["operator_callback_reference_evaluator"] != (
            CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
        ):
            raise MatrixFreeCPUFGMRESError(
                "matrix-free operator reference evaluator is unsupported"
            )
        if raw["operator_callback_outputs_in_contract"] is not True:
            raise MatrixFreeCPUFGMRESError(
                "matrix-free bound operator callback claim must be true"
            )
    payload = {str(key): raw[key] for key in sorted(raw)}
    return {
        **payload,
        "status": "ready",
        "binding_hash": canonical_hash(payload),
    }


def _state_tangent_action(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    displacements_m: np.ndarray,
    load_factor: float,
    direction_m: np.ndarray,
) -> np.ndarray:
    load_coupled = getattr(
        problem,
        "consistent_state_tangent_action_kn_per_m",
        None,
    )
    if callable(load_coupled):
        values = load_coupled(
            displacements_m,
            load_factor,
            direction_m,
        )
    else:
        proportional = getattr(
            problem,
            "consistent_tangent_action_kn_per_m",
            None,
        )
        if not callable(proportional):
            raise MatrixFreeCPUFGMRESError(
                "problem does not expose a state-tangent action"
            )
        values = proportional(displacements_m, direction_m)
    return _finite_vector(
        values,
        name="state_tangent_action_kn",
        dimension=direction_m.size,
    )


def _solve_upper_triangular(
    hessenberg: np.ndarray,
    projected_rhs: np.ndarray,
    count: int,
    *,
    breakdown_tolerance: float,
) -> np.ndarray | None:
    coefficients = np.zeros(count, dtype=np.float64)
    for row in range(count - 1, -1, -1):
        diagonal = float(hessenberg[row, row])
        if (
            not math.isfinite(diagonal)
            or abs(diagonal) <= breakdown_tolerance
        ):
            return None
        tail = math.fsum(
            float(hessenberg[row, column]) * float(coefficients[column])
            for column in range(row + 1, count)
        )
        coefficients[row] = (
            float(projected_rhs[row]) - tail
        ) / diagonal
    if not np.all(np.isfinite(coefficients)):
        return None
    return coefficients


def _explicit_observation(
    *,
    operator: Callable[[np.ndarray], np.ndarray],
    right_hand_side_kn: np.ndarray,
    candidate_m: np.ndarray,
    iteration: int,
    restart_index: int,
    inner_iteration: int,
    projected_residual_l2_kn: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    residual = right_hand_side_kn - operator(candidate_m)
    if not np.all(np.isfinite(residual)):
        raise MatrixFreeCPUFGMRESError(
            "explicit matrix-free residual contains non-finite values"
        )
    return residual, {
        "iteration": int(iteration),
        "restart_index": int(restart_index),
        "inner_iteration": int(inner_iteration),
        "projected_residual_l2_kn": float(projected_residual_l2_kn),
        "explicit_residual_l2_kn": _stable_l2(residual),
        "explicit_residual_inf_kn": _stable_linf(residual),
        "candidate_solution_data_hash": array_data_hash(candidate_m),
        "explicit_residual_data_hash": array_data_hash(residual),
    }


def _run_fgmres(
    *,
    operator: Callable[[np.ndarray], np.ndarray],
    preconditioner: Callable[[np.ndarray], np.ndarray],
    right_hand_side_kn: np.ndarray,
    config: MatrixFreeCPUFGMRESConfig,
) -> dict[str, Any]:
    dimension = int(right_hand_side_kn.size)
    current = np.zeros(dimension, dtype=np.float64)
    residual = right_hand_side_kn - operator(current)
    operator_action_count = 1
    explicit_residual_check_count = 1
    initial_l2 = _stable_l2(residual)
    convergence_threshold_l2_kn = max(
        config.absolute_tolerance_l2_kn,
        config.relative_tolerance_l2 * initial_l2,
    )
    initial_inf = _stable_linf(residual)
    explicit_observations: list[dict[str, Any]] = [
        {
            "iteration": 0,
            "restart_index": 0,
            "inner_iteration": 0,
            "projected_residual_l2_kn": initial_l2,
            "explicit_residual_l2_kn": initial_l2,
            "explicit_residual_inf_kn": initial_inf,
            "candidate_solution_data_hash": array_data_hash(current),
            "explicit_residual_data_hash": array_data_hash(residual),
        }
    ]
    projected_history: list[dict[str, Any]] = []
    if (
        initial_l2 <= convergence_threshold_l2_kn
        and initial_inf <= config.explicit_residual_tolerance_inf_kn
    ):
        return {
            "solution_m": current,
            "explicit_residual_kn": residual,
            "converged": True,
            "terminal_reason": "initial_explicit_residual_satisfied",
            "iteration_count": 0,
            "restart_count": 0,
            "operator_action_count": operator_action_count,
            "preconditioner_application_count": 0,
            "explicit_residual_check_count": explicit_residual_check_count,
            "convergence_threshold_l2_kn": convergence_threshold_l2_kn,
            "projected_history": projected_history,
            "explicit_observations": explicit_observations,
        }

    total_iterations = 0
    restart_index = 0
    preconditioner_application_count = 0
    terminal_reason = "max_iterations"
    converged = False
    while total_iterations < config.max_iterations and not converged:
        beta = _stable_l2(residual)
        if beta <= config.arnoldi_breakdown_tolerance:
            terminal_reason = "arnoldi_breakdown"
            break
        capacity = min(
            config.restart_length,
            config.max_iterations - total_iterations,
        )
        basis_v = np.zeros((dimension, capacity + 1), dtype=np.float64)
        basis_z = np.zeros((dimension, capacity), dtype=np.float64)
        hessenberg = np.zeros((capacity + 1, capacity), dtype=np.float64)
        cosines = np.zeros(capacity, dtype=np.float64)
        sines = np.zeros(capacity, dtype=np.float64)
        projected_rhs = np.zeros(capacity + 1, dtype=np.float64)
        basis_v[:, 0] = residual / beta
        projected_rhs[0] = beta
        cycle_start = current.copy()
        cycle_candidate: np.ndarray | None = None
        cycle_residual: np.ndarray | None = None

        for inner_index in range(capacity):
            z = _finite_vector(
                preconditioner(basis_v[:, inner_index]),
                name="preconditioned_basis_m",
                dimension=dimension,
            )
            preconditioner_application_count += 1
            basis_z[:, inner_index] = z
            work = operator(z)
            operator_action_count += 1

            for _pass in range(2):
                for basis_index in range(inner_index + 1):
                    coefficient = _stable_dot(
                        basis_v[:, basis_index],
                        work,
                    )
                    hessenberg[basis_index, inner_index] = math.fsum(
                        (
                            float(hessenberg[basis_index, inner_index]),
                            coefficient,
                        )
                    )
                    work = work - coefficient * basis_v[:, basis_index]
            next_norm = _stable_l2(work)
            hessenberg[inner_index + 1, inner_index] = next_norm
            if next_norm > config.arnoldi_breakdown_tolerance:
                basis_v[:, inner_index + 1] = work / next_norm

            for prior in range(inner_index):
                upper = hessenberg[prior, inner_index]
                lower = hessenberg[prior + 1, inner_index]
                hessenberg[prior, inner_index] = (
                    cosines[prior] * upper + sines[prior] * lower
                )
                hessenberg[prior + 1, inner_index] = (
                    -sines[prior] * upper + cosines[prior] * lower
                )
            diagonal = hessenberg[inner_index, inner_index]
            subdiagonal = hessenberg[inner_index + 1, inner_index]
            radius = math.hypot(diagonal, subdiagonal)
            if (
                not math.isfinite(radius)
                or radius <= config.arnoldi_breakdown_tolerance
            ):
                total_iterations += 1
                terminal_reason = "arnoldi_breakdown"
                break
            cosine = diagonal / radius
            sine = subdiagonal / radius
            cosines[inner_index] = cosine
            sines[inner_index] = sine
            hessenberg[inner_index, inner_index] = radius
            hessenberg[inner_index + 1, inner_index] = 0.0
            projected_value = projected_rhs[inner_index]
            projected_rhs[inner_index] = cosine * projected_value
            projected_rhs[inner_index + 1] = -sine * projected_value
            total_iterations += 1
            projected_residual_l2_kn = abs(
                float(projected_rhs[inner_index + 1])
            )
            projected_history.append(
                {
                    "iteration": total_iterations,
                    "restart_index": restart_index,
                    "inner_iteration": inner_index + 1,
                    "projected_residual_l2_kn": (
                        projected_residual_l2_kn
                    ),
                }
            )

            explicit_check_required = bool(
                projected_residual_l2_kn <= convergence_threshold_l2_kn
                or next_norm <= config.arnoldi_breakdown_tolerance
                or total_iterations == config.max_iterations
                or inner_index + 1 == capacity
            )
            if not explicit_check_required:
                continue
            coefficients = _solve_upper_triangular(
                hessenberg,
                projected_rhs,
                inner_index + 1,
                breakdown_tolerance=config.arnoldi_breakdown_tolerance,
            )
            if coefficients is None:
                terminal_reason = "projected_system_breakdown"
                break
            cycle_candidate = _stable_basis_update(
                cycle_start,
                basis_z,
                coefficients,
                inner_index + 1,
            )
            cycle_residual, observation = _explicit_observation(
                operator=operator,
                right_hand_side_kn=right_hand_side_kn,
                candidate_m=cycle_candidate,
                iteration=total_iterations,
                restart_index=restart_index,
                inner_iteration=inner_index + 1,
                projected_residual_l2_kn=projected_residual_l2_kn,
            )
            operator_action_count += 1
            explicit_residual_check_count += 1
            explicit_observations.append(observation)
            explicit_l2 = float(observation["explicit_residual_l2_kn"])
            explicit_inf = float(observation["explicit_residual_inf_kn"])
            if (
                explicit_l2 <= convergence_threshold_l2_kn
                and explicit_inf
                <= config.explicit_residual_tolerance_inf_kn
            ):
                current = cycle_candidate
                residual = cycle_residual
                converged = True
                terminal_reason = "converged_explicit_residual"
                break
            if next_norm <= config.arnoldi_breakdown_tolerance:
                current = cycle_candidate
                residual = cycle_residual
                terminal_reason = "arnoldi_breakdown"
                break
            if total_iterations == config.max_iterations:
                current = cycle_candidate
                residual = cycle_residual
                terminal_reason = "max_iterations"
                break

        if converged or total_iterations >= config.max_iterations:
            break
        if terminal_reason in {
            "arnoldi_breakdown",
            "projected_system_breakdown",
        }:
            break
        if cycle_candidate is None or cycle_residual is None:
            raise MatrixFreeCPUFGMRESError(
                "restart boundary lacks an explicit candidate"
            )
        current = cycle_candidate
        residual = cycle_residual
        restart_index += 1

    return {
        "solution_m": current,
        "explicit_residual_kn": residual,
        "converged": converged,
        "terminal_reason": terminal_reason,
        "iteration_count": total_iterations,
        "restart_count": restart_index,
        "operator_action_count": operator_action_count,
        "preconditioner_application_count": (
            preconditioner_application_count
        ),
        "explicit_residual_check_count": explicit_residual_check_count,
        "convergence_threshold_l2_kn": convergence_threshold_l2_kn,
        "projected_history": projected_history,
        "explicit_observations": explicit_observations,
    }


@dataclass(frozen=True)
class MatrixFreeCPUFGMRESStateTangentSolver:
    """Protocol-compatible fixed-reference-preconditioned state solver."""

    profile: str
    contract_hash: str
    config: MatrixFreeCPUFGMRESConfig
    case_id: str
    equation_count: int
    reference_preconditioner_contract: str
    reference_preconditioner_pattern_hash: str
    reference_preconditioner_values_hash: str
    operator_binding: Mapping[str, Any]
    preconditioner_profile: str
    preconditioner_apply_backend: str
    preconditioner_factorization_backend: str
    preconditioner_column_permutation: str
    preconditioner_factor_contract_hash: str | None
    preconditioner_binary_artifact_bundle_hash: str | None
    preconditioner_callback_outputs_in_contract: bool
    claim_boundary: str
    _factorization: Any

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
    ) -> VectorArcLengthTangentSolve:
        if str(getattr(problem, "case_id", "")) != self.case_id:
            raise MatrixFreeCPUFGMRESError(
                "problem case_id does not match the solver binding"
            )
        if int(getattr(problem, "equation_count", -1)) != self.equation_count:
            raise MatrixFreeCPUFGMRESError(
                "problem equation_count does not match the solver binding"
            )
        current_operator_binding = _operator_binding_payload(
            problem,
            case_id=self.case_id,
            equation_count=self.equation_count,
        )
        if current_operator_binding["binding_hash"] != self.operator_binding[
            "binding_hash"
        ]:
            raise MatrixFreeCPUFGMRESError(
                "problem operator binding does not match the solver binding"
            )
        if not str(solve_id).strip():
            raise MatrixFreeCPUFGMRESError("solve_id is required")
        state = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            dimension=self.equation_count,
        )
        right_hand_side = _finite_vector(
            right_hand_side_kn,
            name="right_hand_side_kn",
            dimension=self.equation_count,
        )
        normalized_load_factor = float(load_factor)
        if not math.isfinite(normalized_load_factor):
            raise MatrixFreeCPUFGMRESError("load_factor must be finite")

        def operator(direction_m: np.ndarray) -> np.ndarray:
            return _state_tangent_action(
                problem,
                state,
                normalized_load_factor,
                direction_m,
            )

        def preconditioner(vector_kn: np.ndarray) -> np.ndarray:
            if (
                self.preconditioner_profile
                == MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE
            ):
                try:
                    # The factorized CSR is N/m while the Krylov system is kN.
                    values = self._factorization.solve(vector_kn * 1000.0)
                except RuntimeError as exc:
                    raise MatrixFreeCPUFGMRESError(
                        "reference preconditioner application failed"
                    ) from exc
            elif (
                self.preconditioner_profile
                == MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE
            ):
                try:
                    values = self._factorization.solve_kn_to_m(vector_kn)
                except CanonicalSparseLUError as exc:
                    raise MatrixFreeCPUFGMRESError(
                        "canonical reference preconditioner application failed"
                    ) from exc
            else:  # pragma: no cover - factory invariant
                raise MatrixFreeCPUFGMRESError(
                    "unsupported bound preconditioner profile"
                )
            return _finite_vector(
                values,
                name="reference_preconditioner_solution_m",
                dimension=self.equation_count,
            )

        execution = _run_fgmres(
            operator=operator,
            preconditioner=preconditioner,
            right_hand_side_kn=right_hand_side,
            config=self.config,
        )
        solution = _finite_vector(
            execution["solution_m"],
            name="solution_m",
            dimension=self.equation_count,
        )
        explicit_residual = _finite_vector(
            execution["explicit_residual_kn"],
            name="explicit_residual_kn",
            dimension=self.equation_count,
        )
        explicit_l2 = _stable_l2(explicit_residual)
        explicit_inf = _stable_linf(explicit_residual)
        contract_pass = bool(
            execution["converged"]
            and explicit_l2 <= execution["convergence_threshold_l2_kn"]
            and explicit_inf
            <= self.config.explicit_residual_tolerance_inf_kn
        )
        state_hash = canonical_hash(
            {
                "case_id": self.case_id,
                "free_displacements_data_hash": array_data_hash(state),
                "load_factor": normalized_load_factor,
            }
        )
        state_operator_binding_hash = canonical_hash(
            {
                "operator_binding_hash": self.operator_binding[
                    "binding_hash"
                ],
                "state_hash": state_hash,
                "right_hand_side_data_hash": array_data_hash(
                    right_hand_side
                ),
            }
        )
        if (
            self.preconditioner_profile
            == MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE
        ):
            preconditioner_receipt = {
                "profile": self.preconditioner_profile,
                "source_contract": self.reference_preconditioner_contract,
                "pattern_hash": self.reference_preconditioner_pattern_hash,
                "numeric_values_hash": (
                    self.reference_preconditioner_values_hash
                ),
                "factorization": self.preconditioner_factorization_backend,
                "permc_spec": self.preconditioner_column_permutation,
                "fixed_right_preconditioner": True,
                "reference_operator_force_unit": "N",
                "krylov_force_unit": "kN",
                "right_hand_side_conversion_to_reference_force": 1000.0,
                "current_jacobian_claim": False,
                "production_preconditioner_claim": False,
            }
        else:
            preconditioner_receipt = {
                "profile": self.preconditioner_profile,
                "source_contract": self.reference_preconditioner_contract,
                "pattern_hash": self.reference_preconditioner_pattern_hash,
                "numeric_values_hash": (
                    self.reference_preconditioner_values_hash
                ),
                "factorization": self.preconditioner_factorization_backend,
                "permc_spec": self.preconditioner_column_permutation,
                "apply_backend": self.preconditioner_apply_backend,
                "apply_profile": CANONICAL_SPARSE_LU_APPLY_PROFILE,
                "factor_contract_hash": (
                    self.preconditioner_factor_contract_hash
                ),
                "binary_artifact_bundle_hash": (
                    self.preconditioner_binary_artifact_bundle_hash
                ),
                "binary_artifact_bundle_bound": bool(
                    self.preconditioner_binary_artifact_bundle_hash
                ),
                "fixed_right_preconditioner": True,
                "reference_operator_force_unit": "N",
                "krylov_force_unit": "kN",
                "right_hand_side_conversion_to_reference_force": 1000.0,
                "current_jacobian_claim": False,
                "deterministic_factor_construction_claim": False,
                "retained_release_artifact_claim": False,
                "production_preconditioner_claim": False,
            }
        receipt = {
            "schema_version": MATRIX_FREE_CPU_FGMRES_SCHEMA_VERSION,
            "status": "ready" if contract_pass else "blocked",
            "contract_pass": contract_pass,
            "profile": self.profile,
            "contract_hash": self.contract_hash,
            "solve_id": str(solve_id),
            "case_id": self.case_id,
            "state_hash": state_hash,
            "state_operator_binding_hash": state_operator_binding_hash,
            "operator_binding": dict(self.operator_binding),
            "load_factor": normalized_load_factor,
            "equation_count": self.equation_count,
            "right_hand_side_data_hash": array_data_hash(right_hand_side),
            "right_hand_side_l2_kn": _stable_l2(right_hand_side),
            "right_hand_side_inf_kn": _stable_linf(right_hand_side),
            "solution_data_hash": array_data_hash(solution),
            "explicit_residual_data_hash": array_data_hash(
                explicit_residual
            ),
            "converged": bool(execution["converged"]),
            "terminal_reason": str(execution["terminal_reason"]),
            "iteration_count": int(execution["iteration_count"]),
            "restart_count": int(execution["restart_count"]),
            "operator_action_count": int(
                execution["operator_action_count"]
            ),
            "preconditioner_application_count": int(
                execution["preconditioner_application_count"]
            ),
            "explicit_residual_check_count": int(
                execution["explicit_residual_check_count"]
            ),
            "convergence_threshold_l2_kn": float(
                execution["convergence_threshold_l2_kn"]
            ),
            "explicit_residual_l2_kn": explicit_l2,
            "explicit_residual_inf_kn": explicit_inf,
            "explicit_residual_tolerance_inf_kn": (
                self.config.explicit_residual_tolerance_inf_kn
            ),
            "projected_history": execution["projected_history"],
            "explicit_observations": execution["explicit_observations"],
            "preconditioner": preconditioner_receipt,
            "matrix_free_current_state_operator_action": True,
            "materialized_current_tangent": False,
            "fallback_count": 0,
            "regularization_count": 0,
            "recurrence": {
                "profile": MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
                "accumulation_profile": (
                    MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
                ),
                "dot_norm_order": "ascending_free_equation_index",
                "projected_solve": (
                    "descending_index_python_fsum_back_substitution"
                ),
                "basis_update": (
                    "ascending_free_equation_index_python_fsum"
                ),
                "deterministic_host_arithmetic": True,
                "operator_callback_outputs_in_contract": bool(
                    self.operator_binding.get(
                        "operator_callback_outputs_in_contract",
                        False,
                    )
                ),
                "preconditioner_callback_outputs_in_contract": (
                    self.preconditioner_callback_outputs_in_contract
                ),
            },
            "operator_binding_ready": bool(
                self.operator_binding["status"] == "ready"
            ),
            "deterministic_host_recurrence_arithmetic_claim": True,
            "cross_platform_deterministic_recurrence_claim": False,
            "production_solver_claim": False,
            "rocm_hip_parity_claim": False,
            "promotes_g1_closure": False,
            "config": self.config.contract_payload(),
            "claim_boundary": self.claim_boundary,
        }
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=contract_pass,
            terminal_reason=str(execution["terminal_reason"]),
            solution_free=tuple(float(value) for value in solution),
            receipt=receipt,
        )


def _reference_preconditioner_binding(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
) -> tuple[str, int, str, Any, str, str, Mapping[str, Any]]:
    """Validate and hash the problem's fixed reference preconditioner CSR."""

    from scipy.sparse import csr_matrix

    case_id = str(getattr(problem, "case_id", "")).strip()
    equation_count = int(getattr(problem, "equation_count", -1))
    if not case_id or equation_count < 1:
        raise MatrixFreeCPUFGMRESError(
            "problem must expose case_id and positive equation_count"
        )
    accessor = getattr(
        problem,
        "reference_preconditioner_free_csr_n_per_m",
        None,
    )
    if not callable(accessor):
        raise MatrixFreeCPUFGMRESError(
            "problem does not expose a reference preconditioner CSR"
        )
    source_contract = str(
        getattr(problem, "reference_preconditioner_contract", "")
    ).strip()
    if not source_contract or source_contract == "unavailable":
        raise MatrixFreeCPUFGMRESError(
            "problem reference preconditioner contract is unavailable"
        )
    reference = csr_matrix(accessor(), dtype=np.float64, copy=True)
    reference.sort_indices()
    if reference.shape != (equation_count, equation_count):
        raise MatrixFreeCPUFGMRESError(
            "reference preconditioner dimension mismatch"
        )
    if reference.nnz < 1 or not np.all(np.isfinite(reference.data)):
        raise MatrixFreeCPUFGMRESError(
            "reference preconditioner must be finite and nonempty"
        )
    if np.count_nonzero(reference.diagonal() == 0.0):
        raise MatrixFreeCPUFGMRESError(
            "reference preconditioner has a zero diagonal"
        )
    pattern_hash = canonical_hash(
        {
            "row_pointer_hash": array_data_hash(
                np.asarray(reference.indptr, dtype="<i8")
            ),
            "column_index_hash": array_data_hash(
                np.asarray(reference.indices, dtype="<i8")
            ),
            "shape": [equation_count, equation_count],
        }
    )
    values_hash = array_data_hash(
        np.asarray(reference.data, dtype="<f8")
    )
    operator_binding = _operator_binding_payload(
        problem,
        case_id=case_id,
        equation_count=equation_count,
    )
    return (
        case_id,
        equation_count,
        source_contract,
        reference,
        pattern_hash,
        values_hash,
        MappingProxyType(dict(operator_binding)),
    )


def create_matrix_free_cpu_fgmres_state_tangent_solver(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    *,
    config: MatrixFreeCPUFGMRESConfig | None = None,
) -> MatrixFreeCPUFGMRESStateTangentSolver:
    """Factor the problem's fixed reference CSR and bind one state solver."""

    from scipy.sparse.linalg import splu

    config = config or MatrixFreeCPUFGMRESConfig()
    (
        case_id,
        equation_count,
        source_contract,
        reference,
        pattern_hash,
        values_hash,
        operator_binding,
    ) = _reference_preconditioner_binding(problem)
    try:
        factorization = splu(
            reference.tocsc(),
            permc_spec="COLAMD",
        )
    except RuntimeError as exc:
        raise MatrixFreeCPUFGMRESError(
            "reference preconditioner factorization failed"
        ) from exc
    contract_hash = canonical_hash(
        {
            "profile": MATRIX_FREE_CPU_FGMRES_PROFILE,
            "case_id": case_id,
            "equation_count": equation_count,
            "reference_preconditioner_contract": source_contract,
            "reference_preconditioner_pattern_hash": pattern_hash,
            "reference_preconditioner_values_hash": values_hash,
            "preconditioner_profile": (
                MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE
            ),
            "operator_binding_hash": operator_binding["binding_hash"],
            "config": config.contract_payload(),
            "production_solver_claim": False,
        }
    )
    return MatrixFreeCPUFGMRESStateTangentSolver(
        profile=MATRIX_FREE_CPU_FGMRES_PROFILE,
        contract_hash=contract_hash,
        config=config,
        case_id=case_id,
        equation_count=equation_count,
        reference_preconditioner_contract=source_contract,
        reference_preconditioner_pattern_hash=pattern_hash,
        reference_preconditioner_values_hash=values_hash,
        operator_binding=operator_binding,
        preconditioner_profile=(
            MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE
        ),
        preconditioner_apply_backend="scipy_superlu_solve",
        preconditioner_factorization_backend="scipy.sparse.linalg.splu",
        preconditioner_column_permutation="COLAMD",
        preconditioner_factor_contract_hash=None,
        preconditioner_binary_artifact_bundle_hash=None,
        preconditioner_callback_outputs_in_contract=False,
        claim_boundary=MATRIX_FREE_CPU_FGMRES_CLAIM_BOUNDARY,
        _factorization=factorization,
    )


def create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
    problem: (
        VectorArcLengthStateTangentProblem
        | VectorArcLengthLoadCoupledStateTangentProblem
    ),
    *,
    factor: CanonicalSparseLUFactor,
    binary_artifact_manifest: (
        Mapping[str, Any] | CanonicalSparseLUBinaryArtifactBundle | None
    ) = None,
    config: MatrixFreeCPUFGMRESConfig | None = None,
) -> MatrixFreeCPUFGMRESStateTangentSolver:
    """Bind one validated canonical sparse-LU factor to a state solver.

    This factory never constructs or refactors the reference operator. The
    supplied factor must identify the exact reference CSR pattern and numeric
    bytes exposed by ``problem``. When a binary artifact bundle or manifest is
    supplied, its bundle hash is also included in the solver contract.
    """

    config = config or MatrixFreeCPUFGMRESConfig()
    (
        case_id,
        equation_count,
        source_contract,
        _reference,
        pattern_hash,
        values_hash,
        operator_binding,
    ) = _reference_preconditioner_binding(problem)
    try:
        canonical_factor = validate_canonical_sparse_lu_factor(factor)
    except CanonicalSparseLUError as exc:
        raise MatrixFreeCPUFGMRESError(
            "canonical reference preconditioner factor is invalid"
        ) from exc
    if canonical_factor.dimension != equation_count:
        raise MatrixFreeCPUFGMRESError(
            "canonical reference preconditioner dimension mismatch"
        )
    if (
        canonical_factor.source_operator_pattern_hash != pattern_hash
        or canonical_factor.source_operator_numeric_values_hash != values_hash
    ):
        raise MatrixFreeCPUFGMRESError(
            "canonical reference preconditioner source binding mismatch"
        )

    binary_bundle_hash: str | None = None
    if binary_artifact_manifest is not None:
        try:
            if isinstance(
                binary_artifact_manifest,
                CanonicalSparseLUBinaryArtifactBundle,
            ):
                validated_bundle = (
                    validate_canonical_sparse_lu_binary_artifact_bundle(
                        binary_artifact_manifest
                    )
                )
                manifest = validated_bundle.to_manifest()
            elif isinstance(binary_artifact_manifest, Mapping):
                manifest = (
                    validate_canonical_sparse_lu_binary_artifact_manifest(
                        dict(binary_artifact_manifest)
                    )
                )
            else:
                raise CanonicalSparseLUError(
                    "binary artifact manifest must be an object"
                )
        except CanonicalSparseLUError as exc:
            raise MatrixFreeCPUFGMRESError(
                "canonical preconditioner binary artifact manifest is invalid"
            ) from exc
        if (
            manifest["factor_contract_hash"]
            != canonical_factor.contract_hash
            or manifest["dimension"] != equation_count
            or manifest["source_operator_pattern_hash"] != pattern_hash
            or manifest["source_operator_numeric_values_hash"] != values_hash
        ):
            raise MatrixFreeCPUFGMRESError(
                "canonical preconditioner binary artifact binding mismatch"
            )
        binary_bundle_hash = str(manifest["bundle_hash"])

    contract_hash = canonical_hash(
        {
            "profile": MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE,
            "case_id": case_id,
            "equation_count": equation_count,
            "reference_preconditioner_contract": source_contract,
            "reference_preconditioner_pattern_hash": pattern_hash,
            "reference_preconditioner_values_hash": values_hash,
            "preconditioner_profile": (
                MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE
            ),
            "preconditioner_factor_contract_hash": (
                canonical_factor.contract_hash
            ),
            "preconditioner_binary_artifact_bundle_hash": binary_bundle_hash,
            "preconditioner_apply_profile": (
                CANONICAL_SPARSE_LU_APPLY_PROFILE
            ),
            "operator_binding_hash": operator_binding["binding_hash"],
            "config": config.contract_payload(),
            "production_solver_claim": False,
        }
    )
    return MatrixFreeCPUFGMRESStateTangentSolver(
        profile=MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE,
        contract_hash=contract_hash,
        config=config,
        case_id=case_id,
        equation_count=equation_count,
        reference_preconditioner_contract=source_contract,
        reference_preconditioner_pattern_hash=pattern_hash,
        reference_preconditioner_values_hash=values_hash,
        operator_binding=operator_binding,
        preconditioner_profile=(
            MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE
        ),
        preconditioner_apply_backend=(
            "canonical_csr_sparse_lu_ordered_python_fsum"
        ),
        preconditioner_factorization_backend=(
            "external_prebuilt_factor_outside_solver_contract"
        ),
        preconditioner_column_permutation=(
            "bound_in_canonical_factor_permutation_arrays"
        ),
        preconditioner_factor_contract_hash=canonical_factor.contract_hash,
        preconditioner_binary_artifact_bundle_hash=binary_bundle_hash,
        preconditioner_callback_outputs_in_contract=True,
        claim_boundary=(
            MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_CLAIM_BOUNDARY
        ),
        _factorization=canonical_factor,
    )


__all__ = [
    "MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_CLAIM_BOUNDARY",
    "MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_CLAIM_BOUNDARY",
    "MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE",
    "MATRIX_FREE_CPU_FGMRES_SCHEMA_VERSION",
    "MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION",
    "MatrixFreeCPUFGMRESConfig",
    "MatrixFreeCPUFGMRESError",
    "MatrixFreeCPUFGMRESStateTangentSolver",
    "create_matrix_free_cpu_fgmres_state_tangent_solver",
    "create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu",
]
