from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND,
    create_corotational_fiber_frame_engineering_result_ir,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE,
    CorotationalFiberFrameGeneralError,
    compile_corotational_fiber_frame_general_profile,
    create_corotational_fiber_frame_general_j1_j5_adapter,
    validate_corotational_fiber_frame_general_manifest,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


def _problem() -> StatefulCorotationalFiberFrame2DProblem:
    coordinates = (
        (0.0, 0.0),
        (4.0, 0.0),
        (0.0, 3.0),
        (4.0, 3.0),
        (2.0, 3.0),
        (2.0, 5.0),
    )
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
            ("beam-left", 2, 4),
            ("beam-right", 4, 3),
            ("branch", 4, 5),
        )
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="general-branching-frame",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=((15, 5.0), (16, -10.0)),
        rotation_coordinate_scale_m=4.0,
        prescribed_displacements=((3, 2.0e-4),),
    )


def test_general_j1_j5_binds_branching_supports_and_prescribed_path() -> None:
    problem = _problem()
    compilation = compile_corotational_fiber_frame_general_profile(
        problem,
        model_content_hash=canonical_hash({"fixture": "general-branching-frame.v1"}),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5, 0.75, 1.0),
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-9,
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        ),
    )
    adapter = create_corotational_fiber_frame_general_j1_j5_adapter(compilation, path)
    engineering = create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id="engineering.general_branching_frame",
        source_adapter=adapter,
    )

    assert path.contract_pass is True
    assert (
        compilation.compiler_profile
        == COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE
    )
    assert compilation.support_node_indices == (0, 1)
    assert compilation.branching_node_indices == (4,)
    assert compilation.maximum_node_degree == 3
    assert all(all(row.checks.values()) for row in adapter.stage_receipts)
    assert (
        validate_corotational_fiber_frame_general_manifest(adapter.to_manifest())
        == adapter.to_manifest()
    )
    assert engineering.result_kind == (
        COROTATIONAL_FIBER_FRAME_GENERAL_ENGINEERING_RESULT_KIND
    )
    assert engineering.artifact("node_translation_m")[1, 0] == 2.0e-4
    for factor, step in zip((0.25, 0.5, 0.75, 1.0), path.steps, strict=True):
        assert step.accepted_checkpoint.global_displacements[3] == factor * 2.0e-4
        validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem, step.accepted_checkpoint
        )


def test_prescribed_only_fully_constrained_path_commits_without_newton() -> None:
    coordinates = ((0.0, 0.0), (2.0, 0.0))
    section = make_rectangular_stateful_rc_fiber_section()
    member = StatefulCorotationalFiberFrame2DMember(
        member_id="bar",
        node_i=0,
        node_j=1,
        element=StatefulCorotationalFiberBeam2D(
            node_coordinates_m=coordinates,
            section=section,
            integration_order=2,
            element_id="bar",
        ),
    )
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="prescribed-only",
        node_coordinates_m=coordinates,
        members=(member,),
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=(),
        rotation_coordinate_scale_m=2.0,
        prescribed_displacements=((3, 1.0e-4),),
    )

    path = run_stateful_corotational_fiber_frame2d_load_path(problem, (0.5, 1.0))

    assert path.contract_pass is True
    assert path.final_checkpoint.global_displacements[3] == 1.0e-4
    assert all(
        step.metrics["no_solve_contract_pass"] is True
        and step.trial_solution.metrics["solver_executed"] is False
        and np.linalg.norm(step.trial_assembly.reactions_global, ord=np.inf) > 0.0
        for step in path.steps
    )


def test_general_compiler_rejects_disconnected_or_duplicate_edges() -> None:
    problem = _problem()
    disconnected = replace(problem, members=problem.members[:-1])
    with pytest.raises(
        CorotationalFiberFrameGeneralError,
        match="corotational_general_graph_disconnected",
    ):
        compile_corotational_fiber_frame_general_profile(
            disconnected,
            model_content_hash=canonical_hash({"fixture": "disconnected"}),
        )

    original = problem.members[0]
    duplicate_member = StatefulCorotationalFiberFrame2DMember(
        member_id="parallel-column-left",
        node_i=original.node_i,
        node_j=original.node_j,
        element=StatefulCorotationalFiberBeam2D(
            node_coordinates_m=original.element.node_coordinates_m,
            section=original.element.section,
            integration_order=original.element.integration_order,
            element_id="parallel-column-left",
        ),
    )
    duplicate = replace(problem, members=problem.members + (duplicate_member,))
    with pytest.raises(
        CorotationalFiberFrameGeneralError,
        match="corotational_general_duplicate_edge",
    ):
        compile_corotational_fiber_frame_general_profile(
            duplicate,
            model_content_hash=canonical_hash({"fixture": "duplicate"}),
        )


def test_checkpoint_rejects_tampered_prescribed_displacement() -> None:
    problem = _problem()
    checkpoint = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    with pytest.raises(ValueError, match="state_hash does not match canonical bytes"):
        replace(
            checkpoint,
            global_displacements=(1.0e-4,) + checkpoint.global_displacements[1:],
        )
