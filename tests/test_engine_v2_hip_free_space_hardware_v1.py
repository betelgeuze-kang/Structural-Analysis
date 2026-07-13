from __future__ import annotations

import os
from typing import Any, NoReturn

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
    open_hip_free_space_execution_context,
    validate_hip_free_space_context_receipt,
    validate_hip_free_space_evaluation,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.plan import (
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    HipResidentCsrContextError,
    open_hip_resident_csr_execution_context,
    validate_hip_resident_csr_context_receipt,
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


def _hardware_gate(required: bool, message: str) -> NoReturn:
    if required:
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message} No CPU fallback was used.")


def _close_chain(
    free_space: Any | None,
    resident: Any | None,
    assembly: Any | None,
) -> None:
    errors: list[str] = []
    for label, context in (
        ("free-space", free_space),
        ("resident", resident),
        ("assembly", assembly),
    ):
        if context is None or bool(getattr(context, "closed", False)):
            continue
        try:
            context.close()
        except Exception as exc:  # cleanup must never be converted to a skip
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    if errors:
        pytest.fail(
            "Native HIP cleanup failed: " + "; ".join(errors),
            pytrace=False,
        )


def test_native_free_space_device_chain_and_cpu_parity() -> None:
    required = os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
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
        _hardware_gate(
            required,
            f"Native assembly context open failed: {exc.code}.",
        )

    assembly = assembly_open.context
    if not assembly_open.ready or assembly is None:
        assert assembly_open.receipt.telemetry.fallback_count == 0
        _close_chain(None, None, assembly)
        _hardware_gate(
            required,
            f"Native assembly context is unavailable: {assembly_open.receipt.status}.",
        )
    if (
        assembly_open.evaluation.receipt.status != "verified"
        or assembly_open.evaluation.receipt.parity is None
        or not assembly_open.evaluation.receipt.parity.passed
    ):
        _close_chain(None, None, assembly)
        _hardware_gate(required, "Native assembly CPU parity failed.")

    resident = None
    free_space = None
    evaluation = None
    try:
        try:
            resident_open = open_hip_resident_csr_execution_context(
                assembly,
                create_initial_state(plan),
                architecture=architecture,
            )
        except HipResidentCsrContextError as exc:
            _hardware_gate(
                required,
                f"Native resident context open failed: {exc.code}.",
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
                required,
                f"Native free-space context open failed: {exc.code}.",
            )
        free_space = free_space_open.context
        if not free_space_open.ready or free_space is None:
            assert free_space_open.receipt.telemetry.fallback_count == 0
            _hardware_gate(
                required,
                "Native free-space context is unavailable: "
                f"{free_space_open.receipt.status}.",
            )

        opening = free_space_open.receipt
        assert opening.actual_backend == "hip"
        assert opening.evidence_scope == "native_hiprtc_free_space_composite"
        assert opening.bindings.kernel_origin == "internally_compiled"
        assert opening.kernel is not None
        assert opening.kernel.runtime_library_discovery_source != "injected"
        assert opening.kernel.hiprtc_library_discovery_source != "injected"
        assert opening.telemetry.allocation_success_count == 12
        assert opening.telemetry.h2d_operation_success_count == 6
        assert opening.telemetry.kernel_launch_success_count == 1
        assert opening.telemetry.reduced_numeric_h2d_bytes == 0
        assert opening.telemetry.state_h2d_bytes == 0
        assert opening.telemetry.load_h2d_bytes == 0
        assert opening.telemetry.direction_h2d_bytes == 0
        assert opening.telemetry.new_stream_create_count == 0
        assert opening.telemetry.fallback_count == 0
        assert opening.claims.reduced_csr_device_materialized
        assert opening.claims.device_direction_producer_ready
        assert opening.claims.resident_jvp_consumer_ready
        assert opening.claims.native_composite_context
        validate_hip_free_space_context_receipt(
            opening,
            expected_context=free_space,
        )

        evaluation = free_space.evaluate_for_verification()
        if evaluation.receipt.status == "unavailable":
            reason = evaluation.receipt.reason
            _hardware_gate(
                required,
                "Native free-space launch/export failed: "
                f"{reason.code if reason is not None else 'unknown'}.",
            )
        if (
            evaluation.receipt.status != "verified"
            or evaluation.receipt.parity is None
            or not evaluation.receipt.parity.passed
        ):
            _hardware_gate(required, "Native free-space CPU parity failed.")

        apply = evaluation.apply
        assert apply is not None and apply.status == "enqueued"
        assert apply.evidence_scope == "native_hiprtc_free_space_composite"
        assert apply.telemetry_delta.producer_launch_success_count == 1
        assert apply.telemetry_delta.resident_launch_success_count == 1
        assert apply.telemetry_delta.gather_launch_success_count == 1
        assert apply.telemetry_delta.h2d_operation_count == 0
        assert apply.telemetry_delta.d2h_operation_count == 0
        assert apply.telemetry_delta.allocation_count == 0
        assert apply.telemetry_delta.sync_count == 0
        assert apply.telemetry_delta.fallback_count == 0
        assert apply.claims.direction_device_produced
        assert apply.claims.direction_generation_single_consumed
        assert apply.claims.resident_residual_jvp_enqueued
        assert apply.claims.reduced_jvp_gather_enqueued
        assert not apply.claims.fallback_used

        parity = evaluation.receipt.parity
        assert parity is not None
        assert parity.reduced_values.passed
        assert parity.reduced_state.passed
        assert parity.reduced_load.passed
        assert parity.residual_direction.passed
        assert parity.residual_direction_vs_negative_full_residual_free.passed
        assert parity.reduced_jvp.passed
        assert parity.full_residual.passed
        assert parity.full_direction.passed
        assert parity.constrained_direction_exact_zero
        constrained = plan.array("constrained_dofs")
        assert evaluation.full_direction is not None
        constrained_direction = evaluation.full_direction[constrained]
        assert np.array_equal(
            constrained_direction,
            np.zeros(constrained.size, dtype="<f8"),
        )
        assert not np.signbit(constrained_direction).any()
        assert evaluation.receipt.actual_backend == "hip"
        assert evaluation.receipt.telemetry_delta.fallback_count == 0
        assert evaluation.receipt.telemetry_delta.h2d_operation_count == 0
        validate_hip_free_space_evaluation(
            evaluation,
            expected_context=free_space,
        )
    finally:
        _close_chain(free_space, resident, assembly)

    assert free_space is not None
    free_space_closed = free_space.receipt()
    assert free_space_closed.status == "context_closed"
    assert free_space_closed.telemetry.current_device_bytes == 0
    assert free_space_closed.telemetry.deallocation_success_count == 12
    assert free_space_closed.telemetry.module_close_success_count == 1
    assert free_space_closed.telemetry.lease_release_success_count == 1
    assert free_space_closed.telemetry.fallback_count == 0
    validate_hip_free_space_context_receipt(
        free_space_closed,
        expected_context=free_space,
    )

    assert resident is not None
    resident_closed = resident.receipt()
    assert resident_closed.status == "context_closed"
    assert resident_closed.telemetry.owned_current_device_bytes == 0
    assert resident_closed.telemetry.owned_deallocation_success_count == 4
    assert resident_closed.telemetry.module_close_success_count == 1
    assert resident_closed.telemetry.lease_release_success_count == 1
    assert resident_closed.telemetry.fallback_count == 0
    validate_hip_resident_csr_context_receipt(
        resident_closed,
        expected_context=resident,
    )

    assembly_closed = assembly.receipt()
    assert assembly_closed.status == "context_closed"
    assert assembly_closed.telemetry.current_device_payload_bytes == 0
    assert assembly_closed.telemetry.fallback_count == 0
