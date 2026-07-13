from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import gc
from pathlib import Path
import sys
import threading
from typing import Any, Callable
import weakref

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import structural_analysis.engine_v2 as engine_v2_public  # noqa: E402
import structural_analysis.engine_v2.assembly_backend as assembly_backend_public  # noqa: E402
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    hip_allocation_lineage as lineage,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (  # noqa: E402
    HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
    HipAllocationBorrowLeaseV1,
    HipAllocationCapabilityV1,
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
    borrow_hip_allocations_v1,
    open_hip_allocation_peer_owner_v1,
    release_hip_allocation_borrow_v1,
    reserve_hip_allocation_owner_control_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_capability_v1,
    validate_hip_allocation_owner_control_v1,
)
from structural_analysis.engine_v2.backends.hip.context import (  # noqa: E402
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    load_hip_native_runtime,
)
from tests.test_engine_v2_hip_fgmres_rtc_v2 import (  # noqa: E402
    _compile_sealed_native_runtime_library,
)


class FakeAllocationRuntime:
    """Injected allocator fixture; lineage must never call ``free`` itself."""

    def __init__(
        self,
        *,
        pointers: tuple[Any, ...] = (0x100000, 0x200000, 0x300000),
        malloc_status: int = 0,
        malloc_exception: bool = False,
        malloc_callback: Any | None = None,
        free_fail_count: int = 0,
        free_exception: bool = False,
        device_ordinal: int = 0,
    ) -> None:
        self._pointers = list(pointers)
        self.malloc_status = malloc_status
        self.malloc_exception = malloc_exception
        self.malloc_callback = malloc_callback
        self.free_fail_count = free_fail_count
        self.free_exception = free_exception
        self._device_ordinal = device_ordinal
        self.device_callback: Any | None = None
        self.malloc_calls: list[int] = []
        self.free_calls: list[int] = []
        self._pointer_lock = threading.Lock()

    @property
    def device_ordinal(self) -> int:
        if self.device_callback is not None:
            self.device_callback()
        return self._device_ordinal

    @device_ordinal.setter
    def device_ordinal(self, value: int) -> None:
        self._device_ordinal = value

    def malloc(self, nbytes: int) -> Any:
        self.malloc_calls.append(nbytes)
        if self.malloc_callback is not None:
            self.malloc_callback()
        if self.malloc_exception:
            raise RuntimeError("injected malloc exception")
        if self.malloc_status:
            raise RuntimeError(f"injected malloc status {self.malloc_status}")
        with self._pointer_lock:
            if not self._pointers:
                raise RuntimeError("injected pointer queue exhausted")
            pointer = self._pointers.pop(0)
        return (
            ctypes.c_void_p(pointer)
            if type(pointer) is int and pointer > 0
            else pointer
        )

    def free(self, pointer: Any) -> None:
        value = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
        self.free_calls.append(int(value))
        if self.free_exception:
            raise RuntimeError("injected free exception")
        if self.free_fail_count:
            self.free_fail_count -= 1
            raise RuntimeError("injected free failure")


class _FailOnceRegistry(dict[int, Any]):
    """Dict seam that fails exactly the first publication write."""

    def __init__(self, values: dict[int, Any]) -> None:
        super().__init__(values)
        self.fail_next_write = True

    def __setitem__(self, key: int, value: Any) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise MemoryError("injected registry publication failure")
        super().__setitem__(key, value)


class _FailOnceWeakRegistry(weakref.WeakKeyDictionary[Any, Any]):
    """Weak tombstone registry that rejects exactly one terminal write."""

    def __init__(self, values: weakref.WeakKeyDictionary[Any, Any]) -> None:
        self.fail_next_write = False
        super().__init__(values)
        self.fail_next_write = True

    def __setitem__(self, key: Any, value: Any) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise MemoryError("injected weak tombstone publication failure")
        super().__setitem__(key, value)


class _StoreThenInterruptWeakRegistry(weakref.WeakKeyDictionary[Any, Any]):
    """Publish one terminal marker, then raise one asynchronous exception."""

    def __init__(self, values: weakref.WeakKeyDictionary[Any, Any]) -> None:
        self.interrupt_next_write = False
        super().__init__(values)
        self.interrupt_next_write = True

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        if self.interrupt_next_write:
            self.interrupt_next_write = False
            raise KeyboardInterrupt("injected interruption after terminal marker")


class _FailOnceSet(set[Any]):
    """Set seam that rejects its first new witness publication."""

    def __init__(self, values: set[Any]) -> None:
        super().__init__(values)
        self.fail_next_add = True

    def add(self, value: Any) -> None:
        if self.fail_next_add:
            self.fail_next_add = False
            raise MemoryError("injected poison-domain witness failure")
        super().add(value)


class _ReleaseThenInterruptPublicationLock:
    """Raise once after releasing the wrapped publication mutex."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.interrupt_next_release = True

    def __enter__(self) -> _ReleaseThenInterruptPublicationLock:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        self._lock.release()
        if self.interrupt_next_release:
            self.interrupt_next_release = False
            raise KeyboardInterrupt("injected publication release interruption")

    def locked(self) -> bool:
        return self._lock.locked()


class _SingleFireLineInterrupt:
    """Inject one KeyboardInterrupt at a predicate-matched line event."""

    def __init__(
        self,
        target: Callable[..., object],
        predicate: Callable[[Any], bool],
    ) -> None:
        self._target_code = target.__code__
        self._predicate = predicate
        self._previous_trace: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if (
            not self.fired
            and event == "line"
            and frame.f_code is self._target_code
            and self._predicate(frame)
        ):
            self.fired = True
            sys.settrace(self._previous_trace)
            raise KeyboardInterrupt("injected authority handoff interruption")
        return self._trace

    def __enter__(self) -> _SingleFireLineInterrupt:
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous_trace)


def _assert_error(exc: BaseException, fragment: str) -> None:
    text = " ".join(
        str(value)
        for value in (
            getattr(exc, "code", ""),
            getattr(exc, "path", ""),
            str(exc),
        )
    ).lower()
    assert fragment.lower() in text


def _pointer_value(value: Any) -> int:
    raw = value.value if isinstance(value, ctypes.c_void_p) else value
    return int(raw)


def _open_owner(
    runtime: FakeAllocationRuntime,
    *,
    device_ordinal: int = 0,
    owner_role: str = "test_owner",
) -> HipAllocationOwnerV1:
    return lineage._open_injected_hip_allocation_owner_v1(
        runtime,
        device_ordinal,
        owner_role,
        _mint=lineage._INJECTED_HIP_ALLOCATION_OWNER_MINT,
    )


def _free_success(
    owner: HipAllocationOwnerV1,
    runtime: FakeAllocationRuntime,
    capability: HipAllocationCapabilityV1,
) -> None:
    lease = owner.begin_free(capability)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease)


def _orphan_free_success(
    owner: HipAllocationOwnerV1,
    runtime: FakeAllocationRuntime,
    error: HipAllocationLineageError,
) -> None:
    lease = error.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    _assert_foundation(lease)
    assert lease.pointer_snapshot is not None
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_orphan_free_success(lease)


def _quarantine_orphan(
    owner: HipAllocationOwnerV1,
    error: HipAllocationLineageError,
) -> None:
    lease = error.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    _assert_foundation(lease)
    owner.quarantine_orphan_free_uncertain(lease)


def _copy_slots(value: Any) -> Any:
    forged = object.__new__(type(value))
    for name in type(value).__slots__:
        if hasattr(value, name):
            object.__setattr__(forged, name, getattr(value, name))
    return forged


def _assert_foundation(value: Any) -> None:
    assert value.evidence_scope == HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1
    assert value.evidence_scope == "foundation_non_promoting"
    assert value.promotion_eligible is False


def test_public_surface_has_no_register_or_adopt_entrypoint() -> None:
    assert not hasattr(lineage, "register_hip_allocation_v1")
    assert not hasattr(lineage, "adopt_hip_allocation_v1")
    assert not hasattr(lineage, "acknowledge_free_failure")
    assert "register_hip_allocation_v1" not in lineage.__all__
    assert "adopt_hip_allocation_v1" not in lineage.__all__


def test_peer_owner_factory_is_exported_with_one_public_identity() -> None:
    assert (
        lineage.open_hip_allocation_peer_owner_v1 is open_hip_allocation_peer_owner_v1
    )
    assert (
        assembly_backend_public.open_hip_allocation_peer_owner_v1
        is open_hip_allocation_peer_owner_v1
    )
    assert (
        engine_v2_public.open_hip_allocation_peer_owner_v1
        is open_hip_allocation_peer_owner_v1
    )
    assert "open_hip_allocation_peer_owner_v1" in lineage.__all__
    assert "open_hip_allocation_peer_owner_v1" in assembly_backend_public.__all__
    assert "open_hip_allocation_peer_owner_v1" in engine_v2_public.__all__


@pytest.mark.parametrize(
    "artifact_type",
    (
        HipAllocationCapabilityV1,
        HipAllocationBorrowLeaseV1,
        HipAllocationFreeLeaseV1,
        HipAllocationOrphanLeaseV1,
        HipAllocationOwnerV1,
    ),
)
def test_authority_artifacts_are_not_directly_constructible(
    artifact_type: type[Any],
) -> None:
    with pytest.raises(TypeError):
        artifact_type()


def test_private_factories_and_mints_reject_forgery() -> None:
    runtime = FakeAllocationRuntime()
    with pytest.raises(HipAllocationLineageError):
        lineage._open_injected_hip_allocation_owner_v1(
            runtime,
            0,
            "owner",
            _mint=object(),
        )
    assert lineage._INJECTED_HIP_ALLOCATION_OWNER_MINT not in lineage.__all__
    assert lineage._issue not in tuple(
        getattr(lineage, name) for name in lineage.__all__
    )


@pytest.mark.parametrize("device", (True, -1, 1 << 31, 1.0, "0"))
def test_owner_device_requires_exact_nonnegative_int(device: Any) -> None:
    with pytest.raises(HipAllocationLineageError) as caught:
        _open_owner(FakeAllocationRuntime(), device_ordinal=device)
    _assert_error(caught.value, "device")


@pytest.mark.parametrize("role", ("", " owner", "owner ", "x" * 129, 1, True))
def test_owner_role_requires_exact_trimmed_string(role: Any) -> None:
    with pytest.raises(HipAllocationLineageError) as caught:
        _open_owner(FakeAllocationRuntime(), owner_role=role)
    _assert_error(caught.value, "role")


def test_peer_owner_shares_domain_for_atomic_borrow_and_closes_independently() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x108000, 0x109000, 0x10A000))
    parent = _open_owner(runtime, owner_role="free_space")
    peer = open_hip_allocation_peer_owner_v1(parent, "krylov_primitives")

    assert parent is not peer
    assert parent.owner_role == "free_space"
    assert peer.owner_role == "krylov_primitives"
    assert parent.runtime_domain_id == peer.runtime_domain_id

    parent_capability = parent.allocate("reduced_state", 16, "f64")
    peer_capability = peer.allocate("jacobi_inverse", 16, "f64")
    assert parent_capability.owner_identity != peer_capability.owner_identity
    assert parent_capability.runtime_owner is runtime
    assert peer_capability.runtime_owner is runtime
    assert parent_capability.runtime_domain is peer_capability.runtime_domain
    assert parent_capability.device_ordinal == peer_capability.device_ordinal == 0
    assert parent_capability.generation < peer_capability.generation
    assert parent.generation == parent_capability.generation
    assert peer.generation == peer_capability.generation

    borrower = object()
    lease = borrow_hip_allocations_v1(
        (parent_capability, peer_capability),
        borrower,
    )
    assert lease.borrower is borrower
    assert lease.capabilities == (parent_capability, peer_capability)
    assert validate_hip_allocation_borrow_v1(lease) is lease
    with pytest.raises(HipAllocationLineageError) as parent_busy:
        parent.begin_free(parent_capability)
    _assert_error(parent_busy.value, "busy")
    with pytest.raises(HipAllocationLineageError) as peer_busy:
        peer.begin_free(peer_capability)
    _assert_error(peer_busy.value, "busy")
    release_hip_allocation_borrow_v1(lease)

    _free_success(peer, runtime, peer_capability)
    peer.close()
    assert peer.closed is True
    assert parent.closed is False
    assert parent.validate(parent_capability) is parent_capability

    followup = parent.allocate("reduced_load", 16, "f64")
    assert followup.generation > peer_capability.generation
    _free_success(parent, runtime, followup)
    _free_success(parent, runtime, parent_capability)
    parent.close()


def test_peer_owner_rejects_parent_device_drift_without_publication() -> None:
    runtime = FakeAllocationRuntime(device_ordinal=0)
    parent = _open_owner(runtime, owner_role="free_space")
    owners_before = dict(lineage._OWNERS)
    runtime.device_ordinal = 1
    try:
        with pytest.raises(HipAllocationLineageError) as caught:
            open_hip_allocation_peer_owner_v1(parent, "krylov_primitives")
        _assert_error(caught.value, "device")
        assert lineage._OWNERS == owners_before
    finally:
        runtime.device_ordinal = 0
        parent.close()


def test_peer_owner_rejects_closed_parent_without_publication() -> None:
    parent = _open_owner(FakeAllocationRuntime(), owner_role="free_space")
    parent.close()
    owners_before = dict(lineage._OWNERS)
    with pytest.raises(HipAllocationLineageError) as caught:
        open_hip_allocation_peer_owner_v1(parent, "krylov_primitives")
    _assert_error(caught.value, "owner")
    assert lineage._OWNERS == owners_before


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("_owner_id", 999),
        ("_lock", None),
        ("_runtime_domain_id_snapshot", "forged-domain"),
    ),
)
def test_peer_owner_rejects_tampered_parent_without_publication(
    field: str,
    mutated: Any,
) -> None:
    parent = _open_owner(FakeAllocationRuntime(), owner_role="free_space")
    owners_before = dict(lineage._OWNERS)
    original = getattr(parent, field)
    object.__setattr__(parent, field, mutated)
    try:
        with pytest.raises(HipAllocationLineageError) as caught:
            open_hip_allocation_peer_owner_v1(parent, "krylov_primitives")
        _assert_error(caught.value, "owner")
        assert lineage._OWNERS == owners_before
    finally:
        object.__setattr__(parent, field, original)
        parent.close()


def test_owner_and_capability_are_read_only_nonpromoting_authority() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x110000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 16, "f64")
    _assert_foundation(owner)
    _assert_foundation(capability)
    assert owner.validate(capability) is capability
    assert validate_hip_allocation_capability_v1(capability) is capability
    with pytest.raises(AttributeError):
        owner.owner_role = "changed"
    with pytest.raises((AttributeError, FrozenInstanceError)):
        capability.role = "changed"
    assert runtime.free_calls == []
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize(
    ("nbytes", "element_type", "fragment"),
    (
        (True, "u8", "extent"),
        (0, "u8", "extent"),
        (-1, "u8", "extent"),
        (3, "i32", "extent"),
        (4, "f64", "extent"),
        (1 << (8 * ctypes.sizeof(ctypes.c_void_p)), "u8", "extent"),
        (8, "f32", "element"),
        (8, 1, "element"),
        (8, True, "element"),
    ),
)
def test_extent_and_element_type_fail_before_malloc(
    nbytes: Any,
    element_type: Any,
    fragment: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x120000,))
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", nbytes, element_type)
    _assert_error(caught.value, fragment)
    assert caught.value.orphaned_pointer is None
    assert runtime.malloc_calls == []
    assert owner.generation == 0
    owner.close()


@pytest.mark.parametrize("role", ("", " role", "role ", 1, True))
def test_allocation_role_fails_before_malloc(role: Any) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x130000,))
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate(role, 8, "f64")
    _assert_error(caught.value, "role")
    assert runtime.malloc_calls == []
    owner.close()


@pytest.mark.parametrize(
    ("pointer", "nbytes", "element_type", "fragment"),
    (
        (0, 8, "f64", "pointer"),
        (-8, 8, "f64", "pointer"),
        (True, 1, "u8", "pointer"),
        (ctypes.c_void_p(), 1, "u8", "pointer"),
        (object(), 1, "u8", "pointer"),
        (0x140004, 8, "f64", "alignment"),
        (((1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 3), 8, "u8", "overflow"),
    ),
)
def test_post_malloc_invalid_pointer_is_exposed_for_external_cleanup(
    pointer: Any,
    nbytes: int,
    element_type: str,
    fragment: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(pointer,))
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", nbytes, element_type)
    _assert_error(caught.value, fragment)
    assert caught.value.orphaned_pointer is not None
    assert type(caught.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    assert runtime.free_calls == []
    assert owner.generation == 0
    base = caught.value.orphaned_pointer
    freeable = (type(base) is int and base > 0) or (
        type(base) is ctypes.c_void_p and type(base.value) is int and base.value > 0
    )
    if freeable:
        _orphan_free_success(owner, runtime, caught.value)
    else:
        _quarantine_orphan(owner, caught.value)
    owner.close()


def test_copied_foreign_and_tampered_orphan_cleanup_lease_are_rejected() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x145004,))
    owner = _open_owner(runtime, owner_role="owner")
    foreign = _open_owner(runtime, owner_role="foreign")
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "f64")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    forged = _copy_slots(lease)
    with pytest.raises(HipAllocationLineageError):
        owner.acknowledge_orphan_free_success(forged)
    with pytest.raises(HipAllocationLineageError) as foreign_error:
        foreign.acknowledge_orphan_free_success(lease)
    _assert_error(foreign_error.value, "foreign")
    original_role = lease.role
    object.__setattr__(lease, "role", "forged")
    try:
        with pytest.raises(HipAllocationLineageError):
            owner.acknowledge_orphan_free_success(lease)
    finally:
        object.__setattr__(lease, "role", original_role)
    _orphan_free_success(owner, runtime, caught.value)
    owner.close()
    foreign.close()


def test_malloc_failure_publishes_nothing_and_retry_starts_at_generation_one() -> None:
    runtime = FakeAllocationRuntime(
        pointers=(0x150000,),
        malloc_exception=True,
    )
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "f64")
    _assert_error(caught.value, "malloc")
    assert caught.value.orphaned_pointer is None
    assert owner.generation == 0
    runtime.malloc_exception = False
    capability = owner.allocate("state", 8, "f64")
    assert capability.generation == 1
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize(
    ("pointer", "nbytes", "element_type"),
    (
        (0x160000, 16, "f64"),
        (ctypes.c_void_p(0x170000), 8, "i32"),
        (0x180001, 3, "u8"),
    ),
)
def test_exact_valid_pointer_extent_and_alignment_are_preserved(
    pointer: Any,
    nbytes: int,
    element_type: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(pointer,))
    owner = _open_owner(runtime)
    capability = owner.allocate("buffer", nbytes, element_type)
    assert capability.base is pointer or (
        type(pointer) is int and _pointer_value(capability.base) == pointer
    )
    assert capability.pointer_snapshot == _pointer_value(pointer)
    assert capability.nbytes == nbytes
    assert capability.element_type == element_type
    _free_success(owner, runtime, capability)
    owner.close()


def test_same_owner_live_role_rejects_before_second_malloc() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x190000, 0x1A0000))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "f64")
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "f64")
    _assert_error(caught.value, "role")
    assert runtime.malloc_calls == [8]
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize("shift", (0, 8, 56))
def test_local_shifted_or_contained_range_overlap_is_rejected_atomically(
    shift: int,
) -> None:
    base = 0x1B0000
    runtime = FakeAllocationRuntime(pointers=(base, base + shift))
    owner = _open_owner(runtime)
    first = owner.allocate("left", 64, "u8")
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("right", 16, "u8")
    _assert_error(caught.value, "overlap")
    assert _pointer_value(caught.value.orphaned_pointer) == base + shift
    assert owner.generation == 1
    with pytest.raises(HipAllocationLineageError) as success_error:
        owner.acknowledge_orphan_free_success(caught.value.orphan_cleanup_lease)
    _assert_error(success_error.value, "conflict")
    _quarantine_orphan(owner, caught.value)
    with pytest.raises(HipAllocationLineageError):
        owner.validate(first)
    with pytest.raises(HipAllocationLineageError):
        borrow_hip_allocations_v1((first,), object())
    with pytest.raises(HipAllocationLineageError):
        owner.begin_free(first)
    owner.quarantine_poisoned_allocation(first)
    assert runtime.free_calls == []
    owner.close()


def test_cross_owner_shifted_overlap_shares_injected_runtime_domain() -> None:
    base = 0x1C0000
    runtime = FakeAllocationRuntime(pointers=(base, base + 8))
    first_owner = _open_owner(runtime, owner_role="first")
    second_owner = _open_owner(runtime, owner_role="second")
    first = first_owner.allocate("left", 64, "u8")
    with pytest.raises(HipAllocationLineageError) as caught:
        second_owner.allocate("right", 8, "u8")
    _assert_error(caught.value, "overlap")
    _quarantine_orphan(second_owner, caught.value)
    with pytest.raises(HipAllocationLineageError):
        first_owner.validate(first)
    first_owner.quarantine_poisoned_allocation(first)
    assert runtime.free_calls == []
    first_owner.close()
    second_owner.close()


def test_overlap_during_borrow_requires_release_then_poison_quarantine() -> None:
    base = 0x1C80000
    runtime = FakeAllocationRuntime(pointers=(base, base))
    owner = _open_owner(runtime, owner_role="owner")
    attacker = _open_owner(runtime, owner_role="attacker")
    capability = owner.allocate("state", 8, "u8")
    borrow = borrow_hip_allocations_v1((capability,), object())
    with pytest.raises(HipAllocationLineageError) as caught:
        attacker.allocate("alias", 8, "u8")
    _quarantine_orphan(attacker, caught.value)
    with pytest.raises(HipAllocationLineageError):
        owner.validate(capability)
    with pytest.raises(HipAllocationLineageError):
        owner.begin_free(capability)
    release_hip_allocation_borrow_v1(borrow)
    owner.quarantine_poisoned_allocation(capability)
    assert runtime.free_calls == []
    owner.close()
    attacker.close()


def test_overlap_during_free_pending_is_resolved_by_existing_free_lease_quarantine() -> (
    None
):
    base = 0x1C90000
    runtime = FakeAllocationRuntime(pointers=(base, base))
    owner = _open_owner(runtime, owner_role="owner")
    attacker = _open_owner(runtime, owner_role="attacker")
    capability = owner.allocate("state", 8, "u8")
    free_lease = owner.begin_free(capability)
    with pytest.raises(HipAllocationLineageError) as caught:
        attacker.allocate("alias", 8, "u8")
    _quarantine_orphan(attacker, caught.value)
    with pytest.raises(HipAllocationLineageError):
        owner.validate(capability)
    owner.quarantine_free_uncertain(free_lease)
    assert runtime.free_calls == []
    owner.close()
    attacker.close()


def test_distinct_injected_runtime_objects_have_private_domains() -> None:
    first_runtime = FakeAllocationRuntime(pointers=(0x1D0000,))
    second_runtime = FakeAllocationRuntime(pointers=(0x1D0000,))
    first_owner = _open_owner(first_runtime, owner_role="first")
    second_owner = _open_owner(second_runtime, owner_role="second")
    first = first_owner.allocate("state", 32, "u8")
    second = second_owner.allocate("state", 32, "u8")
    assert first.runtime_domain_id != second.runtime_domain_id
    _free_success(first_owner, first_runtime, first)
    _free_success(second_owner, second_runtime, second)
    first_owner.close()
    second_owner.close()


def test_loader_issued_native_wrappers_share_one_conservative_process_domain(
    tmp_path: Path,
) -> None:
    first_library = _compile_sealed_native_runtime_library(
        tmp_path,
        stem="lineage_native_first",
    )
    second_library = _compile_sealed_native_runtime_library(
        tmp_path,
        stem="lineage_native_second",
    )
    first_loaded = load_hip_native_runtime(first_library)
    second_loaded = load_hip_native_runtime(second_library)
    first_runtime = _BoundHipContextRuntime(first_loaded)
    second_runtime = _BoundHipContextRuntime(second_loaded)
    first_runtime.set_device(0)
    second_runtime.set_device(0)
    first_owner = lineage.open_hip_allocation_owner_v1(
        first_runtime,
        0,
        "native_first",
    )
    second_owner = lineage.open_hip_allocation_owner_v1(
        second_runtime,
        0,
        "native_second",
    )
    first = first_owner.allocate("state", 1, "u8")
    with pytest.raises(HipAllocationLineageError) as caught:
        second_owner.allocate("state", 1, "u8")
    _assert_error(caught.value, "overlap")
    assert first.runtime_domain_id == second_owner.runtime_domain_id
    _quarantine_orphan(second_owner, caught.value)
    with pytest.raises(HipAllocationLineageError):
        first_owner.validate(first)
    first_owner.quarantine_poisoned_allocation(first)
    first_owner.close()
    second_owner.close()


def test_same_injected_runtime_address_isolated_by_device_ordinal() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x1E0000, 0x1E0000))
    device_zero = _open_owner(runtime, device_ordinal=0, owner_role="device0")
    runtime.device_ordinal = 1
    device_one = _open_owner(runtime, device_ordinal=1, owner_role="device1")
    runtime.device_ordinal = 0
    first = device_zero.allocate("state", 16, "u8")
    runtime.device_ordinal = 1
    second = device_one.allocate("state", 16, "u8")
    assert first.runtime_domain is second.runtime_domain
    assert first.device_ordinal == 0
    assert second.device_ordinal == 1
    runtime.device_ordinal = 0
    _free_success(device_zero, runtime, first)
    runtime.device_ordinal = 1
    _free_success(device_one, runtime, second)
    runtime.device_ordinal = 0
    device_zero.close()
    runtime.device_ordinal = 1
    device_one.close()


def test_successful_free_allows_pointer_reuse_only_at_higher_generation() -> None:
    base = 0x1F0000
    runtime = FakeAllocationRuntime(pointers=(base, base))
    first_owner = _open_owner(runtime, owner_role="first")
    first = first_owner.allocate("state", 16, "u8")
    assert first.generation == 1
    _free_success(first_owner, runtime, first)
    first_owner.close()
    with pytest.raises(HipAllocationLineageError):
        validate_hip_allocation_capability_v1(first)

    second_owner = _open_owner(runtime, owner_role="second")
    second = second_owner.allocate("state", 16, "u8")
    assert second.pointer_snapshot == first.pointer_snapshot
    assert second.generation == first.generation + 1
    _free_success(second_owner, runtime, second)
    second_owner.close()


def test_multi_owner_group_borrow_is_atomic_exclusive_and_idempotently_released() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x2100000, 0x2200000, 0x2300000))
    first_owner = _open_owner(runtime, owner_role="first")
    second_owner = _open_owner(runtime, owner_role="second")
    first = first_owner.allocate("first", 8, "f64")
    second = second_owner.allocate("second", 8, "f64")
    third = second_owner.allocate("third", 8, "f64")
    borrower = object()
    lease = borrow_hip_allocations_v1((first, second), borrower)
    _assert_foundation(lease)
    assert lease.capabilities == (first, second)
    assert validate_hip_allocation_borrow_v1(lease) is lease

    with pytest.raises(HipAllocationLineageError) as caught:
        borrow_hip_allocations_v1((third, first), object())
    _assert_error(caught.value, "busy")
    rollback_probe = borrow_hip_allocations_v1((third,), object())
    release_hip_allocation_borrow_v1(rollback_probe)

    for owner, capability in ((first_owner, first), (second_owner, second)):
        with pytest.raises(HipAllocationLineageError):
            owner.begin_free(capability)
    release_hip_allocation_borrow_v1(lease)
    release_hip_allocation_borrow_v1(lease)
    with pytest.raises(HipAllocationLineageError) as caught:
        validate_hip_allocation_borrow_v1(lease)
    _assert_error(caught.value, "released")

    _free_success(first_owner, runtime, first)
    _free_success(second_owner, runtime, second)
    _free_success(second_owner, runtime, third)
    first_owner.close()
    second_owner.close()


@pytest.mark.parametrize(
    ("capabilities", "borrower", "fragment"),
    (
        ((), object(), "capabilities"),
        ([], object(), "capabilities"),
        ((object(),), object(), "capability"),
        (None, object(), "capabilities"),
        ("placeholder", None, "borrower"),
    ),
)
def test_borrow_group_requires_exact_nonempty_tuple_and_borrower(
    capabilities: Any,
    borrower: Any,
    fragment: str,
) -> None:
    if capabilities == "placeholder":
        runtime = FakeAllocationRuntime(pointers=(0x2400000,))
        owner = _open_owner(runtime)
        capability = owner.allocate("state", 8, "u8")
        capabilities = (capability,)
        try:
            with pytest.raises(HipAllocationLineageError) as caught:
                borrow_hip_allocations_v1(capabilities, borrower)
            _assert_error(caught.value, fragment)
        finally:
            _free_success(owner, runtime, capability)
            owner.close()
        return
    with pytest.raises(HipAllocationLineageError) as caught:
        borrow_hip_allocations_v1(capabilities, borrower)
    _assert_error(caught.value, fragment)


def test_borrow_rejects_duplicate_domain_and_device_mismatch_without_marks() -> None:
    first_runtime = FakeAllocationRuntime(pointers=(0x2500000,))
    device_runtime = FakeAllocationRuntime(
        pointers=(0x2600000,),
        device_ordinal=1,
    )
    second_runtime = FakeAllocationRuntime(pointers=(0x2700000,))
    first_owner = _open_owner(first_runtime, device_ordinal=0, owner_role="first")
    other_device = _open_owner(
        device_runtime,
        device_ordinal=1,
        owner_role="other_device",
    )
    other_domain = _open_owner(second_runtime, owner_role="other_domain")
    first = first_owner.allocate("first", 8, "u8")
    device_capability = other_device.allocate("device", 8, "u8")
    domain_capability = other_domain.allocate("domain", 8, "u8")
    for group, fragment in (
        ((first, first), "duplicate"),
        ((first, device_capability), "domain"),
        ((first, domain_capability), "domain"),
    ):
        with pytest.raises(HipAllocationLineageError) as caught:
            borrow_hip_allocations_v1(group, object())
        _assert_error(caught.value, fragment)
    probe = borrow_hip_allocations_v1((first,), object())
    release_hip_allocation_borrow_v1(probe)
    _free_success(first_owner, first_runtime, first)
    _free_success(other_device, device_runtime, device_capability)
    _free_success(other_domain, second_runtime, domain_capability)
    first_owner.close()
    other_device.close()
    other_domain.close()


def test_concurrent_exclusive_borrow_has_exactly_one_winner() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x2800000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    barrier = threading.Barrier(2)

    def compete() -> tuple[str, Any]:
        barrier.wait(timeout=3.0)
        try:
            return "won", borrow_hip_allocations_v1((capability,), object())
        except BaseException as exc:
            return "lost", exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: compete(), range(2)))
    winners = [value for status, value in results if status == "won"]
    losers = [value for status, value in results if status == "lost"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0], HipAllocationLineageError)
    release_hip_allocation_borrow_v1(winners[0])
    _free_success(owner, runtime, capability)
    owner.close()


def test_lineage_never_calls_free_and_success_requires_external_owner_call() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x2900000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    free_lease = owner.begin_free(capability)
    _assert_foundation(free_lease)
    assert runtime.free_calls == []
    with pytest.raises(HipAllocationLineageError):
        owner.begin_free(capability)
    assert runtime.free_calls == []
    runtime.free(capability.base)
    owner.acknowledge_free_success(free_lease)
    assert runtime.free_calls == [capability.pointer_snapshot]
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.acknowledge_free_success(free_lease)
    _assert_error(caught.value, "consumed")
    owner.close()


def test_failed_external_free_keeps_exact_pending_lease_retryable() -> None:
    runtime = FakeAllocationRuntime(
        pointers=(0x2A00000,),
        free_fail_count=1,
    )
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    free_lease = owner.begin_free(capability)
    with pytest.raises(RuntimeError):
        runtime.free(capability.base)
    assert owner.validate(capability) is capability
    with pytest.raises(HipAllocationLineageError):
        owner.close()
    runtime.free(capability.base)
    owner.acknowledge_free_success(free_lease)
    assert runtime.free_calls == [
        capability.pointer_snapshot,
        capability.pointer_snapshot,
    ]
    owner.close()


def test_uncertain_free_quarantine_blocks_validation_refree_and_pointer_reuse() -> None:
    base = 0x2B00000
    runtime = FakeAllocationRuntime(
        pointers=(base, base),
        free_exception=True,
    )
    owner = _open_owner(runtime, owner_role="quarantine_owner")
    capability = owner.allocate("state", 8, "u8")
    free_lease = owner.begin_free(capability)
    with pytest.raises(RuntimeError):
        runtime.free(capability.base)
    runtime.device_ordinal = 1
    owner.quarantine_free_uncertain(free_lease)
    with pytest.raises(HipAllocationLineageError):
        owner.validate(capability)
    with pytest.raises(HipAllocationLineageError):
        owner.begin_free(capability)
    with pytest.raises(HipAllocationLineageError):
        owner.quarantine_free_uncertain(free_lease)
    owner.close()

    runtime.device_ordinal = 0
    runtime.free_exception = False
    replacement_owner = _open_owner(runtime, owner_role="replacement")
    with pytest.raises(HipAllocationLineageError) as caught:
        replacement_owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "overlap")
    assert _pointer_value(caught.value.orphaned_pointer) == base
    _quarantine_orphan(replacement_owner, caught.value)
    replacement_owner.close()


def test_foreign_owner_cannot_begin_or_finish_free() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x2C00000,))
    owner = _open_owner(runtime, owner_role="owner")
    foreign = _open_owner(runtime, owner_role="foreign")
    capability = owner.allocate("state", 8, "u8")
    with pytest.raises(HipAllocationLineageError) as caught:
        foreign.begin_free(capability)
    _assert_error(caught.value, "foreign")
    free_lease = owner.begin_free(capability)
    with pytest.raises(HipAllocationLineageError) as caught:
        foreign.acknowledge_free_success(free_lease)
    _assert_error(caught.value, "foreign")
    runtime.free(capability.base)
    owner.acknowledge_free_success(free_lease)
    owner.close()
    foreign.close()


def test_owner_close_rejects_active_borrowed_and_free_pending_then_is_idempotent() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x2D00000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    with pytest.raises(HipAllocationLineageError):
        owner.close()
    borrow = borrow_hip_allocations_v1((capability,), object())
    with pytest.raises(HipAllocationLineageError):
        owner.close()
    release_hip_allocation_borrow_v1(borrow)
    free_lease = owner.begin_free(capability)
    with pytest.raises(HipAllocationLineageError):
        owner.close()
    runtime.free(capability.base)
    owner.acknowledge_free_success(free_lease)
    owner.close()
    owner.close()
    assert owner.closed
    with pytest.raises(HipAllocationLineageError):
        owner.allocate("other", 8, "u8")


def test_concurrent_begin_free_has_one_exact_winner() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x2E00000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    barrier = threading.Barrier(2)

    def compete() -> tuple[str, Any]:
        barrier.wait(timeout=3.0)
        try:
            return "won", owner.begin_free(capability)
        except BaseException as exc:
            return "lost", exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: compete(), range(2)))
    winners = [value for status, value in results if status == "won"]
    losers = [value for status, value in results if status == "lost"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0], HipAllocationLineageError)
    runtime.free(capability.base)
    owner.acknowledge_free_success(winners[0])
    owner.close()


def test_copied_capability_borrow_and_free_leases_are_foreign_even_with_exact_fields() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x2F00000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    forged_capability = _copy_slots(capability)
    with pytest.raises(HipAllocationLineageError):
        validate_hip_allocation_capability_v1(forged_capability)
    with pytest.raises(HipAllocationLineageError):
        borrow_hip_allocations_v1((forged_capability,), object())

    borrow = borrow_hip_allocations_v1((capability,), object())
    forged_borrow = _copy_slots(borrow)
    with pytest.raises(HipAllocationLineageError):
        validate_hip_allocation_borrow_v1(forged_borrow)
    with pytest.raises(HipAllocationLineageError):
        release_hip_allocation_borrow_v1(forged_borrow)
    release_hip_allocation_borrow_v1(borrow)

    free_lease = owner.begin_free(capability)
    forged_free = _copy_slots(free_lease)
    with pytest.raises(HipAllocationLineageError):
        owner.acknowledge_free_success(forged_free)
    runtime.free(capability.base)
    owner.acknowledge_free_success(free_lease)
    owner.close()


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("allocation_id", "forged"),
        ("role", "forged"),
        ("pointer_snapshot", 0xDEAD0000),
        ("nbytes", 16),
        ("element_type", "i32"),
        ("generation", 999),
        ("owner_identity", "forged"),
        ("runtime_owner", None),
        ("runtime_domain", None),
        ("device_ordinal", 1),
        ("evidence_scope", "promoting"),
        ("promotion_eligible", True),
    ),
)
def test_every_capability_snapshot_field_tamper_is_rejected(
    field: str,
    mutated: Any,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3000000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "f64")
    original = getattr(capability, field)
    object.__setattr__(capability, field, mutated)
    try:
        with pytest.raises(HipAllocationLineageError):
            owner.validate(capability)
        with pytest.raises(HipAllocationLineageError):
            borrow_hip_allocations_v1((capability,), object())
    finally:
        object.__setattr__(capability, field, original)
    _free_success(owner, runtime, capability)
    owner.close()


def test_mutable_c_void_p_base_value_drift_is_rejected() -> None:
    base = ctypes.c_void_p(0x3100000)
    runtime = FakeAllocationRuntime(pointers=(base,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "f64")
    base.value += 8
    try:
        with pytest.raises(HipAllocationLineageError):
            owner.validate(capability)
    finally:
        base.value -= 8
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("lease_id", "forged"),
        ("capabilities", ()),
        ("borrower", None),
        ("runtime_domain", None),
        ("device_ordinal", 1),
        ("evidence_scope", "promoting"),
        ("promotion_eligible", True),
    ),
)
def test_every_borrow_lease_field_tamper_is_rejected(
    field: str,
    mutated: Any,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3200000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = borrow_hip_allocations_v1((capability,), object())
    original = getattr(lease, field)
    object.__setattr__(lease, field, mutated)
    try:
        with pytest.raises(HipAllocationLineageError):
            validate_hip_allocation_borrow_v1(lease)
        with pytest.raises(HipAllocationLineageError):
            release_hip_allocation_borrow_v1(lease)
    finally:
        object.__setattr__(lease, field, original)
    release_hip_allocation_borrow_v1(lease)
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("lease_id", "forged"),
        ("capability", None),
        ("owner_identity", "forged"),
        ("evidence_scope", "promoting"),
        ("promotion_eligible", True),
    ),
)
def test_every_free_lease_field_tamper_is_rejected(
    field: str,
    mutated: Any,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3300000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = owner.begin_free(capability)
    original = getattr(lease, field)
    object.__setattr__(lease, field, mutated)
    try:
        with pytest.raises(HipAllocationLineageError):
            owner.acknowledge_free_success(lease)
    finally:
        object.__setattr__(lease, field, original)
    runtime.free(capability.base)
    owner.acknowledge_free_success(lease)
    owner.close()


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("_owner_id", 999),
        ("_lock", None),
    ),
)
def test_owner_runtime_device_and_private_authority_drift_is_rejected(
    field: str,
    mutated: Any,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3400000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    original = getattr(owner, field)
    object.__setattr__(owner, field, mutated)
    try:
        with pytest.raises(HipAllocationLineageError):
            owner.validate(capability)
        with pytest.raises(HipAllocationLineageError):
            owner.begin_free(capability)
    finally:
        object.__setattr__(owner, field, original)
    _free_success(owner, runtime, capability)
    owner.close()


def test_runtime_and_registry_device_drift_are_rejected_and_recoverable() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3500000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    runtime.device_ordinal = 1
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.validate(capability)
    _assert_error(caught.value, "device")
    runtime.device_ordinal = 0

    owner_row = lineage._OWNERS[id(owner)]
    original_runtime = owner_row.runtime
    owner_row.runtime = FakeAllocationRuntime()
    try:
        with pytest.raises(HipAllocationLineageError) as caught:
            owner.validate(capability)
        _assert_error(caught.value, "runtime")
    finally:
        owner_row.runtime = original_runtime

    owner_row.device_ordinal = 1
    try:
        with pytest.raises(HipAllocationLineageError) as caught:
            owner.validate(capability)
        _assert_error(caught.value, "device")
    finally:
        owner_row.device_ordinal = 0
    _free_success(owner, runtime, capability)
    owner.close()


def test_same_thread_malloc_reentry_is_rejected_without_poisoning_outer_publish() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x3600000,))
    owner = _open_owner(runtime)
    callback_errors: list[BaseException] = []

    def reenter() -> None:
        runtime.malloc_callback = None
        try:
            owner.allocate("nested", 8, "u8")
        except BaseException as exc:
            callback_errors.append(exc)

    runtime.malloc_callback = reenter
    capability = owner.allocate("outer", 8, "u8")
    assert len(callback_errors) == 1
    assert isinstance(callback_errors[0], HipAllocationLineageError)
    _assert_error(callback_errors[0], "reentrant")
    assert capability.generation == 1
    _free_success(owner, runtime, capability)
    owner.close()


def test_borrower_user_protocol_methods_are_never_registry_callbacks() -> None:
    class AdversarialBorrower:
        def __init__(self) -> None:
            self.calls = 0

        def __repr__(self) -> str:
            self.calls += 1
            return "adversarial"

        def __hash__(self) -> int:
            self.calls += 1
            return 1

        def __eq__(self, _other: object) -> bool:
            self.calls += 1
            return False

    runtime = FakeAllocationRuntime(pointers=(0x3700000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    borrower = AdversarialBorrower()
    lease = borrow_hip_allocations_v1((capability,), borrower)
    assert borrower.calls == 0
    assert lease.borrower is borrower
    validate_hip_allocation_borrow_v1(lease)
    release_hip_allocation_borrow_v1(lease)
    assert borrower.calls == 0
    _free_success(owner, runtime, capability)
    owner.close()


def test_concurrent_same_role_allocation_has_one_publish_and_one_orphan() -> None:
    first_pointer = 0x3800000
    second_pointer = 0x3900000
    barrier = threading.Barrier(2)
    runtime = FakeAllocationRuntime(
        pointers=(first_pointer, second_pointer),
        malloc_callback=lambda: barrier.wait(timeout=3.0),
    )
    owner = _open_owner(runtime)

    def allocate() -> tuple[str, Any]:
        try:
            return "published", owner.allocate("state", 8, "u8")
        except BaseException as exc:
            return "orphaned", exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: allocate(), range(2)))
    published = [value for status, value in results if status == "published"]
    orphaned = [value for status, value in results if status == "orphaned"]
    assert len(published) == 1
    assert len(orphaned) == 1
    assert isinstance(orphaned[0], HipAllocationLineageError)
    _assert_error(orphaned[0], "role")
    assert orphaned[0].orphaned_pointer is not None
    assert owner.generation == 1
    _orphan_free_success(owner, runtime, orphaned[0])
    _free_success(owner, runtime, published[0])
    owner.close()


def test_close_rejects_while_malloc_is_outside_registry_lock() -> None:
    entered = threading.Event()
    resume = threading.Event()

    def pause_malloc() -> None:
        entered.set()
        assert resume.wait(timeout=3.0)

    runtime = FakeAllocationRuntime(
        pointers=(0x3A00000,),
        malloc_callback=pause_malloc,
    )
    owner = _open_owner(runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner.allocate, "state", 8, "u8")
        assert entered.wait(timeout=3.0)
        with pytest.raises(HipAllocationLineageError) as caught:
            owner.close()
        _assert_error(caught.value, "busy")
        resume.set()
        capability = future.result(timeout=3.0)
    _free_success(owner, runtime, capability)
    owner.close()


def test_capability_publish_memory_error_rolls_back_and_exposes_orphan_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = 0x3B00000
    runtime = FakeAllocationRuntime(pointers=(base, base))
    owner = _open_owner(runtime)
    original_issue = lineage._issue
    allocations_before = len(lineage._ALLOCATIONS)
    high_water_before = dict(lineage._HIGH_WATER)

    def fail_capability_issue(cls: type[object], values: dict[str, object]) -> object:
        if cls is HipAllocationCapabilityV1:
            raise MemoryError("injected capability publication failure")
        return original_issue(cls, values)

    monkeypatch.setattr(lineage, "_issue", fail_capability_issue)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "publish")
    assert _pointer_value(caught.value.orphaned_pointer) == base
    assert type(caught.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    assert len(lineage._ALLOCATIONS) == allocations_before
    assert lineage._HIGH_WATER == high_water_before
    assert owner.generation == 0
    _orphan_free_success(owner, runtime, caught.value)

    monkeypatch.setattr(lineage, "_issue", original_issue)
    capability = owner.allocate("state", 8, "u8")
    assert capability.generation == 1
    _free_success(owner, runtime, capability)
    owner.close()


def test_unknown_end_overflow_orphan_quarantine_blocks_every_higher_shift() -> None:
    maximum = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
    base = maximum - 3
    runtime = FakeAllocationRuntime(pointers=(base, base + 1))
    owner = _open_owner(runtime, owner_role="overflow")
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "overflow")
    _quarantine_orphan(owner, caught.value)
    owner.close()

    shifted_owner = _open_owner(runtime, owner_role="shifted")
    with pytest.raises(HipAllocationLineageError) as shifted:
        shifted_owner.allocate("state", 1, "u8")
    _assert_error(shifted.value, "overlap")
    _quarantine_orphan(shifted_owner, shifted.value)
    shifted_owner.close()
    assert runtime.free_calls == []


@pytest.mark.parametrize("cleanup", ("success", "quarantine"))
def test_orphan_stage_memory_error_preserves_cleanup_lease(
    monkeypatch: pytest.MonkeyPatch,
    cleanup: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3B80000,))
    owner = _open_owner(runtime)

    def fail_stage(*_arguments: Any, **_kwargs: Any) -> None:
        raise MemoryError("injected orphan staging failure")

    monkeypatch.setattr(lineage, "_stage_orphan_locked", fail_stage)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "stage")
    assert type(caught.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    if cleanup == "success":
        _orphan_free_success(owner, runtime, caught.value)
    else:
        _quarantine_orphan(owner, caught.value)
        assert runtime.free_calls == []
    owner.close()


@pytest.mark.parametrize("cleanup", ("success", "quarantine"))
def test_force_orphan_failure_uses_emergency_cleanup_path(
    monkeypatch: pytest.MonkeyPatch,
    cleanup: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3B90000,))
    owner = _open_owner(runtime)

    def fail(*_arguments: Any, **_kwargs: Any) -> None:
        raise MemoryError("injected orphan fallback failure")

    monkeypatch.setattr(lineage, "_stage_orphan_locked", fail)
    monkeypatch.setattr(lineage, "_force_orphan_pending_locked", fail)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    assert type(caught.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    if cleanup == "success":
        _orphan_free_success(owner, runtime, caught.value)
    else:
        _quarantine_orphan(owner, caught.value)
        assert runtime.free_calls == []
    owner.close()


def test_orphan_free_exception_can_quarantine_during_device_drift_and_block_reuse() -> (
    None
):
    base = 0x3C00004
    runtime = FakeAllocationRuntime(
        pointers=(base, base),
        free_exception=True,
    )
    orphan_owner = _open_owner(runtime, owner_role="orphan")
    with pytest.raises(HipAllocationLineageError) as caught:
        orphan_owner.allocate("state", 8, "f64")
    with pytest.raises(RuntimeError):
        runtime.free(caught.value.orphaned_pointer)
    runtime.device_ordinal = 1
    _quarantine_orphan(orphan_owner, caught.value)
    orphan_owner.close()

    runtime.device_ordinal = 0
    runtime.free_exception = False
    replacement = _open_owner(runtime, owner_role="replacement")
    with pytest.raises(HipAllocationLineageError) as reuse_error:
        replacement.allocate("state", 1, "u8")
    _assert_error(reuse_error.value, "overlap")
    _quarantine_orphan(replacement, reuse_error.value)
    replacement.close()


def test_runtime_device_callback_reentrant_borrow_loses_to_outer_free() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3D00000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    callback_leases: list[HipAllocationBorrowLeaseV1] = []
    callback_errors: list[BaseException] = []

    def borrow_reentrantly() -> None:
        runtime.device_callback = None
        try:
            callback_leases.append(borrow_hip_allocations_v1((capability,), object()))
        except BaseException as exc:
            callback_errors.append(exc)

    runtime.device_callback = borrow_reentrantly
    free_lease: HipAllocationFreeLeaseV1 | None = None
    try:
        free_lease = owner.begin_free(capability)
        assert callback_leases == []
        assert len(callback_errors) == 1
        assert isinstance(callback_errors[0], HipAllocationLineageError)
        _assert_error(callback_errors[0], "busy")
    finally:
        runtime.device_callback = None
        if free_lease is not None:
            runtime.free(capability.base)
            owner.acknowledge_free_success(free_lease)
        owner.close()


def test_runtime_device_callback_reentrant_free_loses_to_outer_borrow() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E00000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    callback_leases: list[HipAllocationFreeLeaseV1] = []
    callback_errors: list[BaseException] = []

    def begin_free_reentrantly() -> None:
        runtime.device_callback = None
        try:
            callback_leases.append(owner.begin_free(capability))
        except BaseException as exc:
            callback_errors.append(exc)

    runtime.device_callback = begin_free_reentrantly
    borrow_lease: HipAllocationBorrowLeaseV1 | None = None
    try:
        borrow_lease = borrow_hip_allocations_v1((capability,), object())
        assert callback_leases == []
        assert len(callback_errors) == 1
        assert isinstance(callback_errors[0], HipAllocationLineageError)
        _assert_error(callback_errors[0], "busy")
    finally:
        runtime.device_callback = None
        if borrow_lease is not None:
            release_hip_allocation_borrow_v1(borrow_lease)
        _free_success(owner, runtime, capability)
        owner.close()


@pytest.mark.parametrize("exception_type", (KeyboardInterrupt, SystemExit))
def test_orphan_reservation_base_exception_leaves_no_transaction_residue(
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E10000,))
    owner = _open_owner(runtime)
    original_issue = lineage._issue
    leases_before = lineage._NEXT_LEASE_ID
    orphans_before = dict(lineage._ORPHANS)

    def interrupt_orphan_issue(cls: type[object], values: dict[str, object]) -> object:
        if cls is HipAllocationOrphanLeaseV1:
            raise exception_type("injected orphan reservation interruption")
        return original_issue(cls, values)

    monkeypatch.setattr(lineage, "_issue", interrupt_orphan_issue)
    with pytest.raises(exception_type):
        owner.allocate("state", 8, "u8")

    assert lineage._NEXT_LEASE_ID == leases_before
    assert lineage._ORPHANS == orphans_before
    assert lineage._OWNERS[id(owner)].allocating_threads == set()
    assert runtime.malloc_calls == []
    assert owner.generation == 0

    monkeypatch.setattr(lineage, "_issue", original_issue)
    capability = owner.allocate("state", 8, "u8")
    assert capability.generation == 1
    _free_success(owner, runtime, capability)
    owner.close()


def test_failed_publication_cannot_rewind_concurrent_success_ids_or_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered_malloc = threading.Event()
    successful_publication = threading.Event()
    callback_lock = threading.Lock()
    first_malloc = True

    def pause_only_first_malloc() -> None:
        nonlocal first_malloc
        with callback_lock:
            should_pause = first_malloc
            first_malloc = False
        if should_pause:
            entered_malloc.set()
            assert successful_publication.wait(timeout=3.0)

    runtime = FakeAllocationRuntime(
        pointers=(0x3E20000, 0x3E30000, 0x3E40000),
        malloc_callback=pause_only_first_malloc,
    )
    failing_owner = _open_owner(runtime, owner_role="failing")
    successful_owner = _open_owner(runtime, owner_role="successful")
    original_issue = lineage._issue
    allocation_id_before = lineage._NEXT_ALLOCATION_ID
    failed_once = False

    def fail_one_capability_issue(
        cls: type[object], values: dict[str, object]
    ) -> object:
        nonlocal failed_once
        if (
            cls is HipAllocationCapabilityV1
            and values.get("role") == "will_fail"
            and not failed_once
        ):
            failed_once = True
            raise MemoryError("injected interleaved publication failure")
        return original_issue(cls, values)

    monkeypatch.setattr(lineage, "_issue", fail_one_capability_issue)
    with ThreadPoolExecutor(max_workers=1) as pool:
        failing_future = pool.submit(
            failing_owner.allocate,
            "will_fail",
            8,
            "u8",
        )
        assert entered_malloc.wait(timeout=3.0)
        successful = successful_owner.allocate("successful", 8, "u8")
        successful_publication.set()
        with pytest.raises(HipAllocationLineageError) as caught:
            failing_future.result(timeout=3.0)

    _assert_error(caught.value, "publish")
    assert successful.allocation_id == allocation_id_before
    assert successful.generation == 1
    assert successful_owner.generation == 1
    assert failing_owner.generation == 0
    assert lineage._ALLOCATIONS[id(successful)].capability is successful
    _orphan_free_success(failing_owner, runtime, caught.value)

    retry = failing_owner.allocate("will_fail", 8, "u8")
    assert retry.allocation_id == successful.allocation_id + 1
    assert retry.generation == successful.generation + 1
    assert failing_owner.generation == retry.generation
    assert len({successful.allocation_id, retry.allocation_id}) == 2
    assert lineage._NEXT_ALLOCATION_ID == retry.allocation_id + 1

    _free_success(successful_owner, runtime, successful)
    _free_success(failing_owner, runtime, retry)
    successful_owner.close()
    failing_owner.close()


@pytest.mark.parametrize("operation", ("borrow", "free"))
@pytest.mark.parametrize("failure_stage", ("issue", "snapshot", "registry"))
def test_lease_publication_failure_restores_rows_registry_and_counter(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure_stage: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E50000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]
    allocation_before = (
        allocation.state,
        allocation.borrow_lease,
        allocation.free_lease,
    )
    lease_id_before = lineage._NEXT_LEASE_ID
    lease_type = (
        HipAllocationBorrowLeaseV1
        if operation == "borrow"
        else HipAllocationFreeLeaseV1
    )
    registry_name = "_BORROWS" if operation == "borrow" else "_FREES"
    snapshot_name = "_borrow_snapshot" if operation == "borrow" else "_free_snapshot"
    original_registry = getattr(lineage, registry_name)
    registry_before = dict(original_registry)
    original_issue = lineage._issue
    original_snapshot = getattr(lineage, snapshot_name)

    if failure_stage == "issue":

        def fail_issue(cls: type[object], values: dict[str, object]) -> object:
            if cls is lease_type:
                raise MemoryError("injected lease issue failure")
            return original_issue(cls, values)

        monkeypatch.setattr(lineage, "_issue", fail_issue)
    elif failure_stage == "snapshot":

        def fail_snapshot(*_args: object, **_kwargs: object) -> tuple[object, ...]:
            raise MemoryError("injected lease snapshot failure")

        monkeypatch.setattr(lineage, snapshot_name, fail_snapshot)
    else:
        monkeypatch.setattr(
            lineage,
            registry_name,
            _FailOnceRegistry(registry_before),
        )

    with pytest.raises((MemoryError, HipAllocationLineageError)):
        if operation == "borrow":
            borrow_hip_allocations_v1((capability,), object())
        else:
            owner.begin_free(capability)

    assert lineage._NEXT_LEASE_ID == lease_id_before
    assert dict(getattr(lineage, registry_name)) == registry_before
    assert (
        allocation.state,
        allocation.borrow_lease,
        allocation.free_lease,
    ) == allocation_before

    monkeypatch.setattr(lineage, "_issue", original_issue)
    monkeypatch.setattr(lineage, snapshot_name, original_snapshot)
    monkeypatch.setattr(lineage, registry_name, original_registry)
    if operation == "borrow":
        lease = borrow_hip_allocations_v1((capability,), object())
        release_hip_allocation_borrow_v1(lease)
        _free_success(owner, runtime, capability)
    else:
        _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize("operation", ("borrow", "free"))
@pytest.mark.parametrize("mutation", ("capability", "lease", "row"))
def test_runtime_callback_tamper_aborts_and_restores_lease_reservation(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    mutation: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E60000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]
    pointer_snapshot = capability.pointer_snapshot
    lease_id_before = lineage._NEXT_LEASE_ID
    borrows_before = dict(lineage._BORROWS)
    frees_before = dict(lineage._FREES)
    original_issue = lineage._issue
    issued: dict[str, object] = {}

    def capture_lease(cls: type[object], values: dict[str, object]) -> object:
        artifact = original_issue(cls, values)
        if cls in {HipAllocationBorrowLeaseV1, HipAllocationFreeLeaseV1}:
            issued["lease"] = artifact
        return artifact

    def mutate_during_device_query() -> None:
        runtime.device_callback = None
        if mutation == "capability":
            object.__setattr__(
                capability,
                "pointer_snapshot",
                pointer_snapshot + 8,
            )
        elif mutation == "lease":
            object.__setattr__(issued["lease"], "promotion_eligible", True)
        else:
            # Revert the reservation state while retaining its lease pointer.
            # The commit must detect this split witness and clear the lease.
            allocation.state = "live"

    monkeypatch.setattr(lineage, "_issue", capture_lease)
    runtime.device_callback = mutate_during_device_query
    try:
        with pytest.raises(HipAllocationLineageError):
            if operation == "borrow":
                borrow_hip_allocations_v1((capability,), object())
            else:
                owner.begin_free(capability)
    finally:
        runtime.device_callback = None
        object.__setattr__(capability, "pointer_snapshot", pointer_snapshot)

    # The issued lease ID stays consumed; callback rollback must never reuse it.
    assert lineage._NEXT_LEASE_ID == lease_id_before + 1
    assert lineage._BORROWS == borrows_before
    assert lineage._FREES == frees_before
    assert allocation.state == ("poisoned" if mutation == "capability" else "live")
    assert allocation.borrow_lease is None
    assert allocation.free_lease is None

    monkeypatch.setattr(lineage, "_issue", original_issue)
    if mutation == "capability":
        owner.quarantine_poisoned_allocation(capability)
        assert id(capability) not in lineage._ALLOCATIONS
        owner.close()
        return
    if operation == "borrow":
        lease = borrow_hip_allocations_v1((capability,), object())
        release_hip_allocation_borrow_v1(lease)
    _free_success(owner, runtime, capability)
    owner.close()


def test_active_borrow_validation_detects_device_drift_and_recovers() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E70000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = borrow_hip_allocations_v1((capability,), object())

    runtime.device_ordinal = 1
    with pytest.raises(HipAllocationLineageError) as caught:
        validate_hip_allocation_borrow_v1(lease)
    _assert_error(caught.value, "device")

    runtime.device_ordinal = 0
    assert validate_hip_allocation_borrow_v1(lease) is lease
    release_hip_allocation_borrow_v1(lease)
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize("exception_type", (KeyboardInterrupt, SystemExit))
def test_malloc_base_exception_poisons_domain_and_quarantines_null_orphan(
    exception_type: type[BaseException],
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3E80000,))

    def interrupt_malloc() -> None:
        raise exception_type("injected outcome-uncertain malloc interruption")

    runtime.malloc_callback = interrupt_malloc
    owner = _open_owner(runtime)
    domain_key = (owner.runtime_domain_id, 0)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "uncertain")
    assert caught.value.orphaned_pointer is None
    assert type(caught.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    assert domain_key in lineage._POISONED_DOMAINS
    assert lineage._OWNERS[id(owner)].allocating_threads == set()
    assert runtime.free_calls == []

    runtime.malloc_callback = None
    _quarantine_orphan(owner, caught.value)
    with pytest.raises(HipAllocationLineageError) as poisoned:
        owner.allocate("retry", 8, "u8")
    _assert_error(poisoned.value, "poison")
    owner.close()
    assert not any(row.owner is owner for row in lineage._ORPHANS.values())


def test_free_lease_freezes_external_pointer_target_against_mutable_base_drift() -> (
    None
):
    pointer = 0x3E90000
    mutable_base = ctypes.c_void_p(pointer)
    runtime = FakeAllocationRuntime(pointers=(mutable_base,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = owner.begin_free(capability)

    assert capability.base is mutable_base
    assert lease.pointer_snapshot == pointer
    assert lease.runtime_domain is capability.runtime_domain
    assert lease.runtime_domain_id == capability.runtime_domain_id
    assert lease.device_ordinal == capability.device_ordinal

    mutable_base.value = pointer + 0x1000
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    assert runtime.free_calls == [pointer]
    assert mutable_base.value != lease.pointer_snapshot

    owner.acknowledge_free_success(lease)
    owner.close()


def test_orphan_lease_freezes_pointer_target_against_mutable_base_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = 0x3E98000
    mutable_base = ctypes.c_void_p(pointer)
    runtime = FakeAllocationRuntime(pointers=(mutable_base,))
    owner = _open_owner(runtime)
    original_issue = lineage._issue

    def fail_capability_issue(cls: type[object], values: dict[str, object]) -> object:
        if cls is HipAllocationCapabilityV1:
            raise MemoryError("injected publication failure after malloc")
        return original_issue(cls, values)

    monkeypatch.setattr(lineage, "_issue", fail_capability_issue)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    assert lease.base is mutable_base
    assert lease.pointer_snapshot == pointer

    mutable_base.value = pointer + 0x1000
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    assert runtime.free_calls == [pointer]
    assert mutable_base.value != lease.pointer_snapshot
    owner.acknowledge_orphan_free_success(lease)
    owner.close()


def test_orphan_without_exact_pointer_rejects_success_ack_and_allows_quarantine() -> (
    None
):
    runtime = FakeAllocationRuntime()

    def interrupt_malloc() -> None:
        raise KeyboardInterrupt("injected pointer-unknown allocator interruption")

    runtime.malloc_callback = interrupt_malloc
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    assert lease.pointer_snapshot is None
    orphan_row = lineage._ORPHANS[id(lease)]

    runtime.malloc_callback = None
    with pytest.raises(HipAllocationLineageError) as rejected:
        owner.acknowledge_orphan_free_success(lease)
    _assert_error(rejected.value, "orphan")
    assert lineage._ORPHANS[id(lease)] is orphan_row
    assert runtime.free_calls == []

    owner.quarantine_orphan_free_uncertain(lease)
    assert id(lease) not in lineage._ORPHANS
    owner.close()


def test_owner_close_tombstone_failure_restores_public_and_registry_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime()
    owner = _open_owner(runtime)
    owner_row = lineage._OWNERS[id(owner)]
    original_registry = lineage._CLOSED_OWNERS
    registry_before = dict(original_registry)
    failing_registry = _FailOnceWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CLOSED_OWNERS", failing_registry)

    with pytest.raises(MemoryError):
        owner.close()

    assert owner.closed is False
    assert owner._closed_snapshot is False
    assert owner_row.closed is False
    assert lineage._OWNERS[id(owner)] is owner_row
    assert dict(failing_registry) == registry_before

    monkeypatch.setattr(lineage, "_CLOSED_OWNERS", original_registry)
    owner.close()
    assert owner.closed is True
    assert id(owner) not in lineage._OWNERS
    assert original_registry.get(owner) is not None


def test_release_borrow_tombstone_failure_preserves_borrow_authority_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3EA0000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = borrow_hip_allocations_v1((capability,), object())
    allocation = lineage._ALLOCATIONS[id(capability)]
    borrow_row = lineage._BORROWS[id(lease)]
    original_registry = lineage._RELEASED_BORROWS
    registry_before = dict(original_registry)
    failing_registry = _FailOnceWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_RELEASED_BORROWS", failing_registry)

    with pytest.raises(MemoryError):
        release_hip_allocation_borrow_v1(lease)

    assert allocation.state == "borrowed"
    assert allocation.borrow_lease is lease
    assert lineage._BORROWS[id(lease)] is borrow_row
    assert borrow_row.released is False
    assert dict(failing_registry) == registry_before
    assert validate_hip_allocation_borrow_v1(lease) is lease

    monkeypatch.setattr(lineage, "_RELEASED_BORROWS", original_registry)
    release_hip_allocation_borrow_v1(lease)
    assert allocation.state == "live"
    assert allocation.borrow_lease is None
    assert id(lease) not in lineage._BORROWS
    assert original_registry.get(lease) is not None
    _free_success(owner, runtime, capability)
    owner.close()


@pytest.mark.parametrize("terminal", ("acknowledge", "quarantine"))
def test_free_terminal_tombstone_failure_preserves_allocation_and_lease_for_retry(
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    pointer = 0x3EB0000
    runtime = FakeAllocationRuntime(pointers=(pointer,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = owner.begin_free(capability)
    allocation = lineage._ALLOCATIONS[id(capability)]
    free_row = lineage._FREES[id(lease)]
    original_registry = lineage._CONSUMED_FREES
    registry_before = dict(original_registry)
    failing_registry = _FailOnceWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CONSUMED_FREES", failing_registry)
    if terminal == "acknowledge":
        runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
        finish = owner.acknowledge_free_success
    else:
        finish = owner.quarantine_free_uncertain

    with pytest.raises(MemoryError):
        finish(lease)

    assert lineage._ALLOCATIONS[id(capability)] is allocation
    assert allocation.state == "free_pending"
    assert allocation.free_lease is lease
    assert lineage._FREES[id(lease)] is free_row
    assert free_row.state == "pending"
    assert dict(failing_registry) == registry_before
    assert runtime.free_calls == ([pointer] if terminal == "acknowledge" else [])

    monkeypatch.setattr(lineage, "_CONSUMED_FREES", original_registry)
    finish(lease)
    assert id(capability) not in lineage._ALLOCATIONS
    assert id(lease) not in lineage._FREES
    assert original_registry[lease][1] == (
        "succeeded" if terminal == "acknowledge" else "quarantined"
    )
    assert runtime.free_calls == ([pointer] if terminal == "acknowledge" else [])
    owner.close()


@pytest.mark.parametrize("terminal", ("acknowledge", "quarantine"))
def test_orphan_terminal_tombstone_failure_preserves_cleanup_authority_for_retry(
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    pointer = 0x3EC0004
    runtime = FakeAllocationRuntime(pointers=(pointer,))
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "f64")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    orphan_row = lineage._ORPHANS[id(lease)]
    original_registry = lineage._CONSUMED_ORPHANS
    registry_before = dict(original_registry)
    failing_registry = _FailOnceWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CONSUMED_ORPHANS", failing_registry)
    if terminal == "acknowledge":
        runtime.free(caught.value.orphaned_pointer)
        finish = owner.acknowledge_orphan_free_success
    else:
        finish = owner.quarantine_orphan_free_uncertain

    with pytest.raises(MemoryError):
        finish(lease)

    assert lineage._ORPHANS[id(lease)] is orphan_row
    assert orphan_row.state == "pending"
    assert orphan_row.lease is lease
    assert dict(failing_registry) == registry_before
    assert runtime.free_calls == ([pointer] if terminal == "acknowledge" else [])

    monkeypatch.setattr(lineage, "_CONSUMED_ORPHANS", original_registry)
    finish(lease)
    assert id(lease) not in lineage._ORPHANS
    assert original_registry[lease][1] == (
        "succeeded" if terminal == "acknowledge" else "quarantined"
    )
    assert runtime.free_calls == ([pointer] if terminal == "acknowledge" else [])
    owner.close()


def test_publication_rollback_serializes_a_concurrent_successful_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3ED0000, 0x3EE0000))
    failing_owner = _open_owner(runtime, owner_role="rollback")
    successful_owner = _open_owner(runtime, owner_role="publisher")
    original_issue = lineage._issue
    original_restore = lineage._restore_orphan_pending_locked
    rollback_entered = threading.Event()
    allow_rollback = threading.Event()
    rollback_completed = threading.Event()
    successful_attempted = threading.Event()
    successful_committed = threading.Event()
    failure_injected = False
    rollback_paused = False

    def fail_first_publication(cls: type[object], values: dict[str, object]) -> object:
        nonlocal failure_injected
        if (
            cls is HipAllocationCapabilityV1
            and values.get("role") == "will_fail"
            and not failure_injected
        ):
            failure_injected = True
            raise MemoryError("injected serialized publication failure")
        return original_issue(cls, values)

    def pause_publication_rollback(lease: HipAllocationOrphanLeaseV1) -> None:
        nonlocal rollback_paused
        if not rollback_paused:
            rollback_paused = True
            rollback_entered.set()
            assert allow_rollback.wait(timeout=3.0)
        original_restore(lease)
        rollback_completed.set()

    def publish_successfully() -> HipAllocationCapabilityV1:
        successful_attempted.set()
        capability = successful_owner.allocate("will_succeed", 8, "u8")
        successful_committed.set()
        return capability

    monkeypatch.setattr(lineage, "_issue", fail_first_publication)
    monkeypatch.setattr(
        lineage,
        "_restore_orphan_pending_locked",
        pause_publication_rollback,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        failed_future = pool.submit(
            failing_owner.allocate,
            "will_fail",
            8,
            "u8",
        )
        assert rollback_entered.wait(timeout=3.0)
        successful_future = pool.submit(publish_successfully)
        assert successful_attempted.wait(timeout=3.0)
        try:
            assert successful_committed.is_set() is False
            assert successful_future.done() is False
        finally:
            allow_rollback.set()
        with pytest.raises(HipAllocationLineageError) as caught:
            failed_future.result(timeout=3.0)
        successful = successful_future.result(timeout=3.0)

    _assert_error(caught.value, "publish")
    assert rollback_completed.is_set()
    assert successful_committed.is_set()
    assert lineage._ALLOCATIONS[id(successful)].capability is successful
    _orphan_free_success(failing_owner, runtime, caught.value)
    _free_success(successful_owner, runtime, successful)
    failing_owner.close()
    successful_owner.close()


def test_releasing_borrow_with_mutable_base_drift_poisons_then_quarantines() -> None:
    pointer = 0x3EF0000
    mutable_base = ctypes.c_void_p(pointer)
    runtime = FakeAllocationRuntime(pointers=(mutable_base,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = borrow_hip_allocations_v1((capability,), object())
    allocation = lineage._ALLOCATIONS[id(capability)]

    mutable_base.value = pointer + 0x1000
    release_hip_allocation_borrow_v1(lease)

    assert allocation.state == "poisoned"
    assert allocation.borrow_lease is None
    assert id(lease) not in lineage._BORROWS
    assert runtime.free_calls == []
    owner.quarantine_poisoned_allocation(capability)
    assert id(capability) not in lineage._ALLOCATIONS
    assert any(
        row.runtime_domain_id == capability.runtime_domain_id
        and row.device_ordinal == 0
        and row.pointer == pointer
        for row in lineage._QUARANTINED_RANGES
    )
    owner.close()


def test_corrupted_live_mutable_base_quarantines_from_private_registry_extent() -> None:
    pointer = 0x3F00000
    mutable_base = ctypes.c_void_p(pointer)
    runtime = FakeAllocationRuntime(pointers=(mutable_base,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 16, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]
    assert allocation.state == "live"

    mutable_base.value = pointer + 0x2000
    owner.quarantine_poisoned_allocation(capability)

    assert id(capability) not in lineage._ALLOCATIONS
    assert runtime.free_calls == []
    assert any(
        row.runtime_domain_id == capability.runtime_domain_id
        and row.device_ordinal == 0
        and row.pointer == pointer
        and row.end == pointer + 16
        for row in lineage._QUARANTINED_RANGES
    )
    owner.close()


@pytest.mark.parametrize("operation", ("borrow", "free"))
def test_unknown_reservation_state_rolls_back_to_poisoned_and_is_quarantinable(
    operation: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3F10000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]

    def corrupt_reservation_state() -> None:
        runtime.device_callback = None
        allocation.state = "unknown_reservation_state"

    runtime.device_callback = corrupt_reservation_state
    try:
        with pytest.raises(HipAllocationLineageError):
            if operation == "borrow":
                borrow_hip_allocations_v1((capability,), object())
            else:
                owner.begin_free(capability)
    finally:
        runtime.device_callback = None

    assert allocation.state == "poisoned"
    assert allocation.borrow_lease is None
    assert allocation.free_lease is None
    assert not any(
        row.allocation_ids == (id(capability),) for row in lineage._BORROWS.values()
    )
    assert not any(
        row.allocation_id == id(capability) for row in lineage._FREES.values()
    )
    owner.quarantine_poisoned_allocation(capability)
    owner.close()


def test_poison_domain_witness_survives_set_add_memory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime()

    def interrupt_malloc() -> None:
        raise SystemExit("injected outcome-uncertain allocator interruption")

    runtime.malloc_callback = interrupt_malloc
    owner = _open_owner(runtime)
    owner_row = lineage._OWNERS[id(owner)]
    original_poisoned_domains = lineage._POISONED_DOMAINS
    failing_poisoned_domains = _FailOnceSet(original_poisoned_domains)
    monkeypatch.setattr(
        lineage,
        "_POISONED_DOMAINS",
        failing_poisoned_domains,
    )

    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8")
    _assert_error(caught.value, "uncertain")
    assert isinstance(caught.value.__cause__, MemoryError)
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    assert caught.value.orphaned_pointer is None
    assert lineage._ORPHANS[id(lease)].lease is lease
    assert owner_row.domain.poisoned is True
    assert (
        owner.runtime_domain_id,
        owner_row.device_ordinal,
    ) not in failing_poisoned_domains

    runtime.malloc_callback = None
    with pytest.raises(HipAllocationLineageError) as poisoned:
        owner.allocate("retry", 8, "u8")
    _assert_error(poisoned.value, "poison")
    assert lineage._ORPHANS[id(lease)].lease is lease
    owner.quarantine_orphan_free_uncertain(lease)
    owner.close()


def test_closed_marker_interruption_is_idempotently_recoverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime()
    owner = _open_owner(runtime)
    original_registry = lineage._CLOSED_OWNERS
    interrupting_registry = _StoreThenInterruptWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CLOSED_OWNERS", interrupting_registry)

    with pytest.raises(KeyboardInterrupt):
        owner.close()

    assert interrupting_registry.get(owner) is not None
    assert owner._closed_snapshot is True
    assert id(owner) not in lineage._OWNERS
    owner.close()
    assert owner.closed is True
    monkeypatch.setattr(lineage, "_CLOSED_OWNERS", original_registry)


def test_released_marker_interruption_completes_borrow_cleanup_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3F20000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = borrow_hip_allocations_v1((capability,), object())
    allocation = lineage._ALLOCATIONS[id(capability)]
    original_registry = lineage._RELEASED_BORROWS
    interrupting_registry = _StoreThenInterruptWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_RELEASED_BORROWS", interrupting_registry)

    with pytest.raises(KeyboardInterrupt):
        release_hip_allocation_borrow_v1(lease)

    assert interrupting_registry.get(lease) is not None
    assert allocation.state == "borrowed"
    assert allocation.borrow_lease is lease
    assert id(lease) in lineage._BORROWS
    release_hip_allocation_borrow_v1(lease)
    assert allocation.state == "live"
    assert allocation.borrow_lease is None
    assert id(lease) not in lineage._BORROWS

    monkeypatch.setattr(lineage, "_RELEASED_BORROWS", original_registry)
    _free_success(owner, runtime, capability)
    owner.close()


def test_consumed_free_marker_interruption_completes_cleanup_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3F30000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    lease = owner.begin_free(capability)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    original_registry = lineage._CONSUMED_FREES
    interrupting_registry = _StoreThenInterruptWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CONSUMED_FREES", interrupting_registry)

    with pytest.raises(KeyboardInterrupt):
        owner.acknowledge_free_success(lease)

    assert interrupting_registry.get(lease) is not None
    assert id(capability) in lineage._ALLOCATIONS
    assert id(lease) in lineage._FREES
    with pytest.raises(HipAllocationLineageError) as consumed:
        owner.acknowledge_free_success(lease)
    _assert_error(consumed.value, "consumed")
    assert id(capability) not in lineage._ALLOCATIONS
    assert id(lease) not in lineage._FREES

    monkeypatch.setattr(lineage, "_CONSUMED_FREES", original_registry)
    owner.close()


def test_consumed_orphan_marker_interruption_completes_cleanup_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3F40004,))
    owner = _open_owner(runtime)
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "f64")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    original_registry = lineage._CONSUMED_ORPHANS
    interrupting_registry = _StoreThenInterruptWeakRegistry(original_registry)
    monkeypatch.setattr(lineage, "_CONSUMED_ORPHANS", interrupting_registry)

    with pytest.raises(KeyboardInterrupt):
        owner.acknowledge_orphan_free_success(lease)

    assert interrupting_registry.get(lease) is not None
    assert id(lease) in lineage._ORPHANS
    with pytest.raises(HipAllocationLineageError) as consumed:
        owner.acknowledge_orphan_free_success(lease)
    _assert_error(consumed.value, "consumed")
    assert id(lease) not in lineage._ORPHANS

    monkeypatch.setattr(lineage, "_CONSUMED_ORPHANS", original_registry)
    owner.close()


def test_publication_release_interruption_does_not_leave_mutex_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x3F50000, 0x3F60000))
    first_owner = _open_owner(runtime, owner_role="first")
    second_owner = _open_owner(runtime, owner_role="second")
    interrupting_lock = _ReleaseThenInterruptPublicationLock()
    monkeypatch.setattr(lineage, "_PUBLICATION_LOCK", interrupting_lock)

    first = first_owner.allocate("first", 8, "u8")
    assert interrupting_lock.locked() is False
    second = second_owner.allocate("second", 8, "u8")
    assert interrupting_lock.locked() is False
    assert second.allocation_id == first.allocation_id + 1

    _free_success(first_owner, runtime, first)
    _free_success(second_owner, runtime, second)
    first_owner.close()
    second_owner.close()


def test_interrupted_domain_poison_sweep_still_blocks_every_allocation_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4100000, 0x4110000))
    first_owner = _open_owner(runtime, owner_role="first")
    second_owner = _open_owner(runtime, owner_role="second")
    poison_owner = _open_owner(runtime, owner_role="poison")
    first = first_owner.allocate("first", 8, "u8")
    second = second_owner.allocate("second", 8, "u8")
    first_row = lineage._ALLOCATIONS[id(first)]
    second_row = lineage._ALLOCATIONS[id(second)]
    original_poison_row = lineage._poison_allocation_row_locked
    sweep_calls = 0

    def interrupt_before_second_row(allocation: Any) -> None:
        nonlocal sweep_calls
        sweep_calls += 1
        if sweep_calls == 2:
            raise KeyboardInterrupt("injected interrupted domain poison sweep")
        original_poison_row(allocation)

    def interrupt_malloc() -> None:
        raise SystemExit("injected outcome-uncertain allocator call")

    monkeypatch.setattr(
        lineage,
        "_poison_allocation_row_locked",
        interrupt_before_second_row,
    )
    runtime.malloc_callback = interrupt_malloc
    with pytest.raises(HipAllocationLineageError) as caught:
        poison_owner.allocate("poison", 8, "u8")
    _assert_error(caught.value, "uncertain")
    assert sweep_calls == 2
    assert first_row.state == "poisoned"
    assert second_row.state == "live"
    assert lineage._OWNERS[id(first_owner)].domain.poisoned is True

    runtime.malloc_callback = None
    for owner, capability in (
        (first_owner, first),
        (second_owner, second),
    ):
        with pytest.raises(HipAllocationLineageError):
            owner.validate(capability)
        with pytest.raises(HipAllocationLineageError):
            borrow_hip_allocations_v1((capability,), object())
        with pytest.raises(HipAllocationLineageError):
            owner.begin_free(capability)
        assert lineage._ALLOCATIONS[id(capability)].state == "poisoned"

    _quarantine_orphan(poison_owner, caught.value)
    first_owner.quarantine_poisoned_allocation(first)
    second_owner.quarantine_poisoned_allocation(second)
    assert runtime.free_calls == []
    poison_owner.close()
    first_owner.close()
    second_owner.close()


def test_inflight_publication_rechecks_new_domain_poison_and_returns_orphan_cleanup() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x4120000, 0x4130000))
    inflight_owner = _open_owner(runtime, owner_role="inflight")
    poison_owner = _open_owner(runtime, owner_role="poison")
    inflight_malloc = threading.Event()
    resume_inflight = threading.Event()
    callback_lock = threading.Lock()
    callback_count = 0

    def coordinate_malloc_calls() -> None:
        nonlocal callback_count
        with callback_lock:
            callback_count += 1
            call_index = callback_count
        if call_index == 1:
            inflight_malloc.set()
            assert resume_inflight.wait(timeout=3.0)
        elif call_index == 2:
            raise KeyboardInterrupt("injected domain-poisoning allocator interruption")

    runtime.malloc_callback = coordinate_malloc_calls
    with ThreadPoolExecutor(max_workers=1) as pool:
        inflight_future = pool.submit(
            inflight_owner.allocate,
            "inflight",
            8,
            "u8",
        )
        assert inflight_malloc.wait(timeout=3.0)
        try:
            with pytest.raises(HipAllocationLineageError) as poison_error:
                poison_owner.allocate("poison", 8, "u8")
            _assert_error(poison_error.value, "uncertain")
            runtime.malloc_callback = None
            _quarantine_orphan(poison_owner, poison_error.value)
        finally:
            resume_inflight.set()
        with pytest.raises(HipAllocationLineageError) as inflight_error:
            inflight_future.result(timeout=3.0)

    _assert_error(inflight_error.value, "poison")
    assert inflight_error.value.orphaned_pointer is not None
    assert type(inflight_error.value.orphan_cleanup_lease) is HipAllocationOrphanLeaseV1
    assert not any(row.owner is inflight_owner for row in lineage._ALLOCATIONS.values())
    _quarantine_orphan(inflight_owner, inflight_error.value)
    assert runtime.free_calls == []
    poison_owner.close()
    inflight_owner.close()


def test_allocation_handoff_interruption_after_commit_returns_capability() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4140000,))
    owner = _open_owner(runtime)

    def committed_and_attempt_finished(frame: Any) -> bool:
        published = frame.f_locals.get("published")
        handoff = frame.f_locals.get("handoff_capability")
        owner_row = lineage._OWNERS.get(id(owner))
        return (
            type(published) is HipAllocationCapabilityV1
            and type(handoff) is list
            and handoff == [published]
            and owner_row is not None
            and owner_row.allocating_threads == set()
            and not lineage._PUBLICATION_LOCK.locked()
        )

    interrupt = _SingleFireLineInterrupt(
        lineage._allocate,
        committed_and_attempt_finished,
    )
    with interrupt:
        capability = owner.allocate("state", 8, "u8")

    assert interrupt.fired
    assert type(capability) is HipAllocationCapabilityV1
    assert lineage._ALLOCATIONS[id(capability)].state == "live"
    assert lineage._OWNERS[id(owner)].allocating_threads == set()
    assert lineage._OWNERS[id(owner)].successful_allocation_publication_count == 1
    assert owner.validate(capability) is capability
    lease = borrow_hip_allocations_v1((capability,), object())
    release_hip_allocation_borrow_v1(lease)
    _free_success(owner, runtime, capability)
    owner.close()


def test_borrow_return_handoff_interruption_rolls_back_for_retry() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4150000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]
    borrows_before = dict(lineage._BORROWS)

    def borrow_committed(frame: Any) -> bool:
        lease = frame.f_locals.get("lease")
        rows = frame.f_locals.get("rows")
        return (
            type(lease) is HipAllocationBorrowLeaseV1
            and type(rows) is tuple
            and bool(rows)
            and lineage._BORROWS.get(id(lease)) is not None
            and all(row.state == "borrowed" for row in rows)
        )

    interrupt = _SingleFireLineInterrupt(lineage._borrow, borrow_committed)
    with interrupt, pytest.raises(KeyboardInterrupt):
        borrow_hip_allocations_v1((capability,), object())

    assert interrupt.fired
    assert allocation.state == "live"
    assert allocation.borrow_lease is None
    assert lineage._BORROWS == borrows_before
    retry = borrow_hip_allocations_v1((capability,), object())
    release_hip_allocation_borrow_v1(retry)
    _free_success(owner, runtime, capability)
    owner.close()


def test_free_return_handoff_interruption_rolls_back_for_retry() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4160000,))
    owner = _open_owner(runtime)
    capability = owner.allocate("state", 8, "u8")
    allocation = lineage._ALLOCATIONS[id(capability)]
    frees_before = dict(lineage._FREES)

    def free_committed(frame: Any) -> bool:
        lease = frame.f_locals.get("lease")
        observed = frame.f_locals.get("allocation")
        return (
            type(lease) is HipAllocationFreeLeaseV1
            and observed is allocation
            and allocation.state == "free_pending"
            and lineage._FREES.get(id(lease)) is not None
        )

    interrupt = _SingleFireLineInterrupt(lineage._begin_free, free_committed)
    with interrupt, pytest.raises(KeyboardInterrupt):
        owner.begin_free(capability)

    assert interrupt.fired
    assert allocation.state == "live"
    assert allocation.free_lease is None
    assert lineage._FREES == frees_before
    _free_success(owner, runtime, capability)
    owner.close()


def test_new_owner_return_handoff_interruption_leaves_no_strong_row() -> None:
    runtime = FakeAllocationRuntime()
    owners_before = dict(lineage._OWNERS)

    def owner_registered(frame: Any) -> bool:
        owner = frame.f_locals.get("owner")
        owner_row = frame.f_locals.get("owner_row")
        return (
            type(owner) is HipAllocationOwnerV1
            and owner_row is not None
            and lineage._OWNERS.get(id(owner)) is owner_row
        )

    interrupt = _SingleFireLineInterrupt(lineage._new_owner, owner_registered)
    with interrupt, pytest.raises(KeyboardInterrupt):
        _open_owner(runtime, owner_role="interrupted")

    assert interrupt.fired
    assert lineage._OWNERS == owners_before
    next_owner = _open_owner(runtime, owner_role="retry")
    assert lineage._OWNERS[id(next_owner)].owner is next_owner
    next_owner.close()


def test_device_zero_poison_does_not_block_same_runtime_device_one_lifecycle() -> None:
    runtime = FakeAllocationRuntime(
        pointers=(0x4170000, 0x4180000),
        device_ordinal=1,
    )
    device_one_owner = _open_owner(
        runtime,
        device_ordinal=1,
        owner_role="device_one",
    )
    device_one_capability = device_one_owner.allocate("state", 8, "u8")
    domain = lineage._OWNERS[id(device_one_owner)].domain

    runtime.device_ordinal = 0
    device_zero_owner = _open_owner(
        runtime,
        device_ordinal=0,
        owner_role="device_zero",
    )

    def interrupt_device_zero_malloc() -> None:
        raise KeyboardInterrupt("injected device-zero allocator uncertainty")

    runtime.malloc_callback = interrupt_device_zero_malloc
    with pytest.raises(HipAllocationLineageError) as caught:
        device_zero_owner.allocate("uncertain", 8, "u8")
    _assert_error(caught.value, "uncertain")
    runtime.malloc_callback = None
    assert domain.is_device_poisoned(0) is True
    assert domain.is_device_poisoned(1) is False

    with pytest.raises(HipAllocationLineageError) as blocked:
        device_zero_owner.allocate("blocked", 8, "u8")
    _assert_error(blocked.value, "poison")

    runtime.device_ordinal = 1
    assert device_one_owner.validate(device_one_capability) is device_one_capability
    first_free = device_one_owner.begin_free(device_one_capability)
    runtime.free(ctypes.c_void_p(first_free.pointer_snapshot))
    device_one_owner.acknowledge_free_success(first_free)
    followup = device_one_owner.allocate("followup", 8, "u8")
    assert followup.device_ordinal == 1
    _free_success(device_one_owner, runtime, followup)
    device_one_owner.close()

    _quarantine_orphan(device_zero_owner, caught.value)
    device_zero_owner.close()
    assert runtime.free_calls == [0x4170000, 0x4180000]


@pytest.mark.parametrize("device_ordinal", (256, 1024))
def test_device_ordinal_above_fixed_poison_witness_range_fails_before_registration(
    device_ordinal: int,
) -> None:
    runtime = FakeAllocationRuntime(device_ordinal=device_ordinal)
    owners_before = dict(lineage._OWNERS)
    domains_before = tuple(lineage._INJECTED_DOMAINS)

    with pytest.raises(HipAllocationLineageError) as caught:
        _open_owner(runtime, device_ordinal=device_ordinal)
    _assert_error(caught.value, "device")
    assert lineage._OWNERS == owners_before
    assert tuple(lineage._INJECTED_DOMAINS) == domains_before
    assert runtime.malloc_calls == []

    runtime.device_ordinal = 0
    owner = _open_owner(runtime, device_ordinal=0, owner_role="valid_retry")
    owner.close()


def test_fifty_cycles_leave_no_strong_registry_rows_or_unbounded_weak_domains() -> None:
    base = 0x3F00000
    runtime = FakeAllocationRuntime(pointers=(base,) * 50)
    runtime_ref = weakref.ref(runtime)
    last_refs: tuple[weakref.ReferenceType[Any], ...] | None = None
    for index in range(50):
        owner = _open_owner(runtime, owner_role=f"owner_{index}")
        capability = owner.allocate("state", 8, "u8")
        borrower = type("WeakBorrower", (), {})()
        borrow = borrow_hip_allocations_v1((capability,), borrower)
        release_hip_allocation_borrow_v1(borrow)
        free_lease = owner.begin_free(capability)
        runtime.free(capability.base)
        owner.acknowledge_free_success(free_lease)
        owner.close()
        last_refs = (
            weakref.ref(owner),
            weakref.ref(capability),
            weakref.ref(borrower),
            weakref.ref(borrow),
            weakref.ref(free_lease),
        )
    gc.collect()
    assert len(lineage._ALLOCATIONS) == 0
    assert len(lineage._BORROWS) == 0
    assert len(lineage._FREES) == 0
    assert len(lineage._OWNERS) == 0
    assert len(lineage._ORPHANS) == 0
    assert len(lineage._RELEASED_BORROWS) <= 1
    assert len(lineage._CONSUMED_FREES) <= 1
    assert len(lineage._CONSUMED_ORPHANS) <= 1
    assert len(lineage._CLOSED_OWNERS) <= 1
    assert last_refs is not None

    del owner, capability, borrower, borrow, free_lease
    gc.collect()
    assert all(reference() is None for reference in last_refs)
    assert len(lineage._RELEASED_BORROWS) == 0
    assert len(lineage._CONSUMED_FREES) == 0
    assert len(lineage._CONSUMED_ORPHANS) == 0
    assert len(lineage._CLOSED_OWNERS) == 0

    del runtime
    gc.collect()
    assert runtime_ref() is None
    sentinel_runtime = FakeAllocationRuntime(pointers=(0x4000000,))
    sentinel_owner = _open_owner(sentinel_runtime, owner_role="sentinel")
    sentinel_owner.close()
    assert len(lineage._INJECTED_DOMAINS) <= 1


def test_owner_control_api_is_exported_and_preserves_requested_role_order() -> None:
    runtime = FakeAllocationRuntime()
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    allowed_roles = ("solution", "residual", "workspace")

    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=allowed_roles,
    )

    assert (
        lineage.reserve_hip_allocation_owner_control_v1
        is reserve_hip_allocation_owner_control_v1
    )
    assert (
        lineage.validate_hip_allocation_owner_control_v1
        is validate_hip_allocation_owner_control_v1
    )
    assert "reserve_hip_allocation_owner_control_v1" in lineage.__all__
    assert "validate_hip_allocation_owner_control_v1" in lineage.__all__
    assert lineage._OWNERS[id(owner)].control.allowed_roles == allowed_roles
    assert (
        validate_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=allowed_roles,
        )
        is owner
    )
    owner.close(_control_token=token)


@pytest.mark.parametrize(
    ("control_token", "expected_owner_role", "allowed_roles", "fragment"),
    (
        (None, "controlled_owner", ("state",), "token"),
        ("token", "controlled_owner", ("state",), "token"),
        (object(), " controlled_owner", ("state",), "role"),
        (object(), "controlled_owner", (), "allowed"),
        (object(), "controlled_owner", ["state"], "allowed"),
        (object(), "controlled_owner", ("state", "state"), "allowed"),
        (object(), "controlled_owner", (" state",), "role"),
    ),
)
def test_owner_control_request_requires_exact_canonical_values(
    control_token: Any,
    expected_owner_role: Any,
    allowed_roles: Any,
    fragment: str,
) -> None:
    owner = _open_owner(FakeAllocationRuntime(), owner_role="controlled_owner")

    with pytest.raises(HipAllocationLineageError) as caught:
        reserve_hip_allocation_owner_control_v1(
            owner,
            control_token,
            expected_owner_role=expected_owner_role,
            allowed_roles=allowed_roles,
        )
    _assert_error(caught.value, fragment)
    assert lineage._OWNERS[id(owner)].control is None
    owner.close()


def test_owner_control_wrong_role_and_changed_or_foreign_requests_fail_closed() -> None:
    owner = _open_owner(FakeAllocationRuntime(), owner_role="controlled_owner")
    token = object()
    roles = ("state", "work")

    with pytest.raises(HipAllocationLineageError) as wrong_role:
        reserve_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="different_owner",
            allowed_roles=roles,
        )
    _assert_error(wrong_role.value, "role")

    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )
    for other_token, other_roles in (
        (object(), roles),
        (token, tuple(reversed(roles))),
        (token, ("state",)),
    ):
        with pytest.raises(HipAllocationLineageError) as conflict:
            reserve_hip_allocation_owner_control_v1(
                owner,
                other_token,
                expected_owner_role="controlled_owner",
                allowed_roles=other_roles,
            )
        _assert_error(conflict.value, "control")
    owner.close(_control_token=token)


def test_owner_control_same_request_remains_idempotent_after_allocation() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4190000,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    roles = ("state", "work")
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )
    capability = owner.allocate("state", 8, "u8", _control_token=token)

    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )
    assert (
        validate_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=roles,
        )
        is owner
    )
    lease = owner.begin_free(capability, _control_token=token)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease, _control_token=token)
    owner.close(_control_token=token)
    owner.close(_control_token=token)


@pytest.mark.parametrize("activity", ("free", "orphan"))
def test_owner_control_reservation_rejects_prior_lineage_activity(
    activity: str,
) -> None:
    pointers = (0x41A0000,) if activity == "free" else (0,)
    runtime = FakeAllocationRuntime(pointers=pointers)
    owner = _open_owner(runtime, owner_role="controlled_owner")
    if activity == "free":
        capability = owner.allocate("state", 8, "u8")
        _free_success(owner, runtime, capability)
    else:
        with pytest.raises(HipAllocationLineageError) as allocation_error:
            owner.allocate("state", 8, "u8")
        lease = allocation_error.value.orphan_cleanup_lease
        assert type(lease) is HipAllocationOrphanLeaseV1
        owner.quarantine_orphan_free_uncertain(lease)

    with pytest.raises(HipAllocationLineageError) as caught:
        reserve_hip_allocation_owner_control_v1(
            owner,
            object(),
            expected_owner_role="controlled_owner",
            allowed_roles=("state",),
        )
    _assert_error(caught.value, "fresh")
    owner.close()


def test_owner_control_rejects_forbidden_role_without_allocator_call() -> None:
    runtime = FakeAllocationRuntime()
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )

    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("foreign", 8, "u8", _control_token=token)
    _assert_error(caught.value, "role")
    assert runtime.malloc_calls == []
    assert lineage._OWNERS[id(owner)].activity_started is False
    owner.close(_control_token=token)


def test_owner_control_concurrent_wrong_token_allocate_and_close_fail_twenty_times() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x41B0000,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    foreign_token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )

    def reject_allocate(_index: int) -> str:
        try:
            owner.allocate("state", 8, "u8", _control_token=foreign_token)
        except HipAllocationLineageError as exc:
            return exc.code
        return "unexpected_success"

    def reject_close(_index: int) -> str:
        try:
            owner.close(_control_token=foreign_token)
        except HipAllocationLineageError as exc:
            return exc.code
        return "unexpected_success"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = tuple(pool.map(reject_allocate, range(20))) + tuple(
            pool.map(reject_close, range(20))
        )
    assert all("control_token_mismatch" in result for result in results)
    assert runtime.malloc_calls == []
    assert owner.closed is False

    capability = owner.allocate("state", 8, "u8", _control_token=token)
    lease = owner.begin_free(capability, _control_token=token)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease, _control_token=token)
    owner.close(_control_token=token)


def test_owner_control_allocation_publication_rechecks_token_after_malloc() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x41C0000,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    foreign_token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )

    def replace_control() -> None:
        with lineage._LOCK:
            lineage._OWNERS[id(owner)].control = lineage._OwnerControl(
                foreign_token,
                "controlled_owner",
                ("state",),
            )

    runtime.malloc_callback = replace_control
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8", _control_token=token)
    _assert_error(caught.value, "control")
    lease = caught.value.orphan_cleanup_lease
    assert type(lease) is HipAllocationOrphanLeaseV1
    assert id(lease) in lineage._ORPHANS

    runtime.malloc_callback = None
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_orphan_free_success(
        lease,
        _control_token=foreign_token,
    )
    owner.close(_control_token=foreign_token)


def test_owner_control_begin_free_rechecks_token_before_commit() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x41D0000,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    foreign_token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )
    capability = owner.allocate("state", 8, "u8", _control_token=token)

    def replace_control() -> None:
        with lineage._LOCK:
            lineage._OWNERS[id(owner)].control = lineage._OwnerControl(
                foreign_token,
                "controlled_owner",
                ("state",),
            )
        runtime.device_callback = None

    runtime.device_callback = replace_control
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.begin_free(capability, _control_token=token)
    _assert_error(caught.value, "control")
    allocation = lineage._ALLOCATIONS[id(capability)]
    assert allocation.state == "live"
    assert allocation.free_lease is None

    lease = owner.begin_free(capability, _control_token=foreign_token)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease, _control_token=foreign_token)
    owner.close(_control_token=foreign_token)


def test_owner_control_reservation_converges_after_store_interruption() -> None:
    owner = _open_owner(FakeAllocationRuntime(), owner_role="controlled_owner")
    owner_row = lineage._OWNERS[id(owner)]
    token = object()
    roles = ("state", "work")

    interrupt = _SingleFireLineInterrupt(
        reserve_hip_allocation_owner_control_v1,
        lambda _frame: owner_row.control is not None,
    )
    with interrupt:
        reserve_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=roles,
        )

    assert interrupt.fired
    assert owner_row.control is not None
    assert owner_row.control.token is token
    assert owner_row.control.allowed_roles == roles
    owner.close(_control_token=token)


def test_owner_control_idempotent_return_interruption_converges() -> None:
    owner = _open_owner(FakeAllocationRuntime(), owner_role="controlled_owner")
    owner_row = lineage._OWNERS[id(owner)]
    token = object()
    roles = ("state",)
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )

    interrupt = _SingleFireLineInterrupt(
        reserve_hip_allocation_owner_control_v1,
        lambda frame: frame.f_locals.get("existing") is owner_row.control,
    )
    with interrupt:
        reserve_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=roles,
        )

    assert interrupt.fired
    assert owner_row.control is not None
    assert owner_row.control.token is token
    owner.close(_control_token=token)


def test_cleanup_snapshot_uses_canonical_publication_ids_not_registry_keys() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x41E0000, 0x41F0000, 0x4200000, 0, 0, 0))
    owner = _open_owner(runtime, owner_role="snapshot_owner")
    capabilities = tuple(
        owner.allocate(f"state_{index}", 8, "u8") for index in range(3)
    )
    frees = tuple(owner.begin_free(capability) for capability in capabilities)
    orphans: list[HipAllocationOrphanLeaseV1] = []
    for index in range(3):
        with pytest.raises(HipAllocationLineageError) as caught:
            owner.allocate(f"orphan_{index}", 8, "u8")
        orphan = caught.value.orphan_cleanup_lease
        assert type(orphan) is HipAllocationOrphanLeaseV1
        orphans.append(orphan)

    original_allocations = lineage._ALLOCATIONS
    original_frees = lineage._FREES
    original_orphans = lineage._ORPHANS
    lineage._ALLOCATIONS = dict(
        enumerate(reversed(tuple(original_allocations.values())), start=1)
    )
    lineage._FREES = dict(enumerate(reversed(tuple(original_frees.values())), start=1))
    lineage._ORPHANS = dict(
        enumerate(reversed(tuple(original_orphans.values())), start=1)
    )
    try:
        assert owner.cleanup_snapshot() == (
            capabilities,
            frees,
            tuple(orphans),
        )
    finally:
        lineage._ALLOCATIONS = original_allocations
        lineage._FREES = original_frees
        lineage._ORPHANS = original_orphans

    for capability, lease in zip(capabilities, frees, strict=True):
        runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
        owner.acknowledge_free_success(lease)
    for orphan in orphans:
        owner.quarantine_orphan_free_uncertain(orphan)
    owner.close()


@pytest.mark.parametrize("token_mode", ("omitted", "foreign"))
@pytest.mark.parametrize(
    "mutation",
    (
        "begin_free",
        "acknowledge_free_success",
        "quarantine_free_uncertain",
        "resolve_free_success",
        "resolve_free_quarantine",
        "acknowledge_orphan_free_success",
        "quarantine_orphan_free_uncertain",
        "resolve_orphan_free_success",
        "resolve_orphan_free_quarantine",
        "quarantine_poisoned_allocation",
        "resolve_poisoned_allocation_quarantine",
        "close",
    ),
)
def test_reserved_owner_public_mutation_methods_forward_control_token(
    mutation: str,
    token_mode: str,
) -> None:
    pointer = 0 if "orphan" in mutation else 0x4210000
    runtime = FakeAllocationRuntime(pointers=(pointer,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    foreign_token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )

    def invoke(method: Callable[..., object], *args: object) -> object:
        if token_mode == "omitted":
            return method(*args)
        return method(*args, _control_token=foreign_token)

    if mutation == "close":
        with pytest.raises(HipAllocationLineageError) as caught:
            invoke(owner.close)
        assert caught.value.code == "hip_allocation_owner_control_token_mismatch"
        assert owner.closed is False
        owner.close(_control_token=token)
        return

    if "orphan" in mutation:
        with pytest.raises(HipAllocationLineageError) as allocation_error:
            owner.allocate("state", 8, "u8", _control_token=token)
        lease = allocation_error.value.orphan_cleanup_lease
        assert type(lease) is HipAllocationOrphanLeaseV1
        method = getattr(owner, mutation)
        with pytest.raises(HipAllocationLineageError) as caught:
            invoke(method, lease)
        assert caught.value.code == "hip_allocation_owner_control_token_mismatch"
        assert lineage._ORPHANS[id(lease)].state in {"pending", "pending_unverified"}
        owner.quarantine_orphan_free_uncertain(lease, _control_token=token)
        owner.close(_control_token=token)
        return

    capability = owner.allocate("state", 8, "u8", _control_token=token)
    if mutation == "begin_free":
        with pytest.raises(HipAllocationLineageError) as caught:
            invoke(owner.begin_free, capability)
        assert caught.value.code == "hip_allocation_owner_control_token_mismatch"
        assert lineage._ALLOCATIONS[id(capability)].state == "live"
        lease = owner.begin_free(capability, _control_token=token)
        runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
        owner.acknowledge_free_success(lease, _control_token=token)
    elif "poisoned" in mutation:
        object.__setattr__(capability, "role", "tampered")
        method = getattr(owner, mutation)
        with pytest.raises(HipAllocationLineageError) as caught:
            invoke(method, capability)
        assert caught.value.code == "hip_allocation_owner_control_token_mismatch"
        assert lineage._ALLOCATIONS[id(capability)].state == "live"
        owner.resolve_poisoned_allocation_quarantine(
            capability,
            _control_token=token,
        )
    else:
        lease = owner.begin_free(capability, _control_token=token)
        method = getattr(owner, mutation)
        with pytest.raises(HipAllocationLineageError) as caught:
            invoke(method, lease)
        assert caught.value.code == "hip_allocation_owner_control_token_mismatch"
        assert lineage._ALLOCATIONS[id(capability)].state == "free_pending"
        assert lineage._FREES[id(lease)].state == "pending"
        runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
        owner.acknowledge_free_success(lease, _control_token=token)
    owner.close(_control_token=token)


@pytest.mark.parametrize(
    "expected_count",
    (True, -1, 1.0, "0", object()),
)
def test_owner_control_expected_publication_count_requires_exact_nonnegative_int(
    expected_count: Any,
) -> None:
    owner = _open_owner(FakeAllocationRuntime(), owner_role="controlled_owner")
    token = object()
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("state",),
    )

    with pytest.raises(HipAllocationLineageError) as caught:
        validate_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=("state",),
            expected_allocation_publication_count=expected_count,
        )
    assert caught.value.code == (
        "hip_allocation_owner_control_publication_count_invalid"
    )
    assert lineage._OWNERS[id(owner)].successful_allocation_publication_count == 0
    owner.close(_control_token=token)


def test_owner_control_publication_count_is_monotonic_across_free_and_reallocate() -> (
    None
):
    runtime = FakeAllocationRuntime(pointers=(0x4220000, 0x4230000))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    roles = ("state",)
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=0,
    )

    first = owner.allocate("state", 8, "u8", _control_token=token)
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=1,
    )
    first_free = owner.begin_free(first, _control_token=token)
    runtime.free(ctypes.c_void_p(first_free.pointer_snapshot))
    owner.acknowledge_free_success(first_free, _control_token=token)
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=1,
    )

    second = owner.allocate("state", 8, "u8", _control_token=token)
    with pytest.raises(HipAllocationLineageError) as mismatch:
        validate_hip_allocation_owner_control_v1(
            owner,
            token,
            expected_owner_role="controlled_owner",
            allowed_roles=roles,
            expected_allocation_publication_count=1,
        )
    assert mismatch.value.code == (
        "hip_allocation_owner_control_publication_count_mismatch"
    )
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=2,
    )
    second_free = owner.begin_free(second, _control_token=token)
    runtime.free(ctypes.c_void_p(second_free.pointer_snapshot))
    owner.acknowledge_free_success(second_free, _control_token=token)
    owner.close(_control_token=token)


def test_allocation_publication_rollback_restores_owner_publication_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4240000, 0x4250000))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    roles = ("state",)
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )
    original_resolve = lineage._resolve_orphan_adopted_locked
    fail_once = True

    def fail_after_publication_store(lease: HipAllocationOrphanLeaseV1) -> None:
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise MemoryError("injected failure after owner publication count store")
        original_resolve(lease)

    monkeypatch.setattr(
        lineage,
        "_resolve_orphan_adopted_locked",
        fail_after_publication_store,
    )
    with pytest.raises(HipAllocationLineageError) as caught:
        owner.allocate("state", 8, "u8", _control_token=token)
    assert lineage._OWNERS[id(owner)].successful_allocation_publication_count == 0
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=0,
    )
    orphan = caught.value.orphan_cleanup_lease
    assert type(orphan) is HipAllocationOrphanLeaseV1
    runtime.free(ctypes.c_void_p(orphan.pointer_snapshot))
    owner.acknowledge_orphan_free_success(orphan, _control_token=token)

    capability = owner.allocate("state", 8, "u8", _control_token=token)
    assert lineage._OWNERS[id(owner)].successful_allocation_publication_count == 1
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=1,
    )
    lease = owner.begin_free(capability, _control_token=token)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease, _control_token=token)
    owner.close(_control_token=token)


def test_allocation_publication_handoff_store_interruption_counts_once() -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4260000,))
    owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    roles = ("state",)
    reserve_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
    )

    def handoff_stored(frame: Any) -> bool:
        allocation_row = frame.f_locals.get("allocation_row")
        handoff = frame.f_locals.get("handoff_capability")
        return (
            allocation_row is not None
            and type(handoff) is list
            and handoff == [allocation_row.capability]
            and lineage._OWNERS[id(owner)].successful_allocation_publication_count == 1
        )

    interrupt = _SingleFireLineInterrupt(
        lineage._publish_allocation_transaction,
        handoff_stored,
    )
    with interrupt:
        capability = owner.allocate("state", 8, "u8", _control_token=token)

    assert interrupt.fired
    assert lineage._OWNERS[id(owner)].successful_allocation_publication_count == 1
    validate_hip_allocation_owner_control_v1(
        owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=roles,
        expected_allocation_publication_count=1,
    )
    lease = owner.begin_free(capability, _control_token=token)
    runtime.free(ctypes.c_void_p(lease.pointer_snapshot))
    owner.acknowledge_free_success(lease, _control_token=token)
    owner.close(_control_token=token)


@pytest.mark.parametrize("borrower_mode", ("none", "foreign"))
def test_controlled_borrow_rejects_noncontroller_all_or_none(
    borrower_mode: str,
) -> None:
    runtime = FakeAllocationRuntime(pointers=(0x4270000, 0x4280000))
    unreserved_owner = _open_owner(runtime, owner_role="unreserved_owner")
    controlled_owner = _open_owner(runtime, owner_role="controlled_owner")
    token = object()
    reserve_hip_allocation_owner_control_v1(
        controlled_owner,
        token,
        expected_owner_role="controlled_owner",
        allowed_roles=("controlled",),
    )
    unreserved = unreserved_owner.allocate("unreserved", 8, "u8")
    controlled = controlled_owner.allocate(
        "controlled",
        8,
        "u8",
        _control_token=token,
    )
    allocations_before = {
        id(capability): (
            lineage._ALLOCATIONS[id(capability)].state,
            lineage._ALLOCATIONS[id(capability)].borrow_lease,
        )
        for capability in (unreserved, controlled)
    }
    borrows_before = dict(lineage._BORROWS)
    next_lease_before = lineage._NEXT_LEASE_ID
    borrower = None if borrower_mode == "none" else object()

    with pytest.raises(HipAllocationLineageError):
        borrow_hip_allocations_v1((unreserved, controlled), borrower)

    assert lineage._BORROWS == borrows_before
    assert lineage._NEXT_LEASE_ID == next_lease_before
    assert {
        id(capability): (
            lineage._ALLOCATIONS[id(capability)].state,
            lineage._ALLOCATIONS[id(capability)].borrow_lease,
        )
        for capability in (unreserved, controlled)
    } == allocations_before

    lease = borrow_hip_allocations_v1((unreserved, controlled), token)
    release_hip_allocation_borrow_v1(lease)
    controlled_free = controlled_owner.begin_free(
        controlled,
        _control_token=token,
    )
    runtime.free(ctypes.c_void_p(controlled_free.pointer_snapshot))
    controlled_owner.acknowledge_free_success(
        controlled_free,
        _control_token=token,
    )
    _free_success(unreserved_owner, runtime, unreserved)
    controlled_owner.close(_control_token=token)
    unreserved_owner.close()
