from __future__ import annotations

import numpy as np

from structural_analysis.assembly.corotational_frame2d_member_features import (
    CorotationalFrame2DMemberFeatures,
    consistent_uniform_load_element_global,
    element_end_coordinates_m,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
    physical_3dof_to_canonical_6dof,
    validate_fiber_frame_execution_topology_against_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
    trace_stateful_fiber_frame2d_free_physical_residual,
    validate_fiber_frame_physical_equation_scaling_against_problem,
    validate_fiber_frame_physical_residual_trace,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)


MODEL_HASH = "sha256:" + "7" * 64
COORDINATES = ((0.0, 0.0), (4.0, 0.0))


def _problem(*, release_j_rz: bool = False) -> StatefulCorotationalFiberFrame2DProblem:
    features = CorotationalFrame2DMemberFeatures(
        offset_i_global_m=(0.2, 0.0),
        offset_j_global_m=(-0.1, 0.0),
        release_j_rz=release_j_rz,
        uniform_load_local_kn_per_m=(0.0, -2.0),
    )
    member = StatefulCorotationalFiberFrame2DMember(
        member_id="M1",
        node_i=0,
        node_j=1,
        element=StatefulCorotationalFiberBeam2D(
            node_coordinates_m=element_end_coordinates_m(
                COORDINATES[0],
                COORDINATES[1],
                features,
            ),
            section=make_rectangular_stateful_rc_fiber_section(),
            integration_order=3,
            element_id="M1",
        ),
        features=features,
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="corotational-topology-scaling",
        node_coordinates_m=COORDINATES,
        members=(member,),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((4, -5.0),),
        rotation_coordinate_scale_m=4.0,
    )


def test_corotational_topology_binds_member_features_and_complete_reference_load() -> None:
    problem = _problem()
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("N1", "N2"),
    )

    expected_source = problem.reference_external_load_vector().copy()
    member = problem.members[0]
    expected_source[list(problem.member_global_dofs(member))] += (
        consistent_uniform_load_element_global(member.element, member.features)
    )
    np.testing.assert_array_equal(
        plan.array("reference_external_load_physical_6dof"),
        physical_3dof_to_canonical_6dof(plan, expected_source),
    )
    assert plan.node_ids == ("N1", "N2")
    assert plan.member_ids == ("M1",)
    validate_fiber_frame_execution_topology_against_problem(problem, plan)

    released = _problem(release_j_rz=True)
    released_plan = compile_stateful_fiber_frame2d_execution_topology(
        released,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("N1", "N2"),
    )
    assert released.members[0].element.contract_hash == member.element.contract_hash
    assert released.members[0].features.contract_hash != member.features.contract_hash
    assert released_plan.operator_hash != plan.operator_hash
    assert released_plan.source_identity_hash != plan.source_identity_hash
    assert released_plan.plan_hash != plan.plan_hash


def test_corotational_equation_scaling_traces_force_and_moment_residuals() -> None:
    problem = _problem()
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("N1", "N2"),
    )
    binding = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    checkpoint = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        checkpoint,
        target_load_factor=1.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    trace = trace_stateful_fiber_frame2d_free_physical_residual(
        topology_plan=plan,
        scaling_binding=binding,
        raw_free_residual_source_3dof=assembly.residual_kn,
    )

    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        plan,
        binding,
    )
    validate_fiber_frame_physical_residual_trace(
        trace,
        topology_plan=plan,
        scaling_binding=binding,
    )
    assert binding.characteristic_length_m > 0.0
    assert binding.reference_force_n > 0.0
    assert trace.raw_translation_linf_n > 0.0
    assert trace.raw_rotation_linf_nm > 0.0
    assert trace.scaled_linf > 0.0
    assert trace.governing_node_id in {"N1", "N2"}
    assert trace.governing_dof in {"UX", "UY", "RZ"}
