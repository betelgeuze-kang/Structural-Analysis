"""Same-stream consumer for an assembly-owned device CSR operator.

This module deliberately composes with a live :class:`HipAssemblyExecutionContext`.
It does not open another HIP foundation, create another stream, allocate another
CSR, or upload CSR/load data.  The consumer owns only four full-DOF vectors:
committed state, direction, residual, and JVP.  Its enqueue primitive performs
one device launch with zero transfer/allocation/synchronization; the separate
verification wrapper performs explicit host I/O and can never become fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

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
from structural_analysis.engine_v2.contracts.state_ir import StateIR, validate_state_ir
from structural_analysis.engine_v2.rtc_backend.csr_context import (
    HipRtcKernelBinding,
    _kernel_binding as _rtc_kernel_binding,
    _validate_kernel_binding as _validate_rtc_kernel_binding,
    _validate_live_kernel as _validate_live_rtc_kernel,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (
    HipRtcCsrKernel,
    HipRtcError,
    compile_hip_rtc_csr_kernel,
)

from .context import HipAssemblyExecutionContext

HIP_RESIDENT_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-resident-csr-context.v1"
)
HIP_RESIDENT_CSR_ENQUEUE_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-resident-csr-enqueue.v1"
)
HIP_RESIDENT_CSR_EVALUATION_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-hip-resident-csr-evaluation.v1"
)
HIP_RESIDENT_CSR_CAPABILITY_PROFILE = (
    "phase0_hiprtc_assembly_resident_csr_residual_jvp_consumer"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_ADDRESS_PATTERN = re.compile(r"(?i)\b0x[0-9a-f]+\b")
_DECIMAL_POINTER_WRAPPER_PATTERN = re.compile(
    r"(?i)\b(?:(?:ctypes\.)?c_void_p|device_ptr|cudeviceptr)"
    r"\s*\(\s*[0-9]+\s*\)"
)
_LONG_DECIMAL_ADDRESS_PATTERN = re.compile(r"\b[1-9][0-9]{8,}\b")
_PARITY_TOLERANCE = 1.0e-8
_OWNED_BUFFER_ORDER = (
    "state_displacement",
    "direction_workspace",
    "residual_workspace",
    "jvp_workspace",
)
_BORROWED_BUFFER_ORDER = (
    "csr_row_ptr",
    "csr_column_indices",
    "csr_values",
    "load_vector_si",
)

ContextStatus = Literal[
    "context_ready",
    "poisoned",
    "cleanup_failed",
    "context_closed",
    "unavailable",
]
EnqueueStatus = Literal["enqueued", "unavailable"]
EvaluationStatus = Literal["verified", "parity_failed", "unavailable"]
EvidenceScope = Literal["native_hiprtc_composite", "injected_test_double"]


class HipResidentCsrContextError(RuntimeError):
    """Fail-closed resident-consumer error with stable code and path."""

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
class HipResidentCsrReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipResidentCsrBindings:
    parent_context_id: str
    parent_opening_receipt_hash: str
    parent_assembly_evaluation_receipt_hash: str
    parent_operator_id: str
    parent_operator_metadata_hash: str
    parent_assembly_kernel_identity_hash: str
    parent_runtime_library_sha256: str
    parent_architecture: str
    parent_evidence_scope: Literal["native_hiprtc", "injected_test_double"]
    source_execution_plan_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_partition_hash: str
    load_pattern_id: str
    load_vector_hash: str
    state_hash: str
    state_epoch: int
    state_displacement_hash: str
    device_ordinal: int
    lease_epoch: int
    ordering_domain: Literal["parent_context_serial_queue"] = (
        "parent_context_serial_queue"
    )
    residual_sign_convention: Literal["internal_minus_external"] = (
        "internal_minus_external"
    )
    host_csr_role: Literal["device_borrowed_never_reuploaded"] = (
        "device_borrowed_never_reuploaded"
    )
    load_source: Literal["foundation_load_vector_si_full"] = (
        "foundation_load_vector_si_full"
    )
    state_load_factor_applied: Literal[False] = False
    residual_kernel_origin: Literal["internally_compiled", "caller_supplied"] = (
        "caller_supplied"
    )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrDimensions:
    global_dof_count: int
    free_dof_count: int
    constrained_dof_count: int
    csr_nnz: int
    borrowed_buffer_count: Literal[4] = 4
    owned_buffer_count: Literal[4] = 4

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrBufferView:
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
class HipResidentCsrTelemetry:
    owned_allocation_attempt_count: int = 0
    owned_allocation_success_count: int = 0
    owned_deallocation_attempt_count: int = 0
    owned_deallocation_success_count: int = 0
    owned_current_device_bytes: int = 0
    owned_peak_device_bytes: int = 0
    borrowed_device_bytes: int = 0
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
    module_close_attempt_count: int = 0
    module_close_success_count: int = 0
    module_owner_acquired_count: int = 0
    lease_release_attempt_count: int = 0
    lease_release_success_count: int = 0
    fallback_count: int = 0
    new_stream_create_count: Literal[0] = 0
    consumer_csr_symbolic_h2d_bytes: Literal[0] = 0
    consumer_csr_numeric_h2d_bytes: Literal[0] = 0
    consumer_load_h2d_bytes: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrClaims:
    exclusive_parent_lease_active: bool
    same_runtime_device_stream: bool
    borrowed_assembly_csr: bool
    borrowed_foundation_load: bool
    resident_residual_jvp_ready: bool
    host_csr_reupload_avoided: bool
    native_composite_context: bool
    solver_ready: Literal[False] = False
    device_resident_krylov_ready: Literal[False] = False
    end_to_end_on_complexity: Literal[False] = False
    performance_or_speedup: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrContextReceipt:
    status: ContextStatus
    context_id: str
    actual_backend: str | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipResidentCsrReason | None
    bindings: HipResidentCsrBindings
    kernel: HipRtcKernelBinding | None
    dimensions: HipResidentCsrDimensions
    owned_buffers: tuple[HipResidentCsrBufferView, ...]
    telemetry: HipResidentCsrTelemetry
    claims: HipResidentCsrClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_RESIDENT_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_resident_csr_context_receipt(self)
        return _context_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipResidentCsrContextOpenResult:
    context: HipResidentCsrExecutionContext | None
    receipt: HipResidentCsrContextReceipt

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


@dataclass(frozen=True, slots=True)
class HipResidentCsrEnqueueDelta:
    h2d_operation_count: Literal[0]
    h2d_bytes: Literal[0]
    d2h_operation_count: Literal[0]
    d2h_bytes: Literal[0]
    allocation_count: Literal[0]
    sync_count: Literal[0]
    kernel_launch_attempt_count: int
    kernel_launch_success_count: int
    fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrEnqueueReceipt:
    status: EnqueueStatus
    enqueue_id: str
    context_id: str
    opening_context_receipt_hash: str
    operator_id: str
    state_hash: str
    state_epoch: int
    kernel_identity_hash: str
    sequence: int
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipResidentCsrReason | None
    telemetry_delta: HipResidentCsrEnqueueDelta
    completion_fence_observed: Literal[False]
    residual_jvp_enqueued: bool
    solver_iteration: Literal[False]
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_RESIDENT_CSR_ENQUEUE_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_resident_csr_enqueue_receipt(self)
        return _enqueue_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipResidentCsrArrayDescriptor:
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
class HipResidentCsrEvaluationDelta:
    h2d_operation_attempt_count: int
    h2d_operation_success_count: int
    h2d_bytes_attempted: int
    h2d_bytes_succeeded: int
    d2h_operation_attempt_count: int
    d2h_operation_success_count: int
    d2h_bytes_attempted: int
    d2h_bytes_succeeded: int
    kernel_launch_attempt_count: int
    kernel_launch_success_count: int
    sync_attempt_count: int
    sync_success_count: int
    allocation_count: Literal[0]
    fallback_count: Literal[0]

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrParityMetric:
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
class HipResidentCsrParityReport:
    residual_full: HipResidentCsrParityMetric
    residual_free: HipResidentCsrParityMetric
    residual_constrained: HipResidentCsrParityMetric
    jvp_full: HipResidentCsrParityMetric
    jvp_free: HipResidentCsrParityMetric
    jvp_constrained: HipResidentCsrParityMetric
    zero_direction_exact: bool
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "execution_plan_v2_cpu_csr_fp64",
            "oracle_role": "verification_only_never_fallback",
            "residual": {
                "full": self.residual_full.to_dict(),
                "free": self.residual_free.to_dict(),
                "constrained": self.residual_constrained.to_dict(),
            },
            "jvp": {
                "full": self.jvp_full.to_dict(),
                "free": self.jvp_free.to_dict(),
                "constrained": self.jvp_constrained.to_dict(),
            },
            "zero_direction_exact": self.zero_direction_exact,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipResidentCsrWorkReceipt:
    global_dof_count: int
    csr_nnz: int

    def to_dict(self) -> dict[str, Any]:
        g = self.global_dof_count
        z = self.csr_nnz
        return {
            "scope": "assembled_device_csr_residual_jvp_verification_v1",
            "global_dof_count": g,
            "csr_nnz": z,
            "csr_pass_count": 1,
            "multiplication_count": 2 * z,
            "accumulation_count": 2 * z,
            "load_subtraction_count": g,
            "flop_equivalent_count": 4 * z + g,
            "operation_count_basis": "structural_source_equivalent_not_counter",
            "physical_dram_bytes": "not_instrumented",
            "end_to_end_o_n_claim": False,
        }


@dataclass(frozen=True, slots=True)
class HipResidentCsrEvaluationClaims:
    assembled_device_csr_consumed: bool
    residual_jvp_completed_after_fence: bool
    cpu_reference_parity_verified: bool
    zero_consumer_csr_h2d: Literal[True] = True
    same_parent_stream: Literal[True] = True
    solver_ready: Literal[False] = False
    device_resident_krylov_ready: Literal[False] = False
    iteration_host_copy_zero: Literal[False] = False
    end_to_end_on_complexity: Literal[False] = False
    performance_or_speedup: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipResidentCsrEvaluationReceipt:
    status: EvaluationStatus
    execution_id: str
    context_id: str
    opening_context_receipt_hash: str
    enqueue: HipResidentCsrEnqueueReceipt | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    actual_backend: str | None
    reason: HipResidentCsrReason | None
    operator_id: str
    state_hash: str
    state_epoch: int
    direction: HipResidentCsrArrayDescriptor
    residual: HipResidentCsrArrayDescriptor | None
    jvp: HipResidentCsrArrayDescriptor | None
    telemetry_delta: HipResidentCsrEvaluationDelta
    parity: HipResidentCsrParityReport | None
    work: HipResidentCsrWorkReceipt
    claims: HipResidentCsrEvaluationClaims
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_RESIDENT_CSR_EVALUATION_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_resident_csr_evaluation_receipt(self)
        return _evaluation_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipResidentCsrEvaluation:
    receipt: HipResidentCsrEvaluationReceipt
    direction: np.ndarray
    residual: np.ndarray | None
    jvp: np.ndarray | None
    enqueue: HipResidentCsrEnqueueReceipt | None

    @property
    def result_hash(self) -> str:
        return self.receipt.receipt_hash

    def to_dict(self) -> dict[str, Any]:
        validate_hip_resident_csr_evaluation(self)
        return self.receipt.to_dict()


class HipResidentCsrExecutionContext:
    """Exclusive same-stream borrower of one assembly-owned CSR operator."""

    def __init__(
        self,
        *,
        parent: HipAssemblyExecutionContext,
        lease_token: object,
        lease_epoch: int,
        state: StateIR,
        rtc_kernel: Any,
        kernel_binding: HipRtcKernelBinding | None,
        evidence_scope: EvidenceScope,
        kernel_internally_compiled: bool,
        context_id: str,
        borrowed_pointers: dict[str, Any],
        pointers: dict[str, Any],
        owned_buffers: tuple[HipResidentCsrBufferView, ...],
        telemetry: HipResidentCsrTelemetry,
        opening_status: ContextStatus,
        failure_reason: HipResidentCsrReason | None,
        kernel_closed: bool = False,
    ) -> None:
        self._parent = parent
        self._lease_token = lease_token
        self._lease_epoch = lease_epoch
        self._state = state
        self._plan = parent._source_plan
        self._runtime = parent._runtime
        self._stream = parent._stream
        self._runtime_snapshot = parent._runtime
        self._stream_snapshot = parent._stream
        self._base_context_snapshot = parent._base_context
        self._device_ordinal_snapshot = parent._operator_view.device_ordinal
        self._rtc_kernel = rtc_kernel
        self._kernel_identity_snapshot = (
            None if rtc_kernel is None else getattr(rtc_kernel, "identity", None)
        )
        self._kernel_binding = kernel_binding
        self._evidence_scope = evidence_scope
        self._kernel_internally_compiled = kernel_internally_compiled
        self._context_id = context_id
        self._borrowed_pointers = borrowed_pointers
        self._pointers = pointers
        self._owned_buffers = owned_buffers
        self._telemetry = telemetry
        self._closed = False
        self._poisoned = opening_status == "poisoned"
        self._cleanup_failed = opening_status == "cleanup_failed"
        self._failure_reason = failure_reason
        self._kernel_closed = kernel_closed
        self._lease_released = False
        self._close_sync_complete = False
        self._enqueue_sequence = 0
        self._direction_generation = 0
        self._downstream_consumer_token: object | None = None
        self._released_downstream_consumer_token: object | None = None
        self._downstream_consumer_epoch_value = 0
        self._active_device_direction_generation: int | None = None
        self._evaluation_active = False
        self._queue_lock = threading.RLock()
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
            f"HipResidentCsrExecutionContext(context_id={self._context_id!r}, "
            f"status={status!r})"
        )

    def __enter__(self) -> HipResidentCsrExecutionContext:
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
    def opening_receipt(self) -> HipResidentCsrContextReceipt:
        return self._opening_receipt

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def parent_context(self) -> HipAssemblyExecutionContext:
        """Return metadata/lifetime authority, never a serialized handle."""

        return self._parent

    def receipt(self) -> HipResidentCsrContextReceipt:
        with self._queue_lock:
            if self._cleanup_failed:
                status: ContextStatus = "cleanup_failed"
            elif self._closed:
                status = "context_closed"
            elif self._poisoned:
                status = "poisoned"
            else:
                status = "context_ready"
            return self._build_receipt(status)

    def enqueue_residual_jvp(self) -> HipResidentCsrEnqueueReceipt:
        """Enqueue one fused device operation with zero transfer or fence."""

        with self._queue_lock:
            self._require_no_downstream_consumer()
            return self._enqueue_residual_jvp_locked()

    def _enqueue_residual_jvp_locked(self) -> HipResidentCsrEnqueueReceipt:
        """Queue one apply while the process-local serial lock is held."""

        self._require_usable()
        self._parent._require_resident_consumer(self._lease_token)
        self._validate_runtime_authority()
        self._validate_borrowed_pointers()
        if self._direction_generation <= 0:
            _fail(
                "hip_resident_direction_uninitialized",
                "/direction_workspace",
                "A host verification upload or device producer must initialize direction.",
            )
        if self._kernel_binding is None:  # pragma: no cover - ready invariant
            _fail("hip_resident_kernel_missing", "/kernel")
        try:
            self._validate_live_kernel_authority()
        except Exception as exc:
            return self._failed_enqueue(
                "hip_resident_kernel_binding_changed", exc, attempted=False
            )

        sequence = self._enqueue_sequence + 1
        delta = HipResidentCsrEnqueueDelta(0, 0, 0, 0, 0, 0, 1, 0, 0)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_attempt_count=self._telemetry.kernel_launch_attempt_count + 1,
        )
        try:
            result = self._rtc_kernel.launch_residual_jvp(
                self._stream,
                self._plan.dof_count,
                self._borrowed_pointers["csr_row_ptr"],
                self._borrowed_pointers["csr_column_indices"],
                self._borrowed_pointers["csr_values"],
                self._pointers["state_displacement"],
                self._borrowed_pointers["load_vector_si"],
                self._pointers["direction_workspace"],
                self._pointers["residual_workspace"],
                self._pointers["jvp_workspace"],
            )
            if result is not None:
                raise HipResidentCsrContextError(
                    "hip_resident_kernel_contract_invalid",
                    "/kernel/launch_residual_jvp",
                    "Kernel launch must return None or raise.",
                )
        except Exception as exc:
            return self._failed_enqueue(
                "hip_resident_kernel_launch_failed", exc, attempted=True
            )

        self._enqueue_sequence = sequence
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_success_count=self._telemetry.kernel_launch_success_count + 1,
        )
        delta = replace(delta, kernel_launch_success_count=1)
        return _build_enqueue_receipt(
            status="enqueued",
            context=self,
            sequence=sequence,
            delta=delta,
            reason=None,
        )

    def evaluate_for_verification(self, direction: Any) -> HipResidentCsrEvaluation:
        """Upload one direction, enqueue, export both outputs, fence, and replay."""

        with self._queue_lock:
            return self._evaluate_for_verification_locked(direction)

    def _evaluate_for_verification_locked(
        self, direction: Any
    ) -> HipResidentCsrEvaluation:
        """Run the explicit host verification path under the serial lock."""

        self._require_usable()
        self._require_no_downstream_consumer()
        if self._evaluation_active:
            _fail(
                "hip_resident_evaluation_reentrant",
                "/evaluation",
                "Verification evaluations are serialized.",
            )
        vector = _direction_vector(direction, self._plan.dof_count)
        direction_descriptor = _array_descriptor(vector)
        execution_id = canonical_hash(
            {
                "context_id": self._context_id,
                "opening_context_receipt_hash": (
                    self._opening_receipt.context_receipt_hash
                ),
                "direction_hash": direction_descriptor.data_hash,
                "next_sequence": self._enqueue_sequence + 1,
            }
        )
        delta = HipResidentCsrEvaluationDelta(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        work = HipResidentCsrWorkReceipt(self._plan.dof_count, self._plan.nnz)
        try:
            host_residual = np.empty(self._plan.dof_count, dtype="<f8")
            host_jvp = np.empty(self._plan.dof_count, dtype="<f8")
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                None,
                "hip_resident_host_staging_failed",
                exc,
                poison=False,
            )

        self._evaluation_active = True
        try:
            delta = replace(
                delta,
                h2d_operation_attempt_count=1,
                h2d_bytes_attempted=int(vector.nbytes),
            )
            self._telemetry = replace(
                self._telemetry,
                h2d_operation_attempt_count=(
                    self._telemetry.h2d_operation_attempt_count + 1
                ),
                h2d_bytes_attempted=(
                    self._telemetry.h2d_bytes_attempted + int(vector.nbytes)
                ),
            )
            self._runtime.copy_h2d_async(
                self._pointers["direction_workspace"], vector, self._stream
            )
            self._direction_generation += 1
            delta = replace(
                delta,
                h2d_operation_success_count=1,
                h2d_bytes_succeeded=int(vector.nbytes),
            )
            self._telemetry = replace(
                self._telemetry,
                h2d_operation_success_count=(
                    self._telemetry.h2d_operation_success_count + 1
                ),
                h2d_bytes_succeeded=(
                    self._telemetry.h2d_bytes_succeeded + int(vector.nbytes)
                ),
            )
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                None,
                "hip_resident_direction_upload_failed",
                exc,
            )

        enqueue = self._enqueue_residual_jvp_locked()
        delta = replace(
            delta,
            kernel_launch_attempt_count=(
                enqueue.telemetry_delta.kernel_launch_attempt_count
            ),
            kernel_launch_success_count=(
                enqueue.telemetry_delta.kernel_launch_success_count
            ),
        )
        if enqueue.status != "enqueued":
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                enqueue,
                "hip_resident_enqueue_failed",
                enqueue.reason.detail if enqueue.reason else "enqueue failed",
            )

        try:
            for host, name in (
                (host_residual, "residual_workspace"),
                (host_jvp, "jvp_workspace"),
            ):
                delta = replace(
                    delta,
                    d2h_operation_attempt_count=(delta.d2h_operation_attempt_count + 1),
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
                self._runtime.copy_d2h_async(host, self._pointers[name], self._stream)
                delta = replace(
                    delta,
                    d2h_operation_success_count=(delta.d2h_operation_success_count + 1),
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
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                enqueue,
                "hip_resident_result_export_failed",
                exc,
            )
        finally:
            self._evaluation_active = False

        try:
            residual = immutable_array(host_residual, dtype="<f8")
            jvp = immutable_array(host_jvp, dtype="<f8")
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                enqueue,
                "hip_resident_output_snapshot_failed",
                exc,
                poison=False,
            )
        if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(jvp)):
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                enqueue,
                "hip_resident_output_nonfinite",
                "Residual/JVP output is non-finite.",
            )
        try:
            cpu_residual = self._plan.residual(self._state.displacement_si)
            cpu_jvp = self._plan.jvp(vector)
            parity = _parity_report(
                self._plan, residual, jvp, cpu_residual, cpu_jvp, vector
            )
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                enqueue,
                "hip_resident_cpu_oracle_failed",
                exc,
                poison=False,
            )
        status: EvaluationStatus = "verified" if parity.passed else "parity_failed"
        if not parity.passed:
            self._poison("hip_resident_cpu_parity_failed")
        receipt = _build_evaluation_receipt(
            status=status,
            execution_id=execution_id,
            context=self,
            direction=direction_descriptor,
            residual=_array_descriptor(residual),
            jvp=_array_descriptor(jvp),
            delta=delta,
            parity=parity,
            work=work,
            enqueue=enqueue,
            reason=None,
        )
        evaluation = HipResidentCsrEvaluation(receipt, vector, residual, jvp, enqueue)
        return validate_hip_resident_csr_evaluation(evaluation, expected_context=self)

    def close(self) -> None:
        """Fence, free owned vectors, close module, then release parent lease."""

        with self._queue_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        """Retryable close implementation under the process-local serial lock."""

        if self._closed:
            return
        if self._downstream_consumer_token is not None:
            _fail(
                "hip_resident_downstream_consumer_active",
                "/lifetime/downstream_consumer",
                "Release the downstream device consumer before closing its resident owner.",
            )
        if not self._close_sync_complete:
            self._telemetry = replace(
                self._telemetry,
                sync_attempt_count=self._telemetry.sync_attempt_count + 1,
            )
            try:
                self._runtime.synchronize(self._stream)
            except Exception as exc:
                self._poison("hip_resident_cleanup_sync_failed")
                self._cleanup_failed = True
                self._failure_reason = HipResidentCsrReason(
                    "hip_resident_cleanup_sync_failed", _exception_detail(exc)
                )
                raise HipResidentCsrContextError(
                    "hip_resident_cleanup_sync_failed",
                    "/cleanup/synchronize",
                    self._failure_reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._close_sync_complete = True
            self._telemetry = replace(
                self._telemetry,
                sync_success_count=self._telemetry.sync_success_count + 1,
            )

        first_error: Exception | None = None
        for name in reversed(_OWNED_BUFFER_ORDER):
            pointer = self._pointers.get(name)
            if pointer is None:
                continue
            self._telemetry = replace(
                self._telemetry,
                owned_deallocation_attempt_count=(
                    self._telemetry.owned_deallocation_attempt_count + 1
                ),
            )
            try:
                self._runtime.free(pointer)
            except Exception as exc:
                first_error = first_error or exc
                continue
            del self._pointers[name]
            byte_length = _view(self._owned_buffers, name).byte_length
            self._telemetry = replace(
                self._telemetry,
                owned_deallocation_success_count=(
                    self._telemetry.owned_deallocation_success_count + 1
                ),
                owned_current_device_bytes=(
                    self._telemetry.owned_current_device_bytes - byte_length
                ),
            )
        if self._pointers:
            self._cleanup_failed = True
            self._failure_reason = HipResidentCsrReason(
                "hip_resident_cleanup_failed",
                _exception_detail(first_error or "owned allocations remain"),
            )
            raise HipResidentCsrContextError(
                "hip_resident_cleanup_failed",
                "/cleanup/owned_buffers",
                self._failure_reason.detail,
                cleanup_owner=self,
            )

        if not self._kernel_closed and self._rtc_kernel is not None:
            self._telemetry = replace(
                self._telemetry,
                module_close_attempt_count=(
                    self._telemetry.module_close_attempt_count + 1
                ),
            )
            try:
                self._rtc_kernel.close()
            except Exception as exc:
                self._cleanup_failed = True
                self._failure_reason = HipResidentCsrReason(
                    "hip_resident_kernel_cleanup_failed", _exception_detail(exc)
                )
                raise HipResidentCsrContextError(
                    "hip_resident_kernel_cleanup_failed",
                    "/cleanup/kernel",
                    self._failure_reason.detail,
                    cleanup_owner=self,
                ) from exc
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
                self._parent._release_resident_consumer(self._lease_token)
            except Exception as exc:
                self._cleanup_failed = True
                self._failure_reason = HipResidentCsrReason(
                    "hip_resident_lease_release_failed", _exception_detail(exc)
                )
                raise HipResidentCsrContextError(
                    "hip_resident_lease_release_failed",
                    "/cleanup/lease",
                    self._failure_reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._lease_released = True
            self._telemetry = replace(
                self._telemetry,
                lease_release_success_count=(
                    self._telemetry.lease_release_success_count + 1
                ),
            )
        self._closed = True
        self._cleanup_failed = False
        self._failure_reason = None

    def _acquire_downstream_consumer(self, token: object | None = None) -> object:
        """Exclusively lease resident workspaces to one process-local child."""

        with self._queue_lock:
            self._require_usable()
            self._parent._require_resident_consumer(self._lease_token)
            self._validate_runtime_authority()
            self._validate_borrowed_pointers()
            if self._downstream_consumer_token is not None:
                _fail(
                    "hip_resident_downstream_consumer_active",
                    "/lifetime/downstream_consumer",
                    "The resident workspaces already have an active downstream consumer.",
                )
            issued_token = object() if token is None else token
            self._downstream_consumer_epoch_value += 1
            self._released_downstream_consumer_token = None
            self._downstream_consumer_token = issued_token
            self._active_device_direction_generation = None
            return issued_token

    def _downstream_consumer_epoch_if_owned(
        self,
        token: object,
    ) -> int | None:
        """Recover a pre-issued token handoff using host-only identity state."""

        with self._queue_lock:
            if token is self._downstream_consumer_token or (
                token is self._released_downstream_consumer_token
            ):
                return self._downstream_consumer_epoch_value
            return None

    def _require_downstream_consumer(self, token: object) -> None:
        """Require the exact live downstream capability without exposing it."""

        with self._queue_lock:
            self._require_downstream_token(token)
            self._require_usable()

    def _downstream_consumer_epoch(self, token: object) -> int:
        """Return the monotonic child epoch for one exact live capability."""

        with self._queue_lock:
            self._require_downstream_token(token)
            self._require_usable()
            return self._downstream_consumer_epoch_value

    def _poison_downstream_consumer(self, token: object, detail: str) -> None:
        """Poison child, resident, and assembly ordering after device failure."""

        with self._queue_lock:
            self._require_downstream_token(token)
            self._poison(_bounded_detail(detail))

    def _release_downstream_consumer(self, token: object) -> None:
        """Release the exact child capability after its own ordered cleanup."""

        with self._queue_lock:
            if token is self._released_downstream_consumer_token:
                if self._downstream_consumer_token is token:
                    self._active_device_direction_generation = None
                    self._downstream_consumer_token = None
                elif self._downstream_consumer_token is not None:
                    _fail(
                        "hip_resident_downstream_consumer_token_invalid",
                        "/lifetime/downstream_consumer",
                        "Released token conflicts with the active consumer.",
                    )
                return
            self._require_downstream_token(token)
            self._active_device_direction_generation = None
            # Publish the exact terminal tombstone before clearing the live
            # slot.  A BaseException between these assignments therefore
            # remains idempotently recoverable by the same caller token.
            self._released_downstream_consumer_token = token
            self._downstream_consumer_token = None

    def _publish_device_direction(self, token: object) -> int:
        """Publish one successfully enqueued same-stream producer generation.

        The downstream child calls this only after its package-owned producer
        launch returns successfully.  A failed launch must instead call
        :meth:`_poison_downstream_consumer` and must never publish.  The returned
        integer is process-local ordering state, not serialized evidence.
        """

        with self._queue_lock:
            self._require_downstream_token(token)
            self._require_usable()
            self._parent._require_resident_consumer(self._lease_token)
            self._validate_runtime_authority()
            self._validate_borrowed_pointers()
            self._direction_generation += 1
            self._active_device_direction_generation = self._direction_generation
            return self._direction_generation

    def _enqueue_residual_jvp_from_device(
        self,
        token: object,
        generation: int,
    ) -> HipResidentCsrEnqueueReceipt:
        """Apply resident CSR once for the exact current device generation."""

        with self._queue_lock:
            self._require_downstream_token(token)
            self._require_usable()
            if (
                type(generation) is not int
                or generation != self._active_device_direction_generation
                or generation != self._direction_generation
            ):
                _fail(
                    "hip_resident_device_direction_stale_or_consumed",
                    "/downstream/device_direction",
                    "Direction handle is stale, foreign, or already consumed.",
                )
            receipt = self._enqueue_residual_jvp_locked()
            if receipt.status == "enqueued":
                self._active_device_direction_generation = None
            return receipt

    def _require_downstream_token(self, token: object) -> None:
        """Identity-only token check usable during poisoned cleanup."""

        if token is not self._downstream_consumer_token:
            _fail(
                "hip_resident_downstream_consumer_token_invalid",
                "/lifetime/downstream_consumer",
                "Downstream consumer token is stale or foreign.",
            )

    def _require_no_downstream_consumer(self) -> None:
        """Keep legacy host verification separate from child workspace authority."""

        if self._downstream_consumer_token is not None:
            _fail(
                "hip_resident_downstream_consumer_active",
                "/lifetime/downstream_consumer",
                "Legacy host verification is unavailable while a child owns the workspaces.",
            )

    def _failed_enqueue(
        self, code: str, error: Any, *, attempted: bool
    ) -> HipResidentCsrEnqueueReceipt:
        self._poison(code)
        delta = HipResidentCsrEnqueueDelta(0, 0, 0, 0, 0, 0, int(attempted), 0, 0)
        return _build_enqueue_receipt(
            status="unavailable",
            context=self,
            sequence=self._enqueue_sequence + 1,
            delta=delta,
            reason=HipResidentCsrReason(code, _exception_detail(error)),
        )

    def _failed_evaluation(
        self,
        execution_id: str,
        direction: np.ndarray,
        direction_descriptor: HipResidentCsrArrayDescriptor,
        delta: HipResidentCsrEvaluationDelta,
        work: HipResidentCsrWorkReceipt,
        enqueue: HipResidentCsrEnqueueReceipt | None,
        code: str,
        error: Any,
        *,
        poison: bool = True,
    ) -> HipResidentCsrEvaluation:
        self._evaluation_active = False
        if poison:
            self._poison(code)
        receipt = _build_evaluation_receipt(
            status="unavailable",
            execution_id=execution_id,
            context=self,
            direction=direction_descriptor,
            residual=None,
            jvp=None,
            delta=delta,
            parity=None,
            work=work,
            enqueue=enqueue,
            reason=HipResidentCsrReason(code, _exception_detail(error)),
        )
        return HipResidentCsrEvaluation(receipt, direction, None, None, enqueue)

    def _poison(self, detail: str) -> None:
        self._poisoned = True
        self._failure_reason = HipResidentCsrReason(
            "hip_resident_context_poisoned", _bounded_detail(detail)
        )
        if not self._parent.poisoned:
            try:
                self._parent._poison_resident_consumer(self._lease_token, detail)
            except Exception:
                # Parent cleanup ownership remains reachable through ``self``;
                # never replace the primary downstream failure with diagnostics.
                pass

    def _require_usable(self) -> None:
        if self._closed:
            _fail("hip_resident_context_closed", "/status")
        if self._cleanup_failed:
            _fail("hip_resident_context_cleanup_failed", "/status")
        if self._poisoned:
            _fail("hip_resident_context_poisoned", "/status")

    def _validate_borrowed_pointers(self) -> None:
        current = {
            "csr_row_ptr": self._parent._pointers.get("csr_row_ptr"),
            "csr_column_indices": self._parent._pointers.get("csr_column_indices"),
            "csr_values": self._parent._pointers.get("csr_values"),
            "load_vector_si": self._parent._base_context._pointers.get(
                "load_vector_si"
            ),
        }
        if any(
            current[name] is not self._borrowed_pointers[name]
            for name in _BORROWED_BUFFER_ORDER
        ):
            self._poison("hip_resident_borrowed_pointer_changed")
            _fail(
                "hip_resident_borrowed_pointer_changed",
                "/parent/borrowed_buffers",
                "Parent device-buffer identity changed after lease acquisition.",
            )

    def _validate_runtime_authority(self) -> None:
        if any(
            (
                self._runtime is not self._runtime_snapshot,
                self._stream is not self._stream_snapshot,
                self._parent._runtime is not self._runtime_snapshot,
                self._parent._stream is not self._stream_snapshot,
                self._parent._base_context is not self._base_context_snapshot,
                self._parent._base_context.closed,
                self._parent._operator_view.device_ordinal
                != self._device_ordinal_snapshot,
            )
        ):
            self._poison("hip_resident_runtime_authority_changed")
            _fail(
                "hip_resident_runtime_authority_changed",
                "/parent/runtime_authority",
                "Runtime, device, stream, or foundation identity changed.",
            )

    def _validate_live_kernel_authority(self) -> None:
        if self._rtc_kernel is None or bool(getattr(self._rtc_kernel, "closed", False)):
            _fail("hip_resident_kernel_closed", "/kernel")
        identity = getattr(self._rtc_kernel, "identity", None)
        if identity is not self._kernel_identity_snapshot:
            _fail("hip_resident_kernel_binding_changed", "/kernel/identity")
        identity_hash = getattr(identity, "identity_hash", None)
        if identity_hash is not None:
            if (
                type(identity_hash) is not str
                or identity_hash != self._kernel_binding.identity_hash
            ):
                _fail("hip_resident_kernel_binding_changed", "/kernel/identity")
            return
        # Injected test doubles are non-promoting and may expose only a mutable
        # manifest. Keep their adversarial validation deep without imposing
        # filesystem/library hashing on the exact native Krylov hot path.
        _validate_live_rtc_kernel(self._rtc_kernel, self._kernel_binding)

    def _build_receipt(self, status: ContextStatus) -> HipResidentCsrContextReceipt:
        ready = status == "context_ready"
        reason = (
            None
            if status in ("context_ready", "context_closed")
            else self._failure_reason
        )
        return _build_context_receipt(
            status=status,
            context_id=self._context_id,
            actual_backend=(
                "hip"
                if self._evidence_scope == "native_hiprtc_composite"
                else "test_double"
            ),
            evidence_scope=self._evidence_scope,
            reason=reason,
            bindings=_bindings(
                self._parent,
                self._state,
                self._lease_epoch,
                self._kernel_internally_compiled,
            ),
            kernel=self._kernel_binding,
            dimensions=_dimensions(self._plan),
            owned_buffers=self._owned_buffers,
            telemetry=self._telemetry,
            claims=_claims(
                ready,
                self._evidence_scope,
                lease_active=not self._lease_released,
            ),
        )


def open_hip_resident_csr_execution_context(
    parent: HipAssemblyExecutionContext,
    committed_state: StateIR,
    *,
    architecture: str | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    rtc_kernel: Any | None = None,
) -> HipResidentCsrContextOpenResult:
    """Borrow a ready assembly operator without another context/stream/CSR."""

    if type(parent) is not HipAssemblyExecutionContext:
        _fail(
            "hip_resident_parent_type_invalid",
            "/parent",
            "Expected the exact assembly context owner type.",
        )
    parent_view = parent.operator_view()
    plan = parent._source_plan
    validate_execution_plan_v2(plan, expected_buffers=parent._buffers)
    validate_state_ir(committed_state, expected_plan=plan)
    if committed_state.role != "committed":
        _fail(
            "hip_resident_state_role_invalid",
            "/committed_state/role",
            "Resident consumer requires a committed StateIR.",
        )
    _validate_load_alias(parent, plan)
    requested_architecture = parent._kernel_binding.architecture
    if architecture is not None and architecture != requested_architecture:
        _fail(
            "hip_resident_architecture_mismatch",
            "/architecture",
            "Residual kernel architecture must match the assembly context.",
        )
    if isinstance(memory_budget_bytes, bool) or (
        memory_budget_bytes is not None
        and (not isinstance(memory_budget_bytes, int) or memory_budget_bytes <= 0)
    ):
        _fail("hip_resident_memory_budget_invalid", "/memory_budget_bytes")
    if rtc_kernel is not None:
        _validate_caller_kernel_preflight(rtc_kernel)

    views = _owned_buffer_views(committed_state, plan.dof_count)
    child_bytes = sum(view.byte_length for view in views)
    parent_bytes = int(parent._telemetry.current_device_payload_bytes)
    if (
        memory_budget_bytes is not None
        and parent_bytes + child_bytes > memory_budget_bytes
    ):
        _fail(
            "hip_resident_memory_budget_exceeded",
            "/memory_budget_bytes",
            f"Required {parent_bytes + child_bytes} bytes exceeds budget {memory_budget_bytes}.",
        )

    borrowed_device_bytes = _borrowed_bytes(parent, plan)
    token = parent._acquire_resident_consumer()
    lease_epoch = parent._resident_consumer_epoch(token)
    borrowed_pointers: dict[str, Any] = {}
    kernel_internally_compiled = rtc_kernel is None
    kernel = rtc_kernel
    binding: HipRtcKernelBinding | None = None
    pointers: dict[str, Any] = {}
    telemetry = HipResidentCsrTelemetry(
        borrowed_device_bytes=borrowed_device_bytes,
        module_owner_acquired_count=int(kernel is not None),
    )
    evidence_scope: EvidenceScope = "injected_test_double"
    try:
        borrowed_pointers = _borrowed_pointer_snapshot(parent)
        if kernel is None:
            loaded_runtime = _loaded_runtime(parent)
            if not callable(getattr(loaded_runtime, "bind", None)):
                _fail(
                    "hip_resident_runtime_invalid",
                    "/kernel/compile",
                    "Native compilation requires the parent's loaded runtime API.",
                )
            selector = getattr(parent._runtime, "set_device", None)
            if callable(selector):
                selector(parent_view.device_ordinal)
            try:
                kernel = compile_hip_rtc_csr_kernel(
                    loaded_runtime,
                    requested_architecture,
                    hiprtc_library=hiprtc_library,
                )
            except HipRtcError as exc:
                raise HipResidentCsrContextError(
                    exc.code, "/kernel/compile", exc.message
                ) from exc
            telemetry = replace(telemetry, module_owner_acquired_count=1)
        binding = _rtc_kernel_binding(kernel, requested_architecture)
        evidence_scope = _evidence_scope(
            parent, kernel, binding, kernel_internally_compiled
        )
        context_id = _context_id(
            parent, committed_state, lease_epoch, binding, evidence_scope
        )
        runtime = parent._runtime
        for view in views:
            telemetry = replace(
                telemetry,
                owned_allocation_attempt_count=(
                    telemetry.owned_allocation_attempt_count + 1
                ),
            )
            pointer = runtime.malloc(view.byte_length)
            pointers[view.name] = pointer
            current = telemetry.owned_current_device_bytes + view.byte_length
            telemetry = replace(
                telemetry,
                owned_allocation_success_count=(
                    telemetry.owned_allocation_success_count + 1
                ),
                owned_current_device_bytes=current,
                owned_peak_device_bytes=max(telemetry.owned_peak_device_bytes, current),
            )
            if view.name == "state_displacement":
                telemetry = replace(
                    telemetry,
                    h2d_operation_attempt_count=(
                        telemetry.h2d_operation_attempt_count + 1
                    ),
                    h2d_bytes_attempted=(
                        telemetry.h2d_bytes_attempted + view.byte_length
                    ),
                )
                runtime.copy_h2d_async(
                    pointer, committed_state.displacement_si, parent._stream
                )
                telemetry = replace(
                    telemetry,
                    h2d_operation_success_count=(
                        telemetry.h2d_operation_success_count + 1
                    ),
                    h2d_bytes_succeeded=(
                        telemetry.h2d_bytes_succeeded + view.byte_length
                    ),
                )
        telemetry = replace(
            telemetry, sync_attempt_count=telemetry.sync_attempt_count + 1
        )
        runtime.synchronize(parent._stream)
        telemetry = replace(
            telemetry, sync_success_count=telemetry.sync_success_count + 1
        )
        context = HipResidentCsrExecutionContext(
            parent=parent,
            lease_token=token,
            lease_epoch=lease_epoch,
            state=committed_state,
            rtc_kernel=kernel,
            kernel_binding=binding,
            evidence_scope=evidence_scope,
            kernel_internally_compiled=kernel_internally_compiled,
            context_id=context_id,
            borrowed_pointers=borrowed_pointers,
            pointers=pointers,
            owned_buffers=views,
            telemetry=telemetry,
            opening_status="context_ready",
            failure_reason=None,
        )
        validate_hip_resident_csr_context_receipt(
            context.opening_receipt, expected_context=context
        )
        return HipResidentCsrContextOpenResult(context, context.opening_receipt)
    except Exception as primary:
        return _cleanup_failed_open(
            primary=primary,
            parent=parent,
            token=token,
            lease_epoch=lease_epoch,
            state=committed_state,
            kernel=kernel,
            binding=binding,
            evidence_scope=evidence_scope,
            kernel_internally_compiled=kernel_internally_compiled,
            borrowed_pointers=borrowed_pointers,
            pointers=pointers,
            views=views,
            telemetry=telemetry,
        )


def _cleanup_failed_open(
    *,
    primary: Exception,
    parent: HipAssemblyExecutionContext,
    token: object,
    lease_epoch: int,
    state: StateIR,
    kernel: Any,
    binding: HipRtcKernelBinding | None,
    evidence_scope: EvidenceScope,
    kernel_internally_compiled: bool,
    borrowed_pointers: dict[str, Any],
    pointers: dict[str, Any],
    views: tuple[HipResidentCsrBufferView, ...],
    telemetry: HipResidentCsrTelemetry,
) -> HipResidentCsrContextOpenResult:
    """Clean an incomplete child open or return a retryable cleanup owner."""

    cleanup_error: Exception | None = None
    cleanup_sync_complete = not pointers
    if pointers:
        telemetry = replace(
            telemetry, sync_attempt_count=telemetry.sync_attempt_count + 1
        )
        try:
            parent._runtime.synchronize(parent._stream)
        except Exception as exc:
            cleanup_error = exc
            if not parent.poisoned:
                try:
                    parent._poison_resident_consumer(
                        token, "hip_resident_open_cleanup_sync_failed"
                    )
                except Exception:
                    pass
        else:
            cleanup_sync_complete = True
            telemetry = replace(
                telemetry, sync_success_count=telemetry.sync_success_count + 1
            )
    if cleanup_sync_complete:
        for name in reversed(_OWNED_BUFFER_ORDER):
            pointer = pointers.get(name)
            if pointer is None:
                continue
            telemetry = replace(
                telemetry,
                owned_deallocation_attempt_count=(
                    telemetry.owned_deallocation_attempt_count + 1
                ),
            )
            try:
                parent._runtime.free(pointer)
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                continue
            del pointers[name]
            byte_length = _view(views, name).byte_length
            telemetry = replace(
                telemetry,
                owned_deallocation_success_count=(
                    telemetry.owned_deallocation_success_count + 1
                ),
                owned_current_device_bytes=(
                    telemetry.owned_current_device_bytes - byte_length
                ),
            )
    kernel_closed = kernel is None
    if not pointers and kernel is not None:
        telemetry = replace(
            telemetry,
            module_close_attempt_count=telemetry.module_close_attempt_count + 1,
        )
        try:
            kernel.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        else:
            kernel_closed = True
            telemetry = replace(
                telemetry,
                module_close_success_count=(telemetry.module_close_success_count + 1),
            )
    lease_released = False
    if not pointers and kernel_closed:
        telemetry = replace(
            telemetry,
            lease_release_attempt_count=telemetry.lease_release_attempt_count + 1,
        )
        try:
            parent._release_resident_consumer(token)
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        else:
            lease_released = True
            telemetry = replace(
                telemetry,
                lease_release_success_count=(telemetry.lease_release_success_count + 1),
            )
    reason = HipResidentCsrReason(
        "hip_resident_context_open_failed", _exception_detail(primary)
    )
    context_id = _fallback_context_id(parent, state, lease_epoch, binding)
    if pointers or not kernel_closed or not lease_released:
        reason = HipResidentCsrReason(
            "hip_resident_context_cleanup_failed",
            _bounded_detail(
                f"{_exception_detail(primary)}; cleanup: "
                f"{_exception_detail(cleanup_error or 'incomplete ownership')}"
            ),
        )
        context = HipResidentCsrExecutionContext(
            parent=parent,
            lease_token=token,
            lease_epoch=lease_epoch,
            state=state,
            rtc_kernel=kernel,
            kernel_binding=binding,
            evidence_scope=evidence_scope,
            kernel_internally_compiled=kernel_internally_compiled,
            context_id=context_id,
            borrowed_pointers=borrowed_pointers,
            pointers=pointers,
            owned_buffers=views,
            telemetry=telemetry,
            opening_status="cleanup_failed",
            failure_reason=reason,
            kernel_closed=kernel_closed,
        )
        context._lease_released = lease_released
        context._close_sync_complete = cleanup_sync_complete
        return HipResidentCsrContextOpenResult(context, context.opening_receipt)

    receipt = _build_context_receipt(
        status="unavailable",
        context_id=context_id,
        actual_backend=None,
        evidence_scope=evidence_scope,
        reason=reason,
        bindings=_bindings(parent, state, lease_epoch, kernel_internally_compiled),
        kernel=binding,
        dimensions=_dimensions(parent._source_plan),
        owned_buffers=(),
        telemetry=telemetry,
        claims=_claims(False, evidence_scope, lease_active=False),
    )
    return HipResidentCsrContextOpenResult(None, receipt)


def _bindings(
    parent: HipAssemblyExecutionContext,
    state: StateIR,
    lease_epoch: int,
    kernel_internally_compiled: bool,
) -> HipResidentCsrBindings:
    view = parent._operator_view
    if view is None:
        _fail("hip_resident_parent_operator_missing", "/parent/operator_view")
    plan = parent._source_plan
    load = plan.array("global_load")
    return HipResidentCsrBindings(
        parent_context_id=parent.context_id,
        parent_opening_receipt_hash=parent.opening_receipt.context_receipt_hash,
        parent_assembly_evaluation_receipt_hash=(
            parent.opening_evaluation.receipt.receipt_hash
        ),
        parent_operator_id=view.operator_id,
        parent_operator_metadata_hash=view.metadata_hash,
        parent_assembly_kernel_identity_hash=parent._kernel_binding.identity_hash,
        parent_runtime_library_sha256=(parent._kernel_binding.runtime_library_sha256),
        parent_architecture=parent._kernel_binding.architecture,
        parent_evidence_scope=parent._evidence_scope,
        source_execution_plan_hash=plan.plan_hash,
        source_operator_hash=plan.operator_hash,
        source_numeric_snapshot_hash=plan.numeric_snapshot_hash,
        source_partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        load_vector_hash=array_data_hash(load),
        state_hash=state.state_hash,
        state_epoch=state.epoch,
        state_displacement_hash=array_data_hash(state.displacement_si),
        device_ordinal=view.device_ordinal,
        lease_epoch=lease_epoch,
        residual_kernel_origin=(
            "internally_compiled" if kernel_internally_compiled else "caller_supplied"
        ),
    )


def _dimensions(plan: ExecutionPlanV2) -> HipResidentCsrDimensions:
    return HipResidentCsrDimensions(
        global_dof_count=plan.dof_count,
        free_dof_count=int(plan.array("free_dofs").size),
        constrained_dof_count=int(plan.array("constrained_dofs").size),
        csr_nnz=plan.nnz,
    )


def _owned_buffer_views(
    state: StateIR, dof_count: int
) -> tuple[HipResidentCsrBufferView, ...]:
    state_view = HipResidentCsrBufferView(
        "state_displacement",
        "<f8",
        (dof_count,),
        8 * dof_count,
        array_data_hash(state.displacement_si),
        "read_only",
        "async_h2d_once_then_same_stream_fence",
    )
    return (
        state_view,
        HipResidentCsrBufferView(
            "direction_workspace",
            "<f8",
            (dof_count,),
            8 * dof_count,
            None,
            "read_write",
            "none",
        ),
        HipResidentCsrBufferView(
            "residual_workspace",
            "<f8",
            (dof_count,),
            8 * dof_count,
            None,
            "write_only",
            "none",
        ),
        HipResidentCsrBufferView(
            "jvp_workspace",
            "<f8",
            (dof_count,),
            8 * dof_count,
            None,
            "write_only",
            "none",
        ),
    )


def _borrowed_bytes(parent: HipAssemblyExecutionContext, plan: ExecutionPlanV2) -> int:
    load_view = parent._base_context.buffer("load_vector_si")
    return (
        _assembly_child_view(parent, "csr_row_ptr").byte_length
        + _assembly_child_view(parent, "csr_column_indices").byte_length
        + _assembly_child_view(parent, "csr_values").byte_length
        + load_view.byte_length
    )


def _borrowed_pointer_snapshot(
    parent: HipAssemblyExecutionContext,
) -> dict[str, Any]:
    snapshot = {
        "csr_row_ptr": parent._pointers.get("csr_row_ptr"),
        "csr_column_indices": parent._pointers.get("csr_column_indices"),
        "csr_values": parent._pointers.get("csr_values"),
        "load_vector_si": parent._base_context._pointers.get("load_vector_si"),
    }
    if any(snapshot[name] is None for name in _BORROWED_BUFFER_ORDER):
        _fail(
            "hip_resident_parent_buffer_missing",
            "/parent/borrowed_buffers",
            "Parent does not expose the four required resident buffers.",
        )
    return snapshot


def _assembly_child_view(parent: HipAssemblyExecutionContext, name: str) -> Any:
    for view in parent._child_buffers:
        if view.name == name:
            return view
    _fail("hip_resident_parent_buffer_missing", f"/parent/child_buffers/{name}")


def _view(
    views: tuple[HipResidentCsrBufferView, ...], name: str
) -> HipResidentCsrBufferView:
    for view in views:
        if view.name == name:
            return view
    _fail("hip_resident_owned_buffer_missing", f"/owned_buffers/{name}")


def _validate_load_alias(
    parent: HipAssemblyExecutionContext, plan: ExecutionPlanV2
) -> None:
    plan_load = plan.array("global_load")
    foundation_load = parent._buffers.array("load_vector_si").reshape(-1)
    if (
        plan_load.dtype.str != "<f8"
        or foundation_load.dtype.str != "<f8"
        or plan_load.shape != foundation_load.shape
        or not np.array_equal(plan_load, foundation_load)
        or array_data_hash(plan_load) != array_data_hash(foundation_load)
    ):
        _fail(
            "hip_resident_load_binding_mismatch",
            "/parent/foundation/load_vector_si",
            "ExecutionPlan load is not byte-equivalent to the resident foundation load.",
        )


def _evidence_scope(
    parent: HipAssemblyExecutionContext,
    kernel: Any,
    binding: HipRtcKernelBinding,
    kernel_internally_compiled: bool,
) -> EvidenceScope:
    native = (
        kernel_internally_compiled
        and parent._evidence_scope == "native_hiprtc"
        and type(_loaded_runtime(parent)) is LoadedHipRuntime
        and type(kernel) is HipRtcCsrKernel
        and binding.architecture == parent._kernel_binding.architecture
        and binding.runtime_library_sha256
        == parent._kernel_binding.runtime_library_sha256
        and binding.runtime_library_discovery_source != "injected"
        and binding.hiprtc_library_discovery_source != "injected"
    )
    return "native_hiprtc_composite" if native else "injected_test_double"


def _loaded_runtime(parent: HipAssemblyExecutionContext) -> Any:
    """Return the exact module API owner beneath the foundation wrapper."""

    return getattr(parent._runtime, "_loaded", parent._runtime)


def _validate_caller_kernel_preflight(kernel: Any) -> None:
    """Reject caller-owned kernels that cannot be reclaimed before leasing."""

    try:
        launch = getattr(kernel, "launch_residual_jvp", None)
        close = getattr(kernel, "close", None)
        closed = bool(getattr(kernel, "closed", False))
    except Exception as exc:
        raise HipResidentCsrContextError(
            "hip_resident_kernel_contract_invalid",
            "/rtc_kernel",
            _exception_detail(exc),
        ) from exc
    if not callable(launch) or not callable(close):
        _fail(
            "hip_resident_kernel_contract_invalid",
            "/rtc_kernel",
            "Caller kernel must expose launch_residual_jvp() and close().",
        )
    if closed:
        _fail(
            "hip_resident_kernel_closed",
            "/rtc_kernel/closed",
            "Caller kernel is already closed.",
        )


def _context_id(
    parent: HipAssemblyExecutionContext,
    state: StateIR,
    lease_epoch: int,
    binding: HipRtcKernelBinding,
    evidence_scope: EvidenceScope,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_RESIDENT_CSR_CAPABILITY_PROFILE,
            "parent_context_id": parent.context_id,
            "parent_operator_id": parent._operator_view.operator_id,
            "state_hash": state.state_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": binding.identity_hash,
            "evidence_scope": evidence_scope,
        }
    )


def _fallback_context_id(
    parent: HipAssemblyExecutionContext,
    state: StateIR,
    lease_epoch: int,
    binding: HipRtcKernelBinding | None,
) -> str:
    return canonical_hash(
        {
            "capability_profile": HIP_RESIDENT_CSR_CAPABILITY_PROFILE,
            "parent_context_id": parent.context_id,
            "state_hash": state.state_hash,
            "lease_epoch": lease_epoch,
            "kernel_identity_hash": (
                _ZERO_HASH if binding is None else binding.identity_hash
            ),
        }
    )


def _claims(
    ready: bool,
    evidence_scope: EvidenceScope,
    *,
    lease_active: bool | None = None,
) -> HipResidentCsrClaims:
    active = ready if lease_active is None else lease_active
    return HipResidentCsrClaims(
        exclusive_parent_lease_active=active,
        same_runtime_device_stream=active,
        borrowed_assembly_csr=active,
        borrowed_foundation_load=active,
        resident_residual_jvp_ready=ready,
        host_csr_reupload_avoided=active,
        native_composite_context=(
            ready and evidence_scope == "native_hiprtc_composite"
        ),
    )


def _direction_vector(value: Any, count: int) -> np.ndarray:
    source = np.asarray(value)
    if source.dtype.kind not in "iuf":
        _fail("hip_resident_direction_type_invalid", "/direction")
    try:
        converted = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HipResidentCsrContextError(
            "hip_resident_direction_type_invalid", "/direction", type(exc).__name__
        ) from exc
    if converted.shape != (count,) or not converted.flags.c_contiguous:
        _fail("hip_resident_direction_shape_invalid", "/direction")
    if not np.all(np.isfinite(converted)):
        _fail("hip_resident_direction_nonfinite", "/direction")
    normalized = converted.copy(order="C")
    normalized[normalized == 0.0] = 0.0
    return immutable_array(normalized, dtype="<f8")


def _array_descriptor(array: np.ndarray) -> HipResidentCsrArrayDescriptor:
    return HipResidentCsrArrayDescriptor(
        "<f8",
        tuple(int(value) for value in array.shape),
        int(array.nbytes),
        array_data_hash(array),
    )


def _metric(actual: np.ndarray, expected: np.ndarray) -> HipResidentCsrParityMetric:
    count = int(actual.size)
    if count == 0:
        return HipResidentCsrParityMetric(0, 0.0, 0.0, 0.0, True)
    magnitude = max(
        1.0,
        float(np.max(np.abs(actual))),
        float(np.max(np.abs(expected))),
    )
    actual_scaled = actual / magnitude
    expected_scaled = expected / magnitude
    difference_scaled = actual_scaled - expected_scaled
    max_difference_scaled = float(np.max(np.abs(difference_scaled)))
    max_abs_long = np.longdouble(magnitude) * np.longdouble(max_difference_scaled)
    max_abs = float(min(max_abs_long, np.longdouble(np.finfo(np.float64).max)))
    expected_norm = float(np.linalg.norm(expected_scaled))
    difference_norm = float(np.linalg.norm(difference_scaled))
    relative = float(
        difference_norm / max(expected_norm, float(np.finfo(np.float64).tiny))
    )
    tolerance_scaled = _PARITY_TOLERANCE / magnitude + _PARITY_TOLERANCE * np.abs(
        expected_scaled
    )
    max_scaled = float(np.max(np.abs(difference_scaled) / tolerance_scaled))
    passed = bool(
        np.allclose(
            actual_scaled,
            expected_scaled,
            atol=_PARITY_TOLERANCE / magnitude,
            rtol=_PARITY_TOLERANCE,
        )
    )
    return HipResidentCsrParityMetric(count, max_abs, relative, max_scaled, passed)


def _parity_report(
    plan: ExecutionPlanV2,
    residual: np.ndarray,
    jvp: np.ndarray,
    cpu_residual: np.ndarray,
    cpu_jvp: np.ndarray,
    direction: np.ndarray,
) -> HipResidentCsrParityReport:
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    metrics = (
        _metric(residual, cpu_residual),
        _metric(residual[free], cpu_residual[free]),
        _metric(residual[constrained], cpu_residual[constrained]),
        _metric(jvp, cpu_jvp),
        _metric(jvp[free], cpu_jvp[free]),
        _metric(jvp[constrained], cpu_jvp[constrained]),
    )
    zero_exact = bool(
        np.any(direction != 0.0) or np.array_equal(jvp, np.zeros_like(jvp))
    )
    return HipResidentCsrParityReport(
        *metrics,
        zero_direction_exact=zero_exact,
        passed=all(row.passed for row in metrics) and zero_exact,
    )


def _build_context_receipt(
    *,
    status: ContextStatus,
    context_id: str,
    actual_backend: str | None,
    evidence_scope: EvidenceScope,
    reason: HipResidentCsrReason | None,
    bindings: HipResidentCsrBindings,
    kernel: HipRtcKernelBinding | None,
    dimensions: HipResidentCsrDimensions,
    owned_buffers: tuple[HipResidentCsrBufferView, ...],
    telemetry: HipResidentCsrTelemetry,
    claims: HipResidentCsrClaims,
) -> HipResidentCsrContextReceipt:
    initial = HipResidentCsrContextReceipt(
        status=status,
        context_id=context_id,
        actual_backend=actual_backend,
        evidence_scope=evidence_scope,
        promotion_eligible=False,
        reason=reason,
        bindings=bindings,
        kernel=kernel,
        dimensions=dimensions,
        owned_buffers=owned_buffers,
        telemetry=telemetry,
        claims=claims,
        context_receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        initial,
        context_receipt_hash=canonical_hash(
            _context_payload(initial, include_hash=False)
        ),
    )
    validate_hip_resident_csr_context_receipt(receipt)
    return receipt


def _build_enqueue_receipt(
    *,
    status: EnqueueStatus,
    context: HipResidentCsrExecutionContext,
    sequence: int,
    delta: HipResidentCsrEnqueueDelta,
    reason: HipResidentCsrReason | None,
) -> HipResidentCsrEnqueueReceipt:
    binding = context._kernel_binding
    initial = HipResidentCsrEnqueueReceipt(
        status=status,
        enqueue_id=canonical_hash(
            {
                "context_id": context.context_id,
                "sequence": sequence,
                "state_hash": context._state.state_hash,
            }
        ),
        context_id=context.context_id,
        opening_context_receipt_hash=(context.opening_receipt.context_receipt_hash),
        operator_id=context._parent._operator_view.operator_id,
        state_hash=context._state.state_hash,
        state_epoch=context._state.epoch,
        kernel_identity_hash=(_ZERO_HASH if binding is None else binding.identity_hash),
        sequence=sequence,
        evidence_scope=context._evidence_scope,
        promotion_eligible=False,
        reason=reason,
        telemetry_delta=delta,
        completion_fence_observed=False,
        residual_jvp_enqueued=status == "enqueued",
        solver_iteration=False,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        initial,
        receipt_hash=canonical_hash(_enqueue_payload(initial, include_hash=False)),
    )
    validate_hip_resident_csr_enqueue_receipt(receipt)
    return receipt


def _build_evaluation_receipt(
    *,
    status: EvaluationStatus,
    execution_id: str,
    context: HipResidentCsrExecutionContext,
    direction: HipResidentCsrArrayDescriptor,
    residual: HipResidentCsrArrayDescriptor | None,
    jvp: HipResidentCsrArrayDescriptor | None,
    delta: HipResidentCsrEvaluationDelta,
    parity: HipResidentCsrParityReport | None,
    work: HipResidentCsrWorkReceipt,
    enqueue: HipResidentCsrEnqueueReceipt | None,
    reason: HipResidentCsrReason | None,
) -> HipResidentCsrEvaluationReceipt:
    completed = status in ("verified", "parity_failed")
    initial = HipResidentCsrEvaluationReceipt(
        status=status,
        execution_id=execution_id,
        context_id=context.context_id,
        opening_context_receipt_hash=(context.opening_receipt.context_receipt_hash),
        enqueue=enqueue,
        evidence_scope=context._evidence_scope,
        promotion_eligible=False,
        actual_backend=(
            "hip"
            if context._evidence_scope == "native_hiprtc_composite"
            else "test_double"
        ),
        reason=reason,
        operator_id=context._parent._operator_view.operator_id,
        state_hash=context._state.state_hash,
        state_epoch=context._state.epoch,
        direction=direction,
        residual=residual,
        jvp=jvp,
        telemetry_delta=delta,
        parity=parity,
        work=work,
        claims=HipResidentCsrEvaluationClaims(
            assembled_device_csr_consumed=completed,
            residual_jvp_completed_after_fence=completed,
            cpu_reference_parity_verified=(
                status == "verified" and parity is not None and parity.passed
            ),
        ),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        initial,
        receipt_hash=canonical_hash(_evaluation_payload(initial, include_hash=False)),
    )
    validate_hip_resident_csr_evaluation_receipt(receipt)
    return receipt


def _context_payload(
    receipt: HipResidentCsrContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_RESIDENT_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_RESIDENT_CSR_CAPABILITY_PROFILE,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "actual_backend": receipt.actual_backend,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "kernel": None if receipt.kernel is None else receipt.kernel.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "borrowed_buffers": [
            {
                "name": name,
                "ownership": "parent_borrowed_process_local",
                "consumer_allocation_count": 0,
                "consumer_h2d_bytes": 0,
                "consumer_d2h_bytes": 0,
            }
            for name in _BORROWED_BUFFER_ORDER
        ],
        "owned_buffers": [view.to_dict() for view in receipt.owned_buffers],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _enqueue_payload(
    receipt: HipResidentCsrEnqueueReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_RESIDENT_CSR_ENQUEUE_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_RESIDENT_CSR_CAPABILITY_PROFILE,
        "status": receipt.status,
        "enqueue_id": receipt.enqueue_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "operator_id": receipt.operator_id,
        "state_hash": receipt.state_hash,
        "state_epoch": receipt.state_epoch,
        "kernel_identity_hash": receipt.kernel_identity_hash,
        "sequence": receipt.sequence,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "completion_fence_observed": receipt.completion_fence_observed,
        "residual_jvp_enqueued": receipt.residual_jvp_enqueued,
        "solver_iteration": receipt.solver_iteration,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _evaluation_payload(
    receipt: HipResidentCsrEvaluationReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_RESIDENT_CSR_EVALUATION_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_RESIDENT_CSR_CAPABILITY_PROFILE,
        "status": receipt.status,
        "execution_id": receipt.execution_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "enqueue": (
            None
            if receipt.enqueue is None
            else _enqueue_payload(receipt.enqueue, include_hash=True)
        ),
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "actual_backend": receipt.actual_backend,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "operator_id": receipt.operator_id,
        "state_hash": receipt.state_hash,
        "state_epoch": receipt.state_epoch,
        "direction": receipt.direction.to_dict(),
        "residual": None if receipt.residual is None else receipt.residual.to_dict(),
        "jvp": None if receipt.jvp is None else receipt.jvp.to_dict(),
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "parity": None if receipt.parity is None else receipt.parity.to_dict(),
        "work": receipt.work.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def validate_hip_resident_csr_context_receipt(
    receipt: HipResidentCsrContextReceipt,
    *,
    expected_context: HipResidentCsrExecutionContext | None = None,
) -> HipResidentCsrContextReceipt:
    if type(receipt) is not HipResidentCsrContextReceipt:
        _fail("hip_resident_context_receipt_type_invalid", "/")
    _validate_context_object_types(receipt)
    if receipt.kernel is not None:
        try:
            _validate_rtc_kernel_binding(receipt.kernel)
        except Exception as exc:
            raise HipResidentCsrContextError(
                "hip_resident_kernel_binding_invalid",
                "/kernel",
                _exception_detail(exc),
            ) from exc
    payload = _context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema_validator(), payload, "hip_resident_context")
    if receipt.context_receipt_hash != canonical_hash(
        _context_payload(receipt, include_hash=False)
    ):
        _fail("hip_resident_context_receipt_hash_mismatch", "/context_receipt_hash")
    if _has_runtime_key(payload) or _has_runtime_value(payload):
        _fail("hip_resident_runtime_handle_leak", "/")
    _validate_context_semantics(receipt)
    if expected_context is not None:
        opening = expected_context.opening_receipt
        expected = (
            opening
            if receipt.context_receipt_hash == opening.context_receipt_hash
            else expected_context._build_receipt(receipt.status)
        )
        if receipt != expected:
            _fail("hip_resident_context_live_binding_mismatch", "/")
    return receipt


def validate_hip_resident_csr_enqueue_receipt(
    receipt: HipResidentCsrEnqueueReceipt,
    *,
    expected_context: HipResidentCsrExecutionContext | None = None,
) -> HipResidentCsrEnqueueReceipt:
    if type(receipt) is not HipResidentCsrEnqueueReceipt:
        _fail("hip_resident_enqueue_receipt_type_invalid", "/")
    if type(receipt.telemetry_delta) is not HipResidentCsrEnqueueDelta or (
        receipt.reason is not None and type(receipt.reason) is not HipResidentCsrReason
    ):
        _fail("hip_resident_enqueue_nested_type_invalid", "/")
    if any(
        type(getattr(receipt, name)) is not kind
        for name, kind in (
            ("status", str),
            ("enqueue_id", str),
            ("context_id", str),
            ("opening_context_receipt_hash", str),
            ("operator_id", str),
            ("state_hash", str),
            ("state_epoch", int),
            ("kernel_identity_hash", str),
            ("sequence", int),
            ("evidence_scope", str),
            ("promotion_eligible", bool),
            ("completion_fence_observed", bool),
            ("residual_jvp_enqueued", bool),
            ("solver_iteration", bool),
            ("receipt_hash", str),
        )
    ) or any(
        type(getattr(receipt.telemetry_delta, name)) is not int
        for name in receipt.telemetry_delta.__dataclass_fields__
    ):
        _fail("hip_resident_enqueue_scalar_type_invalid", "/")
    payload = _enqueue_payload(receipt, include_hash=True)
    _validate_schema(_enqueue_schema_validator(), payload, "hip_resident_enqueue")
    if receipt.receipt_hash != canonical_hash(
        _enqueue_payload(receipt, include_hash=False)
    ):
        _fail("hip_resident_enqueue_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_key(payload) or _has_runtime_value(payload):
        _fail("hip_resident_runtime_handle_leak", "/")
    delta = receipt.telemetry_delta
    if any(
        (
            delta.h2d_operation_count != 0,
            delta.h2d_bytes != 0,
            delta.d2h_operation_count != 0,
            delta.d2h_bytes != 0,
            delta.allocation_count != 0,
            delta.sync_count != 0,
            delta.fallback_count != 0,
            receipt.promotion_eligible,
            receipt.completion_fence_observed,
            receipt.solver_iteration,
        )
    ):
        _fail("hip_resident_enqueue_zero_transfer_contract_invalid", "/")
    if receipt.status == "enqueued":
        if (
            receipt.reason is not None
            or not receipt.residual_jvp_enqueued
            or delta.kernel_launch_attempt_count != 1
            or delta.kernel_launch_success_count != 1
        ):
            _fail("hip_resident_enqueue_success_contract_invalid", "/")
    elif (
        receipt.reason is None
        or receipt.residual_jvp_enqueued
        or delta.kernel_launch_success_count != 0
        or delta.kernel_launch_attempt_count not in (0, 1)
    ):
        _fail("hip_resident_enqueue_failure_contract_invalid", "/")
    expected_enqueue_id = canonical_hash(
        {
            "context_id": receipt.context_id,
            "sequence": receipt.sequence,
            "state_hash": receipt.state_hash,
        }
    )
    if receipt.enqueue_id != expected_enqueue_id:
        _fail("hip_resident_enqueue_id_mismatch", "/enqueue_id")
    if expected_context is not None:
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.opening_context_receipt_hash
                != expected_context.opening_receipt.context_receipt_hash,
                receipt.operator_id
                != expected_context._parent._operator_view.operator_id,
                receipt.state_hash != expected_context._state.state_hash,
                receipt.state_epoch != expected_context._state.epoch,
                receipt.evidence_scope != expected_context._evidence_scope,
                receipt.kernel_identity_hash
                != (
                    _ZERO_HASH
                    if expected_context._kernel_binding is None
                    else expected_context._kernel_binding.identity_hash
                ),
                receipt.sequence
                > expected_context._enqueue_sequence
                + (1 if receipt.status == "unavailable" else 0),
            )
        ):
            _fail("hip_resident_enqueue_context_binding_mismatch", "/")
    return receipt


def validate_hip_resident_csr_evaluation_receipt(
    receipt: HipResidentCsrEvaluationReceipt,
    *,
    expected_context: HipResidentCsrExecutionContext | None = None,
) -> HipResidentCsrEvaluationReceipt:
    if type(receipt) is not HipResidentCsrEvaluationReceipt:
        _fail("hip_resident_evaluation_receipt_type_invalid", "/")
    _validate_evaluation_object_types(receipt)
    payload = _evaluation_payload(receipt, include_hash=True)
    _validate_schema(_evaluation_schema_validator(), payload, "hip_resident_evaluation")
    if receipt.receipt_hash != canonical_hash(
        _evaluation_payload(receipt, include_hash=False)
    ):
        _fail("hip_resident_evaluation_receipt_hash_mismatch", "/receipt_hash")
    if _has_runtime_key(payload) or _has_runtime_value(payload):
        _fail("hip_resident_runtime_handle_leak", "/")
    _validate_evaluation_semantics(receipt)
    if receipt.enqueue is not None:
        validate_hip_resident_csr_enqueue_receipt(
            receipt.enqueue, expected_context=expected_context
        )
        if any(
            (
                receipt.enqueue.context_id != receipt.context_id,
                receipt.enqueue.opening_context_receipt_hash
                != receipt.opening_context_receipt_hash,
                receipt.enqueue.operator_id != receipt.operator_id,
                receipt.enqueue.state_hash != receipt.state_hash,
                receipt.enqueue.state_epoch != receipt.state_epoch,
                receipt.enqueue.evidence_scope != receipt.evidence_scope,
            )
        ):
            _fail("hip_resident_evaluation_enqueue_binding_mismatch", "/enqueue")
        expected_execution_id = canonical_hash(
            {
                "context_id": receipt.context_id,
                "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
                "direction_hash": receipt.direction.data_hash,
                "next_sequence": receipt.enqueue.sequence,
            }
        )
        if receipt.execution_id != expected_execution_id:
            _fail("hip_resident_evaluation_execution_id_mismatch", "/execution_id")
    if expected_context is not None:
        if any(
            (
                receipt.context_id != expected_context.context_id,
                receipt.opening_context_receipt_hash
                != expected_context.opening_receipt.context_receipt_hash,
                receipt.operator_id
                != expected_context._parent._operator_view.operator_id,
                receipt.state_hash != expected_context._state.state_hash,
                receipt.state_epoch != expected_context._state.epoch,
                receipt.evidence_scope != expected_context._evidence_scope,
                receipt.work.global_dof_count != expected_context._plan.dof_count,
                receipt.work.csr_nnz != expected_context._plan.nnz,
            )
        ):
            _fail("hip_resident_evaluation_context_binding_mismatch", "/")
        if receipt.parity is not None:
            free_count = int(expected_context._plan.array("free_dofs").size)
            constrained_count = int(
                expected_context._plan.array("constrained_dofs").size
            )
            if any(
                (
                    receipt.parity.residual_free.count != free_count,
                    receipt.parity.jvp_free.count != free_count,
                    receipt.parity.residual_constrained.count != constrained_count,
                    receipt.parity.jvp_constrained.count != constrained_count,
                )
            ):
                _fail("hip_resident_evaluation_partition_mismatch", "/parity")
    return receipt


def validate_hip_resident_csr_evaluation(
    evaluation: HipResidentCsrEvaluation,
    *,
    expected_context: HipResidentCsrExecutionContext | None = None,
) -> HipResidentCsrEvaluation:
    if type(evaluation) is not HipResidentCsrEvaluation:
        _fail("hip_resident_evaluation_type_invalid", "/")
    validate_hip_resident_csr_evaluation_receipt(
        evaluation.receipt, expected_context=expected_context
    )
    if evaluation.enqueue is None:
        if evaluation.receipt.enqueue is not None:
            _fail("hip_resident_evaluation_enqueue_missing", "/enqueue")
    else:
        if type(evaluation.enqueue) is not HipResidentCsrEnqueueReceipt:
            _fail("hip_resident_evaluation_enqueue_type_invalid", "/enqueue")
        validate_hip_resident_csr_enqueue_receipt(
            evaluation.enqueue, expected_context=expected_context
        )
        if evaluation.receipt.enqueue != evaluation.enqueue:
            _fail("hip_resident_evaluation_enqueue_hash_mismatch", "/enqueue")
        expected_execution_id = canonical_hash(
            {
                "context_id": evaluation.receipt.context_id,
                "opening_context_receipt_hash": (
                    evaluation.receipt.opening_context_receipt_hash
                ),
                "direction_hash": evaluation.receipt.direction.data_hash,
                "next_sequence": evaluation.enqueue.sequence,
            }
        )
        if evaluation.receipt.execution_id != expected_execution_id:
            _fail("hip_resident_evaluation_execution_id_mismatch", "/execution_id")
    _validate_array(evaluation.direction, evaluation.receipt.direction, "/direction")
    if evaluation.receipt.status == "unavailable":
        if evaluation.residual is not None or evaluation.jvp is not None:
            _fail("hip_resident_unavailable_output_invalid", "/outputs")
        return evaluation
    if evaluation.residual is None or evaluation.jvp is None:
        _fail("hip_resident_evaluation_output_missing", "/outputs")
    if evaluation.receipt.residual is None or evaluation.receipt.jvp is None:
        _fail("hip_resident_evaluation_descriptor_missing", "/outputs")
    _validate_array(evaluation.residual, evaluation.receipt.residual, "/residual")
    _validate_array(evaluation.jvp, evaluation.receipt.jvp, "/jvp")
    if expected_context is not None:
        cpu_residual = expected_context._plan.residual(
            expected_context._state.displacement_si
        )
        cpu_jvp = expected_context._plan.jvp(evaluation.direction)
        expected_parity = _parity_report(
            expected_context._plan,
            evaluation.residual,
            evaluation.jvp,
            cpu_residual,
            cpu_jvp,
            evaluation.direction,
        )
        if evaluation.receipt.parity != expected_parity:
            _fail("hip_resident_evaluation_parity_mismatch", "/parity")
        expected_status: EvaluationStatus = (
            "verified" if expected_parity.passed else "parity_failed"
        )
        if evaluation.receipt.status != expected_status:
            _fail("hip_resident_evaluation_status_mismatch", "/status")
    return evaluation


def _validate_context_object_types(receipt: HipResidentCsrContextReceipt) -> None:
    expected = (
        (receipt.bindings, HipResidentCsrBindings),
        (receipt.dimensions, HipResidentCsrDimensions),
        (receipt.telemetry, HipResidentCsrTelemetry),
        (receipt.claims, HipResidentCsrClaims),
    )
    if any(type(value) is not kind for value, kind in expected):
        _fail("hip_resident_context_nested_type_invalid", "/")
    if receipt.reason is not None and type(receipt.reason) is not HipResidentCsrReason:
        _fail("hip_resident_context_nested_type_invalid", "/reason")
    if receipt.kernel is not None and type(receipt.kernel) is not HipRtcKernelBinding:
        _fail("hip_resident_context_nested_type_invalid", "/kernel")
    if type(receipt.owned_buffers) is not tuple or any(
        type(value) is not HipResidentCsrBufferView for value in receipt.owned_buffers
    ):
        _fail("hip_resident_context_nested_type_invalid", "/owned_buffers")
    if any(
        type(getattr(receipt, name)) is not kind
        for name, kind in (
            ("status", str),
            ("context_id", str),
            ("evidence_scope", str),
            ("promotion_eligible", bool),
            ("context_receipt_hash", str),
        )
    ) or (
        receipt.actual_backend is not None and type(receipt.actual_backend) is not str
    ):
        _fail("hip_resident_context_scalar_type_invalid", "/")
    bindings = receipt.bindings
    for name in bindings.__dataclass_fields__:
        expected_type = (
            bool
            if name == "state_load_factor_applied"
            else (
                int if name in {"state_epoch", "device_ordinal", "lease_epoch"} else str
            )
        )
        if type(getattr(bindings, name)) is not expected_type:
            _fail("hip_resident_context_scalar_type_invalid", f"/bindings/{name}")
    if any(
        type(getattr(receipt.dimensions, name)) is not int
        for name in receipt.dimensions.__dataclass_fields__
    ):
        _fail("hip_resident_context_scalar_type_invalid", "/dimensions")
    if any(
        type(getattr(receipt.telemetry, name)) is not int
        for name in receipt.telemetry.__dataclass_fields__
    ):
        _fail("hip_resident_context_scalar_type_invalid", "/telemetry")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_resident_context_scalar_type_invalid", "/claims")
    for index, view in enumerate(receipt.owned_buffers):
        if (
            type(view.name) is not str
            or type(view.dtype) is not str
            or type(view.shape) is not tuple
            or any(type(value) is not int for value in view.shape)
            or type(view.byte_length) is not int
            or (view.data_hash is not None and type(view.data_hash) is not str)
            or type(view.access) is not str
            or type(view.initial_transfer) is not str
        ):
            _fail(
                "hip_resident_context_scalar_type_invalid",
                f"/owned_buffers/{index}",
            )


def _validate_evaluation_object_types(
    receipt: HipResidentCsrEvaluationReceipt,
) -> None:
    expected = (
        (receipt.direction, HipResidentCsrArrayDescriptor),
        (receipt.telemetry_delta, HipResidentCsrEvaluationDelta),
        (receipt.work, HipResidentCsrWorkReceipt),
        (receipt.claims, HipResidentCsrEvaluationClaims),
    )
    if any(type(value) is not kind for value, kind in expected):
        _fail("hip_resident_evaluation_nested_type_invalid", "/")
    for value, kind, path in (
        (receipt.reason, HipResidentCsrReason, "/reason"),
        (receipt.residual, HipResidentCsrArrayDescriptor, "/residual"),
        (receipt.jvp, HipResidentCsrArrayDescriptor, "/jvp"),
        (receipt.parity, HipResidentCsrParityReport, "/parity"),
    ):
        if value is not None and type(value) is not kind:
            _fail("hip_resident_evaluation_nested_type_invalid", path)
    if any(
        type(getattr(receipt, name)) is not kind
        for name, kind in (
            ("status", str),
            ("execution_id", str),
            ("context_id", str),
            ("opening_context_receipt_hash", str),
            ("evidence_scope", str),
            ("promotion_eligible", bool),
            ("operator_id", str),
            ("state_hash", str),
            ("state_epoch", int),
            ("receipt_hash", str),
        )
    ):
        _fail("hip_resident_evaluation_scalar_type_invalid", "/")
    if (
        receipt.enqueue is not None
        and type(receipt.enqueue) is not HipResidentCsrEnqueueReceipt
    ):
        _fail("hip_resident_evaluation_scalar_type_invalid", "/enqueue")
    if receipt.actual_backend is not None and type(receipt.actual_backend) is not str:
        _fail("hip_resident_evaluation_scalar_type_invalid", "/actual_backend")
    if any(
        type(getattr(receipt.telemetry_delta, name)) is not int
        for name in receipt.telemetry_delta.__dataclass_fields__
    ):
        _fail("hip_resident_evaluation_scalar_type_invalid", "/telemetry_delta")
    if any(
        type(getattr(receipt.claims, name)) is not bool
        for name in receipt.claims.__dataclass_fields__
    ):
        _fail("hip_resident_evaluation_scalar_type_invalid", "/claims")
    for descriptor, path in (
        (receipt.direction, "/direction"),
        (receipt.residual, "/residual"),
        (receipt.jvp, "/jvp"),
    ):
        if descriptor is None:
            continue
        if (
            type(descriptor.dtype) is not str
            or type(descriptor.shape) is not tuple
            or any(type(value) is not int for value in descriptor.shape)
            or type(descriptor.byte_length) is not int
            or type(descriptor.data_hash) is not str
        ):
            _fail("hip_resident_evaluation_scalar_type_invalid", path)
    if receipt.parity is not None:
        if any(
            type(getattr(receipt.parity, name)) is not bool
            for name in ("zero_direction_exact", "passed")
        ):
            _fail("hip_resident_evaluation_scalar_type_invalid", "/parity")
        for metric in (
            receipt.parity.residual_full,
            receipt.parity.residual_free,
            receipt.parity.residual_constrained,
            receipt.parity.jvp_full,
            receipt.parity.jvp_free,
            receipt.parity.jvp_constrained,
        ):
            if type(metric) is not HipResidentCsrParityMetric or (
                type(metric.count) is not int
                or any(
                    type(getattr(metric, name)) is not float
                    for name in (
                        "max_abs_error",
                        "relative_l2_error",
                        "max_scaled_error",
                    )
                )
                or type(metric.passed) is not bool
            ):
                _fail("hip_resident_evaluation_scalar_type_invalid", "/parity")


def _validate_context_semantics(receipt: HipResidentCsrContextReceipt) -> None:
    telemetry = receipt.telemetry
    dimensions = receipt.dimensions
    vector_bytes = 8 * dimensions.global_dof_count
    if any(
        type(getattr(telemetry, name)) is not int or getattr(telemetry, name) < 0
        for name in telemetry.__dataclass_fields__
    ):
        _fail("hip_resident_context_telemetry_invalid", "/telemetry")
    if any(
        (
            dimensions.global_dof_count <= 0,
            dimensions.free_dof_count < 0,
            dimensions.constrained_dof_count < 0,
            dimensions.free_dof_count + dimensions.constrained_dof_count
            != dimensions.global_dof_count,
            dimensions.csr_nnz <= 0,
            dimensions.borrowed_buffer_count != 4,
            dimensions.owned_buffer_count != 4,
            telemetry.borrowed_device_bytes
            != 12 * dimensions.csr_nnz + 12 * dimensions.global_dof_count + 4,
        )
    ):
        _fail("hip_resident_context_dimensions_invalid", "/dimensions")
    if any(
        (
            receipt.promotion_eligible,
            telemetry.fallback_count != 0,
            telemetry.new_stream_create_count != 0,
            telemetry.consumer_csr_symbolic_h2d_bytes != 0,
            telemetry.consumer_csr_numeric_h2d_bytes != 0,
            telemetry.consumer_load_h2d_bytes != 0,
            telemetry.owned_allocation_attempt_count > 4,
            telemetry.owned_allocation_success_count > 4,
            telemetry.owned_allocation_success_count
            > telemetry.owned_allocation_attempt_count,
            telemetry.owned_deallocation_success_count
            > telemetry.owned_allocation_success_count,
            telemetry.owned_deallocation_success_count
            > telemetry.owned_deallocation_attempt_count,
            telemetry.owned_peak_device_bytes
            != vector_bytes * telemetry.owned_allocation_success_count,
            telemetry.owned_current_device_bytes
            != vector_bytes
            * (
                telemetry.owned_allocation_success_count
                - telemetry.owned_deallocation_success_count
            ),
            telemetry.h2d_operation_success_count
            > telemetry.h2d_operation_attempt_count,
            telemetry.h2d_bytes_attempted
            != telemetry.h2d_operation_attempt_count * vector_bytes,
            telemetry.h2d_bytes_succeeded
            != telemetry.h2d_operation_success_count * vector_bytes,
            telemetry.d2h_operation_success_count
            > telemetry.d2h_operation_attempt_count,
            telemetry.d2h_bytes_attempted
            != telemetry.d2h_operation_attempt_count * vector_bytes,
            telemetry.d2h_bytes_succeeded
            != telemetry.d2h_operation_success_count * vector_bytes,
            telemetry.kernel_launch_success_count
            > telemetry.kernel_launch_attempt_count,
            telemetry.sync_success_count > telemetry.sync_attempt_count,
            telemetry.module_close_success_count > telemetry.module_close_attempt_count,
            telemetry.module_owner_acquired_count not in (0, 1),
            telemetry.module_close_success_count
            > telemetry.module_owner_acquired_count,
            telemetry.module_owner_acquired_count == 0
            and (
                telemetry.module_close_attempt_count != 0
                or telemetry.module_close_success_count != 0
            ),
            receipt.kernel is not None and telemetry.module_owner_acquired_count != 1,
            telemetry.lease_release_success_count
            > telemetry.lease_release_attempt_count,
            telemetry.lease_release_success_count not in (0, 1),
        )
    ):
        _fail("hip_resident_context_telemetry_invalid", "/telemetry")
    expected_views = (
        (
            "state_displacement",
            "read_only",
            "async_h2d_once_then_same_stream_fence",
            receipt.bindings.state_displacement_hash,
        ),
        ("direction_workspace", "read_write", "none", None),
        ("residual_workspace", "write_only", "none", None),
        ("jvp_workspace", "write_only", "none", None),
    )
    views_valid = len(receipt.owned_buffers) == 4 and all(
        view.name == expected[0]
        and view.dtype == "<f8"
        and view.shape == (dimensions.global_dof_count,)
        and view.byte_length == 8 * dimensions.global_dof_count
        and view.access == expected[1]
        and view.initial_transfer == expected[2]
        and view.data_hash == expected[3]
        for view, expected in zip(receipt.owned_buffers, expected_views)
    )
    if receipt.status == "unavailable" and receipt.owned_buffers:
        _fail("hip_resident_context_owned_buffer_invalid", "/owned_buffers")
    if receipt.status != "unavailable" and not views_valid:
        _fail("hip_resident_context_owned_buffer_invalid", "/owned_buffers")
    ready = receipt.status == "context_ready"
    full_live_owner = all(
        (
            telemetry.owned_allocation_success_count == 4,
            telemetry.owned_current_device_bytes == 4 * vector_bytes,
            telemetry.owned_peak_device_bytes == 4 * vector_bytes,
            telemetry.owned_deallocation_attempt_count == 0,
            telemetry.owned_deallocation_success_count == 0,
            telemetry.module_close_attempt_count == 0,
            telemetry.module_close_success_count == 0,
            telemetry.module_owner_acquired_count == 1,
            telemetry.lease_release_attempt_count == 0,
            telemetry.lease_release_success_count == 0,
        )
    )
    if ready:
        if (
            receipt.reason is not None
            or receipt.kernel is None
            or not views_valid
            or not full_live_owner
            or telemetry.h2d_operation_success_count < 1
            or telemetry.h2d_bytes_succeeded < 8 * receipt.dimensions.global_dof_count
            or telemetry.sync_success_count < 1
            or receipt.claims
            != _claims(True, receipt.evidence_scope, lease_active=True)
        ):
            _fail("hip_resident_context_ready_contract_invalid", "/")
    else:
        if receipt.status not in ("context_closed",) and receipt.reason is None:
            _fail("hip_resident_context_reason_missing", "/reason")
        if any(
            (
                receipt.claims.solver_ready,
                receipt.claims.device_resident_krylov_ready,
                receipt.claims.end_to_end_on_complexity,
                receipt.claims.performance_or_speedup,
                receipt.claims.commercial_readiness,
            )
        ):
            _fail("hip_resident_context_claim_invalid", "/claims")
        cleanup_complete = (
            telemetry.owned_current_device_bytes == 0
            and telemetry.owned_deallocation_success_count
            == telemetry.owned_allocation_success_count
            and telemetry.module_close_success_count
            == telemetry.module_owner_acquired_count
            and telemetry.lease_release_success_count == 1
        )
        if receipt.status in ("context_closed", "unavailable") and any(
            (
                receipt.status == "context_closed" and receipt.reason is not None,
                not cleanup_complete,
                receipt.claims
                != _claims(False, receipt.evidence_scope, lease_active=False),
            )
        ):
            _fail("hip_resident_context_cleanup_complete_invalid", "/")
        if receipt.status in ("poisoned", "cleanup_failed") and (
            receipt.claims != _claims(False, receipt.evidence_scope, lease_active=True)
        ):
            _fail("hip_resident_context_cleanup_owner_claim_invalid", "/claims")
        if receipt.status == "poisoned" and not full_live_owner:
            _fail("hip_resident_context_poisoned_state_invalid", "/telemetry")
        if receipt.status == "cleanup_failed":
            close_pending = (
                telemetry.module_close_success_count
                < telemetry.module_owner_acquired_count
            )
            release_pending = telemetry.lease_release_success_count < 1
            if cleanup_complete or any(
                (
                    telemetry.owned_current_device_bytes > 0
                    and (
                        telemetry.module_close_attempt_count != 0
                        or telemetry.module_close_success_count != 0
                        or telemetry.lease_release_attempt_count != 0
                        or telemetry.lease_release_success_count != 0
                    ),
                    telemetry.owned_current_device_bytes == 0
                    and close_pending
                    and (
                        telemetry.lease_release_attempt_count != 0
                        or telemetry.lease_release_success_count != 0
                    ),
                    not (
                        telemetry.owned_current_device_bytes > 0
                        or close_pending
                        or release_pending
                    ),
                )
            ):
                _fail("hip_resident_context_cleanup_state_invalid", "/telemetry")
    if receipt.evidence_scope == "native_hiprtc_composite":
        if (
            receipt.actual_backend
            != (None if receipt.status == "unavailable" else "hip")
            or (ready and not receipt.claims.native_composite_context)
            or (not ready and receipt.claims.native_composite_context)
        ) or any(
            (
                receipt.bindings.residual_kernel_origin != "internally_compiled",
                receipt.bindings.parent_evidence_scope != "native_hiprtc",
                receipt.kernel is None,
                receipt.kernel is not None
                and receipt.kernel.architecture != receipt.bindings.parent_architecture,
                receipt.kernel is not None
                and receipt.kernel.runtime_library_sha256
                != receipt.bindings.parent_runtime_library_sha256,
                receipt.kernel is not None
                and receipt.kernel.runtime_library_discovery_source == "injected",
                receipt.kernel is not None
                and receipt.kernel.hiprtc_library_discovery_source == "injected",
            )
        ):
            _fail("hip_resident_context_evidence_invalid", "/evidence_scope")
    elif receipt.actual_backend != (
        None if receipt.status == "unavailable" else "test_double"
    ):
        _fail("hip_resident_context_evidence_invalid", "/actual_backend")


def _validate_evaluation_semantics(
    receipt: HipResidentCsrEvaluationReceipt,
) -> None:
    delta = receipt.telemetry_delta
    global_dof_count = receipt.work.global_dof_count
    vector_bytes = 8 * global_dof_count
    if any(
        type(getattr(delta, name)) is not int or getattr(delta, name) < 0
        for name in delta.__dataclass_fields__
    ):
        _fail("hip_resident_evaluation_telemetry_invalid", "/telemetry_delta")
    if any(
        (
            receipt.promotion_eligible,
            delta.allocation_count != 0,
            delta.fallback_count != 0,
            delta.h2d_operation_success_count > delta.h2d_operation_attempt_count,
            delta.h2d_bytes_succeeded > delta.h2d_bytes_attempted,
            delta.d2h_operation_success_count > delta.d2h_operation_attempt_count,
            delta.d2h_bytes_succeeded > delta.d2h_bytes_attempted,
            delta.kernel_launch_success_count > delta.kernel_launch_attempt_count,
            delta.sync_success_count > delta.sync_attempt_count,
            receipt.claims.iteration_host_copy_zero,
            receipt.claims.solver_ready,
            receipt.claims.device_resident_krylov_ready,
            receipt.claims.end_to_end_on_complexity,
            receipt.claims.performance_or_speedup,
            receipt.claims.commercial_readiness,
        )
    ):
        _fail("hip_resident_evaluation_contract_invalid", "/")
    if (
        global_dof_count <= 0
        or receipt.work.csr_nnz <= 0
        or receipt.direction.dtype != "<f8"
        or receipt.direction.shape != (global_dof_count,)
        or receipt.direction.byte_length != vector_bytes
    ):
        _fail("hip_resident_evaluation_dimension_invalid", "/direction")
    if any(
        (
            delta.h2d_bytes_attempted
            != delta.h2d_operation_attempt_count * vector_bytes,
            delta.h2d_bytes_succeeded
            != delta.h2d_operation_success_count * vector_bytes,
            delta.d2h_bytes_attempted
            != delta.d2h_operation_attempt_count * vector_bytes,
            delta.d2h_bytes_succeeded
            != delta.d2h_operation_success_count * vector_bytes,
        )
    ):
        _fail("hip_resident_evaluation_transfer_bytes_invalid", "/telemetry_delta")
    if (
        receipt.evidence_scope == "native_hiprtc_composite"
        and receipt.actual_backend != "hip"
    ) or (
        receipt.evidence_scope == "injected_test_double"
        and receipt.actual_backend != "test_double"
    ):
        _fail(
            "hip_resident_evaluation_evidence_invalid",
            "/actual_backend",
        )
    completed = receipt.status in ("verified", "parity_failed")
    if completed:
        if any(
            (
                receipt.reason is not None,
                receipt.enqueue is None,
                receipt.residual is None,
                receipt.jvp is None,
                receipt.parity is None,
                delta.h2d_operation_attempt_count != 1,
                delta.h2d_operation_success_count != 1,
                delta.h2d_bytes_attempted != vector_bytes,
                delta.h2d_bytes_succeeded != vector_bytes,
                delta.d2h_operation_attempt_count != 2,
                delta.d2h_operation_success_count != 2,
                delta.d2h_bytes_attempted != 2 * vector_bytes,
                delta.d2h_bytes_succeeded != 2 * vector_bytes,
                delta.kernel_launch_attempt_count != 1,
                delta.kernel_launch_success_count != 1,
                delta.sync_attempt_count != 1,
                delta.sync_success_count != 1,
                not receipt.claims.assembled_device_csr_consumed,
                not receipt.claims.residual_jvp_completed_after_fence,
                receipt.enqueue is None,
                receipt.enqueue is not None and receipt.enqueue.status != "enqueued",
                receipt.residual is not None
                and (
                    receipt.residual.dtype != "<f8"
                    or receipt.residual.shape != (global_dof_count,)
                    or receipt.residual.byte_length != vector_bytes
                ),
                receipt.jvp is not None
                and (
                    receipt.jvp.dtype != "<f8"
                    or receipt.jvp.shape != (global_dof_count,)
                    or receipt.jvp.byte_length != vector_bytes
                ),
            )
        ):
            _fail("hip_resident_evaluation_completed_contract_invalid", "/")
        parity = receipt.parity
        if parity is None:  # pragma: no cover - guarded above
            _fail("hip_resident_evaluation_parity_missing", "/parity")
        residual_counts = (
            parity.residual_full.count,
            parity.residual_free.count,
            parity.residual_constrained.count,
        )
        jvp_counts = (
            parity.jvp_full.count,
            parity.jvp_free.count,
            parity.jvp_constrained.count,
        )
        if any(
            (
                residual_counts[0] != global_dof_count,
                jvp_counts[0] != global_dof_count,
                residual_counts[1] + residual_counts[2] != global_dof_count,
                jvp_counts[1] + jvp_counts[2] != global_dof_count,
                residual_counts[1:] != jvp_counts[1:],
            )
        ):
            _fail("hip_resident_evaluation_parity_count_invalid", "/parity")
        metrics = (
            parity.residual_full,
            parity.residual_free,
            parity.residual_constrained,
            parity.jvp_full,
            parity.jvp_free,
            parity.jvp_constrained,
        )
        for metric in metrics:
            errors = (
                metric.max_abs_error,
                metric.relative_l2_error,
                metric.max_scaled_error,
            )
            if (
                metric.count < 0
                or not all(np.isfinite(value) and value >= 0.0 for value in errors)
                or (
                    metric.count == 0
                    and (errors != (0.0, 0.0, 0.0) or not metric.passed)
                )
                or (
                    metric.count > 0
                    and metric.passed != (metric.max_scaled_error <= 1.0)
                )
            ):
                _fail("hip_resident_evaluation_parity_metric_invalid", "/parity")
        if parity.passed != (
            parity.zero_direction_exact and all(metric.passed for metric in metrics)
        ):
            _fail("hip_resident_evaluation_parity_aggregate_invalid", "/parity")
        if receipt.status == "verified" and (
            not receipt.parity.passed
            or not receipt.claims.cpu_reference_parity_verified
        ):
            _fail("hip_resident_evaluation_parity_claim_invalid", "/parity")
        if receipt.status == "parity_failed" and (
            receipt.parity.passed or receipt.claims.cpu_reference_parity_verified
        ):
            _fail("hip_resident_evaluation_parity_claim_invalid", "/parity")
    elif (
        receipt.reason is None
        or receipt.residual is not None
        or receipt.jvp is not None
        or receipt.parity is not None
        or receipt.claims.assembled_device_csr_consumed
        or receipt.claims.residual_jvp_completed_after_fence
        or receipt.claims.cpu_reference_parity_verified
    ):
        _fail("hip_resident_evaluation_unavailable_contract_invalid", "/")
    if receipt.enqueue is None:
        if any(
            (
                delta.kernel_launch_attempt_count != 0,
                delta.kernel_launch_success_count != 0,
            )
        ):
            _fail("hip_resident_evaluation_enqueue_delta_invalid", "/enqueue")
    elif any(
        (
            delta.kernel_launch_attempt_count
            != receipt.enqueue.telemetry_delta.kernel_launch_attempt_count,
            delta.kernel_launch_success_count
            != receipt.enqueue.telemetry_delta.kernel_launch_success_count,
        )
    ):
        _fail("hip_resident_evaluation_enqueue_delta_invalid", "/enqueue")
    h2d_state = (
        delta.h2d_operation_attempt_count,
        delta.h2d_operation_success_count,
    )
    d2h_state = (
        delta.d2h_operation_attempt_count,
        delta.d2h_operation_success_count,
    )
    sync_state = (delta.sync_attempt_count, delta.sync_success_count)
    if (
        h2d_state not in ((0, 0), (1, 0), (1, 1))
        or d2h_state not in ((0, 0), (1, 0), (2, 1), (2, 2))
        or sync_state not in ((0, 0), (1, 0), (1, 1))
    ):
        _fail("hip_resident_evaluation_stage_state_invalid", "/telemetry_delta")
    if receipt.enqueue is None:
        if h2d_state not in ((0, 0), (1, 0)) or any(
            (d2h_state != (0, 0), sync_state != (0, 0))
        ):
            _fail("hip_resident_evaluation_stage_order_invalid", "/telemetry_delta")
    elif receipt.enqueue.status == "unavailable":
        if any(
            (
                h2d_state != (1, 1),
                d2h_state != (0, 0),
                sync_state != (0, 0),
            )
        ):
            _fail("hip_resident_evaluation_stage_order_invalid", "/telemetry_delta")
    else:
        if h2d_state != (1, 1):
            _fail("hip_resident_evaluation_stage_order_invalid", "/telemetry_delta")
        if completed:
            if d2h_state != (2, 2) or sync_state != (1, 1):
                _fail(
                    "hip_resident_evaluation_stage_order_invalid",
                    "/telemetry_delta",
                )
        elif (
            d2h_state not in ((1, 0), (2, 1), (2, 2))
            or (d2h_state != (2, 2) and sync_state != (0, 0))
            or (d2h_state == (2, 2) and sync_state == (0, 0))
        ):
            _fail("hip_resident_evaluation_stage_order_invalid", "/telemetry_delta")


def _validate_array(
    array: np.ndarray,
    descriptor: HipResidentCsrArrayDescriptor,
    path: str,
) -> None:
    if (
        type(array) is not np.ndarray
        or array.dtype.str != "<f8"
        or array.shape != descriptor.shape
        or not array.flags.c_contiguous
        or not has_immutable_bytes_backing(array)
        or not np.all(np.isfinite(array))
        or int(array.nbytes) != descriptor.byte_length
        or array_data_hash(array) != descriptor.data_hash
    ):
        _fail("hip_resident_evaluation_array_invalid", path)


@lru_cache(maxsize=1)
def _context_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_resident_csr_context_v1.schema.json")


@lru_cache(maxsize=1)
def _enqueue_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_resident_csr_enqueue_v1.schema.json")


@lru_cache(maxsize=1)
def _evaluation_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_resident_csr_evaluation_v1.schema.json")


def _schema_validator(name: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / name
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HipResidentCsrContextError(
            "hip_resident_schema_unavailable", "/schema", type(exc).__name__
        ) from exc
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_schema(
    validator: Draft202012Validator, payload: dict[str, Any], label: str
) -> None:
    errors = sorted(
        validator.iter_errors(payload), key=lambda error: list(error.absolute_path)
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipResidentCsrContextError(f"{label}_schema_invalid", path, error.message)


def _has_runtime_key(value: Any) -> bool:
    if isinstance(value, dict):
        allowed = {
            "same_runtime_device_stream",
            "same_parent_stream",
            "new_stream_create_count",
        }
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
            if (forbidden and normalized not in allowed) or _has_runtime_key(child):
                return True
        return False
    if isinstance(value, list):
        return any(_has_runtime_key(child) for child in value)
    return False


def _has_runtime_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_runtime_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_runtime_value(child) for child in value)
    if not isinstance(value, str):
        return False
    if _HASH_PATTERN.fullmatch(value) is not None:
        return False
    if (
        _HEX_ADDRESS_PATTERN.search(value) is not None
        or _DECIMAL_POINTER_WRAPPER_PATTERN.search(value) is not None
    ):
        return True
    return (
        re.search(
            r"(?i)\b(?:pointer|address|handle|module|function|stream)\b"
            r"\s*(?:[:=]\s*)[0-9]+",
            value,
        )
        is not None
    )


def _exception_detail(error: Any) -> str:
    if isinstance(error, str):
        text = error
    elif isinstance(error, BaseException):
        try:
            text = str(error)
        except Exception:
            text = type(error).__name__
    else:
        try:
            text = str(error)
        except Exception:
            text = type(error).__name__
    return _bounded_detail(text)


def _bounded_detail(value: str, limit: int = 512) -> str:
    text = value if type(value) is str else type(value).__name__
    text = _HEX_ADDRESS_PATTERN.sub("<redacted-address>", text)
    text = _DECIMAL_POINTER_WRAPPER_PATTERN.sub("<redacted-address>", text)
    text = _LONG_DECIMAL_ADDRESS_PATTERN.sub("<redacted-address>", text)
    text = re.sub(
        r"(?i)\b(?:pointer|address|stream|handle|module|function)\b"
        r"\s*(?:[:=]\s*)?(?:[0-9]+)?",
        "<redacted-runtime>",
        text,
    )
    text = " ".join(text.split())
    return text[:limit] or "unspecified failure"


def _fail(code: str, path: str, message: str | None = None) -> None:
    raise HipResidentCsrContextError(code, path, message or code.replace("_", " "))


__all__ = [
    "HIP_RESIDENT_CSR_CAPABILITY_PROFILE",
    "HIP_RESIDENT_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION",
    "HIP_RESIDENT_CSR_ENQUEUE_RECEIPT_SCHEMA_VERSION",
    "HIP_RESIDENT_CSR_EVALUATION_RECEIPT_SCHEMA_VERSION",
    "HipResidentCsrContextError",
    "HipResidentCsrContextOpenResult",
    "HipResidentCsrContextReceipt",
    "HipResidentCsrEnqueueReceipt",
    "HipResidentCsrEvaluation",
    "HipResidentCsrEvaluationReceipt",
    "HipResidentCsrExecutionContext",
    "open_hip_resident_csr_execution_context",
    "validate_hip_resident_csr_context_receipt",
    "validate_hip_resident_csr_enqueue_receipt",
    "validate_hip_resident_csr_evaluation",
    "validate_hip_resident_csr_evaluation_receipt",
]
