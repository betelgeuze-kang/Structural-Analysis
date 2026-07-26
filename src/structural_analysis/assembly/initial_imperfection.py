"""Explicit bounded initial-imperfection mesh construction for 3D members."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.elements.frame3d import frame_rotation_matrix
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


INITIAL_IMPERFECTION_PROFILE = "sinusoidal_member_bow_local_yz.v1"
INITIAL_IMPERFECTION_CLAIM_BOUNDARY = (
    "Geometry generator for one explicitly oriented member; no eigenmode "
    "scaling, code-prescribed amplitude, residual stress, or solver promotion."
)


@dataclass(frozen=True)
class InitialImperfectionMesh3D:
    profile: str
    nominal_coordinates_m: np.ndarray
    imperfect_coordinates_m: np.ndarray
    local_y_amplitude_m: float
    local_z_amplitude_m: float
    roll_deg: float
    mesh_hash: str
    claim_boundary: str = INITIAL_IMPERFECTION_CLAIM_BOUNDARY

    def __post_init__(self) -> None:
        nominal = _immutable_coordinates(self.nominal_coordinates_m)
        imperfect = _immutable_coordinates(self.imperfect_coordinates_m)
        if nominal.shape != imperfect.shape:
            raise ValueError("nominal and imperfect coordinate shapes must match")
        object.__setattr__(self, "nominal_coordinates_m", nominal)
        object.__setattr__(self, "imperfect_coordinates_m", imperfect)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "nominal_coordinates_m": self.nominal_coordinates_m.tolist(),
            "imperfect_coordinates_m": self.imperfect_coordinates_m.tolist(),
            "local_y_amplitude_m": self.local_y_amplitude_m,
            "local_z_amplitude_m": self.local_z_amplitude_m,
            "roll_deg": self.roll_deg,
            "mesh_hash": self.mesh_hash,
            "claim_boundary": self.claim_boundary,
        }


def sinusoidal_member_imperfection_mesh(
    start_coordinates_m: Any,
    end_coordinates_m: Any,
    *,
    element_count: int,
    local_y_amplitude_m: float = 0.0,
    local_z_amplitude_m: float = 0.0,
    roll_deg: float = 0.0,
) -> InitialImperfectionMesh3D:
    start = _vector3(start_coordinates_m, "start_coordinates_m")
    end = _vector3(end_coordinates_m, "end_coordinates_m")
    if type(element_count) is not int or element_count < 2:
        raise ValueError("element_count must be an integer of at least two")
    amplitude_y = _finite(local_y_amplitude_m, "local_y_amplitude_m")
    amplitude_z = _finite(local_z_amplitude_m, "local_z_amplitude_m")
    roll = _finite(roll_deg, "roll_deg")
    chord = end - start
    length = float(np.linalg.norm(chord))
    if length <= 1.0e-12:
        raise ValueError("imperfection member must have positive length")
    amplitude = math.hypot(amplitude_y, amplitude_z)
    if amplitude > 0.05 * length:
        raise ValueError("combined imperfection amplitude must not exceed L/20")
    local_axes = frame_rotation_matrix(start, end, roll_deg=roll)
    stations = np.linspace(0.0, 1.0, element_count + 1, dtype=np.float64)
    nominal = start[None, :] + stations[:, None] * chord[None, :]
    shape = np.sin(math.pi * stations)
    shape[0] = 0.0
    shape[-1] = 0.0
    offset_direction = amplitude_y * local_axes[1] + amplitude_z * local_axes[2]
    imperfect = nominal + shape[:, None] * offset_direction[None, :]
    payload = {
        "profile": INITIAL_IMPERFECTION_PROFILE,
        "nominal_coordinates_m": nominal.tolist(),
        "imperfect_coordinates_m": imperfect.tolist(),
        "local_y_amplitude_m": amplitude_y,
        "local_z_amplitude_m": amplitude_z,
        "roll_deg": roll,
    }
    return InitialImperfectionMesh3D(
        profile=INITIAL_IMPERFECTION_PROFILE,
        nominal_coordinates_m=nominal,
        imperfect_coordinates_m=imperfect,
        local_y_amplitude_m=amplitude_y,
        local_z_amplitude_m=amplitude_z,
        roll_deg=roll,
        mesh_hash=canonical_hash(payload),
    )


def _immutable_coordinates(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3 or not np.all(np.isfinite(array)):
        raise ValueError("coordinates must be a finite Nx3 array")
    result = np.array(array, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _vector3(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite three-vector")
    return array


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


__all__ = [
    "INITIAL_IMPERFECTION_CLAIM_BOUNDARY",
    "INITIAL_IMPERFECTION_PROFILE",
    "InitialImperfectionMesh3D",
    "sinusoidal_member_imperfection_mesh",
]
