"""Three-node linear membrane/Mindlin shell element in global 6-DOF form."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class ShellTriangleMatrices:
    stiffness_n_per_m: np.ndarray
    area_m2: float
    local_basis: np.ndarray
    membrane_b: np.ndarray
    bending_b: np.ndarray
    shear_b: np.ndarray
    membrane_d_n_per_m: np.ndarray
    bending_d_nm: np.ndarray
    shear_d_n_per_m: np.ndarray


@dataclass(frozen=True)
class ShellTriangleRecovery:
    membrane_strain: tuple[float, float, float]
    membrane_resultant_n_per_m: tuple[float, float, float]
    curvature_per_m: tuple[float, float, float]
    bending_resultant_nm_per_m: tuple[float, float, float]
    transverse_shear_strain: tuple[float, float]
    transverse_shear_resultant_n_per_m: tuple[float, float]
    strain_energy_j: float


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def shell_triangle_matrices(
    points_m: Sequence[Sequence[float]] | np.ndarray,
    *,
    elastic_modulus_pa: float,
    poisson_ratio: float,
    thickness_m: float,
) -> ShellTriangleMatrices:
    points = np.asarray(points_m, dtype=np.float64)
    if points.shape != (3, 3) or not np.all(np.isfinite(points)):
        raise ValueError("points_m must be a finite 3x3 array")
    elastic = _positive(elastic_modulus_pa, "elastic_modulus_pa")
    thickness = _positive(thickness_m, "thickness_m")
    poisson = float(poisson_ratio)
    if not math.isfinite(poisson) or not (-1.0 < poisson < 0.5):
        raise ValueError("poisson_ratio must be in (-1, 0.5)")
    v1 = points[1] - points[0]
    v2 = points[2] - points[0]
    normal = np.cross(v1, v2)
    area2 = float(np.linalg.norm(normal))
    if area2 <= 1.0e-12:
        raise ValueError("shell triangle is degenerate")
    e1 = v1 / np.linalg.norm(v1)
    e3 = normal / area2
    e2 = np.cross(e3, e1)
    basis = np.vstack((e1, e2, e3))
    xy = np.asarray(
        [
            [np.dot(point - points[0], e1), np.dot(point - points[0], e2)]
            for point in points
        ]
    )
    x1, y1 = xy[0]
    x2, y2 = xy[1]
    x3, y3 = xy[2]
    signed_area = 0.5 * ((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
    if abs(signed_area) <= 1.0e-12:
        raise ValueError("shell triangle local area is degenerate")
    area = abs(float(signed_area))
    b = np.asarray([y2 - y3, y3 - y1, y1 - y2]) / (2.0 * signed_area)
    c = np.asarray([x3 - x2, x1 - x3, x2 - x1]) / (2.0 * signed_area)

    membrane_b = np.zeros((3, 6), dtype=np.float64)
    for node in range(3):
        membrane_b[0, 2 * node] = b[node]
        membrane_b[1, 2 * node + 1] = c[node]
        membrane_b[2, 2 * node] = c[node]
        membrane_b[2, 2 * node + 1] = b[node]
    membrane_d = (
        elastic
        * thickness
        / (1.0 - poisson**2)
        * np.asarray(
            [
                [1.0, poisson, 0.0],
                [poisson, 1.0, 0.0],
                [0.0, 0.0, (1.0 - poisson) / 2.0],
            ]
        )
    )
    membrane_local = area * membrane_b.T @ membrane_d @ membrane_b
    membrane_transform = np.zeros((6, 18), dtype=np.float64)
    for node in range(3):
        membrane_transform[2 * node, 6 * node : 6 * node + 3] = e1
        membrane_transform[2 * node + 1, 6 * node : 6 * node + 3] = e2

    bending_b = np.zeros((3, 9), dtype=np.float64)
    shear_b = np.zeros((2, 9), dtype=np.float64)
    for node in range(3):
        w, theta_x, theta_y = 3 * node, 3 * node + 1, 3 * node + 2
        bending_b[0, theta_y] = b[node]
        bending_b[1, theta_x] = -c[node]
        bending_b[2, theta_x] = -b[node]
        bending_b[2, theta_y] = c[node]
        shear_b[0, w] = b[node]
        shear_b[0, theta_y] = -1.0 / 3.0
        shear_b[1, w] = c[node]
        shear_b[1, theta_x] = 1.0 / 3.0
    bending_d = (
        elastic
        * thickness**3
        / (12.0 * (1.0 - poisson**2))
        * np.asarray(
            [
                [1.0, poisson, 0.0],
                [poisson, 1.0, 0.0],
                [0.0, 0.0, (1.0 - poisson) / 2.0],
            ]
        )
    )
    shear_modulus = elastic / (2.0 * (1.0 + poisson))
    shear_d = (5.0 / 6.0) * shear_modulus * thickness * np.eye(2)
    bending_local = area * (
        bending_b.T @ bending_d @ bending_b + shear_b.T @ shear_d @ shear_b
    )
    bending_transform = np.zeros((9, 18), dtype=np.float64)
    for node in range(3):
        bending_transform[3 * node, 6 * node : 6 * node + 3] = e3
        bending_transform[3 * node + 1, 6 * node + 3 : 6 * node + 6] = e1
        bending_transform[3 * node + 2, 6 * node + 3 : 6 * node + 6] = e2
    stiffness = membrane_transform.T @ membrane_local @ membrane_transform
    stiffness += bending_transform.T @ bending_local @ bending_transform
    drill = max(
        float(np.trace(bending_local)) / 9.0 * 1.0e-6,
        elastic * thickness**3 * area * 1.0e-12,
    )
    for node in range(3):
        rotation = slice(6 * node + 3, 6 * node + 6)
        stiffness[rotation, rotation] += drill * np.outer(e3, e3)
    stiffness = 0.5 * (stiffness + stiffness.T)
    for array in (
        stiffness,
        basis,
        membrane_b,
        bending_b,
        shear_b,
        membrane_d,
        bending_d,
        shear_d,
    ):
        array.setflags(write=False)
    return ShellTriangleMatrices(
        stiffness,
        area,
        basis,
        membrane_b,
        bending_b,
        shear_b,
        membrane_d,
        bending_d,
        shear_d,
    )


def recover_shell_triangle(
    matrices: ShellTriangleMatrices,
    displacement_global: Sequence[float] | np.ndarray,
) -> ShellTriangleRecovery:
    displacement = np.asarray(displacement_global, dtype=np.float64)
    if displacement.shape != (18,) or not np.all(np.isfinite(displacement)):
        raise ValueError("displacement_global must be a finite 18-vector")
    e1, e2, e3 = matrices.local_basis
    membrane_values: list[float] = []
    bending_values: list[float] = []
    for node in range(3):
        translation = displacement[6 * node : 6 * node + 3]
        rotation = displacement[6 * node + 3 : 6 * node + 6]
        membrane_values.extend((float(e1 @ translation), float(e2 @ translation)))
        bending_values.extend(
            (float(e3 @ translation), float(e1 @ rotation), float(e2 @ rotation))
        )
    membrane_strain = matrices.membrane_b @ np.asarray(membrane_values)
    curvature = matrices.bending_b @ np.asarray(bending_values)
    shear_strain = matrices.shear_b @ np.asarray(bending_values)
    membrane_force = matrices.membrane_d_n_per_m @ membrane_strain
    bending_moment = matrices.bending_d_nm @ curvature
    shear_force = matrices.shear_d_n_per_m @ shear_strain
    energy = 0.5 * float(displacement @ matrices.stiffness_n_per_m @ displacement)
    return ShellTriangleRecovery(
        tuple(map(float, membrane_strain)),
        tuple(map(float, membrane_force)),
        tuple(map(float, curvature)),
        tuple(map(float, bending_moment)),
        tuple(map(float, shear_strain)),
        tuple(map(float, shear_force)),
        energy,
    )


__all__ = [
    "ShellTriangleMatrices",
    "ShellTriangleRecovery",
    "recover_shell_triangle",
    "shell_triangle_matrices",
]
