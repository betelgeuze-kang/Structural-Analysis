"""V4 search preserves the authored pin/roller path and solver authority."""

from dataclasses import replace
from pathlib import Path
import json

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_candidate_learning as learning
from structural_analysis.benchmark import rc_control_candidate_search as search
from structural_analysis.io.neutral.loader import load_neutral_json


def candidate(name, width):
    return design.FiberFrameDesignCandidate(
        name, (design.FiberFrameSectionChange("RC1", width_m=width),)
    )


def inputs():
    root = Path("examples/research/rc_reuse_campaign")
    return dict(
        baseline=load_neutral_json(root / "pin-roller-steel-plastic.model.json"),
        candidates=(candidate("wider", 0.5),),
        request=decode_bounded_rc_fiber_direct_control_request(
            (root / "pin-roller-steel-plastic.request.json").read_bytes()
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
    )


def test_v4_descriptors_preserve_request_and_reject_missing_opt_in():
    args = inputs()
    for descriptor in (
        learning.control_candidate_features,
        learning.control_reinforcement_features,
    ):
        values, context = descriptor(args["baseline"], args["request"])
        changed, changed_context = descriptor(
            design.apply_fiber_frame_section_changes(
                args["baseline"], args["candidates"][0]
            ),
            args["request"],
        )
        assert values != changed and context == changed_context
        with pytest.raises(ValueError, match="supported public RC profile"):
            descriptor(
                args["baseline"],
                replace(args["request"], experimental_pin_roller_beam=False),
            )


def test_v4_full_search_keeps_complete_pair_and_separate_oracle(tmp_path):
    args = inputs()
    policy, training = learning.train_rc_control_candidate_policy(
        **(
            args
            | {
                "baseline": design.apply_fiber_frame_section_changes(
                    args["baseline"], candidate("training-base", 0.36)
                ),
                "candidates": (candidate("training-wide", 0.54),),
            }
        ),
        output_directory=tmp_path / "training",
    )
    root = tmp_path / "search"
    report = search.compare_rc_control_candidate_search(
        **args,
        policy=policy,
        training_report=training,
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-29", "Synthetic development arithmetic only"
        ),
        output_directory=root,
        full_analysis_budget=2,
        evaluate_exhaustive_oracle=True,
    )
    assert report["schema_version"] == "experimental-rc-control-candidate-search.v3"
    assert report["candidate_denominator"] == 2
    assert report["candidate_coverage_audit"]["alternative_denominator"] == 1
    assert report["historical_training_cost"] == training
    assert report["historical_training_cost_counted_once_outside_online_arms"] is True
    plan = json.loads((root / "plan.json").read_bytes())
    assert plan["control_request"] == args["request"].to_dict()
    assert plan["original_training_and_pool_models_disjoint"] is True
    assert not set(policy.to_dict()["training_model_identities"]) & {
        r["model_identity"] for r in plan["pool"]
    }
    for name in ("price_order", "learned_order", "exhaustive_oracle"):
        comparison = json.loads((root / name / "comparison.json").read_bytes())
        assert comparison["selected_candidate_id"] == "baseline"
        assert [r["candidate_id"] for r in comparison["rows"]] == ["baseline", "wider"]
        for row in comparison["rows"]:
            assert row["full_reference_verification_pass"] and row["selection_eligible"]
            result = json.loads(
                (root / name / row["artifacts"]["result"]["path"]).read_bytes()
            )
            assert result["request"]["experimental_pin_roller_beam"] is True
            assert result["path"]["accepted_target_prefix_m"] == list(
                args["request"].targets_m
            )
            assert all(i["unknown_execution_work"] is False for i in row["invocations"])
            assert [i["work"]["attempted_step_count"] for i in row["invocations"]] == [
                4,
                4,
            ]
            assert all(
                {(r["node_id"], r["dof"]) for r in response["support_reactions"]}
                == {("N2", "UX"), ("N2", "UY"), ("N6", "UY")}
                for response in result["response_history"]
            )
    assert report["claims"]["net_savings_proved"] is False
