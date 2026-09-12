"""Explicit layout descriptors for future fixed-topology candidate experiments.

This does not relax existing policy contexts or reinterpret old fitted weights.
Control histories/materials/topology remain fixed; only coordinates and the
existing section/bar feature fields may vary within the new context.
"""

from dataclasses import asdict
import math

from structural_analysis.ai.fiber_frame_candidate_learning import (
    FEATURE_NAMES,
    _MAX_FEATURE_MEMBERS,
    _SECTION_FEATURE_FIELDS,
    candidate_preanalysis_features,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_identity,
    fiber_frame_physical_model_payload,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning_split import (
    geometry_shape_signature,
)

PROFILE = "experimental-rc-control-fixed-topology-layout-features.v1"
MAX_NODES = 2 * _MAX_FEATURE_MEMBERS
LAYOUT_FEATURE_NAMES = (
    *FEATURE_NAMES,
    "node_count",
    *(f"node_{i}_relative_{axis}_m" for i in range(MAX_NODES) for axis in ("x", "y")),
)


def control_layout_candidate_features(model, request):
    """Return descriptors and a new context; do not fit, predict or solve."""
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact bounded direct-control request required")
    request = decode_bounded_rc_fiber_direct_control_request(_bytes(request.to_dict()))
    config = PublicRCFiberFrameConfig()
    section_values, _ = candidate_preanalysis_features(model, config)
    physical = fiber_frame_physical_model_payload(model)
    coordinates = physical.pop("node_coordinates_m")
    if not 2 <= len(coordinates) <= MAX_NODES:
        raise ValueError("bounded layout node count required")
    anchor = coordinates[0]
    relative = tuple(
        float(row[axis] - anchor[axis]) for row in coordinates for axis in (0, 1)
    )
    values = (
        *section_values,
        float(len(coordinates)),
        *relative,
        *((0.0,) * (2 * (MAX_NODES - len(coordinates)))),
    )
    if len(values) != len(LAYOUT_FEATURE_NAMES) or not all(
        math.isfinite(x) for x in values
    ):
        raise ValueError("finite complete layout descriptors required")
    physical["node_count"] = len(coordinates)
    for member in physical["members"]:
        for name in _SECTION_FEATURE_FIELDS:
            member["section"].pop(name)
    context = {
        "feature_profile": PROFILE,
        "fixed_topology_and_material_context": physical,
        "configuration": asdict(config),
        "control_request": request.to_dict(),
    }
    return {
        "feature_profile": PROFILE,
        "feature_names": list(LAYOUT_FEATURE_NAMES),
        "values": list(values),
        "context_hash": _sha(_bytes(context)),
        "physical_model_identity": fiber_frame_physical_model_identity(model),
        "geometry_shape_screen": geometry_shape_signature(model),
        "same_context_is_independent_geometry": False,
        "existing_candidate_policy_compatible": False,
        "physical_result_authority": False,
    }
