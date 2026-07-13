"""HIPRTC device element/material assembly context for Engine v2.

The context reuses the Phase 0 :class:`DeviceExecutionContext` model-buffer
residency foundation.  It uploads only sparse symbolic inputs, executes one
fixed frame/truss contribution kernel followed by one deterministic segmented
gather kernel, and retains the resulting CSR values on the device.  Host CSR
numeric values are never uploaded.  An optional download is a verification
oracle only and can never become a fallback execution path.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.hip.context import (
    DeviceExecutionContext,
    open_device_execution_context,
)
from structural_analysis.engine_v2.backends.hip.native import (
    LoadedHipRuntime,
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.buffers import (
    SolverModelBuffers,
    validate_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    _detached_source_snapshot,
    validate_execution_plan_v2,
)

from .plan import (
    HipAssemblyPlanV1,
    validate_hip_assembly_plan_v1,
)
from .rtc import (
    HIP_RTC_CSR_GATHER_BLOCK_SIZE,
    HIP_RTC_CSR_GATHER_SYMBOL,
    HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE,
    HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
    HIP_RTC_LINEAR_ASSEMBLY_IDENTITY_SCHEMA_VERSION,
    HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION,
    HIP_RTC_LINEAR_ASSEMBLY_KERNEL_NAME,
    HipRtcAssemblyError,
    HipRtcLinearFrameTrussAssemblyKernel,
    _fixed_source,
    compile_hip_rtc_linear_frame_truss_assembly_kernel,
)

HIP_ASSEMBLY_CONTEXT_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-assembly-context-receipt.v1"
)
HIP_ASSEMBLY_EVALUATION_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-assembly-evaluation-receipt.v1"
)
HIP_ASSEMBLY_CAPABILITY_PROFILE = "phase0_hiprtc_linear_frame_truss_device_assembly"

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_HEX_ADDRESS_PATTERN = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_RUNTIME_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:pointer|address|stream|handle|module|function)\b"
    r"\s*(?:[:=]\s*)?(?:0x[0-9a-f]+|[0-9]+)"
)
_PARITY_TOLERANCE = 1.0e-8
_CHILD_BUFFER_ORDER = (
    "csr_row_ptr",
    "csr_column_indices",
    "reference_axis_code",
    "reverse_segment_offsets",
    "reverse_contribution_indices",
    "element_contributions",
    "csr_values",
    "error_flag",
)
_INITIAL_UPLOAD_NAMES = frozenset(
    {
        "csr_row_ptr",
        "csr_column_indices",
        "reference_axis_code",
        "reverse_segment_offsets",
        "reverse_contribution_indices",
        "error_flag",
    }
)
_FORBIDDEN_RUNTIME_KEYS = (
    "pointer",
    "address",
    "stream",
    "handle",
    "module",
    "function",
)

ContextStatus = Literal[
    "context_ready",
    "poisoned",
    "cleanup_failed",
    "context_closed",
    "unavailable",
]
EvaluationStatus = Literal[
    "verified",
    "assembled_unverified",
    "parity_failed",
    "unavailable",
]
EvidenceScope = Literal["native_hiprtc", "injected_test_double"]


class HipAssemblyContextError(RuntimeError):
    """Fail-closed assembly-context error with a stable code and path."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str,
        *,
        cleanup_owner: Any | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class HipAssemblyReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipAssemblyBindings:
    model_ir_content_hash: str
    solver_artifact_hash: str
    solver_numeric_buffer_hash: str
    source_execution_plan_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_symbolic_reuse_hash: str
    source_partition_hash: str
    assembly_plan_hash: str
    assembly_symbolic_payload_hash: str
    axis_policy_hash: str
    reverse_map_hash: str
    kernel_identity_hash: str
    device_ordinal: int
    load_pattern_id: str
    verification_requested: bool
    host_csr_values_role: Literal["verification_oracle_only_never_uploaded"] = (
        "verification_oracle_only_never_uploaded"
    )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyKernelBinding:
    abi_version: int
    element_kernel_symbol: str
    gather_kernel_symbol: str
    element_block_size: int
    gather_block_size: int
    architecture: str
    source_resource: str
    source_sha256: str
    code_object_sha256: str
    identity_hash: str
    identity_snapshot_hash: str
    runtime_library_discovery_source: str
    runtime_library_sha256: str
    hiprtc_library_discovery_source: str
    hiprtc_library_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyDevice:
    ordinal: int
    name: str
    architecture: str
    runtime_version_raw: int
    driver_version_raw: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyDimensions:
    node_count: int
    element_count: int
    material_count: int
    section_count: int
    global_dof_count: int
    csr_nnz: int
    contribution_count: int
    foundation_buffer_count: int
    foundation_payload_bytes: int

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyBufferView:
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
class _HipAssemblyChildSpec:
    """Allocation metadata; output-only device buffers have no host backing."""

    dtype: str
    shape: tuple[int, ...]
    byte_length: int
    host_backing: np.ndarray | None
    access: str
    initial_transfer: str


@dataclass(frozen=True, slots=True)
class HipAssemblyTelemetry:
    h2d_bytes: int = 0
    d2h_bytes: int = 0
    h2d_operation_count: int = 0
    d2h_operation_count: int = 0
    d2h_operation_attempt_count: int = 0
    d2h_operation_success_count: int = 0
    d2h_bytes_attempted: int = 0
    d2h_bytes_succeeded: int = 0
    blocking_copy_count: int = 0
    explicit_sync_count: int = 0
    allocation_count: int = 0
    deallocation_count: int = 0
    current_device_payload_bytes: int = 0
    peak_device_payload_bytes: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_count: int = 0
    fallback_count: int = 0
    child_allocation_attempt_count: int = 0
    child_allocation_success_count: int = 0
    child_deallocation_attempt_count: int = 0
    child_deallocation_success_count: int = 0
    child_initial_h2d_attempt_count: int = 0
    child_initial_h2d_success_count: int = 0
    assembly_sync_count: int = 0
    assembly_sync_attempt_count: int = 0
    assembly_sync_success_count: int = 0
    error_flag_d2h_bytes: int = 0
    verification_csr_d2h_bytes: int = 0
    host_csr_values_h2d_bytes: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyClaims:
    device_element_contributions_executed: bool
    device_segmented_gather_executed: bool
    device_csr_operator_resident: bool
    cpu_reference_parity_verified: bool
    native_hiprtc_kernel_loaded: bool
    solver_ready: Literal[False] = False
    device_resident_krylov_ready: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipAssemblyOperatorView:
    """Serializable metadata for a process-local context-owned CSR value view.

    The live allocation is deliberately reachable only through the owning
    context.  No device address or runtime object can enter this value.
    """

    context_id: str
    operator_id: str
    source_execution_plan_hash: str
    assembly_plan_hash: str
    kernel_identity_hash: str
    dtype: Literal["<f8"]
    shape: tuple[int]
    byte_length: int
    csr_nnz: int
    device_ordinal: int
    memory_space: Literal["hip_device"]
    access: Literal["read_only_after_assembly"]
    lifetime: Literal["context_owned_process_local"]
    ordering_domain: Literal["context_serial_queue"]
    verification_data_hash: str | None
    metadata_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = _operator_view_payload(self, include_hash=True)
        if _has_forbidden_runtime_key(payload):
            _fail(
                "hip_assembly_runtime_handle_leak",
                "/operator_view",
                "Operator metadata contains a forbidden runtime term.",
            )
        expected = canonical_hash(_operator_view_payload(self, include_hash=False))
        if self.metadata_hash != expected:
            _fail(
                "hip_assembly_operator_view_hash_mismatch",
                "/operator_view/metadata_hash",
                "Operator-view metadata hash is stale.",
            )
        return payload


@dataclass(frozen=True, slots=True)
class HipAssemblyContextReceipt:
    status: ContextStatus
    context_id: str
    actual_backend: str | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipAssemblyReason | None
    base_context_receipt_hash: str
    assembly_evaluation_receipt_hash: str
    bindings: HipAssemblyBindings
    kernel: HipAssemblyKernelBinding | None
    kernel_ownership: Literal["context"]
    device: HipAssemblyDevice | None
    dimensions: HipAssemblyDimensions
    child_buffers: tuple[HipAssemblyBufferView, ...]
    operator_view: HipAssemblyOperatorView | None
    telemetry: HipAssemblyTelemetry
    claims: HipAssemblyClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_ASSEMBLY_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_assembly_context_receipt(self)
        return _context_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipAssemblyParityMetric:
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
            "relative_tolerance": _PARITY_TOLERANCE,
            "scaled_tolerance": _PARITY_TOLERANCE,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipAssemblyParityReport:
    csr_values: HipAssemblyParityMetric
    structural_zero_count: int
    structural_zeros_exact: bool
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "execution_plan_v2_cpu_csr_values_fp64",
            "oracle_role": "verification_only_never_fallback",
            "csr_values": self.csr_values.to_dict(),
            "structural_zero_count": self.structural_zero_count,
            "structural_zeros_exact": self.structural_zeros_exact,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipAssemblyWorkReceipt:
    element_count: int
    csr_nnz: int
    contribution_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": "hiprtc_linear_frame_truss_assembly_v1",
            "operation_count_basis": (
                "structural_source_equivalent_not_hardware_counter"
            ),
            "element_count": self.element_count,
            "csr_nnz": self.csr_nnz,
            "contribution_count": self.contribution_count,
            "element_kernel_launch_count": 1,
            "segmented_gather_launch_count": 1,
            "contribution_write_count": self.contribution_count,
            "gather_read_count": self.contribution_count,
            "physical_dram_bytes": "not_instrumented",
            "fixed_rank_kernel_scope_linear_in_e_plus_c_plus_z": True,
            "end_to_end_o_n_claim": False,
            "solver_ready": False,
        }


@dataclass(frozen=True, slots=True)
class HipAssemblyEvaluationReceipt:
    status: EvaluationStatus
    execution_id: str
    context_id: str
    actual_backend: str | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipAssemblyReason | None
    bindings: HipAssemblyBindings
    operator_id: str
    device_error_code: int | None
    csr_values_dtype: str | None
    csr_values_shape: tuple[int, ...] | None
    csr_values_byte_length: int | None
    csr_values_data_hash: str | None
    telemetry_delta: HipAssemblyTelemetry
    parity: HipAssemblyParityReport | None
    work: HipAssemblyWorkReceipt
    claims: HipAssemblyClaims
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_ASSEMBLY_EVALUATION_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_assembly_evaluation_receipt(self)
        return _evaluation_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipAssemblyEvaluation:
    receipt: HipAssemblyEvaluationReceipt
    csr_values: np.ndarray | None

    @property
    def result_hash(self) -> str:
        return self.receipt.receipt_hash

    def to_dict(self) -> dict[str, Any]:
        validate_hip_assembly_evaluation(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipAssemblyContextOpenResult:
    context: HipAssemblyExecutionContext | None
    receipt: HipAssemblyContextReceipt
    evaluation: HipAssemblyEvaluation

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


class _HipAssemblyKernelCleanupOwner:
    """Last-resort reachable owner when no strict binding can be serialized."""

    def __init__(self, kernel: Any) -> None:
        self._kernel = kernel
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._kernel.close()
        self._closed = True


class HipAssemblyExecutionContext:
    """Owner of foundation residency, two assembly kernels, and eight children."""

    def __init__(
        self,
        *,
        buffers: SolverModelBuffers,
        source_plan: ExecutionPlanV2,
        assembly_plan: HipAssemblyPlanV1,
        base_context: DeviceExecutionContext | None,
        base_context_receipt_hash: str,
        rtc_kernel: Any,
        kernel_binding: HipAssemblyKernelBinding,
        evidence_scope: EvidenceScope,
        device: HipAssemblyDevice | None,
        context_id: str,
        pointers: dict[str, Any],
        child_buffers: tuple[HipAssemblyBufferView, ...],
        telemetry: HipAssemblyTelemetry,
        opening_evaluation: HipAssemblyEvaluation,
        operator_view: HipAssemblyOperatorView | None,
        opening_status: ContextStatus,
        failure_reason: HipAssemblyReason | None,
        base_deallocation_observed: int | None = None,
        base_current_bytes_observed: int | None = None,
    ) -> None:
        self._buffers = buffers
        self._source_plan = source_plan
        self._assembly_plan = assembly_plan
        self._base_context = base_context
        self._base_context_receipt_hash = base_context_receipt_hash
        self._runtime = None if base_context is None else base_context._runtime
        self._stream = None if base_context is None else base_context._stream
        self._rtc_kernel = rtc_kernel
        self._kernel_binding = kernel_binding
        self._evidence_scope = evidence_scope
        self._device = device
        self._context_id = context_id
        self._pointers = pointers
        self._child_buffers = child_buffers
        self._telemetry = telemetry
        self._opening_evaluation = opening_evaluation
        self._operator_view = operator_view
        self._closed = False
        self._poisoned = opening_status == "poisoned"
        self._cleanup_failed = opening_status == "cleanup_failed"
        self._failure_reason = failure_reason
        # A resident consumer borrows the assembly-owned CSR allocation and
        # stream.  The opaque token prevents the parent from being closed or
        # multiply borrowed while a downstream operator context is live.
        self._resident_consumer_token: object | None = None
        self._resident_operator_epoch = 0
        self._resident_consumer_lock = threading.RLock()
        self._close_sync_complete = False
        self._kernel_closed = False
        self._base_deallocation_observed = int(
            (0 if base_context is None else base_context._telemetry.deallocation_count)
            if base_deallocation_observed is None
            else base_deallocation_observed
        )
        self._base_current_bytes_observed = int(
            (
                0
                if base_context is None
                else base_context._telemetry.current_device_payload_bytes
            )
            if base_current_bytes_observed is None
            else base_current_bytes_observed
        )
        self._opening_receipt = self._build_receipt(opening_status)

    def __repr__(self) -> str:
        if self._cleanup_failed:
            status = "cleanup_failed"
        elif self._closed:
            status = "closed"
        elif self._poisoned:
            status = "poisoned"
        else:
            status = "ready"
        return (
            f"HipAssemblyExecutionContext(context_id={self._context_id!r}, "
            f"status={status!r})"
        )

    def __enter__(self) -> HipAssemblyExecutionContext:
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
    def opening_receipt(self) -> HipAssemblyContextReceipt:
        return self._opening_receipt

    @property
    def opening_evaluation(self) -> HipAssemblyEvaluation:
        return self._opening_evaluation

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def receipt(self) -> HipAssemblyContextReceipt:
        if self._cleanup_failed:
            status: ContextStatus = "cleanup_failed"
        elif self._closed:
            status = "context_closed"
        elif self._poisoned:
            status = "poisoned"
        else:
            status = "context_ready"
        return self._build_receipt(status)

    def operator_view(self) -> HipAssemblyOperatorView:
        self._require_usable()
        _validate_live_contracts(self)
        _validate_live_kernel(self._rtc_kernel, self._kernel_binding)
        if self._operator_view is None:  # pragma: no cover - construction invariant
            _fail(
                "hip_assembly_operator_view_missing",
                "/operator_view",
                "Ready context has no resident operator metadata.",
            )
        self._operator_view.to_dict()
        return self._operator_view

    def close(self) -> None:
        """Synchronize, retryably free children, close the kernel and base."""

        with self._resident_consumer_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        """Close while excluding a concurrent resident-lease acquisition."""

        if self._closed:
            return
        if self._resident_consumer_token is not None:
            _fail(
                "hip_assembly_resident_consumer_active",
                "/lifetime/resident_consumer",
                "Close the resident CSR consumer before closing its assembly owner.",
            )
        if (
            self._base_context is not None
            and not self._close_sync_complete
            and not self._base_context.closed
        ):
            try:
                self._runtime.synchronize(self._stream)
            except Exception as exc:
                self._cleanup_failed = True
                self._failure_reason = HipAssemblyReason(
                    "hip_assembly_cleanup_sync_failed", _exception_detail(exc)
                )
                raise HipAssemblyContextError(
                    "hip_assembly_cleanup_sync_failed",
                    "/cleanup/synchronize",
                    self._failure_reason.detail,
                ) from exc
            self._close_sync_complete = True
            self._telemetry = replace(
                self._telemetry,
                explicit_sync_count=self._telemetry.explicit_sync_count + 1,
            )

        first_error: Exception | None = None
        for name in reversed(_CHILD_BUFFER_ORDER):
            pointer = self._pointers.get(name)
            if pointer is None:
                continue
            self._telemetry = replace(
                self._telemetry,
                child_deallocation_attempt_count=(
                    self._telemetry.child_deallocation_attempt_count + 1
                ),
            )
            try:
                self._runtime.free(pointer)
            except Exception as exc:
                first_error = first_error or exc
                continue
            del self._pointers[name]
            byte_length = _view_by_name(self._child_buffers, name).byte_length
            self._telemetry = replace(
                self._telemetry,
                deallocation_count=self._telemetry.deallocation_count + 1,
                child_deallocation_success_count=(
                    self._telemetry.child_deallocation_success_count + 1
                ),
                current_device_payload_bytes=(
                    self._telemetry.current_device_payload_bytes - byte_length
                ),
            )
        if self._pointers:
            self._cleanup_failed = True
            self._failure_reason = HipAssemblyReason(
                "hip_assembly_context_cleanup_failed",
                _exception_detail(first_error or "child allocations remain"),
            )
            raise HipAssemblyContextError(
                "hip_assembly_context_cleanup_failed",
                "/cleanup/child_buffers",
                self._failure_reason.detail,
            )

        if not self._kernel_closed:
            try:
                self._rtc_kernel.close()
            except Exception as exc:
                self._cleanup_failed = True
                self._failure_reason = HipAssemblyReason(
                    "hip_assembly_kernel_cleanup_failed", _exception_detail(exc)
                )
                raise HipAssemblyContextError(
                    "hip_assembly_kernel_cleanup_failed",
                    "/cleanup/kernel",
                    self._failure_reason.detail,
                ) from exc
            self._kernel_closed = True

        if self._base_context is not None and not self._base_context.closed:
            try:
                self._base_context.close()
            except Exception as exc:
                self._observe_base_cleanup()
                self._cleanup_failed = True
                self._failure_reason = HipAssemblyReason(
                    "hip_assembly_foundation_cleanup_failed",
                    _exception_detail(exc),
                )
                raise HipAssemblyContextError(
                    "hip_assembly_foundation_cleanup_failed",
                    "/cleanup/base_context",
                    self._failure_reason.detail,
                ) from exc
        self._observe_base_cleanup()
        if self._telemetry.current_device_payload_bytes != 0:
            self._cleanup_failed = True
            self._failure_reason = HipAssemblyReason(
                "hip_assembly_context_cleanup_failed",
                "Cleanup completed with non-zero tracked device payload.",
            )
            raise HipAssemblyContextError(
                "hip_assembly_context_cleanup_failed",
                "/cleanup/telemetry",
                self._failure_reason.detail,
            )
        self._closed = True
        self._cleanup_failed = False
        self._failure_reason = None

    def _acquire_resident_consumer(self) -> object:
        """Exclusively lease the process-local operator to a child context."""

        with self._resident_consumer_lock:
            self._require_usable()
            _validate_live_contracts(self)
            _validate_live_kernel(self._rtc_kernel, self._kernel_binding)
            if self._resident_consumer_token is not None:
                _fail(
                    "hip_assembly_resident_consumer_active",
                    "/lifetime/resident_consumer",
                    "The assembly operator already has an active resident consumer.",
                )
            token = object()
            self._resident_operator_epoch += 1
            self._resident_consumer_token = token
            return token

    def _require_resident_consumer(self, token: object) -> None:
        """Validate an opaque child lease without exposing device handles."""

        with self._resident_consumer_lock:
            if token is not self._resident_consumer_token:
                _fail(
                    "hip_assembly_resident_consumer_token_invalid",
                    "/lifetime/resident_consumer",
                    "Resident consumer token is stale or foreign.",
                )
            self._require_usable()

    def _resident_consumer_epoch(self, token: object) -> int:
        """Return the monotonic operator lease epoch for one exact token."""

        with self._resident_consumer_lock:
            self._require_resident_consumer(token)
            return self._resident_operator_epoch

    def _poison_resident_consumer(self, token: object, detail: str) -> None:
        """Invalidate the shared serial queue after downstream device failure."""

        with self._resident_consumer_lock:
            self._require_resident_consumer(token)
            self._poisoned = True
            self._failure_reason = HipAssemblyReason(
                "hip_assembly_resident_consumer_poisoned",
                _bounded_detail(detail),
            )

    def _release_resident_consumer(self, token: object) -> None:
        """Release one exact child lease after its resources are reclaimed."""

        with self._resident_consumer_lock:
            if token is not self._resident_consumer_token:
                _fail(
                    "hip_assembly_resident_consumer_token_invalid",
                    "/lifetime/resident_consumer",
                    "Resident consumer token is stale or foreign.",
                )
            self._resident_consumer_token = None

    def _observe_base_cleanup(self) -> None:
        if self._base_context is None:
            return
        telemetry = self._base_context._telemetry
        dealloc_delta = (
            int(telemetry.deallocation_count) - self._base_deallocation_observed
        )
        released = self._base_current_bytes_observed - int(
            telemetry.current_device_payload_bytes
        )
        if dealloc_delta < 0 or released < 0:
            _fail(
                "hip_assembly_context_telemetry_invalid",
                "/cleanup/base_context",
                "Foundation cleanup telemetry moved backwards.",
            )
        self._telemetry = replace(
            self._telemetry,
            deallocation_count=self._telemetry.deallocation_count + dealloc_delta,
            current_device_payload_bytes=(
                self._telemetry.current_device_payload_bytes - released
            ),
        )
        self._base_deallocation_observed = int(telemetry.deallocation_count)
        self._base_current_bytes_observed = int(telemetry.current_device_payload_bytes)

    def _build_receipt(self, status: ContextStatus) -> HipAssemblyContextReceipt:
        ready = status == "context_ready"
        return _build_context_receipt(
            status=status,
            context_id=self._context_id,
            actual_backend=_actual_backend(self._evidence_scope),
            evidence_scope=self._evidence_scope,
            reason=(
                None
                if status in ("context_ready", "context_closed")
                else self._failure_reason
            ),
            base_context_receipt_hash=self._base_context_receipt_hash,
            evaluation_receipt_hash=self._opening_evaluation.receipt.receipt_hash,
            bindings=_bindings(
                self._buffers,
                self._source_plan,
                self._assembly_plan,
                self._opening_evaluation.receipt.bindings.verification_requested,
                self._kernel_binding.identity_hash,
                self._opening_evaluation.receipt.bindings.device_ordinal,
            ),
            kernel=self._kernel_binding,
            device=self._device,
            dimensions=_dimensions(self._buffers, self._source_plan),
            child_buffers=self._child_buffers,
            operator_view=self._operator_view,
            telemetry=self._telemetry,
            claims=HipAssemblyClaims(
                device_element_contributions_executed=ready,
                device_segmented_gather_executed=ready,
                device_csr_operator_resident=ready,
                cpu_reference_parity_verified=(
                    ready and self._opening_evaluation.receipt.status == "verified"
                ),
                native_hiprtc_kernel_loaded=(
                    ready and self._evidence_scope == "native_hiprtc"
                ),
            ),
        )

    def _require_usable(self) -> None:
        if self._closed:
            _fail("hip_assembly_context_closed", "/status", "Context is closed.")
        if self._cleanup_failed:
            _fail(
                "hip_assembly_context_cleanup_failed",
                "/status",
                "Context is cleanup-only; retry close().",
            )
        if self._poisoned:
            _fail(
                "hip_assembly_context_poisoned",
                "/status",
                "A failed assembly execution poisoned this context.",
            )


def open_hip_assembly_execution_context(
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    *,
    verify_cpu_parity: bool = True,
    device_ordinal: int = 0,
    architecture: str | None = None,
    runtime_library: str | Path | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    runtime: Any | None = None,
    rtc_kernel: Any | None = None,
) -> HipAssemblyContextOpenResult:
    """Assemble and retain one sparse frame/truss operator on a HIP device.

    An injected runtime or kernel always produces ``injected_test_double``
    evidence.  Only an internally loaded exact native runtime and internally
    compiled exact package kernel can produce ``native_hiprtc`` evidence.
    """

    _preflight(
        buffers,
        source_plan,
        assembly_plan,
        verify_cpu_parity=verify_cpu_parity,
        device_ordinal=device_ordinal,
        architecture=architecture,
        memory_budget_bytes=memory_budget_bytes,
        rtc_kernel=rtc_kernel,
    )
    # The sparse plan already owns a detached immutable buffer witness.  Use
    # that witness (and the assembly plan's hash-bound source plan) for every
    # later upload, launch, receipt, and live validation.  Caller mapping
    # containers are never retained as the residency authority.
    source_witness = assembly_plan._source_execution_plan
    authoritative_buffers = _detached_source_snapshot(source_witness._source_buffers)
    authoritative_plan = replace(source_witness, _source_buffers=authoritative_buffers)
    assembly_plan = replace(
        assembly_plan,
        _source_buffers=authoritative_buffers,
        _source_execution_plan=authoritative_plan,
    )
    validate_hip_assembly_plan_v1(
        assembly_plan,
        expected_buffers=authoritative_buffers,
        expected_execution_plan=authoritative_plan,
    )
    buffers = authoritative_buffers
    source_plan = authoritative_plan
    arrays = _child_arrays(source_plan, assembly_plan)
    views = _child_buffer_views(arrays)
    dimensions = _dimensions(buffers, source_plan)
    foundation_bytes = dimensions.foundation_payload_bytes
    child_bytes = sum(view.byte_length for view in views)
    if (
        memory_budget_bytes is not None
        and foundation_bytes + child_bytes > memory_budget_bytes
    ):
        raise HipAssemblyContextError(
            "hip_assembly_memory_budget_exceeded",
            "/memory_budget_bytes",
            f"Required {foundation_bytes + child_bytes} bytes exceeds "
            f"budget {memory_budget_bytes}.",
        )

    # Allocate verification staging before acquiring any kernel or device
    # resource.  A host MemoryError therefore cannot orphan native ownership.
    # The no-verification path allocates only the one-int error scalar.
    host_error, host_csr = _allocate_host_staging(source_plan.nnz, verify_cpu_parity)

    kernel = rtc_kernel
    runtime_for_base = runtime
    if kernel is None:
        if architecture is None:  # guarded by preflight
            raise AssertionError("architecture preflight was bypassed")
        if runtime is None:
            loaded_runtime = load_hip_native_runtime(runtime_library)
        elif callable(getattr(runtime, "bind", None)):
            loaded_runtime = runtime
        else:
            raise HipAssemblyContextError(
                "hip_assembly_runtime_invalid",
                "/runtime",
                "HIPRTC compilation requires a loaded runtime with bind().",
            )
        _select_loaded_runtime_device(loaded_runtime, device_ordinal)
        try:
            kernel = compile_hip_rtc_linear_frame_truss_assembly_kernel(
                loaded_runtime,
                architecture,
                hiprtc_library=hiprtc_library,
            )
        except HipRtcAssemblyError as exc:
            raise HipAssemblyContextError(
                exc.code, "/kernel/compile", exc.message
            ) from exc
        evidence_scope: EvidenceScope = (
            "native_hiprtc"
            if runtime is None
            and type(loaded_runtime) is LoadedHipRuntime
            and type(kernel) is HipRtcLinearFrameTrussAssemblyKernel
            else "injected_test_double"
        )
        runtime_for_base = loaded_runtime
    else:
        evidence_scope = "injected_test_double"

    kernel_binding: HipAssemblyKernelBinding | None = None
    try:
        kernel_binding = _kernel_binding(kernel, architecture)
        bindings = _bindings(
            buffers,
            source_plan,
            assembly_plan,
            verify_cpu_parity,
            kernel_binding.identity_hash,
            device_ordinal,
        )
        context_id = _context_id(
            buffers,
            source_plan,
            assembly_plan,
            kernel_binding,
            evidence_scope,
            device_ordinal,
            verify_cpu_parity,
        )
        operator_id = _operator_id(
            context_id, source_plan, assembly_plan, kernel_binding
        )
        execution_id = _execution_id(context_id, operator_id, verify_cpu_parity)
        work = _work(source_plan, assembly_plan)
        base_budget = (
            None if memory_budget_bytes is None else memory_budget_bytes - child_bytes
        )
        base_open = open_device_execution_context(
            buffers,
            device_ordinal=device_ordinal,
            runtime_library=runtime_library if runtime_for_base is None else None,
            memory_budget_bytes=base_budget,
            runtime=runtime_for_base,
        )
    except Exception as primary:
        return _handle_post_kernel_acquisition_failure(
            primary=primary,
            kernel=kernel,
            kernel_binding=kernel_binding,
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            verify_cpu_parity=verify_cpu_parity,
            evidence_scope=evidence_scope,
            device_ordinal=device_ordinal,
        )

    if not base_open.ready or base_open.context is None:
        base_owner = base_open.context
        cleanup_error: Exception | None = None
        kernel_closed = False
        if base_owner is not None:
            try:
                base_owner.close()
            except Exception as exc:
                cleanup_error = exc
        try:
            kernel.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        else:
            kernel_closed = True
        reason = HipAssemblyReason(
            "hip_assembly_foundation_not_ready",
            _bounded_detail(
                base_open.receipt.reason.detail
                if base_open.receipt.reason is not None
                else "HIP foundation context is unavailable."
            ),
        )
        delta = HipAssemblyTelemetry()
        evaluation = _build_evaluation(
            status="unavailable",
            execution_id=execution_id,
            context_id=context_id,
            evidence_scope=evidence_scope,
            reason=reason,
            bindings=bindings,
            operator_id=operator_id,
            device_error_code=None,
            csr_values=None,
            telemetry_delta=delta,
            parity=None,
            work=work,
        )
        if cleanup_error is not None:
            cleanup_reason = HipAssemblyReason(
                "hip_assembly_context_cleanup_failed",
                _bounded_detail(
                    f"{reason.detail}; cleanup: {_exception_detail(cleanup_error)}"
                ),
            )
            context = HipAssemblyExecutionContext(
                buffers=buffers,
                source_plan=source_plan,
                assembly_plan=assembly_plan,
                base_context=base_owner,
                base_context_receipt_hash=base_open.receipt.context_receipt_hash,
                rtc_kernel=kernel,
                kernel_binding=kernel_binding,
                evidence_scope=evidence_scope,
                device=None,
                context_id=context_id,
                pointers={},
                child_buffers=(),
                telemetry=_telemetry_from_base(
                    base_owner._telemetry
                    if base_owner is not None
                    else base_open.receipt.telemetry
                ),
                opening_evaluation=evaluation,
                operator_view=None,
                opening_status="cleanup_failed",
                failure_reason=cleanup_reason,
                base_deallocation_observed=(
                    int(base_owner._telemetry.deallocation_count)
                    if base_owner is not None
                    else 0
                ),
                base_current_bytes_observed=(
                    int(base_owner._telemetry.current_device_payload_bytes)
                    if base_owner is not None
                    else 0
                ),
            )
            context._kernel_closed = kernel_closed
            return HipAssemblyContextOpenResult(
                context, context.opening_receipt, evaluation
            )
        telemetry = _telemetry_from_base(
            base_owner._telemetry
            if base_owner is not None
            else base_open.receipt.telemetry
        )
        receipt = _build_context_receipt(
            status="unavailable",
            context_id=context_id,
            actual_backend=None,
            evidence_scope=evidence_scope,
            reason=reason,
            base_context_receipt_hash=base_open.receipt.context_receipt_hash,
            evaluation_receipt_hash=evaluation.receipt.receipt_hash,
            bindings=bindings,
            kernel=kernel_binding,
            device=None,
            dimensions=dimensions,
            child_buffers=(),
            operator_view=None,
            telemetry=telemetry,
            claims=_empty_claims(),
        )
        return HipAssemblyContextOpenResult(None, receipt, evaluation)

    base = base_open.context
    runtime_impl = base._runtime
    if base._device is None:  # pragma: no cover - foundation invariant
        raise AssertionError("ready HIP foundation has no device")
    device = HipAssemblyDevice(
        ordinal=device_ordinal,
        name=base._device.name,
        architecture=kernel_binding.architecture,
        runtime_version_raw=base._device.runtime_version_raw,
        driver_version_raw=base._device.driver_version_raw,
    )
    telemetry = _telemetry_from_base(base._telemetry)
    base_telemetry = telemetry
    pointers: dict[str, Any] = {}

    try:
        if evidence_scope == "native_hiprtc":
            _validate_native_open_links(base, kernel, kernel_binding)
        for view in views:
            telemetry = replace(
                telemetry,
                child_allocation_attempt_count=(
                    telemetry.child_allocation_attempt_count + 1
                ),
            )
            pointer = runtime_impl.malloc(view.byte_length)
            pointers[view.name] = pointer
            current = telemetry.current_device_payload_bytes + view.byte_length
            telemetry = replace(
                telemetry,
                allocation_count=telemetry.allocation_count + 1,
                child_allocation_success_count=(
                    telemetry.child_allocation_success_count + 1
                ),
                current_device_payload_bytes=current,
                peak_device_payload_bytes=max(
                    telemetry.peak_device_payload_bytes, current
                ),
            )
            if view.name in _INITIAL_UPLOAD_NAMES:
                telemetry = replace(
                    telemetry,
                    child_initial_h2d_attempt_count=(
                        telemetry.child_initial_h2d_attempt_count + 1
                    ),
                )
                array = arrays[view.name].host_backing
                if array is None:  # pragma: no cover - upload-set invariant
                    _fail(
                        "hip_assembly_output_upload_forbidden",
                        f"/child_buffers/{view.name}",
                        "Output-only allocation has no host backing.",
                    )
                # No branch in this loop can select source_plan CSR numerics:
                # ``global_stiffness_csr_values`` is absent from ``arrays``.
                runtime_impl.copy_h2d_async(pointer, array, base._stream)
                telemetry = replace(
                    telemetry,
                    h2d_bytes=telemetry.h2d_bytes + view.byte_length,
                    h2d_operation_count=telemetry.h2d_operation_count + 1,
                    child_initial_h2d_success_count=(
                        telemetry.child_initial_h2d_success_count + 1
                    ),
                    host_csr_values_h2d_bytes=0,
                )
    except Exception as primary:
        return _finish_pre_execution_open_failure(
            primary=primary,
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base=base,
            base_receipt_hash=base_open.receipt.context_receipt_hash,
            kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
            bindings=bindings,
            dimensions=dimensions,
            execution_id=execution_id,
            operator_id=operator_id,
            work=work,
            base_telemetry=base_telemetry,
        )

    execution_reason: HipAssemblyReason | None = None
    try:
        telemetry = replace(
            telemetry,
            kernel_launch_attempt_count=telemetry.kernel_launch_attempt_count + 1,
        )
        result = kernel.launch_element_contributions(
            base._stream,
            source_plan.element_count,
            source_plan.node_count,
            int(buffers.array("material_properties_si").shape[0]),
            int(buffers.array("section_properties_si").shape[0]),
            base._pointers["node_coordinates_m"],
            base._pointers["element_connectivity"],
            base._pointers["element_type"],
            base._pointers["element_formulation_code"],
            base._pointers["element_material_index"],
            base._pointers["element_section_index"],
            base._pointers["material_law_code"],
            base._pointers["material_properties_si"],
            base._pointers["section_family_code"],
            base._pointers["section_properties_si"],
            base._pointers["element_local_axis_rotation_rad"],
            pointers["reference_axis_code"],
            pointers["element_contributions"],
            pointers["error_flag"],
        )
        if result is not None:
            _fail(
                "hip_assembly_kernel_contract_invalid",
                "/kernel/launch_element_contributions",
                "Kernel launch must return None or raise.",
            )
        telemetry = replace(
            telemetry, kernel_launch_count=telemetry.kernel_launch_count + 1
        )

        telemetry = replace(
            telemetry,
            kernel_launch_attempt_count=telemetry.kernel_launch_attempt_count + 1,
        )
        result = kernel.launch_csr_gather(
            base._stream,
            source_plan.nnz,
            assembly_plan.contribution_count,
            pointers["element_contributions"],
            pointers["reverse_segment_offsets"],
            pointers["reverse_contribution_indices"],
            pointers["csr_values"],
            pointers["error_flag"],
        )
        if result is not None:
            _fail(
                "hip_assembly_kernel_contract_invalid",
                "/kernel/launch_csr_gather",
                "Kernel launch must return None or raise.",
            )
        telemetry = replace(
            telemetry, kernel_launch_count=telemetry.kernel_launch_count + 1
        )

        telemetry = replace(
            telemetry,
            d2h_operation_attempt_count=(telemetry.d2h_operation_attempt_count + 1),
            d2h_bytes_attempted=(
                telemetry.d2h_bytes_attempted + int(host_error.nbytes)
            ),
        )
        runtime_impl.copy_d2h_async(host_error, pointers["error_flag"], base._stream)
        telemetry = replace(
            telemetry,
            d2h_bytes=telemetry.d2h_bytes + int(host_error.nbytes),
            d2h_operation_count=telemetry.d2h_operation_count + 1,
            d2h_operation_success_count=(telemetry.d2h_operation_success_count + 1),
            d2h_bytes_succeeded=(
                telemetry.d2h_bytes_succeeded + int(host_error.nbytes)
            ),
            error_flag_d2h_bytes=int(host_error.nbytes),
        )
        if host_csr is not None:
            telemetry = replace(
                telemetry,
                d2h_operation_attempt_count=(telemetry.d2h_operation_attempt_count + 1),
                d2h_bytes_attempted=(
                    telemetry.d2h_bytes_attempted + int(host_csr.nbytes)
                ),
            )
            runtime_impl.copy_d2h_async(host_csr, pointers["csr_values"], base._stream)
            telemetry = replace(
                telemetry,
                d2h_bytes=telemetry.d2h_bytes + int(host_csr.nbytes),
                d2h_operation_count=telemetry.d2h_operation_count + 1,
                d2h_operation_success_count=(telemetry.d2h_operation_success_count + 1),
                d2h_bytes_succeeded=(
                    telemetry.d2h_bytes_succeeded + int(host_csr.nbytes)
                ),
                verification_csr_d2h_bytes=int(host_csr.nbytes),
            )
        telemetry = replace(
            telemetry,
            assembly_sync_attempt_count=telemetry.assembly_sync_attempt_count + 1,
        )
        runtime_impl.synchronize(base._stream)
        telemetry = replace(
            telemetry,
            explicit_sync_count=telemetry.explicit_sync_count + 1,
            assembly_sync_count=telemetry.assembly_sync_count + 1,
            assembly_sync_success_count=telemetry.assembly_sync_success_count + 1,
        )
    except Exception as exc:
        execution_reason = HipAssemblyReason(
            "hip_assembly_device_execution_failed", _exception_detail(exc)
        )

    try:
        return _complete_post_execution_open(
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base=base,
            base_receipt_hash=base_open.receipt.context_receipt_hash,
            kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            device_ordinal=device_ordinal,
            context_id=context_id,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
            base_telemetry=base_telemetry,
            execution_reason=execution_reason,
            host_error=host_error,
            host_csr=host_csr,
            bindings=bindings,
            operator_id=operator_id,
            execution_id=execution_id,
            work=work,
        )
    except Exception as primary:
        return _finish_pre_execution_open_failure(
            primary=primary,
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base=base,
            base_receipt_hash=base_open.receipt.context_receipt_hash,
            kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
            bindings=bindings,
            dimensions=dimensions,
            execution_id=execution_id,
            operator_id=operator_id,
            work=work,
            base_telemetry=base_telemetry,
        )


def validate_hip_assembly_context_receipt(
    receipt: HipAssemblyContextReceipt,
    *,
    expected_buffers: SolverModelBuffers | None = None,
    expected_source_plan: ExecutionPlanV2 | None = None,
    expected_assembly_plan: HipAssemblyPlanV1 | None = None,
    expected_kernel: Any | None = None,
) -> HipAssemblyContextReceipt:
    """Replay schema, hash, telemetry, claims, and optional object bindings."""

    if type(receipt) is not HipAssemblyContextReceipt:
        _fail(
            "hip_assembly_context_receipt_type_invalid",
            "/",
            "Expected an exact HipAssemblyContextReceipt.",
        )
    _validate_context_object_types(receipt)
    payload = _context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema_validator(), payload, "context")
    if _has_forbidden_runtime_key(payload):
        _fail(
            "hip_assembly_runtime_handle_leak",
            "/",
            "Serialized context receipt contains a runtime handle term.",
        )
    if receipt.context_receipt_hash != canonical_hash(
        _context_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_assembly_context_receipt_hash_mismatch",
            "/context_receipt_hash",
            "Context receipt hash is stale.",
        )
    _validate_context_semantics(receipt)

    if expected_buffers is not None:
        validate_solver_model_buffers(expected_buffers)
        if any(
            (
                receipt.bindings.model_ir_content_hash
                != expected_buffers.model_ir_content_hash,
                receipt.bindings.solver_artifact_hash != expected_buffers.artifact_hash,
                receipt.bindings.solver_numeric_buffer_hash
                != expected_buffers.numeric_buffer_hash,
                receipt.bindings.load_pattern_id != expected_buffers.load_pattern_id,
            )
        ):
            _fail(
                "hip_assembly_context_buffer_binding_mismatch",
                "/bindings",
                "Receipt is bound to different model buffers.",
            )
        if receipt.dimensions.foundation_buffer_count != len(
            expected_buffers.descriptors
        ) or receipt.dimensions.foundation_payload_bytes != sum(
            row.byte_length for row in expected_buffers.descriptors
        ):
            _fail(
                "hip_assembly_context_buffer_binding_mismatch",
                "/dimensions",
                "Foundation dimensions differ from expected buffers.",
            )
    if expected_source_plan is not None:
        validate_execution_plan_v2(
            expected_source_plan, expected_buffers=expected_buffers
        )
        if any(
            (
                receipt.bindings.source_execution_plan_hash
                != expected_source_plan.plan_hash,
                receipt.bindings.source_operator_hash
                != expected_source_plan.operator_hash,
                receipt.bindings.source_numeric_snapshot_hash
                != expected_source_plan.numeric_snapshot_hash,
                receipt.bindings.source_symbolic_reuse_hash
                != expected_source_plan.symbolic_reuse_hash,
                receipt.bindings.source_partition_hash
                != expected_source_plan.partition_hash,
                receipt.dimensions.global_dof_count != expected_source_plan.dof_count,
                receipt.dimensions.csr_nnz != expected_source_plan.nnz,
            )
        ):
            _fail(
                "hip_assembly_context_source_plan_binding_mismatch",
                "/bindings",
                "Receipt is bound to a different sparse execution plan.",
            )
        if expected_buffers is not None and receipt.dimensions != _dimensions(
            expected_buffers, expected_source_plan
        ):
            _fail(
                "hip_assembly_context_dimension_binding_mismatch",
                "/dimensions",
                "All dimensions must replay exactly from expected inputs.",
            )
    if expected_assembly_plan is not None:
        if expected_source_plan is None:
            _fail(
                "hip_assembly_expected_input_invalid",
                "/expected_source_plan",
                "expected_assembly_plan requires expected_source_plan.",
            )
        validate_hip_assembly_plan_v1(
            expected_assembly_plan,
            expected_buffers=expected_buffers,
            expected_execution_plan=expected_source_plan,
        )
        if any(
            (
                receipt.bindings.assembly_plan_hash
                != expected_assembly_plan.assembly_plan_hash,
                receipt.bindings.assembly_symbolic_payload_hash
                != expected_assembly_plan.symbolic_payload_hash,
                receipt.bindings.axis_policy_hash
                != expected_assembly_plan.axis_policy_hash,
                receipt.bindings.reverse_map_hash
                != expected_assembly_plan.reverse_map_hash,
                receipt.dimensions.contribution_count
                != expected_assembly_plan.contribution_count,
            )
        ):
            _fail(
                "hip_assembly_context_assembly_plan_binding_mismatch",
                "/bindings",
                "Receipt is bound to a different assembly plan.",
            )
        if receipt.child_buffers:
            expected_views = _child_buffer_views(
                _child_arrays(expected_source_plan, expected_assembly_plan)
            )
            if receipt.child_buffers != expected_views:
                _fail(
                    "hip_assembly_context_child_hash_mismatch",
                    "/child_buffers",
                    "Uploaded child descriptors differ from bound source bytes.",
                )
    if expected_kernel is not None:
        if receipt.kernel is None:
            _fail(
                "hip_assembly_context_kernel_binding_missing",
                "/kernel",
                "Expected kernel binding is absent.",
            )
        if receipt.status == "context_ready":
            _validate_live_kernel(expected_kernel, receipt.kernel)
        else:
            _validate_kernel_snapshot(expected_kernel, receipt.kernel)
    if (
        expected_buffers is not None
        and expected_source_plan is not None
        and expected_assembly_plan is not None
        and expected_kernel is not None
    ):
        expected_kernel_binding = _kernel_binding(
            expected_kernel,
            None if receipt.device is None else receipt.device.architecture,
        )
        expected_context_id = _context_id(
            expected_buffers,
            expected_source_plan,
            expected_assembly_plan,
            expected_kernel_binding,
            receipt.evidence_scope,
            receipt.bindings.device_ordinal,
            receipt.bindings.verification_requested,
        )
        if receipt.context_id != expected_context_id:
            _fail(
                "hip_assembly_context_device_binding_mismatch",
                "/context_id",
                "Context ID does not bind the selected device ordinal.",
            )
        if receipt.operator_view is not None:
            expected_operator_id = _operator_id(
                expected_context_id,
                expected_source_plan,
                expected_assembly_plan,
                expected_kernel_binding,
            )
            expected_operator = _operator_view(
                expected_context_id,
                expected_operator_id,
                expected_source_plan,
                expected_assembly_plan,
                expected_kernel_binding,
                receipt.bindings.device_ordinal,
                receipt.operator_view.verification_data_hash,
            )
            if receipt.operator_view != expected_operator:
                _fail(
                    "hip_assembly_context_operator_binding_mismatch",
                    "/operator_view",
                    "Operator metadata does not replay from expected inputs.",
                )
    return receipt


def validate_hip_assembly_evaluation_receipt(
    receipt: HipAssemblyEvaluationReceipt,
    *,
    expected_context: HipAssemblyExecutionContext | None = None,
) -> HipAssemblyEvaluationReceipt:
    if type(receipt) is not HipAssemblyEvaluationReceipt:
        _fail(
            "hip_assembly_evaluation_receipt_type_invalid",
            "/",
            "Expected an exact HipAssemblyEvaluationReceipt.",
        )
    _validate_evaluation_object_types(receipt)
    payload = _evaluation_payload(receipt, include_hash=True)
    _validate_schema(_evaluation_schema_validator(), payload, "evaluation")
    if _has_forbidden_runtime_key(payload):
        _fail(
            "hip_assembly_runtime_handle_leak",
            "/",
            "Serialized evaluation receipt contains a runtime handle term.",
        )
    if receipt.receipt_hash != canonical_hash(
        _evaluation_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_assembly_evaluation_receipt_hash_mismatch",
            "/receipt_hash",
            "Evaluation receipt hash is stale.",
        )
    _validate_evaluation_semantics(receipt)
    if expected_context is not None:
        if type(expected_context) is not HipAssemblyExecutionContext:
            _fail(
                "hip_assembly_expected_context_invalid",
                "/expected_context",
                "Expected exact HipAssemblyExecutionContext.",
            )
        if (
            receipt.context_id != expected_context.context_id
            or receipt.receipt_hash
            != expected_context.opening_evaluation.receipt.receipt_hash
            or receipt.bindings != expected_context.opening_receipt.bindings
        ):
            _fail(
                "hip_assembly_evaluation_context_binding_mismatch",
                "/context_id",
                "Evaluation is not the context's opening execution.",
            )
    return receipt


def validate_hip_assembly_evaluation(
    evaluation: HipAssemblyEvaluation,
    *,
    expected_context: HipAssemblyExecutionContext | None = None,
    expected_buffers: SolverModelBuffers | None = None,
    expected_source_plan: ExecutionPlanV2 | None = None,
    expected_assembly_plan: HipAssemblyPlanV1 | None = None,
    expected_kernel: Any | None = None,
) -> HipAssemblyEvaluation:
    if type(evaluation) is not HipAssemblyEvaluation:
        _fail(
            "hip_assembly_evaluation_type_invalid",
            "/",
            "Expected an exact HipAssemblyEvaluation.",
        )
    validate_hip_assembly_evaluation_receipt(
        evaluation.receipt, expected_context=expected_context
    )
    values = evaluation.csr_values
    if values is None:
        if evaluation.receipt.csr_values_data_hash is not None:
            _fail(
                "hip_assembly_evaluation_value_missing",
                "/csr_values",
                "Receipt describes absent CSR values.",
            )
    else:
        if (
            type(values) is not np.ndarray
            or values.dtype.str != "<f8"
            or values.shape != (evaluation.receipt.work.csr_nnz,)
            or not values.flags.c_contiguous
            or not has_immutable_bytes_backing(values)
            or not np.all(np.isfinite(values))
        ):
            _fail(
                "hip_assembly_evaluation_value_invalid",
                "/csr_values",
                "CSR verification values violate immutable FP64 storage.",
            )
        if any(
            (
                evaluation.receipt.csr_values_dtype != "<f8",
                evaluation.receipt.csr_values_shape != values.shape,
                evaluation.receipt.csr_values_byte_length != int(values.nbytes),
                evaluation.receipt.csr_values_data_hash != array_data_hash(values),
            )
        ):
            _fail(
                "hip_assembly_evaluation_value_hash_mismatch",
                "/csr_values",
                "CSR verification values differ from their receipt.",
            )

    if expected_buffers is not None:
        validate_solver_model_buffers(expected_buffers)
        if (
            evaluation.receipt.bindings.solver_artifact_hash
            != expected_buffers.artifact_hash
        ):
            _fail(
                "hip_assembly_evaluation_buffer_binding_mismatch",
                "/bindings",
                "Evaluation is bound to different model buffers.",
            )
    if expected_source_plan is not None:
        validate_execution_plan_v2(
            expected_source_plan, expected_buffers=expected_buffers
        )
        if (
            evaluation.receipt.bindings.source_execution_plan_hash
            != expected_source_plan.plan_hash
        ):
            _fail(
                "hip_assembly_evaluation_source_plan_binding_mismatch",
                "/bindings",
                "Evaluation is bound to a different source plan.",
            )
        if values is not None:
            expected_parity = _parity_report(
                values,
                expected_source_plan.array("global_stiffness_csr_values"),
            )
            if evaluation.receipt.parity != expected_parity:
                _fail(
                    "hip_assembly_evaluation_parity_mismatch",
                    "/parity",
                    "Stored parity does not replay from expected values.",
                )
    if expected_assembly_plan is not None:
        if expected_source_plan is None:
            _fail(
                "hip_assembly_expected_input_invalid",
                "/expected_source_plan",
                "expected_assembly_plan requires expected_source_plan.",
            )
        validate_hip_assembly_plan_v1(
            expected_assembly_plan,
            expected_buffers=expected_buffers,
            expected_execution_plan=expected_source_plan,
        )
        if (
            evaluation.receipt.bindings.assembly_plan_hash
            != expected_assembly_plan.assembly_plan_hash
        ):
            _fail(
                "hip_assembly_evaluation_assembly_plan_binding_mismatch",
                "/bindings",
                "Evaluation is bound to a different assembly plan.",
            )
    if expected_kernel is not None:
        binding = _kernel_binding(expected_kernel, None)
        if binding.identity_hash != evaluation.receipt.bindings.kernel_identity_hash:
            _fail(
                "hip_assembly_evaluation_kernel_binding_mismatch",
                "/bindings",
                "Evaluation kernel binding changed.",
            )
        if (
            evaluation.receipt.evidence_scope == "native_hiprtc"
            and expected_context is None
        ):
            _fail(
                "hip_assembly_evaluation_native_context_required",
                "/evidence_scope",
                "Standalone kernel identity cannot prove native ownership.",
            )
    if all(
        value is not None
        for value in (
            expected_buffers,
            expected_source_plan,
            expected_assembly_plan,
            expected_kernel,
        )
    ):
        checked_kernel = _kernel_binding(expected_kernel, None)
        expected_bindings = _bindings(
            expected_buffers,
            expected_source_plan,
            expected_assembly_plan,
            evaluation.receipt.bindings.verification_requested,
            checked_kernel.identity_hash,
            evaluation.receipt.bindings.device_ordinal,
        )
        if evaluation.receipt.bindings != expected_bindings:
            _fail(
                "hip_assembly_evaluation_binding_mismatch",
                "/bindings",
                "Evaluation bindings do not fully replay from expected inputs.",
            )
        expected_context_id = _context_id(
            expected_buffers,
            expected_source_plan,
            expected_assembly_plan,
            checked_kernel,
            evaluation.receipt.evidence_scope,
            evaluation.receipt.bindings.device_ordinal,
            evaluation.receipt.bindings.verification_requested,
        )
        expected_operator_id = _operator_id(
            expected_context_id,
            expected_source_plan,
            expected_assembly_plan,
            checked_kernel,
        )
        expected_execution_id = _execution_id(
            expected_context_id,
            expected_operator_id,
            evaluation.receipt.bindings.verification_requested,
        )
        if any(
            (
                evaluation.receipt.context_id != expected_context_id,
                evaluation.receipt.operator_id != expected_operator_id,
                evaluation.receipt.execution_id != expected_execution_id,
                evaluation.receipt.work
                != _work(expected_source_plan, expected_assembly_plan),
            )
        ):
            _fail(
                "hip_assembly_evaluation_identity_mismatch",
                "/execution_id",
                "Evaluation identities/work do not replay from expected inputs.",
            )
        if evaluation.receipt.status in (
            "verified",
            "assembled_unverified",
            "parity_failed",
        ) and evaluation.receipt.telemetry_delta != _successful_assembly_delta(
            _dimensions(expected_buffers, expected_source_plan),
            evaluation.receipt.bindings.verification_requested,
        ):
            _fail(
                "hip_assembly_evaluation_telemetry_replay_mismatch",
                "/telemetry_delta",
                "Successful telemetry does not replay from expected dimensions.",
            )
    return evaluation


def _build_context_receipt(
    *,
    status: ContextStatus,
    context_id: str,
    actual_backend: str | None,
    evidence_scope: EvidenceScope,
    reason: HipAssemblyReason | None,
    base_context_receipt_hash: str,
    evaluation_receipt_hash: str,
    bindings: HipAssemblyBindings,
    kernel: HipAssemblyKernelBinding | None,
    device: HipAssemblyDevice | None,
    dimensions: HipAssemblyDimensions,
    child_buffers: tuple[HipAssemblyBufferView, ...],
    operator_view: HipAssemblyOperatorView | None,
    telemetry: HipAssemblyTelemetry,
    claims: HipAssemblyClaims,
) -> HipAssemblyContextReceipt:
    draft = HipAssemblyContextReceipt(
        status=status,
        context_id=context_id,
        actual_backend=actual_backend,
        evidence_scope=evidence_scope,
        promotion_eligible=False,
        reason=reason,
        base_context_receipt_hash=base_context_receipt_hash,
        assembly_evaluation_receipt_hash=evaluation_receipt_hash,
        bindings=bindings,
        kernel=kernel,
        kernel_ownership="context",
        device=device,
        dimensions=dimensions,
        child_buffers=child_buffers,
        operator_view=operator_view,
        telemetry=telemetry,
        claims=claims,
        context_receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        context_receipt_hash=canonical_hash(
            _context_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_assembly_context_receipt(receipt)


def _build_evaluation(
    *,
    status: EvaluationStatus,
    execution_id: str,
    context_id: str,
    evidence_scope: EvidenceScope,
    reason: HipAssemblyReason | None,
    bindings: HipAssemblyBindings,
    operator_id: str,
    device_error_code: int | None,
    csr_values: np.ndarray | None,
    telemetry_delta: HipAssemblyTelemetry,
    parity: HipAssemblyParityReport | None,
    work: HipAssemblyWorkReceipt,
) -> HipAssemblyEvaluation:
    executed = status in ("verified", "assembled_unverified", "parity_failed")
    verified = status == "verified"
    descriptor = (
        (
            "<f8",
            tuple(int(value) for value in csr_values.shape),
            int(csr_values.nbytes),
            array_data_hash(csr_values),
        )
        if csr_values is not None
        else (None, None, None, None)
    )
    draft = HipAssemblyEvaluationReceipt(
        status=status,
        execution_id=execution_id,
        context_id=context_id,
        actual_backend=_actual_backend(evidence_scope) if executed else None,
        evidence_scope=evidence_scope,
        promotion_eligible=False,
        reason=reason,
        bindings=bindings,
        operator_id=operator_id,
        device_error_code=device_error_code,
        csr_values_dtype=descriptor[0],
        csr_values_shape=descriptor[1],
        csr_values_byte_length=descriptor[2],
        csr_values_data_hash=descriptor[3],
        telemetry_delta=telemetry_delta,
        parity=parity,
        work=work,
        claims=HipAssemblyClaims(
            device_element_contributions_executed=executed,
            device_segmented_gather_executed=executed,
            device_csr_operator_resident=executed,
            cpu_reference_parity_verified=verified,
            native_hiprtc_kernel_loaded=(
                executed and evidence_scope == "native_hiprtc"
            ),
        ),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_evaluation_payload(draft, include_hash=False)),
    )
    evaluation = HipAssemblyEvaluation(receipt, csr_values)
    return validate_hip_assembly_evaluation(evaluation)


def _context_payload(
    receipt: HipAssemblyContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_ASSEMBLY_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_ASSEMBLY_CAPABILITY_PROFILE,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "requested_backend": "hip_rtc",
        "actual_backend": receipt.actual_backend,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "base_context_receipt_hash": receipt.base_context_receipt_hash,
        "assembly_evaluation_receipt_hash": (receipt.assembly_evaluation_receipt_hash),
        "bindings": receipt.bindings.to_dict(),
        "kernel": None if receipt.kernel is None else receipt.kernel.to_dict(),
        "kernel_ownership": receipt.kernel_ownership,
        "device": None if receipt.device is None else receipt.device.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "child_buffers": [view.to_dict() for view in receipt.child_buffers],
        "operator_view": (
            None if receipt.operator_view is None else receipt.operator_view.to_dict()
        ),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _evaluation_payload(
    receipt: HipAssemblyEvaluationReceipt, *, include_hash: bool
) -> dict[str, Any]:
    csr_values = None
    if receipt.csr_values_data_hash is not None:
        csr_values = {
            "dtype": receipt.csr_values_dtype,
            "shape": list(receipt.csr_values_shape or ()),
            "byte_length": receipt.csr_values_byte_length,
            "data_hash": receipt.csr_values_data_hash,
        }
    payload: dict[str, Any] = {
        "schema_version": HIP_ASSEMBLY_EVALUATION_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_ASSEMBLY_CAPABILITY_PROFILE,
        "status": receipt.status,
        "execution_id": receipt.execution_id,
        "context_id": receipt.context_id,
        "requested_backend": "hip_rtc",
        "actual_backend": receipt.actual_backend,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "operator_id": receipt.operator_id,
        "device_error_code": receipt.device_error_code,
        "csr_values": csr_values,
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "parity": None if receipt.parity is None else receipt.parity.to_dict(),
        "work": receipt.work.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _operator_view_payload(
    view: HipAssemblyOperatorView, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "context_id": view.context_id,
        "operator_id": view.operator_id,
        "source_execution_plan_hash": view.source_execution_plan_hash,
        "assembly_plan_hash": view.assembly_plan_hash,
        "kernel_identity_hash": view.kernel_identity_hash,
        "dtype": view.dtype,
        "shape": list(view.shape),
        "byte_length": view.byte_length,
        "csr_nnz": view.csr_nnz,
        "device_ordinal": view.device_ordinal,
        "memory_space": view.memory_space,
        "access": view.access,
        "lifetime": view.lifetime,
        "ordering_domain": view.ordering_domain,
        "verification_data_hash": view.verification_data_hash,
    }
    if include_hash:
        payload["metadata_hash"] = view.metadata_hash
    return payload


def _validate_context_object_types(receipt: HipAssemblyContextReceipt) -> None:
    if (
        type(receipt.bindings) is not HipAssemblyBindings
        or (
            receipt.reason is not None and type(receipt.reason) is not HipAssemblyReason
        )
        or (
            receipt.kernel is not None
            and type(receipt.kernel) is not HipAssemblyKernelBinding
        )
        or (
            receipt.device is not None and type(receipt.device) is not HipAssemblyDevice
        )
        or type(receipt.dimensions) is not HipAssemblyDimensions
        or type(receipt.child_buffers) is not tuple
        or any(
            type(view) is not HipAssemblyBufferView for view in receipt.child_buffers
        )
        or (
            receipt.operator_view is not None
            and type(receipt.operator_view) is not HipAssemblyOperatorView
        )
        or type(receipt.telemetry) is not HipAssemblyTelemetry
        or type(receipt.claims) is not HipAssemblyClaims
    ):
        _fail(
            "hip_assembly_context_nested_type_invalid",
            "/",
            "Context receipt requires exact immutable nested record types.",
        )
    if any(
        type(value) is not str
        for value in (
            receipt.status,
            receipt.context_id,
            receipt.evidence_scope,
            receipt.base_context_receipt_hash,
            receipt.assembly_evaluation_receipt_hash,
            receipt.kernel_ownership,
            receipt.context_receipt_hash,
        )
    ) or (
        receipt.actual_backend is not None and type(receipt.actual_backend) is not str
    ):
        _fail(
            "hip_assembly_context_scalar_type_invalid",
            "/",
            "Context scalar strings must use exact built-in types.",
        )
    if type(receipt.promotion_eligible) is not bool:
        _fail(
            "hip_assembly_context_scalar_type_invalid",
            "/promotion_eligible",
            "Promotion flag must be an exact bool.",
        )
    _validate_nested_record_types(
        receipt.bindings,
        receipt.kernel,
        receipt.device,
        receipt.dimensions,
        receipt.child_buffers,
        receipt.operator_view,
        receipt.telemetry,
        receipt.claims,
        receipt.reason,
    )


def _validate_evaluation_object_types(
    receipt: HipAssemblyEvaluationReceipt,
) -> None:
    if (
        type(receipt.bindings) is not HipAssemblyBindings
        or (
            receipt.reason is not None and type(receipt.reason) is not HipAssemblyReason
        )
        or type(receipt.telemetry_delta) is not HipAssemblyTelemetry
        or (
            receipt.parity is not None
            and type(receipt.parity) is not HipAssemblyParityReport
        )
        or type(receipt.work) is not HipAssemblyWorkReceipt
        or type(receipt.claims) is not HipAssemblyClaims
    ):
        _fail(
            "hip_assembly_evaluation_nested_type_invalid",
            "/",
            "Evaluation receipt requires exact immutable nested record types.",
        )
    if any(
        type(value) is not str
        for value in (
            receipt.status,
            receipt.execution_id,
            receipt.context_id,
            receipt.evidence_scope,
            receipt.operator_id,
            receipt.receipt_hash,
        )
    ) or (
        receipt.actual_backend is not None and type(receipt.actual_backend) is not str
    ):
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/",
            "Evaluation scalar strings must use exact built-in types.",
        )
    if type(receipt.promotion_eligible) is not bool:
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/promotion_eligible",
            "Promotion flag must be an exact bool.",
        )
    if (
        receipt.device_error_code is not None
        and type(receipt.device_error_code) is not int
    ):
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/device_error_code",
            "Device error code must be an exact integer.",
        )
    if receipt.csr_values_shape is not None and (
        type(receipt.csr_values_shape) is not tuple
        or any(type(value) is not int for value in receipt.csr_values_shape)
    ):
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/csr_values/shape",
            "CSR shape must be an exact integer tuple.",
        )
    if (
        receipt.csr_values_byte_length is not None
        and type(receipt.csr_values_byte_length) is not int
    ):
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/csr_values/byte_length",
            "CSR byte length must be an exact integer.",
        )
    for value in (
        receipt.csr_values_dtype,
        receipt.csr_values_data_hash,
    ):
        if value is not None and type(value) is not str:
            _fail(
                "hip_assembly_evaluation_scalar_type_invalid",
                "/csr_values",
                "CSR descriptor strings must use exact types.",
            )
    _validate_nested_record_types(
        receipt.bindings,
        None,
        None,
        None,
        (),
        None,
        receipt.telemetry_delta,
        receipt.claims,
        receipt.reason,
    )
    if receipt.parity is not None:
        if type(receipt.parity.csr_values) is not HipAssemblyParityMetric:
            _fail(
                "hip_assembly_evaluation_nested_type_invalid",
                "/parity/csr_values",
                "Parity metric must use its exact type.",
            )
        metric = receipt.parity.csr_values
        if (
            type(metric.count) is not int
            or any(
                type(value) is not float
                for value in (
                    metric.max_abs_error,
                    metric.relative_l2_error,
                    metric.max_scaled_error,
                )
            )
            or type(metric.passed) is not bool
            or type(receipt.parity.structural_zero_count) is not int
            or type(receipt.parity.structural_zeros_exact) is not bool
            or type(receipt.parity.passed) is not bool
        ):
            _fail(
                "hip_assembly_evaluation_scalar_type_invalid",
                "/parity",
                "Parity scalars must use exact numeric types.",
            )
    if any(
        type(value) is not int
        for value in (
            receipt.work.element_count,
            receipt.work.csr_nnz,
            receipt.work.contribution_count,
        )
    ):
        _fail(
            "hip_assembly_evaluation_scalar_type_invalid",
            "/work",
            "Work dimensions must be exact integers.",
        )


def _validate_nested_record_types(
    bindings: HipAssemblyBindings,
    kernel: HipAssemblyKernelBinding | None,
    device: HipAssemblyDevice | None,
    dimensions: HipAssemblyDimensions | None,
    views: tuple[HipAssemblyBufferView, ...],
    operator: HipAssemblyOperatorView | None,
    telemetry: HipAssemblyTelemetry,
    claims: HipAssemblyClaims,
    reason: HipAssemblyReason | None,
) -> None:
    if any(
        type(getattr(bindings, name)) is not str
        for name in bindings.__dataclass_fields__
        if name not in {"verification_requested", "device_ordinal"}
    ) or (
        type(bindings.verification_requested) is not bool
        or type(bindings.device_ordinal) is not int
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/bindings",
            "Binding scalars must use exact built-in types.",
        )
    if reason is not None and (
        type(reason.code) is not str or type(reason.detail) is not str
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/reason",
            "Reason scalars must use exact strings.",
        )
    if kernel is not None:
        for name in kernel.__dataclass_fields__:
            value = getattr(kernel, name)
            expected = (
                int
                if name
                in {
                    "abi_version",
                    "element_block_size",
                    "gather_block_size",
                }
                else str
            )
            if type(value) is not expected:
                _fail(
                    "hip_assembly_nested_scalar_type_invalid",
                    "/kernel",
                    "Kernel binding scalars use invalid types.",
                )
    if device is not None and (
        type(device.ordinal) is not int
        or type(device.runtime_version_raw) is not int
        or type(device.driver_version_raw) is not int
        or type(device.name) is not str
        or type(device.architecture) is not str
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/device",
            "Device scalars use invalid types.",
        )
    if dimensions is not None and any(
        type(getattr(dimensions, name)) is not int
        for name in dimensions.__dataclass_fields__
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/dimensions",
            "Dimensions must be exact integers.",
        )
    for view in views:
        if (
            any(
                type(value) is not str
                for value in (
                    view.name,
                    view.dtype,
                    view.access,
                    view.initial_transfer,
                )
            )
            or type(view.shape) is not tuple
            or any(type(value) is not int for value in view.shape)
            or type(view.byte_length) is not int
            or (view.data_hash is not None and type(view.data_hash) is not str)
        ):
            _fail(
                "hip_assembly_nested_scalar_type_invalid",
                "/child_buffers",
                "Child descriptor scalars use invalid types.",
            )
    if operator is not None:
        if (
            type(operator.shape) is not tuple
            or any(type(value) is not int for value in operator.shape)
            or type(operator.byte_length) is not int
            or type(operator.csr_nnz) is not int
            or type(operator.device_ordinal) is not int
            or any(
                type(getattr(operator, name)) is not str
                for name in operator.__dataclass_fields__
                if name
                not in {
                    "shape",
                    "byte_length",
                    "csr_nnz",
                    "device_ordinal",
                    "verification_data_hash",
                }
            )
            or (
                operator.verification_data_hash is not None
                and type(operator.verification_data_hash) is not str
            )
        ):
            _fail(
                "hip_assembly_nested_scalar_type_invalid",
                "/operator_view",
                "Operator metadata scalars use invalid types.",
            )
    if any(
        type(getattr(telemetry, name)) is not int
        for name in telemetry.__dataclass_fields__
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/telemetry",
            "Telemetry counters must be exact integers.",
        )
    if any(
        type(getattr(claims, name)) is not bool for name in claims.__dataclass_fields__
    ):
        _fail(
            "hip_assembly_nested_scalar_type_invalid",
            "/claims",
            "Claim flags must be exact booleans.",
        )


def _validate_context_semantics(receipt: HipAssemblyContextReceipt) -> None:
    for value in (
        receipt.base_context_receipt_hash,
        receipt.assembly_evaluation_receipt_hash,
        receipt.bindings.model_ir_content_hash,
        receipt.bindings.solver_artifact_hash,
        receipt.bindings.solver_numeric_buffer_hash,
        receipt.bindings.source_execution_plan_hash,
        receipt.bindings.source_operator_hash,
        receipt.bindings.source_numeric_snapshot_hash,
        receipt.bindings.source_symbolic_reuse_hash,
        receipt.bindings.source_partition_hash,
        receipt.bindings.assembly_plan_hash,
        receipt.bindings.assembly_symbolic_payload_hash,
        receipt.bindings.axis_policy_hash,
        receipt.bindings.reverse_map_hash,
        receipt.bindings.kernel_identity_hash,
    ):
        _require_hash(value, "/bindings")
    if (
        receipt.promotion_eligible
        or receipt.bindings.host_csr_values_role
        != "verification_oracle_only_never_uploaded"
        or receipt.bindings.device_ordinal < 0
    ):
        _fail(
            "hip_assembly_claim_boundary_invalid",
            "/bindings",
            "Assembly receipt exceeded its claim boundary.",
        )
    dims = receipt.dimensions
    if any(value <= 0 for value in dims.to_dict().values()):
        _fail(
            "hip_assembly_dimensions_invalid",
            "/dimensions",
            "All assembly dimensions must be positive.",
        )
    if (
        dims.global_dof_count != 6 * dims.node_count
        or dims.contribution_count != 144 * dims.element_count
        or dims.foundation_buffer_count != 16
    ):
        _fail(
            "hip_assembly_dimensions_invalid",
            "/dimensions",
            "Assembly dimensions violate the fixed frame/truss ABI.",
        )
    telemetry = receipt.telemetry
    if any(value < 0 for value in telemetry.to_dict().values()):
        _fail(
            "hip_assembly_context_telemetry_invalid",
            "/telemetry",
            "Telemetry cannot be negative.",
        )
    if (
        telemetry.fallback_count != 0
        or telemetry.blocking_copy_count != 0
        or telemetry.host_csr_values_h2d_bytes != 0
        or telemetry.child_allocation_success_count
        > telemetry.child_allocation_attempt_count
        or telemetry.child_deallocation_success_count
        > telemetry.child_deallocation_attempt_count
        or telemetry.child_initial_h2d_success_count
        > telemetry.child_initial_h2d_attempt_count
        or telemetry.kernel_launch_count > telemetry.kernel_launch_attempt_count
        or telemetry.d2h_operation_success_count > telemetry.d2h_operation_attempt_count
        or telemetry.d2h_operation_count != telemetry.d2h_operation_success_count
        or telemetry.d2h_bytes != telemetry.d2h_bytes_succeeded
        or telemetry.d2h_bytes_succeeded > telemetry.d2h_bytes_attempted
        or telemetry.assembly_sync_success_count > telemetry.assembly_sync_attempt_count
        or telemetry.assembly_sync_count != telemetry.assembly_sync_success_count
        or telemetry.current_device_payload_bytes > telemetry.peak_device_payload_bytes
    ):
        _fail(
            "hip_assembly_context_telemetry_invalid",
            "/telemetry",
            "Context telemetry is internally inconsistent.",
        )
    if receipt.kernel is not None:
        _validate_kernel_binding(receipt.kernel)
        if receipt.kernel.identity_hash != receipt.bindings.kernel_identity_hash:
            _fail(
                "hip_assembly_kernel_binding_mismatch",
                "/bindings/kernel_identity_hash",
                "Receipt bindings and kernel snapshot differ.",
            )
    if (
        receipt.device is not None
        and receipt.device.ordinal != receipt.bindings.device_ordinal
    ):
        _fail(
            "hip_assembly_context_device_binding_mismatch",
            "/device/ordinal",
            "Device identity and binding ordinal differ.",
        )
    if receipt.operator_view is not None:
        receipt.operator_view.to_dict()
        if (
            receipt.operator_view.context_id != receipt.context_id
            or receipt.operator_view.source_execution_plan_hash
            != receipt.bindings.source_execution_plan_hash
            or receipt.operator_view.assembly_plan_hash
            != receipt.bindings.assembly_plan_hash
            or receipt.kernel is None
            or receipt.operator_view.kernel_identity_hash
            != receipt.kernel.identity_hash
            or receipt.operator_view.csr_nnz != dims.csr_nnz
            or receipt.operator_view.shape != (dims.csr_nnz,)
            or receipt.operator_view.byte_length != 8 * dims.csr_nnz
            or receipt.operator_view.device_ordinal != receipt.bindings.device_ordinal
            or receipt.operator_view.operator_id
            != _operator_id_from_hashes(
                receipt.context_id,
                receipt.bindings.source_execution_plan_hash,
                receipt.bindings.assembly_plan_hash,
                receipt.bindings.kernel_identity_hash,
            )
            or (receipt.operator_view.verification_data_hash is not None)
            != receipt.bindings.verification_requested
        ):
            _fail(
                "hip_assembly_operator_view_binding_invalid",
                "/operator_view",
                "Operator-view metadata is bound to different inputs.",
            )

    ready = receipt.status == "context_ready"
    if ready:
        if (
            receipt.reason is not None
            or receipt.actual_backend is None
            or receipt.kernel is None
            or receipt.device is None
            or receipt.operator_view is None
            or tuple(view.name for view in receipt.child_buffers) != _CHILD_BUFFER_ORDER
        ):
            _fail(
                "hip_assembly_context_status_invalid",
                "/status",
                "Ready context is missing exact bindings.",
            )
        _validate_ready_telemetry(receipt)
        if not all(
            (
                receipt.claims.device_element_contributions_executed,
                receipt.claims.device_segmented_gather_executed,
                receipt.claims.device_csr_operator_resident,
            )
        ):
            _fail(
                "hip_assembly_context_claim_invalid",
                "/claims",
                "Ready context must assert only completed assembly claims.",
            )
        if (
            receipt.claims.cpu_reference_parity_verified
            != receipt.bindings.verification_requested
        ):
            _fail(
                "hip_assembly_context_claim_invalid",
                "/claims/cpu_reference_parity_verified",
                "Verification claim differs from requested successful mode.",
            )
    else:
        if any(
            (
                receipt.claims.device_element_contributions_executed,
                receipt.claims.device_segmented_gather_executed,
                receipt.claims.device_csr_operator_resident,
                receipt.claims.cpu_reference_parity_verified,
                receipt.claims.native_hiprtc_kernel_loaded,
            )
        ):
            _fail(
                "hip_assembly_context_claim_invalid",
                "/claims",
                "Non-ready context cannot expose execution/residency claims.",
            )
        if (
            receipt.status in ("poisoned", "cleanup_failed", "unavailable")
            and receipt.reason is None
        ):
            _fail(
                "hip_assembly_context_reason_missing",
                "/reason",
                "Failed context status requires a reason.",
            )
    if (
        receipt.status == "context_closed"
        and telemetry.current_device_payload_bytes != 0
    ):
        _fail(
            "hip_assembly_context_closed_payload_invalid",
            "/telemetry/current_device_payload_bytes",
            "Closed context retains tracked device payload.",
        )
    if receipt.evidence_scope == "injected_test_double":
        if (
            receipt.actual_backend not in ("test_double", None)
            or receipt.claims.native_hiprtc_kernel_loaded
        ):
            _fail(
                "hip_assembly_evidence_scope_invalid",
                "/evidence_scope",
                "Injected execution cannot claim native evidence.",
            )
    elif ready:
        if (
            receipt.actual_backend != "hip"
            or not receipt.claims.native_hiprtc_kernel_loaded
        ):
            _fail(
                "hip_assembly_native_claim_invalid",
                "/claims/native_hiprtc_kernel_loaded",
                "Native ready context lacks linked native evidence.",
            )
        if receipt.kernel is not None and (
            receipt.kernel.runtime_library_discovery_source == "injected"
            or receipt.kernel.hiprtc_library_discovery_source == "injected"
        ):
            _fail(
                "hip_assembly_native_evidence_invalid",
                "/kernel",
                "Native evidence includes an injected library.",
            )


def _validate_ready_telemetry(receipt: HipAssemblyContextReceipt) -> None:
    dims = receipt.dimensions
    telemetry = receipt.telemetry
    child_bytes = _child_payload_bytes(dims)
    upload_bytes = _initial_upload_bytes(dims)
    verify_bytes = 8 * dims.csr_nnz if receipt.bindings.verification_requested else 0
    expected = {
        "h2d_bytes": dims.foundation_payload_bytes + upload_bytes,
        "d2h_bytes": 4 + verify_bytes,
        "h2d_operation_count": dims.foundation_buffer_count + 6,
        "d2h_operation_count": 1 + int(receipt.bindings.verification_requested),
        "d2h_operation_attempt_count": 1 + int(receipt.bindings.verification_requested),
        "d2h_operation_success_count": 1 + int(receipt.bindings.verification_requested),
        "d2h_bytes_attempted": 4 + verify_bytes,
        "d2h_bytes_succeeded": 4 + verify_bytes,
        "blocking_copy_count": 0,
        "explicit_sync_count": 2,
        "allocation_count": dims.foundation_buffer_count + 8,
        "deallocation_count": 0,
        "current_device_payload_bytes": dims.foundation_payload_bytes + child_bytes,
        "peak_device_payload_bytes": dims.foundation_payload_bytes + child_bytes,
        "kernel_launch_attempt_count": 2,
        "kernel_launch_count": 2,
        "fallback_count": 0,
        "child_allocation_attempt_count": 8,
        "child_allocation_success_count": 8,
        "child_deallocation_attempt_count": 0,
        "child_deallocation_success_count": 0,
        "child_initial_h2d_attempt_count": 6,
        "child_initial_h2d_success_count": 6,
        "assembly_sync_count": 1,
        "assembly_sync_attempt_count": 1,
        "assembly_sync_success_count": 1,
        "error_flag_d2h_bytes": 4,
        "verification_csr_d2h_bytes": verify_bytes,
        "host_csr_values_h2d_bytes": 0,
    }
    if telemetry.to_dict() != expected:
        _fail(
            "hip_assembly_ready_telemetry_mismatch",
            "/telemetry",
            "Ready telemetry does not exactly replay from bound dimensions.",
        )
    expected_views = _expected_view_specs(dims)
    for view in receipt.child_buffers:
        actual = view.to_dict()
        expected_view = expected_views[view.name]
        expected_hash = expected_view.pop("data_hash")
        actual_hash = actual.pop("data_hash")
        hash_valid = (
            type(actual_hash) is str
            and _HASH_PATTERN.fullmatch(actual_hash) is not None
            if expected_hash == "__hash__"
            else actual_hash is None
        )
        if actual != expected_view or not hash_valid:
            _fail(
                "hip_assembly_child_buffer_invalid",
                f"/child_buffers/{view.name}",
                "Child buffer metadata does not replay from dimensions.",
            )


def _validate_evaluation_semantics(
    receipt: HipAssemblyEvaluationReceipt,
) -> None:
    for value in (
        receipt.bindings.model_ir_content_hash,
        receipt.bindings.solver_artifact_hash,
        receipt.bindings.solver_numeric_buffer_hash,
        receipt.bindings.source_execution_plan_hash,
        receipt.bindings.source_operator_hash,
        receipt.bindings.source_numeric_snapshot_hash,
        receipt.bindings.source_symbolic_reuse_hash,
        receipt.bindings.source_partition_hash,
        receipt.bindings.assembly_plan_hash,
        receipt.bindings.assembly_symbolic_payload_hash,
        receipt.bindings.axis_policy_hash,
        receipt.bindings.reverse_map_hash,
        receipt.bindings.kernel_identity_hash,
    ):
        _require_hash(value, "/bindings")
    if receipt.promotion_eligible:
        _fail(
            "hip_assembly_evaluation_promotion_invalid",
            "/promotion_eligible",
            "Unsigned assembly evidence is non-promoting.",
        )
    work = receipt.work
    if (
        work.element_count <= 0
        or work.csr_nnz <= 0
        or work.contribution_count != 144 * work.element_count
    ):
        _fail(
            "hip_assembly_work_invalid",
            "/work",
            "Assembly work dimensions are invalid.",
        )
    delta = receipt.telemetry_delta
    if any(value < 0 for value in delta.to_dict().values()) or any(
        (
            delta.fallback_count != 0,
            delta.blocking_copy_count != 0,
            delta.host_csr_values_h2d_bytes != 0,
            delta.d2h_operation_success_count > delta.d2h_operation_attempt_count,
            delta.d2h_operation_count != delta.d2h_operation_success_count,
            delta.d2h_bytes != delta.d2h_bytes_succeeded,
            delta.d2h_bytes_succeeded > delta.d2h_bytes_attempted,
            delta.assembly_sync_success_count > delta.assembly_sync_attempt_count,
            delta.assembly_sync_count != delta.assembly_sync_success_count,
        )
    ):
        _fail(
            "hip_assembly_evaluation_telemetry_invalid",
            "/telemetry_delta",
            "Evaluation telemetry violates no-fallback/no-CSR-H2D policy.",
        )
    executed = receipt.status in (
        "verified",
        "assembled_unverified",
        "parity_failed",
    )
    if executed:
        verify = receipt.bindings.verification_requested
        if any(
            (
                receipt.reason is not None,
                receipt.actual_backend is None,
                receipt.device_error_code != 0,
                delta.kernel_launch_attempt_count != 2,
                delta.kernel_launch_count != 2,
                delta.assembly_sync_count != 1,
                delta.error_flag_d2h_bytes != 4,
                delta.verification_csr_d2h_bytes != (8 * work.csr_nnz if verify else 0),
                delta.d2h_bytes != 4 + (8 * work.csr_nnz if verify else 0),
                delta.d2h_operation_count != 1 + int(verify),
                delta.d2h_operation_attempt_count != 1 + int(verify),
                delta.d2h_operation_success_count != 1 + int(verify),
                delta.d2h_bytes_attempted != 4 + (8 * work.csr_nnz if verify else 0),
                delta.d2h_bytes_succeeded != 4 + (8 * work.csr_nnz if verify else 0),
                delta.assembly_sync_attempt_count != 1,
                delta.assembly_sync_success_count != 1,
                delta.h2d_operation_count != 6,
                delta.h2d_bytes <= 0,
                delta.allocation_count != 8,
                delta.deallocation_count != 0,
                delta.current_device_payload_bytes <= 0,
                delta.current_device_payload_bytes != delta.peak_device_payload_bytes,
                delta.child_allocation_attempt_count != 8,
                delta.child_allocation_success_count != 8,
                delta.child_deallocation_attempt_count != 0,
                delta.child_deallocation_success_count != 0,
                delta.child_initial_h2d_attempt_count != 6,
                delta.child_initial_h2d_success_count != 6,
                not receipt.claims.device_element_contributions_executed,
                not receipt.claims.device_segmented_gather_executed,
                not receipt.claims.device_csr_operator_resident,
            )
        ):
            _fail(
                "hip_assembly_evaluation_execution_invalid",
                "/status",
                "Executed evaluation does not replay exact device work.",
            )
        if verify:
            if (
                receipt.csr_values_data_hash is None
                or receipt.parity is None
                or receipt.status
                != ("verified" if receipt.parity.passed else "parity_failed")
                or receipt.claims.cpu_reference_parity_verified != receipt.parity.passed
            ):
                _fail(
                    "hip_assembly_evaluation_parity_invalid",
                    "/parity",
                    "Verification result is internally inconsistent.",
                )
        elif any(
            (
                receipt.status != "assembled_unverified",
                receipt.csr_values_data_hash is not None,
                receipt.parity is not None,
                receipt.claims.cpu_reference_parity_verified,
            )
        ):
            _fail(
                "hip_assembly_evaluation_unverified_invalid",
                "/status",
                "No-download execution carries verification evidence.",
            )
    else:
        if any(
            (
                receipt.reason is None,
                receipt.actual_backend is not None,
                receipt.csr_values_data_hash is not None,
                receipt.parity is not None,
                receipt.claims.device_element_contributions_executed,
                receipt.claims.device_segmented_gather_executed,
                receipt.claims.device_csr_operator_resident,
                receipt.claims.cpu_reference_parity_verified,
                receipt.claims.native_hiprtc_kernel_loaded,
            )
        ):
            _fail(
                "hip_assembly_evaluation_unavailable_invalid",
                "/status",
                "Unavailable evaluation exposes success claims or outputs.",
            )
    if receipt.csr_values_data_hash is not None:
        if (
            receipt.csr_values_dtype != "<f8"
            or receipt.csr_values_shape != (work.csr_nnz,)
            or receipt.csr_values_byte_length != 8 * work.csr_nnz
        ):
            _fail(
                "hip_assembly_evaluation_descriptor_invalid",
                "/csr_values",
                "CSR verification descriptor is invalid.",
            )
        _require_hash(receipt.csr_values_data_hash, "/csr_values/data_hash")
    elif any(
        value is not None
        for value in (
            receipt.csr_values_dtype,
            receipt.csr_values_shape,
            receipt.csr_values_byte_length,
        )
    ):
        _fail(
            "hip_assembly_evaluation_descriptor_invalid",
            "/csr_values",
            "Null CSR output has a partial descriptor.",
        )
    if receipt.parity is not None:
        _validate_parity(receipt.parity)
    if receipt.evidence_scope == "injected_test_double":
        if (
            receipt.actual_backend not in ("test_double", None)
            or receipt.claims.native_hiprtc_kernel_loaded
        ):
            _fail(
                "hip_assembly_evidence_scope_invalid",
                "/evidence_scope",
                "Injected evaluation cannot claim native evidence.",
            )
    elif executed and (
        receipt.actual_backend != "hip"
        or not receipt.claims.native_hiprtc_kernel_loaded
    ):
        _fail(
            "hip_assembly_native_claim_invalid",
            "/claims/native_hiprtc_kernel_loaded",
            "Native evaluation is not linked to native evidence.",
        )


def _validate_parity(report: HipAssemblyParityReport) -> None:
    metric = report.csr_values
    if (
        metric.count <= 0
        or any(
            not math.isfinite(value) or value < 0.0
            for value in (
                metric.max_abs_error,
                metric.relative_l2_error,
                metric.max_scaled_error,
            )
        )
        or report.structural_zero_count < 0
    ):
        _fail(
            "hip_assembly_parity_metric_invalid",
            "/parity",
            "Parity metric is invalid.",
        )
    passed = (
        metric.relative_l2_error <= _PARITY_TOLERANCE
        and metric.max_scaled_error <= _PARITY_TOLERANCE
    )
    if metric.passed != passed or report.passed != (
        passed and report.structural_zeros_exact
    ):
        _fail(
            "hip_assembly_parity_status_invalid",
            "/parity/passed",
            "Parity status does not replay from its metrics.",
        )


def _preflight(
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    *,
    verify_cpu_parity: bool,
    device_ordinal: int,
    architecture: str | None,
    memory_budget_bytes: int | None,
    rtc_kernel: Any | None,
) -> None:
    try:
        validate_solver_model_buffers(buffers)
        validate_execution_plan_v2(source_plan, expected_buffers=buffers)
        validate_hip_assembly_plan_v1(
            assembly_plan,
            expected_buffers=buffers,
            expected_execution_plan=source_plan,
        )
    except Exception as exc:
        raise HipAssemblyContextError(
            "hip_assembly_binding_invalid", "/bindings", _exception_detail(exc)
        ) from exc
    if type(verify_cpu_parity) is not bool:
        _fail(
            "hip_assembly_verification_mode_invalid",
            "/verify_cpu_parity",
            "verify_cpu_parity must be an exact bool.",
        )
    if type(device_ordinal) is not int or device_ordinal < 0:
        _fail(
            "hip_assembly_device_ordinal_invalid",
            "/device_ordinal",
            "device_ordinal must be a non-negative exact integer.",
        )
    if memory_budget_bytes is not None and (
        type(memory_budget_bytes) is not int or memory_budget_bytes <= 0
    ):
        _fail(
            "hip_assembly_memory_budget_invalid",
            "/memory_budget_bytes",
            "memory_budget_bytes must be a positive exact integer.",
        )
    if rtc_kernel is None and architecture is None:
        _fail(
            "hip_assembly_architecture_required",
            "/architecture",
            "Native HIPRTC compilation requires a gfx architecture.",
        )
    if architecture is not None and (
        type(architecture) is not str or _ARCH_PATTERN.fullmatch(architecture) is None
    ):
        _fail(
            "hip_assembly_architecture_invalid",
            "/architecture",
            "Architecture must be one plain gfx target.",
        )
    arrays = _child_arrays(source_plan, assembly_plan)
    specs = {
        "csr_row_ptr": ("<i4", (source_plan.dof_count + 1,)),
        "csr_column_indices": ("<i4", (source_plan.nnz,)),
        "reference_axis_code": ("|u1", (source_plan.element_count,)),
        "reverse_segment_offsets": ("<i4", (source_plan.nnz + 1,)),
        "reverse_contribution_indices": (
            "<i4",
            (assembly_plan.contribution_count,),
        ),
        "element_contributions": (
            "<f8",
            (assembly_plan.contribution_count,),
        ),
        "csr_values": ("<f8", (source_plan.nnz,)),
        "error_flag": ("<i4", (1,)),
    }
    if tuple(arrays) != _CHILD_BUFFER_ORDER:
        _fail(
            "hip_assembly_child_order_invalid",
            "/child_buffers",
            "Child array order differs from the fixed ABI.",
        )
    for name, spec in arrays.items():
        dtype, shape = specs[name]
        if (
            spec.dtype != dtype
            or spec.shape != shape
            or spec.byte_length != int(np.dtype(dtype).itemsize * math.prod(shape))
            or (
                spec.host_backing is not None
                and (
                    type(spec.host_backing) is not np.ndarray
                    or spec.host_backing.dtype.str != dtype
                    or spec.host_backing.shape != shape
                    or not spec.host_backing.flags.c_contiguous
                )
            )
            or ((name in _INITIAL_UPLOAD_NAMES) != (spec.host_backing is not None))
        ):
            _fail(
                "hip_assembly_child_array_invalid",
                f"/child_buffers/{name}",
                "Child array violates the fixed ABI.",
            )
    # The only source-plan arrays admitted into the child upload dictionary are
    # symbolic row/column indices.  Numeric CSR values cannot be selected.
    if any("stiffness" in name for name in arrays):  # pragma: no cover - guard
        _fail(
            "hip_assembly_host_csr_upload_forbidden",
            "/child_buffers",
            "Host stiffness numerics cannot enter the assembly upload set.",
        )


def _child_arrays(
    source_plan: ExecutionPlanV2, assembly_plan: HipAssemblyPlanV1
) -> dict[str, _HipAssemblyChildSpec]:
    def host(array: np.ndarray, access: str = "read_only") -> _HipAssemblyChildSpec:
        return _HipAssemblyChildSpec(
            dtype=array.dtype.str,
            shape=tuple(int(value) for value in array.shape),
            byte_length=int(array.nbytes),
            host_backing=array,
            access=access,
            initial_transfer="async_h2d_before_assembly",
        )

    def device_only(
        dtype: str, shape: tuple[int, ...], access: str
    ) -> _HipAssemblyChildSpec:
        return _HipAssemblyChildSpec(
            dtype=dtype,
            shape=shape,
            byte_length=int(np.dtype(dtype).itemsize * math.prod(shape)),
            host_backing=None,
            access=access,
            initial_transfer="none",
        )

    return {
        "csr_row_ptr": host(source_plan.array("csr_row_ptr")),
        "csr_column_indices": host(source_plan.array("csr_column_indices")),
        "reference_axis_code": host(assembly_plan.array("reference_axis_code")),
        "reverse_segment_offsets": host(assembly_plan.array("reverse_segment_offsets")),
        "reverse_contribution_indices": host(
            assembly_plan.array("reverse_contribution_indices")
        ),
        "element_contributions": device_only(
            "<f8",
            (assembly_plan.contribution_count,),
            "write_then_read",
        ),
        "csr_values": device_only("<f8", (source_plan.nnz,), "write_then_read_only"),
        "error_flag": host(immutable_array(np.zeros(1), dtype="<i4"), "read_write"),
    }


def _allocate_host_staging(
    csr_nnz: int, verify_cpu_parity: bool
) -> tuple[np.ndarray, np.ndarray | None]:
    error = np.empty(1, dtype="<i4")
    values = np.empty(csr_nnz, dtype="<f8") if verify_cpu_parity else None
    return error, values


def _child_buffer_views(
    arrays: dict[str, _HipAssemblyChildSpec],
) -> tuple[HipAssemblyBufferView, ...]:
    return tuple(
        HipAssemblyBufferView(
            name=name,
            dtype=arrays[name].dtype,
            shape=arrays[name].shape,
            byte_length=arrays[name].byte_length,
            data_hash=(
                array_data_hash(arrays[name].host_backing)
                if arrays[name].host_backing is not None
                else None
            ),
            access=arrays[name].access,
            initial_transfer=arrays[name].initial_transfer,
        )
        for name in _CHILD_BUFFER_ORDER
    )


def _dimensions(
    buffers: SolverModelBuffers, source_plan: ExecutionPlanV2
) -> HipAssemblyDimensions:
    return HipAssemblyDimensions(
        node_count=source_plan.node_count,
        element_count=source_plan.element_count,
        material_count=int(buffers.array("material_properties_si").shape[0]),
        section_count=int(buffers.array("section_properties_si").shape[0]),
        global_dof_count=source_plan.dof_count,
        csr_nnz=source_plan.nnz,
        contribution_count=144 * source_plan.element_count,
        foundation_buffer_count=len(buffers.descriptors),
        foundation_payload_bytes=sum(row.byte_length for row in buffers.descriptors),
    )


def _bindings(
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    verify_cpu_parity: bool,
    kernel_identity_hash: str,
    device_ordinal: int,
) -> HipAssemblyBindings:
    return HipAssemblyBindings(
        model_ir_content_hash=buffers.model_ir_content_hash,
        solver_artifact_hash=buffers.artifact_hash,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
        source_execution_plan_hash=source_plan.plan_hash,
        source_operator_hash=source_plan.operator_hash,
        source_numeric_snapshot_hash=source_plan.numeric_snapshot_hash,
        source_symbolic_reuse_hash=source_plan.symbolic_reuse_hash,
        source_partition_hash=source_plan.partition_hash,
        assembly_plan_hash=assembly_plan.assembly_plan_hash,
        assembly_symbolic_payload_hash=assembly_plan.symbolic_payload_hash,
        axis_policy_hash=assembly_plan.axis_policy_hash,
        reverse_map_hash=assembly_plan.reverse_map_hash,
        kernel_identity_hash=kernel_identity_hash,
        device_ordinal=device_ordinal,
        load_pattern_id=buffers.load_pattern_id,
        verification_requested=verify_cpu_parity,
    )


def _work(
    source_plan: ExecutionPlanV2, assembly_plan: HipAssemblyPlanV1
) -> HipAssemblyWorkReceipt:
    return HipAssemblyWorkReceipt(
        element_count=source_plan.element_count,
        csr_nnz=source_plan.nnz,
        contribution_count=assembly_plan.contribution_count,
    )


def _kernel_binding(
    kernel: Any, requested_architecture: str | None
) -> HipAssemblyKernelBinding:
    identity = getattr(kernel, "identity", None)
    if identity is None or not callable(getattr(identity, "to_dict", None)):
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Assembly kernel identity is missing.",
        )
    try:
        manifest = identity.to_dict()
    except Exception as exc:
        raise HipAssemblyContextError(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            _exception_detail(exc),
        ) from exc
    if type(manifest) is not dict:
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel identity manifest must be a plain object.",
        )
    _validate_kernel_identity_manifest(manifest)
    symbols = manifest.get("kernel_symbols")
    geometry = manifest.get("launch_geometry")
    runtime_library = manifest.get("runtime_library")
    hiprtc_library = manifest.get("hiprtc_library")
    if not all(
        type(value) is dict
        for value in (symbols, geometry, runtime_library, hiprtc_library)
    ):
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel identity lacks fixed nested records.",
        )
    architecture = manifest.get("architecture")
    if type(architecture) is not str or _ARCH_PATTERN.fullmatch(architecture) is None:
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity/architecture",
            "Kernel architecture is invalid.",
        )
    if requested_architecture is not None and architecture != requested_architecture:
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity/architecture",
            "Kernel architecture differs from the requested target.",
        )
    binding = HipAssemblyKernelBinding(
        abi_version=manifest["abi_version"],
        element_kernel_symbol=symbols["element_contribution"],
        gather_kernel_symbol=symbols["csr_gather"],
        element_block_size=geometry["element_contribution_block_size"],
        gather_block_size=geometry["csr_gather_block_size"],
        architecture=architecture,
        source_resource=manifest["source_resource"],
        source_sha256=manifest["source_sha256"],
        code_object_sha256=manifest["code_object_sha256"],
        identity_hash=manifest["identity_hash"],
        identity_snapshot_hash=canonical_hash(manifest),
        runtime_library_discovery_source=runtime_library["discovery_source"],
        runtime_library_sha256=runtime_library["sha256"],
        hiprtc_library_discovery_source=hiprtc_library["discovery_source"],
        hiprtc_library_sha256=hiprtc_library["sha256"],
    )
    _validate_kernel_binding(binding)
    if not all(
        callable(getattr(kernel, name, None))
        for name in (
            "launch_element_contributions",
            "launch_csr_gather",
            "close",
        )
    ):
        _fail(
            "hip_assembly_kernel_contract_invalid",
            "/kernel",
            "Kernel lacks the fixed two-launch lifetime API.",
        )
    return binding


def _validate_kernel_identity_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "abi_version",
        "kernel_name",
        "kernel_symbols",
        "launch_geometry",
        "source_resource",
        "source_sha256",
        "compile_options",
        "architecture",
        "hiprtc_version",
        "hiprtc_library",
        "runtime_library",
        "code_object_byte_length",
        "code_object_sha256",
        "identity_hash",
    }
    if set(manifest) != required:
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel identity fields differ from the fixed manifest.",
        )
    symbols = manifest["kernel_symbols"]
    geometry = manifest["launch_geometry"]
    version = manifest["hiprtc_version"]
    rtc_library = manifest["hiprtc_library"]
    runtime_library = manifest["runtime_library"]
    if (
        type(symbols) is not dict
        or set(symbols) != {"element_contribution", "csr_gather"}
        or any(type(value) is not str for value in symbols.values())
        or type(geometry) is not dict
        or set(geometry)
        != {
            "element_contribution_block_size",
            "csr_gather_block_size",
        }
        or any(type(value) is not int for value in geometry.values())
        or type(version) is not dict
        or set(version) != {"major", "minor"}
        or any(type(value) is not int or value < 0 for value in version.values())
    ):
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel nested identity scalars violate exact ABI types.",
        )
    library_keys = {
        "discovery_source",
        "requested_name",
        "loaded_name",
        "resolved_path",
        "sha256",
    }
    for library in (rtc_library, runtime_library):
        if (
            type(library) is not dict
            or set(library) != library_keys
            or any(
                type(library[name]) is not str
                for name in (
                    "discovery_source",
                    "requested_name",
                    "loaded_name",
                    "sha256",
                )
            )
            or (
                library["resolved_path"] is not None
                and type(library["resolved_path"]) is not str
            )
        ):
            _fail(
                "hip_assembly_kernel_identity_invalid",
                "/kernel/identity/libraries",
                "Kernel library identity uses invalid scalar types.",
            )
        _require_hash(library["sha256"], "/kernel/identity/libraries")
    architecture = manifest["architecture"]
    options = manifest["compile_options"]
    expected_source_hash = "sha256:" + hashlib.sha256(_fixed_source()).hexdigest()
    scalar_strings = (
        manifest["schema_version"],
        manifest["kernel_name"],
        manifest["source_resource"],
        manifest["source_sha256"],
        architecture,
        manifest["code_object_sha256"],
        manifest["identity_hash"],
    )
    if (
        any(type(value) is not str for value in scalar_strings)
        or type(manifest["abi_version"]) is not int
        or type(manifest["code_object_byte_length"]) is not int
        or manifest["code_object_byte_length"] <= 0
        or type(options) is not list
        or any(type(value) is not str for value in options)
        or manifest["schema_version"] != HIP_RTC_LINEAR_ASSEMBLY_IDENTITY_SCHEMA_VERSION
        or manifest["abi_version"] != HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION
        or manifest["kernel_name"] != HIP_RTC_LINEAR_ASSEMBLY_KERNEL_NAME
        or manifest["source_resource"]
        != "kernels/engine_v2_linear_frame_truss_assembly_v1.hip.cpp"
        or manifest["source_sha256"] != expected_source_hash
        or options
        != [
            f"--offload-arch={architecture}",
            "-O3",
            "-std=c++17",
        ]
    ):
        _fail(
            "hip_assembly_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel fixed identity values or scalar types are invalid.",
        )
    for value in (
        manifest["source_sha256"],
        manifest["code_object_sha256"],
        manifest["identity_hash"],
    ):
        _require_hash(value, "/kernel/identity")
    identity_payload = dict(manifest)
    claimed_hash = identity_payload.pop("identity_hash")
    if claimed_hash != canonical_hash(identity_payload):
        _fail(
            "hip_assembly_kernel_identity_hash_mismatch",
            "/kernel/identity/identity_hash",
            "Kernel identity hash is stale or forged.",
        )


def _validate_kernel_binding(binding: HipAssemblyKernelBinding) -> None:
    if (
        binding.abi_version != HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION
        or binding.element_kernel_symbol != HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL
        or binding.gather_kernel_symbol != HIP_RTC_CSR_GATHER_SYMBOL
        or binding.element_block_size != HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE
        or binding.gather_block_size != HIP_RTC_CSR_GATHER_BLOCK_SIZE
        or not binding.source_resource.endswith(".hip.cpp")
    ):
        _fail(
            "hip_assembly_kernel_binding_invalid",
            "/kernel",
            "Kernel binding differs from the package fixed ABI.",
        )
    for value in (
        binding.source_sha256,
        binding.code_object_sha256,
        binding.identity_hash,
        binding.identity_snapshot_hash,
        binding.runtime_library_sha256,
        binding.hiprtc_library_sha256,
    ):
        _require_hash(value, "/kernel")
    allowed = {"explicit", "opt_rocm", "system_loader", "injected"}
    if (
        binding.runtime_library_discovery_source not in allowed
        or binding.hiprtc_library_discovery_source not in allowed
    ):
        _fail(
            "hip_assembly_kernel_binding_invalid",
            "/kernel/libraries",
            "Kernel library discovery source is invalid.",
        )


def _validate_live_kernel(kernel: Any, expected: HipAssemblyKernelBinding) -> None:
    _validate_kernel_snapshot(kernel, expected)
    if bool(getattr(kernel, "closed", False)):
        _fail(
            "hip_assembly_kernel_closed",
            "/kernel",
            "Live assembly kernel is closed.",
        )


def _validate_kernel_snapshot(kernel: Any, expected: HipAssemblyKernelBinding) -> None:
    if _kernel_binding(kernel, expected.architecture) != expected:
        _fail(
            "hip_assembly_kernel_binding_changed",
            "/kernel/identity",
            "Live kernel identity differs from its opening snapshot.",
        )


def _validate_live_contracts(context: HipAssemblyExecutionContext) -> None:
    try:
        validate_solver_model_buffers(context._buffers)
        validate_execution_plan_v2(
            context._source_plan, expected_buffers=context._buffers
        )
        validate_hip_assembly_plan_v1(
            context._assembly_plan,
            expected_buffers=context._buffers,
            expected_execution_plan=context._source_plan,
        )
    except Exception as exc:
        raise HipAssemblyContextError(
            "hip_assembly_live_binding_invalid", "/bindings", _exception_detail(exc)
        ) from exc
    expected = _bindings(
        context._buffers,
        context._source_plan,
        context._assembly_plan,
        context._opening_evaluation.receipt.bindings.verification_requested,
        context._kernel_binding.identity_hash,
        context._opening_evaluation.receipt.bindings.device_ordinal,
    )
    if expected != context.opening_receipt.bindings:
        _fail(
            "hip_assembly_live_binding_changed",
            "/bindings",
            "Live authoritative snapshots differ from opening bindings.",
        )


def _validate_native_open_links(
    base: DeviceExecutionContext,
    kernel: Any,
    binding: HipAssemblyKernelBinding,
) -> None:
    if type(kernel) is not HipRtcLinearFrameTrussAssemblyKernel:
        _fail(
            "hip_assembly_native_evidence_invalid",
            "/kernel",
            "Native evidence requires the exact package kernel owner type.",
        )
    capability = base._capability_receipt
    if (
        capability.status != "ready"
        or capability.library.sha256 != binding.runtime_library_sha256
        or base._device is None
        or capability.device.selected_ordinal != base._device.ordinal
        or binding.runtime_library_discovery_source == "injected"
        or binding.hiprtc_library_discovery_source == "injected"
    ):
        _fail(
            "hip_assembly_native_evidence_invalid",
            "/native_evidence",
            "Runtime, device, and kernel identities are not linked.",
        )


def _select_loaded_runtime_device(runtime: Any, device_ordinal: int) -> None:
    """Select the requested device before compiling/loading a HIP module."""

    direct = getattr(runtime, "set_device", None)
    if callable(direct):
        try:
            result = direct(device_ordinal)
        except Exception as exc:
            raise HipAssemblyContextError(
                "hip_assembly_device_selection_failed",
                "/device_ordinal",
                _bounded_detail(type(exc).__name__),
            ) from exc
        if result not in (None, 0):
            _fail(
                "hip_assembly_device_selection_failed",
                "/device_ordinal",
                "Injected device selection returned a failure status.",
            )
        return
    try:
        function = runtime.bind("hipSetDevice", [ctypes.c_int], ctypes.c_int)
        status = int(function(device_ordinal))
    except Exception as exc:
        raise HipAssemblyContextError(
            "hip_assembly_device_selection_failed",
            "/device_ordinal",
            _bounded_detail(type(exc).__name__),
        ) from exc
    if status != 0:
        detail = "HIP device selection failed."
        error_string = getattr(runtime, "hip_error_string", None)
        if callable(error_string):
            try:
                candidate = error_string(status)
                detail = (
                    candidate
                    if type(candidate) is str
                    else "HIP device selection failed."
                )
            except Exception:
                pass
        _fail(
            "hip_assembly_device_selection_failed",
            "/device_ordinal",
            _bounded_detail(detail),
        )


def _execution_owner(
    *,
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    base: DeviceExecutionContext,
    base_receipt_hash: str,
    kernel: Any,
    kernel_binding: HipAssemblyKernelBinding,
    evidence_scope: EvidenceScope,
    device: HipAssemblyDevice,
    context_id: str,
    pointers: dict[str, Any],
    views: tuple[HipAssemblyBufferView, ...],
    telemetry: HipAssemblyTelemetry,
    evaluation: HipAssemblyEvaluation,
    operator_view: HipAssemblyOperatorView | None,
    status: ContextStatus,
    reason: HipAssemblyReason | None,
) -> HipAssemblyExecutionContext:
    return HipAssemblyExecutionContext(
        buffers=buffers,
        source_plan=source_plan,
        assembly_plan=assembly_plan,
        base_context=base,
        base_context_receipt_hash=base_receipt_hash,
        rtc_kernel=kernel,
        kernel_binding=kernel_binding,
        evidence_scope=evidence_scope,
        device=device,
        context_id=context_id,
        pointers=pointers,
        child_buffers=views,
        telemetry=telemetry,
        opening_evaluation=evaluation,
        operator_view=operator_view,
        opening_status=status,
        failure_reason=reason,
    )


def _complete_post_execution_open(
    *,
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    base: DeviceExecutionContext,
    base_receipt_hash: str,
    kernel: Any,
    kernel_binding: HipAssemblyKernelBinding,
    evidence_scope: EvidenceScope,
    device: HipAssemblyDevice,
    device_ordinal: int,
    context_id: str,
    pointers: dict[str, Any],
    views: tuple[HipAssemblyBufferView, ...],
    telemetry: HipAssemblyTelemetry,
    base_telemetry: HipAssemblyTelemetry,
    execution_reason: HipAssemblyReason | None,
    host_error: np.ndarray,
    host_csr: np.ndarray | None,
    bindings: HipAssemblyBindings,
    operator_id: str,
    execution_id: str,
    work: HipAssemblyWorkReceipt,
) -> HipAssemblyContextOpenResult:
    """Convert synchronized execution state into strict receipts and an owner."""

    delta = _telemetry_delta(base_telemetry, telemetry)
    if execution_reason is not None:
        evaluation = _build_evaluation(
            status="unavailable",
            execution_id=execution_id,
            context_id=context_id,
            evidence_scope=evidence_scope,
            reason=execution_reason,
            bindings=bindings,
            operator_id=operator_id,
            device_error_code=None,
            csr_values=None,
            telemetry_delta=delta,
            parity=None,
            work=work,
        )
        context = _execution_owner(
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base=base,
            base_receipt_hash=base_receipt_hash,
            kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
            evaluation=evaluation,
            operator_view=None,
            status="poisoned",
            reason=execution_reason,
        )
        return HipAssemblyContextOpenResult(
            context, context.opening_receipt, evaluation
        )

    device_error = int(host_error[0])
    if device_error != 0:
        reason = HipAssemblyReason(
            "hip_assembly_device_error_flag",
            f"Device assembly reported stable error code {device_error}.",
        )
        evaluation = _build_evaluation(
            status="unavailable",
            execution_id=execution_id,
            context_id=context_id,
            evidence_scope=evidence_scope,
            reason=reason,
            bindings=bindings,
            operator_id=operator_id,
            device_error_code=device_error,
            csr_values=None,
            telemetry_delta=delta,
            parity=None,
            work=work,
        )
        context = _execution_owner(
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base=base,
            base_receipt_hash=base_receipt_hash,
            kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
            evaluation=evaluation,
            operator_view=None,
            status="poisoned",
            reason=reason,
        )
        return HipAssemblyContextOpenResult(
            context, context.opening_receipt, evaluation
        )

    csr_values: np.ndarray | None = None
    parity: HipAssemblyParityReport | None = None
    status: EvaluationStatus
    reason = None
    if host_csr is None:
        status = "assembled_unverified"
    else:
        csr_values = immutable_array(host_csr, dtype="<f8")
        if not np.all(np.isfinite(csr_values)):
            status = "unavailable"
            reason = HipAssemblyReason(
                "hip_assembly_output_nonfinite",
                "Downloaded CSR values contain non-finite values.",
            )
            csr_values = None
        else:
            parity = _parity_report(
                csr_values,
                source_plan.array("global_stiffness_csr_values"),
            )
            status = "verified" if parity.passed else "parity_failed"

    evaluation = _build_evaluation(
        status=status,
        execution_id=execution_id,
        context_id=context_id,
        evidence_scope=evidence_scope,
        reason=reason,
        bindings=bindings,
        operator_id=operator_id,
        device_error_code=0,
        csr_values=csr_values,
        telemetry_delta=delta,
        parity=parity,
        work=work,
    )
    ready = status in ("verified", "assembled_unverified")
    failure_reason = reason
    if status == "parity_failed":
        failure_reason = HipAssemblyReason(
            "hip_assembly_cpu_parity_failed",
            "Device CSR values differ from the bound CPU verification oracle.",
        )
    view = (
        _operator_view(
            context_id,
            operator_id,
            source_plan,
            assembly_plan,
            kernel_binding,
            device_ordinal,
            None if csr_values is None else array_data_hash(csr_values),
        )
        if ready
        else None
    )
    context = _execution_owner(
        buffers=buffers,
        source_plan=source_plan,
        assembly_plan=assembly_plan,
        base=base,
        base_receipt_hash=base_receipt_hash,
        kernel=kernel,
        kernel_binding=kernel_binding,
        evidence_scope=evidence_scope,
        device=device,
        context_id=context_id,
        pointers=pointers,
        views=views,
        telemetry=telemetry,
        evaluation=evaluation,
        operator_view=view,
        status="context_ready" if ready else "poisoned",
        reason=failure_reason,
    )
    validate_hip_assembly_evaluation(
        evaluation,
        expected_context=context,
        expected_buffers=buffers,
        expected_source_plan=source_plan,
        expected_assembly_plan=assembly_plan,
        expected_kernel=kernel,
    )
    return HipAssemblyContextOpenResult(context, context.opening_receipt, evaluation)


def _handle_post_kernel_acquisition_failure(
    *,
    primary: Exception,
    kernel: Any,
    kernel_binding: HipAssemblyKernelBinding | None,
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    verify_cpu_parity: bool,
    evidence_scope: EvidenceScope,
    device_ordinal: int,
) -> HipAssemblyContextOpenResult:
    """Release a kernel acquired before a foundation owner exists.

    A failed unload is converted into a strict kernel-only cleanup context
    whenever the kernel identity remains serializable.  If even its identity
    is invalid, the raised stable error carries a minimal reachable cleanup
    owner instead of dropping the live module.
    """

    try:
        kernel.close()
    except Exception as cleanup_error:
        cleanup_binding = kernel_binding
        if cleanup_binding is None:
            try:
                cleanup_binding = _kernel_binding(kernel, None)
            except Exception as binding_error:
                owner = _HipAssemblyKernelCleanupOwner(kernel)
                raise HipAssemblyContextError(
                    "hip_assembly_kernel_cleanup_failed",
                    "/open/kernel_cleanup",
                    _bounded_detail(
                        f"{type(primary).__name__}; "
                        f"{type(cleanup_error).__name__}; "
                        f"{type(binding_error).__name__}"
                    ),
                    cleanup_owner=owner,
                ) from primary
        try:
            bindings = _bindings(
                buffers,
                source_plan,
                assembly_plan,
                verify_cpu_parity,
                cleanup_binding.identity_hash,
                device_ordinal,
            )
            context_id = _context_id(
                buffers,
                source_plan,
                assembly_plan,
                cleanup_binding,
                evidence_scope,
                device_ordinal,
                verify_cpu_parity,
            )
            operator_id = _operator_id(
                context_id, source_plan, assembly_plan, cleanup_binding
            )
            execution_id = _execution_id(context_id, operator_id, verify_cpu_parity)
            reason = HipAssemblyReason(
                "hip_assembly_context_cleanup_failed",
                _bounded_detail(
                    f"{type(primary).__name__}; cleanup {type(cleanup_error).__name__}"
                ),
            )
            evaluation = _build_evaluation(
                status="unavailable",
                execution_id=execution_id,
                context_id=context_id,
                evidence_scope=evidence_scope,
                reason=reason,
                bindings=bindings,
                operator_id=operator_id,
                device_error_code=None,
                csr_values=None,
                telemetry_delta=HipAssemblyTelemetry(),
                parity=None,
                work=_work(source_plan, assembly_plan),
            )
            context = HipAssemblyExecutionContext(
                buffers=buffers,
                source_plan=source_plan,
                assembly_plan=assembly_plan,
                base_context=None,
                base_context_receipt_hash=canonical_hash(
                    {
                        "foundation": "not_created",
                        "context_id": context_id,
                    }
                ),
                rtc_kernel=kernel,
                kernel_binding=cleanup_binding,
                evidence_scope=evidence_scope,
                device=None,
                context_id=context_id,
                pointers={},
                child_buffers=(),
                telemetry=HipAssemblyTelemetry(),
                opening_evaluation=evaluation,
                operator_view=None,
                opening_status="cleanup_failed",
                failure_reason=reason,
            )
            return HipAssemblyContextOpenResult(
                context, context.opening_receipt, evaluation
            )
        except Exception as owner_error:
            owner = _HipAssemblyKernelCleanupOwner(kernel)
            raise HipAssemblyContextError(
                "hip_assembly_kernel_cleanup_failed",
                "/open/kernel_cleanup_owner",
                _bounded_detail(type(owner_error).__name__),
                cleanup_owner=owner,
            ) from primary
    raise HipAssemblyContextError(
        "hip_assembly_context_open_failed",
        "/open/post_kernel_acquisition",
        _exception_detail(primary),
    ) from primary


def _finish_pre_execution_open_failure(
    *,
    primary: Exception,
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    base: DeviceExecutionContext,
    base_receipt_hash: str,
    kernel: Any,
    kernel_binding: HipAssemblyKernelBinding,
    evidence_scope: EvidenceScope,
    device: HipAssemblyDevice,
    context_id: str,
    pointers: dict[str, Any],
    views: tuple[HipAssemblyBufferView, ...],
    telemetry: HipAssemblyTelemetry,
    bindings: HipAssemblyBindings,
    dimensions: HipAssemblyDimensions,
    execution_id: str,
    operator_id: str,
    work: HipAssemblyWorkReceipt,
    base_telemetry: HipAssemblyTelemetry,
) -> HipAssemblyContextOpenResult:
    cleanup_error: Exception | None = None
    cleanup_sync_complete = False
    try:
        base._runtime.synchronize(base._stream)
    except Exception as exc:
        cleanup_error = exc
    else:
        cleanup_sync_complete = True
        telemetry = replace(
            telemetry,
            explicit_sync_count=telemetry.explicit_sync_count + 1,
        )

    if cleanup_sync_complete:
        for name in reversed(_CHILD_BUFFER_ORDER):
            pointer = pointers.get(name)
            if pointer is None:
                continue
            telemetry = replace(
                telemetry,
                child_deallocation_attempt_count=(
                    telemetry.child_deallocation_attempt_count + 1
                ),
            )
            try:
                base._runtime.free(pointer)
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                continue
            del pointers[name]
            byte_length = _view_by_name(views, name).byte_length
            telemetry = replace(
                telemetry,
                deallocation_count=telemetry.deallocation_count + 1,
                child_deallocation_success_count=(
                    telemetry.child_deallocation_success_count + 1
                ),
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes - byte_length
                ),
            )

    kernel_closed = False
    if not pointers:
        try:
            kernel.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        else:
            kernel_closed = True
    if not pointers and kernel_closed:
        try:
            base.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        finally:
            released = base_telemetry.current_device_payload_bytes - int(
                base._telemetry.current_device_payload_bytes
            )
            deallocated = (
                int(base._telemetry.deallocation_count)
                - base_telemetry.deallocation_count
            )
            telemetry = replace(
                telemetry,
                deallocation_count=telemetry.deallocation_count + max(deallocated, 0),
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes - max(released, 0)
                ),
            )

    reason = HipAssemblyReason(
        "hip_assembly_context_open_failed", _exception_detail(primary)
    )
    delta = _telemetry_delta(base_telemetry, telemetry)
    evaluation = _build_evaluation(
        status="unavailable",
        execution_id=execution_id,
        context_id=context_id,
        evidence_scope=evidence_scope,
        reason=reason,
        bindings=bindings,
        operator_id=operator_id,
        device_error_code=None,
        csr_values=None,
        telemetry_delta=delta,
        parity=None,
        work=work,
    )
    if cleanup_error is not None or pointers or not base.closed:
        cleanup_reason = HipAssemblyReason(
            "hip_assembly_context_cleanup_failed",
            _bounded_detail(
                f"{_exception_detail(primary)}; cleanup: "
                f"{_exception_detail(cleanup_error)}"
            ),
        )
        context = HipAssemblyExecutionContext(
            buffers=buffers,
            source_plan=source_plan,
            assembly_plan=assembly_plan,
            base_context=base,
            base_context_receipt_hash=base_receipt_hash,
            rtc_kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            child_buffers=views,
            telemetry=telemetry,
            opening_evaluation=evaluation,
            operator_view=None,
            opening_status="cleanup_failed",
            failure_reason=cleanup_reason,
            base_deallocation_observed=int(base._telemetry.deallocation_count),
            base_current_bytes_observed=int(
                base._telemetry.current_device_payload_bytes
            ),
        )
        context._kernel_closed = kernel_closed
        context._close_sync_complete = cleanup_sync_complete
        return HipAssemblyContextOpenResult(
            context, context.opening_receipt, evaluation
        )
    receipt = _build_context_receipt(
        status="unavailable",
        context_id=context_id,
        actual_backend=None,
        evidence_scope=evidence_scope,
        reason=reason,
        base_context_receipt_hash=base_receipt_hash,
        evaluation_receipt_hash=evaluation.receipt.receipt_hash,
        bindings=bindings,
        kernel=kernel_binding,
        device=None,
        dimensions=dimensions,
        child_buffers=(),
        operator_view=None,
        telemetry=telemetry,
        claims=_empty_claims(),
    )
    return HipAssemblyContextOpenResult(None, receipt, evaluation)


def _operator_view(
    context_id: str,
    operator_id: str,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    kernel: HipAssemblyKernelBinding,
    device_ordinal: int,
    verification_data_hash: str | None,
) -> HipAssemblyOperatorView:
    draft = HipAssemblyOperatorView(
        context_id=context_id,
        operator_id=operator_id,
        source_execution_plan_hash=source_plan.plan_hash,
        assembly_plan_hash=assembly_plan.assembly_plan_hash,
        kernel_identity_hash=kernel.identity_hash,
        dtype="<f8",
        shape=(source_plan.nnz,),
        byte_length=8 * source_plan.nnz,
        csr_nnz=source_plan.nnz,
        device_ordinal=device_ordinal,
        memory_space="hip_device",
        access="read_only_after_assembly",
        lifetime="context_owned_process_local",
        ordering_domain="context_serial_queue",
        verification_data_hash=verification_data_hash,
        metadata_hash=_ZERO_HASH,
    )
    view = replace(
        draft,
        metadata_hash=canonical_hash(_operator_view_payload(draft, include_hash=False)),
    )
    view.to_dict()
    return view


def _parity_report(actual: np.ndarray, expected: np.ndarray) -> HipAssemblyParityReport:
    if (
        actual.shape != expected.shape
        or actual.dtype.str != "<f8"
        or expected.dtype.str != "<f8"
    ):
        _fail(
            "hip_assembly_parity_input_invalid",
            "/parity",
            "Parity arrays must be shape-equal little-endian FP64.",
        )
    global_scale = max(
        float(np.max(np.abs(actual), initial=0.0)),
        float(np.max(np.abs(expected), initial=0.0)),
        1.0,
    )
    actual_scaled = actual / global_scale
    expected_scaled = expected / global_scale
    difference_scaled = actual_scaled - expected_scaled
    difference_norm = math.sqrt(float(np.dot(difference_scaled, difference_scaled)))
    expected_norm = math.sqrt(float(np.dot(expected_scaled, expected_scaled)))
    denominator_scaled = max(expected_norm, 1.0 / global_scale)
    relative = difference_norm / denominator_scaled
    if not math.isfinite(relative):
        relative = float(np.finfo(np.float64).max)
    entry_scale = np.maximum(1.0, np.maximum(np.abs(actual), np.abs(expected)))
    entry_difference = np.abs(actual / entry_scale - expected / entry_scale)
    max_scaled = float(np.max(entry_difference, initial=0.0))
    max_abs_scaled = float(np.max(np.abs(difference_scaled), initial=0.0))
    fp64_max = float(np.finfo(np.float64).max)
    max_abs = (
        fp64_max
        if max_abs_scaled > fp64_max / global_scale
        else max_abs_scaled * global_scale
    )
    passed = relative <= _PARITY_TOLERANCE and max_scaled <= _PARITY_TOLERANCE
    zero_mask = expected == 0.0
    zero_count = int(np.count_nonzero(zero_mask))
    zero_exact = bool(np.all(actual[zero_mask] == 0.0))
    metric = HipAssemblyParityMetric(
        count=int(actual.size),
        max_abs_error=max_abs,
        relative_l2_error=relative,
        max_scaled_error=max_scaled,
        passed=passed,
    )
    report = HipAssemblyParityReport(
        csr_values=metric,
        structural_zero_count=zero_count,
        structural_zeros_exact=zero_exact,
        passed=passed and zero_exact,
    )
    _validate_parity(report)
    return report


def _telemetry_from_base(value: Any) -> HipAssemblyTelemetry:
    return HipAssemblyTelemetry(
        h2d_bytes=int(value.h2d_bytes),
        d2h_bytes=int(value.d2h_bytes),
        h2d_operation_count=int(value.h2d_operation_count),
        d2h_operation_count=int(value.d2h_operation_count),
        d2h_operation_attempt_count=int(value.d2h_operation_count),
        d2h_operation_success_count=int(value.d2h_operation_count),
        d2h_bytes_attempted=int(value.d2h_bytes),
        d2h_bytes_succeeded=int(value.d2h_bytes),
        blocking_copy_count=int(value.blocking_copy_count),
        explicit_sync_count=int(value.explicit_sync_count),
        allocation_count=int(value.allocation_count),
        deallocation_count=int(value.deallocation_count),
        current_device_payload_bytes=int(value.current_device_payload_bytes),
        peak_device_payload_bytes=int(value.peak_device_payload_bytes),
        kernel_launch_attempt_count=0,
        kernel_launch_count=int(value.kernel_launch_count),
        fallback_count=int(value.fallback_count),
    )


def _telemetry_delta(
    base: HipAssemblyTelemetry,
    current: HipAssemblyTelemetry,
) -> HipAssemblyTelemetry:
    child_current = max(
        current.current_device_payload_bytes - base.current_device_payload_bytes,
        0,
    )
    child_peak = max(
        current.peak_device_payload_bytes - base.peak_device_payload_bytes,
        0,
    )
    return HipAssemblyTelemetry(
        h2d_bytes=max(current.h2d_bytes - base.h2d_bytes, 0),
        d2h_bytes=max(current.d2h_bytes - base.d2h_bytes, 0),
        h2d_operation_count=max(
            current.h2d_operation_count - base.h2d_operation_count, 0
        ),
        d2h_operation_count=max(
            current.d2h_operation_count - base.d2h_operation_count, 0
        ),
        d2h_operation_attempt_count=max(
            current.d2h_operation_attempt_count - base.d2h_operation_attempt_count,
            0,
        ),
        d2h_operation_success_count=max(
            current.d2h_operation_success_count - base.d2h_operation_success_count,
            0,
        ),
        d2h_bytes_attempted=max(
            current.d2h_bytes_attempted - base.d2h_bytes_attempted, 0
        ),
        d2h_bytes_succeeded=max(
            current.d2h_bytes_succeeded - base.d2h_bytes_succeeded, 0
        ),
        blocking_copy_count=max(
            current.blocking_copy_count - base.blocking_copy_count, 0
        ),
        explicit_sync_count=max(
            current.explicit_sync_count - base.explicit_sync_count, 0
        ),
        allocation_count=max(current.allocation_count - base.allocation_count, 0),
        deallocation_count=max(current.deallocation_count - base.deallocation_count, 0),
        current_device_payload_bytes=child_current,
        peak_device_payload_bytes=child_peak,
        kernel_launch_attempt_count=current.kernel_launch_attempt_count,
        kernel_launch_count=current.kernel_launch_count,
        fallback_count=0,
        child_allocation_attempt_count=current.child_allocation_attempt_count,
        child_allocation_success_count=current.child_allocation_success_count,
        child_deallocation_attempt_count=current.child_deallocation_attempt_count,
        child_deallocation_success_count=current.child_deallocation_success_count,
        child_initial_h2d_attempt_count=current.child_initial_h2d_attempt_count,
        child_initial_h2d_success_count=current.child_initial_h2d_success_count,
        assembly_sync_count=current.assembly_sync_count,
        assembly_sync_attempt_count=current.assembly_sync_attempt_count,
        assembly_sync_success_count=current.assembly_sync_success_count,
        error_flag_d2h_bytes=current.error_flag_d2h_bytes,
        verification_csr_d2h_bytes=current.verification_csr_d2h_bytes,
        host_csr_values_h2d_bytes=0,
    )


def _empty_claims() -> HipAssemblyClaims:
    return HipAssemblyClaims(False, False, False, False, False)


def _actual_backend(scope: EvidenceScope) -> str:
    return "hip" if scope == "native_hiprtc" else "test_double"


def _context_id(
    buffers: SolverModelBuffers,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    kernel: HipAssemblyKernelBinding,
    evidence_scope: EvidenceScope,
    device_ordinal: int,
    verify_cpu_parity: bool,
) -> str:
    digest = canonical_hash(
        {
            "solver_artifact_hash": buffers.artifact_hash,
            "source_execution_plan_hash": source_plan.plan_hash,
            "assembly_plan_hash": assembly_plan.assembly_plan_hash,
            "kernel_identity_snapshot_hash": kernel.identity_snapshot_hash,
            "evidence_scope": evidence_scope,
            "device_ordinal": device_ordinal,
            "verify_cpu_parity": verify_cpu_parity,
        }
    )
    return "HipAssemblyContext:" + digest.removeprefix("sha256:")[:24]


def _operator_id(
    context_id: str,
    source_plan: ExecutionPlanV2,
    assembly_plan: HipAssemblyPlanV1,
    kernel: HipAssemblyKernelBinding,
) -> str:
    return _operator_id_from_hashes(
        context_id,
        source_plan.plan_hash,
        assembly_plan.assembly_plan_hash,
        kernel.identity_hash,
    )


def _operator_id_from_hashes(
    context_id: str,
    source_execution_plan_hash: str,
    assembly_plan_hash: str,
    kernel_identity_hash: str,
) -> str:
    digest = canonical_hash(
        {
            "context_id": context_id,
            "source_execution_plan_hash": source_execution_plan_hash,
            "assembly_plan_hash": assembly_plan_hash,
            "kernel_identity_hash": kernel_identity_hash,
            "memory_space": "hip_device",
        }
    )
    return "HipAssemblyOperator:" + digest.removeprefix("sha256:")[:24]


def _execution_id(context_id: str, operator_id: str, verify_cpu_parity: bool) -> str:
    digest = canonical_hash(
        {
            "context_id": context_id,
            "operator_id": operator_id,
            "verify_cpu_parity": verify_cpu_parity,
            "execution": "open_time_two_kernel_assembly",
        }
    )
    return "HipAssemblyEvaluation:" + digest.removeprefix("sha256:")[:24]


def _child_payload_bytes(dimensions: HipAssemblyDimensions) -> int:
    g = dimensions.global_dof_count
    z = dimensions.csr_nnz
    e = dimensions.element_count
    c = dimensions.contribution_count
    return 4 * (g + 1) + 4 * z + e + 4 * (z + 1) + 4 * c + 8 * c + 8 * z + 4


def _initial_upload_bytes(dimensions: HipAssemblyDimensions) -> int:
    g = dimensions.global_dof_count
    z = dimensions.csr_nnz
    e = dimensions.element_count
    c = dimensions.contribution_count
    return 4 * (g + 1) + 4 * z + e + 4 * (z + 1) + 4 * c + 4


def _successful_assembly_delta(
    dimensions: HipAssemblyDimensions, verify_cpu_parity: bool
) -> HipAssemblyTelemetry:
    verify_bytes = 8 * dimensions.csr_nnz if verify_cpu_parity else 0
    payload = _child_payload_bytes(dimensions)
    return HipAssemblyTelemetry(
        h2d_bytes=_initial_upload_bytes(dimensions),
        d2h_bytes=4 + verify_bytes,
        h2d_operation_count=6,
        d2h_operation_count=1 + int(verify_cpu_parity),
        d2h_operation_attempt_count=1 + int(verify_cpu_parity),
        d2h_operation_success_count=1 + int(verify_cpu_parity),
        d2h_bytes_attempted=4 + verify_bytes,
        d2h_bytes_succeeded=4 + verify_bytes,
        blocking_copy_count=0,
        explicit_sync_count=1,
        allocation_count=8,
        deallocation_count=0,
        current_device_payload_bytes=payload,
        peak_device_payload_bytes=payload,
        kernel_launch_attempt_count=2,
        kernel_launch_count=2,
        fallback_count=0,
        child_allocation_attempt_count=8,
        child_allocation_success_count=8,
        child_deallocation_attempt_count=0,
        child_deallocation_success_count=0,
        child_initial_h2d_attempt_count=6,
        child_initial_h2d_success_count=6,
        assembly_sync_count=1,
        assembly_sync_attempt_count=1,
        assembly_sync_success_count=1,
        error_flag_d2h_bytes=4,
        verification_csr_d2h_bytes=verify_bytes,
        host_csr_values_h2d_bytes=0,
    )


def _expected_view_specs(
    dimensions: HipAssemblyDimensions,
) -> dict[str, dict[str, Any]]:
    g = dimensions.global_dof_count
    z = dimensions.csr_nnz
    e = dimensions.element_count
    c = dimensions.contribution_count
    rows = {
        "csr_row_ptr": (
            "<i4",
            (g + 1,),
            4 * (g + 1),
            "read_only",
            "async_h2d_before_assembly",
            True,
        ),
        "csr_column_indices": (
            "<i4",
            (z,),
            4 * z,
            "read_only",
            "async_h2d_before_assembly",
            True,
        ),
        "reference_axis_code": (
            "|u1",
            (e,),
            e,
            "read_only",
            "async_h2d_before_assembly",
            True,
        ),
        "reverse_segment_offsets": (
            "<i4",
            (z + 1,),
            4 * (z + 1),
            "read_only",
            "async_h2d_before_assembly",
            True,
        ),
        "reverse_contribution_indices": (
            "<i4",
            (c,),
            4 * c,
            "read_only",
            "async_h2d_before_assembly",
            True,
        ),
        "element_contributions": ("<f8", (c,), 8 * c, "write_then_read", "none", False),
        "csr_values": ("<f8", (z,), 8 * z, "write_then_read_only", "none", False),
        "error_flag": ("<i4", (1,), 4, "read_write", "async_h2d_before_assembly", True),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, (dtype, shape, size, access, transfer, hashed) in rows.items():
        result[name] = {
            "name": name,
            "dtype": dtype,
            "shape": list(shape),
            "byte_length": size,
            "data_hash": "__hash__" if hashed else None,
            "memory_space": "hip_device",
            "access": access,
            "initial_transfer": transfer,
        }
    return result


def _view_by_name(
    views: tuple[HipAssemblyBufferView, ...], name: str
) -> HipAssemblyBufferView:
    try:
        return next(view for view in views if view.name == name)
    except StopIteration as exc:
        _fail(
            "hip_assembly_child_buffer_missing",
            f"/child_buffers/{name}",
            "Tracked child allocation has no descriptor.",
        )
        raise AssertionError from exc


def _require_hash(value: Any, path: str) -> None:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "hip_assembly_hash_invalid",
            path,
            "Expected a canonical SHA-256 string.",
        )


def _bounded_detail(value: str) -> str:
    normalized = " ".join(str(value).split()) or "HIP assembly unavailable."
    normalized = _RUNTIME_VALUE_PATTERN.sub("[runtime-reference-redacted]", normalized)
    normalized = _HEX_ADDRESS_PATTERN.sub("[address-redacted]", normalized)
    return normalized[:512]


def _exception_detail(error: Any) -> str:
    """Return bounded diagnostics without invoking untrusted ``__str__``."""

    if type(error) is str:
        return _bounded_detail(error)
    parts = [type(error).__name__]
    for name in ("code", "message"):
        try:
            value = getattr(error, name, None)
        except Exception:
            value = None
        if type(value) is str and value:
            parts.append(value)
    if len(parts) == 1:
        try:
            arguments = error.args
        except Exception:
            arguments = ()
        if type(arguments) is tuple:
            parts.extend(value for value in arguments if type(value) is str and value)
    return _bounded_detail(": ".join(parts))


def _has_forbidden_runtime_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in _FORBIDDEN_RUNTIME_KEYS)
            or _has_forbidden_runtime_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_has_forbidden_runtime_key(item) for item in value)
    if isinstance(value, str):
        return bool(
            _HEX_ADDRESS_PATTERN.search(value) or _RUNTIME_VALUE_PATTERN.search(value)
        )
    return False


def _validate_schema(
    validator: Draft202012Validator, payload: dict[str, Any], label: str
) -> None:
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(
            f"hip_assembly_{label}_schema_invalid",
            path,
            error.message,
        )


@lru_cache(maxsize=1)
def _context_schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_assembly_context_receipt_v1.schema.json"
    )
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _evaluation_schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_assembly_evaluation_receipt_v1.schema.json"
    )
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise HipAssemblyContextError(code, path, message)
