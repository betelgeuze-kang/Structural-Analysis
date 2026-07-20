"""Reusable small-strain, large-rotation planar frame element kernel.

The element uses a two-node Euler--Bernoulli basic system with axial extension
and two end rotations measured relative to the current chord. Internal force is
the exact gradient of the element strain energy and the consistent tangent is
its exact Hessian.

This module owns only the element response. It does not own global assembly,
constraints, load stepping, arc-length control, result authority, or benchmark
acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _positive_scalar(value: Any, *, name: str) -> float:
    result = _finite_scalar(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _coordinates2x2(values: Any) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("node_coordinates_m must be a finite 2x2 array") from exc
    if result.shape != (2, 2) or not np.all(np.isfinite(result)):
        raise ValueError("node_coordinates_m must be a finite 2x2 array")
    return np.ascontiguousarray(result, dtype=np.float64)


def _vector6(values: Any, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite six-vector") from exc
    if result.shape != (6,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite six-vector")
    return np.ascontiguousarray(result, dtype=np.float64)


def _immutable(array: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(array, dtype=np.float64)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class CorotationalFrame2DResponse:
    """Energy, exact gradient, and exact Hessian in global element order.

    Physical equation order is
    ``[ux_i, uy_i, theta_i, ux_j, uy_j, theta_j]``. Translational forces are in
    kN and rotational components are moments in kN m.
    """

    strain_energy_kn_m: float
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray
    basic_deformations: tuple[float, float, float]
    basic_forces: tuple[float, float, float]
    initial_length_m: float
    current_length_m: float
    chord_rotation_change_rad: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strain_energy_kn_m": self.strain_energy_kn_m,
            "internal_force_global": self.internal_force_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "basic_deformations": list(self.basic_deformations),
            "basic_forces": list(self.basic_forces),
            "initial_length_m": self.initial_length_m,
            "current_length_m": self.current_length_m,
            "chord_rotation_change_rad": self.chord_rotation_change_rad,
        }


def corotational_frame2d_response(
    *,
    node_coordinates_m: Any,
    element_displacements: Any,
    youngs_modulus_kn_per_m2: float,
    area_m2: float,
    second_moment_m4: float,
) -> CorotationalFrame2DResponse:
    """Evaluate the planar corotational frame energy and exact derivatives.

    The basic deformation vector is

    ``v = [l-L, theta_i-(phi-phi0), theta_j-(phi-phi0)]``.

    With the linear elastic basic stiffness ``kb``, the response is

    ``U = 0.5 v.T kb v``
    ``f = B.T kb v``
    ``K = B.T kb B + N Hessian(l) - (Mi+Mj) Hessian(phi)``.
    """

    coordinates = _coordinates2x2(node_coordinates_m)
    displacements = _vector6(
        element_displacements,
        name="element_displacements",
    )
    modulus = _positive_scalar(
        youngs_modulus_kn_per_m2,
        name="youngs_modulus_kn_per_m2",
    )
    area = _positive_scalar(area_m2, name="area_m2")
    second_moment = _positive_scalar(
        second_moment_m4,
        name="second_moment_m4",
    )

    initial_chord = coordinates[1] - coordinates[0]
    initial_length = float(np.linalg.norm(initial_chord))
    if initial_length <= np.finfo(np.float64).eps:
        raise ValueError("frame element nodes must not coincide")
    initial_angle = math.atan2(initial_chord[1], initial_chord[0])

    chord_difference = np.asarray(
        [
            [-1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0, 0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    current_chord = initial_chord + chord_difference @ displacements
    current_length = float(np.linalg.norm(current_chord))
    if (
        not math.isfinite(current_length)
        or current_length <= 1.0e-9 * initial_length
    ):
        raise ValueError("frame element current chord is degenerate")

    cosine = float(current_chord[0] / current_length)
    sine = float(current_chord[1] / current_length)
    current_angle = math.atan2(current_chord[1], current_chord[0])
    raw_angle_change = current_angle - initial_angle
    angle_change = math.atan2(
        math.sin(raw_angle_change),
        math.cos(raw_angle_change),
    )

    basic_deformations = np.asarray(
        [
            current_length - initial_length,
            displacements[2] - angle_change,
            displacements[5] - angle_change,
        ],
        dtype=np.float64,
    )
    basic_stiffness = np.asarray(
        [
            [modulus * area / initial_length, 0.0, 0.0],
            [
                0.0,
                4.0 * modulus * second_moment / initial_length,
                2.0 * modulus * second_moment / initial_length,
            ],
            [
                0.0,
                2.0 * modulus * second_moment / initial_length,
                4.0 * modulus * second_moment / initial_length,
            ],
        ],
        dtype=np.float64,
    )
    basic_forces = basic_stiffness @ basic_deformations

    length_gradient_chord = np.asarray([cosine, sine], dtype=np.float64)
    angle_gradient_chord = np.asarray(
        [-sine / current_length, cosine / current_length],
        dtype=np.float64,
    )
    rotation_i_gradient = np.zeros(6, dtype=np.float64)
    rotation_i_gradient[2] = 1.0
    rotation_j_gradient = np.zeros(6, dtype=np.float64)
    rotation_j_gradient[5] = 1.0
    basic_gradient = np.vstack(
        (
            chord_difference.T @ length_gradient_chord,
            rotation_i_gradient - chord_difference.T @ angle_gradient_chord,
            rotation_j_gradient - chord_difference.T @ angle_gradient_chord,
        )
    )

    length_hessian_chord = (
        np.asarray(
            [
                [sine**2, -cosine * sine],
                [-cosine * sine, cosine**2],
            ],
            dtype=np.float64,
        )
        / current_length
    )
    angle_hessian_chord = (
        np.asarray(
            [
                [2.0 * cosine * sine, sine**2 - cosine**2],
                [sine**2 - cosine**2, -2.0 * cosine * sine],
            ],
            dtype=np.float64,
        )
        / current_length**2
    )
    length_hessian = (
        chord_difference.T @ length_hessian_chord @ chord_difference
    )
    angle_hessian = chord_difference.T @ angle_hessian_chord @ chord_difference

    internal_force = basic_gradient.T @ basic_forces
    tangent = (
        basic_gradient.T @ basic_stiffness @ basic_gradient
        + basic_forces[0] * length_hessian
        - (basic_forces[1] + basic_forces[2]) * angle_hessian
    )
    energy = 0.5 * float(basic_deformations @ basic_forces)

    return CorotationalFrame2DResponse(
        strain_energy_kn_m=energy,
        internal_force_global=_immutable(internal_force),
        consistent_tangent_global=_immutable(tangent),
        basic_deformations=tuple(float(value) for value in basic_deformations),
        basic_forces=tuple(float(value) for value in basic_forces),
        initial_length_m=initial_length,
        current_length_m=current_length,
        chord_rotation_change_rad=angle_change,
    )
