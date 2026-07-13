"""Process-local HIP allocation ownership and lifetime capabilities.

This module is deliberately a non-promoting foundation: it proves only the
process-local lineage state maintained here.  It never calls ``hipFree`` and
does not accept caller-owned pointers for registration or adoption.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import threading
from typing import NoReturn
import weakref

from structural_analysis.engine_v2.backends.hip.context import (
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.native import LoadedHipRuntime


HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1 = "foundation_non_promoting"
HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1 = "foundation_non_promoting"

_ARTIFACT_MINT = object()
_INJECTED_HIP_ALLOCATION_OWNER_MINT = object()
_MAX_DEVICE_ORDINAL = 255


class _RuntimeDomain:
    __slots__ = ("_domain_id", "_poisoned_devices")

    def __init__(self, domain_id: str) -> None:
        object.__setattr__(self, "_domain_id", domain_id)
        object.__setattr__(
            self,
            "_poisoned_devices",
            [False] * (_MAX_DEVICE_ORDINAL + 1),
        )

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} fields are read-only")

    @property
    def domain_id(self) -> str:
        return self._domain_id

    @property
    def poisoned(self) -> bool:
        return any(self._poisoned_devices)

    def is_device_poisoned(self, device_ordinal: int) -> bool:
        return self._poisoned_devices[device_ordinal]


_NATIVE_RUNTIME_DOMAIN = _RuntimeDomain("HipAllocationRuntimeDomain:native-process")
_UINTPTR_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
_ELEMENT_LAYOUT = {"f64": (8, 8), "i32": (4, 4), "u8": (1, 1)}


class HipAllocationLineageError(RuntimeError):
    """A fail-closed allocation-lineage contract violation."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str,
        orphaned_pointer: object | None = None,
        orphan_cleanup_lease: HipAllocationOrphanLeaseV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.orphaned_pointer = orphaned_pointer
        self.orphan_cleanup_lease = orphan_cleanup_lease
        super().__init__(f"{code} at {path}: {message}")


class _ImmutableArtifact:
    __slots__ = ("__weakref__",)

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")


class HipAllocationCapabilityV1(_ImmutableArtifact):
    __slots__ = (
        "allocation_id",
        "role",
        "base",
        "pointer_snapshot",
        "nbytes",
        "element_type",
        "generation",
        "owner_identity",
        "runtime_owner",
        "runtime_domain",
        "runtime_domain_id",
        "device_ordinal",
        "evidence_scope",
        "promotion_eligible",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("HipAllocationCapabilityV1 is owner-issued only")


class HipAllocationBorrowLeaseV1(_ImmutableArtifact):
    __slots__ = (
        "lease_id",
        "capabilities",
        "borrower",
        "runtime_domain",
        "device_ordinal",
        "evidence_scope",
        "promotion_eligible",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("HipAllocationBorrowLeaseV1 is registry-issued only")


class HipAllocationFreeLeaseV1(_ImmutableArtifact):
    __slots__ = (
        "lease_id",
        "capability",
        "owner_identity",
        "pointer_snapshot",
        "runtime_domain",
        "runtime_domain_id",
        "device_ordinal",
        "evidence_scope",
        "promotion_eligible",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("HipAllocationFreeLeaseV1 is owner-issued only")


class HipAllocationOrphanLeaseV1(_ImmutableArtifact):
    """Cleanup authority reserved before a successful allocator call."""

    __slots__ = (
        "lease_id",
        "owner_identity",
        "runtime_domain",
        "runtime_domain_id",
        "device_ordinal",
        "role",
        "base",
        "pointer_snapshot",
        "nbytes",
        "element_type",
        "evidence_scope",
        "promotion_eligible",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("HipAllocationOrphanLeaseV1 is allocation-owner issued only")


@dataclass(frozen=True, slots=True)
class _OwnerControl:
    token: object = field(repr=False)
    expected_owner_role: str
    allowed_roles: tuple[str, ...]


@dataclass(slots=True)
class _OwnerRow:
    owner: HipAllocationOwnerV1
    runtime: object
    malloc: object = field(repr=False)
    domain: object
    device_ordinal: int
    owner_id: int
    owner_role: str
    lock_witness: object = field(repr=False)
    generation: int = 0
    closed: bool = False
    allocating_threads: set[int] = field(default_factory=set)
    activity_started: bool = False
    successful_allocation_publication_count: int = 0
    control: _OwnerControl | None = None


@dataclass(slots=True)
class _AllocationRow:
    capability: HipAllocationCapabilityV1
    owner: HipAllocationOwnerV1
    domain: object
    device_ordinal: int
    pointer: int
    end: int
    base: object = field(repr=False)
    nbytes: int
    element_type: str
    role: str
    generation: int
    capability_snapshot: tuple[object, ...]
    state: str = "live"
    borrow_lease: HipAllocationBorrowLeaseV1 | None = None
    free_lease: HipAllocationFreeLeaseV1 | None = None


@dataclass(slots=True)
class _BorrowRow:
    lease: HipAllocationBorrowLeaseV1
    allocation_ids: tuple[int, ...]
    lease_snapshot: tuple[object, ...]
    borrower: object = field(repr=False)
    released: bool = False


@dataclass(slots=True)
class _FreeRow:
    lease: HipAllocationFreeLeaseV1
    allocation_id: int
    lease_snapshot: tuple[object, ...]
    owner: HipAllocationOwnerV1
    state: str = "pending"


@dataclass(slots=True)
class _OrphanRow:
    lease: HipAllocationOrphanLeaseV1
    owner: HipAllocationOwnerV1
    domain: object
    device_ordinal: int
    role: str
    nbytes: int
    element_type: str
    state: str = "allocating"
    base: object | None = field(default=None, repr=False)
    pointer: int | None = None
    end: int | None = None
    lease_snapshot: tuple[object, ...] | None = None
    conflicted: bool = False


@dataclass(frozen=True, slots=True)
class _QuarantinedRange:
    runtime_domain_id: str
    device_ordinal: int
    pointer: int
    end: int | None


_LOCK = threading.RLock()
_PUBLICATION_LOCK = threading.Lock()
_OWNERS: dict[int, _OwnerRow] = {}
_ALLOCATIONS: dict[int, _AllocationRow] = {}
_BORROWS: dict[int, _BorrowRow] = {}
_FREES: dict[int, _FreeRow] = {}
_ORPHANS: dict[int, _OrphanRow] = {}
_QUARANTINED_RANGES: list[_QuarantinedRange] = []
_POISONED_DOMAINS: set[tuple[str, int]] = set()
_INJECTED_DOMAINS: list[tuple[weakref.ReferenceType[object], _RuntimeDomain]] = []
_HIGH_WATER: dict[tuple[str, int], int] = {}
_RELEASED_BORROWS: weakref.WeakKeyDictionary[
    HipAllocationBorrowLeaseV1, tuple[object, ...]
] = weakref.WeakKeyDictionary()
_CONSUMED_FREES: weakref.WeakKeyDictionary[
    HipAllocationFreeLeaseV1, tuple[tuple[object, ...], str]
] = weakref.WeakKeyDictionary()
_CONSUMED_ORPHANS: weakref.WeakKeyDictionary[
    HipAllocationOrphanLeaseV1, tuple[tuple[object, ...], str]
] = weakref.WeakKeyDictionary()
_QUARANTINED_CAPABILITIES: weakref.WeakKeyDictionary[
    HipAllocationCapabilityV1, tuple[int, tuple[object, ...]]
] = weakref.WeakKeyDictionary()
_CLOSED_OWNERS: weakref.WeakKeyDictionary[HipAllocationOwnerV1, tuple[object, ...]] = (
    weakref.WeakKeyDictionary()
)
_CLOSED_OWNER_CONTROLS: weakref.WeakKeyDictionary[
    HipAllocationOwnerV1, _OwnerControl
] = weakref.WeakKeyDictionary()
_NEXT_OWNER_ID = 1
_NEXT_ALLOCATION_ID = 1
_NEXT_LEASE_ID = 1
_NEXT_DOMAIN_ID = 1


def _error(code: str, path: str, message: str) -> NoReturn:
    raise HipAllocationLineageError(code, path, message)


def _exact_int(value: object, path: str, *, positive: bool = False) -> int:
    if type(value) is not int:
        _error("hip_allocation_type_invalid", path, "must be an exact int")
    if value < 0 or (positive and value == 0):
        condition = "positive" if positive else "nonnegative"
        _error("hip_allocation_value_invalid", path, f"must be {condition}")
    return value


def _device_ordinal(value: object, path: str = "device_ordinal") -> int:
    device = _exact_int(value, path)
    if device > _MAX_DEVICE_ORDINAL:
        _error(
            "hip_allocation_value_invalid",
            path,
            f"must be at most {_MAX_DEVICE_ORDINAL}",
        )
    return device


def _nonempty_string(value: object, path: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > 128
    ):
        _error(
            "hip_allocation_type_invalid",
            path,
            "must be an exact trimmed nonempty str of at most 128 characters",
        )
    return value


def _owner_control_request(
    control_token: object,
    expected_owner_role: object,
    allowed_roles: object,
) -> _OwnerControl:
    if type(control_token) is not object:
        _error(
            "hip_allocation_owner_control_token_invalid",
            "control_token",
            "an exact object token is required",
        )
    if (
        type(expected_owner_role) is not str
        or not expected_owner_role
        or expected_owner_role.strip() != expected_owner_role
        or len(expected_owner_role) > 128
    ):
        _error(
            "hip_allocation_owner_control_role_invalid",
            "expected_owner_role",
            "an exact trimmed nonempty str of at most 128 characters is required",
        )
    if type(allowed_roles) is not tuple or not allowed_roles:
        _error(
            "hip_allocation_owner_control_request_invalid",
            "allowed_roles",
            "an exact nonempty tuple of roles is required",
        )
    canonical_roles: list[str] = []
    seen: set[str] = set()
    for index, role in enumerate(allowed_roles):
        if type(role) is not str or not role or role.strip() != role or len(role) > 128:
            _error(
                "hip_allocation_owner_control_role_invalid",
                f"allowed_roles[{index}]",
                "an exact trimmed nonempty str of at most 128 characters is required",
            )
        if role in seen:
            _error(
                "hip_allocation_owner_control_request_invalid",
                f"allowed_roles[{index}]",
                "roles must be unique",
            )
        seen.add(role)
        canonical_roles.append(role)
    return _OwnerControl(
        token=control_token,
        expected_owner_role=expected_owner_role,
        allowed_roles=tuple(canonical_roles),
    )


def _pointer_snapshot(base: object, path: str = "base") -> int:
    if type(base) is int:
        pointer = base
    elif type(base) is ctypes.c_void_p:
        pointer = base.value
    else:
        _error(
            "hip_allocation_pointer_invalid",
            path,
            "must be an exact int or ctypes.c_void_p",
        )
    if (
        type(pointer) is not int
        or pointer <= 0
        or pointer > _UINTPTR_MAX
        or ctypes.c_void_p(pointer).value != pointer
    ):
        _error(
            "hip_allocation_pointer_invalid",
            path,
            "must contain a nonzero uintptr_t value",
        )
    return pointer


def _allocation_extent(
    nbytes: object, element_type: object, path: str = "allocation"
) -> tuple[int, int]:
    if type(element_type) is not str or element_type not in _ELEMENT_LAYOUT:
        _error(
            "hip_allocation_element_type_invalid",
            f"{path}.element_type",
            "must be exactly f64, i32, or u8",
        )
    size, alignment = _ELEMENT_LAYOUT[element_type]
    if (
        type(nbytes) is not int
        or nbytes <= 0
        or nbytes > _UINTPTR_MAX
        or nbytes % size != 0
    ):
        _error(
            "hip_allocation_extent_invalid",
            f"{path}.nbytes",
            "extent must be a positive exact int that fits uintptr_t and is an element-size multiple",
        )
    return nbytes, alignment


def _range_end(pointer: int, nbytes: int, path: str = "allocation") -> int:
    last = pointer + nbytes - 1
    if last < pointer or last > _UINTPTR_MAX:
        _error(
            "hip_allocation_range_overflow",
            path,
            "allocation range exceeds uintptr_t",
        )
    return last + 1


def _injected_domain(runtime: object) -> _RuntimeDomain:
    alive: list[tuple[weakref.ReferenceType[object], _RuntimeDomain]] = []
    dead_domain_ids: set[str] = set()
    found: _RuntimeDomain | None = None
    for representative_ref, witness in _INJECTED_DOMAINS:
        representative = representative_ref()
        if representative is None:
            dead_domain_ids.add(witness.domain_id)
            continue
        alive.append((representative_ref, witness))
        if representative is runtime:
            found = witness
    _INJECTED_DOMAINS[:] = alive
    if dead_domain_ids:
        for key in tuple(_HIGH_WATER):
            if key[0] in dead_domain_ids:
                del _HIGH_WATER[key]
        _POISONED_DOMAINS.difference_update(
            tuple(key for key in _POISONED_DOMAINS if key[0] in dead_domain_ids)
        )
        _QUARANTINED_RANGES[:] = [
            row
            for row in _QUARANTINED_RANGES
            if row.runtime_domain_id not in dead_domain_ids
        ]
    if found is not None:
        return found
    global _NEXT_DOMAIN_ID
    witness = _RuntimeDomain(f"HipAllocationRuntimeDomain:injected:{_NEXT_DOMAIN_ID}")
    try:
        representative_ref = weakref.ref(runtime)
    except TypeError as exc:
        raise HipAllocationLineageError(
            "hip_allocation_runtime_invalid",
            "runtime",
            "injected runtimes must support weak references",
        ) from exc
    _INJECTED_DOMAINS.append((representative_ref, witness))
    _NEXT_DOMAIN_ID += 1
    return witness


def _domain_id(domain: object) -> str:
    if (
        type(domain) is not _RuntimeDomain
        or type(domain.domain_id) is not str
        or type(domain._poisoned_devices) is not list
        or len(domain._poisoned_devices) != _MAX_DEVICE_ORDINAL + 1
        or type(domain.poisoned) is not bool
    ):
        _error(
            "hip_allocation_runtime_invalid",
            "runtime_domain",
            "runtime domain witness is not registered",
        )
    return domain.domain_id


def _issue(cls: type[object], values: dict[str, object]) -> object:
    artifact = object.__new__(cls)
    for name, value in values.items():
        object.__setattr__(artifact, name, value)
    return artifact


class HipAllocationOwnerV1:
    """Exclusive owner that mints capabilities only after a real malloc."""

    __slots__ = (
        "_owner_id",
        "_lock",
        "_owner_role_snapshot",
        "_runtime_domain_id_snapshot",
        "_generation_snapshot",
        "_closed_snapshot",
        "__weakref__",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("HipAllocationOwnerV1 is factory-issued only")

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} fields are read-only")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} fields are read-only")

    @property
    def owner_id(self) -> int:
        with _LOCK:
            _validate_owner_identity_locked(self, "owner")
            return self._owner_id

    @property
    def closed(self) -> bool:
        with _LOCK:
            _validate_owner_identity_locked(self, "owner")
            return self._closed_snapshot

    @property
    def generation(self) -> int:
        with _LOCK:
            _validate_owner_identity_locked(self, "owner")
            return self._generation_snapshot

    @property
    def runtime_domain_id(self) -> str:
        with _LOCK:
            _validate_owner_identity_locked(self, "owner")
            return self._runtime_domain_id_snapshot

    @property
    def owner_role(self) -> str:
        with _LOCK:
            _validate_owner_identity_locked(self, "owner")
            return self._owner_role_snapshot

    @property
    def evidence_scope(self) -> str:
        return HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1

    @property
    def promotion_eligible(self) -> bool:
        return False

    def allocate(
        self,
        role: str,
        nbytes: int,
        element_type: str,
        *,
        _control_token: object | None = None,
    ) -> HipAllocationCapabilityV1:
        return _allocate(
            self,
            role,
            nbytes,
            element_type,
            _control_token=_control_token,
        )

    def validate(
        self, capability: HipAllocationCapabilityV1
    ) -> HipAllocationCapabilityV1:
        _validate_runtime_owner(self, "owner")
        with _LOCK:
            _owner_row(self, "owner")
            row = _capability_row(capability, "capability")
            if row.owner is not self:
                _error("hip_allocation_foreign", "capability", "not active for owner")
            if row.state.startswith("poisoned"):
                _error(
                    "hip_allocation_poisoned",
                    "capability",
                    "allocation lineage is poisoned by an overlap conflict",
                )
            if row.state in {"freed", "quarantined"}:
                _error("hip_allocation_foreign", "capability", "not active for owner")
            return capability

    def begin_free(
        self,
        capability: HipAllocationCapabilityV1,
        *,
        _control_token: object | None = None,
    ) -> HipAllocationFreeLeaseV1:
        return _begin_free(self, capability, _control_token=_control_token)

    def acknowledge_free_success(
        self,
        lease: HipAllocationFreeLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> None:
        _acknowledge_free_success(self, lease, _control_token=_control_token)

    def quarantine_free_uncertain(
        self,
        lease: HipAllocationFreeLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> None:
        _quarantine_free_uncertain(self, lease, _control_token=_control_token)

    def resolve_free_success(
        self,
        lease: HipAllocationFreeLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> str:
        """Idempotently converge a known-successful external free."""

        return _finish_free(
            self,
            lease,
            quarantine=False,
            idempotent=True,
            _control_token=_control_token,
        )

    def resolve_free_quarantine(
        self,
        lease: HipAllocationFreeLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> str:
        """Idempotently converge an outcome-uncertain external free."""

        return _finish_free(
            self,
            lease,
            quarantine=True,
            idempotent=True,
            _control_token=_control_token,
        )

    def acknowledge_orphan_free_success(
        self,
        lease: HipAllocationOrphanLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> None:
        _finish_orphan(
            self,
            lease,
            quarantine=False,
            _control_token=_control_token,
        )

    def quarantine_orphan_free_uncertain(
        self,
        lease: HipAllocationOrphanLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> None:
        _finish_orphan(
            self,
            lease,
            quarantine=True,
            _control_token=_control_token,
        )

    def resolve_orphan_free_success(
        self,
        lease: HipAllocationOrphanLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> str:
        """Idempotently converge a known-successful orphan cleanup."""

        return _finish_orphan(
            self,
            lease,
            quarantine=False,
            idempotent=True,
            _control_token=_control_token,
        )

    def resolve_orphan_free_quarantine(
        self,
        lease: HipAllocationOrphanLeaseV1,
        *,
        _control_token: object | None = None,
    ) -> str:
        """Idempotently converge an outcome-uncertain orphan cleanup."""

        return _finish_orphan(
            self,
            lease,
            quarantine=True,
            idempotent=True,
            _control_token=_control_token,
        )

    def quarantine_poisoned_allocation(
        self,
        capability: HipAllocationCapabilityV1,
        *,
        _control_token: object | None = None,
    ) -> None:
        _quarantine_poisoned_allocation(
            self,
            capability,
            idempotent=False,
            _control_token=_control_token,
        )

    def resolve_poisoned_allocation_quarantine(
        self,
        capability: HipAllocationCapabilityV1,
        *,
        _control_token: object | None = None,
    ) -> str:
        """Idempotently retire a poisoned/corrupted live allocation."""

        return _quarantine_poisoned_allocation(
            self,
            capability,
            idempotent=True,
            _control_token=_control_token,
        )

    def cleanup_snapshot(
        self,
    ) -> tuple[
        tuple[HipAllocationCapabilityV1, ...],
        tuple[HipAllocationFreeLeaseV1, ...],
        tuple[HipAllocationOrphanLeaseV1, ...],
    ]:
        """Snapshot exact live cleanup authorities without runtime callbacks."""

        return snapshot_hip_allocation_owner_cleanup_v1(self)

    def close(self, *, _control_token: object | None = None) -> None:
        with _LOCK:
            if self._closed_snapshot:
                _validate_owner_identity_locked(self, "owner")
                closed_control = _CLOSED_OWNER_CONTROLS.get(self)
                if closed_control is None:
                    if (
                        _control_token is not None
                        and type(_control_token) is not object
                    ):
                        _error(
                            "hip_allocation_owner_control_token_invalid",
                            "_control_token",
                            "an exact object token or None is required",
                        )
                elif (
                    type(_control_token) is not object
                    or _control_token is not closed_control.token
                ):
                    _error(
                        "hip_allocation_owner_control_token_mismatch",
                        "_control_token",
                        "the exact reserved owner-control token is required",
                    )
                return
            owner = _owner_row(self, "owner")
            _require_owner_control_locked(owner, _control_token)
            if owner.allocating_threads:
                _error(
                    "hip_allocation_owner_busy",
                    "owner",
                    "owner has an allocator call in progress",
                )
            for row in _ALLOCATIONS.values():
                if row.owner is self and row.state not in {"freed", "quarantined"}:
                    _error(
                        "hip_allocation_owner_busy",
                        "owner",
                        "owner has live, borrowed, or pending allocations",
                    )
            if any(
                row.owner is self
                and row.state in {"allocating", "pending", "pending_unverified"}
                for row in _ORPHANS.values()
            ):
                _error(
                    "hip_allocation_owner_busy",
                    "owner",
                    "owner has an unresolved post-malloc orphan",
                )
            closed_snapshot: tuple[object, ...] | None = None
            try:
                owner.closed = True
                object.__setattr__(self, "_closed_snapshot", True)
                closed_snapshot = _owner_identity_snapshot(self)
                _CLOSED_OWNERS[self] = closed_snapshot
                del _OWNERS[id(self)]
                if owner.control is not None:
                    _CLOSED_OWNER_CONTROLS[self] = owner.control
            except BaseException:
                if (
                    closed_snapshot is not None
                    and _CLOSED_OWNERS.get(self) == closed_snapshot
                ):
                    _OWNERS.pop(id(self), None)
                    owner.closed = True
                    object.__setattr__(self, "_closed_snapshot", True)
                    if owner.control is not None:
                        _CLOSED_OWNER_CONTROLS[self] = owner.control
                else:
                    owner.closed = False
                    object.__setattr__(self, "_closed_snapshot", False)
                    _CLOSED_OWNER_CONTROLS.pop(self, None)
                raise


def open_hip_allocation_owner_v1(
    runtime: _BoundHipContextRuntime,
    device_ordinal: int,
    owner_role: str,
    *,
    _handoff: list[HipAllocationOwnerV1 | None] | None = None,
) -> HipAllocationOwnerV1:
    """Open a native owner after checking exact loader and selected-device state."""

    if type(runtime) is not _BoundHipContextRuntime:
        _error(
            "hip_allocation_runtime_invalid", "runtime", "exact bound runtime required"
        )
    loaded = runtime.loaded_runtime
    if type(loaded) is not LoadedHipRuntime:
        _error(
            "hip_allocation_runtime_invalid",
            "runtime",
            "native loader provenance required",
        )
    try:
        provenance = loaded._loader_provenance_witness()
    except Exception as exc:
        raise HipAllocationLineageError(
            "hip_allocation_runtime_invalid",
            "runtime",
            "native loader provenance unavailable",
        ) from exc
    device = _device_ordinal(device_ordinal)
    role = _nonempty_string(owner_role, "owner_role")
    if (
        getattr(runtime, "_loader_provenance_witness", None) is not provenance
        or runtime.device_ordinal != device
    ):
        _error(
            "hip_allocation_device_mismatch", "device_ordinal", "runtime device differs"
        )
    try:
        get_device = loaded.bind(
            "hipGetDevice", [ctypes.POINTER(ctypes.c_int)], ctypes.c_int
        )
        current = ctypes.c_int()
        status = get_device(ctypes.byref(current))
    except Exception as exc:
        raise HipAllocationLineageError(
            "hip_allocation_device_query_failed",
            "device_ordinal",
            type(exc).__name__,
        ) from exc
    if status != 0 or current.value != device:
        _error(
            "hip_allocation_device_mismatch",
            "device_ordinal",
            "HIP current device differs",
        )
    return _new_owner(
        runtime,
        _NATIVE_RUNTIME_DOMAIN,
        device,
        role,
        handoff=_handoff,
    )


def open_hip_allocation_peer_owner_v1(
    parent_owner: HipAllocationOwnerV1,
    owner_role: str,
    *,
    _handoff: list[HipAllocationOwnerV1 | None] | None = None,
) -> HipAllocationOwnerV1:
    """Open a sibling owner in the exact runtime/device domain of ``parent_owner``.

    The peer factory does not adopt or copy any allocation.  It only carries
    forward the already-validated allocator provenance so a downstream owner
    can mint its own capabilities in the same atomic-borrow domain.
    """

    role = _nonempty_string(owner_role, "owner_role")
    _validate_runtime_owner(parent_owner, "parent_owner")
    with _LOCK:
        parent = _owner_row(parent_owner, "parent_owner")
        if parent.closed:
            _error(
                "hip_allocation_owner_closed",
                "parent_owner",
                "parent owner is closed",
            )
        runtime = parent.runtime
        domain = parent.domain
        device = parent.device_ordinal
    # ``runtime.malloc`` may be an injected descriptor.  Resolve it only after
    # the registry lock has been released; the parent snapshot above is the
    # peer-open linearization point.
    return _new_owner(runtime, domain, device, role, handoff=_handoff)


def _open_integrated_hip_allocation_owner_v1(
    runtime: object,
    device_ordinal: int,
    owner_role: str,
    *,
    _handoff: list[HipAllocationOwnerV1 | None] | None = None,
) -> HipAllocationOwnerV1:
    """Package-internal bridge for native runtimes and injected test doubles."""

    if (
        type(runtime) is _BoundHipContextRuntime
        and type(runtime.loaded_runtime) is LoadedHipRuntime
    ):
        return open_hip_allocation_owner_v1(
            runtime,
            device_ordinal,
            owner_role,
            _handoff=_handoff,
        )
    return _open_injected_hip_allocation_owner_v1(
        runtime,
        device_ordinal,
        owner_role,
        _mint=_INJECTED_HIP_ALLOCATION_OWNER_MINT,
        _handoff=_handoff,
    )


def _open_injected_hip_allocation_owner_v1(
    runtime: object,
    device_ordinal: int,
    owner_role: str,
    *,
    _mint: object,
    _handoff: list[HipAllocationOwnerV1 | None] | None = None,
) -> HipAllocationOwnerV1:
    """Private test/integration factory; injected evidence cannot be promoted."""

    if _mint is not _INJECTED_HIP_ALLOCATION_OWNER_MINT:
        _error(
            "hip_allocation_runtime_invalid", "_mint", "private injected mint required"
        )
    device = _device_ordinal(device_ordinal)
    role = _nonempty_string(owner_role, "owner_role")
    if getattr(runtime, "device_ordinal", None) != device:
        _error(
            "hip_allocation_device_mismatch", "device_ordinal", "runtime device differs"
        )
    if not callable(getattr(runtime, "malloc", None)):
        _error("hip_allocation_runtime_invalid", "runtime", "malloc callable required")
    with _LOCK:
        domain = _injected_domain(runtime)
    return _new_owner(runtime, domain, device, role, handoff=_handoff)


def borrow_hip_allocations_v1(
    capabilities: tuple[HipAllocationCapabilityV1, ...],
    borrower: object,
) -> HipAllocationBorrowLeaseV1:
    return _borrow(capabilities, borrower)


def validate_hip_allocation_borrow_v1(
    lease: HipAllocationBorrowLeaseV1,
) -> HipAllocationBorrowLeaseV1:
    snapshot = _borrow_snapshot(lease, "lease")
    with _LOCK:
        released = _RELEASED_BORROWS.get(lease)
        if released is not None:
            if released != snapshot:
                _error(
                    "hip_allocation_borrow_invalid",
                    "lease",
                    "released lease fields changed",
                )
            _error("hip_allocation_borrow_released", "lease", "lease is released")
        row = _borrow_row(lease, "lease", require_active=True)
        owners: list[HipAllocationOwnerV1] = []
        for allocation_id in row.allocation_ids:
            allocation = _ALLOCATIONS[allocation_id]
            if all(existing is not allocation.owner for existing in owners):
                owners.append(allocation.owner)
    for owner in owners:
        _validate_runtime_owner(owner, "lease.owner")
    with _LOCK:
        if _borrow_snapshot(lease, "lease") != snapshot:
            _error(
                "hip_allocation_borrow_invalid",
                "lease",
                "lease changed during runtime validation",
            )
        released = _RELEASED_BORROWS.get(lease)
        if released is not None:
            if released != snapshot:
                _error(
                    "hip_allocation_borrow_invalid",
                    "lease",
                    "released lease fields changed",
                )
            _error("hip_allocation_borrow_released", "lease", "lease is released")
        _borrow_row(lease, "lease", require_active=True)
        return lease


def release_hip_allocation_borrow_v1(lease: HipAllocationBorrowLeaseV1) -> None:
    _release_borrow(lease)


def recover_hip_allocation_borrow_v1(
    capabilities: tuple[HipAllocationCapabilityV1, ...],
    borrower: object,
) -> HipAllocationBorrowLeaseV1 | None:
    """Recover an active group-borrow across a caller handoff interruption.

    This is a host-registry-only cleanup operation.  It deliberately performs
    no runtime callback, and only returns the unique exact lease whose tuple
    object and borrower identity match the caller's pre-published witnesses.
    """

    if type(capabilities) is not tuple or not capabilities or borrower is None:
        _error(
            "hip_allocation_borrow_recovery_invalid",
            "borrow",
            "exact nonempty capabilities and borrower identity are required",
        )
    with _LOCK:
        matches = tuple(
            row.lease
            for row in _BORROWS.values()
            if not row.released
            and row.borrower is borrower
            and row.lease.capabilities is capabilities
        )
        if len(matches) > 1:
            _error(
                "hip_allocation_borrow_recovery_ambiguous",
                "borrow",
                "multiple active leases match the same handoff witnesses",
            )
        return None if not matches else matches[0]


def snapshot_hip_allocation_owner_cleanup_v1(
    owner: HipAllocationOwnerV1,
) -> tuple[
    tuple[HipAllocationCapabilityV1, ...],
    tuple[HipAllocationFreeLeaseV1, ...],
    tuple[HipAllocationOrphanLeaseV1, ...],
]:
    """Return all host-registry cleanup witnesses owned by one exact owner."""

    if type(owner) is not HipAllocationOwnerV1:
        _error("hip_allocation_owner_invalid", "owner", "exact owner required")
    with _LOCK:
        _owner_row(owner, "owner")
        capabilities = tuple(
            row.capability
            for row in sorted(
                _ALLOCATIONS.values(),
                key=lambda candidate: candidate.capability_snapshot[0],
            )
            if row.owner is owner
        )
        frees = tuple(
            row.lease
            for row in sorted(
                _FREES.values(),
                key=lambda candidate: candidate.lease_snapshot[0],
            )
            if row.owner is owner
        )
        orphans = tuple(
            row.lease
            for row in sorted(
                _ORPHANS.values(),
                key=lambda candidate: candidate.lease.lease_id,
            )
            if row.owner is owner and row.state in {"pending", "pending_unverified"}
        )
        return capabilities, frees, orphans


def validate_hip_allocation_capability_v1(
    capability: HipAllocationCapabilityV1,
    *,
    expected_owner: HipAllocationOwnerV1 | None = None,
) -> HipAllocationCapabilityV1:
    """Revalidate one process-local capability against its private row."""

    with _LOCK:
        row = _capability_row(capability, "capability")
        owner = row.owner
    _validate_runtime_owner(owner, "capability.owner")
    with _LOCK:
        row = _capability_row(capability, "capability")
        if row.state in {"freed", "quarantined"} or row.state.startswith("poisoned"):
            _error(
                "hip_allocation_capability_stale",
                "capability",
                "allocation is no longer live",
            )
        if expected_owner is not None and row.owner is not expected_owner:
            _error(
                "hip_allocation_foreign",
                "expected_owner",
                "capability belongs to another owner",
            )
    return capability


def validate_hip_allocation_owner_v1(
    owner: HipAllocationOwnerV1,
) -> HipAllocationOwnerV1:
    """Revalidate one live owner and its exact runtime/device provenance."""

    _validate_runtime_owner(owner, "owner")
    return owner


def _owner_control_matches(
    control: object,
    request: _OwnerControl,
) -> bool:
    return (
        type(control) is _OwnerControl
        and control.token is request.token
        and control.expected_owner_role == request.expected_owner_role
        and control.allowed_roles == request.allowed_roles
    )


def _require_owner_control_locked(
    owner_row: _OwnerRow,
    control_token: object | None,
    *,
    allocation_role: str | None = None,
) -> None:
    control = owner_row.control
    if control is None:
        if control_token is not None and type(control_token) is not object:
            _error(
                "hip_allocation_owner_control_token_invalid",
                "_control_token",
                "an exact object token or None is required",
            )
        return
    if (
        type(control) is not _OwnerControl
        or type(control.token) is not object
        or type(control.expected_owner_role) is not str
        or control.expected_owner_role != owner_row.owner_role
        or type(control.allowed_roles) is not tuple
        or not control.allowed_roles
        or any(type(role) is not str or not role for role in control.allowed_roles)
        or len(set(control.allowed_roles)) != len(control.allowed_roles)
    ):
        _error(
            "hip_allocation_owner_control_invalid",
            "owner.control",
            "owner control registry witness changed",
        )
    if type(control_token) is not object or control_token is not control.token:
        _error(
            "hip_allocation_owner_control_token_mismatch",
            "_control_token",
            "the exact reserved owner-control token is required",
        )
    if allocation_role is not None and allocation_role not in control.allowed_roles:
        _error(
            "hip_allocation_owner_control_role_forbidden",
            "allocation.role",
            "allocation role is outside the reserved owner-control role set",
        )


def reserve_hip_allocation_owner_control_v1(
    owner: HipAllocationOwnerV1,
    control_token: object,
    *,
    expected_owner_role: str,
    allowed_roles: tuple[str, ...],
) -> None:
    """Atomically reserve exclusive mutation control over one fresh owner."""

    request = _owner_control_request(
        control_token,
        expected_owner_role,
        allowed_roles,
    )
    try:
        with _LOCK:
            owner_row = _owner_row(owner, "owner")
            existing = owner_row.control
            if existing is not None:
                if _owner_control_matches(existing, request):
                    return
                _error(
                    "hip_allocation_owner_control_conflict",
                    "owner.control",
                    "owner control is already reserved by a different request",
                )
            if owner_row.closed:
                _error(
                    "hip_allocation_owner_closed",
                    "owner",
                    "owner is closed",
                )
            if owner_row.owner_role != request.expected_owner_role:
                _error(
                    "hip_allocation_owner_control_role_mismatch",
                    "expected_owner_role",
                    "live owner role differs from the requested role",
                )
            is_fresh = (
                owner_row.generation == 0
                and not owner_row.activity_started
                and owner_row.successful_allocation_publication_count == 0
                and not owner_row.allocating_threads
                and not any(row.owner is owner for row in _ALLOCATIONS.values())
                and not any(row.owner is owner for row in _FREES.values())
                and not any(row.owner is owner for row in _ORPHANS.values())
            )
            if not is_fresh:
                _error(
                    "hip_allocation_owner_control_not_fresh",
                    "owner",
                    "owner control may only be reserved before lineage activity",
                )
            owner_row.control = request
            return
    except BaseException:
        # A trace/profiler interruption may fire immediately after STORE_ATTR
        # or at the return boundary.  Converge only the exact published request.
        with _LOCK:
            current = _OWNERS.get(id(owner))
            if (
                current is not None
                and current.owner is owner
                and _owner_control_matches(current.control, request)
            ):
                return
        raise


def validate_hip_allocation_owner_control_v1(
    owner: HipAllocationOwnerV1,
    control_token: object,
    *,
    expected_owner_role: str,
    allowed_roles: tuple[str, ...],
    expected_allocation_publication_count: int | None = None,
) -> HipAllocationOwnerV1:
    """Read-only validation of one exact live owner-control reservation."""

    if expected_allocation_publication_count is not None and (
        type(expected_allocation_publication_count) is not int
        or expected_allocation_publication_count < 0
    ):
        _error(
            "hip_allocation_owner_control_publication_count_invalid",
            "expected_allocation_publication_count",
            "an exact nonnegative int or None is required",
        )
    request = _owner_control_request(
        control_token,
        expected_owner_role,
        allowed_roles,
    )
    _validate_runtime_owner(owner, "owner")
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        if not _owner_control_matches(owner_row.control, request):
            _error(
                "hip_allocation_owner_control_mismatch",
                "owner.control",
                "live owner control differs from the requested reservation",
            )
        if (
            expected_allocation_publication_count is not None
            and owner_row.successful_allocation_publication_count
            != expected_allocation_publication_count
        ):
            _error(
                "hip_allocation_owner_control_publication_count_mismatch",
                "expected_allocation_publication_count",
                "successful allocation publication history differs from expected",
            )
        return owner


def _new_owner(
    runtime: object,
    domain: object,
    device_ordinal: int,
    owner_role: str,
    *,
    handoff: list[HipAllocationOwnerV1 | None] | None = None,
) -> HipAllocationOwnerV1:
    malloc = getattr(runtime, "malloc", None)
    if not callable(malloc):
        _error("hip_allocation_runtime_invalid", "runtime", "malloc callable required")
    owner: HipAllocationOwnerV1 | None = None
    owner_row: _OwnerRow | None = None
    if handoff is not None and (
        type(handoff) is not list or len(handoff) != 1 or handoff[0] is not None
    ):
        _error(
            "hip_allocation_owner_handoff_invalid",
            "owner.handoff",
            "exact empty one-slot handoff required",
        )
    try:
        with _LOCK:
            global _NEXT_OWNER_ID
            owner_id = _NEXT_OWNER_ID
            _NEXT_OWNER_ID += 1
            lock_witness = object()
            owner = object.__new__(HipAllocationOwnerV1)
            object.__setattr__(owner, "_owner_id", owner_id)
            object.__setattr__(owner, "_lock", lock_witness)
            object.__setattr__(owner, "_owner_role_snapshot", owner_role)
            object.__setattr__(
                owner,
                "_runtime_domain_id_snapshot",
                _domain_id(domain),
            )
            object.__setattr__(owner, "_generation_snapshot", 0)
            object.__setattr__(owner, "_closed_snapshot", False)
            owner_row = _OwnerRow(
                owner=owner,
                runtime=runtime,
                malloc=malloc,
                domain=domain,
                device_ordinal=device_ordinal,
                owner_id=owner_id,
                owner_role=owner_role,
                lock_witness=lock_witness,
            )
            if handoff is not None:
                handoff[0] = owner
            _OWNERS[id(owner)] = owner_row
            return owner
    except BaseException:
        if owner is not None:
            with _LOCK:
                if _OWNERS.get(id(owner)) is owner_row:
                    del _OWNERS[id(owner)]
            if handoff is not None and handoff[0] is owner:
                handoff[0] = None
        raise


def _owner_row(owner: object, path: str) -> _OwnerRow:
    if type(owner) is not HipAllocationOwnerV1:
        _error("hip_allocation_owner_invalid", path, "exact owner required")
    row = _OWNERS.get(id(owner))
    try:
        valid = (
            row is not None
            and row.owner is owner
            and owner._owner_id == row.owner_id
            and owner._lock is row.lock_witness
            and owner._owner_role_snapshot == row.owner_role
            and owner._runtime_domain_id_snapshot == _domain_id(row.domain)
            and owner._generation_snapshot == row.generation
            and owner._closed_snapshot is row.closed
            and type(row.successful_allocation_publication_count) is int
            and row.successful_allocation_publication_count >= 0
        )
    except AttributeError:
        valid = False
    if not valid or row is None:
        _error("hip_allocation_owner_invalid", path, "owner witness changed")
    return row


def _owner_identity_snapshot(owner: HipAllocationOwnerV1) -> tuple[object, ...]:
    try:
        snapshot = (
            owner._owner_id,
            id(owner._lock),
            owner._owner_role_snapshot,
            owner._runtime_domain_id_snapshot,
            owner._generation_snapshot,
            owner._closed_snapshot,
        )
    except AttributeError as exc:
        raise HipAllocationLineageError(
            "hip_allocation_owner_invalid", "owner", "owner fields missing"
        ) from exc
    if (
        type(snapshot[0]) is not int
        or snapshot[0] <= 0
        or type(snapshot[2]) is not str
        or type(snapshot[3]) is not str
        or type(snapshot[4]) is not int
        or snapshot[4] < 0
        or type(snapshot[5]) is not bool
    ):
        _error("hip_allocation_owner_invalid", "owner", "owner fields changed")
    return snapshot


def _validate_owner_identity_locked(owner: HipAllocationOwnerV1, path: str) -> None:
    if type(owner) is not HipAllocationOwnerV1:
        _error("hip_allocation_owner_invalid", path, "exact owner required")
    snapshot = _owner_identity_snapshot(owner)
    if owner._closed_snapshot:
        if _CLOSED_OWNERS.get(owner) != snapshot:
            _error("hip_allocation_owner_invalid", path, "closed witness changed")
    else:
        _owner_row(owner, path)


def _validate_runtime_owner(owner: HipAllocationOwnerV1, path: str) -> None:
    """Query runtime state outside the lineage registry lock."""

    with _LOCK:
        row = _owner_row(owner, path)
        runtime = row.runtime
        domain = row.domain
        device = row.device_ordinal
        representative = next(
            (
                candidate_runtime_ref()
                for candidate_runtime_ref, candidate_domain in _INJECTED_DOMAINS
                if candidate_domain is domain
            ),
            None,
        )
    if domain is _NATIVE_RUNTIME_DOMAIN:
        if type(runtime) is not _BoundHipContextRuntime:
            _error(
                "hip_allocation_runtime_invalid", path, "native runtime owner changed"
            )
        loaded = runtime.loaded_runtime
        if type(loaded) is not LoadedHipRuntime:
            _error("hip_allocation_runtime_invalid", path, "native provenance changed")
        try:
            provenance = loaded._loader_provenance_witness()
        except Exception as exc:
            raise HipAllocationLineageError(
                "hip_allocation_runtime_invalid", path, "native provenance changed"
            ) from exc
        if (
            getattr(runtime, "_loader_provenance_witness", None) is not provenance
            or runtime.device_ordinal != device
        ):
            _error("hip_allocation_device_mismatch", path, "runtime device changed")
        try:
            get_device = loaded.bind(
                "hipGetDevice", [ctypes.POINTER(ctypes.c_int)], ctypes.c_int
            )
            current = ctypes.c_int()
            status = get_device(ctypes.byref(current))
        except Exception as exc:
            raise HipAllocationLineageError(
                "hip_allocation_device_query_failed", path, type(exc).__name__
            ) from exc
        if status != 0 or current.value != device:
            _error("hip_allocation_device_mismatch", path, "HIP current device differs")
    else:
        if representative is not runtime:
            _error("hip_allocation_runtime_invalid", path, "injected domain changed")
        if getattr(runtime, "device_ordinal", None) != device:
            _error("hip_allocation_device_mismatch", path, "runtime device changed")
    with _LOCK:
        current_row = _owner_row(owner, path)
        if (
            current_row.runtime is not runtime
            or current_row.domain is not domain
            or current_row.device_ordinal != device
        ):
            _error("hip_allocation_runtime_invalid", path, "owner runtime changed")


def _owner_has_live_role(owner: HipAllocationOwnerV1, role: str) -> bool:
    return any(
        row.owner is owner
        and row.role == role
        and row.state not in {"freed", "quarantined"}
        for row in _ALLOCATIONS.values()
    )


def _finish_allocation_attempt(owner: HipAllocationOwnerV1, thread_id: int) -> None:
    with _LOCK:
        row = _OWNERS.get(id(owner))
        if row is not None and row.owner is owner:
            row.allocating_threads.discard(thread_id)


def _finish_allocation_attempt_reliably(
    owner: HipAllocationOwnerV1,
    thread_id: int,
) -> None:
    try:
        _finish_allocation_attempt(owner, thread_id)
    except BaseException:
        # A one-shot asynchronous interruption must not strand the owner or
        # replace the allocation/orphan result that the caller must receive.
        _finish_allocation_attempt(owner, thread_id)


def _reserve_orphan_locked(
    owner: _OwnerRow,
    role: str,
    nbytes: int,
    element_type: str,
) -> HipAllocationOrphanLeaseV1:
    global _NEXT_LEASE_ID
    lease_id = _NEXT_LEASE_ID
    lease: object | None = None
    try:
        lease = _issue(
            HipAllocationOrphanLeaseV1,
            {
                "lease_id": lease_id,
                "owner_identity": owner.owner_id,
                "runtime_domain": owner.domain,
                "runtime_domain_id": _domain_id(owner.domain),
                "device_ordinal": owner.device_ordinal,
                "role": role,
                "base": None,
                "pointer_snapshot": None,
                "nbytes": nbytes,
                "element_type": element_type,
                "evidence_scope": HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                "promotion_eligible": False,
            },
        )
        assert type(lease) is HipAllocationOrphanLeaseV1
        orphan = _OrphanRow(
            lease=lease,
            owner=owner.owner,
            domain=owner.domain,
            device_ordinal=owner.device_ordinal,
            role=role,
            nbytes=nbytes,
            element_type=element_type,
        )
        _ORPHANS[id(lease)] = orphan
        _NEXT_LEASE_ID = lease_id + 1
        return lease
    except BaseException:
        if type(lease) is HipAllocationOrphanLeaseV1:
            current = _ORPHANS.get(id(lease))
            if current is not None and current.lease is lease:
                del _ORPHANS[id(lease)]
        _NEXT_LEASE_ID = lease_id
        raise


def _discard_unallocated_orphan_locked(
    lease: HipAllocationOrphanLeaseV1,
) -> None:
    row = _ORPHANS.get(id(lease))
    if row is None or row.lease is not lease or row.state != "allocating":
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "pre-allocation orphan witness changed",
        )
    del _ORPHANS[id(lease)]


def _discard_unallocated_orphan_reliably_locked(
    lease: HipAllocationOrphanLeaseV1,
) -> None:
    try:
        _discard_unallocated_orphan_locked(lease)
    except BaseException:
        row = _ORPHANS.get(id(lease))
        if row is None:
            return
        if row.lease is lease and row.state == "allocating":
            del _ORPHANS[id(lease)]
            return
        raise


def _stage_orphan_locked(
    lease: HipAllocationOrphanLeaseV1,
    base: object,
    pointer: int | None,
    end: int | None,
) -> None:
    row = _ORPHANS.get(id(lease))
    if row is None or row.lease is not lease or row.state != "allocating":
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "orphan reservation changed",
        )
    object.__setattr__(lease, "base", base)
    object.__setattr__(lease, "pointer_snapshot", pointer)
    row.base = base
    row.pointer = pointer
    row.end = end
    row.state = "pending"
    row.lease_snapshot = _orphan_snapshot(lease, "orphan_lease")
    _detect_orphan_conflicts_locked(row)


def _force_orphan_pending_locked(
    lease: HipAllocationOrphanLeaseV1,
    base: object,
    pointer: int | None,
    end: int | None,
) -> None:
    """Finish the pre-reserved orphan without calling the staging seam."""

    row = _ORPHANS.get(id(lease))
    if (
        row is None
        or row.lease is not lease
        or row.state
        not in {
            "allocating",
            "pending",
        }
    ):
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "orphan reservation cannot be recovered",
        )
    if pointer is None:
        try:
            pointer = _pointer_snapshot(base, "orphan_lease.base")
        except HipAllocationLineageError:
            pointer = None
    object.__setattr__(lease, "base", base)
    object.__setattr__(lease, "pointer_snapshot", pointer)
    row.base = base
    row.pointer = pointer
    row.end = end
    row.state = "pending"
    row.lease_snapshot = _orphan_snapshot(lease, "orphan_lease")
    _detect_orphan_conflicts_locked(row)


def _emergency_orphan_pending_locked(
    lease: HipAllocationOrphanLeaseV1,
    base: object,
    pointer: int | None,
    end: int | None,
) -> None:
    """Allocation-free fallback when normal orphan snapshotting itself fails."""

    row = _ORPHANS.get(id(lease))
    if row is None or row.lease is not lease:
        # The pre-malloc reservation is the last fail-closed authority.  If it
        # was externally destroyed, there is no safe state transition left.
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "preallocated orphan reservation is missing",
        )
    object.__setattr__(lease, "base", base)
    object.__setattr__(lease, "pointer_snapshot", pointer)
    row.base = base
    row.pointer = pointer
    row.end = end
    row.state = "pending_unverified"
    row.lease_snapshot = None
    _detect_orphan_conflicts_locked(row)


def _emergency_orphan_pending_reliably_locked(
    lease: HipAllocationOrphanLeaseV1,
    base: object,
    pointer: int | None,
    end: int | None,
) -> None:
    try:
        _emergency_orphan_pending_locked(lease, base, pointer, end)
    except BaseException:
        row = _ORPHANS.get(id(lease))
        if row is None or row.lease is not lease:
            raise
        object.__setattr__(lease, "base", base)
        object.__setattr__(lease, "pointer_snapshot", pointer)
        row.base = base
        row.pointer = pointer
        row.end = end
        row.state = "pending_unverified"
        row.lease_snapshot = None
        row.conflicted = True


def _restore_orphan_pending_locked(
    lease: HipAllocationOrphanLeaseV1,
) -> None:
    row = _ORPHANS.get(id(lease))
    if row is None or row.lease is not lease:
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "orphan reservation is missing",
        )
    if row.state == "adopted":
        row.state = "pending"
    if row.state != "pending":
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "orphan cannot be restored to pending",
        )


def _mark_orphan_conflict_locked(
    lease: HipAllocationOrphanLeaseV1,
    *,
    overlapping_allocation: _AllocationRow | None = None,
) -> None:
    orphan = _ORPHANS.get(id(lease))
    if (
        orphan is None
        or orphan.lease is not lease
        or orphan.state != "pending"
        or orphan.pointer is None
    ):
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "overlap conflict has no pending orphan witness",
        )
    orphan.conflicted = True
    if overlapping_allocation is not None:
        _poison_allocation_row_locked(overlapping_allocation)
    _append_quarantine_locked(
        _domain_id(orphan.domain),
        orphan.device_ordinal,
        orphan.pointer,
        orphan.end,
    )


def _poison_allocation_row_locked(allocation: _AllocationRow) -> None:
    state_map = {
        "live": "poisoned",
        "borrowed": "poisoned_borrowed",
        "borrow_reserving": "poisoned_borrow_reserving",
        "free_pending": "poisoned_free_pending",
        "free_reserving": "poisoned_free_reserving",
    }
    replacement = state_map.get(allocation.state)
    if replacement is not None:
        allocation.state = replacement


def _poison_domain_locked(domain: object, device_ordinal: int) -> None:
    domain_id = _domain_id(domain)
    domain._poisoned_devices[device_ordinal] = True
    for allocation in _ALLOCATIONS.values():
        if allocation.domain is domain and allocation.device_ordinal == device_ordinal:
            _poison_allocation_row_locked(allocation)
    for orphan in _ORPHANS.values():
        if orphan.domain is domain and orphan.device_ordinal == device_ordinal:
            orphan.conflicted = True
    _POISONED_DOMAINS.add((domain_id, device_ordinal))


def _allocation_domain_is_poisoned_locked(allocation: _AllocationRow) -> bool:
    return (
        allocation.domain.is_device_poisoned(allocation.device_ordinal)
        or (
            _domain_id(allocation.domain),
            allocation.device_ordinal,
        )
        in _POISONED_DOMAINS
    )


def _detect_orphan_conflicts_locked(orphan: _OrphanRow) -> None:
    """Mark conflicts before any fallible publication work can continue."""

    if orphan.pointer is None:
        return
    orphan_end = orphan.end if orphan.end is not None else _UINTPTR_MAX + 1
    domain_id = _domain_id(orphan.domain)
    for allocation in _ALLOCATIONS.values():
        if (
            allocation.domain is orphan.domain
            and allocation.device_ordinal == orphan.device_ordinal
            and orphan.pointer < allocation.end
            and allocation.pointer < orphan_end
        ):
            orphan.conflicted = True
            _poison_allocation_row_locked(allocation)
    for quarantined in _QUARANTINED_RANGES:
        quarantine_end = (
            quarantined.end if quarantined.end is not None else _UINTPTR_MAX + 1
        )
        if (
            quarantined.runtime_domain_id == domain_id
            and quarantined.device_ordinal == orphan.device_ordinal
            and orphan.pointer < quarantine_end
            and quarantined.pointer < orphan_end
        ):
            orphan.conflicted = True
    for other in _ORPHANS.values():
        if (
            other is not orphan
            and other.state
            in {"allocating", "pending", "pending_unverified", "quarantined"}
            and other.domain is orphan.domain
            and other.device_ordinal == orphan.device_ordinal
            and other.pointer is not None
        ):
            other_end = other.end if other.end is not None else _UINTPTR_MAX + 1
            if orphan.pointer < other_end and other.pointer < orphan_end:
                orphan.conflicted = True
                other.conflicted = True


def _resolve_orphan_adopted_locked(
    lease: HipAllocationOrphanLeaseV1,
) -> None:
    row = _ORPHANS.get(id(lease))
    if row is None or row.lease is not lease or row.state != "pending":
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "orphan is not pending publication",
        )
    row.state = "adopted"


def _publish_allocation_transaction(
    owner: HipAllocationOwnerV1,
    thread_id: int,
    orphan_lease: HipAllocationOrphanLeaseV1,
    allocation_role: str,
    base: object,
    pointer: int,
    end: int,
    extent: int,
    element_type: str,
    handoff_capability: list[HipAllocationCapabilityV1 | None],
    *,
    _control_token: object | None = None,
) -> HipAllocationCapabilityV1:
    """Publish or roll back one allocation while the publication lock is held."""

    allocation_row: _AllocationRow | None = None
    generation_key: tuple[str, int] | None = None
    previous_high: int | None = None
    previous_owner_generation: int | None = None
    previous_owner_publication_count: int | None = None
    allocation_id: int | None = None
    try:
        with _LOCK:
            owner_row = _owner_row(owner, "owner")
            _require_owner_control_locked(
                owner_row,
                _control_token,
                allocation_role=allocation_role,
            )
            if thread_id not in owner_row.allocating_threads:
                _error(
                    "hip_allocation_transaction_changed",
                    "allocation",
                    "allocator transaction witness changed",
                )
            if owner_row.closed:
                _error("hip_allocation_owner_closed", "owner", "owner is closed")
            if (
                owner_row.domain.is_device_poisoned(owner_row.device_ordinal)
                or (
                    _domain_id(owner_row.domain),
                    owner_row.device_ordinal,
                )
                in _POISONED_DOMAINS
            ):
                _error(
                    "hip_allocation_domain_poisoned",
                    "owner",
                    "allocator outcome for this runtime/device is unresolved",
                )
            if _owner_has_live_role(owner, allocation_role):
                _error(
                    "hip_allocation_role_live",
                    "allocation.role",
                    "role became live during malloc",
                )
            current_orphan = _ORPHANS.get(id(orphan_lease))
            if (
                current_orphan is None
                or current_orphan.lease is not orphan_lease
                or current_orphan.state != "pending"
            ):
                _error(
                    "hip_allocation_orphan_invalid",
                    "orphan_lease",
                    "publication orphan witness changed",
                )
            if current_orphan.conflicted:
                _mark_orphan_conflict_locked(orphan_lease)
                _error(
                    "hip_allocation_range_overlap",
                    "allocation.base",
                    "allocator result was previously marked as overlapping",
                )
            for active in _ALLOCATIONS.values():
                if (
                    active.state != "freed"
                    and active.domain is owner_row.domain
                    and active.device_ordinal == owner_row.device_ordinal
                    and pointer < active.end
                    and active.pointer < end
                ):
                    _mark_orphan_conflict_locked(
                        orphan_lease,
                        overlapping_allocation=active,
                    )
                    _error(
                        "hip_allocation_range_overlap",
                        "allocation.base",
                        "range overlaps a live or quarantined allocation",
                    )
            domain_id = _domain_id(owner_row.domain)
            for quarantined in _QUARANTINED_RANGES:
                if (
                    quarantined.runtime_domain_id == domain_id
                    and quarantined.device_ordinal == owner_row.device_ordinal
                    and pointer
                    < (
                        quarantined.end
                        if quarantined.end is not None
                        else _UINTPTR_MAX + 1
                    )
                    and quarantined.pointer < end
                ):
                    _mark_orphan_conflict_locked(orphan_lease)
                    _error(
                        "hip_allocation_range_overlap",
                        "allocation.base",
                        "range overlaps a quarantined allocation tombstone",
                    )
            for orphan in _ORPHANS.values():
                if (
                    orphan.lease is not orphan_lease
                    and orphan.state in {"pending", "quarantined"}
                    and orphan.domain is owner_row.domain
                    and orphan.device_ordinal == owner_row.device_ordinal
                    and orphan.pointer is not None
                    and pointer
                    < (orphan.end if orphan.end is not None else _UINTPTR_MAX + 1)
                    and orphan.pointer < end
                ):
                    orphan.conflicted = True
                    _mark_orphan_conflict_locked(orphan_lease)
                    _error(
                        "hip_allocation_range_overlap",
                        "allocation.base",
                        "range overlaps an unresolved allocation orphan",
                    )
            global _NEXT_ALLOCATION_ID
            allocation_id = _NEXT_ALLOCATION_ID
            generation_key = (
                _domain_id(owner_row.domain),
                owner_row.device_ordinal,
            )
            previous_high = _HIGH_WATER.get(generation_key)
            previous_owner_generation = owner_row.generation
            previous_owner_publication_count = (
                owner_row.successful_allocation_publication_count
            )
            generation = max(owner_row.generation, previous_high or 0) + 1
            capability = _issue(
                HipAllocationCapabilityV1,
                {
                    "allocation_id": allocation_id,
                    "role": allocation_role,
                    "base": base,
                    "pointer_snapshot": pointer,
                    "nbytes": extent,
                    "element_type": element_type,
                    "generation": generation,
                    "owner_identity": owner_row.owner_id,
                    "runtime_owner": owner_row.runtime,
                    "runtime_domain": owner_row.domain,
                    "runtime_domain_id": _domain_id(owner_row.domain),
                    "device_ordinal": owner_row.device_ordinal,
                    "evidence_scope": HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                    "promotion_eligible": False,
                },
            )
            assert type(capability) is HipAllocationCapabilityV1
            snapshot = _capability_snapshot(capability, "capability")
            allocation_row = _AllocationRow(
                capability=capability,
                owner=owner,
                domain=owner_row.domain,
                device_ordinal=owner_row.device_ordinal,
                pointer=pointer,
                end=end,
                base=base,
                nbytes=extent,
                element_type=element_type,
                role=allocation_role,
                generation=generation,
                capability_snapshot=snapshot,
            )
            _ALLOCATIONS[id(capability)] = allocation_row
            _HIGH_WATER[generation_key] = generation
            owner_row.generation = generation
            object.__setattr__(owner, "_generation_snapshot", generation)
            owner_row.successful_allocation_publication_count = (
                previous_owner_publication_count + 1
            )
            _resolve_orphan_adopted_locked(orphan_lease)
            _NEXT_ALLOCATION_ID += 1
            owner_row.allocating_threads.discard(thread_id)
            handoff_capability[0] = capability
            del _ORPHANS[id(orphan_lease)]
            return capability
    except BaseException as exc:
        if handoff_capability[0] is not None and allocation_row is not None:
            with _LOCK:
                current_owner = _OWNERS.get(id(owner))
                if current_owner is not None and current_owner.owner is owner:
                    current_owner.allocating_threads.discard(thread_id)
                current_orphan = _ORPHANS.get(id(orphan_lease))
                if current_orphan is not None and current_orphan.lease is orphan_lease:
                    del _ORPHANS[id(orphan_lease)]
            return allocation_row.capability
        rollback_failed = False
        with _LOCK:
            try:
                if allocation_row is not None:
                    current = _ALLOCATIONS.get(id(allocation_row.capability))
                    if current is allocation_row:
                        del _ALLOCATIONS[id(allocation_row.capability)]
                if generation_key is not None:
                    if previous_high is None:
                        _HIGH_WATER.pop(generation_key, None)
                    else:
                        _HIGH_WATER[generation_key] = previous_high
                current_owner = _OWNERS.get(id(owner))
                if (
                    current_owner is not None
                    and current_owner.owner is owner
                    and previous_owner_generation is not None
                ):
                    if previous_owner_publication_count is not None:
                        _restore_owner_publication_count_reliably_locked(
                            current_owner,
                            previous_owner_publication_count,
                        )
                    current_owner.generation = previous_owner_generation
                    object.__setattr__(
                        owner,
                        "_generation_snapshot",
                        previous_owner_generation,
                    )
                if allocation_id is not None and _NEXT_ALLOCATION_ID > allocation_id:
                    _NEXT_ALLOCATION_ID = allocation_id
                _restore_orphan_pending_locked(orphan_lease)
            except BaseException:
                rollback_failed = True
        if isinstance(exc, HipAllocationLineageError):
            code, error_path, message = exc.code, exc.path, exc.message
        else:
            code = "hip_allocation_publish_failed"
            error_path = "allocation.publish"
            message = type(exc).__name__
        if rollback_failed:
            code = "hip_allocation_publish_rollback_failed"
        raise HipAllocationLineageError(
            code,
            error_path,
            message,
            orphaned_pointer=base,
            orphan_cleanup_lease=orphan_lease,
        ) from exc


def _restore_owner_publication_count_reliably_locked(
    owner_row: _OwnerRow,
    publication_count: int,
) -> None:
    try:
        owner_row.successful_allocation_publication_count = publication_count
    except BaseException:
        # One-shot trace/profiler interruption may fire before or immediately
        # after STORE_ATTR.  Repeating the same exact restore converges both.
        owner_row.successful_allocation_publication_count = publication_count


def _allocate(
    owner: HipAllocationOwnerV1,
    role: object,
    nbytes: object,
    element_type: object,
    *,
    _control_token: object | None = None,
) -> HipAllocationCapabilityV1:
    allocation_role = _nonempty_string(role, "allocation.role")
    extent, alignment = _allocation_extent(nbytes, element_type, "allocation")
    thread_id = threading.get_ident()
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(
            owner_row,
            _control_token,
            allocation_role=allocation_role,
        )
        if owner_row.closed:
            _error("hip_allocation_owner_closed", "owner", "owner is closed")
        if (
            owner_row.domain.is_device_poisoned(owner_row.device_ordinal)
            or (
                _domain_id(owner_row.domain),
                owner_row.device_ordinal,
            )
            in _POISONED_DOMAINS
        ):
            _error(
                "hip_allocation_domain_poisoned",
                "owner",
                "allocator outcome for this runtime/device is unresolved",
            )
        if thread_id in owner_row.allocating_threads:
            _error(
                "hip_allocation_reentrant",
                "allocation",
                "same-thread allocator reentry is forbidden",
            )
        if _owner_has_live_role(owner, allocation_role):
            _error(
                "hip_allocation_role_live",
                "allocation.role",
                "owner already has a live allocation for this role",
            )
        owner_row.activity_started = True
        orphan_lease = _reserve_orphan_locked(
            owner_row,
            allocation_role,
            extent,
            element_type,
        )
        try:
            owner_row.allocating_threads.add(thread_id)
            malloc = owner_row.malloc
        except BaseException:
            _discard_unallocated_orphan_reliably_locked(orphan_lease)
            owner_row.allocating_threads.discard(thread_id)
            raise

    handoff_capability: list[HipAllocationCapabilityV1 | None] = [None]
    try:
        _validate_runtime_owner(owner, "owner")
    except BaseException:
        try:
            with _LOCK:
                _discard_unallocated_orphan_reliably_locked(orphan_lease)
        finally:
            _finish_allocation_attempt_reliably(owner, thread_id)
        raise

    base: object | None = None
    try:
        try:
            base = malloc(extent)  # type: ignore[operator]
        except Exception as exc:
            with _LOCK:
                _discard_unallocated_orphan_reliably_locked(orphan_lease)
            raise HipAllocationLineageError(
                "hip_allocation_malloc_failed",
                "allocation.malloc",
                type(exc).__name__,
            ) from exc
        except BaseException as exc:
            bookkeeping_error: BaseException | None = None
            with _LOCK:
                try:
                    _emergency_orphan_pending_reliably_locked(
                        orphan_lease,
                        None,
                        None,
                        None,
                    )
                    current_owner = _owner_row(owner, "owner")
                    _poison_domain_locked(
                        current_owner.domain,
                        current_owner.device_ordinal,
                    )
                except BaseException as bookkeeping_exc:
                    bookkeeping_error = bookkeeping_exc
            raise HipAllocationLineageError(
                "hip_allocation_malloc_outcome_uncertain",
                "allocation.malloc",
                (
                    type(exc).__name__
                    if bookkeeping_error is None
                    else f"{type(exc).__name__}/{type(bookkeeping_error).__name__}"
                ),
                orphaned_pointer=None,
                orphan_cleanup_lease=orphan_lease,
            ) from (bookkeeping_error or exc)
        pointer: int | None = None
        end: int | None = None
        try:
            pointer = _pointer_snapshot(base, "allocation.base")
            try:
                end = _range_end(pointer, extent, "allocation")
            except HipAllocationLineageError:
                with _LOCK:
                    _stage_orphan_locked(orphan_lease, base, pointer, None)
                raise
            with _LOCK:
                _stage_orphan_locked(orphan_lease, base, pointer, end)
            if pointer % alignment != 0:
                _error(
                    "hip_allocation_alignment_invalid",
                    "allocation.base",
                    f"{element_type} base requires {alignment}-byte alignment",
                )
        except BaseException as exc:
            with _LOCK:
                try:
                    _force_orphan_pending_locked(
                        orphan_lease,
                        base,
                        pointer,
                        end,
                    )
                except BaseException:
                    _emergency_orphan_pending_reliably_locked(
                        orphan_lease,
                        base,
                        pointer,
                        end,
                    )
            if isinstance(exc, HipAllocationLineageError):
                code, error_path, message = exc.code, exc.path, exc.message
            else:
                code = "hip_allocation_orphan_stage_failed"
                error_path = "allocation.orphan"
                message = type(exc).__name__
            raise HipAllocationLineageError(
                code,
                error_path,
                message,
                orphaned_pointer=base,
                orphan_cleanup_lease=orphan_lease,
            ) from exc

        try:
            _validate_runtime_owner(owner, "owner")
        except BaseException as exc:
            if isinstance(exc, HipAllocationLineageError):
                code, error_path, message = exc.code, exc.path, exc.message
            else:
                code = "hip_allocation_runtime_validation_failed"
                error_path = "allocation.runtime"
                message = type(exc).__name__
            raise HipAllocationLineageError(
                code,
                error_path,
                message,
                orphaned_pointer=base,
                orphan_cleanup_lease=orphan_lease,
            ) from exc

        published: HipAllocationCapabilityV1 | None = None
        try:
            with _PUBLICATION_LOCK:
                assert pointer is not None
                assert end is not None
                published = _publish_allocation_transaction(
                    owner,
                    thread_id,
                    orphan_lease,
                    allocation_role,
                    base,
                    pointer,
                    end,
                    extent,
                    element_type,
                    handoff_capability,
                    _control_token=_control_token,
                )
            return published
        except HipAllocationLineageError:
            if published is not None:
                return published
            if handoff_capability[0] is not None:
                return handoff_capability[0]
            raise
        except BaseException as exc:
            if published is not None:
                return published
            if handoff_capability[0] is not None:
                return handoff_capability[0]
            raise HipAllocationLineageError(
                "hip_allocation_publish_lock_failed",
                "allocation.publish",
                type(exc).__name__,
                orphaned_pointer=base,
                orphan_cleanup_lease=orphan_lease,
            ) from exc
    finally:
        if handoff_capability[0] is None:
            _finish_allocation_attempt_reliably(owner, thread_id)


def _capability_snapshot(capability: object, path: str) -> tuple[object, ...]:
    if type(capability) is not HipAllocationCapabilityV1:
        _error("hip_allocation_capability_invalid", path, "exact capability required")
    try:
        pointer = _pointer_snapshot(capability.base, f"{path}.base")
        extent, alignment = _allocation_extent(
            capability.nbytes,
            capability.element_type,
            path,
        )
        if pointer % alignment != 0:
            _error("hip_allocation_capability_invalid", path, "base alignment changed")
        _range_end(pointer, extent, path)
        snapshot = (
            capability.allocation_id,
            capability.role,
            id(capability.base),
            pointer,
            capability.pointer_snapshot,
            capability.nbytes,
            capability.element_type,
            capability.generation,
            capability.owner_identity,
            id(capability.runtime_owner),
            id(capability.runtime_domain),
            capability.runtime_domain_id,
            capability.device_ordinal,
            capability.evidence_scope,
            capability.promotion_eligible,
        )
    except AttributeError as exc:
        raise HipAllocationLineageError(
            "hip_allocation_capability_invalid", path, "capability fields missing"
        ) from exc
    if (
        type(snapshot[0]) is not int
        or snapshot[0] <= 0
        or type(snapshot[1]) is not str
        or snapshot[4] != pointer
        or type(snapshot[7]) is not int
        or snapshot[7] <= 0
        or type(snapshot[8]) is not int
        or type(snapshot[11]) is not str
        or type(snapshot[12]) is not int
        or snapshot[12] < 0
        or snapshot[13] != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1
        or snapshot[14] is not False
    ):
        _error("hip_allocation_capability_invalid", path, "fields changed")
    return snapshot


def _capability_row(capability: object, path: str) -> _AllocationRow:
    snapshot = _capability_snapshot(capability, path)
    row = _ALLOCATIONS.get(id(capability))
    if (
        row is None
        or row.capability is not capability
        or row.capability_snapshot != snapshot
    ):
        _error("hip_allocation_capability_invalid", path, "registry witness changed")
    owner = _owner_row(row.owner, f"{path}.owner")
    if (
        capability.owner_identity != owner.owner_id
        or capability.runtime_owner is not owner.runtime
        or capability.runtime_domain is not row.domain
        or capability.runtime_domain_id != _domain_id(row.domain)
        or capability.device_ordinal != row.device_ordinal
        or capability.pointer_snapshot != row.pointer
        or capability.base is not row.base
        or capability.nbytes != row.nbytes
        or capability.element_type != row.element_type
        or capability.role != row.role
        or capability.generation != row.generation
    ):
        _error("hip_allocation_capability_invalid", path, "lineage fields changed")
    if _allocation_domain_is_poisoned_locked(row):
        _poison_allocation_row_locked(row)
    return row


def _capability_matches_private_row(row: _AllocationRow) -> bool:
    try:
        return (
            _capability_snapshot(row.capability, "capability")
            == row.capability_snapshot
        )
    except BaseException:
        return False


def _rollback_borrow_reservation_locked(
    lease: HipAllocationBorrowLeaseV1,
    witness: _BorrowRow,
    rows: tuple[_AllocationRow, ...],
) -> None:
    if _BORROWS.get(id(lease)) is witness:
        del _BORROWS[id(lease)]
    for row in rows:
        if _ALLOCATIONS.get(id(row.capability)) is not row:
            continue
        if (
            row.state
            in {
                "borrow_reserving",
                "borrowed",
                "live",
            }
            and _capability_matches_private_row(row)
            and not _allocation_domain_is_poisoned_locked(row)
        ):
            row.state = "live"
        else:
            row.state = "poisoned"
        row.borrow_lease = None


def _require_controlled_borrower_locked(
    rows: tuple[_AllocationRow, ...],
    borrower: object,
) -> None:
    checked_owners: list[HipAllocationOwnerV1] = []
    for row in rows:
        if any(existing is row.owner for existing in checked_owners):
            continue
        checked_owners.append(row.owner)
        owner_row = _owner_row(row.owner, "capabilities.owner")
        if owner_row.control is not None:
            _require_owner_control_locked(owner_row, borrower)


def _commit_borrow_reservation_locked(
    lease: HipAllocationBorrowLeaseV1,
    witness: _BorrowRow,
    capabilities: tuple[HipAllocationCapabilityV1, ...],
    rows: tuple[_AllocationRow, ...],
) -> None:
    _require_controlled_borrower_locked(rows, witness.borrower)
    if _BORROWS.get(id(lease)) is not witness:
        _error(
            "hip_allocation_borrow_invalid",
            "capabilities",
            "borrow reservation changed",
        )
    if _borrow_snapshot(lease, "lease") != witness.lease_snapshot:
        _error(
            "hip_allocation_borrow_invalid",
            "lease",
            "lease changed during runtime validation",
        )
    for index, (capability, expected) in enumerate(
        zip(capabilities, rows, strict=True)
    ):
        current = _capability_row(capability, f"capabilities.{index}")
        if current is not expected:
            _error(
                "hip_allocation_borrow_invalid",
                f"capabilities.{index}",
                "capability row changed during runtime validation",
            )
    if any(row.state == "poisoned_borrow_reserving" for row in rows):
        _error(
            "hip_allocation_borrow_poisoned",
            "capabilities",
            "allocation domain was poisoned during borrow reservation",
        )
    if any(
        row.state != "borrow_reserving" or row.borrow_lease is not lease for row in rows
    ):
        _error(
            "hip_allocation_borrow_invalid",
            "capabilities",
            "borrow reservation changed",
        )
    for row in rows:
        row.state = "borrowed"


def _commit_borrow_reservation(
    lease: HipAllocationBorrowLeaseV1,
    witness: _BorrowRow,
    capabilities: tuple[HipAllocationCapabilityV1, ...],
    rows: tuple[_AllocationRow, ...],
) -> None:
    """Keep the caller handoff trace point outside the registry lock."""

    with _LOCK:
        _commit_borrow_reservation_locked(
            lease,
            witness,
            capabilities,
            rows,
        )


def _borrow(
    capabilities: object,
    borrower: object,
) -> HipAllocationBorrowLeaseV1:
    if type(capabilities) is not tuple or not capabilities:
        _error(
            "hip_allocation_borrow_group_invalid",
            "capabilities",
            "borrow group must be a nonempty exact tuple",
        )
    if borrower is None:
        _error(
            "hip_allocation_borrow_invalid",
            "borrower",
            "process-local borrower identity is required",
        )
    if any(type(value) is not HipAllocationCapabilityV1 for value in capabilities):
        _error(
            "hip_allocation_borrow_type_invalid",
            "capabilities",
            "every group item must be an exact capability type",
        )
    if len({id(value) for value in capabilities}) != len(capabilities):
        _error(
            "hip_allocation_borrow_duplicate",
            "capabilities",
            "capabilities must be unique",
        )

    with _LOCK:
        rows = tuple(
            _capability_row(value, f"capabilities.{index}")
            for index, value in enumerate(capabilities)
        )
        _require_controlled_borrower_locked(rows, borrower)
        if any(row.state != "live" for row in rows):
            _error(
                "hip_allocation_borrow_busy",
                "capabilities",
                "an allocation is already borrowed or pending free",
            )
        domain = rows[0].domain
        device = rows[0].device_ordinal
        if any(
            row.domain is not domain or row.device_ordinal != device for row in rows
        ):
            _error(
                "hip_allocation_borrow_domain_mismatch",
                "capabilities",
                "atomic borrow requires one runtime domain and device",
            )
        owners: list[HipAllocationOwnerV1] = []
        for row in rows:
            if all(existing is not row.owner for existing in owners):
                owners.append(row.owner)
        global _NEXT_LEASE_ID
        lease_id = _NEXT_LEASE_ID
        lease = _issue(
            HipAllocationBorrowLeaseV1,
            {
                "lease_id": lease_id,
                "capabilities": capabilities,
                "borrower": borrower,
                "runtime_domain": domain,
                "device_ordinal": device,
                "evidence_scope": HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                "promotion_eligible": False,
            },
        )
        assert type(lease) is HipAllocationBorrowLeaseV1
        witness = _BorrowRow(
            lease=lease,
            allocation_ids=tuple(id(row.capability) for row in rows),
            lease_snapshot=_borrow_snapshot(lease, "lease"),
            borrower=borrower,
        )
        try:
            for row in rows:
                row.state = "borrow_reserving"
                row.borrow_lease = lease
            _BORROWS[id(lease)] = witness
            _NEXT_LEASE_ID = lease_id + 1
        except BaseException:
            _rollback_borrow_reservation_locked(lease, witness, rows)
            _NEXT_LEASE_ID = lease_id
            raise
    try:
        for owner in owners:
            _validate_runtime_owner(owner, "capabilities.owner")
    except BaseException:
        with _LOCK:
            _rollback_borrow_reservation_locked(lease, witness, rows)
        raise
    try:
        _commit_borrow_reservation(
            lease,
            witness,
            capabilities,
            rows,
        )
        return lease
    except BaseException:
        with _LOCK:
            _rollback_borrow_reservation_locked(lease, witness, rows)
        raise


def _borrow_snapshot(lease: object, path: str) -> tuple[object, ...]:
    if type(lease) is not HipAllocationBorrowLeaseV1:
        _error("hip_allocation_borrow_invalid", path, "exact lease required")
    try:
        capabilities = lease.capabilities
        snapshot = (
            lease.lease_id,
            id(capabilities),
            tuple(id(value) for value in capabilities),
            id(lease.borrower),
            id(lease.runtime_domain),
            lease.device_ordinal,
            lease.evidence_scope,
            lease.promotion_eligible,
        )
    except (AttributeError, TypeError) as exc:
        raise HipAllocationLineageError(
            "hip_allocation_borrow_invalid", path, "lease fields missing"
        ) from exc
    if (
        type(capabilities) is not tuple
        or not capabilities
        or any(type(value) is not HipAllocationCapabilityV1 for value in capabilities)
        or type(snapshot[0]) is not int
        or snapshot[0] <= 0
        or type(snapshot[5]) is not int
        or snapshot[5] < 0
        or snapshot[6] != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1
        or snapshot[7] is not False
    ):
        _error("hip_allocation_borrow_invalid", path, "lease fields changed")
    return snapshot


def _borrow_row(
    lease: object,
    path: str,
    *,
    require_active: bool,
    allow_poisoned: bool = False,
) -> _BorrowRow:
    snapshot = _borrow_snapshot(lease, path)
    row = _BORROWS.get(id(lease))
    if (
        row is None
        or row.lease is not lease
        or row.lease_snapshot != snapshot
        or lease.borrower is not row.borrower
    ):
        _error("hip_allocation_borrow_invalid", path, "lease witness changed")
    if row.released:
        if require_active:
            _error("hip_allocation_borrow_released", path, "lease is released")
        return row
    if len(row.allocation_ids) != len(lease.capabilities):
        _error("hip_allocation_borrow_invalid", path, "allocation set changed")
    for allocation_id, capability in zip(
        row.allocation_ids, lease.capabilities, strict=True
    ):
        allocation = _ALLOCATIONS.get(allocation_id)
        if (
            allocation is None
            or allocation.capability is not capability
            or allocation.state
            not in (
                {"borrowed", "poisoned_borrowed"} if allow_poisoned else {"borrowed"}
            )
            or allocation.borrow_lease is not lease
        ):
            _error("hip_allocation_borrow_invalid", path, "borrow state changed")
        _capability_row(capability, f"{path}.capability")
        _owner_row(allocation.owner, f"{path}.owner")
    return row


def _complete_borrow_release_locked(
    lease: HipAllocationBorrowLeaseV1,
    snapshot: tuple[object, ...],
) -> None:
    row = _BORROWS.get(id(lease))
    if row is None:
        return
    if (
        row.lease is not lease
        or row.lease_snapshot != snapshot
        or len(row.allocation_ids) != len(lease.capabilities)
    ):
        _error(
            "hip_allocation_borrow_invalid",
            "lease",
            "released borrow registry witness changed",
        )
    for allocation_id, capability in zip(
        row.allocation_ids, lease.capabilities, strict=True
    ):
        allocation = _ALLOCATIONS.get(allocation_id)
        if allocation is None or allocation.capability is not capability:
            continue
        if (
            allocation.state
            in {
                "borrowed",
                "borrow_reserving",
                "live",
            }
            and _capability_matches_private_row(allocation)
            and not _allocation_domain_is_poisoned_locked(allocation)
        ):
            allocation.state = "live"
        else:
            allocation.state = "poisoned"
        allocation.borrow_lease = None
    row.released = True
    del _BORROWS[id(lease)]


def _release_borrow(lease: object) -> None:
    snapshot = _borrow_snapshot(lease, "lease")
    with _LOCK:
        released = _RELEASED_BORROWS.get(lease)
        if released is not None:
            if released != snapshot:
                _error(
                    "hip_allocation_borrow_invalid",
                    "lease",
                    "released lease fields changed",
                )
            _complete_borrow_release_locked(lease, snapshot)
            return
        row = _BORROWS.get(id(lease))
        if row is None or row.lease is not lease or row.lease_snapshot != snapshot:
            _error("hip_allocation_borrow_invalid", "lease", "lease witness changed")
        if row.released:
            return
        if len(row.allocation_ids) != len(lease.capabilities):
            _error(
                "hip_allocation_borrow_invalid",
                "lease",
                "allocation set changed",
            )
        for allocation_id, capability in zip(
            row.allocation_ids, lease.capabilities, strict=True
        ):
            allocation = _ALLOCATIONS.get(allocation_id)
            if (
                allocation is None
                or allocation.capability is not capability
                or allocation.state not in {"borrowed", "poisoned_borrowed"}
                or allocation.borrow_lease is not lease
            ):
                _error(
                    "hip_allocation_borrow_invalid",
                    "lease",
                    "borrow cleanup witness changed",
                )
            _owner_row(allocation.owner, "lease.owner")
        _RELEASED_BORROWS[lease] = snapshot
        _complete_borrow_release_locked(lease, snapshot)


def _rollback_free_reservation_locked(
    lease: HipAllocationFreeLeaseV1,
    free_row: _FreeRow,
    allocation: _AllocationRow,
) -> None:
    if _FREES.get(id(lease)) is free_row:
        del _FREES[id(lease)]
    if _ALLOCATIONS.get(id(allocation.capability)) is not allocation:
        return
    if (
        allocation.state
        in {
            "free_reserving",
            "free_pending",
            "live",
        }
        and _capability_matches_private_row(allocation)
        and not _allocation_domain_is_poisoned_locked(allocation)
    ):
        allocation.state = "live"
    else:
        allocation.state = "poisoned"
    allocation.free_lease = None


def _commit_free_reservation_locked(
    lease: HipAllocationFreeLeaseV1,
    free_row: _FreeRow,
    allocation: _AllocationRow,
    capability: object,
    *,
    _control_token: object | None = None,
) -> None:
    owner_row = _owner_row(free_row.owner, "owner")
    _require_owner_control_locked(owner_row, _control_token)
    if _FREES.get(id(lease)) is not free_row:
        _error(
            "hip_allocation_free_invalid",
            "capability",
            "free reservation changed",
        )
    if _free_snapshot(lease, "lease") != free_row.lease_snapshot:
        _error(
            "hip_allocation_free_invalid",
            "lease",
            "lease changed during runtime validation",
        )
    current = _capability_row(capability, "capability")
    if current is not allocation:
        _error(
            "hip_allocation_free_invalid",
            "capability",
            "capability row changed during runtime validation",
        )
    if allocation.state == "poisoned_free_reserving" and allocation.free_lease is lease:
        _error(
            "hip_allocation_free_poisoned",
            "capability",
            "allocation domain was poisoned during free reservation",
        )
    if allocation.state != "free_reserving" or allocation.free_lease is not lease:
        _error(
            "hip_allocation_free_invalid",
            "capability",
            "free reservation changed",
        )
    allocation.state = "free_pending"


def _commit_free_reservation(
    lease: HipAllocationFreeLeaseV1,
    free_row: _FreeRow,
    allocation: _AllocationRow,
    capability: object,
    *,
    _control_token: object | None = None,
) -> None:
    """Keep the caller handoff trace point outside the registry lock."""

    with _LOCK:
        _commit_free_reservation_locked(
            lease,
            free_row,
            allocation,
            capability,
            _control_token=_control_token,
        )


def _begin_free(
    owner: HipAllocationOwnerV1,
    capability: object,
    *,
    _control_token: object | None = None,
) -> HipAllocationFreeLeaseV1:
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(owner_row, _control_token)
        if owner_row.closed:
            _error("hip_allocation_owner_closed", "owner", "owner is closed")
        allocation = _capability_row(capability, "capability")
        if allocation.owner is not owner:
            _error("hip_allocation_foreign", "capability", "belongs to another owner")
        if allocation.state != "live":
            _error(
                "hip_allocation_free_busy",
                "capability",
                "allocation is borrowed, pending, freed, or quarantined",
            )
        global _NEXT_LEASE_ID
        lease_id = _NEXT_LEASE_ID
        lease = _issue(
            HipAllocationFreeLeaseV1,
            {
                "lease_id": lease_id,
                "capability": capability,
                "owner_identity": owner_row.owner_id,
                "pointer_snapshot": allocation.pointer,
                "runtime_domain": allocation.domain,
                "runtime_domain_id": _domain_id(allocation.domain),
                "device_ordinal": allocation.device_ordinal,
                "evidence_scope": HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                "promotion_eligible": False,
            },
        )
        assert type(lease) is HipAllocationFreeLeaseV1
        free_row = _FreeRow(
            lease=lease,
            allocation_id=id(capability),
            lease_snapshot=_free_snapshot(lease, "lease"),
            owner=owner,
        )
        try:
            allocation.state = "free_reserving"
            allocation.free_lease = lease
            _FREES[id(lease)] = free_row
            _NEXT_LEASE_ID = lease_id + 1
        except BaseException:
            _rollback_free_reservation_locked(lease, free_row, allocation)
            _NEXT_LEASE_ID = lease_id
            raise
    try:
        _validate_runtime_owner(owner, "capability.owner")
    except BaseException:
        with _LOCK:
            _rollback_free_reservation_locked(lease, free_row, allocation)
        raise
    try:
        _commit_free_reservation(
            lease,
            free_row,
            allocation,
            capability,
            _control_token=_control_token,
        )
        return lease
    except BaseException:
        with _LOCK:
            _rollback_free_reservation_locked(lease, free_row, allocation)
        raise


def _free_snapshot(lease: object, path: str) -> tuple[object, ...]:
    if type(lease) is not HipAllocationFreeLeaseV1:
        _error("hip_allocation_free_invalid", path, "exact free lease required")
    try:
        snapshot = (
            lease.lease_id,
            id(lease.capability),
            lease.owner_identity,
            lease.pointer_snapshot,
            id(lease.runtime_domain),
            lease.runtime_domain_id,
            lease.device_ordinal,
            lease.evidence_scope,
            lease.promotion_eligible,
        )
    except AttributeError as exc:
        raise HipAllocationLineageError(
            "hip_allocation_free_invalid", path, "free lease fields missing"
        ) from exc
    if (
        type(lease.capability) is not HipAllocationCapabilityV1
        or type(snapshot[0]) is not int
        or snapshot[0] <= 0
        or type(snapshot[2]) is not int
        or snapshot[2] <= 0
        or type(snapshot[3]) is not int
        or snapshot[3] <= 0
        or snapshot[3] > _UINTPTR_MAX
        or type(lease.runtime_domain) is not _RuntimeDomain
        or type(snapshot[5]) is not str
        or lease.runtime_domain.domain_id != snapshot[5]
        or type(snapshot[6]) is not int
        or snapshot[6] < 0
        or snapshot[7] != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1
        or snapshot[8] is not False
    ):
        _error("hip_allocation_free_invalid", path, "free lease fields changed")
    return snapshot


def _orphan_snapshot(lease: object, path: str) -> tuple[object, ...]:
    if type(lease) is not HipAllocationOrphanLeaseV1:
        _error("hip_allocation_orphan_invalid", path, "exact orphan lease required")
    try:
        snapshot = (
            lease.lease_id,
            lease.owner_identity,
            id(lease.runtime_domain),
            lease.runtime_domain_id,
            lease.device_ordinal,
            lease.role,
            id(lease.base),
            lease.pointer_snapshot,
            lease.nbytes,
            lease.element_type,
            lease.evidence_scope,
            lease.promotion_eligible,
        )
    except AttributeError as exc:
        raise HipAllocationLineageError(
            "hip_allocation_orphan_invalid", path, "orphan lease fields missing"
        ) from exc
    if (
        type(snapshot[0]) is not int
        or snapshot[0] <= 0
        or type(snapshot[1]) is not int
        or type(snapshot[3]) is not str
        or type(snapshot[4]) is not int
        or snapshot[4] < 0
        or type(snapshot[5]) is not str
        or (
            snapshot[7] is not None
            and (
                type(snapshot[7]) is not int
                or snapshot[7] <= 0
                or snapshot[7] > _UINTPTR_MAX
            )
        )
        or type(snapshot[8]) is not int
        or snapshot[8] <= 0
        or type(snapshot[9]) is not str
        or snapshot[9] not in _ELEMENT_LAYOUT
        or snapshot[10] != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1
        or snapshot[11] is not False
    ):
        _error("hip_allocation_orphan_invalid", path, "orphan fields changed")
    return snapshot


def _orphan_row(lease: object, path: str) -> _OrphanRow:
    snapshot = _orphan_snapshot(lease, path)
    row = _ORPHANS.get(id(lease))
    if (
        row is None
        or row.lease is not lease
        or row.lease_snapshot != snapshot
        or row.state != "pending"
    ):
        _error("hip_allocation_orphan_invalid", path, "orphan witness changed")
    owner = _owner_row(row.owner, f"{path}.owner")
    if (
        lease.owner_identity != owner.owner_id
        or lease.runtime_domain is not row.domain
        or lease.runtime_domain_id != _domain_id(row.domain)
        or lease.device_ordinal != row.device_ordinal
        or lease.role != row.role
        or lease.base is not row.base
        or lease.pointer_snapshot != row.pointer
        or lease.nbytes != row.nbytes
        or lease.element_type != row.element_type
    ):
        _error("hip_allocation_orphan_invalid", path, "orphan lineage changed")
    return row


def _complete_consumed_orphan_locked(
    lease: HipAllocationOrphanLeaseV1,
    snapshot: tuple[object, ...],
) -> None:
    orphan = _ORPHANS.get(id(lease))
    if orphan is None:
        return
    normal_witness = (
        orphan.lease is lease
        and orphan.lease_snapshot == snapshot
        and orphan.state == "pending"
    )
    emergency_witness = False
    if orphan.lease is not lease or orphan.state not in {
        "pending",
        "pending_unverified",
    }:
        normal_witness = False
    elif orphan.state == "pending_unverified" and orphan.lease_snapshot is None:
        owner = _owner_row(orphan.owner, "orphan_lease.owner")
        emergency_witness = all(
            (
                lease.owner_identity == owner.owner_id,
                lease.runtime_domain is orphan.domain,
                lease.runtime_domain_id == _domain_id(orphan.domain),
                lease.device_ordinal == orphan.device_ordinal,
                lease.role == orphan.role,
                lease.base is orphan.base,
                lease.pointer_snapshot == orphan.pointer,
                lease.nbytes == orphan.nbytes,
                lease.element_type == orphan.element_type,
            )
        )
    if not normal_witness and not emergency_witness:
        _error(
            "hip_allocation_orphan_invalid",
            "orphan_lease",
            "consumed orphan registry witness changed",
        )
    del _ORPHANS[id(lease)]


def _finish_orphan(
    owner: HipAllocationOwnerV1,
    lease: object,
    *,
    quarantine: bool,
    idempotent: bool = False,
    _control_token: object | None = None,
) -> str:
    # This is an entirely host-registry transition.  In particular,
    # quarantine must remain available when the runtime/device is unavailable.
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(owner_row, _control_token)
        snapshot = _orphan_snapshot(lease, "orphan_lease")
        consumed = _CONSUMED_ORPHANS.get(lease)
        if consumed is not None:
            if consumed[0] != snapshot:
                _error(
                    "hip_allocation_orphan_invalid",
                    "orphan_lease",
                    "consumed orphan fields changed",
                )
            _complete_consumed_orphan_locked(lease, snapshot)
            requested = "quarantined" if quarantine else "succeeded"
            if idempotent:
                if consumed[1] != requested:
                    _error(
                        "hip_allocation_orphan_outcome_mismatch",
                        "orphan_lease",
                        "terminal orphan outcome differs from requested disposition",
                    )
                return consumed[1]
            _error(
                "hip_allocation_orphan_consumed",
                "orphan_lease",
                "orphan cleanup lease already consumed",
            )
        emergency = _ORPHANS.get(id(lease))
        if (
            emergency is not None
            and emergency.lease is lease
            and emergency.state == "pending_unverified"
        ):
            if (
                emergency.owner is not owner
                or lease.owner_identity != owner_row.owner_id
            ):
                _error(
                    "hip_allocation_foreign",
                    "orphan_lease",
                    "emergency orphan belongs to another owner",
                )
            if emergency.conflicted and not quarantine:
                _error(
                    "hip_allocation_orphan_conflict",
                    "orphan_lease",
                    "overlapping allocator results may only be quarantined",
                )
            if emergency.pointer is None and not quarantine:
                _error(
                    "hip_allocation_orphan_target_invalid",
                    "orphan_lease",
                    "an allocator result without an exact pointer may only be quarantined",
                )
            if quarantine and emergency.pointer is not None:
                _append_quarantine_locked(
                    _domain_id(emergency.domain),
                    emergency.device_ordinal,
                    emergency.pointer,
                    emergency.end,
                )
            outcome = "quarantined" if quarantine else "succeeded"
            _CONSUMED_ORPHANS[lease] = (snapshot, outcome)
            del _ORPHANS[id(lease)]
            return outcome
    snapshot = _orphan_snapshot(lease, "orphan_lease")
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(owner_row, _control_token)
        consumed = _CONSUMED_ORPHANS.get(lease)
        if consumed is not None:
            if consumed[0] != snapshot:
                _error(
                    "hip_allocation_orphan_invalid",
                    "orphan_lease",
                    "consumed orphan fields changed",
                )
            _complete_consumed_orphan_locked(lease, snapshot)
            requested = "quarantined" if quarantine else "succeeded"
            if idempotent:
                if consumed[1] != requested:
                    _error(
                        "hip_allocation_orphan_outcome_mismatch",
                        "orphan_lease",
                        "terminal orphan outcome differs from requested disposition",
                    )
                return consumed[1]
            _error(
                "hip_allocation_orphan_consumed",
                "orphan_lease",
                "orphan cleanup lease already consumed",
            )
        orphan = _orphan_row(lease, "orphan_lease")
        if orphan.owner is not owner or lease.owner_identity != owner_row.owner_id:
            _error(
                "hip_allocation_foreign",
                "orphan_lease",
                "orphan belongs to another owner",
            )
        if orphan.state != "pending":
            _error(
                "hip_allocation_orphan_consumed",
                "orphan_lease",
                "orphan cleanup lease already consumed",
            )
        if orphan.conflicted and not quarantine:
            _error(
                "hip_allocation_orphan_conflict",
                "orphan_lease",
                "overlapping allocator results may only be quarantined",
            )
        if orphan.pointer is None and not quarantine:
            _error(
                "hip_allocation_orphan_target_invalid",
                "orphan_lease",
                "an allocator result without an exact pointer may only be quarantined",
            )
        outcome = "quarantined" if quarantine else "succeeded"
        if quarantine and orphan.pointer is not None:
            _append_quarantine_locked(
                _domain_id(orphan.domain),
                orphan.device_ordinal,
                orphan.pointer,
                orphan.end,
            )
        _CONSUMED_ORPHANS[lease] = (snapshot, outcome)
        _complete_consumed_orphan_locked(lease, snapshot)
        return outcome


def _free_row(lease: object, path: str) -> _FreeRow:
    snapshot = _free_snapshot(lease, path)
    row = _FREES.get(id(lease))
    if row is None or row.lease is not lease or row.lease_snapshot != snapshot:
        _error("hip_allocation_free_invalid", path, "free witness changed")
    return row


def _complete_consumed_free_locked(
    lease: HipAllocationFreeLeaseV1,
    snapshot: tuple[object, ...],
) -> None:
    free_row = _FREES.get(id(lease))
    if free_row is None:
        return
    if free_row.lease is not lease or free_row.lease_snapshot != snapshot:
        _error(
            "hip_allocation_free_invalid",
            "lease",
            "consumed free registry witness changed",
        )
    allocation = _ALLOCATIONS.get(free_row.allocation_id)
    if allocation is not None:
        if (
            allocation.capability is not lease.capability
            or allocation.free_lease is not lease
        ):
            _error(
                "hip_allocation_free_invalid",
                "lease",
                "consumed free allocation witness changed",
            )
        del _ALLOCATIONS[free_row.allocation_id]
    del _FREES[id(lease)]


def _finish_free(
    owner: HipAllocationOwnerV1,
    lease: object,
    *,
    quarantine: bool,
    idempotent: bool = False,
    _control_token: object | None = None,
) -> str:
    snapshot = _free_snapshot(lease, "lease")
    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(owner_row, _control_token)
        consumed = _CONSUMED_FREES.get(lease)
        if consumed is not None:
            if consumed[0] != snapshot:
                _error(
                    "hip_allocation_free_invalid",
                    "lease",
                    "consumed free lease fields changed",
                )
            _complete_consumed_free_locked(lease, snapshot)
            requested = "quarantined" if quarantine else "succeeded"
            if idempotent:
                if consumed[1] != requested:
                    _error(
                        "hip_allocation_free_outcome_mismatch",
                        "lease",
                        "terminal free outcome differs from requested disposition",
                    )
                return consumed[1]
            _error("hip_allocation_free_consumed", "lease", "lease already consumed")
        free_row = _free_row(lease, "lease")
        if free_row.owner is not owner or lease.owner_identity != owner_row.owner_id:
            _error("hip_allocation_foreign", "lease", "belongs to another owner")
        if free_row.state != "pending":
            _error("hip_allocation_free_consumed", "lease", "lease already consumed")
        allocation = _ALLOCATIONS.get(free_row.allocation_id)
        if (
            allocation is None
            or allocation.owner is not owner
            or allocation.capability is not lease.capability
            or allocation.state not in {"free_pending", "poisoned_free_pending"}
            or allocation.free_lease is not lease
            or lease.pointer_snapshot != allocation.pointer
            or lease.runtime_domain is not allocation.domain
            or lease.runtime_domain_id != _domain_id(allocation.domain)
            or lease.device_ordinal != allocation.device_ordinal
        ):
            _error("hip_allocation_free_invalid", "lease", "free state changed")
        outcome = "quarantined" if quarantine else "succeeded"
        if quarantine:
            _append_quarantine_locked(
                _domain_id(allocation.domain),
                allocation.device_ordinal,
                allocation.pointer,
                allocation.end,
            )
        _CONSUMED_FREES[lease] = (snapshot, outcome)
        _complete_consumed_free_locked(lease, snapshot)
        return outcome


def _quarantine_poisoned_allocation(
    owner: HipAllocationOwnerV1,
    capability: object,
    *,
    idempotent: bool,
    _control_token: object | None = None,
) -> str:
    """Retire an overlap-poisoned row without issuing another device free."""

    with _LOCK:
        owner_row = _owner_row(owner, "owner")
        _require_owner_control_locked(owner_row, _control_token)
        if type(capability) is not HipAllocationCapabilityV1:
            _error(
                "hip_allocation_capability_invalid",
                "capability",
                "exact capability required",
            )
        consumed = _QUARANTINED_CAPABILITIES.get(capability)
        if consumed is not None:
            if consumed[0] != owner_row.owner_id:
                _error(
                    "hip_allocation_foreign",
                    "capability",
                    "quarantined allocation belongs to another owner",
                )
            allocation = _ALLOCATIONS.get(id(capability))
            if allocation is not None:
                if (
                    allocation.capability is not capability
                    or allocation.owner is not owner
                ):
                    _error(
                        "hip_allocation_capability_invalid",
                        "capability",
                        "quarantined registry witness changed",
                    )
                del _ALLOCATIONS[id(capability)]
            if idempotent:
                return "quarantined"
            _error(
                "hip_allocation_capability_quarantined",
                "capability",
                "allocation is already quarantined",
            )
        allocation = _ALLOCATIONS.get(id(capability))
        if allocation is None or allocation.capability is not capability:
            _error(
                "hip_allocation_capability_invalid",
                "capability",
                "registry witness changed",
            )
        if allocation.owner is not owner:
            _error(
                "hip_allocation_foreign",
                "capability",
                "poisoned allocation belongs to another owner",
            )
        if _allocation_domain_is_poisoned_locked(allocation):
            _poison_allocation_row_locked(allocation)
        capability_corrupted = not _capability_matches_private_row(allocation)
        if allocation.state != "poisoned" and not (
            capability_corrupted and allocation.state == "live"
        ):
            _error(
                "hip_allocation_poison_state_invalid",
                "capability",
                "only poisoned or corrupted-live allocations may be quarantined",
            )
        _append_quarantine_locked(
            _domain_id(allocation.domain),
            allocation.device_ordinal,
            allocation.pointer,
            allocation.end,
        )
        _QUARANTINED_CAPABILITIES[capability] = (
            owner_row.owner_id,
            allocation.capability_snapshot,
        )
        del _ALLOCATIONS[id(capability)]
        return "quarantined"


def _append_quarantine_locked(
    runtime_domain_id: str,
    device_ordinal: int,
    pointer: int,
    end: int | None,
) -> None:
    merged_start = pointer
    merged_end_value = end if end is not None else _UINTPTR_MAX + 1
    retained: list[_QuarantinedRange] = []
    for row in _QUARANTINED_RANGES:
        same_domain = (
            row.runtime_domain_id == runtime_domain_id
            and row.device_ordinal == device_ordinal
        )
        row_end_value = row.end if row.end is not None else _UINTPTR_MAX + 1
        overlaps = (
            same_domain
            and merged_start <= row_end_value
            and row.pointer <= merged_end_value
        )
        if same_domain and overlaps:
            merged_start = min(merged_start, row.pointer)
            merged_end_value = max(merged_end_value, row_end_value)
        else:
            retained.append(row)
    retained.append(
        _QuarantinedRange(
            runtime_domain_id=runtime_domain_id,
            device_ordinal=device_ordinal,
            pointer=merged_start,
            end=(None if merged_end_value == _UINTPTR_MAX + 1 else merged_end_value),
        )
    )
    _QUARANTINED_RANGES[:] = retained


def _acknowledge_free_success(
    owner: HipAllocationOwnerV1,
    lease: object,
    *,
    _control_token: object | None = None,
) -> None:
    _finish_free(
        owner,
        lease,
        quarantine=False,
        _control_token=_control_token,
    )


def _quarantine_free_uncertain(
    owner: HipAllocationOwnerV1,
    lease: object,
    *,
    _control_token: object | None = None,
) -> None:
    _finish_free(
        owner,
        lease,
        quarantine=True,
        _control_token=_control_token,
    )


__all__ = [
    "HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1",
    "HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1",
    "HipAllocationBorrowLeaseV1",
    "HipAllocationCapabilityV1",
    "HipAllocationFreeLeaseV1",
    "HipAllocationLineageError",
    "HipAllocationOrphanLeaseV1",
    "HipAllocationOwnerV1",
    "borrow_hip_allocations_v1",
    "open_hip_allocation_owner_v1",
    "open_hip_allocation_peer_owner_v1",
    "recover_hip_allocation_borrow_v1",
    "release_hip_allocation_borrow_v1",
    "reserve_hip_allocation_owner_control_v1",
    "snapshot_hip_allocation_owner_cleanup_v1",
    "validate_hip_allocation_borrow_v1",
    "validate_hip_allocation_capability_v1",
    "validate_hip_allocation_owner_control_v1",
    "validate_hip_allocation_owner_v1",
]
