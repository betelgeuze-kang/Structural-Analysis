"""Caller-attested owner for the recurrence-v2 checkpoint transaction.

This module owns exactly the already-implemented column-zero
``DECIDE -> SOURCE_PREFLIGHT -> COMMIT -> FINALIZE`` launch slice.  It adds process-local
capabilities, exact typed allocation registration, range validation, a
single-use caller-attested predecessor receipt, exclusive access to the raw
HIPRTC kernel, and conservative poison/fence lifetime rules.  It deliberately
does not claim an upstream device-state producer receipt, allocator
provenance, live Krylov-parent integration, later columns/restarts, a final
guard, or host-copy-zero/full-solver parity.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field, fields
import itertools
import math
import threading
from types import MappingProxyType
from typing import Any, Literal

from structural_analysis.engine_v2.backends.hip.context import (
    _INJECTED_HIP_CONTEXT_RUNTIME_MINT,
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.native import LoadedHipRuntime
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcError, _pointer_integer

from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_MAX_RESTART_DIMENSION,
)
from .fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
)
from .fgmres_rtc_v2 import (
    FgmresV2FirstColumnCheckpointTransactionLaunch,
    HipRtcFgmresV2Kernel,
    _validate_identity,
    first_column_checkpoint_transaction_launches_v2,
    solve_record_byte_length_v2,
)


HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2 = (
    "sha256:0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d"
)
HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2 = (
    "sha256:6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b"
)
HIP_FGMRES_RTC_SOURCE_SHA256_V2 = (
    "sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d"
)

FgmresCheckpointContextStateV2 = Literal[
    "READY",
    "ENQUEUEING",
    "PENDING_FENCE",
    "POISONED_PENDING_FENCE",
    "POISONED_NO_WORK",
    "FENCE_OBSERVED_ACK_PENDING",
    "FENCED",
    "POISONED_FENCED",
    "CLEANUP_FAILED",
    "CLOSED",
]
FgmresAllocationElementTypeV2 = Literal["f64", "u8"]

_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
_VALID_PREDECESSOR_MASKS = frozenset({0, 1792, 7936})
_BUFFER_ROLES = (
    "reduced_state",
    "reduced_load",
    "inverse_diagonal",
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "basis_z",
    "dense",
    "control_state",
    "solve_record",
)
_CANDIDATE_SOURCE_ROLES = ("work_w", "basis_v")
_CHECKPOINT_TRANSACTION_SUBMISSION_KINDS = (
    "control",
    "vector",
    "vector",
    "control",
)
_CHECKPOINT_TRANSACTION_LAUNCH_FIELD_NAMES = tuple(
    row.name for row in fields(FgmresV2FirstColumnCheckpointTransactionLaunch)
)
_ID_COUNTER = itertools.count(1)
_ID_LOCK = threading.Lock()
_RECEIPT_MINT = object()
_CALLER_ATTESTED_EVIDENCE_SCOPE = "caller_attested_valid_predecessor_non_promoting"


class HipFgmresRecurrenceContextV2Error(RuntimeError):
    """Stable fail-closed context error with optional cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        transaction_receipt: HipFgmresCheckpointTransactionReceiptV2 | None = None,
        launch_disposition: str | None = None,
        no_work_proven: bool | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message or code
        self.transaction_receipt = transaction_receipt
        self.launch_disposition = launch_disposition
        self.no_work_proven = no_work_proven
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresDeviceAllocationV2:
    """One exact registered HIP allocation base and immutable lineage."""

    base: Any = field(repr=False, compare=False)
    pointer_snapshot: int
    nbytes: int
    element_type: FgmresAllocationElementTypeV2
    owner_token: object = field(repr=False, compare=False)
    generation: int
    runtime: object = field(repr=False, compare=False)
    device_ordinal: int


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointBuffersV2:
    """The eleven exact allocation descriptors used by the transaction."""

    reduced_state: HipFgmresDeviceAllocationV2
    reduced_load: HipFgmresDeviceAllocationV2
    inverse_diagonal: HipFgmresDeviceAllocationV2
    solution_x: HipFgmresDeviceAllocationV2
    true_residual: HipFgmresDeviceAllocationV2
    work_w: HipFgmresDeviceAllocationV2
    basis_v: HipFgmresDeviceAllocationV2
    basis_z: HipFgmresDeviceAllocationV2
    dense: HipFgmresDeviceAllocationV2
    control_state: HipFgmresDeviceAllocationV2
    solve_record: HipFgmresDeviceAllocationV2

    def items(self) -> tuple[tuple[str, HipFgmresDeviceAllocationV2], ...]:
        return tuple((name, getattr(self, name)) for name in _BUFFER_ROLES)


class HipFgmresCheckpointPredecessorReceiptV2:
    """Nonconstructible, process-local, single-use predecessor capability."""

    __slots__ = (
        "predecessor_id",
        "evidence_scope",
        "authoritative_predecessor_proven",
        "live_krylov_parent_integrated",
        "promotion_eligible",
        "completion_fence_authoritative",
        "kernel",
        "kernel_identity",
        "kernel_identity_hash",
        "combined_abi_hash",
        "checkpoint_schedule_hash",
        "stream",
        "stream_pointer",
        "runtime",
        "device_ordinal",
        "free_dof_count",
        "restart_dimension",
        "maximum_restart_count",
        "schedule_epoch",
        "reduction_epoch",
        "reduction_valid_mask_domain",
        "source_generations",
        "allocation_generations",
        "_issuer",
        "_nonce",
    )

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError(
            "HipFgmresCheckpointPredecessorReceiptV2 is context-issued only."
        )

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("predecessor receipts are immutable")

    @classmethod
    def _issue(cls, mint: object, **values: Any) -> Any:
        if mint is not _RECEIPT_MINT:
            raise TypeError("invalid predecessor receipt mint")
        receipt = object.__new__(cls)
        for name in cls.__slots__:
            object.__setattr__(receipt, name, values[name])
        return receipt


class HipFgmresCheckpointTransactionReceiptV2:
    """Nonconstructible process-local state capability for one transaction."""

    __slots__ = (
        "transaction_id",
        "predecessor_id",
        "evidence_scope",
        "authoritative_predecessor_proven",
        "live_krylov_parent_integrated",
        "promotion_eligible",
        "completion_fence_authoritative",
        "state",
        "checkpoint_schedule_hash",
        "combined_abi_hash",
        "kernel_identity_hash",
        "attempted_launch_count",
        "accepted_launch_count_lower_bound",
        "accepted_launch_count_upper_bound",
        "completion_fence_observed",
        "poisoned",
        "_issuer",
        "_nonce",
    )

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError(
            "HipFgmresCheckpointTransactionReceiptV2 is context-issued only."
        )

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("transaction receipts are immutable")

    @classmethod
    def _issue(cls, mint: object, **values: Any) -> Any:
        if mint is not _RECEIPT_MINT:
            raise TypeError("invalid transaction receipt mint")
        receipt = object.__new__(cls)
        for name in cls.__slots__:
            object.__setattr__(receipt, name, values[name])
        return receipt


@dataclass(frozen=True, slots=True)
class _AllocationCandidate:
    name: str
    descriptor: HipFgmresDeviceAllocationV2
    runtime: object
    runtime_owner: object
    device_ordinal: int
    pointer_snapshot: int
    nbytes: int
    element_type: FgmresAllocationElementTypeV2
    owner_token: object
    generation: int


@dataclass(frozen=True, slots=True)
class _RegisteredAllocation:
    context_token: object
    candidate: _AllocationCandidate


@dataclass(frozen=True, slots=True)
class _GenerationHighWater:
    runtime: object
    owner_token: object
    generation: int


@dataclass(frozen=True, slots=True)
class _RuntimeDomainWitness:
    key: tuple[str, int]
    representative_runtime: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _CheckpointTransactionLaunchBinding:
    kernel: HipRtcFgmresV2Kernel = field(repr=False, compare=False)
    checkpoint_owner_token: object = field(repr=False, compare=False)
    stream_pointer: int
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    stagnation_checkpoint_limit: int
    absolute_tolerance: float
    relative_tolerance: float
    authoritative_tolerance: float
    stagnation_relative_tolerance: float
    divergence_factor: float
    pointer_values: tuple[int, ...]
    launches: tuple[FgmresV2FirstColumnCheckpointTransactionLaunch, ...] = field(
        repr=False,
        compare=False,
    )
    launch_values: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class _AllocationRegistrationReceipt:
    context_token: object
    candidates: tuple[_AllocationCandidate, ...]
    previous_high_water: tuple[
        tuple[tuple[int, int, int], _GenerationHighWater | None], ...
    ]


_REGISTRY_LOCK = threading.RLock()
_ACTIVE_ALLOCATIONS: dict[tuple[int, int, int], _RegisteredAllocation] = {}
_GENERATION_HIGH_WATER: dict[tuple[int, int, int], _GenerationHighWater] = {}
_RUNTIME_DOMAINS: dict[tuple[str, int], _RuntimeDomainWitness] = {}


class HipFgmresRecurrenceExecutionContextV2:
    """Exclusive caller-attested first-column checkpoint transaction owner."""

    def __init__(
        self,
        *,
        kernel: Any,
        runtime: Any,
        stream: Any,
        device_ordinal: int,
        free_dof_count: int,
        restart_dimension: int,
        max_iterations: int,
        maximum_restart_count: int,
        stagnation_checkpoint_limit: int,
        absolute_tolerance: float,
        relative_tolerance: float,
        authoritative_tolerance: float,
        stagnation_relative_tolerance: float,
        divergence_factor: float,
        buffers: HipFgmresCheckpointBuffersV2,
    ) -> None:
        _validate_canonical_hashes()
        self._queue_lock = threading.RLock()
        self._context_token = object()
        self._kernel = kernel
        self._runtime = runtime
        self._stream = stream
        self._stream_pointer = _runtime_pointer(stream, "/stream")
        self._device_ordinal = _nonnegative_int(device_ordinal, "/device_ordinal")
        self._free_dof_count = _positive_int32(
            free_dof_count, "/dimensions/free_dof_count"
        )
        self._restart_dimension = _bounded_int(
            restart_dimension,
            "/dimensions/restart_dimension",
            1,
            HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        self._max_iterations = _bounded_int(
            max_iterations,
            "/policy/max_iterations",
            1,
            HIP_FGMRES_MAX_ITERATIONS,
        )
        self._maximum_restart_count = _bounded_int(
            maximum_restart_count,
            "/dimensions/maximum_restart_count",
            1,
            HIP_FGMRES_MAX_ITERATIONS,
        )
        expected_restarts = (
            self._max_iterations + self._restart_dimension - 1
        ) // self._restart_dimension
        if self._maximum_restart_count != expected_restarts:
            _fail(
                "hip_fgmres_checkpoint_restart_count_invalid",
                "/dimensions/maximum_restart_count",
                "maximum_restart_count must equal ceil(max_iterations/M).",
            )
        self._stagnation_checkpoint_limit = _bounded_int(
            stagnation_checkpoint_limit,
            "/policy/stagnation_checkpoint_limit",
            2,
            16,
        )
        self._absolute_tolerance = _nonnegative_float64(
            absolute_tolerance, "/policy/absolute_tolerance"
        )
        self._relative_tolerance = _nonnegative_float64(
            relative_tolerance, "/policy/relative_tolerance"
        )
        if self._absolute_tolerance == self._relative_tolerance == 0.0:
            _fail(
                "hip_fgmres_checkpoint_tolerance_invalid",
                "/policy",
                "absolute and relative tolerances must not both be zero.",
            )
        self._authoritative_tolerance = _nonnegative_float64(
            authoritative_tolerance, "/policy/authoritative_tolerance"
        )
        self._stagnation_relative_tolerance = _positive_float64(
            stagnation_relative_tolerance,
            "/policy/stagnation_relative_tolerance",
        )
        if self._stagnation_relative_tolerance >= 1.0:
            _fail(
                "hip_fgmres_checkpoint_stagnation_tolerance_invalid",
                "/policy/stagnation_relative_tolerance",
            )
        self._divergence_factor = _positive_float64(
            divergence_factor, "/policy/divergence_factor"
        )
        if self._divergence_factor <= 1.0:
            _fail(
                "hip_fgmres_checkpoint_divergence_factor_invalid",
                "/policy/divergence_factor",
            )
        if type(buffers) is not HipFgmresCheckpointBuffersV2:
            _fail(
                "hip_fgmres_checkpoint_buffers_invalid",
                "/buffers",
                "Expected an exact HipFgmresCheckpointBuffersV2.",
            )
        self._buffers = buffers
        self._launches = first_column_checkpoint_transaction_launches_v2(
            self._free_dof_count,
            self._restart_dimension,
        )
        self._canonical_launches = self._launches
        self._launch_value_snapshot = _checkpoint_transaction_launch_values(
            self._launches
        )
        if tuple(row.submission_kind for row in self._launches) != (
            _CHECKPOINT_TRANSACTION_SUBMISSION_KINDS
        ):
            _fail(
                "hip_fgmres_checkpoint_schedule_invalid",
                "/contract/checkpoint_schedule/launches",
                "The checkpoint transaction must contain control, vector "
                "preflight, vector commit, and control finalize rows.",
            )
        self._kernel_identity = _validate_kernel_owner(kernel)
        self._kernel_identity_hash = self._kernel_identity.identity_hash
        self._kernel_identity_payload_hash = canonical_hash(
            self._kernel_identity.to_dict()
        )
        self._loaded_runtime = self._validate_runtime(runtime, kernel)
        self._loader_provenance_witness = getattr(
            runtime,
            "_loader_provenance_witness",
            None,
        )
        self._injected_runtime_authority_witness = getattr(
            runtime,
            "_injected_runtime_authority_witness",
            None,
        )
        candidates = _validated_buffer_candidates(
            buffers,
            runtime=runtime,
            device_ordinal=self._device_ordinal,
            free_dof_count=self._free_dof_count,
            restart_dimension=self._restart_dimension,
            maximum_restart_count=self._maximum_restart_count,
        )
        self._pointer_snapshot_items = tuple(
            (candidate.name, candidate.pointer_snapshot) for candidate in candidates
        )
        self._pointer_snapshots = MappingProxyType(dict(self._pointer_snapshot_items))
        self._allocation_candidates = candidates
        self._registered: dict[int, HipFgmresDeviceAllocationV2] = {}
        registration = _register_buffer_set(self._context_token, candidates)
        self._registered = {
            candidate.pointer_snapshot: candidate.descriptor for candidate in candidates
        }
        lease_token = object()
        try:
            (
                acquired_token,
                kernel_binding_snapshot,
            ) = kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
                self._device_ordinal,
                _checkpoint_owner_token=lease_token,
            )
            if acquired_token is not lease_token:
                raise HipFgmresRecurrenceContextV2Error(
                    "hip_fgmres_checkpoint_kernel_lease_failed",
                    "/kernel/lease",
                    "The kernel returned a foreign checkpoint lease token.",
                )
        except BaseException as exc:
            _rollback_buffer_set(registration)
            self._registered.clear()
            cleanup_error: BaseException | None = None
            if kernel._checkpoint_owner_token is lease_token:
                try:
                    kernel._release_checkpoint_transaction_owner_without_work(
                        lease_token
                    )
                except BaseException as cleanup_exc:  # pragma: no cover - defensive
                    cleanup_error = cleanup_exc
            if not isinstance(exc, Exception):
                if cleanup_error is not None:
                    exc.add_note(
                        "checkpoint lease cleanup failed: "
                        + type(cleanup_error).__name__
                    )
                raise
            detail = (
                f"{getattr(exc, 'code', type(exc).__name__)}: "
                f"{getattr(exc, 'message', str(exc))}"
            )
            if cleanup_error is not None:
                detail += "; lease cleanup failed: " + type(cleanup_error).__name__
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_kernel_lease_failed",
                "/kernel/lease",
                detail,
            ) from exc
        self._checkpoint_owner_token = lease_token
        self._kernel_binding_snapshot = kernel_binding_snapshot
        self._canonical_transaction_launch_binding = (
            self._capture_transaction_launch_binding()
        )
        self._state: FgmresCheckpointContextStateV2 = "READY"
        self._kernel_unloaded = False
        self._operation: str | None = None
        self._issuer = object()
        self._issued_predecessor: HipFgmresCheckpointPredecessorReceiptV2 | None = None
        self._predecessor_snapshot: tuple[Any, ...] | None = None
        self._predecessor_consumed = False
        self._last_transaction_receipt: (
            HipFgmresCheckpointTransactionReceiptV2 | None
        ) = None
        self._transaction_snapshot: tuple[Any, ...] | None = None
        self._transaction_predecessor_id: str | None = None
        self._transaction_attempted = 0
        self._transaction_accepted_lower = 0
        self._transaction_accepted_upper = 0
        self._transaction_poisoned = False
        self._completion_fence_observed = False
        self._ack_may_have_completed = False

    @property
    def state(self) -> FgmresCheckpointContextStateV2:
        return self._state

    @property
    def last_transaction_receipt(
        self,
    ) -> HipFgmresCheckpointTransactionReceiptV2 | None:
        return self._last_transaction_receipt

    @property
    def buffers(self) -> HipFgmresCheckpointBuffersV2:
        return self._buffers

    def issue_predecessor_receipt(
        self,
        *,
        schedule_epoch: int,
        reduction_epoch: int,
        source_generations: tuple[tuple[str, int], ...],
        reduction_valid_mask_domain: tuple[int, ...] = (0, 1792, 7936),
    ) -> HipFgmresCheckpointPredecessorReceiptV2:
        """Mint the sole non-promoting caller attestation for this boundary."""

        with self._queue_lock:
            self._require_idle("/predecessor")
            self._require_state("READY", "/predecessor")
            self._validate_authority()
            if self._issued_predecessor is not None:
                _fail(
                    "hip_fgmres_checkpoint_predecessor_already_issued",
                    "/predecessor",
                )
            decide = self._launches[0]
            if type(schedule_epoch) is not int or schedule_epoch != (
                decide.expected_schedule_epoch
            ):
                _fail(
                    "hip_fgmres_checkpoint_predecessor_epoch_invalid",
                    "/predecessor/schedule_epoch",
                )
            if type(reduction_epoch) is not int or reduction_epoch != (
                decide.expected_reduction_epoch
            ):
                _fail(
                    "hip_fgmres_checkpoint_predecessor_epoch_invalid",
                    "/predecessor/reduction_epoch",
                )
            if reduction_valid_mask_domain != tuple(sorted(_VALID_PREDECESSOR_MASKS)):
                _fail(
                    "hip_fgmres_checkpoint_predecessor_mask_invalid",
                    "/predecessor/reduction_valid_mask_domain",
                )
            expected_sources = tuple(
                (candidate.name, candidate.generation)
                for candidate in self._allocation_candidates
                if candidate.name in _CANDIDATE_SOURCE_ROLES
            )
            if (
                type(source_generations) is not tuple
                or any(
                    type(row) is not tuple
                    or len(row) != 2
                    or type(row[0]) is not str
                    or type(row[1]) is not int
                    for row in source_generations
                )
                or source_generations != expected_sources
            ):
                _fail(
                    "hip_fgmres_checkpoint_source_generation_invalid",
                    "/predecessor/source_generations",
                )
            allocation_generations = tuple(
                (candidate.name, candidate.generation)
                for candidate in self._allocation_candidates
            )
            nonce = object()
            receipt = HipFgmresCheckpointPredecessorReceiptV2._issue(
                _RECEIPT_MINT,
                predecessor_id=_next_id("HipFgmresCheckpointPredecessor"),
                evidence_scope=_CALLER_ATTESTED_EVIDENCE_SCOPE,
                authoritative_predecessor_proven=False,
                live_krylov_parent_integrated=False,
                promotion_eligible=False,
                completion_fence_authoritative=True,
                kernel=self._kernel,
                kernel_identity=self._kernel_identity,
                kernel_identity_hash=self._kernel_identity_hash,
                combined_abi_hash=HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
                checkpoint_schedule_hash=(
                    HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
                ),
                stream=self._stream,
                stream_pointer=self._stream_pointer,
                runtime=self._runtime,
                device_ordinal=self._device_ordinal,
                free_dof_count=self._free_dof_count,
                restart_dimension=self._restart_dimension,
                maximum_restart_count=self._maximum_restart_count,
                schedule_epoch=schedule_epoch,
                reduction_epoch=reduction_epoch,
                reduction_valid_mask_domain=reduction_valid_mask_domain,
                source_generations=source_generations,
                allocation_generations=allocation_generations,
                _issuer=self._issuer,
                _nonce=nonce,
            )
            self._issued_predecessor = receipt
            self._predecessor_snapshot = _predecessor_values(receipt)
            return receipt

    def enqueue_checkpoint_transaction(
        self,
        receipt: HipFgmresCheckpointPredecessorReceiptV2,
    ) -> HipFgmresCheckpointTransactionReceiptV2:
        """Enqueue the fixed four-row checkpoint transaction exactly once."""

        with self._queue_lock:
            self._require_idle("/transaction")
            if self._state != "READY":
                _fail(
                    "hip_fgmres_checkpoint_state_invalid",
                    "/transaction",
                    "The predecessor receipt cannot be reused when transaction "
                    f"state is {self._state}.",
                )
            binding = self._validate_authority()
            self._validate_predecessor(receipt)
            predecessor_id = receipt.predecessor_id
            self._predecessor_consumed = True
            self._state = "ENQUEUEING"
            self._operation = "ENQUEUEING"
            attempted = 0
            accepted = 0
            expected_launch_count = len(_CHECKPOINT_TRANSACTION_SUBMISSION_KINDS)
            try:
                try:
                    try:
                        prelaunch_pending = (
                            binding.kernel._checkpoint_pending_stream_count(
                                binding.checkpoint_owner_token
                            )
                        )
                    except Exception as exc:
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_pending_observation_failed",
                            "/transaction/prelaunch_pending_stream_count",
                            launch_disposition="not_attempted",
                            no_work_proven=True,
                        ) from exc
                    if type(prelaunch_pending) is not int or prelaunch_pending != 0:
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_pending_owner_invalid",
                            "/transaction/prelaunch_pending_stream_count",
                            launch_disposition="not_attempted",
                            no_work_proven=False,
                        )
                    for launch in binding.launches:
                        attempted += 1
                        self._require_current_transaction_launch_binding(
                            binding,
                            launch_disposition="not_attempted",
                        )
                        self._launch_transaction_row(launch, binding)
                        accepted += 1
                    self._require_current_transaction_launch_binding(binding)
                    try:
                        postlaunch_pending = (
                            binding.kernel._checkpoint_pending_stream_count(
                                binding.checkpoint_owner_token
                            )
                        )
                    except Exception as exc:
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_pending_observation_failed",
                            "/transaction/postlaunch_pending_stream_count",
                        ) from exc
                    if type(postlaunch_pending) is not int or postlaunch_pending != 1:
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_pending_owner_invalid",
                            "/transaction/postlaunch_pending_stream_count",
                        )
                except Exception as exc:
                    disposition = getattr(exc, "launch_disposition", None)
                    upper = (
                        accepted
                        if disposition in ("not_attempted", "rejected")
                        else min(expected_launch_count, accepted + 1)
                    )
                    effective_attempted = (
                        max(0, attempted - 1)
                        if disposition == "not_attempted"
                        else attempted
                    )
                    explicit_no_work = getattr(exc, "no_work_proven", None)
                    no_work = (
                        explicit_no_work
                        if explicit_no_work is not None
                        else accepted == 0
                        and upper == 0
                        and disposition in ("not_attempted", "rejected")
                    )
                    self._state = (
                        "POISONED_NO_WORK" if no_work else "POISONED_PENDING_FENCE"
                    )
                    self._set_transaction_state(
                        attempted=effective_attempted,
                        lower=accepted,
                        upper=upper,
                        poisoned=True,
                        fence=False,
                    )
                    poisoned = self._mint_transaction_receipt(predecessor_id)
                    poison_error = self._poison_kernel_owner(binding)
                    detail = (
                        f"{getattr(exc, 'code', type(exc).__name__)}: "
                        f"{getattr(exc, 'message', str(exc))}"
                    )
                    if poison_error is not None:
                        detail += (
                            "; kernel poison failed: " + type(poison_error).__name__
                        )
                    raise HipFgmresRecurrenceContextV2Error(
                        "hip_fgmres_checkpoint_transaction_enqueue_failed",
                        f"/transaction/launches/{max(0, attempted - 1)}",
                        detail,
                        transaction_receipt=poisoned,
                    ) from exc
                self._state = "PENDING_FENCE"
                self._set_transaction_state(
                    attempted=expected_launch_count,
                    lower=expected_launch_count,
                    upper=expected_launch_count,
                    poisoned=False,
                    fence=False,
                )
                return self._mint_transaction_receipt(predecessor_id)
            finally:
                self._operation = None

    def _launch_transaction_row(
        self,
        launch: Any,
        binding: _CheckpointTransactionLaunchBinding,
    ) -> None:
        """Dispatch one planner-issued row without deriving a host predicate."""

        if launch.submission_kind == "control":
            self._launch_control(launch, binding)
            return
        if launch.submission_kind == "vector":
            self._launch_vector(launch, binding)
            return
        _fail(
            "hip_fgmres_checkpoint_schedule_invalid",
            "/transaction/launch/submission_kind",
            "The fixed checkpoint planner returned an unsupported row kind.",
        )

    def synchronize_checkpoint_transaction(
        self,
        receipt: HipFgmresCheckpointTransactionReceiptV2,
    ) -> HipFgmresCheckpointTransactionReceiptV2:
        """Observe the stream fence, then acknowledge raw launch ownership."""

        with self._queue_lock:
            self._require_idle("/transaction/fence")
            self._validate_transaction_receipt(receipt)
            if self._state not in (
                "PENDING_FENCE",
                "POISONED_PENDING_FENCE",
                "FENCE_OBSERVED_ACK_PENDING",
            ):
                _fail(
                    "hip_fgmres_checkpoint_state_invalid",
                    "/transaction/fence",
                    f"Cannot fence from state {self._state}.",
                )
            binding = self._validate_authority(allow_poisoned=True)
            retrying_ack = self._state == "FENCE_OBSERVED_ACK_PENDING"
            self._operation = "FENCING"
            try:
                if not retrying_ack:
                    try:
                        result = binding.kernel._synchronize_checkpoint_stream(
                            binding.checkpoint_owner_token,
                            binding.stream_pointer,
                        )
                        if result is not None:
                            _fail(
                                "hip_fgmres_checkpoint_runtime_contract_invalid",
                                "/transaction/fence/synchronize",
                            )
                    except Exception as exc:
                        self._state = "POISONED_PENDING_FENCE"
                        self._transaction_poisoned = True
                        self._completion_fence_observed = False
                        self._poison_kernel_owner(binding)
                        poisoned = self._mint_transaction_receipt()
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_fence_failed",
                            "/transaction/fence/synchronize",
                            f"{getattr(exc, 'code', type(exc).__name__)}: "
                            f"{getattr(exc, 'message', str(exc))}",
                            transaction_receipt=poisoned,
                        ) from exc
                    self._completion_fence_observed = True
                try:
                    reservation_count = (
                        binding.kernel._consume_checkpoint_pending_after_fence(
                            binding.checkpoint_owner_token,
                            binding.stream_pointer,
                        )
                    )
                except Exception as exc:
                    self._state = "FENCE_OBSERVED_ACK_PENDING"
                    self._transaction_poisoned = True
                    self._completion_fence_observed = True
                    self._ack_may_have_completed = True
                    self._poison_kernel_owner(binding)
                    pending = self._mint_transaction_receipt()
                    raise HipFgmresRecurrenceContextV2Error(
                        "hip_fgmres_checkpoint_pending_consume_failed",
                        "/transaction/fence/consume_pending",
                        f"{getattr(exc, 'code', type(exc).__name__)}: "
                        f"{getattr(exc, 'message', str(exc))}",
                        transaction_receipt=pending,
                    ) from exc
                if type(reservation_count) is not int or reservation_count < 0:
                    self._transaction_poisoned = True
                    self._completion_fence_observed = True
                    self._state = "POISONED_FENCED"
                    self._ack_may_have_completed = False
                    self._poison_kernel_owner(binding)
                    invalid = self._mint_transaction_receipt()
                    _fail(
                        "hip_fgmres_checkpoint_pending_consume_invalid",
                        "/transaction/fence/consume_pending",
                        transaction_receipt=invalid,
                    )
                if (
                    retrying_ack
                    and self._ack_may_have_completed
                    and reservation_count == 0
                ):
                    self._state = "POISONED_FENCED"
                    self._transaction_poisoned = True
                    self._completion_fence_observed = True
                    self._ack_may_have_completed = False
                    return self._mint_transaction_receipt()
                count_valid = (
                    self._transaction_accepted_lower
                    <= reservation_count
                    <= self._transaction_accepted_upper
                )
                if not count_valid:
                    self._state = "POISONED_FENCED"
                    self._transaction_poisoned = True
                    self._completion_fence_observed = True
                    self._ack_may_have_completed = False
                    self._poison_kernel_owner(binding)
                    mismatch = self._mint_transaction_receipt()
                    _fail(
                        "hip_fgmres_checkpoint_pending_reservation_mismatch",
                        "/transaction/fence/consume_pending",
                        "The atomically consumed launch reservation count is "
                        "outside the accepted-prefix interval.",
                        transaction_receipt=mismatch,
                    )
                self._state = (
                    "POISONED_FENCED" if self._transaction_poisoned else "FENCED"
                )
                self._completion_fence_observed = True
                self._ack_may_have_completed = False
                return self._mint_transaction_receipt()
            finally:
                self._operation = None

    def close(self) -> None:
        """Unload the exclusively leased kernel after all work is fenced."""

        with self._queue_lock:
            self._require_idle("/lifetime/close")
            if self._state == "CLOSED":
                return
            cleanup_retry = self._state == "CLEANUP_FAILED"
            if not cleanup_retry and self._state not in (
                "READY",
                "FENCED",
                "POISONED_FENCED",
                "POISONED_NO_WORK",
            ):
                _fail(
                    "hip_fgmres_checkpoint_close_fence_required",
                    "/lifetime/close",
                    f"Cannot close from state {self._state}.",
                )
            if not cleanup_retry:
                self._validate_cleanup_authority()
            self._operation = "CLOSING"
            try:
                if not self._kernel_unloaded:
                    try:
                        self._kernel.close(
                            _checkpoint_owner_token=self._checkpoint_owner_token
                        )
                    except Exception as exc:
                        raise HipFgmresRecurrenceContextV2Error(
                            "hip_fgmres_checkpoint_kernel_close_failed",
                            "/lifetime/close/kernel",
                            f"{getattr(exc, 'code', type(exc).__name__)}: "
                            f"{getattr(exc, 'message', str(exc))}",
                        ) from exc
                    self._kernel_unloaded = True
                try:
                    _bulk_release_registered_allocations(
                        self._context_token,
                        self._allocation_candidates,
                    )
                    self._registered.clear()
                except Exception as exc:
                    self._state = "CLEANUP_FAILED"
                    raise HipFgmresRecurrenceContextV2Error(
                        "hip_fgmres_checkpoint_registry_cleanup_failed",
                        "/lifetime/close/registry",
                        f"{getattr(exc, 'code', type(exc).__name__)}: "
                        f"{getattr(exc, 'message', str(exc))}",
                    ) from exc
            finally:
                self._operation = None
            self._state = "CLOSED"

    def release_allocation(self, allocation: HipFgmresDeviceAllocationV2) -> None:
        """Unregister one exact allocation after kernel unload (never free it)."""

        with self._queue_lock:
            self._require_idle("/lifetime/release_allocation")
            self._require_state("CLOSED", "/lifetime/release_allocation")
            if type(allocation) is not HipFgmresDeviceAllocationV2:
                _fail(
                    "hip_fgmres_checkpoint_allocation_invalid",
                    "/lifetime/release_allocation",
                )
            candidate = next(
                (
                    row
                    for row in self._allocation_candidates
                    if row.descriptor is allocation
                ),
                None,
            )
            if candidate is None:
                _fail(
                    "hip_fgmres_checkpoint_allocation_foreign",
                    "/lifetime/release_allocation",
                )
            if candidate.pointer_snapshot not in self._registered:
                return
            if self._registered.get(candidate.pointer_snapshot) is not allocation:
                _fail(
                    "hip_fgmres_checkpoint_allocation_foreign",
                    "/lifetime/release_allocation",
                )
            _release_registered_allocation(self._context_token, candidate)
            del self._registered[candidate.pointer_snapshot]

    def _launch_control(
        self,
        launch: FgmresV2FirstColumnCheckpointTransactionLaunch,
        binding: _CheckpointTransactionLaunchBinding,
    ) -> None:
        result = binding.kernel.launch_control(
            binding.stream_pointer,
            launch.mode,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            launch.row_index,
            launch.pass_index,
            binding.free_dof_count,
            binding.restart_dimension,
            binding.max_iterations,
            binding.maximum_restart_count,
            binding.stagnation_checkpoint_limit,
            binding.absolute_tolerance,
            binding.relative_tolerance,
            binding.authoritative_tolerance,
            binding.stagnation_relative_tolerance,
            binding.divergence_factor,
            *binding.pointer_values[-3:],
            _checkpoint_owner_token=binding.checkpoint_owner_token,
        )
        if result is not None:
            _fail(
                "hip_fgmres_checkpoint_kernel_contract_invalid",
                "/transaction/launch/control",
                "The checkpoint control launch returned a non-None value.",
            )

    def _launch_vector(
        self,
        launch: FgmresV2FirstColumnCheckpointTransactionLaunch,
        binding: _CheckpointTransactionLaunchBinding,
    ) -> None:
        result = binding.kernel.launch_vector(
            binding.stream_pointer,
            launch.mode,
            launch.vector_gate,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            binding.free_dof_count,
            launch.logical_index,
            *binding.pointer_values,
            _checkpoint_owner_token=binding.checkpoint_owner_token,
        )
        if result is not None:
            _fail(
                "hip_fgmres_checkpoint_kernel_contract_invalid",
                "/transaction/launch/vector",
                "The checkpoint vector launch returned a non-None value.",
            )

    def _set_transaction_state(
        self,
        *,
        attempted: int,
        lower: int,
        upper: int,
        fence: bool,
        poisoned: bool,
    ) -> None:
        self._transaction_attempted = attempted
        self._transaction_accepted_lower = lower
        self._transaction_accepted_upper = upper
        self._completion_fence_observed = fence
        self._transaction_poisoned = poisoned

    def _mint_transaction_receipt(
        self,
        predecessor_id: str | None = None,
    ) -> HipFgmresCheckpointTransactionReceiptV2:
        if predecessor_id is not None:
            self._transaction_predecessor_id = predecessor_id
        if self._transaction_predecessor_id is None:
            _fail(
                "hip_fgmres_checkpoint_transaction_receipt_invalid",
                "/transaction/receipt",
            )
        receipt = HipFgmresCheckpointTransactionReceiptV2._issue(
            _RECEIPT_MINT,
            transaction_id=_next_id("HipFgmresCheckpointTransaction"),
            predecessor_id=self._transaction_predecessor_id,
            evidence_scope=_CALLER_ATTESTED_EVIDENCE_SCOPE,
            authoritative_predecessor_proven=False,
            live_krylov_parent_integrated=False,
            promotion_eligible=False,
            completion_fence_authoritative=True,
            state=self._state,
            checkpoint_schedule_hash=(
                HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
            ),
            combined_abi_hash=HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
            kernel_identity_hash=self._kernel_identity_hash,
            attempted_launch_count=self._transaction_attempted,
            accepted_launch_count_lower_bound=self._transaction_accepted_lower,
            accepted_launch_count_upper_bound=self._transaction_accepted_upper,
            completion_fence_observed=self._completion_fence_observed,
            poisoned=self._transaction_poisoned,
            _issuer=self._issuer,
            _nonce=object(),
        )
        self._last_transaction_receipt = receipt
        self._transaction_snapshot = _transaction_values(receipt)
        return receipt

    def _validate_transaction_receipt(
        self,
        receipt: HipFgmresCheckpointTransactionReceiptV2,
    ) -> None:
        if (
            type(receipt) is not HipFgmresCheckpointTransactionReceiptV2
            or receipt is not self._last_transaction_receipt
            or receipt._issuer is not self._issuer
            or self._transaction_snapshot is None
            or _transaction_values(receipt) != self._transaction_snapshot
        ):
            _fail(
                "hip_fgmres_checkpoint_transaction_receipt_invalid",
                "/transaction/receipt",
                "The transaction receipt is forged, mutated, stale, or foreign.",
            )

    def _poison_kernel_owner(
        self,
        binding: _CheckpointTransactionLaunchBinding,
    ) -> Exception | None:
        self._transaction_poisoned = True
        try:
            binding.kernel._poison_checkpoint_transaction_owner(
                binding.checkpoint_owner_token
            )
        except Exception as exc:  # pragma: no cover - defensive cleanup evidence
            return exc
        return None

    def _validate_predecessor(
        self, receipt: HipFgmresCheckpointPredecessorReceiptV2
    ) -> None:
        if (
            type(receipt) is not HipFgmresCheckpointPredecessorReceiptV2
            or receipt is not self._issued_predecessor
            or self._predecessor_consumed
            or receipt._issuer is not self._issuer
            or self._predecessor_snapshot is None
            or _predecessor_values(receipt) != self._predecessor_snapshot
        ):
            _fail(
                "hip_fgmres_checkpoint_predecessor_receipt_invalid",
                "/predecessor",
                "The predecessor receipt is forged, stale, foreign, or consumed.",
            )

    def _validate_runtime(self, runtime: Any, kernel: HipRtcFgmresV2Kernel) -> object:
        if type(runtime) is not _BoundHipContextRuntime:
            _fail(
                "hip_fgmres_checkpoint_runtime_invalid",
                "/runtime",
                "An exact native bound HIP context runtime is required; arbitrary "
                "synchronizer facades are unsafe and not admitted.",
            )
        loaded_runtime = runtime.loaded_runtime
        try:
            raw_loaded_runtime = kernel._validated_binding().loaded_runtime
        except Exception as exc:
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_runtime_binding_invalid",
                "/runtime",
                "The raw kernel compiler-issued runtime binding is invalid.",
            ) from exc
        runtime_identity = getattr(runtime, "runtime_library_identity", None)
        loaded_identity = getattr(loaded_runtime, "library_identity", None)
        injected_runtime_authority_witness = getattr(
            runtime,
            "_injected_runtime_authority_witness",
            None,
        )
        try:
            loader_provenance_witness = (
                loaded_runtime._loader_provenance_witness()
                if type(loaded_runtime) is LoadedHipRuntime
                else None
            )
        except Exception as exc:
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_runtime_provenance_invalid",
                "/runtime/provenance",
            ) from exc
        if (
            loaded_runtime is None
            or loaded_runtime is not raw_loaded_runtime
            or type(getattr(runtime, "device_ordinal", None)) is not int
            or runtime.device_ordinal != self._device_ordinal
            or runtime_identity is None
            or loaded_identity is None
            or runtime_identity != loaded_identity
            or loaded_identity != self._kernel_identity.runtime_library
            or getattr(runtime, "_loader_provenance_witness", None)
            is not loader_provenance_witness
            or (
                type(loaded_runtime) is not LoadedHipRuntime
                and injected_runtime_authority_witness
                is not _INJECTED_HIP_CONTEXT_RUNTIME_MINT
            )
        ):
            _fail(
                "hip_fgmres_checkpoint_runtime_binding_invalid",
                "/runtime",
                "The synchronizer must bind the exact loaded runtime, runtime "
                "library identity, and selected device ordinal used by the raw kernel.",
            )
        return loaded_runtime

    def _capture_transaction_launch_binding(
        self,
    ) -> _CheckpointTransactionLaunchBinding:
        pointer_values = tuple(self._pointer_snapshots[role] for role in _BUFFER_ROLES)
        return _CheckpointTransactionLaunchBinding(
            kernel=self._kernel,
            checkpoint_owner_token=self._checkpoint_owner_token,
            stream_pointer=self._stream_pointer,
            free_dof_count=self._free_dof_count,
            restart_dimension=self._restart_dimension,
            max_iterations=self._max_iterations,
            maximum_restart_count=self._maximum_restart_count,
            stagnation_checkpoint_limit=self._stagnation_checkpoint_limit,
            absolute_tolerance=self._absolute_tolerance,
            relative_tolerance=self._relative_tolerance,
            authoritative_tolerance=self._authoritative_tolerance,
            stagnation_relative_tolerance=self._stagnation_relative_tolerance,
            divergence_factor=self._divergence_factor,
            pointer_values=pointer_values,
            launches=self._launches,
            launch_values=_checkpoint_transaction_launch_values(self._launches),
        )

    def _transaction_launch_binding_matches(
        self,
        binding: _CheckpointTransactionLaunchBinding,
        expected: _CheckpointTransactionLaunchBinding,
    ) -> bool:
        return (
            type(binding) is _CheckpointTransactionLaunchBinding
            and binding.kernel is expected.kernel
            and binding.checkpoint_owner_token is expected.checkpoint_owner_token
            and binding.launches is expected.launches
            and binding == expected
        )

    def _require_current_transaction_launch_binding(
        self,
        expected: _CheckpointTransactionLaunchBinding,
        *,
        launch_disposition: str | None = None,
    ) -> None:
        try:
            current = self._capture_transaction_launch_binding()
        except Exception as exc:
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_launch_binding_changed",
                "/transaction/launch_binding",
                launch_disposition=launch_disposition,
            ) from exc
        if not self._transaction_launch_binding_matches(current, expected):
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_launch_binding_changed",
                "/transaction/launch_binding",
                launch_disposition=launch_disposition,
            )

    def _validate_authority(
        self, *, allow_poisoned: bool = False
    ) -> _CheckpointTransactionLaunchBinding:
        try:
            binding = self._capture_transaction_launch_binding()
            canonical_launches = first_column_checkpoint_transaction_launches_v2(
                binding.free_dof_count,
                binding.restart_dimension,
            )
            canonical_values = _checkpoint_transaction_launch_values(canonical_launches)
        except Exception as exc:
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_schedule_changed",
                "/contract/checkpoint_schedule/launches",
            ) from exc
        if (
            binding.launches is not self._canonical_launches
            or binding.launch_values != self._launch_value_snapshot
            or canonical_values != self._launch_value_snapshot
        ):
            _fail(
                "hip_fgmres_checkpoint_schedule_changed",
                "/contract/checkpoint_schedule/launches",
            )
        canonical_binding = self._canonical_transaction_launch_binding
        if (
            self._runtime is None
            or binding.stream_pointer != canonical_binding.stream_pointer
            or _runtime_pointer(self._stream, "/stream") != binding.stream_pointer
        ):
            _fail(
                "hip_fgmres_checkpoint_stream_changed",
                "/stream",
            )
        if (
            binding.kernel is not canonical_binding.kernel
            or binding.checkpoint_owner_token
            is not canonical_binding.checkpoint_owner_token
        ):
            _fail(
                "hip_fgmres_checkpoint_kernel_binding_changed",
                "/kernel/lease",
            )
        if getattr(binding.kernel, "closed", False):
            _fail("hip_fgmres_checkpoint_kernel_closed", "/kernel")
        if getattr(binding.kernel, "identity", None) is not self._kernel_identity:
            _fail(
                "hip_fgmres_checkpoint_kernel_identity_changed",
                "/kernel/identity",
            )
        try:
            _validate_identity(self._kernel_identity)
            identity_payload_hash = canonical_hash(self._kernel_identity.to_dict())
            kernel_binding_snapshot = binding.kernel._checkpoint_binding_snapshot(
                binding.checkpoint_owner_token
            )
            kernel_runtime_owner = binding.kernel._checkpoint_runtime_owner(
                binding.checkpoint_owner_token
            )
            loader_provenance_witness = (
                self._loaded_runtime._loader_provenance_witness()
                if type(self._loaded_runtime) is LoadedHipRuntime
                else None
            )
        except Exception as exc:
            if "device" in str(getattr(exc, "code", "")):
                raise HipFgmresRecurrenceContextV2Error(
                    "hip_fgmres_checkpoint_device_authority_invalid",
                    "/device_ordinal/current",
                    f"{getattr(exc, 'code', type(exc).__name__)}: "
                    f"{getattr(exc, 'message', str(exc))}",
                ) from exc
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_kernel_identity_changed",
                "/kernel/identity",
            ) from exc
        if (
            type(self._pointer_snapshots) is not MappingProxyType
            or tuple(self._pointer_snapshots.items()) != self._pointer_snapshot_items
            or binding.pointer_values != canonical_binding.pointer_values
            or self._pointer_snapshot_items
            != tuple(
                (candidate.name, candidate.pointer_snapshot)
                for candidate in self._allocation_candidates
            )
        ):
            _fail(
                "hip_fgmres_checkpoint_pointer_snapshot_changed",
                "/buffers/pointer_snapshots",
                "The immutable launch pointer snapshot changed after registration.",
            )
        policy_fields = (
            "free_dof_count",
            "restart_dimension",
            "max_iterations",
            "maximum_restart_count",
            "stagnation_checkpoint_limit",
            "absolute_tolerance",
            "relative_tolerance",
            "authoritative_tolerance",
            "stagnation_relative_tolerance",
            "divergence_factor",
        )
        if any(
            getattr(binding, name) != getattr(canonical_binding, name)
            for name in policy_fields
        ):
            _fail(
                "hip_fgmres_checkpoint_policy_binding_changed",
                "/policy",
            )
        if (
            self._kernel_identity.kernel_interface_hash
            != HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
            or self._kernel_identity.identity_hash != self._kernel_identity_hash
            or self._kernel_identity.source_sha256 != HIP_FGMRES_RTC_SOURCE_SHA256_V2
            or identity_payload_hash != self._kernel_identity_payload_hash
            or kernel_binding_snapshot != self._kernel_binding_snapshot
            or kernel_runtime_owner is not self._loaded_runtime
            or loader_provenance_witness is not self._loader_provenance_witness
            or getattr(self._runtime, "_loader_provenance_witness", None)
            is not self._loader_provenance_witness
            or getattr(
                self._runtime,
                "_injected_runtime_authority_witness",
                None,
            )
            is not self._injected_runtime_authority_witness
            or (
                type(self._loaded_runtime) is not LoadedHipRuntime
                and self._injected_runtime_authority_witness
                is not _INJECTED_HIP_CONTEXT_RUNTIME_MINT
            )
            or getattr(self._runtime, "loaded_runtime", None)
            is not self._loaded_runtime
            or getattr(self._runtime, "runtime_library_identity", None)
            != self._kernel_identity.runtime_library
            or type(getattr(self._runtime, "device_ordinal", None)) is not int
            or self._runtime.device_ordinal != self._device_ordinal
        ):
            _fail(
                "hip_fgmres_checkpoint_kernel_identity_changed",
                "/kernel/identity",
            )
        _validate_registered_buffer_set(
            self._context_token,
            self._buffers,
            self._allocation_candidates,
            self._registered,
        )
        if not allow_poisoned and self._state.startswith("POISONED"):
            _fail("hip_fgmres_checkpoint_context_poisoned", "/lifetime")
        return binding

    def _validate_cleanup_authority(self) -> None:
        """Validate only private raw ownership needed to unload and unregister."""

        try:
            kernel_binding_snapshot = self._kernel._checkpoint_binding_snapshot(
                self._checkpoint_owner_token
            )
        except Exception as exc:
            if "device" in str(getattr(exc, "code", "")):
                raise HipFgmresRecurrenceContextV2Error(
                    "hip_fgmres_checkpoint_device_authority_invalid",
                    "/lifetime/close/device_ordinal",
                    f"{getattr(exc, 'code', type(exc).__name__)}: "
                    f"{getattr(exc, 'message', str(exc))}",
                ) from exc
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_kernel_binding_changed",
                "/lifetime/close/kernel",
            ) from exc
        if kernel_binding_snapshot != self._kernel_binding_snapshot:
            _fail(
                "hip_fgmres_checkpoint_kernel_binding_changed",
                "/lifetime/close/kernel",
            )

    def _require_idle(self, path: str) -> None:
        if self._operation is not None:
            _fail(
                "hip_fgmres_checkpoint_reentrant_operation",
                path,
                f"Operation {self._operation} is already active.",
            )

    def _require_state(self, expected: str, path: str) -> None:
        if self._state != expected:
            _fail(
                "hip_fgmres_checkpoint_state_invalid",
                path,
                f"Expected {expected}, observed {self._state}.",
            )


def _validate_canonical_hashes() -> None:
    if (
        canonical_hash(
            hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
        )
        != HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
    ):
        _fail(
            "hip_fgmres_checkpoint_schedule_hash_invalid",
            "/contract/checkpoint_schedule_hash",
        )
    if (
        canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
        != HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
    ):
        _fail(
            "hip_fgmres_checkpoint_combined_abi_hash_invalid",
            "/contract/combined_abi_hash",
        )


def _validate_kernel_owner(kernel: Any) -> Any:
    if type(kernel) is not HipRtcFgmresV2Kernel:
        _fail(
            "hip_fgmres_checkpoint_kernel_invalid",
            "/kernel",
            "An exact HipRtcFgmresV2Kernel is required; proxies are not admitted.",
        )
    identity = getattr(kernel, "identity", None)
    try:
        kernel._validated_binding()
        _validate_identity(identity)
    except Exception as exc:
        raise HipFgmresRecurrenceContextV2Error(
            "hip_fgmres_checkpoint_kernel_identity_invalid",
            "/kernel/identity",
        ) from exc
    if (
        identity is None
        or getattr(identity, "kernel_interface_hash", None)
        != HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
        or getattr(identity, "source_sha256", None) != HIP_FGMRES_RTC_SOURCE_SHA256_V2
        or type(getattr(identity, "identity_hash", None)) is not str
        or not identity.identity_hash.startswith("sha256:")
        or getattr(kernel, "closed", False)
    ):
        _fail(
            "hip_fgmres_checkpoint_kernel_identity_invalid",
            "/kernel/identity",
        )
    try:
        pending = kernel.pending_stream_count
    except (AttributeError, TypeError, ValueError) as exc:
        raise HipFgmresRecurrenceContextV2Error(
            "hip_fgmres_checkpoint_kernel_invalid",
            "/kernel/pending_stream_count",
        ) from exc
    if type(pending) is not int or pending != 0:
        _fail(
            "hip_fgmres_checkpoint_preexisting_fence_required",
            "/kernel/pending_stream_count",
            "The raw kernel must have no pending launch when leased.",
        )
    return identity


def _required_layout(
    free_dof_count: int,
    restart_dimension: int,
    maximum_restart_count: int,
) -> dict[str, tuple[str, int]]:
    f = free_dof_count
    m = restart_dimension
    return {
        "reduced_state": ("f64", 8 * f),
        "reduced_load": ("f64", 8 * f),
        "inverse_diagonal": ("f64", 8 * f),
        "solution_x": ("f64", 8 * f),
        "true_residual": ("f64", 8 * f),
        "work_w": ("f64", 8 * f),
        "basis_v": ("f64", 8 * (m + 1) * f),
        "basis_z": ("f64", 8 * m * f),
        "dense": ("f64", 8 * (m * m + 5 * m + 1)),
        "control_state": ("u8", HIP_FGMRES_CONTROL_STATE_BYTES_V2),
        "solve_record": ("u8", solve_record_byte_length_v2(maximum_restart_count)),
    }


def _validated_buffer_candidates(
    buffers: HipFgmresCheckpointBuffersV2,
    *,
    runtime: object,
    device_ordinal: int,
    free_dof_count: int,
    restart_dimension: int,
    maximum_restart_count: int,
) -> tuple[_AllocationCandidate, ...]:
    layout = _required_layout(
        free_dof_count,
        restart_dimension,
        maximum_restart_count,
    )
    candidates: list[_AllocationCandidate] = []
    allocation_owner: object | None = None
    for name, allocation in buffers.items():
        if type(allocation) is not HipFgmresDeviceAllocationV2:
            _fail(
                "hip_fgmres_checkpoint_allocation_invalid",
                f"/buffers/{name}",
            )
        base = allocation.base
        pointer_snapshot = allocation.pointer_snapshot
        nbytes = allocation.nbytes
        element_type = allocation.element_type
        owner_token = allocation.owner_token
        generation = allocation.generation
        allocation_runtime = allocation.runtime
        allocation_device = allocation.device_ordinal
        pointer = _runtime_pointer(base, f"/buffers/{name}/base")
        expected_type, expected_bytes = layout[name]
        if allocation_owner is None:
            allocation_owner = owner_token
        if (
            type(pointer_snapshot) is not int
            or pointer_snapshot != pointer
            or type(nbytes) is not int
            or nbytes != expected_bytes
            or element_type != expected_type
            or owner_token is None
            or owner_token is not allocation_owner
            or type(generation) is not int
            or generation < 1
            or allocation_runtime is not runtime
            or type(allocation_device) is not int
            or allocation_device != device_ordinal
        ):
            _fail(
                "hip_fgmres_checkpoint_allocation_contract_invalid",
                f"/buffers/{name}",
                "Allocation base, exact extent, type, owner lineage, generation, "
                "runtime, or device differs.",
            )
        required_alignment = (
            8
            if expected_type == "f64" or name in {"control_state", "solve_record"}
            else 1
        )
        if pointer % required_alignment != 0:
            _fail(
                "hip_fgmres_checkpoint_allocation_alignment_invalid",
                f"/buffers/{name}/base",
                f"{name} allocation base must be aligned to "
                f"{required_alignment} bytes.",
            )
        end = pointer + nbytes
        if end <= pointer or end - 1 > _UINTPTR_MAX:
            _fail(
                "hip_fgmres_checkpoint_allocation_range_overflow",
                f"/buffers/{name}",
            )
        candidates.append(
            _AllocationCandidate(
                name=name,
                descriptor=allocation,
                runtime=allocation_runtime,
                runtime_owner=_registered_runtime_owner(allocation_runtime),
                device_ordinal=allocation_device,
                pointer_snapshot=pointer_snapshot,
                nbytes=nbytes,
                element_type=element_type,
                owner_token=owner_token,
                generation=generation,
            )
        )
    ordered = sorted(candidates, key=lambda row: row.pointer_snapshot)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if right.pointer_snapshot < left.pointer_snapshot + left.nbytes:
            _fail(
                "hip_fgmres_checkpoint_allocation_range_overlap",
                f"/buffers/{right.name}",
                f"{left.name} and {right.name} allocation ranges overlap.",
            )
    return tuple(candidates)


def _register_buffer_set(
    context_token: object,
    candidates: tuple[_AllocationCandidate, ...],
) -> _AllocationRegistrationReceipt:
    with _REGISTRY_LOCK:
        for candidate in candidates:
            active_key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            if active_key in _ACTIVE_ALLOCATIONS:
                _fail(
                    "hip_fgmres_checkpoint_allocation_already_registered",
                    "/buffers",
                )
            start = candidate.pointer_snapshot
            end = start + candidate.nbytes
            for active in _ACTIVE_ALLOCATIONS.values():
                active_candidate = active.candidate
                if (
                    active_candidate.runtime_owner is candidate.runtime_owner
                    and active_candidate.device_ordinal == candidate.device_ordinal
                    and start
                    < active_candidate.pointer_snapshot + active_candidate.nbytes
                    and active_candidate.pointer_snapshot < end
                ):
                    _fail(
                        "hip_fgmres_checkpoint_allocation_range_registered",
                        "/buffers",
                        "An allocation range overlaps a range registered by "
                        "another live context.",
                    )
            lineage_key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            previous = _GENERATION_HIGH_WATER.get(lineage_key)
            if previous is not None and candidate.generation <= previous.generation:
                _fail(
                    "hip_fgmres_checkpoint_allocation_generation_stale",
                    "/buffers",
                )
        previous_rows: list[
            tuple[tuple[int, int, int], _GenerationHighWater | None]
        ] = []
        for candidate in candidates:
            active_key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            lineage_key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            previous_rows.append((lineage_key, _GENERATION_HIGH_WATER.get(lineage_key)))
            _ACTIVE_ALLOCATIONS[active_key] = _RegisteredAllocation(
                context_token,
                candidate,
            )
            _GENERATION_HIGH_WATER[lineage_key] = _GenerationHighWater(
                candidate.runtime_owner,
                candidate.owner_token,
                candidate.generation,
            )
        return _AllocationRegistrationReceipt(
            context_token=context_token,
            candidates=candidates,
            previous_high_water=tuple(previous_rows),
        )


def _registered_runtime_owner(runtime: object) -> object:
    if type(runtime) is not _BoundHipContextRuntime:
        _fail(
            "hip_fgmres_checkpoint_runtime_binding_invalid",
            "/buffers/runtime",
        )
    loaded_runtime = runtime.loaded_runtime
    if type(loaded_runtime) is LoadedHipRuntime:
        try:
            loaded_runtime._loader_provenance_witness()
        except Exception as exc:
            raise HipFgmresRecurrenceContextV2Error(
                "hip_fgmres_checkpoint_runtime_provenance_invalid",
                "/buffers/runtime/domain",
            ) from exc
        # Engine v2 does not yet own explicit HIP context handles.  Separate
        # libamdhip64 dlopen handles can still address the same process/device
        # primary-context VA domain, so every exact native wrapper is
        # conservatively unified.  The allocation registry key separately
        # includes the selected device ordinal.  A later explicit-context
        # owner may refine this key with an authoritative hipCtxGetCurrent
        # witness, never with Python wrapper or CDLL object identity.
        key = ("native_process_runtime_domain", 0)
    else:
        if (
            getattr(runtime, "_injected_runtime_authority_witness", None)
            is not _INJECTED_HIP_CONTEXT_RUNTIME_MINT
        ):
            _fail(
                "hip_fgmres_checkpoint_runtime_provenance_invalid",
                "/buffers/runtime/domain",
            )
        key = ("injected_runtime_object", id(loaded_runtime))
    with _REGISTRY_LOCK:
        witness = _RUNTIME_DOMAINS.get(key)
        if witness is None:
            witness = _RuntimeDomainWitness(key, loaded_runtime)
            _RUNTIME_DOMAINS[key] = witness
        elif (
            key[0] == "injected_runtime_object"
            and witness.representative_runtime is not loaded_runtime
        ):
            _fail(
                "hip_fgmres_checkpoint_runtime_domain_changed",
                "/buffers/runtime/domain",
            )
        return witness


def _rollback_buffer_set(receipt: _AllocationRegistrationReceipt) -> None:
    with _REGISTRY_LOCK:
        for candidate in receipt.candidates:
            key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            row = _ACTIVE_ALLOCATIONS.get(key)
            if row is not None and row.context_token is receipt.context_token:
                del _ACTIVE_ALLOCATIONS[key]
        for key, previous in receipt.previous_high_water:
            if previous is None:
                _GENERATION_HIGH_WATER.pop(key, None)
            else:
                _GENERATION_HIGH_WATER[key] = previous


def _validate_registered_buffer_set(
    context_token: object,
    buffers: HipFgmresCheckpointBuffersV2,
    candidates: tuple[_AllocationCandidate, ...],
    registered: dict[int, HipFgmresDeviceAllocationV2],
) -> None:
    with _REGISTRY_LOCK:
        for candidate in candidates:
            allocation = getattr(buffers, candidate.name)
            if (
                _runtime_pointer(allocation.base, "/buffers/base")
                != candidate.pointer_snapshot
            ):
                _fail(
                    "hip_fgmres_checkpoint_allocation_base_changed",
                    "/buffers",
                    "An allocation base object changed after registration.",
                )
            key = (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            row = _ACTIVE_ALLOCATIONS.get(key)
            if (
                allocation is not candidate.descriptor
                or registered.get(candidate.pointer_snapshot) is not allocation
                or row is None
                or row.context_token is not context_token
                or row.candidate is not candidate
                or allocation.runtime is not candidate.runtime
                or _registered_runtime_owner(allocation.runtime)
                is not candidate.runtime_owner
                or allocation.device_ordinal != candidate.device_ordinal
                or allocation.pointer_snapshot != candidate.pointer_snapshot
                or allocation.nbytes != candidate.nbytes
                or allocation.element_type != candidate.element_type
                or allocation.owner_token is not candidate.owner_token
                or allocation.generation != candidate.generation
            ):
                _fail(
                    "hip_fgmres_checkpoint_allocation_registration_changed",
                    "/buffers",
                )


def _release_registered_allocation(
    context_token: object,
    candidate: _AllocationCandidate,
) -> None:
    key = (
        id(candidate.runtime_owner),
        candidate.device_ordinal,
        candidate.pointer_snapshot,
    )
    with _REGISTRY_LOCK:
        row = _ACTIVE_ALLOCATIONS.get(key)
        if (
            row is None
            or row.context_token is not context_token
            or row.candidate is not candidate
        ):
            _fail(
                "hip_fgmres_checkpoint_allocation_registration_changed",
                "/lifetime/release_allocation",
            )
        del _ACTIVE_ALLOCATIONS[key]


def _bulk_release_registered_allocations(
    context_token: object,
    candidates: tuple[_AllocationCandidate, ...],
) -> None:
    with _REGISTRY_LOCK:
        keys = tuple(
            (
                id(candidate.runtime_owner),
                candidate.device_ordinal,
                candidate.pointer_snapshot,
            )
            for candidate in candidates
        )
        for key, candidate in zip(keys, candidates, strict=True):
            row = _ACTIVE_ALLOCATIONS.get(key)
            if (
                row is None
                or row.context_token is not context_token
                or row.candidate is not candidate
            ):
                _fail(
                    "hip_fgmres_checkpoint_allocation_registration_changed",
                    "/lifetime/close/registry",
                )
        for key in keys:
            del _ACTIVE_ALLOCATIONS[key]


def _checkpoint_transaction_launch_values(
    launches: object,
) -> tuple[tuple[Any, ...], ...]:
    if type(launches) is not tuple or len(launches) != len(
        _CHECKPOINT_TRANSACTION_SUBMISSION_KINDS
    ):
        _fail(
            "hip_fgmres_checkpoint_schedule_invalid",
            "/contract/checkpoint_schedule/launches",
        )
    rows: list[tuple[Any, ...]] = []
    for launch in launches:
        if type(launch) is not FgmresV2FirstColumnCheckpointTransactionLaunch:
            _fail(
                "hip_fgmres_checkpoint_schedule_invalid",
                "/contract/checkpoint_schedule/launches",
            )
        rows.append(
            tuple(
                getattr(launch, name)
                for name in _CHECKPOINT_TRANSACTION_LAUNCH_FIELD_NAMES
            )
        )
    return tuple(rows)


def _predecessor_values(
    receipt: HipFgmresCheckpointPredecessorReceiptV2,
) -> tuple[Any, ...]:
    return (
        receipt.predecessor_id,
        receipt.evidence_scope,
        receipt.authoritative_predecessor_proven,
        receipt.live_krylov_parent_integrated,
        receipt.promotion_eligible,
        receipt.completion_fence_authoritative,
        id(receipt.kernel),
        id(receipt.kernel_identity),
        receipt.kernel_identity_hash,
        receipt.combined_abi_hash,
        receipt.checkpoint_schedule_hash,
        id(receipt.stream),
        _receipt_pointer_value(receipt.stream),
        receipt.stream_pointer,
        id(receipt.runtime),
        receipt.device_ordinal,
        receipt.free_dof_count,
        receipt.restart_dimension,
        receipt.maximum_restart_count,
        receipt.schedule_epoch,
        receipt.reduction_epoch,
        tuple(receipt.reduction_valid_mask_domain),
        tuple(tuple(row) for row in receipt.source_generations),
        tuple(tuple(row) for row in receipt.allocation_generations),
        id(receipt._issuer),
        id(receipt._nonce),
    )


def _transaction_values(
    receipt: HipFgmresCheckpointTransactionReceiptV2,
) -> tuple[Any, ...]:
    return (
        receipt.transaction_id,
        receipt.predecessor_id,
        receipt.evidence_scope,
        receipt.authoritative_predecessor_proven,
        receipt.live_krylov_parent_integrated,
        receipt.promotion_eligible,
        receipt.completion_fence_authoritative,
        receipt.state,
        receipt.checkpoint_schedule_hash,
        receipt.combined_abi_hash,
        receipt.kernel_identity_hash,
        receipt.attempted_launch_count,
        receipt.accepted_launch_count_lower_bound,
        receipt.accepted_launch_count_upper_bound,
        receipt.completion_fence_observed,
        receipt.poisoned,
        id(receipt._issuer),
        id(receipt._nonce),
    )


def _receipt_pointer_value(value: Any) -> int | None:
    if isinstance(value, ctypes.c_void_p):
        return value.value
    if type(value) is int:
        return value
    raw = getattr(value, "value", None)
    return raw if type(raw) is int else None


def _next_id(prefix: str) -> str:
    with _ID_LOCK:
        value = next(_ID_COUNTER)
    return f"{prefix}:{value}"


def _runtime_pointer(value: Any, path: str) -> int:
    try:
        pointer = _pointer_integer(value, path)
    except HipRtcError as exc:
        raise HipFgmresRecurrenceContextV2Error(
            "hip_fgmres_checkpoint_pointer_invalid",
            path,
            exc.message,
        ) from exc
    if pointer > _UINTPTR_MAX or ctypes.c_void_p(pointer).value != pointer:
        _fail("hip_fgmres_checkpoint_pointer_invalid", path)
    return pointer


def _bounded_int(value: Any, path: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(
            "hip_fgmres_checkpoint_integer_invalid",
            path,
            f"Expected an exact int in [{minimum}, {maximum}].",
        )
    return value


def _positive_int32(value: Any, path: str) -> int:
    return _bounded_int(value, path, 1, (1 << 31) - 1)


def _nonnegative_int(value: Any, path: str) -> int:
    return _bounded_int(value, path, 0, (1 << 31) - 1)


def _finite_float64(value: Any, path: str) -> float:
    if type(value) not in (int, float):
        _fail("hip_fgmres_checkpoint_float_invalid", path)
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise HipFgmresRecurrenceContextV2Error(
            "hip_fgmres_checkpoint_float_invalid", path
        ) from exc
    if not math.isfinite(converted):
        _fail("hip_fgmres_checkpoint_float_invalid", path)
    return converted


def _nonnegative_float64(value: Any, path: str) -> float:
    converted = _finite_float64(value, path)
    if converted < 0.0:
        _fail("hip_fgmres_checkpoint_float_invalid", path)
    return 0.0 if converted == 0.0 else converted


def _positive_float64(value: Any, path: str) -> float:
    converted = _finite_float64(value, path)
    if converted <= 0.0:
        _fail("hip_fgmres_checkpoint_float_invalid", path)
    return converted


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    transaction_receipt: HipFgmresCheckpointTransactionReceiptV2 | None = None,
) -> Any:
    raise HipFgmresRecurrenceContextV2Error(
        code,
        path,
        message,
        transaction_receipt=transaction_receipt,
    )


__all__ = [
    "HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2",
    "HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2",
    "FgmresAllocationElementTypeV2",
    "FgmresCheckpointContextStateV2",
    "HipFgmresCheckpointBuffersV2",
    "HipFgmresCheckpointPredecessorReceiptV2",
    "HipFgmresCheckpointTransactionReceiptV2",
    "HipFgmresDeviceAllocationV2",
    "HipFgmresRecurrenceContextV2Error",
    "HipFgmresRecurrenceExecutionContextV2",
]
