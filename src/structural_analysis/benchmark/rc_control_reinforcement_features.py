"""Versioned pre-solve descriptors for varying outer reinforcement areas."""

from dataclasses import asdict
import math

from structural_analysis.ai.fiber_frame_candidate_learning import (
    FEATURE_NAMES,
    _MAX_FEATURE_MEMBERS,
    _SECTION_FEATURE_FIELDS,
    candidate_preanalysis_features,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_payload,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import rc_control_design as study

PROFILE = "rc-control-outer-reinforcement-candidate.v1"
OUTER_FIELDS = ("top_bar_area_m2", "bottom_bar_area_m2")
REINFORCEMENT_FEATURE_NAMES = FEATURE_NAMES + tuple(
    f"member_{i}_effective_{name}"
    for i in range(_MAX_FEATURE_MEMBERS)
    for name in OUTER_FIELDS
)


def control_reinforcement_features(model, request):
    """Bind all non-feature physics and the entire direct-control request."""
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact direct-control request required")
    restored = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    config = PublicRCFiberFrameConfig()
    old_values, _ = candidate_preanalysis_features(model, config)
    context = fiber_frame_physical_model_payload(model)
    sections = [member["section"] for member in context["members"]]
    areas = tuple(
        float(s.get(key, s["bar_area_m2"])) for s in sections for key in OUTER_FIELDS
    )
    values = old_values + areas + (0.0,) * (2 * (_MAX_FEATURE_MEMBERS - len(sections)))
    if len(values) != len(REINFORCEMENT_FEATURE_NAMES) or not all(
        math.isfinite(v) for v in values
    ):
        raise ValueError("finite complete reinforcement features required")
    for section in sections:
        for key in (*_SECTION_FEATURE_FIELDS, *OUTER_FIELDS):
            section.pop(key, None)
    return values, study._sha(
        study._bytes(
            {
                "feature_profile": PROFILE,
                "fixed_analysis_context": context,
                "configuration": asdict(config),
                "control_request": restored.to_dict(),
            }
        )
    )
