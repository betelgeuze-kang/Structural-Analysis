"""Bounded crack-band concrete and RC-tie mesh-objectivity benchmark."""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, cast

import numpy as np

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialChainProblem,
    StatefulAxialElement,
    StatefulUniaxialMaterial,
    run_stateful_axial_load_path,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    FRACTURE_ENERGY_DAMAGE_ALGORITHM,
    FRACTURE_ENERGY_TANGENT_DEFINITION,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION = (
    "fracture-energy-concrete-mesh-objectivity-benchmark.v1"
)
FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE = (
    "localized_crack_band_rc_tie_2_4_8_meshes.v1"
)
FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY = (
    "This candidate verifies a uniaxial exponential traction-opening crack-band "
    "law and a seeded single-crack reinforced-concrete tie idealization at 2, 4, "
    "and 8 concrete elements. Continuous reinforcement is one global parallel tie, "
    "perfect bond is assumed at the end sections, and the concrete localization "
    "element is prescribed by a strength imperfection. It does not establish "
    "multiaxial concrete, confinement, bond slip, arbitrary localization, frame or "
    "shell mesh objectivity, published-benchmark credit, design authority, or release "
    "readiness."
)

_HASH_ZERO = "sha256:" + "0" * 64


def _scaled_linf(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    return float(np.max(np.abs(left_array - right_array))) / max(
        1.0,
        float(np.max(np.abs(left_array))),
        float(np.max(np.abs(right_array))),
    )


def _material(
    characteristic_length_m: float,
    *,
    tensile_strength_mpa: float,
) -> FractureEnergyConcreteDamageMaterial:
    return FractureEnergyConcreteDamageMaterial(
        elastic_modulus_mpa=30_000.0,
        tensile_strength_mpa=tensile_strength_mpa,
        compressive_strength_mpa=30.0,
        characteristic_length_m=characteristic_length_m,
        tensile_fracture_energy_n_per_m=100.0,
        compressive_fracture_energy_n_per_m=20_000.0,
        history_tolerance=1.0e-14,
    )


def _mesh_case(
    mesh_count: int,
    *,
    length_m: float,
    gross_area_m2: float,
    reinforcement_ratio: float,
    terminal_displacement_m: float,
    load_step_count: int,
) -> dict[str, Any]:
    element_length = length_m / mesh_count
    concrete_area = gross_area_m2 * (1.0 - reinforcement_ratio)
    elements = tuple(
        StatefulAxialElement(
            element_id=f"concrete-{index + 1}",
            node_i=index,
            node_j=index + 1,
            length_m=element_length,
            area_m2=concrete_area,
            material=cast(
                StatefulUniaxialMaterial,
                _material(
                    element_length,
                    tensile_strength_mpa=(3.0 if index == mesh_count - 1 else 3.3),
                ),
            ),
        )
        for index in range(mesh_count)
    )
    problem = StatefulAxialChainProblem(
        case_id=f"fracture_energy_rc_tie_mesh_{mesh_count}",
        node_count=mesh_count + 1,
        elements=elements,
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=((mesh_count, terminal_displacement_m),),
    )
    targets = tuple(index / load_step_count for index in range(1, load_step_count + 1))
    path = run_stateful_axial_load_path(
        problem,
        targets,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-9,
            increment_tolerance=1.0e-12,
            max_iterations=80,
        ),
    )
    steel = BilinearCombinedHardeningSteel()
    steel_state = steel.initial_state()
    steel_area = gross_area_m2 * reinforcement_ratio
    concrete_force_history: list[float] = []
    reinforcement_force_history: list[float] = []
    total_force_history: list[float] = []
    maximum_equilibrium_spread = 0.0
    for step, target in zip(path.steps, targets, strict=False):
        concrete_forces = [
            float(row["internal_force_kn"])
            for row in step.trial_assembly.element_responses
        ]
        maximum_equilibrium_spread = max(
            maximum_equilibrium_spread,
            max(concrete_forces) - min(concrete_forces),
        )
        concrete_force = math.fsum(concrete_forces) / len(concrete_forces)
        global_strain = target * terminal_displacement_m / length_m
        steel_response = steel.integrate(global_strain, steel_state)
        steel_state = steel_response.state
        reinforcement_force = steel_response.stress_mpa * steel_area * 1_000.0
        concrete_force_history.append(concrete_force)
        reinforcement_force_history.append(reinforcement_force)
        total_force_history.append(concrete_force + reinforcement_force)

    final_states = path.final_state.material_states
    concrete_dissipated_energy_j = 0.0
    localized_indices: list[int] = []
    final_damage: list[float] = []
    for index, (element, state) in enumerate(
        zip(problem.elements, final_states, strict=True)
    ):
        if type(state) is not ConcreteDamageState:
            raise ValueError("fracture-energy mesh state type is invalid")
        damage = state.tensile_damage
        final_damage.append(damage)
        if damage > 0.5:
            localized_indices.append(index)
        concrete_dissipated_energy_j += (
            state.dissipated_energy_density_mj_per_m3
            * element.length_m
            * element.area_m2
            * 1.0e6
        )
    expected_energy_j = 100.0 * concrete_area
    checks = {
        "path_contract_pass": path.contract_pass,
        "all_steps_committed": all(step.committed for step in path.steps),
        "equilibrium_pass": maximum_equilibrium_spread <= 1.0e-8,
        "single_seeded_localization": localized_indices == [mesh_count - 1],
        "zero_fallback": all(
            step.metrics.get("fallback_used") is False for step in path.steps
        ),
        "zero_regularization": all(
            step.metrics.get("regularization_used") is False for step in path.steps
        ),
        "terminal_displacement_exact": bool(
            path.final_state.displacements_m[-1] == terminal_displacement_m
        ),
        "fracture_energy_saturation_pass": bool(
            abs(concrete_dissipated_energy_j - expected_energy_j) / expected_energy_j
            <= 5.0e-4
        ),
    }
    return {
        "mesh_count": mesh_count,
        "element_length_m": element_length,
        "problem_case_id": problem.case_id,
        "terminal_state_hash": path.final_state.state_hash,
        "status": path.status,
        "contract_pass": all(checks.values()),
        "concrete_force_history_kn": concrete_force_history,
        "reinforcement_force_history_kn": reinforcement_force_history,
        "total_rc_force_history_kn": total_force_history,
        "terminal_displacement_m": terminal_displacement_m,
        "maximum_equilibrium_force_spread_kn": maximum_equilibrium_spread,
        "concrete_dissipated_energy_j": concrete_dissipated_energy_j,
        "expected_tensile_fracture_energy_j": expected_energy_j,
        "fracture_energy_relative_error": abs(
            concrete_dissipated_energy_j - expected_energy_j
        )
        / expected_energy_j,
        "localized_element_indices": localized_indices,
        "final_tensile_damage": final_damage,
        "checks": checks,
    }


def build_fracture_energy_concrete_mesh_objectivity_benchmark() -> dict[str, Any]:
    """Build a deterministic non-promoting material/mesh candidate receipt."""

    mesh_counts = (2, 4, 8)
    length_m = 0.04
    gross_area_m2 = 0.01
    reinforcement_ratio = 0.01
    terminal_displacement_m = 3.5e-4
    load_step_count = 50
    crack_openings = (0.0, 1.0e-5, 5.0e-5, 1.0e-4, 3.0e-4)
    opening_rows: list[dict[str, Any]] = []
    maximum_traction_error = 0.0
    opening_energy_by_length: list[float] = []
    tangent_checks: list[dict[str, Any]] = []
    for mesh_count in mesh_counts:
        characteristic_length = length_m / mesh_count
        material = _material(characteristic_length, tensile_strength_mpa=3.0)
        rows: list[dict[str, float]] = []
        for crack_opening in crack_openings:
            energy_mj_per_m2 = material.tensile_fracture_energy_n_per_m / 1.0e6
            expected_traction = material.tensile_strength_mpa * math.exp(
                -material.tensile_strength_mpa * crack_opening / energy_mj_per_m2
            )
            strain = (
                expected_traction / material.elastic_modulus_mpa
                + crack_opening / characteristic_length
            )
            response = material.integrate(strain, material.initial_state())
            traction_error = abs(response.stress_mpa - expected_traction)
            maximum_traction_error = max(maximum_traction_error, traction_error)
            rows.append(
                {
                    "crack_opening_m": crack_opening,
                    "total_strain": strain,
                    "traction_mpa": response.stress_mpa,
                    "expected_traction_mpa": expected_traction,
                    "dissipated_energy_mj_per_m2": (
                        response.state.dissipated_energy_density_mj_per_m3
                        * characteristic_length
                    ),
                }
            )
        opening_energy_by_length.append(rows[-1]["dissipated_energy_mj_per_m2"])
        opening_rows.append(
            {
                "mesh_count": mesh_count,
                "characteristic_length_m": characteristic_length,
                "material_contract_hash": canonical_hash(asdict(material)),
                "rows": rows,
            }
        )
        tangent_checks.extend(
            finite_difference_concrete_damage_tangent_check(
                material,
                material.initial_state(),
                total_strain=strain,
                epsilon=1.0e-8,
                relative_tolerance=1.0e-7,
            )
            for strain in (0.002, -0.002)
        )

    mesh_cases = [
        _mesh_case(
            mesh_count,
            length_m=length_m,
            gross_area_m2=gross_area_m2,
            reinforcement_ratio=reinforcement_ratio,
            terminal_displacement_m=terminal_displacement_m,
            load_step_count=load_step_count,
        )
        for mesh_count in mesh_counts
    ]
    reference_force = mesh_cases[0]["total_rc_force_history_kn"]
    force_parity = [
        _scaled_linf(reference_force, row["total_rc_force_history_kn"])
        for row in mesh_cases[1:]
    ]
    energy_values = [row["concrete_dissipated_energy_j"] for row in mesh_cases]
    energy_spread_relative = (max(energy_values) - min(energy_values)) / max(
        max(energy_values), 1.0e-30
    )
    opening_energy_spread = max(opening_energy_by_length) - min(
        opening_energy_by_length
    )
    checks = {
        "implicit_tangent_finite_difference_pass": all(
            row["pass"] is True for row in tangent_checks
        ),
        "traction_opening_length_invariant": maximum_traction_error <= 1.0e-12,
        "opening_energy_length_invariant": opening_energy_spread <= 1.0e-15,
        "all_mesh_cases_pass": all(row["contract_pass"] for row in mesh_cases),
        "rc_force_history_mesh_objective": max(force_parity, default=0.0) <= 1.0e-8,
        "fracture_energy_mesh_objective": energy_spread_relative <= 1.0e-12,
    }
    body: dict[str, Any] = {
        "schema_version": FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION,
        "artifact_hash": _HASH_ZERO,
        "status": "candidate_verified" if all(checks.values()) else "blocked",
        "contract_pass": all(checks.values()),
        "profile": FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE,
        "material_algorithm": FRACTURE_ENERGY_DAMAGE_ALGORITHM,
        "tangent_definition": FRACTURE_ENERGY_TANGENT_DEFINITION,
        "configuration": {
            "mesh_counts": list(mesh_counts),
            "length_m": length_m,
            "gross_area_m2": gross_area_m2,
            "reinforcement_ratio": reinforcement_ratio,
            "terminal_displacement_m": terminal_displacement_m,
            "load_step_count": load_step_count,
            "seeded_localization": "terminal_concrete_element_10_percent_lower_ft",
            "reinforcement_idealization": "single_global_parallel_tie",
        },
        "traction_opening_cases": opening_rows,
        "tangent_checks": tangent_checks,
        "mesh_cases": mesh_cases,
        "metrics": {
            "maximum_traction_absolute_error_mpa": maximum_traction_error,
            "maximum_rc_force_history_scaled_linf": max(force_parity, default=0.0),
            "concrete_fracture_energy_spread_relative": energy_spread_relative,
            "opening_energy_spread_mj_per_m2": opening_energy_spread,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "checks": checks,
        "claims": {
            "uniaxial_fracture_energy_regularization": all(checks.values()),
            "bounded_seeded_rc_tie_mesh_objectivity": all(checks.values()),
            "arbitrary_rc_frame_or_shell_mesh_objectivity": False,
            "multiaxial_or_confined_concrete": False,
            "bond_slip": False,
            "published_or_external_validation": False,
            "release_readiness": False,
        },
        "limitations": [
            "uniaxial_tension_compression_only",
            "seeded_single_localization_band",
            "global_parallel_reinforcement_tie",
            "no_confinement_bond_slip_or_multiaxial_coupling",
            "no_published_or_external_benchmark_credit",
        ],
        "claim_boundary": FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY,
    }
    body["artifact_hash"] = canonical_hash(
        {key: value for key, value in body.items() if key != "artifact_hash"}
    )
    return body


__all__ = [
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY",
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE",
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION",
    "build_fracture_energy_concrete_mesh_objectivity_benchmark",
]
