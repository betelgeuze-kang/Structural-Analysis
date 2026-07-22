"""Bounded cyclic concrete-damage benchmark on a corotational fiber frame."""

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
    make_rectangular_stateful_rc_fiber_section,
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


STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-concrete-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_FORMULATION = (
    "two_member_euler_bernoulli_corotational_fiber_frame_with_"
    "small_strain_asymmetric_concrete_damage_elastic_reinforcement_and_"
    "material_plus_geometric_tangent"
)
STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded two-member planar cantilever with "
    "small-strain asymmetric tension/compression concrete damage, cyclic "
    "reversal, nonnegative damage dissipation, same-parent material-plus-"
    "geometric tangents, deterministic Newton commits, and exact failed-step "
    "rollback. High-strength elastic reinforcement stabilizes the post-cracking "
    "path while concrete supplies more than 75 percent of the initial flexural "
    "rigidity. This is not a pure-concrete section, crack-band or fracture-energy "
    "regularization, mesh-objectivity evidence, multiaxial concrete validity, "
    "external cyclic-member acceptance, production sparse/ROCm/HIP execution, "
    "full-building equilibrium, G1 closure, or commercial readiness evidence."
)

CONCRETE_FRAME_NODE_COORDINATES_M = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
CONCRETE_FRAME_REFERENCE_TIP_LOAD_KN = -100.0
CONCRETE_FRAME_TIP_VERTICAL_DOF = 7
CONCRETE_FRAME_CYCLIC_LOAD_FACTORS = (
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

_SECTION_WIDTH_M = 0.2
_SECTION_DEPTH_M = 0.4
_SECTION_COVER_M = 0.04
_CONCRETE_LAYER_COUNT = 8
_BAR_COUNT_PER_FACE = 2
_BAR_AREA_M2 = 5.0e-4
_STEEL_ELASTIC_MODULUS_MPA = 200_000.0
_STEEL_ELASTIC_YIELD_STRESS_MPA = 1.0e12
_TOTAL_CANTILEVER_LENGTH_M = 2.0


def _elastic_flexural_rigidity_components() -> tuple[float, float]:
    layer_depth = _SECTION_DEPTH_M / _CONCRETE_LAYER_COUNT
    layer_area = _SECTION_WIDTH_M * layer_depth
    layer_ys = tuple(
        -0.5 * _SECTION_DEPTH_M + (index + 0.5) * layer_depth
        for index in range(_CONCRETE_LAYER_COUNT)
    )
    concrete_second_moment_m4 = math.fsum(layer_area * y**2 for y in layer_ys)
    bar_y = 0.5 * _SECTION_DEPTH_M - _SECTION_COVER_M
    reinforcement_second_moment_m4 = 2 * _BAR_COUNT_PER_FACE * _BAR_AREA_M2 * bar_y**2
    concrete = 1_000.0 * 30_000.0 * concrete_second_moment_m4
    reinforcement = (
        1_000.0 * _STEEL_ELASTIC_MODULUS_MPA * reinforcement_second_moment_m4
    )
    return concrete, reinforcement


(
    CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2,
    CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2,
) = _elastic_flexural_rigidity_components()
CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 = (
    CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2
    + CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2
)
CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION = (
    CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2
    / CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2
)


def make_stateful_corotational_concrete_frame_cyclic_problem() -> (
    StatefulCorotationalFiberFrame2DProblem
):
    """Create the deterministic concrete-dominated two-member cantilever."""

    concrete = AsymmetricConcreteDamageMaterial(
        material_id="concrete-asymmetric-damage-frame",
    )
    elastic_reinforcement = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=_STEEL_ELASTIC_MODULUS_MPA,
        yield_stress_mpa=_STEEL_ELASTIC_YIELD_STRESS_MPA,
        isotropic_hardening_modulus_mpa=1.0,
        kinematic_hardening_modulus_mpa=0.0,
        material_id="elastic-reinforcement-stabilizer",
    )
    members: list[StatefulCorotationalFiberFrame2DMember] = []
    for member_index, (node_i, node_j) in enumerate(((0, 1), (1, 2)), start=1):
        member_id = f"concrete-cyclic-member-{member_index}"
        section = make_rectangular_stateful_rc_fiber_section(
            width_m=_SECTION_WIDTH_M,
            depth_m=_SECTION_DEPTH_M,
            cover_m=_SECTION_COVER_M,
            concrete_layer_count=_CONCRETE_LAYER_COUNT,
            top_bar_count=_BAR_COUNT_PER_FACE,
            bottom_bar_count=_BAR_COUNT_PER_FACE,
            bar_area_m2=_BAR_AREA_M2,
            section_id=f"concrete-cyclic-section-{member_index}",
            steel=elastic_reinforcement,
            concrete=concrete,
        )
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        CONCRETE_FRAME_NODE_COORDINATES_M[node_i],
                        CONCRETE_FRAME_NODE_COORDINATES_M[node_j],
                    ),
                    section=section,
                    integration_order=3,
                    element_id=member_id,
                ),
            )
        )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="stateful-corotational-concrete-frame-cyclic",
        node_coordinates_m=CONCRETE_FRAME_NODE_COORDINATES_M,
        members=tuple(members),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=(
            (
                CONCRETE_FRAME_TIP_VERTICAL_DOF,
                CONCRETE_FRAME_REFERENCE_TIP_LOAD_KN,
            ),
        ),
        rotation_coordinate_scale_m=_TOTAL_CANTILEVER_LENGTH_M,
    )


def _checkpoint_dissipated_energy_mj(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> float:
    return math.fsum(
        member.element.dissipated_energy_mj(state)
        for member, state in zip(
            problem.members,
            checkpoint.element_states,
            strict=True,
        )
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


def _damage_increment_counts(
    problem: StatefulCorotationalFiberFrame2DProblem,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    accepted: StatefulCorotationalFiberFrame2DCheckpoint,
) -> dict[str, int]:
    parent_states, _ = _checkpoint_material_states(problem, parent)
    accepted_states, _ = _checkpoint_material_states(problem, accepted)
    if len(parent_states) != len(accepted_states):
        raise ValueError("concrete state count changed across a step")
    return {
        "tensile_damage_increment_state_count": sum(
            child.tensile_damage > prior.tensile_damage + 1.0e-15
            for prior, child in zip(parent_states, accepted_states, strict=True)
        ),
        "compressive_damage_increment_state_count": sum(
            child.compressive_damage > prior.compressive_damage + 1.0e-15
            for prior, child in zip(parent_states, accepted_states, strict=True)
        ),
    }


def _damage_irreversibility_exact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    path: StatefulCorotationalFiberFrame2DLoadPathResult,
) -> bool:
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps),
    )
    for parent, child in zip(checkpoints, checkpoints[1:]):
        parent_states, _ = _checkpoint_material_states(problem, parent)
        child_states, _ = _checkpoint_material_states(problem, child)
        if len(parent_states) != len(child_states):
            return False
        if any(
            current.tensile_damage + 1.0e-15 < prior.tensile_damage
            or current.compressive_damage + 1.0e-15 < prior.compressive_damage
            for prior, current in zip(parent_states, child_states, strict=True)
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
        zip(CONCRETE_FRAME_CYCLIC_LOAD_FACTORS, path.steps, strict=True),
        start=1,
    ):
        rows.append(
            {
                "step_index": step_index,
                "target_load_factor": load_factor,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "tip_vertical_displacement_m": (
                    step.accepted_checkpoint.global_displacements[
                        CONCRETE_FRAME_TIP_VERTICAL_DOF
                    ]
                ),
                "dissipated_energy_mj": _checkpoint_dissipated_energy_mj(
                    problem,
                    step.accepted_checkpoint,
                ),
                **_damage_increment_counts(
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


def build_stateful_corotational_concrete_frame_cyclic_benchmark() -> dict[str, Any]:
    """Build the deterministic asymmetric concrete-damage frame receipt."""

    problem = make_stateful_corotational_concrete_frame_cyclic_problem()
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        CONCRETE_FRAME_CYCLIC_LOAD_FACTORS,
    )
    replay = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        CONCRETE_FRAME_CYCLIC_LOAD_FACTORS,
    )
    steps = _step_receipts(problem, path)
    energy_history = [0.0, *(row["dissipated_energy_mj"] for row in steps)]
    dissipation_monotonic = all(
        following + 1.0e-15 >= previous
        for previous, following in zip(energy_history, energy_history[1:])
    )
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
    positive_compressive_damage_steps = [
        index
        for index in compressive_damage_steps
        if CONCRETE_FRAME_CYCLIC_LOAD_FACTORS[index - 1] > 0.0
    ]
    reverse_compressive_damage_steps = [
        index
        for index in compressive_damage_steps
        if CONCRETE_FRAME_CYCLIC_LOAD_FACTORS[index - 1] < 0.0
    ]
    damage_steps = [
        int(row["step_index"]) for row in steps if int(row["damaged_member_count"]) > 0
    ]
    if not damage_steps or not compressive_damage_steps:
        raise ValueError("benchmark path did not exercise both damage branches")

    first_damage_step_index = min(damage_steps)
    first_damage_step = path.steps[first_damage_step_index - 1]
    first_damage_quadratic = assess_quadratic_convergence(
        list(first_damage_step.trial_solution.convergence_history),
        minimum_observed_order=1.8,
        minimum_order_sample_count=1,
    )

    first_compressive_damage_step_index = min(compressive_damage_steps)
    tangent_parent = path.steps[
        first_compressive_damage_step_index - 2
    ].accepted_checkpoint
    tangent_step = path.steps[first_compressive_damage_step_index - 1]
    tangent = finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
        problem,
        tangent_parent,
        target_load_factor=CONCRETE_FRAME_CYCLIC_LOAD_FACTORS[
            first_compressive_damage_step_index - 1
        ],
        trial_free_coordinates_m=tangent_step.trial_solution.free_displacements_m,
    )

    final_material = _checkpoint_material_summary(problem, path.final_checkpoint)
    deterministic_replay = bool(
        path.to_dict() == replay.to_dict()
        and path.final_checkpoint.canonical_bytes()
        == replay.final_checkpoint.canonical_bytes()
    )
    damage_irreversible = _damage_irreversibility_exact(problem, path)
    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    fallback_count = sum(bool(row["fallback_used"]) for row in steps)
    regularization_count = sum(bool(row["regularization_used"]) for row in steps)
    line_search_history_entries = sum(
        int(row["line_search_history_entry_count"]) for row in steps
    )

    elastic_step = steps[0]
    elastic_reference_tip_displacement_m = (
        CONCRETE_FRAME_REFERENCE_TIP_LOAD_KN
        * CONCRETE_FRAME_CYCLIC_LOAD_FACTORS[0]
        * _TOTAL_CANTILEVER_LENGTH_M**3
        / (3.0 * CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2)
    )
    elastic_reference_relative_error = abs(
        float(elastic_step["tip_vertical_displacement_m"])
        - elastic_reference_tip_displacement_m
    ) / abs(elastic_reference_tip_displacement_m)
    reversal_dissipation_growth = bool(
        steps[19]["dissipated_energy_mj"] > steps[9]["dissipated_energy_mj"] > 0.0
        and steps[-1]["dissipated_energy_mj"] >= steps[19]["dissipated_energy_mj"]
    )

    rollback_parent = path.steps[8].accepted_checkpoint
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
        and failed.metrics["damaged_member_count"] > 0
        and failed.metrics["yielded_member_count"] == 0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )

    contract_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(CONCRETE_FRAME_CYCLIC_LOAD_FACTORS)
        and _path_ancestry_exact(path)
        and deterministic_replay
        and damage_irreversible
        and dissipation_monotonic
        and energy_history[-1] > 0.0
        and reversal_dissipation_growth
        and tensile_damage_steps
        and positive_compressive_damage_steps
        and reverse_compressive_damage_steps
        and final_material["maximum_tensile_damage"] > 0.0
        and final_material["maximum_compressive_damage"] > 0.0
        and final_material["tensile_damaged_concrete_state_count"] > 0
        and final_material["compressive_damaged_concrete_state_count"] > 0
        and final_material["maximum_steel_accumulated_plastic_strain"] == 0.0
        and final_material["maximum_steel_dissipated_energy_density_mj_per_m3"] == 0.0
        and tangent["pass"] is True
        and tangent["damaged_member_count"] > 0
        and tangent["yielded_member_count"] == 0
        and first_damage_quadratic["pass"] is True
        and elastic_reference_relative_error <= 1.0e-6
        and CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION >= 0.75
        and maximum_residual <= 1.0e-8
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
        and rollback_exact
    )
    return {
        "schema_version": (STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_SCHEMA_VERSION),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": (
            "internal_analytic_elastic_prefix_and_algorithmic_cyclic_frame_path"
        ),
        "formulation": STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_FORMULATION,
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "problem_contract_hash": problem.contract_hash,
        "geometry": {
            "node_coordinates_m": [
                list(row) for row in CONCRETE_FRAME_NODE_COORDINATES_M
            ],
            "member_connectivity": [[0, 1], [1, 2]],
            "fixed_global_dofs": [0, 1, 2],
            "tip_vertical_dof": CONCRETE_FRAME_TIP_VERTICAL_DOF,
            "reference_tip_load_kn": CONCRETE_FRAME_REFERENCE_TIP_LOAD_KN,
            "rotation_coordinate_scale_m": _TOTAL_CANTILEVER_LENGTH_M,
        },
        "section": {
            "profile": "concrete_dominated_elastic_reinforcement_stabilized",
            "width_m": _SECTION_WIDTH_M,
            "depth_m": _SECTION_DEPTH_M,
            "cover_m": _SECTION_COVER_M,
            "concrete_layer_count": _CONCRETE_LAYER_COUNT,
            "bar_count_per_face": _BAR_COUNT_PER_FACE,
            "bar_area_m2": _BAR_AREA_M2,
            "reinforcement_elastic_modulus_mpa": _STEEL_ELASTIC_MODULUS_MPA,
            "reinforcement_yield_stress_mpa": (_STEEL_ELASTIC_YIELD_STRESS_MPA),
            "concrete_flexural_rigidity_kn_m2": (
                CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2
            ),
            "reinforcement_flexural_rigidity_kn_m2": (
                CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2
            ),
            "elastic_flexural_rigidity_kn_m2": (
                CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2
            ),
            "initial_concrete_flexural_rigidity_fraction": (
                CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION
            ),
        },
        "concrete_material": {
            "elastic_modulus_mpa": 30_000.0,
            "tensile_strength_mpa": 3.0,
            "compressive_strength_mpa": 30.0,
            "tensile_softening_rate": 3_000.0,
            "compressive_softening_rate": 400.0,
            "independent_tension_compression_history": True,
        },
        "cyclic_load_factors": list(CONCRETE_FRAME_CYCLIC_LOAD_FACTORS),
        "path_status": path.status,
        "requested_step_count": len(CONCRETE_FRAME_CYCLIC_LOAD_FACTORS),
        "committed_step_count": sum(step.committed for step in path.steps),
        "path_ancestry_exact": _path_ancestry_exact(path),
        "deterministic_replay_exact": deterministic_replay,
        "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
        "final_checkpoint_hash": path.final_checkpoint.state_hash,
        "elastic_reference": {
            "load_factor": CONCRETE_FRAME_CYCLIC_LOAD_FACTORS[0],
            "analytic_tip_displacement_m": elastic_reference_tip_displacement_m,
            "observed_tip_displacement_m": elastic_step["tip_vertical_displacement_m"],
            "relative_error": elastic_reference_relative_error,
            "relative_tolerance": 1.0e-6,
            "pass": elastic_reference_relative_error <= 1.0e-6,
        },
        "damage_history": {
            "damage_irreversible": damage_irreversible,
            "tensile_damage_evolution_step_indices": tensile_damage_steps,
            "compressive_damage_evolution_step_indices": compressive_damage_steps,
            "positive_loading_compressive_damage_step_indices": (
                positive_compressive_damage_steps
            ),
            "reverse_loading_compressive_damage_step_indices": (
                reverse_compressive_damage_steps
            ),
            "first_damage_step_index": first_damage_step_index,
            "first_compressive_damage_step_index": (
                first_compressive_damage_step_index
            ),
            "final_material_state": final_material,
        },
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "reversal_dissipation_growth": reversal_dissipation_growth,
        "final_dissipated_energy_mj": energy_history[-1],
        "same_parent_two_branch_consistent_tangent": tangent,
        "first_damage_quadratic_convergence": first_damage_quadratic,
        "maximum_residual_inf_norm_kn": maximum_residual,
        "line_search_history_entry_count": line_search_history_entries,
        "line_search_used_step_count": sum(
            bool(row["line_search_used"]) for row in steps
        ),
        "damaged_step_count": sum(
            int(int(row["damaged_member_count"]) > 0) for row in steps
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
            "asymmetric_tension_compression_concrete_damage": True,
            "cyclic_concrete_damage_and_nonnegative_dissipation": True,
            "same_parent_material_plus_geometric_tangent": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "analytic_elastic_prefix": True,
            "concrete_dominated_initial_flexural_rigidity": True,
            "pure_concrete_section": False,
            "mesh_objectivity": False,
            "crack_band_or_fracture_energy_regularization": False,
            "multiaxial_concrete_validity": False,
            "external_cyclic_member_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "pure_concrete_section_protocol_not_implemented",
            "elastic_reinforcement_stabilizes_post_cracking_path",
            "crack_band_fracture_energy_regularization_not_implemented",
            "mesh_objectivity_not_established",
            "multiaxial_concrete_model_not_implemented",
            "external_cyclic_member_reference_not_attached",
            "three_dimensional_frame_material_integration_not_closed",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_material_newton_breadth_not_closed",
        ],
        "claim_boundary": (STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_CLAIM_BOUNDARY),
    }


__all__ = [
    "CONCRETE_FRAME_CONCRETE_FLEXURAL_RIGIDITY_KN_M2",
    "CONCRETE_FRAME_CYCLIC_LOAD_FACTORS",
    "CONCRETE_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2",
    "CONCRETE_FRAME_INITIAL_CONCRETE_FLEXURAL_RIGIDITY_FRACTION",
    "CONCRETE_FRAME_NODE_COORDINATES_M",
    "CONCRETE_FRAME_REFERENCE_TIP_LOAD_KN",
    "CONCRETE_FRAME_REINFORCEMENT_FLEXURAL_RIGIDITY_KN_M2",
    "CONCRETE_FRAME_TIP_VERTICAL_DOF",
    "STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_CONCRETE_FRAME_CYCLIC_SCHEMA_VERSION",
    "build_stateful_corotational_concrete_frame_cyclic_benchmark",
    "make_stateful_corotational_concrete_frame_cyclic_problem",
]
