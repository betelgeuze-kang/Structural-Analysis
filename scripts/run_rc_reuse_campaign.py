"""Serial multi-case research campaign; retain failed cases and all enclosing costs.

Each case invokes the existing full-history-gated experiment. A campaign never
averages only successful speed ratios or claims independent validation.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from time import perf_counter_ns

from scripts import diagnose_rc_control_line_search_reuse as experiment
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_design import _bytes as canonical_bytes
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model_ir.validation import load_json_object_strict


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _receipt(path):
    _require(
        path.resolve().is_relative_to(path.parent.resolve()),
        "experiment receipt escapes its result directory",
    )
    _require(path.is_file(), "experiment returned without its success receipt")
    _require(path.stat().st_size <= 64 * 1024 * 1024, "experiment receipt exceeds byte limit")
    return load_json_object_strict(path)


def _step_hashes(directory):
    result = {}
    for path in sorted(directory.glob("*/*-step.json")):
        _require(
            path.resolve().is_relative_to(directory.resolve()),
            "experiment native step escapes its benchmark",
        )
        relative = path.relative_to(directory).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result[relative] = digest.hexdigest()
    _require(result, "experiment has no native step artifacts")
    return result


def _assembly_counts(directory, steps):
    """Recount dispatches from the saved outcome paired with each native step."""
    dispatches = reuse_hits = 0
    for relative in steps:
        outcome = directory / (relative.removesuffix("-step.json") + "-outcome.json")
        _require(
            outcome.resolve().is_relative_to(directory.resolve()),
            "experiment assembly outcome escapes its benchmark",
        )
        payload = _receipt(outcome)
        work = payload.get("newton_assembly_work")
        _require(
            payload.get("status") == "returned"
            and type(work) is dict
            and work.get("schema_version") == "vector-newton-assembly-dispatch-work.v1"
            and work.get("scope") == "vector_newton_problem_assembly_dispatches_only"
            and type(work.get("calls")) is list,
            "experiment assembly outcome is incomplete",
        )
        calls = work["calls"]
        _require(
            all(
                type(call) is dict
                and type(call.get("ordinal")) is int
                and call["ordinal"] == ordinal
                and type(call.get("phase")) is str
                and bool(call["phase"])
                and call.get("status") == "returned"
                and type(call.get("compensated")) is bool
                for ordinal, call in enumerate(calls, 1)
            )
            and all(
                type(work.get(key)) is int and work[key] == count
                for key, count in (
                    ("call_count", len(calls)),
                    ("returned_count", len(calls)),
                    ("exception_count", 0),
                    ("in_flight_count", 0),
                )
            ),
            "experiment assembly dispatch record is malformed",
        )
        hits = work.get("line_search_reuse_hit_count", 0)
        _require(
            type(hits) is int and hits >= 0,
            "experiment assembly reuse count is malformed",
        )
        dispatches += len(calls)
        reuse_hits += hits
    return dispatches, reuse_hits


def _comparison(directory, *, source, request, constant, compiler_profile,
                compiled_problem_contract_hash):
    report = _receipt(directory / "comparison.json")
    identity = report.get("report_hash")
    unsigned = {key: value for key, value in report.items() if key != "report_hash"}
    _require(
        identity == "sha256:" + hashlib.sha256(canonical_bytes(unsigned)).hexdigest(),
        "experiment comparison hash mismatch",
    )
    _require(
        report.get("schema_version")
        == f"experimental-rc-control-seed-comparison.v{2 if constant else 1}"
        and report.get("source_revision") == source
        and report.get("source_revision_is_attestation") is False
        and canonical_bytes(report.get("request")) == canonical_bytes(request.to_dict())
        and report.get("arm_order") == ["reference", "secant", "proposal"]
        and report.get("proposal_requested") is True
        and report.get("reference_repeat_exact") is True
        and report.get("all_execution_work_reported") is True,
        "experiment comparison source or completion mismatch",
    )
    if compiler_profile is not None:
        _require(
            report.get("compiler_profile") == compiler_profile
            and report.get("compiled_problem_contract_hash")
            == compiled_problem_contract_hash,
            "experiment comparison compiler profile or problem mismatch",
        )
    arms = report.get("arms")
    comparisons = report.get("comparisons")
    _require(
        type(arms) is dict
        and type(comparisons) is dict
        and set(arms) == set(comparisons) == {"reference", "secant", "proposal"}
        and all(type(arm) is dict and arm.get("status") == "complete" for arm in arms.values())
        and type(report.get("fresh_reference")) is dict
        and report["fresh_reference"].get("status") == "complete"
        and all(
            type(value) is dict and value.get("full_history_pass") is True
            for value in comparisons.values()
        ),
        "experiment comparison full history or work is incomplete",
    )
    return comparisons


def _validate_case_receipt(directory, values, *, source, repetitions, arithmetic,
                           record_assembly_timing):
    """Check saved, source-bound work before calling a campaign case completed.

    This checks persisted receipts and original step bytes; it does not repeat
    nonlinear analysis or independently establish physical accuracy.
    """
    result = directory / "results"
    summary = _receipt(result / "summary.json")
    expected = {
        "schema", "base_revision", "script_sha256", "model_sha256", "scope",
        "case", "arithmetic_selection", "implementation", "timing_scope",
        "default_solver_changed", "learned_policy",
        "independent_physical_validation", "concurrent_execution_supported",
        "rows", "supplied_request_sha256", "supplied_target_count",
        "supplied_constant_load_count",
    }
    if record_assembly_timing:
        expected.add("assembly_timing_recording")
    _require(set(summary) == expected, "experiment summary fields mismatch")
    request = decode_bounded_rc_fiber_direct_control_request(values["request"])
    compiler_profile = None
    compiled_problem_contract_hashes = {}
    if request.experimental_two_fixed_endpoints or request.experimental_pin_roller_beam:
        profile_flag = (
            "experimental_two_fixed_endpoints"
            if request.experimental_two_fixed_endpoints
            else "experimental_pin_roller_beam"
        )
        compiler_profile = (
            public.EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE
            if request.experimental_two_fixed_endpoints
            else public.EXPERIMENTAL_RC_FIBER_FRAME_PIN_ROLLER_BEAM_CONTROL_PROFILE
        )
        model = load_neutral_json_bytes(values["model"])
        compiled, blockers, _ = public._compile(model, **{profile_flag: True})
        _require(compiled is not None and not blockers, "experiment model compiler mismatch")
        compiled = experiment.runtime.api._with_constant_loading(
            compiled, request.constant_nodal_loads
        )
        for retained in (False, True):
            profile = (
                experiment.learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
                if retained else "binary64"
            )
            compiled_problem_contract_hashes[retained] = (
                experiment.learning._learning_compiled_arithmetic(
                    compiled, profile
                ).problem.contract_hash
            )
    _require(
        summary["schema"] == "rc-immediate-line-search-reuse-experiment.v1"
        and summary["base_revision"] == source
        and summary["script_sha256"]
        == hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest()
        and summary["model_sha256"] == hashlib.sha256(values["model"]).hexdigest()
        and summary["supplied_request_sha256"]
        == hashlib.sha256(values["request"]).hexdigest()
        and type(summary["supplied_target_count"]) is int
        and summary["supplied_target_count"] == len(request.targets_m)
        and type(summary["supplied_constant_load_count"]) is int
        and summary["supplied_constant_load_count"] == len(request.constant_nodal_loads)
        and summary["scope"] == "one supplied model and unmodified supplied request"
        and summary["case"] == "supplied"
        and summary["arithmetic_selection"] == arithmetic
        and summary["implementation"] == "native"
        and summary["timing_scope"]
        == "whole benchmark including serialization, verification, and recording"
        and summary["default_solver_changed"] is False
        and summary["learned_policy"] is False
        and summary["independent_physical_validation"] is False
        and summary["concurrent_execution_supported"] is False
        and (
            not record_assembly_timing
            or summary["assembly_timing_recording"] is True
        ),
        "experiment summary source or scope mismatch",
    )
    profiles = (False, True) if arithmetic == "both" else (arithmetic == "retained",)
    expected_pairs = [(retained, repetition)
                      for retained in profiles for repetition in range(repetitions)]
    rows = summary["rows"]
    _require(
        type(rows) is list and len(rows) == len(expected_pairs),
        "experiment summary repetition count mismatch",
    )
    constant = bool(request.constant_nodal_loads)
    used_directories = set()
    for row, (retained, repetition) in zip(rows, expected_pairs):
        _require(
            type(row) is dict
            and set(row) == {
                "retained", "constant", "repetition", "order", "baseline",
                "reuse", "native_step_bytes_exact", "whole_benchmark_wall_ratio",
            }
            and row["retained"] is retained
            and row["constant"] is constant
            and type(row["repetition"]) is int
            and row["repetition"] == repetition
            and type(row["order"]) is list
            and all(type(enabled) is bool for enabled in row["order"])
            and row["order"]
            == ([False, True] if repetition % 2 == 0 else [True, False])
            and row["native_step_bytes_exact"] is True,
            "experiment summary pair order or scope mismatch",
        )
        pair = {}
        for strategy, enabled in (("baseline", False), ("reuse", True)):
            item = row[strategy]
            # The supplied-case experiment has one configuration-loop slot
            # (constant=False); the row's constant flag instead describes
            # the request itself, which may contain a preload.
            name = f"retained-{retained}-constant-False-rep-{repetition}-{enabled}"
            _require(
                type(item) is dict
                and set(item) == {
                    "directory", "wall_ns", "step_count",
                    "actual_newton_dispatches", "reused_dispatches",
                }
                and item["directory"] == name
                and name not in used_directories
                and type(item["wall_ns"]) is int and item["wall_ns"] > 0
                and type(item["step_count"]) is int and item["step_count"] > 0
                and type(item["actual_newton_dispatches"]) is int
                and item["actual_newton_dispatches"] >= 0
                and type(item["reused_dispatches"]) is int
                and item["reused_dispatches"] >= 0,
                "experiment summary benchmark identity or work mismatch",
            )
            used_directories.add(name)
            benchmark = result / name
            _require(
                benchmark.is_dir() and benchmark.resolve().is_relative_to(result.resolve()),
                "experiment benchmark directory escapes its result",
            )
            steps = _step_hashes(benchmark)
            _require(len(steps) == item["step_count"], "experiment step count mismatch")
            dispatches, reuse_hits = _assembly_counts(benchmark, steps)
            _require(
                item["actual_newton_dispatches"] == dispatches
                and item["reused_dispatches"] == reuse_hits,
                "experiment summary dispatches differ from saved outcomes",
            )
            pair[strategy] = (item, steps, _comparison(
                benchmark, source=source, request=request, constant=constant,
                compiler_profile=compiler_profile,
                compiled_problem_contract_hash=compiled_problem_contract_hashes.get(retained),
            ))
        baseline, reuse = pair["baseline"], pair["reuse"]
        _require(
            baseline[0]["reused_dispatches"] == 0
            and baseline[0]["actual_newton_dispatches"]
            == reuse[0]["actual_newton_dispatches"] + reuse[0]["reused_dispatches"]
            and baseline[1] == reuse[1]
            and baseline[2] == reuse[2],
            "experiment baseline/reuse work or physical comparison differs",
        )
        ratio = row["whole_benchmark_wall_ratio"]
        _require(
            type(ratio) in (int, float)
            and math.isfinite(ratio)
            and ratio > 0
            and math.isclose(
                ratio, reuse[0]["wall_ns"] / baseline[0]["wall_ns"],
                rel_tol=1e-12, abs_tol=0.0,
            ),
            "experiment benchmark wall ratio mismatch",
        )


def run(manifest: Path, output: Path):
    started = perf_counter_ns()
    plan = load_json_object_strict(manifest)
    if set(plan) != {"schema", "repetitions", "arithmetic", "record_assembly_timing", "cases"}:
        raise ValueError("unexpected or missing campaign fields")
    if plan["schema"] != "rc-reuse-campaign-plan.v1":
        raise ValueError("unsupported campaign schema")
    repetitions = plan["repetitions"]
    if type(repetitions) is not int or repetitions < 2 or repetitions % 2:
        raise ValueError("positive even repetitions required")
    if plan["arithmetic"] not in ("binary64", "retained", "both"):
        raise ValueError("unknown arithmetic")
    if type(plan["record_assembly_timing"]) is not bool:
        raise ValueError("explicit boolean timing required")
    if not isinstance(plan["cases"], list) or not plan["cases"]:
        raise ValueError("nonempty case list required")
    frozen, names = [], set()
    for case in plan["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "model", "request"}:
            raise ValueError("case requires id, model and request")
        name = case["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
            raise ValueError("invalid case id")
        if name in names:
            raise ValueError("duplicate case id")
        names.add(name)
        values = {}
        for role in ("model", "request"):
            if not isinstance(case[role], str) or not case[role]:
                raise ValueError("input path must be a nonempty string")
            source = (manifest.parent / case[role]).resolve()
            # Read every input before executing any case, so later external edits
            # cannot silently change a case after the campaign has started.
            values[role] = source.read_bytes()
        frozen.append((name, values))
    output.mkdir(parents=True, exist_ok=False)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    bindings = []
    for name, values in frozen:
        directory = output / name
        directory.mkdir()
        binding = {"id": name, "inputs": {}}
        for role, raw in values.items():
            (directory / f"{role}.json").write_bytes(raw)
            binding["inputs"][role] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        bindings.append(binding)
    _write(output / "plan.json", {
        "source_revision": source, "plan": plan, "bindings": bindings,
        "campaign_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "experiment_script_sha256": hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest(),
    })
    rows = []
    for name, values in frozen:
        directory = output / name
        case_started = perf_counter_ns()
        error = None
        try:
            experiment.run(
                directory / "results", repetitions, case="supplied",
                arithmetic=plan["arithmetic"], implementation="native",
                model_path=directory / "model.json", request_path=directory / "request.json",
                record_assembly_timing=plan["record_assembly_timing"],
            )
            _validate_case_receipt(
                directory, values, source=source, repetitions=repetitions,
                arithmetic=plan["arithmetic"],
                record_assembly_timing=plan["record_assembly_timing"],
            )
        except Exception as exc:
            # Continue independent declared cases, but retain failure and return
            # nonzero from the CLI. Interrupts and process termination propagate.
            error = {"type": type(exc).__name__, "message": str(exc)}
        row = {"id": name, "status": "failed" if error else "completed",
               "error": error, "case_wall_ns": perf_counter_ns() - case_started,
               "receipts": {}}
        for filename in ("summary.json", "failure.json"):
            path = directory / "results" / filename
            if path.is_file():
                raw = path.read_bytes()
                row["receipts"][filename] = {
                    "path": str(path.relative_to(output)), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
        rows.append(row)
        # Persist after every case; a partial campaign is explicitly incomplete.
        _write(output / "campaign.json", {
            "schema": "rc-reuse-campaign.v1", "source_revision": source,
            "planned_case_count": len(frozen), "recorded_case_count": len(rows),
            "campaign_complete": len(rows) == len(frozen),
            "all_cases_completed": len(rows) == len(frozen) and all(r["status"] == "completed" for r in rows),
            "cases": rows, "campaign_wall_ns_through_receipt": perf_counter_ns() - started,
            "timing_scope": "manifest/input reads, setup, all attempted cases, post-run saved receipt verification, and preceding receipt writes; excludes this final receipt write",
            "aggregate_speed_ratio": None, "independent_physical_validation": False,
        })
    return all(row["status"] == "completed" for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.manifest, args.output) else 1)
