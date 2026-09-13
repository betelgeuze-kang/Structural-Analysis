"""Retain rational trial strain for stresses, with original rounded native updates.

Steel uses the original stable active branch plus its sub-ulp strain increment.
Concrete evaluates the original selected history branch in 80-digit arithmetic.
This is an explicit development stress profile, not a new native history scheme.
"""

from dataclasses import asdict, dataclass, fields
from decimal import (
    Decimal,
    localcontext,
    Context,
    ROUND_HALF_EVEN,
    InvalidOperation,
    DivisionByZero,
    Overflow,
)
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
from structural_analysis.materials.stable_stress import (
    StableStressSteel,
    StableStressConcrete,
    _finite,
    _response,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    StatefulFiberSectionResponse,
)
from structural_analysis.materials.direct_fiber_strain import (
    DirectFiberRCSection,
    coordinate_fiber_strains,
)
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder

RETAINED_FIBER_PROFILE = "retained-rational-strain-stress80-original-state.v1"


def _identity(strain):
    return {"numerator": str(strain.numerator), "denominator": str(strain.denominator)}


def _rounded(strain):
    if type(strain) is not F:
        raise ValueError("retained stress requires original rational trial strain")
    return _finite(strain)


@dataclass(frozen=True)
class RetainedSteelResponse(UniaxialPlasticityResponse):
    stress_trial_strain: F

    def to_dict(self):
        return super().to_dict() | {
            "stress_evaluation_profile": RETAINED_FIBER_PROFILE,
            "stress_trial_strain": _identity(self.stress_trial_strain),
        }


@dataclass(frozen=True)
class RetainedConcreteResponse(ConcreteDamageResponse):
    stress_trial_strain: F

    def to_dict(self):
        return super().to_dict() | {
            "stress_evaluation_profile": RETAINED_FIBER_PROFILE,
            "stress_trial_strain": _identity(self.stress_trial_strain),
        }


class RetainedStrainSteel(StableStressSteel):
    def integrate(self, total_strain, committed_state):
        rounded = _rounded(total_strain)
        original = BilinearCombinedHardeningSteel.integrate(
            self, rounded, committed_state
        )
        if original.yielded:
            trial = self.elastic_modulus_mpa * (
                rounded - committed_state.plastic_strain
            )
            sign = 1 if trial - committed_state.backstress_mpa >= 0 else -1
            # Preserve original rounded multiplier and branch, as in stable-stress.
            # Extend that affine branch by the retained sub-ulp strain increment.
            H = F(self.isotropic_hardening_modulus_mpa) + F(
                self.kinematic_hardening_modulus_mpa
            )
            E = F(self.elastic_modulus_mpa)
            stress = (
                F(committed_state.backstress_mpa)
                + sign
                * (
                    F(self.yield_stress_mpa)
                    + F(self.isotropic_hardening_modulus_mpa)
                    * F(committed_state.accumulated_plastic_strain)
                    + H * F(original.plastic_multiplier_increment)
                )
                + E * H / (E + H) * (total_strain - F(rounded))
            )
        else:
            stress = F(self.elastic_modulus_mpa) * (
                total_strain - F(committed_state.plastic_strain)
            )
        value = _finite(stress)
        final_yield = abs(value - original.state.backstress_mpa) - (
            self.yield_stress_mpa
            + self.isotropic_hardening_modulus_mpa
            * original.state.accumulated_plastic_strain
        )
        return _response(
            RetainedSteelResponse,
            original,
            stress_mpa=value,
            final_yield_function_mpa=final_yield,
            stress_trial_strain=total_strain,
        )


class RetainedStrainConcrete(StableStressConcrete):
    def integrate(self, total_strain, committed_state):
        rounded = _rounded(total_strain)
        original = AsymmetricConcreteDamageMaterial.integrate(
            self, rounded, committed_state
        )
        tension = rounded >= 0
        parent = (
            committed_state.tensile_history_strain
            if tension
            else committed_state.compressive_history_strain
        )
        history = (
            original.state.tensile_history_strain
            if tension
            else original.state.compressive_history_strain
        )
        threshold = (
            self.tensile_threshold_strain
            if tension
            else self.compressive_threshold_strain
        )
        rate = (
            self.tensile_softening_rate if tension else self.compressive_softening_rate
        )
        # Retain the original max-history branch. Native updated history stays
        # rounded; only this trial's stress evaluation retains its fine component.
        exact_history = abs(total_strain) if abs(rounded) >= parent else F(parent)
        original_survival = (
            1.0
            if history <= threshold
            else threshold / history * math.exp(-rate * (history - threshold))
        )
        original_derivative = (
            0.0 if history <= threshold else original_survival * (1.0 / history + rate)
        )
        advanced = abs(rounded) > parent + self.history_tolerance
        with localcontext(
            Context(
                prec=80,
                rounding=ROUND_HALF_EVEN,
                Emin=-999999,
                Emax=999999,
                capitals=1,
                clamp=0,
                traps=[InvalidOperation, DivisionByZero, Overflow],
            )
        ):

            def dec(value):
                value = F(value)
                return Decimal(value.numerator) / Decimal(value.denominator)

            strain, h, t, k, E = map(
                dec,
                (
                    total_strain,
                    exact_history,
                    threshold,
                    rate,
                    self.elastic_modulus_mpa,
                ),
            )
            survival = (
                Decimal(1) if history <= threshold else t / h * (-k * (h - t)).exp()
            )
            effective = max(survival, dec(1.0 - math.nextafter(1.0, 0.0)))
            stress = E * effective * strain
            tangent = (
                E * (effective - survival * abs(strain) * (1 / h + k))
                if advanced and original_derivative > 0
                else E * effective
            )
            stress, tangent = float(stress), float(tangent)
        if not math.isfinite(stress) or not math.isfinite(tangent):
            raise ValueError("retained concrete stress exceeds finite binary64 range")
        return _response(
            RetainedConcreteResponse,
            original,
            stress_mpa=stress,
            consistent_tangent_mpa=tangent,
            stress_trial_strain=total_strain,
        )


class RetainedFiberResponse(StatefulFiberSectionResponse):
    def to_dict(self):
        return super().to_dict() | {"fiber_strain_evaluation": RETAINED_FIBER_PROFILE}


class RetainedFiberRCSection(DirectFiberRCSection):
    coordinate_fiber_strain_evaluation = RETAINED_FIBER_PROFILE

    def __post_init__(self):
        StatefulRCFiberSection.__post_init__(self)
        if (
            type(self.steel) is not RetainedStrainSteel
            or type(self.concrete) is not RetainedStrainConcrete
        ):
            raise ValueError(
                "retained fiber section requires both retained stress laws"
            )

    @property
    def contract_hash(self):
        return canonical_hash(
            {
                "base_section_contract_hash": StatefulRCFiberSection._base_contract_hash(
                    self
                ),
                "fiber_strain_evaluation": RETAINED_FIBER_PROFILE,
                "concrete_decimal_precision": 80,
            }
        )

    def integrate_from_element_coordinates(
        self,
        local,
        length,
        xi,
        committed_state,
        *,
        compensation=None,
        material_runtime=None,
    ):
        if (
            material_runtime is not None
            and type(material_runtime) is not MaterialTrialRuntimeRecorder
        ):
            raise ValueError("material_runtime must be MaterialTrialRuntimeRecorder")
        generalized, strains = coordinate_fiber_strains(
            local,
            length,
            xi,
            [f.y_m for f in self.fibers],
            compensation,
            _retain_exact=True,
        )
        if material_runtime is not None:
            material_runtime.mark_instrumented_section_call()
        response = self._integrate(
            generalized,
            committed_state,
            material_runtime=material_runtime,
            _fiber_strain_values=strains,
        )
        return RetainedFiberResponse(
            **{f.name: getattr(response, f.name) for f in fields(response)}
        )


def retained_fiber_section(section):
    if (
        type(section) is not StatefulRCFiberSection
        or type(section.steel) is not BilinearCombinedHardeningSteel
        or type(section.concrete) is not AsymmetricConcreteDamageMaterial
    ):
        raise ValueError(
            "retained fiber profile requires original supported RC section"
        )
    return RetainedFiberRCSection(
        fibers=section.fibers,
        section_id=section.section_id,
        steel=RetainedStrainSteel(**asdict(section.steel)),
        concrete=RetainedStrainConcrete(**asdict(section.concrete)),
    )
