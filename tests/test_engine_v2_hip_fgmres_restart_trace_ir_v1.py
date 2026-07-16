from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_general_history_parity_v2 as parity_v2,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_restart_trace_ir_v1 as trace_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_restart_trace_ir_v1 import (
    HipFgmresRestartTraceClaimsV1,
    HipFgmresRestartTraceIRV1Error,
    build_hip_fgmres_restart_trace_ir_receipt_v1,
    validate_hip_fgmres_restart_trace_ir_receipt_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _hash(label: str) -> str:
    return canonical_hash({"label": label})


def _vector(
    role: str,
    *,
    row_index: int,
) -> parity_v2.HipFgmresHistoryVectorComparisonV2:
    return parity_v2.HipFgmresHistoryVectorComparisonV2(
        name=role,
        value_count=4,
        reference_sha256=_hash(f"{role}-cpu-{row_index}"),
        candidate_sha256=_hash(f"{role}-hip-{row_index}"),
        maximum_absolute_error=0.0,
        difference_l2=0.0,
        reference_l2=float(row_index + 1),
        relative_l2_error=0.0,
        fixed_absolute_tolerance=1.0e-12,
        fixed_relative_tolerance=1.0e-8,
        fixed_componentwise_gate_passed=True,
    )


def _metric(
    name: str,
    *,
    row_index: int,
) -> parity_v2.HipFgmresHistoryScalarEnvelopeV2:
    value = float(row_index + 1)
    return parity_v2.HipFgmresHistoryScalarEnvelopeV2(
        name=name,
        cpu_value=value,
        hip_value=value,
        absolute_difference=0.0,
        vector_transport_bound=0.0,
        cpu_estimator_or_replay_gap=0.0,
        hip_estimator_or_replay_gap=0.0,
        fp_roundoff_guard=1.0e-15,
        total_bound=1.0e-15,
        maximum_bound_ratio=0.0,
    )


def _row(index: int) -> parity_v2.HipFgmresGeneralHistoryRowV2:
    return parity_v2.HipFgmresGeneralHistoryRowV2(
        restart_index=index + 1,
        slot_index=index + 1,
        column_index=0,
        start_iteration=index,
        end_iteration=index + 1,
        arnoldi_step_count=1,
        reorthogonalization_count=0,
        termination_hint="maximum_iterations" if index == 1 else "restart_completed",
        flags=1,
        solution=_vector("checkpoint_solution", row_index=index),
        true_residual=_vector("checkpoint_true_residual", row_index=index),
        residual_roundoff_receipt_hash=_hash(f"roundoff-{index}"),
        residual_roundoff_maximum_componentwise_ratio=0.0,
        true_residual_l2=_metric("true_residual_l2", row_index=index),
        true_residual_linf=_metric("true_residual_linf", row_index=index),
        scaled_true_residual=_metric("scaled_true_residual", row_index=index),
        estimated_residual_l2=_metric("estimated_residual_l2", row_index=index),
        solution_update_l2=_metric("solution_update_l2", row_index=index),
    )


def _source_receipt(
    row_count: int = 2,
) -> parity_v2.HipFgmresGeneralHistoryParityReceiptV2:
    rows = tuple(_row(index) for index in range(row_count))
    bindings = parity_v2.HipFgmresGeneralHistoryParityBindingsV2(
        execution_plan_hash=_hash("plan"),
        operator_hash=_hash("operator"),
        policy_hash=_hash("policy"),
        cpu_checkpoint_history_result_hash=_hash("cpu-history"),
        cpu_base_result_hash=_hash("cpu-base"),
        completion_export_v2_context_id=_hash("completion-context"),
        completion_export_v2_receipt_hash=_hash("completion-receipt"),
        completion_export_v2_payload_hash=_hash("completion-payload"),
        retained_completion_export_v1_receipt_hash=_hash("base-export"),
        checkpoint_history_export_v1_receipt_hash=_hash("history-export"),
        terminal_observation_receipt_hash=_hash("terminal-observation"),
        global_context_id=_hash("global-context"),
        history_plan_hash=_hash("history-plan"),
        history_blob_abi_hash=_hash("history-abi"),
        recurrence_plan_hash=_hash("recurrence-plan"),
        recurrence_kernel_identity_hash=_hash("recurrence-kernel"),
        architecture="gfx1030",
        device_ordinal=0,
    )
    dimensions = parity_v2.HipFgmresGeneralHistoryParityDimensionsV2(
        free_dof_count=4,
        maximum_restart_count=2,
        populated_restart_count=row_count,
        exported_checkpoint_solution_vector_count=row_count,
        exported_checkpoint_true_residual_vector_count=row_count,
        compared_scalar_count=5 * row_count,
        residual_roundoff_receipt_count=row_count,
    )
    telemetry = parity_v2.HipFgmresGeneralHistoryParityTelemetryV2(
        solve_record_restart_row_inspection_count=2,
        checkpoint_vector_pair_comparison_count=row_count,
        gpu_tree_metric_replay_count=4 * row_count,
        scalar_envelope_count=5 * row_count,
        residual_roundoff_receipt_count=row_count,
    )
    draft = parity_v2.HipFgmresGeneralHistoryParityReceiptV2(
        schema_version=parity_v2.HIP_FGMRES_GENERAL_HISTORY_PARITY_SCHEMA_VERSION_V2,
        capability_profile=(
            parity_v2.HIP_FGMRES_GENERAL_HISTORY_PARITY_CAPABILITY_PROFILE_V2
        ),
        status="general_multi_restart_history_v2_verified",
        evidence_scope=parity_v2.HIP_FGMRES_GENERAL_HISTORY_PARITY_EVIDENCE_SCOPE_V2,
        actual_backend="hip",
        promotion_eligible=False,
        parity_id=_hash("parity-id"),
        bindings=bindings,
        dimensions=dimensions,
        rows=rows,
        telemetry=telemetry,
        claims=parity_v2.HipFgmresGeneralHistoryParityClaimsV2(),
        receipt_hash=_hash("draft"),
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(
            parity_v2._receipt_payload(draft, include_hash=False)
        ),
    )
    return parity_v2.validate_hip_fgmres_general_history_parity_receipt_v2(receipt)


@pytest.mark.parametrize("row_count", [0, 2])
def test_restart_trace_projects_general_history_without_result_semantics(
    row_count: int,
) -> None:
    source = _source_receipt(row_count)

    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(source)

    assert validate_hip_fgmres_restart_trace_ir_receipt_v1(trace) is trace
    assert trace.dimensions.trace_row_count == row_count
    assert trace.dimensions.referenced_vector_count == 2 * row_count
    assert trace.dimensions.referenced_scalar_metric_count == 5 * row_count
    assert trace.dimensions.embedded_numeric_vector_byte_count == 0
    assert trace.dimensions.result_array_count == 0
    assert trace.summary.terminal_trace_row_count == (0 if row_count == 0 else 1)
    assert trace.claims.diagnostic_restart_trace_ir_v1_ready is True
    assert trace.claims.result_ir_semantics_separated is True
    assert trace.claims.final_solution_authority_absent is True
    assert trace.claims.solution_ready is False
    assert trace.claims.result_ir_ready is False
    assert trace.claims.result_ir_issuance_authorized is False
    assert trace.telemetry.result_ir_build_count == 0
    assert trace.telemetry.additional_device_operation_count == 0
    assert trace.telemetry.additional_d2h_operation_count == 0
    assert trace.bindings.source_parity_receipt_hash == source.receipt_hash
    assert [row.terminal_row_in_trace for row in trace.rows] == (
        [] if row_count == 0 else [False, True]
    )


def test_restart_trace_preserves_every_source_row_hash_and_envelope() -> None:
    source = _source_receipt()

    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(source)

    assert [row.source_history_row_hash for row in trace.rows] == [
        canonical_hash(row.to_dict()) for row in source.rows
    ]
    assert [row.end_iteration for row in trace.rows] == [1, 2]
    assert all(row.solution.cpu_reference_sha256 for row in trace.rows)
    assert all(row.true_residual.hip_candidate_sha256 for row in trace.rows)
    assert all(row.true_residual_l2.bound_passed for row in trace.rows)
    assert all(row.solution_update_l2.outward_rounding_used for row in trace.rows)


def test_restart_trace_preserves_residual_gate_as_diagnostic_not_authority() -> None:
    source = _source_receipt()
    residual = replace(
        source.rows[0].true_residual,
        fixed_componentwise_gate_passed=False,
    )
    rows = (replace(source.rows[0], true_residual=residual), source.rows[1])
    changed = replace(source, rows=rows)
    changed = replace(
        changed,
        receipt_hash=canonical_hash(
            parity_v2._receipt_payload(changed, include_hash=False)
        ),
    )
    parity_v2.validate_hip_fgmres_general_history_parity_receipt_v2(changed)

    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(changed)

    assert trace.rows[0].solution.fixed_componentwise_gate_passed is True
    assert trace.rows[0].true_residual.fixed_componentwise_gate_passed is False
    assert trace.rows[0].residual_roundoff_maximum_componentwise_ratio == 0.0


def test_restart_trace_rejects_row_tamper_even_with_rehashed_receipt() -> None:
    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(_source_receipt())
    changed_row = replace(trace.rows[0], end_iteration=9)
    changed = replace(trace, rows=(changed_row, trace.rows[1]))
    changed = replace(
        changed,
        receipt_hash=canonical_hash(
            trace_v1._receipt_payload(changed, include_hash=False)
        ),
    )

    with pytest.raises(HipFgmresRestartTraceIRV1Error) as error:
        validate_hip_fgmres_restart_trace_ir_receipt_v1(changed)

    assert error.value.code == "hip_fgmres_restart_trace_source_row_hash_invalid"


def test_restart_trace_forbids_coherently_rehashed_result_ir_claim() -> None:
    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(_source_receipt())
    claims = replace(HipFgmresRestartTraceClaimsV1(), result_ir_ready=True)
    changed = replace(trace, claims=claims)
    changed = replace(
        changed,
        receipt_hash=canonical_hash(
            trace_v1._receipt_payload(changed, include_hash=False)
        ),
    )

    with pytest.raises(HipFgmresRestartTraceIRV1Error) as error:
        validate_hip_fgmres_restart_trace_ir_receipt_v1(changed)

    assert error.value.code in {
        "hip_fgmres_restart_trace_schema_invalid",
        "hip_fgmres_restart_trace_semantics_invalid",
    }


def test_restart_trace_rejects_noncanonical_rows_container() -> None:
    trace = build_hip_fgmres_restart_trace_ir_receipt_v1(_source_receipt())
    changed = replace(trace, rows=list(trace.rows))  # type: ignore[arg-type]

    with pytest.raises(HipFgmresRestartTraceIRV1Error) as error:
        validate_hip_fgmres_restart_trace_ir_receipt_v1(changed)

    assert error.value.code == "hip_fgmres_restart_trace_rows_type_invalid"


def test_restart_trace_rejects_non_general_history_source() -> None:
    with pytest.raises(HipFgmresRestartTraceIRV1Error) as error:
        build_hip_fgmres_restart_trace_ir_receipt_v1(object())  # type: ignore[arg-type]

    assert error.value.code == "hip_fgmres_restart_trace_source_receipt_type_invalid"
