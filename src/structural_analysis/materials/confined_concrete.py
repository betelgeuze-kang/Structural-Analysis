"""Bounded uniaxial confined-concrete compression envelope."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any

from structural_analysis.materials.admissibility import (
    MaterialAdmissibility,
    require_scalar_loading_path_admissible,
)


CONFINED_CONCRETE_PROFILE = "mander_uniaxial_monotonic_compression.v1"
CONFINED_CONCRETE_STATE_SCHEMA_VERSION = "confined-concrete-envelope-state.v1"
CONFINED_CONCRETE_CLAIM_BOUNDARY = (
    "Monotonic uniaxial compression-envelope candidate only. It does not model "
    "cyclic pinching, multiaxial stress, bar buckling, bond slip, localization, "
    "member failure, published validation, or design-code authority."
)
_STATE_DOMAIN = b"structural-analysis/confined-concrete-envelope-state/v1\0"


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


@dataclass(frozen=True)
class ConfinedConcreteMaterial:
    unconfined_compressive_strength_mpa: float = 30.0
    elastic_modulus_mpa: float = 30_000.0
    unconfined_peak_strain: float = 0.002
    effective_lateral_pressure_mpa: float = 0.0
    ultimate_compressive_strain: float = 0.02
    residual_strength_ratio: float = 0.05
    material_id: str = "confined_concrete_mander_1d"
    loading_domain: str = "monotonic_compression"
    supports_unloading: bool = False
    supports_reversal: bool = False
    supports_cyclic: bool = False
    supports_tension: bool = False
    supports_compression: bool = True
    supports_multiaxial: bool = False

    def __post_init__(self) -> None:
        for name in (
            "unconfined_compressive_strength_mpa",
            "elastic_modulus_mpa",
            "unconfined_peak_strain",
            "effective_lateral_pressure_mpa",
            "ultimate_compressive_strain",
            "residual_strength_ratio",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if self.unconfined_compressive_strength_mpa <= 0.0:
            raise ValueError("unconfined_compressive_strength_mpa must be positive")
        if self.elastic_modulus_mpa <= 0.0:
            raise ValueError("elastic_modulus_mpa must be positive")
        if self.unconfined_peak_strain <= 0.0:
            raise ValueError("unconfined_peak_strain must be positive")
        if self.effective_lateral_pressure_mpa < 0.0:
            raise ValueError("effective_lateral_pressure_mpa must be non-negative")
        if self.ultimate_compressive_strain <= self.confined_peak_strain:
            raise ValueError(
                "ultimate_compressive_strain must exceed confined_peak_strain"
            )
        if not 0.0 <= self.residual_strength_ratio < 1.0:
            raise ValueError("residual_strength_ratio must be in [0, 1)")
        if not self.material_id.strip():
            raise ValueError("material_id must be non-empty")
        if self.elastic_modulus_mpa <= self.secant_peak_modulus_mpa:
            raise ValueError(
                "elastic_modulus_mpa must exceed the confined peak secant modulus"
            )

    @property
    def confined_compressive_strength_mpa(self) -> float:
        unconfined = self.unconfined_compressive_strength_mpa
        ratio = self.effective_lateral_pressure_mpa / unconfined
        return unconfined * (
            -1.254 + 2.254 * math.sqrt(1.0 + 7.94 * ratio) - 2.0 * ratio
        )

    @property
    def confinement_strength_gain(self) -> float:
        return (
            self.confined_compressive_strength_mpa
            / self.unconfined_compressive_strength_mpa
        )

    @property
    def confined_peak_strain(self) -> float:
        return self.unconfined_peak_strain * (
            1.0 + 5.0 * (self.confinement_strength_gain - 1.0)
        )

    @property
    def secant_peak_modulus_mpa(self) -> float:
        return self.confined_compressive_strength_mpa / self.confined_peak_strain

    @property
    def shape_parameter(self) -> float:
        return self.elastic_modulus_mpa / (
            self.elastic_modulus_mpa - self.secant_peak_modulus_mpa
        )

    @property
    def admissibility(self) -> MaterialAdmissibility:
        return MaterialAdmissibility(
            loading_domain=self.loading_domain,
            supports_unloading=self.supports_unloading,
            supports_reversal=self.supports_reversal,
            supports_cyclic=self.supports_cyclic,
            supports_tension=self.supports_tension,
            supports_compression=self.supports_compression,
            supports_multiaxial=self.supports_multiaxial,
        )

    def initial_state(self) -> ConfinedConcreteState:
        return ConfinedConcreteState()

    def integrate(
        self,
        strain: float,
        committed_state: ConfinedConcreteState,
    ) -> StatefulConfinedConcreteResponse:
        if type(committed_state) is not ConfinedConcreteState:
            raise ValueError("committed_state must be an exact ConfinedConcreteState")
        value = _finite("strain", strain)
        require_scalar_loading_path_admissible(
            self.admissibility,
            (committed_state.strain, value),
            owner=self.material_id,
        )
        envelope = confined_concrete_response(value, self)
        state = ConfinedConcreteState(
            strain=value,
            maximum_compressive_strain=max(
                committed_state.maximum_compressive_strain,
                max(-value, 0.0),
            ),
        )
        return StatefulConfinedConcreteResponse(
            strain=value,
            stress_mpa=envelope.stress_mpa,
            consistent_tangent_mpa=envelope.consistent_tangent_mpa,
            branch=envelope.branch,
            confinement_strength_gain=envelope.confinement_strength_gain,
            committed_state_hash=committed_state.state_hash,
            state=state,
        )


@dataclass(frozen=True)
class ConfinedConcreteState:
    """Immutable envelope lineage used by member checkpoints.

    The maximum strain is evidence metadata, not an unloading rule. Re-evaluating
    the accepted strain from the accepted state is idempotent, which keeps
    checkpoint validation exact while preserving the monotonic-envelope boundary.
    """

    strain: float = 0.0
    maximum_compressive_strain: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "strain", _finite("strain", self.strain))
        object.__setattr__(
            self,
            "maximum_compressive_strain",
            _finite(
                "maximum_compressive_strain",
                self.maximum_compressive_strain,
            ),
        )
        if self.maximum_compressive_strain < 0.0:
            raise ValueError("maximum_compressive_strain must be non-negative")
        if self.maximum_compressive_strain + 1.0e-15 < max(-self.strain, 0.0):
            raise ValueError(
                "maximum_compressive_strain cannot be below the current strain"
            )

    def canonical_bytes(self) -> bytes:
        return _STATE_DOMAIN + struct.pack(
            "<2d",
            self.strain,
            self.maximum_compressive_strain,
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONFINED_CONCRETE_STATE_SCHEMA_VERSION,
            "strain": self.strain,
            "maximum_compressive_strain": self.maximum_compressive_strain,
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class ConfinedConcreteResponse:
    strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    branch: str
    confinement_strength_gain: float
    profile: str = CONFINED_CONCRETE_PROFILE
    claim_boundary: str = CONFINED_CONCRETE_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "strain": self.strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "branch": self.branch,
            "confinement_strength_gain": self.confinement_strength_gain,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class StatefulConfinedConcreteResponse:
    strain: float
    stress_mpa: float
    consistent_tangent_mpa: float
    branch: str
    confinement_strength_gain: float
    committed_state_hash: str
    state: ConfinedConcreteState
    profile: str = CONFINED_CONCRETE_PROFILE
    claim_boundary: str = CONFINED_CONCRETE_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "strain": self.strain,
            "stress_mpa": self.stress_mpa,
            "consistent_tangent_mpa": self.consistent_tangent_mpa,
            "branch": self.branch,
            "confinement_strength_gain": self.confinement_strength_gain,
            "committed_state_hash": self.committed_state_hash,
            "trial_state": self.state.to_dict(),
            "claim_boundary": self.claim_boundary,
        }


def confined_concrete_response(
    strain: float,
    material: ConfinedConcreteMaterial | None = None,
) -> ConfinedConcreteResponse:
    selected = material or ConfinedConcreteMaterial()
    value = _finite("strain", strain)
    gain = selected.confinement_strength_gain
    if value > 0.0:
        return ConfinedConcreteResponse(
            strain=value,
            stress_mpa=0.0,
            consistent_tangent_mpa=0.0,
            branch="compression_only_tension_open",
            confinement_strength_gain=gain,
        )
    magnitude = -value
    if magnitude > selected.ultimate_compressive_strain:
        residual = _envelope_magnitude(
            selected.ultimate_compressive_strain,
            selected,
        )[0]
        residual = min(
            residual,
            selected.residual_strength_ratio
            * selected.confined_compressive_strength_mpa,
        )
        return ConfinedConcreteResponse(
            strain=value,
            stress_mpa=-residual,
            consistent_tangent_mpa=0.0,
            branch="residual_cutoff",
            confinement_strength_gain=gain,
        )
    stress, tangent = _envelope_magnitude(magnitude, selected)
    return ConfinedConcreteResponse(
        strain=value,
        stress_mpa=-stress,
        consistent_tangent_mpa=tangent,
        branch=(
            "ascending"
            if magnitude < selected.confined_peak_strain
            else "peak"
            if math.isclose(
                magnitude,
                selected.confined_peak_strain,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            else "descending"
        ),
        confinement_strength_gain=gain,
    )


def _envelope_magnitude(
    compressive_strain_magnitude: float,
    material: ConfinedConcreteMaterial,
) -> tuple[float, float]:
    x = compressive_strain_magnitude / material.confined_peak_strain
    r = material.shape_parameter
    if x == 0.0:
        return 0.0, material.elastic_modulus_mpa
    power = x**r
    denominator = r - 1.0 + power
    stress = material.confined_compressive_strength_mpa * r * x / denominator
    tangent = (
        material.confined_compressive_strength_mpa
        * r
        * (r - 1.0)
        * (1.0 - power)
        / (denominator * denominator * material.confined_peak_strain)
    )
    return stress, tangent


def finite_difference_confined_concrete_tangent(
    material: ConfinedConcreteMaterial,
    *,
    strain: float,
    epsilon: float = 1.0e-8,
) -> dict[str, Any]:
    step = _finite("epsilon", epsilon)
    if step <= 0.0:
        raise ValueError("epsilon must be positive")
    center = confined_concrete_response(strain, material)
    forward = confined_concrete_response(strain + step, material)
    backward = confined_concrete_response(strain - step, material)
    finite_difference = (forward.stress_mpa - backward.stress_mpa) / (2.0 * step)
    scale = max(
        abs(center.consistent_tangent_mpa),
        abs(finite_difference),
        1.0,
    )
    return {
        "profile": CONFINED_CONCRETE_PROFILE,
        "analytic_tangent_mpa": center.consistent_tangent_mpa,
        "finite_difference_tangent_mpa": finite_difference,
        "relative_error": abs(center.consistent_tangent_mpa - finite_difference)
        / scale,
        "claim_boundary": CONFINED_CONCRETE_CLAIM_BOUNDARY,
    }


__all__ = [
    "CONFINED_CONCRETE_CLAIM_BOUNDARY",
    "CONFINED_CONCRETE_PROFILE",
    "CONFINED_CONCRETE_STATE_SCHEMA_VERSION",
    "ConfinedConcreteMaterial",
    "ConfinedConcreteResponse",
    "ConfinedConcreteState",
    "StatefulConfinedConcreteResponse",
    "confined_concrete_response",
    "finite_difference_confined_concrete_tangent",
]
