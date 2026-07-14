"""Non-owning fixed-suffix owner for the HIP FGMRES global recurrence.

This context consumes exactly one sealed-checkpoint continuation capability and
submits only the canonical global-program suffix.  It borrows the live kernel,
runtime, device, stream, checkpoint token, direct eleven buffers, delegated CSR
triple, and delegated reduction scratch pair from the still-open sealed lineage.
It never allocates, copies, synchronizes between launches, reads live device
state, or branches the host submission sequence on a numerical outcome.

Completion means only that the immutable suffix was accepted, fenced through
the exact owning runtime, and removed from the checkpoint pending map.  It does
not mean that a terminal solver result, solution parity, performance, or
commercial readiness was observed.
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass, replace
from functools import lru_cache, wraps
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal, NamedTuple, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import ExecutionPlanV2

from .fgmres_context_v2 import (
    HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from .fgmres_global_schedule_plan_v1 import (
    HipFgmresGlobalScheduleLaunchV1,
    HipFgmresGlobalSealedContinuationV1,
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from .fgmres_plan import HipFgmresPlanV1
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
)
from .fgmres_rtc_v2 import HipRtcFgmresV2Kernel
from .fgmres_sealed_checkpoint_transaction_v1 import (
    HipFgmresSealedCheckpointContinuationCapabilityV1,
    HipFgmresSealedCheckpointTransactionExecutionContextV1,
    _mint_global_recurrence_child_lease_v1,
    validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1,
)


HIP_FGMRES_GLOBAL_RECURRENCE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-global-recurrence-context.v1"
)
HIP_FGMRES_GLOBAL_RECURRENCE_CAPABILITY_PROFILE_V1 = (
    "phase0_sealed_continuation_consuming_fixed_global_recurrence"
)
HIP_FGMRES_GLOBAL_RECURRENCE_EVIDENCE_SCOPE_V1 = (
    "fixed_suffix_fenced_device_outcome_unobserved_non_promoting"
)

GlobalRecurrenceStatusV1 = Literal[
    "context_ready",
    "pending_publication_pending",
    "recurrence_pending",
    "fence_observed_ack_pending",
    "completion_publication_pending",
    "recurrence_fenced",
    "poisoned_no_work",
    "poisoned_pending_fence",
    "poisoned_fence_observed_ack_pending",
    "poisoned_fenced",
    "context_closed",
    "cleanup_failed",
]
_GLOBAL_RECURRENCE_STATUSES = frozenset(
    {
        "context_ready",
        "pending_publication_pending",
        "recurrence_pending",
        "fence_observed_ack_pending",
        "completion_publication_pending",
        "recurrence_fenced",
        "poisoned_no_work",
        "poisoned_pending_fence",
        "poisoned_fence_observed_ack_pending",
        "poisoned_fenced",
        "context_closed",
        "cleanup_failed",
    }
)

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
_SCHEMA_RESOURCE = "hip_fgmres_global_recurrence_context_v1.schema.json"


class HipFgmresGlobalRecurrenceV1Error(RuntimeError):
    """Stable global-recurrence error retaining retryable cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        pending: HipFgmresGlobalRecurrencePendingV1 | None = None,
        cleanup_owner: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None,
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


class HipFgmresGlobalRecurrencePendingV1(_ImmutableCapability):
    """Nonconstructible fence authority for one exact suffix submission."""

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
            "Global recurrence pending capabilities are context-issued only."
        )


class HipFgmresGlobalRecurrenceCompletionCapabilityV1(_ImmutableCapability):
    """Fenced-program capability that deliberately carries no solver outcome."""

    __slots__ = (
        "context_id",
        "receipt_hash",
        "continuation_schedule_hash",
        "fenced_launch_count",
        "_issuer",
        "_nonce",
        "_snapshot",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError(
            "Global recurrence completion capabilities are context-issued only."
        )


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceBindingsV1:
    sealed_checkpoint_context_id: str
    sealed_checkpoint_receipt_hash: str
    canonical_predecessor_context_id: str
    live_context_id: str
    primitive_evidence_scope: str
    primitive_actual_backend: Literal["hip", "test_double"]
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    kernel_origin: Literal["internally_compiled", "caller_supplied"]
    runtime_library_discovery_source: str
    hiprtc_library_discovery_source: str
    global_full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    architecture: str
    device_ordinal: int
    stream_identity_serialized: Literal[False] = False
    checkpoint_token_identity_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceDimensionsV1:
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_stage_count: int
    sealed_prefix_launch_count: int
    continuation_launch_count: int
    full_program_launch_count: int
    persistent_capability_count: Literal[11] = 11
    delegated_operator_capability_count: Literal[3] = 3
    delegated_workspace_capability_count: Literal[2] = 2
    physical_capability_count: Literal[16] = 16

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceProjectionV1:
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
class HipFgmresGlobalRecurrenceTelemetryV1:
    continuation_capability_reservation_count: Literal[1] = 1
    continuation_capability_consume_count: int = 0
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
    live_state_host_read_count: Literal[0] = 0
    live_state_host_branch_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceClaimsV1:
    sealed_checkpoint_parent_bound: bool
    continuation_capability_reserved: bool
    continuation_capability_consumed: bool
    direct11_csr3_scratch2_physical16_bound: bool
    same_kernel_runtime_device_stream_checkpoint_bound: bool
    canonical_continuation_suffix_bound: bool
    one_pending_stream_map_bound: bool
    fixed_suffix_fenced: bool
    completion_capability_issued: bool
    no_additional_allocation_or_borrow: bool
    no_h2d_or_d2h_copy: bool
    no_intermediate_synchronization: bool
    no_live_state_host_read_or_branch: bool
    actual_terminal_outcome_host_observed: Literal[False] = False
    authoritative_terminal_status_proven: Literal[False] = False
    numerical_parity_verified: Literal[False] = False
    solution_ready: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceReceiptV1:
    status: GlobalRecurrenceStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresGlobalRecurrenceReasonV1 | None
    bindings: HipFgmresGlobalRecurrenceBindingsV1
    dimensions: HipFgmresGlobalRecurrenceDimensionsV1
    projection: HipFgmresGlobalRecurrenceProjectionV1
    telemetry: HipFgmresGlobalRecurrenceTelemetryV1
    claims: HipFgmresGlobalRecurrenceClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_GLOBAL_RECURRENCE_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_global_recurrence_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRecurrenceOpenResultV1:
    context: HipFgmresGlobalRecurrenceExecutionContextV1
    receipt: HipFgmresGlobalRecurrenceReceiptV1

    @property
    def ready(self) -> bool:
        context = self.context
        with context._lock:
            return (
                self.receipt.status == "context_ready"
                and context._child_released is False
                and context._closed is False
            )


@dataclass(frozen=True, slots=True)
class _GlobalRecurrenceLaunchBinding:
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
    direct_capability_snapshot: tuple[Any, ...]
    pointer_values: tuple[tuple[str, int], ...]
    partition: HipFgmresGlobalSealedContinuationV1
    launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...]
    launch_values: tuple[tuple[tuple[str, Any], ...], ...]
    kernel_binding_snapshot: tuple[Any, ...]


class _GlobalRecurrenceDispatchSnapshot(NamedTuple):
    """Tuple-backed, non-mutable values used by every accepted launch."""

    kernel: HipRtcFgmresV2Kernel
    checkpoint_owner_token: object
    stream_pointer: int
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
    pointer_values: tuple[tuple[str, int], ...]


class _CompletionExportChildLeaseV1:
    """Weak-parent lease held strongly only by one completion exporter."""

    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _CompletionExportChildAuthorityV1:
    """Private frozen authority for the three completion-output buffers."""

    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    continuation_schedule_hash: str
    runtime: Any
    loaded_runtime: Any
    stream: Any
    stream_pointer: int
    device_ordinal: int
    architecture: str
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
    source_fgmres_plan: HipFgmresPlanV1
    source_recurrence_plan: HipFgmresRecurrencePlanV2
    source_execution_plan: ExecutionPlanV2
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    source_capabilities: tuple[Any, ...]
    source_snapshot: tuple[Any, ...]


_CONTEXT_MINT = object()


def _guard_state_change(name: str) -> Any:
    def decorate(operation: Any) -> Any:
        @wraps(operation)
        def guarded(
            self: HipFgmresGlobalRecurrenceExecutionContextV1,
            *arguments: Any,
            **keywords: Any,
        ) -> Any:
            with self._lock:
                if self._active_operation is not None:
                    _fail(
                        "hip_fgmres_global_recurrence_operation_reentrant",
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


class HipFgmresGlobalRecurrenceExecutionContextV1:
    """Single-use non-owning owner of the post-checkpoint fixed suffix."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Global recurrence contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._sealed: HipFgmresSealedCheckpointTransactionExecutionContextV1 | None = (
            None
        )
        self._continuation: HipFgmresSealedCheckpointContinuationCapabilityV1 | None = (
            None
        )
        self._token = _mint_global_recurrence_child_lease_v1()
        self._binding: _GlobalRecurrenceLaunchBinding | None = None
        self._binding_resource_snapshot: tuple[Any, ...] | None = None
        self._bindings: HipFgmresGlobalRecurrenceBindingsV1 | None = None
        self._dimensions: HipFgmresGlobalRecurrenceDimensionsV1 | None = None
        self._context_id = _ZERO_HASH
        self._telemetry = HipFgmresGlobalRecurrenceTelemetryV1()
        self._state: GlobalRecurrenceStatusV1 = "context_ready"
        self._reason: HipFgmresGlobalRecurrenceReasonV1 | None = None
        self._pending: HipFgmresGlobalRecurrencePendingV1 | None = None
        self._completion: HipFgmresGlobalRecurrenceCompletionCapabilityV1 | None = None
        self._pending_nonce = object()
        self._completion_nonce = object()
        self._pending_consume_started = False
        self._completion_export_child_reference: (
            weakref.ReferenceType[_CompletionExportChildLeaseV1] | None
        ) = None
        self._completion_export_capability_consumed = False
        self._completion_export_child_terminal = False
        self._child_released = False
        self._closed = False
        self._active_operation: str | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def completion_capability(
        self,
    ) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1 | None:
        if self._state != "recurrence_fenced" or self._closed or self._child_released:
            return None
        return self._completion

    def receipt(self) -> HipFgmresGlobalRecurrenceReceiptV1:
        with self._lock:
            if self._active_operation is not None:
                _fail(
                    "hip_fgmres_global_recurrence_receipt_inflight",
                    "/receipt/operation",
                    cleanup_owner=self,
                )
            if self._child_released and not self._closed:
                _fail(
                    "hip_fgmres_global_recurrence_close_incomplete",
                    "/receipt/close",
                    cleanup_owner=self,
                )
            if (
                self._telemetry.continuation_capability_consume_count == 1
                and not self._child_released
            ):
                self._reconcile_parent_recovery_progress()
            return self._build_receipt(self._state)

    @_guard_state_change("enqueue")
    def enqueue_remaining_global_recurrence(
        self,
    ) -> HipFgmresGlobalRecurrencePendingV1:
        """Consume continuation authority and submit every fixed suffix row."""

        with self._lock:
            if self._state == "recurrence_pending" and self._pending is not None:
                return self._pending
            if self._state == "pending_publication_pending":
                pending = self._mint_pending()
                self._state = "recurrence_pending"
                return pending
            if (
                self._state == "recurrence_pending"
                and self._pending is None
                and self._dimensions is not None
                and self._telemetry.kernel_launch_attempt_count
                == self._dimensions.continuation_launch_count
                and self._telemetry.kernel_launch_accept_lower_bound
                == self._dimensions.continuation_launch_count
                and self._telemetry.kernel_launch_accept_upper_bound
                == self._dimensions.continuation_launch_count
            ):
                self._state = "pending_publication_pending"
                pending = self._mint_pending()
                self._state = "recurrence_pending"
                return pending
            if self._state != "context_ready" or self._pending is not None:
                _fail(
                    "hip_fgmres_global_recurrence_state_invalid",
                    "/enqueue",
                    cleanup_owner=self,
                )
            self._validate_reserved_authority()
            parent = self._require_sealed()
            capability = self._require_continuation()
            try:
                parent._consume_global_recurrence_continuation_capability(
                    self._token,
                    capability,
                )
                self._record_continuation_consumed()
                binding = self._require_binding()
                launch_count = self._require_frozen_launch_count(binding)
                scratch_stage: dict[str, int] = {}
                for index in range(launch_count):
                    dispatch, launch = self._capture_submission(
                        binding,
                        index,
                    )
                    self._attempt(
                        lambda launch=launch, dispatch=dispatch, index=index: (
                            self._dispatch(
                                dispatch,
                                launch,
                                scratch_stage,
                                expected_prior_pending_count=index,
                            )
                        )
                    )
                self._require_current_binding(
                    expected_pending_operation_bounds=(launch_count, launch_count),
                    expected_binding=binding,
                )
                self._require_schedule_unchanged(binding)
                if (
                    self._telemetry.kernel_launch_attempt_count != launch_count
                    or self._telemetry.kernel_launch_accept_lower_bound != launch_count
                    or self._telemetry.kernel_launch_accept_upper_bound != launch_count
                ):
                    raise RuntimeError("global recurrence launch accounting mismatch")
            except BaseException as exc:
                consumed = self._reconcile_continuation_consumption()
                if consumed:
                    self._poison_after_enqueue_failure(exc)
                if not isinstance(exc, Exception):
                    raise
                if not consumed:
                    raise
                raise HipFgmresGlobalRecurrenceV1Error(
                    "hip_fgmres_global_recurrence_enqueue_failed",
                    "/enqueue",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            self._state = "pending_publication_pending"
            pending = self._mint_pending()
            self._state = "recurrence_pending"
            return pending

    def _record_continuation_consumed(self) -> None:
        self._telemetry = replace(
            self._telemetry,
            continuation_capability_consume_count=1,
        )
        self._state = "recurrence_pending"

    def _reconcile_continuation_consumption(self) -> bool:
        consumed = (
            self._require_sealed()._global_recurrence_continuation_capability_consumed(
                self._token
            )
        )
        if consumed:
            self._record_continuation_consumed()
        return consumed

    @_guard_state_change("fence")
    def synchronize(
        self,
        pending: HipFgmresGlobalRecurrencePendingV1,
    ) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
        """Fence once, acknowledge the pending map, and mint no-outcome completion."""

        with self._lock:
            self._validate_pending(pending)
            self._reconcile_parent_recovery_progress()
            if self._state == "recurrence_fenced" and self._completion is not None:
                return self._completion
            if self._state not in {
                "recurrence_pending",
                "poisoned_pending_fence",
                "fence_observed_ack_pending",
                "poisoned_fence_observed_ack_pending",
                "completion_publication_pending",
            }:
                _fail(
                    "hip_fgmres_global_recurrence_state_invalid",
                    "/fence",
                    cleanup_owner=self,
                )
            if self._state != "completion_publication_pending":
                self._observe_fence_and_consume()
                if self._state == "poisoned_fenced":
                    _fail(
                        "hip_fgmres_global_recurrence_poisoned",
                        "/fence",
                        cleanup_owner=self,
                    )
                try:
                    binding = self._require_frozen_binding()
                    self._require_current_binding(
                        expected_pending_operation_bounds=(0, 0),
                        expected_binding=binding,
                    )
                    self._require_schedule_unchanged(binding)
                except Exception as exc:
                    self._state = "poisoned_fenced"
                    self._set_poison_reason(
                        "hip_fgmres_global_recurrence_post_fence_authority_invalid",
                        _detail(exc),
                    )
                    raise HipFgmresGlobalRecurrenceV1Error(
                        "hip_fgmres_global_recurrence_post_fence_authority_invalid",
                        "/fence/post_authority",
                        _detail(exc),
                        pending=self._pending,
                        cleanup_owner=self,
                    ) from exc
                self._state = "completion_publication_pending"
            completion = self._mint_completion()
            self._state = "recurrence_fenced"
            return completion

    def synchronize_global_recurrence(
        self,
        pending: HipFgmresGlobalRecurrencePendingV1,
    ) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
        """Compatibility spelling for callers that prefer an explicit target."""

        return self.synchronize(pending)

    @_guard_state_change("cleanup")
    def close(self) -> None:
        """Drain accepted work before releasing the non-owning child lease."""

        with self._lock:
            if self._closed:
                return
            try:
                self._reap_completion_export_child_locked()
                if self._active_completion_export_child_locked() is not None:
                    _fail(
                        "hip_fgmres_global_recurrence_completion_export_child_active",
                        "/cleanup/completion_export",
                        cleanup_owner=self,
                    )
                if (
                    self._telemetry.continuation_capability_consume_count == 1
                    and not self._child_released
                ):
                    self._reconcile_parent_recovery_progress(
                        allow_release_in_progress=True
                    )
                if self._state in {
                    "pending_publication_pending",
                    "recurrence_pending",
                    "poisoned_pending_fence",
                    "fence_observed_ack_pending",
                    "poisoned_fence_observed_ack_pending",
                }:
                    self._observe_fence_and_consume()
                    if self._state == "fence_observed_ack_pending":
                        try:
                            binding = self._require_frozen_binding()
                            self._require_current_binding(
                                expected_pending_operation_bounds=(0, 0),
                                expected_binding=binding,
                            )
                            self._require_schedule_unchanged(binding)
                        except Exception as exc:
                            self._state = "poisoned_fenced"
                            self._set_poison_reason(
                                "hip_fgmres_global_recurrence_post_fence_authority_invalid",
                                _detail(exc),
                            )
                        else:
                            self._state = "completion_publication_pending"
                if self._state == "completion_publication_pending":
                    self._mint_completion()
                    self._state = "recurrence_fenced"
                self._release_child()
            except Exception as exc:
                raise HipFgmresGlobalRecurrenceV1Error(
                    "hip_fgmres_global_recurrence_cleanup_failed",
                    "/cleanup",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"
            with _GLOBAL_BINDING_LOCK:
                _GLOBAL_BINDINGS.pop(self, None)

    def _attempt(self, operation: Any) -> None:
        row = self._telemetry
        self._telemetry = replace(
            row,
            kernel_launch_attempt_count=row.kernel_launch_attempt_count + 1,
        )
        parent = self._require_sealed()
        parent._record_global_recurrence_launch_started(self._token)
        try:
            operation()
        except BaseException as exc:
            disposition = getattr(exc, "launch_disposition", None)
            parent._record_global_recurrence_launch_failed(
                self._token,
                definitely_not_accepted=(disposition in {"rejected", "not_attempted"}),
            )
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
        parent._record_global_recurrence_launch_succeeded(self._token)
        row = self._telemetry
        self._telemetry = replace(
            row,
            kernel_launch_accept_lower_bound=row.kernel_launch_accept_lower_bound + 1,
            kernel_launch_accept_upper_bound=row.kernel_launch_accept_upper_bound + 1,
        )

    def _reconcile_parent_recovery_progress(
        self,
        *,
        allow_release_in_progress: bool = False,
    ) -> None:
        """Repair child lifecycle state from the authoritative parent ledger."""

        progress = self._reconcile_parent_launch_telemetry(
            allow_release_in_progress=allow_release_in_progress,
        )
        if not progress.poisoned:
            return
        if self._state in {
            "completion_publication_pending",
            "recurrence_fenced",
            "context_closed",
        }:
            _fail(
                "hip_fgmres_global_recurrence_recovery_progress_invalid",
                "/lifetime/recovery_progress/poison",
                cleanup_owner=self,
            )
        binding = self._require_frozen_binding()
        binding.kernel._poison_checkpoint_transaction_owner(
            binding.checkpoint_owner_token
        )
        pending_snapshot = binding.kernel._checkpoint_pending_snapshot(
            binding.checkpoint_owner_token
        )
        pending_matches = _pending_snapshot_matches(
            pending_snapshot,
            stream_pointer=binding.stream_pointer,
            operation_bounds=(
                progress.launch_accept_lower_bound,
                progress.launch_accept_upper_bound,
            ),
        )
        if (
            type(pending_snapshot) is tuple
            and not pending_snapshot
            and progress.ack_started
        ):
            pending_matches = True
        if not pending_matches:
            _fail(
                "hip_fgmres_global_recurrence_recovery_progress_invalid",
                "/lifetime/recovery_progress/pending",
                cleanup_owner=self,
            )
        if self._state not in {
            "poisoned_fence_observed_ack_pending",
            "poisoned_fenced",
        }:
            self._state = (
                "poisoned_pending_fence" if pending_snapshot else "poisoned_no_work"
            )
        if self._reason is None:
            self._reason = HipFgmresGlobalRecurrenceReasonV1(
                "hip_fgmres_global_recurrence_enqueue_failed",
                "The parent recovery ledger retained an interrupted poison transition.",
            )
        if self._pending is None:
            self._pending = self._mint_pending()

    def _reconcile_parent_launch_telemetry(
        self,
        *,
        allow_release_in_progress: bool = False,
    ) -> Any:
        """Copy exact launch bounds without publishing poison capabilities."""

        progress = self._require_sealed()._global_recurrence_recovery_progress(
            self._token,
            allow_release_in_progress=allow_release_in_progress,
        )
        dimensions = self._dimensions
        integer_progress = (
            progress.launch_limit,
            progress.launch_attempt_count,
            progress.launch_accept_lower_bound,
            progress.launch_accept_upper_bound,
            progress.fence_attempt_count,
        )
        boolean_progress = (
            progress.abandoned,
            progress.child_live,
            progress.continuation_consumed,
            progress.poisoned,
            progress.fence_observed,
            progress.ack_started,
            progress.released,
            progress.terminal,
        )
        if (
            dimensions is None
            or any(type(value) is not int for value in integer_progress)
            or any(type(value) is not bool for value in boolean_progress)
            or (
                progress.acknowledged_launch_count is not None
                and type(progress.acknowledged_launch_count) is not int
            )
            or not progress.child_live
            or progress.abandoned
            or not progress.continuation_consumed
            or (progress.terminal and not progress.released)
            or (progress.released and not allow_release_in_progress)
            or progress.launch_limit != dimensions.continuation_launch_count
            or not 0
            <= progress.launch_accept_lower_bound
            <= progress.launch_accept_upper_bound
            <= progress.launch_attempt_count
            <= progress.launch_limit
        ):
            _fail(
                "hip_fgmres_global_recurrence_recovery_progress_invalid",
                "/lifetime/recovery_progress",
                cleanup_owner=self,
            )
        self._telemetry = replace(
            self._telemetry,
            continuation_capability_consume_count=1,
            kernel_launch_attempt_count=progress.launch_attempt_count,
            kernel_launch_accept_lower_bound=(progress.launch_accept_lower_bound),
            kernel_launch_accept_upper_bound=(progress.launch_accept_upper_bound),
        )
        return progress

    def _dispatch(
        self,
        submission: _GlobalRecurrenceDispatchSnapshot,
        launch: tuple[tuple[str, Any], ...],
        scratch_stage: dict[str, int],
        *,
        expected_prior_pending_count: int,
    ) -> None:
        row = dict(launch)
        pointers = dict(submission.pointer_values)
        token = submission.checkpoint_owner_token
        if row["submission_kind"] == "control":
            result = submission.kernel.launch_control(
                submission.stream_pointer,
                row["mode"],
                row["expected_schedule_epoch"],
                row["expected_restart"],
                row["expected_column"],
                row["row_index"],
                row["pass_index"],
                submission.free_dof_count,
                submission.restart_dimension,
                submission.max_iterations,
                submission.maximum_restart_count,
                submission.stagnation_checkpoint_limit,
                submission.absolute_tolerance,
                submission.relative_tolerance,
                submission.authoritative_tolerance,
                submission.stagnation_relative_tolerance,
                submission.divergence_factor,
                pointers["packed_dense_state"],
                pointers["fgmres_control_state_v2"],
                pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_expected_prior_pending_count=(expected_prior_pending_count),
            )
        elif row["submission_kind"] == "vector":
            result = submission.kernel.launch_vector(
                submission.stream_pointer,
                row["mode"],
                row["vector_gate"],
                row["expected_schedule_epoch"],
                row["expected_restart"],
                row["expected_column"],
                submission.free_dof_count,
                row["logical_index"],
                *(pointers[role] for role in _DIRECT_ROLES),
                _checkpoint_owner_token=token,
                _checkpoint_expected_prior_pending_count=(expected_prior_pending_count),
            )
        elif row["submission_kind"] == "spmv":
            result = submission.kernel.launch_csr_spmv_indexed(
                submission.stream_pointer,
                row["mode"],
                row["expected_schedule_epoch"],
                row["expected_restart"],
                row["expected_column"],
                submission.free_dof_count,
                submission.reduced_csr_nnz,
                row["logical_index"],
                pointers["reduced_csr_row_ptr"],
                pointers["reduced_csr_column_indices"],
                pointers["reduced_csr_values"],
                pointers["solution_x"],
                pointers["work_w"],
                pointers["basis_v"],
                pointers["preconditioned_basis_z"],
                pointers["fgmres_control_state_v2"],
                pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_expected_prior_pending_count=(expected_prior_pending_count),
            )
        elif row["submission_kind"] == "reduction":
            tree_id = row["reduction_tree_id"]
            if type(tree_id) is not str or not tree_id:
                _fail(
                    "hip_fgmres_global_recurrence_schedule_invalid",
                    "/enqueue/schedule/reduction_tree_id",
                    cleanup_owner=self,
                )
            stage = scratch_stage.get(tree_id, 0)
            reduction_input = pointers[
                "reduction_ping" if stage % 2 == 0 else "reduction_pong"
            ]
            reduction_output = pointers[
                "reduction_pong" if stage % 2 == 0 else "reduction_ping"
            ]
            result = submission.kernel.launch_reduction(
                submission.stream_pointer,
                row["mode"],
                row["reduction_target"],
                row["expected_schedule_epoch"],
                row["expected_restart"],
                row["expected_column"],
                row["expected_reduction_epoch"],
                row["value_count"],
                row["logical_index"],
                pointers["reduced_load"],
                pointers["solution_x"],
                pointers["true_residual"],
                pointers["work_w"],
                pointers["basis_v"],
                reduction_input,
                reduction_output,
                pointers["fgmres_control_state_v2"],
                pointers["solve_record"],
                _checkpoint_owner_token=token,
                _checkpoint_expected_prior_pending_count=(expected_prior_pending_count),
            )
            scratch_stage[tree_id] = stage + 1
        else:
            _fail(
                "hip_fgmres_global_recurrence_schedule_invalid",
                "/enqueue/schedule/submission_kind",
                cleanup_owner=self,
            )
        if result is not None:
            _fail(
                "hip_fgmres_global_recurrence_kernel_contract_invalid",
                "/enqueue/kernel",
                cleanup_owner=self,
            )

    def _poison_after_enqueue_failure(self, error: BaseException) -> None:
        binding = self._require_frozen_binding()
        self._require_sealed()._record_global_recurrence_poisoned(self._token)
        # Parent launch accounting is authoritative.  Refresh it before any
        # pending capability can escape through the enqueue error.
        self._reconcile_parent_launch_telemetry()
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
        self._reason = HipFgmresGlobalRecurrenceReasonV1(
            "hip_fgmres_global_recurrence_enqueue_failed",
            _detail(error),
        )
        self._pending = self._mint_pending()

    def _observe_fence_and_consume(self) -> None:
        self._reconcile_parent_recovery_progress()
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
            try:
                fence_required = (
                    self._require_sealed()._global_recurrence_fence_required(
                        self._token
                    )
                )
            except Exception as exc:
                raise HipFgmresGlobalRecurrenceV1Error(
                    "hip_fgmres_global_recurrence_fence_failed",
                    "/fence/query",
                    _detail(exc),
                    pending=self._pending,
                    cleanup_owner=self,
                ) from exc
            if fence_required:
                row = self._telemetry
                self._telemetry = replace(
                    row,
                    fence_attempt_count=row.fence_attempt_count + 1,
                )
                self._require_sealed()._record_global_recurrence_fence_attempt(
                    self._token
                )
                try:
                    binding.kernel._synchronize_checkpoint_stream(
                        binding.checkpoint_owner_token,
                        binding.stream_pointer,
                    )
                except Exception as exc:
                    raise HipFgmresGlobalRecurrenceV1Error(
                        "hip_fgmres_global_recurrence_fence_failed",
                        "/fence/synchronize",
                        _detail(exc),
                        pending=self._pending,
                        cleanup_owner=self,
                    ) from exc
                self._require_sealed()._record_global_recurrence_fence_observed(
                    self._token
                )
                row = self._telemetry
                self._telemetry = replace(
                    row,
                    fence_success_count=row.fence_success_count + 1,
                )
            elif self._telemetry.fence_success_count == 0:
                self._telemetry = replace(
                    self._telemetry,
                    fence_success_count=1,
                )
            elif self._telemetry.fence_success_count != 1:
                _fail(
                    "hip_fgmres_global_recurrence_fence_accounting_invalid",
                    "/fence/telemetry",
                    cleanup_owner=self,
                )
            self._state = (
                "poisoned_fence_observed_ack_pending"
                if self._state == "poisoned_pending_fence"
                else "fence_observed_ack_pending"
            )
        was_started = self._pending_consume_started
        self._require_sealed()._record_global_recurrence_ack_started(self._token)
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
            raise HipFgmresGlobalRecurrenceV1Error(
                "hip_fgmres_global_recurrence_pending_consume_failed",
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
            raise HipFgmresGlobalRecurrenceV1Error(
                "hip_fgmres_global_recurrence_pending_observation_failed",
                "/fence/pending_snapshot",
                _detail(exc),
                pending=self._pending,
                cleanup_owner=self,
            ) from exc
        if pending_snapshot:
            self._poison_ack_pending(
                "hip_fgmres_global_recurrence_pending_consume_mismatch",
                "The fenced reservation map remained non-empty after acknowledgement.",
            )
            _fail(
                "hip_fgmres_global_recurrence_pending_consume_mismatch",
                "/fence/pending_snapshot",
                cleanup_owner=self,
            )
        if consumed == 0 and was_started and lower == upper:
            consumed = upper
        elif consumed == 0 and was_started and lower != upper:
            self._state = "poisoned_fenced"
            self._set_poison_reason(
                "hip_fgmres_global_recurrence_pending_consume_ambiguous",
                "The accepted launch count remained ambiguous after acknowledgement.",
            )
            self._telemetry = replace(self._telemetry, consumed_launch_count=0)
            return
        if not lower <= consumed <= upper or (lower == upper and consumed != lower):
            self._state = "poisoned_fenced"
            self._set_poison_reason(
                "hip_fgmres_global_recurrence_pending_consume_mismatch",
                "The acknowledged reservation count did not match the accepted interval.",
            )
            try:
                binding.kernel._poison_checkpoint_transaction_owner(
                    binding.checkpoint_owner_token
                )
            except BaseException:
                pass
            _fail(
                "hip_fgmres_global_recurrence_pending_consume_mismatch",
                "/fence/consume",
                cleanup_owner=self,
            )
        self._require_sealed()._record_global_recurrence_acknowledged(
            self._token,
            consumed,
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
            self._reason = HipFgmresGlobalRecurrenceReasonV1(code, _detail(detail))

    def _validate_reserved_authority(self) -> None:
        parent = self._require_sealed()
        capability = self._require_continuation()
        parent._require_global_recurrence_child(
            self._token,
            continuation_consumed=False,
        )
        validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
            capability,
            expected_context=parent,
        )
        binding = self._require_binding()
        self._require_schedule_unchanged(binding)
        self._require_current_binding(
            expected_pending_operation_bounds=(0, 0),
            consumed=False,
            expected_binding=binding,
        )

    def _require_current_binding(
        self,
        *,
        expected_pending_operation_bounds: tuple[int, int],
        consumed: bool = True,
        expected_binding: _GlobalRecurrenceLaunchBinding | None = None,
    ) -> None:
        parent = self._require_sealed()
        parent._require_global_recurrence_child(
            self._token,
            continuation_consumed=consumed,
        )
        expected = self._require_frozen_binding()
        if expected_binding is not None and expected_binding is not expected:
            _fail(
                "hip_fgmres_global_recurrence_binding_changed",
                "/authority/binding",
                cleanup_owner=self,
            )
        try:
            current = _capture_binding(
                parent,
                self._token,
                expected.partition,
                expected.launch_values,
                continuation_consumed=consumed,
                expected_pending_operation_bounds=(expected_pending_operation_bounds),
            )
            pending_snapshot = current.kernel._checkpoint_pending_snapshot(
                current.checkpoint_owner_token
            )
        except Exception as exc:
            raise HipFgmresGlobalRecurrenceV1Error(
                "hip_fgmres_global_recurrence_binding_changed",
                "/authority/binding",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        if (
            self._binding_resource_snapshot is None
            or _resource_values(expected) != self._binding_resource_snapshot
            or _resource_values(current) != self._binding_resource_snapshot
            or not _pending_snapshot_matches(
                pending_snapshot,
                stream_pointer=current.stream_pointer,
                operation_bounds=expected_pending_operation_bounds,
            )
        ):
            _fail(
                "hip_fgmres_global_recurrence_binding_changed",
                "/authority/binding",
                cleanup_owner=self,
            )

    def _require_frozen_launch_count(
        self,
        binding: _GlobalRecurrenceLaunchBinding,
    ) -> int:
        with _GLOBAL_BINDING_LOCK:
            witness = _GLOBAL_BINDINGS.get(self)
        if (
            witness is None
            or type(witness) is not tuple
            or len(witness) != 4
            or witness[0] is not binding
            or type(witness[2]) is not tuple
            or not witness[2]
        ):
            _fail(
                "hip_fgmres_global_recurrence_binding_changed",
                "/authority/submission_program",
                cleanup_owner=self,
            )
        return len(witness[2])

    def _capture_submission(
        self,
        binding: _GlobalRecurrenceLaunchBinding,
        index: int,
    ) -> tuple[
        _GlobalRecurrenceDispatchSnapshot,
        tuple[tuple[str, Any], ...],
    ]:
        """Return only canonical immutable values after one live-state check."""

        self._require_sealed()._require_global_recurrence_child(
            self._token,
            continuation_consumed=True,
        )
        with _GLOBAL_BINDING_LOCK:
            witness = _GLOBAL_BINDINGS.get(self)
        resources = self._binding_resource_snapshot
        try:
            launches = binding.launches
            launch_values = binding.launch_values
            partition_launches = binding.partition.continuation.launches
            current_launch = launches[index]
            current_launch_value = _launch_value(current_launch)
        except (AttributeError, IndexError, TypeError, ValueError) as exc:
            raise HipFgmresGlobalRecurrenceV1Error(
                "hip_fgmres_global_recurrence_schedule_changed",
                f"/authority/schedule/{index}",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        if (
            witness is None
            or type(witness) is not tuple
            or len(witness) != 4
            or witness[0] is not binding
            or resources is None
            or witness[1] is not resources
            or _resource_values(binding) != resources
            or type(witness[3]) is not _GlobalRecurrenceDispatchSnapshot
            or _exact_value_snapshot(_dispatch_snapshot(binding))
            != _exact_value_snapshot(witness[3])
        ):
            _fail(
                "hip_fgmres_global_recurrence_binding_changed",
                "/authority/submission_binding",
                cleanup_owner=self,
            )
        if (
            not 0 <= index < len(witness[2])
            or launches is not partition_launches
            or launch_values is not witness[2]
            or current_launch is not launches[index]
            or _exact_value_snapshot(current_launch_value)
            != _exact_value_snapshot(witness[2][index])
        ):
            _fail(
                "hip_fgmres_global_recurrence_schedule_changed",
                f"/authority/schedule/{index}",
                cleanup_owner=self,
            )
        return witness[3], witness[2][index]

    def _require_frozen_fence_authority(
        self,
        *,
        expected_pending_operation_bounds: tuple[int, int],
    ) -> None:
        binding = self._require_frozen_binding()
        self._require_sealed()._require_global_recurrence_child(
            self._token,
            continuation_consumed=True,
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
            raise HipFgmresGlobalRecurrenceV1Error(
                "hip_fgmres_global_recurrence_fence_authority_invalid",
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
                "hip_fgmres_global_recurrence_fence_authority_invalid",
                "/fence/authority",
                cleanup_owner=self,
            )

    def _require_schedule_unchanged(
        self,
        binding: _GlobalRecurrenceLaunchBinding,
    ) -> None:
        if (
            binding.launches is not binding.partition.continuation.launches
            or _exact_value_snapshot(_launch_values(binding.launches))
            != _exact_value_snapshot(binding.launch_values)
            or binding.partition.continuation.canonical_sha256
            != self._require_bindings().continuation_schedule_hash
        ):
            _fail(
                "hip_fgmres_global_recurrence_schedule_changed",
                "/authority/schedule",
                cleanup_owner=self,
            )

    def _validate_pending(self, pending: HipFgmresGlobalRecurrencePendingV1) -> None:
        if (
            type(pending) is not HipFgmresGlobalRecurrencePendingV1
            or pending._issuer is not self
            or pending._nonce is not self._pending_nonce
            or pending._snapshot != _pending_snapshot(pending)
            or pending is not self._pending
        ):
            _fail("hip_fgmres_global_recurrence_pending_invalid", "/pending")

    def _mint_pending(self) -> HipFgmresGlobalRecurrencePendingV1:
        if self._state not in {
            "pending_publication_pending",
            "poisoned_no_work",
            "poisoned_pending_fence",
        }:
            _fail(
                "hip_fgmres_global_recurrence_pending_publication_state_invalid",
                "/pending/state",
                cleanup_owner=self,
            )
        if self._pending is not None:
            return self._pending
        pending = _issue_capability(
            HipFgmresGlobalRecurrencePendingV1,
            {
                "context_id": self._context_id,
                "attempted_launch_count": self._telemetry.kernel_launch_attempt_count,
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
        self._pending = pending
        return pending

    def _mint_completion(self) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
        if self._state != "completion_publication_pending":
            _fail(
                "hip_fgmres_global_recurrence_completion_publication_state_invalid",
                "/completion/state",
                cleanup_owner=self,
            )
        if self._completion is not None:
            return self._completion
        receipt = self._build_receipt(
            "recurrence_fenced",
            completion_will_be_published=True,
        )
        capability = _issue_capability(
            HipFgmresGlobalRecurrenceCompletionCapabilityV1,
            {
                "context_id": self._context_id,
                "receipt_hash": receipt.receipt_hash,
                "continuation_schedule_hash": (
                    receipt.bindings.continuation_schedule_hash
                ),
                "fenced_launch_count": receipt.dimensions.continuation_launch_count,
                "_issuer": self,
                "_nonce": self._completion_nonce,
            },
        )
        object.__setattr__(
            capability,
            "_snapshot",
            _completion_snapshot(capability),
        )
        self._completion = capability
        return capability

    def _reserve_completion_export_child(
        self,
        token: _CompletionExportChildLeaseV1,
        capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> _CompletionExportChildLeaseV1:
        """Reserve the sole downstream raw-export child without consuming it."""

        with self._lock:
            self._reap_completion_export_child_locked()
            validate_hip_fgmres_global_recurrence_completion_capability_v1(
                capability,
                expected_context=self,
            )
            if (
                type(token) is not _CompletionExportChildLeaseV1
                or self._closed
                or self._child_released
                or self._state != "recurrence_fenced"
                or self._completion_export_capability_consumed
                or self._completion_export_child_terminal
                or self._active_completion_export_child_locked() is not None
            ):
                _fail(
                    "hip_fgmres_global_recurrence_completion_export_reservation_invalid",
                    "/completion_export/reserve",
                    cleanup_owner=self,
                )
            self._completion_export_child_reference = weakref.ref(token)
            return token

    def _consume_completion_export_capability(
        self,
        token: _CompletionExportChildLeaseV1,
        capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> None:
        """Irreversibly consume completion authority before the first host read."""

        with self._lock:
            self._require_completion_export_child_locked(token, consumed=False)
            validate_hip_fgmres_global_recurrence_completion_capability_v1(
                capability,
                expected_context=self,
            )
            self._completion_export_capability_consumed = True

    def _completion_export_capability_is_consumed(
        self,
        token: _CompletionExportChildLeaseV1,
    ) -> bool:
        with self._lock:
            self._require_completion_export_child_locked(token)
            return self._completion_export_capability_consumed

    def _completion_export_child_token_is_active(
        self,
        token: _CompletionExportChildLeaseV1,
    ) -> bool:
        with self._lock:
            self._reap_completion_export_child_locked()
            return token is self._active_completion_export_child_locked()

    def _completion_export_child_authority(
        self,
        token: _CompletionExportChildLeaseV1,
        capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
        *,
        consumed: bool,
    ) -> _CompletionExportChildAuthorityV1:
        """Return a fresh exact authority for the immutable output-buffer subset."""

        with self._lock:
            self._require_completion_export_child_locked(token, consumed=consumed)
            validate_hip_fgmres_global_recurrence_completion_capability_v1(
                capability,
                expected_context=self,
            )
            binding = self._require_frozen_binding()
            self._require_current_binding(
                expected_pending_operation_bounds=(0, 0),
                expected_binding=binding,
            )
            self._require_schedule_unchanged(binding)
            direct = binding.direct_capabilities
            if (
                type(direct) is not tuple
                or len(direct) != len(_DIRECT_ROLES)
                or tuple(getattr(row, "role", None) for row in direct) != _DIRECT_ROLES
                or tuple(getattr(row, "pointer_snapshot", None) for row in direct)
                != tuple(pointer for _role, pointer in binding.pointer_values[:11])
            ):
                _fail(
                    "hip_fgmres_global_recurrence_completion_export_sources_invalid",
                    "/completion_export/authority/sources",
                    cleanup_owner=self,
                )
            source_roles = ("solution_x", "true_residual", "solve_record")
            by_role = {row.role: row for row in direct}
            sources = tuple(by_role[role] for role in source_roles)
            source_snapshot = _completion_export_source_snapshot(binding, sources)
            receipt = self._build_receipt("recurrence_fenced")
            bindings = self._require_bindings()
            authority = _CompletionExportChildAuthorityV1(
                global_context_id=self._context_id,
                global_receipt_hash=receipt.receipt_hash,
                completion_receipt_hash=capability.receipt_hash,
                continuation_schedule_hash=capability.continuation_schedule_hash,
                runtime=binding.runtime,
                loaded_runtime=binding.loaded_runtime,
                stream=binding.stream,
                stream_pointer=binding.stream_pointer,
                device_ordinal=binding.device_ordinal,
                architecture=binding.architecture,
                free_dof_count=binding.free_dof_count,
                restart_dimension=binding.restart_dimension,
                max_iterations=binding.max_iterations,
                maximum_restart_count=binding.maximum_restart_count,
                stagnation_checkpoint_limit=binding.stagnation_checkpoint_limit,
                absolute_tolerance=binding.absolute_tolerance,
                relative_tolerance=binding.relative_tolerance,
                authoritative_tolerance=binding.authoritative_tolerance,
                stagnation_relative_tolerance=(binding.stagnation_relative_tolerance),
                divergence_factor=binding.divergence_factor,
                source_fgmres_plan=binding.source_fgmres_plan,
                source_recurrence_plan=binding.source_recurrence_plan,
                source_execution_plan=binding.source_execution_plan,
                recurrence_plan_hash=bindings.recurrence_plan_hash,
                recurrence_kernel_abi_hash=bindings.recurrence_kernel_abi_hash,
                combined_recurrence_abi_hash=bindings.combined_recurrence_abi_hash,
                kernel_identity_hash=bindings.kernel_identity_hash,
                kernel_source_sha256=bindings.kernel_source_sha256,
                direct_generation_binding_hash=(
                    bindings.direct_generation_binding_hash
                ),
                physical_projection_hash=bindings.physical_projection_hash,
                source_capabilities=sources,
                source_snapshot=source_snapshot,
            )
            self._require_completion_export_child_locked(token, consumed=consumed)
            if _completion_export_source_snapshot(binding, sources) != source_snapshot:
                _fail(
                    "hip_fgmres_global_recurrence_completion_export_sources_changed",
                    "/completion_export/authority/sources",
                    cleanup_owner=self,
                )
            return authority

    def _release_completion_export_child(
        self,
        token: _CompletionExportChildLeaseV1,
    ) -> None:
        with self._lock:
            self._require_completion_export_child_locked(token)
            self._completion_export_child_reference = None
            if self._completion_export_capability_consumed:
                self._completion_export_child_terminal = True

    def _require_completion_export_child_locked(
        self,
        token: _CompletionExportChildLeaseV1,
        *,
        consumed: bool | None = None,
    ) -> None:
        self._reap_completion_export_child_locked()
        if (
            type(token) is not _CompletionExportChildLeaseV1
            or token is not self._active_completion_export_child_locked()
            or self._closed
            or self._child_released
            or self._state != "recurrence_fenced"
            or self._completion_export_child_terminal
            or (
                consumed is not None
                and self._completion_export_capability_consumed is not consumed
            )
        ):
            _fail(
                "hip_fgmres_global_recurrence_completion_export_child_invalid",
                "/completion_export/lifetime",
                cleanup_owner=self,
            )

    def _active_completion_export_child_locked(
        self,
    ) -> _CompletionExportChildLeaseV1 | None:
        reference = self._completion_export_child_reference
        return None if reference is None else reference()

    def _reap_completion_export_child_locked(self) -> None:
        reference = self._completion_export_child_reference
        if reference is None or reference() is not None:
            return
        if self._completion_export_capability_consumed:
            self._completion_export_child_terminal = True
        self._completion_export_child_reference = None

    def _release_child(self) -> None:
        if self._child_released:
            return
        parent = self._require_sealed()
        try:
            parent._release_global_recurrence_child(self._token)
        except BaseException as exc:
            try:
                still_active = parent._global_recurrence_child_token_is_active(
                    self._token
                )
            except BaseException:
                raise
            if still_active:
                raise
            self._child_released = True
            if not isinstance(exc, Exception):
                raise
            return
        self._child_released = True

    def _require_sealed(
        self,
    ) -> HipFgmresSealedCheckpointTransactionExecutionContextV1:
        if (
            type(self._sealed)
            is not HipFgmresSealedCheckpointTransactionExecutionContextV1
        ):
            _fail(
                "hip_fgmres_global_recurrence_sealed_context_invalid",
                "/sealed_context",
            )
        return self._sealed

    def _require_continuation(
        self,
    ) -> HipFgmresSealedCheckpointContinuationCapabilityV1:
        if (
            type(self._continuation)
            is not HipFgmresSealedCheckpointContinuationCapabilityV1
        ):
            _fail(
                "hip_fgmres_global_recurrence_continuation_invalid",
                "/continuation",
            )
        return self._continuation

    def _require_bindings(self) -> HipFgmresGlobalRecurrenceBindingsV1:
        if type(self._bindings) is not HipFgmresGlobalRecurrenceBindingsV1:
            _fail("hip_fgmres_global_recurrence_binding_invalid", "/bindings")
        return self._bindings

    def _require_binding(self) -> _GlobalRecurrenceLaunchBinding:
        binding = self._require_frozen_binding()
        with _GLOBAL_BINDING_LOCK:
            witness = _GLOBAL_BINDINGS.get(self)
        if (
            witness is None
            or type(witness) is not tuple
            or len(witness) != 4
            or witness[0] is not binding
            or witness[1] is not self._binding_resource_snapshot
            or _resource_values(binding) != witness[1]
            or _exact_value_snapshot(_launch_values(binding.launches))
            != _exact_value_snapshot(witness[2])
            or binding.launch_values is not witness[2]
            or type(witness[3]) is not _GlobalRecurrenceDispatchSnapshot
            or _exact_value_snapshot(_dispatch_snapshot(binding))
            != _exact_value_snapshot(witness[3])
        ):
            _fail(
                "hip_fgmres_global_recurrence_binding_invalid",
                "/authority/binding",
                cleanup_owner=self,
            )
        return binding

    def _require_frozen_binding(self) -> _GlobalRecurrenceLaunchBinding:
        with _GLOBAL_BINDING_LOCK:
            witness = _GLOBAL_BINDINGS.get(self)
        if (
            witness is None
            or type(witness) is not tuple
            or len(witness) != 4
            or type(witness[0]) is not _GlobalRecurrenceLaunchBinding
        ):
            _fail(
                "hip_fgmres_global_recurrence_binding_invalid",
                "/authority/frozen_binding",
                cleanup_owner=self,
            )
        return witness[0]

    def _build_receipt(
        self,
        status: GlobalRecurrenceStatusV1,
        *,
        completion_will_be_published: bool = False,
    ) -> HipFgmresGlobalRecurrenceReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail("hip_fgmres_global_recurrence_receipt_unavailable", "/receipt")
        bound = status not in {"cleanup_failed", "context_closed"}
        consumed = self._telemetry.continuation_capability_consume_count == 1
        launch_count = self._dimensions.continuation_launch_count
        fenced = (
            status
            in {
                "completion_publication_pending",
                "recurrence_fenced",
                "context_closed",
            }
            and self._reason is None
            and consumed
            and self._telemetry.kernel_launch_attempt_count == launch_count
            and self._telemetry.kernel_launch_accept_lower_bound == launch_count
            and self._telemetry.kernel_launch_accept_upper_bound == launch_count
            and self._telemetry.fence_success_count == 1
            and self._telemetry.consumed_launch_count == launch_count
        )
        completion_issued = status in {"recurrence_fenced", "context_closed"} and (
            self._completion is not None or completion_will_be_published
        )
        claims = HipFgmresGlobalRecurrenceClaimsV1(
            sealed_checkpoint_parent_bound=bound,
            continuation_capability_reserved=bound,
            continuation_capability_consumed=consumed,
            direct11_csr3_scratch2_physical16_bound=bound,
            same_kernel_runtime_device_stream_checkpoint_bound=bound,
            canonical_continuation_suffix_bound=bound,
            one_pending_stream_map_bound=bound,
            fixed_suffix_fenced=fenced,
            completion_capability_issued=completion_issued,
            no_additional_allocation_or_borrow=bound,
            no_h2d_or_d2h_copy=bound,
            no_intermediate_synchronization=bound,
            no_live_state_host_read_or_branch=bound,
        )
        draft = HipFgmresGlobalRecurrenceReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_GLOBAL_RECURRENCE_EVIDENCE_SCOPE_V1,
            actual_backend=self._require_sealed().receipt().actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            projection=HipFgmresGlobalRecurrenceProjectionV1(
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


_GLOBAL_BINDING_LOCK = threading.RLock()
_GLOBAL_BINDINGS: weakref.WeakKeyDictionary[
    HipFgmresGlobalRecurrenceExecutionContextV1,
    tuple[
        _GlobalRecurrenceLaunchBinding,
        tuple[Any, ...],
        tuple[tuple[tuple[str, Any], ...], ...],
        _GlobalRecurrenceDispatchSnapshot,
    ],
] = weakref.WeakKeyDictionary()


def open_hip_fgmres_global_recurrence_context_v1(
    sealed_context: HipFgmresSealedCheckpointTransactionExecutionContextV1,
    continuation_capability: HipFgmresSealedCheckpointContinuationCapabilityV1,
) -> HipFgmresGlobalRecurrenceOpenResultV1:
    """Reserve a non-owning child and bind the canonical sealed suffix."""

    context = HipFgmresGlobalRecurrenceExecutionContextV1(_mint=_CONTEXT_MINT)
    reserved = False
    try:
        if (
            type(sealed_context)
            is not HipFgmresSealedCheckpointTransactionExecutionContextV1
        ):
            _fail(
                "hip_fgmres_global_recurrence_sealed_context_invalid",
                "/sealed_context",
            )
        context._sealed = sealed_context
        context._continuation = continuation_capability
        validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
            continuation_capability,
            expected_context=sealed_context,
        )
        sealed_receipt = sealed_context.receipt()
        if sealed_receipt.status != "transaction_fenced":
            _fail(
                "hip_fgmres_global_recurrence_sealed_checkpoint_invalid",
                "/continuation",
            )
        if sealed_receipt.dimensions.max_iterations == 0:
            _fail(
                "hip_fgmres_global_recurrence_zero_iteration_unavailable",
                "/dimensions/max_iterations",
            )
        partition = compile_hip_fgmres_global_sealed_continuation_v1(
            sealed_receipt.dimensions.free_dof_count,
            sealed_receipt.dimensions.restart_dimension,
            sealed_receipt.dimensions.max_iterations,
        )
        launch_values = _launch_values(partition.continuation.launches)
        acquired = sealed_context._reserve_global_recurrence_child(
            context._token,
            continuation_capability,
        )
        if acquired is not context._token:
            _fail(
                "hip_fgmres_global_recurrence_child_changed",
                "/lifetime",
            )
        reserved = True
        binding = _capture_binding(
            sealed_context,
            context._token,
            partition,
            launch_values,
            continuation_consumed=False,
            expected_pending_operation_bounds=(0, 0),
        )
        sealed_context._register_global_recurrence_recovery_cell(
            context._token,
            kernel=binding.kernel,
            checkpoint_owner_token=binding.checkpoint_owner_token,
            stream_pointer=binding.stream_pointer,
            launch_limit=len(launch_values),
        )
        context._binding = binding
        context._binding_resource_snapshot = _resource_values(binding)
        with _GLOBAL_BINDING_LOCK:
            _GLOBAL_BINDINGS[context] = (
                binding,
                context._binding_resource_snapshot,
                launch_values,
                _dispatch_snapshot(binding),
            )
        sealed_bindings = sealed_receipt.bindings
        context._context_id = canonical_hash(
            {
                "profile": HIP_FGMRES_GLOBAL_RECURRENCE_CAPABILITY_PROFILE_V1,
                "sealed_checkpoint_context_id": sealed_receipt.context_id,
                "sealed_checkpoint_receipt_hash": sealed_receipt.receipt_hash,
                "continuation_schedule_hash": (partition.continuation.canonical_sha256),
                "direct_generation_binding_hash": (
                    sealed_bindings.direct_generation_binding_hash
                ),
                "physical_projection_hash": sealed_bindings.physical_projection_hash,
            }
        )
        context._bindings = HipFgmresGlobalRecurrenceBindingsV1(
            sealed_receipt.context_id,
            sealed_receipt.receipt_hash,
            sealed_bindings.canonical_predecessor_context_id,
            sealed_bindings.live_context_id,
            sealed_bindings.primitive_evidence_scope,
            sealed_bindings.primitive_actual_backend,
            sealed_bindings.recurrence_plan_hash,
            sealed_bindings.recurrence_kernel_abi_hash,
            sealed_bindings.combined_recurrence_abi_hash,
            sealed_bindings.kernel_identity_hash,
            sealed_bindings.kernel_source_sha256,
            sealed_bindings.kernel_origin,
            sealed_bindings.runtime_library_discovery_source,
            sealed_bindings.hiprtc_library_discovery_source,
            partition.full.canonical_sha256,
            partition.sealed_prefix.canonical_sha256,
            partition.continuation.canonical_sha256,
            sealed_bindings.direct_generation_binding_hash,
            sealed_bindings.physical_projection_hash,
            binding.architecture,
            binding.device_ordinal,
        )
        plan = partition.plan
        context._dimensions = HipFgmresGlobalRecurrenceDimensionsV1(
            binding.free_dof_count,
            binding.reduced_csr_nnz,
            binding.restart_dimension,
            binding.max_iterations,
            binding.maximum_restart_count,
            plan.reduction_stage_count,
            partition.sealed_prefix.launch_count,
            partition.continuation.launch_count,
            partition.full.launch_count,
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        return HipFgmresGlobalRecurrenceOpenResultV1(context, receipt)
    except BaseException as primary:
        try:
            if (
                type(sealed_context)
                is HipFgmresSealedCheckpointTransactionExecutionContextV1
            ):
                reserved = (
                    reserved
                    or sealed_context._global_recurrence_child_token_is_active(
                        context._token
                    )
                )
        except BaseException as reconcile:
            context._state = "cleanup_failed"
            context._reason = HipFgmresGlobalRecurrenceReasonV1(
                "hip_fgmres_global_recurrence_open_reservation_reconcile_failed",
                _detail(reconcile),
            )
            raise HipFgmresGlobalRecurrenceV1Error(
                context._reason.code,
                "/open/reservation_reconcile",
                f"open failed: {_detail(primary)}; reservation reconciliation "
                f"failed: {context._reason.detail}",
                cleanup_owner=context,
            ) from reconcile
        if reserved:
            try:
                context._release_child()
                with _GLOBAL_BINDING_LOCK:
                    _GLOBAL_BINDINGS.pop(context, None)
            except BaseException as rollback:
                if context._child_released:
                    with _GLOBAL_BINDING_LOCK:
                        _GLOBAL_BINDINGS.pop(context, None)
                    raise
                context._state = "cleanup_failed"
                context._reason = HipFgmresGlobalRecurrenceReasonV1(
                    "hip_fgmres_global_recurrence_open_rollback_failed",
                    _detail(rollback),
                )
                raise HipFgmresGlobalRecurrenceV1Error(
                    context._reason.code,
                    "/open/rollback",
                    f"open failed: {_detail(primary)}; rollback failed: "
                    f"{context._reason.detail}",
                    cleanup_owner=context,
                ) from rollback
        raise


def _capture_binding(
    sealed: HipFgmresSealedCheckpointTransactionExecutionContextV1,
    child_token: object,
    partition: HipFgmresGlobalSealedContinuationV1,
    launch_values: tuple[tuple[tuple[str, Any], ...], ...],
    *,
    continuation_consumed: bool,
    expected_pending_operation_bounds: tuple[int, int],
) -> _GlobalRecurrenceLaunchBinding:
    authority = sealed._global_recurrence_child_authority(
        child_token,
        continuation_consumed=continuation_consumed,
        expected_pending_operation_bounds=expected_pending_operation_bounds,
    )
    pointer_values = authority.physical_pointer_values
    if (
        type(authority.kernel) is not HipRtcFgmresV2Kernel
        or authority.runtime is None
        or authority.stream is None
        or type(authority.direct_capabilities) is not tuple
        or len(authority.direct_capabilities) != len(_DIRECT_ROLES)
        or tuple(
            getattr(capability, "role", None)
            for capability in authority.direct_capabilities
        )
        != _DIRECT_ROLES
        or tuple(
            getattr(capability, "pointer_snapshot", None)
            for capability in authority.direct_capabilities
        )
        != tuple(pointer for _role, pointer in pointer_values[:11])
        or any(
            getattr(capability, "runtime_owner", None) is not authority.runtime
            or type(getattr(capability, "device_ordinal", None)) is not int
            or capability.device_ordinal != authority.device_ordinal
            or type(getattr(capability, "nbytes", None)) is not int
            or capability.nbytes <= 0
            or getattr(capability, "element_type", None) not in {"f64", "i32", "u8"}
            or type(getattr(capability, "generation", None)) is not int
            or capability.generation <= 0
            or _allocation_base_pointer(capability) != capability.pointer_snapshot
            or getattr(capability, "promotion_eligible", None) is not False
            for capability in authority.direct_capabilities
        )
        or tuple(role for role, _pointer in pointer_values) != _PHYSICAL_ROLES
        or len({pointer for _role, pointer in pointer_values}) != 16
        or any(pointer <= 0 for _role, pointer in pointer_values)
        or partition.plan.free_dof_count != authority.free_dof_count
        or partition.plan.restart_dimension != authority.restart_dimension
        or partition.plan.max_iterations != authority.max_iterations
        or partition.plan.maximum_restart_count != authority.maximum_restart_count
        or partition.continuation.launches == ()
        or type(authority.source_fgmres_plan) is not HipFgmresPlanV1
        or type(authority.source_recurrence_plan) is not HipFgmresRecurrencePlanV2
        or type(authority.source_execution_plan) is not ExecutionPlanV2
        or authority.source_fgmres_plan._source_execution_plan
        is not authority.source_execution_plan
    ):
        _fail(
            "hip_fgmres_global_recurrence_physical_projection_invalid",
            "/authority/physical16",
        )
    return _GlobalRecurrenceLaunchBinding(
        kernel=authority.kernel,
        checkpoint_owner_token=authority.checkpoint_owner_token,
        runtime=authority.runtime,
        loaded_runtime=authority.loaded_runtime,
        stream=authority.stream,
        stream_pointer=authority.stream_pointer,
        device_ordinal=authority.device_ordinal,
        architecture=authority.architecture,
        free_dof_count=authority.free_dof_count,
        reduced_csr_nnz=authority.reduced_csr_nnz,
        restart_dimension=authority.restart_dimension,
        max_iterations=authority.max_iterations,
        maximum_restart_count=authority.maximum_restart_count,
        stagnation_checkpoint_limit=authority.stagnation_checkpoint_limit,
        absolute_tolerance=authority.absolute_tolerance,
        relative_tolerance=authority.relative_tolerance,
        authoritative_tolerance=authority.authoritative_tolerance,
        stagnation_relative_tolerance=authority.stagnation_relative_tolerance,
        divergence_factor=authority.divergence_factor,
        source_fgmres_plan=authority.source_fgmres_plan,
        source_recurrence_plan=authority.source_recurrence_plan,
        source_execution_plan=authority.source_execution_plan,
        direct_capabilities=authority.direct_capabilities,
        direct_capability_snapshot=_direct_capabilities_snapshot(
            authority.direct_capabilities
        ),
        pointer_values=pointer_values,
        partition=partition,
        launches=partition.continuation.launches,
        launch_values=launch_values,
        kernel_binding_snapshot=authority.kernel_binding_snapshot,
    )


def _dispatch_snapshot(
    binding: _GlobalRecurrenceLaunchBinding,
) -> _GlobalRecurrenceDispatchSnapshot:
    return _GlobalRecurrenceDispatchSnapshot(
        binding.kernel,
        binding.checkpoint_owner_token,
        binding.stream_pointer,
        binding.free_dof_count,
        binding.reduced_csr_nnz,
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
    )


def _exact_value_snapshot(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return (
            type(value),
            tuple(_exact_value_snapshot(item) for item in value),
        )
    if type(value) is float:
        return (float, value.hex())
    return (type(value), value)


def _resource_values(binding: _GlobalRecurrenceLaunchBinding) -> tuple[Any, ...]:
    values = (
        id(binding.kernel),
        id(binding.checkpoint_owner_token),
        id(binding.runtime),
        id(binding.loaded_runtime),
        id(binding.stream),
        binding.stream_pointer,
        binding.device_ordinal,
        binding.architecture,
        binding.free_dof_count,
        binding.reduced_csr_nnz,
        binding.restart_dimension,
        binding.max_iterations,
        binding.maximum_restart_count,
        binding.stagnation_checkpoint_limit,
        binding.absolute_tolerance,
        binding.relative_tolerance,
        binding.authoritative_tolerance,
        binding.stagnation_relative_tolerance,
        binding.divergence_factor,
        id(binding.source_fgmres_plan),
        binding.source_fgmres_plan.plan_hash,
        id(binding.source_recurrence_plan),
        binding.source_recurrence_plan.plan_hash,
        id(binding.source_execution_plan),
        binding.source_execution_plan.plan_hash,
        tuple(id(capability) for capability in binding.direct_capabilities),
        binding.direct_capability_snapshot,
        binding.pointer_values,
        binding.partition.full.canonical_sha256,
        binding.partition.sealed_prefix.canonical_sha256,
        binding.partition.continuation.canonical_sha256,
        binding.kernel_binding_snapshot,
    )
    return tuple(_exact_value_snapshot(value) for value in values)


def _direct_capabilities_snapshot(
    capabilities: tuple[Any, ...],
) -> tuple[Any, ...]:
    return tuple(
        (
            type(capability),
            id(capability),
            type(getattr(capability, "allocation_id", None)),
            getattr(capability, "allocation_id", None),
            type(getattr(capability, "role", None)),
            getattr(capability, "role", None),
            type(getattr(capability, "pointer_snapshot", None)),
            getattr(capability, "pointer_snapshot", None),
            type(getattr(capability, "base", None)),
            id(getattr(capability, "base", None)),
            _allocation_base_pointer(capability),
            type(getattr(capability, "nbytes", None)),
            getattr(capability, "nbytes", None),
            type(getattr(capability, "element_type", None)),
            getattr(capability, "element_type", None),
            type(getattr(capability, "generation", None)),
            getattr(capability, "generation", None),
            id(getattr(capability, "owner_identity", None)),
            id(getattr(capability, "runtime_owner", None)),
            id(getattr(capability, "runtime_domain", None)),
            type(getattr(capability, "runtime_domain_id", None)),
            getattr(capability, "runtime_domain_id", None),
            type(getattr(capability, "device_ordinal", None)),
            getattr(capability, "device_ordinal", None),
            type(getattr(capability, "evidence_scope", None)),
            getattr(capability, "evidence_scope", None),
            type(getattr(capability, "promotion_eligible", None)),
            getattr(capability, "promotion_eligible", None),
        )
        for capability in capabilities
    )


def _completion_export_source_snapshot(
    binding: _GlobalRecurrenceLaunchBinding,
    sources: tuple[Any, ...],
) -> tuple[Any, ...]:
    factory = getattr(binding.runtime, "completion_export_copy_binding", None)
    if (
        not callable(factory)
        or getattr(factory, "__self__", None) is not binding.runtime
    ):
        _fail(
            "hip_fgmres_global_recurrence_completion_export_copy_binding_invalid",
            "/completion_export/authority/copy",
        )
    try:
        copy_binding = factory()
    except Exception as exc:
        raise HipFgmresGlobalRecurrenceV1Error(
            "hip_fgmres_global_recurrence_completion_export_copy_binding_invalid",
            "/completion_export/authority/copy",
            _detail(exc),
        ) from exc
    if not callable(copy_binding):
        _fail(
            "hip_fgmres_global_recurrence_completion_export_copy_binding_invalid",
            "/completion_export/authority/copy",
        )
    return (
        id(binding.runtime),
        id(binding.loaded_runtime),
        id(binding.stream),
        (type(binding.stream_pointer), binding.stream_pointer),
        (type(binding.device_ordinal), binding.device_ordinal),
        id(getattr(type(binding.runtime), "completion_export_copy_binding", None)),
        id(getattr(factory, "__func__", None)),
        type(copy_binding),
        id(copy_binding),
        id(getattr(type(copy_binding), "__call__", None)),
        id(getattr(copy_binding, "_memcpy", None)),
        id(getattr(copy_binding, "_loaded", None)),
        _completion_export_copy_operation_snapshot(copy_binding),
        id(getattr(binding.runtime, "_blocking_d2h_copy", None)),
        id(getattr(binding.runtime, "_memcpy", None)),
        id(getattr(binding.runtime, "_loaded", None)),
        _direct_capabilities_snapshot(sources),
    )


def _completion_export_copy_operation_snapshot(
    copy_binding: Any,
) -> tuple[Any, ...]:
    operation = getattr(copy_binding, "_memcpy", None)
    argtypes = getattr(operation, "argtypes", None)
    return (
        type(operation),
        id(operation),
        None
        if argtypes is None
        else tuple((type(argument), id(argument)) for argument in argtypes),
        type(getattr(operation, "restype", None)),
        id(getattr(operation, "restype", None)),
        type(getattr(operation, "errcheck", None)),
        id(getattr(operation, "errcheck", None)),
    )


def _allocation_base_pointer(capability: Any) -> int | None:
    base = getattr(capability, "base", None)
    if type(base) is int and base > 0:
        return base
    if type(base) is ctypes.c_void_p and type(base.value) is int and base.value > 0:
        return base.value
    return None


def _launch_value(
    launch: HipFgmresGlobalScheduleLaunchV1,
) -> tuple[tuple[str, Any], ...]:
    return tuple(asdict(launch).items())


def _launch_values(
    launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...],
) -> tuple[tuple[tuple[str, Any], ...], ...]:
    return tuple(_launch_value(row) for row in launches)


def _pending_snapshot_matches(
    snapshot: tuple[tuple[int, int], ...],
    *,
    stream_pointer: int,
    operation_bounds: tuple[int, int],
) -> bool:
    lower, upper = operation_bounds
    if type(lower) is not int or type(upper) is not int or not 0 <= lower <= upper:
        return False
    if not snapshot:
        return lower == 0
    if len(snapshot) != 1:
        return False
    pending_stream, operation_count = snapshot[0]
    return pending_stream == stream_pointer and lower <= operation_count <= upper


def validate_hip_fgmres_global_recurrence_receipt_v1(
    receipt: HipFgmresGlobalRecurrenceReceiptV1,
    *,
    expected_context: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None,
) -> HipFgmresGlobalRecurrenceReceiptV1:
    """Validate receipt hash, closed structure, semantics, and optional issuer."""

    if type(receipt) is not HipFgmresGlobalRecurrenceReceiptV1:
        _fail("hip_fgmres_global_recurrence_receipt_type_invalid", "/")
    _validate_receipt_object_types(receipt)
    payload = _receipt_payload(receipt, include_hash=False)
    if (
        type(receipt.receipt_hash) is not str
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != canonical_hash(payload)
    ):
        _fail(
            "hip_fgmres_global_recurrence_receipt_hash_invalid",
            "/receipt_hash",
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_global_recurrence_schema_invalid",
            path or "/",
            errors[0].message,
        )
    _validate_receipt_semantics(receipt)
    if expected_context is not None:
        if type(expected_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail("hip_fgmres_global_recurrence_context_invalid", "/")
        current = expected_context.receipt()
        if receipt.receipt_hash != current.receipt_hash:
            _fail("hip_fgmres_global_recurrence_context_mismatch", "/")
    return receipt


def _validate_receipt_object_types(receipt: HipFgmresGlobalRecurrenceReceiptV1) -> None:
    expected = (
        (receipt.bindings, HipFgmresGlobalRecurrenceBindingsV1),
        (receipt.dimensions, HipFgmresGlobalRecurrenceDimensionsV1),
        (receipt.projection, HipFgmresGlobalRecurrenceProjectionV1),
        (receipt.telemetry, HipFgmresGlobalRecurrenceTelemetryV1),
        (receipt.claims, HipFgmresGlobalRecurrenceClaimsV1),
    )
    if any(type(value) is not kind for value, kind in expected):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/")
    if (
        receipt.reason is not None
        and type(receipt.reason) is not HipFgmresGlobalRecurrenceReasonV1
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/reason")
    if (
        type(receipt.status) is not str
        or receipt.status not in _GLOBAL_RECURRENCE_STATUSES
        or type(receipt.context_id) is not str
        or type(receipt.evidence_scope) is not str
        or type(receipt.actual_backend) is not str
        or type(receipt.promotion_eligible) is not bool
        or type(receipt.receipt_hash) is not str
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/")
    if receipt.reason is not None and (
        type(receipt.reason.code) is not str
        or not receipt.reason.code
        or type(receipt.reason.detail) is not str
        or not receipt.reason.detail
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/reason")
    if any(
        type(getattr(receipt.dimensions, name)) is not int
        for name in receipt.dimensions.__dataclass_fields__
    ) or any(
        type(getattr(receipt.telemetry, name)) is not int
        for name in receipt.telemetry.__dataclass_fields__
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/claims")
    if (
        type(receipt.bindings.device_ordinal) is not int
        or type(receipt.bindings.architecture) is not str
        or not receipt.bindings.architecture
        or type(receipt.bindings.kernel_origin) is not str
        or receipt.bindings.kernel_origin
        not in {"internally_compiled", "caller_supplied"}
        or type(receipt.bindings.runtime_library_discovery_source) is not str
        or not receipt.bindings.runtime_library_discovery_source
        or type(receipt.bindings.hiprtc_library_discovery_source) is not str
        or not receipt.bindings.hiprtc_library_discovery_source
        or type(receipt.bindings.primitive_evidence_scope) is not str
        or not receipt.bindings.primitive_evidence_scope
        or type(receipt.bindings.primitive_actual_backend) is not str
        or receipt.bindings.primitive_actual_backend not in {"hip", "test_double"}
        or type(receipt.bindings.stream_identity_serialized) is not bool
        or type(receipt.bindings.checkpoint_token_identity_serialized) is not bool
        or type(receipt.projection.persistent_roles) is not tuple
        or type(receipt.projection.delegated_operator_roles) is not tuple
        or type(receipt.projection.delegated_workspace_roles) is not tuple
        or any(
            type(value) is not str
            for value in (
                *receipt.projection.persistent_roles,
                *receipt.projection.delegated_operator_roles,
                *receipt.projection.delegated_workspace_roles,
            )
        )
    ):
        _fail("hip_fgmres_global_recurrence_receipt_structure_invalid", "/")
    projection = receipt.projection
    if type(projection.pointer_values_serialized) is not bool or any(
        type(value) is not int
        for value in (
            projection.additional_allocation_count,
            projection.additional_device_bytes,
            projection.additional_borrow_count,
            projection.additional_checkpoint_owner_count,
            projection.additional_module_load_count,
        )
    ):
        _fail(
            "hip_fgmres_global_recurrence_receipt_structure_invalid",
            "/projection",
        )


def _validate_receipt_semantics(receipt: HipFgmresGlobalRecurrenceReceiptV1) -> None:
    dimensions = receipt.dimensions
    try:
        partition = compile_hip_fgmres_global_sealed_continuation_v1(
            dimensions.free_dof_count,
            dimensions.restart_dimension,
            dimensions.max_iterations,
        )
    except Exception as exc:
        _fail(
            "hip_fgmres_global_recurrence_dimensions_invalid",
            "/dimensions",
            _detail(exc),
        )
    if (
        dimensions.reduced_csr_nnz < dimensions.free_dof_count
        or dimensions.maximum_restart_count
        != (dimensions.max_iterations + dimensions.restart_dimension - 1)
        // dimensions.restart_dimension
        or dimensions.reduction_stage_count != partition.plan.reduction_stage_count
        or dimensions.sealed_prefix_launch_count != partition.sealed_prefix.launch_count
        or dimensions.continuation_launch_count != partition.continuation.launch_count
        or dimensions.full_program_launch_count != partition.full.launch_count
        or dimensions.full_program_launch_count
        != dimensions.sealed_prefix_launch_count + dimensions.continuation_launch_count
        or dimensions.persistent_capability_count != 11
        or dimensions.delegated_operator_capability_count != 3
        or dimensions.delegated_workspace_capability_count != 2
        or dimensions.physical_capability_count != 16
    ):
        _fail(
            "hip_fgmres_global_recurrence_dimensions_invalid",
            "/dimensions",
        )
    bindings = receipt.bindings
    hash_fields = (
        "sealed_checkpoint_context_id",
        "sealed_checkpoint_receipt_hash",
        "canonical_predecessor_context_id",
        "live_context_id",
        "recurrence_plan_hash",
        "recurrence_kernel_abi_hash",
        "combined_recurrence_abi_hash",
        "kernel_identity_hash",
        "kernel_source_sha256",
        "global_full_schedule_hash",
        "sealed_prefix_schedule_hash",
        "continuation_schedule_hash",
        "direct_generation_binding_hash",
        "physical_projection_hash",
    )
    if any(
        type(getattr(bindings, name)) is not str
        or _HASH_RE.fullmatch(getattr(bindings, name)) is None
        for name in hash_fields
    ):
        _fail("hip_fgmres_global_recurrence_binding_invalid", "/bindings")
    if (
        bindings.global_full_schedule_hash != partition.full.canonical_sha256
        or bindings.sealed_prefix_schedule_hash
        != partition.sealed_prefix.canonical_sha256
        or bindings.continuation_schedule_hash
        != partition.continuation.canonical_sha256
        or bindings.device_ordinal < 0
        or not bindings.architecture
        or bindings.stream_identity_serialized
        or bindings.checkpoint_token_identity_serialized
    ):
        _fail("hip_fgmres_global_recurrence_binding_invalid", "/bindings")
    expected_recurrence_kernel_abi_hash = canonical_hash(
        hip_fgmres_recurrence_kernel_abi_payload_v2()
    )
    if (
        bindings.recurrence_kernel_abi_hash != expected_recurrence_kernel_abi_hash
        or bindings.combined_recurrence_abi_hash
        != HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
        or bindings.kernel_source_sha256 != HIP_FGMRES_RTC_SOURCE_SHA256_V2
    ):
        _fail(
            "hip_fgmres_global_recurrence_abi_identity_invalid",
            "/bindings/recurrence_kernel_abi_hash",
        )
    expected_context_id = canonical_hash(
        {
            "profile": HIP_FGMRES_GLOBAL_RECURRENCE_CAPABILITY_PROFILE_V1,
            "sealed_checkpoint_context_id": bindings.sealed_checkpoint_context_id,
            "sealed_checkpoint_receipt_hash": bindings.sealed_checkpoint_receipt_hash,
            "continuation_schedule_hash": bindings.continuation_schedule_hash,
            "direct_generation_binding_hash": bindings.direct_generation_binding_hash,
            "physical_projection_hash": bindings.physical_projection_hash,
        }
    )
    if receipt.context_id != expected_context_id:
        _fail("hip_fgmres_global_recurrence_context_id_invalid", "/context_id")
    if (
        receipt.evidence_scope != HIP_FGMRES_GLOBAL_RECURRENCE_EVIDENCE_SCOPE_V1
        or receipt.actual_backend not in {"hip", "test_double"}
        or receipt.promotion_eligible
        or receipt.projection.persistent_roles != _DIRECT_ROLES
        or receipt.projection.delegated_operator_roles != _DELEGATED_OPERATOR_ROLES
        or receipt.projection.delegated_workspace_roles != _DELEGATED_WORKSPACE_ROLES
        or receipt.projection.pointer_values_serialized
        or any(
            (
                receipt.projection.additional_allocation_count,
                receipt.projection.additional_device_bytes,
                receipt.projection.additional_borrow_count,
                receipt.projection.additional_checkpoint_owner_count,
                receipt.projection.additional_module_load_count,
            )
        )
    ):
        _fail("hip_fgmres_global_recurrence_projection_invalid", "/projection")
    native_parent = (
        bindings.primitive_evidence_scope == "native_hiprtc_krylov_primitives_composite"
        and bindings.primitive_actual_backend == "hip"
    )
    native_kernel = (
        bindings.kernel_origin == "internally_compiled"
        and bindings.runtime_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
        and bindings.hiprtc_library_discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
    )
    expected_backend = "hip" if native_parent and native_kernel else "test_double"
    if receipt.actual_backend != expected_backend:
        _fail("hip_fgmres_global_recurrence_backend_invalid", "/actual_backend")
    forbidden = (
        receipt.claims.actual_terminal_outcome_host_observed,
        receipt.claims.authoritative_terminal_status_proven,
        receipt.claims.numerical_parity_verified,
        receipt.claims.solution_ready,
        receipt.claims.performance_or_speedup_proven,
        receipt.claims.commercial_ready,
        receipt.claims.promotion_eligible,
    )
    if any(forbidden):
        _fail("hip_fgmres_global_recurrence_claim_invalid", "/claims")
    telemetry = receipt.telemetry
    launch_count = dimensions.continuation_launch_count
    zero_telemetry = (
        telemetry.allocation_count,
        telemetry.allocation_borrow_count,
        telemetry.checkpoint_owner_acquire_count,
        telemetry.module_load_count,
        telemetry.module_unload_count,
        telemetry.h2d_operation_count,
        telemetry.d2h_operation_count,
        telemetry.intermediate_sync_count,
        telemetry.fallback_count,
        telemetry.live_state_host_read_count,
        telemetry.live_state_host_branch_count,
    )
    if (
        telemetry.continuation_capability_reservation_count != 1
        or telemetry.continuation_capability_consume_count not in {0, 1}
        or not 0
        <= telemetry.kernel_launch_accept_lower_bound
        <= telemetry.kernel_launch_accept_upper_bound
        <= telemetry.kernel_launch_attempt_count
        <= launch_count
        or telemetry.fence_success_count > telemetry.fence_attempt_count
        or telemetry.fence_success_count > 1
        or telemetry.consumed_launch_count > telemetry.kernel_launch_accept_upper_bound
        or (
            telemetry.pending_consume_attempt_count > 0
            and telemetry.fence_success_count != 1
        )
        or any(zero_telemetry)
    ):
        _fail("hip_fgmres_global_recurrence_telemetry_invalid", "/telemetry")
    bound = receipt.status not in {"cleanup_failed", "context_closed"}
    bound_claims = (
        receipt.claims.sealed_checkpoint_parent_bound,
        receipt.claims.continuation_capability_reserved,
        receipt.claims.direct11_csr3_scratch2_physical16_bound,
        receipt.claims.same_kernel_runtime_device_stream_checkpoint_bound,
        receipt.claims.canonical_continuation_suffix_bound,
        receipt.claims.one_pending_stream_map_bound,
        receipt.claims.no_additional_allocation_or_borrow,
        receipt.claims.no_h2d_or_d2h_copy,
        receipt.claims.no_intermediate_synchronization,
        receipt.claims.no_live_state_host_read_or_branch,
    )
    if any(value is not bound for value in bound_claims):
        _fail("hip_fgmres_global_recurrence_claim_invalid", "/claims")
    consumed = telemetry.continuation_capability_consume_count == 1
    if receipt.claims.continuation_capability_consumed is not consumed:
        _fail(
            "hip_fgmres_global_recurrence_claim_invalid",
            "/claims/continuation_capability_consumed",
        )
    if receipt.status == "context_ready" and (
        consumed
        or telemetry.kernel_launch_attempt_count != 0
        or telemetry.fence_attempt_count != 0
        or telemetry.pending_consume_attempt_count != 0
        or telemetry.consumed_launch_count != 0
        or receipt.reason is not None
    ):
        _fail("hip_fgmres_global_recurrence_telemetry_invalid", "/telemetry")
    if receipt.status in {"pending_publication_pending", "recurrence_pending"} and (
        not consumed
        or telemetry.kernel_launch_attempt_count != launch_count
        or telemetry.kernel_launch_accept_lower_bound != launch_count
        or telemetry.kernel_launch_accept_upper_bound != launch_count
        or telemetry.fence_success_count != 0
        or telemetry.pending_consume_attempt_count != 0
        or telemetry.consumed_launch_count != 0
        or receipt.reason is not None
    ):
        _fail("hip_fgmres_global_recurrence_telemetry_invalid", "/telemetry")
    if receipt.status in {
        "fence_observed_ack_pending",
        "poisoned_fence_observed_ack_pending",
    } and (
        telemetry.fence_success_count != 1
        or telemetry.pending_consume_attempt_count < 1
        or telemetry.consumed_launch_count != 0
    ):
        _fail("hip_fgmres_global_recurrence_telemetry_invalid", "/telemetry")
    if receipt.status == "poisoned_no_work" and (
        telemetry.kernel_launch_accept_upper_bound != 0
        or telemetry.fence_success_count != 0
        or telemetry.consumed_launch_count != 0
    ):
        _fail("hip_fgmres_global_recurrence_telemetry_invalid", "/telemetry")
    if receipt.status.startswith("poisoned_") and receipt.reason is None:
        _fail("hip_fgmres_global_recurrence_reason_invalid", "/reason")
    if (
        receipt.status
        in {
            "context_ready",
            "pending_publication_pending",
            "recurrence_pending",
            "completion_publication_pending",
            "recurrence_fenced",
        }
        and receipt.reason is not None
    ):
        _fail("hip_fgmres_global_recurrence_reason_invalid", "/reason")
    fenced = receipt.claims.fixed_suffix_fenced
    completion_issued = receipt.claims.completion_capability_issued
    if completion_issued and not fenced:
        _fail("hip_fgmres_global_recurrence_claim_invalid", "/claims")
    if fenced and (
        receipt.status
        not in {
            "completion_publication_pending",
            "recurrence_fenced",
            "context_closed",
        }
        or not consumed
        or telemetry.kernel_launch_attempt_count != launch_count
        or telemetry.kernel_launch_accept_lower_bound != launch_count
        or telemetry.kernel_launch_accept_upper_bound != launch_count
        or telemetry.fence_success_count != 1
        or telemetry.consumed_launch_count != launch_count
    ):
        _fail(
            "hip_fgmres_global_recurrence_claim_invalid", "/claims/fixed_suffix_fenced"
        )
    if receipt.status == "completion_publication_pending" and (
        not fenced or completion_issued
    ):
        _fail(
            "hip_fgmres_global_recurrence_claim_invalid",
            "/claims/completion_capability_issued",
        )
    if receipt.status == "recurrence_fenced" and (not fenced or not completion_issued):
        _fail(
            "hip_fgmres_global_recurrence_claim_invalid", "/claims/fixed_suffix_fenced"
        )


def validate_hip_fgmres_global_recurrence_completion_capability_v1(
    capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    *,
    expected_context: HipFgmresGlobalRecurrenceExecutionContextV1,
) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
    """Validate a still-live fenced-program capability from its exact issuer."""

    if type(expected_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
        _fail("hip_fgmres_global_recurrence_completion_context_invalid", "/")
    with expected_context._lock:
        if (
            type(capability) is not HipFgmresGlobalRecurrenceCompletionCapabilityV1
            or capability._issuer is not expected_context
            or capability._nonce is not expected_context._completion_nonce
            or capability._snapshot != _completion_snapshot(capability)
            or capability is not expected_context._completion
            or capability.context_id != expected_context._context_id
            or expected_context._state != "recurrence_fenced"
            or expected_context.closed
        ):
            _fail(
                "hip_fgmres_global_recurrence_completion_capability_invalid",
                "/capability",
            )
        receipt = expected_context.receipt()
        if (
            capability.receipt_hash != receipt.receipt_hash
            or capability.continuation_schedule_hash
            != receipt.bindings.continuation_schedule_hash
            or capability.fenced_launch_count
            != receipt.dimensions.continuation_launch_count
        ):
            _fail(
                "hip_fgmres_global_recurrence_completion_capability_invalid",
                "/capability/receipt_hash",
            )
        return capability


def _receipt_payload(
    receipt: HipFgmresGlobalRecurrenceReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_GLOBAL_RECURRENCE_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_GLOBAL_RECURRENCE_CAPABILITY_PROFILE_V1,
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
    pending: HipFgmresGlobalRecurrencePendingV1,
) -> tuple[Any, ...]:
    return (
        pending.context_id,
        pending.attempted_launch_count,
        pending.accepted_launch_count_lower_bound,
        pending.accepted_launch_count_upper_bound,
        id(pending._issuer),
        id(pending._nonce),
    )


def _completion_snapshot(
    capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
) -> tuple[Any, ...]:
    return (
        capability.context_id,
        capability.receipt_hash,
        capability.continuation_schedule_hash,
        capability.fenced_launch_count,
        id(capability._issuer),
        id(capability._nonce),
    )


def _issue_capability(type_: type[Any], fields: dict[str, Any]) -> Any:
    value = object.__new__(type_)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


def _mint_completion_export_child_lease_v1() -> _CompletionExportChildLeaseV1:
    """Mint one nonconstructible-by-convention downstream lease token."""

    return _CompletionExportChildLeaseV1()


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
    cleanup_owner: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresGlobalRecurrenceV1Error(
        code,
        path,
        message or code,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_GLOBAL_RECURRENCE_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_GLOBAL_RECURRENCE_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_GLOBAL_RECURRENCE_SCHEMA_VERSION_V1",
    "HipFgmresGlobalRecurrenceBindingsV1",
    "HipFgmresGlobalRecurrenceClaimsV1",
    "HipFgmresGlobalRecurrenceCompletionCapabilityV1",
    "HipFgmresGlobalRecurrenceDimensionsV1",
    "HipFgmresGlobalRecurrenceExecutionContextV1",
    "HipFgmresGlobalRecurrenceOpenResultV1",
    "HipFgmresGlobalRecurrencePendingV1",
    "HipFgmresGlobalRecurrenceProjectionV1",
    "HipFgmresGlobalRecurrenceReasonV1",
    "HipFgmresGlobalRecurrenceReceiptV1",
    "HipFgmresGlobalRecurrenceTelemetryV1",
    "HipFgmresGlobalRecurrenceV1Error",
    "open_hip_fgmres_global_recurrence_context_v1",
    "validate_hip_fgmres_global_recurrence_completion_capability_v1",
    "validate_hip_fgmres_global_recurrence_receipt_v1",
]
