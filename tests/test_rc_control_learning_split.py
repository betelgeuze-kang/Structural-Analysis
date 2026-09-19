"""Geometry transforms and monotone resampling cannot manufacture held-out groups."""

import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_learning import (
    RCControlLearningCase,
    run_rc_control_learning_study,
)
from structural_analysis.benchmark.rc_control_learning_split import (
    control_history_turning_points,
    geometry_shape_signature,
    validate_control_learning_split_shapes,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def make(
    tmp_path,
    name,
    split,
    *,
    transform=None,
    lengths=(2.0, 1.5),
    targets=(-0.01, -0.02, 0.01, 0.02, 0.0, -0.02),
    subdivide=False,
    midpoint_offset=0.0,
):
    model = json.loads(
        Path(
            "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ).read_bytes()
    )
    for node in model["nodes"]:
        if node["id"] == "N2":
            node["coordinates"] = [lengths[0], 0.0, 0.0]
        if node["id"] == "N3":
            node["coordinates"] = [lengths[0], lengths[1], 0.0]
        if transform:
            node["coordinates"] = transform(np.array(node["coordinates"])).tolist()
    if subdivide:
        midpoint = (
            np.array(model["nodes"][0]["coordinates"])
            + np.array(model["nodes"][1]["coordinates"])
        ) / 2
        midpoint[1] += midpoint_offset
        model["nodes"].append({"id": "midpoint", "coordinates": midpoint.tolist()})
        original = model["elements"][0]
        endpoint = original["nodes"][1]
        original["nodes"][1] = "midpoint"
        model["elements"].append(
            {**original, "id": "split-member", "nodes": ["midpoint", endpoint]}
        )
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(model))
    return RCControlLearningCase(
        name,
        name,
        name,
        name,
        split,
        load_neutral_json(path),
        BoundedRCFiberDirectControlRequest(
            7, tuple(targets), allow_reversals=True, maximum_reversals=2
        ),
    )


@pytest.mark.parametrize(
    "transform",
    [
        lambda x: x + [10.0, -8.0, 0.0],
        lambda x: x * 2,
        lambda x: x * [-1.0, 1.0, 1.0],
        lambda x: np.array([[0.6, -0.8, 0.0], [0.8, 0.6, 0.0], [0.0, 0.0, 1.0]]) @ x,
    ],
)
def test_transformed_and_scaled_geometry_groups_are_not_new_holdout(
    tmp_path, transform
):
    a = make(tmp_path, "a", "train")
    b = make(
        tmp_path,
        "b",
        "holdout",
        transform=transform,
        targets=(-0.02, -0.03, 0.01, 0.02, -0.01, -0.025),
    )
    with pytest.raises(ValueError, match="transformed_or_scaled_geometry_shape"):
        validate_control_learning_split_shapes([a, b])
    with pytest.raises(ValueError, match="split_leakage"):
        run_rc_control_learning_study(
            [a, b], source_revision="a" * 40, output_directory=tmp_path / "study"
        )
    assert not (tmp_path / "study").exists()


@pytest.mark.parametrize(
    "targets",
    [
        (-0.02, 0.02, -0.02),
        (-0.005, -0.01, -0.015, -0.02, 0.0, 0.02, 0.0, -0.01, -0.02),
        (-0.01, 0.01, -0.01),
        (0.01, -0.01, 0.01),
        (-0.02, 0.02),
        (-0.02, 0.005),
        (-0.005, -0.02, -0.012),
    ],
)
def test_same_turning_history_sampling_scale_sign_and_prefix_are_grouped(
    tmp_path, targets
):
    a = make(tmp_path, "a", "train")
    b = make(tmp_path, "b", "holdout", lengths=(2.5, 2.0), targets=targets)
    with pytest.raises(ValueError, match="resampled_control_history_or_prefix"):
        validate_control_learning_split_shapes([a, b])
    with pytest.raises(ValueError, match="split_leakage"):
        run_rc_control_learning_study(
            [a, b], source_revision="a" * 40, output_directory=tmp_path / "study"
        )
    assert not (tmp_path / "study").exists()


def test_observation_shapes_remain_distinct_but_not_independent_provenance(tmp_path):
    cases = [
        make(tmp_path, "a", "train"),
        make(tmp_path, "b", "train", lengths=(3.0, 2.5)),
        make(
            tmp_path,
            "v",
            "validation",
            lengths=(2.5, 2.0),
            targets=(-0.018, 0.016, -0.014),
        ),
        make(
            tmp_path, "h", "holdout", lengths=(6.0, 4.7), targets=(-0.014, 0.022, -0.01)
        ),
    ]
    result = validate_control_learning_split_shapes(cases)
    assert len(result["cases"]) == 4
    assert result["independent_provenance"] is False
    assert result["geometry_screen_is_physical_equivalence_test"] is False


def test_identical_shapes_are_allowed_inside_one_training_split(tmp_path):
    assert (
        len(
            validate_control_learning_split_shapes(
                [make(tmp_path, "a", "train"), make(tmp_path, "b", "train")]
            )["cases"]
        )
        == 2
    )


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_collinear_member_subdivision_cannot_create_a_new_geometry_split(
    tmp_path, scale
):
    a = make(tmp_path, "original", "train")
    b = make(
        tmp_path,
        "remeshed",
        "holdout",
        subdivide=True,
        transform=lambda x: scale * x + [8.0, -3.0, 0.0],
        targets=(-0.018, 0.016, -0.014),
    )
    with pytest.raises(ValueError, match="geometry_shape"):
        validate_control_learning_split_shapes([a, b])
    with pytest.raises(ValueError, match="split_leakage"):
        run_rc_control_learning_study(
            [a, b], source_revision="a" * 40, output_directory=tmp_path / "study"
        )
    assert not (tmp_path / "study").exists()


@pytest.mark.parametrize("offset,supported", [(0.1, False), (0.0, True)])
def test_bent_or_supported_midpoint_is_not_collapsed(
    tmp_path, monkeypatch, offset, supported
):
    case = make(
        tmp_path,
        "retained-node",
        "train",
        subdivide=True,
        midpoint_offset=offset,
    )
    if supported:
        # Test restraint preservation in the grouping algorithm only; the public
        # compiler does not admit an added interior roller support in this case.
        from structural_analysis.benchmark import rc_control_learning_split as split

        payload = split.fiber_frame_physical_model_payload(case.model)
        midpoint = payload["node_coordinates_m"].index([1.0, 0.0])
        payload["fixed_global_dofs"].append(3 * midpoint + 1)
        monkeypatch.setattr(
            split, "fiber_frame_physical_model_payload", lambda _: payload
        )
    signature = geometry_shape_signature(case.model)
    assert signature["node_count"] == 4
    assert signature["collinear_reduced_shape"]["node_count"] == 4


@pytest.mark.parametrize(
    "targets", [(), (0.0,), (-1.0, -1.0), (True,), (-1.0, float("nan"))]
)
def test_invalid_histories_do_not_acquire_a_shape_identity(targets):
    with pytest.raises(ValueError):
        control_history_turning_points(targets)


def test_connected_training_groups_exclude_transitive_aliases(tmp_path):
    from structural_analysis.benchmark.rc_control_learning_split import (
        control_training_exclusion_groups,
    )

    a = make(tmp_path, "a", "train")
    b = make(
        tmp_path, "b", "train", lengths=(2.5, 2.0), targets=(-0.018, 0.016, -0.014)
    )
    b = RCControlLearningCase(
        b.case_id,
        a.project_id,
        b.geometry_family_id,
        b.load_history_id,
        b.split,
        b.model,
        b.request,
    )
    c = make(
        tmp_path, "c", "train", lengths=(5.0, 4.0), targets=(-0.012, 0.020, -0.006)
    )
    d = make(
        tmp_path, "d", "train", lengths=(4.0, 3.1), targets=(-0.022, 0.015, -0.013)
    )
    evaluation = RCControlLearningCase(
        "held-out", "held-out", "held-out", "held-out", "holdout", d.model, d.request
    )
    result = control_training_exclusion_groups([d, c, b, a, evaluation])
    assert result["groups"] == [["a", "b", "c"], ["d"]]
    assert result["independent_provenance"] is False
    assert result == control_training_exclusion_groups([a, b, c, d])
    assert {tuple(c["case_ids"]): c["reasons"] for c in result["connections"]} == {
        ("a", "b"): ["project_id"],
        ("b", "c"): ["geometry_shape"],
    }


def test_connected_training_groups_join_resampled_history_even_with_new_ids(tmp_path):
    from structural_analysis.benchmark.rc_control_learning_split import (
        control_training_exclusion_groups,
    )

    a = make(tmp_path, "a", "train")
    b = make(tmp_path, "b", "train", lengths=(3, 2.4), targets=(-0.02, 0.02, -0.02))
    result = control_training_exclusion_groups([a, b])
    assert result["groups"] == [["a", "b"]]
    assert result["connections"][0]["reasons"] == ["history_shape_or_prefix"]


def test_original_group_audit_pins_protocol_and_original_input_bytes(tmp_path):
    import hashlib
    from scripts.audit_rc_runtime_training_groups import audit

    cases = [
        make(tmp_path, "a", "train"),
        make(tmp_path, "b", "train", lengths=(3, 2.4)),
    ]
    root = tmp_path / "packet"
    (root / "inputs").mkdir(parents=True)
    refs, records = [], []

    def save(name, value):
        raw = json.dumps(value).encode()
        (root / name).write_bytes(raw)
        refs.append(
            {
                "destination": name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    for c in cases:
        save(
            f"inputs/{c.case_id}-model.json",
            json.loads((tmp_path / f"{c.case_id}.json").read_bytes()),
        )
        save(f"inputs/{c.case_id}-request.json", c.request.to_dict())
        records.append(
            {
                k: getattr(c, k)
                for k in (
                    "case_id",
                    "project_id",
                    "geometry_family_id",
                    "load_history_id",
                    "split",
                )
            }
            | {
                "model_path": f"{c.case_id}-model.json",
                "request_path": f"{c.case_id}-request.json",
            }
        )
    save("original-plan.json", {"cases": records})
    raw = json.dumps({"source_revision": "a" * 40, "original_files": refs}).encode()
    (root / "protocol.json").write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    result = audit(root, pin)
    assert result["group_screen"]["groups"] == [["a", "b"]]
    assert result["group_withholding_can_leave_training_data"] is False
    assert result["fit_count"] == result["solver_call_count"] == 0
    with pytest.raises(ValueError, match="protocol mismatch"):
        audit(root, "0" * 64)
    with (root / "inputs/a-model.json").open("ab") as out:
        out.write(b" ")
    with pytest.raises(ValueError, match="input mismatch"):
        audit(root, pin)
