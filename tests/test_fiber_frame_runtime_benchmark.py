from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

import structural_analysis.benchmark.fiber_frame_runtime as runtime_benchmark
from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FiberFrameRuntimeBenchmarkConfig,
    FiberFrameWarmStartInput,
    FiberFrameWarmStartProposal,
    benchmark_public_rc_fiber_frame_warm_starts,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.trial_runtime import MaterialTrialTimingError
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "examples" / "public_rc_fiber_frame_cantilever.json"
SOURCE_REVISION = "sha256:" + "1" * 64
BENCHMARK_CONFIG = FiberFrameRuntimeBenchmarkConfig(
    repetitions=1,
    warmup_repetitions=0,
)
SOLVER_CONFIG = PublicRCFiberFrameConfig(load_steps=2)


class _StepClock:
    def __init__(self, step_ns: int) -> None:
        self._value = 0
        self._step_ns = step_ns

    def __call__(self) -> int:
        self._value += self._step_ns
        return self._value


class _IdentityPolicy:
    policy_id = "test.identity-parent"
    policy_version = "v1"
    artifact_hash = "sha256:" + "a" * 64

    def __init__(self) -> None:
        self.inputs: list[FiberFrameWarmStartInput] = []

    def propose(self, value: FiberFrameWarmStartInput) -> FiberFrameWarmStartProposal:
        self.inputs.append(value)
        return FiberFrameWarmStartProposal(
            free_coordinates_m=value.parent_free_coordinates_m,
            uncertainty=0.0,
            ood=False,
        )


@pytest.fixture(scope="module")
def public_model() -> Any:
    return load_neutral_json(MODEL_PATH)


@pytest.fixture(scope="module")
def non_ai_reports(public_model: Any) -> tuple[Any, Any, _IdentityPolicy]:
    policy = _IdentityPolicy()
    first = benchmark_public_rc_fiber_frame_warm_starts(
        public_model,
        SOLVER_CONFIG,
        benchmark_config=BENCHMARK_CONFIG,
        ai_opt_in=False,
        ai_policy=policy,
        source_revision=SOURCE_REVISION,
        clock_ns=_StepClock(10),
    )
    second = benchmark_public_rc_fiber_frame_warm_starts(
        public_model,
        SOLVER_CONFIG,
        benchmark_config=BENCHMARK_CONFIG,
        ai_opt_in=False,
        ai_policy=policy,
        source_revision=SOURCE_REVISION,
        clock_ns=_StepClock(17),
    )
    return first, second, policy


@pytest.fixture(scope="module")
def ai_report(public_model: Any) -> tuple[Any, _IdentityPolicy]:
    policy = _IdentityPolicy()
    result = benchmark_public_rc_fiber_frame_warm_starts(
        public_model,
        SOLVER_CONFIG,
        benchmark_config=BENCHMARK_CONFIG,
        ai_opt_in=True,
        ai_policy=policy,
        source_revision=SOURCE_REVISION,
        clock_ns=_StepClock(23),
    )
    return result, policy


def test_ai_policy_is_not_called_without_explicit_opt_in(non_ai_reports: Any) -> None:
    first, _, policy = non_ai_reports
    payload = first.to_dict()

    assert policy.inputs == []
    assert first.status == "ready"
    assert first.measurement_contract_pass is True
    assert payload["configuration"]["ai_opt_in"] is False
    assert payload["configuration"]["policy"] is None
    assert {row["strategy"] for row in payload["runs"]} == {
        FIBER_FRAME_REFERENCE_STRATEGY,
        FIBER_FRAME_NON_AI_STRATEGY,
    }
    assert FIBER_FRAME_AI_STRATEGY not in payload["summaries"]


def test_experiment_identity_is_stable_while_runtime_report_is_volatile(
    non_ai_reports: Any,
) -> None:
    first, second, _ = non_ai_reports

    assert first.experiment_identity_hash == second.experiment_identity_hash
    assert first.report_hash != second.report_hash
    assert first.to_dict()["compile_wall_ns"] == 10
    assert second.to_dict()["compile_wall_ns"] == 17
    assert first.to_dict()["claims"]["observed_local_timing_available"] is False
    assert first.to_dict()["warmup"]["total_wall_ns"] is None
    assert all(
        comparison["timing_evidence_available"] is False
        and comparison["observed_reference_over_candidate_selected_solver_wall_ratio"]
        is None
        for comparison in first.to_dict()["observed_comparisons"].values()
    )
    for strategy in (FIBER_FRAME_REFERENCE_STRATEGY, FIBER_FRAME_NON_AI_STRATEGY):
        assert first.path(strategy).to_dict() == second.path(strategy).to_dict()


def test_identical_design_report_keeps_quantity_and_currency_claims_unmeasured(
    non_ai_reports: Any,
) -> None:
    first, _, _ = non_ai_reports
    payload = first.to_dict()
    calculation = payload["calculation_cost_accounting"]
    construction = payload["construction_cost_accounting"]
    claims = payload["claims"]
    boundary = payload["claim_boundary"]

    assert calculation["data_generation_wall_ns"] is None
    assert calculation["training_wall_ns"] is None
    assert calculation["candidate_search_wall_ns"] is None
    assert calculation["cpu_process_time_ns"] is None
    assert calculation["gpu_time_ns"] is None
    assert calculation["peak_memory_bytes"] is None
    assert (
        calculation["material_update_reason"] == "measured_material_integrate_api_calls"
    )
    assert (
        calculation["material_update_scope"]
        == runtime_benchmark.MATERIAL_RUNTIME_ACCOUNTING_SCOPE
    )
    assert calculation["material_trial"]["coverage_complete"] is True
    assert (
        calculation["material_update_wall_ns"]
        == calculation["material_trial"]["wall_ns"]
        > 0
    )
    for strategy_cost in calculation["individual_solve_wall_time"].values():
        linear_solve = strategy_cost["attempted_linear_solve_wall_ns"]
        assert linear_solve["count"] == BENCHMARK_CONFIG.repetitions
        assert (
            0
            < linear_solve["minimum"]
            <= linear_solve["median"]
            <= linear_solve["maximum"]
        )
        material = strategy_cost["attempted_material_trial_wall_ns"]
        assert material["count"] == BENCHMARK_CONFIG.repetitions
        assert 0 < material["minimum"] <= material["median"] <= material["maximum"]
    assert construction == {
        "physical_design_changed": False,
        "baseline_quantities": None,
        "candidate_quantities": None,
        "price_table_hash": None,
        "currency": None,
        "confirmed_currency_savings": None,
        "reason": "identical_physical_model_runtime_comparison_only",
    }
    assert claims["positive_speedup_required_for_contract"] is False
    assert claims["generalized_speedup_claimed"] is False
    assert claims["physical_performance_improvement_claimed"] is False
    assert claims["construction_savings_claimed"] is False
    assert boundary["construction_quantity_or_cost_change"] is False
    assert boundary["confirmed_currency_savings"] is False
    json.dumps(payload, sort_keys=True, allow_nan=False)


def test_reference_secant_and_opt_in_ai_pass_full_history_and_j5(
    ai_report: Any,
) -> None:
    result, policy = ai_report
    payload = result.to_dict()
    rows = {row["strategy"]: row for row in payload["runs"]}

    assert result.status == "ready"
    assert result.measurement_contract_pass is True
    assert len(policy.inputs) == SOLVER_CONFIG.load_steps
    assert set(rows) == {
        FIBER_FRAME_REFERENCE_STRATEGY,
        FIBER_FRAME_NON_AI_STRATEGY,
        FIBER_FRAME_AI_STRATEGY,
    }
    for strategy, row in rows.items():
        assert row["status"] == "ready"
        assert row["contract_pass"] is True
        assert row["committed_step_count"] == SOLVER_CONFIG.load_steps
        assert row["authority_verification"]["contract_pass"] is True
        assert row["authority_verification"]["reason_code"] == (
            "full_j1_j5_recovery_passed"
        )
        assert row["authority_verification"]["terminal_receipt_hash"].startswith(
            "sha256:"
        )
        assert row["reference_comparison"]["full_history_response_match"] is True
        assert result.path(strategy).status == "ready"
        assert len(result.path(strategy).steps) == SOLVER_CONFIG.load_steps
        stateful_runtime = row["attempted_stateful_runtime"]
        newton_runtime = row["attempted_newton_runtime"]
        assert stateful_runtime["total_wall_ns"] > 0
        assert stateful_runtime["run_count"] >= SOLVER_CONFIG.load_steps
        assert stateful_runtime["terminal_trial_assembly_call_count"] >= (
            SOLVER_CONFIG.load_steps
        )
        assert newton_runtime["total_wall_ns"] > 0
        assert newton_runtime["assemble_wall_ns"] > 0
        assert newton_runtime["assemble_call_count"] > 0
        assert newton_runtime["linear_solve_wall_ns"] > 0
        assert newton_runtime["linear_solve_call_count"] > 0
        assert newton_runtime["linear_solve_exception_count"] == 0
        assert newton_runtime["linear_solve_reason"] == "measured_increment_backend"
        assert newton_runtime["total_wall_ns"] == (
            newton_runtime["assemble_wall_ns"]
            + newton_runtime["linear_solve_wall_ns"]
            + newton_runtime["unattributed_wall_ns"]
        )
        _assert_material_run_accounting(row)

    material_total = payload["calculation_cost_accounting"]["material_trial"]
    assert material_total["wall_ns"] == sum(
        row["attempted_newton_runtime"]["material_trial"]["wall_ns"]
        + row["attempted_stateful_runtime"]["terminal_material_trial"]["wall_ns"]
        + sum(step["guard_material_trial"]["wall_ns"] for step in row["steps"])
        for row in rows.values()
    )
    for strategy, row in rows.items():
        expected_material_ns = (
            row["attempted_newton_runtime"]["material_trial"]["wall_ns"]
            + row["attempted_stateful_runtime"]["terminal_material_trial"]["wall_ns"]
            + sum(step["guard_material_trial"]["wall_ns"] for step in row["steps"])
        )
        summary = payload["summaries"][strategy]
        assert summary["material_trial"]["wall_ns"] == expected_material_ns
        assert (
            summary["attempted_material_trial_wall_ns"]["median"]
            == expected_material_ns
        )

    assert all(
        step["proposal_source"] == "ai_policy"
        and step["guard"]["status"] == "accepted"
        and step["seeded_attempt"]["committed"] is True
        and step["selected_source"] == "ai_policy"
        for step in rows[FIBER_FRAME_AI_STRATEGY]["steps"]
    )
    assert (
        payload["summaries"][FIBER_FRAME_AI_STRATEGY]["all_full_j1_j5_recovery_passed"]
        is True
    )
    episode_verification = payload["reference_solver_episode_verification"]
    assert episode_verification["comparable_arm_timing"] is False
    assert len(episode_verification["runs"]) == BENCHMARK_CONFIG.repetitions
    assert all(row["contract_pass"] is True for row in episode_verification["runs"])
    assert (
        payload["observed_comparisons"][FIBER_FRAME_AI_STRATEGY][
            "performance_threshold_applied"
        ]
        is False
    )
    assert (
        payload["observed_comparisons"][FIBER_FRAME_AI_STRATEGY][
            "generalized_speedup_confirmed"
        ]
        is False
    )


def test_failed_seeded_attempt_rolls_back_exactly_then_retries_same_parent(
    public_model: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_solve = runtime_benchmark.solve_stateful_fiber_frame2d_load_step
    forced_failure_count = 0
    failed_parent_hash: str | None = None

    def force_one_seeded_failure(*args: Any, **kwargs: Any) -> Any:
        nonlocal forced_failure_count, failed_parent_hash
        result = real_solve(*args, **kwargs)
        seed = kwargs.get("initial_free_coordinates_m")
        if seed is None or forced_failure_count:
            return result
        parent = args[1]
        forced_failure_count += 1
        failed_parent_hash = parent.state_hash
        return replace(
            result,
            status="blocked",
            committed=False,
            accepted_checkpoint=parent,
            metrics={
                **result.metrics,
                "accepted_checkpoint_hash_after": parent.state_hash,
                "accepted_epoch_after": parent.epoch,
                "solver_contract_pass": False,
                "committed": False,
                "rollback_exact": True,
                "terminal_reason": "synthetic_seeded_attempt_failure",
            },
        )

    monkeypatch.setattr(
        runtime_benchmark,
        "solve_stateful_fiber_frame2d_load_step",
        force_one_seeded_failure,
    )
    result = benchmark_public_rc_fiber_frame_warm_starts(
        public_model,
        SOLVER_CONFIG,
        benchmark_config=BENCHMARK_CONFIG,
        ai_opt_in=True,
        ai_policy=_IdentityPolicy(),
        source_revision=SOURCE_REVISION,
        clock_ns=_StepClock(31),
    )
    payload = result.to_dict()
    recovered_steps = [
        (row, step)
        for row in payload["runs"]
        for step in row["steps"]
        if step["failed_seeded_attempt_rollback_exact"] is True
    ]

    assert forced_failure_count == 1
    assert len(recovered_steps) == 1
    recovered_row, recovered = recovered_steps[0]
    assert recovered["seeded_attempt"]["committed"] is False
    assert recovered["seeded_attempt"]["rollback_exact"] is True
    assert recovered["seeded_attempt"]["terminal_reason"] == (
        "synthetic_seeded_attempt_failure"
    )
    assert recovered["baseline_recovery"]["committed"] is True
    assert recovered["selected_source"] == "baseline_recovery"
    assert recovered["selected_committed"] is True
    _assert_material_run_accounting(recovered_row)
    selected_step = result.path(recovered_row["strategy"]).steps[
        recovered["step_index"]
    ]
    assert selected_step.parent_checkpoint.state_hash == failed_parent_hash
    assert selected_step.initial_free_coordinates_m is None
    assert result.status == "ready"
    assert result.measurement_contract_pass is True
    assert all(
        row["authority_verification"]["contract_pass"] is True
        and row["reference_comparison"]["full_history_response_match"] is True
        for row in payload["runs"]
    )


def test_seeded_solver_exception_uses_exact_parent_for_baseline_recovery(
    public_model: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = public_model.detached_analysis_snapshot()
    compiled, _, _ = runtime_benchmark.public_api._compile(snapshot)
    assert compiled is not None
    real_solve = runtime_benchmark.solve_stateful_fiber_frame2d_load_step
    raised = False

    def raise_once_for_seed(*args: Any, **kwargs: Any) -> Any:
        nonlocal raised
        if kwargs.get("initial_free_coordinates_m") is not None and not raised:
            raised = True
            raise ArithmeticError("synthetic seeded solve exception")
        return real_solve(*args, **kwargs)

    monkeypatch.setattr(
        runtime_benchmark,
        "solve_stateful_fiber_frame2d_load_step",
        raise_once_for_seed,
    )
    execution = runtime_benchmark._run_strategy(
        FIBER_FRAME_AI_STRATEGY,
        compiled.problem,
        SOLVER_CONFIG.target_load_factors,
        NewtonRaphsonConfig(
            residual_tolerance=SOLVER_CONFIG.residual_tolerance,
            increment_tolerance=SOLVER_CONFIG.increment_tolerance_m,
            max_iterations=SOLVER_CONFIG.maximum_iterations,
        ),
        BENCHMARK_CONFIG,
        ai_policy=_IdentityPolicy(),
        clock_ns=_StepClock(13),
    )
    recovered = next(
        row
        for row in execution.step_rows
        if row["failed_seeded_attempt_rollback_exact"] is True
    )

    assert raised is True
    assert execution.path.status == "ready"
    assert recovered["seeded_attempt"]["status"] == "error"
    assert recovered["seeded_attempt"]["exception_type"] == "ArithmeticError"
    assert recovered["baseline_recovery"]["committed"] is True
    assert (
        recovered["seeded_attempt"]["parent_checkpoint_state_hash"]
        == recovered["baseline_recovery"]["parent_checkpoint_state_hash"]
    )


def _assert_material_run_accounting(row):
    attempts = [
        step[key]
        for step in row["steps"]
        for key in ("seeded_attempt", "baseline_attempt", "baseline_recovery")
        if step[key] is not None
    ]
    for runtime_key, material_key, inclusive_key in (
        ("newton_runtime", "material_trial", "assemble_wall_ns"),
        (
            "stateful_runtime",
            "terminal_material_trial",
            "terminal_trial_assembly_wall_ns",
        ),
    ):
        aggregated = row["attempted_" + runtime_key][material_key]
        assert aggregated["coverage_complete"] is True
        assert aggregated["unavailable_reasons"] == []
        assert (
            0 < aggregated["wall_ns"] <= row["attempted_" + runtime_key][inclusive_key]
        )
        for field in (
            "wall_ns",
            "call_count",
            "exception_count",
            "instrumented_section_call_count",
        ):
            assert aggregated[field] == sum(
                attempt[runtime_key][material_key][field] for attempt in attempts
            )
        for kind in ("steel", "concrete"):
            assert aggregated["materials"][kind]["call_count"] > 0
    for step in row["steps"]:
        material = step["guard_material_trial"]
        assert material["coverage_complete"] is True
        assert 0 <= material["wall_ns"] <= step["guard_wall_ns"]
        if step["guard"]["assembly_count"]:
            assert material["wall_ns"] > 0
            assert all(
                material["materials"][kind]["call_count"] > 0
                for kind in ("steel", "concrete")
            )
        else:
            assert material["wall_ns"] == material["call_count"] == 0
        # The new material sidecar is separate from the existing guard schema.
        assert "material_trial" not in step["guard"]
        receipt = step["guard"]["guard_receipt_hash"]
        if receipt is not None:
            assert receipt == canonical_hash(
                {
                    key: value
                    for key, value in step["guard"].items()
                    if key != "guard_receipt_hash"
                }
            )


@pytest.mark.parametrize("missing", ["newton", "terminal", "guard"])
def test_missing_material_metadata_keeps_observed_subset_but_not_complete_cost(
    ai_report, missing
):
    report, _ = ai_report
    row = deepcopy(
        next(
            row
            for row in report.to_dict()["runs"]
            if row["strategy"] == FIBER_FRAME_AI_STRATEGY
        )
    )
    original = runtime_benchmark._strategy_summary([row])
    if missing == "newton":
        removed = row["attempted_newton_runtime"].pop("material_trial")
    elif missing == "terminal":
        removed = row["attempted_stateful_runtime"].pop("terminal_material_trial")
    else:
        removed = row["steps"][0].pop("guard_material_trial")
    summary = runtime_benchmark._strategy_summary([row])
    material = summary["material_trial"]
    assert material["coverage_complete"] is False
    assert "material_trial_metadata_missing" in material["unavailable_reasons"]
    assert (
        material["wall_ns"]
        == original["material_trial"]["wall_ns"] - removed["wall_ns"]
        > 0
    )
    assert (
        material["call_count"]
        == original["material_trial"]["call_count"] - removed["call_count"]
        > 0
    )
    distribution = summary["attempted_material_trial_wall_ns"]
    assert distribution["count"] == 0
    assert (
        distribution["minimum"]
        is distribution["median"]
        is distribution["maximum"]
        is None
    )
    assert distribution["reason"] == "material_trial_coverage_incomplete"


@pytest.mark.parametrize("mutation", ["scope", "subtotals", "boolean_time"])
def test_invalid_material_metadata_is_not_credited_as_measured(ai_report, mutation):
    report, _ = ai_report
    row = deepcopy(
        next(
            row
            for row in report.to_dict()["runs"]
            if row["strategy"] == FIBER_FRAME_AI_STRATEGY
        )
    )
    material = row["attempted_newton_runtime"]["material_trial"]
    if mutation == "scope":
        material["scope"] = "unknown_material_work"
    elif mutation == "subtotals":
        material["wall_ns"] += 1
    else:
        material["wall_ns"] = True
    summary = runtime_benchmark._strategy_summary([row])
    assert summary["material_trial"]["coverage_complete"] is False
    assert (
        "material_trial_metadata_invalid"
        in summary["material_trial"]["unavailable_reasons"]
    )
    assert summary["attempted_material_trial_wall_ns"]["median"] is None


@pytest.mark.parametrize("capture_failure", [False, True])
def test_material_clock_defect_is_not_reclassified_as_recoverable_solver_failure(
    monkeypatch, capture_failure
):
    error = MaterialTrialTimingError("synthetic material timing defect")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        runtime_benchmark, "solve_stateful_fiber_frame2d_load_step", fail
    )
    with pytest.raises(MaterialTrialTimingError) as caught:
        runtime_benchmark._timed_solve(
            object(),
            object(),
            1.0,
            NewtonRaphsonConfig(),
            initial_free_coordinates_m=(0.0,),
            clock_ns=_StepClock(10),
            capture_failure=capture_failure,
        )
    assert caught.value is error


@pytest.mark.parametrize("capture_failure", [False, True])
def test_consecutive_material_and_outer_clock_failures_keep_timing_error(
    public_model, capture_failure
):
    compiled, _, _ = runtime_benchmark.public_api._compile(public_model)
    assert compiled is not None
    problem = compiled.problem
    parent = runtime_benchmark.initial_stateful_fiber_frame2d_checkpoint(problem)
    parent_bytes = parent.canonical_bytes()

    class ConsecutiveFailureClock:
        calls = 0

        def __call__(self):
            self.calls += 1
            # Material entry fails first; the enclosing assembly finally fails
            # next, replacing that exception with its own ValueError.
            return False if self.calls in (5, 6) else self.calls * 10

    clock = ConsecutiveFailureClock()
    with pytest.raises(MaterialTrialTimingError, match="timing failed"):
        runtime_benchmark._timed_solve(
            problem,
            parent,
            0.5,
            NewtonRaphsonConfig(max_iterations=1),
            initial_free_coordinates_m=(0.0,) * len(problem.free_global_dofs),
            clock_ns=clock,
            capture_failure=capture_failure,
        )
    assert clock.calls == 8
    assert parent.canonical_bytes() == parent_bytes


@pytest.mark.parametrize("capture_failure", [False, True])
@pytest.mark.parametrize("phase", ["newton", "terminal"])
def test_normal_return_with_material_timing_error_cannot_become_solver_attempt(
    monkeypatch, capture_failure, phase
):
    returned = []

    def normal_return_with_invalid_timing(*args, runtime_recorder, **kwargs):
        material = (
            runtime_recorder.newton.material
            if phase == "newton"
            else runtime_recorder.terminal_material
        )
        material.timing_error_count = 1
        sentinel = object()
        returned.append(sentinel)
        return sentinel

    monkeypatch.setattr(
        runtime_benchmark,
        "solve_stateful_fiber_frame2d_load_step",
        normal_return_with_invalid_timing,
    )
    with pytest.raises(MaterialTrialTimingError, match="timing failed"):
        runtime_benchmark._timed_solve(
            object(),
            object(),
            1.0,
            NewtonRaphsonConfig(),
            initial_free_coordinates_m=(0.0,),
            clock_ns=_StepClock(10),
            capture_failure=capture_failure,
        )
    assert len(returned) == 1
