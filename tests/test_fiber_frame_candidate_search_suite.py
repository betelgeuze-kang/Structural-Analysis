"""Synthetic contract probes only; no physical solves or timing evidence."""

from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from tests.test_fiber_frame_candidate_search import (
    _model,
    math_training_artifact as _math_training_artifact,
)
from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


SOURCE = "a" * 40


def _rehash(payload, field="report_hash"):
    payload[field] = canonical_hash(
        {key: value for key, value in payload.items() if key != field}
    )


@pytest.fixture(scope="module")
def training():
    math_training_artifact = _math_training_artifact.__wrapped__()
    report = math_training_artifact.to_dict()
    report["cost_accounting"].update(
        data_generation_wall_ns=1000, training_wall_ns=2000
    )
    _rehash(report)
    return replace(math_training_artifact, _report_json=json.dumps(report))


def _case(training, case_id="case-a", width=0.4):
    return suite.FiberFrameCandidateSearchCase(
        case_id,
        _model(width),
        (
            design.FiberFrameDesignCandidate(
                "candidate-a", (design.FiberFrameSectionChange("RC1", width_m=0.39),)
            ),
        ),
        training,
        design.FiberFrameMaterialPrices(
            100.0, 1.0, "KRW", "2026-09-08", "synthetic test"
        ),
        design.FiberFrameTerminalLimits(0.01, 0.01),
        full_analysis_budget=2,
    )


def _binding(case):
    report = case.training.to_dict()
    payload = {
        "case_id": case.case_id,
        "source_revision": SOURCE,
        "baseline_model_checksum": case.baseline.canonical_model_checksum,
        "candidates": [
            {
                **asdict(candidate),
                "model_checksum": design.apply_fiber_frame_section_changes(
                    case.baseline, candidate
                ).canonical_model_checksum,
            }
            for candidate in case.candidates
        ],
        "configuration": asdict(case.config),
        "terminal_limits": asdict(case.terminal_limits),
        "price_basis": {
            **asdict(case.prices),
            "price_table_hash": case.prices.price_table_hash,
        },
        "full_analysis_budget": case.full_analysis_budget,
        "exploration_slots": case.exploration_slots,
        "policy_artifact_hash": case.training.policy.artifact_hash,
        "training_report_hash": report["report_hash"],
        "training_cost_accounting": report["cost_accounting"],
    }
    return json.loads(json.dumps(payload))


def _fake_report(case, order=("deterministic", "learned"), oracle=True, blocked=False):
    """Producer-shaped values exercise accounting, never numerical authority."""
    binding = _binding(case)
    pool = [
        {
            **row,
            "screening_status": "ready",
            "preanalysis_material_estimate": 90.0,
            "predicted_terminal_safe": True,
            "predicted_limit_ratio": 0.5,
            "prediction": None,
            "failure": None,
        }
        for row in binding["candidates"]
    ]
    shortlist = [pool[0]["candidate_id"]]
    frozen = canonical_hash(
        {
            "pool": pool,
            "shortlists": {name: shortlist for name in suite.STRATEGIES},
            "policy_hash": binding["policy_artifact_hash"],
        }
    )

    def analyzed(key, checksum, total):
        return {
            "candidate_id": key,
            "model_checksum": checksum,
            "status": "ready",
            "analysis_requested": True,
            "solver_executed": True,
            "full_reference_verification_pass": True,
            "terminal_limit_status": "fail" if blocked else "pass",
            "material_estimate": {"total": total},
            "performance": None,
            "result": None,
            "quantities": None,
            "failure": None,
        }

    baseline = analyzed("baseline", binding["baseline_model_checksum"], 100.0)
    analyzed_outcomes = [
        analyzed(row["candidate_id"], row["model_checksum"], 90.0) for row in pool
    ]
    outcomes = [
        row
        if row["candidate_id"] in shortlist
        else {
            **row,
            "analysis_requested": False,
            "solver_executed": False,
            "status": "not_shortlisted",
            "full_reference_verification_pass": False,
            "terminal_limit_status": "unavailable",
            "material_estimate": None,
        }
        for row in analyzed_outcomes
    ]
    oracle_rows = [deepcopy(baseline), *deepcopy(analyzed_outcomes)] if oracle else None
    arms = []
    for name in suite.STRATEGIES:
        learned = name == "learned"
        audit = search._audit_outcomes(pool, shortlist, oracle_rows)
        if not learned:
            audit.update(
                false_safe_count=None,
                false_safe_candidate_ids=None,
                predicted_safe_unverifiable_count=None,
                predicted_safe_unverifiable_candidate_ids=None,
                false_safe_applicability="strategy_makes_no_predicted_safety_claim",
            )
        cost = {
            "shared_pool_preparation_charged_wall_ns": 10,
            "inference_wall_ns": 5 if learned else 0,
            "inference_count": len(pool) if learned else 0,
            "shortlist_selection_wall_ns": 3,
            "final_selection_wall_ns": 4,
            "policy_setup_wall_ns": 6 if learned else 0,
            "full_reanalysis_wall_ns": 50 if learned else 100,
            "baseline_analysis_request_count": 1,
            "candidate_analysis_request_count": 1,
            "total_analysis_request_count": 2,
            "known_solver_execution_count": 2,
            "unknown_solver_execution_count": 0,
            "charged_online_wall_ns": 78 if learned else 117,
        }
        arms.append(
            {
                "strategy": name,
                "shortlist": shortlist.copy(),
                "ranking": [row["candidate_id"] for row in pool],
                "frozen_shortlist_hash": frozen,
                "baseline": deepcopy(baseline),
                "candidate_outcomes": deepcopy(outcomes),
                "final_selection": None if blocked else deepcopy(outcomes[0]),
                "oracle_audit": audit,
                "cost_accounting": cost,
            }
        )
    historical = binding["training_cost_accounting"]
    report = {
        "schema_version": "fiber-frame-candidate-search-comparison.v2",
        "identity_profile": learning.PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": learning.CANDIDATE_FEATURE_PROFILE,
        "status": "blocked" if blocked else "ready",
        "source_revision": SOURCE,
        "configuration": binding["configuration"],
        "terminal_limits": binding["terminal_limits"],
        "price_basis": binding["price_basis"],
        "policy_artifact_hash": binding["policy_artifact_hash"],
        "training_report_hash": binding["training_report_hash"],
        "fixed_full_analysis_budget_per_arm": case.full_analysis_budget,
        "exploration_slots": case.exploration_slots,
        "execution_order": list(order),
        "baseline_included_in_budget": True,
        "declared_candidate_count": len(pool),
        "candidate_pool": pool,
        "frozen_shortlist_hash": frozen,
        "arms": arms,
        "oracle": {
            "executed": oracle,
            "labels_available_to_online_selection": False,
            "rows": oracle_rows,
            "wall_ns": 200 if oracle else None,
            "baseline_analysis_request_count": 1 if oracle else None,
            "candidate_analysis_request_count": len(pool) if oracle else None,
            "full_analysis_request_count": len(pool) + 1 if oracle else None,
            "known_solver_execution_count": len(pool) + 1 if oracle else None,
            "unknown_solver_execution_count": 0 if oracle else None,
        },
        "cost_accounting": {
            "data_generation_wall_ns": historical["data_generation_wall_ns"],
            "training_wall_ns": historical["training_wall_ns"],
            "training_full_analysis_request_count": historical[
                "full_analysis_request_count"
            ],
            "actual_shared_preparation_wall_ns": 10,
            "online_full_analysis_request_count": 4,
            "total_analysis_request_count_including_training_and_oracle": (
                historical["full_analysis_request_count"]
                + 4
                + (len(pool) + 1 if oracle else 0)
            ),
            "actual_comparison_wall_ns_including_oracle": 500,
            "io_wall_ns": None,
            "peak_memory_bytes": None,
        },
        "observed_comparison": {
            "deterministic_minus_learned_charged_online_wall_ns": 39,
            "learned_verified_scoped_material_cost_not_worse": not blocked,
            "projected_reuses_to_amortize_data_and_training": None if blocked else 77,
            "break_even_is_observed_execution": False,
        },
    }
    _rehash(report)
    return report


def _result(report):
    return search.FiberFrameCandidateSearchResult(report["status"], json.dumps(report))


def _runner(baseline, candidates, **kwargs):
    case = suite.FiberFrameCandidateSearchCase(
        "runner-copy",
        baseline,
        candidates,
        kwargs["training"],
        kwargs["prices"],
        kwargs["terminal_limits"],
        kwargs["config"],
        kwargs["full_analysis_budget"],
        kwargs["exploration_slots"],
    )
    return _result(_fake_report(case, kwargs["arm_order"], kwargs["oracle_audit"]))


class _Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 10_000
        return self.value


def test_round_major_schedule_warmup_parity_and_actual_total_costs(training):
    cases = [_case(training), _case(training, "case-b", 0.41)]
    calls = []

    def record(baseline, candidates, **kwargs):
        calls.append((baseline.canonical_model_checksum, kwargs["arm_order"]))
        return _runner(baseline, candidates, **kwargs)

    result = suite.benchmark_fiber_frame_candidate_search_suite(
        cases,
        source_revision=SOURCE,
        repetitions=4,
        warmups=1,
        runner=record,
        clock_ns=_Clock(),
    )
    report = result.to_dict()
    assert report["status"] == "ready", report["runs"]
    expected = [
        (
            case.baseline.canonical_model_checksum,
            suite.STRATEGIES if (round_ + i) % 2 == 0 else suite.STRATEGIES[::-1],
        )
        for rounds in (1, 4)
        for round_ in range(rounds)
        for i, case in enumerate(cases)
    ]
    assert calls == expected
    assert [
        (run["phase"], run["repetition"], run["case_id"]) for run in report["runs"]
    ] == [
        (phase, round_, case.case_id)
        for phase, rounds in (("warmup", 1), ("measured", 4))
        for round_ in range(rounds)
        for case in cases
    ]
    costs = report["cost_accounting"]
    assert costs["historical_training_analysis_request_count"] == 4
    assert costs["historical_data_generation_wall_ns"] == 1000
    assert costs["historical_training_wall_ns"] == 2000
    assert costs["phases"]["warmup"]["total_analysis_request_count"] == 12
    assert costs["phases"]["measured"]["total_analysis_request_count"] == 48
    assert (
        costs["total_analysis_request_count_including_training_warmups_and_oracles"]
        == 64
    )
    for summary in report["case_summaries"]:
        assert summary["paired_deterministic_minus_learned_wall_ns"]["count"] == 4
        assert summary["paired_deterministic_minus_learned_wall_ns"]["median"] == 39
        assert summary["projected_reuses_to_amortize_this_artifact"] is None
        audit = summary["measured_oracle_audit"]
        assert (
            audit["scope"]
            == "candidate_observations_across_repetitions_not_unique_physical_candidates"
        )
        assert audit["declared_candidate_observations"] == 4
        assert audit["validated_candidate_observations"] == 4
        assert audit["by_strategy"]["learned"]["oracle_verified_candidate_count"] == 4
        assert audit["by_strategy"]["deterministic"]["false_safe_count"] is None
    assert report["claims"]["local_timing_evidence_eligible"] is False
    detached = result.to_dict()
    detached["runs"].clear()
    assert len(result.to_dict()["runs"]) == 10


def test_all_case_snapshots_and_per_call_training_are_isolated(training):
    cases = [_case(training), _case(training, "case-b", 0.41)]
    expected_checksums = [case.baseline.canonical_model_checksum for case in cases] * 2
    expected_training_json = training._report_json
    observed = []

    def mutate(baseline, candidates, **kwargs):
        observed.append(
            (baseline.canonical_model_checksum, kwargs["training"]._report_json)
        )
        result = _runner(baseline, candidates, **kwargs)
        baseline.sections[0]["width_m"] = 0.9
        object.__setattr__(kwargs["training"], "_report_json", "{}")
        cases[1].baseline.sections[0]["width_m"] = 0.8
        return result

    report = suite.benchmark_fiber_frame_candidate_search_suite(
        cases, source_revision=SOURCE, runner=mutate, clock_ns=_Clock()
    ).to_dict()
    assert [row[0] for row in observed] == expected_checksums
    assert [row[1] for row in observed] == [expected_training_json] * 4
    assert report["status"] == "ready", report["runs"]
    assert training._report_json == expected_training_json


@pytest.mark.parametrize("failure_kind", ["exception", "malformed"])
@pytest.mark.parametrize("failed_call", [0, 1])
def test_failed_attempt_keeps_elapsed_unknown_requests_and_other_runs(
    training, failure_kind, failed_call
):
    calls = 0

    def fail_one(baseline, candidates, **kwargs):
        nonlocal calls
        index, calls = calls, calls + 1
        if index == failed_call:
            if failure_kind == "exception":
                raise RuntimeError(
                    "failure after an unknown number of physical requests"
                )
            report = _runner(baseline, candidates, **kwargs).to_dict()
            report["source_revision"] = "b" * 40
            _rehash(report)
            return _result(report)
        return _runner(baseline, candidates, **kwargs)

    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)],
        source_revision=SOURCE,
        warmups=1,
        runner=fail_one,
        clock_ns=_Clock(),
    ).to_dict()
    assert calls == 3
    assert report["status"] == "incomplete"
    assert len(report["runs"]) == 3
    failed = report["runs"][failed_call]
    assert failed["report_contract_pass"] is False
    assert failed["observed_attempt_wall_ns"] == 10_000
    assert (failed["comparison_report"] is None) == (failure_kind == "exception")
    phase = report["cost_accounting"]["phases"][
        "warmup" if failed_call == 0 else "measured"
    ]
    assert phase["unknown_request_comparisons"] == 1
    assert phase["total_analysis_request_count"] is None
    assert phase["validated_online_request_subtotal"] == (0 if failed_call == 0 else 4)
    assert (
        report["cost_accounting"][
            "total_analysis_request_count_including_training_warmups_and_oracles"
        ]
        is None
    )
    assert (
        report["case_summaries"][0]["all_warmup_and_measured_attempts_ready"] is False
    )
    assert (
        report["case_summaries"][0]["projected_reuses_to_amortize_this_artifact"]
        is None
    )


def test_blocked_pair_timings_remain_in_distribution(training):
    calls = 0

    def block_one(baseline, candidates, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _result(
                _fake_report(
                    _case(kwargs["training"]), kwargs["arm_order"], blocked=True
                )
            )
        return _runner(baseline, candidates, **kwargs)

    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)], source_revision=SOURCE, runner=block_one, clock_ns=_Clock()
    ).to_dict()
    summary = report["case_summaries"][0]
    assert report["status"] == "incomplete"
    assert summary["valid_report_count"] == 2
    assert summary["ready_comparison_count"] == 1
    assert summary["paired_deterministic_minus_learned_wall_ns"]["count"] == 2
    assert summary["charged_online_wall_ns_by_strategy"]["learned"]["count"] == 2
    assert (
        summary["learned_verified_material_objective_not_worse_in_every_pair"] is False
    )
    assert summary["projected_reuses_to_amortize_this_artifact"] is None
    assert (
        report["cost_accounting"]["phases"]["measured"]["total_analysis_request_count"]
        == 12
    )


def test_distinct_training_reports_are_each_charged_once(training):
    changed = training.to_dict()
    changed["cost_accounting"]["data_generation_wall_ns"] = 1500
    _rehash(changed)
    second = replace(training, _report_json=json.dumps(changed))
    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training), _case(second, "case-b", 0.41)],
        source_revision=SOURCE,
        runner=_runner,
        clock_ns=_Clock(),
    ).to_dict()
    cost = report["cost_accounting"]
    assert len(cost["training_artifacts_charged_once"]) == 2
    assert cost["historical_data_generation_wall_ns"] == 2500
    assert cost["historical_training_wall_ns"] == 4000
    assert cost["historical_training_analysis_request_count"] == 8
    assert (
        cost["total_analysis_request_count_including_training_warmups_and_oracles"]
        == 32
    )


@pytest.mark.parametrize("injection", ["runner", "clock"])
def test_each_injection_kind_disqualifies_timing_and_projection(
    training, monkeypatch, injection
):
    options = {"runner": _runner}
    if injection == "clock":
        monkeypatch.setattr(suite, "compare_fiber_frame_candidate_search", _runner)
        options = {"clock_ns": _Clock()}
    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)], source_revision=SOURCE, **options
    ).to_dict()
    assert report["status"] == "ready"
    assert report["claims"]["local_timing_evidence_eligible"] is False
    assert (
        report["case_summaries"][0]["projected_reuses_to_amortize_this_artifact"]
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "configuration",
        "prices",
        "limits",
        "changes",
        "model",
        "baseline",
        "policy",
        "training",
        "order",
        "shortlist",
        "count",
        "charge",
        "total_count",
        "historical_cost",
        "oracle_count",
        "quality",
        "audit",
        "difference",
        "identity_profile",
        "feature_profile",
        "solver_status",
        "shared_preparation",
        "core_wall",
    ],
)
def test_rehashed_comparison_mismatch_is_rejected(training, mutation):
    case = _case(training)
    report = _fake_report(case)
    if mutation == "source":
        report["source_revision"] = "b" * 40
    elif mutation == "configuration":
        report["configuration"]["load_steps"] += 1
    elif mutation == "prices":
        report["price_basis"]["currency"] = "USD"
    elif mutation == "limits":
        report["terminal_limits"]["maximum_translation_m"] *= 2
    elif mutation == "changes":
        report["candidate_pool"][0]["changes"][0]["width_m"] = 0.38
    elif mutation == "model":
        report["candidate_pool"][0]["model_checksum"] = "sha256:" + "c" * 64
    elif mutation == "baseline":
        report["arms"][0]["baseline"]["model_checksum"] = "sha256:" + "c" * 64
    elif mutation == "policy":
        report["policy_artifact_hash"] = "sha256:" + "c" * 64
    elif mutation == "training":
        report["training_report_hash"] = "sha256:" + "c" * 64
    elif mutation == "order":
        report["execution_order"].reverse()
    elif mutation == "shortlist":
        report["arms"][0]["shortlist"] = []
    elif mutation == "count":
        report["arms"][0]["cost_accounting"]["total_analysis_request_count"] = 3
    elif mutation == "charge":
        report["arms"][0]["cost_accounting"]["charged_online_wall_ns"] += 1
    elif mutation == "total_count":
        report["cost_accounting"]["online_full_analysis_request_count"] += 1
    elif mutation == "historical_cost":
        report["cost_accounting"]["training_wall_ns"] += 1
    elif mutation == "oracle_count":
        report["oracle"]["full_analysis_request_count"] += 1
    elif mutation == "quality":
        report["observed_comparison"][
            "learned_verified_scoped_material_cost_not_worse"
        ] = False
    elif mutation == "audit":
        report["arms"][1]["oracle_audit"]["missed_feasible_count"] += 1
    elif mutation == "difference":
        report["observed_comparison"][
            "deterministic_minus_learned_charged_online_wall_ns"
        ] += 1
    elif mutation in ("identity_profile", "feature_profile"):
        report[mutation] = "old-profile.v1"
    elif mutation == "solver_status":
        report["arms"][0]["baseline"]["solver_executed"] = "unknown"
        report["arms"][0]["cost_accounting"]["known_solver_execution_count"] = 1
    elif mutation == "shared_preparation":
        report["cost_accounting"]["actual_shared_preparation_wall_ns"] += 1
    elif mutation == "core_wall":
        report["cost_accounting"]["actual_comparison_wall_ns_including_oracle"] = 0
    _rehash(report)
    with pytest.raises((ValueError, TypeError, KeyError)):
        suite._validate_report(report, _binding(case), suite.STRATEGIES, True)


def test_oracle_disabled_keeps_denominator_unavailable(training):
    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)],
        source_revision=SOURCE,
        oracle_audit=False,
        runner=_runner,
        clock_ns=_Clock(),
    ).to_dict()
    assert report["status"] == "ready", report["runs"]
    cost = report["cost_accounting"]
    assert cost["phases"]["measured"]["validated_oracle_request_subtotal"] == 0
    assert (
        cost["total_analysis_request_count_including_training_warmups_and_oracles"]
        == 12
    )
    for run in report["runs"]:
        assert run["comparison_report"]["oracle"]["rows"] is None


@pytest.mark.parametrize(
    "key",
    [
        "baseline_analysis_request_count",
        "candidate_analysis_request_count",
        "known_solver_execution_count",
        "unknown_solver_execution_count",
    ],
)
def test_disabled_oracle_cannot_carry_rehashed_count_credit(training, key):
    case = _case(training)
    report = _fake_report(case, oracle=False)
    report["oracle"][key] = 1
    _rehash(report)
    with pytest.raises((ValueError, TypeError, KeyError)):
        suite._validate_report(report, _binding(case), suite.STRATEGIES, False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_executed", True),
        ("full_reference_verification_pass", True),
        ("result", {"hidden": "physical solve"}),
    ],
)
def test_nonshortlisted_candidate_cannot_hide_solver_execution(training, field, value):
    case = _case(training)
    case = replace(
        case,
        candidates=(
            *case.candidates,
            design.FiberFrameDesignCandidate(
                "candidate-b", (design.FiberFrameSectionChange("RC1", width_m=0.405),)
            ),
        ),
    )
    report = _fake_report(case)
    suite._validate_report(report, _binding(case), suite.STRATEGIES, True)
    report["arms"][0]["candidate_outcomes"][1][field] = value
    _rehash(report)
    with pytest.raises(ValueError):
        suite._validate_report(report, _binding(case), suite.STRATEGIES, True)


def test_individually_valid_reports_cannot_change_frozen_pool_between_attempts(
    training,
):
    calls = 0

    def drifting(baseline, candidates, **kwargs):
        nonlocal calls
        calls += 1
        report = _runner(baseline, candidates, **kwargs).to_dict()
        report["candidate_pool"][0]["prediction"] = {"test_observation": calls}
        frozen = canonical_hash(
            {
                "pool": report["candidate_pool"],
                "shortlists": {
                    arm["strategy"]: arm["shortlist"] for arm in report["arms"]
                },
                "policy_hash": report["policy_artifact_hash"],
            }
        )
        report["frozen_shortlist_hash"] = frozen
        for arm in report["arms"]:
            arm["frozen_shortlist_hash"] = frozen
        _rehash(report)
        return _result(report)

    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)], source_revision=SOURCE, runner=drifting, clock_ns=_Clock()
    ).to_dict()
    assert calls == 2
    assert [row["report_contract_pass"] for row in report["runs"]] == [True, False]
    assert "frozen" in report["runs"][1]["failure"]["detail"]
    assert (
        report["case_summaries"][0]["paired_deterministic_minus_learned_wall_ns"][
            "count"
        ]
        == 1
    )
    assert (
        report["cost_accounting"]["phases"]["measured"]["total_analysis_request_count"]
        is None
    )


def test_nonfinite_report_cannot_poison_retained_suite_failures(training):
    calls = 0

    def nonfinite_once(baseline, candidates, **kwargs):
        nonlocal calls
        calls += 1
        result = _runner(baseline, candidates, **kwargs)
        if calls == 1:
            payload = result.to_dict()
            payload["cost_accounting"]["actual_comparison_wall_ns_including_oracle"] = (
                float("nan")
            )
            return _result(payload)
        return result

    result = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)],
        source_revision=SOURCE,
        runner=nonfinite_once,
        clock_ns=_Clock(),
    )
    report = result.to_dict()
    assert calls == 2
    assert report["status"] == "incomplete"
    assert [row["report_contract_pass"] for row in report["runs"]] == [False, True]
    assert report["runs"][0]["comparison_report"] is None
    assert report["runs"][0]["observed_attempt_wall_ns"] == 10_000
    assert (
        report["cost_accounting"]["phases"]["measured"]["total_analysis_request_count"]
        is None
    )
    assert json.dumps(report, allow_nan=False)


def test_actual_core_report_contract_integrates_with_suite_without_physics(
    training, monkeypatch
):
    calls = []

    def blocked_design(key, model, *_args):
        calls.append((key, model.canonical_model_checksum))
        return {
            "candidate_id": key,
            "model_checksum": model.canonical_model_checksum,
            "status": "blocked",
            "solver_executed": False,
            "full_reference_verification_pass": False,
            "result": None,
            "terminal_limit_status": "unavailable",
            "material_estimate": None,
            "performance": None,
            "quantities": None,
            "failure": "synthetic block",
        }

    def forbidden(*_args, **_kwargs):
        pytest.fail("integration contract test must not run physical analysis")

    monkeypatch.setattr(design, "_evaluate_design", blocked_design)
    monkeypatch.setattr(design.public_api, "analyze_public_rc_fiber_frame", forbidden)
    report = suite.benchmark_fiber_frame_candidate_search_suite(
        [_case(training)],
        source_revision=SOURCE,
        runner=search.compare_fiber_frame_candidate_search,
    ).to_dict()
    assert report["status"] == "incomplete"
    assert len(calls) == 12
    assert all(row["report_contract_pass"] for row in report["runs"]), report["runs"]
    assert [row["execution_order"] for row in report["runs"]] == [
        list(suite.STRATEGIES),
        list(suite.STRATEGIES[::-1]),
    ]
    assert (
        report["cost_accounting"]["phases"]["measured"]["total_analysis_request_count"]
        == 12
    )
    assert report["case_summaries"][0]["valid_report_count"] == 2
    assert report["case_summaries"][0]["ready_comparison_count"] == 0


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("positive", 77),
        ("zero", None),
        ("negative", None),
        ("quality_failure", None),
        ("warmup_failure", None),
    ],
)
def test_projection_arithmetic_requires_positive_complete_quality_pairs(
    training, scenario, expected
):
    """Pure summary arithmetic; injected=False here is not timing evidence."""
    case = _case(training)
    report = _fake_report(case)
    if scenario in ("zero", "negative"):
        added = 39 if scenario == "zero" else 49
        report["arms"][1]["cost_accounting"]["charged_online_wall_ns"] += added
        report["arms"][1]["cost_accounting"]["full_reanalysis_wall_ns"] += added
        report["observed_comparison"][
            "deterministic_minus_learned_charged_online_wall_ns"
        ] -= added
    if scenario == "quality_failure":
        report["observed_comparison"][
            "learned_verified_scoped_material_cost_not_worse"
        ] = False
    runs = [
        {
            "case_id": case.case_id,
            "phase": "measured",
            "report_contract_pass": True,
            "status": "ready",
            "comparison_report": deepcopy(report),
        }
        for _ in range(2)
    ]
    if scenario == "warmup_failure":
        runs.insert(
            0,
            {
                "case_id": case.case_id,
                "phase": "warmup",
                "report_contract_pass": False,
                "status": "error",
            },
        )
    summary = suite._case_summary(_binding(case), runs, 2, False)
    assert summary["projected_reuses_to_amortize_this_artifact"] == expected
    assert summary["paired_deterministic_minus_learned_wall_ns"]["count"] == 2
    if scenario == "positive":
        assert summary["paired_deterministic_minus_learned_wall_ns"]["median"] == 39


@pytest.mark.parametrize("repetitions", [True, False, 1, 3, 33, -2, 2.0])
def test_invalid_repetitions_are_rejected_before_runner(training, repetitions):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid repetition declarations must not execute")

    with pytest.raises(ValueError, match="repetitions"):
        suite.benchmark_fiber_frame_candidate_search_suite(
            [_case(training)],
            source_revision=SOURCE,
            repetitions=repetitions,
            runner=forbidden,
        )
