"""Synthetic clocks test arithmetic only; real-search coverage lives alongside it."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_search_accounting import (
    account_rc_control_search_reports as account,
    main,
)


def bind(value):
    body = {k: v for k, v in value.items() if k != "report_hash"}
    return body | {"report_hash": study._sha(study._bytes(body))}


def example(oracle=True):
    training = bind(
        {
            "schema_version": "experimental-rc-control-candidate-training.v1",
            "wall_ns": 100,
            "label_generation_wall_ns": 70,
            "fit": {
                "wall_ns": 20,
                "status": "completed",
                "unknown_fit_work_until_outcome": False,
            },
        }
    )
    return bind(
        {
            "schema_version": "experimental-rc-control-candidate-search.v3",
            "historical_training_cost": training,
            "historical_training_cost_counted_once_outside_online_arms": True,
            "timing_scope": "preflight_ranking_both_full_analysis_arms_optional_oracle_and_IO_excluding_final_report_write",
            "arms": {
                "price_order": {"status": "completed", "wall_ns": 40},
                "learned_order": {"status": "completed", "wall_ns": 30},
            },
            "oracle": {"status": "completed", "wall_ns": 60} if oracle else None,
            "ranking_wall_ns": 5,
            "online_and_optional_oracle_wall_ns": 150 if oracle else 90,
        }
    )


def test_shared_training_once_and_all_nested_intervals_disjoint():
    result = account([example(), example(False)])
    assert result["observed_search_wall_ns"] == 240
    assert result["historical_training_wall_ns_counted_once"] == 100
    assert result["combined_recorded_interval_sum_ns"] == 340
    assert len(result["distinct_historical_training"]) == 1
    for row in result["executions"]:
        assert row["unallocated_search_wall_ns"] == 15
    assert result["executions"][1]["oracle_executed"] is False
    assert result["executions"][1]["oracle_wall_ns"] == 0
    assert not result["net_savings_proved"]
    assert not result["strategy_complete_costs_separately_measured"]


def test_distinct_training_runs_are_not_deduplicated_by_equal_cost():
    other = example(False)
    other["historical_training_cost"] = bind(
        other["historical_training_cost"] | {"source_revision": "different"}
    )
    result = account([example(), bind(other)])
    assert result["historical_training_wall_ns_counted_once"] == 200


@pytest.mark.parametrize("value", [True, -1, 1.5, None, "5"])
def test_invalid_clock_even_after_rehash_rejects(value):
    report = example()
    report["ranking_wall_ns"] = value
    with pytest.raises(ValueError, match="nonnegative integer"):
        account([bind(report)])


@pytest.mark.parametrize("target", ["search", "training"])
def test_impossible_nested_intervals_reject(target):
    report = example()
    if target == "search":
        report["online_and_optional_oracle_wall_ns"] = 1
    else:
        report["historical_training_cost"] = bind(
            report["historical_training_cost"] | {"wall_ns": 1}
        )
    with pytest.raises(ValueError, match="subintervals exceed total"):
        account([bind(report)])


def test_duplicate_report_and_tampered_nested_hash_reject():
    report = example()
    with pytest.raises(ValueError, match="duplicate"):
        account([report, deepcopy(report)])
    report["historical_training_cost"]["wall_ns"] += 1
    with pytest.raises(ValueError, match="hash mismatch"):
        account([bind(report)])


def test_cli_rejects_duplicate_json_keys_before_printing(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text('{"schema_version":"one","schema_version":"two"}')
    with pytest.raises(ValueError):
        main([str(path)])
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "change",
    [
        {"timing_scope": "unknown"},
        {"historical_training_cost_counted_once_outside_online_arms": False},
        {
            "arms": {
                "price_order": {"status": "raised", "wall_ns": 40},
                "learned_order": {"status": "completed", "wall_ns": 30},
            }
        },
    ],
)
def test_unknown_scope_or_unfinished_execution_rejects(change):
    with pytest.raises(ValueError):
        account([bind(example() | change)])
