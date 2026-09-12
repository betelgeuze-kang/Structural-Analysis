"""Controlled metadata/clocks verify cohort accounting, not performance."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_strategy_costs import (
    CLI_SCOPE,
    EXCLUDES,
    SEARCH_SCOPE,
    compare_rc_control_strategy_costs as compare,
    main,
)

ROOT = Path("tests/frontend/fixtures/rc-control-search-cost-no-oracle")


def bind(value, field):
    body = {k: v for k, v in value.items() if k != field}
    return body | {field: study._sha(study._bytes(body))}


def paired(repeat=0):
    result = {}
    for strategy in ("price_order", "learned_order"):
        report = json.loads((ROOT / "result.json").read_bytes())
        plan = json.loads((ROOT / "plan.json").read_bytes())
        report.update(
            schema_version="experimental-rc-control-candidate-strategy.v1",
            strategy=strategy,
            arms={strategy: report["arms"][strategy]},
            timing_scope=SEARCH_SCOPE,
        )
        # Unique controlled repeat identity. No numerical re-execution implied.
        report["online_and_optional_oracle_wall_ns"] += repeat
        plan.update(
            schema_version="experimental-rc-control-candidate-strategy-plan.v1",
            strategy=strategy,
            plans={strategy: plan["plans"][strategy]},
        )
        if strategy == "price_order":
            plan.update(predictions=[], policy_hash=None, training_report_hash=None)
            report.update(historical_training_cost=None, ranking_wall_ns=0)
        plan = bind(plan, "plan_hash")
        report["plan_hash"] = plan["plan_hash"]
        report = bind(report, "report_hash")
        runtime = dict(
            schema_version="experimental-rc-control-candidate-strategy-runtime.v1",
            strategy=strategy,
            source_revision=report["source_revision"],
            report_hash=report["report_hash"],
            wall_ns=report["online_and_optional_oracle_wall_ns"] + 100,
            cpu_ns=report["online_and_optional_oracle_cpu_ns"] + 100,
            scope=CLI_SCOPE,
            excludes=EXCLUDES,
            new_training_fit_count=0,
            net_savings_proved=False,
        )
        result[strategy] = dict(report=report, plan=plan, runtime=runtime)
    return result


def rebind(execution):
    execution["plan"] = bind(execution["plan"], "plan_hash")
    execution["report"]["plan_hash"] = execution["plan"]["plan_hash"]
    execution["report"] = bind(execution["report"], "report_hash")
    execution["runtime"]["report_hash"] = execution["report"]["report_hash"]


def test_shared_training_charged_once_across_distinct_executions():
    pairs = [paired(), paired(1)]
    result = compare(pairs)
    training = pairs[0]["learned_order"]["report"]["historical_training_cost"][
        "wall_ns"
    ]
    assert result["historical_training_wall_ns_counted_once"] == training
    assert len(result["distinct_historical_training_wall_ns"]) == 1
    assert result["pair_count"] == 2 and result["uncomparable_pair_count"] == 0
    assert (
        result["learned_plus_historical_interval_sum_ns"]
        == result["learned_cli_interval_sum_ns"] + training
    )
    assert (
        not result["net_savings_proved"]
        and not result["original_physical_artifacts_replayed"]
    )


def test_failed_selection_is_retained_and_blocks_cohort_ratio():
    pair = paired()
    arm = pair["price_order"]["report"]["arms"]["price_order"]
    arm.update(
        selected_candidate_id=None,
        selected_estimate=None,
        selected_full_reference_verified=False,
    )
    rebind(pair["price_order"])
    result = compare([pair, paired(1)])
    assert result["pair_count"] == 2 and result["uncomparable_pair_count"] == 1
    assert result["pairs"][0]["learned_over_price_cli_ratio"] is None
    assert result["learned_plus_historical_over_price_ratio"] is None
    assert (
        result["price_cli_interval_sum_ns"] > pair["price_order"]["runtime"]["wall_ns"]
    )


@pytest.mark.parametrize(
    "field",
    [
        "control_request",
        "pool",
        "price_table_hash",
        "full_analysis_budget_per_arm",
        "line_search_assembly_reuse",
    ],
)
def test_rehashed_unmatched_conditions_reject(field):
    pair = paired()
    plan = pair["learned_order"]["plan"]
    if field == "control_request":
        plan[field] = plan[field] | {"changed": True}
    elif field == "pool":
        plan[field][0]["model_checksum"] = "sha256:" + "a" * 64
    elif field == "full_analysis_budget_per_arm":
        plan[field] += 1
    else:
        plan[field] = "different"
    rebind(pair["learned_order"])
    with pytest.raises(ValueError):
        compare([pair])


@pytest.mark.parametrize("value", [True, -1, 1.5, 2**53])
def test_invalid_runtime_clocks_reject(value):
    pair = paired()
    pair["learned_order"]["runtime"]["wall_ns"] = value
    with pytest.raises(ValueError):
        compare([pair])


def test_duplicate_execution_rejects_and_runtime_identity_cannot_be_substituted():
    pair = paired()
    with pytest.raises(ValueError, match="duplicate"):
        compare([pair, deepcopy(pair)])
    pair["learned_order"]["runtime"]["report_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="bound runtime"):
        compare([pair])


def test_unknown_numerical_work_cannot_receive_ratio():
    pair = paired()
    pair["learned_order"]["report"]["arms"]["learned_order"]["execution_work"][
        "known_counters"
    ]["unknown_solver_work_attempt_count"] = 1
    rebind(pair["learned_order"])
    with pytest.raises(ValueError, match="unknown solver work"):
        compare([pair])


def test_cli_binds_original_input_bytes(tmp_path, capsys):
    pair = paired()
    dirs = []
    for strategy, data in pair.items():
        root = tmp_path / strategy
        root.mkdir()
        dirs.append(str(root))
        for key, name in [
            ("report", "result.json"),
            ("plan", "plan.json"),
            ("runtime", "strategy-runtime.json"),
        ]:
            (root / name).write_bytes(study._bytes(data[key]))
    main(["--pair", *dirs, "--source-revision", "a" * 40])
    result = json.loads(capsys.readouterr().out)
    assert len(result["input_files"]) == 6
    assert result["report_hash"] == study._sha(
        study._bytes({k: v for k, v in result.items() if k != "report_hash"})
    )


def test_more_expensive_recorded_feasible_selection_does_not_get_speed_credit():
    pair = paired()
    learned = pair["learned_order"]
    arm = learned["report"]["arms"]["learned_order"]
    arm.update(
        selected_candidate_id="baseline",
        selected_estimate=learned["plan"]["pool"][0]["material_estimate"]["total"],
    )
    rebind(learned)
    result = compare([pair])
    assert result["uncomparable_pair_count"] == 1
    assert result["pairs"][0]["learned_over_price_cli_ratio"] is None


def test_rehashed_unknown_historical_label_work_rejects():
    pair = paired()
    learned = pair["learned_order"]
    h = learned["report"]["historical_training_cost"]
    h["label_invocations"][0]["unknown_execution_work"] = True
    h = bind(h, "report_hash")
    learned["report"]["historical_training_cost"] = h
    learned["plan"]["training_report_hash"] = h["report_hash"]
    rebind(learned)
    with pytest.raises(ValueError, match="known historical label work"):
        compare([pair])


def test_aggregate_clock_overflow_is_not_serialized_as_an_inexact_browser_number():
    pair = paired()
    pair['learned_order']['runtime']['wall_ns'] = 2**53 - 1
    with pytest.raises(ValueError, match='safe integer'):
        compare([pair])
