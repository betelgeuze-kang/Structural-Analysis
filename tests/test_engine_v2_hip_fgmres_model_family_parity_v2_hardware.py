"""Actual-gfx1030 replay and transfer audit of all fixed-suite v2 cells."""

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
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_host_transfer_audit_v1 import (
    attest_hip_fgmres_model_family_host_transfer_audit_v1,
    validate_hip_fgmres_model_family_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
    attest_hip_fgmres_model_family_coverage_v2,
    validate_hip_fgmres_model_family_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
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
        )
    )


@dataclass(slots=True)
class _LiveCaseResources:
    chain: Any
    sealed: Any
    global_open: Any
    audit_context: Any

    def close(self) -> None:
        _run_all_cleanup_steps(
            (
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
        setattr(
            primary,
            "_engine_v2_cleanup_failures",
            tuple(cleanup_errors),
        )
    except Exception:
        # Cleanup diagnostics must never replace the primary failure.
        return


def _execute_live_case(
    slot: Any,
    architecture: str,
    required: bool,
) -> tuple[Any, Any, Any]:
    chain = sealed = global_open = audit_context = None
    audit_opens: list[Any] = []

    def open_audit_before_enqueue(canonical: Any) -> None:
        opened = open_hip_fgmres_iteration_host_transfer_audit_v1(canonical)
        audit_opens.append(opened.context)

    try:
        chain, predecessor_capability = _open_canonical_chain(
            model=slot.model,
            architecture=architecture,
            required=required,
            policy=slot.policy,
            load_pattern_id=slot.execution_plan.load_pattern_id,
            before_canonical_enqueue=open_audit_before_enqueue,
        )
        assert len(audit_opens) == 1
        audit_context = audit_opens[0]
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
        )
        return resources, parity, audit_context
    except BaseException as primary_error:
        try:
            audit_steps = tuple(opened.close for opened in reversed(audit_opens))
            _run_all_cleanup_steps(
                (
                    *audit_steps,
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
    try:
        for slot_id in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2:
            print(f"actual-gfx1030 fixed-suite cell: {slot_id}", flush=True)
            opened, case, audit_context = _execute_live_case(
                registry.slot(slot_id),
                architecture,
                required,
            )
            resources.append(opened)
            cases.append(case)
            audit_contexts.append(audit_context)

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
