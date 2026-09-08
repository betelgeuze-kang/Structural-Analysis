"""Fresh processes for ordered candidate-search arms and their later oracle.

Training artifacts are read, never regenerated. Each online worker prepares and
ranks its own immutable pool before fresh public reanalysis. Parent preflight
freezes both plans before any worker starts. Resource sidecars do not confer
numerical, provenance, design, or release authority.
"""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
import math
import os
from pathlib import Path
import re
from statistics import median, pstdev
from time import perf_counter_ns, process_time_ns
from typing import Any, Callable

from structural_analysis.benchmark import fiber_frame_runtime_process as process


REQUEST_SCHEMA = "rc-fiber-candidate-process-suite-request.v1"
WORKER_SCHEMA = "rc-fiber-candidate-process-worker-request.v1"
SCHEMA_VERSION = "rc-fiber-candidate-process-suite.v1"
STRATEGIES = ("deterministic", "learned")
CASE_FIELDS = {
    "case_id",
    "model_file",
    "training_file",
    "candidates",
    "configuration",
    "prices",
    "terminal_limits",
    "history_limits",
    "full_analysis_budget",
    "exploration_slots",
}


def _read_bounded(path: Path, limit: int = 16 * 1024 * 1024) -> bytes:
    if ".env" in path.name or path.is_symlink() or not path.is_file():
        raise ValueError("regular JSON input file required")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit exceeded")
    return data


def _identity(path: Path) -> dict[str, Any]:
    data = _read_bounded(path, 128 * 1024 * 1024)
    return {
        "path": str(path),
        "sha256": process._digest(data),
        "byte_length": len(data),
    }


def _unchanged(identities: list[dict[str, Any]]) -> bool:
    try:
        return all(_identity(Path(row["path"])) == row for row in identities)
    except (OSError, ValueError):
        return False


def _case_arguments(
    row: dict[str, Any],
    base_dir: Path,
    read: Callable[[Path, int], bytes] = _read_bounded,
) -> dict[str, Any]:
    """Decode one frozen case without fitting a policy or entering the solver."""
    from structural_analysis.ai.fiber_frame_candidate_learning import (
        FiberFrameCandidatePolicy,
        FiberFrameCandidateTrainingResult,
        _validated_training_report,
    )
    from structural_analysis.api import PublicRCFiberFrameConfig
    from structural_analysis.benchmark.fiber_frame_candidate_search_suite import (
        FiberFrameCandidateSearchCase,
    )
    from structural_analysis.benchmark.fiber_frame_design import (
        FiberFrameDesignCandidate,
        FiberFrameHistoryLimits,
        FiberFrameMaterialPrices,
        FiberFrameSectionChange,
        FiberFrameTerminalLimits,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes

    process._fields(row, CASE_FIELDS)
    for key in ("model_file", "training_file"):
        if type(row[key]) is not str or not row[key]:
            raise ValueError("model and training paths required")
    model_path = base_dir / row["model_file"]
    baseline = load_neutral_json_bytes(read(model_path, 16 * 1024 * 1024))
    training_report = process._json(
        read(base_dir / row["training_file"], 16 * 1024 * 1024)
    )
    policy_json = training_report["policy"]
    policy = FiberFrameCandidatePolicy(
        **{
            field.name: policy_json[field.name]
            for field in fields(FiberFrameCandidatePolicy)
            if field.init
        }
    )
    if process._bytes(policy.to_dict()) != process._bytes(policy_json):
        raise ValueError("candidate policy artifact mismatch")
    training = FiberFrameCandidateTrainingResult(
        training_report["status"],
        policy,
        json.dumps(training_report, sort_keys=True, allow_nan=False),
    )
    _validated_training_report(training)
    candidates = []
    if type(row["candidates"]) is not list or not 1 <= len(row["candidates"]) <= 64:
        raise ValueError("one to 64 candidate declarations required")
    for candidate in row["candidates"]:
        process._fields(candidate, {"candidate_id", "changes"})
        if type(candidate["changes"]) is not list:
            raise ValueError("candidate changes must be an array")
        changes = []
        for change in candidate["changes"]:
            process._fields(change, {f.name for f in fields(FiberFrameSectionChange)})
            changes.append(FiberFrameSectionChange(**change))
        candidates.append(
            FiberFrameDesignCandidate(candidate["candidate_id"], tuple(changes))
        )
    for key, cls in (
        ("configuration", PublicRCFiberFrameConfig),
        ("prices", FiberFrameMaterialPrices),
        ("terminal_limits", FiberFrameTerminalLimits),
    ):
        process._fields(row[key], {f.name for f in fields(cls)})
    history = row["history_limits"]
    if history is not None:
        process._fields(history, {f.name for f in fields(FiberFrameHistoryLimits)})
        history = FiberFrameHistoryLimits(**history)
    case = FiberFrameCandidateSearchCase(
        row["case_id"],
        baseline,
        tuple(candidates),
        training,
        FiberFrameMaterialPrices(**row["prices"]),
        FiberFrameTerminalLimits(**row["terminal_limits"]),
        PublicRCFiberFrameConfig(**row["configuration"]),
        row["full_analysis_budget"],
        row["exploration_slots"],
        history,
    )
    return {
        "baseline": case.baseline,
        "candidates": case.candidates,
        "training": case.training,
        "prices": case.prices,
        "terminal_limits": case.terminal_limits,
        "config": case.config,
        "full_analysis_budget": case.full_analysis_budget,
        "exploration_slots": case.exploration_slots,
        "history_limits": case.history_limits,
    }


def _freeze_inputs(
    request_path: Path, output: Path, *, source_revision: str
) -> dict[str, Any]:
    from structural_analysis.ai.fiber_frame_candidate_learning import _source_revision
    from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
        prepare_fiber_frame_candidate_search_expectations,
    )

    source_revision = _source_revision(source_revision)
    raw_request = _read_bounded(request_path, 4 * 1024 * 1024)
    request = process._json(raw_request)
    process._fields(
        request, {"schema_version", "cases", "repetitions", "warmups", "oracle_audit"}
    )
    if request["schema_version"] != REQUEST_SCHEMA:
        raise ValueError("unsupported candidate process suite request")
    if type(request["cases"]) is not list or not 1 <= len(request["cases"]) <= 64:
        raise ValueError("one to 64 cases required")
    repetitions, warmups = request["repetitions"], request["warmups"]
    if type(repetitions) is not int or not 2 <= repetitions <= 32 or repetitions % 2:
        raise ValueError("repetitions must be even and in [2,32]")
    if type(warmups) is not int or not 0 <= warmups <= 5:
        raise ValueError("warmups must be in [0,5]")
    if type(request["oracle_audit"]) is not bool:
        raise ValueError("oracle_audit must be boolean")
    frozen = output / "inputs"
    frozen.mkdir(mode=0o700)
    process._write(frozen / "original-request.json", raw_request)
    identities = [_identity(frozen / "original-request.json")]
    cases, case_ids, artifacts = [], set(), {}
    for index, declared in enumerate(request["cases"]):
        process._fields(declared, CASE_FIELDS)
        row = dict(declared)
        for key, stem in (("model_file", "model"), ("training_file", "training")):
            if type(row[key]) is not str or not row[key]:
                raise ValueError("model and training paths required")
            original = request_path.parent / row[key]
            target = frozen / f"{stem}-{index:03d}.json"
            process._write(target, _read_bounded(original))
            identities.append(_identity(target))
            row[key] = str(target)
        arguments = _case_arguments(row, frozen)
        if row["case_id"] in case_ids:
            raise ValueError("case IDs must be unique")
        case_ids.add(row["case_id"])
        expectations = prepare_fiber_frame_candidate_search_expectations(
            **arguments,
            source_revision=source_revision,
        )
        training_report = arguments["training"].to_dict()
        costs = {
            key: training_report["cost_accounting"][key]
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        }
        previous = artifacts.setdefault(training_report["report_hash"], costs)
        if previous != costs:
            raise ValueError("one training artifact cannot have multiple costs")
        cases.append(
            {"case_id": row["case_id"], "request": row, "expectations": expectations}
        )
    result = {
        "source_revision": source_revision,
        "configuration": {
            key: request[key] for key in ("repetitions", "warmups", "oracle_audit")
        },
        "cases": cases,
        "identities": identities,
        "training_artifacts": artifacts,
    }
    process._write(frozen / "declaration.json", process._bytes(result))
    result["identities"].append(_identity(frozen / "declaration.json"))
    return result


def _worker(request_path: Path, source_revision: str, output: Path) -> int:
    """Record complete process scopes even when a workload raises an exception."""
    started = perf_counter_ns()
    reads: list[dict[str, Any]] = []
    workload_wall = workload_cpu = 0
    strategy, stage = None, "input_contract"

    def read(path: Path, limit: int) -> bytes:
        tick = perf_counter_ns()
        data = _read_bounded(path, limit)
        elapsed = perf_counter_ns() - tick
        reads.append(
            {
                "path": str(path),
                "byte_length": len(data),
                "sha256": process._digest(data),
                "read_wall_ns": elapsed,
            }
        )
        return data

    try:
        from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
            run_fiber_frame_candidate_search_arm,
            run_fiber_frame_candidate_search_oracle,
        )

        request = process._json(read(request_path, 4 * 1024 * 1024))
        process._fields(
            request,
            {
                "schema_version",
                "case",
                "strategy",
                "expected_plan_hash",
                "expected_inputs",
                "online_completion_hashes",
            },
        )
        strategy = request["strategy"]
        if request["schema_version"] != WORKER_SCHEMA or strategy not in (
            *STRATEGIES,
            "oracle",
        ):
            raise ValueError("invalid worker profile")
        completions = request["online_completion_hashes"]
        if strategy == "oracle":
            process._fields(completions, set(STRATEGIES))
            if any(
                type(value) is not str
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
                for value in completions.values()
            ):
                raise ValueError("oracle requires both online completion identities")
        elif completions != {}:
            raise ValueError(
                "online worker cannot receive oracle or other result labels"
            )
        arguments = _case_arguments(request["case"], request_path.parent, read)
        actual_inputs = [
            {key: row[key] for key in ("path", "sha256", "byte_length")}
            for row in reads[1:]
        ]
        if process._bytes(actual_inputs) != process._bytes(request["expected_inputs"]):
            raise ValueError("worker input bytes differ from frozen inputs")
        stage = "candidate_search"
        begin_wall, begin_cpu = perf_counter_ns(), process_time_ns()
        try:
            execute = (
                run_fiber_frame_candidate_search_oracle
                if strategy == "oracle"
                else run_fiber_frame_candidate_search_arm
            )
            report = execute(
                **arguments,
                source_revision=source_revision,
                expected_plan_hash=request["expected_plan_hash"],
                **({} if strategy == "oracle" else {"strategy": strategy}),
            )
        finally:
            workload_wall, workload_cpu = (
                perf_counter_ns() - begin_wall,
                process_time_ns() - begin_cpu,
            )
    except Exception as error:
        report = {
            "schema_version": "rc-fiber-candidate-process-failure.v1",
            "status": "error",
            "report_contract_pass": False,
            "strategy": strategy,
            "source_revision": source_revision,
            "failure": {"stage": stage, "exception_type": type(error).__name__},
            "analysis_request_count": None if stage == "candidate_search" else 0,
        }
        process._write(output / "failure.json", process._bytes(report))
    encode_start = perf_counter_ns()
    encoded = process._bytes(report)
    encode_wall = perf_counter_ns() - encode_start
    write_start = perf_counter_ns()
    process._write(output / "search.json", encoded)
    write_wall = perf_counter_ns() - write_start
    peak, peak_scope = process._peak_rss()
    measurement_pass = report.get("report_contract_pass") is True
    resources = {
        "schema_version": "rc-fiber-candidate-search-process-resources.v1",
        "worker_pid": os.getpid(),
        "source_revision": source_revision,
        "status": "ready" if measurement_pass else "blocked",
        "measurement_contract_pass": measurement_pass,
        "search_sha256": process._digest(encoded),
        "search_byte_length": len(encoded),
        "inputs": reads,
        "input_read_wall_ns": sum(row["read_wall_ns"] for row in reads),
        "input_bytes_read": sum(row["byte_length"] for row in reads),
        "input_io_scope": "bounded_file_reads_only_excluding_decode_parse_and_hashing",
        "workload_wall_ns": workload_wall,
        "workload_cpu_process_time_ns": workload_cpu,
        "workload_scope": process._CANDIDATE.workload_scope,
        "report_encode_wall_ns": encode_wall,
        "report_write_flush_fsync_wall_ns": write_wall,
        "report_bytes_written": len(encoded),
        "worker_observed_wall_ns": perf_counter_ns() - started,
        "cpu_process_time_ns": process_time_ns(),
        "process_cpu_scope": "worker_process_lifetime_through_search_persistence_excluding_resource_sidecar_emission",
        "peak_memory_bytes": peak,
        "peak_memory_scope_or_reason": peak_scope,
        "per_strategy_peak_memory_bytes": peak,
        "per_strategy_peak_memory_reason": process.CANDIDATE_PEAK_SCOPE,
        "strategy": strategy,
        "gpu_time_ns": None,
        "gpu_time_reason": "cpu_only_solver_path",
        "resource_sidecar_io_included": False,
        "source_revision_is_attestation": False,
        "independent_hardware_validation": False,
        "generalized_speedup_claimed": False,
    }
    process._write(output / "resources.json", process._bytes(resources))
    return 0 if measurement_pass else 3


def _launch_worker(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    return process._run_fiber_frame_process(
        request_path,
        source_revision=source_revision,
        output_directory=output_directory,
        timeout_seconds=timeout_seconds,
        profile=process._CANDIDATE,
    )


def _natural(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer measurement required")
    return value


def _distribution(values: list[int]) -> dict[str, Any]:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "median": median(values) if values else None,
        "maximum": max(values) if values else None,
        "population_standard_deviation": pstdev(values) if values else None,
    }


def _validate_worker(
    output: Path,
    request_path: Path,
    expectations: dict[str, Any],
    *,
    source_revision: str,
) -> dict[str, Any]:
    """Recheck stored bytes and independent report/resource contracts, no solve."""
    from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
        validate_fiber_frame_candidate_search_arm_report,
        validate_fiber_frame_candidate_search_oracle_report,
    )

    result = {
        "report_contract_pass": False,
        "resource_contract_pass": False,
        "report": None,
        "resources": None,
        "manifest": None,
        "failure": {"report": None, "resources": None},
    }
    try:
        request = process._json(_read_bounded(request_path, 4 * 1024 * 1024))
        strategy = request["strategy"]
        if strategy not in (*STRATEGIES, "oracle"):
            raise ValueError("unexpected worker strategy")
        manifest = process._json(_read_bounded(output / "manifest.json"))
        process._fields(
            manifest,
            {
                "schema_version",
                "source_revision",
                "status",
                "worker_pid",
                "parent_pid",
                "worker_exit_code",
                "fresh_python_process",
                "launch_to_exit_wall_ns",
                "parent_orchestration_cpu_time_ns",
                "parent_cpu_scope",
                "launch_scope",
                "artifacts",
                "worker_measurements_available",
                "worker_resource_validation_failure",
                "source_revision_is_attestation",
                "independent_validation",
            },
        )
        if type(manifest["artifacts"]) is not dict or not set(
            manifest["artifacts"]
        ) <= {
            "search.json",
            "resources.json",
            "failure.json",
        }:
            raise ValueError("worker artifact inventory invalid")
        for artifact in manifest["artifacts"].values():
            process._fields(artifact, {"sha256", "byte_length"})
            _natural(artifact["byte_length"])
            if type(artifact["sha256"]) is not str or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", artifact["sha256"]
            ):
                raise ValueError("worker artifact digest invalid")
        if (
            manifest["schema_version"]
            != "rc-fiber-candidate-search-process-manifest.v1"
            or manifest["source_revision"] != source_revision
            or manifest["source_revision_is_attestation"] is not False
            or manifest["independent_validation"] is not False
            or manifest["fresh_python_process"] is not True
            or type(manifest["worker_pid"]) is not int
            or manifest["worker_pid"] <= 0
            or type(manifest["parent_pid"]) is not int
            or manifest["parent_pid"] <= 0
            or manifest["worker_pid"] == manifest["parent_pid"]
            or type(manifest["worker_exit_code"]) is not int
            or manifest["status"] not in ("ready", "blocked", "timeout")
            or type(manifest["worker_measurements_available"]) is not bool
            or manifest["parent_cpu_scope"]
            != "launch_wait_and_artifact_validation_before_manifest_emission"
            or manifest["launch_scope"]
            != "spawn_imports_inputs_search_and_worker_persistence_excluding_manifest_emission"
            or (manifest["worker_resource_validation_failure"] is None)
            is not manifest["worker_measurements_available"]
        ):
            raise ValueError("worker manifest identity invalid")
        for key in ("launch_to_exit_wall_ns", "parent_orchestration_cpu_time_ns"):
            _natural(manifest[key])
        result["manifest"] = manifest
        if manifest["status"] == "timeout":
            raise ValueError("timed-out worker cannot publish final observations")
        raw = _read_bounded(output / "search.json", 128 * 1024 * 1024)
        identity = {"sha256": process._digest(raw), "byte_length": len(raw)}
        if manifest["artifacts"].get("search.json") != identity:
            raise ValueError("search artifact bytes mismatch")
        report = process._json(raw)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        UnicodeError,
        RecursionError,
    ) as error:
        result["failure"] = {key: str(error) for key in ("report", "resources")}
        return result
    try:
        if request["expected_plan_hash"] != expectations[strategy]["frozen_plan_hash"]:
            raise ValueError("worker plan declaration mismatch")
        validate = (
            validate_fiber_frame_candidate_search_oracle_report
            if strategy == "oracle"
            else validate_fiber_frame_candidate_search_arm_report
        )
        validate(
            report,
            expectations,
            **({} if strategy == "oracle" else {"strategy": strategy}),
        )
        result.update(report_contract_pass=True, report=report)
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError) as error:
        result["failure"]["report"] = str(error)
    try:
        raw_resources = _read_bounded(output / "resources.json")
        if manifest["artifacts"].get("resources.json") != {
            "sha256": process._digest(raw_resources),
            "byte_length": len(raw_resources),
        }:
            raise ValueError("resource artifact bytes mismatch")
        resources = process._json(raw_resources)
        reason = process._resource_validation_failure(
            resources,
            manifest["worker_pid"],
            source_revision,
            identity,
            process._CANDIDATE,
        )
        if reason:
            raise ValueError(reason)
        if manifest["worker_measurements_available"] is not True or manifest[
            "status"
        ] != (
            "ready"
            if manifest["worker_exit_code"] == 0
            and resources["measurement_contract_pass"] is True
            else "blocked"
        ):
            raise ValueError("manifest/resource status mismatch")
        if resources["strategy"] != strategy:
            raise ValueError("resource strategy mismatch")
        expected_inputs = [_identity(request_path), *request["expected_inputs"]]
        inputs = resources["inputs"]
        if type(inputs) is not list or len(inputs) != len(expected_inputs):
            raise ValueError("input coverage mismatch")
        for actual, expected in zip(inputs, expected_inputs, strict=True):
            process._fields(actual, {"path", "sha256", "byte_length", "read_wall_ns"})
            _natural(actual["read_wall_ns"])
            _natural(actual["byte_length"])
            if {key: actual[key] for key in expected} != expected:
                raise ValueError("input byte identity/order mismatch")
            if _identity(Path(actual["path"])) != expected:
                raise ValueError("frozen input changed")
        if (
            resources["input_read_wall_ns"]
            != sum(row["read_wall_ns"] for row in inputs)
            or resources["input_bytes_read"]
            != sum(row["byte_length"] for row in inputs)
            or resources["workload_cpu_process_time_ns"]
            > resources["cpu_process_time_ns"]
            or sum(
                resources[key]
                for key in (
                    "input_read_wall_ns",
                    "workload_wall_ns",
                    "report_encode_wall_ns",
                    "report_write_flush_fsync_wall_ns",
                )
            )
            > resources["worker_observed_wall_ns"]
            or resources["worker_observed_wall_ns"] > manifest["launch_to_exit_wall_ns"]
        ):
            raise ValueError("resource subtotal or scope mismatch")
        peak_scope = resources["peak_memory_scope_or_reason"]
        if (
            resources["peak_memory_bytes"] is None
            and peak_scope
            not in (
                "post_exec_process_peak_rss_not_supported_on_this_platform",
                "post_exec_process_peak_rss_unavailable",
            )
        ) or (
            resources["peak_memory_bytes"] is not None
            and peak_scope
            != "linux_proc_vmhwm_post_exec_address_space_including_interpreter_imports_and_report_encoding"
        ):
            raise ValueError("peak memory scope mismatch")
        if result["report_contract_pass"] and (
            resources["measurement_contract_pass"] is not True
            or report["cost_accounting"]["actual_workload_wall_ns"]
            > resources["workload_wall_ns"]
        ):
            raise ValueError("workload/report timing mismatch")
        result.update(resource_contract_pass=True, resources=resources)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        UnicodeError,
        RecursionError,
    ) as error:
        result["failure"]["resources"] = str(error)
    return result


def _counts(report: dict[str, Any]) -> dict[str, int]:
    if report["strategy"] == "oracle":
        rows = report["rows"]
    else:
        arm = report["arm"]
        rows = [arm["baseline"], *arm["candidate_outcomes"]]
    requested = [row for row in rows if row["analysis_requested"] is True]
    return {
        "full_analysis_request_count": len(requested),
        "known_solver_execution_count": sum(
            row["solver_executed"] is True for row in requested
        ),
        "unknown_solver_execution_count": sum(
            row["solver_executed"] is None for row in requested
        ),
    }


def _summarize_cases(
    frozen: dict[str, Any], runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from structural_analysis.benchmark.fiber_frame_candidate_search import (
        _audit_outcomes,
    )

    summaries = []
    for case in frozen["cases"]:
        rows = [row for row in runs if row["case_id"] == case["case_id"]]
        measured = [row for row in rows if row["phase"] == "measured"]
        pairs, wall_differences, cpu_differences = [], [], []
        for repetition in range(frozen["configuration"]["repetitions"]):
            group = {
                row["strategy"]: row
                for row in measured
                if row["repetition"] == repetition
            }
            arms = {
                name: group[name]["report"]["arm"]
                for name in STRATEGIES
                if group[name]["report_contract_pass"]
            }
            valid = len(arms) == 2
            quality = valid and all(
                arms[name]["final_selection"] is not None for name in STRATEGIES
            )
            if quality:
                quality = (
                    arms["learned"]["final_selection"]["material_estimate"]["total"]
                    <= arms["deterministic"]["final_selection"]["material_estimate"][
                        "total"
                    ]
                )
            resources_valid = all(
                group[name]["resource_contract_pass"] for name in STRATEGIES
            )
            difference = None
            if valid and resources_valid:
                # Each sequential parent slot includes request persistence,
                # spawn/import/input/report costs, and parent validation.
                difference = (
                    group["deterministic"]["parent_slot_observed_wall_ns"]
                    - group["learned"]["parent_slot_observed_wall_ns"]
                )
                wall_differences.append(difference)
                cpu_differences.append(
                    group["deterministic"]["resources"]["cpu_process_time_ns"]
                    - group["learned"]["resources"]["cpu_process_time_ns"]
                )
            oracle = group.get("oracle")
            oracle_rows = (
                oracle["report"]["rows"]
                if oracle and oracle["report_contract_pass"]
                else None
            )
            audits = {}
            if valid:
                for name in STRATEGIES:
                    audit = _audit_outcomes(
                        case["expectations"]["learned"]["candidate_pool"],
                        arms[name]["shortlist"],
                        oracle_rows,
                        case["request"]["history_limits"] is not None,
                    )
                    if name == "deterministic":
                        audit.update(
                            false_safe_count=None,
                            false_safe_candidate_ids=None,
                            predicted_safe_unverifiable_count=None,
                            predicted_safe_unverifiable_candidate_ids=None,
                            false_safe_applicability="strategy_makes_no_predicted_safety_claim",
                        )
                    audits[name] = audit
            pairs.append(
                {
                    "repetition": repetition,
                    "online_reports_valid": valid,
                    "online_resources_valid": resources_valid,
                    "learned_verified_scoped_material_cost_not_worse": bool(quality),
                    "selected_candidate_ids": {
                        name: arms[name]["final_selection"]["candidate_id"]
                        if name in arms and arms[name]["final_selection"]
                        else None
                        for name in STRATEGIES
                    },
                    "deterministic_minus_learned_slot_wall_ns": difference,
                    "oracle_audit": audits,
                }
            )
        all_ready = all(
            row["report_contract_pass"]
            and row["resource_contract_pass"]
            and row["report"]["status"] == "ready"
            for row in rows
            if row["strategy"] in STRATEGIES
        )
        quality = all(
            pair["learned_verified_scoped_material_cost_not_worse"] for pair in pairs
        )
        saving = (
            median(wall_differences) if len(wall_differences) == len(pairs) else None
        )
        training = case["expectations"]["input_binding"]["training_cost_accounting"]
        summaries.append(
            {
                "case_id": case["case_id"],
                "measured_pairs": pairs,
                "all_online_attempts_ready": all_ready,
                "paired_deterministic_minus_learned_slot_wall_ns": _distribution(
                    wall_differences
                ),
                "paired_deterministic_minus_learned_worker_cpu_ns": _distribution(
                    cpu_differences
                ),
                "comparison_scope": "sequential_parent_slot_including_request_persistence_worker_spawn_import_input_preparation_ranking_reanalysis_selection_report_persistence_and_parent_validation_excludes_shared_preflight_final_aggregation_and_historical_training",
                "projected_reuses_to_amortize_this_training_artifact": max(
                    1,
                    math.ceil(
                        (
                            training["data_generation_wall_ns"]
                            + training["training_wall_ns"]
                        )
                        / saving
                    ),
                )
                if all_ready and quality and saving is not None and saving > 0
                else None,
                "projection_scope": "conditional_positive_paired_median_for_this_case_including_slot_parent_validation_excludes_shared_preflight_and_final_aggregation",
                "break_even_is_observed_execution": False,
            }
        )
    return summaries


def run_fiber_frame_candidate_process_suite(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Execute the declared round/case schedule, retaining every failed slot."""
    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    from structural_analysis.ai.fiber_frame_candidate_learning import _source_revision
    from structural_analysis.engine_v2.contracts._canonical import canonical_hash

    source_revision = _source_revision(source_revision)
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be finite and positive")
    output = Path(output_directory)
    if output.is_symlink():
        raise ValueError("output directory must be new")
    output = output.resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    frozen = _freeze_inputs(
        Path(request_path).absolute(), output, source_revision=source_revision
    )
    preflight_wall, preflight_cpu = (
        perf_counter_ns() - started_wall,
        process_time_ns() - started_cpu,
    )
    (output / "workers").mkdir()
    (output / "requests").mkdir()
    input_lookup = {row["path"]: row for row in frozen["identities"]}
    runs = []
    seen_worker_pids: set[int] = set()
    index = 0
    for phase, count in (
        ("warmup", frozen["configuration"]["warmups"]),
        ("measured", frozen["configuration"]["repetitions"]),
    ):
        for repetition in range(count):
            for case_index, case in enumerate(frozen["cases"]):
                order = (
                    STRATEGIES
                    if (repetition + case_index) % 2 == 0
                    else STRATEGIES[::-1]
                )
                completed = {}
                for strategy in (
                    *order,
                    *(("oracle",) if frozen["configuration"]["oracle_audit"] else ()),
                ):
                    slot_wall, slot_cpu = perf_counter_ns(), process_time_ns()
                    index += 1
                    destination = output / "workers" / f"{index:05d}-{strategy}"
                    request_file = output / "requests" / f"{index:05d}-{strategy}.json"
                    row = {
                        "case_id": case["case_id"],
                        "phase": phase,
                        "repetition": repetition,
                        "strategy": strategy,
                        "execution_order": list(order),
                        "attempted": False,
                        "worker_directory": str(destination),
                        "request_file": str(request_file),
                        "report_contract_pass": False,
                        "resource_contract_pass": False,
                        "report": None,
                        "resources": None,
                        "manifest": None,
                        "failure": {"report": None, "resources": None},
                    }
                    if not _unchanged(frozen["identities"]):
                        row["failure"] = {
                            key: "frozen_input_changed"
                            for key in ("report", "resources")
                        }
                    elif strategy == "oracle" and set(completed) != set(STRATEGIES):
                        row["failure"] = {
                            key: "online_completion_unavailable"
                            for key in ("report", "resources")
                        }
                    else:
                        worker_request = {
                            "schema_version": WORKER_SCHEMA,
                            "case": case["request"],
                            "strategy": strategy,
                            "expected_plan_hash": case["expectations"][strategy][
                                "frozen_plan_hash"
                            ],
                            "expected_inputs": [
                                input_lookup[case["request"][key]]
                                for key in ("model_file", "training_file")
                            ],
                            "online_completion_hashes": dict(completed)
                            if strategy == "oracle"
                            else {},
                        }
                        process._write(request_file, process._bytes(worker_request))
                        row["request_identity"] = _identity(request_file)
                        row["attempted"] = True
                        try:
                            launched = _launch_worker(
                                request_file,
                                source_revision=source_revision,
                                output_directory=destination,
                                timeout_seconds=timeout_seconds,
                            )
                            checked = _validate_worker(
                                destination,
                                request_file,
                                case["expectations"],
                                source_revision=source_revision,
                            )
                            if checked["manifest"] is not None and process._bytes(
                                checked["manifest"]
                            ) != process._bytes(launched):
                                raise ValueError("launcher and saved manifest disagree")
                            row.update(checked)
                            if row["manifest"] is not None:
                                worker_pid = row["manifest"]["worker_pid"]
                                if worker_pid in seen_worker_pids:
                                    raise ValueError(
                                        "duplicate worker PID across suite slots"
                                    )
                                seen_worker_pids.add(worker_pid)
                            if (
                                not _unchanged(frozen["identities"])
                                or _identity(request_file) != row["request_identity"]
                            ):
                                raise ValueError(
                                    "frozen inputs changed during worker execution"
                                )
                        except (
                            ValueError,
                            OSError,
                            KeyError,
                            TypeError,
                            UnicodeError,
                        ) as error:
                            row.update(
                                report_contract_pass=False,
                                resource_contract_pass=False,
                                report=None,
                                resources=None,
                                failure={
                                    key: str(error) for key in ("report", "resources")
                                },
                            )
                        if strategy in STRATEGIES and row["report_contract_pass"]:
                            completed[strategy] = row["manifest"]["artifacts"][
                                "search.json"
                            ]["sha256"]
                    row.update(
                        parent_slot_observed_wall_ns=perf_counter_ns() - slot_wall,
                        parent_slot_cpu_time_ns=process_time_ns() - slot_cpu,
                        slot_wall_includes_worker_launch_and_parent_validation=True,
                    )
                    runs.append(row)
    case_summaries = _summarize_cases(frozen, runs)
    costs, resources = _aggregate(frozen, runs)
    parent_cpu = process_time_ns() - started_cpu
    parent_wall = perf_counter_ns() - started_wall
    resources.update(
        parent_cpu_time_ns=parent_cpu,
        parent_wall_ns=parent_wall,
        parent_preflight_cpu_ns=preflight_cpu,
        parent_preflight_wall_ns=preflight_wall,
        parent_preflight_is_subset=True,
        parent_scope="snapshot_preflight_extra_predictions_launch_wait_validation_aggregation_excludes_final_suite_encoding_and_persistence",
        parent_peak_memory_bytes=None,
        parent_peak_memory_reason="coordinator_not_a_fresh_measured_address_space",
    )
    if resources["worker_cpu_process_time_ns"] is not None:
        resources["current_parent_plus_workers_cpu_time_ns"] = (
            parent_cpu + resources["worker_cpu_process_time_ns"]
        )
    else:
        resources["current_parent_plus_workers_cpu_time_ns"] = None
    costs.update(
        current_parent_wall_ns_through_aggregation=parent_wall,
        accounted_wall_ns_including_historical_generation_and_fit=parent_wall
        + costs["historical_data_generation_wall_ns"]
        + costs["historical_training_wall_ns"],
        historical_cpu_time_ns=None,
        historical_cpu_reason="frozen_training_report_contains_wall_costs_only",
    )
    complete = all(
        row["report_contract_pass"] and row["resource_contract_pass"] for row in runs
    )
    physical_ready = all(
        row["report_contract_pass"] and row["report"]["status"] == "ready"
        for row in runs
        if row["strategy"] in STRATEGIES
    )
    declaration = {
        "source_revision": source_revision,
        "configuration": frozen["configuration"],
        "cases": [
            {
                "case_id": row["case_id"],
                "input_binding": row["expectations"]["input_binding"],
                "plans": {
                    key: row["expectations"][key] for key in (*STRATEGIES, "oracle")
                },
            }
            for row in frozen["cases"]
        ],
        "inputs": frozen["identities"],
        "execution_schedule": "round_major_case_order_alternating_online_arms_then_optional_oracle",
        "parent_plans_frozen_before_first_worker": True,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if complete and physical_ready else "incomplete",
        "declaration": declaration,
        "suite_identity_hash": canonical_hash(declaration),
        "runs": runs,
        "case_summaries": case_summaries,
        "cost_accounting": costs,
        "resource_accounting": resources,
        "claims": {
            "report_contract_pass": complete,
            "all_declared_slots_retained": True,
            "local_timing_evidence_eligible": complete and physical_ready,
            "historical_training_reexecuted": False,
            "oracle_labels_available_to_online_selection": False,
            "independent_case_families_verified": False,
            "hashes_attest_provenance": False,
            "generalized_speedup_claimed": False,
            "confirmed_construction_savings": False,
            "design_code_compliance": False,
            "production_promotion_eligible": False,
        },
    }
    report["report_hash"] = canonical_hash(report)
    process._write(output / "suite.json", process._bytes(report))
    return report


def _aggregate(
    frozen: dict[str, Any], runs: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = frozen["training_artifacts"]
    historical = {
        key: sum(_natural(row[key]) for row in artifacts.values())
        for key in (
            "data_generation_wall_ns",
            "training_wall_ns",
            "full_analysis_request_count",
        )
    }
    phases = {}
    for phase in ("warmup", "measured"):
        rows = [row for row in runs if row["phase"] == phase]
        valid = [row for row in rows if row["report_contract_pass"]]
        counts = [_counts(row["report"]) for row in valid]
        phases[phase] = {
            "declared_worker_slots": len(rows),
            "attempted_worker_slots": sum(row["attempted"] for row in rows),
            "validated_report_count": len(valid),
            "unknown_request_slots": sum(
                row["attempted"] and not row["report_contract_pass"] for row in rows
            ),
            "not_launched_slots": sum(not row["attempted"] for row in rows),
            "validated_online_request_subtotal": sum(
                _counts(row["report"])["full_analysis_request_count"]
                for row in valid
                if row["strategy"] in STRATEGIES
            ),
            "validated_oracle_request_subtotal": sum(
                _counts(row["report"])["full_analysis_request_count"]
                for row in valid
                if row["strategy"] == "oracle"
            ),
            "total_analysis_request_count": sum(
                row["full_analysis_request_count"] for row in counts
            )
            if all(not row["attempted"] or row["report_contract_pass"] for row in rows)
            else None,
            "known_solver_execution_subtotal": sum(
                row["known_solver_execution_count"] for row in counts
            ),
            "unknown_solver_execution_subtotal": sum(
                row["unknown_solver_execution_count"] for row in counts
            ),
        }
    observed = [row for row in runs if row["resource_contract_pass"]]
    all_observed = all(
        not row["attempted"] or row["resource_contract_pass"] for row in runs
    )
    cpu_subtotal = sum(row["resources"]["cpu_process_time_ns"] for row in observed)
    by_strategy = {}
    for name in (*STRATEGIES, "oracle"):
        matching = [row for row in observed if row["strategy"] == name]
        by_strategy[name] = {}
        for phase in ("warmup", "measured"):
            selected = [row for row in matching if row["phase"] == phase]
            by_strategy[name][phase] = {
                "observed_workers": len(selected),
                "declared_slots": sum(
                    row["strategy"] == name and row["phase"] == phase for row in runs
                ),
                "worker_cpu_process_time_ns": _distribution(
                    [row["resources"]["cpu_process_time_ns"] for row in selected]
                ),
                "launch_to_exit_wall_ns": _distribution(
                    [row["manifest"]["launch_to_exit_wall_ns"] for row in selected]
                ),
                "peak_memory_bytes": _distribution(
                    [
                        row["resources"]["peak_memory_bytes"]
                        for row in selected
                        if row["resources"]["peak_memory_bytes"] is not None
                    ]
                ),
                "peak_values_are_separate_process_high_water_marks": True,
                "input_bytes_read": sum(
                    row["resources"]["input_bytes_read"] for row in selected
                ),
                "input_read_wall_ns": sum(
                    row["resources"]["input_read_wall_ns"] for row in selected
                ),
                "report_bytes_written": sum(
                    row["resources"]["report_bytes_written"] for row in selected
                ),
                "report_write_flush_fsync_wall_ns": sum(
                    row["resources"]["report_write_flush_fsync_wall_ns"]
                    for row in selected
                ),
            }
    current_requests = (
        sum(row["total_analysis_request_count"] for row in phases.values())
        if all(
            row["total_analysis_request_count"] is not None for row in phases.values()
        )
        else None
    )
    return (
        {
            "training_artifacts_charged_once": artifacts,
            "historical_training_cost_scope": "one_generation_and_fit_per_distinct_training_report_hash",
            "historical_data_generation_wall_ns": historical["data_generation_wall_ns"],
            "historical_training_wall_ns": historical["training_wall_ns"],
            "historical_training_analysis_request_count": historical[
                "full_analysis_request_count"
            ],
            "phases": phases,
            "current_analysis_request_count": current_requests,
            "total_analysis_request_count_including_training_warmups_and_oracles": historical[
                "full_analysis_request_count"
            ]
            + current_requests
            if current_requests is not None
            else None,
        },
        {
            "workers_by_strategy": by_strategy,
            "validated_resource_worker_count": len(observed),
            "worker_cpu_process_time_ns_subtotal": cpu_subtotal,
            "worker_cpu_process_time_ns": cpu_subtotal if all_observed else None,
            "cpu_scopes_are_disjoint_parent_and_workers": True,
            "resource_io_scope": "worker_input_file_reads_and_search_report_encode_flush_fsync_only_sidecars_manifests_and_parent_suite_persistence_excluded",
            "peak_memory_aggregation": "distribution_of_separate_process_peaks_never_sum_or_subtract",
            "gpu_time_ns": None,
            "gpu_time_reason": "cpu_only_solver_path",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    args = parser.parse_args(argv)
    result = run_fiber_frame_candidate_process_suite(
        args.request,
        source_revision=args.source_revision,
        output_directory=args.output_directory,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps({"status": result["status"], "report_hash": result["report_hash"]})
    )
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
