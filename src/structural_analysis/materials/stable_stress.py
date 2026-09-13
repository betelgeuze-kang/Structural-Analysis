"""Explicit experimental stress evaluation with original binary64 state updates.

These implementations run inside each original material trial. They retain the
original active-set decisions and native state update; they are not a new law,
checkpoint precision scheme, or a post-processing replacement of accepted forces.
"""

from dataclasses import asdict, fields
from fractions import Fraction as F
import math

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
)
from structural_analysis.materials.stateful_fiber_section import StatefulRCFiberSection

STABLE_STRESS_PROFILE = "stable-stress-original-state.v1"


def _response(cls, original, **updates):
    values = {field.name: getattr(original, field.name) for field in fields(original)}
    return cls(**(values | updates))


def _finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("stable stress evaluation exceeds finite binary64 range")
    return result


class StableSteelResponse(UniaxialPlasticityResponse):
    def to_dict(self):
        return super().to_dict() | {"stress_evaluation_profile": STABLE_STRESS_PROFILE}


class StableConcreteResponse(ConcreteDamageResponse):
    def to_dict(self):
        return super().to_dict() | {"stress_evaluation_profile": STABLE_STRESS_PROFILE}


class StableStressSteel(BilinearCombinedHardeningSteel):
    def integrate(self, total_strain, committed_state):
        original = super().integrate(total_strain, committed_state)
        strain = original.total_strain
        if original.yielded:
            # Same flow direction and rounded multiplier as the original trial.
            trial = self.elastic_modulus_mpa * (strain - committed_state.plastic_strain)
            direction = 1 if trial - committed_state.backstress_mpa >= 0 else -1
            stress = _finite(
                F(committed_state.backstress_mpa)
                + direction
                * (
                    F(self.yield_stress_mpa)
                    + F(self.isotropic_hardening_modulus_mpa)
                    * F(committed_state.accumulated_plastic_strain)
                    + (
                        F(self.isotropic_hardening_modulus_mpa)
                        + F(self.kinematic_hardening_modulus_mpa)
                    )
                    * F(original.plastic_multiplier_increment)
                )
            )
        else:
            stress = _finite(
                F(self.elastic_modulus_mpa)
                * (F(strain) - F(committed_state.plastic_strain))
            )
        final_yield = abs(stress - original.state.backstress_mpa) - (
            self.yield_stress_mpa
            + self.isotropic_hardening_modulus_mpa
            * original.state.accumulated_plastic_strain
        )
        return _response(
            StableSteelResponse,
            original,
            stress_mpa=stress,
            final_yield_function_mpa=final_yield,
        )


class StableStressConcrete(AsymmetricConcreteDamageMaterial):
    def integrate(self, total_strain, committed_state):
        original = super().integrate(total_strain, committed_state)
        strain = original.total_strain
        tension = strain >= 0
        history = (
            original.state.tensile_history_strain
            if tension
            else original.state.compressive_history_strain
        )
        parent_history = (
            committed_state.tensile_history_strain
            if tension
            else committed_state.compressive_history_strain
        )
        threshold = (
            self.tensile_threshold_strain
            if tension
            else self.compressive_threshold_strain
        )
        rate = (
            self.tensile_softening_rate if tension else self.compressive_softening_rate
        )
        survival = (
            1.0
            if history <= threshold
            else threshold / history * math.exp(-rate * (history - threshold))
        )
        # Retain the original nextafter(1,0) damage cap and its survival floor.
        floor = 1.0 - math.nextafter(1.0, 0.0)
        effective = max(survival, floor)
        stress = _finite(F(effective) * F(self.elastic_modulus_mpa) * F(strain))
        measure = abs(strain)
        advanced = measure > parent_history + self.history_tolerance
        derivative = 0.0 if history <= threshold else survival * (1.0 / history + rate)
        if advanced and derivative > 0:
            # Algebraically retain the original unclipped derivative, including
            # its existing cap semantics, without subtracting rounded damage.
            tangent = _finite(
                F(self.elastic_modulus_mpa)
                * (F(effective) - F(survival) * F(measure) * (1 / F(history) + F(rate)))
            )
        else:
            tangent = _finite(F(self.elastic_modulus_mpa) * F(effective))
        return _response(
            StableConcreteResponse,
            original,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
        )


class StableStressRCFiberSection(StatefulRCFiberSection):
    def __post_init__(self):
        super().__post_init__()
        if (
            type(self.steel) is not StableStressSteel
            or type(self.concrete) is not StableStressConcrete
        ):
            raise ValueError("stable section requires both explicit stable materials")

    @property
    def contract_hash(self):
        return canonical_hash(
            {
                "base_section_contract_hash": super().contract_hash,
                "material_arithmetic_profile": STABLE_STRESS_PROFILE,
            }
        )


def stable_stress_section(section):
    if type(section) is not StatefulRCFiberSection:
        raise ValueError("original supported RC section required")
    if (
        type(section.steel) is not BilinearCombinedHardeningSteel
        or type(section.concrete) is not AsymmetricConcreteDamageMaterial
    ):
        raise ValueError("original supported steel and concrete laws required")
    return StableStressRCFiberSection(
        fibers=section.fibers,
        section_id=section.section_id,
        steel=StableStressSteel(**asdict(section.steel)),
        concrete=StableStressConcrete(**asdict(section.concrete)),
    )
