"""Process-local RTC launch/fence ordinal audit for one FGMRES-v2 lineage.

This additive companion contract opens before the canonical predecessor's
first enqueue and seals immediately after the global recurrence completion
fence, before a completion-export child is opened.  It replays the exact fixed
descriptor sequence against the kernel-owned rolling ordinal ledger.

The contract observes only package-owned calls routed through the retained
``HipRtcFgmresV2Kernel``.  It is not a process-wide ROCm trace, a device
execution attestation, or numerical parity evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_canonical_predecessor_v1 import (
    HipFgmresCanonicalPredecessorExecutionContextV1,
    _OWNED_ROLES as _CANONICAL_OWNED_ROLES,
)
from .fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    HipFgmresGlobalRecurrenceExecutionContextV1,
    validate_hip_fgmres_global_recurrence_completion_capability_v1,
)
from .fgmres_rtc_launch_fence_ledger_v1 import (
    HipFgmresRtcLaunchFenceLedgerSnapshotV1,
    HipFgmresRtcOperationCounterV1,
    _HipFgmresRtcLaunchFenceLedgerCaptureV1,
    _capture_rtc_launch_fence_ledger_v1,
    _fence_descriptor_hash_v1,
    _launch_descriptor_hash_v1,
    _memset_descriptor_hash_v1,
    _replay_successful_operation_v1,
)
from .fgmres_sealed_checkpoint_transaction_v1 import (
    HipFgmresSealedCheckpointTransactionExecutionContextV1,
)


HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-recurrence-launch-fence-audit.v1"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_CAPABILITY_PROFILE_V1 = (
    "phase0_exact_kernel_rtc_launch_fence_rolling_ordinal_audit"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_EVIDENCE_SCOPE_V1 = (
    "process_local_exact_kernel_fixed_recurrence_descriptor_order_non_promoting"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_START_BOUNDARY_V1 = (
    "canonical_context_ready_before_predecessor_enqueue"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_END_BOUNDARY_V1 = (
    "global_recurrence_fenced_before_completion_export_open"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_LEDGER_ALGORITHM_V1 = (
    "sha256_fixed_binary_predecessor_chain_v1"
)
HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_DESCRIPTOR_ALGORITHM_V1 = (
    "canonical_common_schedule_projection_sha256_v1"
)

_SCHEMA_RESOURCE = "hip_fgmres_recurrence_launch_fence_audit_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_JSON_SAFE_INTEGER = (1 << 53) - 1


class HipFgmresRecurrenceLaunchFenceAuditV1Error(RuntimeError):
    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        cleanup_owner: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1
        | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditBindingsV1:
    canonical_context_id: str
    canonical_open_receipt_hash: str
    canonical_fenced_receipt_hash: str
    sealed_checkpoint_context_id: str
    sealed_checkpoint_receipt_hash: str
    global_context_id: str
    global_receipt_hash: str
    completion_receipt_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_abi_hash: str
    combined_recurrence_abi_hash: str
    kernel_identity_hash: str
    kernel_source_sha256: str
    canonical_schedule_hash: str
    checkpoint_schedule_hash: str
    global_full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str
    direct_generation_binding_hash: str
    physical_projection_hash: str
    program_descriptor_hash: str
    architecture: str
    device_ordinal: int
    ledger_algorithm: Literal["sha256_fixed_binary_predecessor_chain_v1"]
    descriptor_algorithm: Literal["canonical_common_schedule_projection_sha256_v1"]
    runtime_identity_serialized: Literal[False] = False
    stream_identity_serialized: Literal[False] = False
    checkpoint_token_identity_serialized: Literal[False] = False
    kernel_object_identity_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditWindowV1:
    start_boundary: Literal["canonical_context_ready_before_predecessor_enqueue"]
    end_boundary: Literal["global_recurrence_fenced_before_completion_export_open"]
    start_operation_ordinal: int
    end_operation_ordinal: int
    start_event_sequence: int
    end_event_sequence: int
    start_rolling_hash: str
    end_rolling_hash: str
    first_recurrence_launch_ordinal: int
    canonical_fence_ordinal: int
    sealed_checkpoint_fence_ordinal: int
    terminal_fence_ordinal: int
    start_in_flight_count: Literal[0]
    end_in_flight_count: Literal[0]
    terminal_event_kind: Literal["fence"]
    terminal_event_disposition: Literal["success"]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_stage_count: int
    prelaunch_memset_count: Literal[8]
    canonical_launch_count: int
    sealed_checkpoint_launch_count: Literal[4]
    continuation_launch_count: int
    full_program_launch_count: int
    fence_count: Literal[3]
    total_native_call_count: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditTelemetryV1:
    memset: HipFgmresRtcOperationCounterV1
    launch: HipFgmresRtcOperationCounterV1
    fence: HipFgmresRtcOperationCounterV1
    operation_ordinal_delta: int
    event_sequence_delta: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "memset": self.memset.to_dict(),
            "launch": self.launch.to_dict(),
            "fence": self.fence.to_dict(),
            "operation_ordinal_delta": self.operation_ordinal_delta,
            "event_sequence_delta": self.event_sequence_delta,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditClaimsV1:
    exact_process_local_kernel_ledger_bound: Literal[True]
    canonical_to_terminal_fence_lineage_bound: Literal[True]
    fixed_recurrence_descriptor_order_replayed: Literal[True]
    native_attempt_recorded_before_each_owned_call: Literal[True]
    canonical_sealed_terminal_fences_ordered: Literal[True]
    exact_successful_call_counts_bound: Literal[True]
    constant_space_rolling_ledger_bound: Literal[True]
    raw_or_fresh_native_binding_calls_observed: Literal[False] = False
    process_wide_rocm_launch_completeness_proven: Literal[False] = False
    all_device_operations_observed: Literal[False] = False
    hostile_same_process_mutation_resistant: Literal[False] = False
    device_kernel_execution_success_proven: Literal[False] = False
    device_content_or_numerical_outcome_proven: Literal[False] = False
    standalone_receipt_provenance_authenticity: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    external_architecture_verified: Literal[False] = False
    signed_hardware_truth_verified: Literal[False] = False
    result_ir_ready: Literal[False] = False
    end_to_end_on_complexity_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditReceiptV1:
    status: Literal["ordinal_chain_sealed"]
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    bindings: HipFgmresRecurrenceLaunchFenceAuditBindingsV1
    window: HipFgmresRecurrenceLaunchFenceAuditWindowV1
    dimensions: HipFgmresRecurrenceLaunchFenceAuditDimensionsV1
    telemetry: HipFgmresRecurrenceLaunchFenceAuditTelemetryV1
    claims: HipFgmresRecurrenceLaunchFenceAuditClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1

    @property
    def capability_profile(self) -> str:
        return HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_CAPABILITY_PROFILE_V1

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditResultV1:
    receipt: HipFgmresRecurrenceLaunchFenceAuditReceiptV1

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrenceLaunchFenceAuditOpenResultV1:
    context: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1

    @property
    def ready(self) -> bool:
        return self.context.ready


class HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1:
    def __init__(
        self,
        canonical: HipFgmresCanonicalPredecessorExecutionContextV1,
        capture: _HipFgmresRtcLaunchFenceLedgerCaptureV1,
        checkpoint_owner_token: object,
        canonical_open_receipt_hash: str,
    ) -> None:
        self._lock = threading.RLock()
        self._canonical = canonical
        self._kernel = capture.kernel
        self._checkpoint_owner_token = checkpoint_owner_token
        self._start_capture = capture
        self._canonical_open_receipt_hash = canonical_open_receipt_hash
        self._state: Literal[
            "context_ready", "seal_in_progress", "sealed", "poisoned", "closed"
        ] = "context_ready"
        self._active_operation = False
        self._global_context: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._completion_capability: (
            HipFgmresGlobalRecurrenceCompletionCapabilityV1 | None
        ) = None
        self._result: HipFgmresRecurrenceLaunchFenceAuditResultV1 | None = None

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._state == "context_ready" and not self._active_operation

    @property
    def result(self) -> HipFgmresRecurrenceLaunchFenceAuditResultV1 | None:
        with self._lock:
            return self._result if self._state in {"sealed", "closed"} else None

    def seal_terminal_fence(
        self,
        global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
        completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> HipFgmresRecurrenceLaunchFenceAuditResultV1:
        with self._lock:
            if self._result is not None and self._state == "sealed":
                if (
                    global_context is not self._global_context
                    or completion_capability is not self._completion_capability
                ):
                    _fail(
                        "hip_fgmres_recurrence_launch_fence_audit_cached_input_changed",
                        "/seal/input",
                        cleanup_owner=self,
                    )
                return self._result
            if self._active_operation:
                _fail(
                    "hip_fgmres_recurrence_launch_fence_audit_reentrant",
                    "/seal/operation",
                    cleanup_owner=self,
                )
            if self._state != "context_ready":
                _fail(
                    "hip_fgmres_recurrence_launch_fence_audit_state_invalid",
                    "/seal/state",
                    cleanup_owner=self,
                )
            self._active_operation = True
            self._state = "seal_in_progress"
            try:
                with global_context._lock:
                    lineage = self._validate_fenced_lineage(
                        global_context,
                        completion_capability,
                    )
                    if (
                        global_context._completion_export_child_terminal
                        or global_context._active_completion_export_child_locked()
                        is not None
                    ):
                        _fail(
                            "hip_fgmres_recurrence_launch_fence_audit_export_started",
                            "/window/end",
                            cleanup_owner=self,
                        )
                    end_capture = _capture_rtc_launch_fence_ledger_v1(
                        self._kernel,
                        self._checkpoint_owner_token,
                    )
                self._require_same_capture(end_capture, "/window/end")
                expected = self._expected_program(lineage)
                self._validate_ledger_window(end_capture.snapshot, expected)
                receipt = self._build_receipt(
                    lineage=lineage,
                    end_capture=end_capture,
                    expected=expected,
                )
                result = HipFgmresRecurrenceLaunchFenceAuditResultV1(receipt)
                self._global_context = global_context
                self._completion_capability = completion_capability
                self._result = result
                self._state = "sealed"
                validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
                    result,
                    expected_context=self,
                )
                return result
            except BaseException as exc:
                self._state = "poisoned"
                if not isinstance(exc, Exception):
                    raise
                if (
                    isinstance(exc, HipFgmresRecurrenceLaunchFenceAuditV1Error)
                    and exc.cleanup_owner is self
                ):
                    raise
                raise HipFgmresRecurrenceLaunchFenceAuditV1Error(
                    "hip_fgmres_recurrence_launch_fence_audit_seal_failed",
                    "/seal",
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
                    "hip_fgmres_recurrence_launch_fence_audit_operation_active",
                    "/close",
                    cleanup_owner=self,
                )
            self._state = "closed"
            _release_ledger_audit_owner(self._start_capture.state, self)

    def _validate_fenced_lineage(
        self,
        global_context: HipFgmresGlobalRecurrenceExecutionContextV1,
        completion_capability: HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    ) -> tuple[Any, ...]:
        if type(global_context) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_global_invalid",
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
                "hip_fgmres_recurrence_launch_fence_audit_global_not_fenced",
                "/global_context/status",
                cleanup_owner=self,
            )
        sealed = global_context._require_sealed()
        if type(sealed) is not HipFgmresSealedCheckpointTransactionExecutionContextV1:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_sealed_invalid",
                "/sealed_context",
                cleanup_owner=self,
            )
        canonical = sealed._require_canonical()
        if canonical is not self._canonical:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_canonical_changed",
                "/canonical_context",
                cleanup_owner=self,
            )
        canonical_receipt = canonical.receipt()
        sealed_receipt = sealed.receipt()
        global_binding = global_context._require_binding()
        sealed_binding = sealed._require_binding()
        live = canonical._require_live()
        kernel = canonical._kernel()
        if (
            kernel is not self._kernel
            or live._checkpoint_token is not self._checkpoint_owner_token
            or global_binding.kernel is not kernel
            or sealed_binding.kernel is not kernel
            or global_binding.checkpoint_owner_token is not self._checkpoint_owner_token
            or sealed_binding.checkpoint_owner_token is not self._checkpoint_owner_token
            or global_binding.loaded_runtime is not live._loaded_runtime
            or sealed_binding.loaded_runtime is not live._loaded_runtime
            or kernel._checkpoint_runtime_owner(self._checkpoint_owner_token)
            is not live._loaded_runtime
            or global_binding.runtime is not live._runtime
            or global_binding.stream is not live._stream
            or global_binding.stream_pointer != live._stream_pointer_snapshot
            or sealed_binding.stream_pointer != live._stream_pointer_snapshot
            or global_binding.device_ordinal != live._device_ordinal
            or global_binding.architecture != live._architecture
            or global_receipt.bindings.canonical_predecessor_context_id
            != canonical_receipt.context_id
            or global_receipt.bindings.sealed_checkpoint_context_id
            != sealed_receipt.context_id
            or global_receipt.bindings.sealed_checkpoint_receipt_hash
            != sealed_receipt.receipt_hash
            or completion_capability.receipt_hash != global_receipt.receipt_hash
        ):
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_lineage_changed",
                "/lineage",
                cleanup_owner=self,
            )
        return (
            canonical_receipt,
            sealed_receipt,
            global_receipt,
            sealed_binding,
            global_binding,
        )

    def _require_same_capture(
        self,
        capture: _HipFgmresRtcLaunchFenceLedgerCaptureV1,
        path: str,
    ) -> None:
        if (
            capture.kernel is not self._kernel
            or capture.state is not self._start_capture.state
            or capture.binding_snapshot != self._start_capture.binding_snapshot
        ):
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_ledger_changed",
                path,
                cleanup_owner=self,
            )

    def _expected_program(self, lineage: tuple[Any, ...]) -> dict[str, Any]:
        (
            _canonical_receipt,
            _sealed_receipt,
            global_receipt,
            sealed_binding,
            global_binding,
        ) = lineage
        canonical_rows = self._canonical._schedule
        sealed_rows = sealed_binding.launches
        continuation_rows = global_binding.partition.continuation.launches
        full_rows = global_binding.partition.full.launches
        canonical_descriptors = tuple(
            _launch_descriptor_hash_v1(row) for row in canonical_rows
        )
        sealed_descriptors = tuple(
            _launch_descriptor_hash_v1(row) for row in sealed_rows
        )
        continuation_descriptors = tuple(
            _launch_descriptor_hash_v1(row) for row in continuation_rows
        )
        full_descriptors = tuple(_launch_descriptor_hash_v1(row) for row in full_rows)
        if (
            canonical_descriptors + sealed_descriptors + continuation_descriptors
            != full_descriptors
            or len(sealed_descriptors) != 4
            or len(full_descriptors)
            != global_receipt.dimensions.full_program_launch_count
        ):
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_program_changed",
                "/program/descriptors",
                cleanup_owner=self,
            )
        memset_descriptors = tuple(
            _memset_descriptor_hash_v1(
                role,
                self._canonical._owned_byte_lengths[role],
            )
            for role in _CANONICAL_OWNED_ROLES
        )
        if len(memset_descriptors) != 8:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_program_changed",
                "/program/memsets",
                cleanup_owner=self,
            )
        fence = _fence_descriptor_hash_v1()
        operations: tuple[tuple[str, str], ...] = (
            tuple(("memset", value) for value in memset_descriptors)
            + tuple(("launch", value) for value in canonical_descriptors)
            + (("fence", fence),)
            + tuple(("launch", value) for value in sealed_descriptors)
            + (("fence", fence),)
            + tuple(("launch", value) for value in continuation_descriptors)
            + (("fence", fence),)
        )
        return {
            "operations": operations,
            "program_descriptor_hash": canonical_hash(
                [
                    {"kind": kind, "descriptor_hash": descriptor_hash}
                    for kind, descriptor_hash in operations
                ]
            ),
            "canonical_launch_count": len(canonical_descriptors),
            "continuation_launch_count": len(continuation_descriptors),
            "full_program_launch_count": len(full_descriptors),
        }

    def _validate_ledger_window(
        self,
        end: HipFgmresRtcLaunchFenceLedgerSnapshotV1,
        expected: dict[str, Any],
    ) -> None:
        start = self._start_capture.snapshot
        if start.total_in_flight_count != 0 or end.total_in_flight_count != 0:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_inflight",
                "/window",
                cleanup_owner=self,
            )
        head = start.rolling_hash
        ordinal = start.operation_ordinal
        for kind, descriptor_hash in expected["operations"]:
            head, ordinal = _replay_successful_operation_v1(
                head,
                ordinal,
                kind,
                descriptor_hash,
            )
        expected_call_count = len(expected["operations"])
        if (
            end.rolling_hash != head
            or end.operation_ordinal != ordinal
            or end.operation_ordinal - start.operation_ordinal != expected_call_count
            or end.event_sequence - start.event_sequence != 2 * expected_call_count
            or end.last_completed_operation_ordinal != end.operation_ordinal
            or end.last_completed_kind != "fence"
            or end.last_completed_disposition != "success"
        ):
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_chain_mismatch",
                "/window/rolling_chain",
                cleanup_owner=self,
            )
        deltas = {
            kind: _counter_delta(
                getattr(start, kind),
                getattr(end, kind),
                path=f"/window/{kind}",
                cleanup_owner=self,
            )
            for kind in ("memset", "launch", "fence")
        }
        expected_counts = {
            "memset": 8,
            "launch": expected["full_program_launch_count"],
            "fence": 3,
        }
        for kind, count in expected_counts.items():
            row = deltas[kind]
            if row != HipFgmresRtcOperationCounterV1(count, count, 0, 0, 0):
                _fail(
                    "hip_fgmres_recurrence_launch_fence_audit_disposition_mismatch",
                    f"/window/{kind}",
                    cleanup_owner=self,
                )

    def _build_receipt(
        self,
        *,
        lineage: tuple[Any, ...],
        end_capture: _HipFgmresRtcLaunchFenceLedgerCaptureV1,
        expected: dict[str, Any],
    ) -> HipFgmresRecurrenceLaunchFenceAuditReceiptV1:
        (
            canonical_receipt,
            sealed_receipt,
            global_receipt,
            _sealed_binding,
            _global_binding,
        ) = lineage
        global_bindings = global_receipt.bindings
        sealed_bindings = sealed_receipt.bindings
        start = self._start_capture.snapshot
        end = end_capture.snapshot
        canonical_count = expected["canonical_launch_count"]
        continuation_count = expected["continuation_launch_count"]
        full_count = expected["full_program_launch_count"]
        first_launch = start.operation_ordinal + 9
        canonical_fence = first_launch + canonical_count
        sealed_fence = canonical_fence + 5
        terminal_fence = sealed_fence + continuation_count + 1
        telemetry = HipFgmresRecurrenceLaunchFenceAuditTelemetryV1(
            memset=_counter_delta(
                start.memset,
                end.memset,
                path="/telemetry/memset",
                cleanup_owner=self,
            ),
            launch=_counter_delta(
                start.launch,
                end.launch,
                path="/telemetry/launch",
                cleanup_owner=self,
            ),
            fence=_counter_delta(
                start.fence,
                end.fence,
                path="/telemetry/fence",
                cleanup_owner=self,
            ),
            operation_ordinal_delta=end.operation_ordinal - start.operation_ordinal,
            event_sequence_delta=end.event_sequence - start.event_sequence,
        )
        draft = HipFgmresRecurrenceLaunchFenceAuditReceiptV1(
            status="ordinal_chain_sealed",
            context_id=canonical_hash(
                {
                    "profile": (
                        HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_CAPABILITY_PROFILE_V1
                    ),
                    "canonical_context_id": canonical_receipt.context_id,
                    "canonical_open_receipt_hash": self._canonical_open_receipt_hash,
                    "global_context_id": global_receipt.context_id,
                    "global_receipt_hash": global_receipt.receipt_hash,
                    "start_operation_ordinal": start.operation_ordinal,
                    "start_rolling_hash": start.rolling_hash,
                }
            ),
            evidence_scope=(HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_EVIDENCE_SCOPE_V1),
            actual_backend=global_receipt.actual_backend,
            promotion_eligible=False,
            bindings=HipFgmresRecurrenceLaunchFenceAuditBindingsV1(
                canonical_context_id=canonical_receipt.context_id,
                canonical_open_receipt_hash=self._canonical_open_receipt_hash,
                canonical_fenced_receipt_hash=canonical_receipt.receipt_hash,
                sealed_checkpoint_context_id=sealed_receipt.context_id,
                sealed_checkpoint_receipt_hash=sealed_receipt.receipt_hash,
                global_context_id=global_receipt.context_id,
                global_receipt_hash=global_receipt.receipt_hash,
                completion_receipt_hash=global_receipt.receipt_hash,
                recurrence_plan_hash=global_bindings.recurrence_plan_hash,
                recurrence_kernel_abi_hash=(global_bindings.recurrence_kernel_abi_hash),
                combined_recurrence_abi_hash=(
                    global_bindings.combined_recurrence_abi_hash
                ),
                kernel_identity_hash=global_bindings.kernel_identity_hash,
                kernel_source_sha256=global_bindings.kernel_source_sha256,
                canonical_schedule_hash=sealed_bindings.canonical_schedule_hash,
                checkpoint_schedule_hash=sealed_bindings.checkpoint_schedule_hash,
                global_full_schedule_hash=global_bindings.global_full_schedule_hash,
                sealed_prefix_schedule_hash=(
                    global_bindings.sealed_prefix_schedule_hash
                ),
                continuation_schedule_hash=(global_bindings.continuation_schedule_hash),
                direct_generation_binding_hash=(
                    global_bindings.direct_generation_binding_hash
                ),
                physical_projection_hash=global_bindings.physical_projection_hash,
                program_descriptor_hash=expected["program_descriptor_hash"],
                architecture=global_bindings.architecture,
                device_ordinal=global_bindings.device_ordinal,
                ledger_algorithm=(
                    HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_LEDGER_ALGORITHM_V1
                ),
                descriptor_algorithm=(
                    HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_DESCRIPTOR_ALGORITHM_V1
                ),
            ),
            window=HipFgmresRecurrenceLaunchFenceAuditWindowV1(
                start_boundary=(
                    HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_START_BOUNDARY_V1
                ),
                end_boundary=(HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_END_BOUNDARY_V1),
                start_operation_ordinal=start.operation_ordinal,
                end_operation_ordinal=end.operation_ordinal,
                start_event_sequence=start.event_sequence,
                end_event_sequence=end.event_sequence,
                start_rolling_hash=start.rolling_hash,
                end_rolling_hash=end.rolling_hash,
                first_recurrence_launch_ordinal=first_launch,
                canonical_fence_ordinal=canonical_fence,
                sealed_checkpoint_fence_ordinal=sealed_fence,
                terminal_fence_ordinal=terminal_fence,
                start_in_flight_count=0,
                end_in_flight_count=0,
                terminal_event_kind="fence",
                terminal_event_disposition="success",
            ),
            dimensions=HipFgmresRecurrenceLaunchFenceAuditDimensionsV1(
                free_dof_count=global_receipt.dimensions.free_dof_count,
                restart_dimension=global_receipt.dimensions.restart_dimension,
                max_iterations=global_receipt.dimensions.max_iterations,
                maximum_restart_count=(global_receipt.dimensions.maximum_restart_count),
                reduction_stage_count=(global_receipt.dimensions.reduction_stage_count),
                prelaunch_memset_count=8,
                canonical_launch_count=canonical_count,
                sealed_checkpoint_launch_count=4,
                continuation_launch_count=continuation_count,
                full_program_launch_count=full_count,
                fence_count=3,
                total_native_call_count=8 + full_count + 3,
            ),
            telemetry=telemetry,
            claims=HipFgmresRecurrenceLaunchFenceAuditClaimsV1(
                exact_process_local_kernel_ledger_bound=True,
                canonical_to_terminal_fence_lineage_bound=True,
                fixed_recurrence_descriptor_order_replayed=True,
                native_attempt_recorded_before_each_owned_call=True,
                canonical_sealed_terminal_fences_ordered=True,
                exact_successful_call_counts_bound=True,
                constant_space_rolling_ledger_bound=True,
            ),
            receipt_hash=_ZERO_HASH,
        )
        receipt = replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )
        return validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(receipt)


_LEDGER_AUDIT_OWNERS_LOCK = threading.RLock()
_LEDGER_AUDIT_OWNERS: weakref.WeakKeyDictionary[
    Any,
    weakref.ReferenceType[Any],
] = weakref.WeakKeyDictionary()


def open_hip_fgmres_recurrence_launch_fence_audit_v1(
    canonical_context: HipFgmresCanonicalPredecessorExecutionContextV1,
) -> HipFgmresRecurrenceLaunchFenceAuditOpenResultV1:
    if type(canonical_context) is not HipFgmresCanonicalPredecessorExecutionContextV1:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_canonical_invalid",
            "/canonical_context",
        )
    with canonical_context._lock:
        canonical_receipt = canonical_context.receipt()
        if canonical_receipt.status != "context_ready":
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_canonical_not_ready",
                "/canonical_context/status",
            )
        canonical_context._validate_authority(require_idle_kernel=True)
        live = canonical_context._require_live()
        kernel = canonical_context._kernel()
        token = live._checkpoint_token
        capture = _capture_rtc_launch_fence_ledger_v1(kernel, token)
        if capture.snapshot.total_in_flight_count != 0:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_inflight",
                "/window/start",
            )
        if capture.binding_snapshot != live._kernel_binding_snapshot:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_binding_invalid",
                "/kernel/binding",
            )
        if canonical_context.receipt() != canonical_receipt:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_start_boundary_changed",
                "/window/start",
            )
        context = HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1(
            canonical_context,
            capture,
            token,
            canonical_receipt.receipt_hash,
        )
        _reserve_ledger_audit_owner(capture.state, context)
    return HipFgmresRecurrenceLaunchFenceAuditOpenResultV1(context=context)


def validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(
    receipt: HipFgmresRecurrenceLaunchFenceAuditReceiptV1,
    *,
    expected_context: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1
    | None = None,
) -> HipFgmresRecurrenceLaunchFenceAuditReceiptV1:
    if type(receipt) is not HipFgmresRecurrenceLaunchFenceAuditReceiptV1:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_receipt_invalid",
            "/",
        )
    _validate_exact_types(receipt)
    payload = _receipt_payload(receipt, include_hash=False)
    if (
        type(receipt.receipt_hash) is not str
        or _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != canonical_hash(payload)
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_hash_invalid",
            "/receipt_hash",
        )
    errors = sorted(
        _schema_validator().iter_errors(_receipt_payload(receipt, include_hash=True)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_schema_invalid",
            "/",
            errors[0].message,
        )
    _validate_semantics(receipt)
    if expected_context is not None:
        if (
            type(expected_context)
            is not HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1
        ):
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_context_invalid",
                "/expected_context",
            )
        with expected_context._lock:
            if (
                expected_context._result is None
                or expected_context._result.receipt is not receipt
                or expected_context._state not in {"sealed", "closed"}
            ):
                _fail(
                    "hip_fgmres_recurrence_launch_fence_audit_context_mismatch",
                    "/expected_context",
                )
    return receipt


def validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
    result: HipFgmresRecurrenceLaunchFenceAuditResultV1,
    *,
    expected_context: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1
    | None = None,
) -> HipFgmresRecurrenceLaunchFenceAuditResultV1:
    if type(result) is not HipFgmresRecurrenceLaunchFenceAuditResultV1:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_result_invalid",
            "/",
        )
    validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(
        result.receipt,
        expected_context=expected_context,
    )
    return result


def _counter_delta(
    start: HipFgmresRtcOperationCounterV1,
    end: HipFgmresRtcOperationCounterV1,
    *,
    path: str,
    cleanup_owner: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1,
) -> HipFgmresRtcOperationCounterV1:
    if (
        type(start) is not HipFgmresRtcOperationCounterV1
        or type(end) is not HipFgmresRtcOperationCounterV1
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_counter_invalid",
            path,
            cleanup_owner=cleanup_owner,
        )
    values = tuple(
        getattr(end, name) - getattr(start, name) for name in start.__dataclass_fields__
    )
    if any(type(value) is not int or value < 0 for value in values):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_counter_regressed",
            path,
            cleanup_owner=cleanup_owner,
        )
    return HipFgmresRtcOperationCounterV1(*values)


def _reserve_ledger_audit_owner(state: Any, context: Any) -> None:
    with _LEDGER_AUDIT_OWNERS_LOCK:
        reference = _LEDGER_AUDIT_OWNERS.get(state)
        owner = reference() if reference is not None else None
        if owner is not None and owner is not context:
            _fail(
                "hip_fgmres_recurrence_launch_fence_audit_ledger_busy",
                "/ledger/owner",
            )
        _LEDGER_AUDIT_OWNERS[state] = weakref.ref(context)


def _release_ledger_audit_owner(state: Any, context: Any) -> None:
    with _LEDGER_AUDIT_OWNERS_LOCK:
        reference = _LEDGER_AUDIT_OWNERS.get(state)
        if reference is not None and reference() is context:
            _LEDGER_AUDIT_OWNERS.pop(state, None)


def _validate_exact_types(
    receipt: HipFgmresRecurrenceLaunchFenceAuditReceiptV1,
) -> None:
    expected = (
        (receipt.bindings, HipFgmresRecurrenceLaunchFenceAuditBindingsV1),
        (receipt.window, HipFgmresRecurrenceLaunchFenceAuditWindowV1),
        (receipt.dimensions, HipFgmresRecurrenceLaunchFenceAuditDimensionsV1),
        (receipt.telemetry, HipFgmresRecurrenceLaunchFenceAuditTelemetryV1),
        (receipt.claims, HipFgmresRecurrenceLaunchFenceAuditClaimsV1),
        (receipt.telemetry.memset, HipFgmresRtcOperationCounterV1),
        (receipt.telemetry.launch, HipFgmresRtcOperationCounterV1),
        (receipt.telemetry.fence, HipFgmresRtcOperationCounterV1),
    )
    if any(type(value) is not kind for value, kind in expected):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_type_invalid",
            "/",
        )
    payload = _receipt_payload(receipt, include_hash=True)
    _require_exact_json_types(payload, "/")


def _require_exact_json_types(value: Any, path: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail(
                    "hip_fgmres_recurrence_launch_fence_audit_type_invalid",
                    path,
                )
            _require_exact_json_types(item, f"{path}/{key}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _require_exact_json_types(item, f"{path}/{index}")
        return
    if type(value) not in {str, int, bool, type(None)}:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_type_invalid",
            path,
        )


def _validate_semantics(
    receipt: HipFgmresRecurrenceLaunchFenceAuditReceiptV1,
) -> None:
    bindings = receipt.bindings
    window = receipt.window
    dimensions = receipt.dimensions
    telemetry = receipt.telemetry
    claims = receipt.claims
    hashes = tuple(
        getattr(bindings, name)
        for name in bindings.__dataclass_fields__
        if name.endswith("_hash") or name.endswith("_sha256")
    ) + (
        window.start_rolling_hash,
        window.end_rolling_hash,
        receipt.context_id,
        receipt.receipt_hash,
    )
    if any(
        type(value) is not str or _HASH_RE.fullmatch(value) is None for value in hashes
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_binding_invalid",
            "/bindings",
        )
    integer_values = (
        bindings.device_ordinal,
        *(
            getattr(window, name)
            for name in (
                "start_operation_ordinal",
                "end_operation_ordinal",
                "start_event_sequence",
                "end_event_sequence",
                "first_recurrence_launch_ordinal",
                "canonical_fence_ordinal",
                "sealed_checkpoint_fence_ordinal",
                "terminal_fence_ordinal",
                "start_in_flight_count",
                "end_in_flight_count",
            )
        ),
        *(getattr(dimensions, name) for name in dimensions.__dataclass_fields__),
        telemetry.operation_ordinal_delta,
        telemetry.event_sequence_delta,
        *(
            getattr(row, name)
            for row in (telemetry.memset, telemetry.launch, telemetry.fence)
            for name in row.__dataclass_fields__
        ),
    )
    if any(
        type(value) is not int or value < 0 or value > _MAX_JSON_SAFE_INTEGER
        for value in integer_values
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_type_invalid",
            "/",
        )
    if (
        receipt.status != "ordinal_chain_sealed"
        or receipt.evidence_scope
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_EVIDENCE_SCOPE_V1
        or receipt.actual_backend not in {"hip", "test_double"}
        or receipt.promotion_eligible is not False
        or bindings.ledger_algorithm
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_LEDGER_ALGORITHM_V1
        or bindings.descriptor_algorithm
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_DESCRIPTOR_ALGORITHM_V1
        or window.start_boundary
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_START_BOUNDARY_V1
        or window.end_boundary
        != HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_END_BOUNDARY_V1
        or any(
            getattr(bindings, name) is not False
            for name in (
                "runtime_identity_serialized",
                "stream_identity_serialized",
                "checkpoint_token_identity_serialized",
                "kernel_object_identity_serialized",
            )
        )
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_semantics_invalid",
            "/",
        )
    expected_context_id = canonical_hash(
        {
            "profile": HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_CAPABILITY_PROFILE_V1,
            "canonical_context_id": bindings.canonical_context_id,
            "canonical_open_receipt_hash": bindings.canonical_open_receipt_hash,
            "global_context_id": bindings.global_context_id,
            "global_receipt_hash": bindings.global_receipt_hash,
            "start_operation_ordinal": window.start_operation_ordinal,
            "start_rolling_hash": window.start_rolling_hash,
        }
    )
    if (
        receipt.context_id != expected_context_id
        or bindings.completion_receipt_hash != bindings.global_receipt_hash
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_binding_invalid",
            "/bindings",
        )
    if (
        dimensions.prelaunch_memset_count != 8
        or dimensions.sealed_checkpoint_launch_count != 4
        or dimensions.fence_count != 3
        or dimensions.full_program_launch_count
        != dimensions.canonical_launch_count
        + dimensions.sealed_checkpoint_launch_count
        + dimensions.continuation_launch_count
        or dimensions.total_native_call_count
        != dimensions.prelaunch_memset_count
        + dimensions.full_program_launch_count
        + dimensions.fence_count
        or dimensions.maximum_restart_count
        != (dimensions.max_iterations + dimensions.restart_dimension - 1)
        // dimensions.restart_dimension
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_dimensions_invalid",
            "/dimensions",
        )
    expected_ordinals = (
        window.start_operation_ordinal + 9,
        window.start_operation_ordinal + 9 + dimensions.canonical_launch_count,
        window.start_operation_ordinal + 9 + dimensions.canonical_launch_count + 5,
        window.start_operation_ordinal + dimensions.total_native_call_count,
    )
    if (
        (
            window.first_recurrence_launch_ordinal,
            window.canonical_fence_ordinal,
            window.sealed_checkpoint_fence_ordinal,
            window.terminal_fence_ordinal,
        )
        != expected_ordinals
        or window.end_operation_ordinal != window.terminal_fence_ordinal
        or window.end_operation_ordinal - window.start_operation_ordinal
        != dimensions.total_native_call_count
        or window.end_event_sequence - window.start_event_sequence
        != 2 * dimensions.total_native_call_count
        or window.start_event_sequence != 2 * window.start_operation_ordinal
        or window.end_event_sequence != 2 * window.end_operation_ordinal
        or telemetry.operation_ordinal_delta != dimensions.total_native_call_count
        or telemetry.event_sequence_delta != 2 * dimensions.total_native_call_count
        or window.start_in_flight_count != 0
        or window.end_in_flight_count != 0
        or window.terminal_event_kind != "fence"
        or window.terminal_event_disposition != "success"
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_window_invalid",
            "/window",
        )
    expected_rows = (
        (telemetry.memset, dimensions.prelaunch_memset_count),
        (telemetry.launch, dimensions.full_program_launch_count),
        (telemetry.fence, dimensions.fence_count),
    )
    if any(
        row != HipFgmresRtcOperationCounterV1(count, count, 0, 0, 0)
        for row, count in expected_rows
    ):
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_telemetry_invalid",
            "/telemetry",
        )
    expected_claims = HipFgmresRecurrenceLaunchFenceAuditClaimsV1(
        exact_process_local_kernel_ledger_bound=True,
        canonical_to_terminal_fence_lineage_bound=True,
        fixed_recurrence_descriptor_order_replayed=True,
        native_attempt_recorded_before_each_owned_call=True,
        canonical_sealed_terminal_fences_ordered=True,
        exact_successful_call_counts_bound=True,
        constant_space_rolling_ledger_bound=True,
    )
    if claims != expected_claims:
        _fail(
            "hip_fgmres_recurrence_launch_fence_audit_claim_invalid",
            "/claims",
        )


def _receipt_payload(
    receipt: HipFgmresRecurrenceLaunchFenceAuditReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": receipt.promotion_eligible,
        "bindings": receipt.bindings.to_dict(),
        "window": receipt.window.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _detail(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:512] or "unspecified"


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1 | None = None,
) -> NoReturn:
    raise HipFgmresRecurrenceLaunchFenceAuditV1Error(
        code,
        path,
        message,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_RECURRENCE_LAUNCH_FENCE_AUDIT_SCHEMA_VERSION_V1",
    "HipFgmresRecurrenceLaunchFenceAuditBindingsV1",
    "HipFgmresRecurrenceLaunchFenceAuditClaimsV1",
    "HipFgmresRecurrenceLaunchFenceAuditDimensionsV1",
    "HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1",
    "HipFgmresRecurrenceLaunchFenceAuditOpenResultV1",
    "HipFgmresRecurrenceLaunchFenceAuditReceiptV1",
    "HipFgmresRecurrenceLaunchFenceAuditResultV1",
    "HipFgmresRecurrenceLaunchFenceAuditTelemetryV1",
    "HipFgmresRecurrenceLaunchFenceAuditV1Error",
    "HipFgmresRecurrenceLaunchFenceAuditWindowV1",
    "open_hip_fgmres_recurrence_launch_fence_audit_v1",
    "validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1",
    "validate_hip_fgmres_recurrence_launch_fence_audit_result_v1",
]
