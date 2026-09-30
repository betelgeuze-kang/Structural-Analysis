"""Explicit coordinate-to-fiber trials with one final binary64 strain rounding."""

from dataclasses import fields
from fractions import Fraction as F
import math

import numpy as np

from structural_analysis.elements.fiber_beam2d_strain import exact_fiber_beam2d_strain
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionResponse,
)
from structural_analysis.materials.stable_stress import StableStressRCFiberSection
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder

DIRECT_FIBER_PROFILE = "coordinate-to-fiber-single-round.v1"


def coordinate_fiber_strains(
    local, length, xi, locations, compensation=None, *, _retain_exact=False
):
    """Keep generalized outputs; combine their exact expressions before rounding fibers."""
    generalized = exact_fiber_beam2d_strain(local, length, xi, compensation)
    if not all(
        isinstance(y, (float, int)) and not isinstance(y, bool) and math.isfinite(y)
        for y in locations
    ):
        raise ValueError("finite fiber locations required")
    u = [F(float(x)) for x in local]
    if compensation is not None:
        u = [x + F(float(y)) for x, y in zip(u, compensation, strict=True)]
    L, x = F(float(length)), F(float(xi))
    axial = (u[3] - u[0]) / L
    curvature = (
        6 * x * (u[1] - u[4]) / L + (3 * x - 1) * u[2] + (3 * x + 1) * u[5]
    ) / L
    exact = tuple(axial - F(float(y)) * curvature for y in locations)
    try:
        strains = np.array([float(value) for value in exact])
    except OverflowError as exc:
        raise ValueError("fiber strain exceeds finite binary64 range") from exc
    if not np.all(np.isfinite(strains)):
        raise ValueError("fiber strain exceeds finite binary64 range")
    strains.setflags(write=False)
    return generalized, exact if _retain_exact else strains


class DirectFiberSectionResponse(StatefulFiberSectionResponse):
    def to_dict(self):
        return super().to_dict() | {"fiber_strain_evaluation": DIRECT_FIBER_PROFILE}


class DirectFiberRCSection(StableStressRCFiberSection):
    coordinate_fiber_strain_evaluation = DIRECT_FIBER_PROFILE

    @property
    def contract_hash(self):
        return canonical_hash(
            {
                "base_section_contract_hash": super().contract_hash,
                "fiber_strain_evaluation": DIRECT_FIBER_PROFILE,
            }
        )

    def integrate(self, generalized_strain, committed_state):
        raise ValueError("direct fiber section requires original element coordinates")

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
            local, length, xi, [f.y_m for f in self.fibers], compensation
        )
        if material_runtime is not None:
            material_runtime.mark_instrumented_section_call()
        response = self._integrate(
            generalized,
            committed_state,
            material_runtime=material_runtime,
            _fiber_strain_values=strains,
        )
        return DirectFiberSectionResponse(
            **{f.name: getattr(response, f.name) for f in fields(response)}
        )


def direct_fiber_section(section):
    if type(section) is not StableStressRCFiberSection:
        raise ValueError("direct fiber profile requires original stable-stress section")
    return DirectFiberRCSection(
        fibers=section.fibers,
        section_id=section.section_id,
        steel=section.steel,
        concrete=section.concrete,
    )
