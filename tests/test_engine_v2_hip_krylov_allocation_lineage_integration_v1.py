from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    krylov_primitives as primitives,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
    HipFreeSpaceExecutionContext,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOwnerV1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (
    HipKrylovPrimitivesExecutionContext,
    HipKrylovPrimitivesContextError,
    open_hip_krylov_primitives_execution_context,
)

from tests.test_engine_v2_hip_free_space_allocation_lineage_integration_v1 import (
    _KnownNotFreed,
    _HandoffInterrupt,
    _MisalignedMallocRuntime,
    _NativeShapedClassifiedFreeRuntime,
    _OutcomeUncertain,
    _ResolveTerminalInterrupt,
    _UncertainMallocRuntime,
    _allocation_states,
    _free_terminal_snapshot,
    _open_free_space_on,
    _pointer_value,
    _runtime_domain_poison_snapshot,
    _strong_lineage_registry_snapshot,
)
from tests.test_engine_v2_hip_free_space_context_v1 import _close_chain
from tests.test_engine_v2_hip_krylov_primitives_context_v1 import (
    FakeKrylovPrimitivesKernel,
    _close_all,
    _open_primitives,
)


_PARENT_BORROWED_ROLES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
    "reduced_direction",
    "reduced_jvp",
)
_OWNED_ROLES = (
    "jacobi_inverse",
    "work_x",
    "work_y",
    "preconditioned",
    "reduction_ping",
    "reduction_pong",
    "dot_result",
    "norm_result",
    "error_flag",
)


def _rehash_krylov_context_receipt(receipt: Any) -> Any:
    return replace(
        receipt,
        context_receipt_hash=primitives.canonical_hash(
            primitives._context_payload(receipt, include_hash=False)
        ),
    )


class _InvalidNonPointerMallocRuntime(_NativeShapedClassifiedFreeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._invalid_next_malloc = False
        self.invalid_base = object()

    def arm_invalid_malloc(self) -> None:
        self._invalid_next_malloc = True

    def malloc(self, byte_length: int) -> object:
        if not self._invalid_next_malloc:
            return super().malloc(byte_length)
        self._invalid_next_malloc = False
        self.malloc_calls += 1
        return self.invalid_base


@pytest.fixture(autouse=True)
def _lineage_registry_guard() -> Iterator[dict[str, tuple[tuple[Any, ...], ...]]]:
    baseline = _strong_lineage_registry_snapshot()
    yield baseline
    assert _strong_lineage_registry_snapshot() == baseline


def _open_primitives_on(
    runtime: _NativeShapedClassifiedFreeRuntime,
) -> tuple[Any, ...]:
    (
        *prefix,
        actual_runtime,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    assert actual_runtime is runtime
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    assert source_apply.status == "enqueued"
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    return (
        *prefix,
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        kernel,
        opened,
    )


def _assert_parent_capabilities_live(context: Any) -> None:
    assert _allocation_states(context._parent_capabilities) == ("live",) * 5


def _retire_poisoned_context_for_teardown(context: Any) -> None:
    """Recover only test-owned poisoned rows when intended open cleanup regresses."""

    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    for name, capability in tuple(context._owned_capabilities.items()):
        owner.quarantine_poisoned_allocation(capability)
        size = next(
            view.byte_length for view in context._owned_buffers if view.name == name
        )
        context._finish_owned_retirement(name, size, quarantined=True)
    context.close()


def test_ready_context_binds_exact_parent_group_peer_owner_and_owned_lineage() -> None:
    (
        *_,
        runtime,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives()
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None and opened.ready
    peer_owner = context._allocation_owner
    parent_owner = free._allocation_owner
    assert type(peer_owner) is HipAllocationOwnerV1
    assert type(parent_owner) is HipAllocationOwnerV1
    try:
        parent_capabilities = context._parent_capabilities
        parent_borrow = free._krylov_consumer_borrow_lease
        assert parent_borrow is not None
        assert parent_capabilities is context._parent_capability_snapshot
        assert parent_capabilities is parent_borrow.capabilities
        assert tuple(capability.role for capability in parent_capabilities) == (
            _PARENT_BORROWED_ROLES
        )
        assert len(parent_capabilities) == 5
        assert _allocation_states(parent_capabilities) == ("borrowed",) * 5
        for role, capability in zip(
            _PARENT_BORROWED_ROLES,
            parent_capabilities,
            strict=True,
        ):
            assert capability is free._owned_capabilities[role]
            assert context._borrowed_pointers[role] is capability.base

        assert peer_owner.owner_role == "krylov_primitives_owned_buffers"
        assert peer_owner.runtime_domain_id == parent_owner.runtime_domain_id
        assert peer_owner.owner_id != parent_owner.owner_id
        assert peer_owner.evidence_scope == "foundation_non_promoting"
        assert peer_owner.promotion_eligible is False

        views = {view.name: view for view in opened.receipt.owned_buffers}
        assert tuple(context._owned_capabilities) == _OWNED_ROLES
        assert tuple(views) == _OWNED_ROLES
        assert len(context._owned_capabilities) == 9
        for role in _OWNED_ROLES:
            capability = context._owned_capabilities[role]
            view = views[role]
            raw_base = context._pointers[role]
            assert capability.role == role
            assert capability.nbytes == view.byte_length
            assert capability.element_type == ("i32" if view.dtype == "<i4" else "f64")
            assert capability.runtime_owner is runtime
            assert capability.device_ordinal == parent_capabilities[0].device_ordinal
            assert capability.runtime_domain is parent_capabilities[0].runtime_domain
            assert capability.base is raw_base
            assert capability.pointer_snapshot == _pointer_value(raw_base)
            assert capability.evidence_scope == "foundation_non_promoting"
            assert capability.promotion_eligible is False

        managed_bytes = sum(view.byte_length for view in views.values())
        assert opened.receipt.allocation_lineage is not None
        assert opened.receipt.allocation_lineage.to_dict() == {
            "capability_profile": "foundation_non_promoting",
            "evidence_scope": "foundation_non_promoting",
            "owner_role": "krylov_primitives_owned_buffers",
            "runtime_device_bound": True,
            "parent_borrowed_capability_count": 5,
            "managed_buffer_count": 9,
            "managed_device_bytes": managed_bytes,
            "all_owned_buffers_managed": True,
            "pointer_values_serialized": False,
            "promotion_eligible": False,
        }
        assert opened.receipt.telemetry.lineage_owner_open_success_count == 1
        assert opened.receipt.telemetry.lineage_capability_mint_success_count == 9
        assert opened.receipt.telemetry.lineage_capability_mint_bytes == managed_bytes
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_owner_assignment_interrupt_repairs_krylov_open_close_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    allocations_before = set(runtime.allocations)
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption before Krylov owner-open telemetry assignment"
    )
    injected = False
    cleanup_results: list[Any] = []
    captured_owners: list[HipAllocationOwnerV1] = []
    original_replace = primitives.replace
    original_cleanup = primitives._cleanup_failed_open

    def replace_then_interrupt(value: Any, /, **changes: Any) -> Any:
        nonlocal injected
        result = original_replace(value, **changes)
        if not injected and changes.get("lineage_owner_open_success_count") == 1:
            injected = True
            raise interruption
        return result

    def capture_cleanup_result(**arguments: Any) -> Any:
        owner = arguments["allocation_owner"]
        assert type(owner) is HipAllocationOwnerV1
        captured_owners.append(owner)
        result = original_cleanup(**arguments)
        cleanup_results.append(result)
        return result

    monkeypatch.setattr(primitives, "replace", replace_then_interrupt)
    monkeypatch.setattr(
        primitives,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert injected
        assert len(cleanup_results) == 1
        result = cleanup_results[0]
        assert result.context is None
        assert result.receipt.status == "unavailable"
        telemetry = result.receipt.telemetry
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert len(captured_owners) == 1 and captured_owners[0].closed
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == lineage_before
        primitives.validate_hip_krylov_primitives_context_receipt(result.receipt)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_capability_publication_interrupt_recovers_krylov_byte_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    first_extent = primitives._buffer_views(free)[0].byte_length
    allocations_before = set(runtime.allocations)
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption before Krylov capability byte telemetry assignment"
    )
    injected = False
    cleanup_results: list[Any] = []
    recovered_snapshots: list[tuple[int, int, int, int]] = []
    original_replace = primitives.replace
    original_cleanup = primitives._cleanup_failed_open
    original_recover = (
        HipKrylovPrimitivesExecutionContext._recover_allocation_cleanup_authority
    )

    def replace_then_interrupt(value: Any, /, **changes: Any) -> Any:
        nonlocal injected
        result = original_replace(value, **changes)
        if not injected and "lineage_capability_mint_bytes" in changes:
            injected = True
            raise interruption
        return result

    def capture_cleanup_result(**arguments: Any) -> Any:
        result = original_cleanup(**arguments)
        cleanup_results.append(result)
        return result

    def recover_and_capture(target: HipKrylovPrimitivesExecutionContext) -> None:
        original_recover(target)
        if not recovered_snapshots:
            recovered_snapshots.append(
                (
                    target._initial_managed_device_bytes,
                    target._telemetry.current_device_bytes,
                    target._telemetry.peak_device_bytes,
                    target._telemetry.lineage_capability_mint_bytes,
                )
            )

    monkeypatch.setattr(primitives, "replace", replace_then_interrupt)
    monkeypatch.setattr(
        primitives,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    monkeypatch.setattr(
        HipKrylovPrimitivesExecutionContext,
        "_recover_allocation_cleanup_authority",
        recover_and_capture,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert injected
        assert recovered_snapshots == [
            (first_extent, first_extent, first_extent, first_extent)
        ]
        assert len(cleanup_results) == 1
        result = cleanup_results[0]
        assert result.context is None
        assert result.receipt.status == "unavailable"
        telemetry = result.receipt.telemetry
        assert telemetry.allocation_attempt_count == 1
        assert telemetry.allocation_success_count == 1
        assert telemetry.lineage_capability_mint_success_count == 1
        assert telemetry.lineage_capability_mint_bytes == first_extent
        assert telemetry.peak_device_bytes == first_extent
        assert telemetry.current_device_bytes == 0
        assert telemetry.deallocation_success_count == 1
        assert len(runtime.free_pointer_calls) == 1
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == lineage_before
        primitives.validate_hip_krylov_primitives_context_receipt(result.receipt)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_close_reverses_nine_acks_then_closes_peer_and_releases_parent_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives()
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    peer_owner = context._allocation_owner
    assert type(peer_owner) is HipAllocationOwnerV1
    events: list[str] = []
    original_resolve = HipAllocationOwnerV1.resolve_free_success
    original_owner_close = HipAllocationOwnerV1.close
    original_parent_release = HipFreeSpaceExecutionContext._release_krylov_consumer

    def record_resolution(
        owner: HipAllocationOwnerV1,
        lease: HipAllocationFreeLeaseV1,
    ) -> str:
        outcome = original_resolve(owner, lease)
        assert type(outcome) is str
        if owner is peer_owner:
            assert outcome == "succeeded"
            events.append(f"ack:{lease.capability.role}")
        return outcome

    def record_owner_close(owner: HipAllocationOwnerV1) -> None:
        original_owner_close(owner)
        if owner is peer_owner:
            events.append("peer_owner_closed")

    def record_parent_release(
        parent: HipFreeSpaceExecutionContext,
        token: object,
    ) -> None:
        original_parent_release(parent, token)
        if parent is free:
            events.append("parent_group_released")

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "resolve_free_success",
        record_resolution,
    )
    monkeypatch.setattr(HipAllocationOwnerV1, "close", record_owner_close)
    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_release_krylov_consumer",
        record_parent_release,
    )
    try:
        context.close()

        assert events == [
            *(f"ack:{role}" for role in reversed(_OWNED_ROLES)),
            "peer_owner_closed",
            "parent_group_released",
        ]
        assert context.closed
        assert peer_owner.closed
        assert context.receipt().telemetry.lineage_free_acknowledgement_count == 9
        assert context.receipt().telemetry.lineage_owner_close_success_count == 1
        assert context.receipt().telemetry.lease_release_success_count == 1
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        _assert_parent_capabilities_live(context)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_active_krylov_group_blocks_parent_begin_free_and_close() -> None:
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives()
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    parent_owner = free._allocation_owner
    assert type(parent_owner) is HipAllocationOwnerV1
    parent_capabilities = context._parent_capabilities
    try:
        assert _allocation_states(parent_capabilities) == ("borrowed",) * 5
        with pytest.raises(HipAllocationLineageError) as begin_free:
            parent_owner.begin_free(parent_capabilities[0])
        assert begin_free.value.code == "hip_allocation_free_busy"
        with pytest.raises(HipAllocationLineageError) as owner_close:
            parent_owner.close()
        assert owner_close.value.code == "hip_allocation_owner_busy"
        with pytest.raises(HipFreeSpaceContextError) as parent_close:
            free.close()
        assert parent_close.value.code == "hip_free_space_krylov_consumer_active"

        context.close()
        _assert_parent_capabilities_live(context)
        free.close()
        assert free.closed
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_known_not_freed_retry_reuses_same_lease_without_double_begin_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives_on(runtime)
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    failed_role = "work_x"
    failed_capability = context._owned_capabilities[failed_role]
    failed_pointer = failed_capability.pointer_snapshot
    runtime.arm_classified_free(failed_pointer, _KnownNotFreed)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as first_close:
            context.close()
        assert first_close.value.code == "hip_krylov_primitives_cleanup_failed"
        assert first_close.value.cleanup_owner is context
        assert context.receipt().status == "cleanup_failed"
        assert set(context._owned_capabilities) == {failed_role}
        assert set(context._pending_free_leases) == {failed_role}
        pending = context._pending_free_leases[failed_role]
        assert pending.capability is failed_capability
        assert pending.pointer_snapshot == failed_pointer
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert free._krylov_consumer_token is not None

        def reject_second_begin_free(
            _owner: HipAllocationOwnerV1,
            _capability: object,
        ) -> None:
            raise AssertionError("retry must reuse the pending free lease")

        with monkeypatch.context() as retry_patch:
            retry_patch.setattr(
                HipAllocationOwnerV1,
                "begin_free",
                reject_second_begin_free,
            )
            context.close()

        assert context.closed
        assert runtime.free_pointer_calls.count(failed_pointer) == 2
        telemetry = context.receipt().telemetry
        assert telemetry.deallocation_attempt_count == 10
        assert telemetry.deallocation_success_count == 9
        assert telemetry.lineage_free_acknowledgement_count == 9
        assert telemetry.lineage_free_quarantine_count == 0
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert free._krylov_consumer_token is None
        _assert_parent_capabilities_live(context)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_typed_uncertain_free_is_quarantined_terminally_without_refree() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives_on(runtime)
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    failed_role = "work_x"
    failed_pointer = context._owned_capabilities[failed_role].pointer_snapshot
    failed_bytes = next(
        view.byte_length
        for view in opened.receipt.owned_buffers
        if view.name == failed_role
    )
    runtime.arm_classified_free(failed_pointer, _OutcomeUncertain)
    try:
        context.close()

        terminal = context.receipt()
        assert context.closed
        assert terminal.status == "cleanup_quarantined"
        assert terminal.reason is not None
        assert terminal.reason.code == "hip_krylov_primitives_cleanup_quarantined"
        assert terminal.telemetry.deallocation_attempt_count == 9
        assert terminal.telemetry.deallocation_success_count == 8
        assert terminal.telemetry.lineage_free_acknowledgement_count == 8
        assert terminal.telemetry.lineage_free_quarantine_count == 1
        assert terminal.telemetry.quarantined_device_bytes == failed_bytes
        assert terminal.telemetry.current_device_bytes == failed_bytes
        assert terminal.telemetry.lineage_owner_close_success_count == 1
        assert terminal.telemetry.lease_release_success_count == 1
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert failed_pointer in runtime.allocations
        assert free._krylov_consumer_token is None
        _assert_parent_capabilities_live(context)

        context.close()
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
    finally:
        _close_all(opened, free_open, resident_open, parent_open)

    assert set(runtime.allocations) == {failed_pointer}


def test_partial_malloc_failure_cleans_exact_caps_and_releases_parent_borrow(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    parent_capabilities = tuple(
        free._owned_capabilities[role] for role in _PARENT_BORROWED_ROLES
    )
    runtime_allocations_before = set(runtime.allocations)
    lineage_before = _strong_lineage_registry_snapshot()
    views = primitives._buffer_views(free)
    expected_minted_bytes = sum(view.byte_length for view in views[:3])
    runtime.malloc_failure_at = runtime.malloc_calls + 4
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.kernel is not None
        assert opened.receipt.allocation_lineage is not None
        assert opened.receipt.allocation_lineage.parent_borrowed_capability_count == 5
        assert opened.receipt.allocation_lineage.managed_buffer_count == 3
        assert (
            opened.receipt.allocation_lineage.managed_device_bytes
            == expected_minted_bytes
        )
        assert not opened.receipt.allocation_lineage.all_owned_buffers_managed

        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_attempt_count == 4
        assert telemetry.allocation_success_count == 3
        assert telemetry.lineage_capability_mint_success_count == 3
        assert telemetry.lineage_capability_mint_bytes == expected_minted_bytes
        assert telemetry.deallocation_attempt_count == 3
        assert telemetry.deallocation_success_count == 3
        assert telemetry.lineage_free_acknowledgement_count == 3
        assert telemetry.lineage_free_quarantine_count == 0
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.sync_attempt_count == 1
        assert telemetry.sync_success_count == 1
        assert telemetry.module_owner_acquired_count == 1
        assert telemetry.module_close_attempt_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_attempt_count == 1
        assert telemetry.lease_release_success_count == 1
        assert telemetry.current_device_bytes == 0
        assert set(runtime.allocations) == runtime_allocations_before
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert _allocation_states(parent_capabilities) == ("live",) * 5
        assert _strong_lineage_registry_snapshot() == lineage_before
        primitives.validate_hip_krylov_primitives_context_receipt(opened.receipt)
        for field in (
            "deallocation_attempt_count",
            "module_close_attempt_count",
            "lease_release_attempt_count",
        ):
            forged = _rehash_krylov_context_receipt(
                replace(
                    opened.receipt,
                    telemetry=replace(
                        telemetry,
                        **{field: getattr(telemetry, field) + 1},
                    ),
                )
            )
            with pytest.raises(HipKrylovPrimitivesContextError):
                primitives.validate_hip_krylov_primitives_context_receipt(forged)
        forged_module_lifecycle = _rehash_krylov_context_receipt(
            replace(
                opened.receipt,
                telemetry=replace(
                    telemetry,
                    module_owner_acquired_count=0,
                    module_close_attempt_count=0,
                    module_close_success_count=0,
                ),
            )
        )
        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(
                forged_module_lifecycle
            )
    finally:
        _close_chain(free_open, resident_open, parent_open)

    assert _strong_lineage_registry_snapshot() == _lineage_registry_guard


def test_post_resolve_interruption_retries_terminal_without_second_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives_on(runtime)
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    failed_role = "jacobi_inverse"
    failed_capability = context._owned_capabilities[failed_role]
    failed_pointer = failed_capability.pointer_snapshot
    original_resolve = HipAllocationOwnerV1.resolve_free_success
    injected = False
    resolved: list[tuple[str, str]] = []

    def resolve_then_interrupt_once(
        owner: HipAllocationOwnerV1,
        lease: HipAllocationFreeLeaseV1,
    ) -> str:
        nonlocal injected
        outcome = original_resolve(owner, lease)
        assert type(outcome) is str
        resolved.append((lease.capability.role, outcome))
        if lease.capability is failed_capability and not injected:
            injected = True
            raise _ResolveTerminalInterrupt(
                "injected interruption after terminal free resolution"
            )
        return outcome

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "resolve_free_success",
        resolve_then_interrupt_once,
    )
    try:
        with pytest.raises(_ResolveTerminalInterrupt):
            context.close()
        assert context.receipt().status == "cleanup_failed"
        assert injected
        assert set(context._owned_capabilities) == {failed_role}
        assert set(context._pending_free_leases) == {failed_role}
        pending = context._pending_free_leases[failed_role]
        assert pending.capability is failed_capability
        assert pending.pointer_snapshot == failed_pointer
        assert context._cleanup_dispositions[failed_role] == ("external_free_succeeded")
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert failed_pointer not in runtime.allocations
        assert context._free_acknowledged_roles == set(_OWNED_ROLES) - {failed_role}
        assert _free_terminal_snapshot(pending) == ("succeeded", False, False)
        first_telemetry = context.receipt().telemetry
        assert first_telemetry.deallocation_attempt_count == 9
        assert first_telemetry.deallocation_success_count == 9
        assert first_telemetry.lineage_free_acknowledgement_count == 8

        context.close()

        assert context.closed
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert context._cleanup_dispositions[failed_role] == "terminal"
        assert resolved.count((failed_role, "succeeded")) == 2
        assert _free_terminal_snapshot(pending) == ("succeeded", False, False)
        telemetry = context.receipt().telemetry
        assert telemetry.deallocation_attempt_count == 9
        assert telemetry.deallocation_success_count == 9
        assert telemetry.lineage_free_acknowledgement_count == 9
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert free._krylov_consumer_token is None
        _assert_parent_capabilities_live(context)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_malloc_base_exception_quarantines_orphan_and_domain_allocations() -> None:
    runtime = _UncertainMallocRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    views = primitives._buffer_views(free)
    expected_minted_bytes = sum(view.byte_length for view in views[:3])
    orphan_bytes = views[3].byte_length
    free_parent_pointers = {
        capability.pointer_snapshot for capability in free._owned_capabilities.values()
    }
    kernel = FakeKrylovPrimitivesKernel(runtime)
    free_calls_before = tuple(runtime.free_pointer_calls)
    runtime.arm_uncertain_malloc(after_successes=3)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "cleanup_quarantined"
        assert opened.receipt.reason is not None
        assert opened.receipt.reason.code == (
            "hip_krylov_primitives_cleanup_quarantined"
        )
        assert _runtime_domain_poison_snapshot(runtime)[1:] == (True, True)
        assert len(runtime.post_arm_pointers) == 3
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert set(runtime.post_arm_pointers) <= set(runtime.allocations)

        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_attempt_count == 4
        assert telemetry.allocation_success_count == 3
        assert telemetry.lineage_capability_mint_success_count == 3
        assert telemetry.lineage_capability_mint_bytes == expected_minted_bytes
        assert telemetry.deallocation_attempt_count == 0
        assert telemetry.deallocation_success_count == 0
        assert telemetry.lineage_free_acknowledgement_count == 0
        assert telemetry.lineage_free_quarantine_count == 3
        assert telemetry.lineage_orphan_acknowledgement_count == 0
        assert telemetry.lineage_orphan_quarantine_count == 1
        assert telemetry.quarantined_device_bytes == expected_minted_bytes
        assert telemetry.unknown_malloc_outcome_count == 1
        assert telemetry.unknown_requested_bytes == orphan_bytes
        assert telemetry.current_device_bytes == expected_minted_bytes
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert kernel.closed
        assert free._krylov_consumer_token is None
    finally:
        if opened.context is not None and not opened.context.closed:
            _retire_poisoned_context_for_teardown(opened.context)
        _close_chain(free_open, resident_open, parent_open)

    assert set(runtime.allocations) == (
        set(runtime.post_arm_pointers) | free_parent_pointers
    )


def test_parent_consumer_handoff_interrupt_releases_group_borrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    parent_capabilities = tuple(
        free._owned_capabilities[role] for role in _PARENT_BORROWED_ROLES
    )
    allocations_before = set(runtime.allocations)
    free_calls_before = tuple(runtime.free_pointer_calls)
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption after parent Krylov consumer publication"
    )
    published_tokens: list[object] = []
    original_acquire = HipFreeSpaceExecutionContext._acquire_krylov_consumer_for_apply

    def acquire_then_interrupt(
        parent: HipFreeSpaceExecutionContext,
        source_apply_arg: Any,
        token: object | None = None,
    ) -> object:
        published = original_acquire(parent, source_apply_arg, token)
        assert token is not None
        assert published is token
        published_tokens.append(published)
        raise interruption

    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_acquire_krylov_consumer_for_apply",
        acquire_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert len(published_tokens) == 1
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        assert free._krylov_consumer_capability_snapshot is None
        assert _allocation_states(parent_capabilities) == ("live",) * 5
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert _strong_lineage_registry_snapshot() == lineage_before
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_peer_owner_handoff_interrupt_recovers_and_closes_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    parent_capabilities = tuple(
        free._owned_capabilities[role] for role in _PARENT_BORROWED_ROLES
    )
    allocations_before = set(runtime.allocations)
    free_calls_before = tuple(runtime.free_pointer_calls)
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption after Krylov peer owner handoff"
    )
    captured: list[tuple[HipAllocationOwnerV1, list[HipAllocationOwnerV1 | None]]] = []
    original_open_owner = HipFreeSpaceExecutionContext._open_krylov_allocation_owner

    def open_owner_then_interrupt(
        parent: HipFreeSpaceExecutionContext,
        token: object,
        owner_role: str,
        *,
        _handoff: list[HipAllocationOwnerV1 | None] | None = None,
    ) -> HipAllocationOwnerV1:
        owner = original_open_owner(
            parent,
            token,
            owner_role,
            _handoff=_handoff,
        )
        assert _handoff is not None
        assert _handoff == [owner]
        captured.append((owner, _handoff))
        raise interruption

    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_open_krylov_allocation_owner",
        open_owner_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert len(captured) == 1
        owner, handoff = captured[0]
        assert handoff == [owner]
        assert owner.closed
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        assert _allocation_states(parent_capabilities) == ("live",) * 5
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert _strong_lineage_registry_snapshot() == lineage_before
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_allocate_handoff_interrupt_recovers_capability_and_frees_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    parent_capabilities = tuple(
        free._owned_capabilities[role] for role in _PARENT_BORROWED_ROLES
    )
    allocations_before = set(runtime.allocations)
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption after Krylov capability publication"
    )
    captured: list[tuple[HipAllocationOwnerV1, Any]] = []
    original_allocate = HipAllocationOwnerV1.allocate

    def allocate_then_interrupt(
        owner: HipAllocationOwnerV1,
        role: str,
        nbytes: int,
        element_type: str,
    ) -> Any:
        capability = original_allocate(owner, role, nbytes, element_type)
        captured.append((owner, capability))
        raise interruption

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "allocate",
        allocate_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert len(captured) == 1
        owner, capability = captured[0]
        assert capability.role == _OWNED_ROLES[0]
        pointer = capability.pointer_snapshot
        assert runtime.free_pointer_calls.count(pointer) == 1
        assert pointer not in runtime.allocations
        assert owner.closed
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        assert _allocation_states(parent_capabilities) == ("live",) * 5
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == lineage_before
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_begin_free_handoff_interrupt_retry_recovers_same_lease_without_refree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert context is not None
    target_role = "error_flag"
    target_capability = context._owned_capabilities[target_role]
    target_pointer = target_capability.pointer_snapshot
    interruption = _HandoffInterrupt(
        "injected interruption after begin_free lease publication"
    )
    captured_leases: list[HipAllocationFreeLeaseV1] = []
    target_begin_calls = 0
    original_begin_free = HipAllocationOwnerV1.begin_free

    def begin_free_then_interrupt(
        owner: HipAllocationOwnerV1,
        capability: Any,
    ) -> HipAllocationFreeLeaseV1:
        nonlocal target_begin_calls
        if capability is not target_capability:
            return original_begin_free(owner, capability)
        target_begin_calls += 1
        if target_begin_calls > 1:
            raise AssertionError("retry must recover the published free lease")
        lease = original_begin_free(owner, capability)
        captured_leases.append(lease)
        raise interruption

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "begin_free",
        begin_free_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            context.close()

        assert caught.value is interruption
        assert target_begin_calls == 1
        assert len(captured_leases) == 1
        lease = captured_leases[0]
        assert target_role not in context._pending_free_leases
        assert _free_terminal_snapshot(lease) == (None, True, True)
        assert runtime.free_pointer_calls.count(target_pointer) == 0
        assert context.receipt().status == "cleanup_failed"
        assert free._krylov_consumer_token is not None

        context.close()

        assert context.closed
        assert target_begin_calls == 1
        assert runtime.free_pointer_calls.count(target_pointer) == 1
        assert target_pointer not in runtime.allocations
        assert _free_terminal_snapshot(lease) == ("succeeded", False, False)
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        _assert_parent_capabilities_live(context)
        assert _strong_lineage_registry_snapshot() == lineage_before

        context.close()
        assert runtime.free_pointer_calls.count(target_pointer) == 1
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_invalid_non_pointer_malloc_quarantines_unknown_without_free_none() -> None:
    runtime = _InvalidNonPointerMallocRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    parent_capabilities = tuple(
        free._owned_capabilities[role] for role in _PARENT_BORROWED_ROLES
    )
    allocations_before = set(runtime.allocations)
    free_calls_before = tuple(runtime.free_pointer_calls)
    lineage_before = _strong_lineage_registry_snapshot()
    first_view = primitives._buffer_views(free)[0]
    kernel = FakeKrylovPrimitivesKernel(runtime)
    runtime.arm_invalid_malloc()
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "cleanup_quarantined"
        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_attempt_count == 1
        assert telemetry.allocation_success_count == 0
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.deallocation_attempt_count == 0
        assert telemetry.deallocation_success_count == 0
        assert telemetry.lineage_orphan_acknowledgement_count == 0
        assert telemetry.lineage_orphan_quarantine_count == 1
        assert telemetry.quarantined_device_bytes == 0
        assert telemetry.unknown_malloc_outcome_count == 1
        assert telemetry.unknown_requested_bytes == first_view.byte_length
        assert telemetry.current_device_bytes == 0
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert None not in runtime.free_pointer_calls
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert set(runtime.allocations) == allocations_before
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert free._krylov_consumer_borrow_lease is None
        assert _allocation_states(parent_capabilities) == ("live",) * 5
        assert _strong_lineage_registry_snapshot() == lineage_before
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_cleanup_quarantined_receipt_rejects_current_quarantine_byte_mismatch() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives_on(runtime)
    context = opened.context
    assert context is not None
    failed_pointer = context._owned_capabilities["work_x"].pointer_snapshot
    runtime.arm_classified_free(failed_pointer, _OutcomeUncertain)
    try:
        context.close()
        terminal = context.receipt()
        assert terminal.status == "cleanup_quarantined"
        assert terminal.telemetry.current_device_bytes == (
            terminal.telemetry.quarantined_device_bytes
        )
        forged_telemetry = replace(
            terminal.telemetry,
            current_device_bytes=terminal.telemetry.current_device_bytes + 1,
        )
        forged = replace(
            terminal,
            telemetry=forged_telemetry,
            context_receipt_hash=primitives._ZERO_HASH,
        )
        forged = replace(
            forged,
            context_receipt_hash=primitives.canonical_hash(
                primitives._context_payload(forged, include_hash=False)
            ),
        )

        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            primitives.validate_hip_krylov_primitives_context_receipt(forged)
        assert rejected.value.code == "hip_krylov_primitives_context_status_invalid"
        assert rejected.value.path == "/status"
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_rehashed_ready_attempt_and_terminal_managed_byte_forgeries_fail_closed() -> (
    None
):
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives()
    context = opened.context
    assert context is not None and opened.ready
    try:
        forged_ready = _rehash_krylov_context_receipt(
            replace(
                opened.receipt,
                telemetry=replace(
                    opened.receipt.telemetry,
                    allocation_attempt_count=(
                        opened.receipt.telemetry.allocation_attempt_count + 1
                    ),
                ),
            )
        )
        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(forged_ready)

        context.close()
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.allocation_lineage is not None
        forged_terminal = _rehash_krylov_context_receipt(
            replace(
                terminal,
                allocation_lineage=replace(
                    terminal.allocation_lineage,
                    managed_device_bytes=(
                        terminal.allocation_lineage.managed_device_bytes + 1
                    ),
                ),
                telemetry=replace(
                    terminal.telemetry,
                    lineage_capability_mint_bytes=(
                        terminal.telemetry.lineage_capability_mint_bytes + 1
                    ),
                ),
            )
        )
        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(forged_terminal)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_rehashed_terminal_quarantine_byte_forgery_fails_closed() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        free_open,
        _,
        _,
        opened,
    ) = _open_primitives_on(runtime)
    context = opened.context
    assert context is not None
    failed_pointer = context._owned_capabilities["work_x"].pointer_snapshot
    runtime.arm_classified_free(failed_pointer, _OutcomeUncertain)
    try:
        context.close()
        terminal = context.receipt()
        assert terminal.status == "cleanup_quarantined"
        forged = _rehash_krylov_context_receipt(
            replace(
                terminal,
                telemetry=replace(
                    terminal.telemetry,
                    quarantined_device_bytes=(
                        terminal.telemetry.quarantined_device_bytes + 1
                    ),
                    current_device_bytes=(terminal.telemetry.current_device_bytes + 1),
                ),
            )
        )

        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(forged)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_rehashed_unknown_requested_byte_forgery_fails_closed() -> None:
    runtime = _UncertainMallocRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    runtime.arm_uncertain_malloc(after_successes=0)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        terminal = opened.receipt
        assert opened.context is None
        assert terminal.status == "cleanup_quarantined"
        assert terminal.telemetry.unknown_malloc_outcome_count == 1
        forged = _rehash_krylov_context_receipt(
            replace(
                terminal,
                telemetry=replace(
                    terminal.telemetry,
                    unknown_requested_bytes=(
                        terminal.telemetry.unknown_requested_bytes + 1
                    ),
                ),
            )
        )

        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(forged)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_rehashed_ownerless_terminal_work_telemetry_forgeries_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()

    def fail_owner_open(*_: Any, **__: Any) -> Any:
        raise RuntimeError("injected pre-owner Krylov open failure")

    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_open_krylov_allocation_owner",
        fail_owner_open,
    )
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
    )
    try:
        terminal = opened.receipt
        assert opened.context is None
        assert terminal.status == "unavailable"
        assert terminal.allocation_lineage is None
        assert terminal.telemetry.lineage_owner_open_success_count == 0
        for field in (
            "allocation_attempt_count",
            "deallocation_attempt_count",
            "peak_device_bytes",
            "h2d_operation_attempt_count",
            "kernel_launch_attempt_count",
            "d2h_operation_attempt_count",
            "sync_attempt_count",
        ):
            assert getattr(terminal.telemetry, field) == 0
            forged = _rehash_krylov_context_receipt(
                replace(
                    terminal,
                    telemetry=replace(terminal.telemetry, **{field: 1}),
                )
            )
            with pytest.raises(HipKrylovPrimitivesContextError):
                primitives.validate_hip_krylov_primitives_context_receipt(forged)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_rehashed_first_malloc_failure_operation_stage_forgeries_fail_closed() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    runtime.malloc_failure_at = runtime.malloc_calls + 1
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        terminal = opened.receipt
        telemetry = terminal.telemetry
        assert opened.context is None
        assert terminal.status == "unavailable"
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.lineage_orphan_acknowledgement_count == 0
        assert telemetry.lineage_orphan_quarantine_count == 0
        for field in (
            "h2d_operation_attempt_count",
            "kernel_launch_attempt_count",
            "d2h_operation_attempt_count",
            "sync_attempt_count",
        ):
            assert getattr(telemetry, field) == 0
            forged = _rehash_krylov_context_receipt(
                replace(
                    terminal,
                    telemetry=replace(telemetry, **{field: 1}),
                )
            )
            with pytest.raises(HipKrylovPrimitivesContextError):
                primitives.validate_hip_krylov_primitives_context_receipt(forged)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_rehashed_pointerful_orphan_cannot_remove_cleanup_sync() -> None:
    runtime = _MisalignedMallocRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    allocations_before = set(runtime.allocations)
    kernel = FakeKrylovPrimitivesKernel(runtime)
    runtime.arm_misaligned_malloc()
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        terminal = opened.receipt
        telemetry = terminal.telemetry
        pointer = runtime.misaligned_pointer
        assert type(pointer) is int
        assert opened.context is None
        assert terminal.status == "unavailable"
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.lineage_orphan_acknowledgement_count == 1
        assert telemetry.lineage_orphan_quarantine_count == 0
        assert telemetry.sync_attempt_count == 1
        assert telemetry.sync_success_count == 1
        assert runtime.free_pointer_calls.count(pointer) == 1
        assert pointer not in runtime.allocations
        assert set(runtime.allocations) == allocations_before
        primitives.validate_hip_krylov_primitives_context_receipt(terminal)

        forged = _rehash_krylov_context_receipt(
            replace(
                terminal,
                telemetry=replace(
                    telemetry,
                    sync_attempt_count=0,
                    sync_success_count=0,
                ),
            )
        )
        with pytest.raises(HipKrylovPrimitivesContextError):
            primitives.validate_hip_krylov_primitives_context_receipt(forged)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_ready_receipt_validation_failure_reuses_preallocated_exact_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    validation_error = RuntimeError("injected ready receipt validation failure")
    ready_contexts: list[HipKrylovPrimitivesExecutionContext] = []
    cleanup_contexts: list[HipKrylovPrimitivesExecutionContext] = []
    opened_owners: list[HipAllocationOwnerV1] = []
    validation_calls = 0
    original_validate = primitives.validate_hip_krylov_primitives_context_receipt
    original_cleanup = primitives._cleanup_failed_open
    original_open_owner = HipFreeSpaceExecutionContext._open_krylov_allocation_owner
    original_initializer = primitives._HIP_KRYLOV_PRIMITIVES_CONTEXT_INITIALIZER

    def capture_ready_initializer(
        context: HipKrylovPrimitivesExecutionContext,
        **arguments: Any,
    ) -> None:
        ready_contexts.append(context)
        original_initializer(context, **arguments)

    def fail_ready_validation_once(
        receipt: Any,
        *,
        expected_context: HipKrylovPrimitivesExecutionContext | None = None,
    ) -> Any:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            raise validation_error
        return original_validate(receipt, expected_context=expected_context)

    def capture_cleanup_context(**arguments: Any) -> Any:
        existing = arguments["existing_context"]
        assert type(existing) is HipKrylovPrimitivesExecutionContext
        cleanup_contexts.append(existing)
        return original_cleanup(**arguments)

    def capture_open_owner(
        parent: HipFreeSpaceExecutionContext,
        token: object,
        owner_role: str,
        *,
        _handoff: list[HipAllocationOwnerV1 | None] | None = None,
    ) -> HipAllocationOwnerV1:
        owner = original_open_owner(
            parent,
            token,
            owner_role,
            _handoff=_handoff,
        )
        opened_owners.append(owner)
        return owner

    monkeypatch.setattr(
        primitives,
        "validate_hip_krylov_primitives_context_receipt",
        fail_ready_validation_once,
    )
    monkeypatch.setattr(
        primitives,
        "_HIP_KRYLOV_PRIMITIVES_CONTEXT_INITIALIZER",
        capture_ready_initializer,
    )
    monkeypatch.setattr(
        primitives,
        "_cleanup_failed_open",
        capture_cleanup_context,
    )
    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_open_krylov_allocation_owner",
        capture_open_owner,
    )
    result = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert result.context is None
        assert result.receipt.status == "unavailable"
        assert len(ready_contexts) == 1
        assert cleanup_contexts == ready_contexts
        assert len(opened_owners) == 1
        assert ready_contexts[0]._allocation_owner_snapshot is opened_owners[0]
        assert opened_owners[0].closed
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert len(runtime.free_pointer_calls) == len(_OWNED_ROLES)
        assert len(set(runtime.free_pointer_calls)) == len(_OWNED_ROLES)
        assert _strong_lineage_registry_snapshot() == lineage_before
        primitives.validate_hip_krylov_primitives_context_receipt(result.receipt)
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_cleanup_constructor_failure_uses_captured_original_initializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    interruption = _HandoffInterrupt(
        "injected interruption after Krylov opening synchronization"
    )
    cleanup_constructor_error = MemoryError(
        "injected Krylov cleanup constructor failure"
    )
    sync_interrupted = False
    cleanup_initializer_failures = 0
    cleanup_results: list[Any] = []
    original_synchronize = type(runtime).synchronize
    original_initializer = HipKrylovPrimitivesExecutionContext.__init__
    original_cleanup = primitives._cleanup_failed_open

    def synchronize_then_interrupt(target: Any, stream: Any) -> None:
        nonlocal sync_interrupted
        original_synchronize(target, stream)
        if not sync_interrupted:
            sync_interrupted = True
            raise interruption

    def fail_cleanup_initializer_once(
        context: HipKrylovPrimitivesExecutionContext,
        **arguments: Any,
    ) -> None:
        nonlocal cleanup_initializer_failures
        if (
            arguments["opening_status"] == "cleanup_failed"
            and cleanup_initializer_failures == 0
        ):
            cleanup_initializer_failures += 1
            raise cleanup_constructor_error
        original_initializer(context, **arguments)

    def capture_cleanup_result(**arguments: Any) -> Any:
        result = original_cleanup(**arguments)
        cleanup_results.append(result)
        return result

    monkeypatch.setattr(type(runtime), "synchronize", synchronize_then_interrupt)
    monkeypatch.setattr(
        HipKrylovPrimitivesExecutionContext,
        "__init__",
        fail_cleanup_initializer_once,
    )
    monkeypatch.setattr(
        primitives,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert sync_interrupted
        assert cleanup_initializer_failures == 1
        assert len(cleanup_results) == 1
        result = cleanup_results[0]
        assert result.context is None
        assert result.receipt.status == "unavailable"
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert len(runtime.free_pointer_calls) == len(_OWNED_ROLES)
        assert len(set(runtime.free_pointer_calls)) == len(_OWNED_ROLES)
        assert _strong_lineage_registry_snapshot() == lineage_before
        primitives.validate_hip_krylov_primitives_context_receipt(result.receipt)
    finally:
        _close_chain(free_open, resident_open, parent_open)


@pytest.mark.parametrize("mutated_mapping", ["pointer", "capability"])
def test_mutated_owned_mapping_fails_first_close_then_registry_recovers(
    monkeypatch: pytest.MonkeyPatch,
    mutated_mapping: str,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        free_open,
    ) = _open_free_space_on(runtime)
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    lineage_before = _strong_lineage_registry_snapshot()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert context is not None
    target_role = "work_x"
    original_pointer = context._pointers[target_role]
    original_capability = context._owned_capabilities[target_role]
    owned_pointers = tuple(
        capability.pointer_snapshot
        for capability in context._owned_capabilities.values()
    )
    recovered: list[bool] = []
    original_recover = (
        HipKrylovPrimitivesExecutionContext._recover_allocation_cleanup_authority
    )

    def recover_and_assert(target: HipKrylovPrimitivesExecutionContext) -> None:
        original_recover(target)
        recovered.append(
            target._pointers[target_role] is original_pointer
            and target._owned_capabilities[target_role] is original_capability
        )

    monkeypatch.setattr(
        HipKrylovPrimitivesExecutionContext,
        "_recover_allocation_cleanup_authority",
        recover_and_assert,
    )
    if mutated_mapping == "pointer":
        context._pointers[target_role] = object()
    else:
        context._owned_capabilities[target_role] = context._owned_capabilities["work_y"]
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as failed_close:
            context.close()
        assert failed_close.value.code == (
            "hip_krylov_primitives_cleanup_authority_invalid"
        )
        assert failed_close.value.cleanup_owner is context
        assert context.receipt().status == "cleanup_failed"
        assert not runtime.free_pointer_calls
        assert free._krylov_consumer_token is not None

        context.close()

        assert recovered == [True]
        assert context.closed
        assert kernel.closed
        assert free._krylov_consumer_token is None
        assert all(
            runtime.free_pointer_calls.count(pointer) == 1 for pointer in owned_pointers
        )
        assert _strong_lineage_registry_snapshot() == lineage_before
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        primitives.validate_hip_krylov_primitives_context_receipt(
            terminal,
            expected_context=context,
        )
    finally:
        _close_all(opened, free_open, resident_open, parent_open)
