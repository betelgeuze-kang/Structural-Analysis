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
    for member in payload["members"]:
        for node in member["nodes"]:
            degrees[node] += 1
    return {
        "node_count": len(coordinates),
        "member_count": len(payload["members"]),
        "sorted_degrees": sorted(degrees),
        "restraint_count": len(payload["fixed_global_dofs"]),
        "normalized_pair_distances": [d / diameter for d in distances],
    }


def validate_control_learning_split_shapes(cases):
    """Reject transformed geometry or resampled history aliases across splits."""
    records = []
    for case in cases:
        geometry = geometry_shape_signature(case.model)
        turning = control_history_turning_points(case.request.targets_m)
        for previous in records:
            if previous["split"] == case.split:
                continue
            old = previous["geometry"]
            topology = all(
                old[k] == geometry[k]
                for k in [
                    "node_count",
                    "member_count",
                    "sorted_degrees",
                    "restraint_count",
                ]
            )
            if topology and np.allclose(
                old["normalized_pair_distances"],
                geometry["normalized_pair_distances"],
                rtol=1e-10,
                atol=1e-12,
            ):
                raise ValueError("split_leakage: transformed_or_scaled_geometry_shape")
            history = previous["normalized_turning_points"]
            count = min(len(history), len(turning))
            if np.allclose(history[:count], turning[:count], rtol=1e-10, atol=1e-12):
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
        "schema_version": "rc-control-learning-conservative-shape-screen.v1",
        "cases": records,
        "comparison_relative_tolerance": 1e-10,
        "comparison_absolute_tolerance": 1e-12,
        "tolerances_apply_only_to_split_screen_not_physical_acceptance": True,
        "independent_provenance": False,
        "geometry_screen_is_physical_equivalence_test": False,
    }
