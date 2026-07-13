"""Non-promoting AI shadow runner for the Phase 0 direct linear solver.

The current authoritative direct solver has no initial-guess input.  This
runner therefore evaluates the proposal gate, deliberately does not feed the
proposal to the solver, and executes the same plan twice through
``execute_linear_static_plan_v1``.  AI-on and AI-off results must be bit
identical.  No timing or speed claim is produced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

import numpy as np

from structural_analysis.engine_v2.ai.gate import (
    AIProposalGateReceipt,
    MAX_PHASE0_RANK,
    evaluate_ai_proposal_gate,
    validate_ai_proposal_gate_receipt,
)
from structural_analysis.engine_v2.buffers import SolverModelBuffers
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan import ExecutionPlan
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    create_initial_state,
    validate_state_ir,
)
from structural_analysis.engine_v2.runner import (
    LinearStaticRun,
    execute_linear_static_plan_v1,
    validate_linear_static_run,
)

AI_SHADOW_RUN_SCHEMA_VERSION = "structural-analysis-ai-shadow-run.v1"
_ZERO_HASH = "sha256:" + ("0" * 64)


class AIShadowRunError(RuntimeError):
    """Fail-closed shadow-run mismatch with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AIShadowParity:
    input_and_plan_bindings_bit_identical: bool
    backend_identity_bit_identical: bool
    backend_result_hash_bit_identical: bool
    displacement_bytes_bit_identical: bool
    residual_bytes_bit_identical: bool
    reaction_bytes_bit_identical: bool
    element_force_bytes_bit_identical: bool
    element_energy_bytes_bit_identical: bool
    total_energy_bit_identical: bool
    state_lineage_hashes_bit_identical: bool
    result_ir_hash_bit_identical: bool
    result_ir_manifest_bit_identical: bool
    receipt_chain_hash_bit_identical: bool
    all_authoritative_outputs_bit_identical: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class AIShadowRun:
    schema_version: str
    status: Literal["shadow_verified"]
    gate_receipt: AIProposalGateReceipt
    ai_off_run: LinearStaticRun
    ai_on_run: LinearStaticRun
    parity: AIShadowParity
    authoritative_solver_invocation_count: int
    proposal_consumed_by_authoritative_solver: bool
    direct_solver_initial_guess_supported: bool
    commit_performed_by_ai: bool
    speed_claim_allowed: bool
    timing_measured: bool
    shadow_run_hash: str

    def to_manifest(self) -> dict[str, Any]:
        validate_ai_shadow_run(self)
        return _shadow_manifest(self, include_hash=True)


def run_ai_shadow_v1(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    accepted_state: StateIR,
    proposal: Any,
) -> AIShadowRun:
    """Gate a proposal, then run untouched AI-off and AI-on solver paths."""

    expected_initial_state = create_initial_state(plan)
    if accepted_state.state_hash != expected_initial_state.state_hash:
        raise AIShadowRunError(
            "ai_shadow_non_initial_base_unsupported",
            "The Phase 0 direct solver can shadow only its deterministic "
            "epoch-0 initial state; later committed-state warm starts are "
            "not supported.",
        )

    gate_receipt = evaluate_ai_proposal_gate(plan, accepted_state, proposal)

    # Both invocations intentionally call the existing authoritative entrypoint.
    # The direct solver has no warm-start API, so the proposal is never consumed.
    ai_off = execute_linear_static_plan_v1(buffers, plan)
    ai_on = execute_linear_static_plan_v1(buffers, plan)
    parity = _compare_authoritative_runs(ai_off, ai_on)
    if not parity.all_authoritative_outputs_bit_identical:
        raise AIShadowRunError(
            "ai_shadow_authoritative_parity_failed",
            "AI-on and AI-off authoritative runs are not bit identical.",
        )
    provisional = AIShadowRun(
        schema_version=AI_SHADOW_RUN_SCHEMA_VERSION,
        status="shadow_verified",
        gate_receipt=gate_receipt,
        ai_off_run=ai_off,
        ai_on_run=ai_on,
        parity=parity,
        authoritative_solver_invocation_count=2,
        proposal_consumed_by_authoritative_solver=False,
        direct_solver_initial_guess_supported=False,
        commit_performed_by_ai=False,
        speed_claim_allowed=False,
        timing_measured=False,
        shadow_run_hash=_ZERO_HASH,
    )
    run = replace(provisional, shadow_run_hash=_shadow_hash(provisional))
    validate_ai_shadow_run(
        run,
        expected_buffers=buffers,
        expected_plan=plan,
        expected_accepted_state=accepted_state,
        expected_proposal=proposal,
    )
    return run


def validate_ai_shadow_run(
    run: AIShadowRun,
    *,
    expected_buffers: SolverModelBuffers | None = None,
    expected_plan: ExecutionPlan | None = None,
    expected_accepted_state: StateIR | None = None,
    expected_proposal: Any | None = None,
) -> None:
    """Revalidate the gate and every authoritative parity assertion."""

    if not isinstance(run, AIShadowRun):
        raise AIShadowRunError("ai_shadow_type_invalid", "Expected an AIShadowRun.")
    if run.schema_version != AI_SHADOW_RUN_SCHEMA_VERSION or run.status != "shadow_verified":
        raise AIShadowRunError("ai_shadow_schema_invalid", "Unsupported shadow artifact.")
    validate_linear_static_run(run.ai_off_run, expected_buffers=expected_buffers)
    validate_linear_static_run(run.ai_on_run, expected_buffers=expected_buffers)
    off_bindings = _run_bindings(run.ai_off_run)
    on_bindings = _run_bindings(run.ai_on_run)
    gate_bindings = _gate_bindings(run.gate_receipt)
    if off_bindings != on_bindings or gate_bindings != off_bindings:
        raise AIShadowRunError(
            "ai_shadow_input_binding_mismatch",
            "Gate, AI-off, and AI-on artifacts are not bound to the same buffers and plan.",
        )
    gate_accepted_state_hash = run.gate_receipt.input_bindings.accepted_state_hash
    if not (
        gate_accepted_state_hash == run.ai_off_run.initial_state.state_hash
        == run.ai_on_run.initial_state.state_hash
    ):
        raise AIShadowRunError(
            "ai_shadow_initial_state_binding_mismatch",
            "The proposal base state is not the deterministic initial state "
            "used by both authoritative direct-solver runs.",
        )
    gate_bindings_receipt = run.gate_receipt.input_bindings
    if not (
        gate_bindings_receipt.accepted_state_epoch
        == run.ai_off_run.initial_state.epoch
        == run.ai_on_run.initial_state.epoch
    ):
        raise AIShadowRunError(
            "ai_shadow_initial_state_epoch_mismatch",
            "The gate accepted-state epoch differs from both authoritative "
            "initial-state epochs.",
        )
    off_initial_displacement_hash = array_data_hash(
        run.ai_off_run.initial_state.displacement_si
    )
    on_initial_displacement_hash = array_data_hash(
        run.ai_on_run.initial_state.displacement_si
    )
    rollback = run.gate_receipt.rollback_proof
    if not (
        gate_bindings_receipt.accepted_displacement_hash
        == rollback.accepted_displacement_hash_before
        == rollback.accepted_displacement_hash_after
        == off_initial_displacement_hash
        == on_initial_displacement_hash
    ):
        raise AIShadowRunError(
            "ai_shadow_initial_displacement_binding_mismatch",
            "The gate and rollback displacement hashes differ from both "
            "authoritative initial states.",
        )
    policy = run.gate_receipt.proposal_policy
    off_free_dof_count = len(run.ai_off_run.execution_plan.free_dofs)
    on_free_dof_count = len(run.ai_on_run.execution_plan.free_dofs)
    if not (
        policy.free_dof_count == off_free_dof_count == on_free_dof_count
    ):
        raise AIShadowRunError(
            "ai_shadow_free_dof_count_mismatch",
            "The proposal free-DOF count differs from both authoritative plans.",
        )
    if not (
        1 <= policy.rank_cap <= MAX_PHASE0_RANK
        and 1
        <= policy.retained_rank
        <= min(policy.rank_cap, policy.free_dof_count)
    ):
        raise AIShadowRunError(
            "ai_shadow_rank_binding_invalid",
            "The retained rank and rank cap exceed the bound free-DOF space.",
        )
    if expected_plan is not None:
        expected_plan_bindings = (
            expected_plan.plan_hash,
            expected_plan.operator_hash,
            expected_plan.pattern_hash,
            expected_plan.partition_hash,
        )
        for candidate in (run.ai_off_run.execution_plan, run.ai_on_run.execution_plan):
            if (
                candidate.plan_hash,
                candidate.operator_hash,
                candidate.pattern_hash,
                candidate.partition_hash,
            ) != expected_plan_bindings:
                raise AIShadowRunError(
                    "ai_shadow_expected_plan_mismatch",
                    "An authoritative run is bound to a different expected plan.",
                )
    gate_expected = (expected_plan, expected_accepted_state, expected_proposal)
    if any(value is not None for value in gate_expected):
        if not all(value is not None for value in gate_expected):
            raise AIShadowRunError(
                "ai_shadow_gate_inputs_incomplete",
                "Plan, accepted state, and proposal are all required for gate replay.",
            )
        validate_state_ir(expected_accepted_state, expected_plan=expected_plan)
        validate_ai_proposal_gate_receipt(
            run.gate_receipt,
            expected_plan=expected_plan,
            expected_accepted_state=expected_accepted_state,
            expected_proposal=expected_proposal,
        )
    else:
        validate_ai_proposal_gate_receipt(run.gate_receipt)

    replay_parity = _compare_authoritative_runs(run.ai_off_run, run.ai_on_run)
    if run.parity != replay_parity or not replay_parity.all_authoritative_outputs_bit_identical:
        raise AIShadowRunError(
            "ai_shadow_parity_receipt_mismatch",
            "Stored parity flags differ from authoritative replay.",
        )
    if (
        run.authoritative_solver_invocation_count != 2
        or run.proposal_consumed_by_authoritative_solver
        or run.direct_solver_initial_guess_supported
        or run.commit_performed_by_ai
        or run.speed_claim_allowed
        or run.timing_measured
    ):
        raise AIShadowRunError(
            "ai_shadow_authority_boundary_invalid",
            "Shadow artifact exceeds Phase 0 authority or makes a speed claim.",
        )
    if run.shadow_run_hash != _shadow_hash(run):
        raise AIShadowRunError(
            "ai_shadow_hash_mismatch",
            "Shadow run hash is stale.",
        )


def _compare_authoritative_runs(
    ai_off: LinearStaticRun,
    ai_on: LinearStaticRun,
) -> AIShadowParity:
    off_result = ai_off.backend_result
    on_result = ai_on.backend_result
    flags = {
        "input_and_plan_bindings_bit_identical": (
            _run_bindings(ai_off) == _run_bindings(ai_on)
        ),
        "backend_identity_bit_identical": off_result.backend == on_result.backend,
        "backend_result_hash_bit_identical": off_result.result_hash == on_result.result_hash,
        "displacement_bytes_bit_identical": _array_bytes_equal(
            off_result.displacements_si, on_result.displacements_si
        ),
        "residual_bytes_bit_identical": _array_bytes_equal(
            off_result.residual_si, on_result.residual_si
        ),
        "reaction_bytes_bit_identical": _array_bytes_equal(
            off_result.reactions_si, on_result.reactions_si
        ),
        "element_force_bytes_bit_identical": _array_bytes_equal(
            off_result.element_end_forces_local_si,
            on_result.element_end_forces_local_si,
        ),
        "element_energy_bytes_bit_identical": _array_bytes_equal(
            off_result.element_strain_energy_j,
            on_result.element_strain_energy_j,
        ),
        "total_energy_bit_identical": (
            off_result.total_strain_energy_j == on_result.total_strain_energy_j
        ),
        "state_lineage_hashes_bit_identical": (
            ai_off.initial_state.state_hash == ai_on.initial_state.state_hash
            and ai_off.evaluated_trial_state.state_hash
            == ai_on.evaluated_trial_state.state_hash
            and ai_off.committed_state.state_hash == ai_on.committed_state.state_hash
        ),
        "result_ir_hash_bit_identical": (
            ai_off.result_ir.result_ir_hash == ai_on.result_ir.result_ir_hash
        ),
        "result_ir_manifest_bit_identical": (
            ai_off.result_ir.to_manifest() == ai_on.result_ir.to_manifest()
        ),
        "receipt_chain_hash_bit_identical": (
            ai_off.receipt_chain_hash == ai_on.receipt_chain_hash
        ),
    }
    return AIShadowParity(
        **flags,
        all_authoritative_outputs_bit_identical=all(flags.values()),
    )


def _array_bytes_equal(left: np.ndarray, right: np.ndarray) -> bool:
    return (
        left.dtype == right.dtype
        and left.shape == right.shape
        and left.tobytes(order="C") == right.tobytes(order="C")
    )


def _run_bindings(run: LinearStaticRun) -> tuple[str, ...]:
    return (
        run.buffers.model_ir_content_hash,
        run.buffers.numeric_buffer_hash,
        run.buffers.entity_mapping_hash,
        run.buffers.artifact_hash,
        run.execution_plan.plan_hash,
        run.execution_plan.operator_hash,
        run.execution_plan.pattern_hash,
        run.execution_plan.partition_hash,
    )


def _gate_bindings(receipt: AIProposalGateReceipt) -> tuple[str, ...]:
    bindings = receipt.input_bindings
    return (
        bindings.model_ir_content_hash,
        bindings.solver_numeric_buffer_hash,
        bindings.solver_entity_mapping_hash,
        bindings.solver_artifact_hash,
        bindings.execution_plan_hash,
        bindings.operator_hash,
        bindings.pattern_hash,
        bindings.partition_hash,
    )


def _shadow_manifest(run: AIShadowRun, *, include_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": run.schema_version,
        "status": run.status,
        "gate_receipt_hash": run.gate_receipt.gate_receipt_hash,
        "gate_status": run.gate_receipt.status,
        "gate_reason_codes": list(run.gate_receipt.reason_codes),
        "accepted_state_hash": run.gate_receipt.input_bindings.accepted_state_hash,
        "execution_plan_hash": run.ai_off_run.execution_plan.plan_hash,
        "ai_off": {
            "backend_native_result_hash": run.ai_off_run.backend_result.result_hash,
            "result_ir_hash": run.ai_off_run.result_ir.result_ir_hash,
            "receipt_chain_hash": run.ai_off_run.receipt_chain_hash,
        },
        "ai_on": {
            "backend_native_result_hash": run.ai_on_run.backend_result.result_hash,
            "result_ir_hash": run.ai_on_run.result_ir.result_ir_hash,
            "receipt_chain_hash": run.ai_on_run.receipt_chain_hash,
        },
        "parity": run.parity.to_dict(),
        "authoritative_solver_invocation_count": run.authoritative_solver_invocation_count,
        "proposal_consumed_by_authoritative_solver": run.proposal_consumed_by_authoritative_solver,
        "direct_solver_initial_guess_supported": run.direct_solver_initial_guess_supported,
        "commit_performed_by_ai": run.commit_performed_by_ai,
        "speed_claim_allowed": run.speed_claim_allowed,
        "timing_measured": run.timing_measured,
        "claim_boundary": (
            "phase0_shadow_only_direct_solver_ignores_ai_proposal_no_speed_claim"
        ),
    }
    if include_hash:
        payload["shadow_run_hash"] = run.shadow_run_hash
    return payload


def _shadow_hash(run: AIShadowRun) -> str:
    return canonical_hash(_shadow_manifest(run, include_hash=False))


__all__ = [
    "AI_SHADOW_RUN_SCHEMA_VERSION",
    "AIShadowParity",
    "AIShadowRun",
    "AIShadowRunError",
    "run_ai_shadow_v1",
    "validate_ai_shadow_run",
]
