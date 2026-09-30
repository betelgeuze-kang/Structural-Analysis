"""Enclosing process intervals for verified standalone strategy cost pairs.

Caller-bound process observations are not clock attestations or physical evidence.
Process intervals replace CLI intervals; they are never added to their children.
"""

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_strategy_costs import (
    _nat,
    compare_rc_control_strategy_costs,
)

PROCESS_SCOPE = "subprocess_launch_through_exit_including_startup_and_stdout"


def compare_rc_control_process_costs(pairs, processes):
    """Compare completed paired processes, retaining incompatible selections."""
    cli = compare_rc_control_strategy_costs(pairs)
    if type(processes) is not list or len(processes) != 2 * cli["pair_count"]:
        raise ValueError("one process observation per execution required")
    expected = {
        row[f"{strategy}_report_hash"]: (
            row[f"{strategy}_runtime_digest"],
            row[f"{strategy}_cli_wall_ns"],
        )
        for row in cli["pairs"]
        for strategy in ("price", "learned")
    }
    indexed = {}
    for process in processes:
        if type(process) is not dict or set(process) != {
            "report_hash",
            "runtime_digest",
            "wall_ns",
            "return_code",
            "scope",
        }:
            raise ValueError("exact process observation fields required")
        identity = process["report_hash"]
        if type(identity) is not str or identity not in expected or identity in indexed:
            raise ValueError("missing, duplicate or foreign process identity")
        digest, child_ns = expected[identity]
        if (
            process["runtime_digest"] != digest
            or type(process["return_code"]) is not int
            or process["return_code"] != 0
            or process["scope"] != PROCESS_SCOPE
            or _nat(process["wall_ns"]) < child_ns
        ):
            raise ValueError("completed enclosing process interval required")
        indexed[identity] = process
    rows = []
    for pair in cli["pairs"]:
        price = indexed[pair["price_report_hash"]]
        learned = indexed[pair["learned_report_hash"]]
        rows.append(
            {
                "price_report_hash": price["report_hash"],
                "learned_report_hash": learned["report_hash"],
                "price_process_digest": study._sha(study._bytes(price)),
                "learned_process_digest": study._sha(study._bytes(learned)),
                "price_process_wall_ns": price["wall_ns"],
                "learned_process_wall_ns": learned["wall_ns"],
                "price_outside_cli_wall_ns": price["wall_ns"]
                - pair["price_cli_wall_ns"],
                "learned_outside_cli_wall_ns": learned["wall_ns"]
                - pair["learned_cli_wall_ns"],
                "recorded_selection_comparable": pair["recorded_selection_comparable"],
                "learned_over_price_process_ratio": (
                    learned["wall_ns"] / price["wall_ns"]
                    if pair["recorded_selection_comparable"] and price["wall_ns"] > 0
                    else None
                ),
            }
        )
    price_total = _nat(sum(row["price_process_wall_ns"] for row in rows))
    learned_total = _nat(sum(row["learned_process_wall_ns"] for row in rows))
    training = cli["historical_training_wall_ns_counted_once"]
    inclusive = _nat(learned_total + training)
    return {
        "schema_version": "experimental-rc-control-process-cost-cohort.v1",
        "cli_accounting_digest": study._sha(study._bytes(cli)),
        "pairs": rows,
        "pair_count": len(rows),
        "uncomparable_pair_count": cli["uncomparable_pair_count"],
        "price_process_interval_sum_ns": price_total,
        "learned_process_interval_sum_ns": learned_total,
        "distinct_historical_training_wall_ns": cli[
            "distinct_historical_training_wall_ns"
        ],
        "historical_training_wall_ns_counted_once": training,
        "learned_plus_historical_interval_sum_ns": inclusive,
        "learned_plus_historical_over_price_ratio": (
            inclusive / price_total
            if not cli["uncomparable_pair_count"] and price_total > 0
            else None
        ),
        "scope": "sum_of_process_intervals_plus_distinct_historical_training_not_campaign_elapsed",
        "excluded": [
            "transport_and_workbench_review",
            "separate_audits",
            "campaign_preparation",
        ],
        "outside_cli_interval_is_startup_only": False,
        "process_digest_is_attestation": False,
        "original_physical_artifacts_replayed": False,
        "net_savings_proved": False,
        "independent_generalization": False,
    }
