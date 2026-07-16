"""Live owner for additive FGMRES checkpoint solution/residual history.

The context reserves one optional child on an unopened global-recurrence
suffix, allocates two owner-minted history blobs, and inserts one device-only
capture immediately after each checkpoint finalizer.  The base recurrence
keeps its frozen ABI and launch accounting; a companion failure poisons only
this history result and never truncates the base solve.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_checkpoint_history_plan_v1 import (
    HipFgmresCheckpointHistoryBlobV1,
    HipFgmresCheckpointHistoryPlanV1,
    compile_hip_fgmres_checkpoint_history_plan_v1,
    validate_hip_fgmres_checkpoint_history_blob_pair_v1,
    validate_hip_fgmres_checkpoint_history_plan_v1,
)
from .fgmres_checkpoint_history_rtc_v1 import (
    HipRtcFgmresCheckpointHistoryKernelV1,
    compile_hip_rtc_fgmres_checkpoint_history_kernel_v1,
)
from .fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceExecutionContextV1,
    _CheckpointHistoryChildAuthorityV1,
    _CheckpointHistoryChildLeaseV1,
    _mint_checkpoint_history_child_lease_v1,
)
from .hip_allocation_lineage import (
    HipAllocationCapabilityV1,
    HipAllocationOwnerV1,
    open_hip_allocation_owner_v1,
    validate_hip_allocation_capability_v1,
)


HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-checkpoint-history-context.v1"
)
HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_CAPABILITY_PROFILE_V1 = (
    "phase0_live_device_committed_checkpoint_vector_history"
)
HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_EVIDENCE_SCOPE_V1 = (
    "process_local_same_stream_checkpoint_history_non_promoting"
)
HIP_FGMRES_CHECKPOINT_HISTORY_COPY_API_V1 = "hipMemcpyDeviceToHost_blocking"

CheckpointHistoryStatusV1 = Literal[
    "context_ready",
    "exported",
    "poisoned",
    "cleanup_failed",
    "context_closed",
]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROLES = ("checkpoint_solution_history", "checkpoint_true_residual_history")
_SOURCE_ROLES = ("solution_x", "true_residual", "solve_record")
_SCHEMA_RESOURCE = "hip_fgmres_checkpoint_history_context_v1.schema.json"


class HipFgmresCheckpointHistoryContextV1Error(RuntimeError):
    """Stable live-history failure with retryable cleanup ownership."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresCheckpointHistoryExecutionContextV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message or code
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryBindingsV1:
    global_context_id: str
    global_open_receipt_hash: str
    continuation_schedule_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    recurrence_kernel_identity_hash: str
    recurrence_kernel_source_sha256: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    source_binding_hash: str
    history_plan_hash: str
    history_blob_abi_hash: str
    history_kernel_identity_hash: str
    history_kernel_source_sha256: str
    architecture: str
    device_ordinal: int
    source_pointer_values_serialized: Literal[False] = False
    history_pointer_values_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    expected_capture_launch_count: int
    history_blob_byte_count: int
    owned_device_byte_count: int
    exported_buffer_count: Literal[2] = 2

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryBufferV1:
    role: Literal[
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    ]
    dtype: Literal["|u1"]
    byte_count: int
    allocation_generation: int
    allocation_lineage_hash: str
    payload_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "dtype": self.dtype,
            "byte_count": self.byte_count,
            "allocation_generation": self.allocation_generation,
            "allocation_lineage_hash": self.allocation_lineage_hash,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryTelemetryV1:
    child_reservation_count: Literal[1] = 1
    allocation_attempt_count: int = 0
    allocation_success_count: int = 0
    allocated_device_bytes: int = 0
    initialize_launch_attempt_count: int = 0
    initialize_launch_success_count: int = 0
    capture_launch_attempt_count: int = 0
    capture_launch_success_count: int = 0
    capture_launch_failure_count: int = 0
    acknowledged_module_launch_count: int = 0
    d2h_operation_attempt_count: int = 0
    d2h_operation_success_count: int = 0
    d2h_bytes_attempted: int = 0
    d2h_bytes_succeeded: int = 0
    blocking_copy_completion_count: int = 0
    cleanup_stream_sync_count: int = 0
    free_attempt_count: int = 0
    free_success_count: int = 0
    module_close_attempt_count: int = 0
    module_close_success_count: int = 0
    fallback_count: Literal[0] = 0
    recurrence_d2h_operation_count: Literal[0] = 0
    recurrence_host_state_branch_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryClaimsV1:
    frozen_recurrence_and_solve_record_abi_preserved: bool
    same_runtime_device_stream_bound: bool
    exact_three_capture_sources_bound: bool
    owner_minted_nonoverlapping_history_allocations: bool
    prefix_capture_submitted: bool
    one_capture_after_each_checkpoint_finalizer: bool
    capture_launch_count_complete: bool
    device_only_recurrence_capture: bool
    row_marker_published_after_vector_copy: bool
    exact_two_blocking_completion_copies: bool
    detached_history_blobs_validated: bool
    per_restart_solution_vectors_exported: bool
    per_restart_true_residual_vectors_exported: bool
    general_restart_history_parity_verified: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryReceiptV1:
    status: CheckpointHistoryStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresCheckpointHistoryReasonV1 | None
    bindings: HipFgmresCheckpointHistoryBindingsV1
    dimensions: HipFgmresCheckpointHistoryDimensionsV1
    buffers: tuple[HipFgmresCheckpointHistoryBufferV1, ...]
    telemetry: HipFgmresCheckpointHistoryTelemetryV1
    claims: HipFgmresCheckpointHistoryClaimsV1
    payload_hash: str
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_checkpoint_history_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryResultV1:
    receipt: HipFgmresCheckpointHistoryReceiptV1
    checkpoint_solution_history: bytes
    checkpoint_true_residual_history: bytes
    payload_hash: str
    solution: HipFgmresCheckpointHistoryBlobV1
    true_residual: HipFgmresCheckpointHistoryBlobV1

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_checkpoint_history_result_v1(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryOpenResultV1:
    context: HipFgmresCheckpointHistoryExecutionContextV1
    receipt: HipFgmresCheckpointHistoryReceiptV1

    @property
    def ready(self) -> bool:
        context = self.context
        with context._lock:
            return (
                self.receipt.status == "context_ready"
                and context._state == "context_ready"
                and not context._closed
                and context._parent_reserved
            )


class HipFgmresCheckpointHistoryExecutionContextV1:
    """Single-use allocation, capture, export, and cleanup owner."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Checkpoint history contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._global: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._token: _CheckpointHistoryChildLeaseV1 = (
            _mint_checkpoint_history_child_lease_v1()
        )
        self._authority: _CheckpointHistoryChildAuthorityV1 | None = None
        self._plan: HipFgmresCheckpointHistoryPlanV1 | None = None
        self._owner: HipAllocationOwnerV1 | None = None
        self._capabilities: dict[str, HipAllocationCapabilityV1] = {}
        self._kernel: HipRtcFgmresCheckpointHistoryKernelV1 | None = None
        self._bindings: HipFgmresCheckpointHistoryBindingsV1 | None = None
        self._dimensions: HipFgmresCheckpointHistoryDimensionsV1 | None = None
        self._context_id = _ZERO_HASH
        self._actual_backend: Literal["hip", "test_double"] = "test_double"
        self._telemetry = HipFgmresCheckpointHistoryTelemetryV1()
        self._reason: HipFgmresCheckpointHistoryReasonV1 | None = None
        self._state: CheckpointHistoryStatusV1 = "context_ready"
        self._result: HipFgmresCheckpointHistoryResultV1 | None = None
        self._parent_reserved = False
        self._history_started = False
        self._module_fenced = False
        self._module_closed = False
        self._freed_roles: set[str] = set()
        self._owner_closed = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def result(self) -> HipFgmresCheckpointHistoryResultV1 | None:
        return self._result

    def receipt(self) -> HipFgmresCheckpointHistoryReceiptV1:
        with self._lock:
            if self._result is not None and not self._closed:
                return self._result.receipt
            return self._build_receipt(self._state)

    def export_history_blobs(self) -> HipFgmresCheckpointHistoryResultV1:
        """Copy exactly two fenced history blobs and validate their ABI."""

        with self._lock:
            if self._result is not None:
                return self._result
            if self._closed or self._state != "context_ready" or self._reason:
                _fail(
                    "hip_fgmres_checkpoint_history_export_state_invalid",
                    "/export",
                    cleanup_owner=self,
                )
            parent = self._require_global()
            parent_receipt = parent.receipt()
            if (
                parent_receipt.status != "recurrence_fenced"
                or parent.completion_capability is None
            ):
                _fail(
                    "hip_fgmres_checkpoint_history_parent_not_fenced",
                    "/export/global",
                    cleanup_owner=self,
                )
            self._acknowledge_parent_fence()
            dimensions = self._require_dimensions()
            expected_module_launches = 1 + dimensions.expected_capture_launch_count
            if self._telemetry.acknowledged_module_launch_count != (
                expected_module_launches
            ):
                self._poison(
                    "hip_fgmres_checkpoint_history_launch_count_incomplete",
                    "The fixed initialization plus capture program was incomplete.",
                )
                _fail(
                    self._reason.code,
                    "/export/launch_count",
                    self._reason.detail,
                    cleanup_owner=self,
                )
            authority = self._require_authority()
            copy_method = authority.runtime.completion_export_copy_binding()
            staging = tuple(
                np.empty(capability.nbytes, dtype=np.uint8)
                for capability in self._ordered_capabilities()
            )
            for role, capability, target in zip(
                _ROLES,
                self._ordered_capabilities(),
                staging,
                strict=True,
            ):
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_attempt_count=(
                        self._telemetry.d2h_operation_attempt_count + 1
                    ),
                    d2h_bytes_attempted=(
                        self._telemetry.d2h_bytes_attempted + capability.nbytes
                    ),
                )
                try:
                    copy_method(target, capability.pointer_snapshot)
                except BaseException as exc:
                    self._poison(
                        "hip_fgmres_checkpoint_history_copy_failed",
                        _detail(exc),
                    )
                    if not isinstance(exc, Exception):
                        raise
                    raise HipFgmresCheckpointHistoryContextV1Error(
                        self._reason.code,
                        f"/export/{role}",
                        self._reason.detail,
                        cleanup_owner=self,
                    ) from exc
                self._telemetry = replace(
                    self._telemetry,
                    d2h_operation_success_count=(
                        self._telemetry.d2h_operation_success_count + 1
                    ),
                    d2h_bytes_succeeded=(
                        self._telemetry.d2h_bytes_succeeded + capability.nbytes
                    ),
                    blocking_copy_completion_count=(
                        self._telemetry.blocking_copy_completion_count + 1
                    ),
                )
            payloads = tuple(bytes(memoryview(row).cast("B")) for row in staging)
            try:
                solution, true_residual = (
                    validate_hip_fgmres_checkpoint_history_blob_pair_v1(
                        payloads[0],
                        payloads[1],
                        expected_free_dof_count=dimensions.free_dof_count,
                        expected_maximum_restart_count=(
                            dimensions.maximum_restart_count
                        ),
                        expected_capture_launch_count=(
                            dimensions.expected_capture_launch_count
                        ),
                    )
                )
            except Exception as exc:
                self._poison(
                    "hip_fgmres_checkpoint_history_blob_validation_failed",
                    _detail(exc),
                )
                raise HipFgmresCheckpointHistoryContextV1Error(
                    self._reason.code,
                    "/export/payload",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            payload_hash = _bundle_hash(payloads)
            buffers = self._buffer_descriptors(payloads)
            receipt = self._build_receipt(
                "exported",
                buffers=buffers,
                payload_hash=payload_hash,
            )
            result = HipFgmresCheckpointHistoryResultV1(
                receipt=receipt,
                checkpoint_solution_history=payloads[0],
                checkpoint_true_residual_history=payloads[1],
                payload_hash=payload_hash,
                solution=solution,
                true_residual=true_residual,
            )
            validate_hip_fgmres_checkpoint_history_result_v1(result)
            self._result = result
            self._state = "exported"
            return result

    def export(self) -> HipFgmresCheckpointHistoryResultV1:
        return self.export_history_blobs()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._ensure_cleanup_fence()
                self._close_kernel()
                self._free_allocations()
                self._close_owner()
                self._release_parent(terminal=self._history_started)
            except Exception as exc:
                self._state = "cleanup_failed"
                self._reason = HipFgmresCheckpointHistoryReasonV1(
                    "hip_fgmres_checkpoint_history_cleanup_failed",
                    _detail(exc),
                )
                raise HipFgmresCheckpointHistoryContextV1Error(
                    self._reason.code,
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"

    def _capture_after_global_finalize_v1(
        self,
        parent: HipFgmresGlobalRecurrenceExecutionContextV1,
        *,
        expected_restart: int,
        expected_column: int,
        continuation_index: int,
    ) -> None:
        with self._lock:
            if (
                parent is not self._global
                or self._closed
                or self._state != "context_ready"
                or self._reason is not None
                or type(continuation_index) is not int
                or continuation_index < 0
            ):
                return
            dimensions = self._require_dimensions()
            if (
                type(expected_restart) is not int
                or not 1 <= expected_restart <= dimensions.maximum_restart_count
                or type(expected_column) is not int
                or not 0 <= expected_column < dimensions.restart_dimension
            ):
                self._poison(
                    "hip_fgmres_checkpoint_history_coordinate_invalid",
                    "Global finalizer coordinates are outside the fixed program.",
                )
                return
            end_iteration = (
                (expected_restart - 1) * dimensions.restart_dimension
                + expected_column
                + 1
            )
            self._launch_capture(expected_restart, expected_column, end_iteration)

    def _poison_from_global_capture_v1(self, error: BaseException) -> None:
        with self._lock:
            self._poison(
                "hip_fgmres_checkpoint_history_capture_failed",
                _detail(error),
            )

    def _launch_capture(
        self,
        expected_restart: int,
        expected_column: int,
        expected_end_iteration: int,
    ) -> None:
        authority = self._require_authority()
        kernel = self._require_kernel()
        sources = {row.role: row for row in authority.source_capabilities}
        destinations = self._capabilities
        self._telemetry = replace(
            self._telemetry,
            capture_launch_attempt_count=(
                self._telemetry.capture_launch_attempt_count + 1
            ),
        )
        try:
            kernel.launch_capture(
                authority.stream,
                expected_restart,
                expected_column,
                expected_end_iteration,
                authority.free_dof_count,
                authority.maximum_restart_count,
                sources["solution_x"].pointer_snapshot,
                sources["true_residual"].pointer_snapshot,
                sources["solve_record"].pointer_snapshot,
                destinations[_ROLES[0]].pointer_snapshot,
                destinations[_ROLES[1]].pointer_snapshot,
            )
        except BaseException:
            self._telemetry = replace(
                self._telemetry,
                capture_launch_failure_count=(
                    self._telemetry.capture_launch_failure_count + 1
                ),
            )
            raise
        self._telemetry = replace(
            self._telemetry,
            capture_launch_success_count=(
                self._telemetry.capture_launch_success_count + 1
            ),
        )

    def _acknowledge_parent_fence(self) -> None:
        if self._module_fenced:
            return
        authority = self._require_authority()
        acknowledged = self._require_kernel().acknowledge_stream_fence(authority.stream)
        self._telemetry = replace(
            self._telemetry,
            acknowledged_module_launch_count=acknowledged,
        )
        self._module_fenced = True

    def _ensure_cleanup_fence(self) -> None:
        kernel = self._kernel
        if kernel is None or self._module_fenced or not kernel.pending:
            self._module_fenced = True
            return
        parent = self._global
        if parent is not None:
            try:
                if parent.receipt().status == "recurrence_fenced":
                    self._acknowledge_parent_fence()
                    return
            except Exception:
                pass
        authority = self._require_authority()
        authority.runtime.synchronize(authority.stream)
        self._telemetry = replace(
            self._telemetry,
            cleanup_stream_sync_count=self._telemetry.cleanup_stream_sync_count + 1,
        )
        acknowledged = kernel.acknowledge_stream_fence(authority.stream)
        self._telemetry = replace(
            self._telemetry,
            acknowledged_module_launch_count=acknowledged,
        )
        self._module_fenced = True

    def _close_kernel(self) -> None:
        if self._module_closed or self._kernel is None:
            return
        self._telemetry = replace(
            self._telemetry,
            module_close_attempt_count=self._telemetry.module_close_attempt_count + 1,
        )
        self._kernel.close()
        self._module_closed = True
        self._telemetry = replace(
            self._telemetry,
            module_close_success_count=self._telemetry.module_close_success_count + 1,
        )

    def _free_allocations(self) -> None:
        owner = self._owner
        authority = self._authority
        if owner is None or authority is None:
            return
        for role in reversed(_ROLES):
            if role in self._freed_roles or role not in self._capabilities:
                continue
            capability = self._capabilities[role]
            lease = owner.begin_free(capability)
            self._telemetry = replace(
                self._telemetry,
                free_attempt_count=self._telemetry.free_attempt_count + 1,
            )
            authority.runtime.free(capability.base)
            owner.acknowledge_free_success(lease)
            self._freed_roles.add(role)
            self._telemetry = replace(
                self._telemetry,
                free_success_count=self._telemetry.free_success_count + 1,
            )

    def _close_owner(self) -> None:
        if self._owner_closed or self._owner is None:
            return
        self._owner.close()
        self._owner_closed = True

    def _release_parent(self, *, terminal: bool) -> None:
        if not self._parent_reserved:
            return
        self._require_global()._release_checkpoint_history_child(
            self._token,
            terminal=terminal,
        )
        self._parent_reserved = False

    def _require_global(self) -> HipFgmresGlobalRecurrenceExecutionContextV1:
        if type(self._global) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_checkpoint_history_global_missing",
                "/global",
                cleanup_owner=self,
            )
        return self._global

    def _require_authority(self) -> _CheckpointHistoryChildAuthorityV1:
        if type(self._authority) is not _CheckpointHistoryChildAuthorityV1:
            _fail(
                "hip_fgmres_checkpoint_history_authority_missing",
                "/authority",
                cleanup_owner=self,
            )
        return self._authority

    def _require_kernel(self) -> HipRtcFgmresCheckpointHistoryKernelV1:
        if type(self._kernel) is not HipRtcFgmresCheckpointHistoryKernelV1:
            _fail(
                "hip_fgmres_checkpoint_history_kernel_missing",
                "/kernel",
                cleanup_owner=self,
            )
        return self._kernel

    def _require_dimensions(self) -> HipFgmresCheckpointHistoryDimensionsV1:
        if type(self._dimensions) is not HipFgmresCheckpointHistoryDimensionsV1:
            _fail(
                "hip_fgmres_checkpoint_history_dimensions_missing",
                "/dimensions",
                cleanup_owner=self,
            )
        return self._dimensions

    def _ordered_capabilities(self) -> tuple[HipAllocationCapabilityV1, ...]:
        try:
            result = tuple(self._capabilities[role] for role in _ROLES)
        except KeyError:
            _fail(
                "hip_fgmres_checkpoint_history_allocations_missing",
                "/allocations",
                cleanup_owner=self,
            )
        for capability in result:
            validate_hip_allocation_capability_v1(
                capability,
                expected_owner=self._owner,
            )
        return result

    def _poison(self, code: str, detail: str) -> None:
        if self._reason is None:
            self._reason = HipFgmresCheckpointHistoryReasonV1(code, detail)
            self._state = "poisoned"

    def _buffer_descriptors(
        self,
        payloads: tuple[bytes, bytes],
    ) -> tuple[HipFgmresCheckpointHistoryBufferV1, ...]:
        return tuple(
            HipFgmresCheckpointHistoryBufferV1(
                role=role,  # type: ignore[arg-type]
                dtype="|u1",
                byte_count=capability.nbytes,
                allocation_generation=capability.generation,
                allocation_lineage_hash=_allocation_lineage_hash(capability),
                payload_sha256=_sha256(payload),
            )
            for role, capability, payload in zip(
                _ROLES,
                self._ordered_capabilities(),
                payloads,
                strict=True,
            )
        )

    def _build_receipt(
        self,
        status: CheckpointHistoryStatusV1,
        *,
        buffers: tuple[HipFgmresCheckpointHistoryBufferV1, ...] = (),
        payload_hash: str = _ZERO_HASH,
    ) -> HipFgmresCheckpointHistoryReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail(
                "hip_fgmres_checkpoint_history_receipt_unavailable",
                "/receipt",
                cleanup_owner=self,
            )
        exported = status == "exported"
        healthy = status in {"context_ready", "exported", "context_closed"}
        claims = HipFgmresCheckpointHistoryClaimsV1(
            frozen_recurrence_and_solve_record_abi_preserved=healthy,
            same_runtime_device_stream_bound=healthy,
            exact_three_capture_sources_bound=healthy,
            owner_minted_nonoverlapping_history_allocations=healthy,
            prefix_capture_submitted=healthy,
            one_capture_after_each_checkpoint_finalizer=exported,
            capture_launch_count_complete=exported,
            device_only_recurrence_capture=healthy,
            row_marker_published_after_vector_copy=healthy,
            exact_two_blocking_completion_copies=exported,
            detached_history_blobs_validated=exported,
            per_restart_solution_vectors_exported=exported,
            per_restart_true_residual_vectors_exported=exported,
        )
        reason = None if healthy else self._reason
        draft = HipFgmresCheckpointHistoryReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_EVIDENCE_SCOPE_V1,
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            buffers=buffers,
            telemetry=self._telemetry,
            claims=claims,
            payload_hash=payload_hash,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


_CONTEXT_MINT = object()


def open_hip_fgmres_checkpoint_history_context_v1(
    global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
    *,
    hiprtc_library: str | None = None,
) -> HipFgmresCheckpointHistoryOpenResultV1:
    """Attach history capture before the global suffix is consumed."""

    context = HipFgmresCheckpointHistoryExecutionContextV1(_mint=_CONTEXT_MINT)
    context._global = global_context
    try:
        if type(global_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_checkpoint_history_global_invalid",
                "/global_context",
                cleanup_owner=context,
            )
        acquired = global_context._reserve_checkpoint_history_child(
            context._token,
            context,
        )
        if acquired is not context._token:
            _fail(
                "hip_fgmres_checkpoint_history_reservation_changed",
                "/global_context/reservation",
                cleanup_owner=context,
            )
        context._parent_reserved = True
        authority = global_context._checkpoint_history_child_authority(context._token)
        context._authority = authority
        context._actual_backend = global_context.receipt().actual_backend
        plan = compile_hip_fgmres_checkpoint_history_plan_v1(
            authority.free_dof_count,
            authority.maximum_restart_count,
        )
        context._plan = plan
        owner = open_hip_allocation_owner_v1(
            authority.runtime,
            authority.device_ordinal,
            "fgmres_checkpoint_history_v1",
        )
        context._owner = owner
        for role in _ROLES:
            context._telemetry = replace(
                context._telemetry,
                allocation_attempt_count=(
                    context._telemetry.allocation_attempt_count + 1
                ),
            )
            capability = owner.allocate(role, plan.blob_byte_count, "u8")
            context._capabilities[role] = capability
            context._telemetry = replace(
                context._telemetry,
                allocation_success_count=(
                    context._telemetry.allocation_success_count + 1
                ),
                allocated_device_bytes=(
                    context._telemetry.allocated_device_bytes + capability.nbytes
                ),
            )
        _validate_source_and_history_nonoverlap(
            authority.source_capabilities,
            context._ordered_capabilities(),
        )
        kernel = compile_hip_rtc_fgmres_checkpoint_history_kernel_v1(
            authority.loaded_runtime,
            authority.architecture,
            hiprtc_library,
        )
        context._kernel = kernel
        context._dimensions = HipFgmresCheckpointHistoryDimensionsV1(
            free_dof_count=authority.free_dof_count,
            restart_dimension=authority.restart_dimension,
            max_iterations=authority.max_iterations,
            maximum_restart_count=authority.maximum_restart_count,
            expected_capture_launch_count=(
                authority.maximum_restart_count * authority.restart_dimension
            ),
            history_blob_byte_count=plan.blob_byte_count,
            owned_device_byte_count=plan.owned_device_byte_length,
        )
        source_binding_hash = _source_binding_hash(authority.source_capabilities)
        history_binding_hash = canonical_hash(
            {
                "global_context_id": authority.global_context_id,
                "plan_hash": plan.plan_hash,
                "kernel_identity_hash": kernel.identity.identity_hash,
                "source_binding_hash": source_binding_hash,
                "history_allocations": [
                    {
                        "role": row.role,
                        "nbytes": row.nbytes,
                        "element_type": row.element_type,
                        "generation": row.generation,
                        "lineage_hash": _allocation_lineage_hash(row),
                    }
                    for row in context._ordered_capabilities()
                ],
            }
        )
        context._context_id = history_binding_hash
        context._bindings = HipFgmresCheckpointHistoryBindingsV1(
            global_context_id=authority.global_context_id,
            global_open_receipt_hash=authority.global_open_receipt_hash,
            continuation_schedule_hash=authority.continuation_schedule_hash,
            recurrence_plan_hash=authority.recurrence_plan_hash,
            recurrence_kernel_abi_hash=authority.recurrence_kernel_abi_hash,
            combined_recurrence_abi_hash=authority.combined_recurrence_abi_hash,
            recurrence_kernel_identity_hash=authority.kernel_identity_hash,
            recurrence_kernel_source_sha256=authority.kernel_source_sha256,
            direct_generation_binding_hash=(authority.direct_generation_binding_hash),
            physical_projection_hash=authority.physical_projection_hash,
            source_binding_hash=source_binding_hash,
            history_plan_hash=plan.plan_hash,
            history_blob_abi_hash=plan.abi_hash,
            history_kernel_identity_hash=kernel.identity.identity_hash,
            history_kernel_source_sha256=kernel.identity.source_sha256,
            architecture=authority.architecture,
            device_ordinal=authority.device_ordinal,
        )
        destinations = context._capabilities
        context._telemetry = replace(
            context._telemetry,
            initialize_launch_attempt_count=1,
        )
        kernel.launch_initialize(
            authority.stream,
            authority.free_dof_count,
            authority.maximum_restart_count,
            destinations[_ROLES[0]].pointer_snapshot,
            destinations[_ROLES[1]].pointer_snapshot,
        )
        context._telemetry = replace(
            context._telemetry,
            initialize_launch_success_count=1,
        )
        context._history_started = True
        context._launch_capture(1, 0, 1)
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_checkpoint_history_receipt_v1(
            receipt,
            expected_context=context,
        )
        return HipFgmresCheckpointHistoryOpenResultV1(context, receipt)
    except BaseException as primary:
        try:
            context.close()
        except BaseException as cleanup:
            if not isinstance(cleanup, Exception):
                raise
            raise HipFgmresCheckpointHistoryContextV1Error(
                "hip_fgmres_checkpoint_history_open_cleanup_failed",
                "/open/cleanup",
                f"open failed: {_detail(primary)}; cleanup failed: {_detail(cleanup)}",
                cleanup_owner=context,
            ) from cleanup
        raise


def validate_hip_fgmres_checkpoint_history_receipt_v1(
    receipt: HipFgmresCheckpointHistoryReceiptV1,
    *,
    expected_context: HipFgmresCheckpointHistoryExecutionContextV1 | None = None,
) -> HipFgmresCheckpointHistoryReceiptV1:
    if type(receipt) is not HipFgmresCheckpointHistoryReceiptV1:
        _fail("hip_fgmres_checkpoint_history_receipt_type_invalid", "/")
    if (
        receipt.evidence_scope
        != HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_EVIDENCE_SCOPE_V1
        or receipt.promotion_eligible is not False
        or receipt.actual_backend not in {"hip", "test_double"}
        or receipt.status
        not in {
            "context_ready",
            "exported",
            "poisoned",
            "cleanup_failed",
            "context_closed",
        }
        or _HASH_RE.fullmatch(receipt.context_id) is None
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash
        != canonical_hash(_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_checkpoint_history_receipt_invalid", "/")
    _validate_schema(_receipt_payload(receipt, include_hash=True))
    dimensions = receipt.dimensions
    if (
        dimensions.free_dof_count <= 0
        or dimensions.restart_dimension <= 0
        or dimensions.max_iterations <= 0
        or dimensions.maximum_restart_count <= 0
        or dimensions.expected_capture_launch_count
        != dimensions.maximum_restart_count * dimensions.restart_dimension
        or dimensions.owned_device_byte_count != 2 * dimensions.history_blob_byte_count
        or dimensions.exported_buffer_count != 2
    ):
        _fail("hip_fgmres_checkpoint_history_dimensions_invalid", "/dimensions")
    plan = compile_hip_fgmres_checkpoint_history_plan_v1(
        dimensions.free_dof_count,
        dimensions.maximum_restart_count,
    )
    validate_hip_fgmres_checkpoint_history_plan_v1(plan)
    if (
        dimensions.history_blob_byte_count != plan.blob_byte_count
        or dimensions.owned_device_byte_count != plan.owned_device_byte_length
        or receipt.bindings.history_plan_hash != plan.plan_hash
        or receipt.bindings.history_blob_abi_hash != plan.abi_hash
    ):
        _fail("hip_fgmres_checkpoint_history_plan_binding_invalid", "/bindings")
    exported = receipt.status == "exported"
    if (
        (len(receipt.buffers) == 2) is not exported
        or (receipt.payload_hash != _ZERO_HASH) is not exported
        or (receipt.reason is None)
        is not (receipt.status in {"context_ready", "exported", "context_closed"})
        or receipt.claims.exact_two_blocking_completion_copies is not exported
        or receipt.claims.detached_history_blobs_validated is not exported
        or receipt.claims.per_restart_solution_vectors_exported is not exported
        or receipt.claims.per_restart_true_residual_vectors_exported is not exported
        or receipt.claims.general_restart_history_parity_verified is not False
        or receipt.claims.performance_or_speedup_proven is not False
        or receipt.claims.commercial_ready is not False
        or receipt.claims.promotion_eligible is not False
    ):
        _fail("hip_fgmres_checkpoint_history_claim_invalid", "/claims")
    telemetry = receipt.telemetry
    if (
        telemetry.child_reservation_count != 1
        or telemetry.allocation_attempt_count != 2
        or telemetry.allocation_success_count != 2
        or telemetry.allocated_device_bytes != plan.owned_device_byte_length
        or telemetry.initialize_launch_attempt_count != 1
        or telemetry.initialize_launch_success_count != 1
        or telemetry.capture_launch_failure_count != 0
        or telemetry.fallback_count != 0
        or telemetry.recurrence_d2h_operation_count != 0
        or telemetry.recurrence_host_state_branch_count != 0
        or telemetry.capture_launch_success_count
        > dimensions.expected_capture_launch_count
        or telemetry.capture_launch_attempt_count
        != telemetry.capture_launch_success_count
    ):
        _fail("hip_fgmres_checkpoint_history_telemetry_invalid", "/telemetry")
    if exported and (
        telemetry.capture_launch_success_count
        != dimensions.expected_capture_launch_count
        or telemetry.acknowledged_module_launch_count
        != 1 + dimensions.expected_capture_launch_count
        or telemetry.d2h_operation_attempt_count != 2
        or telemetry.d2h_operation_success_count != 2
        or telemetry.blocking_copy_completion_count != 2
        or telemetry.d2h_bytes_attempted != plan.owned_device_byte_length
        or telemetry.d2h_bytes_succeeded != plan.owned_device_byte_length
    ):
        _fail("hip_fgmres_checkpoint_history_telemetry_invalid", "/telemetry")
    if expected_context is not None:
        if (
            type(expected_context) is not HipFgmresCheckpointHistoryExecutionContextV1
            or receipt.context_id != expected_context._context_id
        ):
            _fail("hip_fgmres_checkpoint_history_context_mismatch", "/context_id")
    return receipt


def validate_hip_fgmres_checkpoint_history_result_v1(
    result: HipFgmresCheckpointHistoryResultV1,
) -> HipFgmresCheckpointHistoryResultV1:
    if type(result) is not HipFgmresCheckpointHistoryResultV1:
        _fail("hip_fgmres_checkpoint_history_result_type_invalid", "/")
    receipt = validate_hip_fgmres_checkpoint_history_receipt_v1(result.receipt)
    if (
        receipt.status != "exported"
        or type(result.checkpoint_solution_history) is not bytes
        or type(result.checkpoint_true_residual_history) is not bytes
        or result.payload_hash != receipt.payload_hash
        or result.payload_hash
        != _bundle_hash(
            (
                result.checkpoint_solution_history,
                result.checkpoint_true_residual_history,
            )
        )
    ):
        _fail("hip_fgmres_checkpoint_history_result_invalid", "/")
    solution, residual = validate_hip_fgmres_checkpoint_history_blob_pair_v1(
        result.checkpoint_solution_history,
        result.checkpoint_true_residual_history,
        expected_free_dof_count=receipt.dimensions.free_dof_count,
        expected_maximum_restart_count=receipt.dimensions.maximum_restart_count,
        expected_capture_launch_count=(
            receipt.dimensions.expected_capture_launch_count
        ),
    )
    if result.solution != solution or result.true_residual != residual:
        _fail("hip_fgmres_checkpoint_history_result_decode_mismatch", "/payload")
    for descriptor, role, payload in zip(
        receipt.buffers,
        _ROLES,
        (result.checkpoint_solution_history, result.checkpoint_true_residual_history),
        strict=True,
    ):
        if (
            descriptor.role != role
            or descriptor.dtype != "|u1"
            or descriptor.byte_count != len(payload)
            or descriptor.payload_sha256 != _sha256(payload)
        ):
            _fail("hip_fgmres_checkpoint_history_buffer_invalid", "/buffers")
    return result


def _receipt_payload(
    receipt: HipFgmresCheckpointHistoryReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_SCHEMA_VERSION_V1,
        "capability_profile": (
            HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_CAPABILITY_PROFILE_V1
        ),
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "buffers": [row.to_dict() for row in receipt.buffers],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "payload_hash": receipt.payload_hash,
        "extensions": {},
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_source_and_history_nonoverlap(
    sources: tuple[Any, ...],
    destinations: tuple[HipAllocationCapabilityV1, ...],
) -> None:
    rows = (*sources, *destinations)
    ranges: list[tuple[int, int, str]] = []
    for row in rows:
        pointer = getattr(row, "pointer_snapshot", None)
        nbytes = getattr(row, "nbytes", None)
        role = getattr(row, "role", "unknown")
        if type(pointer) is not int or type(nbytes) is not int or nbytes <= 0:
            _fail(
                "hip_fgmres_checkpoint_history_extent_invalid",
                f"/allocations/{role}",
            )
        end = pointer + nbytes
        if end <= pointer:
            _fail(
                "hip_fgmres_checkpoint_history_extent_invalid",
                f"/allocations/{role}",
            )
        ranges.append((pointer, end, role))
    for index, left in enumerate(ranges):
        for right in ranges[index + 1 :]:
            if max(left[0], right[0]) < min(left[1], right[1]):
                _fail(
                    "hip_fgmres_checkpoint_history_allocation_overlap",
                    f"/allocations/{left[2]}/{right[2]}",
                )


def _source_binding_hash(sources: tuple[Any, ...]) -> str:
    if tuple(getattr(row, "role", None) for row in sources) != _SOURCE_ROLES:
        _fail("hip_fgmres_checkpoint_history_source_roles_invalid", "/sources")
    return canonical_hash(
        [
            {
                "role": row.role,
                "nbytes": row.nbytes,
                "element_type": row.element_type,
                "generation": row.generation,
                "allocation_id": row.allocation_id,
                "owner_identity": row.owner_identity,
            }
            for row in sources
        ]
    )


def _allocation_lineage_hash(capability: HipAllocationCapabilityV1) -> str:
    return canonical_hash(
        {
            "allocation_id": capability.allocation_id,
            "role": capability.role,
            "nbytes": capability.nbytes,
            "element_type": capability.element_type,
            "generation": capability.generation,
            "owner_identity": capability.owner_identity,
            "runtime_domain_id": capability.runtime_domain_id,
            "device_ordinal": capability.device_ordinal,
            "evidence_scope": capability.evidence_scope,
            "promotion_eligible": capability.promotion_eligible,
        }
    )


def _bundle_hash(payloads: tuple[bytes, bytes]) -> str:
    digest = hashlib.sha256()
    for role, payload in zip(_ROLES, payloads, strict=True):
        role_bytes = role.encode("ascii")
        digest.update(len(role_bytes).to_bytes(8, "little"))
        digest.update(role_bytes)
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _detail(value: object) -> str:
    return (" ".join(str(value).split())[:512]) or "unspecified"


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(
            "hip_fgmres_checkpoint_history_schema_invalid",
            path,
            error.message,
        )


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresCheckpointHistoryExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresCheckpointHistoryContextV1Error(
        code,
        path,
        message or code,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_CONTEXT_SCHEMA_VERSION_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_COPY_API_V1",
    "HipFgmresCheckpointHistoryBindingsV1",
    "HipFgmresCheckpointHistoryBufferV1",
    "HipFgmresCheckpointHistoryClaimsV1",
    "HipFgmresCheckpointHistoryContextV1Error",
    "HipFgmresCheckpointHistoryDimensionsV1",
    "HipFgmresCheckpointHistoryExecutionContextV1",
    "HipFgmresCheckpointHistoryOpenResultV1",
    "HipFgmresCheckpointHistoryReasonV1",
    "HipFgmresCheckpointHistoryReceiptV1",
    "HipFgmresCheckpointHistoryResultV1",
    "HipFgmresCheckpointHistoryTelemetryV1",
    "open_hip_fgmres_checkpoint_history_context_v1",
    "validate_hip_fgmres_checkpoint_history_receipt_v1",
    "validate_hip_fgmres_checkpoint_history_result_v1",
]
