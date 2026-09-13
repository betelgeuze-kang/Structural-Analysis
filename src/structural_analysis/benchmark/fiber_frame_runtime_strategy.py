"""One frozen strategy batch, verified locally before parent-side comparison.

The fresh-process collector owns imports, input/output and whole-worker resource
measurement.  These nested wall/CPU intervals describe compilation, executions,
selected-path replay and the reference-only solver-episode replay separately.
No phase peak memory or cross-strategy response authority is claimed here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import asdict
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.benchmark import fiber_frame_runtime as runtime
from structural_analysis.benchmark.fiber_frame_runtime_suite import (
    FiberFrameRuntimeCase,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIBER_FRAME_RUNTIME_STRATEGY_SCHEMA_VERSION = (
    "public-rc-fiber-frame-runtime-strategy.v1"
)
_STRATEGIES = (
    runtime.FIBER_FRAME_REFERENCE_STRATEGY,
    runtime.FIBER_FRAME_NON_AI_STRATEGY,
    runtime.FIBER_FRAME_AI_STRATEGY,
)
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})\Z")


def _failure(exc: Exception) -> dict[str, str]:
    return {"exception_type": type(exc).__name__, "detail": str(exc)[:1000]}


def _observe(
    operation: Callable[[], Any],
) -> tuple[Any, dict[str, str] | None, int, int]:
    wall_started = runtime._tick(perf_counter_ns)
    cpu_started = runtime._tick(process_time_ns)
    result = None
    failure = None
    try:
        result = operation()
    except Exception as exc:
        failure = _failure(exc)
    cpu = runtime._elapsed(process_time_ns, cpu_started)
    wall = runtime._elapsed(perf_counter_ns, wall_started)
    return result, failure, wall, cpu


def _not_verified(reason: str) -> dict[str, Any]:
    return {"status": "not_run", "contract_pass": False, "reason_code": reason}


def _empty_run(strategy: str, index: int, *, warmup: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "warmup_index" if warmup else "repetition": index,
        "strategy": strategy,
        "status": "not_run",
        "contract_pass": False,
        "failure": None,
        "wall_ns": None,
        "execution_call_wall_ns": None,
        "execution_cpu_process_time_ns": None,
        "path_hash": None,
        "load_step_count": None,
        "committed_step_count": None,
        "attempted_newton_iteration_count": None,
        "attempted_line_search_evaluation_count": None,
        "comparison_snapshot": None,
        "authority_verification": _not_verified(
            "warmup_execution_only" if warmup else "execution_not_run"
        ),
    }
    if not warmup:
        row.update(
            execution_order_index=0,
            terminal_checkpoint_state_hash=None,
            newton_iteration_count=None,
            selected_solve_wall_ns=None,
            attempted_solve_wall_ns=None,
            verification_wall_ns=None,
            verification_cpu_process_time_ns=None,
            execution_and_authority_verification_wall_ns=None,
            execution_and_authority_verification_cpu_process_time_ns=None,
            inference_wall_ns=None,
            guard_wall_ns=None,
            seeded_attempt_wall_ns=None,
            baseline_recovery_wall_ns=None,
            guard_assembly_call_count=None,
            selected_stateful_runtime=None,
            attempted_stateful_runtime=None,
            selected_newton_runtime=None,
            attempted_newton_runtime=None,
            steps=None,
        )
    return row


def _execution_fields(execution: Any) -> dict[str, Any]:
    return {
        "status": execution.path.status,
        "contract_pass": execution.path.contract_pass,
        "path_hash": canonical_hash(execution.path.to_dict()),
        "load_step_count": len(execution.path.steps),
        "committed_step_count": sum(step.committed for step in execution.path.steps),
        "wall_ns": execution.wall_ns,
        "attempted_newton_iteration_count": execution.attempted_newton_iteration_count,
        "attempted_line_search_evaluation_count": (
            execution.attempted_line_search_evaluation_count
        ),
    }


def _run_locally_verified(
    row: dict[str, Any],
    *,
    model: Any,
    compiled: Any,
    config: Any,
    solver_config: Any,
    measure: runtime.FiberFrameRuntimeBenchmarkConfig,
    ai_policy: runtime.FiberFrameWarmStartPolicy | None,
    warmup: bool,
) -> Any:
    outer_wall_started = runtime._tick(perf_counter_ns)
    outer_cpu_started = runtime._tick(process_time_ns)
    try:
        execution, failure, wall, cpu = _observe(
            lambda: runtime._run_strategy(
                row["strategy"],
                compiled.problem,
                config.target_load_factors,
                solver_config,
                measure,
                ai_policy=ai_policy,
                clock_ns=perf_counter_ns,
            )
        )
        row.update(
            execution_call_wall_ns=wall,
            execution_cpu_process_time_ns=cpu,
            wall_ns=wall,
            failure=failure,
        )
        if failure is not None:
            row["status"] = "error"
            row["authority_verification"] = _not_verified("execution_failed")
            return None
        try:
            row.update(_execution_fields(execution))
            if warmup:
                return None
            row.update(
                terminal_checkpoint_state_hash=execution.path.final_checkpoint.state_hash,
                newton_iteration_count=sum(
                    len(step.trial_solution.convergence_history)
                    for step in execution.path.steps
                ),
                selected_solve_wall_ns=execution.selected_solve_wall_ns,
                attempted_solve_wall_ns=execution.attempted_solve_wall_ns,
                inference_wall_ns=execution.inference_wall_ns,
                guard_wall_ns=execution.guard_wall_ns,
                seeded_attempt_wall_ns=execution.seeded_attempt_wall_ns,
                baseline_recovery_wall_ns=execution.baseline_recovery_wall_ns,
                guard_assembly_call_count=execution.guard_assembly_call_count,
                selected_stateful_runtime=deepcopy(
                    dict(execution.selected_stateful_runtime)
                ),
                attempted_stateful_runtime=deepcopy(
                    dict(execution.attempted_stateful_runtime)
                ),
                selected_newton_runtime=dict(execution.selected_newton_runtime),
                attempted_newton_runtime=dict(execution.attempted_newton_runtime),
                steps=[dict(step) for step in execution.step_rows],
                comparison_snapshot=runtime._path_comparison_snapshot(execution.path),
            )
            verification, failure, wall, cpu = _observe(
                lambda: runtime._verify_selected_path(model, compiled, execution.path)
            )
            row.update(
                verification_wall_ns=wall,
                verification_cpu_process_time_ns=cpu,
            )
            if failure is not None:
                row["failure"] = failure
                row["authority_verification"] = _not_verified(
                    "authority_verification_failed"
                )
                return None
            proof, source = verification
            row["authority_verification"] = deepcopy(proof)
            return source
        except Exception as exc:
            row["failure"] = _failure(exc)
            row["status"] = "error"
            return None

    finally:
        outer_cpu = runtime._elapsed(process_time_ns, outer_cpu_started)
        outer_wall = runtime._elapsed(perf_counter_ns, outer_wall_started)
        if not warmup:
            row["execution_and_authority_verification_wall_ns"] = outer_wall
            row["execution_and_authority_verification_cpu_process_time_ns"] = outer_cpu


def benchmark_public_rc_fiber_frame_runtime_strategy(
    cases: Sequence[FiberFrameRuntimeCase],
    *,
    strategy: str,
    source_revision: str,
    benchmark_config: runtime.FiberFrameRuntimeBenchmarkConfig | None = None,
    ai_policy: runtime.FiberFrameWarmStartPolicy | None = None,
) -> dict[str, Any]:
    """Execute one strategy for every declared case/warmup/repetition.

    A ready report requires complete local selected-path verification and, for
    the reference strategy, a full baseline episode replay per measured run.
    Cross-worker response equality is deliberately still unavailable.  Every
    planned row remains in the report if an earlier operation fails.
    """

    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise runtime.FiberFrameRuntimeBenchmarkError(
            "cases must be a non-empty sequence"
        )
    cases = tuple(cases)
    if any(type(case) is not FiberFrameRuntimeCase for case in cases):
        raise runtime.FiberFrameRuntimeBenchmarkError(
            "every case must be a FiberFrameRuntimeCase"
        )
    if len({case.case_id for case in cases}) != len(cases):
        raise runtime.FiberFrameRuntimeBenchmarkError("case_id values must be unique")
    if type(strategy) is not str or strategy not in _STRATEGIES:
        raise runtime.FiberFrameRuntimeBenchmarkError("strategy is invalid")
    if type(source_revision) is not str or not _REVISION.fullmatch(source_revision):
        raise runtime.FiberFrameRuntimeBenchmarkError("source_revision is invalid")
    if (
        benchmark_config is not None
        and type(benchmark_config) is not runtime.FiberFrameRuntimeBenchmarkConfig
    ):
        raise runtime.FiberFrameRuntimeBenchmarkError("benchmark_config is invalid")
    measure = benchmark_config or runtime.FiberFrameRuntimeBenchmarkConfig()
    use_ai = strategy == runtime.FIBER_FRAME_AI_STRATEGY
    if not use_ai and ai_policy is not None:
        raise runtime.FiberFrameRuntimeBenchmarkError(
            "ai_policy requires the AI strategy"
        )
    policy = runtime._policy_identity(ai_policy) if use_ai else None

    snapshots = []
    snapshot_failures = []
    declarations = []
    # Finish every detached input snapshot before calling any compiler or policy.
    for case in cases:
        snapshot = None
        failure = None
        checksum = None
        try:
            snapshot = case.model.detached_analysis_snapshot()
            checksum = snapshot.canonical_model_checksum
        except Exception as exc:
            failure = _failure(exc)
        snapshots.append(snapshot)
        snapshot_failures.append(failure)
        declarations.append(
            {
                "case_id": case.case_id,
                "canonical_model_checksum": checksum,
                "model_identity_available": checksum is not None,
                "input_checksum": case.model.input_checksum
                if type(case.model.input_checksum) is str
                else None,
                "public_solver_configuration": asdict(case.config),
                "target_load_factors": list(case.config.target_load_factors),
            }
        )
    declaration = {
        "source_revision": source_revision,
        "strategy": strategy,
        "cases_in_execution_order": declarations,
        "benchmark_configuration": measure.to_dict(),
        "policy": policy,
    }
    rows = []
    policy_unchanged = True
    for case, snapshot, binding, snapshot_failure in zip(
        cases, snapshots, declarations, snapshot_failures, strict=True
    ):
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "binding": deepcopy(binding),
            "status": "error",
            "measurement_contract_pass": False,
            "failure": snapshot_failure,
            "compile_wall_ns": None,
            "compile_cpu_process_time_ns": None,
            "runtime_bindings": None,
            "unsupported_features": [],
            "warnings": [],
            "warmups": [
                _empty_run(strategy, i, warmup=True)
                for i in range(measure.warmup_repetitions)
            ],
            "runs": [
                _empty_run(strategy, i, warmup=False)
                for i in range(measure.repetitions)
            ],
            "reference_solver_episode_verification": {
                "required": strategy == runtime.FIBER_FRAME_REFERENCE_STRATEGY,
                "runs": [],
            },
        }
        rows.append(row)
        if snapshot is None or not policy_unchanged:
            if snapshot is not None:
                row["failure"] = {
                    "exception_type": "PolicyIdentityChanged",
                    "detail": "earlier execution changed the declared policy identity",
                }
            continue
        compilation, failure, wall, cpu = _observe(
            lambda: runtime.public_api._compile(snapshot)
        )
        row.update(
            compile_wall_ns=wall, compile_cpu_process_time_ns=cpu, failure=failure
        )
        if failure is not None:
            continue
        try:
            compiled, unsupported, warnings = compilation
            row["unsupported_features"] = deepcopy(unsupported)
            row["warnings"] = deepcopy(warnings)
            if compiled is None:
                row["status"] = "unsupported"
                row["failure"] = {
                    "exception_type": "UnsupportedPublicProfile",
                    "detail": "model is outside the bounded public RC fiber profile",
                }
                continue
            solver_config = runtime.NewtonRaphsonConfig(
                residual_tolerance=case.config.residual_tolerance,
                increment_tolerance=case.config.increment_tolerance_m,
                max_iterations=case.config.maximum_iterations,
                terminal_polishing=measure.terminal_polishing,
            )
            problem = compiled.problem
            row["runtime_bindings"] = {
                "problem_contract_hash": problem.contract_hash,
                "compiler_profile": runtime.public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
                "solver_id": runtime.public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
                "coordinate_binding_hash": canonical_hash(
                    {
                        "problem_contract_hash": problem.contract_hash,
                        "free_global_dofs": list(problem.free_global_dofs),
                        "physical_coordinate_scale": problem.physical_coordinate_scale.tolist(),
                        "coordinate_profile": "generalized-free-solver-coordinates-m.v1",
                    }
                ),
                "solver_config_hash": canonical_hash(
                    runtime._solver_config_payload(solver_config)
                ),
                "load_history_hash": canonical_hash(
                    list(case.config.target_load_factors)
                ),
            }
            for warmup, run_rows in ((True, row["warmups"]), (False, row["runs"])):
                for run in run_rows:
                    if not policy_unchanged:
                        break
                    source = _run_locally_verified(
                        run,
                        model=snapshot,
                        compiled=compiled,
                        config=case.config,
                        solver_config=solver_config,
                        measure=measure,
                        ai_policy=ai_policy,
                        warmup=warmup,
                    )
                    if use_ai:
                        try:
                            policy_unchanged = (
                                runtime._policy_identity(ai_policy) == policy
                            )
                        except Exception:
                            policy_unchanged = False
                        if not policy_unchanged:
                            row["failure"] = {
                                "exception_type": "PolicyIdentityChanged",
                                "detail": "execution changed the declared policy identity",
                            }
                    if (
                        not warmup
                        and strategy == runtime.FIBER_FRAME_REFERENCE_STRATEGY
                    ):
                        proof, failure, wall, cpu = _observe(
                            lambda: runtime._verify_reference_solver_episode(source)
                        )
                        episode = {
                            "repetition": run["repetition"],
                            "wall_ns": wall,
                            "cpu_process_time_ns": cpu,
                            "failure": failure,
                            **(
                                _not_verified("reference_episode_verification_failed")
                                if failure is not None
                                else proof
                            ),
                        }
                        row["reference_solver_episode_verification"]["runs"].append(
                            episode
                        )
            warmups_pass = all(_execution_pass(run) for run in row["warmups"])
            runs_pass = all(
                _execution_pass(run) and _proof_pass(run["authority_verification"])
                for run in row["runs"]
            )
            episodes = row["reference_solver_episode_verification"]["runs"]
            episodes_pass = strategy != runtime.FIBER_FRAME_REFERENCE_STRATEGY or (
                len(episodes) == measure.repetitions
                and all(
                    _proof_pass(proof) and proof["failure"] is None
                    for proof in episodes
                )
                and len({proof.get("solver_episode_hash") for proof in episodes}) == 1
                and len(
                    {proof.get("solver_episode_adapter_hash") for proof in episodes}
                )
                == 1
            )
            passed = bool(
                warmups_pass and runs_pass and episodes_pass and policy_unchanged
            )
            row["measurement_contract_pass"] = passed
            row["status"] = "ready" if passed else "blocked"
        except Exception as exc:
            row["failure"] = _failure(exc)
            row["status"] = "error"

    coverage = {
        "declared_case_count": len(cases),
        "ready_case_count": sum(row["status"] == "ready" for row in rows),
        "blocked_case_count": sum(row["status"] == "blocked" for row in rows),
        "unsupported_case_count": sum(row["status"] == "unsupported" for row in rows),
        "error_case_count": sum(row["status"] == "error" for row in rows),
        "expected_warmup_count": len(cases) * measure.warmup_repetitions,
        "attempted_warmup_count": sum(
            run["execution_call_wall_ns"] is not None
            for row in rows
            for run in row["warmups"]
        ),
        "ready_warmup_count": sum(
            _execution_pass(run) for row in rows for run in row["warmups"]
        ),
        "expected_measured_run_count": len(cases) * measure.repetitions,
        "attempted_measured_run_count": sum(
            run["execution_call_wall_ns"] is not None
            for row in rows
            for run in row["runs"]
        ),
        "selected_path_authority_pass_count": sum(
            _execution_pass(run) and _proof_pass(run["authority_verification"])
            for row in rows
            for run in row["runs"]
        ),
        "expected_reference_episode_verification_count": len(cases)
        * measure.repetitions
        if strategy == runtime.FIBER_FRAME_REFERENCE_STRATEGY
        else 0,
        "attempted_reference_episode_verification_count": sum(
            len(row["reference_solver_episode_verification"]["runs"]) for row in rows
        ),
        "reference_episode_verification_pass_count": sum(
            _proof_pass(proof) and proof["failure"] is None
            for row in rows
            for proof in row["reference_solver_episode_verification"]["runs"]
        ),
    }
    passed = policy_unchanged and all(row["measurement_contract_pass"] for row in rows)
    payload = {
        "schema_version": FIBER_FRAME_RUNTIME_STRATEGY_SCHEMA_VERSION,
        "status": "ready" if passed else "blocked",
        "measurement_contract_pass": bool(passed),
        "strategy_identity_hash": canonical_hash(declaration),
        "declaration": declaration,
        "cases": rows,
        "coverage": coverage,
        "reference_comparison": {
            "status": "not_run",
            "full_history_response_match": None,
            "scope": "parent_cross_strategy_comparison_required",
        },
        "measurement_scope": {
            "clock": "time.perf_counter_ns",
            "cpu_clock": "time.process_time_ns",
            "local_contract": "selected_path_full_j1_j5_recovery_and_reference_only_solver_episode_replay",
            "warmups": "execution_only_no_authority_replay",
            "reference_episode": "separate_nested_wall_and_cpu_scope_in_reference_worker_peak",
            "comparison_snapshot": "complete_checkpoint_and_trial_fields_used_by_legacy_path_comparison",
            "comparison_snapshot_preparation_included_in_verified_run_interval": True,
            "cross_strategy_comparison_included": False,
            "per_phase_peak_memory_bytes": None,
            "per_phase_peak_memory_reason": "phases_share_one_strategy_worker",
            "training_executed": False,
            "worker_imports_input_output_resources": "fresh_process_collector_sidecar",
        },
        "policy_execution_contract": {
            "same_instance_reused_across_cases_warmups_repetitions": use_ai,
            "policy_identity_unchanged": policy_unchanged,
            "policy_reset_between_runs": False,
            "deterministic_inference_asserted": False,
            "training_executed": False,
        },
    }
    payload["report_hash"] = canonical_hash(payload)
    return payload


def _proof_pass(proof: Any) -> bool:
    return (
        type(proof) is dict
        and proof.get("status") == "ready"
        and proof.get("contract_pass") is True
    )


def _execution_pass(row: dict[str, Any]) -> bool:
    return bool(
        row["status"] == "ready"
        and row["contract_pass"] is True
        and row["failure"] is None
        and row["load_step_count"] is not None
        and row["committed_step_count"] == row["load_step_count"]
    )
