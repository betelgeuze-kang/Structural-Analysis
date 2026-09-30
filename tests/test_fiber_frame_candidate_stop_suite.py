"""Opt-in stop contracts over retained rows and synthetic memory statistics.

Only the row evaluation boundary is stubbed. Production planning, M2 assembly,
accounting and validators run unchanged; these are not new physical observations.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from structural_analysis.benchmark import fiber_frame_design as design
from tests.test_fiber_frame_candidate_material_contract import (
    SOURCE,
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
def arguments(tmp_path, retained):
    options = _arguments.__wrapped__(_material_request.__wrapped__(tmp_path, retained))
    return dict(
        options,
        stop_mode=search.FIRST_VERIFIED_FEASIBLE,
        candidates=tuple(reversed(options["candidates"])),
        full_analysis_budget=3,
        exploration_slots=0,
        terminal_limits=design.FiberFrameTerminalLimits(1.0, 1.0),
        history_limits=design.FiberFrameHistoryLimits(1.0, 1.0),
    )


@pytest.fixture
def evaluate_rows(retained, monkeypatch):
    source = next(
        r["report"]["rows"] for r in retained["runs"] if r["strategy"] == "oracle"
    )
    original = {row["model_checksum"]: row for row in source}
    original_evaluate = design._evaluate_design
    calls, damage = [], {"baseline": 0.4, "narrow": 0.1, "near-limit": 0.1}

    def evaluate(candidate_id, model, *_args, **_kwargs):
        calls.append(candidate_id)
        if damage[candidate_id] is None:

            def fail_public(*_args, **_kwargs):
                raise RuntimeError("synthetic public evaluation failure")

            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(
                    design.public_api, "analyze_public_rc_fiber_frame", fail_public
                )
                return original_evaluate(candidate_id, model, *_args, **_kwargs)
        row = with_material(
            original[model.canonical_model_checksum], damage[candidate_id]
        )
        row.pop("analysis_requested", None)
        row.update(
            candidate_id=candidate_id,
            reference_and_quantity_wall_ns=0,
            terminal_limit_status="pass",
            violated_terminal_limits=[],
            history_limit_status="pass",
            violated_history_limits=[],
        )
        return row

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    return calls, damage


def produce(arguments, *, oracle=True):
    expected = arm.prepare_fiber_frame_candidate_search_expectations(**arguments)
    payload = search.compare_fiber_frame_candidate_search(
        **arguments, oracle_audit=oracle
    ).to_dict()
    suite._validate_report(
        payload, expected["input_binding"], ("deterministic", "learned"), oracle
    )
    return payload, expected["input_binding"]


def test_actual_prefix_order_counts_and_exhaustive_oracle(arguments, evaluate_rows):
    calls, _ = evaluate_rows
    payload, _ = produce(arguments)
    assert payload["schema_version"] == search.SEARCH_STOP_SCHEMA
    assert calls == [
        "baseline",
        "narrow",
        "baseline",
        "narrow",
        "baseline",
        "near-limit",
        "narrow",
    ]
    for row in payload["arms"]:
        assert row["shortlist"] == ["narrow", "near-limit"]
        assert [r["candidate_id"] for r in row["candidate_outcomes"]] == [
            "near-limit",
            "narrow",
        ]
        assert row["execution"]["attempted_candidate_ids"] == ["narrow"]
        assert row["execution"]["unused_analysis_request_budget"] == 1
        assert row["candidate_outcomes"][0]["status"] == "not_attempted_after_stop"
        assert row["cost_accounting"]["candidate_analysis_request_count"] == 1
        assert [r["candidate_id"] for r in row["design_comparison"]["rows"]] == [
            "baseline",
            "narrow",
        ]
        assert row["oracle_audit"]["missed_feasible_count"] == 0
        assert row["oracle_audit"]["unrequested_feasible_count"] == 1
        assert row["oracle_audit"]["unrequested_feasible_candidate_ids"] == [
            "near-limit"
        ]
    assert payload["cost_accounting"]["online_full_analysis_request_count"] == 4
    assert payload["oracle"]["full_analysis_request_count"] == 3


def test_baseline_stop_preserves_pool_and_no_m2(arguments, evaluate_rows):
    calls, damage = evaluate_rows
    damage["baseline"] = 0.1
    payload, _ = produce(arguments, oracle=False)
    assert calls == ["baseline", "baseline"]
    for row in payload["arms"]:
        assert row["final_selection"]["candidate_id"] == "baseline"
        assert row["execution"]["attempted_candidate_ids"] == []
        assert row["execution"]["unused_analysis_request_budget"] == 2
        assert row["design_comparison"] is None
        assert (
            row["design_comparison_unavailable_reason"]
            == "stopped_before_candidate_evaluation"
        )
        assert row["oracle_audit"]["unrequested_feasible_count"] is None
        assert row["oracle_audit"]["unrequested_feasible_candidate_ids"] is None


def test_exhaustion_keeps_both_failed_limits_and_no_winner(arguments, evaluate_rows):
    calls, damage = evaluate_rows
    damage.update(narrow=0.4, **{"near-limit": 0.4})
    payload, _ = produce(arguments, oracle=False)
    assert len(calls) == 6
    for row in payload["arms"]:
        assert row["final_selection"] is None
        assert row["execution"]["termination_reason"] == "planned_shortlist_exhausted"
        assert row["execution"]["unused_analysis_request_budget"] == 0
        assert all(r["analysis_requested"] for r in row["candidate_outcomes"])


def test_unverified_baseline_stops_blocked_without_candidate_requests(
    arguments, evaluate_rows
):
    calls, damage = evaluate_rows
    damage["baseline"] = None
    payload, _ = produce(arguments, oracle=False)
    assert calls == ["baseline", "baseline"]
    assert payload["status"] == "blocked"
    for row in payload["arms"]:
        assert row["final_selection"] is None
        assert (
            row["execution"]["termination_reason"]
            == "baseline_verification_unavailable"
        )
        assert row["execution"]["attempted_candidate_ids"] == []
        assert row["cost_accounting"]["unknown_solver_execution_count"] == 1
        assert row["baseline"]["failure"]["exception_type"] == "RuntimeError"


def test_failed_attempt_keeps_unknown_execution_and_continues_prefix(
    arguments, evaluate_rows
):
    calls, damage = evaluate_rows
    damage["narrow"] = None
    payload, _ = produce(arguments, oracle=False)
    assert calls == ["baseline", "narrow", "near-limit"] * 2
    for row in payload["arms"]:
        assert row["final_selection"]["candidate_id"] == "near-limit"
        assert row["execution"]["attempted_candidate_ids"] == ["narrow", "near-limit"]
        assert row["execution"]["unused_analysis_request_budget"] == 0
        assert row["cost_accounting"]["total_analysis_request_count"] == 3
        assert row["cost_accounting"]["unknown_solver_execution_count"] == 1
        assert (
            row["candidate_outcomes"][1]["failure"]["exception_type"] == "RuntimeError"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_mode",
        "schema",
        "extra_execution",
        "wrong_reason",
        "prefix",
        "unused_budget",
        "suffix",
        "unattempted_failed",
        "hidden_request",
        "oracle_actual",
        "oracle_planned",
    ],
)
def test_rehashed_stop_contradictions_rejected(arguments, evaluate_rows, mutation):
    payload, binding = produce(arguments)
    first = payload["arms"][0]
    if mutation == "missing_mode":
        payload.pop("stop_mode")
    elif mutation == "schema":
        payload["schema_version"] = search.SEARCH_MATERIAL_HISTORY_SCHEMA
    elif mutation == "extra_execution":
        first["execution"]["fabricated"] = True
    elif mutation == "wrong_reason":
        first["execution"]["termination_reason"] = "planned_shortlist_exhausted"
    elif mutation == "prefix":
        first["execution"]["attempted_candidate_ids"] = ["near-limit"]
    elif mutation == "unused_budget":
        first["execution"]["unused_analysis_request_budget"] = 0
    elif mutation == "suffix":
        first["execution"]["unattempted_candidate_ids"] = []
    elif mutation == "unattempted_failed":
        first["candidate_outcomes"][0]["status"] = "execution_failed"
    elif mutation == "hidden_request":
        first["candidate_outcomes"][0]["analysis_requested"] = True
    elif mutation == "oracle_actual":
        first["oracle_audit"]["unrequested_feasible_count"] = 0
    elif mutation == "oracle_planned":
        first["oracle_audit"]["missed_feasible_count"] = 1
    rehash(payload)
    with pytest.raises((ValueError, KeyError)):
        suite._validate_report(payload, binding, ("deterministic", "learned"), True)


def test_rehashed_missing_frozen_binding_rejected(arguments, evaluate_rows):
    payload, binding = produce(arguments)
    binding.pop("stop_mode")
    with pytest.raises(ValueError, match="stop mode presence"):
        suite._validate_report(payload, binding, ("deterministic", "learned"), True)


def test_suite_forwards_mode_and_retains_mixed_case_versions(arguments, evaluate_rows):
    options = dict(arguments)
    options.pop("source_revision")
    stop = suite.FiberFrameCandidateSearchCase("stop", **options)
    legacy = replace(stop, case_id="legacy", stop_mode=None)
    report = suite.benchmark_fiber_frame_candidate_search_suite(
        (stop, legacy), source_revision=SOURCE, oracle_audit=False
    ).to_dict()
    assert report["schema_version"] == suite.STOP_SCHEMA_VERSION
    assert report["status"] == "ready", [r["failure"] for r in report["runs"]]
    for row in report["runs"]:
        comparison = row["comparison_report"]
        assert ("stop_mode" in comparison) is (row["case_id"] == "stop")
        assert comparison["schema_version"] == (
            search.SEARCH_STOP_SCHEMA
            if row["case_id"] == "stop"
            else search.SEARCH_MATERIAL_HISTORY_SCHEMA
        )


@pytest.mark.parametrize("mode", [False, 1, "", "all", "first_verified"])
def test_case_rejects_unsupported_mode(arguments, mode):
    options = dict(arguments)
    options.pop("source_revision")
    with pytest.raises(ValueError, match="stop_mode"):
        suite.FiberFrameCandidateSearchCase("invalid", **dict(options, stop_mode=mode))


def test_terminal_only_stop_uses_same_bundle_gate(arguments, evaluate_rows):
    # Explicitly remove synthetic history fields at the evaluator boundary.
    original = design._evaluate_design
    patch = pytest.MonkeyPatch()

    def terminal(*args, **kwargs):
        row = original(*args, **kwargs)
        for key in list(row):
            if "history" in key:
                row.pop(key)
        row["performance"] = {
            k: v for k, v in row["performance"].items() if k.startswith("terminal_")
        }
        return row

    patch.setattr(design, "_evaluate_design", terminal)
    try:
        options = deepcopy(arguments)
        options.pop("material_history_limits")
        options["history_limits"] = None
        payload, _ = produce(options)
        assert all(
            row["execution"]["stop_candidate_id"] == "baseline"
            for row in payload["arms"]
        )
    finally:
        patch.undo()
