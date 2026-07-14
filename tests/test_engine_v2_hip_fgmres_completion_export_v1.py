from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, dataclass, replace
import gc
import json
from pathlib import Path
import threading
from typing import Any
import weakref

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

import structural_analysis.engine_v2 as engine_v2_public
import structural_analysis.engine_v2.assembly_backend as assembly_backend_public
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_completion_export_v1 as completion_export_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V1,
    HipFgmresCompletionExportExecutionContextV1,
    HipFgmresCompletionExportV1Error,
    open_hip_fgmres_completion_export_context_v1,
    validate_hip_fgmres_completion_export_receipt_v1,
    validate_hip_fgmres_completion_export_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceCompletionCapabilityV1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_global_recurrence_context_v1 import (
    _InjectedOpcodeInterruption,
    _close_stack,
    _interrupt_immediately_after_store_attr,
    _open_stack,
)


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "structural_analysis"
    / "schemas"
    / "hip_fgmres_completion_export_v1.schema.json"
)
SOURCE_ROLES = ("solution_x", "true_residual", "solve_record")


@dataclass
class _BlockingCopyProbe:
    """Test-local stable blocking-D2H binding for the shared fake runtime."""

    fail_at: int | None = None
    fail_after_copy: bool = False

    def __post_init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def install(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runtime: Any,
    ) -> None:
        class _StableBlockingCopy:
            __slots__ = ("_loaded", "_memcpy")

            def __init__(_self) -> None:
                _self._memcpy = runtime.allocations
                _self._loaded = runtime

            def __call__(_self, array: np.ndarray, pointer: int) -> None:
                call_number = len(self.calls) + 1
                self.calls.append((int(pointer), int(array.nbytes)))
                if call_number == self.fail_at and not self.fail_after_copy:
                    raise RuntimeError(f"injected blocking D2H failure {call_number}")
                memoryview(array).cast("B")[:] = runtime.allocations[int(pointer)]
                if call_number == self.fail_at and self.fail_after_copy:
                    raise RuntimeError(
                        f"injected blocking D2H return loss {call_number}"
                    )

        stable_copy = _StableBlockingCopy()
        monkeypatch.setattr(
            runtime,
            "_blocking_d2h_copy",
            stable_copy,
            raising=False,
        )


def _fence_global(stack: dict[str, Any]) -> Any:
    context = stack["global"].context
    pending = context.enqueue_remaining_global_recurrence()
    completion = context.synchronize(pending)
    assert type(completion) is HipFgmresGlobalRecurrenceCompletionCapabilityV1
    assert context.receipt().status == "recurrence_fenced"
    return completion


def _completion_sources(stack: dict[str, Any]) -> tuple[Any, ...]:
    direct = stack["global"].context._require_binding().direct_capabilities
    by_role = {row.role: row for row in direct}
    return tuple(by_role[role] for role in SOURCE_ROLES)


def _seed_completion_sources(
    stack: dict[str, Any],
) -> tuple[tuple[Any, ...], tuple[bytes, ...]]:
    runtime = stack["runtime"]
    sources = _completion_sources(stack)
    payloads = tuple(
        bytes(
            (17 + 53 * role_index + 29 * byte_index) & 0xFF
            for byte_index in range(source.nbytes)
        )
        for role_index, source in enumerate(sources)
    )
    for source, payload in zip(sources, payloads, strict=True):
        runtime.allocations[int(source.pointer_snapshot)][:] = payload
    return sources, payloads


def _receipt_with_recomputed_hash(receipt: Any, **changes: Any) -> Any:
    forged = replace(receipt, **changes)
    return replace(
        forged,
        receipt_hash=canonical_hash(
            completion_export_module._receipt_payload(
                forged,
                include_hash=False,
            )
        ),
    )


def test_completion_export_copies_exact_three_buffers_in_order_and_preserves_global_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    export_context = None
    try:
        completion = _fence_global(stack)
        sources, payloads = _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        global_before = stack["global"].context.receipt()
        global_before_payload = global_before.to_dict()
        malloc_count = stack["runtime"].malloc_calls
        h2d_count = len(stack["runtime"].h2d_arrays)
        launch_count = len(stack["loaded"].launch_records)
        fence_count = len(stack["loaded"].sync_streams)

        opened = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        )
        export_context = opened.context
        assert opened.ready
        assert opened.receipt.status == "context_ready"
        assert opened.receipt.bindings.copy_api == (
            HIP_FGMRES_COMPLETION_EXPORT_COPY_API_V1
        )
        assert opened.receipt.telemetry.d2h_operation_attempt_count == 0
        assert tuple(row.role for row in opened.receipt.buffers) == SOURCE_ROLES

        result = export_context.export_completion_buffers()
        assert export_context.export() is result
        assert export_context.result is result
        assert export_context._staging is None
        assert probe.calls == [
            (int(source.pointer_snapshot), int(source.nbytes)) for source in sources
        ]
        assert (
            result.solution_x,
            result.true_residual,
            result.solve_record,
        ) == payloads

        receipt = result.receipt
        dimensions = receipt.dimensions
        expected_byte_counts = (
            8 * dimensions.free_dof_count,
            8 * dimensions.free_dof_count,
            192 + 72 * dimensions.maximum_restart_count,
        )
        assert tuple(len(payload) for payload in payloads) == expected_byte_counts
        assert tuple(row.byte_count for row in receipt.buffers) == (
            expected_byte_counts
        )
        assert dimensions.total_export_byte_count == sum(expected_byte_counts)
        assert receipt.status == "exported"
        assert receipt.telemetry.completion_capability_consume_count == 1
        assert receipt.telemetry.host_staging_allocation_count == 3
        assert receipt.telemetry.d2h_operation_attempt_count == 3
        assert receipt.telemetry.d2h_operation_success_count == 3
        assert receipt.telemetry.d2h_bytes_attempted == sum(expected_byte_counts)
        assert receipt.telemetry.d2h_bytes_succeeded == sum(expected_byte_counts)
        assert receipt.telemetry.blocking_copy_completion_count == 3
        assert receipt.telemetry.explicit_stream_sync_count == 0
        assert receipt.claims.global_fenced_completion_bound
        assert receipt.claims.completion_capability_consumed
        assert receipt.claims.raw_completion_buffers_host_materialized
        assert receipt.claims.blocking_completion_only_d2h
        assert receipt.claims.immutable_detached_host_payload
        assert not receipt.claims.solve_record_semantics_interpreted
        assert not receipt.claims.actual_terminal_outcome_host_observed
        assert not receipt.claims.authoritative_terminal_status_proven
        assert not receipt.claims.numerical_parity_verified
        assert not receipt.claims.solution_ready
        assert not receipt.claims.result_ir_ready
        assert not receipt.claims.promotion_eligible

        assert stack["runtime"].malloc_calls == malloc_count
        assert len(stack["runtime"].h2d_arrays) == h2d_count
        assert len(stack["loaded"].launch_records) == launch_count
        assert len(stack["loaded"].sync_streams) == fence_count
        global_after = stack["global"].context.receipt()
        assert global_after == global_before
        assert global_after.to_dict() == global_before_payload
        assert global_after.telemetry.d2h_operation_count == 0
        assert not global_after.claims.actual_terminal_outcome_host_observed

        export_context.close()
        assert export_context.closed
        assert stack["global"].context.receipt() == global_before
        assert result.solution_x == payloads[0]
        assert result.true_residual == payloads[1]
        assert result.solve_record == payloads[2]
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_completion_export_is_single_use_and_concurrent_calls_publish_one_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    export_context = None
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        opened = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        )
        export_context = opened.context

        with pytest.raises(Exception) as active_child:
            open_hip_fgmres_completion_export_context_v1(
                stack["global"].context,
                completion,
            )
        assert getattr(active_child.value, "code", "") == (
            "hip_fgmres_global_recurrence_completion_export_reservation_invalid"
        )
        assert probe.calls == []

        barrier = threading.Barrier(4)

        def export_once() -> Any:
            barrier.wait()
            return export_context.export()

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = tuple(executor.map(lambda _index: export_once(), range(4)))
        assert all(result is results[0] for result in results)
        assert len(probe.calls) == 3

        export_context.close()
        assert export_context.closed
        with pytest.raises(Exception) as consumed:
            open_hip_fgmres_completion_export_context_v1(
                stack["global"].context,
                completion,
            )
        assert getattr(consumed.value, "code", "") == (
            "hip_fgmres_global_recurrence_completion_export_reservation_invalid"
        )
        assert len(probe.calls) == 3
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_unused_reopen_binding_drift_and_staging_failure_remain_precopy_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    export_context = None
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        parent = stack["global"].context

        unused = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        with pytest.raises(Exception) as active_child:
            parent.close()
        assert getattr(active_child.value, "code", "") == (
            "hip_fgmres_global_recurrence_cleanup_failed"
        )
        assert not parent.closed
        abandoned = weakref.ref(unused)
        del unused
        gc.collect()
        assert abandoned() is None

        export_context = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        original_fenced_count = completion.fenced_launch_count
        object.__setattr__(
            completion,
            "fenced_launch_count",
            original_fenced_count + 1,
        )
        try:
            with pytest.raises(HipFgmresCompletionExportV1Error) as upstream:
                export_context.export()
        finally:
            object.__setattr__(
                completion,
                "fenced_launch_count",
                original_fenced_count,
            )
        assert upstream.value.code == (
            "hip_fgmres_completion_export_upstream_failed"
        )
        assert upstream.value.cleanup_owner is export_context
        assert export_context.receipt().status == "context_ready"
        assert probe.calls == []

        stable_binding = stack["runtime"]._blocking_d2h_copy
        original_memcpy = stable_binding._memcpy
        object.__setattr__(stable_binding, "_memcpy", object())
        try:
            with pytest.raises(Exception):
                export_context.export()
        finally:
            object.__setattr__(stable_binding, "_memcpy", original_memcpy)
        assert probe.calls == []
        assert export_context.receipt().status == "context_ready"

        with monkeypatch.context() as operation_drift:
            operation_drift.setattr(
                type(stable_binding),
                "__call__",
                lambda _self, _array, _pointer: None,
            )
            with pytest.raises(HipFgmresCompletionExportV1Error) as changed_call:
                export_context.export()
        assert changed_call.value.cleanup_owner is export_context
        assert probe.calls == []
        assert export_context.receipt().status == "context_ready"

        original_binding = stack["runtime"]._blocking_d2h_copy
        with monkeypatch.context() as drift:
            drift.setattr(stack["runtime"], "_blocking_d2h_copy", object())
            with pytest.raises(Exception):
                export_context.export()
        assert probe.calls == []
        assert export_context.receipt().status == "context_ready"
        assert stack["runtime"]._blocking_d2h_copy is original_binding

        with monkeypatch.context() as allocation_failure:
            allocation_failure.setattr(
                completion_export_module,
                "_allocate_host_staging",
                lambda _sources: (_ for _ in ()).throw(
                    MemoryError("injected host allocation failure")
                ),
            )
            with pytest.raises(HipFgmresCompletionExportV1Error) as failed:
                export_context.export()
        assert failed.value.code == (
            "hip_fgmres_completion_export_host_staging_allocation_failed"
        )
        ready = export_context.receipt()
        assert ready.status == "context_ready"
        assert ready.telemetry.completion_capability_consume_count == 0
        assert ready.telemetry.host_staging_allocation_count == 0
        assert probe.calls == []

        result = export_context.export()
        assert result.receipt.status == "exported"
        assert len(probe.calls) == 3
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_completion_export_public_api_has_one_identity() -> None:
    assert len(completion_export_module.__all__) == 18
    for name in completion_export_module.__all__:
        assert name in assembly_backend_public.__all__
        assert name in engine_v2_public.__all__
        assert getattr(assembly_backend_public, name) is getattr(
            completion_export_module,
            name,
        )
        assert getattr(engine_v2_public, name) is getattr(
            completion_export_module,
            name,
        )


def test_consume_reconcile_and_release_return_loss_preserve_cleanup_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    export_context = None
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        parent = stack["global"].context

        ambiguous = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        with monkeypatch.context() as consume_failure:
            consume_failure.setattr(
                parent,
                "_consume_completion_export_capability",
                lambda _token, _capability: (_ for _ in ()).throw(
                    RuntimeError("injected pre-consume failure")
                ),
            )
            consume_failure.setattr(
                parent,
                "_completion_export_capability_is_consumed",
                lambda _token: (_ for _ in ()).throw(
                    RuntimeError("injected consume-query failure")
                ),
            )
            with pytest.raises(HipFgmresCompletionExportV1Error) as failed:
                ambiguous.export()
        assert failed.value.code == (
            "hip_fgmres_completion_export_consume_reconcile_failed"
        )
        with pytest.raises(HipFgmresCompletionExportV1Error) as blocked_receipt:
            ambiguous.receipt()
        assert blocked_receipt.value.code == (
            "hip_fgmres_completion_export_consumption_reconciliation_required"
        )
        ambiguous.close()
        closed = ambiguous.receipt()
        assert closed.status == "context_closed"
        assert closed.telemetry.completion_capability_consume_count == 0
        assert closed.telemetry.host_staging_allocation_count == 0
        assert probe.calls == []

        empty_cleanup = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        with monkeypatch.context() as empty_failure:
            empty_failure.setattr(
                parent,
                "_release_completion_export_child",
                lambda _token: (_ for _ in ()).throw(RuntimeError()),
            )
            with pytest.raises(HipFgmresCompletionExportV1Error) as cleanup:
                empty_cleanup.close()
        cleanup_receipt = empty_cleanup.receipt()
        assert cleanup.value.cleanup_owner is empty_cleanup
        assert cleanup_receipt.status == "cleanup_failed"
        assert cleanup_receipt.reason is not None
        assert cleanup_receipt.reason.detail == cleanup_receipt.reason.code
        validate_hip_fgmres_completion_export_receipt_v1(
            cleanup_receipt,
            expected_context=empty_cleanup,
        )
        empty_cleanup.close()

        unconsumed_return_loss = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        original_release = parent._release_completion_export_child
        with monkeypatch.context() as release_failure:

            def release_then_raise(token: object) -> None:
                original_release(token)
                raise RuntimeError("injected release return loss")

            release_failure.setattr(
                parent,
                "_release_completion_export_child",
                release_then_raise,
            )
            unconsumed_return_loss.close()
        assert unconsumed_return_loss.closed

        export_context = open_hip_fgmres_completion_export_context_v1(
            parent,
            completion,
        ).context
        result = export_context.export()
        assert result.receipt.status == "exported"
        assert len(probe.calls) == 3
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                type(parent)._release_completion_export_child,
                "_completion_export_child_terminal",
                export_context.close,
            )
        assert not export_context.closed
        assert export_context._child_released
        export_context.close()
        assert export_context.closed
        with pytest.raises(Exception):
            open_hip_fgmres_completion_export_context_v1(parent, completion)
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_publication_store_interruptions_reconcile_without_recopied_or_closed_resurrection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    export_context = None
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        export_context = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        ).context

        export_operation = (
            HipFgmresCompletionExportExecutionContextV1.export_completion_buffers
        )
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                export_operation.__wrapped__,
                "_publication",
                export_context.export,
            )
        publication = export_context._publication
        assert publication is not None
        assert export_context.receipt() is publication.receipt
        assert export_context.result is None
        assert len(probe.calls) == 3

        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                HipFgmresCompletionExportExecutionContextV1._finish_publication,
                "_result",
                export_context.export,
            )
        assert export_context.result is publication
        assert export_context.receipt() is publication.receipt
        assert export_context.export() is publication
        assert len(probe.calls) == 3

        export_context.close()
        closed_receipt = export_context.receipt()
        assert closed_receipt.status == "context_closed"
        forged_closed = _receipt_with_recomputed_hash(
            closed_receipt,
            telemetry=replace(
                closed_receipt.telemetry,
                completion_capability_consume_count=0,
                host_staging_allocation_count=0,
                d2h_operation_attempt_count=0,
                d2h_operation_success_count=0,
                d2h_bytes_attempted=0,
                d2h_bytes_succeeded=0,
                blocking_copy_completion_count=0,
            ),
            claims=replace(
                closed_receipt.claims,
                completion_capability_consumed=False,
            ),
        )
        assert validate_hip_fgmres_completion_export_receipt_v1(
            forged_closed
        ) is forged_closed
        with pytest.raises(HipFgmresCompletionExportV1Error) as forged_provenance:
            validate_hip_fgmres_completion_export_receipt_v1(
                forged_closed,
                expected_context=export_context,
            )
        assert forged_provenance.value.code == (
            "hip_fgmres_completion_export_provenance_invalid"
        )
        with pytest.raises(HipFgmresCompletionExportV1Error):
            export_context.export()
        assert export_context.closed
        assert export_context.receipt() == closed_receipt
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_completion_export_rejects_prefence_foreign_and_forged_capabilities_without_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_stack = _open_stack(monkeypatch)
    target_stack = None
    source_export_context = None
    try:
        completion = _fence_global(source_stack)
        source_probe = _BlockingCopyProbe()
        source_probe.install(monkeypatch, source_stack["runtime"])
        target_stack = _open_stack(monkeypatch)
        target_probe = _BlockingCopyProbe()
        target_probe.install(monkeypatch, target_stack["runtime"])
        assert target_stack["global"].context.receipt().status == "context_ready"

        with pytest.raises(Exception):
            open_hip_fgmres_completion_export_context_v1(
                target_stack["global"].context,
                completion,
            )
        assert target_probe.calls == []
        assert target_stack["global"].context.receipt().status == "context_ready"

        original_count = completion.fenced_launch_count
        object.__setattr__(completion, "fenced_launch_count", original_count + 1)
        try:
            with pytest.raises(Exception) as forged:
                open_hip_fgmres_completion_export_context_v1(
                    source_stack["global"].context,
                    completion,
                )
            assert getattr(forged.value, "code", "") == (
                "hip_fgmres_global_recurrence_completion_capability_invalid"
            )
        finally:
            object.__setattr__(completion, "fenced_launch_count", original_count)
        assert source_probe.calls == []

        with pytest.raises(AttributeError):
            completion.fenced_launch_count = original_count + 1
        with pytest.raises(TypeError):
            HipFgmresGlobalRecurrenceCompletionCapabilityV1()
        with pytest.raises(TypeError):
            HipFgmresCompletionExportExecutionContextV1()

        source_export_context = open_hip_fgmres_completion_export_context_v1(
            source_stack["global"].context,
            completion,
        ).context
        assert source_export_context.receipt().status == "context_ready"
    finally:
        if source_export_context is not None and not source_export_context.closed:
            source_export_context.close()
        if target_stack is not None:
            _close_stack(target_stack)
        _close_stack(source_stack)


@pytest.mark.parametrize("failure_at", (1, 2, 3))
def test_blocking_copy_failure_is_fail_closed_and_never_publishes_partial_result(
    monkeypatch: pytest.MonkeyPatch,
    failure_at: int,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    export_context = None
    try:
        completion = _fence_global(stack)
        sources, _ = _seed_completion_sources(stack)
        probe = _BlockingCopyProbe(fail_at=failure_at)
        probe.install(monkeypatch, stack["runtime"])
        global_before = stack["global"].context.receipt()
        opened = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        )
        export_context = opened.context

        with pytest.raises(HipFgmresCompletionExportV1Error) as failed:
            export_context.export()
        assert failed.value.code == "hip_fgmres_completion_export_copy_failed"
        assert failed.value.path == f"/export/{SOURCE_ROLES[failure_at - 1]}"
        assert failed.value.cleanup_owner is export_context
        assert export_context.result is None
        assert export_context._publication is None
        receipt = export_context.receipt()
        validate_hip_fgmres_completion_export_receipt_v1(
            receipt,
            expected_context=export_context,
        )
        attempted_sources = sources[:failure_at]
        succeeded_sources = sources[: failure_at - 1]
        assert receipt.status == "poisoned"
        assert receipt.telemetry.completion_capability_consume_count == 1
        assert receipt.telemetry.d2h_operation_attempt_count == failure_at
        assert receipt.telemetry.d2h_operation_success_count == failure_at - 1
        assert receipt.telemetry.d2h_bytes_attempted == sum(
            source.nbytes for source in attempted_sources
        )
        assert receipt.telemetry.d2h_bytes_succeeded == sum(
            source.nbytes for source in succeeded_sources
        )
        assert receipt.telemetry.blocking_copy_completion_count == failure_at - 1
        assert not receipt.claims.raw_completion_buffers_host_materialized
        assert not receipt.claims.immutable_detached_host_payload
        assert receipt.payload_hash == "sha256:" + "0" * 64
        assert len(probe.calls) == failure_at

        with pytest.raises(HipFgmresCompletionExportV1Error) as retry:
            export_context.export()
        assert retry.value.code == "hip_fgmres_completion_export_state_invalid"
        assert export_context.result is None
        assert len(probe.calls) == failure_at
        assert stack["global"].context.receipt() == global_before
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)


def test_completion_export_schema_and_result_are_strict_and_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    export_context = None
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        export_context = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        ).context
        result = export_context.export()
        receipt = result.receipt

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(receipt.to_dict())
        root_extra = receipt.to_dict()
        root_extra["unexpected"] = True
        with pytest.raises(ValidationError):
            validator.validate(root_extra)
        nested_extra = receipt.to_dict()
        nested_extra["bindings"]["unexpected"] = True
        with pytest.raises(ValidationError):
            validator.validate(nested_extra)

        validate_hip_fgmres_completion_export_result_v1(
            result,
            expected_context=export_context,
        )
        assert result.to_manifest() == receipt.to_dict()
        assert result.solution_x_array.dtype.str == "<f8"
        assert result.true_residual_array.dtype.str == "<f8"
        assert result.solve_record_array.dtype.str == "|u1"
        assert result.solution_x_array.shape == (receipt.dimensions.free_dof_count,)
        assert result.true_residual_array.shape == (receipt.dimensions.free_dof_count,)
        assert result.solve_record_array.shape == (
            receipt.dimensions.solve_record_byte_count,
        )
        for array in (
            result.solution_x_array,
            result.true_residual_array,
            result.solve_record_array,
        ):
            assert array.flags.c_contiguous
            assert not array.flags.writeable
            assert type(array.base) is bytes
            with pytest.raises(ValueError):
                array[0] = 0

        with pytest.raises(FrozenInstanceError):
            result.payload_hash = "sha256:" + "0" * 64
        with pytest.raises(FrozenInstanceError):
            receipt.status = "poisoned"
        tampered = replace(
            result,
            solution_x=bytes([result.solution_x[0] ^ 0xFF]) + result.solution_x[1:],
        )
        with pytest.raises(HipFgmresCompletionExportV1Error) as invalid_payload:
            validate_hip_fgmres_completion_export_result_v1(tampered)
        assert invalid_payload.value.code == (
            "hip_fgmres_completion_export_result_payload_invalid"
        )

        forged_claims = _receipt_with_recomputed_hash(
            receipt,
            claims=replace(receipt.claims, solution_ready=True),
        )
        with pytest.raises(HipFgmresCompletionExportV1Error) as invalid_claim:
            validate_hip_fgmres_completion_export_receipt_v1(forged_claims)
        assert invalid_claim.value.code in {
            "hip_fgmres_completion_export_receipt_schema_invalid",
            "hip_fgmres_completion_export_receipt_semantic_invalid",
        }

        for field in (
            "completion_capability_reservation_count",
            "completion_capability_consume_count",
        ):
            bool_as_integer = _receipt_with_recomputed_hash(
                receipt,
                telemetry=replace(
                    receipt.telemetry,
                    **{field: True},
                ),
            )
            with pytest.raises(HipFgmresCompletionExportV1Error) as invalid_type:
                validate_hip_fgmres_completion_export_receipt_v1(bool_as_integer)
            assert invalid_type.value.code == (
                "hip_fgmres_completion_export_receipt_type_invalid"
            )

        zero_hash = "sha256:" + "0" * 64
        impossible_prefix = _receipt_with_recomputed_hash(
            receipt,
            status="poisoned",
            reason=completion_export_module.HipFgmresCompletionExportReasonV1(
                "injected_impossible_prefix",
                "three failed attempts cannot have zero completed prefix copies",
            ),
            buffers=tuple(
                replace(row, payload_sha256=zero_hash) for row in receipt.buffers
            ),
            telemetry=replace(
                receipt.telemetry,
                d2h_operation_success_count=0,
                d2h_bytes_succeeded=0,
                blocking_copy_completion_count=0,
            ),
            claims=replace(
                receipt.claims,
                raw_completion_buffers_host_materialized=False,
                blocking_completion_only_d2h=False,
                immutable_detached_host_payload=False,
            ),
            payload_hash=zero_hash,
        )
        with pytest.raises(HipFgmresCompletionExportV1Error) as invalid_prefix:
            validate_hip_fgmres_completion_export_receipt_v1(impossible_prefix)
        assert invalid_prefix.value.code == (
            "hip_fgmres_completion_export_receipt_semantic_invalid"
        )
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        _close_stack(stack)
