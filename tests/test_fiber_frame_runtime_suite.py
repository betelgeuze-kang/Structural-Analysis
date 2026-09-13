from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import pytest

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE,
    FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE,
    FiberFrameRuntimeBenchmarkConfig,
    FiberFrameRuntimeBenchmarkResult,
)
from structural_analysis.benchmark.fiber_frame_runtime_suite import (
    FiberFrameRuntimeCase,
    FiberFrameRuntimeSuiteError,
    benchmark_public_rc_fiber_frame_runtime_suite,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.model.schema import CanonicalModel


REVISION = "1" * 40
MEASURE = FiberFrameRuntimeBenchmarkConfig(repetitions=1, warmup_repetitions=0)
CONFIG = PublicRCFiberFrameConfig(load_steps=2)


@pytest.fixture(scope="module")
def public_model() -> CanonicalModel:
    return load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )


@pytest.fixture
def cases(public_model: CanonicalModel) -> tuple[FiberFrameRuntimeCase, ...]:
    baseline = public_model.detached_analysis_snapshot()
    variant = public_model.detached_analysis_snapshot()
    variant.sections[0]["depth_m"] = 0.7
    variant.loads[0]["components"]["FY"] = -12.0
    return (
        FiberFrameRuntimeCase("baseline", baseline, CONFIG),
        FiberFrameRuntimeCase("deeper_higher_load", variant, CONFIG),
    )


def _result(payload: dict[str, Any]) -> FiberFrameRuntimeBenchmarkResult:
    payload = deepcopy(payload)
    payload["report_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    return FiberFrameRuntimeBenchmarkResult(
        status=payload["status"],
        measurement_contract_pass=payload["measurement_contract_pass"],
        report_hash=payload["report_hash"],
        experiment_identity_hash=canonical_hash({"test": "runner"}),
        _payload=payload,
        _paths={},
    )


def _runner(
    model: CanonicalModel, config: PublicRCFiberFrameConfig, **kwargs: Any
) -> FiberFrameRuntimeBenchmarkResult:
    strategies = [FIBER_FRAME_REFERENCE_STRATEGY, FIBER_FRAME_NON_AI_STRATEGY]
    policy = None
    if kwargs["ai_opt_in"]:
        strategies.append(FIBER_FRAME_AI_STRATEGY)
        source = kwargs["ai_policy"]
        policy = {
            "policy_id": source.policy_id,
            "policy_version": source.policy_version,
            "policy_artifact_hash": source.artifact_hash,
        }
    return _result(
        {
            "status": "ready",
            "measurement_contract_pass": True,
            "measurement_profile": FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE
            if kwargs["clock_ns"] is perf_counter_ns
            else FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE,
            "measurement_eligibility": {"local_timing_evidence_eligible": True},
            "bindings": {
                "canonical_model_checksum": model.canonical_model_checksum,
                "input_checksum": model.input_checksum,
                "source_revision": kwargs["source_revision"],
                "load_history_hash": canonical_hash(list(config.target_load_factors)),
            },
            "configuration": {
                "public_solver": {
                    "load_factors": list(config.target_load_factors),
                    "residual_tolerance": config.residual_tolerance,
                    "increment_tolerance": config.increment_tolerance_m,
                    "max_iterations": config.maximum_iterations,
                },
                "benchmark": kwargs["benchmark_config"].to_dict(),
                "ai_opt_in": kwargs["ai_opt_in"],
                "policy": policy,
            },
            "runs": [
                {
                    "repetition": repetition,
                    "strategy": strategy,
                    "status": "ready",
                    "contract_pass": True,
                    "committed_step_count": config.load_steps,
                    "load_step_count": config.load_steps,
                    "authority_verification": {
                        "contract_pass": True,
                        "reason_code": "full_j1_j5_recovery_passed",
                    },
                    "reference_comparison": {"full_history_response_match": True},
                    "verified_end_to_end_wall_ns": kwargs["clock_ns"](),
                }
                for repetition in range(kwargs["benchmark_config"].repetitions)
                for strategy in strategies
            ],
            "reference_solver_episode_verification": {
                "runs": [
                    {"repetition": repetition, "status": "ready", "contract_pass": True}
                    for repetition in range(kwargs["benchmark_config"].repetitions)
                ],
            },
        }
    )


def _suite(cases: tuple[FiberFrameRuntimeCase, ...], **kwargs: Any) -> Any:
    return benchmark_public_rc_fiber_frame_runtime_suite(
        cases,
        source_revision=kwargs.pop("source_revision", REVISION),
        benchmark_config=kwargs.pop("benchmark_config", MEASURE),
        runner=kwargs.pop("runner", _runner),
        **kwargs,
    )


def test_case_and_suite_declarations_reject_ambiguous_ids(cases: Any) -> None:
    for case_id in ("", " contains-space", "baseline ", "a/b", "1numeric", True):
        with pytest.raises(FiberFrameRuntimeSuiteError, match="case_id"):
            FiberFrameRuntimeCase(case_id, cases[0].model)
    with pytest.raises(FiberFrameRuntimeSuiteError, match="CanonicalModel"):
        FiberFrameRuntimeCase("bad", {})
    with pytest.raises(FiberFrameRuntimeSuiteError, match="PublicRCFiberFrameConfig"):
        FiberFrameRuntimeCase("bad", cases[0].model, {})
    with pytest.raises(FiberFrameRuntimeSuiteError, match="unique"):
        _suite((cases[0], cases[0]))
    with pytest.raises(FiberFrameRuntimeSuiteError, match="non-empty"):
        _suite(())
    with pytest.raises(FiberFrameRuntimeSuiteError, match="source_revision"):
        _suite(cases, source_revision=" main ")
    with pytest.raises(FiberFrameRuntimeSuiteError, match="ai_policy"):
        _suite(cases, ai_opt_in=True)


def test_identity_binds_declared_cases_config_revision_but_not_timing(
    cases: Any,
) -> None:
    first = _suite(cases, clock_ns=lambda: 10)
    second = _suite(cases, clock_ns=lambda: 100)
    assert first.suite_identity_hash == second.suite_identity_hash
    assert first.report_hash != second.report_hash
    modified = cases[1].model.detached_analysis_snapshot()
    modified.sections[0]["width_m"] = 0.5
    variants = (
        _suite(cases, source_revision="2" * 40, clock_ns=lambda: 10),
        _suite((cases[0], replace(cases[1], model=modified)), clock_ns=lambda: 10),
        _suite(
            (cases[0], replace(cases[1], config=replace(CONFIG, load_steps=3))),
            clock_ns=lambda: 10,
        ),
        _suite(tuple(reversed(cases)), clock_ns=lambda: 10),
        _suite(
            cases, benchmark_config=replace(MEASURE, repetitions=2), clock_ns=lambda: 10
        ),
    )
    assert all(
        result.suite_identity_hash != first.suite_identity_hash for result in variants
    )
    payload = first.to_dict()
    assert first.measurement_contract_pass is True
    assert payload["coverage"]["declared_case_count"] == 2
    assert payload["coverage"]["fully_verified_run_count"] == 4
    assert payload["suite_speedup_ratio"] is None
    assert payload["claims"]["generalized_speedup_claimed"] is False
    assert payload["measurement_eligibility"]["local_timing_evidence_eligible"] is False
    assert (
        payload["measurement_eligibility"]["injected_runner_for_contract_testing_only"]
        is True
    )
    assert (
        payload["measurement_eligibility"]["injected_clock_for_contract_testing_only"]
        is True
    )
    payload["cases"].clear()
    assert len(first.to_dict()["cases"]) == 2
    json.dumps(first.to_dict(), allow_nan=False)


def test_failure_and_blocked_case_stay_in_denominator_and_later_cases_run(
    cases: Any,
) -> None:
    cases = (
        cases[0],
        replace(cases[1], case_id="blocked"),
        replace(cases[0], case_id="later"),
    )
    calls = []

    def runner(model: Any, config: Any, **kwargs: Any) -> Any:
        calls.append(model.canonical_model_checksum)
        if len(calls) == 1:
            raise RuntimeError("original-case-error")
        result = _runner(model, config, **kwargs)
        if len(calls) == 2:
            payload = result.to_dict()
            payload["status"] = "blocked"
            payload["measurement_contract_pass"] = False
            payload["runs"][1]["reference_comparison"][
                "full_history_response_match"
            ] = False
            return _result(payload)
        return result

    payload = _suite(cases, runner=runner).to_dict()
    assert len(calls) == 3
    assert payload["status"] == "blocked"
    assert payload["cases"][0]["failure"] == {
        "exception_type": "RuntimeError",
        "detail": "original-case-error",
    }
    assert payload["cases"][1]["benchmark_report"]["status"] == "blocked"
    coverage = payload["coverage"]
    assert coverage["declared_case_count"] == coverage["attempted_case_count"] == 3
    assert coverage["verified_case_count"] == 1
    assert coverage["expected_run_count"] == 6
    assert coverage["fully_verified_run_count"] == 3
    assert coverage["status_counts"] == {
        "ready": 1,
        "blocked": 1,
        "unsupported": 0,
        "error": 1,
    }
    assert coverage["unsuccessful_case_ids"] == ["baseline", "blocked"]
    assert coverage["successful_cases_only_filter_applied"] is False
    assert payload["claims"]["generalized_speedup_claimed"] is False
    assert (
        payload["claims"]["observed_local_timing_available_for_complete_suite"] is False
    )


@pytest.mark.parametrize(
    "alteration",
    [
        "foreign_model",
        "foreign_revision",
        "foreign_config",
        "missing",
        "duplicate",
        "unverified",
        "missing_episode",
        "tampered_hash",
        "malformed",
    ],
)
def test_incomplete_or_unbound_reports_cannot_pass(cases: Any, alteration: str) -> None:
    def runner(model: Any, config: Any, **kwargs: Any) -> Any:
        payload = _runner(model, config, **kwargs).to_dict()
        if alteration == "foreign_model":
            payload["bindings"]["canonical_model_checksum"] = "sha256:" + "a" * 64
        elif alteration == "foreign_revision":
            payload["bindings"]["source_revision"] = "2" * 40
        elif alteration == "foreign_config":
            payload["configuration"]["public_solver"]["max_iterations"] += 1
        elif alteration == "missing":
            payload["runs"].pop()
        elif alteration == "duplicate":
            payload["runs"][1] = deepcopy(payload["runs"][0])
        elif alteration == "unverified":
            payload["runs"][1]["authority_verification"]["contract_pass"] = False
        elif alteration == "missing_episode":
            payload["reference_solver_episode_verification"]["runs"].clear()
        elif alteration == "malformed":
            payload["runs"] = None
        result = _result(payload)
        return (
            replace(result, report_hash="sha256:" + "a" * 64)
            if alteration == "tampered_hash"
            else result
        )

    payload = _suite(cases, runner=runner).to_dict()
    assert payload["status"] == "blocked"
    assert payload["coverage"]["verified_case_count"] == 0
    assert payload["coverage"]["expected_run_count"] == 4
    assert payload["coverage"]["unsuccessful_case_ids"] == [
        case.case_id for case in cases
    ]
    assert len(payload["cases"]) == 2


def test_all_inputs_are_snapshotted_before_runner_can_mutate_later_case(
    cases: Any,
) -> None:
    original = cases[1].model.canonical_model_checksum
    calls = []

    def runner(model: Any, config: Any, **kwargs: Any) -> Any:
        calls.append(model.canonical_model_checksum)
        cases[1].model.sections[0]["depth_m"] = 9.0
        return _runner(model, config, **kwargs)

    payload = _suite(cases, runner=runner).to_dict()
    assert calls[1] == original
    assert (
        payload["declaration"]["cases_in_execution_order"][1][
            "canonical_model_checksum"
        ]
        == original
    )
    assert payload["measurement_contract_pass"] is True


def test_unserializable_model_and_mutable_case_list_do_not_drop_declared_cases(
    cases: Any,
) -> None:
    malformed = replace(cases[0].model, metadata={"case_id": {"not_json"}})
    case_list = [
        replace(cases[0], model=malformed),
        cases[1],
        replace(cases[0], case_id="last"),
    ]

    def runner(model: Any, config: Any, **kwargs: Any) -> Any:
        case_list.clear()
        return _runner(model, config, **kwargs)

    payload = _suite(case_list, runner=runner).to_dict()
    assert payload["status"] == "blocked"
    assert payload["coverage"]["declared_case_count"] == 3
    assert payload["coverage"]["verified_case_count"] == 2
    assert payload["cases"][0]["failure"]["exception_type"] == "TypeError"
    assert payload["cases"][0]["binding"]["model_identity_available"] is False
    assert payload["cases"][0]["binding"]["canonical_model_checksum"] is None
    assert payload["coverage"]["expected_run_count"] == 6


def test_opt_in_adds_each_ai_arm_and_policy_identity_without_implicit_enablement(
    cases: Any,
) -> None:
    class Policy:
        policy_id = "test.policy"
        policy_version = "v1"
        artifact_hash = "sha256:" + "a" * 64

        def propose(self, value: Any) -> Any:
            raise AssertionError("injected runner must not perform inference")

    policy = Policy()
    disabled = _suite(cases, ai_policy=policy).to_dict()
    enabled = _suite(cases, ai_policy=policy, ai_opt_in=True).to_dict()
    assert disabled["declaration"]["policy"] is None
    assert disabled["coverage"]["expected_run_count"] == 4
    assert enabled["coverage"]["expected_run_count"] == 6
    assert (
        enabled["coverage"]["verified_runs_by_strategy"][FIBER_FRAME_AI_STRATEGY] == 2
    )
    assert (
        enabled["declaration"]["policy"]["policy_artifact_hash"] == policy.artifact_hash
    )
    assert enabled["suite_identity_hash"] != disabled["suite_identity_hash"]


def test_real_public_solver_keeps_unsupported_case_and_verifies_supported_case(
    public_model: CanonicalModel,
) -> None:
    unsupported = replace(
        public_model, unsupported_features=[{"kind": "suite_test_unsupported"}]
    )
    suite = benchmark_public_rc_fiber_frame_runtime_suite(
        (
            FiberFrameRuntimeCase("unsupported_first", unsupported, CONFIG),
            FiberFrameRuntimeCase("supported_after", public_model, CONFIG),
        ),
        source_revision=REVISION,
        benchmark_config=MEASURE,
    )
    payload = suite.to_dict()
    assert suite.status == "blocked"
    assert payload["coverage"]["status_counts"] == {
        "ready": 1,
        "blocked": 0,
        "unsupported": 1,
        "error": 0,
    }
    assert payload["coverage"]["expected_run_count"] == 4
    assert payload["coverage"]["fully_verified_run_count"] == 2
    assert payload["coverage"]["verified_reference_episode_count"] == 1
    assert "suite_test_unsupported" in payload["cases"][0]["failure"]["detail"]
    supported = payload["cases"][1]
    assert supported["measurement_contract_pass"] is True
    assert supported["coverage"]["validation_errors"] == []
    assert (
        supported["benchmark_report"]["bindings"]["canonical_model_checksum"]
        == public_model.canonical_model_checksum
    )
    assert payload["measurement_eligibility"]["local_timing_evidence_eligible"] is False
