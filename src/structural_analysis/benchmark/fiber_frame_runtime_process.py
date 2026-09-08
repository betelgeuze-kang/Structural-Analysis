"""Fresh-process RC runtime suites and learning studies with scoped resources.

Run as a module with --request, --source-revision and --output-directory. A
separate Python worker owns the suite so RSS is not inherited from earlier
benchmark runs in the caller. Resource observations are not solver authority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from typing import Any


@dataclass(frozen=True)
class _ProcessProfile:
    workload: str
    schema_prefix: str
    report_stem: str
    workload_scope: str

    @property
    def report_file(self) -> str:
        return self.report_stem + ".json"


_RUNTIME = _ProcessProfile(
    "runtime-suite",
    "rc-fiber-runtime-process",
    "suite",
    "whole_suite_including_warmups_full_verification_and_reference_episode_checks",
)
_LEARNING = _ProcessProfile(
    "learning-study",
    "rc-fiber-learning-process",
    "study",
    "whole_learning_study_including_data_generation_training_and_frozen_evaluation",
)
_STRATEGY = _ProcessProfile(
    "runtime-strategy",
    "rc-fiber-strategy-process",
    "strategy",
    "single_strategy_batch_including_warmups_full_selected_path_verification_and_reference_only_episode_checks",
)
_CANDIDATE = _ProcessProfile(
    "candidate-search-arm",
    "rc-fiber-candidate-search-process",
    "search",
    "one_candidate_search_arm_or_later_oracle_including_own_preparation_ranking_full_reanalysis_and_selection",
)
STRATEGY_PEAK_SCOPE = "one_declared_strategy_per_fresh_worker_including_reference_episode_checks_for_reference_only"
CANDIDATE_PEAK_SCOPE = "one_candidate_search_arm_or_oracle_per_fresh_worker_including_inputs_imports_ranking_verification_and_report_persistence"


def _bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _json(data: bytes) -> Any:
    return json.loads(data, object_pairs_hook=_unique, parse_constant=_reject_constant)


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON constant")


def _fields(value: Any, expected: set[str]) -> None:
    if type(value) is not dict or set(value) != expected:
        raise ValueError("request fields do not match the contract")


def _peak_rss() -> tuple[int | None, str]:
    if sys.platform != "linux":
        return None, "post_exec_process_peak_rss_not_supported_on_this_platform"
    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None, "post_exec_process_peak_rss_unavailable"
    # Linux ru_maxrss can retain the parent's high-water mark through exec.
    # VmHWM belongs to the worker's new address space and excludes that history.
    rows = [line.strip() for line in status.splitlines() if line.startswith("VmHWM:")]
    match = re.fullmatch(r"VmHWM:\s+([0-9]+)\s+kB", rows[0]) if len(rows) == 1 else None
    if match is None or int(match[1]) <= 0:
        return None, "post_exec_process_peak_rss_unavailable"
    return (
        int(match[1]) * 1024,
        "linux_proc_vmhwm_post_exec_address_space_including_interpreter_imports_and_report_encoding",
    )


def _decode_policy(data: bytes) -> Any:
    from structural_analysis.ai.fiber_frame_warm_start_learning import (
        FiberFrameLearnedWarmStartPolicy,
    )

    declared = _json(data)
    policy = FiberFrameLearnedWarmStartPolicy(
        **{
            f.name: declared[f.name]
            for f in fields(FiberFrameLearnedWarmStartPolicy)
            if f.init
        }
    )
    if _bytes(policy.to_dict()) != _bytes(declared):
        raise ValueError("policy artifact or contract mismatch")
    return policy


def _study_phases_valid(value: Any, resource: dict[str, Any]) -> bool:
    expected = {
        "schema_version",
        "study_started",
        "phases",
        "measurement_contract_pass",
        "local_timing_evidence_eligible",
        "cpu_scope",
        "phase_accounting_scope",
        "per_phase_peak_memory_bytes",
        "per_phase_peak_memory_reason",
        "physical_validation_claimed",
        "generalized_speedup_claimed",
    }
    if type(value) is not dict or set(value) != expected:
        return False
    if (
        value["schema_version"] != "fiber-frame-learning-study-phase-runtime.v1"
        or value["study_started"] is not True
        or type(value["measurement_contract_pass"]) is not bool
        or type(value["local_timing_evidence_eligible"]) is not bool
        or value["per_phase_peak_memory_bytes"] is not None
        or value["per_phase_peak_memory_reason"] != "phases_share_one_process"
        or value["physical_validation_claimed"] is not False
        or value["generalized_speedup_claimed"] is not False
        or any(
            type(value[key]) is not str or not value[key]
            for key in ("cpu_scope", "phase_accounting_scope")
        )
        or type(value["phases"]) is not dict
        or set(value["phases"]) != {"data_collection", "training_attempt", "evaluation"}
    ):
        return False
    rows = list(value["phases"].values())
    row_fields = {
        "status",
        "reason",
        "scope",
        "wall_ns",
        "cpu_process_time_ns",
        "exception_type",
        "measurement_errors",
    }
    for row in rows:
        if type(row) is not dict or set(row) != row_fields:
            return False
        if (
            row["status"] not in ("skipped", "completed", "blocked", "exception")
            or type(row["scope"]) is not str
            or not row["scope"]
            or any(
                row[key] is not None and type(row[key]) is not str
                for key in ("reason", "exception_type")
            )
            or type(row["measurement_errors"]) is not list
        ):
            return False
        for error in row["measurement_errors"]:
            if (
                type(error) is not dict
                or set(error) != {"field", "reason"}
                or error["field"] not in ("wall_ns", "cpu_process_time_ns")
                or error["reason"]
                not in ("clock_raised", "clock_value_invalid", "clock_regressed")
            ):
                return False
        for field in ("wall_ns", "cpu_process_time_ns"):
            if row["status"] == "skipped":
                if row[field] is not None:
                    return False
            elif row[field] is None:
                if not any(
                    error["field"] == field for error in row["measurement_errors"]
                ):
                    return False
            elif type(row[field]) is not int or row[field] < 0:
                return False
    observed = [row for row in rows if row["status"] != "skipped"]
    if resource["study_status"] == "ready" and any(
        row["status"] != "completed" for row in rows
    ):
        return False
    stopped = False
    for name in ("data_collection", "training_attempt", "evaluation"):
        status = value["phases"][name]["status"]
        if stopped and status != "skipped":
            return False
        if status != "completed":
            stopped = True
    valid = bool(observed) and all(not row["measurement_errors"] for row in observed)
    if value["measurement_contract_pass"] is not valid:
        return False
    if value["local_timing_evidence_eligible"] and not valid:
        return False
    for field, outer in (
        ("wall_ns", "workload_wall_ns"),
        ("cpu_process_time_ns", "workload_cpu_process_time_ns"),
    ):
        if sum(row[field] or 0 for row in rows) > resource[outer]:
            return False
    return True


def _resource_validation_failure(
    value: Any,
    worker_pid: int,
    revision: str,
    suite_artifact: dict[str, Any] | None,
    profile: _ProcessProfile = _RUNTIME,
) -> str | None:
    integer_fields = {
        f"{profile.report_stem}_byte_length",
        "input_read_wall_ns",
        "input_bytes_read",
        "workload_wall_ns",
        "workload_cpu_process_time_ns",
        "report_encode_wall_ns",
        "report_write_flush_fsync_wall_ns",
        "report_bytes_written",
        "worker_observed_wall_ns",
        "cpu_process_time_ns",
    }
    scope_fields = {
        "input_io_scope",
        "workload_scope",
        "process_cpu_scope",
        "peak_memory_scope_or_reason",
        "per_strategy_peak_memory_reason",
        "gpu_time_reason",
    }
    false_fields = {
        "resource_sidecar_io_included",
        "source_revision_is_attestation",
        "independent_hardware_validation",
        "generalized_speedup_claimed",
    }
    expected = (
        integer_fields
        | scope_fields
        | false_fields
        | {
            "schema_version",
            "worker_pid",
            "source_revision",
            "status",
            "measurement_contract_pass",
            f"{profile.report_stem}_sha256",
            "inputs",
            "peak_memory_bytes",
            "per_strategy_peak_memory_bytes",
            "gpu_time_ns",
        }
    )
    if profile == _LEARNING:
        expected |= {
            "study_phases",
            "study_status",
            "per_phase_peak_memory_bytes",
            "per_phase_peak_memory_reason",
        }
    if profile in (_STRATEGY, _CANDIDATE):
        expected.add("strategy")
    if type(value) is not dict or set(value) != expected:
        return "worker_resources_contract_invalid"
    if (
        value["schema_version"] != f"{profile.schema_prefix}-resources.v1"
        or type(value["worker_pid"]) is not int
        or type(value["measurement_contract_pass"]) is not bool
        or value["status"]
        != ("ready" if value["measurement_contract_pass"] is True else "blocked")
        or any(type(value[key]) is not int or value[key] < 0 for key in integer_fields)
        or any(type(value[key]) is not str or not value[key] for key in scope_fields)
        or any(value[key] is not False for key in false_fields)
        or type(value["inputs"]) is not list
        or (
            value["per_strategy_peak_memory_bytes"] != value["peak_memory_bytes"]
            if profile in (_STRATEGY, _CANDIDATE)
            else value["per_strategy_peak_memory_bytes"] is not None
        )
        or value["gpu_time_ns"] is not None
        or (
            value["peak_memory_bytes"] is not None
            and (
                type(value["peak_memory_bytes"]) is not int
                or value["peak_memory_bytes"] <= 0
            )
        )
    ):
        return "worker_resources_contract_invalid"
    if profile == _STRATEGY:
        from structural_analysis.benchmark.fiber_frame_runtime import (
            FIBER_FRAME_AI_STRATEGY,
            FIBER_FRAME_NON_AI_STRATEGY,
            FIBER_FRAME_REFERENCE_STRATEGY,
        )

        if (
            value["strategy"]
            not in (
                FIBER_FRAME_REFERENCE_STRATEGY,
                FIBER_FRAME_NON_AI_STRATEGY,
                FIBER_FRAME_AI_STRATEGY,
            )
            or type(value["per_strategy_peak_memory_bytes"])
            is not type(value["peak_memory_bytes"])
            or value["per_strategy_peak_memory_reason"] != STRATEGY_PEAK_SCOPE
            or value["workload_scope"] != profile.workload_scope
            or value["input_io_scope"]
            != "bounded_file_reads_only_excluding_decode_parse_and_hashing"
            or value["process_cpu_scope"]
            != "worker_process_lifetime_through_strategy_persistence_excluding_resource_sidecar_emission"
            or value["gpu_time_reason"] != "cpu_only_solver_path"
        ):
            return "worker_resources_contract_invalid"
    if profile == _CANDIDATE and (
        value["strategy"] not in ("deterministic", "learned", "oracle")
        or type(value["per_strategy_peak_memory_bytes"])
        is not type(value["peak_memory_bytes"])
        or value["per_strategy_peak_memory_reason"] != CANDIDATE_PEAK_SCOPE
        or value["workload_scope"] != profile.workload_scope
        or value["input_io_scope"]
        != "bounded_file_reads_only_excluding_decode_parse_and_hashing"
        or value["process_cpu_scope"]
        != "worker_process_lifetime_through_search_persistence_excluding_resource_sidecar_emission"
        or value["gpu_time_reason"] != "cpu_only_solver_path"
    ):
        return "worker_resources_contract_invalid"
    if profile == _LEARNING and (
        not _study_phases_valid(value["study_phases"], value)
        or value["study_status"] not in ("ready", "blocked")
        or value["measurement_contract_pass"]
        is not (
            value["study_status"] == "ready"
            and value["study_phases"]["measurement_contract_pass"]
            and value["study_phases"]["local_timing_evidence_eligible"]
        )
        or value["per_phase_peak_memory_bytes"] is not None
        or value["per_phase_peak_memory_reason"]
        != "learning_phases_share_one_worker_address_space"
    ):
        return "worker_resources_contract_invalid"
    if (
        value["worker_pid"] != worker_pid
        or value["source_revision"] != revision
        or suite_artifact
        != {
            "sha256": value[f"{profile.report_stem}_sha256"],
            "byte_length": value[f"{profile.report_stem}_byte_length"],
        }
        or value["report_bytes_written"] != value[f"{profile.report_stem}_byte_length"]
    ):
        return "worker_resource_identity_mismatch"
    return None


def _worker(
    request_path: Path,
    source_revision: str,
    output: Path,
    profile: _ProcessProfile = _RUNTIME,
) -> int:
    if profile == _CANDIDATE:
        from structural_analysis.benchmark.fiber_frame_candidate_process import (
            _worker as candidate_worker,
        )

        return candidate_worker(request_path, source_revision, output)
    started = perf_counter_ns()
    reads: list[dict[str, Any]] = []
    stage = "imports"
    phase_runtime = None
    try:
        from structural_analysis.api import PublicRCFiberFrameConfig
        from structural_analysis.benchmark.fiber_frame_runtime import (
            FiberFrameRuntimeBenchmarkConfig,
        )
        from structural_analysis.benchmark.fiber_frame_runtime_suite import (
            FiberFrameRuntimeCase,
            benchmark_public_rc_fiber_frame_runtime_suite,
        )
        from structural_analysis.io.neutral.loader import load_neutral_json_bytes

        if profile == _LEARNING:
            from structural_analysis.ai.fiber_frame_warm_start_data import (
                FiberFrameWarmStartDataCase,
            )
            from structural_analysis.benchmark.fiber_frame_learning_study import (
                FiberFrameLearningStudyPhaseRecorder,
                run_fiber_frame_learning_study,
            )
        if profile == _STRATEGY:
            from structural_analysis.benchmark.fiber_frame_runtime_strategy import (
                benchmark_public_rc_fiber_frame_runtime_strategy,
            )

        def read(path: Path, limit: int) -> bytes:
            tick = perf_counter_ns()
            with path.open("rb") as handle:
                data = handle.read(limit + 1)
            elapsed = perf_counter_ns() - tick
            if len(data) > limit:
                raise ValueError("input size limit exceeded")
            reads.append(
                {
                    "path": str(path),
                    "byte_length": len(data),
                    "sha256": _digest(data),
                    "read_wall_ns": elapsed,
                }
            )
            return data

        stage = "input_contract"
        request = _json(read(request_path, 1024 * 1024))
        _fields(
            request,
            {
                "schema_version",
                "cases",
                "benchmark_configuration",
                "learning_configuration" if profile == _LEARNING else "policy_file",
            }
            | ({"strategy"} if profile == _STRATEGY else set()),
        )
        if request["schema_version"] != f"{profile.schema_prefix}-request.v1":
            raise ValueError("unsupported request schema")
        if type(request["cases"]) is not list or not 1 <= len(request["cases"]) <= 64:
            raise ValueError("one to 64 cases required")
        configuration = request["benchmark_configuration"]
        _fields(
            configuration, {f.name for f in fields(FiberFrameRuntimeBenchmarkConfig)}
        )
        if type(configuration["damping_factors"]) is not list:
            raise ValueError("damping_factors must be a JSON array")
        configuration = {
            **configuration,
            "damping_factors": tuple(configuration["damping_factors"]),
        }
        measure = FiberFrameRuntimeBenchmarkConfig(**configuration)
        learning_configuration = None
        if profile == _LEARNING:
            learning_configuration = request["learning_configuration"]
            _fields(learning_configuration, {"ridge", "ood_margin"})
            for name, value in learning_configuration.items():
                if (
                    type(value) not in (float, int)
                    or not math.isfinite(value)
                    or value < 0
                    or (name == "ridge" and value == 0)
                ):
                    raise ValueError("invalid learning configuration")
        cases = []
        for row in request["cases"]:
            row_fields = {"case_id", "model_file", "configuration"}
            if profile == _LEARNING:
                row_fields |= {
                    "project_id",
                    "geometry_family_id",
                    "load_history_id",
                    "split",
                }
            _fields(row, row_fields)
            _fields(
                row["configuration"], {f.name for f in fields(PublicRCFiberFrameConfig)}
            )
            if type(row["model_file"]) is not str or not row["model_file"]:
                raise ValueError("model_file must be a path")
            path = (request_path.parent / row["model_file"]).resolve()
            model = load_neutral_json_bytes(
                read(path, 16 * 1024 * 1024), source_path=str(path)
            )
            public_config = PublicRCFiberFrameConfig(**row["configuration"])
            if profile == _LEARNING:
                cases.append(
                    FiberFrameWarmStartDataCase(
                        case_id=row["case_id"],
                        project_id=row["project_id"],
                        geometry_family_id=row["geometry_family_id"],
                        load_history_id=row["load_history_id"],
                        split=row["split"],
                        model=model,
                        config=public_config,
                    )
                )
            else:
                cases.append(
                    FiberFrameRuntimeCase(row["case_id"], model, public_config)
                )
        policy = None
        if profile != _LEARNING and request["policy_file"] is not None:
            if type(request["policy_file"]) is not str or not request["policy_file"]:
                raise ValueError("policy_file must be null or a path")
            path = (request_path.parent / request["policy_file"]).resolve()
            policy = _decode_policy(read(path, 16 * 1024 * 1024))
        stage = (
            "runtime_strategy"
            if profile == _STRATEGY
            else "learning_study"
            if profile == _LEARNING
            else "runtime_suite"
        )
        if profile == _LEARNING:
            phase_runtime = FiberFrameLearningStudyPhaseRecorder()
        wall_start, cpu_start = perf_counter_ns(), process_time_ns()
        if profile == _LEARNING:
            result = run_fiber_frame_learning_study(
                cases,
                source_revision=source_revision,
                benchmark_config=measure,
                phase_runtime=phase_runtime,
                **learning_configuration,
            )
        elif profile == _STRATEGY:
            result = benchmark_public_rc_fiber_frame_runtime_strategy(
                cases,
                strategy=request["strategy"],
                source_revision=source_revision,
                benchmark_config=measure,
                ai_policy=policy,
            )
        else:
            result = benchmark_public_rc_fiber_frame_runtime_suite(
                cases,
                source_revision=source_revision,
                benchmark_config=measure,
                ai_opt_in=policy is not None,
                ai_policy=policy,
            )
        workload_cpu, workload_wall = (
            process_time_ns() - cpu_start,
            perf_counter_ns() - wall_start,
        )
        stage = "report_persistence"
        phase_report = phase_runtime.to_dict() if phase_runtime is not None else None
        measurement_contract_pass = (
            (
                result.status == "ready"
                and phase_report["measurement_contract_pass"]
                and phase_report["local_timing_evidence_eligible"]
            )
            if profile == _LEARNING
            else (
                result["measurement_contract_pass"]
                if profile == _STRATEGY
                else result.measurement_contract_pass
            )
        )
        encoding_start = perf_counter_ns()
        encoded = _bytes(result if profile == _STRATEGY else result.to_dict())
        encoding_wall = perf_counter_ns() - encoding_start
        write_start = perf_counter_ns()
        _write(output / profile.report_file, encoded)
        write_wall = perf_counter_ns() - write_start
        peak, peak_scope = _peak_rss()
        resource_report = {
            "schema_version": f"{profile.schema_prefix}-resources.v1",
            "worker_pid": os.getpid(),
            "source_revision": source_revision,
            "status": "ready" if measurement_contract_pass else "blocked",
            "measurement_contract_pass": measurement_contract_pass,
            f"{profile.report_stem}_sha256": _digest(encoded),
            f"{profile.report_stem}_byte_length": len(encoded),
            "inputs": reads,
            "input_read_wall_ns": sum(row["read_wall_ns"] for row in reads),
            "input_bytes_read": sum(row["byte_length"] for row in reads),
            "input_io_scope": "bounded_file_reads_only_excluding_decode_parse_and_hashing",
            "workload_wall_ns": workload_wall,
            "workload_cpu_process_time_ns": workload_cpu,
            "workload_scope": profile.workload_scope,
            "report_encode_wall_ns": encoding_wall,
            "report_write_flush_fsync_wall_ns": write_wall,
            "report_bytes_written": len(encoded),
            "worker_observed_wall_ns": perf_counter_ns() - started,
            "cpu_process_time_ns": process_time_ns(),
            "process_cpu_scope": f"worker_process_lifetime_through_{profile.report_stem}_persistence_excluding_resource_sidecar_emission",
            "peak_memory_bytes": peak,
            "peak_memory_scope_or_reason": peak_scope,
            "per_strategy_peak_memory_bytes": peak if profile == _STRATEGY else None,
            "per_strategy_peak_memory_reason": (
                STRATEGY_PEAK_SCOPE
                if profile == _STRATEGY
                else "arms_share_one_fresh_worker_process"
            ),
            "gpu_time_ns": None,
            "gpu_time_reason": "cpu_only_solver_path",
            "resource_sidecar_io_included": False,
            "source_revision_is_attestation": False,
            "independent_hardware_validation": False,
            "generalized_speedup_claimed": False,
        }
        if profile == _STRATEGY:
            resource_report["strategy"] = request["strategy"]
        if phase_runtime is not None:
            resource_report.update(
                study_phases=phase_report,
                study_status=result.status,
                per_phase_peak_memory_bytes=None,
                per_phase_peak_memory_reason="learning_phases_share_one_worker_address_space",
            )
        _write(output / "resources.json", _bytes(resource_report))
        return 0 if measurement_contract_pass else 2
    except Exception as error:
        _write(
            output / "failure.json",
            _bytes(
                {
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "measurement_contract_pass": False,
                    "worker_pid": os.getpid(),
                    **(
                        {"study_phases": phase_runtime.to_dict()}
                        if phase_runtime is not None
                        else {}
                    ),
                }
            ),
        )
        return 3


def _run_fiber_frame_process(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    profile: _ProcessProfile,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Retain all output in a fresh private directory, including failed attempts."""
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}"
        if profile == _LEARNING
        else r"[0-9a-f]{40}|sha256:[0-9a-f]{64}",
        source_revision,
    ):
        raise ValueError("full source revision required")
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be finite and positive")
    output = Path(output_directory).resolve()
    if Path(output_directory).is_symlink():
        raise ValueError("output directory must be new")
    output.mkdir(mode=0o700, exist_ok=False)
    environment = os.environ.copy()
    source_root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = str(source_root)
    command = [
        sys.executable,
        "-m",
        "structural_analysis.benchmark.fiber_frame_runtime_process",
        "--worker",
        "--workload",
        profile.workload,
        "--request",
        str(Path(request_path).resolve()),
        "--source-revision",
        source_revision,
        "--output-directory",
        str(output),
    ]
    wall, cpu = perf_counter_ns(), process_time_ns()
    timed_out = False
    with (
        (output / "worker.stdout").open("xb") as stdout,
        (output / "worker.stderr").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            command, cwd=source_root, env=environment, stdout=stdout, stderr=stderr
        )
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    launch_elapsed = perf_counter_ns() - wall
    resources = None
    resources_path = output / "resources.json"
    validation_failure = "worker_timeout" if timed_out else "worker_resources_missing"
    # A timeout can interrupt the exclusive sidecar write at any byte. Retain
    # those bytes as an artifact, but never parse or credit partial measurements.
    if resources_path.exists() and not timed_out:
        try:
            resources = _json(resources_path.read_bytes())
            validation_failure = None
        except (ValueError, UnicodeError, RecursionError):
            validation_failure = "worker_resources_json_invalid"
    artifacts = {
        name: {
            "sha256": _digest((output / name).read_bytes()),
            "byte_length": (output / name).stat().st_size,
        }
        for name in (profile.report_file, "resources.json", "failure.json")
        if (output / name).is_file()
    }
    if validation_failure is None:
        validation_failure = _resource_validation_failure(
            resources,
            process.pid,
            source_revision,
            artifacts.get(profile.report_file),
            profile,
        )
    if validation_failure is not None:
        resources = None
    report = {
        "schema_version": f"{profile.schema_prefix}-manifest.v1",
        "source_revision": source_revision,
        "status": "timeout"
        if timed_out
        else "ready"
        if exit_code == 0
        and resources is not None
        and resources["status"] == "ready"
        and resources["measurement_contract_pass"] is True
        else "blocked",
        "worker_pid": process.pid,
        "parent_pid": os.getpid(),
        "worker_exit_code": exit_code,
        "fresh_python_process": process.pid != os.getpid(),
        "launch_to_exit_wall_ns": launch_elapsed,
        "parent_orchestration_cpu_time_ns": process_time_ns() - cpu,
        "parent_cpu_scope": "launch_wait_and_artifact_validation_before_manifest_emission",
        "launch_scope": f"spawn_imports_inputs_{profile.report_stem}_and_worker_persistence_excluding_manifest_emission",
        "artifacts": artifacts,
        "worker_measurements_available": resources is not None and not timed_out,
        "worker_resource_validation_failure": validation_failure,
        "source_revision_is_attestation": False,
        "independent_validation": False,
    }
    _write(output / "manifest.json", _bytes(report))
    return report


def run_fiber_frame_runtime_process(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Measure a runtime suite using its existing version-one artifact contract."""
    return _run_fiber_frame_process(
        request_path,
        source_revision=source_revision,
        output_directory=output_directory,
        timeout_seconds=timeout_seconds,
        profile=_RUNTIME,
    )


def run_fiber_frame_learning_process(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Measure full data generation, train-only fitting and frozen evaluation."""
    return _run_fiber_frame_process(
        request_path,
        source_revision=source_revision,
        output_directory=output_directory,
        timeout_seconds=timeout_seconds,
        profile=_LEARNING,
    )


def run_fiber_frame_strategy_process(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Observe one declared strategy batch in its own Python address space."""
    return _run_fiber_frame_process(
        request_path,
        source_revision=source_revision,
        output_directory=output_directory,
        timeout_seconds=timeout_seconds,
        profile=_STRATEGY,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument(
        "--workload",
        choices=(
            "runtime-suite",
            "learning-study",
            "runtime-strategy",
            "candidate-search-arm",
        ),
        default="runtime-suite",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    profile = {
        item.workload: item for item in (_RUNTIME, _LEARNING, _STRATEGY, _CANDIDATE)
    }[args.workload]
    if args.worker:
        return _worker(
            args.request, args.source_revision, args.output_directory, profile
        )
    try:
        report = _run_fiber_frame_process(
            args.request,
            source_revision=args.source_revision,
            output_directory=args.output_directory,
            timeout_seconds=args.timeout_seconds,
            profile=profile,
        )
    except (ValueError, OSError) as error:
        parser.error(type(error).__name__)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
