"""Additive five-buffer completion export with checkpoint vector history.

Version 2 composes the frozen three-buffer completion export with the two
validated history blobs.  It neither changes the v1 payload nor performs any
additional device work; the only new completion transfers are the two bulk
history D2H copies owned by the attached history context.
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

from .fgmres_checkpoint_history_context_v1 import (
    HipFgmresCheckpointHistoryExecutionContextV1,
    HipFgmresCheckpointHistoryResultV1,
    validate_hip_fgmres_checkpoint_history_result_v1,
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


HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-completion-export.v2"
)
HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V2 = (
    "phase0_fenced_five_buffer_completion_and_checkpoint_history_export"
)
HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V2 = (
    "process_local_composed_five_buffer_export_non_promoting"
)
HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V2 = "hipMemcpyDeviceToHost_blocking"

CompletionExportStatusV2 = Literal[
    "context_ready",
    "exported",
    "poisoned",
    "cleanup_failed",
    "context_closed",
]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROLES = (
    "solution_x",
    "true_residual",
    "solve_record",
    "checkpoint_solution_history",
    "checkpoint_true_residual_history",
)
_DTYPES = ("<f8", "<f8", "|u1", "|u1", "|u1")
_SCHEMA_RESOURCE = "hip_fgmres_completion_export_v2.schema.json"


class HipFgmresCompletionExportV2Error(RuntimeError):
    """Stable composite-export failure with retryable cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresCompletionExportExecutionContextV2 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message or code
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportReasonV2:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportBindingsV2:
    global_context_id: str
    global_completion_receipt_hash: str
    base_export_context_id: str
    base_export_open_receipt_hash: str
    history_context_id: str
    history_open_receipt_hash: str
    history_plan_hash: str
    history_blob_abi_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_identity_hash: str
    architecture: str
    device_ordinal: int
    copy_api: Literal["hipMemcpyDeviceToHost_blocking"]
    nested_device_pointer_values_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportDimensionsV2:
    free_dof_count: int
    maximum_restart_count: int
    solution_byte_count: int
    true_residual_byte_count: int
    solve_record_byte_count: int
    checkpoint_solution_history_byte_count: int
    checkpoint_true_residual_history_byte_count: int
    base_export_byte_count: int
    history_export_byte_count: int
    total_export_byte_count: int
    exported_buffer_count: Literal[5] = 5

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportBufferV2:
    role: Literal[
        "solution_x",
        "true_residual",
        "solve_record",
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    ]
    dtype: Literal["<f8", "|u1"]
    byte_count: int
    payload_sha256: str
    nested_receipt_hash: str
    nested_buffer_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "dtype": self.dtype,
            "byte_count": self.byte_count,
            "payload_sha256": self.payload_sha256,
            "nested_receipt_hash": self.nested_receipt_hash,
            "nested_buffer_index": self.nested_buffer_index,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportTelemetryV2:
    base_blocking_d2h_attempt_count: int
    base_blocking_d2h_success_count: int
    history_blocking_d2h_attempt_count: int
    history_blocking_d2h_success_count: int
    total_blocking_d2h_attempt_count: int
    total_blocking_d2h_success_count: int
    base_d2h_byte_count: int
    history_d2h_byte_count: int
    total_d2h_byte_count: int
    composite_device_allocation_count: Literal[0] = 0
    composite_h2d_operation_count: Literal[0] = 0
    composite_kernel_launch_count: Literal[0] = 0
    composite_explicit_stream_sync_count: Literal[0] = 0
    composite_fallback_count: Literal[0] = 0
    numerical_content_branch_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportClaimsV2:
    retained_completion_export_v1_validated: bool
    checkpoint_history_export_v1_validated: bool
    same_global_context_bound: bool
    exact_five_buffer_roles_bound: bool
    exact_five_blocking_completion_copies: bool
    immutable_detached_payloads: bool
    per_restart_checkpoint_solution_exported: bool
    per_restart_checkpoint_true_residual_exported: bool
    no_composite_device_allocation_or_kernel: bool
    no_recurrence_d2h_or_host_state_branch: bool
    solve_record_semantics_interpreted: Literal[False] = False
    general_restart_history_parity_verified: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportReceiptV2:
    status: CompletionExportStatusV2
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresCompletionExportReasonV2 | None
    bindings: HipFgmresCompletionExportBindingsV2
    dimensions: HipFgmresCompletionExportDimensionsV2
    buffers: tuple[HipFgmresCompletionExportBufferV2, ...]
    telemetry: HipFgmresCompletionExportTelemetryV2
    claims: HipFgmresCompletionExportClaimsV2
    payload_hash: str
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V2

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_completion_export_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportResultV2:
    receipt: HipFgmresCompletionExportReceiptV2
    solution_x: bytes
    true_residual: bytes
    solve_record: bytes
    checkpoint_solution_history: bytes
    checkpoint_true_residual_history: bytes
    payload_hash: str
    base_export: HipFgmresCompletionExportResultV1
    history_export: HipFgmresCheckpointHistoryResultV1

    @property
    def solution_x_array(self) -> np.ndarray:
        return np.frombuffer(self.solution_x, dtype="<f8")

    @property
    def true_residual_array(self) -> np.ndarray:
        return np.frombuffer(self.true_residual, dtype="<f8")

    @property
    def solve_record_array(self) -> np.ndarray:
        return np.frombuffer(self.solve_record, dtype="|u1")

    @property
    def checkpoint_solution_array(self) -> np.ndarray:
        return self.history_export.solution.vector_array

    @property
    def checkpoint_true_residual_array(self) -> np.ndarray:
        return self.history_export.true_residual.vector_array

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_completion_export_result_v2(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportOpenResultV2:
    context: HipFgmresCompletionExportExecutionContextV2
    receipt: HipFgmresCompletionExportReceiptV2

    @property
    def ready(self) -> bool:
        context = self.context
        with context._lock:
            return (
                self.receipt.status == "context_ready"
                and context._state == "context_ready"
                and not context._closed
            )


class HipFgmresCompletionExportExecutionContextV2:
    """Composite owner for one history export plus one retained v1 export."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Completion export v2 contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._global: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._history: HipFgmresCheckpointHistoryExecutionContextV1 | None = None
        self._base: HipFgmresCompletionExportExecutionContextV1 | None = None
        self._bindings: HipFgmresCompletionExportBindingsV2 | None = None
        self._dimensions: HipFgmresCompletionExportDimensionsV2 | None = None
        self._context_id = _ZERO_HASH
        self._actual_backend: Literal["hip", "test_double"] = "test_double"
        self._state: CompletionExportStatusV2 = "context_ready"
        self._reason: HipFgmresCompletionExportReasonV2 | None = None
        self._result: HipFgmresCompletionExportResultV2 | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def result(self) -> HipFgmresCompletionExportResultV2 | None:
        return self._result

    def receipt(self) -> HipFgmresCompletionExportReceiptV2:
        with self._lock:
            if self._result is not None and not self._closed:
                return self._result.receipt
            return self._build_receipt(
                self._state,
                base_result=(
                    None if self._result is None else self._result.base_export
                ),
                history_result=(
                    None if self._result is None else self._result.history_export
                ),
            )

    def export_completion_buffers(self) -> HipFgmresCompletionExportResultV2:
        with self._lock:
            if self._result is not None:
                return self._result
            if self._closed or self._state != "context_ready":
                _fail(
                    "hip_fgmres_completion_export_v2_state_invalid",
                    "/export",
                    cleanup_owner=self,
                )
            try:
                history_result = self._require_history().export()
                base_result = self._require_base().export()
            except BaseException as exc:
                self._state = "poisoned"
                self._reason = HipFgmresCompletionExportReasonV2(
                    "hip_fgmres_completion_export_v2_nested_export_failed",
                    _detail(exc),
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresCompletionExportV2Error(
                    self._reason.code,
                    "/export/nested",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            validate_hip_fgmres_completion_export_result_v1(base_result)
            validate_hip_fgmres_checkpoint_history_result_v1(history_result)
            payloads = (
                base_result.solution_x,
                base_result.true_residual,
                base_result.solve_record,
                history_result.checkpoint_solution_history,
                history_result.checkpoint_true_residual_history,
            )
            payload_hash = _bundle_hash(payloads)
            buffers = _buffer_descriptors(base_result, history_result, payloads)
            receipt = self._build_receipt(
                "exported",
                base_result=base_result,
                history_result=history_result,
                buffers=buffers,
                payload_hash=payload_hash,
            )
            result = HipFgmresCompletionExportResultV2(
                receipt=receipt,
                solution_x=payloads[0],
                true_residual=payloads[1],
                solve_record=payloads[2],
                checkpoint_solution_history=payloads[3],
                checkpoint_true_residual_history=payloads[4],
                payload_hash=payload_hash,
                base_export=base_result,
                history_export=history_result,
            )
            validate_hip_fgmres_completion_export_result_v2(result)
            self._result = result
            self._state = "exported"
            return result

    def export(self) -> HipFgmresCompletionExportResultV2:
        return self.export_completion_buffers()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            errors: list[BaseException] = []
            for owner in (self._base, self._history):
                if owner is None or owner.closed:
                    continue
                try:
                    owner.close()
                except BaseException as exc:
                    errors.append(exc)
            if errors:
                self._state = "cleanup_failed"
                self._reason = HipFgmresCompletionExportReasonV2(
                    "hip_fgmres_completion_export_v2_cleanup_failed",
                    _detail(errors[0]),
                )
                first = errors[0]
                if not isinstance(first, Exception):
                    raise first
                raise HipFgmresCompletionExportV2Error(
                    self._reason.code,
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from first
            self._closed = True
            self._state = "context_closed"

    def _require_history(self) -> HipFgmresCheckpointHistoryExecutionContextV1:
        if type(self._history) is not HipFgmresCheckpointHistoryExecutionContextV1:
            _fail(
                "hip_fgmres_completion_export_v2_history_missing",
                "/history",
                cleanup_owner=self,
            )
        return self._history

    def _require_base(self) -> HipFgmresCompletionExportExecutionContextV1:
        if type(self._base) is not HipFgmresCompletionExportExecutionContextV1:
            _fail(
                "hip_fgmres_completion_export_v2_base_missing",
                "/base",
                cleanup_owner=self,
            )
        return self._base

    def _build_receipt(
        self,
        status: CompletionExportStatusV2,
        *,
        base_result: HipFgmresCompletionExportResultV1 | None = None,
        history_result: HipFgmresCheckpointHistoryResultV1 | None = None,
        buffers: tuple[HipFgmresCompletionExportBufferV2, ...] = (),
        payload_hash: str = _ZERO_HASH,
    ) -> HipFgmresCompletionExportReceiptV2:
        if self._bindings is None or self._dimensions is None:
            _fail(
                "hip_fgmres_completion_export_v2_receipt_unavailable",
                "/receipt",
                cleanup_owner=self,
            )
        exported = status == "exported"
        healthy = status in {"context_ready", "exported", "context_closed"}
        if exported and (base_result is None or history_result is None):
            _fail(
                "hip_fgmres_completion_export_v2_nested_result_missing",
                "/receipt",
                cleanup_owner=self,
            )
        telemetry = _telemetry(base_result, history_result)
        claims = HipFgmresCompletionExportClaimsV2(
            retained_completion_export_v1_validated=healthy,
            checkpoint_history_export_v1_validated=healthy,
            same_global_context_bound=healthy,
            exact_five_buffer_roles_bound=exported,
            exact_five_blocking_completion_copies=exported,
            immutable_detached_payloads=exported,
            per_restart_checkpoint_solution_exported=exported,
            per_restart_checkpoint_true_residual_exported=exported,
            no_composite_device_allocation_or_kernel=healthy,
            no_recurrence_d2h_or_host_state_branch=healthy,
        )
        draft = HipFgmresCompletionExportReceiptV2(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V2,
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=None if healthy else self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            buffers=buffers,
            telemetry=telemetry,
            claims=claims,
            payload_hash=payload_hash,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


_CONTEXT_MINT = object()


def open_hip_fgmres_completion_export_context_v2(
    global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
    completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    history_context: HipFgmresCheckpointHistoryExecutionContextV1,
) -> HipFgmresCompletionExportOpenResultV2:
    """Reserve retained v1 export and compose it with one live history child."""

    if type(global_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
        _fail("hip_fgmres_completion_export_v2_global_invalid", "/global_context")
    if type(history_context) is not HipFgmresCheckpointHistoryExecutionContextV1:
        _fail("hip_fgmres_completion_export_v2_history_invalid", "/history_context")
    validate_hip_fgmres_global_recurrence_completion_capability_v1(
        completion_capability,
        expected_context=global_context,
    )
    if (
        history_context._global is not global_context
        or history_context.closed
        or history_context._reason is not None
    ):
        _fail(
            "hip_fgmres_completion_export_v2_history_binding_invalid",
            "/history_context",
        )
    base_open = open_hip_fgmres_completion_export_context_v1(
        global_context,
        completion_capability,
    )
    context = HipFgmresCompletionExportExecutionContextV2(_mint=_CONTEXT_MINT)
    context._global = global_context
    context._history = history_context
    context._base = base_open.context
    try:
        base_receipt = base_open.receipt
        history_receipt = history_context.receipt()
        if (
            base_receipt.actual_backend != history_receipt.actual_backend
            or base_receipt.bindings.global_context_id
            != history_receipt.bindings.global_context_id
            or base_receipt.bindings.global_context_id
            != completion_capability.context_id
            or base_receipt.dimensions.free_dof_count
            != history_receipt.dimensions.free_dof_count
            or base_receipt.dimensions.maximum_restart_count
            != history_receipt.dimensions.maximum_restart_count
        ):
            _fail(
                "hip_fgmres_completion_export_v2_nested_binding_mismatch",
                "/bindings",
                cleanup_owner=context,
            )
        context._actual_backend = base_receipt.actual_backend
        context._bindings = HipFgmresCompletionExportBindingsV2(
            global_context_id=completion_capability.context_id,
            global_completion_receipt_hash=completion_capability.receipt_hash,
            base_export_context_id=base_receipt.context_id,
            base_export_open_receipt_hash=base_receipt.receipt_hash,
            history_context_id=history_receipt.context_id,
            history_open_receipt_hash=history_receipt.receipt_hash,
            history_plan_hash=history_receipt.bindings.history_plan_hash,
            history_blob_abi_hash=history_receipt.bindings.history_blob_abi_hash,
            recurrence_plan_hash=base_receipt.bindings.recurrence_plan_hash,
            recurrence_kernel_identity_hash=(
                base_receipt.bindings.kernel_identity_hash
            ),
            architecture=base_receipt.bindings.architecture,
            device_ordinal=base_receipt.bindings.device_ordinal,
            copy_api=HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V2,
        )
        base_bytes = base_receipt.dimensions.total_export_byte_count
        history_bytes = history_receipt.dimensions.owned_device_byte_count
        context._dimensions = HipFgmresCompletionExportDimensionsV2(
            free_dof_count=base_receipt.dimensions.free_dof_count,
            maximum_restart_count=base_receipt.dimensions.maximum_restart_count,
            solution_byte_count=base_receipt.dimensions.solution_byte_count,
            true_residual_byte_count=(base_receipt.dimensions.true_residual_byte_count),
            solve_record_byte_count=base_receipt.dimensions.solve_record_byte_count,
            checkpoint_solution_history_byte_count=(
                history_receipt.dimensions.history_blob_byte_count
            ),
            checkpoint_true_residual_history_byte_count=(
                history_receipt.dimensions.history_blob_byte_count
            ),
            base_export_byte_count=base_bytes,
            history_export_byte_count=history_bytes,
            total_export_byte_count=base_bytes + history_bytes,
        )
        context._context_id = canonical_hash(
            {
                "schema_version": HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V2,
                "global_context_id": completion_capability.context_id,
                "base_export_context_id": base_receipt.context_id,
                "history_context_id": history_receipt.context_id,
                "history_plan_hash": history_receipt.bindings.history_plan_hash,
            }
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_completion_export_receipt_v2(receipt)
        return HipFgmresCompletionExportOpenResultV2(context, receipt)
    except BaseException as primary:
        try:
            context.close()
        except BaseException as cleanup:
            if not isinstance(cleanup, Exception):
                raise
            raise HipFgmresCompletionExportV2Error(
                "hip_fgmres_completion_export_v2_open_cleanup_failed",
                "/open/cleanup",
                f"open failed: {_detail(primary)}; cleanup failed: {_detail(cleanup)}",
                cleanup_owner=context,
            ) from cleanup
        raise


def validate_hip_fgmres_completion_export_receipt_v2(
    receipt: HipFgmresCompletionExportReceiptV2,
) -> HipFgmresCompletionExportReceiptV2:
    if type(receipt) is not HipFgmresCompletionExportReceiptV2:
        _fail("hip_fgmres_completion_export_v2_receipt_type_invalid", "/")
    if (
        receipt.evidence_scope != HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V2
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
        _fail("hip_fgmres_completion_export_v2_receipt_invalid", "/")
    _validate_schema(_receipt_payload(receipt, include_hash=True))
    dimensions = receipt.dimensions
    base_bytes = (
        dimensions.solution_byte_count
        + dimensions.true_residual_byte_count
        + dimensions.solve_record_byte_count
    )
    history_bytes = (
        dimensions.checkpoint_solution_history_byte_count
        + dimensions.checkpoint_true_residual_history_byte_count
    )
    if (
        dimensions.free_dof_count <= 0
        or dimensions.maximum_restart_count <= 0
        or dimensions.solution_byte_count != 8 * dimensions.free_dof_count
        or dimensions.true_residual_byte_count != 8 * dimensions.free_dof_count
        or dimensions.base_export_byte_count != base_bytes
        or dimensions.history_export_byte_count != history_bytes
        or dimensions.total_export_byte_count != base_bytes + history_bytes
        or dimensions.exported_buffer_count != 5
    ):
        _fail("hip_fgmres_completion_export_v2_dimensions_invalid", "/dimensions")
    exported = receipt.status == "exported"
    if (
        (len(receipt.buffers) == 5) is not exported
        or (receipt.payload_hash != _ZERO_HASH) is not exported
        or (receipt.reason is None)
        is not (receipt.status in {"context_ready", "exported", "context_closed"})
        or receipt.claims.exact_five_buffer_roles_bound is not exported
        or receipt.claims.exact_five_blocking_completion_copies is not exported
        or receipt.claims.immutable_detached_payloads is not exported
        or receipt.claims.per_restart_checkpoint_solution_exported is not exported
        or receipt.claims.per_restart_checkpoint_true_residual_exported is not exported
        or receipt.claims.solve_record_semantics_interpreted is not False
        or receipt.claims.general_restart_history_parity_verified is not False
        or receipt.claims.solution_ready is not False
        or receipt.claims.result_ir_ready is not False
        or receipt.claims.performance_or_speedup_proven is not False
        or receipt.claims.commercial_ready is not False
        or receipt.claims.promotion_eligible is not False
    ):
        _fail("hip_fgmres_completion_export_v2_claim_invalid", "/claims")
    telemetry = receipt.telemetry
    if any(
        (
            telemetry.composite_device_allocation_count,
            telemetry.composite_h2d_operation_count,
            telemetry.composite_kernel_launch_count,
            telemetry.composite_explicit_stream_sync_count,
            telemetry.composite_fallback_count,
            telemetry.numerical_content_branch_count,
        )
    ):
        _fail("hip_fgmres_completion_export_v2_telemetry_invalid", "/telemetry")
    if exported and (
        telemetry.base_blocking_d2h_attempt_count != 3
        or telemetry.base_blocking_d2h_success_count != 3
        or telemetry.history_blocking_d2h_attempt_count != 2
        or telemetry.history_blocking_d2h_success_count != 2
        or telemetry.total_blocking_d2h_attempt_count != 5
        or telemetry.total_blocking_d2h_success_count != 5
        or telemetry.base_d2h_byte_count != dimensions.base_export_byte_count
        or telemetry.history_d2h_byte_count != dimensions.history_export_byte_count
        or telemetry.total_d2h_byte_count != dimensions.total_export_byte_count
    ):
        _fail("hip_fgmres_completion_export_v2_telemetry_invalid", "/telemetry")
    return receipt


def validate_hip_fgmres_completion_export_result_v2(
    result: HipFgmresCompletionExportResultV2,
) -> HipFgmresCompletionExportResultV2:
    if type(result) is not HipFgmresCompletionExportResultV2:
        _fail("hip_fgmres_completion_export_v2_result_type_invalid", "/")
    receipt = validate_hip_fgmres_completion_export_receipt_v2(result.receipt)
    base = validate_hip_fgmres_completion_export_result_v1(result.base_export)
    history = validate_hip_fgmres_checkpoint_history_result_v1(result.history_export)
    payloads = (
        result.solution_x,
        result.true_residual,
        result.solve_record,
        result.checkpoint_solution_history,
        result.checkpoint_true_residual_history,
    )
    if (
        receipt.status != "exported"
        or any(type(row) is not bytes for row in payloads)
        or result.payload_hash != receipt.payload_hash
        or result.payload_hash != _bundle_hash(payloads)
        or payloads[:3] != (base.solution_x, base.true_residual, base.solve_record)
        or payloads[3:]
        != (
            history.checkpoint_solution_history,
            history.checkpoint_true_residual_history,
        )
    ):
        _fail("hip_fgmres_completion_export_v2_result_invalid", "/")
    for index, (descriptor, role, dtype, payload) in enumerate(
        zip(receipt.buffers, _ROLES, _DTYPES, payloads, strict=True)
    ):
        expected_nested_hash = (
            base.receipt.receipt_hash if index < 3 else history.receipt.receipt_hash
        )
        expected_nested_index = index if index < 3 else index - 3
        if (
            descriptor.role != role
            or descriptor.dtype != dtype
            or descriptor.byte_count != len(payload)
            or descriptor.payload_sha256 != _sha256(payload)
            or descriptor.nested_receipt_hash != expected_nested_hash
            or descriptor.nested_buffer_index != expected_nested_index
        ):
            _fail("hip_fgmres_completion_export_v2_buffer_invalid", "/buffers")
    return result


def _telemetry(
    base: HipFgmresCompletionExportResultV1 | None,
    history: HipFgmresCheckpointHistoryResultV1 | None,
) -> HipFgmresCompletionExportTelemetryV2:
    if base is None or history is None:
        return HipFgmresCompletionExportTelemetryV2(0, 0, 0, 0, 0, 0, 0, 0, 0)
    base_row = base.receipt.telemetry
    history_row = history.receipt.telemetry
    base_bytes = base_row.d2h_bytes_succeeded
    history_bytes = history_row.d2h_bytes_succeeded
    return HipFgmresCompletionExportTelemetryV2(
        base_blocking_d2h_attempt_count=base_row.d2h_operation_attempt_count,
        base_blocking_d2h_success_count=base_row.d2h_operation_success_count,
        history_blocking_d2h_attempt_count=history_row.d2h_operation_attempt_count,
        history_blocking_d2h_success_count=history_row.d2h_operation_success_count,
        total_blocking_d2h_attempt_count=(
            base_row.d2h_operation_attempt_count
            + history_row.d2h_operation_attempt_count
        ),
        total_blocking_d2h_success_count=(
            base_row.d2h_operation_success_count
            + history_row.d2h_operation_success_count
        ),
        base_d2h_byte_count=base_bytes,
        history_d2h_byte_count=history_bytes,
        total_d2h_byte_count=base_bytes + history_bytes,
    )


def _buffer_descriptors(
    base: HipFgmresCompletionExportResultV1,
    history: HipFgmresCheckpointHistoryResultV1,
    payloads: tuple[bytes, bytes, bytes, bytes, bytes],
) -> tuple[HipFgmresCompletionExportBufferV2, ...]:
    return tuple(
        HipFgmresCompletionExportBufferV2(
            role=role,  # type: ignore[arg-type]
            dtype=dtype,  # type: ignore[arg-type]
            byte_count=len(payload),
            payload_sha256=_sha256(payload),
            nested_receipt_hash=(
                base.receipt.receipt_hash if index < 3 else history.receipt.receipt_hash
            ),
            nested_buffer_index=index if index < 3 else index - 3,
        )
        for index, (role, dtype, payload) in enumerate(
            zip(_ROLES, _DTYPES, payloads, strict=True)
        )
    )


def _receipt_payload(
    receipt: HipFgmresCompletionExportReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V2,
        "capability_profile": HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V2,
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


def _bundle_hash(payloads: tuple[bytes, bytes, bytes, bytes, bytes]) -> str:
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
        _fail("hip_fgmres_completion_export_v2_schema_invalid", path, error.message)


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresCompletionExportExecutionContextV2 | None = None,
) -> NoReturn:
    raise HipFgmresCompletionExportV2Error(
        code,
        path,
        message or code,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V2",
    "HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V2",
    "HipFgmresCompletionExportBindingsV2",
    "HipFgmresCompletionExportBufferV2",
    "HipFgmresCompletionExportClaimsV2",
    "HipFgmresCompletionExportDimensionsV2",
    "HipFgmresCompletionExportExecutionContextV2",
    "HipFgmresCompletionExportOpenResultV2",
    "HipFgmresCompletionExportReasonV2",
    "HipFgmresCompletionExportReceiptV2",
    "HipFgmresCompletionExportResultV2",
    "HipFgmresCompletionExportTelemetryV2",
    "HipFgmresCompletionExportV2Error",
    "open_hip_fgmres_completion_export_context_v2",
    "validate_hip_fgmres_completion_export_receipt_v2",
    "validate_hip_fgmres_completion_export_result_v2",
]
