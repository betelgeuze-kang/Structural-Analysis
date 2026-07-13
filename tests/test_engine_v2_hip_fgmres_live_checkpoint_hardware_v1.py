from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, NoReturn

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.context import (  # noqa: E402
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (  # noqa: E402
    HipFgmresLiveCheckpointContextV1Error,
    open_hip_fgmres_live_checkpoint_context_v1,
    validate_hip_fgmres_live_checkpoint_context_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (  # noqa: E402
    HipFreeSpaceContextError,
    open_hip_free_space_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (  # noqa: E402
    HipKrylovPrimitivesContextError,
    open_hip_krylov_primitives_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.plan import (  # noqa: E402
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (  # noqa: E402
    HipResidentCsrContextError,
    open_hip_resident_csr_execution_context,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
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


_OWNED_ROLES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_PARENT_ROLES = ("reduced_state", "reduced_load", "jacobi_inverse")


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_LIVE_CHECKPOINT_HARDWARE",
        )
    )


def _hardware_gate(required: bool, message: str) -> NoReturn:
    if required:
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message} No CPU fallback was used.")


def _close_chain(
    live: Any | None,
    primitives: Any | None,
    free_space: Any | None,
    resident: Any | None,
    assembly: Any | None,
) -> None:
    errors: list[str] = []
    for label, context in (
        ("fgmres-live-checkpoint", live),
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


def test_native_fgmres_live_checkpoint_resource_owner_and_reverse_cleanup() -> None:
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
    execution_plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, execution_plan)

    assembly = None
    resident = None
    free_space = None
    primitives = None
    live = None
    try:
        try:
            assembly_open = open_hip_assembly_execution_context(
                buffers,
                execution_plan,
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
            _hardware_gate(
                required,
                "Native assembly context is unavailable: "
                f"{assembly_open.receipt.status}.",
            )
        if (
            assembly_open.evaluation.receipt.status != "verified"
            or assembly_open.evaluation.receipt.parity is None
            or not assembly_open.evaluation.receipt.parity.passed
        ):
            _hardware_gate(required, "Native assembly CPU parity failed.")
        assert assembly_open.receipt.actual_backend == "hip"
        assert assembly_open.receipt.telemetry.fallback_count == 0

        try:
            resident_open = open_hip_resident_csr_execution_context(
                assembly,
                create_initial_state(execution_plan),
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
        assert resident_open.receipt.actual_backend == "hip"
        assert resident_open.receipt.telemetry.fallback_count == 0

        free_space_plan = compile_hip_free_space_operator_plan_v1(execution_plan)
        try:
            free_space_open = open_hip_free_space_execution_context(
                resident,
                free_space_plan,
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
        assert free_space_open.receipt.actual_backend == "hip"
        assert free_space_open.receipt.telemetry.fallback_count == 0

        source_apply = free_space.enqueue_operator_apply()
        if source_apply.status != "enqueued":
            reason = source_apply.reason
            _hardware_gate(
                required,
                "Native free-space apply failed: "
                f"{reason.code if reason is not None else 'unknown'}.",
            )
        assert source_apply.telemetry_delta.fallback_count == 0
        assert source_apply.telemetry_delta.h2d_operation_count == 0
        assert source_apply.telemetry_delta.d2h_operation_count == 0

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
        assert primitives_open.receipt.actual_backend == "hip"
        assert primitives_open.receipt.telemetry.fallback_count == 0

        fgmres_plan = compile_hip_fgmres_plan_v1(
            execution_plan,
            free_space_plan,
        )
        recurrence_plan = compile_hip_fgmres_recurrence_plan_v2(fgmres_plan)
        try:
            live_open = open_hip_fgmres_live_checkpoint_context_v1(
                primitives,
                source_apply,
                recurrence_plan,
                architecture=architecture,
            )
        except HipFgmresLiveCheckpointContextV1Error as exc:
            _hardware_gate(
                required,
                f"Native live checkpoint context open failed: {exc.code}.",
            )
        live = live_open.context
        if not live_open.ready or live is None:
            assert live_open.receipt.telemetry.fallback_count == 0
            reason = live_open.receipt.reason
            _hardware_gate(
                required,
                "Native live checkpoint context is unavailable: "
                f"{reason.code if reason is not None else live_open.receipt.status}.",
            )

        opening = live_open.receipt
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            opening,
            expected_context=live,
        )
        assert opening.status == "context_ready"
        assert opening.actual_backend == "hip"
        assert opening.evidence_scope == (
            "allocator_bound_live_checkpoint_resources_non_promoting"
        )
        assert opening.promotion_eligible is False
        assert opening.reason is None
        assert opening.bindings.primitive_actual_backend == "hip"
        assert opening.bindings.primitive_evidence_scope == (
            "native_hiprtc_krylov_primitives_composite"
        )
        assert opening.kernel is not None
        assert opening.kernel.architecture == architecture
        assert opening.kernel.kernel_origin == "internally_compiled"
        assert opening.kernel.runtime_library_discovery_source != "injected"
        assert opening.kernel.hiprtc_library_discovery_source != "injected"

        assert opening.dimensions.parent_capability_count == 3
        assert opening.dimensions.solver_owned_capability_count == 8
        assert opening.dimensions.atomic_group_capability_count == 11
        assert tuple(row.name for row in opening.owned_buffers) == _OWNED_ROLES

        expected_bytes = sum(row.byte_length for row in opening.owned_buffers)
        lineage = opening.allocation_lineage
        assert lineage.owner_role == "fgmres_checkpoint_owned_buffers"
        assert lineage.runtime_device_bound
        assert lineage.same_stream_bound
        assert lineage.parent_borrowed_capability_count == 3
        assert lineage.managed_buffer_count == 8
        assert lineage.managed_device_bytes == expected_bytes
        assert lineage.atomic_group_capability_count == 11
        assert lineage.all_owned_buffers_managed
        assert lineage.pointer_values_serialized is False
        assert lineage.promotion_eligible is False

        group = live._group_capabilities
        assert len(group) == 11
        assert tuple(row.role for row in group[:3]) == _PARENT_ROLES
        assert tuple(row.role for row in group[3:]) == _OWNED_ROLES
        assert live._group_lease is not None
        assert primitives._fgmres_solver_child_phase == "active"

        telemetry = opening.telemetry
        assert telemetry.allocation_attempt_count == 8
        assert telemetry.allocation_success_count == 8
        assert telemetry.deallocation_attempt_count == 0
        assert telemetry.deallocation_success_count == 0
        assert telemetry.current_device_bytes == expected_bytes
        assert telemetry.peak_device_bytes == expected_bytes
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_owner_close_success_count == 0
        assert telemetry.lineage_capability_mint_success_count == 8
        assert telemetry.lineage_capability_mint_bytes == expected_bytes
        assert telemetry.lineage_free_acknowledgement_count == 0
        assert telemetry.lineage_free_quarantine_count == 0
        assert telemetry.lineage_orphan_acknowledgement_count == 0
        assert telemetry.lineage_orphan_quarantine_count == 0
        assert telemetry.quarantined_device_bytes == 0
        assert telemetry.unknown_malloc_outcome_count == 0
        assert telemetry.unknown_requested_bytes == 0
        assert telemetry.module_owner_acquire_success_count == 1
        assert telemetry.module_close_attempt_count == 0
        assert telemetry.module_close_success_count == 0
        assert telemetry.checkpoint_token_acquire_success_count == 1
        assert telemetry.checkpoint_token_release_success_count == 0
        assert telemetry.group_borrow_acquire_success_count == 1
        assert telemetry.group_borrow_release_attempt_count == 0
        assert telemetry.group_borrow_release_success_count == 0
        assert telemetry.semantic_lease_acquire_success_count == 1
        assert telemetry.semantic_lease_release_attempt_count == 0
        assert telemetry.semantic_lease_release_success_count == 0
        assert telemetry.h2d_operation_count == 0
        assert telemetry.d2h_operation_count == 0
        assert telemetry.kernel_launch_count == 0
        assert telemetry.sync_count == 0
        assert telemetry.fallback_count == 0

        claims = opening.claims
        assert claims.live_krylov_parent_integrated
        assert claims.allocator_provenance_bound
        assert claims.resource_owner_ready
        assert not claims.owned_content_initialized
        assert not claims.authoritative_predecessor_proven
        assert not claims.device_mask_domain_validator_bound
        assert not claims.actual_mask_host_observed
        assert not claims.checkpoint_transaction_ready
        assert not claims.live_solver_ready
        assert not claims.solution_ready
        assert not claims.iteration_host_copy_zero_proven
        assert not claims.asymptotic_o_n_proven
        assert not claims.speedup_proven
        assert not claims.commercial_ready
        assert not claims.promotion_eligible

        allocation_owner = live._allocation_owner
        assert allocation_owner is not None
        live.close()
        assert live.closed
        assert allocation_owner.closed
        assert live._owned_capabilities == {}
        assert live._group_released
        assert live._semantic_released
        assert primitives._fgmres_solver_child_phase == "idle"
        assert primitives._fgmres_solver_child_token is None

        terminal = live.receipt()
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            terminal,
            expected_context=live,
        )
        assert terminal.status == "context_closed"
        assert terminal.telemetry.allocation_attempt_count == 8
        assert terminal.telemetry.allocation_success_count == 8
        assert terminal.telemetry.deallocation_attempt_count == 8
        assert terminal.telemetry.deallocation_success_count == 8
        assert terminal.telemetry.current_device_bytes == 0
        assert terminal.telemetry.peak_device_bytes == expected_bytes
        assert terminal.telemetry.lineage_owner_open_success_count == 1
        assert terminal.telemetry.lineage_owner_close_success_count == 1
        assert terminal.telemetry.lineage_capability_mint_success_count == 8
        assert terminal.telemetry.lineage_capability_mint_bytes == expected_bytes
        assert terminal.telemetry.lineage_free_acknowledgement_count == 8
        assert terminal.telemetry.lineage_free_quarantine_count == 0
        assert terminal.telemetry.lineage_orphan_acknowledgement_count == 0
        assert terminal.telemetry.lineage_orphan_quarantine_count == 0
        assert terminal.telemetry.quarantined_device_bytes == 0
        assert terminal.telemetry.unknown_malloc_outcome_count == 0
        assert terminal.telemetry.unknown_requested_bytes == 0
        assert terminal.telemetry.module_owner_acquire_success_count == 1
        assert terminal.telemetry.module_close_attempt_count == 1
        assert terminal.telemetry.module_close_success_count == 1
        assert terminal.telemetry.checkpoint_token_acquire_success_count == 1
        assert terminal.telemetry.checkpoint_token_release_success_count == 1
        assert terminal.telemetry.group_borrow_acquire_success_count == 1
        assert terminal.telemetry.group_borrow_release_attempt_count == 1
        assert terminal.telemetry.group_borrow_release_success_count == 1
        assert terminal.telemetry.semantic_lease_acquire_success_count == 1
        assert terminal.telemetry.semantic_lease_release_attempt_count == 1
        assert terminal.telemetry.semantic_lease_release_success_count == 1
        assert terminal.telemetry.h2d_operation_count == 0
        assert terminal.telemetry.d2h_operation_count == 0
        assert terminal.telemetry.kernel_launch_count == 0
        assert terminal.telemetry.sync_count == 0
        assert terminal.telemetry.fallback_count == 0
        assert not any(terminal.claims.to_dict().values())

        primitives.close()
        assert primitives.closed
        primitives_terminal = primitives.receipt()
        assert primitives_terminal.status == "context_closed"
        assert primitives_terminal.telemetry.current_device_bytes == 0
        assert primitives_terminal.telemetry.deallocation_success_count == 9
        assert primitives_terminal.telemetry.module_close_success_count == 1
        assert primitives_terminal.telemetry.lease_release_success_count == 1
        assert primitives_terminal.telemetry.fallback_count == 0

        free_space.close()
        assert free_space.closed
        free_space_terminal = free_space.receipt()
        assert free_space_terminal.status == "context_closed"
        assert free_space_terminal.telemetry.current_device_bytes == 0
        assert free_space_terminal.telemetry.deallocation_success_count == 12
        assert free_space_terminal.telemetry.module_close_success_count == 1
        assert free_space_terminal.telemetry.lease_release_success_count == 1
        assert free_space_terminal.telemetry.fallback_count == 0

        resident.close()
        assert resident.closed
        resident_terminal = resident.receipt()
        assert resident_terminal.status == "context_closed"
        assert resident_terminal.telemetry.owned_current_device_bytes == 0
        assert resident_terminal.telemetry.owned_deallocation_success_count == 4
        assert resident_terminal.telemetry.module_close_success_count == 1
        assert resident_terminal.telemetry.lease_release_success_count == 1
        assert resident_terminal.telemetry.fallback_count == 0

        assembly.close()
        assert assembly.closed
        assembly_terminal = assembly.receipt()
        assert assembly_terminal.status == "context_closed"
        assert assembly_terminal.telemetry.current_device_payload_bytes == 0
        assert assembly_terminal.telemetry.fallback_count == 0
    finally:
        _close_chain(live, primitives, free_space, resident, assembly)
