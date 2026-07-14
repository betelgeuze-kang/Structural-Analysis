"""Completion-only raw output export for the HIP FGMRES recurrence.

The exporter consumes one process-local global-recurrence completion capability
and performs exactly three blocking device-to-host copies after the recurrence
fence: ``solution_x``, ``true_residual``, and the opaque ``solve_record``.  It
does not parse the record, branch on numerical content, establish terminal
status, verify parity, or declare a solution ready.

Blocking ``hipMemcpy`` is deliberate in this first product slice.  No DMA is
left pending after a copy call returns, so abandoned exporters cannot outlive
their private host staging buffers or the upstream device allocations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache, wraps
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.hip.context import (
    _BoundBlockingD2HCopy,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    HipFgmresGlobalRecurrenceExecutionContextV1,
    _CompletionExportChildAuthorityV1,
    _mint_completion_export_child_lease_v1,
    validate_hip_fgmres_global_recurrence_completion_capability_v1,
)
from .fgmres_recurrence_plan_v2 import hip_fgmres_solve_record_abi_payload_v2
from .fgmres_rtc_v2 import solve_record_byte_length_v2


HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-completion-export.v1"
)
HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V1 = (
    "phase0_fenced_completion_three_buffer_blocking_d2h_export"
)
HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V1 = (
    "fenced_completion_bytes_exported_outcome_uninterpreted_non_promoting"
)
HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V1 = "hipMemcpyDeviceToHost_blocking"

CompletionExportStatusV1 = Literal[
    "context_ready",
    "exported",
    "poisoned",
    "context_closed",
    "cleanup_failed",
]

_SOURCE_ROLES = ("solution_x", "true_residual", "solve_record")
_ROLE_DTYPES = {
    "solution_x": "<f8",
    "true_residual": "<f8",
    "solve_record": "|u1",
}
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCHEMA_RESOURCE = "hip_fgmres_completion_export_v1.schema.json"
_CONTEXT_MINT = object()
_PAYLOAD_DOMAIN = b"structural-analysis-hip-fgmres-completion-export.v1\0"


class HipFgmresCompletionExportV1Error(RuntimeError):
    """Stable export error retaining the exact cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresCompletionExportExecutionContextV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportBindingsV1:
    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    continuation_schedule_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    solve_record_abi_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    source_binding_hash: str
    architecture: str
    device_ordinal: int
    copy_api: Literal["hipMemcpyDeviceToHost_blocking"]
    completion_capability_identity_serialized: Literal[False] = False
    device_pointer_values_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportDimensionsV1:
    free_dof_count: int
    maximum_restart_count: int
    solution_byte_count: int
    true_residual_byte_count: int
    solve_record_byte_count: int
    total_export_byte_count: int
    exported_buffer_count: Literal[3] = 3

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportBufferV1:
    role: Literal["solution_x", "true_residual", "solve_record"]
    dtype: Literal["<f8", "|u1"]
    shape: tuple[int, ...]
    byte_count: int
    allocation_generation: int
    source_lineage_hash: str
    payload_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "byte_count": self.byte_count,
            "allocation_generation": self.allocation_generation,
            "source_lineage_hash": self.source_lineage_hash,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportTelemetryV1:
    completion_capability_reservation_count: Literal[1] = 1
    completion_capability_consume_count: int = 0
    host_staging_allocation_count: int = 0
    d2h_operation_attempt_count: int = 0
    d2h_operation_success_count: int = 0
    d2h_bytes_attempted: int = 0
    d2h_bytes_succeeded: int = 0
    blocking_copy_completion_count: int = 0
    device_allocation_count: Literal[0] = 0
    allocation_borrow_count: Literal[0] = 0
    h2d_operation_count: Literal[0] = 0
    kernel_launch_count: Literal[0] = 0
    explicit_stream_sync_count: Literal[0] = 0
    fallback_count: Literal[0] = 0
    numerical_content_branch_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportClaimsV1:
    global_fenced_completion_bound: bool
    completion_capability_consumed: bool
    exact_three_source_lineages_bound: bool
    raw_completion_buffers_host_materialized: bool
    blocking_completion_only_d2h: bool
    immutable_detached_host_payload: bool
    no_device_allocation_or_borrow: bool
    no_h2d_or_kernel_launch: bool
    no_explicit_stream_synchronization: bool
    solve_record_semantics_interpreted: Literal[False] = False
    numerical_content_host_branch_performed: Literal[False] = False
    actual_terminal_outcome_host_observed: Literal[False] = False
    authoritative_terminal_status_proven: Literal[False] = False
    numerical_parity_verified: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportReceiptV1:
    status: CompletionExportStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresCompletionExportReasonV1 | None
    bindings: HipFgmresCompletionExportBindingsV1
    dimensions: HipFgmresCompletionExportDimensionsV1
    buffers: tuple[HipFgmresCompletionExportBufferV1, ...]
    telemetry: HipFgmresCompletionExportTelemetryV1
    claims: HipFgmresCompletionExportClaimsV1
    payload_hash: str
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_completion_export_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportResultV1:
    receipt: HipFgmresCompletionExportReceiptV1
    solution_x: bytes
    true_residual: bytes
    solve_record: bytes
    payload_hash: str

    @property
    def solution_x_array(self) -> np.ndarray:
        return np.frombuffer(self.solution_x, dtype="<f8")

    @property
    def true_residual_array(self) -> np.ndarray:
        return np.frombuffer(self.true_residual, dtype="<f8")

    @property
    def solve_record_array(self) -> np.ndarray:
        return np.frombuffer(self.solve_record, dtype="|u1")

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_completion_export_result_v1(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresCompletionExportOpenResultV1:
    context: HipFgmresCompletionExportExecutionContextV1
    receipt: HipFgmresCompletionExportReceiptV1

    @property
    def ready(self) -> bool:
        context = self.context
        with context._lock:
            return (
                self.receipt.status == "context_ready"
                and context._state == "context_ready"
                and not context._closed
                and not context._child_released
            )


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _CompletionExportPolicySnapshotV1:
    """Private value-only copy of the exact recurrence decision policy."""

    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    stagnation_checkpoint_limit: int
    absolute_tolerance: float
    relative_tolerance: float
    authoritative_tolerance: float
    stagnation_relative_tolerance: float
    divergence_factor: float


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _CompletionExportPublishedResultAuthorityV1:
    """Private identity seal for one fully published detached result."""

    result: HipFgmresCompletionExportResultV1
    receipt: HipFgmresCompletionExportReceiptV1
    solution_x: bytes
    true_residual: bytes
    solve_record: bytes
    receipt_hash: str
    payload_hash: str
    buffer_payload_hashes: tuple[str, str, str]
    policy: _CompletionExportPolicySnapshotV1


def _guard_state_change(name: str) -> Any:
    def decorate(operation: Any) -> Any:
        @wraps(operation)
        def guarded(
            self: HipFgmresCompletionExportExecutionContextV1,
            *arguments: Any,
            **keywords: Any,
        ) -> Any:
            with self._lock:
                if self._active_operation is not None:
                    _fail(
                        "hip_fgmres_completion_export_operation_reentrant",
                        f"/{name}/operation",
                        cleanup_owner=self,
                    )
                self._active_operation = name
                try:
                    return operation(self, *arguments, **keywords)
                except BaseException as exc:
                    if self._closed:
                        self._state = "context_closed"
                    elif name == "export" and self._result is not None:
                        self._state = "exported"
                    elif name == "export" and self._publication is not None:
                        self._state = "publication_pending"
                    elif (
                        name == "export"
                        and self._telemetry.completion_capability_consume_count == 1
                        and self._state != "poisoned"
                    ):
                        self._poison(
                            "post_consume_export_interrupted",
                            _detail(exc),
                        )
                    elif (
                        name == "export"
                        and self._telemetry.completion_capability_consume_count == 0
                        and self._state == "context_ready"
                    ):
                        self._staging = None
                        self._telemetry = replace(
                            self._telemetry,
                            host_staging_allocation_count=0,
                        )
                    if name == "export" and isinstance(exc, Exception):
                        if (
                            isinstance(exc, HipFgmresCompletionExportV1Error)
                            and exc.cleanup_owner is self
                        ):
                            raise
                        raise HipFgmresCompletionExportV1Error(
                            "hip_fgmres_completion_export_upstream_failed",
                            "/export/upstream",
                            _detail(exc)
                            or "hip_fgmres_completion_export_upstream_failed",
                            cleanup_owner=self,
                        ) from exc
                    raise
                finally:
                    self._active_operation = None

        return guarded

    return decorate


class HipFgmresCompletionExportExecutionContextV1:
    """Single-use owner of three synchronous post-fence D2H copies."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Completion export contexts are factory-issued only.")
        self._lock = threading.RLock()
        self._global: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._completion: HipFgmresGlobalRecurrenceCompletionCapabilityV1 | None = None
        self._token = _mint_completion_export_child_lease_v1()
        self._authority: _CompletionExportChildAuthorityV1 | None = None
        self._authority_snapshot: tuple[Any, ...] | None = None
        self._copy_method: Any | None = None
        self._copy_method_snapshot: tuple[Any, ...] | None = None
        self._context_id = _ZERO_HASH
        self._actual_backend: Literal["hip", "test_double"] = "test_double"
        self._bindings: HipFgmresCompletionExportBindingsV1 | None = None
        self._dimensions: HipFgmresCompletionExportDimensionsV1 | None = None
        self._telemetry = HipFgmresCompletionExportTelemetryV1()
        self._state: str = "context_ready"
        self._reason: HipFgmresCompletionExportReasonV1 | None = None
        self._staging: tuple[np.ndarray, ...] | None = None
        self._publication: HipFgmresCompletionExportResultV1 | None = None
        self._result: HipFgmresCompletionExportResultV1 | None = None
        self._published_result_authority_state: (
            tuple[_CompletionExportPublishedResultAuthorityV1, tuple[Any, ...]] | None
        ) = None
        self._child_released = False
        self._closed = False
        self._active_operation: str | None = None
        self._consumption_reconciliation_failed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def result(self) -> HipFgmresCompletionExportResultV1 | None:
        return self._result if self._state == "exported" else None

    def receipt(self) -> HipFgmresCompletionExportReceiptV1:
        with self._lock:
            if self._consumption_reconciliation_failed:
                _fail(
                    "hip_fgmres_completion_export_consumption_reconciliation_required",
                    "/receipt/consume",
                    cleanup_owner=self,
                )
            if self._active_operation is not None:
                _fail(
                    "hip_fgmres_completion_export_receipt_inflight",
                    "/receipt/operation",
                    cleanup_owner=self,
                )
            if not self._closed:
                publication = self._result or self._publication
                if publication is not None:
                    return publication.receipt
            return self._build_receipt(self._public_status())

    @_guard_state_change("export")
    def export_completion_buffers(self) -> HipFgmresCompletionExportResultV1:
        """Consume completion and publish three detached opaque byte snapshots."""

        with self._lock:
            if self._closed:
                _fail(
                    "hip_fgmres_completion_export_state_invalid",
                    "/export",
                    cleanup_owner=self,
                )
            if self._result is not None:
                return self._result
            if self._publication is not None:
                return self._finish_publication()
            if self._state != "context_ready":
                _fail(
                    "hip_fgmres_completion_export_state_invalid",
                    "/export",
                    cleanup_owner=self,
                )
            authority = self._require_authority(consumed=False)
            sources = authority.source_capabilities
            try:
                staging = _allocate_host_staging(sources)
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresCompletionExportV1Error(
                    "hip_fgmres_completion_export_host_staging_allocation_failed",
                    "/export/staging",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            self._staging = staging
            self._telemetry = replace(
                self._telemetry,
                host_staging_allocation_count=len(staging),
            )
            parent = self._require_global()
            completion = self._require_completion()
            try:
                parent._consume_completion_export_capability(
                    self._token,
                    completion,
                )
                self._record_consumed()
            except BaseException as exc:
                consumed = False
                try:
                    consumed = parent._completion_export_capability_is_consumed(
                        self._token
                    )
                except BaseException as reconcile:
                    self._consumption_reconciliation_failed = True
                    self._state = "cleanup_failed"
                    self._reason = HipFgmresCompletionExportReasonV1(
                        "hip_fgmres_completion_export_consume_reconcile_failed",
                        _detail(
                            f"consume failed: {_detail(exc)}; reconciliation "
                            f"failed: {_detail(reconcile)}"
                        ),
                    )
                    if not isinstance(reconcile, Exception):
                        raise
                    raise HipFgmresCompletionExportV1Error(
                        self._reason.code,
                        "/export/consume/reconcile",
                        self._reason.detail,
                        cleanup_owner=self,
                    ) from reconcile
                if consumed:
                    self._record_consumed()
                    self._poison("completion_consume_return_lost", _detail(exc))
                if not isinstance(exc, Exception) or not consumed:
                    raise
                raise HipFgmresCompletionExportV1Error(
                    "hip_fgmres_completion_export_consume_failed",
                    "/export/consume",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc

            self._state = "export_in_progress"
            authority = self._require_authority(consumed=True)
            sources = authority.source_capabilities
            copy_method = self._require_copy_method(authority)

            for index, (source, target) in enumerate(
                zip(sources, staging, strict=True)
            ):
                self._require_authority(consumed=True)
                self._require_copy_method(authority)
                attempted = self._telemetry
                self._telemetry = replace(
                    attempted,
                    d2h_operation_attempt_count=(
                        attempted.d2h_operation_attempt_count + 1
                    ),
                    d2h_bytes_attempted=(
                        attempted.d2h_bytes_attempted + int(source.nbytes)
                    ),
                )
                try:
                    copy_method(target, source.pointer_snapshot)
                    succeeded = self._telemetry
                    self._telemetry = replace(
                        succeeded,
                        d2h_operation_success_count=(
                            succeeded.d2h_operation_success_count + 1
                        ),
                        d2h_bytes_succeeded=(
                            succeeded.d2h_bytes_succeeded + int(source.nbytes)
                        ),
                        blocking_copy_completion_count=(
                            succeeded.blocking_copy_completion_count + 1
                        ),
                    )
                except BaseException as exc:
                    self._poison(
                        f"blocking_copy_{_SOURCE_ROLES[index]}_failed",
                        _detail(exc),
                    )
                    if not isinstance(exc, Exception):
                        raise
                    raise HipFgmresCompletionExportV1Error(
                        "hip_fgmres_completion_export_copy_failed",
                        f"/export/{_SOURCE_ROLES[index]}",
                        _detail(exc),
                        cleanup_owner=self,
                    ) from exc

            self._require_authority(consumed=True)
            payloads = tuple(bytes(memoryview(target).cast("B")) for target in staging)
            payload_hash = _bundle_hash(payloads)
            buffers = self._buffer_descriptors(payloads)
            receipt = self._build_receipt(
                "exported",
                buffers=buffers,
                payload_hash=payload_hash,
            )
            publication = HipFgmresCompletionExportResultV1(
                receipt=receipt,
                solution_x=payloads[0],
                true_residual=payloads[1],
                solve_record=payloads[2],
                payload_hash=payload_hash,
            )
            validate_hip_fgmres_completion_export_result_v1(publication)
            self._publication = publication
            self._state = "publication_pending"
            return self._finish_publication()

    def export(self) -> HipFgmresCompletionExportResultV1:
        return self.export_completion_buffers()

    @_guard_state_change("cleanup")
    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if not self._child_released:
                    parent = self._require_global()
                    if self._consumption_reconciliation_failed:
                        consumed = parent._completion_export_capability_is_consumed(
                            self._token
                        )
                        if consumed:
                            self._record_consumed()
                        else:
                            self._staging = None
                            self._telemetry = replace(
                                self._telemetry,
                                host_staging_allocation_count=0,
                            )
                        self._consumption_reconciliation_failed = False
                    self._release_child()
            except Exception as exc:
                self._state = "cleanup_failed"
                code = "hip_fgmres_completion_export_cleanup_failed"
                self._reason = HipFgmresCompletionExportReasonV1(
                    code,
                    _detail(exc) or code,
                )
                raise HipFgmresCompletionExportV1Error(
                    self._reason.code,
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._staging = None
            self._closed = True
            self._state = "context_closed"

    def _finish_publication(self) -> HipFgmresCompletionExportResultV1:
        publication = self._publication
        if publication is None:
            _fail(
                "hip_fgmres_completion_export_publication_missing",
                "/export/publication",
                cleanup_owner=self,
            )
        validate_hip_fgmres_completion_export_result_v1(publication)
        authority = self._require_authority(consumed=True)
        seal = _published_result_authority(
            publication,
            _completion_export_policy_snapshot(authority),
        )
        seal_snapshot = _published_result_authority_snapshot(seal)
        authority_state = self._published_result_authority_state
        if authority_state is None:
            self._published_result_authority_state = (seal, seal_snapshot)
        elif (
            _published_result_authority_snapshot(authority_state[0])
            != authority_state[1]
            or seal_snapshot != authority_state[1]
        ):
            _fail(
                "hip_fgmres_completion_export_publication_authority_changed",
                "/export/publication/authority",
                cleanup_owner=self,
            )
        # All three blocking copies have already been detached into immutable
        # ``bytes`` owned by ``publication``.  Release the temporary NumPy
        # staging before publishing the final result so large-F exports do not
        # retain a second host-side payload until ``close()``.
        self._staging = None
        self._result = publication
        self._state = "exported"
        return publication

    def _terminal_outcome_observation_authority(
        self,
        result: HipFgmresCompletionExportResultV1,
    ) -> _CompletionExportPublishedResultAuthorityV1:
        """Return the exact final-publication seal; intermediate publication fails."""

        with self._lock:
            authority_state = self._published_result_authority_state
            seal = None if authority_state is None else authority_state[0]
            snapshot = None if authority_state is None else authority_state[1]
            if (
                type(result) is not HipFgmresCompletionExportResultV1
                or self._result is not result
                or type(seal) is not _CompletionExportPublishedResultAuthorityV1
                or snapshot is None
                or _published_result_authority_snapshot(seal) != snapshot
                or seal.result is not result
                or seal.receipt is not result.receipt
                or seal.solution_x is not result.solution_x
                or seal.true_residual is not result.true_residual
                or seal.solve_record is not result.solve_record
                or seal.receipt_hash != result.receipt.receipt_hash
                or seal.payload_hash != result.payload_hash
                or seal.buffer_payload_hashes
                != tuple(row.payload_sha256 for row in result.receipt.buffers)
            ):
                _fail(
                    "hip_fgmres_completion_export_final_publication_invalid",
                    "/result",
                    cleanup_owner=self,
                )
            validate_hip_fgmres_completion_export_result_v1(result)
            return seal

    def _record_consumed(self) -> None:
        self._telemetry = replace(
            self._telemetry,
            completion_capability_consume_count=1,
        )

    def _release_child(self) -> None:
        if self._child_released:
            return
        parent = self._require_global()
        try:
            parent._release_completion_export_child(self._token)
        except BaseException as exc:
            try:
                still_active = parent._completion_export_child_token_is_active(
                    self._token
                )
            except BaseException:
                raise
            if still_active:
                raise
            self._child_released = True
            if not isinstance(exc, Exception):
                raise
            return
        self._child_released = True

    def _poison(self, code: str, detail: str) -> None:
        if self._reason is None:
            self._reason = HipFgmresCompletionExportReasonV1(
                code,
                _detail(detail or code),
            )
        self._state = "poisoned"

    def _require_authority(
        self,
        *,
        consumed: bool,
    ) -> _CompletionExportChildAuthorityV1:
        parent = self._require_global()
        capability = self._require_completion()
        current = parent._completion_export_child_authority(
            self._token,
            capability,
            consumed=consumed,
        )
        snapshot = _authority_snapshot(current)
        if (
            self._authority is None
            or self._authority_snapshot is None
            or snapshot != self._authority_snapshot
            or _authority_snapshot(self._authority) != self._authority_snapshot
        ):
            _fail(
                "hip_fgmres_completion_export_authority_changed",
                "/authority",
                cleanup_owner=self,
            )
        return current

    def _require_copy_method(
        self,
        authority: _CompletionExportChildAuthorityV1,
    ) -> Any:
        method = self._copy_method
        current = _resolve_copy_binding(authority.runtime, cleanup_owner=self)
        _validate_copy_binding_relationship(
            authority,
            current,
            actual_backend=self._actual_backend,
            cleanup_owner=self,
        )
        snapshot = _copy_method_snapshot(authority.runtime, current)
        if (
            method is None
            or self._copy_method_snapshot is None
            or current is not method
            or snapshot != self._copy_method_snapshot
        ):
            _fail(
                "hip_fgmres_completion_export_copy_binding_changed",
                "/authority/copy",
                cleanup_owner=self,
            )
        return method

    def _require_global(self) -> HipFgmresGlobalRecurrenceExecutionContextV1:
        parent = self._global
        if type(parent) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_completion_export_global_context_invalid",
                "/global_context",
                cleanup_owner=self,
            )
        return parent

    def _require_completion(
        self,
    ) -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
        capability = self._completion
        if type(capability) is not HipFgmresGlobalRecurrenceCompletionCapabilityV1:
            _fail(
                "hip_fgmres_completion_export_completion_invalid",
                "/completion",
                cleanup_owner=self,
            )
        return capability

    def _public_status(self) -> CompletionExportStatusV1:
        if self._state in {
            "context_ready",
            "exported",
            "poisoned",
            "context_closed",
            "cleanup_failed",
        }:
            return self._state  # type: ignore[return-value]
        if self._reason is not None:
            return "poisoned"
        return "context_ready"

    def _buffer_descriptors(
        self,
        payloads: tuple[bytes, ...] | None,
    ) -> tuple[HipFgmresCompletionExportBufferV1, ...]:
        authority = self._authority
        dimensions = self._dimensions
        if authority is None or dimensions is None:
            _fail(
                "hip_fgmres_completion_export_descriptor_unavailable",
                "/buffers",
                cleanup_owner=self,
            )
        shapes = (
            (dimensions.free_dof_count,),
            (dimensions.free_dof_count,),
            (dimensions.solve_record_byte_count,),
        )
        descriptors = []
        for index, (role, source, shape) in enumerate(
            zip(_SOURCE_ROLES, authority.source_capabilities, shapes, strict=True)
        ):
            payload_hash = (
                _ZERO_HASH if payloads is None else _sha256_bytes(payloads[index])
            )
            descriptors.append(
                HipFgmresCompletionExportBufferV1(
                    role=role,  # type: ignore[arg-type]
                    dtype=_ROLE_DTYPES[role],  # type: ignore[arg-type]
                    shape=shape,
                    byte_count=int(source.nbytes),
                    allocation_generation=int(source.generation),
                    source_lineage_hash=_source_lineage_hash(source),
                    payload_sha256=payload_hash,
                )
            )
        return tuple(descriptors)

    def _build_receipt(
        self,
        status: CompletionExportStatusV1,
        *,
        buffers: tuple[HipFgmresCompletionExportBufferV1, ...] | None = None,
        payload_hash: str = _ZERO_HASH,
    ) -> HipFgmresCompletionExportReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail(
                "hip_fgmres_completion_export_receipt_unavailable",
                "/receipt",
                cleanup_owner=self,
            )
        exported = status == "exported"
        consumed = self._telemetry.completion_capability_consume_count == 1
        bound = status not in {"context_closed", "cleanup_failed"}
        claims = HipFgmresCompletionExportClaimsV1(
            global_fenced_completion_bound=bound,
            completion_capability_consumed=consumed,
            exact_three_source_lineages_bound=bound,
            raw_completion_buffers_host_materialized=exported,
            blocking_completion_only_d2h=exported,
            immutable_detached_host_payload=exported,
            no_device_allocation_or_borrow=bound,
            no_h2d_or_kernel_launch=bound,
            no_explicit_stream_synchronization=bound,
        )
        draft = HipFgmresCompletionExportReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V1,
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            buffers=(self._buffer_descriptors(None) if buffers is None else buffers),
            telemetry=self._telemetry,
            claims=claims,
            payload_hash=payload_hash,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


def open_hip_fgmres_completion_export_context_v1(
    global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
    completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
) -> HipFgmresCompletionExportOpenResultV1:
    """Reserve one single-use completion exporter from a fenced global owner."""

    context = HipFgmresCompletionExportExecutionContextV1(_mint=_CONTEXT_MINT)
    reserved = False
    try:
        if type(global_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_completion_export_global_context_invalid",
                "/global_context",
            )
        context._global = global_context
        context._completion = completion_capability
        validate_hip_fgmres_global_recurrence_completion_capability_v1(
            completion_capability,
            expected_context=global_context,
        )
        acquired = global_context._reserve_completion_export_child(
            context._token,
            completion_capability,
        )
        if acquired is not context._token:
            _fail(
                "hip_fgmres_completion_export_reservation_changed",
                "/lifetime",
            )
        reserved = True
        authority = global_context._completion_export_child_authority(
            context._token,
            completion_capability,
            consumed=False,
        )
        _validate_authority_extents(authority)
        copy_method = _resolve_copy_binding(authority.runtime)
        actual_backend = global_context.receipt().actual_backend
        _validate_copy_binding_relationship(
            authority,
            copy_method,
            actual_backend=actual_backend,
        )
        copy_snapshot = _copy_method_snapshot(authority.runtime, copy_method)
        if (
            not callable(copy_method)
            or getattr(authority.runtime, "_loaded", None)
            is not authority.loaded_runtime
        ):
            _fail(
                "hip_fgmres_completion_export_copy_binding_invalid",
                "/authority/copy",
            )
        context._authority = authority
        context._authority_snapshot = _authority_snapshot(authority)
        context._copy_method = copy_method
        context._copy_method_snapshot = copy_snapshot
        context._actual_backend = actual_backend
        source_binding_hash = canonical_hash(
            {
                "global_context_id": authority.global_context_id,
                "global_receipt_hash": authority.global_receipt_hash,
                "roles": [
                    {
                        "role": source.role,
                        "lineage_hash": _source_lineage_hash(source),
                    }
                    for source in authority.source_capabilities
                ],
            }
        )
        solve_record_abi_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
        context._context_id = canonical_hash(
            {
                "profile": HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V1,
                "global_context_id": authority.global_context_id,
                "global_receipt_hash": authority.global_receipt_hash,
                "completion_receipt_hash": authority.completion_receipt_hash,
                "source_binding_hash": source_binding_hash,
                "solve_record_abi_hash": solve_record_abi_hash,
            }
        )
        context._bindings = HipFgmresCompletionExportBindingsV1(
            authority.global_context_id,
            authority.global_receipt_hash,
            authority.completion_receipt_hash,
            authority.continuation_schedule_hash,
            authority.recurrence_plan_hash,
            authority.recurrence_kernel_abi_hash,
            authority.combined_recurrence_abi_hash,
            authority.kernel_identity_hash,
            authority.kernel_source_sha256,
            solve_record_abi_hash,
            authority.direct_generation_binding_hash,
            authority.physical_projection_hash,
            source_binding_hash,
            authority.architecture,
            authority.device_ordinal,
            HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V1,
        )
        solution_bytes = 8 * authority.free_dof_count
        record_bytes = solve_record_byte_length_v2(authority.maximum_restart_count)
        context._dimensions = HipFgmresCompletionExportDimensionsV1(
            authority.free_dof_count,
            authority.maximum_restart_count,
            solution_bytes,
            solution_bytes,
            record_bytes,
            2 * solution_bytes + record_bytes,
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_completion_export_receipt_v1(
            receipt,
            expected_context=context,
        )
        return HipFgmresCompletionExportOpenResultV1(context, receipt)
    except BaseException as primary:
        try:
            active = reserved or (
                type(global_context) is HipFgmresGlobalRecurrenceExecutionContextV1
                and global_context._completion_export_child_token_is_active(
                    context._token
                )
            )
        except BaseException as reconcile:
            context._state = "cleanup_failed"
            code = "hip_fgmres_completion_export_open_reconcile_failed"
            context._reason = HipFgmresCompletionExportReasonV1(
                code,
                _detail(reconcile) or code,
            )
            raise HipFgmresCompletionExportV1Error(
                context._reason.code,
                "/open/reconcile",
                f"open failed: {_detail(primary)}; reconciliation failed: "
                f"{context._reason.detail}",
                cleanup_owner=context,
            ) from reconcile
        if active:
            try:
                context._release_child()
            except BaseException as rollback:
                if context._child_released:
                    raise
                context._state = "cleanup_failed"
                code = "hip_fgmres_completion_export_open_rollback_failed"
                context._reason = HipFgmresCompletionExportReasonV1(
                    code,
                    _detail(rollback) or code,
                )
                raise HipFgmresCompletionExportV1Error(
                    context._reason.code,
                    "/open/rollback",
                    f"open failed: {_detail(primary)}; rollback failed: "
                    f"{context._reason.detail}",
                    cleanup_owner=context,
                ) from rollback
        raise


def validate_hip_fgmres_completion_export_receipt_v1(
    receipt: HipFgmresCompletionExportReceiptV1,
    *,
    expected_context: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> HipFgmresCompletionExportReceiptV1:
    """Validate exact types, hash, schema, semantics, and optional provenance."""

    if type(receipt) is not HipFgmresCompletionExportReceiptV1:
        _fail("hip_fgmres_completion_export_receipt_type_invalid", "/")
    _validate_receipt_types(receipt)
    payload = _receipt_payload(receipt, include_hash=False)
    if _HASH_RE.fullmatch(
        receipt.receipt_hash
    ) is None or receipt.receipt_hash != canonical_hash(payload):
        _fail(
            "hip_fgmres_completion_export_receipt_hash_invalid",
            "/receipt_hash",
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_completion_export_receipt_schema_invalid",
            path,
            errors[0].message,
        )
    _validate_receipt_semantics(receipt)
    if expected_context is not None:
        if type(expected_context) is not HipFgmresCompletionExportExecutionContextV1:
            _fail(
                "hip_fgmres_completion_export_expected_context_invalid",
                "/expected_context",
            )
        with expected_context._lock:
            if receipt.context_id != expected_context._context_id:
                _fail(
                    "hip_fgmres_completion_export_context_mismatch",
                    "/context_id",
                )
            if receipt.status == "exported":
                result = expected_context._result or expected_context._publication
                if result is None or receipt is not result.receipt:
                    _fail(
                        "hip_fgmres_completion_export_provenance_invalid",
                        "/receipt",
                    )
            elif expected_context._closed:
                if receipt != expected_context._build_receipt("context_closed"):
                    _fail(
                        "hip_fgmres_completion_export_provenance_invalid",
                        "/receipt",
                    )
            elif receipt != expected_context._build_receipt(
                expected_context._public_status()
            ):
                _fail(
                    "hip_fgmres_completion_export_provenance_invalid",
                    "/receipt",
                )
    return receipt


def validate_hip_fgmres_completion_export_result_v1(
    result: HipFgmresCompletionExportResultV1,
    *,
    expected_context: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> HipFgmresCompletionExportResultV1:
    if type(result) is not HipFgmresCompletionExportResultV1:
        _fail("hip_fgmres_completion_export_result_type_invalid", "/")
    if (
        type(result.solution_x) is not bytes
        or type(result.true_residual) is not bytes
        or type(result.solve_record) is not bytes
        or type(result.payload_hash) is not str
    ):
        _fail("hip_fgmres_completion_export_result_type_invalid", "/payload")
    receipt = validate_hip_fgmres_completion_export_receipt_v1(result.receipt)
    payloads = (result.solution_x, result.true_residual, result.solve_record)
    if (
        receipt.status != "exported"
        or tuple(len(payload) for payload in payloads)
        != tuple(row.byte_count for row in receipt.buffers)
        or tuple(_sha256_bytes(payload) for payload in payloads)
        != tuple(row.payload_sha256 for row in receipt.buffers)
        or result.payload_hash != _bundle_hash(payloads)
        or result.payload_hash != receipt.payload_hash
    ):
        _fail(
            "hip_fgmres_completion_export_result_payload_invalid",
            "/payload",
        )
    for array in (
        result.solution_x_array,
        result.true_residual_array,
        result.solve_record_array,
    ):
        if array.flags.writeable or not array.flags.c_contiguous:
            _fail(
                "hip_fgmres_completion_export_result_array_invalid",
                "/payload/array",
            )
    if expected_context is not None:
        with expected_context._lock:
            if result is not (
                expected_context._result or expected_context._publication
            ):
                _fail(
                    "hip_fgmres_completion_export_result_provenance_invalid",
                    "/result",
                )
        validate_hip_fgmres_completion_export_receipt_v1(
            receipt,
            expected_context=expected_context,
        )
    return result


def _validate_authority_extents(
    authority: _CompletionExportChildAuthorityV1,
) -> None:
    sources = authority.source_capabilities
    expected_record_bytes = solve_record_byte_length_v2(authority.maximum_restart_count)
    expected = (
        ("solution_x", "f64", 8 * authority.free_dof_count),
        ("true_residual", "f64", 8 * authority.free_dof_count),
        ("solve_record", "u8", expected_record_bytes),
    )
    if (
        type(authority.free_dof_count) is not int
        or authority.free_dof_count <= 0
        or type(authority.restart_dimension) is not int
        or authority.restart_dimension <= 0
        or type(authority.max_iterations) is not int
        or authority.max_iterations <= 0
        or type(authority.maximum_restart_count) is not int
        or authority.maximum_restart_count <= 0
        or authority.maximum_restart_count
        != (authority.max_iterations + authority.restart_dimension - 1)
        // authority.restart_dimension
        or type(authority.stagnation_checkpoint_limit) is not int
        or not 2 <= authority.stagnation_checkpoint_limit <= 16
        or any(
            type(value) is not float or not math.isfinite(value)
            for value in (
                authority.absolute_tolerance,
                authority.relative_tolerance,
                authority.authoritative_tolerance,
                authority.stagnation_relative_tolerance,
                authority.divergence_factor,
            )
        )
        or type(sources) is not tuple
        or len(sources) != 3
    ):
        _fail(
            "hip_fgmres_completion_export_authority_invalid",
            "/authority/dimensions",
        )
    for source, (role, element_type, nbytes) in zip(sources, expected, strict=True):
        if (
            getattr(source, "role", None) != role
            or getattr(source, "element_type", None) != element_type
            or type(getattr(source, "nbytes", None)) is not int
            or source.nbytes != nbytes
            or type(getattr(source, "generation", None)) is not int
            or source.generation <= 0
            or type(getattr(source, "pointer_snapshot", None)) is not int
            or source.pointer_snapshot <= 0
            or getattr(source, "runtime_owner", None) is not authority.runtime
            or getattr(source, "device_ordinal", None) != authority.device_ordinal
            or getattr(source, "promotion_eligible", None) is not False
        ):
            _fail(
                "hip_fgmres_completion_export_source_extent_invalid",
                f"/authority/sources/{role}",
            )


def _authority_snapshot(
    authority: _CompletionExportChildAuthorityV1,
) -> tuple[Any, ...]:
    return (
        type(authority),
        authority.global_context_id,
        authority.global_receipt_hash,
        authority.completion_receipt_hash,
        authority.continuation_schedule_hash,
        id(authority.runtime),
        id(authority.loaded_runtime),
        id(authority.stream),
        (type(authority.stream_pointer), authority.stream_pointer),
        (type(authority.device_ordinal), authority.device_ordinal),
        (type(authority.architecture), authority.architecture),
        (type(authority.free_dof_count), authority.free_dof_count),
        (type(authority.restart_dimension), authority.restart_dimension),
        (type(authority.max_iterations), authority.max_iterations),
        (type(authority.maximum_restart_count), authority.maximum_restart_count),
        (
            type(authority.stagnation_checkpoint_limit),
            authority.stagnation_checkpoint_limit,
        ),
        (type(authority.absolute_tolerance), float.hex(authority.absolute_tolerance)),
        (type(authority.relative_tolerance), float.hex(authority.relative_tolerance)),
        (
            type(authority.authoritative_tolerance),
            float.hex(authority.authoritative_tolerance),
        ),
        (
            type(authority.stagnation_relative_tolerance),
            float.hex(authority.stagnation_relative_tolerance),
        ),
        (type(authority.divergence_factor), float.hex(authority.divergence_factor)),
        authority.recurrence_plan_hash,
        authority.recurrence_kernel_abi_hash,
        authority.combined_recurrence_abi_hash,
        authority.kernel_identity_hash,
        authority.kernel_source_sha256,
        authority.direct_generation_binding_hash,
        authority.physical_projection_hash,
        tuple(id(source) for source in authority.source_capabilities),
        authority.source_snapshot,
        _copy_method_snapshot(
            authority.runtime,
            _resolve_copy_binding(authority.runtime),
        ),
    )


def _completion_export_policy_snapshot(
    authority: _CompletionExportChildAuthorityV1,
) -> _CompletionExportPolicySnapshotV1:
    return _CompletionExportPolicySnapshotV1(
        restart_dimension=authority.restart_dimension,
        max_iterations=authority.max_iterations,
        maximum_restart_count=authority.maximum_restart_count,
        stagnation_checkpoint_limit=authority.stagnation_checkpoint_limit,
        absolute_tolerance=authority.absolute_tolerance,
        relative_tolerance=authority.relative_tolerance,
        authoritative_tolerance=authority.authoritative_tolerance,
        stagnation_relative_tolerance=authority.stagnation_relative_tolerance,
        divergence_factor=authority.divergence_factor,
    )


def _published_result_authority(
    result: HipFgmresCompletionExportResultV1,
    policy: _CompletionExportPolicySnapshotV1,
) -> _CompletionExportPublishedResultAuthorityV1:
    return _CompletionExportPublishedResultAuthorityV1(
        result=result,
        receipt=result.receipt,
        solution_x=result.solution_x,
        true_residual=result.true_residual,
        solve_record=result.solve_record,
        receipt_hash=result.receipt.receipt_hash,
        payload_hash=result.payload_hash,
        buffer_payload_hashes=tuple(
            row.payload_sha256 for row in result.receipt.buffers
        ),
        policy=policy,
    )


def _published_result_authority_snapshot(
    authority: _CompletionExportPublishedResultAuthorityV1,
) -> tuple[Any, ...]:
    policy = authority.policy
    return (
        type(authority),
        id(authority.result),
        id(authority.receipt),
        id(authority.solution_x),
        id(authority.true_residual),
        id(authority.solve_record),
        authority.receipt_hash,
        authority.payload_hash,
        authority.buffer_payload_hashes,
        type(policy),
        (type(policy.restart_dimension), policy.restart_dimension),
        (type(policy.max_iterations), policy.max_iterations),
        (type(policy.maximum_restart_count), policy.maximum_restart_count),
        (
            type(policy.stagnation_checkpoint_limit),
            policy.stagnation_checkpoint_limit,
        ),
        (type(policy.absolute_tolerance), float.hex(policy.absolute_tolerance)),
        (type(policy.relative_tolerance), float.hex(policy.relative_tolerance)),
        (
            type(policy.authoritative_tolerance),
            float.hex(policy.authoritative_tolerance),
        ),
        (
            type(policy.stagnation_relative_tolerance),
            float.hex(policy.stagnation_relative_tolerance),
        ),
        (type(policy.divergence_factor), float.hex(policy.divergence_factor)),
    )


def _resolve_copy_binding(
    runtime: Any,
    *,
    cleanup_owner: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> Any:
    factory = getattr(runtime, "completion_export_copy_binding", None)
    if not callable(factory) or getattr(factory, "__self__", None) is not runtime:
        _fail(
            "hip_fgmres_completion_export_copy_binding_invalid",
            "/authority/copy",
            cleanup_owner=cleanup_owner,
        )
    try:
        binding = factory()
    except Exception as exc:
        raise HipFgmresCompletionExportV1Error(
            "hip_fgmres_completion_export_copy_binding_invalid",
            "/authority/copy",
            _detail(exc),
            cleanup_owner=cleanup_owner,
        ) from exc
    if not callable(binding):
        _fail(
            "hip_fgmres_completion_export_copy_binding_invalid",
            "/authority/copy",
            cleanup_owner=cleanup_owner,
        )
    return binding


def _validate_copy_binding_relationship(
    authority: _CompletionExportChildAuthorityV1,
    method: Any,
    *,
    actual_backend: Literal["hip", "test_double"],
    cleanup_owner: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> None:
    if actual_backend != "hip":
        return
    runtime = authority.runtime
    if (
        type(method) is not _BoundBlockingD2HCopy
        or method is not getattr(runtime, "_blocking_d2h_copy", None)
        or getattr(method, "_memcpy", None) is not getattr(runtime, "_memcpy", None)
        or getattr(method, "_loaded", None) is not authority.loaded_runtime
        or getattr(runtime, "_loaded", None) is not authority.loaded_runtime
    ):
        _fail(
            "hip_fgmres_completion_export_native_copy_binding_invalid",
            "/authority/copy/native",
            cleanup_owner=cleanup_owner,
        )


def _copy_method_snapshot(runtime: Any, method: Any) -> tuple[Any, ...]:
    factory = getattr(runtime, "completion_export_copy_binding", None)
    return (
        id(runtime),
        id(getattr(type(runtime), "completion_export_copy_binding", None)),
        id(getattr(factory, "__self__", None)),
        id(getattr(factory, "__func__", None)),
        type(method),
        id(method),
        id(getattr(type(method), "__call__", None)),
        id(getattr(method, "__self__", None)),
        id(getattr(method, "__func__", None)),
        id(getattr(method, "_memcpy", None)),
        id(getattr(method, "_loaded", None)),
        _copy_operation_snapshot(method),
        id(getattr(runtime, "_blocking_d2h_copy", None)),
        id(getattr(runtime, "_memcpy", None)),
        id(getattr(runtime, "_loaded", None)),
    )


def _copy_operation_snapshot(method: Any) -> tuple[Any, ...]:
    operation = getattr(method, "_memcpy", None)
    argtypes = getattr(operation, "argtypes", None)
    return (
        type(operation),
        id(operation),
        None
        if argtypes is None
        else tuple((type(argument), id(argument)) for argument in argtypes),
        type(getattr(operation, "restype", None)),
        id(getattr(operation, "restype", None)),
        type(getattr(operation, "errcheck", None)),
        id(getattr(operation, "errcheck", None)),
    )


def _source_lineage_hash(source: Any) -> str:
    return canonical_hash(
        {
            "allocation_id": int(source.allocation_id),
            "role": source.role,
            "nbytes": int(source.nbytes),
            "element_type": source.element_type,
            "generation": int(source.generation),
            "runtime_domain_id": source.runtime_domain_id,
            "device_ordinal": int(source.device_ordinal),
            "evidence_scope": source.evidence_scope,
            "promotion_eligible": False,
        }
    )


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _bundle_hash(payloads: tuple[bytes, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(_PAYLOAD_DOMAIN)
    for role, payload in zip(_SOURCE_ROLES, payloads, strict=True):
        encoded = role.encode("ascii")
        digest.update(len(encoded).to_bytes(2, "little"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _validate_receipt_types(receipt: HipFgmresCompletionExportReceiptV1) -> None:
    if (
        type(receipt.status) is not str
        or type(receipt.context_id) is not str
        or type(receipt.evidence_scope) is not str
        or type(receipt.actual_backend) is not str
        or receipt.promotion_eligible is not False
        or (
            receipt.reason is not None
            and type(receipt.reason) is not HipFgmresCompletionExportReasonV1
        )
        or type(receipt.bindings) is not HipFgmresCompletionExportBindingsV1
        or type(receipt.dimensions) is not HipFgmresCompletionExportDimensionsV1
        or type(receipt.buffers) is not tuple
        or any(
            type(row) is not HipFgmresCompletionExportBufferV1
            for row in receipt.buffers
        )
        or type(receipt.telemetry) is not HipFgmresCompletionExportTelemetryV1
        or type(receipt.claims) is not HipFgmresCompletionExportClaimsV1
        or type(receipt.payload_hash) is not str
        or type(receipt.receipt_hash) is not str
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_type_invalid",
            "/",
        )
    if receipt.reason is not None and (
        type(receipt.reason.code) is not str or type(receipt.reason.detail) is not str
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_type_invalid",
            "/reason",
        )
    string_bindings = (
        "global_context_id",
        "global_receipt_hash",
        "completion_receipt_hash",
        "continuation_schedule_hash",
        "recurrence_plan_hash",
        "recurrence_kernel_abi_hash",
        "combined_recurrence_abi_hash",
        "kernel_identity_hash",
        "kernel_source_sha256",
        "solve_record_abi_hash",
        "direct_generation_binding_hash",
        "physical_projection_hash",
        "source_binding_hash",
        "architecture",
        "copy_api",
    )
    if (
        any(
            type(getattr(receipt.bindings, name)) is not str for name in string_bindings
        )
        or type(receipt.bindings.device_ordinal) is not int
        or receipt.bindings.completion_capability_identity_serialized is not False
        or receipt.bindings.device_pointer_values_serialized is not False
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_type_invalid",
            "/bindings",
        )
    for value in (
        getattr(receipt.dimensions, name)
        for name in receipt.dimensions.__dataclass_fields__
    ):
        if type(value) is not int:
            _fail(
                "hip_fgmres_completion_export_receipt_type_invalid",
                "/dimensions",
            )
    if len(receipt.buffers) != 3:
        _fail(
            "hip_fgmres_completion_export_receipt_type_invalid",
            "/buffers",
        )
    for index, row in enumerate(receipt.buffers):
        if (
            type(row.role) is not str
            or type(row.dtype) is not str
            or type(row.shape) is not tuple
            or any(type(extent) is not int for extent in row.shape)
            or type(row.byte_count) is not int
            or type(row.allocation_generation) is not int
            or type(row.source_lineage_hash) is not str
            or type(row.payload_sha256) is not str
        ):
            _fail(
                "hip_fgmres_completion_export_receipt_type_invalid",
                f"/buffers/{index}",
            )
    for value in (
        getattr(receipt.telemetry, name)
        for name in receipt.telemetry.__dataclass_fields__
    ):
        if type(value) is not int:
            _fail(
                "hip_fgmres_completion_export_receipt_type_invalid",
                "/telemetry",
            )
    for value in (
        getattr(receipt.claims, name) for name in receipt.claims.__dataclass_fields__
    ):
        if type(value) is not bool:
            _fail(
                "hip_fgmres_completion_export_receipt_type_invalid",
                "/claims",
            )


def _validate_receipt_semantics(receipt: HipFgmresCompletionExportReceiptV1) -> None:
    dimensions = receipt.dimensions
    telemetry = receipt.telemetry
    claims = receipt.claims
    buffers = receipt.buffers
    exported = receipt.status == "exported"
    expected_total = (
        dimensions.solution_byte_count
        + dimensions.true_residual_byte_count
        + dimensions.solve_record_byte_count
    )
    telemetry_values = tuple(
        getattr(telemetry, name) for name in telemetry.__dataclass_fields__
    )
    attempted_count = telemetry.d2h_operation_attempt_count
    success_count = telemetry.d2h_operation_success_count
    attempted_bytes = (
        sum(row.byte_count for row in buffers[:attempted_count])
        if 0 <= attempted_count <= 3
        else -1
    )
    succeeded_bytes = (
        sum(row.byte_count for row in buffers[:success_count])
        if 0 <= success_count <= 3
        else -1
    )
    bound = receipt.status not in {"context_closed", "cleanup_failed"}
    consumed = telemetry.completion_capability_consume_count == 1
    expected_source_binding_hash = canonical_hash(
        {
            "global_context_id": receipt.bindings.global_context_id,
            "global_receipt_hash": receipt.bindings.global_receipt_hash,
            "roles": [
                {
                    "role": row.role,
                    "lineage_hash": row.source_lineage_hash,
                }
                for row in buffers
            ],
        }
    )
    expected_context_id = canonical_hash(
        {
            "profile": HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V1,
            "global_context_id": receipt.bindings.global_context_id,
            "global_receipt_hash": receipt.bindings.global_receipt_hash,
            "completion_receipt_hash": receipt.bindings.completion_receipt_hash,
            "source_binding_hash": expected_source_binding_hash,
            "solve_record_abi_hash": receipt.bindings.solve_record_abi_hash,
        }
    )
    if (
        receipt.evidence_scope != HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V1
        or receipt.actual_backend not in {"hip", "test_double"}
        or receipt.promotion_eligible is not False
        or _HASH_RE.fullmatch(receipt.context_id) is None
        or _HASH_RE.fullmatch(receipt.payload_hash) is None
        or dimensions.free_dof_count <= 0
        or dimensions.maximum_restart_count <= 0
        or dimensions.solution_byte_count != 8 * dimensions.free_dof_count
        or dimensions.true_residual_byte_count != 8 * dimensions.free_dof_count
        or dimensions.solve_record_byte_count
        != solve_record_byte_length_v2(dimensions.maximum_restart_count)
        or dimensions.total_export_byte_count != expected_total
        or dimensions.exported_buffer_count != 3
        or receipt.bindings.solve_record_abi_hash
        != canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
        or receipt.bindings.global_receipt_hash
        != receipt.bindings.completion_receipt_hash
        or receipt.bindings.source_binding_hash != expected_source_binding_hash
        or receipt.context_id != expected_context_id
        or tuple(row.role for row in buffers) != _SOURCE_ROLES
        or tuple(row.dtype for row in buffers) != ("<f8", "<f8", "|u1")
        or tuple(row.shape for row in buffers)
        != (
            (dimensions.free_dof_count,),
            (dimensions.free_dof_count,),
            (dimensions.solve_record_byte_count,),
        )
        or tuple(row.byte_count for row in buffers)
        != (
            dimensions.solution_byte_count,
            dimensions.true_residual_byte_count,
            dimensions.solve_record_byte_count,
        )
        or any(row.allocation_generation <= 0 for row in buffers)
        or any(_HASH_RE.fullmatch(row.source_lineage_hash) is None for row in buffers)
        or any(_HASH_RE.fullmatch(row.payload_sha256) is None for row in buffers)
        or telemetry.completion_capability_reservation_count != 1
        or telemetry.device_allocation_count != 0
        or telemetry.allocation_borrow_count != 0
        or telemetry.h2d_operation_count != 0
        or telemetry.kernel_launch_count != 0
        or telemetry.explicit_stream_sync_count != 0
        or telemetry.fallback_count != 0
        or telemetry.numerical_content_branch_count != 0
        or any(value < 0 for value in telemetry_values)
        or telemetry.completion_capability_consume_count not in {0, 1}
        or telemetry.host_staging_allocation_count not in {0, 3}
        or (
            receipt.status in {"poisoned", "exported"}
            and telemetry.host_staging_allocation_count != 3
        )
        or success_count > attempted_count
        or attempted_count - success_count > 1
        or (attempted_count > 0 and not consumed)
        or telemetry.blocking_copy_completion_count != success_count
        or telemetry.d2h_bytes_attempted != attempted_bytes
        or telemetry.d2h_bytes_succeeded != succeeded_bytes
        or claims.global_fenced_completion_bound is not bound
        or claims.completion_capability_consumed is not consumed
        or claims.exact_three_source_lineages_bound is not bound
        or claims.no_device_allocation_or_borrow is not bound
        or claims.no_h2d_or_kernel_launch is not bound
        or claims.no_explicit_stream_synchronization is not bound
        or claims.solve_record_semantics_interpreted
        or claims.numerical_content_host_branch_performed
        or claims.actual_terminal_outcome_host_observed
        or claims.authoritative_terminal_status_proven
        or claims.numerical_parity_verified
        or claims.solution_ready
        or claims.result_ir_ready
        or claims.iteration_host_copy_zero_proven
        or claims.performance_or_speedup_proven
        or claims.commercial_ready
        or claims.promotion_eligible
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_semantic_invalid",
            "/",
        )
    if receipt.status == "context_ready" and (
        receipt.reason is not None
        or consumed
        or telemetry.host_staging_allocation_count != 0
        or attempted_count != 0
        or success_count != 0
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_semantic_invalid",
            "/status",
        )
    if receipt.status in {"poisoned", "cleanup_failed"} and receipt.reason is None:
        _fail(
            "hip_fgmres_completion_export_receipt_semantic_invalid",
            "/reason",
        )
    if receipt.status == "poisoned" and not consumed:
        _fail(
            "hip_fgmres_completion_export_receipt_semantic_invalid",
            "/status",
        )
    if exported:
        if (
            receipt.reason is not None
            or receipt.payload_hash == _ZERO_HASH
            or telemetry.completion_capability_consume_count != 1
            or telemetry.host_staging_allocation_count != 3
            or telemetry.d2h_operation_attempt_count != 3
            or telemetry.d2h_operation_success_count != 3
            or telemetry.d2h_bytes_attempted != expected_total
            or telemetry.d2h_bytes_succeeded != expected_total
            or telemetry.blocking_copy_completion_count != 3
            or any(row.payload_sha256 == _ZERO_HASH for row in buffers)
            or not claims.global_fenced_completion_bound
            or not claims.completion_capability_consumed
            or not claims.exact_three_source_lineages_bound
            or not claims.raw_completion_buffers_host_materialized
            or not claims.blocking_completion_only_d2h
            or not claims.immutable_detached_host_payload
            or not claims.no_device_allocation_or_borrow
            or not claims.no_h2d_or_kernel_launch
            or not claims.no_explicit_stream_synchronization
        ):
            _fail(
                "hip_fgmres_completion_export_receipt_semantic_invalid",
                "/status",
            )
    elif (
        receipt.payload_hash != _ZERO_HASH
        or any(row.payload_sha256 != _ZERO_HASH for row in buffers)
        or claims.raw_completion_buffers_host_materialized
        or claims.blocking_completion_only_d2h
        or claims.immutable_detached_host_payload
    ):
        _fail(
            "hip_fgmres_completion_export_receipt_semantic_invalid",
            "/payload_hash",
        )


def _receipt_payload(
    receipt: HipFgmresCompletionExportReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V1,
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


def _allocate_host_staging(sources: tuple[Any, ...]) -> tuple[np.ndarray, ...]:
    return tuple(np.empty(int(source.nbytes), dtype=np.uint8) for source in sources)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: object) -> str:
    text = " ".join(str(value).split())
    return text[:512]


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresCompletionExportExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresCompletionExportV1Error(
        code,
        path,
        message,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_COMPLETION_EXPORT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V1",
    "HIP_FGMRES_COMPLETION_EXPORT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_COMPLETION_EXPORT_SCHEMA_VERSION_V1",
    "HipFgmresCompletionExportBindingsV1",
    "HipFgmresCompletionExportBufferV1",
    "HipFgmresCompletionExportClaimsV1",
    "HipFgmresCompletionExportDimensionsV1",
    "HipFgmresCompletionExportExecutionContextV1",
    "HipFgmresCompletionExportOpenResultV1",
    "HipFgmresCompletionExportReasonV1",
    "HipFgmresCompletionExportReceiptV1",
    "HipFgmresCompletionExportResultV1",
    "HipFgmresCompletionExportTelemetryV1",
    "HipFgmresCompletionExportV1Error",
    "open_hip_fgmres_completion_export_context_v1",
    "validate_hip_fgmres_completion_export_receipt_v1",
    "validate_hip_fgmres_completion_export_result_v1",
]
