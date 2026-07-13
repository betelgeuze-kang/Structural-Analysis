"""Plan/state-bound HIPRTC canonical-CSR residual/JVP verification context.

The context owns eight child allocations above the existing HIP model-buffer
foundation. It executes one fixed fused device kernel per evaluation and uses
a CPU CSR replay only after a successful download as a parity oracle. It is
not a solver, Newton/Krylov loop, constitutive assembly, or O(N) end-to-end
claim.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
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
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    validate_state_ir,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (
    HIP_RTC_CSR_KERNEL_ABI_VERSION,
    HIP_RTC_CSR_KERNEL_BLOCK_SIZE,
    HIP_RTC_CSR_KERNEL_SYMBOL,
    HipRtcCsrKernel,
    HipRtcError,
    compile_hip_rtc_csr_kernel,
)

RTC_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-rtc-csr-context-receipt.v1"
)
RTC_RESIDUAL_JVP_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-rtc-residual-jvp-receipt.v1"
)
RTC_CSR_CAPABILITY_PROFILE = "phase0_hiprtc_canonical_csr_residual_jvp"
RTC_CSR_WORK_SCOPE = "hiprtc_csr_residual_jvp_kernel_only"

_ZERO_HASH = "sha256:" + ("0" * 64)
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PARITY_TOLERANCE = 1.0e-8
_CHILD_BUFFER_ORDER = (
    "csr_row_ptr",
    "csr_column_indices",
    "csr_values",
    "global_load",
    "state_displacement",
    "direction_workspace",
    "residual_workspace",
    "jvp_workspace",
)
_INITIAL_UPLOAD_NAMES = frozenset(_CHILD_BUFFER_ORDER[:5])

ContextStatus = Literal[
    "context_ready",
    "poisoned",
    "cleanup_failed",
    "context_closed",
    "unavailable",
]
EvaluationStatus = Literal["verified", "parity_failed", "unavailable"]
EvidenceScope = Literal["native_hiprtc", "injected_test_double"]


class HipRtcCsrContextError(RuntimeError):
    """Fail-closed context error with a stable code and JSON path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class HipRtcReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipRtcCsrBindings:
    model_ir_content_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    operator_hash: str
    pattern_hash: str
    partition_hash: str
    load_pattern_id: str
    state_hash: str
    state_epoch: int
    state_displacement_hash: str
    state_role: Literal["committed"]
    load_source: Literal["execution_plan_global_load"]
    state_load_factor_applied: Literal[False]
    host_execution_plan_dense_operator_present: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_ir_content_hash": self.model_ir_content_hash,
            "solver_artifact_hash": self.solver_artifact_hash,
            "execution_plan_hash": self.execution_plan_hash,
            "operator_hash": self.operator_hash,
            "pattern_hash": self.pattern_hash,
            "partition_hash": self.partition_hash,
            "load_pattern_id": self.load_pattern_id,
            "state_hash": self.state_hash,
            "state_epoch": self.state_epoch,
            "state_displacement_hash": self.state_displacement_hash,
            "state_role": self.state_role,
            "load_source": self.load_source,
            "state_load_factor_applied": self.state_load_factor_applied,
            "host_execution_plan_dense_operator_present": (
                self.host_execution_plan_dense_operator_present
            ),
        }


@dataclass(frozen=True, slots=True)
class HipRtcKernelBinding:
    abi_version: int
    kernel_symbol: str
    block_size: int
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
        return {
            "abi_version": self.abi_version,
            "kernel_symbol": self.kernel_symbol,
            "block_size": self.block_size,
            "architecture": self.architecture,
            "source_resource": self.source_resource,
            "source_sha256": self.source_sha256,
            "code_object_sha256": self.code_object_sha256,
            "identity_hash": self.identity_hash,
            "identity_snapshot_hash": self.identity_snapshot_hash,
            "runtime_library_discovery_source": (
                self.runtime_library_discovery_source
            ),
            "runtime_library_sha256": self.runtime_library_sha256,
            "hiprtc_library_discovery_source": (
                self.hiprtc_library_discovery_source
            ),
            "hiprtc_library_sha256": self.hiprtc_library_sha256,
        }


@dataclass(frozen=True, slots=True)
class HipRtcDevice:
    ordinal: int
    name: str
    architecture: str
    runtime_version_raw: int
    driver_version_raw: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "name": self.name,
            "architecture": self.architecture,
            "runtime_version_raw": self.runtime_version_raw,
            "driver_version_raw": self.driver_version_raw,
        }


@dataclass(frozen=True, slots=True)
class HipRtcCsrDimensions:
    global_dof_count: int
    free_dof_count: int
    constrained_dof_count: int
    csr_nnz: int

    def to_dict(self) -> dict[str, int]:
        return {
            "global_dof_count": self.global_dof_count,
            "free_dof_count": self.free_dof_count,
            "constrained_dof_count": self.constrained_dof_count,
            "csr_nnz": self.csr_nnz,
        }


@dataclass(frozen=True, slots=True)
class HipRtcCsrBufferView:
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
class HipRtcCsrTelemetry:
    h2d_bytes: int = 0
    d2h_bytes: int = 0
    h2d_operation_count: int = 0
    d2h_operation_count: int = 0
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

    def to_dict(self) -> dict[str, int]:
        return {
            name: int(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipRtcCsrContextClaims:
    canonical_csr_operator_bound: bool
    committed_state_bound: bool
    residual_jvp_ready: bool
    native_hiprtc_kernel_loaded: bool
    solver_ready: Literal[False] = False
    device_resident_newton_krylov: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {
            name: bool(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipRtcCsrContextReceipt:
    status: ContextStatus
    context_id: str
    actual_backend: str | None
    evidence_scope: EvidenceScope
    promotion_eligible: Literal[False]
    reason: HipRtcReason | None
    base_context_receipt_hash: str
    bindings: HipRtcCsrBindings
    kernel: HipRtcKernelBinding | None
    kernel_ownership: Literal["context"]
    device: HipRtcDevice | None
    dimensions: HipRtcCsrDimensions
    child_buffers: tuple[HipRtcCsrBufferView, ...]
    telemetry: HipRtcCsrTelemetry
    claims: HipRtcCsrContextClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return RTC_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_rtc_csr_context_receipt(self)
        return _context_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipRtcCsrContextOpenResult:
    context: HipRtcCsrExecutionContext | None
    receipt: HipRtcCsrContextReceipt

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


@dataclass(frozen=True, slots=True)
class HipRtcArrayDescriptor:
    dtype: str
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
class HipRtcEvaluationBindings:
    execution_plan_hash: str
    operator_hash: str
    pattern_hash: str
    state_hash: str
    state_epoch: int
    kernel_identity_hash: str
    kernel_identity_snapshot_hash: str
    kernel_runtime_library_discovery_source: str
    kernel_runtime_library_sha256: str
    kernel_hiprtc_library_discovery_source: str
    kernel_hiprtc_library_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name) for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipRtcEvaluationTelemetryDelta:
    h2d_bytes: int
    d2h_bytes: int
    h2d_operation_count: int
    d2h_operation_count: int
    blocking_copy_count: int
    explicit_sync_count: int
    allocation_count: int
    kernel_launch_attempt_count: int
    kernel_launch_count: int
    fallback_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            name: int(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipRtcParityMetric:
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
class HipRtcParityReport:
    residual_full: HipRtcParityMetric
    residual_free: HipRtcParityMetric
    residual_constrained: HipRtcParityMetric
    jvp_full: HipRtcParityMetric
    jvp_free: HipRtcParityMetric
    jvp_constrained: HipRtcParityMetric
    zero_direction_exact: bool | None
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "cpu_canonical_csr_fp64",
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
class HipRtcCsrWorkReceipt:
    global_dof_count: int
    free_dof_count: int
    constrained_dof_count: int
    csr_nnz: int

    def to_dict(self) -> dict[str, Any]:
        g = self.global_dof_count
        z = self.csr_nnz
        return {
            "scope": RTC_CSR_WORK_SCOPE,
            "load_source": "execution_plan_global_load",
            "state_load_factor_applied": False,
            "host_execution_plan_dense_operator_present": True,
            "operation_count_basis": (
                "structural_source_equivalent_not_hardware_counter"
            ),
            "global_dof_count": g,
            "free_dof_count": self.free_dof_count,
            "constrained_dof_count": self.constrained_dof_count,
            "csr_nnz": z,
            "csr_pass_count": 1,
            "multiplication_count": 2 * z,
            "accumulation_count": 2 * z,
            "load_subtraction_count": g,
            "flop_equivalent_count": 4 * z + g,
            "logical_source_bytes": 28 * z + 32 * g,
            "physical_dram_bytes": "not_instrumented",
            "end_to_end_o_n_claim": False,
        }


@dataclass(frozen=True, slots=True)
class HipRtcResidualJvpClaims:
    residual_jvp_executed: bool
    cpu_reference_parity_verified: bool
    solver_ready: Literal[False] = False
    device_resident_newton_krylov: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {
            name: bool(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipRtcResidualJvpReceipt:
    status: EvaluationStatus
    execution_id: str
    context_id: str
    opening_context_receipt_hash: str
    evidence_scope: EvidenceScope
    promotion_eligible: bool
    actual_backend: str | None
    reason: HipRtcReason | None
    bindings: HipRtcEvaluationBindings
    direction: HipRtcArrayDescriptor
    residual: HipRtcArrayDescriptor | None
    jvp: HipRtcArrayDescriptor | None
    telemetry_delta: HipRtcEvaluationTelemetryDelta
    parity: HipRtcParityReport | None
    work: HipRtcCsrWorkReceipt
    claims: HipRtcResidualJvpClaims
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return RTC_RESIDUAL_JVP_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_rtc_residual_jvp_receipt(self)
        return _result_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipRtcResidualJvpEvaluation:
    receipt: HipRtcResidualJvpReceipt
    direction: np.ndarray
    residual: np.ndarray | None
    jvp: np.ndarray | None

    @property
    def result_hash(self) -> str:
        return self.receipt.receipt_hash

    def to_dict(self) -> dict[str, Any]:
        validate_hip_rtc_residual_jvp_evaluation(self)
        return self.receipt.to_dict()


class HipRtcCsrExecutionContext:
    """Owner of one fixed plan/state HIPRTC replay and eight child buffers."""

    def __init__(
        self,
        *,
        buffers: SolverModelBuffers,
        plan: ExecutionPlan,
        committed_state: StateIR,
        base_context: DeviceExecutionContext,
        base_context_receipt_hash: str,
        rtc_kernel: Any,
        kernel_binding: HipRtcKernelBinding,
        evidence_scope: EvidenceScope,
        device: HipRtcDevice | None,
        context_id: str,
        pointers: dict[str, Any],
        child_buffers: tuple[HipRtcCsrBufferView, ...],
        telemetry: HipRtcCsrTelemetry,
        opening_status: ContextStatus = "context_ready",
        failure_reason: HipRtcReason | None = None,
        base_deallocation_observed: int | None = None,
        base_current_bytes_observed: int | None = None,
    ) -> None:
        self._buffers = buffers
        self._plan = plan
        self._state = committed_state
        self._base_context = base_context
        self._base_context_receipt_hash = base_context_receipt_hash
        self._runtime = base_context._runtime
        self._stream = base_context._stream
        self._rtc_kernel = rtc_kernel
        self._kernel_binding = kernel_binding
        self._evidence_scope = evidence_scope
        self._device = device
        self._context_id = context_id
        self._pointers = pointers
        self._child_buffers = child_buffers
        self._telemetry = telemetry
        self._closed = False
        self._poisoned = False
        self._cleanup_failed = opening_status == "cleanup_failed"
        self._failure_reason = failure_reason
        self._base_deallocation_observed = int(
            base_context._telemetry.deallocation_count
            if base_deallocation_observed is None
            else base_deallocation_observed
        )
        self._base_current_bytes_observed = int(
            base_context._telemetry.current_device_payload_bytes
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
            f"HipRtcCsrExecutionContext(context_id={self._context_id!r}, "
            f"status={status!r})"
        )

    def __enter__(self) -> HipRtcCsrExecutionContext:
        self._require_usable()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:
            pass

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def opening_receipt(self) -> HipRtcCsrContextReceipt:
        return self._opening_receipt

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def receipt(self) -> HipRtcCsrContextReceipt:
        if self._cleanup_failed:
            status: ContextStatus = "cleanup_failed"
        elif self._closed:
            status = "context_closed"
        elif self._poisoned:
            status = "poisoned"
        else:
            status = "context_ready"
        return self._build_receipt(status)

    def evaluate_residual_jvp(
        self, direction: Any
    ) -> HipRtcResidualJvpEvaluation:
        """Run exactly one fused launch and verify downloaded outputs on CPU."""

        self._require_usable()
        vector = _direction_vector(direction, self._plan.dof_count)
        direction_descriptor = _array_descriptor(vector)
        dimensions = _dimensions(self._plan)
        work = HipRtcCsrWorkReceipt(**dimensions.to_dict())
        delta = HipRtcEvaluationTelemetryDelta(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        execution_id = _execution_id(
            self._context_id,
            self._opening_receipt.context_receipt_hash,
            direction_descriptor.data_hash,
        )

        try:
            _validate_live_contracts(self)
            _validate_live_kernel(self._rtc_kernel, self._kernel_binding)
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                "hip_rtc_kernel_binding_changed",
                exc,
            )
        try:
            self._runtime.copy_h2d_async(
                self._pointers["direction_workspace"], vector, self._stream
            )
            delta = replace(
                delta,
                h2d_bytes=int(vector.nbytes),
                h2d_operation_count=1,
            )
            self._telemetry = replace(
                self._telemetry,
                h2d_bytes=self._telemetry.h2d_bytes + int(vector.nbytes),
                h2d_operation_count=self._telemetry.h2d_operation_count + 1,
            )
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                "hip_rtc_direction_upload_failed",
                exc,
            )

        delta = replace(delta, kernel_launch_attempt_count=1)
        self._telemetry = replace(
            self._telemetry,
            kernel_launch_attempt_count=(
                self._telemetry.kernel_launch_attempt_count + 1
            ),
        )
        try:
            launch_result = self._rtc_kernel.launch_residual_jvp(
                self._stream,
                self._plan.dof_count,
                self._pointers["csr_row_ptr"],
                self._pointers["csr_column_indices"],
                self._pointers["csr_values"],
                self._pointers["state_displacement"],
                self._pointers["global_load"],
                self._pointers["direction_workspace"],
                self._pointers["residual_workspace"],
                self._pointers["jvp_workspace"],
            )
            if launch_result is not None:
                raise HipRtcCsrContextError(
                    "hip_rtc_kernel_contract_invalid",
                    "/kernel/launch_residual_jvp",
                    "Kernel launch must return None or raise.",
                )
            delta = replace(delta, kernel_launch_count=1)
            self._telemetry = replace(
                self._telemetry,
                kernel_launch_count=self._telemetry.kernel_launch_count + 1,
            )
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                "hip_rtc_kernel_launch_failed",
                exc,
            )

        host_residual = np.empty(self._plan.dof_count, dtype="<f8")
        host_jvp = np.empty(self._plan.dof_count, dtype="<f8")
        try:
            for host, name in (
                (host_residual, "residual_workspace"),
                (host_jvp, "jvp_workspace"),
            ):
                self._runtime.copy_d2h_async(
                    host, self._pointers[name], self._stream
                )
                delta = replace(
                    delta,
                    d2h_bytes=delta.d2h_bytes + int(host.nbytes),
                    d2h_operation_count=delta.d2h_operation_count + 1,
                )
                self._telemetry = replace(
                    self._telemetry,
                    d2h_bytes=self._telemetry.d2h_bytes + int(host.nbytes),
                    d2h_operation_count=(
                        self._telemetry.d2h_operation_count + 1
                    ),
                )
            self._runtime.synchronize(self._stream)
            delta = replace(delta, explicit_sync_count=1)
            self._telemetry = replace(
                self._telemetry,
                explicit_sync_count=self._telemetry.explicit_sync_count + 1,
            )
        except Exception as exc:
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                "hip_rtc_result_download_failed",
                exc,
            )

        residual = immutable_array(host_residual, dtype="<f8")
        jvp = immutable_array(host_jvp, dtype="<f8")
        if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(jvp)):
            return self._failed_evaluation(
                execution_id,
                vector,
                direction_descriptor,
                delta,
                work,
                "hip_rtc_output_nonfinite",
                ValueError("Downloaded residual/JVP contains non-finite values."),
            )
        cpu_residual, cpu_jvp = _cpu_csr_oracle(
            self._plan, self._state.displacement_si, vector
        )
        parity = _parity_report(
            self._plan,
            residual,
            jvp,
            cpu_residual,
            cpu_jvp,
            vector,
        )
        status: EvaluationStatus = (
            "verified" if parity.passed else "parity_failed"
        )
        receipt = _build_result_receipt(
            status=status,
            execution_id=execution_id,
            context=self,
            direction=direction_descriptor,
            residual=_array_descriptor(residual),
            jvp=_array_descriptor(jvp),
            telemetry_delta=delta,
            parity=parity,
            work=work,
            reason=None,
        )
        evaluation = HipRtcResidualJvpEvaluation(
            receipt=receipt,
            direction=vector,
            residual=residual,
            jvp=jvp,
        )
        return validate_hip_rtc_residual_jvp_evaluation(
            evaluation, expected_context=self
        )

    def close(self) -> None:
        """Free children, unload the kernel, then close the base context."""

        if self._closed:
            return
        if not self._base_context.closed:
            try:
                self._runtime.synchronize(self._stream)
            except Exception as exc:
                self._cleanup_failed = True
                self._failure_reason = HipRtcReason(
                    "hip_rtc_cleanup_sync_failed", _bounded_detail(str(exc))
                )
                raise HipRtcCsrContextError(
                    "hip_rtc_cleanup_sync_failed",
                    "/cleanup/synchronize",
                    self._failure_reason.detail,
                ) from exc
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
                if first_error is None:
                    first_error = exc
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
            self._failure_reason = HipRtcReason(
                "hip_rtc_context_cleanup_failed",
                _bounded_detail(str(first_error or "child allocations remain")),
            )
            raise HipRtcCsrContextError(
                "hip_rtc_context_cleanup_failed",
                "/cleanup/child_buffers",
                self._failure_reason.detail,
            )

        try:
            self._rtc_kernel.close()
        except Exception as exc:
            self._cleanup_failed = True
            self._failure_reason = HipRtcReason(
                "hip_rtc_kernel_cleanup_failed", _bounded_detail(str(exc))
            )
            raise HipRtcCsrContextError(
                "hip_rtc_kernel_cleanup_failed",
                "/cleanup/kernel",
                self._failure_reason.detail,
            ) from exc

        try:
            self._base_context.close()
        except Exception as exc:
            self._cleanup_failed = True
            self._failure_reason = HipRtcReason(
                "hip_rtc_foundation_cleanup_failed", _bounded_detail(str(exc))
            )
            raise HipRtcCsrContextError(
                "hip_rtc_foundation_cleanup_failed",
                "/cleanup/base_context",
                self._failure_reason.detail,
            ) from exc
        self._observe_base_cleanup()
        if self._telemetry.current_device_payload_bytes != 0:
            self._cleanup_failed = True
            self._failure_reason = HipRtcReason(
                "hip_rtc_context_cleanup_failed",
                "Cleanup completed with non-zero tracked device payload.",
            )
            raise HipRtcCsrContextError(
                "hip_rtc_context_cleanup_failed",
                "/cleanup/telemetry",
                self._failure_reason.detail,
            )
        self._cleanup_failed = False
        self._failure_reason = None
        self._closed = True

    def _failed_evaluation(
        self,
        execution_id: str,
        direction: np.ndarray,
        direction_descriptor: HipRtcArrayDescriptor,
        delta: HipRtcEvaluationTelemetryDelta,
        work: HipRtcCsrWorkReceipt,
        code: str,
        error: Exception,
    ) -> HipRtcResidualJvpEvaluation:
        self._poisoned = True
        self._failure_reason = HipRtcReason(code, _bounded_detail(str(error)))
        receipt = _build_result_receipt(
            status="unavailable",
            execution_id=execution_id,
            context=self,
            direction=direction_descriptor,
            residual=None,
            jvp=None,
            telemetry_delta=delta,
            parity=None,
            work=work,
            reason=self._failure_reason,
        )
        return HipRtcResidualJvpEvaluation(receipt, direction, None, None)

    def _build_receipt(
        self, status: ContextStatus
    ) -> HipRtcCsrContextReceipt:
        ready = status == "context_ready"
        return _build_context_receipt(
            status=status,
            context_id=self._context_id,
            actual_backend=_actual_backend(self._evidence_scope),
            evidence_scope=self._evidence_scope,
            reason=None if ready or status == "context_closed" else self._failure_reason,
            base_context_receipt_hash=self._base_context_receipt_hash,
            bindings=_bindings(self._buffers, self._plan, self._state),
            kernel=self._kernel_binding,
            device=self._device,
            dimensions=_dimensions(self._plan),
            child_buffers=self._child_buffers,
            telemetry=self._telemetry,
            ready=ready,
        )

    def _observe_base_cleanup(self) -> None:
        base_telemetry = self._base_context._telemetry
        deallocation_delta = (
            int(base_telemetry.deallocation_count)
            - self._base_deallocation_observed
        )
        released_bytes = (
            self._base_current_bytes_observed
            - int(base_telemetry.current_device_payload_bytes)
        )
        if deallocation_delta < 0 or released_bytes < 0:
            raise HipRtcCsrContextError(
                "hip_rtc_context_telemetry_invalid",
                "/cleanup/base_context",
                "Base cleanup telemetry moved backwards.",
            )
        self._telemetry = replace(
            self._telemetry,
            deallocation_count=(
                self._telemetry.deallocation_count + deallocation_delta
            ),
            current_device_payload_bytes=(
                self._telemetry.current_device_payload_bytes - released_bytes
            ),
        )
        self._base_deallocation_observed = int(
            base_telemetry.deallocation_count
        )
        self._base_current_bytes_observed = int(
            base_telemetry.current_device_payload_bytes
        )

    def _require_usable(self) -> None:
        if self._closed:
            raise HipRtcCsrContextError(
                "hip_rtc_csr_context_closed", "/status", "Context is closed."
            )
        if self._cleanup_failed:
            raise HipRtcCsrContextError(
                "hip_rtc_context_cleanup_failed",
                "/status",
                "Context is cleanup-only after a failed close.",
            )
        if self._poisoned:
            raise HipRtcCsrContextError(
                "hip_rtc_csr_context_poisoned",
                "/status",
                "A failed device evaluation poisoned this context.",
            )


def open_hip_rtc_csr_execution_context(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    committed_state: StateIR,
    *,
    device_ordinal: int = 0,
    architecture: str | None = None,
    runtime_library: str | Path | None = None,
    hiprtc_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    runtime: Any | None = None,
    rtc_kernel: Any | None = None,
) -> HipRtcCsrContextOpenResult:
    """Open a fixed-plan/fixed-committed-state no-fallback HIPRTC context.

    An injected ``rtc_kernel`` transfers lifetime ownership to the returned
    context and is always labelled ``injected_test_double``. A kernel compiled
    internally with the native runtime is the only ``native_hiprtc`` path.
    """

    _preflight(
        buffers,
        plan,
        committed_state,
        device_ordinal=device_ordinal,
        architecture=architecture,
        memory_budget_bytes=memory_budget_bytes,
        rtc_kernel=rtc_kernel,
    )
    arrays = _child_arrays(plan, committed_state)
    views = _child_buffer_views(arrays)
    foundation_bytes = sum(row.byte_length for row in buffers.descriptors)
    child_bytes = sum(view.byte_length for view in views)
    if (
        memory_budget_bytes is not None
        and foundation_bytes + child_bytes > memory_budget_bytes
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_memory_budget_exceeded",
            "/memory_budget_bytes",
            f"Required {foundation_bytes + child_bytes} bytes exceeds "
            f"budget {memory_budget_bytes}.",
        )

    evidence_scope: EvidenceScope
    runtime_for_base = runtime
    kernel = rtc_kernel
    if kernel is None:
        if architecture is None:  # guarded by _preflight
            raise AssertionError("architecture preflight was bypassed")
        if runtime is None:
            loaded_runtime = load_hip_native_runtime(runtime_library)
        elif callable(getattr(runtime, "bind", None)):
            loaded_runtime = runtime
        else:
            raise HipRtcCsrContextError(
                "hip_rtc_runtime_invalid",
                "/runtime",
                "Kernel compilation requires a loaded runtime with bind().",
            )
        try:
            kernel = compile_hip_rtc_csr_kernel(
                loaded_runtime,
                architecture,
                hiprtc_library=hiprtc_library,
            )
        except HipRtcError as exc:
            raise HipRtcCsrContextError(
                exc.code, "/kernel/compile", exc.message
            ) from exc
        evidence_scope = (
            "native_hiprtc"
            if runtime is None
            and type(loaded_runtime) is LoadedHipRuntime
            and type(kernel) is HipRtcCsrKernel
            else "injected_test_double"
        )
        runtime_for_base = loaded_runtime
    else:
        evidence_scope = "injected_test_double"
    kernel_binding = _kernel_binding(kernel, architecture)

    base_budget = (
        None
        if memory_budget_bytes is None
        else memory_budget_bytes - child_bytes
    )
    base_open = open_device_execution_context(
        buffers,
        device_ordinal=device_ordinal,
        runtime_library=runtime_library if runtime_for_base is None else None,
        memory_budget_bytes=base_budget,
        runtime=runtime_for_base,
    )
    context_id = _context_id(
        buffers,
        plan,
        committed_state,
        kernel_binding,
        evidence_scope,
        device_ordinal,
    )
    dimensions = _dimensions(plan)
    bindings = _bindings(buffers, plan, committed_state)
    if not base_open.ready or base_open.context is None:
        base_owner = base_open.context
        cleanup_error: Exception | None = None
        if base_owner is not None:
            try:
                base_owner.close()
            except Exception as exc:
                cleanup_error = exc
        try:
            kernel.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
        reason = HipRtcReason(
            "hip_rtc_foundation_not_ready",
            _bounded_detail(
                base_open.receipt.reason.detail
                if base_open.receipt.reason is not None
                else "HIP foundation context is unavailable."
            ),
        )
        if cleanup_error is not None and base_owner is not None:
            cleanup_reason = HipRtcReason(
                "hip_rtc_context_cleanup_failed",
                _bounded_detail(
                    f"{reason.detail}; cleanup incomplete: {cleanup_error}"
                ),
            )
            cleanup_context = HipRtcCsrExecutionContext(
                buffers=buffers,
                plan=plan,
                committed_state=committed_state,
                base_context=base_owner,
                base_context_receipt_hash=(
                    base_open.receipt.context_receipt_hash
                ),
                rtc_kernel=kernel,
                kernel_binding=kernel_binding,
                evidence_scope=evidence_scope,
                device=None,
                context_id=context_id,
                pointers={},
                child_buffers=(),
                telemetry=_telemetry_from_base(base_open.receipt.telemetry),
                opening_status="cleanup_failed",
                failure_reason=cleanup_reason,
                base_deallocation_observed=int(
                    base_open.receipt.telemetry.deallocation_count
                ),
                base_current_bytes_observed=int(
                    base_open.receipt.telemetry.current_device_payload_bytes
                ),
            )
            return HipRtcCsrContextOpenResult(
                cleanup_context, cleanup_context.opening_receipt
            )
        if cleanup_error is not None:
            raise HipRtcCsrContextError(
                "hip_rtc_kernel_cleanup_failed",
                "/open/kernel_cleanup",
                str(cleanup_error),
            ) from cleanup_error
        final_telemetry = (
            _telemetry_from_base(base_owner._telemetry)
            if base_owner is not None
            else _telemetry_from_base(base_open.receipt.telemetry)
        )
        receipt = _build_context_receipt(
            status="unavailable",
            context_id=context_id,
            actual_backend=None,
            evidence_scope=evidence_scope,
            reason=reason,
            base_context_receipt_hash=base_open.receipt.context_receipt_hash,
            bindings=bindings,
            kernel=kernel_binding,
            device=None,
            dimensions=dimensions,
            child_buffers=(),
            telemetry=final_telemetry,
            ready=False,
        )
        return HipRtcCsrContextOpenResult(None, receipt)

    base = base_open.context
    runtime_impl = base._runtime
    device = HipRtcDevice(
        ordinal=device_ordinal,
        name=base._device.name,
        architecture=kernel_binding.architecture,
        runtime_version_raw=base._device.runtime_version_raw,
        driver_version_raw=base._device.driver_version_raw,
    )
    telemetry = _telemetry_from_base(base._telemetry)
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
                array = arrays[view.name][0]
                runtime_impl.copy_h2d_async(pointer, array, base._stream)
                telemetry = replace(
                    telemetry,
                    h2d_bytes=telemetry.h2d_bytes + view.byte_length,
                    h2d_operation_count=telemetry.h2d_operation_count + 1,
                    child_initial_h2d_success_count=(
                        telemetry.child_initial_h2d_success_count + 1
                    ),
                )
        runtime_impl.synchronize(base._stream)
        telemetry = replace(
            telemetry,
            explicit_sync_count=telemetry.explicit_sync_count + 1,
        )
        context = HipRtcCsrExecutionContext(
            buffers=buffers,
            plan=plan,
            committed_state=committed_state,
            base_context=base,
            base_context_receipt_hash=base_open.receipt.context_receipt_hash,
            rtc_kernel=kernel,
            kernel_binding=kernel_binding,
            evidence_scope=evidence_scope,
            device=device,
            context_id=context_id,
            pointers=pointers,
            child_buffers=views,
            telemetry=telemetry,
        )
        return HipRtcCsrContextOpenResult(context, context.opening_receipt)
    except Exception as primary:
        cleanup_error: Exception | None = None
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
                runtime_impl.free(pointer)
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
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
        base_close_succeeded = False
        base_close_failed = False
        if not pointers:
            try:
                kernel.close()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                base.close()
            except Exception as exc:
                base_close_failed = True
                cleanup_error = cleanup_error or exc
            else:
                base_close_succeeded = True
            if base_close_succeeded:
                base_telemetry = base._telemetry
                base_released = (
                    base_open.receipt.telemetry.current_device_payload_bytes
                    - base_telemetry.current_device_payload_bytes
                )
                telemetry = replace(
                    telemetry,
                    deallocation_count=(
                        telemetry.deallocation_count
                        + int(base_telemetry.deallocation_count)
                    ),
                    current_device_payload_bytes=(
                        telemetry.current_device_payload_bytes - base_released
                    ),
                )
        reason = HipRtcReason(
            "hip_rtc_context_open_failed",
            _bounded_detail(str(primary)),
        )
        if cleanup_error is not None or pointers or not base.closed:
            reason = HipRtcReason(
                "hip_rtc_context_cleanup_failed",
                _bounded_detail(f"{primary}; cleanup: {cleanup_error}"),
            )
            cleanup_context = HipRtcCsrExecutionContext(
                buffers=buffers,
                plan=plan,
                committed_state=committed_state,
                base_context=base,
                base_context_receipt_hash=base_open.receipt.context_receipt_hash,
                rtc_kernel=kernel,
                kernel_binding=kernel_binding,
                evidence_scope=evidence_scope,
                device=device,
                context_id=context_id,
                pointers=pointers,
                child_buffers=views,
                telemetry=telemetry,
                opening_status="cleanup_failed",
                failure_reason=reason,
                base_deallocation_observed=(
                    int(base_open.receipt.telemetry.deallocation_count)
                    if base_close_failed
                    else None
                ),
                base_current_bytes_observed=(
                    int(base_open.receipt.telemetry.current_device_payload_bytes)
                    if base_close_failed
                    else None
                ),
            )
            return HipRtcCsrContextOpenResult(
                cleanup_context, cleanup_context.opening_receipt
            )
        receipt = _build_context_receipt(
            status="unavailable",
            context_id=context_id,
            actual_backend=None,
            evidence_scope=evidence_scope,
            reason=reason,
            base_context_receipt_hash=base_open.receipt.context_receipt_hash,
            bindings=bindings,
            kernel=kernel_binding,
            device=None,
            dimensions=dimensions,
            child_buffers=(),
            telemetry=telemetry,
            ready=False,
        )
        return HipRtcCsrContextOpenResult(None, receipt)


def validate_hip_rtc_csr_context_receipt(
    receipt: HipRtcCsrContextReceipt,
    *,
    expected_buffers: SolverModelBuffers | None = None,
    expected_plan: ExecutionPlan | None = None,
    expected_state: StateIR | None = None,
    expected_kernel: Any | None = None,
) -> HipRtcCsrContextReceipt:
    if not isinstance(receipt, HipRtcCsrContextReceipt):
        _fail("hip_rtc_context_receipt_type_invalid", "/", "Expected receipt.")
    payload = _context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema_validator(), payload, "hip_rtc_context")
    if receipt.context_receipt_hash != canonical_hash(
        _context_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_rtc_context_receipt_hash_mismatch",
            "/context_receipt_hash",
            "Context receipt hash is stale.",
        )
    _validate_context_semantics(receipt)
    if expected_buffers is not None:
        validate_solver_model_buffers(expected_buffers)
        if receipt.bindings.model_ir_content_hash != expected_buffers.model_ir_content_hash:
            _fail("hip_rtc_context_buffer_binding_mismatch", "/bindings")
        if receipt.bindings.solver_artifact_hash != expected_buffers.artifact_hash:
            _fail("hip_rtc_context_buffer_binding_mismatch", "/bindings")
    if expected_plan is not None:
        validate_execution_plan(expected_plan, expected_buffers=expected_buffers)
        if any(
            (
                receipt.bindings.model_ir_content_hash
                != expected_plan.model_ir_content_hash,
                receipt.bindings.execution_plan_hash != expected_plan.plan_hash,
                receipt.bindings.operator_hash != expected_plan.operator_hash,
                receipt.bindings.pattern_hash != expected_plan.pattern_hash,
                receipt.bindings.partition_hash != expected_plan.partition_hash,
                receipt.bindings.load_pattern_id != expected_plan.load_pattern_id,
            )
        ):
            _fail("hip_rtc_context_plan_binding_mismatch", "/bindings")
    if expected_state is not None:
        if expected_plan is None:
            raise HipRtcCsrContextError(
                "hip_rtc_context_expected_input_invalid",
                "/expected_plan",
                "expected_state requires expected_plan.",
            )
        validate_state_ir(expected_state, expected_plan=expected_plan)
        if any(
            (
                receipt.bindings.state_hash != expected_state.state_hash,
                receipt.bindings.state_epoch != expected_state.epoch,
                receipt.bindings.state_displacement_hash
                != array_data_hash(expected_state.displacement_si),
                receipt.bindings.state_role != expected_state.role,
            )
        ):
            _fail("hip_rtc_context_state_binding_mismatch", "/bindings")
    if expected_plan is not None and expected_state is not None:
        expected_views = _child_buffer_views(
            _child_arrays(expected_plan, expected_state)
        )
        if receipt.child_buffers and receipt.child_buffers != expected_views:
            _fail("hip_rtc_context_child_binding_mismatch", "/child_buffers")
    if expected_kernel is not None:
        if receipt.kernel != _kernel_binding(expected_kernel, None):
            _fail("hip_rtc_context_kernel_binding_mismatch", "/kernel")
    if _has_runtime_handle_key(payload):
        _fail("hip_rtc_context_runtime_handle_leak", "/")
    return receipt


def validate_hip_rtc_residual_jvp_receipt(
    receipt: HipRtcResidualJvpReceipt,
    *,
    expected_context: HipRtcCsrExecutionContext | None = None,
) -> HipRtcResidualJvpReceipt:
    if not isinstance(receipt, HipRtcResidualJvpReceipt):
        _fail("hip_rtc_result_receipt_type_invalid", "/", "Expected receipt.")
    payload = _result_payload(receipt, include_hash=True)
    _validate_schema(_result_schema_validator(), payload, "hip_rtc_result")
    if receipt.receipt_hash != canonical_hash(
        _result_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_rtc_result_receipt_hash_mismatch",
            "/receipt_hash",
            "Result receipt hash is stale.",
        )
    _validate_result_semantics(receipt)
    if expected_context is not None:
        if receipt.context_id != expected_context.context_id:
            _fail("hip_rtc_result_context_binding_mismatch", "/context_id")
        if (
            receipt.opening_context_receipt_hash
            != expected_context.opening_receipt.context_receipt_hash
        ):
            _fail(
                "hip_rtc_result_context_binding_mismatch",
                "/opening_context_receipt_hash",
            )
        expected_bindings = _evaluation_bindings(expected_context)
        if receipt.bindings != expected_bindings:
            _fail("hip_rtc_result_binding_mismatch", "/bindings")
        if receipt.evidence_scope != expected_context._evidence_scope:
            _fail("hip_rtc_result_evidence_scope_mismatch", "/evidence_scope")
        expected_dimensions = _dimensions(expected_context._plan)
        expected_work = HipRtcCsrWorkReceipt(**expected_dimensions.to_dict())
        if receipt.work != expected_work:
            _fail("hip_rtc_result_work_binding_mismatch", "/work")
    if _has_runtime_handle_key(payload):
        _fail("hip_rtc_result_runtime_handle_leak", "/")
    return receipt


def validate_hip_rtc_residual_jvp_evaluation(
    evaluation: HipRtcResidualJvpEvaluation,
    *,
    expected_context: HipRtcCsrExecutionContext | None = None,
) -> HipRtcResidualJvpEvaluation:
    if not isinstance(evaluation, HipRtcResidualJvpEvaluation):
        _fail("hip_rtc_evaluation_type_invalid", "/", "Expected evaluation.")
    validate_hip_rtc_residual_jvp_receipt(
        evaluation.receipt, expected_context=expected_context
    )
    _validate_immutable_vector(
        evaluation.direction,
        evaluation.receipt.work.global_dof_count,
        "direction",
    )
    if array_data_hash(evaluation.direction) != evaluation.receipt.direction.data_hash:
        _fail("hip_rtc_evaluation_array_hash_mismatch", "/direction")
    if evaluation.receipt.direction != _array_descriptor(evaluation.direction):
        _fail("hip_rtc_evaluation_descriptor_mismatch", "/direction")
    if evaluation.receipt.status == "unavailable":
        if evaluation.residual is not None or evaluation.jvp is not None:
            _fail("hip_rtc_evaluation_unavailable_output_invalid", "/outputs")
        return evaluation
    if evaluation.residual is None or evaluation.jvp is None:
        _fail("hip_rtc_evaluation_output_missing", "/outputs")
    for name, array, descriptor in (
        ("residual", evaluation.residual, evaluation.receipt.residual),
        ("jvp", evaluation.jvp, evaluation.receipt.jvp),
    ):
        if descriptor is None:
            _fail("hip_rtc_evaluation_descriptor_missing", f"/{name}")
        _validate_immutable_vector(
            array, evaluation.receipt.work.global_dof_count, name
        )
        if array_data_hash(array) != descriptor.data_hash:
            _fail("hip_rtc_evaluation_array_hash_mismatch", f"/{name}")
        if descriptor != _array_descriptor(array):
            _fail("hip_rtc_evaluation_descriptor_mismatch", f"/{name}")
    if expected_context is not None:
        cpu_residual, cpu_jvp = _cpu_csr_oracle(
            expected_context._plan,
            expected_context._state.displacement_si,
            evaluation.direction,
        )
        expected_parity = _parity_report(
            expected_context._plan,
            evaluation.residual,
            evaluation.jvp,
            cpu_residual,
            cpu_jvp,
            evaluation.direction,
        )
        if evaluation.receipt.parity != expected_parity:
            _fail("hip_rtc_evaluation_parity_mismatch", "/parity")
        expected_status: EvaluationStatus = (
            "verified" if expected_parity.passed else "parity_failed"
        )
        if evaluation.receipt.status != expected_status:
            _fail("hip_rtc_evaluation_status_mismatch", "/status")
        expected_claims = HipRtcResidualJvpClaims(
            residual_jvp_executed=True,
            cpu_reference_parity_verified=expected_parity.passed,
        )
        if evaluation.receipt.claims != expected_claims:
            _fail("hip_rtc_evaluation_claim_mismatch", "/claims")
        if evaluation.receipt.promotion_eligible:
            _fail("hip_rtc_evaluation_promotion_invalid", "/promotion_eligible")
    return evaluation


def _build_context_receipt(
    *,
    status: ContextStatus,
    context_id: str,
    actual_backend: str | None,
    evidence_scope: EvidenceScope,
    reason: HipRtcReason | None,
    base_context_receipt_hash: str,
    bindings: HipRtcCsrBindings,
    kernel: HipRtcKernelBinding | None,
    device: HipRtcDevice | None,
    dimensions: HipRtcCsrDimensions,
    child_buffers: tuple[HipRtcCsrBufferView, ...],
    telemetry: HipRtcCsrTelemetry,
    ready: bool,
) -> HipRtcCsrContextReceipt:
    draft = HipRtcCsrContextReceipt(
        status=status,
        context_id=context_id,
        actual_backend=actual_backend,
        evidence_scope=evidence_scope,
        promotion_eligible=False,
        reason=reason,
        base_context_receipt_hash=base_context_receipt_hash,
        bindings=bindings,
        kernel=kernel,
        kernel_ownership="context",
        device=device,
        dimensions=dimensions,
        child_buffers=child_buffers,
        telemetry=telemetry,
        claims=HipRtcCsrContextClaims(
            canonical_csr_operator_bound=ready,
            committed_state_bound=ready,
            residual_jvp_ready=ready,
            native_hiprtc_kernel_loaded=(
                ready and evidence_scope == "native_hiprtc"
            ),
        ),
        context_receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        context_receipt_hash=canonical_hash(
            _context_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_rtc_csr_context_receipt(receipt)


def _build_result_receipt(
    *,
    status: EvaluationStatus,
    execution_id: str,
    context: HipRtcCsrExecutionContext,
    direction: HipRtcArrayDescriptor,
    residual: HipRtcArrayDescriptor | None,
    jvp: HipRtcArrayDescriptor | None,
    telemetry_delta: HipRtcEvaluationTelemetryDelta,
    parity: HipRtcParityReport | None,
    work: HipRtcCsrWorkReceipt,
    reason: HipRtcReason | None,
) -> HipRtcResidualJvpReceipt:
    executed = status in ("verified", "parity_failed")
    parity_verified = status == "verified"
    draft = HipRtcResidualJvpReceipt(
        status=status,
        execution_id=execution_id,
        context_id=context.context_id,
        opening_context_receipt_hash=(
            context.opening_receipt.context_receipt_hash
        ),
        evidence_scope=context._evidence_scope,
        promotion_eligible=False,
        actual_backend=(
            _actual_backend(context._evidence_scope) if executed else None
        ),
        reason=reason,
        bindings=_evaluation_bindings(context),
        direction=direction,
        residual=residual,
        jvp=jvp,
        telemetry_delta=telemetry_delta,
        parity=parity,
        work=work,
        claims=HipRtcResidualJvpClaims(
            residual_jvp_executed=executed,
            cpu_reference_parity_verified=parity_verified,
        ),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )
    return validate_hip_rtc_residual_jvp_receipt(
        receipt, expected_context=context
    )


def _context_payload(
    receipt: HipRtcCsrContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": RTC_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "capability_profile": RTC_CSR_CAPABILITY_PROFILE,
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
        "bindings": receipt.bindings.to_dict(),
        "kernel": None if receipt.kernel is None else receipt.kernel.to_dict(),
        "kernel_ownership": receipt.kernel_ownership,
        "device": None if receipt.device is None else receipt.device.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "child_buffers": [view.to_dict() for view in receipt.child_buffers],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _result_payload(
    receipt: HipRtcResidualJvpReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": RTC_RESIDUAL_JVP_RECEIPT_SCHEMA_VERSION,
        "capability_profile": RTC_CSR_CAPABILITY_PROFILE,
        "status": receipt.status,
        "execution_id": receipt.execution_id,
        "context_id": receipt.context_id,
        "opening_context_receipt_hash": receipt.opening_context_receipt_hash,
        "requested_backend": "hip_rtc",
        "actual_backend": receipt.actual_backend,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "direction": receipt.direction.to_dict(),
        "residual": None if receipt.residual is None else receipt.residual.to_dict(),
        "jvp": None if receipt.jvp is None else receipt.jvp.to_dict(),
        "telemetry_delta": receipt.telemetry_delta.to_dict(),
        "parity": None if receipt.parity is None else receipt.parity.to_dict(),
        "work": receipt.work.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_context_semantics(receipt: HipRtcCsrContextReceipt) -> None:
    for value in (
        receipt.base_context_receipt_hash,
        receipt.bindings.model_ir_content_hash,
        receipt.bindings.solver_artifact_hash,
        receipt.bindings.execution_plan_hash,
        receipt.bindings.operator_hash,
        receipt.bindings.pattern_hash,
        receipt.bindings.partition_hash,
        receipt.bindings.state_hash,
        receipt.bindings.state_displacement_hash,
    ):
        _require_hash(value, "/bindings")
    if (
        receipt.bindings.load_source != "execution_plan_global_load"
        or receipt.bindings.state_load_factor_applied
        or not receipt.bindings.host_execution_plan_dense_operator_present
        or receipt.bindings.state_role != "committed"
    ):
        _fail("hip_rtc_context_physics_binding_invalid", "/bindings")
    dims = receipt.dimensions
    if (
        dims.global_dof_count < 1
        or dims.free_dof_count + dims.constrained_dof_count
        != dims.global_dof_count
        or dims.csr_nnz < dims.global_dof_count
    ):
        _fail("hip_rtc_context_dimensions_invalid", "/dimensions")
    telemetry = receipt.telemetry
    if any(value < 0 for value in telemetry.to_dict().values()):
        _fail("hip_rtc_context_telemetry_invalid", "/telemetry")
    if telemetry.fallback_count != 0 or telemetry.blocking_copy_count != 0:
        _fail("hip_rtc_context_fallback_forbidden", "/telemetry")
    if telemetry.child_allocation_success_count > telemetry.child_allocation_attempt_count:
        _fail("hip_rtc_context_telemetry_invalid", "/telemetry")
    if telemetry.child_deallocation_success_count > telemetry.child_deallocation_attempt_count:
        _fail("hip_rtc_context_telemetry_invalid", "/telemetry")
    if telemetry.child_initial_h2d_success_count > telemetry.child_initial_h2d_attempt_count:
        _fail("hip_rtc_context_telemetry_invalid", "/telemetry")
    if telemetry.current_device_payload_bytes > telemetry.peak_device_payload_bytes:
        _fail("hip_rtc_context_telemetry_invalid", "/telemetry")
    if receipt.promotion_eligible:
        _fail("hip_rtc_context_promotion_invalid", "/promotion_eligible")
    if receipt.child_buffers:
        _validate_child_views_semantics(receipt.child_buffers, dims)
    ready = receipt.status == "context_ready"
    if ready:
        if receipt.reason is not None or receipt.actual_backend is None:
            _fail("hip_rtc_context_status_invalid", "/status")
        if receipt.kernel is None or receipt.device is None:
            _fail("hip_rtc_context_binding_missing", "/kernel")
        names = tuple(view.name for view in receipt.child_buffers)
        if names != _CHILD_BUFFER_ORDER:
            _fail("hip_rtc_context_child_order_invalid", "/child_buffers")
        if (
            telemetry.child_allocation_attempt_count != 8
            or telemetry.child_allocation_success_count != 8
            or telemetry.child_initial_h2d_attempt_count != 5
            or telemetry.child_initial_h2d_success_count != 5
        ):
            _fail("hip_rtc_context_initial_transfer_invalid", "/telemetry")
        if not all(
            (
                receipt.claims.canonical_csr_operator_bound,
                receipt.claims.committed_state_bound,
                receipt.claims.residual_jvp_ready,
            )
        ):
            _fail("hip_rtc_context_claim_invalid", "/claims")
    else:
        if any(
            (
                receipt.claims.canonical_csr_operator_bound,
                receipt.claims.committed_state_bound,
                receipt.claims.residual_jvp_ready,
            )
        ):
            _fail("hip_rtc_context_claim_invalid", "/claims")
        if receipt.status in ("poisoned", "cleanup_failed", "unavailable") and receipt.reason is None:
            _fail("hip_rtc_context_reason_missing", "/reason")
    if receipt.evidence_scope == "injected_test_double":
        if receipt.actual_backend not in ("test_double", None):
            _fail("hip_rtc_context_evidence_scope_invalid", "/actual_backend")
        if receipt.claims.native_hiprtc_kernel_loaded:
            _fail("hip_rtc_context_native_claim_invalid", "/claims")
    else:
        if ready and (
            receipt.actual_backend != "hip"
            or not receipt.claims.native_hiprtc_kernel_loaded
            or receipt.kernel is None
            or receipt.device is None
        ):
            _fail("hip_rtc_context_native_claim_invalid", "/claims")
        if receipt.kernel is not None and (
            receipt.kernel.runtime_library_discovery_source == "injected"
            or receipt.kernel.hiprtc_library_discovery_source == "injected"
        ):
            _fail("hip_rtc_context_native_evidence_invalid", "/kernel")
    if receipt.status == "context_closed" and telemetry.current_device_payload_bytes != 0:
        _fail("hip_rtc_context_closed_payload_invalid", "/telemetry")
    if receipt.kernel is not None:
        _validate_kernel_binding(receipt.kernel)


def _validate_child_views_semantics(
    views: tuple[HipRtcCsrBufferView, ...], dims: HipRtcCsrDimensions
) -> None:
    if tuple(view.name for view in views) != _CHILD_BUFFER_ORDER:
        _fail("hip_rtc_context_child_order_invalid", "/child_buffers")
    g = dims.global_dof_count
    z = dims.csr_nnz
    specifications = {
        "csr_row_ptr": ("<i4", (g + 1,), 4 * (g + 1), "read_only", "async_h2d_then_explicit_sync", True),
        "csr_column_indices": ("<i4", (z,), 4 * z, "read_only", "async_h2d_then_explicit_sync", True),
        "csr_values": ("<f8", (z,), 8 * z, "read_only", "async_h2d_then_explicit_sync", True),
        "global_load": ("<f8", (g,), 8 * g, "read_only", "async_h2d_then_explicit_sync", True),
        "state_displacement": ("<f8", (g,), 8 * g, "read_only", "async_h2d_then_explicit_sync", True),
        "direction_workspace": ("<f8", (g,), 8 * g, "read_write", "none", False),
        "residual_workspace": ("<f8", (g,), 8 * g, "write_only", "none", False),
        "jvp_workspace": ("<f8", (g,), 8 * g, "write_only", "none", False),
    }
    for view in views:
        dtype, shape, byte_length, access, transfer, has_hash = specifications[
            view.name
        ]
        if (
            view.dtype != dtype
            or view.shape != shape
            or view.byte_length != byte_length
            or view.access != access
            or view.initial_transfer != transfer
        ):
            _fail(
                "hip_rtc_context_child_descriptor_invalid",
                f"/child_buffers/{view.name}",
            )
        if has_hash:
            _require_hash(view.data_hash, f"/child_buffers/{view.name}/data_hash")
        elif view.data_hash is not None:
            _fail(
                "hip_rtc_context_workspace_hash_invalid",
                f"/child_buffers/{view.name}/data_hash",
            )


def _validate_result_semantics(receipt: HipRtcResidualJvpReceipt) -> None:
    for value in (
        receipt.opening_context_receipt_hash,
        receipt.bindings.execution_plan_hash,
        receipt.bindings.operator_hash,
        receipt.bindings.pattern_hash,
        receipt.bindings.state_hash,
        receipt.bindings.kernel_identity_hash,
        receipt.bindings.kernel_identity_snapshot_hash,
        receipt.bindings.kernel_runtime_library_sha256,
        receipt.bindings.kernel_hiprtc_library_sha256,
        receipt.direction.data_hash,
    ):
        _require_hash(value, "/bindings")
    allowed_sources = {"explicit", "opt_rocm", "system_loader", "injected"}
    if (
        receipt.bindings.kernel_runtime_library_discovery_source
        not in allowed_sources
        or receipt.bindings.kernel_hiprtc_library_discovery_source
        not in allowed_sources
    ):
        _fail("hip_rtc_result_evidence_source_invalid", "/bindings")
    delta = receipt.telemetry_delta
    if any(value < 0 for value in delta.to_dict().values()):
        _fail("hip_rtc_result_telemetry_invalid", "/telemetry_delta")
    if delta.fallback_count != 0 or delta.blocking_copy_count != 0:
        _fail("hip_rtc_result_fallback_forbidden", "/telemetry_delta")
    work = receipt.work
    g = work.global_dof_count
    z = work.csr_nnz
    if (
        work.free_dof_count + work.constrained_dof_count != g
        or g < 1
        or z < g
    ):
        _fail("hip_rtc_result_work_dimensions_invalid", "/work")
    _validate_result_descriptor(receipt.direction, g, "/direction")
    work_payload = work.to_dict()
    if (
        work_payload["multiplication_count"] != 2 * z
        or work_payload["accumulation_count"] != 2 * z
        or work_payload["load_subtraction_count"] != g
        or work_payload["flop_equivalent_count"] != 4 * z + g
        or work_payload["logical_source_bytes"] != 28 * z + 32 * g
        or work_payload["physical_dram_bytes"] != "not_instrumented"
        or work_payload["end_to_end_o_n_claim"]
    ):
        _fail("hip_rtc_result_work_invalid", "/work")
    executed = receipt.status in ("verified", "parity_failed")
    if executed:
        if (
            receipt.reason is not None
            or receipt.actual_backend is None
            or receipt.residual is None
            or receipt.jvp is None
            or receipt.parity is None
        ):
            _fail("hip_rtc_result_status_invalid", "/status")
        _validate_result_descriptor(receipt.residual, g, "/residual")
        _validate_result_descriptor(receipt.jvp, g, "/jvp")
        if (
            delta.h2d_bytes != 8 * g
            or delta.d2h_bytes != 16 * g
            or delta.h2d_operation_count != 1
            or delta.d2h_operation_count != 2
            or delta.explicit_sync_count != 1
            or delta.allocation_count != 0
            or delta.kernel_launch_attempt_count != 1
            or delta.kernel_launch_count != 1
        ):
            _fail("hip_rtc_result_transfer_delta_invalid", "/telemetry_delta")
        if not receipt.claims.residual_jvp_executed:
            _fail("hip_rtc_result_claim_invalid", "/claims")
        expected_status = "verified" if receipt.parity.passed else "parity_failed"
        if receipt.status != expected_status:
            _fail("hip_rtc_result_parity_status_invalid", "/status")
        if receipt.claims.cpu_reference_parity_verified != receipt.parity.passed:
            _fail("hip_rtc_result_claim_invalid", "/claims")
    else:
        if (
            receipt.reason is None
            or receipt.actual_backend is not None
            or receipt.residual is not None
            or receipt.jvp is not None
            or receipt.parity is not None
            or receipt.claims.residual_jvp_executed
            or receipt.claims.cpu_reference_parity_verified
        ):
            _fail("hip_rtc_result_unavailable_invalid", "/status")
    if receipt.promotion_eligible:
        _fail("hip_rtc_result_promotion_invalid", "/promotion_eligible")
    if receipt.evidence_scope == "injected_test_double":
        if receipt.actual_backend not in ("test_double", None) or receipt.promotion_eligible:
            _fail("hip_rtc_result_evidence_scope_invalid", "/evidence_scope")
    else:
        if executed and receipt.actual_backend != "hip":
            _fail("hip_rtc_result_evidence_scope_invalid", "/actual_backend")
        if (
            receipt.bindings.kernel_runtime_library_discovery_source == "injected"
            or receipt.bindings.kernel_hiprtc_library_discovery_source == "injected"
        ):
            _fail("hip_rtc_result_native_evidence_invalid", "/bindings")
    if receipt.parity is not None:
        _validate_parity_report(receipt.parity)


def _validate_parity_report(report: HipRtcParityReport) -> None:
    metrics = (
        report.residual_full,
        report.residual_free,
        report.residual_constrained,
        report.jvp_full,
        report.jvp_free,
        report.jvp_constrained,
    )
    for metric in metrics:
        if metric.count < 0 or any(
            not math.isfinite(value) or value < 0.0
            for value in (
                metric.max_abs_error,
                metric.relative_l2_error,
                metric.max_scaled_error,
            )
        ):
            _fail("hip_rtc_parity_metric_invalid", "/parity")
        expected = (
            metric.max_abs_error <= _PARITY_TOLERANCE
            and metric.relative_l2_error <= _PARITY_TOLERANCE
            and metric.max_scaled_error <= _PARITY_TOLERANCE
        )
        if metric.passed != expected:
            _fail("hip_rtc_parity_metric_status_invalid", "/parity")
    expected_pass = all(metric.passed for metric in metrics)
    if report.zero_direction_exact is False:
        expected_pass = False
    if report.passed != expected_pass:
        _fail("hip_rtc_parity_status_invalid", "/parity/passed")


def _validate_result_descriptor(
    descriptor: HipRtcArrayDescriptor | None, count: int, path: str
) -> None:
    if (
        not isinstance(descriptor, HipRtcArrayDescriptor)
        or descriptor.dtype != "<f8"
        or descriptor.shape != (count,)
        or descriptor.byte_length != 8 * count
    ):
        _fail("hip_rtc_result_descriptor_invalid", path)
    _require_hash(descriptor.data_hash, f"{path}/data_hash")


def _preflight(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    state: StateIR,
    *,
    device_ordinal: int,
    architecture: str | None,
    memory_budget_bytes: int | None,
    rtc_kernel: Any | None,
) -> None:
    try:
        validate_solver_model_buffers(buffers)
        validate_execution_plan(plan, expected_buffers=buffers)
        validate_state_ir(state, expected_plan=plan)
    except Exception as exc:
        raise HipRtcCsrContextError(
            "hip_rtc_binding_invalid", "/bindings", str(exc)
        ) from exc
    if state.role != "committed":
        raise HipRtcCsrContextError(
            "hip_rtc_state_role_invalid",
            "/committed_state/role",
            "Context requires one committed StateIR.",
        )
    if isinstance(device_ordinal, bool) or not isinstance(device_ordinal, int) or device_ordinal < 0:
        raise HipRtcCsrContextError(
            "hip_rtc_device_ordinal_invalid", "/device_ordinal", "Invalid ordinal."
        )
    if memory_budget_bytes is not None and (
        isinstance(memory_budget_bytes, bool)
        or not isinstance(memory_budget_bytes, int)
        or memory_budget_bytes <= 0
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_memory_budget_invalid",
            "/memory_budget_bytes",
            "memory_budget_bytes must be a positive integer.",
        )
    if rtc_kernel is None and architecture is None:
        raise HipRtcCsrContextError(
            "hip_rtc_architecture_required",
            "/architecture",
            "Native HIPRTC compilation requires one plain gfx architecture.",
        )
    if architecture is not None and (
        not isinstance(architecture, str)
        or re.fullmatch(r"gfx[0-9][0-9a-f]{2,15}", architecture) is None
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_architecture_invalid", "/architecture", "Invalid gfx target."
        )
    arrays = _child_arrays(plan, state)
    expected = {
        "csr_row_ptr": ("<i4", (plan.dof_count + 1,)),
        "csr_column_indices": ("<i4", (plan.array("csr_column_indices").size,)),
        "csr_values": ("<f8", (plan.array("global_stiffness_csr_values").size,)),
        "global_load": ("<f8", (plan.dof_count,)),
        "state_displacement": ("<f8", (plan.dof_count,)),
        "direction_workspace": ("<f8", (plan.dof_count,)),
        "residual_workspace": ("<f8", (plan.dof_count,)),
        "jvp_workspace": ("<f8", (plan.dof_count,)),
    }
    for name, (array, _, _) in arrays.items():
        dtype, shape = expected[name]
        if array.dtype.str != dtype or array.shape != shape or not array.flags.c_contiguous:
            raise HipRtcCsrContextError(
                "hip_rtc_child_array_invalid", f"/child_arrays/{name}", "Invalid array."
            )


def _bindings(
    buffers: SolverModelBuffers, plan: ExecutionPlan, state: StateIR
) -> HipRtcCsrBindings:
    return HipRtcCsrBindings(
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_artifact_hash=buffers.artifact_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        state_hash=state.state_hash,
        state_epoch=state.epoch,
        state_displacement_hash=array_data_hash(state.displacement_si),
        state_role="committed",
        load_source="execution_plan_global_load",
        state_load_factor_applied=False,
        host_execution_plan_dense_operator_present=True,
    )


def _dimensions(plan: ExecutionPlan) -> HipRtcCsrDimensions:
    return HipRtcCsrDimensions(
        global_dof_count=plan.dof_count,
        free_dof_count=int(plan.array("free_dofs").size),
        constrained_dof_count=int(plan.array("constrained_dofs").size),
        csr_nnz=int(plan.array("csr_column_indices").size),
    )


def _child_arrays(
    plan: ExecutionPlan, state: StateIR
) -> dict[str, tuple[np.ndarray, str, str]]:
    g = plan.dof_count
    return {
        "csr_row_ptr": (
            plan.array("csr_row_ptr"),
            "read_only",
            "async_h2d_then_explicit_sync",
        ),
        "csr_column_indices": (
            plan.array("csr_column_indices"),
            "read_only",
            "async_h2d_then_explicit_sync",
        ),
        "csr_values": (
            plan.array("global_stiffness_csr_values"),
            "read_only",
            "async_h2d_then_explicit_sync",
        ),
        "global_load": (
            plan.array("global_load"),
            "read_only",
            "async_h2d_then_explicit_sync",
        ),
        "state_displacement": (
            state.displacement_si,
            "read_only",
            "async_h2d_then_explicit_sync",
        ),
        "direction_workspace": (
            immutable_array(np.zeros(g), dtype="<f8"),
            "read_write",
            "none",
        ),
        "residual_workspace": (
            immutable_array(np.zeros(g), dtype="<f8"),
            "write_only",
            "none",
        ),
        "jvp_workspace": (
            immutable_array(np.zeros(g), dtype="<f8"),
            "write_only",
            "none",
        ),
    }


def _child_buffer_views(
    arrays: dict[str, tuple[np.ndarray, str, str]],
) -> tuple[HipRtcCsrBufferView, ...]:
    views = []
    for name in _CHILD_BUFFER_ORDER:
        array, access, transfer = arrays[name]
        views.append(
            HipRtcCsrBufferView(
                name=name,
                dtype=array.dtype.str,
                shape=tuple(int(value) for value in array.shape),
                byte_length=int(array.nbytes),
                data_hash=(
                    array_data_hash(array)
                    if name in _INITIAL_UPLOAD_NAMES
                    else None
                ),
                access=access,
                initial_transfer=transfer,
            )
        )
    return tuple(views)


def _kernel_binding(
    kernel: Any, requested_architecture: str | None
) -> HipRtcKernelBinding:
    identity = getattr(kernel, "identity", None)
    if identity is None or not callable(getattr(identity, "to_dict", None)):
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity",
            "HIPRTC kernel identity is missing.",
        )
    try:
        manifest = identity.to_dict()
    except Exception as exc:
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid", "/kernel/identity", str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity",
            "Kernel identity manifest is invalid.",
        )
    architecture = manifest.get("architecture")
    if not isinstance(architecture, str) or not architecture:
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity/architecture",
            "Kernel architecture is missing.",
        )
    if requested_architecture is not None and architecture != requested_architecture:
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity/architecture",
            "Kernel architecture differs from requested architecture.",
        )
    if manifest.get("kernel_symbol") != HIP_RTC_CSR_KERNEL_SYMBOL:
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity/kernel_symbol",
            "Unexpected fixed kernel symbol.",
        )
    runtime_library = manifest.get("runtime_library")
    hiprtc_library = manifest.get("hiprtc_library")
    if not isinstance(runtime_library, dict) or not isinstance(hiprtc_library, dict):
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_identity_invalid",
            "/kernel/identity/libraries",
            "Kernel native library identities are missing.",
        )
    binding = HipRtcKernelBinding(
        abi_version=int(manifest.get("abi_version", -1)),
        kernel_symbol=str(manifest.get("kernel_symbol", "")),
        block_size=HIP_RTC_CSR_KERNEL_BLOCK_SIZE,
        architecture=architecture,
        source_resource=str(manifest.get("source_resource", "")),
        source_sha256=str(manifest.get("source_sha256", "")),
        code_object_sha256=str(manifest.get("code_object_sha256", "")),
        identity_hash=str(manifest.get("identity_hash", "")),
        identity_snapshot_hash=canonical_hash(manifest),
        runtime_library_discovery_source=str(
            runtime_library.get("discovery_source", "")
        ),
        runtime_library_sha256=str(runtime_library.get("sha256", "")),
        hiprtc_library_discovery_source=str(
            hiprtc_library.get("discovery_source", "")
        ),
        hiprtc_library_sha256=str(hiprtc_library.get("sha256", "")),
    )
    _validate_kernel_binding(binding)
    if not callable(getattr(kernel, "launch_residual_jvp", None)) or not callable(
        getattr(kernel, "close", None)
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_contract_invalid",
            "/kernel",
            "Kernel must expose launch_residual_jvp() and close().",
        )
    return binding


def _validate_kernel_binding(binding: HipRtcKernelBinding) -> None:
    if (
        binding.abi_version != HIP_RTC_CSR_KERNEL_ABI_VERSION
        or binding.kernel_symbol != HIP_RTC_CSR_KERNEL_SYMBOL
        or binding.block_size != HIP_RTC_CSR_KERNEL_BLOCK_SIZE
        or not binding.source_resource.endswith(".hip.cpp")
    ):
        _fail("hip_rtc_kernel_binding_invalid", "/kernel")
    for value in (
        binding.source_sha256,
        binding.code_object_sha256,
        binding.identity_hash,
        binding.identity_snapshot_hash,
        binding.runtime_library_sha256,
        binding.hiprtc_library_sha256,
    ):
        _require_hash(value, "/kernel")
    allowed_sources = {"explicit", "opt_rocm", "system_loader", "injected"}
    if (
        binding.runtime_library_discovery_source not in allowed_sources
        or binding.hiprtc_library_discovery_source not in allowed_sources
    ):
        _fail("hip_rtc_kernel_binding_invalid", "/kernel/libraries")


def _validate_live_kernel(kernel: Any, expected: HipRtcKernelBinding) -> None:
    current = _kernel_binding(kernel, expected.architecture)
    if current != expected:
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_binding_changed",
            "/kernel/identity",
            "Live HIPRTC kernel identity differs from its opening snapshot.",
        )
    if bool(getattr(kernel, "closed", False)):
        raise HipRtcCsrContextError(
            "hip_rtc_kernel_closed", "/kernel", "Live HIPRTC kernel is closed."
        )


def _validate_native_open_links(
    base: DeviceExecutionContext,
    kernel: Any,
    binding: HipRtcKernelBinding,
) -> None:
    if type(kernel) is not HipRtcCsrKernel:
        raise HipRtcCsrContextError(
            "hip_rtc_native_evidence_invalid",
            "/kernel",
            "Native evidence requires the exact package HipRtcCsrKernel type.",
        )
    capability = base._capability_receipt
    if (
        capability.status != "ready"
        or capability.library.sha256 != binding.runtime_library_sha256
        or capability.device.selected_ordinal != base._device.ordinal
        or binding.runtime_library_discovery_source == "injected"
        or binding.hiprtc_library_discovery_source == "injected"
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_native_evidence_invalid",
            "/native_evidence",
            "Runtime, device, and compiled kernel identities are not linked.",
        )


def _validate_live_contracts(context: HipRtcCsrExecutionContext) -> None:
    try:
        validate_solver_model_buffers(context._buffers)
        validate_execution_plan(
            context._plan, expected_buffers=context._buffers
        )
        validate_state_ir(context._state, expected_plan=context._plan)
    except Exception as exc:
        raise HipRtcCsrContextError(
            "hip_rtc_live_binding_invalid", "/bindings", str(exc)
        ) from exc
    if context._state.role != "committed":
        raise HipRtcCsrContextError(
            "hip_rtc_live_binding_invalid",
            "/bindings/state_role",
            "Live state is not committed.",
        )
    if _bindings(context._buffers, context._plan, context._state) != (
        context.opening_receipt.bindings
    ):
        raise HipRtcCsrContextError(
            "hip_rtc_live_binding_changed",
            "/bindings",
            "Live buffers/plan/state differ from the opening snapshot.",
        )
    expected_views = _child_buffer_views(
        _child_arrays(context._plan, context._state)
    )
    if context._child_buffers != expected_views:
        raise HipRtcCsrContextError(
            "hip_rtc_live_binding_changed",
            "/child_buffers",
            "Child buffer descriptors differ from the opening snapshot.",
        )


def _evaluation_bindings(
    context: HipRtcCsrExecutionContext,
) -> HipRtcEvaluationBindings:
    return HipRtcEvaluationBindings(
        execution_plan_hash=context._plan.plan_hash,
        operator_hash=context._plan.operator_hash,
        pattern_hash=context._plan.pattern_hash,
        state_hash=context._state.state_hash,
        state_epoch=context._state.epoch,
        kernel_identity_hash=context._kernel_binding.identity_hash,
        kernel_identity_snapshot_hash=(
            context._kernel_binding.identity_snapshot_hash
        ),
        kernel_runtime_library_discovery_source=(
            context._kernel_binding.runtime_library_discovery_source
        ),
        kernel_runtime_library_sha256=(
            context._kernel_binding.runtime_library_sha256
        ),
        kernel_hiprtc_library_discovery_source=(
            context._kernel_binding.hiprtc_library_discovery_source
        ),
        kernel_hiprtc_library_sha256=(
            context._kernel_binding.hiprtc_library_sha256
        ),
    )


def _telemetry_from_base(value: Any) -> HipRtcCsrTelemetry:
    return HipRtcCsrTelemetry(
        h2d_bytes=int(value.h2d_bytes),
        d2h_bytes=int(value.d2h_bytes),
        h2d_operation_count=int(value.h2d_operation_count),
        d2h_operation_count=int(value.d2h_operation_count),
        blocking_copy_count=int(value.blocking_copy_count),
        explicit_sync_count=int(value.explicit_sync_count),
        allocation_count=int(value.allocation_count),
        deallocation_count=int(value.deallocation_count),
        current_device_payload_bytes=int(value.current_device_payload_bytes),
        peak_device_payload_bytes=int(value.peak_device_payload_bytes),
        kernel_launch_count=int(value.kernel_launch_count),
        fallback_count=int(value.fallback_count),
    )


def _cpu_csr_oracle(
    plan: ExecutionPlan, state: np.ndarray, direction: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    values = plan.array("global_stiffness_csr_values")
    load = plan.array("global_load")
    residual = np.empty(plan.dof_count, dtype="<f8")
    jvp = np.empty(plan.dof_count, dtype="<f8")
    for row in range(plan.dof_count):
        state_sum = 0.0
        direction_sum = 0.0
        for entry in range(int(row_ptr[row]), int(row_ptr[row + 1])):
            column = int(columns[entry])
            coefficient = float(values[entry])
            state_sum += coefficient * float(state[column])
            direction_sum += coefficient * float(direction[column])
        residual[row] = state_sum - float(load[row])
        jvp[row] = direction_sum
    return (
        immutable_array(residual, dtype="<f8"),
        immutable_array(jvp, dtype="<f8"),
    )


def _parity_report(
    plan: ExecutionPlan,
    residual: np.ndarray,
    jvp: np.ndarray,
    cpu_residual: np.ndarray,
    cpu_jvp: np.ndarray,
    direction: np.ndarray,
) -> HipRtcParityReport:
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    metrics = (
        _parity_metric(residual, cpu_residual),
        _parity_metric(residual[free], cpu_residual[free]),
        _parity_metric(residual[constrained], cpu_residual[constrained]),
        _parity_metric(jvp, cpu_jvp),
        _parity_metric(jvp[free], cpu_jvp[free]),
        _parity_metric(jvp[constrained], cpu_jvp[constrained]),
    )
    zero_exact = None
    if np.count_nonzero(direction) == 0:
        zero_exact = bool(
            np.array_equal(jvp, np.zeros_like(jvp))
            and np.array_equal(cpu_jvp, np.zeros_like(cpu_jvp))
        )
    passed = all(metric.passed for metric in metrics)
    if zero_exact is False:
        passed = False
    return HipRtcParityReport(*metrics, zero_exact, passed)


def _parity_metric(
    observed: np.ndarray, reference: np.ndarray
) -> HipRtcParityMetric:
    count = int(observed.size)
    if count == 0:
        return HipRtcParityMetric(0, 0.0, 0.0, 0.0, True)
    difference = np.asarray(observed - reference, dtype="<f8")
    max_abs = float(np.max(np.abs(difference), initial=0.0))
    denominator = float(np.linalg.norm(reference))
    relative_l2 = float(np.linalg.norm(difference)) / max(denominator, 1.0)
    scaled = float(
        np.max(
            np.abs(difference) / np.maximum(np.abs(reference), 1.0),
            initial=0.0,
        )
    )
    finite = all(math.isfinite(value) for value in (max_abs, relative_l2, scaled))
    passed = finite and max(max_abs, relative_l2, scaled) <= _PARITY_TOLERANCE
    return HipRtcParityMetric(count, max_abs, relative_l2, scaled, passed)


def _direction_vector(value: Any, dof_count: int) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except Exception as exc:
        raise HipRtcCsrContextError(
            "hip_rtc_direction_invalid", "/direction", str(exc)
        ) from exc
    if array.shape != (dof_count,) or not np.all(np.isfinite(array)):
        raise HipRtcCsrContextError(
            "hip_rtc_direction_invalid",
            "/direction",
            f"Direction must contain {dof_count} finite FP64 values.",
        )
    return immutable_array(array, dtype="<f8")


def _array_descriptor(array: np.ndarray) -> HipRtcArrayDescriptor:
    return HipRtcArrayDescriptor(
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
    )


def _validate_immutable_vector(array: Any, count: int, name: str) -> None:
    if (
        not isinstance(array, np.ndarray)
        or array.dtype.str != "<f8"
        or array.shape != (count,)
        or not array.flags.c_contiguous
        or array.flags.writeable
        or not has_immutable_bytes_backing(array)
        or not np.all(np.isfinite(array))
    ):
        _fail("hip_rtc_evaluation_array_invalid", f"/{name}")


def _context_id(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    state: StateIR,
    kernel: HipRtcKernelBinding,
    evidence_scope: EvidenceScope,
    ordinal: int,
) -> str:
    digest = canonical_hash(
        {
            "solver_artifact_hash": buffers.artifact_hash,
            "execution_plan_hash": plan.plan_hash,
            "state_hash": state.state_hash,
            "kernel_identity_snapshot_hash": kernel.identity_snapshot_hash,
            "evidence_scope": evidence_scope,
            "device_ordinal": ordinal,
        }
    )
    return f"HipRtcCsrContext:{digest.removeprefix('sha256:')[:24]}"


def _execution_id(
    context_id: str, opening_receipt_hash: str, direction_hash: str
) -> str:
    digest = canonical_hash(
        {
            "context_id": context_id,
            "opening_context_receipt_hash": opening_receipt_hash,
            "direction_hash": direction_hash,
        }
    )
    return f"HipRtcResidualJvp:{digest.removeprefix('sha256:')[:24]}"


def _actual_backend(evidence_scope: EvidenceScope) -> str:
    return "hip" if evidence_scope == "native_hiprtc" else "test_double"


def _view_by_name(
    views: tuple[HipRtcCsrBufferView, ...], name: str
) -> HipRtcCsrBufferView:
    for view in views:
        if view.name == name:
            return view
    raise HipRtcCsrContextError(
        "hip_rtc_child_view_missing", f"/child_buffers/{name}", "Missing view."
    )


def _bounded_detail(value: str) -> str:
    normalized = " ".join(str(value).split()) or "HIPRTC context unavailable."
    return normalized[:512]


def _require_hash(value: Any, path: str) -> None:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hip_rtc_hash_invalid", path)


def _has_runtime_handle_key(value: Any) -> bool:
    forbidden = ("pointer", "address", "stream", "handle")
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in forbidden)
            or _has_runtime_handle_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_has_runtime_handle_key(child) for child in value)
    return False


def _fail(code: str, path: str, message: str = "Receipt is invalid.") -> None:
    raise HipRtcCsrContextError(code, path, message)


def _validate_schema(
    validator: Draft202012Validator, payload: dict[str, Any], prefix: str
) -> None:
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(f"{prefix}_schema_invalid", path, error.message)


@lru_cache(maxsize=1)
def _context_schema_validator() -> Draft202012Validator:
    return _schema_validator("rtc_csr_context_receipt_v1.schema.json")


@lru_cache(maxsize=1)
def _result_schema_validator() -> Draft202012Validator:
    return _schema_validator("rtc_residual_jvp_receipt_v1.schema.json")


def _schema_validator(name: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "RTC_CSR_CAPABILITY_PROFILE",
    "RTC_CSR_CONTEXT_RECEIPT_SCHEMA_VERSION",
    "RTC_RESIDUAL_JVP_RECEIPT_SCHEMA_VERSION",
    "HipRtcCsrContextError",
    "HipRtcCsrContextOpenResult",
    "HipRtcCsrContextReceipt",
    "HipRtcCsrExecutionContext",
    "HipRtcResidualJvpEvaluation",
    "HipRtcResidualJvpReceipt",
    "open_hip_rtc_csr_execution_context",
    "validate_hip_rtc_csr_context_receipt",
    "validate_hip_rtc_residual_jvp_evaluation",
    "validate_hip_rtc_residual_jvp_receipt",
]
