"""Reusable two-node 2D current-chord truss element kernel.

The kernel owns only element kinematics, force recovery, and the exact
material-plus-initial-stress tangent. It accepts any stateful uniaxial material
that exposes ``integrate(total_strain, committed_state)`` and returns finite
``stress_mpa`` and ``consistent_tangent_mpa`` values.

It does not own load stepping, Newton/arc-length orchestration, state commit,
result authority, or benchmark acceptance. Those remain higher-level
responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Protocol

import numpy as np


MPA_M2_TO_KN = 1000.0


class StatefulUniaxialResponse(Protocol):
    """Minimum response contract consumed by the element kernel."""

    stress_mpa: float
    consistent_tangent_mpa: float
    state: Any


class StatefulUniaxialMaterial(Protocol):
    """Minimum material contract consumed by the element kernel."""

    def integrate(
        self,
        total_strain: float,
        committed_state: Any,
    ) -> StatefulUniaxialResponse: ...


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


def _vector2(values: Any, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite two-vector") from exc
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite two-vector")
    return np.ascontiguousarray(result, dtype=np.float64)


def _immutable(array: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(array, dtype=np.float64)
    result.setflags(write=False)
    return result


def _material_response_payload(response: Any) -> Any:
    serializer = getattr(response, "to_dict", None)
    if callable(serializer):
        return serializer()
    return {
        "stress_mpa": float(response.stress_mpa),
        "consistent_tangent_mpa": float(response.consistent_tangent_mpa),
    }


@dataclass(frozen=True)
class CorotationalTruss2DResponse:
    """Force and exact consistent tangent for one two-node truss element.

    Global translational equation order is ``[ux_i, uy_i, ux_j, uy_j]``.
    Internal force uses the standard element sign convention
    ``[-N*n_x, -N*n_y, N*n_x, N*n_y]``.
    """

    element_id: str
    initial_length_m: float
    current_length_m: float
    current_direction: np.ndarray
    engineering_strain: float
    axial_force_kn: float
    internal_force_global_kn: np.ndarray
    material_tangent_global_kn_per_m: np.ndarray
    geometric_tangent_global_kn_per_m: np.ndarray
    consistent_tangent_global_kn_per_m: np.ndarray
    material_response: StatefulUniaxialResponse

    @property
    def node_j_internal_force_kn(self) -> np.ndarray:
        """Return the free-end force used by the historical fixed-base benchmark."""

        return self.internal_force_global_kn[2:4]

    @property
    def node_j_material_tangent_kn_per_m(self) -> np.ndarray:
        return self.material_tangent_global_kn_per_m[2:4, 2:4]

    @property
    def node_j_geometric_tangent_kn_per_m(self) -> np.ndarray:
        return self.geometric_tangent_global_kn_per_m[2:4, 2:4]

    @property
    def node_j_consistent_tangent_kn_per_m(self) -> np.ndarray:
        return self.consistent_tangent_global_kn_per_m[2:4, 2:4]

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "initial_length_m": self.initial_length_m,
            "current_length_m": self.current_length_m,
            "current_direction": self.current_direction.tolist(),
            "engineering_strain": self.engineering_strain,
            "axial_force_kn": self.axial_force_kn,
            "internal_force_global_kn": self.internal_force_global_kn.tolist(),
            "material_tangent_global_kn_per_m": (
                self.material_tangent_global_kn_per_m.tolist()
            ),
            "geometric_tangent_global_kn_per_m": (
                self.geometric_tangent_global_kn_per_m.tolist()
            ),
            "consistent_tangent_global_kn_per_m": (
                self.consistent_tangent_global_kn_per_m.tolist()
            ),
            "material_response": _material_response_payload(self.material_response),
        }


def corotational_truss2d_response(
    *,
    element_id: str,
    node_i_coordinate_m: Any,
    node_j_coordinate_m: Any,
    node_i_displacement_m: Any,
    node_j_displacement_m: Any,
    area_m2: float,
    material: StatefulUniaxialMaterial,
    committed_state: Any,
) -> CorotationalTruss2DResponse:
    """Evaluate exact current-chord force and consistent tangent.

    With ``n`` the current chord direction, ``N`` the axial force, ``l`` the
    current length, ``L0`` the reference length, and ``Et`` the algorithmic
    material tangent, the node-j translational tangent is

    ``A*Et/L0 * (n outer n) + N/l * (I - n outer n)``.

    The full four-equation matrix is assembled with the standard
    ``[[k, -k], [-k, k]]`` two-node topology. Every material evaluation is
    performed from the caller-supplied committed parent; the kernel never
    mutates or commits state.
    """

    normalized_id = str(element_id).strip()
    if not normalized_id:
        raise ValueError("element_id must be non-empty")

    coordinate_i = _vector2(node_i_coordinate_m, name="node_i_coordinate_m")
    coordinate_j = _vector2(node_j_coordinate_m, name="node_j_coordinate_m")
    displacement_i = _vector2(
        node_i_displacement_m,
        name="node_i_displacement_m",
    )
    displacement_j = _vector2(
        node_j_displacement_m,
        name="node_j_displacement_m",
    )
    area = _positive_scalar(area_m2, name="area_m2")

    initial_chord = coordinate_j - coordinate_i
    initial_length = float(np.linalg.norm(initial_chord))
    if not math.isfinite(initial_length) or initial_length <= 0.0:
        raise ValueError("the initial bar length must be positive")

    current_chord = (
        coordinate_j + displacement_j - coordinate_i - displacement_i
    )
    current_length = float(np.linalg.norm(current_chord))
    if (
        not math.isfinite(current_length)
        or current_length <= np.finfo(np.float64).eps * initial_length
    ):
        raise ValueError("the current bar length is degenerate")

    direction = current_chord / current_length
    strain = (current_length - initial_length) / initial_length
    response = material.integrate(float(strain), committed_state)
    stress = _finite_scalar(response.stress_mpa, name="material stress_mpa")
    tangent_modulus = _finite_scalar(
        response.consistent_tangent_mpa,
        name="material consistent_tangent_mpa",
    )

    axial_force = stress * area * MPA_M2_TO_KN
    direction_projector = np.outer(direction, direction)
    free_material_tangent = (
        tangent_modulus
        * area
        * MPA_M2_TO_KN
        / initial_length
        * direction_projector
    )
    free_geometric_tangent = (
        axial_force
        / current_length
        * (np.eye(2, dtype=np.float64) - direction_projector)
    )
    free_consistent_tangent = free_material_tangent + free_geometric_tangent
    free_internal_force = axial_force * direction

    internal_force = np.concatenate((-free_internal_force, free_internal_force))
    material_tangent = np.block(
        [
            [free_material_tangent, -free_material_tangent],
            [-free_material_tangent, free_material_tangent],
        ]
    )
    geometric_tangent = np.block(
        [
            [free_geometric_tangent, -free_geometric_tangent],
            [-free_geometric_tangent, free_geometric_tangent],
        ]
    )
    consistent_tangent = material_tangent + geometric_tangent

    return CorotationalTruss2DResponse(
        element_id=normalized_id,
        initial_length_m=initial_length,
        current_length_m=current_length,
        current_direction=_immutable(direction),
        engineering_strain=float(strain),
        axial_force_kn=float(axial_force),
        internal_force_global_kn=_immutable(internal_force),
        material_tangent_global_kn_per_m=_immutable(material_tangent),
        geometric_tangent_global_kn_per_m=_immutable(geometric_tangent),
        consistent_tangent_global_kn_per_m=_immutable(consistent_tangent),
        material_response=response,
    )


def corotational_truss2d_fixed_base_response(
    *,
    element_id: str,
    base_coordinate_m: Any,
    initial_free_coordinate_m: Any,
    free_displacement_m: Any,
    area_m2: float,
    material: StatefulUniaxialMaterial,
    committed_state: Any,
) -> CorotationalTruss2DResponse:
    """Compatibility helper for a fixed node-i and a translated node-j."""

    return corotational_truss2d_response(
        element_id=element_id,
        node_i_coordinate_m=base_coordinate_m,
        node_j_coordinate_m=initial_free_coordinate_m,
        node_i_displacement_m=(0.0, 0.0),
        node_j_displacement_m=free_displacement_m,
        area_m2=area_m2,
        material=material,
        committed_state=committed_state,
    )
