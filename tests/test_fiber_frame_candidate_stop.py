"""Real search/M2 serialization over retained rows and synthetic material data.

These control-flow and source-binding tests forbid solves, fitting and workers;
they do not establish numerical correctness or a timing benefit.
"""

from copy import deepcopy

import pytest

from structural_analysis.ai.fiber_frame_candidate_learning import (
    FiberFrameCandidatePrediction,
)
from structural_analysis.benchmark import fiber_frame_candidate_search as core
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from structural_analysis.benchmark import fiber_frame_design as design
from tests.test_fiber_frame_candidate_material_contract import (
    arguments as _arguments,
    material_request as _material_request,
    no_execution as _no_execution,
    rehash,
    retained as _retained,
    with_material,
)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    return _no_execution.__wrapped__(monkeypatch)


@pytest.fixture(scope="module")
def retained():
    return _retained.__wrapped__()


@pytest.fixture
def options(tmp_path, retained):
    request = _material_request.__wrapped__(tmp_path, retained)
    return {
        **_arguments.__wrapped__(request),
        "stop_mode": core.FIRST_VERIFIED_FEASIBLE,
        "full_analysis_budget": 3,
        "exploration_slots": 0,
    }


@pytest.fixture
def controlled_rows(monkeypatch, retained, options):
    original = next(
        run["report"]["rows"] for run in retained["runs"] if run["strategy"] == "oracle"
    )
    by_model = {row["model_checksum"]: row for row in original}
    state = {
        "calls": [],
        "ood": False,
        "damage": {"baseline": 0.4, "narrow": 0.1, "near-limit": 0.1},
    }
    original_evaluate = design._evaluate_design

    def predict(_policy, model, _config):
        # Explicit algebraic ranking control; no accuracy claim about stored weights.
        if state["ood"]:
            return FiberFrameCandidatePrediction(None, None, True, "synthetic_ood")
        key = by_model[model.canonical_model_checksum]["candidate_id"]
        ratio = 2.0 if key == "narrow" else 0.5
        return FiberFrameCandidatePrediction(
            options["terminal_limits"].maximum_translation_m * ratio,
            options["terminal_limits"].maximum_absolute_fiber_strain * ratio,
            False,
            "synthetic_ordering_fixture",
        )

    def evaluate(candidate_id, model, *args, **kwargs):
        state["calls"].append(candidate_id)
        if candidate_id == state.get("exception_candidate"):
            return original_evaluate(candidate_id, model, *args, **kwargs)
        row = with_material(
            by_model[model.canonical_model_checksum], state["damage"][candidate_id]
        )
        row.pop("analysis_requested", None)
        row.update(candidate_id=candidate_id, reference_and_quantity_wall_ns=0)
        return row

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    monkeypatch.setattr(type(options["training"].policy), "predict", predict)
    return state


def produce(options, strategy):
    expectations = arm.prepare_fiber_frame_candidate_search_expectations(**options)
    report = arm.run_fiber_frame_candidate_search_arm(
        **options,
        strategy=strategy,
        expected_plan_hash=expectations[strategy]["frozen_plan_hash"],
    )
    arm.validate_fiber_frame_candidate_search_arm_report(
        report, expectations, strategy=strategy
    )
    return report, expectations


@pytest.mark.parametrize("strategy", ["deterministic", "learned"])
def test_first_verified_feasible_preserves_plan_and_original_prefix(
    options, controlled_rows, strategy
):
    report, expected = produce(options, strategy)
    actual = report["arm"]
    prefix = ["narrow", "near-limit"] if strategy == "deterministic" else ["near-limit"]
    assert report["schema_version"] == arm.ARM_STOP_SCHEMA_VERSION
    assert actual["shortlist"] == expected[strategy]["frozen_plan"]["shortlist"]
    assert len(actual["shortlist"]) == 2
    assert controlled_rows["calls"] == ["baseline", *prefix]
    assert actual["execution"]["attempted_candidate_ids"] == prefix
    assert actual["execution"]["stop_candidate_id"] == "near-limit"
    assert actual["execution"]["termination_reason"] == "first_verified_feasible"
    assert actual["execution"]["unused_analysis_request_budget"] == 2 - len(prefix)
    assert actual["cost_accounting"]["total_analysis_request_count"] == len(prefix) + 1
    assert [row["candidate_id"] for row in actual["design_comparison"]["rows"]] == [
        "baseline",
        *prefix,
    ]
    assert [row["candidate_id"] for row in actual["candidate_outcomes"]] == [
        "narrow",
        "near-limit",
    ]
    if strategy == "learned":
        skipped = actual["candidate_outcomes"][0]
        assert skipped["status"] == "not_attempted_after_stop"
        assert skipped["analysis_requested"] is False and skipped["result"] is None


def test_verified_baseline_stops_before_candidate_and_remains_source_validated(
    options, controlled_rows
):
    controlled_rows["damage"]["baseline"] = 0.1
    report, expected = produce(options, "learned")
    actual = report["arm"]
    assert controlled_rows["calls"] == ["baseline"]
    assert actual["execution"]["stop_candidate_id"] == "baseline"
    assert actual["execution"]["attempted_candidate_ids"] == []
    assert actual["design_comparison"] is None
    assert (
        actual["design_comparison_unavailable_reason"]
        == "stopped_before_candidate_evaluation"
    )
    forged = deepcopy(report)
    forged["arm"]["baseline"]["material_estimate"]["total"] += 1.0
    forged["arm"]["final_selection"] = deepcopy(forged["arm"]["baseline"])
    rehash(forged)
    with pytest.raises(ValueError):
        arm.validate_fiber_frame_candidate_search_arm_report(
            forged, expected, strategy="learned"
        )


def test_failed_material_limits_exhaust_instead_of_using_ready_status(
    options, controlled_rows
):
    controlled_rows["damage"] = {key: 0.4 for key in controlled_rows["damage"]}
    report, _ = produce(options, "learned")
    actual = report["arm"]
    assert report["status"] == "blocked" and actual["final_selection"] is None
    assert controlled_rows["calls"] == ["baseline", *actual["shortlist"]]
    assert actual["execution"]["termination_reason"] == "planned_shortlist_exhausted"
    assert actual["execution"]["unattempted_candidate_ids"] == []
    assert actual["cost_accounting"]["total_analysis_request_count"] == 3


def test_ood_predictions_continue_to_full_verification_without_safety_credit(
    options, controlled_rows
):
    controlled_rows["ood"] = True
    report, _ = produce(options, "learned")
    assert all(
        row["predicted_terminal_safe"] is None for row in report["candidate_pool"]
    )
    assert controlled_rows["calls"] == ["baseline", "narrow", "near-limit"]
    assert report["arm"]["final_selection"]["candidate_id"] == "near-limit"


@pytest.mark.parametrize("failed_id", ["baseline", "narrow"])
def test_injected_analysis_failure_retains_unknown_execution_and_correct_stop(
    options, controlled_rows, monkeypatch, failed_id
):
    def fail_without_numerical_execution(*args, **kwargs):
        raise RuntimeError("synthetic public-call exception before numerical execution")

    monkeypatch.setattr(
        design.public_api,
        "analyze_public_rc_fiber_frame",
        fail_without_numerical_execution,
    )
    controlled_rows["exception_candidate"] = failed_id
    controlled_rows["ood"] = True
    report, _ = produce(options, "learned")
    actual = report["arm"]
    assert actual["cost_accounting"]["unknown_solver_execution_count"] == 1
    if failed_id == "baseline":
        assert controlled_rows["calls"] == ["baseline"]
        assert report["status"] == "blocked" and actual["final_selection"] is None
        assert (
            actual["execution"]["termination_reason"]
            == "baseline_verification_unavailable"
        )
        assert actual["execution"]["attempted_candidate_ids"] == []
        assert actual["cost_accounting"]["known_solver_execution_count"] == 0
    else:
        assert controlled_rows["calls"] == ["baseline", "narrow", "near-limit"]
        assert actual["execution"]["termination_reason"] == "first_verified_feasible"
        assert actual["final_selection"]["candidate_id"] == "near-limit"
        assert actual["candidate_outcomes"][0]["analysis_requested"] is True
        assert (
            actual["candidate_outcomes"][0]["full_reference_verification_pass"] is False
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report["arm"]["execution"].update(attempted_candidate_ids=[]),
        lambda report: report["arm"]["execution"].update(
            attempted_candidate_ids=["narrow"]
        ),
        lambda report: report["arm"]["execution"].update(
            attempted_candidate_ids=["near-limit", "narrow"]
        ),
        lambda report: report["arm"]["execution"].update(
            termination_reason="planned_shortlist_exhausted"
        ),
        lambda report: report["arm"]["execution"].update(stop_candidate_id="baseline"),
        lambda report: report["arm"]["execution"].update(
            unused_analysis_request_budget=True
        ),
        lambda report: report["arm"]["execution"].update(unattempted_candidate_ids=[]),
        lambda report: report["arm"]["execution"].update(
            global_material_optimality_verified=True
        ),
        lambda report: report["arm"]["candidate_outcomes"][0].update(
            analysis_requested=True
        ),
        lambda report: report.pop("stop_mode"),
        lambda report: report.update(schema_version=arm.ARM_MATERIAL_SCHEMA_VERSION),
    ],
)
def test_rehashed_stop_prefix_receipt_and_downgrade_mutations_rejected(
    options, controlled_rows, mutation
):
    report, expected = produce(options, "learned")
    mutation(report)
    rehash(report)
    with pytest.raises(ValueError):
        arm.validate_fiber_frame_candidate_search_arm_report(
            report, expected, strategy="learned"
        )


def test_oracle_stays_exhaustive_and_counts_unrequested_feasible_separately(
    options, controlled_rows
):
    report, _ = produce(options, "learned")
    oracle = arm.run_fiber_frame_candidate_search_oracle(**options)
    assert controlled_rows["calls"] == [
        "baseline",
        "near-limit",
        "baseline",
        "narrow",
        "near-limit",
    ]
    frozen = arm.prepare_fiber_frame_candidate_search_expectations(**options)
    arm.validate_fiber_frame_candidate_search_oracle_report(oracle, frozen)
    assert oracle["schema_version"] == arm.ORACLE_STOP_SCHEMA_VERSION
    pool = report["candidate_pool"]
    planned = core._audit_outcomes(
        pool, report["arm"]["shortlist"], oracle["rows"], True, True
    )
    audited = core._with_unrequested_feasible(
        planned, pool, [], oracle["rows"], True, True
    )
    assert audited["missed_feasible_count"] == 0
    assert audited["unrequested_feasible_candidate_ids"] == ["near-limit"]
    assert audited["unrequested_feasible_count"] == 1
    assert "unrequested_feasible_count" not in planned
    unavailable = core._with_unrequested_feasible(planned, pool, [], None, True, True)
    assert unavailable["unrequested_feasible_count"] is None
    assert unavailable["unrequested_feasible_candidate_ids"] is None


@pytest.mark.parametrize(
    "value", [False, True, 1, "", "evaluate_shortlist", "first_predicted_safe"]
)
def test_bad_stop_policy_rejected_before_evaluation(options, controlled_rows, value):
    with pytest.raises(ValueError, match="stop mode"):
        arm.run_fiber_frame_candidate_search_arm(
            **{**options, "stop_mode": value}, strategy="learned"
        )
    assert controlled_rows["calls"] == []
