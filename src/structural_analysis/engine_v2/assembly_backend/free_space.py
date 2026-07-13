"""Same-stream free-space view over an assembly-resident CSR operator.

The context is a non-solver vertical slice.  It uploads only the five canonical
integer arrays that describe ``K_ff`` and materializes its numeric values by a
device-to-device gather from the assembly-owned full CSR.  A package-owned
kernel then produces ``r_f = F_f - K_ff u_f`` directly into the resident full
direction workspace, after which the existing resident residual/JVP kernel
consumes the opaque, single-use generation on the same stream.

No device handle is serializable.  No host reduced numeric values, state, load,
or direction are uploaded.  The verification wrapper exports arrays only after
the complete device chain has been enqueued and fenced; it is never fallback.
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
import numpy as np

from structural_analysis.engine_v2.backends.hip.context import (
    HipFreeKnownNotFreedError,
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip.native import LoadedHipRuntime
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)

from .free_space_plan import (
    HipFreeSpaceOperatorPlanV1,
    compile_hip_free_space_operator_plan_v1,
    validate_hip_free_space_operator_plan_v1,
)
from .free_space_rtc import (
    HipRtcFreeSpaceError,
    HipRtcFreeSpaceOperatorKernel,
    _HipRtcFreeSpaceKernelHandoff,
    _compile_free_space_operator_with_handoff,
    compile_hip_rtc_free_space_operator_kernel,
)
from .hip_allocation_lineage import (
    HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
    HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
    HipAllocationCapabilityV1,
    HipAllocationBorrowLeaseV1,
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
    _open_integrated_hip_allocation_owner_v1,
    borrow_hip_allocations_v1,
    open_hip_allocation_peer_owner_v1,
    recover_hip_allocation_borrow_v1,
    release_hip_allocation_borrow_v1,
    snapshot_hip_allocation_owner_cleanup_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_capability_v1,
    validate_hip_allocation_owner_v1,
)
from .resident import (
    HipResidentCsrEnqueueReceipt,
    HipResidentCsrExecutionContext,
    validate_hip_resident_csr_enqueue_receipt,
)

HIP_FREE_SPACE_CONTEXT_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-free-space-context.v2"
)
HIP_FREE_SPACE_APPLY_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-free-space-apply.v1"
)
HIP_FREE_SPACE_EVALUATION_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-free-space-evaluation.v1"
)
HIP_FREE_SPACE_CAPABILITY_PROFILE = (
    "phase0_hip_free_space_device_direction_operator_apply"
)

ContextStatus = Literal[
    "context_ready",
    "context_closed",
    "poisoned",
    "cleanup_failed",
    "cleanup_quarantined",
    "unavailable",
]
ApplyStatus = Literal["enqueued", "unavailable"]
EvaluationStatus = Literal["verified", "parity_failed", "unavailable"]
EvidenceScope = Literal["native_hiprtc_free_space_composite", "injected_test_double"]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_ADDRESS_PATTERN = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_PARITY_TOLERANCE = 1.0e-8
_ZERO_I32_DATA_HASH = array_data_hash(immutable_array([0], dtype="<i4"))
_SYMBOLIC_NAMES = (
    "free_dofs",
    "global_to_free",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
)
_WORK_NAMES = (
    "reduced_csr_values",
    "reduced_state",
    "reduced_load",
    "reduced_direction",
    "reduced_residual",
    "reduced_jvp",
    "error_flag",
)
_OWNED_ORDER = _SYMBOLIC_NAMES + _WORK_NAMES
_BORROWED_NAMES = (
    "full_csr_values",
    "full_state",
    "full_load",
    "full_direction",
    "full_residual",
    "full_jvp",
)


class HipFreeSpaceContextError(RuntimeError):
    """Stable fail-closed error with optional retryable cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str,
        *,
        cleanup_owner: HipFreeSpaceExecutionContext | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class HipFreeSpaceReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceKernelBinding:
    abi_version: int
    architecture: str
    materialize_symbol: str
    residual_direction_symbol: str
    gather_jvp_symbol: str
    block_size: int
    source_resource: str
    source_sha256: str
    code_object_sha256: str
    identity_hash: str
    runtime_library_discovery_source: str
    runtime_library_sha256: str
    hiprtc_library_discovery_source: str
    hiprtc_library_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceBindings:
    resident_context_id: str
    resident_opening_receipt_hash: str
    parent_assembly_context_id: str
    parent_operator_id: str
    free_space_plan_id: str
    free_space_plan_hash: str
    free_space_view_hash: str
    source_execution_plan_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_symbolic_reuse_hash: str
    source_partition_hash: str
    state_hash: str
    state_epoch: int
    load_pattern_id: str
    device_ordinal: int
    downstream_lease_epoch: int
    kernel_origin: Literal["internally_compiled", "caller_supplied"]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceDimensions:
    global_dof_count: int
    free_dof_count: int
    constrained_dof_count: int
    full_csr_nnz: int
    reduced_csr_nnz: int
    symbolic_buffer_count: Literal[5] = 5
    work_buffer_count: Literal[7] = 7
    borrowed_buffer_count: Literal[6] = 6

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceBufferView:
    name: str
    dtype: str
    shape: tuple[int, ...]
    byte_length: int
    data_hash: str | None
    access: str
    initial_transfer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "memory_space": "hip_device",
            "access": self.access,
            "initial_transfer": self.initial_transfer,
        }


@dataclass(frozen=True, slots=True)
class HipFreeSpaceTelemetry:
    allocation_attempt_count: int = 0
    allocation_success_count: int = 0
    deallocation_attempt_count: int = 0
    deallocation_success_count: int = 0
    current_device_bytes: int = 0
    peak_device_bytes: int = 0
    h2d_operation_attempt_count: int = 0
    h2d_operation_success_count: int = 0
    h2d_bytes_attempted: int = 0
    h2d_bytes_succeeded: int = 0
    d2h_operation_attempt_count: int = 0
    d2h_operation_success_count: int = 0
    d2h_bytes_attempted: int = 0
    d2h_bytes_succeeded: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_success_count: int = 0
    sync_attempt_count: int = 0
    sync_success_count: int = 0
    module_owner_acquired_count: int = 0
    module_close_attempt_count: int = 0
    module_close_success_count: int = 0
    lease_release_attempt_count: int = 0
    lease_release_success_count: int = 0
    lineage_owner_open_success_count: int = 0
    lineage_capability_mint_success_count: int = 0
    lineage_capability_mint_bytes: int = 0
    lineage_free_acknowledgement_count: int = 0
    lineage_free_quarantine_count: int = 0
    lineage_orphan_acknowledgement_count: int = 0
    lineage_orphan_quarantine_count: int = 0
    lineage_owner_close_success_count: int = 0
    quarantined_device_bytes: int = 0
    unknown_malloc_outcome_count: int = 0
    unknown_requested_bytes: int = 0
    symbolic_h2d_bytes: int = 0
    error_flag_h2d_bytes: int = 0
    error_flag_d2h_bytes: int = 0
    reduced_numeric_h2d_bytes: Literal[0] = 0
    state_h2d_bytes: Literal[0] = 0
    load_h2d_bytes: Literal[0] = 0
    direction_h2d_bytes: Literal[0] = 0
    new_stream_create_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceAllocationLineage:
    capability_profile: Literal["foundation_non_promoting"]
    evidence_scope: Literal["foundation_non_promoting"]
    owner_role: Literal["free_space_owned_buffers"]
    runtime_device_bound: Literal[True]
    managed_buffer_count: int
    managed_device_bytes: int
    all_owned_buffers_managed: bool
    pointer_values_serialized: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(slots=True)
class _HipFreeSpaceOrphanCleanup:
    lease: HipAllocationOrphanLeaseV1
    pointer: object | None
    byte_length: int
    must_quarantine: bool = False
    external_free_succeeded: bool = False
    quarantine_pending: bool = False


@dataclass(frozen=True, slots=True)
class HipFreeSpaceClaims:
    exclusive_resident_lease_active: bool
    same_runtime_device_stream: bool
    reduced_csr_device_materialized: bool
    device_direction_producer_ready: bool
    resident_jvp_consumer_ready: bool
    host_reduced_numeric_h2d_avoided: bool
    native_composite_context: bool
    krylov_iteration_ready: Literal[False] = False
    preconditioner_ready: Literal[False] = False
    solver_ready: Literal[False] = False
    iteration_host_copy_zero: Literal[False] = False
    end_to_end_on_complexity: Literal[False] = False
    performance_or_speedup: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceContextReceipt:
    status: ContextStatus
    context_id: str
    evidence_scope: EvidenceScope
    actual_backend: str | None
    promotion_eligible: Literal[False]
    reason: HipFreeSpaceReason | None
    bindings: HipFreeSpaceBindings
    kernel: HipFreeSpaceKernelBinding | None
    dimensions: HipFreeSpaceDimensions
    owned_buffers: tuple[HipFreeSpaceBufferView, ...]
    allocation_lineage: HipFreeSpaceAllocationLineage | None
    telemetry: HipFreeSpaceTelemetry
    claims: HipFreeSpaceClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FREE_SPACE_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_free_space_context_receipt(self)
        return _context_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFreeSpaceApplyDelta:
    producer_launch_attempt_count: int
    producer_launch_success_count: int
    resident_launch_attempt_count: int
    resident_launch_success_count: int
    gather_launch_attempt_count: int
    gather_launch_success_count: int
    h2d_operation_count: Literal[0]
    d2h_operation_count: Literal[0]
    allocation_count: Literal[0]
    sync_count: Literal[0]
    fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceApplyClaims:
    direction_device_produced: bool
    direction_generation_single_consumed: bool
    resident_residual_jvp_enqueued: bool
    reduced_jvp_gather_enqueued: bool
    completion_fence_observed: Literal[False] = False
    solver_iteration: Literal[False] = False
    fallback_used: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceApplyReceipt:
    status: ApplyStatus
    apply_id: str
    context_id: str
    opening_context_receipt_hash: str
    sequence: int
    direction_generation: int | None
    resident_enqueue: HipResidentCsrEnqueueReceipt | None
    resident_enqueue_receipt_hash: str | None
    resident_enqueue_sequence: int | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipFreeSpaceReason | None
    telemetry_delta: HipFreeSpaceApplyDelta
    claims: HipFreeSpaceApplyClaims
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FREE_SPACE_APPLY_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_free_space_apply_receipt(self)
        return _apply_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFreeSpaceArrayDescriptor:
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    byte_length: int
    data_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dtype": self.dtype,
            "shape": list(self.shape),
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
        }


@dataclass(frozen=True, slots=True)
class HipFreeSpaceParityMetric:
    count: int
    max_abs_error: float
    relative_l2_error: float
    max_scaled_error: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "max_abs_error": self.max_abs_error,
            "relative_l2_error": self.relative_l2_error,
            "max_scaled_error": self.max_scaled_error,
            "absolute_tolerance": _PARITY_TOLERANCE,
            "relative_tolerance": _PARITY_TOLERANCE,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipFreeSpaceParityReport:
    reduced_values: HipFreeSpaceParityMetric
    reduced_state: HipFreeSpaceParityMetric
    reduced_load: HipFreeSpaceParityMetric
    residual_direction: HipFreeSpaceParityMetric
    residual_direction_vs_negative_full_residual_free: HipFreeSpaceParityMetric
    reduced_jvp: HipFreeSpaceParityMetric
    full_residual: HipFreeSpaceParityMetric
    full_direction: HipFreeSpaceParityMetric
    constrained_direction_exact_zero: bool
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "execution_plan_v2_cpu_full_and_reduced_csr_fp64",
            "oracle_role": "verification_only_never_fallback",
            "metrics": {
                "reduced_values": self.reduced_values.to_dict(),
                "reduced_state": self.reduced_state.to_dict(),
                "reduced_load": self.reduced_load.to_dict(),
                "residual_direction": self.residual_direction.to_dict(),
                "residual_direction_vs_negative_full_residual_free": (
                    self.residual_direction_vs_negative_full_residual_free.to_dict()
                ),
                "reduced_jvp": self.reduced_jvp.to_dict(),
                "full_residual": self.full_residual.to_dict(),
                "full_direction": self.full_direction.to_dict(),
            },
            "constrained_direction_exact_zero": (self.constrained_direction_exact_zero),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipFreeSpaceEvaluationDelta:
    d2h_operation_attempt_count: int
    d2h_operation_success_count: int
    d2h_bytes_attempted: int
    d2h_bytes_succeeded: int
    sync_attempt_count: int
    sync_success_count: int
    allocation_count: Literal[0]
    h2d_operation_count: Literal[0]
    fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFreeSpaceEvaluationReceipt:
    status: EvaluationStatus
    execution_id: str
    context_id: str
    opening_context_receipt_hash: str
    apply: HipFreeSpaceApplyReceipt | None
    evidence_scope: EvidenceScope
    actual_backend: str
    promotion_eligible: Literal[False]
    reason: HipFreeSpaceReason | None
    arrays: tuple[tuple[str, HipFreeSpaceArrayDescriptor], ...]
    telemetry_delta: HipFreeSpaceEvaluationDelta
    parity: HipFreeSpaceParityReport | None
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FREE_SPACE_EVALUATION_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_free_space_evaluation_receipt(self)
        return _evaluation_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFreeSpaceEvaluation:
    receipt: HipFreeSpaceEvaluationReceipt
    reduced_values: np.ndarray | None
    reduced_state: np.ndarray | None
    reduced_load: np.ndarray | None
    residual_direction: np.ndarray | None
    reduced_jvp: np.ndarray | None
    full_residual: np.ndarray | None
    full_direction: np.ndarray | None
    apply: HipFreeSpaceApplyReceipt | None


@dataclass(frozen=True, slots=True)
class HipFreeSpaceContextOpenResult:
    context: HipFreeSpaceExecutionContext | None
    receipt: HipFreeSpaceContextReceipt

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


class HipFreeSpaceExecutionContext:
    """Exclusive downstream owner of one resident free-space device view."""

    def __init__(
        self,
        *,
        resident: HipResidentCsrExecutionContext,
        overlay: HipFreeSpaceOperatorPlanV1,
        lease_token: object,
        lease_epoch: int,
        kernel: Any,
        kernel_binding: HipFreeSpaceKernelBinding | None,
        kernel_internally_compiled: bool,
        evidence_scope: EvidenceScope,
        context_id: str,
        borrowed_pointers: dict[str, Any],
        pointers: dict[str, Any],
        allocation_owner: HipAllocationOwnerV1 | None,
        owned_capabilities: dict[str, HipAllocationCapabilityV1],
        pending_free_leases: dict[str, HipAllocationFreeLeaseV1] | None,
        external_free_succeeded: set[str] | None,
        orphan_cleanups: list[_HipFreeSpaceOrphanCleanup] | None,
        allocation_owner_closed: bool,
        allocation_lineage: HipFreeSpaceAllocationLineage | None,
        owned_buffers: tuple[HipFreeSpaceBufferView, ...],
        telemetry: HipFreeSpaceTelemetry,
        opening_status: ContextStatus,
        failure_reason: HipFreeSpaceReason | None,
        kernel_closed: bool = False,
    ) -> None:
        self._resident = resident
        self._overlay = overlay
        self._plan = overlay._source_execution_plan
        self._overlay_identity_snapshot = overlay
        self._plan_identity_snapshot = self._plan
        self._overlay_authority_snapshot = _overlay_authority_signature(overlay)
        self._plan_authority_snapshot = _plan_authority_signature(self._plan)
        self._resident_state_snapshot = resident._state
        self._lease_token = lease_token
        self._lease_epoch = lease_epoch
        self._runtime = resident._runtime
        self._stream = resident._stream
        self._runtime_snapshot = resident._runtime
        self._stream_snapshot = resident._stream
        self._resident_snapshot = resident
        self._kernel = kernel
        self._kernel_object_snapshot = kernel
        self._kernel_identity_snapshot = (
            None if kernel is None else getattr(kernel, "identity", None)
        )
        self._kernel_binding = kernel_binding
        self._kernel_internally_compiled = kernel_internally_compiled
        self._evidence_scope = evidence_scope
        self._context_id = context_id
        self._borrowed_pointers = borrowed_pointers
        self._pointers = pointers
        self._owned_pointer_snapshot = dict(pointers)
        self._allocation_owner = allocation_owner
        self._allocation_owner_snapshot = allocation_owner
        self._owned_capabilities = owned_capabilities
        self._owned_capability_snapshot = dict(owned_capabilities)
        self._pending_free_leases = (
            {} if pending_free_leases is None else pending_free_leases
        )
        self._external_free_succeeded = (
            set() if external_free_succeeded is None else external_free_succeeded
        )
        self._quarantine_pending: set[str] = set()
        self._poisoned_quarantine_pending: set[str] = set()
        self._orphan_cleanups = [] if orphan_cleanups is None else orphan_cleanups
        self._initial_managed_device_bytes = telemetry.current_device_bytes
        self._deallocation_success_sizes: dict[str, int] = {}
        self._free_acknowledged_roles: set[str] = set()
        self._free_quarantined_sizes: dict[str, int] = {}
        self._orphan_acknowledged_ids: set[int] = set()
        self._orphan_quarantined_sizes: dict[int, int] = {}
        self._unknown_orphan_requested_sizes: dict[int, int] = {}
        self._lineage_managed_roles = set(owned_capabilities)
        self._lineage_orphan_seen_ids = {
            cleanup.lease.lease_id for cleanup in self._orphan_cleanups
        }
        self._allocation_owner_closed = allocation_owner_closed
        self._allocation_lineage_snapshot = allocation_lineage
        self._owned_buffers = owned_buffers
        self._bindings_snapshot = _bindings(
            resident,
            overlay,
            lease_epoch,
            kernel_internally_compiled,
        )
        self._dimensions_snapshot = _dimensions(overlay)
        self._telemetry = telemetry
        self._opening_status = opening_status
        self._failure_reason = failure_reason
        self._closed = False
        self._poisoned = opening_status == "poisoned"
        self._cleanup_failed = opening_status == "cleanup_failed"
        self._cleanup_quarantined = opening_status == "cleanup_quarantined"
        self._kernel_closed = kernel_closed
        self._lease_released = False
        self._close_sync_complete = False
        self._sequence = 0
        self._last_apply: HipFreeSpaceApplyReceipt | None = None
        self._apply_witnesses: dict[int, tuple[int | None, str]] = {}
        self._krylov_consumer_token: object | None = None
        self._krylov_consumer_borrow_lease: HipAllocationBorrowLeaseV1 | None = None
        self._krylov_consumer_capability_snapshot: (
            tuple[HipAllocationCapabilityV1, ...] | None
        ) = None
        self._krylov_consumer_rollback_pending = False
        self._krylov_consumer_phase = "idle"
        self._released_krylov_consumer_token: object | None = None
        self._krylov_consumer_epoch_value = 0
        self._closing = False
        self._queue_lock = threading.RLock()
        self._recover_allocation_cleanup_authority()
        self._opening_receipt = self._build_receipt(opening_status)

    def __enter__(self) -> HipFreeSpaceExecutionContext:
        self._require_usable()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter cleanup
        try:
            self.close()
        except Exception:
            pass

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def opening_receipt(self) -> HipFreeSpaceContextReceipt:
        return self._opening_receipt

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def resident_context(self) -> HipResidentCsrExecutionContext:
        return self._resident

    def receipt(self) -> HipFreeSpaceContextReceipt:
        with self._queue_lock:
            # Retirement bookkeeping is the authoritative, interruption-safe
            # source.  Re-project it before every serialized observation so a
            # retry cannot expose stale success/quarantine counters.
            self._refresh_retirement_telemetry()
            self._refresh_lifecycle_terminal_telemetry()
            if self._cleanup_failed:
                status: ContextStatus = "cleanup_failed"
            elif self._cleanup_quarantined:
                status = "cleanup_quarantined"
            elif self._closed:
                status = "context_closed"
            elif self._poisoned:
                status = "poisoned"
            else:
                status = "context_ready"
            return self._build_receipt(status)

    def enqueue_operator_apply(self) -> HipFreeSpaceApplyReceipt:
        """Produce ``F-Ku`` on device, consume it once, then gather ``Jv_f``."""

        with self._queue_lock:
            self._require_no_krylov_consumer()
            return self._enqueue_operator_apply_locked()

    def _enqueue_operator_apply_locked(self) -> HipFreeSpaceApplyReceipt:
        self._require_usable()
        self._resident._require_downstream_consumer(self._lease_token)
        self._validate_authority()
        sequence = self._sequence + 1
        delta = HipFreeSpaceApplyDelta(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_attempt_count=self._telemetry.kernel_launch_attempt_count + 1,
        )
        try:
            result = self._kernel.launch_residual_direction(
                self._stream,
                self._plan.dof_count,
                self._overlay.free_dof_count,
                self._overlay.reduced_csr_nnz,
                self._pointers["global_to_free"],
                self._pointers["reduced_csr_row_ptr"],
                self._pointers["reduced_csr_column_indices"],
                self._pointers["reduced_csr_values"],
                self._pointers["reduced_state"],
                self._pointers["reduced_load"],
                self._pointers["reduced_direction"],
                self._pointers["reduced_residual"],
                self._borrowed_pointers["full_direction"],
                self._pointers["error_flag"],
            )
            if result is not None:
                _fail("hip_free_space_kernel_contract_invalid", "/apply/producer")
        except Exception as exc:
            return self._failed_apply(
                sequence,
                delta,
                "hip_free_space_direction_launch_failed",
                exc,
            )
        delta = replace(delta, producer_launch_success_count=1)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_success_count=self._telemetry.kernel_launch_success_count + 1,
        )
        generation: int | None = None
        resident_enqueue: HipResidentCsrEnqueueReceipt | None = None
        try:
            generation = self._resident._publish_device_direction(self._lease_token)
            resident_enqueue = self._resident._enqueue_residual_jvp_from_device(
                self._lease_token, generation
            )
            validate_hip_resident_csr_enqueue_receipt(
                resident_enqueue, expected_context=self._resident
            )
        except Exception as exc:
            return self._failed_apply(
                sequence,
                delta,
                "hip_free_space_resident_apply_failed",
                exc,
                direction_generation=generation,
                resident_enqueue=resident_enqueue,
            )
        delta = replace(
            delta,
            resident_launch_attempt_count=(
                resident_enqueue.telemetry_delta.kernel_launch_attempt_count
            ),
            resident_launch_success_count=(
                resident_enqueue.telemetry_delta.kernel_launch_success_count
            ),
        )
        if resident_enqueue.status != "enqueued":
            return self._failed_apply(
                sequence,
                delta,
                "hip_free_space_resident_apply_unavailable",
                resident_enqueue.reason.detail
                if resident_enqueue.reason is not None
                else "resident apply unavailable",
                direction_generation=generation,
                resident_enqueue=resident_enqueue,
            )

        delta = replace(delta, gather_launch_attempt_count=1)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_attempt_count=self._telemetry.kernel_launch_attempt_count + 1,
        )
        try:
            result = self._kernel.launch_gather_jvp(
                self._stream,
                self._plan.dof_count,
                self._overlay.free_dof_count,
                self._pointers["free_dofs"],
                self._borrowed_pointers["full_jvp"],
                self._pointers["reduced_jvp"],
                self._pointers["error_flag"],
            )
            if result is not None:
                _fail("hip_free_space_kernel_contract_invalid", "/apply/gather")
        except Exception as exc:
            return self._failed_apply(
                sequence,
                delta,
                "hip_free_space_gather_launch_failed",
                exc,
                direction_generation=generation,
                resident_enqueue=resident_enqueue,
            )
        delta = replace(delta, gather_launch_success_count=1)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_success_count=self._telemetry.kernel_launch_success_count + 1,
        )
        self._sequence = sequence
        receipt = _build_apply_receipt(
            status="enqueued",
            context=self,
            sequence=sequence,
            direction_generation=generation,
            resident_enqueue=resident_enqueue,
            delta=delta,
            reason=None,
        )
        self._record_apply_witness(receipt)
        return receipt

    def evaluate_for_verification(self) -> HipFreeSpaceEvaluation:
        """Export the composed result after one fence and replay CPU oracles."""

        with self._queue_lock:
            self._require_no_krylov_consumer()
            return self._evaluate_for_verification_locked()

    def _evaluate_for_verification_locked(self) -> HipFreeSpaceEvaluation:
        self._require_usable()
        apply = self._enqueue_operator_apply_locked()
        execution_id = canonical_hash(
            {
                "context_id": self._context_id,
                "opening_context_receipt_hash": (
                    self._opening_receipt.context_receipt_hash
                ),
                "apply_receipt_hash": apply.receipt_hash,
            }
        )
        if apply.status != "enqueued":
            return _unavailable_evaluation(
                self,
                execution_id,
                apply,
                HipFreeSpaceEvaluationDelta(0, 0, 0, 0, 0, 0, 0, 0, 0),
                "hip_free_space_apply_unavailable",
                apply.reason.detail if apply.reason else "apply unavailable",
            )

        host_arrays = {
            "reduced_values": np.empty(self._overlay.reduced_csr_nnz, dtype="<f8"),
            "reduced_state": np.empty(self._overlay.free_dof_count, dtype="<f8"),
            "reduced_load": np.empty(self._overlay.free_dof_count, dtype="<f8"),
            "residual_direction": np.empty(self._overlay.free_dof_count, dtype="<f8"),
            "reduced_jvp": np.empty(self._overlay.free_dof_count, dtype="<f8"),
            "full_residual": np.empty(self._plan.dof_count, dtype="<f8"),
            "full_direction": np.empty(self._plan.dof_count, dtype="<f8"),
        }
        pointer_names = {
            "reduced_values": "reduced_csr_values",
            "reduced_state": "reduced_state",
            "reduced_load": "reduced_load",
            "residual_direction": "reduced_direction",
            "reduced_jvp": "reduced_jvp",
            "full_residual": "full_residual",
            "full_direction": "full_direction",
        }
        delta = HipFreeSpaceEvaluationDelta(0, 0, 0, 0, 0, 0, 0, 0, 0)
        try:
            for name, host in host_arrays.items():
                delta = replace(
                    delta,
                    d2h_operation_attempt_count=delta.d2h_operation_attempt_count + 1,
                    d2h_bytes_attempted=delta.d2h_bytes_attempted + int(host.nbytes),
                )
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_attempt_count=(
                        self._telemetry.d2h_operation_attempt_count + 1
                    ),
                    d2h_bytes_attempted=(
                        self._telemetry.d2h_bytes_attempted + int(host.nbytes)
                    ),
                )
                pointer_name = pointer_names[name]
                pointer = (
                    self._borrowed_pointers[pointer_name]
                    if pointer_name in self._borrowed_pointers
                    else self._pointers[pointer_name]
                )
                self._runtime.copy_d2h_async(host, pointer, self._stream)
                delta = replace(
                    delta,
                    d2h_operation_success_count=delta.d2h_operation_success_count + 1,
                    d2h_bytes_succeeded=delta.d2h_bytes_succeeded + int(host.nbytes),
                )
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_success_count=(
                        self._telemetry.d2h_operation_success_count + 1
                    ),
                    d2h_bytes_succeeded=(
                        self._telemetry.d2h_bytes_succeeded + int(host.nbytes)
                    ),
                )
            error = np.empty(1, dtype="<i4")
            delta = replace(
                delta,
                d2h_operation_attempt_count=delta.d2h_operation_attempt_count + 1,
                d2h_bytes_attempted=delta.d2h_bytes_attempted + 4,
                sync_attempt_count=1,
            )
            self._telemetry = replace(
                self._telemetry,
                d2h_operation_attempt_count=(
                    self._telemetry.d2h_operation_attempt_count + 1
                ),
                d2h_bytes_attempted=self._telemetry.d2h_bytes_attempted + 4,
                error_flag_d2h_bytes=self._telemetry.error_flag_d2h_bytes + 4,
                sync_attempt_count=self._telemetry.sync_attempt_count + 1,
            )
            self._runtime.copy_d2h_async(
                error, self._pointers["error_flag"], self._stream
            )
            delta = replace(
                delta,
                d2h_operation_success_count=delta.d2h_operation_success_count + 1,
                d2h_bytes_succeeded=delta.d2h_bytes_succeeded + 4,
            )
            self._telemetry = replace(
                self._telemetry,
                d2h_operation_success_count=(
                    self._telemetry.d2h_operation_success_count + 1
                ),
                d2h_bytes_succeeded=self._telemetry.d2h_bytes_succeeded + 4,
            )
            self._runtime.synchronize(self._stream)
            delta = replace(delta, sync_success_count=1)
            self._telemetry = replace(
                self._telemetry,
                sync_success_count=self._telemetry.sync_success_count + 1,
            )
        except Exception as exc:
            self._poison("hip_free_space_verification_export_failed")
            return _unavailable_evaluation(
                self,
                execution_id,
                apply,
                delta,
                "hip_free_space_verification_export_failed",
                exc,
            )
        if int(error[0]) != 0:
            self._poison("hip_free_space_device_error")
            return _unavailable_evaluation(
                self,
                execution_id,
                apply,
                delta,
                "hip_free_space_device_error",
                f"device error code {int(error[0])}",
            )
        arrays = {
            name: immutable_array(value, dtype="<f8")
            for name, value in host_arrays.items()
        }
        expected = _cpu_expected_for_context(self)
        parity = _parity_report(arrays, expected, self._plan)
        status: EvaluationStatus = "verified" if parity.passed else "parity_failed"
        if not parity.passed:
            self._poison("hip_free_space_cpu_parity_failed")
        receipt = _build_evaluation_receipt(
            status=status,
            execution_id=execution_id,
            context=self,
            apply=apply,
            arrays=arrays,
            delta=delta,
            parity=parity,
            reason=None,
        )
        evaluation = HipFreeSpaceEvaluation(
            receipt,
            arrays["reduced_values"],
            arrays["reduced_state"],
            arrays["reduced_load"],
            arrays["residual_direction"],
            arrays["reduced_jvp"],
            arrays["full_residual"],
            arrays["full_direction"],
            apply,
        )
        return validate_hip_free_space_evaluation(evaluation, expected_context=self)

    def close(self) -> None:
        with self._queue_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            return
        if self._closing:
            _fail("hip_free_space_cleanup_reentrant", "/cleanup")
        self._closing = True
        try:
            self._require_no_krylov_consumer()
            if self._cleanup_failed:
                self._recover_allocation_cleanup_authority()
            self._refresh_lifecycle_terminal_telemetry()
            if not self._close_sync_complete and not self._cleanup_failed:
                try:
                    self._validate_cleanup_authority()
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_free_space_cleanup_authority_invalid",
                        "/cleanup/authority",
                        exc,
                    )
            if not self._close_sync_complete:
                self._telemetry = replace(
                    self._telemetry,
                    sync_attempt_count=self._telemetry.sync_attempt_count + 1,
                )
                try:
                    self._runtime.synchronize(self._stream)
                except Exception as exc:
                    self._poison("hip_free_space_cleanup_sync_failed")
                    self._raise_cleanup_error(
                        "hip_free_space_cleanup_sync_failed",
                        "/cleanup/synchronize",
                        exc,
                    )
                self._close_sync_complete = True
                self._telemetry = replace(
                    self._telemetry,
                    sync_success_count=self._telemetry.sync_success_count + 1,
                )

            first_error: Exception | None = None
            for orphan in tuple(self._orphan_cleanups):
                error = self._retire_orphan_cleanup(orphan)
                first_error = first_error or error
            for name in reversed(_OWNED_ORDER):
                error = self._retire_owned_allocation(name)
                first_error = first_error or error
            if self._owned_capabilities or self._orphan_cleanups:
                self._raise_cleanup_error(
                    "hip_free_space_cleanup_failed",
                    "/cleanup/owned_buffers",
                    first_error or "allocation lineage remains",
                )

            if self._allocation_owner is not None and not self._allocation_owner_closed:
                try:
                    self._allocation_owner.close()
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_free_space_lineage_owner_cleanup_failed",
                        "/cleanup/allocation_lineage/owner",
                        exc,
                    )
                self._allocation_owner_closed = True
                self._telemetry = replace(
                    self._telemetry,
                    lineage_owner_close_success_count=(
                        self._telemetry.lineage_owner_close_success_count + 1
                    ),
                )

            if not self._kernel_closed and self._kernel is not None:
                self._telemetry = replace(
                    self._telemetry,
                    module_close_attempt_count=(
                        self._telemetry.module_close_attempt_count + 1
                    ),
                )
                try:
                    self._kernel.close()
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_free_space_kernel_cleanup_failed",
                        "/cleanup/kernel",
                        exc,
                    )
                self._kernel_closed = True
                self._telemetry = replace(
                    self._telemetry,
                    module_close_success_count=(
                        self._telemetry.module_close_success_count + 1
                    ),
                )
            if not self._lease_released:
                self._telemetry = replace(
                    self._telemetry,
                    lease_release_attempt_count=(
                        self._telemetry.lease_release_attempt_count + 1
                    ),
                )
                try:
                    self._resident._release_downstream_consumer(self._lease_token)
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_free_space_lease_release_failed",
                        "/cleanup/lease",
                        exc,
                    )
                self._lease_released = True
                self._telemetry = replace(
                    self._telemetry,
                    lease_release_success_count=(
                        self._telemetry.lease_release_success_count + 1
                    ),
                )
            if self._cleanup_quarantined:
                self._failure_reason = HipFreeSpaceReason(
                    "hip_free_space_cleanup_quarantined",
                    "One or more allocator outcomes remain quarantined; no device free will be retried.",
                )
            else:
                self._failure_reason = None
            # Publish all terminal receipt state before the closed fast-path.
            # An interruption before `_closed` remains retryable; after it,
            # every serialized lifecycle counter is already converged.
            self._cleanup_failed = False
            self._refresh_lifecycle_terminal_telemetry()
            self._closed = True
        except BaseException as exc:
            if not isinstance(exc, Exception) and not self._closed:
                self._cleanup_failed = True
                self._failure_reason = HipFreeSpaceReason(
                    "hip_free_space_cleanup_interrupted",
                    _detail(exc),
                )
            raise
        finally:
            self._closing = False

    def _retire_owned_allocation(self, name: str) -> Exception | None:
        size = _buffer_view(self._owned_buffers, name).byte_length
        if name in self._free_acknowledged_roles:
            self._finish_owned_retirement(name, size, quarantined=False)
            return None
        if name in self._free_quarantined_sizes:
            self._finish_owned_retirement(name, size, quarantined=True)
            return None
        capability = self._owned_capabilities.get(name)
        if capability is None:
            return None
        owner = self._allocation_owner
        if owner is None:
            return HipFreeSpaceContextError(
                "hip_free_space_lineage_owner_missing",
                f"/cleanup/owned_buffers/{name}",
                "allocation capability has no owner",
            )
        try:
            if name in self._poisoned_quarantine_pending:
                owner.resolve_poisoned_allocation_quarantine(capability)
                self._finish_owned_retirement(name, size, quarantined=True)
                return None

            lease = self._pending_free_leases.get(name)
            if name in self._quarantine_pending:
                if lease is None:
                    _fail(
                        "hip_free_space_lineage_free_lease_missing",
                        f"/cleanup/owned_buffers/{name}",
                    )
                owner.resolve_free_quarantine(lease)
                self._finish_owned_retirement(name, size, quarantined=True)
                return None
            if name in self._external_free_succeeded:
                if lease is None:
                    _fail(
                        "hip_free_space_lineage_free_lease_missing",
                        f"/cleanup/owned_buffers/{name}",
                    )
                owner.resolve_free_success(lease)
                self._finish_owned_retirement(name, size, quarantined=False)
                return None

            validate_hip_allocation_owner_v1(owner)
            if lease is None:
                try:
                    lease = owner.begin_free(capability)
                except HipAllocationLineageError as exc:
                    if exc.code in {
                        "hip_allocation_capability_invalid",
                        "hip_allocation_capability_stale",
                        "hip_allocation_poisoned",
                        "hip_allocation_free_busy",
                        "hip_allocation_free_poisoned",
                    }:
                        self._poisoned_quarantine_pending.add(name)
                        owner.resolve_poisoned_allocation_quarantine(capability)
                        self._finish_owned_retirement(
                            name,
                            size,
                            quarantined=True,
                        )
                        return None
                    raise
                self._pending_free_leases[name] = lease
            self._telemetry = replace(
                self._telemetry,
                deallocation_attempt_count=(
                    self._telemetry.deallocation_attempt_count + 1
                ),
            )
            try:
                self._runtime.free(lease.pointer_snapshot)
                self._external_free_succeeded.add(name)
                self._deallocation_success_sizes[name] = size
            except BaseException as exc:
                self._external_free_succeeded.discard(name)
                self._deallocation_success_sizes.pop(name, None)
                if _free_outcome_known_not_freed(self._runtime, exc):
                    if isinstance(exc, Exception):
                        return exc
                    raise
                self._quarantine_pending.add(name)
                owner.resolve_free_quarantine(lease)
                self._finish_owned_retirement(name, size, quarantined=True)
                if isinstance(exc, Exception):
                    return None
                raise

            owner.resolve_free_success(lease)
            self._finish_owned_retirement(name, size, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_owned_retirement(
        self,
        name: str,
        size: int,
        *,
        quarantined: bool,
    ) -> None:
        if quarantined:
            self._cleanup_quarantined = True
            self._free_quarantined_sizes[name] = size
        else:
            self._free_acknowledged_roles.add(name)
        self._refresh_retirement_telemetry()
        self._pointers.pop(name, None)
        self._owned_pointer_snapshot.pop(name, None)
        self._pending_free_leases.pop(name, None)
        self._external_free_succeeded.discard(name)
        self._quarantine_pending.discard(name)
        self._poisoned_quarantine_pending.discard(name)
        self._owned_capability_snapshot.pop(name, None)
        # Keep the authoritative local capability reachable until every other
        # retirement field and telemetry projection has converged.
        self._owned_capabilities.pop(name, None)

    def _retire_orphan_cleanup(
        self,
        cleanup: _HipFreeSpaceOrphanCleanup,
    ) -> Exception | None:
        owner = self._allocation_owner
        if owner is None:
            return HipFreeSpaceContextError(
                "hip_free_space_lineage_owner_missing",
                "/cleanup/allocation_lineage/orphan",
                "orphan cleanup lease has no owner",
            )
        lease = cleanup.lease
        key = f"orphan:{lease.lease_id}"
        try:
            if cleanup.must_quarantine or cleanup.pointer is None:
                cleanup.quarantine_pending = True
            if cleanup.quarantine_pending:
                owner.resolve_orphan_free_quarantine(lease)
                self._finish_orphan_retirement(cleanup, quarantined=True)
                return None
            if cleanup.external_free_succeeded:
                owner.resolve_orphan_free_success(lease)
                self._finish_orphan_retirement(cleanup, quarantined=False)
                return None

            validate_hip_allocation_owner_v1(owner)
            self._telemetry = replace(
                self._telemetry,
                deallocation_attempt_count=(
                    self._telemetry.deallocation_attempt_count + 1
                ),
            )
            try:
                self._runtime.free(lease.pointer_snapshot)
                cleanup.external_free_succeeded = True
                self._deallocation_success_sizes[key] = cleanup.byte_length
            except BaseException as exc:
                cleanup.external_free_succeeded = False
                self._deallocation_success_sizes.pop(key, None)
                if _free_outcome_known_not_freed(self._runtime, exc):
                    if isinstance(exc, Exception):
                        return exc
                    raise
                cleanup.quarantine_pending = True
                owner.resolve_orphan_free_quarantine(lease)
                self._finish_orphan_retirement(cleanup, quarantined=True)
                if isinstance(exc, Exception):
                    return None
                raise

            owner.resolve_orphan_free_success(lease)
            self._finish_orphan_retirement(cleanup, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_orphan_retirement(
        self,
        cleanup: _HipFreeSpaceOrphanCleanup,
        *,
        quarantined: bool,
    ) -> None:
        lease_id = cleanup.lease.lease_id
        if quarantined:
            self._cleanup_quarantined = True
            if cleanup.pointer is None:
                self._unknown_orphan_requested_sizes[lease_id] = cleanup.byte_length
            else:
                self._orphan_quarantined_sizes[lease_id] = cleanup.byte_length
        else:
            self._orphan_acknowledged_ids.add(lease_id)
        self._refresh_retirement_telemetry()
        if cleanup in self._orphan_cleanups:
            self._orphan_cleanups.remove(cleanup)

    def _refresh_retirement_telemetry(self) -> None:
        successful_bytes = sum(self._deallocation_success_sizes.values())
        quarantined_bytes = sum(self._free_quarantined_sizes.values()) + sum(
            self._orphan_quarantined_sizes.values()
        )
        self._telemetry = replace(
            self._telemetry,
            deallocation_success_count=len(self._deallocation_success_sizes),
            current_device_bytes=max(
                0,
                self._initial_managed_device_bytes - successful_bytes,
            ),
            lineage_free_acknowledgement_count=len(self._free_acknowledged_roles),
            lineage_free_quarantine_count=len(self._free_quarantined_sizes),
            lineage_orphan_acknowledgement_count=len(self._orphan_acknowledged_ids),
            lineage_orphan_quarantine_count=(
                len(self._orphan_quarantined_sizes)
                + len(self._unknown_orphan_requested_sizes)
            ),
            quarantined_device_bytes=quarantined_bytes,
            unknown_malloc_outcome_count=len(self._unknown_orphan_requested_sizes),
            unknown_requested_bytes=sum(self._unknown_orphan_requested_sizes.values()),
        )

    def _refresh_lifecycle_terminal_telemetry(self) -> None:
        owner_closed = int(
            self._allocation_owner is not None and self._allocation_owner_closed
        )
        module_closed = int(
            self._telemetry.module_owner_acquired_count == 1 and self._kernel_closed
        )
        lease_released = int(self._lease_released)
        self._telemetry = replace(
            self._telemetry,
            lineage_owner_close_success_count=max(
                self._telemetry.lineage_owner_close_success_count,
                owner_closed,
            ),
            module_close_attempt_count=max(
                self._telemetry.module_close_attempt_count,
                module_closed,
            ),
            module_close_success_count=max(
                self._telemetry.module_close_success_count,
                module_closed,
            ),
            lease_release_attempt_count=max(
                self._telemetry.lease_release_attempt_count,
                lease_released,
            ),
            lease_release_success_count=max(
                self._telemetry.lease_release_success_count,
                lease_released,
            ),
        )

    def _recover_allocation_cleanup_authority(self) -> None:
        """Reconcile caller-handoff gaps from the owner's host registry."""

        owner = self._allocation_owner
        if owner is None:
            return
        if self._allocation_owner_closed or owner.closed:
            self._allocation_owner_closed = True
            self._refresh_lifecycle_terminal_telemetry()
            return
        capabilities, free_leases, orphan_leases = (
            snapshot_hip_allocation_owner_cleanup_v1(owner)
        )
        known_roles = set(_OWNED_ORDER)
        newly_managed_bytes = 0
        for capability in capabilities:
            identity_roles = tuple(
                role
                for role, known in self._owned_capability_snapshot.items()
                if known is capability
            )
            role = identity_roles[0] if len(identity_roles) == 1 else capability.role
            if type(role) is not str or role not in known_roles:
                _fail(
                    "hip_free_space_allocation_lineage_changed",
                    "/cleanup/allocation_lineage/capability",
                )
            if role not in self._lineage_managed_roles:
                self._lineage_managed_roles.add(role)
                newly_managed_bytes += _buffer_view(
                    self._owned_buffers,
                    role,
                ).byte_length
            self._owned_capabilities[role] = capability
            self._owned_capability_snapshot[role] = capability
            self._pointers[role] = capability.base
            self._owned_pointer_snapshot[role] = capability.base

        for lease in free_leases:
            identity_roles = tuple(
                role
                for role, known in self._owned_capability_snapshot.items()
                if known is lease.capability
            )
            role = (
                identity_roles[0] if len(identity_roles) == 1 else lease.capability.role
            )
            if type(role) is str and role in known_roles:
                self._pending_free_leases[role] = lease

        known_orphans = {cleanup.lease.lease_id for cleanup in self._orphan_cleanups}
        for lease in orphan_leases:
            if lease.lease_id in known_orphans:
                continue
            cleanup = _HipFreeSpaceOrphanCleanup(
                lease=lease,
                pointer=lease.pointer_snapshot,
                byte_length=lease.nbytes,
                # A missed caller handoff no longer carries the exact failure
                # classification.  Conservative quarantine is the only safe
                # default and never retries an unknown allocator outcome.
                must_quarantine=True,
            )
            self._orphan_cleanups.append(cleanup)
            known_orphans.add(lease.lease_id)
            if lease.lease_id not in self._lineage_orphan_seen_ids:
                self._lineage_orphan_seen_ids.add(lease.lease_id)
                if lease.pointer_snapshot is not None:
                    newly_managed_bytes += lease.nbytes

        if newly_managed_bytes:
            self._initial_managed_device_bytes += newly_managed_bytes
        managed_count = len(self._lineage_managed_roles)
        managed_bytes = sum(
            _buffer_view(self._owned_buffers, role).byte_length
            for role in self._lineage_managed_roles
        )
        live_orphan_managed_bytes = sum(
            cleanup.byte_length
            for cleanup in self._orphan_cleanups
            if cleanup.pointer is not None
        )
        self._initial_managed_device_bytes = max(
            self._initial_managed_device_bytes,
            managed_bytes + live_orphan_managed_bytes,
        )
        minimum_successes = managed_count + sum(
            cleanup.pointer is not None for cleanup in self._orphan_cleanups
        )
        minimum_attempts = minimum_successes + sum(
            cleanup.pointer is None for cleanup in self._orphan_cleanups
        )
        self._telemetry = replace(
            self._telemetry,
            allocation_attempt_count=max(
                self._telemetry.allocation_attempt_count,
                minimum_attempts,
            ),
            allocation_success_count=max(
                self._telemetry.allocation_success_count,
                minimum_successes,
            ),
            lineage_capability_mint_success_count=max(
                self._telemetry.lineage_capability_mint_success_count,
                managed_count,
            ),
            lineage_capability_mint_bytes=max(
                self._telemetry.lineage_capability_mint_bytes,
                managed_bytes,
            ),
            peak_device_bytes=max(
                self._telemetry.peak_device_bytes,
                self._initial_managed_device_bytes,
            ),
        )
        self._refresh_retirement_telemetry()
        self._allocation_lineage_snapshot = _allocation_lineage(self._telemetry)

    def _raise_cleanup_error(self, code: str, path: str, error: Any) -> None:
        self._cleanup_failed = True
        self._failure_reason = HipFreeSpaceReason(code, _detail(error))
        raise HipFreeSpaceContextError(
            code,
            path,
            self._failure_reason.detail,
            cleanup_owner=self,
        ) from (error if isinstance(error, BaseException) else None)

    def _failed_apply(
        self,
        sequence: int,
        delta: HipFreeSpaceApplyDelta,
        code: str,
        error: Any,
        *,
        direction_generation: int | None = None,
        resident_enqueue: HipResidentCsrEnqueueReceipt | None = None,
    ) -> HipFreeSpaceApplyReceipt:
        self._poison(code)
        receipt = _build_apply_receipt(
            status="unavailable",
            context=self,
            sequence=sequence,
            direction_generation=direction_generation,
            resident_enqueue=resident_enqueue,
            delta=delta,
            reason=HipFreeSpaceReason(code, _detail(error)),
        )
        self._record_apply_witness(receipt)
        return receipt

    def _record_apply_witness(self, receipt: HipFreeSpaceApplyReceipt) -> None:
        if receipt.sequence in self._apply_witnesses:
            _fail("hip_free_space_apply_sequence_reused", "/apply/sequence")
        self._apply_witnesses[receipt.sequence] = (
            receipt.direction_generation,
            receipt.receipt_hash,
        )
        self._last_apply = receipt

    def _acquire_krylov_consumer(self, token: object | None = None) -> object:
        """Exclusively lease reduced device buffers to one primitive child."""

        issued_token = object() if token is None else token
        try:
            with self._queue_lock:
                capabilities = self._prepare_krylov_consumer_locked(issued_token)
            return self._commit_krylov_consumer_borrow(
                issued_token,
                capabilities,
            )
        except BaseException:
            self._rollback_krylov_reservation_after_error(issued_token)
            raise

    def _acquire_krylov_consumer_for_apply(
        self,
        source_apply: HipFreeSpaceApplyReceipt,
        token: object | None = None,
    ) -> object:
        """Atomically bind the child lease to the exact latest device apply."""

        issued_token = object() if token is None else token
        try:
            with self._queue_lock:
                if (
                    type(source_apply) is not HipFreeSpaceApplyReceipt
                    or source_apply.status != "enqueued"
                    or source_apply is not self._last_apply
                    or source_apply.direction_generation is None
                    or self._apply_witnesses.get(source_apply.sequence)
                    != (source_apply.direction_generation, source_apply.receipt_hash)
                ):
                    _fail(
                        "hip_free_space_krylov_source_apply_not_latest",
                        "/lifetime/krylov_consumer/source_apply",
                    )
                capabilities = self._prepare_krylov_consumer_locked(issued_token)
            return self._commit_krylov_consumer_borrow(
                issued_token,
                capabilities,
            )
        except BaseException:
            self._rollback_krylov_reservation_after_error(issued_token)
            raise

    def _prepare_krylov_consumer_locked(
        self,
        token: object,
    ) -> tuple[HipAllocationCapabilityV1, ...]:
        """Reserve the semantic child token and snapshot its exact five buffers."""

        self._require_usable()
        self._resident._require_downstream_consumer(self._lease_token)
        self._validate_authority()
        self._resume_krylov_consumer_terminal_locked()
        if self._krylov_consumer_token is not None:
            _fail(
                "hip_free_space_krylov_consumer_active",
                "/lifetime/krylov_consumer",
            )
        capabilities = tuple(
            self._owned_capabilities[name]
            for name in (
                "reduced_csr_row_ptr",
                "reduced_csr_column_indices",
                "reduced_csr_values",
                "reduced_direction",
                "reduced_jvp",
            )
        )
        self._krylov_consumer_epoch_value += 1
        self._released_krylov_consumer_token = None
        self._krylov_consumer_capability_snapshot = capabilities
        # Reservation is unpublished to a child until the group lease commit
        # succeeds.  Keeping this marker set closes every interruption gap
        # between semantic reservation, registry borrow, and caller return.
        self._krylov_consumer_rollback_pending = True
        self._krylov_consumer_phase = "semantic_reserved"
        # Token publication is the final linearization point.  Every cleanup
        # field is already available if interruption occurs immediately after.
        self._krylov_consumer_token = token
        return capabilities

    def _commit_krylov_consumer_borrow(
        self,
        token: object,
        capabilities: tuple[HipAllocationCapabilityV1, ...],
    ) -> object:
        lease: HipAllocationBorrowLeaseV1 | None = None
        try:
            lease = borrow_hip_allocations_v1(capabilities, token)
            with self._queue_lock:
                if (
                    self._krylov_consumer_token is not token
                    or self._krylov_consumer_borrow_lease is not None
                    or self._krylov_consumer_capability_snapshot is not capabilities
                    or not self._krylov_consumer_rollback_pending
                    or self._krylov_consumer_phase != "semantic_reserved"
                ):
                    _fail(
                        "hip_free_space_krylov_consumer_transaction_changed",
                        "/lifetime/krylov_consumer",
                    )
                self._krylov_consumer_borrow_lease = lease
                self._krylov_consumer_rollback_pending = False
                self._krylov_consumer_phase = "active"
                return token
        except BaseException:
            with self._queue_lock:
                if (
                    self._krylov_consumer_token is token
                    and self._krylov_consumer_capability_snapshot is capabilities
                ):
                    self._krylov_consumer_rollback_pending = True
                    self._krylov_consumer_phase = "rollback_pending"
                    if self._krylov_consumer_borrow_lease is None:
                        self._krylov_consumer_borrow_lease = lease
                    try:
                        self._resume_krylov_consumer_terminal_locked()
                    except BaseException:
                        # Exact cleanup authority remains published on the
                        # context.  close() or the next acquire resumes it.
                        pass
            raise

    def _rollback_krylov_reservation_after_error(self, token: object) -> None:
        with self._queue_lock:
            if (
                self._krylov_consumer_token is token
                and self._krylov_consumer_phase == "semantic_reserved"
            ):
                self._krylov_consumer_rollback_pending = True
                self._krylov_consumer_phase = "rollback_pending"
            if (
                self._krylov_consumer_token is token
                and self._krylov_consumer_phase == "rollback_pending"
            ):
                try:
                    self._resume_krylov_consumer_terminal_locked()
                except BaseException:
                    pass

    def _require_krylov_consumer(self, token: object) -> None:
        """Require the exact live primitive-child capability."""

        with self._queue_lock:
            self._require_krylov_token(token)
            self._require_usable()
            self._resident._require_downstream_consumer(self._lease_token)
            self._validate_authority()
            self._validate_krylov_allocation_borrow_locked()

    def _krylov_consumer_epoch(self, token: object) -> int:
        with self._queue_lock:
            self._require_krylov_token(token)
            self._require_usable()
            self._validate_krylov_allocation_borrow_locked()
            return self._krylov_consumer_epoch_value

    def _krylov_consumer_epoch_if_owned(self, token: object) -> int | None:
        """Recover a pre-issued child token using host-only identity state."""

        with self._queue_lock:
            if token is self._krylov_consumer_token or (
                token is self._released_krylov_consumer_token
            ):
                return self._krylov_consumer_epoch_value
            return None

    def _krylov_parent_allocation_capabilities(
        self,
        token: object,
    ) -> tuple[HipAllocationCapabilityV1, ...]:
        with self._queue_lock:
            self._require_krylov_token(token)
            self._require_usable()
            self._validate_krylov_allocation_borrow_locked()
            assert self._krylov_consumer_capability_snapshot is not None
            return self._krylov_consumer_capability_snapshot

    def _open_krylov_allocation_owner(
        self,
        token: object,
        owner_role: str,
        *,
        _handoff: list[HipAllocationOwnerV1 | None] | None = None,
    ) -> HipAllocationOwnerV1:
        with self._queue_lock:
            self._require_krylov_token(token)
            self._require_usable()
            self._validate_krylov_allocation_borrow_locked()
            parent_owner = self._allocation_owner
            if parent_owner is None or self._allocation_owner_closed:
                _fail(
                    "hip_free_space_allocation_owner_unavailable",
                    "/lifetime/krylov_consumer/allocation_owner",
                )
        peer = open_hip_allocation_peer_owner_v1(
            parent_owner,
            owner_role,
            _handoff=_handoff,
        )
        try:
            with self._queue_lock:
                self._require_krylov_token(token)
                self._validate_krylov_allocation_borrow_locked()
        except BaseException:
            try:
                peer.close()
            finally:
                raise
        return peer

    def _poison_krylov_consumer(self, token: object, detail: str) -> None:
        """Share a primitive-child queue failure through the full owner chain."""

        with self._queue_lock:
            self._require_krylov_token(token)
            self._poison(detail)

    def _release_krylov_consumer(self, token: object) -> None:
        with self._queue_lock:
            if token is self._released_krylov_consumer_token:
                if self._krylov_consumer_token is token:
                    self._krylov_consumer_borrow_lease = None
                    self._krylov_consumer_capability_snapshot = None
                    self._krylov_consumer_token = None
                    self._krylov_consumer_rollback_pending = False
                    self._krylov_consumer_phase = "idle"
                elif self._krylov_consumer_token is not None:
                    _fail(
                        "hip_free_space_krylov_consumer_token_invalid",
                        "/lifetime/krylov_consumer",
                    )
                return
            self._require_krylov_token(token)
            lease = self._krylov_consumer_borrow_lease
            if lease is None:
                _fail(
                    "hip_free_space_krylov_allocation_borrow_invalid",
                    "/lifetime/krylov_consumer/allocation_lineage",
                )
            self._krylov_consumer_phase = "release_pending"
            release_hip_allocation_borrow_v1(lease)
            # Publish the exact terminal marker before clearing local fields;
            # release_hip_allocation_borrow_v1 is itself idempotent.
            self._released_krylov_consumer_token = token
            self._krylov_consumer_borrow_lease = None
            self._krylov_consumer_capability_snapshot = None
            self._krylov_consumer_token = None
            self._krylov_consumer_rollback_pending = False
            self._krylov_consumer_phase = "idle"

    def _resume_krylov_consumer_terminal_locked(self) -> None:
        token = self._krylov_consumer_token
        if token is None:
            self._krylov_consumer_borrow_lease = None
            self._krylov_consumer_capability_snapshot = None
            self._krylov_consumer_rollback_pending = False
            self._krylov_consumer_phase = "idle"
            return
        if token is self._released_krylov_consumer_token:
            self._krylov_consumer_borrow_lease = None
            self._krylov_consumer_capability_snapshot = None
            self._krylov_consumer_token = None
            self._krylov_consumer_rollback_pending = False
            self._krylov_consumer_phase = "idle"
            return
        if (
            self._krylov_consumer_phase == "release_pending"
            and not self._krylov_consumer_rollback_pending
        ):
            lease = self._krylov_consumer_borrow_lease
            if lease is None:
                _fail(
                    "hip_free_space_krylov_allocation_borrow_invalid",
                    "/lifetime/krylov_consumer/allocation_lineage",
                )
            release_hip_allocation_borrow_v1(lease)
            self._released_krylov_consumer_token = token
            self._krylov_consumer_borrow_lease = None
            self._krylov_consumer_capability_snapshot = None
            self._krylov_consumer_token = None
            self._krylov_consumer_phase = "idle"
            return
        if (
            not self._krylov_consumer_rollback_pending
            or self._krylov_consumer_phase != "rollback_pending"
        ):
            return
        capabilities = self._krylov_consumer_capability_snapshot
        if capabilities is None:
            _fail(
                "hip_free_space_krylov_allocation_borrow_invalid",
                "/lifetime/krylov_consumer/allocation_lineage",
            )
        lease = self._krylov_consumer_borrow_lease
        if lease is None:
            lease = recover_hip_allocation_borrow_v1(capabilities, token)
            self._krylov_consumer_borrow_lease = lease
        if lease is not None:
            release_hip_allocation_borrow_v1(lease)
        self._released_krylov_consumer_token = token
        self._krylov_consumer_borrow_lease = None
        self._krylov_consumer_capability_snapshot = None
        self._krylov_consumer_token = None
        self._krylov_consumer_rollback_pending = False
        self._krylov_consumer_phase = "idle"

    def _validate_krylov_allocation_borrow_locked(self) -> None:
        lease = self._krylov_consumer_borrow_lease
        capabilities = self._krylov_consumer_capability_snapshot
        if (
            self._krylov_consumer_phase != "active"
            or self._krylov_consumer_rollback_pending
            or lease is None
            or capabilities is None
            or lease.capabilities is not capabilities
        ):
            _fail(
                "hip_free_space_krylov_allocation_borrow_invalid",
                "/lifetime/krylov_consumer/allocation_lineage",
            )
        try:
            validate_hip_allocation_borrow_v1(lease)
        except HipAllocationLineageError as exc:
            raise HipFreeSpaceContextError(
                "hip_free_space_krylov_allocation_borrow_invalid",
                "/lifetime/krylov_consumer/allocation_lineage",
                _detail(exc),
            ) from exc

    def _require_krylov_token(self, token: object) -> None:
        if token is not self._krylov_consumer_token:
            _fail(
                "hip_free_space_krylov_consumer_token_invalid",
                "/lifetime/krylov_consumer",
            )

    def _require_no_krylov_consumer(self) -> None:
        self._resume_krylov_consumer_terminal_locked()
        if self._krylov_consumer_token is not None:
            _fail(
                "hip_free_space_krylov_consumer_active",
                "/lifetime/krylov_consumer",
                "Release the primitive child before using or closing its free-space owner.",
            )

    def _poison(self, detail: str) -> None:
        self._poisoned = True
        self._failure_reason = HipFreeSpaceReason(
            "hip_free_space_context_poisoned", _detail(detail)
        )
        if not self._resident.poisoned:
            try:
                self._resident._poison_downstream_consumer(self._lease_token, detail)
            except Exception:
                pass

    def _require_usable(self) -> None:
        if self._closed:
            _fail("hip_free_space_context_closed", "/status")
        if self._closing:
            _fail("hip_free_space_context_closing", "/status")
        if self._cleanup_failed:
            _fail("hip_free_space_context_cleanup_failed", "/status")
        if self._poisoned:
            _fail("hip_free_space_context_poisoned", "/status")

    def _validate_authority(self) -> None:
        try:
            changed = any(
                (
                    self._resident is not self._resident_snapshot,
                    self._runtime is not self._runtime_snapshot,
                    self._stream is not self._stream_snapshot,
                    self._resident._runtime is not self._runtime_snapshot,
                    self._resident._stream is not self._stream_snapshot,
                    self._resident.closed,
                    self._resident._state is not self._resident_state_snapshot,
                    self._overlay is not self._overlay_identity_snapshot,
                    self._plan is not self._plan_identity_snapshot,
                    self._overlay._source_execution_plan
                    is not self._plan_identity_snapshot,
                    _overlay_authority_signature(self._overlay)
                    != self._overlay_authority_snapshot,
                    _plan_authority_signature(self._plan)
                    != self._plan_authority_snapshot,
                    _bindings(
                        self._resident,
                        self._overlay,
                        self._lease_epoch,
                        self._kernel_internally_compiled,
                    )
                    != self._bindings_snapshot,
                    _dimensions(self._overlay) != self._dimensions_snapshot,
                )
            )
        except Exception:
            changed = True
        if changed:
            self._poison("hip_free_space_runtime_authority_changed")
            _fail("hip_free_space_runtime_authority_changed", "/resident")
        current = _borrowed_pointer_snapshot(self._resident)
        if any(
            current[name] is not self._borrowed_pointers[name]
            for name in _BORROWED_NAMES
        ):
            self._poison("hip_free_space_borrowed_pointer_changed")
            _fail("hip_free_space_borrowed_pointer_changed", "/resident/buffers")
        self._validate_owned_pointer_authority()
        identity = getattr(self._kernel, "identity", None)
        if (
            self._kernel is None
            or self._kernel is not self._kernel_object_snapshot
            or bool(getattr(self._kernel, "closed", False))
            or identity is not self._kernel_identity_snapshot
            or self._kernel_binding is None
            or getattr(identity, "identity_hash", None)
            != self._kernel_binding.identity_hash
        ):
            self._poison("hip_free_space_kernel_authority_changed")
            _fail("hip_free_space_kernel_authority_changed", "/kernel")

    def _validate_owned_pointer_authority(self) -> None:
        self._validate_owned_pointer_mapping_identity()
        owner = self._allocation_owner
        names = set(self._pointers)
        assert owner is not None
        for name in _OWNED_ORDER:
            if name not in names:
                continue
            capability = self._owned_capabilities[name]
            view = _buffer_view(self._owned_buffers, name)
            element_type = _lineage_element_type(view)
            try:
                validate_hip_allocation_capability_v1(
                    capability,
                    expected_owner=owner,
                )
            except HipAllocationLineageError as exc:
                self._poison("hip_free_space_allocation_lineage_changed")
                raise HipFreeSpaceContextError(
                    "hip_free_space_allocation_lineage_changed",
                    f"/owned_buffers/{name}",
                    _detail(exc),
                ) from exc
            if any(
                (
                    capability.role != name,
                    capability.base is not self._pointers[name],
                    capability.pointer_snapshot
                    != _pointer_snapshot_value(self._pointers[name]),
                    capability.nbytes != view.byte_length,
                    capability.element_type != element_type,
                    capability.runtime_owner is not self._runtime,
                    capability.device_ordinal
                    != self._resident._device_ordinal_snapshot,
                    capability.evidence_scope
                    != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                    capability.promotion_eligible,
                )
            ):
                self._poison("hip_free_space_allocation_lineage_changed")
                _fail(
                    "hip_free_space_allocation_lineage_changed",
                    f"/owned_buffers/{name}",
                )

    def _validate_owned_pointer_mapping_identity(self) -> None:
        owner = self._allocation_owner
        names = set(self._pointers)
        if (
            owner is None
            or owner is not self._allocation_owner_snapshot
            or names != set(self._owned_pointer_snapshot)
            or names != set(self._owned_capabilities)
            or names != set(self._owned_capability_snapshot)
            or any(
                self._pointers[name] is not pointer
                for name, pointer in self._owned_pointer_snapshot.items()
            )
            or any(
                self._owned_capabilities[name] is not capability
                for name, capability in self._owned_capability_snapshot.items()
            )
        ):
            self._poison("hip_free_space_owned_pointer_changed")
            _fail("hip_free_space_owned_pointer_changed", "/owned_buffers")

    def _validate_cleanup_authority(self) -> None:
        if any(
            (
                self._resident is not self._resident_snapshot,
                self._runtime is not self._runtime_snapshot,
                self._stream is not self._stream_snapshot,
                self._kernel is not self._kernel_object_snapshot,
                self._kernel is None,
                bool(getattr(self._kernel, "closed", False)),
            )
        ):
            self._poison("hip_free_space_cleanup_authority_changed")
            _fail("hip_free_space_cleanup_authority_changed", "/cleanup/authority")
        self._validate_owned_pointer_mapping_identity()

    def _build_receipt(self, status: ContextStatus) -> HipFreeSpaceContextReceipt:
        ready = status == "context_ready"
        return _build_context_receipt(
            status=status,
            context_id=self._context_id,
            evidence_scope=self._evidence_scope,
            actual_backend=(
                "hip"
                if self._evidence_scope == "native_hiprtc_free_space_composite"
                else "test_double"
            ),
            reason=(
                None
                if status in ("context_ready", "context_closed")
                else self._failure_reason
            ),
            bindings=self._bindings_snapshot,
            kernel=self._kernel_binding,
            dimensions=self._dimensions_snapshot,
            owned_buffers=self._owned_buffers,
            allocation_lineage=self._allocation_lineage_snapshot,
            telemetry=self._telemetry,
            claims=_claims(
                ready,
                self._evidence_scope,
                lease_active=not self._lease_released,
            ),
        )


_HIP_FREE_SPACE_CONTEXT_INITIALIZER = HipFreeSpaceExecutionContext.__init__


def open_hip_free_space_execution_context(
    resident: HipResidentCsrExecutionContext,
    overlay: HipFreeSpaceOperatorPlanV1,
    *,
    architecture: str | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    rtc_kernel: Any | None = None,
) -> HipFreeSpaceContextOpenResult:
    """Open the exclusive symbolic-only K_ff device overlay."""

    if type(resident) is not HipResidentCsrExecutionContext:
        _fail("hip_free_space_resident_type_invalid", "/resident")
    if type(overlay) is not HipFreeSpaceOperatorPlanV1:
        _fail("hip_free_space_plan_type_invalid", "/overlay")
    source_plan = resident._plan
    validate_execution_plan_v2(source_plan)
    validate_hip_free_space_operator_plan_v1(
        overlay, expected_execution_plan=source_plan
    )
    resident._require_usable()
    resident._parent._require_resident_consumer(resident._lease_token)
    _validate_zero_prescribed_state(resident, source_plan)
    # The caller-owned overlay remains only an input.  Recompile the exact
    # deterministic view so all live metadata and CPU witnesses are owned by
    # this context and cannot be changed through the caller's object graph.
    overlay_snapshot = compile_hip_free_space_operator_plan_v1(source_plan)
    if (
        overlay_snapshot.plan_id != overlay.plan_id
        or overlay_snapshot.plan_hash != overlay.plan_hash
        or overlay_snapshot.free_space_view_hash != overlay.free_space_view_hash
    ):
        _fail("hip_free_space_plan_snapshot_mismatch", "/overlay")
    overlay = overlay_snapshot
    requested_architecture = resident._parent._kernel_binding.architecture
    if architecture is not None and architecture != requested_architecture:
        _fail("hip_free_space_architecture_mismatch", "/architecture")
    if isinstance(memory_budget_bytes, bool) or (
        memory_budget_bytes is not None
        and (not isinstance(memory_budget_bytes, int) or memory_budget_bytes <= 0)
    ):
        _fail("hip_free_space_memory_budget_invalid", "/memory_budget_bytes")
    if rtc_kernel is not None:
        _preflight_kernel(rtc_kernel)

    views = _buffer_views(overlay)
    owned_bytes = sum(view.byte_length for view in views)
    if memory_budget_bytes is not None and owned_bytes > memory_budget_bytes:
        _fail(
            "hip_free_space_memory_budget_exceeded",
            "/memory_budget_bytes",
            f"Required {owned_bytes} bytes exceeds budget {memory_budget_bytes}.",
        )
    # Pre-issue the process-local token before the resident publishes it.  The
    # exact identity is therefore recoverable even if acquisition is
    # interrupted after the parent state changes but before caller return.
    token = object()
    lease_epoch = 0
    kernel_internally_compiled = rtc_kernel is None
    kernel = rtc_kernel
    kernel_handoff = _HipRtcFreeSpaceKernelHandoff()
    binding: HipFreeSpaceKernelBinding | None = None
    pointers: dict[str, Any] = {}
    allocation_owner: HipAllocationOwnerV1 | None = None
    allocation_owner_handoff: list[HipAllocationOwnerV1 | None] = [None]
    owned_capabilities: dict[str, HipAllocationCapabilityV1] = {}
    pending_free_leases: dict[str, HipAllocationFreeLeaseV1] = {}
    external_free_succeeded: set[str] = set()
    orphan_cleanups: list[_HipFreeSpaceOrphanCleanup] = []
    borrowed_pointers: dict[str, Any] = {}
    telemetry = HipFreeSpaceTelemetry(
        module_owner_acquired_count=int(kernel is not None)
    )
    evidence_scope: EvidenceScope = "injected_test_double"
    context_id = _ZERO_HASH
    context: HipFreeSpaceExecutionContext | None = None
    try:
        resident._acquire_downstream_consumer(token)
        lease_epoch = resident._downstream_consumer_epoch(token)
        context_id = _fallback_context_id(resident, overlay, lease_epoch, None)
        borrowed_pointers = _borrowed_pointer_snapshot(resident)
        selector = getattr(resident._runtime, "set_device", None)
        if callable(selector):
            selector(resident._device_ordinal_snapshot)
        if kernel is None:
            loaded = _loaded_runtime(resident)
            if not callable(getattr(loaded, "bind", None)):
                _fail("hip_free_space_runtime_invalid", "/kernel/compile")
            try:
                kernel = _compile_free_space_operator_with_handoff(
                    compile_hip_rtc_free_space_operator_kernel,
                    kernel_handoff,
                    loaded,
                    requested_architecture,
                    hiprtc_library,
                )
            except HipRtcFreeSpaceError as exc:
                if exc.cleanup_owner is not None:
                    kernel = exc.cleanup_owner
                    telemetry = replace(
                        telemetry,
                        module_owner_acquired_count=1,
                    )
                raise HipFreeSpaceContextError(
                    exc.code, "/kernel/compile", exc.message
                ) from exc
            telemetry = replace(telemetry, module_owner_acquired_count=1)
        binding = _kernel_binding(kernel, requested_architecture)
        evidence_scope = _evidence_scope(
            resident, kernel, binding, kernel_internally_compiled
        )
        context_id = _context_id(
            resident, overlay, lease_epoch, binding, evidence_scope
        )
        runtime = resident._runtime
        allocation_owner = _open_integrated_hip_allocation_owner_v1(
            runtime,
            resident._device_ordinal_snapshot,
            "free_space_owned_buffers",
            _handoff=allocation_owner_handoff,
        )
        telemetry = replace(
            telemetry,
            lineage_owner_open_success_count=1,
        )
        for view in views:
            telemetry = replace(
                telemetry,
                allocation_attempt_count=telemetry.allocation_attempt_count + 1,
            )
            try:
                capability = allocation_owner.allocate(
                    view.name,
                    view.byte_length,
                    _lineage_element_type(view),
                )
            except HipAllocationLineageError as exc:
                orphan = exc.orphan_cleanup_lease
                if orphan is not None:
                    orphan_cleanups.append(
                        _HipFreeSpaceOrphanCleanup(
                            lease=orphan,
                            pointer=orphan.pointer_snapshot,
                            byte_length=orphan.nbytes,
                            must_quarantine=exc.code
                            in {
                                "hip_allocation_range_overlap",
                                "hip_allocation_range_overflow",
                                "hip_allocation_domain_poisoned",
                                "hip_allocation_malloc_outcome_uncertain",
                            },
                        )
                    )
                    if orphan.pointer_snapshot is not None:
                        current = telemetry.current_device_bytes + orphan.nbytes
                        telemetry = replace(
                            telemetry,
                            allocation_success_count=(
                                telemetry.allocation_success_count + 1
                            ),
                            current_device_bytes=current,
                            peak_device_bytes=max(
                                telemetry.peak_device_bytes,
                                current,
                            ),
                        )
                raise
            pointer = capability.base
            pointers[view.name] = pointer
            owned_capabilities[view.name] = capability
            current = telemetry.current_device_bytes + view.byte_length
            telemetry = replace(
                telemetry,
                allocation_success_count=telemetry.allocation_success_count + 1,
                lineage_capability_mint_success_count=(
                    telemetry.lineage_capability_mint_success_count + 1
                ),
                lineage_capability_mint_bytes=(
                    telemetry.lineage_capability_mint_bytes + view.byte_length
                ),
                current_device_bytes=current,
                peak_device_bytes=max(telemetry.peak_device_bytes, current),
            )
            host = _initial_host_array(overlay, view.name)
            if host is None:
                continue
            telemetry = replace(
                telemetry,
                h2d_operation_attempt_count=telemetry.h2d_operation_attempt_count + 1,
                h2d_bytes_attempted=telemetry.h2d_bytes_attempted + view.byte_length,
            )
            runtime.copy_h2d_async(pointer, host, resident._stream)
            telemetry = replace(
                telemetry,
                h2d_operation_success_count=telemetry.h2d_operation_success_count + 1,
                h2d_bytes_succeeded=telemetry.h2d_bytes_succeeded + view.byte_length,
                symbolic_h2d_bytes=(
                    telemetry.symbolic_h2d_bytes
                    + (view.byte_length if view.name in _SYMBOLIC_NAMES else 0)
                ),
                error_flag_h2d_bytes=(
                    telemetry.error_flag_h2d_bytes
                    + (view.byte_length if view.name == "error_flag" else 0)
                ),
            )

        telemetry = replace(
            telemetry,
            kernel_launch_attempt_count=telemetry.kernel_launch_attempt_count + 1,
        )
        result = kernel.launch_materialize(
            resident._stream,
            source_plan.dof_count,
            source_plan.nnz,
            overlay.free_dof_count,
            overlay.reduced_csr_nnz,
            pointers["free_dofs"],
            pointers["reduced_csr_global_value_indices"],
            borrowed_pointers["full_csr_values"],
            borrowed_pointers["full_state"],
            borrowed_pointers["full_load"],
            pointers["reduced_csr_values"],
            pointers["reduced_state"],
            pointers["reduced_load"],
            pointers["error_flag"],
        )
        if result is not None:
            _fail("hip_free_space_kernel_contract_invalid", "/kernel/materialize")
        telemetry = replace(
            telemetry,
            kernel_launch_success_count=telemetry.kernel_launch_success_count + 1,
        )
        host_error = np.empty(1, dtype="<i4")
        telemetry = replace(
            telemetry,
            d2h_operation_attempt_count=telemetry.d2h_operation_attempt_count + 1,
            d2h_bytes_attempted=telemetry.d2h_bytes_attempted + 4,
            error_flag_d2h_bytes=telemetry.error_flag_d2h_bytes + 4,
            sync_attempt_count=telemetry.sync_attempt_count + 1,
        )
        runtime.copy_d2h_async(host_error, pointers["error_flag"], resident._stream)
        telemetry = replace(
            telemetry,
            d2h_operation_success_count=telemetry.d2h_operation_success_count + 1,
            d2h_bytes_succeeded=telemetry.d2h_bytes_succeeded + 4,
        )
        runtime.synchronize(resident._stream)
        telemetry = replace(
            telemetry,
            sync_success_count=telemetry.sync_success_count + 1,
        )
        if int(host_error[0]) != 0:
            _fail(
                "hip_free_space_materialize_device_error",
                "/kernel/materialize",
                f"device error code {int(host_error[0])}",
            )
        # Preallocate the cleanup owner before initialization transfers any
        # live resource references into it.  This removes the constructor
        # return/STORE handoff gap and lets the failure path reuse the exact
        # same authority after validation or return-path interruption.
        context = object.__new__(HipFreeSpaceExecutionContext)
        _HIP_FREE_SPACE_CONTEXT_INITIALIZER(
            context,
            resident=resident,
            overlay=overlay,
            lease_token=token,
            lease_epoch=lease_epoch,
            kernel=kernel,
            kernel_binding=binding,
            kernel_internally_compiled=kernel_internally_compiled,
            evidence_scope=evidence_scope,
            context_id=context_id,
            borrowed_pointers=borrowed_pointers,
            pointers=pointers,
            allocation_owner=allocation_owner,
            owned_capabilities=owned_capabilities,
            pending_free_leases=pending_free_leases,
            external_free_succeeded=external_free_succeeded,
            orphan_cleanups=orphan_cleanups,
            allocation_owner_closed=False,
            allocation_lineage=_allocation_lineage(telemetry),
            owned_buffers=views,
            telemetry=telemetry,
            opening_status="context_ready",
            failure_reason=None,
        )
        validate_hip_free_space_context_receipt(
            context.opening_receipt, expected_context=context
        )
        return HipFreeSpaceContextOpenResult(context, context.opening_receipt)
    except BaseException as primary:
        recovered_epoch = resident._downstream_consumer_epoch_if_owned(token)
        if recovered_epoch is None:
            # No resident state was published, so no cleanup authority exists
            # and the preflight/acquisition failure can propagate unchanged.
            raise
        lease_epoch = recovered_epoch
        if context_id == _ZERO_HASH:
            context_id = _fallback_context_id(
                resident,
                overlay,
                lease_epoch,
                None,
            )
        if allocation_owner is None:
            allocation_owner = allocation_owner_handoff[0]
        if allocation_owner is not None:
            telemetry = replace(
                telemetry,
                lineage_owner_open_success_count=max(
                    telemetry.lineage_owner_open_success_count,
                    1,
                ),
            )
        if kernel is None and kernel_handoff.kernel is not None:
            kernel = kernel_handoff.kernel
        if kernel is not None:
            telemetry = replace(
                telemetry,
                module_owner_acquired_count=max(
                    telemetry.module_owner_acquired_count,
                    1,
                ),
            )
        cleanup_result = _cleanup_failed_open(
            primary=primary,
            resident=resident,
            overlay=overlay,
            token=token,
            lease_epoch=lease_epoch,
            kernel=kernel,
            binding=binding,
            kernel_internally_compiled=kernel_internally_compiled,
            evidence_scope=evidence_scope,
            context_id=context_id,
            borrowed_pointers=borrowed_pointers,
            pointers=pointers,
            allocation_owner=allocation_owner,
            owned_capabilities=owned_capabilities,
            pending_free_leases=pending_free_leases,
            external_free_succeeded=external_free_succeeded,
            orphan_cleanups=orphan_cleanups,
            views=views,
            telemetry=telemetry,
            existing_context=context,
        )
        if isinstance(primary, Exception):
            return cleanup_result
        if cleanup_result.context is not None:
            raise HipFreeSpaceContextError(
                "hip_free_space_context_open_interrupted",
                "/open",
                _detail(primary),
                cleanup_owner=cleanup_result.context,
            ) from primary
        raise


def _cleanup_failed_open(
    *,
    primary: BaseException,
    resident: HipResidentCsrExecutionContext,
    overlay: HipFreeSpaceOperatorPlanV1,
    token: object,
    lease_epoch: int,
    kernel: Any,
    binding: HipFreeSpaceKernelBinding | None,
    kernel_internally_compiled: bool,
    evidence_scope: EvidenceScope,
    context_id: str,
    borrowed_pointers: dict[str, Any],
    pointers: dict[str, Any],
    allocation_owner: HipAllocationOwnerV1 | None,
    owned_capabilities: dict[str, HipAllocationCapabilityV1],
    pending_free_leases: dict[str, HipAllocationFreeLeaseV1],
    external_free_succeeded: set[str],
    orphan_cleanups: list[_HipFreeSpaceOrphanCleanup],
    views: tuple[HipFreeSpaceBufferView, ...],
    telemetry: HipFreeSpaceTelemetry,
    existing_context: HipFreeSpaceExecutionContext | None = None,
) -> HipFreeSpaceContextOpenResult:
    reason = HipFreeSpaceReason(
        "hip_free_space_context_cleanup_failed",
        _detail(primary),
    )
    context_arguments: dict[str, Any] = {
        "resident": resident,
        "overlay": overlay,
        "lease_token": token,
        "lease_epoch": lease_epoch,
        "kernel": kernel,
        "kernel_binding": binding,
        "kernel_internally_compiled": kernel_internally_compiled,
        "evidence_scope": evidence_scope,
        "context_id": context_id,
        "borrowed_pointers": borrowed_pointers,
        "pointers": pointers,
        "allocation_owner": allocation_owner,
        "owned_capabilities": owned_capabilities,
        "pending_free_leases": pending_free_leases,
        "external_free_succeeded": external_free_succeeded,
        "orphan_cleanups": orphan_cleanups,
        "allocation_owner_closed": False,
        "allocation_lineage": (
            _allocation_lineage(telemetry) if allocation_owner is not None else None
        ),
        "owned_buffers": views,
        "telemetry": telemetry,
        "opening_status": "cleanup_failed",
        "failure_reason": reason,
        "kernel_closed": kernel is None,
    }
    if existing_context is not None and hasattr(existing_context, "_queue_lock"):
        context = existing_context
        context._failure_reason = reason
        context._cleanup_failed = True
    else:
        try:
            context = HipFreeSpaceExecutionContext(**context_arguments)
        except BaseException:
            # Preserve a constructor-independent cleanup path.  Tests can
            # inject a failing public constructor, and a partially failed
            # ready-context construction can still converge through the
            # original initializer.
            context = object.__new__(HipFreeSpaceExecutionContext)
            _HIP_FREE_SPACE_CONTEXT_INITIALIZER(context, **context_arguments)
    context._close_sync_complete = not pointers and not any(
        cleanup.pointer is not None for cleanup in orphan_cleanups
    )
    try:
        context.close()
    except BaseException as cleanup_error:
        context._failure_reason = HipFreeSpaceReason(
            "hip_free_space_context_cleanup_failed",
            _detail(f"{_detail(primary)}; cleanup: {_detail(cleanup_error)}"),
        )
        context._cleanup_failed = True
        context._opening_receipt = context._build_receipt("cleanup_failed")
        return HipFreeSpaceContextOpenResult(context, context.opening_receipt)

    telemetry = context._telemetry
    lineage = context._allocation_lineage_snapshot
    if context._cleanup_quarantined:
        receipt = _build_context_receipt(
            status="cleanup_quarantined",
            context_id=context_id,
            evidence_scope=evidence_scope,
            actual_backend=(
                "hip"
                if evidence_scope == "native_hiprtc_free_space_composite"
                else "test_double"
            ),
            reason=context._failure_reason,
            bindings=_bindings(
                resident,
                overlay,
                lease_epoch,
                kernel_internally_compiled,
            ),
            kernel=binding,
            dimensions=_dimensions(overlay),
            owned_buffers=(),
            allocation_lineage=lineage,
            telemetry=telemetry,
            claims=_claims(False, evidence_scope, lease_active=False),
        )
        return HipFreeSpaceContextOpenResult(None, receipt)

    reason = HipFreeSpaceReason("hip_free_space_context_open_failed", _detail(primary))
    receipt = _build_context_receipt(
        status="unavailable",
        context_id=context_id,
        evidence_scope=evidence_scope,
        actual_backend=None,
        reason=reason,
        bindings=_bindings(resident, overlay, lease_epoch, kernel_internally_compiled),
        kernel=binding,
        dimensions=_dimensions(overlay),
        owned_buffers=(),
        allocation_lineage=lineage,
        telemetry=telemetry,
        claims=_claims(False, evidence_scope, lease_active=False),
    )
    return HipFreeSpaceContextOpenResult(None, receipt)


def _buffer_views(
    overlay: HipFreeSpaceOperatorPlanV1,
) -> tuple[HipFreeSpaceBufferView, ...]:
    views: list[HipFreeSpaceBufferView] = []
    for name in _SYMBOLIC_NAMES:
        array = overlay.array(name)
        views.append(
            HipFreeSpaceBufferView(
                name,
                "<i4",
                tuple(int(value) for value in array.shape),
                int(array.nbytes),
                array_data_hash(array),
                "read_only",
                "async_h2d_once_then_same_stream_fence",
            )
        )
    f = overlay.free_dof_count
    z = overlay.reduced_csr_nnz
    for name, shape, access in (
        ("reduced_csr_values", (z,), "read_only_after_materialize"),
        ("reduced_state", (f,), "read_only_after_materialize"),
        ("reduced_load", (f,), "read_only_after_materialize"),
        ("reduced_direction", (f,), "write_only"),
        ("reduced_residual", (f,), "write_only"),
        ("reduced_jvp", (f,), "write_only"),
    ):
        views.append(
            HipFreeSpaceBufferView(
                name,
                "<f8",
                shape,
                8 * shape[0],
                None,
                access,
                "device_only",
            )
        )
    views.append(
        HipFreeSpaceBufferView(
            "error_flag",
            "<i4",
            (1,),
            4,
            array_data_hash(immutable_array([0], dtype="<i4")),
            "read_write",
            "async_h2d_zero_once_then_same_stream_fence",
        )
    )
    return tuple(views)


def _lineage_element_type(view: HipFreeSpaceBufferView) -> str:
    if view.dtype == "<i4":
        return "i32"
    if view.dtype == "<f8":
        return "f64"
    _fail(
        "hip_free_space_lineage_element_type_invalid",
        f"/owned_buffers/{view.name}/dtype",
    )


def _allocation_lineage(
    telemetry: HipFreeSpaceTelemetry,
) -> HipFreeSpaceAllocationLineage:
    count = telemetry.lineage_capability_mint_success_count
    return HipFreeSpaceAllocationLineage(
        capability_profile="foundation_non_promoting",
        evidence_scope="foundation_non_promoting",
        owner_role="free_space_owned_buffers",
        runtime_device_bound=True,
        managed_buffer_count=count,
        managed_device_bytes=telemetry.lineage_capability_mint_bytes,
        all_owned_buffers_managed=count == len(_OWNED_ORDER),
    )


def _pointer_snapshot_value(pointer: object) -> int:
    if type(pointer) is int:
        return pointer
    if type(pointer) is ctypes.c_void_p and type(pointer.value) is int:
        return pointer.value
    _fail("hip_free_space_owned_pointer_changed", "/owned_buffers")


def _free_outcome_known_not_freed(
    runtime: object,
    error: BaseException,
) -> bool:
    # A native call has crossed the FFI boundary before any Python exception
    # is observed, so it is always uncertain.  For an injected runtime, only
    # the exact package-sealed exception is retry authority; subclasses and
    # caller-controlled attributes cannot downgrade an unknown outcome.
    return (
        type(runtime) is not _BoundHipContextRuntime
        and type(error) is HipFreeKnownNotFreedError
    )


def _initial_host_array(
    overlay: HipFreeSpaceOperatorPlanV1, name: str
) -> np.ndarray | None:
    if name in _SYMBOLIC_NAMES:
        return overlay.array(name)
    if name == "error_flag":
        return immutable_array([0], dtype="<i4")
    return None


def _borrowed_pointer_snapshot(
    resident: HipResidentCsrExecutionContext,
) -> dict[str, Any]:
    snapshot = {
        "full_csr_values": resident._borrowed_pointers.get("csr_values"),
        "full_state": resident._pointers.get("state_displacement"),
        "full_load": resident._borrowed_pointers.get("load_vector_si"),
        "full_direction": resident._pointers.get("direction_workspace"),
        "full_residual": resident._pointers.get("residual_workspace"),
        "full_jvp": resident._pointers.get("jvp_workspace"),
    }
    if any(snapshot[name] is None for name in _BORROWED_NAMES):
        _fail("hip_free_space_borrowed_buffer_missing", "/resident/buffers")
    return snapshot


def _buffer_view(
    views: tuple[HipFreeSpaceBufferView, ...], name: str
) -> HipFreeSpaceBufferView:
    for view in views:
        if view.name == name:
            return view
    _fail("hip_free_space_owned_buffer_missing", f"/owned_buffers/{name}")


def _loaded_runtime(resident: HipResidentCsrExecutionContext) -> Any:
    runtime = resident._parent._runtime
    return getattr(runtime, "_loaded", runtime)


def _preflight_kernel(kernel: Any) -> None:
    try:
        methods = (
            getattr(kernel, "launch_materialize", None),
            getattr(kernel, "launch_residual_direction", None),
            getattr(kernel, "launch_gather_jvp", None),
            getattr(kernel, "close", None),
        )
        closed = bool(getattr(kernel, "closed", False))
    except Exception as exc:
        raise HipFreeSpaceContextError(
            "hip_free_space_kernel_contract_invalid", "/rtc_kernel", _detail(exc)
        ) from exc
    if not all(callable(method) for method in methods):
        _fail("hip_free_space_kernel_contract_invalid", "/rtc_kernel")
    if closed:
        _fail("hip_free_space_kernel_closed", "/rtc_kernel/closed")


def _kernel_binding(kernel: Any, architecture: str) -> HipFreeSpaceKernelBinding:
    identity = getattr(kernel, "identity", None)
    if identity is None or not callable(getattr(identity, "to_dict", None)):
        _fail("hip_free_space_kernel_identity_invalid", "/kernel/identity")
    try:
        manifest = identity.to_dict()
    except Exception as exc:
        raise HipFreeSpaceContextError(
            "hip_free_space_kernel_identity_invalid",
            "/kernel/identity",
            _detail(exc),
        ) from exc
    if not isinstance(manifest, dict):
        _fail("hip_free_space_kernel_identity_invalid", "/kernel/identity")
    symbols = manifest.get("kernel_symbols")
    geometry = manifest.get("launch_geometry")
    runtime = manifest.get("runtime_library")
    hiprtc = manifest.get("hiprtc_library")
    if not all(
        isinstance(value, dict) for value in (symbols, geometry, runtime, hiprtc)
    ):
        _fail("hip_free_space_kernel_identity_invalid", "/kernel/identity")
    binding = HipFreeSpaceKernelBinding(
        abi_version=int(manifest.get("abi_version", -1)),
        architecture=str(manifest.get("architecture", "")),
        materialize_symbol=str(symbols.get("materialize", "")),
        residual_direction_symbol=str(symbols.get("residual_direction", "")),
        gather_jvp_symbol=str(symbols.get("gather_jvp", "")),
        block_size=int(geometry.get("block_size", -1)),
        source_resource=str(manifest.get("source_resource", "")),
        source_sha256=str(manifest.get("source_sha256", "")),
        code_object_sha256=str(manifest.get("code_object_sha256", "")),
        identity_hash=str(manifest.get("identity_hash", "")),
        runtime_library_discovery_source=str(runtime.get("discovery_source", "")),
        runtime_library_sha256=str(runtime.get("sha256", "")),
        hiprtc_library_discovery_source=str(hiprtc.get("discovery_source", "")),
        hiprtc_library_sha256=str(hiprtc.get("sha256", "")),
    )
    _validate_kernel_binding(binding, architecture)
    _preflight_kernel(kernel)
    return binding


def _validate_kernel_binding(
    binding: HipFreeSpaceKernelBinding, architecture: str | None = None
) -> None:
    from .free_space_rtc import (
        HIP_RTC_FREE_SPACE_ABI_VERSION,
        HIP_RTC_FREE_SPACE_BLOCK_SIZE,
        HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
        HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
    )

    if any(
        (
            binding.abi_version != HIP_RTC_FREE_SPACE_ABI_VERSION,
            binding.block_size != HIP_RTC_FREE_SPACE_BLOCK_SIZE,
            binding.materialize_symbol != HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
            binding.residual_direction_symbol
            != HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
            binding.gather_jvp_symbol != HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
            not binding.source_resource.endswith(".hip.cpp"),
            architecture is not None and binding.architecture != architecture,
        )
    ):
        _fail("hip_free_space_kernel_binding_invalid", "/kernel")
    for value in (
        binding.source_sha256,
        binding.code_object_sha256,
        binding.identity_hash,
        binding.runtime_library_sha256,
        binding.hiprtc_library_sha256,
    ):
        _require_hash(value, "/kernel")
    allowed = {"explicit", "opt_rocm", "system_loader", "injected"}
    if (
        binding.runtime_library_discovery_source not in allowed
        or binding.hiprtc_library_discovery_source not in allowed
    ):
        _fail("hip_free_space_kernel_binding_invalid", "/kernel/libraries")


def _evidence_scope(
    resident: HipResidentCsrExecutionContext,
    kernel: Any,
    binding: HipFreeSpaceKernelBinding,
    internally_compiled: bool,
) -> EvidenceScope:
    parent_binding = resident._parent._kernel_binding
    native = (
        internally_compiled
        and resident._evidence_scope == "native_hiprtc_composite"
        and type(_loaded_runtime(resident)) is LoadedHipRuntime
        and type(kernel) is HipRtcFreeSpaceOperatorKernel
        and binding.architecture == parent_binding.architecture
        and binding.runtime_library_sha256 == parent_binding.runtime_library_sha256
        and binding.runtime_library_discovery_source != "injected"
        and binding.hiprtc_library_discovery_source != "injected"
    )
    return "native_hiprtc_free_space_composite" if native else "injected_test_double"


def _dimensions(overlay: HipFreeSpaceOperatorPlanV1) -> HipFreeSpaceDimensions:
    return HipFreeSpaceDimensions(
        overlay.global_dof_count,
        overlay.free_dof_count,
        overlay.constrained_dof_count,
        overlay.full_csr_nnz,
        overlay.reduced_csr_nnz,
    )


def _overlay_authority_signature(
    overlay: HipFreeSpaceOperatorPlanV1,
) -> tuple[Any, ...]:
    return (
        overlay.schema_version,
        overlay.capability_profile,
        overlay.plan_id,
        overlay.plan_hash,
        overlay.free_space_view_hash,
        overlay.source_execution_plan_hash,
        overlay.source_operator_hash,
        overlay.source_numeric_snapshot_hash,
        overlay.source_symbolic_reuse_hash,
        overlay.source_partition_hash,
        overlay.global_dof_count,
        overlay.constrained_dof_count,
        overlay.free_dof_count,
        overlay.full_csr_nnz,
        overlay.reduced_csr_nnz,
        tuple(id(row) for row in overlay.descriptors),
        tuple(id(array) for array in overlay._arrays),
        id(overlay._source_execution_plan),
    )


def _plan_authority_signature(plan: ExecutionPlanV2) -> tuple[Any, ...]:
    return (
        plan.schema_version,
        plan.capability_profile,
        plan.plan_id,
        plan.plan_hash,
        plan.operator_hash,
        plan.numeric_snapshot_hash,
        plan.symbolic_reuse_hash,
        plan.partition_hash,
        plan.load_pattern_id,
        plan.dof_count,
        plan.nnz,
        plan.reduced_nnz,
        tuple(id(row) for row in plan.descriptors),
        tuple(id(array) for array in plan._arrays),
        id(plan._source_buffers),
    )


def _validate_zero_prescribed_state(
    resident: HipResidentCsrExecutionContext,
    plan: ExecutionPlanV2,
) -> None:
    constrained = plan.array("constrained_dofs")
    values = resident._state.displacement_si[constrained]
    if np.any(values != 0.0) or np.signbit(values).any():
        _fail(
            "hip_free_space_nonzero_constrained_state_unsupported",
            "/resident/committed_state/kinematics/displacement_si",
            "The zero-only free-space operator requires exact +0.0 at every constrained DOF.",
        )


def _bindings(
    resident: HipResidentCsrExecutionContext,
    overlay: HipFreeSpaceOperatorPlanV1,
    lease_epoch: int,
    internally_compiled: bool,
) -> HipFreeSpaceBindings:
    plan = resident._plan
    return HipFreeSpaceBindings(
        resident_context_id=resident.context_id,
        resident_opening_receipt_hash=(resident.opening_receipt.context_receipt_hash),
        parent_assembly_context_id=resident._parent.context_id,
        parent_operator_id=resident._parent._operator_view.operator_id,
        free_space_plan_id=overlay.plan_id,
        free_space_plan_hash=overlay.plan_hash,
        free_space_view_hash=overlay.free_space_view_hash,
        source_execution_plan_hash=plan.plan_hash,
        source_operator_hash=plan.operator_hash,
        source_numeric_snapshot_hash=plan.numeric_snapshot_hash,
        source_symbolic_reuse_hash=plan.symbolic_reuse_hash,
        source_partition_hash=plan.partition_hash,
        state_hash=resident._state.state_hash,
        state_epoch=resident._state.epoch,
        load_pattern_id=plan.load_pattern_id,
        device_ordinal=resident._device_ordinal_snapshot,
        downstream_lease_epoch=lease_epoch,
        kernel_origin="internally_compiled"
        if internally_compiled
        else "caller_supplied",
    )


def _claims(
    ready: bool,
    evidence_scope: EvidenceScope,
    *,
    lease_active: bool,
) -> HipFreeSpaceClaims:
    active = lease_active
    return HipFreeSpaceClaims(
        exclusive_resident_lease_active=active,
        same_runtime_device_stream=active,
        reduced_csr_device_materialized=ready,
        device_direction_producer_ready=ready,
        resident_jvp_consumer_ready=ready,
        host_reduced_numeric_h2d_avoided=active,
        native_composite_context=(
            ready and evidence_scope == "native_hiprtc_free_space_composite"
        ),
    )


def _context_id(
    resident: HipResidentCsrExecutionContext,
    overlay: HipFreeSpaceOperatorPlanV1,
    lease_epoch: int,
    binding: HipFreeSpaceKernelBinding,
    evidence_scope: EvidenceScope,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
            "resident_context_id": resident.context_id,
            "free_space_plan_hash": overlay.plan_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": binding.identity_hash,
            "evidence_scope": evidence_scope,
        }
    )


def _fallback_context_id(
    resident: HipResidentCsrExecutionContext,
    overlay: HipFreeSpaceOperatorPlanV1,
    lease_epoch: int,
    binding: HipFreeSpaceKernelBinding | None,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
            "resident_context_id": resident.context_id,
            "free_space_plan_hash": overlay.plan_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": (
                _ZERO_HASH if binding is None else binding.identity_hash
            ),
        }
    )


def _cpu_expected_for_context(
    context: HipFreeSpaceExecutionContext,
) -> dict[str, np.ndarray]:
    plan = context._plan
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    full_state = context._resident._state.displacement_si
    reduced_values = plan.array("reduced_stiffness_csr_values")
    reduced_state = full_state[free]
    reduced_load = plan.array("global_load")[free]
    full_residual = plan.residual(full_state)
    # This is deliberately derived from the full operator so the oracle does
    # not duplicate a missing K_fc u_c term in the reduced device path.
    direction = -full_residual[free]
    full_direction = np.zeros(plan.dof_count, dtype="<f8")
    full_direction[free] = direction
    return {
        "reduced_values": reduced_values,
        "reduced_state": reduced_state,
        "reduced_load": reduced_load,
        "residual_direction": direction,
        "reduced_jvp": _csr_matvec(
            plan.array("reduced_csr_row_ptr"),
            plan.array("reduced_csr_column_indices"),
            reduced_values,
            direction,
        ),
        "full_residual": full_residual,
        "full_direction": full_direction,
    }


def _csr_matvec(
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    result = np.zeros(row_ptr.size - 1, dtype="<f8")
    for row in range(result.size):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        result[row] = np.dot(values[begin:end], vector[columns[begin:end]])
    result[result == 0.0] = 0.0
    return result


def _metric(actual: np.ndarray, expected: np.ndarray) -> HipFreeSpaceParityMetric:
    count = int(actual.size)
    if count == 0:
        return HipFreeSpaceParityMetric(0, 0.0, 0.0, 0.0, True)
    magnitude = max(
        1.0,
        float(np.max(np.abs(actual))),
        float(np.max(np.abs(expected))),
    )
    actual_scaled = actual / magnitude
    expected_scaled = expected / magnitude
    difference = actual_scaled - expected_scaled
    max_difference = float(np.max(np.abs(difference)))
    max_abs_long = np.longdouble(magnitude) * np.longdouble(max_difference)
    max_abs = float(min(max_abs_long, np.longdouble(np.finfo(np.float64).max)))
    relative = float(
        np.linalg.norm(difference)
        / max(np.linalg.norm(expected_scaled), np.finfo(np.float64).tiny)
    )
    tolerance = _PARITY_TOLERANCE / magnitude + _PARITY_TOLERANCE * np.abs(
        expected_scaled
    )
    max_scaled = float(np.max(np.abs(difference) / tolerance))
    passed = bool(
        np.allclose(
            actual_scaled,
            expected_scaled,
            atol=_PARITY_TOLERANCE / magnitude,
            rtol=_PARITY_TOLERANCE,
        )
    )
    return HipFreeSpaceParityMetric(count, max_abs, relative, max_scaled, passed)


def _parity_report(
    actual: dict[str, np.ndarray],
    expected: dict[str, np.ndarray],
    plan: ExecutionPlanV2,
) -> HipFreeSpaceParityReport:
    metrics = {
        name: _metric(actual[name], expected[name])
        for name in (
            "reduced_values",
            "reduced_state",
            "reduced_load",
            "residual_direction",
            "reduced_jvp",
            "full_residual",
            "full_direction",
        )
    }
    free = plan.array("free_dofs")
    cross_metric = _metric(
        actual["residual_direction"],
        -actual["full_residual"][free],
    )
    constrained = plan.array("constrained_dofs")
    constrained_zero = bool(
        np.array_equal(
            actual["full_direction"][constrained],
            np.zeros(constrained.size, dtype="<f8"),
        )
        and not np.signbit(actual["full_direction"][constrained]).any()
    )
    return HipFreeSpaceParityReport(
        metrics["reduced_values"],
        metrics["reduced_state"],
        metrics["reduced_load"],
        metrics["residual_direction"],
        cross_metric,
        metrics["reduced_jvp"],
        metrics["full_residual"],
        metrics["full_direction"],
        constrained_direction_exact_zero=constrained_zero,
        passed=(
            all(metric.passed for metric in metrics.values())
            and cross_metric.passed
            and constrained_zero
        ),
    )


def _array_descriptor(array: np.ndarray) -> HipFreeSpaceArrayDescriptor:
    return HipFreeSpaceArrayDescriptor(
        "<f8",
        tuple(int(value) for value in array.shape),
        int(array.nbytes),
        array_data_hash(array),
    )


def _build_context_receipt(
    *,
    status: ContextStatus,
    context_id: str,
    evidence_scope: EvidenceScope,
    actual_backend: str | None,
    reason: HipFreeSpaceReason | None,
    bindings: HipFreeSpaceBindings,
    kernel: HipFreeSpaceKernelBinding | None,
    dimensions: HipFreeSpaceDimensions,
    owned_buffers: tuple[HipFreeSpaceBufferView, ...],
    allocation_lineage: HipFreeSpaceAllocationLineage | None,
    telemetry: HipFreeSpaceTelemetry,
    claims: HipFreeSpaceClaims,
) -> HipFreeSpaceContextReceipt:
    draft = HipFreeSpaceContextReceipt(
        status,
        context_id,
        evidence_scope,
        actual_backend,
        False,
        reason,
        bindings,
        kernel,
        dimensions,
        owned_buffers,
        allocation_lineage,
        telemetry,
        claims,
        _ZERO_HASH,
    )
    receipt = replace(
        draft,
        context_receipt_hash=canonical_hash(
            _context_payload(draft, include_hash=False)
        ),
    )
    validate_hip_free_space_context_receipt(receipt)
    return receipt


def _build_apply_receipt(
    *,
    status: ApplyStatus,
    context: HipFreeSpaceExecutionContext,
    sequence: int,
    direction_generation: int | None,
    resident_enqueue: HipResidentCsrEnqueueReceipt | None,
    delta: HipFreeSpaceApplyDelta,
    reason: HipFreeSpaceReason | None,
) -> HipFreeSpaceApplyReceipt:
    apply_id = canonical_hash(
        {
            "context_id": context.context_id,
            "sequence": sequence,
            "direction_generation": direction_generation,
        }
    )
    claims = HipFreeSpaceApplyClaims(
        delta.producer_launch_success_count == 1,
        delta.resident_launch_success_count == 1,
        delta.resident_launch_success_count == 1,
        delta.gather_launch_success_count == 1,
    )
    draft = HipFreeSpaceApplyReceipt(
        status=status,
        apply_id=apply_id,
        context_id=context.context_id,
        opening_context_receipt_hash=(context.opening_receipt.context_receipt_hash),
        sequence=sequence,
        direction_generation=direction_generation,
        resident_enqueue=resident_enqueue,
        resident_enqueue_receipt_hash=(
            None if resident_enqueue is None else resident_enqueue.receipt_hash
        ),
        resident_enqueue_sequence=(
            None if resident_enqueue is None else resident_enqueue.sequence
        ),
        evidence_scope=context._evidence_scope,
        promotion_eligible=False,
        reason=reason,
        telemetry_delta=delta,
        claims=claims,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_apply_payload(draft, include_hash=False)),
    )
    validate_hip_free_space_apply_receipt(receipt)
    return receipt


def _build_evaluation_receipt(
    *,
    status: EvaluationStatus,
    execution_id: str,
    context: HipFreeSpaceExecutionContext,
    apply: HipFreeSpaceApplyReceipt | None,
    arrays: dict[str, np.ndarray],
    delta: HipFreeSpaceEvaluationDelta,
    parity: HipFreeSpaceParityReport | None,
    reason: HipFreeSpaceReason | None,
) -> HipFreeSpaceEvaluationReceipt:
    descriptors = tuple(
        (name, _array_descriptor(arrays[name]))
        for name in (
            "reduced_values",
            "reduced_state",
            "reduced_load",
            "residual_direction",
            "reduced_jvp",
            "full_residual",
            "full_direction",
        )
        if name in arrays
    )
    draft = HipFreeSpaceEvaluationReceipt(
        status=status,
        execution_id=execution_id,
        context_id=context.context_id,
        opening_context_receipt_hash=(context.opening_receipt.context_receipt_hash),
        apply=apply,
        evidence_scope=context._evidence_scope,
        actual_backend=(
            "hip"
            if context._evidence_scope == "native_hiprtc_free_space_composite"
            else "test_double"
        ),
        promotion_eligible=False,
        reason=reason,
        arrays=descriptors,
        telemetry_delta=delta,
        parity=parity,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_evaluation_payload(draft, include_hash=False)),
    )
    validate_hip_free_space_evaluation_receipt(receipt)
    return receipt


def _unavailable_evaluation(
    context: HipFreeSpaceExecutionContext,
    execution_id: str,
    apply: HipFreeSpaceApplyReceipt | None,
    delta: HipFreeSpaceEvaluationDelta,
    code: str,
    error: Any,
) -> HipFreeSpaceEvaluation:
    receipt = _build_evaluation_receipt(
        status="unavailable",
        execution_id=execution_id,
        context=context,
        apply=apply,
        arrays={},
        delta=delta,
        parity=None,
        reason=HipFreeSpaceReason(code, _detail(error)),
    )
    return HipFreeSpaceEvaluation(
        receipt, None, None, None, None, None, None, None, apply
    )


def _context_payload(
    receipt: HipFreeSpaceContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "kernel": None if receipt.kernel is None else receipt.kernel.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "owned_buffers": [view.to_dict() for view in receipt.owned_buffers],
        "allocation_lineage": (
            None
            if receipt.allocation_lineage is None
            else receipt.allocation_lineage.to_dict()
        ),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _apply_payload(
    receipt: HipFreeSpaceApplyReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
        "status": receipt.status,
        "apply_id": receipt.apply_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "sequence": receipt.sequence,
        "direction_generation": receipt.direction_generation,
        "resident_enqueue": (
            None
            if receipt.resident_enqueue is None
            else receipt.resident_enqueue.to_dict()
        ),
        "resident_enqueue_receipt_hash": receipt.resident_enqueue_receipt_hash,
        "resident_enqueue_sequence": receipt.resident_enqueue_sequence,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _evaluation_payload(
    receipt: HipFreeSpaceEvaluationReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
        "status": receipt.status,
        "execution_id": receipt.execution_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "apply": None if receipt.apply is None else receipt.apply.to_dict(),
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "arrays": {name: descriptor.to_dict() for name, descriptor in receipt.arrays},
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "parity": None if receipt.parity is None else receipt.parity.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def validate_hip_free_space_context_receipt(
    receipt: HipFreeSpaceContextReceipt,
    *,
    expected_context: HipFreeSpaceExecutionContext | None = None,
) -> HipFreeSpaceContextReceipt:
    if type(receipt) is not HipFreeSpaceContextReceipt:
        _fail("hip_free_space_context_receipt_type_invalid", "/")
    nested = (
        (receipt.bindings, HipFreeSpaceBindings),
        (receipt.dimensions, HipFreeSpaceDimensions),
        (receipt.telemetry, HipFreeSpaceTelemetry),
        (receipt.claims, HipFreeSpaceClaims),
    )
    if any(type(value) is not kind for value, kind in nested):
        _fail("hip_free_space_context_nested_type_invalid", "/")
    if receipt.reason is not None and type(receipt.reason) is not HipFreeSpaceReason:
        _fail("hip_free_space_context_nested_type_invalid", "/reason")
    if (
        receipt.allocation_lineage is not None
        and type(receipt.allocation_lineage) is not HipFreeSpaceAllocationLineage
    ):
        _fail(
            "hip_free_space_context_nested_type_invalid",
            "/allocation_lineage",
        )
    if (
        receipt.kernel is not None
        and type(receipt.kernel) is not HipFreeSpaceKernelBinding
    ):
        _fail("hip_free_space_context_nested_type_invalid", "/kernel")
    if type(receipt.owned_buffers) is not tuple or any(
        type(view) is not HipFreeSpaceBufferView for view in receipt.owned_buffers
    ):
        _fail("hip_free_space_context_nested_type_invalid", "/owned_buffers")
    payload = _context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema(), payload, "context")
    if receipt.context_receipt_hash != canonical_hash(
        _context_payload(receipt, include_hash=False)
    ):
        _fail("hip_free_space_context_receipt_hash_mismatch", "/context_receipt_hash")
    if _has_runtime_handle(payload):
        _fail("hip_free_space_runtime_handle_leak", "/")
    _validate_context_semantics(receipt)
    if expected_context is not None:
        if type(expected_context) is not HipFreeSpaceExecutionContext:
            _fail("hip_free_space_expected_context_invalid", "/expected_context")
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.bindings != expected_context._bindings_snapshot,
                receipt.dimensions != expected_context._dimensions_snapshot,
                receipt.kernel != expected_context._kernel_binding,
                receipt.owned_buffers != expected_context._owned_buffers,
                receipt.allocation_lineage
                != expected_context._allocation_lineage_snapshot,
            )
        ):
            _fail("hip_free_space_context_binding_mismatch", "/")
    return receipt


def _validate_context_semantics(receipt: HipFreeSpaceContextReceipt) -> None:
    t = receipt.telemetry
    d = receipt.dimensions
    b = receipt.bindings
    if any(
        type(getattr(t, name)) is not int or getattr(t, name) < 0
        for name in t.__dataclass_fields__
    ):
        _fail("hip_free_space_context_telemetry_invalid", "/telemetry")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_free_space_context_claim_type_invalid", "/claims")
    if any(
        (
            d.global_dof_count <= 0,
            d.free_dof_count <= 0,
            d.constrained_dof_count < 0,
            d.free_dof_count + d.constrained_dof_count != d.global_dof_count,
            d.full_csr_nnz <= 0,
            d.reduced_csr_nnz <= 0,
            d.reduced_csr_nnz > d.full_csr_nnz,
            d.symbolic_buffer_count != 5,
            d.work_buffer_count != 7,
            d.borrowed_buffer_count != 6,
        )
    ):
        _fail("hip_free_space_context_dimension_invalid", "/dimensions")
    if any(
        (
            receipt.promotion_eligible,
            t.allocation_success_count > t.allocation_attempt_count,
            t.allocation_success_count > 12,
            t.allocation_attempt_count > len(_OWNED_ORDER),
            t.deallocation_success_count > t.deallocation_attempt_count,
            t.deallocation_success_count > t.allocation_success_count,
            t.h2d_operation_success_count > t.h2d_operation_attempt_count,
            t.h2d_bytes_succeeded > t.h2d_bytes_attempted,
            t.d2h_operation_success_count > t.d2h_operation_attempt_count,
            t.d2h_bytes_succeeded > t.d2h_bytes_attempted,
            t.kernel_launch_success_count > t.kernel_launch_attempt_count,
            t.sync_success_count > t.sync_attempt_count,
            t.module_owner_acquired_count not in (0, 1),
            t.module_close_success_count > t.module_close_attempt_count,
            t.module_close_success_count > t.module_owner_acquired_count,
            t.lease_release_success_count > t.lease_release_attempt_count,
            t.lease_release_success_count not in (0, 1),
            t.lineage_owner_open_success_count not in (0, 1),
            t.lineage_owner_close_success_count > t.lineage_owner_open_success_count,
            t.lineage_capability_mint_success_count > t.allocation_success_count,
            t.allocation_success_count - t.lineage_capability_mint_success_count > 1,
            t.lineage_capability_mint_success_count > len(_OWNED_ORDER),
            t.lineage_free_acknowledgement_count + t.lineage_free_quarantine_count
            > t.lineage_capability_mint_success_count,
            t.lineage_orphan_acknowledgement_count + t.lineage_orphan_quarantine_count
            > 1,
            t.unknown_malloc_outcome_count > t.lineage_orphan_quarantine_count,
            (t.unknown_malloc_outcome_count == 0) != (t.unknown_requested_bytes == 0),
            t.quarantined_device_bytes > t.current_device_bytes,
            t.reduced_numeric_h2d_bytes != 0,
            t.state_h2d_bytes != 0,
            t.load_h2d_bytes != 0,
            t.direction_h2d_bytes != 0,
            t.new_stream_create_count != 0,
            t.fallback_count != 0,
        )
    ):
        _fail("hip_free_space_context_telemetry_invalid", "/telemetry")
    if receipt.status in {
        "unavailable",
        "context_closed",
        "cleanup_quarantined",
    }:
        pointerful_orphan_count = (
            t.lineage_orphan_acknowledgement_count
            + t.lineage_orphan_quarantine_count
            - t.unknown_malloc_outcome_count
        )
        if any(
            (
                pointerful_orphan_count < 0,
                t.lineage_free_acknowledgement_count + t.lineage_free_quarantine_count
                != t.lineage_capability_mint_success_count,
                t.deallocation_success_count
                != t.lineage_free_acknowledgement_count
                + t.lineage_orphan_acknowledgement_count,
                t.allocation_success_count
                != t.lineage_capability_mint_success_count + pointerful_orphan_count,
            )
        ):
            _fail(
                "hip_free_space_context_telemetry_conservation_invalid",
                "/telemetry",
            )
        _validate_allocation_byte_conservation(receipt)
        if receipt.status == "unavailable" or not receipt.owned_buffers:
            _validate_failed_open_operation_conservation(receipt)
    ready = receipt.status == "context_ready"
    active = receipt.status in ("context_ready", "poisoned", "cleanup_failed")
    expected_backend = (
        None
        if receipt.status == "unavailable"
        else (
            "hip"
            if receipt.evidence_scope == "native_hiprtc_free_space_composite"
            else "test_double"
        )
    )
    if receipt.actual_backend != expected_backend:
        _fail("hip_free_space_context_backend_invalid", "/actual_backend")
    _validate_allocation_lineage_semantics(receipt)
    if receipt.kernel is not None:
        _validate_kernel_binding(receipt.kernel)
        if t.module_owner_acquired_count != 1:
            _fail("hip_free_space_context_kernel_owner_invalid", "/telemetry")
    if receipt.kernel is None:
        expected_context_id = canonical_hash(
            {
                "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
                "resident_context_id": b.resident_context_id,
                "free_space_plan_hash": b.free_space_plan_hash,
                "lease_epoch": b.downstream_lease_epoch,
                "kernel_identity_hash": _ZERO_HASH,
            }
        )
    else:
        expected_context_id = canonical_hash(
            {
                "capability_profile": HIP_FREE_SPACE_CAPABILITY_PROFILE,
                "resident_context_id": b.resident_context_id,
                "free_space_plan_hash": b.free_space_plan_hash,
                "lease_epoch": b.downstream_lease_epoch,
                "kernel_identity_hash": receipt.kernel.identity_hash,
                "evidence_scope": receipt.evidence_scope,
            }
        )
    if receipt.context_id != expected_context_id:
        _fail("hip_free_space_context_id_mismatch", "/context_id")
    expected_claims = _claims(
        ready,
        receipt.evidence_scope,
        lease_active=active,
    )
    if receipt.claims != expected_claims:
        _fail("hip_free_space_context_claim_invalid", "/claims")
    if any(
        (
            receipt.claims.krylov_iteration_ready,
            receipt.claims.preconditioner_ready,
            receipt.claims.solver_ready,
            receipt.claims.iteration_host_copy_zero,
            receipt.claims.end_to_end_on_complexity,
            receipt.claims.performance_or_speedup,
            receipt.claims.commercial_readiness,
        )
    ):
        _fail("hip_free_space_context_broad_claim_invalid", "/claims")
    if receipt.status == "unavailable":
        if (
            receipt.reason is None
            or receipt.owned_buffers
            or t.current_device_bytes != 0
            or t.deallocation_success_count != t.allocation_success_count
            or t.deallocation_attempt_count != t.deallocation_success_count
            or t.module_close_success_count != t.module_owner_acquired_count
            or t.module_close_attempt_count != t.module_close_success_count
            or t.lease_release_success_count != 1
            or t.lease_release_attempt_count != t.lease_release_success_count
            or t.lineage_free_quarantine_count != 0
            or t.lineage_orphan_quarantine_count != 0
            or t.quarantined_device_bytes != 0
            or t.unknown_malloc_outcome_count != 0
            or t.unknown_requested_bytes != 0
            or t.lineage_owner_close_success_count != t.lineage_owner_open_success_count
        ):
            _fail("hip_free_space_context_unavailable_invalid", "/")
        return
    if receipt.status != "cleanup_quarantined" and len(receipt.owned_buffers) != 12:
        _fail("hip_free_space_context_buffer_count_invalid", "/owned_buffers")
    if receipt.owned_buffers:
        if len(receipt.owned_buffers) != 12:
            _fail("hip_free_space_context_buffer_count_invalid", "/owned_buffers")
        _validate_owned_buffer_view_semantics(receipt)
    if ready or receipt.status == "poisoned":
        expected_bytes = sum(view.byte_length for view in receipt.owned_buffers)
        symbolic_bytes = sum(
            view.byte_length
            for view in receipt.owned_buffers
            if view.name in _SYMBOLIC_NAMES
        )
        if any(
            (
                receipt.reason is not None if ready else receipt.reason is None,
                receipt.kernel is None,
                t.allocation_attempt_count != len(_OWNED_ORDER),
                t.allocation_success_count != 12,
                t.lineage_owner_open_success_count != 1,
                t.lineage_capability_mint_success_count != 12,
                t.lineage_capability_mint_bytes != expected_bytes,
                t.lineage_owner_close_success_count != 0,
                t.lineage_free_acknowledgement_count != 0,
                t.lineage_free_quarantine_count != 0,
                t.lineage_orphan_acknowledgement_count != 0,
                t.lineage_orphan_quarantine_count != 0,
                t.quarantined_device_bytes != 0,
                t.unknown_malloc_outcome_count != 0,
                t.unknown_requested_bytes != 0,
                t.current_device_bytes != expected_bytes,
                t.peak_device_bytes != expected_bytes,
                t.deallocation_attempt_count != 0,
                t.module_close_attempt_count != 0,
                t.lease_release_attempt_count != 0,
                t.symbolic_h2d_bytes != symbolic_bytes,
                t.error_flag_h2d_bytes != 4,
                t.reduced_numeric_h2d_bytes != 0,
                t.kernel_launch_success_count < 1,
                t.error_flag_d2h_bytes < 4,
                t.sync_success_count < 1,
            )
        ):
            _fail("hip_free_space_context_live_state_invalid", "/")
    elif receipt.status == "context_closed":
        if any(
            (
                receipt.reason is not None,
                t.current_device_bytes != 0,
                t.deallocation_success_count != t.allocation_success_count,
                t.lineage_owner_close_success_count
                != t.lineage_owner_open_success_count,
                t.lineage_free_acknowledgement_count
                != t.lineage_capability_mint_success_count,
                t.lineage_free_quarantine_count != 0,
                t.lineage_orphan_quarantine_count != 0,
                t.quarantined_device_bytes != 0,
                t.unknown_malloc_outcome_count != 0,
                t.unknown_requested_bytes != 0,
                t.module_close_success_count != t.module_owner_acquired_count,
                t.lease_release_success_count != 1,
            )
        ):
            _fail("hip_free_space_context_closed_invalid", "/")
    elif receipt.status == "cleanup_failed":
        if receipt.reason is None or not (
            t.current_device_bytes > 0
            or t.module_close_success_count < t.module_owner_acquired_count
            or t.lease_release_success_count < 1
            or t.lineage_owner_close_success_count < t.lineage_owner_open_success_count
        ):
            _fail("hip_free_space_context_cleanup_state_invalid", "/")
    elif receipt.status == "cleanup_quarantined":
        if any(
            (
                receipt.reason is None,
                t.lineage_owner_open_success_count != 1,
                t.lineage_owner_close_success_count != 1,
                t.lineage_free_quarantine_count + t.lineage_orphan_quarantine_count
                <= 0,
                t.quarantined_device_bytes <= 0 and t.unknown_malloc_outcome_count <= 0,
                t.current_device_bytes != t.quarantined_device_bytes,
                t.module_close_success_count != t.module_owner_acquired_count,
                t.lease_release_success_count != 1,
            )
        ):
            _fail("hip_free_space_context_quarantine_state_invalid", "/")
        if not receipt.owned_buffers and any(
            (
                t.deallocation_attempt_count > t.allocation_success_count,
                t.module_close_attempt_count != t.module_close_success_count,
                t.lease_release_attempt_count != t.lease_release_success_count,
            )
        ):
            _fail("hip_free_space_context_quarantine_state_invalid", "/")


def _validate_allocation_lineage_semantics(
    receipt: HipFreeSpaceContextReceipt,
) -> None:
    lineage = receipt.allocation_lineage
    telemetry = receipt.telemetry
    if telemetry.lineage_owner_open_success_count == 0:
        if lineage is not None or any(
            (
                telemetry.allocation_attempt_count,
                telemetry.allocation_success_count,
                telemetry.deallocation_attempt_count,
                telemetry.deallocation_success_count,
                telemetry.current_device_bytes,
                telemetry.peak_device_bytes,
                telemetry.h2d_operation_attempt_count,
                telemetry.h2d_operation_success_count,
                telemetry.h2d_bytes_attempted,
                telemetry.h2d_bytes_succeeded,
                telemetry.d2h_operation_attempt_count,
                telemetry.d2h_operation_success_count,
                telemetry.d2h_bytes_attempted,
                telemetry.d2h_bytes_succeeded,
                telemetry.kernel_launch_attempt_count,
                telemetry.kernel_launch_success_count,
                telemetry.sync_attempt_count,
                telemetry.sync_success_count,
                telemetry.symbolic_h2d_bytes,
                telemetry.error_flag_h2d_bytes,
                telemetry.error_flag_d2h_bytes,
                telemetry.lineage_capability_mint_success_count,
                telemetry.lineage_capability_mint_bytes,
                telemetry.lineage_free_acknowledgement_count,
                telemetry.lineage_free_quarantine_count,
                telemetry.lineage_orphan_acknowledgement_count,
                telemetry.lineage_orphan_quarantine_count,
                telemetry.lineage_owner_close_success_count,
                telemetry.quarantined_device_bytes,
                telemetry.unknown_malloc_outcome_count,
                telemetry.unknown_requested_bytes,
            )
        ):
            _fail(
                "hip_free_space_allocation_lineage_invalid",
                "/allocation_lineage",
            )
        return
    if lineage is None:
        _fail(
            "hip_free_space_allocation_lineage_invalid",
            "/allocation_lineage",
        )
    if any(
        (
            lineage.capability_profile != HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
            lineage.evidence_scope != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
            lineage.owner_role != "free_space_owned_buffers",
            not lineage.runtime_device_bound,
            lineage.managed_buffer_count
            != telemetry.lineage_capability_mint_success_count,
            lineage.managed_device_bytes != telemetry.lineage_capability_mint_bytes,
            lineage.managed_device_bytes
            != sum(
                _lineage_buffer_byte_lengths(receipt.dimensions)[
                    : lineage.managed_buffer_count
                ]
            ),
            lineage.all_owned_buffers_managed
            is not (lineage.managed_buffer_count == len(_OWNED_ORDER)),
            lineage.pointer_values_serialized,
            lineage.promotion_eligible,
        )
    ):
        _fail(
            "hip_free_space_allocation_lineage_invalid",
            "/allocation_lineage",
        )


def _validate_allocation_byte_conservation(
    receipt: HipFreeSpaceContextReceipt,
) -> None:
    """Reject terminal receipts whose byte ledger cannot come from owned roles."""

    telemetry = receipt.telemetry
    extents = _lineage_buffer_byte_lengths(receipt.dimensions)
    minted_count = telemetry.lineage_capability_mint_success_count
    minted_extents = extents[:minted_count]
    orphan_count = (
        telemetry.lineage_orphan_acknowledgement_count
        + telemetry.lineage_orphan_quarantine_count
    )
    if orphan_count and minted_count >= len(extents):
        _fail(
            "hip_free_space_context_byte_conservation_invalid",
            "/telemetry",
        )
    next_extent = extents[minted_count] if orphan_count else 0
    pointerful_orphan_count = orphan_count - telemetry.unknown_malloc_outcome_count
    expected_peak = sum(minted_extents) + next_extent * pointerful_orphan_count
    known_quarantined_orphan_count = (
        telemetry.lineage_orphan_quarantine_count
        - telemetry.unknown_malloc_outcome_count
    )
    allowed_quarantined_bytes = {
        owned_total + next_extent * known_quarantined_orphan_count
        for owned_total in _possible_quarantined_byte_totals(
            minted_extents,
            telemetry.lineage_free_quarantine_count,
        )
    }
    expected_unknown_bytes = (
        next_extent if telemetry.unknown_malloc_outcome_count else 0
    )
    allowed_attempt_counts = {minted_count}
    if minted_count < len(extents):
        allowed_attempt_counts.add(minted_count + 1)
    if orphan_count:
        allowed_attempt_counts = {minted_count + 1}
    if any(
        (
            telemetry.lineage_capability_mint_bytes != sum(minted_extents),
            telemetry.peak_device_bytes != expected_peak,
            telemetry.quarantined_device_bytes not in allowed_quarantined_bytes,
            telemetry.unknown_requested_bytes != expected_unknown_bytes,
            telemetry.allocation_attempt_count not in allowed_attempt_counts,
        )
    ):
        _fail(
            "hip_free_space_context_byte_conservation_invalid",
            "/telemetry",
        )


def _validate_failed_open_operation_conservation(
    receipt: HipFreeSpaceContextReceipt,
) -> None:
    telemetry = receipt.telemetry
    extents = _lineage_buffer_byte_lengths(receipt.dimensions)
    minted_count = telemetry.lineage_capability_mint_success_count
    allocation_progressed = (
        telemetry.allocation_attempt_count > minted_count
        or telemetry.lineage_orphan_acknowledgement_count
        + telemetry.lineage_orphan_quarantine_count
        > 0
    )
    upload_specs = tuple(
        (index, extents[index], index < len(_SYMBOLIC_NAMES))
        for index in (*range(len(_SYMBOLIC_NAMES)), len(_OWNED_ORDER) - 1)
    )
    last_minted_index = minted_count - 1
    ambiguous_last_upload = not allocation_progressed and any(
        index == last_minted_index for index, _, _ in upload_specs
    )
    completed = tuple(
        spec
        for spec in upload_specs
        if spec[0] < minted_count
        and (not ambiguous_last_upload or spec[0] != last_minted_index)
    )
    base_attempt_count = len(completed)
    base_attempt_bytes = sum(size for _, size, _ in completed)
    base_symbolic_bytes = sum(size for _, size, symbolic in completed if symbolic)
    base_error_bytes = sum(
        size for index, size, _ in completed if index == len(_OWNED_ORDER) - 1
    )
    h2d_states = {
        (
            base_attempt_count,
            base_attempt_count,
            base_attempt_bytes,
            base_attempt_bytes,
            base_symbolic_bytes,
            base_error_bytes,
        )
    }
    if ambiguous_last_upload:
        _, size, symbolic = next(
            spec for spec in upload_specs if spec[0] == last_minted_index
        )
        attempted = (
            base_attempt_count + 1,
            base_attempt_count,
            base_attempt_bytes + size,
            base_attempt_bytes,
            base_symbolic_bytes,
            base_error_bytes,
        )
        succeeded = (
            base_attempt_count + 1,
            base_attempt_count + 1,
            base_attempt_bytes + size,
            base_attempt_bytes + size,
            base_symbolic_bytes + (size if symbolic else 0),
            base_error_bytes
            + (size if last_minted_index == len(_OWNED_ORDER) - 1 else 0),
        )
        h2d_states.update((attempted, succeeded))

    allowed: set[tuple[int, ...]] = set()
    for h2d_state in h2d_states:
        allowed.add((*h2d_state[:4], 0, 0, 0, 0, 0, 0, 0, 0, *h2d_state[4:], 0))
        if minted_count != len(_OWNED_ORDER) or h2d_state[1] != len(upload_specs):
            continue
        # kernel attempt, kernel success, D2H+sync attempt, D2H success,
        # and sync success are the only deterministic failed-open prefixes.
        allowed.update(
            {
                (*h2d_state[:4], 0, 0, 0, 0, 1, 0, 0, 0, *h2d_state[4:], 0),
                (*h2d_state[:4], 0, 0, 0, 0, 1, 1, 0, 0, *h2d_state[4:], 0),
                (*h2d_state[:4], 1, 0, 4, 0, 1, 1, 1, 0, *h2d_state[4:], 4),
                (*h2d_state[:4], 1, 1, 4, 4, 1, 1, 1, 0, *h2d_state[4:], 4),
                (*h2d_state[:4], 1, 1, 4, 4, 1, 1, 1, 1, *h2d_state[4:], 4),
            }
        )
    pointerful_resources = minted_count + (
        telemetry.lineage_orphan_acknowledgement_count
        + telemetry.lineage_orphan_quarantine_count
        - telemetry.unknown_malloc_outcome_count
    )
    if pointerful_resources:
        allowed = {
            signature[:10] + (signature[10] + 1, signature[11] + 1) + signature[12:]
            for signature in tuple(allowed)
        }
    actual = (
        telemetry.h2d_operation_attempt_count,
        telemetry.h2d_operation_success_count,
        telemetry.h2d_bytes_attempted,
        telemetry.h2d_bytes_succeeded,
        telemetry.d2h_operation_attempt_count,
        telemetry.d2h_operation_success_count,
        telemetry.d2h_bytes_attempted,
        telemetry.d2h_bytes_succeeded,
        telemetry.kernel_launch_attempt_count,
        telemetry.kernel_launch_success_count,
        telemetry.sync_attempt_count,
        telemetry.sync_success_count,
        telemetry.symbolic_h2d_bytes,
        telemetry.error_flag_h2d_bytes,
        telemetry.error_flag_d2h_bytes,
    )
    if actual not in allowed:
        _fail(
            "hip_free_space_context_operation_conservation_invalid",
            "/telemetry",
        )


def _possible_quarantined_byte_totals(
    extents: tuple[int, ...],
    quarantined_count: int,
) -> frozenset[int]:
    if quarantined_count > len(extents):
        return frozenset()
    totals_by_count: list[set[int]] = [set() for _ in range(quarantined_count + 1)]
    totals_by_count[0].add(0)
    for extent in extents:
        for count in range(quarantined_count, 0, -1):
            totals_by_count[count].update(
                total + extent for total in totals_by_count[count - 1]
            )
    return frozenset(totals_by_count[quarantined_count])


def _lineage_buffer_byte_lengths(
    dimensions: HipFreeSpaceDimensions,
) -> tuple[int, ...]:
    free = dimensions.free_dof_count
    global_dofs = dimensions.global_dof_count
    nnz = dimensions.reduced_csr_nnz
    return (
        4 * free,
        4 * global_dofs,
        4 * (free + 1),
        4 * nnz,
        4 * nnz,
        8 * nnz,
        8 * free,
        8 * free,
        8 * free,
        8 * free,
        8 * free,
        4,
    )


def _validate_owned_buffer_view_semantics(
    receipt: HipFreeSpaceContextReceipt,
) -> None:
    d = receipt.dimensions
    f = d.free_dof_count
    g = d.global_dof_count
    z = d.reduced_csr_nnz
    specs = (
        (
            "free_dofs",
            "<i4",
            (f,),
            4 * f,
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            "symbolic",
        ),
        (
            "global_to_free",
            "<i4",
            (g,),
            4 * g,
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            "symbolic",
        ),
        (
            "reduced_csr_row_ptr",
            "<i4",
            (f + 1,),
            4 * (f + 1),
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            "symbolic",
        ),
        (
            "reduced_csr_column_indices",
            "<i4",
            (z,),
            4 * z,
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            "symbolic",
        ),
        (
            "reduced_csr_global_value_indices",
            "<i4",
            (z,),
            4 * z,
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            "symbolic",
        ),
        (
            "reduced_csr_values",
            "<f8",
            (z,),
            8 * z,
            "read_only_after_materialize",
            "device_only",
            "none",
        ),
        (
            "reduced_state",
            "<f8",
            (f,),
            8 * f,
            "read_only_after_materialize",
            "device_only",
            "none",
        ),
        (
            "reduced_load",
            "<f8",
            (f,),
            8 * f,
            "read_only_after_materialize",
            "device_only",
            "none",
        ),
        (
            "reduced_direction",
            "<f8",
            (f,),
            8 * f,
            "write_only",
            "device_only",
            "none",
        ),
        (
            "reduced_residual",
            "<f8",
            (f,),
            8 * f,
            "write_only",
            "device_only",
            "none",
        ),
        (
            "reduced_jvp",
            "<f8",
            (f,),
            8 * f,
            "write_only",
            "device_only",
            "none",
        ),
        (
            "error_flag",
            "<i4",
            (1,),
            4,
            "read_write",
            "async_h2d_zero_once_then_same_stream_fence",
            "zero",
        ),
    )
    for index, (view, spec) in enumerate(
        zip(receipt.owned_buffers, specs, strict=True)
    ):
        name, dtype, shape, byte_length, access, transfer, hash_role = spec
        if any(
            (
                view.name != name,
                view.dtype != dtype,
                type(view.shape) is not tuple,
                view.shape != shape,
                type(view.byte_length) is not int,
                view.byte_length != byte_length,
                view.access != access,
                view.initial_transfer != transfer,
            )
        ):
            _fail(
                "hip_free_space_context_buffer_semantics_invalid",
                f"/owned_buffers/{index}",
            )
        if hash_role == "symbolic":
            _require_hash(view.data_hash, f"/owned_buffers/{index}/data_hash")
        elif hash_role == "zero":
            if view.data_hash != _ZERO_I32_DATA_HASH:
                _fail(
                    "hip_free_space_context_buffer_semantics_invalid",
                    f"/owned_buffers/{index}/data_hash",
                )
        elif view.data_hash is not None:
            _fail(
                "hip_free_space_context_buffer_semantics_invalid",
                f"/owned_buffers/{index}/data_hash",
            )


def validate_hip_free_space_apply_receipt(
    receipt: HipFreeSpaceApplyReceipt,
    *,
    expected_context: HipFreeSpaceExecutionContext | None = None,
) -> HipFreeSpaceApplyReceipt:
    if type(receipt) is not HipFreeSpaceApplyReceipt:
        _fail("hip_free_space_apply_receipt_type_invalid", "/")
    if (
        type(receipt.telemetry_delta) is not HipFreeSpaceApplyDelta
        or type(receipt.claims) is not HipFreeSpaceApplyClaims
    ):
        _fail("hip_free_space_apply_nested_type_invalid", "/")
    if receipt.reason is not None and type(receipt.reason) is not HipFreeSpaceReason:
        _fail("hip_free_space_apply_nested_type_invalid", "/reason")
    if receipt.resident_enqueue is not None:
        validate_hip_resident_csr_enqueue_receipt(
            receipt.resident_enqueue,
            expected_context=(
                None if expected_context is None else expected_context._resident
            ),
        )
    payload = _apply_payload(receipt, include_hash=True)
    _validate_schema(_apply_schema(), payload, "apply")
    if receipt.receipt_hash != canonical_hash(
        _apply_payload(receipt, include_hash=False)
    ):
        _fail("hip_free_space_apply_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_handle(payload):
        _fail("hip_free_space_runtime_handle_leak", "/")
    delta = receipt.telemetry_delta
    if any(
        type(getattr(delta, name)) is not int or getattr(delta, name) < 0
        for name in delta.__dataclass_fields__
    ):
        _fail("hip_free_space_apply_delta_invalid", "/telemetry_delta")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_free_space_apply_claim_type_invalid", "/claims")
    if any(
        (
            receipt.promotion_eligible,
            delta.h2d_operation_count != 0,
            delta.d2h_operation_count != 0,
            delta.allocation_count != 0,
            delta.sync_count != 0,
            delta.fallback_count != 0,
            delta.producer_launch_success_count > delta.producer_launch_attempt_count,
            delta.resident_launch_success_count > delta.resident_launch_attempt_count,
            delta.gather_launch_success_count > delta.gather_launch_attempt_count,
        )
    ):
        _fail("hip_free_space_apply_delta_invalid", "/telemetry_delta")
    if any(
        getattr(delta, name) not in (0, 1)
        for name in (
            "producer_launch_attempt_count",
            "producer_launch_success_count",
            "resident_launch_attempt_count",
            "resident_launch_success_count",
            "gather_launch_attempt_count",
            "gather_launch_success_count",
        )
    ):
        _fail("hip_free_space_apply_delta_invalid", "/telemetry_delta")
    expected_claims = HipFreeSpaceApplyClaims(
        delta.producer_launch_success_count == 1,
        delta.resident_launch_success_count == 1,
        delta.resident_launch_success_count == 1,
        delta.gather_launch_success_count == 1,
    )
    if receipt.claims != expected_claims:
        _fail("hip_free_space_apply_claim_invalid", "/claims")
    if delta.producer_launch_attempt_count != 1:
        _fail("hip_free_space_apply_stage_order_invalid", "/telemetry_delta")
    if delta.producer_launch_success_count == 0 and any(
        (
            receipt.direction_generation is not None,
            receipt.resident_enqueue is not None,
            delta.resident_launch_attempt_count != 0,
            delta.resident_launch_success_count != 0,
            delta.gather_launch_attempt_count != 0,
            delta.gather_launch_success_count != 0,
        )
    ):
        _fail("hip_free_space_apply_stage_order_invalid", "/telemetry_delta")
    if delta.resident_launch_success_count == 0 and any(
        (
            delta.gather_launch_attempt_count != 0,
            delta.gather_launch_success_count != 0,
        )
    ):
        _fail("hip_free_space_apply_stage_order_invalid", "/telemetry_delta")
    if receipt.resident_enqueue is None:
        if any(
            (
                receipt.resident_enqueue_receipt_hash is not None,
                receipt.resident_enqueue_sequence is not None,
                delta.resident_launch_attempt_count != 0,
                delta.resident_launch_success_count != 0,
            )
        ):
            _fail("hip_free_space_apply_resident_binding_invalid", "/resident_enqueue")
    else:
        nested = receipt.resident_enqueue
        if any(
            (
                receipt.direction_generation is None,
                receipt.resident_enqueue_receipt_hash != nested.receipt_hash,
                receipt.resident_enqueue_sequence != nested.sequence,
                delta.resident_launch_attempt_count
                != nested.telemetry_delta.kernel_launch_attempt_count,
                delta.resident_launch_success_count
                != nested.telemetry_delta.kernel_launch_success_count,
            )
        ):
            _fail("hip_free_space_apply_resident_binding_invalid", "/resident_enqueue")
    if delta.resident_launch_success_count == 1 and (
        receipt.resident_enqueue is None
        or receipt.resident_enqueue.status != "enqueued"
        or receipt.direction_generation is None
    ):
        _fail("hip_free_space_apply_resident_binding_invalid", "/resident_enqueue")
    ready = receipt.status == "enqueued"
    if ready:
        if any(
            (
                receipt.reason is not None,
                receipt.direction_generation is None,
                receipt.resident_enqueue is None,
                receipt.resident_enqueue_receipt_hash
                != receipt.resident_enqueue.receipt_hash,
                receipt.resident_enqueue_sequence != receipt.resident_enqueue.sequence,
                receipt.resident_enqueue.status != "enqueued",
                delta.producer_launch_attempt_count != 1,
                delta.producer_launch_success_count != 1,
                delta.resident_launch_attempt_count != 1,
                delta.resident_launch_success_count != 1,
                delta.gather_launch_attempt_count != 1,
                delta.gather_launch_success_count != 1,
            )
        ):
            _fail("hip_free_space_apply_success_invalid", "/")
    elif receipt.reason is None or delta.gather_launch_success_count == 1:
        _fail("hip_free_space_apply_failure_invalid", "/")
    expected_id = canonical_hash(
        {
            "context_id": receipt.context_id,
            "sequence": receipt.sequence,
            "direction_generation": receipt.direction_generation,
        }
    )
    if receipt.apply_id != expected_id:
        _fail("hip_free_space_apply_id_mismatch", "/apply_id")
    if expected_context is not None:
        witness = expected_context._apply_witnesses.get(receipt.sequence)
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.opening_context_receipt_hash
                != expected_context.opening_receipt.context_receipt_hash,
                receipt.evidence_scope != expected_context._evidence_scope,
                receipt.sequence > expected_context._sequence + (0 if ready else 1),
                witness is None,
                witness is not None
                and witness != (receipt.direction_generation, receipt.receipt_hash),
            )
        ):
            _fail("hip_free_space_apply_context_binding_mismatch", "/")
    return receipt


def validate_hip_free_space_evaluation_receipt(
    receipt: HipFreeSpaceEvaluationReceipt,
    *,
    expected_context: HipFreeSpaceExecutionContext | None = None,
) -> HipFreeSpaceEvaluationReceipt:
    if type(receipt) is not HipFreeSpaceEvaluationReceipt:
        _fail("hip_free_space_evaluation_receipt_type_invalid", "/")
    if type(receipt.telemetry_delta) is not HipFreeSpaceEvaluationDelta:
        _fail("hip_free_space_evaluation_nested_type_invalid", "/telemetry_delta")
    if receipt.reason is not None and type(receipt.reason) is not HipFreeSpaceReason:
        _fail("hip_free_space_evaluation_nested_type_invalid", "/reason")
    if type(receipt.arrays) is not tuple or any(
        type(entry) is not tuple
        or len(entry) != 2
        or type(entry[0]) is not str
        or type(entry[1]) is not HipFreeSpaceArrayDescriptor
        for entry in receipt.arrays
    ):
        _fail("hip_free_space_evaluation_nested_type_invalid", "/arrays")
    if (
        receipt.parity is not None
        and type(receipt.parity) is not HipFreeSpaceParityReport
    ):
        _fail("hip_free_space_evaluation_nested_type_invalid", "/parity")
    if receipt.apply is not None:
        validate_hip_free_space_apply_receipt(
            receipt.apply, expected_context=expected_context
        )
    payload = _evaluation_payload(receipt, include_hash=True)
    _validate_schema(_evaluation_schema(), payload, "evaluation")
    if receipt.receipt_hash != canonical_hash(
        _evaluation_payload(receipt, include_hash=False)
    ):
        _fail("hip_free_space_evaluation_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_handle(payload):
        _fail("hip_free_space_runtime_handle_leak", "/")
    delta = receipt.telemetry_delta
    if any(
        type(getattr(delta, name)) is not int or getattr(delta, name) < 0
        for name in delta.__dataclass_fields__
    ) or any(
        (
            receipt.promotion_eligible,
            delta.d2h_operation_success_count > delta.d2h_operation_attempt_count,
            delta.d2h_bytes_succeeded > delta.d2h_bytes_attempted,
            delta.sync_success_count > delta.sync_attempt_count,
            delta.allocation_count != 0,
            delta.h2d_operation_count != 0,
            delta.fallback_count != 0,
        )
    ):
        _fail("hip_free_space_evaluation_delta_invalid", "/telemetry_delta")
    ready = receipt.status in ("verified", "parity_failed")
    expected_backend = (
        "hip"
        if receipt.evidence_scope == "native_hiprtc_free_space_composite"
        else "test_double"
    )
    if receipt.actual_backend != expected_backend:
        _fail("hip_free_space_evaluation_backend_invalid", "/actual_backend")
    if ready:
        expected_names = (
            "reduced_values",
            "reduced_state",
            "reduced_load",
            "residual_direction",
            "reduced_jvp",
            "full_residual",
            "full_direction",
        )
        if any(
            (
                receipt.reason is not None,
                receipt.apply is None,
                receipt.apply is not None and receipt.apply.status != "enqueued",
                receipt.parity is None,
                tuple(name for name, _ in receipt.arrays) != expected_names,
                delta.d2h_operation_attempt_count != 8,
                delta.d2h_operation_success_count != 8,
                delta.sync_attempt_count != 1,
                delta.sync_success_count != 1,
            )
        ):
            _fail("hip_free_space_evaluation_success_invalid", "/")
        _validate_parity_semantics(receipt.parity)
        _validate_evaluation_descriptor_semantics(receipt, expected_context)
        if receipt.status == "verified" and not receipt.parity.passed:
            _fail("hip_free_space_evaluation_status_invalid", "/parity")
        if receipt.status == "parity_failed" and receipt.parity.passed:
            _fail("hip_free_space_evaluation_status_invalid", "/parity")
    elif any(
        (
            receipt.reason is None,
            bool(receipt.arrays),
            receipt.parity is not None,
        )
    ):
        _fail("hip_free_space_evaluation_failure_invalid", "/")
    if receipt.apply is not None:
        expected_execution_id = canonical_hash(
            {
                "context_id": receipt.context_id,
                "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
                "apply_receipt_hash": receipt.apply.receipt_hash,
            }
        )
        if receipt.execution_id != expected_execution_id:
            _fail("hip_free_space_execution_id_mismatch", "/execution_id")
    if expected_context is not None and any(
        (
            receipt.context_id != expected_context.context_id,
            receipt.opening_context_receipt_hash
            != expected_context.opening_receipt.context_receipt_hash,
            receipt.evidence_scope != expected_context._evidence_scope,
        )
    ):
        _fail("hip_free_space_evaluation_context_binding_mismatch", "/")
    return receipt


def _validate_evaluation_descriptor_semantics(
    receipt: HipFreeSpaceEvaluationReceipt,
    expected_context: HipFreeSpaceExecutionContext | None,
) -> None:
    parity = receipt.parity
    if parity is None:  # pragma: no cover - caller establishes ready state
        _fail("hip_free_space_evaluation_parity_missing", "/parity")
    f = parity.reduced_state.count
    g = parity.full_residual.count
    z = parity.reduced_values.count
    expected_counts = {
        "reduced_values": z,
        "reduced_state": f,
        "reduced_load": f,
        "residual_direction": f,
        "reduced_jvp": f,
        "full_residual": g,
        "full_direction": g,
    }
    if any(
        (
            f <= 0,
            g <= 0,
            z <= 0,
            parity.reduced_load.count != f,
            parity.residual_direction.count != f,
            parity.residual_direction_vs_negative_full_residual_free.count != f,
            parity.reduced_jvp.count != f,
            parity.full_direction.count != g,
        )
    ):
        _fail("hip_free_space_evaluation_parity_count_invalid", "/parity/metrics")
    if expected_context is not None:
        d = expected_context._dimensions_snapshot
        if (g, f, z) != (d.global_dof_count, d.free_dof_count, d.reduced_csr_nnz):
            _fail("hip_free_space_evaluation_dimension_mismatch", "/parity/metrics")
    payload_bytes = 4
    for name, descriptor in receipt.arrays:
        count = expected_counts[name]
        if any(
            (
                descriptor.dtype != "<f8",
                type(descriptor.shape) is not tuple,
                descriptor.shape != (count,),
                type(descriptor.byte_length) is not int,
                descriptor.byte_length != 8 * count,
            )
        ):
            _fail(
                "hip_free_space_evaluation_descriptor_invalid",
                f"/arrays/{name}",
            )
        _require_hash(descriptor.data_hash, f"/arrays/{name}/data_hash")
        payload_bytes += descriptor.byte_length
    delta = receipt.telemetry_delta
    if any(
        (
            delta.d2h_bytes_attempted != payload_bytes,
            delta.d2h_bytes_succeeded != payload_bytes,
        )
    ):
        _fail("hip_free_space_evaluation_byte_count_invalid", "/telemetry_delta")


def validate_hip_free_space_evaluation(
    evaluation: HipFreeSpaceEvaluation,
    *,
    expected_context: HipFreeSpaceExecutionContext | None = None,
) -> HipFreeSpaceEvaluation:
    if type(evaluation) is not HipFreeSpaceEvaluation:
        _fail("hip_free_space_evaluation_type_invalid", "/")
    validate_hip_free_space_evaluation_receipt(
        evaluation.receipt, expected_context=expected_context
    )
    if evaluation.apply != evaluation.receipt.apply:
        _fail("hip_free_space_evaluation_apply_mismatch", "/apply")
    if evaluation.receipt.status == "unavailable":
        if any(
            value is not None
            for value in (
                evaluation.reduced_values,
                evaluation.reduced_state,
                evaluation.reduced_load,
                evaluation.residual_direction,
                evaluation.reduced_jvp,
                evaluation.full_residual,
                evaluation.full_direction,
            )
        ):
            _fail("hip_free_space_unavailable_output_invalid", "/outputs")
        return evaluation
    arrays = {
        "reduced_values": evaluation.reduced_values,
        "reduced_state": evaluation.reduced_state,
        "reduced_load": evaluation.reduced_load,
        "residual_direction": evaluation.residual_direction,
        "reduced_jvp": evaluation.reduced_jvp,
        "full_residual": evaluation.full_residual,
        "full_direction": evaluation.full_direction,
    }
    descriptors = dict(evaluation.receipt.arrays)
    for name, array in arrays.items():
        if array is None:
            _fail("hip_free_space_evaluation_output_missing", f"/arrays/{name}")
        _validate_array(array, descriptors[name], f"/arrays/{name}")
    if expected_context is not None:
        expected = _cpu_expected_for_context(expected_context)
        parity = _parity_report(arrays, expected, expected_context._plan)
        if evaluation.receipt.parity != parity:
            _fail("hip_free_space_evaluation_parity_mismatch", "/parity")
    return evaluation


def _validate_parity_semantics(report: HipFreeSpaceParityReport) -> None:
    if type(report) is not HipFreeSpaceParityReport:
        _fail("hip_free_space_parity_type_invalid", "/parity")
    metrics = (
        report.reduced_values,
        report.reduced_state,
        report.reduced_load,
        report.residual_direction,
        report.residual_direction_vs_negative_full_residual_free,
        report.reduced_jvp,
        report.full_residual,
        report.full_direction,
    )
    for metric in metrics:
        if type(metric) is not HipFreeSpaceParityMetric:
            _fail("hip_free_space_parity_metric_type_invalid", "/parity")
        values = (
            metric.max_abs_error,
            metric.relative_l2_error,
            metric.max_scaled_error,
        )
        if (
            type(metric.count) is not int
            or metric.count < 0
            or any(type(value) is not float for value in values)
            or not all(np.isfinite(value) and value >= 0.0 for value in values)
            or type(metric.passed) is not bool
            or (metric.count == 0 and (values != (0.0, 0.0, 0.0) or not metric.passed))
            or (metric.count > 0 and metric.passed != (metric.max_scaled_error <= 1.0))
        ):
            _fail("hip_free_space_parity_metric_invalid", "/parity")
    if (
        type(report.constrained_direction_exact_zero) is not bool
        or type(report.passed) is not bool
    ):
        _fail("hip_free_space_parity_scalar_invalid", "/parity")
    if report.passed != (
        report.constrained_direction_exact_zero
        and all(metric.passed for metric in metrics)
    ):
        _fail("hip_free_space_parity_aggregate_invalid", "/parity")


def _validate_array(
    array: np.ndarray,
    descriptor: HipFreeSpaceArrayDescriptor,
    path: str,
) -> None:
    if (
        type(array) is not np.ndarray
        or type(descriptor) is not HipFreeSpaceArrayDescriptor
        or array.dtype.str != "<f8"
        or array.shape != descriptor.shape
        or int(array.nbytes) != descriptor.byte_length
        or not array.flags.c_contiguous
        or not has_immutable_bytes_backing(array)
        or not np.all(np.isfinite(array))
        or array_data_hash(array) != descriptor.data_hash
    ):
        _fail("hip_free_space_evaluation_array_invalid", path)


@lru_cache(maxsize=1)
def _context_schema() -> Draft202012Validator:
    return _schema("hip_free_space_context_v2.schema.json")


@lru_cache(maxsize=1)
def _apply_schema() -> Draft202012Validator:
    return _schema("hip_free_space_apply_v1.schema.json")


@lru_cache(maxsize=1)
def _evaluation_schema() -> Draft202012Validator:
    return _schema("hip_free_space_evaluation_v1.schema.json")


def _schema(name: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HipFreeSpaceContextError(
            "hip_free_space_schema_unavailable", "/schema", type(exc).__name__
        ) from exc
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


def _validate_schema(
    validator: Draft202012Validator,
    payload: dict[str, Any],
    label: str,
) -> None:
    errors = sorted(
        validator.iter_errors(payload), key=lambda error: list(error.absolute_path)
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipFreeSpaceContextError(
            f"hip_free_space_{label}_schema_invalid", path, error.message
        )


def _has_runtime_handle(value: Any) -> bool:
    if isinstance(value, dict):
        allowed = {"same_runtime_device_stream", "new_stream_create_count"}
        for key, child in value.items():
            normalized = str(key).lower()
            forbidden = normalized in {
                "pointer",
                "address",
                "stream",
                "handle",
                "module",
                "function",
            } or normalized.endswith(
                ("_pointer", "_address", "_handle", "_module", "_function")
            )
            if (forbidden and normalized not in allowed) or _has_runtime_handle(child):
                return True
        return False
    if isinstance(value, list):
        return any(_has_runtime_handle(child) for child in value)
    if isinstance(value, str):
        return _HEX_ADDRESS_PATTERN.search(value) is not None
    return False


def _detail(value: Any, limit: int = 512) -> str:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        text = type(value).__name__
    text = _HEX_ADDRESS_PATTERN.sub("<redacted-address>", text)
    text = re.sub(
        r"(?i)\b(?:pointer|address|stream|handle|module|function)\b"
        r"\s*(?:[:=]\s*)?(?:[0-9]+)?",
        "<redacted-runtime>",
        text,
    )
    text = " ".join(text.split())
    return text[:limit] or "unspecified failure"


def _require_hash(value: Any, path: str) -> None:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hip_free_space_hash_invalid", path)


def _fail(code: str, path: str, message: str | None = None) -> None:
    raise HipFreeSpaceContextError(code, path, message or code.replace("_", " "))


__all__ = [
    "HIP_FREE_SPACE_APPLY_RECEIPT_SCHEMA_VERSION",
    "HIP_FREE_SPACE_CAPABILITY_PROFILE",
    "HIP_FREE_SPACE_CONTEXT_RECEIPT_SCHEMA_VERSION",
    "HIP_FREE_SPACE_EVALUATION_RECEIPT_SCHEMA_VERSION",
    "HipFreeSpaceApplyReceipt",
    "HipFreeSpaceAllocationLineage",
    "HipFreeSpaceContextError",
    "HipFreeSpaceContextOpenResult",
    "HipFreeSpaceContextReceipt",
    "HipFreeSpaceEvaluation",
    "HipFreeSpaceEvaluationReceipt",
    "HipFreeSpaceExecutionContext",
    "open_hip_free_space_execution_context",
    "validate_hip_free_space_apply_receipt",
    "validate_hip_free_space_context_receipt",
    "validate_hip_free_space_evaluation",
    "validate_hip_free_space_evaluation_receipt",
]
