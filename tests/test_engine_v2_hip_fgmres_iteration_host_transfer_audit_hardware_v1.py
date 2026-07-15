"""Actual-gfx1030 gate for the bound-runtime recurrence copy audit."""

from __future__ import annotations

import os
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    HipFgmresCanonicalPredecessorExecutionContextV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_iteration_host_transfer_audit_v1 import (
    open_hip_fgmres_iteration_host_transfer_audit_v1,
    validate_hip_fgmres_iteration_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_launch_fence_audit_v1 import (
    open_hip_fgmres_recurrence_launch_fence_audit_v1,
    validate_hip_fgmres_recurrence_launch_fence_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1
from structural_analysis.model_ir import load_model_ir_v2

from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    FIXTURE,
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_TRANSFER_AUDIT_HARDWARE",
        )
    )


def test_native_gfx1030_recurrence_program_copy_zero_and_fenced_export_three_d2h() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = load_model_ir_v2(FIXTURE)
    policy = compile_fgmres_policy_v1(
        restart_dimension=1,
        max_iterations=1,
        relative_tolerance=1.0e-15,
    )
    audit_opens: list[Any] = []
    ordinal_opens: list[Any] = []
    def open_audit_before_first_enqueue(
        context: HipFgmresCanonicalPredecessorExecutionContextV1,
    ) -> None:
        assert not audit_opens and not ordinal_opens
        transfer = open_hip_fgmres_iteration_host_transfer_audit_v1(context)
        try:
            ordinal = open_hip_fgmres_recurrence_launch_fence_audit_v1(context)
        except BaseException:
            transfer.context.close()
            raise
        audit_opens.append(transfer)
        ordinal_opens.append(ordinal)
    chain = None
    audit = ordinal_audit = None
    sealed = global_open = None
    try:
        chain, predecessor = _open_canonical_chain(
            model=model,
            architecture=architecture,
            required=required,
            policy=policy,
            before_canonical_enqueue=open_audit_before_first_enqueue,
        )
        assert len(audit_opens) == 1 and len(ordinal_opens) == 1
        audit = audit_opens[0].context
        ordinal_audit = ordinal_opens[0].context
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor,
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
        ordinal_result = ordinal_audit.seal_terminal_fence(
            global_open.context,
            completion,
        )
        validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
            ordinal_result,
            expected_context=ordinal_audit,
        )
        result = audit.export_completion_buffers(global_open.context, completion)
        validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
            result,
            expected_context=audit,
        )

        receipt = result.receipt
        assert receipt.actual_backend == "hip"
        assert receipt.bindings.native_loader_bound_runtime
        assert receipt.bindings.architecture == "gfx1030"
        assert receipt.window.recurrence_program.sequence_delta == 0
        assert receipt.window.completion_export.sequence_delta == 6
        blocking = receipt.window.completion_export.d2h_blocking
        assert blocking.attempt_count == 3
        assert blocking.success_count == 3
        assert blocking.failure_count == 0
        assert blocking.bytes_succeeded == 360
        assert receipt.dimensions.total_export_byte_count == 360
        assert not receipt.claims.iteration_host_copy_zero_proven
        assert not getattr(
            receipt.claims,
            "pre_window_async_copy_completion_or_device_dma_activity_zero_proven",
        )
        assert not receipt.claims.process_wide_host_transfer_zero_proven
        assert not receipt.claims.commercial_ready

        ordinal_receipt = ordinal_result.receipt
        ordinal_dimensions = ordinal_receipt.dimensions
        assert ordinal_receipt.actual_backend == "hip"
        assert ordinal_receipt.bindings.architecture == "gfx1030"
        assert ordinal_receipt.telemetry.memset.attempt_count == 8
        assert ordinal_receipt.telemetry.memset.success_count == 8
        assert ordinal_receipt.telemetry.launch.attempt_count == (
            ordinal_dimensions.full_program_launch_count
        )
        assert ordinal_receipt.telemetry.launch.success_count == (
            ordinal_dimensions.full_program_launch_count
        )
        assert ordinal_receipt.telemetry.fence.attempt_count == 3
        assert ordinal_receipt.telemetry.fence.success_count == 3
        assert ordinal_receipt.window.terminal_fence_ordinal == (
            ordinal_receipt.window.end_operation_ordinal
        )
        assert not ordinal_receipt.claims.device_kernel_execution_success_proven
        assert not ordinal_receipt.claims.iteration_host_copy_zero_proven
        assert not ordinal_receipt.claims.commercial_ready
    finally:
        if ordinal_audit is not None:
            ordinal_audit.close()
        elif ordinal_opens:
            ordinal_opens[-1].context.close()
        if audit is not None:
            audit.close()
        elif audit_opens:
            audit_opens[-1].context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if chain is not None:
            chain.close()
