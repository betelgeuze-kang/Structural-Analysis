from __future__ import annotations

# ruff: noqa: E402

from pathlib import Path
import sys
import threading
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_slot_recurrence_v1 as recurrence_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_recurrence_v1 import (
    HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
    open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1 import (
    HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
    validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1,
)

from tests.test_engine_v2_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1 import (
    _close_slot_stack,
    _guard_kernel,
    _open_slot_stack,
    _slot_kernel,
)


def test_live_route_releases_its_queue_lock_before_slot_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch)
    context = stack["slot"].context
    live = stack["live"].context
    canonical = stack["canonical"].context
    assert context is not None
    assert live is not None
    callback_observations: list[bool] = []
    validation_started = threading.Event()
    validation_finished = threading.Event()
    validation_errors: list[BaseException] = []

    def validate_opening_receipt() -> None:
        validation_started.set()
        try:
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                stack["slot"].receipt,
                expected_context=context,
            )
        except BaseException as exc:
            validation_errors.append(exc)
        finally:
            validation_finished.set()

    with context._lock:
        validator = threading.Thread(target=validate_opening_receipt)
        validator.start()
        assert validation_started.wait(timeout=2.0)
        assert not validation_finished.wait(timeout=2.0)
    validator.join(timeout=2.0)
    assert not validator.is_alive()
    assert validation_finished.is_set()
    assert validation_errors == []

    def observe_callback(
        _context: Any,
        _token: object,
        routed_live: Any,
        **_keywords: Any,
    ) -> None:
        def probe_queue_lock() -> None:
            acquired = routed_live._queue_lock.acquire(blocking=False)
            callback_observations.append(acquired)
            if acquired:
                routed_live._queue_lock.release()

        probe = threading.Thread(target=probe_queue_lock)
        probe.start()
        probe.join(timeout=2.0)
        assert not probe.is_alive()

    monkeypatch.setattr(type(context), "_enqueue_instead_of_jacobi", observe_callback)
    try:
        assert live._enqueue_fixed_rank_coarse_slot_instead_of_jacobi(
            phase="canonical_prefix",
            owner=canonical,
            expected_schedule_epoch=context._schedule_epochs[0],
            expected_restart=context._coordinates[0][0],
            expected_column=context._coordinates[0][1],
            logical_index=context._coordinates[0][1],
            audit_descriptor_hash="sha256:" + "1" * 64,
            expected_prior_pending_count=None,
        )
        assert callback_observations == [True]
    finally:
        _close_slot_stack(stack)


def test_open_failure_returns_the_already_reserved_coarse_child_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch, open_slot=False)
    live = stack["live"].context
    coarse = stack["coarse"].context
    assert live is not None
    assert coarse is not None
    kernel, _ = _slot_kernel(monkeypatch, stack["loaded"])

    def reject_live_route(
        _self: Any,
        _token: object,
        _slot_context: object,
        _coarse_context: object,
    ) -> object:
        raise RuntimeError("injected live-route reservation failure")

    monkeypatch.setattr(
        type(live),
        "_reserve_fixed_rank_coarse_slot",
        reject_live_route,
    )
    try:
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
            match="open_failed",
        ):
            open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1(
                coarse,
                rtc_kernel=kernel,
            )
        assert coarse._recurrence_overlay_child_token is None
        assert coarse._recurrence_overlay_child_context is None
        assert not kernel.closed
    finally:
        if not kernel.closed:
            kernel.close()
        _close_slot_stack(stack)


def test_failed_open_unload_retry_retains_both_parent_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch, open_slot=False)
    live = stack["live"].context
    coarse = stack["coarse"].context
    assert live is not None
    assert coarse is not None
    slot_kernel, _ = _slot_kernel(monkeypatch, stack["loaded"])
    guard_kernel, guard_runtime = _guard_kernel(monkeypatch, stack["loaded"])
    unload_statuses = [7, 0]

    def unload_guard(_module: Any) -> int:
        guard_runtime.unloads += 1
        return unload_statuses.pop(0)

    monkeypatch.setattr(guard_runtime, "unload", unload_guard)

    def fail_context_hash(_payload: Any) -> str:
        raise RuntimeError("injected context hash failure")

    monkeypatch.setattr(recurrence_module, "canonical_hash", fail_context_hash)
    try:
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
            match="open_cleanup_failed",
        ) as failed:
            open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1(
                coarse,
                rtc_kernel=slot_kernel,
                terminal_guard_kernel=guard_kernel,
            )
        cleanup_owner = failed.value.cleanup_owner
        assert cleanup_owner is not None
        assert live._fixed_rank_coarse_slot_context is cleanup_owner
        assert coarse._recurrence_overlay_child_context is cleanup_owner
        assert not slot_kernel.closed
        assert not guard_kernel.closed

        cleanup_owner.close()
        assert cleanup_owner.closed
        assert slot_kernel.closed
        assert guard_kernel.closed
        assert live._fixed_rank_coarse_slot_context is None
        assert coarse._recurrence_overlay_child_context is None
        assert guard_runtime.unloads == 2
    finally:
        _close_slot_stack(stack)


def test_poisoned_close_still_requires_the_parent_fence_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch)
    context = stack["slot"].context
    canonical = stack["canonical"].context
    live = stack["live"].context
    assert context is not None
    assert live is not None
    pending = canonical.enqueue_canonical_predecessor()
    try:
        assert (
            context.slot_kernel.acknowledge_stream_fence(live._stream_pointer_snapshot)
            == 4
        )
        assert (
            context.terminal_guard_kernel.acknowledge_stream_fence(
                live._stream_pointer_snapshot
            )
            == 1
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="context_invalid",
        ):
            context.receipt()
        context._state = "poisoned"
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
            match="parent_fence_required",
        ):
            context.close()

        # The synthetic direct kernel acknowledgement above cannot stand in
        # for the recurrence parent's fence.  Restore only the test ledger so
        # the real parent fence can complete and the stack can be released.
        context._acknowledged_by_phase["canonical_prefix"] = 4
        context._guard_acknowledged_by_phase["canonical_prefix"] = 1
        canonical.synchronize_canonical_predecessor(pending)
    finally:
        _close_slot_stack(stack)
