"""Conservative cyclic learning groups beyond entity names and sample density.

These screens deliberately prefer keeping near-duplicate shapes in one split.
They are not physical equivalence tests or independent-project authentication.
"""

from __future__ import annotations

import math

import numpy as np

from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_payload,
)


def control_history_turning_points(targets):
    """Ignore monotone resampling; retain ordered reversals and the final target."""
    turning = []
    previous = 0.0
    direction = None
    for value in targets:
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value == previous
        ):
            raise ValueError("finite distinct control targets required")
        next_direction = 1 if value > previous else -1
        if direction is not None and next_direction != direction:
            turning.append(previous)
        previous = float(value)
        direction = next_direction
    if direction is None:
        raise ValueError("nonempty control history required")
    turning.append(previous)
    scale = turning[0]
    normalized = tuple(x / scale for x in turning)
    if not all(math.isfinite(x) for x in normalized):
        raise ValueError("finite normalized turning points required")
    return normalized


def geometry_shape_signature(model):
    """Sorted normalized pair distances plus coarse connectivity; no solver calls.

    Congruent, mirrored and uniformly scaled coordinate sets group together even
    when entity order, orientation or origin changes. Different homometric graphs
    can also group together: false-positive split rejection is conservative.
    """
    payload = fiber_frame_physical_model_payload(model)
    coordinates = np.asarray(payload["node_coordinates_m"], dtype=float)
    edges = [tuple(member["nodes"]) for member in payload["members"]]
    signature = _distance_signature(
        coordinates, edges, len(payload["fixed_global_dofs"])
    )
    protected = {dof // 3 for dof in payload["fixed_global_dofs"]}
    active = set(range(len(coordinates)))
    while True:
        for node in sorted(active - protected):
            incident = [edge for edge in edges if node in edge]
            if len(incident) != 2:
                continue
            neighbors = [edge[1] if edge[0] == node else edge[0] for edge in incident]
            if neighbors[0] == neighbors[1]:
                continue
            left, right = (coordinates[n] - coordinates[node] for n in neighbors)
            lengths = [float(np.linalg.norm(v)) for v in (left, right)]
            if not all(math.isfinite(v) and v > 0 for v in lengths):
                continue
            # Opposite unit directions identify only an interior straight node.
            if np.linalg.norm(left / lengths[0] + right / lengths[1]) > 1e-10:
                continue
            for edge in incident:
                edges.remove(edge)
            edges.append(tuple(neighbors))
            active.remove(node)
            break
        else:
            break
    ordered = sorted(active)
    index = {node: i for i, node in enumerate(ordered)}
    signature["collinear_reduced_shape"] = _distance_signature(
        coordinates[ordered],
        [(index[a], index[b]) for a, b in edges],
        len(payload["fixed_global_dofs"]),
    )
    return signature


def _distance_signature(coordinates, edges, restraint_count):
    distances = sorted(
        float(np.linalg.norm(a - b))
        for i, a in enumerate(coordinates)
        for b in coordinates[i + 1 :]
    )
    diameter = max(distances, default=0.0)
    if (
        not math.isfinite(diameter)
        or diameter <= 0
        or not all(math.isfinite(d) for d in distances)
    ):
        raise ValueError("finite nondegenerate model geometry required")
    degrees = [0] * len(coordinates)
    for edge in edges:
        for node in edge:
            degrees[node] += 1
    return {
        "node_count": len(coordinates),
        "member_count": len(edges),
        "sorted_degrees": sorted(degrees),
        "restraint_count": restraint_count,
        "normalized_pair_distances": [d / diameter for d in distances],
    }


def geometry_shapes_overlap(left, right):
    """Shared conservative shape comparison for explicit split contracts."""
    if "collinear_reduced_shape" in left and "collinear_reduced_shape" in right:
        if geometry_shapes_overlap(
            left["collinear_reduced_shape"], right["collinear_reduced_shape"]
        ):
            return True
    topology = all(
        left[k] == right[k]
        for k in ("node_count", "member_count", "sorted_degrees", "restraint_count")
    )
    return bool(
        topology
        and np.allclose(
            left["normalized_pair_distances"],
            right["normalized_pair_distances"],
            rtol=1e-10,
            atol=1e-12,
        )
    )


def _history_prefix(shorter, longer):
    if len(shorter) > len(longer):
        return False
    if len(shorter) == 1:
        return True
    if not np.allclose(
        shorter[:-1], longer[: len(shorter) - 1], rtol=1e-10, atol=1e-12
    ):
        return False
    # A truncated case can stop inside a monotone leg, before its next reversal.
    start, stop = longer[len(shorter) - 2 : len(shorter)]
    endpoint = shorter[-1]
    tolerance = 1e-12 + 1e-10 * max(abs(start), abs(stop), abs(endpoint))
    return min(start, stop) - tolerance <= endpoint <= max(start, stop) + tolerance


def validate_control_learning_split_shapes(cases):
    """Reject transformed geometry or resampled history aliases across splits."""
    records = []
    for case in cases:
        geometry = geometry_shape_signature(case.model)
        turning = control_history_turning_points(case.request.targets_m)
        for previous in records:
            if previous["split"] == case.split:
                continue
            if geometry_shapes_overlap(previous["geometry"], geometry):
                raise ValueError("split_leakage: transformed_or_scaled_geometry_shape")
            history = previous["normalized_turning_points"]
            if _history_prefix(history, turning) or _history_prefix(turning, history):
                raise ValueError("split_leakage: resampled_control_history_or_prefix")
        records.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "geometry": geometry,
                "normalized_turning_points": list(turning),
            }
        )
    return {
        "schema_version": "rc-control-learning-conservative-shape-screen.v2",
        "cases": records,
        "comparison_relative_tolerance": 1e-10,
        "comparison_absolute_tolerance": 1e-12,
        "tolerances_apply_only_to_split_screen_not_physical_acceptance": True,
        "independent_provenance": False,
        "geometry_screen_is_physical_equivalence_test": False,
        "unrestrained_collinear_subdivision_screened": True,
        "collinear_unit_direction_tolerance": 1e-10,
    }
