"""Allocation-lineage owner for the HIP FGMRES fixed-rank coarse overlay.

This is the first live resource slice for the fixed-rank coarse
preconditioner.  It delegates the exact live FGMRES ``jacobi_inverse``,
``basis_v``, and ``preconditioned_basis_z`` capabilities, allocates six
coarse-owned buffers through a peer allocation-lineage owner, enqueues the
three immutable coarse arrays once on the parent stream, and owns the exact
four-symbol HIPRTC module through fence and cleanup.

The context deliberately does not replace ``APPLY_JACOBI_INDEXED`` in the
canonical recurrence state machine.  Its receipts therefore remain
process-local, non-promoting resource/application evidence.
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import re
import threading
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.hip.context import (
    HipFreeKnownNotFreedError,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_fixed_rank_coarse_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE,
    HipFgmresFixedRankCoarseBufferPlanV1,
    HipFgmresFixedRankCoarsePlanV1,
    validate_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from .fgmres_fixed_rank_coarse_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseKernelIdentityV1,
    HipRtcFgmresFixedRankCoarseKernelV1,
    HipRtcFgmresFixedRankCoarseV1Error,
    _compile_fixed_rank_coarse_with_handoff_v1,
    _HipRtcFgmresFixedRankCoarseKernelHandoffV1,
    compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1,
    validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1,
)
from .fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointExecutionContextV1,
    _HipFgmresFixedRankCoarseParentAuthorityV1,
)
from .hip_allocation_lineage import (
    HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
    HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
    HipAllocationCapabilityV1,
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
    open_hip_allocation_peer_owner_v1,
    reserve_hip_allocation_owner_control_v1,
    snapshot_hip_allocation_owner_cleanup_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_capability_v1,
    validate_hip_allocation_owner_control_v1,
    validate_hip_allocation_owner_v1,
)


HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-context.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_RECEIPT_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-application.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_CAPABILITY_PROFILE = (
    "phase0_live_hip_fgmres_fixed_rank_coarse_resource_owner"
)
HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_EVIDENCE_SCOPE = (
    "allocation_lineage_live_parent_delegation_non_promoting"
)

CoarseContextStatusV1 = Literal[
    "context_ready",
    "poisoned",
    "context_closed",
    "cleanup_failed",
    "cleanup_quarantined",
    "unavailable",
]
KernelOriginV1 = Literal["internally_compiled", "caller_supplied"]

_PARENT_ROLES = ("jacobi_inverse", "basis_v", "preconditioned_basis_z")
_OWNED_ROLES = (
    "coarse_physical_basis_z",
    "coarse_operator_basis_az",
    "coarse_cholesky_l",
    "coarse_rhs",
    "coarse_coefficients",
    "coarse_status",
)
_STATIC_UPLOAD_ROLES = (
    "coarse_physical_basis_z",
    "coarse_operator_basis_az",
    "coarse_cholesky_l",
)
_OWNER_ROLE = "fgmres_fixed_rank_coarse_owned_buffers"
_CONTEXT_SCHEMA_RESOURCE = "hip_fgmres_fixed_rank_coarse_context_v1.schema.json"
_APPLICATION_SCHEMA_RESOURCE = "hip_fgmres_fixed_rank_coarse_application_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTEXT_MINT = object()


class HipFgmresFixedRankCoarseContextV1Error(RuntimeError):
    """Stable fail-closed context error with retryable cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresFixedRankCoarseExecutionContextV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseBindingsV1:
    live_checkpoint_context_id: str
    live_checkpoint_opening_receipt_hash: str
    source_fgmres_plan_hash: str
    recurrence_plan_hash: str
    coarse_plan_hash: str
    coarse_space_hash: str
    coarse_memory_layout_hash: str
    kernel_abi_hash: str
    parent_child_epoch: int
    parent_generation_binding_hash: str
    owned_generation_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    retained_rank: int
    parent_capability_count: Literal[3] = 3
    owned_capability_count: Literal[6] = 6
    static_upload_count: Literal[3] = 3
    launches_per_application: Literal[4] = 4

    def to_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in asdict(self).items()}


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseBufferV1:
    name: str
    dtype: str
    shape: tuple[int, ...]
    element_count: int
    byte_length: int
    access: str
    initialization: str
    layout: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "element_count": self.element_count,
            "byte_length": self.byte_length,
            "memory_space": "hip_device",
            "ownership": "owned",
            "access": self.access,
            "initialization": self.initialization,
            "layout": self.layout,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseKernelV1:
    architecture: str
    identity_hash: str
    source_sha256: str
    code_object_sha256: str
    kernel_abi_hash: str
    runtime_library_sha256: str
    runtime_library_discovery_source: str
    hiprtc_library_sha256: str
    hiprtc_library_discovery_source: str
    kernel_origin: KernelOriginV1

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseLineageV1:
    capability_profile: Literal["foundation_non_promoting"]
    evidence_scope: Literal["foundation_non_promoting"]
    owner_role: Literal["fgmres_fixed_rank_coarse_owned_buffers"]
    runtime_device_bound: bool
    same_stream_bound: bool
    delegated_parent_capability_count: int
    managed_buffer_count: int
    managed_device_bytes: int
    all_owned_buffers_managed: bool
    duplicate_registry_borrow_count: Literal[0] = 0
    pointer_values_serialized: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseTelemetryV1:
    allocation_attempt_count: int = 0
    allocation_success_count: int = 0
    deallocation_attempt_count: int = 0
    deallocation_success_count: int = 0
    current_device_bytes: int = 0
    peak_device_bytes: int = 0
    quarantined_device_bytes: int = 0
    lineage_owner_open_success_count: int = 0
    lineage_owner_close_success_count: int = 0
    lineage_capability_mint_success_count: int = 0
    lineage_capability_mint_bytes: int = 0
    lineage_free_acknowledgement_count: int = 0
    lineage_free_quarantine_count: int = 0
    lineage_orphan_acknowledgement_count: int = 0
    lineage_orphan_quarantine_count: int = 0
    parent_delegation_acquire_success_count: int = 0
    parent_delegation_release_success_count: int = 0
    module_owner_acquire_success_count: int = 0
    module_close_attempt_count: int = 0
    module_close_success_count: int = 0
    h2d_operation_attempt_count: int = 0
    h2d_operation_success_count: int = 0
    h2d_bytes_attempted: int = 0
    h2d_bytes_succeeded: int = 0
    application_attempt_count: int = 0
    application_success_count: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_success_count: int = 0
    fence_attempt_count: int = 0
    fence_success_count: int = 0
    fence_acknowledged_launch_count: int = 0
    d2h_operation_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in asdict(self).items()}


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseClaimsV1:
    exact_live_parent_delegated: bool
    allocator_provenance_bound: bool
    static_uploads_enqueued_once: bool
    same_stream_application_ready: bool
    application_host_copy_zero_by_construction: bool
    actual_device_application_observed: Literal[False] = False
    recurrence_state_machine_integrated: Literal[False] = False
    device_status_terminal_bound: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    asymptotic_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseContextReceiptV1:
    status: CoarseContextStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"] | None
    promotion_eligible: Literal[False]
    reason: HipFgmresFixedRankCoarseReasonV1 | None
    bindings: HipFgmresFixedRankCoarseBindingsV1
    kernel: HipFgmresFixedRankCoarseKernelV1
    dimensions: HipFgmresFixedRankCoarseDimensionsV1
    owned_buffers: tuple[HipFgmresFixedRankCoarseBufferV1, ...]
    allocation_lineage: HipFgmresFixedRankCoarseLineageV1
    telemetry: HipFgmresFixedRankCoarseTelemetryV1
    claims: HipFgmresFixedRankCoarseClaimsV1
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(self)
        return _context_receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseApplicationReceiptV1:
    context_id: str
    sequence: int
    logical_index: int
    accepted_launch_count: Literal[4]
    application_h2d_copy_count: Literal[0]
    application_d2h_copy_count: Literal[0]
    application_allocation_count: Literal[0]
    application_synchronization_count: Literal[0]
    application_csr_apply_count: Literal[0]
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_RECEIPT_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(self)
        return _application_receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseContextOpenResultV1:
    context: HipFgmresFixedRankCoarseExecutionContextV1 | None
    receipt: HipFgmresFixedRankCoarseContextReceiptV1 | None
    reason: HipFgmresFixedRankCoarseReasonV1 | None = None

    @property
    def ready(self) -> bool:
        return (
            self.context is not None
            and self.receipt is not None
            and self.receipt.status == "context_ready"
        )


@dataclass(slots=True)
class _OrphanCleanupV1:
    lease: HipAllocationOrphanLeaseV1
    byte_length: int
    must_quarantine: bool
    disposition: str = "live"


class HipFgmresFixedRankCoarseExecutionContextV1:
    """Exclusive owner of one live fixed-rank coarse resource overlay."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Fixed-rank coarse contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._operation_active = False
        self._parent: HipFgmresLiveCheckpointExecutionContextV1 | None = None
        self._token = object()
        self._parent_authority: _HipFgmresFixedRankCoarseParentAuthorityV1 | None = None
        self._plan: HipFgmresFixedRankCoarsePlanV1 | None = None
        self._runtime: object | None = None
        self._loaded_runtime: object | None = None
        self._stream: object | None = None
        self._stream_pointer_snapshot: int | None = None
        self._device_ordinal: int | None = None
        self._architecture: str | None = None
        self._actual_backend: Literal["hip", "test_double"] | None = None
        self._allocation_owner: HipAllocationOwnerV1 | None = None
        self._owned_capabilities: dict[str, HipAllocationCapabilityV1] = {}
        self._pending_free_leases: dict[str, HipAllocationFreeLeaseV1] = {}
        self._cleanup_dispositions: dict[str, str] = {}
        self._orphan_cleanups: list[_OrphanCleanupV1] = []
        self._kernel: HipRtcFgmresFixedRankCoarseKernelV1 | None = None
        self._kernel_identity_snapshot: (
            HipRtcFgmresFixedRankCoarseKernelIdentityV1 | None
        ) = None
        self._kernel_origin: KernelOriginV1 | None = None
        self._kernel_summary: HipFgmresFixedRankCoarseKernelV1 | None = None
        self._owned_buffers: tuple[HipFgmresFixedRankCoarseBufferV1, ...] = ()
        self._bindings: HipFgmresFixedRankCoarseBindingsV1 | None = None
        self._dimensions: HipFgmresFixedRankCoarseDimensionsV1 | None = None
        self._context_id = _ZERO_HASH
        self._telemetry = HipFgmresFixedRankCoarseTelemetryV1()
        self._opening_receipt: HipFgmresFixedRankCoarseContextReceiptV1 | None = None
        self._failure_reason: HipFgmresFixedRankCoarseReasonV1 | None = None
        self._sequence = 0
        self._stream_work_requires_fence = False
        self._poisoned = False
        self._cleanup_failed = False
        self._cleanup_quarantined = False
        self._kernel_terminal = False
        self._parent_reserved = False
        self._parent_released = False
        self._recurrence_overlay_child_token: object | None = None
        self._recurrence_overlay_child_context: object | None = None
        self._recurrence_overlay_child_terminal = False
        self._owner_closed = False
        self._closed = False

    @property
    def opening_receipt(self) -> HipFgmresFixedRankCoarseContextReceiptV1:
        if self._opening_receipt is None:
            _fail("hip_fgmres_coarse_context_receipt_unavailable", "/receipt")
        return self._opening_receipt

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def receipt(self) -> HipFgmresFixedRankCoarseContextReceiptV1:
        with self._lock:
            if self._cleanup_quarantined:
                status: CoarseContextStatusV1 = "cleanup_quarantined"
            elif self._cleanup_failed:
                status = "cleanup_failed"
            elif self._closed:
                status = "context_closed"
            elif self._poisoned:
                status = "poisoned"
            else:
                status = "context_ready"
            return self._build_receipt(status)

    def enqueue_application(
        self, logical_index: int
    ) -> HipFgmresFixedRankCoarseApplicationReceiptV1:
        with self._serialized_operation("/application"):
            if self._recurrence_overlay_child_token is not None:
                _fail(
                    "hip_fgmres_coarse_context_recurrence_overlay_active",
                    "/application/recurrence_overlay",
                    cleanup_owner=self,
                )
            return self._enqueue_application_locked(logical_index)

    def _enqueue_recurrence_overlay_application(
        self,
        token: object,
        child_context: object,
        logical_index: int,
    ) -> HipFgmresFixedRankCoarseApplicationReceiptV1:
        """Submit one overlay application for the exact reserved child."""

        with self._serialized_operation("/recurrence_overlay/application"):
            self._require_recurrence_overlay_child(token, child_context)
            return self._enqueue_application_locked(logical_index)

    def _enqueue_application_locked(
        self,
        logical_index: int,
    ) -> HipFgmresFixedRankCoarseApplicationReceiptV1:
        if type(logical_index) is not int:
            _fail(
                "hip_fgmres_coarse_context_logical_index_invalid",
                "/application/logical_index",
                cleanup_owner=self,
            )
        dimensions = self._require_dimensions()
        if not 0 <= logical_index < dimensions.restart_dimension:
            _fail(
                "hip_fgmres_coarse_context_logical_index_invalid",
                "/application/logical_index",
                cleanup_owner=self,
            )
        if self._poisoned or self._closed:
            _fail(
                "hip_fgmres_coarse_context_unavailable",
                "/application",
                cleanup_owner=self,
            )
        authority = self._validate_authority()
        kernel = self._require_kernel()
        before_attempted = kernel.lifetime_attempted_launch_count
        before_accepted = kernel.lifetime_accepted_launch_count
        self._telemetry = replace(
            self._telemetry,
            application_attempt_count=self._telemetry.application_attempt_count + 1,
        )
        self._stream_work_requires_fence = True
        try:
            accepted = kernel.launch_application(
                stream=self._stream_pointer_snapshot,
                free_dof_count=dimensions.free_dof_count,
                retained_rank=dimensions.retained_rank,
                restart_dimension=dimensions.restart_dimension,
                logical_index=logical_index,
                **self._pointer_arguments(authority),
            )
        except BaseException as exc:
            attempted_delta = max(
                0, kernel.lifetime_attempted_launch_count - before_attempted
            )
            accepted_delta = max(
                0, kernel.lifetime_accepted_launch_count - before_accepted
            )
            self._telemetry = replace(
                self._telemetry,
                kernel_launch_attempt_count=(
                    self._telemetry.kernel_launch_attempt_count + attempted_delta
                ),
                kernel_launch_success_count=(
                    self._telemetry.kernel_launch_success_count + accepted_delta
                ),
            )
            if attempted_delta or kernel.pending:
                self._poison("hip_fgmres_coarse_context_launch_outcome_uncertain")
            raise HipFgmresFixedRankCoarseContextV1Error(
                "hip_fgmres_coarse_context_application_failed",
                "/application/launch",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        attempted_delta = kernel.lifetime_attempted_launch_count - before_attempted
        accepted_delta = kernel.lifetime_accepted_launch_count - before_accepted
        if accepted != 4 or attempted_delta != 4 or accepted_delta != 4:
            self._poison("hip_fgmres_coarse_context_launch_accounting_invalid")
            _fail(
                "hip_fgmres_coarse_context_launch_accounting_invalid",
                "/application/launch",
                cleanup_owner=self,
            )
        self._telemetry = replace(
            self._telemetry,
            application_success_count=self._telemetry.application_success_count + 1,
            kernel_launch_attempt_count=(
                self._telemetry.kernel_launch_attempt_count + attempted_delta
            ),
            kernel_launch_success_count=(
                self._telemetry.kernel_launch_success_count + accepted_delta
            ),
        )
        self._sequence += 1
        draft = HipFgmresFixedRankCoarseApplicationReceiptV1(
            context_id=self._context_id,
            sequence=self._sequence,
            logical_index=logical_index,
            accepted_launch_count=4,
            application_h2d_copy_count=0,
            application_d2h_copy_count=0,
            application_allocation_count=0,
            application_synchronization_count=0,
            application_csr_apply_count=0,
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(
                _application_receipt_payload(draft, include_hash=False)
            ),
        )
        return validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
            receipt,
            expected_context=self,
        )

    def fence(self) -> int:
        with self._serialized_operation("/fence"):
            return self._fence_locked()

    def close(self) -> None:
        with self._serialized_operation("/cleanup"):
            if self._closed:
                return
            if self._recurrence_overlay_child_token is not None:
                _fail(
                    "hip_fgmres_coarse_context_recurrence_overlay_child_active",
                    "/cleanup/recurrence_overlay",
                    cleanup_owner=self,
                )
            self._recover_parent_reservation_locked()
            self._recover_allocation_cleanup_snapshot_locked(opening=False)
            if self._stream_work_requires_fence or (
                self._kernel is not None and self._kernel.pending
            ):
                self._fence_locked()
            self._close_kernel_locked()
            errors: list[BaseException] = []
            for name in reversed(_OWNED_ROLES):
                error = self._retire_owned_locked(name)
                if error is not None:
                    errors.append(error)
            for cleanup in tuple(self._orphan_cleanups):
                error = self._retire_orphan_locked(cleanup)
                if error is not None:
                    errors.append(error)
            if errors:
                self._cleanup_failed = True
                self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
                    "hip_fgmres_coarse_context_cleanup_failed",
                    "; ".join(_detail(error) for error in errors),
                )
                raise HipFgmresFixedRankCoarseContextV1Error(
                    self._failure_reason.code,
                    "/cleanup/allocations",
                    self._failure_reason.detail,
                    cleanup_owner=self,
                ) from errors[0]
            if not self._owner_closed and self._allocation_owner is not None:
                try:
                    self._allocation_owner.close(_control_token=self._token)
                except BaseException as exc:
                    try:
                        owner_closed = self._allocation_owner.closed
                    except BaseException:
                        owner_closed = False
                    if not owner_closed:
                        self._cleanup_failed = True
                        self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
                            "hip_fgmres_coarse_context_owner_close_failed",
                            _detail(exc),
                        )
                        raise HipFgmresFixedRankCoarseContextV1Error(
                            self._failure_reason.code,
                            "/cleanup/allocation_owner",
                            self._failure_reason.detail,
                            cleanup_owner=self,
                        ) from exc
                    self._owner_closed = True
                    self._telemetry = replace(
                        self._telemetry,
                        lineage_owner_close_success_count=1,
                    )
                    if not isinstance(exc, Exception):
                        raise
                else:
                    self._owner_closed = True
                    self._telemetry = replace(
                        self._telemetry,
                        lineage_owner_close_success_count=1,
                    )
            # The parent owns the stream/runtime backing this peer owner.  Keep
            # its semantic child lease until every coarse allocation and the
            # coarse owner itself are terminal, otherwise a concurrent parent
            # close could invalidate cleanup authority mid-flight.
            self._release_parent_locked()
            self._closed = True
            self._cleanup_failed = False

    def _reserve_recurrence_overlay_child(
        self,
        token: object,
        child_context: object,
    ) -> object:
        if type(token) is not object or child_context is None:
            _fail(
                "hip_fgmres_coarse_context_recurrence_overlay_token_invalid",
                "/recurrence_overlay/lifetime",
                cleanup_owner=self,
            )
        with self._lock:
            if (
                self._closed
                or self._poisoned
                or self._recurrence_overlay_child_terminal
                or self._recurrence_overlay_child_token is not None
            ):
                _fail(
                    "hip_fgmres_coarse_context_recurrence_overlay_unavailable",
                    "/recurrence_overlay/lifetime",
                    cleanup_owner=self,
                )
            self._validate_authority()
            self._recurrence_overlay_child_token = token
            self._recurrence_overlay_child_context = child_context
            return token

    def _require_recurrence_overlay_child(
        self,
        token: object,
        child_context: object,
    ) -> None:
        if (
            token is not self._recurrence_overlay_child_token
            or child_context is not self._recurrence_overlay_child_context
            or self._closed
        ):
            _fail(
                "hip_fgmres_coarse_context_recurrence_overlay_token_invalid",
                "/recurrence_overlay/lifetime",
                cleanup_owner=self,
            )

    def _acknowledge_recurrence_overlay_fence(
        self,
        token: object,
        child_context: object,
    ) -> int:
        """Consume coarse pending work after an exact same-stream parent fence."""

        with self._serialized_operation("/recurrence_overlay/fence"):
            self._require_recurrence_overlay_child(token, child_context)
            self._validate_authority()
            kernel = self._require_kernel()
            pending_before = kernel.pending_accepted_launch_count
            try:
                acknowledged = kernel.acknowledge_stream_fence(
                    self._stream_pointer_snapshot
                )
            except BaseException as exc:
                if kernel.pending:
                    self._poison(
                        "hip_fgmres_coarse_context_recurrence_overlay_fence_ack_failed"
                    )
                    raise HipFgmresFixedRankCoarseContextV1Error(
                        "hip_fgmres_coarse_context_recurrence_overlay_fence_ack_failed",
                        "/recurrence_overlay/fence",
                        _detail(exc),
                        cleanup_owner=self,
                    ) from exc
                acknowledged = pending_before
            self._stream_work_requires_fence = False
            self._telemetry = replace(
                self._telemetry,
                fence_acknowledged_launch_count=(
                    self._telemetry.fence_acknowledged_launch_count + acknowledged
                ),
            )
            return acknowledged

    def _release_recurrence_overlay_child(
        self,
        token: object,
        child_context: object,
    ) -> None:
        with self._lock:
            self._require_recurrence_overlay_child(token, child_context)
            kernel = self._require_kernel()
            if kernel.pending or self._stream_work_requires_fence:
                _fail(
                    "hip_fgmres_coarse_context_recurrence_overlay_fence_required",
                    "/recurrence_overlay/lifetime",
                    cleanup_owner=self,
                )
            self._recurrence_overlay_child_terminal = True
            self._recurrence_overlay_child_token = None
            self._recurrence_overlay_child_context = None

    def _serialized_operation(self, path: str) -> _SerializedContextOperation:
        return _SerializedContextOperation(self, path)

    def _recover_parent_reservation_locked(self) -> None:
        parent = self._parent
        if parent is None or self._closed:
            return
        active = parent._fixed_rank_coarse_child_token_is_active(self._token, self)
        if active:
            self._parent_reserved = True
            self._parent_released = False
            self._telemetry = replace(
                self._telemetry,
                parent_delegation_acquire_success_count=1,
            )
            return
        if self._parent_reserved and not self._parent_released:
            # A release call may have committed before its return/store
            # boundary was interrupted.  The exact parent query is the
            # authoritative monotonic witness.
            self._parent_reserved = False
            self._parent_released = True
            self._telemetry = replace(
                self._telemetry,
                parent_delegation_release_success_count=1,
            )

    def _recover_allocation_cleanup_snapshot_locked(self, *, opening: bool) -> None:
        owner = self._allocation_owner
        if owner is None or self._owner_closed:
            return
        if owner.closed:
            if (
                self._owned_capabilities
                or self._pending_free_leases
                or self._orphan_cleanups
            ):
                _fail(
                    "hip_fgmres_coarse_context_owner_closed_with_live_lineage",
                    "/cleanup/allocation_owner",
                    cleanup_owner=self,
                )
            self._owner_closed = True
            self._telemetry = replace(
                self._telemetry,
                lineage_owner_close_success_count=1,
            )
            return
        capabilities, free_leases, orphan_leases = (
            snapshot_hip_allocation_owner_cleanup_v1(owner)
        )
        views = {view.name: view for view in self._owned_buffers}
        for capability in capabilities:
            validate_hip_allocation_capability_v1(
                capability,
                expected_owner=owner,
            )
            view = views.get(capability.role)
            if view is None or (
                capability.nbytes != view.byte_length
                or capability.element_type != ("i32" if view.dtype == "<u4" else "f64")
                or capability.runtime_owner is not self._runtime
                or capability.device_ordinal != self._device_ordinal
            ):
                _fail(
                    "hip_fgmres_coarse_context_allocation_recovery_invalid",
                    f"/cleanup/owned_buffers/{capability.role}",
                    cleanup_owner=self,
                )
            current = self._owned_capabilities.get(capability.role)
            if current is not None and current is not capability:
                _fail(
                    "hip_fgmres_coarse_context_allocation_recovery_changed",
                    f"/cleanup/owned_buffers/{capability.role}",
                    cleanup_owner=self,
                )
            self._owned_capabilities[capability.role] = capability
            self._cleanup_dispositions.setdefault(capability.role, "live")
        for lease in free_leases:
            capability = lease.capability
            current = self._owned_capabilities.get(capability.role)
            if current is not capability:
                _fail(
                    "hip_fgmres_coarse_context_free_lease_recovery_invalid",
                    f"/cleanup/owned_buffers/{capability.role}",
                    cleanup_owner=self,
                )
            known = self._pending_free_leases.get(capability.role)
            if known is not None and known is not lease:
                _fail(
                    "hip_fgmres_coarse_context_free_lease_recovery_changed",
                    f"/cleanup/owned_buffers/{capability.role}",
                    cleanup_owner=self,
                )
            self._pending_free_leases[capability.role] = lease
        known_orphans = {id(cleanup.lease) for cleanup in self._orphan_cleanups}
        for lease in orphan_leases:
            if id(lease) in known_orphans:
                continue
            if lease.role not in views:
                _fail(
                    "hip_fgmres_coarse_context_orphan_recovery_invalid",
                    "/cleanup/allocation_lineage/orphan",
                    cleanup_owner=self,
                )
            self._orphan_cleanups.append(
                _OrphanCleanupV1(
                    lease,
                    lease.nbytes,
                    lease.pointer_snapshot is None,
                )
            )
            known_orphans.add(id(lease))
        if opening:
            pointerful_orphans = tuple(
                cleanup
                for cleanup in self._orphan_cleanups
                if cleanup.lease.pointer_snapshot is not None
            )
            managed_bytes = sum(row.nbytes for row in capabilities) + sum(
                row.byte_length for row in pointerful_orphans
            )
            self._telemetry = replace(
                self._telemetry,
                allocation_success_count=(len(capabilities) + len(pointerful_orphans)),
                current_device_bytes=managed_bytes,
                peak_device_bytes=max(self._telemetry.peak_device_bytes, managed_bytes),
                lineage_capability_mint_success_count=len(capabilities),
                lineage_capability_mint_bytes=sum(row.nbytes for row in capabilities),
            )

    def _fence_locked(self) -> int:
        if self._closed:
            _fail(
                "hip_fgmres_coarse_context_unavailable",
                "/fence",
                cleanup_owner=self,
            )
        kernel = self._require_kernel()
        if not self._stream_work_requires_fence and not kernel.pending:
            return 0
        runtime = self._runtime
        stream = self._stream
        if runtime is None or stream is None:
            _fail(
                "hip_fgmres_coarse_context_authority_invalid",
                "/fence/runtime",
                cleanup_owner=self,
            )
        self._telemetry = replace(
            self._telemetry,
            fence_attempt_count=self._telemetry.fence_attempt_count + 1,
        )
        try:
            runtime.synchronize(stream)  # type: ignore[attr-defined]
        except BaseException as exc:
            self._poison("hip_fgmres_coarse_context_fence_outcome_uncertain")
            self._cleanup_failed = True
            self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
                "hip_fgmres_coarse_context_fence_failed", _detail(exc)
            )
            raise HipFgmresFixedRankCoarseContextV1Error(
                self._failure_reason.code,
                "/fence/synchronize",
                self._failure_reason.detail,
                cleanup_owner=self,
            ) from exc
        pending_before = kernel.pending_accepted_launch_count
        try:
            acknowledged = kernel.acknowledge_stream_fence(
                self._stream_pointer_snapshot
            )
        except BaseException as exc:
            # The acknowledgement has no native call.  If its monotonic state
            # already cleared, converge the interrupted return/store boundary.
            if kernel.pending:
                self._poison("hip_fgmres_coarse_context_fence_ack_failed")
                self._cleanup_failed = True
                raise HipFgmresFixedRankCoarseContextV1Error(
                    "hip_fgmres_coarse_context_fence_ack_failed",
                    "/fence/acknowledge",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            acknowledged = pending_before
        self._stream_work_requires_fence = False
        self._telemetry = replace(
            self._telemetry,
            fence_success_count=self._telemetry.fence_success_count + 1,
            fence_acknowledged_launch_count=(
                self._telemetry.fence_acknowledged_launch_count + acknowledged
            ),
        )
        return acknowledged

    def _close_kernel_locked(self) -> None:
        if self._kernel_terminal or self._kernel is None:
            return
        kernel = self._kernel
        self._telemetry = replace(
            self._telemetry,
            module_close_attempt_count=self._telemetry.module_close_attempt_count + 1,
        )
        try:
            kernel.close()
        except HipRtcFgmresFixedRankCoarseV1Error as exc:
            if kernel.closed or kernel.unload_disposition == "terminal":
                self._kernel_terminal = True
                self._telemetry = replace(
                    self._telemetry,
                    module_close_success_count=(
                        self._telemetry.module_close_success_count + 1
                    ),
                )
                return
            if kernel.unload_disposition == "unload_outcome_uncertain":
                # The RTC owner forbids a second unload.  Record terminal
                # quarantine and continue with post-fence allocation cleanup.
                self._kernel_terminal = True
                self._cleanup_quarantined = True
                self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
                    "hip_fgmres_coarse_context_module_unload_uncertain",
                    _detail(exc),
                )
                return
            self._cleanup_failed = True
            self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
                "hip_fgmres_coarse_context_module_close_failed", _detail(exc)
            )
            raise HipFgmresFixedRankCoarseContextV1Error(
                self._failure_reason.code,
                "/cleanup/kernel",
                self._failure_reason.detail,
                cleanup_owner=self,
            ) from exc
        except BaseException as exc:
            if kernel.closed or kernel.unload_disposition == "terminal":
                self._kernel_terminal = True
                self._telemetry = replace(
                    self._telemetry,
                    module_close_success_count=(
                        self._telemetry.module_close_success_count + 1
                    ),
                )
                if not isinstance(exc, Exception):
                    raise
                return
            self._cleanup_failed = True
            raise HipFgmresFixedRankCoarseContextV1Error(
                "hip_fgmres_coarse_context_module_close_failed",
                "/cleanup/kernel",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        self._kernel_terminal = True
        self._telemetry = replace(
            self._telemetry,
            module_close_success_count=self._telemetry.module_close_success_count + 1,
        )

    def _release_parent_locked(self) -> None:
        if self._parent_released:
            return
        parent = self._parent
        plan = self._plan
        if parent is None or plan is None or not self._parent_reserved:
            return
        try:
            parent._release_fixed_rank_coarse_child(self._token, self)
        except BaseException as exc:
            try:
                still_active = parent._fixed_rank_coarse_child_token_is_active(
                    self._token,
                    self,
                )
            except BaseException:
                still_active = True
            if still_active:
                self._cleanup_failed = True
                raise HipFgmresFixedRankCoarseContextV1Error(
                    "hip_fgmres_coarse_context_parent_release_failed",
                    "/cleanup/parent_delegation",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            self._parent_released = True
            self._parent_reserved = False
            self._telemetry = replace(
                self._telemetry,
                parent_delegation_release_success_count=1,
            )
            if not isinstance(exc, Exception):
                raise
            return
        self._parent_released = True
        self._parent_reserved = False
        self._telemetry = replace(
            self._telemetry,
            parent_delegation_release_success_count=1,
        )

    def _retire_owned_locked(self, name: str) -> BaseException | None:
        capability = self._owned_capabilities.get(name)
        if capability is None:
            return None
        owner = self._allocation_owner
        runtime = self._runtime
        if owner is None or runtime is None:
            return RuntimeError("allocation cleanup authority missing")
        try:
            disposition = self._cleanup_dispositions.get(name, "live")
            lease = self._pending_free_leases.get(name)
            if disposition == "terminal":
                self._owned_capabilities.pop(name, None)
                self._pending_free_leases.pop(name, None)
                return None
            if disposition == "live":
                validate_hip_allocation_owner_v1(owner)
                if lease is None:
                    lease = owner.begin_free(
                        capability,
                        _control_token=self._token,
                    )
                    self._pending_free_leases[name] = lease
                self._telemetry = replace(
                    self._telemetry,
                    deallocation_attempt_count=(
                        self._telemetry.deallocation_attempt_count + 1
                    ),
                )
                self._cleanup_dispositions[name] = "free_call_inflight"
                try:
                    runtime.free(lease.pointer_snapshot)  # type: ignore[attr-defined]
                    self._cleanup_dispositions[name] = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(exc):
                        self._cleanup_dispositions[name] = "live"
                        if isinstance(exc, Exception):
                            return exc
                        raise
                    self._cleanup_dispositions[name] = "quarantine_pending"
                    outcome = owner.resolve_free_quarantine(
                        lease,
                        _control_token=self._token,
                    )
                    if outcome != "quarantined":
                        _fail(
                            "hip_fgmres_coarse_context_lineage_outcome_invalid",
                            f"/cleanup/owned_buffers/{name}",
                            cleanup_owner=self,
                        )
                    self._finish_retired_owned(
                        name,
                        capability.nbytes,
                        quarantined=True,
                    )
                    if not isinstance(exc, Exception):
                        raise
                    return None
                disposition = self._cleanup_dispositions[name]
            elif disposition == "free_call_inflight":
                self._cleanup_dispositions[name] = "quarantine_pending"
                disposition = "quarantine_pending"
            if disposition == "quarantine_pending":
                if lease is None:
                    outcome = owner.resolve_poisoned_allocation_quarantine(
                        capability,
                        _control_token=self._token,
                    )
                else:
                    outcome = owner.resolve_free_quarantine(
                        lease,
                        _control_token=self._token,
                    )
                if outcome != "quarantined":
                    _fail(
                        "hip_fgmres_coarse_context_lineage_outcome_invalid",
                        f"/cleanup/owned_buffers/{name}",
                        cleanup_owner=self,
                    )
                self._finish_retired_owned(
                    name,
                    capability.nbytes,
                    quarantined=True,
                )
                return None
            if disposition != "external_free_succeeded" or lease is None:
                _fail(
                    "hip_fgmres_coarse_context_cleanup_disposition_invalid",
                    f"/cleanup/owned_buffers/{name}",
                    cleanup_owner=self,
                )
            outcome = owner.resolve_free_success(
                lease,
                _control_token=self._token,
            )
            if outcome != "succeeded":
                _fail(
                    "hip_fgmres_coarse_context_lineage_outcome_invalid",
                    f"/cleanup/owned_buffers/{name}",
                    cleanup_owner=self,
                )
            self._finish_retired_owned(
                name,
                capability.nbytes,
                quarantined=False,
            )
            return None
        except Exception as exc:
            return exc

    def _finish_retired_owned(
        self, name: str, byte_length: int, *, quarantined: bool
    ) -> None:
        self._owned_capabilities.pop(name, None)
        self._pending_free_leases.pop(name, None)
        self._cleanup_dispositions[name] = "terminal"
        self._telemetry = replace(
            self._telemetry,
            deallocation_success_count=(
                self._telemetry.deallocation_success_count + (0 if quarantined else 1)
            ),
            current_device_bytes=max(
                0, self._telemetry.current_device_bytes - byte_length
            ),
            quarantined_device_bytes=(
                self._telemetry.quarantined_device_bytes
                + (byte_length if quarantined else 0)
            ),
            lineage_free_quarantine_count=(
                self._telemetry.lineage_free_quarantine_count
                + (1 if quarantined else 0)
            ),
            lineage_free_acknowledgement_count=(
                self._telemetry.lineage_free_acknowledgement_count
                + (0 if quarantined else 1)
            ),
        )
        self._cleanup_quarantined = self._cleanup_quarantined or quarantined

    def _retire_orphan_locked(self, cleanup: _OrphanCleanupV1) -> BaseException | None:
        if cleanup not in self._orphan_cleanups:
            return None
        owner = self._allocation_owner
        runtime = self._runtime
        if owner is None or runtime is None:
            return RuntimeError("orphan cleanup authority missing")
        try:
            if cleanup.disposition == "terminal":
                self._orphan_cleanups.remove(cleanup)
                return None
            if cleanup.must_quarantine or cleanup.lease.pointer_snapshot is None:
                cleanup.disposition = "quarantine_pending"
            if cleanup.disposition == "live":
                self._telemetry = replace(
                    self._telemetry,
                    deallocation_attempt_count=(
                        self._telemetry.deallocation_attempt_count + 1
                    ),
                )
                cleanup.disposition = "free_call_inflight"
                try:
                    runtime.free(cleanup.lease.pointer_snapshot)  # type: ignore[attr-defined]
                    cleanup.disposition = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(exc):
                        cleanup.disposition = "live"
                        if isinstance(exc, Exception):
                            return exc
                        raise
                    cleanup.disposition = "quarantine_pending"
                    outcome = owner.resolve_orphan_free_quarantine(
                        cleanup.lease,
                        _control_token=self._token,
                    )
                    if outcome != "quarantined":
                        _fail(
                            "hip_fgmres_coarse_context_lineage_outcome_invalid",
                            "/cleanup/allocation_lineage/orphan",
                            cleanup_owner=self,
                        )
                    self._finish_retired_orphan(cleanup, quarantined=True)
                    if not isinstance(exc, Exception):
                        raise
                    return None
            elif cleanup.disposition == "free_call_inflight":
                cleanup.disposition = "quarantine_pending"
            if cleanup.disposition == "quarantine_pending":
                outcome = owner.resolve_orphan_free_quarantine(
                    cleanup.lease,
                    _control_token=self._token,
                )
                if outcome != "quarantined":
                    _fail(
                        "hip_fgmres_coarse_context_lineage_outcome_invalid",
                        "/cleanup/allocation_lineage/orphan",
                        cleanup_owner=self,
                    )
                self._finish_retired_orphan(cleanup, quarantined=True)
                return None
            if cleanup.disposition != "external_free_succeeded":
                _fail(
                    "hip_fgmres_coarse_context_cleanup_disposition_invalid",
                    "/cleanup/allocation_lineage/orphan",
                    cleanup_owner=self,
                )
            outcome = owner.resolve_orphan_free_success(
                cleanup.lease,
                _control_token=self._token,
            )
            if outcome != "succeeded":
                _fail(
                    "hip_fgmres_coarse_context_lineage_outcome_invalid",
                    "/cleanup/allocation_lineage/orphan",
                    cleanup_owner=self,
                )
            self._finish_retired_orphan(cleanup, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_retired_orphan(
        self,
        cleanup: _OrphanCleanupV1,
        *,
        quarantined: bool,
    ) -> None:
        cleanup.disposition = "terminal"
        self._orphan_cleanups.remove(cleanup)
        self._telemetry = replace(
            self._telemetry,
            deallocation_success_count=(
                self._telemetry.deallocation_success_count
                + (
                    1
                    if cleanup.lease.pointer_snapshot is not None and not quarantined
                    else 0
                )
            ),
            current_device_bytes=max(
                0,
                self._telemetry.current_device_bytes
                - (
                    cleanup.byte_length
                    if cleanup.lease.pointer_snapshot is not None
                    else 0
                ),
            ),
            quarantined_device_bytes=(
                self._telemetry.quarantined_device_bytes
                + (cleanup.byte_length if quarantined else 0)
            ),
            lineage_orphan_quarantine_count=(
                self._telemetry.lineage_orphan_quarantine_count
                + (1 if quarantined else 0)
            ),
            lineage_orphan_acknowledgement_count=(
                self._telemetry.lineage_orphan_acknowledgement_count
                + (0 if quarantined else 1)
            ),
        )
        self._cleanup_quarantined = self._cleanup_quarantined or quarantined

    def _validate_authority(self) -> _HipFgmresFixedRankCoarseParentAuthorityV1:
        parent = self._parent
        plan = self._plan
        owner = self._allocation_owner
        kernel = self._kernel
        canonical = self._parent_authority
        if (
            parent is None
            or plan is None
            or owner is None
            or kernel is None
            or canonical is None
            or self._parent_released
            or self._owner_closed
            or self._kernel_terminal
            or self._closed
        ):
            _fail(
                "hip_fgmres_coarse_context_authority_invalid",
                "/authority",
                cleanup_owner=self,
            )
        try:
            current = parent._fixed_rank_coarse_child_authority(self._token, self)
            validate_hip_fgmres_fixed_rank_coarse_plan_v1(
                plan,
                expected_fgmres_plan=current.source_plan,
                expected_coarse_space=plan._source_coarse_space,
            )
            validate_hip_allocation_borrow_v1(current.parent_group_lease)
            validate_hip_allocation_owner_v1(owner)
            validate_hip_allocation_owner_control_v1(
                owner,
                self._token,
                expected_owner_role=_OWNER_ROLE,
                allowed_roles=_OWNED_ROLES,
                expected_allocation_publication_count=6,
            )
            capabilities, free_leases, orphan_leases = (
                snapshot_hip_allocation_owner_cleanup_v1(owner)
            )
            for capability in current.source_capabilities:
                validate_hip_allocation_capability_v1(capability)
            for capability in capabilities:
                validate_hip_allocation_capability_v1(capability, expected_owner=owner)
        except BaseException as exc:
            self._poison("hip_fgmres_coarse_context_authority_changed")
            raise HipFgmresFixedRankCoarseContextV1Error(
                "hip_fgmres_coarse_context_authority_invalid",
                "/authority",
                _detail(exc),
                cleanup_owner=self,
            ) from exc
        if (
            not _parent_authority_matches(current, canonical)
            or current.stream is not self._stream
            or _pointer_value(current.stream) != self._stream_pointer_snapshot
            or current.runtime is not self._runtime
            or current.loaded_runtime is not self._loaded_runtime
            or current.device_ordinal != self._device_ordinal
            or current.architecture != self._architecture
            or len(capabilities) != 6
            or tuple(capability.role for capability in capabilities) != _OWNED_ROLES
            or any(
                capability is not self._owned_capabilities.get(capability.role)
                for capability in capabilities
            )
            or free_leases
            or orphan_leases
            or kernel.closed
            or kernel.identity is not self._kernel_identity_snapshot
        ):
            self._poison("hip_fgmres_coarse_context_authority_changed")
            _fail(
                "hip_fgmres_coarse_context_authority_invalid",
                "/authority",
                cleanup_owner=self,
            )
        for role, capability in zip(
            _PARENT_ROLES, current.source_capabilities, strict=True
        ):
            row = plan.buffer(role)
            if capability.role != role or capability.nbytes != row.byte_length:
                _fail(
                    "hip_fgmres_coarse_context_parent_extent_invalid",
                    f"/authority/parent/{role}",
                    cleanup_owner=self,
                )
        return current

    def _pointer_arguments(
        self, authority: _HipFgmresFixedRankCoarseParentAuthorityV1
    ) -> dict[str, object]:
        values = {
            capability.role: capability.base
            for capability in authority.source_capabilities
        }
        values.update(
            {role: self._owned_capabilities[role].base for role in _OWNED_ROLES}
        )
        return values

    def _poison(self, detail: str) -> None:
        if self._poisoned:
            return
        self._poisoned = True
        self._failure_reason = HipFgmresFixedRankCoarseReasonV1(
            "hip_fgmres_coarse_context_poisoned",
            _detail(detail),
        )
        parent = self._parent
        if parent is not None and not self._parent_released:
            try:
                parent._poison_fixed_rank_coarse_child(self._token, self, detail)
            except BaseException:
                pass

    def _require_kernel(self) -> HipRtcFgmresFixedRankCoarseKernelV1:
        if self._kernel is None or self._kernel_terminal:
            _fail(
                "hip_fgmres_coarse_context_kernel_invalid",
                "/kernel",
                cleanup_owner=self,
            )
        return self._kernel

    def _require_dimensions(self) -> HipFgmresFixedRankCoarseDimensionsV1:
        if self._dimensions is None:
            _fail(
                "hip_fgmres_coarse_context_dimensions_invalid",
                "/dimensions",
                cleanup_owner=self,
            )
        return self._dimensions

    def _build_receipt(
        self, status: CoarseContextStatusV1
    ) -> HipFgmresFixedRankCoarseContextReceiptV1:
        if (
            self._bindings is None
            or self._dimensions is None
            or self._kernel_summary is None
        ):
            _fail("hip_fgmres_coarse_context_receipt_unavailable", "/receipt")
        ready = status == "context_ready"
        lineage = HipFgmresFixedRankCoarseLineageV1(
            capability_profile=HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
            evidence_scope=HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
            owner_role=_OWNER_ROLE,
            runtime_device_bound=ready,
            same_stream_bound=ready,
            delegated_parent_capability_count=(
                0 if self._parent_authority is None or self._parent_released else 3
            ),
            managed_buffer_count=len(self._owned_capabilities),
            managed_device_bytes=self._telemetry.current_device_bytes,
            all_owned_buffers_managed=ready and len(self._owned_capabilities) == 6,
        )
        claims = HipFgmresFixedRankCoarseClaimsV1(
            exact_live_parent_delegated=ready,
            allocator_provenance_bound=ready,
            static_uploads_enqueued_once=(
                ready
                and self._telemetry.h2d_operation_success_count == 3
                and self._telemetry.h2d_bytes_succeeded
                == self._plan.static_upload_byte_count  # type: ignore[union-attr]
            ),
            same_stream_application_ready=ready,
            application_host_copy_zero_by_construction=ready,
        )
        draft = HipFgmresFixedRankCoarseContextReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_EVIDENCE_SCOPE,
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=(
                None
                if status in {"context_ready", "context_closed"}
                else self._failure_reason
            ),
            bindings=self._bindings,
            kernel=self._kernel_summary,
            dimensions=self._dimensions,
            owned_buffers=self._owned_buffers,
            allocation_lineage=lineage,
            telemetry=self._telemetry,
            claims=claims,
            context_receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            context_receipt_hash=canonical_hash(
                _context_receipt_payload(draft, include_hash=False)
            ),
        )


class _SerializedContextOperation:
    def __init__(
        self, context: HipFgmresFixedRankCoarseExecutionContextV1, path: str
    ) -> None:
        self._context = context
        self._path = path

    def __enter__(self) -> None:
        context = self._context
        context._lock.acquire()
        if context._operation_active:
            context._lock.release()
            _fail(
                "hip_fgmres_coarse_context_reentrant_operation",
                self._path,
                cleanup_owner=context,
            )
        context._operation_active = True

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        context = self._context
        context._operation_active = False
        context._lock.release()


def open_hip_fgmres_fixed_rank_coarse_context_v1(
    parent: HipFgmresLiveCheckpointExecutionContextV1,
    plan: HipFgmresFixedRankCoarsePlanV1,
    *,
    architecture: str | None = None,
    hiprtc_library: str | None = None,
    memory_budget_bytes: int | None = None,
    rtc_kernel: HipRtcFgmresFixedRankCoarseKernelV1 | None = None,
) -> HipFgmresFixedRankCoarseContextOpenResultV1:
    """Open the exact parent3/owned6 coarse lifetime and upload slice."""

    context = HipFgmresFixedRankCoarseExecutionContextV1(_mint=_CONTEXT_MINT)
    owner_handoff: list[HipAllocationOwnerV1 | None] = [None]
    internal_kernel_handoff = _HipRtcFgmresFixedRankCoarseKernelHandoffV1()
    caller_kernel_handoff: list[HipRtcFgmresFixedRankCoarseKernelV1 | None] = [None]
    try:
        if type(parent) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail("hip_fgmres_coarse_context_parent_invalid", "/parent")
        if type(plan) is not HipFgmresFixedRankCoarsePlanV1:
            _fail("hip_fgmres_coarse_context_plan_invalid", "/plan")
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(
            plan,
            expected_fgmres_plan=plan._source_fgmres_plan,
            expected_coarse_space=plan._source_coarse_space,
        )
        if isinstance(memory_budget_bytes, bool) or (
            memory_budget_bytes is not None
            and (type(memory_budget_bytes) is not int or memory_budget_bytes <= 0)
        ):
            _fail(
                "hip_fgmres_coarse_context_memory_budget_invalid",
                "/memory_budget_bytes",
            )
        if (
            memory_budget_bytes is not None
            and plan.owned_device_byte_length > memory_budget_bytes
        ):
            return HipFgmresFixedRankCoarseContextOpenResultV1(
                None,
                None,
                HipFgmresFixedRankCoarseReasonV1(
                    "hip_fgmres_coarse_context_memory_budget_exceeded",
                    f"required={plan.owned_device_byte_length}",
                ),
            )

        context._parent = parent
        context._plan = plan
        acquired = parent._reserve_fixed_rank_coarse_child(context._token, context)
        if acquired is not context._token:
            _fail(
                "hip_fgmres_coarse_context_parent_reservation_changed",
                "/parent/delegation",
                cleanup_owner=context,
            )
        context._parent_reserved = True
        authority = parent._fixed_rank_coarse_child_authority(context._token, context)
        _validate_plan_parent_binding(plan, authority)
        context._parent_authority = authority
        context._runtime = authority.runtime
        context._loaded_runtime = authority.loaded_runtime
        context._stream = authority.stream
        context._stream_pointer_snapshot = _pointer_value(authority.stream)
        context._device_ordinal = authority.device_ordinal
        context._architecture = authority.architecture
        context._actual_backend = authority.actual_backend
        context._telemetry = replace(
            context._telemetry,
            parent_delegation_acquire_success_count=1,
        )
        if architecture is not None and architecture != authority.architecture:
            _fail(
                "hip_fgmres_coarse_context_architecture_mismatch",
                "/architecture",
                cleanup_owner=context,
            )

        owner = open_hip_allocation_peer_owner_v1(
            authority.allocation_owner,
            _OWNER_ROLE,
            _handoff=owner_handoff,
        )
        context._allocation_owner = owner
        context._telemetry = replace(
            context._telemetry,
            lineage_owner_open_success_count=1,
        )
        reserve_hip_allocation_owner_control_v1(
            owner,
            context._token,
            expected_owner_role=_OWNER_ROLE,
            allowed_roles=_OWNED_ROLES,
        )

        if rtc_kernel is None:
            context._kernel_origin = "internally_compiled"
            kernel = _compile_fixed_rank_coarse_with_handoff_v1(
                compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1,
                internal_kernel_handoff,
                authority.loaded_runtime,
                authority.architecture,
                hiprtc_library,
            )
            _validate_kernel_binding(kernel, plan, authority)
        else:
            context._kernel_origin = "caller_supplied"
            kernel = _preflight_kernel(
                rtc_kernel,
                plan,
                authority,
                _handoff=caller_kernel_handoff,
            )
        context._kernel = kernel
        context._kernel_identity_snapshot = kernel.identity
        context._kernel_summary = _kernel_summary(kernel, context._kernel_origin)
        context._telemetry = replace(
            context._telemetry,
            module_owner_acquire_success_count=1,
        )

        context._owned_buffers = tuple(
            _buffer_view(row) for row in plan.buffers if row.ownership == "owned"
        )
        for view in context._owned_buffers:
            context._telemetry = replace(
                context._telemetry,
                allocation_attempt_count=context._telemetry.allocation_attempt_count
                + 1,
            )
            try:
                capability = owner.allocate(
                    view.name,
                    view.byte_length,
                    "i32" if view.dtype == "<u4" else "f64",
                    _control_token=context._token,
                )
            except HipAllocationLineageError as exc:
                orphan = exc.orphan_cleanup_lease
                if orphan is not None:
                    context._orphan_cleanups.append(
                        _OrphanCleanupV1(
                            orphan,
                            orphan.nbytes,
                            exc.code
                            in {
                                "hip_allocation_range_overlap",
                                "hip_allocation_range_overflow",
                                "hip_allocation_domain_poisoned",
                                "hip_allocation_malloc_outcome_uncertain",
                            },
                        )
                    )
                    if orphan.pointer_snapshot is not None:
                        current = (
                            context._telemetry.current_device_bytes + orphan.nbytes
                        )
                        context._telemetry = replace(
                            context._telemetry,
                            allocation_success_count=(
                                context._telemetry.allocation_success_count + 1
                            ),
                            current_device_bytes=current,
                            peak_device_bytes=max(
                                context._telemetry.peak_device_bytes, current
                            ),
                        )
                raise
            context._owned_capabilities[view.name] = capability
            context._cleanup_dispositions[view.name] = "live"
            current = context._telemetry.current_device_bytes + view.byte_length
            context._telemetry = replace(
                context._telemetry,
                allocation_success_count=context._telemetry.allocation_success_count
                + 1,
                current_device_bytes=current,
                peak_device_bytes=max(context._telemetry.peak_device_bytes, current),
                lineage_capability_mint_success_count=(
                    context._telemetry.lineage_capability_mint_success_count + 1
                ),
                lineage_capability_mint_bytes=(
                    context._telemetry.lineage_capability_mint_bytes + view.byte_length
                ),
            )

        _validate_owned_capabilities(context)
        coarse = plan._source_coarse_space
        static_arrays = {
            "coarse_physical_basis_z": np.ascontiguousarray(
                coarse.physical_basis_z, dtype="<f8"
            ),
            "coarse_operator_basis_az": np.ascontiguousarray(
                coarse.operator_basis_az, dtype="<f8"
            ),
            "coarse_cholesky_l": np.ascontiguousarray(
                coarse.coarse_cholesky_l, dtype="<f8"
            ),
        }
        for role in _STATIC_UPLOAD_ROLES:
            array = static_arrays[role]
            capability = context._owned_capabilities[role]
            if int(array.nbytes) != capability.nbytes:
                _fail(
                    "hip_fgmres_coarse_context_static_upload_extent_invalid",
                    f"/uploads/{role}",
                    cleanup_owner=context,
                )
            context._telemetry = replace(
                context._telemetry,
                h2d_operation_attempt_count=(
                    context._telemetry.h2d_operation_attempt_count + 1
                ),
                h2d_bytes_attempted=(
                    context._telemetry.h2d_bytes_attempted + int(array.nbytes)
                ),
            )
            context._stream_work_requires_fence = True
            try:
                authority.runtime.copy_h2d_async(  # type: ignore[attr-defined]
                    capability.base,
                    array,
                    authority.stream,
                )
            except BaseException:
                context._poison("hip_fgmres_coarse_context_upload_outcome_uncertain")
                raise
            context._telemetry = replace(
                context._telemetry,
                h2d_operation_success_count=(
                    context._telemetry.h2d_operation_success_count + 1
                ),
                h2d_bytes_succeeded=(
                    context._telemetry.h2d_bytes_succeeded + int(array.nbytes)
                ),
            )

        parent_generation_hash = _generation_hash(authority.source_capabilities)
        owned_generation_hash = _generation_hash(
            tuple(context._owned_capabilities[role] for role in _OWNED_ROLES)
        )
        context._context_id = canonical_hash(
            {
                "profile": (HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_CAPABILITY_PROFILE),
                "live_context_id": authority.live_context_id,
                "live_opening_receipt_hash": authority.live_opening_receipt_hash,
                "coarse_plan_hash": plan.plan_hash,
                "parent_child_epoch": authority.child_epoch,
                "parent_generation_binding_hash": parent_generation_hash,
                "owned_generation_binding_hash": owned_generation_hash,
            }
        )
        context._bindings = HipFgmresFixedRankCoarseBindingsV1(
            live_checkpoint_context_id=authority.live_context_id,
            live_checkpoint_opening_receipt_hash=(authority.live_opening_receipt_hash),
            source_fgmres_plan_hash=plan.source_fgmres_plan_hash,
            recurrence_plan_hash=authority.recurrence_plan.plan_hash,
            coarse_plan_hash=plan.plan_hash,
            coarse_space_hash=plan.source_coarse_space_hash,
            coarse_memory_layout_hash=plan.memory_layout_hash,
            kernel_abi_hash=plan.kernel_abi_hash,
            parent_child_epoch=authority.child_epoch,
            parent_generation_binding_hash=parent_generation_hash,
            owned_generation_binding_hash=owned_generation_hash,
        )
        context._dimensions = HipFgmresFixedRankCoarseDimensionsV1(
            free_dof_count=plan.free_dof_count,
            restart_dimension=plan.restart_dimension,
            retained_rank=plan.retained_rank,
        )
        # Ready means the immutable Z/AZ/L initialization has crossed an
        # observed same-stream setup fence.  This one setup synchronization is
        # outside every zero-copy/zero-sync application window.
        context._fence_locked()
        context._validate_authority()
        context._opening_receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
            context._opening_receipt,
            expected_context=context,
        )
        return HipFgmresFixedRankCoarseContextOpenResultV1(
            context,
            context._opening_receipt,
        )
    except BaseException as primary:
        if context._allocation_owner is None and owner_handoff[0] is not None:
            context._allocation_owner = owner_handoff[0]
        if context._kernel is None:
            handoff_kernel = internal_kernel_handoff.kernel
            handoff_origin: KernelOriginV1 = "internally_compiled"
            if handoff_kernel is None:
                handoff_kernel = caller_kernel_handoff[0]
                handoff_origin = "caller_supplied"
            if handoff_kernel is not None:
                context._kernel = handoff_kernel
                context._kernel_identity_snapshot = handoff_kernel.identity
                context._kernel_origin = handoff_origin
                context._kernel_summary = _kernel_summary(
                    handoff_kernel,
                    handoff_origin,
                )
        recovery_error: BaseException | None = None
        try:
            context._recover_parent_reservation_locked()
            context._recover_allocation_cleanup_snapshot_locked(opening=True)
        except BaseException as exc:
            recovery_error = exc
        cleanup_error: BaseException | None = None
        if context._parent is not None:
            try:
                context.close()
            except BaseException as exc:
                cleanup_error = exc
        if recovery_error is not None or cleanup_error is not None:
            raise HipFgmresFixedRankCoarseContextV1Error(
                "hip_fgmres_coarse_context_open_cleanup_failed",
                "/open/cleanup",
                "primary="
                + _detail(primary)
                + "; recovery="
                + _detail(recovery_error)
                + "; cleanup="
                + _detail(cleanup_error),
                cleanup_owner=None if context.closed else context,
            ) from primary
        if isinstance(primary, HipFgmresFixedRankCoarseContextV1Error):
            raise
        raise HipFgmresFixedRankCoarseContextV1Error(
            "hip_fgmres_coarse_context_open_interrupted"
            if not isinstance(primary, Exception)
            else "hip_fgmres_coarse_context_open_failed",
            "/open",
            _detail(primary),
            cleanup_owner=None if context.closed else context,
        ) from primary


def _validate_plan_parent_binding(
    plan: HipFgmresFixedRankCoarsePlanV1,
    authority: _HipFgmresFixedRankCoarseParentAuthorityV1,
) -> None:
    try:
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(
            plan,
            expected_fgmres_plan=authority.source_plan,
            expected_coarse_space=plan._source_coarse_space,
        )
        validate_hip_allocation_borrow_v1(authority.parent_group_lease)
    except BaseException as exc:
        raise HipFgmresFixedRankCoarseContextV1Error(
            "hip_fgmres_coarse_context_parent_binding_invalid",
            "/parent/authority",
            _detail(exc),
        ) from exc
    if (
        plan.capability_profile
        != HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE
        or plan.source_fgmres_plan_hash != authority.source_plan.plan_hash
        or plan.free_dof_count != authority.recurrence_plan.free_dof_count
        or plan.restart_dimension != authority.recurrence_plan.restart_dimension
        or tuple(capability.role for capability in authority.source_capabilities)
        != _PARENT_ROLES
        or any(
            capability.runtime_owner is not authority.runtime
            or capability.runtime_domain is not authority.allocation_runtime_domain
            or capability.runtime_domain_id != authority.allocation_runtime_domain_id
            or capability.device_ordinal != authority.device_ordinal
            or capability.nbytes != plan.buffer(capability.role).byte_length
            for capability in authority.source_capabilities
        )
    ):
        _fail(
            "hip_fgmres_coarse_context_parent_binding_invalid",
            "/parent/authority",
        )


def _preflight_kernel(
    kernel: HipRtcFgmresFixedRankCoarseKernelV1,
    plan: HipFgmresFixedRankCoarsePlanV1,
    authority: _HipFgmresFixedRankCoarseParentAuthorityV1,
    *,
    _handoff: list[HipRtcFgmresFixedRankCoarseKernelV1 | None],
) -> HipRtcFgmresFixedRankCoarseKernelV1:
    if type(_handoff) is not list or len(_handoff) != 1 or _handoff[0] is not None:
        _fail("hip_fgmres_coarse_context_kernel_handoff_invalid", "/rtc_kernel")
    _validate_kernel_binding(kernel, plan, authority)
    _handoff[0] = kernel
    return kernel


def _validate_kernel_binding(
    kernel: HipRtcFgmresFixedRankCoarseKernelV1,
    plan: HipFgmresFixedRankCoarsePlanV1,
    authority: _HipFgmresFixedRankCoarseParentAuthorityV1,
) -> None:
    if type(kernel) is not HipRtcFgmresFixedRankCoarseKernelV1:
        _fail("hip_fgmres_coarse_context_kernel_invalid", "/rtc_kernel")
    identity = kernel.identity
    validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(identity)
    live_kernel = authority.live_context.opening_receipt.kernel
    if (
        kernel.closed
        or kernel.pending
        or identity.architecture != authority.architecture
        or identity.source_sha256 != plan.kernel_source_hash
        or identity.kernel_abi_hash != plan.kernel_abi_hash
        or live_kernel is None
        or identity.runtime_library.sha256 != live_kernel.runtime_library_sha256
    ):
        _fail("hip_fgmres_coarse_context_kernel_invalid", "/rtc_kernel")


def _kernel_summary(
    kernel: HipRtcFgmresFixedRankCoarseKernelV1,
    origin: KernelOriginV1,
) -> HipFgmresFixedRankCoarseKernelV1:
    identity = kernel.identity
    runtime_sha = identity.runtime_library.sha256
    if type(runtime_sha) is not str:
        _fail("hip_fgmres_coarse_context_kernel_invalid", "/kernel/runtime")
    return HipFgmresFixedRankCoarseKernelV1(
        architecture=identity.architecture,
        identity_hash=identity.identity_hash,
        source_sha256=identity.source_sha256,
        code_object_sha256=identity.code_object_sha256,
        kernel_abi_hash=identity.kernel_abi_hash,
        runtime_library_sha256=runtime_sha,
        runtime_library_discovery_source=identity.runtime_library.discovery_source,
        hiprtc_library_sha256=identity.hiprtc_library.sha256,
        hiprtc_library_discovery_source=identity.hiprtc_library.discovery_source,
        kernel_origin=origin,
    )


def _validate_owned_capabilities(
    context: HipFgmresFixedRankCoarseExecutionContextV1,
) -> None:
    owner = context._allocation_owner
    plan = context._plan
    if owner is None or plan is None:
        _fail("hip_fgmres_coarse_context_owned_lineage_invalid", "/allocations")
    capabilities = tuple(context._owned_capabilities.get(role) for role in _OWNED_ROLES)
    if any(
        type(capability) is not HipAllocationCapabilityV1 for capability in capabilities
    ):
        _fail("hip_fgmres_coarse_context_owned_lineage_invalid", "/allocations")
    for role, capability in zip(_OWNED_ROLES, capabilities, strict=True):
        assert type(capability) is HipAllocationCapabilityV1
        row = plan.buffer(role)
        validate_hip_allocation_capability_v1(capability, expected_owner=owner)
        if (
            capability.role != role
            or capability.nbytes != row.byte_length
            or capability.element_type != ("i32" if row.dtype == "<u4" else "f64")
        ):
            _fail(
                "hip_fgmres_coarse_context_owned_lineage_invalid",
                f"/allocations/{role}",
            )


def _buffer_view(
    row: HipFgmresFixedRankCoarseBufferPlanV1,
) -> HipFgmresFixedRankCoarseBufferV1:
    return HipFgmresFixedRankCoarseBufferV1(
        name=row.name,
        dtype=row.dtype,
        shape=row.shape,
        element_count=row.element_count,
        byte_length=row.byte_length,
        access=row.access,
        initialization=row.initialization,
        layout=row.layout,
    )


def _generation_hash(
    capabilities: tuple[HipAllocationCapabilityV1, ...],
) -> str:
    return canonical_hash(
        {
            "roles": [capability.role for capability in capabilities],
            "generations": [capability.generation for capability in capabilities],
            "byte_lengths": [capability.nbytes for capability in capabilities],
            "element_types": [capability.element_type for capability in capabilities],
        }
    )


def _parent_authority_matches(
    current: _HipFgmresFixedRankCoarseParentAuthorityV1,
    canonical: _HipFgmresFixedRankCoarseParentAuthorityV1,
) -> bool:
    identity_fields = (
        "live_context",
        "child_context",
        "child_token",
        "recurrence_plan",
        "source_plan",
        "runtime",
        "loaded_runtime",
        "stream",
        "allocation_owner",
        "allocation_runtime_domain",
        "parent_group_lease",
    )
    scalar_fields = (
        "child_epoch",
        "live_context_id",
        "live_opening_receipt_hash",
        "architecture",
        "device_ordinal",
        "allocation_runtime_domain_id",
        "actual_backend",
    )
    return (
        all(
            getattr(current, field) is getattr(canonical, field)
            for field in identity_fields
        )
        and all(
            actual is expected
            for actual, expected in zip(
                current.source_capabilities,
                canonical.source_capabilities,
                strict=True,
            )
        )
        and all(
            type(getattr(current, field)) is type(getattr(canonical, field))
            and getattr(current, field) == getattr(canonical, field)
            for field in scalar_fields
        )
    )


def _context_receipt_payload(
    receipt: HipFgmresFixedRankCoarseContextReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": (
            HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_CAPABILITY_PROFILE
        ),
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "kernel": receipt.kernel.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "owned_buffers": [row.to_dict() for row in receipt.owned_buffers],
        "allocation_lineage": receipt.allocation_lineage.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
    receipt: HipFgmresFixedRankCoarseContextReceiptV1,
    *,
    expected_context: HipFgmresFixedRankCoarseExecutionContextV1 | None = None,
) -> HipFgmresFixedRankCoarseContextReceiptV1:
    if type(receipt) is not HipFgmresFixedRankCoarseContextReceiptV1:
        _fail("hip_fgmres_coarse_context_receipt_type_invalid", "/receipt")
    _validate_json_schema(
        _context_receipt_payload(receipt, include_hash=True),
        _CONTEXT_SCHEMA_RESOURCE,
        "hip_fgmres_coarse_context_schema_invalid",
    )
    ready = receipt.status == "context_ready"
    if (
        receipt.schema_version != HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION
        or receipt.evidence_scope
        != HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_EVIDENCE_SCOPE
        or receipt.promotion_eligible is not False
        or not _valid_hash(receipt.context_id)
        or not _valid_hash(receipt.context_receipt_hash)
        or tuple(row.name for row in receipt.owned_buffers) != _OWNED_ROLES
        or receipt.dimensions.parent_capability_count != 3
        or receipt.dimensions.owned_capability_count != 6
        or receipt.dimensions.static_upload_count != 3
        or receipt.dimensions.launches_per_application != 4
        or receipt.allocation_lineage.duplicate_registry_borrow_count != 0
        or receipt.claims.exact_live_parent_delegated is not ready
        or receipt.claims.allocator_provenance_bound is not ready
        or receipt.claims.same_stream_application_ready is not ready
        or receipt.claims.application_host_copy_zero_by_construction is not ready
        or receipt.claims.recurrence_state_machine_integrated
        or receipt.claims.device_status_terminal_bound
        or receipt.claims.iteration_host_copy_zero_proven
        or receipt.claims.asymptotic_o_n_proven
        or receipt.claims.speedup_proven
        or receipt.claims.commercial_ready
        or receipt.claims.promotion_eligible
        or receipt.telemetry.d2h_operation_count != 0
        or receipt.telemetry.fallback_count != 0
    ):
        _fail("hip_fgmres_coarse_context_receipt_invalid", "/receipt")
    payload = _context_receipt_payload(receipt, include_hash=False)
    if receipt.context_receipt_hash != canonical_hash(payload):
        _fail("hip_fgmres_coarse_context_receipt_hash_invalid", "/receipt/hash")
    if expected_context is not None:
        if (
            type(expected_context) is not HipFgmresFixedRankCoarseExecutionContextV1
            or receipt.context_id != expected_context._context_id
            or receipt.bindings is not expected_context._bindings
            or receipt.kernel is not expected_context._kernel_summary
            or receipt.dimensions is not expected_context._dimensions
            or receipt.owned_buffers is not expected_context._owned_buffers
        ):
            _fail("hip_fgmres_coarse_context_receipt_context_invalid", "/receipt")
    return receipt


def _application_receipt_payload(
    receipt: HipFgmresFixedRankCoarseApplicationReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "context_id": receipt.context_id,
        "sequence": receipt.sequence,
        "logical_index": receipt.logical_index,
        "accepted_launch_count": receipt.accepted_launch_count,
        "application_h2d_copy_count": receipt.application_h2d_copy_count,
        "application_d2h_copy_count": receipt.application_d2h_copy_count,
        "application_allocation_count": receipt.application_allocation_count,
        "application_synchronization_count": (
            receipt.application_synchronization_count
        ),
        "application_csr_apply_count": receipt.application_csr_apply_count,
        "promotion_eligible": False,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
    receipt: HipFgmresFixedRankCoarseApplicationReceiptV1,
    *,
    expected_context: HipFgmresFixedRankCoarseExecutionContextV1 | None = None,
) -> HipFgmresFixedRankCoarseApplicationReceiptV1:
    if type(receipt) is not HipFgmresFixedRankCoarseApplicationReceiptV1:
        _fail("hip_fgmres_coarse_application_receipt_invalid", "/receipt")
    _validate_json_schema(
        _application_receipt_payload(receipt, include_hash=True),
        _APPLICATION_SCHEMA_RESOURCE,
        "hip_fgmres_coarse_application_schema_invalid",
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_RECEIPT_V1_SCHEMA_VERSION
        or not _valid_hash(receipt.context_id)
        or type(receipt.sequence) is not int
        or receipt.sequence <= 0
        or type(receipt.logical_index) is not int
        or receipt.logical_index < 0
        or receipt.accepted_launch_count != 4
        or receipt.application_h2d_copy_count != 0
        or receipt.application_d2h_copy_count != 0
        or receipt.application_allocation_count != 0
        or receipt.application_synchronization_count != 0
        or receipt.application_csr_apply_count != 0
        or not _valid_hash(receipt.receipt_hash)
        or receipt.receipt_hash
        != canonical_hash(_application_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_coarse_application_receipt_invalid", "/receipt")
    if expected_context is not None and (
        type(expected_context) is not HipFgmresFixedRankCoarseExecutionContextV1
        or receipt.context_id != expected_context._context_id
        or receipt.logical_index
        >= expected_context._require_dimensions().restart_dimension
    ):
        _fail("hip_fgmres_coarse_application_receipt_context_invalid", "/receipt")
    return receipt


@lru_cache(maxsize=2)
def _schema_validator(resource_name: str) -> Draft202012Validator:
    schema_raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(resource_name)
        .read_bytes()
    )
    schema = json.loads(schema_raw.decode("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_json_schema(
    payload: dict[str, Any],
    resource_name: str,
    code: str,
) -> None:
    errors = sorted(
        _schema_validator(resource_name).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(code, path or "/", errors[0].message)


def _pointer_value(value: object) -> int:
    if type(value) is int:
        pointer = value
    elif type(value) is ctypes.c_void_p:
        pointer = value.value
    else:
        pointer = id(value)
    if type(pointer) is not int or pointer <= 0:
        _fail("hip_fgmres_coarse_context_pointer_invalid", "/stream")
    return pointer


def _free_outcome_uncertain(error: BaseException) -> bool:
    """Only the dedicated error proves that an external free did not occur."""

    return type(error) is not HipFreeKnownNotFreedError


def _valid_hash(value: object) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _detail(value: object) -> str:
    text = str(value).replace("\n", " ").strip()
    return text[:512] if text else type(value).__name__


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresFixedRankCoarseExecutionContextV1 | None = None,
) -> None:
    raise HipFgmresFixedRankCoarseContextV1Error(
        code,
        path,
        message,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_RECEIPT_V1_SCHEMA_VERSION",
    "HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_CAPABILITY_PROFILE",
    "HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_EVIDENCE_SCOPE",
    "HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION",
    "HipFgmresFixedRankCoarseApplicationReceiptV1",
    "HipFgmresFixedRankCoarseBindingsV1",
    "HipFgmresFixedRankCoarseBufferV1",
    "HipFgmresFixedRankCoarseClaimsV1",
    "HipFgmresFixedRankCoarseContextOpenResultV1",
    "HipFgmresFixedRankCoarseContextReceiptV1",
    "HipFgmresFixedRankCoarseContextV1Error",
    "HipFgmresFixedRankCoarseDimensionsV1",
    "HipFgmresFixedRankCoarseExecutionContextV1",
    "HipFgmresFixedRankCoarseKernelV1",
    "HipFgmresFixedRankCoarseLineageV1",
    "HipFgmresFixedRankCoarseReasonV1",
    "HipFgmresFixedRankCoarseTelemetryV1",
    "open_hip_fgmres_fixed_rank_coarse_context_v1",
    "validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1",
    "validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1",
]
