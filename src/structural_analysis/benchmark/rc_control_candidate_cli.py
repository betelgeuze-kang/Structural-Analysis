"""Train and compare rankings on a fixed RC displacement-control path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    read_design_experiment_with_material_history,
)
from structural_analysis.benchmark.rc_control_candidate_learning import (
    RCControlCandidatePolicy,
    train_rc_control_candidate_policy,
)
from structural_analysis.benchmark.rc_control_candidate_search import (
    compare_rc_control_candidate_search,
)
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("train", "search"):
        sub = commands.add_parser(name)
        for field in ("model", "request", "experiment", "output"):
            sub.add_argument("--" + field, type=Path, required=True)
        sub.add_argument("--source-revision", required=True)
        if name == "train":
            sub.add_argument("--ridge", type=float, default=1.0)
            sub.add_argument("--ood-margin", type=float, default=0.0)
        else:
            sub.add_argument("--policy", type=Path, required=True)
            sub.add_argument("--training-report", type=Path, required=True)
            sub.add_argument("--full-analysis-budget", type=int, default=3)
            sub.add_argument("--evaluate-exhaustive-oracle", action="store_true")
    args = parser.parse_args(argv)
    model = load_neutral_json_bytes(
        _read(args.model, 16 * 1024 * 1024), source_path=str(args.model)
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        _read(args.request, 128 * 1024)
    )
    candidates, prices, terminal, history, material = (
        read_design_experiment_with_material_history(args.experiment)
    )
    common = dict(
        baseline=model,
        candidates=candidates,
        request=request,
        history_limits=history,
        material_limits=material,
        source_revision=args.source_revision,
        output_directory=args.output,
    )
    if args.command == "train":
        policy, report = train_rc_control_candidate_policy(
            **common, ridge=args.ridge, ood_margin=args.ood_margin
        )
        output = {
            "policy_hash": policy.policy_hash,
            "training_report_hash": report["report_hash"],
            "sample_count": report["sample_count"],
            "net_savings_proved": False,
        }
    else:
        if prices is None:
            raise ValueError("search requires a common price table")
        policy = RCControlCandidatePolicy(
            _read(args.policy, 2 * 1024 * 1024).decode("utf-8")
        )
        training = json.loads(_read(args.training_report, 2 * 1024 * 1024))
        report = compare_rc_control_candidate_search(
            **common,
            prices=prices,
            terminal_limits=terminal,
            policy=policy,
            training_report=training,
            full_analysis_budget=args.full_analysis_budget,
            evaluate_exhaustive_oracle=args.evaluate_exhaustive_oracle,
        )
        output = {
            "report_hash": report["report_hash"],
            "candidate_denominator": report["candidate_denominator"],
            "arms": report["arms"],
            "workbench_search_report": str(args.output / "result.json"),
            "workbench_design_reports": {
                name: str(args.output / arm["comparison_path"])
                for name, arm in report["arms"].items()
            },
            "workbench_scope": "configure rcControlSearchUrl with a same-origin result.json endpoint; artifact hosting is required",
            "net_savings_proved": False,
        }
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
