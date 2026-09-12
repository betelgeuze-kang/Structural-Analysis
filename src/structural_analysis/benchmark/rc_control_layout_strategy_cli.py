"""Execute one full-layout strategy with original reference records and full costs."""

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
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_layout_search as search
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.benchmark.rc_control_layout_learning import (
    RCControlLayoutPolicy,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def read_layout_experiment(path: Path):
    value = strict_json_object_bytes(_read(path, 1024**2), maximum_bytes=1024**2)
    if (
        set(value)
        != {
            "schema_version",
            "candidates",
            "prices",
            "history_limits",
            "material_limits",
            "terminal_limits",
        }
        or value["schema_version"] != "rc-control-layout-experiment.v1"
    ):
        raise ValueError("exact layout experiment fields and schema required")
    rows = value["candidates"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        raise ValueError("one to sixteen layout candidates required")
    root = path.resolve().parent
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"candidate_id", "model_path"}:
            raise ValueError("candidate_id and model_path required")
        name = row["model_path"]
        if not isinstance(name, str) or "\\" in name:
            raise ValueError("relative JSON model path required")
        relative = Path(name)
        if (
            relative.is_absolute()
            or relative.suffix != ".json"
            or ".." in relative.parts
        ):
            raise ValueError("relative JSON model path required")
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ValueError("model path escapes experiment directory")
        model = load_neutral_json_bytes(
            _read(target, 16 * 1024**2), source_path=str(target)
        )
        candidates.append(search.RCControlLayoutCandidate(row["candidate_id"], model))
    return dict(
        candidates=tuple(candidates),
        prices=design.FiberFrameMaterialPrices(**value["prices"]),
        history_limits=design.FiberFrameHistoryLimits(**value["history_limits"]),
        material_limits=design.FiberFrameMaterialHistoryLimits(
            **value["material_limits"]
        ),
        terminal_limits=None
        if value["terminal_limits"] is None
        else design.FiberFrameTerminalLimits(**value["terminal_limits"]),
    )


def main(argv=None):
    wall, cpu = perf_counter_ns(), process_time_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("model", "request", "experiment", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument(
        "--strategy", choices=("price_order", "learned_order"), required=True
    )
    parser.add_argument(
        "--execution", choices=("full", "cost-pruned", "staged"), required=True
    )
    parser.add_argument("--prefix-target-count", type=int)
    parser.add_argument("--full-analysis-budget", type=int, default=3)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--training-report", type=Path)
    args = parser.parse_args(argv)
    if (args.execution == "staged") != (args.prefix_target_count is not None):
        raise ValueError("prefix target count is required only for staged execution")
    if args.strategy == "price_order" and (
        args.policy is not None or args.training_report is not None
    ):
        raise ValueError("price-only execution must not receive learned artifacts")
    if args.strategy == "learned_order" and (
        args.policy is None or args.training_report is None
    ):
        raise ValueError(
            "learned execution requires policy and historical training report"
        )
    policy = training = None
    if args.strategy == "learned_order":
        policy = RCControlLayoutPolicy(_read(args.policy, 2 * 1024**2).decode("utf-8"))
        training = strict_json_object_bytes(
            _read(args.training_report, 2 * 1024**2), maximum_bytes=2 * 1024**2
        )
    model = load_neutral_json_bytes(
        _read(args.model, 16 * 1024**2), source_path=str(args.model)
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        _read(args.request, 128 * 1024)
    )
    inputs = read_layout_experiment(args.experiment)
    runner = {
        "full": search.run_control_layout_strategy,
        "cost-pruned": search.run_control_layout_cost_pruned_strategy,
        "staged": search.run_control_layout_staged_strategy,
    }[args.execution]
    if args.execution == "staged":
        inputs["prefix_target_count"] = args.prefix_target_count
    report = runner(
        baseline=model,
        request=request,
        **inputs,
        policy=policy,
        training_report=training,
        strategy=args.strategy,
        source_revision=args.source_revision,
        output_directory=args.output,
        full_analysis_budget=args.full_analysis_budget,
    )
    runtime = {
        "schema_version": "experimental-rc-control-layout-strategy-runtime.v1",
        "source_revision": args.source_revision,
        "strategy": args.strategy,
        "execution": args.execution,
        "report_hash": report["report_hash"],
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "scope": "argument_parsing_input_reads_preparation_strategy_and_report_persistence",
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
    print(json.dumps(runtime, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
