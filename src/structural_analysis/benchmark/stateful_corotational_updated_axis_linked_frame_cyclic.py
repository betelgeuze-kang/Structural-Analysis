"""Updated-current-axis bilinear-link benchmark on a 2D fiber frame."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d_link import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY,
    StatefulCorotationalFiberFrame2DLinkLoadPathResult,
    StatefulCorotationalFiberFrame2DLinkProblem,
    finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check,
    run_stateful_corotational_fiber_frame2d_link_load_path,
    solve_stateful_corotational_fiber_frame2d_link_load_step,
)
from structural_analysis.benchmark.stateful_corotational_local_axis_linked_frame_cyclic import (
    LOCAL_AXIS_LINKED_FRAME_ANCHOR_NODE,
    LOCAL_AXIS_LINKED_FRAME_ANCHOR_TRANSLATION_DOFS,
    LOCAL_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    LOCAL_AXIS_LINKED_FRAME_DIRECTIONAL_COMPLIANCE_M_PER_KN,
    LOCAL_AXIS_LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION,
    LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS,
    LOCAL_AXIS_LINKED_FRAME_MEMBER_CONNECTIVITY,
    LOCAL_AXIS_LINKED_FRAME_NEWTON_CONFIG,
    LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M,
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION,
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN,
    LOCAL_AXIS_LINKED_FRAME_TOP_NODE,
    LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS,
    make_stateful_corotational_local_axis_linked_frame_cyclic_problem,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_FORMULATION = (
    "one_corotational_fiber_cantilever_braced_to_a_fixed_anchor_by_one_"
    "current_chord_updated_axial_state_updated_bilinear_link"
)
STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded planar elastic-carrier cantilever "
    "connected to a fixed anchor by a scalar bilinear link whose deformation is "
    "current length minus reference length and whose internal force direction "
    "and geometric tangent follow the current chord. It is not a general "
    "nonconservative follower-load formulation and does not provide rotational "
    "or coupled multi-axis response, gap/contact, friction, uplift, damping, rate "
    "effects, degradation or pinching, inelastic frame-member/link interaction, "
    "shells, three-dimensional frames, external device acceptance, production "
    "sparse/ROCm/HIP execution, full-building equilibrium, G1 closure, or "
    "commercial-readiness evidence."
)

UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS = (
    LOCAL_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS
)
UPDATED_AXIS_LINKED_FRAME_NODE_COORDINATES_M = (
    LOCAL_AXIS_LINKED_FRAME_NODE_COORDINATES_M
)
UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS = LOCAL_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS
UPDATED_AXIS_LINKED_FRAME_REFERENCE_DIRECTION = (
    LOCAL_AXIS_LINKED_FRAME_REFERENCE_DIRECTION
)
UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN = LOCAL_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN
UPDATED_AXIS_LINKED_FRAME_NEWTON_CONFIG = LOCAL_AXIS_LINKED_FRAME_NEWTON_CONFIG

_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8
_MAXIMUM_VECTOR_BALANCE_ERROR_KN = 3.0e-8
_MAXIMUM_FORCE_TRANSFORMATION_ERROR_KN = 1.0e-12
_MAXIMUM_COMPATIBILITY_ERROR_M = 1.0e-12
_MINIMUM_CURRENT_AXIS_ROTATION_RAD = 1.0e-4
_MINIMUM_UPDATED_FIXED_FORCE_DIFFERENCE_KN = 1.0e-4


def make_stateful_corotational_updated_axis_linked_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DLinkProblem
):
    """Reuse the paired elastic carrier with a current-chord axial link."""

    fixed_reference = (
        make_stateful_corotational_local_axis_linked_frame_cyclic_problem()
    )
    frame = replace(
        fixed_reference.frame_problem,
        case_id="stateful-corotational-updated-axis-linked-frame-carrier",
    )
    fixed_link = fixed_reference.links[0]
    link = replace(
        fixed_link,
        link_id="updated-current-chord-anchor-link",
        component="updated_axial",
        material=replace(
            fixed_link.material,
            material_id="updated-current-chord-anchor-bilinear-link",
        ),
    )
    return StatefulCorotationalFiberFrame2DLinkProblem(
        case_id="stateful-corotational-updated-axis-linked-frame-cyclic",
        frame_problem=frame,
        links=(link,),
    )


def _path_ancestry_exact(
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> bool:
    parent = path.initial_checkpoint
    for step in path.steps:
        accepted = step.accepted_checkpoint
        if (
            step.parent_checkpoint.state_hash != parent.state_hash
            or step.trial_assembly.parent_checkpoint_hash != parent.state_hash
            or accepted.parent_state_hash != parent.state_hash
            or accepted.epoch != parent.epoch + 1
            or accepted.frame_checkpoint.parent_state_hash
            != parent.frame_checkpoint.state_hash
            or not step.metrics["frame_and_link_parent_binding_passed"]
            or not step.metrics["parent_checkpoint_immutable"]
        ):
            return False
        parent = accepted
    return parent.state_hash == path.final_checkpoint.state_hash


def _exact_array_bytes(values: Any) -> bytes:
    return np.ascontiguousarray(values, dtype="<f8").tobytes(order="C")


def _replay_exact(
    left: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
    right: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> bool:
    if len(left.steps) != len(right.steps):
        return False
    left_checkpoints = (
        left.initial_checkpoint,
        *(step.accepted_checkpoint for step in left.steps),
    )
    right_checkpoints = (
        right.initial_checkpoint,
        *(step.accepted_checkpoint for step in right.steps),
    )
    return bool(
        all(
            a.canonical_bytes() == b.canonical_bytes() and a.state_hash == b.state_hash
            for a, b in zip(left_checkpoints, right_checkpoints, strict=True)
        )
        and all(
            _exact_array_bytes(a.trial_assembly.residual_kn)
            == _exact_array_bytes(b.trial_assembly.residual_kn)
            and _exact_array_bytes(a.trial_assembly.jacobian_kn_per_m)
            == _exact_array_bytes(b.trial_assembly.jacobian_kn_per_m)
            for a, b in zip(left.steps, right.steps, strict=True)
        )
    )


def _assess_pre_roundoff_quadratic_convergence(
    convergence_history: list[dict[str, Any]],
    *,
    relative_residual_floor: float = 1.0e-7,
) -> dict[str, Any]:
    retained: list[dict[str, Any]] = []
    for row in convergence_history:
        retained.append(row)
        if (
            row.get("accepted") is True
            and float(row.get("line_search_alpha", math.nan)) == 1.0
            and float(row.get("relative_residual", math.inf)) <= relative_residual_floor
        ):
            break
    result = assess_quadratic_convergence(
        retained,
        minimum_observed_order=1.8,
        minimum_order_sample_count=1,
    )
    return {
        **result,
        "relative_residual_roundoff_floor": relative_residual_floor,
        "input_history_count": len(convergence_history),
        "retained_history_count": len(retained),
        "excluded_terminal_roundoff_history_count": (
            len(convergence_history) - len(retained)
        ),
    }


def _kinematic_objectivity_receipt(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
) -> dict[str, Any]:
    link = problem.links[0]
    coordinates = np.asarray(problem.frame_problem.node_coordinates_m, dtype=np.float64)
    angle = 0.37
    rotation = np.array(
        ((math.cos(angle), -math.sin(angle)), (math.sin(angle), math.cos(angle))),
        dtype=np.float64,
    )
    translation = np.array((0.83, -0.41), dtype=np.float64)
    current = coordinates @ rotation.T + translation
    rigid_displacements = np.zeros(problem.global_dof_count, dtype=np.float64)
    for node_index in range(coordinates.shape[0]):
        rigid_displacements[3 * node_index : 3 * node_index + 2] = (
            current[node_index] - coordinates[node_index]
        )
    reference_direction = np.asarray(
        link.reference_direction_cosines(coordinates),
        dtype=np.float64,
    )
    current_length, nx, ny = link.current_length_and_direction(
        coordinates,
        rigid_displacements,
    )
    current_direction = np.array((nx, ny), dtype=np.float64)
    expected_direction = rotation @ reference_direction
    deformation = link.deformation_m(rigid_displacements, coordinates)

    stretch = 1.08
    stretched_displacements = rigid_displacements.copy()
    node_i = link.node_i
    node_j = link.node_j
    reference_delta = coordinates[node_j] - coordinates[node_i]
    stretched_current_delta = stretch * (rotation @ reference_delta)
    anchor_current = current[node_i]
    top_current = anchor_current + stretched_current_delta
    stretched_displacements[3 * node_j : 3 * node_j + 2] = (
        top_current - coordinates[node_j]
    )
    analytic_hessian = link.deformation_hessian_per_m(
        coordinates,
        stretched_displacements,
    )
    epsilon = 1.0e-7
    finite_difference_hessian = np.empty_like(analytic_hessian)
    dofs = link.global_dofs()
    for column, dof in enumerate(dofs):
        perturbation = np.zeros(problem.global_dof_count, dtype=np.float64)
        perturbation[dof] = epsilon
        forward = link.kinematic_vector(
            coordinates,
            stretched_displacements + perturbation,
        )
        backward = link.kinematic_vector(
            coordinates,
            stretched_displacements - perturbation,
        )
        finite_difference_hessian[:, column] = (forward - backward) / (2.0 * epsilon)
    hessian_error = float(
        np.linalg.norm(analytic_hessian - finite_difference_hessian, ord=np.inf)
    )
    hessian_scale = max(
        float(np.linalg.norm(analytic_hessian, ord=np.inf)),
        float(np.linalg.norm(finite_difference_hessian, ord=np.inf)),
        1.0,
    )
    reference_length = link.reference_length_m(coordinates)
    stretched_deformation = link.deformation_m(
        stretched_displacements,
        coordinates,
    )
    rigid_deformation_error = abs(deformation)
    direction_rotation_error = float(
        np.linalg.norm(current_direction - expected_direction, ord=np.inf)
    )
    stretch_deformation_error = abs(
        stretched_deformation - (stretch - 1.0) * reference_length
    )
    relative_hessian_error = hessian_error / hessian_scale
    return {
        "rigid_rotation_rad": angle,
        "rigid_translation_m": translation.tolist(),
        "reference_length_m": reference_length,
        "rigid_current_length_m": current_length,
        "rigid_deformation_error_m": rigid_deformation_error,
        "rotated_direction_error": direction_rotation_error,
        "stretch_ratio": stretch,
        "stretch_deformation_error_m": stretch_deformation_error,
        "hessian_finite_difference_epsilon_m": epsilon,
        "hessian_absolute_inf_error_per_m": hessian_error,
        "hessian_relative_inf_error": relative_hessian_error,
        "pass": bool(
            rigid_deformation_error <= 1.0e-12
            and direction_rotation_error <= 1.0e-12
            and stretch_deformation_error <= 1.0e-12
            and relative_hessian_error <= 1.0e-8
        ),
    }


def _step_receipts(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> list[dict[str, Any]]:
    link = problem.links[0]
    coordinates = problem.frame_problem.node_coordinates_m
    reference_direction = np.asarray(
        link.reference_direction_cosines(coordinates),
        dtype=np.float64,
    )
    reference_angle = math.atan2(reference_direction[1], reference_direction[0])
    reference_length = link.reference_length_m(coordinates)
    rows: list[dict[str, Any]] = []
    previous_plastic_deformation = 0.0
    for index, step in enumerate(path.steps, start=1):
        assembly = step.trial_assembly
        link_row = assembly.link_assemblies[0]
        state = step.accepted_checkpoint.link_states[0]
        plastic_increment = state.plastic_deformation_m - previous_plastic_deformation
        flow_direction = (
            1 if plastic_increment > 0.0 else -1 if plastic_increment < 0.0 else 0
        )
        load_factor = float(step.metrics["target_load_factor"])
        applied = (
            load_factor
            * UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN
            * reference_direction
        )
        current_length, nx, ny = link.current_length_and_direction(
            coordinates,
            assembly.global_displacements,
        )
        current_direction = np.array((nx, ny), dtype=np.float64)
        current_transverse = np.array((-ny, nx), dtype=np.float64)
        anchor_force = link_row.internal_load_global_kn[:2]
        top_link_force = link_row.internal_load_global_kn[2:]
        fixed_reaction = np.array(
            (
                assembly.reactions_global[0] + assembly.reactions_global[3],
                assembly.reactions_global[1] + assembly.reactions_global[4],
            ),
            dtype=np.float64,
        )
        frame_top_force = assembly.frame_assembly.internal_loads_global[
            list(LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS)
        ]
        relative_translation = (
            assembly.global_displacements[
                list(LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS)
            ]
            - assembly.global_displacements[
                list(LOCAL_AXIS_LINKED_FRAME_ANCHOR_TRANSLATION_DOFS)
            ]
        )
        current_axis_rotation = math.atan2(ny, nx) - reference_angle
        rows.append(
            {
                "step_index": index,
                "load_factor": load_factor,
                "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "nested_frame_checkpoint_hash": (
                    step.accepted_checkpoint.frame_checkpoint.state_hash
                ),
                "top_displacement_global_m": assembly.global_displacements[
                    list(LOCAL_AXIS_LINKED_FRAME_TOP_TRANSLATION_DOFS)
                ].tolist(),
                "current_link_length_m": current_length,
                "current_direction_cosines": current_direction.tolist(),
                "current_axis_rotation_rad": current_axis_rotation,
                "link_deformation_m": link_row.deformation_m,
                "fixed_reference_projection_m": float(
                    reference_direction @ relative_translation
                ),
                "updated_minus_fixed_projection_m": (
                    link_row.deformation_m
                    - float(reference_direction @ relative_translation)
                ),
                "link_force_kn": link_row.response.force_kn,
                "link_consistent_tangent_kn_per_m": (
                    link_row.response.consistent_tangent_kn_per_m
                ),
                "link_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(
                        link_row.geometric_tangent_global_kn_per_m,
                        ord=np.inf,
                    )
                ),
                "link_yielded": link_row.response.yielded,
                "link_plastic_flow_direction": flow_direction,
                "link_accumulated_plastic_deformation_m": (
                    state.accumulated_plastic_deformation_m
                ),
                "link_dissipated_energy_kn_m": state.dissipated_energy_kn_m,
                "link_endpoint_vector_balance_error_kn": float(
                    np.linalg.norm(anchor_force + top_link_force, ord=np.inf)
                ),
                "link_force_projection_error_kn": abs(
                    float(current_direction @ top_link_force)
                    - link_row.response.force_kn
                ),
                "link_transverse_force_leakage_kn": abs(
                    float(current_transverse @ top_link_force)
                ),
                "link_compatibility_error_m": abs(
                    link_row.deformation_m - (current_length - reference_length)
                ),
                "top_node_vector_equilibrium_error_kn": float(
                    np.linalg.norm(
                        frame_top_force + top_link_force - applied,
                        ord=np.inf,
                    )
                ),
                "global_vector_balance_error_kn": float(
                    np.linalg.norm(fixed_reaction + applied, ord=np.inf)
                ),
                "frame_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(
                        assembly.frame_geometric_tangent_global,
                        ord=np.inf,
                    )
                ),
                "residual_inf_norm_kn": float(
                    np.linalg.norm(assembly.residual_kn, ord=np.inf)
                ),
                "relative_residual": step.trial_solution.metrics["relative_residual"],
                "iteration_count": step.trial_solution.metrics["iteration_count"],
                "line_search_used": step.trial_solution.metrics["line_search_used"],
                "line_search_history_entry_count": len(
                    step.trial_solution.line_search_history
                ),
                "yielded_member_count": step.metrics["yielded_member_count"],
                "damaged_member_count": step.metrics["damaged_member_count"],
                "regularization_used": step.metrics["regularization_used"],
                "fallback_used": step.metrics["fallback_used"],
            }
        )
        previous_plastic_deformation = state.plastic_deformation_m
    return rows


def build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark() -> dict[
    str, Any
]:
    """Build the deterministic updated-current-axis cyclic receipt."""

    problem = make_stateful_corotational_updated_axis_linked_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=UPDATED_AXIS_LINKED_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=UPDATED_AXIS_LINKED_FRAME_NEWTON_CONFIG,
    )
    fixed_problem = make_stateful_corotational_local_axis_linked_frame_cyclic_problem()
    fixed_path = run_stateful_corotational_fiber_frame2d_link_load_path(
        fixed_problem,
        UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=UPDATED_AXIS_LINKED_FRAME_NEWTON_CONFIG,
    )
    steps = _step_receipts(problem, path)
    yielded_steps = [
        int(row["step_index"]) for row in steps if bool(row["link_yielded"])
    ]
    reverse_yielded_steps = [
        index
        for index in yielded_steps
        if UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS[index - 1] < 0.0
    ]
    if not yielded_steps or not reverse_yielded_steps:
        raise ValueError("updated-axis benchmark did not exercise both link branches")
    tangent_step_index = next(
        index
        for index in yielded_steps
        if path.steps[index - 1]
        .parent_checkpoint.link_states[0]
        .accumulated_plastic_deformation_m
        > 0.0
    )
    tangent_step = path.steps[tangent_step_index - 1]
    tangent = finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
        problem,
        tangent_step.parent_checkpoint,
        target_load_factor=(
            UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS[tangent_step_index - 1]
        ),
        trial_free_coordinates_m=tangent_step.trial_solution.free_displacements_m,
    )
    reverse_tangent_step_index = next(
        index
        for index in reverse_yielded_steps
        if path.steps[index - 1]
        .parent_checkpoint.link_states[0]
        .accumulated_plastic_deformation_m
        > 0.0
    )
    reverse_tangent_step = path.steps[reverse_tangent_step_index - 1]
    reverse_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
            problem,
            reverse_tangent_step.parent_checkpoint,
            target_load_factor=(
                UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
                    reverse_tangent_step_index - 1
                ]
            ),
            trial_free_coordinates_m=(
                reverse_tangent_step.trial_solution.free_displacements_m
            ),
        )
    )
    quadratic = _assess_pre_roundoff_quadratic_convergence(
        list(tangent_step.trial_solution.convergence_history)
    )
    energy_history = [
        0.0,
        *(float(row["link_dissipated_energy_kn_m"]) for row in steps),
    ]
    dissipation_monotonic = all(
        following + 1.0e-15 >= previous
        for previous, following in zip(energy_history, energy_history[1:])
    )
    nonzero_flow_directions = [
        int(row["link_plastic_flow_direction"])
        for row in steps
        if int(row["link_plastic_flow_direction"]) != 0
    ]
    flow_reversal_count = sum(
        current != previous
        for previous, current in zip(
            nonzero_flow_directions,
            nonzero_flow_directions[1:],
        )
    )
    elastic_step = steps[0]
    elastic_applied_load = (
        UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS[0]
        * UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN
    )
    analytic_elastic_link_force = (
        elastic_applied_load * LOCAL_AXIS_LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION
    )
    elastic_link_force_relative_error = abs(
        float(elastic_step["link_force_kn"]) - analytic_elastic_link_force
    ) / abs(analytic_elastic_link_force)
    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    maximum_vector_balance_error = max(
        max(
            float(row["link_endpoint_vector_balance_error_kn"]),
            float(row["top_node_vector_equilibrium_error_kn"]),
            float(row["global_vector_balance_error_kn"]),
        )
        for row in steps
    )
    maximum_force_transformation_error = max(
        max(
            float(row["link_force_projection_error_kn"]),
            float(row["link_transverse_force_leakage_kn"]),
        )
        for row in steps
    )
    maximum_compatibility_error = max(
        float(row["link_compatibility_error_m"]) for row in steps
    )
    maximum_axis_rotation = max(
        abs(float(row["current_axis_rotation_rad"])) for row in steps
    )
    maximum_projection_difference = max(
        abs(float(row["updated_minus_fixed_projection_m"])) for row in steps
    )
    maximum_link_geometric_tangent = max(
        float(row["link_geometric_tangent_inf_norm_kn_per_m"]) for row in steps
    )
    fixed_force_history = [
        float(step.trial_assembly.link_assemblies[0].response.force_kn)
        for step in fixed_path.steps
    ]
    updated_fixed_force_differences = [
        abs(float(row["link_force_kn"]) - fixed_force)
        for row, fixed_force in zip(steps, fixed_force_history, strict=True)
    ]
    maximum_updated_fixed_force_difference = max(updated_fixed_force_differences)
    fallback_count = sum(bool(row["fallback_used"]) for row in steps)
    regularization_count = sum(bool(row["regularization_used"]) for row in steps)
    line_search_history_entries = sum(
        int(row["line_search_history_entry_count"]) for row in steps
    )
    carrier_member_state_evolution_count = sum(
        int(row["yielded_member_count"]) + int(row["damaged_member_count"])
        for row in steps
    )
    deterministic_replay = _replay_exact(path, replay)
    ancestry_exact = _path_ancestry_exact(path)
    objectivity = _kinematic_objectivity_receipt(problem)

    rollback_parent = path.steps[yielded_steps[0] - 1].accepted_checkpoint
    rollback_parent_bytes = rollback_parent.canonical_bytes()
    rollback_parent_link_bytes = rollback_parent.link_states[0].canonical_bytes()
    failed = solve_stateful_corotational_fiber_frame2d_link_load_step(
        problem,
        rollback_parent,
        target_load_factor=-1.0,
        config=NewtonRaphsonConfig(max_iterations=0),
    )
    rollback_exact = bool(
        failed.status == "blocked"
        and failed.committed is False
        and failed.accepted_checkpoint is rollback_parent
        and failed.accepted_checkpoint.canonical_bytes() == rollback_parent_bytes
        and failed.accepted_checkpoint.link_states[0].canonical_bytes()
        == rollback_parent_link_bytes
        and failed.metrics["rollback_exact"] is True
        and rollback_parent.link_states[0].accumulated_plastic_deformation_m > 0.0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )
    link = problem.links[0]
    coordinates = problem.frame_problem.node_coordinates_m
    zero_displacements = np.zeros(problem.global_dof_count, dtype=np.float64)
    reference_direction = link.reference_direction_cosines(coordinates)
    initial_kinematic = link.kinematic_vector(coordinates, zero_displacements)
    initial_link_tangent = link.material.initial_stiffness_kn_per_m * np.outer(
        initial_kinematic,
        initial_kinematic,
    )
    contract_pass = bool(
        path.status == "ready"
        and fixed_path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS)
        and ancestry_exact
        and deterministic_replay
        and yielded_steps
        and reverse_yielded_steps
        and flow_reversal_count >= 1
        and dissipation_monotonic
        and energy_history[-1] > 0.0
        and tangent["pass"] is True
        and tangent["yielded_link_count"] > 0
        and tangent["link_geometric_tangent_inf_norm_kn_per_m"] > 0.0
        and tangent["all_tangent_terms_active"] is True
        and reverse_tangent["pass"] is True
        and reverse_tangent["yielded_link_count"] > 0
        and reverse_tangent["link_geometric_tangent_inf_norm_kn_per_m"] > 0.0
        and quadratic["pass"] is True
        and objectivity["pass"] is True
        and elastic_link_force_relative_error <= 1.0e-4
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and maximum_vector_balance_error <= _MAXIMUM_VECTOR_BALANCE_ERROR_KN
        and maximum_force_transformation_error <= _MAXIMUM_FORCE_TRANSFORMATION_ERROR_KN
        and maximum_compatibility_error <= _MAXIMUM_COMPATIBILITY_ERROR_M
        and maximum_axis_rotation >= _MINIMUM_CURRENT_AXIS_ROTATION_RAD
        and maximum_projection_difference > 0.0
        and maximum_link_geometric_tangent > 0.0
        and maximum_updated_fixed_force_difference
        >= _MINIMUM_UPDATED_FIXED_FORCE_DIFFERENCE_KN
        and carrier_member_state_evolution_count == 0
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rollback_exact
    )
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
        ),
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": (
            "internal_objectivity_and_algorithmic_cyclic_updated_current_axis_link"
        ),
        "formulation": (
            STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_FORMULATION
        ),
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in UPDATED_AXIS_LINKED_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [
                list(row) for row in LOCAL_AXIS_LINKED_FRAME_MEMBER_CONNECTIVITY
            ],
            "fixed_global_dofs": [0, 1, 2, 3, 4, 5],
            "link_end_nodes": [
                LOCAL_AXIS_LINKED_FRAME_ANCHOR_NODE,
                LOCAL_AXIS_LINKED_FRAME_TOP_NODE,
            ],
            "link_component": "updated_axial",
            "link_global_dofs": list(UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS),
            "reference_length_m": link.reference_length_m(coordinates),
            "reference_direction_cosines": list(reference_direction),
            "initial_link_kinematic_vector": initial_kinematic.tolist(),
            "top_reference_load_global_kn": [
                UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN * reference_direction[0],
                UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN * reference_direction[1],
            ],
        },
        "link": {
            **link.contract_payload(coordinates)["material"],
            "plastic_consistent_tangent_kn_per_m": (
                link.material.plastic_consistent_tangent_kn_per_m
            ),
            "initial_global_tangent_kn_per_m": initial_link_tangent.tolist(),
        },
        "cyclic_load_factors": list(UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "committed_step_count": sum(step.committed for step in path.steps),
        "path_ancestry_exact": ancestry_exact,
        "deterministic_replay_exact": deterministic_replay,
        "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
        "final_checkpoint_hash": path.final_checkpoint.state_hash,
        "yielded_step_indices": yielded_steps,
        "reverse_loading_yielded_step_indices": reverse_yielded_steps,
        "plastic_flow_reversal_count": flow_reversal_count,
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "final_link_dissipated_energy_kn_m": energy_history[-1],
        "elastic_reference": {
            "load_factor": UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS[0],
            "directional_frame_compliance_m_per_kn": (
                LOCAL_AXIS_LINKED_FRAME_DIRECTIONAL_COMPLIANCE_M_PER_KN
            ),
            "link_transfer_fraction": (
                LOCAL_AXIS_LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION
            ),
            "analytic_first_order_link_force_kn": analytic_elastic_link_force,
            "observed_link_force_kn": elastic_step["link_force_kn"],
            "relative_error": elastic_link_force_relative_error,
            "relative_tolerance": 1.0e-4,
            "pass": elastic_link_force_relative_error <= 1.0e-4,
        },
        "rigid_body_and_length_hessian_objectivity": objectivity,
        "same_parent_frame_link_tangent": tangent,
        "same_parent_reverse_frame_link_tangent": reverse_tangent,
        "yielded_link_newton_quadratic_convergence": quadratic,
        "maximum_current_axis_rotation_rad": maximum_axis_rotation,
        "minimum_current_axis_rotation_contract_rad": (
            _MINIMUM_CURRENT_AXIS_ROTATION_RAD
        ),
        "maximum_updated_minus_fixed_projection_m": maximum_projection_difference,
        "maximum_link_geometric_tangent_inf_norm_kn_per_m": (
            maximum_link_geometric_tangent
        ),
        "paired_fixed_reference_path_status": fixed_path.status,
        "maximum_updated_fixed_link_force_difference_kn": (
            maximum_updated_fixed_force_difference
        ),
        "minimum_updated_fixed_link_force_difference_contract_kn": (
            _MINIMUM_UPDATED_FIXED_FORCE_DIFFERENCE_KN
        ),
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_residual_inf_norm_tolerance_kn": _MAXIMUM_RESIDUAL_INF_NORM_KN,
        "maximum_vector_balance_error_kn": maximum_vector_balance_error,
        "maximum_vector_balance_error_tolerance_kn": (_MAXIMUM_VECTOR_BALANCE_ERROR_KN),
        "maximum_force_transformation_error_kn": maximum_force_transformation_error,
        "maximum_force_transformation_error_tolerance_kn": (
            _MAXIMUM_FORCE_TRANSFORMATION_ERROR_KN
        ),
        "maximum_link_compatibility_error_m": maximum_compatibility_error,
        "maximum_link_compatibility_error_tolerance_m": (
            _MAXIMUM_COMPATIBILITY_ERROR_M
        ),
        "line_search_history_entry_count": line_search_history_entries,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "elastic_carrier_member_state_evolution_count": (
            carrier_member_state_evolution_count
        ),
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "parent_link_state_hash": rollback_parent.link_states[0].state_hash,
            "target_load_factor": -1.0,
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
            "bounded_corotational_fiber_cantilever": True,
            "updated_current_axis_internal_translational_link": True,
            "current_length_force_and_consistent_geometric_tangent": True,
            "rigid_body_objective_link_kinematics": True,
            "cyclic_link_yield_reversal_and_nonnegative_dissipation": True,
            "atomic_frame_and_link_checkpoint_commit": True,
            "same_parent_frame_material_and_link_geometric_tangent": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "general_nonconservative_follower_external_load": False,
            "rotational_or_coupled_multi_axis_link_response": False,
            "inelastic_frame_member_and_link_interaction": False,
            "gap_contact_friction_or_uplift": False,
            "viscous_rate_degradation_or_pinching": False,
            "shell_connection_integration": False,
            "external_device_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "general_nonconservative_follower_loads_not_implemented",
            "rotational_and_coupled_multi_axis_link_response_not_implemented",
            "gap_contact_friction_uplift_families_not_state_updated",
            "viscous_rate_degradation_pinching_not_implemented",
            "inelastic_member_and_link_interaction_not_validated",
            "shell_connection_integration_not_implemented",
            "external_device_reference_not_attached",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_link_material_newton_breadth_not_closed",
        ],
        "coupling_claim_boundary": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY
        ),
        "benchmark_claim_boundary": (
            STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY
        ),
    }


__all__ = [
    "STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_UPDATED_AXIS_LINKED_FRAME_CYCLIC_SCHEMA_VERSION",
    "UPDATED_AXIS_LINKED_FRAME_CYCLIC_LOAD_FACTORS",
    "UPDATED_AXIS_LINKED_FRAME_LINK_GLOBAL_DOFS",
    "UPDATED_AXIS_LINKED_FRAME_NEWTON_CONFIG",
    "UPDATED_AXIS_LINKED_FRAME_NODE_COORDINATES_M",
    "UPDATED_AXIS_LINKED_FRAME_REFERENCE_DIRECTION",
    "UPDATED_AXIS_LINKED_FRAME_REFERENCE_LOAD_KN",
    "build_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark",
    "make_stateful_corotational_updated_axis_linked_frame_cyclic_problem",
]
