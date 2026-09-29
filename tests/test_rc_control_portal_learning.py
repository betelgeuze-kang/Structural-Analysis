"""The two-fixed RC portal opt-in reaches learning and full-path comparisons."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_runtime_selection as selection
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
    validate_control_learning_split_shapes,
)
from structural_analysis.io.neutral.loader import load_neutral_json


_PORTAL = Path("examples/research/rc_internal_portal_20mm")


def _portal_cases():
    request = decode_bounded_rc_fiber_direct_control_request(
        (_PORTAL / "experimental-two-fixed-endpoints-request.json").read_bytes()
    )
    return [
        learning.RCControlLearningCase(
            case_id,
            case_id,
            case_id,
            case_id,
            split,
            load_neutral_json(_PORTAL / model_file),
            replace(request, targets_m=targets),
        )
        for case_id, split, model_file, targets in (
            (
                "train-a",
                "train",
                "portal-span-360.json",
                (-0.01, -0.02, 0.01),
            ),
            (
                "train-b",
                "train",
                "original-model.json",
                (-0.008, 0.002, -0.012),
            ),
            (
                "validation",
                "validation",
                "portal-span-440.json",
                (-0.006, 0.001, -0.009),
            ),
        )
    ]


def test_legacy_split_and_group_payload_hashes_are_unchanged():
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = learning.BoundedRCFiberDirectControlRequest(
        7,
        (-0.01, -0.02, 0.01, 0.02, 0.0, -0.02),
        allow_reversals=True,
        maximum_reversals=2,
    )
    cases = [
        learning.RCControlLearningCase(name, name, name, name, "train", model, request)
        for name in ("a", "b")
    ]
    assert _sha(_bytes(validate_control_learning_split_shapes(cases))) == (
        "sha256:d47853f938847dfdd412898ce9999b2f0d1edd32cf58e27e6820946d797925f1"
    )
    assert _sha(_bytes(control_training_exclusion_groups(cases))) == (
        "sha256:e3aff9ba86eccfb87da3df301e4d8e06032930236a743047562292dc109e2419"
    )


def test_portal_profiles_group_separately_and_mixed_roster_refuses_before_output(
    tmp_path,
):
    cases = _portal_cases()
    shapes = validate_control_learning_split_shapes(cases)
    groups = control_training_exclusion_groups(cases)
    assert shapes["experimental_two_fixed_endpoints"] is True
    assert groups["experimental_two_fixed_endpoints"] is True
    assert groups["groups"] == [["train-a"], ["train-b"]]
    prepared = learning._preflight(cases)
    assert {row[1].problem.free_global_dofs for row in prepared.values()} == {
        (6, 7, 8, 9, 10, 11)
    }
    assert len({row[2].context_hash for row in prepared.values()}) == 1

    mixed = [
        cases[0],
        learning.RCControlLearningCase(
            "legacy",
            "legacy",
            "legacy",
            "legacy",
            "train",
            cases[1].model,
            replace(cases[1].request, experimental_two_fixed_endpoints=False),
        ),
        cases[2],
    ]
    with pytest.raises(
        ValueError, match="mixed or invalid RC learning compiler profiles"
    ):
        validate_control_learning_split_shapes(mixed)
    with pytest.raises(
        ValueError, match="mixed or invalid RC learning compiler profiles"
    ):
        control_training_exclusion_groups(mixed)
    output = tmp_path / "mixed"
    with pytest.raises(
        ValueError, match="mixed or invalid RC learning compiler profiles"
    ):
        learning.run_rc_control_learning_study(
            mixed,
            source_revision="a" * 40,
            output_directory=output,
        )
    assert not output.exists()


def test_pin_roller_profile_refuses_learning_before_output(tmp_path):
    # The v4 flag must be rejected before any model compilation or label output.
    cases = [
        learning.RCControlLearningCase(
            case.case_id,
            case.project_id,
            case.geometry_family_id,
            case.load_history_id,
            case.split,
            case.model,
            replace(
                case.request,
                experimental_two_fixed_endpoints=False,
                experimental_pin_roller_beam=True,
            ),
        )
        for case in _portal_cases()
    ]
    assert all(case.request.to_dict()["schema_version"].endswith(".v4") for case in cases)
    with pytest.raises(ValueError, match="pin-roller RC learning compiler profile"):
        validate_control_learning_split_shapes(cases)
    with pytest.raises(ValueError, match="pin-roller RC learning compiler profile"):
        control_training_exclusion_groups(cases)
    output = tmp_path / "unsupported-pin-roller-learning"
    with pytest.raises(ValueError, match="pin-roller RC learning compiler profile"):
        learning.run_rc_control_learning_study(
            cases, source_revision="a" * 40, output_directory=output
        )
    assert not output.exists()


def test_portal_opt_in_survives_real_learning_proposal_and_grouped_full_paths(
    tmp_path,
):
    cases = _portal_cases()
    root = tmp_path / "portal-learning"
    report = learning.run_rc_control_learning_study(
        cases,
        source_revision="a" * 40,
        output_directory=root,
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
        ridge=1e4,
        # Test-only range slack forces an actual proposal through the native
        # full-path verifier; it is not a selected or calibrated policy margin.
        ood_margin=10.0,
    )
    samples = json.loads((root / "training-samples.json").read_bytes())
    assert len(samples) == 4
    assert report["fit"]["status"] == "completed"
    assert all(row["labels_eligible"] for row in report["generation"])
    assert all(
        row["report"]["request"]["experimental_two_fixed_endpoints"] is True
        for row in report["generation"]
    )
    evaluated = report["evaluation"]
    assert len(evaluated) == 1 and evaluated[0]["status"] == "returned"
    comparison = evaluated[0]["report"]
    assert comparison["request"]["experimental_two_fixed_endpoints"] is True
    assert comparison["reference_repeat_exact"]
    assert comparison["all_execution_work_reported"]
    assert all(row["full_history_pass"] for row in comparison["comparisons"].values())
    assert all(row["status"] == "complete" for row in comparison["arms"].values())
    assert any(
        decision["decision"] == "proposed"
        for decision in evaluated[0]["proposal_decisions"]
    )

    policy = learning.RCControlSeedPolicy(json.dumps(report["policy"]))
    selection_root = tmp_path / "portal-runtime-selection"
    selected = selection.run_rc_control_runtime_selection(
        cases,
        samples,
        policy,
        source_revision="a" * 40,
        output_directory=selection_root,
        ridge_grid=(1e4,),
        withholding_strategy="connected_training_groups",
        proposal_abstention_strategy="secant",
        maximum_fits=3,
        maximum_core_calls=100,
    )
    plan = json.loads((selection_root / "plan.json").read_bytes())
    assert plan["training_exclusion_groups"]["groups"] == [["train-a"], ["train-b"]]
    assert plan["training_exclusion_groups"]["experimental_two_fixed_endpoints"]
    assert len(selected["folds"]) == 2
    assert all(fold["score"]["full_comparison_pass"] for fold in selected["folds"])
    assert all(
        fold["score"]["execution_work"]["unknown_work"] is False
        for fold in selected["folds"]
    )
    assert all(
        json.loads((selection_root / f"fold-{index:04d}/request.json").read_bytes())[
            "request"
        ]["experimental_two_fixed_endpoints"]
        for index in range(2)
    )
