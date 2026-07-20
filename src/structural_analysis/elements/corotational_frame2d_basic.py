"""Exact basic-deformation boundary for a planar corotational frame.

This module separates current-chord kinematics from any elastic or stateful
section law.  A constitutive implementation supplies the three conjugate basic
forces and its algorithmic ``3 x 3`` tangent; this boundary maps them to the
six global element equations with the exact material and geometric tangent.

The principal chord-angle branch is intentionally bounded to one continuous
local solve path.  Multi-turn rotation unwrapping requires committed history
and belongs to a stateful consumer, not this stateless kinematic boundary. The
``StatefulCorotationalFiberBeam2D`` consumer owns that committed history.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Protocol, runtime_checkable

import numpy as np


COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER = (
    "ux_i_m",
    "uy_i_m",
    "theta_i_rad",
    "ux_j_m",
    "uy_j_m",
    "theta_j_rad",
)
COROTATIONAL_FRAME2D_BASIC_DEFORMATION_ORDER = (
    "axial_extension_m",
    "rotation_i_relative_to_chord_rad",
    "rotation_j_relative_to_chord_rad",
)
COROTATIONAL_FRAME2D_BASIC_FORCE_ORDER = (
    "axial_force_kN",
    "moment_i_kN_m",
    "moment_j_kN_m",
)
COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY = "principal_atan2_current_minus_initial.v1"


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _readonly_array(
    values: Any,
    *,
    shape: tuple[int, ...],
    name: str,
    shape_label: str | None = None,
) -> np.ndarray:
    expected = shape_label or f"array with shape {shape}"
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite {expected}") from exc
    if result.shape != shape or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite {expected}")
    immutable = np.array(result, dtype=np.float64, copy=True, order="C")
    immutable.setflags(write=False)
    return immutable


@runtime_checkable
class Frame2DBasicConstitutiveResponse(Protocol):
    """Minimal force/tangent response consumed by corotational recovery."""

    @property
    def basic_forces(self) -> Any: ...

    @property
    def consistent_tangent_basic(self) -> Any: ...


@dataclass(frozen=True)
class CorotationalFrame2DBasicKinematics:
    """Basic deformations and their exact global first/second derivatives."""

    initial_length_m: float
    current_length_m: float
    chord_rotation_change_rad: float
    current_direction: np.ndarray
    basic_deformations: np.ndarray
    basic_deformation_gradient_global: np.ndarray
    basic_deformation_hessians_global: np.ndarray

    def __post_init__(self) -> None:
        initial = _finite_scalar(self.initial_length_m, name="initial_length_m")
        current = _finite_scalar(self.current_length_m, name="current_length_m")
        if initial <= 0.0:
            raise ValueError("initial_length_m must be positive")
        if current <= 1.0e-9 * initial:
            raise ValueError("current_length_m must not be degenerate")
        object.__setattr__(self, "initial_length_m", initial)
        object.__setattr__(self, "current_length_m", current)
        object.__setattr__(
            self,
            "chord_rotation_change_rad",
            _finite_scalar(
                self.chord_rotation_change_rad,
                name="chord_rotation_change_rad",
            ),
        )
        object.__setattr__(
            self,
            "current_direction",
            _readonly_array(
                self.current_direction,
                shape=(2,),
                name="current_direction",
            ),
        )
        object.__setattr__(
            self,
            "basic_deformations",
            _readonly_array(
                self.basic_deformations,
                shape=(3,),
                name="basic_deformations",
            ),
        )
        object.__setattr__(
            self,
            "basic_deformation_gradient_global",
            _readonly_array(
                self.basic_deformation_gradient_global,
                shape=(3, 6),
                name="basic_deformation_gradient_global",
            ),
        )
        object.__setattr__(
            self,
            "basic_deformation_hessians_global",
            _readonly_array(
                self.basic_deformation_hessians_global,
                shape=(3, 6, 6),
                name="basic_deformation_hessians_global",
            ),
        )
        if not math.isclose(
            float(np.linalg.norm(self.current_direction)),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ):
            raise ValueError("current_direction must be a unit vector")

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_dof_order": list(COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER),
            "basic_deformation_order": list(
                COROTATIONAL_FRAME2D_BASIC_DEFORMATION_ORDER
            ),
            "angle_branch_policy": COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY,
            "initial_length_m": self.initial_length_m,
            "current_length_m": self.current_length_m,
            "chord_rotation_change_rad": self.chord_rotation_change_rad,
            "current_direction": self.current_direction.tolist(),
            "basic_deformations": self.basic_deformations.tolist(),
            "basic_deformation_gradient_global": (
                self.basic_deformation_gradient_global.tolist()
            ),
            "basic_deformation_hessians_global": (
                self.basic_deformation_hessians_global.tolist()
            ),
        }


@dataclass(frozen=True)
class CorotationalFrame2DGlobalResponse:
    """Global force plus material/geometric consistent-tangent decomposition."""

    internal_force_global: np.ndarray
    material_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "internal_force_global",
            "material_tangent_global",
            "geometric_tangent_global",
            "consistent_tangent_global",
        ):
            shape = (6,) if name == "internal_force_global" else (6, 6)
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), shape=shape, name=name),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_dof_order": list(COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER),
            "basic_force_order": list(COROTATIONAL_FRAME2D_BASIC_FORCE_ORDER),
            "internal_force_global": self.internal_force_global.tolist(),
            "material_tangent_global": self.material_tangent_global.tolist(),
            "geometric_tangent_global": self.geometric_tangent_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
        }


def corotational_frame2d_basic_kinematics(
    *,
    node_coordinates_m: Any,
    element_displacements: Any,
) -> CorotationalFrame2DBasicKinematics:
    """Evaluate exact current-chord basic deformations and derivatives."""

    coordinates = _readonly_array(
        node_coordinates_m,
        shape=(2, 2),
        name="node_coordinates_m",
        shape_label="2x2 array",
    )
    displacements = _readonly_array(
        element_displacements,
        shape=(6,),
        name="element_displacements",
        shape_label="six-vector",
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
    if not math.isfinite(current_length) or current_length <= 1.0e-9 * initial_length:
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
    length_hessian = chord_difference.T @ length_hessian_chord @ chord_difference
    angle_hessian = chord_difference.T @ angle_hessian_chord @ chord_difference
    basic_hessians = np.stack(
        (length_hessian, -angle_hessian, -angle_hessian),
        axis=0,
    )

    return CorotationalFrame2DBasicKinematics(
        initial_length_m=initial_length,
        current_length_m=current_length,
        chord_rotation_change_rad=angle_change,
        current_direction=np.asarray([cosine, sine], dtype=np.float64),
        basic_deformations=basic_deformations,
        basic_deformation_gradient_global=basic_gradient,
        basic_deformation_hessians_global=basic_hessians,
    )


def assemble_corotational_frame2d_global_response(
    *,
    kinematics: CorotationalFrame2DBasicKinematics,
    basic_response: Frame2DBasicConstitutiveResponse,
) -> CorotationalFrame2DGlobalResponse:
    """Map one basic force/tangent response to exact global equations."""

    if type(kinematics) is not CorotationalFrame2DBasicKinematics:
        raise ValueError("kinematics must be CorotationalFrame2DBasicKinematics")
    if not isinstance(basic_response, Frame2DBasicConstitutiveResponse):
        raise ValueError("basic_response must satisfy Frame2DBasicConstitutiveResponse")
    basic_forces = _readonly_array(
        basic_response.basic_forces,
        shape=(3,),
        name="basic_response.basic_forces",
    )
    basic_tangent = _readonly_array(
        basic_response.consistent_tangent_basic,
        shape=(3, 3),
        name="basic_response.consistent_tangent_basic",
    )
    gradient = kinematics.basic_deformation_gradient_global
    material_tangent = gradient.T @ basic_tangent @ gradient
    geometric_tangent = np.einsum(
        "a,aij->ij",
        basic_forces,
        kinematics.basic_deformation_hessians_global,
    )
    internal_force = gradient.T @ basic_forces
    return CorotationalFrame2DGlobalResponse(
        internal_force_global=internal_force,
        material_tangent_global=material_tangent,
        geometric_tangent_global=geometric_tangent,
        consistent_tangent_global=material_tangent + geometric_tangent,
    )


__all__ = [
    "COROTATIONAL_FRAME2D_ANGLE_BRANCH_POLICY",
    "COROTATIONAL_FRAME2D_BASIC_DEFORMATION_ORDER",
    "COROTATIONAL_FRAME2D_BASIC_FORCE_ORDER",
    "COROTATIONAL_FRAME2D_GLOBAL_DOF_ORDER",
    "CorotationalFrame2DBasicKinematics",
    "CorotationalFrame2DGlobalResponse",
    "Frame2DBasicConstitutiveResponse",
    "assemble_corotational_frame2d_global_response",
    "corotational_frame2d_basic_kinematics",
]
