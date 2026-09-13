"""Cost bounds preserve cheaper/tied candidates and require verified incumbents."""

from copy import deepcopy
import json

import pytest

from tests import test_rc_control_layout_search as layout_search_tests
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_cost_dominance import (
    layout_cost_dominance,
)

actual = layout_search_tests.actual
inputs = layout_search_tests.inputs


def original(actual):
    root, _, _ = actual
    plan = json.loads((root / "plan.json").read_bytes())
    rows = json.loads((root / "exhaustive_oracle/comparison.json").read_bytes())["rows"]
    return plan, {r["candidate_id"]: r for r in rows}


def rehash(plan):
    plan["plan_hash"] = study._sha(
        study._bytes({k: v for k, v in plan.items() if k != "plan_hash"})
    )


def test_actual_reference_incumbent_retains_cheaper_uncomputed_candidate(actual):
    plan, rows = original(actual)
    result = layout_cost_dominance(plan, [rows["baseline"]])
    assert result["incumbent_candidate_id"] == "baseline"
    assert result["cost_dominated_unevaluated_candidate_ids"] == ["large"]
    assert result["retained_unevaluated_candidate_ids"] == ["small"]
    assert result["unevaluated_physical_feasibility"] == "unknown"
    assert result["global_cost_optimality_proved"] is False
    assert result["execution_skips_performed"] == 0
    result2 = layout_cost_dominance(plan, [rows["baseline"], rows["small"]])
    assert result2["incumbent_candidate_id"] == "small"
    assert result2["cost_dominated_unevaluated_candidate_ids"] == ["large"]
    assert rows["large"]["selection_eligible"] is True  # Expensive is not infeasible.


def test_no_incumbent_cannot_prune_from_predictions(actual):
    plan, _ = original(actual)
    result = layout_cost_dominance(plan, [])
    assert result["incumbent_candidate_id"] is None
    assert result["cost_dominated_unevaluated_candidate_ids"] == []
    assert set(result["retained_unevaluated_candidate_ids"]) == {
        "baseline",
        "small",
        "large",
    }


@pytest.mark.parametrize(
    "reason",
    ["verification", "limit", "empty_work", "zero_work", "unknown_work", "selection"],
)
def test_unverified_or_ineligible_rows_do_not_establish_bound(actual, reason):
    plan, rows = original(actual)
    row = rows["baseline"]
    if reason == "verification":
        row["full_reference_verification_pass"] = False
    elif reason == "limit":
        next(iter(row["screens"].values()))["status"] = "fail"
    elif reason == "empty_work":
        row["invocations"] = []
    elif reason == "unknown_work":
        row["invocations"][0]["unknown_execution_work"] = True
    elif reason == "zero_work":
        row["invocations"][0]["work"]["attempted_step_count"] = 0
    else:
        row["selection_eligible"] = False
    result = layout_cost_dominance(plan, [row])
    assert result["incumbent_candidate_id"] is None
    assert result["cost_dominated_unevaluated_candidate_ids"] == []


def test_equal_cost_candidate_is_retained_for_ties(actual):
    plan, rows = original(actual)
    baseline_cost = rows["baseline"]["material_estimate"]["total"]
    next(p for p in plan["pool"] if p["candidate_id"] == "large")["material_estimate"][
        "total"
    ] = baseline_cost
    rehash(plan)
    result = layout_cost_dominance(plan, [rows["baseline"]])
    assert result["cost_dominated_unevaluated_candidate_ids"] == []
    assert "large" in result["retained_unevaluated_candidate_ids"]


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), 10**400])
def test_invalid_pool_costs_cannot_produce_bounds(actual, value):
    plan, rows = original(actual)
    plan["pool"][-1]["material_estimate"]["total"] = value
    with pytest.raises(ValueError):
        rehash(plan)
        layout_cost_dominance(plan, [rows["baseline"]])


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("scope", "other"),
        ("price_table_hash", "sha256:" + "0" * 64),
    ],
)
def test_mixed_price_identities_are_rejected(actual, field, value):
    plan, rows = original(actual)
    plan["pool"][-1]["material_estimate"][field] = value
    rehash(plan)
    with pytest.raises(ValueError, match="currency, scope and price table"):
        layout_cost_dominance(plan, [rows["baseline"]])


def test_unbound_plan_and_mismatched_original_rows_are_rejected(actual):
    plan, rows = original(actual)
    altered = deepcopy(plan)
    altered["pool"][-1]["material_estimate"]["total"] += 1
    with pytest.raises(ValueError, match="frozen"):
        layout_cost_dominance(altered, [rows["baseline"]])
    rows["baseline"]["artifacts"]["model"]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="model artifact"):
        layout_cost_dominance(plan, [rows["baseline"]])


def test_duplicate_evaluated_rows_are_rejected(actual):
    plan, rows = original(actual)
    with pytest.raises(ValueError, match="unique evaluated"):
        layout_cost_dominance(plan, [rows["baseline"], rows["baseline"]])


def test_missing_model_binding_cannot_be_hidden_by_matching_rows(actual):
    plan, rows = original(actual)
    plan["pool"][0]["model_artifact"] = {}
    rows["baseline"]["artifacts"]["model"] = {}
    rehash(plan)
    with pytest.raises(ValueError, match="model and quantity bindings"):
        layout_cost_dominance(plan, [rows["baseline"]])
