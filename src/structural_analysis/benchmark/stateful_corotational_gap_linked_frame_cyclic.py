"""Cyclic active-set benchmark for one compression-only frame gap link."""

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
from structural_analysis.benchmark.stateful_corotational_linked_frame_cyclic import (
    LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2,
    LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
    LINKED_FRAME_MEMBER_CONNECTIVITY,
    LINKED_FRAME_NODE_COORDINATES_M,
    LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
    LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M,
    make_stateful_corotational_linked_frame_cyclic_problem,
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
    assess_quadratic_convergence,
)


STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-gap-linked-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_FORMULATION = (
    "two_independent_corotational_fiber_cantilevers_coupled_at_their_free_"
    "global_x_dofs_by_one_frictionless_compression_only_elastic_gap"
)
STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded planar two-column elastic-carrier "
    "frame with a scalar global-x compression-only gap between its free top "
    "nodes. It exercises exact open/closed active-set transitions, a continuous "
    "piecewise-linear force law, one-sided tangent selection, atomic checkpoint "
    "commit, deterministic replay, and exact rollback. It is not a local or "
    "follower contact normal, friction, impact, restitution, coupled contact, "
    "general foundation uplift validation, inelastic contact, member hinge or "
    "shell contact integration, external acceptance, production sparse/ROCm/HIP "
    "execution, full-building equilibrium, G1 closure, or commercial-readiness "
    "evidence."
)

GAP_LINKED_FRAME_NODE_COORDINATES_M = LINKED_FRAME_NODE_COORDINATES_M
GAP_LINKED_FRAME_MEMBER_CONNECTIVITY = LINKED_FRAME_MEMBER_CONNECTIVITY
GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF = LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF = LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF
GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN = 20.0
GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M = 5_000.0
GAP_LINKED_FRAME_INITIAL_GAP_M = 0.004
GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS = (
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
GAP_LINKED_FRAME_NEWTON_CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=60,
)

_ROTATION_COORDINATE_SCALE_M = 3.0
_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8
_MAXIMUM_FORCE_TRANSFER_ERROR_KN = 3.0e-8


def make_stateful_corotational_gap_linked_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DLinkProblem
):
    """Reuse the verified elastic carriers with one bounded unilateral link."""

    base_frame = make_stateful_corotational_linked_frame_cyclic_problem().frame_problem
    frame_problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="stateful-corotational-gap-linked-frame-carrier",
        node_coordinates_m=base_frame.node_coordinates_m,
        members=base_frame.members,
        fixed_global_dofs=base_frame.fixed_global_dofs,
        reference_external_loads=(
            (
                GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
                GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN,
            ),
        ),
        rotation_coordinate_scale_m=_ROTATION_COORDINATE_SCALE_M,
    )
    link = StatefulCorotationalFiberFrame2DCompressionOnlyGapLink(
        link_id="top-compression-only-gap",
        node_i=1,
        node_j=3,
        material=CompressionOnlyGapLink(
            contact_stiffness_kn_per_m=(GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M),
            initial_gap_m=GAP_LINKED_FRAME_INITIAL_GAP_M,
            material_id="gap-linked-frame-top-contact",
        ),
    )
    return StatefulCorotationalFiberFrame2DLinkProblem(
        case_id="stateful-corotational-gap-linked-frame-cyclic",
        frame_problem=frame_problem,
        links=(link,),
    )


def _exact_array_bytes(values: Any) -> bytes:
    return np.ascontiguousarray(values, dtype="<f8").tobytes(order="C")


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


def _step_receipts(
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, step in enumerate(path.steps, start=1):
        assembly = step.trial_assembly
        link_row = assembly.link_assemblies[0]
        response = link_row.response
        state = step.accepted_checkpoint.link_states[0]
        load_factor = float(step.metrics["target_load_factor"])
        applied_horizontal_load = (
            load_factor * GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
        )
        horizontal_reaction_sum = float(
            assembly.reactions_global[0] + assembly.reactions_global[6]
        )
        left_frame_transfer_force = float(
            assembly.frame_assembly.internal_loads_global[
                GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
            ]
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
                "left_top_horizontal_displacement_m": float(
                    assembly.global_displacements[
                        GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
                    ]
                ),
                "right_top_horizontal_displacement_m": float(
                    assembly.global_displacements[
                        GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF
                    ]
                ),
                "link_deformation_m": link_row.deformation_m,
                "link_signed_clearance_m": response.signed_clearance_m,
                "link_penetration_m": response.penetration_m,
                "link_force_kn": response.force_kn,
                "link_consistent_tangent_kn_per_m": (
                    response.consistent_tangent_kn_per_m
                ),
                "contact_active": response.contact_active,
                "active_set_transition": response.active_set_transition,
                "recoverable_contact_energy_kn_m": (response.recoverable_energy_kn_m),
                "maximum_penetration_m": state.maximum_penetration_m,
                "closure_event_count": state.closure_event_count,
                "opening_event_count": state.opening_event_count,
                "link_endpoint_force_sum_error_kn": abs(
                    float(np.sum(link_row.internal_load_global_kn))
                ),
                "link_compatibility_error_m": abs(
                    link_row.deformation_m
                    - float(
                        assembly.global_displacements[
                            GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF
                        ]
                        - assembly.global_displacements[
                            GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
                        ]
                    )
                ),
                "left_frame_link_transfer_error_kn": abs(
                    left_frame_transfer_force - response.force_kn
                ),
                "global_horizontal_balance_error_kn": abs(
                    horizontal_reaction_sum + applied_horizontal_load
                ),
                "frame_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(
                        assembly.frame_geometric_tangent_global,
                        ord=np.inf,
                    )
                ),
                "link_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(
                        assembly.link_geometric_tangent_global,
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
    return rows


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


def build_stateful_corotational_gap_linked_frame_cyclic_benchmark() -> dict[str, Any]:
    """Build a deterministic open-close-open unilateral contact receipt."""

    problem = make_stateful_corotational_gap_linked_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=GAP_LINKED_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=GAP_LINKED_FRAME_NEWTON_CONFIG,
    )
    if path.status != "ready" or not path.contract_pass:
        raise ValueError("gap-linked frame path did not commit every target")
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
    if len(active_steps) < 2 or not open_steps:
        raise ValueError("gap-linked frame did not exercise both active sets")

    open_tangent_step_index = 4
    closed_tangent_step_index = 7
    open_tangent_step = path.steps[open_tangent_step_index - 1]
    closed_tangent_step = path.steps[closed_tangent_step_index - 1]
    open_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
            problem,
            open_tangent_step.parent_checkpoint,
            target_load_factor=GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
                open_tangent_step_index - 1
            ],
            trial_free_coordinates_m=(
                open_tangent_step.trial_solution.free_displacements_m
            ),
            relative_tolerance=1.0e-6,
        )
    )
    closed_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
            problem,
            closed_tangent_step.parent_checkpoint,
            target_load_factor=GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[
                closed_tangent_step_index - 1
            ],
            trial_free_coordinates_m=(
                closed_tangent_step.trial_solution.free_displacements_m
            ),
            relative_tolerance=1.0e-6,
        )
    )
    material = problem.links[0].material
    open_material_tangent = finite_difference_gap_link_tangent_check(
        material,
        open_tangent_step.parent_checkpoint.link_states[0],
        deformation_m=float(steps[open_tangent_step_index - 1]["link_deformation_m"]),
    )
    closed_material_tangent = finite_difference_gap_link_tangent_check(
        material,
        closed_tangent_step.parent_checkpoint.link_states[0],
        deformation_m=float(steps[closed_tangent_step_index - 1]["link_deformation_m"]),
    )
    quadratic = _assess_pre_roundoff_quadratic_convergence(
        list(closed_tangent_step.trial_solution.convergence_history)
    )

    column_stiffness = LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M
    analytic_onset_load_factor = (
        -(column_stiffness * GAP_LINKED_FRAME_INITIAL_GAP_M)
        / GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
    )
    first_active_step = active_steps[0]
    previous_factor = GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[first_active_step - 2]
    first_active_factor = GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[first_active_step - 1]
    onset_bracket_pass = bool(
        previous_factor > analytic_onset_load_factor > first_active_factor
    )

    analytic_open_step_index = 4
    open_load = (
        GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[analytic_open_step_index - 1]
        * GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
    )
    analytic_open_relative_displacement = open_load / column_stiffness
    observed_open_relative_displacement = float(
        steps[analytic_open_step_index - 1]["link_deformation_m"]
    )
    open_relative_displacement_error = abs(
        observed_open_relative_displacement - analytic_open_relative_displacement
    ) / abs(analytic_open_relative_displacement)

    analytic_contact_step_index = 7
    contact_load = (
        GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS[analytic_contact_step_index - 1]
        * GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
    )
    analytic_contact_force = (
        GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M
        * (contact_load + column_stiffness * GAP_LINKED_FRAME_INITIAL_GAP_M)
        / (column_stiffness + 2.0 * GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M)
    )
    observed_contact_force = float(
        steps[analytic_contact_step_index - 1]["link_force_kn"]
    )
    contact_force_relative_error = abs(
        observed_contact_force - analytic_contact_force
    ) / abs(analytic_contact_force)

    zero = np.zeros(problem.global_dof_count, dtype=np.float64)
    open_translation = zero.copy()
    open_translation[
        [
            GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
            GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
        ]
    ] = 0.375
    open_translation_response = material.integrate(
        problem.links[0].deformation_m(open_translation),
        material.initial_state(),
    )
    closed_reference = zero.copy()
    closed_reference[GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF] = -0.125
    closed_translated = closed_reference.copy()
    closed_translated[GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF] += 0.5
    closed_translated[GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF] += 0.5
    closed_reference_response = material.integrate(
        problem.links[0].deformation_m(closed_reference),
        material.initial_state(),
    )
    closed_translated_response = material.integrate(
        problem.links[0].deformation_m(closed_translated),
        material.initial_state(),
    )
    common_translation_exact = bool(
        open_translation_response.deformation_m == 0.0
        and open_translation_response.force_kn == 0.0
        and closed_reference_response.deformation_m
        == closed_translated_response.deformation_m
        and closed_reference_response.force_kn == closed_translated_response.force_kn
        and closed_reference_response.state.canonical_bytes()
        == closed_translated_response.state.canonical_bytes()
    )

    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    maximum_force_transfer_error = max(
        max(
            float(row["left_frame_link_transfer_error_kn"]),
            float(row["global_horizontal_balance_error_kn"]),
            float(row["link_endpoint_force_sum_error_kn"]),
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
    carrier_member_state_evolution_count = sum(
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
    recoverable_energies = [
        float(row["recoverable_contact_energy_kn_m"]) for row in steps
    ]
    conservative_return_pass = bool(
        all(value >= 0.0 for value in recoverable_energies)
        and recoverable_energies[-1] == 0.0
        and final_state.contact_active is False
    )
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
        len(path.steps) == len(GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS)
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
        and open_relative_displacement_error <= 1.0e-5
        and contact_force_relative_error <= 1.0e-5
        and open_tangent["pass"] is True
        and closed_tangent["pass"] is True
        and open_tangent["link_material_tangent_inf_norm_kn_per_m"] == 0.0
        and closed_tangent["link_material_tangent_inf_norm_kn_per_m"] > 0.0
        and closed_tangent["all_tangent_terms_active"] is True
        and open_material_tangent["pass"] is True
        and closed_material_tangent["pass"] is True
        and quadratic["pass"] is True
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and maximum_force_transfer_error <= _MAXIMUM_FORCE_TRANSFER_ERROR_KN
        and maximum_compatibility_error == 0.0
        and maximum_link_geometric_tangent == 0.0
        and maximum_frame_geometric_tangent > 0.0
        and carrier_member_state_evolution_count == 0
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and common_translation_exact
        and rollback_exact
    )
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
        ),
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": ("internal_analytic_piecewise_linear_unilateral_gap_frame"),
        "formulation": STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_FORMULATION,
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in GAP_LINKED_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [
                list(row) for row in GAP_LINKED_FRAME_MEMBER_CONNECTIVITY
            ],
            "fixed_global_dofs": [0, 1, 2, 6, 7, 8],
            "link_end_nodes": [1, 3],
            "link_component": "ux",
            "contact_normal": "global_x_node_i_to_node_j",
            "link_global_dofs": [
                GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
                GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
            ],
            "right_top_reference_load_kn": (
                GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
            ),
            "rotation_coordinate_scale_m": _ROTATION_COORDINATE_SCALE_M,
        },
        "elastic_carrier_frame": {
            "column_flexural_rigidity_kn_m2": (
                LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
            ),
            "small_displacement_column_lateral_stiffness_kn_per_m": (column_stiffness),
            "member_state_evolution_count": carrier_member_state_evolution_count,
        },
        "gap_link": {
            **problem.links[0].contract_payload()["material"],
            "active_set_algorithm": GAP_LINK_ACTIVE_SET_ALGORITHM,
            "closure_convention": GAP_LINK_CLOSURE_CONVENTION,
            "tangent_definition": GAP_LINK_TANGENT_DEFINITION,
            "force_sign_convention": "compression_negative",
            "dissipation_model": "none_elastic_recoverable_only",
        },
        "cyclic_load_factors": list(GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
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
            "step_index": analytic_open_step_index,
            "analytic_relative_displacement_m": (analytic_open_relative_displacement),
            "observed_relative_displacement_m": (observed_open_relative_displacement),
            "relative_error": open_relative_displacement_error,
            "relative_tolerance": 1.0e-5,
            "pass": open_relative_displacement_error <= 1.0e-5,
        },
        "analytic_contact_branch": {
            "step_index": analytic_contact_step_index,
            "analytic_contact_force_kn": analytic_contact_force,
            "observed_contact_force_kn": observed_contact_force,
            "relative_error": contact_force_relative_error,
            "relative_tolerance": 1.0e-5,
            "pass": contact_force_relative_error <= 1.0e-5,
        },
        "same_parent_open_frame_gap_tangent": open_tangent,
        "same_parent_closed_frame_gap_tangent": closed_tangent,
        "same_parent_open_material_tangent": open_material_tangent,
        "same_parent_closed_material_tangent": closed_material_tangent,
        "closed_active_set_newton_quadratic_convergence": quadratic,
        "common_translation_objectivity": {
            "open_common_translation_m": 0.375,
            "closed_common_translation_m": 0.5,
            "exact": common_translation_exact,
        },
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_residual_inf_norm_tolerance_kn": (_MAXIMUM_RESIDUAL_INF_NORM_KN),
        "maximum_force_transfer_error_kn": maximum_force_transfer_error,
        "maximum_force_transfer_error_tolerance_kn": (_MAXIMUM_FORCE_TRANSFER_ERROR_KN),
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
            "accepted_checkpoint_hash_after": (failed.accepted_checkpoint.state_hash),
            "accepted_link_state_hash_after": (
                failed.accepted_checkpoint.link_states[0].state_hash
            ),
            "exact": rollback_exact,
        },
        "steps": steps,
        "claims": {
            "bounded_two_member_corotational_fiber_frame": True,
            "scalar_global_x_compression_only_gap": True,
            "frictionless_continuous_unilateral_response": True,
            "open_closed_active_set_checkpoint_history": True,
            "same_parent_open_and_closed_consistent_tangents": True,
            "atomic_frame_and_gap_checkpoint_commit": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "analytic_open_contact_onset_and_closed_branch": True,
            "local_or_follower_contact_normal": False,
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
            STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY
        ),
    }


__all__ = [
    "GAP_LINKED_FRAME_CONTACT_STIFFNESS_KN_PER_M",
    "GAP_LINKED_FRAME_CYCLIC_LOAD_FACTORS",
    "GAP_LINKED_FRAME_INITIAL_GAP_M",
    "GAP_LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF",
    "GAP_LINKED_FRAME_MEMBER_CONNECTIVITY",
    "GAP_LINKED_FRAME_NEWTON_CONFIG",
    "GAP_LINKED_FRAME_NODE_COORDINATES_M",
    "GAP_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN",
    "GAP_LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF",
    "STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_GAP_LINKED_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_gap_linked_frame_cyclic_benchmark",
    "make_stateful_corotational_gap_linked_frame_cyclic_problem",
]
