"""Engine v2 Phase 0 linear-static orchestration and receipt-chain validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from structural_analysis.engine_v2.backends.cpu_reference import (
    LinearStaticResult,
    solve_linear_static_operator,
)
from structural_analysis.engine_v2.buffers import SolverModelBuffers
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    compile_execution_plan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.result_ir import (
    ResultIR,
    build_result_ir,
    validate_result_ir_v1,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
    validate_state_ir,
)

LINEAR_STATIC_RUN_SCHEMA_VERSION = "structural-analysis-linear-static-run.v1"


class EngineV2RunError(RuntimeError):
    """Fail-closed orchestration or receipt-chain error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class LinearStaticRun:
    """Complete immutable Phase 0 execution and its authoritative receipts."""

    buffers: SolverModelBuffers
    execution_plan: ExecutionPlan
    initial_state: StateIR
    evaluated_trial_state: StateIR
    committed_state: StateIR
    backend_result: LinearStaticResult
    result_ir: ResultIR
    receipt_chain_hash: str

    @property
    def status(self) -> str:
        return self.backend_result.status

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": LINEAR_STATIC_RUN_SCHEMA_VERSION,
            "status": self.status,
            "model_ir_content_hash": self.buffers.model_ir_content_hash,
            "solver_numeric_buffer_hash": self.buffers.numeric_buffer_hash,
            "solver_entity_mapping_hash": self.buffers.entity_mapping_hash,
            "solver_artifact_hash": self.buffers.artifact_hash,
            "execution_plan_hash": self.execution_plan.plan_hash,
            "initial_state_hash": self.initial_state.state_hash,
            "evaluated_trial_state_hash": self.evaluated_trial_state.state_hash,
            "committed_state_hash": self.committed_state.state_hash,
            "backend_native_result_hash": self.backend_result.result_hash,
            "result_ir_hash": self.result_ir.result_ir_hash,
            "receipt_chain_hash": self.receipt_chain_hash,
            "claim_boundary": "phase0_cpu_reference_linear_static_not_hip_parity",
        }


def run_linear_static_v1(
    buffers: SolverModelBuffers,
    *,
    matrix_backend: Literal["dense", "scipy_sparse"] = "dense",
    residual_tolerance: float = 1.0e-10,
) -> LinearStaticRun:
    """Compile and execute one complete CPU-reference receipt chain."""

    plan = compile_execution_plan(
        buffers,
        matrix_backend=matrix_backend,
        residual_tolerance=residual_tolerance,
    )
    return execute_linear_static_plan_v1(buffers, plan)


def execute_linear_static_plan_v1(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
) -> LinearStaticRun:
    """Execute a previously compiled plan without reassembling its operator."""

    validate_execution_plan(plan, expected_buffers=buffers)
    initial = create_initial_state(plan)
    backend_result = solve_linear_static_operator(
        plan.operator,
        node_count=plan.node_count,
        matrix_backend=plan.matrix_backend,
        residual_tolerance=plan.residual_tolerance,
    )
    if backend_result.status != "ready":
        raise EngineV2RunError(
            "engine_v2_backend_not_ready",
            "CPU backend did not satisfy the ExecutionPlan residual tolerance.",
        )
    trial = open_trial_state(
        initial,
        backend_result.displacements_si.reshape(-1),
        load_step=1,
        iteration=0,
        load_factor=1.0,
        time_s=0.0,
        expected_plan=plan,
    )
    committed = commit_trial_state(initial, trial, expected_plan=plan)
    result_ir = build_result_ir(
        buffers,
        plan,
        trial,
        committed,
        backend_result,
        matrix_backend=plan.matrix_backend,
        requested_residual_tolerance=plan.residual_tolerance,
    )
    provisional = LinearStaticRun(
        buffers=buffers,
        execution_plan=plan,
        initial_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        backend_result=backend_result,
        result_ir=result_ir,
        receipt_chain_hash="sha256:" + ("0" * 64),
    )
    run = LinearStaticRun(
        **{
            **provisional.__dict__,
            "receipt_chain_hash": _receipt_chain_hash(provisional),
        }
    )
    validate_linear_static_run(run, expected_buffers=buffers)
    return run


def validate_linear_static_run(
    run: LinearStaticRun,
    *,
    expected_buffers: SolverModelBuffers | None = None,
) -> None:
    """Revalidate every link instead of trusting aggregate hash labels."""

    if not isinstance(run, LinearStaticRun):
        raise EngineV2RunError(
            "engine_v2_run_type_invalid", "Expected a LinearStaticRun artifact."
        )
    buffers = run.buffers
    if expected_buffers is not None and buffers is not expected_buffers:
        expected_bindings = (
            expected_buffers.model_ir_content_hash,
            expected_buffers.numeric_buffer_hash,
            expected_buffers.entity_mapping_hash,
            expected_buffers.artifact_hash,
        )
        actual_bindings = (
            buffers.model_ir_content_hash,
            buffers.numeric_buffer_hash,
            buffers.entity_mapping_hash,
            buffers.artifact_hash,
        )
        if actual_bindings != expected_bindings:
            raise EngineV2RunError(
                "engine_v2_run_buffer_binding_mismatch",
                "Run is bound to different SolverModelBuffers.",
            )
    validate_execution_plan(run.execution_plan, expected_buffers=buffers)
    for state in (
        run.initial_state,
        run.evaluated_trial_state,
        run.committed_state,
    ):
        validate_state_ir(state, expected_plan=run.execution_plan)
    if (
        run.initial_state.role != "committed"
        or run.initial_state.epoch != 0
        or run.initial_state.parent_state_hash is not None
        or run.evaluated_trial_state.role != "trial"
        or run.evaluated_trial_state.epoch != 1
        or run.evaluated_trial_state.parent_state_hash
        != run.initial_state.state_hash
        or run.committed_state.role != "committed"
        or run.committed_state.epoch != 1
        or run.committed_state.parent_state_hash
        != run.evaluated_trial_state.state_hash
    ):
        raise EngineV2RunError(
            "engine_v2_run_state_lineage_invalid",
            "Initial, trial, and committed StateIR lineage is invalid.",
        )
    if not np.array_equal(
        run.backend_result.displacements_si.reshape(-1),
        run.evaluated_trial_state.displacement_si,
    ):
        raise EngineV2RunError(
            "engine_v2_run_trial_result_mismatch",
            "Backend displacement differs from the evaluated trial state.",
        )
    validate_result_ir_v1(
        run.result_ir,
        buffers=buffers,
        plan=run.execution_plan,
        evaluated_trial_state=run.evaluated_trial_state,
        committed_state=run.committed_state,
        backend_result=run.backend_result,
    )
    if run.receipt_chain_hash != _receipt_chain_hash(run):
        raise EngineV2RunError(
            "engine_v2_run_receipt_chain_hash_mismatch",
            "Aggregate run receipt hash is stale.",
        )


def _receipt_chain_hash(run: LinearStaticRun) -> str:
    payload = run.to_manifest()
    payload.pop("receipt_chain_hash")
    return canonical_hash(payload)


__all__ = [
    "LINEAR_STATIC_RUN_SCHEMA_VERSION",
    "EngineV2RunError",
    "LinearStaticRun",
    "execute_linear_static_plan_v1",
    "run_linear_static_v1",
    "validate_linear_static_run",
]
