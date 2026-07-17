"""Live typed fixed-rank coarse recurrence-row replacement v1.

This internal integration owner replaces each scheduled
``APPLY_JACOBI_INDEXED`` row with one recurrence-ledger reservation backed by
the four-launch typed coarse-slot module followed by one same-stream device
terminal guard.  The guard publishes coarse-status failures directly into the
frozen solve record without a host copy, host branch, or intermediate fence.
The canonical/global owners retain their original logical launch counts and
exact parent fences.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import threading
from typing import Any, Literal, NoReturn

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_fixed_rank_coarse_context_v1 import (
    HipFgmresFixedRankCoarseExecutionContextV1,
    validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1,
)
from .fgmres_fixed_rank_coarse_slot_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseSlotKernelV1,
    _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1,
    _compile_fixed_rank_coarse_slot_with_handoff_v1,
    compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1,
)
from .fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_CAPABILITY_PROFILE,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_EVIDENCE_SCOPE,
    HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1,
    HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1,
    HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1,
    HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1,
    HipFgmresFixedRankCoarseSlotRecurrencePhaseV1,
    HipFgmresFixedRankCoarseSlotRecurrenceReasonV1,
    HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1,
    HipFgmresFixedRankCoarseSlotRecurrenceStatusV1,
    HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1,
    _context_id_for,
    _receipt_payload,
    _ZERO_HASH,
    validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1,
)
from .fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
    _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1,
    _compile_terminal_guard_with_handoff_v1,
    compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1,
)
from .fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from .fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointExecutionContextV1,
    validate_hip_fgmres_live_checkpoint_context_receipt_v1,
)
from .fgmres_recurrence_plan_v2 import _VECTOR_MODE_CODES
from .fgmres_rtc_v2 import HipRtcFgmresV2Kernel


HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_V1_CAPABILITY_PROFILE = (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_CAPABILITY_PROFILE
)

SlotPhaseV1 = HipFgmresFixedRankCoarseSlotRecurrencePhaseV1
SlotRecurrenceStateV1 = HipFgmresFixedRankCoarseSlotRecurrenceStatusV1

_CONTEXT_MINT = object()


class HipFgmresFixedRankCoarseSlotRecurrenceV1Error(RuntimeError):
    """Stable integration failure retaining fence/cleanup authority."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str = "",
        *,
        launch_disposition: str | None = None,
        cleanup_owner: HipFgmresFixedRankCoarseSlotRecurrenceV1 | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = _detail(message or code)
        self.launch_disposition = launch_disposition
        self.cleanup_owner = cleanup_owner
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseSlotRecurrenceOpenResultV1:
    context: HipFgmresFixedRankCoarseSlotRecurrenceV1 | None
    context_id: str | None
    receipt: HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1 | None = None

    @property
    def ready(self) -> bool:
        return (
            self.context is not None
            and self.receipt is not None
            and self.receipt.status == "context_ready"
        )


class HipFgmresFixedRankCoarseSlotRecurrenceV1:
    """Exclusive bridge from one logical row to four slot kernels plus a guard."""

    def __init__(self, *, _mint: object | None = None) -> None:
        if _mint is not _CONTEXT_MINT:
            raise TypeError("typed coarse recurrence contexts are factory-issued only")
        self._lock = threading.RLock()
        self._token = object()
        self._live: HipFgmresLiveCheckpointExecutionContextV1 | None = None
        self._coarse: HipFgmresFixedRankCoarseExecutionContextV1 | None = None
        self._slot_kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None
        self._terminal_guard_kernel: (
            HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1 | None
        ) = None
        self._coordinates: tuple[tuple[int, int], ...] = ()
        self._schedule_epochs: tuple[int, ...] = ()
        self._applications: list[
            HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1
        ] = []
        self._telemetry = HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1()
        self._accepted_by_phase: dict[SlotPhaseV1, int] = {
            "canonical_prefix": 0,
            "global_suffix": 0,
        }
        self._acknowledged_by_phase: dict[SlotPhaseV1, int] = {
            "canonical_prefix": 0,
            "global_suffix": 0,
        }
        self._guard_accepted_by_phase: dict[SlotPhaseV1, int] = {
            "canonical_prefix": 0,
            "global_suffix": 0,
        }
        self._guard_acknowledged_by_phase: dict[SlotPhaseV1, int] = {
            "canonical_prefix": 0,
            "global_suffix": 0,
        }
        self._canonical_owner: object | None = None
        self._global_owner: object | None = None
        self._global_context_id = _ZERO_HASH
        self._global_receipt_hash = _ZERO_HASH
        self._bindings: HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1 | None = None
        self._dimensions: HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1 | None = (
            None
        )
        self._actual_backend: Literal["hip", "test_double"] = "test_double"
        self._context_id = _ZERO_HASH
        self._state: SlotRecurrenceStateV1 = "context_ready"
        self._reason: HipFgmresFixedRankCoarseSlotRecurrenceReasonV1 | None = None
        self._live_reserved = False
        self._coarse_reserved = False
        self._live_released = False
        self._coarse_released = False
        self._open_published = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def state(self) -> SlotRecurrenceStateV1:
        return self._state

    @property
    def context_id(self) -> str:
        return self._context_id

    def receipt(self) -> HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
        with self._lock:
            return validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                self._build_receipt(self._state),
                expected_context=self,
            )

    @property
    def applications(
        self,
    ) -> tuple[HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1, ...]:
        return tuple(self._applications)

    @property
    def telemetry(self) -> HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1:
        return self._telemetry

    @property
    def slot_kernel(self) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
        return self._require_slot_kernel()

    @property
    def terminal_guard_kernel(
        self,
    ) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
        return self._require_terminal_guard_kernel()

    def _enqueue_instead_of_jacobi(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
        *,
        phase: str,
        owner: object,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        logical_index: int,
        audit_descriptor_hash: str,
        expected_prior_pending_count: int | None,
    ) -> None:
        with self._lock:
            self._require_route(token, live)
            typed_phase, typed_owner = self._validate_phase_owner(phase, owner)
            index = len(self._applications)
            expected_phase: SlotPhaseV1 = (
                "canonical_prefix" if index == 0 else "global_suffix"
            )
            if (
                index >= len(self._coordinates)
                or typed_phase != expected_phase
                or self._coordinates[index] != (expected_restart, expected_column)
                or self._schedule_epochs[index] != expected_schedule_epoch
                or logical_index != expected_column
                or self._state
                not in {
                    "context_ready",
                    "canonical_fenced",
                    "global_slot_pending",
                }
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_coordinate_invalid",
                    f"/applications/{index}",
                    cleanup_owner=self,
                )
            if typed_phase == "canonical_prefix":
                if self._canonical_owner not in {None, typed_owner}:
                    _fail(
                        "hip_fgmres_coarse_slot_recurrence_owner_changed",
                        "/owners/canonical",
                        cleanup_owner=self,
                    )
                self._canonical_owner = typed_owner
                pending_bounds = (
                    typed_owner._telemetry.async_operation_accept_lower_bound,
                    typed_owner._telemetry.async_operation_accept_upper_bound,
                )
            else:
                if self._global_owner not in {None, typed_owner}:
                    _fail(
                        "hip_fgmres_coarse_slot_recurrence_owner_changed",
                        "/owners/global",
                        cleanup_owner=self,
                    )
                self._global_owner = typed_owner
                pending_bounds = (
                    typed_owner._telemetry.kernel_launch_accept_lower_bound,
                    typed_owner._telemetry.kernel_launch_accept_upper_bound,
                )
            if expected_prior_pending_count is not None and pending_bounds != (
                expected_prior_pending_count,
                expected_prior_pending_count,
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_pending_count_invalid",
                    f"/applications/{index}/pending",
                    cleanup_owner=self,
                )

            coarse = self._require_coarse()
            dimensions, pointers = coarse._typed_slot_pointer_arguments(
                self._token,
                self,
                pending_bounds,
            )
            recurrence = live._recurrence_plan
            recurrence_kernel = live._kernel
            if (
                recurrence is None
                or type(recurrence_kernel) is not HipRtcFgmresV2Kernel
                or live._stream_pointer_snapshot is None
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_live_invalid",
                    "/authority/live",
                    cleanup_owner=self,
                )
            try:
                control_state = live._owned_capabilities["fgmres_control_state_v2"].base
                solve_record = live._owned_capabilities["solve_record"].base
            except KeyError as exc:
                raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
                    "hip_fgmres_coarse_slot_recurrence_pointer_invalid",
                    "/authority/live/pointers",
                    type(exc).__name__,
                    cleanup_owner=self,
                ) from exc

            slot_kernel = self._require_slot_kernel()
            guard_kernel = self._require_terminal_guard_kernel()
            accepted_before = slot_kernel.lifetime_accepted_launch_count
            guard_accepted_before = guard_kernel.lifetime_accepted_launch_count
            self._telemetry = replace(
                self._telemetry,
                application_attempt_count=(
                    self._telemetry.application_attempt_count + 1
                ),
            )
            try:
                recurrence_kernel._launch_fixed_rank_coarse_slot_v1(
                    slot_kernel,
                    guard_kernel,
                    stream=live._stream_pointer_snapshot,
                    expected_schedule_epoch=expected_schedule_epoch,
                    expected_restart=expected_restart,
                    expected_column=expected_column,
                    maximum_restart_count=recurrence.maximum_restart_count,
                    free_dof_count=dimensions.free_dof_count,
                    retained_rank=dimensions.retained_rank,
                    restart_dimension=dimensions.restart_dimension,
                    logical_index=logical_index,
                    jacobi_inverse=pointers["jacobi_inverse"],
                    basis_v=pointers["basis_v"],
                    preconditioned_basis_z=pointers["preconditioned_basis_z"],
                    coarse_physical_basis_z=pointers["coarse_physical_basis_z"],
                    coarse_operator_basis_az=pointers["coarse_operator_basis_az"],
                    coarse_cholesky_l=pointers["coarse_cholesky_l"],
                    coarse_rhs=pointers["coarse_rhs"],
                    coarse_coefficients=pointers["coarse_coefficients"],
                    coarse_status=pointers["coarse_status"],
                    control_state=control_state,
                    solve_record=solve_record,
                    checkpoint_owner_token=live._checkpoint_token,
                    checkpoint_expected_prior_pending_count=(
                        expected_prior_pending_count
                    ),
                    checkpoint_audit_descriptor_hash=audit_descriptor_hash,
                )
            except BaseException as exc:
                accepted_delta = max(
                    0,
                    slot_kernel.lifetime_accepted_launch_count - accepted_before,
                )
                guard_accepted_delta = max(
                    0,
                    guard_kernel.lifetime_accepted_launch_count - guard_accepted_before,
                )
                self._accepted_by_phase[typed_phase] += accepted_delta
                self._guard_accepted_by_phase[typed_phase] += guard_accepted_delta
                self._telemetry = replace(
                    self._telemetry,
                    physical_slot_launch_accept_count=(
                        self._telemetry.physical_slot_launch_accept_count
                        + accepted_delta
                    ),
                    physical_terminal_guard_launch_accept_count=(
                        self._telemetry.physical_terminal_guard_launch_accept_count
                        + guard_accepted_delta
                    ),
                )
                self._poison(exc)
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
                    "hip_fgmres_coarse_slot_recurrence_enqueue_failed",
                    f"/applications/{index}",
                    _detail(exc),
                    launch_disposition=getattr(exc, "launch_disposition", None),
                    cleanup_owner=self,
                ) from exc
            accepted_delta = (
                slot_kernel.lifetime_accepted_launch_count - accepted_before
            )
            guard_accepted_delta = (
                guard_kernel.lifetime_accepted_launch_count - guard_accepted_before
            )
            if accepted_delta != 4 or guard_accepted_delta != 1:
                self._accepted_by_phase[typed_phase] += max(0, accepted_delta)
                self._guard_accepted_by_phase[typed_phase] += max(
                    0, guard_accepted_delta
                )
                self._poison(
                    "accepted physical launch delta was not four slot plus one guard"
                )
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_launch_count_invalid",
                    f"/applications/{index}",
                    cleanup_owner=self,
                )
            self._accepted_by_phase[typed_phase] += 4
            self._guard_accepted_by_phase[typed_phase] += 1
            self._applications.append(
                HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1(
                    sequence=index + 1,
                    phase=typed_phase,
                    schedule_epoch=expected_schedule_epoch,
                    restart_index=expected_restart,
                    column_index=expected_column,
                    logical_index=logical_index,
                    recurrence_descriptor_hash=audit_descriptor_hash,
                )
            )
            self._telemetry = replace(
                self._telemetry,
                application_success_count=(
                    self._telemetry.application_success_count + 1
                ),
                logical_recurrence_launch_count=(
                    self._telemetry.logical_recurrence_launch_count + 1
                ),
                physical_slot_launch_accept_count=(
                    self._telemetry.physical_slot_launch_accept_count + 4
                ),
                physical_terminal_guard_launch_accept_count=(
                    self._telemetry.physical_terminal_guard_launch_accept_count + 1
                ),
                canonical_application_count=(
                    self._telemetry.canonical_application_count
                    + (typed_phase == "canonical_prefix")
                ),
                global_application_count=(
                    self._telemetry.global_application_count
                    + (typed_phase == "global_suffix")
                ),
            )
            self._state = (
                "canonical_slot_pending"
                if typed_phase == "canonical_prefix"
                else "global_slot_pending"
            )

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
            expected_owner = (
                self._canonical_owner
                if typed_phase == "canonical_prefix"
                else self._global_owner
            )
            slot_kernel = self._require_slot_kernel()
            guard_kernel = self._require_terminal_guard_kernel()
            if (
                expected_owner is None
                and self._accepted_by_phase[typed_phase] == 0
                and self._guard_accepted_by_phase[typed_phase] == 0
                and not slot_kernel.pending
                and not guard_kernel.pending
            ):
                return 0
            if typed_owner is not expected_owner:
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_owner_changed",
                    f"/fences/{typed_phase}",
                    cleanup_owner=self,
                )
            expected_slot = (
                self._accepted_by_phase[typed_phase]
                - self._acknowledged_by_phase[typed_phase]
            )
            pending_before = slot_kernel.pending_accepted_launch_count
            try:
                acknowledged_slot = slot_kernel.acknowledge_stream_fence(
                    live._stream_pointer_snapshot
                )
            except BaseException as exc:
                if slot_kernel.pending:
                    self._poison(exc)
                    raise
                acknowledged_slot = pending_before
            if acknowledged_slot != expected_slot:
                self._poison(
                    "expected slot fence count "
                    f"{expected_slot}, got {acknowledged_slot}"
                )
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_fence_count_invalid",
                    f"/fences/{typed_phase}",
                    cleanup_owner=self,
                )
            self._acknowledged_by_phase[typed_phase] += acknowledged_slot
            self._telemetry = replace(
                self._telemetry,
                physical_slot_launch_ack_count=(
                    self._telemetry.physical_slot_launch_ack_count + acknowledged_slot
                ),
            )

            expected_guard = (
                self._guard_accepted_by_phase[typed_phase]
                - self._guard_acknowledged_by_phase[typed_phase]
            )
            guard_pending_before = guard_kernel.pending_accepted_launch_count
            try:
                acknowledged_guard = guard_kernel.acknowledge_stream_fence(
                    live._stream_pointer_snapshot
                )
            except BaseException as exc:
                if guard_kernel.pending:
                    self._poison(exc)
                    raise
                acknowledged_guard = guard_pending_before
            if acknowledged_guard != expected_guard:
                self._poison(
                    "expected terminal-guard fence count "
                    f"{expected_guard}, got {acknowledged_guard}"
                )
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_fence_count_invalid",
                    f"/fences/{typed_phase}/terminal_guard",
                    cleanup_owner=self,
                )
            self._guard_acknowledged_by_phase[typed_phase] += acknowledged_guard
            self._telemetry = replace(
                self._telemetry,
                parent_fence_ack_count=self._telemetry.parent_fence_ack_count + 1,
                physical_terminal_guard_launch_ack_count=(
                    self._telemetry.physical_terminal_guard_launch_ack_count
                    + acknowledged_guard
                ),
            )
            if self._state != "poisoned":
                self._state = (
                    "canonical_fenced"
                    if typed_phase == "canonical_prefix"
                    else "global_fenced"
                )
            return acknowledged_slot + acknowledged_guard

    def _bind_global_recurrence_receipt(
        self,
        token: object,
        live: HipFgmresLiveCheckpointExecutionContextV1,
        *,
        owner: object,
        receipt: object,
    ) -> None:
        with self._lock:
            self._require_route(token, live)
            typed_phase, typed_owner = self._validate_phase_owner(
                "global_suffix",
                owner,
            )
            if (
                typed_phase != "global_suffix"
                or typed_owner is not self._global_owner
                or self._state != "global_fenced"
                or len(self._applications) != len(self._coordinates)
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_global_publication_invalid",
                    "/global_receipt",
                    cleanup_owner=self,
                )
            from .fgmres_global_recurrence_context_v1 import (
                validate_hip_fgmres_global_recurrence_receipt_v1,
            )

            validated = validate_hip_fgmres_global_recurrence_receipt_v1(
                receipt,  # type: ignore[arg-type]
            )
            if validated.status != "recurrence_fenced":
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_global_publication_invalid",
                    "/global_receipt/status",
                    cleanup_owner=self,
                )
            self._global_context_id = validated.context_id
            self._global_receipt_hash = validated.receipt_hash
            self._state = "global_receipt_bound"
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                self._build_receipt("global_receipt_bound"),
                expected_context=self,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if not self._open_published:
                self._close_failed_open()
                return
            slot_kernel = self._require_slot_kernel()
            guard_kernel = self._require_terminal_guard_kernel()
            unacknowledged_slot = sum(self._accepted_by_phase.values()) - sum(
                self._acknowledged_by_phase.values()
            )
            unacknowledged_guard = sum(self._guard_accepted_by_phase.values()) - sum(
                self._guard_acknowledged_by_phase.values()
            )
            if (
                slot_kernel.pending
                or guard_kernel.pending
                or unacknowledged_slot != 0
                or unacknowledged_guard != 0
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_parent_fence_required",
                    "/cleanup/fence",
                    cleanup_owner=self,
                )
            if any(
                self._accepted_by_phase[phase] != self._acknowledged_by_phase[phase]
                or self._guard_accepted_by_phase[phase]
                != self._guard_acknowledged_by_phase[phase]
                for phase in ("canonical_prefix", "global_suffix")
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_parent_fence_required",
                    "/cleanup/parent_fence",
                    cleanup_owner=self,
                )
            if (
                self._state != "poisoned"
                and self._applications
                and (
                    len(self._applications) != len(self._coordinates)
                    or self._global_receipt_hash == _ZERO_HASH
                )
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_incomplete",
                    "/cleanup",
                    cleanup_owner=self,
                )
            try:
                if not guard_kernel.closed:
                    guard_kernel.close()
                if not slot_kernel.closed:
                    slot_kernel.close()
                if self._live_reserved and not self._live_released:
                    self._require_live()._release_fixed_rank_coarse_slot(
                        self._token,
                        self,
                    )
                    self._live_released = True
                if self._coarse_reserved and not self._coarse_released:
                    self._require_coarse()._release_recurrence_overlay_child(
                        self._token,
                        self,
                    )
                    self._coarse_released = True
            except BaseException as exc:
                self._state = "cleanup_failed"
                self._reason = HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
                    "hip_fgmres_coarse_slot_recurrence_cleanup_failed",
                    _detail(exc),
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
                    "hip_fgmres_coarse_slot_recurrence_cleanup_failed",
                    "/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"

    def _close_failed_open(self) -> None:
        """Retry partial factory cleanup without releasing parent authority early."""

        with self._lock:
            if self._closed:
                return
            try:
                for kernel in (
                    self._terminal_guard_kernel,
                    self._slot_kernel,
                ):
                    if kernel is None or kernel.closed:
                        continue
                    if kernel.pending:
                        _fail(
                            "hip_fgmres_coarse_slot_recurrence_parent_fence_required",
                            "/open/cleanup/fence",
                            cleanup_owner=self,
                        )
                    kernel.close()
                if self._live_reserved and not self._live_released:
                    self._require_live()._release_fixed_rank_coarse_slot(
                        self._token,
                        self,
                    )
                    self._live_released = True
                if self._coarse_reserved and not self._coarse_released:
                    self._require_coarse()._release_recurrence_overlay_child(
                        self._token,
                        self,
                    )
                    self._coarse_released = True
            except BaseException as exc:
                self._state = "cleanup_failed"
                self._reason = HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
                    "hip_fgmres_coarse_slot_recurrence_cleanup_failed",
                    _detail(exc),
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
                    "hip_fgmres_coarse_slot_recurrence_cleanup_failed",
                    "/open/cleanup",
                    self._reason.detail,
                    cleanup_owner=self,
                ) from exc
            self._closed = True
            self._state = "context_closed"

    def _validate_phase_owner(
        self,
        phase: str,
        owner: object,
    ) -> tuple[SlotPhaseV1, Any]:
        from .fgmres_canonical_predecessor_v1 import (
            HipFgmresCanonicalPredecessorExecutionContextV1,
        )
        from .fgmres_global_recurrence_context_v1 import (
            HipFgmresGlobalRecurrenceExecutionContextV1,
        )

        if phase == "canonical_prefix" and type(owner) is (
            HipFgmresCanonicalPredecessorExecutionContextV1
        ):
            return phase, owner
        if phase == "global_suffix" and type(owner) is (
            HipFgmresGlobalRecurrenceExecutionContextV1
        ):
            return phase, owner
        _fail(
            "hip_fgmres_coarse_slot_recurrence_owner_invalid",
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
                "hip_fgmres_coarse_slot_recurrence_route_invalid",
                "/lifetime",
                cleanup_owner=self,
            )
        live._require_fixed_rank_coarse_slot(self._token, self)
        self._require_coarse()._require_recurrence_overlay_child(self._token, self)

    def _poison(self, error: object) -> None:
        self._state = "poisoned"
        self._reason = HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
            "hip_fgmres_coarse_slot_recurrence_poisoned",
            _detail(error),
        )
        coarse = self._coarse
        if coarse is not None:
            try:
                coarse._poison("hip_fgmres_coarse_slot_recurrence_poisoned")
            except BaseException:
                pass

    def _build_receipt(
        self,
        status: SlotRecurrenceStateV1,
    ) -> HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
        bindings = self._bindings
        dimensions = self._dimensions
        if bindings is None or dimensions is None:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_receipt_unavailable",
                "/receipt",
                cleanup_owner=self,
            )
        applications = tuple(self._applications)
        expected_count = dimensions.expected_application_count
        telemetry = self._telemetry
        all_rows_fenced = (
            len(applications) == expected_count
            and telemetry.application_attempt_count == expected_count
            and telemetry.application_success_count == expected_count
            and telemetry.physical_slot_launch_accept_count == 4 * expected_count
            and telemetry.physical_terminal_guard_launch_accept_count == expected_count
            and telemetry.physical_slot_launch_ack_count == 4 * expected_count
            and telemetry.physical_terminal_guard_launch_ack_count == expected_count
            and telemetry.parent_fence_ack_count == 2
        )
        global_bound = (
            self._global_context_id != _ZERO_HASH
            and self._global_receipt_hash != _ZERO_HASH
        )
        claims = HipFgmresFixedRankCoarseSlotRecurrenceClaimsV1(
            exact_live_and_coarse_contexts_bound=True,
            exact_slot_and_terminal_guard_kernel_identities_bound=True,
            immutable_schedule_hashes_bound=True,
            global_recurrence_receipt_bound=global_bound,
            all_scheduled_jacobi_rows_replaced=all_rows_fenced,
            one_logical_row_per_five_physical_launches=all_rows_fenced,
            same_stream_slot_then_terminal_guard_order_bound=all_rows_fenced,
            both_physical_owners_parent_fenced=all_rows_fenced,
            device_terminal_status_binding_contract=all_rows_fenced,
            application_window_host_copy_zero_contract=all_rows_fenced,
            no_additional_intermediate_synchronization_contract=all_rows_fenced,
            legacy_jacobi_launch_zero_observed=all_rows_fenced,
        )
        draft = HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1(
            status=status,
            context_id=self._context_id,
            evidence_scope=(
                HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_EVIDENCE_SCOPE
            ),
            actual_backend=self._actual_backend,
            promotion_eligible=False,
            reason=self._reason,
            bindings=bindings,
            dimensions=dimensions,
            applications=applications,
            application_sequence_hash=canonical_hash(
                [row.to_dict() for row in applications]
            ),
            global_context_id=self._global_context_id,
            global_receipt_hash=self._global_receipt_hash,
            telemetry=telemetry,
            claims=claims,
            receipt_hash=_ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
        )

    def _require_live(self) -> HipFgmresLiveCheckpointExecutionContextV1:
        if type(self._live) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_live_invalid",
                "/lifetime/live",
                cleanup_owner=self,
            )
        return self._live

    def _require_coarse(self) -> HipFgmresFixedRankCoarseExecutionContextV1:
        if type(self._coarse) is not HipFgmresFixedRankCoarseExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_coarse_invalid",
                "/lifetime/coarse",
                cleanup_owner=self,
            )
        return self._coarse

    def _require_slot_kernel(self) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
        if type(self._slot_kernel) is not HipRtcFgmresFixedRankCoarseSlotKernelV1:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_kernel_invalid",
                "/lifetime/kernel",
                cleanup_owner=self,
            )
        return self._slot_kernel

    def _require_terminal_guard_kernel(
        self,
    ) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
        if type(self._terminal_guard_kernel) is not (
            HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1
        ):
            _fail(
                "hip_fgmres_coarse_slot_recurrence_terminal_guard_invalid",
                "/lifetime/terminal_guard",
                cleanup_owner=self,
            )
        return self._terminal_guard_kernel


def open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1(
    coarse_context: HipFgmresFixedRankCoarseExecutionContextV1,
    *,
    hiprtc_library: str | None = None,
    rtc_kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None,
    terminal_guard_kernel: (
        HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1 | None
    ) = None,
) -> HipFgmresFixedRankCoarseSlotRecurrenceOpenResultV1:
    """Reserve the exact route and adopt slot plus device-guard owners."""

    context = HipFgmresFixedRankCoarseSlotRecurrenceV1(_mint=_CONTEXT_MINT)
    slot_handoff = _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1()
    guard_handoff = _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1()
    slot_candidate: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None
    guard_candidate: HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1 | None = None
    slot_compiled_here = False
    guard_compiled_here = False
    owners_adopted = False
    try:
        if type(coarse_context) is not HipFgmresFixedRankCoarseExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_context_invalid",
                "/coarse_context",
            )
        coarse_receipt = validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
            coarse_context.receipt(),
            expected_context=coarse_context,
        )
        if (
            coarse_receipt.status != "context_ready"
            or coarse_context._sequence != 0
            or coarse_context._recurrence_overlay_child_token is not None
            or coarse_context._kernel is None
            or coarse_context._kernel.pending
        ):
            _fail(
                "hip_fgmres_coarse_slot_recurrence_pristine_context_required",
                "/coarse_context",
            )
        live = coarse_context._parent
        if type(live) is not HipFgmresLiveCheckpointExecutionContextV1:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_live_invalid",
                "/live_context",
            )
        live_receipt = validate_hip_fgmres_live_checkpoint_context_receipt_v1(
            live.receipt(),
            expected_context=live,
        )
        recurrence = live._recurrence_plan
        if (
            live_receipt.status != "context_ready"
            or recurrence is None
            or live._loaded_runtime is None
            or live._architecture is None
        ):
            _fail(
                "hip_fgmres_coarse_slot_recurrence_live_invalid",
                "/live_context",
            )
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
        schedule_epochs = tuple(int(row.expected_schedule_epoch) for row in rows)
        if not coordinates:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_schedule_invalid",
                "/schedule",
            )

        # Store both exact parents before the first lease is acquired.  If the
        # second reservation fails, open cleanup must still be able to return
        # the already-acquired coarse-child lease.
        context._live = live
        context._coarse = coarse_context
        coarse_context._reserve_recurrence_overlay_child(context._token, context)
        context._coarse_reserved = True
        live._reserve_fixed_rank_coarse_slot(
            context._token,
            context,
            coarse_context,
        )
        context._live_reserved = True
        context._coordinates = coordinates
        context._schedule_epochs = schedule_epochs

        if rtc_kernel is None:
            slot_candidate = _compile_fixed_rank_coarse_slot_with_handoff_v1(
                compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1,
                slot_handoff,
                live._loaded_runtime,
                live._architecture,
                hiprtc_library,
            )
            slot_compiled_here = True
        else:
            if (
                type(rtc_kernel) is not HipRtcFgmresFixedRankCoarseSlotKernelV1
                or rtc_kernel.closed
                or rtc_kernel.pending
                or rtc_kernel.unload_disposition != "live"
                or rtc_kernel.identity.architecture != live._architecture
                or rtc_kernel._runtime._runtime is not live._loaded_runtime
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_kernel_invalid",
                    "/rtc_kernel",
                )
            slot_candidate = rtc_kernel

        if terminal_guard_kernel is None:
            guard_candidate = _compile_terminal_guard_with_handoff_v1(
                compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1,
                guard_handoff,
                live._loaded_runtime,
                live._architecture,
                hiprtc_library,
            )
            guard_compiled_here = True
        else:
            if (
                type(terminal_guard_kernel)
                is not HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1
                or terminal_guard_kernel.closed
                or terminal_guard_kernel.pending
                or terminal_guard_kernel.unload_disposition != "live"
                or terminal_guard_kernel.identity.architecture != live._architecture
                or terminal_guard_kernel._runtime._runtime is not live._loaded_runtime
            ):
                _fail(
                    "hip_fgmres_coarse_slot_recurrence_terminal_guard_invalid",
                    "/terminal_guard_kernel",
                )
            guard_candidate = terminal_guard_kernel

        if (
            type(slot_candidate) is not HipRtcFgmresFixedRankCoarseSlotKernelV1
            or type(guard_candidate)
            is not HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1
        ):
            _fail(
                "hip_fgmres_coarse_slot_recurrence_kernel_invalid",
                "/owners",
            )
        context._slot_kernel = slot_candidate
        context._terminal_guard_kernel = guard_candidate
        owners_adopted = True
        if live_receipt.kernel is None or coarse_receipt.actual_backend not in {
            "hip",
            "test_double",
        }:
            _fail(
                "hip_fgmres_coarse_slot_recurrence_receipt_binding_invalid",
                "/receipt/bindings",
            )
        slot_identity = slot_candidate.identity
        guard_identity = guard_candidate.identity
        context._actual_backend = coarse_receipt.actual_backend
        context._bindings = HipFgmresFixedRankCoarseSlotRecurrenceBindingsV1(
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
            slot_kernel_identity_hash=slot_identity.identity_hash,
            slot_kernel_abi_hash=slot_identity.kernel_abi_hash,
            slot_combined_source_sha256=slot_identity.combined_source_sha256,
            terminal_guard_identity_hash=guard_identity.identity_hash,
            terminal_guard_abi_hash=guard_identity.kernel_abi_hash,
            terminal_guard_combined_source_sha256=(
                guard_identity.combined_source_sha256
            ),
            full_schedule_hash=partition.full.canonical_sha256,
            sealed_prefix_schedule_hash=partition.sealed_prefix.canonical_sha256,
            continuation_schedule_hash=partition.continuation.canonical_sha256,
            schedule_coordinates_hash=canonical_hash(
                [list(row) for row in coordinates]
            ),
            schedule_epochs_hash=canonical_hash(list(schedule_epochs)),
        )
        context._dimensions = HipFgmresFixedRankCoarseSlotRecurrenceDimensionsV1(
            free_dof_count=recurrence.free_dof_count,
            restart_dimension=recurrence.restart_dimension,
            max_iterations=recurrence.max_iterations,
            maximum_restart_count=recurrence.maximum_restart_count,
            retained_rank=coarse_receipt.dimensions.retained_rank,
            expected_application_count=len(coordinates),
            global_suffix_application_count=len(coordinates) - 1,
        )
        context._context_id = _context_id_for(
            context._bindings,
            context._dimensions,
            context._actual_backend,
        )
        opening_receipt = context._build_receipt("context_ready")
        validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
            opening_receipt,
            expected_context=context,
        )
        context._open_published = True
        return HipFgmresFixedRankCoarseSlotRecurrenceOpenResultV1(
            context,
            context._context_id,
            opening_receipt,
        )
    except BaseException as primary:
        if not owners_adopted:
            if slot_compiled_here or slot_handoff.kernel is not None:
                context._slot_kernel = slot_candidate or slot_handoff.kernel
            if guard_compiled_here or guard_handoff.kernel is not None:
                context._terminal_guard_kernel = guard_candidate or guard_handoff.kernel
        try:
            context._close_failed_open()
        except BaseException as cleanup:
            if not isinstance(cleanup, Exception):
                raise
            raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
                "hip_fgmres_coarse_slot_recurrence_open_cleanup_failed",
                "/open/cleanup",
                f"primary={type(primary).__name__}; cleanup={type(cleanup).__name__}",
                cleanup_owner=context,
            ) from cleanup
        if isinstance(primary, HipFgmresFixedRankCoarseSlotRecurrenceV1Error):
            raise
        if not isinstance(primary, Exception):
            raise
        raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
            "hip_fgmres_coarse_slot_recurrence_open_failed",
            "/open",
            _detail(primary),
            cleanup_owner=context,
        ) from primary


def _detail(value: object) -> str:
    text = str(value).strip().replace("\n", " ")
    redacted = re.sub(r"(?i)0x[0-9a-f]+", "<redacted>", text)
    return (redacted or type(value).__name__)[:320]


def _fail(
    code: str,
    path: str,
    message: str = "",
    *,
    cleanup_owner: HipFgmresFixedRankCoarseSlotRecurrenceV1 | None = None,
) -> NoReturn:
    raise HipFgmresFixedRankCoarseSlotRecurrenceV1Error(
        code,
        path,
        message,
        cleanup_owner=cleanup_owner,
    )


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_V1_CAPABILITY_PROFILE",
    "HipFgmresFixedRankCoarseSlotRecurrenceApplicationV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceOpenResultV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceTelemetryV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceV1",
    "HipFgmresFixedRankCoarseSlotRecurrenceV1Error",
    "open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1",
]
