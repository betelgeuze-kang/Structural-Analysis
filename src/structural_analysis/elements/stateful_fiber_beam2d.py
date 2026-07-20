"""State-updated local-coordinate small-displacement 2D fiber beam kernel.

The Euler-Bernoulli element maps six local nodal degrees of freedom to axial
strain and curvature at Gauss points. Its section dependency is the structural
``AxialCurvatureSection`` protocol rather than one concrete implementation.
Coordinate transformation and multi-element assembly live in the assembly
layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.elements.axial_curvature_section import (
    AxialCurvatureSection,
    AxialCurvatureSectionResponse,
    AxialCurvatureSectionState,
)
from structural_analysis.elements.stateful_fiber_beam2d_contract import (
    STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_FIBER_BEAM2D_KINEMATICS,
    STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION,
    STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
    STATEFUL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.elements.stateful_fiber_beam2d_response import (
    StatefulFiberBeam2DResponse,
)
from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _positive(value: Any, *, name: str) -> float:
    normalized = _finite(value, name=name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _local_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite six-vector")
    return np.array(vector, dtype=np.float64, copy=True, order="C")


def _gauss_rule(order: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if type(order) is not int or order not in (2, 3):
        raise ValueError("integration_order must be 2 or 3")
    if order == 2:
        abscissa = 0.5773502691896257
        return (-abscissa, abscissa), (1.0, 1.0)
    abscissa = 0.7745966692414834
    return (
        (-abscissa, 0.0, abscissa),
        (0.5555555555555556, 0.8888888888888888, 0.5555555555555556),
    )


@dataclass(frozen=True)
class StatefulFiberBeam2D:
    section: AxialCurvatureSection
    length_m: float = 3.0
    integration_order: int = 3
    element_id: str = "stateful_rc_fiber_beam2d"

    def __post_init__(self) -> None:
        if not isinstance(self.section, AxialCurvatureSection):
            raise ValueError("section must satisfy AxialCurvatureSection")
        object.__setattr__(
            self,
            "length_m",
            _positive(self.length_m, name="length_m"),
        )
        _gauss_rule(self.integration_order)
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)

    @property
    def quadrature(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return _gauss_rule(self.integration_order)

    @property
    def contract_hash(self) -> str:
        points, weights = self.quadrature
        return canonical_hash(
            {
                "schema_version": STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION,
                "element_id": self.element_id,
                "length_m": self.length_m,
                "integration_order": self.integration_order,
                "integration_point_xi": list(points),
                "integration_point_weights": list(weights),
                "section_contract_hash": self.section.contract_hash,
                "kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
                "internal_force": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
                "tangent": STATEFUL_FIBER_BEAM2D_TANGENT,
            }
        )

    def strain_displacement_matrix(self, xi: float) -> np.ndarray:
        coordinate = _finite(xi, name="xi")
        if coordinate < -1.0 or coordinate > 1.0:
            raise ValueError("xi must be in [-1, 1]")
        ratio = 0.5 * (coordinate + 1.0)
        length = self.length_m
        matrix = np.asarray(
            [
                [-1.0 / length, 0.0, 0.0, 1.0 / length, 0.0, 0.0],
                [
                    0.0,
                    (-6.0 + 12.0 * ratio) / length**2,
                    (-4.0 + 6.0 * ratio) / length,
                    0.0,
                    (6.0 - 12.0 * ratio) / length**2,
                    (-2.0 + 6.0 * ratio) / length,
                ],
            ],
            dtype=np.float64,
        )
        matrix.setflags(write=False)
        return matrix

    def uniform_generalized_strain_displacements(
        self,
        axial_strain: float,
        curvature_z_per_m: float,
    ) -> np.ndarray:
        axial = _finite(axial_strain, name="axial_strain")
        curvature = _finite(
            curvature_z_per_m,
            name="curvature_z_per_m",
        )
        length = self.length_m
        displacement = np.asarray(
            [
                0.0,
                0.0,
                0.0,
                axial * length,
                0.5 * curvature * length**2,
                curvature * length,
            ],
            dtype=np.float64,
        )
        displacement.setflags(write=False)
        return displacement

    def initial_state(self) -> StatefulFiberBeam2DState:
        return StatefulFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=0,
            local_displacements=(0.0,) * 6,
            integration_point_states=tuple(
                self.section.initial_state() for _ in range(self.integration_order)
            ),
        )

    def validate_state(self, state: StatefulFiberBeam2DState) -> None:
        if type(state) is not StatefulFiberBeam2DState:
            raise ValueError("state type is invalid")
        if state.element_id != self.element_id:
            raise ValueError("state element_id does not match element")
        if state.element_contract_hash != self.contract_hash:
            raise ValueError("state element_contract_hash does not match element")
        if len(state.integration_point_states) != self.integration_order:
            raise ValueError("state integration-point count does not match element")
        local = np.asarray(state.local_displacements, dtype=np.float64)
        for xi, section_state in zip(
            self.quadrature[0],
            state.integration_point_states,
            strict=True,
        ):
            self.section.validate_state(section_state)
            if section_state.step_index != state.step_index:
                raise ValueError("section and element step indices do not match")
            expected = self.strain_displacement_matrix(xi) @ local
            actual = np.asarray(
                [
                    section_state.axial_strain,
                    section_state.curvature_z_per_m,
                ],
                dtype=np.float64,
            )
            if not np.allclose(expected, actual, rtol=0.0, atol=1.0e-14):
                raise ValueError(
                    "section generalized strain does not match element state"
                )

    def dissipated_energy_mj(self, state: StatefulFiberBeam2DState) -> float:
        self.validate_state(state)
        _, weights = self.quadrature
        jacobian = 0.5 * self.length_m
        return math.fsum(
            weight * jacobian * self.section.dissipated_energy_mj_per_m(section_state)
            for weight, section_state in zip(
                weights,
                state.integration_point_states,
                strict=True,
            )
        )

    def integrate(
        self,
        local_displacements: Any,
        committed_state: StatefulFiberBeam2DState,
    ) -> StatefulFiberBeam2DResponse:
        self.validate_state(committed_state)
        local = _local_vector(
            local_displacements,
            name="local_displacements",
        )
        points, weights = self.quadrature
        jacobian = 0.5 * self.length_m
        internal_force = np.zeros(6, dtype=np.float64)
        tangent = np.zeros((6, 6), dtype=np.float64)
        generalized_strains: list[np.ndarray] = []
        section_responses: list[AxialCurvatureSectionResponse] = []
        next_states: list[AxialCurvatureSectionState] = []

        for xi, weight, parent in zip(
            points,
            weights,
            committed_state.integration_point_states,
            strict=True,
        ):
            strain_displacement = self.strain_displacement_matrix(xi)
            generalized = strain_displacement @ local
            response = self.section.integrate(generalized, parent)
            if not isinstance(response, AxialCurvatureSectionResponse):
                raise ValueError(
                    "section response must satisfy AxialCurvatureSectionResponse"
                )
            if response.parent_state_hash != parent.state_hash:
                raise ValueError(
                    "section response parent_state_hash does not match "
                    "integration-point parent"
                )
            factor = weight * jacobian
            internal_force += (strain_displacement.T @ response.resultants) * factor
            tangent += (
                strain_displacement.T
                @ response.consistent_tangent
                @ strain_displacement
            ) * factor
            generalized_strains.append(generalized)
            section_responses.append(response)
            next_states.append(response.state)

        next_state = StatefulFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=committed_state.step_index + 1,
            local_displacements=tuple(float(value) for value in local),
            integration_point_states=tuple(next_states),
        )
        generalized_array = np.asarray(
            generalized_strains,
            dtype=np.float64,
        )
        point_array = np.asarray(points, dtype=np.float64)
        weight_array = np.asarray(weights, dtype=np.float64)
        for array in (
            local,
            internal_force,
            tangent,
            generalized_array,
            point_array,
            weight_array,
        ):
            array.setflags(write=False)
        return StatefulFiberBeam2DResponse(
            parent_state_hash=committed_state.state_hash,
            local_displacements=local,
            internal_force_local=internal_force,
            consistent_tangent_local=tangent,
            integration_point_xi=point_array,
            integration_point_weights=weight_array,
            generalized_strains=generalized_array,
            section_responses=tuple(section_responses),
            yielded_integration_point_count=sum(
                int(response.yielded_steel_fiber_count > 0)
                for response in section_responses
            ),
            damaged_integration_point_count=sum(
                int(response.damaged_concrete_fiber_count > 0)
                for response in section_responses
            ),
            dissipated_energy_mj=self.dissipated_energy_mj(next_state),
            state=next_state,
        )


__all__ = [
    "STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE",
    "STATEFUL_FIBER_BEAM2D_KINEMATICS",
    "STATEFUL_FIBER_BEAM2D_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_TANGENT",
    "StatefulFiberBeam2D",
    "StatefulFiberBeam2DResponse",
    "StatefulFiberBeam2DState",
]
