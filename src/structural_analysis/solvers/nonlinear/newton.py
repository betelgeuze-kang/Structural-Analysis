"""Narrow deterministic Newton-Raphson seed for scalar nonlinear axial references."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
import warnings

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

RESIDUAL_FORMULA = "F_internal_minus_F_external"
GLOBALIZATION = "backtracking_line_search"
MATRIX_BACKEND = "numpy_linalg_solve_scalar"
VECTOR_MATRIX_BACKEND = "numpy_linalg_solve_dense"
VECTOR_SPARSE_MATRIX_BACKEND = "scipy_sparse_spsolve_cpu"
VECTOR_MATRIX_BACKENDS = (VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND)
VECTOR_SPARSE_STIFFNESS_STORAGE = "scipy_sparse_csr"
SPARSE_BACKEND_USED = False
SCALAR_CONFIG_BACKENDS = (MATRIX_BACKEND, VECTOR_MATRIX_BACKEND)


class VectorEquilibriumProblem(Protocol):
    """Vector equilibrium problem with assembled residual and consistent tangent."""

    case_id: str

    def reference_force_scale(self) -> float: ...

    def initial_free_displacements_m(self) -> np.ndarray: ...

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]: ...


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
            self.linear_stiffness_kn_per_m * u
            + self.cubic_stiffness_kn_per_m3 * u**3
        )

    def tangent_stiffness(self, displacement_m: float) -> float:
        u = float(displacement_m)
        return self.linear_stiffness_kn_per_m + 3.0 * self.cubic_stiffness_kn_per_m3 * u**2

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


def _vector_backend_metadata(matrix_backend: str) -> dict[str, Any]:
    sparse_backend = matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND
    return {
        "matrix_backend": matrix_backend,
        "sparse_backend_used": sparse_backend,
        "stiffness_storage": (
            VECTOR_SPARSE_STIFFNESS_STORAGE
            if sparse_backend
            else "numpy_dense_ndarray"
        ),
    }


def _solve_vector_increment(
    jacobian_kn_per_m: np.ndarray,
    residual_kn: np.ndarray,
    *,
    matrix_backend: str,
) -> np.ndarray:
    if matrix_backend == VECTOR_MATRIX_BACKEND:
        return np.linalg.solve(jacobian_kn_per_m, -residual_kn)
    if matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND:
        sparse_jacobian = csr_matrix(jacobian_kn_per_m)
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            increment = spsolve(sparse_jacobian, -residual_kn)
        increment = np.asarray(increment, dtype=float)
        if increment.shape != residual_kn.shape or not np.all(np.isfinite(increment)):
            raise np.linalg.LinAlgError("sparse vector solve returned invalid increment")
        return increment
    raise ValueError(f"unsupported vector matrix backend: {matrix_backend}")


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


def _relative_residual(problem: ScalarAxialEquilibriumProblem, residual: float) -> float:
    return abs(residual) / problem.reference_force_scale()


def _relative_residual_vector(problem: VectorEquilibriumProblem, residual: np.ndarray) -> float:
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
                "trial_relative_residual": _relative_residual_vector(problem, trial_residual),
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
) -> NewtonRaphsonVectorSolution:
    """Solve assembled R(u)=F_internal(u)-F_external with Newton and line search."""
    cfg = config or NewtonRaphsonConfig()
    if cfg.matrix_backend not in VECTOR_MATRIX_BACKENDS:
        return _blocked_vector_solution(
            problem,
            cfg,
            free_displacements_m=problem.initial_free_displacements_m().astype(float).copy(),
            history=[],
            line_search_history=[],
            detail="unsupported_matrix_backend",
        )
    backend_metadata = _vector_backend_metadata(cfg.matrix_backend)
    free_displacements_m = problem.initial_free_displacements_m().astype(float).copy()
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    regularization_used = False
    fallback_used = False

    for iteration in range(cfg.max_iterations + 1):
        residual_kn, jacobian_kn_per_m = problem.assemble(free_displacements_m)
        relative_residual = _relative_residual_vector(problem, residual_kn)
        residual_gate_passed = relative_residual <= cfg.residual_tolerance

        try:
            newton_increment_m = _solve_vector_increment(
                jacobian_kn_per_m,
                residual_kn,
                matrix_backend=cfg.matrix_backend,
            )
        except (np.linalg.LinAlgError, ValueError, MatrixRankWarning):
            return _blocked_vector_solution(
                problem,
                cfg,
                free_displacements_m=free_displacements_m,
                history=history,
                line_search_history=line_search_history,
                detail=(
                    "singular_tangent_stiffness_at_residual_gate"
                    if residual_gate_passed
                    else "singular_tangent_stiffness"
                ),
            )
        residual_based_increment_abs = float(np.linalg.norm(newton_increment_m, ord=np.inf))
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
            break

        next_displacement_m, line_search_alpha, attempts = _vector_line_search(
            problem,
            free_displacements_m=free_displacements_m,
            newton_increment_m=newton_increment_m,
            residual_before=residual_kn,
            alphas=cfg.line_search_alphas,
        )
        increment_abs = float(np.linalg.norm(next_displacement_m - free_displacements_m, ord=np.inf))
        increment_gate_passed = increment_abs <= cfg.increment_tolerance
        accepted = line_search_alpha > 0.0 or increment_gate_passed
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
            )
    else:
        return _blocked_vector_solution(
            problem,
            cfg,
            free_displacements_m=free_displacements_m,
            history=history,
            line_search_history=line_search_history,
            detail="iteration_loop_exhausted",
        )

    final_residual, _ = problem.assemble(free_displacements_m)
    final_relative_residual = _relative_residual_vector(problem, final_residual)
    final_increment_abs = float(history[-1]["increment_abs_m"]) if history else 0.0
    residual_gate_passed = final_relative_residual <= cfg.residual_tolerance
    increment_gate_passed = final_increment_abs <= cfg.increment_tolerance or (
        history[-1]["iteration"] == 0 and residual_gate_passed
    )
    contract_pass = residual_gate_passed and increment_gate_passed
    metrics = {
        "case_id": problem.case_id,
        "free_displacements_m": free_displacements_m.tolist(),
        "residual_kn": final_residual.tolist(),
        "relative_residual": final_relative_residual,
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": "dF_internal_du_consistent",
        "globalization": GLOBALIZATION,
        **backend_metadata,
        "residual_tolerance": cfg.residual_tolerance,
        "increment_tolerance": cfg.increment_tolerance,
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "final_increment_abs_m": final_increment_abs,
        "iteration_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["line_search_alpha"] < 1.0 for row in history if row["iteration"] < len(history) - 1
        ),
        "regularization_used": regularization_used,
        "fallback_used": fallback_used,
        "contract_pass": contract_pass,
    }
    return NewtonRaphsonVectorSolution(
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
) -> NewtonRaphsonVectorSolution:
    residual_kn, _ = problem.assemble(free_displacements_m)
    backend_metadata = _vector_backend_metadata(cfg.matrix_backend)
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
            "globalization": GLOBALIZATION,
            **backend_metadata,
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
        accepted = line_search_alpha > 0.0 or increment_gate_passed
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
        "tangent_definition": "dF_internal_du_consistent",
        "globalization": GLOBALIZATION,
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
            row["line_search_alpha"] < 1.0 for row in history if row["iteration"] < len(history) - 1
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
            "globalization": GLOBALIZATION,
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
                raise ValueError("expected_scalar_equilibrium_displacement: root not bracketed.")
    else:
        low, high = bracket_positive
        if problem.residual(low) * problem.residual(high) > 0.0:
            raise ValueError("expected_scalar_equilibrium_displacement: root not bracketed.")
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
