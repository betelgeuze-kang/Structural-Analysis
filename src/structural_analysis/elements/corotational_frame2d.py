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

from structural_analysis.elements.corotational_frame2d_basic import (
    assemble_corotational_frame2d_global_response,
    corotational_frame2d_basic_kinematics,
)


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


def _immutable(array: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(array, dtype=np.float64)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class _ElasticFrame2DBasicResponse:
    basic_forces: np.ndarray
    consistent_tangent_basic: np.ndarray


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

    kinematics = corotational_frame2d_basic_kinematics(
        node_coordinates_m=node_coordinates_m,
        element_displacements=element_displacements,
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

    initial_length = kinematics.initial_length_m
    basic_deformations = kinematics.basic_deformations
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
    global_response = assemble_corotational_frame2d_global_response(
        kinematics=kinematics,
        basic_response=_ElasticFrame2DBasicResponse(
            basic_forces=_immutable(basic_forces),
            consistent_tangent_basic=_immutable(basic_stiffness),
        ),
    )
    energy = 0.5 * float(basic_deformations @ basic_forces)

    return CorotationalFrame2DResponse(
        strain_energy_kn_m=energy,
        internal_force_global=global_response.internal_force_global,
        consistent_tangent_global=global_response.consistent_tangent_global,
        basic_deformations=tuple(float(value) for value in basic_deformations),
        basic_forces=tuple(float(value) for value in basic_forces),
        initial_length_m=initial_length,
        current_length_m=kinematics.current_length_m,
        chord_rotation_change_rad=kinematics.chord_rotation_change_rad,
    )
