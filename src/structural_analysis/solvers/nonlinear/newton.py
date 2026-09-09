"""Narrow deterministic Newton-Raphson seed for scalar nonlinear axial references."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import math
from time import perf_counter_ns
from typing import Any, Protocol, cast

import numpy as np
from scipy.sparse import csr_matrix, issparse

from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_BACKEND,
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
)

RESIDUAL_FORMULA = "F_internal_minus_F_external"
RESIDUAL_FORMULA_HASH = (
    "sha256:" + hashlib.sha256(RESIDUAL_FORMULA.encode("utf-8")).hexdigest()
)
GLOBALIZATION = "backtracking_line_search"
SOLVE_FREE_EQUATIONS_DISPOSITION = "solve_free_equations"
NO_SOLVE_REACTION_ONLY_DISPOSITION = "no_solve_reaction_only"
MATRIX_BACKEND = "numpy_linalg_solve_scalar"
VECTOR_MATRIX_BACKEND = "numpy_linalg_solve_dense"
VECTOR_SPARSE_MATRIX_BACKEND = "scipy_sparse_spsolve_cpu"
VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND = "scipy_sparse_splu_cpu_exact_1536"
VECTOR_SPARSE_MATRIX_BACKENDS = (
    VECTOR_SPARSE_MATRIX_BACKEND,
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
)
VECTOR_MATRIX_BACKENDS = (VECTOR_MATRIX_BACKEND, *VECTOR_SPARSE_MATRIX_BACKENDS)
VECTOR_SPARSE_STIFFNESS_STORAGE = "scipy_sparse_csr"
SPARSE_BACKEND_USED = False
SCALAR_CONFIG_BACKENDS = (MATRIX_BACKEND, VECTOR_MATRIX_BACKEND)
VECTOR_INCREMENT_TIMING_SCOPE = (
    "vector_increment_backend_including_conversion_and_sparse_diagnostics"
)


@dataclass
class VectorIncrementRuntimeRecorder:
    """Caller-owned timing sidecar; never part of numerical solution identity.

    Measures the existing increment backend, including matrix conversion and
    sparse factorization diagnostics. It is not isolated BLAS/LAPACK kernel time.
    """

    clock_ns: Callable[[], int] = field(default=perf_counter_ns, repr=False)
    wall_ns: int = field(default=0, init=False)
    call_count: int = field(default=0, init=False)
    exception_count: int = field(default=0, init=False)
    _active: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not callable(self.clock_ns):
            raise ValueError("clock_ns must be callable")

    def _read_clock(self) -> int:
        value = self.clock_ns()
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError("increment clock_ns must return integer nanoseconds")
        return value

    def _solve(
        self, jacobian: Any, residual: np.ndarray, *, matrix_backend: str
    ) -> tuple[np.ndarray, dict[str, Any] | None]:
        if self._active:
            raise RuntimeError("increment runtime recorder is already active")
        started = self._read_clock()
        self._active = True
        self.call_count += 1
        try:
            return _solve_vector_increment(
                jacobian, residual, matrix_backend=matrix_backend
            )
        except BaseException:
            self.exception_count += 1
            raise
        finally:
            self._active = False
            elapsed = self._read_clock() - started
            if elapsed < 0:
                raise RuntimeError("increment clock_ns must be monotonic")
            self.wall_ns += elapsed


class VectorEquilibriumProblem(Protocol):
    """Vector equilibrium problem with assembled residual and consistent tangent."""

    @property
    def case_id(self) -> str: ...

    def reference_force_scale(self) -> float: ...

    def initial_free_displacements_m(self) -> np.ndarray: ...

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, Any]: ...


class CompensatedVectorEquilibriumProblem(VectorEquilibriumProblem, Protocol):
    """Optional assembly interface selected by retained terminal coordinates."""

    def assemble_with_compensation(
        self, high: np.ndarray, low: np.ndarray
    ) -> tuple[np.ndarray, Any]: ...


class ScalarAxialEquilibriumProblem(Protocol):
    """Scalar axial bar with explicit F_internal, consistent tangent, and F_external load."""

    case_id: str
    external_force_kn: float
    initial_displacement_m: float

    def internal_force(self, displacement_m: float) -> float: ...

    def tangent_stiffness(self, displacement_m: float) -> float: ...

    def residual(self, displacement_m: float) -> float: ...

    def reference_force_scale(self) -> float: ...


@dataclass(frozen=True)
class ScalarNonlinearAxialReference:
    """Cubic spring axial bar: F_internal(u)=k_lin*u+k_cub*u^3, F_external=P."""

    linear_stiffness_kn_per_m: float = 100.0
    cubic_stiffness_kn_per_m3: float = 1000.0
    external_force_kn: float = 100.0
    initial_displacement_m: float = 0.0
    case_id: str = "phase2_scalar_nonlinear_axial_cubic_spring"

    def internal_force(self, displacement_m: float) -> float:
        u = float(displacement_m)
        return (
            self.linear_stiffness_kn_per_m * u + self.cubic_stiffness_kn_per_m3 * u**3
        )

    def tangent_stiffness(self, displacement_m: float) -> float:
        u = float(displacement_m)
        return (
            self.linear_stiffness_kn_per_m + 3.0 * self.cubic_stiffness_kn_per_m3 * u**2
        )

    def residual(self, displacement_m: float) -> float:
        return self.internal_force(displacement_m) - self.external_force_kn

    def reference_force_scale(self) -> float:
        return max(abs(self.external_force_kn), 1.0)

    @property
    def model_kind(self) -> str:
        return "scalar_nonlinear_axial_cubic_spring"


@dataclass(frozen=True)
class ScalarBilinearHardeningAxialReference:
    """Bilinear axial bar: elastic branch then lower positive post-yield tangent."""

    elastic_stiffness_kn_per_m: float = 200.0
    post_yield_stiffness_kn_per_m: float = 50.0
    yield_force_kn: float = 40.0
    external_force_kn: float = 100.0
    initial_displacement_m: float = 0.0
    case_id: str = "phase2_scalar_nonlinear_axial_bilinear_hardening"

    def _yield_displacement_m(self) -> float:
        return self.yield_force_kn / self.elastic_stiffness_kn_per_m

    def internal_force(self, displacement_m: float) -> float:
        u = max(0.0, float(displacement_m))
        yield_displacement_m = self._yield_displacement_m()
        elastic_force_kn = self.elastic_stiffness_kn_per_m * u
        if elastic_force_kn <= self.yield_force_kn:
            return elastic_force_kn
        return self.yield_force_kn + self.post_yield_stiffness_kn_per_m * (
            u - yield_displacement_m
        )

    def tangent_stiffness(self, displacement_m: float) -> float:
        u = max(0.0, float(displacement_m))
        if self.elastic_stiffness_kn_per_m * u < self.yield_force_kn:
            return self.elastic_stiffness_kn_per_m
        return self.post_yield_stiffness_kn_per_m

    def residual(self, displacement_m: float) -> float:
        return self.internal_force(displacement_m) - self.external_force_kn

    def reference_force_scale(self) -> float:
        return max(abs(self.external_force_kn), 1.0)

    @property
    def model_kind(self) -> str:
        return "scalar_nonlinear_axial_bilinear_hardening"


@dataclass(frozen=True)
class NewtonRaphsonConfig:
    residual_tolerance: float = 1.0e-10
    increment_tolerance: float = 1.0e-12
    max_iterations: int = 25
    line_search_alphas: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125)
    matrix_backend: str = VECTOR_MATRIX_BACKEND
    terminal_polishing: bool = False

    def __post_init__(self) -> None:
        if type(self.terminal_polishing) is not bool:
            raise ValueError("terminal_polishing must be a boolean")
        for name in ("residual_tolerance", "increment_tolerance"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value,
                (int, float, np.integer, np.floating),
            ):
                raise ValueError(f"{name} must be a finite positive number")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
            object.__setattr__(self, name, normalized)

        if (
            isinstance(self.max_iterations, (bool, np.bool_))
            or not isinstance(self.max_iterations, (int, np.integer))
            or int(self.max_iterations) < 0
        ):
            raise ValueError("max_iterations must be a non-negative integer")
        object.__setattr__(self, "max_iterations", int(self.max_iterations))

        if not isinstance(self.line_search_alphas, (tuple, list)) or not (
            self.line_search_alphas
        ):
            raise ValueError("line_search_alphas must be a non-empty sequence")
        normalized_alphas: list[float] = []
        previous_alpha = math.inf
        for value in self.line_search_alphas:
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value,
                (int, float, np.integer, np.floating),
            ):
                raise ValueError(
                    "line_search_alphas must contain finite positive numbers"
                )
            alpha = float(value)
            if not math.isfinite(alpha) or alpha <= 0.0 or alpha > 1.0:
                raise ValueError(
                    "line_search_alphas must be finite in the interval (0, 1]"
                )
            if alpha >= previous_alpha:
                raise ValueError("line_search_alphas must be strictly decreasing")
            normalized_alphas.append(alpha)
            previous_alpha = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized_alphas))

        if not isinstance(self.matrix_backend, str) or not self.matrix_backend.strip():
            raise ValueError("matrix_backend must be a non-empty string")


def sparse_factorization_policy_for_backend(
    matrix_backend: str,
) -> SparseFactorizationPolicy:
    """Resolve the explicit sparse diagnostic scope without relaxing its gates."""
    if matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND:
        return SparseFactorizationPolicy()
    if matrix_backend == VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND:
        return SparseFactorizationPolicy(
            maximum_condition_number_1=1.0e12,
            minimum_normalized_absolute_pivot=1.0e-14,
            maximum_backward_error=1.0e-12,
            maximum_exact_condition_equations=1536,
        )
    raise ValueError(f"unsupported sparse matrix backend: {matrix_backend}")


def _vector_backend_metadata(
    matrix_backend: str,
    *,
    native_sparse_assembly_used: bool = False,
) -> dict[str, Any]:
    sparse_backend = matrix_backend in VECTOR_SPARSE_MATRIX_BACKENDS
    return {
        "matrix_backend": matrix_backend,
        "sparse_backend_used": sparse_backend,
        "native_sparse_assembly_used": native_sparse_assembly_used,
        "stiffness_storage": (
            VECTOR_SPARSE_STIFFNESS_STORAGE if sparse_backend else "numpy_dense_ndarray"
        ),
    }


def _solve_vector_increment(
    jacobian_kn_per_m: Any,
    residual_kn: np.ndarray,
    *,
    matrix_backend: str,
) -> tuple[np.ndarray, dict[str, Any] | None]:
    if matrix_backend == VECTOR_MATRIX_BACKEND:
        dense_jacobian = (
            jacobian_kn_per_m.toarray()
            if issparse(jacobian_kn_per_m)
            else np.asarray(jacobian_kn_per_m, dtype=float)
        )
        return np.linalg.solve(dense_jacobian, -residual_kn), None
    if matrix_backend in VECTOR_SPARSE_MATRIX_BACKENDS:
        sparse_jacobian = (
            jacobian_kn_per_m.tocsr(copy=True)
            if issparse(jacobian_kn_per_m)
            else csr_matrix(jacobian_kn_per_m)
        )
        sparse_jacobian.sum_duplicates()
        sparse_jacobian.eliminate_zeros()
        sparse_jacobian.sort_indices()
        if sparse_jacobian.shape != (
            residual_kn.size,
            residual_kn.size,
        ) or not np.all(np.isfinite(sparse_jacobian.data)):
            raise np.linalg.LinAlgError("sparse vector tangent is invalid")
        if matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND:
            solved = factorize_and_solve_sparse(sparse_jacobian, -residual_kn)
        else:
            solved = factorize_and_solve_sparse(
                sparse_jacobian,
                -residual_kn,
                policy=sparse_factorization_policy_for_backend(matrix_backend),
            )
        increment = np.asarray(solved.solution, dtype=float)
        if increment.shape != residual_kn.shape or not np.all(np.isfinite(increment)):
            raise np.linalg.LinAlgError(
                "sparse vector solve returned invalid increment"
            )
        return increment, solved.diagnostic.to_manifest()
    raise ValueError(f"unsupported vector matrix backend: {matrix_backend}")


def _sparse_factorization_metadata(
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    if not diagnostics:
        return {
            "sparse_factorization_backend": None,
            "sparse_factorization_count": 0,
            "sparse_factorization_diagnostics_passed": None,
            "sparse_factorization_max_condition_number_1": None,
            "sparse_factorization_min_normalized_absolute_pivot": None,
            "sparse_factorization_max_backward_error": None,
            "sparse_factorization_diagnostics": [],
        }
    return {
        "sparse_factorization_backend": SPARSE_FACTORIZATION_BACKEND,
        "sparse_factorization_count": len(diagnostics),
        "sparse_factorization_diagnostics_passed": all(
            row.get("contract_pass") is True for row in diagnostics
        ),
        "sparse_factorization_max_condition_number_1": max(
            float(row["condition_number_1"]) for row in diagnostics
        ),
        "sparse_factorization_min_normalized_absolute_pivot": min(
            float(row["normalized_absolute_pivot_minimum"]) for row in diagnostics
        ),
        "sparse_factorization_max_backward_error": max(
            float(row["backward_error"]) for row in diagnostics
        ),
        "sparse_factorization_diagnostics": list(diagnostics),
    }


def _terminal_polishing_record(
    reason: str = "usual_convergence_not_reached",
) -> dict[str, Any]:
    """Optional attempted work, separate from the selected Newton path."""
    return {
        "schema_version": "newton-vector-terminal-polishing.v1",
        "enabled": True,
        "status": "skipped" if reason == "no_free_equations" else "not_reached",
        "attempted": False,
        "accepted": False,
        "reason": reason,
        "source_iteration": None,
        "candidate_iteration": None,
        "original_residual_linf": None,
        "candidate_residual_linf": None,
        "original_relative_residual": None,
        "candidate_relative_residual": None,
        "candidate_increment_abs_m": None,
        "original_free_displacements_m": None,
        "candidate_free_displacements_m": None,
        "original_residual_kn": None,
        "candidate_residual_kn": None,
        "proposed_correction_m": None,
        "candidate_newton_increment_m": None,
        "assembly_call_count": 0,
        "assembly_exception_count": 0,
        "linear_solve_count": 0,
        "linear_solve_exception_count": 0,
        "sparse_factorization_diagnostic": None,
        "error_type": None,
        "error_message": None,
    }


def _terminal_polish_vector(
    problem: VectorEquilibriumProblem,
    cfg: NewtonRaphsonConfig,
    *,
    iteration: int,
    coordinates: np.ndarray,
    coordinate_compensation: np.ndarray | None = None,
    residual: np.ndarray,
    relative_residual: float,
    correction: np.ndarray,
    solve_increment: Callable[..., tuple[np.ndarray, dict[str, Any] | None]],
) -> dict[str, Any]:
    """Try one full correction; rejection cannot replace the converged state.

    Assembly and backend calls use the caller's existing instrumented paths.
    Programming/recorder errors propagate; anticipated numerical failures are
    retained here rather than contaminating selected-path sparse diagnostics.
    """
    record = _terminal_polishing_record()
    original_norm = float(np.linalg.norm(residual, ord=np.inf))
    record.update(
        source_iteration=iteration,
        candidate_iteration=iteration + 1,
        original_residual_linf=original_norm,
        original_relative_residual=relative_residual,
        original_free_displacements_m=coordinates.tolist(),
        original_residual_kn=residual.tolist(),
        proposed_correction_m=correction.tolist(),
    )
    if coordinate_compensation is not None:
        record["original_coordinate_compensation_m"] = coordinate_compensation.tolist()
    if iteration >= cfg.max_iterations:
        record.update(status="skipped", reason="max_iterations_exhausted")
        return record
    record.update(status="rejected", attempted=True)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            precision = getattr(problem, "terminal_coordinate_precision", "binary64")
            compensation = None
            if precision == "twofold":
                from fractions import Fraction
                from structural_analysis.solvers.nonlinear import (
                    twofold_coordinates as twofold,
                )

                candidate, compensation = twofold.split(
                    Fraction(float(x)) + Fraction(float(low)) + Fraction(float(d))
                    for x, low, d in zip(
                        coordinates,
                        np.zeros_like(coordinates)
                        if coordinate_compensation is None
                        else coordinate_compensation,
                        correction,
                        strict=True,
                    )
                )
                record["coordinate_precision"] = "twofold"
                record["candidate_coordinate_compensation_m"] = compensation.tolist()
            elif precision == "binary64":
                candidate = coordinates + correction
            else:
                raise ValueError("unsupported terminal coordinate precision")
            if candidate.shape != coordinates.shape or not np.all(
                np.isfinite(candidate)
            ):
                raise np.linalg.LinAlgError("terminal polishing candidate is invalid")
            record["candidate_free_displacements_m"] = candidate.tolist()
            if candidate.tobytes() == coordinates.tobytes() and (
                (compensation is None or not np.any(compensation))
                if coordinate_compensation is None
                else compensation is not None
                and np.array_equal(compensation, coordinate_compensation)
            ):
                record["reason"] = "candidate_equals_converged_state"
                return record
            record["assembly_call_count"] += 1
            try:
                if compensation is None:
                    candidate_residual, candidate_jacobian = problem.assemble(candidate)
                else:
                    candidate_residual, candidate_jacobian = cast(
                        CompensatedVectorEquilibriumProblem, problem
                    ).assemble_with_compensation(candidate, compensation)
            except BaseException:
                record["assembly_exception_count"] += 1
                raise
            candidate_residual = np.asarray(candidate_residual, dtype=float)
            if (
                candidate_residual.shape != coordinates.shape
                or not np.all(np.isfinite(candidate_residual))
                or candidate.shape != coordinates.shape
                or not np.all(np.isfinite(candidate))
            ):
                raise np.linalg.LinAlgError("terminal polishing residual is invalid")
            jacobian_values = (
                np.asarray(candidate_jacobian.tocsr(copy=False).data, dtype=float)
                if issparse(candidate_jacobian)
                else np.asarray(candidate_jacobian, dtype=float)
            )
            jacobian_shape = (
                candidate_jacobian.shape
                if issparse(candidate_jacobian)
                else jacobian_values.shape
            )
            if jacobian_shape != (coordinates.size, coordinates.size) or not np.all(
                np.isfinite(jacobian_values)
            ):
                raise np.linalg.LinAlgError("terminal polishing Jacobian is invalid")
            candidate_norm = float(np.linalg.norm(candidate_residual, ord=np.inf))
            candidate_relative = _relative_residual_vector(problem, candidate_residual)
            if not math.isfinite(candidate_relative):
                raise np.linalg.LinAlgError(
                    "terminal polishing relative residual is invalid"
                )
            record.update(
                candidate_residual_kn=candidate_residual.tolist(),
                candidate_residual_linf=candidate_norm,
                candidate_relative_residual=candidate_relative,
            )
            if candidate_norm >= original_norm:
                record["reason"] = "strict_residual_improvement_not_met"
                return record
            if candidate_relative > cfg.residual_tolerance:
                record["reason"] = "candidate_residual_gate_failed"
                return record
            record["linear_solve_count"] += 1
            try:
                candidate_correction, diagnostic = solve_increment(
                    candidate_jacobian,
                    candidate_residual,
                    matrix_backend=cfg.matrix_backend,
                )
            except BaseException:
                record["linear_solve_exception_count"] += 1
                raise
            record["sparse_factorization_diagnostic"] = diagnostic
            candidate_correction = np.asarray(candidate_correction, dtype=float)
            if (
                candidate_correction.shape != coordinates.shape
                or not np.all(np.isfinite(candidate_correction))
                or (
                    cfg.matrix_backend in VECTOR_SPARSE_MATRIX_BACKENDS
                    and (
                        type(diagnostic) is not dict
                        or diagnostic.get("contract_pass") is not True
                    )
                )
            ):
                raise np.linalg.LinAlgError(
                    "terminal polishing increment/backend is invalid"
                )
            candidate_increment = float(
                np.linalg.norm(candidate_correction, ord=np.inf)
            )
            record.update(
                candidate_newton_increment_m=candidate_correction.tolist(),
                candidate_increment_abs_m=candidate_increment,
            )
            if candidate_increment > cfg.increment_tolerance:
                record["reason"] = "candidate_increment_gate_failed"
                return record
            record.update(
                status="accepted",
                accepted=True,
                reason="strict_residual_improvement_and_original_gates_passed",
            )
    except (
        np.linalg.LinAlgError,
        ValueError,
        FloatingPointError,
        OverflowError,
    ) as exc:
        if isinstance(exc, SparseFactorizationError) and exc.diagnostic is not None:
            record["sparse_factorization_diagnostic"] = exc.diagnostic.to_manifest()
        record.update(
            reason="numerical_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return record


@dataclass(frozen=True)
class NewtonRaphsonSolution:
    status: str
    problem: ScalarAxialEquilibriumProblem
    config: NewtonRaphsonConfig
    displacement_m: float
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    line_search_history: list[dict[str, Any]] = field(default_factory=list)
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NewtonRaphsonVectorSolution:
    status: str
    problem: VectorEquilibriumProblem
    config: NewtonRaphsonConfig
    free_displacements_m: np.ndarray
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    line_search_history: list[dict[str, Any]] = field(default_factory=list)
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    free_displacement_compensation_m: np.ndarray | None = None


def _no_solve_reaction_only_vector_solution(
    problem: VectorEquilibriumProblem,
    cfg: NewtonRaphsonConfig,
    *,
    free_displacements_m: np.ndarray,
) -> NewtonRaphsonVectorSolution:
    """Route F=0 to a reaction-only terminal state without Newton recurrence."""
    detail = "free_equation_space_empty"
    residual_kn = np.asarray([], dtype=float)
    try:
        assembled_residual, assembled_jacobian = problem.assemble(free_displacements_m)
        residual_kn = np.asarray(assembled_residual, dtype=float)
        if issparse(assembled_jacobian):
            # An empty sparse system needs shape/data checks, not a dense copy.
            sparse_jacobian = assembled_jacobian.tocsr(copy=True)
            jacobian_shape = sparse_jacobian.shape
            jacobian_values = np.asarray(sparse_jacobian.data, dtype=float)
        else:
            jacobian_values = np.asarray(assembled_jacobian, dtype=float)
            jacobian_shape = jacobian_values.shape
        assembly_contract_valid = bool(
            residual_kn.shape == (0,)
            and jacobian_shape == (0, 0)
            and np.all(np.isfinite(residual_kn))
            and np.all(np.isfinite(jacobian_values))
        )
    except (TypeError, ValueError, ArithmeticError, AttributeError, LookupError):
        assembly_contract_valid = False
    if not assembly_contract_valid:
        detail = "zero_equation_assembly_contract_invalid"

    contract_pass = assembly_contract_valid
    metrics = {
        "case_id": problem.case_id,
        "free_displacements_m": [],
        "active_equation_count": 0,
        "residual_kn": residual_kn.tolist(),
        "relative_residual": None,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "tangent_definition": "not_applicable_no_free_equations",
        "globalization": "not_applicable_no_free_equations",
        "matrix_backend": None,
        "sparse_backend_used": False,
        "native_sparse_assembly_used": False,
        "stiffness_storage": "none",
        **_sparse_factorization_metadata([]),
        "terminal_disposition": NO_SOLVE_REACTION_ONLY_DISPOSITION,
        "terminal_reason": detail,
        "solver_executed": False,
        "newton_iteration_count": 0,
        "linear_solve_count": 0,
        "line_search_step_count": 0,
        "line_search_used": False,
        "residual_norm_applicable": False,
        "increment_norm_applicable": False,
        "residual_gate_passed": None,
        "increment_gate_passed": None,
        "convergence_claim": False,
        "reaction_observation_only": True,
        "assembly_contract_valid": assembly_contract_valid,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
    }
    if cfg.terminal_polishing:
        metrics["terminal_polishing"] = _terminal_polishing_record("no_free_equations")
    unsupported = []
    if not contract_pass:
        unsupported.append(
            {
                "kind": "newton_vector_no_solve_contract_blocked",
                "detail": detail,
                "guard_outcome": "blocked",
                "regularization_used": False,
                "fallback_used": False,
            }
        )
    return NewtonRaphsonVectorSolution(
        status="ready" if contract_pass else "blocked",
        problem=problem,
        config=cfg,
        free_displacements_m=free_displacements_m,
        metrics=metrics,
        convergence_history=[],
        line_search_history=[],
        unsupported_features=unsupported,
    )


def _relative_residual(
    problem: ScalarAxialEquilibriumProblem, residual: float
) -> float:
    return abs(residual) / problem.reference_force_scale()


def _relative_residual_vector(
    problem: VectorEquilibriumProblem, residual: np.ndarray
) -> float:
    return float(np.linalg.norm(residual, ord=np.inf)) / problem.reference_force_scale()


def _line_search(
    problem: ScalarAxialEquilibriumProblem,
    *,
    displacement_m: float,
    newton_increment_m: float,
    residual_before: float,
    alphas: tuple[float, ...],
) -> tuple[float, float, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    best_alpha = 0.0
    best_residual = residual_before
    best_displacement = displacement_m
    for alpha in alphas:
        trial_displacement = displacement_m + alpha * newton_increment_m
        trial_residual = problem.residual(trial_displacement)
        accepted = abs(trial_residual) < abs(residual_before)
        attempts.append(
            {
                "alpha": alpha,
                "trial_displacement_m": trial_displacement,
                "trial_residual_kn": trial_residual,
                "trial_relative_residual": _relative_residual(problem, trial_residual),
                "accepted": accepted,
            }
        )
        if accepted:
            return trial_displacement, alpha, attempts
        if abs(trial_residual) < abs(best_residual):
            best_residual = trial_residual
            best_alpha = alpha
            best_displacement = trial_displacement
    if best_alpha > 0.0:
        return best_displacement, best_alpha, attempts
    return displacement_m, 0.0, attempts


def _vector_line_search(
    problem: VectorEquilibriumProblem,
    *,
    free_displacements_m: np.ndarray,
    newton_increment_m: np.ndarray,
    residual_before: np.ndarray,
    alphas: tuple[float, ...],
) -> tuple[np.ndarray, float, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    best_alpha = 0.0
    best_residual = residual_before
    best_displacement = free_displacements_m.copy()
    residual_norm_before = float(np.linalg.norm(residual_before, ord=np.inf))
    for alpha in alphas:
        trial_displacement = free_displacements_m + alpha * newton_increment_m
        trial_residual, _ = problem.assemble(trial_displacement)
        trial_norm = float(np.linalg.norm(trial_residual, ord=np.inf))
        accepted = trial_norm < residual_norm_before
        attempts.append(
            {
                "alpha": alpha,
                "trial_free_displacements_m": trial_displacement.tolist(),
                "trial_residual_kn": trial_residual.tolist(),
                "trial_relative_residual": _relative_residual_vector(
                    problem, trial_residual
                ),
                "accepted": accepted,
            }
        )
        if accepted:
            return trial_displacement, alpha, attempts
        if trial_norm < float(np.linalg.norm(best_residual, ord=np.inf)):
            best_residual = trial_residual
            best_alpha = alpha
            best_displacement = trial_displacement
    if best_alpha > 0.0:
        return best_displacement, best_alpha, attempts
    return free_displacements_m.copy(), 0.0, attempts


def newton_raphson_vector(
    problem: VectorEquilibriumProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
    increment_runtime: VectorIncrementRuntimeRecorder | None = None,
) -> NewtonRaphsonVectorSolution:
    """Solve assembled R(u)=F_internal(u)-F_external with Newton and line search."""
    if (
        increment_runtime is not None
        and type(increment_runtime) is not VectorIncrementRuntimeRecorder
    ):
        raise ValueError("increment_runtime must be VectorIncrementRuntimeRecorder")
    cfg = config or NewtonRaphsonConfig()
    free_displacements_m = np.asarray(
        problem.initial_free_displacements_m(),
        dtype=float,
    ).copy()
    if free_displacements_m.ndim != 1 or not np.all(np.isfinite(free_displacements_m)):
        raise ValueError(
            "initial_free_displacements_m must be a finite one-dimensional vector"
        )
    if free_displacements_m.size == 0:
        return _no_solve_reaction_only_vector_solution(
            problem,
            cfg,
            free_displacements_m=free_displacements_m,
        )
    if cfg.matrix_backend not in VECTOR_MATRIX_BACKENDS:
        return _blocked_vector_solution(
            problem,
            cfg,
            free_displacements_m=free_displacements_m,
            history=[],
            line_search_history=[],
            detail="unsupported_matrix_backend",
        )
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    regularization_used = False
    fallback_used = False
    native_sparse_assembly_used = False
    sparse_factorization_diagnostics: list[dict[str, Any]] = []
    linear_solve_count = 0
    refinement_limit = getattr(problem, "terminal_refinement_limit", 1)
    if type(refinement_limit) is not int or not 1 <= refinement_limit <= 4:
        raise ValueError("terminal refinement limit must be an integer from 1 to 4")
    if refinement_limit > 1 and (
        not cfg.terminal_polishing
        or getattr(problem, "terminal_coordinate_precision", "binary64") != "twofold"
    ):
        raise ValueError(
            "additional terminal refinement requires enabled twofold polishing"
        )
    polishing = _terminal_polishing_record() if cfg.terminal_polishing else None
    free_compensation = None

    for iteration in range(cfg.max_iterations + 1):
        residual_kn, jacobian_kn_per_m = problem.assemble(free_displacements_m)
        residual_kn = np.asarray(residual_kn, dtype=float)
        native_sparse_assembly_used = bool(
            native_sparse_assembly_used or issparse(jacobian_kn_per_m)
        )
        relative_residual = _relative_residual_vector(problem, residual_kn)
        residual_gate_passed = relative_residual <= cfg.residual_tolerance

        try:
            solve_increment = (
                _solve_vector_increment
                if increment_runtime is None
                else increment_runtime._solve
            )
            linear_solve_count += 1
            newton_increment_m, factorization_diagnostic = solve_increment(
                jacobian_kn_per_m,
                residual_kn,
                matrix_backend=cfg.matrix_backend,
            )
            if factorization_diagnostic is not None:
                sparse_factorization_diagnostics.append(factorization_diagnostic)
        except (np.linalg.LinAlgError, ValueError) as error:
            if (
                isinstance(error, SparseFactorizationError)
                and error.diagnostic is not None
            ):
                sparse_factorization_diagnostics.append(error.diagnostic.to_manifest())
            return _blocked_vector_solution(
                problem,
                cfg,
                free_displacements_m=free_displacements_m,
                history=history,
                line_search_history=line_search_history,
                detail=(
                    error.code
                    if isinstance(error, SparseFactorizationError)
                    else (
                        "singular_tangent_stiffness_at_residual_gate"
                        if residual_gate_passed
                        else "singular_tangent_stiffness"
                    )
                ),
                sparse_factorization_diagnostics=sparse_factorization_diagnostics,
                linear_solve_count=linear_solve_count,
            )
        residual_based_increment_abs = float(
            np.linalg.norm(newton_increment_m, ord=np.inf)
        )
        increment_gate_passed = residual_based_increment_abs <= cfg.increment_tolerance

        if residual_gate_passed and increment_gate_passed:
            history.append(
                {
                    "iteration": iteration,
                    "free_displacements_m": free_displacements_m.tolist(),
                    "residual_kn": residual_kn.tolist(),
                    "relative_residual": relative_residual,
                    "newton_increment_m": newton_increment_m.tolist(),
                    "increment_abs_m": residual_based_increment_abs,
                    "line_search_alpha": 1.0,
                    "line_search_attempt_count": 0,
                    "residual_gate_passed": True,
                    "increment_gate_passed": True,
                    "accepted": True,
                }
            )
            if cfg.terminal_polishing:
                attempts = []
                refinement_residual = residual_kn
                refinement_relative = relative_residual
                refinement_correction = newton_increment_m
                for refinement_index in range(refinement_limit):
                    attempt = _terminal_polish_vector(
                        problem,
                        cfg,
                        iteration=iteration + refinement_index,
                        coordinates=free_displacements_m,
                        coordinate_compensation=free_compensation,
                        residual=refinement_residual,
                        relative_residual=refinement_relative,
                        correction=refinement_correction,
                        solve_increment=solve_increment,
                    )
                    attempts.append(attempt)
                    linear_solve_count += attempt["linear_solve_count"]
                    if attempt["accepted"]:
                        free_displacements_m = np.asarray(
                            attempt["candidate_free_displacements_m"], dtype=float
                        )
                        if "candidate_coordinate_compensation_m" in attempt:
                            free_compensation = np.asarray(
                                attempt["candidate_coordinate_compensation_m"],
                                dtype=float,
                            )
                            free_compensation.setflags(write=False)
                        diagnostic = attempt["sparse_factorization_diagnostic"]
                        if diagnostic is not None:
                            sparse_factorization_diagnostics.append(diagnostic)
                        history.append(
                            {
                                "iteration": iteration + refinement_index + 1,
                                **(
                                    {
                                        "free_displacement_compensation_m": free_compensation.tolist()
                                    }
                                    if free_compensation is not None
                                    else {}
                                ),
                                "free_displacements_m": free_displacements_m.tolist(),
                                "residual_kn": attempt["candidate_residual_kn"],
                                "relative_residual": attempt[
                                    "candidate_relative_residual"
                                ],
                                "newton_increment_m": attempt[
                                    "candidate_newton_increment_m"
                                ],
                                "increment_abs_m": attempt["candidate_increment_abs_m"],
                                "line_search_alpha": 1.0,
                                "line_search_attempt_count": 0,
                                "residual_gate_passed": True,
                                "increment_gate_passed": True,
                                "accepted": True,
                            }
                        )
                        refinement_residual = np.asarray(
                            attempt["candidate_residual_kn"], dtype=float
                        )
                        refinement_relative = attempt["candidate_relative_residual"]
                        refinement_correction = np.asarray(
                            attempt["candidate_newton_increment_m"], dtype=float
                        )
                    else:
                        break
                polishing = attempts[0]
                if refinement_limit > 1:
                    selected = next(
                        (a for a in reversed(attempts) if a["accepted"]), attempts[0]
                    )
                    polishing = dict(selected)
                    polishing.update(
                        schema_version="newton-vector-terminal-refinement.v1",
                        refinement_limit=refinement_limit,
                        attempts=attempts,
                        attempt_count=sum(a["attempted"] for a in attempts),
                        accepted_correction_count=sum(a["accepted"] for a in attempts),
                        stop_reason=attempts[-1]["reason"]
                        if not attempts[-1]["accepted"]
                        else "refinement_limit_reached",
                    )
                    for key in (
                        "assembly_call_count",
                        "assembly_exception_count",
                        "linear_solve_count",
                        "linear_solve_exception_count",
                    ):
                        polishing[key] = sum(a[key] for a in attempts)
            break

        next_displacement_m, line_search_alpha, attempts = _vector_line_search(
            problem,
            free_displacements_m=free_displacements_m,
            newton_increment_m=newton_increment_m,
            residual_before=residual_kn,
            alphas=cfg.line_search_alphas,
        )
        increment_abs = float(
            np.linalg.norm(next_displacement_m - free_displacements_m, ord=np.inf)
        )
        increment_gate_passed = increment_abs <= cfg.increment_tolerance
        accepted = line_search_alpha > 0.0
        line_search_history.append(
            {
                "iteration": iteration,
                "starting_free_displacements_m": free_displacements_m.tolist(),
                "newton_increment_m": newton_increment_m.tolist(),
                "selected_alpha": line_search_alpha,
                "attempt_count": len(attempts),
                "attempts": attempts,
            }
        )
        history.append(
            {
                "iteration": iteration,
                "free_displacements_m": free_displacements_m.tolist(),
                "residual_kn": residual_kn.tolist(),
                "relative_residual": relative_residual,
                "newton_increment_m": newton_increment_m.tolist(),
                "increment_abs_m": increment_abs,
                "line_search_alpha": line_search_alpha,
                "line_search_attempt_count": len(attempts),
                "residual_gate_passed": residual_gate_passed,
                "increment_gate_passed": increment_gate_passed,
                "accepted": accepted,
            }
        )

        if not accepted:
            return _blocked_vector_solution(
                problem,
                cfg,
                free_displacements_m=free_displacements_m,
                history=history,
                line_search_history=line_search_history,
                detail="line_search_failed_to_reduce_residual",
                sparse_factorization_diagnostics=sparse_factorization_diagnostics,
                linear_solve_count=linear_solve_count,
            )

        free_displacements_m = next_displacement_m
        if iteration == cfg.max_iterations:
            return _blocked_vector_solution(
                problem,
                cfg,
                free_displacements_m=free_displacements_m,
                history=history,
                line_search_history=line_search_history,
                detail="max_iterations_exceeded",
                sparse_factorization_diagnostics=sparse_factorization_diagnostics,
                linear_solve_count=linear_solve_count,
            )
    else:
        return _blocked_vector_solution(
            problem,
            cfg,
            free_displacements_m=free_displacements_m,
            history=history,
            line_search_history=line_search_history,
            detail="iteration_loop_exhausted",
            sparse_factorization_diagnostics=sparse_factorization_diagnostics,
            linear_solve_count=linear_solve_count,
        )

    if free_compensation is None:
        final_residual, final_jacobian = problem.assemble(free_displacements_m)
    else:
        final_residual, final_jacobian = cast(
            CompensatedVectorEquilibriumProblem, problem
        ).assemble_with_compensation(free_displacements_m, free_compensation)
    final_residual = np.asarray(final_residual, dtype=float)
    native_sparse_assembly_used = bool(
        native_sparse_assembly_used or issparse(final_jacobian)
    )
    final_relative_residual = _relative_residual_vector(problem, final_residual)
    final_increment_abs = float(history[-1]["increment_abs_m"]) if history else 0.0
    residual_gate_passed = final_relative_residual <= cfg.residual_tolerance
    increment_gate_passed = final_increment_abs <= cfg.increment_tolerance or (
        history[-1]["iteration"] == 0 and residual_gate_passed
    )
    sparse_factorization_contract = bool(
        cfg.matrix_backend not in VECTOR_SPARSE_MATRIX_BACKENDS
        or (
            sparse_factorization_diagnostics
            and all(
                row.get("contract_pass") is True
                for row in sparse_factorization_diagnostics
            )
        )
    )
    contract_pass = bool(
        residual_gate_passed and increment_gate_passed and sparse_factorization_contract
    )
    metrics = {
        "case_id": problem.case_id,
        "free_displacements_m": free_displacements_m.tolist(),
        "residual_kn": final_residual.tolist(),
        "relative_residual": final_relative_residual,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "active_equation_count": int(free_displacements_m.size),
        "tangent_definition": "dF_internal_du_consistent",
        "globalization": GLOBALIZATION,
        "terminal_disposition": SOLVE_FREE_EQUATIONS_DISPOSITION,
        "terminal_reason": "residual_and_increment_converged",
        "solver_executed": True,
        "newton_iteration_count": len(history),
        "linear_solve_count": len(history),
        "residual_norm_applicable": True,
        "increment_norm_applicable": True,
        "convergence_claim": contract_pass,
        "reaction_observation_only": False,
        **_vector_backend_metadata(
            cfg.matrix_backend,
            native_sparse_assembly_used=native_sparse_assembly_used,
        ),
        **_sparse_factorization_metadata(sparse_factorization_diagnostics),
        "residual_tolerance": cfg.residual_tolerance,
        "increment_tolerance": cfg.increment_tolerance,
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "final_increment_abs_m": final_increment_abs,
        "iteration_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["line_search_alpha"] < 1.0
            for row in history
            if row["iteration"] < len(history) - 1
        ),
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "contract_pass": contract_pass,
    }
    if free_compensation is not None:
        metrics["free_displacement_compensation_m"] = free_compensation.tolist()
    if polishing is not None:
        metrics["terminal_polishing"] = polishing
        metrics["linear_solve_count"] = linear_solve_count
    return NewtonRaphsonVectorSolution(
        free_displacement_compensation_m=free_compensation,
        status="ready" if contract_pass else "blocked",
        problem=problem,
        config=cfg,
        free_displacements_m=free_displacements_m,
        metrics=metrics,
        convergence_history=history,
        line_search_history=line_search_history,
    )


def _blocked_vector_solution(
    problem: VectorEquilibriumProblem,
    cfg: NewtonRaphsonConfig,
    *,
    free_displacements_m: np.ndarray,
    history: list[dict[str, Any]],
    line_search_history: list[dict[str, Any]],
    detail: str,
    sparse_factorization_diagnostics: list[dict[str, Any]] | None = None,
    linear_solve_count: int = 0,
) -> NewtonRaphsonVectorSolution:
    residual_kn, jacobian_kn_per_m = problem.assemble(free_displacements_m)
    residual_kn = np.asarray(residual_kn, dtype=float)
    backend_metadata = _vector_backend_metadata(
        cfg.matrix_backend,
        native_sparse_assembly_used=issparse(jacobian_kn_per_m),
    )
    return NewtonRaphsonVectorSolution(
        status="blocked",
        problem=problem,
        config=cfg,
        free_displacements_m=free_displacements_m,
        metrics={
            "case_id": problem.case_id,
            "free_displacements_m": free_displacements_m.tolist(),
            "residual_kn": residual_kn.tolist(),
            "relative_residual": _relative_residual_vector(problem, residual_kn),
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "globalization": GLOBALIZATION,
            "active_equation_count": int(free_displacements_m.size),
            "terminal_disposition": SOLVE_FREE_EQUATIONS_DISPOSITION,
            "terminal_reason": detail,
            "solver_executed": detail != "unsupported_matrix_backend",
            "residual_norm_applicable": True,
            "increment_norm_applicable": True,
            "convergence_claim": False,
            "reaction_observation_only": False,
            **backend_metadata,
            **_sparse_factorization_metadata(sparse_factorization_diagnostics or []),
            "residual_gate_passed": False,
            "increment_gate_passed": False,
            "regularization_used": False,
            "fallback_used": False,
            "contract_pass": False,
            "detail": detail,
            **(
                {
                    "terminal_polishing": _terminal_polishing_record(),
                    "newton_iteration_count": len(history),
                    "iteration_count": len(history),
                    "linear_solve_count": linear_solve_count,
                }
                if cfg.terminal_polishing
                else {}
            ),
        },
        convergence_history=history,
        line_search_history=line_search_history,
        unsupported_features=[
            {
                "kind": "newton_vector_reference_blocked",
                "detail": detail,
                "guard_outcome": "blocked",
                "regularization_used": False,
                "fallback_used": False,
            }
        ],
    )


def newton_raphson_scalar(
    problem: ScalarAxialEquilibriumProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> NewtonRaphsonSolution:
    """Solve R(u)=F_internal(u)-F_external with consistent tangent and line search."""
    cfg = config or NewtonRaphsonConfig()
    if cfg.terminal_polishing:
        raise ValueError("terminal_polishing is supported only by the vector solver")
    if cfg.matrix_backend not in SCALAR_CONFIG_BACKENDS:
        return _blocked_solution(
            problem,
            cfg,
            displacement_m=float(problem.initial_displacement_m),
            history=[],
            line_search_history=[],
            detail="unsupported_matrix_backend",
        )
    displacement_m = float(problem.initial_displacement_m)
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    regularization_used = False
    fallback_used = False

    for iteration in range(cfg.max_iterations + 1):
        residual_kn = problem.residual(displacement_m)
        relative_residual = _relative_residual(problem, residual_kn)
        tangent_kn_per_m = problem.tangent_stiffness(displacement_m)
        internal_force_kn = problem.internal_force(displacement_m)
        residual_gate_passed = relative_residual <= cfg.residual_tolerance

        if abs(tangent_kn_per_m) <= np.finfo(float).tiny:
            return _blocked_solution(
                problem,
                cfg,
                displacement_m=displacement_m,
                history=history,
                line_search_history=line_search_history,
                detail=(
                    "singular_tangent_stiffness_at_residual_gate"
                    if residual_gate_passed
                    else "singular_tangent_stiffness"
                ),
            )
        else:
            residual_based_increment_m = -residual_kn / tangent_kn_per_m
            residual_based_increment_abs = abs(residual_based_increment_m)
        increment_gate_passed = residual_based_increment_abs <= cfg.increment_tolerance

        if residual_gate_passed and increment_gate_passed:
            history.append(
                {
                    "iteration": iteration,
                    "displacement_m": displacement_m,
                    "residual_kn": residual_kn,
                    "relative_residual": relative_residual,
                    "internal_force_kn": internal_force_kn,
                    "external_force_kn": problem.external_force_kn,
                    "tangent_kn_per_m": tangent_kn_per_m,
                    "newton_increment_m": residual_based_increment_m,
                    "increment_abs": residual_based_increment_abs,
                    "line_search_alpha": 1.0,
                    "line_search_attempt_count": 0,
                    "residual_gate_passed": True,
                    "increment_gate_passed": True,
                    "accepted": True,
                }
            )
            break

        newton_increment_m = residual_based_increment_m
        (
            next_displacement_m,
            line_search_alpha,
            attempts,
        ) = _line_search(
            problem,
            displacement_m=displacement_m,
            newton_increment_m=newton_increment_m,
            residual_before=residual_kn,
            alphas=cfg.line_search_alphas,
        )
        increment_abs = abs(next_displacement_m - displacement_m)
        increment_gate_passed = increment_abs <= cfg.increment_tolerance
        accepted = line_search_alpha > 0.0
        line_search_history.append(
            {
                "iteration": iteration,
                "starting_displacement_m": displacement_m,
                "newton_increment_m": newton_increment_m,
                "selected_alpha": line_search_alpha,
                "attempt_count": len(attempts),
                "attempts": attempts,
            }
        )
        history.append(
            {
                "iteration": iteration,
                "displacement_m": displacement_m,
                "residual_kn": residual_kn,
                "relative_residual": relative_residual,
                "internal_force_kn": internal_force_kn,
                "external_force_kn": problem.external_force_kn,
                "tangent_kn_per_m": tangent_kn_per_m,
                "newton_increment_m": newton_increment_m,
                "increment_abs": increment_abs,
                "line_search_alpha": line_search_alpha,
                "line_search_attempt_count": len(attempts),
                "residual_gate_passed": residual_gate_passed,
                "increment_gate_passed": increment_gate_passed,
                "accepted": accepted,
            }
        )

        if not accepted:
            return _blocked_solution(
                problem,
                cfg,
                displacement_m=displacement_m,
                history=history,
                line_search_history=line_search_history,
                detail="line_search_failed_to_reduce_residual",
            )

        displacement_m = next_displacement_m
        if iteration == cfg.max_iterations:
            return _blocked_solution(
                problem,
                cfg,
                displacement_m=displacement_m,
                history=history,
                line_search_history=line_search_history,
                detail="max_iterations_exceeded",
            )
    else:
        return _blocked_solution(
            problem,
            cfg,
            displacement_m=displacement_m,
            history=history,
            line_search_history=line_search_history,
            detail="iteration_loop_exhausted",
        )

    final_residual = problem.residual(displacement_m)
    final_relative_residual = _relative_residual(problem, final_residual)
    final_increment_abs = float(history[-1]["increment_abs"]) if history else 0.0
    residual_gate_passed = final_relative_residual <= cfg.residual_tolerance
    increment_gate_passed = final_increment_abs <= cfg.increment_tolerance or (
        history[-1]["iteration"] == 0 and residual_gate_passed
    )
    contract_pass = residual_gate_passed and increment_gate_passed
    metrics = {
        "case_id": problem.case_id,
        "displacement_m": displacement_m,
        "internal_force_kn": problem.internal_force(displacement_m),
        "external_force_kn": problem.external_force_kn,
        "residual_kn": final_residual,
        "relative_residual": final_relative_residual,
        "tangent_kn_per_m": problem.tangent_stiffness(displacement_m),
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "active_equation_count": 1,
        "tangent_definition": "dF_internal_du_consistent",
        "globalization": GLOBALIZATION,
        "terminal_disposition": SOLVE_FREE_EQUATIONS_DISPOSITION,
        "terminal_reason": "residual_and_increment_converged",
        "solver_executed": True,
        "newton_iteration_count": len(history),
        "linear_solve_count": len(history),
        "residual_norm_applicable": True,
        "increment_norm_applicable": True,
        "convergence_claim": contract_pass,
        "reaction_observation_only": False,
        "matrix_backend": MATRIX_BACKEND,
        "sparse_backend_used": SPARSE_BACKEND_USED,
        "residual_tolerance": cfg.residual_tolerance,
        "increment_tolerance": cfg.increment_tolerance,
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "final_increment_abs_m": final_increment_abs,
        "iteration_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["line_search_alpha"] < 1.0
            for row in history
            if row["iteration"] < len(history) - 1
        ),
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "contract_pass": contract_pass,
    }
    return NewtonRaphsonSolution(
        status="ready" if contract_pass else "blocked",
        problem=problem,
        config=cfg,
        displacement_m=displacement_m,
        metrics=metrics,
        convergence_history=history,
        line_search_history=line_search_history,
    )


def _blocked_solution(
    problem: ScalarAxialEquilibriumProblem,
    cfg: NewtonRaphsonConfig,
    *,
    displacement_m: float,
    history: list[dict[str, Any]],
    line_search_history: list[dict[str, Any]],
    detail: str,
) -> NewtonRaphsonSolution:
    residual_kn = problem.residual(displacement_m)
    return NewtonRaphsonSolution(
        status="blocked",
        problem=problem,
        config=cfg,
        displacement_m=displacement_m,
        metrics={
            "case_id": problem.case_id,
            "displacement_m": displacement_m,
            "residual_kn": residual_kn,
            "relative_residual": _relative_residual(problem, residual_kn),
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "globalization": GLOBALIZATION,
            "active_equation_count": 1,
            "terminal_disposition": SOLVE_FREE_EQUATIONS_DISPOSITION,
            "terminal_reason": detail,
            "solver_executed": detail != "unsupported_matrix_backend",
            "residual_norm_applicable": True,
            "increment_norm_applicable": True,
            "convergence_claim": False,
            "reaction_observation_only": False,
            "matrix_backend": (
                cfg.matrix_backend
                if detail == "unsupported_matrix_backend"
                else MATRIX_BACKEND
            ),
            "sparse_backend_used": SPARSE_BACKEND_USED,
            "residual_gate_passed": False,
            "increment_gate_passed": False,
            "regularization_used": False,
            "fallback_used": False,
            "contract_pass": False,
            "detail": detail,
        },
        convergence_history=history,
        line_search_history=line_search_history,
        unsupported_features=[
            {
                "kind": "newton_scalar_reference_blocked",
                "detail": detail,
                "guard_outcome": "blocked",
                "regularization_used": False,
                "fallback_used": False,
            }
        ],
    )


def expected_scalar_equilibrium_displacement(
    problem: ScalarAxialEquilibriumProblem,
    *,
    bracket_positive: tuple[float, float] | None = None,
    tolerance: float = 1.0e-14,
    max_iterations: int = 200,
) -> float:
    """Bracketed bisection root for scalar axial equilibrium (artifact truth check)."""
    if bracket_positive is None:
        low = 0.0
        high = 1.0
        if problem.residual(low) * problem.residual(high) > 0.0:
            for _ in range(60):
                high *= 2.0
                if problem.residual(low) * problem.residual(high) <= 0.0:
                    break
            else:
                raise ValueError(
                    "expected_scalar_equilibrium_displacement: root not bracketed."
                )
    else:
        low, high = bracket_positive
        if problem.residual(low) * problem.residual(high) > 0.0:
            raise ValueError(
                "expected_scalar_equilibrium_displacement: root not bracketed."
            )
    if problem.residual(low) == 0.0:
        return low
    if problem.residual(high) == 0.0:
        return high
    for _ in range(max_iterations):
        mid = 0.5 * (low + high)
        residual_mid = problem.residual(mid)
        if abs(residual_mid) <= tolerance or (high - low) <= tolerance:
            return mid
        if problem.residual(low) * residual_mid <= 0.0:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)


def finite_difference_tangent_check(
    problem: ScalarAxialEquilibriumProblem,
    displacement_m: float,
    *,
    epsilon: float = 1.0e-8,
) -> dict[str, Any]:
    analytic = problem.tangent_stiffness(displacement_m)
    fd = (
        problem.internal_force(displacement_m + epsilon)
        - problem.internal_force(displacement_m - epsilon)
    ) / (2.0 * epsilon)
    error = abs(fd - analytic)
    return {
        "displacement_m": displacement_m,
        "finite_difference_epsilon": epsilon,
        "analytic_tangent_kn_per_m": analytic,
        "finite_difference_tangent_kn_per_m": fd,
        "abs_error": error,
        "pass": error <= 1.0e-6,
    }


def assess_quadratic_convergence(
    convergence_history: list[dict[str, Any]],
    *,
    minimum_observed_order: float = 1.8,
    minimum_order_sample_count: int = 2,
) -> dict[str, Any]:
    """Assess local Newton order from consecutive accepted full-step residuals."""

    samples: list[dict[str, float | int]] = []
    for row in convergence_history:
        if not isinstance(row, dict) or row.get("accepted") is not True:
            continue
        residual = float(row.get("relative_residual", math.nan))
        alpha = float(row.get("line_search_alpha", math.nan))
        if not math.isfinite(residual) or residual <= 0.0 or alpha != 1.0:
            continue
        samples.append(
            {
                "iteration": int(row.get("iteration", len(samples))),
                "relative_residual": residual,
            }
        )

    order_rows: list[dict[str, float | int]] = []
    for previous, current, following in zip(
        samples,
        samples[1:],
        samples[2:],
        strict=False,
    ):
        residual_previous = float(previous["relative_residual"])
        residual_current = float(current["relative_residual"])
        residual_following = float(following["relative_residual"])
        if not (
            residual_following < residual_current < residual_previous
            and residual_previous > 0.0
        ):
            continue
        denominator = math.log(residual_current / residual_previous)
        if denominator == 0.0:
            continue
        observed_order = math.log(residual_following / residual_current) / denominator
        quadratic_ratio = residual_following / (residual_current**2)
        if not math.isfinite(observed_order) or not math.isfinite(quadratic_ratio):
            continue
        order_rows.append(
            {
                "ending_iteration": int(following["iteration"]),
                "observed_order": observed_order,
                "quadratic_ratio": quadratic_ratio,
            }
        )

    observed_orders = [float(row["observed_order"]) for row in order_rows]
    minimum_order = min(observed_orders) if observed_orders else None
    passed = bool(
        len(observed_orders) >= minimum_order_sample_count
        and minimum_order is not None
        and minimum_order >= minimum_observed_order
    )
    return {
        "method": "consecutive_full_step_relative_residual_order",
        "minimum_observed_order_required": minimum_observed_order,
        "minimum_order_sample_count_required": minimum_order_sample_count,
        "full_step_sample_count": len(samples),
        "order_sample_count": len(order_rows),
        "minimum_observed_order": minimum_order,
        "samples": samples,
        "order_samples": order_rows,
        "pass": passed,
    }
