"""Actual-gfx1030 parity, transfer, and launch/fence audit of fixed-suite v2."""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    attest_hip_fgmres_model_case_parity_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_iteration_host_transfer_audit_v1 import (
    open_hip_fgmres_iteration_host_transfer_audit_v1,
    validate_hip_fgmres_iteration_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_audited_parity_v2 import (
    attest_hip_fgmres_model_family_audited_parity_v2,
    validate_hip_fgmres_model_family_audited_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_host_transfer_audit_v1 import (
    attest_hip_fgmres_model_family_host_transfer_audit_v1,
    validate_hip_fgmres_model_family_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
    attest_hip_fgmres_model_family_coverage_v2,
    validate_hip_fgmres_model_family_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_result_ir_disposition_v1 import (
    HipFgmresModelFamilyResultIRNotIssuedObservationV1,
    HipFgmresModelFamilyResultIRReadyObservationV1,
    attest_hip_fgmres_model_family_result_ir_disposition_v1,
    validate_hip_fgmres_model_family_result_ir_disposition_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_diagnostic_ir_v1 import (
    attest_hip_fgmres_model_family_diagnostic_ir_v1,
    validate_hip_fgmres_model_family_diagnostic_ir_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_launch_fence_audit_v1 import (
    open_hip_fgmres_recurrence_launch_fence_audit_v1,
    validate_hip_fgmres_recurrence_launch_fence_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    build_hip_fgmres_result_ir_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_diagnostic_ir_v1 import (
    build_hip_fgmres_diagnostic_ir_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    observe_hip_fgmres_terminal_outcome_v1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    attest_hip_device_identity_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    solve_cpu_fgmres_reference_v1,
)

from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_PARITY_V2_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_V2_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_RESULT_IR_DISPOSITION_V1_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_V1_HARDWARE",
        )
    )


@dataclass(slots=True)
class _LiveCaseResources:
    chain: Any
    sealed: Any
    global_open: Any
    audit_context: Any
    ordinal_context: Any

    def close(self) -> None:
        _run_all_cleanup_steps(
            (
                lambda: (
                    self.ordinal_context.close()
                    if self.ordinal_context is not None
                    else None
                ),
                lambda: (
                    self.audit_context.close()
                    if self.audit_context is not None
                    else None
                ),
                lambda: (
                    self.global_open.context.close()
                    if self.global_open is not None
                    and not self.global_open.context.closed
                    else None
                ),
                lambda: (
                    self.sealed.context.close()
                    if self.sealed is not None and not self.sealed.context.closed
                    else None
                ),
                self.chain.close,
            )
        )


def _run_all_cleanup_steps(steps: tuple[Any, ...]) -> None:
    errors: list[BaseException] = []
    for step in steps:
        try:
            step()
        except BaseException as exc:
            errors.append(exc)
    if errors:
        first = errors[0]
        _attach_cleanup_failures(first, errors[1:])
        raise first


def _attach_cleanup_failures(
    primary: BaseException,
    cleanup_errors: list[BaseException],
) -> None:
    if not cleanup_errors:
        return
    try:
        existing = getattr(primary, "_engine_v2_cleanup_failures", ())
        if type(existing) is not tuple or any(
            not isinstance(exc, BaseException) for exc in existing
        ):
            existing = ()
        setattr(
            primary,
            "_engine_v2_cleanup_failures",
            existing + tuple(cleanup_errors),
        )
    except Exception:
        # Cleanup diagnostics must never replace the primary failure.
        return


def _execute_live_case(
    slot: Any,
    architecture: str,
    required: bool,
) -> tuple[Any, Any, Any, Any]:
    chain = sealed = global_open = audit_context = ordinal_context = None
    audit_opens: list[Any] = []
    ordinal_opens: list[Any] = []

    def open_audits_before_enqueue(canonical: Any) -> None:
        transfer = open_hip_fgmres_iteration_host_transfer_audit_v1(canonical)
        try:
            ordinal = open_hip_fgmres_recurrence_launch_fence_audit_v1(canonical)
        except BaseException as primary_error:
            try:
                transfer.context.close()
            except BaseException as cleanup_error:
                _attach_cleanup_failures(primary_error, [cleanup_error])
            raise
        audit_opens.append(transfer.context)
        ordinal_opens.append(ordinal.context)

    def close_audits_before_chain_cleanup() -> None:
        _run_all_cleanup_steps(
            (
                *(opened.close for opened in reversed(ordinal_opens)),
                *(opened.close for opened in reversed(audit_opens)),
            )
        )

    try:
        chain, predecessor_capability = _open_canonical_chain(
            model=slot.model,
            architecture=architecture,
            required=required,
            policy=slot.policy,
            load_pattern_id=slot.execution_plan.load_pattern_id,
            before_canonical_enqueue=open_audits_before_enqueue,
            before_chain_cleanup=close_audits_before_chain_cleanup,
        )
        assert len(audit_opens) == 1 and len(ordinal_opens) == 1
        audit_context = audit_opens[0]
        ordinal_context = ordinal_opens[0]
        source_fgmres_plan = chain.recurrence._source_fgmres_plan
        source_execution_plan = source_fgmres_plan._source_execution_plan
        assert source_execution_plan.plan_hash == slot.execution_plan.plan_hash
        assert source_fgmres_plan.plan_hash == slot.fgmres_plan.plan_hash
        assert chain.recurrence.plan_hash == slot.recurrence_plan.plan_hash

        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        global_pending = global_open.context.enqueue_remaining_global_recurrence()
        completion = global_open.context.synchronize(global_pending)
        ordinal_result = ordinal_context.seal_terminal_fence(
            global_open.context,
            completion,
        )
        validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
            ordinal_result,
            expected_context=ordinal_context,
        )
        audit_result = audit_context.export_completion_buffers(
            global_open.context,
            completion,
        )
        validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
            audit_result,
            expected_context=audit_context,
        )
        export_context = audit_result.completion_export_context
        export_result = audit_result.completion_export_result
        observation = observe_hip_fgmres_terminal_outcome_v1(
            export_result,
            expected_export_context=export_context,
        )
        cpu_result = solve_cpu_fgmres_reference_v1(
            source_execution_plan,
            source_fgmres_plan.policy,
        )
        assert cpu_result.result_hash == slot.cpu_result.result_hash
        loaded_runtime = chain.live._loaded_runtime
        assert loaded_runtime is not None
        device_identity = attest_hip_device_identity_v1(
            loaded_runtime,
            device_ordinal=0,
            expected_compiled_architecture=architecture,
        )
        parity = attest_hip_fgmres_model_case_parity_v1(
            cpu_result,
            observation,
            device_identity,
        )
        resources = _LiveCaseResources(
            chain=chain,
            sealed=sealed,
            global_open=global_open,
            audit_context=audit_context,
            ordinal_context=ordinal_context,
        )
        return resources, parity, audit_context, ordinal_context
    except BaseException as primary_error:
        try:
            _run_all_cleanup_steps(
                (
                    close_audits_before_chain_cleanup,
                    lambda: (
                        global_open.context.close()
                        if global_open is not None and not global_open.context.closed
                        else None
                    ),
                    lambda: (
                        sealed.context.close()
                        if sealed is not None and not sealed.context.closed
                        else None
                    ),
                    lambda: chain.close() if chain is not None else None,
                )
            )
        except BaseException as cleanup_error:
            _attach_cleanup_failures(primary_error, [cleanup_error])
        raise


def test_native_gfx1030_replays_and_audits_all_ten_cells_in_one_live_aggregate() -> (
    None
):
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    registry = load_hip_fgmres_fixture_registry_v1()
    resources: list[_LiveCaseResources] = []
    cases: list[Any] = []
    audit_contexts: list[Any] = []
    ordinal_contexts: list[Any] = []
    result_ir_bridges: list[Any] = []
    diagnostic_ir_bridges: list[Any] = []
    family_disposition = None
    family_diagnostic = None
    try:
        for slot_id in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2:
            print(f"actual-gfx1030 fixed-suite cell: {slot_id}", flush=True)
            opened, case, audit_context, ordinal_context = _execute_live_case(
                registry.slot(slot_id),
                architecture,
                required,
            )
            resources.append(opened)
            cases.append(case)
            audit_contexts.append(audit_context)
            ordinal_contexts.append(ordinal_context)
            if registry.slot(slot_id).cpu_result.status == "converged":
                result_ir_bridges.append(
                    build_hip_fgmres_result_ir_v2(
                        case,
                        result_id=f"Result.hip-fgmres-fixed-suite.{slot_id}.v2",
                    )
                )
            else:
                assert registry.slot(slot_id).cpu_result.status == "max_iterations"
                diagnostic_ir_bridges.append(
                    build_hip_fgmres_diagnostic_ir_v1(
                        case,
                        diagnostic_id=(
                            f"Diagnostic.hip-fgmres-fixed-suite.{slot_id}.v1"
                        ),
                    )
                )

        family = attest_hip_fgmres_model_family_coverage_v2(tuple(cases))
        validate_hip_fgmres_model_family_parity_result_v2(
            family,
            expected_case_results=tuple(cases),
        )
        receipt = family.receipt
        assert receipt.status == (
            "primary_gfx1030_fixed_suite_complete_external_gfx1100_pending"
        )
        assert receipt.coverage.validated_input_case_count == 10
        assert receipt.coverage.covered_matrix_cell_count == 10
        assert receipt.coverage.completed_architecture_bases == ("gfx1030",)
        assert receipt.coverage.incomplete_architecture_bases == ("gfx1100",)
        assert receipt.claims.primary_gfx1030_fixed_suite_complete
        assert not receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
        assert not receipt.claims.full_model_family_parity_verified
        assert not receipt.claims.multiarchitecture_parity_verified
        assert not receipt.claims.signed_evidence
        assert not receipt.claims.result_ir_verified
        assert not receipt.claims.iteration_host_copy_zero_verified
        assert not receipt.claims.speedup_verified
        assert not receipt.claims.end_to_end_o_n_verified
        assert not receipt.claims.commercial_ready
        assert not receipt.promotion_eligible

        composed = attest_hip_fgmres_model_family_host_transfer_audit_v1(
            family,
            tuple(audit_contexts),
        )
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
            composed,
            expected_family_result=family,
            expected_audit_contexts=tuple(audit_contexts),
        )
        audit_receipt = composed.receipt
        assert audit_receipt.totals.paired_slot_count == 10
        assert audit_receipt.totals.recurrence_program_copy_attempt_count == 0
        assert audit_receipt.totals.completion_export_blocking_d2h_attempt_count == 30
        assert audit_receipt.totals.completion_export_blocking_d2h_success_count == 30
        assert audit_receipt.totals.completion_export_byte_count == 4408
        assert all(
            row.recurrence_program_copy_attempt_count == 0
            and row.completion_export_blocking_d2h_attempt_count == 3
            for row in audit_receipt.observations
        )
        assert audit_receipt.claims.exact_gfx1030_registered_ten_slot_coverage_bound
        assert audit_receipt.claims.case_parity_and_audit_same_export_identity_bound
        assert not audit_receipt.claims.external_gfx1100_fixed_suite_audited
        assert not audit_receipt.claims.iteration_host_copy_zero_proven
        assert not audit_receipt.claims.standalone_receipt_provenance_authenticity
        assert not audit_receipt.claims.commercial_ready
        assert not audit_receipt.promotion_eligible

        audited = attest_hip_fgmres_model_family_audited_parity_v2(
            composed,
            tuple(ordinal_contexts),
        )
        validate_hip_fgmres_model_family_audited_parity_result_v2(
            audited,
            expected_transfer_composition_result=composed,
            expected_ordinal_contexts=tuple(ordinal_contexts),
        )
        audited_receipt = audited.receipt
        totals = audited_receipt.totals
        assert totals.paired_slot_count == 10
        assert totals.recurrence_program_copy_attempt_count == 0
        assert totals.completion_export_blocking_d2h_attempt_count == 30
        assert totals.completion_export_blocking_d2h_success_count == 30
        assert totals.completion_export_byte_count == 4408
        assert totals.ordinal_memset_attempt_count == 80
        assert totals.ordinal_memset_success_count == 80
        assert totals.ordinal_memset_rejected_count == 0
        assert totals.ordinal_memset_ambiguous_count == 0
        assert totals.ordinal_memset_in_flight_count == 0
        assert totals.ordinal_launch_attempt_count == 1230
        assert totals.ordinal_launch_success_count == 1230
        assert totals.ordinal_launch_rejected_count == 0
        assert totals.ordinal_launch_ambiguous_count == 0
        assert totals.ordinal_launch_in_flight_count == 0
        assert totals.ordinal_fence_attempt_count == 30
        assert totals.ordinal_fence_success_count == 30
        assert totals.ordinal_fence_rejected_count == 0
        assert totals.ordinal_fence_ambiguous_count == 0
        assert totals.ordinal_fence_in_flight_count == 0
        claims = audited_receipt.claims
        assert claims.three_retained_authority_families_replayed
        assert claims.exact_gfx1030_registered_ten_slot_coverage_bound
        assert claims.transfer_and_ordinal_lineage_cross_bound
        assert claims.per_slot_bound_runtime_recurrence_copy_attempt_zero
        assert claims.per_slot_fixed_recurrence_descriptor_order_replayed
        assert not claims.external_gfx1100_fixed_suite_audited
        assert not claims.iteration_host_copy_zero_proven
        assert not claims.standalone_receipt_provenance_authenticity
        assert not claims.hostile_same_process_mutation_or_interposition_resistance
        assert not claims.result_ir_verified
        assert not claims.commercial_ready
        assert not audited_receipt.promotion_eligible

        family_disposition = attest_hip_fgmres_model_family_result_ir_disposition_v1(
            audited,
            tuple(result_ir_bridges),
        )
        result_receipt = family_disposition.receipt
        result_totals = result_receipt.totals
        assert tuple(
            row.slot_id
            for row in result_receipt.observations
            if type(row) is HipFgmresModelFamilyResultIRReadyObservationV1
        ) == (
            "frame_single_axial",
            "frame_single_weak_axis_bending",
            "frame_single_strong_axis_bending",
            "frame_single_torsion",
            "frame_serial_later_column",
            "truss_single_axial",
            "recurrence_initial_or_early_terminal",
        )
        assert tuple(
            row.slot_id
            for row in result_receipt.observations
            if type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1
        ) == (
            "frame_single_rotated_local_axis_bending",
            "recurrence_later_restart_partial_final_cycle",
            "recurrence_exact_full_final_cycle_guard",
        )
        assert all(
            row.disposition == "ready_result_ir_v2"
            and row.result_array_count == 6
            and row.additional_device_operation_count == 0
            and row.additional_d2h_operation_count == 0
            and row.additional_solve_count == 0
            and row.additional_export_count == 0
            and row.fallback_count == 0
            for row in result_receipt.observations
            if type(row) is HipFgmresModelFamilyResultIRReadyObservationV1
        )
        assert all(
            row.disposition == "not_issued_nonconverged"
            and row.result_ir_absence_reason == "source_not_converged"
            and row.result_ir_materialized is False
            and row.solver_tolerance_passed is False
            and row.authoritative_plan_tolerance_passed is False
            for row in result_receipt.observations
            if type(row) is HipFgmresModelFamilyResultIRNotIssuedObservationV1
        )
        assert result_totals.required_slot_count == 10
        assert result_totals.ready_result_ir_v2_count == 7
        assert result_totals.not_issued_nonconverged_count == 3
        assert result_totals.package_global_dof_count == 162
        assert result_totals.package_element_count == 17
        assert result_totals.package_free_dof_count == 97
        assert result_totals.package_csr_nnz == 2196
        assert result_totals.ready_global_dof_count == 90
        assert result_totals.ready_element_count == 8
        assert result_totals.ready_free_dof_count == 43
        assert result_totals.ready_csr_nnz == 1116
        assert result_totals.ready_result_array_count == 42
        assert result_totals.ready_result_array_byte_count == 3336
        assert result_totals.ready_detached_raw_payload_byte_count == 688
        assert result_totals.upstream_completion_export_blocking_d2h_attempt_count == 30
        assert result_totals.upstream_completion_export_blocking_d2h_success_count == 30
        assert result_totals.upstream_completion_export_blocking_d2h_failure_count == 0
        assert result_totals.upstream_completion_export_byte_count == 4408
        assert result_totals.result_ir_projection_additional_device_operation_count == 0
        assert result_totals.result_ir_projection_additional_d2h_operation_count == 0
        assert result_totals.result_ir_projection_additional_solve_count == 0
        assert result_totals.result_ir_projection_additional_export_count == 0
        assert result_totals.result_ir_projection_fallback_count == 0
        assert len(family_disposition.result_ir_bridges) == 7
        for bridge in family_disposition.result_ir_bridges:
            provenance = bridge.receipt.source_provenance
            assert provenance.actual_backend == "hip"
            assert provenance.runtime_architecture_base == "gfx1030"
            assert provenance.additional_device_operation_count == 0
            assert provenance.additional_d2h_operation_count == 0
            assert provenance.additional_solve_count == 0
            assert provenance.additional_export_count == 0
            assert provenance.fallback_count == 0
        result_claims = result_receipt.claims
        assert result_claims.seven_converged_result_ir_v2_verified
        assert result_claims.three_nonconverged_result_ir_v2_not_issued
        assert not result_claims.exact_ten_slot_result_ir_v2_ready
        assert not result_claims.external_gfx1100_result_ir_verified
        assert not result_claims.iteration_host_copy_zero_proven
        assert not result_claims.end_to_end_o_n_verified
        assert not result_claims.performance_or_speedup_proven
        assert not result_claims.signed_evidence
        assert not result_claims.commercial_ready
        assert not result_receipt.promotion_eligible

        family_diagnostic = attest_hip_fgmres_model_family_diagnostic_ir_v1(
            audited,
            family_disposition,
            tuple(reversed(diagnostic_ir_bridges)),
        )
        diagnostic_receipt = family_diagnostic.receipt
        diagnostic_totals = diagnostic_receipt.totals
        assert tuple(row.slot_id for row in diagnostic_receipt.observations) == (
            "frame_single_rotated_local_axis_bending",
            "recurrence_later_restart_partial_final_cycle",
            "recurrence_exact_full_final_cycle_guard",
        )
        assert diagnostic_totals.required_diagnostic_slot_count == 3
        assert diagnostic_totals.ready_result_ir_v2_count == 7
        assert diagnostic_totals.ready_diagnostic_ir_v1_count == 3
        assert diagnostic_totals.diagnostic_global_dof_count == 72
        assert diagnostic_totals.diagnostic_element_count == 9
        assert diagnostic_totals.diagnostic_free_dof_count == 54
        assert diagnostic_totals.diagnostic_csr_nnz == 1080
        assert diagnostic_totals.diagnostic_array_count == 9
        assert diagnostic_totals.diagnostic_array_byte_count == 1584
        assert (
            diagnostic_totals.diagnostic_detached_raw_export_payload_byte_count == 1872
        )
        assert (
            diagnostic_totals.upstream_completion_export_blocking_d2h_attempt_count == 9
        )
        assert (
            diagnostic_totals.upstream_completion_export_blocking_d2h_success_count == 9
        )
        assert (
            diagnostic_totals.upstream_completion_export_blocking_d2h_failure_count == 0
        )
        assert diagnostic_totals.upstream_completion_export_byte_count == 1872
        assert diagnostic_totals.sparse_residual_replay_count == 3
        assert (
            diagnostic_totals.diagnostic_projection_additional_device_operation_count
            == 0
        )
        assert (
            diagnostic_totals.diagnostic_projection_additional_d2h_operation_count == 0
        )
        assert diagnostic_totals.diagnostic_projection_additional_solve_count == 0
        assert diagnostic_totals.diagnostic_projection_additional_export_count == 0
        assert diagnostic_totals.diagnostic_projection_fallback_count == 0
        assert diagnostic_totals.diagnostic_projection_state_commit_count == 0
        assert len(family_diagnostic.diagnostic_bridges) == 3
        diagnostic_claims = diagnostic_receipt.claims
        assert diagnostic_claims.source_result_ir_disposition_replayed_unchanged
        assert diagnostic_claims.seven_converged_result_ir_v2_preserved
        assert diagnostic_claims.three_nonconverged_diagnostic_ir_v1_verified
        assert diagnostic_claims.partial_iterates_preserved
        assert diagnostic_claims.evaluated_trial_states_verified
        assert diagnostic_claims.nonconverged_state_commit_zero
        assert diagnostic_claims.sparse_residual_replayed_for_each_diagnostic
        assert not diagnostic_claims.exact_ten_slot_result_ir_v2_ready
        assert not diagnostic_claims.all_ten_solution_ready
        assert not diagnostic_claims.all_ten_converged
        assert not diagnostic_claims.diagnostic_ir_is_solution_result
        assert not diagnostic_claims.nonconverged_state_committed
        assert not diagnostic_claims.external_gfx1100_diagnostic_ir_verified
        assert not diagnostic_claims.iteration_host_copy_zero_proven
        assert not diagnostic_claims.standalone_receipt_provenance_authenticity
        assert not diagnostic_claims.end_to_end_o_n_verified
        assert not diagnostic_claims.performance_or_speedup_proven
        assert not diagnostic_claims.commercial_ready
        assert not diagnostic_claims.promotion_eligible
        assert not diagnostic_receipt.promotion_eligible
    finally:
        cleanup_errors: list[BaseException] = []
        for opened in reversed(resources):
            try:
                opened.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            active_error = sys.exc_info()[1]
            if active_error is not None:
                _attach_cleanup_failures(active_error, cleanup_errors)
            else:
                first = cleanup_errors[0]
                _attach_cleanup_failures(first, cleanup_errors[1:])
                raise first
    assert family_disposition is not None
    assert family_diagnostic is not None
    assert (
        validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
            family_disposition
        )
        is family_disposition
    )
    assert (
        validate_hip_fgmres_model_family_diagnostic_ir_result_v1(family_diagnostic)
        is family_diagnostic
    )
