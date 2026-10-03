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
    "rotation_coordinate_scale_m",
    *(f"node_{i}_relative_{axis}_m" for i in range(MAX_NODES) for axis in ("x", "y")),
)


def control_layout_candidate_features(model, request):
    """Return descriptors and a new context; do not fit, predict or solve."""
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact bounded direct-control request required")
    request = decode_bounded_rc_fiber_direct_control_request(_bytes(request.to_dict()))
    config = PublicRCFiberFrameConfig()
    section_values, _ = candidate_preanalysis_features(
        model,
        config,
        experimental_two_fixed_endpoints=request.experimental_two_fixed_endpoints,
        experimental_pin_roller_beam=request.experimental_pin_roller_beam,
    )
    physical = fiber_frame_physical_model_payload(
        model,
        experimental_two_fixed_endpoints=request.experimental_two_fixed_endpoints,
        experimental_pin_roller_beam=request.experimental_pin_roller_beam,
    )
    coordinates = physical.pop("node_coordinates_m")
    if not 2 <= len(coordinates) <= MAX_NODES:
        raise ValueError("bounded layout node count required")
    rotation_scale = physical.pop("rotation_coordinate_scale_m")
    anchor = coordinates[0]
    relative = tuple(
        float(row[axis] - anchor[axis]) for row in coordinates for axis in (0, 1)
    )
    values = (
        *section_values,
        float(len(coordinates)),
        float(rotation_scale),
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
    if request.experimental_pin_roller_beam:
        # Global DOFs index the authored node declaration, whereas the physical
        # payload sorts nodes by coordinates. Bind their meaning before allowing
        # different layouts into one context. Legacy contexts stay byte-exact.
        authored = model.nodes
        index, component = divmod(request.control_global_dof, 3)
        if index >= len(authored):
            raise ValueError("pin-roller layout control node is outside the model")
        canonical = {tuple(row): i for i, row in enumerate(coordinates)}
        nodes = {
            row["id"]: canonical[tuple(row["coordinates"][:2])] for row in authored
        }
        try:
            preload = [
                {
                    "canonical_node_index": nodes[node],
                    "FX_kN": fx,
                    "FY_kN": fy,
                    "MZ_kNm": mz,
                }
                for node, fx, fy, mz in request.constant_nodal_loads
            ]
        except KeyError as error:
            raise ValueError(
                "pin-roller layout preload node is outside the model"
            ) from error
        context["canonical_control_request_binding"] = {
            "control_global_dof": 3 * nodes[authored[index]["id"]] + component,
            "constant_nodal_loads": preload,
        }
    return {
        "feature_profile": PROFILE,
        "feature_names": list(LAYOUT_FEATURE_NAMES),
        "values": list(values),
        "context_hash": _sha(_bytes(context)),
        "physical_model_identity": fiber_frame_physical_model_identity(
            model,
            experimental_two_fixed_endpoints=request.experimental_two_fixed_endpoints,
            experimental_pin_roller_beam=request.experimental_pin_roller_beam,
        ),
        "geometry_shape_screen": geometry_shape_signature(
            model,
            experimental_two_fixed_endpoints=request.experimental_two_fixed_endpoints,
            experimental_pin_roller_beam=request.experimental_pin_roller_beam,
        ),
        "same_context_is_independent_geometry": False,
        "existing_candidate_policy_compatible": False,
        "physical_result_authority": False,
    }
