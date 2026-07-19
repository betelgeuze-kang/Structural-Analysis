"""State-updated uniaxial steel plasticity with deterministic return mapping."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Iterable


STATE_SCHEMA_VERSION = "uniaxial-combined-hardening-state.v1"
RETURN_MAPPING_ALGORITHM = "backward_euler_1d_radial_return"
TANGENT_DEFINITION = "algorithmic_consistent_d_stress_d_total_strain"
_STATE_HASH_DOMAIN = b"structural-analysis/uniaxial-plasticity-state/v1\0"


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class UniaxialPlasticityState:
    """Immutable committed integration-point state.

    Stress-like quantities use MPa. Stress times strain is therefore MJ/m3.
    """

    plastic_strain: float = 0.0
    backstress_mpa: float = 0.0
    accumulated_plastic_strain: float = 0.0
    dissipated_energy_density_mj_per_m3: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "plastic_strain",
            "backstress_mpa",
            "accumulated_plastic_strain",
            "dissipated_energy_density_mj_per_m3",
        ):
            _require_finite(name, getattr(self, name))
        if self.accumulated_plastic_strain < 0.0:
            raise ValueError("accumulated_plastic_strain must be non-negative")
        if self.dissipated_energy_density_mj_per_m3 < 0.0:
            raise ValueError(
                "dissipated_energy_density_mj_per_m3 must be non-negative"
            )

    def canonical_bytes(self) -> bytes:
        """Return a platform-independent little-endian binary state encoding."""
        return _STATE_HASH_DOMAIN + struct.pack(
            "<4d",
            self.plastic_strain,
            self.backstress_mpa,
            self.accumulated_plastic_strain,
            self.dissipated_energy_density_mj_per_m3,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "plastic_strain": self.plastic_strain,
            "backstress_mpa": self.backstress_mpa,
            "accumulated_plastic_strain": self.accumulated_plastic_strain,
            "dissipated_energy_density_mj_per_m3": (
                self.dissipated_energy_density_mj_per_m3
            ),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class UniaxialPlasticityResponse:
    total_strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    elastic_strain: float
    yielded: bool
    plastic_multiplier_increment: float
    trial_yield_function_mpa: float
    final_yield_function_mpa: float
    committed_state_hash: str
    state: UniaxialPlasticityState

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_strain": self.total_strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "elastic_strain": self.elastic_strain,
            "yielded": self.yielded,
            "plastic_multiplier_increment": self.plastic_multiplier_increment,
            "trial_yield_function_mpa": self.trial_yield_function_mpa,
            "final_yield_function_mpa": self.final_yield_function_mpa,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class BilinearCombinedHardeningSteel:
    """Small-strain J2-equivalent 1D steel with linear combined hardening."""

    elastic_modulus_mpa: float = 200_000.0
    yield_stress_mpa: float = 250.0
    isotropic_hardening_modulus_mpa: float = 3_000.0
    kinematic_hardening_modulus_mpa: float = 5_000.0
    yield_tolerance_mpa: float = 1.0e-10
    material_id: str = "steel_bilinear_combined_hardening_1d"

    def __post_init__(self) -> None:
        for name in (
            "elastic_modulus_mpa",
            "yield_stress_mpa",
            "isotropic_hardening_modulus_mpa",
            "kinematic_hardening_modulus_mpa",
            "yield_tolerance_mpa",
        ):
            _require_finite(name, getattr(self, name))
        if self.elastic_modulus_mpa <= 0.0:
            raise ValueError("elastic_modulus_mpa must be positive")
        if self.yield_stress_mpa <= 0.0:
            raise ValueError("yield_stress_mpa must be positive")
        if self.isotropic_hardening_modulus_mpa < 0.0:
            raise ValueError("isotropic_hardening_modulus_mpa must be non-negative")
        if self.kinematic_hardening_modulus_mpa < 0.0:
            raise ValueError("kinematic_hardening_modulus_mpa must be non-negative")
        if self.yield_tolerance_mpa < 0.0:
            raise ValueError("yield_tolerance_mpa must be non-negative")
        if not str(self.material_id).strip():
            raise ValueError("material_id must be non-empty")

    @property
    def hardening_modulus_mpa(self) -> float:
        return (
            self.isotropic_hardening_modulus_mpa
            + self.kinematic_hardening_modulus_mpa
        )

    @property
    def plastic_consistent_tangent_mpa(self) -> float:
        hardening = self.hardening_modulus_mpa
        return self.elastic_modulus_mpa * hardening / (
            self.elastic_modulus_mpa + hardening
        )

    def initial_state(self) -> UniaxialPlasticityState:
        return UniaxialPlasticityState()

    def integrate(
        self,
        total_strain: float,
        committed_state: UniaxialPlasticityState,
    ) -> UniaxialPlasticityResponse:
        """Evaluate one trial strain from an immutable committed state."""
        strain = _require_finite("total_strain", total_strain)
        elastic_trial = strain - committed_state.plastic_strain
        trial_stress = self.elastic_modulus_mpa * elastic_trial
        relative_trial_stress = trial_stress - committed_state.backstress_mpa
        yield_radius = self.yield_stress_mpa + (
            self.isotropic_hardening_modulus_mpa
            * committed_state.accumulated_plastic_strain
        )
        trial_yield = abs(relative_trial_stress) - yield_radius

        if trial_yield <= self.yield_tolerance_mpa:
            stress = trial_stress
            tangent = self.elastic_modulus_mpa
            plastic_increment = 0.0
            next_state = committed_state
            yielded = False
        else:
            flow_direction = 1.0 if relative_trial_stress >= 0.0 else -1.0
            denominator = self.elastic_modulus_mpa + self.hardening_modulus_mpa
            plastic_increment = trial_yield / denominator
            next_state = UniaxialPlasticityState(
                plastic_strain=(
                    committed_state.plastic_strain
                    + plastic_increment * flow_direction
                ),
                backstress_mpa=(
                    committed_state.backstress_mpa
                    + self.kinematic_hardening_modulus_mpa
                    * plastic_increment
                    * flow_direction
                ),
                accumulated_plastic_strain=(
                    committed_state.accumulated_plastic_strain
                    + plastic_increment
                ),
                dissipated_energy_density_mj_per_m3=(
                    committed_state.dissipated_energy_density_mj_per_m3
                    + self.yield_stress_mpa * plastic_increment
                ),
            )
            stress = trial_stress - (
                self.elastic_modulus_mpa * plastic_increment * flow_direction
            )
            tangent = self.plastic_consistent_tangent_mpa
            yielded = True

        elastic_strain = strain - next_state.plastic_strain
        final_yield = abs(stress - next_state.backstress_mpa) - (
            self.yield_stress_mpa
            + self.isotropic_hardening_modulus_mpa
            * next_state.accumulated_plastic_strain
        )
        return UniaxialPlasticityResponse(
            total_strain=strain,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            elastic_strain=elastic_strain,
            yielded=yielded,
            plastic_multiplier_increment=plastic_increment,
            trial_yield_function_mpa=trial_yield,
            final_yield_function_mpa=final_yield,
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


def finite_difference_consistent_tangent_check(
    material: BilinearCombinedHardeningSteel,
    committed_state: UniaxialPlasticityState,
    *,
    total_strain: float,
    epsilon: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    """Compare the algorithmic tangent with a same-parent central difference."""
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
    return {
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "tangent_definition": TANGENT_DEFINITION,
        "total_strain": float(total_strain),
        "finite_difference_epsilon": epsilon,
        "analytic_consistent_tangent_mpa": center.consistent_tangent_mpa,
        "finite_difference_tangent_mpa": finite_difference,
        "absolute_error_mpa": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "same_committed_parent_state": bool(
            forward.committed_state_hash
            == center.committed_state_hash
            == backward.committed_state_hash
        ),
        "pass": bool(
            relative_error <= relative_tolerance
            and forward.committed_state_hash
            == center.committed_state_hash
            == backward.committed_state_hash
        ),
    }


def integrate_strain_history(
    material: BilinearCombinedHardeningSteel,
    strains: Iterable[float],
    *,
    initial_state: UniaxialPlasticityState | None = None,
) -> dict[str, Any]:
    """Commit a deterministic strain path and audit plastic energy/reversals."""
    strain_path = tuple(_require_finite("strain", value) for value in strains)
    if not strain_path:
        raise ValueError("strains must contain at least one value")
    state = initial_state or material.initial_state()
    previous_strain = 0.0
    previous_stress = material.integrate(previous_strain, state).stress_mpa
    previous_flow_direction = 0
    work_density = 0.0
    reversal_count = 0
    rows: list[dict[str, Any]] = []
    dissipation_values = [state.dissipated_energy_density_mj_per_m3]

    for step_index, strain in enumerate(strain_path, start=1):
        parent_state = state
        response = material.integrate(strain, parent_state)
        work_density += 0.5 * (previous_stress + response.stress_mpa) * (
            strain - previous_strain
        )
        plastic_strain_increment = (
            response.state.plastic_strain - parent_state.plastic_strain
        )
        flow_direction = (
            1
            if plastic_strain_increment > 0.0
            else -1
            if plastic_strain_increment < 0.0
            else 0
        )
        if (
            flow_direction != 0
            and previous_flow_direction != 0
            and flow_direction != previous_flow_direction
        ):
            reversal_count += 1
        if flow_direction != 0:
            previous_flow_direction = flow_direction
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent_state.state_hash,
                "plastic_flow_direction": flow_direction,
                **response.to_dict(),
            }
        )
        state = response.state
        dissipation_values.append(state.dissipated_energy_density_mj_per_m3)
        previous_strain = strain
        previous_stress = response.stress_mpa

    dissipation_monotonic = all(
        current + 1.0e-15 >= previous
        for previous, current in zip(
            dissipation_values,
            dissipation_values[1:],
        )
    )
    return {
        "material_id": material.material_id,
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "strain_path": list(strain_path),
        "step_count": len(rows),
        "yielded_step_count": sum(bool(row["yielded"]) for row in rows),
        "plastic_flow_reversal_count": reversal_count,
        "stress_strain_work_density_mj_per_m3": work_density,
        "cumulative_dissipated_energy_density_mj_per_m3": (
            state.dissipated_energy_density_mj_per_m3
        ),
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "energy_dissipation_gate_passed": bool(
            dissipation_monotonic
            and state.dissipated_energy_density_mj_per_m3 > 0.0
        ),
        "final_state": state.to_dict(),
        "history": rows,
    }
