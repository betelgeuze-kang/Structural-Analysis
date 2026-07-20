"""Response container for one stateful corotational 2D fiber beam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structural_analysis.elements.corotational_frame2d_basic import (
    CorotationalFrame2DBasicKinematics,
    CorotationalFrame2DGlobalResponse,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_contract import (
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_state import (
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.elements.stateful_fiber_beam2d_response import (
    StatefulFiberBeam2DResponse,
)


def _sha256_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _readonly(values: Any, *, shape: tuple[int, ...], name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite array with shape {shape}") from exc
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite array with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True, order="C")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class StatefulCorotationalFiberBeam2DResponse:
    parent_state_hash: str
    kinematics: CorotationalFrame2DBasicKinematics
    basic_forces: np.ndarray
    consistent_tangent_basic: np.ndarray
    global_response: CorotationalFrame2DGlobalResponse
    fiber_beam_response: StatefulFiberBeam2DResponse
    state: StatefulCorotationalFiberBeam2DState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_state_hash",
            _sha256_hash(self.parent_state_hash, name="parent_state_hash"),
        )
        if type(self.kinematics) is not CorotationalFrame2DBasicKinematics:
            raise ValueError("kinematics type is invalid")
        if type(self.global_response) is not CorotationalFrame2DGlobalResponse:
            raise ValueError("global_response type is invalid")
        if type(self.fiber_beam_response) is not StatefulFiberBeam2DResponse:
            raise ValueError("fiber_beam_response type is invalid")
        if type(self.state) is not StatefulCorotationalFiberBeam2DState:
            raise ValueError("state type is invalid")
        object.__setattr__(
            self,
            "basic_forces",
            _readonly(self.basic_forces, shape=(3,), name="basic_forces"),
        )
        object.__setattr__(
            self,
            "consistent_tangent_basic",
            _readonly(
                self.consistent_tangent_basic,
                shape=(3, 3),
                name="consistent_tangent_basic",
            ),
        )
        if (
            self.state.basic_beam_state.canonical_bytes()
            != self.fiber_beam_response.state.canonical_bytes()
        ):
            raise ValueError("state does not contain the fiber-beam trial state")

    @property
    def internal_force_global(self) -> np.ndarray:
        return self.global_response.internal_force_global

    @property
    def material_tangent_global(self) -> np.ndarray:
        return self.global_response.material_tangent_global

    @property
    def geometric_tangent_global(self) -> np.ndarray:
        return self.global_response.geometric_tangent_global

    @property
    def consistent_tangent_global(self) -> np.ndarray:
        return self.global_response.consistent_tangent_global

    @property
    def yielded_integration_point_count(self) -> int:
        return self.fiber_beam_response.yielded_integration_point_count

    @property
    def damaged_integration_point_count(self) -> int:
        return self.fiber_beam_response.damaged_integration_point_count

    @property
    def dissipated_energy_mj(self) -> float:
        return self.fiber_beam_response.dissipated_energy_mj

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_COROTATIONAL_FIBER_BEAM2D_SCHEMA_VERSION,
            "parent_state_hash": self.parent_state_hash,
            "kinematics": self.kinematics.to_dict(),
            "basic_forces": self.basic_forces.tolist(),
            "consistent_tangent_basic": self.consistent_tangent_basic.tolist(),
            "global_response": self.global_response.to_dict(),
            "fiber_beam_response": self.fiber_beam_response.to_dict(),
            "basic_to_local_definition": (
                STATEFUL_COROTATIONAL_FIBER_BEAM2D_BASIC_TO_LOCAL
            ),
            "angle_unwrap_definition": (
                STATEFUL_COROTATIONAL_FIBER_BEAM2D_ANGLE_UNWRAP
            ),
            "internal_force_definition": (
                STATEFUL_COROTATIONAL_FIBER_BEAM2D_INTERNAL_FORCE
            ),
            "tangent_definition": STATEFUL_COROTATIONAL_FIBER_BEAM2D_TANGENT,
            "trial_state": self.state.to_dict(),
        }


__all__ = ["StatefulCorotationalFiberBeam2DResponse"]
