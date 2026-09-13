"""Controlled prices/outcomes test cost reasoning, not physical solver accuracy."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark.rc_control_candidate_cost import (
    candidate_cost_optimality_audit,
)


def case():
    rows = [
        {
            "candidate_id": name,
            "material_estimate": {
                "total": price,
                "currency": "KRW",
                "scope": "test",
                "price_table_hash": "common",
            },
            "full_reference_verification_pass": True,
            "screens": {"limit": {"status": "pass"}},
        }
        for name, price in [
            ("baseline", 300),
            ("cheap", 100),
            ("middle", 200),
            ("costly", 400),
        ]
    ]
    plan = {
        "pool": deepcopy(rows),
        "price_table_hash": "common",
        "history_limits": {"limit": 1},
        "material_limits": {},
        "terminal_limits": None,
        "plans": {
            "price_order": {"shortlist": ["cheap"]},
            "learned_order": {"shortlist": ["middle"]},
        },
    }
    reports = {
        name: {
            "rows": deepcopy(selected),
            "price_table_hash": "common",
            "report_hash": name,
            "selected_candidate_id": winner,
        }
        for name, selected, winner in [
            ("price_order", rows[:2], "cheap"),
            ("learned_order", [rows[0], rows[2]], "middle"),
            ("exhaustive_oracle", rows, "cheap"),
        ]
    }
    return plan, reports


def test_more_expensive_missed_feasible_does_not_count_as_lost_cost_optimality():
    plan, reports = case()
    result = candidate_cost_optimality_audit(plan, reports)
    assert result["pool_minimum_feasible_candidate_ids"] == ["cheap"]
    assert result["pool_minimum_feasible_estimate"] == 100
    price, learned = result["arms"]["price_order"], result["arms"]["learned_order"]
    assert price["selected_minus_pool_minimum_estimate"] == 0
    assert price["missed_cheaper_feasible_count"] == 0
    assert price["matches_pool_minimum"] is True
    assert learned["selected_minus_pool_minimum_estimate"] == 100
    assert learned["missed_cheaper_feasible_candidate_ids"] == ["cheap"]
    assert learned["matches_pool_minimum"] is False
    assert not result["global_design_optimality_proved"]


@pytest.mark.parametrize("unknown", ["cheap", "costly", "baseline"])
@pytest.mark.parametrize("mutation", ["failed_replay", "partial_screens"])
def test_any_incomplete_oracle_row_keeps_minimum_and_gap_unknown(unknown, mutation):
    plan, reports = case()
    row = next(
        r for r in reports["exhaustive_oracle"]["rows"] if r["candidate_id"] == unknown
    )
    if mutation == "failed_replay":
        row["full_reference_verification_pass"] = False
    else:
        row["screens"] = {"different_limit": {"status": "fail"}}
    result = candidate_cost_optimality_audit(plan, reports)
    assert result["status"] == "oracle_incomplete"
    assert result["oracle_unverifiable_candidate_ids"] == [unknown]
    assert result["pool_minimum_feasible_estimate"] is None
    for arm in result["arms"].values():
        assert arm["selected_minus_pool_minimum_estimate"] is None
        assert arm["matches_pool_minimum"] is None
        assert arm["missed_cheaper_feasible_count"] is None


def test_no_oracle_is_distinct_from_no_feasible_candidate():
    plan, reports = case()
    no_oracle = {k: v for k, v in reports.items() if k != "exhaustive_oracle"}
    first = candidate_cost_optimality_audit(plan, no_oracle)
    assert first["status"] == "oracle_not_run"
    assert first["oracle_unverifiable_candidate_ids"] is None
    for row in reports["exhaustive_oracle"]["rows"]:
        row["screens"]["limit"]["status"] = "fail"
    second = candidate_cost_optimality_audit(plan, reports)
    assert second["status"] == "no_feasible_candidate"
    assert second["oracle_unverifiable_candidate_ids"] == []
    assert second["pool_minimum_feasible_candidate_ids"] is None


def test_missing_selection_is_not_zero_gap_or_an_invented_oracle_selection():
    plan, reports = case()
    reports["learned_order"]["selected_candidate_id"] = None
    result = candidate_cost_optimality_audit(plan, reports)["arms"]["learned_order"]
    assert result["status"] == "no_verified_selection"
    assert result["selected_estimate"] is None
    assert result["selected_minus_pool_minimum_estimate"] is None


def test_contradictory_later_outcome_cannot_certify_online_selection():
    plan, reports = case()
    reports["exhaustive_oracle"]["rows"][2]["screens"]["limit"]["status"] = "fail"
    arm = candidate_cost_optimality_audit(plan, reports)["arms"]["learned_order"]
    assert arm["status"] == "selection_not_confirmed_by_oracle"
    assert arm["selected_candidate_id"] == "middle"
    assert arm["selected_minus_pool_minimum_estimate"] is None


@pytest.mark.parametrize("zero", [False, True])
def test_baseline_is_included_and_all_equal_cost_winners_are_retained(zero):
    plan, reports = case()
    for row in [*plan["pool"], *(r for c in reports.values() for r in c["rows"])]:
        row["material_estimate"]["total"] = 0 if zero else 100
    result = candidate_cost_optimality_audit(plan, reports)
    assert result["baseline_included"] is True
    assert result["candidate_denominator"] == 4
    assert result["pool_minimum_feasible_candidate_ids"] == [
        "baseline",
        "cheap",
        "costly",
        "middle",
    ]
    assert all(a["matches_pool_minimum"] for a in result["arms"].values())


@pytest.mark.parametrize(
    "mutation",
    [
        "currency",
        "scope",
        "price_table_hash",
        "estimate",
        "missing",
        "duplicate",
        "selection",
    ],
)
def test_mismatched_inputs_cannot_produce_a_cost_gap(mutation):
    plan, reports = case()
    if mutation in ("currency", "scope", "price_table_hash"):
        plan["pool"][1]["material_estimate"][mutation] = "different"
    elif mutation == "estimate":
        reports["learned_order"]["rows"][1]["material_estimate"]["total"] = 1
    elif mutation == "missing":
        reports["exhaustive_oracle"]["rows"].pop()
    elif mutation == "duplicate":
        reports["exhaustive_oracle"]["rows"][-1] = reports["exhaustive_oracle"]["rows"][
            0
        ]
    else:
        reports["learned_order"]["selected_candidate_id"] = "cheap"
    with pytest.raises(ValueError):
        candidate_cost_optimality_audit(plan, reports)


@pytest.mark.parametrize("price", [True, -1, float("nan"), float("inf")])
def test_invalid_prices_are_not_comparable(price):
    plan, reports = case()
    plan["pool"][0]["material_estimate"]["total"] = price
    with pytest.raises(ValueError, match="finite nonnegative"):
        candidate_cost_optimality_audit(plan, reports)
