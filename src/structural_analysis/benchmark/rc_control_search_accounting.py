"""Account recorded RC search intervals without inferring deployment speedups.

This is an arithmetic audit of hash-bound reports, not artifact/physics replay.
Historical training is charged once per distinct training report in the cohort.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_design as study


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _bound(report, schema):
    if type(report) is not dict or report.get("schema_version") != schema:
        raise ValueError("unsupported accounting report schema")
    body = {k: v for k, v in report.items() if k != "report_hash"}
    if report.get("report_hash") != study._sha(study._bytes(body)):
        raise ValueError("accounting report hash mismatch")


def account_rc_control_search_reports(reports):
    """Keep nested intervals disjoint and unaffiliated overhead explicit.

    No ratios or amortization projections are emitted: the producer does not meter
    separate complete preparation/delivery paths for price and learned strategies.
    Even exact arithmetic here does not validate the reports' physical assertions.
    """
    rows, training, seen = [], {}, set()
    for report in reports:
        _bound(report, "experimental-rc-control-candidate-search.v3")
        identity = report["report_hash"]
        if identity in seen:
            raise ValueError("duplicate search execution report")
        seen.add(identity)
        historical = report["historical_training_cost"]
        _bound(historical, "experimental-rc-control-candidate-training.v1")
        if (
            report.get("historical_training_cost_counted_once_outside_online_arms")
            is not True
        ):
            raise ValueError("explicit historical training accounting required")
        total = _count(historical["wall_ns"], "training wall")
        labels = _count(historical["label_generation_wall_ns"], "label wall")
        fit = _count(historical["fit"]["wall_ns"], "fit wall")
        if (
            historical["fit"].get("status") != "completed"
            or historical["fit"].get("unknown_fit_work_until_outcome") is not False
        ):
            raise ValueError("completed known training fit required")
        if labels + fit > total:
            raise ValueError("training subintervals exceed total")
        training[historical["report_hash"]] = {
            "wall_ns": total,
            "label_generation_wall_ns": labels,
            "fit_wall_ns": fit,
            "other_training_wall_ns": total - labels - fit,
        }
        if report.get("timing_scope") != (
            "preflight_ranking_both_full_analysis_arms_optional_oracle_and_IO_excluding_final_report_write"
        ):
            raise ValueError("unsupported search timing scope")
        arms = report["arms"]
        if set(arms) != {"price_order", "learned_order"}:
            raise ValueError("both original search arms required")
        arm_times = {}
        for name, arm in [*arms.items(), ("oracle", report["oracle"])]:
            if arm is None and name == "oracle":
                arm_times[name] = 0
                continue
            if arm.get("status") != "completed":
                raise ValueError("completed recorded execution required")
            arm_times[name] = _count(arm["wall_ns"], name + " wall")
        ranking = _count(report["ranking_wall_ns"], "ranking wall")
        search = _count(report["online_and_optional_oracle_wall_ns"], "search wall")
        accounted = ranking + sum(arm_times.values())
        if accounted > search:
            raise ValueError("search subintervals exceed total")
        rows.append(
            {
                "search_report_hash": identity,
                "training_report_hash": historical["report_hash"],
                "search_wall_ns": search,
                "price_arm_wall_ns": arm_times["price_order"],
                "learned_arm_wall_ns": arm_times["learned_order"],
                "learned_ranking_wall_ns": ranking,
                "oracle_executed": report["oracle"] is not None,
                "oracle_wall_ns": arm_times["oracle"],
                "unallocated_search_wall_ns": search - accounted,
            }
        )
    if not rows:
        raise ValueError("at least one search execution required")
    search_total = sum(r["search_wall_ns"] for r in rows)
    training_total = sum(t["wall_ns"] for t in training.values())
    return {
        "schema_version": "experimental-rc-control-search-accounting.v1",
        "executions": rows,
        "distinct_historical_training": training,
        "observed_search_wall_ns": search_total,
        "historical_training_wall_ns_counted_once": training_total,
        "combined_recorded_interval_sum_ns": search_total + training_total,
        "scope": "sum_of_recorded_intervals_not_campaign_elapsed_or_deployed_strategy_cost",
        "excluded_or_unmeasured": [
            "final_search_report_write",
            "source_snapshot_preparation",
            "external_audit",
            "transport_and_workbench_review",
        ],
        "strategy_complete_costs_separately_measured": False,
        "net_savings_proved": False,
        "original_artifacts_replayed": False,
        "independent_physical_validation": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)
    reports = []
    for path in args.reports:
        with path.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        reports.append(strict_json_object_bytes(raw, maximum_bytes=2 * 1024 * 1024))
    print(
        json.dumps(
            account_rc_control_search_reports(reports), indent=2, allow_nan=False
        )
    )


if __name__ == "__main__":
    main()
