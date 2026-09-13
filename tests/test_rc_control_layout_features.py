"""Pre-solve descriptor boundaries, not cross-layout prediction evidence."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    control_candidate_features,
)
from structural_analysis.benchmark.rc_control_layout_features import (
    LAYOUT_FEATURE_NAMES,
    control_layout_candidate_features,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def raw_model():
    return json.loads(
        Path(
            "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ).read_bytes()
    )


def describe(raw, request=None):
    model = load_neutral_json_bytes(json.dumps(raw).encode())
    return control_layout_candidate_features(
        model,
        request
        or BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, 1e-5), allow_reversals=True, maximum_reversals=1
        ),
    )


def test_layout_is_encoded_without_changing_old_policy_context():
    original = raw_model()
    changed = deepcopy(original)
    changed["nodes"][-1]["coordinates"][1] *= 1.2
    a, b = describe(original), describe(changed)
    assert a["context_hash"] == b["context_hash"]
    assert a["values"] != b["values"]
    assert a["geometry_shape_screen"] != b["geometry_shape_screen"]
    assert a["physical_model_identity"] != b["physical_model_identity"]
    assert len(a["values"]) == len(LAYOUT_FEATURE_NAMES)
    request = BoundedRCFiberDirectControlRequest(
        7, (-1e-5, -2e-5, 1e-5), allow_reversals=True, maximum_reversals=1
    )
    models = [
        load_neutral_json_bytes(json.dumps(raw).encode()) for raw in (original, changed)
    ]
    assert (
        control_candidate_features(models[0], request)[1]
        != control_candidate_features(models[1], request)[1]
    )
    assert a["existing_candidate_policy_compatible"] is False


def test_translation_preserves_descriptors_and_geometry_group():
    original = raw_model()
    changed = deepcopy(original)
    for row in changed["nodes"]:
        row["coordinates"][0] += 10
        row["coordinates"][1] -= 20
    a, b = describe(original), describe(changed)
    assert a["values"] == b["values"]
    assert a["context_hash"] == b["context_hash"]
    assert a["geometry_shape_screen"] == b["geometry_shape_screen"]
    assert a["same_context_is_independent_geometry"] is False


def test_changed_history_is_still_a_different_context():
    req = BoundedRCFiberDirectControlRequest(
        7, (-1e-5, -2e-5, 1e-5), allow_reversals=True, maximum_reversals=1
    )
    a = describe(raw_model(), req)
    b = describe(raw_model(), replace(req, targets_m=(-1e-5, -2e-5, 1.1e-5)))
    assert a["values"] == b["values"]
    assert a["context_hash"] != b["context_hash"]


def test_section_changes_are_features_not_fixed_context():
    raw = raw_model()
    changed = deepcopy(raw)
    changed["sections"][0]["width_m"] *= 1.1
    a, b = describe(raw), describe(changed)
    assert a["context_hash"] == b["context_hash"]
    assert a["values"] != b["values"]


def test_rejects_untyped_request():
    with pytest.raises(ValueError, match="exact bounded"):
        control_layout_candidate_features(
            load_neutral_json_bytes(json.dumps(raw_model()).encode()), {}
        )


@pytest.mark.parametrize("change", ["material", "support", "load", "orientation"])
def test_fixed_physical_conditions_cannot_share_a_layout_context(change):
    original = raw_model()
    changed = deepcopy(original)
    if change == "material":
        changed["materials"][0]["yield_stress_mpa"] *= 1.1
    if change == "support":
        changed["supports"].append({"node": "N2", "dofs": ["UX"]})
    if change == "load":
        changed["loads"][0]["components"]["FY"] *= 1.1
    if change == "orientation":
        changed["elements"][0]["nodes"].reverse()
    if change == "support":
        with pytest.raises(ValueError, match="supported public RC profile"):
            describe(changed)
    else:
        assert describe(original)["context_hash"] != describe(changed)["context_hash"]


def test_geometry_derived_rotation_scale_is_explicitly_encoded():
    raw = raw_model()
    changed = deepcopy(raw)
    changed["nodes"][1]["coordinates"] = [3.0, 0.0, 0.0]
    changed["nodes"][2]["coordinates"] = [3.0, 2.5, 0.0]
    a, b = describe(raw), describe(changed)
    index = LAYOUT_FEATURE_NAMES.index("rotation_coordinate_scale_m")
    assert a["values"][index] == 2.0
    assert b["values"][index] == 3.0
    assert a["context_hash"] == b["context_hash"]
