from __future__ import annotations

import numpy as np

from structural_analysis.assembly.corotational_frame2d_member_features import (
    CorotationalFrame2DMemberFeatures,
    element_end_coordinates_m,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    create_corotational_fiber_frame_engineering_result_ir,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    compile_corotational_fiber_frame_general_profile,
    create_corotational_fiber_frame_general_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    compare_corotational_fiber_frame_dense_sparse_assembly,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


def _member(
    member_id: str,
    nodes: tuple[tuple[float, float], tuple[float, float]],
    features: CorotationalFrame2DMemberFeatures | None = None,
) -> StatefulCorotationalFiberFrame2DMember:
    selected = features or CorotationalFrame2DMemberFeatures()
    element = StatefulCorotationalFiberBeam2D(
        node_coordinates_m=element_end_coordinates_m(nodes[0], nodes[1], selected),
        section=make_rectangular_stateful_rc_fiber_section(),
        integration_order=3,
        element_id=member_id,
    )
    return StatefulCorotationalFiberFrame2DMember(
        member_id=member_id,
        node_i=0,
        node_j=1,
        element=element,
        features=selected,
    )


def test_load_factor_residual_derivative_includes_prescribed_displacement() -> None:
    nodes = ((0.0, 0.0), (3.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="load-factor-linearization",
        node_coordinates_m=nodes,
        members=(_member("beam", nodes),),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((4, -10.0),),
        rotation_coordinate_scale_m=4.0,
        prescribed_displacements=((0, 1.0e-4),),
    )
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    free = np.asarray([2.0e-4, -3.0e-4, 4.0e-4])
    load_factor = 0.4
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=load_factor,
        trial_free_coordinates_m=free,
    )
    # The constitutive integration is deterministic but its internal trial
    # arithmetic is not intended for machine-epsilon finite differencing.
    step = 1.0e-4
    forward = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=load_factor + step,
        trial_free_coordinates_m=free,
    )
    backward = assemble_stateful_corotational_fiber_frame2d(
        problem,
        initial,
        target_load_factor=load_factor - step,
        trial_free_coordinates_m=free,
    )
    finite_difference = (forward.residual_kn - backward.residual_kn) / (2.0 * step)
    scaled_error = float(
        np.max(np.abs(finite_difference - assembly.residual_load_factor_derivative_kn))
        / max(1.0, float(np.max(np.abs(finite_difference))))
    )

    assert scaled_error < 2.0e-8
    parity = compare_corotational_fiber_frame_dense_sparse_assembly(
        problem,
        initial,
        target_load_factor=load_factor,
        trial_free_coordinates_m=free,
    )
    assert parity.checks["load_factor_derivative_parity"] is True


def _feature_problem() -> StatefulCorotationalFiberFrame2DProblem:
    nodes = ((0.0, 0.0), (4.0, 0.0))
    features = CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.0),
        offset_j_global_m=(-0.2, 0.0),
        release_j_rz=True,
        uniform_load_local_kn_per_m=(0.0, -2.0),
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-displacement-control",
        node_coordinates_m=nodes,
        members=(_member("released-beam", nodes, features),),
        fixed_global_dofs=(0, 1, 2, 5),
        reference_external_loads=(),
        rotation_coordinate_scale_m=4.0,
    )


def _path(matrix_backend: str):
    problem = _feature_problem()
    terminal = -1.6e-4
    path = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        (-4.0e-5, -8.0e-5, -1.2e-4, terminal),
        controlled_global_dof=4,
        terminal_control_displacement=terminal,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-9,
            max_iterations=60,
            matrix_backend=matrix_backend,
        ),
    )
    return problem, path


def test_direct_displacement_control_dense_sparse_parity_and_exact_recovery() -> None:
    problem, dense = _path(VECTOR_MATRIX_BACKEND)
    _sparse_problem, sparse = _path(VECTOR_SPARSE_MATRIX_BACKEND)

    assert dense.contract_pass is True
    assert sparse.contract_pass is True
    np.testing.assert_allclose(
        dense.final_checkpoint.global_displacements,
        sparse.final_checkpoint.global_displacements,
        rtol=1.0e-12,
        atol=1.0e-15,
    )
    assert dense.final_checkpoint.load_factor == sparse.final_checkpoint.load_factor
    assert dense.final_checkpoint.global_displacements[4] == -1.6e-4
    assert dense.final_checkpoint.load_factor != 1.0
    assert all(step.metrics["control_target_reached"] is True for step in dense.steps)
    assert all(
        step.metrics["control_mode"] == "displacement_control" for step in dense.steps
    )

    compilation = compile_corotational_fiber_frame_general_profile(
        problem,
        model_content_hash=canonical_hash(
            {"fixture": "direct-displacement-control.v1"}
        ),
    )
    adapter = create_corotational_fiber_frame_general_j1_j5_adapter(compilation, dense)
    engineering = create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id="engineering.direct_displacement_control",
        source_adapter=adapter,
    )

    assert adapter.stage_receipts[-1].contract_profile.endswith(
        "terminal_displacement_control_convergence.v1"
    )
    assert engineering.load_factor == dense.final_checkpoint.load_factor
    assert engineering.artifact("node_translation_m")[1, 1] == -1.6e-4
    assert engineering.metrics["terminal_assembly_replay_exact"] is True

    targets = (-4.0e-5, -8.0e-5, -1.2e-4, -1.6e-4)
    solver_config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-9,
        max_iterations=60,
        matrix_backend=VECTOR_MATRIX_BACKEND,
    )
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[:2],
        controlled_global_dof=4,
        terminal_control_displacement=targets[-1],
        config=solver_config,
    )
    suffix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[2:],
        controlled_global_dof=4,
        terminal_control_displacement=targets[-1],
        initial_checkpoint=prefix.final_checkpoint,
        config=solver_config,
    )
    assert prefix.contract_pass is True
    assert suffix.contract_pass is True
    assert suffix.final_checkpoint.canonical_bytes() == (
        dense.final_checkpoint.canonical_bytes()
    )


def test_failed_displacement_control_step_rolls_back_exactly() -> None:
    problem = _feature_problem()
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)

    blocked = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        problem,
        initial,
        controlled_global_dof=4,
        target_control_displacement=-1.6e-4,
        terminal_control_displacement=-1.6e-4,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-14,
            increment_tolerance=1.0e-16,
            max_iterations=1,
        ),
    )

    assert blocked.status == "blocked"
    assert blocked.committed is False
    assert blocked.accepted_checkpoint is initial
    assert blocked.accepted_checkpoint.canonical_bytes() == initial.canonical_bytes()
    assert blocked.metrics["rollback_exact"] is True
