from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.benchmark.sparse_chain_arc_length import (
    SPARSE_CHAIN_ARC_LENGTH_CONFIG,
    SPARSE_CHAIN_EQUATION_COUNT,
    SparseChainShallowArchProblem,
    build_sparse_chain_cpu_fgmres_arc_length_seed,
    create_sparse_chain_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthContractError,
    VectorArcLengthTangentSolve,
    vector_arc_length_continuation,
)


class _FalseReadyZeroStateSolver:
    profile = "false_ready_zero_state_solver.v1"
    contract_hash = "sha256:" + "e" * 64

    def solve_at_state(
        self,
        problem,
        free_displacements_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        load_factor: float,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve:
        del problem, free_displacements_m, load_factor, solve_id
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=True,
            terminal_reason="falsely_reported_ready",
            solution_free=tuple(0.0 for _ in right_hand_side_kn),
            receipt={},
        )


def test_sparse_chain_state_tangent_action_matches_centered_difference() -> None:
    problem = SparseChainShallowArchProblem()
    displacement = problem.exact_free_displacements_m(0.17)
    displacement[4] += 0.002
    direction = np.linspace(-0.8, 1.1, problem.equation_count)
    step = 1.0e-7

    finite_difference = (
        problem.internal_force_kn(displacement + step * direction)
        - problem.internal_force_kn(displacement - step * direction)
    ) / (2.0 * step)
    action = problem.consistent_tangent_action_kn_per_m(
        displacement,
        direction,
    )

    np.testing.assert_allclose(action, finite_difference, rtol=1.0e-8, atol=1.0e-6)
    assert not hasattr(problem, "consistent_tangent_kn_per_m")


def test_sparse_chain_full_short_path_uses_state_csr_fgmres() -> None:
    payload = build_sparse_chain_cpu_fgmres_arc_length_seed()
    metrics = payload["solver_result"]["metrics"]
    operator = payload["sparse_operator"]
    verification = payload["verification"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert metrics["contract_pass"] is True
    assert metrics["equation_count"] == SPARSE_CHAIN_EQUATION_COUNT
    assert metrics["accepted_step_count"] == 5
    assert metrics["rejected_step_count"] == 1
    assert metrics["rollback_exact"] is True
    assert metrics["tangent_linear_solver_mode"] == (
        VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE
    )
    assert metrics["negative_load_factor_observed"] is True
    assert operator["global_dof_count"] == 72
    assert operator["free_equation_count"] == 12
    assert operator["global_csr_nnz"] == 94
    assert operator["reduced_csr_nnz"] == 34
    assert operator["dense_free_matrix_entry_count"] == 144
    assert operator["dense_tangent_materialized_by_solver"] is False
    assert operator["sparse_gate_passed"] is True
    assert verification["tangent_solve_count"] == 52
    assert verification["maximum_tangent_solve_iteration_count"] == 12
    assert (
        verification["maximum_tangent_solve_explicit_residual_inf_norm_kn"]
        <= SPARSE_CHAIN_ARC_LENGTH_CONFIG.tangent_solve_residual_tolerance_kn
    )
    assert verification["exact_chain_reduction_gate_passed"] is True
    assert verification["dense_reference_gate_passed"] is True
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0


def test_sparse_chain_replay_restart_and_claim_boundaries_are_explicit() -> None:
    payload = build_sparse_chain_cpu_fgmres_arc_length_seed()

    assert payload["verification"]["deterministic_replay_exact"] is True
    assert payload["verification"]["checkpoint_restart_exact"] is True
    assert payload["claims"]["sparse_state_operator_arc_length_integration"] is True
    assert payload["claims"]["dense_tangent_materialization_avoided"] is True
    assert payload["claims"]["production_scale_sparse_preconditioner"] is False
    assert payload["claims"]["general_frame_shell_arc_length"] is False
    assert payload["claims"]["production_rocm_hip_nonlinear_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_sparse_state_solver_contract_is_checkpoint_bound() -> None:
    problem = SparseChainShallowArchProblem()
    solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(problem)
    first = vector_arc_length_continuation(
        problem,
        config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
        state_tangent_solver=solver,
    )
    midpoint = first.checkpoints[len(first.checkpoints) // 2]
    tampered_solver = replace(solver, contract_hash="sha256:" + "f" * 64)

    with pytest.raises(VectorArcLengthContractError, match="path contract"):
        vector_arc_length_continuation(
            problem,
            config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
            resume_from=midpoint,
            state_tangent_solver=tampered_solver,
        )


def test_sparse_state_solver_recomputes_and_gates_explicit_residual() -> None:
    result = vector_arc_length_continuation(
        SparseChainShallowArchProblem(),
        config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
        state_tangent_solver=_FalseReadyZeroStateSolver(),
    )

    assert result.status == "blocked"
    assert len(result.checkpoints) == 1
    assert result.terminal_reason == "minimum_arc_length_exhausted"
    assert all(row["accepted"] is False for row in result.attempts)
    assert all(
        "external tangent solve failed the explicit residual gate"
        in row["stop_reason"]
        for row in result.attempts
    )
