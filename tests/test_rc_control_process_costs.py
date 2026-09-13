"""Controlled clocks check containment and accounting, not speed or physics."""

from copy import deepcopy

import pytest

from tests.test_rc_control_strategy_costs import paired
from structural_analysis.benchmark.rc_control_strategy_costs import (
    compare_rc_control_strategy_costs,
)
from structural_analysis.benchmark.rc_control_process_costs import (
    PROCESS_SCOPE,
    compare_rc_control_process_costs,
)


def inputs(pairs=None):
    pairs = [paired(), paired(1)] if pairs is None else pairs
    cli = compare_rc_control_strategy_costs(pairs)
    processes = [
        dict(
            report_hash=r[f"{s}_report_hash"],
            runtime_digest=r[f"{s}_runtime_digest"],
            wall_ns=r[f"{s}_cli_wall_ns"] + overhead,
            return_code=0,
            scope=PROCESS_SCOPE,
        )
        for r in cli["pairs"]
        for s, overhead in (("price", 1000), ("learned", 2000))
    ]
    return pairs, cli, processes


def test_enclosing_intervals_replace_children_and_shared_training_is_counted_once():
    pairs, cli, processes = inputs()
    result = compare_rc_control_process_costs(pairs, list(reversed(processes)))
    assert (
        result["price_process_interval_sum_ns"]
        == cli["price_cli_interval_sum_ns"] + 2000
    )
    assert (
        result["learned_process_interval_sum_ns"]
        == cli["learned_cli_interval_sum_ns"] + 4000
    )
    assert (
        result["historical_training_wall_ns_counted_once"]
        == cli["historical_training_wall_ns_counted_once"]
    )
    assert (
        result["learned_plus_historical_interval_sum_ns"]
        == result["learned_process_interval_sum_ns"]
        + result["historical_training_wall_ns_counted_once"]
    )
    assert result["outside_cli_interval_is_startup_only"] is False
    assert result["net_savings_proved"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign",
        "runtime",
        "short",
        "bool",
        "failure",
        "bool_exit",
        "scope",
        "extra",
        "overflow",
    ],
)
def test_rejects_unbound_incomplete_or_non_enclosing_processes(mutation):
    pairs, cli, processes = inputs()
    processes = deepcopy(processes)
    if mutation == "missing":
        processes.pop()
    if mutation == "duplicate":
        processes[1] = processes[0]
    if mutation == "foreign":
        processes[0]["report_hash"] = "sha256:" + "0" * 64
    if mutation == "runtime":
        processes[0]["runtime_digest"] = processes[1]["runtime_digest"]
    if mutation == "short":
        processes[0]["wall_ns"] = cli["pairs"][0]["price_cli_wall_ns"] - 1
    if mutation == "bool":
        processes[0]["wall_ns"] = True
    if mutation == "failure":
        processes[0]["return_code"] = 1
    if mutation == "bool_exit":
        processes[0]["return_code"] = False
    if mutation == "scope":
        processes[0]["scope"] = "solver_only"
    if mutation == "extra":
        processes[0]["verified"] = True
    if mutation == "overflow":
        for p in processes:
            p["wall_ns"] = 2**53 - 1
    with pytest.raises(ValueError):
        compare_rc_control_process_costs(pairs, processes)


def test_incomparable_pair_is_retained_without_a_ratio():
    from tests.test_rc_control_strategy_costs import rebind

    pair = paired()
    arm = pair["price_order"]["report"]["arms"]["price_order"]
    arm.update(
        selected_candidate_id=None,
        selected_estimate=None,
        selected_full_reference_verified=False,
    )
    rebind(pair["price_order"])
    pairs, cli, processes = inputs([pair])
    result = compare_rc_control_process_costs(pairs, processes)
    assert result["pair_count"] == result["uncomparable_pair_count"] == 1
    assert result["pairs"][0]["learned_over_price_process_ratio"] is None
    assert result["learned_plus_historical_over_price_ratio"] is None
    assert result["price_process_interval_sum_ns"] > 0
