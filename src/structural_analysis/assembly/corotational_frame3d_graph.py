"""Bounded larger-graph contract for the native-sparse 3D frame path.

This model deliberately shares the immutable member contract used by the
small dense reference, but it does not call or alter that reference model.  Its
larger limits are available only to the experimental native-sparse solver.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


COROTATIONAL_FRAME3D_GRAPH_PROFILE = (
    "bounded_native_sparse_corotational_frame3d_graph.v1"
)
COROTATIONAL_FRAME3D_GRAPH_CLAIM_BOUNDARY = (
    "Experimental connected 3D frame graph contract bounded to 128 nodes, "
    "256 members, and 768 free equations. It is consumed only by the native "
    "sparse candidate and has no release or external-validation authority."
)
COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_NODES = 128
COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_MEMBERS = 256
COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS = 768


@dataclass(frozen=True)
class CorotationalFrame3DGraphModel:
    """Connected, deterministic, larger 3D graph for native sparse assembly."""

    node_coordinates_m: tuple[tuple[float, float, float], ...]
    members: tuple[CorotationalFrame3DMember, ...]
    restrained_dofs: tuple[int, ...]
    reference_load_kn: tuple[float, ...]
    model_id: str = "bounded_native_sparse_corotational_frame3d_graph"

    def __post_init__(self) -> None:
        coordinates = tuple(
            tuple(_finite(value, f"node_coordinates_m[{index}]") for value in row)
            for index, row in enumerate(self.node_coordinates_m)
        )
        if not 2 <= len(coordinates) <= COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_NODES:
            raise ValueError(
                f"node count must be in [2, {COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_NODES}]"
            )
        if any(len(row) != 3 for row in coordinates):
            raise ValueError("every node coordinate must contain three values")
        object.__setattr__(self, "node_coordinates_m", coordinates)

        members = tuple(self.members)
        if not 1 <= len(members) <= COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_MEMBERS:
            raise ValueError(
                "member count must be in [1, "
                f"{COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_MEMBERS}]"
            )
        if any(type(member) is not CorotationalFrame3DMember for member in members):
            raise ValueError(
                "members must contain exact CorotationalFrame3DMember rows"
            )
        identifiers = tuple(member.member_id for member in members)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("member_id values must be unique")
        endpoint_pairs: set[tuple[int, int]] = set()
        for member in members:
            if min(member.node_i, member.node_j) < 0 or max(
                member.node_i, member.node_j
            ) >= len(coordinates):
                raise ValueError(f"member {member.member_id} endpoint is out of range")
            pair = (
                min(member.node_i, member.node_j),
                max(member.node_i, member.node_j),
            )
            if pair in endpoint_pairs:
                raise ValueError("parallel or duplicate members are outside v1")
            endpoint_pairs.add(pair)
            chord = np.subtract(coordinates[member.node_j], coordinates[member.node_i])
            if float(np.linalg.norm(chord)) <= 1.0e-12:
                raise ValueError(f"member {member.member_id} has zero length")
        _validate_connected_graph(len(coordinates), members)
        object.__setattr__(self, "members", members)

        total_dofs = 6 * len(coordinates)
        restrained = tuple(self.restrained_dofs)
        if any(type(value) is not int for value in restrained):
            raise ValueError("restrained_dofs must contain integers")
        if tuple(sorted(set(restrained))) != restrained:
            raise ValueError("restrained_dofs must be sorted and unique")
        if not restrained or min(restrained) < 0 or max(restrained) >= total_dofs:
            raise ValueError("restrained_dofs must reference at least one valid DOF")
        free_count = total_dofs - len(restrained)
        if not 1 <= free_count <= COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS:
            raise ValueError(
                "free equation count must be in [1, "
                f"{COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS}]"
            )
        object.__setattr__(self, "restrained_dofs", restrained)

        loads = tuple(
            _finite(value, f"reference_load_kn[{index}]")
            for index, value in enumerate(self.reference_load_kn)
        )
        if len(loads) != total_dofs:
            raise ValueError(f"reference_load_kn must contain {total_dofs} values")
        if not any(value != 0.0 for value in loads):
            raise ValueError("reference_load_kn must contain a nonzero load")
        object.__setattr__(self, "reference_load_kn", loads)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")

    @property
    def total_dofs(self) -> int:
        return 6 * len(self.node_coordinates_m)

    @property
    def free_dofs(self) -> tuple[int, ...]:
        restrained = set(self.restrained_dofs)
        return tuple(
            index for index in range(self.total_dofs) if index not in restrained
        )

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": COROTATIONAL_FRAME3D_GRAPH_PROFILE,
            "model_id": self.model_id,
            "node_coordinates_m": [list(row) for row in self.node_coordinates_m],
            "members": [member.to_manifest() for member in self.members],
            "restrained_dofs": list(self.restrained_dofs),
            "reference_load_kn": list(self.reference_load_kn),
            "limits": {
                "maximum_nodes": COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_NODES,
                "maximum_members": COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_MEMBERS,
                "maximum_free_equations": (
                    COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS
                ),
            },
            "claim_boundary": COROTATIONAL_FRAME3D_GRAPH_CLAIM_BOUNDARY,
        }


def _validate_connected_graph(
    node_count: int,
    members: tuple[CorotationalFrame3DMember, ...],
) -> None:
    adjacency: list[set[int]] = [set() for _ in range(node_count)]
    for member in members:
        adjacency[member.node_i].add(member.node_j)
        adjacency[member.node_j].add(member.node_i)
    visited = {0}
    frontier = [0]
    while frontier:
        node = frontier.pop()
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    if len(visited) != node_count:
        raise ValueError("frame3d graph must be connected and include every node")


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


__all__ = [
    "COROTATIONAL_FRAME3D_GRAPH_CLAIM_BOUNDARY",
    "COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_FREE_EQUATIONS",
    "COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_MEMBERS",
    "COROTATIONAL_FRAME3D_GRAPH_MAXIMUM_NODES",
    "COROTATIONAL_FRAME3D_GRAPH_PROFILE",
    "CorotationalFrame3DGraphModel",
]
