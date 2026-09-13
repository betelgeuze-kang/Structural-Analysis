"""Declared-case runtime comparisons for the bounded public RC fiber profile.

Every requested case remains in the denominator, including unsupported inputs,
nonconvergence and exceptions.  Each case compares strategies on one unchanged
physical model; cases are not interchangeable samples of a speedup claim.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from time import perf_counter_ns
from typing import Any

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE,
    FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE,
    FiberFrameRuntimeBenchmarkConfig,
    FiberFrameRuntimeBenchmarkError,
    FiberFrameRuntimeBenchmarkResult,
    FiberFrameWarmStartPolicy,
    benchmark_public_rc_fiber_frame_warm_starts,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel


FIBER_FRAME_RUNTIME_SUITE_SCHEMA_VERSION = "public-rc-fiber-frame-runtime-suite.v1"
_STABLE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})\Z")
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


class FiberFrameRuntimeSuiteError(ValueError):
    """Invalid suite declaration or injected execution contract."""


@dataclass(frozen=True)
class FiberFrameRuntimeCase:
    """One declared physical model and its fixed public solver configuration."""

    case_id: str
    model: CanonicalModel
    config: PublicRCFiberFrameConfig = field(default_factory=PublicRCFiberFrameConfig)

    def __post_init__(self) -> None:
        if type(self.case_id) is not str or not _STABLE_ID.fullmatch(self.case_id):
            raise FiberFrameRuntimeSuiteError("case_id must be a stable identifier")
        if type(self.model) is not CanonicalModel:
            raise FiberFrameRuntimeSuiteError("model must be a CanonicalModel")
        if type(self.config) is not PublicRCFiberFrameConfig:
            raise FiberFrameRuntimeSuiteError(
                "config must be a PublicRCFiberFrameConfig"
            )


@dataclass(frozen=True)
class FiberFrameRuntimeSuiteResult:
    """Stable suite declaration and volatile reports of all attempted cases."""

    status: str
    measurement_contract_pass: bool
    suite_identity_hash: str
    report_hash: str
    _payload: Mapping[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self._payload))


def benchmark_public_rc_fiber_frame_runtime_suite(
    cases: Sequence[FiberFrameRuntimeCase],
    *,
    source_revision: str,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig | None = None,
    ai_opt_in: bool = False,
    ai_policy: FiberFrameWarmStartPolicy | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    runner: Callable[..., FiberFrameRuntimeBenchmarkResult] | None = None,
) -> FiberFrameRuntimeSuiteResult:
    """Run a predeclared suite without dropping unsuccessful cases.

    ``runner`` and ``clock_ns`` support bounded contract tests.  Either injection
    disqualifies the suite from local timing evidence, even if a supplied report
    claims otherwise.  One caller-owned opt-in policy instance is reused across
    cases, warmups and repetitions; no reset or deterministic inference is implied.
    """

    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise FiberFrameRuntimeSuiteError("cases must be a non-empty sequence")
    cases = tuple(cases)
    if any(type(case) is not FiberFrameRuntimeCase for case in cases):
        raise FiberFrameRuntimeSuiteError("every case must be a FiberFrameRuntimeCase")
    if len({case.case_id for case in cases}) != len(cases):
        raise FiberFrameRuntimeSuiteError("case_id values must be unique")
    if type(source_revision) is not str or not _REVISION.fullmatch(source_revision):
        raise FiberFrameRuntimeSuiteError(
            "source_revision must be a lowercase Git ID or sha256 hash"
        )
    if (
        benchmark_config is not None
        and type(benchmark_config) is not FiberFrameRuntimeBenchmarkConfig
    ):
        raise FiberFrameRuntimeSuiteError(
            "benchmark_config must be a FiberFrameRuntimeBenchmarkConfig"
        )
    if type(ai_opt_in) is not bool:
        raise FiberFrameRuntimeSuiteError("ai_opt_in must be a boolean")
    if not callable(clock_ns) or (runner is not None and not callable(runner)):
        raise FiberFrameRuntimeSuiteError("clock_ns and runner must be callable")
    measure = benchmark_config or FiberFrameRuntimeBenchmarkConfig()
    policy = _policy_identity(ai_policy) if ai_opt_in else None
    strategies = [FIBER_FRAME_REFERENCE_STRATEGY, FIBER_FRAME_NON_AI_STRATEGY]
    if ai_opt_in:
        strategies.append(FIBER_FRAME_AI_STRATEGY)
    measurement_profile = (
        FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE
        if clock_ns is perf_counter_ns
        else FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE
    )
    execute = benchmark_public_rc_fiber_frame_warm_starts if runner is None else runner

    # Snapshot all inputs before invoking any runner or caller-owned policy.
    snapshots: list[CanonicalModel | None] = []
    snapshot_failures: list[dict[str, str] | None] = []
    declarations = []
    for case in cases:
        snapshot = None
        failure = None
        checksum = None
        try:
            snapshot = case.model.detached_analysis_snapshot()
            checksum = snapshot.canonical_model_checksum
        except Exception as exc:
            failure = {"exception_type": type(exc).__name__, "detail": str(exc)}
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
        "schema_version": FIBER_FRAME_RUNTIME_SUITE_SCHEMA_VERSION,
        "source_revision": source_revision,
        "cases_in_execution_order": declarations,
        "benchmark_configuration": measure.to_dict(),
        "strategies": strategies,
        "ai_opt_in": ai_opt_in,
        "policy": policy,
        "measurement_profile": measurement_profile,
        "runner_profile": "public_runtime_benchmark"
        if runner is None
        else "injected_test_runner",
    }
    suite_identity_hash = canonical_hash(declaration)
    rows = []
    for case, snapshot, binding, snapshot_failure in zip(
        cases, snapshots, declarations, snapshot_failures, strict=True
    ):
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "binding": deepcopy(binding),
            "status": "error",
            "measurement_contract_pass": False,
            "failure": None,
            "benchmark_report": None,
            "coverage": _empty_coverage(measure.repetitions, len(strategies)),
        }
        if snapshot_failure is not None:
            row["failure"] = snapshot_failure
            rows.append(row)
            continue
        try:
            result = execute(
                snapshot,
                case.config,
                benchmark_config=measure,
                ai_opt_in=ai_opt_in,
                ai_policy=ai_policy,
                source_revision=source_revision,
                clock_ns=clock_ns,
            )
            if type(result) is not FiberFrameRuntimeBenchmarkResult:
                raise FiberFrameRuntimeSuiteError(
                    "runner must return FiberFrameRuntimeBenchmarkResult"
                )
            payload = result.to_dict()
            # Require a finite canonical report before retaining any timing values.
            report_hash = canonical_hash(
                {key: value for key, value in payload.items() if key != "report_hash"}
            )
            row["benchmark_report"] = payload
            coverage = _coverage(
                payload,
                binding,
                source_revision,
                measure,
                strategies,
                ai_opt_in,
                policy,
                measurement_profile,
            )
            if (
                payload.get("report_hash") != report_hash
                or result.report_hash != report_hash
            ):
                coverage["validation_errors"].append("report_hash_mismatch")
                coverage["fully_verified_run_count"] = 0
                coverage["verified_reference_episode_count"] = 0
                coverage["verified_runs_by_strategy"] = {
                    strategy: 0 for strategy in strategies
                }
            if result.measurement_contract_pass is not True or result.status != "ready":
                coverage["validation_errors"].append("result_contract_not_ready")
            row["coverage"] = coverage
            passed = not coverage["validation_errors"]
            row["status"] = "ready" if passed else "blocked"
            row["measurement_contract_pass"] = passed
        except Exception as exc:
            unsupported = isinstance(exc, FiberFrameRuntimeBenchmarkError) and str(
                exc
            ).startswith("model is outside the bounded public RC fiber profile:")
            row["status"] = "unsupported" if unsupported else "error"
            row["failure"] = {"exception_type": type(exc).__name__, "detail": str(exc)}
        rows.append(row)

    coverage = _aggregate_coverage(rows, strategies)
    passed = coverage["verified_case_count"] == len(cases)
    eligible = bool(
        passed
        and runner is None
        and clock_ns is perf_counter_ns
        and all(
            row["benchmark_report"]
            .get("measurement_eligibility", {})
            .get("local_timing_evidence_eligible")
            is True
            for row in rows
        )
    )
    payload = {
        "schema_version": FIBER_FRAME_RUNTIME_SUITE_SCHEMA_VERSION,
        "status": "ready" if passed else "blocked",
        "measurement_contract_pass": passed,
        "suite_identity_hash": suite_identity_hash,
        "declaration": declaration,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases": rows,
        "coverage": coverage,
        "measurement_eligibility": {
            "local_timing_evidence_eligible": eligible,
            "injected_runner_for_contract_testing_only": runner is not None,
            "injected_clock_for_contract_testing_only": clock_ns is not perf_counter_ns,
        },
        "policy_execution_contract": {
            "same_caller_owned_instance_reused_across_cases": ai_opt_in,
            "automatic_state_reset_between_cases": False,
            "deterministic_inference_asserted": False,
        },
        "comparison_scope": "within_each_declared_case_only",
        "suite_speedup_ratio": None,
        "suite_speedup_reason": "heterogeneous_cases_and_failures_are_not_pooled_into_a_speedup_claim",
        "claims": {
            "all_declared_cases_retained": len(rows) == len(cases),
            "all_declared_cases_verified": passed,
            "observed_local_timing_available_for_complete_suite": eligible,
            "generalized_speedup_claimed": False,
            "positive_speedup_required_for_contract": False,
            "physical_performance_improvement_claimed": False,
            "construction_savings_claimed": False,
        },
    }
    payload["report_hash"] = canonical_hash(payload)
    return FiberFrameRuntimeSuiteResult(
        status=payload["status"],
        measurement_contract_pass=passed,
        suite_identity_hash=suite_identity_hash,
        report_hash=payload["report_hash"],
        _payload=payload,
    )


def _empty_coverage(repetitions: int, strategy_count: int) -> dict[str, Any]:
    return {
        "expected_run_count": repetitions * strategy_count,
        "reported_run_count": 0,
        "fully_verified_run_count": 0,
        "expected_reference_episode_count": repetitions,
        "verified_reference_episode_count": 0,
        "verified_runs_by_strategy": {},
        "validation_errors": [],
    }


def _coverage(
    payload: Mapping[str, Any],
    binding: Mapping[str, Any],
    revision: str,
    measure: FiberFrameRuntimeBenchmarkConfig,
    strategies: list[str],
    ai_opt_in: bool,
    policy: Mapping[str, str] | None,
    measurement_profile: str,
) -> dict[str, Any]:
    coverage = _empty_coverage(measure.repetitions, len(strategies))
    errors = coverage["validation_errors"]
    bindings = payload.get("bindings", {})
    configuration = payload.get("configuration", {})
    solver = configuration.get("public_solver", {})
    expected_solver = binding["public_solver_configuration"]
    input_match = (
        bindings.get("canonical_model_checksum") == binding["canonical_model_checksum"]
        and bindings.get("input_checksum") == binding["input_checksum"]
        and bindings.get("source_revision") == revision
        and bindings.get("load_history_hash")
        == canonical_hash(binding["target_load_factors"])
        and solver.get("load_factors") == binding["target_load_factors"]
        and solver.get("residual_tolerance") == expected_solver["residual_tolerance"]
        and solver.get("increment_tolerance")
        == expected_solver["increment_tolerance_m"]
        and solver.get("max_iterations") == expected_solver["maximum_iterations"]
        and configuration.get("benchmark") == measure.to_dict()
        and configuration.get("ai_opt_in") is ai_opt_in
        and configuration.get("policy") == policy
        and payload.get("measurement_profile") == measurement_profile
    )
    if not input_match:
        errors.append("declared_input_binding_mismatch")
    if (
        payload.get("measurement_contract_pass") is not True
        or payload.get("status") != "ready"
    ):
        errors.append("benchmark_contract_not_ready")
    runs = payload.get("runs", [])
    expected_pairs = {
        (repetition, strategy)
        for repetition in range(measure.repetitions)
        for strategy in strategies
    }
    pairs = Counter((run.get("repetition"), run.get("strategy")) for run in runs)
    coverage["reported_run_count"] = len(runs)
    if set(pairs) != expected_pairs or any(count != 1 for count in pairs.values()):
        errors.append("missing_duplicate_or_unexpected_strategy_run")
    verified = Counter()
    for run in runs:
        pair = (run.get("repetition"), run.get("strategy"))
        if (
            input_match
            and pair in expected_pairs
            and pairs[pair] == 1
            and type(run.get("repetition")) is int
            and run.get("status") == "ready"
            and run.get("contract_pass") is True
            and run.get("committed_step_count") == expected_solver["load_steps"]
            and run.get("load_step_count") == expected_solver["load_steps"]
            and run.get("authority_verification", {}).get("contract_pass") is True
            and run.get("authority_verification", {}).get("reason_code")
            == "full_j1_j5_recovery_passed"
            and run.get("reference_comparison", {}).get("full_history_response_match")
            is True
        ):
            verified[run["strategy"]] += 1
    coverage["verified_runs_by_strategy"] = {
        strategy: verified[strategy] for strategy in strategies
    }
    coverage["fully_verified_run_count"] = sum(verified.values())
    if coverage["fully_verified_run_count"] != coverage["expected_run_count"]:
        errors.append("full_history_or_authority_verification_incomplete")
    episodes = payload.get("reference_solver_episode_verification", {}).get("runs", [])
    episode_pairs = Counter(episode.get("repetition") for episode in episodes)
    coverage["verified_reference_episode_count"] = sum(
        int(
            input_match
            and type(episode.get("repetition")) is int
            and episode["repetition"] in range(measure.repetitions)
            and episode_pairs[episode["repetition"]] == 1
            and episode.get("contract_pass") is True
            and episode.get("status") == "ready"
        )
        for episode in episodes
    )
    if (
        len(episodes) != measure.repetitions
        or coverage["verified_reference_episode_count"] != measure.repetitions
    ):
        errors.append("reference_episode_verification_incomplete")
    return coverage


def _aggregate_coverage(
    rows: list[dict[str, Any]], strategies: list[str]
) -> dict[str, Any]:
    return {
        "declared_case_count": len(rows),
        "attempted_case_count": len(rows),
        "verified_case_count": sum(row["measurement_contract_pass"] for row in rows),
        "status_counts": {
            status: sum(row["status"] == status for row in rows)
            for status in ("ready", "blocked", "unsupported", "error")
        },
        **{
            field_name: sum(row["coverage"][field_name] for row in rows)
            for field_name in (
                "expected_run_count",
                "reported_run_count",
                "fully_verified_run_count",
                "expected_reference_episode_count",
                "verified_reference_episode_count",
            )
        },
        "verified_runs_by_strategy": {
            strategy: sum(
                row["coverage"]["verified_runs_by_strategy"].get(strategy, 0)
                for row in rows
            )
            for strategy in strategies
        },
        "unsuccessful_case_ids": [
            row["case_id"] for row in rows if not row["measurement_contract_pass"]
        ],
        "successful_cases_only_filter_applied": False,
    }


def _policy_identity(policy: FiberFrameWarmStartPolicy | None) -> dict[str, str]:
    if policy is None or not callable(getattr(policy, "propose", None)):
        raise FiberFrameRuntimeSuiteError(
            "ai_policy with callable propose is required for opt-in"
        )
    values = {
        "policy_id": getattr(policy, "policy_id", None),
        "policy_version": getattr(policy, "policy_version", None),
        "policy_artifact_hash": getattr(policy, "artifact_hash", None),
    }
    for name, value in values.items():
        pattern = _HASH if name == "policy_artifact_hash" else _STABLE_ID
        if type(value) is not str or not pattern.fullmatch(value):
            raise FiberFrameRuntimeSuiteError(f"invalid {name}")
    return values
