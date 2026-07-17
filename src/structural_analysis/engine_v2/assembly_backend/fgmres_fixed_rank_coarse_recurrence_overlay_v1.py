"""Same-stream fixed-rank coarse overlay for the canonical FGMRES recurrence.

The v1 overlay deliberately preserves the accepted recurrence-v2 ABI and its
``APPLY_JACOBI_INDEXED`` row.  Immediately after each such logical row, it
submits the four fixed-rank coarse kernels on the exact same stream, so the
coarse result overwrites ``preconditioned_basis_z`` before
``PRECONDITION_ACCEPT`` and the following Arnoldi SpMV consume it.  This is a
real numerical data-path integration, but not yet removal of the legacy
Jacobi launch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import re
import threading
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_canonical_predecessor_v1 import (
    HipFgmresCanonicalPredecessorExecutionContextV1,
)
from .fgmres_fixed_rank_coarse_context_v1 import (
    HipFgmresFixedRankCoarseApplicationReceiptV1,
    HipFgmresFixedRankCoarseExecutionContextV1,
    validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1,
    validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1,
)
from .fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceExecutionContextV1,
    validate_hip_fgmres_global_recurrence_receipt_v1,
)
from .fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from .fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointExecutionContextV1,
    validate_hip_fgmres_live_checkpoint_context_receipt_v1,
)
from .fgmres_recurrence_plan_v2 import _VECTOR_MODE_CODES
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeObservationResultV1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)


HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-recurrence-overlay.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_CAPABILITY_PROFILE = (
    "phase0_live_fgmres_fixed_rank_coarse_recurrence_overlay"
)
HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_EVIDENCE_SCOPE = (
    "same_stream_canonical_and_global_recurrence_overlay_non_promoting"
)

CoarseRecurrenceOverlayStatusV1 = Literal[
    "context_ready",
    "canonical_overlay_pending",
    "canonical_fenced",
    "global_overlay_pending",
    "recurrence_fenced",
    "terminal_bound",
    "poisoned",
    "cleanup_failed",
    "context_closed",
]
OverlayPhaseV1 = Literal["canonical_prefix", "global_suffix"]

_SCHEMA_RESOURCE = "hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1.schema.json"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONTEXT_MINT = object()


class HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(RuntimeError):
    """Stable overlay error retaining the exact cleanup owner."""

    def __init__(
        self,
        code: str,
        path: str,
        detail: str = "",
        *,
        cleanup_owner: HipFgmresFixedRankCoarseRecurrenceOverlayV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code} at {path}" + (f": {detail}" if detail else ""))


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayBindingsV1:
    live_checkpoint_context_id: str
    live_checkpoint_opening_receipt_hash: str
    coarse_context_id: str
    coarse_context_opening_receipt_hash: str
    source_fgmres_plan_hash: str
    recurrence_plan_hash: str
    recurrence_kernel_identity_hash: str
    recurrence_kernel_source_sha256: str
    coarse_plan_hash: str
    coarse_space_hash: str
    coarse_kernel_identity_hash: str
    coarse_kernel_source_sha256: str
    full_schedule_hash: str
    sealed_prefix_schedule_hash: str
    continuation_schedule_hash: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1:
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    retained_rank: int
    expected_application_count: int
    canonical_prefix_application_count: Literal[1] = 1
    global_suffix_application_count: int = 0
    retained_jacobi_row_count: int = 0
    coarse_launches_per_application: Literal[4] = 4

    def to_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in asdict(self).items()}


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayApplicationV1:
    sequence: int
    phase: OverlayPhaseV1
    restart_index: int
    column_index: int
    logical_index: int
    coarse_application_receipt_hash: str
    retained_jacobi_launch_count: Literal[1] = 1
    accepted_coarse_launch_count: Literal[4] = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayTelemetryV1:
    application_attempt_count: int = 0
    application_success_count: int = 0
    canonical_prefix_application_count: int = 0
    global_suffix_application_count: int = 0
    retained_jacobi_launch_count: int = 0
    coarse_kernel_launch_count: int = 0
    external_parent_fence_ack_count: int = 0
    externally_acknowledged_coarse_launch_count: int = 0
    additional_h2d_copy_count: Literal[0] = 0
    additional_d2h_copy_count: Literal[0] = 0
    additional_allocation_count: Literal[0] = 0
    additional_synchronization_count: Literal[0] = 0
    additional_csr_apply_count: Literal[0] = 0
    host_terminal_branch_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in asdict(self).items()}


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayClaimsV1:
    exact_live_and_coarse_contexts_bound: bool
    fixed_schedule_coordinates_bound: bool
    same_stream_overlay_order_bound: bool
    coarse_output_consumed_by_recurrence: bool
    terminal_observation_bound: bool
    application_window_host_copy_zero: bool
    no_additional_intermediate_synchronization: bool
    canonical_jacobi_row_retained: Literal[True] = True
    canonical_jacobi_row_replaced: Literal[False] = False
    coarse_device_status_directly_terminal_bound: Literal[False] = False
    full_iteration_host_copy_zero_proven: Literal[False] = False
    end_to_end_o_n_proven: Literal[False] = False
    speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
    status: CoarseRecurrenceOverlayStatusV1
    context_id: str
    evidence_scope: str
    actual_backend: Literal["hip", "test_double"]
    promotion_eligible: Literal[False]
    reason: HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1 | None
    bindings: HipFgmresFixedRankCoarseRecurrenceOverlayBindingsV1
    dimensions: HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1
    applications: tuple[HipFgmresFixedRankCoarseRecurrenceOverlayApplicationV1, ...]
    application_sequence_hash: str
    global_context_id: str
    global_receipt_hash: str
    terminal_observation_receipt_hash: str
    terminal_outcome_hash: str
    telemetry: HipFgmresFixedRankCoarseRecurrenceOverlayTelemetryV1
    claims: HipFgmresFixedRankCoarseRecurrenceOverlayClaimsV1
    receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseRecurrenceOverlayOpenResultV1:
    context: HipFgmresFixedRankCoarseRecurrenceOverlayV1
    receipt: HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1

    @property
    def ready(self) -> bool:
        return not self.context.closed and self.receipt.status == "context_ready"


class HipFgmresFixedRankCoarseRecurrenceOverlayV1:
    """Single-use coordinator spanning canonical and global recurrence owners."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("Coarse recurrence overlays are factory-issued only.")
        self._lock = threading.RLock()
        self._token = object()
        self._live: HipFgmresLiveCheckpointExecutionContextV1 | None = None
        self._coarse: HipFgmresFixedRankCoarseExecutionContextV1 | None = None
        self._canonical_owner: (
            HipFgmresCanonicalPredecessorExecutionContextV1 | None
        ) = None
        self._global_owner: HipFgmresGlobalRecurrenceExecutionContextV1 | None = None
        self._coordinates: tuple[tuple[int, int], ...] = ()
        self._applications: list[
            HipFgmresFixedRankCoarseRecurrenceOverlayApplicationV1
        ] = []
        self._application_receipts: list[
            HipFgmresFixedRankCoarseApplicationReceiptV1
        ] = []
        self._bindings: HipFgmresFixedRankCoarseRecurrenceOverlayBindingsV1 | None = (
            None
        )
        self._dimensions: (
            HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1 | None
        ) = None
        self._context_id = _ZERO_HASH
        self._actual_backend: Literal["hip", "test_double"] = "test_double"
        self._telemetry = HipFgmresFixedRankCoarseRecurrenceOverlayTelemetryV1()
        self._state: CoarseRecurrenceOverlayStatusV1 = "context_ready"
        self._reason: HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1 | None = None
        self._terminal: HipFgmresTerminalOutcomeObservationResultV1 | None = None
        self._global_context_id = _ZERO_HASH
        self._global_receipt_hash = _ZERO_HASH
        self._live_reserved = False
        self._coarse_reserved = False
        self._live_released = False
        self._coarse_released = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def receipt(self) -> HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
        with self._lock:
            return self._build_receipt(self._state)

    def bind_terminal_observation(
        self,
        result: HipFgmresTerminalOutcomeObservationResultV1,
    ) -> HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
        """Bind the exact downstream terminal observer after recurrence fencing."""

        with self._lock:
            if self._state == "terminal_bound" and self._terminal is result:
                return self._build_receipt("terminal_bound")
            if self._state != "recurrence_fenced" or self._closed:
                _fail(
                    "hip_fgmres_coarse_overlay_terminal_state_invalid",
                    "/terminal",
                    cleanup_owner=self,
                )
            validate_hip_fgmres_terminal_outcome_observation_result_v1(result)
            global_owner = self._require_global_owner()
            global_receipt = validate_hip_fgmres_global_recurrence_receipt_v1(
                global_owner.receipt(),
                expected_context=global_owner,
            )
            terminal = result.receipt
            dimensions = self._require_dimensions()
            if (
                global_receipt.status != "recurrence_fenced"
                or terminal.bindings.global_context_id != global_receipt.context_id
                or terminal.bindings.global_receipt_hash != global_receipt.receipt_hash
                or terminal.dimensions.free_dof_count != dimensions.free_dof_count
                or terminal.dimensions.maximum_restart_count
                != dimensions.maximum_restart_count
                or terminal.outcome.counters.preconditioner_apply_count
                != terminal.outcome.counters.effective_iterations
                or terminal.outcome.counters.effective_iterations
                > dimensions.max_iterations
            ):
                _fail(
                    "hip_fgmres_coarse_overlay_terminal_binding_invalid",
                    "/terminal/bindings",
                    cleanup_owner=self,
                )
            self._terminal = result
            self._state = "terminal_bound"
            receipt = self._build_receipt("terminal_bound")
            return validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
                receipt,
                expected_context=self,
            )

    def close(self) -> None:
        """Release route authority before allowing the coarse context to close."""

        with self._lock:
            if self._closed:
                return
            coarse = self._require_coarse()
            pending_coarse_work = coarse._stream_work_requires_fence or (
                coarse._kernel is not None and coarse._kernel.pending
            )
            if pending_coarse_work and self._state != "poisoned":
                _fail(
                    "hip_fgmres_coarse_overlay_parent_fence_required",
                    "/cleanup/fence",
                    cleanup_owner=self,
                )
            if pending_coarse_work:
                coarse.fence()
            try:
                if self._live_reserved and not self._live_released:
                    self._require_live()._release_fixed_rank_coarse_overlay(
                        self._token,
                        self,
                    )
                    self._live_released = True
                if self._coarse_reserved and not self._coarse_released:
                    coarse._release_recurrence_overlay_child(self._token, self)
                    self._coarse_released = True
            except BaseException as exc:
                self._state = "cleanup_failed"
                self._reason = HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1(
                    "hip_fgmres_coarse_overlay_cleanup_failed",
                    _detail(exc),
                )
                raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
                    self._reason.code,
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"

    def _enqueue_after_jacobi(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
        *,
        phase: str,
        owner: object,
        expected_restart: int,
        expected_column: int,
        logical_index: int,
    ) -> HipFgmresFixedRankCoarseApplicationReceiptV1:
        with self._lock:
            self._require_route(token, live)
            typed_phase, typed_owner = self._validate_phase_owner(phase, owner)
            index = len(self._applications)
            if index >= len(self._coordinates):
                _fail(
                    "hip_fgmres_coarse_overlay_application_count_exceeded",
                    "/applications",
                    cleanup_owner=self,
                )
            coordinate = self._coordinates[index]
            expected_phase: OverlayPhaseV1 = (
                "canonical_prefix" if index == 0 else "global_suffix"
            )
            if (
                typed_phase != expected_phase
                or coordinate != (expected_restart, expected_column)
                or logical_index != expected_column
                or self._closed
                or self._state
                not in {
                    "context_ready",
                    "canonical_fenced",
                    "global_overlay_pending",
                }
            ):
                _fail(
                    "hip_fgmres_coarse_overlay_coordinate_invalid",
                    f"/applications/{index}",
                    cleanup_owner=self,
                )
            if typed_phase == "canonical_prefix":
                if self._canonical_owner not in {None, typed_owner}:
                    _fail(
                        "hip_fgmres_coarse_overlay_canonical_owner_changed",
                        "/owners/canonical",
                        cleanup_owner=self,
                    )
                self._canonical_owner = typed_owner
            else:
                if self._global_owner not in {None, typed_owner}:
                    _fail(
                        "hip_fgmres_coarse_overlay_global_owner_changed",
                        "/owners/global",
                        cleanup_owner=self,
                    )
                self._global_owner = typed_owner
            self._telemetry = replace(
                self._telemetry,
                application_attempt_count=self._telemetry.application_attempt_count + 1,
            )
            if typed_phase == "canonical_prefix":
                pending_bounds = (
                    typed_owner._telemetry.async_operation_accept_lower_bound,
                    typed_owner._telemetry.async_operation_accept_upper_bound,
                )
            else:
                pending_bounds = (
                    typed_owner._telemetry.kernel_launch_accept_lower_bound,
                    typed_owner._telemetry.kernel_launch_accept_upper_bound,
                )
            coarse = self._require_coarse()
            accepted_before = coarse.receipt().telemetry.kernel_launch_success_count
            try:
                application = coarse._enqueue_recurrence_overlay_application(
                    self._token,
                    self,
                    logical_index,
                    pending_bounds,
                )
            except BaseException as exc:
                accepted_after = coarse.receipt().telemetry.kernel_launch_success_count
                accepted_delta = accepted_after - accepted_before
                if not 0 <= accepted_delta <= 4:
                    accepted_delta = 0
                self._telemetry = replace(
                    self._telemetry,
                    retained_jacobi_launch_count=(
                        self._telemetry.retained_jacobi_launch_count + 1
                    ),
                    coarse_kernel_launch_count=(
                        self._telemetry.coarse_kernel_launch_count + accepted_delta
                    ),
                )
                self._poison("hip_fgmres_coarse_overlay_application_failed", exc)
                raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
                    "hip_fgmres_coarse_overlay_application_failed",
                    f"/applications/{index}",
                    _detail(exc),
                    cleanup_owner=self,
                ) from exc
            validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
                application,
                expected_context=coarse,
            )
            accepted_after = coarse.receipt().telemetry.kernel_launch_success_count
            if accepted_after - accepted_before != 4:
                self._poison(
                    "hip_fgmres_coarse_overlay_application_accounting_invalid",
                    "accepted coarse launch delta was not four",
                )
                _fail(
                    "hip_fgmres_coarse_overlay_application_accounting_invalid",
                    f"/applications/{index}",
                    cleanup_owner=self,
                )
            row = HipFgmresFixedRankCoarseRecurrenceOverlayApplicationV1(
                sequence=index + 1,
                phase=typed_phase,
                restart_index=expected_restart,
                column_index=expected_column,
                logical_index=logical_index,
                coarse_application_receipt_hash=application.receipt_hash,
            )
            self._applications.append(row)
            self._application_receipts.append(application)
            self._telemetry = replace(
                self._telemetry,
                application_success_count=self._telemetry.application_success_count + 1,
                canonical_prefix_application_count=(
                    self._telemetry.canonical_prefix_application_count
                    + (1 if typed_phase == "canonical_prefix" else 0)
                ),
                global_suffix_application_count=(
                    self._telemetry.global_suffix_application_count
                    + (1 if typed_phase == "global_suffix" else 0)
                ),
                retained_jacobi_launch_count=(
                    self._telemetry.retained_jacobi_launch_count + 1
                ),
                coarse_kernel_launch_count=self._telemetry.coarse_kernel_launch_count
                + 4,
            )
            self._state = (
                "canonical_overlay_pending"
                if typed_phase == "canonical_prefix"
                else "global_overlay_pending"
            )
            return application

    def _acknowledge_parent_fence(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
        *,
        phase: str,
        owner: object,
    ) -> int:
        with self._lock:
            self._require_route(token, live)
            typed_phase, typed_owner = self._validate_phase_owner(phase, owner)
            dimensions = self._require_dimensions()
            if self._state == "poisoned":
                coarse = self._require_coarse()
                target = self._telemetry.coarse_kernel_launch_count
                current_acknowledged = (
                    coarse.receipt().telemetry.fence_acknowledged_launch_count
                )
                if current_acknowledged > target:
                    _fail(
                        "hip_fgmres_coarse_overlay_fence_ack_count_invalid",
                        f"/fences/{typed_phase}",
                        f"target={target}; current={current_acknowledged}",
                        cleanup_owner=self,
                    )
                remaining = target - current_acknowledged
                acknowledged = coarse._acknowledge_recurrence_overlay_fence(
                    self._token,
                    self,
                    remaining,
                )
                if (
                    acknowledged != remaining
                    or coarse.receipt().telemetry.fence_acknowledged_launch_count
                    != target
                ):
                    _fail(
                        "hip_fgmres_coarse_overlay_fence_ack_count_invalid",
                        f"/fences/{typed_phase}",
                        f"expected={remaining}; acknowledged={acknowledged}",
                        cleanup_owner=self,
                    )
                self._telemetry = replace(
                    self._telemetry,
                    external_parent_fence_ack_count=(
                        1 if typed_phase == "canonical_prefix" else 2
                    ),
                    externally_acknowledged_coarse_launch_count=target,
                )
                return acknowledged
            if typed_phase == "canonical_prefix":
                if (
                    typed_owner is not self._canonical_owner
                    or len(self._applications) != 1
                    or self._state
                    not in {"canonical_overlay_pending", "canonical_fenced"}
                ):
                    _fail(
                        "hip_fgmres_coarse_overlay_canonical_fence_invalid",
                        "/fences/canonical",
                        cleanup_owner=self,
                    )
                if self._state == "canonical_fenced":
                    return 0
            else:
                if self._global_owner is None:
                    self._global_owner = typed_owner
                if (
                    typed_owner is not self._global_owner
                    or len(self._applications) != dimensions.expected_application_count
                    or self._state
                    not in {
                        "canonical_fenced",
                        "global_overlay_pending",
                        "recurrence_fenced",
                    }
                ):
                    _fail(
                        "hip_fgmres_coarse_overlay_global_fence_invalid",
                        "/fences/global",
                        cleanup_owner=self,
                    )
                if self._state == "recurrence_fenced":
                    return 0
            coarse = self._require_coarse()
            target = (
                4
                if typed_phase == "canonical_prefix"
                else 4 * dimensions.expected_application_count
            )
            current_acknowledged = (
                coarse.receipt().telemetry.fence_acknowledged_launch_count
            )
            if current_acknowledged > target:
                _fail(
                    "hip_fgmres_coarse_overlay_fence_ack_count_invalid",
                    f"/fences/{typed_phase}",
                    f"target={target}; current={current_acknowledged}",
                    cleanup_owner=self,
                )
            remaining = target - current_acknowledged
            try:
                acknowledged = coarse._acknowledge_recurrence_overlay_fence(
                    self._token,
                    self,
                    remaining,
                )
            except BaseException as exc:
                committed = (
                    coarse.receipt().telemetry.fence_acknowledged_launch_count == target
                    and coarse._kernel is not None
                    and not coarse._kernel.pending
                )
                if not committed:
                    self._poison("hip_fgmres_coarse_overlay_fence_ack_failed", exc)
                    raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
                        "hip_fgmres_coarse_overlay_fence_ack_failed",
                        f"/fences/{typed_phase}",
                        _detail(exc),
                        cleanup_owner=self,
                    ) from exc
                acknowledged = remaining
            if (
                acknowledged != remaining
                or coarse.receipt().telemetry.fence_acknowledged_launch_count != target
            ):
                _fail(
                    "hip_fgmres_coarse_overlay_fence_ack_count_invalid",
                    f"/fences/{typed_phase}",
                    f"expected={remaining}; acknowledged={acknowledged}",
                    cleanup_owner=self,
                )
            self._telemetry = replace(
                self._telemetry,
                external_parent_fence_ack_count=(
                    1 if typed_phase == "canonical_prefix" else 2
                ),
                externally_acknowledged_coarse_launch_count=target,
            )
            self._state = (
                "canonical_fenced"
                if typed_phase == "canonical_prefix"
                else "recurrence_fenced"
            )
            return acknowledged

    def _bind_global_recurrence_receipt(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
        *,
        owner: object,
        receipt: object,
    ) -> None:
        """Store the final recurrence receipt before its owner may close."""

        with self._lock:
            self._require_route(token, live)
            if type(owner) is not HipFgmresGlobalRecurrenceExecutionContextV1:
                _fail(
                    "hip_fgmres_coarse_overlay_global_owner_invalid",
                    "/owners/global",
                    cleanup_owner=self,
                )
            if owner is not self._global_owner or self._state != "recurrence_fenced":
                _fail(
                    "hip_fgmres_coarse_overlay_global_publication_invalid",
                    "/global_receipt",
                    cleanup_owner=self,
                )
            validated = validate_hip_fgmres_global_recurrence_receipt_v1(
                receipt,  # type: ignore[arg-type]
            )
            if validated.status != "recurrence_fenced":
                _fail(
                    "hip_fgmres_coarse_overlay_global_publication_invalid",
                    "/global_receipt/status",
                    cleanup_owner=self,
                )
            if self._global_context_id not in {_ZERO_HASH, validated.context_id} or (
                self._global_receipt_hash not in {_ZERO_HASH, validated.receipt_hash}
            ):
                _fail(
                    "hip_fgmres_coarse_overlay_global_publication_changed",
                    "/global_receipt",
                    cleanup_owner=self,
                )
            self._global_context_id = validated.context_id
            self._global_receipt_hash = validated.receipt_hash

    def _validate_phase_owner(
        self,
        phase: str,
        owner: object,
    ) -> tuple[
        OverlayPhaseV1,
        HipFgmresCanonicalPredecessorExecutionContextV1
        | HipFgmresGlobalRecurrenceExecutionContextV1,
    ]:
        if phase == "canonical_prefix" and type(owner) is (
            HipFgmresCanonicalPredecessorExecutionContextV1
        ):
            return phase, owner
        if phase == "global_suffix" and type(owner) is (
            HipFgmresGlobalRecurrenceExecutionContextV1
        ):
            return phase, owner
        _fail(
            "hip_fgmres_coarse_overlay_owner_invalid",
            "/owners",
            cleanup_owner=self,
        )

    def _require_route(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
    ) -> None:
        if token is not self._token or live is not self._live or self._closed:
            _fail(
                "hip_fgmres_coarse_overlay_route_invalid",
                "/lifetime",
                cleanup_owner=self,
            )
        live._require_fixed_rank_coarse_overlay(self._token, self)
        self._require_coarse()._require_recurrence_overlay_child(self._token, self)

    def _poison(self, code: str, error: object) -> None:
        self._state = "poisoned"
        self._reason = HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1(
            code,
            _detail(error),
        )

    def _require_live(self) -> HipFgmresLiveCheckpointExecutionContextV1:
        if type(self._live) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_overlay_live_invalid",
                "/lifetime/live",
                cleanup_owner=self,
            )
        return self._live

    def _require_coarse(self) -> HipFgmresFixedRankCoarseExecutionContextV1:
        if type(self._coarse) is not HipFgmresFixedRankCoarseExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_overlay_context_invalid",
                "/lifetime/coarse",
                cleanup_owner=self,
            )
        return self._coarse

    def _require_global_owner(self) -> HipFgmresGlobalRecurrenceExecutionContextV1:
        if type(self._global_owner) is not HipFgmresGlobalRecurrenceExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_overlay_global_owner_invalid",
                "/owners/global",
                cleanup_owner=self,
            )
        return self._global_owner

    def _require_dimensions(
        self,
    ) -> HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1:
        if self._dimensions is None:
            _fail(
                "hip_fgmres_coarse_overlay_dimensions_invalid",
                "/dimensions",
                cleanup_owner=self,
            )
        return self._dimensions

    def _build_receipt(
        self,
        status: CoarseRecurrenceOverlayStatusV1,
    ) -> HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
        if self._bindings is None or self._dimensions is None:
            _fail(
                "hip_fgmres_coarse_overlay_receipt_unavailable",
                "/receipt",
                cleanup_owner=self,
            )
        applications = tuple(self._applications)
        sequence_hash = canonical_hash([row.to_dict() for row in applications])
        global_id = self._global_context_id
        global_hash = self._global_receipt_hash
        terminal_hash = _ZERO_HASH
        outcome_hash = _ZERO_HASH
        if self._terminal is not None:
            terminal_hash = self._terminal.receipt.receipt_hash
            outcome_hash = self._terminal.receipt.outcome_hash
        integrated = (
            len(applications) == self._dimensions.expected_application_count
            and self._state in {"recurrence_fenced", "terminal_bound", "context_closed"}
            and self._global_context_id != _ZERO_HASH
            and self._global_receipt_hash != _ZERO_HASH
        )
        claims = HipFgmresFixedRankCoarseRecurrenceOverlayClaimsV1(
            exact_live_and_coarse_contexts_bound=True,
            fixed_schedule_coordinates_bound=integrated,
            same_stream_overlay_order_bound=integrated,
            coarse_output_consumed_by_recurrence=integrated,
            terminal_observation_bound=self._terminal is not None,
            application_window_host_copy_zero=integrated,
            no_additional_intermediate_synchronization=integrated,
        )
        draft = HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=(
                HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_EVIDENCE_SCOPE
            ),
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=self._bindings,
            dimensions=self._dimensions,
            applications=applications,
            application_sequence_hash=sequence_hash,
            global_context_id=global_id,
            global_receipt_hash=global_hash,
            terminal_observation_receipt_hash=terminal_hash,
            terminal_outcome_hash=outcome_hash,
            telemetry=self._telemetry,
            claims=claims,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )


def open_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1(
    coarse_context: HipFgmresFixedRankCoarseExecutionContextV1,
) -> HipFgmresFixedRankCoarseRecurrenceOverlayOpenResultV1:
    """Reserve the exact coarse child and install one recurrence overlay route."""

    context = HipFgmresFixedRankCoarseRecurrenceOverlayV1(_mint=_CONTEXT_MINT)
    try:
        if type(coarse_context) is not HipFgmresFixedRankCoarseExecutionContextV1:
            _fail("hip_fgmres_coarse_overlay_context_invalid", "/coarse_context")
        coarse_receipt = validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
            coarse_context.receipt(),
            expected_context=coarse_context,
        )
        if (
            coarse_receipt.status != "context_ready"
            or coarse_context._sequence != 0
            or coarse_receipt.telemetry.application_attempt_count != 0
            or coarse_receipt.telemetry.application_success_count != 0
            or coarse_context._kernel is None
            or coarse_context._kernel.pending
        ):
            _fail(
                "hip_fgmres_coarse_overlay_pristine_context_required",
                "/coarse_context",
            )
        live = coarse_context._parent
        if type(live) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail("hip_fgmres_coarse_overlay_live_invalid", "/live_context")
        live_receipt = validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            live.receipt(),
            expected_context=live,
        )
        if live_receipt.status != "context_ready" or live._recurrence_plan is None:
            _fail("hip_fgmres_coarse_overlay_live_invalid", "/live_context")
        recurrence = live._recurrence_plan
        partition = compile_hip_fgmres_global_sealed_continuation_v1(
            recurrence.free_dof_count,
            recurrence.restart_dimension,
            recurrence.max_iterations,
        )
        rows = tuple(
            row
            for row in partition.full.launches
            if row.submission_kind == "vector"
            and row.mode == _VECTOR_MODE_CODES["APPLY_JACOBI_INDEXED"]
        )
        coordinates = tuple(
            (int(row.expected_restart), int(row.expected_column)) for row in rows
        )
        expected_coordinates = tuple(
            (restart, column)
            for restart in range(1, recurrence.maximum_restart_count + 1)
            for column in range(recurrence.restart_dimension)
        )
        if not coordinates or coordinates != expected_coordinates:
            _fail(
                "hip_fgmres_coarse_overlay_schedule_invalid",
                "/schedule/coordinates",
            )
        coarse_context._reserve_recurrence_overlay_child(context._token, context)
        context._coarse_reserved = True
        live._reserve_fixed_rank_coarse_overlay(
            context._token,
            context,
            coarse_context,
        )
        context._live_reserved = True
        context._live = live
        context._coarse = coarse_context
        context._coordinates = coordinates
        context._actual_backend = coarse_receipt.actual_backend  # type: ignore[assignment]
        context._context_id = canonical_hash(
            {
                "profile": (
                    HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_CAPABILITY_PROFILE
                ),
                "live_context_id": live_receipt.context_id,
                "coarse_context_id": coarse_receipt.context_id,
                "recurrence_plan_hash": recurrence.plan_hash,
                "coarse_plan_hash": coarse_receipt.bindings.coarse_plan_hash,
                "full_schedule_hash": partition.full.canonical_sha256,
            }
        )
        context._bindings = HipFgmresFixedRankCoarseRecurrenceOverlayBindingsV1(
            live_checkpoint_context_id=live_receipt.context_id,
            live_checkpoint_opening_receipt_hash=(
                live.opening_receipt.context_receipt_hash
            ),
            coarse_context_id=coarse_receipt.context_id,
            coarse_context_opening_receipt_hash=(
                coarse_context.opening_receipt.context_receipt_hash
            ),
            source_fgmres_plan_hash=coarse_receipt.bindings.source_fgmres_plan_hash,
            recurrence_plan_hash=recurrence.plan_hash,
            recurrence_kernel_identity_hash=live_receipt.kernel.identity_hash,
            recurrence_kernel_source_sha256=live_receipt.kernel.source_sha256,
            coarse_plan_hash=coarse_receipt.bindings.coarse_plan_hash,
            coarse_space_hash=coarse_receipt.bindings.coarse_space_hash,
            coarse_kernel_identity_hash=coarse_receipt.kernel.identity_hash,
            coarse_kernel_source_sha256=coarse_receipt.kernel.source_sha256,
            full_schedule_hash=partition.full.canonical_sha256,
            sealed_prefix_schedule_hash=partition.sealed_prefix.canonical_sha256,
            continuation_schedule_hash=partition.continuation.canonical_sha256,
        )
        context._dimensions = HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1(
            free_dof_count=recurrence.free_dof_count,
            restart_dimension=recurrence.restart_dimension,
            max_iterations=recurrence.max_iterations,
            maximum_restart_count=recurrence.maximum_restart_count,
            retained_rank=coarse_receipt.dimensions.retained_rank,
            expected_application_count=len(coordinates),
            global_suffix_application_count=len(coordinates) - 1,
            retained_jacobi_row_count=len(coordinates),
        )
        receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
            receipt,
            expected_context=context,
        )
        return HipFgmresFixedRankCoarseRecurrenceOverlayOpenResultV1(
            context,
            receipt,
        )
    except BaseException as primary:
        context._coarse = (
            coarse_context
            if type(coarse_context) is HipFgmresFixedRankCoarseExecutionContextV1
            else None
        )
        if context._live is None and context._coarse is not None:
            parent = context._coarse._parent
            if type(parent) is HipFgmresLiveCheckpointExecutionContextV1:
                context._live = parent
        cleanup_error: BaseException | None = None
        try:
            if context._live_reserved and not context._live_released:
                context._require_live()._release_fixed_rank_coarse_overlay(
                    context._token,
                    context,
                )
                context._live_released = True
            if context._coarse_reserved and not context._coarse_released:
                context._require_coarse()._release_recurrence_overlay_child(
                    context._token,
                    context,
                )
                context._coarse_released = True
        except BaseException as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
                "hip_fgmres_coarse_overlay_open_cleanup_failed",
                "/open/cleanup",
                f"primary={_detail(primary)}; cleanup={_detail(cleanup_error)}",
                cleanup_owner=context,
            ) from primary
        if isinstance(primary, HipFgmresFixedRankCoarseRecurrenceOverlayV1Error):
            raise
        raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
            "hip_fgmres_coarse_overlay_open_failed",
            "/open",
            _detail(primary),
        ) from primary


def validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
    receipt: HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1,
    *,
    expected_context: HipFgmresFixedRankCoarseRecurrenceOverlayV1 | None = None,
) -> HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
    """Validate one pointer-free overlay receipt and optional live provenance."""

    if type(receipt) is not HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1:
        _fail("hip_fgmres_coarse_overlay_receipt_type_invalid", "/receipt")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(
            "hip_fgmres_coarse_overlay_receipt_schema_invalid",
            path or "/",
            errors[0].message,
        )
    dimensions = receipt.dimensions
    applications = receipt.applications
    expected_count = dimensions.restart_dimension * dimensions.maximum_restart_count
    expected_coordinates = tuple(
        (restart, column)
        for restart in range(1, dimensions.maximum_restart_count + 1)
        for column in range(dimensions.restart_dimension)
    )
    actual_coordinates = tuple(
        (row.restart_index, row.column_index) for row in applications
    )
    global_bound = (
        receipt.global_context_id != _ZERO_HASH
        and receipt.global_receipt_hash != _ZERO_HASH
    )
    integrated = (
        receipt.status in {"recurrence_fenced", "terminal_bound", "context_closed"}
        and len(applications) == expected_count
        and global_bound
    )
    terminal_hashes_bound = (
        receipt.terminal_observation_receipt_hash != _ZERO_HASH
        and receipt.terminal_outcome_hash != _ZERO_HASH
    )
    terminal_bound = (
        receipt.status in {"terminal_bound", "context_closed"} and terminal_hashes_bound
    )
    healthy_state_valid = {
        "context_ready": (
            len(applications) == 0
            and receipt.telemetry.application_attempt_count == 0
            and receipt.telemetry.external_parent_fence_ack_count == 0
        ),
        "canonical_overlay_pending": (
            len(applications) == 1
            and receipt.telemetry.application_attempt_count == 1
            and receipt.telemetry.external_parent_fence_ack_count == 0
        ),
        "canonical_fenced": (
            len(applications) == 1
            and receipt.telemetry.application_attempt_count == 1
            and receipt.telemetry.external_parent_fence_ack_count == 1
            and receipt.telemetry.externally_acknowledged_coarse_launch_count == 4
        ),
        "global_overlay_pending": (
            2 <= len(applications) <= expected_count
            and receipt.telemetry.application_attempt_count == len(applications)
            and receipt.telemetry.external_parent_fence_ack_count == 1
            and receipt.telemetry.externally_acknowledged_coarse_launch_count == 4
        ),
        "recurrence_fenced": (
            integrated
            and receipt.telemetry.application_attempt_count == expected_count
            and receipt.telemetry.external_parent_fence_ack_count == 2
            and receipt.telemetry.externally_acknowledged_coarse_launch_count
            == 4 * expected_count
        ),
        "terminal_bound": (
            integrated
            and terminal_bound
            and receipt.telemetry.application_attempt_count == expected_count
            and receipt.telemetry.external_parent_fence_ack_count == 2
            and receipt.telemetry.externally_acknowledged_coarse_launch_count
            == 4 * expected_count
        ),
    }
    reason_valid = (
        receipt.reason is not None
        if receipt.status in {"poisoned", "cleanup_failed"}
        else receipt.reason is None
        if receipt.status != "context_closed"
        else True
    )
    if (
        receipt.schema_version
        != HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION
        or receipt.evidence_scope
        != HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_EVIDENCE_SCOPE
        or receipt.promotion_eligible is not False
        or not _valid_hash(receipt.context_id)
        or not _valid_hash(receipt.receipt_hash)
        or not _valid_hash(receipt.application_sequence_hash)
        or dimensions.free_dof_count <= 0
        or dimensions.restart_dimension <= 0
        or dimensions.max_iterations <= 0
        or dimensions.maximum_restart_count <= 0
        or dimensions.retained_rank <= 0
        or dimensions.expected_application_count != expected_count
        or dimensions.canonical_prefix_application_count != 1
        or dimensions.global_suffix_application_count != expected_count - 1
        or dimensions.retained_jacobi_row_count != expected_count
        or dimensions.coarse_launches_per_application != 4
        or len(applications) > expected_count
        or actual_coordinates != expected_coordinates[: len(applications)]
        or any(
            row.sequence != index + 1
            or row.phase != ("canonical_prefix" if index == 0 else "global_suffix")
            or row.logical_index != row.column_index
            or row.retained_jacobi_launch_count != 1
            or row.accepted_coarse_launch_count != 4
            or not _valid_hash(row.coarse_application_receipt_hash)
            for index, row in enumerate(applications)
        )
        or receipt.application_sequence_hash
        != canonical_hash([row.to_dict() for row in applications])
        or not reason_valid
        or (
            receipt.status in healthy_state_valid
            and not healthy_state_valid[receipt.status]
        )
        or not len(applications)
        <= receipt.telemetry.application_attempt_count
        <= expected_count
        or receipt.telemetry.application_success_count != len(applications)
        or receipt.telemetry.canonical_prefix_application_count
        != min(1, len(applications))
        or receipt.telemetry.global_suffix_application_count
        != max(0, len(applications) - 1)
        or receipt.telemetry.retained_jacobi_launch_count
        != receipt.telemetry.application_attempt_count
        or not 4 * len(applications)
        <= receipt.telemetry.coarse_kernel_launch_count
        <= 4 * receipt.telemetry.application_attempt_count
        or (
            integrated
            and receipt.telemetry.coarse_kernel_launch_count != 4 * expected_count
        )
        or not 0 <= receipt.telemetry.external_parent_fence_ack_count <= 2
        or receipt.telemetry.externally_acknowledged_coarse_launch_count
        > receipt.telemetry.coarse_kernel_launch_count
        or any(
            getattr(receipt.telemetry, name) != 0
            for name in (
                "additional_h2d_copy_count",
                "additional_d2h_copy_count",
                "additional_allocation_count",
                "additional_synchronization_count",
                "additional_csr_apply_count",
                "host_terminal_branch_count",
                "fallback_count",
            )
        )
        or receipt.claims.exact_live_and_coarse_contexts_bound is not True
        or receipt.claims.fixed_schedule_coordinates_bound is not integrated
        or receipt.claims.same_stream_overlay_order_bound is not integrated
        or receipt.claims.coarse_output_consumed_by_recurrence is not integrated
        or receipt.claims.terminal_observation_bound is not terminal_bound
        or receipt.claims.application_window_host_copy_zero is not integrated
        or receipt.claims.no_additional_intermediate_synchronization is not integrated
        or receipt.claims.canonical_jacobi_row_retained is not True
        or receipt.claims.canonical_jacobi_row_replaced is not False
        or receipt.claims.coarse_device_status_directly_terminal_bound is not False
        or receipt.claims.full_iteration_host_copy_zero_proven is not False
        or receipt.claims.end_to_end_o_n_proven is not False
        or receipt.claims.speedup_proven is not False
        or receipt.claims.commercial_ready is not False
        or receipt.claims.promotion_eligible is not False
        or (integrated and len(applications) != expected_count)
        or (receipt.global_context_id != _ZERO_HASH) is not global_bound
        or (receipt.global_receipt_hash != _ZERO_HASH) is not global_bound
        or (not integrated and global_bound)
        or (receipt.terminal_observation_receipt_hash != _ZERO_HASH)
        is not terminal_hashes_bound
        or (receipt.terminal_outcome_hash != _ZERO_HASH) is not terminal_hashes_bound
        or (receipt.status == "terminal_bound" and not terminal_bound)
        or (
            receipt.status not in {"terminal_bound", "context_closed"}
            and terminal_hashes_bound
        )
    ):
        _fail("hip_fgmres_coarse_overlay_receipt_invalid", "/receipt")
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail("hip_fgmres_coarse_overlay_receipt_hash_invalid", "/receipt/hash")
    if expected_context is not None:
        if (
            type(expected_context) is not HipFgmresFixedRankCoarseRecurrenceOverlayV1
            or receipt.context_id != expected_context._context_id
            or receipt.bindings is not expected_context._bindings
            or receipt.dimensions is not expected_context._dimensions
        ):
            _fail("hip_fgmres_coarse_overlay_receipt_context_invalid", "/receipt")
        for source, application in zip(
            expected_context._application_receipts,
            applications,
            strict=True,
        ):
            validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
                source,
                expected_context=expected_context._require_coarse(),
            )
            if source.receipt_hash != application.coarse_application_receipt_hash:
                _fail(
                    "hip_fgmres_coarse_overlay_application_provenance_invalid",
                    "/applications",
                )
    return receipt


def _receipt_payload(
    receipt: HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "evidence_scope": receipt.evidence_scope,
        "actual_backend": receipt.actual_backend,
        "promotion_eligible": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "applications": [row.to_dict() for row in receipt.applications],
        "application_sequence_hash": receipt.application_sequence_hash,
        "global_context_id": receipt.global_context_id,
        "global_receipt_hash": receipt.global_receipt_hash,
        "terminal_observation_receipt_hash": (
            receipt.terminal_observation_receipt_hash
        ),
        "terminal_outcome_hash": receipt.terminal_outcome_hash,
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    raw = (
        resources.files("structural_analysis.schemas")
        .joinpath(_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(raw)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_hash(value: object) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _detail(value: object) -> str:
    text = str(value) if value is not None else ""
    return re.sub(r"(?i)0x[0-9a-f]+", "<redacted>", text)[:512]


def _fail(
    code: str,
    path: str,
    detail: str = "",
    *,
    cleanup_owner: HipFgmresFixedRankCoarseRecurrenceOverlayV1 | None = None,
) -> NoReturn:
    raise HipFgmresFixedRankCoarseRecurrenceOverlayV1Error(
        code,
        path,
        detail,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_CAPABILITY_PROFILE",
    "HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_EVIDENCE_SCOPE",
    "HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION",
    "HipFgmresFixedRankCoarseRecurrenceOverlayApplicationV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayBindingsV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayClaimsV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayDimensionsV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayOpenResultV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayReceiptV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayTelemetryV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayV1",
    "HipFgmresFixedRankCoarseRecurrenceOverlayV1Error",
    "open_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1",
    "validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1",
]
