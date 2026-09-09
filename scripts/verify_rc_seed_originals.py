"""Replay stored RC seed-study transitions, including independent arm preloads.

This audit invokes constitutive assembly at original coordinates, never Newton
or a new accepted solve. It is reproducibility evidence, not an external oracle.
"""

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    load_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadStepAdapter,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    _arithmetic_kwargs,
    _learning_compiled_arithmetic,
    RETAINED_LEARNING_ARITHMETIC_PROFILE,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    from structural_analysis.api.frame3d_direct_control_request import (
        strict_json_object_bytes,
    )

    maximum = 256 * 1024**2
    require(path.stat().st_size <= maximum, "original artifact byte budget exceeded")
    return strict_json_object_bytes(path.read_bytes(), maximum_bytes=maximum)


def checked(path, key):
    value = read(path)
    payload = {k: v for k, v in value.items() if k != key}
    require(value[key] == _sha(_bytes(payload)), f"original {key} differs")
    return value


def verify(study, model_path, request_path):
    started = perf_counter_ns()
    study = Path(study)
    report = checked(study / "comparison.json", "report_hash")
    require(
        report["absolute_tolerance"] == 1e-10 and report["relative_tolerance"] == 1e-8,
        "predeclared comparison tolerances differ",
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        Path(request_path).read_bytes()
    )
    require(
        bool(request.constant_nodal_loads), "explicit constant-loaded study required"
    )
    require(report["request"] == request.to_dict(), "original request differs")
    profile = RETAINED_LEARNING_ARITHMETIC_PROFILE
    require(
        all(report.get(k) == v for k, v in _arithmetic_kwargs(profile).items()),
        "original retained arithmetic profile differs",
    )
    model = load_neutral_json(Path(model_path))
    require(
        model.canonical_model_checksum == report["model_checksum"],
        "original model differs",
    )
    compiled, blockers, _ = public._compile(model)
    require(compiled is not None and not blockers, "unsupported original model")
    compiled = _learning_compiled_arithmetic(
        api._with_constant_loading(compiled, request.constant_nodal_loads), profile
    )
    problem = compiled.problem
    require(
        problem.contract_hash == report["compiled_problem_contract_hash"],
        "compiled constant loading differs",
    )
    require(
        set(report["arm_order"]) == {"reference", "secant"},
        "reference/secant audit scope required",
    )
    spec = importlib.util.spec_from_file_location(
        "original_rational_audit",
        Path(__file__).with_name("verify_rc_rational_assembly.py"),
    )
    if spec is None or spec.loader is None:
        raise ValueError("rational record auditor unavailable")
    rational = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rational)
    work: Counter[str] = Counter()
    audit_work: Counter[str] = Counter()
    rows: dict[str, Any] = {}
    paths: dict[str, Any] = {}
    for name in [*report["arm_order"], "fresh-reference"]:
        root = study / name
        path = checked(root / "path.json", "path_hash")
        require(
            path["source_problem_hash"] == problem.contract_hash, "path problem differs"
        )
        summary = (
            report["fresh_reference"]
            if name == "fresh-reference"
            else report["arms"][name]
        )
        require(
            summary
            == {
                k: v
                for k, v in path.items()
                if k
                not in ("response_history", "terminal_checkpoint", "preload_response")
            },
            "stored path summary differs",
        )
        require(
            path["status"] == "complete"
            and path["failure"] is None
            and len(path["entries"])
            == len(path["response_history"])
            == len(request.targets_m),
            "incomplete original path; repetition admission unavailable",
        )
        parent = initial_stateful_fiber_frame2d_checkpoint(problem)
        arm_work: Counter[str] = Counter()
        invocations = path["preload_invocations"]
        require(
            len(invocations) == 1, "each arm must have exactly one original preload"
        )
        transitions: list[tuple[int | None, Any, str, Any]] = [
            (None, invocations[0], "preload", path["preload_response"])
        ]
        for index, entry in enumerate(path["entries"]):
            require(
                entry["target_index"] == index
                and entry["target_m"] == request.targets_m[index],
                "target order differs",
            )
            require(
                len(entry["invocations"]) == 1,
                "multiple original attempts require separate failure audit",
            )
            transitions.append(
                (
                    index,
                    entry["invocations"][0],
                    f"{index:03d}-1",
                    path["response_history"][index],
                )
            )
        for transition_index, invocation, stem, response in transitions:
            require(
                invocation == read(root / (stem + "-outcome.json")),
                "original invocation differs",
            )
            reservation = read(root / (stem + "-started.json"))
            require(
                reservation["status"] == "started"
                and reservation["unknown_work"] is True,
                "original numerical reservation absent",
            )
            require(
                invocation["status"] == "returned"
                and invocation["committed"] is True
                and invocation["unknown_work"] is False,
                "original numerical work unavailable",
            )
            step = read(root / (stem + "-step.json"))
            require(
                step["parent_checkpoint"] == parent.to_dict(),
                "original parent chain differs",
            )
            require(step["committed"] is True, "uncommitted original transition")
            solution = step["trial_solution"]
            metrics = solution["metrics"]
            expected_work = dict(
                core_calls=1,
                newton_iterations=metrics["iteration_count"],
                linear_solves=metrics["linear_solve_count"],
            )
            require(
                all(type(v) is int and v >= 0 for v in expected_work.values())
                and invocation["work"] == expected_work,
                "original work counters differ",
            )
            require(
                all(
                    metrics[k] is True
                    for k in (
                        "contract_pass",
                        "increment_gate_passed",
                        "residual_gate_passed",
                    )
                ),
                "original Newton gates failed",
            )
            arm_work.update(expected_work)
            adapter: Any
            if transition_index is None:
                identity = _sha(_bytes(step))
                attempt = read(root / "preload-attempt.json")
                require(
                    attempt["step"] == step and attempt["solver_work"] == metrics,
                    "original preload attempt differs",
                )
                adapter = StatefulFiberFrame2DLoadStepAdapter(problem, parent, 0.0)
                high, low = adapter.absolute_coordinates(
                    np.asarray(metrics["free_displacements_m"]),
                    None
                    if metrics.get("free_displacement_compensation_m") is None
                    else np.asarray(metrics["free_displacement_compensation_m"]),
                )
                factor = 0.0
            else:
                identity = canonical_hash(
                    {k: v for k, v in step.items() if k != "step_hash"}
                )
                require(step["step_hash"] == identity, "original step identity differs")
                adapter = StatefulFiberFrame2DDisplacementControlStepAdapter(
                    problem,
                    parent,
                    request.control_global_dof,
                    request.targets_m[transition_index],
                    request.solver_config,
                )
                coordinates, compensation = adapter.absolute_coordinates(
                    np.asarray(solution["solver_increment_coordinates_m"]),
                    None
                    if solution.get("solver_increment_coordinate_compensation_m")
                    is None
                    else np.asarray(
                        solution["solver_increment_coordinate_compensation_m"]
                    ),
                )
                require(
                    np.array_equal(coordinates, solution["augmented_coordinates_m"])
                    and np.array_equal(
                        compensation, solution["augmented_coordinate_compensation_m"]
                    ),
                    "original absolute coordinates differ",
                )
                factor = adapter.load_factor_at(coordinates, compensation)
                high, low = coordinates[:-1], compensation[:-1]
            require(
                response["source_step_hash"] == identity,
                "original response step binding differs",
            )
            child = load_stateful_fiber_frame2d_checkpoint_bytes(
                _bytes(step["accepted_checkpoint"]), problem
            )
            if (
                child.free_coordinates_m is None
                or child.free_coordinate_compensation_m is None
            ):
                raise ValueError("original native twofold coordinates unavailable")
            require(
                child.parent_state_hash == parent.state_hash
                and child.epoch == parent.epoch + 1
                and child.load_factor == factor
                and np.array_equal(child.free_coordinates_m, high)
                and np.array_equal(child.free_coordinate_compensation_m, low),
                "original native coordinates differ",
            )
            recorder = MaterialTrialRuntimeRecorder()
            fresh = assemble_stateful_fiber_frame2d(
                problem,
                parent,
                target_load_factor=factor,
                trial_free_coordinates_m=high,
                trial_free_coordinate_compensation_m=low,
                material_runtime=recorder,
            )
            audit_work["assembly_replays"] += 1
            audit_work["material_integrations"] += recorder.call_count
            require(
                recorder.coverage_complete, "assembly replay material costs unavailable"
            )
            require(
                _bytes(fresh.to_dict()) == _bytes(step["trial_assembly"]),
                "original assembly replay differs",
            )
            require(
                tuple(fresh.trial_element_states) == child.element_states
                and np.array_equal(
                    fresh.global_displacements, child.global_displacements
                ),
                "original native state replay differs",
            )
            rational.verify_assembly(problem, step["trial_assembly"])
            audit_work["rational_record_rebuilds"] += 1
            require(
                _bytes(api._response_rows(compiled, fresh, child, identity))
                == _bytes(response),
                "original physical response replay differs",
            )
            parent = child
        require(
            path["terminal_checkpoint"] == parent.to_dict(),
            "original terminal checkpoint differs",
        )
        work.update(arm_work)
        recovery = read(root / "preload-recovery-outcome.json")
        require(
            recovery["status"] == "returned", "original preload recovery incomplete"
        )
        nested_times = {}
        for clock in ("wall", "cpu"):
            nested_times["core_" + clock + "_ns"] = sum(
                i[1][clock + "_ns"] for i in transitions
            )
            nested_times["proposal_" + clock + "_ns"] = sum(
                e["proposal_" + clock + "_ns"] for e in path["entries"]
            )
            nested_times["recovery_" + clock + "_ns"] = recovery[clock + "_ns"] + sum(
                e["recovery_" + clock + "_ns"] for e in path["entries"]
            )
            values = [
                nested_times[k + "_" + clock + "_ns"]
                for k in ("core", "proposal", "recovery")
            ]
            require(
                all(type(v) is int and v >= 0 for v in values)
                and sum(values) <= path[clock + "_ns"],
                "original nested times differ",
            )
        rows[name] = dict(
            work=arm_work,
            **nested_times,
            path_wall_ns=path["wall_ns"],
            path_cpu_ns=path["cpu_ns"],
            accepted_targets=path["accepted_target_count"],
        )
        paths[name] = path
    histories = {
        name: [p["preload_response"], *p["response_history"]]
        for name, p in paths.items()
    }
    comparisons = {}
    for name in report["arm_order"]:
        structure, _, _, within = _numeric_payload_difference(
            histories["fresh-reference"],
            histories[name],
            absolute_tolerance=report["absolute_tolerance"],
            relative_tolerance=report["relative_tolerance"],
        )
        passed = structure and within
        require(
            report["comparisons"][name]["full_history_pass"] == passed,
            "stored full comparison differs",
        )
        comparisons[name] = passed
    exact = (
        _bytes(histories["reference"]) == _bytes(histories["fresh-reference"])
        and paths["reference"]["terminal_checkpoint"]
        == paths["fresh-reference"]["terminal_checkpoint"]
    )
    require(
        report["reference_repeat_exact"] == exact, "stored reference repeat differs"
    )
    return dict(
        schema_version="rc-constant-seed-original-audit.v1",
        original_records_reproduced=True,
        repeat_admissible=exact and all(comparisons.values()),
        comparisons=comparisons,
        original_work=dict(work),
        audit_work={**audit_work, "newton_solves": 0, "state_commits": 0},
        paths=rows,
        elapsed_ns=perf_counter_ns() - started,
        independent_physical_validation=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.study, args.model, args.request)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
