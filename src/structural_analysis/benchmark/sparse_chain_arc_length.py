"""Sparse state-operator arc-length integration through Engine v2 CPU FGMRES."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from structural_analysis.benchmark.geometric_nonlinear import TwoBarShallowArch
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    create_execution_plan,
)
from structural_analysis.engine_v2.cpu_fgmres_tangent import (
    solve_cpu_fgmres_tangent_system,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE,
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthConfig,
    VectorArcLengthLoadCoupledStateTangentProblem,
    VectorArcLengthStateTangentProblem,
    VectorArcLengthTangentSolve,
    vector_arc_length_continuation,
)


SPARSE_CHAIN_ARC_LENGTH_SCHEMA_VERSION = (
    "phase2-sparse-chain-cpu-fgmres-arc-length.v1"
)
SPARSE_CHAIN_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This receipt verifies a complete short arc-length path on one analytic "
    "12-equation sparse chain without materializing its tangent as a dense "
    "matrix. Every predictor and Schur-corrector tangent solve uses an exact "
    "sparse CSR ExecutionPlan and deterministic Engine v2 CPU FGMRES. It does "
    "not assemble a frame/shell model, prove production scale or preconditioner "
    "effectiveness, establish ROCm/HIP parity, reach G1 full-building load, or "
    "provide release-readiness evidence."
)
SPARSE_CHAIN_STATE_TANGENT_SOLVER_PROFILE = (
    "sparse_chain_state_csr_engine_v2_cpu_fgmres.v1"
)
SPARSE_CHAIN_EQUATION_COUNT = 12
SPARSE_CHAIN_ARC_LENGTH_CONFIG = VectorArcLengthConfig(
    target_monitor_displacement_m=0.20,
    initial_arc_length_m=0.10,
    minimum_arc_length_m=0.0125,
    maximum_arc_length_m=0.10,
    failed_step_reduction=0.5,
    maximum_corrector_iterations=5,
    tangent_solve_residual_tolerance_kn=1.0e-9,
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


@dataclass(frozen=True)
class SparseChainShallowArchProblem:
    """Conservative tridiagonal chain with an exact shallow-arch reduction."""

    case_id: str = "sparse_chain_shallow_arch_state_operator_arc_length"
    equation_count: int = SPARSE_CHAIN_EQUATION_COUNT
    chain_ratio: float = 0.65
    coupling_stiffness_kn_per_m: float = 400.0
    arch: TwoBarShallowArch = field(default_factory=TwoBarShallowArch)

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.equation_count, dtype=float)

    def initial_load_factor(self) -> float:
        return 0.0

    def reference_load_kn(self) -> np.ndarray:
        load = np.zeros(self.equation_count, dtype=float)
        load[0] = 1.0
        return load

    def internal_force_kn(self, free_displacements_m: np.ndarray) -> np.ndarray:
        displacements = np.asarray(free_displacements_m, dtype=float)
        if displacements.shape != (self.equation_count,):
            raise ValueError("free displacement dimension is invalid")
        force = np.zeros(self.equation_count, dtype=float)
        force[0] = self.arch.internal_force_kn(float(displacements[0]))
        stiffness = self.coupling_stiffness_kn_per_m
        ratio = self.chain_ratio
        for index in range(1, self.equation_count):
            extension = displacements[index] - ratio * displacements[index - 1]
            link_force = stiffness * extension
            force[index] += link_force
            force[index - 1] -= ratio * link_force
        return force

    def tangent_diagonal_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        displacements = np.asarray(free_displacements_m, dtype=float)
        if displacements.shape != (self.equation_count,):
            raise ValueError("free displacement dimension is invalid")
        stiffness = self.coupling_stiffness_kn_per_m
        ratio = self.chain_ratio
        diagonal = np.full(
            self.equation_count,
            stiffness * (1.0 + ratio**2),
            dtype=float,
        )
        diagonal[0] = (
            self.arch.consistent_tangent_kn_per_m(float(displacements[0]))
            + stiffness * ratio**2
        )
        diagonal[-1] = stiffness
        return diagonal

    def consistent_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        direction = np.asarray(direction_m, dtype=float)
        if direction.shape != (self.equation_count,):
            raise ValueError("tangent direction dimension is invalid")
        diagonal = self.tangent_diagonal_kn_per_m(free_displacements_m)
        result = diagonal * direction
        off_diagonal = -self.coupling_stiffness_kn_per_m * self.chain_ratio
        result[:-1] += off_diagonal * direction[1:]
        result[1:] += off_diagonal * direction[:-1]
        return result

    def exact_free_displacements_m(self, primary_displacement_m: float) -> np.ndarray:
        return np.asarray(
            [
                self.chain_ratio**index * primary_displacement_m
                for index in range(self.equation_count)
            ],
            dtype=float,
        )


@dataclass(frozen=True)
class SparseChainDenseReferenceProblem(SparseChainShallowArchProblem):
    """Verification-only dense materialization of the same sparse operator."""

    def consistent_tangent_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        identity = np.eye(self.equation_count, dtype=float)
        return np.column_stack(
            [
                self.consistent_tangent_action_kn_per_m(
                    free_displacements_m,
                    identity[:, column],
                )
                for column in range(self.equation_count)
            ]
        )


def _csr_pattern(problem: SparseChainShallowArchProblem) -> tuple[np.ndarray, np.ndarray]:
    dof_count = problem.equation_count * 6
    free_dofs = set(range(0, dof_count, 6))
    row_ptr = [0]
    columns: list[int] = []
    for global_row in range(dof_count):
        if global_row in free_dofs:
            local_row = global_row // 6
            columns.extend(
                6 * local_column
                for local_column in range(
                    max(0, local_row - 1),
                    min(problem.equation_count, local_row + 2),
                )
            )
        else:
            columns.append(global_row)
        row_ptr.append(len(columns))
    return (
        np.asarray(row_ptr, dtype="<i8"),
        np.asarray(columns, dtype="<i4"),
    )


def _build_binding(problem: SparseChainShallowArchProblem) -> dict[str, Any]:
    node_count = problem.equation_count
    dof_count = node_count * 6
    free_dofs = np.arange(0, dof_count, 6, dtype="<i4")
    constrained_dofs = np.asarray(
        [index for index in range(dof_count) if index % 6 != 0],
        dtype="<i4",
    )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free_dofs] = np.arange(node_count, dtype="<i4")
    row_ptr, column_indices = _csr_pattern(problem)
    base = create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="SPARSE_CHAIN_ARC_LENGTH",
        operator_id="sparse-chain-consistent-tangent",
        operator_version="sparse-chain-consistent-tangent.v1",
        operator_hash=_hash("5"),
        node_ids=tuple(f"N{index:02d}" for index in range(node_count)),
        element_ids=tuple(f"L{index:02d}" for index in range(node_count - 1)),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(node_count, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.asarray(
            [
                [
                    *range(6 * index, 6 * index + 6),
                    *range(6 * (index + 1), 6 * (index + 1) + 6),
                ]
                for index in range(node_count - 1)
            ],
            dtype="<i4",
        ),
        constrained_dofs=constrained_dofs,
        free_dofs=free_dofs,
        csr_row_ptr=row_ptr,
        csr_column_indices=column_indices,
    )
    coordinates = np.zeros((node_count, 3), dtype="<f8")
    coordinates[:, 0] = np.arange(node_count, dtype=float)
    reference_equation_load = np.zeros(dof_count, dtype="<f8")
    reference_equation_load[free_dofs[0]] = 1.0
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_equation_load,
    )
    return {
        "plan": plan,
        "scaling": scaling,
        "coordinates": coordinates,
        "reference_equation_load": reference_equation_load,
        "free_dofs": free_dofs,
    }


def _global_csr_values(
    problem: SparseChainShallowArchProblem,
    binding: dict[str, Any],
    free_displacements_m: np.ndarray,
    load_factor: float,
) -> np.ndarray:
    plan = binding["plan"]
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    state_diagonal = getattr(
        problem,
        "state_tangent_diagonal_kn_per_m",
        None,
    )
    diagonal = (
        state_diagonal(free_displacements_m, load_factor)
        if callable(state_diagonal)
        else problem.tangent_diagonal_kn_per_m(free_displacements_m)
    )
    off_diagonal = -problem.coupling_stiffness_kn_per_m * problem.chain_ratio
    values = np.zeros(columns.size, dtype="<f8")
    for global_row in range(plan.dof_count):
        for position in range(int(row_ptr[global_row]), int(row_ptr[global_row + 1])):
            global_column = int(columns[position])
            if global_row % 6 != 0:
                values[position] = 1.0 if global_column == global_row else 0.0
                continue
            local_row = global_row // 6
            local_column = global_column // 6
            values[position] = (
                diagonal[local_row]
                if local_row == local_column
                else off_diagonal
            )
    return values


@dataclass(frozen=True)
class SparseChainCPUFGMRESStateTangentSolver:
    """Exact sparse-CSR state adapter for the analytic chain problem."""

    binding: dict[str, Any]
    profile: str
    contract_hash: str

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
        if not isinstance(problem, SparseChainShallowArchProblem):
            raise TypeError("sparse chain solver received an incompatible problem")
        solve = solve_cpu_fgmres_tangent_system(
            execution_plan=self.binding["plan"],
            scaling=self.binding["scaling"],
            node_coordinates_m=self.binding["coordinates"],
            reference_equation_load_si=self.binding["reference_equation_load"],
            global_csr_values_si=_global_csr_values(
                problem,
                self.binding,
                free_displacements_m,
                load_factor,
            ),
            right_hand_side_free=right_hand_side_kn,
            solution_artifact_uri=(
                f"artifact://sparse-chain-arc-length/{solve_id}/solution_free.f64le"
            ),
            max_iterations=problem.equation_count * 2,
            restart_length=problem.equation_count,
            relative_tolerance_scaled_l2=1.0e-12,
            absolute_tolerance_scaled_l2=1.0e-14,
            explicit_residual_tolerance=1.0e-9,
        )
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=solve.contract_pass,
            terminal_reason=solve.terminal_reason,
            solution_free=tuple(float(value) for value in solve.solution_free),
            receipt=solve.to_manifest(),
        )


def create_sparse_chain_cpu_fgmres_state_tangent_solver(
    problem: SparseChainShallowArchProblem,
) -> SparseChainCPUFGMRESStateTangentSolver:
    binding = _build_binding(problem)
    equilibrium_linearization_mode = (
        VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        if callable(getattr(problem, "residual_kn", None))
        else VECTOR_ARC_LENGTH_PROPORTIONAL_EQUILIBRIUM_MODE
    )
    contract_hash = canonical_hash(
        {
            "profile": SPARSE_CHAIN_STATE_TANGENT_SOLVER_PROFILE,
            "operator_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
            "execution_plan_hash": binding["plan"].plan_hash,
            "scaling_hash": binding["scaling"].scaling_hash,
            "equation_count": problem.equation_count,
            "chain_ratio": problem.chain_ratio,
            "coupling_stiffness_kn_per_m": problem.coupling_stiffness_kn_per_m,
            "load_coupling_kn_per_m": getattr(
                problem,
                "load_coupling_kn_per_m",
                None,
            ),
            "equilibrium_linearization_mode": (
                equilibrium_linearization_mode
            ),
            "max_iterations": problem.equation_count * 2,
            "restart_length": problem.equation_count,
            "relative_tolerance_scaled_l2": 1.0e-12,
            "absolute_tolerance_scaled_l2": 1.0e-14,
            "explicit_residual_tolerance": 1.0e-9,
            "preconditioner_profile": "identity_right_preconditioner.v1",
        }
    )
    return SparseChainCPUFGMRESStateTangentSolver(
        binding=binding,
        profile=SPARSE_CHAIN_STATE_TANGENT_SOLVER_PROFILE,
        contract_hash=contract_hash,
    )


def _tangent_solve_rows(attempts: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
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


@lru_cache(maxsize=1)
def _build_sparse_chain_cpu_fgmres_arc_length_seed_cached() -> dict[str, Any]:
    """Build sparse operator, deterministic replay, restart, and dense-reference gates."""

    problem = SparseChainShallowArchProblem()
    config = SPARSE_CHAIN_ARC_LENGTH_CONFIG
    solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(problem)
    first = vector_arc_length_continuation(
        problem,
        config=config,
        state_tangent_solver=solver,
    )
    second = vector_arc_length_continuation(
        problem,
        config=config,
        state_tangent_solver=solver,
    )
    restart_checkpoint = first.checkpoints[len(first.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        problem,
        config=config,
        resume_from=restart_checkpoint,
        state_tangent_solver=solver,
    )
    dense_reference = vector_arc_length_continuation(
        SparseChainDenseReferenceProblem(),
        config=config,
    )
    same_checkpoint_count = len(first.checkpoints) == len(dense_reference.checkpoints)
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
    reduction_errors = [
        float(
            np.max(
                np.abs(
                    np.asarray(checkpoint.free_displacements_m, dtype=float)
                    - problem.exact_free_displacements_m(
                        checkpoint.free_displacements_m[0]
                    )
                )
            )
        )
        for checkpoint in first.checkpoints
    ]
    load_reduction_errors = [
        abs(
            checkpoint.load_factor
            - problem.arch.internal_force_kn(checkpoint.free_displacements_m[0])
        )
        for checkpoint in first.checkpoints
    ]
    tangent_solve_rows = _tangent_solve_rows(first.attempts)
    receipts = [row["receipt"] for row in tangent_solve_rows]
    plan = solver.binding["plan"]
    reduced_nnz = 3 * problem.equation_count - 2
    sparse_gate = bool(
        plan.array("csr_column_indices").size
        == reduced_nnz + 5 * problem.equation_count
        and reduced_nnz < problem.equation_count**2
        and first.metrics["tangent_linear_solver_mode"]
        == VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE
        and all(
            row["operator_mode"] == VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE
            for row in tangent_solve_rows
        )
    )
    exact_reduction_gate = bool(
        max(reduction_errors) <= 1.0e-11
        and max(load_reduction_errors) <= config.residual_tolerance_kn
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
        tangent_solve_rows
        and all(receipt["contract_pass"] is True for receipt in receipts)
        and max(
            float(row["explicit_residual_inf_norm_kn"])
            for row in tangent_solve_rows
        )
        <= config.tangent_solve_residual_tolerance_kn
    )
    contract_pass = bool(
        first.status == "ready"
        and sparse_gate
        and exact_reduction_gate
        and dense_reference_gate
        and deterministic_replay_exact
        and checkpoint_restart_exact
        and tangent_gate
        and first.metrics["negative_load_factor_observed"] is True
        and first.metrics["fallback_count"] == 0
        and first.metrics["regularization_count"] == 0
    )
    return {
        "schema_version": SPARSE_CHAIN_ARC_LENGTH_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": problem.case_id,
        "analysis_type": "sparse_state_operator_cpu_fgmres_arc_length",
        "equation_count": problem.equation_count,
        "solver_result": first.to_dict(),
        "sparse_operator": {
            "operator_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
            "execution_plan_hash": plan.plan_hash,
            "scaling_hash": solver.binding["scaling"].scaling_hash,
            "global_dof_count": plan.dof_count,
            "free_equation_count": problem.equation_count,
            "global_csr_nnz": int(plan.array("csr_column_indices").size),
            "reduced_csr_nnz": reduced_nnz,
            "dense_free_matrix_entry_count": problem.equation_count**2,
            "dense_tangent_materialized_by_solver": False,
            "sparse_gate_passed": sparse_gate,
        },
        "verification": {
            "tangent_solve_count": len(tangent_solve_rows),
            "maximum_tangent_solve_iteration_count": max(
                receipt["solver"]["iteration_count"] for receipt in receipts
            ),
            "maximum_tangent_solve_explicit_residual_inf_norm_kn": max(
                float(row["explicit_residual_inf_norm_kn"])
                for row in tangent_solve_rows
            ),
            "all_tangent_solves_ready": tangent_gate,
            "tangent_solve_hashes": [
                receipt["solve_hash"] for receipt in receipts
            ],
            "operator_numeric_values_hashes": [
                receipt["source"]["operator_numeric_values_hash"]
                for receipt in receipts
            ],
            "unique_operator_numeric_values_hash_count": len(
                {
                    receipt["source"]["operator_numeric_values_hash"]
                    for receipt in receipts
                }
            ),
            "exact_chain_reduction_gate_passed": exact_reduction_gate,
            "maximum_chain_reduction_displacement_error_m": max(reduction_errors),
            "maximum_chain_reduction_load_factor_error": max(
                load_reduction_errors
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
            "sparse_state_operator_arc_length_integration": contract_pass,
            "dense_tangent_materialization_avoided": sparse_gate,
            "engine_v2_cpu_fgmres_every_tangent_solve": tangent_gate,
            "failed_step_rollback": first.metrics["rollback_exact"],
            "checkpoint_restart": checkpoint_restart_exact,
            "deterministic_replay": deterministic_replay_exact,
            "dense_reference_equivalence": dense_reference_gate,
            "production_scale_sparse_preconditioner": False,
            "general_frame_shell_arc_length": False,
            "production_rocm_hip_nonlinear_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "frame_shell_consistent_residual_not_connected",
            "production_scale_sparse_preconditioner_not_verified",
            "production_rocm_hip_nonlinear_parity_not_verified",
            "g1_full_load_full_mesh_not_closed",
        ],
        "claim_boundary": SPARSE_CHAIN_ARC_LENGTH_CLAIM_BOUNDARY,
    }


def build_sparse_chain_cpu_fgmres_arc_length_seed() -> dict[str, Any]:
    """Return an isolated copy of the deterministic cached evidence payload."""

    return deepcopy(_build_sparse_chain_cpu_fgmres_arc_length_seed_cached())


__all__ = [
    "SPARSE_CHAIN_ARC_LENGTH_CLAIM_BOUNDARY",
    "SPARSE_CHAIN_ARC_LENGTH_CONFIG",
    "SPARSE_CHAIN_ARC_LENGTH_SCHEMA_VERSION",
    "SPARSE_CHAIN_EQUATION_COUNT",
    "SPARSE_CHAIN_STATE_TANGENT_SOLVER_PROFILE",
    "SparseChainCPUFGMRESStateTangentSolver",
    "SparseChainDenseReferenceProblem",
    "SparseChainShallowArchProblem",
    "build_sparse_chain_cpu_fgmres_arc_length_seed",
    "create_sparse_chain_cpu_fgmres_state_tangent_solver",
]
