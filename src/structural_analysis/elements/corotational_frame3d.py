"""Bounded energy-based 3D corotational Timoshenko frame reference."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation

from structural_analysis.elements.frame3d import frame_rotation_matrix
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
    timoshenko_basic_bending_stiffness,
)


COROTATIONAL_FRAME3D_PROFILE = "energy_corotated_timoshenko_frame3d_fd2.v1"
COROTATIONAL_FRAME3D_DERIVATIVE_PROFILE = (
    "five_point_energy_gradient_symmetric_energy_hessian.v1"
)
COROTATIONAL_FRAME3D_GLOBAL_DOF_ORDER = (
    "ux_i_m",
    "uy_i_m",
    "uz_i_m",
    "rotation_vector_x_i_rad",
    "rotation_vector_y_i_rad",
    "rotation_vector_z_i_rad",
    "ux_j_m",
    "uy_j_m",
    "uz_j_m",
    "rotation_vector_x_j_rad",
    "rotation_vector_y_j_rad",
    "rotation_vector_z_j_rad",
)
COROTATIONAL_FRAME3D_BASIC_DEFORMATION_ORDER = (
    "axial_extension_m",
    "torsion_i_relative_to_corotated_frame_rad",
    "bending_y_i_relative_to_corotated_frame_rad",
    "bending_z_i_relative_to_corotated_frame_rad",
    "torsion_j_relative_to_corotated_frame_rad",
    "bending_y_j_relative_to_corotated_frame_rad",
    "bending_z_j_relative_to_corotated_frame_rad",
)
COROTATIONAL_FRAME3D_CLAIM_BOUNDARY = (
    "One elastic two-node 3D Timoshenko element with principal rotation-vector "
    "coordinates and numerical energy derivatives; no global nonlinear assembly, "
    "stateful section, warping coupling, multi-turn rotation, or external V&V."
)


@dataclass(frozen=True)
class CorotationalFrame3DBasicKinematics:
    basic_deformations: np.ndarray
    initial_length_m: float
    current_length_m: float
    corotated_axes_global: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "basic_deformations",
            _immutable(self.basic_deformations, (7,), "basic_deformations"),
        )
        object.__setattr__(
            self,
            "corotated_axes_global",
            _immutable(
                self.corotated_axes_global,
                (3, 3),
                "corotated_axes_global",
            ),
        )


@dataclass(frozen=True)
class CorotationalFrame3DResponse:
    strain_energy_kn_m: float
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray
    basic_deformations: np.ndarray
    basic_forces: np.ndarray
    initial_length_m: float
    current_length_m: float
    corotated_axes_global: np.ndarray
    profile: str = COROTATIONAL_FRAME3D_PROFILE
    derivative_profile: str = COROTATIONAL_FRAME3D_DERIVATIVE_PROFILE
    claim_boundary: str = COROTATIONAL_FRAME3D_CLAIM_BOUNDARY

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "internal_force_global",
            _immutable(self.internal_force_global, (12,), "internal_force_global"),
        )
        object.__setattr__(
            self,
            "consistent_tangent_global",
            _immutable(
                self.consistent_tangent_global,
                (12, 12),
                "consistent_tangent_global",
            ),
        )
        object.__setattr__(
            self,
            "basic_deformations",
            _immutable(self.basic_deformations, (7,), "basic_deformations"),
        )
        object.__setattr__(
            self,
            "basic_forces",
            _immutable(self.basic_forces, (7,), "basic_forces"),
        )
        object.__setattr__(
            self,
            "corotated_axes_global",
            _immutable(
                self.corotated_axes_global,
                (3, 3),
                "corotated_axes_global",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "derivative_profile": self.derivative_profile,
            "global_dof_order": list(COROTATIONAL_FRAME3D_GLOBAL_DOF_ORDER),
            "basic_deformation_order": list(
                COROTATIONAL_FRAME3D_BASIC_DEFORMATION_ORDER
            ),
            "strain_energy_kn_m": self.strain_energy_kn_m,
            "internal_force_global": self.internal_force_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "basic_deformations": self.basic_deformations.tolist(),
            "basic_forces": self.basic_forces.tolist(),
            "initial_length_m": self.initial_length_m,
            "current_length_m": self.current_length_m,
            "corotated_axes_global": self.corotated_axes_global.tolist(),
            "claim_boundary": self.claim_boundary,
        }


def corotational_frame3d_response(
    *,
    node_coordinates_m: Any,
    element_displacements: Any,
    section: TimoshenkoFrame3DSection,
    local_axis_roll_deg: float = 0.0,
) -> CorotationalFrame3DResponse:
    """Evaluate objective energy plus deterministic numerical derivatives."""

    coordinates = _coordinates(node_coordinates_m)
    displacement = _displacements(element_displacements)
    roll = _finite(local_axis_roll_deg, "local_axis_roll_deg")
    initial_length = float(np.linalg.norm(coordinates[1] - coordinates[0]))
    if initial_length <= 1.0e-12:
        raise ValueError("frame3d initial chord must have positive length")
    _validate_rotation_vectors(displacement)
    energy, basic, basic_forces, current_length, axes = _energy_state(
        coordinates,
        displacement,
        section,
        roll,
    )
    gradient_steps = _derivative_steps(initial_length, relative=2.0e-6)
    hessian_steps = _derivative_steps(initial_length, relative=2.0e-4)
    internal_force = _energy_gradient(
        coordinates,
        displacement,
        section,
        roll,
        gradient_steps,
    )
    tangent = _energy_hessian(
        coordinates,
        displacement,
        section,
        roll,
        hessian_steps,
        center_energy=energy,
    )
    return CorotationalFrame3DResponse(
        strain_energy_kn_m=energy,
        internal_force_global=internal_force,
        consistent_tangent_global=tangent,
        basic_deformations=basic,
        basic_forces=basic_forces,
        initial_length_m=initial_length,
        current_length_m=current_length,
        corotated_axes_global=axes,
    )


def corotational_frame3d_strain_energy(
    *,
    node_coordinates_m: Any,
    element_displacements: Any,
    section: TimoshenkoFrame3DSection,
    local_axis_roll_deg: float = 0.0,
) -> float:
    """Expose the independent scalar energy for derivative verification."""

    coordinates = _coordinates(node_coordinates_m)
    displacement = _displacements(element_displacements)
    _validate_rotation_vectors(displacement)
    energy, _, _, _, _ = _energy_state(
        coordinates,
        displacement,
        section,
        _finite(local_axis_roll_deg, "local_axis_roll_deg"),
    )
    return energy


def corotational_frame3d_basic_kinematics(
    *,
    node_coordinates_m: Any,
    element_displacements: Any,
    local_axis_roll_deg: float = 0.0,
) -> CorotationalFrame3DBasicKinematics:
    """Evaluate the objective seven-mode kinematics without energy derivatives."""

    coordinates = _coordinates(node_coordinates_m)
    displacement = _displacements(element_displacements)
    _validate_rotation_vectors(displacement)
    basic, initial_length, current_length, axes = _kinematic_state(
        coordinates,
        displacement,
        _finite(local_axis_roll_deg, "local_axis_roll_deg"),
    )
    return CorotationalFrame3DBasicKinematics(
        basic_deformations=basic,
        initial_length_m=initial_length,
        current_length_m=current_length,
        corotated_axes_global=axes,
    )


def _energy_state(
    coordinates: np.ndarray,
    displacement: np.ndarray,
    section: TimoshenkoFrame3DSection,
    roll_deg: float,
) -> tuple[float, np.ndarray, np.ndarray, float, np.ndarray]:
    basic, initial_length, current_length, current_axes = _kinematic_state(
        coordinates,
        displacement,
        roll_deg,
    )
    basic_stiffness = _basic_stiffness(section, initial_length)
    basic_forces = basic_stiffness @ basic
    energy = 0.5 * float(basic @ basic_forces)
    if not math.isfinite(energy) or energy < -1.0e-12:
        raise ValueError("corotational frame3d energy is invalid")
    return energy, basic, basic_forces, current_length, current_axes


def _kinematic_state(
    coordinates: np.ndarray,
    displacement: np.ndarray,
    roll_deg: float,
) -> tuple[np.ndarray, float, float, np.ndarray]:
    initial_start = coordinates[0]
    initial_end = coordinates[1]
    initial_chord = initial_end - initial_start
    initial_length = float(np.linalg.norm(initial_chord))
    current_start = initial_start + displacement[0:3]
    current_end = initial_end + displacement[6:9]
    current_chord = current_end - current_start
    current_length = float(np.linalg.norm(current_chord))
    if not math.isfinite(current_length) or current_length <= 1.0e-6 * initial_length:
        raise ValueError("frame3d current chord is degenerate")
    initial_axes = frame_rotation_matrix(
        initial_start,
        initial_end,
        roll_deg=roll_deg,
    ).T
    rotation_i = Rotation.from_rotvec(displacement[3:6]).as_matrix()
    rotation_j = Rotation.from_rotvec(displacement[9:12]).as_matrix()
    current_x = current_chord / current_length
    average_y = rotation_i @ initial_axes[:, 1] + rotation_j @ initial_axes[:, 1]
    projected_y = average_y - current_x * float(current_x @ average_y)
    projected_norm = float(np.linalg.norm(projected_y))
    if not math.isfinite(projected_norm) or projected_norm <= 1.0e-8:
        raise ValueError("corotated transverse director is degenerate")
    current_y = projected_y / projected_norm
    current_z = np.cross(current_x, current_y)
    current_z /= float(np.linalg.norm(current_z))
    current_y = np.cross(current_z, current_x)
    current_axes = np.column_stack([current_x, current_y, current_z])

    relative_i = current_axes.T @ rotation_i @ initial_axes
    relative_j = current_axes.T @ rotation_j @ initial_axes
    rotation_relative_i = Rotation.from_matrix(relative_i).as_rotvec()
    rotation_relative_j = Rotation.from_matrix(relative_j).as_rotvec()
    if (
        max(
            float(np.linalg.norm(rotation_relative_i)),
            float(np.linalg.norm(rotation_relative_j)),
        )
        >= math.pi - 1.0e-6
    ):
        raise ValueError("relative rotation reached the principal-branch boundary")
    basic = np.asarray(
        [
            current_length - initial_length,
            *rotation_relative_i.tolist(),
            *rotation_relative_j.tolist(),
        ],
        dtype=np.float64,
    )
    return basic, initial_length, current_length, current_axes


def _basic_stiffness(
    section: TimoshenkoFrame3DSection,
    initial_length: float,
) -> np.ndarray:
    props = section.frame
    stiffness = np.zeros((7, 7), dtype=np.float64)
    stiffness[0, 0] = props.e_n_per_m2 * props.area_m2 / initial_length
    torsion = props.g_n_per_m2 * props.j_m4 / initial_length
    stiffness[np.ix_((1, 4), (1, 4))] = np.asarray(
        [[torsion, -torsion], [-torsion, torsion]],
        dtype=np.float64,
    )
    stiffness[np.ix_((2, 5), (2, 5))] = timoshenko_basic_bending_stiffness(
        flexural_rigidity_kn_m2=props.e_n_per_m2 * props.iy_m4,
        shear_rigidity_kn=(props.g_n_per_m2 * section.effective_shear_area_z_m2),
        length_m=initial_length,
    )
    stiffness[np.ix_((3, 6), (3, 6))] = timoshenko_basic_bending_stiffness(
        flexural_rigidity_kn_m2=props.e_n_per_m2 * props.iz_m4,
        shear_rigidity_kn=(props.g_n_per_m2 * section.effective_shear_area_y_m2),
        length_m=initial_length,
    )
    return stiffness


def _energy_only(
    coordinates: np.ndarray,
    displacement: np.ndarray,
    section: TimoshenkoFrame3DSection,
    roll_deg: float,
) -> float:
    return _energy_state(coordinates, displacement, section, roll_deg)[0]


def _energy_gradient(
    coordinates: np.ndarray,
    displacement: np.ndarray,
    section: TimoshenkoFrame3DSection,
    roll_deg: float,
    steps: np.ndarray,
) -> np.ndarray:
    gradient = np.empty(12, dtype=np.float64)
    for index, step in enumerate(steps):
        plus_one = displacement.copy()
        minus_one = displacement.copy()
        plus_two = displacement.copy()
        minus_two = displacement.copy()
        plus_one[index] += step
        minus_one[index] -= step
        plus_two[index] += 2.0 * step
        minus_two[index] -= 2.0 * step
        gradient[index] = (
            -_energy_only(coordinates, plus_two, section, roll_deg)
            + 8.0 * _energy_only(coordinates, plus_one, section, roll_deg)
            - 8.0 * _energy_only(coordinates, minus_one, section, roll_deg)
            + _energy_only(coordinates, minus_two, section, roll_deg)
        ) / (12.0 * step)
    return gradient


def _energy_hessian(
    coordinates: np.ndarray,
    displacement: np.ndarray,
    section: TimoshenkoFrame3DSection,
    roll_deg: float,
    steps: np.ndarray,
    *,
    center_energy: float,
) -> np.ndarray:
    hessian = np.empty((12, 12), dtype=np.float64)
    for first in range(12):
        first_step = steps[first]
        plus_one = displacement.copy()
        minus_one = displacement.copy()
        plus_two = displacement.copy()
        minus_two = displacement.copy()
        plus_one[first] += first_step
        minus_one[first] -= first_step
        plus_two[first] += 2.0 * first_step
        minus_two[first] -= 2.0 * first_step
        hessian[first, first] = (
            -_energy_only(coordinates, plus_two, section, roll_deg)
            + 16.0 * _energy_only(coordinates, plus_one, section, roll_deg)
            - 30.0 * center_energy
            + 16.0 * _energy_only(coordinates, minus_one, section, roll_deg)
            - _energy_only(coordinates, minus_two, section, roll_deg)
        ) / (12.0 * first_step**2)
        for second in range(first + 1, 12):
            second_step = steps[second]
            plus_plus = displacement.copy()
            plus_minus = displacement.copy()
            minus_plus = displacement.copy()
            minus_minus = displacement.copy()
            plus_plus[first] += first_step
            plus_plus[second] += second_step
            plus_minus[first] += first_step
            plus_minus[second] -= second_step
            minus_plus[first] -= first_step
            minus_plus[second] += second_step
            minus_minus[first] -= first_step
            minus_minus[second] -= second_step
            value = (
                _energy_only(coordinates, plus_plus, section, roll_deg)
                - _energy_only(coordinates, plus_minus, section, roll_deg)
                - _energy_only(coordinates, minus_plus, section, roll_deg)
                + _energy_only(coordinates, minus_minus, section, roll_deg)
            ) / (4.0 * first_step * second_step)
            hessian[first, second] = value
            hessian[second, first] = value
    return 0.5 * (hessian + hessian.T)


def _derivative_steps(initial_length: float, *, relative: float) -> np.ndarray:
    translation_step = relative * max(initial_length, 1.0)
    return np.asarray(
        [
            translation_step,
            translation_step,
            translation_step,
            relative,
            relative,
            relative,
            translation_step,
            translation_step,
            translation_step,
            relative,
            relative,
            relative,
        ],
        dtype=np.float64,
    )


def _validate_rotation_vectors(displacement: np.ndarray) -> None:
    for values in (displacement[3:6], displacement[9:12]):
        if float(np.linalg.norm(values)) >= math.pi - 1.0e-6:
            raise ValueError(
                "nodal rotation vector reached the principal-branch boundary"
            )


def _coordinates(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (2, 3) or not np.all(np.isfinite(array)):
        raise ValueError("node_coordinates_m must be a finite 2x3 array")
    return np.array(array, copy=True)


def _displacements(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (12,) or not np.all(np.isfinite(array)):
        raise ValueError("element_displacements must be a finite 12-vector")
    return np.array(array, copy=True)


def _immutable(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


__all__ = [
    "COROTATIONAL_FRAME3D_BASIC_DEFORMATION_ORDER",
    "COROTATIONAL_FRAME3D_CLAIM_BOUNDARY",
    "COROTATIONAL_FRAME3D_DERIVATIVE_PROFILE",
    "COROTATIONAL_FRAME3D_GLOBAL_DOF_ORDER",
    "COROTATIONAL_FRAME3D_PROFILE",
    "CorotationalFrame3DBasicKinematics",
    "CorotationalFrame3DResponse",
    "corotational_frame3d_basic_kinematics",
    "corotational_frame3d_response",
    "corotational_frame3d_strain_energy",
]
