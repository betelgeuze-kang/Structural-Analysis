from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
from typing import Any, NoReturn

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.context import (  # noqa: E402
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (  # noqa: E402
    open_hip_fgmres_canonical_predecessor_context_v1,
    validate_hip_fgmres_canonical_predecessor_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (  # noqa: E402
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (  # noqa: E402
    reduction_stage_output_counts_v2,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (  # noqa: E402
    open_hip_free_space_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (  # noqa: E402
    open_hip_krylov_primitives_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.plan import (  # noqa: E402
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (  # noqa: E402
    open_hip_resident_csr_execution_context,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers  # noqa: E402
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

from tests.test_engine_v2_hip_resident_csr_hardware_v1 import (  # noqa: E402
    FIXTURE,
    _local_architectures,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_CANONICAL_PREDECESSOR_HARDWARE",
        )
    )


def _hardware_gate(required: bool, message: str) -> NoReturn:
    if required:
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message} No CPU fallback was used.")


def _close_chain(*contexts: tuple[str, Any]) -> None:
    errors: list[str] = []
    for label, context in contexts:
        if context is None or bool(getattr(context, "closed", False)):
            continue
        try:
            context.close()
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    if errors:
        pytest.fail("Native HIP reverse cleanup failed: " + "; ".join(errors))


def _i32(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 4], "little", signed=True)


def test_native_live_canonical_predecessor_is_device_sealed_without_product_d2h() -> (
    None
):
    required = _hardware_required()
    architectures = _local_architectures()
    if not architectures:
        _hardware_gate(required, "No real gfx agent was detected.")
    architecture = architectures[0]
    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert not capability.fallback_used
        _hardware_gate(required, f"Native HIP unavailable: {capability.status_code}.")

    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )
    execution_plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, execution_plan)
    assembly = resident = free_space = primitives = live = canonical = None
    try:
        assembly_open = open_hip_assembly_execution_context(
            buffers,
            execution_plan,
            assembly_plan,
            verify_cpu_parity=True,
            device_ordinal=0,
            architecture=architecture,
        )
        assembly = assembly_open.context
        if not assembly_open.ready or assembly is None:
            _hardware_gate(
                required, f"Assembly unavailable: {assembly_open.receipt.status}."
            )
        assert assembly_open.receipt.actual_backend == "hip"
        assert assembly_open.receipt.telemetry.fallback_count == 0

        resident_open = open_hip_resident_csr_execution_context(
            assembly,
            create_initial_state(execution_plan),
            architecture=architecture,
        )
        resident = resident_open.context
        if not resident_open.ready or resident is None:
            _hardware_gate(
                required, f"Resident unavailable: {resident_open.receipt.status}."
            )

        free_space_plan = compile_hip_free_space_operator_plan_v1(execution_plan)
        free_open = open_hip_free_space_execution_context(
            resident, free_space_plan, architecture=architecture
        )
        free_space = free_open.context
        if not free_open.ready or free_space is None:
            _hardware_gate(
                required, f"FreeSpace unavailable: {free_open.receipt.status}."
            )
        source_apply = free_space.enqueue_operator_apply()
        if source_apply.status != "enqueued":
            _hardware_gate(required, "Native source apply was not enqueued.")

        primitives_open = open_hip_krylov_primitives_execution_context(
            free_space, source_apply, architecture=architecture
        )
        primitives = primitives_open.context
        if not primitives_open.ready or primitives is None:
            _hardware_gate(
                required, f"Krylov unavailable: {primitives_open.receipt.status}."
            )
        assert primitives_open.receipt.actual_backend == "hip"

        plan = compile_hip_fgmres_plan_v1(execution_plan, free_space_plan)
        recurrence = compile_hip_fgmres_recurrence_plan_v2(plan)
        live_open = open_hip_fgmres_live_checkpoint_context_v1(
            primitives,
            source_apply,
            recurrence,
            architecture=architecture,
        )
        live = live_open.context
        if not live_open.ready or live is None:
            _hardware_gate(
                required, f"Live FGMRES unavailable: {live_open.receipt.status}."
            )
        assert live_open.receipt.actual_backend == "hip"
        assert live_open.receipt.kernel is not None
        assert live_open.receipt.kernel.kernel_origin == "internally_compiled"

        canonical_open = open_hip_fgmres_canonical_predecessor_context_v1(live)
        canonical = canonical_open.context
        pending = canonical.enqueue_canonical_predecessor()
        canonical.synchronize_canonical_predecessor(pending)
        receipt = canonical.receipt()
        validate_hip_fgmres_canonical_predecessor_receipt_v1(
            receipt, expected_context=canonical
        )
        stages = len(reduction_stage_output_counts_v2(recurrence.free_dof_count))
        expected_kernels = 27 + 14 * stages
        expected_operations = 8 + expected_kernels
        assert receipt.status == "predecessor_fenced"
        assert receipt.actual_backend == "hip"
        assert receipt.telemetry.memset_attempt_count == 8
        assert receipt.telemetry.kernel_launch_attempt_count == expected_kernels
        assert receipt.telemetry.consumed_operation_count == expected_operations
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.d2h_operation_count == 0
        assert receipt.telemetry.intermediate_sync_count == 0
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.fallback_count == 0
        assert receipt.claims.canonical_producer_prefix_fenced
        assert receipt.claims.device_mask_domain_gate_bound
        assert not receipt.claims.actual_mask_host_observed
        assert not receipt.claims.device_validation_outcome_host_observed
        assert not receipt.claims.authoritative_predecessor_proven

        # Verification-only D2H, intentionally outside production telemetry.
        control = np.empty(256, dtype="u1")
        runtime = live._runtime
        stream = live._stream
        assert runtime is not None and stream is not None
        runtime.copy_d2h_async(
            control,
            ctypes.c_void_p(canonical._pointers["fgmres_control_state_v2"]),
            stream,
        )
        runtime.synchronize(stream)
        payload = control.tobytes()
        actual_mask = _i32(payload, 100)
        assert actual_mask in (0, 1792, 7936)
        assert _i32(payload, 96) == 14 * stages
        assert _i32(payload, 112) == 26 + 14 * stages
        assert _i32(payload, 116) == 1
        assert _i32(payload, 120) == actual_mask
        assert _i32(payload, 124) == 14 * stages
        assert canonical.receipt().telemetry.d2h_operation_count == 0
    finally:
        _close_chain(
            ("canonical-predecessor", canonical),
            ("fgmres-live", live),
            ("krylov", primitives),
            ("free-space", free_space),
            ("resident", resident),
            ("assembly", assembly),
        )
