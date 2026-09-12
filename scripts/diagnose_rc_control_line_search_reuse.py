"""Serial research experiment; never changes the default solver implementation.

Only the exact RC control adapter may reuse an immediately preceding line-search
assembly at byte-identical coordinates in the next primary iteration. Final and
terminal observations remain fresh. Run in a dedicated process: the experiment
temporarily replaces a module function, and is not a concurrent service API.
"""

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter_ns
from unittest.mock import patch

import numpy as np

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear import newton


class ImmediateLineSearchReuse:
    """One-entry, one-use cache, restricted to an explicitly supplied exact type."""

    def __init__(self, dispatch, *, adapter_type=Adapter):
        self.dispatch = dispatch
        self.adapter_type = adapter_type
        self.pending = None
        self.hits = 0
        self.dispatches = 0

    def __call__(self, problem, coordinates, *, compensation=None, phase, recorder=None):
        pending, self.pending = self.pending, None
        eligible = type(problem) is self.adapter_type and compensation is None
        key = None
        if eligible:
            values = np.asarray(coordinates)
            key = (values.dtype.str, values.shape, values.tobytes())
        if (
            eligible
            and phase == "primary_iteration"
            and pending is not None
            and pending[0] is problem
            and pending[1] == key
        ):
            self.hits += 1
            return pending[2]
        self.dispatches += 1
        result = self.dispatch(
            problem, coordinates, compensation=compensation, phase=phase,
            recorder=recorder,
        )
        if eligible and phase == "line_search":
            self.pending = (problem, key, tuple(value.copy() for value in result))
        return result


YIELDED_TARGETS_M = (
    -0.0004, -0.0008, -0.0012000000000000001, -0.0016, -0.002,
    -0.0024000000000000002, -0.0028, -0.0032, -0.0036, -0.004, -0.0044,
    -0.0048000000000000004, -0.0052, -0.0056, -0.006, -0.0056,
)


def experiment_request(case, constant):
    if case not in ("small", "yielded-prefix"):
        raise ValueError("unknown experiment case")
    if case == "yielded-prefix" and constant:
        raise ValueError("yielded prefix does not declare a constant preload")
    request = BoundedRCFiberDirectControlRequest(
        7, YIELDED_TARGETS_M if case == "yielded-prefix" else (-1e-6, -2e-6, 1e-6),
        allow_reversals=True, maximum_reversals=3,
        maximum_targets=16 if case == "yielded-prefix" else 255,
        constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),) if constant else (),
    )
    return replace(request, solver_config=replace(
        request.solver_config,
        newton=replace(request.solver_config.newton, terminal_polishing=True,
                       max_iterations=40 if case == "yielded-prefix" else
                       request.solver_config.newton.max_iterations),
    ))


def run(output: Path, repetitions: int, case: str = "small", arithmetic: str = "both"):
    if type(repetitions) is not int or repetitions < 2 or repetitions % 2:
        raise ValueError("a positive even number of order-balanced repetitions required")
    experiment_request(case, False)  # validate before creating output
    if arithmetic not in ("both", "binary64", "retained"):
        raise ValueError("unknown arithmetic selection")
    # Refuse existing output; raw evidence is never overwritten.
    output.mkdir(parents=True, exist_ok=False)
    source_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    model_path = Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    model = load_neutral_json(model_path)
    identity = "sha256:" + hashlib.sha256(b"deterministic-secant-reuse-study").hexdigest()
    rows = []
    profiles = (False, True) if arithmetic == "both" else (arithmetic == "retained",)
    for retained in profiles:
        for constant in ((False,) if case == "yielded-prefix" else (False, True)):
            request = experiment_request(case, constant)
            arithmetic_kwargs = learning._arithmetic_kwargs(
                learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
            ) if retained else {}
            for repetition in range(repetitions):
                pair = {}
                order = (False, True) if repetition % 2 == 0 else (True, False)
                for enabled in order:
                    name = f"retained-{retained}-constant-{constant}-rep-{repetition}-{enabled}"
                    destination = output / name
                    reuse = ImmediateLineSearchReuse(newton.assemble_vector)
                    dispatch = reuse if enabled else newton.assemble_vector
                    started = perf_counter_ns()
                    with patch.object(newton, "assemble_vector", dispatch):
                        report = runtime.benchmark_rc_control_seed_paths(
                            model, request, source_revision=source_revision,
                            output_directory=destination, proposal=runtime.secant_seed,
                            proposal_identity=identity, record_assembly_work=True,
                            **arithmetic_kwargs,
                        )
                    elapsed = perf_counter_ns() - started
                    if not (report["reference_repeat_exact"] and
                            report["all_execution_work_reported"]):
                        raise ValueError("incomplete or nonrepeatable full path")
                    if not all(v["full_history_pass"] for v in report["comparisons"].values()):
                        raise ValueError("a strategy failed its full-history comparison")
                    steps = {str(p.relative_to(destination)): p.read_bytes()
                             for p in destination.glob("*/*-step.json")}
                    calls = 0
                    for step in steps:
                        path = destination / step.replace("-step.json", "-outcome.json")
                        work = json.loads(path.read_bytes())["newton_assembly_work"]
                        if work["exception_count"] or work["in_flight_count"]:
                            raise ValueError("assembly failure in completed experiment")
                        calls += work["call_count"]
                    pair[enabled] = (steps, report, {
                        "directory": name, "wall_ns": elapsed,
                        "step_count": len(steps), "actual_newton_dispatches": calls,
                        "reused_dispatches": reuse.hits if enabled else 0,
                    })
                baseline, reused = pair[False], pair[True]
                if not baseline[0] or baseline[0] != reused[0]:
                    raise ValueError("baseline/reuse native steps differ")
                if baseline[1]["comparisons"] != reused[1]["comparisons"]:
                    raise ValueError("baseline/reuse full-history comparisons differ")
                if (baseline[2]["actual_newton_dispatches"] !=
                        reused[2]["actual_newton_dispatches"] +
                        reused[2]["reused_dispatches"]):
                    raise ValueError("actual dispatch accounting does not close")
                rows.append({
                    "retained": retained, "constant": constant,
                    "repetition": repetition, "order": list(order),
                    "baseline": baseline[2], "reuse": reused[2],
                    "native_step_bytes_exact": True,
                    "whole_benchmark_wall_ratio": reused[2]["wall_ns"] / baseline[2]["wall_ns"],
                })
                print(json.dumps(rows[-1]), flush=True)
    summary = {
        "schema": "rc-immediate-line-search-reuse-experiment.v1",
        "base_revision": source_revision,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "scope": "single authored L-frame; declared arithmetic/preload configurations",
        "case": case,
        "arithmetic_selection": arithmetic,
        "timing_scope": "whole benchmark including serialization, verification, and recording",
        "default_solver_changed": False, "learned_policy": False,
        "independent_physical_validation": False,
        "concurrent_execution_supported": False,
        "rows": rows,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repetitions", type=int, default=4)
    parser.add_argument("--case", choices=("small", "yielded-prefix"), default="small")
    parser.add_argument("--arithmetic", choices=("both", "binary64", "retained"), default="both")
    args = parser.parse_args()
    run(args.output, args.repetitions, args.case, args.arithmetic)
