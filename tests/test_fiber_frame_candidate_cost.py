"""Finite-pool cost controls, without a solver or a new physical claim."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from structural_analysis.benchmark.fiber_frame_candidate_cost import (
    audit_fiber_frame_candidate_pool_cost,
)
from structural_analysis.benchmark.fiber_frame_design import (
    QUANTITY_SCOPE,
    FiberFrameMaterialPrices,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _seal(report):
    report["report_hash"] = canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )
    return report


def _row(candidate_id, total, price_hash, *, requested=True):
    return {
        "candidate_id": candidate_id,
        "analysis_requested": requested,
        "full_reference_verification_pass": requested,
        "terminal_limit_status": "pass" if requested else "unavailable",
        "material_estimate": {
            "total": total,
            "currency": "KRW",
            "scope": QUANTITY_SCOPE,
            "price_table_hash": price_hash,
        }
        if requested
        else None,
    }


def _arm(name, shortlist, totals, price_hash, *, attempted=None):
    attempted = shortlist if attempted is None else attempted
    baseline = _row("baseline", totals["baseline"], price_hash)
    outcomes = [
        _row(key, totals[key], price_hash, requested=key in attempted)
        for key in ("cheap", "middle", "costly")
    ]
    selected = min(
        [baseline, *(row for row in outcomes if row["analysis_requested"])],
        key=lambda row: row["material_estimate"]["total"],
    )
    arm = {
        "strategy": name,
        "shortlist": shortlist,
        "baseline": baseline,
        "candidate_outcomes": outcomes,
        "final_selection": selected,
    }
    if attempted != shortlist:
        arm["execution"] = {"attempted_candidate_ids": attempted}
    return arm


def _case():
    prices = FiberFrameMaterialPrices(100, 1, "KRW", "2026-09-27", "synthetic test")
    totals = {"baseline": 300, "cheap": 100, "middle": 200, "costly": 400}
    return _seal(
        {
            "schema_version": "fiber-frame-candidate-search-comparison.v2",
            "price_basis": {
                **asdict(prices),
                "price_table_hash": prices.price_table_hash,
            },
            "candidate_pool": [
                {
                    "candidate_id": key,
                    "screening_status": "ready",
                    "preanalysis_material_estimate": totals[key],
                }
                for key in ("cheap", "middle", "costly")
            ],
            "arms": [
                _arm("deterministic", ["cheap"], totals, prices.price_table_hash),
                _arm("learned", ["middle"], totals, prices.price_table_hash),
            ],
            "oracle": {
                "executed": True,
                "labels_available_to_online_selection": False,
                "rows": [
                    _row(key, total, prices.price_table_hash)
                    for key, total in totals.items()
                ],
            },
        }
    )


def test_cost_audit_separates_missed_feasibility_from_lost_cost_optimality():
    report = _case()
    frozen = deepcopy(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    assert report == frozen
    assert audit["candidate_denominator"] == 4
    assert audit["source_report_hash"] == report["report_hash"]
    assert audit["baseline_included"] is True
    assert audit["price_table_hash"] == report["price_basis"]["price_table_hash"]
    assert audit["pool_minimum_feasible_candidate_ids"] == ["cheap"]
    det, learned = audit["arms"]["deterministic"], audit["arms"]["learned"]
    assert {
        row["candidate_id"]
        for row in report["oracle"]["rows"]
        if row["candidate_id"] not in {"baseline", *report["arms"][0]["shortlist"]}
        and row["terminal_limit_status"] == "pass"
    } == {"middle", "costly"}
    assert det["selected_minus_pool_minimum_estimate"] == 0
    assert det["missed_cheaper_feasible_candidate_ids"] == []
    assert learned["selected_minus_pool_minimum_estimate"] == 100
    assert learned["missed_cheaper_feasible_candidate_ids"] == ["cheap"]
    assert learned["unrequested_cheaper_feasible_candidate_ids"] == ["cheap"]
    assert audit["global_design_optimality_proved"] is False


@pytest.mark.parametrize("unknown", ["baseline", "cheap", "costly"])
def test_any_unknown_oracle_outcome_keeps_cost_gap_unknown(unknown):
    report = _case()
    row = next(
        row for row in report["oracle"]["rows"] if row["candidate_id"] == unknown
    )
    row["full_reference_verification_pass"] = False
    _seal(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    assert audit["status"] == "oracle_incomplete"
    assert audit["oracle_unverifiable_candidate_ids"] == [unknown]
    assert audit["pool_minimum_feasible_estimate"] is None
    for arm in audit["arms"].values():
        assert arm["selected_minus_pool_minimum_estimate"] is None
        assert arm["missed_cheaper_feasible_count"] is None
        assert arm["unrequested_cheaper_feasible_count"] is None


def test_no_oracle_and_known_failed_limit_are_distinct():
    report = _case()
    report["oracle"].update(executed=False, rows=None)
    _seal(report)
    absent = audit_fiber_frame_candidate_pool_cost(report)
    assert absent["status"] == "oracle_not_run"
    assert absent["oracle_unverifiable_candidate_ids"] is None
    assert absent["arms"]["learned"]["selected_minus_pool_minimum_estimate"] is None
    report = _case()
    report["oracle"]["rows"][-1]["terminal_limit_status"] = "fail"
    _seal(report)
    known = audit_fiber_frame_candidate_pool_cost(report)
    assert known["status"] == "complete"
    assert known["oracle_unverifiable_candidate_ids"] == []
    assert known["pool_minimum_feasible_estimate"] == 100


@pytest.mark.parametrize(
    "mutation", ["declared_price", "currency", "scope", "hash", "total", "pool_total"]
)
def test_mismatched_common_prices_and_candidate_estimates_are_rejected(mutation):
    report = _case()
    if mutation == "declared_price":
        report["price_basis"]["concrete_per_m3"] = 101
    elif mutation == "pool_total":
        report["candidate_pool"][0]["preanalysis_material_estimate"] = 99
    else:
        value = report["oracle"]["rows"][1]["material_estimate"]
        value[mutation if mutation != "hash" else "price_table_hash"] = {
            "currency": "USD",
            "scope": "wrong",
            "hash": "wrong",
            "total": 99,
        }[mutation]
    _seal(report)
    with pytest.raises(ValueError, match="price|estimate"):
        audit_fiber_frame_candidate_pool_cost(report)


def test_complete_oracle_cannot_certify_a_selection_it_contradicts():
    report = _case()
    report["oracle"]["rows"][2]["terminal_limit_status"] = "fail"
    _seal(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    arm = audit["arms"]["learned"]
    assert audit["status"] == "complete"
    assert arm["status"] == "selection_not_confirmed_by_oracle"
    assert arm["selected_candidate_id"] == "middle"
    assert arm["selected_minus_pool_minimum_estimate"] is None
    assert arm["missed_cheaper_feasible_candidate_ids"] is None


def test_baseline_and_zero_cost_ties_are_included_without_a_ratio():
    report = _case()
    for row in report["candidate_pool"]:
        row["preanalysis_material_estimate"] = 0
    for arm in report["arms"]:
        arm["baseline"]["material_estimate"]["total"] = 0
        for row in arm["candidate_outcomes"]:
            if row["material_estimate"] is not None:
                row["material_estimate"]["total"] = 0
        arm["final_selection"]["material_estimate"]["total"] = 0
        arm["final_selection"] = arm["baseline"]
    for row in report["oracle"]["rows"]:
        row["material_estimate"]["total"] = 0
    _seal(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    assert audit["pool_minimum_feasible_candidate_ids"] == [
        "baseline",
        "cheap",
        "costly",
        "middle",
    ]
    assert all(arm["matches_pool_minimum"] for arm in audit["arms"].values())
    assert all(
        arm["missed_cheaper_feasible_count"] == 0 for arm in audit["arms"].values()
    )


def test_stop_mode_separates_planned_shortlist_from_attempted_prefix():
    report = _case()
    report["schema_version"] = "fiber-frame-candidate-search-comparison.v5"
    report["stop_mode"] = "first_verified_feasible"
    prices = report["price_basis"]["price_table_hash"]
    totals = {"baseline": 300, "cheap": 100, "middle": 200, "costly": 400}
    report["arms"] = [
        _arm("deterministic", ["cheap", "middle"], totals, prices, attempted=["cheap"]),
        _arm("learned", ["middle", "cheap"], totals, prices, attempted=["middle"]),
    ]
    for arm in report["arms"]:
        arm["baseline"]["terminal_limit_status"] = "fail"
    report["oracle"]["rows"][0]["terminal_limit_status"] = "fail"
    _seal(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    learned = audit["arms"]["learned"]
    assert learned["selected_minus_pool_minimum_estimate"] == 100
    assert learned["missed_cheaper_feasible_candidate_ids"] == []
    assert learned["unrequested_cheaper_feasible_candidate_ids"] == ["cheap"]


def test_requested_material_history_must_be_verified_for_every_oracle_row():
    report = _case()
    report["schema_version"] = "fiber-frame-candidate-search-comparison.v4"
    report["history_limits"] = {"maximum_translation_m": 1}
    report["material_history_limits"] = {"maximum_steel_accumulated_plastic_strain": 1}
    for arm in report["arms"]:
        for row in [arm["baseline"], *arm["candidate_outcomes"]]:
            if row["analysis_requested"]:
                row.update(
                    full_history_verification_pass=True,
                    history_limit_status="pass",
                    full_material_history_verification_pass=True,
                    material_history_limit_status="pass",
                )
    for row in report["oracle"]["rows"]:
        row.update(
            full_history_verification_pass=True,
            history_limit_status="pass",
            full_material_history_verification_pass=True,
            material_history_limit_status="pass",
        )
    report["oracle"]["rows"][-1]["full_material_history_verification_pass"] = False
    _seal(report)
    audit = audit_fiber_frame_candidate_pool_cost(report)
    assert audit["status"] == "oracle_incomplete"
    assert audit["oracle_unverifiable_candidate_ids"] == ["costly"]


def test_online_selection_must_match_its_attempted_verified_rows():
    report = _case()
    report["arms"][1]["final_selection"] = report["oracle"]["rows"][1]
    _seal(report)
    with pytest.raises(ValueError, match="selection"):
        audit_fiber_frame_candidate_pool_cost(report)


def test_changed_report_is_rejected_before_cost_arithmetic():
    report = _case()
    report["oracle"]["rows"][1]["material_estimate"]["total"] = 50
    with pytest.raises(ValueError, match="source report hash"):
        audit_fiber_frame_candidate_pool_cost(report)
