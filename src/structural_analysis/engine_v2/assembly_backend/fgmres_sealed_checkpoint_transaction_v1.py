"""Canonical-capability-consuming first-column checkpoint transaction.

The context in this module is a non-owning child of a still-open canonical
predecessor producer.  It borrows the exact live kernel, checkpoint owner,
stream, and direct eleven allocation projection, consumes the canonical
predecessor capability once, submits the fixed four-row transaction, and
observes one final exact-runtime fence.  It never observes the device mask,
validation verdict, commit gate, or numerical transaction outcome on host.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache, wraps
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import ExecutionPlanV2

from .fgmres_canonical_predecessor_v1 import (
    HipFgmresCanonicalPredecessorCapabilityV1,
    HipFgmresCanonicalPredecessorExecutionContextV1,
    validate_hip_fgmres_canonical_predecessor_capability_v1,
    validate_hip_fgmres_canonical_predecessor_receipt_v1,
)
from .fgmres_context_v2 import (
    HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2,
    HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_first_column_predecessor_validation_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
)
from .fgmres_plan import HipFgmresPlanV1
from .fgmres_rtc_v2 import (
    FgmresV2FirstColumnCheckpointTransactionLaunch,
    HipRtcFgmresV2Kernel,
    canonical_first_column_predecessor_launches_v2,
    first_column_checkpoint_transaction_launches_v2,
    reduction_stage_output_counts_v2,
)
from .fgmres_rtc_launch_fence_ledger_v1 import _launch_descriptor_hash_v1


HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-sealed-checkpoint-transaction.v1"
)
HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_CAPABILITY_PROFILE_V1 = (
    "phase0_canonical_capability_consuming_sealed_checkpoint_transaction"
)
HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_EVIDENCE_SCOPE_V1 = (
    "canonical_capability_consumed_device_outcome_unobserved_non_promoting"
)

SealedCheckpointTransactionStatusV1 = Literal[
    "context_ready",
    "transaction_pending",
    "fence_observed_ack_pending",
    "transaction_fenced",
    "poisoned_no_work",
    "poisoned_pending_fence",
    "poisoned_fence_observed_ack_pending",
    "poisoned_fenced",
    "context_closed",
    "cleanup_failed",
]

_DIRECT_ROLES = (
    "reduced_state",
    "reduced_load",
    "jacobi_inverse",
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_DELEGATED_OPERATOR_ROLES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
)
_DELEGATED_WORKSPACE_ROLES = ("reduction_ping", "reduction_pong")
_PHYSICAL_ROLES = (
    *_DIRECT_ROLES,
    *_DELEGATED_OPERATOR_ROLES,
    *_DELEGATED_WORKSPACE_ROLES,
)
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HEX_ADDRESS_RE = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_DECIMAL_HANDLE_RE = re.compile(
    r"(?i)\b(?:pointer|ptr|handle|stream|module|function|device_address)"
    r"\s*[=:]\s*\d+\b"
)
_SCHEMA_RESOURCE = "hip_fgmres_sealed_checkpoint_transaction_v1.schema.json"


class HipFgmresSealedCheckpointTransactionV1Error(RuntimeError):
    """Stable transaction error retaining retryable cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        pending: HipFgmresSealedCheckpointTransactionPendingV1 | None = None,
        cleanup_owner: HipFgmresSealedCheckpointTransactionExecutionContextV1
        | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.pending = pending
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


class _ImmutableCapability:
    __slots__ = ("__weakref__",)

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")


class HipFgmresSealedCheckpointTransactionPendingV1(_ImmutableCapability):
    """Nonconstructible fence authority for one exact child context."""

    __slots__ = (
        "context_id",
        "attempted_launch_count",
        "accepted_launch_count_lower_bound",
        "accepted_launch_count_upper_bound",
        "_issuer",
        "_nonce",
        "_snapshot",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError(
            "Sealed checkpoint pending capabilities are context-issued only."
        )


class HipFgmresSealedCheckpointContinuationCapabilityV1(_ImmutableCapability):
    """Conditional, outcome-unobserved post-checkpoint continuation authority."""

    __slots__ = (
        "context_id",
        "receipt_hash",
        "canonical_predecessor_context_id",
        "checkpoint_schedule_hash",
        "_issuer",
        "_nonce",
        "_snapshot",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError(
            "Sealed checkpoint continuation capabilities are context-issued only."
        )


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionBindingsV1:
    canonical_predecessor_context_id: str
    canonical_predecessor_receipt_hash: str
    live_context_id: str
    live_opening_receipt_hash: str
    primitive_context_id: str
    primitive_opening_receipt_hash: str
    primitive_evidence_scope: str
    primitive_actual_backend: Literal["hip", "test_double"]
    source_apply_receipt_hash: str
    source_state_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    kernel_origin: Literal["internally_compiled", "caller_supplied"]
    runtime_library_discovery_source: str
    hiprtc_library_discovery_source: str
    canonical_schedule_hash: str
    validator_schedule_hash: str
    checkpoint_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    primitive_parent_lease_epoch: int
    solver_child_lease_epoch: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_stage_count: int
    transaction_launch_count: Literal[4] = 4
    persistent_capability_count: Literal[11] = 11
    physical_capability_count: Literal[16] = 16

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionProjectionV1:
    persistent_roles: tuple[str, ...]
    delegated_operator_roles: tuple[str, ...]
    delegated_workspace_roles: tuple[str, ...]
    pointer_values_serialized: Literal[False] = False
    additional_allocation_count: Literal[0] = 0
    additional_device_bytes: Literal[0] = 0
    additional_borrow_count: Literal[0] = 0
    additional_checkpoint_owner_count: Literal[0] = 0
    additional_module_load_count: Literal[0] = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "persistent_roles": list(self.persistent_roles),
            "delegated_operator_roles": list(self.delegated_operator_roles),
            "delegated_workspace_roles": list(self.delegated_workspace_roles),
            "pointer_values_serialized": False,
            "additional_allocation_count": 0,
            "additional_device_bytes": 0,
            "additional_borrow_count": 0,
            "additional_checkpoint_owner_count": 0,
            "additional_module_load_count": 0,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionTelemetryV1:
    predecessor_capability_reservation_count: Literal[1] = 1
    predecessor_capability_consume_count: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_accept_lower_bound: int = 0
    kernel_launch_accept_upper_bound: int = 0
    fence_attempt_count: int = 0
    fence_success_count: int = 0
    pending_consume_attempt_count: int = 0
    consumed_launch_count: int = 0
    allocation_count: Literal[0] = 0
    allocation_borrow_count: Literal[0] = 0
    checkpoint_owner_acquire_count: Literal[0] = 0
    module_load_count: Literal[0] = 0
    module_unload_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    d2h_operation_count: Literal[0] = 0
    intermediate_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionClaimsV1:
    live_krylov_parent_bound: bool
    canonical_predecessor_capability_reserved: bool
    canonical_predecessor_capability_consumed: bool
    direct11_physical16_continuity_bound: bool
    same_runtime_device_stream_bound: bool
    fixed_four_row_program_bound: bool
    fixed_four_row_transaction_fenced: bool
    device_seal_transition_program_bound: bool
    invalid_source_destination_atomicity_contract_bound: bool
    conditional_post_checkpoint_capability_issued: bool
    device_validation_outcome_host_observed: Literal[False] = False
    actual_mask_host_observed: Literal[False] = False
    commit_gate_host_observed: Literal[False] = False
    checkpoint_commit_host_observed: Literal[False] = False
    authoritative_predecessor_proven: Literal[False] = False
    authoritative_numerical_transaction_proven: Literal[False] = False
    live_solver_ready: Literal[False] = False
    solution_ready: Literal[False] = False
    later_recurrence_ready: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    asymptotic_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionReceiptV1:
    status: SealedCheckpointTransactionStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresSealedCheckpointTransactionReasonV1 | None
    bindings: HipFgmresSealedCheckpointTransactionBindingsV1
    dimensions: HipFgmresSealedCheckpointTransactionDimensionsV1
    projection: HipFgmresSealedCheckpointTransactionProjectionV1
    telemetry: HipFgmresSealedCheckpointTransactionTelemetryV1
    claims: HipFgmresSealedCheckpointTransactionClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresSealedCheckpointTransactionOpenResultV1:
    context: HipFgmresSealedCheckpointTransactionExecutionContextV1
    receipt: HipFgmresSealedCheckpointTransactionReceiptV1

    @property
    def ready(self) -> bool:
        return self.receipt.status == "context_ready" and not self.context.closed


@dataclass(frozen=True, slots=True)
class _SealedTransactionLaunchBinding:
    kernel: HipRtcFgmresV2Kernel
    checkpoint_owner_token: object
    loaded_runtime: Any
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
    launches: tuple[FgmresV2FirstColumnCheckpointTransactionLaunch, ...]
    launch_values: tuple[tuple[tuple[str, Any], ...], ...]
    kernel_binding_snapshot: tuple[Any, ...]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _GlobalRecurrenceChildAuthorityV1:
    """Internal immutable physical-16 witness for one reserved child."""

    kernel: HipRtcFgmresV2Kernel
    checkpoint_owner_token: object
    runtime: Any
    loaded_runtime: Any
    stream: Any
    stream_pointer: int
    device_ordinal: int
    architecture: str
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    stagnation_checkpoint_limit: int
    absolute_tolerance: float
    relative_tolerance: float
    authoritative_tolerance: float
    stagnation_relative_tolerance: float
    divergence_factor: float
    source_fgmres_plan: HipFgmresPlanV1
    source_recurrence_plan: HipFgmresRecurrencePlanV2
    source_execution_plan: ExecutionPlanV2
    direct_capabilities: tuple[Any, ...]
    physical_pointer_values: tuple[tuple[str, int], ...]
    kernel_binding_snapshot: tuple[Any, ...]


class _GlobalRecurrenceChildLeaseV1:
    """Weak-parent lease held strongly only by the downstream owner."""

    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True)
class _GlobalRecurrenceRecoverySnapshotV1:
    """Non-authoritative private view of parent-owned cleanup progress."""

    abandoned: bool
    child_live: bool
    continuation_consumed: bool
    launch_limit: int
    launch_attempt_count: int
    launch_accept_lower_bound: int
    launch_accept_upper_bound: int
    poisoned: bool
    fence_attempt_count: int
    fence_observed: bool
    ack_started: bool
    acknowledged_launch_count: int | None
    released: bool
    terminal: bool


class _GlobalRecurrenceRecoveryCellV1:
    """Parent-owned authority for draining an abandoned global child.

    The cell deliberately holds neither the downstream context nor its lease.
    The only strong token retained here is the already parent-owned checkpoint
    owner token needed by the exact frozen RTC cleanup authority.
    """

    __slots__ = (
        "__weakref__",
        "lease_reference",
        "kernel",
        "checkpoint_owner_token",
        "stream_pointer",
        "launch_limit",
        "launch_attempt_count",
        "launch_accept_lower_bound",
        "launch_accept_upper_bound",
        "poisoned",
        "fence_attempt_count",
        "fence_observed",
        "ack_started",
        "acknowledged_launch_count",
        "released",
        "terminal",
        "abandoned",
        "continuation_consumed",
    )

    def __init__(
        self,
        lease: _GlobalRecurrenceChildLeaseV1,
        *,
        kernel: HipRtcFgmresV2Kernel,
        checkpoint_owner_token: object,
        stream_pointer: int,
        launch_limit: int,
    ) -> None:
        self.kernel = kernel
        self.checkpoint_owner_token = checkpoint_owner_token
        self.stream_pointer = stream_pointer
        self.launch_limit = launch_limit
        self.launch_attempt_count = 0
        self.launch_accept_lower_bound = 0
        self.launch_accept_upper_bound = 0
        self.poisoned = False
        self.fence_attempt_count = 0
        self.fence_observed = False
        self.ack_started = False
        self.acknowledged_launch_count: int | None = None
        self.released = False
        self.terminal = False
        self.abandoned = False
        self.continuation_consumed = False
        cell_reference = weakref.ref(self)

        def mark_abandoned(_lease_reference: object) -> None:
            cell = cell_reference()
            if cell is not None and type(cell.released) is bool and not cell.released:
                # A weakref callback may run on an arbitrary Python thread.  It
                # records liveness only; HIP/runtime calls belong to close().
                cell.abandoned = True

        self.lease_reference = weakref.ref(lease, mark_abandoned)

    def snapshot(self) -> _GlobalRecurrenceRecoverySnapshotV1:
        return _GlobalRecurrenceRecoverySnapshotV1(
            abandoned=self.abandoned,
            child_live=self.lease_reference() is not None,
            continuation_consumed=self.continuation_consumed,
            launch_limit=self.launch_limit,
            launch_attempt_count=self.launch_attempt_count,
            launch_accept_lower_bound=self.launch_accept_lower_bound,
            launch_accept_upper_bound=self.launch_accept_upper_bound,
            poisoned=self.poisoned,
            fence_attempt_count=self.fence_attempt_count,
            fence_observed=self.fence_observed,
            ack_started=self.ack_started,
            acknowledged_launch_count=self.acknowledged_launch_count,
            released=self.released,
            terminal=self.terminal,
        )


def _mint_global_recurrence_child_lease_v1() -> _GlobalRecurrenceChildLeaseV1:
    return _GlobalRecurrenceChildLeaseV1()


_CONTEXT_MINT = object()


def _guard_state_change(name: str) -> Any:
    """Reject same-thread runtime callback re-entry into a state transition."""

    def decorate(operation: Any) -> Any:
        @wraps(operation)
        def guarded(
            self: HipFgmresSealedCheckpointTransactionExecutionContextV1,
            *arguments: Any,
            **keywords: Any,
        ) -> Any:
            with self._lock:
                if self._active_operation is not None:
                    _fail(
                        "hip_fgmres_sealed_checkpoint_transaction_operation_reentrant",
                        f"/{name}/operation",
                        cleanup_owner=self,
                    )
                self._active_operation = name
                try:
                    return operation(self, *arguments, **keywords)
                finally:
                    self._active_operation = None

        return guarded

    return decorate


class HipFgmresSealedCheckpointTransactionExecutionContextV1:
    """Single-use non-owning child over one canonical predecessor context."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError(
                "Sealed checkpoint transaction contexts are factory-issued only."
            )
        self._lock = threading.RLock()
        self._canonical: HipFgmresCanonicalPredecessorExecutionContextV1 | None = None
        self._predecessor_capability: (
            HipFgmresCanonicalPredecessorCapabilityV1 | None
        ) = None
        self._token = object()
        self._binding: _SealedTransactionLaunchBinding | None = None
        self._binding_value_snapshot: tuple[Any, ...] | None = None
        self._bindings: HipFgmresSealedCheckpointTransactionBindingsV1 | None = None
        self._dimensions: HipFgmresSealedCheckpointTransactionDimensionsV1 | None = None
        self._context_id = _ZERO_HASH
        self._telemetry = HipFgmresSealedCheckpointTransactionTelemetryV1()
        self._state: SealedCheckpointTransactionStatusV1 = "context_ready"
        self._reason: HipFgmresSealedCheckpointTransactionReasonV1 | None = None
        self._pending: HipFgmresSealedCheckpointTransactionPendingV1 | None = None
        self._continuation: HipFgmresSealedCheckpointContinuationCapabilityV1 | None = (
            None
        )
        self._pending_nonce = object()
        self._continuation_nonce = object()
        self._pending_consume_started = False
        self._global_recurrence_child_token: (
            weakref.ReferenceType[_GlobalRecurrenceChildLeaseV1] | None
        ) = None
        self._global_recurrence_child_operation: tuple[str, object] | None = None
        self._global_recurrence_child_terminal = False
        self._global_recurrence_recovery_cell: (
            _GlobalRecurrenceRecoveryCellV1 | None
        ) = None
        self._continuation_consumed = False
        self._child_released = False
        self._closed = False
        self._active_operation: str | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def continuation_capability(
        self,
    ) -> HipFgmresSealedCheckpointContinuationCapabilityV1 | None:
        return self._continuation

    def receipt(self) -> HipFgmresSealedCheckpointTransactionReceiptV1:
        with self._lock:
            if self._active_operation is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_receipt_inflight",
                    "/receipt/operation",
                    cleanup_owner=self,
                )
            return self._build_receipt(self._state)

    @_guard_state_change("enqueue")
    def enqueue_sealed_checkpoint_transaction(
        self,
    ) -> HipFgmresSealedCheckpointTransactionPendingV1:
        """Consume the predecessor capability and submit the fixed four rows."""

        with self._lock:
            if self._state != "context_ready" or self._pending is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_state_invalid",
                    "/enqueue",
                    cleanup_owner=self,
                )
            self._validate_reserved_authority()
            canonical = self._require_canonical()
            capability = self._require_predecessor_capability()
            try:
                canonical._consume_sealed_checkpoint_transaction_capability(
                    self._token,
                    capability,
                )
                self._record_predecessor_capability_consumed()
                binding = self._require_binding()
                for index, launch in enumerate(binding.launches):
                    self._require_current_binding(
                        expected_pending_operation_bounds=(index, index),
                        expected_binding=binding,
                    )
                    self._attempt(
                        lambda launch=launch, binding=binding: self._dispatch(
                            binding,
                            launch,
                        )
                    )
                self._require_current_binding(
                    expected_pending_operation_bounds=(4, 4),
                    expected_binding=binding,
                )
                if (
                    self._telemetry.kernel_launch_attempt_count != 4
                    or self._telemetry.kernel_launch_accept_lower_bound != 4
                    or self._telemetry.kernel_launch_accept_upper_bound != 4
                ):
                    raise RuntimeError(
                        "sealed transaction operation accounting mismatch"
                    )
            except BaseException as exc:
                consumed = self._reconcile_predecessor_capability_consumption()
                if consumed:
                    self._poison_after_enqueue_failure(exc)
                if not isinstance(exc, Exception):
                    raise
                if not consumed:
                    raise
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    "hip_fgmres_sealed_checkpoint_transaction_enqueue_failed",
                    "/enqueue",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            self._pending = self._mint_pending()
            return self._pending

    def _record_predecessor_capability_consumed(self) -> None:
        self._telemetry = replace(
            self._telemetry,
            predecessor_capability_consume_count=1,
        )
        self._state = "transaction_pending"

    def _reconcile_predecessor_capability_consumption(self) -> bool:
        """Repair caller state after a consume-return interruption boundary."""

        consumed = self._require_canonical()._sealed_checkpoint_transaction_capability_consumed(
            self._token
        )
        if consumed:
            self._record_predecessor_capability_consumed()
        return consumed

    @_guard_state_change("fence")
    def synchronize_sealed_checkpoint_transaction(
        self,
        pending: HipFgmresSealedCheckpointTransactionPendingV1,
    ) -> HipFgmresSealedCheckpointContinuationCapabilityV1:
        """Fence once, atomically consume four reservations, and mint continuity."""

        with self._lock:
            self._validate_pending(pending)
            if self._state == "transaction_fenced" and self._continuation is not None:
                return self._continuation
            if self._state not in {
                "transaction_pending",
                "poisoned_pending_fence",
                "fence_observed_ack_pending",
                "poisoned_fence_observed_ack_pending",
            }:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_state_invalid",
                    "/fence",
                    cleanup_owner=self,
                )
            self._observe_fence_and_consume()
            if self._state == "poisoned_fenced":
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_poisoned",
                    "/fence",
                    cleanup_owner=self,
                )
            try:
                self._require_current_binding(
                    expected_pending_operation_bounds=(0, 0),
                    expected_binding=self._require_frozen_binding(),
                )
            except Exception as exc:
                self._state = "poisoned_fenced"
                self._set_poison_reason(
                    "hip_fgmres_sealed_checkpoint_transaction_post_fence_authority_invalid",
                    _detail(exc),
                )
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    "hip_fgmres_sealed_checkpoint_transaction_post_fence_authority_invalid",
                    "/fence/post_authority",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            self._state = "transaction_fenced"
            self._continuation = self._mint_continuation()
            return self._continuation

    @_guard_state_change("cleanup")
    def close(self) -> None:
        """Fence pending work and release only the non-owning child reservation."""

        with self._lock:
            if self._closed:
                return
            try:
                self._recover_abandoned_global_recurrence_child()
            except Exception as exc:
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    "hip_fgmres_sealed_checkpoint_transaction_cleanup_failed",
                    "/cleanup/global_recurrence_recovery",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            if self._global_recurrence_child_operation is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
                    "/lifetime/global_recurrence_child/operation",
                    cleanup_owner=self,
                )
            if self._global_recurrence_child_token is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_active",
                    "/lifetime/global_recurrence_child",
                    cleanup_owner=self,
                )
            try:
                if self._state in {
                    "transaction_pending",
                    "poisoned_pending_fence",
                    "fence_observed_ack_pending",
                    "poisoned_fence_observed_ack_pending",
                }:
                    self._observe_fence_and_consume()
                    if self._state == "fence_observed_ack_pending":
                        try:
                            self._require_current_binding(
                                expected_pending_operation_bounds=(0, 0),
                                expected_binding=self._require_frozen_binding(),
                            )
                        except Exception as exc:
                            self._state = "poisoned_fenced"
                            self._set_poison_reason(
                                "hip_fgmres_sealed_checkpoint_transaction_post_fence_authority_invalid",
                                _detail(exc),
                            )
                        else:
                            self._state = "transaction_fenced"
                            self._continuation = self._mint_continuation()
                self._release_child()
            except Exception as exc:
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    "hip_fgmres_sealed_checkpoint_transaction_cleanup_failed",
                    "/cleanup",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"
            with _TRANSACTION_BINDING_LOCK:
                _TRANSACTION_BINDINGS.pop(self, None)

    def _reserve_global_recurrence_child(
        self,
        token: object,
        capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
    ) -> object:
        """Reserve the sole later-recurrence child without consuming continuity."""

        if type(token) is not _GlobalRecurrenceChildLeaseV1:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_token_invalid",
                "/lifetime/global_recurrence_child",
            )
        operation_marker = object()
        try:
            self._begin_global_recurrence_child_operation(
                "reserve",
                operation_marker,
            )
            self._reap_abandoned_global_recurrence_child()
            with self._lock:
                self._require_current_continuation_locked(
                    capability,
                    continuation_consumed=False,
                )
                if (
                    self._global_recurrence_child_terminal
                    or self._global_recurrence_child_token is not None
                ):
                    _fail(
                        "hip_fgmres_sealed_checkpoint_transaction_global_child_unavailable",
                        "/lifetime/global_recurrence_child",
                        cleanup_owner=self,
                    )
            self._require_current_binding(
                expected_pending_operation_bounds=(0, 0),
                expected_binding=self._require_frozen_binding(),
            )
            self._require_exact_empty_pending_map()
            with self._lock:
                self._require_current_continuation_locked(
                    capability,
                    continuation_consumed=False,
                )
                if (
                    self._global_recurrence_child_terminal
                    or self._global_recurrence_child_token is not None
                ):
                    _fail(
                        "hip_fgmres_sealed_checkpoint_transaction_global_child_unavailable",
                        "/lifetime/global_recurrence_child",
                        cleanup_owner=self,
                    )
                self._global_recurrence_child_token = weakref.ref(token)
                return token
        finally:
            self._finish_global_recurrence_child_operation(operation_marker)

    def _register_global_recurrence_recovery_cell(
        self,
        token: object,
        *,
        kernel: HipRtcFgmresV2Kernel,
        checkpoint_owner_token: object,
        stream_pointer: int,
        launch_limit: int,
    ) -> None:
        """Freeze cleanup authority before continuation consumption begins."""

        if (
            type(token) is not _GlobalRecurrenceChildLeaseV1
            or type(kernel) is not HipRtcFgmresV2Kernel
            or type(stream_pointer) is not int
            or stream_pointer <= 0
            or type(launch_limit) is not int
            or launch_limit <= 0
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_recovery_registration_invalid",
                "/lifetime/global_recurrence_child/recovery",
                cleanup_owner=self,
            )
        operation_marker = object()
        try:
            self._begin_global_recurrence_child_operation(
                "register_recovery",
                operation_marker,
            )
            binding = self._require_frozen_binding()
            self._require_current_binding(
                expected_pending_operation_bounds=(0, 0),
                expected_binding=binding,
            )
            with self._lock:
                self._require_global_recurrence_child_locked(
                    token,
                    continuation_consumed=False,
                )
                if (
                    self._global_recurrence_recovery_cell is not None
                    or kernel is not binding.kernel
                    or checkpoint_owner_token is not binding.checkpoint_owner_token
                    or stream_pointer != binding.stream_pointer
                ):
                    _fail(
                        "hip_fgmres_sealed_checkpoint_transaction_global_recovery_registration_invalid",
                        "/lifetime/global_recurrence_child/recovery",
                        cleanup_owner=self,
                    )
                self._global_recurrence_recovery_cell = _GlobalRecurrenceRecoveryCellV1(
                    token,
                    kernel=kernel,
                    checkpoint_owner_token=checkpoint_owner_token,
                    stream_pointer=stream_pointer,
                    launch_limit=launch_limit,
                )
        finally:
            self._finish_global_recurrence_child_operation(operation_marker)

    def _global_recurrence_recovery_snapshot(
        self,
    ) -> _GlobalRecurrenceRecoverySnapshotV1 | None:
        """Return private lifecycle progress without exposing cleanup handles."""

        with self._lock:
            cell = self._global_recurrence_recovery_cell
            return None if cell is None else cell.snapshot()

    def _require_global_recurrence_child(
        self,
        token: object,
        *,
        continuation_consumed: bool | None = None,
    ) -> None:
        """Require the exact active child and, optionally, its consume state."""

        with self._lock:
            if self._global_recurrence_child_operation is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
                    "/lifetime/global_recurrence_child/operation",
                    cleanup_owner=self,
                )
            self._require_global_recurrence_child_locked(
                token,
                continuation_consumed=continuation_consumed,
            )

    def _global_recurrence_child_token_is_active(self, token: object) -> bool:
        """Observe only whether one exact private child token remains active.

        The query deliberately does not require the parent to remain open.  A
        child uses it only to reconcile an exception raised after reserve or
        release changed parent state but before that result reached the child.
        """

        if type(token) is not _GlobalRecurrenceChildLeaseV1:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_token_invalid",
                "/lifetime/global_recurrence_child",
                cleanup_owner=self,
            )
        with self._lock:
            if self._global_recurrence_child_operation is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
                    "/lifetime/global_recurrence_child/operation",
                    cleanup_owner=self,
                )
            active = self._active_global_recurrence_child_locked()
            if active is None:
                cell = self._global_recurrence_recovery_cell
                if (
                    type(cell) is _GlobalRecurrenceRecoveryCellV1
                    and cell.released
                    and not cell.terminal
                    and not self._continuation_consumed
                ):
                    self._global_recurrence_recovery_cell = None
            return token is active

    def _consume_global_recurrence_continuation_capability(
        self,
        token: object,
        capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
    ) -> None:
        """Atomically consume continuation at the later-recurrence enqueue edge."""

        operation_marker = object()
        try:
            self._begin_global_recurrence_child_operation(
                "consume",
                operation_marker,
            )
            with self._lock:
                self._require_global_recurrence_child_locked(
                    token,
                    continuation_consumed=False,
                )
                self._require_current_continuation_locked(
                    capability,
                    continuation_consumed=False,
                )
            self._require_current_binding(
                expected_pending_operation_bounds=(0, 0),
                expected_binding=self._require_frozen_binding(),
            )
            self._require_exact_empty_pending_map()
            with self._lock:
                self._require_global_recurrence_child_locked(
                    token,
                    continuation_consumed=False,
                )
                self._require_current_continuation_locked(
                    capability,
                    continuation_consumed=False,
                )
                cell = self._global_recurrence_recovery_cell
                if (
                    type(cell) is not _GlobalRecurrenceRecoveryCellV1
                    or cell.lease_reference() is not token
                ):
                    self._fail_global_recurrence_recovery_progress_locked()
                self._reconcile_global_recurrence_consumed_locked(cell)
                if cell.continuation_consumed:
                    self._fail_global_recurrence_recovery_progress_locked()
                self._validate_global_recurrence_recovery_cell_locked(cell)
                # This is deliberately the final fallible state change.  A caller
                # interrupted after return can reconcile this shared bit exactly.
                self._continuation_consumed = True
                cell.continuation_consumed = True
        finally:
            self._finish_global_recurrence_child_operation(operation_marker)

    def _global_recurrence_continuation_capability_consumed(
        self,
        token: object,
    ) -> bool:
        """Return the exact parent-owned consume bit for interruption repair."""

        with self._lock:
            if self._global_recurrence_child_operation is not None:
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
                    "/lifetime/global_recurrence_child/operation",
                    cleanup_owner=self,
                )
            self._require_global_recurrence_child_locked(token)
            cell = self._global_recurrence_recovery_cell
            if cell is not None:
                if cell.lease_reference() is not token:
                    self._fail_global_recurrence_recovery_progress_locked()
                self._reconcile_global_recurrence_consumed_locked(cell)
            return self._continuation_consumed

    def _record_global_recurrence_launch_started(self, token: object) -> None:
        """Durably reserve one conservative accepted-work upper bound."""

        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if (
                not cell.continuation_consumed
                or cell.fence_attempt_count != 0
                or cell.ack_started
                or cell.released
                or cell.launch_attempt_count >= cell.launch_limit
                or cell.launch_accept_upper_bound >= cell.launch_limit
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            cell.launch_attempt_count += 1
            # Pessimistically include the row before the fallible dispatch.  A
            # rejected/not-attempted return narrows this bound afterwards.
            cell.launch_accept_upper_bound += 1

    def _record_global_recurrence_launch_succeeded(self, token: object) -> None:
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if (
                cell.launch_accept_lower_bound >= cell.launch_accept_upper_bound
                or cell.launch_accept_lower_bound >= cell.launch_limit
                or cell.fence_attempt_count != 0
                or cell.ack_started
                or cell.released
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            cell.launch_accept_lower_bound += 1

    def _record_global_recurrence_launch_failed(
        self,
        token: object,
        *,
        definitely_not_accepted: bool,
    ) -> None:
        if type(definitely_not_accepted) is not bool:
            self._fail_global_recurrence_recovery_progress_locked()
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if (
                cell.launch_attempt_count == 0
                or cell.launch_accept_upper_bound <= cell.launch_accept_lower_bound
                or cell.fence_attempt_count != 0
                or cell.ack_started
                or cell.released
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            if definitely_not_accepted:
                cell.launch_accept_upper_bound -= 1

    def _record_global_recurrence_poisoned(self, token: object) -> None:
        with self._lock:
            # Poisoning is a fail-safe ledger transition and performs no HIP
            # work.  It must remain possible after a frozen authority mismatch
            # so the live child can close without publishing completion once
            # the exact private field is restored.
            cell = self._require_global_recurrence_poison_cell_locked(token)
            if cell.released:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.poisoned = True

    def _record_global_recurrence_fence_attempt(self, token: object) -> None:
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if cell.ack_started or cell.released:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.fence_attempt_count += 1

    def _global_recurrence_fence_required(self, token: object) -> bool:
        """Reconcile a lost successful-sync return before a live retry."""

        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if cell.ack_started or cell.released:
                self._fail_global_recurrence_recovery_progress_locked()
            if cell.fence_observed:
                return False
            if cell.fence_attempt_count == 0:
                return True
            kernel = cell.kernel
            checkpoint_owner_token = cell.checkpoint_owner_token
            stream_pointer = cell.stream_pointer
        complete = kernel._query_checkpoint_stream_completion(
            checkpoint_owner_token,
            stream_pointer,
        )
        if type(complete) is not bool:
            self._fail_global_recurrence_recovery_progress_locked()
        if not complete:
            return True
        with self._lock:
            current = self._require_global_recurrence_recovery_cell_locked(token)
            if (
                current is not cell
                or current.kernel is not kernel
                or current.checkpoint_owner_token is not checkpoint_owner_token
                or current.stream_pointer != stream_pointer
                or current.ack_started
                or current.released
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            current.fence_observed = True
        return False

    def _record_global_recurrence_fence_observed(self, token: object) -> None:
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if cell.fence_attempt_count <= 0 or cell.ack_started or cell.released:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.fence_observed = True

    def _record_global_recurrence_ack_started(self, token: object) -> None:
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if not cell.fence_observed or cell.released:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.ack_started = True

    def _record_global_recurrence_acknowledged(
        self,
        token: object,
        consumed_launch_count: int,
    ) -> None:
        if type(consumed_launch_count) is not int:
            self._fail_global_recurrence_recovery_progress_locked()
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(token)
            if (
                not cell.ack_started
                or cell.released
                or not cell.launch_accept_lower_bound
                <= consumed_launch_count
                <= cell.launch_accept_upper_bound
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            previous = cell.acknowledged_launch_count
            if previous is not None and previous != consumed_launch_count:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.acknowledged_launch_count = consumed_launch_count

    def _global_recurrence_recovery_progress(
        self,
        token: object,
        *,
        allow_release_in_progress: bool = False,
    ) -> _GlobalRecurrenceRecoverySnapshotV1:
        """Return exact parent-ledger progress to its still-live child only."""

        if type(allow_release_in_progress) is not bool:
            self._fail_global_recurrence_recovery_progress_locked()
        with self._lock:
            cell = self._require_global_recurrence_recovery_cell_locked(
                token,
                allow_release_in_progress=allow_release_in_progress,
            )
            if cell.released:
                if not allow_release_in_progress:
                    self._fail_global_recurrence_recovery_progress_locked()
                pending = cell.kernel._checkpoint_pending_snapshot(
                    cell.checkpoint_owner_token
                )
                if pending != ():
                    self._fail_global_recurrence_recovery_progress_locked()
            return cell.snapshot()

    def _global_recurrence_child_authority(
        self,
        token: object,
        *,
        continuation_consumed: bool,
        expected_pending_operation_bounds: tuple[int, int] = (0, 0),
    ) -> _GlobalRecurrenceChildAuthorityV1:
        """Capture the exact live physical-16 lineage without exposing a dict."""

        if type(continuation_consumed) is not bool:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_continuation_state_invalid",
                "/continuation_capability/consumed",
                cleanup_owner=self,
            )
        if (
            type(expected_pending_operation_bounds) is not tuple
            or len(expected_pending_operation_bounds) != 2
            or any(
                type(value) is not int for value in expected_pending_operation_bounds
            )
            or not 0
            <= expected_pending_operation_bounds[0]
            <= expected_pending_operation_bounds[1]
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_pending_expectation_invalid",
                "/kernel/pending_operation_bounds",
                cleanup_owner=self,
            )
        operation_marker = object()
        try:
            self._begin_global_recurrence_child_operation(
                "authority",
                operation_marker,
            )
            with self._lock:
                self._require_global_recurrence_child_locked(
                    token,
                    continuation_consumed=continuation_consumed,
                )
            binding = self._require_frozen_binding()
            self._require_current_binding(
                expected_pending_operation_bounds=expected_pending_operation_bounds,
                expected_binding=binding,
            )
            canonical = self._require_canonical()
            with canonical._lock:
                canonical._require_sealed_checkpoint_transaction_child(
                    self._token,
                    capability_consumed=True,
                )
                live = canonical._require_live()
                recurrence = live._recurrence_plan
                source_plan = live._source_plan
                projection = canonical._projection
                canonical_bindings = canonical._bindings
                sealed_bindings = self._bindings
                direct = tuple(live._group_capabilities)
                try:
                    delegated = tuple(projection.ordered_resources)
                    physical_pointer_values = tuple(
                        (role, int(canonical._pointers[role]))
                        for role in _PHYSICAL_ROLES
                    )
                    direct_pointer_values = tuple(
                        int(row.pointer_snapshot) for row in direct
                    )
                    delegated_pointer_values = tuple(
                        int(row.pointer_snapshot) for row in delegated
                    )
                except Exception as exc:
                    raise HipFgmresSealedCheckpointTransactionV1Error(
                        "hip_fgmres_sealed_checkpoint_transaction_global_child_authority_invalid",
                        "/authority/physical16",
                        _detail(exc),
                        cleanup_owner=self,
                    ) from exc
                policy = None if source_plan is None else source_plan.policy
                execution_plan = (
                    None if source_plan is None else source_plan._source_execution_plan
                )
                identity = binding.kernel.identity
                if (
                    type(recurrence) is not HipFgmresRecurrencePlanV2
                    or type(source_plan) is not HipFgmresPlanV1
                    or type(execution_plan) is not ExecutionPlanV2
                    or policy is None
                    or projection is None
                    or canonical_bindings is None
                    or sealed_bindings is None
                    or binding.kernel is not live._kernel
                    or binding.checkpoint_owner_token is not live._checkpoint_token
                    or binding.loaded_runtime is not live._loaded_runtime
                    or binding.stream_pointer != live._stream_pointer_snapshot
                    or projection.runtime is not live._runtime
                    or projection.loaded_runtime is not live._loaded_runtime
                    or projection.stream is not live._stream
                    or type(live._device_ordinal) is not int
                    or live._device_ordinal < 0
                    or projection.device_ordinal != live._device_ordinal
                    or type(live._architecture) is not str
                    or not live._architecture
                    or identity.architecture != live._architecture
                    or identity.identity_hash != sealed_bindings.kernel_identity_hash
                    or identity.source_sha256 != sealed_bindings.kernel_source_sha256
                    or tuple(row.role for row in direct) != _DIRECT_ROLES
                    or tuple(row.role for row in delegated)
                    != (*_DELEGATED_OPERATOR_ROLES, *_DELEGATED_WORKSPACE_ROLES)
                    or tuple(role for role, _pointer in physical_pointer_values)
                    != _PHYSICAL_ROLES
                    or tuple(pointer for _role, pointer in physical_pointer_values[:11])
                    != direct_pointer_values
                    or tuple(pointer for _role, pointer in physical_pointer_values[11:])
                    != delegated_pointer_values
                    or binding.pointer_values != direct_pointer_values
                    or len({pointer for _role, pointer in physical_pointer_values})
                    != 16
                    or any(pointer <= 0 for _role, pointer in physical_pointer_values)
                    or binding.free_dof_count != recurrence.free_dof_count
                    or binding.restart_dimension != recurrence.restart_dimension
                    or binding.max_iterations != recurrence.max_iterations
                    or binding.maximum_restart_count != recurrence.maximum_restart_count
                    or binding.stagnation_checkpoint_limit
                    != policy.stagnation_checkpoint_limit
                    or binding.absolute_tolerance != policy.absolute_tolerance
                    or binding.relative_tolerance != policy.relative_tolerance
                    or binding.authoritative_tolerance
                    != source_plan.source_residual_tolerance
                    or binding.stagnation_relative_tolerance
                    != policy.stagnation_relative_tolerance
                    or binding.divergence_factor != policy.divergence_factor
                    or source_plan._source_execution_plan is not execution_plan
                    or recurrence.source_fgmres_plan_hash != source_plan.plan_hash
                    or recurrence.source_execution_plan_hash != execution_plan.plan_hash
                    or sealed_bindings.recurrence_plan_hash != recurrence.plan_hash
                    or binding.kernel_binding_snapshot != live._kernel_binding_snapshot
                    or canonical_bindings.direct_generation_binding_hash
                    != sealed_bindings.direct_generation_binding_hash
                    or canonical_bindings.physical_projection_hash
                    != sealed_bindings.physical_projection_hash
                ):
                    _fail(
                        "hip_fgmres_sealed_checkpoint_transaction_global_child_authority_invalid",
                        "/authority/physical16",
                        cleanup_owner=self,
                    )
                authority = _GlobalRecurrenceChildAuthorityV1(
                    kernel=binding.kernel,
                    checkpoint_owner_token=binding.checkpoint_owner_token,
                    runtime=live._runtime,
                    loaded_runtime=binding.loaded_runtime,
                    stream=live._stream,
                    stream_pointer=binding.stream_pointer,
                    device_ordinal=live._device_ordinal,
                    architecture=live._architecture,
                    free_dof_count=recurrence.free_dof_count,
                    reduced_csr_nnz=recurrence.reduced_csr_nnz,
                    restart_dimension=recurrence.restart_dimension,
                    max_iterations=recurrence.max_iterations,
                    maximum_restart_count=recurrence.maximum_restart_count,
                    stagnation_checkpoint_limit=binding.stagnation_checkpoint_limit,
                    absolute_tolerance=binding.absolute_tolerance,
                    relative_tolerance=binding.relative_tolerance,
                    authoritative_tolerance=binding.authoritative_tolerance,
                    stagnation_relative_tolerance=(
                        binding.stagnation_relative_tolerance
                    ),
                    divergence_factor=binding.divergence_factor,
                    source_fgmres_plan=source_plan,
                    source_recurrence_plan=recurrence,
                    source_execution_plan=execution_plan,
                    direct_capabilities=direct,
                    physical_pointer_values=physical_pointer_values,
                    kernel_binding_snapshot=binding.kernel_binding_snapshot,
                )
            with self._lock:
                self._require_global_recurrence_child_locked(
                    token,
                    continuation_consumed=continuation_consumed,
                )
            return authority
        finally:
            self._finish_global_recurrence_child_operation(operation_marker)

    def _release_global_recurrence_child(self, token: object) -> None:
        """Release only after the shared stream reservation map is exactly empty."""

        operation_marker = object()
        try:
            self._begin_global_recurrence_child_operation(
                "release",
                operation_marker,
            )
            with self._lock:
                self._require_global_recurrence_child_locked(token)
            self._require_exact_empty_pending_map()
            self._require_current_binding(
                expected_pending_operation_bounds=(0, 0),
                expected_binding=self._require_frozen_binding(),
            )
            with self._lock:
                self._require_global_recurrence_child_locked(token)
                cell = self._global_recurrence_recovery_cell
                if cell is not None:
                    if cell.lease_reference() is not token:
                        _fail(
                            "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid",
                            "/lifetime/global_recurrence_child/recovery",
                            cleanup_owner=self,
                        )
                    self._reconcile_global_recurrence_consumed_locked(cell)
                    self._validate_global_recurrence_recovery_cell_locked(
                        cell,
                        allow_release_in_progress=(cell.released is True),
                    )
                    if not cell.released:
                        cell.released = True
                if self._continuation_consumed:
                    if cell is not None and not cell.terminal:
                        cell.terminal = True
                    if not self._global_recurrence_child_terminal:
                        self._global_recurrence_child_terminal = True
                    self._global_recurrence_child_token = None
                else:
                    self._global_recurrence_child_token = None
                    self._global_recurrence_recovery_cell = None
        finally:
            self._finish_global_recurrence_child_operation(operation_marker)

    def _begin_global_recurrence_child_operation(
        self,
        operation: str,
        marker: object,
    ) -> None:
        """Mark a transition while keeping parent locks out of lower callbacks."""

        with self._lock:
            if (
                self._active_operation is not None
                or self._global_recurrence_child_operation is not None
            ):
                _fail(
                    "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
                    "/lifetime/global_recurrence_child/operation",
                    cleanup_owner=self,
                )
            self._global_recurrence_child_operation = (operation, marker)

    def _finish_global_recurrence_child_operation(self, marker: object) -> None:
        with self._lock:
            active = self._global_recurrence_child_operation
            if active is not None and active[1] is marker:
                self._global_recurrence_child_operation = None

    def _require_global_recurrence_child_locked(
        self,
        token: object,
        *,
        continuation_consumed: bool | None = None,
    ) -> None:
        if token is not self._active_global_recurrence_child_locked():
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_token_invalid",
                "/lifetime/global_recurrence_child",
            )
        if self._closed or self._state != "transaction_fenced":
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_unavailable",
                "/lifetime/global_recurrence_child",
                cleanup_owner=self,
            )
        if (
            continuation_consumed is not None
            and self._continuation_consumed is not continuation_consumed
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_continuation_state_invalid",
                "/continuation_capability/consumed",
                cleanup_owner=self,
            )

    def _require_global_recurrence_recovery_cell_locked(
        self,
        token: object,
        *,
        allow_release_in_progress: bool = False,
    ) -> _GlobalRecurrenceRecoveryCellV1:
        if type(allow_release_in_progress) is not bool:
            self._fail_global_recurrence_recovery_progress_locked()
        self._require_global_recurrence_child_locked(
            token,
            continuation_consumed=True,
        )
        cell = self._global_recurrence_recovery_cell
        if (
            type(cell) is not _GlobalRecurrenceRecoveryCellV1
            or cell.lease_reference() is not token
        ):
            self._fail_global_recurrence_recovery_progress_locked()
        self._reconcile_global_recurrence_consumed_locked(cell)
        if not cell.continuation_consumed:
            self._fail_global_recurrence_recovery_progress_locked()
        self._validate_global_recurrence_recovery_cell_locked(
            cell,
            allow_release_in_progress=allow_release_in_progress,
        )
        return cell

    def _require_global_recurrence_poison_cell_locked(
        self,
        token: object,
    ) -> _GlobalRecurrenceRecoveryCellV1:
        """Require exact live ledger state while deliberately doing no HIP work."""

        self._require_global_recurrence_child_locked(
            token,
            continuation_consumed=True,
        )
        cell = self._global_recurrence_recovery_cell
        if (
            type(cell) is not _GlobalRecurrenceRecoveryCellV1
            or cell.lease_reference() is not token
        ):
            self._fail_global_recurrence_recovery_progress_locked()
        self._reconcile_global_recurrence_consumed_locked(cell)
        if not cell.continuation_consumed:
            self._fail_global_recurrence_recovery_progress_locked()
        self._validate_global_recurrence_recovery_ledger_locked(cell)
        return cell

    def _reconcile_global_recurrence_consumed_locked(
        self,
        cell: _GlobalRecurrenceRecoveryCellV1,
    ) -> None:
        """Complete the monotonic parent-bit -> recovery-cell transition."""

        if (
            type(self._continuation_consumed) is not bool
            or type(cell.continuation_consumed) is not bool
        ):
            self._fail_global_recurrence_recovery_progress_locked()
        if self._continuation_consumed:
            if not cell.continuation_consumed:
                cell.continuation_consumed = True
            return
        if cell.continuation_consumed:
            self._fail_global_recurrence_recovery_progress_locked()

    def _fail_global_recurrence_recovery_progress_locked(self) -> NoReturn:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid",
            "/lifetime/global_recurrence_child/recovery",
            cleanup_owner=self,
        )

    def _active_global_recurrence_child_locked(
        self,
    ) -> _GlobalRecurrenceChildLeaseV1 | None:
        reference = self._global_recurrence_child_token
        return None if reference is None else reference()

    def _reap_abandoned_global_recurrence_child(self) -> None:
        """Lazily release only a dead, unconsumed, stream-idle weak lease."""

        with self._lock:
            reference = self._global_recurrence_child_token
            cell = self._global_recurrence_recovery_cell
            abandoned = (
                reference is not None
                and reference() is None
                and not self._continuation_consumed
            )
        if not abandoned:
            return
        self._require_exact_empty_pending_map()
        with self._lock:
            reference = self._global_recurrence_child_token
            if (
                reference is not None
                and reference() is None
                and not self._continuation_consumed
            ):
                cell = self._global_recurrence_recovery_cell
                if cell is not None:
                    if cell.lease_reference() is not None or cell.continuation_consumed:
                        self._fail_global_recurrence_recovery_progress_locked()
                    cell.abandoned = True
                    cell.released = True
                self._global_recurrence_recovery_cell = None
                self._global_recurrence_child_token = None

    def _recover_abandoned_global_recurrence_child(self) -> None:
        """Drain only a dead registered child through frozen cleanup authority."""

        self._reap_abandoned_global_recurrence_child()
        with self._lock:
            reference = self._global_recurrence_child_token
            cell = self._global_recurrence_recovery_cell
            if reference is None:
                if cell is None:
                    return
                if (
                    cell.released
                    and cell.terminal
                    and self._global_recurrence_child_terminal
                    and self._continuation_consumed
                ):
                    return
                self._fail_global_recurrence_recovery_progress_locked()
            if reference() is not None:
                return
            if type(cell) is not _GlobalRecurrenceRecoveryCellV1:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.abandoned = True
            self._reconcile_global_recurrence_consumed_locked(cell)
            if (
                cell.lease_reference() is not None
                or not self._continuation_consumed
                or not cell.continuation_consumed
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            if cell.released:
                self._validate_global_recurrence_recovery_cell_locked(
                    cell,
                    allow_release_in_progress=True,
                )
                if self._global_recurrence_recovery_pending_snapshot(cell):
                    self._fail_global_recurrence_recovery_progress_locked()
                self._terminally_release_abandoned_global_recurrence(cell)
                return
            if cell.terminal:
                self._fail_global_recurrence_recovery_progress_locked()
            self._validate_global_recurrence_recovery_cell_locked(cell)

        pending = self._global_recurrence_recovery_pending_snapshot(cell)
        lower = cell.launch_accept_lower_bound
        upper = cell.launch_accept_upper_bound
        if not pending:
            if cell.ack_started:
                acknowledged = cell.acknowledged_launch_count
                if acknowledged is None:
                    if lower == upper:
                        acknowledged = upper
                        with self._lock:
                            if cell is not self._global_recurrence_recovery_cell:
                                self._fail_global_recurrence_recovery_progress_locked()
                            cell.acknowledged_launch_count = acknowledged
                    else:
                        # The exact count can be lost after a successful pop.
                        # Cleanup remains safe because the empty map is the
                        # lifecycle authority; retain ambiguity and publish no
                        # numerical/completion capability.
                        with self._lock:
                            if cell is not self._global_recurrence_recovery_cell:
                                self._fail_global_recurrence_recovery_progress_locked()
                            cell.poisoned = True
                if acknowledged is not None and not lower <= acknowledged <= upper:
                    self._fail_global_recurrence_recovery_progress_locked()
            elif not (
                lower == 0
                and (upper == 0 or (cell.poisoned and cell.fence_attempt_count == 0))
            ):
                # Accepted work cannot disappear before an acknowledgement was
                # durably started.  Preserve ownership on malformed state.
                self._fail_global_recurrence_recovery_progress_locked()
            self._terminally_release_abandoned_global_recurrence(cell)
            return

        pending_stream, pending_count = pending[0]
        if (
            pending_stream != cell.stream_pointer
            or not lower <= pending_count <= upper
            or pending_count <= 0
            or pending_count > cell.launch_limit
        ):
            self._fail_global_recurrence_recovery_progress_locked()

        complete = cell.kernel._query_checkpoint_stream_completion(
            cell.checkpoint_owner_token,
            cell.stream_pointer,
        )
        if type(complete) is not bool:
            self._fail_global_recurrence_recovery_progress_locked()
        if not complete:
            with self._lock:
                if (
                    cell is not self._global_recurrence_recovery_cell
                    or cell.fence_observed
                ):
                    self._fail_global_recurrence_recovery_progress_locked()
                # Set before the call.  A later NOT_READY result proves that a
                # preceding failed/STORE-interrupted call did not complete the
                # stream, while COMPLETE prevents a duplicate successful fence.
                cell.fence_attempt_count += 1
            cell.kernel._synchronize_checkpoint_stream(
                cell.checkpoint_owner_token,
                cell.stream_pointer,
            )
            complete = cell.kernel._query_checkpoint_stream_completion(
                cell.checkpoint_owner_token,
                cell.stream_pointer,
            )
            if complete is not True:
                self._fail_global_recurrence_recovery_progress_locked()

        with self._lock:
            if cell is not self._global_recurrence_recovery_cell:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.fence_observed = True
            was_started = cell.ack_started
            cell.ack_started = True
        consumed = cell.kernel._consume_checkpoint_pending_after_fence(
            cell.checkpoint_owner_token,
            cell.stream_pointer,
        )
        if type(consumed) is not int:
            self._fail_global_recurrence_recovery_progress_locked()
        remaining = self._global_recurrence_recovery_pending_snapshot(cell)
        if remaining:
            self._fail_global_recurrence_recovery_progress_locked()
        if consumed == 0 and was_started:
            if lower == upper:
                consumed = upper
            else:
                with self._lock:
                    if cell is not self._global_recurrence_recovery_cell:
                        self._fail_global_recurrence_recovery_progress_locked()
                    cell.poisoned = True
                self._terminally_release_abandoned_global_recurrence(cell)
                return
        if not lower <= consumed <= upper or (lower == upper and consumed != lower):
            self._fail_global_recurrence_recovery_progress_locked()
        with self._lock:
            if cell is not self._global_recurrence_recovery_cell:
                self._fail_global_recurrence_recovery_progress_locked()
            previous = cell.acknowledged_launch_count
            if previous is not None and previous != consumed:
                self._fail_global_recurrence_recovery_progress_locked()
            cell.acknowledged_launch_count = consumed
        self._terminally_release_abandoned_global_recurrence(cell)

    def _validate_global_recurrence_recovery_cell_locked(
        self,
        cell: _GlobalRecurrenceRecoveryCellV1,
        *,
        allow_release_in_progress: bool = False,
    ) -> None:
        self._validate_global_recurrence_recovery_ledger_locked(
            cell,
            allow_release_in_progress=allow_release_in_progress,
        )
        binding = self._require_frozen_binding()
        if (
            cell.kernel is not binding.kernel
            or cell.checkpoint_owner_token is not binding.checkpoint_owner_token
            or type(cell.stream_pointer) is not int
            or cell.stream_pointer != binding.stream_pointer
        ):
            self._fail_global_recurrence_recovery_progress_locked()

    def _validate_global_recurrence_recovery_ledger_locked(
        self,
        cell: _GlobalRecurrenceRecoveryCellV1,
        *,
        allow_release_in_progress: bool = False,
    ) -> None:
        """Validate no-HIP recovery progress independently of frozen handles."""

        if (
            type(cell) is not _GlobalRecurrenceRecoveryCellV1
            or type(allow_release_in_progress) is not bool
        ):
            self._fail_global_recurrence_recovery_progress_locked()
        acknowledged = cell.acknowledged_launch_count
        exact_ints = (
            cell.launch_limit,
            cell.launch_attempt_count,
            cell.launch_accept_lower_bound,
            cell.launch_accept_upper_bound,
            cell.fence_attempt_count,
        )
        exact_bools = (
            cell.poisoned,
            cell.fence_observed,
            cell.ack_started,
            cell.released,
            cell.terminal,
            cell.abandoned,
            cell.continuation_consumed,
        )
        if (
            any(type(value) is not int for value in exact_ints)
            or any(type(value) is not bool for value in exact_bools)
            or cell.launch_limit <= 0
            or not 0
            <= cell.launch_accept_lower_bound
            <= cell.launch_accept_upper_bound
            <= cell.launch_attempt_count
            <= cell.launch_limit
            or cell.fence_attempt_count < 0
            or (cell.ack_started and not cell.fence_observed)
            or (acknowledged is not None and type(acknowledged) is not int)
            or (
                acknowledged is not None
                and (
                    not cell.ack_started
                    or not cell.launch_accept_lower_bound
                    <= acknowledged
                    <= cell.launch_accept_upper_bound
                )
            )
            or (cell.terminal and not cell.released)
            or ((cell.released or cell.terminal) and not allow_release_in_progress)
        ):
            self._fail_global_recurrence_recovery_progress_locked()

    def _global_recurrence_recovery_pending_snapshot(
        self,
        cell: _GlobalRecurrenceRecoveryCellV1,
    ) -> tuple[tuple[int, int], ...]:
        pending = cell.kernel._checkpoint_pending_snapshot(cell.checkpoint_owner_token)
        valid = type(pending) is tuple and len(pending) <= 1
        if pending:
            row = pending[0]
            valid = (
                valid
                and type(row) is tuple
                and len(row) == 2
                and type(row[0]) is int
                and type(row[1]) is int
            )
        if not valid:
            self._fail_global_recurrence_recovery_progress_locked()
        return pending

    def _terminally_release_abandoned_global_recurrence(
        self,
        cell: _GlobalRecurrenceRecoveryCellV1,
    ) -> None:
        if self._global_recurrence_recovery_pending_snapshot(cell):
            self._fail_global_recurrence_recovery_progress_locked()
        with self._lock:
            reference = self._global_recurrence_child_token
            if (
                cell is not self._global_recurrence_recovery_cell
                or (reference is not None and reference() is not None)
                or cell.lease_reference() is not None
                or not self._continuation_consumed
            ):
                self._fail_global_recurrence_recovery_progress_locked()
            self._reconcile_global_recurrence_consumed_locked(cell)
            if not cell.released:
                cell.released = True
            if not cell.terminal:
                cell.terminal = True
            if not self._global_recurrence_child_terminal:
                self._global_recurrence_child_terminal = True
            if reference is not None:
                self._global_recurrence_child_token = None

    def _require_current_continuation_locked(
        self,
        capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
        *,
        continuation_consumed: bool,
    ) -> None:
        if (
            type(capability) is not HipFgmresSealedCheckpointContinuationCapabilityV1
            or capability._issuer is not self
            or capability._nonce is not self._continuation_nonce
            or capability._snapshot != _continuation_snapshot(capability)
            or capability is not self._continuation
            or capability.context_id != self._context_id
            or capability.checkpoint_schedule_hash
            != HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
            or self._state != "transaction_fenced"
            or self._closed
            or self._continuation_consumed is not continuation_consumed
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_continuation_capability_invalid",
                "/capability",
                cleanup_owner=self,
            )

    def _require_exact_empty_pending_map(self) -> None:
        self._require_pending_map_bounds((0, 0))

    def _require_pending_map_bounds(
        self,
        expected_pending_operation_bounds: tuple[int, int],
    ) -> None:
        binding = self._require_frozen_binding()
        try:
            pending = binding.kernel._checkpoint_pending_snapshot(
                binding.checkpoint_owner_token
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_authority_invalid",
                "/kernel/pending_operation_bounds",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        lower, upper = expected_pending_operation_bounds
        valid = not pending and lower == 0
        if len(pending) == 1:
            stream_pointer, operation_count = pending[0]
            valid = (
                type(stream_pointer) is int
                and stream_pointer == binding.stream_pointer
                and type(operation_count) is int
                and operation_count > 0
                and lower <= operation_count <= upper
            )
        if not valid:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_global_child_pending",
                "/kernel/pending_operation_bounds",
                cleanup_owner=self,
            )

    def _attempt(self, operation: Any) -> None:
        row = self._telemetry
        self._telemetry = replace(
            row,
            kernel_launch_attempt_count=row.kernel_launch_attempt_count + 1,
        )
        try:
            operation()
        except BaseException as exc:
            disposition = getattr(exc, "launch_disposition", None)
            if disposition == "ambiguous" or disposition not in {
                "rejected",
                "not_attempted",
            }:
                row = self._telemetry
                self._telemetry = replace(
                    row,
                    kernel_launch_accept_upper_bound=(
                        row.kernel_launch_accept_upper_bound + 1
                    ),
                )
            raise
        row = self._telemetry
        self._telemetry = replace(
            row,
            kernel_launch_accept_lower_bound=(row.kernel_launch_accept_lower_bound + 1),
            kernel_launch_accept_upper_bound=(row.kernel_launch_accept_upper_bound + 1),
        )

    def _dispatch(
        self,
        binding: _SealedTransactionLaunchBinding,
        launch: FgmresV2FirstColumnCheckpointTransactionLaunch,
    ) -> None:
        audit_descriptor_hash = _launch_descriptor_hash_v1(launch)
        if launch.submission_kind == "control":
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
                _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
            )
        elif launch.submission_kind == "vector":
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
                _checkpoint_audit_descriptor_hash=audit_descriptor_hash,
            )
        else:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_schedule_invalid",
                "/enqueue/schedule/submission_kind",
                cleanup_owner=self,
            )
        if result is not None:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_kernel_contract_invalid",
                "/enqueue/kernel",
                cleanup_owner=self,
            )

    def _poison_after_enqueue_failure(self, error: BaseException) -> None:
        binding = self._require_frozen_binding()
        try:
            binding.kernel._poison_checkpoint_transaction_owner(
                binding.checkpoint_owner_token
            )
        except BaseException:
            pass
        try:
            pending = bool(
                binding.kernel._checkpoint_pending_snapshot(
                    binding.checkpoint_owner_token
                )
            )
        except BaseException:
            pending = True
        self._state = "poisoned_pending_fence" if pending else "poisoned_no_work"
        self._reason = HipFgmresSealedCheckpointTransactionReasonV1(
            "hip_fgmres_sealed_checkpoint_transaction_enqueue_failed",
            _detail(error),
        )
        self._pending = self._mint_pending()

    def _observe_fence_and_consume(self) -> None:
        binding = self._require_frozen_binding()
        lower = self._telemetry.kernel_launch_accept_lower_bound
        upper = self._telemetry.kernel_launch_accept_upper_bound
        if self._state not in {
            "fence_observed_ack_pending",
            "poisoned_fence_observed_ack_pending",
        }:
            self._require_frozen_fence_authority(
                expected_pending_operation_bounds=(lower, upper),
            )
            row = self._telemetry
            self._telemetry = replace(
                row,
                fence_attempt_count=row.fence_attempt_count + 1,
            )
            try:
                binding.kernel._synchronize_checkpoint_stream(
                    binding.checkpoint_owner_token,
                    binding.stream_pointer,
                )
            except Exception as exc:
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    "hip_fgmres_sealed_checkpoint_transaction_fence_failed",
                    "/fence/synchronize",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            row = self._telemetry
            self._telemetry = replace(
                row,
                fence_success_count=row.fence_success_count + 1,
            )
            self._state = (
                "poisoned_fence_observed_ack_pending"
                if self._state == "poisoned_pending_fence"
                else "fence_observed_ack_pending"
            )
        was_started = self._pending_consume_started
        self._pending_consume_started = True
        row = self._telemetry
        self._telemetry = replace(
            row,
            pending_consume_attempt_count=row.pending_consume_attempt_count + 1,
        )
        try:
            consumed = binding.kernel._consume_checkpoint_pending_after_fence(
                binding.checkpoint_owner_token,
                binding.stream_pointer,
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_failed",
                "/fence/consume",
                _detail(exc),
                pending=self._pending,
                cleanup_owner=self,
            ) from exc
        try:
            pending_snapshot = binding.kernel._checkpoint_pending_snapshot(
                binding.checkpoint_owner_token
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_pending_observation_failed",
                "/fence/pending_snapshot",
                _detail(exc),
                pending=self._pending,
                cleanup_owner=self,
            ) from exc
        if pending_snapshot:
            self._poison_ack_pending(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_mismatch",
                "The fenced reservation map remained non-empty after acknowledgement.",
            )
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_mismatch",
                "/fence/pending_snapshot",
                cleanup_owner=self,
            )
        if consumed == 0 and was_started and lower == upper:
            consumed = upper
        elif consumed == 0 and was_started and lower != upper:
            self._state = "poisoned_fenced"
            self._set_poison_reason(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_ambiguous",
                "The accepted launch count remained ambiguous after acknowledgement.",
            )
            self._telemetry = replace(
                self._telemetry,
                consumed_launch_count=0,
            )
            return
        if not lower <= consumed <= upper or (lower == upper and consumed != lower):
            self._state = "poisoned_fenced"
            self._set_poison_reason(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_mismatch",
                "The acknowledged reservation count did not match the accepted interval.",
            )
            try:
                binding.kernel._poison_checkpoint_transaction_owner(
                    binding.checkpoint_owner_token
                )
            except BaseException:
                pass
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_pending_consume_mismatch",
                "/fence/consume",
                cleanup_owner=self,
            )
        self._telemetry = replace(
            self._telemetry,
            consumed_launch_count=consumed,
        )
        if self._state == "poisoned_fence_observed_ack_pending":
            self._state = "poisoned_fenced"

    def _poison_ack_pending(self, code: str, detail: str) -> None:
        binding = self._require_frozen_binding()
        try:
            binding.kernel._poison_checkpoint_transaction_owner(
                binding.checkpoint_owner_token
            )
        except BaseException:
            pass
        self._state = "poisoned_fence_observed_ack_pending"
        self._set_poison_reason(code, detail)

    def _set_poison_reason(self, code: str, detail: str) -> None:
        if self._reason is None:
            self._reason = HipFgmresSealedCheckpointTransactionReasonV1(
                code,
                _detail(detail),
            )

    def _validate_reserved_authority(self) -> None:
        canonical = self._require_canonical()
        capability = self._require_predecessor_capability()
        canonical._require_sealed_checkpoint_transaction_child(
            self._token,
            capability_consumed=False,
        )
        validate_hip_fgmres_canonical_predecessor_capability_v1(
            capability,
            expected_context=canonical,
        )
        canonical._validate_authority(require_idle_kernel=True)
        self._require_current_binding(
            expected_pending_operation_bounds=(0, 0),
            consumed=False,
        )

    def _require_current_binding(
        self,
        *,
        expected_pending_operation_bounds: tuple[int, int],
        consumed: bool = True,
        expected_binding: _SealedTransactionLaunchBinding | None = None,
    ) -> None:
        canonical = self._require_canonical()
        if consumed:
            canonical._validate_sealed_checkpoint_transaction_authority(
                self._token,
                expected_pending_operation_bounds=(expected_pending_operation_bounds),
            )
        try:
            current = _capture_binding(canonical)
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_binding_changed",
                "/authority/binding",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        expected = self._require_binding()
        if expected_binding is not None and expected_binding is not expected:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_changed",
                "/authority/binding",
                cleanup_owner=self,
            )
        snapshot = self._binding_value_snapshot
        pending_snapshot = current.kernel._checkpoint_pending_snapshot(
            current.checkpoint_owner_token
        )
        if (
            snapshot is None
            or _binding_values(expected) != snapshot
            or _binding_values(current) != snapshot
            or not _pending_snapshot_matches(
                pending_snapshot,
                stream_pointer=current.stream_pointer,
                operation_bounds=expected_pending_operation_bounds,
            )
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_changed",
                "/authority/binding",
                cleanup_owner=self,
            )

    def _require_frozen_fence_authority(
        self,
        *,
        expected_pending_operation_bounds: tuple[int, int],
    ) -> None:
        """Validate only immutable lease data needed to drain accepted work."""

        binding = self._require_frozen_binding()
        canonical = self._require_canonical()
        canonical._require_sealed_checkpoint_transaction_child(
            self._token,
            capability_consumed=True,
        )
        try:
            runtime_owner = binding.kernel._checkpoint_runtime_owner(
                binding.checkpoint_owner_token
            )
            kernel_snapshot = binding.kernel._checkpoint_binding_snapshot(
                binding.checkpoint_owner_token
            )
            pending_snapshot = binding.kernel._checkpoint_pending_snapshot(
                binding.checkpoint_owner_token
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_fence_authority_invalid",
                "/fence/authority",
                _detail(exc),
                pending=self._pending,
                cleanup_owner=self,
            ) from exc
        if (
            runtime_owner is not binding.loaded_runtime
            or kernel_snapshot != binding.kernel_binding_snapshot
            or not _pending_snapshot_matches(
                pending_snapshot,
                stream_pointer=binding.stream_pointer,
                operation_bounds=expected_pending_operation_bounds,
            )
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_fence_authority_invalid",
                "/fence/authority",
                cleanup_owner=self,
            )

    def _validate_pending(
        self,
        pending: HipFgmresSealedCheckpointTransactionPendingV1,
    ) -> None:
        if (
            type(pending) is not HipFgmresSealedCheckpointTransactionPendingV1
            or pending._issuer is not self
            or pending._nonce is not self._pending_nonce
            or pending._snapshot != _pending_snapshot(pending)
            or pending is not self._pending
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_pending_invalid",
                "/pending",
            )

    def _mint_pending(self) -> HipFgmresSealedCheckpointTransactionPendingV1:
        if self._pending is not None:
            return self._pending
        pending = _issue_capability(
            HipFgmresSealedCheckpointTransactionPendingV1,
            {
                "context_id": self._context_id,
                "attempted_launch_count": (self._telemetry.kernel_launch_attempt_count),
                "accepted_launch_count_lower_bound": (
                    self._telemetry.kernel_launch_accept_lower_bound
                ),
                "accepted_launch_count_upper_bound": (
                    self._telemetry.kernel_launch_accept_upper_bound
                ),
                "_issuer": self,
                "_nonce": self._pending_nonce,
            },
        )
        object.__setattr__(pending, "_snapshot", _pending_snapshot(pending))
        return pending

    def _mint_continuation(
        self,
    ) -> HipFgmresSealedCheckpointContinuationCapabilityV1:
        if self._continuation is not None:
            return self._continuation
        receipt = self._build_receipt("transaction_fenced")
        capability = _issue_capability(
            HipFgmresSealedCheckpointContinuationCapabilityV1,
            {
                "context_id": self._context_id,
                "receipt_hash": receipt.receipt_hash,
                "canonical_predecessor_context_id": (
                    receipt.bindings.canonical_predecessor_context_id
                ),
                "checkpoint_schedule_hash": (receipt.bindings.checkpoint_schedule_hash),
                "_issuer": self,
                "_nonce": self._continuation_nonce,
            },
        )
        object.__setattr__(
            capability,
            "_snapshot",
            _continuation_snapshot(capability),
        )
        return capability

    def _release_child(self) -> None:
        if self._child_released:
            return
        self._require_canonical()._release_sealed_checkpoint_transaction_child(
            self._token
        )
        self._child_released = True

    def _require_canonical(
        self,
    ) -> HipFgmresCanonicalPredecessorExecutionContextV1:
        if type(self._canonical) is not HipFgmresCanonicalPredecessorExecutionContextV1:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_canonical_invalid",
                "/canonical_context",
            )
        return self._canonical

    def _require_predecessor_capability(
        self,
    ) -> HipFgmresCanonicalPredecessorCapabilityV1:
        if (
            type(self._predecessor_capability)
            is not HipFgmresCanonicalPredecessorCapabilityV1
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_capability_invalid",
                "/predecessor_capability",
            )
        return self._predecessor_capability

    def _require_binding(self) -> _SealedTransactionLaunchBinding:
        with _TRANSACTION_BINDING_LOCK:
            witness = _TRANSACTION_BINDINGS.get(self)
        if witness is None:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_invalid",
                "/authority/binding",
            )
        binding, snapshot = witness
        try:
            current_values = _binding_values(binding)
            canonical_launch_values = _launch_values(
                first_column_checkpoint_transaction_launches_v2(
                    binding.free_dof_count,
                    binding.restart_dimension,
                )
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_binding_invalid",
                "/authority/binding",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        if (
            type(self._binding) is not _SealedTransactionLaunchBinding
            or self._binding is not binding
            or self._binding_value_snapshot != snapshot
            or current_values != snapshot
            or _launch_values(binding.launches) != binding.launch_values
            or canonical_launch_values != binding.launch_values
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_invalid",
                "/authority/binding",
                cleanup_owner=self,
            )
        return binding

    def _require_frozen_binding(self) -> _SealedTransactionLaunchBinding:
        """Return the factory witness used only for fail-safe drain/cleanup."""

        with _TRANSACTION_BINDING_LOCK:
            witness = _TRANSACTION_BINDINGS.get(self)
        if witness is None or type(witness[0]) is not _SealedTransactionLaunchBinding:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_invalid",
                "/authority/frozen_binding",
                cleanup_owner=self,
            )
        return witness[0]

    def _build_receipt(
        self,
        status: SealedCheckpointTransactionStatusV1,
    ) -> HipFgmresSealedCheckpointTransactionReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_receipt_unavailable",
                "/receipt",
            )
        bound = status not in {"cleanup_failed", "context_closed"}
        consumed = self._telemetry.predecessor_capability_consume_count == 1
        fenced = status in {"transaction_fenced", "context_closed"} and (
            self._continuation is not None or status == "transaction_fenced"
        )
        claims = HipFgmresSealedCheckpointTransactionClaimsV1(
            live_krylov_parent_bound=bound,
            canonical_predecessor_capability_reserved=bound,
            canonical_predecessor_capability_consumed=consumed,
            direct11_physical16_continuity_bound=bound,
            same_runtime_device_stream_bound=bound,
            fixed_four_row_program_bound=bound,
            fixed_four_row_transaction_fenced=fenced,
            device_seal_transition_program_bound=bound,
            invalid_source_destination_atomicity_contract_bound=bound,
            conditional_post_checkpoint_capability_issued=fenced,
        )
        draft = HipFgmresSealedCheckpointTransactionReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_EVIDENCE_SCOPE_V1,
            actual_backend=self._require_canonical().receipt().actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            projection=HipFgmresSealedCheckpointTransactionProjectionV1(
                _DIRECT_ROLES,
                _DELEGATED_OPERATOR_ROLES,
                _DELEGATED_WORKSPACE_ROLES,
            ),
            telemetry=self._telemetry,
            claims=claims,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


_TRANSACTION_BINDING_LOCK = threading.RLock()
_TRANSACTION_BINDINGS: weakref.WeakKeyDictionary[
    HipFgmresSealedCheckpointTransactionExecutionContextV1,
    tuple[_SealedTransactionLaunchBinding, tuple[Any, ...]],
] = weakref.WeakKeyDictionary()


def open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
    canonical_context: HipFgmresCanonicalPredecessorExecutionContextV1,
    predecessor_capability: HipFgmresCanonicalPredecessorCapabilityV1,
) -> HipFgmresSealedCheckpointTransactionOpenResultV1:
    """Reserve a non-owning four-row child over an exact canonical capability."""

    context = HipFgmresSealedCheckpointTransactionExecutionContextV1(
        _mint=_CONTEXT_MINT
    )
    reserved = False
    try:
        if (
            type(canonical_context)
            is not HipFgmresCanonicalPredecessorExecutionContextV1
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_canonical_invalid",
                "/canonical_context",
            )
        context._canonical = canonical_context
        context._predecessor_capability = predecessor_capability
        validate_hip_fgmres_canonical_predecessor_capability_v1(
            predecessor_capability,
            expected_context=canonical_context,
        )
        acquired = canonical_context._reserve_sealed_checkpoint_transaction_child(
            context._token,
            predecessor_capability,
        )
        if acquired is not context._token:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_child_changed",
                "/lifetime",
            )
        reserved = True
        canonical_receipt = canonical_context.receipt()
        validate_hip_fgmres_canonical_predecessor_receipt_v1(
            canonical_receipt,
            expected_context=canonical_context,
        )
        if canonical_receipt.status != "predecessor_fenced":
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_predecessor_invalid",
                "/predecessor_capability",
            )
        binding = _capture_binding(canonical_context)
        context._binding = binding
        context._binding_value_snapshot = _binding_values(binding)
        with _TRANSACTION_BINDING_LOCK:
            _TRANSACTION_BINDINGS[context] = (
                binding,
                context._binding_value_snapshot,
            )
        live = canonical_context._require_live()
        direct = tuple(live._group_capabilities)
        if (
            tuple(row.role for row in direct) != _DIRECT_ROLES
            or tuple(int(row.pointer_snapshot) for row in direct)
            != binding.pointer_values
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_direct_group_invalid",
                "/projection/direct11",
            )
        canonical_bindings = canonical_context._bindings
        dimensions = canonical_context._dimensions
        if canonical_bindings is None or dimensions is None:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_predecessor_invalid",
                "/canonical_context/bindings",
            )
        checkpoint_payload = (
            hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
        )
        checkpoint_hash = canonical_hash(checkpoint_payload)
        if checkpoint_hash != HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_schedule_invalid",
                "/bindings/checkpoint_schedule_hash",
            )
        context._context_id = canonical_hash(
            {
                "profile": (
                    HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_CAPABILITY_PROFILE_V1
                ),
                "canonical_predecessor_context_id": canonical_receipt.context_id,
                "canonical_predecessor_receipt_hash": (canonical_receipt.receipt_hash),
                "checkpoint_schedule_hash": checkpoint_hash,
                "direct_generation_binding_hash": (
                    canonical_bindings.direct_generation_binding_hash
                ),
                "physical_projection_hash": (
                    canonical_bindings.physical_projection_hash
                ),
            }
        )
        context._bindings = HipFgmresSealedCheckpointTransactionBindingsV1(
            canonical_receipt.context_id,
            canonical_receipt.receipt_hash,
            canonical_bindings.live_context_id,
            canonical_bindings.live_opening_receipt_hash,
            canonical_bindings.primitive_context_id,
            canonical_bindings.primitive_opening_receipt_hash,
            canonical_bindings.primitive_evidence_scope,
            canonical_bindings.primitive_actual_backend,
            canonical_bindings.source_apply_receipt_hash,
            canonical_bindings.source_state_hash,
            canonical_bindings.recurrence_plan_hash,
            canonical_bindings.recurrence_kernel_abi_hash,
            HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
            canonical_bindings.kernel_identity_hash,
            canonical_bindings.kernel_source_sha256,
            canonical_bindings.kernel_origin,
            canonical_bindings.runtime_library_discovery_source,
            canonical_bindings.hiprtc_library_discovery_source,
            canonical_bindings.canonical_schedule_hash,
            canonical_bindings.validator_schedule_hash,
            checkpoint_hash,
            canonical_bindings.direct_generation_binding_hash,
            canonical_bindings.physical_projection_hash,
            canonical_bindings.primitive_parent_lease_epoch,
            canonical_bindings.solver_child_lease_epoch,
        )
        context._dimensions = HipFgmresSealedCheckpointTransactionDimensionsV1(
            binding.free_dof_count,
            binding.restart_dimension,
            binding.max_iterations,
            binding.maximum_restart_count,
            len(reduction_stage_output_counts_v2(binding.free_dof_count)),
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            receipt,
            expected_context=context,
        )
        return HipFgmresSealedCheckpointTransactionOpenResultV1(context, receipt)
    except BaseException as primary:
        if reserved:
            try:
                canonical_context._release_sealed_checkpoint_transaction_child(
                    context._token
                )
                context._child_released = True
                with _TRANSACTION_BINDING_LOCK:
                    _TRANSACTION_BINDINGS.pop(context, None)
            except BaseException as rollback:
                context._state = "cleanup_failed"
                context._reason = HipFgmresSealedCheckpointTransactionReasonV1(
                    "hip_fgmres_sealed_checkpoint_transaction_open_rollback_failed",
                    _detail(rollback),
                )
                raise HipFgmresSealedCheckpointTransactionV1Error(
                    context._reason.code,
                    "/open/rollback",
                    f"open failed: {_detail(primary)}; rollback failed: "
                    f"{context._reason.detail}",
                    cleanup_owner=context,
                ) from rollback
        raise


def _capture_binding(
    canonical: HipFgmresCanonicalPredecessorExecutionContextV1,
) -> _SealedTransactionLaunchBinding:
    with canonical._lock:
        live = canonical._require_live()
        plan = live._source_plan
        recurrence = live._recurrence_plan
        kernel = live._kernel
        loaded_runtime = live._loaded_runtime
        if (
            plan is None
            or recurrence is None
            or type(kernel) is not HipRtcFgmresV2Kernel
            or loaded_runtime is None
            or live._kernel_binding_snapshot is None
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_binding_invalid",
                "/authority/binding",
            )
        try:
            direct_capabilities = tuple(live._group_capabilities)
            direct_roles = tuple(row.role for row in direct_capabilities)
            direct_pointer_values = tuple(
                int(row.pointer_snapshot) for row in direct_capabilities
            )
            canonical_pointer_values = tuple(
                int(canonical._pointers[role]) for role in _DIRECT_ROLES
            )
        except Exception as exc:
            raise HipFgmresSealedCheckpointTransactionV1Error(
                "hip_fgmres_sealed_checkpoint_transaction_direct_group_invalid",
                "/authority/direct11",
                _detail(exc),
            ) from exc
        if (
            direct_roles != _DIRECT_ROLES
            or len(direct_capabilities) != 11
            or canonical_pointer_values != direct_pointer_values
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_direct_group_invalid",
                "/authority/direct11",
            )
        policy = plan.policy
        launches = first_column_checkpoint_transaction_launches_v2(
            recurrence.free_dof_count,
            recurrence.restart_dimension,
        )
        checkpoint_token = canonical._live_checkpoint_token()
        return _SealedTransactionLaunchBinding(
            kernel=kernel,
            checkpoint_owner_token=checkpoint_token,
            loaded_runtime=loaded_runtime,
            stream_pointer=int(canonical._stream()),
            free_dof_count=recurrence.free_dof_count,
            restart_dimension=recurrence.restart_dimension,
            max_iterations=recurrence.max_iterations,
            maximum_restart_count=recurrence.maximum_restart_count,
            stagnation_checkpoint_limit=policy.stagnation_checkpoint_limit,
            absolute_tolerance=policy.absolute_tolerance,
            relative_tolerance=policy.relative_tolerance,
            authoritative_tolerance=plan.source_residual_tolerance,
            stagnation_relative_tolerance=policy.stagnation_relative_tolerance,
            divergence_factor=policy.divergence_factor,
            pointer_values=direct_pointer_values,
            launches=launches,
            launch_values=_launch_values(launches),
            kernel_binding_snapshot=kernel._checkpoint_binding_snapshot(
                checkpoint_token
            ),
        )


def _launch_values(
    launches: tuple[FgmresV2FirstColumnCheckpointTransactionLaunch, ...],
) -> tuple[tuple[tuple[str, Any], ...], ...]:
    return tuple(tuple(asdict(row).items()) for row in launches)


def _binding_values(binding: _SealedTransactionLaunchBinding) -> tuple[Any, ...]:
    return (
        id(binding.kernel),
        id(binding.checkpoint_owner_token),
        id(binding.loaded_runtime),
        binding.stream_pointer,
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
        binding.pointer_values,
        binding.launch_values,
        _launch_values(binding.launches),
        binding.kernel_binding_snapshot,
    )


def _pending_snapshot_matches(
    snapshot: tuple[tuple[int, int], ...],
    *,
    stream_pointer: int,
    operation_bounds: tuple[int, int],
) -> bool:
    lower, upper = operation_bounds
    if not snapshot:
        return lower == 0
    if len(snapshot) != 1:
        return False
    pending_stream, operation_count = snapshot[0]
    return (
        type(pending_stream) is int
        and pending_stream == stream_pointer
        and type(operation_count) is int
        and operation_count > 0
        and lower <= operation_count <= upper
    )


def validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
    receipt: HipFgmresSealedCheckpointTransactionReceiptV1,
    *,
    expected_context: HipFgmresSealedCheckpointTransactionExecutionContextV1
    | None = None,
) -> HipFgmresSealedCheckpointTransactionReceiptV1:
    if type(receipt) is not HipFgmresSealedCheckpointTransactionReceiptV1:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_receipt_type_invalid",
            "/",
        )
    payload = _receipt_payload(receipt, include_hash=False)
    if (
        type(receipt.receipt_hash) is not str
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != canonical_hash(payload)
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_receipt_hash_invalid",
            "/receipt_hash",
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_schema_invalid",
            path or "/",
            errors[0].message,
        )
    forbidden = (
        receipt.promotion_eligible,
        receipt.claims.device_validation_outcome_host_observed,
        receipt.claims.actual_mask_host_observed,
        receipt.claims.commit_gate_host_observed,
        receipt.claims.checkpoint_commit_host_observed,
        receipt.claims.authoritative_predecessor_proven,
        receipt.claims.authoritative_numerical_transaction_proven,
        receipt.claims.live_solver_ready,
        receipt.claims.solution_ready,
        receipt.claims.later_recurrence_ready,
        receipt.claims.iteration_host_copy_zero_proven,
        receipt.claims.asymptotic_o_n_proven,
        receipt.claims.speedup_proven,
        receipt.claims.commercial_ready,
        receipt.claims.promotion_eligible,
    )
    if any(forbidden):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims",
        )
    native_parent = (
        receipt.bindings.primitive_evidence_scope
        == "native_hiprtc_krylov_primitives_composite"
        and receipt.bindings.primitive_actual_backend == "hip"
    )
    native_kernel = (
        receipt.bindings.kernel_origin == "internally_compiled"
        and receipt.bindings.runtime_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
        and receipt.bindings.hiprtc_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
    )
    expected_backend = "hip" if native_parent and native_kernel else "test_double"
    if receipt.actual_backend != expected_backend:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_backend_invalid",
            "/actual_backend",
        )
    _validate_receipt_semantics(receipt)
    if expected_context is not None:
        if (
            type(expected_context)
            is not HipFgmresSealedCheckpointTransactionExecutionContextV1
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_context_invalid",
                "/",
            )
        current = expected_context.receipt()
        if receipt.receipt_hash != current.receipt_hash:
            _fail(
                "hip_fgmres_sealed_checkpoint_transaction_context_mismatch",
                "/",
            )
    return receipt


def _validate_receipt_semantics(
    receipt: HipFgmresSealedCheckpointTransactionReceiptV1,
) -> None:
    dimensions = receipt.dimensions
    try:
        stages = len(reduction_stage_output_counts_v2(dimensions.free_dof_count))
        launches = first_column_checkpoint_transaction_launches_v2(
            dimensions.free_dof_count,
            dimensions.restart_dimension,
        )
        canonical_launches = canonical_first_column_predecessor_launches_v2(
            dimensions.free_dof_count,
            dimensions.restart_dimension,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_dimensions_invalid",
            "/dimensions",
            _detail(exc),
        )
    if (
        dimensions.reduction_stage_count != stages
        or dimensions.transaction_launch_count != 4
        or len(launches) != 4
        or dimensions.persistent_capability_count != 11
        or dimensions.physical_capability_count != 16
        or dimensions.maximum_restart_count
        != (dimensions.max_iterations + dimensions.restart_dimension - 1)
        // dimensions.restart_dimension
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_dimensions_invalid",
            "/dimensions",
        )
    expected_checkpoint_hash = canonical_hash(
        hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    )
    expected_recurrence_abi_hash = canonical_hash(
        hip_fgmres_recurrence_kernel_abi_payload_v2()
    )
    expected_canonical_schedule_hash = canonical_hash(
        [asdict(row) for row in canonical_launches]
    )
    expected_validator_schedule_hash = canonical_hash(
        hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    )
    bindings = receipt.bindings
    if (
        expected_checkpoint_hash != HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
        or bindings.checkpoint_schedule_hash != expected_checkpoint_hash
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_schedule_invalid",
            "/bindings/checkpoint_schedule_hash",
        )
    if (
        bindings.combined_recurrence_abi_hash
        != HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
        or bindings.recurrence_kernel_abi_hash != expected_recurrence_abi_hash
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_abi_invalid",
            "/bindings/combined_recurrence_abi_hash",
        )
    if bindings.kernel_source_sha256 != HIP_FGMRES_RTC_SOURCE_SHA256_V2:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_source_identity_invalid",
            "/bindings/kernel_source_sha256",
        )
    if bindings.canonical_schedule_hash != expected_canonical_schedule_hash:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_schedule_invalid",
            "/bindings/canonical_schedule_hash",
        )
    if bindings.validator_schedule_hash != expected_validator_schedule_hash:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_schedule_invalid",
            "/bindings/validator_schedule_hash",
        )
    expected_context_id = canonical_hash(
        {
            "profile": HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_CAPABILITY_PROFILE_V1,
            "canonical_predecessor_context_id": (
                bindings.canonical_predecessor_context_id
            ),
            "canonical_predecessor_receipt_hash": (
                bindings.canonical_predecessor_receipt_hash
            ),
            "checkpoint_schedule_hash": bindings.checkpoint_schedule_hash,
            "direct_generation_binding_hash": (bindings.direct_generation_binding_hash),
            "physical_projection_hash": bindings.physical_projection_hash,
        }
    )
    if receipt.context_id != expected_context_id:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_context_id_invalid",
            "/context_id",
        )
    projection = receipt.projection
    if (
        projection.persistent_roles != _DIRECT_ROLES
        or projection.delegated_operator_roles != _DELEGATED_OPERATOR_ROLES
        or projection.delegated_workspace_roles != _DELEGATED_WORKSPACE_ROLES
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_projection_invalid",
            "/projection",
        )
    bound = receipt.status not in {"cleanup_failed", "context_closed"}
    bound_claims = (
        receipt.claims.live_krylov_parent_bound,
        receipt.claims.canonical_predecessor_capability_reserved,
        receipt.claims.direct11_physical16_continuity_bound,
        receipt.claims.same_runtime_device_stream_bound,
        receipt.claims.fixed_four_row_program_bound,
        receipt.claims.device_seal_transition_program_bound,
        receipt.claims.invalid_source_destination_atomicity_contract_bound,
    )
    if any(value is not bound for value in bound_claims):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims",
        )
    telemetry = receipt.telemetry
    if (
        telemetry.predecessor_capability_reservation_count != 1
        or telemetry.predecessor_capability_consume_count not in {0, 1}
        or not 0
        <= telemetry.kernel_launch_accept_lower_bound
        <= telemetry.kernel_launch_accept_upper_bound
        <= telemetry.kernel_launch_attempt_count
        <= 4
        or telemetry.fence_success_count > telemetry.fence_attempt_count
        or telemetry.fence_success_count > 1
        or telemetry.consumed_launch_count > telemetry.kernel_launch_accept_upper_bound
        or (
            telemetry.pending_consume_attempt_count > 0
            and telemetry.fence_success_count != 1
        )
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_telemetry_invalid",
            "/telemetry",
        )
    consumed_claim = receipt.claims.canonical_predecessor_capability_consumed
    consumed = telemetry.predecessor_capability_consume_count == 1
    if consumed_claim is not consumed:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims/canonical_predecessor_capability_consumed",
        )
    if receipt.status == "context_ready" and (
        consumed
        or telemetry.kernel_launch_attempt_count != 0
        or telemetry.fence_attempt_count != 0
        or telemetry.pending_consume_attempt_count != 0
        or telemetry.consumed_launch_count != 0
        or receipt.reason is not None
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status == "transaction_pending" and (
        not consumed
        or telemetry.kernel_launch_attempt_count != 4
        or telemetry.kernel_launch_accept_lower_bound != 4
        or telemetry.kernel_launch_accept_upper_bound != 4
        or telemetry.fence_success_count != 0
        or telemetry.pending_consume_attempt_count != 0
        or telemetry.consumed_launch_count != 0
        or receipt.reason is not None
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status in {
        "fence_observed_ack_pending",
        "poisoned_fence_observed_ack_pending",
    } and (
        telemetry.fence_success_count != 1
        or telemetry.pending_consume_attempt_count < 1
        or telemetry.consumed_launch_count != 0
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status == "poisoned_no_work" and (
        telemetry.kernel_launch_accept_upper_bound != 0
        or telemetry.fence_success_count != 0
        or telemetry.consumed_launch_count != 0
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_telemetry_invalid",
            "/telemetry",
        )
    if receipt.status.startswith("poisoned_") and receipt.reason is None:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_reason_invalid",
            "/reason",
        )
    if (
        receipt.status in {"context_ready", "transaction_pending", "transaction_fenced"}
        and receipt.reason is not None
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_reason_invalid",
            "/reason",
        )
    fenced = receipt.claims.fixed_four_row_transaction_fenced
    continuation = receipt.claims.conditional_post_checkpoint_capability_issued
    if fenced is not continuation:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims",
        )
    if fenced and (
        receipt.status not in {"transaction_fenced", "context_closed"}
        or not consumed
        or telemetry.kernel_launch_attempt_count != 4
        or telemetry.kernel_launch_accept_lower_bound != 4
        or telemetry.kernel_launch_accept_upper_bound != 4
        or telemetry.fence_success_count != 1
        or telemetry.consumed_launch_count != 4
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims/fixed_four_row_transaction_fenced",
        )
    if receipt.status == "transaction_fenced" and not fenced:
        _fail(
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid",
            "/claims/fixed_four_row_transaction_fenced",
        )


def validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
    capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
    *,
    expected_context: HipFgmresSealedCheckpointTransactionExecutionContextV1,
) -> HipFgmresSealedCheckpointContinuationCapabilityV1:
    """Validate one still-open conditional post-checkpoint capability."""

    if (
        type(expected_context)
        is not HipFgmresSealedCheckpointTransactionExecutionContextV1
    ):
        _fail(
            "hip_fgmres_sealed_checkpoint_continuation_context_invalid",
            "/",
        )
    with expected_context._lock:
        if (
            type(capability) is not HipFgmresSealedCheckpointContinuationCapabilityV1
            or capability._issuer is not expected_context
            or capability._nonce is not expected_context._continuation_nonce
            or capability._snapshot != _continuation_snapshot(capability)
            or capability is not expected_context._continuation
            or capability.context_id != expected_context._context_id
            or capability.checkpoint_schedule_hash
            != HIP_FGMRES_CHECKPOINT_TRANSACTION_SCHEDULE_HASH_V2
            or expected_context._state != "transaction_fenced"
            or expected_context.closed
            or expected_context._continuation_consumed
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_continuation_capability_invalid",
                "/capability",
            )
        receipt = expected_context.receipt()
        if (
            capability.receipt_hash != receipt.receipt_hash
            or capability.canonical_predecessor_context_id
            != receipt.bindings.canonical_predecessor_context_id
        ):
            _fail(
                "hip_fgmres_sealed_checkpoint_continuation_capability_invalid",
                "/capability/receipt_hash",
            )
        return capability


def _receipt_payload(
    receipt: HipFgmresSealedCheckpointTransactionReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_CAPABILITY_PROFILE_V1,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "projection": receipt.projection.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _pending_snapshot(
    pending: HipFgmresSealedCheckpointTransactionPendingV1,
) -> tuple[Any, ...]:
    return (
        pending.context_id,
        pending.attempted_launch_count,
        pending.accepted_launch_count_lower_bound,
        pending.accepted_launch_count_upper_bound,
        id(pending._issuer),
        id(pending._nonce),
    )


def _continuation_snapshot(
    capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
) -> tuple[Any, ...]:
    return (
        capability.context_id,
        capability.receipt_hash,
        capability.canonical_predecessor_context_id,
        capability.checkpoint_schedule_hash,
        id(capability._issuer),
        id(capability._nonce),
    )


def _issue_capability(type_: type[Any], fields: dict[str, Any]) -> Any:
    value = object.__new__(type_)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: object) -> str:
    text = _HEX_ADDRESS_RE.sub("<redacted-address>", str(value))
    text = _DECIMAL_HANDLE_RE.sub("<redacted-handle>", text)
    return (" ".join(text.split())[:512]) or "unspecified"


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresSealedCheckpointTransactionExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresSealedCheckpointTransactionV1Error(
        code,
        path,
        message or code,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_SCHEMA_VERSION_V1",
    "HipFgmresSealedCheckpointContinuationCapabilityV1",
    "HipFgmresSealedCheckpointTransactionBindingsV1",
    "HipFgmresSealedCheckpointTransactionClaimsV1",
    "HipFgmresSealedCheckpointTransactionDimensionsV1",
    "HipFgmresSealedCheckpointTransactionExecutionContextV1",
    "HipFgmresSealedCheckpointTransactionOpenResultV1",
    "HipFgmresSealedCheckpointTransactionPendingV1",
    "HipFgmresSealedCheckpointTransactionProjectionV1",
    "HipFgmresSealedCheckpointTransactionReasonV1",
    "HipFgmresSealedCheckpointTransactionReceiptV1",
    "HipFgmresSealedCheckpointTransactionTelemetryV1",
    "HipFgmresSealedCheckpointTransactionV1Error",
    "open_hip_fgmres_sealed_checkpoint_transaction_context_v1",
    "validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1",
    "validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1",
]
