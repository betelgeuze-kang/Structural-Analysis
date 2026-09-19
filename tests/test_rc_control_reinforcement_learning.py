"""Distinct reinforcement policies retain physical labels and legacy boundaries."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_candidate_learning as learning
from structural_analysis.benchmark import rc_control_candidate_search as search
from structural_analysis.benchmark.rc_control_reinforcement_features import (
    control_reinforcement_features,
    REINFORCEMENT_FEATURE_NAMES,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def base():
    return load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))


def change(name, top, bottom):
    return design.FiberFrameDesignCandidate(
        name,
        (
            design.FiberFrameSectionChange(
                "RC1",
                top_bar_area_m2=top,
                bottom_bar_area_m2=bottom,
            ),
        ),
    )


def request():
    return BoundedRCFiberDirectControlRequest(
        4,
        (-1e-5, -2e-5, 1e-5),
        allow_reversals=True,
        maximum_reversals=2,
        constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
    )


def test_area_swap_is_feature_difference_not_context_relaxation():
    a = design.apply_fiber_frame_section_changes(base(), change("a", 0.0002, 0.0004))
    b = design.apply_fiber_frame_section_changes(base(), change("b", 0.0004, 0.0002))
    va, ca = control_reinforcement_features(a, request())
    vb, cb = control_reinforcement_features(b, request())
    assert ca == cb and va != vb
    assert va[3] == vb[3]  # same total steel does not imply the same placement
    assert len(va) == len(REINFORCEMENT_FEATURE_NAMES)
    assert (
        learning.control_candidate_features(a, request())[1]
        != learning.control_candidate_features(b, request())[1]
    )
    assert (
        control_reinforcement_features(a, replace(request(), constant_nodal_loads=()))[
            1
        ]
        != ca
    )
    b.materials[0]["yield_stress_mpa"] *= 1.1
    assert control_reinforcement_features(b, request())[1] != ca


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("reinforcement-policy") / "training"
    policy, report = learning.train_rc_control_candidate_policy(
        base(),
        (change("top-small", 0.0002, 0.0004), change("bottom-small", 0.0004, 0.0002)),
        request(),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
        output_directory=root,
        reinforcement_features=True,
    )
    return policy, report, root


def test_full_labels_and_separate_policy_schema(trained):
    policy, report, root = trained
    assert type(policy) is learning.RCControlReinforcementPolicy
    assert report["sample_count"] == 3
    assert len(report["label_invocations"]) == 6
    assert report["net_savings_proved"] is False
    labels = json.loads((root / "labels" / "comparison.json").read_bytes())
    assert all(row["full_reference_verification_pass"] for row in labels["rows"])
    assert (
        learning.RCControlReinforcementPolicy(policy._json).policy_hash
        == policy.policy_hash
    )
    with pytest.raises(ValueError):
        learning.RCControlCandidatePolicy(policy._json)


def test_new_policy_executes_unseen_candidate_search_and_oracle(trained, tmp_path):
    policy, training, _ = trained
    baseline = design.apply_fiber_frame_section_changes(
        base(), change("evaluation", 0.0003, 0.00035)
    )
    result = search.compare_rc_control_candidate_search(
        baseline,
        (change("cheaper", 0.00025, 0.00035),),
        request(),
        policy=policy,
        training_report=training,
        prices=design.FiberFrameMaterialPrices(
            100, 2, "USD", "2026-09-20", "synthetic test"
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
        output_directory=tmp_path / "search",
        full_analysis_budget=2,
        evaluate_exhaustive_oracle=True,
    )
    assert all(
        arm["selected_full_reference_verified"] for arm in result["arms"].values()
    )
    assert all(
        arm["selected_candidate_id"] == "cheaper" for arm in result["arms"].values()
    )
    assert result["claims"]["net_savings_proved"] is False
    assert result["historical_training_cost"]["report_hash"] == training["report_hash"]


def test_new_policy_rejects_unseen_request_and_extrapolated_area(trained):
    policy, _, _ = trained
    inside = design.apply_fiber_frame_section_changes(
        base(), change("inside", 0.0003, 0.00035)
    )
    outside = design.apply_fiber_frame_section_changes(
        base(), change("outside", 0.0001, 0.0005)
    )
    assert policy.predict(outside, request())["performance"] is None
    assert (
        policy.predict(inside, replace(request(), constant_nodal_loads=()))[
            "performance"
        ]
        is None
    )


def test_legacy_training_does_not_silently_adopt_new_area_features(tmp_path):
    root = tmp_path / "legacy"
    with pytest.raises(ValueError, match="one fixed context"):
        learning.train_rc_control_candidate_policy(
            base(),
            (change("unequal", 0.0002, 0.0004),),
            request(),
            history_limits=design.FiberFrameHistoryLimits(1, 1),
            material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
            source_revision="a" * 40,
            output_directory=root,
        )
    assert not root.exists()


def test_unused_area_alias_is_rejected_as_duplicate_before_training(tmp_path):
    root = tmp_path / "duplicates"
    model = design.apply_fiber_frame_section_changes(
        base(), change("physical", 0.0002, 0.0004)
    )
    alias = design.FiberFrameDesignCandidate(
        "alias", (design.FiberFrameSectionChange("RC1", bar_area_m2=0.0003),)
    )
    with pytest.raises(ValueError, match="unique physical training models"):
        learning.train_rc_control_candidate_policy(
            model,
            (alias,),
            request(),
            history_limits=design.FiberFrameHistoryLimits(1, 1),
            material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
            source_revision="a" * 40,
            output_directory=root,
            reinforcement_features=True,
        )
    assert not root.exists()


def test_explicit_schema_loader_rejects_unknown_and_ambiguous_documents(trained):
    policy, _, _ = trained
    loader = learning.load_rc_control_candidate_policy
    assert type(loader(policy._json.encode())) is learning.RCControlReinforcementPolicy
    with pytest.raises(ValueError, match="duplicate"):
        loader(b'{"schema_version":"unknown",' + policy._json.encode()[1:])
    for schema in ("unknown", None, [], 1):
        with pytest.raises(ValueError, match="schema"):
            loader(json.dumps({"schema_version": schema}).encode())
    with pytest.raises(ValueError, match="bytes"):
        loader(policy._json)
