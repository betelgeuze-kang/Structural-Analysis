from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.benchmark.load_coupled_sparse_chain_arc_length import (
    LoadCoupledSparseChainShallowArchProblem,
    build_load_coupled_sparse_chain_arc_length_seed,
)
from structural_analysis.benchmark.sparse_chain_arc_length import (
    SPARSE_CHAIN_ARC_LENGTH_CONFIG,
    SparseChainShallowArchProblem,
    create_sparse_chain_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    VectorArcLengthContractError,
    vector_arc_length_continuation,
)


def test_load_coupled_displacement_jacobian_matches_centered_difference() -> None:
    problem = LoadCoupledSparseChainShallowArchProblem()
    displacement = problem.exact_free_displacements_m(0.17)
    displacement[4] += 0.002
    load_factor = problem.exact_load_factor(0.17)
    direction = np.linspace(-0.8, 1.1, problem.equation_count)
    step = 1.0e-7

    finite_difference = (
        problem.residual_kn(displacement + step * direction, load_factor)
        - problem.residual_kn(displacement - step * direction, load_factor)
    ) / (2.0 * step)
    action = problem.consistent_state_tangent_action_kn_per_m(
        displacement,
        load_factor,
        direction,
    )

    np.testing.assert_allclose(action, finite_difference, rtol=1.0e-8, atol=1.0e-6)


def test_negative_load_derivative_matches_centered_difference() -> None:
    problem = LoadCoupledSparseChainShallowArchProblem()
    displacement = problem.exact_free_displacements_m(0.17)
    load_factor = problem.exact_load_factor(0.17)
    step = 1.0e-7

    finite_difference = -(
        problem.residual_kn(displacement, load_factor + step)
        - problem.residual_kn(displacement, load_factor - step)
    ) / (2.0 * step)
    derivative = problem.negative_load_derivative_kn(
        displacement,
        load_factor,
    )

    np.testing.assert_allclose(
        derivative,
        finite_difference,
        rtol=1.0e-8,
        atol=1.0e-7,
    )


def test_load_coupled_short_path_uses_sparse_state_fgmres() -> None:
    payload = build_load_coupled_sparse_chain_arc_length_seed()
    metrics = payload["solver_result"]["metrics"]
    verification = payload["verification"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert metrics["contract_pass"] is True
    assert metrics["equilibrium_linearization_mode"] == (
        VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
    )
    assert metrics["accepted_step_count"] == 6
    assert metrics["rejected_step_count"] == 1
    assert metrics["external_tangent_solve_count"] == 61
    assert verification["displacement_jacobian_gate_passed"] is True
    assert verification["negative_load_derivative_gate_passed"] is True
    assert verification["load_linearization_primary_rhs_varies"] is True
    assert verification["exact_chain_reduction_gate_passed"] is True
    assert verification["dense_reference_gate_passed"] is True
    assert verification["maximum_tangent_solve_iteration_count"] == 12


def test_load_coupled_replay_restart_and_claim_boundaries_are_explicit() -> None:
    payload = build_load_coupled_sparse_chain_arc_length_seed()

    assert payload["verification"]["deterministic_replay_exact"] is True
    assert payload["verification"]["checkpoint_restart_exact"] is True
    assert payload["claims"][
        "load_factor_coupled_residual_jacobian_arc_length"
    ] is True
    assert payload["claims"][
        "real_mgt_frame_shell_material_adapter_connected"
    ] is False
    assert payload["claims"]["production_scale_sparse_preconditioner"] is False
    assert payload["claims"]["production_rocm_hip_nonlinear_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_load_coupled_problem_requires_state_tangent_solver() -> None:
    with pytest.raises(
        VectorArcLengthContractError,
        match="requires a state tangent solver",
    ):
        vector_arc_length_continuation(
            LoadCoupledSparseChainShallowArchProblem(),
            config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
        )


def test_incomplete_load_coupled_contract_fails_closed() -> None:
    class IncompleteProblem(SparseChainShallowArchProblem):
        def residual_kn(
            self,
            free_displacements_m: np.ndarray,
            load_factor: float,
        ) -> np.ndarray:
            return self.internal_force_kn(free_displacements_m) - (
                load_factor * self.reference_load_kn()
            )

    problem = IncompleteProblem()
    solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(problem)
    with pytest.raises(
        VectorArcLengthContractError,
        match="load-coupled equilibrium contract is incomplete",
    ):
        vector_arc_length_continuation(
            problem,
            config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
            state_tangent_solver=solver,
        )


def test_checkpoint_binds_load_coupled_equilibrium_mode() -> None:
    coupled = LoadCoupledSparseChainShallowArchProblem()
    coupled_solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(coupled)
    first = vector_arc_length_continuation(
        coupled,
        config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
        state_tangent_solver=coupled_solver,
    )
    midpoint = first.checkpoints[len(first.checkpoints) // 2]
    proportional = SparseChainShallowArchProblem(case_id=coupled.case_id)
    proportional_solver = create_sparse_chain_cpu_fgmres_state_tangent_solver(
        proportional
    )

    with pytest.raises(VectorArcLengthContractError, match="path contract"):
        vector_arc_length_continuation(
            proportional,
            config=SPARSE_CHAIN_ARC_LENGTH_CONFIG,
            resume_from=midpoint,
            state_tangent_solver=proportional_solver,
        )
