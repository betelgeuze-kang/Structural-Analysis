"""Bounded orchestration contracts; injected runtimes are not performance evidence."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    FiberFrameWarmStartDataResult,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartSample,
    train_fiber_frame_warm_start_policy,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
import structural_analysis.benchmark.fiber_frame_learning_study as study
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FiberFrameRuntimeBenchmarkConfig,
    FiberFrameWarmStartInput,
)
from structural_analysis.benchmark.fiber_frame_runtime_suite import (
    FiberFrameRuntimeCase,
    FiberFrameRuntimeSuiteResult,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


REVISION = "a" * 40
BENCHMARK = FiberFrameRuntimeBenchmarkConfig(repetitions=2, warmup_repetitions=0)
UPFRONT_SCOPE = (
    "data_generation_plus_entire_training_attempt_excluding_offline_evaluation"
)


@pytest.fixture
def cases():
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    rows = []
    for index, split in enumerate(("train", "validation", "holdout")):
        snapshot = model.detached_analysis_snapshot()
        snapshot.sections[0]["width_m"] = 0.4 + index * 0.001
        rows.append(
            FiberFrameWarmStartDataCase(
                case_id=f"case-{index}",
                project_id=f"project-{index}",
                geometry_family_id=f"geometry-{index}",
                load_history_id=f"history-{index}",
                split=split,
                model=snapshot,
                config=PublicRCFiberFrameConfig(load_steps=2),
            )
        )
    return tuple(rows)


@pytest.fixture
def samples(cases):
    rows = []
    for case_index, case in enumerate(cases):
        for epoch in range(1, 3):
            load = (epoch - 1) / 2.0
            problem_hash = canonical_hash({"case": case.case_id})
            value = FiberFrameWarmStartInput(
                problem_contract_hash=problem_hash,
                parent_checkpoint_state_hash=canonical_hash(
                    {"case": case.case_id, "epoch": epoch - 1}
                ),
                previous_checkpoint_state_hash=None,
                parent_load_factor=load,
                previous_load_factor=None,
                target_load_factor=load + 0.5,
                free_global_dofs=(3, 4, 5),
                physical_coordinate_scale=(1.0, 1.0, 1.0 / 3.0),
                parent_free_coordinates_m=(0.0, -load * 0.002, -load * 0.001),
                previous_free_coordinates_m=None,
            )
            rows.append(
                FiberFrameWarmStartSample(
                    sample_id=f"sample-{case_index}-{epoch}",
                    project_id=case.project_id,
                    geometry_family_id=case.geometry_family_id,
                    load_history_id=case.load_history_id,
                    model_identity_hash=case.model.canonical_model_checksum,
                    physical_problem_identity_hash=problem_hash,
                    split=case.split,
                    runtime_input=value,
                    accepted_target_free_coordinates_m=(
                        0.0,
                        -(load + 0.5) * 0.002,
                        -(load + 0.5) * 0.001,
                    ),
                )
            )
    return tuple(rows)


def _collection(cases, samples=(), *, status="ready", generation_ns=300):
    rows = [
        {
            "case_id": case.case_id,
            "split": case.split,
            "status": "ready",
            "failure": None,
        }
        for case in cases
    ]
    blockers = []
    if status != "ready":
        rows[-1]["status"] = "blocked"
        rows[-1]["failure"] = {
            "kind": "original_physical_nonconvergence",
            "committed_steps": 1,
            "requested_steps": 2,
        }
        blockers.append({"case_id": cases[-1].case_id, **rows[-1]["failure"]})
    return FiberFrameWarmStartDataResult(
        status,
        tuple(samples),
        json.dumps(
            {
                "status": status,
                "dataset_complete": status == "ready",
                "data_generation_wall_ns": generation_ns,
                "cases": rows,
                "blockers": blockers,
                "injected_test_data_not_physical_or_timing_evidence": True,
            }
        ),
    )


def _evaluation(cases, *, e2e=None, verified=True, real_timing=True):
    if e2e is None:
        e2e = [(1000, 600, 800)] * len(cases)
    rows = []
    for case, medians in zip(cases, e2e, strict=True):
        rows.append(
            {
                "case_id": case.case_id,
                "status": "ready" if verified else "blocked",
                "measurement_contract_pass": verified,
                "benchmark_report": {
                    "measurement_eligibility": {
                        "local_timing_evidence_eligible": real_timing
                    },
                    "summaries": {
                        strategy: {
                            "verified_end_to_end_wall_ns": {"median": median},
                            # Selected-only timing intentionally contradicts e2e.
                            "selected_solver_wall_ns": {"median": selected},
                        }
                        for strategy, median, selected in zip(
                            (
                                FIBER_FRAME_REFERENCE_STRATEGY,
                                FIBER_FRAME_NON_AI_STRATEGY,
                                FIBER_FRAME_AI_STRATEGY,
                            ),
                            medians,
                            (10, 20, 1),
                            strict=True,
                        )
                    },
                },
            }
        )
    payload = {
        "cases": rows,
        "injected_test_data_not_timing_evidence": True,
        "measurement_contract_pass": verified,
    }
    return FiberFrameRuntimeSuiteResult(
        status="ready" if verified else "blocked",
        measurement_contract_pass=verified,
        suite_identity_hash=canonical_hash({"fixture": "study_evaluation"}),
        report_hash=canonical_hash(payload),
        _payload=payload,
    )


def _must_not_run(*args, **kwargs):
    raise AssertionError("incomplete collection must stop downstream execution")


@pytest.mark.parametrize("status", ["blocked", "partial"])
def test_incomplete_collection_preserves_failures_and_stops_training_and_evaluation(
    cases, monkeypatch, status
):
    collection = _collection(cases, status=status)
    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(study, "train_fiber_frame_warm_start_policy", _must_not_run)
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", _must_not_run
    )
    monkeypatch.setattr(study, "perf_counter_ns", iter((10, 50)).__next__)

    result = study.run_fiber_frame_learning_study(cases, source_revision=REVISION)
    payload = result.to_dict()
    assert result.status == "blocked"
    assert payload["data_collection"] == collection.to_dict()
    assert payload["failure"] == {
        "kind": "data_collection_incomplete",
        "blockers": collection.to_dict()["blockers"],
    }
    assert payload["training"] is payload["evaluation"] is None
    assert payload["case_break_even"] == []
    assert payload["cost_accounting"] == {
        "data_generation_wall_ns": 300,
        "training_wall_ns": None,
        "training_attempt_wall_ns": None,
        "evaluation_wall_ns": None,
        "study_wall_ns": 40,
        "unavailable_reasons": {
            "training_wall_ns": "training_did_not_return_internal_measurement",
            "training_attempt_wall_ns": "phase_not_executed",
            "evaluation_wall_ns": "phase_not_executed",
        },
        "amortized_upfront_scope": UPFRONT_SCOPE,
    }
    payload["data_collection"]["cases"].clear()
    assert len(result.to_dict()["data_collection"]["cases"]) == 3


def test_study_freezes_train_artifact_and_evaluates_only_validation_and_holdout(
    cases, samples, monkeypatch
):
    collection = _collection(cases, samples)
    calls = {}

    def collect(selected, *, source_revision):
        assert selected == cases
        assert source_revision == REVISION
        calls["collected"] = True
        return collection

    def train(selected, *, ridge, ood_margin):
        assert calls["collected"] is True
        assert selected == samples
        calls["trained"] = train_fiber_frame_warm_start_policy(
            selected, ridge=ridge, ood_margin=ood_margin
        )
        return calls["trained"]

    def evaluate(selected, **kwargs):
        assert all(type(case) is FiberFrameRuntimeCase for case in selected)
        assert [case.case_id for case in selected] == [
            cases[1].case_id,
            cases[2].case_id,
        ]
        assert [case.model.canonical_model_checksum for case in selected] == [
            case.model.canonical_model_checksum for case in cases[1:]
        ]
        assert [case.config for case in selected] == [case.config for case in cases[1:]]
        assert kwargs == {
            "source_revision": REVISION,
            "benchmark_config": BENCHMARK,
            "ai_opt_in": True,
            "ai_policy": calls["trained"].policy,
        }
        calls["evaluated_artifact_hash"] = kwargs["ai_policy"].artifact_hash
        return _evaluation(selected, real_timing=False)

    monkeypatch.setattr(study, "collect_fiber_frame_warm_start_data", collect)
    monkeypatch.setattr(study, "train_fiber_frame_warm_start_policy", train)
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", evaluate
    )
    payload = study.run_fiber_frame_learning_study(
        cases,
        source_revision=REVISION,
        benchmark_config=BENCHMARK,
        ridge=0.002,
        ood_margin=0.3,
    ).to_dict()

    assert payload["status"] == "ready"
    assert (
        payload["training"]["policy"]["artifact_hash"]
        == calls["evaluated_artifact_hash"]
    )
    assert set(payload["training"]["policy"]["training_sample_hashes"]) == {
        row.sample_hash for row in samples if row.split == "train"
    }
    assert payload["hyperparameters_declared_before_collection"] == {
        "ridge": 0.002,
        "ood_margin": 0.3,
    }
    assert payload["training"]["training_wall_ns"] > 0
    assert all(
        row["projected_reuses_to_amortize_upfront_cost"] is None
        for row in payload["case_break_even"]
    )
    assert payload["claims"]["generalized_speedup_claimed"] is False
    assert payload["claims"]["hyperparameters_selected_using_holdout"] is False
    assert payload["claims"]["independent_project_generalization_verified"] is False


def test_break_even_uses_verified_e2e_and_only_generation_plus_training_upfront(
    cases, samples, monkeypatch
):
    collection = _collection(cases, samples, generation_ns=300)
    training = replace(
        train_fiber_frame_warm_start_policy(samples), training_wall_ns=100
    )
    evaluation = _evaluation(cases[1:], e2e=[(1000, 600, 800), (1000, 900, 1000)])
    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(
        study, "train_fiber_frame_warm_start_policy", lambda *a, **k: training
    )
    monkeypatch.setattr(
        study,
        "benchmark_public_rc_fiber_frame_runtime_suite",
        lambda *a, **k: evaluation,
    )
    monkeypatch.setattr(
        study, "perf_counter_ns", iter((0, 350, 500, 550, 1150, 1300)).__next__
    )

    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION
    ).to_dict()
    assert payload["cost_accounting"] == {
        "data_generation_wall_ns": 300,
        "training_wall_ns": 100,
        "training_attempt_wall_ns": 150,
        "evaluation_wall_ns": 600,
        "study_wall_ns": 1300,
        "unavailable_reasons": {},
        "amortized_upfront_scope": UPFRONT_SCOPE,
    }
    rows = payload["case_break_even"]
    assert len(rows) == 4
    assert [row["observed_verified_end_to_end_saving_ns"] for row in rows] == [
        200,
        -200,
        0,
        -100,
    ]
    assert [row["projected_reuses_to_amortize_upfront_cost"] for row in rows] == [
        3,
        None,
        None,
        None,
    ]
    assert all(row["data_generation_and_training_wall_ns"] == 450 for row in rows)
    assert all(row["observed_break_even_execution"] is False for row in rows)
    assert all(row["generalized_speedup_claimed"] is False for row in rows)
    assert all(row["reason"] == "no_positive_observed_net_saving" for row in rows[1:])
    assert payload["report_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )


@pytest.mark.parametrize("verified,real_timing", [(False, True), (True, False)])
def test_unverified_or_ineligible_cases_never_get_break_even_projections(
    cases, samples, monkeypatch, verified, real_timing
):
    collection = _collection(cases, samples)
    training = train_fiber_frame_warm_start_policy(samples)
    evaluation = _evaluation(cases[1:], verified=verified, real_timing=real_timing)
    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(
        study, "train_fiber_frame_warm_start_policy", lambda *a, **k: training
    )
    monkeypatch.setattr(
        study,
        "benchmark_public_rc_fiber_frame_runtime_suite",
        lambda *a, **k: evaluation,
    )
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION
    ).to_dict()
    assert payload["evaluation"] == evaluation.to_dict()
    assert payload["status"] == ("ready" if verified else "blocked")
    assert all(
        row["observed_verified_end_to_end_saving_ns"] is None
        for row in payload["case_break_even"]
    )
    assert all(
        row["projected_reuses_to_amortize_upfront_cost"] is None
        for row in payload["case_break_even"]
    )


def test_policy_mutation_during_evaluation_blocks_projection_and_keeps_report(
    cases, samples, monkeypatch
):
    collection = _collection(cases, samples)
    training = train_fiber_frame_warm_start_policy(samples)
    evaluation = _evaluation(cases[1:])
    original_hash = training.policy.artifact_hash

    def mutate_during_evaluation(selected, **kwargs):
        # Deliberate fault injection bypasses the frozen dataclass for this test.
        object.__setattr__(
            kwargs["ai_policy"], "artifact_hash", canonical_hash({"tampered": True})
        )
        return evaluation

    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(
        study, "train_fiber_frame_warm_start_policy", lambda *a, **k: training
    )
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", mutate_during_evaluation
    )
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION
    ).to_dict()
    assert payload["status"] == "blocked"
    assert payload["training"]["policy"]["artifact_hash"] == original_hash
    assert payload["evaluation"] == evaluation.to_dict()
    assert payload["failure"] == {
        "kind": "learning_or_evaluation_failed",
        "exception_type": "ValueError",
    }
    assert payload["case_break_even"] == []


def test_training_failure_preserves_collection_and_skips_evaluation(
    cases, samples, monkeypatch
):
    collection = _collection(cases, samples)

    def fail_training(*args, **kwargs):
        raise RuntimeError("unit-test training failure")

    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(study, "train_fiber_frame_warm_start_policy", fail_training)
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", _must_not_run
    )
    monkeypatch.setattr(study, "perf_counter_ns", iter((0, 400, 470, 500)).__next__)
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION
    ).to_dict()
    assert payload["status"] == "blocked"
    assert payload["data_collection"] == collection.to_dict()
    assert payload["training"] is payload["evaluation"] is None
    assert payload["failure"]["exception_type"] == "RuntimeError"
    assert payload["case_break_even"] == []
    assert payload["cost_accounting"]["training_attempt_wall_ns"] == 70
    assert payload["cost_accounting"]["training_wall_ns"] is None
    assert payload["cost_accounting"]["evaluation_wall_ns"] is None
    assert payload["cost_accounting"]["study_wall_ns"] == 500
    assert payload["cost_accounting"]["unavailable_reasons"] == {
        "training_wall_ns": "training_did_not_return_internal_measurement",
        "evaluation_wall_ns": "phase_not_executed",
    }
    json.dumps(deepcopy(payload), allow_nan=False)


def test_evaluation_exception_keeps_elapsed_cost_and_frozen_training_report(
    cases, samples, monkeypatch
):
    collection = _collection(cases, samples)
    training = replace(
        train_fiber_frame_warm_start_policy(samples), training_wall_ns=100
    )

    def fail_evaluation(*args, **kwargs):
        raise RuntimeError("unit-test evaluation failure")

    monkeypatch.setattr(
        study, "collect_fiber_frame_warm_start_data", lambda *a, **k: collection
    )
    monkeypatch.setattr(
        study, "train_fiber_frame_warm_start_policy", lambda *a, **k: training
    )
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", fail_evaluation
    )
    monkeypatch.setattr(
        study, "perf_counter_ns", iter((0, 350, 500, 550, 1150, 1300)).__next__
    )
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION
    ).to_dict()
    assert payload["status"] == "blocked"
    assert payload["training"] == training.to_dict()
    assert payload["evaluation"] is None
    assert payload["failure"]["exception_type"] == "RuntimeError"
    assert payload["case_break_even"] == []
    assert payload["cost_accounting"] == {
        "data_generation_wall_ns": 300,
        "training_wall_ns": 100,
        "training_attempt_wall_ns": 150,
        "evaluation_wall_ns": 600,
        "study_wall_ns": 1300,
        "unavailable_reasons": {},
        "amortized_upfront_scope": UPFRONT_SCOPE,
    }
