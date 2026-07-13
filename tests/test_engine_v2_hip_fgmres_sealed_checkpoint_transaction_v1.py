from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2 import (
    HipFgmresSealedCheckpointContinuationCapabilityV1,
    HipFgmresSealedCheckpointTransactionPendingV1,
    HipFgmresSealedCheckpointTransactionV1Error,
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
    validate_hip_fgmres_canonical_predecessor_capability_v1,
    validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1,
    validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (
    first_column_checkpoint_transaction_launches_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    _PHYSICAL_ROLES,
    _binding_values,
    _mint_global_recurrence_child_lease_v1,
    _receipt_payload,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_canonical_predecessor_v1 import (
    _close as _close_canonical,
    _open as _open_canonical,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/hip_fgmres_sealed_checkpoint_transaction_v1.schema.json"
)


def _open_predecessor(monkeypatch: pytest.MonkeyPatch) -> tuple[tuple[Any, ...], Any]:
    values = _open_canonical(monkeypatch)
    canonical = values[-1]
    pending = canonical.context.enqueue_canonical_predecessor()
    capability = canonical.context.synchronize_canonical_predecessor(pending)
    return values, capability


def _open_sealed(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[tuple[Any, ...], Any, Any, int]:
    values, capability = _open_predecessor(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    baseline = len(loaded.launch_records)
    opened = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
        values[-1].context,
        capability,
    )
    return values, capability, opened, baseline


def _close(values: tuple[Any, ...], sealed: Any | None = None) -> None:
    if sealed is not None and not sealed.context.closed:
        sealed.context.close()
    _close_canonical(values)


def _register_global_recurrence_recovery(context: Any, token: object) -> Any:
    """Mirror the production capture/register sequence before consume."""

    authority = context._global_recurrence_child_authority(
        token,
        continuation_consumed=False,
    )
    partition = compile_hip_fgmres_global_sealed_continuation_v1(
        authority.free_dof_count,
        authority.restart_dimension,
        authority.max_iterations,
    )
    context._register_global_recurrence_recovery_cell(
        token,
        kernel=authority.kernel,
        checkpoint_owner_token=authority.checkpoint_owner_token,
        stream_pointer=authority.stream_pointer,
        launch_limit=partition.continuation.launch_count,
    )
    return authority


def test_sealed_checkpoint_transaction_is_exact_nonowning_four_row_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, predecessor, opened, baseline = _open_sealed(monkeypatch)
    *_, kernel, live, canonical = values
    context = opened.context
    assert live.context is not None
    try:
        assert opened.ready
        opening = opened.receipt
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            opening,
            expected_context=context,
        )
        assert opening.status == "context_ready"
        assert opening.projection.additional_allocation_count == 0
        assert opening.projection.additional_borrow_count == 0
        assert opening.projection.additional_checkpoint_owner_count == 0
        assert opening.projection.additional_module_load_count == 0
        assert opening.claims.canonical_predecessor_capability_reserved
        assert not opening.claims.canonical_predecessor_capability_consumed
        assert not opening.claims.fixed_four_row_transaction_fenced
        assert not opening.claims.actual_mask_host_observed

        pending = context.enqueue_sealed_checkpoint_transaction()
        assert type(pending) is HipFgmresSealedCheckpointTransactionPendingV1
        assert pending.attempted_launch_count == 4
        assert pending.accepted_launch_count_lower_bound == 4
        assert pending.accepted_launch_count_upper_bound == 4
        snapshot = kernel._checkpoint_pending_snapshot(live.context._checkpoint_token)
        assert snapshot == ((live.context._stream_pointer_snapshot, 4),)
        rows = first_column_checkpoint_transaction_launches_v2(
            opening.dimensions.free_dof_count,
            opening.dimensions.restart_dimension,
        )
        loaded = kernel._runtime._runtime
        suffix = loaded.launch_records[baseline:]
        assert len(suffix) == 4
        assert [record["symbol"] for record in suffix] == [
            row.kernel_symbol for row in rows
        ]

        continuation = context.synchronize_sealed_checkpoint_transaction(pending)
        assert type(continuation) is HipFgmresSealedCheckpointContinuationCapabilityV1
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )
        assert kernel._checkpoint_pending_snapshot(live.context._checkpoint_token) == ()
        receipt = context.receipt()
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.status == "transaction_fenced"
        assert receipt.telemetry.predecessor_capability_consume_count == 1
        assert receipt.telemetry.kernel_launch_attempt_count == 4
        assert receipt.telemetry.kernel_launch_accept_lower_bound == 4
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 4
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        assert receipt.telemetry.consumed_launch_count == 4
        assert receipt.telemetry.allocation_count == 0
        assert receipt.telemetry.allocation_borrow_count == 0
        assert receipt.telemetry.module_load_count == 0
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.d2h_operation_count == 0
        assert receipt.telemetry.intermediate_sync_count == 0
        assert receipt.telemetry.fallback_count == 0
        assert receipt.claims.canonical_predecessor_capability_consumed
        assert receipt.claims.direct11_physical16_continuity_bound
        assert receipt.claims.fixed_four_row_transaction_fenced
        assert receipt.claims.invalid_source_destination_atomicity_contract_bound
        assert receipt.claims.conditional_post_checkpoint_capability_issued
        assert not receipt.claims.authoritative_predecessor_proven
        assert not receipt.claims.authoritative_numerical_transaction_proven
        with pytest.raises(Exception) as consumed:
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                predecessor,
                expected_context=canonical.context,
            )
        assert getattr(consumed.value, "code", "") == (
            "hip_fgmres_canonical_predecessor_capability_invalid"
        )
    finally:
        _close(values, opened)


def test_unused_child_close_allows_reopen_but_consumed_capability_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability = _open_predecessor(monkeypatch)
    canonical = values[-1].context
    first = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
        canonical,
        capability,
    )
    second = None
    try:
        with pytest.raises(Exception) as active:
            open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
                canonical,
                capability,
            )
        assert getattr(active.value, "code", "") == (
            "hip_fgmres_canonical_predecessor_sealed_child_unavailable"
        )
        with pytest.raises(Exception) as close_blocked:
            canonical.close()
        assert getattr(close_blocked.value, "code", "") == (
            "hip_fgmres_canonical_predecessor_sealed_child_active"
        )
        first.context.close()
        second = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical,
            capability,
        )
        pending = second.context.enqueue_sealed_checkpoint_transaction()
        second.context.synchronize_sealed_checkpoint_transaction(pending)
        second.context.close()
        with pytest.raises(Exception) as stale:
            open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
                canonical,
                capability,
            )
        assert getattr(stale.value, "code", "") == (
            "hip_fgmres_canonical_predecessor_capability_invalid"
        )
    finally:
        if second is not None and not second.context.closed:
            second.context.close()
        if not first.context.closed:
            first.context.close()
        _close_canonical(values)


def test_global_recurrence_child_unused_release_reopens_but_consumed_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    first_token = _mint_global_recurrence_child_lease_v1()
    second_token = _mint_global_recurrence_child_lease_v1()
    active_token: object | None = None
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as forged:
            context._reserve_global_recurrence_child(
                HipFgmresSealedCheckpointContinuationCapabilityV1,
                continuation,
            )
        assert forged.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_global_child_token_invalid"
        )
        assert (
            context._reserve_global_recurrence_child(first_token, continuation)
            is first_token
        )
        active_token = first_token
        authority = context._global_recurrence_child_authority(
            first_token,
            continuation_consumed=False,
        )
        binding = context._binding
        assert binding is not None
        assert authority.kernel is binding.kernel
        assert authority.checkpoint_owner_token is binding.checkpoint_owner_token
        assert authority.loaded_runtime is binding.loaded_runtime
        assert authority.stream_pointer == binding.stream_pointer
        assert (
            tuple(role for role, _pointer in authority.physical_pointer_values)
            == _PHYSICAL_ROLES
        )
        assert len(authority.physical_pointer_values) == 16
        assert not hasattr(authority, "__dict__")
        with pytest.raises(AttributeError):
            authority.stream_pointer = authority.stream_pointer + 1  # type: ignore[misc]

        canonical = values[-1].context
        original_scratch = canonical._pointers["reduction_ping"]
        canonical._pointers["reduction_ping"] = original_scratch + 8
        try:
            with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as drifted:
                context._global_recurrence_child_authority(
                    first_token,
                    continuation_consumed=False,
                )
            assert drifted.value.code == (
                "hip_fgmres_sealed_checkpoint_transaction_global_child_authority_invalid"
            )
        finally:
            canonical._pointers["reduction_ping"] = original_scratch
        context._require_global_recurrence_child(
            first_token,
            continuation_consumed=False,
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as blocked:
            context.close()
        assert blocked.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_global_child_active"
        )
        assert not context.closed

        context._release_global_recurrence_child(first_token)
        active_token = None
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )

        assert (
            context._reserve_global_recurrence_child(second_token, continuation)
            is second_token
        )
        active_token = second_token
        _register_global_recurrence_recovery(context, second_token)
        context._consume_global_recurrence_continuation_capability(
            second_token,
            continuation,
        )
        consumed_authority = context._global_recurrence_child_authority(
            second_token,
            continuation_consumed=True,
        )
        assert consumed_authority.kernel is authority.kernel
        assert (
            consumed_authority.physical_pointer_values
            == authority.physical_pointer_values
        )
        assert context._global_recurrence_continuation_capability_consumed(second_token)
        context._require_global_recurrence_child(
            second_token,
            continuation_consumed=True,
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as consumed:
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
        assert consumed.value.code == (
            "hip_fgmres_sealed_checkpoint_continuation_capability_invalid"
        )

        context._release_global_recurrence_child(second_token)
        active_token = None
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as reopened:
            context._reserve_global_recurrence_child(
                _mint_global_recurrence_child_lease_v1(),
                continuation,
            )
        assert reopened.value.code == (
            "hip_fgmres_sealed_checkpoint_continuation_capability_invalid"
        )
    finally:
        if active_token is not None:
            context._release_global_recurrence_child(active_token)
        _close(values, opened)


def test_global_recurrence_child_two_thread_reserve_race_has_one_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    tokens = (
        _mint_global_recurrence_child_lease_v1(),
        _mint_global_recurrence_child_lease_v1(),
    )
    winner: object | None = None
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    context._reserve_global_recurrence_child,
                    token,
                    continuation,
                )
                for token in tokens
            ]
        successes: list[object] = []
        failures: list[BaseException] = []
        for future in futures:
            try:
                successes.append(future.result())
            except BaseException as exc:
                failures.append(exc)
        assert len(successes) == len(failures) == 1
        winner = successes[0]
        assert winner in tokens
        assert getattr(failures[0], "code", "") in {
            "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant",
            "hip_fgmres_sealed_checkpoint_transaction_global_child_unavailable",
        }
        context._require_global_recurrence_child(
            winner,
            continuation_consumed=False,
        )
    finally:
        if winner is not None:
            context._release_global_recurrence_child(winner)
        _close(values, opened)


def test_global_recurrence_consume_without_recovery_registration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    binding = context._binding
    assert binding is not None
    token = _mint_global_recurrence_child_lease_v1()
    active = False
    try:
        context._reserve_global_recurrence_child(token, continuation)
        active = True
        launch_count = len(loaded.launch_records)
        sync_count = len(loaded.sync_streams)
        query_count = len(loaded.query_streams)
        pending_snapshot = kernel._checkpoint_pending_snapshot(
            binding.checkpoint_owner_token
        )

        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as missing:
            context._consume_global_recurrence_continuation_capability(
                token,
                continuation,
            )
        assert missing.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid"
        )
        assert not context._global_recurrence_continuation_capability_consumed(token)
        assert context._global_recurrence_recovery_snapshot() is None
        assert len(loaded.launch_records) == launch_count
        assert len(loaded.sync_streams) == sync_count
        assert len(loaded.query_streams) == query_count
        assert (
            kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token)
            == pending_snapshot
            == ()
        )

        context._release_global_recurrence_child(token)
        active = False
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )
    finally:
        if active:
            context._release_global_recurrence_child(token)
        _close(values, opened)


def test_global_recurrence_consume_return_baseexception_reconciles_parent_bit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    token = _mint_global_recurrence_child_lease_v1()
    context_type = type(context)
    original_consume = context_type._consume_global_recurrence_continuation_capability

    class InjectedInterruption(BaseException):
        pass

    def consume_then_interrupt(owner: Any, child: object, capability: Any) -> None:
        original_consume(owner, child, capability)
        raise InjectedInterruption("injected interruption after shared consume")

    monkeypatch.setattr(
        context_type,
        "_consume_global_recurrence_continuation_capability",
        consume_then_interrupt,
    )
    active = False
    try:
        context._reserve_global_recurrence_child(token, continuation)
        active = True
        _register_global_recurrence_recovery(context, token)
        with pytest.raises(InjectedInterruption):
            context._consume_global_recurrence_continuation_capability(
                token,
                continuation,
            )
        assert context._global_recurrence_continuation_capability_consumed(token)
        context._require_global_recurrence_child(
            token,
            continuation_consumed=True,
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
        context._release_global_recurrence_child(token)
        active = False
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
            context._reserve_global_recurrence_child(
                _mint_global_recurrence_child_lease_v1(),
                continuation,
            )
    finally:
        if active:
            context._release_global_recurrence_child(token)
        _close(values, opened)


def test_global_recurrence_release_requires_exact_empty_pending_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    kernel = values[-3]
    context = opened.context
    binding = context._binding
    assert binding is not None
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    token = _mint_global_recurrence_child_lease_v1()
    context._reserve_global_recurrence_child(token, continuation)
    kernel_type = type(kernel)
    original_snapshot = kernel_type._checkpoint_pending_snapshot
    try:

        def nonempty_zero_count_map(owner: Any, checkpoint_token: object) -> Any:
            if checkpoint_token is binding.checkpoint_owner_token:
                return ((binding.stream_pointer, 0),)
            return original_snapshot(owner, checkpoint_token)

        with monkeypatch.context() as patch:
            patch.setattr(
                kernel_type,
                "_checkpoint_pending_snapshot",
                nonempty_zero_count_map,
            )
            with pytest.raises(
                HipFgmresSealedCheckpointTransactionV1Error
            ) as malformed_authority:
                context._global_recurrence_child_authority(
                    token,
                    continuation_consumed=False,
                )
            assert malformed_authority.value.code == (
                "hip_fgmres_sealed_checkpoint_transaction_binding_changed"
            )
            with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as rejected:
                context._release_global_recurrence_child(token)
            assert rejected.value.code == (
                "hip_fgmres_sealed_checkpoint_transaction_global_child_pending"
            )

        def exact_two_operation_map(owner: Any, checkpoint_token: object) -> Any:
            if checkpoint_token is binding.checkpoint_owner_token:
                return ((binding.stream_pointer, 2),)
            return original_snapshot(owner, checkpoint_token)

        with monkeypatch.context() as patch:
            patch.setattr(
                kernel_type,
                "_checkpoint_pending_snapshot",
                exact_two_operation_map,
            )
            authority = context._global_recurrence_child_authority(
                token,
                continuation_consumed=False,
                expected_pending_operation_bounds=(2, 2),
            )
            assert authority.stream_pointer == binding.stream_pointer
        context._require_global_recurrence_child(
            token,
            continuation_consumed=False,
        )
    finally:
        context._release_global_recurrence_child(token)
        _close(values, opened)


def test_global_recurrence_transition_callback_cannot_reenter_parent_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    token = _mint_global_recurrence_child_lease_v1()
    context_type = type(context)
    original_require_binding = context_type._require_current_binding
    callback_failures: list[BaseException] = []
    callback_count = 0

    def require_binding_with_callback(owner: Any, **keywords: Any) -> None:
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            try:
                owner.close()
            except BaseException as exc:
                callback_failures.append(exc)
        original_require_binding(owner, **keywords)

    monkeypatch.setattr(
        context_type,
        "_require_current_binding",
        require_binding_with_callback,
    )
    active = False
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            reserved = pool.submit(
                context._reserve_global_recurrence_child,
                token,
                continuation,
            ).result(timeout=5)
        active = True
        assert reserved is token
        assert len(callback_failures) == 1
        assert getattr(callback_failures[0], "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_global_child_operation_reentrant"
        )
        assert not context.closed
    finally:
        if active:
            context._release_global_recurrence_child(token)
        _close(values, opened)


def test_global_recurrence_begin_return_interruptions_clear_exact_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    continuation = context.synchronize_sealed_checkpoint_transaction(pending)
    token = _mint_global_recurrence_child_lease_v1()
    context_type = type(context)
    original_begin = context_type._begin_global_recurrence_child_operation

    class InjectedInterruption(BaseException):
        pass

    def begin_then_interrupt(
        owner: Any,
        operation: str,
        marker: object,
    ) -> None:
        original_begin(owner, operation, marker)
        raise InjectedInterruption(operation)

    active = False
    try:
        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            begin_then_interrupt,
        )
        with pytest.raises(InjectedInterruption, match="reserve"):
            context._reserve_global_recurrence_child(token, continuation)
        assert context._global_recurrence_child_operation is None
        assert context._global_recurrence_child_token is None

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            original_begin,
        )
        assert context._reserve_global_recurrence_child(token, continuation) is token
        active = True
        _register_global_recurrence_recovery(context, token)

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            begin_then_interrupt,
        )
        with pytest.raises(InjectedInterruption, match="consume"):
            context._consume_global_recurrence_continuation_capability(
                token,
                continuation,
            )
        assert context._global_recurrence_child_operation is None
        assert not context._global_recurrence_continuation_capability_consumed(token)

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            original_begin,
        )
        context._consume_global_recurrence_continuation_capability(
            token,
            continuation,
        )

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            begin_then_interrupt,
        )
        with pytest.raises(InjectedInterruption, match="authority"):
            context._global_recurrence_child_authority(
                token,
                continuation_consumed=True,
            )
        assert context._global_recurrence_child_operation is None

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            original_begin,
        )
        authority = context._global_recurrence_child_authority(
            token,
            continuation_consumed=True,
        )
        assert authority.stream_pointer > 0

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            begin_then_interrupt,
        )
        with pytest.raises(InjectedInterruption, match="release"):
            context._release_global_recurrence_child(token)
        assert context._global_recurrence_child_operation is None
        context._require_global_recurrence_child(
            token,
            continuation_consumed=True,
        )

        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            original_begin,
        )
        context._release_global_recurrence_child(token)
        active = False
        assert context._global_recurrence_child_token is None
        assert context._global_recurrence_child_terminal
    finally:
        monkeypatch.setattr(
            context_type,
            "_begin_global_recurrence_child_operation",
            original_begin,
        )
        if active:
            context._release_global_recurrence_child(token)
        _close(values, opened)


def test_two_thread_open_and_enqueue_races_are_single_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability = _open_predecessor(monkeypatch)
    canonical = values[-1].context
    opened: list[Any] = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
                    canonical,
                    capability,
                )
                for _ in range(2)
            ]
        failures: list[BaseException] = []
        for future in futures:
            try:
                opened.append(future.result())
            except BaseException as exc:
                failures.append(exc)
        assert len(opened) == len(failures) == 1
        context = opened[0].context
        loaded = values[-3]._runtime._runtime
        baseline = len(loaded.launch_records)
        with ThreadPoolExecutor(max_workers=2) as pool:
            enqueue_futures = [
                pool.submit(context.enqueue_sealed_checkpoint_transaction)
                for _ in range(2)
            ]
        pending: list[Any] = []
        enqueue_failures: list[BaseException] = []
        for future in enqueue_futures:
            try:
                pending.append(future.result())
            except BaseException as exc:
                enqueue_failures.append(exc)
        assert len(pending) == len(enqueue_failures) == 1
        assert getattr(enqueue_failures[0], "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_state_invalid"
        )
        assert len(loaded.launch_records[baseline:]) == 4
        context.synchronize_sealed_checkpoint_transaction(pending[0])
    finally:
        for row in opened:
            if not row.context.closed:
                row.context.close()
        _close_canonical(values)


def test_binding_drift_before_enqueue_is_zero_work_and_capability_remains_unused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability, opened, baseline = _open_sealed(monkeypatch)
    canonical = values[-1].context
    loaded = values[-3]._runtime._runtime
    original = canonical._pointers["work_w"]
    canonical._pointers["work_w"] = original + 8
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as changed:
            opened.context.enqueue_sealed_checkpoint_transaction()
        assert changed.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_binding_changed"
        )
        assert opened.context.receipt().status == "context_ready"
        assert len(loaded.launch_records) == baseline
        assert (
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability,
                expected_context=canonical,
            )
            is capability
        )
    finally:
        canonical._pointers["work_w"] = original
        _close(values, opened)


def test_consume_return_interruption_reconciles_shared_state_and_cleanup_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability, opened, baseline = _open_sealed(monkeypatch)
    canonical = values[-1].context
    loaded = values[-3]._runtime._runtime
    context = opened.context
    canonical_type = type(canonical)
    original_consume = canonical_type._consume_sealed_checkpoint_transaction_capability

    def consume_then_interrupt(owner: Any, token: object, predecessor: Any) -> None:
        original_consume(owner, token, predecessor)
        raise RuntimeError("injected interruption after shared consume")

    monkeypatch.setattr(
        canonical_type,
        "_consume_sealed_checkpoint_transaction_capability",
        consume_then_interrupt,
    )
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.enqueue_sealed_checkpoint_transaction()
        assert failed.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_enqueue_failed"
        )
        assert failed.value.cleanup_owner is context
        assert failed.value.pending is not None
        receipt = context.receipt()
        assert receipt.status == "poisoned_no_work"
        assert receipt.telemetry.predecessor_capability_consume_count == 1
        assert receipt.telemetry.kernel_launch_attempt_count == 0
        assert len(loaded.launch_records) == baseline
        with pytest.raises(Exception) as consumed:
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability,
                expected_context=canonical,
            )
        assert getattr(consumed.value, "code", "") == (
            "hip_fgmres_canonical_predecessor_capability_invalid"
        )
        context.close()
        assert context.closed
    finally:
        _close(values, opened)


@pytest.mark.parametrize("cleanup_entry", ("synchronize", "close"))
def test_partial_enqueue_pointer_drift_cleanup_uses_frozen_owner_binding(
    monkeypatch: pytest.MonkeyPatch,
    cleanup_entry: str,
) -> None:
    values, _, opened, baseline = _open_sealed(monkeypatch)
    *_, kernel, live, canonical = values
    assert live.context is not None
    context = opened.context
    binding = context._binding
    assert binding is not None
    loaded = kernel._runtime._runtime
    original_pointer = canonical.context._pointers["work_w"]

    def drift_after_first_transaction_row(record_count: int) -> None:
        if record_count == baseline + 1:
            canonical.context._pointers["work_w"] = original_pointer + 8

    loaded.launch_callback = drift_after_first_transaction_row
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.enqueue_sealed_checkpoint_transaction()
        pending = failed.value.pending
        assert pending is not None
        assert len(loaded.launch_records[baseline:]) == 1
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == (
            (binding.stream_pointer, 1),
        )

        if cleanup_entry == "synchronize":
            with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
                context.synchronize_sealed_checkpoint_transaction(pending)
            assert context.receipt().status == "poisoned_fenced"
            assert not context.closed
        else:
            context.close()
            assert context.closed

        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
        assert loaded.sync_streams[-1] == binding.stream_pointer
        assert len(loaded.launch_records[baseline:]) == 1
    finally:
        loaded.launch_callback = None
        canonical.context._pointers["work_w"] = original_pointer
        if kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token):
            kernel._synchronize_checkpoint_stream(
                binding.checkpoint_owner_token,
                binding.stream_pointer,
            )
            kernel._consume_checkpoint_pending_after_fence(
                binding.checkpoint_owner_token,
                binding.stream_pointer,
            )
        if not context.closed:
            context.close()
        _close_canonical(values)


def test_consume_count_without_pending_pop_stays_ack_pending_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    kernel = values[-3]
    context = opened.context
    binding = context._binding
    assert binding is not None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def report_without_pop_then_consume(
        owner: Any,
        token: object,
        stream: Any,
    ) -> int:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            return 4
        return int(original_consume(owner, token, stream))

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        report_without_pop_then_consume,
    )
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert failed.value.cleanup_owner is context
        retryable = context.receipt()
        assert retryable.status in {
            "fence_observed_ack_pending",
            "poisoned_fence_observed_ack_pending",
        }
        assert retryable.telemetry.fence_attempt_count == 1
        assert retryable.telemetry.fence_success_count == 1
        assert retryable.telemetry.pending_consume_attempt_count == 1
        assert retryable.telemetry.consumed_launch_count == 0
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == (
            (binding.stream_pointer, 4),
        )

        if retryable.status == "poisoned_fence_observed_ack_pending":
            with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
                context.synchronize_sealed_checkpoint_transaction(pending)
        else:
            context.synchronize_sealed_checkpoint_transaction(pending)
        fenced = context.receipt()
        assert fenced.status in {"transaction_fenced", "poisoned_fenced"}
        assert fenced.telemetry.fence_attempt_count == 1
        assert fenced.telemetry.pending_consume_attempt_count == 2
        assert fenced.telemetry.consumed_launch_count == 4
        assert consume_calls == 2
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
    finally:
        if kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token):
            original_consume(
                kernel,
                binding.checkpoint_owner_token,
                binding.stream_pointer,
            )
        if not context.closed:
            context.close()
        _close_canonical(values)


@pytest.mark.parametrize("failure_phase", ("fence", "before_pop"))
def test_close_retry_completes_real_fence_and_pending_pop(
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    values, _, opened, baseline = _open_sealed(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    context = opened.context
    binding = context._binding
    assert binding is not None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def fail_once_before_pop(owner: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            raise RuntimeError("injected close interruption before pop")
        return int(original_consume(owner, token, stream))

    if failure_phase == "fence":
        loaded.sync_fail_count = 1
    else:
        monkeypatch.setattr(
            kernel_type,
            "_consume_checkpoint_pending_after_fence",
            fail_once_before_pop,
        )
    pending = context.enqueue_sealed_checkpoint_transaction()
    assert pending.accepted_launch_count_lower_bound == 4
    transaction_sync_baseline = len(loaded.sync_streams)
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.close()
        assert failed.value.cleanup_owner is context
        assert not context.closed
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == (
            (binding.stream_pointer, 4),
        )

        context.close()
        assert context.closed
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
        assert len(loaded.launch_records[baseline:]) == 4
        expected_sync_attempts = 2 if failure_phase == "fence" else 1
        assert (
            len(loaded.sync_streams) - transaction_sync_baseline
            == expected_sync_attempts
        )
        if failure_phase == "before_pop":
            assert consume_calls == 2
    finally:
        if kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token):
            if failure_phase == "fence":
                kernel._synchronize_checkpoint_stream(
                    binding.checkpoint_owner_token,
                    binding.stream_pointer,
                )
            original_consume(
                kernel,
                binding.checkpoint_owner_token,
                binding.stream_pointer,
            )
        if not context.closed:
            context.close()
        _close_canonical(values)


def test_binding_snapshot_and_pointer_map_forgery_cannot_bypass_live_exact11(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability, opened, baseline = _open_sealed(monkeypatch)
    *_, kernel, live, canonical = values
    assert live.context is not None
    context = opened.context
    loaded = kernel._runtime._runtime
    original_binding = context._binding
    original_snapshot = context._binding_value_snapshot
    assert original_binding is not None
    original_pointer = canonical.context._pointers["work_w"]
    work_capability = next(
        row for row in live.context._group_capabilities if row.role == "work_w"
    )
    assert work_capability.pointer_snapshot == original_pointer
    forged_pointer = original_pointer + 8
    forged_pointers = list(original_binding.pointer_values)
    forged_pointers[5] = forged_pointer
    forged_binding = replace(
        original_binding,
        pointer_values=tuple(forged_pointers),
    )
    context._binding = forged_binding
    context._binding_value_snapshot = _binding_values(forged_binding)
    canonical.context._pointers["work_w"] = forged_pointer
    try:
        with pytest.raises(Exception):
            context.enqueue_sealed_checkpoint_transaction()
        assert len(loaded.launch_records) == baseline
        assert (
            kernel._checkpoint_pending_snapshot(original_binding.checkpoint_owner_token)
            == ()
        )
        assert context.receipt().status == "context_ready"
        assert (
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability,
                expected_context=canonical.context,
            )
            is capability
        )
        assert work_capability.pointer_snapshot == original_pointer
    finally:
        canonical.context._pointers["work_w"] = original_pointer
        context._binding = original_binding
        context._binding_value_snapshot = original_snapshot
        if not context.closed:
            context.close()
        _close_canonical(values)


def test_open_rollback_failure_returns_cleanup_owner_for_manual_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, capability = _open_predecessor(monkeypatch)
    canonical = values[-1].context
    canonical_type = type(canonical)
    original_reserve = canonical_type._reserve_sealed_checkpoint_transaction_child
    original_release = canonical_type._release_sealed_checkpoint_transaction_child
    original_pointer = canonical._pointers["work_w"]
    reserved_tokens: list[object] = []
    release_calls = 0
    cleanup_owner: Any | None = None
    reopened: Any | None = None

    def reserve_then_drift(
        owner: Any,
        token: object,
        predecessor: Any,
    ) -> object:
        acquired = original_reserve(owner, token, predecessor)
        reserved_tokens.append(token)
        owner._pointers["work_w"] = original_pointer + 8
        return acquired

    def fail_first_rollback_release(owner: Any, token: object) -> None:
        nonlocal release_calls
        release_calls += 1
        if release_calls == 1:
            raise RuntimeError("injected rollback release failure")
        original_release(owner, token)

    monkeypatch.setattr(
        canonical_type,
        "_reserve_sealed_checkpoint_transaction_child",
        reserve_then_drift,
    )
    monkeypatch.setattr(
        canonical_type,
        "_release_sealed_checkpoint_transaction_child",
        fail_first_rollback_release,
    )
    try:
        with pytest.raises(Exception) as failed:
            open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
                canonical,
                capability,
            )
        cleanup_owner = getattr(failed.value, "cleanup_owner", None)
        assert cleanup_owner is not None
        assert reserved_tokens
        assert release_calls == 1
        assert (
            canonical._sealed_checkpoint_transaction_child_token is reserved_tokens[0]
        )

        canonical._pointers["work_w"] = original_pointer
        cleanup_owner.close()
        assert cleanup_owner.closed
        assert release_calls == 2
        assert canonical._sealed_checkpoint_transaction_child_token is None

        monkeypatch.setattr(
            canonical_type,
            "_reserve_sealed_checkpoint_transaction_child",
            original_reserve,
        )
        monkeypatch.setattr(
            canonical_type,
            "_release_sealed_checkpoint_transaction_child",
            original_release,
        )
        reopened = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical,
            capability,
        )
        reopened.context.close()
    finally:
        canonical._pointers["work_w"] = original_pointer
        monkeypatch.setattr(
            canonical_type,
            "_reserve_sealed_checkpoint_transaction_child",
            original_reserve,
        )
        monkeypatch.setattr(
            canonical_type,
            "_release_sealed_checkpoint_transaction_child",
            original_release,
        )
        if reopened is not None and not reopened.context.closed:
            reopened.context.close()
        if cleanup_owner is not None and not cleanup_owner.closed:
            cleanup_owner.close()
        elif (
            reserved_tokens
            and canonical._sealed_checkpoint_transaction_child_token
            is reserved_tokens[0]
        ):
            original_release(canonical, reserved_tokens[0])
        _close_canonical(values)


def test_pending_and_continuation_mutation_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        original_attempts = pending.attempted_launch_count
        object.__setattr__(pending, "attempted_launch_count", original_attempts + 1)
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as changed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert changed.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_pending_invalid"
        )
        object.__setattr__(pending, "attempted_launch_count", original_attempts)
        continuation = context.synchronize_sealed_checkpoint_transaction(pending)
        original_hash = continuation.receipt_hash
        object.__setattr__(continuation, "receipt_hash", "sha256:" + "0" * 64)
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as forged:
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
        assert forged.value.code == (
            "hip_fgmres_sealed_checkpoint_continuation_capability_invalid"
        )
        object.__setattr__(continuation, "receipt_hash", original_hash)
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )
        context.close()
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
    finally:
        _close(values, opened)


def test_fence_failure_retries_without_reenqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, baseline = _open_sealed(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    context = opened.context
    pending = context.enqueue_sealed_checkpoint_transaction()
    loaded.sync_fail_count = 1
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert failed.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_fence_failed"
        )
        assert len(loaded.launch_records[baseline:]) == 4
        assert context.receipt().status == "transaction_pending"
        context.synchronize_sealed_checkpoint_transaction(pending)
        receipt = context.receipt()
        assert receipt.telemetry.fence_attempt_count == 2
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.consumed_launch_count == 4
        assert len(loaded.launch_records[baseline:]) == 4
    finally:
        _close(values, opened)


def test_receipt_immediately_after_sync_fence_failure_is_self_validating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    context = opened.context
    binding = context._binding
    assert binding is not None
    pending = context.enqueue_sealed_checkpoint_transaction()
    loaded.sync_fail_count = 1
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert failed.value.cleanup_owner is context

        receipt = context.receipt()
        assert receipt.status == "transaction_pending"
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 0
        assert receipt.telemetry.pending_consume_attempt_count == 0
        assert not receipt.claims.fixed_four_row_transaction_fenced
        assert (
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                receipt,
                expected_context=context,
            )
            is receipt
        )
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(receipt.to_dict())
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == (
            (binding.stream_pointer, 4),
        )

        context.synchronize_sealed_checkpoint_transaction(pending)
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
    finally:
        _close(values, opened)


def test_sync_callback_pointer_drift_drains_pending_without_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    *_, kernel, _, canonical = values
    loaded = kernel._runtime._runtime
    context = opened.context
    binding = context._binding
    assert binding is not None
    original_pointer = canonical.context._pointers["work_w"]
    pending = context.enqueue_sealed_checkpoint_transaction()
    sync_baseline = len(loaded.sync_streams)
    callback_calls = 0

    def drift_during_fence() -> None:
        nonlocal callback_calls
        callback_calls += 1
        canonical.context._pointers["work_w"] = original_pointer + 8

    loaded.sync_callback = drift_during_fence
    try:
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert failed.value.cleanup_owner is context
        assert callback_calls == 1
        assert len(loaded.sync_streams) - sync_baseline == 1
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
        assert context.continuation_capability is None

        receipt = context.receipt()
        assert receipt.status == "poisoned_fenced"
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        assert receipt.telemetry.consumed_launch_count == 4
        assert not receipt.claims.fixed_four_row_transaction_fenced
        assert not receipt.claims.conditional_post_checkpoint_capability_issued
        assert (
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                receipt,
                expected_context=context,
            )
            is receipt
        )

        context.close()
        assert context.closed
    finally:
        loaded.sync_callback = None
        canonical.context._pointers["work_w"] = original_pointer
        if not context.closed:
            context.close()
        _close_canonical(values)


def test_same_thread_sync_callback_reentry_is_rejected_without_disturbing_outer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    context = opened.context
    binding = context._binding
    assert binding is not None
    pending = context.enqueue_sealed_checkpoint_transaction()
    sync_baseline = len(loaded.sync_streams)
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    consume_calls = 0
    nested_errors: list[HipFgmresSealedCheckpointTransactionV1Error] = []

    def counted_consume(owner: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        return int(original_consume(owner, token, stream))

    def reenter_synchronize() -> None:
        loaded.sync_callback = None
        try:
            context.synchronize_sealed_checkpoint_transaction(pending)
        except HipFgmresSealedCheckpointTransactionV1Error as exc:
            nested_errors.append(exc)

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        counted_consume,
    )
    loaded.sync_callback = reenter_synchronize
    try:
        continuation = context.synchronize_sealed_checkpoint_transaction(pending)
        assert len(nested_errors) == 1
        assert nested_errors[0].code == (
            "hip_fgmres_sealed_checkpoint_transaction_operation_reentrant"
        )
        assert nested_errors[0].cleanup_owner is context
        assert len(loaded.sync_streams) - sync_baseline == 1
        assert consume_calls == 1
        assert kernel._checkpoint_pending_snapshot(binding.checkpoint_owner_token) == ()
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )

        receipt = context.receipt()
        assert receipt.status == "transaction_fenced"
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        assert receipt.telemetry.consumed_launch_count == 4
        assert receipt.claims.fixed_four_row_transaction_fenced
        assert (
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                receipt,
                expected_context=context,
            )
            is receipt
        )
    finally:
        loaded.sync_callback = None
        _close(values, opened)


def test_same_thread_launch_callback_cannot_observe_transient_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, baseline = _open_sealed(monkeypatch)
    kernel = values[-3]
    loaded = kernel._runtime._runtime
    context = opened.context
    inflight_errors: list[HipFgmresSealedCheckpointTransactionV1Error] = []

    def observe_during_first_row(record_count: int) -> None:
        if record_count != baseline + 1:
            return
        try:
            context.receipt()
        except HipFgmresSealedCheckpointTransactionV1Error as exc:
            inflight_errors.append(exc)

    loaded.launch_callback = observe_during_first_row
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        assert len(inflight_errors) == 1
        assert inflight_errors[0].code == (
            "hip_fgmres_sealed_checkpoint_transaction_receipt_inflight"
        )
        assert inflight_errors[0].cleanup_owner is context
        continuation = context.synchronize_sealed_checkpoint_transaction(pending)
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=context,
            )
            is continuation
        )
        receipt = context.receipt()
        assert (
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                receipt,
                expected_context=context,
            )
            is receipt
        )
    finally:
        loaded.launch_callback = None
        _close(values, opened)


@pytest.mark.parametrize("failure_position", ("before_pop", "after_pop"))
def test_pending_consume_retry_never_refences_or_double_consumes(
    monkeypatch: pytest.MonkeyPatch,
    failure_position: str,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    kernel = values[-3]
    context = opened.context
    kernel_type = type(kernel)
    original = kernel_type._consume_checkpoint_pending_after_fence
    calls = 0

    def interrupted(owner: Any, token: object, stream: Any) -> int:
        nonlocal calls
        calls += 1
        if failure_position == "before_pop" and calls == 1:
            raise RuntimeError("injected before-pop")
        consumed = int(original(owner, token, stream))
        if failure_position == "after_pop" and calls == 1:
            raise RuntimeError("injected after-pop")
        return consumed

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        interrupted,
    )
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as failed:
            context.synchronize_sealed_checkpoint_transaction(pending)
        assert failed.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_pending_consume_failed"
        )
        assert context.receipt().status == "fence_observed_ack_pending"
        context.synchronize_sealed_checkpoint_transaction(pending)
        receipt = context.receipt()
        assert receipt.status == "transaction_fenced"
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 2
        assert receipt.telemetry.consumed_launch_count == 4
        assert calls == 2
    finally:
        _close(values, opened)


def test_receipt_schema_hash_and_semantic_forgery_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        context.synchronize_sealed_checkpoint_transaction(pending)
        receipt = context.receipt()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(receipt.to_dict())

        forged_claims = replace(receipt.claims, actual_mask_host_observed=True)
        forged = replace(receipt, claims=forged_claims)
        forged = replace(
            forged,
            receipt_hash=canonical_hash(_receipt_payload(forged, include_hash=False)),
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(forged)

        inconsistent = replace(
            receipt,
            telemetry=replace(receipt.telemetry, consumed_launch_count=3),
        )
        inconsistent = replace(
            inconsistent,
            receipt_hash=canonical_hash(
                _receipt_payload(inconsistent, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as telemetry:
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(inconsistent)
        assert telemetry.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_claim_invalid"
        )

        relabeled = replace(receipt, actual_backend="hip")
        relabeled = replace(
            relabeled,
            receipt_hash=canonical_hash(
                _receipt_payload(relabeled, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as backend:
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(relabeled)
        assert backend.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_backend_invalid"
        )

        for field in (
            "kernel_source_sha256",
            "recurrence_kernel_abi_hash",
            "canonical_schedule_hash",
            "validator_schedule_hash",
        ):
            wrong_identity = replace(
                receipt,
                bindings=replace(
                    receipt.bindings,
                    **{field: "sha256:" + "0" * 64},
                ),
            )
            wrong_identity = replace(
                wrong_identity,
                receipt_hash=canonical_hash(
                    _receipt_payload(wrong_identity, include_hash=False)
                ),
            )
            with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error):
                validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                    wrong_identity
                )

        coordinated = replace(
            receipt,
            actual_backend="hip",
            bindings=replace(
                receipt.bindings,
                primitive_evidence_scope="native_hiprtc_krylov_primitives_composite",
                primitive_actual_backend="hip",
                kernel_origin="internally_compiled",
                runtime_library_discovery_source="explicit",
                hiprtc_library_discovery_source="explicit",
            ),
        )
        coordinated = replace(
            coordinated,
            receipt_hash=canonical_hash(
                _receipt_payload(coordinated, include_hash=False)
            ),
        )
        # Standalone validation proves closed-schema semantic consistency, not
        # provenance authenticity. The live process-local context is the trust
        # anchor for coordinated provenance relabel rejection.
        assert (
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(coordinated)
            is coordinated
        )
        with pytest.raises(HipFgmresSealedCheckpointTransactionV1Error) as lineage:
            validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
                coordinated,
                expected_context=context,
            )
        assert lineage.value.code == (
            "hip_fgmres_sealed_checkpoint_transaction_context_mismatch"
        )
    finally:
        _close(values, opened)


def test_closed_receipt_drops_current_binding_claims_but_keeps_fenced_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values, _, opened, _ = _open_sealed(monkeypatch)
    context = opened.context
    try:
        pending = context.enqueue_sealed_checkpoint_transaction()
        context.synchronize_sealed_checkpoint_transaction(pending)
        context.close()
        receipt = context.receipt()
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.status == "context_closed"
        assert not receipt.claims.live_krylov_parent_bound
        assert not receipt.claims.canonical_predecessor_capability_reserved
        assert not receipt.claims.direct11_physical16_continuity_bound
        assert not receipt.claims.same_runtime_device_stream_bound
        assert not receipt.claims.fixed_four_row_program_bound
        assert not receipt.claims.device_seal_transition_program_bound
        assert not receipt.claims.invalid_source_destination_atomicity_contract_bound
        assert receipt.claims.canonical_predecessor_capability_consumed
        assert receipt.claims.fixed_four_row_transaction_fenced
        assert receipt.claims.conditional_post_checkpoint_capability_issued
    finally:
        _close(values, opened)


def test_sealed_capability_types_are_not_publicly_constructible() -> None:
    with pytest.raises(TypeError):
        HipFgmresSealedCheckpointTransactionPendingV1()
    with pytest.raises(TypeError):
        HipFgmresSealedCheckpointContinuationCapabilityV1()
