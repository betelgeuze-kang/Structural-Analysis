"""Bounded cyclic steel-concrete composite corotational-frame benchmark."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
    run_stateful_corotational_fiber_frame2d_load_path,
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.benchmark.stateful_corotational_fiber_frame2d_diagnostics import (
    finite_difference_stateful_corotational_fiber_frame2d_tangent_check,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageState,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    StatefulSectionFiber,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityState,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    assess_quadratic_convergence,
)


STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-composite-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_FORMULATION = (
    "two_member_euler_bernoulli_corotational_perfect_bond_steel_girder_"
    "concrete_slab_fiber_frame_with_material_plus_geometric_tangent"
)
STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded two-member planar cantilever with a "
    "perfect-bond reduced-fiber steel-girder and concrete-slab section. It "
    "exercises combined-hardening steel plasticity and independent concrete "
    "tension/compression damage in one section, cyclic reversal, constituent "
    "dissipation, same-parent material-plus-geometric tangents, deterministic "
    "Newton commits, and exact failed-step rollback. The deliberately low "
    "200 MPa steel yield stress and 8 MPa concrete compressive strength are "
    "benchmark parameters, not design-grade recommendations. This is not "
    "partial interaction, connector-slip or shear-transfer validation, local "
    "flange/web buckling, slab mesh-objectivity or fracture-energy evidence, "
    "multiaxial material validity, an external cyclic-member acceptance result, "
    "production sparse/ROCm/HIP execution, full-building equilibrium, G1 "
    "closure, or commercial readiness evidence."
)

COMPOSITE_FRAME_NODE_COORDINATES_M = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
COMPOSITE_FRAME_REFERENCE_TIP_LOAD_KN = -100.0
COMPOSITE_FRAME_TIP_VERTICAL_DOF = 7
COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS = (
    0.05,
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
    0.80,
    0.85,
    0.90,
    0.95,
    1.00,
    0.90,
    0.80,
    0.70,
    0.60,
    0.50,
    0.40,
    0.30,
    0.20,
    0.10,
    0.00,
    -0.10,
    -0.20,
    -0.30,
    -0.40,
    -0.50,
    -0.60,
    -0.70,
    -0.80,
    -0.90,
    -1.00,
    -0.90,
    -0.80,
    -0.70,
    -0.60,
    -0.50,
    -0.40,
    -0.30,
    -0.20,
    -0.10,
    0.00,
    0.10,
    0.20,
    0.30,
    0.40,
    0.50,
    0.60,
    0.70,
    0.80,
    0.90,
    1.00,
)

_CONCRETE_SLAB_WIDTH_M = 0.60
_CONCRETE_SLAB_THICKNESS_M = 0.12
_CONCRETE_SLAB_BOTTOM_Y_M = 0.15
_CONCRETE_SLAB_LAYER_COUNT = 8
_STEEL_GIRDER_DEPTH_M = 0.30
_STEEL_FLANGE_WIDTH_M = 0.18
_STEEL_FLANGE_THICKNESS_M = 0.015
_STEEL_WEB_THICKNESS_M = 0.008
_STEEL_WEB_LAYER_COUNT = 6
_STEEL_ELASTIC_MODULUS_MPA = 200_000.0
_STEEL_YIELD_STRESS_MPA = 200.0
_STEEL_ISOTROPIC_HARDENING_MODULUS_MPA = 3_000.0
_STEEL_KINEMATIC_HARDENING_MODULUS_MPA = 5_000.0
_CONCRETE_ELASTIC_MODULUS_MPA = 30_000.0
_CONCRETE_TENSILE_STRENGTH_MPA = 3.0
_CONCRETE_COMPRESSIVE_STRENGTH_MPA = 8.0
_CONCRETE_TENSILE_SOFTENING_RATE = 1_000.0
_CONCRETE_COMPRESSIVE_SOFTENING_RATE = 200.0
_TOTAL_CANTILEVER_LENGTH_M = 2.0
_MAXIMUM_RESIDUAL_INF_NORM_KN = 3.0e-8

COMPOSITE_FRAME_NEWTON_CONFIG = NewtonRaphsonConfig(
    residual_tolerance=1.0e-9,
    increment_tolerance=1.0e-12,
    max_iterations=60,
)


def _section_fibers() -> tuple[StatefulSectionFiber, ...]:
    concrete_layer_depth = _CONCRETE_SLAB_THICKNESS_M / _CONCRETE_SLAB_LAYER_COUNT
    fibers = [
        StatefulSectionFiber(
            fiber_id=f"concrete-slab-{index:02d}",
            y_m=(_CONCRETE_SLAB_BOTTOM_Y_M + (index + 0.5) * concrete_layer_depth),
            area_m2=_CONCRETE_SLAB_WIDTH_M * concrete_layer_depth,
            material_kind="concrete",
        )
        for index in range(_CONCRETE_SLAB_LAYER_COUNT)
    ]
    clear_web_depth = _STEEL_GIRDER_DEPTH_M - 2.0 * _STEEL_FLANGE_THICKNESS_M
    flange_y = 0.5 * _STEEL_GIRDER_DEPTH_M - 0.5 * _STEEL_FLANGE_THICKNESS_M
    fibers.append(
        StatefulSectionFiber(
            fiber_id="steel-bottom-flange",
            y_m=-flange_y,
            area_m2=_STEEL_FLANGE_WIDTH_M * _STEEL_FLANGE_THICKNESS_M,
            material_kind="steel",
        )
    )
    web_layer_depth = clear_web_depth / _STEEL_WEB_LAYER_COUNT
    for index in range(_STEEL_WEB_LAYER_COUNT):
        fibers.append(
            StatefulSectionFiber(
                fiber_id=f"steel-web-{index:02d}",
                y_m=(-0.5 * clear_web_depth + (index + 0.5) * web_layer_depth),
                area_m2=_STEEL_WEB_THICKNESS_M * web_layer_depth,
                material_kind="steel",
            )
        )
    fibers.append(
        StatefulSectionFiber(
            fiber_id="steel-top-flange",
            y_m=flange_y,
            area_m2=_STEEL_FLANGE_WIDTH_M * _STEEL_FLANGE_THICKNESS_M,
            material_kind="steel",
        )
    )
    return tuple(fibers)


_COMPOSITE_SECTION_FIBERS = _section_fibers()


def _elastic_section_properties() -> dict[str, float]:
    weighted_area = math.fsum(
        (
            _STEEL_ELASTIC_MODULUS_MPA
            if fiber.material_kind == "steel"
            else _CONCRETE_ELASTIC_MODULUS_MPA
        )
        * fiber.area_m2
        for fiber in _COMPOSITE_SECTION_FIBERS
    )
    centroid = (
        math.fsum(
            (
                _STEEL_ELASTIC_MODULUS_MPA
                if fiber.material_kind == "steel"
                else _CONCRETE_ELASTIC_MODULUS_MPA
            )
            * fiber.area_m2
            * fiber.y_m
            for fiber in _COMPOSITE_SECTION_FIBERS
        )
        / weighted_area
    )
    steel_ei = 1_000.0 * math.fsum(
        _STEEL_ELASTIC_MODULUS_MPA * fiber.area_m2 * (fiber.y_m - centroid) ** 2
        for fiber in _COMPOSITE_SECTION_FIBERS
        if fiber.material_kind == "steel"
    )
    concrete_ei = 1_000.0 * math.fsum(
        _CONCRETE_ELASTIC_MODULUS_MPA * fiber.area_m2 * (fiber.y_m - centroid) ** 2
        for fiber in _COMPOSITE_SECTION_FIBERS
        if fiber.material_kind == "concrete"
    )
    return {
        "elastic_axial_rigidity_kn": 1_000.0 * weighted_area,
        "elastic_centroid_y_m": centroid,
        "steel_flexural_rigidity_kn_m2": steel_ei,
        "concrete_flexural_rigidity_kn_m2": concrete_ei,
        "elastic_flexural_rigidity_kn_m2": steel_ei + concrete_ei,
        "initial_steel_flexural_rigidity_fraction": steel_ei / (steel_ei + concrete_ei),
        "initial_concrete_flexural_rigidity_fraction": concrete_ei
        / (steel_ei + concrete_ei),
    }


_ELASTIC_SECTION_PROPERTIES = _elastic_section_properties()
COMPOSITE_FRAME_ELASTIC_AXIAL_RIGIDITY_KN = _ELASTIC_SECTION_PROPERTIES[
    "elastic_axial_rigidity_kn"
]
COMPOSITE_FRAME_ELASTIC_CENTROID_Y_M = _ELASTIC_SECTION_PROPERTIES[
    "elastic_centroid_y_m"
]
COMPOSITE_FRAME_STEEL_FLEXURAL_RIGIDITY_KN_M2 = _ELASTIC_SECTION_PROPERTIES[
    "steel_flexural_rigidity_kn_m2"
]
COMPOSITE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2 = _ELASTIC_SECTION_PROPERTIES[
    "concrete_flexural_rigidity_kn_m2"
]
COMPOSITE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 = _ELASTIC_SECTION_PROPERTIES[
    "elastic_flexural_rigidity_kn_m2"
]
COMPOSITE_FRAME_INITIAL_STEEL_FLEXURAL_RIGIDITY_FRACTION = _ELASTIC_SECTION_PROPERTIES[
    "initial_steel_flexural_rigidity_fraction"
]
COMPOSITE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION = (
    _ELASTIC_SECTION_PROPERTIES["initial_concrete_flexural_rigidity_fraction"]
)


def _make_composite_section(section_id: str) -> StatefulRCFiberSection:
    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=_STEEL_ELASTIC_MODULUS_MPA,
        yield_stress_mpa=_STEEL_YIELD_STRESS_MPA,
        isotropic_hardening_modulus_mpa=(_STEEL_ISOTROPIC_HARDENING_MODULUS_MPA),
        kinematic_hardening_modulus_mpa=(_STEEL_KINEMATIC_HARDENING_MODULUS_MPA),
        material_id="composite-girder-combined-hardening-steel",
    )
    concrete = AsymmetricConcreteDamageMaterial(
        elastic_modulus_mpa=_CONCRETE_ELASTIC_MODULUS_MPA,
        tensile_strength_mpa=_CONCRETE_TENSILE_STRENGTH_MPA,
        compressive_strength_mpa=_CONCRETE_COMPRESSIVE_STRENGTH_MPA,
        tensile_softening_rate=_CONCRETE_TENSILE_SOFTENING_RATE,
        compressive_softening_rate=_CONCRETE_COMPRESSIVE_SOFTENING_RATE,
        material_id="composite-slab-asymmetric-damage-concrete",
    )
    return StatefulRCFiberSection(
        fibers=_COMPOSITE_SECTION_FIBERS,
        steel=steel,
        concrete=concrete,
        section_id=section_id,
    )


def make_stateful_corotational_composite_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DProblem
):
    """Create the deterministic perfect-bond composite cantilever."""

    members: list[StatefulCorotationalFiberFrame2DMember] = []
    for member_index, (node_i, node_j) in enumerate(((0, 1), (1, 2)), start=1):
        member_id = f"composite-cyclic-member-{member_index}"
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        COMPOSITE_FRAME_NODE_COORDINATES_M[node_i],
                        COMPOSITE_FRAME_NODE_COORDINATES_M[node_j],
                    ),
                    section=_make_composite_section(
                        f"composite-cyclic-section-{member_index}"
                    ),
                    integration_order=3,
                    element_id=member_id,
                ),
            )
        )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="stateful-corotational-composite-frame-cyclic",
        node_coordinates_m=COMPOSITE_FRAME_NODE_COORDINATES_M,
        members=tuple(members),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=(
            (
                COMPOSITE_FRAME_TIP_VERTICAL_DOF,
                COMPOSITE_FRAME_REFERENCE_TIP_LOAD_KN,
            ),
        ),
        rotation_coordinate_scale_m=_TOTAL_CANTILEVER_LENGTH_M,
    )


def _checkpoint_material_states(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> tuple[tuple[ConcreteDamageState, ...], tuple[UniaxialPlasticityState, ...]]:
    concrete_states: list[ConcreteDamageState] = []
    steel_states: list[UniaxialPlasticityState] = []
    for member, element_state in zip(
        problem.members,
        checkpoint.element_states,
        strict=True,
    ):
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            raise ValueError("benchmark section must be StatefulRCFiberSection")
        for section_state in element_state.basic_beam_state.integration_point_states:
            for fiber, state in zip(
                section.fibers,
                section_state.fiber_states,
                strict=True,
            ):
                if fiber.material_kind == "concrete":
                    if type(state) is not ConcreteDamageState:
                        raise ValueError("concrete fiber state type is invalid")
                    concrete_states.append(state)
                else:
                    if type(state) is not UniaxialPlasticityState:
                        raise ValueError("steel fiber state type is invalid")
                    steel_states.append(state)
    return tuple(concrete_states), tuple(steel_states)


def _checkpoint_material_summary(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> dict[str, Any]:
    concrete_states, steel_states = _checkpoint_material_states(problem, checkpoint)
    return {
        "concrete_fiber_state_count": len(concrete_states),
        "steel_fiber_state_count": len(steel_states),
        "tensile_damaged_concrete_state_count": sum(
            state.tensile_damage > 0.0 for state in concrete_states
        ),
        "compressive_damaged_concrete_state_count": sum(
            state.compressive_damage > 0.0 for state in concrete_states
        ),
        "plastified_steel_state_count": sum(
            state.accumulated_plastic_strain > 0.0 for state in steel_states
        ),
        "maximum_tensile_damage": max(
            (state.tensile_damage for state in concrete_states),
            default=0.0,
        ),
        "maximum_compressive_damage": max(
            (state.compressive_damage for state in concrete_states),
            default=0.0,
        ),
        "maximum_concrete_dissipated_energy_density_mj_per_m3": max(
            (state.dissipated_energy_density_mj_per_m3 for state in concrete_states),
            default=0.0,
        ),
        "maximum_steel_accumulated_plastic_strain": max(
            (state.accumulated_plastic_strain for state in steel_states),
            default=0.0,
        ),
        "maximum_steel_dissipated_energy_density_mj_per_m3": max(
            (state.dissipated_energy_density_mj_per_m3 for state in steel_states),
            default=0.0,
        ),
    }


def _checkpoint_dissipated_energy_components_mj(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> dict[str, float]:
    steel_energy = 0.0
    concrete_energy = 0.0
    direct_total = 0.0
    for member, element_state in zip(
        problem.members,
        checkpoint.element_states,
        strict=True,
    ):
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            raise ValueError("benchmark section must be StatefulRCFiberSection")
        _, weights = member.element.basic_beam.quadrature
        jacobian = 0.5 * member.element.initial_length_m
        for weight, section_state in zip(
            weights,
            element_state.basic_beam_state.integration_point_states,
            strict=True,
        ):
            for fiber, state in zip(
                section.fibers,
                section_state.fiber_states,
                strict=True,
            ):
                energy = (
                    float(weight)
                    * jacobian
                    * fiber.area_m2
                    * state.dissipated_energy_density_mj_per_m3
                )
                if fiber.material_kind == "steel":
                    steel_energy += energy
                else:
                    concrete_energy += energy
        direct_total += member.element.dissipated_energy_mj(element_state)
    total = steel_energy + concrete_energy
    return {
        "steel_mj": steel_energy,
        "concrete_mj": concrete_energy,
        "total_mj": total,
        "direct_total_mj": direct_total,
        "component_sum_error_mj": abs(total - direct_total),
    }


def _material_increment_counts(
    problem: StatefulCorotationalFiberFrame2DProblem,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    accepted: StatefulCorotationalFiberFrame2DCheckpoint,
) -> dict[str, int]:
    parent_concrete, parent_steel = _checkpoint_material_states(problem, parent)
    accepted_concrete, accepted_steel = _checkpoint_material_states(problem, accepted)
    if len(parent_concrete) != len(accepted_concrete) or len(parent_steel) != len(
        accepted_steel
    ):
        raise ValueError("material state count changed across a step")
    return {
        "tensile_damage_increment_state_count": sum(
            child.tensile_damage > prior.tensile_damage + 1.0e-15
            for prior, child in zip(
                parent_concrete,
                accepted_concrete,
                strict=True,
            )
        ),
        "compressive_damage_increment_state_count": sum(
            child.compressive_damage > prior.compressive_damage + 1.0e-15
            for prior, child in zip(
                parent_concrete,
                accepted_concrete,
                strict=True,
            )
        ),
        "steel_plastic_increment_state_count": sum(
            child.accumulated_plastic_strain
            > prior.accumulated_plastic_strain + 1.0e-15
            for prior, child in zip(parent_steel, accepted_steel, strict=True)
        ),
    }


def _material_irreversibility_exact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps),
    )
    for parent, child in zip(checkpoints, checkpoints[1:]):
        parent_concrete, parent_steel = _checkpoint_material_states(problem, parent)
        child_concrete, child_steel = _checkpoint_material_states(problem, child)
        if any(
            current.tensile_damage + 1.0e-15 < prior.tensile_damage
            or current.compressive_damage + 1.0e-15 < prior.compressive_damage
            or current.dissipated_energy_density_mj_per_m3 + 1.0e-15
            < prior.dissipated_energy_density_mj_per_m3
            for prior, current in zip(
                parent_concrete,
                child_concrete,
                strict=True,
            )
        ):
            return False
        if any(
            current.accumulated_plastic_strain + 1.0e-15
            < prior.accumulated_plastic_strain
            or current.dissipated_energy_density_mj_per_m3 + 1.0e-15
            < prior.dissipated_energy_density_mj_per_m3
            for prior, current in zip(parent_steel, child_steel, strict=True)
        ):
            return False
    return True


def _path_ancestry_exact(path: StatefulCorotationalFiberFrame2DLoadPathResult) -> bool:
    parent = path.initial_checkpoint
    for step in path.steps:
        if (
            step.parent_checkpoint.state_hash != parent.state_hash
            or step.accepted_checkpoint.parent_state_hash != parent.state_hash
        ):
            return False
        parent = step.accepted_checkpoint
    return parent.state_hash == path.final_checkpoint.state_hash


def _step_receipts(
    problem: StatefulCorotationalFiberFrame2DProblem,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step_index, (load_factor, step) in enumerate(
        zip(COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS, path.steps, strict=True),
        start=1,
    ):
        rows.append(
            {
                "step_index": step_index,
                "target_load_factor": load_factor,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "tip_vertical_displacement_m": (
                    step.accepted_checkpoint.global_displacements[
                        COMPOSITE_FRAME_TIP_VERTICAL_DOF
                    ]
                ),
                "dissipated_energy": (
                    _checkpoint_dissipated_energy_components_mj(
                        problem,
                        step.accepted_checkpoint,
                    )
                ),
                **_material_increment_counts(
                    problem,
                    step.parent_checkpoint,
                    step.accepted_checkpoint,
                ),
                "material_state": _checkpoint_material_summary(
                    problem,
                    step.accepted_checkpoint,
                ),
                "yielded_member_count": step.metrics["yielded_member_count"],
                "damaged_member_count": step.metrics["damaged_member_count"],
                "residual_inf_norm_kn": float(
                    np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf)
                ),
                "relative_residual": step.trial_solution.metrics["relative_residual"],
                "iteration_count": step.trial_solution.metrics["iteration_count"],
                "line_search_used": step.trial_solution.metrics["line_search_used"],
                "line_search_history_entry_count": len(
                    step.trial_solution.line_search_history
                ),
                "regularization_used": step.metrics["regularization_used"],
                "fallback_used": step.metrics["fallback_used"],
            }
        )
    return rows


def _monotonic(values: list[float]) -> bool:
    return all(
        following + 1.0e-15 >= previous
        for previous, following in zip(values, values[1:])
    )


def _assess_pre_roundoff_quadratic_convergence(
    convergence_history: list[dict[str, Any]],
    *,
    relative_residual_floor: float = 1.0e-7,
) -> dict[str, Any]:
    """Assess full-step order through the first point at the numerical floor."""

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


def build_stateful_corotational_composite_frame_cyclic_benchmark() -> dict[str, Any]:
    """Build the deterministic perfect-bond composite frame receipt."""

    problem = make_stateful_corotational_composite_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS,
        config=COMPOSITE_FRAME_NEWTON_CONFIG,
    )
    replay = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS,
        config=COMPOSITE_FRAME_NEWTON_CONFIG,
    )
    steps = _step_receipts(problem, path)

    tensile_damage_steps = [
        int(row["step_index"])
        for row in steps
        if int(row["tensile_damage_increment_state_count"]) > 0
    ]
    compressive_damage_steps = [
        int(row["step_index"])
        for row in steps
        if int(row["compressive_damage_increment_state_count"]) > 0
    ]
    steel_plastic_steps = [
        int(row["step_index"])
        for row in steps
        if int(row["steel_plastic_increment_state_count"]) > 0
    ]
    simultaneous_steps = sorted(
        set(steel_plastic_steps).intersection(tensile_damage_steps)
    )
    if not simultaneous_steps or not compressive_damage_steps:
        raise ValueError(
            "benchmark path did not exercise mixed plastic-damage and compression states"
        )

    simultaneous_step_index = simultaneous_steps[0]
    simultaneous_step = path.steps[simultaneous_step_index - 1]
    simultaneous_parent = path.steps[simultaneous_step_index - 2].accepted_checkpoint
    simultaneous_tangent = (
        finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
            problem,
            simultaneous_parent,
            target_load_factor=COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS[
                simultaneous_step_index - 1
            ],
            trial_free_coordinates_m=(
                simultaneous_step.trial_solution.free_displacements_m
            ),
        )
    )
    simultaneous_quadratic = _assess_pre_roundoff_quadratic_convergence(
        list(simultaneous_step.trial_solution.convergence_history),
    )

    compression_step_index = compressive_damage_steps[0]
    compression_step = path.steps[compression_step_index - 1]
    compression_parent = path.steps[compression_step_index - 2].accepted_checkpoint
    compression_tangent = finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
        problem,
        compression_parent,
        target_load_factor=COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS[
            compression_step_index - 1
        ],
        trial_free_coordinates_m=compression_step.trial_solution.free_displacements_m,
    )

    energy_histories = {
        name: [0.0, *(float(row["dissipated_energy"][name]) for row in steps)]
        for name in ("steel_mj", "concrete_mj", "total_mj")
    }
    energy_monotonic = {
        name: _monotonic(values) for name, values in energy_histories.items()
    }
    maximum_energy_component_sum_error = max(
        float(row["dissipated_energy"]["component_sum_error_mj"]) for row in steps
    )
    final_material = _checkpoint_material_summary(problem, path.final_checkpoint)
    deterministic_replay = bool(
        path.to_dict() == replay.to_dict()
        and path.final_checkpoint.canonical_bytes()
        == replay.final_checkpoint.canonical_bytes()
    )
    material_irreversible = _material_irreversibility_exact(problem, path)
    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    fallback_count = sum(bool(row["fallback_used"]) for row in steps)
    regularization_count = sum(bool(row["regularization_used"]) for row in steps)
    line_search_history_entries = sum(
        int(row["line_search_history_entry_count"]) for row in steps
    )

    first_inelastic_step = min(tensile_damage_steps[0], steel_plastic_steps[0])
    elastic_prefix_step_count = first_inelastic_step - 1
    elastic_prefix_state = steps[elastic_prefix_step_count - 1]["material_state"]
    elastic_prefix_no_state_evolution = bool(
        elastic_prefix_state["tensile_damaged_concrete_state_count"] == 0
        and elastic_prefix_state["compressive_damaged_concrete_state_count"] == 0
        and elastic_prefix_state["plastified_steel_state_count"] == 0
    )
    reversal_dissipation_growth = bool(
        steps[39]["dissipated_energy"]["total_mj"]
        > steps[19]["dissipated_energy"]["total_mj"]
        > 0.0
        and steps[-1]["dissipated_energy"]["total_mj"]
        >= steps[39]["dissipated_energy"]["total_mj"]
    )

    rollback_parent = path.steps[15].accepted_checkpoint
    rollback_parent_bytes = rollback_parent.canonical_bytes()
    failed = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        rollback_parent,
        target_load_factor=1.0,
        config=NewtonRaphsonConfig(max_iterations=0),
    )
    rollback_exact = bool(
        failed.status == "blocked"
        and failed.committed is False
        and failed.accepted_checkpoint is rollback_parent
        and failed.accepted_checkpoint.canonical_bytes() == rollback_parent_bytes
        and failed.metrics["rollback_exact"] is True
        and failed.metrics["yielded_member_count"] > 0
        and failed.metrics["damaged_member_count"] > 0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )

    contract_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS)
        and _path_ancestry_exact(path)
        and deterministic_replay
        and material_irreversible
        and all(energy_monotonic.values())
        and energy_histories["steel_mj"][-1] > 0.0
        and energy_histories["concrete_mj"][-1] > 0.0
        and reversal_dissipation_growth
        and maximum_energy_component_sum_error <= 1.0e-15
        and final_material["maximum_steel_accumulated_plastic_strain"] > 0.0
        and final_material["maximum_steel_dissipated_energy_density_mj_per_m3"] > 0.0
        and final_material["maximum_tensile_damage"] > 0.0
        and final_material["maximum_compressive_damage"] > 0.0
        and final_material["maximum_concrete_dissipated_energy_density_mj_per_m3"] > 0.0
        and simultaneous_tangent["pass"] is True
        and simultaneous_tangent["yielded_member_count"] > 0
        and simultaneous_tangent["damaged_member_count"] > 0
        and compression_tangent["pass"] is True
        and compression_tangent["damaged_member_count"] > 0
        and simultaneous_quadratic["pass"] is True
        and elastic_prefix_no_state_evolution
        and maximum_residual <= _MAXIMUM_RESIDUAL_INF_NORM_KN
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rollback_exact
    )

    return {
        "schema_version": (STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_SCHEMA_VERSION),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "analysis_type": "stateful_corotational_composite_frame_cyclic_benchmark",
        "formulation": STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_FORMULATION,
        "assembly_contract": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "section": {
            "profile": "perfect_bond_reduced_fiber_steel_girder_concrete_slab",
            "steel_fiber_count": sum(
                fiber.material_kind == "steel" for fiber in _COMPOSITE_SECTION_FIBERS
            ),
            "concrete_fiber_count": sum(
                fiber.material_kind == "concrete" for fiber in _COMPOSITE_SECTION_FIBERS
            ),
            "concrete_slab_width_m": _CONCRETE_SLAB_WIDTH_M,
            "concrete_slab_thickness_m": _CONCRETE_SLAB_THICKNESS_M,
            "steel_girder_depth_m": _STEEL_GIRDER_DEPTH_M,
            "steel_flange_width_m": _STEEL_FLANGE_WIDTH_M,
            "steel_flange_thickness_m": _STEEL_FLANGE_THICKNESS_M,
            "steel_web_thickness_m": _STEEL_WEB_THICKNESS_M,
            **_ELASTIC_SECTION_PROPERTIES,
        },
        "steel_material": {
            "elastic_modulus_mpa": _STEEL_ELASTIC_MODULUS_MPA,
            "yield_stress_mpa": _STEEL_YIELD_STRESS_MPA,
            "isotropic_hardening_modulus_mpa": (_STEEL_ISOTROPIC_HARDENING_MODULUS_MPA),
            "kinematic_hardening_modulus_mpa": (_STEEL_KINEMATIC_HARDENING_MODULUS_MPA),
        },
        "concrete_material": {
            "elastic_modulus_mpa": _CONCRETE_ELASTIC_MODULUS_MPA,
            "tensile_strength_mpa": _CONCRETE_TENSILE_STRENGTH_MPA,
            "compressive_strength_mpa": _CONCRETE_COMPRESSIVE_STRENGTH_MPA,
            "tensile_softening_rate": _CONCRETE_TENSILE_SOFTENING_RATE,
            "compressive_softening_rate": _CONCRETE_COMPRESSIVE_SOFTENING_RATE,
            "independent_tension_compression_history": True,
        },
        "newton_config": {
            "residual_tolerance": COMPOSITE_FRAME_NEWTON_CONFIG.residual_tolerance,
            "increment_tolerance": COMPOSITE_FRAME_NEWTON_CONFIG.increment_tolerance,
            "max_iterations": COMPOSITE_FRAME_NEWTON_CONFIG.max_iterations,
        },
        "cyclic_load_factors": list(COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS),
        "committed_step_count": sum(step.committed for step in path.steps),
        "path_ancestry_exact": _path_ancestry_exact(path),
        "deterministic_replay_exact": deterministic_replay,
        "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
        "final_checkpoint_hash": path.final_checkpoint.state_hash,
        "elastic_prefix": {
            "step_count": elastic_prefix_step_count,
            "no_material_state_evolution": elastic_prefix_no_state_evolution,
        },
        "material_history": {
            "irreversible": material_irreversible,
            "tensile_damage_evolution_step_indices": tensile_damage_steps,
            "compressive_damage_evolution_step_indices": compressive_damage_steps,
            "steel_plastic_evolution_step_indices": steel_plastic_steps,
            "simultaneous_steel_plastic_concrete_damage_step_indices": (
                simultaneous_steps
            ),
            "final_material_state": final_material,
        },
        "dissipation": {
            "steel_nonnegative_monotonic": energy_monotonic["steel_mj"],
            "concrete_nonnegative_monotonic": energy_monotonic["concrete_mj"],
            "total_nonnegative_monotonic": energy_monotonic["total_mj"],
            "reversal_growth": reversal_dissipation_growth,
            "final_steel_mj": energy_histories["steel_mj"][-1],
            "final_concrete_mj": energy_histories["concrete_mj"][-1],
            "final_total_mj": energy_histories["total_mj"][-1],
            "maximum_component_sum_error_mj": maximum_energy_component_sum_error,
        },
        "same_parent_simultaneous_mixed_tangent": simultaneous_tangent,
        "same_parent_compression_damage_after_plastic_history_tangent": (
            compression_tangent
        ),
        "first_simultaneous_mixed_newton_quadratic_convergence": (
            simultaneous_quadratic
        ),
        "maximum_residual_inf_norm_kn": maximum_residual,
        "maximum_residual_inf_norm_tolerance_kn": (_MAXIMUM_RESIDUAL_INF_NORM_KN),
        "line_search_history_entry_count": line_search_history_entries,
        "line_search_used_step_count": sum(
            bool(row["line_search_used"]) for row in steps
        ),
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "steps": steps,
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "target_load_factor": 1.0,
            "status": failed.status,
            "terminal_reason": failed.metrics["terminal_reason"],
            "trial_yielded_member_count": failed.metrics["yielded_member_count"],
            "trial_damaged_member_count": failed.metrics["damaged_member_count"],
            "accepted_checkpoint_hash_after": failed.accepted_checkpoint.state_hash,
            "exact": rollback_exact,
        },
        "claims": {
            "bounded_two_member_corotational_fiber_frame": True,
            "perfect_bond_steel_girder_concrete_slab_section": True,
            "simultaneous_steel_plasticity_and_concrete_damage": True,
            "cyclic_constituent_dissipation": True,
            "same_parent_material_plus_geometric_tangent": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "general_composite_section_breadth": False,
            "partial_interaction_or_connector_slip": False,
            "composite_shear_transfer_validation": False,
            "local_buckling_or_fracture": False,
            "mesh_objectivity_or_fracture_energy_regularization": False,
            "multiaxial_material_validity": False,
            "external_cyclic_member_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "partial_interaction_connector_slip_not_implemented",
            "composite_shear_transfer_not_validated",
            "local_flange_web_buckling_not_implemented",
            "slab_crack_band_fracture_energy_regularization_not_implemented",
            "mesh_objectivity_not_established",
            "multiaxial_material_models_not_implemented",
            "external_composite_cyclic_reference_not_attached",
            "three_dimensional_composite_frame_integration_not_closed",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_material_newton_breadth_not_closed",
        ],
        "claim_boundary": (STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_CLAIM_BOUNDARY),
    }


__all__ = [
    "COMPOSITE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2",
    "COMPOSITE_FRAME_CYCLIC_LOAD_FACTORS",
    "COMPOSITE_FRAME_ELASTIC_AXIAL_RIGIDITY_KN",
    "COMPOSITE_FRAME_ELASTIC_CENTROID_Y_M",
    "COMPOSITE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2",
    "COMPOSITE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION",
    "COMPOSITE_FRAME_INITIAL_STEEL_FLEXURAL_RIGIDITY_FRACTION",
    "COMPOSITE_FRAME_NEWTON_CONFIG",
    "COMPOSITE_FRAME_NODE_COORDINATES_M",
    "COMPOSITE_FRAME_REFERENCE_TIP_LOAD_KN",
    "COMPOSITE_FRAME_STEEL_FLEXURAL_RIGIDITY_KN_M2",
    "COMPOSITE_FRAME_TIP_VERTICAL_DOF",
    "STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_COMPOSITE_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_composite_frame_cyclic_benchmark",
    "make_stateful_corotational_composite_frame_cyclic_problem",
]
