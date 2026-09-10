"""Real small control studies plus explicitly injected decision/failure checks."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_candidate_learning as learning
from structural_analysis.benchmark import rc_control_candidate_search as search
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.io.neutral.loader import load_neutral_json


def candidate(name, width):
    return design.FiberFrameDesignCandidate(
        name, (design.FiberFrameSectionChange("RC1", width_m=width),)
    )


def model(width):
    base = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
    return design.apply_fiber_frame_section_changes(base, candidate("dimension", width))


def inputs():
    return dict(
        baseline=model(0.32),
        candidates=(candidate("medium", 0.40), candidate("wide", 0.54)),
        request=BoundedRCFiberDirectControlRequest(
            4,
            (-1e-5, -2e-5, 1e-5),
            allow_reversals=True,
            maximum_reversals=2,
            constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        source_revision="a" * 40,
    )


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("rc-candidate-train") / "study"
    args = inputs()
    before = args["baseline"].canonical_payload()
    policy, report = learning.train_rc_control_candidate_policy(
        **args, output_directory=root
    )
    assert args["baseline"].canonical_payload() == before
    return policy, report, root


def search_inputs(trained):
    policy, training, _ = trained
    args = inputs()
    args.update(
        baseline=model(0.43),
        candidates=(
            candidate("cheap", 0.36),
            candidate("middle", 0.46),
            candidate("costly", 0.50),
        ),
        policy=policy,
        training_report=training,
        full_analysis_budget=2,
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-10", "synthetic test only"
        ),
    )
    return args


def test_actual_training_labels_include_preload_all_epochs_and_fresh_verification(
    trained,
):
    policy, report, root = trained
    labels = json.loads((root / "labels/comparison.json").read_bytes())
    samples = json.loads((root / "training-samples.json").read_bytes())
    assert labels["verified_count"] == 3 and report["sample_count"] == 3
    assert len(report["label_invocations"]) == 6
    assert (
        sum(i["work"]["attempted_step_count"] for i in report["label_invocations"])
        == 24
    )
    for row, sample in zip(labels["rows"], samples, strict=True):
        assert row["performance"]["accepted_epoch_count"] == 4
        assert sample["targets"] == [row["performance"][k] for k in learning.TARGETS]
        assert row["full_reference_verification_pass"]
    p = policy.to_dict()
    x = np.array([s["features"] for s in samples])
    y = np.array([s["targets"] for s in samples])
    assert np.array_equal(x.mean(axis=0), p["mean"])
    z = np.column_stack(((x - p["mean"]) / p["scale"], np.ones(len(x))))
    w = np.array(p["weights"])
    residual = z.T @ (z @ w - y / p["target_scale"]) + p["ridge"] * w
    assert (
        np.linalg.norm(residual) / max(np.linalg.norm(z.T @ (y / p["target_scale"])), 1)
        < 1e-12
    )
    assert (
        report["wall_ns"]
        >= report["label_generation_wall_ns"] + report["fit"]["wall_ns"]
    )
    assert not report["independent_generalization"] and not report["net_savings_proved"]


def test_actual_search_freezes_both_rankings_before_full_paths_and_oracle(
    trained, tmp_path, monkeypatch
):
    args = search_inputs(trained)
    before = args["baseline"].canonical_payload()
    root = tmp_path / "search"
    call = study.compare_rc_control_designs
    observed = []

    def observe(*a, **kw):
        plan = json.loads((root / "plan.json").read_bytes())
        assert set(plan["plans"]) == {"price_order", "learned_order"}
        assert plan["predictions"]
        observed.append(kw["output_directory"].name)
        return call(*a, **kw)

    monkeypatch.setattr(study, "compare_rc_control_designs", observe)
    report = search.compare_rc_control_candidate_search(
        **args, output_directory=root, evaluate_exhaustive_oracle=True
    )
    assert observed == ["price_order", "learned_order", "exhaustive_oracle"]
    assert args["baseline"].canonical_payload() == before
    assert report["candidate_denominator"] == 4
    for arm in report["arms"].values():
        assert arm["request_count"] == 2
        assert arm["execution_work"]["known_counters"]["attempted_step_count"] == 16
        assert arm["selected_full_reference_verified"]
        comparison = json.loads((root / arm["comparison_path"]).read_bytes())
        assert comparison["schema_version"] == study.SCHEMA
        assert comparison["price_table_hash"] == args["prices"].price_table_hash
        assert comparison["control_request"] == args["request"].to_dict()
        for row in comparison["rows"]:
            assert row["full_reference_verification_pass"]
            assert row["performance"]["accepted_epoch_count"] == 4
    assert report["oracle"]["request_count"] == 4
    assert (
        report["oracle"]["execution_work"]["known_counters"]["attempted_step_count"]
        == 32
    )
    assert report["historical_training_cost"] == trained[1]
    assert report["historical_training_cost_counted_once_outside_online_arms"]
    assert not report["claims"]["net_savings_proved"]
    audit = report["candidate_coverage_audit"]
    assert audit["alternative_denominator"] == 3
    assert audit["baseline_excluded"]
    for arm in audit["arms"].values():
        assert arm["missed_feasible_candidate_ids"] == ["middle", "costly"]
        assert arm["missed_feasible_count"] == 2
        assert arm["oracle_unverifiable_count"] == 0
    assert audit["arms"]["price_order"]["false_safe_count"] is None
    assert audit["oracle_comparison_hash"] == report["oracle"]["comparison_hash"]


@pytest.mark.parametrize(
    "change",
    [
        {"targets_m": (-1e-5, -3e-5, 1e-5)},
        {"constant_nodal_loads": (("N2", -500.0, 0.0, 0.0),)},
        {"maximum_reversals": 3},
    ],
)
def test_control_context_changes_reject_before_output_or_solves(
    trained, tmp_path, monkeypatch, change
):
    args = search_inputs(trained)
    args["request"] = replace(args["request"], **change)
    monkeypatch.setattr(
        study,
        "compare_rc_control_designs",
        lambda *a, **kw: pytest.fail("preflight must reject before solving"),
    )
    root = tmp_path / "rejected"
    with pytest.raises(ValueError, match="context mismatch"):
        search.compare_rc_control_candidate_search(**args, output_directory=root)
    assert not root.exists()


def test_training_physics_alias_cannot_enter_search(trained, tmp_path):
    args = search_inputs(trained)
    args["candidates"] = (candidate("renamed-training-case", 0.40),)
    with pytest.raises(ValueError, match="physical model overlap"):
        search.compare_rc_control_candidate_search(
            **args, output_directory=tmp_path / "reject"
        )


def test_training_costs_cannot_be_silently_changed(trained, tmp_path):
    args = search_inputs(trained)
    args["training_report"] = deepcopy(args["training_report"])
    args["training_report"]["wall_ns"] = 0
    with pytest.raises(ValueError, match="training report hash mismatch"):
        search.compare_rc_control_candidate_search(
            **args, output_directory=tmp_path / "reject"
        )


@pytest.mark.parametrize("budget", [True, 1, 18, 2.0])
def test_budget_rejection_before_execution(trained, tmp_path, budget):
    args = search_inputs(trained)
    args["full_analysis_budget"] = budget
    with pytest.raises(ValueError, match="requests per arm"):
        search.compare_rc_control_candidate_search(
            **args, output_directory=tmp_path / "reject"
        )


def test_policy_export_is_detached_and_tampering_rejected(trained):
    policy, _, _ = trained
    p = policy.to_dict()
    identity = policy.policy_hash
    p["weights"][0][0] += 1
    assert policy.policy_hash == identity
    with pytest.raises(ValueError, match="hash mismatch"):
        learning.RCControlCandidatePolicy(study._bytes(p).decode())
    assert learning.RCControlCandidatePolicy(policy._json).policy_hash == identity


def test_out_of_range_prediction_has_no_physical_values(trained):
    prediction = trained[0].predict(model(0.8), inputs()["request"])
    assert prediction["abstained"] and prediction["performance"] is None
    assert not prediction["physical_result_authority"]


@pytest.mark.parametrize("unknown_kind", ["missing", "declared"])
def test_unknown_work_stops_before_second_arm_or_oracle(
    trained, tmp_path, monkeypatch, unknown_kind
):
    args = search_inputs(trained)
    calls = []

    # Deliberately synthetic failure metadata; no numerical result is asserted.
    def failed(*a, **kw):
        calls.append(kw["output_directory"].name)
        work = {
            "attempted_step_count": 1,
            "known_linear_solve_count": 1,
            "known_newton_iteration_count": 1,
            "unknown_solver_work_attempt_count": 1 if unknown_kind == "declared" else 0,
        }
        if unknown_kind == "missing":
            work.pop("known_linear_solve_count")
        return {
            "rows": [
                {
                    "candidate_id": "baseline",
                    "invocations": [{"unknown_execution_work": False, "work": work}],
                }
            ],
            "selected_candidate_id": None,
            "report_hash": "sha256:" + "c" * 64,
        }

    monkeypatch.setattr(study, "compare_rc_control_designs", failed)
    root = tmp_path / "unknown"
    with pytest.raises(ValueError, match="unknown numerical work"):
        search.compare_rc_control_candidate_search(
            **args, output_directory=root, evaluate_exhaustive_oracle=True
        )
    assert calls == ["price_order"]
    assert json.loads((root / "price_order-outcome.json").read_bytes())[
        "unknown_work_until_outcome"
    ]
    assert not (root / "result.json").exists()


def test_interrupt_preserves_started_and_unknown_outcome(
    trained, tmp_path, monkeypatch
):
    def interrupt(*a, **kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(study, "compare_rc_control_designs", interrupt)
    root = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        search.compare_rc_control_candidate_search(
            **search_inputs(trained), output_directory=root
        )
    assert (root / "price_order-started.json").exists()
    outcome = json.loads((root / "price_order-outcome.json").read_bytes())
    assert outcome["status"] == "interrupted" and outcome["unknown_work_until_outcome"]
    assert not (root / "learned_order-started.json").exists()


def test_injected_optimistic_ranking_cannot_authorize_a_failed_physical_screen(
    trained, tmp_path, monkeypatch
):
    # Deliberately invented predictions test decision authority, not learned quality.
    def optimistic(self, model, request):
        return {
            "policy_hash": self.policy_hash,
            "abstained": False,
            "performance": dict.fromkeys(learning.TARGETS, 0.0),
            "physical_result_authority": False,
            "uncertainty_calibrated": False,
            "reason": "injected optimistic test prediction",
        }

    monkeypatch.setattr(learning.RCControlCandidatePolicy, "predict", optimistic)
    args = search_inputs(trained)
    args["history_limits"] = design.FiberFrameHistoryLimits(1e-20, 1e-20)
    report = search.compare_rc_control_candidate_search(
        **args,
        output_directory=tmp_path / "false-positive",
        evaluate_exhaustive_oracle=True,
    )
    assert all(a["selected_candidate_id"] is None for a in report["arms"].values())
    assert all(
        not a["selected_full_reference_verified"] for a in report["arms"].values()
    )
    audit = report["candidate_coverage_audit"]["arms"]["learned_order"]
    assert audit["false_safe_candidate_ids"] == ["cheap", "middle", "costly"]
    assert audit["false_safe_count"] == 3
    assert audit["predicted_safe_unverifiable_count"] == 0
    assert audit["missed_feasible_count"] == 0


def coverage_inputs():
    ids = ["baseline", "unsafe", "unknown", "missed", "abstained"]
    plan = {
        "pool": [{"candidate_id": i} for i in ids],
        "history_limits": {},
        "material_limits": {"damage": 1},
        "terminal_limits": None,
        "plans": {
            "price_order": {"shortlist": ["unsafe"]},
            "learned_order": {"shortlist": ["unsafe"]},
        },
        "predictions": [
            {
                "candidate_id": i,
                "prediction": {"abstained": i == "abstained"},
                "predicted_screens": None
                if i == "abstained"
                else {"damage": {"status": "fail" if i == "missed" else "pass"}},
            }
            for i in ids[1:]
        ],
    }
    # Deliberately mixed oracle controls: unknown has a failed-looking partial
    # screen but failed full verification. It must never become false-safe.
    oracle = {
        "report_hash": "sha256:" + "b" * 64,
        "rows": [
            {
                "candidate_id": i,
                "full_reference_verification_pass": i != "unknown",
                "screens": {
                    "damage": {
                        "status": "fail" if i in ("unsafe", "unknown") else "pass"
                    }
                },
            }
            for i in ids
        ],
    }
    return plan, oracle


def test_coverage_keeps_unverified_distinct_from_verified_failure():
    plan, oracle = coverage_inputs()
    report = search._coverage_audit(plan, oracle)
    learned = report["arms"]["learned_order"]
    assert learned["false_safe_candidate_ids"] == ["unsafe"]
    assert learned["predicted_safe_unverifiable_candidate_ids"] == ["unknown"]
    assert learned["oracle_unverifiable_candidate_ids"] == ["unknown"]
    assert learned["false_negative_candidate_ids"] == ["missed"]
    assert learned["missed_feasible_candidate_ids"] == ["missed", "abstained"]
    assert all(
        learned[k] == 1
        for k in [
            "false_safe_count",
            "predicted_safe_unverifiable_count",
            "false_negative_count",
        ]
    )
    assert report["arms"]["price_order"]["false_safe_count"] is None
    assert len(report["candidates"]) == 4
    assert report["candidates"][-1]["predicted_all_requested_limits_pass"] is None


def test_coverage_without_oracle_is_unavailable_not_zero():
    plan, _ = coverage_inputs()
    result = search._coverage_audit(plan, None)
    assert result["status"] == "oracle_not_run"
    assert result["oracle_comparison_hash"] is None
    assert all(
        value is None for arm in result["arms"].values() for value in arm.values()
    )
    assert all(
        r["oracle_all_requested_limits_pass"] is None for r in result["candidates"]
    )


def test_partial_screen_set_and_missing_work_remain_unknown():
    plan, oracle = coverage_inputs()
    oracle["rows"][1]["screens"] = {"unrequested": {"status": "fail"}}
    result = search._coverage_audit(plan, oracle)["arms"]["learned_order"]
    assert result["false_safe_count"] == 0
    assert result["predicted_safe_unverifiable_candidate_ids"] == ["unsafe", "unknown"]
    assert search._work(
        {"rows": [{"invocations": [{"unknown_execution_work": False, "work": None}]}]}
    )["unknown_work"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign"])
def test_coverage_rejects_incomplete_or_aliased_oracle_denominator(mutation):
    plan, oracle = coverage_inputs()
    if mutation == "missing":
        oracle["rows"].pop()
    else:
        oracle["rows"][-1]["candidate_id"] = (
            "unknown" if mutation == "duplicate" else "foreign"
        )
    with pytest.raises(ValueError, match="complete candidate pool"):
        search._coverage_audit(plan, oracle)


def test_injected_predictions_change_shortlist_before_any_solver_call(
    trained, tmp_path, monkeypatch
):
    args = search_inputs(trained)
    cheap_id = learning.candidate_model_identity(
        design.apply_fiber_frame_section_changes(
            args["baseline"], args["candidates"][0]
        )
    )

    def prediction(self, model, request):
        values = dict.fromkeys(learning.TARGETS, 0.0)
        if learning.candidate_model_identity(model) == cheap_id:
            values["maximum_absolute_fiber_strain"] = 2.0
        return {
            "policy_hash": self.policy_hash,
            "abstained": False,
            "performance": values,
            "physical_result_authority": False,
            "uncertainty_calibrated": False,
            "reason": "injected ranking control",
        }

    monkeypatch.setattr(learning.RCControlCandidatePolicy, "predict", prediction)
    root = tmp_path / "ranking"

    def inspect(*a, **kw):
        plan = json.loads((root / "plan.json").read_bytes())
        assert plan["plans"]["price_order"]["shortlist"] == ["cheap"]
        assert plan["plans"]["learned_order"]["shortlist"] == ["middle"]
        raise KeyboardInterrupt()

    monkeypatch.setattr(study, "compare_rc_control_designs", inspect)
    with pytest.raises(KeyboardInterrupt):
        search.compare_rc_control_candidate_search(**args, output_directory=root)


def test_infeasible_training_rows_are_retained_after_physical_verification(tmp_path):
    args = inputs()
    args["history_limits"] = design.FiberFrameHistoryLimits(1e-20, 1e-20)
    root = tmp_path / "infeasible-labels"
    policy, report = learning.train_rc_control_candidate_policy(
        **args, output_directory=root
    )
    labels = json.loads((root / "labels/comparison.json").read_bytes())
    assert all(not r["selection_eligible"] for r in labels["rows"])
    assert (
        report["sample_count"] == len(policy.to_dict()["training_sample_hashes"]) == 3
    )
