"""Bounded distributed axial-biaxial fiber correction for a 3D frame member.

The existing corotational Timoshenko element remains the objective geometric,
torsion, and elastic-shear reference. Axial and two bending fiber responses are
integrated at Gauss points. Their nonlinear increment relative to the section's
initial elastic tangent is mapped through deterministic numerical derivatives of
the seven corotational basic modes. This is an experimental verification kernel,
not a production analytic 3D tangent or release-authoritative element.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any

import numpy as np

from structural_analysis.elements.corotational_frame3d import (
    CorotationalFrame3DResponse,
    corotational_frame3d_basic_kinematics,
    corotational_frame3d_response,
)
from structural_analysis.elements.timoshenko_frame3d import TimoshenkoFrame3DSection
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.materials.stateful_biaxial_fiber_section import (
    StatefulBiaxialFiberSection,
    StatefulBiaxialFiberSectionResponse,
    StatefulBiaxialFiberSectionState,
)


STATEFUL_COROTATIONAL_FIBER_FRAME3D_PROFILE = (
    "corotational_timoshenko_with_distributed_axial_biaxial_fiber_correction.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME3D_STATE_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame3d-state.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME3D_CLAIM_BOUNDARY = (
    "Bounded 2/3-point axial-biaxial fiber correction on the objective 3D "
    "corotational Timoshenko reference. Material states, commit/rollback, and "
    "checkpoint replay are exact; the basic-mode map uses disclosed deterministic "
    "numerical derivatives. Shear and torsion remain elastic. There is no "
    "distributed bond-slip field, warping, member release/load feature, multi-turn "
    "rotation, production-scale performance, external V&V, or release authority."
)
_STATE_DOMAIN = b"structural-analysis/stateful-corotational-fiber-frame3d-state/v1\0"
_SELECTED_BASIC_INDICES = (0, 2, 3, 5, 6)


def _coordinates(values: Any) -> tuple[tuple[float, float, float], ...]:
    try:
        coordinates = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("node_coordinates_m must be a finite 2 by 3 array") from exc
    if coordinates.shape != (2, 3) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2 by 3 array")
    return tuple((float(row[0]), float(row[1]), float(row[2])) for row in coordinates)


def _displacement(values: Any) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("element_displacements must be a finite 12-vector") from exc
    if vector.shape != (12,) or not np.all(np.isfinite(vector)):
        raise ValueError("element_displacements must be a finite 12-vector")
    return np.array(vector, dtype=np.float64, copy=True)


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
class StatefulCorotationalFiberFrame3DState:
    element_id: str
    element_contract_hash: str
    element_displacements: tuple[float, ...]
    integration_point_states: tuple[StatefulBiaxialFiberSectionState, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        normalized_hash = str(self.element_contract_hash).strip()
        digest = normalized_hash.removeprefix("sha256:")
        if (
            not normalized_hash.startswith("sha256:")
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("element_contract_hash must be a lowercase sha256 digest")
        object.__setattr__(self, "element_contract_hash", normalized_hash)
        object.__setattr__(
            self,
            "element_displacements",
            tuple(float(value) for value in _displacement(self.element_displacements)),
        )
        if (
            not isinstance(self.integration_point_states, tuple)
            or not self.integration_point_states
            or not all(
                type(state) is StatefulBiaxialFiberSectionState
                for state in self.integration_point_states
            )
        ):
            raise ValueError(
                "integration_point_states must contain biaxial section states"
            )

    def canonical_bytes(self) -> bytes:
        element_id = self.element_id.encode("utf-8")
        contract_hash = self.element_contract_hash.encode("ascii")
        chunks = [
            _STATE_DOMAIN,
            struct.pack("<Q", len(element_id)),
            element_id,
            struct.pack("<Q", len(contract_hash)),
            contract_hash,
            struct.pack(
                "<12dQ",
                *self.element_displacements,
                len(self.integration_point_states),
            ),
        ]
        for state in self.integration_point_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_COROTATIONAL_FIBER_FRAME3D_STATE_SCHEMA_VERSION,
            "element_id": self.element_id,
            "element_contract_hash": self.element_contract_hash,
            "element_displacements": list(self.element_displacements),
            "integration_point_states": [
                state.to_dict() for state in self.integration_point_states
            ],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame3DResponse:
    parent_state_hash: str
    elastic_reference: CorotationalFrame3DResponse
    selected_basic_deformations: np.ndarray
    fiber_basic_forces: np.ndarray
    fiber_basic_tangent: np.ndarray
    initial_fiber_basic_tangent: np.ndarray
    correction_basic_forces: np.ndarray
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray
    basic_jacobian: np.ndarray
    section_responses: tuple[StatefulBiaxialFiberSectionResponse, ...]
    dissipated_energy_mj: float
    state: StatefulCorotationalFiberFrame3DState
    profile: str = STATEFUL_COROTATIONAL_FIBER_FRAME3D_PROFILE
    claim_boundary: str = STATEFUL_COROTATIONAL_FIBER_FRAME3D_CLAIM_BOUNDARY

    def __post_init__(self) -> None:
        arrays = (
            ("selected_basic_deformations", (5,)),
            ("fiber_basic_forces", (5,)),
            ("fiber_basic_tangent", (5, 5)),
            ("initial_fiber_basic_tangent", (5, 5)),
            ("correction_basic_forces", (5,)),
            ("internal_force_global", (12,)),
            ("consistent_tangent_global", (12, 12)),
            ("basic_jacobian", (5, 12)),
        )
        for name, shape in arrays:
            values = immutable_array(getattr(self, name), dtype="<f8")
            if values.shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
            object.__setattr__(self, name, values)

    @property
    def axial_strain(self) -> float:
        return float(
            self.selected_basic_deformations[0]
            / self.elastic_reference.initial_length_m
        )

    @property
    def axial_force_kn(self) -> float:
        return float(self.fiber_basic_forces[0])

    @property
    def axial_tangent_kn_per_m(self) -> float:
        return float(self.fiber_basic_tangent[0, 0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "parent_state_hash": self.parent_state_hash,
            "selected_basic_order": [
                "axial_extension_m",
                "bending_y_i_rad",
                "bending_z_i_rad",
                "bending_y_j_rad",
                "bending_z_j_rad",
            ],
            "selected_basic_deformations": self.selected_basic_deformations.tolist(),
            "fiber_basic_forces": self.fiber_basic_forces.tolist(),
            "fiber_basic_tangent": self.fiber_basic_tangent.tolist(),
            "initial_fiber_basic_tangent": (self.initial_fiber_basic_tangent.tolist()),
            "correction_basic_forces": self.correction_basic_forces.tolist(),
            "global_end_forces": self.internal_force_global.tolist(),
            "section_responses": [row.to_dict() for row in self.section_responses],
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "trial_state": self.state.to_dict(),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame3D:
    node_coordinates_m: tuple[tuple[float, float, float], ...]
    section: StatefulBiaxialFiberSection
    integration_order: int = 3
    local_axis_roll_deg: float = 0.0
    element_id: str = "stateful_corotational_fiber_frame3d"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "node_coordinates_m",
            _coordinates(self.node_coordinates_m),
        )
        if type(self.section) is not StatefulBiaxialFiberSection:
            raise ValueError("section must be an exact StatefulBiaxialFiberSection")
        _gauss_rule(self.integration_order)
        object.__setattr__(
            self,
            "local_axis_roll_deg",
            _finite(self.local_axis_roll_deg, name="local_axis_roll_deg"),
        )
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        if self.initial_length_m <= 1.0e-12:
            raise ValueError("initial member length must be positive")

    @property
    def initial_length_m(self) -> float:
        coordinates = np.asarray(self.node_coordinates_m, dtype=np.float64)
        return float(np.linalg.norm(coordinates[1] - coordinates[0]))

    @property
    def quadrature(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return _gauss_rule(self.integration_order)

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        points, weights = self.quadrature
        return {
            "profile": STATEFUL_COROTATIONAL_FIBER_FRAME3D_PROFILE,
            "element_id": self.element_id,
            "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
            "local_axis_roll_deg": self.local_axis_roll_deg,
            "integration_order": self.integration_order,
            "integration_point_xi": list(points),
            "integration_point_weights": list(weights),
            "section_contract_hash": self.section.contract_hash,
            "basic_modes": list(_SELECTED_BASIC_INDICES),
            "derivative_profile": (
                "five_point_basic_jacobian_and_symmetric_basic_hessian.v1"
            ),
            "reference_policy": ("elastic_timoshenko_plus_fiber_minus_initial_fiber"),
            "claim_boundary": STATEFUL_COROTATIONAL_FIBER_FRAME3D_CLAIM_BOUNDARY,
        }

    def initial_state(self) -> StatefulCorotationalFiberFrame3DState:
        state = StatefulCorotationalFiberFrame3DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            element_displacements=(0.0,) * 12,
            integration_point_states=tuple(
                self.section.initial_state() for _ in range(self.integration_order)
            ),
        )
        self.validate_state(state)
        return state

    def validate_reference_section(
        self,
        reference: TimoshenkoFrame3DSection,
        *,
        relative_tolerance: float = 1.0e-10,
    ) -> None:
        if type(reference) is not TimoshenkoFrame3DSection:
            raise ValueError("reference must be an exact TimoshenkoFrame3DSection")
        tangent = np.asarray(self.section.initial_consistent_tangent())
        props = reference.frame
        expected = np.diag(
            (
                props.e_n_per_m2 * props.area_m2,
                props.e_n_per_m2 * props.iy_m4,
                props.e_n_per_m2 * props.iz_m4,
            )
        )
        scale = max(
            float(np.linalg.norm(tangent, ord=np.inf)),
            float(np.linalg.norm(expected, ord=np.inf)),
            1.0,
        )
        if float(np.linalg.norm(tangent - expected, ord=np.inf)) > (
            relative_tolerance * scale
        ):
            raise ValueError(
                "distributed fiber initial tangent does not match frame reference"
            )

    def validate_state(self, state: StatefulCorotationalFiberFrame3DState) -> None:
        if type(state) is not StatefulCorotationalFiberFrame3DState:
            raise ValueError("state type is invalid")
        if state.element_id != self.element_id:
            raise ValueError("state element_id does not match element")
        if state.element_contract_hash != self.contract_hash:
            raise ValueError("state element_contract_hash does not match element")
        if len(state.integration_point_states) != self.integration_order:
            raise ValueError("state integration-point count does not match element")
        displacement = _displacement(state.element_displacements)
        selected = self._selected_basic(displacement)
        for xi, section_state in zip(
            self.quadrature[0],
            state.integration_point_states,
            strict=True,
        ):
            self.section.validate_state(section_state)
            expected = self._strain_matrix(xi) @ selected
            actual = np.asarray(
                (
                    section_state.axial_strain,
                    section_state.curvature_y_per_m,
                    section_state.curvature_z_per_m,
                ),
                dtype=np.float64,
            )
            if not np.allclose(expected, actual, atol=2.0e-12, rtol=0.0):
                raise ValueError(
                    "section generalized strain does not match element state"
                )

    def dissipated_energy_mj(
        self,
        state: StatefulCorotationalFiberFrame3DState,
    ) -> float:
        self.validate_state(state)
        _, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
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
        element_displacements: Any,
        committed_state: StatefulCorotationalFiberFrame3DState,
        *,
        reference_section: TimoshenkoFrame3DSection,
    ) -> StatefulCorotationalFiberFrame3DResponse:
        self.validate_reference_section(reference_section)
        self.validate_state(committed_state)
        displacement = _displacement(element_displacements)
        elastic = corotational_frame3d_response(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacement,
            section=reference_section,
            local_axis_roll_deg=self.local_axis_roll_deg,
        )
        selected, jacobian, hessians = self._selected_basic_derivatives(displacement)
        fiber_force, fiber_tangent, responses, states = self._integrate_basic(
            selected,
            committed_state.integration_point_states,
        )
        initial_tangent = self._initial_basic_tangent()
        correction_force = fiber_force - initial_tangent @ selected
        correction_tangent = fiber_tangent - initial_tangent
        global_correction = jacobian.T @ correction_force
        global_tangent_correction = jacobian.T @ correction_tangent @ jacobian
        for index in range(5):
            global_tangent_correction += correction_force[index] * hessians[index]
        internal = np.asarray(elastic.internal_force_global) + global_correction
        tangent = (
            np.asarray(elastic.consistent_tangent_global) + global_tangent_correction
        )
        tangent = 0.5 * (tangent + tangent.T)
        if not np.all(np.isfinite(internal)) or not np.all(np.isfinite(tangent)):
            raise ValueError("distributed fiber member response is non-finite")
        state = StatefulCorotationalFiberFrame3DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            element_displacements=tuple(float(value) for value in displacement),
            integration_point_states=states,
        )
        self.validate_state(state)
        return StatefulCorotationalFiberFrame3DResponse(
            parent_state_hash=committed_state.state_hash,
            elastic_reference=elastic,
            selected_basic_deformations=selected,
            fiber_basic_forces=fiber_force,
            fiber_basic_tangent=fiber_tangent,
            initial_fiber_basic_tangent=initial_tangent,
            correction_basic_forces=correction_force,
            internal_force_global=internal,
            consistent_tangent_global=tangent,
            basic_jacobian=jacobian,
            section_responses=responses,
            dissipated_energy_mj=self.dissipated_energy_mj(state),
            state=state,
        )

    def _selected_basic(self, displacement: np.ndarray) -> np.ndarray:
        kinematics = corotational_frame3d_basic_kinematics(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacement,
            local_axis_roll_deg=self.local_axis_roll_deg,
        )
        return np.asarray(
            kinematics.basic_deformations[list(_SELECTED_BASIC_INDICES)],
            dtype=np.float64,
        )

    def _strain_matrix(self, xi: float) -> np.ndarray:
        coordinate = _finite(xi, name="xi")
        if not -1.0 <= coordinate <= 1.0:
            raise ValueError("xi must be in [-1, 1]")
        length = self.initial_length_m
        first = (3.0 * coordinate - 1.0) / length
        second = (3.0 * coordinate + 1.0) / length
        return np.asarray(
            (
                (1.0 / length, 0.0, 0.0, 0.0, 0.0),
                (0.0, first, 0.0, second, 0.0),
                (0.0, 0.0, first, 0.0, second),
            ),
            dtype=np.float64,
        )

    def _integrate_basic(
        self,
        selected: np.ndarray,
        parents: tuple[StatefulBiaxialFiberSectionState, ...],
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        tuple[StatefulBiaxialFiberSectionResponse, ...],
        tuple[StatefulBiaxialFiberSectionState, ...],
    ]:
        points, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
        force = np.zeros(5, dtype=np.float64)
        tangent = np.zeros((5, 5), dtype=np.float64)
        responses: list[StatefulBiaxialFiberSectionResponse] = []
        states: list[StatefulBiaxialFiberSectionState] = []
        for xi, weight, parent in zip(points, weights, parents, strict=True):
            strain_matrix = self._strain_matrix(xi)
            response = self.section.integrate(strain_matrix @ selected, parent)
            factor = weight * jacobian
            force += strain_matrix.T @ response.resultants * factor
            tangent += (
                strain_matrix.T @ response.consistent_tangent @ strain_matrix * factor
            )
            responses.append(response)
            states.append(response.state)
        tangent = 0.5 * (tangent + tangent.T)
        return force, tangent, tuple(responses), tuple(states)

    def _initial_basic_tangent(self) -> np.ndarray:
        points, weights = self.quadrature
        jacobian = 0.5 * self.initial_length_m
        section_tangent = np.asarray(self.section.initial_consistent_tangent())
        tangent = np.zeros((5, 5), dtype=np.float64)
        for xi, weight in zip(points, weights, strict=True):
            strain_matrix = self._strain_matrix(xi)
            tangent += (
                strain_matrix.T @ section_tangent @ strain_matrix * weight * jacobian
            )
        return 0.5 * (tangent + tangent.T)

    def _selected_basic_derivatives(
        self,
        displacement: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        center = self._selected_basic(displacement)
        length = self.initial_length_m
        jacobian_steps = np.asarray(
            [1.0e-6 * max(length, 1.0)] * 3
            + [1.0e-6] * 3
            + [1.0e-6 * max(length, 1.0)] * 3
            + [1.0e-6] * 3,
            dtype=np.float64,
        )
        hessian_steps = np.asarray(
            [2.0e-4 * max(length, 1.0)] * 3
            + [2.0e-4] * 3
            + [2.0e-4 * max(length, 1.0)] * 3
            + [2.0e-4] * 3,
            dtype=np.float64,
        )
        jacobian = np.empty((5, 12), dtype=np.float64)
        hessians = np.empty((5, 12, 12), dtype=np.float64)
        for first in range(12):
            step = jacobian_steps[first]
            plus_one = displacement.copy()
            minus_one = displacement.copy()
            plus_two = displacement.copy()
            minus_two = displacement.copy()
            plus_one[first] += step
            minus_one[first] -= step
            plus_two[first] += 2.0 * step
            minus_two[first] -= 2.0 * step
            jacobian[:, first] = (
                -self._selected_basic(plus_two)
                + 8.0 * self._selected_basic(plus_one)
                - 8.0 * self._selected_basic(minus_one)
                + self._selected_basic(minus_two)
            ) / (12.0 * step)

            second_step = hessian_steps[first]
            plus_one = displacement.copy()
            minus_one = displacement.copy()
            plus_two = displacement.copy()
            minus_two = displacement.copy()
            plus_one[first] += second_step
            minus_one[first] -= second_step
            plus_two[first] += 2.0 * second_step
            minus_two[first] -= 2.0 * second_step
            hessians[:, first, first] = (
                -self._selected_basic(plus_two)
                + 16.0 * self._selected_basic(plus_one)
                - 30.0 * center
                + 16.0 * self._selected_basic(minus_one)
                - self._selected_basic(minus_two)
            ) / (12.0 * second_step**2)
            for second in range(first + 1, 12):
                other_step = hessian_steps[second]
                plus_plus = displacement.copy()
                plus_minus = displacement.copy()
                minus_plus = displacement.copy()
                minus_minus = displacement.copy()
                plus_plus[first] += second_step
                plus_plus[second] += other_step
                plus_minus[first] += second_step
                plus_minus[second] -= other_step
                minus_plus[first] -= second_step
                minus_plus[second] += other_step
                minus_minus[first] -= second_step
                minus_minus[second] -= other_step
                values = (
                    self._selected_basic(plus_plus)
                    - self._selected_basic(plus_minus)
                    - self._selected_basic(minus_plus)
                    + self._selected_basic(minus_minus)
                ) / (4.0 * second_step * other_step)
                hessians[:, first, second] = values
                hessians[:, second, first] = values
        return center, jacobian, hessians


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME3D_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME3D_PROFILE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME3D_STATE_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame3D",
    "StatefulCorotationalFiberFrame3DResponse",
    "StatefulCorotationalFiberFrame3DState",
]
