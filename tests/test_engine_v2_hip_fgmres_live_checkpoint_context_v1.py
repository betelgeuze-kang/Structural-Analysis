from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import threading
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_rtc_v2,
    fgmres_live_checkpoint_context_v1 as live_checkpoint_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1,
    HipFgmresLiveCheckpointContextV1Error,
    _receipt_payload,
    open_hip_fgmres_live_checkpoint_context_v1,
    validate_hip_fgmres_live_checkpoint_context_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (
    HipAllocationOwnerV1,
    HipAllocationLineageError,
    validate_hip_allocation_borrow_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_context_v2 import BoundFakeLoadedRuntime
from tests.test_engine_v2_hip_fgmres_rtc_v2 import _compile_fake
from tests.test_engine_v2_hip_krylov_primitives_context_v1 import (
    _close_all,
    _open_primitives,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/hip_fgmres_live_checkpoint_context_v1.schema.json"
)
OWNED_ROLES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
PARENT_ROLES = ("reduced_state", "reduced_load", "jacobi_inverse")


def _prepare_live_inputs(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    *_, runtime, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    parent = opened.context
    assert parent is not None
    source_plan = compile_hip_fgmres_plan_v1(
        parent._parent._plan,
        parent._parent._overlay,
    )
    recurrence_plan = compile_hip_fgmres_recurrence_plan_v2(source_plan)
    loaded = BoundFakeLoadedRuntime()
    runtime._loaded = loaded
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    return (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        recurrence_plan,
        kernel,
        loaded,
    )


def _open_live(monkeypatch: pytest.MonkeyPatch, **options: Any) -> tuple[Any, ...]:
    malloc_failure_offset = options.pop("malloc_failure_offset", None)
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        recurrence_plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    if malloc_failure_offset is not None:
        runtime.malloc_failure_at = runtime.malloc_calls + malloc_failure_offset
    live = open_hip_fgmres_live_checkpoint_context_v1(
        parent,
        source_apply,
        recurrence_plan,
        architecture="gfx1030",
        rtc_kernel=kernel,
        **options,
    )
    return (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        recurrence_plan,
        kernel,
        live,
    )


def _cleanup(
    live: Any,
    opened: Any,
    free_open: Any,
    resident_open: Any,
    parent_open: Any,
) -> None:
    if live.context is not None and not live.context.closed:
        live.context.close()
    _close_all(opened, free_open, resident_open, parent_open)


def _observe_live_terminal_order(
    monkeypatch: pytest.MonkeyPatch,
    parent: Any,
    runtime: Any,
) -> list[str]:
    events: list[str] = []
    original_free = runtime.free

    def observed_free(pointer: int) -> None:
        events.append("owned_free")
        original_free(pointer)

    monkeypatch.setattr(runtime, "free", observed_free)
    original_owner_close = HipAllocationOwnerV1.close

    def observed_owner_close(
        owner: HipAllocationOwnerV1,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if owner.owner_role == "fgmres_checkpoint_owned_buffers":
            events.append("owner_close")
        original_owner_close(owner, *args, **kwargs)

    monkeypatch.setattr(HipAllocationOwnerV1, "close", observed_owner_close)
    parent_type = type(parent)
    original_semantic_release = parent_type._release_fgmres_solver_child

    def observed_semantic_release(
        primitive: Any,
        token: object,
        source_apply: Any,
    ) -> None:
        if primitive is parent:
            events.append("semantic_release")
        original_semantic_release(primitive, token, source_apply)

    monkeypatch.setattr(
        parent_type,
        "_release_fgmres_solver_child",
        observed_semantic_release,
    )
    return events


def test_live_resource_owner_ready_receipt_and_close_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        plan,
        kernel,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    parent = opened.context
    assert context is not None and parent is not None and live.ready
    try:
        receipt = live.receipt
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            receipt, expected_context=context
        )
        assert receipt.status == "context_ready"
        assert receipt.actual_backend == "test_double"
        assert receipt.bindings.primitive_evidence_scope == "injected_test_double"
        assert receipt.bindings.primitive_actual_backend == "test_double"
        assert receipt.kernel is not None
        assert receipt.kernel.kernel_origin == "caller_supplied"
        assert receipt.kernel.runtime_library_discovery_source == "injected"
        assert receipt.kernel.hiprtc_library_discovery_source == "injected"
        assert receipt.schema_version == (
            HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1
        )
        assert receipt.dimensions.parent_capability_count == 3
        assert receipt.dimensions.solver_owned_capability_count == 8
        assert receipt.dimensions.atomic_group_capability_count == 11
        assert tuple(row.name for row in receipt.owned_buffers) == OWNED_ROLES
        assert receipt.telemetry.allocation_attempt_count == 8
        assert receipt.telemetry.allocation_success_count == 8
        assert receipt.telemetry.group_borrow_acquire_success_count == 1
        assert receipt.telemetry.module_owner_acquire_success_count == 1
        assert receipt.telemetry.kernel_launch_count == 0
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.claims.live_krylov_parent_integrated
        assert receipt.claims.allocator_provenance_bound
        assert receipt.claims.resource_owner_ready
        assert not receipt.claims.owned_content_initialized
        assert not receipt.claims.authoritative_predecessor_proven
        assert not receipt.claims.checkpoint_transaction_ready
        assert not receipt.claims.live_solver_ready
        assert not receipt.claims.promotion_eligible

        expected_bytes = sum(plan.buffer(name).byte_length for name in OWNED_ROLES)
        formula_bytes = (
            8
            * (
                (2 * plan.restart_dimension + 4) * plan.free_dof_count
                + plan.restart_dimension * plan.restart_dimension
                + 5 * plan.restart_dimension
                + 1
            )
            + 448
            + 72 * plan.maximum_restart_count
        )
        assert expected_bytes == formula_bytes
        assert receipt.allocation_lineage.managed_device_bytes == expected_bytes
        assert receipt.telemetry.current_device_bytes == expected_bytes

        group = context._group_capabilities
        assert len(group) == 11
        assert tuple(capability.role for capability in group[:3]) == PARENT_ROLES
        assert tuple(capability.role for capability in group[3:]) == OWNED_ROLES
        assert context._group_lease is not None
        validate_hip_allocation_borrow_v1(context._group_lease)
        assert parent._fgmres_solver_child_phase == "active"

        serialized = json.dumps(receipt.to_dict(), sort_keys=True)
        for forbidden in (
            "pointer_snapshot",
            "owner_identity",
            "lease_id",
            "stream_pointer",
            "module_pointer",
            "function_pointer",
        ):
            assert forbidden not in serialized

        owned_pointers = {capability.pointer_snapshot for capability in group[3:]}
        context.close()
        assert context.closed and kernel.closed
        assert parent._fgmres_solver_child_phase == "idle"
        assert parent._fgmres_solver_child_token is None
        assert owned_pointers.isdisjoint(runtime.allocations)
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.telemetry.deallocation_success_count == 8
        assert terminal.telemetry.group_borrow_release_success_count == 1
        assert terminal.telemetry.semantic_lease_release_success_count == 1
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_sequential_live_context_reuses_parent_allocation_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        first_kernel,
        first,
    ) = _open_live(monkeypatch)
    parent = opened.context
    assert first.context is not None and parent is not None
    parent_generations = tuple(
        capability.generation for capability in first.context._parent_capabilities
    )
    second: Any = None
    try:
        first.context.close()
        assert first_kernel.closed
        loaded = runtime._loaded
        second_kernel, _, _ = _compile_fake(monkeypatch, loaded)
        second = open_hip_fgmres_live_checkpoint_context_v1(
            parent,
            source_apply,
            plan,
            architecture="gfx1030",
            rtc_kernel=second_kernel,
        )
        assert second.ready and second.context is not None
        assert (
            tuple(
                capability.generation
                for capability in second.context._parent_capabilities
            )
            == parent_generations
        )
        second.context.close()
        assert second_kernel.closed
    finally:
        if (
            second is not None
            and second.context is not None
            and not second.context.closed
        ):
            second.context.close()
        _cleanup(first, opened, free_open, resident_open, parent_open)


def test_memory_budget_failure_cleans_every_live_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        kernel,
        live,
    ) = _open_live(monkeypatch, memory_budget_bytes=1)
    parent = opened.context
    assert parent is not None
    try:
        assert live.context is None
        assert live.receipt.status == "unavailable"
        assert parent._fgmres_solver_child_token is None
        assert parent._fgmres_solver_child_phase == "idle"
        assert not kernel.closed
        assert live.receipt.telemetry.allocation_attempt_count == 0
        assert live.receipt.telemetry.semantic_lease_release_success_count == 0
        assert live.receipt.telemetry.module_owner_acquire_success_count == 0
    finally:
        if not kernel.closed:
            kernel.close()
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_peer_owner_return_store_interruption_recovers_exact_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_open = live_checkpoint_module.open_hip_allocation_peer_owner_v1
    published: list[HipAllocationOwnerV1] = []

    def interrupt_after_owner_return(*args: Any, **kwargs: Any) -> Any:
        owner = original_open(*args, **kwargs)
        published.append(owner)
        raise KeyboardInterrupt("peer owner return STORE interrupted")

    monkeypatch.setattr(
        live_checkpoint_module,
        "open_hip_allocation_peer_owner_v1",
        interrupt_after_owner_return,
    )
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert interrupted.value.code == (
            "hip_fgmres_live_checkpoint_context_open_interrupted"
        )
        assert interrupted.value.cleanup_owner is None
        assert len(published) == 1 and published[0].closed
        assert not kernel.closed
        assert parent._fgmres_solver_child_phase == "idle"
        assert events == ["owner_close"]
    finally:
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


def test_semantic_reserve_return_store_recovers_exact_owner_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    parent_type = type(parent)
    original_reserve = parent_type._reserve_fgmres_solver_child_for_source_apply
    fired = False

    def interrupt_after_semantic_reserve(
        primitive: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal fired
        capabilities = original_reserve(primitive, *args, **kwargs)
        if primitive is parent and not fired:
            fired = True
            raise KeyboardInterrupt("semantic reserve return STORE interrupted")
        return capabilities

    monkeypatch.setattr(
        parent_type,
        "_reserve_fgmres_solver_child_for_source_apply",
        interrupt_after_semantic_reserve,
    )
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert fired
        assert interrupted.value.cleanup_owner is None
        assert not kernel.closed
        assert parent._fgmres_solver_child_phase == "idle"
        assert events == ["owner_close", "semantic_release"]
    finally:
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


def test_checkpoint_acquire_return_store_recovers_preissued_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        loaded,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    kernel_type = type(kernel)
    original_acquire = (
        kernel_type._acquire_checkpoint_transaction_owner_and_binding_snapshot
    )
    fired = False

    def interrupt_after_checkpoint_acquire(
        owner: Any, *args: Any, **kwargs: Any
    ) -> Any:
        nonlocal fired
        result = original_acquire(owner, *args, **kwargs)
        if owner is kernel and not fired:
            fired = True
            raise KeyboardInterrupt("checkpoint acquire return STORE interrupted")
        return result

    monkeypatch.setattr(
        kernel_type,
        "_acquire_checkpoint_transaction_owner_and_binding_snapshot",
        interrupt_after_checkpoint_acquire,
    )
    unload_before = loaded.unload_calls
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert fired
        assert interrupted.value.cleanup_owner is None
        assert kernel.closed
        assert loaded.unload_calls == unload_before + 1
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
    finally:
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("handoff_phase", ("module_owner", "promoted_kernel"))
def test_internal_compile_return_store_recovers_exact_module_authority(
    monkeypatch: pytest.MonkeyPatch,
    handoff_phase: str,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        initial_kernel,
        loaded,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    initial_kernel.close()
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_compile = live_checkpoint_module._compile_v2_with_handoff
    published: list[Any] = []

    def interrupt_after_compile_handoff(*args: Any, **kwargs: Any) -> Any:
        kernel = original_compile(*args, **kwargs)
        if handoff_phase == "module_owner":
            module_owner = kernel._ownership_cell.preowner
            assert type(module_owner) is (
                fgmres_rtc_v2._HipRtcFgmresV2ModuleCleanupOwner
            )
            fgmres_rtc_v2._reclaim_fgmres_v2_module_ownership(
                module_owner,
                kernel,
            )
            published.append(module_owner)
        else:
            published.append(kernel)
        raise KeyboardInterrupt(f"{handoff_phase} return STORE interrupted")

    monkeypatch.setattr(
        live_checkpoint_module,
        "_compile_v2_with_handoff",
        interrupt_after_compile_handoff,
    )
    unload_before = loaded.unload_calls
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
            )
        assert interrupted.value.cleanup_owner is None
        assert len(published) == 1
        if handoff_phase == "promoted_kernel":
            assert published[0].closed
        else:
            assert published[0]._closed
        assert loaded.unload_calls == unload_before + 1
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
    finally:
        owner = published[0] if published else None
        if owner is not None and not getattr(owner, "closed", False):
            owner.close()
        _close_all(opened, free_open, resident_open, parent_open)


def test_group_borrow_return_store_recovers_exact_lease_and_split_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_borrow = live_checkpoint_module.borrow_hip_allocations_v1
    fired = False

    def interrupt_after_group_borrow(*args: Any, **kwargs: Any) -> Any:
        nonlocal fired
        lease = original_borrow(*args, **kwargs)
        if not fired:
            fired = True
            raise KeyboardInterrupt("group borrow return STORE interrupted")
        return lease

    monkeypatch.setattr(
        live_checkpoint_module,
        "borrow_hip_allocations_v1",
        interrupt_after_group_borrow,
    )
    baseline_allocations = set(runtime.allocations)
    free_before = runtime.free_calls
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert fired
        assert interrupted.value.cleanup_owner is None
        assert kernel.closed
        assert runtime.free_calls == free_before + 8
        assert set(runtime.allocations) == baseline_allocations
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
        assert events.count("owned_free") == 8
    finally:
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


def test_parent_commit_validation_interrupt_cleanup_owner_reaches_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_open_owner = live_checkpoint_module.open_hip_allocation_peer_owner_v1
    peer_owners: list[HipAllocationOwnerV1] = []

    def capture_peer_owner(*args: Any, **kwargs: Any) -> Any:
        owner = original_open_owner(*args, **kwargs)
        peer_owners.append(owner)
        return owner

    monkeypatch.setattr(
        live_checkpoint_module,
        "open_hip_allocation_peer_owner_v1",
        capture_peer_owner,
    )
    parent_type = type(parent)
    original_validate = parent_type._validate_fgmres_live_allocation_borrow
    fired = False

    def interrupt_commit_validation(primitive: Any, lease: Any) -> None:
        nonlocal fired
        if primitive is parent and not fired:
            fired = True
            assert len(peer_owners) == 1
            capabilities, _, _ = peer_owners[0].cleanup_snapshot()
            solve_record = next(
                row for row in capabilities if row.role == "solve_record"
            )
            runtime.free_failure_pointer_once = solve_record.pointer_snapshot
            raise KeyboardInterrupt("parent borrow validation interrupted")
        original_validate(primitive, lease)

    monkeypatch.setattr(
        parent_type,
        "_validate_fgmres_live_allocation_borrow",
        interrupt_commit_validation,
    )
    cleanup_owner: Any = None
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert fired
        cleanup_owner = interrupted.value.cleanup_owner
        assert cleanup_owner is not None and not cleanup_owner.closed
        assert cleanup_owner._group_released
        assert not cleanup_owner._semantic_released
        assert parent._fgmres_solver_child_phase == "semantic_cleanup_active"

        cleanup_owner.close()
        assert cleanup_owner.closed
        assert peer_owners[0].closed
        assert kernel.closed
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
        assert events.count("owned_free") == 9
    finally:
        if cleanup_owner is not None and not cleanup_owner.closed:
            cleanup_owner.close()
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("role", OWNED_ROLES)
def test_each_allocation_return_store_recovers_registry_capability(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        plan,
        kernel,
        _,
    ) = _prepare_live_inputs(monkeypatch)
    parent = opened.context
    assert parent is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_allocate = HipAllocationOwnerV1.allocate
    published: list[Any] = []
    fired = False

    def interrupt_after_allocation_return(
        owner: HipAllocationOwnerV1,
        allocation_role: str,
        nbytes: int,
        element_type: str,
        *,
        _control_token: object | None = None,
    ) -> Any:
        nonlocal fired
        capability = original_allocate(
            owner,
            allocation_role,
            nbytes,
            element_type,
            _control_token=_control_token,
        )
        if allocation_role == role and not fired:
            fired = True
            published.append(capability)
            raise KeyboardInterrupt(
                f"{allocation_role} capability return STORE interrupted"
            )
        return capability

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "allocate",
        interrupt_after_allocation_return,
    )
    baseline_allocations = set(runtime.allocations)
    free_before = runtime.free_calls
    expected_count = OWNED_ROLES.index(role) + 1
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as interrupted:
            open_hip_fgmres_live_checkpoint_context_v1(
                parent,
                source_apply,
                plan,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert fired and len(published) == 1
        assert interrupted.value.cleanup_owner is None
        assert kernel.closed
        assert runtime.free_calls == free_before + expected_count
        assert set(runtime.allocations) == baseline_allocations
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
        assert events.count("owned_free") == expected_count
    finally:
        if not kernel.closed:
            kernel.close()
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("failure_offset", range(1, 9))
def test_each_owned_malloc_failure_cleans_prefix_and_parent_lease(
    monkeypatch: pytest.MonkeyPatch,
    failure_offset: int,
) -> None:
    (
        _,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        kernel,
        live,
    ) = _open_live(monkeypatch, malloc_failure_offset=failure_offset)
    parent = opened.context
    assert parent is not None
    try:
        assert live.context is None
        assert live.receipt.status == "unavailable"
        assert live.receipt.telemetry.allocation_attempt_count == failure_offset
        assert live.receipt.telemetry.allocation_success_count == failure_offset - 1
        assert live.receipt.telemetry.deallocation_success_count == failure_offset - 1
        assert live.receipt.telemetry.current_device_bytes == 0
        assert live.receipt.telemetry.lineage_owner_close_success_count == 1
        assert live.receipt.telemetry.module_close_success_count == 1
        assert live.receipt.telemetry.semantic_lease_release_success_count == 1
        assert parent._fgmres_solver_child_phase == "idle"
        assert parent._fgmres_solver_child_token is None
        assert kernel.closed
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_live_group_blocks_parent_diagnostics_close_and_every_begin_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        _,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    parent = opened.context
    assert context is not None and parent is not None
    try:
        for operation in (parent.enqueue_primitive_batch, parent.close):
            with pytest.raises(Exception) as blocked:
                operation()
            assert getattr(blocked.value, "code", "") == (
                "hip_krylov_primitives_fgmres_solver_child_active"
            )
        owners = (
            parent._parent._allocation_owner,
            parent._parent._allocation_owner,
            parent._allocation_owner,
            *(context._allocation_owner for _ in range(8)),
        )
        for owner, capability in zip(owners, context._group_capabilities, strict=True):
            with pytest.raises(HipAllocationLineageError) as borrowed:
                owner.begin_free(
                    capability,
                    _control_token=(
                        context._token if owner is context._allocation_owner else None
                    ),
                )
            assert borrowed.value.code == "hip_allocation_free_busy"
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_parent_direct_combined_release_rejects_live_owned_peer_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        opened,
        _,
        _,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    parent = opened.context
    assert context is not None and parent is not None
    owner = context._allocation_owner
    assert owner is not None and not owner.closed
    try:
        with pytest.raises(Exception) as blocked:
            parent._release_fgmres_solver_child(context._token, source_apply)
        assert getattr(blocked.value, "code", "") == (
            "hip_krylov_primitives_fgmres_solver_child_split_release_required"
        )
        assert parent._fgmres_solver_child_phase == "active"
        assert parent._fgmres_solver_child_token is context._token
        assert not owner.closed
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            context.receipt(),
            expected_context=context,
        )

        context.close()
        assert context.closed and owner.closed
        assert parent._fgmres_solver_child_phase == "idle"
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_controlled_live_owner_rejects_foreign_concurrent_mutations_20_of_20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        _,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    assert context is not None
    owner = context._allocation_owner
    assert owner is not None
    foreign = object()
    owned_generation = owner.generation

    def attempt_allocate(barrier: threading.Barrier) -> str:
        barrier.wait(timeout=5.0)
        try:
            owner.allocate(
                "solution_x",
                8,
                "f64",
                _control_token=foreign,
            )
        except HipAllocationLineageError as exc:
            return exc.code
        return "accepted"

    def attempt_close(barrier: threading.Barrier) -> str:
        barrier.wait(timeout=5.0)
        try:
            owner.close(_control_token=foreign)
        except HipAllocationLineageError as exc:
            return exc.code
        return "accepted"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for _ in range(20):
                barrier = threading.Barrier(2)
                allocate = executor.submit(attempt_allocate, barrier)
                close = executor.submit(attempt_close, barrier)
                codes = (
                    allocate.result(timeout=10.0),
                    close.result(timeout=10.0),
                )
                assert all(code != "accepted" and "control" in code for code in codes)

        with pytest.raises(HipAllocationLineageError) as wrong_role:
            owner.allocate(
                "not_an_owned_checkpoint_role",
                8,
                "f64",
                _control_token=context._token,
            )
        assert "control" in wrong_role.value.code
        capabilities, frees, orphans = owner.cleanup_snapshot()
        assert capabilities == context._group_capabilities[3:]
        assert frees == () and orphans == ()
        assert len(capabilities) == 8
        assert owner.generation == owned_generation
        assert owned_generation == capabilities[-1].generation

        context.close()
        assert context.closed and owner.closed
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_known_not_freed_close_retries_exact_pointer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        kernel,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    assert context is not None
    retry_pointer = context._owned_capabilities["solve_record"].pointer_snapshot
    runtime.free_failure_pointer_once = retry_pointer
    try:
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as failed:
            context.close()
        assert failed.value.cleanup_owner is context
        assert context.receipt().status == "cleanup_failed"
        assert kernel.closed
        assert context._group_released
        assert not context._semantic_released
        first_attempts = context.receipt().telemetry.deallocation_attempt_count
        assert first_attempts == 1

        context.close()
        assert context.closed
        assert context.receipt().telemetry.deallocation_attempt_count == 9
        assert context.receipt().telemetry.deallocation_success_count == 8
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("role", OWNED_ROLES)
def test_each_begin_free_return_store_recovers_exact_pending_lease(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        kernel,
        live,
    ) = _open_live(monkeypatch)
    context = live.context
    parent = opened.context
    assert context is not None and parent is not None
    owner = context._allocation_owner
    assert owner is not None
    events = _observe_live_terminal_order(monkeypatch, parent, runtime)
    original_begin_free = HipAllocationOwnerV1.begin_free
    fired = False

    def interrupt_after_begin_free(
        current_owner: HipAllocationOwnerV1,
        capability: Any,
        *,
        _control_token: object | None = None,
    ) -> Any:
        nonlocal fired
        lease = original_begin_free(
            current_owner,
            capability,
            _control_token=_control_token,
        )
        if current_owner is owner and capability.role == role and not fired:
            fired = True
            raise KeyboardInterrupt(
                f"{capability.role} begin_free return STORE interrupted"
            )
        return lease

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "begin_free",
        interrupt_after_begin_free,
    )
    baseline_allocations = set(runtime.allocations) - {
        capability.pointer_snapshot
        for capability in context._owned_capabilities.values()
    }
    free_before = runtime.free_calls
    try:
        with pytest.raises(KeyboardInterrupt):
            context.close()
        assert fired
        assert not context.closed
        assert not context._semantic_released
        assert not owner.closed

        context.close()
        assert context.closed and owner.closed and kernel.closed
        assert runtime.free_calls == free_before + 8
        assert set(runtime.allocations) == baseline_allocations
        assert context.receipt().telemetry.deallocation_attempt_count == 8
        assert context.receipt().telemetry.deallocation_success_count == 8
        assert parent._fgmres_solver_child_phase == "idle"
        assert events[-2:] == ["owner_close", "semantic_release"]
        assert events.count("owned_free") == 8
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_claim_rehash_forgery_is_semantically_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *prefix, opened, _, _, live = _open_live(monkeypatch)
    parent_open, resident_open, free_open = prefix[1], prefix[2], prefix[3]
    context = live.context
    assert context is not None
    try:
        forged_claims = replace(
            live.receipt.claims,
            authoritative_predecessor_proven=True,
        )
        forged = replace(live.receipt, claims=forged_claims)
        forged = replace(
            forged,
            context_receipt_hash=canonical_hash(
                _receipt_payload(forged, include_hash=False)
            ),
        )
        with pytest.raises((HipFgmresLiveCheckpointContextV1Error, ValueError)):
            validate_hip_fgmres_live_checkpoint_context_receipt_v1(forged)
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_backend_provenance_semantics_fix_test_double_and_hip_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *prefix, opened, _, _, live = _open_live(monkeypatch)
    parent_open, resident_open, free_open = prefix[1], prefix[2], prefix[3]
    context = live.context
    assert context is not None and live.receipt.kernel is not None
    try:
        assert live.receipt.actual_backend == "test_double"
        native_bindings = replace(
            live.receipt.bindings,
            primitive_evidence_scope=("native_hiprtc_krylov_primitives_composite"),
            primitive_actual_backend="hip",
        )
        native_kernel = replace(
            live.receipt.kernel,
            runtime_library_discovery_source="explicit",
            hiprtc_library_discovery_source="system_loader",
            kernel_origin="internally_compiled",
        )
        native = replace(
            live.receipt,
            bindings=native_bindings,
            kernel=native_kernel,
            actual_backend="hip",
        )
        native = replace(
            native,
            context_receipt_hash=canonical_hash(
                _receipt_payload(native, include_hash=False)
            ),
        )
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(native)
        assert not native.promotion_eligible
        assert not native.claims.live_solver_ready

        mislabeled = replace(native, actual_backend="test_double")
        mislabeled = replace(
            mislabeled,
            context_receipt_hash=canonical_hash(
                _receipt_payload(mislabeled, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresLiveCheckpointContextV1Error) as rejected:
            validate_hip_fgmres_live_checkpoint_context_receipt_v1(mislabeled)
        assert rejected.value.code == ("hip_fgmres_live_checkpoint_backend_invalid")
    finally:
        _cleanup(live, opened, free_open, resident_open, parent_open)


def test_schema_is_strict_draft_2020_12() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_public_exports() -> None:
    import structural_analysis.engine_v2 as engine_v2

    assert (
        engine_v2.open_hip_fgmres_live_checkpoint_context_v1
        is open_hip_fgmres_live_checkpoint_context_v1
    )
    assert callable(engine_v2.validate_hip_fgmres_live_checkpoint_context_receipt_v1)
    assert callable(engine_v2.reserve_hip_allocation_owner_control_v1)
    assert callable(engine_v2.validate_hip_allocation_owner_control_v1)
