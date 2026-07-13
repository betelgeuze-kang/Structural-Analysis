from __future__ import annotations

import os
from typing import Any, NoReturn

import pytest

from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
    open_hip_free_space_execution_context,
    validate_hip_free_space_apply_receipt,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (
    HipKrylovPrimitivesContextError,
    open_hip_krylov_primitives_execution_context,
    validate_hip_krylov_primitives_batch_receipt,
    validate_hip_krylov_primitives_context_receipt,
    validate_hip_krylov_primitives_evaluation,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives_rtc import (
    reduction_output_count,
)
from structural_analysis.engine_v2.assembly_backend.plan import (
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    HipResidentCsrContextError,
    open_hip_resident_csr_execution_context,
)
from structural_analysis.engine_v2.backends.hip.native import probe_hip_capability
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import create_initial_state
from structural_analysis.model_ir import load_model_ir_v2

from tests.test_engine_v2_hip_resident_csr_hardware_v1 import (
    FIXTURE,
    _local_architectures,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_KRYLOV_PRIMITIVES_HARDWARE",
        )
    )


def _hardware_gate(required: bool, message: str) -> NoReturn:
    if required:
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message} No CPU fallback was used.")


def _reduction_stage_count(partial_count: int) -> int:
    stages = 0
    count = partial_count
    while True:
        stages += 1
        count = reduction_output_count(count)
        if count == 1:
            return stages


def _close_chain(
    primitives: Any | None,
    free_space: Any | None,
    resident: Any | None,
    assembly: Any | None,
) -> None:
    errors: list[str] = []
    for label, context in (
        ("krylov-primitives", primitives),
        ("free-space", free_space),
        ("resident", resident),
        ("assembly", assembly),
    ):
        if context is None or bool(getattr(context, "closed", False)):
            continue
        try:
            context.close()
        except Exception as exc:  # cleanup failure must never become a skip
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    if errors:
        pytest.fail(
            "Native HIP reverse cleanup failed: " + "; ".join(errors),
            pytrace=False,
        )


def test_native_krylov_primitives_device_chain_and_cpu_parity() -> None:
    required = _hardware_required()
    architectures = _local_architectures()
    if not architectures:
        _hardware_gate(required, "No real gfx agent was detected.")
    architecture = architectures[0]

    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert not capability.fallback_used
        _hardware_gate(
            required,
            f"Native HIP capability is unavailable: {capability.status_code}.",
        )

    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE),
        load_pattern_id="LC_AXIAL",
    )
    plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, plan)
    try:
        assembly_open = open_hip_assembly_execution_context(
            buffers,
            plan,
            assembly_plan,
            verify_cpu_parity=True,
            device_ordinal=0,
            architecture=architecture,
        )
    except HipAssemblyContextError as exc:
        _hardware_gate(required, f"Native assembly context open failed: {exc.code}.")

    assembly = assembly_open.context
    if not assembly_open.ready or assembly is None:
        assert assembly_open.receipt.telemetry.fallback_count == 0
        _close_chain(None, None, None, assembly)
        _hardware_gate(
            required,
            f"Native assembly context is unavailable: {assembly_open.receipt.status}.",
        )
    if (
        assembly_open.evaluation.receipt.status != "verified"
        or assembly_open.evaluation.receipt.parity is None
        or not assembly_open.evaluation.receipt.parity.passed
    ):
        _close_chain(None, None, None, assembly)
        _hardware_gate(required, "Native assembly CPU parity failed.")

    resident = None
    free_space = None
    primitives = None
    try:
        try:
            resident_open = open_hip_resident_csr_execution_context(
                assembly,
                create_initial_state(plan),
                architecture=architecture,
            )
        except HipResidentCsrContextError as exc:
            _hardware_gate(
                required, f"Native resident context open failed: {exc.code}."
            )
        resident = resident_open.context
        if not resident_open.ready or resident is None:
            assert resident_open.receipt.telemetry.fallback_count == 0
            _hardware_gate(
                required,
                "Native resident context is unavailable: "
                f"{resident_open.receipt.status}.",
            )

        overlay = compile_hip_free_space_operator_plan_v1(plan)
        try:
            free_space_open = open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture=architecture,
            )
        except HipFreeSpaceContextError as exc:
            _hardware_gate(
                required, f"Native free-space context open failed: {exc.code}."
            )
        free_space = free_space_open.context
        if not free_space_open.ready or free_space is None:
            assert free_space_open.receipt.telemetry.fallback_count == 0
            _hardware_gate(
                required,
                "Native free-space context is unavailable: "
                f"{free_space_open.receipt.status}.",
            )

        source_apply = free_space.enqueue_operator_apply()
        if source_apply.status != "enqueued":
            reason = source_apply.reason
            _hardware_gate(
                required,
                "Native free-space apply failed: "
                f"{reason.code if reason is not None else 'unknown'}.",
            )
        assert source_apply.evidence_scope == "native_hiprtc_free_space_composite"
        assert source_apply.telemetry_delta.h2d_operation_count == 0
        assert source_apply.telemetry_delta.d2h_operation_count == 0
        assert source_apply.telemetry_delta.allocation_count == 0
        assert source_apply.telemetry_delta.sync_count == 0
        assert source_apply.telemetry_delta.fallback_count == 0
        validate_hip_free_space_apply_receipt(
            source_apply,
            expected_context=free_space,
        )

        try:
            primitives_open = open_hip_krylov_primitives_execution_context(
                free_space,
                source_apply,
                architecture=architecture,
            )
        except HipKrylovPrimitivesContextError as exc:
            _hardware_gate(
                required,
                f"Native Krylov primitive context open failed: {exc.code}.",
            )
        primitives = primitives_open.context
        if not primitives_open.ready or primitives is None:
            assert primitives_open.receipt.telemetry.fallback_count == 0
            _hardware_gate(
                required,
                "Native Krylov primitive context is unavailable: "
                f"{primitives_open.receipt.status}.",
            )

        opening = primitives_open.receipt
        assert opening.actual_backend == "hip"
        assert opening.evidence_scope == "native_hiprtc_krylov_primitives_composite"
        assert opening.bindings.kernel_origin == "internally_compiled"
        assert opening.bindings.source_apply_receipt_hash == source_apply.receipt_hash
        assert opening.bindings.source_apply_sequence == source_apply.sequence
        assert (
            opening.bindings.source_direction_generation
            == source_apply.direction_generation
        )
        assert opening.kernel is not None
        assert opening.kernel.architecture == architecture
        assert opening.kernel.runtime_library_discovery_source != "injected"
        assert opening.kernel.hiprtc_library_discovery_source != "injected"
        assert opening.dimensions.free_dof_count == overlay.free_dof_count
        assert opening.dimensions.reduction_segment_size == 512
        assert opening.dimensions.reduction_partial_count == max(
            1, (overlay.free_dof_count + 511) // 512
        )
        assert opening.telemetry.allocation_success_count == 9
        assert opening.telemetry.h2d_operation_success_count == 1
        assert opening.telemetry.h2d_bytes_succeeded == 4
        assert opening.telemetry.d2h_operation_success_count == 1
        assert opening.telemetry.d2h_bytes_succeeded == 4
        assert opening.telemetry.kernel_launch_success_count == 1
        assert opening.telemetry.sync_success_count == 1
        assert opening.telemetry.vector_h2d_bytes == 0
        assert opening.telemetry.reduction_h2d_bytes == 0
        assert opening.telemetry.new_stream_create_count == 0
        assert opening.telemetry.fallback_count == 0
        assert opening.claims.positive_jacobi_inverse_ready
        assert opening.claims.affine_primitive_ready
        assert opening.claims.dot_primitive_ready
        assert opening.claims.stable_l2_primitive_ready
        assert opening.claims.native_hiprtc_evidence
        assert not opening.claims.host_copy_zero_proven
        assert not opening.claims.spd_proven
        assert not opening.claims.pcg_ready
        assert not opening.claims.krylov_solver_ready
        assert not opening.claims.preconditioner_integrated
        assert not opening.claims.asymptotic_o_n_proven
        assert not opening.claims.speedup_proven
        assert not opening.claims.commercial_ready
        validate_hip_krylov_primitives_context_receipt(
            opening,
            expected_context=primitives,
        )

        expected_reduction_stages = _reduction_stage_count(
            opening.dimensions.reduction_partial_count
        )
        raw_batch = primitives.enqueue_primitive_batch()
        if raw_batch.status != "enqueued":
            reason = raw_batch.reason
            _hardware_gate(
                required,
                "Native Krylov raw batch failed: "
                f"{reason.code if reason is not None else 'unknown'}.",
            )
        assert raw_batch.telemetry_delta.fill_launch_success_count == 1
        assert raw_batch.telemetry_delta.affine_launch_success_count == 2
        assert raw_batch.telemetry_delta.jacobi_launch_success_count == 1
        assert raw_batch.telemetry_delta.dot_stage_launch_success_count == 1
        assert (
            raw_batch.telemetry_delta.sum_stage_launch_success_count
            == expected_reduction_stages
        )
        assert raw_batch.telemetry_delta.lassq_stage_launch_success_count == 1
        assert (
            raw_batch.telemetry_delta.lassq_combine_launch_success_count
            == expected_reduction_stages
        )
        assert raw_batch.telemetry_delta.lassq_finalize_launch_success_count == 1
        assert raw_batch.telemetry_delta.h2d_operation_count == 0
        assert raw_batch.telemetry_delta.d2h_operation_count == 0
        assert raw_batch.telemetry_delta.allocation_count == 0
        assert raw_batch.telemetry_delta.sync_count == 0
        assert raw_batch.telemetry_delta.fallback_count == 0
        assert not raw_batch.claims.completion_fence_observed
        assert not raw_batch.claims.solver_iteration
        assert not raw_batch.claims.pcg_iteration
        assert not raw_batch.claims.fallback_used
        validate_hip_krylov_primitives_batch_receipt(
            raw_batch,
            expected_context=primitives,
        )

        evaluation = primitives.evaluate_for_verification()
        if evaluation.receipt.status == "unavailable":
            reason = evaluation.receipt.reason
            _hardware_gate(
                required,
                "Native Krylov export failed: "
                f"{reason.code if reason is not None else 'unknown'}.",
            )
        if (
            evaluation.receipt.status != "verified"
            or evaluation.receipt.parity is None
            or not evaluation.receipt.parity.passed
        ):
            _hardware_gate(required, "Native Krylov primitive CPU parity failed.")
        assert evaluation.receipt.actual_backend == "hip"
        assert (
            evaluation.receipt.evidence_scope
            == "native_hiprtc_krylov_primitives_composite"
        )
        assert evaluation.receipt.telemetry_delta.d2h_operation_success_count == 7
        assert evaluation.receipt.telemetry_delta.d2h_bytes_succeeded == (
            32 * overlay.free_dof_count + 20
        )
        assert evaluation.receipt.telemetry_delta.sync_success_count == 1
        assert evaluation.receipt.telemetry_delta.h2d_operation_count == 0
        assert evaluation.receipt.telemetry_delta.allocation_count == 0
        assert evaluation.receipt.telemetry_delta.fallback_count == 0
        parity = evaluation.receipt.parity
        assert parity is not None
        assert parity.jacobi_inverse.passed
        assert parity.work_x.passed
        assert parity.work_y.passed
        assert parity.preconditioned.passed
        assert parity.dot_result.passed
        assert parity.norm_result.passed
        validate_hip_krylov_primitives_evaluation(
            evaluation,
            expected_context=primitives,
        )
    finally:
        _close_chain(primitives, free_space, resident, assembly)

    assert primitives is not None
    primitives_closed = primitives.receipt()
    assert primitives_closed.status == "context_closed"
    assert primitives_closed.telemetry.current_device_bytes == 0
    assert primitives_closed.telemetry.deallocation_success_count == 9
    assert primitives_closed.telemetry.module_close_success_count == 1
    assert primitives_closed.telemetry.lease_release_success_count == 1
    assert primitives_closed.telemetry.fallback_count == 0
    validate_hip_krylov_primitives_context_receipt(
        primitives_closed,
        expected_context=primitives,
    )

    assert free_space is not None
    free_space_closed = free_space.receipt()
    assert free_space_closed.status == "context_closed"
    assert free_space_closed.telemetry.current_device_bytes == 0
    assert free_space_closed.telemetry.deallocation_success_count == 12
    assert free_space_closed.telemetry.module_close_success_count == 1
    assert free_space_closed.telemetry.lease_release_success_count == 1
    assert free_space_closed.telemetry.fallback_count == 0

    assert resident is not None
    resident_closed = resident.receipt()
    assert resident_closed.status == "context_closed"
    assert resident_closed.telemetry.owned_current_device_bytes == 0
    assert resident_closed.telemetry.owned_deallocation_success_count == 4
    assert resident_closed.telemetry.module_close_success_count == 1
    assert resident_closed.telemetry.lease_release_success_count == 1
    assert resident_closed.telemetry.fallback_count == 0

    assembly_closed = assembly.receipt()
    assert assembly_closed.status == "context_closed"
    assert assembly_closed.telemetry.current_device_payload_bytes == 0
    assert assembly_closed.telemetry.fallback_count == 0
