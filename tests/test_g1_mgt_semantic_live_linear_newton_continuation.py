from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


adapter = _load_module(
    "g1_linear_newton_test_adapter",
    PHASE1 / "g1_mgt_load_coupled_arc_length_adapter.py",
)
module = _load_module(
    "g1_mgt_semantic_live_linear_newton_continuation",
    PHASE1 / "g1_mgt_semantic_live_linear_newton_continuation.py",
)


def _linear_problem():
    tangent_n_per_m = np.asarray(
        [
            [6000.0, -1000.0, 0.0],
            [-1000.0, 5000.0, -500.0],
            [0.0, -500.0, 3500.0],
        ],
        dtype=np.float64,
    )
    reference_load_n = np.asarray([1200.0, -300.0, 750.0])

    def residual_free_n(
        displacement: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        return (
            tangent_n_per_m @ displacement
            - float(load_factor) * reference_load_n
        )

    historical = adapter.LoadCoupledArcLengthCallbackProblem(
        case_id="linear_reference_newton_fixture",
        initial_displacements_m=np.asarray([0.01, 0.02, -0.01]),
        initial_factor=0.656,
        reference_load_free_n=reference_load_n,
        residual_free_n=residual_free_n,
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: reference_load_n
        ),
        zero_state_predictor_free_m=np.linalg.solve(
            tangent_n_per_m,
            reference_load_n,
        ),
        initial_state_policy="historical_checkpoint",
        state_invariant_tangent_csr_n_per_m=tangent_n_per_m,
        state_invariant_tangent_contract=(
            adapter.MGT_STATE_INVARIANT_TANGENT_CONTRACT
        ),
    )
    return historical.zero_state_problem(), tangent_n_per_m, reference_load_n


def _config(*, target: float = 1.0, maximum_iterations: int = 4):
    return module.LinearReferenceNewtonConfig(
        target_load_factor=target,
        initial_load_increment=0.25,
        minimum_load_increment=0.0625,
        maximum_load_increment=0.5,
        successful_step_growth=2.0,
        failed_step_reduction=0.5,
        maximum_attempt_count=12,
        maximum_newton_iterations=maximum_iterations,
        residual_tolerance_n=1.0e-9,
        increment_tolerance_m=1.0e-10,
        tangent_solve_residual_tolerance_n=1.0e-9,
    )


def test_linear_reference_newton_reaches_full_load_without_promotion() -> None:
    problem, tangent, reference = _linear_problem()

    result = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=_config(),
    )
    payload = result.to_dict()

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert [row.load_factor for row in result.checkpoints] == [
        0.0,
        0.25,
        0.75,
        1.0,
    ]
    np.testing.assert_allclose(
        result.final_checkpoint.free_displacements_m,
        np.linalg.solve(tangent, reference),
        rtol=1.0e-12,
        atol=1.0e-12,
    )
    assert result.metrics["accepted_step_count"] == 3
    assert result.metrics["failed_step_count"] == 0
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["material_state_commit_count"] == 0
    assert result.tangent_consistency_audit["all_gates_passed"] is True
    assert all(
        history_row.get("accepted_alpha") in (None, 1.0)
        for attempt in result.attempts
        for history_row in attempt["history"]
    )
    assert payload["claims"]["full_load_linear_reference_checkpoint"] is True
    assert payload["claims"]["actual_mgt_semantic_live_load"] is False
    assert payload["claims"]["failed_step_rollback_exact"] is False
    assert payload["claims"]["restart_checkpoint_consumed"] is False
    assert payload["claims"]["nonlinear_current_tangent"] is False
    assert payload["claims"]["quadratic_convergence"] is False
    assert payload["claims"]["material_state_commit_rollback"] is False
    assert payload["claims"]["g1_full_load_checkpoint"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_restart_checkpoint_replays_to_identical_full_load_state() -> None:
    problem, _, _ = _linear_problem()
    first = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=_config(target=0.75),
    )

    restarted = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=_config(target=1.0),
        checkpoint=first.final_checkpoint,
    )
    direct = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=_config(target=1.0),
    )

    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.to_dict()["claims"]["restart_checkpoint_consumed"] is True
    assert restarted.initial_checkpoint.state_hash == (
        first.final_checkpoint.state_hash
    )
    np.testing.assert_array_equal(
        restarted.final_checkpoint.free_displacements_m,
        direct.final_checkpoint.free_displacements_m,
    )


def test_failed_step_rolls_back_exactly_and_reduces_increment() -> None:
    problem, _, _ = _linear_problem()
    config = module.LinearReferenceNewtonConfig(
        target_load_factor=1.0,
        initial_load_increment=0.5,
        minimum_load_increment=0.25,
        maximum_load_increment=0.5,
        successful_step_growth=1.0,
        failed_step_reduction=0.5,
        maximum_attempt_count=4,
        maximum_newton_iterations=1,
        residual_tolerance_n=1.0e-9,
        increment_tolerance_m=1.0e-10,
        tangent_solve_residual_tolerance_n=1.0e-9,
    )

    result = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=config,
    )

    assert result.status == "partial"
    assert result.terminal_reason == "minimum_load_increment_exhausted"
    assert result.final_checkpoint.load_factor == 0.0
    np.testing.assert_array_equal(
        result.final_checkpoint.free_displacements_m,
        np.zeros(problem.equation_count),
    )
    assert result.metrics["failed_step_count"] == 2
    assert result.metrics["failed_step_rollback_exercised"] is True
    assert result.metrics["rollback_exact"] is True
    assert result.to_dict()["claims"]["failed_step_rollback_exact"] is True
    assert [row["requested_load_increment"] for row in result.attempts] == [
        0.5,
        0.25,
    ]
    assert all(row["rollback_performed"] is True for row in result.attempts)


def test_checkpoint_and_initial_state_contracts_fail_closed() -> None:
    problem, _, _ = _linear_problem()
    config = _config(target=0.5)
    result = module.run_linear_reference_newton_continuation(
        problem=problem,
        config=config,
    )

    with pytest.raises(module.LinearReferenceNewtonContractError, match="hash"):
        module.LinearReferenceNewtonCheckpoint(
            schema_version=module.LINEAR_NEWTON_CHECKPOINT_SCHEMA_VERSION,
            case_id=result.case_id,
            path_contract_hash=result.path_contract_hash,
            step_index=result.final_checkpoint.step_index,
            load_factor=result.final_checkpoint.load_factor,
            free_displacements_m=(
                result.final_checkpoint.free_displacements_m
            ),
            state_hash="sha256:" + "0" * 64,
        )

    historical, _, _ = _linear_problem()
    historical = adapter.LoadCoupledArcLengthCallbackProblem(
        case_id=historical.case_id,
        initial_displacements_m=np.ones(historical.equation_count),
        initial_factor=0.656,
        reference_load_free_n=historical.reference_load_free_n,
        residual_free_n=historical.residual_free_n,
        negative_load_derivative_free_n=(
            historical.negative_load_derivative_free_n
        ),
        initial_state_policy="historical_checkpoint",
        state_invariant_tangent_csr_n_per_m=(
            historical.state_invariant_tangent_csr_n_per_m
        ),
        state_invariant_tangent_contract=(
            historical.state_invariant_tangent_contract
        ),
    )
    with pytest.raises(
        module.LinearReferenceNewtonContractError,
        match="zero_state",
    ):
        module.run_linear_reference_newton_continuation(
            problem=historical,
            config=config,
        )
