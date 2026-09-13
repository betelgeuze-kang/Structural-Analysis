"""Run one RC candidate strategy, metering input reads through report persistence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    read_design_experiment_with_material_history,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    RCControlCandidatePolicy,
)
from structural_analysis.benchmark.rc_control_candidate_ranking import (
    LEGACY_RANKING,
    RANKING_STRATEGIES,
)
from structural_analysis.benchmark.rc_control_candidate_search import (
    run_rc_control_candidate_strategy,
)
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def main(argv=None):
    wall, cpu = perf_counter_ns(), process_time_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "request", "experiment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--strategy", choices=("price_order", "learned_order"), required=True
    )
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--training-report", type=Path)
    parser.add_argument("--full-analysis-budget", type=int, default=3)
    parser.add_argument(
        "--ranking-strategy", choices=RANKING_STRATEGIES, default=LEGACY_RANKING
    )
    parser.add_argument("--reuse-line-search-assembly", action="store_true")
    args = parser.parse_args(argv)
    if args.strategy == "price_order":
        if args.policy is not None or args.training_report is not None:
            raise ValueError("price-only execution must not receive learned artifacts")
    elif args.policy is None or args.training_report is None:
        raise ValueError(
            "learned execution requires policy and historical training report"
        )
    policy = training = None
    if args.strategy == "learned_order":
        assert args.policy is not None and args.training_report is not None
        policy = RCControlCandidatePolicy(
            _read(args.policy, 2 * 1024 * 1024).decode("utf-8")
        )
        training = strict_json_object_bytes(
            _read(args.training_report, 2 * 1024 * 1024), maximum_bytes=2 * 1024 * 1024
        )
    model = load_neutral_json_bytes(
        _read(args.model, 16 * 1024 * 1024), source_path=str(args.model)
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        _read(args.request, 128 * 1024)
    )
    candidates, prices, terminal, history, material = (
        read_design_experiment_with_material_history(args.experiment)
    )
    report = run_rc_control_candidate_strategy(
        model,
        candidates,
        request,
        strategy=args.strategy,
        policy=policy,
        training_report=training,
        prices=prices,
        history_limits=history,
        material_limits=material,
        terminal_limits=terminal,
        source_revision=args.source_revision,
        output_directory=args.output,
        full_analysis_budget=args.full_analysis_budget,
        ranking_strategy=args.ranking_strategy,
        reuse_line_search_assembly=args.reuse_line_search_assembly,
    )
    runtime = {
        "schema_version": "experimental-rc-control-candidate-strategy-runtime.v1",
        "source_revision": args.source_revision,
        "strategy": args.strategy,
        "report_hash": report["report_hash"],
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "scope": "argument_parsing_input_reads_preparation_ranking_full_reference_and_report_persistence",
        "excludes": [
            "interpreter_startup_and_module_imports",
            "runtime_sidecar_and_stdout",
            "transport_and_workbench_review",
        ],
        "new_training_fit_count": 0,
        "net_savings_proved": False,
    }
    with (args.output / "strategy-runtime.json").open("x") as stream:
        json.dump(runtime, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(runtime, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
