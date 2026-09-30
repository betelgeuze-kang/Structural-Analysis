"""Pre-solve descriptor boundaries, not cross-layout prediction evidence."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
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


def test_outer_area_overrides_remain_bound_in_layout_context():
    payload = raw_model()
    before = describe(payload)
    payload["sections"][0].update(top_bar_area_m2=0.00005, bottom_bar_area_m2=0.0002)
    unequal = describe(payload)
    payload["sections"][0].update(top_bar_area_m2=0.0002, bottom_bar_area_m2=0.00005)
    swapped = describe(payload)
    assert len({row["context_hash"] for row in (before, unequal, swapped)}) == 3
    assert (
        len({row["physical_model_identity"] for row in (before, unequal, swapped)}) == 3
    )


def test_two_fixed_portal_layout_features_keep_explicit_request_context():
    root = Path("examples/research/rc_internal_portal_20mm")
    original = json.loads((root / "original-model.json").read_bytes())
    narrower = deepcopy(original)
    narrower["sections"][0]["width_m"] = 0.36
    request = decode_bounded_rc_fiber_direct_control_request(
        (root / "experimental-two-fixed-endpoints-request.json").read_bytes()
    )
    baseline = describe(original, request)
    changed = describe(narrower, request)
    assert baseline["context_hash"] == changed["context_hash"]
    assert baseline["values"] != changed["values"]
    assert baseline["physical_model_identity"] != changed["physical_model_identity"]
    with pytest.raises(ValueError, match="supported public RC profile"):
        describe(original, replace(request, experimental_two_fixed_endpoints=False))


def test_pin_roller_layout_features_bind_full_request_and_declared_control_node():
    from tests.test_rc_fiber_pin_roller_beam_public import _model, _request

    original = _model().canonical_payload()
    request = _request()
    first = describe(original, request)
    shorter = deepcopy(original)
    for node in shorter["nodes"]:
        node["coordinates"][0] *= 0.9
    second = describe(shorter, request)
    assert first["context_hash"] == second["context_hash"]
    assert first["values"] != second["values"]
    assert first["physical_model_identity"] != second["physical_model_identity"]
    assert first["geometry_shape_screen"]["restraint_count"] == 3
    assert first["physical_result_authority"] is False
    assert first["existing_candidate_policy_compatible"] is False
    # Canonical physical topology stays fixed, but DOF 10 now names N3, not N4.
    shorter["nodes"][2], shorter["nodes"][3] = shorter["nodes"][3], shorter["nodes"][2]
    reordered = describe(shorter, request)
    assert reordered["values"] == second["values"]
    assert reordered["physical_model_identity"] == second["physical_model_identity"]
    assert reordered["context_hash"] != second["context_hash"]
    preload = replace(request, constant_nodal_loads=(("N4", 0.0, -0.01, 0.0),))
    assert describe(original, preload)["context_hash"] != first["context_hash"]
    with pytest.raises(ValueError, match="preload node is outside"):
        describe(
            original,
            replace(request, constant_nodal_loads=(("missing", 0.0, -0.01, 0.0),)),
        )
    with pytest.raises(ValueError, match="control node is outside"):
        describe(original, replace(request, control_global_dof=21))


@pytest.mark.parametrize(
    "version,expected",
    [
        ("v1", "7cd86af1d9be201da90fa29e56cebac0ab624a0215e74d2b35e3fe2323f9f749"),
        ("v2", "4cdadc06e3597db41c3ddd17cdea0502447995930943afd8b9ca52e3f56278be"),
        ("v3", "241046aebed7847a36522c6fcc1ad4dd7f1a3412837ce60a3919f1d54e77df91"),
    ],
)
def test_legacy_layout_descriptor_original_bytes_stay_exact(version, expected):
    import hashlib
    from structural_analysis.benchmark.rc_control_design import _bytes

    request = BoundedRCFiberDirectControlRequest(
        7, (-1e-5, -2e-5, 1e-5), allow_reversals=True, maximum_reversals=1
    )
    raw = raw_model()
    if version == "v2":
        request = replace(request, constant_nodal_loads=(("N2", 0.0, -0.01, 0.0),))
    elif version == "v3":
        root = Path("examples/research/rc_internal_portal_20mm")
        raw = json.loads((root / "original-model.json").read_bytes())
        request = decode_bounded_rc_fiber_direct_control_request(
            (root / "experimental-two-fixed-endpoints-request.json").read_bytes()
        )
    assert hashlib.sha256(_bytes(describe(raw, request))).hexdigest() == expected
