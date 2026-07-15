"""Process-local accounting for Engine-v2-owned HIP copy bindings.

The counter in this module is deliberately narrower than a ROCm activity
tracer.  It observes calls made through one exact bound Engine-v2 runtime; it
does not observe fresh ``dlsym``/``ctypes`` bindings, external libraries, or
DMA initiated outside that owner.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Literal


BoundHipCopyKindV1 = Literal[
    "h2d_async",
    "d2h_async",
    "d2h_blocking",
]

_COPY_KINDS: tuple[BoundHipCopyKindV1, ...] = (
    "h2d_async",
    "d2h_async",
    "d2h_blocking",
)
_BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1 = object()


@dataclass(frozen=True, slots=True)
class HipBoundCopyCounterV1:
    attempt_count: int
    success_count: int
    failure_count: int
    bytes_attempted: int
    bytes_succeeded: int
    in_flight_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "attempt_count": self.attempt_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "bytes_attempted": self.bytes_attempted,
            "bytes_succeeded": self.bytes_succeeded,
            "in_flight_count": self.in_flight_count,
        }


@dataclass(frozen=True, slots=True)
class HipBoundCopyAuditSnapshotV1:
    sequence: int
    h2d_async: HipBoundCopyCounterV1
    d2h_async: HipBoundCopyCounterV1
    d2h_blocking: HipBoundCopyCounterV1

    @property
    def total_in_flight_count(self) -> int:
        return sum(
            row.in_flight_count
            for row in (self.h2d_async, self.d2h_async, self.d2h_blocking)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "h2d_async": self.h2d_async.to_dict(),
            "d2h_async": self.d2h_async.to_dict(),
            "d2h_blocking": self.d2h_blocking.to_dict(),
        }


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _BoundCopyAuditTicketV1:
    nonce: object
    kind: BoundHipCopyKindV1
    byte_count: int


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _BoundCopyAuditCaptureV1:
    runtime: Any
    state: _BoundHipCopyAuditStateV1
    snapshot: HipBoundCopyAuditSnapshotV1
    binding_identity: tuple[Any, ...]
    native_loader_bound: bool


class _BoundHipCopyAuditStateV1:
    """Monotonic aggregate ledger shared by one bound runtime's copy paths."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._counters: dict[BoundHipCopyKindV1, list[int]] = {
            kind: [0, 0, 0, 0, 0, 0] for kind in _COPY_KINDS
        }
        self._in_flight: dict[object, _BoundCopyAuditTicketV1] = {}

    def begin(
        self,
        kind: BoundHipCopyKindV1,
        byte_count: int,
    ) -> _BoundCopyAuditTicketV1:
        if kind not in _COPY_KINDS:
            raise ValueError(f"Unsupported HIP copy audit kind: {kind!r}")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int):
            raise TypeError("byte_count must be an integer")
        if byte_count < 0:
            raise ValueError("byte_count must be non-negative")
        nonce = object()
        ticket = _BoundCopyAuditTicketV1(nonce, kind, byte_count)
        with self._lock:
            row = self._counters[kind]
            row[0] += 1
            row[3] += byte_count
            row[5] += 1
            self._sequence += 1
            self._in_flight[nonce] = ticket
        return ticket

    def finish(self, ticket: _BoundCopyAuditTicketV1, *, succeeded: bool) -> None:
        if type(ticket) is not _BoundCopyAuditTicketV1:
            raise TypeError("copy audit ticket is invalid")
        if type(succeeded) is not bool:
            raise TypeError("succeeded must be a bool")
        with self._lock:
            current = self._in_flight.get(ticket.nonce)
            if current is not ticket:
                raise RuntimeError("copy audit ticket is stale or already completed")
            row = self._counters[ticket.kind]
            if succeeded:
                row[1] += 1
                row[4] += ticket.byte_count
            else:
                row[2] += 1
            row[5] -= 1
            self._sequence += 1
            del self._in_flight[ticket.nonce]

    def snapshot(self) -> HipBoundCopyAuditSnapshotV1:
        with self._lock:
            rows = {
                kind: HipBoundCopyCounterV1(*self._counters[kind])
                for kind in _COPY_KINDS
            }
            return HipBoundCopyAuditSnapshotV1(
                sequence=self._sequence,
                h2d_async=rows["h2d_async"],
                d2h_async=rows["d2h_async"],
                d2h_blocking=rows["d2h_blocking"],
            )


def _capture_bound_copy_audit_v1(runtime: Any) -> _BoundCopyAuditCaptureV1:
    factory = getattr(runtime, "_bound_copy_audit_snapshot_v1", None)
    if not callable(factory) or getattr(factory, "__self__", None) is not runtime:
        raise TypeError("runtime does not expose the bound-copy audit authority")
    result = factory(_BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1)
    if (
        type(result) is not tuple
        or len(result) != 2
        or type(result[0]) is not _BoundHipCopyAuditStateV1
        or type(result[1]) is not HipBoundCopyAuditSnapshotV1
    ):
        raise TypeError("runtime returned an invalid bound-copy audit snapshot")
    state, snapshot = result
    _validate_bound_copy_audit_snapshot_v1(snapshot)
    blocking = getattr(runtime, "_blocking_d2h_copy", None)
    blocking_state = getattr(blocking, "_copy_audit_v1", None)
    native_loader_bound = (
        getattr(runtime, "_loader_provenance_witness", None) is not None
        and getattr(runtime, "_loaded", None) is not None
        and blocking_state is state
    )
    binding_identity = (
        type(runtime),
        id(runtime),
        id(getattr(factory, "__func__", None)),
        id(state),
        id(getattr(runtime, "_loaded", None)),
        id(getattr(runtime, "_memcpy_async", None)),
        id(getattr(runtime, "_memcpy", None)),
        id(getattr(type(runtime), "copy_h2d_async", None)),
        id(getattr(type(runtime), "copy_d2h_async", None)),
        id(getattr(type(runtime), "completion_export_copy_binding", None)),
        type(blocking),
        id(blocking),
        id(getattr(type(blocking), "__call__", None)),
        id(blocking_state),
    )
    return _BoundCopyAuditCaptureV1(
        runtime=runtime,
        state=state,
        snapshot=snapshot,
        binding_identity=binding_identity,
        native_loader_bound=native_loader_bound,
    )


def _validate_bound_copy_audit_snapshot_v1(
    snapshot: HipBoundCopyAuditSnapshotV1,
) -> None:
    if type(snapshot) is not HipBoundCopyAuditSnapshotV1:
        raise TypeError("bound-copy audit snapshot has an invalid type")
    if isinstance(snapshot.sequence, bool) or not isinstance(snapshot.sequence, int):
        raise TypeError("bound-copy audit sequence must be an integer")
    if snapshot.sequence < 0:
        raise ValueError("bound-copy audit sequence must be non-negative")
    total_events = 0
    for row in (snapshot.h2d_async, snapshot.d2h_async, snapshot.d2h_blocking):
        if type(row) is not HipBoundCopyCounterV1:
            raise TypeError("bound-copy audit counter has an invalid type")
        values = tuple(getattr(row, name) for name in row.__dataclass_fields__)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise TypeError("bound-copy audit counters must be integers")
        if any(value < 0 for value in values):
            raise ValueError("bound-copy audit counters must be non-negative")
        if (
            row.success_count + row.failure_count + row.in_flight_count
            != row.attempt_count
        ):
            raise ValueError("bound-copy audit operation conservation failed")
        if row.bytes_succeeded > row.bytes_attempted:
            raise ValueError("bound-copy audit byte conservation failed")
        total_events += row.attempt_count + row.success_count + row.failure_count
    if snapshot.sequence != total_events:
        raise ValueError("bound-copy audit sequence conservation failed")


__all__ = [
    "HipBoundCopyAuditSnapshotV1",
    "HipBoundCopyCounterV1",
]
