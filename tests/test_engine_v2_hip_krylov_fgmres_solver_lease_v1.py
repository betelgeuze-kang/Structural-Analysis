from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import threading
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    krylov_primitives as primitives,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (  # noqa: E402
    HipAllocationBorrowLeaseV1,
    HipAllocationLineageError,
    borrow_hip_allocations_v1,
    open_hip_allocation_peer_owner_v1,
    release_hip_allocation_borrow_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_owner_control_v1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (  # noqa: E402
    HipKrylovPrimitivesContextError,
)

from tests.test_engine_v2_hip_krylov_primitives_context_v1 import (  # noqa: E402
    _close_all,
    _open_primitives,
)

_LIVE_TAIL_ROLES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_LIVE_TEST_OWNERS: dict[int, tuple[Any, Any, tuple[Any, ...]]] = {}


class _SingleFireLineInterrupt:
    def __init__(
        self,
        target: Callable[..., object],
        predicate: Callable[[Any], bool],
    ) -> None:
        self._code = target.__code__
        self._predicate = predicate
        self._previous: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if (
            not self.fired
            and event == "line"
            and frame.f_code is self._code
            and self._predicate(frame)
        ):
            self.fired = True
            sys.settrace(self._previous)
            raise KeyboardInterrupt("injected FGMRES lease handoff interruption")
        return self._trace

    def __enter__(self) -> _SingleFireLineInterrupt:
        self._previous = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous)


def _allocate_live_owned_group(
    context: Any,
    parent: tuple[Any, ...],
    owner: Any,
) -> tuple[Any, ...]:
    token = context._fgmres_solver_child_token
    assert token is not None
    owned = tuple(
        owner.allocate(role, 8, "u8", _control_token=token) for role in _LIVE_TAIL_ROLES
    )
    group = parent + owned
    _LIVE_TEST_OWNERS[id(context)] = (context, owner, group)
    return group


def _open_live_owned_owner(context: Any) -> Any:
    owner = open_hip_allocation_peer_owner_v1(
        context._allocation_owner,
        "fgmres_checkpoint_owned_buffers",
    )
    _LIVE_TEST_OWNERS[id(context)] = (context, owner, ())
    return owner


def _reserve_live_group(
    context: Any,
    source_apply: Any,
) -> tuple[object, tuple[Any, ...], tuple[Any, ...]]:
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    group = _allocate_live_owned_group(context, parent, owner)
    prepared = context._prepare_fgmres_solver_child_allocation_borrow(
        token,
        source_apply,
        group,
    )
    assert prepared is group
    capabilities, pending_frees, pending_orphans = owner.cleanup_snapshot()
    assert capabilities == group[3:]
    assert pending_frees == ()
    assert pending_orphans == ()
    assert owner.generation == group[-1].generation
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="fgmres_checkpoint_owned_buffers",
        allowed_roles=_LIVE_TAIL_ROLES,
        expected_allocation_publication_count=8,
    )
    return token, parent, group


def _free_live_owned_capabilities(
    context: Any,
    owner: Any,
    group: tuple[Any, ...],
) -> None:
    token = context._fgmres_solver_child_token
    assert token is not None
    for capability in reversed(group[3:]):
        lease = owner.begin_free(capability, _control_token=token)
        context._runtime.free(lease.pointer_snapshot)
        owner.resolve_free_success(lease, _control_token=token)


def _retire_live_owned_group(context: Any, owner: Any, group: tuple[Any, ...]) -> None:
    token = context._fgmres_solver_child_token
    if group:
        assert token is not None
        _free_live_owned_capabilities(context, owner, group)
    owner.close(_control_token=token)


def _commit_live_group(
    context: Any,
    source_apply: Any,
    token: object,
    group: tuple[Any, ...],
) -> HipAllocationBorrowLeaseV1:
    lease = borrow_hip_allocations_v1(group, token)
    committed = context._commit_fgmres_solver_child_allocation_borrow(
        token,
        source_apply,
        group,
        lease,
    )
    assert committed is token
    return lease


def _release_live_solver_child(context: object) -> None:
    token = context._fgmres_solver_child_token
    source_apply = context._source_apply_snapshot
    if token is not None and context._fgmres_solver_child_phase in {
        "active",
        "allocation_release_pending",
    }:
        context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
    elif token is not None and context._fgmres_solver_child_phase in {
        "semantic_reserved",
        "release_pending",
        "rollback_pending",
    }:
        context._recover_fgmres_solver_child_allocation_borrow(token)
    owned = _LIVE_TEST_OWNERS.pop(id(context), None)
    if owned is not None:
        expected_context, owner, group = owned
        assert expected_context is context
        if not owner.closed:
            _retire_live_owned_group(context, owner, group)
    token = context._fgmres_solver_child_token
    if token is not None:
        context._release_fgmres_solver_child(token, source_apply)


def test_fgmres_solver_child_lease_is_exact_exclusive_and_monotonic() -> None:
    *_, runtime, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    try:
        first = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
        first_snapshot = context._fgmres_solver_child_snapshot(first, source_apply)
        context._require_fgmres_solver_child(first, source_apply)

        assert first_snapshot.primitive_context is context
        assert first_snapshot.primitive_context_id == context.context_id
        assert first_snapshot.primitive_opening_receipt is context.opening_receipt
        assert first_snapshot.source_apply is source_apply
        assert first_snapshot.source_execution_plan is free._plan
        assert first_snapshot.source_free_space_plan is free._overlay
        assert first_snapshot.source_free_space_plan_hash == free._overlay.plan_hash
        assert (
            first_snapshot.source_free_space_view_hash
            == free._overlay.free_space_view_hash
        )
        assert (
            first_snapshot.source_state_displacement
            is free._resident._state.displacement_si
        )
        assert first_snapshot.source_state_displacement_hash == (
            free._resident.opening_receipt.bindings.state_displacement_hash
        )
        assert first_snapshot.runtime is runtime
        assert first_snapshot.loaded_runtime is getattr(runtime, "_loaded", runtime)
        assert first_snapshot.stream is context._stream
        assert first_snapshot.architecture == context._kernel_binding.architecture
        assert first_snapshot.solver_child_lease_epoch == 1
        assert first_snapshot.primitive_parent_lease_epoch == context._lease_epoch
        assert first_snapshot.source_apply_receipt_hash == source_apply.receipt_hash
        assert first_snapshot.free_dof_count == free._overlay.free_dof_count
        assert first_snapshot.reduced_csr_nnz == free._overlay.reduced_csr_nnz

        pointer_names = tuple(name for name, _ in first_snapshot.device_pointers)
        assert pointer_names == (
            "reduced_csr_row_ptr",
            "reduced_csr_column_indices",
            "reduced_csr_values",
            "reduced_state",
            "reduced_load",
            "reduced_direction",
            "jacobi_inverse",
        )
        for name in pointer_names[:-1]:
            assert first_snapshot.pointer(name) is free._pointers[name]
        assert (
            first_snapshot.pointer("jacobi_inverse")
            is context._pointers["jacobi_inverse"]
        )
        assert "work_x" not in pointer_names
        with pytest.raises(KeyError):
            first_snapshot.pointer("work_x")

        with pytest.raises(HipKrylovPrimitivesContextError) as duplicate:
            context._acquire_fgmres_solver_child_for_source_apply(source_apply)
        assert duplicate.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_active"
        )

        forged_source = replace(source_apply)
        for operation in (
            lambda: context._require_fgmres_solver_child(first, forged_source),
            lambda: context._fgmres_solver_child_snapshot(first, forged_source),
            lambda: context._poison_fgmres_solver_child(
                first, forged_source, "must not poison"
            ),
            lambda: context._release_fgmres_solver_child(first, forged_source),
        ):
            with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
                operation()
            assert rejected.value.code == (
                "hip_krylov_primitives_fgmres_source_apply_invalid"
            )
            assert context._fgmres_solver_child_token is first
        assert not context.poisoned

        for field, replacement_value in (
            ("sequence", source_apply.sequence + 1),
            ("direction_generation", source_apply.direction_generation + 1),
            ("receipt_hash", "sha256:" + "f" * 64),
        ):
            original_value = getattr(source_apply, field)
            object.__setattr__(source_apply, field, replacement_value)
            try:
                with pytest.raises(HipKrylovPrimitivesContextError) as changed:
                    context._require_fgmres_solver_child(first, source_apply)
                assert changed.value.code == (
                    "hip_krylov_primitives_fgmres_source_apply_invalid"
                )
                assert context._fgmres_solver_child_token is first
            finally:
                object.__setattr__(source_apply, field, original_value)

        context._release_fgmres_solver_child(first, source_apply)
        second = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
        second_snapshot = context._fgmres_solver_child_snapshot(second, source_apply)
        assert second is not first
        assert second_snapshot is not first_snapshot
        assert second_snapshot.solver_child_lease_epoch == 2

        for operation in (
            lambda: context._require_fgmres_solver_child(first, source_apply),
            lambda: context._fgmres_solver_child_snapshot(first, source_apply),
            lambda: context._release_fgmres_solver_child(first, source_apply),
        ):
            with pytest.raises(HipKrylovPrimitivesContextError) as stale:
                operation()
            assert stale.value.code == (
                "hip_krylov_primitives_fgmres_solver_child_token_invalid"
            )
            assert context._fgmres_solver_child_token is second

        context._release_fgmres_solver_child(second, source_apply)
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_snapshot_value is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_active_fgmres_child_blocks_diagnostics_and_close_before_mutation() -> None:
    *_, runtime, parent_open, resident_open, free_open, source_apply, kernel, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    telemetry_before = context.receipt().telemetry
    runtime_before = (
        runtime.h2d_attempt_count,
        len(runtime.d2h_streams),
        len(runtime.sync_streams),
        runtime.malloc_calls,
        runtime.free_calls,
        tuple(runtime.allocations),
    )
    kernel_before = tuple(kernel.calls)
    pointers_before = dict(context._pointers)
    try:
        assert context.receipt().status == "context_ready"
        for operation in (
            context.enqueue_primitive_batch,
            context.evaluate_for_verification,
            context.close,
            lambda: context._acquire_fgmres_solver_child_for_source_apply(source_apply),
        ):
            with pytest.raises(HipKrylovPrimitivesContextError) as blocked:
                operation()
            assert blocked.value.code == (
                "hip_krylov_primitives_fgmres_solver_child_active"
            )

        assert context.receipt().telemetry == telemetry_before
        assert runtime_before == (
            runtime.h2d_attempt_count,
            len(runtime.d2h_streams),
            len(runtime.sync_streams),
            runtime.malloc_calls,
            runtime.free_calls,
            tuple(runtime.allocations),
        )
        assert tuple(kernel.calls) == kernel_before
        assert context._pointers == pointers_before

        context._release_fgmres_solver_child(token, source_apply)
        batch = context.enqueue_primitive_batch()
        assert batch.status == "enqueued"
        assert len(kernel.calls) > len(kernel_before)
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_fgmres_child_poison_is_shared_and_cleanup_retry_remains_owned() -> None:
    *_, runtime, parent_open, resident_open, free_open, source_apply, kernel, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and free is not None
    assert resident is not None and parent is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    try:
        context._poison_fgmres_solver_child(
            token, source_apply, "injected FGMRES recurrence launch failure"
        )
        assert context.poisoned and free.poisoned
        assert resident.poisoned and parent.poisoned

        with pytest.raises(HipKrylovPrimitivesContextError) as unusable:
            context._require_fgmres_solver_child(token, source_apply)
        assert unusable.value.code == "hip_krylov_primitives_context_poisoned"

        with pytest.raises(HipKrylovPrimitivesContextError) as foreign:
            context._release_fgmres_solver_child(object(), source_apply)
        assert foreign.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_token_invalid"
        )
        assert context._fgmres_solver_child_token is token

        context._release_fgmres_solver_child(token, source_apply)
        retry_pointer = context._pointers["work_x"]
        runtime.free_failure_pointer_once = retry_pointer
        with pytest.raises(HipKrylovPrimitivesContextError) as first_close:
            context.close()
        assert first_close.value.cleanup_owner is context
        assert context.receipt().status == "cleanup_failed"
        assert not kernel.closed
        assert free._krylov_consumer_token is not None

        context.close()
        assert context.closed and kernel.closed
        assert context.receipt().telemetry.lease_release_success_count == 1
        assert free._krylov_consumer_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_two_thread_fgmres_acquire_has_exactly_one_winner() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    barrier = threading.Barrier(3)
    successes: list[object] = []
    failures: list[HipKrylovPrimitivesContextError] = []

    def acquire() -> None:
        barrier.wait(timeout=5)
        try:
            successes.append(
                context._acquire_fgmres_solver_child_for_source_apply(source_apply)
            )
        except HipKrylovPrimitivesContextError as exc:
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
        assert failures[0].code == ("hip_krylov_primitives_fgmres_solver_child_active")
        winner = successes[0]
        snapshot = context._fgmres_solver_child_snapshot(winner, source_apply)
        assert snapshot.solver_child_lease_epoch == 1
        context._release_fgmres_solver_child(winner, source_apply)
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_failed_fgmres_snapshot_build_never_publishes_a_child_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    context_type = type(context)
    original_build = context_type._build_fgmres_solver_child_snapshot_locked
    call_count = 0

    def fail_once(owner: object) -> object:
        nonlocal call_count
        call_count += 1
        if owner is context and call_count == 1:
            raise RuntimeError("injected snapshot construction failure")
        return original_build(owner)

    monkeypatch.setattr(
        context_type,
        "_build_fgmres_solver_child_snapshot_locked",
        fail_once,
    )
    try:
        with pytest.raises(RuntimeError, match="snapshot construction failure"):
            context._acquire_fgmres_solver_child_for_source_apply(source_apply)
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_snapshot_value is None

        token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
        snapshot = context._fgmres_solver_child_snapshot(token, source_apply)
        assert snapshot.solver_child_lease_epoch == 2
        context._release_fgmres_solver_child(token, source_apply)
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_parent_authority_failure_is_normalized_and_shared() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    original_runtime = free._resident._runtime
    try:
        free._resident._runtime = object()
        with pytest.raises(HipKrylovPrimitivesContextError) as normalized:
            context._fgmres_solver_child_snapshot(token, source_apply)
        assert normalized.value.code == (
            "hip_krylov_primitives_fgmres_parent_authority_invalid"
        )
        assert context.poisoned and free.poisoned
    finally:
        free._resident._runtime = original_runtime
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_fgmres_snapshot_pointer_drift_poison_is_detected_but_releasable() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    original = free._pointers["reduced_load"]
    try:
        free._pointers["reduced_load"] = object()
        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._fgmres_solver_child_snapshot(token, source_apply)
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_snapshot_changed"
        )
        assert context.poisoned and free.poisoned

        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_token is None
    finally:
        free._pointers["reduced_load"] = original
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source_free_space_plan", object()),
        ("source_free_space_plan_hash", "sha256:" + "e" * 64),
        ("source_free_space_view_hash", "sha256:" + "d" * 64),
        ("architecture", "gfx1100"),
        ("loaded_runtime", object()),
    ),
)
def test_fgmres_snapshot_runtime_binding_drift_poison_is_releasable(
    field: str,
    replacement: object,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    snapshot = context._fgmres_solver_child_snapshot(token, source_apply)
    try:
        object.__setattr__(snapshot, field, replacement)
        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._fgmres_solver_child_snapshot(token, source_apply)
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_snapshot_changed"
        )
        assert context.poisoned and free.poisoned

        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_snapshot_value is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize(
    "field",
    ("source_free_space_plan_hash", "source_free_space_view_hash", "architecture"),
)
def test_fgmres_snapshot_scalar_binding_requires_exact_type(
    field: str,
) -> None:
    class EqualString(str):
        pass

    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token = context._acquire_fgmres_solver_child_for_source_apply(source_apply)
    snapshot = context._fgmres_solver_child_snapshot(token, source_apply)
    try:
        replacement = EqualString(getattr(snapshot, field))
        assert replacement == getattr(snapshot, field)
        object.__setattr__(snapshot, field, replacement)

        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._require_fgmres_solver_child(token, source_apply)
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_snapshot_changed"
        )
        assert context.poisoned and free.poisoned

        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_live_fgmres_foundation_binds_exact_parent3_and_one_exact11_borrow() -> None:
    *_, runtime, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token, parent, group = _reserve_live_group(context, source_apply)
    lease: HipAllocationBorrowLeaseV1 | None = None
    try:
        assert tuple(capability.role for capability in parent) == (
            "reduced_state",
            "reduced_load",
            "jacobi_inverse",
        )
        assert parent[0] is free._owned_capabilities["reduced_state"]
        assert parent[1] is free._owned_capabilities["reduced_load"]
        assert parent[2] is context._owned_capabilities["jacobi_inverse"]
        assert parent[0].owner_identity == free._allocation_owner.owner_id
        assert parent[1].owner_identity == free._allocation_owner.owner_id
        assert parent[2].owner_identity == context._allocation_owner.owner_id
        assert len({capability.owner_identity for capability in group}) == 3
        assert tuple(capability.role for capability in group[3:]) == _LIVE_TAIL_ROLES
        assert len({capability.owner_identity for capability in group[3:]}) == 1
        assert group[3].owner_identity not in {
            parent[0].owner_identity,
            parent[2].owner_identity,
        }
        assert all(capability.runtime_owner is runtime for capability in group)
        assert all(
            capability.runtime_domain is parent[0].runtime_domain
            and capability.runtime_domain_id == parent[0].runtime_domain_id
            and capability.device_ordinal == parent[0].device_ordinal
            and type(capability.generation) is int
            and capability.generation > 0
            for capability in group
        )
        assert context._fgmres_solver_child_phase == "semantic_reserved"
        assert context._fgmres_solver_child_group_capability_snapshot is group
        assert context._fgmres_solver_child_borrow_lease is None

        lease = _commit_live_group(context, source_apply, token, group)
        snapshot = context._fgmres_solver_child_snapshot(token, source_apply)
        assert snapshot.parent_allocation_capabilities is parent
        assert snapshot.allocation_borrow_capabilities is group
        assert snapshot.allocation_borrow_lease is lease
        assert snapshot.allocation_borrow_phase == "active"
        assert snapshot.allocation_runtime_domain is parent[0].runtime_domain
        assert snapshot.allocation_runtime_domain_id == parent[0].runtime_domain_id
        assert snapshot.allocation_device_ordinal == parent[0].device_ordinal
        assert snapshot.allocation_generations == tuple(
            capability.generation for capability in group
        )

        for owner, capability in (
            (free._allocation_owner, parent[0]),
            (free._allocation_owner, parent[1]),
            (context._allocation_owner, parent[2]),
        ):
            with pytest.raises(HipAllocationLineageError) as blocked:
                owner.begin_free(capability)
            assert blocked.value.code == "hip_allocation_free_busy"
        with pytest.raises(HipKrylovPrimitivesContextError) as close_blocked:
            context.close()
        assert close_blocked.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_active"
        )

        with pytest.raises(HipKrylovPrimitivesContextError) as split_required:
            context._release_fgmres_solver_child(token, source_apply)
        assert split_required.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_split_release_required"
        )
        assert validate_hip_allocation_borrow_v1(lease) is lease

        context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
        with pytest.raises(HipKrylovPrimitivesContextError) as owner_open:
            context._release_fgmres_solver_child(token, source_apply)
        assert owner_open.value.code == (
            "hip_krylov_primitives_fgmres_owned_owner_open"
        )
        _retire_live_owned_group(context, owner, group)
        _LIVE_TEST_OWNERS.pop(id(context))
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_two_thread_live_fgmres_reservation_has_exactly_one_winner() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    barrier = threading.Barrier(3)
    successes: list[tuple[object, tuple[Any, ...], Any]] = []
    failures: list[HipKrylovPrimitivesContextError] = []

    def reserve() -> None:
        token = object()
        owner = open_hip_allocation_peer_owner_v1(
            context._allocation_owner,
            "fgmres_checkpoint_owned_buffers",
        )
        barrier.wait(timeout=5)
        try:
            parent = context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
            successes.append((token, parent, owner))
        except HipKrylovPrimitivesContextError as exc:
            failures.append(exc)
            owner.close(_control_token=token)

    threads = tuple(threading.Thread(target=reserve, daemon=True) for _ in range(2))
    try:
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
        assert all(not thread.is_alive() for thread in threads)
        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].code == ("hip_krylov_primitives_fgmres_solver_child_active")
        winner, parent, owner = successes[0]
        _LIVE_TEST_OWNERS[id(context)] = (context, owner, ())
        assert parent is context._fgmres_solver_child_parent_capability_snapshot
        context._recover_fgmres_solver_child_allocation_borrow(winner)
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        owner.close(_control_token=winner)
        context._release_fgmres_solver_child(winner, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("token", ("not-an-object-token", type("Token", (), {})()))
def test_live_reservation_requires_exact_builtin_object_token(token: object) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = _open_live_owned_owner(context)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_token_invalid"
        )
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_epoch_value == 0
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


@pytest.mark.parametrize("forgery", ("role_swap", "krylov_work"))
def test_live_owned8_role_or_owner_forgery_rolls_back_before_borrow(
    forgery: str,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    group = _allocate_live_owned_group(context, parent, owner)
    forged = list(group)
    if forgery == "role_swap":
        forged[-1], forged[-2] = forged[-2], forged[-1]
    else:
        forged[3] = context._owned_capabilities["work_x"]
    forged_group = tuple(forged)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._prepare_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                forged_group,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_allocation_group_invalid"
        )
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_group_capability_snapshot is None

        probe = borrow_hip_allocations_v1(group, token)
        release_hip_allocation_borrow_v1(probe)
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_live_reservation_token_publication_interruption_rolls_back() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    interrupt = _SingleFireLineInterrupt(
        type(context)._reserve_fgmres_solver_child_for_source_apply,
        lambda _frame: (
            context._fgmres_solver_child_token is token
            and context._fgmres_solver_child_phase == "semantic_reserved"
        ),
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert interrupt.fired
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_parent_capability_snapshot is not None
        assert context._fgmres_solver_child_owned_owner_snapshot is owner
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_live_reservation_before_token_store_interruption_rolls_back() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    interrupt = _SingleFireLineInterrupt(
        type(context)._reserve_fgmres_solver_child_for_source_apply,
        lambda _frame: (
            context._fgmres_solver_child_token is None
            and context._fgmres_solver_child_phase == "semantic_reserved"
        ),
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert interrupt.fired
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_parent_capability_snapshot is not None
        assert context._fgmres_solver_child_owned_owner_snapshot is owner
        assert context._released_fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_exact11_prepublication_interruption_rolls_back_without_borrow() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    group = _allocate_live_owned_group(context, parent, owner)
    interrupt = _SingleFireLineInterrupt(
        type(context)._prepare_fgmres_solver_child_allocation_borrow,
        lambda _frame: context._fgmres_solver_child_group_capability_snapshot is group,
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            context._prepare_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                group,
            )
        assert interrupt.fired
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        probe = borrow_hip_allocations_v1(group, token)
        release_hip_allocation_borrow_v1(probe)
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_lost_borrow_return_is_recovered_from_preissued_token_and_exact11() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = borrow_hip_allocations_v1(group, token)
    try:
        assert context._fgmres_solver_child_borrow_lease is None
        context._recover_fgmres_solver_child_allocation_borrow(token)
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_commit_lease_store_interruption_releases_exact11(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = borrow_hip_allocations_v1(group, token)

    def interrupt_after_store(actual: HipAllocationBorrowLeaseV1) -> object:
        assert actual is lease
        assert context._fgmres_solver_child_borrow_lease is lease
        raise KeyboardInterrupt("injected after child lease STORE")

    monkeypatch.setattr(
        primitives,
        "validate_hip_allocation_borrow_v1",
        interrupt_after_store,
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            context._commit_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                group,
                lease,
            )
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_token is token
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_commit_phase_interruption_rolls_back_committed_exact11() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = borrow_hip_allocations_v1(group, token)
    interrupt = _SingleFireLineInterrupt(
        type(context)._commit_fgmres_solver_child_allocation_borrow,
        lambda _frame: (
            context._fgmres_solver_child_phase == "active"
            and context._fgmres_solver_child_rollback_pending
        ),
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            context._commit_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                group,
                lease,
            )
        assert interrupt.fired
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_token is token
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_release_terminal_marker_interruption_finishes_field_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
    context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
    _retire_live_owned_group(context, owner, group)
    _LIVE_TEST_OWNERS.pop(id(context))
    original_finish = type(context)._finish_fgmres_solver_child_terminal_locked
    interrupted = False

    def interrupt_once(actual_context: Any, actual_token: object) -> None:
        nonlocal interrupted
        assert actual_context is context and actual_token is token
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt("injected after semantic terminal marker")
        original_finish(actual_context, actual_token)

    monkeypatch.setattr(
        type(context),
        "_finish_fgmres_solver_child_terminal_locked",
        interrupt_once,
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            context._release_fgmres_solver_child(token, source_apply)
        assert interrupted
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_owned_owner_snapshot is owner
        context._release_fgmres_solver_child(token, source_apply)
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_group_capability_snapshot is None
        assert context._fgmres_solver_child_borrow_lease is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_release_field_clear_interruption_finishes_from_terminal_marker() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
    context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
    _retire_live_owned_group(context, owner, group)
    _LIVE_TEST_OWNERS.pop(id(context))
    interrupt = _SingleFireLineInterrupt(
        type(context)._finish_fgmres_solver_child_terminal_locked,
        lambda _frame: (
            context._fgmres_solver_child_parent_capability_snapshot is None
            and context._fgmres_solver_child_owned_owner_snapshot is owner
            and context._fgmres_solver_child_token is token
        ),
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            context._release_fgmres_solver_child(token, source_apply)
        assert interrupt.fired
        assert context._fgmres_solver_child_owned_owner_snapshot is owner
        context._release_fgmres_solver_child(token, source_apply)
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_snapshot_value is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_live_snapshot_allocation_tamper_poison_is_exactly_releasable() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    snapshot = context._fgmres_solver_child_snapshot(token, source_apply)
    try:
        object.__setattr__(
            snapshot,
            "allocation_generations",
            snapshot.allocation_generations[:-1] + (10**9,),
        )
        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._require_fgmres_solver_child(token, source_apply)
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_snapshot_changed"
        )
        assert context.poisoned and free.poisoned

        _release_live_solver_child(context)
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_preborrow_capability_generation_tamper_poison_rolls_back() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    group = _allocate_live_owned_group(context, parent, owner)
    target = group[-1]
    original_generation = target.generation
    try:
        object.__setattr__(target, "generation", original_generation + 1)
        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._prepare_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                group,
            )
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_allocation_group_invalid"
        )
        assert context.poisoned and free.poisoned
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_token is token
    finally:
        object.__setattr__(target, "generation", original_generation)
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_commit_tuple_identity_tamper_releases_the_exact_registry_lease() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = borrow_hip_allocations_v1(group, token)
    forged_group = tuple(list(group))
    assert forged_group == group and forged_group is not group
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as changed:
            context._commit_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                forged_group,
                lease,
            )
        assert changed.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_transaction_changed"
        )
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_token is token
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_split_group_release_retains_semantic_parent_until_owned8_retire() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, parent_capabilities, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
    try:
        context._release_fgmres_solver_child_allocation_borrow(
            token,
            source_apply,
        )
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_parent_capability_snapshot is (
            parent_capabilities
        )
        assert context._fgmres_solver_child_group_capability_snapshot is None
        assert context._fgmres_solver_child_borrow_lease is None

        with pytest.raises(HipKrylovPrimitivesContextError) as still_blocked:
            context.enqueue_primitive_batch()
        assert still_blocked.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_active"
        )

        _retire_live_owned_group(context, owner, group)
        _LIVE_TEST_OWNERS.pop(id(context))
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_split_group_release_rejects_wrong_token_and_source_without_mutation() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    forged_source = replace(source_apply)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as wrong_token:
            context._release_fgmres_solver_child_allocation_borrow(
                object(), source_apply
            )
        assert wrong_token.value.code == (
            "hip_krylov_primitives_fgmres_solver_child_token_invalid"
        )
        with pytest.raises(HipKrylovPrimitivesContextError) as wrong_source:
            context._release_fgmres_solver_child_allocation_borrow(token, forged_source)
        assert wrong_source.value.code == (
            "hip_krylov_primitives_fgmres_source_apply_invalid"
        )
        assert context._fgmres_solver_child_phase == "active"
        assert validate_hip_allocation_borrow_v1(lease) is lease
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_live_reservation_rejects_parent_closed_and_foreign_exact_owners() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    closed_owner = open_hip_allocation_peer_owner_v1(
        context._allocation_owner,
        "test_fgmres_closed_owner",
    )
    closed_owner.close()
    try:
        for owner in (context._allocation_owner, closed_owner):
            with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
                context._reserve_fgmres_solver_child_for_source_apply(
                    source_apply,
                    object(),
                    owner,
                )
            assert rejected.value.code == (
                "hip_krylov_primitives_fgmres_owned_owner_invalid"
            )
            assert context._fgmres_solver_child_phase == "idle"
            assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_owned8_freed_but_owner_open_blocks_final_and_recover_bypass() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, parent_capabilities, group = _reserve_live_group(context, source_apply)
    lease = _commit_live_group(context, source_apply, token, group)
    _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
    try:
        context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
        _free_live_owned_capabilities(context, owner, group)
        for finalize in (
            lambda: context._release_fgmres_solver_child(token, source_apply),
            lambda: context._recover_fgmres_solver_child_allocation_borrow(token),
        ):
            with pytest.raises(HipKrylovPrimitivesContextError) as owner_open:
                finalize()
            assert owner_open.value.code == (
                "hip_krylov_primitives_fgmres_owned_owner_open"
            )
            assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
            assert context._fgmres_solver_child_token is token
            assert context._fgmres_solver_child_parent_capability_snapshot is (
                parent_capabilities
            )
            assert context._fgmres_solver_child_owned_owner_snapshot is owner
        with pytest.raises(HipAllocationLineageError) as released:
            validate_hip_allocation_borrow_v1(lease)
        assert released.value.code == "hip_allocation_borrow_released"

        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context))
        context._recover_fgmres_solver_child_allocation_borrow(token)
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
        assert context._fgmres_solver_child_owned_owner_snapshot is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_owner_close_return_interruption_preserves_monotonic_closed_witness() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token, _, group = _reserve_live_group(context, source_apply)
    _commit_live_group(context, source_apply, token, group)
    _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
    context._release_fgmres_solver_child_allocation_borrow(token, source_apply)
    _free_live_owned_capabilities(context, owner, group)
    interrupt = _SingleFireLineInterrupt(
        type(owner).close,
        lambda frame: (
            frame.f_locals.get("closed_snapshot") is not None
            and frame.f_globals["_CLOSED_OWNERS"].get(owner)
            == frame.f_locals["closed_snapshot"]
            and owner.closed is True
        ),
    )
    try:
        with interrupt, pytest.raises(KeyboardInterrupt):
            owner.close(_control_token=token)
        assert interrupt.fired
        assert owner.closed is True
        _LIVE_TEST_OWNERS.pop(id(context))
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_twenty_concurrent_split_final_and_recover_rounds_converge() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    try:
        for _round in range(20):
            token, _, group = _reserve_live_group(context, source_apply)
            lease = _commit_live_group(context, source_apply, token, group)
            _, owner, _ = _LIVE_TEST_OWNERS[id(context)]
            split_errors: list[BaseException] = []
            split_barrier = threading.Barrier(3)

            def split() -> None:
                split_barrier.wait(timeout=5)
                try:
                    context._release_fgmres_solver_child_allocation_borrow(
                        token,
                        source_apply,
                    )
                except BaseException as exc:  # pragma: no cover - asserted empty
                    split_errors.append(exc)

            split_threads = tuple(
                threading.Thread(target=split, daemon=True) for _ in range(2)
            )
            for thread in split_threads:
                thread.start()
            split_barrier.wait(timeout=5)
            for thread in split_threads:
                thread.join(timeout=5)
            assert all(not thread.is_alive() for thread in split_threads)
            assert split_errors == []
            assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
            with pytest.raises(HipAllocationLineageError) as released:
                validate_hip_allocation_borrow_v1(lease)
            assert released.value.code == "hip_allocation_borrow_released"

            _free_live_owned_capabilities(context, owner, group)
            owner.close(_control_token=token)
            _LIVE_TEST_OWNERS.pop(id(context))
            terminal_errors: list[BaseException] = []
            terminal_barrier = threading.Barrier(3)

            def final_semantic() -> None:
                terminal_barrier.wait(timeout=5)
                try:
                    context._release_fgmres_solver_child(token, source_apply)
                except BaseException as exc:  # pragma: no cover - asserted empty
                    terminal_errors.append(exc)

            def recover_semantic() -> None:
                terminal_barrier.wait(timeout=5)
                try:
                    context._recover_fgmres_solver_child_allocation_borrow(token)
                except BaseException as exc:  # pragma: no cover - asserted empty
                    terminal_errors.append(exc)

            terminal_threads = (
                threading.Thread(target=final_semantic, daemon=True),
                threading.Thread(target=recover_semantic, daemon=True),
            )
            for thread in terminal_threads:
                thread.start()
            terminal_barrier.wait(timeout=5)
            for thread in terminal_threads:
                thread.join(timeout=5)
            assert all(not thread.is_alive() for thread in terminal_threads)
            assert terminal_errors == []
            assert context._fgmres_solver_child_phase == "idle"
            assert context._fgmres_solver_child_token is None
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_control_reservation_rejects_nonfresh_owner_with_extra_capability() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = _open_live_owned_owner(context)
    token = object()
    extra = owner.allocate("extra_before_control", 8, "u8")
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_owned_owner_invalid"
        )
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
    finally:
        lease = owner.begin_free(extra, _control_token=token)
        context._runtime.free(lease.pointer_snapshot)
        owner.resolve_free_success(lease, _control_token=token)
        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context), None)
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_control_reservation_rejects_wrong_owner_role() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = open_hip_allocation_peer_owner_v1(
        context._allocation_owner,
        "not_fgmres_checkpoint_owned_buffers",
    )
    token = object()
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_owned_owner_invalid"
        )
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        owner.close(_control_token=token)
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_control_reservation_rejects_prior_pending_free_state() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = _open_live_owned_owner(context)
    token = object()
    capability = owner.allocate("solution_x", 8, "u8")
    pending = owner.begin_free(capability)
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_owned_owner_invalid"
        )
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        context._runtime.free(pending.pointer_snapshot)
        owner.resolve_free_success(pending, _control_token=token)
        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context), None)
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_control_reservation_closes_prevalidation_to_control_toctou(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = _open_live_owned_owner(context)
    token = object()
    original = type(context)._validate_fgmres_owned_owner_for_reservation

    def validate_then_close(primitive: Any, candidate: Any) -> Any:
        result = original(primitive, candidate)
        assert candidate is owner
        owner.close(_control_token=token)
        return result

    monkeypatch.setattr(
        type(context),
        "_validate_fgmres_owned_owner_for_reservation",
        validate_then_close,
    )
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_owned_owner_invalid"
        )
        assert owner.closed
        assert context._fgmres_solver_child_phase == "idle"
        assert context._fgmres_solver_child_token is None
    finally:
        _LIVE_TEST_OWNERS.pop(id(context), None)
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_control_publish_return_interruption_recovers_semantic_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    owner = _open_live_owned_owner(context)
    token = object()
    original = primitives.reserve_hip_allocation_owner_control_v1
    fired = False

    def reserve_then_interrupt(*args: Any, **kwargs: Any) -> Any:
        nonlocal fired
        result = original(*args, **kwargs)
        if not fired:
            fired = True
            raise KeyboardInterrupt("owner control return STORE interrupted")
        return result

    monkeypatch.setattr(
        primitives,
        "reserve_hip_allocation_owner_control_v1",
        reserve_then_interrupt,
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            context._reserve_fgmres_solver_child_for_source_apply(
                source_apply,
                token,
                owner,
            )
        assert fired
        assert context._fgmres_solver_child_token is token
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        with pytest.raises(HipAllocationLineageError) as foreign_close:
            owner.close()
        assert "control" in foreign_close.value.code

        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context), None)
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_prepare_rejects_pending_free_in_exact_owned8_cleanup_snapshot() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    group = _allocate_live_owned_group(context, parent, owner)
    pending = owner.begin_free(group[-1], _control_token=token)
    try:
        try:
            with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
                context._prepare_fgmres_solver_child_allocation_borrow(
                    token,
                    source_apply,
                    group,
                )
            assert rejected.value.code == (
                "hip_krylov_primitives_fgmres_allocation_group_invalid"
            )
            assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
            assert context._fgmres_solver_child_token is token
        finally:
            context._runtime.free(pending.pointer_snapshot)
            owner.resolve_free_success(pending, _control_token=token)

        for capability in reversed(group[3:-1]):
            lease = owner.begin_free(capability, _control_token=token)
            context._runtime.free(lease.pointer_snapshot)
            owner.resolve_free_success(lease, _control_token=token)
        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context), None)
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)


def test_prepare_rejects_exact_owned8_snapshot_with_ninth_publication_history() -> None:
    *_, parent_open, resident_open, free_open, source_apply, _, opened = (
        _open_primitives()
    )
    context = opened.context
    assert context is not None
    token = object()
    owner = _open_live_owned_owner(context)
    parent = context._reserve_fgmres_solver_child_for_source_apply(
        source_apply,
        token,
        owner,
    )
    transient = owner.allocate(
        _LIVE_TAIL_ROLES[0],
        8,
        "u8",
        _control_token=token,
    )
    transient_free = owner.begin_free(transient, _control_token=token)
    context._runtime.free(transient_free.pointer_snapshot)
    owner.resolve_free_success(transient_free, _control_token=token)
    group = _allocate_live_owned_group(context, parent, owner)
    capabilities, pending_frees, pending_orphans = owner.cleanup_snapshot()
    assert capabilities == group[3:]
    assert pending_frees == ()
    assert pending_orphans == ()
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as rejected:
            context._prepare_fgmres_solver_child_allocation_borrow(
                token,
                source_apply,
                group,
            )
        assert rejected.value.code == (
            "hip_krylov_primitives_fgmres_allocation_group_invalid"
        )
        assert "publication" in rejected.value.message
        assert context._fgmres_solver_child_phase == "semantic_cleanup_active"
        assert context._fgmres_solver_child_token is token

        _free_live_owned_capabilities(context, owner, group)
        owner.close(_control_token=token)
        _LIVE_TEST_OWNERS.pop(id(context), None)
        context._release_fgmres_solver_child(token, source_apply)
        assert context._fgmres_solver_child_phase == "idle"
    finally:
        _release_live_solver_child(context)
        _close_all(opened, free_open, resident_open, parent_open)
