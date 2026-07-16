from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_case_parity_v2 as parity_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeRestartRowV1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_fp64_csr_residual_normwise_v1 import _terminal_case


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_case_parity_v2.schema.json"
)
V1_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_case_parity_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _scoped_sources() -> tuple[object, object, object, object, object]:
    plan, cpu, solution, residual, outcome, _row = _terminal_case()
    assert outcome.metrics is not None
    assert len(cpu.history) == 1
    cpu_row = cpu.history[0]
    metrics = outcome.metrics
    hip_row = HipFgmresTerminalOutcomeRestartRowV1(
        slot_index=1,
        populated=True,
        restart_index=cpu_row.restart_index,
        start_iteration=cpu_row.start_iteration,
        end_iteration=cpu_row.end_iteration,
        arnoldi_step_count=cpu_row.arnoldi_step_count,
        reorthogonalization_count=cpu_row.reorthogonalization_count,
        termination_hint=cpu_row.termination_hint,
        termination_hint_code=0,
        flags=0,
        flag_names=(),
        estimated_residual_l2=cpu_row.estimated_residual_l2,
        true_residual_l2=metrics.final_residual_l2,
        true_residual_linf=metrics.final_residual_linf,
        scaled_true_residual=metrics.final_scaled_residual,
        solution_update_l2=cpu_row.solution_update_l2,
    )
    scoped_outcome = replace(outcome, restart_rows=(hip_row,))
    terminal = parity_v2.replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution,
        true_residual=residual,
        outcome=scoped_outcome,
    )
    history = parity_v2.replay_hip_fgmres_single_terminal_restart_history_v2(
        cpu_result=cpu,
        outcome=scoped_outcome,
        terminal_metric_parity=terminal,
    )
    return plan, cpu, scoped_outcome, terminal, history


def _receipt() -> parity_v2.HipFgmresModelCaseParityReceiptV2:
    plan, cpu, _outcome, terminal, history = _scoped_sources()
    child = terminal.receipt
    child_bindings = child.bindings
    bindings = parity_v2.HipFgmresModelCaseParityBindingsV2(
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_id=plan.plan_id,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        symbolic_reuse_hash=plan.symbolic_reuse_hash,
        partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        fgmres_plan_id="HipFgmresPlan:" + "1" * 24,
        fgmres_plan_hash=_hash("fgmres-plan"),
        recurrence_plan_id="HipFgmresRecurrencePlan:" + "2" * 24,
        recurrence_plan_hash=_hash("recurrence-plan"),
        policy_hash=cpu.policy.policy_hash,
        terminal_observation_id=_hash("observation-id"),
        terminal_observation_receipt_hash=_hash("observation-receipt"),
        terminal_outcome_hash=child_bindings.terminal_outcome_hash,
        completion_export_context_id=_hash("export-context"),
        completion_export_receipt_hash=_hash("export-receipt"),
        completion_export_payload_hash=_hash("export-payload"),
        global_context_id=_hash("global-context"),
        global_receipt_hash=_hash("global-receipt"),
        kernel_identity_hash=_hash("kernel-identity"),
        kernel_source_sha256=_hash("kernel-source"),
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_identity_receipt_hash=_hash("device-receipt"),
        runtime_library_sha256=_hash("runtime-library"),
        device_uuid_bytes_hex="0123456789abcdef0123456789abcdef",
        device_pci_bdf="0000:03:00.0",
        cpu_result_hash=cpu.result_hash,
        terminal_metric_parity_id=child.parity_id,
        terminal_metric_parity_receipt_hash=child.receipt_hash,
        cpu_candidate_componentwise_receipt_hash=(
            child_bindings.cpu_candidate_componentwise_receipt_hash
        ),
        cpu_candidate_normwise_receipt_hash=(
            child_bindings.cpu_candidate_normwise_receipt_hash
        ),
        candidate_replay_componentwise_receipt_hash=(
            child_bindings.candidate_replay_componentwise_receipt_hash
        ),
        candidate_replay_normwise_receipt_hash=(
            child_bindings.candidate_replay_normwise_receipt_hash
        ),
        terminal_metric_projection_hash=(
            child_bindings.terminal_metric_projection_hash
        ),
    )
    dimensions = parity_v2.HipFgmresModelCaseParityDimensionsV2(
        global_dof_count=plan.dof_count,
        free_dof_count=len(plan.free_dofs),
        reduced_csr_nnz=len(plan.array("reduced_csr_column_indices")),
        restart_dimension=cpu.policy.restart_dimension,
        max_iterations=cpu.policy.max_iterations,
        maximum_restart_count=(
            cpu.policy.max_iterations + cpu.policy.restart_dimension - 1
        )
        // cpu.policy.restart_dimension,
        populated_restart_row_count=1,
        prior_restart_row_count=0,
        exported_checkpoint_solution_vector_count=0,
        exported_checkpoint_true_residual_vector_count=0,
        solve_record_scalar_count_per_restart=5,
    )
    case_id = canonical_hash(
        {
            "profile": parity_v2.HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2,
            "execution_plan_hash": bindings.execution_plan_hash,
            "policy_hash": bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
            "terminal_metric_parity_receipt_hash": (
                bindings.terminal_metric_parity_receipt_hash
            ),
        }
    )
    draft = parity_v2.HipFgmresModelCaseParityReceiptV2(
        schema_version=parity_v2.HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V2,
        capability_profile=(
            parity_v2.HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V2
        ),
        status="scoped_case_parity_verified",
        evidence_scope=parity_v2.HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V2,
        actual_backend="hip",
        promotion_eligible=False,
        case_id=case_id,
        bindings=bindings,
        dimensions=dimensions,
        discrete=parity_v2._verified_discrete(),
        solution=terminal.roundoff_replay.solution_comparison,
        history=history,
        compatibility=parity_v2.HipFgmresModelCaseParityCompatibilityV2(),
        telemetry=parity_v2.HipFgmresModelCaseParityTelemetryV2(),
        claims=parity_v2.HipFgmresModelCaseParityClaimsV2(),
        receipt_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            parity_v2._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash(
    receipt: parity_v2.HipFgmresModelCaseParityReceiptV2,
    **changes: object,
) -> parity_v2.HipFgmresModelCaseParityReceiptV2:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            parity_v2._receipt_payload(draft, include_hash=False)
        ),
    )


def test_single_terminal_restart_history_exposes_exact_covered_and_missing_scope() -> (
    None
):
    _plan, _cpu, _outcome, terminal, history = _scoped_sources()

    assert history.scope == "exactly_one_populated_terminal_restart_row"
    assert history.cpu_terminal_true_residual_alias_verified
    assert history.hip_terminal_true_residual_alias_verified
    assert history.terminal_true_residual_metrics_delegated_to_normwise_v2
    assert not history.checkpoint_vector_roles_exported
    assert not history.general_restart_history_v2_verified
    assert history.required_next_abi == (
        parity_v2.HIP_FGMRES_MODEL_CASE_PARITY_REQUIRED_HISTORY_ABI_V2
    )
    assert history.missing_evidence == parity_v2._MISSING_HISTORY_EVIDENCE
    assert history.estimated_residual.legacy_fixed_gate_passed
    assert history.solution_update.legacy_fixed_gate_passed
    assert not history.estimated_residual.roundoff_error_model_verified
    assert not history.solution_update.roundoff_error_model_verified
    assert all(row.record_difference_bound_passed for row in terminal.receipt.records)


def test_history_replay_rejects_multirow_alias_and_unmodelled_scalar_drift() -> None:
    _plan, cpu, outcome, terminal, _history = _scoped_sources()
    row = outcome.restart_rows[0]

    def child(changed: object) -> object:
        return parity_v2.replay_hip_fgmres_detached_terminal_metric_parity_v2(
            execution_plan=terminal._execution_plan,
            cpu_result=cpu,
            solution_x=terminal._solution_x,
            true_residual=terminal._true_residual,
            outcome=changed,
        )

    multi_outcome = replace(outcome, restart_rows=(row, replace(row, slot_index=2)))
    with pytest.raises(parity_v2.HipFgmresModelCaseParityV2Error) as multi:
        parity_v2.replay_hip_fgmres_single_terminal_restart_history_v2(
            cpu_result=cpu,
            outcome=multi_outcome,
            terminal_metric_parity=child(multi_outcome),
        )
    assert multi.value.code == "hip_fgmres_model_case_parity_v2_discrete_mismatch"

    alias_outcome = replace(
        outcome,
        restart_rows=(
            replace(
                row,
                true_residual_l2=row.true_residual_l2
                + max(1.0e-6, abs(row.true_residual_l2)),
            ),
        ),
    )
    with pytest.raises(parity_v2.HipFgmresModelCaseParityV2Error) as alias:
        parity_v2.replay_hip_fgmres_single_terminal_restart_history_v2(
            cpu_result=cpu,
            outcome=alias_outcome,
            terminal_metric_parity=child(alias_outcome),
        )
    assert (
        alias.value.code == "hip_fgmres_model_case_parity_v2_hip_terminal_alias_invalid"
    )

    scalar_outcome = replace(
        outcome,
        restart_rows=(
            replace(
                row,
                estimated_residual_l2=row.estimated_residual_l2 + 1.0,
            ),
        ),
    )
    with pytest.raises(parity_v2.HipFgmresModelCaseParityV2Error) as scalar:
        parity_v2.replay_hip_fgmres_single_terminal_restart_history_v2(
            cpu_result=cpu,
            outcome=scalar_outcome,
            terminal_metric_parity=child(scalar_outcome),
        )
    assert scalar.value.code == (
        "hip_fgmres_model_case_parity_v2_legacy_history_metric_mismatch"
    )


def test_v2_receipt_schema_is_strict_scoped_and_nonpromoting() -> None:
    receipt = _receipt()
    assert parity_v2.validate_hip_fgmres_model_case_parity_receipt_v2(receipt) is (
        receipt
    )
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(
        receipt.to_dict()
    )
    assert receipt.actual_backend == "hip"
    assert receipt.dimensions.populated_restart_row_count == 1
    assert receipt.dimensions.prior_restart_row_count == 0
    assert not receipt.claims.general_restart_history_metric_v2_verified
    assert not receipt.claims.result_ir_ready
    assert not receipt.claims.promotion_eligible


def test_v2_receipt_rejects_coherent_history_relabel_and_v1_wire_stays_frozen() -> None:
    receipt = _receipt()
    forged_metric = replace(
        receipt.history.estimated_residual,
        absolute_difference=receipt.history.estimated_residual.absolute_difference
        + 1.0,
    )
    forged_history = replace(receipt.history, estimated_residual=forged_metric)
    forged = _rehash(receipt, history=forged_history)
    with pytest.raises(parity_v2.HipFgmresModelCaseParityV2Error) as caught:
        parity_v2.validate_hip_fgmres_model_case_parity_receipt_v2(forged)
    assert caught.value.code == (
        "hip_fgmres_model_case_parity_v2_history_metric_replay_invalid"
    )

    assert hashlib.sha256(V1_SCHEMA.read_bytes()).hexdigest() == (
        "4da38578a99ba1c479f32b66f62ef8c1771b4e734f947c1a0b24e1648066f050"
    )
