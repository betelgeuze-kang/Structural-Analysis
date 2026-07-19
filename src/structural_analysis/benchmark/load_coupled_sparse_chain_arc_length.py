"""Load-coupled sparse state-operator arc-length verification seed."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any

import numpy as np

from structural_analysis.benchmark.sparse_chain_arc_length import (
    SPARSE_CHAIN_ARC_LENGTH_CONFIG,
    SparseChainShallowArchProblem,
    create_sparse_chain_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthLoadCoupledStateTangentProblem,
    VectorArcLengthTangentSolve,
    vector_arc_length_continuation,
)


LOAD_COUPLED_SPARSE_CHAIN_SCHEMA_VERSION = (
    "phase2-load-coupled-sparse-chain-cpu-fgmres-arc-length.v1"
)
LOAD_COUPLED_SPARSE_CHAIN_CLAIM_BOUNDARY = (
    "This receipt verifies an analytic 12-equation sparse arc-length path whose "
    "physical residual, displacement Jacobian, and negative load-factor "
    "derivative are all state coupled. It does not connect the real MGT "
    "frame/shell/material assembler, prove production-scale preconditioning or "
    "ROCm/HIP parity, create a full-load G1 checkpoint, or close G1."
)
LOAD_COUPLED_DENSE_REFERENCE_SOLVER_PROFILE = (
    "load_coupled_dense_state_reference_solve.v1"
)


@dataclass(frozen=True)
class LoadCoupledSparseChainShallowArchProblem(SparseChainShallowArchProblem):
    """Analytic chain with a load-dependent geometric internal-force term."""

    case_id: str = "load_coupled_sparse_chain_state_operator_arc_length"
    load_coupling_kn_per_m: float = 2.0

    def residual_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        displacements = np.asarray(free_displacements_m, dtype=float)
        residual = self.internal_force_kn(displacements)
        residual = residual - float(load_factor) * self.reference_load_kn()
        residual[0] += (
            float(load_factor)
            * self.load_coupling_kn_per_m
            * float(displacements[0])
        )
        return residual

    def negative_load_derivative_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        del load_factor
        displacements = np.asarray(free_displacements_m, dtype=float)
        derivative = self.reference_load_kn()
        derivative[0] -= (
            self.load_coupling_kn_per_m * float(displacements[0])
        )
        return derivative

    def state_tangent_diagonal_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        diagonal = self.tangent_diagonal_kn_per_m(free_displacements_m)
        diagonal[0] += float(load_factor) * self.load_coupling_kn_per_m
        return diagonal

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        action = self.consistent_tangent_action_kn_per_m(
            free_displacements_m,
            direction_m,
        )
        direction = np.asarray(direction_m, dtype=float)
        action[0] += (
            float(load_factor)
            * self.load_coupling_kn_per_m
            * float(direction[0])
        )
        return action

    def exact_load_factor(self, primary_displacement_m: float) -> float:
        denominator = 1.0 - (
            self.load_coupling_kn_per_m * primary_displacement_m
        )
        if abs(denominator) <= np.finfo(float).eps:
            raise ValueError("exact load-factor reduction is singular")
        return self.arch.internal_force_kn(primary_displacement_m) / denominator


@dataclass(frozen=True)
class LoadCoupledDenseReferenceStateTangentSolver:
    """Verification-only dense solve for the same load-coupled operator."""

    profile: str
    contract_hash: str

    def solve_at_state(
        self,
        problem: VectorArcLengthLoadCoupledStateTangentProblem,
        free_displacements_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        load_factor: float,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve:
        if not isinstance(problem, LoadCoupledSparseChainShallowArchProblem):
            raise TypeError("dense reference solver received an incompatible problem")
        identity = np.eye(problem.equation_count, dtype=float)
        tangent = np.column_stack(
            [
                problem.consistent_state_tangent_action_kn_per_m(
                    free_displacements_m,
                    load_factor,
                    identity[:, column],
                )
                for column in range(problem.equation_count)
            ]
        )
        right_hand_side = np.asarray(right_hand_side_kn, dtype=float)
        try:
            solution = np.linalg.solve(tangent, right_hand_side)
        except np.linalg.LinAlgError:
            solution = np.zeros_like(right_hand_side)
            contract_pass = False
            terminal_reason = "dense_reference_tangent_singular"
        else:
            explicit_residual = tangent @ solution - right_hand_side
            explicit_residual_inf = float(
                np.linalg.norm(explicit_residual, ord=np.inf)
            )
            contract_pass = bool(
                np.all(np.isfinite(solution))
                and math.isfinite(explicit_residual_inf)
                and explicit_residual_inf <= 1.0e-9
            )
            terminal_reason = (
                "converged"
                if contract_pass
                else "dense_reference_explicit_residual_failed"
            )
        operator_hash = canonical_hash(
            {
                "load_factor": float(load_factor),
                "tangent": tangent.tolist(),
            }
        )
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=contract_pass,
            terminal_reason=terminal_reason,
            solution_free=tuple(float(value) for value in solution),
            receipt={
                "schema_version": "load-coupled-dense-reference-solve.v1",
                "contract_pass": contract_pass,
                "solve_hash": canonical_hash(
                    {
                        "solve_id": solve_id,
                        "operator_hash": operator_hash,
                        "right_hand_side": right_hand_side.tolist(),
                        "solution": solution.tolist(),
                    }
                ),
                "source": {
                    "operator_numeric_values_hash": operator_hash,
                },
                "solver": {
                    "profile": self.profile,
                    "iteration_count": 1,
                },
            },
        )


def create_load_coupled_dense_reference_solver(
    problem: LoadCoupledSparseChainShallowArchProblem,
) -> LoadCoupledDenseReferenceStateTangentSolver:
    return LoadCoupledDenseReferenceStateTangentSolver(
        profile=LOAD_COUPLED_DENSE_REFERENCE_SOLVER_PROFILE,
        contract_hash=canonical_hash(
            {
                "profile": LOAD_COUPLED_DENSE_REFERENCE_SOLVER_PROFILE,
                "equation_count": problem.equation_count,
                "chain_ratio": problem.chain_ratio,
                "coupling_stiffness_kn_per_m": (
                    problem.coupling_stiffness_kn_per_m
                ),
                "load_coupling_kn_per_m": problem.load_coupling_kn_per_m,
                "explicit_residual_tolerance_kn": 1.0e-9,
            }
        ),
    )


def _tangent_solve_rows(
    attempts: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt in attempts:
        predictor = attempt.get("predictor_tangent_solve")
        if isinstance(predictor, dict):
            rows.append(predictor)
        for history_row in attempt.get("corrector_history", []):
            metadata = history_row.get("tangent_solve_metadata") or {}
            for key in (
                "residual_solve",
                "reference_load_solve",
                "load_linearization_solve",
            ):
                row = metadata.get(key)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def _finite_difference_gates(
    problem: LoadCoupledSparseChainShallowArchProblem,
) -> dict[str, Any]:
    displacements = problem.exact_free_displacements_m(0.17)
    displacements[4] += 0.002
    load_factor = problem.exact_load_factor(0.17)
    direction = np.linspace(-0.8, 1.1, problem.equation_count)
    displacement_step = 1.0e-7
    load_step = 1.0e-7
    displacement_difference = (
        problem.residual_kn(
            displacements + displacement_step * direction,
            load_factor,
        )
        - problem.residual_kn(
            displacements - displacement_step * direction,
            load_factor,
        )
    ) / (2.0 * displacement_step)
    displacement_action = (
        problem.consistent_state_tangent_action_kn_per_m(
            displacements,
            load_factor,
            direction,
        )
    )
    load_difference = -(
        problem.residual_kn(displacements, load_factor + load_step)
        - problem.residual_kn(displacements, load_factor - load_step)
    ) / (2.0 * load_step)
    negative_load_derivative = problem.negative_load_derivative_kn(
        displacements,
        load_factor,
    )
    displacement_error = float(
        np.linalg.norm(displacement_action - displacement_difference, ord=np.inf)
    )
    load_error = float(
        np.linalg.norm(
            negative_load_derivative - load_difference,
            ord=np.inf,
        )
    )
    return {
        "probe_load_factor": load_factor,
        "displacement_jacobian_finite_difference_step_m": displacement_step,
        "maximum_displacement_jacobian_action_error_kn": displacement_error,
        "displacement_jacobian_gate_passed": displacement_error <= 1.0e-6,
        "load_derivative_finite_difference_step": load_step,
        "maximum_negative_load_derivative_error_kn": load_error,
        "negative_load_derivative_gate_passed": load_error <= 1.0e-7,
    }


@lru_cache(maxsize=1)
def _build_load_coupled_sparse_chain_seed_cached() -> dict[str, Any]:
    problem = LoadCoupledSparseChainShallowArchProblem()
    sparse_solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(problem)
    dense_solver = create_load_coupled_dense_reference_solver(problem)
    config = SPARSE_CHAIN_ARC_LENGTH_CONFIG
    first = vector_arc_length_continuation(
        problem,
        config=config,
        state_tangent_solver=sparse_solver,
    )
    second = vector_arc_length_continuation(
        problem,
        config=config,
        state_tangent_solver=sparse_solver,
    )
    restart_checkpoint = first.checkpoints[len(first.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        problem,
        config=config,
        resume_from=restart_checkpoint,
        state_tangent_solver=sparse_solver,
    )
    dense_reference = vector_arc_length_continuation(
        problem,
        config=config,
        state_tangent_solver=dense_solver,
    )
    same_checkpoint_count = (
        len(first.checkpoints) == len(dense_reference.checkpoints)
    )
    displacement_error = max(
        abs(left_value - right_value)
        for left, right in zip(first.checkpoints, dense_reference.checkpoints)
        for left_value, right_value in zip(
            left.free_displacements_m,
            right.free_displacements_m,
        )
    )
    load_error = max(
        abs(left.load_factor - right.load_factor)
        for left, right in zip(first.checkpoints, dense_reference.checkpoints)
    )
    reduction_displacement_errors = [
        float(
            np.linalg.norm(
                np.asarray(checkpoint.free_displacements_m, dtype=float)
                - problem.exact_free_displacements_m(
                    checkpoint.free_displacements_m[0]
                ),
                ord=np.inf,
            )
        )
        for checkpoint in first.checkpoints
    ]
    reduction_load_errors = [
        abs(
            checkpoint.load_factor
            - problem.exact_load_factor(checkpoint.free_displacements_m[0])
        )
        for checkpoint in first.checkpoints
    ]
    finite_difference = _finite_difference_gates(problem)
    tangent_rows = _tangent_solve_rows(first.attempts)
    receipts = [row["receipt"] for row in tangent_rows]
    plan = sparse_solver.binding["plan"]
    reduced_nnz = 3 * problem.equation_count - 2
    sparse_gate = bool(
        int(plan.array("csr_column_indices").size)
        == reduced_nnz + 5 * problem.equation_count
        and reduced_nnz < problem.equation_count**2
        and first.metrics["tangent_linear_solver_mode"]
        == VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE
    )
    load_coupling_gate = bool(
        first.metrics["equilibrium_linearization_mode"]
        == VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        and finite_difference["displacement_jacobian_gate_passed"] is True
        and finite_difference["negative_load_derivative_gate_passed"] is True
    )
    exact_reduction_gate = bool(
        max(reduction_displacement_errors) <= 1.0e-11
        and max(reduction_load_errors) <= config.residual_tolerance_kn
    )
    dense_reference_gate = bool(
        dense_reference.status == "ready"
        and same_checkpoint_count
        and displacement_error <= 1.0e-10
        and load_error <= 1.0e-10
    )
    deterministic_replay_exact = first.to_dict() == second.to_dict()
    checkpoint_restart_exact = restarted.final_checkpoint == first.final_checkpoint
    tangent_gate = bool(
        tangent_rows
        and all(receipt["contract_pass"] is True for receipt in receipts)
        and max(
            float(row["explicit_residual_inf_norm_kn"])
            for row in tangent_rows
        )
        <= config.tangent_solve_residual_tolerance_kn
    )
    contract_pass = bool(
        first.status == "ready"
        and sparse_gate
        and load_coupling_gate
        and exact_reduction_gate
        and dense_reference_gate
        and deterministic_replay_exact
        and checkpoint_restart_exact
        and tangent_gate
        and first.metrics["negative_load_factor_observed"] is True
        and first.metrics["fallback_count"] == 0
        and first.metrics["regularization_count"] == 0
    )
    load_rhs_primary_values = [
        float(
            problem.negative_load_derivative_kn(
                np.asarray(checkpoint.free_displacements_m, dtype=float),
                checkpoint.load_factor,
            )[0]
        )
        for checkpoint in first.checkpoints
    ]
    return {
        "schema_version": LOAD_COUPLED_SPARSE_CHAIN_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": problem.case_id,
        "analysis_type": "load_coupled_sparse_state_operator_arc_length",
        "equation_count": problem.equation_count,
        "solver_result": first.to_dict(),
        "sparse_operator": {
            "operator_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
            "equilibrium_linearization_mode": (
                VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
            ),
            "execution_plan_hash": plan.plan_hash,
            "scaling_hash": sparse_solver.binding["scaling"].scaling_hash,
            "global_dof_count": plan.dof_count,
            "free_equation_count": problem.equation_count,
            "global_csr_nnz": int(plan.array("csr_column_indices").size),
            "reduced_csr_nnz": reduced_nnz,
            "dense_free_matrix_entry_count": problem.equation_count**2,
            "dense_tangent_materialized_by_production_path": False,
            "sparse_gate_passed": sparse_gate,
        },
        "verification": {
            **finite_difference,
            "load_coupling_kn_per_m": problem.load_coupling_kn_per_m,
            "load_linearization_primary_rhs_values_kn": (
                load_rhs_primary_values
            ),
            "load_linearization_primary_rhs_varies": (
                len(set(load_rhs_primary_values)) > 1
            ),
            "load_coupling_gate_passed": load_coupling_gate,
            "tangent_solve_count": len(tangent_rows),
            "maximum_tangent_solve_iteration_count": max(
                receipt["solver"]["iteration_count"] for receipt in receipts
            ),
            "maximum_tangent_solve_explicit_residual_inf_norm_kn": max(
                float(row["explicit_residual_inf_norm_kn"])
                for row in tangent_rows
            ),
            "all_tangent_solves_ready": tangent_gate,
            "unique_operator_numeric_values_hash_count": len(
                {
                    receipt["source"]["operator_numeric_values_hash"]
                    for receipt in receipts
                }
            ),
            "exact_chain_reduction_gate_passed": exact_reduction_gate,
            "maximum_chain_reduction_displacement_error_m": max(
                reduction_displacement_errors
            ),
            "maximum_chain_reduction_load_factor_error": max(
                reduction_load_errors
            ),
            "same_dense_reference_checkpoint_count": same_checkpoint_count,
            "dense_reference_gate_passed": dense_reference_gate,
            "maximum_dense_reference_displacement_error_m": displacement_error,
            "maximum_dense_reference_load_factor_error": load_error,
            "deterministic_replay_exact": deterministic_replay_exact,
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "negative_load_branch_reached": first.metrics[
                "negative_load_factor_observed"
            ],
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "claims": {
            "load_factor_coupled_residual_jacobian_arc_length": contract_pass,
            "sparse_state_operator_arc_length_integration": contract_pass,
            "dense_tangent_materialization_avoided": sparse_gate,
            "engine_v2_cpu_fgmres_every_production_tangent_solve": tangent_gate,
            "real_mgt_frame_shell_material_adapter_connected": False,
            "production_scale_sparse_preconditioner": False,
            "production_rocm_hip_nonlinear_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "real_mgt_load_coupled_residual_adapter_not_connected",
            "frame_shell_material_state_commit_rollback_not_connected",
            "production_scale_sparse_preconditioner_not_verified",
            "production_rocm_hip_nonlinear_parity_not_verified",
            "g1_full_load_full_mesh_not_closed",
        ],
        "claim_boundary": LOAD_COUPLED_SPARSE_CHAIN_CLAIM_BOUNDARY,
    }


def build_load_coupled_sparse_chain_arc_length_seed() -> dict[str, Any]:
    """Return an isolated copy of deterministic load-coupled evidence."""

    return deepcopy(_build_load_coupled_sparse_chain_seed_cached())


__all__ = [
    "LOAD_COUPLED_DENSE_REFERENCE_SOLVER_PROFILE",
    "LOAD_COUPLED_SPARSE_CHAIN_CLAIM_BOUNDARY",
    "LOAD_COUPLED_SPARSE_CHAIN_SCHEMA_VERSION",
    "LoadCoupledDenseReferenceStateTangentSolver",
    "LoadCoupledSparseChainShallowArchProblem",
    "build_load_coupled_sparse_chain_arc_length_seed",
    "create_load_coupled_dense_reference_solver",
]
