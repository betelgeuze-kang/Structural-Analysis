"""Private constant-space ordinal ledger for FGMRES-v2 RTC submissions.

The ledger observes only calls that pass through the exact package-owned
``HipRtcFgmresV2Kernel`` instance.  It is deliberately not a ROCm activity
trace and does not claim visibility into fresh native bindings, other
libraries, or device-side work submitted outside that owner.

On a healthy, receipt-eligible ledger path, each native-call attempt receives
one monotonically increasing operation ordinal before the call.  A second
hash-chain event records the disposition after the call.  An internal audit
fault irreversibly poisons receipt issuance while the owning solver may keep
its native lifecycle running without a ticket.  The state retains counters and
a rolling SHA-256 head rather than an event array, so one operation costs
constant additional memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import threading
from typing import Any, Literal

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


HipFgmresRtcOperationKindV1 = Literal["memset", "launch", "fence"]
HipFgmresRtcOperationDispositionV1 = Literal[
    "success",
    "rejected",
    "ambiguous",
]

_KINDS: tuple[HipFgmresRtcOperationKindV1, ...] = (
    "memset",
    "launch",
    "fence",
)
_KIND_CODE = {"memset": 1, "launch": 2, "fence": 3}
_DISPOSITION_CODE = {"success": 1, "rejected": 2, "ambiguous": 3}
_DOMAIN = b"structural-analysis/hip-fgmres-rtc-launch-fence-ledger/v1\x00"
_GENESIS_HASH = "sha256:" + hashlib.sha256(_DOMAIN + b"genesis").hexdigest()
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_JSON_SAFE_INTEGER = (1 << 53) - 1
_FENCE_DESCRIPTOR_HASH = canonical_hash(
    {
        "schema": "structural-analysis-hip-fgmres-rtc-operation-descriptor.v1",
        "kind": "fence",
        "native_symbol": "hipStreamSynchronize",
    }
)

_LAUNCH_DESCRIPTOR_FIELDS = (
    "name",
    "submission_kind",
    "kernel_symbol",
    "mode",
    "expected_schedule_epoch",
    "expected_restart",
    "expected_column",
    "logical_index",
    "row_index",
    "pass_index",
    "vector_gate",
    "reduction_target",
    "expected_reduction_epoch",
    "value_count",
    "output_count",
    "final_stage",
    "device_gate_source",
    "reduction_tree_id",
)

_RTC_LAUNCH_FENCE_LEDGER_SNAPSHOT_MINT_V1 = object()


@dataclass(frozen=True, slots=True)
class HipFgmresRtcOperationCounterV1:
    attempt_count: int
    success_count: int
    rejected_count: int
    ambiguous_count: int
    in_flight_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRtcLaunchFenceLedgerSnapshotV1:
    operation_ordinal: int
    event_sequence: int
    rolling_hash: str
    memset: HipFgmresRtcOperationCounterV1
    launch: HipFgmresRtcOperationCounterV1
    fence: HipFgmresRtcOperationCounterV1
    last_completed_operation_ordinal: int
    last_completed_kind: Literal["none", "memset", "launch", "fence"]
    last_completed_disposition: Literal[
        "none",
        "success",
        "rejected",
        "ambiguous",
    ]

    @property
    def total_in_flight_count(self) -> int:
        return sum(
            row.in_flight_count for row in (self.memset, self.launch, self.fence)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_ordinal": self.operation_ordinal,
            "event_sequence": self.event_sequence,
            "rolling_hash": self.rolling_hash,
            "memset": self.memset.to_dict(),
            "launch": self.launch.to_dict(),
            "fence": self.fence.to_dict(),
            "last_completed_operation_ordinal": (self.last_completed_operation_ordinal),
            "last_completed_kind": self.last_completed_kind,
            "last_completed_disposition": self.last_completed_disposition,
        }


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresRtcOperationTicketV1:
    nonce: object
    ordinal: int
    kind: HipFgmresRtcOperationKindV1
    descriptor_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresRtcLaunchFenceLedgerCaptureV1:
    kernel: Any
    state: _HipFgmresRtcLaunchFenceLedgerStateV1
    snapshot: HipFgmresRtcLaunchFenceLedgerSnapshotV1
    binding_snapshot: tuple[Any, ...]


class _HipFgmresRtcLaunchFenceLedgerStateV1:
    """One exact kernel's monotonic, constant-space operation ledger."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._poisoned = False
        self._operation_ordinal = 0
        self._event_sequence = 0
        self._rolling_hash = _GENESIS_HASH
        self._counters: dict[HipFgmresRtcOperationKindV1, list[int]] = {
            kind: [0, 0, 0, 0, 0] for kind in _KINDS
        }
        self._in_flight: dict[object, _HipFgmresRtcOperationTicketV1] = {}
        self._last_completed_operation_ordinal = 0
        self._last_completed_kind: Literal["none", "memset", "launch", "fence"] = "none"
        self._last_completed_disposition: Literal[
            "none", "success", "rejected", "ambiguous"
        ] = "none"

    def begin(
        self,
        kind: HipFgmresRtcOperationKindV1,
        descriptor_hash: str,
    ) -> _HipFgmresRtcOperationTicketV1:
        _require_kind(kind)
        _require_hash(descriptor_hash, "descriptor_hash")
        nonce = object()
        with self._lock:
            if self._poisoned:
                raise RuntimeError("RTC launch/fence audit ledger is poisoned")
            if self._in_flight:
                raise RuntimeError(
                    "an RTC launch/fence audit operation is already in flight"
                )
            if self._operation_ordinal >= _MAX_JSON_SAFE_INTEGER:
                raise OverflowError("RTC launch/fence operation ordinal exhausted")
            if self._event_sequence > _MAX_JSON_SAFE_INTEGER - 2:
                raise OverflowError("RTC launch/fence event sequence exhausted")
            ordinal = self._operation_ordinal + 1
            ticket = _HipFgmresRtcOperationTicketV1(
                nonce,
                ordinal,
                kind,
                descriptor_hash,
            )
            try:
                row = self._counters[kind]
                row[0] += 1
                row[4] += 1
                self._operation_ordinal = ordinal
                self._event_sequence += 1
                self._rolling_hash = _fold_event(
                    self._rolling_hash,
                    ordinal=ordinal,
                    kind=kind,
                    descriptor_hash=descriptor_hash,
                    phase="attempt",
                    disposition=None,
                )
                self._in_flight[nonce] = ticket
            except BaseException:
                self._poisoned = True
                raise
            return ticket

    def finish(
        self,
        ticket: _HipFgmresRtcOperationTicketV1,
        *,
        disposition: HipFgmresRtcOperationDispositionV1,
    ) -> None:
        if type(ticket) is not _HipFgmresRtcOperationTicketV1:
            raise TypeError("RTC launch/fence audit ticket is invalid")
        if disposition not in _DISPOSITION_CODE:
            raise ValueError("RTC launch/fence disposition is invalid")
        with self._lock:
            if self._poisoned:
                raise RuntimeError("RTC launch/fence audit ledger is poisoned")
            current = self._in_flight.get(ticket.nonce)
            if current is not ticket:
                raise RuntimeError(
                    "RTC launch/fence audit ticket is stale or already completed"
                )
            try:
                row = self._counters[ticket.kind]
                row[{"success": 1, "rejected": 2, "ambiguous": 3}[disposition]] += 1
                row[4] -= 1
                self._event_sequence += 1
                self._rolling_hash = _fold_event(
                    self._rolling_hash,
                    ordinal=ticket.ordinal,
                    kind=ticket.kind,
                    descriptor_hash=ticket.descriptor_hash,
                    phase="outcome",
                    disposition=disposition,
                )
                del self._in_flight[ticket.nonce]
                self._last_completed_operation_ordinal = ticket.ordinal
                self._last_completed_kind = ticket.kind
                self._last_completed_disposition = disposition
            except BaseException:
                self._poisoned = True
                raise

    def poison(self) -> None:
        """Fail closed after an interrupted caller-side begin hand-off."""

        with self._lock:
            self._poisoned = True

    def snapshot(self) -> HipFgmresRtcLaunchFenceLedgerSnapshotV1:
        with self._lock:
            if self._poisoned:
                raise RuntimeError("RTC launch/fence audit ledger is poisoned")
            rows = {
                kind: HipFgmresRtcOperationCounterV1(*self._counters[kind])
                for kind in _KINDS
            }
            snapshot = HipFgmresRtcLaunchFenceLedgerSnapshotV1(
                operation_ordinal=self._operation_ordinal,
                event_sequence=self._event_sequence,
                rolling_hash=self._rolling_hash,
                memset=rows["memset"],
                launch=rows["launch"],
                fence=rows["fence"],
                last_completed_operation_ordinal=(
                    self._last_completed_operation_ordinal
                ),
                last_completed_kind=self._last_completed_kind,
                last_completed_disposition=self._last_completed_disposition,
            )
        _validate_snapshot_v1(snapshot)
        return snapshot


def _capture_rtc_launch_fence_ledger_v1(
    kernel: Any,
    checkpoint_owner_token: object,
) -> _HipFgmresRtcLaunchFenceLedgerCaptureV1:
    factory = getattr(kernel, "_checkpoint_launch_fence_ledger_snapshot_v1", None)
    if not callable(factory) or getattr(factory, "__self__", None) is not kernel:
        raise TypeError("kernel does not expose RTC launch/fence ledger authority")
    result = factory(
        checkpoint_owner_token,
        _RTC_LAUNCH_FENCE_LEDGER_SNAPSHOT_MINT_V1,
    )
    if (
        type(result) is not tuple
        or len(result) != 3
        or type(result[0]) is not _HipFgmresRtcLaunchFenceLedgerStateV1
        or type(result[1]) is not HipFgmresRtcLaunchFenceLedgerSnapshotV1
        or type(result[2]) is not tuple
    ):
        raise TypeError("kernel returned an invalid RTC launch/fence snapshot")
    state, snapshot, binding_snapshot = result
    _validate_snapshot_v1(snapshot)
    return _HipFgmresRtcLaunchFenceLedgerCaptureV1(
        kernel=kernel,
        state=state,
        snapshot=snapshot,
        binding_snapshot=binding_snapshot,
    )


def _launch_descriptor_hash_v1(row: Any) -> str:
    if type(row) is tuple:
        try:
            source = dict(row)
        except (TypeError, ValueError) as exc:
            raise TypeError("FGMRES RTC launch descriptor row is invalid") from exc
        values = {name: source.get(name) for name in _LAUNCH_DESCRIPTOR_FIELDS}
    else:
        values = {name: getattr(row, name, None) for name in _LAUNCH_DESCRIPTOR_FIELDS}
    if (
        type(values["name"]) is not str
        or not values["name"]
        or type(values["submission_kind"]) is not str
        or not values["submission_kind"]
        or type(values["kernel_symbol"]) is not str
        or not values["kernel_symbol"]
    ):
        raise TypeError("FGMRES RTC launch descriptor row is invalid")
    return canonical_hash(
        {
            "schema": ("structural-analysis-hip-fgmres-rtc-operation-descriptor.v1"),
            "kind": "launch",
            "row": values,
        }
    )


def _memset_descriptor_hash_v1(role: str, byte_length: int) -> str:
    if type(role) is not str or not role:
        raise TypeError("FGMRES RTC memset role is invalid")
    if type(byte_length) is not int or byte_length <= 0:
        raise TypeError("FGMRES RTC memset byte length is invalid")
    return canonical_hash(
        {
            "schema": ("structural-analysis-hip-fgmres-rtc-operation-descriptor.v1"),
            "kind": "memset",
            "role": role,
            "byte_length": byte_length,
        }
    )


def _fallback_descriptor_hash_v1(
    kind: Literal["memset", "launch"],
    operation: str,
) -> str:
    if type(operation) is not str or not operation:
        raise TypeError("FGMRES RTC fallback operation is invalid")
    return canonical_hash(
        {
            "schema": ("structural-analysis-hip-fgmres-rtc-operation-descriptor.v1"),
            "kind": kind,
            "fallback_operation": operation,
            "authoritative_schedule_descriptor": False,
        }
    )


def _fence_descriptor_hash_v1() -> str:
    return _FENCE_DESCRIPTOR_HASH


def _replay_successful_operation_v1(
    rolling_hash: str,
    operation_ordinal: int,
    kind: HipFgmresRtcOperationKindV1,
    descriptor_hash: str,
) -> tuple[str, int]:
    _require_hash(rolling_hash, "rolling_hash")
    _require_kind(kind)
    _require_hash(descriptor_hash, "descriptor_hash")
    if (
        type(operation_ordinal) is not int
        or operation_ordinal < 0
        or operation_ordinal >= _MAX_JSON_SAFE_INTEGER
    ):
        raise ValueError("RTC launch/fence replay ordinal is invalid")
    ordinal = operation_ordinal + 1
    head = _fold_event(
        rolling_hash,
        ordinal=ordinal,
        kind=kind,
        descriptor_hash=descriptor_hash,
        phase="attempt",
        disposition=None,
    )
    return (
        _fold_event(
            head,
            ordinal=ordinal,
            kind=kind,
            descriptor_hash=descriptor_hash,
            phase="outcome",
            disposition="success",
        ),
        ordinal,
    )


def _validate_snapshot_v1(
    snapshot: HipFgmresRtcLaunchFenceLedgerSnapshotV1,
) -> None:
    if type(snapshot) is not HipFgmresRtcLaunchFenceLedgerSnapshotV1:
        raise TypeError("RTC launch/fence ledger snapshot has an invalid type")
    integers = (
        snapshot.operation_ordinal,
        snapshot.event_sequence,
        snapshot.last_completed_operation_ordinal,
    )
    if any(type(value) is not int for value in integers):
        raise TypeError("RTC launch/fence ledger ordinals must be exact integers")
    if any(value < 0 or value > _MAX_JSON_SAFE_INTEGER for value in integers):
        raise ValueError("RTC launch/fence ledger ordinal is out of range")
    _require_hash(snapshot.rolling_hash, "rolling_hash")
    attempts = completed = in_flight = 0
    for row in (snapshot.memset, snapshot.launch, snapshot.fence):
        if type(row) is not HipFgmresRtcOperationCounterV1:
            raise TypeError("RTC launch/fence counter has an invalid type")
        values = tuple(getattr(row, name) for name in row.__dataclass_fields__)
        if any(type(value) is not int for value in values):
            raise TypeError("RTC launch/fence counters must be exact integers")
        if any(value < 0 or value > _MAX_JSON_SAFE_INTEGER for value in values):
            raise ValueError("RTC launch/fence counter is out of range")
        if (
            row.success_count
            + row.rejected_count
            + row.ambiguous_count
            + row.in_flight_count
            != row.attempt_count
        ):
            raise ValueError("RTC launch/fence counter conservation failed")
        attempts += row.attempt_count
        completed += row.success_count + row.rejected_count + row.ambiguous_count
        in_flight += row.in_flight_count
    if snapshot.operation_ordinal != attempts:
        raise ValueError("RTC launch/fence operation ordinal conservation failed")
    if snapshot.event_sequence != attempts + completed:
        raise ValueError("RTC launch/fence event sequence conservation failed")
    if in_flight > 1:
        raise ValueError("RTC launch/fence ledger permits at most one in-flight call")
    if completed == 0:
        if (
            snapshot.last_completed_operation_ordinal != 0
            or snapshot.last_completed_kind != "none"
            or snapshot.last_completed_disposition != "none"
        ):
            raise ValueError("RTC launch/fence empty tail is inconsistent")
    else:
        if (
            snapshot.last_completed_operation_ordinal
            != snapshot.operation_ordinal - in_flight
            or snapshot.last_completed_kind not in _KINDS
            or snapshot.last_completed_disposition not in _DISPOSITION_CODE
        ):
            raise ValueError("RTC launch/fence completed tail is inconsistent")
        last_counter = getattr(snapshot, snapshot.last_completed_kind)
        if (
            getattr(
                last_counter,
                f"{snapshot.last_completed_disposition}_count",
            )
            <= 0
        ):
            raise ValueError("RTC launch/fence completed tail has no matching event")


def _fold_event(
    rolling_hash: str,
    *,
    ordinal: int,
    kind: HipFgmresRtcOperationKindV1,
    descriptor_hash: str,
    phase: Literal["attempt", "outcome"],
    disposition: HipFgmresRtcOperationDispositionV1 | None,
) -> str:
    _require_hash(rolling_hash, "rolling_hash")
    _require_hash(descriptor_hash, "descriptor_hash")
    if type(ordinal) is not int or not 1 <= ordinal <= _MAX_JSON_SAFE_INTEGER:
        raise ValueError("RTC launch/fence event ordinal is invalid")
    _require_kind(kind)
    if phase == "attempt":
        if disposition is not None:
            raise ValueError("RTC attempt event cannot carry a disposition")
        phase_code = 1
        disposition_code = 0
    elif phase == "outcome" and disposition in _DISPOSITION_CODE:
        phase_code = 2
        disposition_code = _DISPOSITION_CODE[disposition]
    else:
        raise ValueError("RTC launch/fence event phase is invalid")
    digest = hashlib.sha256()
    digest.update(_DOMAIN)
    digest.update(bytes.fromhex(rolling_hash[7:]))
    digest.update(ordinal.to_bytes(8, "big", signed=False))
    digest.update(bytes((_KIND_CODE[kind], phase_code, disposition_code)))
    digest.update(bytes.fromhex(descriptor_hash[7:]))
    return "sha256:" + digest.hexdigest()


def _require_kind(kind: object) -> None:
    if type(kind) is not str or kind not in _KIND_CODE:
        raise ValueError("RTC launch/fence operation kind is invalid")


def _require_hash(value: object, name: str) -> None:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 value")


__all__ = [
    "HipFgmresRtcLaunchFenceLedgerSnapshotV1",
    "HipFgmresRtcOperationCounterV1",
]
