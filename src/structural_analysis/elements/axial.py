"""Axial 3D truss element calculations for the first deterministic solver slice."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class AxialElementProperties:
    element_id: str
    node_ids: tuple[str, str]
    elastic_modulus: float
    area: float
    length: float
    direction_cosines: tuple[float, float, float]


def axial_element_properties(
    *,
    element_id: str,
    node_ids: tuple[str, str],
    start_coordinates: tuple[float, float, float],
    end_coordinates: tuple[float, float, float],
    elastic_modulus: float,
    area: float,
) -> AxialElementProperties:
    dx = end_coordinates[0] - start_coordinates[0]
    dy = end_coordinates[1] - start_coordinates[1]
    dz = end_coordinates[2] - start_coordinates[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 0.0:
        raise ValueError(f"Element {element_id} has zero length.")
    if elastic_modulus <= 0.0:
        raise ValueError(f"Element {element_id} elastic modulus must be positive.")
    if area <= 0.0:
        raise ValueError(f"Element {element_id} area must be positive.")
    return AxialElementProperties(
        element_id=element_id,
        node_ids=node_ids,
        elastic_modulus=elastic_modulus,
        area=area,
        length=length,
        direction_cosines=(dx / length, dy / length, dz / length),
    )


def axial_global_stiffness(properties: AxialElementProperties) -> np.ndarray:
    lx, ly, lz = properties.direction_cosines
    direction = np.array([lx, ly, lz], dtype=float)
    local = np.outer(direction, direction)
    stiffness = properties.elastic_modulus * properties.area / properties.length
    return stiffness * np.block([[local, -local], [-local, local]])
