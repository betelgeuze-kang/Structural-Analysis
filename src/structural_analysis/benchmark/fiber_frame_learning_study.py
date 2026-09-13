"""Solver-produced learning study with held-out guarded runtime comparisons."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    collect_fiber_frame_warm_start_data,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    train_fiber_frame_warm_start_policy,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FiberFrameRuntimeBenchmarkConfig,
)
from structural_analysis.benchmark.fiber_frame_runtime_suite import (
    FiberFrameRuntimeCase,
    benchmark_public_rc_fiber_frame_runtime_suite,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


_PHASE_WALL_CLOCK = perf_counter_ns
_PHASE_CPU_CLOCK = process_time_ns
_PHASE_SCOPES = {
    "data_collection": "whole_data_collection_call_and_report_conversion_including_evaluation_labels",
    "training_attempt": "whole_train_policy_call_report_conversion_and_frozen_policy_identity",
    "evaluation": "whole_runtime_suite_call_report_conversion_and_frozen_policy_check",
}


class FiberFrameLearningStudyPhaseRecorder:
    """Caller-owned, single-study CPU/wall sidecar; never part of study hashes."""

    def __init__(
        self,
        *,
        wall_clock_ns: Callable[[], int] = _PHASE_WALL_CLOCK,
        cpu_clock_ns: Callable[[], int] = _PHASE_CPU_CLOCK,
    ) -> None:
        if not callable(wall_clock_ns) or not callable(cpu_clock_ns):
            raise ValueError("phase clocks must be callable")
        self._wall_clock = wall_clock_ns
        self._cpu_clock = cpu_clock_ns
        self._used = False
        self._phases = {
            name: {
                "status": "skipped",
                "reason": "phase_not_reached",
                "scope": scope,
                "wall_ns": None,
                "cpu_process_time_ns": None,
                "exception_type": None,
                "measurement_errors": [],
            }
            for name, scope in _PHASE_SCOPES.items()
        }

    def _begin_study(self) -> None:
        if self._used:
            raise ValueError("phase recorder is single-use for one study")
        self._used = True

    @staticmethod
    def _read_clock(clock: Callable[[], int]) -> tuple[int | None, str | None]:
        try:
            value = clock()
        except Exception:
            return None, "clock_raised"
        if type(value) is not int or value < 0:
            return None, "clock_value_invalid"
        return value, None

    @contextmanager
    def _observe(self, name: str) -> Iterator[dict[str, Any]]:
        row = self._phases[name]
        row.update(status="running", reason=None)
        wall_start = self._read_clock(self._wall_clock)
        cpu_start = self._read_clock(self._cpu_clock)
        try:
            yield row
        except BaseException as exc:
            row.update(
                status="exception",
                reason="phase_raised",
                exception_type=type(exc).__name__,
            )
            raise
        else:
            if row["status"] == "running":
                row["status"] = "completed"
        finally:
            wall_end = self._read_clock(self._wall_clock)
            cpu_end = self._read_clock(self._cpu_clock)
            for key, start, end in (
                ("wall_ns", wall_start, wall_end),
                ("cpu_process_time_ns", cpu_start, cpu_end),
            ):
                first, first_error = start
                last, last_error = end
                error = first_error or last_error
                if error is None and last < first:
                    error = "clock_regressed"
                if error is None:
                    row[key] = last - first
                else:
                    row["measurement_errors"].append({"field": key, "reason": error})

    def to_dict(self) -> dict[str, Any]:
        measured = [row for row in self._phases.values() if row["status"] != "skipped"]
        valid = bool(measured) and all(
            row["status"] != "running" and not row["measurement_errors"]
            for row in measured
        )
        return {
            "schema_version": "fiber-frame-learning-study-phase-runtime.v1",
            "study_started": self._used,
            "phases": deepcopy(self._phases),
            "measurement_contract_pass": valid,
            "local_timing_evidence_eligible": valid
            and self._wall_clock is _PHASE_WALL_CLOCK
            and self._cpu_clock is _PHASE_CPU_CLOCK,
            "cpu_scope": "current_process_cpu_including_threads_excluding_child_processes",
            "phase_accounting_scope": "declared_phase_calls_excluding_interphase_setup_final_study_assembly_and_hashing",
            "per_phase_peak_memory_bytes": None,
            "per_phase_peak_memory_reason": "phases_share_one_process",
            "physical_validation_claimed": False,
            "generalized_speedup_claimed": False,
        }


@dataclass(frozen=True)
class FiberFrameLearningStudyResult:
    status: str
    _payload: dict[str, Any] = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._payload)


def _policy_bytes(policy) -> bytes:
    return json.dumps(policy.to_dict(), sort_keys=True, allow_nan=False).encode()


def _secant_training_snapshot(training, payload, collection, *, ridge, ood_margin):
    """Bind the explicitly selected target before any held-out evaluation."""
    from structural_analysis.ai.fiber_frame_secant_correction_warm_start_learning import (
        FiberFrameSecantCorrectionWarmStartPolicy,
        decode_fiber_frame_secant_correction_warm_start_policy,
    )

    if (
        type(training.policy) is not FiberFrameSecantCorrectionWarmStartPolicy
        or payload.get("schema_version")
        != "fiber-frame-secant-correction-warm-start-training-result.v3"
    ):
        raise ValueError("secant-correction training profile mismatch")
    decoded = decode_fiber_frame_secant_correction_warm_start_policy(payload["policy"])
    frozen = _policy_bytes(training.policy)
    if (
        frozen != _policy_bytes(decoded)
        or decoded.training_sample_hashes
        != tuple(
            sorted(
                sample.sample_hash
                for sample in collection.samples
                if sample.split == "train"
            )
        )
        or decoded.ridge != float(ridge)
        or decoded.ood_margin != float(ood_margin)
        or json.dumps(payload["dataset_report"], sort_keys=True, allow_nan=False)
        != json.dumps(
            collection.to_dict()["dataset_report"], sort_keys=True, allow_nan=False
        )
    ):
        raise ValueError("secant-correction training source or configuration mismatch")
    return frozen


def run_fiber_frame_learning_study(
    cases: Sequence[FiberFrameWarmStartDataCase],
    *,
    source_revision: str,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig | None = None,
    ridge: float = 1e-6,
    ood_margin: float = 0.1,
    model_conditioning: bool = False,
    learning_target: str = "parent_increment",
    phase_runtime: FiberFrameLearningStudyPhaseRecorder | None = None,
) -> FiberFrameLearningStudyResult:
    """Freeze a train-only policy, then benchmark validation and holdout cases.

    Caller-declared synthetic split identities do not establish independent
    projects or blind prediction. Full data generation includes evaluation label
    computation and is charged explicitly; no label is used to select hyperparameters.
    Optional phase observations remain in the caller's recorder, outside the result.
    """
    if type(model_conditioning) is not bool:
        raise ValueError("model_conditioning must be boolean")
    if type(learning_target) is not str or learning_target not in (
        "parent_increment",
        "secant_correction",
    ):
        raise ValueError(
            "learning_target must be parent_increment or secant_correction"
        )
    secant_correction = learning_target == "secant_correction"
    if secant_correction and not model_conditioning:
        raise ValueError("secant_correction requires model_conditioning=true")
    if (
        phase_runtime is not None
        and type(phase_runtime) is not FiberFrameLearningStudyPhaseRecorder
    ):
        raise ValueError("phase_runtime must be a FiberFrameLearningStudyPhaseRecorder")
    selected = tuple(cases)
    if not selected or any(
        type(case) is not FiberFrameWarmStartDataCase for case in selected
    ):
        raise ValueError("cases must contain typed warm-start data cases")
    for name, value in (("ridge", ridge), ("ood_margin", ood_margin)):
        if (
            type(value) not in (float, int)
            or not math.isfinite(value)
            or value < 0
            or (name == "ridge" and value == 0)
        ):
            raise ValueError(f"{name} is invalid")
    cfg = benchmark_config or FiberFrameRuntimeBenchmarkConfig()
    if type(cfg) is not FiberFrameRuntimeBenchmarkConfig:
        raise ValueError("benchmark_config must be FiberFrameRuntimeBenchmarkConfig")
    declared_hyperparameters = {"ridge": float(ridge), "ood_margin": float(ood_margin)}
    conditioning_declaration = {}
    train_policy = train_fiber_frame_warm_start_policy
    if model_conditioning:
        from structural_analysis.ai.fiber_frame_conditioned_warm_start_learning import (
            train_fiber_frame_conditioned_warm_start_policy,
        )
        from structural_analysis.ai.fiber_frame_warm_start_features import (
            MODEL_FEATURE_PROFILE,
        )

        train_policy = train_fiber_frame_conditioned_warm_start_policy
        declared_hyperparameters["model_conditioning"] = True
        conditioning_declaration = {
            "model_conditioning": True,
            "model_feature_profile": MODEL_FEATURE_PROFILE,
        }
        if secant_correction:
            from structural_analysis.ai.fiber_frame_secant_correction_warm_start_learning import (
                train_fiber_frame_secant_correction_warm_start_policy,
            )

            train_policy = train_fiber_frame_secant_correction_warm_start_policy
            declared_hyperparameters["learning_target"] = learning_target
            conditioning_declaration["learning_target"] = learning_target
    if phase_runtime is not None:
        phase_runtime._begin_study()
    started = perf_counter_ns()
    with (
        phase_runtime._observe("data_collection")
        if phase_runtime is not None
        else nullcontext()
    ) as phase:
        collection = collect_fiber_frame_warm_start_data(
            selected,
            source_revision=source_revision,
            **({"model_conditioning": True} if model_conditioning else {}),
        )
        data_report = collection.to_dict()
        if model_conditioning and (
            data_report.get("schema_version")
            != "fiber-frame-warm-start-data-collection.v2"
            or data_report.get("model_conditioning") is not True
            or data_report.get("model_feature_profile") != MODEL_FEATURE_PROFILE
        ):
            raise ValueError("model-conditioned collection profile mismatch")
        if phase is not None and collection.status != "ready":
            phase.update(status="blocked", reason="data_collection_incomplete")
    report: dict[str, Any] = {
        "schema_version": "fiber-frame-learned-runtime-study.v3"
        if secant_correction
        else "fiber-frame-learned-runtime-study.v2"
        if model_conditioning
        else "fiber-frame-learned-runtime-study.v1",
        **conditioning_declaration,
        "status": "blocked",
        "source_revision": source_revision,
        "hyperparameters_declared_before_collection": declared_hyperparameters,
        "data_collection": data_report,
        "training": None,
        "evaluation": None,
        "cost_accounting": {
            "data_generation_wall_ns": data_report["data_generation_wall_ns"],
            "training_wall_ns": None,
            "training_attempt_wall_ns": None,
            "evaluation_wall_ns": None,
            "study_wall_ns": None,
        },
        "case_break_even": [],
        "failure": None,
        "claims": {
            "training_uses_only_train_targets": True,
            "evaluation_case_splits": ["validation", "holdout"],
            "hyperparameters_selected_using_holdout": False,
            "independent_project_generalization_verified": False,
            "blind_prediction_verified": False,
            "generalized_speedup_claimed": False,
            "construction_savings_claimed": False,
            "production_promotion_eligible": False,
        },
    }
    if collection.status == "ready":
        try:
            frozen_policy = None
            with (
                phase_runtime._observe("training_attempt")
                if phase_runtime is not None
                else nullcontext()
            ):
                training_started = perf_counter_ns()
                try:
                    training = train_policy(
                        collection.samples, ridge=ridge, ood_margin=ood_margin
                    )
                    if secant_correction:
                        report["training"] = training.to_dict()
                        frozen_policy = _secant_training_snapshot(
                            training,
                            report["training"],
                            collection,
                            ridge=ridge,
                            ood_margin=ood_margin,
                        )
                finally:
                    report["cost_accounting"]["training_attempt_wall_ns"] = (
                        perf_counter_ns() - training_started
                    )
                if not secant_correction:
                    report["training"] = training.to_dict()
                report["cost_accounting"]["training_wall_ns"] = (
                    training.training_wall_ns
                )
                policy_hash = training.policy.artifact_hash
            evaluation_cases = tuple(
                FiberFrameRuntimeCase(case.case_id, case.model, case.config)
                for case in selected
                if case.split in {"validation", "holdout"}
            )
            with (
                phase_runtime._observe("evaluation")
                if phase_runtime is not None
                else nullcontext()
            ) as phase:
                eval_started = perf_counter_ns()
                try:
                    evaluation = benchmark_public_rc_fiber_frame_runtime_suite(
                        evaluation_cases,
                        source_revision=source_revision,
                        benchmark_config=cfg,
                        ai_opt_in=True,
                        ai_policy=training.policy,
                    )
                    if secant_correction:
                        report["evaluation"] = evaluation.to_dict()
                        if _policy_bytes(training.policy) != frozen_policy:
                            raise ValueError(
                                "policy bytes changed during frozen evaluation"
                            )
                finally:
                    report["cost_accounting"]["evaluation_wall_ns"] = (
                        perf_counter_ns() - eval_started
                    )
                if not secant_correction:
                    report["evaluation"] = evaluation.to_dict()
                if training.policy.artifact_hash != policy_hash:
                    raise ValueError("policy changed during frozen evaluation")
                report["status"] = (
                    "ready" if evaluation.measurement_contract_pass else "blocked"
                )
                if phase is not None and report["status"] != "ready":
                    phase.update(
                        status="blocked", reason="evaluation_contract_not_passed"
                    )
            upfront = (
                data_report["data_generation_wall_ns"]
                + report["cost_accounting"]["training_attempt_wall_ns"]
            )
            for case in report["evaluation"]["cases"]:
                report["case_break_even"].extend(_case_break_even(case, upfront))
        except Exception as exc:
            report["status"] = "blocked"
            report["failure"] = {
                "kind": "learning_or_evaluation_failed",
                "exception_type": type(exc).__name__,
            }
    else:
        report["failure"] = {
            "kind": "data_collection_incomplete",
            "blockers": data_report["blockers"],
        }
    report["cost_accounting"]["study_wall_ns"] = perf_counter_ns() - started
    report["cost_accounting"]["unavailable_reasons"] = {
        name: (
            "phase_not_executed"
            if name != "training_wall_ns"
            else "training_did_not_return_internal_measurement"
        )
        for name, value in report["cost_accounting"].items()
        if value is None
    }
    report["cost_accounting"]["amortized_upfront_scope"] = (
        "data_generation_plus_entire_training_attempt_excluding_offline_evaluation"
    )
    report["report_hash"] = canonical_hash(report)
    return FiberFrameLearningStudyResult(report["status"], report)


def _case_break_even(case: dict[str, Any], upfront_ns: int) -> list[dict[str, Any]]:
    rows = []
    benchmark = case.get("benchmark_report")
    eligible = bool(
        case.get("measurement_contract_pass")
        and benchmark
        and benchmark["measurement_eligibility"]["local_timing_evidence_eligible"]
    )
    for baseline in (FIBER_FRAME_REFERENCE_STRATEGY, FIBER_FRAME_NON_AI_STRATEGY):
        saving = None
        count = None
        reason = "case_not_fully_verified_with_real_timing"
        if eligible:
            summaries = benchmark["summaries"]
            saving = (
                summaries[baseline]["verified_end_to_end_wall_ns"]["median"]
                - summaries[FIBER_FRAME_AI_STRATEGY]["verified_end_to_end_wall_ns"][
                    "median"
                ]
            )
            reason = "no_positive_observed_net_saving"
            if saving > 0:
                count = max(1, math.ceil(upfront_ns / saving))
                reason = "local_median_projection_for_repeated_identical_case"
        rows.append(
            {
                "case_id": case["case_id"],
                "baseline_strategy": baseline,
                "candidate_strategy": FIBER_FRAME_AI_STRATEGY,
                "data_generation_and_training_wall_ns": upfront_ns,
                "observed_verified_end_to_end_saving_ns": saving,
                "projected_reuses_to_amortize_upfront_cost": count,
                "reason": reason,
                "observed_break_even_execution": False,
                "generalized_speedup_claimed": False,
            }
        )
    return rows
