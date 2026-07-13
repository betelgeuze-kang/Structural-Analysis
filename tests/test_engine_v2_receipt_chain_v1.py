from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    EngineV2RunError,
    compile_execution_plan,
    execute_linear_static_plan_v1,
    pack_solver_model_buffers,
    run_linear_static_v1,
    solve_linear_static,
    validate_linear_static_run,
)
from structural_analysis.engine_v2.contracts import execution_plan as plan_module  # noqa: E402
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    rollback_trial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"


def _buffers(load_pattern_id: str = "LC_STRONG"):
    return pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )


def test_runner_builds_one_complete_authoritative_receipt_chain() -> None:
    run = run_linear_static_v1(_buffers())
    manifest = run.to_manifest()

    assert run.status == "ready"
    assert run.initial_state.epoch == 0
    assert run.evaluated_trial_state.parent_state_hash == run.initial_state.state_hash
    assert run.committed_state.parent_state_hash == run.evaluated_trial_state.state_hash
    assert run.result_ir.input_bindings.execution_plan_hash == run.execution_plan.plan_hash
    assert run.result_ir.input_bindings.evaluated_trial_state_hash == (
        run.evaluated_trial_state.state_hash
    )
    assert run.result_ir.input_bindings.committed_state_hash == (
        run.committed_state.state_hash
    )
    assert manifest["receipt_chain_hash"] == run.receipt_chain_hash
    assert manifest["claim_boundary"] == (
        "phase0_cpu_reference_linear_static_not_hip_parity"
    )


def test_runner_executes_compiled_operator_without_hidden_reassembly(monkeypatch) -> None:
    calls = 0
    original = plan_module.assemble_linear_static_operator

    def counted_assembly(buffers):
        nonlocal calls
        calls += 1
        return original(buffers)

    monkeypatch.setattr(plan_module, "assemble_linear_static_operator", counted_assembly)
    run = run_linear_static_v1(_buffers())

    assert run.status == "ready"
    assert calls == 1


def test_precompiled_plan_is_reusable_and_replay_deterministic() -> None:
    buffers = _buffers()
    plan = compile_execution_plan(buffers)
    first = execute_linear_static_plan_v1(buffers, plan)
    second = execute_linear_static_plan_v1(buffers, plan)

    assert first.execution_plan is plan
    assert second.execution_plan is plan
    assert first.receipt_chain_hash == second.receipt_chain_hash
    assert first.result_ir.result_ir_hash == second.result_ir.result_ir_hash
    np.testing.assert_array_equal(
        first.backend_result.displacements_si,
        second.backend_result.displacements_si,
    )


def test_runner_result_matches_buffer_convenience_solver() -> None:
    buffers = _buffers()
    run = run_linear_static_v1(buffers, matrix_backend="scipy_sparse")
    direct = solve_linear_static(buffers, matrix_backend="scipy_sparse")

    np.testing.assert_array_equal(
        run.backend_result.displacements_si, direct.displacements_si
    )
    np.testing.assert_array_equal(run.backend_result.residual_si, direct.residual_si)
    np.testing.assert_array_equal(run.backend_result.reactions_si, direct.reactions_si)
    assert run.backend_result.result_hash == direct.result_hash


def test_dense_and_sparse_runs_share_input_but_have_distinct_receipts() -> None:
    buffers = _buffers()
    dense = run_linear_static_v1(buffers, matrix_backend="dense")
    sparse = run_linear_static_v1(buffers, matrix_backend="scipy_sparse")

    assert dense.buffers.artifact_hash == sparse.buffers.artifact_hash
    assert dense.execution_plan.pattern_hash == sparse.execution_plan.pattern_hash
    assert dense.execution_plan.plan_hash != sparse.execution_plan.plan_hash
    assert dense.result_ir.result_ir_hash != sparse.result_ir.result_ir_hash
    assert dense.receipt_chain_hash != sparse.receipt_chain_hash
    np.testing.assert_allclose(
        dense.backend_result.displacements_si,
        sparse.backend_result.displacements_si,
        rtol=1.0e-12,
        atol=1.0e-12,
    )


def test_trial_rollback_returns_exact_initial_state_after_completed_run() -> None:
    run = run_linear_static_v1(_buffers())

    rolled_back = rollback_trial_state(
        run.initial_state,
        run.evaluated_trial_state,
        expected_plan=run.execution_plan,
    )
    assert rolled_back is run.initial_state
    assert rolled_back.state_hash == run.initial_state.state_hash


def test_receipt_chain_hash_and_buffer_binding_tampering_fail_closed() -> None:
    run = run_linear_static_v1(_buffers("LC_STRONG"))
    forged = replace(run, receipt_chain_hash="sha256:" + "0" * 64)

    with pytest.raises(EngineV2RunError) as hash_error:
        validate_linear_static_run(forged)
    assert hash_error.value.code == "engine_v2_run_receipt_chain_hash_mismatch"

    with pytest.raises(EngineV2RunError) as binding_error:
        validate_linear_static_run(run, expected_buffers=_buffers("LC_WEAK"))
    assert binding_error.value.code == "engine_v2_run_buffer_binding_mismatch"


@pytest.mark.parametrize("bad_tolerance", [0.0, -1.0, np.nan, np.inf])
def test_runner_rejects_invalid_tolerance(bad_tolerance: float) -> None:
    with pytest.raises((ValueError, EngineV2RunError)):
        run_linear_static_v1(_buffers(), residual_tolerance=bad_tolerance)
