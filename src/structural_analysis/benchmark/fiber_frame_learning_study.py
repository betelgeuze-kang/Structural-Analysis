"""Solver-produced learning study with held-out guarded runtime comparisons."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import math
from time import perf_counter_ns
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


@dataclass(frozen=True)
class FiberFrameLearningStudyResult:
    status: str
    _payload: dict[str, Any] = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._payload)


def run_fiber_frame_learning_study(
    cases: Sequence[FiberFrameWarmStartDataCase],
    *,
    source_revision: str,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig | None = None,
    ridge: float = 1e-6,
    ood_margin: float = 0.1,
) -> FiberFrameLearningStudyResult:
    """Freeze a train-only policy, then benchmark validation and holdout cases.

    Caller-declared synthetic split identities do not establish independent
    projects or blind prediction. Full data generation includes evaluation label
    computation and is charged explicitly; no label is used to select hyperparameters.
    """
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
    started = perf_counter_ns()
    collection = collect_fiber_frame_warm_start_data(
        selected, source_revision=source_revision
    )
    data_report = collection.to_dict()
    report: dict[str, Any] = {
        "schema_version": "fiber-frame-learned-runtime-study.v1",
        "status": "blocked",
        "source_revision": source_revision,
        "hyperparameters_declared_before_collection": {
            "ridge": float(ridge),
            "ood_margin": float(ood_margin),
        },
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
            training_started = perf_counter_ns()
            try:
                training = train_fiber_frame_warm_start_policy(
                    collection.samples, ridge=ridge, ood_margin=ood_margin
                )
            finally:
                report["cost_accounting"]["training_attempt_wall_ns"] = (
                    perf_counter_ns() - training_started
                )
            report["training"] = training.to_dict()
            report["cost_accounting"]["training_wall_ns"] = training.training_wall_ns
            policy_hash = training.policy.artifact_hash
            evaluation_cases = tuple(
                FiberFrameRuntimeCase(case.case_id, case.model, case.config)
                for case in selected
                if case.split in {"validation", "holdout"}
            )
            eval_started = perf_counter_ns()
            try:
                evaluation = benchmark_public_rc_fiber_frame_runtime_suite(
                    evaluation_cases,
                    source_revision=source_revision,
                    benchmark_config=cfg,
                    ai_opt_in=True,
                    ai_policy=training.policy,
                )
            finally:
                report["cost_accounting"]["evaluation_wall_ns"] = (
                    perf_counter_ns() - eval_started
                )
            report["evaluation"] = evaluation.to_dict()
            if training.policy.artifact_hash != policy_hash:
                raise ValueError("policy changed during frozen evaluation")
            report["status"] = (
                "ready" if evaluation.measurement_contract_pass else "blocked"
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
