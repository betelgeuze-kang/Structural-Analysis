"""Plan-bound HIP canonical-CSR residual/JVP verification replay.

This module deliberately sits *above* :mod:`.context`.  The v1
``DeviceExecutionContext`` remains a model-buffer-only foundation whose
receipt is not changed or promoted.  This v1 operator layer owns eight
additional allocations, binds one immutable ``ExecutionPlan`` and one
committed ``StateIR``, and can execute exactly one fused ``R = K u - F`` /
``Jv = K v`` replay per evaluation.

The replay is not a linear solver, Newton method, Krylov method, constitutive
assembly, or commercial-readiness receipt.  CPU arithmetic appears only in
the separately-invoked parity verifier and is never a fallback path.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator
import numpy as np

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

from .context import (
    DeviceExecutionContext,
    HipBufferBinding,
    HipContextError,
    HipContextReason,
    HipDeviceContextIdentity,
    open_device_execution_context,
)
from .kernel_artifact import (
    HipCsrKernelArtifactReceipt,
    _is_loader_owned_hip_csr_kernel,
    validate_hip_csr_kernel_artifact_receipt,
)


HIP_OPERATOR_CONTEXT_SCHEMA_VERSION = (
    "structural-analysis-hip-operator-context.v1"
)
HIP_RESIDUAL_JVP_RESULT_SCHEMA_VERSION = (
    "structural-analysis-hip-residual-jvp-result.v1"
)
HIP_RESIDUAL_JVP_PARITY_SCHEMA_VERSION = (
    "structural-analysis-hip-residual-jvp-parity.v1"
)
HIP_OPERATOR_CONTEXT_CAPABILITY_PROFILE = (
    "phase0_hip_csr_residual_jvp_operator_context"
)
HIP_CSR_KERNEL_ARTIFACT_SCHEMA_VERSION = (
    "structural-analysis-hip-csr-kernel-artifact.v1"
)
HIP_CSR_KERNEL_ENTRYPOINT = "engine_v2_hip_csr_launch"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_HASH = "sha256:" + ("0" * 64)
_VIEW_NAMES = (
    "csr_row_ptr",
    "csr_col_ind",
    "csr_values",
    "load_vector",
    "committed_displacement",
    "direction",
    "residual_output",
    "jvp_output",
)
_INITIAL_UPLOAD_NAMES = frozenset(
    {
        "csr_row_ptr",
        "csr_col_ind",
        "csr_values",
        "load_vector",
        "committed_displacement",
    }
)
_RELATIVE_ERROR_DENOMINATOR_FLOOR = 1.0e-300


class HipOperatorContextError(RuntimeError):
    """Fail-closed operator replay error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


class HipResidualJvpKernelProtocol(Protocol):
    """Duck-typed kernel artifact boundary owned by the native loader."""

    @property
    def artifact_receipt(self) -> Any: ...

    def launch_residual_jvp(
        self,
        *,
        row_count: int,
        nnz_count: int,
        row_ptr: Any,
        column_indices: Any,
        values: Any,
        load: Any,
        state: Any,
        direction: Any,
        residual_out: Any,
        jvp_out: Any,
        stream: Any,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class HipExecutionPlanBinding:
    schema_version: str
    model_ir_content_hash: str
    plan_hash: str
    operator_hash: str
    pattern_hash: str
    partition_hash: str
    dof_count: int
    free_dof_count: int
    nnz: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_ir_content_hash": self.model_ir_content_hash,
            "plan_hash": self.plan_hash,
            "operator_hash": self.operator_hash,
            "pattern_hash": self.pattern_hash,
            "partition_hash": self.partition_hash,
            "dof_count": self.dof_count,
            "free_dof_count": self.free_dof_count,
            "nnz": self.nnz,
        }


@dataclass(frozen=True, slots=True)
class HipCommittedStateBinding:
    schema_version: str
    role: Literal["committed"]
    state_hash: str
    displacement_hash: str
    epoch: int
    execution_plan_hash: str
    operator_hash: str
    dof_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "state_hash": self.state_hash,
            "displacement_hash": self.displacement_hash,
            "epoch": self.epoch,
            "execution_plan_hash": self.execution_plan_hash,
            "operator_hash": self.operator_hash,
            "dof_count": self.dof_count,
        }


@dataclass(frozen=True, slots=True)
class HipKernelArtifactBinding:
    schema_version: str
    artifact_receipt_hash: str
    artifact_hash: str
    source_hash: str
    library_hash: str
    abi_hash: str
    build_target_hash: str
    entrypoint: str
    abi_version: int
    block_size: int
    targets: tuple[str, ...]
    flags: tuple[str, ...]
    artifact_kind: Literal["native_hip", "test_double"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_receipt_hash": self.artifact_receipt_hash,
            "artifact_hash": self.artifact_hash,
            "source_hash": self.source_hash,
            "library_hash": self.library_hash,
            "abi_hash": self.abi_hash,
            "build_target_hash": self.build_target_hash,
            "entrypoint": self.entrypoint,
            "abi_version": self.abi_version,
            "block_size": self.block_size,
            "targets": list(self.targets),
            "flags": list(self.flags),
            "artifact_kind": self.artifact_kind,
        }


@dataclass(frozen=True, slots=True)
class HipOperatorDeviceView:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str | None
    memory_space: Literal["hip_device"]
    device_ordinal: int
    access: Literal["read_only", "read_write", "write_only"]
    initial_transfer: Literal["async_h2d_then_explicit_sync", "none"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "memory_space": self.memory_space,
            "device_ordinal": self.device_ordinal,
            "access": self.access,
            "initial_transfer": self.initial_transfer,
        }


@dataclass(frozen=True, slots=True)
class HipOperatorTelemetry:
    """Exact attempt/success counters for the eight operator allocations only."""

    allocation_attempt_count: int = 0
    allocation_success_count: int = 0
    h2d_operation_attempt_count: int = 0
    h2d_operation_success_count: int = 0
    h2d_bytes_attempted: int = 0
    h2d_bytes_succeeded: int = 0
    d2h_operation_attempt_count: int = 0
    d2h_operation_success_count: int = 0
    d2h_bytes_attempted: int = 0
    d2h_bytes_succeeded: int = 0
    explicit_sync_attempt_count: int = 0
    explicit_sync_success_count: int = 0
    kernel_launch_attempt_count: int = 0
    kernel_launch_success_count: int = 0
    deallocation_attempt_count: int = 0
    deallocation_success_count: int = 0
    current_device_payload_bytes: int = 0
    peak_device_payload_bytes: int = 0
    fallback_count: int = 0

    def to_dict(self) -> dict[str, int]:
        # Attempted and successful byte counters are both serialized and
        # hash-bound so partial enqueue failures remain auditable offline.
        return {
            "allocation_attempt_count": self.allocation_attempt_count,
            "allocation_success_count": self.allocation_success_count,
            "h2d_operation_attempt_count": self.h2d_operation_attempt_count,
            "h2d_operation_success_count": self.h2d_operation_success_count,
            "h2d_bytes_attempted": self.h2d_bytes_attempted,
            "h2d_bytes_succeeded": self.h2d_bytes_succeeded,
            "h2d_bytes": self.h2d_bytes_succeeded,
            "d2h_operation_attempt_count": self.d2h_operation_attempt_count,
            "d2h_operation_success_count": self.d2h_operation_success_count,
            "d2h_bytes_attempted": self.d2h_bytes_attempted,
            "d2h_bytes_succeeded": self.d2h_bytes_succeeded,
            "d2h_bytes": self.d2h_bytes_succeeded,
            "explicit_sync_attempt_count": self.explicit_sync_attempt_count,
            "explicit_sync_success_count": self.explicit_sync_success_count,
            "kernel_launch_attempt_count": self.kernel_launch_attempt_count,
            "kernel_launch_success_count": self.kernel_launch_success_count,
            "deallocation_attempt_count": self.deallocation_attempt_count,
            "deallocation_success_count": self.deallocation_success_count,
            "blocking_copy_count": 0,
            "current_device_payload_bytes": self.current_device_payload_bytes,
            "peak_device_payload_bytes": self.peak_device_payload_bytes,
            "fallback_count": self.fallback_count,
        }


@dataclass(frozen=True, slots=True)
class HipOperatorClaims:
    model_buffers_foundation_bound: bool
    canonical_csr_operator_bound: bool
    committed_state_bound: bool
    residual_jvp_ready: bool
    native_hip_kernel_execution_proven: Literal[False] = False
    device_constitutive_assembly_proven: Literal[False] = False
    solver_ready: Literal[False] = False
    newton_ready: Literal[False] = False
    krylov_ready: Literal[False] = False
    cpu_hip_global_parity_proven: Literal[False] = False
    exact_foundation_cleanup_proven: Literal[False] = False
    commercial_readiness: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {
            field: bool(getattr(self, field))
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipOperatorContextReceipt:
    status: Literal[
        "context_ready",
        "context_closed",
        "unavailable",
        "poisoned",
        "cleanup_failed",
    ]
    context_id: str
    actual_backend: Literal["hip_native", "test_double"] | None
    execution_evidence_kind: Literal["native_hip", "test_double"]
    reason: HipContextReason | None
    capability_receipt_hash: str
    foundation_context_receipt_hash: str
    solver_model_buffers: HipBufferBinding
    execution_plan: HipExecutionPlanBinding
    committed_state: HipCommittedStateBinding
    kernel_artifact: HipKernelArtifactBinding
    device: HipDeviceContextIdentity | None
    device_views: tuple[HipOperatorDeviceView, ...]
    telemetry: HipOperatorTelemetry
    claims: HipOperatorClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_OPERATOR_CONTEXT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_operator_context_receipt(self)
        return _operator_context_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipOperatorContextOpenResult:
    context: HipOperatorExecutionContext | None
    receipt: HipOperatorContextReceipt
    cleanup_owner: DeviceExecutionContext | None = None

    @property
    def ready(self) -> bool:
        return (
            self.context is not None
            and self.cleanup_owner is None
            and self.receipt.status == "context_ready"
        )


@dataclass(frozen=True, slots=True)
class HipDirectionBinding:
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
class HipOutputBinding:
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
class HipResidualJvpTransferDelta:
    h2d_operation_attempt_count: int
    h2d_operation_success_count: int
    h2d_bytes_attempted: int
    h2d_bytes_succeeded: int
    d2h_operation_attempt_count: int
    d2h_operation_success_count: int
    d2h_bytes_attempted: int
    d2h_bytes_succeeded: int
    explicit_sync_attempt_count: int
    explicit_sync_success_count: int
    kernel_launch_attempt_count: int
    kernel_launch_success_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            field: int(getattr(self, field))
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipResidualJvpEvaluation:
    residual_sign: Literal["internal_minus_external"]
    jvp_semantics: Literal["linear_preassembled_K_times_v"]
    load_factor_semantics: Literal["plan_global_load_unscaled_phase0"]
    fused_launch: Literal[True]
    launch_count: Literal[1]
    dof_count: int
    nnz: int

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field) for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipResidualJvpComplexity:
    complexity_class: Literal["O(nnz)"]
    row_visits: int
    csr_entry_visits: int
    multiply_count: int
    load_subtraction_count: int
    dense_matrix_materialized: Literal[False]
    proof_scope: Literal["exact_single_fused_csr_residual_jvp_evaluation"]

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field) for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class HipResidualJvpResultReceipt:
    result_id: str
    context_id: str
    context_receipt_hash: str
    foundation_context_receipt_hash: str
    solver_artifact_hash: str
    execution_evidence_kind: Literal["native_hip", "test_double"]
    execution_plan: HipExecutionPlanBinding
    committed_state: HipCommittedStateBinding
    kernel_artifact: HipKernelArtifactBinding
    direction: HipDirectionBinding
    residual: HipOutputBinding
    jvp: HipOutputBinding
    evaluation: HipResidualJvpEvaluation
    complexity: HipResidualJvpComplexity
    transfer_delta: HipResidualJvpTransferDelta
    native_hip_kernel_execution_proven: bool
    result_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_RESIDUAL_JVP_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_residual_jvp_result_receipt(self)
        return _residual_jvp_result_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipResidualJvpResult:
    receipt: HipResidualJvpResultReceipt
    direction: np.ndarray
    residual: np.ndarray
    jvp: np.ndarray

    @property
    def result_hash(self) -> str:
        return self.receipt.result_hash

    def to_dict(self) -> dict[str, Any]:
        validate_hip_residual_jvp_result(self)
        return self.receipt.to_dict()

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipParityMetrics:
    max_abs_error: float
    max_relative_error: float
    absolute_tolerance: float
    relative_tolerance: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_abs_error": self.max_abs_error,
            "max_relative_error": self.max_relative_error,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HipResidualJvpParityReceipt:
    parity_id: str
    status: Literal["pass", "fail"]
    execution_evidence_kind: Literal["native_hip", "test_double"]
    result_hash: str
    context_receipt_hash: str
    execution_plan_hash: str
    operator_hash: str
    committed_state_hash: str
    kernel_artifact_hash: str
    direction_hash: str
    evaluated_residual_hash: str
    evaluated_jvp_hash: str
    cpu_residual_hash: str
    cpu_jvp_hash: str
    cpu_residual_linf: float
    cpu_jvp_linf: float
    model_ir_content_hash: str
    case_id: str
    dof_count: int
    nnz_count: int
    residual: HipParityMetrics
    jvp: HipParityMetrics
    evaluation_count: Literal[1]
    fallback_used: Literal[False]
    global_parity_proven: Literal[False]
    parity_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_RESIDUAL_JVP_PARITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_residual_jvp_parity_receipt(self)
        return _parity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipOperatorExecutionContext:
    """Owner of a fixed plan/state replay context and its operator buffers."""

    def __init__(
        self,
        *,
        buffers: SolverModelBuffers,
        plan: ExecutionPlan,
        committed_state: StateIR,
        kernel: HipResidualJvpKernelProtocol,
        kernel_binding: HipKernelArtifactBinding,
        execution_evidence_kind: Literal["native_hip", "test_double"],
        base_context: DeviceExecutionContext,
        foundation_context_receipt_hash: str,
        context_id: str,
        pointers: dict[str, Any],
        device_views: tuple[HipOperatorDeviceView, ...],
        telemetry: HipOperatorTelemetry,
    ) -> None:
        self._buffers = buffers
        self._plan = plan
        self._committed_state = committed_state
        self._kernel = kernel
        self._kernel_binding = kernel_binding
        self._execution_evidence_kind = execution_evidence_kind
        self._base = base_context
        self._foundation_context_receipt_hash = foundation_context_receipt_hash
        self._context_id = context_id
        self._pointers = pointers
        self._device_views = device_views
        self._telemetry = telemetry
        self._closed = False
        self._poisoned = False
        self._cleanup_failed = False
        self._foundation_cleanup_failed = False
        self._failure_reason: HipContextReason | None = None

    def __repr__(self) -> str:
        if self._foundation_cleanup_failed or self._cleanup_failed:
            status = "cleanup_failed"
        elif self._closed:
            status = "closed"
        elif self._poisoned:
            status = "poisoned"
        else:
            status = "ready"
        return (
            f"HipOperatorExecutionContext(context_id={self._context_id!r}, "
            f"status={status!r})"
        )

    def __enter__(self) -> HipOperatorExecutionContext:
        self._require_evaluable()
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
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def receipt(self) -> HipOperatorContextReceipt:
        if self._foundation_cleanup_failed or self._cleanup_failed:
            status = "cleanup_failed"
        elif self._closed:
            status = "context_closed"
        elif self._poisoned:
            status = "poisoned"
        else:
            status = "context_ready"
        ready = status == "context_ready"
        return _build_operator_context_receipt(
            status=status,
            context_id=self._context_id,
            actual_backend=_actual_backend(self._execution_evidence_kind),
            execution_evidence_kind=self._execution_evidence_kind,
            reason=self._failure_reason,
            capability_receipt_hash=self._base._capability_receipt.receipt_hash,
            foundation_context_receipt_hash=self._foundation_context_receipt_hash,
            buffers=self._buffers,
            plan=self._plan,
            committed_state=self._committed_state,
            kernel_binding=self._kernel_binding,
            device=self._base._device,
            device_views=self._device_views,
            telemetry=self._telemetry,
            ready=ready,
        )

    def evaluate_for_verification(self, direction: Any) -> HipResidualJvpResult:
        """Execute one fused device replay and explicitly download both outputs."""

        self._require_evaluable()
        _validate_live_bindings(
            self._buffers,
            self._plan,
            self._committed_state,
            self._kernel,
            self._kernel_binding,
            self._execution_evidence_kind,
        )
        vector = _direction_vector(direction, self._plan.dof_count)
        residual_host = np.empty(self._plan.dof_count, dtype="<f8")
        jvp_host = np.empty(self._plan.dof_count, dtype="<f8")
        runtime = self._base._runtime
        stream = self._base._stream
        before = self._telemetry
        try:
            self._telemetry = replace(
                self._telemetry,
                h2d_operation_attempt_count=(
                    self._telemetry.h2d_operation_attempt_count + 1
                ),
                h2d_bytes_attempted=(
                    self._telemetry.h2d_bytes_attempted + vector.nbytes
                ),
            )
            runtime.copy_h2d_async(self._pointers["direction"], vector, stream)
            self._telemetry = replace(
                self._telemetry,
                h2d_operation_success_count=(
                    self._telemetry.h2d_operation_success_count + 1
                ),
                h2d_bytes_succeeded=(
                    self._telemetry.h2d_bytes_succeeded + vector.nbytes
                ),
            )

            self._telemetry = replace(
                self._telemetry,
                kernel_launch_attempt_count=(
                    self._telemetry.kernel_launch_attempt_count + 1
                ),
            )
            launch_result = self._kernel.launch_residual_jvp(
                row_count=self._plan.dof_count,
                nnz_count=int(
                    self._plan.array("global_stiffness_csr_values").size
                ),
                row_ptr=self._pointers["csr_row_ptr"],
                column_indices=self._pointers["csr_col_ind"],
                values=self._pointers["csr_values"],
                load=self._pointers["load_vector"],
                state=self._pointers["committed_displacement"],
                direction=self._pointers["direction"],
                residual_out=self._pointers["residual_output"],
                jvp_out=self._pointers["jvp_output"],
                stream=stream,
            )
            if launch_result is not None:
                raise HipOperatorContextError(
                    "hip_kernel_contract_invalid",
                    "/kernel/launch_residual_jvp",
                    "Kernel launch method must return None or raise.",
                )
            self._telemetry = replace(
                self._telemetry,
                kernel_launch_success_count=(
                    self._telemetry.kernel_launch_success_count + 1
                ),
            )

            for host, name in (
                (residual_host, "residual_output"),
                (jvp_host, "jvp_output"),
            ):
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_attempt_count=(
                        self._telemetry.d2h_operation_attempt_count + 1
                    ),
                    d2h_bytes_attempted=(
                        self._telemetry.d2h_bytes_attempted + host.nbytes
                    ),
                )
                runtime.copy_d2h_async(host, self._pointers[name], stream)
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_success_count=(
                        self._telemetry.d2h_operation_success_count + 1
                    ),
                    d2h_bytes_succeeded=(
                        self._telemetry.d2h_bytes_succeeded + host.nbytes
                    ),
                )

            self._telemetry = replace(
                self._telemetry,
                explicit_sync_attempt_count=(
                    self._telemetry.explicit_sync_attempt_count + 1
                ),
            )
            runtime.synchronize(stream)
            self._telemetry = replace(
                self._telemetry,
                explicit_sync_success_count=(
                    self._telemetry.explicit_sync_success_count + 1
                ),
            )
        except Exception as exc:
            self._poisoned = True
            self._failure_reason = HipContextReason(
                "operator_context_poisoned", _bounded_detail(str(exc))
            )
            if isinstance(exc, HipOperatorContextError):
                raise
            code = exc.code if isinstance(exc, HipContextError) else "hip_operator_evaluation_failed"
            raise HipOperatorContextError(code, "/evaluation", str(exc)) from exc

        residual = immutable_array(residual_host, dtype="<f8")
        jvp = immutable_array(jvp_host, dtype="<f8")
        if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(jvp)):
            self._poisoned = True
            self._failure_reason = HipContextReason(
                "operator_context_poisoned",
                "Residual/JVP download contains non-finite values.",
            )
            raise HipOperatorContextError(
                "hip_operator_output_nonfinite",
                "/evaluation/outputs",
                "Residual/JVP download contains non-finite values.",
            )
        after = self._telemetry
        context_receipt = self.receipt()
        receipt = _build_residual_jvp_result_receipt(
            context_id=self._context_id,
            context_receipt_hash=context_receipt.context_receipt_hash,
            foundation_context_receipt_hash=(
                self._foundation_context_receipt_hash
            ),
            solver_artifact_hash=self._buffers.artifact_hash,
            execution_evidence_kind=self._execution_evidence_kind,
            plan_binding=_plan_binding(self._plan),
            state_binding=_state_binding(self._committed_state),
            kernel_binding=self._kernel_binding,
            direction=vector,
            residual=residual,
            jvp=jvp,
            before=before,
            after=after,
        )
        result = HipResidualJvpResult(receipt, vector, residual, jvp)
        return validate_hip_residual_jvp_result(result, expected_context=self)

    def close(self) -> None:
        """Release all operator allocations, then close the v1 foundation."""

        if self._closed:
            return
        runtime = self._base._runtime
        first_error: Exception | None = None

        if not self._base.closed:
            self._telemetry = replace(
                self._telemetry,
                explicit_sync_attempt_count=(
                    self._telemetry.explicit_sync_attempt_count + 1
                ),
            )
            try:
                runtime.synchronize(self._base._stream)
                self._telemetry = replace(
                    self._telemetry,
                    explicit_sync_success_count=(
                        self._telemetry.explicit_sync_success_count + 1
                    ),
                )
            except Exception as exc:
                first_error = exc

        for name in reversed(tuple(self._pointers)):
            self._telemetry = replace(
                self._telemetry,
                deallocation_attempt_count=(
                    self._telemetry.deallocation_attempt_count + 1
                ),
            )
            byte_length = _view_by_name(self._device_views, name).byte_length
            try:
                runtime.free(self._pointers[name])
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                continue
            del self._pointers[name]
            self._telemetry = replace(
                self._telemetry,
                deallocation_success_count=(
                    self._telemetry.deallocation_success_count + 1
                ),
                current_device_payload_bytes=(
                    self._telemetry.current_device_payload_bytes - byte_length
                ),
            )

        if not self._base.closed:
            try:
                self._base.close()
            except Exception as exc:
                self._foundation_cleanup_failed = True
                if first_error is None:
                    first_error = exc
            else:
                self._foundation_cleanup_failed = False

        if first_error is not None or self._pointers or self._foundation_cleanup_failed:
            self._cleanup_failed = True
            self._failure_reason = HipContextReason(
                "operator_context_cleanup_failed",
                _bounded_detail(str(first_error or "operator allocations remain")),
            )
            raise HipOperatorContextError(
                "hip_operator_cleanup_failed",
                "/cleanup",
                self._failure_reason.detail,
            )
        self._cleanup_failed = False
        self._closed = True
        self._failure_reason = None

    def _require_evaluable(self) -> None:
        if self._closed:
            raise HipOperatorContextError(
                "hip_operator_context_closed", "/status", "Context is closed."
            )
        if self._cleanup_failed or self._foundation_cleanup_failed:
            raise HipOperatorContextError(
                "hip_operator_cleanup_failed",
                "/status",
                "Context cleanup failed and evaluation is forbidden.",
            )
        if self._poisoned:
            raise HipOperatorContextError(
                "hip_operator_context_poisoned",
                "/status",
                "Context is poisoned after a failed evaluation.",
            )


def open_hip_operator_execution_context(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    committed_state: StateIR,
    *,
    kernel: HipResidualJvpKernelProtocol,
    device_ordinal: int = 0,
    runtime_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    runtime: Any | None = None,
) -> HipOperatorContextOpenResult:
    """Open a no-fallback, fixed-plan/fixed-state HIP replay context."""

    try:
        validate_solver_model_buffers(buffers)
        validate_execution_plan(plan, expected_buffers=buffers)
        validate_state_ir(committed_state, expected_plan=plan)
    except Exception as exc:
        raise HipOperatorContextError(
            "hip_operator_binding_invalid", "/bindings", str(exc)
        ) from exc
    if committed_state.role != "committed":
        raise HipOperatorContextError(
            "hip_operator_state_role_invalid",
            "/committed_state/role",
            "Operator context requires one committed StateIR.",
        )
    if not callable(getattr(kernel, "launch_residual_jvp", None)):
        raise HipOperatorContextError(
            "hip_kernel_contract_invalid",
            "/kernel/launch_residual_jvp",
            "Kernel must expose launch_residual_jvp().",
        )
    evidence_kind = _execution_evidence_kind(kernel, runtime)
    kernel_binding = _kernel_binding(kernel, evidence_kind)

    arrays = _operator_host_arrays(plan, committed_state)
    operator_bytes = sum(array.nbytes for array in arrays.values())
    foundation_bytes = sum(row.byte_length for row in buffers.descriptors)
    if memory_budget_bytes is not None:
        if (
            isinstance(memory_budget_bytes, bool)
            or not isinstance(memory_budget_bytes, int)
            or memory_budget_bytes <= 0
        ):
            raise HipOperatorContextError(
                "hip_memory_budget_invalid",
                "/memory_budget_bytes",
                "memory_budget_bytes must be a positive integer.",
            )
        foundation_budget = max(1, memory_budget_bytes - operator_bytes)
    else:
        foundation_budget = None

    base_open = open_device_execution_context(
        buffers,
        device_ordinal=device_ordinal,
        runtime_library=runtime_library,
        memory_budget_bytes=foundation_budget,
        runtime=runtime,
    )
    foundation_hash = base_open.receipt.context_receipt_hash
    context_id = _operator_context_id(
        base_open.receipt.context_id,
        plan,
        committed_state,
        kernel_binding,
    )
    if not base_open.ready or base_open.context is None:
        foundation_detail = (
            base_open.receipt.reason.detail
            if base_open.receipt.reason is not None
            else "HIP foundation unavailable."
        )
        reason = HipContextReason(
            "foundation_context_not_ready", foundation_detail
        )
        if (
            memory_budget_bytes is not None
            and foundation_bytes + operator_bytes > memory_budget_bytes
        ):
            reason = HipContextReason(
                "foundation_context_not_ready",
                (
                    f"Required {foundation_bytes + operator_bytes} bytes exceeds "
                    f"budget {memory_budget_bytes}."
                ),
            )
        receipt = _build_operator_context_receipt(
            status="unavailable",
            context_id=context_id,
            actual_backend=None,
            execution_evidence_kind=evidence_kind,
            reason=reason,
            capability_receipt_hash=base_open.capability_receipt.receipt_hash,
            foundation_context_receipt_hash=foundation_hash,
            buffers=buffers,
            plan=plan,
            committed_state=committed_state,
            kernel_binding=kernel_binding,
            device=None,
            device_views=(),
            telemetry=HipOperatorTelemetry(),
            ready=False,
        )
        return HipOperatorContextOpenResult(
            None,
            receipt,
            cleanup_owner=base_open.context,
        )

    base = base_open.context
    runtime_impl = base._runtime
    pointers: dict[str, Any] = {}
    telemetry = HipOperatorTelemetry()
    views = _operator_device_views(arrays, device_ordinal)
    try:
        for view in views:
            telemetry = replace(
                telemetry,
                allocation_attempt_count=telemetry.allocation_attempt_count + 1,
            )
            pointer = runtime_impl.malloc(view.byte_length)
            pointers[view.name] = pointer
            telemetry = replace(
                telemetry,
                allocation_success_count=telemetry.allocation_success_count + 1,
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes + view.byte_length
                ),
                peak_device_payload_bytes=(
                    telemetry.peak_device_payload_bytes + view.byte_length
                ),
            )
            if view.name in _INITIAL_UPLOAD_NAMES:
                array = arrays[view.name]
                telemetry = replace(
                    telemetry,
                    h2d_operation_attempt_count=(
                        telemetry.h2d_operation_attempt_count + 1
                    ),
                    h2d_bytes_attempted=(
                        telemetry.h2d_bytes_attempted + view.byte_length
                    ),
                )
                runtime_impl.copy_h2d_async(pointer, array, base._stream)
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
            telemetry,
            explicit_sync_attempt_count=telemetry.explicit_sync_attempt_count + 1,
        )
        runtime_impl.synchronize(base._stream)
        telemetry = replace(
            telemetry,
            explicit_sync_success_count=telemetry.explicit_sync_success_count + 1,
        )
        context = HipOperatorExecutionContext(
            buffers=buffers,
            plan=plan,
            committed_state=committed_state,
            kernel=kernel,
            kernel_binding=kernel_binding,
            execution_evidence_kind=evidence_kind,
            base_context=base,
            foundation_context_receipt_hash=foundation_hash,
            context_id=context_id,
            pointers=pointers,
            device_views=views,
            telemetry=telemetry,
        )
        receipt = context.receipt()
        return HipOperatorContextOpenResult(context, receipt)
    except Exception as exc:
        cleanup_error: Exception | None = None
        for name in reversed(tuple(pointers)):
            telemetry = replace(
                telemetry,
                deallocation_attempt_count=telemetry.deallocation_attempt_count + 1,
            )
            byte_length = _view_by_name(views, name).byte_length
            try:
                runtime_impl.free(pointers[name])
            except Exception as free_exc:
                if cleanup_error is None:
                    cleanup_error = free_exc
                continue
            del pointers[name]
            telemetry = replace(
                telemetry,
                deallocation_success_count=(
                    telemetry.deallocation_success_count + 1
                ),
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes - byte_length
                ),
            )
        foundation_cleanup_failed = False
        try:
            base.close()
        except Exception as base_close_exc:
            foundation_cleanup_failed = True
            if cleanup_error is None:
                cleanup_error = base_close_exc
        reason = _open_failure_reason(exc)
        status: Literal["unavailable", "cleanup_failed"] = (
            "cleanup_failed" if cleanup_error is not None or pointers else "unavailable"
        )
        if cleanup_error is not None:
            reason = HipContextReason(
                "operator_context_cleanup_failed",
                _bounded_detail(f"{exc}; cleanup: {cleanup_error}"),
            )
        if status == "cleanup_failed":
            cleanup_context = HipOperatorExecutionContext(
                buffers=buffers,
                plan=plan,
                committed_state=committed_state,
                kernel=kernel,
                kernel_binding=kernel_binding,
                execution_evidence_kind=evidence_kind,
                base_context=base,
                foundation_context_receipt_hash=foundation_hash,
                context_id=context_id,
                pointers=pointers,
                device_views=views,
                telemetry=telemetry,
            )
            cleanup_context._cleanup_failed = True
            cleanup_context._foundation_cleanup_failed = (
                foundation_cleanup_failed
            )
            cleanup_context._failure_reason = reason
            return HipOperatorContextOpenResult(
                cleanup_context, cleanup_context.receipt()
            )
        receipt = _build_operator_context_receipt(
            status=status,
            context_id=context_id,
            actual_backend=(
                _actual_backend(evidence_kind) if status == "cleanup_failed" else None
            ),
            execution_evidence_kind=evidence_kind,
            reason=reason,
            capability_receipt_hash=base_open.capability_receipt.receipt_hash,
            foundation_context_receipt_hash=foundation_hash,
            buffers=buffers,
            plan=plan,
            committed_state=committed_state,
            kernel_binding=kernel_binding,
            device=base._device if status == "cleanup_failed" else None,
            device_views=views if status == "cleanup_failed" else (),
            telemetry=telemetry,
            ready=False,
        )
        return HipOperatorContextOpenResult(None, receipt)


def validate_hip_operator_context_receipt(
    receipt: HipOperatorContextReceipt,
    *,
    expected_buffers: SolverModelBuffers | None = None,
    expected_plan: ExecutionPlan | None = None,
    expected_state: StateIR | None = None,
    expected_kernel: Any | None = None,
) -> HipOperatorContextReceipt:
    if not isinstance(receipt, HipOperatorContextReceipt):
        raise HipOperatorContextError(
            "hip_operator_receipt_type_invalid", "/", "Expected context receipt."
        )
    payload = _operator_context_payload(receipt, include_hash=True)
    _validate_schema(_context_schema_validator(), payload, "hip_operator_context")
    expected_hash = canonical_hash(
        _operator_context_payload(receipt, include_hash=False)
    )
    if receipt.context_receipt_hash != expected_hash:
        _fail("hip_operator_context_hash_mismatch", "/context_receipt_hash")
    _validate_hash_bindings(receipt)
    _validate_telemetry(receipt.telemetry)
    if (
        receipt.execution_plan.model_ir_content_hash
        != receipt.solver_model_buffers.model_ir_content_hash
        or receipt.committed_state.execution_plan_hash
        != receipt.execution_plan.plan_hash
        or receipt.committed_state.operator_hash
        != receipt.execution_plan.operator_hash
        or receipt.committed_state.dof_count != receipt.execution_plan.dof_count
    ):
        _fail("hip_operator_cross_binding_mismatch", "/bindings")
    if receipt.telemetry.fallback_count != 0:
        _fail("hip_operator_fallback_forbidden", "/telemetry/fallback_count")
    if any(
        (
            receipt.claims.native_hip_kernel_execution_proven,
            receipt.claims.device_constitutive_assembly_proven,
            receipt.claims.solver_ready,
            receipt.claims.newton_ready,
            receipt.claims.krylov_ready,
            receipt.claims.cpu_hip_global_parity_proven,
            receipt.claims.exact_foundation_cleanup_proven,
            receipt.claims.commercial_readiness,
        )
    ):
        _fail("hip_operator_claim_invalid", "/claims")
    if receipt.status == "context_ready":
        if not all(
            (
                receipt.claims.model_buffers_foundation_bound,
                receipt.claims.canonical_csr_operator_bound,
                receipt.claims.committed_state_bound,
                receipt.claims.residual_jvp_ready,
            )
        ):
            _fail("hip_operator_ready_claim_missing", "/claims")
        if tuple(view.name for view in receipt.device_views) != _VIEW_NAMES:
            _fail("hip_operator_device_views_invalid", "/device_views")
        if receipt.telemetry.allocation_success_count != len(_VIEW_NAMES):
            _fail("hip_operator_telemetry_invalid", "/telemetry")
        if receipt.telemetry.h2d_operation_success_count < len(_INITIAL_UPLOAD_NAMES):
            _fail("hip_operator_initial_upload_incomplete", "/telemetry")
    elif receipt.status == "unavailable":
        if any(
            (
                receipt.claims.model_buffers_foundation_bound,
                receipt.claims.canonical_csr_operator_bound,
                receipt.claims.committed_state_bound,
                receipt.claims.residual_jvp_ready,
            )
        ):
            _fail("hip_operator_nonready_claim_invalid", "/claims")
    else:
        expected_bound = receipt.status in (
            "context_closed",
            "poisoned",
            "cleanup_failed",
        )
        if (
            receipt.claims.model_buffers_foundation_bound != expected_bound
            or receipt.claims.canonical_csr_operator_bound != expected_bound
            or receipt.claims.committed_state_bound != expected_bound
            or receipt.claims.residual_jvp_ready
        ):
            _fail("hip_operator_nonready_claim_invalid", "/claims")
    if receipt.device_views:
        _validate_device_view_shapes(receipt)
    if receipt.status == "context_ready":
        _validate_ready_context_telemetry(receipt)
    if receipt.device is not None and (
        receipt.device.free_memory_bytes_before_upload
        > receipt.device.total_memory_bytes
        or receipt.device.free_memory_bytes_after_upload
        > receipt.device.total_memory_bytes
    ):
        _fail("hip_operator_device_memory_invalid", "/device")
    if receipt.execution_evidence_kind == "test_double":
        if receipt.actual_backend not in (None, "test_double"):
            _fail("hip_operator_evidence_kind_mismatch", "/actual_backend")
        if receipt.kernel_artifact.artifact_kind != "test_double":
            _fail("hip_operator_evidence_kind_mismatch", "/kernel_artifact")
    else:
        if receipt.actual_backend not in (None, "hip_native"):
            _fail("hip_operator_evidence_kind_mismatch", "/actual_backend")
        if receipt.kernel_artifact.artifact_kind != "native_hip":
            _fail("hip_operator_evidence_kind_mismatch", "/kernel_artifact")
    _reject_runtime_handle_terms(payload)

    if expected_buffers is not None:
        validate_solver_model_buffers(expected_buffers)
        if receipt.solver_model_buffers != _buffer_binding(expected_buffers):
            _fail("hip_operator_buffer_binding_mismatch", "/solver_model_buffers")
    if expected_plan is not None:
        validate_execution_plan(expected_plan, expected_buffers=expected_buffers)
        if receipt.execution_plan != _plan_binding(expected_plan):
            _fail("hip_operator_plan_binding_mismatch", "/execution_plan")
        if receipt.device_views:
            expected_hashes = {
                "csr_row_ptr": array_data_hash(expected_plan.array("csr_row_ptr")),
                "csr_col_ind": array_data_hash(
                    expected_plan.array("csr_column_indices")
                ),
                "csr_values": array_data_hash(
                    expected_plan.array("global_stiffness_csr_values")
                ),
                "load_vector": array_data_hash(expected_plan.array("global_load")),
            }
            for name, expected_hash in expected_hashes.items():
                if _view_by_name(receipt.device_views, name).data_hash != expected_hash:
                    _fail(
                        "hip_operator_device_view_binding_mismatch",
                        f"/device_views/{name}/data_hash",
                    )
    if expected_state is not None:
        validate_state_ir(expected_state, expected_plan=expected_plan)
        if receipt.committed_state != _state_binding(expected_state):
            _fail("hip_operator_state_binding_mismatch", "/committed_state")
        if receipt.device_views and (
            _view_by_name(
                receipt.device_views, "committed_displacement"
            ).data_hash
            != expected_state.vector_hashes["displacement"]
        ):
            _fail(
                "hip_operator_device_view_binding_mismatch",
                "/device_views/committed_displacement/data_hash",
            )
    if expected_kernel is not None:
        expected_kind = receipt.execution_evidence_kind
        if receipt.kernel_artifact != _kernel_binding(expected_kernel, expected_kind):
            _fail("hip_operator_kernel_binding_mismatch", "/kernel_artifact")
    return receipt


def validate_hip_residual_jvp_result_receipt(
    receipt: HipResidualJvpResultReceipt,
) -> HipResidualJvpResultReceipt:
    if not isinstance(receipt, HipResidualJvpResultReceipt):
        raise HipOperatorContextError(
            "hip_residual_jvp_receipt_type_invalid", "/", "Expected result receipt."
        )
    payload = _residual_jvp_result_payload(receipt, include_hash=True)
    _validate_schema(_result_schema_validator(), payload, "hip_residual_jvp_result")
    if receipt.result_hash != canonical_hash(
        _residual_jvp_result_payload(receipt, include_hash=False)
    ):
        _fail("hip_residual_jvp_result_hash_mismatch", "/result_hash")
    for value in (
        receipt.context_receipt_hash,
        receipt.foundation_context_receipt_hash,
        receipt.solver_artifact_hash,
        receipt.execution_plan.model_ir_content_hash,
        receipt.execution_plan.plan_hash,
        receipt.execution_plan.operator_hash,
        receipt.execution_plan.pattern_hash,
        receipt.execution_plan.partition_hash,
        receipt.committed_state.state_hash,
        receipt.committed_state.displacement_hash,
        receipt.committed_state.execution_plan_hash,
        receipt.committed_state.operator_hash,
        receipt.kernel_artifact.artifact_receipt_hash,
        receipt.kernel_artifact.artifact_hash,
        receipt.kernel_artifact.source_hash,
        receipt.kernel_artifact.library_hash,
        receipt.kernel_artifact.abi_hash,
        receipt.kernel_artifact.build_target_hash,
        receipt.direction.data_hash,
        receipt.residual.data_hash,
        receipt.jvp.data_hash,
    ):
        _require_hash(value, "/bindings")
    plan = receipt.execution_plan
    state = receipt.committed_state
    if (
        state.execution_plan_hash != plan.plan_hash
        or state.operator_hash != plan.operator_hash
        or state.dof_count != plan.dof_count
        or plan.free_dof_count > plan.dof_count
        or receipt.evaluation.dof_count != plan.dof_count
        or receipt.evaluation.nnz != plan.nnz
    ):
        _fail("hip_residual_jvp_cross_binding_mismatch", "/input_bindings")
    for name, binding in (
        ("direction", receipt.direction),
        ("residual", receipt.residual),
        ("jvp", receipt.jvp),
    ):
        if (
            binding.dtype != "<f8"
            or binding.shape != (plan.dof_count,)
            or binding.byte_length != plan.dof_count * np.dtype("<f8").itemsize
        ):
            _fail(
                "hip_residual_jvp_vector_binding_invalid",
                f"/{name}",
            )
    if receipt.evaluation.launch_count != 1 or not receipt.evaluation.fused_launch:
        _fail("hip_residual_jvp_launch_count_invalid", "/evaluation")
    expected_delta = (
        1,
        1,
        2,
        2,
        1,
        1,
        1,
        1,
    )
    actual_delta = (
        receipt.transfer_delta.h2d_operation_attempt_count,
        receipt.transfer_delta.h2d_operation_success_count,
        receipt.transfer_delta.d2h_operation_attempt_count,
        receipt.transfer_delta.d2h_operation_success_count,
        receipt.transfer_delta.explicit_sync_attempt_count,
        receipt.transfer_delta.explicit_sync_success_count,
        receipt.transfer_delta.kernel_launch_attempt_count,
        receipt.transfer_delta.kernel_launch_success_count,
    )
    if actual_delta != expected_delta:
        _fail("hip_residual_jvp_transfer_delta_invalid", "/transfer_delta")
    vector_bytes = receipt.evaluation.dof_count * np.dtype("<f8").itemsize
    if (
        receipt.transfer_delta.h2d_bytes_attempted != vector_bytes
        or receipt.transfer_delta.h2d_bytes_succeeded != vector_bytes
        or receipt.transfer_delta.d2h_bytes_attempted != 2 * vector_bytes
        or receipt.transfer_delta.d2h_bytes_succeeded != 2 * vector_bytes
    ):
        _fail("hip_residual_jvp_transfer_bytes_invalid", "/transfer_delta")
    if receipt.complexity.row_visits != receipt.evaluation.dof_count:
        _fail("hip_residual_jvp_complexity_invalid", "/complexity/row_visits")
    if receipt.complexity.csr_entry_visits != receipt.evaluation.nnz:
        _fail("hip_residual_jvp_complexity_invalid", "/complexity/csr_entry_visits")
    if receipt.complexity.multiply_count != 2 * receipt.evaluation.nnz:
        _fail("hip_residual_jvp_complexity_invalid", "/complexity/multiply_count")
    if receipt.complexity.load_subtraction_count != receipt.evaluation.dof_count:
        _fail(
            "hip_residual_jvp_complexity_invalid",
            "/complexity/load_subtraction_count",
        )
    if receipt.native_hip_kernel_execution_proven != (
        receipt.execution_evidence_kind == "native_hip"
    ):
        _fail("hip_residual_jvp_native_proof_invalid", "/native_hip_kernel_execution_proven")
    if receipt.kernel_artifact.artifact_kind != receipt.execution_evidence_kind:
        _fail("hip_residual_jvp_evidence_kind_invalid", "/kernel_artifact")
    _reject_runtime_handle_terms(payload)
    return receipt


def validate_hip_residual_jvp_result(
    result: HipResidualJvpResult,
    *,
    expected_context: HipOperatorExecutionContext | None = None,
    expected_plan: ExecutionPlan | None = None,
    expected_state: StateIR | None = None,
) -> HipResidualJvpResult:
    if not isinstance(result, HipResidualJvpResult):
        raise HipOperatorContextError(
            "hip_residual_jvp_result_type_invalid", "/", "Expected result."
        )
    validate_hip_residual_jvp_result_receipt(result.receipt)
    dof_count = result.receipt.evaluation.dof_count
    for name, array, binding in (
        ("direction", result.direction, result.receipt.direction),
        ("residual", result.residual, result.receipt.residual),
        ("jvp", result.jvp, result.receipt.jvp),
    ):
        _validate_immutable_f64_vector(array, dof_count, f"/{name}")
        if (
            binding.dtype != array.dtype.str
            or binding.shape != array.shape
            or binding.byte_length != array.nbytes
            or binding.data_hash != array_data_hash(array)
        ):
            _fail("hip_residual_jvp_array_binding_mismatch", f"/{name}")
    if expected_context is not None:
        if result.receipt.context_id != expected_context.context_id:
            _fail("hip_residual_jvp_context_binding_mismatch", "/context_id")
        if (
            result.receipt.foundation_context_receipt_hash
            != expected_context._foundation_context_receipt_hash
            or result.receipt.solver_artifact_hash
            != expected_context._buffers.artifact_hash
        ):
            _fail("hip_residual_jvp_context_binding_mismatch", "/input_bindings")
        if result.receipt.execution_plan != _plan_binding(expected_context._plan):
            _fail("hip_residual_jvp_plan_binding_mismatch", "/execution_plan")
        if result.receipt.committed_state != _state_binding(
            expected_context._committed_state
        ):
            _fail("hip_residual_jvp_state_binding_mismatch", "/committed_state")
        if result.receipt.kernel_artifact != expected_context._kernel_binding:
            _fail("hip_residual_jvp_kernel_binding_mismatch", "/kernel_artifact")
    if expected_plan is not None:
        validate_execution_plan(expected_plan)
        if result.receipt.execution_plan != _plan_binding(expected_plan):
            _fail("hip_residual_jvp_plan_binding_mismatch", "/execution_plan")
    if expected_state is not None:
        validate_state_ir(expected_state, expected_plan=expected_plan)
        if result.receipt.committed_state != _state_binding(expected_state):
            _fail("hip_residual_jvp_state_binding_mismatch", "/committed_state")
    return result


def verify_hip_residual_jvp_parity(
    result: HipResidualJvpResult,
    *,
    plan: ExecutionPlan,
    committed_state: StateIR,
    residual_absolute_tolerance: float = 1.0e-8,
    residual_relative_tolerance: float = 1.0e-8,
    jvp_absolute_tolerance: float = 1.0e-8,
    jvp_relative_tolerance: float = 1.0e-8,
) -> HipResidualJvpParityReceipt:
    """Replay the same CSR on CPU solely as a one-case verification oracle."""

    validate_execution_plan(plan)
    validate_state_ir(committed_state, expected_plan=plan)
    validate_hip_residual_jvp_result(
        result, expected_plan=plan, expected_state=committed_state
    )
    tolerances = (
        residual_absolute_tolerance,
        residual_relative_tolerance,
        jvp_absolute_tolerance,
        jvp_relative_tolerance,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.integer, np.floating))
        or not math.isfinite(float(value))
        or float(value) < 0.0
        for value in tolerances
    ):
        raise HipOperatorContextError(
            "hip_parity_tolerance_invalid",
            "/tolerances",
            "Parity tolerances must be finite and non-negative.",
        )
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    values = plan.array("global_stiffness_csr_values")
    load = plan.array("global_load")
    cpu_residual = immutable_array(
        _csr_matvec(row_ptr, columns, values, committed_state.displacement_si) - load,
        dtype="<f8",
    )
    cpu_jvp = immutable_array(
        _csr_matvec(row_ptr, columns, values, result.direction), dtype="<f8"
    )
    residual_metrics = _parity_metrics(
        result.residual,
        cpu_residual,
        float(residual_absolute_tolerance),
        float(residual_relative_tolerance),
    )
    jvp_metrics = _parity_metrics(
        result.jvp,
        cpu_jvp,
        float(jvp_absolute_tolerance),
        float(jvp_relative_tolerance),
    )
    status: Literal["pass", "fail"] = (
        "pass" if residual_metrics.passed and jvp_metrics.passed else "fail"
    )
    parity_seed = canonical_hash(
        {
            "result_hash": result.result_hash,
            "cpu_residual_hash": array_data_hash(cpu_residual),
            "cpu_jvp_hash": array_data_hash(cpu_jvp),
            "residual_tolerances": [
                float(residual_absolute_tolerance),
                float(residual_relative_tolerance),
            ],
            "jvp_tolerances": [
                float(jvp_absolute_tolerance),
                float(jvp_relative_tolerance),
            ],
        }
    )
    draft = HipResidualJvpParityReceipt(
        parity_id=f"HipParity:{parity_seed.removeprefix('sha256:')[:24]}",
        status=status,
        execution_evidence_kind=result.receipt.execution_evidence_kind,
        result_hash=result.result_hash,
        context_receipt_hash=result.receipt.context_receipt_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        committed_state_hash=committed_state.state_hash,
        kernel_artifact_hash=result.receipt.kernel_artifact.artifact_hash,
        direction_hash=result.receipt.direction.data_hash,
        evaluated_residual_hash=result.receipt.residual.data_hash,
        evaluated_jvp_hash=result.receipt.jvp.data_hash,
        cpu_residual_hash=array_data_hash(cpu_residual),
        cpu_jvp_hash=array_data_hash(cpu_jvp),
        cpu_residual_linf=float(np.max(np.abs(cpu_residual), initial=0.0)),
        cpu_jvp_linf=float(np.max(np.abs(cpu_jvp), initial=0.0)),
        model_ir_content_hash=plan.model_ir_content_hash,
        case_id=plan.plan_id,
        dof_count=plan.dof_count,
        nnz_count=int(plan.array("global_stiffness_csr_values").size),
        residual=residual_metrics,
        jvp=jvp_metrics,
        evaluation_count=1,
        fallback_used=False,
        global_parity_proven=False,
        parity_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        parity_hash=canonical_hash(_parity_payload(draft, include_hash=False)),
    )
    return validate_hip_residual_jvp_parity_receipt(receipt)


def validate_hip_residual_jvp_parity_receipt(
    receipt: HipResidualJvpParityReceipt,
) -> HipResidualJvpParityReceipt:
    if not isinstance(receipt, HipResidualJvpParityReceipt):
        raise HipOperatorContextError(
            "hip_parity_receipt_type_invalid", "/", "Expected parity receipt."
        )
    payload = _parity_payload(receipt, include_hash=True)
    _validate_schema(_parity_schema_validator(), payload, "hip_residual_jvp_parity")
    if receipt.parity_hash != canonical_hash(
        _parity_payload(receipt, include_hash=False)
    ):
        _fail("hip_parity_hash_mismatch", "/parity_hash")
    expected_status = (
        "pass" if receipt.residual.passed and receipt.jvp.passed else "fail"
    )
    if receipt.status != expected_status:
        _fail("hip_parity_status_invalid", "/status")
    if receipt.evaluation_count != 1 or receipt.global_parity_proven:
        _fail("hip_parity_scope_invalid", "/evaluation_count")
    for value in (
        receipt.result_hash,
        receipt.context_receipt_hash,
        receipt.execution_plan_hash,
        receipt.operator_hash,
        receipt.committed_state_hash,
        receipt.kernel_artifact_hash,
        receipt.direction_hash,
        receipt.evaluated_residual_hash,
        receipt.evaluated_jvp_hash,
        receipt.cpu_residual_hash,
        receipt.cpu_jvp_hash,
        receipt.model_ir_content_hash,
    ):
        _require_hash(value, "/input_bindings")
    if receipt.dof_count < 1 or receipt.nnz_count < receipt.dof_count:
        _fail("hip_parity_scope_invalid", "/case_scope")
    for metrics in (receipt.residual, receipt.jvp):
        values = (
            metrics.max_abs_error,
            metrics.max_relative_error,
            metrics.absolute_tolerance,
            metrics.relative_tolerance,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            _fail("hip_parity_metric_invalid", "/metrics")
        expected_pass = (
            metrics.max_abs_error <= metrics.absolute_tolerance
            and metrics.max_relative_error <= metrics.relative_tolerance
        )
        if metrics.passed != expected_pass:
            _fail("hip_parity_check_invalid", "/checks")
    _reject_runtime_handle_terms(payload)
    return receipt


def _operator_host_arrays(
    plan: ExecutionPlan, committed_state: StateIR
) -> dict[str, np.ndarray]:
    dof_count = plan.dof_count
    return {
        "csr_row_ptr": plan.array("csr_row_ptr"),
        "csr_col_ind": plan.array("csr_column_indices"),
        "csr_values": plan.array("global_stiffness_csr_values"),
        "load_vector": plan.array("global_load"),
        "committed_displacement": committed_state.displacement_si,
        "direction": immutable_array(np.zeros(dof_count), dtype="<f8"),
        "residual_output": immutable_array(np.zeros(dof_count), dtype="<f8"),
        "jvp_output": immutable_array(np.zeros(dof_count), dtype="<f8"),
    }


def _operator_device_views(
    arrays: dict[str, np.ndarray], ordinal: int
) -> tuple[HipOperatorDeviceView, ...]:
    access = {
        "csr_row_ptr": "read_only",
        "csr_col_ind": "read_only",
        "csr_values": "read_only",
        "load_vector": "read_only",
        "committed_displacement": "read_only",
        "direction": "read_write",
        "residual_output": "write_only",
        "jvp_output": "write_only",
    }
    views: list[HipOperatorDeviceView] = []
    for name in _VIEW_NAMES:
        array = arrays[name]
        views.append(
            HipOperatorDeviceView(
                name=name,
                dtype=array.dtype.str,
                shape=array.shape,
                layout="C",
                byte_length=array.nbytes,
                data_hash=(
                    array_data_hash(array) if name in _INITIAL_UPLOAD_NAMES else None
                ),
                memory_space="hip_device",
                device_ordinal=ordinal,
                access=access[name],
                initial_transfer=(
                    "async_h2d_then_explicit_sync"
                    if name in _INITIAL_UPLOAD_NAMES
                    else "none"
                ),
            )
        )
    return tuple(views)


def _execution_evidence_kind(
    kernel: Any, runtime: Any | None
) -> Literal["native_hip", "test_double"]:
    if runtime is None and _is_loader_owned_hip_csr_kernel(kernel):
        try:
            validate_hip_csr_kernel_artifact_receipt(kernel.artifact_receipt)
        except Exception as exc:
            raise HipOperatorContextError(
                "hip_kernel_artifact_receipt_invalid",
                "/kernel/artifact_receipt",
                str(exc),
            ) from exc
        return "native_hip"
    return "test_double"


def _kernel_binding(
    kernel: Any,
    artifact_kind: Literal["native_hip", "test_double"],
) -> HipKernelArtifactBinding:
    try:
        receipt = kernel.artifact_receipt
    except Exception as exc:
        raise HipOperatorContextError(
            "hip_kernel_artifact_receipt_missing",
            "/kernel/artifact_receipt",
            "Kernel must expose an artifact_receipt.",
        ) from exc
    if artifact_kind == "native_hip":
        if not isinstance(receipt, HipCsrKernelArtifactReceipt):
            raise HipOperatorContextError(
                "hip_kernel_artifact_receipt_invalid",
                "/kernel/artifact_receipt",
                "Native evidence requires HipCsrKernelArtifactReceipt.",
            )
        try:
            validate_hip_csr_kernel_artifact_receipt(receipt)
        except Exception as exc:
            raise HipOperatorContextError(
                "hip_kernel_artifact_receipt_invalid",
                "/kernel/artifact_receipt",
                str(exc),
            ) from exc
    if hasattr(receipt, "to_dict"):
        manifest = receipt.to_dict()
    elif hasattr(receipt, "to_manifest"):
        manifest = receipt.to_manifest()
    elif isinstance(receipt, dict):
        manifest = dict(receipt)
    else:
        raise HipOperatorContextError(
            "hip_kernel_artifact_receipt_invalid",
            "/kernel/artifact_receipt",
            "Artifact receipt must be manifest-like.",
        )
    if not isinstance(manifest, dict):
        _fail("hip_kernel_artifact_receipt_invalid", "/kernel/artifact_receipt")
    required = (
        "schema_version",
        "artifact_hash",
        "source_hash",
        "library_hash",
        "abi_hash",
        "build_target_hash",
        "entrypoint",
        "abi_version",
        "block_size",
        "targets",
        "flags",
    )
    missing = [name for name in required if name not in manifest]
    if missing:
        raise HipOperatorContextError(
            "hip_kernel_artifact_receipt_invalid",
            "/kernel/artifact_receipt",
            f"Missing artifact fields: {', '.join(missing)}.",
        )
    if manifest["schema_version"] != HIP_CSR_KERNEL_ARTIFACT_SCHEMA_VERSION:
        _fail("hip_kernel_schema_version_invalid", "/kernel/schema_version")
    if manifest["entrypoint"] != HIP_CSR_KERNEL_ENTRYPOINT:
        _fail("hip_kernel_entrypoint_invalid", "/kernel/entrypoint")
    for name in (
        "artifact_hash",
        "source_hash",
        "library_hash",
        "abi_hash",
        "build_target_hash",
    ):
        _require_hash(manifest[name], f"/kernel/{name}")
    if manifest["artifact_hash"] != manifest["library_hash"]:
        _fail("hip_kernel_library_hash_mismatch", "/kernel/library_hash")
    abi_version = _nonnegative_int(manifest["abi_version"], "/kernel/abi_version", 1)
    block_size = _nonnegative_int(manifest["block_size"], "/kernel/block_size", 1)
    targets = _string_tuple(manifest["targets"], "/kernel/targets", require_nonempty=True)
    flags = _string_tuple(manifest["flags"], "/kernel/flags", require_nonempty=False)
    artifact_receipt_hash = manifest.get("receipt_hash")
    if artifact_receipt_hash is None:
        artifact_receipt_hash = canonical_hash(manifest)
    else:
        _require_hash(artifact_receipt_hash, "/kernel/receipt_hash")
        unhashed_manifest = dict(manifest)
        del unhashed_manifest["receipt_hash"]
        if artifact_receipt_hash != canonical_hash(unhashed_manifest):
            _fail(
                "hip_kernel_artifact_receipt_hash_mismatch",
                "/kernel/receipt_hash",
            )
    return HipKernelArtifactBinding(
        schema_version=str(manifest["schema_version"]),
        artifact_receipt_hash=str(artifact_receipt_hash),
        artifact_hash=str(manifest["artifact_hash"]),
        source_hash=str(manifest["source_hash"]),
        library_hash=str(manifest["library_hash"]),
        abi_hash=str(manifest["abi_hash"]),
        build_target_hash=str(manifest["build_target_hash"]),
        entrypoint=str(manifest["entrypoint"]),
        abi_version=abi_version,
        block_size=block_size,
        targets=targets,
        flags=flags,
        artifact_kind=artifact_kind,
    )


def _validate_live_bindings(
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    committed_state: StateIR,
    kernel: Any,
    kernel_binding: HipKernelArtifactBinding,
    evidence_kind: Literal["native_hip", "test_double"],
) -> None:
    validate_solver_model_buffers(buffers)
    validate_execution_plan(plan, expected_buffers=buffers)
    validate_state_ir(committed_state, expected_plan=plan)
    if committed_state.role != "committed":
        _fail("hip_operator_state_role_invalid", "/committed_state/role")
    if _kernel_binding(kernel, evidence_kind) != kernel_binding:
        _fail("hip_operator_kernel_binding_mismatch", "/kernel_artifact")


def _buffer_binding(buffers: SolverModelBuffers) -> HipBufferBinding:
    return HipBufferBinding(
        schema_version=buffers.schema_version,
        model_ir_content_hash=buffers.model_ir_content_hash,
        load_pattern_id=buffers.load_pattern_id,
        numeric_buffer_hash=buffers.numeric_buffer_hash,
        entity_mapping_hash=buffers.entity_mapping_hash,
        artifact_hash=buffers.artifact_hash,
    )


def _plan_binding(plan: ExecutionPlan) -> HipExecutionPlanBinding:
    return HipExecutionPlanBinding(
        schema_version=plan.schema_version,
        model_ir_content_hash=plan.model_ir_content_hash,
        plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        partition_hash=plan.partition_hash,
        dof_count=plan.dof_count,
        free_dof_count=int(plan.array("free_dofs").size),
        nnz=int(plan.array("global_stiffness_csr_values").size),
    )


def _state_binding(state: StateIR) -> HipCommittedStateBinding:
    if state.role != "committed":
        _fail("hip_operator_state_role_invalid", "/committed_state/role")
    return HipCommittedStateBinding(
        schema_version=state.schema_version,
        role="committed",
        state_hash=state.state_hash,
        displacement_hash=state.vector_hashes["displacement"],
        epoch=state.epoch,
        execution_plan_hash=state.execution_plan_hash,
        operator_hash=state.operator_hash,
        dof_count=state.dof_count,
    )


def _build_operator_context_receipt(
    *,
    status: Literal[
        "context_ready",
        "context_closed",
        "unavailable",
        "poisoned",
        "cleanup_failed",
    ],
    context_id: str,
    actual_backend: Literal["hip_native", "test_double"] | None,
    execution_evidence_kind: Literal["native_hip", "test_double"],
    reason: HipContextReason | None,
    capability_receipt_hash: str,
    foundation_context_receipt_hash: str,
    buffers: SolverModelBuffers,
    plan: ExecutionPlan,
    committed_state: StateIR,
    kernel_binding: HipKernelArtifactBinding,
    device: HipDeviceContextIdentity | None,
    device_views: tuple[HipOperatorDeviceView, ...],
    telemetry: HipOperatorTelemetry,
    ready: bool,
) -> HipOperatorContextReceipt:
    bindings_preserved = status != "unavailable"
    draft = HipOperatorContextReceipt(
        status=status,
        context_id=context_id,
        actual_backend=actual_backend,
        execution_evidence_kind=execution_evidence_kind,
        reason=reason,
        capability_receipt_hash=capability_receipt_hash,
        foundation_context_receipt_hash=foundation_context_receipt_hash,
        solver_model_buffers=_buffer_binding(buffers),
        execution_plan=_plan_binding(plan),
        committed_state=_state_binding(committed_state),
        kernel_artifact=kernel_binding,
        device=device,
        device_views=device_views,
        telemetry=telemetry,
        claims=HipOperatorClaims(
            model_buffers_foundation_bound=bindings_preserved,
            canonical_csr_operator_bound=bindings_preserved,
            committed_state_bound=bindings_preserved,
            residual_jvp_ready=ready,
        ),
        context_receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        context_receipt_hash=canonical_hash(
            _operator_context_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_operator_context_receipt(receipt)


def _operator_context_payload(
    receipt: HipOperatorContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_OPERATOR_CONTEXT_SCHEMA_VERSION,
        "capability_profile": HIP_OPERATOR_CONTEXT_CAPABILITY_PROFILE,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "requested_backend": "hip",
        "actual_backend": receipt.actual_backend,
        "execution_evidence_kind": receipt.execution_evidence_kind,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "capability_receipt_hash": receipt.capability_receipt_hash,
        "foundation_context_receipt_hash": receipt.foundation_context_receipt_hash,
        "solver_model_buffers": receipt.solver_model_buffers.to_dict(),
        "execution_plan": receipt.execution_plan.to_dict(),
        "committed_state": receipt.committed_state.to_dict(),
        "kernel_artifact": receipt.kernel_artifact.to_dict(),
        "device": (
            None if receipt.device is None else _operator_device_payload(receipt.device)
        ),
        "device_views": [view.to_dict() for view in receipt.device_views],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _build_residual_jvp_result_receipt(
    *,
    context_id: str,
    context_receipt_hash: str,
    foundation_context_receipt_hash: str,
    solver_artifact_hash: str,
    execution_evidence_kind: Literal["native_hip", "test_double"],
    plan_binding: HipExecutionPlanBinding,
    state_binding: HipCommittedStateBinding,
    kernel_binding: HipKernelArtifactBinding,
    direction: np.ndarray,
    residual: np.ndarray,
    jvp: np.ndarray,
    before: HipOperatorTelemetry,
    after: HipOperatorTelemetry,
) -> HipResidualJvpResultReceipt:
    direction_binding = HipDirectionBinding(
        dtype="<f8",
        shape=direction.shape,
        byte_length=direction.nbytes,
        data_hash=array_data_hash(direction),
    )
    residual_binding = HipOutputBinding(
        dtype="<f8",
        shape=residual.shape,
        byte_length=residual.nbytes,
        data_hash=array_data_hash(residual),
    )
    jvp_binding = HipOutputBinding(
        dtype="<f8",
        shape=jvp.shape,
        byte_length=jvp.nbytes,
        data_hash=array_data_hash(jvp),
    )
    transfer_delta = HipResidualJvpTransferDelta(
        h2d_operation_attempt_count=(
            after.h2d_operation_attempt_count - before.h2d_operation_attempt_count
        ),
        h2d_operation_success_count=(
            after.h2d_operation_success_count - before.h2d_operation_success_count
        ),
        h2d_bytes_attempted=after.h2d_bytes_attempted - before.h2d_bytes_attempted,
        h2d_bytes_succeeded=after.h2d_bytes_succeeded - before.h2d_bytes_succeeded,
        d2h_operation_attempt_count=(
            after.d2h_operation_attempt_count - before.d2h_operation_attempt_count
        ),
        d2h_operation_success_count=(
            after.d2h_operation_success_count - before.d2h_operation_success_count
        ),
        d2h_bytes_attempted=after.d2h_bytes_attempted - before.d2h_bytes_attempted,
        d2h_bytes_succeeded=after.d2h_bytes_succeeded - before.d2h_bytes_succeeded,
        explicit_sync_attempt_count=(
            after.explicit_sync_attempt_count - before.explicit_sync_attempt_count
        ),
        explicit_sync_success_count=(
            after.explicit_sync_success_count - before.explicit_sync_success_count
        ),
        kernel_launch_attempt_count=(
            after.kernel_launch_attempt_count - before.kernel_launch_attempt_count
        ),
        kernel_launch_success_count=(
            after.kernel_launch_success_count - before.kernel_launch_success_count
        ),
    )
    seed = canonical_hash(
        {
            "context_id": context_id,
            "context_receipt_hash": context_receipt_hash,
            "foundation_context_receipt_hash": foundation_context_receipt_hash,
            "solver_artifact_hash": solver_artifact_hash,
            "direction_hash": direction_binding.data_hash,
            "residual_hash": residual_binding.data_hash,
            "jvp_hash": jvp_binding.data_hash,
        }
    )
    draft = HipResidualJvpResultReceipt(
        result_id=f"HipResidualJvp:{seed.removeprefix('sha256:')[:24]}",
        context_id=context_id,
        context_receipt_hash=context_receipt_hash,
        foundation_context_receipt_hash=foundation_context_receipt_hash,
        solver_artifact_hash=solver_artifact_hash,
        execution_evidence_kind=execution_evidence_kind,
        execution_plan=plan_binding,
        committed_state=state_binding,
        kernel_artifact=kernel_binding,
        direction=direction_binding,
        residual=residual_binding,
        jvp=jvp_binding,
        evaluation=HipResidualJvpEvaluation(
            residual_sign="internal_minus_external",
            jvp_semantics="linear_preassembled_K_times_v",
            load_factor_semantics="plan_global_load_unscaled_phase0",
            fused_launch=True,
            launch_count=1,
            dof_count=plan_binding.dof_count,
            nnz=plan_binding.nnz,
        ),
        complexity=HipResidualJvpComplexity(
            complexity_class="O(nnz)",
            row_visits=plan_binding.dof_count,
            csr_entry_visits=plan_binding.nnz,
            multiply_count=2 * plan_binding.nnz,
            load_subtraction_count=plan_binding.dof_count,
            dense_matrix_materialized=False,
            proof_scope="exact_single_fused_csr_residual_jvp_evaluation",
        ),
        transfer_delta=transfer_delta,
        native_hip_kernel_execution_proven=(
            execution_evidence_kind == "native_hip"
        ),
        result_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        result_hash=canonical_hash(
            _residual_jvp_result_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_residual_jvp_result_receipt(receipt)


def _residual_jvp_result_payload(
    receipt: HipResidualJvpResultReceipt, *, include_hash: bool
) -> dict[str, Any]:
    transfer = receipt.transfer_delta
    payload: dict[str, Any] = {
        "schema_version": HIP_RESIDUAL_JVP_RESULT_SCHEMA_VERSION,
        "capability_profile": "phase0_hip_canonical_csr_residual_jvp",
        "status": "evaluated",
        "result_id": receipt.result_id,
        "context_id": receipt.context_id,
        "actual_backend": _actual_backend(receipt.execution_evidence_kind),
        "execution_evidence_kind": receipt.execution_evidence_kind,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "input_bindings": {
            "context_receipt_hash": receipt.context_receipt_hash,
            "foundation_context_receipt_hash": (
                receipt.foundation_context_receipt_hash
            ),
            "solver_artifact_hash": receipt.solver_artifact_hash,
            "execution_plan": receipt.execution_plan.to_dict(),
            "committed_state": receipt.committed_state.to_dict(),
            "kernel_artifact": receipt.kernel_artifact.to_dict(),
            "direction": receipt.direction.to_dict(),
        },
        "evaluation": {
            "residual_definition": "K_times_u_minus_F",
            "jvp_definition": "K_times_v",
            "residual_sign": receipt.evaluation.residual_sign,
            "jvp_semantics": receipt.evaluation.jvp_semantics,
            "load_factor_semantics": receipt.evaluation.load_factor_semantics,
            "operator_storage": "canonical_full_dof_csr",
            "fused_residual_jvp": receipt.evaluation.fused_launch,
            "kernel_entrypoint": receipt.kernel_artifact.entrypoint,
            "kernel_launch_count": receipt.evaluation.launch_count,
            "dof_count": receipt.evaluation.dof_count,
            "direction_dof_count": receipt.direction.shape[0],
            "nnz_count": receipt.evaluation.nnz,
        },
        "outputs": {
            "layout": "C",
            "residual": receipt.residual.to_dict(),
            "jvp": receipt.jvp.to_dict(),
        },
        "transfer_delta": {
            "h2d_operation_attempt_count": transfer.h2d_operation_attempt_count,
            "h2d_operation_success_count": transfer.h2d_operation_success_count,
            "h2d_operation_count": transfer.h2d_operation_success_count,
            "h2d_bytes_attempted": transfer.h2d_bytes_attempted,
            "h2d_bytes_succeeded": transfer.h2d_bytes_succeeded,
            "h2d_bytes": transfer.h2d_bytes_succeeded,
            "d2h_operation_attempt_count": transfer.d2h_operation_attempt_count,
            "d2h_operation_success_count": transfer.d2h_operation_success_count,
            "d2h_operation_count": transfer.d2h_operation_success_count,
            "d2h_bytes_attempted": transfer.d2h_bytes_attempted,
            "d2h_bytes_succeeded": transfer.d2h_bytes_succeeded,
            "d2h_bytes": transfer.d2h_bytes_succeeded,
            "explicit_sync_attempt_count": transfer.explicit_sync_attempt_count,
            "explicit_sync_success_count": transfer.explicit_sync_success_count,
            "explicit_sync_count": transfer.explicit_sync_success_count,
            "kernel_launch_attempt_count": transfer.kernel_launch_attempt_count,
            "kernel_launch_success_count": transfer.kernel_launch_success_count,
            "kernel_launch_count": transfer.kernel_launch_success_count,
            "blocking_copy_count": 0,
            "fallback_count": 0,
        },
        "complexity": {
            "time_complexity": receipt.complexity.complexity_class,
            "auxiliary_device_space_complexity": "O(n_dof)",
            "csr_nonzero_visit_count": receipt.complexity.csr_entry_visits,
            "row_visit_count": receipt.complexity.row_visits,
            "multiply_count": receipt.complexity.multiply_count,
            "load_subtraction_count": (
                receipt.complexity.load_subtraction_count
            ),
            "dense_operator_materialized": (
                receipt.complexity.dense_matrix_materialized
            ),
            "proof_scope": receipt.complexity.proof_scope,
        },
        "claims": {
            "canonical_csr_operator_executed": True,
            "fused_single_kernel_launch_proven": True,
            "residual_jvp_evaluation_proven": True,
            "native_hip_kernel_execution_proven": (
                receipt.native_hip_kernel_execution_proven
            ),
            "device_constitutive_assembly_proven": False,
            "solver_ready": False,
            "newton_ready": False,
            "krylov_ready": False,
            "cpu_hip_global_parity_proven": False,
            "commercial_readiness": False,
        },
        "extensions": {},
    }
    if include_hash:
        payload["result_hash"] = receipt.result_hash
    return payload


def _parity_payload(
    receipt: HipResidualJvpParityReceipt, *, include_hash: bool
) -> dict[str, Any]:
    residual_abs_pass = (
        receipt.residual.max_abs_error <= receipt.residual.absolute_tolerance
    )
    residual_relative_pass = (
        receipt.residual.max_relative_error <= receipt.residual.relative_tolerance
    )
    jvp_abs_pass = receipt.jvp.max_abs_error <= receipt.jvp.absolute_tolerance
    jvp_relative_pass = (
        receipt.jvp.max_relative_error <= receipt.jvp.relative_tolerance
    )
    overall = receipt.residual.passed and receipt.jvp.passed
    payload: dict[str, Any] = {
        "schema_version": HIP_RESIDUAL_JVP_PARITY_SCHEMA_VERSION,
        "capability_profile": "phase0_hip_cpu_oracle_narrow_case_parity",
        "parity_id": receipt.parity_id,
        "status": receipt.status,
        "execution_evidence_kind": receipt.execution_evidence_kind,
        "evaluation_count": receipt.evaluation_count,
        "fallback_policy": "forbidden",
        "fallback_used": receipt.fallback_used,
        "input_bindings": {
            "residual_jvp_result_hash": receipt.result_hash,
            "context_receipt_hash": receipt.context_receipt_hash,
            "execution_plan_hash": receipt.execution_plan_hash,
            "operator_hash": receipt.operator_hash,
            "committed_state_hash": receipt.committed_state_hash,
            "kernel_artifact_hash": receipt.kernel_artifact_hash,
            "direction_hash": receipt.direction_hash,
            "evaluated_residual_hash": receipt.evaluated_residual_hash,
            "evaluated_jvp_hash": receipt.evaluated_jvp_hash,
        },
        "cpu_oracle": {
            "backend": "cpu_reference",
            "oracle_version": "engine-v2-cpu-canonical-csr-residual-jvp.v1",
            "evaluation_count": 1,
            "residual_definition": "K_times_u_minus_F",
            "jvp_definition": "K_times_v",
            "residual_hash": receipt.cpu_residual_hash,
            "jvp_hash": receipt.cpu_jvp_hash,
        },
        "metrics": {
            "residual_max_abs_error": receipt.residual.max_abs_error,
            "residual_max_relative_error": receipt.residual.max_relative_error,
            "jvp_max_abs_error": receipt.jvp.max_abs_error,
            "jvp_max_relative_error": receipt.jvp.max_relative_error,
            "cpu_residual_linf": receipt.cpu_residual_linf,
            "cpu_jvp_linf": receipt.cpu_jvp_linf,
        },
        "tolerances": {
            "residual_abs_tolerance": receipt.residual.absolute_tolerance,
            "residual_relative_tolerance": receipt.residual.relative_tolerance,
            "jvp_abs_tolerance": receipt.jvp.absolute_tolerance,
            "jvp_relative_tolerance": receipt.jvp.relative_tolerance,
            "relative_error_denominator_floor": (
                _RELATIVE_ERROR_DENOMINATOR_FLOOR
            ),
        },
        "checks": {
            "single_result_evaluation_bound": True,
            "cpu_oracle_replayed": True,
            "residual_abs_within_tolerance": residual_abs_pass,
            "residual_relative_within_tolerance": residual_relative_pass,
            "residual_pass": receipt.residual.passed,
            "jvp_abs_within_tolerance": jvp_abs_pass,
            "jvp_relative_within_tolerance": jvp_relative_pass,
            "jvp_pass": receipt.jvp.passed,
            "overall_pass": overall,
        },
        "case_scope": {
            "scope": "narrow_linear_static_case",
            "case_id": receipt.case_id,
            "model_ir_content_hash": receipt.model_ir_content_hash,
            "dof_count": receipt.dof_count,
            "nnz_count": receipt.nnz_count,
            "analysis_type": "linear_static",
            "constitutive_scope": "preassembled_linear_operator_only",
            "coverage_statement": (
                "one_model_one_state_one_direction_one_fused_evaluation"
            ),
        },
        "claims": {
            "narrow_case_result_cpu_parity_proven": overall,
            "native_hip_narrow_case_parity_proven": (
                overall and receipt.execution_evidence_kind == "native_hip"
            ),
            "cpu_hip_global_parity_proven": receipt.global_parity_proven,
            "constitutive_parity_proven": False,
            "solver_parity_proven": False,
            "newton_parity_proven": False,
            "krylov_parity_proven": False,
            "commercial_readiness": False,
        },
        "extensions": {},
    }
    if include_hash:
        payload["parity_receipt_hash"] = receipt.parity_hash
    return payload


def _validate_hash_bindings(receipt: HipOperatorContextReceipt) -> None:
    for path, value in (
        ("/capability_receipt_hash", receipt.capability_receipt_hash),
        ("/foundation_context_receipt_hash", receipt.foundation_context_receipt_hash),
        ("/solver_model_buffers/artifact_hash", receipt.solver_model_buffers.artifact_hash),
        ("/execution_plan/model_ir_content_hash", receipt.execution_plan.model_ir_content_hash),
        ("/execution_plan/plan_hash", receipt.execution_plan.plan_hash),
        ("/execution_plan/operator_hash", receipt.execution_plan.operator_hash),
        ("/execution_plan/pattern_hash", receipt.execution_plan.pattern_hash),
        ("/execution_plan/partition_hash", receipt.execution_plan.partition_hash),
        ("/committed_state/state_hash", receipt.committed_state.state_hash),
        ("/committed_state/displacement_hash", receipt.committed_state.displacement_hash),
        ("/committed_state/execution_plan_hash", receipt.committed_state.execution_plan_hash),
        ("/committed_state/operator_hash", receipt.committed_state.operator_hash),
        ("/kernel_artifact/artifact_receipt_hash", receipt.kernel_artifact.artifact_receipt_hash),
        ("/kernel_artifact/artifact_hash", receipt.kernel_artifact.artifact_hash),
        ("/kernel_artifact/source_hash", receipt.kernel_artifact.source_hash),
        ("/kernel_artifact/library_hash", receipt.kernel_artifact.library_hash),
        ("/kernel_artifact/abi_hash", receipt.kernel_artifact.abi_hash),
        ("/kernel_artifact/build_target_hash", receipt.kernel_artifact.build_target_hash),
    ):
        _require_hash(value, path)


def _validate_telemetry(telemetry: HipOperatorTelemetry) -> None:
    if not isinstance(telemetry, HipOperatorTelemetry):
        _fail("hip_operator_telemetry_type_invalid", "/telemetry")
    values = telemetry.to_dict()
    if any(isinstance(value, bool) or value < 0 for value in values.values()):
        _fail("hip_operator_telemetry_negative", "/telemetry")
    pairs = (
        (telemetry.allocation_attempt_count, telemetry.allocation_success_count),
        (telemetry.h2d_operation_attempt_count, telemetry.h2d_operation_success_count),
        (telemetry.d2h_operation_attempt_count, telemetry.d2h_operation_success_count),
        (telemetry.explicit_sync_attempt_count, telemetry.explicit_sync_success_count),
        (telemetry.kernel_launch_attempt_count, telemetry.kernel_launch_success_count),
        (telemetry.deallocation_attempt_count, telemetry.deallocation_success_count),
        (telemetry.h2d_bytes_attempted, telemetry.h2d_bytes_succeeded),
        (telemetry.d2h_bytes_attempted, telemetry.d2h_bytes_succeeded),
    )
    if any(success > attempt for attempt, success in pairs):
        _fail("hip_operator_telemetry_success_exceeds_attempt", "/telemetry")
    if telemetry.current_device_payload_bytes > telemetry.peak_device_payload_bytes:
        _fail("hip_operator_telemetry_payload_invalid", "/telemetry")


def _validate_device_view_shapes(receipt: HipOperatorContextReceipt) -> None:
    if tuple(view.name for view in receipt.device_views) != _VIEW_NAMES:
        _fail("hip_operator_device_views_invalid", "/device_views")
    dof_count = receipt.execution_plan.dof_count
    nnz = receipt.execution_plan.nnz
    expected = {
        "csr_row_ptr": ("<i4", (dof_count + 1,), 4 * (dof_count + 1)),
        "csr_col_ind": ("<i4", (nnz,), 4 * nnz),
        "csr_values": ("<f8", (nnz,), 8 * nnz),
        "load_vector": ("<f8", (dof_count,), 8 * dof_count),
        "committed_displacement": ("<f8", (dof_count,), 8 * dof_count),
        "direction": ("<f8", (dof_count,), 8 * dof_count),
        "residual_output": ("<f8", (dof_count,), 8 * dof_count),
        "jvp_output": ("<f8", (dof_count,), 8 * dof_count),
    }
    for view in receipt.device_views:
        dtype, shape, byte_length = expected[view.name]
        if (
            view.dtype != dtype
            or view.shape != shape
            or view.byte_length != byte_length
        ):
            _fail(
                "hip_operator_device_view_shape_mismatch",
                f"/device_views/{view.name}",
            )
    total_bytes = sum(view.byte_length for view in receipt.device_views)
    allocated_count = receipt.telemetry.allocation_success_count
    expected_peak = sum(
        view.byte_length for view in receipt.device_views[:allocated_count]
    )
    if receipt.telemetry.peak_device_payload_bytes != expected_peak:
        _fail("hip_operator_telemetry_payload_invalid", "/telemetry")
    if receipt.status in ("context_ready", "poisoned"):
        if receipt.telemetry.current_device_payload_bytes != total_bytes:
            _fail("hip_operator_telemetry_payload_invalid", "/telemetry")
    elif receipt.status == "context_closed":
        if receipt.telemetry.current_device_payload_bytes != 0:
            _fail("hip_operator_telemetry_payload_invalid", "/telemetry")


def _validate_ready_context_telemetry(
    receipt: HipOperatorContextReceipt,
) -> None:
    telemetry = receipt.telemetry
    launches = telemetry.kernel_launch_success_count
    dof_bytes = receipt.execution_plan.dof_count * np.dtype("<f8").itemsize
    initial_h2d_bytes = sum(
        view.byte_length
        for view in receipt.device_views
        if view.name in _INITIAL_UPLOAD_NAMES
    )
    expected = {
        "allocation_attempt_count": len(_VIEW_NAMES),
        "allocation_success_count": len(_VIEW_NAMES),
        "h2d_operation_attempt_count": len(_INITIAL_UPLOAD_NAMES) + launches,
        "h2d_operation_success_count": len(_INITIAL_UPLOAD_NAMES) + launches,
        "h2d_bytes_attempted": initial_h2d_bytes + launches * dof_bytes,
        "h2d_bytes_succeeded": initial_h2d_bytes + launches * dof_bytes,
        "d2h_operation_attempt_count": 2 * launches,
        "d2h_operation_success_count": 2 * launches,
        "d2h_bytes_attempted": 2 * launches * dof_bytes,
        "d2h_bytes_succeeded": 2 * launches * dof_bytes,
        "explicit_sync_attempt_count": 1 + launches,
        "explicit_sync_success_count": 1 + launches,
        "kernel_launch_attempt_count": launches,
        "kernel_launch_success_count": launches,
        "deallocation_attempt_count": 0,
        "deallocation_success_count": 0,
        "fallback_count": 0,
    }
    if any(getattr(telemetry, name) != value for name, value in expected.items()):
        _fail("hip_operator_ready_telemetry_invalid", "/telemetry")


def _direction_vector(value: Any, dof_count: int) -> np.ndarray:
    try:
        array = immutable_array(value, dtype="<f8")
    except Exception as exc:
        raise HipOperatorContextError(
            "hip_direction_invalid", "/direction", str(exc)
        ) from exc
    if array.shape != (dof_count,):
        raise HipOperatorContextError(
            "hip_direction_shape_invalid",
            "/direction/shape",
            f"Expected ({dof_count},), got {array.shape}.",
        )
    if not np.all(np.isfinite(array)):
        raise HipOperatorContextError(
            "hip_direction_nonfinite", "/direction", "Direction must be finite."
        )
    return array


def _validate_immutable_f64_vector(
    array: np.ndarray, dof_count: int, path: str
) -> None:
    if (
        not isinstance(array, np.ndarray)
        or array.dtype.str != "<f8"
        or array.shape != (dof_count,)
        or not array.flags.c_contiguous
        or not has_immutable_bytes_backing(array)
        or not np.all(np.isfinite(array))
    ):
        _fail("hip_residual_jvp_array_invalid", path)


def _csr_matvec(
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    result = np.empty(row_ptr.size - 1, dtype="<f8")
    for row in range(result.size):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        result[row] = np.dot(values[start:stop], vector[columns[start:stop]])
    return result


def _parity_metrics(
    actual: np.ndarray,
    expected: np.ndarray,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> HipParityMetrics:
    difference = np.abs(actual - expected)
    max_abs = float(np.max(difference, initial=0.0))
    component_denominator = np.maximum(
        np.abs(expected), _RELATIVE_ERROR_DENOMINATOR_FLOOR
    )
    max_relative = float(
        np.max(difference / component_denominator, initial=0.0)
    )
    passed = bool(
        max_abs <= absolute_tolerance and max_relative <= relative_tolerance
    )
    return HipParityMetrics(
        max_abs_error=max_abs,
        max_relative_error=max_relative,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        passed=passed,
    )


def _operator_context_id(
    foundation_context_id: str,
    plan: ExecutionPlan,
    committed_state: StateIR,
    kernel_binding: HipKernelArtifactBinding,
) -> str:
    digest = canonical_hash(
        {
            "foundation_context_id": foundation_context_id,
            "plan_hash": plan.plan_hash,
            "operator_hash": plan.operator_hash,
            "state_hash": committed_state.state_hash,
            "kernel_artifact_receipt_hash": kernel_binding.artifact_receipt_hash,
        }
    )
    return f"HipOperatorContext:{digest.removeprefix('sha256:')[:24]}"


def _actual_backend(
    kind: Literal["native_hip", "test_double"]
) -> Literal["hip_native", "test_double"]:
    return "hip_native" if kind == "native_hip" else "test_double"


def _operator_device_payload(device: HipDeviceContextIdentity) -> dict[str, Any]:
    return {
        "ordinal": device.ordinal,
        "name": device.name,
        "architecture": device.architecture,
        "runtime_version_raw": device.runtime_version_raw,
        "driver_version_raw": device.driver_version_raw,
        "total_memory_bytes": device.total_memory_bytes,
        "free_memory_bytes_before_upload": device.free_memory_bytes_before_upload,
        "free_memory_bytes_after_upload": device.free_memory_bytes_after_upload,
    }


def _view_by_name(
    views: tuple[HipOperatorDeviceView, ...], name: str
) -> HipOperatorDeviceView:
    return next(view for view in views if view.name == name)


def _nonnegative_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        _fail("hip_kernel_artifact_receipt_invalid", path)
    normalized = int(value)
    if normalized < minimum:
        _fail("hip_kernel_artifact_receipt_invalid", path)
    return normalized


def _string_tuple(
    value: Any, path: str, *, require_nonempty: bool
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("hip_kernel_artifact_receipt_invalid", path)
    result = tuple(value)
    if require_nonempty and not result:
        _fail("hip_kernel_artifact_receipt_invalid", path)
    if any(not isinstance(item, str) or not item for item in result):
        _fail("hip_kernel_artifact_receipt_invalid", path)
    return result


def _require_hash(value: Any, path: str) -> None:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hip_operator_hash_invalid", path)


def _bounded_detail(value: str) -> str:
    return (" ".join(value.split()) or "HIP operator context failure.")[:512]


def _open_failure_reason(exc: Exception) -> HipContextReason:
    code = getattr(exc, "code", "")
    if code == "hip_allocation_failed":
        stable_code = "hip_allocation_failed"
    elif code == "hip_copy_failed":
        stable_code = "hip_copy_failed"
    else:
        # The only remaining native operation in the open transaction is the
        # explicit post-upload synchronization.
        stable_code = "hip_sync_failed"
    return HipContextReason(stable_code, _bounded_detail(str(exc)))


def _reject_runtime_handle_terms(payload: Any) -> None:
    forbidden = ("pointer", "address", "stream", "handle")
    if _has_forbidden_key(payload, forbidden):
        _fail("hip_operator_runtime_handle_leak", "/")


def _has_forbidden_key(value: Any, forbidden: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in forbidden)
            or _has_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_forbidden_key(item, forbidden) for item in value)
    return False


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
        raise HipOperatorContextError(
            f"{prefix}_schema_invalid", path, error.message
        )


def _fail(code: str, path: str, message: str | None = None) -> None:
    raise HipOperatorContextError(code, path, message or "Contract invariant failed.")


@lru_cache(maxsize=1)
def _context_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_operator_context_v1.schema.json")


@lru_cache(maxsize=1)
def _result_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_residual_jvp_result_v1.schema.json")


@lru_cache(maxsize=1)
def _parity_schema_validator() -> Draft202012Validator:
    return _schema_validator("hip_residual_jvp_parity_v1.schema.json")


def _schema_validator(name: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parents[3] / "schemas" / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "HIP_OPERATOR_CONTEXT_CAPABILITY_PROFILE",
    "HIP_OPERATOR_CONTEXT_SCHEMA_VERSION",
    "HIP_RESIDUAL_JVP_PARITY_SCHEMA_VERSION",
    "HIP_RESIDUAL_JVP_RESULT_SCHEMA_VERSION",
    "HipKernelArtifactBinding",
    "HipOperatorContextError",
    "HipOperatorContextOpenResult",
    "HipOperatorContextReceipt",
    "HipOperatorExecutionContext",
    "HipResidualJvpKernelProtocol",
    "HipResidualJvpParityReceipt",
    "HipResidualJvpResult",
    "HipResidualJvpResultReceipt",
    "open_hip_operator_execution_context",
    "validate_hip_operator_context_receipt",
    "validate_hip_residual_jvp_parity_receipt",
    "validate_hip_residual_jvp_result",
    "validate_hip_residual_jvp_result_receipt",
    "verify_hip_residual_jvp_parity",
]
