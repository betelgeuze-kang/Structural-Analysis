"""Engine v2 deterministic CPU FGMRES adapter for one tangent system.

The adapter preserves the ExecutionPlan, EquationScaling, and reduced-CSR
identity contracts while exposing a compact internal linear-solve receipt. It
does not itself assemble a nonlinear residual, commit state, or claim a
production nonlinear backend.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    EquationScaling,
    validate_equation_scaling_binding,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (
    create_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.cpu_fgmres import (
    CPU_FGMRES_IDENTITY_PRECONDITIONER,
    CPUFGMRESRun,
    run_cpu_fgmres,
    validate_cpu_fgmres_run,
)


CPU_FGMRES_TANGENT_SOLVE_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-tangent-solve.v1"
)
CPU_FGMRES_TANGENT_SOLVE_PROFILE = (
    "engine_v2_reduced_csr_cpu_fgmres_tangent_solve.v1"
)
CPU_FGMRES_TANGENT_CLAIM_BOUNDARY = (
    "This receipt covers one deterministic Engine v2 reduced-CSR tangent linear "
    "solve. It does not prove nonlinear residual assembly, augmented arc-length "
    "integration, state commit/rollback, a sparse production nonlinear path, "
    "ROCm/HIP parity, full-building equilibrium, or G1 closure."
)


class CPUFGMRESTangentSolveError(ValueError):
    """Stable fail-closed tangent adapter error."""


@dataclass(frozen=True)
class CPUFGMRESTangentSolve:
    schema_version: str
    solve_hash: str
    status: str
    contract_pass: bool
    profile: str
    run_hash: str
    execution_plan_hash: str
    scaling_hash: str
    reduced_csr_identity_hash: str
    operator_numeric_values_hash: str
    right_hand_side_free_data_hash: str
    solution_free_data_hash: str
    free_count: int
    preconditioner_profile: str
    converged: bool
    terminal_reason: str
    iteration_count: int
    matvec_count: int
    explicit_residual_inf_norm: float
    explicit_residual_tolerance: float
    explicit_residual_data_hash: str
    fallback_count: int
    regularization_count: int
    claim_boundary: str
    _run: CPUFGMRESRun
    _right_hand_side_free: np.ndarray
    _explicit_residual_free: np.ndarray

    @property
    def solution_free(self) -> np.ndarray:
        return self._run.solution_free

    @property
    def right_hand_side_free(self) -> np.ndarray:
        return self._right_hand_side_free

    @property
    def explicit_residual_free(self) -> np.ndarray:
        return self._explicit_residual_free

    def to_manifest(self) -> dict[str, Any]:
        validate_cpu_fgmres_tangent_solve(self)
        return _solve_payload(self, include_solve_hash=True)


def _finite_vector(values: Any, *, shape: tuple[int, ...], path: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype="<f8")
    except (TypeError, ValueError) as exc:
        raise CPUFGMRESTangentSolveError(
            f"{path} must be a finite FP64 vector"
        ) from exc
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise CPUFGMRESTangentSolveError(
            f"{path} must be a finite FP64 vector with shape {shape}"
        )
    return immutable_array(array, dtype="<f8")


def _positive_float(value: Any, *, path: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise CPUFGMRESTangentSolveError(f"{path} must be numeric") from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise CPUFGMRESTangentSolveError(f"{path} must be finite and positive")
    return normalized


def _reduced_matvec(run: CPUFGMRESRun, values: np.ndarray) -> np.ndarray:
    reduced = run._reduced_csr
    row_ptr = reduced.array("free_csr_row_ptr")
    columns = reduced.array("free_csr_column_indices")
    global_positions = reduced.array("free_csr_global_value_indices")
    solution = run.solution_free
    result = np.zeros(reduced.free_count, dtype="<f8")
    for row in range(reduced.free_count):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        result[row] = math.fsum(
            float(values[int(global_positions[position])])
            * float(solution[int(columns[position])])
            for position in range(start, stop)
        )
    return immutable_array(result, dtype="<f8")


def solve_cpu_fgmres_tangent_system(
    *,
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
    global_csr_values_si: Any,
    right_hand_side_free: Any,
    solution_artifact_uri: str,
    max_iterations: int = 100,
    restart_length: int | None = None,
    relative_tolerance_scaled_l2: float = 1.0e-12,
    absolute_tolerance_scaled_l2: float = 1.0e-14,
    arnoldi_breakdown_tolerance: float = 1.0e-14,
    explicit_residual_tolerance: float = 1.0e-10,
    right_preconditioner_profile: str = CPU_FGMRES_IDENTITY_PRECONDITIONER,
    right_preconditioner_inverse_diagonal: Any | None = None,
) -> CPUFGMRESTangentSolve:
    """Solve one bound free-equation tangent system and emit a compact receipt."""

    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling_binding(
        plan,
        scaling=scaling,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
    )
    free_count = int(plan.array("free_dofs").size)
    if free_count < 1:
        raise CPUFGMRESTangentSolveError(
            "tangent solve requires at least one free equation"
        )
    right_hand_side = _finite_vector(
        right_hand_side_free,
        shape=(free_count,),
        path="right_hand_side_free",
    )
    global_values = _finite_vector(
        global_csr_values_si,
        shape=(int(plan.array("csr_column_indices").size),),
        path="global_csr_values_si",
    )
    residual_tolerance = _positive_float(
        explicit_residual_tolerance,
        path="explicit_residual_tolerance",
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=array_data_hash(global_values),
    )
    global_right_hand_side = np.zeros(plan.dof_count, dtype="<f8")
    global_right_hand_side[plan.array("free_dofs")] = right_hand_side
    global_right_hand_side = immutable_array(
        global_right_hand_side,
        dtype="<f8",
    )
    restart = free_count if restart_length is None else restart_length
    run = run_cpu_fgmres(
        execution_plan=plan,
        scaling=scaling,
        reduced_csr=reduced,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
        global_csr_values_si=global_values,
        right_hand_side_si=global_right_hand_side,
        solution_artifact_uri=solution_artifact_uri,
        max_iterations=max_iterations,
        restart_length=restart,
        relative_tolerance_scaled_l2=relative_tolerance_scaled_l2,
        absolute_tolerance_scaled_l2=absolute_tolerance_scaled_l2,
        arnoldi_breakdown_tolerance=arnoldi_breakdown_tolerance,
        right_preconditioner_profile=right_preconditioner_profile,
        right_preconditioner_inverse_diagonal=(
            right_preconditioner_inverse_diagonal
        ),
    )
    explicit_residual = immutable_array(
        _reduced_matvec(run, global_values) - right_hand_side,
        dtype="<f8",
    )
    residual_inf_norm = float(np.linalg.norm(explicit_residual, ord=np.inf))
    contract_pass = bool(run.converged and residual_inf_norm <= residual_tolerance)
    provisional = CPUFGMRESTangentSolve(
        schema_version=CPU_FGMRES_TANGENT_SOLVE_SCHEMA_VERSION,
        solve_hash="sha256:" + "0" * 64,
        status="ready" if contract_pass else "blocked",
        contract_pass=contract_pass,
        profile=CPU_FGMRES_TANGENT_SOLVE_PROFILE,
        run_hash=run.run_hash,
        execution_plan_hash=plan.plan_hash,
        scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        operator_numeric_values_hash=reduced.operator_numeric_values_hash,
        right_hand_side_free_data_hash=array_data_hash(right_hand_side),
        solution_free_data_hash=array_data_hash(run.solution_free),
        free_count=free_count,
        preconditioner_profile=run.preconditioner_profile,
        converged=run.converged,
        terminal_reason=run.terminal_reason,
        iteration_count=run.iteration_count,
        matvec_count=run.matvec_count,
        explicit_residual_inf_norm=residual_inf_norm,
        explicit_residual_tolerance=residual_tolerance,
        explicit_residual_data_hash=array_data_hash(explicit_residual),
        fallback_count=0,
        regularization_count=0,
        claim_boundary=CPU_FGMRES_TANGENT_CLAIM_BOUNDARY,
        _run=run,
        _right_hand_side_free=right_hand_side,
        _explicit_residual_free=explicit_residual,
    )
    solve = replace(
        provisional,
        solve_hash=canonical_hash(
            _solve_payload(provisional, include_solve_hash=False)
        ),
    )
    return validate_cpu_fgmres_tangent_solve(solve)


def _solve_payload(
    solve: CPUFGMRESTangentSolve,
    *,
    include_solve_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": solve.schema_version,
        "status": solve.status,
        "contract_pass": solve.contract_pass,
        "profile": solve.profile,
        "source": {
            "execution_plan_hash": solve.execution_plan_hash,
            "scaling_hash": solve.scaling_hash,
            "reduced_csr_identity_hash": solve.reduced_csr_identity_hash,
            "operator_numeric_values_hash": solve.operator_numeric_values_hash,
            "right_hand_side_free_data_hash": (
                solve.right_hand_side_free_data_hash
            ),
        },
        "solver": {
            "run_hash": solve.run_hash,
            "free_count": solve.free_count,
            "preconditioner_profile": solve.preconditioner_profile,
            "converged": solve.converged,
            "terminal_reason": solve.terminal_reason,
            "iteration_count": solve.iteration_count,
            "matvec_count": solve.matvec_count,
            "fallback_count": solve.fallback_count,
            "regularization_count": solve.regularization_count,
        },
        "explicit_residual": {
            "inf_norm": solve.explicit_residual_inf_norm,
            "tolerance": solve.explicit_residual_tolerance,
            "data_hash": solve.explicit_residual_data_hash,
            "gate_passed": (
                solve.explicit_residual_inf_norm
                <= solve.explicit_residual_tolerance
            ),
        },
        "solution_artifact": {
            "data_hash": solve.solution_free_data_hash,
            "descriptor": solve._run.solution_descriptor.to_dict(),
        },
        "claim_boundary": {
            "description": solve.claim_boundary,
            "nonlinear_residual_assembly": False,
            "arc_length_integration": False,
            "state_commit_rollback": False,
            "production_sparse_nonlinear_backend": False,
            "rocm_hip_parity": False,
            "g1_closure": False,
        },
    }
    if include_solve_hash:
        payload["solve_hash"] = solve.solve_hash
    return payload


def validate_cpu_fgmres_tangent_solve(
    solve: CPUFGMRESTangentSolve,
) -> CPUFGMRESTangentSolve:
    if type(solve) is not CPUFGMRESTangentSolve:
        raise CPUFGMRESTangentSolveError("expected CPUFGMRESTangentSolve")
    run = validate_cpu_fgmres_run(solve._run)
    if solve.schema_version != CPU_FGMRES_TANGENT_SOLVE_SCHEMA_VERSION:
        raise CPUFGMRESTangentSolveError("schema_version is invalid")
    if solve.profile != CPU_FGMRES_TANGENT_SOLVE_PROFILE:
        raise CPUFGMRESTangentSolveError("profile is invalid")
    right_hand_side = _finite_vector(
        solve._right_hand_side_free,
        shape=(run.free_count,),
        path="right_hand_side_free",
    )
    global_values = run._input_arrays["global_csr_values_si"]
    expected_residual = immutable_array(
        _reduced_matvec(run, global_values) - right_hand_side,
        dtype="<f8",
    )
    supplied_residual = _finite_vector(
        solve._explicit_residual_free,
        shape=(run.free_count,),
        path="explicit_residual_free",
    )
    if not np.array_equal(expected_residual, supplied_residual):
        raise CPUFGMRESTangentSolveError("explicit residual bytes do not match")
    residual_inf_norm = float(np.linalg.norm(expected_residual, ord=np.inf))
    residual_tolerance = _positive_float(
        solve.explicit_residual_tolerance,
        path="explicit_residual_tolerance",
    )
    contract_pass = bool(run.converged and residual_inf_norm <= residual_tolerance)
    expected_fields = {
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "run_hash": run.run_hash,
        "execution_plan_hash": run.execution_plan_hash,
        "scaling_hash": run.scaling_hash,
        "reduced_csr_identity_hash": run.reduced_csr_identity_hash,
        "operator_numeric_values_hash": run.operator_numeric_values_hash,
        "right_hand_side_free_data_hash": array_data_hash(right_hand_side),
        "solution_free_data_hash": array_data_hash(run.solution_free),
        "free_count": run.free_count,
        "preconditioner_profile": run.preconditioner_profile,
        "converged": run.converged,
        "terminal_reason": run.terminal_reason,
        "iteration_count": run.iteration_count,
        "matvec_count": run.matvec_count,
        "explicit_residual_inf_norm": residual_inf_norm,
        "explicit_residual_data_hash": array_data_hash(expected_residual),
        "fallback_count": 0,
        "regularization_count": 0,
        "claim_boundary": CPU_FGMRES_TANGENT_CLAIM_BOUNDARY,
    }
    for name, expected in expected_fields.items():
        if getattr(solve, name) != expected:
            raise CPUFGMRESTangentSolveError(f"{name} does not match the CPU run")
    expected_hash = canonical_hash(
        _solve_payload(solve, include_solve_hash=False)
    )
    if solve.solve_hash != expected_hash:
        raise CPUFGMRESTangentSolveError("solve_hash mismatch")
    if solve.solution_free.flags.writeable:
        raise CPUFGMRESTangentSolveError("solution bytes must be immutable")
    return solve


__all__ = [
    "CPU_FGMRES_TANGENT_CLAIM_BOUNDARY",
    "CPU_FGMRES_TANGENT_SOLVE_PROFILE",
    "CPU_FGMRES_TANGENT_SOLVE_SCHEMA_VERSION",
    "CPUFGMRESTangentSolve",
    "CPUFGMRESTangentSolveError",
    "solve_cpu_fgmres_tangent_system",
    "validate_cpu_fgmres_tangent_solve",
]
