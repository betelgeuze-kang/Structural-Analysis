"""Bound-runtime host-transfer audit for one HIP FGMRES recurrence lineage.

The audit window starts while the canonical predecessor owner is ready, before
its first enqueue, and ends after the global recurrence terminal fence.  The
same counter then verifies the completion export's three blocking D2H calls.

This is not a process-wide ROCm trace.  Fresh native bindings, external DMA,
third-party libraries, and hostile same-process mutation remain outside the
claim boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import threading
from typing import Any, Literal
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.backends.hip.transfer_audit_v1 import (
    HipBoundCopyAuditSnapshotV1,
    HipBoundCopyCounterV1,
    _BoundCopyAuditCaptureV1,
    _capture_bound_copy_audit_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_canonical_predecessor_v1 import (
    HipFgmresCanonicalPredecessorExecutionContextV1,
)
from .fgmres_completion_export_v1 import (
    HipFgmresCompletionExportExecutionContextV1,
    HipFgmresCompletionExportResultV1,
    open_hip_fgmres_completion_export_context_v1,
    validate_hip_fgmres_completion_export_result_v1,
)
from .fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    HipFgmresGlobalRecurrenceExecutionContextV1,
    validate_hip_fgmres_global_recurrence_completion_capability_v1,
)
from .fgmres_sealed_checkpoint_transaction_v1 import (
    HipFgmresSealedCheckpointTransactionExecutionContextV1,
)


HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-iteration-host-transfer-audit.v1"
)
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1 = (
    "phase0_bound_runtime_canonical_to_global_fence_copy_audit"
)
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1 = "engine_v2_bound_runtime_recurrence_program_copy_zero_and_fenced_export_non_promoting"
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1 = (
    "exact_engine_v2_bound_context_runtime_only"
)
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_START_BOUNDARY_V1 = (
    "canonical_context_ready_before_predecessor_enqueue"
)
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_FENCE_BOUNDARY_V1 = (
    "global_recurrence_fenced_before_completion_export_open"
)
HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EXPORT_BOUNDARY_V1 = (
    "completion_export_returned_after_three_blocking_d2h_calls"
)

_SCHEMA_RESOURCE = "hip_fgmres_iteration_host_transfer_audit_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64


class HipFgmresIterationHostTransferAuditV1Error(RuntimeError):
    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresIterationHostTransferAuditExecutionContextV1
        | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresHostTransferDeltaV1:
    attempt_count: int
    success_count: int
    failure_count: int
    bytes_attempted: int
    bytes_succeeded: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresHostTransferPhaseV1:
    sequence_delta: int
    h2d_async: HipFgmresHostTransferDeltaV1
    d2h_async: HipFgmresHostTransferDeltaV1
    d2h_blocking: HipFgmresHostTransferDeltaV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_delta": self.sequence_delta,
            "h2d_async": self.h2d_async.to_dict(),
            "d2h_async": self.d2h_async.to_dict(),
            "d2h_blocking": self.d2h_blocking.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditBindingsV1:
    canonical_context_id: str
    canonical_open_receipt_hash: str
    canonical_fenced_receipt_hash: str
    sealed_checkpoint_context_id: str
    sealed_checkpoint_receipt_hash: str
    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    global_full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    architecture: str
    device_ordinal: int
    runtime_scope: Literal["exact_engine_v2_bound_context_runtime_only"]
    native_loader_bound_runtime: bool
    stream_identity_serialized: Literal[False] = False
    runtime_identity_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditWindowV1:
    start_boundary: Literal["canonical_context_ready_before_predecessor_enqueue"]
    fence_boundary: Literal["global_recurrence_fenced_before_completion_export_open"]
    export_boundary: Literal[
        "completion_export_returned_after_three_blocking_d2h_calls"
    ]
    start_sequence: int
    fence_sequence: int
    export_sequence: int
    start_in_flight_count: Literal[0]
    fence_in_flight_count: Literal[0]
    export_in_flight_count: Literal[0]
    recurrence_program: HipFgmresHostTransferPhaseV1
    completion_export: HipFgmresHostTransferPhaseV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_boundary": self.start_boundary,
            "fence_boundary": self.fence_boundary,
            "export_boundary": self.export_boundary,
            "start_sequence": self.start_sequence,
            "fence_sequence": self.fence_sequence,
            "export_sequence": self.export_sequence,
            "start_in_flight_count": self.start_in_flight_count,
            "fence_in_flight_count": self.fence_in_flight_count,
            "export_in_flight_count": self.export_in_flight_count,
            "recurrence_program": self.recurrence_program.to_dict(),
            "completion_export": self.completion_export.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditDimensionsV1:
    free_dof_count: int
    maximum_restart_count: int
    full_program_launch_count: int
    solution_byte_count: int
    true_residual_byte_count: int
    solve_record_byte_count: int
    total_export_byte_count: int
    exported_buffer_count: Literal[3] = 3

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditClaimsV1:
    canonical_to_global_fence_lineage_bound: Literal[True]
    exact_bound_runtime_copy_counter_bound: Literal[True]
    recurrence_program_bound_runtime_copy_attempt_zero: Literal[True]
    post_fence_exact_three_blocking_d2h: Literal[True]
    post_fence_export_byte_count_exact: Literal[True]
    same_runtime_device_stream_lineage_bound: Literal[True]
    process_wide_host_transfer_zero_proven: Literal[False] = False
    raw_cdll_or_fresh_binding_transfer_zero_proven: Literal[False] = False
    hostile_same_process_interference_excluded: Literal[False] = False
    synchronization_zero_proven: Literal[False] = False
    host_scheduling_zero_proven: Literal[False] = False
    full_solver_setup_transfer_zero_proven: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    pre_window_async_copy_completion_or_device_dma_activity_zero_proven: Literal[
        False
    ] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    numerical_parity_verified: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditReceiptV1:
    status: Literal["exported"]
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresIterationHostTransferAuditBindingsV1
    window: HipFgmresIterationHostTransferAuditWindowV1
    dimensions: HipFgmresIterationHostTransferAuditDimensionsV1
    claims: HipFgmresIterationHostTransferAuditClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditResultV1:
    receipt: HipFgmresIterationHostTransferAuditReceiptV1
    completion_export_context: HipFgmresCompletionExportExecutionContextV1
    completion_export_result: HipFgmresCompletionExportResultV1

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_iteration_host_transfer_audit_result_v1(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresIterationHostTransferAuditOpenResultV1:
    context: HipFgmresIterationHostTransferAuditExecutionContextV1

    @property
    def ready(self) -> bool:
        return self.context.ready


class HipFgmresIterationHostTransferAuditExecutionContextV1:
    def __init__(
        self,
        canonical: HipFgmresCanonicalPredecessorExecutionContextV1,
        capture: _BoundCopyAuditCaptureV1,
        canonical_open_receipt_hash: str,
    ) -> None:
        self._lock = threading.RLock()
        self._canonical = canonical
        self._runtime = capture.runtime
        self._start_capture = capture
        self._canonical_open_receipt_hash = canonical_open_receipt_hash
        self._state: Literal[
            "context_ready", "export_in_progress", "exported", "poisoned", "closed"
        ] = "context_ready"
        self._active_operation = False
        self._export_context: HipFgmresCompletionExportExecutionContextV1 | None = None
        self._global_context: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._completion_capability: (
            HipFgmresGlobalRecurrenceCompletionCapabilityV1 | None
        ) = None
        self._result: HipFgmresIterationHostTransferAuditResultV1 | None = None

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._state == "context_ready" and not self._active_operation

    @property
    def result(self) -> HipFgmresIterationHostTransferAuditResultV1 | None:
        with self._lock:
            return self._result if self._state == "exported" else None

    def export_completion_buffers(
        self,
        global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
        completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> HipFgmresIterationHostTransferAuditResultV1:
        with self._lock:
            if self._result is not None and self._state == "exported":
                if (
                    global_context is not self._global_context
                    or completion_capability is not self._completion_capability
                ):
                    _fail(
                        "hip_fgmres_iteration_host_transfer_audit_cached_input_changed",
                        "/export/input",
                        cleanup_owner=self,
                    )
                return self._result
            if self._active_operation:
                _fail(
                    "hip_fgmres_iteration_host_transfer_audit_reentrant",
                    "/export/operation",
                    cleanup_owner=self,
                )
            if self._state != "context_ready":
                _fail(
                    "hip_fgmres_iteration_host_transfer_audit_state_invalid",
                    "/export/state",
                    cleanup_owner=self,
                )
            self._active_operation = True
            self._state = "export_in_progress"
            try:
                lineage = self._validate_fenced_lineage(
                    global_context,
                    completion_capability,
                )
                fence_capture = _capture_bound_copy_audit_v1(self._runtime)
                self._require_same_binding(fence_capture, "/window/fence")
                recurrence_phase = _phase_delta(
                    self._start_capture.snapshot,
                    fence_capture.snapshot,
                    path="/window/recurrence_program",
                )
                if not _phase_is_zero(recurrence_phase):
                    _fail(
                        "hip_fgmres_iteration_host_transfer_audit_copy_observed",
                        "/window/recurrence_program",
                        cleanup_owner=self,
                    )
                opened = open_hip_fgmres_completion_export_context_v1(
                    global_context,
                    completion_capability,
                )
                self._export_context = opened.context
                export_result = opened.context.export_completion_buffers()
                validate_hip_fgmres_completion_export_result_v1(
                    export_result,
                    expected_context=opened.context,
                )
                export_capture = _capture_bound_copy_audit_v1(self._runtime)
                self._require_same_binding(export_capture, "/window/export")
                export_phase = _phase_delta(
                    fence_capture.snapshot,
                    export_capture.snapshot,
                    path="/window/completion_export",
                )
                _validate_export_phase(export_phase, export_result)
                receipt = self._build_receipt(
                    lineage=lineage,
                    fence_capture=fence_capture,
                    export_capture=export_capture,
                    recurrence_phase=recurrence_phase,
                    export_phase=export_phase,
                    export_result=export_result,
                )
                result = HipFgmresIterationHostTransferAuditResultV1(
                    receipt=receipt,
                    completion_export_context=opened.context,
                    completion_export_result=export_result,
                )
                self._global_context = global_context
                self._completion_capability = completion_capability
                self._result = result
                self._state = "exported"
                validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
                    result,
                    expected_context=self,
                )
                return result
            except BaseException as exc:
                self._state = "poisoned"
                if not isinstance(exc, Exception):
                    raise
                if (
                    isinstance(exc, HipFgmresIterationHostTransferAuditV1Error)
                    and exc.cleanup_owner is self
                ):
                    raise
                raise HipFgmresIterationHostTransferAuditV1Error(
                    "hip_fgmres_iteration_host_transfer_audit_export_failed",
                    "/export",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            finally:
                self._active_operation = False

    def close(self) -> None:
        with self._lock:
            if self._state == "closed":
                return
            if self._active_operation:
                _fail(
                    "hip_fgmres_iteration_host_transfer_audit_operation_active",
                    "/close",
                    cleanup_owner=self,
                )
            if self._export_context is not None and not self._export_context.closed:
                self._export_context.close()
            self._state = "closed"
            _release_runtime_audit_owner(self._runtime, self)

    def _validate_fenced_lineage(
        self,
        global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
        completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> tuple[Any, ...]:
        if type(global_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_global_invalid",
                "/global_context",
                cleanup_owner=self,
            )
        validate_hip_fgmres_global_recurrence_completion_capability_v1(
            completion_capability,
            expected_context=global_context,
        )
        global_receipt = global_context.receipt()
        if global_receipt.status != "recurrence_fenced":
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_global_not_fenced",
                "/global_context/status",
                cleanup_owner=self,
            )
        sealed = global_context._require_sealed()
        if type(sealed) is not HipFgmresSealedCheckpointTransactionExecutionContextV1:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_sealed_invalid",
                "/sealed_context",
                cleanup_owner=self,
            )
        canonical = sealed._require_canonical()
        if canonical is not self._canonical:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_canonical_changed",
                "/canonical_context",
                cleanup_owner=self,
            )
        canonical_receipt = canonical.receipt()
        sealed_receipt = sealed.receipt()
        binding = global_context._require_binding()
        live = canonical._require_live()
        if (
            binding.runtime is not self._runtime
            or live._runtime is not self._runtime
            or binding.loaded_runtime is not live._loaded_runtime
            or binding.stream is not live._stream
            or binding.stream_pointer != live._stream_pointer_snapshot
            or binding.device_ordinal != live._device_ordinal
            or binding.architecture != live._architecture
            or global_receipt.actual_backend != canonical.receipt().actual_backend
            or global_receipt.bindings.canonical_predecessor_context_id
            != canonical_receipt.context_id
            or global_receipt.bindings.sealed_checkpoint_context_id
            != sealed_receipt.context_id
            or global_receipt.bindings.sealed_checkpoint_receipt_hash
            != sealed_receipt.receipt_hash
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_lineage_changed",
                "/lineage",
                cleanup_owner=self,
            )
        if (
            global_receipt.actual_backend == "hip"
            and not self._start_capture.native_loader_bound
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_native_binding_invalid",
                "/runtime/native_binding",
                cleanup_owner=self,
            )
        return (
            canonical_receipt,
            sealed_receipt,
            global_receipt,
            binding,
        )

    def _require_same_binding(
        self,
        capture: _BoundCopyAuditCaptureV1,
        path: str,
    ) -> None:
        if (
            capture.runtime is not self._runtime
            or capture.state is not self._start_capture.state
            or capture.binding_identity != self._start_capture.binding_identity
            or capture.native_loader_bound != self._start_capture.native_loader_bound
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_counter_changed",
                path,
                cleanup_owner=self,
            )

    def _build_receipt(
        self,
        *,
        lineage: tuple[Any, ...],
        fence_capture: _BoundCopyAuditCaptureV1,
        export_capture: _BoundCopyAuditCaptureV1,
        recurrence_phase: HipFgmresHostTransferPhaseV1,
        export_phase: HipFgmresHostTransferPhaseV1,
        export_result: HipFgmresCompletionExportResultV1,
    ) -> HipFgmresIterationHostTransferAuditReceiptV1:
        canonical_receipt, sealed_receipt, global_receipt, _binding = lineage
        global_bindings = global_receipt.bindings
        export_receipt = export_result.receipt
        dimensions = export_receipt.dimensions
        bindings = HipFgmresIterationHostTransferAuditBindingsV1(
            canonical_context_id=canonical_receipt.context_id,
            canonical_open_receipt_hash=self._canonical_open_receipt_hash,
            canonical_fenced_receipt_hash=canonical_receipt.receipt_hash,
            sealed_checkpoint_context_id=sealed_receipt.context_id,
            sealed_checkpoint_receipt_hash=sealed_receipt.receipt_hash,
            global_context_id=global_receipt.context_id,
            global_receipt_hash=global_receipt.receipt_hash,
            completion_receipt_hash=export_receipt.bindings.completion_receipt_hash,
            completion_export_context_id=export_receipt.context_id,
            completion_export_receipt_hash=export_receipt.receipt_hash,
            completion_export_payload_hash=export_result.payload_hash,
            recurrence_plan_hash=global_bindings.recurrence_plan_hash,
            recurrence_kernel_abi_hash=global_bindings.recurrence_kernel_abi_hash,
            combined_recurrence_abi_hash=global_bindings.combined_recurrence_abi_hash,
            kernel_identity_hash=global_bindings.kernel_identity_hash,
            kernel_source_sha256=global_bindings.kernel_source_sha256,
            global_full_schedule_hash=global_bindings.global_full_schedule_hash,
            sealed_prefix_schedule_hash=global_bindings.sealed_prefix_schedule_hash,
            continuation_schedule_hash=global_bindings.continuation_schedule_hash,
            direct_generation_binding_hash=(
                global_bindings.direct_generation_binding_hash
            ),
            physical_projection_hash=global_bindings.physical_projection_hash,
            architecture=global_bindings.architecture,
            device_ordinal=global_bindings.device_ordinal,
            runtime_scope=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1,
            native_loader_bound_runtime=(
                global_receipt.actual_backend == "hip"
                and self._start_capture.native_loader_bound
            ),
        )
        window = HipFgmresIterationHostTransferAuditWindowV1(
            start_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_START_BOUNDARY_V1,
            fence_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_FENCE_BOUNDARY_V1,
            export_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EXPORT_BOUNDARY_V1,
            start_sequence=self._start_capture.snapshot.sequence,
            fence_sequence=fence_capture.snapshot.sequence,
            export_sequence=export_capture.snapshot.sequence,
            start_in_flight_count=0,
            fence_in_flight_count=0,
            export_in_flight_count=0,
            recurrence_program=recurrence_phase,
            completion_export=export_phase,
        )
        draft = HipFgmresIterationHostTransferAuditReceiptV1(
            status="exported",
            context_id=canonical_hash(
                {
                    "profile": (
                        HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1
                    ),
                    "canonical_context_id": canonical_receipt.context_id,
                    "canonical_open_receipt_hash": self._canonical_open_receipt_hash,
                    "global_context_id": global_receipt.context_id,
                    "global_receipt_hash": global_receipt.receipt_hash,
                    "completion_export_context_id": export_receipt.context_id,
                }
            ),
            evidence_scope=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1,
            actual_backend=global_receipt.actual_backend,
            promotion_eligible=False,
            bindings=bindings,
            window=window,
            dimensions=HipFgmresIterationHostTransferAuditDimensionsV1(
                free_dof_count=dimensions.free_dof_count,
                maximum_restart_count=dimensions.maximum_restart_count,
                full_program_launch_count=(
                    global_receipt.dimensions.full_program_launch_count
                ),
                solution_byte_count=dimensions.solution_byte_count,
                true_residual_byte_count=dimensions.true_residual_byte_count,
                solve_record_byte_count=dimensions.solve_record_byte_count,
                total_export_byte_count=dimensions.total_export_byte_count,
            ),
            claims=HipFgmresIterationHostTransferAuditClaimsV1(
                canonical_to_global_fence_lineage_bound=True,
                exact_bound_runtime_copy_counter_bound=True,
                recurrence_program_bound_runtime_copy_attempt_zero=True,
                post_fence_exact_three_blocking_d2h=True,
                post_fence_export_byte_count_exact=True,
                same_runtime_device_stream_lineage_bound=True,
            ),
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )
        return validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(receipt)


_RUNTIME_AUDIT_OWNERS_LOCK = threading.RLock()
_RUNTIME_AUDIT_OWNERS: weakref.WeakKeyDictionary[Any, weakref.ReferenceType[Any]] = (
    weakref.WeakKeyDictionary()
)


def open_hip_fgmres_iteration_host_transfer_audit_v1(
    canonical_context: HipFgmresCanonicalPredecessorExecutionContextV1,
) -> HipFgmresIterationHostTransferAuditOpenResultV1:
    if type(canonical_context) is not HipFgmresCanonicalPredecessorExecutionContextV1:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_canonical_invalid",
            "/canonical_context",
        )
    # The receipt, idle authority, start counter snapshot, and runtime-owner
    # reservation form one boundary.  Holding the canonical lock prevents a
    # concurrent first enqueue from moving the state before the snapshot while
    # the serialized boundary still claims "before predecessor enqueue".
    with canonical_context._lock:
        canonical_receipt = canonical_context.receipt()
        if canonical_receipt.status != "context_ready":
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_canonical_not_ready",
                "/canonical_context/status",
            )
        canonical_context._validate_authority(require_idle_kernel=True)
        live = canonical_context._require_live()
        runtime = live._runtime
        capture = _capture_bound_copy_audit_v1(runtime)
        if capture.snapshot.total_in_flight_count != 0:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_copy_inflight",
                "/window/start",
            )
        if (
            canonical_receipt.actual_backend == "hip"
            and not capture.native_loader_bound
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_native_binding_invalid",
                "/runtime/native_binding",
            )
        if canonical_context.receipt() != canonical_receipt:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_start_boundary_changed",
                "/window/start",
            )
        context = HipFgmresIterationHostTransferAuditExecutionContextV1(
            canonical_context,
            capture,
            canonical_receipt.receipt_hash,
        )
        _reserve_runtime_audit_owner(runtime, context)
    return HipFgmresIterationHostTransferAuditOpenResultV1(context=context)


def validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(
    receipt: HipFgmresIterationHostTransferAuditReceiptV1,
    *,
    expected_context: HipFgmresIterationHostTransferAuditExecutionContextV1
    | None = None,
) -> HipFgmresIterationHostTransferAuditReceiptV1:
    if type(receipt) is not HipFgmresIterationHostTransferAuditReceiptV1:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_receipt_invalid",
            "/receipt",
        )
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload), key=lambda row: list(row.path)
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_schema_invalid",
            path or "/",
            first.message,
        )
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_hash_invalid",
            "/receipt_hash",
        )
    _validate_receipt_semantics(receipt)
    if expected_context is not None:
        if (
            type(expected_context)
            is not HipFgmresIterationHostTransferAuditExecutionContextV1
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_context_invalid",
                "/context",
            )
        with expected_context._lock:
            result = expected_context._result
            if (
                result is None
                or result.receipt is not receipt
                or expected_context._state not in {"exported", "closed"}
            ):
                _fail(
                    "hip_fgmres_iteration_host_transfer_audit_receipt_changed",
                    "/receipt",
                    cleanup_owner=expected_context,
                )
    return receipt


def validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
    result: HipFgmresIterationHostTransferAuditResultV1,
    *,
    expected_context: HipFgmresIterationHostTransferAuditExecutionContextV1
    | None = None,
) -> HipFgmresIterationHostTransferAuditResultV1:
    if type(result) is not HipFgmresIterationHostTransferAuditResultV1:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_result_invalid",
            "/result",
        )
    validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(
        result.receipt,
        expected_context=expected_context,
    )
    validate_hip_fgmres_completion_export_result_v1(
        result.completion_export_result,
        expected_context=result.completion_export_context,
    )
    export = result.completion_export_result
    bindings = result.receipt.bindings
    export_bindings = export.receipt.bindings
    if (
        bindings.completion_export_context_id != export.receipt.context_id
        or bindings.completion_export_receipt_hash != export.receipt.receipt_hash
        or bindings.completion_export_payload_hash != export.payload_hash
        or result.receipt.actual_backend != export.receipt.actual_backend
        or bindings.global_context_id != export_bindings.global_context_id
        or bindings.global_receipt_hash != export_bindings.global_receipt_hash
        or bindings.completion_receipt_hash != export_bindings.completion_receipt_hash
        or bindings.recurrence_plan_hash != export_bindings.recurrence_plan_hash
        or bindings.recurrence_kernel_abi_hash
        != export_bindings.recurrence_kernel_abi_hash
        or bindings.combined_recurrence_abi_hash
        != export_bindings.combined_recurrence_abi_hash
        or bindings.kernel_identity_hash != export_bindings.kernel_identity_hash
        or bindings.kernel_source_sha256 != export_bindings.kernel_source_sha256
        or bindings.continuation_schedule_hash
        != export_bindings.continuation_schedule_hash
        or bindings.direct_generation_binding_hash
        != export_bindings.direct_generation_binding_hash
        or bindings.physical_projection_hash != export_bindings.physical_projection_hash
        or bindings.architecture != export_bindings.architecture
        or bindings.device_ordinal != export_bindings.device_ordinal
        or result.receipt.dimensions.free_dof_count
        != export.receipt.dimensions.free_dof_count
        or result.receipt.dimensions.maximum_restart_count
        != export.receipt.dimensions.maximum_restart_count
        or result.receipt.dimensions.solution_byte_count
        != export.receipt.dimensions.solution_byte_count
        or result.receipt.dimensions.true_residual_byte_count
        != export.receipt.dimensions.true_residual_byte_count
        or result.receipt.dimensions.solve_record_byte_count
        != export.receipt.dimensions.solve_record_byte_count
        or result.receipt.dimensions.total_export_byte_count
        != export.receipt.dimensions.total_export_byte_count
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_export_binding_invalid",
            "/result/completion_export",
            cleanup_owner=expected_context,
        )
    if expected_context is not None:
        with expected_context._lock:
            if (
                expected_context._result is not result
                or expected_context._export_context
                is not result.completion_export_context
            ):
                _fail(
                    "hip_fgmres_iteration_host_transfer_audit_result_changed",
                    "/result",
                    cleanup_owner=expected_context,
                )
    return result


def _phase_delta(
    start: HipBoundCopyAuditSnapshotV1,
    end: HipBoundCopyAuditSnapshotV1,
    *,
    path: str,
) -> HipFgmresHostTransferPhaseV1:
    if start.total_in_flight_count != 0 or end.total_in_flight_count != 0:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_copy_inflight",
            path,
        )
    if end.sequence < start.sequence:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_counter_regressed",
            f"{path}/sequence",
        )
    return HipFgmresHostTransferPhaseV1(
        sequence_delta=end.sequence - start.sequence,
        h2d_async=_counter_delta(start.h2d_async, end.h2d_async, path=path),
        d2h_async=_counter_delta(start.d2h_async, end.d2h_async, path=path),
        d2h_blocking=_counter_delta(
            start.d2h_blocking,
            end.d2h_blocking,
            path=path,
        ),
    )


def _counter_delta(
    start: HipBoundCopyCounterV1,
    end: HipBoundCopyCounterV1,
    *,
    path: str,
) -> HipFgmresHostTransferDeltaV1:
    names = (
        "attempt_count",
        "success_count",
        "failure_count",
        "bytes_attempted",
        "bytes_succeeded",
    )
    values = tuple(getattr(end, name) - getattr(start, name) for name in names)
    if any(value < 0 for value in values):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_counter_regressed",
            path,
        )
    delta = HipFgmresHostTransferDeltaV1(*values)
    if delta.success_count + delta.failure_count != delta.attempt_count:
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_counter_invalid",
            path,
        )
    return delta


def _phase_is_zero(phase: HipFgmresHostTransferPhaseV1) -> bool:
    return phase.sequence_delta == 0 and all(
        all(value == 0 for value in row.to_dict().values())
        for row in (phase.h2d_async, phase.d2h_async, phase.d2h_blocking)
    )


def _validate_export_phase(
    phase: HipFgmresHostTransferPhaseV1,
    export: HipFgmresCompletionExportResultV1,
) -> None:
    expected_bytes = export.receipt.dimensions.total_export_byte_count
    blocking = phase.d2h_blocking
    if (
        not _delta_is_zero(phase.h2d_async)
        or not _delta_is_zero(phase.d2h_async)
        or phase.sequence_delta != 6
        or blocking.attempt_count != 3
        or blocking.success_count != 3
        or blocking.failure_count != 0
        or blocking.bytes_attempted != expected_bytes
        or blocking.bytes_succeeded != expected_bytes
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_export_counter_invalid",
            "/window/completion_export",
        )


def _delta_is_zero(delta: HipFgmresHostTransferDeltaV1) -> bool:
    return all(value == 0 for value in delta.to_dict().values())


def _validate_receipt_semantics(
    receipt: HipFgmresIterationHostTransferAuditReceiptV1,
) -> None:
    if (
        type(receipt.bindings) is not HipFgmresIterationHostTransferAuditBindingsV1
        or type(receipt.window) is not HipFgmresIterationHostTransferAuditWindowV1
        or type(receipt.dimensions)
        is not HipFgmresIterationHostTransferAuditDimensionsV1
        or type(receipt.claims) is not HipFgmresIterationHostTransferAuditClaimsV1
        or type(receipt.status) is not str
        or type(receipt.context_id) is not str
        or type(receipt.evidence_scope) is not str
        or type(receipt.actual_backend) is not str
        or type(receipt.promotion_eligible) is not bool
        or type(receipt.receipt_hash) is not str
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_type_invalid",
            "/receipt",
        )
    window = receipt.window
    dimensions = receipt.dimensions
    claims = receipt.claims
    bindings = receipt.bindings
    _validate_phase_types(window.recurrence_program, "/window/recurrence_program")
    _validate_phase_types(window.completion_export, "/window/completion_export")
    binding_string_values = (
        bindings.canonical_context_id,
        bindings.canonical_open_receipt_hash,
        bindings.canonical_fenced_receipt_hash,
        bindings.sealed_checkpoint_context_id,
        bindings.sealed_checkpoint_receipt_hash,
        bindings.global_context_id,
        bindings.global_receipt_hash,
        bindings.completion_receipt_hash,
        bindings.completion_export_context_id,
        bindings.completion_export_receipt_hash,
        bindings.completion_export_payload_hash,
        bindings.recurrence_plan_hash,
        bindings.recurrence_kernel_abi_hash,
        bindings.combined_recurrence_abi_hash,
        bindings.kernel_identity_hash,
        bindings.kernel_source_sha256,
        bindings.global_full_schedule_hash,
        bindings.sealed_prefix_schedule_hash,
        bindings.continuation_schedule_hash,
        bindings.direct_generation_binding_hash,
        bindings.physical_projection_hash,
        bindings.architecture,
        bindings.runtime_scope,
        window.start_boundary,
        window.fence_boundary,
        window.export_boundary,
    )
    if any(type(value) is not str for value in binding_string_values):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_type_invalid",
            "/receipt/string",
        )
    integer_values = (
        window.start_sequence,
        window.fence_sequence,
        window.export_sequence,
        window.start_in_flight_count,
        window.fence_in_flight_count,
        window.export_in_flight_count,
        bindings.device_ordinal,
        dimensions.free_dof_count,
        dimensions.maximum_restart_count,
        dimensions.full_program_launch_count,
        dimensions.solution_byte_count,
        dimensions.true_residual_byte_count,
        dimensions.solve_record_byte_count,
        dimensions.total_export_byte_count,
        dimensions.exported_buffer_count,
    )
    if any(type(value) is not int or value < 0 for value in integer_values):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_type_invalid",
            "/receipt/integer",
        )
    if (
        type(bindings.native_loader_bound_runtime) is not bool
        or type(bindings.stream_identity_serialized) is not bool
        or type(bindings.runtime_identity_serialized) is not bool
        or any(
            type(getattr(claims, name)) is not bool
            for name in claims.__dataclass_fields__
        )
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_type_invalid",
            "/receipt/boolean",
        )
    if (
        receipt.status != "exported"
        or receipt.promotion_eligible is not False
        or receipt.evidence_scope
        != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1
        or window.start_boundary
        != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_START_BOUNDARY_V1
        or window.fence_boundary
        != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_FENCE_BOUNDARY_V1
        or window.export_boundary
        != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EXPORT_BOUNDARY_V1
        or window.start_in_flight_count != 0
        or window.fence_in_flight_count != 0
        or window.export_in_flight_count != 0
        or window.fence_sequence - window.start_sequence
        != window.recurrence_program.sequence_delta
        or window.export_sequence - window.fence_sequence
        != window.completion_export.sequence_delta
        or not _phase_is_zero(window.recurrence_program)
        or dimensions.solution_byte_count != 8 * dimensions.free_dof_count
        or dimensions.true_residual_byte_count != 8 * dimensions.free_dof_count
        or dimensions.solve_record_byte_count
        != 192 + 72 * dimensions.maximum_restart_count
        or dimensions.total_export_byte_count
        != dimensions.solution_byte_count
        + dimensions.true_residual_byte_count
        + dimensions.solve_record_byte_count
        or dimensions.exported_buffer_count != 3
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_semantics_invalid",
            "/receipt",
        )
    dummy_export_dimensions = dimensions.total_export_byte_count
    phase = window.completion_export
    if (
        not _delta_is_zero(phase.h2d_async)
        or not _delta_is_zero(phase.d2h_async)
        or phase.sequence_delta != 6
        or phase.d2h_blocking.attempt_count != 3
        or phase.d2h_blocking.success_count != 3
        or phase.d2h_blocking.failure_count != 0
        or phase.d2h_blocking.bytes_attempted != dummy_export_dimensions
        or phase.d2h_blocking.bytes_succeeded != dummy_export_dimensions
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_semantics_invalid",
            "/window/completion_export",
        )
    true_claims = (
        claims.canonical_to_global_fence_lineage_bound,
        claims.exact_bound_runtime_copy_counter_bound,
        claims.recurrence_program_bound_runtime_copy_attempt_zero,
        claims.post_fence_exact_three_blocking_d2h,
        claims.post_fence_export_byte_count_exact,
        claims.same_runtime_device_stream_lineage_bound,
    )
    false_claims = tuple(
        getattr(claims, name)
        for name in claims.__dataclass_fields__
        if name
        not in {
            "canonical_to_global_fence_lineage_bound",
            "exact_bound_runtime_copy_counter_bound",
            "recurrence_program_bound_runtime_copy_attempt_zero",
            "post_fence_exact_three_blocking_d2h",
            "post_fence_export_byte_count_exact",
            "same_runtime_device_stream_lineage_bound",
        }
    )
    if not all(value is True for value in true_claims) or not all(
        value is False for value in false_claims
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_claim_invalid",
            "/claims",
        )
    if (
        receipt.bindings.runtime_scope
        != HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1
        or (
            receipt.actual_backend == "hip"
            and receipt.bindings.native_loader_bound_runtime is not True
        )
        or (
            receipt.actual_backend == "test_double"
            and receipt.bindings.native_loader_bound_runtime is not False
        )
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_binding_invalid",
            "/bindings",
        )


def _validate_phase_types(
    phase: HipFgmresHostTransferPhaseV1,
    path: str,
) -> None:
    if (
        type(phase) is not HipFgmresHostTransferPhaseV1
        or type(phase.sequence_delta) is not int
        or phase.sequence_delta < 0
    ):
        _fail(
            "hip_fgmres_iteration_host_transfer_audit_type_invalid",
            path,
        )
    for name in ("h2d_async", "d2h_async", "d2h_blocking"):
        row = getattr(phase, name)
        if type(row) is not HipFgmresHostTransferDeltaV1 or any(
            type(getattr(row, field)) is not int or getattr(row, field) < 0
            for field in row.__dataclass_fields__
        ):
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_type_invalid",
                f"{path}/{name}",
            )


def _reserve_runtime_audit_owner(
    runtime: Any,
    context: HipFgmresIterationHostTransferAuditExecutionContextV1,
) -> None:
    with _RUNTIME_AUDIT_OWNERS_LOCK:
        reference = _RUNTIME_AUDIT_OWNERS.get(runtime)
        active = None if reference is None else reference()
        if active is not None:
            _fail(
                "hip_fgmres_iteration_host_transfer_audit_runtime_busy",
                "/runtime/lifetime",
            )
        _RUNTIME_AUDIT_OWNERS[runtime] = weakref.ref(context)


def _release_runtime_audit_owner(
    runtime: Any,
    context: HipFgmresIterationHostTransferAuditExecutionContextV1,
) -> None:
    with _RUNTIME_AUDIT_OWNERS_LOCK:
        reference = _RUNTIME_AUDIT_OWNERS.get(runtime)
        if reference is not None and reference() is context:
            del _RUNTIME_AUDIT_OWNERS[runtime]


def _receipt_payload(
    receipt: HipFgmresIterationHostTransferAuditReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "bindings": receipt.bindings.to_dict(),
        "window": receipt.window.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: Any) -> str:
    text = " ".join(str(value).split())
    return text[:512]


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresIterationHostTransferAuditExecutionContextV1 | None = None,
) -> None:
    raise HipFgmresIterationHostTransferAuditV1Error(
        code,
        path,
        message,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_SCHEMA_VERSION_V1",
    "HipFgmresHostTransferDeltaV1",
    "HipFgmresHostTransferPhaseV1",
    "HipFgmresIterationHostTransferAuditBindingsV1",
    "HipFgmresIterationHostTransferAuditClaimsV1",
    "HipFgmresIterationHostTransferAuditDimensionsV1",
    "HipFgmresIterationHostTransferAuditExecutionContextV1",
    "HipFgmresIterationHostTransferAuditOpenResultV1",
    "HipFgmresIterationHostTransferAuditReceiptV1",
    "HipFgmresIterationHostTransferAuditResultV1",
    "HipFgmresIterationHostTransferAuditV1Error",
    "HipFgmresIterationHostTransferAuditWindowV1",
    "open_hip_fgmres_iteration_host_transfer_audit_v1",
    "validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1",
    "validate_hip_fgmres_iteration_host_transfer_audit_result_v1",
]
