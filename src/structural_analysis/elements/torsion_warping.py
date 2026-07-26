"""Two-node Vlasov torsion/warping energy reference with explicit warping DOFs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


TORSION_WARPING_PROFILE = "vlasov_hermite_twist_gradient_2node.v1"
TORSION_WARPING_DOF_ORDER = (
    "twist_i_rad",
    "twist_gradient_i_rad_per_m",
    "twist_j_rad",
    "twist_gradient_j_rad_per_m",
)
TORSION_WARPING_CLAIM_BOUNDARY = (
    "Linear prismatic 4-DOF twist/gradient kernel; not assembled into the "
    "12-DOF frame, open-section stress recovery, or nonlinear frame path."
)


@dataclass(frozen=True)
class TorsionWarpingProperties:
    shear_modulus_kn_per_m2: float
    torsional_constant_m4: float
    elastic_modulus_kn_per_m2: float
    warping_constant_m6: float

    def __post_init__(self) -> None:
        for name in (
            "shear_modulus_kn_per_m2",
            "torsional_constant_m4",
            "elastic_modulus_kn_per_m2",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        object.__setattr__(
            self,
            "warping_constant_m6",
            _nonnegative(self.warping_constant_m6, "warping_constant_m6"),
        )


@dataclass(frozen=True)
class TorsionWarpingResponse:
    strain_energy_kn_m: float
    generalized_forces: np.ndarray
    tangent: np.ndarray
    dof_order: tuple[str, ...] = TORSION_WARPING_DOF_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "generalized_forces", _immutable(self.generalized_forces, (4,))
        )
        object.__setattr__(self, "tangent", _immutable(self.tangent, (4, 4)))


def local_torsion_warping_stiffness(
    properties: TorsionWarpingProperties,
    length_m: float,
) -> np.ndarray:
    """Integrate ``GJ theta'^2 + E Cw theta''^2`` with cubic Hermite twist."""

    length = _positive(length_m, "length_m")
    stiffness = np.zeros((4, 4), dtype=np.float64)
    # Four-point Gauss-Legendre exactly integrates the polynomial products and
    # keeps one implementation for both Saint-Venant and warping terms.
    points, weights = np.polynomial.legendre.leggauss(4)
    for point, weight in zip(points, weights, strict=True):
        xi = 0.5 * (float(point) + 1.0)
        jacobian = 0.5 * length
        first = _hermite_first_derivative(xi, length)
        second = _hermite_second_derivative(xi, length)
        stiffness += (
            weight
            * jacobian
            * (
                properties.shear_modulus_kn_per_m2
                * properties.torsional_constant_m4
                * np.outer(first, first)
                + properties.elastic_modulus_kn_per_m2
                * properties.warping_constant_m6
                * np.outer(second, second)
            )
        )
    stiffness = 0.5 * (stiffness + stiffness.T)
    stiffness[np.abs(stiffness) < 1.0e-15 * max(np.max(np.abs(stiffness)), 1.0)] = 0.0
    stiffness.setflags(write=False)
    return stiffness


def torsion_warping_response(
    properties: TorsionWarpingProperties,
    length_m: float,
    generalized_deformations: Any,
) -> TorsionWarpingResponse:
    deformation = np.asarray(generalized_deformations, dtype=np.float64)
    if deformation.shape != (4,) or not np.all(np.isfinite(deformation)):
        raise ValueError("generalized_deformations must be a finite four-vector")
    tangent = local_torsion_warping_stiffness(properties, length_m)
    forces = tangent @ deformation
    return TorsionWarpingResponse(
        strain_energy_kn_m=0.5 * float(deformation @ forces),
        generalized_forces=forces,
        tangent=tangent,
    )


def condensed_twist_stiffness(tangent: Any) -> np.ndarray:
    """Statically condense the two twist-gradient DOFs to end twists."""

    matrix = np.asarray(tangent, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError("tangent must be a finite 4x4 matrix")
    retained = np.asarray([0, 2], dtype=np.int64)
    internal = np.asarray([1, 3], dtype=np.int64)
    rr = matrix[np.ix_(retained, retained)]
    ri = matrix[np.ix_(retained, internal)]
    ii = matrix[np.ix_(internal, internal)]
    try:
        condensed = rr - ri @ np.linalg.solve(ii, ri.T)
    except np.linalg.LinAlgError as exc:
        raise ValueError("twist-gradient block cannot be condensed") from exc
    condensed = 0.5 * (condensed + condensed.T)
    condensed.setflags(write=False)
    return condensed


def _hermite_first_derivative(xi: float, length: float) -> np.ndarray:
    return np.asarray(
        [
            (-6.0 * xi + 6.0 * xi**2) / length,
            1.0 - 4.0 * xi + 3.0 * xi**2,
            (6.0 * xi - 6.0 * xi**2) / length,
            -2.0 * xi + 3.0 * xi**2,
        ],
        dtype=np.float64,
    )


def _hermite_second_derivative(xi: float, length: float) -> np.ndarray:
    return np.asarray(
        [
            (-6.0 + 12.0 * xi) / length**2,
            (-4.0 + 6.0 * xi) / length,
            (6.0 - 12.0 * xi) / length**2,
            (-2.0 + 6.0 * xi) / length,
        ],
        dtype=np.float64,
    )


def _immutable(value: Any, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"array must be finite with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _positive(value: Any, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _nonnegative(value: Any, name: str) -> float:
    normalized = _finite(value, name)
    if normalized < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return normalized


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


__all__ = [
    "TORSION_WARPING_CLAIM_BOUNDARY",
    "TORSION_WARPING_DOF_ORDER",
    "TORSION_WARPING_PROFILE",
    "TorsionWarpingProperties",
    "TorsionWarpingResponse",
    "condensed_twist_stiffness",
    "local_torsion_warping_stiffness",
    "torsion_warping_response",
]
