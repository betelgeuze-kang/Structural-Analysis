"""Cyclic bilinear-link coupling benchmark on a corotational fiber frame."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_link import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY,
    StatefulCorotationalFiberFrame2DLink,
    StatefulCorotationalFiberFrame2DLinkLoadPathResult,
    StatefulCorotationalFiberFrame2DLinkProblem,
    finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check,
    run_stateful_corotational_fiber_frame2d_link_load_path,
    solve_stateful_corotational_fiber_frame2d_link_load_step,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.materials.bilinear_link import BilinearCombinedHardeningLink
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-linked-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION = (
    "two_independent_corotational_fiber_cantilevers_coupled_at_their_free_"
    "horizontal_dofs_by_one_state_updated_bilinear_force_deformation_link"
)
STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded planar two-column frame whose free "
    "top horizontal DOFs are connected by a global-x scalar bilinear link. "
    "The deliberately high-strength fiber sections remain elastic carriers so "
    "the link state, force transfer, dissipation, tangent scatter, atomic commit, "
    "and rollback can be isolated. It is not rotational or multi-axis link "
    "coupling, local-axis transformation, gap/contact, friction, uplift, damping, "
    "rate dependence, degradation or pinching, inelastic frame-member coupling, "
    "shell connection integration, an external device acceptance result, "
    "production sparse/ROCm/HIP execution, full-building equilibrium, G1 closure, "
    "or commercial-readiness evidence."
)

LINKED_FRAME_NODE_COORDINATES_M = (
    (0.0, 0.0),
    (0.0, 3.0),
    (3.0, 0.0),
    (3.0, 3.0),
)
LINKED_FRAME_MEMBER_CONNECTIVITY = ((0, 1), (2, 3))
LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF = 3
LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF = 9
LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN = 80.0
LINKED_FRAME_CYCLIC_LOAD_FACTORS = (
    0.1,
    0.2,
    0.3,
    0.4,
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
    1.0,
    0.8,
    0.6,
    0.4,
    0.2,
    0.0,
    -0.2,
    -0.4,
    -0.6,
    -0.8,
    -1.0,
    -0.8,
    -0.6,
    -0.4,
    -0.2,
    0.0,
    0.2,
    0.4,
    0.6,
    0.8,
    1.0,
)

_COLUMN_HEIGHT_M = 3.0
_SECTION_WIDTH_M = 0.25
_SECTION_DEPTH_M = 0.40
_SECTION_COVER_M = 0.04
_CONCRETE_LAYER_COUNT = 4
_BAR_COUNT_PER_FACE = 2
_BAR_AREA_M2 = 4.0e-4
_STEEL_ELASTIC_MODULUS_MPA = 200_000.0
_ELASTIC_CARRIER_STRENGTH_MPA = 1.0e12
_CONCRETE_CARRIER_ELASTIC_MODULUS_MPA = 1.0
_LINK_INITIAL_STIFFNESS_KN_PER_M = 5_000.0
_LINK_YIELD_FORCE_KN = 20.0
_LINK_ISOTROPIC_HARDENING_KN_PER_M = 200.0
_LINK_KINEMATIC_HARDENING_KN_PER_M = 300.0
_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8
_MAXIMUM_FORCE_TRANSFER_ERROR_KN = 3.0e-8

LINKED_FRAME_NEWTON_CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=60,
)


def _elastic_frame_properties() -> dict[str, float]:
    bar_y = 0.5 * _SECTION_DEPTH_M - _SECTION_COVER_M
    steel_second_moment = 2.0 * _BAR_COUNT_PER_FACE * _BAR_AREA_M2 * bar_y**2
    layer_depth = _SECTION_DEPTH_M / _CONCRETE_LAYER_COUNT
    layer_area = _SECTION_WIDTH_M * layer_depth
    layer_ys = tuple(
        -0.5 * _SECTION_DEPTH_M + (index + 0.5) * layer_depth
        for index in range(_CONCRETE_LAYER_COUNT)
    )
    concrete_second_moment = math.fsum(layer_area * y**2 for y in layer_ys)
    rigidity = 1_000.0 * (
        _STEEL_ELASTIC_MODULUS_MPA * steel_second_moment
        + _CONCRETE_CARRIER_ELASTIC_MODULUS_MPA * concrete_second_moment
    )
    lateral_stiffness = 3.0 * rigidity / _COLUMN_HEIGHT_M**3
    transfer_fraction = _LINK_INITIAL_STIFFNESS_KN_PER_M / (
        lateral_stiffness + 2.0 * _LINK_INITIAL_STIFFNESS_KN_PER_M
    )
    return {
        "column_flexural_rigidity_kn_m2": rigidity,
        "small_displacement_column_lateral_stiffness_kn_per_m": (lateral_stiffness),
        "elastic_link_transfer_fraction": transfer_fraction,
    }


_ELASTIC_FRAME_PROPERTIES = _elastic_frame_properties()
LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2 = _ELASTIC_FRAME_PROPERTIES[
    "column_flexural_rigidity_kn_m2"
]
LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M = (
    _ELASTIC_FRAME_PROPERTIES["small_displacement_column_lateral_stiffness_kn_per_m"]
)
LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION = _ELASTIC_FRAME_PROPERTIES[
    "elastic_link_transfer_fraction"
]


def make_stateful_corotational_linked_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DLinkProblem
):
    """Create two elastic-carrier cantilevers coupled by one stateful link."""

    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=_STEEL_ELASTIC_MODULUS_MPA,
        yield_stress_mpa=_ELASTIC_CARRIER_STRENGTH_MPA,
        isotropic_hardening_modulus_mpa=0.0,
        kinematic_hardening_modulus_mpa=0.0,
        material_id="linked-frame-elastic-steel-carrier",
    )
    concrete = AsymmetricConcreteDamageMaterial(
        elastic_modulus_mpa=_CONCRETE_CARRIER_ELASTIC_MODULUS_MPA,
        tensile_strength_mpa=_ELASTIC_CARRIER_STRENGTH_MPA,
        compressive_strength_mpa=_ELASTIC_CARRIER_STRENGTH_MPA,
        tensile_softening_rate=1.0,
        compressive_softening_rate=1.0,
        material_id="linked-frame-elastic-concrete-carrier",
    )
    members: list[StatefulCorotationalFiberFrame2DMember] = []
    for member_index, (node_i, node_j) in enumerate(
        LINKED_FRAME_MEMBER_CONNECTIVITY,
        start=1,
    ):
        member_id = f"linked-frame-column-{member_index}"
        section = make_rectangular_stateful_rc_fiber_section(
            width_m=_SECTION_WIDTH_M,
            depth_m=_SECTION_DEPTH_M,
            cover_m=_SECTION_COVER_M,
            concrete_layer_count=_CONCRETE_LAYER_COUNT,
            top_bar_count=_BAR_COUNT_PER_FACE,
            bottom_bar_count=_BAR_COUNT_PER_FACE,
            bar_area_m2=_BAR_AREA_M2,
            section_id=f"linked-frame-section-{member_index}",
            steel=steel,
            concrete=concrete,
        )
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        LINKED_FRAME_NODE_COORDINATES_M[node_i],
                        LINKED_FRAME_NODE_COORDINATES_M[node_j],
                    ),
                    section=section,
                    integration_order=3,
                    element_id=member_id,
                ),
            )
        )
    frame_problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="stateful-corotational-linked-frame-carrier",
        node_coordinates_m=LINKED_FRAME_NODE_COORDINATES_M,
        members=tuple(members),
        fixed_global_dofs=(0, 1, 2, 6, 7, 8),
        reference_external_loads=(
            (
                LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
                LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN,
            ),
        ),
        rotation_coordinate_scale_m=_COLUMN_HEIGHT_M,
    )
    link = StatefulCorotationalFiberFrame2DLink(
        link_id="top-transfer-link",
        node_i=1,
        node_j=3,
        component="ux",
        material=BilinearCombinedHardeningLink(
            initial_stiffness_kn_per_m=_LINK_INITIAL_STIFFNESS_KN_PER_M,
            yield_force_kn=_LINK_YIELD_FORCE_KN,
            isotropic_hardening_kn_per_m=(_LINK_ISOTROPIC_HARDENING_KN_PER_M),
            kinematic_hardening_kn_per_m=(_LINK_KINEMATIC_HARDENING_KN_PER_M),
            material_id="linked-frame-top-transfer-bilinear",
        ),
    )
    return StatefulCorotationalFiberFrame2DLinkProblem(
        case_id="stateful-corotational-linked-frame-cyclic",
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
            _exact_array_bytes(a.trial_assembly.residual_kn)
            == _exact_array_bytes(b.trial_assembly.residual_kn)
            and _exact_array_bytes(a.trial_assembly.jacobian_kn_per_m)
            == _exact_array_bytes(b.trial_assembly.jacobian_kn_per_m)
            for a, b in zip(left.steps, right.steps, strict=True)
        )
    )


def _exact_array_bytes(values: Any) -> bytes:
    return np.ascontiguousarray(values, dtype="<f8").tobytes(order="C")


def _step_receipts(
    path: StatefulCorotationalFiberFrame2DLinkLoadPathResult,
) -> list[dict[str, Any]]:
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
        applied_horizontal_load = load_factor * LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
        horizontal_reaction_sum = float(
            assembly.reactions_global[0] + assembly.reactions_global[6]
        )
        left_frame_transfer_force = float(
            assembly.frame_assembly.internal_loads_global[
                LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
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
                    assembly.global_displacements[LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF]
                ),
                "right_top_horizontal_displacement_m": float(
                    assembly.global_displacements[LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF]
                ),
                "link_deformation_m": link_row.deformation_m,
                "link_force_kn": link_row.response.force_kn,
                "link_consistent_tangent_kn_per_m": (
                    link_row.response.consistent_tangent_kn_per_m
                ),
                "link_yielded": link_row.response.yielded,
                "link_plastic_flow_direction": flow_direction,
                "link_accumulated_plastic_deformation_m": (
                    state.accumulated_plastic_deformation_m
                ),
                "link_dissipated_energy_kn_m": state.dissipated_energy_kn_m,
                "link_endpoint_force_sum_error_kn": abs(
                    float(np.sum(link_row.internal_load_global_kn))
                ),
                "link_compatibility_error_m": abs(
                    link_row.deformation_m
                    - float(
                        assembly.global_displacements[
                            LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF
                        ]
                        - assembly.global_displacements[
                            LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF
                        ]
                    )
                ),
                "left_frame_link_transfer_error_kn": abs(
                    left_frame_transfer_force - link_row.response.force_kn
                ),
                "global_horizontal_balance_error_kn": abs(
                    horizontal_reaction_sum + applied_horizontal_load
                ),
                "frame_geometric_tangent_inf_norm_kn_per_m": float(
                    np.linalg.norm(assembly.geometric_tangent_global, ord=np.inf)
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


def _assess_pre_roundoff_quadratic_convergence(
    convergence_history: list[dict[str, Any]],
    *,
    relative_residual_floor: float = 1.0e-7,
) -> dict[str, Any]:
    """Assess full-step Newton order through the first numerical-floor point."""

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


def build_stateful_corotational_linked_frame_cyclic_benchmark() -> dict[str, Any]:
    """Build the deterministic cyclic frame-to-frame link receipt."""

    problem = make_stateful_corotational_linked_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=LINKED_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_link_load_path(
        problem,
        LINKED_FRAME_CYCLIC_LOAD_FACTORS,
        config=LINKED_FRAME_NEWTON_CONFIG,
    )
    steps = _step_receipts(path)
    yielded_steps = [
        int(row["step_index"]) for row in steps if bool(row["link_yielded"])
    ]
    reverse_yielded_steps = [
        index
        for index in yielded_steps
        if LINKED_FRAME_CYCLIC_LOAD_FACTORS[index - 1] < 0.0
    ]
    if not yielded_steps or not reverse_yielded_steps:
        raise ValueError("linked-frame benchmark did not exercise both link branches")
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
        target_load_factor=LINKED_FRAME_CYCLIC_LOAD_FACTORS[tangent_step_index - 1],
        trial_free_coordinates_m=tangent_step.trial_solution.free_displacements_m,
    )
    quadratic = _assess_pre_roundoff_quadratic_convergence(
        list(tangent_step.trial_solution.convergence_history),
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
        LINKED_FRAME_CYCLIC_LOAD_FACTORS[0] * LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN
    )
    analytic_elastic_link_force = (
        elastic_applied_load * LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION
    )
    elastic_link_force_relative_error = abs(
        float(elastic_step["link_force_kn"]) - analytic_elastic_link_force
    ) / abs(analytic_elastic_link_force)
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
        and rollback_parent.link_states[0].accumulated_plastic_deformation_m > 0.0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )
    contract_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(LINKED_FRAME_CYCLIC_LOAD_FACTORS)
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
        and quadratic["pass"] is True
        and elastic_link_force_relative_error <= 1.0e-4
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and maximum_force_transfer_error <= _MAXIMUM_FORCE_TRANSFER_ERROR_KN
        and maximum_compatibility_error == 0.0
        and carrier_member_state_evolution_count == 0
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rollback_exact
    )
    return {
        "schema_version": STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION,
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": (
            "internal_analytic_elastic_prefix_and_algorithmic_cyclic_linked_frame"
        ),
        "formulation": STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION,
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in LINKED_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [
                list(row) for row in LINKED_FRAME_MEMBER_CONNECTIVITY
            ],
            "fixed_global_dofs": [0, 1, 2, 6, 7, 8],
            "link_end_nodes": [1, 3],
            "link_component": "ux",
            "link_global_dofs": [
                LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF,
                LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF,
            ],
            "right_top_reference_load_kn": (LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN),
            "rotation_coordinate_scale_m": _COLUMN_HEIGHT_M,
        },
        "elastic_carrier_frame": {
            "section_profile": "steel_dominated_rc_protocol_elastic_carrier",
            "column_flexural_rigidity_kn_m2": (
                LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2
            ),
            "small_displacement_column_lateral_stiffness_kn_per_m": (
                LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M
            ),
            "member_state_evolution_count": carrier_member_state_evolution_count,
        },
        "link": {
            **problem.links[0].contract_payload()["material"],
            "plastic_consistent_tangent_kn_per_m": (
                problem.links[0].material.plastic_consistent_tangent_kn_per_m
            ),
        },
        "cyclic_load_factors": list(LINKED_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(LINKED_FRAME_CYCLIC_LOAD_FACTORS),
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
            "load_factor": LINKED_FRAME_CYCLIC_LOAD_FACTORS[0],
            "link_transfer_fraction": LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION,
            "analytic_link_force_kn": analytic_elastic_link_force,
            "observed_link_force_kn": elastic_step["link_force_kn"],
            "relative_error": elastic_link_force_relative_error,
            "relative_tolerance": 1.0e-4,
            "pass": elastic_link_force_relative_error <= 1.0e-4,
        },
        "same_parent_frame_link_tangent": tangent,
        "yielded_link_newton_quadratic_convergence": quadratic,
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_residual_inf_norm_tolerance_kn": (_MAXIMUM_RESIDUAL_INF_NORM_KN),
        "maximum_force_transfer_error_kn": maximum_force_transfer_error,
        "maximum_force_transfer_error_tolerance_kn": (_MAXIMUM_FORCE_TRANSFER_ERROR_KN),
        "maximum_link_compatibility_error_m": maximum_compatibility_error,
        "line_search_history_entry_count": line_search_history_entries,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "parent_link_state_hash": rollback_parent.link_states[0].state_hash,
            "parent_link_accumulated_plastic_deformation_m": (
                rollback_parent.link_states[0].accumulated_plastic_deformation_m
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
            "free_to_free_global_axis_translational_link": True,
            "state_updated_link_force_and_tangent_scatter": True,
            "cyclic_link_yield_reversal_and_nonnegative_dissipation": True,
            "atomic_frame_and_link_checkpoint_commit": True,
            "same_parent_frame_link_geometric_tangent": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "analytic_elastic_force_transfer_prefix": True,
            "inelastic_frame_member_and_link_interaction": False,
            "rotational_or_multi_axis_link_coupling": False,
            "local_axis_link_transformation": False,
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
            "rotational_and_multi_axis_link_coupling_not_implemented",
            "local_axis_link_transformation_not_implemented",
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
            STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY
        ),
    }


__all__ = [
    "LINKED_FRAME_COLUMN_FLEXURAL_RIGIDITY_KN_M2",
    "LINKED_FRAME_CYCLIC_LOAD_FACTORS",
    "LINKED_FRAME_ELASTIC_LINK_TRANSFER_FRACTION",
    "LINKED_FRAME_LEFT_TOP_HORIZONTAL_DOF",
    "LINKED_FRAME_MEMBER_CONNECTIVITY",
    "LINKED_FRAME_NEWTON_CONFIG",
    "LINKED_FRAME_NODE_COORDINATES_M",
    "LINKED_FRAME_REFERENCE_RIGHT_TOP_LOAD_KN",
    "LINKED_FRAME_RIGHT_TOP_HORIZONTAL_DOF",
    "LINKED_FRAME_SMALL_DISPLACEMENT_COLUMN_LATERAL_STIFFNESS_KN_PER_M",
    "STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_LINKED_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_linked_frame_cyclic_benchmark",
    "make_stateful_corotational_linked_frame_cyclic_problem",
]
