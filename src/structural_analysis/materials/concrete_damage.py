"""Thermodynamically bounded 1D asymmetric concrete damage seed."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any, Iterable


STATE_SCHEMA_VERSION = "uniaxial-asymmetric-concrete-damage-state.v1"
DAMAGE_ALGORITHM = "history_max_exponential_tension_compression_damage"
TANGENT_DEFINITION = "algorithmic_consistent_d_stress_d_total_strain"
FRACTURE_ENERGY_DAMAGE_ALGORITHM = (
    "crack_band_exponential_traction_effective_crack_opening"
)
FRACTURE_ENERGY_TANGENT_DEFINITION = "implicit_consistent_d_traction_d_total_strain"
_STATE_HASH_DOMAIN = b"structural-analysis/concrete-damage-state/v1\0"


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class ConcreteDamageState:
    tensile_history_strain: float = 0.0
    compressive_history_strain: float = 0.0
    tensile_damage: float = 0.0
    compressive_damage: float = 0.0
    dissipated_energy_density_mj_per_m3: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "tensile_history_strain",
            "compressive_history_strain",
            "tensile_damage",
            "compressive_damage",
            "dissipated_energy_density_mj_per_m3",
        ):
            _require_finite(name, getattr(self, name))
        if self.tensile_history_strain < 0.0:
            raise ValueError("tensile_history_strain must be non-negative")
        if self.compressive_history_strain < 0.0:
            raise ValueError("compressive_history_strain must be non-negative")
        if not 0.0 <= self.tensile_damage < 1.0:
            raise ValueError("tensile_damage must be in [0, 1)")
        if not 0.0 <= self.compressive_damage < 1.0:
            raise ValueError("compressive_damage must be in [0, 1)")
        if self.dissipated_energy_density_mj_per_m3 < 0.0:
            raise ValueError(
                "dissipated_energy_density_mj_per_m3 must be non-negative"
            )

    def canonical_bytes(self) -> bytes:
        return _STATE_HASH_DOMAIN + struct.pack(
            "<5d",
            self.tensile_history_strain,
            self.compressive_history_strain,
            self.tensile_damage,
            self.compressive_damage,
            self.dissipated_energy_density_mj_per_m3,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "tensile_history_strain": self.tensile_history_strain,
            "compressive_history_strain": self.compressive_history_strain,
            "tensile_damage": self.tensile_damage,
            "compressive_damage": self.compressive_damage,
            "dissipated_energy_density_mj_per_m3": (
                self.dissipated_energy_density_mj_per_m3
            ),
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class ConcreteDamageResponse:
    total_strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    active_branch: str
    active_damage: float
    damage_evolved: bool
    tensile_damage_increment: float
    compressive_damage_increment: float
    committed_state_hash: str
    state: ConcreteDamageState

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_strain": self.total_strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "active_branch": self.active_branch,
            "active_damage": self.active_damage,
            "damage_evolved": self.damage_evolved,
            "tensile_damage_increment": self.tensile_damage_increment,
            "compressive_damage_increment": self.compressive_damage_increment,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class AsymmetricConcreteDamageMaterial:
    """Elastic-to-peak tension/compression law with irreversible softening."""

    elastic_modulus_mpa: float = 30_000.0
    tensile_strength_mpa: float = 3.0
    compressive_strength_mpa: float = 30.0
    tensile_softening_rate: float = 3_000.0
    compressive_softening_rate: float = 400.0
    history_tolerance: float = 1.0e-14
    material_id: str = "concrete_asymmetric_exponential_damage_1d"

    def __post_init__(self) -> None:
        for name in (
            "elastic_modulus_mpa",
            "tensile_strength_mpa",
            "compressive_strength_mpa",
            "tensile_softening_rate",
            "compressive_softening_rate",
            "history_tolerance",
        ):
            _require_finite(name, getattr(self, name))
        if self.elastic_modulus_mpa <= 0.0:
            raise ValueError("elastic_modulus_mpa must be positive")
        if self.tensile_strength_mpa <= 0.0:
            raise ValueError("tensile_strength_mpa must be positive")
        if self.compressive_strength_mpa <= 0.0:
            raise ValueError("compressive_strength_mpa must be positive")
        if self.tensile_softening_rate <= 0.0:
            raise ValueError("tensile_softening_rate must be positive")
        if self.compressive_softening_rate <= 0.0:
            raise ValueError("compressive_softening_rate must be positive")
        if self.history_tolerance < 0.0:
            raise ValueError("history_tolerance must be non-negative")
        if not self.material_id:
            raise ValueError("material_id must be non-empty")

    @property
    def tensile_threshold_strain(self) -> float:
        return self.tensile_strength_mpa / self.elastic_modulus_mpa

    @property
    def damage_algorithm(self) -> str:
        return DAMAGE_ALGORITHM

    @property
    def tangent_definition(self) -> str:
        return TANGENT_DEFINITION

    @property
    def compressive_threshold_strain(self) -> float:
        return self.compressive_strength_mpa / self.elastic_modulus_mpa

    def initial_state(self) -> ConcreteDamageState:
        return ConcreteDamageState()

    @staticmethod
    def _damage_and_derivative(
        history_strain: float,
        *,
        threshold_strain: float,
        softening_rate: float,
    ) -> tuple[float, float]:
        if history_strain <= threshold_strain:
            return 0.0, 0.0
        survival = (
            threshold_strain
            / history_strain
            * math.exp(
                -softening_rate * (history_strain - threshold_strain)
            )
        )
        damage = min(1.0 - survival, math.nextafter(1.0, 0.0))
        derivative = survival * (1.0 / history_strain + softening_rate)
        return damage, derivative

    def integrate(
        self,
        total_strain: float,
        committed_state: ConcreteDamageState,
    ) -> ConcreteDamageResponse:
        strain = _require_finite("total_strain", total_strain)
        tensile_measure = max(strain, 0.0)
        compressive_measure = max(-strain, 0.0)
        next_tensile_history = max(
            committed_state.tensile_history_strain,
            tensile_measure,
        )
        next_compressive_history = max(
            committed_state.compressive_history_strain,
            compressive_measure,
        )
        tensile_damage, tensile_derivative = self._damage_and_derivative(
            next_tensile_history,
            threshold_strain=self.tensile_threshold_strain,
            softening_rate=self.tensile_softening_rate,
        )
        compressive_damage, compressive_derivative = self._damage_and_derivative(
            next_compressive_history,
            threshold_strain=self.compressive_threshold_strain,
            softening_rate=self.compressive_softening_rate,
        )
        tensile_increment = max(
            tensile_damage - committed_state.tensile_damage,
            0.0,
        )
        compressive_increment = max(
            compressive_damage - committed_state.compressive_damage,
            0.0,
        )
        dissipated_increment = 0.5 * self.elastic_modulus_mpa * strain**2 * (
            tensile_increment + compressive_increment
        )
        next_state = ConcreteDamageState(
            tensile_history_strain=next_tensile_history,
            compressive_history_strain=next_compressive_history,
            tensile_damage=tensile_damage,
            compressive_damage=compressive_damage,
            dissipated_energy_density_mj_per_m3=(
                committed_state.dissipated_energy_density_mj_per_m3
                + dissipated_increment
            ),
        )

        if strain >= 0.0:
            active_branch = "tension"
            active_measure = tensile_measure
            active_damage = tensile_damage
            active_derivative = tensile_derivative
            history_advanced = bool(
                tensile_measure
                > committed_state.tensile_history_strain
                + self.history_tolerance
            )
        else:
            active_branch = "compression"
            active_measure = compressive_measure
            active_damage = compressive_damage
            active_derivative = compressive_derivative
            history_advanced = bool(
                compressive_measure
                > committed_state.compressive_history_strain
                + self.history_tolerance
            )
        stress = (1.0 - active_damage) * self.elastic_modulus_mpa * strain
        if history_advanced and active_derivative > 0.0:
            tangent = self.elastic_modulus_mpa * (
                1.0 - active_damage - active_measure * active_derivative
            )
        else:
            tangent = self.elastic_modulus_mpa * (1.0 - active_damage)
        damage_evolved = bool(tensile_increment > 0.0 or compressive_increment > 0.0)
        return ConcreteDamageResponse(
            total_strain=strain,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            active_branch=active_branch,
            active_damage=active_damage,
            damage_evolved=damage_evolved,
            tensile_damage_increment=tensile_increment,
            compressive_damage_increment=compressive_increment,
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


@dataclass(frozen=True)
class FractureEnergyConcreteDamageMaterial(AsymmetricConcreteDamageMaterial):
    """Uniaxial crack-band damage regularized by characteristic band length.

    The post-peak branch is defined by ``sigma = f * exp(-f*w/Gf)`` and
    ``w = h*(kappa-sigma/E)``.  Supplying ``h`` makes the traction-opening
    curve and asymptotic energy per crack area independent of mesh length.
    """

    tensile_softening_rate: float = field(init=False, default=1.0)
    compressive_softening_rate: float = field(init=False, default=1.0)
    characteristic_length_m: float = 0.01
    tensile_fracture_energy_n_per_m: float = 100.0
    compressive_fracture_energy_n_per_m: float = 20_000.0
    material_id: str = "concrete_fracture_energy_crack_band_1d"

    def __post_init__(self) -> None:
        characteristic_length = _require_finite(
            "characteristic_length_m", self.characteristic_length_m
        )
        tensile_energy = _require_finite(
            "tensile_fracture_energy_n_per_m",
            self.tensile_fracture_energy_n_per_m,
        )
        compressive_energy = _require_finite(
            "compressive_fracture_energy_n_per_m",
            self.compressive_fracture_energy_n_per_m,
        )
        if characteristic_length <= 0.0:
            raise ValueError("characteristic_length_m must be positive")
        if tensile_energy <= 0.0 or compressive_energy <= 0.0:
            raise ValueError("fracture energies must be positive")
        tensile_rate = (
            characteristic_length
            * float(self.tensile_strength_mpa)
            * 1.0e6
            / tensile_energy
        )
        compressive_rate = (
            characteristic_length
            * float(self.compressive_strength_mpa)
            * 1.0e6
            / compressive_energy
        )
        object.__setattr__(self, "characteristic_length_m", characteristic_length)
        object.__setattr__(self, "tensile_fracture_energy_n_per_m", tensile_energy)
        object.__setattr__(
            self, "compressive_fracture_energy_n_per_m", compressive_energy
        )
        object.__setattr__(self, "tensile_softening_rate", tensile_rate)
        object.__setattr__(self, "compressive_softening_rate", compressive_rate)
        super().__post_init__()
        for branch, strength, rate in (
            ("tensile", self.tensile_strength_mpa, tensile_rate),
            ("compressive", self.compressive_strength_mpa, compressive_rate),
        ):
            if rate * strength / self.elastic_modulus_mpa >= 1.0:
                raise ValueError(
                    f"{branch} crack-band mapping must satisfy "
                    "softening_rate*strength/elastic_modulus < 1"
                )

    @property
    def damage_algorithm(self) -> str:
        return FRACTURE_ENERGY_DAMAGE_ALGORITHM

    @property
    def tangent_definition(self) -> str:
        return FRACTURE_ENERGY_TANGENT_DEFINITION

    @staticmethod
    def _traction_and_tangent(
        history_strain: float,
        *,
        elastic_modulus_mpa: float,
        strength_mpa: float,
        softening_rate: float,
    ) -> tuple[float, float, float]:
        threshold = strength_mpa / elastic_modulus_mpa
        if history_strain <= threshold:
            return elastic_modulus_mpa * history_strain, elastic_modulus_mpa, 0.0

        lower = 0.0
        upper = strength_mpa
        for _ in range(96):
            trial = 0.5 * (lower + upper)
            equation = (
                math.log(trial / strength_mpa)
                + softening_rate * history_strain
                - softening_rate * trial / elastic_modulus_mpa
            )
            if equation > 0.0:
                upper = trial
            else:
                lower = trial
        traction = 0.5 * (lower + upper)
        tangent = -softening_rate / (
            1.0 / traction - softening_rate / elastic_modulus_mpa
        )
        damage = min(
            1.0 - traction / (elastic_modulus_mpa * history_strain),
            math.nextafter(1.0, 0.0),
        )
        return traction, tangent, max(damage, 0.0)

    def _branch_dissipated_energy_density(
        self,
        history_strain: float,
        *,
        strength_mpa: float,
        fracture_energy_n_per_m: float,
        softening_rate: float,
    ) -> float:
        threshold = strength_mpa / self.elastic_modulus_mpa
        if history_strain <= threshold:
            return 0.0
        traction, _tangent, _damage = self._traction_and_tangent(
            history_strain,
            elastic_modulus_mpa=self.elastic_modulus_mpa,
            strength_mpa=strength_mpa,
            softening_rate=softening_rate,
        )
        crack_opening_m = self.characteristic_length_m * (
            history_strain - traction / self.elastic_modulus_mpa
        )
        fracture_energy_mj_per_m2 = fracture_energy_n_per_m / 1.0e6
        dissipated_mj_per_m2 = (
            fracture_energy_mj_per_m2 * (1.0 - traction / strength_mpa)
            - 0.5 * traction * crack_opening_m
        )
        return max(dissipated_mj_per_m2 / self.characteristic_length_m, 0.0)

    def integrate(
        self,
        total_strain: float,
        committed_state: ConcreteDamageState,
    ) -> ConcreteDamageResponse:
        strain = _require_finite("total_strain", total_strain)
        if type(committed_state) is not ConcreteDamageState:
            raise ValueError("committed_state must be a ConcreteDamageState")
        tensile_measure = max(strain, 0.0)
        compressive_measure = max(-strain, 0.0)
        tensile_history = max(committed_state.tensile_history_strain, tensile_measure)
        compressive_history = max(
            committed_state.compressive_history_strain, compressive_measure
        )
        _tensile_traction, tensile_tangent, tensile_damage = self._traction_and_tangent(
            tensile_history,
            elastic_modulus_mpa=self.elastic_modulus_mpa,
            strength_mpa=self.tensile_strength_mpa,
            softening_rate=self.tensile_softening_rate,
        )
        _compressive_traction, compressive_tangent, compressive_damage = (
            self._traction_and_tangent(
                compressive_history,
                elastic_modulus_mpa=self.elastic_modulus_mpa,
                strength_mpa=self.compressive_strength_mpa,
                softening_rate=self.compressive_softening_rate,
            )
        )
        tensile_increment = max(tensile_damage - committed_state.tensile_damage, 0.0)
        compressive_increment = max(
            compressive_damage - committed_state.compressive_damage, 0.0
        )
        computed_dissipation = self._branch_dissipated_energy_density(
            tensile_history,
            strength_mpa=self.tensile_strength_mpa,
            fracture_energy_n_per_m=self.tensile_fracture_energy_n_per_m,
            softening_rate=self.tensile_softening_rate,
        ) + self._branch_dissipated_energy_density(
            compressive_history,
            strength_mpa=self.compressive_strength_mpa,
            fracture_energy_n_per_m=self.compressive_fracture_energy_n_per_m,
            softening_rate=self.compressive_softening_rate,
        )
        next_state = ConcreteDamageState(
            tensile_history_strain=tensile_history,
            compressive_history_strain=compressive_history,
            tensile_damage=tensile_damage,
            compressive_damage=compressive_damage,
            dissipated_energy_density_mj_per_m3=max(
                committed_state.dissipated_energy_density_mj_per_m3,
                computed_dissipation,
            ),
        )

        if strain >= 0.0:
            active_branch = "tension"
            active_damage = tensile_damage
            loading_tangent = tensile_tangent
            history_advanced = bool(
                tensile_measure
                > committed_state.tensile_history_strain + self.history_tolerance
            )
        else:
            active_branch = "compression"
            active_damage = compressive_damage
            loading_tangent = compressive_tangent
            history_advanced = bool(
                compressive_measure
                > committed_state.compressive_history_strain + self.history_tolerance
            )
        stress = (1.0 - active_damage) * self.elastic_modulus_mpa * strain
        tangent = (
            loading_tangent
            if history_advanced
            else self.elastic_modulus_mpa * (1.0 - active_damage)
        )
        return ConcreteDamageResponse(
            total_strain=strain,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            active_branch=active_branch,
            active_damage=active_damage,
            damage_evolved=bool(tensile_increment > 0.0 or compressive_increment > 0.0),
            tensile_damage_increment=tensile_increment,
            compressive_damage_increment=compressive_increment,
            committed_state_hash=committed_state.state_hash,
            state=next_state,
        )


def finite_difference_concrete_damage_tangent_check(
    material: AsymmetricConcreteDamageMaterial,
    committed_state: ConcreteDamageState,
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
        "damage_algorithm": material.damage_algorithm,
        "tangent_definition": material.tangent_definition,
        "active_branch": center.active_branch,
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


def integrate_concrete_damage_history(
    material: AsymmetricConcreteDamageMaterial,
    strains: Iterable[float],
    *,
    initial_state: ConcreteDamageState | None = None,
) -> dict[str, Any]:
    strain_path = tuple(_require_finite("strain", value) for value in strains)
    if not strain_path:
        raise ValueError("strains must contain at least one value")
    state = initial_state or material.initial_state()
    previous_strain = 0.0
    previous_stress = material.integrate(0.0, state).stress_mpa
    previous_increment_sign = 0
    reversal_count = 0
    work_density = 0.0
    dissipation_values = [state.dissipated_energy_density_mj_per_m3]
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
        rows.append(
            {
                "step_index": step_index,
                "parent_state_hash": parent.state_hash,
                "increment_sign": increment_sign,
                **response.to_dict(),
            }
        )
        state = response.state
        dissipation_values.append(state.dissipated_energy_density_mj_per_m3)
        previous_strain = strain
        previous_stress = response.stress_mpa

    dissipation_monotonic = all(
        current + 1.0e-15 >= previous
        for previous, current in zip(dissipation_values, dissipation_values[1:])
    )
    damage_irreversible = all(
        current["trial_state"]["tensile_damage"]
        + 1.0e-15
        >= previous["trial_state"]["tensile_damage"]
        and current["trial_state"]["compressive_damage"]
        + 1.0e-15
        >= previous["trial_state"]["compressive_damage"]
        for previous, current in zip(rows, rows[1:])
    )
    return {
        "material_id": material.material_id,
        "damage_algorithm": material.damage_algorithm,
        "strain_path": list(strain_path),
        "step_count": len(rows),
        "reversal_count": reversal_count,
        "damage_evolution_step_count": sum(
            bool(row["damage_evolved"]) for row in rows
        ),
        "stress_strain_work_density_mj_per_m3": work_density,
        "cumulative_dissipated_energy_density_mj_per_m3": (
            state.dissipated_energy_density_mj_per_m3
        ),
        "dissipation_nonnegative_monotonic": dissipation_monotonic,
        "damage_irreversible": damage_irreversible,
        "energy_damage_gate_passed": bool(
            dissipation_monotonic
            and damage_irreversible
            and state.dissipated_energy_density_mj_per_m3 > 0.0
            and state.tensile_damage > 0.0
            and state.compressive_damage > 0.0
        ),
        "final_state": state.to_dict(),
        "history": rows,
    }
