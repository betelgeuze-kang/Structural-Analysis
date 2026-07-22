"""Cyclic moment-rotation link benchmark on a corotational fiber frame."""

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
    StatefulCorotationalFiberFrame2DRotationalLink,
    assemble_stateful_corotational_fiber_frame2d_links,
    finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check,
    initial_stateful_corotational_fiber_frame2d_link_checkpoint,
    run_stateful_corotational_fiber_frame2d_link_load_path,
    solve_stateful_corotational_fiber_frame2d_link_load_step,
)
from structural_analysis.benchmark.stateful_corotational_linked_frame_cyclic import (
    LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2,
    LINKED_FRAME_CYCLIC_LOAD_FACTORS,
    LINKED_FRAME_MEMBER_CONNECTIVITY,
    LINKED_FRAME_NEWTON_CONFIG,
    LINKED_FRAME_NODE_COORDINATES_M,
    LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN,
    make_stateful_corotational_linked_frame_cyclic_problem,
)
from structural_analysis.materials.bilinear_rotational_link import (
    BilinearCombinedHardeningRotationalLink,
    finite_difference_rotational_link_tangent_check,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-rotational-linked-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION = (
    "paired_two_corotational_fiber_cantilevers_with_free_top_rz_dofs_coupled_"
    "by_one_state_updated_bilinear_moment_rotation_link"
)
STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark reuses the exact two-cantilever carrier, geometry, load, "
    "and 30-target path of the global-x translational-link case, but couples "
    "only the two free top rz DOFs through one scalar bilinear moment-rotation "
    "link with a distinct kN-m/rad material and rotational state. It does not "
    "establish coupled multi-axis link response, hinge localization within a "
    "member, gap/contact, friction, uplift, damping, rate dependence, "
    "degradation or pinching, inelastic frame-member/link interaction, shell "
    "or 3D connection integration, external device acceptance, production "
    "sparse/ROCm/HIP execution, full-building equilibrium, G1 closure, or "
    "commercial readiness."
)

ROTATIONAL_LINKED_FRAME_NODE_COORDINATES_M = LINKED_FRAME_NODE_COORDINATES_M
ROTATIONAL_LINKED_FRAME_MEMBER_CONNECTIVITY = LINKED_FRAME_MEMBER_CONNECTIVITY
ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF = 5
ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF = 11
ROTATIONAL_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN = (
    LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
)
ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS = LINKED_FRAME_CYCLIC_LOAD_FACTORS
ROTATIONAL_LINKED_FRAME_NEWTON_CONFIG = LINKED_FRAME_NEWTON_CONFIG
ROTATIONAL_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2 = (
    LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
)

_COLUMN_HEIGHT_M = 3.0
_LINK_INITIAL_STIFFNESS_KN_M_PER_RAD = 5_000.0
_LINK_YIELD_MOMENT_KN_M = 20.0
_LINK_ISOTROPIC_HARDENING_KN_M_PER_RAD = 200.0
_LINK_KINEMATIC_HARDENING_KN_M_PER_RAD = 300.0
_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8
_MAXIMUM_MOMENT_TRANSFER_ERROR_KN_M = 3.0e-8
_ELASTIC_REFERENCE_RELATIVE_TOLERANCE = 1.0e-5


def _elastic_rotational_link_moment_kn_m(applied_load_kn: float) -> float:
    """Return the small-displacement two-cantilever connector moment."""

    stiffness = _LINK_INITIAL_STIFFNESS_KN_M_PER_RAD
    height = _COLUMN_HEIGHT_M
    rigidity = ROTATIONAL_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
    return (
        stiffness
        * applied_load_kn
        * height**2
        / (2.0 * rigidity + 4.0 * stiffness * height)
    )


def make_stateful_corotational_rotational_linked_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DLinkProblem
):
    """Create the paired elastic carriers with one free-to-free rz link."""

    translational_case = make_stateful_corotational_linked_frame_cyclic_problem()
    frame_problem = replace(
        translational_case.frame_problem,
        case_id="stateful-corotational-rotational-linked-frame-carrier",
    )
    link = StatefulCorotationalFiberFrame2DRotationalLink(
        link_id="top-rotation-transfer-link",
        node_i=1,
        node_j=3,
        material=BilinearCombinedHardeningRotationalLink(
            initial_stiffness_kn_m_per_rad=(_LINK_INITIAL_STIFFNESS_KN_M_PER_RAD),
            yield_moment_kn_m=_LINK_YIELD_MOMENT_KN_M,
            isotropic_hardening_kn_m_per_rad=(_LINK_ISOTROPIC_HARDENING_KN_M_PER_RAD),
            kinematic_hardening_kn_m_per_rad=(_LINK_KINEMATIC_HARDENING_KN_M_PER_RAD),
            material_id="linked-frame-top-rotation-bilinear",
        ),
    )
    return StatefulCorotationalFiberFrame2DLinkProblem(
        case_id="stateful-corotational-rotational-linked-frame-cyclic",
        frame_problem=frame_problem,
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
            np.ascontiguousarray(a.trial_assembly.residual_kn, dtype="<f8").tobytes()
            == np.ascontiguousarray(
                b.trial_assembly.residual_kn,
                dtype="<f8",
            ).tobytes()
            and np.ascontiguousarray(
                a.trial_assembly.jacobian_kn_per_m,
                dtype="<f8",
            ).tobytes()
            == np.ascontiguousarray(
                b.trial_assembly.jacobian_kn_per_m,
                dtype="<f8",
            ).tobytes()
            for a, b in zip(left.steps, right.steps, strict=True)
        )
    )


def _step_receipts(
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_plastic_rotation = 0.0
    for index, step in enumerate(path.steps, start=1):
        assembly = step.trial_assembly
        link_row = assembly.link_assemblies[0]
        state = step.accepted_checkpoint.link_states[0]
        plastic_increment = state.plastic_rotation_rad - previous_plastic_rotation
        flow_direction = (
            1 if plastic_increment > 0.0 else -1 if plastic_increment < 0.0 else 0
        )
        left_frame_moment = float(
            assembly.frame_assembly.internal_loads_global[
                ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF
            ]
        )
        right_frame_moment = float(
            assembly.frame_assembly.internal_loads_global[
                ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF
            ]
        )
        rows.append(
            {
                "step_index": index,
                "load_factor": float(step.metrics["target_load_factor"]),
                "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "nested_frame_checkpoint_hash": (
                    step.accepted_checkpoint.frame_checkpoint.state_hash
                ),
                "left_top_rotation_rad": float(
                    assembly.global_displacements[
                        ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF
                    ]
                ),
                "right_top_rotation_rad": float(
                    assembly.global_displacements[
                        ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF
                    ]
                ),
                "link_rotation_rad": link_row.rotation_rad,
                "link_moment_kn_m": link_row.response.moment_kn_m,
                "link_consistent_tangent_kn_m_per_rad": (
                    link_row.response.consistent_tangent_kn_m_per_rad
                ),
                "link_yielded": link_row.response.yielded,
                "link_plastic_flow_direction": flow_direction,
                "link_accumulated_plastic_rotation_rad": (
                    state.accumulated_plastic_rotation_rad
                ),
                "link_dissipated_energy_kn_m": state.dissipated_energy_kn_m,
                "link_endpoint_moment_sum_error_kn_m": abs(
                    float(np.sum(link_row.internal_moments_global_kn_m))
                ),
                "link_compatibility_error_rad": abs(
                    link_row.rotation_rad
                    - float(
                        assembly.global_displacements[
                            ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF
                        ]
                        - assembly.global_displacements[
                            ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF
                        ]
                    )
                ),
                "left_frame_link_transfer_error_kn_m": abs(
                    left_frame_moment - link_row.response.moment_kn_m
                ),
                "right_frame_link_transfer_error_kn_m": abs(
                    right_frame_moment + link_row.response.moment_kn_m
                ),
                "frame_geometric_tangent_inf_norm": float(
                    np.linalg.norm(
                        assembly.frame_geometric_tangent_global,
                        ord=np.inf,
                    )
                ),
                "link_geometric_tangent_inf_norm": float(
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
                "line_search_history_entry_count": len(
                    step.trial_solution.line_search_history
                ),
                "yielded_member_count": step.metrics["yielded_member_count"],
                "damaged_member_count": step.metrics["damaged_member_count"],
                "regularization_used": step.metrics["regularization_used"],
                "fallback_used": step.metrics["fallback_used"],
            }
        )
        previous_plastic_rotation = state.plastic_rotation_rad
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


def build_stateful_corotational_rotational_linked_frame_cyclic_benchmark() -> dict[
    str, Any
]:
    """Build the deterministic scalar moment-rotation coupling receipt."""

    problem = make_stateful_corotational_rotational_linked_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=ROTATIONAL_LINKED_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=ROTATIONAL_LINKED_FRAME_NEWTON_CONFIG,
    )
    steps = _step_receipts(path)
    yielded_steps = [
        int(row["step_index"]) for row in steps if bool(row["link_yielded"])
    ]
    reverse_yielded_steps = [
        index
        for index in yielded_steps
        if ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS[index - 1] < 0.0
    ]
    if not yielded_steps or not reverse_yielded_steps:
        raise ValueError("rotational-link benchmark did not exercise both branches")
    tangent_step_index = next(
        index
        for index in yielded_steps
        if path.steps[index - 1]
        .parent_checkpoint.link_states[0]
        .accumulated_plastic_rotation_rad
        > 0.0
    )
    tangent_step = path.steps[tangent_step_index - 1]
    tangent = finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
        problem,
        tangent_step.parent_checkpoint,
        target_load_factor=(
            ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS[tangent_step_index - 1]
        ),
        trial_free_coordinates_m=tangent_step.trial_solution.free_displacements_m,
    )
    material_tangent = finite_difference_rotational_link_tangent_check(
        problem.links[0].material,
        tangent_step.parent_checkpoint.link_states[0],
        rotation_rad=tangent_step.trial_assembly.link_assemblies[0].rotation_rad,
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
        ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS[0]
        * ROTATIONAL_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
    )
    analytic_elastic_moment = _elastic_rotational_link_moment_kn_m(elastic_applied_load)
    elastic_moment_relative_error = (
        abs(abs(float(elastic_step["link_moment_kn_m"])) - analytic_elastic_moment)
        / analytic_elastic_moment
    )
    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    maximum_moment_transfer_error = max(
        max(
            float(row["link_endpoint_moment_sum_error_kn_m"]),
            float(row["left_frame_link_transfer_error_kn_m"]),
            float(row["right_frame_link_transfer_error_kn_m"]),
        )
        for row in steps
    )
    maximum_compatibility_error = max(
        float(row["link_compatibility_error_rad"]) for row in steps
    )
    maximum_frame_geometric_tangent = max(
        float(row["frame_geometric_tangent_inf_norm"]) for row in steps
    )
    maximum_link_geometric_tangent = max(
        float(row["link_geometric_tangent_inf_norm"]) for row in steps
    )
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

    common_rotation_displacements = np.zeros(
        problem.global_dof_count,
        dtype=np.float64,
    )
    common_rotation_displacements[ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF] = 0.37
    common_rotation_displacements[ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF] = 0.37
    common_rotation_error = abs(
        problem.links[0].rotation_rad(common_rotation_displacements)
    )
    common_rotation_moment = abs(
        problem.links[0]
        .material.integrate(
            problem.links[0].rotation_rad(common_rotation_displacements),
            problem.links[0].material.initial_state(),
        )
        .moment_kn_m
    )

    initial_checkpoint = initial_stateful_corotational_fiber_frame2d_link_checkpoint(
        problem
    )
    zero_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        initial_checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )
    rotation_dofs = problem.links[0].global_dofs()
    zero_link_tangent = zero_assembly.link_material_tangent_global[
        np.ix_(rotation_dofs, rotation_dofs)
    ]
    expected_zero_link_tangent = _LINK_INITIAL_STIFFNESS_KN_M_PER_RAD * np.array(
        ((1.0, -1.0), (-1.0, 1.0)), dtype=np.float64
    )
    physical_tangent_error = float(
        np.linalg.norm(zero_link_tangent - expected_zero_link_tangent, ord=np.inf)
    )
    rotational_scale = problem.physical_coordinate_scale[list(rotation_dofs)]
    generalized_zero_link_tangent = (
        rotational_scale[:, None] * zero_link_tangent * rotational_scale[None, :]
    )
    expected_generalized_zero_link_tangent = (
        expected_zero_link_tangent / _COLUMN_HEIGHT_M**2
    )
    generalized_tangent_error = float(
        np.linalg.norm(
            generalized_zero_link_tangent - expected_generalized_zero_link_tangent,
            ord=np.inf,
        )
    )

    rollback_parent = path.steps[8].accepted_checkpoint
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
        and rollback_parent.link_states[0].accumulated_plastic_rotation_rad > 0.0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )
    contract_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS)
        and ancestry_exact
        and deterministic_replay
        and yielded_steps
        and reverse_yielded_steps
        and flow_reversal_count >= 1
        and dissipation_monotonic
        and energy_history[-1] > 0.0
        and tangent["pass"] is True
        and tangent["yielded_link_count"] > 0
        and tangent["all_tangent_terms_active"] is True
        and material_tangent["pass"] is True
        and quadratic["pass"] is True
        and elastic_moment_relative_error <= _ELASTIC_REFERENCE_RELATIVE_TOLERANCE
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and maximum_moment_transfer_error <= _MAXIMUM_MOMENT_TRANSFER_ERROR_KN_M
        and maximum_compatibility_error == 0.0
        and maximum_frame_geometric_tangent > 0.0
        and maximum_link_geometric_tangent == 0.0
        and common_rotation_error == 0.0
        and common_rotation_moment == 0.0
        and physical_tangent_error == 0.0
        and generalized_tangent_error <= 1.0e-12
        and carrier_member_state_evolution_count == 0
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rollback_exact
    )
    return {
        "schema_version": (
            STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION
        ),
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": (
            "internal_analytic_elastic_prefix_and_algorithmic_cyclic_"
            "moment_rotation_linked_frame"
        ),
        "formulation": (
            STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION
        ),
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in ROTATIONAL_LINKED_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [
                list(row) for row in ROTATIONAL_LINKED_FRAME_MEMBER_CONNECTIVITY
            ],
            "fixed_global_dofs": [0, 1, 2, 6, 7, 8],
            "link_end_nodes": [1, 3],
            "link_component": "rz",
            "link_global_dofs": list(rotation_dofs),
            "right_top_reference_load_kn": (
                ROTATIONAL_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
            ),
            "rotation_coordinate_scale_m": _COLUMN_HEIGHT_M,
        },
        "elastic_carrier_frame": {
            "paired_with_global_x_translational_link_benchmark": True,
            "column_flexural_rigidity_kn_m2": (
                ROTATIONAL_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
            ),
            "member_state_evolution_count": carrier_member_state_evolution_count,
        },
        "rotational_link": {
            **problem.links[0].contract_payload()["material"],
            "plastic_consistent_tangent_kn_m_per_rad": (
                problem.links[0].material.plastic_consistent_tangent_kn_m_per_rad
            ),
        },
        "cyclic_load_factors": list(ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS),
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
            "load_factor": ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS[0],
            "analytic_link_moment_kn_m": analytic_elastic_moment,
            "observed_link_moment_kn_m": elastic_step["link_moment_kn_m"],
            "relative_error": elastic_moment_relative_error,
            "relative_tolerance": _ELASTIC_REFERENCE_RELATIVE_TOLERANCE,
            "pass": (
                elastic_moment_relative_error <= _ELASTIC_REFERENCE_RELATIVE_TOLERANCE
            ),
        },
        "common_rotation_objectivity": {
            "common_rotation_rad": 0.37,
            "relative_rotation_error_rad": common_rotation_error,
            "link_moment_error_kn_m": common_rotation_moment,
            "pass": common_rotation_error == 0.0 and common_rotation_moment == 0.0,
        },
        "rotation_coordinate_scaling": {
            "physical_tangent_error_kn_m_per_rad": physical_tangent_error,
            "generalized_tangent_error_kn_per_m": generalized_tangent_error,
            "pass": physical_tangent_error == 0.0
            and generalized_tangent_error <= 1.0e-12,
        },
        "same_parent_frame_link_tangent": tangent,
        "same_parent_moment_rotation_material_tangent": material_tangent,
        "yielded_link_newton_quadratic_convergence": quadratic,
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_residual_inf_norm_tolerance_kn": _MAXIMUM_RESIDUAL_INF_NORM_KN,
        "maximum_moment_transfer_error_kn_m": maximum_moment_transfer_error,
        "maximum_moment_transfer_error_tolerance_kn_m": (
            _MAXIMUM_MOMENT_TRANSFER_ERROR_KN_M
        ),
        "maximum_link_compatibility_error_rad": maximum_compatibility_error,
        "maximum_frame_geometric_tangent_inf_norm": (maximum_frame_geometric_tangent),
        "maximum_link_geometric_tangent_inf_norm": maximum_link_geometric_tangent,
        "line_search_history_entry_count": line_search_history_entries,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "parent_link_state_hash": rollback_parent.link_states[0].state_hash,
            "parent_link_accumulated_plastic_rotation_rad": (
                rollback_parent.link_states[0].accumulated_plastic_rotation_rad
            ),
            "target_load_factor": -1.0,
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
            "free_to_free_scalar_relative_rz_link": True,
            "distinct_moment_rotation_material_and_state_units": True,
            "state_updated_link_moment_and_tangent_scatter": True,
            "cyclic_link_yield_reversal_and_nonnegative_dissipation": True,
            "atomic_frame_and_link_checkpoint_commit": True,
            "same_parent_frame_link_consistent_tangent": True,
            "common_rotation_objectivity": True,
            "analytic_elastic_moment_transfer_prefix": True,
            "coupled_multi_axis_link_response": False,
            "inelastic_frame_member_and_link_interaction": False,
            "gap_contact_friction_or_uplift": False,
            "viscous_rate_degradation_or_pinching": False,
            "shell_or_3d_connection_integration": False,
            "external_device_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "coupled_multi_axis_link_response_not_implemented",
            "gap_contact_friction_uplift_families_not_state_updated",
            "viscous_rate_degradation_pinching_not_implemented",
            "inelastic_member_and_link_interaction_not_validated",
            "shell_or_3d_connection_integration_not_implemented",
            "external_device_reference_not_attached",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_link_material_newton_breadth_not_closed",
        ],
        "coupling_claim_boundary": (
            STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY
        ),
        "benchmark_claim_boundary": (
            STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY
        ),
    }


__all__ = [
    "ROTATIONAL_LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2",
    "ROTATIONAL_LINKED_FRAME_CYCLIC_LOAD_FACTORS",
    "ROTATIONAL_LINKED_FRAME_LEFT_TOP_ROTATION_DOF",
    "ROTATIONAL_LINKED_FRAME_MEMBER_CONNECTIVITY",
    "ROTATIONAL_LINKED_FRAME_NEWTON_CONFIG",
    "ROTATIONAL_LINKED_FRAME_NODE_COORDINATES_M",
    "ROTATIONAL_LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN",
    "ROTATIONAL_LINKED_FRAME_RIGHT_TOP_ROTATION_DOF",
    "STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_ROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_rotational_linked_frame_cyclic_benchmark",
    "make_stateful_corotational_rotational_linked_frame_cyclic_problem",
]
