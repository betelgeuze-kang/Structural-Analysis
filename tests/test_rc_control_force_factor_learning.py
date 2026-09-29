"""The indexed factor learner uses solver/replay labels, including floor failures."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_force_factor_learning as learning
from structural_analysis.io.neutral.loader import load_neutral_json


SOURCE = Path("examples/research/rc_reuse_campaign")
FLOOR = {
    "target_index": 2,
    "target_control_displacement_m": -0.00014,
    "minimum_load_factor": 180.0,
}


def _candidate(candidate_id, width):
    return design.FiberFrameDesignCandidate(
        candidate_id, (design.FiberFrameSectionChange("RC1", width_m=width),)
    )


def _inputs():
    return {
        "baseline": load_neutral_json(SOURCE / "pin-roller-replication.model.json"),
        "candidates": (_candidate("w32", 0.32), _candidate("w56", 0.56)),
        "request": decode_bounded_rc_fiber_direct_control_request(
            (SOURCE / "pin-roller-replication.request.json").read_bytes()
        ),
        "force_response_floor": dict(FLOOR),
        "history_limits": design.FiberFrameHistoryLimits(1, 1),
        "material_limits": design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        "source_revision": "a" * 40,
    }


def test_force_factor_fit_retains_failed_floor_as_signed_verified_label(tmp_path):
    args = _inputs()
    policy, report = learning.train_rc_control_force_factor_policy(
        **args, output_directory=tmp_path / "training"
    )
    root = tmp_path / "training"
    labels = json.loads((root / "labels" / "comparison.json").read_bytes())
    samples = json.loads((root / "training-samples.json").read_bytes())
    assert report["schema_version"] == learning.FORCE_FACTOR_TRAINING_SCHEMA
    assert report["sample_count"] == 3
    assert len(report["label_invocations"]) == 6
    assert all(row["full_reference_verification_pass"] for row in labels["rows"])
    assert any(
        row["screens"]["load_factor_at_target"]["status"] == "fail"
        for row in labels["rows"]
    )
    assert [sample["targets"][-1] for sample in samples] == [
        row["performance"]["load_factor_at_target"] for row in labels["rows"]
    ]
    assert all(len(sample["targets"]) == 8 for sample in samples)
    assert policy.to_dict()["force_target"] == {
        "target_index": FLOOR["target_index"],
        "target_control_displacement_m": FLOOR["target_control_displacement_m"],
    }
    prediction = policy.predict(args["baseline"], args["request"], FLOOR)
    assert prediction["abstained"] is False
    assert isinstance(prediction["performance"]["load_factor_at_target"], float)
    assert prediction["physical_result_authority"] is False
    other_target = dict(FLOOR, target_index=1, target_control_displacement_m=-0.00009)
    wrong_target_prediction = policy.predict(
        args["baseline"], args["request"], other_target
    )
    assert wrong_target_prediction["performance"] is None
    assert wrong_target_prediction["abstained"] is True
    assert wrong_target_prediction["reason"] == "force_target_or_fixed_context_mismatch"
    outside = design.apply_fiber_frame_section_changes(
        args["baseline"], _candidate("outside", 0.60)
    )
    assert policy.predict(outside, args["request"], FLOOR)["reason"] == (
        "outside_training_feature_bounds"
    )
    assert report["independent_generalization"] is False
    assert report["net_savings_proved"] is False


def test_force_target_and_invalid_request_rejected_before_output(tmp_path):
    args = _inputs()
    wrong = dict(FLOOR, target_index=1)
    with pytest.raises(ValueError, match="target differs"):
        learning.train_rc_control_force_factor_policy(
            **(args | {"force_response_floor": wrong}),
            output_directory=tmp_path / "wrong-target",
        )
    assert not (tmp_path / "wrong-target").exists()
    changed = replace(args["request"], experimental_pin_roller_beam=False)
    with pytest.raises(ValueError, match="pin/roller"):
        learning.train_rc_control_force_factor_policy(
            **(args | {"request": changed}),
            output_directory=tmp_path / "wrong-request",
        )
    assert not (tmp_path / "wrong-request").exists()


def test_force_factor_policy_rejects_duplicate_json_key():
    raw = b'{"schema_version":"one","schema_version":"two"}'
    with pytest.raises(ValueError, match="duplicate"):
        learning.load_rc_control_force_factor_policy(raw)
