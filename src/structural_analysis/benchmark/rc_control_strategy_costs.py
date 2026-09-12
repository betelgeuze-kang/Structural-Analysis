"""Compare recorded standalone CLI intervals under matching search conditions.

This verifies metadata/accounting bindings, not numerical artifacts or physics.
Original Workbench design validation remains required before engineering use.
"""

from __future__ import annotations

import math
import re

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_ranking import (
    LEGACY_RANKING,
    candidate_ranking,
)

CLI_SCOPE = "argument_parsing_input_reads_preparation_ranking_full_reference_and_report_persistence"
SEARCH_SCOPE = "single_strategy_preparation_ranking_full_reference_and_IO_excluding_final_report_write"
EXCLUDES = [
    "interpreter_startup_and_module_imports",
    "runtime_sidecar_and_stdout",
    "transport_and_workbench_review",
]


def _nat(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("nonnegative safe integer time required")
    return value


def _bound(value, schema, field):
    if type(value) is not dict or value.get("schema_version") != schema:
        raise ValueError("supported cost input schema required")
    if value.get(field) != study._sha(
        study._bytes({k: v for k, v in value.items() if k != field})
    ):
        raise ValueError("cost input hash mismatch")


def _execution(execution, strategy):
    report, plan, runtime = (execution[k] for k in ("report", "plan", "runtime"))
    _bound(report, "experimental-rc-control-candidate-strategy.v1", "report_hash")
    _bound(plan, "experimental-rc-control-candidate-strategy-plan.v1", "plan_hash")
    if (
        report.get("strategy") != strategy
        or plan.get("strategy") != strategy
        or report.get("plan_hash") != plan["plan_hash"]
        or report.get("source_revision") != plan.get("source_revision")
        or report.get("oracle") is not None
        or plan.get("oracle_after_online_arms") is not False
        or set(report["arms"]) != {strategy}
        or set(plan["plans"]) != {strategy}
        or report.get("timing_scope") != SEARCH_SCOPE
    ):
        raise ValueError("standalone strategy/report binding mismatch")
    if not re.fullmatch(r"[a-f0-9]{40}", str(report.get("source_revision"))):
        raise ValueError("full source revision required")
    arm = report["arms"][strategy]
    if (
        arm.get("status") != "completed"
        or arm.get("unknown_work_until_outcome") is not False
        or arm.get("execution_work", {}).get("unknown_work") is not False
        or type(runtime) is not dict
        or runtime.get("schema_version")
        != "experimental-rc-control-candidate-strategy-runtime.v1"
        or runtime.get("report_hash") != report["report_hash"]
        or runtime.get("source_revision") != report["source_revision"]
        or runtime.get("strategy") != strategy
        or runtime.get("scope") != CLI_SCOPE
        or runtime.get("excludes") != EXCLUDES
        or runtime.get("net_savings_proved") is not False
        or type(runtime.get("new_training_fit_count")) is not int
        or runtime["new_training_fit_count"] != 0
    ):
        raise ValueError("completed known execution and bound runtime required")
    work = arm["execution_work"].get("known_counters", {})
    for key in (
        "attempted_step_count",
        "known_linear_solve_count",
        "known_newton_iteration_count",
        "unknown_solver_work_attempt_count",
    ):
        _nat(work.get(key))
    if work["unknown_solver_work_attempt_count"] != 0:
        raise ValueError("unknown solver work cannot be compared")
    for clock in ("wall_ns", "cpu_ns"):
        if _nat(runtime[clock]) < _nat(
            report["online_and_optional_oracle_" + clock]
        ) or _nat(report["online_and_optional_oracle_" + clock]) < _nat(arm[clock]):
            raise ValueError("nested execution timing mismatch")
    if (
        _nat(report["ranking_wall_ns"]) + arm["wall_ns"]
        > report["online_and_optional_oracle_wall_ns"]
    ):
        raise ValueError("ranking interval exceeds search time")
    pool = plan["pool"]
    if type(pool) is not list or not 2 <= len(pool) <= 17:
        raise ValueError("bounded candidate pool required")
    for row in pool:
        estimate = row["material_estimate"]["total"]
        if (
            type(estimate) not in (int, float)
            or not math.isfinite(estimate)
            or estimate < 0
        ):
            raise ValueError("finite nonnegative scoped estimate required")
    ids = [r["candidate_id"] for r in pool]
    if ids[0] != "baseline" or len(set(ids)) != len(ids):
        raise ValueError("unique baseline and alternatives required")
    budget = plan["full_analysis_budget_per_arm"]
    if type(budget) is not int or not 2 <= budget <= 17:
        raise ValueError("bounded strategy budget required")
    if strategy == "price_order":
        if (
            report["historical_training_cost"] is not None
            or plan["policy_hash"] is not None
            or plan["training_report_hash"] is not None
            or plan["predictions"] != []
            or report["ranking_wall_ns"] != 0
        ):
            raise ValueError("price execution must not carry learned costs")
        ordering = [
            r["candidate_id"]
            for r in sorted(
                pool[1:],
                key=lambda r: (r["material_estimate"]["total"], r["candidate_id"]),
            )
        ]
    else:
        if [r["candidate_id"] for r in plan["predictions"]] != ids[1:]:
            raise ValueError("complete prediction denominator required")
        ordering, detail = candidate_ranking(
            plan["predictions"], plan.get("ranking", {}).get("strategy", LEGACY_RANKING)
        )
        if detail != plan.get("ranking"):
            raise ValueError("learned ranking binding mismatch")
    if plan["plans"][strategy] != {
        "ordering": ordering,
        "shortlist": ordering[: budget - 1],
    } or arm["request_count"] != min(budget, len(pool)):
        raise ValueError("strategy shortlist/budget mismatch")
    chosen = arm["selected_candidate_id"]
    expected = next(
        (r["material_estimate"]["total"] for r in pool if r["candidate_id"] == chosen),
        None,
    )
    if arm["selected_estimate"] != expected or (
        chosen is not None and chosen not in ["baseline", *ordering[: budget - 1]]
    ):
        raise ValueError("selected estimate/pool mismatch")
    if type(arm["selected_full_reference_verified"]) is not bool or (
        chosen is None and arm["selected_full_reference_verified"]
    ):
        raise ValueError("selected verification declaration mismatch")
    return report, plan, runtime, arm


def compare_rc_control_strategy_costs(pairs):
    """Retain every pair; emit no ratio when any recorded selection is incomparable."""
    rows, training, seen = [], {}, set()
    for pair in pairs:
        p, pp, pr, pa = _execution(pair["price_order"], "price_order")
        learned_report, lp, lr, la = _execution(pair["learned_order"], "learned_order")
        for report in (p, learned_report):
            if report["report_hash"] in seen:
                raise ValueError("duplicate execution is not an independent repetition")
            seen.add(report["report_hash"])
        for key in (
            "source_revision",
            "control_request",
            "pool",
            "history_limits",
            "material_limits",
            "terminal_limits",
            "price_table_hash",
            "full_analysis_budget_per_arm",
            "line_search_assembly_reuse",
        ):
            if key != "line_search_assembly_reuse" and (key not in pp or key not in lp):
                raise ValueError("paired search condition missing: " + key)
            if pp.get(key) != lp.get(key):
                raise ValueError("paired search conditions differ: " + key)
        historical = learned_report["historical_training_cost"]
        _bound(
            historical, "experimental-rc-control-candidate-training.v1", "report_hash"
        )
        if (
            historical["report_hash"] != lp["training_report_hash"]
            or historical["policy_hash"] != lp["policy_hash"]
        ):
            raise ValueError("historical training identity mismatch")
        if (
            historical["fit"].get("status") != "completed"
            or historical["fit"].get("unknown_fit_work_until_outcome") is not False
        ):
            raise ValueError("completed historical fit required")
        upfront = _nat(historical["wall_ns"])
        labels = historical.get("label_invocations")
        samples = historical.get("sample_count")
        if (
            type(samples) is not int
            or not 2 <= samples <= 17
            or type(labels) is not list
            or len(labels) != 2 * samples
        ):
            raise ValueError("complete historical label denominator required")
        for invocation in labels:
            work = invocation.get("work")
            if (
                invocation.get("unknown_execution_work") is not False
                or type(work) is not dict
            ):
                raise ValueError("known historical label work required")
            for key in (
                "attempted_step_count",
                "known_linear_solve_count",
                "known_newton_iteration_count",
                "unknown_solver_work_attempt_count",
            ):
                _nat(work.get(key))
            if work["unknown_solver_work_attempt_count"] != 0:
                raise ValueError("known historical label work required")
        if (
            _nat(historical["label_generation_wall_ns"])
            + _nat(historical["fit"]["wall_ns"])
            > upfront
        ):
            raise ValueError("historical training subintervals exceed total")
        training[historical["report_hash"]] = upfront
        comparable = (
            pa["selected_full_reference_verified"]
            and la["selected_full_reference_verified"]
            and la["selected_estimate"] <= pa["selected_estimate"]
        )
        rows.append(
            {
                "price_report_hash": p["report_hash"],
                "learned_report_hash": learned_report["report_hash"],
                "price_runtime_digest": study._sha(study._bytes(pr)),
                "learned_runtime_digest": study._sha(study._bytes(lr)),
                "training_report_hash": historical["report_hash"],
                "price_cli_wall_ns": pr["wall_ns"],
                "learned_cli_wall_ns": lr["wall_ns"],
                "recorded_selection_comparable": comparable,
                "learned_over_price_cli_ratio": lr["wall_ns"] / pr["wall_ns"]
                if comparable and pr["wall_ns"] > 0
                else None,
            }
        )
    if not rows:
        raise ValueError("at least one matched execution pair required")
    price = sum(r["price_cli_wall_ns"] for r in rows)
    learned = sum(r["learned_cli_wall_ns"] for r in rows)
    upfront = sum(training.values())
    for total in (price, learned, upfront, learned + upfront):
        _nat(total)
    comparable = all(r["recorded_selection_comparable"] for r in rows)
    return {
        "schema_version": "experimental-rc-control-strategy-cost-cohort.v1",
        "pairs": rows,
        "pair_count": len(rows),
        "uncomparable_pair_count": sum(
            not r["recorded_selection_comparable"] for r in rows
        ),
        "distinct_historical_training_wall_ns": training,
        "price_cli_interval_sum_ns": price,
        "learned_cli_interval_sum_ns": learned,
        "historical_training_wall_ns_counted_once": upfront,
        "learned_plus_historical_interval_sum_ns": learned + upfront,
        "learned_plus_historical_over_price_ratio": (learned + upfront) / price
        if comparable and price > 0
        else None,
        "scope": "sum_of_cli_intervals_plus_distinct_historical_training_not_campaign_elapsed",
        "excluded": [*EXCLUDES, "separate_audits"],
        "original_physical_artifacts_replayed": False,
        "runtime_digest_is_attestation": False,
        "net_savings_proved": False,
        "independent_generalization": False,
    }


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    from structural_analysis.api.frame3d_direct_control_request import (
        strict_json_object_bytes,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair",
        nargs=2,
        type=Path,
        action="append",
        required=True,
        metavar=("PRICE_DIR", "LEARNED_DIR"),
    )
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_revision):
        raise ValueError("full accounting source revision required")
    pairs, refs = [], []
    for paths in args.pair:
        pair = {}
        for strategy, directory in zip(
            ("price_order", "learned_order"), paths, strict=True
        ):
            values = {}
            for key, name in (
                ("report", "result.json"),
                ("plan", "plan.json"),
                ("runtime", "strategy-runtime.json"),
            ):
                with (directory / name).open("rb") as stream:
                    raw = stream.read(2 * 1024 * 1024 + 1)
                values[key] = strict_json_object_bytes(
                    raw, maximum_bytes=2 * 1024 * 1024
                )
                refs.append(
                    {
                        "path": str(directory / name),
                        "byte_length": len(raw),
                        "sha256": study._sha(raw),
                    }
                )
            pair[strategy] = values
        pairs.append(pair)
    result = compare_rc_control_strategy_costs(pairs)
    result["input_files"] = refs
    result["accounting_source_revision"] = args.source_revision
    result["accounting_source_revision_is_attestation"] = False
    result["report_hash"] = study._sha(study._bytes(result))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
