from __future__ import annotations

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    COROTATIONAL_FIBER_FRAME_SPARSE_STORAGE_PROFILE,
    assemble_stateful_corotational_fiber_frame2d_sparse,
    compare_corotational_fiber_frame_dense_sparse_assembly,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


def _portal_problem() -> StatefulCorotationalFiberFrame2DProblem:
    coordinates = ((0.0, 0.0), (4.0, 0.0), (0.0, 3.0), (4.0, 3.0))
    section = make_rectangular_stateful_rc_fiber_section()
    members = tuple(
        StatefulCorotationalFiberFrame2DMember(
            member_id=member_id,
            node_i=node_i,
            node_j=node_j,
            element=StatefulCorotationalFiberBeam2D(
                node_coordinates_m=(coordinates[node_i], coordinates[node_j]),
                section=section,
                integration_order=3,
                element_id=member_id,
            ),
        )
        for member_id, node_i, node_j in (
            ("column-left", 0, 2),
            ("column-right", 1, 3),
            ("beam-top", 2, 3),
        )
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="native-sparse-corotational-portal",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=((9, 20.0), (10, -50.0)),
        rotation_coordinate_scale_m=4.0,
    )


def test_native_coo_csr_assembly_matches_dense_and_is_deterministic() -> None:
    problem = _portal_problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    trial = np.asarray(
        [1.0e-4, -2.0e-5, -4.0e-5, 1.2e-4, -2.1e-5, -4.5e-5],
        dtype=np.float64,
    )

    receipt = compare_corotational_fiber_frame_dense_sparse_assembly(
        problem,
        checkpoint,
        target_load_factor=0.75,
        trial_free_coordinates_m=trial,
    )
    first = assemble_stateful_corotational_fiber_frame2d_sparse(
        problem,
        checkpoint,
        target_load_factor=0.75,
        trial_free_coordinates_m=trial,
    )
    repeated = assemble_stateful_corotational_fiber_frame2d_sparse(
        problem,
        checkpoint,
        target_load_factor=0.75,
        trial_free_coordinates_m=trial,
    )

    assert all(receipt.checks.values())
    assert receipt.metrics["tangent_scaled_linf"] <= 1.0e-13
    assert first.storage_profile == COROTATIONAL_FIBER_FRAME_SPARSE_STORAGE_PROFILE
    assert first.raw_coo_entry_count > first.csr_nnz > 0
    assert first.assembly_hash == repeated.assembly_hash
    assert first.csr_pattern_hash == repeated.csr_pattern_hash
    assert first.csr_numeric_hash == repeated.csr_numeric_hash
    assert first.jacobian_csr.has_sorted_indices
    assert first.jacobian_csr.shape == (6, 6)
    assert first.to_manifest()["assembly_hash"] == first.assembly_hash


def test_sparse_load_path_uses_native_assembly_and_matches_dense_solution() -> None:
    problem = _portal_problem()
    factors = (0.25, 0.5, 0.75, 1.0)
    dense = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        factors,
        config=NewtonRaphsonConfig(matrix_backend=VECTOR_MATRIX_BACKEND),
    )
    sparse = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        factors,
        config=NewtonRaphsonConfig(matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
    )

    assert dense.contract_pass is True
    assert sparse.contract_pass is True
    assert all(
        step.metrics["native_sparse_assembly_used"] is True
        and step.metrics["sparse_backend_used"] is True
        and step.metrics["sparse_factorization_diagnostics_passed"] is True
        and step.metrics["sparse_factorization_count"] > 0
        and step.metrics["sparse_factorization_max_condition_number_1"] < 1.0e12
        and step.metrics["sparse_factorization_max_backward_error"] <= 1.0e-12
        and step.metrics["fallback_used"] is False
        and step.metrics["regularization_used"] is False
        for step in sparse.steps
    )
    np.testing.assert_allclose(
        sparse.final_checkpoint.global_displacements,
        dense.final_checkpoint.global_displacements,
        rtol=1.0e-12,
        atol=1.0e-14,
    )
