"""State-updated iso-strain steel-concrete composite axial section seed."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any, Iterable

from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)


STATE_SCHEMA_VERSION = "parallel-steel-concrete-section-state.v1"
COMPOSITE_ALGORITHM = "iso_strain_parallel_constituent_integration"
TANGENT_DEFINITION = "area_fraction_weighted_constituent_consistent_tangent"
_STATE_HASH_DOMAIN = b"structural-analysis/composite-section-state/v1\0"


@dataclass(frozen=True)
class ParallelCompositeSectionState:
    steel_state: UniaxialPlasticityState = field(
        default_factory=UniaxialPlasticityState
    )
    concrete_state: ConcreteDamageState = field(default_factory=ConcreteDamageState)

    def canonical_bytes(self) -> bytes:
        steel = self.steel_state.canonical_bytes()
        concrete = self.concrete_state.canonical_bytes()
        return b"".join(
            (
                _STATE_HASH_DOMAIN,
                struct.pack("<Q", len(steel)),
                steel,
                struct.pack("<Q", len(concrete)),
                concrete,
            )
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "steel_state": self.steel_state.to_dict(),
            "concrete_state": self.concrete_state.to_dict(),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class ParallelCompositeSectionResponse:
    total_strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    steel_area_fraction: float
    concrete_area_fraction: float
    yielded: bool
    damage_evolved: bool
    committed_state_hash: str
    steel_response: UniaxialPlasticityResponse
    concrete_response: ConcreteDamageResponse
    state: ParallelCompositeSectionState

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_strain": self.total_strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "steel_area_fraction": self.steel_area_fraction,
            "concrete_area_fraction": self.concrete_area_fraction,
            "yielded": self.yielded,
            "damage_evolved": self.damage_evolved,
            "committed_state_hash": self.committed_state_hash,
            "steel_response": self.steel_response.to_dict(),
            "concrete_response": self.concrete_response.to_dict(),
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class ParallelSteelConcreteSectionMaterial:
    """Perfect-bond axial mixture; not a bending fiber or connector-slip model."""

    steel_area_fraction: float = 0.04
    steel: BilinearCombinedHardeningSteel = field(
        default_factory=BilinearCombinedHardeningSteel
    )
    concrete: AsymmetricConcreteDamageMaterial = field(
        default_factory=AsymmetricConcreteDamageMaterial
    )
    material_id: str = "parallel_steel_concrete_iso_strain_section_1d"

    def __post_init__(self) -> None:
        fraction = float(self.steel_area_fraction)
        if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
            raise ValueError("steel_area_fraction must be finite and in (0, 1)")
        if not self.material_id:
            raise ValueError("material_id must be non-empty")

    @property
    def concrete_area_fraction(self) -> float:
        return 1.0 - self.steel_area_fraction

    def initial_state(self) -> ParallelCompositeSectionState:
        return ParallelCompositeSectionState(
            steel_state=self.steel.initial_state(),
            concrete_state=self.concrete.initial_state(),
        )

    def integrate(
        self,
        total_strain: float,
        committed_state: ParallelCompositeSectionState,
    ) -> ParallelCompositeSectionResponse:
        strain = float(total_strain)
        if not math.isfinite(strain):
            raise ValueError("total_strain must be finite")
        steel_response = self.steel.integrate(strain, committed_state.steel_state)
        concrete_response = self.concrete.integrate(
            strain,
            committed_state.concrete_state,
        )
        concrete_fraction = self.concrete_area_fraction
        stress = (
            self.steel_area_fraction * steel_response.stress_mpa
            + concrete_fraction * concrete_response.stress_mpa
        )
        tangent = (
            self.steel_area_fraction * steel_response.consistent_tangent_mpa
            + concrete_fraction * concrete_response.consistent_tangent_mpa
        )
        state = ParallelCompositeSectionState(
            steel_state=steel_response.state,
            concrete_state=concrete_response.state,
        )
        return ParallelCompositeSectionResponse(
            total_strain=strain,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            steel_area_fraction=self.steel_area_fraction,
            concrete_area_fraction=concrete_fraction,
            yielded=steel_response.yielded,
            damage_evolved=concrete_response.damage_evolved,
            committed_state_hash=committed_state.state_hash,
            steel_response=steel_response,
            concrete_response=concrete_response,
            state=state,
        )

    def dissipated_energy_density_mj_per_m3(
        self,
        state: ParallelCompositeSectionState,
    ) -> float:
        return (
            self.steel_area_fraction
            * state.steel_state.dissipated_energy_density_mj_per_m3
            + self.concrete_area_fraction
            * state.concrete_state.dissipated_energy_density_mj_per_m3
        )


def finite_difference_composite_section_tangent_check(
    material: ParallelSteelConcreteSectionMaterial,
    committed_state: ParallelCompositeSectionState,
    *,
    total_strain: float,
    epsilon: float = 1.0e-9,
    relative_tolerance: float = 1.0e-6,
) -> dict[str, Any]:
    if epsilon <= 0.0 or not math.isfinite(epsilon):
        raise ValueError("epsilon must be finite and positive")
    center = material.integrate(total_strain, committed_state)
    forward = material.integrate(total_strain + epsilon, committed_state)
    backward = material.integrate(total_strain - epsilon, committed_state)
    finite_difference = (forward.stress_mpa - backward.stress_mpa) / (
        2.0 * epsilon
    )
    absolute_error = abs(finite_difference - center.consistent_tangent_mpa)
    scale = max(abs(finite_difference), abs(center.consistent_tangent_mpa), 1.0)
    relative_error = absolute_error / scale
    same_parent = bool(
        forward.committed_state_hash
        == center.committed_state_hash
        == backward.committed_state_hash
    )
    return {
        "composite_algorithm": COMPOSITE_ALGORITHM,
        "tangent_definition": TANGENT_DEFINITION,
        "total_strain": float(total_strain),
        "finite_difference_epsilon": epsilon,
        "analytic_consistent_tangent_mpa": center.consistent_tangent_mpa,
        "finite_difference_tangent_mpa": finite_difference,
        "absolute_error_mpa": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "same_committed_parent_state": same_parent,
        "pass": bool(relative_error <= relative_tolerance and same_parent),
    }


def integrate_composite_section_history(
    material: ParallelSteelConcreteSectionMaterial,
    strains: Iterable[float],
    *,
    initial_state: ParallelCompositeSectionState | None = None,
) -> dict[str, Any]:
    strain_path = tuple(float(value) for value in strains)
    if not strain_path or not all(math.isfinite(value) for value in strain_path):
        raise ValueError("strains must contain finite values")
    state = initial_state or material.initial_state()
    previous_strain = 0.0
    previous_stress = material.integrate(0.0, state).stress_mpa
    previous_increment_sign = 0
    reversal_count = 0
    work_density = 0.0
    dissipation_values = [material.dissipated_energy_density_mj_per_m3(state)]
    rows: list[dict[str, Any]] = []

    for step_index, strain in enumerate(strain_path, start=1):
        parent = state
        response = material.integrate(strain, parent)
        increment = strain - previous_strain
        increment_sign = 1 if increment > 0.0 else -1 if increment < 0.0 else 0
        if (
            increment_sign != 0
            and previous_increment_sign != 0
            and increment_sign != previous_increment_sign
        ):
            reversal_count += 1
        if increment_sign != 0:
            previous_increment_sign = increment_sign
        work_density += 0.5 * (previous_stress + response.stress_mpa) * increment
        state = response.state
        dissipation = material.dissipated_energy_density_mj_per_m3(state)
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "increment_sign": increment_sign,
                "composite_dissipated_energy_density_mj_per_m3": dissipation,
                **response.to_dict(),
            }
        )
        dissipation_values.append(dissipation)
        previous_strain = strain
        previous_stress = response.stress_mpa

    dissipation_monotonic = all(
        current + 1.0e-15 >= previous
        for previous, current in zip(dissipation_values, dissipation_values[1:])
    )
    return {
        "material_id": material.material_id,
        "composite_algorithm": COMPOSITE_ALGORITHM,
        "strain_path": list(strain_path),
        "step_count": len(rows),
        "reversal_count": reversal_count,
        "steel_yield_step_count": sum(bool(row["yielded"]) for row in rows),
        "concrete_damage_step_count": sum(
            bool(row["damage_evolved"]) for row in rows
        ),
        "stress_strain_work_density_mj_per_m3": work_density,
        "cumulative_dissipated_energy_density_mj_per_m3": (
            dissipation_values[-1]
        ),
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "constituent_state_gate_passed": bool(
            state.steel_state.accumulated_plastic_strain > 0.0
            and state.concrete_state.tensile_damage > 0.0
            and state.concrete_state.compressive_damage > 0.0
        ),
        "energy_gate_passed": bool(
            dissipation_monotonic and dissipation_values[-1] > 0.0
        ),
        "final_state": state.to_dict(),
        "history": rows,
    }
