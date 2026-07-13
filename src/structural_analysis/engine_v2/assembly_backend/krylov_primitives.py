"""Same-stream HIP Krylov vector and reduction primitive context.

This module deliberately stops below a Krylov solver.  It leases the reduced
device buffers produced by :mod:`free_space`, prepares an *unshifted* positive
Jacobi inverse, and exposes one fixed diagnostic batch of affine, Jacobi, dot,
and scale-first L2 operations.  The raw batch performs no allocation, transfer,
or synchronization.  Host copies exist only in the explicit verification path
and are never a fallback.
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
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import ExecutionPlanV2

from .free_space import (
    HipFreeSpaceApplyReceipt,
    HipFreeSpaceExecutionContext,
    validate_hip_free_space_apply_receipt,
)
from .free_space_plan import HipFreeSpaceOperatorPlanV1
from .hip_allocation_lineage import (
    HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
    HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
    HipAllocationBorrowLeaseV1,
    HipAllocationCapabilityV1,
    HipAllocationFreeLeaseV1,
    HipAllocationLineageError,
    HipAllocationOrphanLeaseV1,
    HipAllocationOwnerV1,
    recover_hip_allocation_borrow_v1,
    reserve_hip_allocation_owner_control_v1,
    release_hip_allocation_borrow_v1,
    snapshot_hip_allocation_owner_cleanup_v1,
    validate_hip_allocation_borrow_v1,
    validate_hip_allocation_capability_v1,
    validate_hip_allocation_owner_control_v1,
    validate_hip_allocation_owner_v1,
)
from .krylov_primitives_rtc import (
    HipRtcKrylovPrimitivesError,
    HipRtcKrylovPrimitivesKernel,
    _HipRtcKrylovPrimitivesKernelHandoff,
    _compile_krylov_primitives_with_handoff,
    compile_hip_rtc_krylov_primitives_kernel,
    reduction_output_count,
)

HIP_KRYLOV_PRIMITIVES_CONTEXT_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-krylov-primitives-context.v2"
)
HIP_KRYLOV_PRIMITIVES_BATCH_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-krylov-primitives-batch.v1"
)
HIP_KRYLOV_PRIMITIVES_EVALUATION_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-krylov-primitives-evaluation.v1"
)
HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE = (
    "phase0_hip_krylov_vector_reduction_positive_jacobi_primitives"
)

ContextStatus = Literal[
    "context_ready",
    "context_closed",
    "poisoned",
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
BatchStatus = Literal["enqueued", "unavailable"]
EvaluationStatus = Literal["verified", "parity_failed", "unavailable"]
EvidenceScope = Literal[
    "native_hiprtc_krylov_primitives_composite", "injected_test_double"
]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_ADDRESS_PATTERN = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_DECIMAL_HANDLE_PATTERN = re.compile(
    r"(?i)\b(?:pointer|ptr|handle|stream|module|function|device_address)\s*[=:]\s*\d+\b"
)
_PARITY_TOLERANCE = 1.0e-8
_ZERO_I32_DATA_HASH = array_data_hash(immutable_array([0], dtype="<i4"))
_BORROWED_NAMES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
    "reduced_direction",
    "reduced_jvp",
)
_OWNED_ORDER = (
    "jacobi_inverse",
    "work_x",
    "work_y",
    "preconditioned",
    "reduction_ping",
    "reduction_pong",
    "dot_result",
    "norm_result",
    "error_flag",
)
_FGMRES_PARENT_CAPABILITY_ROLES = (
    "reduced_state",
    "reduced_load",
    "jacobi_inverse",
)
_FGMRES_LIVE_OWNED_CAPABILITY_ROLES = (
    "solution_x",
    "true_residual",
    "work_w",
    "basis_v",
    "preconditioned_basis_z",
    "packed_dense_state",
    "fgmres_control_state_v2",
    "solve_record",
)
_FGMRES_LIVE_CAPABILITY_COUNT = 11
_FGMRES_PRODUCER_OPERATOR_ROLES = (
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_values",
)
_FGMRES_PRODUCER_WORKSPACE_ROLES = (
    "reduction_ping",
    "reduction_pong",
)


class HipKrylovPrimitivesContextError(RuntimeError):
    """Stable fail-closed error with an optional retryable cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipKrylovPrimitivesExecutionContext | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message or code
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesKernelBinding:
    abi_version: int
    architecture: str
    kernel_name: str
    prepare_positive_jacobi_symbol: str
    fill_symbol: str
    affine_symbol: str
    apply_jacobi_symbol: str
    dot_stage_symbol: str
    sum_stage_symbol: str
    lassq_stage_symbol: str
    lassq_combine_stage_symbol: str
    lassq_finalize_symbol: str
    vector_block_size: int
    reduction_segment_size: int
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
class HipKrylovPrimitivesBindings:
    parent_context_id: str
    parent_opening_receipt_hash: str
    source_apply_id: str
    source_apply_receipt_hash: str
    source_apply_sequence: int
    source_direction_generation: int
    source_execution_plan_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_partition_hash: str
    state_hash: str
    state_epoch: int
    lease_epoch: int
    kernel_origin: Literal["internally_compiled", "caller_supplied"]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesDimensions:
    free_dof_count: int
    reduced_csr_nnz: int
    reduction_segment_size: Literal[512]
    reduction_partial_count: int
    borrowed_buffer_count: Literal[5] = 5
    owned_buffer_count: Literal[9] = 9

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesBufferView:
    name: str
    dtype: Literal["<f8", "<i4"]
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
class HipKrylovPrimitivesTelemetry:
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
    error_flag_h2d_bytes: int = 0
    error_flag_d2h_bytes: int = 0
    vector_h2d_bytes: Literal[0] = 0
    reduction_h2d_bytes: Literal[0] = 0
    new_stream_create_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesAllocationLineage:
    capability_profile: Literal["foundation_non_promoting"]
    evidence_scope: Literal["foundation_non_promoting"]
    owner_role: Literal["krylov_primitives_owned_buffers"]
    runtime_device_bound: Literal[True]
    parent_borrowed_capability_count: Literal[5]
    managed_buffer_count: int
    managed_device_bytes: int
    all_owned_buffers_managed: bool
    pointer_values_serialized: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(slots=True)
class _HipKrylovPrimitivesOrphanCleanup:
    lease: HipAllocationOrphanLeaseV1
    pointer: object | None
    byte_length: int
    must_quarantine: bool = False
    disposition: CleanupDisposition = "live"


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesClaims:
    exclusive_parent_lease_active: bool
    same_runtime_and_stream: bool
    positive_jacobi_inverse_ready: bool
    affine_primitive_ready: bool
    dot_primitive_ready: bool
    stable_l2_primitive_ready: bool
    native_hiprtc_evidence: bool
    host_copy_zero_proven: Literal[False] = False
    diagonal_shift_or_clamp_used: Literal[False] = False
    spd_proven: Literal[False] = False
    pcg_ready: Literal[False] = False
    krylov_solver_ready: Literal[False] = False
    preconditioner_integrated: Literal[False] = False
    solver_iteration_ready: Literal[False] = False
    asymptotic_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    fallback_used: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesContextReceipt:
    status: ContextStatus
    context_id: str
    evidence_scope: EvidenceScope
    actual_backend: str | None
    promotion_eligible: Literal[False]
    reason: HipKrylovPrimitivesReason | None
    bindings: HipKrylovPrimitivesBindings
    kernel: HipKrylovPrimitivesKernelBinding | None
    dimensions: HipKrylovPrimitivesDimensions
    owned_buffers: tuple[HipKrylovPrimitivesBufferView, ...]
    allocation_lineage: HipKrylovPrimitivesAllocationLineage | None
    telemetry: HipKrylovPrimitivesTelemetry
    claims: HipKrylovPrimitivesClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_KRYLOV_PRIMITIVES_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_krylov_primitives_context_receipt(self)
        return _context_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesBatchDelta:
    fill_launch_attempt_count: int = 0
    fill_launch_success_count: int = 0
    affine_launch_attempt_count: int = 0
    affine_launch_success_count: int = 0
    jacobi_launch_attempt_count: int = 0
    jacobi_launch_success_count: int = 0
    dot_stage_launch_attempt_count: int = 0
    dot_stage_launch_success_count: int = 0
    sum_stage_launch_attempt_count: int = 0
    sum_stage_launch_success_count: int = 0
    lassq_stage_launch_attempt_count: int = 0
    lassq_stage_launch_success_count: int = 0
    lassq_combine_launch_attempt_count: int = 0
    lassq_combine_launch_success_count: int = 0
    lassq_finalize_launch_attempt_count: int = 0
    lassq_finalize_launch_success_count: int = 0
    h2d_operation_count: Literal[0] = 0
    d2h_operation_count: Literal[0] = 0
    allocation_count: Literal[0] = 0
    sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesBatchClaims:
    fill_enqueued: bool
    affine_program_enqueued: bool
    jacobi_apply_enqueued: bool
    dot_reduction_enqueued: bool
    stable_l2_reduction_enqueued: bool
    completion_fence_observed: Literal[False] = False
    solver_iteration: Literal[False] = False
    pcg_iteration: Literal[False] = False
    fallback_used: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesBatchReceipt:
    status: BatchStatus
    batch_id: str
    context_id: str
    opening_context_receipt_hash: str
    source_apply_receipt_hash: str
    sequence: int
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipKrylovPrimitivesReason | None
    telemetry_delta: HipKrylovPrimitivesBatchDelta
    claims: HipKrylovPrimitivesBatchClaims
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_KRYLOV_PRIMITIVES_BATCH_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_krylov_primitives_batch_receipt(self)
        return _batch_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesArrayDescriptor:
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
class HipKrylovPrimitivesParityMetric:
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
class HipKrylovPrimitivesParityReport:
    jacobi_inverse: HipKrylovPrimitivesParityMetric
    work_x: HipKrylovPrimitivesParityMetric
    work_y: HipKrylovPrimitivesParityMetric
    preconditioned: HipKrylovPrimitivesParityMetric
    dot_result: HipKrylovPrimitivesParityMetric
    norm_result: HipKrylovPrimitivesParityMetric
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "execution_plan_v2_cpu_reduced_csr_fp64",
            "oracle_role": "verification_only_never_fallback",
            "metrics": {
                "jacobi_inverse": self.jacobi_inverse.to_dict(),
                "work_x": self.work_x.to_dict(),
                "work_y": self.work_y.to_dict(),
                "preconditioned": self.preconditioned.to_dict(),
                "dot_result": self.dot_result.to_dict(),
                "norm_result": self.norm_result.to_dict(),
            },
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesEvaluationDelta:
    d2h_operation_attempt_count: int
    d2h_operation_success_count: int
    d2h_bytes_attempted: int
    d2h_bytes_succeeded: int
    sync_attempt_count: int
    sync_success_count: int
    allocation_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesEvaluationReceipt:
    status: EvaluationStatus
    execution_id: str
    context_id: str
    opening_context_receipt_hash: str
    source_apply_receipt_hash: str
    batch: HipKrylovPrimitivesBatchReceipt
    evidence_scope: EvidenceScope
    actual_backend: str
    promotion_eligible: Literal[False]
    reason: HipKrylovPrimitivesReason | None
    arrays: tuple[tuple[str, HipKrylovPrimitivesArrayDescriptor], ...]
    telemetry_delta: HipKrylovPrimitivesEvaluationDelta
    parity: HipKrylovPrimitivesParityReport | None
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_KRYLOV_PRIMITIVES_EVALUATION_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_krylov_primitives_evaluation_receipt(self)
        return _evaluation_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesEvaluation:
    receipt: HipKrylovPrimitivesEvaluationReceipt
    jacobi_inverse: np.ndarray | None
    work_x: np.ndarray | None
    work_y: np.ndarray | None
    preconditioned: np.ndarray | None
    dot_result: np.ndarray | None
    norm_result: np.ndarray | None
    batch: HipKrylovPrimitivesBatchReceipt


@dataclass(frozen=True, slots=True)
class HipKrylovPrimitivesContextOpenResult:
    context: HipKrylovPrimitivesExecutionContext | None
    receipt: HipKrylovPrimitivesContextReceipt

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


@dataclass(frozen=True, slots=True)
class _HipFgmresSolverChildSnapshot:
    """Process-local authority snapshot for one exact FGMRES child lease.

    The snapshot is deliberately not serializable evidence.  It carries object
    identity and device-pointer capabilities that are meaningful only while the
    matching child token remains live in the owning primitive context.
    """

    primitive_context: HipKrylovPrimitivesExecutionContext
    primitive_context_id: str
    primitive_opening_receipt: HipKrylovPrimitivesContextReceipt
    primitive_opening_receipt_hash: str
    source_apply: HipFreeSpaceApplyReceipt
    source_apply_receipt_hash: str
    source_apply_sequence: int
    source_direction_generation: int
    source_execution_plan: ExecutionPlanV2
    source_free_space_plan: HipFreeSpaceOperatorPlanV1
    source_state_displacement: np.ndarray
    source_state_displacement_hash: str
    primitive_parent_lease_epoch: int
    solver_child_lease_epoch: int
    runtime: Any
    loaded_runtime: Any
    stream: Any
    device_ordinal: int
    architecture: str
    source_execution_plan_hash: str
    source_free_space_plan_hash: str
    source_free_space_view_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_partition_hash: str
    state_hash: str
    state_epoch: int
    free_dof_count: int
    reduced_csr_nnz: int
    parent_allocation_capabilities: tuple[
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
    ]
    allocation_borrow_capabilities: tuple[HipAllocationCapabilityV1, ...] | None
    allocation_borrow_lease: HipAllocationBorrowLeaseV1 | None
    allocation_borrow_phase: str
    allocation_runtime_domain: Any
    allocation_runtime_domain_id: str
    allocation_device_ordinal: int
    allocation_generations: tuple[int, ...]
    device_pointers: tuple[tuple[str, Any], ...]

    def pointer(self, name: str) -> Any:
        for pointer_name, pointer in self.device_pointers:
            if pointer_name == name:
                return pointer
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class _HipFgmresDelegatedProducerResource:
    """One non-owning, process-local producer resource binding.

    This is not an allocation-registry artifact and intentionally has no
    serialization surface.  Its authority exists only through the exact live
    FGMRES child and the parent/owner objects captured by its projection.
    """

    delegation_kind: Literal["free_space_parent_borrow", "krylov_primitive_owned"]
    role: str
    capability: HipAllocationCapabilityV1
    allocation_owner: HipAllocationOwnerV1
    allocation_id: int
    owner_identity: int
    base: Any
    pointer_snapshot: int
    element_type: str
    element_extent: tuple[int, ...]
    nbytes: int
    generation: int
    runtime_owner: Any
    runtime_domain: Any
    runtime_domain_id: str
    device_ordinal: int


@dataclass(frozen=True, slots=True)
class _HipFgmresProducerResourceProjection:
    """Exact CSR3 + reduction2 capability projected into one live child."""

    primitive_context: HipKrylovPrimitivesExecutionContext
    primitive_context_id: str
    primitive_parent_lease_token: object
    primitive_parent_lease_epoch: int
    solver_child_token: object
    solver_child_lease_epoch: int
    source_apply: HipFreeSpaceApplyReceipt
    source_apply_receipt_hash: str
    runtime: Any
    loaded_runtime: Any
    stream: Any
    runtime_domain: Any
    runtime_domain_id: str
    device_ordinal: int
    operator_parent_borrow_capabilities: tuple[HipAllocationCapabilityV1, ...]
    operator_parent_borrow_lease: HipAllocationBorrowLeaseV1
    solver_allocation_borrow_capabilities: tuple[HipAllocationCapabilityV1, ...]
    solver_allocation_borrow_lease: HipAllocationBorrowLeaseV1
    delegated_operator_resources: tuple[
        _HipFgmresDelegatedProducerResource,
        _HipFgmresDelegatedProducerResource,
        _HipFgmresDelegatedProducerResource,
    ]
    delegated_workspace_resources: tuple[
        _HipFgmresDelegatedProducerResource,
        _HipFgmresDelegatedProducerResource,
    ]

    @property
    def ordered_resources(self) -> tuple[_HipFgmresDelegatedProducerResource, ...]:
        return self.delegated_operator_resources + self.delegated_workspace_resources

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(resource.role for resource in self.ordered_resources)

    @property
    def capabilities(self) -> tuple[HipAllocationCapabilityV1, ...]:
        return tuple(resource.capability for resource in self.ordered_resources)

    def resource(self, role: str) -> _HipFgmresDelegatedProducerResource:
        for resource in self.ordered_resources:
            if resource.role == role:
                return resource
        raise KeyError(role)

    def pointer(self, role: str) -> Any:
        return self.resource(role).base


class HipKrylovPrimitivesExecutionContext:
    """Exclusive child owner of reduced Krylov primitive workspaces."""

    def __init__(
        self,
        *,
        parent: HipFreeSpaceExecutionContext,
        source_apply: HipFreeSpaceApplyReceipt,
        lease_token: object,
        lease_epoch: int,
        kernel: Any,
        kernel_binding: HipKrylovPrimitivesKernelBinding | None,
        kernel_internally_compiled: bool,
        evidence_scope: EvidenceScope,
        context_id: str,
        borrowed_pointers: dict[str, Any],
        parent_capabilities: tuple[HipAllocationCapabilityV1, ...],
        pointers: dict[str, Any],
        allocation_owner: HipAllocationOwnerV1 | None,
        owned_capabilities: dict[str, HipAllocationCapabilityV1],
        pending_free_leases: dict[str, HipAllocationFreeLeaseV1] | None,
        cleanup_dispositions: dict[str, CleanupDisposition] | None,
        orphan_cleanups: list[_HipKrylovPrimitivesOrphanCleanup] | None,
        allocation_owner_closed: bool,
        allocation_lineage: HipKrylovPrimitivesAllocationLineage | None,
        owned_buffers: tuple[HipKrylovPrimitivesBufferView, ...],
        telemetry: HipKrylovPrimitivesTelemetry,
        opening_status: ContextStatus,
        failure_reason: HipKrylovPrimitivesReason | None,
        kernel_closed: bool = False,
    ) -> None:
        self._parent = parent
        self._source_apply = source_apply
        self._lease_token = lease_token
        self._lease_epoch = lease_epoch
        self._runtime = parent._runtime
        self._stream = parent._stream
        self._kernel = kernel
        self._kernel_binding = kernel_binding
        self._kernel_internally_compiled = kernel_internally_compiled
        self._evidence_scope = evidence_scope
        self._context_id = context_id
        self._borrowed_pointers = borrowed_pointers
        self._parent_capabilities = parent_capabilities
        self._parent_capability_snapshot = parent_capabilities
        self._pointers = pointers
        self._allocation_owner = allocation_owner
        self._allocation_owner_snapshot = allocation_owner
        self._owned_capabilities = owned_capabilities
        self._owned_capability_snapshot = dict(owned_capabilities)
        self._pending_free_leases = (
            {} if pending_free_leases is None else pending_free_leases
        )
        self._cleanup_dispositions = (
            {} if cleanup_dispositions is None else cleanup_dispositions
        )
        self._orphan_cleanups = [] if orphan_cleanups is None else orphan_cleanups
        self._lineage_managed_roles = set(owned_capabilities)
        self._lineage_orphan_seen_ids = {
            cleanup.lease.lease_id for cleanup in self._orphan_cleanups
        }
        self._initial_managed_device_bytes = telemetry.current_device_bytes
        self._free_acknowledged_roles: set[str] = set()
        self._free_quarantined_sizes: dict[str, int] = {}
        self._orphan_acknowledged_sizes: dict[int, int] = {}
        self._orphan_quarantined_sizes: dict[int, int] = {}
        self._unknown_orphan_requested_sizes: dict[int, int] = {}
        self._allocation_owner_closed = allocation_owner_closed
        self._allocation_lineage_snapshot = allocation_lineage
        self._owned_buffers = owned_buffers
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
        self._last_batch: HipKrylovPrimitivesBatchReceipt | None = None
        self._batch_witnesses: dict[int, str] = {}
        self._queue_lock = threading.RLock()
        self._fgmres_solver_child_token: object | None = None
        self._fgmres_solver_child_epoch_value = 0
        self._fgmres_solver_child_snapshot_value: (
            _HipFgmresSolverChildSnapshot | None
        ) = None
        self._fgmres_solver_child_parent_capability_snapshot: (
            tuple[
                HipAllocationCapabilityV1,
                HipAllocationCapabilityV1,
                HipAllocationCapabilityV1,
            ]
            | None
        ) = None
        self._fgmres_solver_child_owned_owner_snapshot: HipAllocationOwnerV1 | None = (
            None
        )
        self._fgmres_solver_child_owned_owner_identity_snapshot: (
            tuple[int, str, str] | None
        ) = None
        self._fgmres_solver_child_owned_owner_generation_snapshot: int | None = None
        self._fgmres_solver_child_group_capability_snapshot: (
            tuple[HipAllocationCapabilityV1, ...] | None
        ) = None
        self._fgmres_solver_child_borrow_lease: HipAllocationBorrowLeaseV1 | None = None
        self._fgmres_producer_resource_projection_value: (
            _HipFgmresProducerResourceProjection | None
        ) = None
        self._fgmres_solver_child_rollback_pending = False
        self._fgmres_solver_child_phase = "idle"
        self._released_fgmres_solver_child_token: object | None = None
        self._closing = False
        self._parent_snapshot = parent
        self._runtime_snapshot = self._runtime
        self._stream_snapshot = self._stream
        self._source_apply_snapshot = source_apply
        self._source_apply_hash_snapshot = source_apply.receipt_hash
        self._source_apply_sequence_snapshot = source_apply.sequence
        self._source_direction_generation_snapshot = source_apply.direction_generation
        self._parent_opening_hash_snapshot = parent.opening_receipt.context_receipt_hash
        self._borrowed_pointer_snapshot = dict(borrowed_pointers)
        self._owned_pointer_snapshot = dict(pointers)
        self._kernel_object_snapshot = kernel
        self._kernel_identity_snapshot = (
            None if kernel is None else getattr(kernel, "identity", None)
        )
        self._bindings_snapshot = _bindings(
            parent, source_apply, lease_epoch, kernel_internally_compiled
        )
        self._dimensions_snapshot = _dimensions(parent)
        self._opening_receipt = self._build_receipt(opening_status)

    def __enter__(self) -> HipKrylovPrimitivesExecutionContext:
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
    def opening_receipt(self) -> HipKrylovPrimitivesContextReceipt:
        return self._opening_receipt

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def parent_context(self) -> HipFreeSpaceExecutionContext:
        return self._parent

    def receipt(self) -> HipKrylovPrimitivesContextReceipt:
        with self._queue_lock:
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

    def enqueue_primitive_batch(self) -> HipKrylovPrimitivesBatchReceipt:
        """Enqueue the fixed diagnostic primitive program without a fence."""

        with self._queue_lock:
            self._require_no_fgmres_solver_child()
            self._require_usable()
            self._parent._require_krylov_consumer(self._lease_token)
            self._validate_authority()
            sequence = self._sequence + 1
            delta = HipKrylovPrimitivesBatchDelta()

            def launch(
                attempt_field: str,
                success_field: str,
                code: str,
                method: Any,
                *arguments: Any,
            ) -> bool:
                nonlocal delta
                delta = replace(
                    delta,
                    **{attempt_field: getattr(delta, attempt_field) + 1},
                )
                self._telemetry = replace(
                    self._telemetry,
                    kernel_launch_attempt_count=(
                        self._telemetry.kernel_launch_attempt_count + 1
                    ),
                )
                try:
                    result = method(self._stream, *arguments)
                    if result is not None:
                        _fail(
                            "hip_krylov_primitives_kernel_contract_invalid",
                            f"/batch/{code}",
                        )
                except Exception as exc:
                    receipt = self._failed_batch(sequence, delta, code, exc)
                    raise _BatchAbort(receipt) from exc
                delta = replace(
                    delta,
                    **{success_field: getattr(delta, success_field) + 1},
                )
                self._telemetry = replace(
                    self._telemetry,
                    kernel_launch_success_count=(
                        self._telemetry.kernel_launch_success_count + 1
                    ),
                )
                return True

            f = self._dimensions_snapshot.free_dof_count
            p = self._dimensions_snapshot.reduction_partial_count
            try:
                launch(
                    "fill_launch_attempt_count",
                    "fill_launch_success_count",
                    "hip_krylov_primitives_fill_launch_failed",
                    self._kernel.launch_fill,
                    f,
                    0.25,
                    self._pointers["work_y"],
                    self._pointers["error_flag"],
                )
                launch(
                    "affine_launch_attempt_count",
                    "affine_launch_success_count",
                    "hip_krylov_primitives_affine_x_launch_failed",
                    self._kernel.launch_affine,
                    f,
                    -0.5,
                    self._borrowed_pointers["reduced_direction"],
                    0.0,
                    self._borrowed_pointers["reduced_direction"],
                    self._pointers["work_x"],
                    self._pointers["error_flag"],
                )
                launch(
                    "affine_launch_attempt_count",
                    "affine_launch_success_count",
                    "hip_krylov_primitives_affine_y_launch_failed",
                    self._kernel.launch_affine,
                    f,
                    0.25,
                    self._borrowed_pointers["reduced_jvp"],
                    1.0,
                    self._pointers["work_y"],
                    self._pointers["work_y"],
                    self._pointers["error_flag"],
                )
                launch(
                    "jacobi_launch_attempt_count",
                    "jacobi_launch_success_count",
                    "hip_krylov_primitives_jacobi_launch_failed",
                    self._kernel.launch_apply_jacobi,
                    f,
                    self._pointers["jacobi_inverse"],
                    self._borrowed_pointers["reduced_direction"],
                    self._pointers["preconditioned"],
                    self._pointers["error_flag"],
                )
                launch(
                    "dot_stage_launch_attempt_count",
                    "dot_stage_launch_success_count",
                    "hip_krylov_primitives_dot_stage_launch_failed",
                    self._kernel.launch_dot_stage,
                    f,
                    self._borrowed_pointers["reduced_direction"],
                    self._pointers["preconditioned"],
                    self._pointers["reduction_ping"],
                    self._pointers["error_flag"],
                )
                count = p
                input_pointer = self._pointers["reduction_ping"]
                toggle = False
                while True:
                    output_count = reduction_output_count(count)
                    output_pointer = (
                        self._pointers["dot_result"]
                        if output_count == 1
                        else self._pointers[
                            "reduction_ping" if toggle else "reduction_pong"
                        ]
                    )
                    launch(
                        "sum_stage_launch_attempt_count",
                        "sum_stage_launch_success_count",
                        "hip_krylov_primitives_sum_stage_launch_failed",
                        self._kernel.launch_sum_stage,
                        count,
                        input_pointer,
                        output_pointer,
                        self._pointers["error_flag"],
                    )
                    if output_count == 1:
                        break
                    input_pointer = output_pointer
                    count = output_count
                    toggle = not toggle

                launch(
                    "lassq_stage_launch_attempt_count",
                    "lassq_stage_launch_success_count",
                    "hip_krylov_primitives_lassq_stage_launch_failed",
                    self._kernel.launch_lassq_stage,
                    f,
                    self._borrowed_pointers["reduced_direction"],
                    self._pointers["reduction_ping"],
                    self._pointers["error_flag"],
                )
                count = p
                input_pointer = self._pointers["reduction_ping"]
                toggle = False
                while True:
                    output_count = reduction_output_count(count)
                    output_pointer = self._pointers[
                        "reduction_ping" if toggle else "reduction_pong"
                    ]
                    launch(
                        "lassq_combine_launch_attempt_count",
                        "lassq_combine_launch_success_count",
                        "hip_krylov_primitives_lassq_combine_launch_failed",
                        self._kernel.launch_lassq_combine_stage,
                        count,
                        input_pointer,
                        output_pointer,
                        self._pointers["error_flag"],
                    )
                    input_pointer = output_pointer
                    if output_count == 1:
                        break
                    count = output_count
                    toggle = not toggle
                launch(
                    "lassq_finalize_launch_attempt_count",
                    "lassq_finalize_launch_success_count",
                    "hip_krylov_primitives_lassq_finalize_launch_failed",
                    self._kernel.launch_lassq_finalize,
                    input_pointer,
                    self._pointers["norm_result"],
                    self._pointers["error_flag"],
                )
            except _BatchAbort as abort:
                return abort.receipt

            self._sequence = sequence
            receipt = _build_batch_receipt(
                status="enqueued",
                context=self,
                sequence=sequence,
                delta=delta,
                reason=None,
            )
            self._record_batch_witness(receipt)
            return receipt

    def evaluate_for_verification(self) -> HipKrylovPrimitivesEvaluation:
        """Run a fresh batch, fence once, then compare exported arrays to CPU."""

        with self._queue_lock:
            self._require_no_fgmres_solver_child()
            self._require_usable()
            batch = self.enqueue_primitive_batch()
            execution_id = canonical_hash(
                {
                    "context_id": self._context_id,
                    "opening_context_receipt_hash": (
                        self._opening_receipt.context_receipt_hash
                    ),
                    "batch_receipt_hash": batch.receipt_hash,
                }
            )
            zero_delta = HipKrylovPrimitivesEvaluationDelta(0, 0, 0, 0, 0, 0)
            if batch.status != "enqueued":
                return _unavailable_evaluation(
                    self,
                    execution_id,
                    batch,
                    zero_delta,
                    "hip_krylov_primitives_batch_unavailable",
                    batch.reason.detail if batch.reason else "batch unavailable",
                )

            f = self._dimensions_snapshot.free_dof_count
            host_arrays = {
                "jacobi_inverse": np.empty(f, dtype="<f8"),
                "work_x": np.empty(f, dtype="<f8"),
                "work_y": np.empty(f, dtype="<f8"),
                "preconditioned": np.empty(f, dtype="<f8"),
                "dot_result": np.empty(1, dtype="<f8"),
                "norm_result": np.empty(1, dtype="<f8"),
            }
            host_error = np.empty(1, dtype="<i4")
            delta = zero_delta
            try:
                for name, host in (*host_arrays.items(), ("error_flag", host_error)):
                    delta = replace(
                        delta,
                        d2h_operation_attempt_count=(
                            delta.d2h_operation_attempt_count + 1
                        ),
                        d2h_bytes_attempted=delta.d2h_bytes_attempted
                        + int(host.nbytes),
                    )
                    self._telemetry = replace(
                        self._telemetry,
                        d2h_operation_attempt_count=(
                            self._telemetry.d2h_operation_attempt_count + 1
                        ),
                        d2h_bytes_attempted=(
                            self._telemetry.d2h_bytes_attempted + int(host.nbytes)
                        ),
                        error_flag_d2h_bytes=(
                            self._telemetry.error_flag_d2h_bytes
                            + (int(host.nbytes) if name == "error_flag" else 0)
                        ),
                    )
                    self._runtime.copy_d2h_async(
                        host, self._pointers[name], self._stream
                    )
                    delta = replace(
                        delta,
                        d2h_operation_success_count=(
                            delta.d2h_operation_success_count + 1
                        ),
                        d2h_bytes_succeeded=(
                            delta.d2h_bytes_succeeded + int(host.nbytes)
                        ),
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
                delta = replace(delta, sync_attempt_count=1)
                self._telemetry = replace(
                    self._telemetry,
                    sync_attempt_count=self._telemetry.sync_attempt_count + 1,
                )
                self._runtime.synchronize(self._stream)
                delta = replace(delta, sync_success_count=1)
                self._telemetry = replace(
                    self._telemetry,
                    sync_success_count=self._telemetry.sync_success_count + 1,
                )
                _acknowledge_kernel_completion_if_pending(self._kernel, self._stream)
            except Exception as exc:
                self._poison("hip_krylov_primitives_verification_transfer_failed")
                return _unavailable_evaluation(
                    self,
                    execution_id,
                    batch,
                    delta,
                    "hip_krylov_primitives_verification_transfer_failed",
                    exc,
                )
            if int(host_error[0]) != 0:
                self._poison("hip_krylov_primitives_device_error")
                return _unavailable_evaluation(
                    self,
                    execution_id,
                    batch,
                    delta,
                    "hip_krylov_primitives_device_error",
                    f"device error bits {int(host_error[0])}",
                )

            expected = _cpu_expected(self)
            arrays = {
                name: immutable_array(value, dtype="<f8")
                for name, value in host_arrays.items()
            }
            parity = _parity(arrays, expected)
            status: EvaluationStatus = "verified" if parity.passed else "parity_failed"
            receipt = _build_evaluation_receipt(
                status=status,
                execution_id=execution_id,
                context=self,
                batch=batch,
                arrays=arrays,
                delta=delta,
                parity=parity,
                reason=None,
            )
            evaluation = HipKrylovPrimitivesEvaluation(
                receipt,
                arrays["jacobi_inverse"],
                arrays["work_x"],
                arrays["work_y"],
                arrays["preconditioned"],
                arrays["dot_result"],
                arrays["norm_result"],
                batch,
            )
            validated = validate_hip_krylov_primitives_evaluation(
                evaluation, expected_context=self
            )
            if not parity.passed:
                self._poison("hip_krylov_primitives_cpu_parity_failed")
            return validated

    def close(self) -> None:
        with self._queue_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            return
        if self._closing:
            _fail("hip_krylov_primitives_cleanup_reentrant", "/cleanup")
        self._closing = True
        try:
            self._require_no_fgmres_solver_child()
            if self._cleanup_failed:
                self._recover_allocation_cleanup_authority()
                if (
                    not self._kernel_closed
                    and self._kernel is not None
                    and bool(getattr(self._kernel, "closed", False))
                ):
                    self._kernel_closed = True
            self._refresh_lifecycle_terminal_telemetry()
            if not self._close_sync_complete and not self._cleanup_failed:
                try:
                    self._validate_cleanup_authority()
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_krylov_primitives_cleanup_authority_invalid",
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
                    self._poison("hip_krylov_primitives_cleanup_sync_failed")
                    self._raise_cleanup_error(
                        "hip_krylov_primitives_cleanup_sync_failed",
                        "/cleanup/synchronize",
                        exc,
                    )
                self._telemetry = replace(
                    self._telemetry,
                    sync_success_count=self._telemetry.sync_success_count + 1,
                )
                try:
                    _acknowledge_kernel_completion_if_pending(
                        self._kernel, self._stream
                    )
                except Exception as exc:
                    self._poison("hip_krylov_primitives_cleanup_completion_ack_failed")
                    self._raise_cleanup_error(
                        "hip_krylov_primitives_cleanup_completion_ack_failed",
                        "/cleanup/completion_acknowledgement",
                        exc,
                    )
                self._close_sync_complete = True

            first_error: Exception | None = None
            for orphan in tuple(self._orphan_cleanups):
                error = self._retire_orphan_cleanup(orphan)
                first_error = first_error or error
            for name in reversed(_OWNED_ORDER):
                error = self._retire_owned_allocation(name)
                first_error = first_error or error
            if self._owned_capabilities or self._orphan_cleanups:
                self._raise_cleanup_error(
                    "hip_krylov_primitives_cleanup_failed",
                    "/cleanup/owned_buffers",
                    first_error or "allocation lineage remains",
                )

            if self._allocation_owner is not None and not self._allocation_owner_closed:
                try:
                    self._allocation_owner.close()
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_krylov_primitives_lineage_owner_cleanup_failed",
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
                        "hip_krylov_primitives_kernel_cleanup_failed",
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
                    self._parent._release_krylov_consumer(self._lease_token)
                except Exception as exc:
                    self._raise_cleanup_error(
                        "hip_krylov_primitives_lease_release_failed",
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
            self._cleanup_failed = False
            self._refresh_lifecycle_terminal_telemetry()
            if self._cleanup_quarantined:
                self._failure_reason = HipKrylovPrimitivesReason(
                    "hip_krylov_primitives_cleanup_quarantined",
                    "One or more allocator outcomes remain quarantined; no device free will be retried.",
                )
            else:
                self._failure_reason = None
            # Every serialized terminal marker is converged before the closed
            # fast-path is published.
            self._closed = True
        except BaseException as exc:
            if not isinstance(exc, Exception) and not self._closed:
                terminal = (
                    not self._owned_capabilities
                    and not self._orphan_cleanups
                    and (
                        self._allocation_owner is None or self._allocation_owner_closed
                    )
                    and (self._kernel is None or self._kernel_closed)
                    and self._lease_released
                )
                if terminal:
                    self._cleanup_failed = False
                    self._refresh_lifecycle_terminal_telemetry()
                    if self._cleanup_quarantined:
                        self._failure_reason = HipKrylovPrimitivesReason(
                            "hip_krylov_primitives_cleanup_quarantined",
                            "One or more allocator outcomes remain quarantined; no device free will be retried.",
                        )
                    else:
                        self._failure_reason = None
                    self._closed = True
                else:
                    self._cleanup_failed = True
                    self._failure_reason = HipKrylovPrimitivesReason(
                        "hip_krylov_primitives_cleanup_interrupted",
                        _detail(exc),
                    )
            raise
        finally:
            self._closing = False

    def _retire_owned_allocation(self, name: str) -> Exception | None:
        capability = self._owned_capabilities.get(name)
        if capability is None:
            return None
        owner = self._allocation_owner
        if owner is None:
            return HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_lineage_owner_missing",
                f"/cleanup/owned_buffers/{name}",
                "allocation capability has no owner",
            )
        size = _buffer_view(self._owned_buffers, name).byte_length
        try:
            disposition = self._cleanup_dispositions.get(name, "live")
            lease = self._pending_free_leases.get(name)
            if disposition == "terminal":
                self._finalize_owned_retirement_local(name)
                return None
            if disposition == "live":
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
                            self._cleanup_dispositions[name] = "quarantine_pending"
                            outcome = owner.resolve_poisoned_allocation_quarantine(
                                capability
                            )
                            if outcome != "quarantined":
                                _fail(
                                    "hip_krylov_primitives_lineage_outcome_invalid",
                                    f"/cleanup/owned_buffers/{name}",
                                )
                            self._finish_owned_retirement(name, size, quarantined=True)
                            return None
                        raise
                    self._pending_free_leases[name] = lease
                self._telemetry = replace(
                    self._telemetry,
                    deallocation_attempt_count=(
                        self._telemetry.deallocation_attempt_count + 1
                    ),
                )
                self._cleanup_dispositions[name] = "free_call_inflight"
                try:
                    self._runtime.free(lease.pointer_snapshot)
                    self._cleanup_dispositions[name] = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(self._runtime, exc):
                        self._cleanup_dispositions[name] = "live"
                        if isinstance(exc, Exception):
                            return exc
                        raise
                    self._cleanup_dispositions[name] = "quarantine_pending"
                    outcome = owner.resolve_free_quarantine(lease)
                    if outcome != "quarantined":
                        _fail(
                            "hip_krylov_primitives_lineage_outcome_invalid",
                            f"/cleanup/owned_buffers/{name}",
                        )
                    self._finish_owned_retirement(name, size, quarantined=True)
                    if isinstance(exc, Exception):
                        return None
                    raise
                disposition = self._cleanup_dispositions[name]
            elif disposition == "free_call_inflight":
                self._cleanup_dispositions[name] = "quarantine_pending"
                disposition = "quarantine_pending"

            if disposition == "quarantine_pending":
                if lease is None:
                    outcome = owner.resolve_poisoned_allocation_quarantine(capability)
                else:
                    outcome = owner.resolve_free_quarantine(lease)
                if outcome != "quarantined":
                    _fail(
                        "hip_krylov_primitives_lineage_outcome_invalid",
                        f"/cleanup/owned_buffers/{name}",
                    )
                self._finish_owned_retirement(name, size, quarantined=True)
                return None
            if disposition != "external_free_succeeded" or lease is None:
                _fail(
                    "hip_krylov_primitives_cleanup_disposition_invalid",
                    f"/cleanup/owned_buffers/{name}",
                )
            outcome = owner.resolve_free_success(lease)
            if outcome != "succeeded":
                _fail(
                    "hip_krylov_primitives_lineage_outcome_invalid",
                    f"/cleanup/owned_buffers/{name}",
                )
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
        # Publish the terminal disposition before dropping the exact lease or
        # any other local cleanup authority.  A signal between subsequent
        # field removals therefore resumes local finalization without another
        # allocator call or a second lineage resolution.
        self._cleanup_dispositions[name] = "terminal"
        self._pointers.pop(name, None)
        self._owned_pointer_snapshot.pop(name, None)
        self._owned_capability_snapshot.pop(name, None)
        self._pending_free_leases.pop(name, None)
        # Keep the authoritative capability reachable until all local terminal
        # projections have converged.  A BaseException before this final pop is
        # retried from the persistent terminal disposition without a device free.
        self._owned_capabilities.pop(name, None)

    def _finalize_owned_retirement_local(self, name: str) -> None:
        self._refresh_retirement_telemetry()
        self._pointers.pop(name, None)
        self._owned_pointer_snapshot.pop(name, None)
        self._owned_capability_snapshot.pop(name, None)
        self._pending_free_leases.pop(name, None)
        self._owned_capabilities.pop(name, None)

    def _retire_orphan_cleanup(
        self,
        cleanup: _HipKrylovPrimitivesOrphanCleanup,
    ) -> Exception | None:
        owner = self._allocation_owner
        if owner is None:
            return HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_lineage_owner_missing",
                "/cleanup/allocation_lineage/orphan",
                "orphan cleanup lease has no owner",
            )
        lease = cleanup.lease
        try:
            disposition = cleanup.disposition
            if disposition == "terminal":
                self._finalize_orphan_retirement_local(cleanup)
                return None
            if cleanup.must_quarantine or cleanup.pointer is None:
                cleanup.disposition = "quarantine_pending"
                disposition = "quarantine_pending"
            if disposition == "live":
                validate_hip_allocation_owner_v1(owner)
                self._telemetry = replace(
                    self._telemetry,
                    deallocation_attempt_count=(
                        self._telemetry.deallocation_attempt_count + 1
                    ),
                )
                cleanup.disposition = "free_call_inflight"
                try:
                    self._runtime.free(lease.pointer_snapshot)
                    cleanup.disposition = "external_free_succeeded"
                except BaseException as exc:
                    if not _free_outcome_uncertain(self._runtime, exc):
                        cleanup.disposition = "live"
                        if isinstance(exc, Exception):
                            return exc
                        raise
                    cleanup.disposition = "quarantine_pending"
                    outcome = owner.resolve_orphan_free_quarantine(lease)
                    if outcome != "quarantined":
                        _fail(
                            "hip_krylov_primitives_lineage_outcome_invalid",
                            "/cleanup/allocation_lineage/orphan",
                        )
                    self._finish_orphan_retirement(cleanup, quarantined=True)
                    if isinstance(exc, Exception):
                        return None
                    raise
                disposition = cleanup.disposition
            elif disposition == "free_call_inflight":
                cleanup.disposition = "quarantine_pending"
                disposition = "quarantine_pending"

            if disposition == "quarantine_pending":
                outcome = owner.resolve_orphan_free_quarantine(lease)
                if outcome != "quarantined":
                    _fail(
                        "hip_krylov_primitives_lineage_outcome_invalid",
                        "/cleanup/allocation_lineage/orphan",
                    )
                self._finish_orphan_retirement(cleanup, quarantined=True)
                return None
            if disposition != "external_free_succeeded":
                _fail(
                    "hip_krylov_primitives_cleanup_disposition_invalid",
                    "/cleanup/allocation_lineage/orphan",
                )
            outcome = owner.resolve_orphan_free_success(lease)
            if outcome != "succeeded":
                _fail(
                    "hip_krylov_primitives_lineage_outcome_invalid",
                    "/cleanup/allocation_lineage/orphan",
                )
            self._finish_orphan_retirement(cleanup, quarantined=False)
            return None
        except Exception as exc:
            return exc

    def _finish_orphan_retirement(
        self,
        cleanup: _HipKrylovPrimitivesOrphanCleanup,
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
            self._orphan_acknowledged_sizes[lease_id] = cleanup.byte_length
        self._refresh_retirement_telemetry()
        cleanup.disposition = "terminal"
        self._finalize_orphan_retirement_local(cleanup)

    def _finalize_orphan_retirement_local(
        self,
        cleanup: _HipKrylovPrimitivesOrphanCleanup,
    ) -> None:
        self._refresh_retirement_telemetry()
        if cleanup in self._orphan_cleanups:
            self._orphan_cleanups.remove(cleanup)

    def _refresh_retirement_telemetry(self) -> None:
        externally_freed_owned = {
            name
            for name, disposition in self._cleanup_dispositions.items()
            if disposition == "external_free_succeeded"
        }
        successfully_freed_owned = (
            externally_freed_owned | self._free_acknowledged_roles
        )
        owned_success_bytes = sum(
            _buffer_view(self._owned_buffers, name).byte_length
            for name in successfully_freed_owned
        )
        live_orphan_successes = {
            cleanup.lease.lease_id: cleanup.byte_length
            for cleanup in self._orphan_cleanups
            if cleanup.disposition == "external_free_succeeded"
        }
        orphan_successes = dict(self._orphan_acknowledged_sizes)
        orphan_successes.update(live_orphan_successes)
        successful_bytes = owned_success_bytes + sum(orphan_successes.values())
        quarantined_bytes = sum(self._free_quarantined_sizes.values()) + sum(
            self._orphan_quarantined_sizes.values()
        )
        self._telemetry = replace(
            self._telemetry,
            deallocation_success_count=(
                len(successfully_freed_owned) + len(orphan_successes)
            ),
            current_device_bytes=max(
                0,
                self._initial_managed_device_bytes - successful_bytes,
            ),
            lineage_free_acknowledgement_count=len(self._free_acknowledged_roles),
            lineage_free_quarantine_count=len(self._free_quarantined_sizes),
            lineage_orphan_acknowledgement_count=len(self._orphan_acknowledged_sizes),
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

        owner = self._allocation_owner_snapshot
        if owner is None:
            return
        self._allocation_owner = owner
        if self._allocation_owner_closed or owner.closed:
            self._allocation_owner_closed = True
            self._refresh_lifecycle_terminal_telemetry()
            return
        capabilities, free_leases, orphan_leases = (
            snapshot_hip_allocation_owner_cleanup_v1(owner)
        )
        known_roles = set(_OWNED_ORDER)
        for mapping in (
            self._owned_capabilities,
            self._owned_capability_snapshot,
            self._pointers,
            self._owned_pointer_snapshot,
            self._pending_free_leases,
            self._cleanup_dispositions,
        ):
            for role in tuple(mapping):
                if role not in known_roles:
                    mapping.pop(role, None)
        self._lineage_managed_roles.intersection_update(known_roles)
        recovered_roles: set[str] = set()
        for capability in capabilities:
            identity_roles = tuple(
                role
                for role, known in self._owned_capability_snapshot.items()
                if known is capability
            )
            role = identity_roles[0] if len(identity_roles) == 1 else capability.role
            if type(role) is not str or role not in known_roles:
                _fail(
                    "hip_krylov_primitives_allocation_lineage_changed",
                    "/cleanup/allocation_lineage/capability",
                )
            recovered_roles.add(role)
            self._lineage_managed_roles.add(role)
            # The registry snapshot is authoritative during recovery.  Replace
            # mutated live mappings instead of preserving caller-visible drift.
            self._owned_capabilities[role] = capability
            self._owned_capability_snapshot[role] = capability
            self._pointers[role] = capability.base
            self._owned_pointer_snapshot[role] = capability.base
            self._cleanup_dispositions.setdefault(role, "live")

        recovered_free_roles: set[str] = set()
        for lease in free_leases:
            identity_roles = tuple(
                role
                for role, known in self._owned_capability_snapshot.items()
                if known is lease.capability
            )
            role = (
                identity_roles[0] if len(identity_roles) == 1 else lease.capability.role
            )
            if type(role) is not str or role not in known_roles:
                _fail(
                    "hip_krylov_primitives_allocation_lineage_changed",
                    "/cleanup/allocation_lineage/free_lease",
                )
            recovered_free_roles.add(role)
            self._pending_free_leases[role] = lease
            self._cleanup_dispositions.setdefault(role, "live")

        for role in recovered_roles:
            if (
                role not in recovered_free_roles
                or self._cleanup_dispositions.get(role) == "terminal"
            ):
                self._cleanup_dispositions[role] = "live"
            if role not in recovered_free_roles:
                self._pending_free_leases.pop(role, None)

        known_orphans = {cleanup.lease.lease_id for cleanup in self._orphan_cleanups}
        for lease in orphan_leases:
            if lease.lease_id in known_orphans:
                continue
            role = lease.role
            if type(role) is not str or role not in known_roles:
                _fail(
                    "hip_krylov_primitives_allocation_lineage_changed",
                    "/cleanup/allocation_lineage/orphan",
                )
            self._orphan_cleanups.append(
                _HipKrylovPrimitivesOrphanCleanup(
                    lease=lease,
                    pointer=lease.pointer_snapshot,
                    byte_length=lease.nbytes,
                    # The exact allocation failure classification was lost at
                    # the caller handoff.  Conservatively quarantine and never
                    # issue a device free for the recovered orphan.
                    must_quarantine=True,
                )
            )
            known_orphans.add(lease.lease_id)
            self._lineage_orphan_seen_ids.add(lease.lease_id)

        managed_count = len(self._lineage_managed_roles)
        managed_bytes = sum(
            _buffer_view(self._owned_buffers, role).byte_length
            for role in self._lineage_managed_roles
        )
        live_orphan_success_count = sum(
            cleanup.pointer is not None for cleanup in self._orphan_cleanups
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
        minimum_successes = managed_count + live_orphan_success_count
        minimum_attempts = managed_count + len(self._orphan_cleanups)
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
        self._failure_reason = HipKrylovPrimitivesReason(code, _detail(error))
        raise HipKrylovPrimitivesContextError(
            code,
            path,
            self._failure_reason.detail,
            cleanup_owner=self,
        ) from (error if isinstance(error, BaseException) else None)

    def _acquire_fgmres_solver_child_for_source_apply(
        self, source_apply: HipFreeSpaceApplyReceipt
    ) -> object:
        """Lease the raw primitive/apply snapshot for compatibility callers.

        This path intentionally does not borrow allocation capabilities.  A
        production live FGMRES owner must preissue its token, reserve through
        :meth:`_reserve_fgmres_solver_child_for_source_apply`, and commit one
        exact eleven-capability allocation borrow instead.
        """

        with self._queue_lock:
            self._require_exact_fgmres_source_apply(source_apply)
            self._require_usable()
            self._require_fgmres_parent_authority_locked()
            self._validate_authority()
            if (
                self._fgmres_solver_child_token is not None
                or self._fgmres_solver_child_phase != "idle"
                or self._fgmres_producer_resource_projection_value is not None
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_active",
                    "/lifetime/fgmres_solver_child",
                    "The primitive context already has an active FGMRES child.",
                )
            self._fgmres_solver_child_epoch_value += 1
            snapshot = self._build_fgmres_solver_child_snapshot_locked()
            parent_capabilities = snapshot.parent_allocation_capabilities
            token = object()
            self._released_fgmres_solver_child_token = None
            self._fgmres_solver_child_parent_capability_snapshot = parent_capabilities
            self._fgmres_solver_child_owned_owner_snapshot = None
            self._fgmres_solver_child_owned_owner_identity_snapshot = None
            self._fgmres_solver_child_owned_owner_generation_snapshot = None
            self._fgmres_solver_child_group_capability_snapshot = None
            self._fgmres_solver_child_borrow_lease = None
            self._fgmres_solver_child_rollback_pending = False
            self._fgmres_solver_child_phase = "compatibility_active"
            self._fgmres_solver_child_snapshot_value = snapshot
            self._fgmres_solver_child_token = token
            return token

    def _reserve_fgmres_solver_child_for_source_apply(
        self,
        source_apply: HipFreeSpaceApplyReceipt,
        preissued_token: object,
        exact_owned_owner: HipAllocationOwnerV1,
    ) -> tuple[
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
    ]:
        """Reserve the canonical parent-three prefix for a future live owner.

        The live peer owner must already exist and remain the exact owner of
        every solver-owned capability through terminal cleanup.  No registry
        borrow occurs here.  The caller allocates its eight capabilities,
        forms ``parent_three + owned_eight``, and calls
        ``borrow_hip_allocations_v1`` outside this context's queue lock.
        """

        if type(preissued_token) is not object:
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                "/lifetime/fgmres_solver_child",
                "An exact built-in object token must be preissued by the live owner.",
            )
        owner_identity, owner_generation = (
            self._validate_fgmres_owned_owner_for_reservation(exact_owned_owner)
        )
        parent_capabilities: (
            tuple[
                HipAllocationCapabilityV1,
                HipAllocationCapabilityV1,
                HipAllocationCapabilityV1,
            ]
            | None
        ) = None
        reservation_epoch: int | None = None
        control_reserved = False
        try:
            with self._queue_lock:
                self._require_exact_fgmres_source_apply(source_apply)
                self._require_usable()
                self._require_fgmres_parent_authority_locked()
                self._validate_authority()
                if (
                    self._fgmres_solver_child_token is not None
                    or self._fgmres_solver_child_phase != "idle"
                    or self._fgmres_producer_resource_projection_value is not None
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_active",
                        "/lifetime/fgmres_solver_child",
                        "The primitive context already has an active FGMRES child.",
                    )
                parent_capabilities = (
                    self._fgmres_parent_allocation_capabilities_locked()
                )
                self._require_fgmres_owned_owner_separate_from_parent_locked(
                    exact_owned_owner,
                    owner_identity,
                    parent_capabilities,
                )
                try:
                    reserve_hip_allocation_owner_control_v1(
                        exact_owned_owner,
                        preissued_token,
                        expected_owner_role="fgmres_checkpoint_owned_buffers",
                        allowed_roles=_FGMRES_LIVE_OWNED_CAPABILITY_ROLES,
                    )
                except HipAllocationLineageError as exc:
                    raise HipKrylovPrimitivesContextError(
                        "hip_krylov_primitives_fgmres_owned_owner_invalid",
                        "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner/control",
                        _detail(exc),
                    ) from exc
                control_reserved = True
                reservation_epoch = self._fgmres_solver_child_epoch_value + 1
                self._fgmres_solver_child_epoch_value = reservation_epoch
                self._released_fgmres_solver_child_token = None
                self._fgmres_solver_child_parent_capability_snapshot = (
                    parent_capabilities
                )
                self._fgmres_solver_child_owned_owner_snapshot = exact_owned_owner
                self._fgmres_solver_child_owned_owner_identity_snapshot = owner_identity
                self._fgmres_solver_child_owned_owner_generation_snapshot = (
                    owner_generation
                )
                self._fgmres_solver_child_group_capability_snapshot = None
                self._fgmres_solver_child_borrow_lease = None
                self._fgmres_solver_child_rollback_pending = True
                self._fgmres_solver_child_phase = "semantic_reserved"
                # Publish the caller-preissued token before building the
                # semantic snapshot.  Every cleanup witness is now recoverable
                # even if snapshot construction or the return handoff is
                # interrupted.
                self._fgmres_solver_child_token = preissued_token
                self._fgmres_solver_child_snapshot_value = (
                    self._build_fgmres_solver_child_snapshot_locked(
                        parent_capabilities=parent_capabilities,
                        allocation_capabilities=None,
                        allocation_borrow_lease=None,
                        allocation_borrow_phase="semantic_reserved",
                    )
                )
                return parent_capabilities
        except BaseException:
            if not control_reserved:
                try:
                    validate_hip_allocation_owner_control_v1(
                        exact_owned_owner,
                        preissued_token,
                        expected_owner_role="fgmres_checkpoint_owned_buffers",
                        allowed_roles=_FGMRES_LIVE_OWNED_CAPABILITY_ROLES,
                    )
                except BaseException:
                    control_reserved = False
                else:
                    control_reserved = True
            with self._queue_lock:
                if control_reserved and parent_capabilities is not None:
                    if reservation_epoch is None:
                        reservation_epoch = self._fgmres_solver_child_epoch_value + 1
                    if self._fgmres_solver_child_phase == "idle":
                        if self._fgmres_solver_child_token is not None:
                            _fail(
                                "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                                "/lifetime/fgmres_solver_child",
                            )
                        self._fgmres_solver_child_epoch_value = reservation_epoch
                        self._released_fgmres_solver_child_token = None
                        self._fgmres_solver_child_parent_capability_snapshot = (
                            parent_capabilities
                        )
                        self._fgmres_solver_child_owned_owner_snapshot = (
                            exact_owned_owner
                        )
                        self._fgmres_solver_child_owned_owner_identity_snapshot = (
                            owner_identity
                        )
                        self._fgmres_solver_child_owned_owner_generation_snapshot = (
                            owner_generation
                        )
                        self._fgmres_solver_child_group_capability_snapshot = None
                        self._fgmres_solver_child_borrow_lease = None
                        self._fgmres_solver_child_snapshot_value = None
                    elif (
                        self._fgmres_solver_child_owned_owner_snapshot
                        is not exact_owned_owner
                        or self._fgmres_solver_child_owned_owner_identity_snapshot
                        != owner_identity
                    ):
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child",
                        )
                    if self._fgmres_solver_child_token is None:
                        self._fgmres_solver_child_token = preissued_token
                    self._fgmres_solver_child_phase = "rollback_pending"
                    self._fgmres_solver_child_rollback_pending = True
            if control_reserved and parent_capabilities is not None:
                try:
                    self._resume_fgmres_solver_child_terminal(preissued_token)
                except BaseException:
                    pass
            raise

    def _prepare_fgmres_solver_child_allocation_borrow(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
        capabilities: tuple[HipAllocationCapabilityV1, ...],
    ) -> tuple[HipAllocationCapabilityV1, ...]:
        """Publish exact11 before the caller performs its atomic group borrow."""

        cleanup_capabilities = capabilities if type(capabilities) is tuple else None
        owned_owner: HipAllocationOwnerV1 | None = None
        owned_owner_identity: tuple[int, str, str] | None = None
        owned_owner_generation: int | None = None
        try:
            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                owned_owner, owned_owner_identity, owned_owner_generation = (
                    self._require_fgmres_owned_owner_snapshot_locked()
                )
                if (
                    self._fgmres_solver_child_phase != "semantic_reserved"
                    or not self._fgmres_solver_child_rollback_pending
                    or self._fgmres_solver_child_group_capability_snapshot is not None
                    or self._fgmres_solver_child_borrow_lease is not None
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                self._require_exact_fgmres_live_capability_group_locked(
                    capabilities,
                    None,
                    token,
                )
                # This exact tuple and the preissued token are sufficient for
                # host-registry recovery if borrow returns but its lease STORE
                # never becomes visible to the external factory.
                self._fgmres_solver_child_group_capability_snapshot = capabilities

            prepared_owner_generation = self._validate_fgmres_live_capability_group(
                capabilities,
                owned_owner,
                owned_owner_identity,
                owned_owner_generation,
                token,
            )
            self._validate_fgmres_parent_allocation_capabilities(capabilities[:3])

            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                self._require_fgmres_owned_owner_snapshot_locked(
                    owned_owner,
                    owned_owner_identity,
                    owned_owner_generation,
                )
                if (
                    self._fgmres_solver_child_phase != "semantic_reserved"
                    or not self._fgmres_solver_child_rollback_pending
                    or self._fgmres_solver_child_group_capability_snapshot
                    is not capabilities
                    or self._fgmres_solver_child_borrow_lease is not None
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                self._fgmres_solver_child_owned_owner_generation_snapshot = (
                    prepared_owner_generation
                )
                return capabilities
        except BaseException:
            try:
                self._recover_fgmres_solver_child_allocation_borrow(
                    token,
                    cleanup_capabilities,
                )
            except BaseException:
                pass
            raise

    def _fgmres_reserved_solver_child_snapshot(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> _HipFgmresSolverChildSnapshot:
        """Return the exact semantic-reservation snapshot before group borrow."""

        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            if (
                self._fgmres_solver_child_phase != "semantic_reserved"
                or not self._fgmres_solver_child_rollback_pending
                or self._fgmres_solver_child_group_capability_snapshot is not None
                or self._fgmres_solver_child_borrow_lease is not None
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child",
                )
            self._require_usable()
            self._validate_authority()
            self._validate_fgmres_solver_child_snapshot_locked()
            self._require_fgmres_parent_authority_locked()
            snapshot = self._fgmres_solver_child_snapshot_value
            if snapshot is None:  # pragma: no cover - structural guard
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_snapshot_missing",
                    "/lifetime/fgmres_solver_child/snapshot",
                )
            return snapshot

    def _commit_fgmres_solver_child_allocation_borrow(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
        capabilities: tuple[HipAllocationCapabilityV1, ...],
        lease: HipAllocationBorrowLeaseV1,
    ) -> object:
        """Bind one already-acquired exact-11 allocation lease to the child."""

        cleanup_capabilities: tuple[HipAllocationCapabilityV1, ...] | None = (
            capabilities if type(capabilities) is tuple else None
        )
        cleanup_lease: HipAllocationBorrowLeaseV1 | None = (
            lease if type(lease) is HipAllocationBorrowLeaseV1 else None
        )
        if cleanup_lease is not None:
            lease_capabilities = cleanup_lease.capabilities
            if type(lease_capabilities) is tuple:
                cleanup_capabilities = lease_capabilities
        owned_owner: HipAllocationOwnerV1 | None = None
        owned_owner_identity: tuple[int, str, str] | None = None
        owned_owner_generation: int | None = None
        try:
            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                owned_owner, owned_owner_identity, owned_owner_generation = (
                    self._require_fgmres_owned_owner_snapshot_locked()
                )
                if (
                    self._fgmres_solver_child_phase != "semantic_reserved"
                    or not self._fgmres_solver_child_rollback_pending
                    or self._fgmres_solver_child_borrow_lease is not None
                    or self._fgmres_solver_child_group_capability_snapshot
                    is not capabilities
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                self._require_exact_fgmres_live_capability_group_locked(
                    capabilities,
                    lease,
                    token,
                )
                # Publish both recovery witnesses before any fallible registry
                # validation.  The exact tuple was already published before
                # the caller's external registry borrow; only its lease needs
                # to cross this final STORE boundary.
                self._fgmres_solver_child_borrow_lease = lease

            # Runtime-owner validation may call into HIP.  It must never run
            # while the primitive queue lock is held.
            self._validate_fgmres_live_allocation_borrow(lease)
            committed_owner_generation = self._validate_fgmres_live_capability_group(
                capabilities,
                owned_owner,
                owned_owner_identity,
                owned_owner_generation,
                token,
            )
            if committed_owner_generation != owned_owner_generation:
                _fail(
                    "hip_krylov_primitives_fgmres_owned_owner_invalid",
                    "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                    "The controlled owned8 generation changed after prepare.",
                )
            self._validate_fgmres_parent_allocation_capabilities(capabilities[:3])

            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                self._require_fgmres_owned_owner_snapshot_locked(
                    owned_owner,
                    owned_owner_identity,
                    owned_owner_generation,
                )
                if (
                    self._fgmres_solver_child_phase != "semantic_reserved"
                    or not self._fgmres_solver_child_rollback_pending
                    or self._fgmres_solver_child_group_capability_snapshot
                    is not capabilities
                    or self._fgmres_solver_child_borrow_lease is not lease
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                parent_capabilities = (
                    self._fgmres_solver_child_parent_capability_snapshot
                )
                if parent_capabilities is None:  # pragma: no cover - invariant
                    _fail(
                        "hip_krylov_primitives_fgmres_parent_capability_invalid",
                        "/lifetime/fgmres_solver_child/allocation_lineage/parent",
                    )
                snapshot = self._build_fgmres_solver_child_snapshot_locked(
                    parent_capabilities=parent_capabilities,
                    allocation_capabilities=capabilities,
                    allocation_borrow_lease=lease,
                    allocation_borrow_phase="active",
                )
                self._fgmres_solver_child_snapshot_value = snapshot
                self._fgmres_solver_child_phase = "active"
                # Final commit marker.  Every cleanup witness was published
                # before this assignment.
                self._fgmres_solver_child_rollback_pending = False
                return token
        except BaseException:
            try:
                self._recover_fgmres_solver_child_allocation_borrow(
                    token,
                    cleanup_capabilities,
                    cleanup_lease,
                )
            except BaseException:
                pass
            raise

    def _recover_fgmres_solver_child_allocation_borrow(
        self,
        token: object,
        capabilities: tuple[HipAllocationCapabilityV1, ...] | None = None,
        lease: HipAllocationBorrowLeaseV1 | None = None,
    ) -> None:
        """Recover and roll back an interrupted live-child allocation handoff."""

        try:
            finish_semantic = False
            with self._queue_lock:
                if token is self._released_fgmres_solver_child_token:
                    if self._fgmres_solver_child_token is None:
                        if self._fgmres_solver_child_phase != "idle":
                            _fail(
                                "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                                "/lifetime/fgmres_solver_child",
                            )
                        self._finish_fgmres_solver_child_terminal_locked(token)
                        return
                    if self._fgmres_solver_child_token is not token:
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                            "/lifetime/fgmres_solver_child",
                        )
                elif token is not self._fgmres_solver_child_token:
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                        "/lifetime/fgmres_solver_child",
                    )
                self._require_fgmres_owned_owner_snapshot_locked()
                if self._fgmres_solver_child_phase == "semantic_cleanup_active":
                    if capabilities is not None or lease is not None:
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child/allocation_lineage",
                        )
                    finish_semantic = True
                if capabilities is not None and type(capabilities) is not tuple:
                    _fail(
                        "hip_krylov_primitives_fgmres_allocation_group_invalid",
                        "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
                    )
                if lease is not None and type(lease) is not HipAllocationBorrowLeaseV1:
                    _fail(
                        "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                        "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                    )
                if not finish_semantic and lease is not None:
                    lease_capabilities = lease.capabilities
                    if type(lease_capabilities) is not tuple:
                        _fail(
                            "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                            "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                        )
                    if capabilities is None:
                        capabilities = lease_capabilities
                    elif capabilities is not lease_capabilities:
                        _fail(
                            "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                            "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                        )
                if not finish_semantic:
                    current_capabilities = (
                        self._fgmres_solver_child_group_capability_snapshot
                    )
                    if current_capabilities is None:
                        self._fgmres_solver_child_group_capability_snapshot = (
                            capabilities
                        )
                    elif (
                        capabilities is not None
                        and current_capabilities is not capabilities
                    ):
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child/allocation_lineage",
                        )
                    current_lease = self._fgmres_solver_child_borrow_lease
                    if current_lease is None:
                        self._fgmres_solver_child_borrow_lease = lease
                    elif lease is not None and current_lease is not lease:
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child/allocation_lineage",
                        )
                    self._fgmres_solver_child_phase = "rollback_pending"
                    self._fgmres_solver_child_rollback_pending = True
            if finish_semantic:
                self._release_fgmres_solver_child(
                    token,
                    self._source_apply_snapshot,
                )
                return
            self._resume_fgmres_solver_child_terminal(token)
        except BaseException:
            try:
                self._resume_fgmres_solver_child_terminal(token)
            except BaseException:
                pass
            raise

    def _require_fgmres_solver_child(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> None:
        """Require one exact live FGMRES capability and its source apply."""

        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_active_fgmres_solver_child_locked()
            self._require_usable()
            self._validate_authority()
            self._validate_fgmres_solver_child_snapshot_locked()
            self._require_fgmres_parent_authority_locked()
            phase = self._fgmres_solver_child_phase
            lease = self._fgmres_solver_child_borrow_lease
        if phase == "active":
            if lease is None:  # pragma: no cover - structural guard above
                _fail(
                    "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                    "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                )
            self._validate_fgmres_live_allocation_borrow(lease)
            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                self._require_active_fgmres_solver_child_locked()
                self._validate_fgmres_solver_child_snapshot_locked()

    def _fgmres_solver_child_snapshot(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> _HipFgmresSolverChildSnapshot:
        """Return the immutable process-local lineage/pointer snapshot."""

        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_active_fgmres_solver_child_locked()
            self._require_usable()
            self._validate_authority()
            self._validate_fgmres_solver_child_snapshot_locked()
            self._require_fgmres_parent_authority_locked()
            snapshot = self._fgmres_solver_child_snapshot_value
            if snapshot is None:  # pragma: no cover - guarded invariant
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_snapshot_missing",
                    "/lifetime/fgmres_solver_child/snapshot",
                )
            phase = self._fgmres_solver_child_phase
            lease = self._fgmres_solver_child_borrow_lease
        if phase == "active":
            if lease is None:  # pragma: no cover - structural guard above
                _fail(
                    "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                    "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                )
            self._validate_fgmres_live_allocation_borrow(lease)
            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                self._require_active_fgmres_solver_child_locked()
                self._validate_fgmres_solver_child_snapshot_locked()
                snapshot = self._fgmres_solver_child_snapshot_value
                if snapshot is None:  # pragma: no cover - guarded invariant
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_snapshot_missing",
                        "/lifetime/fgmres_solver_child/snapshot",
                    )
        return snapshot

    def _issue_fgmres_producer_resource_projection(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> _HipFgmresProducerResourceProjection:
        """Issue the exact non-owning CSR3 + reduction2 producer projection.

        Issuance is possible only after the canonical exact-11 solver borrow is
        active.  It performs no allocation and creates no registry borrow; the
        returned object's authority is the already-live parent and solver
        semantic chain.
        """

        self._fgmres_solver_child_snapshot(token, source_apply)
        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_exact_fgmres_producer_phase_locked()
            self._validate_fgmres_solver_child_snapshot_locked()
            projection = self._fgmres_producer_resource_projection_value
            if projection is None:
                projection = self._build_fgmres_producer_resource_projection_locked()
                self._fgmres_producer_resource_projection_value = projection
            else:
                self._validate_fgmres_producer_resource_projection_locked(projection)
            return projection

    def _validate_fgmres_producer_resource_projection(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
        projection: _HipFgmresProducerResourceProjection,
    ) -> _HipFgmresProducerResourceProjection:
        """Revalidate one exact issued producer projection before device use."""

        self._fgmres_solver_child_snapshot(token, source_apply)
        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_exact_fgmres_producer_phase_locked()
            current = self._fgmres_producer_resource_projection_value
            if (
                type(projection) is not _HipFgmresProducerResourceProjection
                or projection is not current
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_producer_projection_invalid",
                    "/lifetime/fgmres_solver_child/producer_resources",
                    "The projection is stale, foreign, or was not issued here.",
                )
            self._validate_fgmres_solver_child_snapshot_locked()
            self._validate_fgmres_producer_resource_projection_locked(projection)
            return projection

    def _poison_fgmres_solver_child(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
        detail: str,
    ) -> None:
        """Share an FGMRES queue failure through every live owner."""

        with self._queue_lock:
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_active_fgmres_solver_child_locked()
            self._poison(detail)

    def _release_fgmres_solver_child(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> None:
        """Release compatibility directly or live semantics strictly last."""

        with self._queue_lock:
            if token is self._released_fgmres_solver_child_token:
                if self._fgmres_solver_child_token is None:
                    if self._fgmres_solver_child_phase != "idle":
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child",
                        )
                    self._finish_fgmres_solver_child_terminal_locked(token)
                    return
                if self._fgmres_solver_child_token is not token:
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                        "/lifetime/fgmres_solver_child",
                    )
            self._require_fgmres_solver_child_identity(token, source_apply)
            phase = self._fgmres_solver_child_phase
            if phase == "compatibility_active":
                if (
                    self._fgmres_solver_child_owned_owner_snapshot is not None
                    or self._fgmres_solver_child_owned_owner_identity_snapshot
                    is not None
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child",
                    )
                self._released_fgmres_solver_child_token = token
                self._finish_fgmres_solver_child_terminal_locked(token)
                return
            if phase != "semantic_cleanup_active":
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_split_release_required",
                    "/lifetime/fgmres_solver_child/allocation_lineage",
                    "Release the exact11 group before retiring owned8 and semantics.",
                )
            if (
                self._fgmres_solver_child_borrow_lease is not None
                or self._fgmres_solver_child_group_capability_snapshot is not None
                or self._fgmres_solver_child_rollback_pending
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child/allocation_lineage",
                )
            owned_owner, owned_owner_identity, owned_owner_generation = (
                self._require_fgmres_owned_owner_snapshot_locked()
            )

        # Owner.closed is the allocation registry's monotonic terminal witness.
        # A live-owner validator intentionally rejects this state, so final
        # semantics must inspect the exact retained owner directly and outside
        # the queue lock.
        try:
            owner_closed = owned_owner.closed
        except HipAllocationLineageError as exc:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                _detail(exc),
            ) from exc
        if owner_closed is not True:
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_open",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                "Close the exact solver-owned allocation owner before semantics.",
            )

        with self._queue_lock:
            if (
                self._fgmres_solver_child_token is None
                and token is self._released_fgmres_solver_child_token
                and self._fgmres_solver_child_phase == "idle"
            ):
                return
            self._require_fgmres_solver_child_identity(token, source_apply)
            self._require_fgmres_owned_owner_snapshot_locked(
                owned_owner,
                owned_owner_identity,
                owned_owner_generation,
            )
            if (
                self._fgmres_solver_child_phase != "semantic_cleanup_active"
                or self._fgmres_solver_child_borrow_lease is not None
                or self._fgmres_solver_child_group_capability_snapshot is not None
                or self._fgmres_solver_child_rollback_pending
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child/allocation_lineage",
                )
            self._released_fgmres_solver_child_token = token
            self._finish_fgmres_solver_child_terminal_locked(token)

    def _release_fgmres_solver_child_allocation_borrow(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> None:
        """Release exact11 while retaining the semantic parent cleanup lease.

        This split terminal is used only by the allocator-backed live owner.
        The child must call it before freeing its owned eight allocations, then
        call :meth:`_release_fgmres_solver_child` only after its peer owner has
        closed.  The registry release is idempotent; the local phase marker is
        published before cleanup fields are cleared so an interruption never
        repeats a non-idempotent operation or loses the parent-three snapshot.
        """

        lease: HipAllocationBorrowLeaseV1 | None = None
        capabilities: tuple[HipAllocationCapabilityV1, ...] | None = None
        owned_owner: HipAllocationOwnerV1 | None = None
        owned_owner_identity: tuple[int, str, str] | None = None
        owned_owner_generation: int | None = None
        try:
            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                owned_owner, owned_owner_identity, owned_owner_generation = (
                    self._require_fgmres_owned_owner_snapshot_locked()
                )
                phase = self._fgmres_solver_child_phase
                if phase == "semantic_cleanup_active":
                    self._finish_fgmres_solver_child_group_release_local_locked(token)
                    return
                if phase not in {"active", "allocation_release_pending"}:
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                lease = self._fgmres_solver_child_borrow_lease
                capabilities = self._fgmres_solver_child_group_capability_snapshot
                if (
                    lease is None
                    or capabilities is None
                    or lease.capabilities is not capabilities
                    or lease.borrower is not token
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                        "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                    )
                # Persist the intent before leaving the queue lock.  A retry
                # calls the registry's idempotent terminal release on the same
                # exact lease and capabilities.
                self._fgmres_solver_child_phase = "allocation_release_pending"
                self._fgmres_solver_child_rollback_pending = False

            release_hip_allocation_borrow_v1(lease)

            with self._queue_lock:
                self._require_fgmres_solver_child_identity(token, source_apply)
                self._require_fgmres_owned_owner_snapshot_locked(
                    owned_owner,
                    owned_owner_identity,
                    owned_owner_generation,
                )
                if self._fgmres_solver_child_phase == "semantic_cleanup_active":
                    self._finish_fgmres_solver_child_group_release_local_locked(token)
                    return
                if (
                    self._fgmres_solver_child_phase != "allocation_release_pending"
                    or self._fgmres_solver_child_borrow_lease is not lease
                    or self._fgmres_solver_child_group_capability_snapshot
                    is not capabilities
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                        "/lifetime/fgmres_solver_child/allocation_lineage",
                    )
                # Terminal marker first.  Field clearing and snapshot projection
                # below are local/idempotent and can be resumed without another
                # external registry transition.
                self._fgmres_solver_child_phase = "semantic_cleanup_active"
                self._finish_fgmres_solver_child_group_release_local_locked(token)
        except BaseException:
            # If release completed before an asynchronous interruption, the
            # idempotent call converges the exact lease and then finishes local
            # projection.  If it did not complete, the same lease remains the
            # sole cleanup authority.
            if lease is not None and capabilities is not None:
                try:
                    release_hip_allocation_borrow_v1(lease)
                    with self._queue_lock:
                        self._require_fgmres_solver_child_identity(token, source_apply)
                        self._require_fgmres_owned_owner_snapshot_locked(
                            owned_owner,
                            owned_owner_identity,
                            owned_owner_generation,
                        )
                        if self._fgmres_solver_child_phase in {
                            "active",
                            "allocation_release_pending",
                        }:
                            self._fgmres_solver_child_phase = "semantic_cleanup_active"
                        if self._fgmres_solver_child_phase == "semantic_cleanup_active":
                            self._finish_fgmres_solver_child_group_release_local_locked(
                                token
                            )
                except BaseException:
                    pass
            raise

    def _finish_fgmres_solver_child_group_release_local_locked(
        self,
        token: object,
    ) -> None:
        if (
            token is not self._fgmres_solver_child_token
            or self._fgmres_solver_child_phase != "semantic_cleanup_active"
        ):
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                "/lifetime/fgmres_solver_child/allocation_lineage",
            )
        parent_capabilities = self._fgmres_solver_child_parent_capability_snapshot
        self._require_fgmres_owned_owner_snapshot_locked()
        if parent_capabilities is None:
            _fail(
                "hip_krylov_primitives_fgmres_parent_capability_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/parent",
            )
        self._fgmres_solver_child_borrow_lease = None
        self._fgmres_solver_child_group_capability_snapshot = None
        self._fgmres_solver_child_rollback_pending = False
        self._fgmres_solver_child_snapshot_value = (
            self._build_fgmres_solver_child_snapshot_locked(
                parent_capabilities=parent_capabilities,
                allocation_capabilities=None,
                allocation_borrow_lease=None,
                allocation_borrow_phase="semantic_cleanup_active",
            )
        )

    def _require_exact_fgmres_source_apply(
        self, source_apply: HipFreeSpaceApplyReceipt
    ) -> None:
        if (
            type(source_apply) is not HipFreeSpaceApplyReceipt
            or source_apply is not self._source_apply_snapshot
            or source_apply is not self._source_apply
            or source_apply.status != "enqueued"
            or source_apply.receipt_hash != self._source_apply_hash_snapshot
            or source_apply.sequence != self._source_apply_sequence_snapshot
            or source_apply.direction_generation
            != self._source_direction_generation_snapshot
            or source_apply.direction_generation is None
            or source_apply is not self._parent._last_apply
            or self._parent._apply_witnesses.get(source_apply.sequence)
            != (source_apply.direction_generation, source_apply.receipt_hash)
        ):
            _fail(
                "hip_krylov_primitives_fgmres_source_apply_invalid",
                "/lifetime/fgmres_solver_child/source_apply",
                "FGMRES must bind the exact source apply owned by this primitive context.",
            )

    def _require_fgmres_solver_child_identity(
        self,
        token: object,
        source_apply: HipFreeSpaceApplyReceipt,
    ) -> None:
        if token is not self._fgmres_solver_child_token:
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                "/lifetime/fgmres_solver_child",
                "The FGMRES child token is stale or foreign.",
            )
        if source_apply is not self._source_apply_snapshot:
            _fail(
                "hip_krylov_primitives_fgmres_source_apply_invalid",
                "/lifetime/fgmres_solver_child/source_apply",
                "The source apply object is stale or foreign.",
            )
        if (
            type(source_apply.sequence) is not int
            or source_apply.sequence != self._source_apply_sequence_snapshot
            or type(source_apply.direction_generation) is not int
            or source_apply.direction_generation
            != self._source_direction_generation_snapshot
            or type(source_apply.receipt_hash) is not str
            or source_apply.receipt_hash != self._source_apply_hash_snapshot
        ):
            _fail(
                "hip_krylov_primitives_fgmres_source_apply_invalid",
                "/lifetime/fgmres_solver_child/source_apply",
                "The source apply lineage changed while the child lease was live.",
            )

    def _require_fgmres_parent_authority_locked(self) -> None:
        try:
            self._parent._require_krylov_consumer(self._lease_token)
        except Exception as exc:
            self._poison("hip_krylov_primitives_fgmres_parent_authority_invalid")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_parent_authority_invalid",
                "/lifetime/fgmres_solver_child/parent",
                _detail(exc),
            ) from exc

    def _fgmres_parent_allocation_capabilities_locked(
        self,
    ) -> tuple[
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
        HipAllocationCapabilityV1,
    ]:
        try:
            capabilities = (
                self._parent._owned_capabilities["reduced_state"],
                self._parent._owned_capabilities["reduced_load"],
                self._owned_capabilities["jacobi_inverse"],
            )
            free_owner = self._parent._allocation_owner
            primitive_owner = self._allocation_owner
            expected_owners = (free_owner, free_owner, primitive_owner)
            device = self._parent._resident._device_ordinal_snapshot
            runtime_domain = capabilities[0].runtime_domain
            runtime_domain_id = capabilities[0].runtime_domain_id
            if free_owner is None or primitive_owner is None:
                raise ValueError("allocation owner missing")
            for index, (capability, role, owner) in enumerate(
                zip(
                    capabilities,
                    _FGMRES_PARENT_CAPABILITY_ROLES,
                    expected_owners,
                    strict=True,
                )
            ):
                if (
                    type(capability) is not HipAllocationCapabilityV1
                    or capability.role != role
                    or capability.owner_identity != owner.owner_id
                    or capability.runtime_owner is not self._runtime
                    or capability.runtime_domain is not runtime_domain
                    or capability.runtime_domain_id != runtime_domain_id
                    or capability.device_ordinal != device
                    or type(capability.generation) is not int
                    or capability.generation <= 0
                    or capability.base
                    is not (
                        self._parent._pointers[role]
                        if index < 2
                        else self._pointers[role]
                    )
                ):
                    raise ValueError(f"invalid canonical parent capability {role}")
            if (
                type(runtime_domain_id) is not str
                or not runtime_domain_id
                or type(device) is not int
                or device < 0
            ):
                raise ValueError("invalid allocation runtime binding")
            return capabilities
        except Exception as exc:
            self._poison("hip_krylov_primitives_fgmres_parent_capability_invalid")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_parent_capability_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/parent",
                _detail(exc),
            ) from exc

    def _validate_fgmres_parent_allocation_capabilities(
        self,
        capabilities: tuple[HipAllocationCapabilityV1, ...],
    ) -> None:
        with self._queue_lock:
            canonical = self._fgmres_parent_allocation_capabilities_locked()
            free_owner = self._parent._allocation_owner
            primitive_owner = self._allocation_owner
        if (
            type(capabilities) is not tuple
            or len(capabilities) != 3
            or any(
                actual is not expected
                for actual, expected in zip(capabilities, canonical, strict=True)
            )
            or free_owner is None
            or primitive_owner is None
        ):
            _fail(
                "hip_krylov_primitives_fgmres_parent_capability_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/parent",
            )
        try:
            validate_hip_allocation_capability_v1(
                capabilities[0], expected_owner=free_owner
            )
            validate_hip_allocation_capability_v1(
                capabilities[1], expected_owner=free_owner
            )
            validate_hip_allocation_capability_v1(
                capabilities[2], expected_owner=primitive_owner
            )
        except HipAllocationLineageError as exc:
            self._poison("hip_krylov_primitives_fgmres_parent_capability_invalid")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_parent_capability_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/parent",
                _detail(exc),
            ) from exc

    def _validate_fgmres_owned_owner_for_reservation(
        self,
        owner: HipAllocationOwnerV1,
    ) -> tuple[tuple[int, str, str], int]:
        """Preflight one fresh peer; registry control is the linearization."""

        identity, generation = self._validate_fgmres_owned_owner_identity(owner)
        try:
            capabilities, pending_frees, pending_orphans = (
                snapshot_hip_allocation_owner_cleanup_v1(owner)
            )
        except HipAllocationLineageError as exc:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                _detail(exc),
            ) from exc
        free_owner = self._parent._allocation_owner
        primitive_owner = self._allocation_owner
        if (
            type(free_owner) is not HipAllocationOwnerV1
            or type(primitive_owner) is not HipAllocationOwnerV1
        ):
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                "The canonical parent allocation owners are unavailable.",
            )
        try:
            free_owner_id = free_owner.owner_id
            primitive_owner_id = primitive_owner.owner_id
            primitive_domain_id = primitive_owner.runtime_domain_id
        except HipAllocationLineageError as exc:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                _detail(exc),
            ) from exc
        if (
            identity[0] in {free_owner_id, primitive_owner_id}
            or identity[1] != primitive_domain_id
            or identity[2] != "fgmres_checkpoint_owned_buffers"
            or generation != 0
            or capabilities
            or pending_frees
            or pending_orphans
        ):
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                "The live owner must be a distinct peer in the parent runtime domain.",
            )
        return identity, generation

    def _validate_fgmres_owned_owner_identity(
        self,
        owner: HipAllocationOwnerV1,
        expected_identity: tuple[int, str, str] | None = None,
        expected_generation: int | None = None,
        *,
        exact_generation: bool = False,
    ) -> tuple[tuple[int, str, str], int]:
        """Validate one exact *live* owner without holding the queue lock."""

        if type(owner) is not HipAllocationOwnerV1:
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                "An exact HipAllocationOwnerV1 is required.",
            )
        try:
            validate_hip_allocation_owner_v1(owner)
            identity = (
                owner.owner_id,
                owner.runtime_domain_id,
                owner.owner_role,
            )
            generation = owner.generation
        except HipAllocationLineageError as exc:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                _detail(exc),
            ) from exc
        if (
            type(identity[0]) is not int
            or identity[0] <= 0
            or type(identity[1]) is not str
            or not identity[1]
            or type(identity[2]) is not str
            or not identity[2]
            or type(generation) is not int
            or generation < 0
            or (expected_identity is not None and identity != expected_identity)
            or (
                expected_generation is not None
                and (
                    generation < expected_generation
                    or (exact_generation and generation != expected_generation)
                )
            )
        ):
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
                "The live owner identity changed.",
            )
        return identity, generation

    def _require_fgmres_owned_owner_separate_from_parent_locked(
        self,
        owner: HipAllocationOwnerV1,
        identity: tuple[int, str, str],
        parent_capabilities: tuple[
            HipAllocationCapabilityV1,
            HipAllocationCapabilityV1,
            HipAllocationCapabilityV1,
        ],
    ) -> None:
        del owner  # Exact type/live validation occurred before queue acquisition.
        parent_owner_ids = {
            capability.owner_identity for capability in parent_capabilities
        }
        if (
            len(parent_owner_ids) != 2
            or identity[0] in parent_owner_ids
            or identity[1] != parent_capabilities[0].runtime_domain_id
        ):
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
            )

    def _require_fgmres_owned_owner_snapshot_locked(
        self,
        expected_owner: HipAllocationOwnerV1 | None = None,
        expected_identity: tuple[int, str, str] | None = None,
        expected_generation: int | None = None,
    ) -> tuple[HipAllocationOwnerV1, tuple[int, str, str], int]:
        owner = self._fgmres_solver_child_owned_owner_snapshot
        identity = self._fgmres_solver_child_owned_owner_identity_snapshot
        generation = self._fgmres_solver_child_owned_owner_generation_snapshot
        if (
            type(owner) is not HipAllocationOwnerV1
            or type(identity) is not tuple
            or len(identity) != 3
            or type(generation) is not int
            or generation < 0
            or (expected_owner is not None and owner is not expected_owner)
            or (expected_identity is not None and identity != expected_identity)
            or (expected_generation is not None and generation != expected_generation)
        ):
            _fail(
                "hip_krylov_primitives_fgmres_owned_owner_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/owned_owner",
            )
        return owner, identity, generation

    def _require_exact_fgmres_live_capability_group_locked(
        self,
        capabilities: object,
        lease: object | None,
        token: object,
    ) -> None:
        parent_capabilities = self._fgmres_solver_child_parent_capability_snapshot
        if (
            type(capabilities) is not tuple
            or len(capabilities) != _FGMRES_LIVE_CAPABILITY_COUNT
            or any(
                type(capability) is not HipAllocationCapabilityV1
                for capability in capabilities
            )
            or len({id(capability) for capability in capabilities})
            != _FGMRES_LIVE_CAPABILITY_COUNT
            or parent_capabilities is None
            or any(
                capabilities[index] is not parent_capabilities[index]
                for index in range(3)
            )
        ):
            _fail(
                "hip_krylov_primitives_fgmres_allocation_group_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
                "The live child requires canonical parent3 followed by exact owned8.",
            )
        owned_capabilities = capabilities[3:]
        _owned_owner, owned_owner_identity, _owned_owner_generation = (
            self._require_fgmres_owned_owner_snapshot_locked()
        )
        parent_owner_identities = {
            capability.owner_identity for capability in parent_capabilities
        }
        owned_owner_identities = {
            capability.owner_identity for capability in owned_capabilities
        }
        generations = tuple(capability.generation for capability in capabilities)
        if (
            tuple(capability.role for capability in owned_capabilities)
            != _FGMRES_LIVE_OWNED_CAPABILITY_ROLES
            or len(parent_owner_identities) != 2
            or len(owned_owner_identities) != 1
            or not parent_owner_identities.isdisjoint(owned_owner_identities)
            or owned_owner_identities != {owned_owner_identity[0]}
            or len(set(generations)) != _FGMRES_LIVE_CAPABILITY_COUNT
            or any(
                previous >= current
                for previous, current in zip(
                    generations,
                    generations[1:],
                    strict=False,
                )
            )
        ):
            _fail(
                "hip_krylov_primitives_fgmres_allocation_group_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
                "The owned8 roles, allocation order, or peer-owner lineage changed.",
            )
        # Byte extents are plan-dependent and are revalidated by the live
        # context.  Exact owner identity is a primitive-layer lifetime
        # invariant and may not be delegated to that layer.
        if lease is not None and (
            type(lease) is not HipAllocationBorrowLeaseV1
            or lease.capabilities is not capabilities
            or lease.borrower is not token
        ):
            _fail(
                "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/lease",
            )
        runtime_domain = parent_capabilities[0].runtime_domain
        runtime_domain_id = parent_capabilities[0].runtime_domain_id
        device = parent_capabilities[0].device_ordinal
        if (
            lease is not None
            and (
                lease.runtime_domain is not runtime_domain
                or lease.device_ordinal != device
            )
        ) or any(
            capability.runtime_domain is not runtime_domain
            or capability.runtime_domain_id != runtime_domain_id
            or capability.device_ordinal != device
            or capability.runtime_owner is not self._runtime
            or type(capability.generation) is not int
            or capability.generation <= 0
            for capability in capabilities
        ):
            _fail(
                "hip_krylov_primitives_fgmres_allocation_domain_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
            )

    def _validate_fgmres_live_allocation_borrow(
        self,
        lease: HipAllocationBorrowLeaseV1,
    ) -> None:
        try:
            validate_hip_allocation_borrow_v1(lease)
        except HipAllocationLineageError as exc:
            self._poison("hip_krylov_primitives_fgmres_allocation_borrow_invalid")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/lease",
                _detail(exc),
            ) from exc

    def _validate_fgmres_live_capability_group(
        self,
        capabilities: tuple[HipAllocationCapabilityV1, ...],
        owned_owner: HipAllocationOwnerV1,
        owned_owner_identity: tuple[int, str, str],
        owned_owner_generation: int,
        controller: object,
    ) -> int:
        try:
            validate_hip_allocation_owner_control_v1(
                owned_owner,
                controller,
                expected_owner_role="fgmres_checkpoint_owned_buffers",
                allowed_roles=_FGMRES_LIVE_OWNED_CAPABILITY_ROLES,
                expected_allocation_publication_count=8,
            )
            _, current_generation = self._validate_fgmres_owned_owner_identity(
                owned_owner,
                owned_owner_identity,
                owned_owner_generation,
            )
            owner_capabilities, pending_frees, pending_orphans = (
                snapshot_hip_allocation_owner_cleanup_v1(owned_owner)
            )
            for capability in capabilities[:3]:
                validate_hip_allocation_capability_v1(capability)
            for capability in capabilities[3:]:
                validate_hip_allocation_capability_v1(
                    capability,
                    expected_owner=owned_owner,
                )
        except HipAllocationLineageError as exc:
            self._poison("hip_krylov_primitives_fgmres_allocation_group_invalid")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_fgmres_allocation_group_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
                _detail(exc),
            ) from exc
        expected_owned = capabilities[3:]
        if (
            current_generation != capabilities[-1].generation
            or len(owner_capabilities) != len(expected_owned)
            or any(
                actual is not expected
                for actual, expected in zip(
                    owner_capabilities,
                    expected_owned,
                    strict=True,
                )
            )
            or pending_frees
            or pending_orphans
        ):
            _fail(
                "hip_krylov_primitives_fgmres_allocation_group_invalid",
                "/lifetime/fgmres_solver_child/allocation_lineage/capabilities",
                "The controlled owner cleanup snapshot is not exact owned8.",
            )
        return current_generation

    def _require_active_fgmres_solver_child_locked(self) -> None:
        phase = self._fgmres_solver_child_phase
        if phase == "compatibility_active":
            if (
                self._fgmres_solver_child_rollback_pending
                or self._fgmres_solver_child_borrow_lease is not None
                or self._fgmres_solver_child_group_capability_snapshot is not None
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child",
                )
            return
        if phase == "active":
            self._require_fgmres_owned_owner_snapshot_locked()
            lease = self._fgmres_solver_child_borrow_lease
            capabilities = self._fgmres_solver_child_group_capability_snapshot
            if (
                self._fgmres_solver_child_rollback_pending
                or lease is None
                or capabilities is None
                or lease.capabilities is not capabilities
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_allocation_borrow_invalid",
                    "/lifetime/fgmres_solver_child/allocation_lineage",
                )
            return
        _fail(
            "hip_krylov_primitives_fgmres_solver_child_not_active",
            "/lifetime/fgmres_solver_child",
        )

    def _resume_fgmres_solver_child_terminal(
        self,
        expected_token: object | None = None,
    ) -> None:
        finish_semantic = False
        with self._queue_lock:
            token = self._fgmres_solver_child_token
            if token is None:
                if expected_token is not None and (
                    expected_token is not self._released_fgmres_solver_child_token
                ):
                    _fail(
                        "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                        "/lifetime/fgmres_solver_child",
                    )
                if (
                    expected_token is self._released_fgmres_solver_child_token
                    and self._fgmres_solver_child_phase == "idle"
                ):
                    self._finish_fgmres_solver_child_terminal_locked(expected_token)
                return
            if expected_token is not None and token is not expected_token:
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_token_invalid",
                    "/lifetime/fgmres_solver_child",
                )
            if token is self._released_fgmres_solver_child_token:
                if self._fgmres_solver_child_owned_owner_snapshot is None:
                    self._finish_fgmres_solver_child_terminal_locked(token)
                    return
                finish_semantic = True
            phase = self._fgmres_solver_child_phase
            if phase == "semantic_cleanup_active":
                finish_semantic = True
            if finish_semantic:
                capabilities = None
                lease = None
            elif phase not in {
                "release_pending",
                "rollback_pending",
                "allocation_release_pending",
            }:
                return
            else:
                self._require_fgmres_owned_owner_snapshot_locked()
                capabilities = self._fgmres_solver_child_group_capability_snapshot
                lease = self._fgmres_solver_child_borrow_lease

        if finish_semantic:
            self._release_fgmres_solver_child(
                token,
                self._source_apply_snapshot,
            )
            return

        if lease is None and capabilities is not None:
            lease = recover_hip_allocation_borrow_v1(capabilities, token)
            if lease is not None:
                with self._queue_lock:
                    if (
                        self._fgmres_solver_child_token is not token
                        or self._fgmres_solver_child_phase
                        not in {
                            "release_pending",
                            "rollback_pending",
                            "allocation_release_pending",
                        }
                        or self._fgmres_solver_child_group_capability_snapshot
                        is not capabilities
                    ):
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child/allocation_lineage",
                        )
                    current = self._fgmres_solver_child_borrow_lease
                    if current is None:
                        self._fgmres_solver_child_borrow_lease = lease
                    elif current is not lease:
                        _fail(
                            "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                            "/lifetime/fgmres_solver_child/allocation_lineage",
                        )
        if lease is not None:
            release_hip_allocation_borrow_v1(lease)

        with self._queue_lock:
            if (
                self._fgmres_solver_child_token is None
                and token is self._released_fgmres_solver_child_token
                and self._fgmres_solver_child_phase == "idle"
            ):
                return
            if self._fgmres_solver_child_token is not token:
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child",
                )
            if self._fgmres_solver_child_phase == "semantic_cleanup_active":
                self._finish_fgmres_solver_child_group_release_local_locked(token)
                return
            if self._fgmres_solver_child_phase not in {
                "release_pending",
                "rollback_pending",
                "allocation_release_pending",
            }:
                _fail(
                    "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                    "/lifetime/fgmres_solver_child/allocation_lineage",
                )
            self._fgmres_solver_child_phase = "semantic_cleanup_active"
            self._finish_fgmres_solver_child_group_release_local_locked(token)

    def _finish_fgmres_solver_child_terminal_locked(self, token: object) -> None:
        if token is not self._released_fgmres_solver_child_token:
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_transaction_changed",
                "/lifetime/fgmres_solver_child",
            )
        self._fgmres_solver_child_borrow_lease = None
        self._fgmres_solver_child_group_capability_snapshot = None
        self._fgmres_solver_child_parent_capability_snapshot = None
        self._fgmres_solver_child_snapshot_value = None
        self._fgmres_producer_resource_projection_value = None
        self._fgmres_solver_child_rollback_pending = False
        self._fgmres_solver_child_phase = "idle"
        if self._fgmres_solver_child_token is token:
            self._fgmres_solver_child_token = None
        # The exact owner witness remains available through the semantic
        # terminal linearization above.  These trailing local clears are
        # idempotent when a one-shot interruption re-enters with token=None.
        self._fgmres_solver_child_owned_owner_identity_snapshot = None
        self._fgmres_solver_child_owned_owner_generation_snapshot = None
        self._fgmres_solver_child_owned_owner_snapshot = None

    def _require_no_fgmres_solver_child(self) -> None:
        if (
            self._fgmres_solver_child_token is not None
            or self._fgmres_solver_child_phase != "idle"
            or self._fgmres_producer_resource_projection_value is not None
        ):
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_active",
                "/lifetime/fgmres_solver_child",
                "Release the FGMRES child before diagnostic work or close.",
            )

    def _require_exact_fgmres_producer_phase_locked(self) -> None:
        self._require_active_fgmres_solver_child_locked()
        capabilities = self._fgmres_solver_child_group_capability_snapshot
        lease = self._fgmres_solver_child_borrow_lease
        token = self._fgmres_solver_child_token
        if (
            self._fgmres_solver_child_phase != "active"
            or type(token) is not object
            or type(capabilities) is not tuple
            or type(lease) is not HipAllocationBorrowLeaseV1
        ):
            _fail(
                "hip_krylov_primitives_fgmres_producer_projection_not_active",
                "/lifetime/fgmres_solver_child/producer_resources",
                "The exact-11 live solver borrow must be active.",
            )
        self._require_exact_fgmres_live_capability_group_locked(
            capabilities,
            lease,
            token,
        )

    def _build_fgmres_producer_resource_projection_locked(
        self,
    ) -> _HipFgmresProducerResourceProjection:
        self._require_exact_fgmres_producer_phase_locked()
        token = self._fgmres_solver_child_token
        solver_capabilities = self._fgmres_solver_child_group_capability_snapshot
        solver_lease = self._fgmres_solver_child_borrow_lease
        parent_capabilities = self._parent_capability_snapshot
        parent_lease = self._parent._krylov_consumer_borrow_lease
        free_owner = self._parent._allocation_owner
        workspace_owner = self._allocation_owner
        if (
            type(token) is not object
            or type(solver_capabilities) is not tuple
            or type(solver_lease) is not HipAllocationBorrowLeaseV1
            or type(parent_capabilities) is not tuple
            or len(parent_capabilities) != len(_BORROWED_NAMES)
            or type(parent_lease) is not HipAllocationBorrowLeaseV1
            or parent_lease.capabilities is not parent_capabilities
            or parent_lease.borrower is not self._lease_token
            or type(free_owner) is not HipAllocationOwnerV1
            or type(workspace_owner) is not HipAllocationOwnerV1
        ):
            _fail(
                "hip_krylov_primitives_fgmres_producer_projection_invalid",
                "/lifetime/fgmres_solver_child/producer_resources/authority",
            )

        f = self._dimensions_snapshot.free_dof_count
        nnz = self._dimensions_snapshot.reduced_csr_nnz
        partials = self._dimensions_snapshot.reduction_partial_count
        resource_specs = (
            (
                "free_space_parent_borrow",
                "reduced_csr_row_ptr",
                parent_capabilities[0],
                free_owner,
                self._parent._pointers["reduced_csr_row_ptr"],
                "i32",
                (f + 1,),
                4 * (f + 1),
            ),
            (
                "free_space_parent_borrow",
                "reduced_csr_column_indices",
                parent_capabilities[1],
                free_owner,
                self._parent._pointers["reduced_csr_column_indices"],
                "i32",
                (nnz,),
                4 * nnz,
            ),
            (
                "free_space_parent_borrow",
                "reduced_csr_values",
                parent_capabilities[2],
                free_owner,
                self._parent._pointers["reduced_csr_values"],
                "f64",
                (nnz,),
                8 * nnz,
            ),
            (
                "krylov_primitive_owned",
                "reduction_ping",
                self._owned_capabilities["reduction_ping"],
                workspace_owner,
                self._pointers["reduction_ping"],
                "f64",
                (2 * partials,),
                16 * partials,
            ),
            (
                "krylov_primitive_owned",
                "reduction_pong",
                self._owned_capabilities["reduction_pong"],
                workspace_owner,
                self._pointers["reduction_pong"],
                "f64",
                (2 * partials,),
                16 * partials,
            ),
        )
        resources: list[_HipFgmresDelegatedProducerResource] = []
        runtime_domain = solver_capabilities[0].runtime_domain
        runtime_domain_id = solver_capabilities[0].runtime_domain_id
        device = solver_capabilities[0].device_ordinal
        for (
            delegation_kind,
            role,
            capability,
            owner,
            base,
            element_type,
            element_extent,
            nbytes,
        ) in resource_specs:
            if (
                type(capability) is not HipAllocationCapabilityV1
                or capability.role != role
                or capability.base is not base
                or capability.pointer_snapshot != _pointer_snapshot_value(base)
                or capability.nbytes != nbytes
                or capability.element_type != element_type
                or type(capability.generation) is not int
                or capability.generation <= 0
                or capability.owner_identity != owner.owner_id
                or capability.runtime_owner is not self._runtime
                or capability.runtime_domain is not runtime_domain
                or capability.runtime_domain_id != runtime_domain_id
                or capability.device_ordinal != device
            ):
                _fail(
                    "hip_krylov_primitives_fgmres_producer_projection_invalid",
                    f"/lifetime/fgmres_solver_child/producer_resources/{role}",
                )
            resources.append(
                _HipFgmresDelegatedProducerResource(
                    delegation_kind=delegation_kind,
                    role=role,
                    capability=capability,
                    allocation_owner=owner,
                    allocation_id=capability.allocation_id,
                    owner_identity=capability.owner_identity,
                    base=base,
                    pointer_snapshot=capability.pointer_snapshot,
                    element_type=element_type,
                    element_extent=element_extent,
                    nbytes=nbytes,
                    generation=capability.generation,
                    runtime_owner=capability.runtime_owner,
                    runtime_domain=runtime_domain,
                    runtime_domain_id=runtime_domain_id,
                    device_ordinal=device,
                )
            )

        resource_tuple = tuple(resources)
        if (
            tuple(resource.role for resource in resource_tuple[:3])
            != _FGMRES_PRODUCER_OPERATOR_ROLES
            or tuple(resource.role for resource in resource_tuple[3:])
            != _FGMRES_PRODUCER_WORKSPACE_ROLES
            or len({id(resource.capability) for resource in resource_tuple}) != 5
            or not {id(resource.capability) for resource in resource_tuple}.isdisjoint(
                id(capability) for capability in solver_capabilities
            )
        ):
            _fail(
                "hip_krylov_primitives_fgmres_producer_projection_invalid",
                "/lifetime/fgmres_solver_child/producer_resources/order",
            )

        operator_resources = (
            resource_tuple[0],
            resource_tuple[1],
            resource_tuple[2],
        )
        workspace_resources = (resource_tuple[3], resource_tuple[4])
        return _HipFgmresProducerResourceProjection(
            primitive_context=self,
            primitive_context_id=self._context_id,
            primitive_parent_lease_token=self._lease_token,
            primitive_parent_lease_epoch=self._lease_epoch,
            solver_child_token=token,
            solver_child_lease_epoch=self._fgmres_solver_child_epoch_value,
            source_apply=self._source_apply_snapshot,
            source_apply_receipt_hash=self._source_apply_hash_snapshot,
            runtime=self._runtime,
            loaded_runtime=_loaded_runtime(self._parent),
            stream=self._stream,
            runtime_domain=runtime_domain,
            runtime_domain_id=runtime_domain_id,
            device_ordinal=device,
            operator_parent_borrow_capabilities=parent_capabilities,
            operator_parent_borrow_lease=parent_lease,
            solver_allocation_borrow_capabilities=solver_capabilities,
            solver_allocation_borrow_lease=solver_lease,
            delegated_operator_resources=operator_resources,
            delegated_workspace_resources=workspace_resources,
        )

    def _validate_fgmres_producer_resource_projection_locked(
        self,
        projection: _HipFgmresProducerResourceProjection,
    ) -> None:
        try:
            expected = self._build_fgmres_producer_resource_projection_locked()
            identity_fields = (
                "primitive_context",
                "primitive_parent_lease_token",
                "solver_child_token",
                "source_apply",
                "runtime",
                "loaded_runtime",
                "stream",
                "runtime_domain",
                "operator_parent_borrow_capabilities",
                "operator_parent_borrow_lease",
                "solver_allocation_borrow_capabilities",
                "solver_allocation_borrow_lease",
            )
            scalar_fields = (
                "primitive_context_id",
                "primitive_parent_lease_epoch",
                "solver_child_lease_epoch",
                "source_apply_receipt_hash",
                "runtime_domain_id",
                "device_ordinal",
            )
            changed = any(
                getattr(projection, field) is not getattr(expected, field)
                for field in identity_fields
            ) or any(
                type(getattr(projection, field)) is not type(getattr(expected, field))
                or getattr(projection, field) != getattr(expected, field)
                for field in scalar_fields
            )
            actual_groups = (
                projection.delegated_operator_resources,
                projection.delegated_workspace_resources,
            )
            expected_groups = (
                expected.delegated_operator_resources,
                expected.delegated_workspace_resources,
            )
            if any(
                type(actual_group) is not tuple
                or len(actual_group) != len(expected_group)
                for actual_group, expected_group in zip(
                    actual_groups,
                    expected_groups,
                    strict=True,
                )
            ):
                changed = True
            else:
                resource_identity_fields = (
                    "capability",
                    "allocation_owner",
                    "base",
                    "runtime_owner",
                    "runtime_domain",
                )
                resource_scalar_fields = (
                    "delegation_kind",
                    "role",
                    "allocation_id",
                    "owner_identity",
                    "pointer_snapshot",
                    "element_type",
                    "element_extent",
                    "nbytes",
                    "generation",
                    "runtime_domain_id",
                    "device_ordinal",
                )
                for actual_group, expected_group in zip(
                    actual_groups,
                    expected_groups,
                    strict=True,
                ):
                    for actual, expected_resource in zip(
                        actual_group,
                        expected_group,
                        strict=True,
                    ):
                        if type(actual) is not _HipFgmresDelegatedProducerResource:
                            changed = True
                            break
                        if any(
                            getattr(actual, field)
                            is not getattr(expected_resource, field)
                            for field in resource_identity_fields
                        ) or any(
                            type(getattr(actual, field))
                            is not type(getattr(expected_resource, field))
                            or getattr(actual, field)
                            != getattr(expected_resource, field)
                            for field in resource_scalar_fields
                        ):
                            changed = True
                            break
                    if changed:
                        break
        except Exception:
            changed = True
        if changed:
            self._poison("hip_krylov_primitives_fgmres_producer_projection_changed")
            _fail(
                "hip_krylov_primitives_fgmres_producer_projection_changed",
                "/lifetime/fgmres_solver_child/producer_resources",
            )

    def _build_fgmres_solver_child_snapshot_locked(
        self,
        *,
        parent_capabilities: tuple[
            HipAllocationCapabilityV1,
            HipAllocationCapabilityV1,
            HipAllocationCapabilityV1,
        ]
        | None = None,
        allocation_capabilities: tuple[HipAllocationCapabilityV1, ...] | None = None,
        allocation_borrow_lease: HipAllocationBorrowLeaseV1 | None = None,
        allocation_borrow_phase: str | None = None,
    ) -> _HipFgmresSolverChildSnapshot:
        source_apply = self._source_apply_snapshot
        direction_generation = source_apply.direction_generation
        if direction_generation is None:  # pragma: no cover - acquisition guard
            _fail(
                "hip_krylov_primitives_fgmres_source_apply_invalid",
                "/lifetime/fgmres_solver_child/source_apply/direction_generation",
            )
        bindings = self._bindings_snapshot
        execution_plan = self._parent._plan
        free_space_plan = self._parent._overlay
        state_displacement = self._parent._resident._state.displacement_si
        kernel_binding = self._kernel_binding
        if kernel_binding is None:  # pragma: no cover - usable-context invariant
            _fail(
                "hip_krylov_primitives_fgmres_kernel_binding_missing",
                "/lifetime/fgmres_solver_child/kernel",
            )
        if parent_capabilities is None:
            parent_capabilities = self._fgmres_solver_child_parent_capability_snapshot
            if parent_capabilities is None:
                parent_capabilities = (
                    self._fgmres_parent_allocation_capabilities_locked()
                )
        if allocation_capabilities is None:
            allocation_capabilities = (
                self._fgmres_solver_child_group_capability_snapshot
            )
        if allocation_borrow_lease is None:
            allocation_borrow_lease = self._fgmres_solver_child_borrow_lease
        if allocation_borrow_phase is None:
            allocation_borrow_phase = self._fgmres_solver_child_phase
            if allocation_borrow_phase == "idle":
                allocation_borrow_phase = "compatibility_active"
        lineage_capabilities = (
            parent_capabilities
            if allocation_capabilities is None
            else allocation_capabilities
        )
        runtime_domain = parent_capabilities[0].runtime_domain
        runtime_domain_id = parent_capabilities[0].runtime_domain_id
        allocation_device = parent_capabilities[0].device_ordinal
        device_pointers = (
            ("reduced_csr_row_ptr", self._parent._pointers["reduced_csr_row_ptr"]),
            (
                "reduced_csr_column_indices",
                self._parent._pointers["reduced_csr_column_indices"],
            ),
            ("reduced_csr_values", self._parent._pointers["reduced_csr_values"]),
            ("reduced_state", self._parent._pointers["reduced_state"]),
            ("reduced_load", self._parent._pointers["reduced_load"]),
            ("reduced_direction", self._parent._pointers["reduced_direction"]),
            ("jacobi_inverse", self._pointers["jacobi_inverse"]),
        )
        return _HipFgmresSolverChildSnapshot(
            primitive_context=self,
            primitive_context_id=self._context_id,
            primitive_opening_receipt=self._opening_receipt,
            primitive_opening_receipt_hash=(self._opening_receipt.context_receipt_hash),
            source_apply=source_apply,
            source_apply_receipt_hash=self._source_apply_hash_snapshot,
            source_apply_sequence=source_apply.sequence,
            source_direction_generation=direction_generation,
            source_execution_plan=execution_plan,
            source_free_space_plan=free_space_plan,
            source_state_displacement=state_displacement,
            source_state_displacement_hash=(
                self._parent._resident.opening_receipt.bindings.state_displacement_hash
            ),
            primitive_parent_lease_epoch=self._lease_epoch,
            solver_child_lease_epoch=self._fgmres_solver_child_epoch_value,
            runtime=self._runtime,
            loaded_runtime=_loaded_runtime(self._parent),
            stream=self._stream,
            device_ordinal=self._parent._resident._device_ordinal_snapshot,
            architecture=kernel_binding.architecture,
            source_execution_plan_hash=bindings.source_execution_plan_hash,
            source_free_space_plan_hash=free_space_plan.plan_hash,
            source_free_space_view_hash=free_space_plan.free_space_view_hash,
            source_operator_hash=bindings.source_operator_hash,
            source_numeric_snapshot_hash=bindings.source_numeric_snapshot_hash,
            source_partition_hash=bindings.source_partition_hash,
            state_hash=bindings.state_hash,
            state_epoch=bindings.state_epoch,
            free_dof_count=self._dimensions_snapshot.free_dof_count,
            reduced_csr_nnz=self._dimensions_snapshot.reduced_csr_nnz,
            parent_allocation_capabilities=parent_capabilities,
            allocation_borrow_capabilities=allocation_capabilities,
            allocation_borrow_lease=allocation_borrow_lease,
            allocation_borrow_phase=allocation_borrow_phase,
            allocation_runtime_domain=runtime_domain,
            allocation_runtime_domain_id=runtime_domain_id,
            allocation_device_ordinal=allocation_device,
            allocation_generations=tuple(
                capability.generation for capability in lineage_capabilities
            ),
            device_pointers=device_pointers,
        )

    def _validate_fgmres_solver_child_snapshot_locked(self) -> None:
        snapshot = self._fgmres_solver_child_snapshot_value
        if snapshot is None:
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_snapshot_missing",
                "/lifetime/fgmres_solver_child/snapshot",
            )
        try:
            expected = self._build_fgmres_solver_child_snapshot_locked()
            identity_fields = (
                "primitive_context",
                "primitive_opening_receipt",
                "source_apply",
                "source_execution_plan",
                "source_free_space_plan",
                "source_state_displacement",
                "runtime",
                "loaded_runtime",
                "stream",
                "parent_allocation_capabilities",
                "allocation_borrow_capabilities",
                "allocation_borrow_lease",
                "allocation_runtime_domain",
            )
            scalar_fields = (
                "primitive_context_id",
                "primitive_opening_receipt_hash",
                "source_apply_receipt_hash",
                "source_apply_sequence",
                "source_direction_generation",
                "source_state_displacement_hash",
                "primitive_parent_lease_epoch",
                "solver_child_lease_epoch",
                "device_ordinal",
                "architecture",
                "source_execution_plan_hash",
                "source_free_space_plan_hash",
                "source_free_space_view_hash",
                "source_operator_hash",
                "source_numeric_snapshot_hash",
                "source_partition_hash",
                "state_hash",
                "state_epoch",
                "free_dof_count",
                "reduced_csr_nnz",
                "allocation_borrow_phase",
                "allocation_runtime_domain_id",
                "allocation_device_ordinal",
                "allocation_generations",
            )
            changed = any(
                getattr(snapshot, name) is not getattr(expected, name)
                for name in identity_fields
            ) or any(
                type(getattr(snapshot, name)) is not type(getattr(expected, name))
                or getattr(snapshot, name) != getattr(expected, name)
                for name in scalar_fields
            )
            actual_pointers = snapshot.device_pointers
            expected_pointers = expected.device_pointers
            if type(actual_pointers) is not tuple or len(actual_pointers) != len(
                expected_pointers
            ):
                changed = True
            else:
                for actual, expected_pointer in zip(
                    actual_pointers, expected_pointers, strict=True
                ):
                    if (
                        type(actual) is not tuple
                        or len(actual) != 2
                        or type(actual[0]) is not str
                        or actual[0] != expected_pointer[0]
                        or actual[1] is not expected_pointer[1]
                    ):
                        changed = True
                        break
        except Exception:
            changed = True
        if changed:
            self._poison("hip_krylov_primitives_fgmres_solver_child_snapshot_changed")
            _fail(
                "hip_krylov_primitives_fgmres_solver_child_snapshot_changed",
                "/lifetime/fgmres_solver_child/snapshot",
            )

    def _failed_batch(
        self,
        sequence: int,
        delta: HipKrylovPrimitivesBatchDelta,
        code: str,
        error: Any,
    ) -> HipKrylovPrimitivesBatchReceipt:
        self._poison(code)
        receipt = _build_batch_receipt(
            status="unavailable",
            context=self,
            sequence=sequence,
            delta=delta,
            reason=HipKrylovPrimitivesReason(code, _detail(error)),
        )
        self._record_batch_witness(receipt)
        return receipt

    def _record_batch_witness(self, receipt: HipKrylovPrimitivesBatchReceipt) -> None:
        if receipt.sequence in self._batch_witnesses:
            _fail("hip_krylov_primitives_batch_sequence_reused", "/batch/sequence")
        self._batch_witnesses[receipt.sequence] = receipt.receipt_hash
        self._last_batch = receipt

    def _poison(self, detail: str) -> None:
        self._poisoned = True
        self._failure_reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_context_poisoned", _detail(detail)
        )
        if not self._parent.poisoned:
            try:
                self._parent._poison_krylov_consumer(self._lease_token, detail)
            except Exception:
                pass

    def _require_usable(self) -> None:
        if self._closed:
            _fail("hip_krylov_primitives_context_closed", "/status")
        if self._closing:
            _fail("hip_krylov_primitives_context_closing", "/status")
        if self._cleanup_failed:
            _fail("hip_krylov_primitives_context_cleanup_failed", "/status")
        if self._poisoned:
            _fail("hip_krylov_primitives_context_poisoned", "/status")

    def _validate_authority(self) -> None:
        try:
            changed = any(
                (
                    self._parent is not self._parent_snapshot,
                    self._runtime is not self._runtime_snapshot,
                    self._stream is not self._stream_snapshot,
                    self._parent._runtime is not self._runtime_snapshot,
                    self._parent._stream is not self._stream_snapshot,
                    self._parent.closed,
                    self._source_apply is not self._source_apply_snapshot,
                    self._source_apply.receipt_hash != self._source_apply_hash_snapshot,
                    self._parent.opening_receipt.context_receipt_hash
                    != self._parent_opening_hash_snapshot,
                    _bindings(
                        self._parent,
                        self._source_apply,
                        self._lease_epoch,
                        self._kernel_internally_compiled,
                    )
                    != self._bindings_snapshot,
                    _dimensions(self._parent) != self._dimensions_snapshot,
                )
            )
        except Exception:
            changed = True
        if changed:
            self._poison("hip_krylov_primitives_runtime_authority_changed")
            _fail("hip_krylov_primitives_runtime_authority_changed", "/parent")
        self._validate_parent_allocation_authority()
        current = _borrowed_pointer_snapshot(self._parent_capability_snapshot)
        if any(
            current[name] is not self._borrowed_pointer_snapshot[name]
            for name in _BORROWED_NAMES
        ):
            self._poison("hip_krylov_primitives_borrowed_pointer_changed")
            _fail(
                "hip_krylov_primitives_borrowed_pointer_changed",
                "/parent/buffers",
            )
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
            self._poison("hip_krylov_primitives_kernel_authority_changed")
            _fail("hip_krylov_primitives_kernel_authority_changed", "/kernel")

    def _validate_parent_allocation_authority(self) -> None:
        try:
            current = self._parent._krylov_parent_allocation_capabilities(
                self._lease_token
            )
        except Exception as exc:
            self._poison("hip_krylov_primitives_parent_allocation_lineage_changed")
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_parent_allocation_lineage_changed",
                "/parent/allocation_lineage",
                _detail(exc),
            ) from exc
        if (
            type(current) is not tuple
            or current is not self._parent_capability_snapshot
            or self._parent_capabilities is not self._parent_capability_snapshot
            or len(current) != len(_BORROWED_NAMES)
        ):
            self._poison("hip_krylov_primitives_parent_allocation_lineage_changed")
            _fail(
                "hip_krylov_primitives_parent_allocation_lineage_changed",
                "/parent/allocation_lineage",
            )
        parent_owner = self._parent._allocation_owner
        for name, capability in zip(_BORROWED_NAMES, current, strict=True):
            try:
                validate_hip_allocation_capability_v1(
                    capability,
                    expected_owner=parent_owner,
                )
            except HipAllocationLineageError as exc:
                self._poison("hip_krylov_primitives_parent_allocation_lineage_changed")
                raise HipKrylovPrimitivesContextError(
                    "hip_krylov_primitives_parent_allocation_lineage_changed",
                    f"/parent/allocation_lineage/{name}",
                    _detail(exc),
                ) from exc
            if any(
                (
                    type(capability) is not HipAllocationCapabilityV1,
                    capability.role != name,
                    capability.base is not self._borrowed_pointers[name],
                    capability.pointer_snapshot
                    != _pointer_snapshot_value(self._borrowed_pointers[name]),
                    capability.runtime_owner is not self._runtime,
                    capability.device_ordinal
                    != self._parent._resident._device_ordinal_snapshot,
                    capability.evidence_scope
                    != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                    capability.promotion_eligible,
                )
            ):
                self._poison("hip_krylov_primitives_parent_allocation_lineage_changed")
                _fail(
                    "hip_krylov_primitives_parent_allocation_lineage_changed",
                    f"/parent/allocation_lineage/{name}",
                )

    def _validate_owned_pointer_authority(self) -> None:
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
            self._poison("hip_krylov_primitives_owned_pointer_changed")
            _fail("hip_krylov_primitives_owned_pointer_changed", "/owned_buffers")
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
                self._poison("hip_krylov_primitives_allocation_lineage_changed")
                raise HipKrylovPrimitivesContextError(
                    "hip_krylov_primitives_allocation_lineage_changed",
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
                    != self._parent._resident._device_ordinal_snapshot,
                    capability.evidence_scope
                    != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                    capability.promotion_eligible,
                )
            ):
                self._poison("hip_krylov_primitives_allocation_lineage_changed")
                _fail(
                    "hip_krylov_primitives_allocation_lineage_changed",
                    f"/owned_buffers/{name}",
                )

    def _validate_cleanup_authority(self) -> None:
        if any(
            (
                self._parent is not self._parent_snapshot,
                self._runtime is not self._runtime_snapshot,
                self._stream is not self._stream_snapshot,
                self._kernel is not self._kernel_object_snapshot,
                self._kernel is None,
                bool(getattr(self._kernel, "closed", False)),
            )
        ):
            self._poison("hip_krylov_primitives_cleanup_authority_changed")
            _fail("hip_krylov_primitives_cleanup_authority_changed", "/cleanup")
        self._validate_owned_pointer_authority()

    def _build_receipt(
        self, status: ContextStatus
    ) -> HipKrylovPrimitivesContextReceipt:
        ready = status == "context_ready"
        return _build_context_receipt(
            status=status,
            context_id=self._context_id,
            evidence_scope=self._evidence_scope,
            actual_backend=(
                "hip"
                if self._evidence_scope == "native_hiprtc_krylov_primitives_composite"
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


_HIP_KRYLOV_PRIMITIVES_CONTEXT_INITIALIZER = (
    HipKrylovPrimitivesExecutionContext.__init__
)


class _BatchAbort(Exception):
    def __init__(self, receipt: HipKrylovPrimitivesBatchReceipt) -> None:
        self.receipt = receipt


def open_hip_krylov_primitives_execution_context(
    parent: HipFreeSpaceExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    *,
    architecture: str | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    rtc_kernel: Any | None = None,
) -> HipKrylovPrimitivesContextOpenResult:
    """Open a same-stream primitive child for the latest device apply."""

    if type(parent) is not HipFreeSpaceExecutionContext:
        _fail("hip_krylov_primitives_parent_type_invalid", "/parent")
    if type(source_apply) is not HipFreeSpaceApplyReceipt:
        _fail("hip_krylov_primitives_source_apply_type_invalid", "/source_apply")
    parent._require_usable()
    validate_hip_free_space_apply_receipt(source_apply, expected_context=parent)
    if (
        source_apply.status != "enqueued"
        or source_apply is not parent._last_apply
        or source_apply.direction_generation is None
        or parent._apply_witnesses.get(source_apply.sequence)
        != (source_apply.direction_generation, source_apply.receipt_hash)
    ):
        _fail(
            "hip_krylov_primitives_source_apply_not_latest",
            "/source_apply",
        )
    requested_architecture = parent._kernel_binding.architecture
    if architecture is not None and architecture != requested_architecture:
        _fail("hip_krylov_primitives_architecture_mismatch", "/architecture")
    if isinstance(memory_budget_bytes, bool) or (
        memory_budget_bytes is not None
        and (not isinstance(memory_budget_bytes, int) or memory_budget_bytes <= 0)
    ):
        _fail("hip_krylov_primitives_memory_budget_invalid", "/memory_budget_bytes")
    if rtc_kernel is not None:
        _preflight_kernel(rtc_kernel)

    views = _buffer_views(parent)
    owned_bytes = sum(view.byte_length for view in views)
    if memory_budget_bytes is not None and owned_bytes > memory_budget_bytes:
        _fail(
            "hip_krylov_primitives_memory_budget_exceeded",
            "/memory_budget_bytes",
            f"Required {owned_bytes} bytes exceeds budget {memory_budget_bytes}.",
        )
    # Pre-issue the process-local token before the parent publishes it.  The
    # exact identity therefore survives an interruption between parent return
    # and caller assignment.
    token = object()
    lease_epoch = 0
    internally_compiled = rtc_kernel is None
    kernel = rtc_kernel
    kernel_handoff = _HipRtcKrylovPrimitivesKernelHandoff()
    binding: HipKrylovPrimitivesKernelBinding | None = None
    pointers: dict[str, Any] = {}
    parent_capabilities: tuple[HipAllocationCapabilityV1, ...] = ()
    allocation_owner: HipAllocationOwnerV1 | None = None
    allocation_owner_handoff: list[HipAllocationOwnerV1 | None] = [None]
    owned_capabilities: dict[str, HipAllocationCapabilityV1] = {}
    pending_free_leases: dict[str, HipAllocationFreeLeaseV1] = {}
    cleanup_dispositions: dict[str, CleanupDisposition] = {}
    orphan_cleanups: list[_HipKrylovPrimitivesOrphanCleanup] = []
    borrowed: dict[str, Any] = {}
    telemetry = HipKrylovPrimitivesTelemetry(
        module_owner_acquired_count=int(kernel is not None)
    )
    evidence_scope: EvidenceScope = "injected_test_double"
    context_id = _ZERO_HASH
    sync_complete = False
    poison_parent = False
    context: HipKrylovPrimitivesExecutionContext | None = None
    try:
        acquired_token = parent._acquire_krylov_consumer_for_apply(
            source_apply,
            token,
        )
        if acquired_token is not token:
            _fail(
                "hip_krylov_primitives_parent_token_changed",
                "/parent/lifetime/krylov_consumer",
            )
        lease_epoch = parent._krylov_consumer_epoch(token)
        context_id = _fallback_context_id(parent, source_apply, lease_epoch, None)
        selector = getattr(parent._runtime, "set_device", None)
        if callable(selector):
            selector(parent._resident._device_ordinal_snapshot)
        parent_capabilities = _parent_allocation_capabilities(parent, token)
        borrowed = _borrowed_pointer_snapshot(parent_capabilities)
        allocation_owner = parent._open_krylov_allocation_owner(
            token,
            "krylov_primitives_owned_buffers",
            _handoff=allocation_owner_handoff,
        )
        telemetry = replace(
            telemetry,
            lineage_owner_open_success_count=1,
        )
        if kernel is None:
            loaded = _loaded_runtime(parent)
            try:
                kernel = _compile_krylov_primitives_with_handoff(
                    compile_hip_rtc_krylov_primitives_kernel,
                    kernel_handoff,
                    loaded,
                    requested_architecture,
                    hiprtc_library,
                )
            except HipRtcKrylovPrimitivesError as exc:
                if exc.cleanup_owner is not None:
                    kernel = exc.cleanup_owner
                    telemetry = replace(telemetry, module_owner_acquired_count=1)
                raise
            telemetry = replace(telemetry, module_owner_acquired_count=1)
        binding = _kernel_binding(kernel, requested_architecture)
        evidence_scope = _evidence_scope(parent, kernel, binding, internally_compiled)
        context_id = _context_id(
            parent, source_apply, lease_epoch, binding, evidence_scope
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
                        _HipKrylovPrimitivesOrphanCleanup(
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
            cleanup_dispositions[view.name] = "live"
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
            if view.name != "error_flag":
                continue
            zero = immutable_array([0], dtype="<i4")
            telemetry = replace(
                telemetry,
                h2d_operation_attempt_count=1,
                h2d_bytes_attempted=4,
                error_flag_h2d_bytes=4,
            )
            # From the first queue mutation onward, any exception means that
            # ordering or device state is no longer authoritatively known.
            poison_parent = True
            parent._runtime.copy_h2d_async(pointer, zero, parent._stream)
            telemetry = replace(
                telemetry,
                h2d_operation_success_count=1,
                h2d_bytes_succeeded=4,
            )

        telemetry = replace(
            telemetry,
            kernel_launch_attempt_count=telemetry.kernel_launch_attempt_count + 1,
        )
        result = kernel.launch_prepare_positive_jacobi(
            parent._stream,
            parent._overlay.free_dof_count,
            parent._overlay.reduced_csr_nnz,
            borrowed["reduced_csr_row_ptr"],
            borrowed["reduced_csr_column_indices"],
            borrowed["reduced_csr_values"],
            pointers["jacobi_inverse"],
            pointers["error_flag"],
        )
        if result is not None:
            _fail("hip_krylov_primitives_kernel_contract_invalid", "/kernel/prepare")
        telemetry = replace(
            telemetry,
            kernel_launch_success_count=telemetry.kernel_launch_success_count + 1,
        )
        host_error = np.empty(1, dtype="<i4")
        telemetry = replace(
            telemetry,
            d2h_operation_attempt_count=1,
            d2h_bytes_attempted=4,
            error_flag_d2h_bytes=4,
            sync_attempt_count=1,
        )
        parent._runtime.copy_d2h_async(
            host_error, pointers["error_flag"], parent._stream
        )
        telemetry = replace(
            telemetry,
            d2h_operation_success_count=1,
            d2h_bytes_succeeded=4,
        )
        parent._runtime.synchronize(parent._stream)
        telemetry = replace(telemetry, sync_success_count=1)
        _acknowledge_kernel_completion_if_pending(kernel, parent._stream)
        sync_complete = True
        error_bits = int(host_error[0])
        if error_bits != 0:
            from .krylov_primitives_rtc import (
                KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
                KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL,
            )

            if error_bits in {
                KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL,
                KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
            }:
                if _trusted_jacobi_diagonal_status(parent) == "unsupported":
                    poison_parent = False
                    raise _UnsupportedDiagonal(error_bits)
                _fail(
                    "hip_krylov_primitives_prepare_device_mismatch",
                    "/kernel/prepare",
                    "device rejected a trusted positive reduced diagonal",
                )
            poison_parent = True
            _fail(
                "hip_krylov_primitives_prepare_device_error",
                "/kernel/prepare",
                f"device error bits {error_bits}",
            )
        # Preallocate the cleanup owner before initialization transfers live
        # authority into it.  Validation or caller STORE interruption can then
        # reuse this exact object instead of creating a competing owner.
        context = object.__new__(HipKrylovPrimitivesExecutionContext)
        _HIP_KRYLOV_PRIMITIVES_CONTEXT_INITIALIZER(
            context,
            parent=parent,
            source_apply=source_apply,
            lease_token=token,
            lease_epoch=lease_epoch,
            kernel=kernel,
            kernel_binding=binding,
            kernel_internally_compiled=internally_compiled,
            evidence_scope=evidence_scope,
            context_id=context_id,
            borrowed_pointers=borrowed,
            parent_capabilities=parent_capabilities,
            pointers=pointers,
            allocation_owner=allocation_owner,
            owned_capabilities=owned_capabilities,
            pending_free_leases=pending_free_leases,
            cleanup_dispositions=cleanup_dispositions,
            orphan_cleanups=orphan_cleanups,
            allocation_owner_closed=False,
            allocation_lineage=_allocation_lineage(telemetry),
            owned_buffers=views,
            telemetry=telemetry,
            opening_status="context_ready",
            failure_reason=None,
        )
        validate_hip_krylov_primitives_context_receipt(
            context.opening_receipt, expected_context=context
        )
        return HipKrylovPrimitivesContextOpenResult(context, context.opening_receipt)
    except BaseException as primary:
        recovered_epoch = parent._krylov_consumer_epoch_if_owned(token)
        if recovered_epoch is None:
            # Parent state was never published, so no cleanup authority exists.
            raise
        lease_epoch = recovered_epoch
        if context_id == _ZERO_HASH:
            context_id = _fallback_context_id(
                parent,
                source_apply,
                lease_epoch,
                None,
            )
        if allocation_owner is None:
            handed_off_owner = allocation_owner_handoff[0]
            # The parent may have closed a handed-off peer while rolling back
            # its own post-open validation.  Only retain live cleanup authority;
            # a closed owner is already terminal and must not be snapshotted.
            if handed_off_owner is not None and not handed_off_owner.closed:
                allocation_owner = handed_off_owner
        if allocation_owner is not None and allocation_owner.closed:
            allocation_owner = None
        if allocation_owner is not None:
            # The local owner assignment may have completed immediately before
            # an interruption in the telemetry publication that follows it.
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
        if isinstance(primary, _UnsupportedDiagonal):
            poison_parent = False
        cleanup_result = _cleanup_failed_open(
            primary=primary,
            parent=parent,
            source_apply=source_apply,
            token=token,
            lease_epoch=lease_epoch,
            kernel=kernel,
            binding=binding,
            internally_compiled=internally_compiled,
            evidence_scope=evidence_scope,
            context_id=context_id,
            borrowed=borrowed,
            parent_capabilities=parent_capabilities,
            pointers=pointers,
            allocation_owner=allocation_owner,
            owned_capabilities=owned_capabilities,
            pending_free_leases=pending_free_leases,
            cleanup_dispositions=cleanup_dispositions,
            orphan_cleanups=orphan_cleanups,
            views=views,
            telemetry=telemetry,
            sync_complete=sync_complete,
            poison_parent=poison_parent,
            existing_context=context,
        )
        if isinstance(primary, Exception):
            return cleanup_result
        if cleanup_result.context is not None:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_context_open_interrupted",
                "/open",
                _detail(primary),
                cleanup_owner=cleanup_result.context,
            ) from primary
        raise


class _UnsupportedDiagonal(Exception):
    def __init__(self, error_bits: int) -> None:
        self.error_bits = error_bits
        super().__init__(
            "positive unshifted Jacobi is unsupported: diagonal is missing or nonpositive"
        )


def _cleanup_failed_open(
    *,
    primary: BaseException,
    parent: HipFreeSpaceExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    token: object,
    lease_epoch: int,
    kernel: Any,
    binding: HipKrylovPrimitivesKernelBinding | None,
    internally_compiled: bool,
    evidence_scope: EvidenceScope,
    context_id: str,
    borrowed: dict[str, Any],
    parent_capabilities: tuple[HipAllocationCapabilityV1, ...],
    pointers: dict[str, Any],
    allocation_owner: HipAllocationOwnerV1 | None,
    owned_capabilities: dict[str, HipAllocationCapabilityV1],
    pending_free_leases: dict[str, HipAllocationFreeLeaseV1],
    cleanup_dispositions: dict[str, CleanupDisposition],
    orphan_cleanups: list[_HipKrylovPrimitivesOrphanCleanup],
    views: tuple[HipKrylovPrimitivesBufferView, ...],
    telemetry: HipKrylovPrimitivesTelemetry,
    sync_complete: bool,
    poison_parent: bool,
    existing_context: HipKrylovPrimitivesExecutionContext | None = None,
) -> HipKrylovPrimitivesContextOpenResult:
    if poison_parent:
        try:
            parent._poison_krylov_consumer(
                token, "hip_krylov_primitives_context_open_queue_failed"
            )
        except BaseException:
            pass
    if isinstance(primary, _UnsupportedDiagonal):
        reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_positive_jacobi_unsupported", _detail(primary)
        )
    else:
        reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_context_cleanup_failed", _detail(primary)
        )
    context_arguments: dict[str, Any] = {
        "parent": parent,
        "source_apply": source_apply,
        "lease_token": token,
        "lease_epoch": lease_epoch,
        "kernel": kernel,
        "kernel_binding": binding,
        "kernel_internally_compiled": internally_compiled,
        "evidence_scope": evidence_scope,
        "context_id": context_id,
        "borrowed_pointers": borrowed,
        "parent_capabilities": parent_capabilities,
        "pointers": pointers,
        "allocation_owner": allocation_owner,
        "owned_capabilities": owned_capabilities,
        "pending_free_leases": pending_free_leases,
        "cleanup_dispositions": cleanup_dispositions,
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
            context = HipKrylovPrimitivesExecutionContext(**context_arguments)
        except BaseException:
            # A failing public constructor must not strand the resource graph.
            # Reuse the captured original initializer on one preallocated owner.
            context = object.__new__(HipKrylovPrimitivesExecutionContext)
            _HIP_KRYLOV_PRIMITIVES_CONTEXT_INITIALIZER(
                context,
                **context_arguments,
            )
    context._close_sync_complete = sync_complete or (
        not pointers
        and not any(cleanup.pointer is not None for cleanup in orphan_cleanups)
    )
    try:
        context.close()
    except BaseException as cleanup_error:
        context._failure_reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_context_cleanup_failed",
            _detail(f"{_detail(primary)}; cleanup: {_detail(cleanup_error)}"),
        )
        context._cleanup_failed = True
        context._opening_receipt = context._build_receipt("cleanup_failed")
        return HipKrylovPrimitivesContextOpenResult(context, context.opening_receipt)

    telemetry = context._telemetry
    lineage = context._allocation_lineage_snapshot
    if context._cleanup_quarantined:
        receipt = _build_context_receipt(
            status="cleanup_quarantined",
            context_id=context_id,
            evidence_scope=evidence_scope,
            actual_backend=(
                "hip"
                if evidence_scope == "native_hiprtc_krylov_primitives_composite"
                else "test_double"
            ),
            reason=context._failure_reason,
            bindings=_bindings(parent, source_apply, lease_epoch, internally_compiled),
            kernel=binding,
            dimensions=_dimensions(parent),
            owned_buffers=(),
            allocation_lineage=lineage,
            telemetry=telemetry,
            claims=_claims(False, evidence_scope, lease_active=False),
        )
        return HipKrylovPrimitivesContextOpenResult(None, receipt)

    if isinstance(primary, _UnsupportedDiagonal):
        reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_positive_jacobi_unsupported", _detail(primary)
        )
    else:
        reason = HipKrylovPrimitivesReason(
            "hip_krylov_primitives_context_open_failed", _detail(primary)
        )
    receipt = _build_context_receipt(
        status="unavailable",
        context_id=context_id,
        evidence_scope=evidence_scope,
        actual_backend=None,
        reason=reason,
        bindings=_bindings(parent, source_apply, lease_epoch, internally_compiled),
        kernel=binding,
        dimensions=_dimensions(parent),
        owned_buffers=(),
        allocation_lineage=lineage,
        telemetry=telemetry,
        claims=_claims(False, evidence_scope, lease_active=False),
    )
    return HipKrylovPrimitivesContextOpenResult(None, receipt)


def _buffer_views(
    parent: HipFreeSpaceExecutionContext,
) -> tuple[HipKrylovPrimitivesBufferView, ...]:
    f = parent._overlay.free_dof_count
    p = max(1, (f + 511) // 512)
    views: list[HipKrylovPrimitivesBufferView] = []
    for name, count, access in (
        ("jacobi_inverse", f, "read_only_after_prepare"),
        ("work_x", f, "read_write"),
        ("work_y", f, "read_write"),
        ("preconditioned", f, "read_write"),
        ("reduction_ping", 2 * p, "read_write"),
        ("reduction_pong", 2 * p, "read_write"),
        ("dot_result", 1, "write_only"),
        ("norm_result", 1, "write_only"),
    ):
        views.append(
            HipKrylovPrimitivesBufferView(
                name,
                "<f8",
                (count,),
                8 * count,
                None,
                access,
                "device_only",
            )
        )
    views.append(
        HipKrylovPrimitivesBufferView(
            "error_flag",
            "<i4",
            (1,),
            4,
            _ZERO_I32_DATA_HASH,
            "read_write",
            "async_h2d_zero_once_then_same_stream_fence",
        )
    )
    return tuple(views)


def _buffer_view(
    views: tuple[HipKrylovPrimitivesBufferView, ...], name: str
) -> HipKrylovPrimitivesBufferView:
    for view in views:
        if view.name == name:
            return view
    _fail("hip_krylov_primitives_owned_buffer_missing", f"/owned_buffers/{name}")


def _lineage_element_type(view: HipKrylovPrimitivesBufferView) -> str:
    if view.dtype == "<i4":
        return "i32"
    if view.dtype == "<f8":
        return "f64"
    _fail(
        "hip_krylov_primitives_lineage_element_type_invalid",
        f"/owned_buffers/{view.name}/dtype",
    )


def _allocation_lineage(
    telemetry: HipKrylovPrimitivesTelemetry,
) -> HipKrylovPrimitivesAllocationLineage:
    count = telemetry.lineage_capability_mint_success_count
    return HipKrylovPrimitivesAllocationLineage(
        capability_profile="foundation_non_promoting",
        evidence_scope="foundation_non_promoting",
        owner_role="krylov_primitives_owned_buffers",
        runtime_device_bound=True,
        parent_borrowed_capability_count=5,
        managed_buffer_count=count,
        managed_device_bytes=telemetry.lineage_capability_mint_bytes,
        all_owned_buffers_managed=count == len(_OWNED_ORDER),
    )


def _pointer_snapshot_value(pointer: object) -> int:
    if type(pointer) is int:
        return pointer
    if type(pointer) is ctypes.c_void_p and type(pointer.value) is int:
        return pointer.value
    _fail("hip_krylov_primitives_owned_pointer_changed", "/owned_buffers")


def _free_outcome_uncertain(runtime: object, error: BaseException) -> bool:
    if type(runtime) is _BoundHipContextRuntime:
        return True
    return type(error) is not HipFreeKnownNotFreedError


def _parent_allocation_capabilities(
    parent: HipFreeSpaceExecutionContext,
    token: object,
) -> tuple[HipAllocationCapabilityV1, ...]:
    try:
        capabilities = parent._krylov_parent_allocation_capabilities(token)
    except Exception as exc:
        raise HipKrylovPrimitivesContextError(
            "hip_krylov_primitives_parent_allocation_lineage_invalid",
            "/parent/allocation_lineage",
            _detail(exc),
        ) from exc
    if type(capabilities) is not tuple or len(capabilities) != len(_BORROWED_NAMES):
        _fail(
            "hip_krylov_primitives_parent_allocation_lineage_invalid",
            "/parent/allocation_lineage",
        )
    parent_owner = parent._allocation_owner
    for name, capability in zip(_BORROWED_NAMES, capabilities, strict=True):
        if type(capability) is not HipAllocationCapabilityV1:
            _fail(
                "hip_krylov_primitives_parent_allocation_lineage_invalid",
                f"/parent/allocation_lineage/{name}",
            )
        try:
            validate_hip_allocation_capability_v1(
                capability,
                expected_owner=parent_owner,
            )
        except HipAllocationLineageError as exc:
            raise HipKrylovPrimitivesContextError(
                "hip_krylov_primitives_parent_allocation_lineage_invalid",
                f"/parent/allocation_lineage/{name}",
                _detail(exc),
            ) from exc
        if any(
            (
                capability.role != name,
                capability.runtime_owner is not parent._runtime,
                capability.device_ordinal != parent._resident._device_ordinal_snapshot,
                capability.evidence_scope != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
                capability.promotion_eligible,
            )
        ):
            _fail(
                "hip_krylov_primitives_parent_allocation_lineage_invalid",
                f"/parent/allocation_lineage/{name}",
            )
    return capabilities


def _borrowed_pointer_snapshot(
    capabilities: tuple[HipAllocationCapabilityV1, ...],
) -> dict[str, Any]:
    if type(capabilities) is not tuple or len(capabilities) != len(_BORROWED_NAMES):
        _fail("hip_krylov_primitives_borrowed_buffer_missing", "/parent/buffers")
    snapshot = {
        name: capability.base
        for name, capability in zip(_BORROWED_NAMES, capabilities, strict=True)
    }
    if any(snapshot[name] is None for name in _BORROWED_NAMES):
        _fail("hip_krylov_primitives_borrowed_buffer_missing", "/parent/buffers")
    return snapshot


def _loaded_runtime(parent: HipFreeSpaceExecutionContext) -> Any:
    runtime = parent._resident._parent._runtime
    return getattr(runtime, "_loaded", runtime)


def _acknowledge_kernel_completion_if_pending(kernel: Any, stream: Any) -> None:
    """Clear exact-stream launch bookkeeping only after an observed fence."""

    if kernel is None:
        return
    try:
        pending = getattr(kernel, "pending_stream_count", None)
        acknowledge = getattr(kernel, "acknowledge_stream_completion", None)
    except Exception as exc:
        raise HipKrylovPrimitivesContextError(
            "hip_krylov_primitives_completion_ack_contract_invalid",
            "/kernel/completion_acknowledgement",
            _detail(exc),
        ) from exc
    if pending is None and acknowledge is None:
        # A module-only cleanup owner has never launched device work.
        return
    if type(pending) is not int or pending < 0 or not callable(acknowledge):
        _fail(
            "hip_krylov_primitives_completion_ack_contract_invalid",
            "/kernel/completion_acknowledgement",
        )
    if pending > 0:
        acknowledge(stream)


def _preflight_kernel(kernel: Any) -> None:
    names = (
        "launch_prepare_positive_jacobi",
        "launch_fill",
        "launch_affine",
        "launch_apply_jacobi",
        "launch_dot_stage",
        "launch_sum_stage",
        "launch_lassq_stage",
        "launch_lassq_combine_stage",
        "launch_lassq_finalize",
        "acknowledge_stream_completion",
        "close",
    )
    try:
        methods = tuple(getattr(kernel, name, None) for name in names)
        closed = bool(getattr(kernel, "closed", False))
        pending_stream_count = getattr(kernel, "pending_stream_count", None)
    except Exception as exc:
        raise HipKrylovPrimitivesContextError(
            "hip_krylov_primitives_kernel_contract_invalid",
            "/rtc_kernel",
            _detail(exc),
        ) from exc
    if not all(callable(method) for method in methods):
        _fail("hip_krylov_primitives_kernel_contract_invalid", "/rtc_kernel")
    if type(pending_stream_count) is not int or pending_stream_count != 0:
        _fail(
            "hip_krylov_primitives_kernel_contract_invalid",
            "/rtc_kernel/pending_stream_count",
        )
    if closed:
        _fail("hip_krylov_primitives_kernel_closed", "/rtc_kernel/closed")


def _kernel_binding(kernel: Any, architecture: str) -> HipKrylovPrimitivesKernelBinding:
    identity = getattr(kernel, "identity", None)
    if identity is None or not callable(getattr(identity, "to_dict", None)):
        _fail("hip_krylov_primitives_kernel_identity_invalid", "/kernel/identity")
    try:
        manifest = identity.to_dict()
    except Exception as exc:
        raise HipKrylovPrimitivesContextError(
            "hip_krylov_primitives_kernel_identity_invalid",
            "/kernel/identity",
            _detail(exc),
        ) from exc
    if not isinstance(manifest, dict):
        _fail("hip_krylov_primitives_kernel_identity_invalid", "/kernel/identity")
    symbols = manifest.get("kernel_symbols")
    geometry = manifest.get("launch_geometry")
    runtime = manifest.get("runtime_library")
    hiprtc = manifest.get("hiprtc_library")
    if not all(
        isinstance(value, dict) for value in (symbols, geometry, runtime, hiprtc)
    ):
        _fail("hip_krylov_primitives_kernel_identity_invalid", "/kernel/identity")
    binding = HipKrylovPrimitivesKernelBinding(
        abi_version=int(manifest.get("abi_version", -1)),
        architecture=str(manifest.get("architecture", "")),
        kernel_name=str(manifest.get("kernel_name", "")),
        prepare_positive_jacobi_symbol=str(symbols.get("prepare_positive_jacobi", "")),
        fill_symbol=str(symbols.get("fill", "")),
        affine_symbol=str(symbols.get("affine", "")),
        apply_jacobi_symbol=str(symbols.get("apply_jacobi", "")),
        dot_stage_symbol=str(symbols.get("dot_stage", "")),
        sum_stage_symbol=str(symbols.get("sum_stage", "")),
        lassq_stage_symbol=str(symbols.get("lassq_stage", "")),
        lassq_combine_stage_symbol=str(symbols.get("lassq_combine_stage", "")),
        lassq_finalize_symbol=str(symbols.get("lassq_finalize", "")),
        vector_block_size=int(geometry.get("block_size", -1)),
        reduction_segment_size=int(geometry.get("reduction_values_per_block", -1)),
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
    binding: HipKrylovPrimitivesKernelBinding, architecture: str | None = None
) -> None:
    from . import krylov_primitives_rtc as rtc

    expected_symbols = (
        rtc.HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL,
        rtc.HIP_RTC_KRYLOV_FILL_SYMBOL,
        rtc.HIP_RTC_KRYLOV_AFFINE_SYMBOL,
        rtc.HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL,
        rtc.HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL,
        rtc.HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL,
        rtc.HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL,
        rtc.HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL,
        rtc.HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL,
    )
    actual_symbols = (
        binding.prepare_positive_jacobi_symbol,
        binding.fill_symbol,
        binding.affine_symbol,
        binding.apply_jacobi_symbol,
        binding.dot_stage_symbol,
        binding.sum_stage_symbol,
        binding.lassq_stage_symbol,
        binding.lassq_combine_stage_symbol,
        binding.lassq_finalize_symbol,
    )
    if any(
        (
            binding.abi_version != rtc.HIP_RTC_KRYLOV_PRIMITIVES_ABI_VERSION,
            binding.kernel_name != rtc.HIP_RTC_KRYLOV_PRIMITIVES_KERNEL_NAME,
            binding.vector_block_size != rtc.HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE,
            binding.reduction_segment_size != 512,
            actual_symbols != expected_symbols,
            not binding.source_resource.endswith(".hip.cpp"),
            architecture is not None and binding.architecture != architecture,
        )
    ):
        _fail("hip_krylov_primitives_kernel_binding_invalid", "/kernel")
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
        _fail("hip_krylov_primitives_kernel_binding_invalid", "/kernel/libraries")


def _evidence_scope(
    parent: HipFreeSpaceExecutionContext,
    kernel: Any,
    binding: HipKrylovPrimitivesKernelBinding,
    internally_compiled: bool,
) -> EvidenceScope:
    parent_binding = parent._kernel_binding
    native = (
        internally_compiled
        and parent._evidence_scope == "native_hiprtc_free_space_composite"
        and type(_loaded_runtime(parent)) is LoadedHipRuntime
        and type(kernel) is HipRtcKrylovPrimitivesKernel
        and binding.architecture == parent_binding.architecture
        and binding.runtime_library_sha256 == parent_binding.runtime_library_sha256
        and binding.runtime_library_discovery_source != "injected"
        and binding.hiprtc_library_discovery_source != "injected"
    )
    return (
        "native_hiprtc_krylov_primitives_composite"
        if native
        else "injected_test_double"
    )


def _bindings(
    parent: HipFreeSpaceExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    lease_epoch: int,
    internally_compiled: bool,
) -> HipKrylovPrimitivesBindings:
    plan = parent._plan
    state = parent._resident._state
    generation = source_apply.direction_generation
    if generation is None:
        _fail("hip_krylov_primitives_source_apply_generation_missing", "/source_apply")
    return HipKrylovPrimitivesBindings(
        parent.context_id,
        parent.opening_receipt.context_receipt_hash,
        source_apply.apply_id,
        source_apply.receipt_hash,
        source_apply.sequence,
        generation,
        plan.plan_hash,
        plan.operator_hash,
        plan.numeric_snapshot_hash,
        plan.partition_hash,
        state.state_hash,
        state.epoch,
        lease_epoch,
        "internally_compiled" if internally_compiled else "caller_supplied",
    )


def _dimensions(
    parent: HipFreeSpaceExecutionContext,
) -> HipKrylovPrimitivesDimensions:
    f = parent._overlay.free_dof_count
    return HipKrylovPrimitivesDimensions(
        f,
        parent._overlay.reduced_csr_nnz,
        512,
        max(1, (f + 511) // 512),
    )


def _claims(
    ready: bool,
    evidence_scope: EvidenceScope,
    *,
    lease_active: bool,
) -> HipKrylovPrimitivesClaims:
    return HipKrylovPrimitivesClaims(
        exclusive_parent_lease_active=lease_active,
        same_runtime_and_stream=lease_active,
        positive_jacobi_inverse_ready=ready,
        affine_primitive_ready=ready,
        dot_primitive_ready=ready,
        stable_l2_primitive_ready=ready,
        native_hiprtc_evidence=(
            ready and evidence_scope == "native_hiprtc_krylov_primitives_composite"
        ),
    )


def _trusted_jacobi_diagonal_status(
    parent: HipFreeSpaceExecutionContext,
) -> Literal["positive", "unsupported"]:
    """Classify the immutable CPU plan, never the mutable device allocation."""

    plan = parent._plan
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    return _classify_trusted_jacobi_diagonal(
        row_ptr, columns, values, parent._overlay.free_dof_count
    )


def _classify_trusted_jacobi_diagonal(
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    row_count: int,
) -> Literal["positive", "unsupported"]:
    for row in range(row_count):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        matches = np.flatnonzero(columns[begin:end] == row)
        if matches.size != 1:
            return "unsupported"
        diagonal = float(values[begin + int(matches[0])])
        if not np.isfinite(diagonal):
            _fail(
                "hip_krylov_primitives_trusted_numeric_corruption",
                f"/source_plan/diagonal/{row}",
            )
        if diagonal <= 0.0:
            return "unsupported"
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            reciprocal = np.float64(1.0) / np.float64(diagonal)
        if not np.isfinite(reciprocal):
            return "unsupported"
    return "positive"


def _context_id(
    parent: HipFreeSpaceExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    lease_epoch: int,
    binding: HipKrylovPrimitivesKernelBinding,
    evidence_scope: EvidenceScope,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE,
            "parent_context_id": parent.context_id,
            "source_apply_receipt_hash": source_apply.receipt_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": binding.identity_hash,
            "evidence_scope": evidence_scope,
        }
    )


def _fallback_context_id(
    parent: HipFreeSpaceExecutionContext,
    source_apply: HipFreeSpaceApplyReceipt,
    lease_epoch: int,
    binding: HipKrylovPrimitivesKernelBinding | None,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE,
            "parent_context_id": parent.context_id,
            "source_apply_receipt_hash": source_apply.receipt_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": (
                _ZERO_HASH if binding is None else binding.identity_hash
            ),
        }
    )


def _cpu_expected(
    context: HipKrylovPrimitivesExecutionContext,
) -> dict[str, np.ndarray]:
    plan = context._parent._plan
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    full_state = context._parent._resident._state.displacement_si
    residual_direction = -plan.residual(full_state)[free]
    reduced_jvp = _csr_matvec(row_ptr, columns, values, residual_direction)
    diagonal = np.empty(residual_direction.size, dtype="<f8")
    for row in range(diagonal.size):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        matches = np.flatnonzero(columns[begin:end] == row)
        if matches.size != 1:
            _fail(
                "hip_krylov_primitives_cpu_oracle_diagonal_invalid",
                f"/oracle/diagonal/{row}",
            )
        diagonal[row] = values[begin + int(matches[0])]
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0.0):
        _fail(
            "hip_krylov_primitives_cpu_oracle_diagonal_invalid",
            "/oracle/diagonal",
        )
    inverse = np.ascontiguousarray(1.0 / diagonal, dtype="<f8")
    preconditioned = np.ascontiguousarray(inverse * residual_direction, dtype="<f8")
    return {
        "jacobi_inverse": inverse,
        "work_x": np.ascontiguousarray(-0.5 * residual_direction, dtype="<f8"),
        "work_y": np.ascontiguousarray(0.25 * reduced_jvp + 0.25, dtype="<f8"),
        "preconditioned": preconditioned,
        "dot_result": np.asarray(
            [float(np.dot(residual_direction, preconditioned))], dtype="<f8"
        ),
        "norm_result": np.asarray([_stable_l2(residual_direction)], dtype="<f8"),
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


def _stable_l2(vector: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for raw in vector:
        value = abs(float(raw))
        if value == 0.0:
            continue
        if scale < value:
            ratio = 0.0 if scale == 0.0 else scale / value
            sumsq = 1.0 + sumsq * ratio * ratio
            scale = value
        else:
            ratio = value / scale
            sumsq += ratio * ratio
    return 0.0 if scale == 0.0 else scale * float(np.sqrt(sumsq))


def _metric(
    actual: np.ndarray, expected: np.ndarray
) -> HipKrylovPrimitivesParityMetric:
    count = int(actual.size)
    if count == 0:
        return HipKrylovPrimitivesParityMetric(0, 0.0, 0.0, 0.0, True)
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        return _failed_metric(count)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        signed_difference = actual - expected
        difference = np.abs(signed_difference)
    if not np.isfinite(difference).all():
        return _failed_metric(count)
    max_abs = float(np.max(difference))
    expected_norm = _stable_l2(expected)
    difference_norm = _stable_l2(signed_difference)
    if not np.isfinite(expected_norm) or not np.isfinite(difference_norm):
        return _failed_metric(count)
    relative_l2 = difference_norm / max(expected_norm, 1.0)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        scaled = difference / (
            _PARITY_TOLERANCE
            + _PARITY_TOLERANCE * np.maximum(np.abs(actual), np.abs(expected))
        )
    if not np.isfinite(scaled).all() or not np.isfinite(relative_l2):
        return _failed_metric(count)
    max_scaled = float(np.max(scaled))
    return HipKrylovPrimitivesParityMetric(
        count,
        max_abs,
        relative_l2,
        max_scaled,
        max_scaled <= 1.0,
    )


def _failed_metric(count: int) -> HipKrylovPrimitivesParityMetric:
    sentinel = float(np.finfo(np.float64).max)
    return HipKrylovPrimitivesParityMetric(count, sentinel, sentinel, sentinel, False)


def _parity(
    actual: dict[str, np.ndarray], expected: dict[str, np.ndarray]
) -> HipKrylovPrimitivesParityReport:
    metrics = {name: _metric(actual[name], expected[name]) for name in expected}
    return HipKrylovPrimitivesParityReport(
        metrics["jacobi_inverse"],
        metrics["work_x"],
        metrics["work_y"],
        metrics["preconditioned"],
        metrics["dot_result"],
        metrics["norm_result"],
        all(metric.passed for metric in metrics.values()),
    )


def _array_descriptor(
    array: np.ndarray,
) -> HipKrylovPrimitivesArrayDescriptor:
    return HipKrylovPrimitivesArrayDescriptor(
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
    reason: HipKrylovPrimitivesReason | None,
    bindings: HipKrylovPrimitivesBindings,
    kernel: HipKrylovPrimitivesKernelBinding | None,
    dimensions: HipKrylovPrimitivesDimensions,
    owned_buffers: tuple[HipKrylovPrimitivesBufferView, ...],
    allocation_lineage: HipKrylovPrimitivesAllocationLineage | None,
    telemetry: HipKrylovPrimitivesTelemetry,
    claims: HipKrylovPrimitivesClaims,
) -> HipKrylovPrimitivesContextReceipt:
    draft = HipKrylovPrimitivesContextReceipt(
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
    validate_hip_krylov_primitives_context_receipt(receipt)
    return receipt


def _batch_claims(
    delta: HipKrylovPrimitivesBatchDelta,
    dimensions: HipKrylovPrimitivesDimensions,
) -> HipKrylovPrimitivesBatchClaims:
    reduction_stages = _reduction_stage_count(dimensions.reduction_partial_count)
    return HipKrylovPrimitivesBatchClaims(
        fill_enqueued=delta.fill_launch_success_count == 1,
        affine_program_enqueued=delta.affine_launch_success_count == 2,
        jacobi_apply_enqueued=delta.jacobi_launch_success_count == 1,
        dot_reduction_enqueued=(
            delta.dot_stage_launch_success_count == 1
            and delta.sum_stage_launch_success_count == reduction_stages
        ),
        stable_l2_reduction_enqueued=(
            delta.lassq_stage_launch_success_count == 1
            and delta.lassq_combine_launch_success_count == reduction_stages
            and delta.lassq_finalize_launch_success_count == 1
        ),
    )


def _build_batch_receipt(
    *,
    status: BatchStatus,
    context: HipKrylovPrimitivesExecutionContext,
    sequence: int,
    delta: HipKrylovPrimitivesBatchDelta,
    reason: HipKrylovPrimitivesReason | None,
) -> HipKrylovPrimitivesBatchReceipt:
    batch_id = canonical_hash(
        {
            "context_id": context.context_id,
            "source_apply_receipt_hash": context._source_apply.receipt_hash,
            "sequence": sequence,
        }
    )
    draft = HipKrylovPrimitivesBatchReceipt(
        status,
        batch_id,
        context.context_id,
        context.opening_receipt.context_receipt_hash,
        context._source_apply.receipt_hash,
        sequence,
        context._evidence_scope,
        False,
        reason,
        delta,
        _batch_claims(delta, context._dimensions_snapshot),
        _ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_batch_payload(draft, include_hash=False)),
    )
    validate_hip_krylov_primitives_batch_receipt(receipt)
    return receipt


def _build_evaluation_receipt(
    *,
    status: EvaluationStatus,
    execution_id: str,
    context: HipKrylovPrimitivesExecutionContext,
    batch: HipKrylovPrimitivesBatchReceipt,
    arrays: dict[str, np.ndarray],
    delta: HipKrylovPrimitivesEvaluationDelta,
    parity: HipKrylovPrimitivesParityReport | None,
    reason: HipKrylovPrimitivesReason | None,
) -> HipKrylovPrimitivesEvaluationReceipt:
    descriptors = tuple(
        (name, _array_descriptor(array)) for name, array in arrays.items()
    )
    draft = HipKrylovPrimitivesEvaluationReceipt(
        status,
        execution_id,
        context.context_id,
        context.opening_receipt.context_receipt_hash,
        context._source_apply.receipt_hash,
        batch,
        context._evidence_scope,
        "hip"
        if context._evidence_scope == "native_hiprtc_krylov_primitives_composite"
        else "test_double",
        False,
        reason,
        descriptors,
        delta,
        parity,
        _ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_evaluation_payload(draft, include_hash=False)),
    )
    validate_hip_krylov_primitives_evaluation_receipt(receipt)
    return receipt


def _unavailable_evaluation(
    context: HipKrylovPrimitivesExecutionContext,
    execution_id: str,
    batch: HipKrylovPrimitivesBatchReceipt,
    delta: HipKrylovPrimitivesEvaluationDelta,
    code: str,
    detail: Any,
) -> HipKrylovPrimitivesEvaluation:
    receipt = _build_evaluation_receipt(
        status="unavailable",
        execution_id=execution_id,
        context=context,
        batch=batch,
        arrays={},
        delta=delta,
        parity=None,
        reason=HipKrylovPrimitivesReason(code, _detail(detail)),
    )
    return HipKrylovPrimitivesEvaluation(
        receipt, None, None, None, None, None, None, batch
    )


def _reduction_stage_count(partial_count: int) -> int:
    count = partial_count
    stages = 0
    while True:
        stages += 1
        count = reduction_output_count(count)
        if count == 1:
            return stages


def _context_payload(
    receipt: HipKrylovPrimitivesContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE,
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


def _batch_payload(
    receipt: HipKrylovPrimitivesBatchReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE,
        "status": receipt.status,
        "batch_id": receipt.batch_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "source_apply_receipt_hash": receipt.source_apply_receipt_hash,
        "sequence": receipt.sequence,
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
    receipt: HipKrylovPrimitivesEvaluationReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": HIP_KRYLOV_PRIMITIVES_CAPABILITY_PROFILE,
        "status": receipt.status,
        "execution_id": receipt.execution_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "source_apply_receipt_hash": receipt.source_apply_receipt_hash,
        "batch": None if receipt.batch is None else receipt.batch.to_dict(),
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


def validate_hip_krylov_primitives_context_receipt(
    receipt: HipKrylovPrimitivesContextReceipt,
    *,
    expected_context: HipKrylovPrimitivesExecutionContext | None = None,
) -> HipKrylovPrimitivesContextReceipt:
    if type(receipt) is not HipKrylovPrimitivesContextReceipt:
        _fail("hip_krylov_primitives_context_receipt_type_invalid", "/")
    nested_types = (
        (receipt.bindings, HipKrylovPrimitivesBindings, "/bindings"),
        (receipt.dimensions, HipKrylovPrimitivesDimensions, "/dimensions"),
        (receipt.telemetry, HipKrylovPrimitivesTelemetry, "/telemetry"),
        (receipt.claims, HipKrylovPrimitivesClaims, "/claims"),
    )
    for value, expected, path in nested_types:
        if type(value) is not expected:
            _fail("hip_krylov_primitives_context_nested_type_invalid", path)
    if (
        receipt.reason is not None
        and type(receipt.reason) is not HipKrylovPrimitivesReason
    ):
        _fail("hip_krylov_primitives_context_nested_type_invalid", "/reason")
    if (
        receipt.kernel is not None
        and type(receipt.kernel) is not HipKrylovPrimitivesKernelBinding
    ):
        _fail("hip_krylov_primitives_context_nested_type_invalid", "/kernel")
    if (
        receipt.allocation_lineage is not None
        and type(receipt.allocation_lineage) is not HipKrylovPrimitivesAllocationLineage
    ):
        _fail(
            "hip_krylov_primitives_context_nested_type_invalid",
            "/allocation_lineage",
        )
    if type(receipt.owned_buffers) is not tuple or any(
        type(view) is not HipKrylovPrimitivesBufferView
        for view in receipt.owned_buffers
    ):
        _fail("hip_krylov_primitives_context_nested_type_invalid", "/owned_buffers")
    payload = _context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema(), payload, "context")
    if receipt.context_receipt_hash != canonical_hash(
        _context_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_krylov_primitives_context_receipt_hash_mismatch",
            "/context_receipt_hash",
        )
    if _has_runtime_handle(payload):
        _fail("hip_krylov_primitives_runtime_handle_leak", "/")
    _require_hash(receipt.context_id, "/context_id")
    _require_hash(receipt.context_receipt_hash, "/context_receipt_hash")
    if type(receipt.promotion_eligible) is not bool or receipt.promotion_eligible:
        _fail("hip_krylov_primitives_context_promotion_invalid", "/promotion_eligible")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_krylov_primitives_context_claim_type_invalid", "/claims")
    broad = (
        "host_copy_zero_proven",
        "diagonal_shift_or_clamp_used",
        "spd_proven",
        "pcg_ready",
        "krylov_solver_ready",
        "preconditioner_integrated",
        "solver_iteration_ready",
        "asymptotic_o_n_proven",
        "speedup_proven",
        "commercial_ready",
        "fallback_used",
    )
    if any(getattr(receipt.claims, name) for name in broad):
        _fail("hip_krylov_primitives_context_claim_invalid", "/claims")
    binding = receipt.bindings
    for name in (
        "parent_context_id",
        "parent_opening_receipt_hash",
        "source_apply_id",
        "source_apply_receipt_hash",
        "source_execution_plan_hash",
        "source_operator_hash",
        "source_numeric_snapshot_hash",
        "source_partition_hash",
        "state_hash",
    ):
        _require_hash(getattr(binding, name), f"/bindings/{name}")
    for name in (
        "source_apply_sequence",
        "source_direction_generation",
        "state_epoch",
        "lease_epoch",
    ):
        value = getattr(binding, name)
        if type(value) is not int or value < 1:
            if name == "state_epoch" and value == 0:
                continue
            _fail("hip_krylov_primitives_context_binding_invalid", f"/bindings/{name}")
    dimensions = receipt.dimensions
    if any(
        type(getattr(dimensions, name)) is not int
        for name in dimensions.__dataclass_fields__
    ) or any(
        (
            dimensions.free_dof_count <= 0,
            dimensions.reduced_csr_nnz <= 0,
            dimensions.reduction_segment_size != 512,
            dimensions.reduction_partial_count
            != max(1, (dimensions.free_dof_count + 511) // 512),
            dimensions.borrowed_buffer_count != 5,
            dimensions.owned_buffer_count != 9,
        )
    ):
        _fail("hip_krylov_primitives_context_dimensions_invalid", "/dimensions")
    telemetry = receipt.telemetry
    if any(
        type(getattr(telemetry, name)) is not int or getattr(telemetry, name) < 0
        for name in telemetry.__dataclass_fields__
    ):
        _fail("hip_krylov_primitives_context_telemetry_invalid", "/telemetry")
    if any(
        (
            telemetry.allocation_success_count > telemetry.allocation_attempt_count,
            telemetry.allocation_success_count > len(_OWNED_ORDER),
            telemetry.allocation_attempt_count > len(_OWNED_ORDER),
            telemetry.allocation_attempt_count
            - telemetry.lineage_capability_mint_success_count
            > 1,
            telemetry.allocation_success_count
            - telemetry.lineage_capability_mint_success_count
            > 1,
            telemetry.deallocation_success_count > telemetry.deallocation_attempt_count,
            telemetry.deallocation_success_count > telemetry.allocation_success_count,
            telemetry.h2d_operation_success_count
            > telemetry.h2d_operation_attempt_count,
            telemetry.h2d_bytes_succeeded > telemetry.h2d_bytes_attempted,
            telemetry.d2h_operation_success_count
            > telemetry.d2h_operation_attempt_count,
            telemetry.d2h_bytes_succeeded > telemetry.d2h_bytes_attempted,
            telemetry.kernel_launch_success_count
            > telemetry.kernel_launch_attempt_count,
            telemetry.sync_success_count > telemetry.sync_attempt_count,
            telemetry.module_close_success_count > telemetry.module_close_attempt_count,
            telemetry.module_owner_acquired_count not in (0, 1),
            telemetry.module_close_success_count
            > telemetry.module_owner_acquired_count,
            telemetry.lease_release_success_count
            > telemetry.lease_release_attempt_count,
            telemetry.lease_release_success_count not in (0, 1),
            telemetry.lineage_owner_open_success_count not in (0, 1),
            telemetry.lineage_owner_close_success_count
            > telemetry.lineage_owner_open_success_count,
            telemetry.lineage_capability_mint_success_count
            > telemetry.allocation_success_count,
            telemetry.lineage_capability_mint_success_count > len(_OWNED_ORDER),
            telemetry.lineage_free_acknowledgement_count
            + telemetry.lineage_free_quarantine_count
            > telemetry.lineage_capability_mint_success_count,
            telemetry.lineage_orphan_acknowledgement_count
            + telemetry.lineage_orphan_quarantine_count
            > telemetry.allocation_attempt_count,
            telemetry.lineage_orphan_acknowledgement_count
            + telemetry.lineage_orphan_quarantine_count
            > 1,
            telemetry.unknown_malloc_outcome_count
            > telemetry.lineage_orphan_quarantine_count,
            telemetry.unknown_malloc_outcome_count == 0
            and telemetry.unknown_requested_bytes != 0,
            telemetry.unknown_malloc_outcome_count > 0
            and telemetry.unknown_requested_bytes == 0,
            telemetry.current_device_bytes > telemetry.peak_device_bytes,
            telemetry.quarantined_device_bytes > telemetry.current_device_bytes,
            telemetry.vector_h2d_bytes != 0,
            telemetry.reduction_h2d_bytes != 0,
            telemetry.new_stream_create_count != 0,
            telemetry.fallback_count != 0,
        )
    ):
        _fail("hip_krylov_primitives_context_telemetry_invalid", "/telemetry")
    if receipt.status in {
        "unavailable",
        "context_closed",
        "cleanup_quarantined",
    }:
        pointerful_orphan_count = (
            telemetry.lineage_orphan_acknowledgement_count
            + telemetry.lineage_orphan_quarantine_count
            - telemetry.unknown_malloc_outcome_count
        )
        if any(
            (
                pointerful_orphan_count < 0,
                telemetry.lineage_free_acknowledgement_count
                + telemetry.lineage_free_quarantine_count
                != telemetry.lineage_capability_mint_success_count,
                telemetry.deallocation_success_count
                != telemetry.lineage_free_acknowledgement_count
                + telemetry.lineage_orphan_acknowledgement_count,
                telemetry.allocation_success_count
                != telemetry.lineage_capability_mint_success_count
                + pointerful_orphan_count,
            )
        ):
            _fail(
                "hip_krylov_primitives_context_telemetry_conservation_invalid",
                "/telemetry",
            )
        _validate_allocation_byte_conservation(receipt)
        if receipt.status == "unavailable" or not receipt.owned_buffers:
            _validate_failed_open_operation_conservation(receipt)
    _validate_allocation_lineage_semantics(receipt)
    ready = receipt.status == "context_ready"
    active = receipt.status in ("context_ready", "poisoned", "cleanup_failed")
    expected_backend = (
        None
        if receipt.status == "unavailable"
        else (
            "hip"
            if receipt.evidence_scope == "native_hiprtc_krylov_primitives_composite"
            else "test_double"
        )
    )
    if receipt.actual_backend != expected_backend:
        _fail("hip_krylov_primitives_context_status_invalid", "/actual_backend")
    expected_claims = _claims(
        ready,
        receipt.evidence_scope,
        lease_active=active,
    )
    if receipt.claims != expected_claims:
        _fail("hip_krylov_primitives_context_claim_invalid", "/claims")
    if receipt.kernel is not None:
        _validate_kernel_binding(receipt.kernel)
        if telemetry.module_owner_acquired_count != 1:
            _fail(
                "hip_krylov_primitives_context_kernel_owner_invalid",
                "/telemetry",
            )
    if receipt.evidence_scope == "native_hiprtc_krylov_primitives_composite":
        if receipt.actual_backend not in ("hip", None) or (
            receipt.kernel is not None
            and (
                receipt.kernel.runtime_library_discovery_source == "injected"
                or receipt.kernel.hiprtc_library_discovery_source == "injected"
            )
        ):
            _fail("hip_krylov_primitives_native_evidence_invalid", "/evidence_scope")
    if receipt.status == "unavailable":
        if any(
            (
                receipt.reason is None,
                bool(receipt.owned_buffers),
                telemetry.current_device_bytes != 0,
                telemetry.deallocation_success_count
                != telemetry.allocation_success_count,
                telemetry.deallocation_attempt_count
                != telemetry.deallocation_success_count,
                telemetry.lineage_free_quarantine_count != 0,
                telemetry.lineage_orphan_quarantine_count != 0,
                telemetry.quarantined_device_bytes != 0,
                telemetry.unknown_malloc_outcome_count != 0,
                telemetry.unknown_requested_bytes != 0,
                telemetry.lineage_owner_close_success_count
                != telemetry.lineage_owner_open_success_count,
                telemetry.module_close_success_count
                != telemetry.module_owner_acquired_count,
                telemetry.module_close_attempt_count
                != telemetry.module_close_success_count,
                telemetry.lease_release_success_count != 1,
                telemetry.lease_release_attempt_count
                != telemetry.lease_release_success_count,
            )
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
        return receipt
    if receipt.status != "cleanup_quarantined" and len(receipt.owned_buffers) != 9:
        _fail("hip_krylov_primitives_context_status_invalid", "/owned_buffers")
    if receipt.owned_buffers:
        if len(receipt.owned_buffers) != 9:
            _fail("hip_krylov_primitives_context_status_invalid", "/owned_buffers")
        _validate_buffer_views(receipt)
    if ready or receipt.status == "poisoned":
        expected_bytes = sum(view.byte_length for view in receipt.owned_buffers)
        if any(
            (
                receipt.reason is not None if ready else receipt.reason is None,
                receipt.kernel is None,
                telemetry.allocation_attempt_count != len(_OWNED_ORDER),
                telemetry.allocation_success_count != 9,
                telemetry.lineage_owner_open_success_count != 1,
                telemetry.lineage_capability_mint_success_count != 9,
                telemetry.lineage_capability_mint_bytes != expected_bytes,
                telemetry.lineage_owner_close_success_count != 0,
                telemetry.lineage_free_acknowledgement_count != 0,
                telemetry.lineage_free_quarantine_count != 0,
                telemetry.lineage_orphan_acknowledgement_count != 0,
                telemetry.lineage_orphan_quarantine_count != 0,
                telemetry.quarantined_device_bytes != 0,
                telemetry.unknown_malloc_outcome_count != 0,
                telemetry.unknown_requested_bytes != 0,
                telemetry.current_device_bytes != expected_bytes,
                telemetry.peak_device_bytes != expected_bytes,
                telemetry.deallocation_attempt_count != 0,
                telemetry.module_close_attempt_count != 0,
                telemetry.lease_release_attempt_count != 0,
            )
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
    elif receipt.status == "context_closed":
        if any(
            (
                receipt.reason is not None,
                telemetry.current_device_bytes != 0,
                telemetry.deallocation_success_count
                != telemetry.allocation_success_count,
                telemetry.lineage_owner_close_success_count
                != telemetry.lineage_owner_open_success_count,
                telemetry.lineage_free_acknowledgement_count
                != telemetry.lineage_capability_mint_success_count,
                telemetry.lineage_free_quarantine_count != 0,
                telemetry.lineage_orphan_quarantine_count != 0,
                telemetry.quarantined_device_bytes != 0,
                telemetry.unknown_malloc_outcome_count != 0,
                telemetry.unknown_requested_bytes != 0,
                telemetry.module_close_success_count
                != telemetry.module_owner_acquired_count,
                telemetry.lease_release_success_count != 1,
            )
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
    elif receipt.status == "cleanup_failed":
        if receipt.reason is None or not (
            telemetry.current_device_bytes > 0
            or telemetry.module_close_success_count
            < telemetry.module_owner_acquired_count
            or telemetry.lease_release_success_count < 1
            or telemetry.lineage_owner_close_success_count
            < telemetry.lineage_owner_open_success_count
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
    elif receipt.status == "cleanup_quarantined":
        if any(
            (
                receipt.reason is None,
                telemetry.lineage_owner_open_success_count != 1,
                telemetry.lineage_owner_close_success_count != 1,
                telemetry.lineage_free_quarantine_count
                + telemetry.lineage_orphan_quarantine_count
                <= 0,
                telemetry.quarantined_device_bytes <= 0
                and telemetry.unknown_malloc_outcome_count <= 0,
                telemetry.current_device_bytes != telemetry.quarantined_device_bytes,
                telemetry.module_close_success_count
                != telemetry.module_owner_acquired_count,
                telemetry.lease_release_success_count != 1,
            )
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
        if not receipt.owned_buffers and any(
            (
                telemetry.deallocation_attempt_count
                > telemetry.allocation_success_count,
                telemetry.module_close_attempt_count
                != telemetry.module_close_success_count,
                telemetry.lease_release_attempt_count
                != telemetry.lease_release_success_count,
            )
        ):
            _fail("hip_krylov_primitives_context_status_invalid", "/status")
    if expected_context is not None:
        if type(expected_context) is not HipKrylovPrimitivesExecutionContext:
            _fail("hip_krylov_primitives_expected_context_type_invalid", "/")
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.bindings != expected_context._bindings_snapshot,
                receipt.dimensions != expected_context._dimensions_snapshot,
                receipt.evidence_scope != expected_context._evidence_scope,
                receipt.kernel != expected_context._kernel_binding,
                receipt.owned_buffers != expected_context._owned_buffers,
                receipt.allocation_lineage
                != expected_context._allocation_lineage_snapshot,
            )
        ):
            _fail("hip_krylov_primitives_context_witness_mismatch", "/context_id")
    return receipt


def _validate_allocation_lineage_semantics(
    receipt: HipKrylovPrimitivesContextReceipt,
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
                "hip_krylov_primitives_allocation_lineage_invalid",
                "/allocation_lineage",
            )
        return
    if lineage is None:
        _fail(
            "hip_krylov_primitives_allocation_lineage_invalid",
            "/allocation_lineage",
        )
    if any(
        (
            lineage.capability_profile != HIP_ALLOCATION_LINEAGE_CAPABILITY_PROFILE_V1,
            lineage.evidence_scope != HIP_ALLOCATION_LINEAGE_EVIDENCE_SCOPE_V1,
            lineage.owner_role != "krylov_primitives_owned_buffers",
            not lineage.runtime_device_bound,
            lineage.parent_borrowed_capability_count != len(_BORROWED_NAMES),
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
            "hip_krylov_primitives_allocation_lineage_invalid",
            "/allocation_lineage",
        )


def _validate_allocation_byte_conservation(
    receipt: HipKrylovPrimitivesContextReceipt,
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
            "hip_krylov_primitives_context_byte_conservation_invalid",
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
            "hip_krylov_primitives_context_byte_conservation_invalid",
            "/telemetry",
        )


def _validate_failed_open_operation_conservation(
    receipt: HipKrylovPrimitivesContextReceipt,
) -> None:
    telemetry = receipt.telemetry
    minted_count = telemetry.lineage_capability_mint_success_count
    h2d_states = {(0, 0, 0, 0, 0)}
    if minted_count == len(_OWNED_ORDER):
        h2d_states.update(
            {
                (1, 0, 4, 0, 4),
                (1, 1, 4, 4, 4),
            }
        )
    allowed: set[tuple[int, ...]] = set()
    for h2d_state in h2d_states:
        allowed.add((*h2d_state[:4], 0, 0, 0, 0, 0, 0, 0, 0, h2d_state[4], 0))
        if minted_count != len(_OWNED_ORDER) or h2d_state[1] != 1:
            continue
        allowed.update(
            {
                (*h2d_state[:4], 0, 0, 0, 0, 1, 0, 0, 0, h2d_state[4], 0),
                (*h2d_state[:4], 0, 0, 0, 0, 1, 1, 0, 0, h2d_state[4], 0),
                (*h2d_state[:4], 1, 0, 4, 0, 1, 1, 1, 0, h2d_state[4], 4),
                (*h2d_state[:4], 1, 1, 4, 4, 1, 1, 1, 0, h2d_state[4], 4),
                (*h2d_state[:4], 1, 1, 4, 4, 1, 1, 1, 1, h2d_state[4], 4),
            }
        )
    pointerful_resources = minted_count + (
        telemetry.lineage_orphan_acknowledgement_count
        + telemetry.lineage_orphan_quarantine_count
        - telemetry.unknown_malloc_outcome_count
    )
    if pointerful_resources:
        base_allowed = tuple(allowed)
        allowed = {
            signature[:10] + (signature[10] + 1, signature[11] + 1) + signature[12:]
            for signature in base_allowed
        }
        allowed.update(
            signature
            for signature in base_allowed
            if signature[11] == 1
            or (
                minted_count == 1
                and telemetry.lineage_orphan_acknowledgement_count
                + telemetry.lineage_orphan_quarantine_count
                == 0
            )
            or (
                minted_count == 0
                and telemetry.lineage_orphan_acknowledgement_count == 0
                and telemetry.lineage_orphan_quarantine_count == 1
                and telemetry.unknown_malloc_outcome_count == 0
            )
        )
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
        telemetry.error_flag_h2d_bytes,
        telemetry.error_flag_d2h_bytes,
    )
    if actual not in allowed:
        _fail(
            "hip_krylov_primitives_context_operation_conservation_invalid",
            "/telemetry",
        )


def _lineage_buffer_byte_lengths(
    dimensions: HipKrylovPrimitivesDimensions,
) -> tuple[int, ...]:
    free = dimensions.free_dof_count
    partials = dimensions.reduction_partial_count
    return (
        8 * free,
        8 * free,
        8 * free,
        8 * free,
        16 * partials,
        16 * partials,
        8,
        8,
        4,
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


def _validate_buffer_views(receipt: HipKrylovPrimitivesContextReceipt) -> None:
    if not receipt.owned_buffers:
        return
    f = receipt.dimensions.free_dof_count
    p = receipt.dimensions.reduction_partial_count
    expected = (
        ("jacobi_inverse", "<f8", (f,), 8 * f, None),
        ("work_x", "<f8", (f,), 8 * f, None),
        ("work_y", "<f8", (f,), 8 * f, None),
        ("preconditioned", "<f8", (f,), 8 * f, None),
        ("reduction_ping", "<f8", (2 * p,), 16 * p, None),
        ("reduction_pong", "<f8", (2 * p,), 16 * p, None),
        ("dot_result", "<f8", (1,), 8, None),
        ("norm_result", "<f8", (1,), 8, None),
        ("error_flag", "<i4", (1,), 4, _ZERO_I32_DATA_HASH),
    )
    actual = tuple(
        (view.name, view.dtype, view.shape, view.byte_length, view.data_hash)
        for view in receipt.owned_buffers
    )
    if actual != expected:
        _fail(
            "hip_krylov_primitives_context_buffer_semantics_invalid", "/owned_buffers"
        )


def validate_hip_krylov_primitives_batch_receipt(
    receipt: HipKrylovPrimitivesBatchReceipt,
    *,
    expected_context: HipKrylovPrimitivesExecutionContext | None = None,
) -> HipKrylovPrimitivesBatchReceipt:
    if type(receipt) is not HipKrylovPrimitivesBatchReceipt:
        _fail("hip_krylov_primitives_batch_receipt_type_invalid", "/")
    if (
        type(receipt.telemetry_delta) is not HipKrylovPrimitivesBatchDelta
        or type(receipt.claims) is not HipKrylovPrimitivesBatchClaims
    ):
        _fail("hip_krylov_primitives_batch_nested_type_invalid", "/")
    if (
        receipt.reason is not None
        and type(receipt.reason) is not HipKrylovPrimitivesReason
    ):
        _fail("hip_krylov_primitives_batch_nested_type_invalid", "/reason")
    payload = _batch_payload(receipt, include_hash=True)
    _validate_schema(_batch_schema(), payload, "batch")
    if receipt.receipt_hash != canonical_hash(
        _batch_payload(receipt, include_hash=False)
    ):
        _fail("hip_krylov_primitives_batch_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_handle(payload):
        _fail("hip_krylov_primitives_runtime_handle_leak", "/")
    for value, path in (
        (receipt.batch_id, "/batch_id"),
        (receipt.context_id, "/context_id"),
        (receipt.opening_context_receipt_hash, "/opening_context_receipt_hash"),
        (receipt.source_apply_receipt_hash, "/source_apply_receipt_hash"),
        (receipt.receipt_hash, "/receipt_hash"),
    ):
        _require_hash(value, path)
    if type(receipt.sequence) is not int or receipt.sequence < 1:
        _fail("hip_krylov_primitives_batch_sequence_invalid", "/sequence")
    delta = receipt.telemetry_delta
    if any(
        type(getattr(delta, name)) is not int or getattr(delta, name) < 0
        for name in delta.__dataclass_fields__
    ):
        _fail("hip_krylov_primitives_batch_delta_invalid", "/telemetry_delta")
    pairs = (
        ("fill_launch_attempt_count", "fill_launch_success_count", 1),
        ("affine_launch_attempt_count", "affine_launch_success_count", 2),
        ("jacobi_launch_attempt_count", "jacobi_launch_success_count", 1),
        ("dot_stage_launch_attempt_count", "dot_stage_launch_success_count", 1),
        ("sum_stage_launch_attempt_count", "sum_stage_launch_success_count", None),
        ("lassq_stage_launch_attempt_count", "lassq_stage_launch_success_count", 1),
        (
            "lassq_combine_launch_attempt_count",
            "lassq_combine_launch_success_count",
            None,
        ),
        (
            "lassq_finalize_launch_attempt_count",
            "lassq_finalize_launch_success_count",
            1,
        ),
    )
    for attempt_name, success_name, maximum in pairs:
        attempt = getattr(delta, attempt_name)
        success = getattr(delta, success_name)
        if success > attempt or (maximum is not None and attempt > maximum):
            _fail("hip_krylov_primitives_batch_delta_invalid", "/telemetry_delta")
    if any(
        (
            receipt.promotion_eligible,
            delta.h2d_operation_count != 0,
            delta.d2h_operation_count != 0,
            delta.allocation_count != 0,
            delta.sync_count != 0,
            delta.fallback_count != 0,
        )
    ):
        _fail("hip_krylov_primitives_batch_delta_invalid", "/telemetry_delta")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ) or any(
        (
            receipt.claims.completion_fence_observed,
            receipt.claims.solver_iteration,
            receipt.claims.pcg_iteration,
            receipt.claims.fallback_used,
        )
    ):
        _fail("hip_krylov_primitives_batch_claim_invalid", "/claims")

    planned = None
    if expected_context is not None:
        planned = _reduction_stage_count(
            expected_context._dimensions_snapshot.reduction_partial_count
        )
        if (
            delta.sum_stage_launch_attempt_count > planned
            or delta.lassq_combine_launch_attempt_count > planned
        ):
            _fail("hip_krylov_primitives_batch_delta_invalid", "/telemetry_delta")
        expected_claims = _batch_claims(delta, expected_context._dimensions_snapshot)
    else:
        expected_claims = HipKrylovPrimitivesBatchClaims(
            delta.fill_launch_success_count == 1,
            delta.affine_launch_success_count == 2,
            delta.jacobi_launch_success_count == 1,
            delta.dot_stage_launch_success_count == 1
            and delta.sum_stage_launch_attempt_count >= 1
            and delta.sum_stage_launch_attempt_count
            == delta.sum_stage_launch_success_count,
            delta.lassq_stage_launch_success_count == 1
            and delta.lassq_combine_launch_attempt_count >= 1
            and delta.lassq_combine_launch_attempt_count
            == delta.lassq_combine_launch_success_count
            and delta.lassq_finalize_launch_success_count == 1,
        )
    if receipt.claims != expected_claims:
        _fail("hip_krylov_primitives_batch_claim_invalid", "/claims")
    if delta.fill_launch_attempt_count != 1:
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    ordered_prefix = delta.fill_launch_success_count == 1 or all(
        getattr(delta, name) == 0
        for name in delta.__dataclass_fields__
        if name.startswith(("affine_", "jacobi_", "dot_", "sum_", "lassq_"))
    )
    if not ordered_prefix:
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if delta.affine_launch_success_count < 2 and any(
        getattr(delta, name) != 0
        for name in delta.__dataclass_fields__
        if name.startswith(("jacobi_", "dot_", "sum_", "lassq_"))
    ):
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if delta.jacobi_launch_success_count == 0 and any(
        getattr(delta, name) != 0
        for name in delta.__dataclass_fields__
        if name.startswith(("dot_", "sum_", "lassq_"))
    ):
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if delta.dot_stage_launch_success_count == 0 and any(
        getattr(delta, name) != 0
        for name in delta.__dataclass_fields__
        if name.startswith(("sum_", "lassq_"))
    ):
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if delta.lassq_stage_launch_attempt_count and (
        delta.sum_stage_launch_attempt_count == 0
        or delta.sum_stage_launch_attempt_count != delta.sum_stage_launch_success_count
    ):
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if delta.lassq_finalize_launch_attempt_count and (
        delta.lassq_combine_launch_attempt_count == 0
        or delta.lassq_combine_launch_attempt_count
        != delta.lassq_combine_launch_success_count
    ):
        _fail("hip_krylov_primitives_batch_stage_order_invalid", "/telemetry_delta")
    if planned is not None:
        if delta.lassq_stage_launch_attempt_count:
            if (
                delta.sum_stage_launch_attempt_count != planned
                or delta.sum_stage_launch_success_count != planned
            ):
                _fail(
                    "hip_krylov_primitives_batch_stage_order_invalid",
                    "/telemetry_delta/sum_stage",
                )
        elif delta.sum_stage_launch_success_count < planned and (
            delta.sum_stage_launch_attempt_count
            != delta.sum_stage_launch_success_count + 1
        ):
            _fail(
                "hip_krylov_primitives_batch_stage_order_invalid",
                "/telemetry_delta/sum_stage",
            )
        if delta.lassq_finalize_launch_attempt_count:
            if (
                delta.lassq_combine_launch_attempt_count != planned
                or delta.lassq_combine_launch_success_count != planned
            ):
                _fail(
                    "hip_krylov_primitives_batch_stage_order_invalid",
                    "/telemetry_delta/lassq_combine",
                )
        elif (
            delta.lassq_combine_launch_attempt_count
            and delta.lassq_combine_launch_success_count < planned
            and delta.lassq_combine_launch_attempt_count
            != delta.lassq_combine_launch_success_count + 1
        ):
            _fail(
                "hip_krylov_primitives_batch_stage_order_invalid",
                "/telemetry_delta/lassq_combine",
            )
    complete = all(
        (
            delta.fill_launch_success_count == 1,
            delta.affine_launch_success_count == 2,
            delta.jacobi_launch_success_count == 1,
            delta.dot_stage_launch_success_count == 1,
            delta.sum_stage_launch_success_count
            == (
                planned if planned is not None else delta.sum_stage_launch_attempt_count
            ),
            delta.sum_stage_launch_success_count >= 1,
            delta.lassq_stage_launch_success_count == 1,
            delta.lassq_combine_launch_success_count
            == (
                planned
                if planned is not None
                else delta.lassq_combine_launch_attempt_count
            ),
            delta.lassq_combine_launch_success_count >= 1,
            delta.lassq_finalize_launch_success_count == 1,
        )
    )
    if receipt.status == "enqueued":
        if (
            receipt.reason is not None
            or not complete
            or not all(
                (
                    receipt.claims.fill_enqueued,
                    receipt.claims.affine_program_enqueued,
                    receipt.claims.jacobi_apply_enqueued,
                    receipt.claims.dot_reduction_enqueued,
                    receipt.claims.stable_l2_reduction_enqueued,
                )
            )
        ):
            _fail("hip_krylov_primitives_batch_status_invalid", "/status")
    elif receipt.reason is None or complete:
        _fail("hip_krylov_primitives_batch_status_invalid", "/status")
    expected_id = canonical_hash(
        {
            "context_id": receipt.context_id,
            "source_apply_receipt_hash": receipt.source_apply_receipt_hash,
            "sequence": receipt.sequence,
        }
    )
    if receipt.batch_id != expected_id:
        _fail("hip_krylov_primitives_batch_id_mismatch", "/batch_id")
    if expected_context is not None:
        witness = expected_context._batch_witnesses.get(receipt.sequence)
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.opening_context_receipt_hash
                != expected_context.opening_receipt.context_receipt_hash,
                receipt.source_apply_receipt_hash
                != expected_context._source_apply.receipt_hash,
                receipt.evidence_scope != expected_context._evidence_scope,
                witness is None,
                witness != receipt.receipt_hash,
            )
        ):
            _fail("hip_krylov_primitives_batch_witness_mismatch", "/context_id")
    return receipt


def validate_hip_krylov_primitives_evaluation_receipt(
    receipt: HipKrylovPrimitivesEvaluationReceipt,
    *,
    expected_context: HipKrylovPrimitivesExecutionContext | None = None,
) -> HipKrylovPrimitivesEvaluationReceipt:
    if type(receipt) is not HipKrylovPrimitivesEvaluationReceipt:
        _fail("hip_krylov_primitives_evaluation_receipt_type_invalid", "/")
    if type(receipt.telemetry_delta) is not HipKrylovPrimitivesEvaluationDelta:
        _fail(
            "hip_krylov_primitives_evaluation_nested_type_invalid", "/telemetry_delta"
        )
    if (
        receipt.reason is not None
        and type(receipt.reason) is not HipKrylovPrimitivesReason
    ):
        _fail("hip_krylov_primitives_evaluation_nested_type_invalid", "/reason")
    if receipt.batch is None:
        _fail("hip_krylov_primitives_evaluation_batch_missing", "/batch")
    validate_hip_krylov_primitives_batch_receipt(
        receipt.batch, expected_context=expected_context
    )
    if receipt.parity is not None:
        _validate_parity_type(receipt.parity)
    if type(receipt.arrays) is not tuple or any(
        type(row) is not tuple
        or len(row) != 2
        or type(row[0]) is not str
        or type(row[1]) is not HipKrylovPrimitivesArrayDescriptor
        for row in receipt.arrays
    ):
        _fail("hip_krylov_primitives_evaluation_nested_type_invalid", "/arrays")
    payload = _evaluation_payload(receipt, include_hash=True)
    _validate_schema(_evaluation_schema(), payload, "evaluation")
    if receipt.receipt_hash != canonical_hash(
        _evaluation_payload(receipt, include_hash=False)
    ):
        _fail("hip_krylov_primitives_evaluation_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_handle(payload):
        _fail("hip_krylov_primitives_runtime_handle_leak", "/")
    for value, path in (
        (receipt.execution_id, "/execution_id"),
        (receipt.context_id, "/context_id"),
        (receipt.opening_context_receipt_hash, "/opening_context_receipt_hash"),
        (receipt.source_apply_receipt_hash, "/source_apply_receipt_hash"),
        (receipt.receipt_hash, "/receipt_hash"),
    ):
        _require_hash(value, path)
    expected_execution_id = canonical_hash(
        {
            "context_id": receipt.context_id,
            "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
            "batch_receipt_hash": receipt.batch.receipt_hash,
        }
    )
    if receipt.execution_id != expected_execution_id:
        _fail(
            "hip_krylov_primitives_evaluation_execution_id_mismatch",
            "/execution_id",
        )
    expected_backend = (
        "hip"
        if receipt.evidence_scope == "native_hiprtc_krylov_primitives_composite"
        else "test_double"
    )
    if receipt.actual_backend != expected_backend:
        _fail(
            "hip_krylov_primitives_evaluation_backend_mismatch",
            "/actual_backend",
        )
    delta = receipt.telemetry_delta
    if any(
        type(getattr(delta, name)) is not int or getattr(delta, name) < 0
        for name in delta.__dataclass_fields__
    ) or any(
        (
            delta.d2h_operation_success_count > delta.d2h_operation_attempt_count,
            delta.d2h_bytes_succeeded > delta.d2h_bytes_attempted,
            delta.sync_success_count > delta.sync_attempt_count,
            delta.allocation_count != 0,
            delta.h2d_operation_count != 0,
            delta.fallback_count != 0,
            receipt.promotion_eligible,
        )
    ):
        _fail("hip_krylov_primitives_evaluation_delta_invalid", "/telemetry_delta")
    names = tuple(name for name, _ in receipt.arrays)
    if len(set(names)) != len(names):
        _fail("hip_krylov_primitives_evaluation_array_invalid", "/arrays")
    expected_names = (
        "jacobi_inverse",
        "work_x",
        "work_y",
        "preconditioned",
        "dot_result",
        "norm_result",
    )
    if receipt.status in ("verified", "parity_failed"):
        if (
            receipt.reason is not None
            or receipt.batch is None
            or receipt.batch.status != "enqueued"
            or names != expected_names
            or receipt.parity is None
            or delta.d2h_operation_attempt_count != 7
            or delta.d2h_operation_success_count != 7
            or delta.sync_attempt_count != 1
            or delta.sync_success_count != 1
        ):
            _fail("hip_krylov_primitives_evaluation_status_invalid", "/status")
        if receipt.parity.passed != (receipt.status == "verified"):
            _fail("hip_krylov_primitives_evaluation_status_invalid", "/parity")
        descriptor_map = dict(receipt.arrays)
        f_shape = descriptor_map["jacobi_inverse"].shape
        if len(f_shape) != 1:
            _fail("hip_krylov_primitives_evaluation_array_invalid", "/arrays")
        f = f_shape[0]
        expected_shapes = {
            "jacobi_inverse": (f,),
            "work_x": (f,),
            "work_y": (f,),
            "preconditioned": (f,),
            "dot_result": (1,),
            "norm_result": (1,),
        }
        for name, descriptor in receipt.arrays:
            if (
                descriptor.dtype != "<f8"
                or descriptor.shape != expected_shapes[name]
                or descriptor.byte_length != 8 * expected_shapes[name][0]
            ):
                _fail(
                    "hip_krylov_primitives_evaluation_array_invalid",
                    f"/arrays/{name}",
                )
            _require_hash(descriptor.data_hash, f"/arrays/{name}/data_hash")
        expected_bytes = 32 * f + 20
        if (
            delta.d2h_bytes_attempted != expected_bytes
            or delta.d2h_bytes_succeeded != expected_bytes
        ):
            _fail(
                "hip_krylov_primitives_evaluation_delta_invalid",
                "/telemetry_delta",
            )
        assert receipt.parity is not None
        metric_counts = (
            receipt.parity.jacobi_inverse.count,
            receipt.parity.work_x.count,
            receipt.parity.work_y.count,
            receipt.parity.preconditioned.count,
            receipt.parity.dot_result.count,
            receipt.parity.norm_result.count,
        )
        if metric_counts != (f, f, f, f, 1, 1):
            _fail("hip_krylov_primitives_parity_metric_invalid", "/parity/metrics")
    else:
        if receipt.reason is None or receipt.arrays or receipt.parity is not None:
            _fail("hip_krylov_primitives_evaluation_status_invalid", "/status")
    if expected_context is not None:
        f = expected_context._dimensions_snapshot.free_dof_count
        if receipt.status in ("verified", "parity_failed") and dict(receipt.arrays)[
            "jacobi_inverse"
        ].shape != (f,):
            _fail("hip_krylov_primitives_evaluation_array_invalid", "/arrays")
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.opening_context_receipt_hash
                != expected_context.opening_receipt.context_receipt_hash,
                receipt.source_apply_receipt_hash
                != expected_context._source_apply.receipt_hash,
                receipt.evidence_scope != expected_context._evidence_scope,
            )
        ):
            _fail("hip_krylov_primitives_evaluation_witness_mismatch", "/context_id")
    return receipt


def validate_hip_krylov_primitives_evaluation(
    evaluation: HipKrylovPrimitivesEvaluation,
    *,
    expected_context: HipKrylovPrimitivesExecutionContext | None = None,
) -> HipKrylovPrimitivesEvaluation:
    if type(evaluation) is not HipKrylovPrimitivesEvaluation:
        _fail("hip_krylov_primitives_evaluation_type_invalid", "/")
    validate_hip_krylov_primitives_evaluation_receipt(
        evaluation.receipt, expected_context=expected_context
    )
    if evaluation.batch is not evaluation.receipt.batch:
        _fail("hip_krylov_primitives_evaluation_batch_alias_invalid", "/batch")
    values = (
        ("jacobi_inverse", evaluation.jacobi_inverse),
        ("work_x", evaluation.work_x),
        ("work_y", evaluation.work_y),
        ("preconditioned", evaluation.preconditioned),
        ("dot_result", evaluation.dot_result),
        ("norm_result", evaluation.norm_result),
    )
    if evaluation.receipt.status == "unavailable":
        if any(value is not None for _, value in values):
            _fail("hip_krylov_primitives_evaluation_array_invalid", "/arrays")
        return evaluation
    if expected_context is None:
        _fail(
            "hip_krylov_primitives_evaluation_context_required",
            "/expected_context",
            "A live context is required to recompute successful evaluation parity.",
        )
    descriptors = dict(evaluation.receipt.arrays)
    for name, value in values:
        if type(value) is not np.ndarray:
            _fail("hip_krylov_primitives_evaluation_array_invalid", f"/{name}")
        assert value is not None
        if (
            value.dtype.str != "<f8"
            or value.ndim != 1
            or value.flags.writeable
            or not value.flags.c_contiguous
            or not np.isfinite(value).all()
            or _array_descriptor(value) != descriptors[name]
        ):
            _fail("hip_krylov_primitives_evaluation_array_invalid", f"/{name}")
    if expected_context is not None:
        actual = {name: value for name, value in values if value is not None}
        recomputed = _parity(actual, _cpu_expected(expected_context))
        if evaluation.receipt.parity != recomputed:
            _fail("hip_krylov_primitives_parity_witness_mismatch", "/receipt/parity")
    if expected_context is not None:
        f = expected_context._dimensions_snapshot.free_dof_count
        if any(
            (
                evaluation.jacobi_inverse.shape != (f,),
                evaluation.work_x.shape != (f,),
                evaluation.work_y.shape != (f,),
                evaluation.preconditioned.shape != (f,),
                evaluation.dot_result.shape != (1,),
                evaluation.norm_result.shape != (1,),
            )
        ):
            _fail("hip_krylov_primitives_evaluation_array_invalid", "/arrays")
    return evaluation


def _validate_parity_type(report: HipKrylovPrimitivesParityReport) -> None:
    if (
        type(report) is not HipKrylovPrimitivesParityReport
        or type(report.passed) is not bool
    ):
        _fail("hip_krylov_primitives_parity_type_invalid", "/parity")
    metrics = (
        report.jacobi_inverse,
        report.work_x,
        report.work_y,
        report.preconditioned,
        report.dot_result,
        report.norm_result,
    )
    for metric in metrics:
        if type(metric) is not HipKrylovPrimitivesParityMetric:
            _fail("hip_krylov_primitives_parity_type_invalid", "/parity/metrics")
        if (
            type(metric.count) is not int
            or metric.count < 0
            or type(metric.passed) is not bool
            or type(metric.max_abs_error) is not float
            or type(metric.relative_l2_error) is not float
            or type(metric.max_scaled_error) is not float
            or not np.isfinite(metric.max_abs_error)
            or not np.isfinite(metric.relative_l2_error)
            or not np.isfinite(metric.max_scaled_error)
            or metric.max_abs_error < 0.0
            or metric.relative_l2_error < 0.0
            or metric.max_scaled_error < 0.0
            or metric.passed != (metric.max_scaled_error <= 1.0)
        ):
            _fail("hip_krylov_primitives_parity_metric_invalid", "/parity/metrics")
    if report.passed != all(metric.passed for metric in metrics):
        _fail("hip_krylov_primitives_parity_invalid", "/parity/passed")


@lru_cache(maxsize=1)
def _context_schema() -> dict[str, Any]:
    return _load_schema("hip_krylov_primitives_context_v2.schema.json")


@lru_cache(maxsize=1)
def _batch_schema() -> dict[str, Any]:
    return _load_schema("hip_krylov_primitives_batch_v1.schema.json")


@lru_cache(maxsize=1)
def _evaluation_schema() -> dict[str, Any]:
    return _load_schema("hip_krylov_primitives_evaluation_v1.schema.json")


def _load_schema(name: str) -> dict[str, Any]:
    path = Path(__file__).parents[2] / "schemas" / name
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def _validate_schema(
    schema: dict[str, Any], payload: dict[str, Any], label: str
) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(
            f"hip_krylov_primitives_{label}_schema_invalid",
            path or "/",
            error.message,
        )


def _has_runtime_handle(value: Any, key: str = "") -> bool:
    lowered = key.lower()
    suspicious = lowered in {
        "pointer",
        "handle",
        "stream",
        "module",
        "function",
    } or lowered.endswith(("_pointer", "_handle", "_address"))
    if suspicious and isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return any(_has_runtime_handle(item, str(name)) for name, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_runtime_handle(item, key) for item in value)
    if isinstance(value, str):
        return bool(
            _HEX_ADDRESS_PATTERN.search(value) or _DECIMAL_HANDLE_PATTERN.search(value)
        )
    return False


def _require_hash(value: Any, path: str) -> None:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hip_krylov_primitives_hash_invalid", path)


def _detail(value: Any) -> str:
    text = str(value)
    text = _HEX_ADDRESS_PATTERN.sub("<redacted-address>", text)
    text = _DECIMAL_HANDLE_PATTERN.sub("<redacted-handle>", text)
    text = " ".join(text.split())
    return text[:512] or "unspecified"


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipKrylovPrimitivesContextError(code, path, _detail(message or code))
