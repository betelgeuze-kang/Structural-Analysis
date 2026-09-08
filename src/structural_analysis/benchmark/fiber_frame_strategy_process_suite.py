"""Isolated strategy batches with full-history cross-worker comparisons.

The request uses rc-fiber-runtime-process-request.v1. This is an additional
frozen-policy experiment, not a replacement or a relabeling of an older suite.
Each worker executes one strategy over all declared cases, warmups and repeats.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, fields
import json
import math
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FiberFrameRuntimeBenchmarkConfig,
    _aggregate_material_trial,
    _compare_path_comparison_snapshots,
    _distribution,
    _observed_comparison,
    _solver_config_payload,
    _strategy_summary,
    _unmeasured_distribution,
    public_api,
)
from structural_analysis.benchmark.fiber_frame_runtime_suite import (
    FiberFrameRuntimeCase,
    _policy_identity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


SCHEMA_VERSION = "rc-fiber-strategy-process-suite.v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REFERENCE = FIBER_FRAME_REFERENCE_STRATEGY
_DETERMINISTIC = FIBER_FRAME_NON_AI_STRATEGY
_LEARNED = FIBER_FRAME_AI_STRATEGY


def _identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": process._digest(data),
        "byte_length": len(data),
    }


def _unchanged(identities: list[dict[str, Any]]) -> bool:
    try:
        return all(
            _identity(Path(row["path"]))
            == {k: v for k, v in row.items() if k != "original_path"}
            for row in identities
        )
    except OSError:
        return False


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit exceeded")
    return data


def _runtime_bindings_for_input(
    snapshot: Any, config: PublicRCFiberFrameConfig
) -> dict[str, str] | None:
    compiled, _, _ = public_api._compile(snapshot)
    if compiled is None:
        return None
    problem = compiled.problem
    return {
        "problem_contract_hash": problem.contract_hash,
        "compiler_profile": public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        "solver_id": public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
        "coordinate_binding_hash": canonical_hash(
            {
                "problem_contract_hash": problem.contract_hash,
                "free_global_dofs": list(problem.free_global_dofs),
                "physical_coordinate_scale": problem.physical_coordinate_scale.tolist(),
                "coordinate_profile": "generalized-free-solver-coordinates-m.v1",
            }
        ),
        "solver_config_hash": canonical_hash(
            _solver_config_payload(
                NewtonRaphsonConfig(
                    residual_tolerance=config.residual_tolerance,
                    increment_tolerance=config.increment_tolerance_m,
                    max_iterations=config.maximum_iterations,
                )
            )
        ),
        "load_history_hash": canonical_hash(list(config.target_load_factors)),
    }


def _freeze_inputs(request_path: Path, output: Path) -> dict[str, Any]:
    """Snapshot all inputs before launching any worker, with raw byte identities."""
    frozen = output / "inputs"
    frozen.mkdir(mode=0o700)
    raw_request = _read_bounded(request_path, 1024 * 1024)
    process._write(frozen / "original-request.json", raw_request)
    request = process._json(raw_request)
    process._fields(
        request,
        {"schema_version", "cases", "benchmark_configuration", "policy_file"},
    )
    if request["schema_version"] != "rc-fiber-runtime-process-request.v1":
        raise ValueError("unsupported request schema")
    if type(request["cases"]) is not list or not 1 <= len(request["cases"]) <= 64:
        raise ValueError("one to 64 cases required")
    configuration = request["benchmark_configuration"]
    process._fields(
        configuration, {f.name for f in fields(FiberFrameRuntimeBenchmarkConfig)}
    )
    if type(configuration["damping_factors"]) is not list:
        raise ValueError("damping_factors must be a JSON array")
    measure = FiberFrameRuntimeBenchmarkConfig(
        **{**configuration, "damping_factors": tuple(configuration["damping_factors"])}
    )
    bindings, runtime_bindings, case_requests, originals = [], [], [], []
    for index, row in enumerate(request["cases"]):
        process._fields(row, {"case_id", "model_file", "configuration"})
        process._fields(
            row["configuration"], {f.name for f in fields(PublicRCFiberFrameConfig)}
        )
        if type(row["model_file"]) is not str or not row["model_file"]:
            raise ValueError("model_file must be a path")
        original = (request_path.parent / row["model_file"]).resolve()
        target = frozen / f"model-{index:03d}.json"
        process._write(target, _read_bounded(original, 16 * 1024 * 1024))
        model = load_neutral_json_bytes(target.read_bytes(), source_path=str(target))
        case = FiberFrameRuntimeCase(
            row["case_id"], model, PublicRCFiberFrameConfig(**row["configuration"])
        )
        snapshot = case.model.detached_analysis_snapshot()
        runtime_bindings.append(_runtime_bindings_for_input(snapshot, case.config))
        bindings.append(
            {
                "case_id": case.case_id,
                "canonical_model_checksum": snapshot.canonical_model_checksum,
                "model_identity_available": True,
                "input_checksum": case.model.input_checksum,
                "public_solver_configuration": asdict(case.config),
                "target_load_factors": list(case.config.target_load_factors),
            }
        )
        case_requests.append(
            {
                "case_id": case.case_id,
                "model_file": str(target),
                "configuration": asdict(case.config),
            }
        )
        originals.append({"original_path": str(original), **_identity(target)})
    if len({row["case_id"] for row in bindings}) != len(bindings):
        raise ValueError("case_id values must be unique")
    policy = None
    policy_file = None
    if request["policy_file"] is not None:
        if type(request["policy_file"]) is not str or not request["policy_file"]:
            raise ValueError("policy_file must be null or a path")
        original = (request_path.parent / request["policy_file"]).resolve()
        policy_file = frozen / "policy.json"
        process._write(policy_file, _read_bounded(original, 16 * 1024 * 1024))
        policy = _policy_identity(process._decode_policy(policy_file.read_bytes()))
        originals.append({"original_path": str(original), **_identity(policy_file)})
    return {
        "case_bindings": bindings,
        "case_runtime_bindings": runtime_bindings,
        "case_requests": case_requests,
        "benchmark_configuration": measure.to_dict(),
        "policy": policy,
        "policy_file": str(policy_file) if policy_file is not None else None,
        "original_request": {
            "original_path": str(request_path),
            **_identity(frozen / "original-request.json"),
        },
        "inputs": originals,
    }


def _finite_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _ordered_rows(rows: Any, key: str, count: int) -> bool:
    return (
        type(rows) is list
        and len(rows) == count
        and all(
            type(row) is dict and type(row.get(key)) is int and row[key] == index
            for index, row in enumerate(rows)
        )
    )


def _material_subset_contract(record: Any, enclosing_wall_ns: int) -> bool:
    """A complete material observation must fit its enclosing assembly interval."""
    material = _aggregate_material_trial([record])
    if not material["coverage_complete"]:
        return True
    return material["wall_ns"] <= enclosing_wall_ns and all(
        item["exception_count"] <= item["call_count"]
        for item in (material, *material["materials"].values())
    )


def _run_cost_contract(row: dict[str, Any], step_count: int) -> bool:
    """Validate every required cost input before the common summary reads it."""
    scalars = (
        "wall_ns",
        "execution_call_wall_ns",
        "selected_solve_wall_ns",
        "attempted_solve_wall_ns",
        "verification_wall_ns",
        "execution_and_authority_verification_wall_ns",
        "inference_wall_ns",
        "guard_wall_ns",
        "seeded_attempt_wall_ns",
        "baseline_recovery_wall_ns",
        "guard_assembly_call_count",
        "newton_iteration_count",
        "attempted_newton_iteration_count",
        "attempted_line_search_evaluation_count",
        "execution_cpu_process_time_ns",
        "verification_cpu_process_time_ns",
        "execution_and_authority_verification_cpu_process_time_ns",
    )
    if any(not _finite_nonnegative_int(row.get(key)) for key in scalars):
        return False
    newton_fields = (
        "total_wall_ns",
        "assemble_wall_ns",
        "unattributed_wall_ns",
        "run_count",
        "completed_run_count",
        "exception_run_count",
        "assemble_call_count",
        "assemble_exception_count",
        "linear_solve_wall_ns",
        "linear_solve_call_count",
        "linear_solve_exception_count",
    )
    stateful_fields = (
        "total_wall_ns",
        "terminal_trial_assembly_wall_ns",
        "unattributed_wall_ns",
        "run_count",
        "completed_run_count",
        "exception_run_count",
        "terminal_trial_assembly_call_count",
        "terminal_trial_assembly_exception_count",
    )
    for prefix in ("selected", "attempted"):
        newton = row.get(f"{prefix}_newton_runtime")
        stateful = row.get(f"{prefix}_stateful_runtime")
        if (
            type(newton) is not dict
            or type(stateful) is not dict
            or any(
                not _finite_nonnegative_int(newton.get(key)) for key in newton_fields
            )
            or any(
                not _finite_nonnegative_int(stateful.get(key))
                for key in stateful_fields
            )
        ):
            return False
        if (
            newton["assemble_wall_ns"]
            + newton["linear_solve_wall_ns"]
            + newton["unattributed_wall_ns"]
            != newton["total_wall_ns"]
            or stateful["terminal_trial_assembly_wall_ns"]
            + newton["total_wall_ns"]
            + stateful["unattributed_wall_ns"]
            != stateful["total_wall_ns"]
            or stateful["total_wall_ns"] > row[f"{prefix}_solve_wall_ns"]
            or newton["completed_run_count"] + newton["exception_run_count"]
            != newton["run_count"]
            or stateful["completed_run_count"] + stateful["exception_run_count"]
            != stateful["run_count"]
            or newton["assemble_exception_count"] > newton["assemble_call_count"]
            or newton["linear_solve_exception_count"]
            > newton["linear_solve_call_count"]
            or stateful["terminal_trial_assembly_exception_count"]
            > stateful["terminal_trial_assembly_call_count"]
            or not _material_subset_contract(
                newton.get("material_trial"), newton["assemble_wall_ns"]
            )
            or not _material_subset_contract(
                stateful.get("terminal_material_trial"),
                stateful["terminal_trial_assembly_wall_ns"],
            )
        ):
            return False
    if (
        row["selected_solve_wall_ns"] > row["attempted_solve_wall_ns"]
        or row["attempted_solve_wall_ns"]
        + row["inference_wall_ns"]
        + row["guard_wall_ns"]
        > row["wall_ns"]
        or row["wall_ns"] > row["execution_call_wall_ns"]
        or row["execution_call_wall_ns"] + row["verification_wall_ns"]
        > row["execution_and_authority_verification_wall_ns"]
        or row["execution_cpu_process_time_ns"]
        + row["verification_cpu_process_time_ns"]
        > row["execution_and_authority_verification_cpu_process_time_ns"]
        or row["seeded_attempt_wall_ns"] + row["baseline_recovery_wall_ns"]
        > row["attempted_solve_wall_ns"]
    ):
        return False
    steps = row.get("steps")
    return (
        type(steps) is list
        and len(steps) == step_count
        and all(
            type(step) is dict
            and _finite_nonnegative_int(step.get("guard_wall_ns"))
            and _material_subset_contract(
                step.get("guard_material_trial"), step["guard_wall_ns"]
            )
            and {"seeded_attempt", "baseline_recovery"} <= step.keys()
            and all(
                step[name] is None or type(step[name]) is dict
                for name in ("seeded_attempt", "baseline_recovery")
            )
            for step in steps
        )
    )


def _validate_worker_payload(
    report: Any,
    resources: Any,
    manifest: Any,
    *,
    strategy: str,
    source_revision: str,
    expected_declaration: dict[str, Any],
    expected_inputs: list[dict[str, Any]],
    expected_runtime_bindings: list[dict[str, Any] | None] | None = None,
) -> list[str]:
    """Check transport and complete ordered scope before using worker observations."""
    try:
        return _validate_worker_payload_impl(
            report,
            resources,
            manifest,
            strategy=strategy,
            source_revision=source_revision,
            expected_declaration=expected_declaration,
            expected_inputs=expected_inputs,
            expected_runtime_bindings=expected_runtime_bindings,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ArithmeticError,
        RecursionError,
    ):
        return ["worker_payload_invalid"]


def _validate_resource_observation(
    report: Any,
    resources: Any,
    manifest: Any,
    *,
    strategy: str,
    source_revision: str,
    expected_inputs: list[dict[str, Any]],
) -> list[str]:
    errors = []
    if (
        type(manifest) is not dict
        or type(resources) is not dict
        or type(report) is not dict
    ):
        return ["worker_payload_missing"]
    if (
        manifest.get("schema_version") != "rc-fiber-strategy-process-manifest.v1"
        or manifest.get("source_revision") != source_revision
        or manifest.get("fresh_python_process") is not True
        or type(manifest.get("worker_pid")) is not int
        or type(manifest.get("parent_pid")) is not int
        or manifest["worker_pid"] == manifest["parent_pid"]
        or manifest.get("worker_measurements_available") is not True
        or manifest.get("worker_resource_validation_failure") is not None
        or manifest.get("source_revision_is_attestation") is not False
        or manifest.get("independent_validation") is not False
        or type(manifest.get("artifacts")) is not dict
    ):
        errors.append("worker_manifest_identity_or_availability_mismatch")
    failure = process._resource_validation_failure(
        resources,
        manifest.get("worker_pid"),
        source_revision,
        manifest.get("artifacts", {}).get("strategy.json"),
        process._STRATEGY,
    )
    if failure is not None:
        return errors + [failure]
    for name, value in (("strategy.json", report), ("resources.json", resources)):
        raw = process._bytes(value)
        if manifest["artifacts"].get(name) != {
            "sha256": process._digest(raw),
            "byte_length": len(raw),
        }:
            errors.append("worker_payload_byte_binding_mismatch")
    if resources["strategy"] != strategy:
        errors.append("worker_strategy_mismatch")
    inputs = resources["inputs"]
    if (
        len(inputs) != len(expected_inputs)
        or any(
            type(row) is not dict
            or set(row) != {"path", "sha256", "byte_length", "read_wall_ns"}
            or not _finite_nonnegative_int(row["read_wall_ns"])
            for row in inputs
        )
        or [{k: v for k, v in row.items() if k != "read_wall_ns"} for row in inputs]
        != expected_inputs
    ):
        errors.append("worker_input_snapshot_mismatch")
    elif (
        sum(row["byte_length"] for row in inputs) != resources["input_bytes_read"]
        or sum(row["read_wall_ns"] for row in inputs) != resources["input_read_wall_ns"]
    ):
        errors.append("worker_input_accounting_mismatch")
    if (
        resources["workload_cpu_process_time_ns"] > resources["cpu_process_time_ns"]
        or not _finite_nonnegative_int(manifest.get("launch_to_exit_wall_ns"))
        or resources["worker_observed_wall_ns"] > manifest["launch_to_exit_wall_ns"]
        or sum(
            resources[name]
            for name in (
                "input_read_wall_ns",
                "workload_wall_ns",
                "report_encode_wall_ns",
                "report_write_flush_fsync_wall_ns",
            )
        )
        > resources["worker_observed_wall_ns"]
        or type(resources["per_strategy_peak_memory_bytes"])
        is not type(resources["peak_memory_bytes"])
    ):
        errors.append("worker_resource_accounting_mismatch")
    allowed_peak_scopes = {
        "linux_proc_vmhwm_post_exec_address_space_including_interpreter_imports_and_report_encoding",
        "post_exec_process_peak_rss_not_supported_on_this_platform",
        "post_exec_process_peak_rss_unavailable",
    }
    if resources["peak_memory_scope_or_reason"] not in allowed_peak_scopes or (
        resources["peak_memory_bytes"] is None
    ) is (resources["peak_memory_scope_or_reason"].startswith("linux_proc_")):
        errors.append("worker_peak_scope_mismatch")
    return sorted(set(errors))


def _validate_worker_payload_impl(
    report: Any,
    resources: Any,
    manifest: Any,
    *,
    strategy: str,
    source_revision: str,
    expected_declaration: dict[str, Any],
    expected_inputs: list[dict[str, Any]],
    expected_runtime_bindings: list[dict[str, Any] | None] | None,
) -> list[str]:
    errors = _validate_resource_observation(
        report,
        resources,
        manifest,
        strategy=strategy,
        source_revision=source_revision,
        expected_inputs=expected_inputs,
    )
    if errors:
        return errors
    if (
        report.get("schema_version") != "public-rc-fiber-frame-runtime-strategy.v1"
        or process._bytes(report.get("declaration"))
        != process._bytes(expected_declaration)
        or report.get("strategy_identity_hash") != canonical_hash(expected_declaration)
        or report.get("report_hash")
        != canonical_hash({k: v for k, v in report.items() if k != "report_hash"})
        or report.get("reference_comparison")
        != {
            "status": "not_run",
            "full_history_response_match": None,
            "scope": "parent_cross_strategy_comparison_required",
        }
    ):
        errors.append("worker_report_identity_or_scope_mismatch")
    if (
        manifest.get("status") != "ready"
        or manifest.get("worker_exit_code") != 0
        or resources.get("status") != "ready"
        or resources.get("measurement_contract_pass") is not True
        or report.get("status") != "ready"
        or report.get("measurement_contract_pass") is not True
    ):
        errors.append("worker_selected_path_contract_not_ready")
    expected_cases = expected_declaration["cases_in_execution_order"]
    cases = report.get("cases")
    if type(cases) is not list or len(cases) != len(expected_cases):
        return errors + ["worker_case_coverage_mismatch"]
    cfg = expected_declaration["benchmark_configuration"]
    case_count = len(expected_cases)
    expected_warmups = case_count * cfg["warmup_repetitions"]
    expected_runs = case_count * cfg["repetitions"]
    expected_episodes = expected_runs if strategy == _REFERENCE else 0
    if process._bytes(report.get("coverage")) != process._bytes(
        {
            "declared_case_count": case_count,
            "ready_case_count": case_count,
            "blocked_case_count": 0,
            "unsupported_case_count": 0,
            "error_case_count": 0,
            "expected_warmup_count": expected_warmups,
            "attempted_warmup_count": expected_warmups,
            "ready_warmup_count": expected_warmups,
            "expected_measured_run_count": expected_runs,
            "attempted_measured_run_count": expected_runs,
            "selected_path_authority_pass_count": expected_runs,
            "expected_reference_episode_verification_count": expected_episodes,
            "attempted_reference_episode_verification_count": expected_episodes,
            "reference_episode_verification_pass_count": expected_episodes,
        }
    ):
        errors.append("worker_reported_coverage_mismatch")
    if report.get("policy_execution_contract") != {
        "same_instance_reused_across_cases_warmups_repetitions": strategy == _LEARNED,
        "policy_identity_unchanged": True,
        "policy_reset_between_runs": False,
        "deterministic_inference_asserted": False,
        "training_executed": False,
    }:
        errors.append("worker_policy_execution_contract_mismatch")
    if report.get("measurement_scope") != {
        "clock": "time.perf_counter_ns",
        "cpu_clock": "time.process_time_ns",
        "local_contract": "selected_path_full_j1_j5_recovery_and_reference_only_solver_episode_replay",
        "warmups": "execution_only_no_authority_replay",
        "reference_episode": "separate_nested_wall_and_cpu_scope_in_reference_worker_peak",
        "comparison_snapshot": "complete_checkpoint_and_trial_fields_used_by_legacy_path_comparison",
        "cross_strategy_comparison_included": False,
        "comparison_snapshot_preparation_included_in_verified_run_interval": True,
        "per_phase_peak_memory_bytes": None,
        "per_phase_peak_memory_reason": "phases_share_one_strategy_worker",
        "training_executed": False,
        "worker_imports_input_output_resources": "fresh_process_collector_sidecar",
    }:
        errors.append("worker_measurement_scope_mismatch")
    phase_cpu, phase_wall = 0, 0
    for case_index, (case, binding) in enumerate(
        zip(cases, expected_cases, strict=True)
    ):
        if (
            type(case) is not dict
            or case.get("case_id") != binding["case_id"]
            or process._bytes(case.get("binding")) != process._bytes(binding)
        ):
            errors.append("worker_case_binding_mismatch")
            continue
        if (
            case.get("status") != "ready"
            or case.get("measurement_contract_pass") is not True
            or case.get("failure") is not None
        ):
            errors.append("worker_case_not_ready")
        for name in ("compile_wall_ns", "compile_cpu_process_time_ns"):
            if not _finite_nonnegative_int(case.get(name)):
                errors.append("worker_compile_observation_invalid")
        if not errors:
            phase_cpu += case["compile_cpu_process_time_ns"]
            phase_wall += case["compile_wall_ns"]
        runtime_bindings = case.get("runtime_bindings")
        if expected_runtime_bindings is not None and (
            len(expected_runtime_bindings) != len(expected_cases)
            or runtime_bindings != expected_runtime_bindings[case_index]
        ):
            errors.append("worker_compiled_input_binding_mismatch")
        public_config = binding["public_solver_configuration"]
        expected_solver_hash = canonical_hash(
            _solver_config_payload(
                NewtonRaphsonConfig(
                    residual_tolerance=public_config["residual_tolerance"],
                    increment_tolerance=public_config["increment_tolerance_m"],
                    max_iterations=public_config["maximum_iterations"],
                )
            )
        )
        if (
            type(runtime_bindings) is not dict
            or set(runtime_bindings)
            != {
                "problem_contract_hash",
                "compiler_profile",
                "solver_id",
                "coordinate_binding_hash",
                "solver_config_hash",
                "load_history_hash",
            }
            or runtime_bindings.get("compiler_profile")
            != public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE
            or runtime_bindings.get("solver_id")
            != public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID
            or runtime_bindings.get("solver_config_hash") != expected_solver_hash
            or runtime_bindings.get("load_history_hash")
            != canonical_hash(binding["target_load_factors"])
            or any(
                not isinstance(runtime_bindings.get(name), str)
                or not _HASH.fullmatch(runtime_bindings[name])
                for name in ("problem_contract_hash", "coordinate_binding_hash")
            )
        ):
            errors.append("worker_runtime_binding_mismatch")
            continue
        runs, warmups = case.get("runs"), case.get("warmups")
        if not _ordered_rows(runs, "repetition", cfg["repetitions"]):
            errors.append("worker_run_coverage_mismatch")
            continue
        if not _ordered_rows(warmups, "warmup_index", cfg["warmup_repetitions"]):
            errors.append("worker_warmup_coverage_mismatch")
        elif any(
            row.get("strategy") != strategy
            or row.get("status") != "ready"
            or row.get("contract_pass") is not True
            or row.get("failure") is not None
            or row.get("authority_verification")
            != {
                "status": "not_run",
                "contract_pass": False,
                "reason_code": "warmup_execution_only",
            }
            or any(
                not _finite_nonnegative_int(row.get(name))
                for name in ("wall_ns", "execution_cpu_process_time_ns")
            )
            for row in warmups
        ):
            errors.append("worker_warmup_contract_mismatch")
        elif all(
            _finite_nonnegative_int(row.get("execution_call_wall_ns"))
            and row["wall_ns"] <= row["execution_call_wall_ns"]
            for row in warmups
        ):
            phase_cpu += sum(row["execution_cpu_process_time_ns"] for row in warmups)
            phase_wall += sum(row["execution_call_wall_ns"] for row in warmups)
        else:
            errors.append("worker_warmup_contract_mismatch")
        for row in runs:
            if not _run_cost_contract(row, len(binding["target_load_factors"])):
                errors.append("worker_run_cost_contract_invalid")
            else:
                phase_cpu += row[
                    "execution_and_authority_verification_cpu_process_time_ns"
                ]
                phase_wall += row["execution_and_authority_verification_wall_ns"]
            verification = row.get("authority_verification", {})
            if type(verification) is not dict:
                errors.append("worker_run_authority_or_resource_mismatch")
                continue
            if (
                row.get("strategy") != strategy
                or row.get("status") != "ready"
                or row.get("contract_pass") is not True
                or row.get("failure") is not None
                or row.get("load_step_count") != len(binding["target_load_factors"])
                or row.get("committed_step_count")
                != len(binding["target_load_factors"])
                or type(row.get("load_step_count")) is not int
                or type(row.get("committed_step_count")) is not int
                or verification.get("contract_pass") is not True
                or verification.get("status") != "ready"
                or any(
                    not isinstance(verification.get(name), str)
                    or not _HASH.fullmatch(verification[name])
                    for name in (
                        "checkpoint_chain_hash",
                        "terminal_receipt_hash",
                        "numerical_result_hash",
                        "engineering_result_hash",
                    )
                )
                or any(
                    not _finite_nonnegative_int(row.get(name))
                    for name in (
                        "execution_cpu_process_time_ns",
                        "verification_cpu_process_time_ns",
                        "execution_and_authority_verification_cpu_process_time_ns",
                        "execution_and_authority_verification_wall_ns",
                    )
                )
            ):
                errors.append("worker_run_authority_or_resource_mismatch")
            elif (
                row["execution_cpu_process_time_ns"]
                + row["verification_cpu_process_time_ns"]
                > row["execution_and_authority_verification_cpu_process_time_ns"]
            ):
                errors.append("worker_run_cpu_scope_mismatch")
            snapshot = row.get("comparison_snapshot")
            try:
                comparison = _compare_path_comparison_snapshots(
                    snapshot,
                    snapshot,
                    absolute_tolerance=cfg["response_absolute_tolerance"],
                    relative_tolerance=cfg["response_relative_tolerance"],
                )
                if comparison["full_history_response_match"] is not True:
                    errors.append("worker_snapshot_not_ready")
                checkpoints = snapshot["checkpoints"]
                if (
                    [(r["epoch"], r["load_factor"]) for r in checkpoints]
                    != list(enumerate([0.0, *binding["target_load_factors"]]))
                    or len(snapshot["trial_assemblies"])
                    != len(binding["target_load_factors"])
                    or checkpoints[-1]["state_hash"]
                    != row.get("terminal_checkpoint_state_hash")
                    or any(
                        current["parent_state_hash"] != previous["state_hash"]
                        for previous, current in zip(checkpoints, checkpoints[1:])
                    )
                    or any(
                        r["problem_contract_hash"]
                        != runtime_bindings["problem_contract_hash"]
                        for r in checkpoints
                    )
                ):
                    errors.append("worker_snapshot_execution_binding_mismatch")
            except (ValueError, TypeError, KeyError, ArithmeticError):
                errors.append("worker_snapshot_invalid")
        episode_report = case.get("reference_solver_episode_verification", {})
        episodes = episode_report.get("runs") if type(episode_report) is dict else None
        expected_repetitions = (
            list(range(cfg["repetitions"])) if strategy == _REFERENCE else []
        )
        if (
            not _ordered_rows(episodes, "repetition", len(expected_repetitions))
            or episode_report.get("required") is not (strategy == _REFERENCE)
        ) or any(
            r.get("contract_pass") is not True
            or r.get("status") != "ready"
            or r.get("failure") is not None
            or any(
                not _finite_nonnegative_int(r.get(name))
                for name in ("wall_ns", "cpu_process_time_ns")
            )
            or any(
                not isinstance(r.get(name), str) or not _HASH.fullmatch(r[name])
                for name in ("solver_episode_adapter_hash", "solver_episode_hash")
            )
            for r in episodes
        ):
            errors.append("worker_reference_episode_coverage_mismatch")
        else:
            phase_cpu += sum(row["cpu_process_time_ns"] for row in episodes)
            phase_wall += sum(row["wall_ns"] for row in episodes)
            if strategy == _REFERENCE and any(
                len({row[name] for row in episodes}) != 1
                for name in ("solver_episode_adapter_hash", "solver_episode_hash")
            ):
                errors.append("worker_reference_episode_identity_not_repeatable")
    if (
        phase_cpu > resources["workload_cpu_process_time_ns"]
        or phase_wall > resources["workload_wall_ns"]
    ):
        errors.append("worker_nested_phase_accounting_exceeds_workload")
    return sorted(set(errors))


def _gather_worker(
    directory: Path,
    manifest: dict[str, Any],
    *,
    strategy: str,
    source_revision: str,
    expected_declaration: dict[str, Any],
    expected_inputs: list[dict[str, Any]],
    expected_runtime_bindings: list[dict[str, Any] | None],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "strategy": strategy,
        "output_directory": str(directory),
        "status": "blocked",
        "manifest": manifest,
        "resources": None,
        "resources_validated": False,
        "report": None,
        "validation_errors": [],
    }
    try:
        persisted_manifest = process._json((directory / "manifest.json").read_bytes())
        if persisted_manifest != manifest:
            raise ValueError("worker manifest changed after collection")
        for name in ("strategy.json", "resources.json"):
            data = (directory / name).read_bytes()
            if manifest["artifacts"].get(name) != {
                "sha256": process._digest(data),
                "byte_length": len(data),
            }:
                raise ValueError("worker artifact identity mismatch")
            row["report" if name == "strategy.json" else "resources"] = process._json(
                data
            )
        row["resources_validated"] = not _validate_resource_observation(
            row["report"],
            row["resources"],
            manifest,
            strategy=strategy,
            source_revision=source_revision,
            expected_inputs=expected_inputs,
        )
        row["validation_errors"] = _validate_worker_payload(
            row["report"],
            row["resources"],
            manifest,
            strategy=strategy,
            source_revision=source_revision,
            expected_declaration=expected_declaration,
            expected_inputs=expected_inputs,
            expected_runtime_bindings=expected_runtime_bindings,
        )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, RecursionError):
        row["validation_errors"] = ["worker_artifact_unavailable_or_invalid"]
    row["status"] = "ready" if not row["validation_errors"] else "blocked"
    return row


def _compare_workers(
    workers: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    configuration: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    comparison_wall, comparison_cpu = 0, 0
    cases = []
    strategies = [worker["strategy"] for worker in workers]
    for case_index, binding in enumerate(bindings):
        run_rows = []
        failures = []
        for repetition in range(configuration["repetitions"]):
            reference_worker = next(
                worker for worker in workers if worker["strategy"] == _REFERENCE
            )
            reference = (
                reference_worker["report"]["cases"][case_index]["runs"][repetition]
                if reference_worker["status"] == "ready"
                else None
            )
            for worker in workers:
                if worker["status"] != "ready" or reference is None:
                    failures.append(
                        {
                            "repetition": repetition,
                            "strategy": worker["strategy"],
                            "reason": "verified_worker_or_reference_unavailable",
                        }
                    )
                    continue
                source_row = worker["report"]["cases"][case_index]["runs"][repetition]
                row = deepcopy(
                    {k: v for k, v in source_row.items() if k != "comparison_snapshot"}
                )
                wall, cpu = perf_counter_ns(), process_time_ns()
                try:
                    if (
                        worker["report"]["cases"][case_index]["runtime_bindings"]
                        != reference_worker["report"]["cases"][case_index][
                            "runtime_bindings"
                        ]
                    ):
                        raise ValueError(
                            "worker runtime bindings differ from reference"
                        )
                    comparison = _compare_path_comparison_snapshots(
                        reference["comparison_snapshot"],
                        source_row["comparison_snapshot"],
                        absolute_tolerance=configuration["response_absolute_tolerance"],
                        relative_tolerance=configuration["response_relative_tolerance"],
                    )
                    # A structural mismatch can contain infinite diagnostic maxima;
                    # retain a failed comparison reason, never nonfinite timing JSON.
                    canonical_hash(comparison)
                except (ValueError, TypeError, KeyError, ArithmeticError):
                    comparison = {
                        "full_history_response_match": False,
                        "reason": "invalid_or_incompatible_full_history_snapshot",
                    }
                row["comparison_cpu_process_time_ns"] = process_time_ns() - cpu
                row["comparison_wall_ns"] = perf_counter_ns() - wall
                comparison_cpu += row["comparison_cpu_process_time_ns"]
                comparison_wall += row["comparison_wall_ns"]
                row["reference_comparison"] = comparison
                row["verified_end_to_end_wall_ns"] = (
                    row["execution_and_authority_verification_wall_ns"]
                    + row["comparison_wall_ns"]
                )
                row["verified_execution_and_comparison_cpu_process_time_ns"] = (
                    row["execution_and_authority_verification_cpu_process_time_ns"]
                    + row["comparison_cpu_process_time_ns"]
                )
                run_rows.append(row)
        complete = (
            not failures
            and len(run_rows) == configuration["repetitions"] * len(strategies)
            and all(
                row["reference_comparison"]["full_history_response_match"]
                for row in run_rows
            )
        )
        summaries = {}
        for strategy in strategies:
            rows = [row for row in run_rows if row["strategy"] == strategy]
            summaries[strategy] = {
                **_strategy_summary(rows),
                "summary_available": bool(rows),
                "execution_authority_and_parent_comparison_cpu_process_time_ns": _distribution(
                    [
                        row["verified_execution_and_comparison_cpu_process_time_ns"]
                        for row in rows
                    ]
                ),
            }
            if not rows:
                summaries[strategy]["all_full_history_matches_reference"] = False
                summaries[strategy]["all_full_j1_j5_recovery_passed"] = False
                summaries[strategy]["material_trial"]["coverage_complete"] = False
                summaries[strategy]["material_trial"]["unavailable_reasons"] = [
                    "no_verified_runs"
                ]
                summaries[strategy]["attempted_material_trial_wall_ns"] = (
                    _unmeasured_distribution("no_verified_runs")
                )
        cases.append(
            {
                "case_id": binding["case_id"],
                "binding": binding,
                "measurement_contract_pass": complete,
                "status": "ready" if complete else "blocked",
                "runs": run_rows,
                "unavailable_runs": failures,
                "summaries": summaries,
                "observed_comparisons": {
                    strategy: _observed_comparison(
                        summaries[_REFERENCE],
                        summaries[strategy],
                        timing_evidence_available=complete,
                    )
                    for strategy in strategies
                    if strategy != _REFERENCE
                },
            }
        )
    return cases, comparison_wall, comparison_cpu


def run_fiber_frame_strategy_process_suite(
    request_path: Path,
    *,
    source_revision: str,
    output_directory: Path,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Run each frozen strategy once across the full declared repeated-case batch.

    CPU observations describe this new execution. Historical training/evaluation
    is never rerun or silently included, and peak RSS values are never added or
    subtracted. Every failed worker/case stays in the requested denominator.
    """
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}|sha256:[0-9a-f]{64}", source_revision
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
    parent_wall, parent_cpu = perf_counter_ns(), process_time_ns()
    request = _freeze_inputs(Path(request_path).resolve(), output)
    strategies = [_REFERENCE, _DETERMINISTIC]
    if request["policy"] is not None:
        strategies.append(_LEARNED)
    declaration = {
        "schema_version": SCHEMA_VERSION,
        "source_revision": source_revision,
        "cases_in_execution_order": request["case_bindings"],
        "benchmark_configuration": request["benchmark_configuration"],
        "strategies_in_launch_order": strategies,
        "policy": request["policy"],
        "compiled_input_bindings": request["case_runtime_bindings"],
        "execution_scope": "one_fresh_worker_per_strategy_for_all_cases_warmups_and_repetitions",
    }
    workers = []
    worker_pids = set()
    frozen_identities = [request["original_request"], *request["inputs"]]
    for index, strategy in enumerate(strategies):
        directory = output / f"{index:02d}-{strategy}"
        if not _unchanged(frozen_identities):
            workers.append(
                {
                    "strategy": strategy,
                    "output_directory": str(directory),
                    "status": "blocked",
                    "manifest": {
                        "status": "not_run",
                        "reason": "frozen_inputs_changed",
                    },
                    "resources": None,
                    "resources_validated": False,
                    "report": None,
                    "validation_errors": ["frozen_inputs_changed_before_execution"],
                }
            )
            continue
        child_request = {
            "schema_version": "rc-fiber-strategy-process-request.v1",
            "strategy": strategy,
            "cases": request["case_requests"],
            "benchmark_configuration": request["benchmark_configuration"],
            "policy_file": request["policy_file"] if strategy == _LEARNED else None,
        }
        child_request_path = output / "inputs" / f"request-{index:03d}.json"
        process._write(child_request_path, process._bytes(child_request))
        expected_inputs = [_identity(child_request_path)] + [
            _identity(Path(row["model_file"])) for row in request["case_requests"]
        ]
        if strategy == _LEARNED:
            expected_inputs.append(_identity(Path(request["policy_file"])))
        expected_declaration = {
            "source_revision": source_revision,
            "strategy": strategy,
            "cases_in_execution_order": request["case_bindings"],
            "benchmark_configuration": request["benchmark_configuration"],
            "policy": request["policy"] if strategy == _LEARNED else None,
        }
        try:
            manifest = process.run_fiber_frame_strategy_process(
                child_request_path,
                source_revision=source_revision,
                output_directory=directory,
                timeout_seconds=timeout_seconds,
            )
        except (OSError, ValueError) as error:
            workers.append(
                {
                    "strategy": strategy,
                    "output_directory": str(directory),
                    "status": "blocked",
                    "manifest": {
                        "status": "error",
                        "exception_type": type(error).__name__,
                    },
                    "resources": None,
                    "resources_validated": False,
                    "report": None,
                    "validation_errors": ["worker_launch_or_collection_failed"],
                }
            )
            continue
        worker = _gather_worker(
            directory,
            manifest,
            strategy=strategy,
            source_revision=source_revision,
            expected_declaration=expected_declaration,
            expected_inputs=expected_inputs,
            expected_runtime_bindings=request["case_runtime_bindings"],
        )
        if manifest["worker_pid"] in worker_pids:
            worker["validation_errors"].append("worker_pid_reused_across_strategies")
            worker["status"] = "blocked"
            worker["resources_validated"] = False
        worker_pids.add(manifest["worker_pid"])
        if not _unchanged(expected_inputs):
            worker["validation_errors"].append("frozen_inputs_changed_during_execution")
            worker["status"] = "blocked"
            worker["resources_validated"] = False
        workers.append(worker)
    frozen_unchanged = _unchanged(frozen_identities)
    cases, comparison_wall, comparison_cpu = _compare_workers(
        workers, request["case_bindings"], request["benchmark_configuration"]
    )
    passed = (
        frozen_unchanged
        and all(row["status"] == "ready" for row in workers)
        and all(row["measurement_contract_pass"] for row in cases)
    )
    resources_complete = all(row["resources_validated"] for row in workers)
    cfg = request["benchmark_configuration"]
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if passed else "blocked",
        "measurement_contract_pass": passed,
        "declaration": declaration,
        "input_snapshots": {
            "original_request": request["original_request"],
            "frozen_inputs": request["inputs"],
        },
        "suite_identity_hash": canonical_hash(declaration),
        "workers": workers,
        "cases": cases,
        "coverage": {
            "declared_case_count": len(cases),
            "declared_strategy_count": len(strategies),
            "expected_measured_run_count": len(cases)
            * len(strategies)
            * cfg["repetitions"],
            "expected_warmup_run_count": len(cases)
            * len(strategies)
            * cfg["warmup_repetitions"],
            "expected_reference_episode_count": len(cases) * cfg["repetitions"],
            "verified_measured_run_count": sum(
                row["reference_comparison"]["full_history_response_match"]
                for case in cases
                for row in case["runs"]
            ),
            "verified_case_count": sum(
                case["measurement_contract_pass"] for case in cases
            ),
            "ready_worker_count": sum(row["status"] == "ready" for row in workers),
            "frozen_inputs_unchanged": frozen_unchanged,
        },
        "resource_accounting": {
            "all_worker_measurements_validated": resources_complete,
            "observed_worker_resource_count": sum(
                row["resources_validated"] for row in workers
            ),
            "observed_worker_cpu_process_time_ns": sum(
                row["resources"]["cpu_process_time_ns"]
                for row in workers
                if row["resources_validated"]
            )
            if any(row["resources_validated"] for row in workers)
            else None,
            "observed_worker_cpu_scope": "validated_completed_worker_lifetimes_including_physically_blocked_attempts;partial_when_workers_are_missing",
            "worker_cpu_process_time_ns": (
                sum(row["resources"]["cpu_process_time_ns"] for row in workers)
                if resources_complete
                else None
            ),
            "worker_workload_cpu_process_time_ns": (
                sum(row["resources"]["workload_cpu_process_time_ns"] for row in workers)
                if resources_complete
                else None
            ),
            "parent_comparison_count": sum(len(case["runs"]) for case in cases),
            "parent_comparison_wall_ns": comparison_wall
            if any(case["runs"] for case in cases)
            else None,
            "parent_comparison_cpu_process_time_ns": comparison_cpu
            if any(case["runs"] for case in cases)
            else None,
            "parent_orchestration_cpu_process_time_ns": process_time_ns() - parent_cpu,
            "parent_observed_wall_ns": perf_counter_ns() - parent_wall,
            "parent_scope": "input_snapshot_launch_wait_artifact_validation_and_comparison_before_combined_report_encoding",
            "comparison_cpu_is_subset_of_parent_cpu": True,
            "worker_cpu_scope": "fresh_worker_lifetime_through_strategy_report_persistence_excluding_resource_sidecar_emission",
            "per_strategy_peak_memory_scope": process.STRATEGY_PEAK_SCOPE,
            "combined_peak_memory_bytes": None,
            "combined_peak_memory_reason": "independent_process_peaks_are_not_additive_or_subtractable",
            "training_execution_count": 0,
            "data_collection_execution_count": 0,
            "historical_training_cost_ns": None,
            "historical_training_cost_reason": "frozen_policy_input_only_upfront_study_costs_require_separate_bound_artifacts",
            "additional_experiment_not_historical_suite_relabeling": True,
            "physical_disk_io_measured": False,
            "gpu_time_ns": None,
        },
        "claims": {
            "full_history_cross_strategy_comparison_passed": passed,
            "selected_paths_verified_in_own_workers": passed,
            "per_strategy_process_resources_available": resources_complete,
            "reference_peak_includes_extra_baseline_episode_checks": True,
            "equal_scope_peak_memory_advantage_claimed": False,
            "independent_validation": False,
            "source_revision_is_attestation": False,
            "generalized_speedup_claimed": False,
            "construction_savings_claimed": False,
        },
    }
    report["report_hash"] = canonical_hash(report)
    process._write(output / "report.json", process._bytes(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    args = parser.parse_args(argv)
    try:
        report = run_fiber_frame_strategy_process_suite(
            args.request,
            source_revision=args.source_revision,
            output_directory=args.output_directory,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, ValueError) as error:
        parser.error(type(error).__name__)
    print(
        json.dumps({"status": report["status"], "report_hash": report["report_hash"]})
    )
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
