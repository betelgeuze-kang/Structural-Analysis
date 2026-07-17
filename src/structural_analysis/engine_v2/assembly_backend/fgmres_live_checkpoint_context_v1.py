"""Allocator-backed live owner for the FGMRES checkpoint buffer projection.

This first walking slice owns lifetime only.  It binds the exact live Krylov
parent, borrows FreeSpace ``reduced_state``/``reduced_load`` and the prepared
Krylov ``jacobi_inverse``, allocates the eight checkpoint-owned buffers, and
holds one exact eleven-capability allocation lease plus one recurrence-v2 RTC
module lease.  It deliberately exposes no launch or predecessor API.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.context import (
    HipFreeKnownNotFreedError,
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_plan import HipFgmresPlanV1, validate_hip_fgmres_plan_v1
from .fgmres_recurrence_plan_v2 import (
    HipFgmresRecurrencePlanV2,
    validate_hip_fgmres_recurrence_plan_v2,
)
from .fgmres_rtc_v2 import (
    HipRtcFgmresV2Kernel,
    _HipRtcFgmresV2KernelHandoff,
    _HipRtcFgmresV2ModuleCleanupOwner,
    _compile_v2_with_handoff,
    _validate_identity,
    compile_hip_rtc_fgmres_v2_kernel,
)
from .free_space import HipFreeSpaceApplyReceipt
from .hip_allocation_lineage import (
    HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
    HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
    HipAllocationBorrowLeaseV1,
    HipAllocationCapabilityV1,
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
    borrow_hip_allocations_v1,
    open_hip_allocation_peer_owner_v1,
    recover_hip_allocation_borrow_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_capability_v1,
    validate_hip_allocation_owner_v1,
)
from .krylov_primitives import HipKrylovPrimitivesExecutionContext


HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-live-checkpoint-context.v1"
)
HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_CAPABILITY_PROFILE_V1 = (
    "phase0_live_fgmres_checkpoint_resource_owner"
)
HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_EVIDENCE_SCOPE_V1 = (
    "allocator_bound_live_checkpoint_resources_non_promoting"
)

LiveCheckpointStatusV1 = Literal[
    "context_ready",
    "context_closed",
    "cleanup_failed",
    "cleanup_quarantined",
    "unavailable",
]
CleanupDisposition = Literal[
    "live",
    "free_call_inflight",
    "external_free_succeeded",
    "quarantine_pending",
    "terminal",
]

_OWNED_ROLES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_PARENT_ROLES = ("reduced_state", "reduced_load", "jacobi_inverse")
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HEX_ADDRESS_RE = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_DECIMAL_HANDLE_RE = re.compile(
    r"(?i)\b(?:pointer|ptr|handle|stream|module|function|device_address)\s*[=:]\s*\d+\b"
)
_SCHEMA_RESOURCE = "hip_fgmres_live_checkpoint_context_v1.schema.json"


class HipFgmresLiveCheckpointContextV1Error(RuntimeError):
    """Stable fail-closed error with an optional retryable cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresLiveCheckpointExecutionContextV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointBindingsV1:
    primitive_context_id: str
    primitive_opening_receipt_hash: str
    primitive_evidence_scope: str
    primitive_actual_backend: Literal["hip", "test_double"]
    source_apply_id: str
    source_apply_receipt_hash: str
    source_apply_sequence: int
    source_direction_generation: int
    source_execution_plan_hash: str
    source_free_space_plan_hash: str
    source_state_hash: str
    source_state_epoch: int
    source_fgmres_plan_hash: str
    recurrence_plan_id: str
    recurrence_plan_hash: str
    recurrence_memory_layout_hash: str
    recurrence_kernel_abi_hash: str
    primitive_parent_lease_epoch: int
    solver_child_lease_epoch: int
    allocation_generation_binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    parent_capability_count: Literal[3] = 3
    solver_owned_capability_count: Literal[8] = 8
    atomic_group_capability_count: Literal[11] = 11

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointBufferV1:
    name: str
    dtype: Literal["<f8", "|u1"]
    shape: tuple[int, ...]
    element_count: int
    byte_length: int
    access: str
    initialization: str
    extent_formula: str

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
            "extent_formula": self.extent_formula,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointKernelV1:
    architecture: str
    identity_hash: str
    source_sha256: str
    code_object_sha256: str
    kernel_interface_hash: str
    runtime_library_sha256: str
    runtime_library_discovery_source: str
    hiprtc_library_sha256: str
    hiprtc_library_discovery_source: str
    kernel_origin: Literal["internally_compiled", "caller_supplied"]

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointLineageV1:
    capability_profile: Literal["foundation_non_promoting"]
    evidence_scope: Literal["foundation_non_promoting"]
    owner_role: Literal["fgmres_checkpoint_owned_buffers"]
    runtime_device_bound: bool
    same_stream_bound: bool
    parent_borrowed_capability_count: int
    managed_buffer_count: int
    managed_device_bytes: int
    atomic_group_capability_count: int
    all_owned_buffers_managed: bool
    pointer_values_serialized: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointTelemetryV1:
    allocation_attempt_count: int = 0
    allocation_success_count: int = 0
    deallocation_attempt_count: int = 0
    deallocation_success_count: int = 0
    current_device_bytes: int = 0
    peak_device_bytes: int = 0
    lineage_owner_open_success_count: int = 0
    lineage_owner_close_success_count: int = 0
    lineage_capability_mint_success_count: int = 0
    lineage_capability_mint_bytes: int = 0
    lineage_free_acknowledgement_count: int = 0
    lineage_free_quarantine_count: int = 0
    lineage_orphan_acknowledgement_count: int = 0
    lineage_orphan_quarantine_count: int = 0
    quarantined_device_bytes: int = 0
    unknown_malloc_outcome_count: int = 0
    unknown_requested_bytes: int = 0
    module_owner_acquire_success_count: int = 0
    module_close_attempt_count: int = 0
    module_close_success_count: int = 0
    checkpoint_token_acquire_success_count: int = 0
    checkpoint_token_release_success_count: int = 0
    group_borrow_acquire_success_count: int = 0
    group_borrow_release_attempt_count: int = 0
    group_borrow_release_success_count: int = 0
    semantic_lease_acquire_success_count: int = 0
    semantic_lease_release_attempt_count: int = 0
    semantic_lease_release_success_count: int = 0
    h2d_operation_count: Literal[0] = 0
    d2h_operation_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointClaimsV1:
    live_krylov_parent_integrated: bool
    allocator_provenance_bound: bool
    resource_owner_ready: bool
    owned_content_initialized: Literal[False] = False
    authoritative_predecessor_proven: Literal[False] = False
    device_mask_domain_validator_bound: Literal[False] = False
    actual_mask_host_observed: Literal[False] = False
    checkpoint_transaction_ready: Literal[False] = False
    live_solver_ready: Literal[False] = False
    solution_ready: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    asymptotic_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointContextReceiptV1:
    status: LiveCheckpointStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"] | None
    promotion_eligible: Literal[False]
    reason: HipFgmresLiveCheckpointReasonV1 | None
    bindings: HipFgmresLiveCheckpointBindingsV1
    kernel: HipFgmresLiveCheckpointKernelV1 | None
    dimensions: HipFgmresLiveCheckpointDimensionsV1
    owned_buffers: tuple[HipFgmresLiveCheckpointBufferV1, ...]
    allocation_lineage: HipFgmresLiveCheckpointLineageV1
    telemetry: HipFgmresLiveCheckpointTelemetryV1
    claims: HipFgmresLiveCheckpointClaimsV1
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresLiveCheckpointContextOpenResultV1:
    context: HipFgmresLiveCheckpointExecutionContextV1 | None
    receipt: HipFgmresLiveCheckpointContextReceiptV1

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresFixedRankCoarseParentAuthorityV1:
    """Non-serializable authority for one exact live coarse child.

    The live checkpoint context already owns the exclusive allocation-registry
    borrow for ``jacobi_inverse``, ``basis_v``, and
    ``preconditioned_basis_z``.  A coarse child therefore receives a semantic
    delegation of those exact capabilities instead of attempting an invalid
    second registry borrow.
    """

    live_context: HipFgmresLiveCheckpointExecutionContextV1
    child_context: object
    child_token: object
    child_epoch: int
    live_context_id: str
    live_opening_receipt_hash: str
    recurrence_plan: HipFgmresRecurrencePlanV2
    source_plan: HipFgmresPlanV1
    runtime: object
    loaded_runtime: object
    stream: object
    architecture: str
    device_ordinal: int
    allocation_owner: HipAllocationOwnerV1
    allocation_runtime_domain: object
    allocation_runtime_domain_id: str
    parent_group_lease: HipAllocationBorrowLeaseV1
    source_capabilities: tuple[
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
    ]
    actual_backend: Literal["hip", "test_double"]


@dataclass(slots=True)
class _OrphanCleanup:
    lease: HipAllocationOrphanLeaseV1
    byte_length: int
    pointer: object | None
    must_quarantine: bool
    disposition: CleanupDisposition = "live"


class HipFgmresLiveCheckpointExecutionContextV1:
    """Exclusive process-local owner of the live checkpoint resource slice."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Live FGMRES checkpoint contexts are factory-issued only.")
        self._queue_lock = threading.RLock()
        self._parent: HipKrylovPrimitivesExecutionContext | None = None
        self._source_apply: HipFreeSpaceApplyReceipt | None = None
        self._recurrence_plan: HipFgmresRecurrencePlanV2 | None = None
        self._source_plan: HipFgmresPlanV1 | None = None
        self._token = object()
        self._checkpoint_token = object()
        self._parent_capabilities: tuple[HipAllocationCapabilityV1, ...] = ()
        self._group_capabilities: tuple[HipAllocationCapabilityV1, ...] = ()
        self._group_lease: HipAllocationBorrowLeaseV1 | None = None
        self._allocation_owner: HipAllocationOwnerV1 | None = None
        self._owned_capabilities: dict[str, HipAllocationCapabilityV1] = {}
        self._pending_free_leases: dict[str, HipAllocationFreeLeaseV1] = {}
        self._cleanup_dispositions: dict[str, CleanupDisposition] = {}
        self._orphan_cleanups: list[_OrphanCleanup] = []
        self._owned_buffers: tuple[HipFgmresLiveCheckpointBufferV1, ...] = ()
        self._kernel: (
            HipRtcFgmresV2Kernel | _HipRtcFgmresV2ModuleCleanupOwner | None
        ) = None
        self._kernel_binding_snapshot: tuple[Any, ...] | None = None
        self._kernel_summary: HipFgmresLiveCheckpointKernelV1 | None = None
        self._kernel_origin: (
            Literal["internally_compiled", "caller_supplied"] | None
        ) = None
        self._primitive_opening_receipt: Any | None = None
        self._actual_backend: Literal["hip", "test_double"] | None = None
        self._runtime: object | None = None
        self._loaded_runtime: object | None = None
        self._stream: object | None = None
        self._stream_pointer_snapshot: int | None = None
        self._device_ordinal: int | None = None
        self._architecture: str | None = None
        self._context_id = _ZERO_HASH
        self._bindings: HipFgmresLiveCheckpointBindingsV1 | None = None
        self._dimensions: HipFgmresLiveCheckpointDimensionsV1 | None = None
        self._telemetry = HipFgmresLiveCheckpointTelemetryV1()
        self._opening_receipt: HipFgmresLiveCheckpointContextReceiptV1 | None = None
        self._failure_reason: HipFgmresLiveCheckpointReasonV1 | None = None
        self._closed = False
        self._cleanup_failed = False
        self._cleanup_quarantined = False
        self._kernel_closed = False
        self._group_released = False
        self._owner_closed = False
        self._semantic_released = False
        self._canonical_predecessor_child_token: object | None = None
        self._canonical_predecessor_child_terminal = False
        self._fixed_rank_coarse_child_token: object | None = None
        self._fixed_rank_coarse_child_context: object | None = None
        self._fixed_rank_coarse_child_epoch = 0
        self._fixed_rank_coarse_overlay_token: object | None = None
        self._fixed_rank_coarse_overlay_context: object | None = None
        self._fixed_rank_coarse_overlay_coarse_context: object | None = None
        self._fixed_rank_coarse_overlay_deferred_poison_detail: str | None = None
        self._closing = False

    @property
    def opening_receipt(self) -> HipFgmresLiveCheckpointContextReceiptV1:
        receipt = self._opening_receipt
        if receipt is None:
            raise HipFgmresLiveCheckpointContextV1Error(
                "hip_fgmres_live_checkpoint_opening_receipt_unavailable", "/status"
            )
        return receipt

    @property
    def closed(self) -> bool:
        return self._closed

    def receipt(self) -> HipFgmresLiveCheckpointContextReceiptV1:
        with self._queue_lock:
            if self._cleanup_failed:
                status: LiveCheckpointStatusV1 = "cleanup_failed"
            elif self._cleanup_quarantined:
                status = "cleanup_quarantined"
            elif self._closed:
                status = "context_closed"
            else:
                status = "context_ready"
            return self._build_receipt(status)

    def close(self) -> None:
        with self._queue_lock:
            if self._closed:
                return
            if self._canonical_predecessor_child_token is not None:
                _fail(
                    "hip_fgmres_live_checkpoint_canonical_child_active",
                    "/lifetime/canonical_predecessor_child",
                )
            if self._fixed_rank_coarse_child_token is not None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_child_active",
                    "/lifetime/fixed_rank_coarse_child",
                )
            if self._fixed_rank_coarse_overlay_token is not None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_active",
                    "/lifetime/fixed_rank_coarse_overlay",
                )
            if self._closing:
                _fail("hip_fgmres_live_checkpoint_cleanup_reentrant", "/cleanup")
            self._closing = True
            try:
                self._flush_fixed_rank_coarse_overlay_deferred_poison()
                self._close_locked()
            finally:
                self._closing = False

    def _reserve_canonical_predecessor_child(self, token: object) -> object:
        """Reserve the sole producer child without changing resource evidence."""

        if type(token) is not object:
            _fail(
                "hip_fgmres_live_checkpoint_canonical_child_token_invalid",
                "/lifetime/canonical_predecessor_child",
            )
        with self._queue_lock:
            if (
                self._closed
                or self._closing
                or self._canonical_predecessor_child_terminal
                or self._canonical_predecessor_child_token is not None
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_canonical_child_unavailable",
                    "/lifetime/canonical_predecessor_child",
                )
            self._validate_authority()
            self._canonical_predecessor_child_token = token
            return token

    def _require_canonical_predecessor_child(self, token: object) -> None:
        with self._queue_lock:
            if token is not self._canonical_predecessor_child_token:
                _fail(
                    "hip_fgmres_live_checkpoint_canonical_child_token_invalid",
                    "/lifetime/canonical_predecessor_child",
                )
            if self._closed or self._closing:
                _fail(
                    "hip_fgmres_live_checkpoint_canonical_child_unavailable",
                    "/lifetime/canonical_predecessor_child",
                )

    def _release_canonical_predecessor_child(self, token: object) -> None:
        with self._queue_lock:
            self._require_canonical_predecessor_child(token)
            kernel = self._kernel
            if (
                type(kernel) is not HipRtcFgmresV2Kernel
                or kernel.pending_stream_count != 0
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_canonical_child_fence_required",
                    "/lifetime/canonical_predecessor_child",
                )
            self._canonical_predecessor_child_terminal = True
            self._canonical_predecessor_child_token = None

    def _reserve_fixed_rank_coarse_child(
        self,
        token: object,
        child_context: object,
    ) -> object:
        """Reserve one non-owning coarse child beside the recurrence chain."""

        if type(token) is not object or child_context is None:
            _fail(
                "hip_fgmres_live_checkpoint_coarse_child_token_invalid",
                "/lifetime/fixed_rank_coarse_child",
            )
        with self._queue_lock:
            if (
                self._closed
                or self._closing
                or self._fixed_rank_coarse_overlay_deferred_poison_detail is not None
                or self._fixed_rank_coarse_child_token is not None
                or self._fixed_rank_coarse_child_context is not None
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_child_unavailable",
                    "/lifetime/fixed_rank_coarse_child",
                )
            self._validate_authority()
            self._fixed_rank_coarse_child_epoch += 1
            self._fixed_rank_coarse_child_token = token
            self._fixed_rank_coarse_child_context = child_context
            return token

    def _require_fixed_rank_coarse_child(
        self,
        token: object,
        child_context: object,
    ) -> None:
        with self._queue_lock:
            if (
                token is not self._fixed_rank_coarse_child_token
                or child_context is not self._fixed_rank_coarse_child_context
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_child_token_invalid",
                    "/lifetime/fixed_rank_coarse_child",
                )
            if self._closed or self._closing:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_child_unavailable",
                    "/lifetime/fixed_rank_coarse_child",
                )

    def _fixed_rank_coarse_child_token_is_active(
        self,
        token: object,
        child_context: object,
    ) -> bool:
        """Return whether the exact process-local child lease is still active."""

        with self._queue_lock:
            return (
                token is self._fixed_rank_coarse_child_token
                and child_context is self._fixed_rank_coarse_child_context
            )

    def _fixed_rank_coarse_child_authority(
        self,
        token: object,
        child_context: object,
        *,
        overlay_token: object | None = None,
        overlay_context: object | None = None,
        pending_operation_bounds: tuple[int, int] = (0, 0),
    ) -> _HipFgmresFixedRankCoarseParentAuthorityV1:
        """Issue the exact parent-three projection for one live coarse child."""

        with self._queue_lock:
            self._require_fixed_rank_coarse_child(token, child_context)
            if overlay_token is None and overlay_context is None:
                self._validate_authority()
            elif overlay_token is not None and overlay_context is not None:
                self._require_fixed_rank_coarse_overlay(
                    overlay_token,
                    overlay_context,
                )
                _context_validate_authority_common(
                    self,
                    canonical_child_token=None,
                    pending_operation_bounds=pending_operation_bounds,
                    force_leased_pending_snapshot=True,
                )
            else:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_authority_invalid",
                    "/lifetime/fixed_rank_coarse_overlay/authority",
                )
            if (
                self._recurrence_plan is None
                or self._source_plan is None
                or self._runtime is None
                or self._loaded_runtime is None
                or self._stream is None
                or self._architecture is None
                or self._device_ordinal is None
                or self._allocation_owner is None
                or self._group_lease is None
                or self._opening_receipt is None
                or self._actual_backend not in {"hip", "test_double"}
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_authority_invalid",
                    "/lifetime/fixed_rank_coarse_child/authority",
                )
            try:
                capabilities = (
                    self._group_capabilities[2],
                    self._owned_capabilities["basis_v"],
                    self._owned_capabilities["preconditioned_basis_z"],
                )
            except (IndexError, KeyError) as exc:
                raise HipFgmresLiveCheckpointContextV1Error(
                    "hip_fgmres_live_checkpoint_coarse_authority_invalid",
                    "/lifetime/fixed_rank_coarse_child/authority/capabilities",
                    type(exc).__name__,
                ) from exc
            if tuple(row.role for row in capabilities) != (
                "jacobi_inverse",
                "basis_v",
                "preconditioned_basis_z",
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_authority_invalid",
                    "/lifetime/fixed_rank_coarse_child/authority/capabilities",
                )
            for capability in capabilities:
                validate_hip_allocation_capability_v1(capability)
            return _HipFgmresFixedRankCoarseParentAuthorityV1(
                live_context=self,
                child_context=child_context,
                child_token=token,
                child_epoch=self._fixed_rank_coarse_child_epoch,
                live_context_id=self._context_id,
                live_opening_receipt_hash=(self._opening_receipt.context_receipt_hash),
                recurrence_plan=self._recurrence_plan,
                source_plan=self._source_plan,
                runtime=self._runtime,
                loaded_runtime=self._loaded_runtime,
                stream=self._stream,
                architecture=self._architecture,
                device_ordinal=self._device_ordinal,
                allocation_owner=self._allocation_owner,
                allocation_runtime_domain=capabilities[0].runtime_domain,
                allocation_runtime_domain_id=capabilities[0].runtime_domain_id,
                parent_group_lease=self._group_lease,
                source_capabilities=capabilities,
                actual_backend=self._actual_backend,
            )

    def _release_fixed_rank_coarse_child(
        self,
        token: object,
        child_context: object,
    ) -> None:
        """Release the semantic delegation after the coarse child is terminal."""

        with self._queue_lock:
            self._require_fixed_rank_coarse_child(token, child_context)
            self._fixed_rank_coarse_child_token = None
            self._fixed_rank_coarse_child_context = None

    def _poison_fixed_rank_coarse_child(
        self,
        token: object,
        child_context: object,
        detail: str,
    ) -> None:
        """Propagate uncertain same-stream coarse work to the solver chain."""

        with self._queue_lock:
            self._require_fixed_rank_coarse_child(token, child_context)
            if self._parent is None or self._source_apply is None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_authority_invalid",
                    "/lifetime/fixed_rank_coarse_child/authority",
                )
            if (
                self._fixed_rank_coarse_overlay_token is not None
                and self._fixed_rank_coarse_overlay_context is not None
                and self._fixed_rank_coarse_overlay_coarse_context is child_context
            ):
                # The integrated recurrence owners still need an unpoisoned
                # semantic parent long enough to return their exact leases.
                # Their own state machines and the coarse/overlay contexts are
                # poisoned immediately; publish the shared primitive poison
                # only once every recurrence/coarse child has been released
                # and the live context begins terminal cleanup.
                if self._fixed_rank_coarse_overlay_deferred_poison_detail is None:
                    self._fixed_rank_coarse_overlay_deferred_poison_detail = _detail(
                        detail
                    )
                return
            self._parent._poison_fgmres_solver_child(
                self._token,
                self._source_apply,
                _detail(detail),
            )

    def _flush_fixed_rank_coarse_overlay_deferred_poison(self) -> None:
        detail = self._fixed_rank_coarse_overlay_deferred_poison_detail
        if detail is None:
            return
        if self._parent is None or self._source_apply is None:
            _fail(
                "hip_fgmres_live_checkpoint_coarse_authority_invalid",
                "/lifetime/fixed_rank_coarse_overlay/deferred_poison",
            )
        self._parent._poison_fgmres_solver_child(
            self._token,
            self._source_apply,
            detail,
        )
        self._fixed_rank_coarse_overlay_deferred_poison_detail = None

    def _reserve_fixed_rank_coarse_overlay(
        self,
        token: object,
        overlay_context: object,
        coarse_context: object,
    ) -> object:
        """Register one exact same-stream recurrence overlay route."""

        if (
            type(token) is not object
            or overlay_context is None
            or coarse_context is None
        ):
            _fail(
                "hip_fgmres_live_checkpoint_coarse_overlay_token_invalid",
                "/lifetime/fixed_rank_coarse_overlay",
            )
        with self._queue_lock:
            if (
                self._closed
                or self._closing
                or self._fixed_rank_coarse_overlay_token is not None
                or self._fixed_rank_coarse_overlay_context is not None
                or coarse_context is not self._fixed_rank_coarse_child_context
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_unavailable",
                    "/lifetime/fixed_rank_coarse_overlay",
                )
            self._validate_authority()
            self._fixed_rank_coarse_overlay_token = token
            self._fixed_rank_coarse_overlay_context = overlay_context
            self._fixed_rank_coarse_overlay_coarse_context = coarse_context
            return token

    def _require_fixed_rank_coarse_overlay(
        self,
        token: object,
        overlay_context: object,
    ) -> None:
        if (
            token is not self._fixed_rank_coarse_overlay_token
            or overlay_context is not self._fixed_rank_coarse_overlay_context
            or self._fixed_rank_coarse_overlay_coarse_context
            is not self._fixed_rank_coarse_child_context
            or self._closed
            or self._closing
        ):
            _fail(
                "hip_fgmres_live_checkpoint_coarse_overlay_token_invalid",
                "/lifetime/fixed_rank_coarse_overlay",
            )

    def _enqueue_fixed_rank_coarse_overlay_after_jacobi(
        self,
        *,
        phase: str,
        owner: object,
        expected_restart: int,
        expected_column: int,
        logical_index: int,
    ) -> object | None:
        """Invoke the registered overlay immediately after one Jacobi row."""

        with self._queue_lock:
            overlay = self._fixed_rank_coarse_overlay_context
            token = self._fixed_rank_coarse_overlay_token
            if overlay is None and token is None:
                return None
            if overlay is None or token is None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_invalid",
                    "/lifetime/fixed_rank_coarse_overlay",
                )
            self._require_fixed_rank_coarse_overlay(token, overlay)
            return overlay._enqueue_after_jacobi(  # type: ignore[attr-defined]
                token,
                self,
                phase=phase,
                owner=owner,
                expected_restart=expected_restart,
                expected_column=expected_column,
                logical_index=logical_index,
            )

    def _acknowledge_fixed_rank_coarse_overlay_fence(
        self,
        *,
        phase: str,
        owner: object,
    ) -> int:
        """Forward an already-observed exact-stream fence to the overlay."""

        with self._queue_lock:
            overlay = self._fixed_rank_coarse_overlay_context
            token = self._fixed_rank_coarse_overlay_token
            if overlay is None and token is None:
                return 0
            if overlay is None or token is None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_invalid",
                    "/lifetime/fixed_rank_coarse_overlay",
                )
            self._require_fixed_rank_coarse_overlay(token, overlay)
            return int(
                overlay._acknowledge_parent_fence(  # type: ignore[attr-defined]
                    token,
                    self,
                    phase=phase,
                    owner=owner,
                )
            )

    def _publish_fixed_rank_coarse_overlay_global_receipt(
        self,
        *,
        owner: object,
        receipt: object,
    ) -> None:
        """Bind the final global receipt after its completion publication."""

        with self._queue_lock:
            overlay = self._fixed_rank_coarse_overlay_context
            token = self._fixed_rank_coarse_overlay_token
            if overlay is None and token is None:
                return
            if overlay is None or token is None:
                _fail(
                    "hip_fgmres_live_checkpoint_coarse_overlay_invalid",
                    "/lifetime/fixed_rank_coarse_overlay",
                )
            self._require_fixed_rank_coarse_overlay(token, overlay)
            overlay._bind_global_recurrence_receipt(  # type: ignore[attr-defined]
                token,
                self,
                owner=owner,
                receipt=receipt,
            )

    def _release_fixed_rank_coarse_overlay(
        self,
        token: object,
        overlay_context: object,
    ) -> None:
        """Release the route after the overlay child becomes terminal."""

        with self._queue_lock:
            self._require_fixed_rank_coarse_overlay(token, overlay_context)
            self._fixed_rank_coarse_overlay_token = None
            self._fixed_rank_coarse_overlay_context = None
            self._fixed_rank_coarse_overlay_coarse_context = None

    def _adopt_allocation_owner(self, owner: HipAllocationOwnerV1 | None) -> None:
        if owner is None:
            return
        if type(owner) is not HipAllocationOwnerV1:
            _fail(
                "hip_fgmres_live_checkpoint_owner_handoff_invalid",
                "/cleanup/allocation_owner",
            )
        if self._allocation_owner is not None and self._allocation_owner is not owner:
            _fail(
                "hip_fgmres_live_checkpoint_owner_handoff_changed",
                "/cleanup/allocation_owner",
            )
        self._allocation_owner = owner
        validate_hip_allocation_owner_v1(owner)
        self._telemetry = replace(
            self._telemetry,
            lineage_owner_open_success_count=1,
        )

    def _adopt_kernel_owner(
        self,
        owner: HipRtcFgmresV2Kernel | _HipRtcFgmresV2ModuleCleanupOwner | None,
    ) -> None:
        if owner is None:
            return
        if type(owner) not in {
            HipRtcFgmresV2Kernel,
            _HipRtcFgmresV2ModuleCleanupOwner,
        }:
            _fail(
                "hip_fgmres_live_checkpoint_kernel_handoff_invalid",
                "/cleanup/kernel",
            )
        if self._kernel is not None and self._kernel is not owner:
            _fail(
                "hip_fgmres_live_checkpoint_kernel_handoff_changed",
                "/cleanup/kernel",
            )
        self._kernel = owner
        self._telemetry = replace(
            self._telemetry,
            module_owner_acquire_success_count=1,
        )
        if type(owner) is HipRtcFgmresV2Kernel:
            origin = self._kernel_origin
            if origin is None:
                _fail(
                    "hip_fgmres_live_checkpoint_kernel_origin_missing",
                    "/kernel/kernel_origin",
                )
            self._kernel_summary = _kernel_summary(owner, origin)
            parent_receipt = self._primitive_opening_receipt
            if parent_receipt is None:
                _fail(
                    "hip_fgmres_live_checkpoint_parent_receipt_missing",
                    "/bindings/primitive_opening_receipt_hash",
                )
            self._actual_backend = _derive_actual_backend(
                parent_receipt,
                owner,
                origin,
            )

    def _recover_checkpoint_authority(self) -> None:
        kernel = self._kernel
        if type(kernel) is not HipRtcFgmresV2Kernel or kernel.closed:
            return
        try:
            runtime_owner = kernel._checkpoint_runtime_owner(self._checkpoint_token)
            binding_snapshot = kernel._checkpoint_binding_snapshot(
                self._checkpoint_token
            )
        except Exception as exc:
            if getattr(exc, "code", "") == (
                "hip_rtc_fgmres_v2_checkpoint_lease_token_invalid"
            ):
                return
            raise
        if runtime_owner is not self._loaded_runtime:
            _fail(
                "hip_fgmres_live_checkpoint_kernel_runtime_mismatch",
                "/kernel/runtime",
            )
        self._kernel_binding_snapshot = binding_snapshot
        self._telemetry = replace(
            self._telemetry,
            checkpoint_token_acquire_success_count=1,
        )

    def _recover_semantic_authority(self) -> None:
        parent = self._parent
        if parent is None:
            return
        if parent._fgmres_solver_child_token is self._token:
            self._telemetry = replace(
                self._telemetry,
                semantic_lease_acquire_success_count=1,
            )

    def _recover_allocation_cleanup_snapshot(self, *, opening: bool) -> None:
        owner = self._allocation_owner
        if owner is None or self._owner_closed:
            return
        capabilities, free_leases, orphan_leases = owner.cleanup_snapshot()
        views = {view.name: view for view in self._owned_buffers}
        for capability in capabilities:
            validate_hip_allocation_capability_v1(
                capability,
                expected_owner=owner,
            )
            view = views.get(capability.role)
            if view is None or any(
                (
                    capability.nbytes != view.byte_length,
                    capability.element_type != ("f64" if view.dtype == "<f8" else "u8"),
                    capability.runtime_owner is not self._runtime,
                    capability.device_ordinal != self._device_ordinal,
                )
            ):
                _fail(
                    "hip_fgmres_live_checkpoint_allocation_recovery_invalid",
                    f"/cleanup/owned_buffers/{capability.role}",
                )
            current = self._owned_capabilities.get(capability.role)
            if current is not None and current is not capability:
                _fail(
                    "hip_fgmres_live_checkpoint_allocation_recovery_changed",
                    f"/cleanup/owned_buffers/{capability.role}",
                )
            self._owned_capabilities[capability.role] = capability
            self._cleanup_dispositions.setdefault(capability.role, "live")
        for lease in free_leases:
            capability = lease.capability
            current_capability = self._owned_capabilities.get(capability.role)
            if current_capability is not capability:
                _fail(
                    "hip_fgmres_live_checkpoint_free_lease_recovery_invalid",
                    f"/cleanup/owned_buffers/{capability.role}",
                )
            current_lease = self._pending_free_leases.get(capability.role)
            if current_lease is not None and current_lease is not lease:
                _fail(
                    "hip_fgmres_live_checkpoint_free_lease_recovery_changed",
                    f"/cleanup/owned_buffers/{capability.role}",
                )
            self._pending_free_leases[capability.role] = lease
        known_orphans = {id(cleanup.lease) for cleanup in self._orphan_cleanups}
        for lease in orphan_leases:
            if id(lease) in known_orphans:
                continue
            if lease.role not in views:
                _fail(
                    "hip_fgmres_live_checkpoint_orphan_recovery_invalid",
                    "/cleanup/allocation_lineage/orphan",
                )
            self._orphan_cleanups.append(
                _OrphanCleanup(
                    lease,
                    lease.nbytes,
                    lease.base,
                    lease.pointer_snapshot is None,
                )
            )
            known_orphans.add(id(lease))
        if opening:
            pointerful_orphans = tuple(
                cleanup
                for cleanup in self._orphan_cleanups
                if cleanup.pointer is not None
            )
            managed_bytes = sum(row.nbytes for row in capabilities) + sum(
                row.byte_length for row in pointerful_orphans
            )
            self._telemetry = replace(
                self._telemetry,
                allocation_success_count=(len(capabilities) + len(pointerful_orphans)),
                current_device_bytes=managed_bytes,
                peak_device_bytes=max(
                    self._telemetry.peak_device_bytes,
                    managed_bytes,
                ),
                lineage_capability_mint_success_count=len(capabilities),
                lineage_capability_mint_bytes=sum(row.nbytes for row in capabilities),
            )

    def _recover_group_borrow(self) -> None:
        capabilities = self._group_capabilities
        if self._parent is None or self._source_apply is None:
            if not capabilities:
                return
            _fail(
                "hip_fgmres_live_checkpoint_group_recovery_invalid",
                "/cleanup/allocation_lineage/group_borrow",
            )
        phase = self._parent._fgmres_solver_child_phase
        if not capabilities:
            if phase == "semantic_reserved":
                self._parent._recover_fgmres_solver_child_allocation_borrow(self._token)
                if self._parent._fgmres_solver_child_phase != "semantic_cleanup_active":
                    _fail(
                        "hip_fgmres_live_checkpoint_group_recovery_invalid",
                        "/cleanup/allocation_lineage/group_borrow",
                    )
            return
        lease = self._group_lease
        if lease is None:
            lease = recover_hip_allocation_borrow_v1(capabilities, self._token)
            if lease is None:
                if phase == "semantic_reserved":
                    self._parent._recover_fgmres_solver_child_allocation_borrow(
                        self._token,
                        capabilities,
                    )
                    if (
                        self._parent._fgmres_solver_child_phase
                        != "semantic_cleanup_active"
                    ):
                        _fail(
                            "hip_fgmres_live_checkpoint_group_recovery_invalid",
                            "/cleanup/allocation_lineage/group_borrow",
                        )
                return
            self._group_lease = lease
        phase = self._parent._fgmres_solver_child_phase
        try:
            validate_hip_allocation_borrow_v1(lease)
        except HipAllocationLineageError as exc:
            if (
                exc.code == "hip_allocation_borrow_released"
                and phase == "semantic_cleanup_active"
            ):
                self._group_released = True
                self._telemetry = replace(
                    self._telemetry,
                    group_borrow_acquire_success_count=1,
                    group_borrow_release_attempt_count=max(
                        1,
                        self._telemetry.group_borrow_release_attempt_count,
                    ),
                    group_borrow_release_success_count=1,
                )
                return
            raise
        if phase == "semantic_reserved":
            committed = self._parent._commit_fgmres_solver_child_allocation_borrow(
                self._token,
                self._source_apply,
                capabilities,
                lease,
            )
            if committed is not self._token:
                _fail(
                    "hip_fgmres_live_checkpoint_group_recovery_changed",
                    "/cleanup/allocation_lineage/group_borrow",
                )
        elif phase != "active":
            _fail(
                "hip_fgmres_live_checkpoint_group_recovery_invalid",
                "/cleanup/allocation_lineage/group_borrow",
            )
        self._telemetry = replace(
            self._telemetry,
            group_borrow_acquire_success_count=1,
        )

    def _close_locked(self) -> None:
        try:
            self._recover_semantic_authority()
            self._recover_allocation_cleanup_snapshot(opening=False)
            self._recover_checkpoint_authority()
            self._close_kernel()
            self._release_group_only()
            for name in reversed(_OWNED_ROLES):
                error = self._retire_owned(name)
                if error is not None:
                    self._raise_cleanup(
                        "hip_fgmres_live_checkpoint_allocation_cleanup_failed",
                        f"/cleanup/owned_buffers/{name}",
                        error,
                    )
            for orphan in tuple(reversed(self._orphan_cleanups)):
                error = self._retire_orphan(orphan)
                if error is not None:
                    self._raise_cleanup(
                        "hip_fgmres_live_checkpoint_orphan_cleanup_failed",
                        "/cleanup/allocation_lineage/orphan",
                        error,
                    )
            if not self._owner_closed and self._allocation_owner is not None:
                try:
                    self._allocation_owner.close(_control_token=self._token)
                except Exception as exc:
                    self._raise_cleanup(
                        "hip_fgmres_live_checkpoint_owner_close_failed",
                        "/cleanup/allocation_owner",
                        exc,
                    )
                self._owner_closed = True
                self._telemetry = replace(
                    self._telemetry,
                    lineage_owner_close_success_count=1,
                )
            self._release_semantic_last()
            self._cleanup_failed = False
            self._closed = True
            self._failure_reason = (
                HipFgmresLiveCheckpointReasonV1(
                    "hip_fgmres_live_checkpoint_cleanup_quarantined",
                    "One or more allocator outcomes are quarantined; no external free will be retried.",
                )
                if self._cleanup_quarantined
                else None
            )
        except BaseException as exc:
            if not isinstance(exc, Exception):
                self._cleanup_failed = True
                self._failure_reason = HipFgmresLiveCheckpointReasonV1(
                    "hip_fgmres_live_checkpoint_cleanup_interrupted", _detail(exc)
                )
            raise

    def _close_kernel(self) -> None:
        if self._kernel_closed or self._kernel is None:
            return
        self._telemetry = replace(
            self._telemetry,
            module_close_attempt_count=self._telemetry.module_close_attempt_count + 1,
        )
        try:
            if type(self._kernel) is HipRtcFgmresV2Kernel:
                if self._kernel.pending_stream_count != 0:
                    _fail(
                        "hip_fgmres_live_checkpoint_unexpected_pending_work",
                        "/cleanup/kernel/pending_stream_count",
                    )
                if self._telemetry.checkpoint_token_acquire_success_count:
                    self._kernel.close(_checkpoint_owner_token=self._checkpoint_token)
                else:
                    self._kernel.close()
            else:
                self._kernel.close()
        except Exception as exc:
            self._raise_cleanup(
                "hip_fgmres_live_checkpoint_kernel_close_failed",
                "/cleanup/kernel",
                exc,
            )
        self._kernel_closed = True
        self._telemetry = replace(
            self._telemetry,
            module_close_success_count=1,
            checkpoint_token_release_success_count=(
                self._telemetry.checkpoint_token_acquire_success_count
            ),
        )

    def _release_group_only(self) -> None:
        if self._group_released or self._group_lease is None:
            return
        if self._parent is None or self._source_apply is None:
            self._raise_cleanup(
                "hip_fgmres_live_checkpoint_group_release_failed",
                "/cleanup/allocation_lineage/group_borrow",
                RuntimeError("parent cleanup authority missing"),
            )
        self._telemetry = replace(
            self._telemetry,
            group_borrow_release_attempt_count=(
                self._telemetry.group_borrow_release_attempt_count + 1
            ),
        )
        try:
            self._parent._release_fgmres_solver_child_allocation_borrow(
                self._token,
                self._source_apply,
            )
        except Exception as exc:
            self._raise_cleanup(
                "hip_fgmres_live_checkpoint_group_release_failed",
                "/cleanup/allocation_lineage/group_borrow",
                exc,
            )
        self._group_released = True
        self._telemetry = replace(
            self._telemetry,
            group_borrow_release_success_count=1,
        )

    def _release_semantic_last(self) -> None:
        if (
            self._semantic_released
            or not self._telemetry.semantic_lease_acquire_success_count
            or self._parent is None
            or self._source_apply is None
        ):
            return
        self._telemetry = replace(
            self._telemetry,
            semantic_lease_release_attempt_count=(
                self._telemetry.semantic_lease_release_attempt_count + 1
            ),
        )
        try:
            self._parent._release_fgmres_solver_child(self._token, self._source_apply)
        except Exception as exc:
            self._raise_cleanup(
                "hip_fgmres_live_checkpoint_semantic_release_failed",
                "/cleanup/parent_lease",
                exc,
            )
        self._semantic_released = True
        self._telemetry = replace(
            self._telemetry,
            semantic_lease_release_success_count=1,
        )

    def _retire_owned(self, name: str) -> Exception | None:
        capability = self._owned_capabilities.get(name)
        if capability is None:
            return None
        owner = self._allocation_owner
        if owner is None:
            return RuntimeError("allocation owner missing")
        size = next(row.byte_length for row in self._owned_buffers if row.name == name)
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
                    assert self._runtime is not None
                    self._runtime.free(lease.pointer_snapshot)  # type: ignore[attr-defined]
                    self._cleanup_dispositions[name] = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(self._runtime, exc):
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
                            "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                            f"/cleanup/owned_buffers/{name}",
                        )
                    self._finish_owned(name, size, quarantined=True)
                    if isinstance(exc, Exception):
                        return None
                    raise
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
                        "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                        f"/cleanup/owned_buffers/{name}",
                    )
                self._finish_owned(name, size, quarantined=True)
                return None
            if disposition != "external_free_succeeded" or lease is None:
                _fail(
                    "hip_fgmres_live_checkpoint_cleanup_disposition_invalid",
                    f"/cleanup/owned_buffers/{name}",
                )
            outcome = owner.resolve_free_success(
                lease,
                _control_token=self._token,
            )
            if outcome != "succeeded":
                _fail(
                    "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                    f"/cleanup/owned_buffers/{name}",
                )
            self._finish_owned(name, size, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_owned(self, name: str, size: int, *, quarantined: bool) -> None:
        if quarantined:
            self._cleanup_quarantined = True
            self._telemetry = replace(
                self._telemetry,
                lineage_free_quarantine_count=(
                    self._telemetry.lineage_free_quarantine_count + 1
                ),
                quarantined_device_bytes=(
                    self._telemetry.quarantined_device_bytes + size
                ),
            )
        else:
            self._telemetry = replace(
                self._telemetry,
                deallocation_success_count=(
                    self._telemetry.deallocation_success_count + 1
                ),
                lineage_free_acknowledgement_count=(
                    self._telemetry.lineage_free_acknowledgement_count + 1
                ),
            )
        self._telemetry = replace(
            self._telemetry,
            current_device_bytes=max(0, self._telemetry.current_device_bytes - size),
        )
        self._cleanup_dispositions[name] = "terminal"
        self._pending_free_leases.pop(name, None)
        self._owned_capabilities.pop(name, None)

    def _retire_orphan(self, cleanup: _OrphanCleanup) -> Exception | None:
        if cleanup not in self._orphan_cleanups:
            return None
        owner = self._allocation_owner
        if owner is None:
            return RuntimeError("allocation owner missing")
        try:
            if cleanup.disposition == "terminal":
                self._orphan_cleanups.remove(cleanup)
                return None
            if cleanup.must_quarantine or cleanup.pointer is None:
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
                    assert self._runtime is not None
                    self._runtime.free(cleanup.lease.pointer_snapshot)  # type: ignore[attr-defined]
                    cleanup.disposition = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(self._runtime, exc):
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
                            "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                            "/cleanup/allocation_lineage/orphan",
                        )
                    self._finish_orphan(cleanup, quarantined=True)
                    if isinstance(exc, Exception):
                        return None
                    raise
            elif cleanup.disposition == "free_call_inflight":
                cleanup.disposition = "quarantine_pending"
            if cleanup.disposition == "quarantine_pending":
                outcome = owner.resolve_orphan_free_quarantine(
                    cleanup.lease,
                    _control_token=self._token,
                )
                if outcome != "quarantined":
                    _fail(
                        "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                        "/cleanup/allocation_lineage/orphan",
                    )
                self._finish_orphan(cleanup, quarantined=True)
                return None
            if cleanup.disposition != "external_free_succeeded":
                _fail(
                    "hip_fgmres_live_checkpoint_cleanup_disposition_invalid",
                    "/cleanup/allocation_lineage/orphan",
                )
            outcome = owner.resolve_orphan_free_success(
                cleanup.lease,
                _control_token=self._token,
            )
            if outcome != "succeeded":
                _fail(
                    "hip_fgmres_live_checkpoint_lineage_outcome_invalid",
                    "/cleanup/allocation_lineage/orphan",
                )
            self._finish_orphan(cleanup, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_orphan(self, cleanup: _OrphanCleanup, *, quarantined: bool) -> None:
        if quarantined:
            self._cleanup_quarantined = True
            self._telemetry = replace(
                self._telemetry,
                lineage_orphan_quarantine_count=(
                    self._telemetry.lineage_orphan_quarantine_count + 1
                ),
                quarantined_device_bytes=(
                    self._telemetry.quarantined_device_bytes
                    + (cleanup.byte_length if cleanup.pointer is not None else 0)
                ),
                unknown_malloc_outcome_count=(
                    self._telemetry.unknown_malloc_outcome_count
                    + (1 if cleanup.pointer is None else 0)
                ),
                unknown_requested_bytes=(
                    self._telemetry.unknown_requested_bytes
                    + (cleanup.byte_length if cleanup.pointer is None else 0)
                ),
            )
        else:
            self._telemetry = replace(
                self._telemetry,
                deallocation_success_count=(
                    self._telemetry.deallocation_success_count + 1
                ),
                lineage_orphan_acknowledgement_count=(
                    self._telemetry.lineage_orphan_acknowledgement_count + 1
                ),
            )
        if cleanup.pointer is not None:
            self._telemetry = replace(
                self._telemetry,
                current_device_bytes=max(
                    0, self._telemetry.current_device_bytes - cleanup.byte_length
                ),
            )
        cleanup.disposition = "terminal"
        self._orphan_cleanups.remove(cleanup)

    def _raise_cleanup(self, code: str, path: str, error: object) -> None:
        self._cleanup_failed = True
        self._failure_reason = HipFgmresLiveCheckpointReasonV1(code, _detail(error))
        raise HipFgmresLiveCheckpointContextV1Error(
            code, path, _detail(error), cleanup_owner=self
        ) from (error if isinstance(error, BaseException) else None)

    def _build_receipt(
        self, status: LiveCheckpointStatusV1
    ) -> HipFgmresLiveCheckpointContextReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail("hip_fgmres_live_checkpoint_receipt_unavailable", "/receipt")
        ready = status == "context_ready"
        lineage = HipFgmresLiveCheckpointLineageV1(
            capability_profile=HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
            evidence_scope=HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
            owner_role="fgmres_checkpoint_owned_buffers",
            runtime_device_bound=ready,
            same_stream_bound=ready,
            parent_borrowed_capability_count=3 if self._parent_capabilities else 0,
            managed_buffer_count=len(self._owned_capabilities),
            managed_device_bytes=self._telemetry.current_device_bytes,
            atomic_group_capability_count=(
                11 if self._group_lease is not None and not self._group_released else 0
            ),
            all_owned_buffers_managed=ready and len(self._owned_capabilities) == 8,
        )
        claims = HipFgmresLiveCheckpointClaimsV1(
            live_krylov_parent_integrated=ready,
            allocator_provenance_bound=ready,
            resource_owner_ready=ready,
        )
        draft = HipFgmresLiveCheckpointContextReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_EVIDENCE_SCOPE_V1,
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=None
            if ready or status == "context_closed"
            else self._failure_reason,
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
                _receipt_payload(draft, include_hash=False)
            ),
        )


_CONTEXT_MINT = object()


def open_hip_fgmres_live_checkpoint_context_v1(
    parent: HipKrylovPrimitivesExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    recurrence_plan: HipFgmresRecurrencePlanV2,
    *,
    architecture: str | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    rtc_kernel: Any | None = None,
) -> HipFgmresLiveCheckpointContextOpenResultV1:
    """Open the allocation/module lifetime slice without numerical work.

    A caller-supplied kernel remains caller-owned until exact preflight publishes
    it into the private handoff.  Publication transfers ownership to this
    factory: every later failure closes it, while a ready result transfers that
    same obligation to the returned context.  Failures before preflight (for
    example a memory-budget rejection) leave the caller's kernel untouched.
    """

    context = HipFgmresLiveCheckpointExecutionContextV1(_mint=_CONTEXT_MINT)
    owner_handoff: list[HipAllocationOwnerV1 | None] = [None]
    kernel_handoff = _HipRtcFgmresV2KernelHandoff()
    caller_kernel_handoff: list[HipRtcFgmresV2Kernel | None] = [None]
    try:
        if type(parent) is not HipKrylovPrimitivesExecutionContext:
            _fail("hip_fgmres_live_checkpoint_parent_invalid", "/parent")
        if type(source_apply) is not HipFreeSpaceApplyReceipt:
            _fail("hip_fgmres_live_checkpoint_source_apply_invalid", "/source_apply")
        if type(recurrence_plan) is not HipFgmresRecurrencePlanV2:
            _fail("hip_fgmres_live_checkpoint_plan_invalid", "/recurrence_plan")
        validate_hip_fgmres_recurrence_plan_v2(
            recurrence_plan,
            expected_source_plan=recurrence_plan._source_fgmres_plan,
        )
        source_plan = recurrence_plan._source_fgmres_plan
        validate_hip_fgmres_plan_v1(
            source_plan,
            expected_execution_plan=source_plan._source_execution_plan,
            expected_free_space_plan=source_plan._source_free_space_plan,
        )
        if isinstance(memory_budget_bytes, bool) or (
            memory_budget_bytes is not None
            and (type(memory_budget_bytes) is not int or memory_budget_bytes <= 0)
        ):
            _fail(
                "hip_fgmres_live_checkpoint_memory_budget_invalid",
                "/memory_budget_bytes",
            )
        context._parent = parent
        context._source_apply = source_apply
        context._recurrence_plan = recurrence_plan
        context._source_plan = source_plan
        context._dimensions = HipFgmresLiveCheckpointDimensionsV1(
            recurrence_plan.free_dof_count,
            recurrence_plan.restart_dimension,
            recurrence_plan.max_iterations,
            recurrence_plan.maximum_restart_count,
        )
        context._owned_buffers = _owned_buffer_views(recurrence_plan)
        owned_bytes = sum(row.byte_length for row in context._owned_buffers)
        if memory_budget_bytes is not None and owned_bytes > memory_budget_bytes:
            _fail(
                "hip_fgmres_live_checkpoint_memory_budget_exceeded",
                "/memory_budget_bytes",
                f"Required {owned_bytes} bytes exceeds the requested budget.",
            )

        allocation_owner = open_hip_allocation_peer_owner_v1(
            parent._allocation_owner,
            "fgmres_checkpoint_owned_buffers",
            _handoff=owner_handoff,
        )
        context._adopt_allocation_owner(allocation_owner)

        parent_capabilities = parent._reserve_fgmres_solver_child_for_source_apply(
            source_apply,
            context._token,
            allocation_owner,
        )
        context._parent_capabilities = parent_capabilities
        context._telemetry = replace(
            context._telemetry, semantic_lease_acquire_success_count=1
        )
        snapshot = parent._fgmres_reserved_solver_child_snapshot(
            context._token, source_apply
        )
        _validate_plan_against_parent(recurrence_plan, source_plan, snapshot)
        selected_architecture = snapshot.architecture
        if architecture is not None and architecture != selected_architecture:
            _fail("hip_fgmres_live_checkpoint_architecture_mismatch", "/architecture")
        context._runtime = snapshot.runtime
        context._loaded_runtime = snapshot.loaded_runtime
        context._stream = snapshot.stream
        context._stream_pointer_snapshot = _pointer_value(snapshot.stream)
        context._device_ordinal = snapshot.device_ordinal
        context._architecture = selected_architecture
        context._primitive_opening_receipt = snapshot.primitive_opening_receipt
        context._context_id = canonical_hash(
            {
                "profile": HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_CAPABILITY_PROFILE_V1,
                "primitive_context_id": snapshot.primitive_context_id,
                "primitive_opening_receipt_hash": snapshot.primitive_opening_receipt_hash,
                "source_apply_receipt_hash": snapshot.source_apply_receipt_hash,
                "recurrence_plan_hash": recurrence_plan.plan_hash,
                "solver_child_lease_epoch": snapshot.solver_child_lease_epoch,
            }
        )

        if rtc_kernel is None:
            context._kernel_origin = "internally_compiled"
            kernel = _compile_v2_with_handoff(
                compile_hip_rtc_fgmres_v2_kernel,
                kernel_handoff,
                snapshot.loaded_runtime,
                selected_architecture,
                hiprtc_library,
            )
        else:
            context._kernel_origin = "caller_supplied"
            kernel = _preflight_kernel(
                rtc_kernel,
                selected_architecture,
                _handoff=caller_kernel_handoff,
            )
        context._adopt_kernel_owner(kernel)
        assert type(context._kernel) is HipRtcFgmresV2Kernel
        acquired_token, binding_snapshot = (
            context._kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
                snapshot.device_ordinal,
                _checkpoint_owner_token=context._checkpoint_token,
            )
        )
        if acquired_token is not context._checkpoint_token:
            _fail(
                "hip_fgmres_live_checkpoint_kernel_token_changed",
                "/kernel/checkpoint_token",
            )
        if context._kernel._checkpoint_runtime_owner(context._checkpoint_token) is not (
            snapshot.loaded_runtime
        ):
            _fail(
                "hip_fgmres_live_checkpoint_kernel_runtime_mismatch", "/kernel/runtime"
            )
        context._kernel_binding_snapshot = binding_snapshot
        assert context._kernel_origin is not None
        context._kernel_summary = _kernel_summary(
            context._kernel,
            context._kernel_origin,
        )
        context._telemetry = replace(
            context._telemetry, checkpoint_token_acquire_success_count=1
        )

        assert context._allocation_owner is not None
        for view in context._owned_buffers:
            context._telemetry = replace(
                context._telemetry,
                allocation_attempt_count=context._telemetry.allocation_attempt_count
                + 1,
            )
            try:
                capability = context._allocation_owner.allocate(
                    view.name,
                    view.byte_length,
                    "f64" if view.dtype == "<f8" else "u8",
                    _control_token=context._token,
                )
            except HipAllocationLineageError as exc:
                orphan = exc.orphan_cleanup_lease
                if orphan is not None:
                    context._orphan_cleanups.append(
                        _OrphanCleanup(
                            orphan,
                            orphan.nbytes,
                            orphan.base,
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
                        context._telemetry = replace(
                            context._telemetry,
                            allocation_success_count=(
                                context._telemetry.allocation_success_count + 1
                            ),
                            current_device_bytes=(
                                context._telemetry.current_device_bytes + orphan.nbytes
                            ),
                            peak_device_bytes=max(
                                context._telemetry.peak_device_bytes,
                                context._telemetry.current_device_bytes + orphan.nbytes,
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

        group = parent_capabilities + tuple(
            context._owned_capabilities[name] for name in _OWNED_ROLES
        )
        prepared = parent._prepare_fgmres_solver_child_allocation_borrow(
            context._token, source_apply, group
        )
        if prepared is not group:
            _fail(
                "hip_fgmres_live_checkpoint_group_changed",
                "/allocation_lineage/group",
            )
        context._group_capabilities = group
        lease = borrow_hip_allocations_v1(group, context._token)
        context._group_lease = lease
        committed = parent._commit_fgmres_solver_child_allocation_borrow(
            context._token, source_apply, group, lease
        )
        if committed is not context._token:
            _fail(
                "hip_fgmres_live_checkpoint_group_commit_changed",
                "/allocation_lineage/group",
            )
        context._telemetry = replace(
            context._telemetry, group_borrow_acquire_success_count=1
        )
        active_snapshot = parent._fgmres_solver_child_snapshot(
            context._token, source_apply
        )
        generation_hash = _generation_binding_hash(group)
        context._bindings = _bindings(
            recurrence_plan,
            source_plan,
            active_snapshot,
            generation_hash,
        )
        context._validate_authority()
        context._opening_receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            context._opening_receipt, expected_context=context
        )
        return HipFgmresLiveCheckpointContextOpenResultV1(
            context, context._opening_receipt
        )
    except BaseException as primary:
        context._failure_reason = HipFgmresLiveCheckpointReasonV1(
            "hip_fgmres_live_checkpoint_context_open_failed", _detail(primary)
        )
        recovery_error: BaseException | None = None
        try:
            context._adopt_allocation_owner(owner_handoff[0])
            context._recover_semantic_authority()
            handoff_kernel = kernel_handoff.kernel
            if handoff_kernel is None:
                handoff_kernel = caller_kernel_handoff[0]
            context._adopt_kernel_owner(handoff_kernel)
            context._recover_checkpoint_authority()
            context._recover_allocation_cleanup_snapshot(opening=True)
            context._recover_group_borrow()
        except BaseException as exc:
            recovery_error = exc
        cleanup_error: BaseException | None = None
        try:
            context.close()
        except BaseException as exc:
            cleanup_error = exc
        if not isinstance(primary, Exception):
            raise HipFgmresLiveCheckpointContextV1Error(
                "hip_fgmres_live_checkpoint_context_open_interrupted",
                "/open",
                _detail(primary),
                cleanup_owner=None if context.closed else context,
            ) from (cleanup_error or recovery_error or primary)
        if (
            recovery_error is not None
            or cleanup_error is not None
            or not context.closed
            or context._cleanup_quarantined
        ):
            context._cleanup_failed = (
                recovery_error is not None or cleanup_error is not None
            )
            receipt = context.receipt()
            return HipFgmresLiveCheckpointContextOpenResultV1(context, receipt)
        unavailable = _unavailable_receipt(context, primary)
        return HipFgmresLiveCheckpointContextOpenResultV1(None, unavailable)


def _validate_plan_against_parent(
    recurrence_plan: HipFgmresRecurrencePlanV2,
    source_plan: HipFgmresPlanV1,
    snapshot: Any,
) -> None:
    validate_hip_fgmres_plan_v1(
        source_plan,
        expected_execution_plan=snapshot.source_execution_plan,
        expected_free_space_plan=snapshot.source_free_space_plan,
    )
    validate_hip_fgmres_recurrence_plan_v2(
        recurrence_plan, expected_source_plan=source_plan
    )
    if (
        recurrence_plan.source_execution_plan_hash
        != snapshot.source_execution_plan_hash
        or recurrence_plan.source_free_space_plan_hash
        != snapshot.source_free_space_plan_hash
        or recurrence_plan.free_dof_count != snapshot.free_dof_count
        or recurrence_plan.reduced_csr_nnz != snapshot.reduced_csr_nnz
    ):
        _fail("hip_fgmres_live_checkpoint_plan_parent_mismatch", "/recurrence_plan")


def _owned_buffer_views(
    recurrence_plan: HipFgmresRecurrencePlanV2,
) -> tuple[HipFgmresLiveCheckpointBufferV1, ...]:
    rows = []
    for name in _OWNED_ROLES:
        row = recurrence_plan.buffer(name)
        if (
            row.name != name
            or row.ownership != "owned"
            or row.dtype
            not in {
                "<f8",
                "|u1",
            }
        ):
            _fail(
                "hip_fgmres_live_checkpoint_buffer_plan_invalid",
                f"/recurrence_plan/buffers/{name}",
            )
        rows.append(
            HipFgmresLiveCheckpointBufferV1(
                name=row.name,
                dtype=row.dtype,
                shape=row.shape,
                element_count=row.element_count,
                byte_length=row.byte_length,
                access=row.access,
                initialization=row.initialization,
                extent_formula=row.extent_formula,
            )
        )
    return tuple(rows)


def _preflight_kernel(
    kernel: Any,
    architecture: str,
    *,
    _handoff: list[HipRtcFgmresV2Kernel | None] | None = None,
) -> HipRtcFgmresV2Kernel:
    if _handoff is not None and (
        type(_handoff) is not list or len(_handoff) != 1 or _handoff[0] is not None
    ):
        _fail(
            "hip_fgmres_live_checkpoint_kernel_handoff_invalid",
            "/rtc_kernel/handoff",
        )
    if type(kernel) is not HipRtcFgmresV2Kernel:
        _fail("hip_fgmres_live_checkpoint_kernel_invalid", "/rtc_kernel")
    try:
        _validate_identity(kernel.identity)
        if (
            kernel.closed
            or kernel.pending_stream_count != 0
            or kernel.identity.architecture != architecture
        ):
            raise ValueError("kernel is closed, pending, or architecture-mismatched")
    except Exception as exc:
        raise HipFgmresLiveCheckpointContextV1Error(
            "hip_fgmres_live_checkpoint_kernel_invalid",
            "/rtc_kernel",
            _detail(exc),
        ) from exc
    if _handoff is not None:
        _handoff[0] = kernel
    return kernel


def _kernel_summary(
    kernel: HipRtcFgmresV2Kernel,
    origin: Literal["internally_compiled", "caller_supplied"],
) -> HipFgmresLiveCheckpointKernelV1:
    identity = kernel.identity
    _validate_identity(identity)
    return HipFgmresLiveCheckpointKernelV1(
        architecture=identity.architecture,
        identity_hash=identity.identity_hash,
        source_sha256=identity.source_sha256,
        code_object_sha256=identity.code_object_sha256,
        kernel_interface_hash=identity.kernel_interface_hash,
        runtime_library_sha256=identity.runtime_library.sha256,
        runtime_library_discovery_source=identity.runtime_library.discovery_source,
        hiprtc_library_sha256=identity.hiprtc_library.sha256,
        hiprtc_library_discovery_source=identity.hiprtc_library.discovery_source,
        kernel_origin=origin,
    )


def _derive_actual_backend(
    primitive_opening_receipt: Any,
    kernel: HipRtcFgmresV2Kernel,
    origin: Literal["internally_compiled", "caller_supplied"],
) -> Literal["hip", "test_double"]:
    identity = kernel.identity
    _validate_identity(identity)
    native_parent = (
        primitive_opening_receipt.evidence_scope
        == "native_hiprtc_krylov_primitives_composite"
        and primitive_opening_receipt.actual_backend == "hip"
    )
    native_kernel = (
        origin == "internally_compiled"
        and identity.runtime_library.discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
        and identity.hiprtc_library.discovery_source
        in {"explicit", "opt_rocm", "system_loader"}
    )
    return "hip" if native_parent and native_kernel else "test_double"


def _generation_binding_hash(
    capabilities: tuple[HipAllocationCapabilityV1, ...],
) -> str:
    return canonical_hash(
        {
            "roles": [capability.role for capability in capabilities],
            "generations": [capability.generation for capability in capabilities],
            "byte_lengths": [capability.nbytes for capability in capabilities],
            "element_types": [capability.element_type for capability in capabilities],
            "pointer_values_serialized": False,
        }
    )


def _bindings(
    recurrence_plan: HipFgmresRecurrencePlanV2,
    source_plan: HipFgmresPlanV1,
    snapshot: Any,
    generation_hash: str,
) -> HipFgmresLiveCheckpointBindingsV1:
    return HipFgmresLiveCheckpointBindingsV1(
        primitive_context_id=snapshot.primitive_context_id,
        primitive_opening_receipt_hash=snapshot.primitive_opening_receipt_hash,
        primitive_evidence_scope=(snapshot.primitive_opening_receipt.evidence_scope),
        primitive_actual_backend=(snapshot.primitive_opening_receipt.actual_backend),
        source_apply_id=snapshot.source_apply.apply_id,
        source_apply_receipt_hash=snapshot.source_apply_receipt_hash,
        source_apply_sequence=snapshot.source_apply_sequence,
        source_direction_generation=snapshot.source_direction_generation,
        source_execution_plan_hash=snapshot.source_execution_plan_hash,
        source_free_space_plan_hash=snapshot.source_free_space_plan_hash,
        source_state_hash=snapshot.state_hash,
        source_state_epoch=snapshot.state_epoch,
        source_fgmres_plan_hash=source_plan.plan_hash,
        recurrence_plan_id=recurrence_plan.plan_id,
        recurrence_plan_hash=recurrence_plan.plan_hash,
        recurrence_memory_layout_hash=recurrence_plan.memory_layout_hash,
        recurrence_kernel_abi_hash=recurrence_plan.kernel_module_abi_hash,
        primitive_parent_lease_epoch=snapshot.primitive_parent_lease_epoch,
        solver_child_lease_epoch=snapshot.solver_child_lease_epoch,
        allocation_generation_binding_hash=generation_hash,
    )


def _unavailable_receipt(
    context: HipFgmresLiveCheckpointExecutionContextV1,
    error: BaseException,
) -> HipFgmresLiveCheckpointContextReceiptV1:
    if context._bindings is None:
        plan = context._recurrence_plan
        source = context._source_plan
        parent = context._parent
        if plan is None or source is None or parent is None:
            raise error
        snapshot = (
            parent._fgmres_solver_child_snapshot(context._token, context._source_apply)
            if (
                context._telemetry.semantic_lease_acquire_success_count
                and not context._semantic_released
                and parent._fgmres_solver_child_token is context._token
            )
            else None
        )
        if snapshot is None:
            # Bind only immutable plan/source rows after a fully cleaned failure.
            opening = parent.opening_receipt
            context._bindings = HipFgmresLiveCheckpointBindingsV1(
                parent.context_id,
                opening.context_receipt_hash,
                opening.evidence_scope,
                opening.actual_backend,
                getattr(context._source_apply, "apply_id", _ZERO_HASH),
                getattr(context._source_apply, "receipt_hash", _ZERO_HASH),
                int(getattr(context._source_apply, "sequence", 0)),
                int(getattr(context._source_apply, "direction_generation", 0) or 0),
                source.source_execution_plan_hash,
                source.source_free_space_plan_hash,
                opening.bindings.state_hash,
                opening.bindings.state_epoch,
                source.plan_hash,
                plan.plan_id,
                plan.plan_hash,
                plan.memory_layout_hash,
                plan.kernel_module_abi_hash,
                opening.bindings.lease_epoch,
                0,
                _ZERO_HASH,
            )
    if context._dimensions is None and context._recurrence_plan is not None:
        plan = context._recurrence_plan
        context._dimensions = HipFgmresLiveCheckpointDimensionsV1(
            plan.free_dof_count,
            plan.restart_dimension,
            plan.max_iterations,
            plan.maximum_restart_count,
        )
    context._failure_reason = HipFgmresLiveCheckpointReasonV1(
        "hip_fgmres_live_checkpoint_context_open_failed", _detail(error)
    )
    receipt = context._build_receipt("unavailable")
    return receipt


def _receipt_payload(
    receipt: HipFgmresLiveCheckpointContextReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_CAPABILITY_PROFILE_V1,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "kernel": None if receipt.kernel is None else receipt.kernel.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "owned_buffers": [row.to_dict() for row in receipt.owned_buffers],
        "allocation_lineage": receipt.allocation_lineage.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def validate_hip_fgmres_live_checkpoint_context_receipt_v1(
    receipt: HipFgmresLiveCheckpointContextReceiptV1,
    *,
    expected_context: HipFgmresLiveCheckpointExecutionContextV1 | None = None,
) -> HipFgmresLiveCheckpointContextReceiptV1:
    if type(receipt) is not HipFgmresLiveCheckpointContextReceiptV1:
        _fail("hip_fgmres_live_checkpoint_receipt_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=False)
    if (
        type(receipt.context_receipt_hash) is not str
        or _HASH_RE.fullmatch(receipt.context_receipt_hash) is None
        or receipt.context_receipt_hash != canonical_hash(payload)
    ):
        _fail(
            "hip_fgmres_live_checkpoint_receipt_hash_invalid", "/context_receipt_hash"
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_live_checkpoint_schema_invalid",
            path or "/",
            errors[0].message,
        )
    ready = receipt.status == "context_ready"
    expected_backend: Literal["hip", "test_double"] | None = None
    if receipt.kernel is not None:
        native_parent = (
            receipt.bindings.primitive_evidence_scope
            == "native_hiprtc_krylov_primitives_composite"
            and receipt.bindings.primitive_actual_backend == "hip"
        )
        native_kernel = (
            receipt.kernel.kernel_origin == "internally_compiled"
            and receipt.kernel.runtime_library_discovery_source
            in {"explicit", "opt_rocm", "system_loader"}
            and receipt.kernel.hiprtc_library_discovery_source
            in {"explicit", "opt_rocm", "system_loader"}
        )
        expected_backend = "hip" if native_parent and native_kernel else "test_double"
    if receipt.actual_backend != expected_backend:
        _fail(
            "hip_fgmres_live_checkpoint_backend_invalid",
            "/actual_backend",
        )
    if any(
        (
            receipt.promotion_eligible,
            receipt.claims.owned_content_initialized,
            receipt.claims.authoritative_predecessor_proven,
            receipt.claims.device_mask_domain_validator_bound,
            receipt.claims.actual_mask_host_observed,
            receipt.claims.checkpoint_transaction_ready,
            receipt.claims.live_solver_ready,
            receipt.claims.solution_ready,
            receipt.claims.iteration_host_copy_zero_proven,
            receipt.claims.asymptotic_o_n_proven,
            receipt.claims.speedup_proven,
            receipt.claims.commercial_ready,
            receipt.claims.promotion_eligible,
        )
    ):
        _fail("hip_fgmres_live_checkpoint_claim_invalid", "/claims")
    if (
        receipt.claims.live_krylov_parent_integrated is not ready
        or receipt.claims.allocator_provenance_bound is not ready
        or receipt.claims.resource_owner_ready is not ready
    ):
        _fail("hip_fgmres_live_checkpoint_claim_invalid", "/claims")
    if ready and (
        receipt.reason is not None
        or len(receipt.owned_buffers) != 8
        or receipt.dimensions.parent_capability_count != 3
        or receipt.dimensions.solver_owned_capability_count != 8
        or receipt.dimensions.atomic_group_capability_count != 11
        or receipt.allocation_lineage.parent_borrowed_capability_count != 3
        or receipt.allocation_lineage.managed_buffer_count != 8
        or receipt.allocation_lineage.atomic_group_capability_count != 11
        or not receipt.allocation_lineage.all_owned_buffers_managed
    ):
        _fail("hip_fgmres_live_checkpoint_status_invalid", "/status")
    if expected_context is not None:
        if type(expected_context) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail("hip_fgmres_live_checkpoint_expected_context_invalid", "/")
        if ready:
            expected_context._validate_authority()
        current = expected_context.receipt()
        if receipt is expected_context._opening_receipt:
            if (
                receipt.context_receipt_hash
                != expected_context._opening_receipt.context_receipt_hash
            ):
                _fail("hip_fgmres_live_checkpoint_receipt_context_mismatch", "/")
        elif receipt.context_receipt_hash != current.context_receipt_hash:
            _fail("hip_fgmres_live_checkpoint_receipt_context_mismatch", "/")
    return receipt


def _validate_context_authority(
    context: HipFgmresLiveCheckpointExecutionContextV1,
) -> None:
    context._validate_authority()


def _context_validate_authority(
    self: HipFgmresLiveCheckpointExecutionContextV1,
) -> None:
    _context_validate_authority_common(
        self,
        canonical_child_token=None,
        pending_operation_bounds=(0, 0),
    )


def _context_validate_authority_for_canonical_child(
    self: HipFgmresLiveCheckpointExecutionContextV1,
    canonical_child_token: object,
    *,
    pending_operation_bounds: tuple[int, int],
) -> None:
    _context_validate_authority_common(
        self,
        canonical_child_token=canonical_child_token,
        pending_operation_bounds=pending_operation_bounds,
    )


def _context_validate_authority_common(
    self: HipFgmresLiveCheckpointExecutionContextV1,
    *,
    canonical_child_token: object | None,
    pending_operation_bounds: tuple[int, int],
    force_leased_pending_snapshot: bool = False,
) -> None:
    if (
        type(pending_operation_bounds) is not tuple
        or len(pending_operation_bounds) != 2
        or any(type(value) is not int for value in pending_operation_bounds)
        or not 0 <= pending_operation_bounds[0] <= pending_operation_bounds[1]
    ):
        _fail(
            "hip_fgmres_live_checkpoint_pending_bounds_invalid",
            "/kernel/pending_operation_bounds",
        )
    with self._queue_lock:
        if canonical_child_token is not None:
            self._require_canonical_predecessor_child(canonical_child_token)
        _context_validate_authority_locked(
            self,
            pending_operation_bounds=pending_operation_bounds,
            use_leased_pending_snapshot=(
                canonical_child_token is not None or force_leased_pending_snapshot
            ),
        )


def _context_validate_authority_locked(
    self: HipFgmresLiveCheckpointExecutionContextV1,
    *,
    pending_operation_bounds: tuple[int, int],
    use_leased_pending_snapshot: bool,
) -> None:
    if (
        self._parent is None
        or self._source_apply is None
        or self._recurrence_plan is None
        or self._source_plan is None
        or self._group_lease is None
        or self._group_released
        or self._allocation_owner is None
        or self._kernel is None
        or type(self._kernel) is not HipRtcFgmresV2Kernel
        or self._kernel_closed
        or self._runtime is None
        or self._stream is None
        or _pointer_value(self._stream) != self._stream_pointer_snapshot
        or self._device_ordinal is None
        or self._kernel_binding_snapshot is None
    ):
        _fail("hip_fgmres_live_checkpoint_authority_invalid", "/authority")
    validate_hip_fgmres_recurrence_plan_v2(
        self._recurrence_plan, expected_source_plan=self._source_plan
    )
    self._parent._require_fgmres_solver_child(self._token, self._source_apply)
    snapshot = self._parent._fgmres_solver_child_snapshot(
        self._token, self._source_apply
    )
    if (
        snapshot.runtime is not self._runtime
        or snapshot.loaded_runtime is not self._loaded_runtime
        or snapshot.stream is not self._stream
        or snapshot.device_ordinal != self._device_ordinal
        or snapshot.allocation_borrow_capabilities is not self._group_capabilities
        or snapshot.allocation_borrow_lease is not self._group_lease
        or snapshot.allocation_borrow_phase != "active"
        or self._group_lease.capabilities is not self._group_capabilities
        or self._group_lease.borrower is not self._token
    ):
        _fail("hip_fgmres_live_checkpoint_authority_invalid", "/authority")
    validate_hip_allocation_borrow_v1(self._group_lease)
    validate_hip_allocation_owner_v1(self._allocation_owner)
    for capability in self._group_capabilities:
        validate_hip_allocation_capability_v1(capability)
    if not use_leased_pending_snapshot:
        # Preserve the original public owner validation contract.  The
        # canonical child path below needs the stronger leased-stream snapshot,
        # but callers of the live owner still observe this exact legacy probe.
        pending_valid = self._kernel.pending_stream_count == 0
    else:
        pending_snapshot = self._kernel._checkpoint_pending_snapshot(
            self._checkpoint_token
        )
        lower, upper = pending_operation_bounds
        pending_valid = False
        if not pending_snapshot:
            pending_valid = lower == 0
        elif len(pending_snapshot) == 1:
            stream_pointer, operation_count = pending_snapshot[0]
            pending_valid = (
                stream_pointer == self._stream_pointer_snapshot
                and lower <= operation_count <= upper
            )
    if (
        self._kernel._checkpoint_runtime_owner(self._checkpoint_token)
        is not self._loaded_runtime
        or self._kernel._checkpoint_binding_snapshot(self._checkpoint_token)
        != self._kernel_binding_snapshot
        or not pending_valid
    ):
        _fail("hip_fgmres_live_checkpoint_kernel_authority_invalid", "/kernel")


HipFgmresLiveCheckpointExecutionContextV1._validate_authority = (  # type: ignore[attr-defined]
    _context_validate_authority
)
HipFgmresLiveCheckpointExecutionContextV1._validate_authority_for_canonical_child = (  # type: ignore[attr-defined]
    _context_validate_authority_for_canonical_child
)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer_value(value: object) -> int:
    if type(value) is int and value > 0:
        return value
    if type(value) is ctypes.c_void_p and type(value.value) is int and value.value > 0:
        return value.value
    # Injected parent streams are opaque process-local identity capabilities.
    return id(value)


def _free_outcome_uncertain(runtime: object, error: BaseException) -> bool:
    if type(runtime) is _BoundHipContextRuntime:
        return True
    return type(error) is not HipFreeKnownNotFreedError


def _detail(value: object) -> str:
    text = _HEX_ADDRESS_RE.sub("<redacted-address>", str(value))
    text = _DECIMAL_HANDLE_RE.sub("<redacted-handle>", text)
    return (" ".join(text.split())[:512]) or "unspecified"


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresLiveCheckpointContextV1Error(code, path, message or code)


__all__ = [
    "HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_LIVE_CHECKPOINT_CONTEXT_SCHEMA_VERSION_V1",
    "HipFgmresLiveCheckpointBindingsV1",
    "HipFgmresLiveCheckpointBufferV1",
    "HipFgmresLiveCheckpointClaimsV1",
    "HipFgmresLiveCheckpointContextOpenResultV1",
    "HipFgmresLiveCheckpointContextReceiptV1",
    "HipFgmresLiveCheckpointContextV1Error",
    "HipFgmresLiveCheckpointDimensionsV1",
    "HipFgmresLiveCheckpointExecutionContextV1",
    "HipFgmresLiveCheckpointKernelV1",
    "HipFgmresLiveCheckpointLineageV1",
    "HipFgmresLiveCheckpointReasonV1",
    "HipFgmresLiveCheckpointTelemetryV1",
    "open_hip_fgmres_live_checkpoint_context_v1",
    "validate_hip_fgmres_live_checkpoint_context_receipt_v1",
]
