from __future__ import annotations

import threading

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    free_space as free_space_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    hip_allocation_lineage as lineage,
)
from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    HipResidentCsrContextError,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (
    HipAllocationBorrowLeaseV1,
)

from tests.test_engine_v2_hip_free_space_context_v1 import (
    _close_chain,
    _open_free_space,
)


def _release_live_krylov_child(context: object) -> None:
    token = context._krylov_consumer_token
    if token is not None:
        context._release_krylov_consumer(token)


class _BorrowCommitInterrupt(BaseException):
    pass


class _ReleaseTerminalInterrupt(BaseException):
    pass


def _borrow_registry_snapshot() -> tuple[tuple[object, ...], ...]:
    with lineage._LOCK:
        return tuple(
            sorted(
                (key, row.allocation_ids, row.released)
                for key, row in lineage._BORROWS.items()
            )
        )


def _allocation_states(capabilities: tuple[object, ...]) -> tuple[str, ...]:
    with lineage._LOCK:
        return tuple(
            lineage._ALLOCATIONS[id(capability)].state for capability in capabilities
        )


def _assert_krylov_consumer_idle(context: object) -> None:
    assert context._krylov_consumer_token is None
    assert context._krylov_consumer_borrow_lease is None
    assert context._krylov_consumer_capability_snapshot is None
    assert context._krylov_consumer_rollback_pending is False
    assert context._krylov_consumer_phase == "idle"


def test_krylov_lease_is_exact_exclusive_and_monotonic() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        first = context._acquire_krylov_consumer()
        assert context._krylov_consumer_epoch(first) == 1
        context._require_krylov_consumer(first)

        with pytest.raises(HipFreeSpaceContextError) as duplicate:
            context._acquire_krylov_consumer()
        assert duplicate.value.code == "hip_free_space_krylov_consumer_active"

        foreign = object()
        for operation in (
            lambda: context._require_krylov_consumer(foreign),
            lambda: context._krylov_consumer_epoch(foreign),
            lambda: context._release_krylov_consumer(foreign),
        ):
            with pytest.raises(HipFreeSpaceContextError) as rejected:
                operation()
            assert rejected.value.code == (
                "hip_free_space_krylov_consumer_token_invalid"
            )
            assert context._krylov_consumer_token is first

        context._release_krylov_consumer(first)
        second = context._acquire_krylov_consumer()
        assert second is not first
        assert context._krylov_consumer_epoch(second) == 2
        context._require_krylov_consumer(second)

        for operation in (
            lambda: context._require_krylov_consumer(first),
            lambda: context._krylov_consumer_epoch(first),
            lambda: context._release_krylov_consumer(first),
        ):
            with pytest.raises(HipFreeSpaceContextError) as stale:
                operation()
            assert stale.value.code == ("hip_free_space_krylov_consumer_token_invalid")
            assert context._krylov_consumer_token is second

        context._release_krylov_consumer(second)
        assert context._krylov_consumer_token is None
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)


def test_active_krylov_child_atomically_blocks_owner_and_ancestor_work() -> None:
    *_, runtime, parent_open, resident_open, _, kernel, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and resident is not None and parent is not None
    token = context._acquire_krylov_consumer()
    free_space_telemetry = context.receipt().telemetry
    resident_telemetry = resident.receipt().telemetry
    assembly_telemetry = parent.receipt().telemetry
    work_before = (
        runtime.sync_calls,
        runtime.free_calls,
        tuple(runtime.allocations),
        len(kernel.direction_calls),
        len(kernel.gather_calls),
        len(resident._rtc_kernel.launches),
    )
    try:
        for operation in (
            context.enqueue_operator_apply,
            context.evaluate_for_verification,
            context.close,
        ):
            with pytest.raises(HipFreeSpaceContextError) as blocked:
                operation()
            assert blocked.value.code == "hip_free_space_krylov_consumer_active"

        with pytest.raises(HipResidentCsrContextError) as resident_close:
            resident.close()
        assert resident_close.value.code == ("hip_resident_downstream_consumer_active")

        with pytest.raises(HipAssemblyContextError) as assembly_close:
            parent.close()
        assert assembly_close.value.code == "hip_assembly_resident_consumer_active"

        assert context.receipt().telemetry == free_space_telemetry
        assert resident.receipt().telemetry == resident_telemetry
        assert parent.receipt().telemetry == assembly_telemetry
        assert work_before == (
            runtime.sync_calls,
            runtime.free_calls,
            tuple(runtime.allocations),
            len(kernel.direction_calls),
            len(kernel.gather_calls),
            len(resident._rtc_kernel.launches),
        )

        context._release_krylov_consumer(token)
        apply = context.enqueue_operator_apply()
        assert apply.status == "enqueued"
        assert len(kernel.direction_calls) == 1
        assert len(kernel.gather_calls) == 1
        assert len(resident._rtc_kernel.launches) == 1

        context.close()
        resident.close()
        parent.close()
        assert context.closed and resident.closed and parent.closed
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)


def test_krylov_child_poison_is_shared_and_exact_release_remains_available() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and resident is not None and parent is not None
    token = context._acquire_krylov_consumer()
    try:
        context._poison_krylov_consumer(
            token, "injected Krylov primitive launch failure"
        )
        assert context.poisoned and resident.poisoned and parent.poisoned
        assert context.receipt().status == "poisoned"
        assert resident.receipt().status == "poisoned"
        assert parent.receipt().status == "poisoned"

        with pytest.raises(HipFreeSpaceContextError) as foreign_release:
            context._release_krylov_consumer(object())
        assert foreign_release.value.code == (
            "hip_free_space_krylov_consumer_token_invalid"
        )
        assert context._krylov_consumer_token is token

        context._release_krylov_consumer(token)
        assert context._krylov_consumer_token is None
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)


def test_two_thread_krylov_acquire_has_exactly_one_winner() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    barrier = threading.Barrier(3)
    successes: list[object] = []
    failures: list[HipFreeSpaceContextError] = []

    def acquire() -> None:
        barrier.wait(timeout=5)
        try:
            successes.append(context._acquire_krylov_consumer())
        except HipFreeSpaceContextError as exc:
            failures.append(exc)

    threads = tuple(threading.Thread(target=acquire, daemon=True) for _ in range(2))
    try:
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)

        assert all(not thread.is_alive() for thread in threads)
        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].code == "hip_free_space_krylov_consumer_active"
        winner = successes[0]
        assert context._krylov_consumer_token is winner
        assert context._krylov_consumer_epoch(winner) == 1
        context._release_krylov_consumer(winner)
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)


def test_post_borrow_interruption_recovers_exact_group_before_next_acquire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    capabilities = tuple(
        context._owned_capabilities[name]
        for name in (
            "reduced_csr_row_ptr",
            "reduced_csr_column_indices",
            "reduced_csr_values",
            "reduced_direction",
            "reduced_jvp",
        )
    )
    borrows_before = _borrow_registry_snapshot()
    original_borrow = free_space_module.borrow_hip_allocations_v1
    original_release = free_space_module.release_hip_allocation_borrow_v1
    borrowed: list[HipAllocationBorrowLeaseV1] = []
    borrow_groups: list[tuple[object, ...]] = []
    released: list[HipAllocationBorrowLeaseV1] = []
    interrupted = False

    def borrow_then_interrupt_once(
        group: tuple[object, ...],
        borrower: object,
    ) -> HipAllocationBorrowLeaseV1:
        nonlocal interrupted
        lease = original_borrow(group, borrower)
        borrowed.append(lease)
        borrow_groups.append(group)
        if not interrupted:
            interrupted = True
            raise _BorrowCommitInterrupt(
                "injected interruption after group-borrow commit"
            )
        return lease

    def record_release(lease: HipAllocationBorrowLeaseV1) -> None:
        original_release(lease)
        released.append(lease)

    monkeypatch.setattr(
        free_space_module,
        "borrow_hip_allocations_v1",
        borrow_then_interrupt_once,
    )
    monkeypatch.setattr(
        free_space_module,
        "release_hip_allocation_borrow_v1",
        record_release,
    )
    try:
        with pytest.raises(_BorrowCommitInterrupt):
            context._acquire_krylov_consumer()

        assert len(borrowed) == 1
        stranded = borrowed[0]
        assert stranded.capabilities is borrow_groups[0]
        assert stranded.capabilities == capabilities
        assert released == [stranded]
        assert _borrow_registry_snapshot() == borrows_before
        assert _allocation_states(capabilities) == ("live",) * 5
        _assert_krylov_consumer_idle(context)

        token = context._acquire_krylov_consumer()
        active = context._krylov_consumer_borrow_lease
        assert active is not None and active is borrowed[1]
        assert active is not stranded
        assert active.capabilities is context._krylov_consumer_capability_snapshot
        assert active.capabilities == capabilities
        assert _allocation_states(capabilities) == ("borrowed",) * 5

        context._release_krylov_consumer(token)
        assert released == [stranded, active]
        assert _borrow_registry_snapshot() == borrows_before
        assert _allocation_states(capabilities) == ("live",) * 5
        _assert_krylov_consumer_idle(context)

        context.close()
        assert context.closed
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)


@pytest.mark.parametrize("recovery", ("next_acquire", "close"))
def test_post_release_interruption_resumes_idempotent_terminal_group(
    monkeypatch: pytest.MonkeyPatch,
    recovery: str,
) -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    borrows_before = _borrow_registry_snapshot()
    token = context._acquire_krylov_consumer()
    lease = context._krylov_consumer_borrow_lease
    capabilities = context._krylov_consumer_capability_snapshot
    assert lease is not None and capabilities is not None
    original_release = free_space_module.release_hip_allocation_borrow_v1
    release_calls: list[HipAllocationBorrowLeaseV1] = []
    interrupted = False

    def release_then_interrupt_once(
        candidate: HipAllocationBorrowLeaseV1,
    ) -> None:
        nonlocal interrupted
        original_release(candidate)
        release_calls.append(candidate)
        if candidate is lease and not interrupted:
            interrupted = True
            raise _ReleaseTerminalInterrupt(
                "injected interruption after group-release terminal record"
            )

    monkeypatch.setattr(
        free_space_module,
        "release_hip_allocation_borrow_v1",
        release_then_interrupt_once,
    )
    try:
        with pytest.raises(_ReleaseTerminalInterrupt):
            context._release_krylov_consumer(token)

        assert context._krylov_consumer_token is token
        assert context._krylov_consumer_borrow_lease is lease
        assert context._krylov_consumer_capability_snapshot is capabilities
        assert context._krylov_consumer_phase == "release_pending"
        assert context._krylov_consumer_rollback_pending is False
        assert _borrow_registry_snapshot() == borrows_before
        assert _allocation_states(capabilities) == ("live",) * 5
        assert release_calls == [lease]

        if recovery == "next_acquire":
            next_token = context._acquire_krylov_consumer()
            next_lease = context._krylov_consumer_borrow_lease
            assert next_lease is not None and next_lease is not lease
            assert next_lease.capabilities is (
                context._krylov_consumer_capability_snapshot
            )
            assert next_lease.capabilities == capabilities
            context._release_krylov_consumer(next_token)
            assert release_calls == [lease, lease, next_lease]
            assert _borrow_registry_snapshot() == borrows_before
            assert _allocation_states(capabilities) == ("live",) * 5
            _assert_krylov_consumer_idle(context)
            context.close()
        else:
            context.close()
            assert release_calls == [lease, lease]

        assert context.closed
        assert _borrow_registry_snapshot() == borrows_before
        _assert_krylov_consumer_idle(context)
    finally:
        _release_live_krylov_child(context)
        _close_chain(opened, resident_open, parent_open)
