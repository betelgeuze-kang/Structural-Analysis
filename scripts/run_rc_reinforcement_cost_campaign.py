"""Predeclared four-case, order-balanced internal reinforcement cost observation."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_process_costs import (
    compare_rc_control_process_costs,
    PROCESS_SCOPE,
)
from structural_analysis.benchmark.rc_control_strategy_costs import (
    compare_rc_control_strategy_costs,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.io.neutral.loader import load_neutral_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output
    root.mkdir(parents=True, exist_ok=False)
    start = perf_counter_ns()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_bytes(value))

    def candidate(name, top, bottom):
        return design.FiberFrameDesignCandidate(
            name,
            (
                design.FiberFrameSectionChange(
                    "RC1", top_bar_area_m2=top, bottom_bar_area_m2=bottom
                ),
            ),
        )

    def experiment(candidates):
        return dict(
            schema_version="rc-fiber-design-experiment.v3",
            candidates=[c.to_dict() for c in candidates],
            prices=asdict(
                design.FiberFrameMaterialPrices(
                    100,
                    2,
                    "USD",
                    "2026-09-20",
                    "synthetic campaign prices, not a quote",
                )
            ),
            terminal_limits=None,
            history_limits=asdict(design.FiberFrameHistoryLimits(1, 0.0008)),
            material_history_limits=asdict(
                design.FiberFrameMaterialHistoryLimits(1, 1, 1)
            ),
        )

    train = tuple(
        candidate(f"train-{i}-{j}", top, bottom)
        for i, top in enumerate((0.00018, 0.0003, 0.00042))
        for j, bottom in enumerate((0.00022, 0.00036, 0.0005))
    )
    evaluate = (
        candidate("cheap", 0.0002, 0.00025),
        candidate("middle", 0.0003, 0.0004),
        candidate("costly", 0.00035, 0.00045),
    )
    base = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
    protocol = {
        "schema_version": "rc-reinforcement-cost-campaign.v1",
        "source_revision": source,
        "cases": [],
        "orders": [["price_order", "learned_order"], ["learned_order", "price_order"]],
        "budget": 3,
        "independent_generalization": False,
        "preparation_transport_review_in_strategy_intervals": False,
    }
    for width in (0.32, 0.48):
        for label, targets in [
            ("small", (-0.001, -0.002, 0.001)),
            ("large", (-0.004, -0.008, 0.004)),
        ]:
            name = f"w{int(width * 100)}-{label}"
            model = design.apply_fiber_frame_section_changes(
                base,
                design.FiberFrameDesignCandidate(
                    "width", (design.FiberFrameSectionChange("RC1", width_m=width),)
                ),
            )
            request = BoundedRCFiberDirectControlRequest(
                4,
                targets,
                allow_reversals=True,
                maximum_reversals=2,
                constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
            )
            folder = root / name
            inputs = {
                "training-model.json": model.canonical_payload(),
                "evaluation-model.json": design.apply_fiber_frame_section_changes(
                    model, candidate("evaluation", 0.00032, 0.00042)
                ).canonical_payload(),
                "training-experiment.json": experiment(train),
                "evaluation-experiment.json": experiment(evaluate),
                "request.json": request.to_dict(),
            }
            for file, value in inputs.items():
                save(folder / file, value)
            protocol["cases"].append(
                {
                    "id": name,
                    "width_m": width,
                    "targets_m": targets,
                    "inputs": {
                        file: {
                            "sha256": _sha(_bytes(value)),
                            "byte_length": len(_bytes(value)),
                        }
                        for file, value in inputs.items()
                    },
                }
            )
    save(root / "protocol.json", protocol)
    (root / "driver.py").write_bytes(Path(__file__).read_bytes())
    cases = []

    def execute(folder, label, module, args):
        wall = perf_counter_ns()
        with (
            (folder / (label + ".stdout")).open("wb") as out,
            (folder / (label + ".stderr")).open("wb") as err,
        ):
            result = subprocess.run(
                [sys.executable, "-m", module, *args], stdout=out, stderr=err
            )
        receipt = {
            "return_code": result.returncode,
            "wall_ns": perf_counter_ns() - wall,
            "arguments": args,
            "module": module,
        }
        save(folder / (label + ".process.json"), receipt)
        if result.returncode:
            raise ValueError(f"{label} exited {result.returncode}")
        return receipt

    for case in protocol["cases"]:
        folder = root / case["id"]
        record = {"id": case["id"], "status": "started", "pairs": 0}
        cases.append(record)
        wall = perf_counter_ns()
        try:
            common = [
                "--request",
                str(folder / "request.json"),
                "--source-revision",
                source,
            ]
            training = execute(
                folder,
                "training",
                "structural_analysis.benchmark.rc_control_candidate_cli",
                [
                    "train",
                    "--model",
                    str(folder / "training-model.json"),
                    "--experiment",
                    str(folder / "training-experiment.json"),
                    "--output",
                    str(folder / "training"),
                    "--reinforcement-features",
                    *common,
                ],
            )
            pairs = []
            processes = []
            for repetition, order in enumerate(protocol["orders"]):
                pair = {}
                for strategy in order:
                    label = f"r{repetition}-{strategy}"
                    destination = folder / label
                    args = [
                        "--strategy",
                        strategy,
                        "--model",
                        str(folder / "evaluation-model.json"),
                        "--experiment",
                        str(folder / "evaluation-experiment.json"),
                        "--output",
                        str(destination),
                        "--full-analysis-budget",
                        "3",
                        *common,
                    ]
                    if strategy == "learned_order":
                        args += [
                            "--policy",
                            str(folder / "training/policy.json"),
                            "--training-report",
                            str(folder / "training/training.json"),
                        ]
                    process = execute(
                        folder,
                        label,
                        "structural_analysis.benchmark.rc_control_candidate_strategy_cli",
                        args,
                    )
                    values = {
                        key: json.loads((destination / file).read_bytes())
                        for key, file in [
                            ("report", "result.json"),
                            ("plan", "plan.json"),
                            ("runtime", "strategy-runtime.json"),
                        ]
                    }
                    pair[strategy] = values
                    processes.append(
                        {
                            "report_hash": values["report"]["report_hash"],
                            "runtime_digest": _sha(_bytes(values["runtime"])),
                            "wall_ns": process["wall_ns"],
                            "return_code": 0,
                            "scope": PROCESS_SCOPE,
                        }
                    )
                pairs.append(pair)
                record["pairs"] = len(pairs)
            cli = compare_rc_control_strategy_costs(pairs)
            enclosing = compare_rc_control_process_costs(pairs, processes)
            save(folder / "cli-costs.json", cli)
            save(folder / "process-costs.json", enclosing)
            save(folder / "process-observations.json", processes)
            # Existing report charges the inner training interval once. Also show
            # the complete enclosing training process without double counting.
            inclusive = (
                enclosing["learned_process_interval_sum_ns"] + training["wall_ns"]
            )
            record.update(
                status="completed",
                uncomparable_pair_count=enclosing["uncomparable_pair_count"],
                price_process_wall_ns=enclosing["price_process_interval_sum_ns"],
                learned_process_wall_ns=enclosing["learned_process_interval_sum_ns"],
                training_process_wall_ns=training["wall_ns"],
                full_process_inclusive_ratio=inclusive
                / enclosing["price_process_interval_sum_ns"]
                if not enclosing["uncomparable_pair_count"]
                else None,
                selections=[
                    {
                        s: p[s]["report"]["arms"][s]["selected_candidate_id"]
                        for s in ("price_order", "learned_order")
                    }
                    for p in pairs
                ],
            )
        except Exception as exc:
            record.update(
                status="failed",
                error_type=type(exc).__name__,
                error=str(exc),
                full_process_inclusive_ratio=None,
            )
        record["case_wall_ns"] = perf_counter_ns() - wall
        summary = {
            "protocol_sha256": _sha((root / "protocol.json").read_bytes()),
            "cases": cases,
            "planned_case_count": len(protocol["cases"]),
            "completed_case_count": sum(c["status"] == "completed" for c in cases),
            "campaign_wall_ns": perf_counter_ns() - start,
            "net_savings_proved": False,
            "independent_generalization": False,
            "aggregate_ratio": None,
        }
        save(root / "summary.json", summary)
        print(json.dumps(record), flush=True)
    inventory = {
        str(p.relative_to(root)): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "byte_length": p.stat().st_size,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    save(root / "inventory.json", inventory)
    return 0 if all(c["status"] == "completed" for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
