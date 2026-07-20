"""Stateful planar corotational fiber beam built on basic deformations.

The element reuses ``StatefulFiberBeam2D`` solely as the axial-curvature
section integrator in the three corotational basic modes.  It owns finite-chord
kinematics, committed chord-angle unwrapping, and exact global material plus
geometric tangent recovery.  Multi-element assembly and nonlinear solution
control remain outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Any

import numpy as np

from structural_analysis.elements.axial_curvature_section import (
    AxialCurvatureSection,
)
from structural_analysis.elements.corotational_frame2d_basic import (
    COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY,
    CorotationalFrame2DBasicKinematics,
    assemble_corotational_frame2d_global_response,
    corotational_frame2d_basic_kinematics,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_contract import (
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_response import (
    StatefulCorotationalFiberBeam2DResponse,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_state import (
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


_TWO_PI = 2.0 * math.pi
_BASIC_TO_LOCAL = np.frombuffer(
    np.asarray(
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    ).tobytes(order="C"),
    dtype=np.float64,
).reshape((6, 3))


def _coordinates_tuple(values: Any) -> tuple[tuple[float, float], ...]:
    try:
        coordinates = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("node_coordinates_m must be a finite 2x2 array") from exc
    if coordinates.shape != (2, 2) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2x2 array")
    return tuple(tuple(float(value) for value in row) for row in coordinates)


def _vector6(values: Any) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("element_displacements must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError("element_displacements must be a finite six-vector")
    return np.array(vector, dtype=np.float64, copy=True, order="C")


def _unwrap_angle_near_committed(
    principal_angle: float,
    committed_angle: float,
) -> float:
    try:
        turns = math.floor((committed_angle - principal_angle) / _TWO_PI + 0.5)
        unwrapped = principal_angle + _TWO_PI * turns
    except (OverflowError, ValueError) as exc:
        raise ValueError("committed chord rotation cannot be unwrapped") from exc
    if not math.isfinite(unwrapped):
        raise ValueError("committed chord rotation cannot be unwrapped")
    return unwrapped


def _replace_chord_rotation(
    kinematics: CorotationalFrame2DBasicKinematics,
    chord_rotation_change_rad: float,
) -> CorotationalFrame2DBasicKinematics:
    offset = chord_rotation_change_rad - kinematics.chord_rotation_change_rad
    basic_deformations = np.array(
        kinematics.basic_deformations,
        dtype=np.float64,
        copy=True,
    )
    basic_deformations[1:] -= offset
    return replace(
        kinematics,
        chord_rotation_change_rad=chord_rotation_change_rad,
        basic_deformations=basic_deformations,
    )


@dataclass(frozen=True)
class _BasicResponse:
    basic_forces: np.ndarray
    consistent_tangent_basic: np.ndarray


@dataclass(frozen=True)
class StatefulCorotationalFiberBeam2D:
    node_coordinates_m: tuple[tuple[float, float], ...]
    section: AxialCurvatureSection
    integration_order: int = 3
    element_id: str = "stateful_corotational_rc_fiber_beam2d"
    _basic_beam: StatefulFiberBeam2D = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        coordinates = _coordinates_tuple(self.node_coordinates_m)
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        zero_kinematics = corotational_frame2d_basic_kinematics(
            node_coordinates_m=coordinates,
            element_displacements=np.zeros(6, dtype=np.float64),
        )
        object.__setattr__(self, "node_coordinates_m", coordinates)
        object.__setattr__(self, "element_id", normalized_id)
        object.__setattr__(
            self,
            "_basic_beam",
            StatefulFiberBeam2D(
                section=self.section,
                length_m=zero_kinematics.initial_length_m,
                integration_order=self.integration_order,
                element_id=f"{normalized_id}::basic-fiber-beam",
            ),
        )

    @property
    def initial_length_m(self) -> float:
        return self._basic_beam.length_m

    @property
    def basic_beam(self) -> StatefulFiberBeam2D:
        return self._basic_beam

    @property
    def basic_projection_to_local(self) -> np.ndarray:
        return _BASIC_TO_LOCAL

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            {
                "schema_version": STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION,
                "element_id": self.element_id,
                "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
                "integration_order": self.integration_order,
                "basic_beam_contract_hash": self._basic_beam.contract_hash,
                "principal_angle_branch": COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY,
                "angle_unwrap": STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP,
                "basic_to_local": STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL,
                "internal_force": STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE,
                "tangent": STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT,
            }
        )

    def initial_state(self) -> StatefulCorotationalFiberBeam2DState:
        state = StatefulCorotationalFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=0,
            element_displacements=(0.0,) * 6,
            chord_rotation_change_rad=0.0,
            basic_beam_state=self._basic_beam.initial_state(),
        )
        self.validate_state(state)
        return state

    def validate_state(self, state: StatefulCorotationalFiberBeam2DState) -> None:
        if type(state) is not StatefulCorotationalFiberBeam2DState:
            raise ValueError("state type is invalid")
        if state.element_id != self.element_id:
            raise ValueError("state element_id does not match element")
        if state.element_contract_hash != self.contract_hash:
            raise ValueError("state element_contract_hash does not match element")
        self._basic_beam.validate_state(state.basic_beam_state)
        if state.basic_beam_state.step_index != state.step_index:
            raise ValueError("basic beam and corotational step indices do not match")
        principal = corotational_frame2d_basic_kinematics(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=state.element_displacements,
        )
        wrapped_difference = math.atan2(
            math.sin(
                state.chord_rotation_change_rad - principal.chord_rotation_change_rad
            ),
            math.cos(
                state.chord_rotation_change_rad - principal.chord_rotation_change_rad
            ),
        )
        if abs(wrapped_difference) > 1.0e-12:
            raise ValueError("state chord rotation does not match current chord")
        unwrapped = _replace_chord_rotation(
            principal,
            state.chord_rotation_change_rad,
        )
        expected_local = _BASIC_TO_LOCAL @ unwrapped.basic_deformations
        actual_local = np.asarray(
            state.basic_beam_state.local_displacements,
            dtype=np.float64,
        )
        if not np.allclose(expected_local, actual_local, rtol=0.0, atol=1.0e-13):
            raise ValueError(
                "basic beam local displacement does not match corotational state"
            )

    def trial_basic_kinematics(
        self,
        element_displacements: Any,
        committed_state: StatefulCorotationalFiberBeam2DState,
    ) -> CorotationalFrame2DBasicKinematics:
        self.validate_state(committed_state)
        displacements = _vector6(element_displacements)
        principal = corotational_frame2d_basic_kinematics(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacements,
        )
        unwrapped_angle = _unwrap_angle_near_committed(
            principal.chord_rotation_change_rad,
            committed_state.chord_rotation_change_rad,
        )
        return _replace_chord_rotation(principal, unwrapped_angle)

    def dissipated_energy_mj(
        self,
        state: StatefulCorotationalFiberBeam2DState,
    ) -> float:
        self.validate_state(state)
        return self._basic_beam.dissipated_energy_mj(state.basic_beam_state)

    def integrate(
        self,
        element_displacements: Any,
        committed_state: StatefulCorotationalFiberBeam2DState,
    ) -> StatefulCorotationalFiberBeam2DResponse:
        self.validate_state(committed_state)
        displacements = _vector6(element_displacements)
        principal = corotational_frame2d_basic_kinematics(
            node_coordinates_m=self.node_coordinates_m,
            element_displacements=displacements,
        )
        kinematics = _replace_chord_rotation(
            principal,
            _unwrap_angle_near_committed(
                principal.chord_rotation_change_rad,
                committed_state.chord_rotation_change_rad,
            ),
        )
        local_displacements = _BASIC_TO_LOCAL @ kinematics.basic_deformations
        fiber_beam_response = self._basic_beam.integrate(
            local_displacements,
            committed_state.basic_beam_state,
        )
        if (
            fiber_beam_response.parent_state_hash
            != committed_state.basic_beam_state.state_hash
        ):
            raise ValueError("fiber-beam response parent state does not match")
        basic_forces = _BASIC_TO_LOCAL.T @ fiber_beam_response.internal_force_local
        basic_tangent = (
            _BASIC_TO_LOCAL.T
            @ fiber_beam_response.consistent_tangent_local
            @ _BASIC_TO_LOCAL
        )
        global_response = assemble_corotational_frame2d_global_response(
            kinematics=kinematics,
            basic_response=_BasicResponse(
                basic_forces=basic_forces,
                consistent_tangent_basic=basic_tangent,
            ),
        )
        next_state = StatefulCorotationalFiberBeam2DState(
            element_id=self.element_id,
            element_contract_hash=self.contract_hash,
            step_index=committed_state.step_index + 1,
            element_displacements=tuple(float(value) for value in displacements),
            chord_rotation_change_rad=kinematics.chord_rotation_change_rad,
            basic_beam_state=fiber_beam_response.state,
        )
        self.validate_state(next_state)
        return StatefulCorotationalFiberBeam2DResponse(
            parent_state_hash=committed_state.state_hash,
            kinematics=kinematics,
            basic_forces=basic_forces,
            consistent_tangent_basic=basic_tangent,
            global_response=global_response,
            fiber_beam_response=fiber_beam_response,
            state=next_state,
        )


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT",
    "StatefulCorotationalFiberBeam2D",
    "StatefulCorotationalFiberBeam2DResponse",
    "StatefulCorotationalFiberBeam2DState",
]
