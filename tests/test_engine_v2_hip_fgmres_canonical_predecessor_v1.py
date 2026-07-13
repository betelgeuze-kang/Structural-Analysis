from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2 import (
    HipFgmresCanonicalPredecessorCapabilityV1,
    HipFgmresCanonicalPredecessorPendingV1,
    HipFgmresCanonicalPredecessorV1Error,
    open_hip_fgmres_canonical_predecessor_context_v1,
    validate_hip_fgmres_canonical_predecessor_capability_v1,
    validate_hip_fgmres_canonical_predecessor_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    _receipt_payload,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _open_live,
)
from tests.test_engine_v2_hip_fgmres_context_v2 import BoundFakeLoadedRuntime


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/hip_fgmres_canonical_predecessor_v1.schema.json"
)


def _open(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    values = _open_live(monkeypatch)
    live = values[-1]
    assert live.context is not None
    opened = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
    return (*values, opened)


def _close(values: tuple[Any, ...]) -> None:
    (
        _,
        parent_open,
        resident_open,
        free_open,
        _,
        primitives_open,
        _,
        _,
        live,
        canonical,
    ) = values
    if not canonical.context.closed:
        canonical.context.close()
    _cleanup(live, primitives_open, free_open, resident_open, parent_open)


def test_canonical_predecessor_fences_exact_schedule_without_host_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, live, canonical = values
    context = canonical.context
    try:
        assert canonical.ready
        opening = canonical.receipt
        validate_hip_fgmres_canonical_predecessor_receipt_v1(
            opening, expected_context=context
        )
        assert opening.status == "context_ready"
        assert opening.actual_backend == "test_double"
        assert opening.dimensions.persistent_capability_count == 11
        assert opening.dimensions.delegated_operator_capability_count == 3
        assert opening.dimensions.delegated_workspace_capability_count == 2
        assert opening.dimensions.physical_capability_count == 16
        assert opening.projection.additional_allocation_count == 0
        assert opening.admitted_mask_domain == (0, 1792, 7936)
        assert not opening.claims.canonical_producer_prefix_fenced
        assert not opening.claims.actual_mask_host_observed

        pending = context.enqueue_canonical_predecessor()
        stages = opening.dimensions.reduction_stage_count
        expected_kernels = 27 + 14 * stages
        expected_operations = 8 + expected_kernels
        assert type(pending) is HipFgmresCanonicalPredecessorPendingV1
        assert pending.attempted_operation_count == expected_operations
        assert pending.accepted_operation_lower_bound == expected_operations
        assert pending.accepted_operation_upper_bound == expected_operations
        assert kernel.pending_stream_count == 1

        capability = context.synchronize_canonical_predecessor(pending)
        assert type(capability) is HipFgmresCanonicalPredecessorCapabilityV1
        assert (
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability, expected_context=context
            )
            is capability
        )
        assert capability.mask_domain == (0, 1792, 7936)
        assert kernel.pending_stream_count == 0
        receipt = context.receipt()
        validate_hip_fgmres_canonical_predecessor_receipt_v1(
            receipt, expected_context=context
        )
        assert receipt.status == "predecessor_fenced"
        assert receipt.telemetry.memset_attempt_count == 8
        assert receipt.telemetry.kernel_launch_attempt_count == expected_kernels
        assert receipt.telemetry.async_operation_attempt_count == expected_operations
        assert receipt.telemetry.consumed_operation_count == expected_operations
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.d2h_operation_count == 0
        assert receipt.claims.owned_content_initialized
        assert receipt.claims.canonical_producer_prefix_fenced
        assert receipt.claims.device_mask_domain_gate_bound
        assert not receipt.claims.device_validation_outcome_host_observed
        assert not receipt.claims.authoritative_predecessor_proven
        assert not receipt.claims.checkpoint_transaction_ready
        assert not receipt.claims.invalid_source_destination_atomicity_proven
        assert live.context is not None
        assert live.context.receipt().telemetry.kernel_launch_count == 0
    finally:
        _close(values)


def test_live_close_is_blocked_until_canonical_child_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, live, canonical = values
    assert live.context is not None
    try:
        with pytest.raises(Exception) as blocked:
            live.context.close()
        assert getattr(blocked.value, "code", "") == (
            "hip_fgmres_live_checkpoint_canonical_child_active"
        )
        canonical.context.close()
        live.context.close()
        assert live.context.closed
    finally:
        _close(values)


def test_enqueue_is_single_use_under_two_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, canonical = values
    context = canonical.context
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(context.enqueue_canonical_predecessor) for _ in range(2)
            ]
        results: list[Any] = []
        errors: list[BaseException] = []
        for future in futures:
            try:
                results.append(future.result())
            except BaseException as exc:
                errors.append(exc)
        assert len(results) == 1
        assert len(errors) == 1
        assert getattr(errors[0], "code", "") == (
            "hip_fgmres_canonical_predecessor_state_invalid"
        )
        context.synchronize_canonical_predecessor(results[0])
    finally:
        _close(values)


def test_foreign_and_mutated_pending_capabilities_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _open(monkeypatch)
    second = _open(monkeypatch)
    first_context = first[-1].context
    second_context = second[-1].context
    try:
        first_pending = first_context.enqueue_canonical_predecessor()
        second_pending = second_context.enqueue_canonical_predecessor()
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as foreign:
            first_context.synchronize_canonical_predecessor(second_pending)
        assert foreign.value.code == "hip_fgmres_canonical_predecessor_pending_invalid"
        object.__setattr__(
            first_pending,
            "attempted_operation_count",
            first_pending.attempted_operation_count + 1,
        )
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as changed:
            first_context.synchronize_canonical_predecessor(first_pending)
        assert changed.value.code == "hip_fgmres_canonical_predecessor_pending_invalid"
        object.__setattr__(
            first_pending,
            "attempted_operation_count",
            first_pending.attempted_operation_count - 1,
        )
        first_context.synchronize_canonical_predecessor(first_pending)
        second_context.synchronize_canonical_predecessor(second_pending)
    finally:
        _close(second)
        _close(first)


def test_capability_validator_rejects_mutation_and_stale_after_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, canonical = values
    context = canonical.context
    try:
        pending = context.enqueue_canonical_predecessor()
        capability = context.synchronize_canonical_predecessor(pending)
        original_mask_domain = capability.mask_domain
        object.__setattr__(capability, "mask_domain", (0, 1792))
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as mutated:
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability, expected_context=context
            )
        assert mutated.value.code == (
            "hip_fgmres_canonical_predecessor_capability_invalid"
        )
        object.__setattr__(capability, "mask_domain", original_mask_domain)
        assert (
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability, expected_context=context
            )
            is capability
        )

        context.close()
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as stale:
            validate_hip_fgmres_canonical_predecessor_capability_v1(
                capability, expected_context=context
            )
        assert stale.value.code == (
            "hip_fgmres_canonical_predecessor_capability_invalid"
        )
    finally:
        _close(values)


def test_first_memset_rejection_is_exact_no_work_and_ignores_public_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_bind = BoundFakeLoadedRuntime.bind
    memset_calls = 0

    def reject_first_memset(*_arguments: Any) -> int:
        nonlocal memset_calls
        memset_calls += 1
        return 7

    def bind(
        runtime: BoundFakeLoadedRuntime,
        symbol: str,
        argtypes: Any,
        restype: Any,
    ) -> Any:
        if symbol == "hipMemsetAsync":
            return reject_first_memset
        return original_bind(runtime, symbol, argtypes, restype)

    monkeypatch.setattr(BoundFakeLoadedRuntime, "bind", bind)
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    kernel_type = type(kernel)
    original_pending_property = kernel_type.pending_stream_count
    public_pending_reads = 0

    def misleading_public_pending(_kernel: Any) -> int:
        nonlocal public_pending_reads
        public_pending_reads += 1
        return 0 if public_pending_reads == 1 else 1

    monkeypatch.setattr(
        kernel_type,
        "pending_stream_count",
        property(misleading_public_pending),
    )
    try:
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as failed:
            context.enqueue_canonical_predecessor()
        assert failed.value.code == "hip_fgmres_canonical_predecessor_enqueue_failed"
        assert failed.value.pending is not None
        assert failed.value.pending.attempted_operation_count == 1
        assert failed.value.pending.accepted_operation_lower_bound == 0
        assert failed.value.pending.accepted_operation_upper_bound == 0
        receipt = context.receipt()
        assert receipt.status == "poisoned_no_work"
        assert receipt.telemetry.memset_attempt_count == 1
        assert receipt.telemetry.memset_accept_lower_bound == 0
        assert receipt.telemetry.memset_accept_upper_bound == 0
        assert receipt.telemetry.kernel_launch_attempt_count == 0
        assert receipt.telemetry.fence_attempt_count == 0
        assert memset_calls == 1
        assert public_pending_reads == 1
    finally:
        monkeypatch.setattr(
            kernel_type,
            "pending_stream_count",
            original_pending_property,
        )
        assert (
            kernel._checkpoint_pending_stream_count(context._live_checkpoint_token())
            == 0
        )
        _close(values)


def test_projection_drift_before_enqueue_keeps_ready_no_work_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    loaded = kernel._runtime._runtime
    assert context._projection is not None
    context._projection = replace(context._projection)
    try:
        with pytest.raises(Exception) as failed:
            context.enqueue_canonical_predecessor()
        assert getattr(failed.value, "code", "") == (
            "hip_krylov_primitives_fgmres_producer_projection_invalid"
        )
        receipt = context.receipt()
        assert receipt.status == "context_ready"
        assert context._pending is None
        assert receipt.telemetry.async_operation_attempt_count == 0
        assert receipt.telemetry.async_operation_accept_lower_bound == 0
        assert receipt.telemetry.async_operation_accept_upper_bound == 0
        assert receipt.telemetry.fence_attempt_count == 0
        assert kernel.pending_stream_count == 0
        assert loaded.sync_streams == []

        context.close()
        assert context.closed
    finally:
        _close(values)


def test_ambiguous_first_kernel_has_bounded_prefix_and_no_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    loaded = kernel._runtime._runtime
    loaded.launch_exception = True
    try:
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as failed:
            context.enqueue_canonical_predecessor()
        assert failed.value.code == "hip_fgmres_canonical_predecessor_enqueue_failed"
        pending = failed.value.pending
        assert pending is not None
        assert pending.attempted_operation_count == 9
        assert pending.accepted_operation_lower_bound == 8
        assert pending.accepted_operation_upper_bound == 9
        receipt = context.receipt()
        assert receipt.status == "poisoned_pending_fence"
        assert receipt.telemetry.memset_accept_lower_bound == 8
        assert receipt.telemetry.memset_accept_upper_bound == 8
        assert receipt.telemetry.kernel_launch_attempt_count == 1
        assert receipt.telemetry.kernel_launch_accept_lower_bound == 0
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 1
        assert len(loaded.launch_records) == 1
        assert kernel.pending_stream_count == 1

        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as poisoned:
            context.synchronize_canonical_predecessor(pending)
        assert poisoned.value.code == "hip_fgmres_canonical_predecessor_poisoned"
        terminal = context.receipt()
        assert terminal.status == "poisoned_fenced"
        assert terminal.telemetry.consumed_operation_count == 9
        assert terminal.telemetry.fence_success_count == 1
        assert not terminal.claims.canonical_producer_prefix_fenced
        assert kernel.pending_stream_count == 0
    finally:
        _close(values)


@pytest.mark.parametrize("failure_position", ("before_pop", "after_pop"))
def test_fence_observed_consume_retry_does_not_refence_or_double_consume(
    monkeypatch: pytest.MonkeyPatch,
    failure_position: str,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    loaded = kernel._runtime._runtime
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    consume_calls = 0
    raw_consumed: list[int] = []

    def interrupted_consume(
        owner: Any,
        token: object,
        stream: Any,
    ) -> int:
        nonlocal consume_calls
        consume_calls += 1
        if failure_position == "before_pop" and consume_calls == 1:
            raise RuntimeError("injected pre-consume interruption")
        consumed = int(original_consume(owner, token, stream))
        raw_consumed.append(consumed)
        if failure_position == "after_pop" and consume_calls == 1:
            raise RuntimeError("injected post-consume interruption")
        return consumed

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        interrupted_consume,
    )
    try:
        pending = context.enqueue_canonical_predecessor()
        expected_operations = pending.accepted_operation_lower_bound
        assert expected_operations == pending.accepted_operation_upper_bound
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as failed:
            context.synchronize_canonical_predecessor(pending)
        assert failed.value.code == (
            "hip_fgmres_canonical_predecessor_pending_consume_failed"
        )
        assert failed.value.pending is pending
        retry = context.receipt()
        assert retry.status == "fence_observed_ack_pending"
        assert retry.telemetry.fence_attempt_count == 1
        assert retry.telemetry.fence_success_count == 1
        assert retry.telemetry.pending_consume_attempt_count == 1
        assert len(loaded.sync_streams) == 1
        assert kernel.pending_stream_count == (
            1 if failure_position == "before_pop" else 0
        )

        capability = context.synchronize_canonical_predecessor(pending)
        assert context.synchronize_canonical_predecessor(pending) is capability
        fenced = context.receipt()
        assert fenced.status == "predecessor_fenced"
        assert fenced.telemetry.fence_attempt_count == 1
        assert fenced.telemetry.fence_success_count == 1
        assert fenced.telemetry.pending_consume_attempt_count == 2
        assert fenced.telemetry.consumed_operation_count == expected_operations
        assert consume_calls == 2
        assert len(loaded.sync_streams) == 1
        assert kernel.pending_stream_count == 0
        if failure_position == "before_pop":
            assert raw_consumed == [expected_operations]
        else:
            assert raw_consumed == [expected_operations, 0]
    finally:
        _close(values)


def test_partial_rejected_kernel_poison_is_fenced_before_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    loaded = kernel._runtime._runtime
    loaded.launch_status = 7
    try:
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as failed:
            context.enqueue_canonical_predecessor()
        assert failed.value.code == "hip_fgmres_canonical_predecessor_enqueue_failed"
        assert failed.value.pending is not None
        receipt = context.receipt()
        assert receipt.status == "poisoned_pending_fence"
        assert receipt.telemetry.memset_accept_lower_bound == 8
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 0
        assert kernel.pending_stream_count == 1
        context.close()
        assert kernel.pending_stream_count == 0
    finally:
        _close(values)


def test_fence_failure_retains_pending_and_retries_without_reenqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, kernel, _, canonical = values
    context = canonical.context
    loaded = kernel._runtime._runtime
    pending = context.enqueue_canonical_predecessor()
    loaded.sync_fail_count = 1
    try:
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as failed:
            context.synchronize_canonical_predecessor(pending)
        assert failed.value.code == "hip_fgmres_canonical_predecessor_fence_failed"
        assert kernel.pending_stream_count == 1
        capability = context.synchronize_canonical_predecessor(pending)
        assert capability.context_id == context.receipt().context_id
        assert kernel.pending_stream_count == 0
        assert context.receipt().telemetry.fence_attempt_count == 2
        assert context.receipt().telemetry.fence_success_count == 1
    finally:
        _close(values)


def test_receipt_schema_and_semantic_forgery_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _open(monkeypatch)
    *_, canonical = values
    context = canonical.context
    try:
        pending = context.enqueue_canonical_predecessor()
        context.synchronize_canonical_predecessor(pending)
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
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error):
            validate_hip_fgmres_canonical_predecessor_receipt_v1(forged)
        relabeled = replace(receipt, actual_backend="hip")
        relabeled = replace(
            relabeled,
            receipt_hash=canonical_hash(
                _receipt_payload(relabeled, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error):
            validate_hip_fgmres_canonical_predecessor_receipt_v1(
                relabeled, expected_context=context
            )
        inconsistent_telemetry = replace(
            receipt,
            telemetry=replace(
                receipt.telemetry,
                kernel_launch_attempt_count=(
                    receipt.telemetry.kernel_launch_attempt_count - 1
                ),
            ),
        )
        inconsistent_telemetry = replace(
            inconsistent_telemetry,
            receipt_hash=canonical_hash(
                _receipt_payload(inconsistent_telemetry, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as telemetry:
            validate_hip_fgmres_canonical_predecessor_receipt_v1(inconsistent_telemetry)
        assert telemetry.value.code == (
            "hip_fgmres_canonical_predecessor_telemetry_invalid"
        )
        inconsistent_schedule = replace(
            receipt,
            bindings=replace(
                receipt.bindings,
                canonical_schedule_hash=canonical_hash({"forged": True}),
            ),
        )
        inconsistent_schedule = replace(
            inconsistent_schedule,
            receipt_hash=canonical_hash(
                _receipt_payload(inconsistent_schedule, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresCanonicalPredecessorV1Error) as schedule:
            validate_hip_fgmres_canonical_predecessor_receipt_v1(inconsistent_schedule)
        assert schedule.value.code == (
            "hip_fgmres_canonical_predecessor_schedule_hash_invalid"
        )
    finally:
        _close(values)


def test_capability_types_are_not_publicly_constructible() -> None:
    with pytest.raises(TypeError):
        HipFgmresCanonicalPredecessorPendingV1()
    with pytest.raises(TypeError):
        HipFgmresCanonicalPredecessorCapabilityV1()
