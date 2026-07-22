"""Bounded cyclic steel-hardening benchmark on the corotational fiber frame."""

from __future__ import annotations

from dataclasses import dataclass
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


STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_SCHEMA_VERSION = (
    "stateful-corotational-steel-frame-cyclic-benchmark.v1"
)
STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_FORMULATION = (
    "two_member_euler_bernoulli_corotational_fiber_frame_with_"
    "small_strain_bilinear_steel_and_material_plus_geometric_tangent"
)
STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_CLAIM_BOUNDARY = (
    "This benchmark verifies one bounded two-member planar cantilever whose "
    "fiber sections are deliberately steel-dominated. It exercises small-strain "
    "bilinear steel with linear isotropic, kinematic, and combined hardening, "
    "cyclic reversal, nonnegative plastic dissipation, same-parent material-plus-"
    "geometric tangents, deterministic Newton commits, and exact failed-step "
    "rollback. Very-low-stiffness, very-high-strength concrete carrier fibers "
    "remain elastic only because the existing section protocol requires both "
    "steel and concrete fibers. This is not a pure-steel section, concrete "
    "validation, finite-strain or multiaxial plasticity, local-buckling, fracture, "
    "external cyclic-member acceptance, production sparse/ROCm/HIP execution, "
    "full-building equilibrium, G1 closure, or commercial readiness evidence."
)

STEEL_FRAME_NODE_COORDINATES_M = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
STEEL_FRAME_REFERENCE_TIP_LOAD_KN = -50.0
STEEL_FRAME_TIP_VERTICAL_DOF = 7
STEEL_FRAME_CYCLIC_LOAD_FACTORS = (
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
_CONCRETE_LAYER_COUNT = 4
_BAR_COUNT_PER_FACE = 2
_BAR_AREA_M2 = 5.0e-4
_STEEL_ELASTIC_MODULUS_MPA = 200_000.0
_STEEL_YIELD_STRESS_MPA = 250.0
_CONCRETE_CARRIER_ELASTIC_MODULUS_MPA = 1.0
_CONCRETE_CARRIER_STRENGTH_MPA = 1.0e12
_TOTAL_CANTILEVER_LENGTH_M = 2.0


@dataclass(frozen=True)
class SteelHardeningVariant:
    variant_id: str
    isotropic_hardening_modulus_mpa: float
    kinematic_hardening_modulus_mpa: float

    @property
    def total_hardening_modulus_mpa(self) -> float:
        return (
            self.isotropic_hardening_modulus_mpa + self.kinematic_hardening_modulus_mpa
        )

    def material(self) -> BilinearCombinedHardeningSteel:
        return BilinearCombinedHardeningSteel(
            elastic_modulus_mpa=_STEEL_ELASTIC_MODULUS_MPA,
            yield_stress_mpa=_STEEL_YIELD_STRESS_MPA,
            isotropic_hardening_modulus_mpa=(self.isotropic_hardening_modulus_mpa),
            kinematic_hardening_modulus_mpa=(self.kinematic_hardening_modulus_mpa),
            material_id=self.variant_id,
        )

    def to_dict(self) -> dict[str, Any]:
        material = self.material()
        return {
            "variant_id": self.variant_id,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "yield_stress_mpa": material.yield_stress_mpa,
            "isotropic_hardening_modulus_mpa": (
                material.isotropic_hardening_modulus_mpa
            ),
            "kinematic_hardening_modulus_mpa": (
                material.kinematic_hardening_modulus_mpa
            ),
            "total_hardening_modulus_mpa": self.total_hardening_modulus_mpa,
            "plastic_consistent_tangent_mpa": (material.plastic_consistent_tangent_mpa),
        }


STEEL_HARDENING_VARIANTS = (
    SteelHardeningVariant(
        variant_id="steel_bilinear_isotropic_hardening_frame",
        isotropic_hardening_modulus_mpa=8_000.0,
        kinematic_hardening_modulus_mpa=0.0,
    ),
    SteelHardeningVariant(
        variant_id="steel_bilinear_kinematic_hardening_frame",
        isotropic_hardening_modulus_mpa=0.0,
        kinematic_hardening_modulus_mpa=8_000.0,
    ),
    SteelHardeningVariant(
        variant_id="steel_bilinear_combined_hardening_frame",
        isotropic_hardening_modulus_mpa=3_000.0,
        kinematic_hardening_modulus_mpa=5_000.0,
    ),
)


def _variant(variant_id: str) -> SteelHardeningVariant:
    normalized = str(variant_id).strip()
    for row in STEEL_HARDENING_VARIANTS:
        if row.variant_id == normalized:
            return row
    raise ValueError(f"unsupported steel hardening variant: {normalized!r}")


def _elastic_flexural_rigidity_kn_m2() -> float:
    bar_y = 0.5 * _SECTION_DEPTH_M - _SECTION_COVER_M
    steel_second_moment_m4 = 2 * _BAR_COUNT_PER_FACE * _BAR_AREA_M2 * bar_y**2
    layer_depth = _SECTION_DEPTH_M / _CONCRETE_LAYER_COUNT
    layer_area = _SECTION_WIDTH_M * layer_depth
    layer_ys = tuple(
        -0.5 * _SECTION_DEPTH_M + (index + 0.5) * layer_depth
        for index in range(_CONCRETE_LAYER_COUNT)
    )
    concrete_second_moment_m4 = math.fsum(layer_area * y**2 for y in layer_ys)
    return 1_000.0 * (
        _STEEL_ELASTIC_MODULUS_MPA * steel_second_moment_m4
        + _CONCRETE_CARRIER_ELASTIC_MODULUS_MPA * concrete_second_moment_m4
    )


STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2 = _elastic_flexural_rigidity_kn_m2()


def make_stateful_corotational_steel_frame_cyclic_problem(
    variant_id: str,
) -> StatefulCorotationalFiberFrame2DProblem:
    """Create the deterministic two-member steel-dominated cantilever."""

    variant = _variant(variant_id)
    steel = variant.material()
    concrete_carrier = AsymmetricConcreteDamageMaterial(
        elastic_modulus_mpa=_CONCRETE_CARRIER_ELASTIC_MODULUS_MPA,
        tensile_strength_mpa=_CONCRETE_CARRIER_STRENGTH_MPA,
        compressive_strength_mpa=_CONCRETE_CARRIER_STRENGTH_MPA,
        tensile_softening_rate=1.0,
        compressive_softening_rate=1.0,
        material_id=f"{variant.variant_id}-elastic-concrete-carrier",
    )
    members: list[StatefulCorotationalFiberFrame2DMember] = []
    for member_index, (node_i, node_j) in enumerate(((0, 1), (1, 2)), start=1):
        member_id = f"{variant.variant_id}-member-{member_index}"
        section = make_rectangular_stateful_rc_fiber_section(
            width_m=_SECTION_WIDTH_M,
            depth_m=_SECTION_DEPTH_M,
            cover_m=_SECTION_COVER_M,
            concrete_layer_count=_CONCRETE_LAYER_COUNT,
            top_bar_count=_BAR_COUNT_PER_FACE,
            bottom_bar_count=_BAR_COUNT_PER_FACE,
            bar_area_m2=_BAR_AREA_M2,
            section_id=f"{variant.variant_id}-section-{member_index}",
            steel=steel,
            concrete=concrete_carrier,
        )
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=(
                        STEEL_FRAME_NODE_COORDINATES_M[node_i],
                        STEEL_FRAME_NODE_COORDINATES_M[node_j],
                    ),
                    section=section,
                    integration_order=3,
                    element_id=member_id,
                ),
            )
        )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=f"stateful-corotational-cyclic-{variant.variant_id}",
        node_coordinates_m=STEEL_FRAME_NODE_COORDINATES_M,
        members=tuple(members),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=(
            (STEEL_FRAME_TIP_VERTICAL_DOF, STEEL_FRAME_REFERENCE_TIP_LOAD_KN),
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


def _checkpoint_material_extrema(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> dict[str, Any]:
    accumulated_plastic_strains: list[float] = []
    steel_dissipations: list[float] = []
    concrete_damages: list[float] = []
    concrete_dissipations: list[float] = []
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
                if fiber.material_kind == "steel":
                    if type(state) is not UniaxialPlasticityState:
                        raise ValueError("steel fiber state type is invalid")
                    accumulated_plastic_strains.append(state.accumulated_plastic_strain)
                    steel_dissipations.append(state.dissipated_energy_density_mj_per_m3)
                else:
                    if type(state) is not ConcreteDamageState:
                        raise ValueError("concrete fiber state type is invalid")
                    concrete_damages.extend(
                        (state.tensile_damage, state.compressive_damage)
                    )
                    concrete_dissipations.append(
                        state.dissipated_energy_density_mj_per_m3
                    )
    return {
        "maximum_accumulated_plastic_strain": max(
            accumulated_plastic_strains,
            default=0.0,
        ),
        "maximum_steel_dissipated_energy_density_mj_per_m3": max(
            steel_dissipations,
            default=0.0,
        ),
        "maximum_concrete_damage": max(concrete_damages, default=0.0),
        "maximum_concrete_dissipated_energy_density_mj_per_m3": max(
            concrete_dissipations,
            default=0.0,
        ),
    }


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
        zip(STEEL_FRAME_CYCLIC_LOAD_FACTORS, path.steps, strict=True),
        start=1,
    ):
        rows.append(
            {
                "step_index": step_index,
                "target_load_factor": load_factor,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "tip_vertical_displacement_m": (
                    step.accepted_checkpoint.global_displacements[
                        STEEL_FRAME_TIP_VERTICAL_DOF
                    ]
                ),
                "dissipated_energy_mj": _checkpoint_dissipated_energy_mj(
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


def _build_variant_result(
    variant: SteelHardeningVariant,
) -> tuple[
    dict[str, Any],
    StatefulCorotationalFiberFrame2DProblem,
    StatefulCorotationalFiberFrame2DLoadPathResult,
]:
    problem = make_stateful_corotational_steel_frame_cyclic_problem(variant.variant_id)
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        STEEL_FRAME_CYCLIC_LOAD_FACTORS,
    )
    replay = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        STEEL_FRAME_CYCLIC_LOAD_FACTORS,
    )
    steps = _step_receipts(problem, path)
    energy_history = [0.0, *(row["dissipated_energy_mj"] for row in steps)]
    dissipation_monotonic = all(
        following + 1.0e-15 >= previous
        for previous, following in zip(
            energy_history,
            energy_history[1:],
        )
    )
    yielded_steps = [
        int(row["step_index"]) for row in steps if int(row["yielded_member_count"]) > 0
    ]
    if not yielded_steps:
        raise ValueError(f"{variant.variant_id} did not yield on the benchmark path")
    first_yield_step = yielded_steps[0]
    parent = (
        path.initial_checkpoint
        if first_yield_step == 1
        else path.steps[first_yield_step - 2].accepted_checkpoint
    )
    yielded_step = path.steps[first_yield_step - 1]
    tangent = finite_difference_stateful_corotational_fiber_frame2d_tangent_check(
        problem,
        parent,
        target_load_factor=STEEL_FRAME_CYCLIC_LOAD_FACTORS[first_yield_step - 1],
        trial_free_coordinates_m=(yielded_step.trial_solution.free_displacements_m),
    )
    quadratic = assess_quadratic_convergence(
        list(yielded_step.trial_solution.convergence_history),
        minimum_observed_order=1.8,
        minimum_order_sample_count=1,
    )
    elastic_step = steps[0]
    elastic_reference_tip_displacement_m = (
        STEEL_FRAME_REFERENCE_TIP_LOAD_KN
        * STEEL_FRAME_CYCLIC_LOAD_FACTORS[0]
        * _TOTAL_CANTILEVER_LENGTH_M**3
        / (3.0 * STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2)
    )
    elastic_reference_relative_error = abs(
        float(elastic_step["tip_vertical_displacement_m"])
        - elastic_reference_tip_displacement_m
    ) / abs(elastic_reference_tip_displacement_m)
    reverse_yielded_steps = [
        index
        for index in yielded_steps
        if STEEL_FRAME_CYCLIC_LOAD_FACTORS[index - 1] < 0.0
    ]
    material_extrema = _checkpoint_material_extrema(problem, path.final_checkpoint)
    deterministic_replay = bool(
        path.to_dict() == replay.to_dict()
        and path.final_checkpoint.canonical_bytes()
        == replay.final_checkpoint.canonical_bytes()
    )
    maximum_residual = max(float(row["residual_inf_norm_kn"]) for row in steps)
    fallback_count = sum(bool(row["fallback_used"]) for row in steps)
    regularization_count = sum(bool(row["regularization_used"]) for row in steps)
    damaged_step_count = sum(int(int(row["damaged_member_count"]) > 0) for row in steps)
    line_search_history_entries = sum(
        int(row["line_search_history_entry_count"]) for row in steps
    )
    contract_pass = bool(
        path.status == "ready"
        and path.contract_pass
        and len(path.steps) == len(STEEL_FRAME_CYCLIC_LOAD_FACTORS)
        and _path_ancestry_exact(path)
        and deterministic_replay
        and dissipation_monotonic
        and energy_history[-1] > 0.0
        and material_extrema["maximum_accumulated_plastic_strain"] > 0.0
        and material_extrema["maximum_steel_dissipated_energy_density_mj_per_m3"] > 0.0
        and material_extrema["maximum_concrete_damage"] == 0.0
        and material_extrema["maximum_concrete_dissipated_energy_density_mj_per_m3"]
        == 0.0
        and damaged_step_count == 0
        and tangent["pass"] is True
        and tangent["yielded_member_count"] > 0
        and tangent["damaged_member_count"] == 0
        and quadratic["pass"] is True
        and elastic_reference_relative_error <= 1.0e-6
        and reverse_yielded_steps
        and maximum_residual <= 1.0e-8
        and fallback_count == 0
        and regularization_count == 0
        and line_search_history_entries > 0
    )
    return (
        {
            "variant": variant.to_dict(),
            "problem_contract_hash": problem.contract_hash,
            "contract_pass": contract_pass,
            "path_status": path.status,
            "requested_step_count": len(STEEL_FRAME_CYCLIC_LOAD_FACTORS),
            "committed_step_count": sum(step.committed for step in path.steps),
            "path_ancestry_exact": _path_ancestry_exact(path),
            "deterministic_replay_exact": deterministic_replay,
            "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
            "final_checkpoint_hash": path.final_checkpoint.state_hash,
            "elastic_reference": {
                "flexural_rigidity_kn_m2": (
                    STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2
                ),
                "load_factor": STEEL_FRAME_CYCLIC_LOAD_FACTORS[0],
                "analytic_tip_displacement_m": (elastic_reference_tip_displacement_m),
                "observed_tip_displacement_m": elastic_step[
                    "tip_vertical_displacement_m"
                ],
                "relative_error": elastic_reference_relative_error,
                "relative_tolerance": 1.0e-6,
                "pass": elastic_reference_relative_error <= 1.0e-6,
            },
            "yielded_step_indices": yielded_steps,
            "reverse_loading_yielded_step_indices": reverse_yielded_steps,
            "first_reverse_yield_step_index": min(reverse_yielded_steps),
            "dissipation_nonnegative_monotonic": dissipation_monotonic,
            "final_dissipated_energy_mj": energy_history[-1],
            "material_state_extrema": material_extrema,
            "same_parent_consistent_tangent": tangent,
            "first_yield_quadratic_convergence": quadratic,
            "maximum_residual_inf_norm_kn": maximum_residual,
            "line_search_history_entry_count": line_search_history_entries,
            "line_search_used_step_count": sum(
                bool(row["line_search_used"]) for row in steps
            ),
            "damaged_step_count": damaged_step_count,
            "fallback_count": fallback_count,
            "regularization_count": regularization_count,
            "steps": steps,
        },
        problem,
        path,
    )


def build_stateful_corotational_steel_frame_cyclic_benchmark() -> dict[str, Any]:
    """Build the deterministic three-variant cyclic frame benchmark receipt."""

    runs = tuple(_build_variant_result(variant) for variant in STEEL_HARDENING_VARIANTS)
    results = [row[0] for row in runs]
    by_variant = {row["variant"]["variant_id"]: row for row in results}
    isotropic = by_variant["steel_bilinear_isotropic_hardening_frame"]
    kinematic = by_variant["steel_bilinear_kinematic_hardening_frame"]
    combined = by_variant["steel_bilinear_combined_hardening_frame"]
    energy_ordering = bool(
        kinematic["final_dissipated_energy_mj"]
        > combined["final_dissipated_energy_mj"]
        > isotropic["final_dissipated_energy_mj"]
        > 0.0
    )
    reverse_yield_separation = bool(
        kinematic["first_reverse_yield_step_index"]
        <= combined["first_reverse_yield_step_index"]
        < isotropic["first_reverse_yield_step_index"]
    )
    elastic_tip_displacements = [
        float(row["elastic_reference"]["observed_tip_displacement_m"])
        for row in results
    ]
    elastic_variant_spread_m = max(elastic_tip_displacements) - min(
        elastic_tip_displacements
    )
    branch_separation_pass = bool(
        energy_ordering
        and reverse_yield_separation
        and elastic_variant_spread_m <= 1.0e-13
    )

    combined_run = next(
        row
        for row in runs
        if row[0]["variant"]["variant_id"] == "steel_bilinear_combined_hardening_frame"
    )
    combined_problem = combined_run[1]
    combined_path = combined_run[2]
    rollback_parent = combined_path.steps[7].accepted_checkpoint
    rollback_parent_bytes = rollback_parent.canonical_bytes()
    failed = solve_stateful_corotational_fiber_frame2d_load_step(
        combined_problem,
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
        and failed.metrics["damaged_member_count"] == 0
        and failed.metrics["fallback_used"] is False
        and failed.metrics["regularization_used"] is False
    )
    variant_contract = all(row["contract_pass"] for row in results)
    contract_pass = bool(variant_contract and branch_separation_pass and rollback_exact)
    return {
        "schema_version": (STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_SCHEMA_VERSION),
        "status": "partial",
        "contract_pass": contract_pass,
        "truth_class": (
            "internal_analytic_elastic_prefix_and_algorithmic_cyclic_frame_path"
        ),
        "formulation": STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_FORMULATION,
        "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_ASSEMBLY,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "geometry": {
            "node_coordinates_m": [list(row) for row in STEEL_FRAME_NODE_COORDINATES_M],
            "member_connectivity": [[0, 1], [1, 2]],
            "fixed_global_dofs": [0, 1, 2],
            "tip_vertical_dof": STEEL_FRAME_TIP_VERTICAL_DOF,
            "reference_tip_load_kn": STEEL_FRAME_REFERENCE_TIP_LOAD_KN,
            "rotation_coordinate_scale_m": _TOTAL_CANTILEVER_LENGTH_M,
        },
        "section": {
            "profile": "steel_dominated_rc_protocol_carrier",
            "width_m": _SECTION_WIDTH_M,
            "depth_m": _SECTION_DEPTH_M,
            "cover_m": _SECTION_COVER_M,
            "concrete_layer_count": _CONCRETE_LAYER_COUNT,
            "bar_count_per_face": _BAR_COUNT_PER_FACE,
            "bar_area_m2": _BAR_AREA_M2,
            "concrete_carrier_elastic_modulus_mpa": (
                _CONCRETE_CARRIER_ELASTIC_MODULUS_MPA
            ),
            "concrete_carrier_strength_mpa": (_CONCRETE_CARRIER_STRENGTH_MPA),
            "elastic_flexural_rigidity_kn_m2": (
                STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2
            ),
        },
        "cyclic_load_factors": list(STEEL_FRAME_CYCLIC_LOAD_FACTORS),
        "hardening_variant_count": len(results),
        "hardening_variants": results,
        "hardening_branch_separation": {
            "elastic_variant_tip_displacement_spread_m": (elastic_variant_spread_m),
            "kinematic_energy_greater_than_combined_greater_than_isotropic": (
                energy_ordering
            ),
            "kinematic_component_reverse_yield_precedes_pure_isotropic": (
                reverse_yield_separation
            ),
            "pass": branch_separation_pass,
        },
        "forced_failure_rollback": {
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "target_load_factor": 1.0,
            "status": failed.status,
            "terminal_reason": failed.metrics["terminal_reason"],
            "trial_yielded_member_count": failed.metrics["yielded_member_count"],
            "trial_damaged_member_count": failed.metrics["damaged_member_count"],
            "accepted_checkpoint_hash_after": (failed.accepted_checkpoint.state_hash),
            "exact": rollback_exact,
        },
        "claims": {
            "bounded_two_member_corotational_fiber_frame": True,
            "isotropic_kinematic_combined_linear_hardening": True,
            "cyclic_steel_yield_and_nonnegative_dissipation": True,
            "same_parent_material_plus_geometric_tangent": True,
            "consistent_newton_commit_and_exact_rollback": True,
            "analytic_elastic_prefix": True,
            "pure_steel_section": False,
            "concrete_damage_validation": False,
            "finite_strain_or_multiaxial_steel": False,
            "local_buckling_or_fracture": False,
            "external_cyclic_member_acceptance": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
            "commercial_readiness": False,
        },
        "blockers_remaining": [
            "pure_steel_section_protocol_not_implemented",
            "external_cyclic_member_reference_not_attached",
            "finite_strain_multiaxial_steel_not_implemented",
            "local_buckling_fracture_fatigue_not_implemented",
            "three_dimensional_frame_material_integration_not_closed",
            "production_sparse_rocm_hip_parity_not_closed",
            "full_building_material_newton_breadth_not_closed",
        ],
        "claim_boundary": (STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_CLAIM_BOUNDARY),
    }


__all__ = [
    "STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_FORMULATION",
    "STATEFUL_COROTATIONAL_STEEL_FRAME_CYCLIC_SCHEMA_VERSION",
    "STEEL_FRAME_CYCLIC_LOAD_FACTORS",
    "STEEL_FRAME_ELASTIC_FLEXURAL_RIGIDITY_KN_M2",
    "STEEL_FRAME_NODE_COORDINATES_M",
    "STEEL_FRAME_REFERENCE_TIP_LOAD_KN",
    "STEEL_FRAME_TIP_VERTICAL_DOF",
    "STEEL_HARDENING_VARIANTS",
    "SteelHardeningVariant",
    "build_stateful_corotational_steel_frame_cyclic_benchmark",
    "make_stateful_corotational_steel_frame_cyclic_problem",
]
