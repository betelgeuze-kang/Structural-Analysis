from __future__ import annotations

import ctypes
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    free_space as free_space_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    hip_allocation_lineage as lineage,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
    HipFreeSpaceExecutionContext,
    open_hip_free_space_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
)
from structural_analysis.engine_v2.backends.hip.context import (
    HipContextError,
    HipFreeKnownNotFreedError,
    HipFreeOutcomeUncertainError,
)

from tests.test_engine_v2_hip_free_space_context_v1 import (
    FakeFreeSpaceKernel,
    _close_chain,
    _open_free_space,
)
from tests.test_engine_v2_hip_resident_csr_v1 import (
    TrackingRuntime,
    _open_resident,
)


_OWNED_ROLES = (
    "free_dofs",
    "global_to_free",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
    "reduced_csr_values",
    "reduced_state",
    "reduced_load",
    "reduced_direction",
    "reduced_residual",
    "reduced_jvp",
    "error_flag",
)
_KRYLOV_PARENT_ROLES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
    "reduced_direction",
    "reduced_jvp",
)


_KnownNotFreed = HipFreeKnownNotFreedError
_OutcomeUncertain = HipFreeOutcomeUncertainError


def _rehash_free_space_context_receipt(receipt: Any) -> Any:
    return replace(
        receipt,
        context_receipt_hash=free_space_module.canonical_hash(
            free_space_module._context_payload(receipt, include_hash=False)
        ),
    )


class _MallocOutcomeUncertain(BaseException):
    pass


class _ResolveTerminalInterrupt(BaseException):
    pass


class _HandoffInterrupt(KeyboardInterrupt):
    pass


class _GenericInjectedFreeError(HipContextError):
    pass


class _NativeShapedClassifiedFreeRuntime(TrackingRuntime):
    """HIP-shaped injected runtime with one explicitly classified free result."""

    def __init__(self) -> None:
        super().__init__()
        self.free_pointer_calls: list[int] = []
        self._classified_pointer: int | None = None
        self._classified_error: type[HipContextError] | None = None
        self._classification_fired = False

    def arm_classified_free(
        self,
        pointer: int,
        error_type: type[HipContextError],
    ) -> None:
        self._classified_pointer = pointer
        self._classified_error = error_type
        self._classification_fired = False

    def free(self, pointer: int) -> None:
        self.free_pointer_calls.append(pointer)
        if (
            pointer == self._classified_pointer
            and self._classified_error is not None
            and not self._classification_fired
        ):
            self._classification_fired = True
            self.free_calls += 1
            raise self._classified_error(
                "hip_device_access_failed",
                "injected typed hipFree outcome",
            )
        super().free(pointer)


class _MisalignedMallocRuntime(_NativeShapedClassifiedFreeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._misalign_next_malloc = False
        self.misaligned_pointer: int | None = None

    def arm_misaligned_malloc(self) -> None:
        self._misalign_next_malloc = True

    def malloc(self, byte_length: int) -> int:
        pointer = super().malloc(byte_length)
        if not self._misalign_next_malloc:
            return pointer
        self._misalign_next_malloc = False
        misaligned = pointer + 2
        self.allocations[misaligned] = self.allocations.pop(pointer)
        self.misaligned_pointer = misaligned
        return misaligned


class _UncertainMallocRuntime(_NativeShapedClassifiedFreeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._remaining_successes: int | None = None
        self.post_arm_pointers: list[int] = []

    def arm_uncertain_malloc(self, *, after_successes: int) -> None:
        self._remaining_successes = after_successes

    def malloc(self, byte_length: int) -> int:
        remaining = self._remaining_successes
        if remaining == 0:
            self._remaining_successes = None
            raise _MallocOutcomeUncertain(
                "injected post-call allocator outcome interruption"
            )
        pointer = super().malloc(byte_length)
        if remaining is not None:
            self._remaining_successes = remaining - 1
            self.post_arm_pointers.append(pointer)
        return pointer


class _RangeOverflowMallocRuntime(_NativeShapedClassifiedFreeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._overflow_next_malloc = False
        self.overflow_pointer: int | None = None

    def arm_range_overflow_malloc(self) -> None:
        self._overflow_next_malloc = True

    def malloc(self, byte_length: int) -> int:
        pointer = super().malloc(byte_length)
        if not self._overflow_next_malloc:
            return pointer
        self._overflow_next_malloc = False
        uintptr_max = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
        overflow_pointer = uintptr_max - 3
        self.allocations[overflow_pointer] = self.allocations.pop(pointer)
        self.overflow_pointer = overflow_pointer
        return overflow_pointer


def _pointer_value(base: object) -> int:
    if type(base) is int:
        return base
    if type(base) is ctypes.c_void_p and type(base.value) is int:
        return base.value
    raise AssertionError("expected an exact HIP allocation base")


def _strong_lineage_registry_snapshot() -> dict[str, tuple[tuple[Any, ...], ...]]:
    """Copy primitive registry facts while holding the lineage registry lock."""

    with lineage._LOCK:
        owners = tuple(
            sorted(
                (
                    key,
                    row.owner_role,
                    row.device_ordinal,
                    row.closed,
                    len(row.allocating_threads),
                )
                for key, row in lineage._OWNERS.items()
            )
        )
        allocations = tuple(
            sorted(
                (
                    key,
                    id(row.owner),
                    row.role,
                    row.pointer,
                    row.end,
                    row.nbytes,
                    row.element_type,
                    row.generation,
                    row.state,
                    None if row.borrow_lease is None else id(row.borrow_lease),
                    None if row.free_lease is None else id(row.free_lease),
                )
                for key, row in lineage._ALLOCATIONS.items()
            )
        )
        borrows = tuple(
            sorted(
                (key, row.allocation_ids, row.released)
                for key, row in lineage._BORROWS.items()
            )
        )
        frees = tuple(
            sorted(
                (key, row.allocation_id, id(row.owner), row.state)
                for key, row in lineage._FREES.items()
            )
        )
        orphans = tuple(
            sorted(
                (
                    key,
                    id(row.owner),
                    row.role,
                    row.nbytes,
                    row.element_type,
                    row.state,
                    row.pointer,
                    row.end,
                    row.conflicted,
                )
                for key, row in lineage._ORPHANS.items()
            )
        )
    return {
        "owners": owners,
        "allocations": allocations,
        "borrows": borrows,
        "frees": frees,
        "orphans": orphans,
    }


def _allocation_states(capabilities: tuple[object, ...]) -> tuple[str, ...]:
    with lineage._LOCK:
        return tuple(
            lineage._ALLOCATIONS[id(capability)].state for capability in capabilities
        )


def _runtime_domain_poison_snapshot(runtime: object) -> tuple[str, bool, bool]:
    with lineage._LOCK:
        matches = tuple(
            domain
            for representative_ref, domain in lineage._INJECTED_DOMAINS
            if representative_ref() is runtime
        )
        assert len(matches) == 1
        domain = matches[0]
        domain_id = domain.domain_id
        return (
            domain_id,
            domain.is_device_poisoned(0),
            (
                domain_id,
                0,
            )
            in lineage._POISONED_DOMAINS,
        )


def _free_terminal_snapshot(
    lease: HipAllocationFreeLeaseV1,
) -> tuple[str | None, bool, bool]:
    with lineage._LOCK:
        terminal = lineage._CONSUMED_FREES.get(lease)
        return (
            None if terminal is None else terminal[1],
            id(lease) in lineage._FREES,
            id(lease.capability) in lineage._ALLOCATIONS,
        )


def _orphan_terminal_snapshot(lease: HipAllocationOrphanLeaseV1) -> str | None:
    with lineage._LOCK:
        terminal = lineage._CONSUMED_ORPHANS.get(lease)
        return None if terminal is None else terminal[1]


@pytest.fixture(autouse=True)
def _lineage_registry_guard() -> Iterator[dict[str, tuple[tuple[Any, ...], ...]]]:
    baseline = _strong_lineage_registry_snapshot()
    yield baseline
    assert _strong_lineage_registry_snapshot() == baseline


def _open_free_space_on(runtime: TrackingRuntime) -> tuple[Any, ...]:
    *prefix, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    return (
        *prefix,
        runtime,
        parent_open,
        resident_open,
        overlay,
        kernel,
        opened,
    )


def _close_resident_chain(resident_open: Any, parent_open: Any) -> None:
    resident = resident_open.context
    parent = parent_open.context
    if resident is not None and resident._downstream_consumer_token is not None:
        resident._release_downstream_consumer(resident._downstream_consumer_token)
    if resident is not None and not resident.closed:
        resident.close()
    if parent is not None and not parent.closed:
        parent.close()


def test_ready_context_owns_exact_capabilities_and_close_retires_lineage(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    *_, runtime, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    assert context is not None and resident is not None and opened.ready
    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    try:
        views = {view.name: view for view in opened.receipt.owned_buffers}
        assert tuple(context._owned_capabilities) == _OWNED_ROLES
        assert tuple(views) == _OWNED_ROLES
        assert len(context._owned_capabilities) == 12

        for role in _OWNED_ROLES:
            capability = context._owned_capabilities[role]
            view = views[role]
            raw_base = context._pointers[role]
            assert capability.role == role
            assert capability.nbytes == view.byte_length
            assert capability.element_type == ("i32" if view.dtype == "<i4" else "f64")
            assert capability.runtime_owner is runtime
            assert capability.device_ordinal == resident._device_ordinal_snapshot
            assert capability.base is raw_base
            assert capability.pointer_snapshot == _pointer_value(raw_base)
            assert capability.evidence_scope == "foundation_non_promoting"
            assert capability.promotion_eligible is False

        managed_bytes = sum(view.byte_length for view in views.values())
        assert opened.receipt.allocation_lineage is not None
        assert opened.receipt.allocation_lineage.to_dict() == {
            "capability_profile": "foundation_non_promoting",
            "evidence_scope": "foundation_non_promoting",
            "owner_role": "free_space_owned_buffers",
            "runtime_device_bound": True,
            "managed_buffer_count": 12,
            "managed_device_bytes": managed_bytes,
            "all_owned_buffers_managed": True,
            "pointer_values_serialized": False,
            "promotion_eligible": False,
        }
        assert opened.receipt.telemetry.lineage_capability_mint_success_count == 12
        assert opened.receipt.telemetry.lineage_capability_mint_bytes == managed_bytes

        context.close()

        closed = context.receipt()
        assert closed.status == "context_closed"
        assert closed.telemetry.deallocation_success_count == 12
        assert closed.telemetry.lineage_free_acknowledgement_count == 12
        assert closed.telemetry.lineage_free_quarantine_count == 0
        assert closed.telemetry.lineage_owner_close_success_count == 1
        assert closed.telemetry.current_device_bytes == 0
        assert context._allocation_owner_closed
        assert owner._closed_snapshot is True
        assert not context._pointers
        assert not context._owned_capabilities
        assert not context._pending_free_leases
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_krylov_semantic_token_borrows_exact_parent_group_and_restores_live() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    token: object | None = None
    try:
        expected = tuple(
            context._owned_capabilities[role] for role in _KRYLOV_PARENT_ROLES
        )
        token = context._acquire_krylov_consumer()
        lease = context._krylov_consumer_borrow_lease
        capability_snapshot = context._krylov_consumer_capability_snapshot
        assert lease is not None
        assert capability_snapshot is not None
        assert lease.borrower is token
        assert lease.capabilities is capability_snapshot
        assert lease.capabilities == expected
        assert tuple(capability.role for capability in lease.capabilities) == (
            _KRYLOV_PARENT_ROLES
        )
        assert context._krylov_parent_allocation_capabilities(token) is (
            capability_snapshot
        )
        assert context._krylov_parent_allocation_capabilities(token) == expected
        assert _allocation_states(expected) == ("borrowed",) * 5

        with pytest.raises(HipAllocationLineageError) as begin_free:
            owner.begin_free(expected[0])
        assert begin_free.value.code == "hip_allocation_free_busy"
        with pytest.raises(HipAllocationLineageError) as owner_close:
            owner.close()
        assert owner_close.value.code == "hip_allocation_owner_busy"
        with pytest.raises(HipFreeSpaceContextError) as context_close:
            context.close()
        assert context_close.value.code == "hip_free_space_krylov_consumer_active"

        context._release_krylov_consumer(token)
        token = None
        assert context._krylov_consumer_borrow_lease is None
        assert context._krylov_consumer_capability_snapshot is None
        assert _allocation_states(expected) == ("live",) * 5
        assert not _strong_lineage_registry_snapshot()["borrows"]

        context.close()
        assert context.closed
    finally:
        if token is not None and context._krylov_consumer_token is token:
            context._release_krylov_consumer(token)
        _close_chain(opened, resident_open, parent_open)


def test_known_not_freed_retry_reuses_pending_lease_and_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    assert context is not None
    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    failed_role = "reduced_state"
    failed_capability = context._owned_capabilities[failed_role]
    failed_pointer = failed_capability.pointer_snapshot
    runtime.arm_classified_free(failed_pointer, _KnownNotFreed)
    try:
        with pytest.raises(HipFreeSpaceContextError) as failed_close:
            context.close()
        assert failed_close.value.code == "hip_free_space_cleanup_failed"
        assert failed_close.value.cleanup_owner is context
        assert context.receipt().status == "cleanup_failed"
        assert set(context._owned_capabilities) == {failed_role}
        assert set(context._pending_free_leases) == {failed_role}

        pending = context._pending_free_leases[failed_role]
        assert pending.capability is failed_capability
        assert pending.pointer_snapshot == failed_pointer
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        with pytest.raises(AttributeError):
            pending.pointer_snapshot = failed_pointer + 8

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
        assert not context._pending_free_leases
        telemetry = context.receipt().telemetry
        assert telemetry.deallocation_attempt_count == 13
        assert telemetry.deallocation_success_count == 12
        assert telemetry.lineage_free_acknowledgement_count == 12
        assert telemetry.lineage_free_quarantine_count == 0
        assert telemetry.lineage_owner_close_success_count == 1
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_typed_outcome_uncertain_free_is_terminally_quarantined_once(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and resident is not None and parent is not None
    failed_role = "reduced_state"
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
        assert terminal.reason.code == "hip_free_space_cleanup_quarantined"
        assert terminal.telemetry.deallocation_attempt_count == 12
        assert terminal.telemetry.deallocation_success_count == 11
        assert terminal.telemetry.lineage_free_acknowledgement_count == 11
        assert terminal.telemetry.lineage_free_quarantine_count == 1
        assert terminal.telemetry.quarantined_device_bytes == failed_bytes
        assert terminal.telemetry.current_device_bytes == failed_bytes
        assert terminal.telemetry.lineage_owner_close_success_count == 1
        assert terminal.telemetry.lease_release_success_count == 1
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert failed_pointer in runtime.allocations
        assert context._allocation_owner_closed
        assert resident._downstream_consumer_token is None
        assert not context._owned_capabilities
        assert not context._pending_free_leases
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard

        context.close()
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
    finally:
        _close_chain(opened, resident_open, parent_open)

    assert resident.closed and parent.closed
    assert parent._resident_consumer_token is None
    assert set(runtime.allocations) == {failed_pointer}


def test_rehashed_ready_attempt_and_terminal_managed_byte_forgeries_fail_closed() -> (
    None
):
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None and opened.ready
    try:
        forged_ready = _rehash_free_space_context_receipt(
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
        with pytest.raises(HipFreeSpaceContextError):
            free_space_module.validate_hip_free_space_context_receipt(forged_ready)

        context.close()
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.allocation_lineage is not None
        forged_terminal = _rehash_free_space_context_receipt(
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
        with pytest.raises(HipFreeSpaceContextError):
            free_space_module.validate_hip_free_space_context_receipt(forged_terminal)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_rehashed_terminal_quarantine_byte_forgery_fails_closed() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    assert context is not None
    failed_pointer = context._owned_capabilities["reduced_state"].pointer_snapshot
    runtime.arm_classified_free(failed_pointer, _OutcomeUncertain)
    try:
        context.close()
        terminal = context.receipt()
        assert terminal.status == "cleanup_quarantined"
        forged = _rehash_free_space_context_receipt(
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

        with pytest.raises(HipFreeSpaceContextError):
            free_space_module.validate_hip_free_space_context_receipt(forged)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_rehashed_unknown_requested_byte_forgery_fails_closed() -> None:
    runtime = _UncertainMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    runtime.arm_uncertain_malloc(after_successes=0)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        terminal = opened.receipt
        assert opened.context is None
        assert terminal.status == "cleanup_quarantined"
        assert terminal.telemetry.unknown_malloc_outcome_count == 1
        forged = _rehash_free_space_context_receipt(
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

        with pytest.raises(HipFreeSpaceContextError):
            free_space_module.validate_hip_free_space_context_receipt(forged)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_rehashed_ownerless_terminal_work_telemetry_forgeries_fail_closed() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
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
            forged = _rehash_free_space_context_receipt(
                replace(
                    terminal,
                    telemetry=replace(terminal.telemetry, **{field: 1}),
                )
            )
            with pytest.raises(HipFreeSpaceContextError):
                free_space_module.validate_hip_free_space_context_receipt(forged)
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_rehashed_first_malloc_failure_operation_stage_forgeries_fail_closed() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    runtime.malloc_failure_at = runtime.malloc_calls + 1
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
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
            forged = _rehash_free_space_context_receipt(
                replace(
                    terminal,
                    telemetry=replace(telemetry, **{field: 1}),
                )
            )
            with pytest.raises(HipFreeSpaceContextError):
                free_space_module.validate_hip_free_space_context_receipt(forged)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_unknown_generic_injected_free_is_quarantined_without_refree() -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    assert context is not None
    failed_role = "reduced_state"
    failed_pointer = context._owned_capabilities[failed_role].pointer_snapshot
    failed_bytes = next(
        view.byte_length
        for view in opened.receipt.owned_buffers
        if view.name == failed_role
    )
    runtime.arm_classified_free(failed_pointer, _GenericInjectedFreeError)
    try:
        context.close()

        terminal = context.receipt()
        assert context.closed
        assert terminal.status == "cleanup_quarantined"
        assert terminal.telemetry.deallocation_attempt_count == 12
        assert terminal.telemetry.deallocation_success_count == 11
        assert terminal.telemetry.lineage_free_acknowledgement_count == 11
        assert terminal.telemetry.lineage_free_quarantine_count == 1
        assert terminal.telemetry.quarantined_device_bytes == failed_bytes
        assert terminal.telemetry.unknown_malloc_outcome_count == 0
        assert terminal.telemetry.unknown_requested_bytes == 0
        assert terminal.telemetry.current_device_bytes == failed_bytes
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert failed_pointer in runtime.allocations

        context.close()
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
    finally:
        _close_chain(opened, resident_open, parent_open)

    assert set(runtime.allocations) == {failed_pointer}


def test_partial_malloc_failure_cleans_owner_capabilities_and_reports_unavailable(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = TrackingRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    allocations_before = set(runtime.allocations)
    runtime.malloc_failure_at = runtime.malloc_calls + 4
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    expected_minted_bytes = sum(
        int(overlay.array(role).nbytes) for role in _OWNED_ROLES[:3]
    )
    kernel = FakeFreeSpaceKernel(runtime)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.allocation_lineage is not None
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
        assert telemetry.current_device_bytes == 0
        assert telemetry.module_close_attempt_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_attempt_count == 1
        assert telemetry.lease_release_success_count == 1
        assert set(runtime.allocations) == allocations_before
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
        free_space_module.validate_hip_free_space_context_receipt(opened.receipt)
        for field in (
            "deallocation_attempt_count",
            "module_close_attempt_count",
            "lease_release_attempt_count",
        ):
            forged = _rehash_free_space_context_receipt(
                replace(
                    opened.receipt,
                    telemetry=replace(
                        telemetry,
                        **{field: getattr(telemetry, field) + 1},
                    ),
                )
            )
            with pytest.raises(HipFreeSpaceContextError):
                free_space_module.validate_hip_free_space_context_receipt(forged)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_post_malloc_range_overflow_is_quarantined_without_external_free(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _RangeOverflowMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    parent = parent_open.context
    assert resident is not None and parent is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    first_extent = int(overlay.array(_OWNED_ROLES[0]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    free_calls_before = tuple(runtime.free_pointer_calls)
    runtime.arm_range_overflow_malloc()
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        pointer = runtime.overflow_pointer
        assert type(pointer) is int
        assert opened.context is None
        assert opened.receipt.status == "cleanup_quarantined"
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert pointer in runtime.allocations

        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_attempt_count == 1
        assert telemetry.allocation_success_count == 1
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.deallocation_attempt_count == 0
        assert telemetry.deallocation_success_count == 0
        assert telemetry.lineage_orphan_acknowledgement_count == 0
        assert telemetry.lineage_orphan_quarantine_count == 1
        assert telemetry.quarantined_device_bytes == first_extent
        assert telemetry.unknown_malloc_outcome_count == 0
        assert telemetry.unknown_requested_bytes == 0
        assert telemetry.current_device_bytes == first_extent
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_chain(opened, resident_open, parent_open)

    assert parent.closed
    assert set(runtime.allocations) == {pointer}


def test_post_malloc_alignment_orphan_is_freed_and_acknowledged_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _MisalignedMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    allocations_before = set(runtime.allocations)
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    first_extent = int(overlay.array(_OWNED_ROLES[0]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    resolved: list[tuple[HipAllocationOrphanLeaseV1, str]] = []
    original_resolve = HipAllocationOwnerV1.resolve_orphan_free_success

    def capture_orphan_resolution(
        owner: HipAllocationOwnerV1,
        lease: HipAllocationOrphanLeaseV1,
    ) -> str:
        outcome = original_resolve(owner, lease)
        assert type(outcome) is str
        resolved.append((lease, outcome))
        return outcome

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "resolve_orphan_free_success",
        capture_orphan_resolution,
    )
    runtime.arm_misaligned_malloc()
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        pointer = runtime.misaligned_pointer
        assert type(pointer) is int
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert len(resolved) == 1
        orphan_lease, outcome = resolved[0]
        assert outcome == "succeeded"
        assert type(orphan_lease) is HipAllocationOrphanLeaseV1
        assert orphan_lease.role == _OWNED_ROLES[0]
        assert orphan_lease.pointer_snapshot == pointer
        assert _pointer_value(orphan_lease.base) == pointer
        assert orphan_lease.nbytes == first_extent
        assert _orphan_terminal_snapshot(orphan_lease) == "succeeded"
        assert runtime.free_pointer_calls.count(pointer) == 1
        assert pointer not in runtime.allocations

        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_attempt_count == 1
        assert telemetry.allocation_success_count == 1
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.deallocation_attempt_count == 1
        assert telemetry.deallocation_success_count == 1
        assert telemetry.lineage_orphan_acknowledgement_count == 1
        assert telemetry.lineage_orphan_quarantine_count == 0
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.current_device_bytes == 0
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert set(runtime.allocations) == allocations_before
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_post_resolve_interruption_retries_terminal_without_second_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    assert context is not None
    failed_role = "free_dofs"
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
        assert failed_role in context._external_free_succeeded
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert failed_pointer not in runtime.allocations
        assert context._quarantine_pending == set()
        assert context._poisoned_quarantine_pending == set()
        assert context._deallocation_success_sizes == {
            role: next(
                view.byte_length
                for view in opened.receipt.owned_buffers
                if view.name == role
            )
            for role in _OWNED_ROLES
        }
        assert context._free_acknowledged_roles == set(_OWNED_ROLES) - {failed_role}
        assert _free_terminal_snapshot(pending) == ("succeeded", False, False)
        first_telemetry = context.receipt().telemetry
        assert first_telemetry.deallocation_attempt_count == 12
        assert first_telemetry.deallocation_success_count == 12
        assert first_telemetry.lineage_free_acknowledgement_count == 11
        assert first_telemetry.current_device_bytes == 0

        context.close()

        assert context.closed
        assert context.receipt().status == "context_closed"
        assert runtime.free_pointer_calls.count(failed_pointer) == 1
        assert not context._pending_free_leases
        assert not context._external_free_succeeded
        assert context._free_acknowledged_roles == set(_OWNED_ROLES)
        assert resolved.count((failed_role, "succeeded")) == 2
        assert _free_terminal_snapshot(pending) == ("succeeded", False, False)
        telemetry = context.receipt().telemetry
        assert telemetry.deallocation_attempt_count == 12
        assert telemetry.deallocation_success_count == 12
        assert telemetry.lineage_free_acknowledgement_count == 12
        assert telemetry.lineage_free_quarantine_count == 0
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.current_device_bytes == 0
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_malloc_base_exception_quarantines_orphan_and_existing_capabilities(
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _UncertainMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    parent = parent_open.context
    assert resident is not None and parent is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    expected_minted_bytes = sum(
        int(overlay.array(role).nbytes) for role in _OWNED_ROLES[:3]
    )
    uncertain_orphan_bytes = int(overlay.array(_OWNED_ROLES[3]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    free_calls_before = tuple(runtime.free_pointer_calls)
    runtime.arm_uncertain_malloc(after_successes=3)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "cleanup_quarantined"
        assert opened.receipt.reason is not None
        assert opened.receipt.reason.code == "hip_free_space_cleanup_quarantined"
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
        assert telemetry.unknown_requested_bytes == uncertain_orphan_bytes
        assert telemetry.current_device_bytes == expected_minted_bytes
        assert telemetry.lineage_owner_open_success_count == 1
        assert telemetry.lineage_owner_close_success_count == 1
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_chain(opened, resident_open, parent_open)

    assert resident.closed and parent.closed
    assert parent._resident_consumer_token is None
    assert set(runtime.allocations) == set(runtime.post_arm_pointers)


def test_downstream_consumer_handoff_interrupt_recovers_open_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    free_calls_before = tuple(runtime.free_pointer_calls)
    published_tokens: list[object] = []
    interruption = _HandoffInterrupt(
        "injected interruption after downstream consumer publication"
    )
    original_acquire = type(resident)._acquire_downstream_consumer

    def acquire_then_interrupt(
        target: Any,
        token: object | None = None,
    ) -> object:
        published = original_acquire(target, token)
        assert token is not None
        assert published is token
        published_tokens.append(published)
        raise interruption

    monkeypatch.setattr(
        type(resident),
        "_acquire_downstream_consumer",
        acquire_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert len(published_tokens) == 1
        assert resident._downstream_consumer_token is None
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_allocation_owner_factory_handoff_interrupt_recovers_owner(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    free_calls_before = tuple(runtime.free_pointer_calls)
    captured: list[tuple[HipAllocationOwnerV1, list[HipAllocationOwnerV1 | None]]] = []
    interruption = _HandoffInterrupt(
        "injected interruption after allocation owner handoff"
    )
    original_open_owner = free_space_module._open_integrated_hip_allocation_owner_v1

    def open_owner_then_interrupt(
        runtime_arg: object,
        device_ordinal: int,
        owner_role: str,
        *,
        _handoff: list[HipAllocationOwnerV1 | None] | None = None,
    ) -> HipAllocationOwnerV1:
        owner = original_open_owner(
            runtime_arg,
            device_ordinal,
            owner_role,
            _handoff=_handoff,
        )
        assert _handoff is not None
        assert _handoff == [owner]
        captured.append((owner, _handoff))
        raise interruption

    monkeypatch.setattr(
        free_space_module,
        "_open_integrated_hip_allocation_owner_v1",
        open_owner_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert len(captured) == 1
        owner, handoff = captured[0]
        assert handoff == [owner]
        assert owner.closed
        assert resident._downstream_consumer_token is None
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_allocate_handoff_interrupt_recovers_missing_capability_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    captured: list[tuple[HipAllocationOwnerV1, Any]] = []
    interruption = _HandoffInterrupt(
        "injected interruption after allocation capability publication"
    )
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
            open_hip_free_space_execution_context(
                resident,
                overlay,
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
        assert resident._downstream_consumer_token is None
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_cleanup_context_initializer_failure_uses_original_fallback(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    sync_interrupted = False
    cleanup_initializer_failures = 0
    interruption = _HandoffInterrupt(
        "injected interruption after opening synchronization"
    )
    cleanup_constructor_error = MemoryError(
        "injected cleanup context initializer failure"
    )
    original_synchronize = type(runtime).synchronize
    original_initializer = HipFreeSpaceExecutionContext.__init__

    def synchronize_then_interrupt(target: Any, stream: Any) -> None:
        nonlocal sync_interrupted
        original_synchronize(target, stream)
        if not sync_interrupted:
            sync_interrupted = True
            raise interruption

    def fail_public_initializer_once(
        context: HipFreeSpaceExecutionContext,
        **arguments: Any,
    ) -> None:
        nonlocal cleanup_initializer_failures
        opening_status = arguments["opening_status"]
        if opening_status == "cleanup_failed" and cleanup_initializer_failures == 0:
            cleanup_initializer_failures += 1
            raise cleanup_constructor_error
        original_initializer(context, **arguments)

    monkeypatch.setattr(
        type(runtime),
        "synchronize",
        synchronize_then_interrupt,
    )
    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "__init__",
        fail_public_initializer_once,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert sync_interrupted
        assert cleanup_initializer_failures == 1
        assert resident._downstream_consumer_token is None
        assert kernel.closed
        assert set(runtime.allocations) == allocations_before
        assert len(runtime.free_pointer_calls) == len(_OWNED_ROLES)
        assert len(set(runtime.free_pointer_calls)) == len(_OWNED_ROLES)
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_resident_chain(resident_open, parent_open)


@pytest.mark.parametrize("terminal_outcome", ["succeeded", "quarantined"])
def test_terminal_free_interrupt_during_local_retirement_does_not_refree(
    monkeypatch: pytest.MonkeyPatch,
    terminal_outcome: str,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        _,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    assert context is not None
    target_role = "error_flag"
    target_capability = context._owned_capabilities[target_role]
    target_pointer = target_capability.pointer_snapshot
    if terminal_outcome == "quarantined":
        runtime.arm_classified_free(target_pointer, _OutcomeUncertain)
    interruption = _HandoffInterrupt(
        f"injected interruption during {terminal_outcome} local retirement"
    )
    injected = False
    original_refresh = HipFreeSpaceExecutionContext._refresh_retirement_telemetry

    def refresh_then_interrupt(target: HipFreeSpaceExecutionContext) -> None:
        nonlocal injected
        original_refresh(target)
        terminal_published = (
            target_role in target._free_acknowledged_roles
            if terminal_outcome == "succeeded"
            else target_role in target._free_quarantined_sizes
        )
        if (
            not injected
            and terminal_published
            and target_role in target._owned_capabilities
        ):
            injected = True
            raise interruption

    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_refresh_retirement_telemetry",
        refresh_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            context.close()

        assert caught.value is interruption
        assert injected
        assert target_role in context._owned_capabilities
        assert target_role in context._pointers
        lease = context._pending_free_leases[target_role]
        assert _free_terminal_snapshot(lease) == (
            terminal_outcome,
            False,
            False,
        )
        assert runtime.free_pointer_calls.count(target_pointer) == 1
        assert context.receipt().status == "cleanup_failed"

        context.close()

        assert context.closed
        assert target_role not in context._owned_capabilities
        assert target_role not in context._pointers
        assert target_role not in context._pending_free_leases
        assert runtime.free_pointer_calls.count(target_pointer) == 1
        assert _free_terminal_snapshot(lease) == (
            terminal_outcome,
            False,
            False,
        )
        terminal = context.receipt()
        assert terminal.status == (
            "context_closed"
            if terminal_outcome == "succeeded"
            else "cleanup_quarantined"
        )

        context.close()
        assert runtime.free_pointer_calls.count(target_pointer) == 1
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_owner_close_handoff_interrupt_resumes_kernel_lease_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        kernel,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    resident = resident_open.context
    assert context is not None and resident is not None
    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    owned_pointers = tuple(
        capability.pointer_snapshot
        for capability in context._owned_capabilities.values()
    )
    interruption = _HandoffInterrupt(
        "injected interruption after allocation owner close"
    )
    injected = False
    original_owner_close = HipAllocationOwnerV1.close

    def close_owner_then_interrupt(target: HipAllocationOwnerV1) -> None:
        nonlocal injected
        original_owner_close(target)
        if target is owner and not injected:
            injected = True
            raise interruption

    monkeypatch.setattr(
        HipAllocationOwnerV1,
        "close",
        close_owner_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            context.close()

        assert caught.value is interruption
        assert injected
        assert owner.closed
        assert not context._allocation_owner_closed
        assert not context.closed
        assert not kernel.closed
        assert resident._downstream_consumer_token is not None
        assert all(
            runtime.free_pointer_calls.count(pointer) == 1 for pointer in owned_pointers
        )

        context.close()

        assert context.closed
        assert context._allocation_owner_closed
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert all(
            runtime.free_pointer_calls.count(pointer) == 1 for pointer in owned_pointers
        )
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.telemetry.lineage_owner_close_success_count == 1
        assert terminal.telemetry.module_close_success_count == 1
        assert terminal.telemetry.lease_release_success_count == 1
        free_space_module.validate_hip_free_space_context_receipt(
            terminal,
            expected_context=context,
        )
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_krylov_group_prepare_publication_interrupt_rolls_back_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    capabilities = tuple(
        context._owned_capabilities[role] for role in _KRYLOV_PARENT_ROLES
    )
    lineage_before = _strong_lineage_registry_snapshot()
    token = object()
    interruption = _HandoffInterrupt(
        "injected interruption after Krylov semantic token publication"
    )
    injected = False
    original_prepare = HipFreeSpaceExecutionContext._prepare_krylov_consumer_locked

    def prepare_then_interrupt(
        target: HipFreeSpaceExecutionContext,
        issued_token: object,
    ) -> tuple[Any, ...]:
        nonlocal injected
        prepared = original_prepare(target, issued_token)
        if not injected:
            injected = True
            assert target._krylov_consumer_token is issued_token
            assert target._krylov_consumer_phase == "semantic_reserved"
            raise interruption
        return prepared

    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "_prepare_krylov_consumer_locked",
        prepare_then_interrupt,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            context._acquire_krylov_consumer(token)

        assert caught.value is interruption
        assert injected
        assert context._krylov_consumer_token is None
        assert context._krylov_consumer_borrow_lease is None
        assert context._krylov_consumer_capability_snapshot is None
        assert not context._krylov_consumer_rollback_pending
        assert context._krylov_consumer_phase == "idle"
        assert _allocation_states(capabilities) == ("live",) * 5
        assert _strong_lineage_registry_snapshot() == lineage_before

        retry_token = context._acquire_krylov_consumer()
        context._release_krylov_consumer(retry_token)
        assert _allocation_states(capabilities) == ("live",) * 5
        assert _strong_lineage_registry_snapshot() == lineage_before
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_pending_unverified_orphan_terminal_store_interrupt_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _UncertainMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    first_extent = int(overlay.array(_OWNED_ROLES[0]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    free_calls_before = tuple(runtime.free_pointer_calls)
    interruption = _HandoffInterrupt(
        "injected interruption after orphan terminal marker publication"
    )
    backing = lineage._CONSUMED_ORPHANS

    class InterruptingTerminalStore:
        def __init__(self) -> None:
            self.injected = False

        def get(self, key: object, default: Any = None) -> Any:
            return backing.get(key, default)

        def __setitem__(self, key: object, value: Any) -> None:
            backing[key] = value
            if not self.injected:
                self.injected = True
                raise interruption

        def __getattr__(self, name: str) -> Any:
            return getattr(backing, name)

    terminal_store = InterruptingTerminalStore()
    monkeypatch.setattr(lineage, "_CONSUMED_ORPHANS", terminal_store)
    runtime.arm_uncertain_malloc(after_successes=0)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert context is not None
    owner = context._allocation_owner
    assert type(owner) is HipAllocationOwnerV1
    assert len(context._orphan_cleanups) == 1
    cleanup = context._orphan_cleanups[0]
    lease = cleanup.lease
    try:
        assert terminal_store.injected
        assert opened.receipt.status == "cleanup_failed"
        assert context._initial_managed_device_bytes == 0
        assert _orphan_terminal_snapshot(lease) == "quarantined"
        with lineage._LOCK:
            assert lineage._ORPHANS[id(lease)].state == "pending_unverified"

        with pytest.raises(HipAllocationLineageError) as mismatch:
            owner.resolve_orphan_free_success(lease)
        assert mismatch.value.code == "hip_allocation_orphan_outcome_mismatch"
        with lineage._LOCK:
            assert id(lease) not in lineage._ORPHANS
        assert owner.resolve_orphan_free_quarantine(lease) == "quarantined"
        assert owner.resolve_orphan_free_quarantine(lease) == "quarantined"

        context.close()

        assert context.closed
        terminal = context.receipt()
        assert terminal.status == "cleanup_quarantined"
        assert terminal.telemetry.unknown_malloc_outcome_count == 1
        assert terminal.telemetry.unknown_requested_bytes == first_extent
        assert terminal.telemetry.quarantined_device_bytes == 0
        assert terminal.telemetry.current_device_bytes == 0
        assert None not in runtime.free_pointer_calls
        assert tuple(runtime.free_pointer_calls) == free_calls_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_lease_release_flag_interrupt_recovers_success_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    (
        *_,
        parent_open,
        resident_open,
        _,
        kernel,
        opened,
    ) = _open_free_space_on(runtime)
    context = opened.context
    resident = resident_open.context
    assert context is not None and resident is not None
    owned_pointers = tuple(
        capability.pointer_snapshot
        for capability in context._owned_capabilities.values()
    )
    interruption = _HandoffInterrupt(
        "injected interruption before lease success telemetry publication"
    )
    injected = False
    original_replace = free_space_module.replace

    def replace_then_interrupt(value: Any, /, **changes: Any) -> Any:
        nonlocal injected
        result = original_replace(value, **changes)
        if (
            not injected
            and context._lease_released
            and changes.get("lease_release_success_count") == 1
        ):
            injected = True
            raise interruption
        return result

    monkeypatch.setattr(free_space_module, "replace", replace_then_interrupt)
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            context.close()

        assert caught.value is interruption
        assert injected
        assert context._lease_released
        assert not context.closed
        assert resident._downstream_consumer_token is None
        assert kernel.closed
        assert context._telemetry.lease_release_success_count == 0

        context.close()

        assert context.closed
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.telemetry.lease_release_attempt_count == 1
        assert terminal.telemetry.lease_release_success_count == 1
        assert terminal.telemetry.lineage_owner_close_success_count == 1
        assert terminal.telemetry.module_close_success_count == 1
        assert all(
            runtime.free_pointer_calls.count(pointer) == 1 for pointer in owned_pointers
        )
        free_space_module.validate_hip_free_space_context_receipt(
            terminal,
            expected_context=context,
        )
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_owner_assignment_interrupt_repairs_open_close_receipt(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    interruption = _HandoffInterrupt(
        "injected interruption before owner-open telemetry assignment"
    )
    injected = False
    cleanup_results: list[Any] = []
    captured_owners: list[HipAllocationOwnerV1] = []
    original_replace = free_space_module.replace
    original_cleanup = free_space_module._cleanup_failed_open

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

    monkeypatch.setattr(free_space_module, "replace", replace_then_interrupt)
    monkeypatch.setattr(
        free_space_module,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
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
        assert resident._downstream_consumer_token is None
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
        free_space_module.validate_hip_free_space_context_receipt(result.receipt)
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_capability_publication_interrupt_recovers_full_byte_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _NativeShapedClassifiedFreeRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    first_extent = int(overlay.array(_OWNED_ROLES[0]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    interruption = _HandoffInterrupt(
        "injected interruption before capability byte telemetry assignment"
    )
    injected = False
    cleanup_results: list[Any] = []
    preclose_snapshots: list[tuple[int, int, int, int]] = []
    original_replace = free_space_module.replace
    original_cleanup = free_space_module._cleanup_failed_open
    original_close = HipFreeSpaceExecutionContext.close

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

    def capture_preclose(target: HipFreeSpaceExecutionContext) -> None:
        if target._opening_status == "cleanup_failed" and not preclose_snapshots:
            preclose_snapshots.append(
                (
                    target._initial_managed_device_bytes,
                    target._telemetry.current_device_bytes,
                    target._telemetry.peak_device_bytes,
                    target._telemetry.lineage_capability_mint_bytes,
                )
            )
        original_close(target)

    monkeypatch.setattr(free_space_module, "replace", replace_then_interrupt)
    monkeypatch.setattr(
        free_space_module,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "close",
        capture_preclose,
    )
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert injected
        assert preclose_snapshots == [
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
        assert resident._downstream_consumer_token is None
        assert set(runtime.allocations) == allocations_before
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
        free_space_module.validate_hip_free_space_context_receipt(result.receipt)
    finally:
        _close_resident_chain(resident_open, parent_open)


def test_pointer_known_orphan_publication_interrupt_recovers_byte_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    _lineage_registry_guard: dict[str, tuple[tuple[Any, ...], ...]],
) -> None:
    runtime = _MisalignedMallocRuntime()
    *_, actual_runtime, _, _, parent_open, resident_open = _open_resident(
        runtime=runtime
    )
    assert actual_runtime is runtime
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    first_extent = int(overlay.array(_OWNED_ROLES[0]).nbytes)
    kernel = FakeFreeSpaceKernel(runtime)
    allocations_before = set(runtime.allocations)
    interruption = _HandoffInterrupt(
        "injected interruption before pointer-known orphan byte telemetry assignment"
    )
    injected = False
    cleanup_results: list[Any] = []
    preclose_snapshots: list[tuple[int, int, int]] = []
    original_replace = free_space_module.replace
    original_cleanup = free_space_module._cleanup_failed_open
    original_close = HipFreeSpaceExecutionContext.close

    def replace_then_interrupt(value: Any, /, **changes: Any) -> Any:
        nonlocal injected
        result = original_replace(value, **changes)
        if (
            not injected
            and "allocation_success_count" in changes
            and "lineage_capability_mint_success_count" not in changes
        ):
            injected = True
            raise interruption
        return result

    def capture_cleanup_result(**arguments: Any) -> Any:
        result = original_cleanup(**arguments)
        cleanup_results.append(result)
        return result

    def capture_preclose(target: HipFreeSpaceExecutionContext) -> None:
        if target._opening_status == "cleanup_failed" and not preclose_snapshots:
            preclose_snapshots.append(
                (
                    target._initial_managed_device_bytes,
                    target._telemetry.current_device_bytes,
                    target._telemetry.peak_device_bytes,
                )
            )
        original_close(target)

    monkeypatch.setattr(free_space_module, "replace", replace_then_interrupt)
    monkeypatch.setattr(
        free_space_module,
        "_cleanup_failed_open",
        capture_cleanup_result,
    )
    monkeypatch.setattr(
        HipFreeSpaceExecutionContext,
        "close",
        capture_preclose,
    )
    runtime.arm_misaligned_malloc()
    try:
        with pytest.raises(_HandoffInterrupt) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )

        assert caught.value is interruption
        assert injected
        pointer = runtime.misaligned_pointer
        assert type(pointer) is int
        assert preclose_snapshots == [(first_extent, first_extent, first_extent)]
        assert len(cleanup_results) == 1
        result = cleanup_results[0]
        assert result.context is None
        assert result.receipt.status == "unavailable"
        telemetry = result.receipt.telemetry
        assert telemetry.allocation_attempt_count == 1
        assert telemetry.allocation_success_count == 1
        assert telemetry.lineage_capability_mint_success_count == 0
        assert telemetry.lineage_capability_mint_bytes == 0
        assert telemetry.deallocation_attempt_count == 1
        assert telemetry.deallocation_success_count == 1
        assert telemetry.lineage_orphan_acknowledgement_count == 1
        assert telemetry.lineage_orphan_quarantine_count == 0
        assert telemetry.peak_device_bytes == first_extent
        assert telemetry.current_device_bytes == 0
        assert runtime.free_pointer_calls.count(pointer) == 1
        assert pointer not in runtime.allocations
        assert set(runtime.allocations) == allocations_before
        assert kernel.closed
        assert resident._downstream_consumer_token is None
        assert _strong_lineage_registry_snapshot() == _lineage_registry_guard
        free_space_module.validate_hip_free_space_context_receipt(result.receipt)
    finally:
        _close_resident_chain(resident_open, parent_open)
