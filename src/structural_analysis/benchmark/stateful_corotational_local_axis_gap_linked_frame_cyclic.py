"""Fixed-reference local-axis compression-only gap benchmark."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_link import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY,
    StatefulCorotationalFiberFrame2DCompressionOnlyGapLink,
    StatefulCorotationalFiberFrame2DLinkLoadPathResult,
    StatefulCorotationalFiberFrame2DLinkProblem,
    finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check,
    run_stateful_corotational_fiber_frame2d_link_load_path,
    solve_stateful_corotational_fiber_frame2d_link_load_step,
)
from structural_analysis.benchmark.stateful_corotational_gap_linked_frame_cyclic import (
    _assess_pre_roundoff_quadratic_convergence,
    _path_ancestry_exact,
    _replay_exact,
)
from structural_analysis.benchmark.stateful_corotational_local_axis_linked_frame_cyclic import (
    LOCAL_AXIS_LINKED_FRAME_ANCHOR_NODE,
    LOCAL_AXIS_LINKED_FRAME_BASE_TRANSLATION_DOFS,
    LOCAL_AXIS_LINKED_FRAME_COLUMN_AXIAL_RIGIDITY_KN,
    LOCAL_AXIS_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2,
    LOCAL_AXIS_LINKED_FRAME_DIRECTIONAL_COMPLIANCE_M_PER_KN,
    LOCAL_AXIS_LINKED_FRAME_MEMBER_CONNECTIVITY,
    LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M,
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION,
    LOCAL_AXIS_LINKED_FRAME_TOP_NODE,
    LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS,
    make_stateful_corotational_local_axis_linked_frame_cyclic_problem,
)
from structural_analysis.materials.compression_only_gap_link import (
    GAP_LINK_ACTIVE_SET_ALGORITHM,
    GAP_LINK_CLOSURE_CONVENTION,
    GAP_LINK_TANGENT_DEFINITION,
    CompressionOnlyGapLink,
    finite_difference_gap_link_tangent_check,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
)


STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-local-axis-gap-linked-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_FORMULATION = (
    "one_corotational_fiber_cantilever_braced_to_a_fixed_anchor_by_one_"
    "fixed_reference_local_axis_frictionless_compression_only_elastic_gap"
)
STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded planar elastic-carrier cantilever "
    "connected to a fixed anchor by a 45-degree frictionless compression-only "
    "gap whose normal is fixed by the undeformed node coordinates. It exercises "
    "open/closed active-set transitions, four-DOF force and tangent transforms, "
    "coordinate-rotation covariance, atomic checkpoint commit, deterministic "
    "replay, and exact rollback. It is not an updated/follower contact normal, "
    "friction, impact, restitution, coupled contact, general foundation uplift "
    "validation, inelastic contact, shell/3D contact, external acceptance, "
    "production sparse/ROCm/HIP execution, full-building equilibrium, G1 "
    "closure, or commercial-readiness evidence."
)

LOCAL_AXIS_GAP_LINKED_FRAME_NODE_COORDINATES_M = (
    LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M
)
LOCAL_AXIS_GAP_LINKED_FRAME_MEMBER_CONNECTIVITY = (
    LOCAL_AXIS_LINKED_FRAME_MEMBER_CONNECTIVITY
)
LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION = (
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION
)
LOCAL_AXIS_GAP_LINKED_FRAME_LINK_GLOBAL_DOFS = (0, 1, 6, 7)
LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN = 40.0
LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M = 5_000.0
LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M = 0.004
LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS = (
    0.05,
    0.0,
    -0.05,
    -0.1,
    -0.15,
    -0.2,
    -0.3,
    -0.5,
    -0.7,
    -1.0,
    -0.7,
    -0.5,
    -0.3,
    -0.2,
    -0.15,
    -0.1,
    0.0,
    0.2,
    0.0,
    -0.1,
    -0.15,
    -0.25,
    -0.4,
    -0.6,
    -0.8,
    -1.0,
    -0.6,
    -0.3,
    -0.15,
    0.0,
)
LOCAL_AXIS_GAP_LINKED_FRAME_NEWTON_CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=60,
)

_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8
_MAXIMUM_VECTOR_BALANCE_ERROR_KN = 3.0e-8
_MAXIMUM_TRANSFORMATION_ERROR_KN = 1.0e-12
_MAXIMUM_COMPATIBILITY_ERROR_M = 1.0e-12
_LINEARIZED_OPEN_RELATIVE_TOLERANCE = 2.0e-3
_LINEARIZED_CONTACT_RELATIVE_TOLERANCE = 7.0e-3


def make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DLinkProblem
):
    """Reuse the verified inclined elastic carrier with one unilateral gap."""

    base_frame = (
        make_stateful_corotational_local_axis_linked_frame_cyclic_problem().frame_problem
    )
    nx, ny = LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION
    frame_problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="stateful-corotational-local-axis-gap-linked-frame-carrier",
        node_coordinates_m=base_frame.node_coordinates_m,
        members=base_frame.members,
        fixed_global_dofs=base_frame.fixed_global_dofs,
        reference_external_loads=(
            (
                LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS[0],
                LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN * nx,
            ),
            (
                LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS[1],
                LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN * ny,
            ),
        ),
        rotation_coordinate_scale_m=3.0,
    )
    link = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="inclined-anchor-compression-only-gap",
        node_i=LOCAL_AXIS_LINKED_FRAME_ANCHOR_NODE,
        node_j=LOCAL_AXIS_LINKED_FRAME_TOP_NODE,
        component="local_axial",
        material=CompressionOnlyGapLink(
            contact_stiffness_kn_per_m=(
                LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
            ),
            initial_gap_m=LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M,
            material_id="local-axis-gap-linked-frame-contact",
        ),
    )
    return StatefulCorotationalFiberFrame2DLinkProblem(
        case_id="stateful-corotational-local-axis-gap-linked-frame-cyclic",
        frame_problem=frame_problem,
        links=(link,),
    )


def _step_receipts(
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> list[dict[str, Any]]:
    nx, ny = LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION
    direction = np.array((nx, ny), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for index, step in enumerate(path.steps, start=1):
        assembly = step.trial_assembly
        link_row = assembly.link_assemblies[0]
        response = link_row.response
        state = step.accepted_checkpoint.link_states[0]
        load_factor = float(step.metrics["target_load_factor"])
        applied = (
            load_factor * LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN * direction
        )
        top_displacement = assembly.global_displacements[
            list(LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS)
        ]
        anchor_displacement = assembly.global_displacements[[0, 1]]
        fixed_translation_dofs = (
            0,
            1,
            *LOCAL_AXIS_LINKED_FRAME_BASE_TRANSLATION_DOFS,
        )
        reaction = np.array(
            (
                math.fsum(
                    float(assembly.reactions_global[dof])
                    for dof in fixed_translation_dofs
                    if dof % 3 == 0
                ),
                math.fsum(
                    float(assembly.reactions_global[dof])
                    for dof in fixed_translation_dofs
                    if dof % 3 == 1
                ),
            ),
            dtype=np.float64,
        )
        rows.append(
            {
                "step_index": index,
                "load_factor": load_factor,
                "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "nested_frame_checkpoint_hash": (
                    step.accepted_checkpoint.frame_checkpoint.state_hash
                ),
                "top_displacement_m": top_displacement.tolist(),
                "link_deformation_m": link_row.deformation_m,
                "link_signed_clearance_m": response.signed_clearance_m,
                "link_penetration_m": response.penetration_m,
                "link_force_kn": response.force_kn,
                "link_consistent_tangent_kn_per_m": (
                    response.consistent_tangent_kn_per_m
                ),
                "contact_active": response.contact_active,
                "active_set_transition": response.active_set_transition,
                "recoverable_contact_energy_kn_m": response.recoverable_energy_kn_m,
                "maximum_penetration_m": state.maximum_penetration_m,
                "closure_event_count": state.closure_event_count,
                "opening_event_count": state.opening_event_count,
                "link_endpoint_force_sum_error_kn": float(
                    np.linalg.norm(
                        link_row.internal_load_global_kn[:2]
                        + link_row.internal_load_global_kn[2:],
                        ord=np.inf,
                    )
                ),
                "link_force_transformation_error_kn": float(
                    np.linalg.norm(
                        link_row.internal_load_global_kn[2:]
                        - response.force_kn * direction,
                        ord=np.inf,
                    )
                ),
                "link_compatibility_error_m": abs(
                    link_row.deformation_m
                    - float(direction @ (top_displacement - anchor_displacement))
                ),
                "global_vector_balance_error_kn": float(
                    np.linalg.norm(reaction + applied, ord=np.inf)
                ),
                "frame_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(assembly.frame_geometric_tangent_global, ord=np.inf)
                ),
                "link_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(assembly.link_geometric_tangent_global, ord=np.inf)
                ),
                "residual_inf_norm_kn": float(
                    np.linalg.norm(assembly.residual_kn, ord=np.inf)
                ),
                "relative_residual": step.trial_solution.metrics["relative_residual"],
                "iteration_count": step.trial_solution.metrics["iteration_count"],
                "line_search_history_entry_count": len(
                    step.trial_solution.line_search_history
                ),
                "yielded_member_count": step.metrics["yielded_member_count"],
                "damaged_member_count": step.metrics["damaged_member_count"],
                "regularization_used": step.metrics["regularization_used"],
                "fallback_used": step.metrics["fallback_used"],
            }
        )
    return rows


def _fixed_reference_rotation_covariance(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
) -> dict[str, Any]:
    link = problem.links[0]
    coordinates = np.asarray(problem.frame_problem.node_coordinates_m, dtype=np.float64)
    angle = 0.371
    cosine = math.cos(angle)
    sine = math.sin(angle)
    rotation = np.array(((cosine, -sine), (sine, cosine)), dtype=np.float64)
    rotated_coordinates = coordinates @ rotation.T
    active_displacements = np.array((0.012, -0.009, -0.021, 0.017))
    block_rotation = np.block(
        [[rotation, np.zeros((2, 2))], [np.zeros((2, 2)), rotation]]
    )
    rotated_active_displacements = block_rotation @ active_displacements
    global_displacements = np.zeros(problem.global_dof_count, dtype=np.float64)
    rotated_global_displacements = np.zeros_like(global_displacements)
    global_displacements[list(link.global_dofs())] = active_displacements
    rotated_global_displacements[list(link.global_dofs())] = (
        rotated_active_displacements
    )
    reference_kinematic = link.kinematic_vector(coordinates)
    rotated_kinematic = link.kinematic_vector(rotated_coordinates)
    reference_deformation = link.deformation_m(global_displacements, coordinates)
    rotated_deformation = link.deformation_m(
        rotated_global_displacements,
        rotated_coordinates,
    )
    response = link.material.integrate(reference_deformation, link.material.initial_state())
    reference_force = response.force_kn * reference_kinematic
    rotated_force = response.force_kn * rotated_kinematic
    reference_tangent = response.consistent_tangent_kn_per_m * np.outer(
        reference_kinematic,
        reference_kinematic,
    )
    rotated_tangent = response.consistent_tangent_kn_per_m * np.outer(
        rotated_kinematic,
        rotated_kinematic,
    )
    translated = np.array(global_displacements, copy=True)
    common_translation = np.array((0.125, -0.375))
    for node in (link.node_i, link.node_j):
        translated[3 * node : 3 * node + 2] += common_translation
    translated_deformation = link.deformation_m(translated, coordinates)
    deformation_error = abs(rotated_deformation - reference_deformation)
    force_error = float(
        np.linalg.norm(rotated_force - block_rotation @ reference_force, ord=np.inf)
    )
    tangent_error = float(
        np.linalg.norm(
            rotated_tangent
            - block_rotation @ reference_tangent @ block_rotation.T,
            ord=np.inf,
        )
    )
    common_translation_error = abs(translated_deformation - reference_deformation)
    maximum_error = max(
        deformation_error,
        force_error,
        tangent_error,
        common_translation_error,
    )
    return {
        "rotation_rad": angle,
        "reference_deformation_m": reference_deformation,
        "rotated_deformation_m": rotated_deformation,
        "deformation_error_m": deformation_error,
        "force_covariance_error_kn": force_error,
        "tangent_covariance_error_kn_per_m": tangent_error,
        "common_translation_error_m": common_translation_error,
        "maximum_error": maximum_error,
        "tolerance": 1.0e-10,
        "pass": maximum_error <= 1.0e-10,
    }


def build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark() -> (
    dict[str, Any]
):
    """Build a deterministic inclined-normal open-close-open receipt."""

    problem = make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=LOCAL_AXIS_GAP_LINKED_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=LOCAL_AXIS_GAP_LINKED_FRAME_NEWTON_CONFIG,
    )
    if path.status != "ready" or not path.contract_pass:
        raise ValueError("local-axis gap-linked frame path did not commit every target")
    steps = _step_receipts(path)
    active_steps = [
        int(row["step_index"]) for row in steps if bool(row["contact_active"])
    ]
    open_steps = [
        int(row["step_index"]) for row in steps if not bool(row["contact_active"])
    ]
    closure_steps = [
        int(row["step_index"])
        for row in steps
        if row["active_set_transition"] == "closed"
    ]
    opening_steps = [
        int(row["step_index"])
        for row in steps
        if row["active_set_transition"] == "opened"
    ]

    open_step_index = 4
    closed_step_index = 7
    open_step = path.steps[open_step_index - 1]
    closed_step = path.steps[closed_step_index - 1]
    open_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
            problem,
            open_step.parent_checkpoint,
            target_load_factor=LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
                open_step_index - 1
            ],
            trial_free_coordinates_m=open_step.trial_solution.free_displacements_m,
            relative_tolerance=1.0e-6,
        )
    )
    closed_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
            problem,
            closed_step.parent_checkpoint,
            target_load_factor=LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
                closed_step_index - 1
            ],
            trial_free_coordinates_m=closed_step.trial_solution.free_displacements_m,
            relative_tolerance=1.0e-6,
        )
    )
    material = problem.links[0].material
    open_material_tangent = finite_difference_gap_link_tangent_check(
        material,
        open_step.parent_checkpoint.link_states[0],
        deformation_m=float(steps[open_step_index - 1]["link_deformation_m"]),
    )
    closed_material_tangent = finite_difference_gap_link_tangent_check(
        material,
        closed_step.parent_checkpoint.link_states[0],
        deformation_m=float(steps[closed_step_index - 1]["link_deformation_m"]),
    )
    quadratic = _assess_pre_roundoff_quadratic_convergence(
        list(closed_step.trial_solution.convergence_history)
    )

    compliance = LOCAL_AXIS_LINKED_FRAME_DIRECTIONAL_COMPLIANCE_M_PER_KN
    frame_stiffness = 1.0 / compliance
    analytic_onset_load_factor = -LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M / (
        compliance * LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN
    )
    first_active_step = active_steps[0]
    previous_factor = LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
        first_active_step - 2
    ]
    first_active_factor = LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
        first_active_step - 1
    ]
    onset_bracket_pass = bool(
        previous_factor > analytic_onset_load_factor > first_active_factor
    )
    open_load = (
        LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[open_step_index - 1]
        * LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN
    )
    analytic_open_deformation = compliance * open_load
    observed_open_deformation = float(
        steps[open_step_index - 1]["link_deformation_m"]
    )
    open_relative_error = abs(
        observed_open_deformation - analytic_open_deformation
    ) / abs(analytic_open_deformation)
    closed_load = (
        LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[closed_step_index - 1]
        * LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN
    )
    analytic_contact_force = (
        LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
        * (
            closed_load
            + frame_stiffness * LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M
        )
        / (
            frame_stiffness
            + LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
        )
    )
    observed_contact_force = float(steps[closed_step_index - 1]["link_force_kn"])
    contact_relative_error = abs(
        observed_contact_force - analytic_contact_force
    ) / abs(analytic_contact_force)

    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    maximum_balance_error = max(
        float(row["global_vector_balance_error_kn"]) for row in steps
    )
    maximum_transformation_error = max(
        max(
            float(row["link_endpoint_force_sum_error_kn"]),
            float(row["link_force_transformation_error_kn"]),
        )
        for row in steps
    )
    maximum_compatibility_error = max(
        float(row["link_compatibility_error_m"]) for row in steps
    )
    maximum_link_geometric_tangent = max(
        float(row["link_geometric_tangent_inf_norm_kn_per_m"]) for row in steps
    )
    maximum_frame_geometric_tangent = max(
        float(row["frame_geometric_tangent_inf_norm_kn_per_m"]) for row in steps
    )
    carrier_state_evolution_count = sum(
        int(row["yielded_member_count"]) + int(row["damaged_member_count"])
        for row in steps
    )
    fallback_count = sum(bool(row["fallback_used"]) for row in steps)
    regularization_count = sum(bool(row["regularization_used"]) for row in steps)
    line_search_history_entries = sum(
        int(row["line_search_history_entry_count"]) for row in steps
    )
    force_sign_pass = all(
        (
            float(row["link_force_kn"]) < 0.0
            if row["contact_active"]
            else float(row["link_force_kn"]) == 0.0
        )
        for row in steps
    )
    final_state = path.final_checkpoint.link_states[0]
    conservative_return_pass = bool(
        all(float(row["recoverable_contact_energy_kn_m"]) >= 0.0 for row in steps)
        and float(steps[-1]["recoverable_contact_energy_kn_m"]) == 0.0
        and final_state.contact_active is False
    )
    rotation_covariance = _fixed_reference_rotation_covariance(problem)
    deterministic_replay = _replay_exact(path, replay)
    ancestry_exact = _path_ancestry_exact(path)

    rollback_parent = path.steps[9].accepted_checkpoint
    rollback_parent_bytes = rollback_parent.canonical_bytes()
    rollback_parent_link_bytes = rollback_parent.link_states[0].canonical_bytes()
    failed = solve_stateful_corotational_fiber_frame2d_link_load_step(
        problem,
        rollback_parent,
        target_load_factor=0.2,
        config=NewtonRaphsonConfig(max_iterations=0),
    )
    rollback_exact = bool(
        failed.status == "blocked"
        and failed.committed is False
        and failed.accepted_checkpoint is rollback_parent
        and failed.accepted_checkpoint.canonical_bytes() == rollback_parent_bytes
        and failed.accepted_checkpoint.link_states[0].canonical_bytes()
        == rollback_parent_link_bytes
        and rollback_parent.link_states[0].contact_active is True
        and failed.metrics["rollback_exact"] is True
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )

    contract_pass = bool(
        len(path.steps) == len(LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS)
        and ancestry_exact
        and deterministic_replay
        and closure_steps == [6, 22]
        and opening_steps == [15, 29]
        and final_state.closure_event_count == 2
        and final_state.opening_event_count == 2
        and final_state.maximum_penetration_m > 0.0
        and force_sign_pass
        and conservative_return_pass
        and onset_bracket_pass
        and open_relative_error <= _LINEARIZED_OPEN_RELATIVE_TOLERANCE
        and contact_relative_error <= _LINEARIZED_CONTACT_RELATIVE_TOLERANCE
        and open_tangent["pass"] is True
        and closed_tangent["pass"] is True
        and open_tangent["link_material_tangent_inf_norm_kn_per_m"] == 0.0
        and closed_tangent["link_material_tangent_inf_norm_kn_per_m"] > 0.0
        and open_material_tangent["pass"] is True
        and closed_material_tangent["pass"] is True
        and quadratic["pass"] is True
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and maximum_balance_error <= _MAXIMUM_VECTOR_BALANCE_ERROR_KN
        and maximum_transformation_error <= _MAXIMUM_TRANSFORMATION_ERROR_KN
        and maximum_compatibility_error <= _MAXIMUM_COMPATIBILITY_ERROR_M
        and maximum_link_geometric_tangent == 0.0
        and maximum_frame_geometric_tangent > 0.0
        and carrier_state_evolution_count == 0
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rotation_covariance["pass"] is True
        and rollback_exact
    )
    link_payload = problem.links[0].contract_payload(
        problem.frame_problem.node_coordinates_m
    )
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
        ),
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": "internal_analytic_fixed_normal_piecewise_linear_gap_frame",
        "formulation": (
            STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_FORMULATION
        ),
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in LOCAL_AXIS_GAP_LINKED_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [
                list(row) for row in LOCAL_AXIS_GAP_LINKED_FRAME_MEMBER_CONNECTIVITY
            ],
            "fixed_global_dofs": list(problem.fixed_global_dofs),
            "link_end_nodes": [
                LOCAL_AXIS_LINKED_FRAME_ANCHOR_NODE,
                LOCAL_AXIS_LINKED_FRAME_TOP_NODE,
            ],
            "link_component": "local_axial",
            "contact_normal": "fixed_reference_local_axis_node_i_to_node_j",
            "reference_direction_cosines": list(
                LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION
            ),
            "link_global_dofs": list(LOCAL_AXIS_GAP_LINKED_FRAME_LINK_GLOBAL_DOFS),
            "reference_load_kn": LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN,
        },
        "elastic_carrier_frame": {
            "column_axial_rigidity_kn": (
                LOCAL_AXIS_LINKED_FRAME_COLUMN_AXIAL_RIGIDITY_KN
            ),
            "column_flexural_rigidity_kn_m2": (
                LOCAL_AXIS_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
            ),
            "directional_compliance_m_per_kn": compliance,
            "member_state_evolution_count": carrier_state_evolution_count,
        },
        "gap_link": {
            **link_payload["material"],
            "active_set_algorithm": GAP_LINK_ACTIVE_SET_ALGORITHM,
            "closure_convention": GAP_LINK_CLOSURE_CONVENTION,
            "tangent_definition": GAP_LINK_TANGENT_DEFINITION,
            "force_sign_convention": "compression_negative",
            "dissipation_model": "none_elastic_recoverable_only",
            "axis_update": link_payload["axis_update"],
            "geometric_tangent": link_payload["geometric_tangent"],
        },
        "cyclic_load_factors": list(LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "committed_step_count": sum(step.committed for step in path.steps),
        "path_ancestry_exact": ancestry_exact,
        "deterministic_replay_exact": deterministic_replay,
        "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
        "final_checkpoint_hash": path.final_checkpoint.state_hash,
        "active_step_indices": active_steps,
        "open_step_indices": open_steps,
        "closure_transition_step_indices": closure_steps,
        "opening_transition_step_indices": opening_steps,
        "final_closure_event_count": final_state.closure_event_count,
        "final_opening_event_count": final_state.opening_event_count,
        "maximum_penetration_m": final_state.maximum_penetration_m,
        "force_sign_pass": force_sign_pass,
        "conservative_return_to_open_pass": conservative_return_pass,
        "analytic_contact_onset": {
            "analytic_load_factor": analytic_onset_load_factor,
            "previous_open_load_factor": previous_factor,
            "first_active_load_factor": first_active_factor,
            "bracket_pass": onset_bracket_pass,
        },
        "analytic_open_branch": {
            "reference_class": "small_displacement_linearized_carrier",
            "step_index": open_step_index,
            "analytic_deformation_m": analytic_open_deformation,
            "observed_deformation_m": observed_open_deformation,
            "relative_error": open_relative_error,
            "relative_tolerance": _LINEARIZED_OPEN_RELATIVE_TOLERANCE,
            "pass": open_relative_error <= _LINEARIZED_OPEN_RELATIVE_TOLERANCE,
        },
        "analytic_contact_branch": {
            "reference_class": "small_displacement_linearized_carrier_plus_gap",
            "step_index": closed_step_index,
            "analytic_contact_force_kn": analytic_contact_force,
            "observed_contact_force_kn": observed_contact_force,
            "relative_error": contact_relative_error,
            "relative_tolerance": _LINEARIZED_CONTACT_RELATIVE_TOLERANCE,
            "pass": (
                contact_relative_error <= _LINEARIZED_CONTACT_RELATIVE_TOLERANCE
            ),
        },
        "same_parent_open_frame_gap_tangent": open_tangent,
        "same_parent_closed_frame_gap_tangent": closed_tangent,
        "same_parent_open_material_tangent": open_material_tangent,
        "same_parent_closed_material_tangent": closed_material_tangent,
        "closed_active_set_newton_quadratic_convergence": quadratic,
        "fixed_reference_rotation_covariance": rotation_covariance,
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_vector_balance_error_kn": maximum_balance_error,
        "maximum_force_transformation_error_kn": maximum_transformation_error,
        "maximum_link_compatibility_error_m": maximum_compatibility_error,
        "maximum_frame_geometric_tangent_inf_norm_kn_per_m": (
            maximum_frame_geometric_tangent
        ),
        "maximum_link_geometric_tangent_inf_norm_kn_per_m": (
            maximum_link_geometric_tangent
        ),
        "line_search_history_entry_count": line_search_history_entries,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "parent_link_state_hash": rollback_parent.link_states[0].state_hash,
            "parent_contact_active": rollback_parent.link_states[0].contact_active,
            "target_load_factor": 0.2,
            "status": failed.status,
            "terminal_reason": failed.metrics["terminal_reason"],
            "accepted_checkpoint_hash_after": failed.accepted_checkpoint.state_hash,
            "accepted_link_state_hash_after": (
                failed.accepted_checkpoint.link_states[0].state_hash
            ),
            "exact": rollback_exact,
        },
        "steps": steps,
        "claims": {
            "bounded_inclined_corotational_fiber_frame": True,
            "scalar_fixed_reference_local_axis_compression_only_gap": True,
            "four_dof_direction_cosine_force_and_tangent_scatter": True,
            "coordinate_rotation_covariance": True,
            "frictionless_continuous_unilateral_response": True,
            "open_closed_active_set_checkpoint_history": True,
            "same_parent_open_and_closed_consistent_tangents": True,
            "atomic_frame_and_gap_checkpoint_commit": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "analytic_open_contact_onset_and_closed_branch": True,
            "updated_or_follower_contact_normal": False,
            "friction_impact_or_coupled_contact": False,
            "general_foundation_uplift_validation": False,
            "inelastic_contact_or_member_interaction": False,
            "shell_or_three_dimensional_contact": False,
            "external_contact_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "updated_and_follower_contact_normals_not_implemented",
            "friction_impact_restitution_and_coupled_contact_not_implemented",
            "general_foundation_uplift_not_validated",
            "inelastic_contact_and_member_interaction_not_validated",
            "shell_and_three_dimensional_contact_not_implemented",
            "external_contact_reference_not_attached",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_contact_material_newton_breadth_not_closed",
        ],
        "coupling_claim_boundary": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY
        ),
        "benchmark_claim_boundary": (
            STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY
        ),
    }


__all__ = [
    "LOCAL_AXIS_GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M",
    "LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS",
    "LOCAL_AXIS_GAP_LINKED_FRAME_INITIAL_GAP_M",
    "LOCAL_AXIS_GAP_LINKED_FRAME_LINK_GLOBAL_DOFS",
    "LOCAL_AXIS_GAP_LINKED_FRAME_MEMBER_CONNECTIVITY",
    "LOCAL_AXIS_GAP_LINKED_FRAME_NEWTON_CONFIG",
    "LOCAL_AXIS_GAP_LINKED_FRAME_NODE_COORDINATES_M",
    "LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_DIRECTION",
    "LOCAL_AXIS_GAP_LINKED_FRAME_REFERENCE_LOAD_KN",
    "STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_LOCAL_AXIS_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark",
    "make_stateful_corotational_local_axis_gap_linked_frame_cyclic_problem",
]
