"""Strict local 3D Timoshenko frame stiffness reference."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.elements.frame3d import FrameProps


TIMOSHENKO_FRAME3D_PROFILE = "two_node_timoshenko_frame3d_shear_condensed.v1"
TIMOSHENKO_FRAME3D_CLAIM_BOUNDARY = (
    "Linear local 12-DOF prismatic frame with explicit effective shear areas; "
    "no shear locking study, nonlinear section state, or external validation."
)


@dataclass(frozen=True)
class TimoshenkoFrame3DSection:
    frame: FrameProps
    effective_shear_area_y_m2: float
    effective_shear_area_z_m2: float

    def __post_init__(self) -> None:
        for name in ("effective_shear_area_y_m2", "effective_shear_area_z_m2"):
            value = _positive(getattr(self, name), name)
            object.__setattr__(self, name, value)


def local_timoshenko_frame_stiffness(
    section: TimoshenkoFrame3DSection,
    length_m: float,
) -> np.ndarray:
    """Return the symmetric 12x12 local stiffness in frame3d DOF order."""

    length = _positive(length_m, "length_m")
    props = section.frame
    stiffness = np.zeros((12, 12), dtype=np.float64)
    _add_pair(
        stiffness,
        0,
        6,
        props.e_n_per_m2 * props.area_m2 / length,
    )
    _add_pair(
        stiffness,
        3,
        9,
        props.g_n_per_m2 * props.j_m4 / length,
    )

    phi_z = (
        12.0
        * props.e_n_per_m2
        * props.iz_m4
        / (props.g_n_per_m2 * section.effective_shear_area_y_m2 * length**2)
    )
    bending_z = _bending_plane_stiffness(
        flexural_rigidity=props.e_n_per_m2 * props.iz_m4,
        length=length,
        shear_parameter=phi_z,
        rotation_sign=1.0,
    )
    _scatter(stiffness, (1, 5, 7, 11), bending_z)

    phi_y = (
        12.0
        * props.e_n_per_m2
        * props.iy_m4
        / (props.g_n_per_m2 * section.effective_shear_area_z_m2 * length**2)
    )
    bending_y = _bending_plane_stiffness(
        flexural_rigidity=props.e_n_per_m2 * props.iy_m4,
        length=length,
        shear_parameter=phi_y,
        rotation_sign=-1.0,
    )
    _scatter(stiffness, (2, 4, 8, 10), bending_y)
    result = 0.5 * (stiffness + stiffness.T)
    result.setflags(write=False)
    return result


def timoshenko_basic_bending_stiffness(
    *,
    flexural_rigidity_kn_m2: float,
    shear_rigidity_kn: float,
    length_m: float,
) -> np.ndarray:
    """Return the 2x2 end-rotation stiffness relative to the current chord."""

    flexural = _positive(flexural_rigidity_kn_m2, "flexural_rigidity_kn_m2")
    shear = _positive(shear_rigidity_kn, "shear_rigidity_kn")
    length = _positive(length_m, "length_m")
    phi = 12.0 * flexural / (shear * length**2)
    factor = flexural / (length * (1.0 + phi))
    result = factor * np.asarray(
        [[4.0 + phi, 2.0 - phi], [2.0 - phi, 4.0 + phi]],
        dtype=np.float64,
    )
    result.setflags(write=False)
    return result


def _bending_plane_stiffness(
    *,
    flexural_rigidity: float,
    length: float,
    shear_parameter: float,
    rotation_sign: float,
) -> np.ndarray:
    factor = flexural_rigidity / (length**3 * (1.0 + shear_parameter))
    signed_six_l = rotation_sign * 6.0 * length
    return factor * np.asarray(
        [
            [12.0, signed_six_l, -12.0, signed_six_l],
            [
                signed_six_l,
                (4.0 + shear_parameter) * length**2,
                -signed_six_l,
                (2.0 - shear_parameter) * length**2,
            ],
            [-12.0, -signed_six_l, 12.0, -signed_six_l],
            [
                signed_six_l,
                (2.0 - shear_parameter) * length**2,
                -signed_six_l,
                (4.0 + shear_parameter) * length**2,
            ],
        ],
        dtype=np.float64,
    )


def _add_pair(matrix: np.ndarray, first: int, second: int, value: float) -> None:
    matrix[first, first] += value
    matrix[first, second] -= value
    matrix[second, first] -= value
    matrix[second, second] += value


def _scatter(
    target: np.ndarray,
    indices: tuple[int, ...],
    values: np.ndarray,
) -> None:
    target[np.ix_(indices, indices)] += values


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return normalized


__all__ = [
    "TIMOSHENKO_FRAME3D_CLAIM_BOUNDARY",
    "TIMOSHENKO_FRAME3D_PROFILE",
    "TimoshenkoFrame3DSection",
    "local_timoshenko_frame_stiffness",
    "timoshenko_basic_bending_stiffness",
]
