from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import dis
import gc
import json
from pathlib import Path
import sys
from typing import Any
import weakref

import pytest
from jsonschema import Draft202012Validator, ValidationError

from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceCompletionCapabilityV1,
    HipFgmresGlobalRecurrencePendingV1,
    HipFgmresGlobalRecurrenceV1Error,
    _launch_values,
    _receipt_payload,
    open_hip_fgmres_global_recurrence_context_v1,
    validate_hip_fgmres_global_recurrence_completion_capability_v1,
    validate_hip_fgmres_global_recurrence_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _prepare_live_inputs,
)


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "structural_analysis"
    / "schemas"
    / "hip_fgmres_global_recurrence_context_v1.schema.json"
)


class _InjectedOpcodeInterruption(KeyboardInterrupt):
    pass


def _interrupt_immediately_after_store_attr(
    target: Any,
    attribute: str,
    operation: Any,
) -> None:
    """Raise at the first opcode boundary after one exact STORE_ATTR."""

    code = target.__code__
    offsets = {
        instruction.offset
        for instruction in dis.get_instructions(target)
        if instruction.opname == "STORE_ATTR" and instruction.argval == attribute
    }
    assert offsets, f"no STORE_ATTR {attribute!r} in {target.__qualname__}"
    armed = False
    previous_trace = sys.gettrace()

    def trace(frame: Any, event: str, _argument: Any) -> Any:
        nonlocal armed
        if frame.f_code is code:
            frame.f_trace_opcodes = True
            if event == "opcode":
                if armed:
                    raise _InjectedOpcodeInterruption(
                        f"interrupted after STORE_ATTR {attribute}"
                    )
                if frame.f_lasti in offsets:
                    armed = True
            return trace
        return trace

    sys.settrace(trace)
    try:
        operation()
    finally:
        sys.settrace(previous_trace)


def _open_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    restart_dimension: int = 1,
    max_iterations: int = 1,
) -> dict[str, Any]:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        primitive_open,
        _,
        kernel,
        loaded,
    ) = _prepare_live_inputs(monkeypatch)
    primitive = primitive_open.context
    assert primitive is not None
    policy = compile_fgmres_policy_v1(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
    )
    source_plan = compile_hip_fgmres_plan_v1(
        primitive._parent._plan,
        primitive._parent._overlay,
        policy,
    )
    recurrence = compile_hip_fgmres_recurrence_plan_v2(source_plan)
    live = open_hip_fgmres_live_checkpoint_context_v1(
        primitive,
        source_apply,
        recurrence,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    canonical = sealed = global_open = None
    try:
        assert live.context is not None
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        canonical_pending = canonical.context.enqueue_canonical_predecessor()
        canonical_capability = canonical.context.synchronize_canonical_predecessor(
            canonical_pending
        )
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical.context,
            canonical_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        baseline = len(loaded.launch_records)
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        return {
            "runtime": runtime,
            "parent_open": parent_open,
            "resident_open": resident_open,
            "free_open": free_open,
            "primitive_open": primitive_open,
            "kernel": kernel,
            "loaded": loaded,
            "live": live,
            "canonical": canonical,
            "sealed": sealed,
            "continuation": continuation,
            "global": global_open,
            "baseline": baseline,
        }
    except BaseException:
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)
        raise


def _close_stack(stack: dict[str, Any]) -> None:
    global_open = stack.get("global")
    sealed = stack["sealed"]
    canonical = stack["canonical"]
    if global_open is not None and not global_open.context.closed:
        global_open.context.close()
    if not sealed.context.closed:
        sealed.context.close()
    if not canonical.context.closed:
        canonical.context.close()
    _cleanup(
        stack["live"],
        stack["primitive_open"],
        stack["free_open"],
        stack["resident_open"],
        stack["parent_open"],
    )


def _assert_record_matches_launch(
    record: dict[str, Any],
    launch: Any,
    *,
    free_dof_count: int,
    reduced_csr_nnz: int,
) -> None:
    assert record["symbol"] == launch.kernel_symbol
    arguments = record["arguments"]
    if launch.submission_kind == "control":
        assert arguments[:6] == (
            launch.mode,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            launch.row_index,
            launch.pass_index,
        )
    elif launch.submission_kind == "vector":
        assert arguments[:7] == (
            launch.mode,
            launch.vector_gate,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            free_dof_count,
            launch.logical_index,
        )
    elif launch.submission_kind == "spmv":
        assert arguments[:7] == (
            launch.mode,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            free_dof_count,
            reduced_csr_nnz,
            launch.logical_index,
        )
    else:
        assert launch.submission_kind == "reduction"
        assert arguments[:8] == (
            launch.mode,
            launch.reduction_target,
            launch.expected_schedule_epoch,
            launch.expected_restart,
            launch.expected_column,
            launch.expected_reduction_epoch,
            launch.value_count,
            launch.logical_index,
        )


def test_global_recurrence_submits_exact_suffix_and_fences_without_new_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    context = stack["global"].context
    opening = stack["global"].receipt
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    partition = compile_hip_fgmres_global_sealed_continuation_v1(
        opening.dimensions.free_dof_count,
        opening.dimensions.restart_dimension,
        opening.dimensions.max_iterations,
    )
    allocation_count = stack["runtime"].malloc_calls
    module_load_count = loaded.load_calls
    sync_count = len(loaded.sync_streams)
    try:
        validate_hip_fgmres_global_recurrence_receipt_v1(
            opening,
            expected_context=context,
        )
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_validator = Draft202012Validator(schema)
        schema_validator.validate(opening.to_dict())
        root_extra = opening.to_dict()
        root_extra["unexpected"] = True
        with pytest.raises(ValidationError):
            schema_validator.validate(root_extra)
        nested_extra = opening.to_dict()
        nested_extra["bindings"]["unexpected"] = True
        with pytest.raises(ValidationError):
            schema_validator.validate(nested_extra)
        assert opening.status == "context_ready"
        assert opening.dimensions.continuation_launch_count == 35
        assert opening.bindings.continuation_schedule_hash == (
            partition.continuation.canonical_sha256
        )
        assert opening.projection.additional_allocation_count == 0
        assert opening.projection.additional_borrow_count == 0
        assert opening.projection.additional_checkpoint_owner_count == 0
        assert opening.projection.additional_module_load_count == 0
        assert opening.telemetry.h2d_operation_count == 0
        assert opening.telemetry.d2h_operation_count == 0
        assert opening.telemetry.intermediate_sync_count == 0
        assert not opening.claims.actual_terminal_outcome_host_observed
        assert not opening.claims.numerical_parity_verified
        assert not opening.claims.solution_ready
        assert not opening.claims.commercial_ready

        pending = context.enqueue_remaining_global_recurrence()
        assert type(pending) is HipFgmresGlobalRecurrencePendingV1
        assert pending.attempted_launch_count == len(partition.continuation.launches)
        assert pending.accepted_launch_count_lower_bound == len(
            partition.continuation.launches
        )
        assert pending.accepted_launch_count_upper_bound == len(
            partition.continuation.launches
        )
        assert context._require_binding().launch_values == _launch_values(
            partition.continuation.launches
        )
        records = loaded.launch_records[stack["baseline"] :]
        assert len(records) == len(partition.continuation.launches)
        for record, launch in zip(records, partition.continuation.launches):
            assert record["stream"] == live._stream_pointer_snapshot
            _assert_record_matches_launch(
                record,
                launch,
                free_dof_count=opening.dimensions.free_dof_count,
                reduced_csr_nnz=opening.dimensions.reduced_csr_nnz,
            )

        pointers = dict(context._require_binding().pointer_values)
        stages: dict[str, int] = {}
        for record, launch in zip(records, partition.continuation.launches):
            if launch.submission_kind != "reduction":
                continue
            stage = stages.get(launch.reduction_tree_id, 0)
            expected_input = pointers[
                "reduction_ping" if stage % 2 == 0 else "reduction_pong"
            ]
            expected_output = pointers[
                "reduction_pong" if stage % 2 == 0 else "reduction_ping"
            ]
            assert record["arguments"][-4:-2] == (
                expected_input,
                expected_output,
            )
            stages[launch.reduction_tree_id] = stage + 1

        assert stack["runtime"].malloc_calls == allocation_count
        assert loaded.load_calls == module_load_count
        assert len(loaded.sync_streams) == sync_count
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == (
            (live._stream_pointer_snapshot, len(partition.continuation.launches)),
        )

        completion = context.synchronize(pending)
        assert type(completion) is HipFgmresGlobalRecurrenceCompletionCapabilityV1
        assert (
            validate_hip_fgmres_global_recurrence_completion_capability_v1(
                completion,
                expected_context=context,
            )
            is completion
        )
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == ()
        assert len(loaded.sync_streams) == sync_count + 1
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        schema_validator.validate(receipt.to_dict())
        assert receipt.status == "recurrence_fenced"
        assert receipt.telemetry.continuation_capability_consume_count == 1
        assert receipt.telemetry.kernel_launch_attempt_count == 35
        assert receipt.telemetry.consumed_launch_count == 35
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        assert receipt.claims.fixed_suffix_fenced
        assert receipt.claims.completion_capability_issued
        assert receipt.claims.no_live_state_host_read_or_branch
        assert not receipt.claims.actual_terminal_outcome_host_observed

        with pytest.raises(Exception) as parent_blocked:
            stack["sealed"].context.close()
        assert getattr(parent_blocked.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_global_child_active"
        )
    finally:
        _close_stack(stack)


def test_submission_loop_has_constant_deep_checks_and_atomic_linear_pending_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def measure(max_iterations: int) -> tuple[int, int, int, int, tuple[int, ...]]:
        stack = _open_stack(
            monkeypatch,
            restart_dimension=1,
            max_iterations=max_iterations,
        )
        context = stack["global"].context
        kernel = stack["kernel"]
        launch_count = stack["global"].receipt.dimensions.continuation_launch_count
        context_type = type(context)
        kernel_type = type(kernel)
        identity_type = type(kernel.identity)
        original_deep = context_type._require_current_binding
        original_snapshot = kernel_type._checkpoint_pending_snapshot
        original_launch = kernel_type._launch
        original_identity_to_dict = identity_type.to_dict
        deep_calls = 0
        snapshot_calls = 0
        identity_to_dict_calls = 0
        expected_prior_counts: list[int] = []

        def counted_deep(owner: Any, **keywords: Any) -> None:
            nonlocal deep_calls
            if owner is context:
                deep_calls += 1
            original_deep(owner, **keywords)

        def counted_snapshot(owner: Any, token: object) -> Any:
            nonlocal snapshot_calls
            if owner is kernel:
                snapshot_calls += 1
            return original_snapshot(owner, token)

        def counted_launch(
            owner: Any,
            function_name: str,
            **keywords: Any,
        ) -> None:
            if owner is kernel:
                expected = keywords["checkpoint_expected_prior_pending_count"]
                assert type(expected) is int
                expected_prior_counts.append(expected)
            original_launch(owner, function_name, **keywords)

        def counted_identity_to_dict(identity: Any) -> dict[str, Any]:
            nonlocal identity_to_dict_calls
            if identity is kernel.identity:
                identity_to_dict_calls += 1
            return original_identity_to_dict(identity)

        pending = None
        try:
            with monkeypatch.context() as patch:
                patch.setattr(
                    context_type,
                    "_require_current_binding",
                    counted_deep,
                )
                patch.setattr(
                    kernel_type,
                    "_checkpoint_pending_snapshot",
                    counted_snapshot,
                )
                patch.setattr(kernel_type, "_launch", counted_launch)
                patch.setattr(identity_type, "to_dict", counted_identity_to_dict)
                pending = context.enqueue_remaining_global_recurrence()
            context.synchronize(pending)
            return (
                launch_count,
                deep_calls,
                snapshot_calls,
                identity_to_dict_calls,
                tuple(expected_prior_counts),
            )
        finally:
            _close_stack(stack)

    short = measure(1)
    long = measure(2)
    assert short[0] == 1
    assert long[0] == 35
    assert short[1] == long[1] == 2
    assert short[2] == long[2]
    assert short[3] == long[3] == 0
    assert short[4] == tuple(range(short[0]))
    assert long[4] == tuple(range(long[0]))


def test_dispatch_uses_validated_immutable_row_and_resource_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    context = stack["global"].context
    binding = context._require_binding()
    first = binding.launches[0]
    alternate = next(
        row
        for row in binding.launches[1:]
        if row.submission_kind == "control"
        and row.mode != first.mode
        and row.expected_schedule_epoch != first.expected_schedule_epoch
    )
    original_pointer_values = binding.pointer_values
    pointer_map = dict(original_pointer_values)
    forged_pointer_values = tuple(
        (
            role,
            pointer + 1_048_576 if role == "packed_dense_state" else pointer,
        )
        for role, pointer in original_pointer_values
    )
    first_fields = (
        "mode",
        "expected_schedule_epoch",
        "expected_restart",
        "expected_column",
        "row_index",
        "pass_index",
    )
    original_first_values = tuple(getattr(first, name) for name in first_fields)
    alternate_values = tuple(getattr(alternate, name) for name in first_fields)
    context_type = type(context)
    original_dispatch = context_type._dispatch
    fired = False

    def dispatch_during_transient_drift(
        owner: Any,
        submission: Any,
        launch: Any,
        scratch_stage: dict[str, int],
        *,
        expected_prior_pending_count: int,
    ) -> None:
        nonlocal fired
        if not fired:
            fired = True
            for name, value in zip(first_fields, alternate_values):
                object.__setattr__(first, name, value)
            object.__setattr__(binding, "pointer_values", forged_pointer_values)
            try:
                original_dispatch(
                    owner,
                    submission,
                    launch,
                    scratch_stage,
                    expected_prior_pending_count=expected_prior_pending_count,
                )
            finally:
                object.__setattr__(binding, "pointer_values", original_pointer_values)
                for name, value in zip(first_fields, original_first_values):
                    object.__setattr__(first, name, value)
            return
        original_dispatch(
            owner,
            submission,
            launch,
            scratch_stage,
            expected_prior_pending_count=expected_prior_pending_count,
        )

    try:
        monkeypatch.setattr(context_type, "_dispatch", dispatch_during_transient_drift)
        pending = context.enqueue_remaining_global_recurrence()
        assert fired
        records = stack["loaded"].launch_records[stack["baseline"] :]
        assert len(records) == pending.attempted_launch_count
        _assert_record_matches_launch(
            records[0],
            first,
            free_dof_count=binding.free_dof_count,
            reduced_csr_nnz=binding.reduced_csr_nnz,
        )
        assert records[0]["arguments"][-3:] == (
            pointer_map["packed_dense_state"],
            pointer_map["fgmres_control_state_v2"],
            pointer_map["solve_record"],
        )
        assert (
            records[0]["arguments"][-3]
            != dict(forged_pointer_values)["packed_dense_state"]
        )
        context.synchronize(pending)
        receipt = context.receipt()
        assert receipt.status == "recurrence_fenced"
        assert receipt.claims.fixed_suffix_fenced
    finally:
        _close_stack(stack)


def test_consume_return_interruption_reconciles_and_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    original = sealed._consume_global_recurrence_continuation_capability
    fired = False

    def interrupted(token: object, capability: Any) -> None:
        nonlocal fired
        original(token, capability)
        if not fired:
            fired = True
            raise RuntimeError("interrupted after shared consume")

    monkeypatch.setattr(
        sealed,
        "_consume_global_recurrence_continuation_capability",
        interrupted,
    )
    try:
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.enqueue_remaining_global_recurrence()
        assert failed.value.code == "hip_fgmres_global_recurrence_enqueue_failed"
        assert failed.value.pending is not None
        receipt = context.receipt()
        assert receipt.status == "poisoned_no_work"
        assert receipt.telemetry.continuation_capability_consume_count == 1
        assert receipt.telemetry.kernel_launch_attempt_count == 0
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 0
        assert stack["loaded"].launch_records[stack["baseline"] :] == []
    finally:
        _close_stack(stack)


@pytest.mark.parametrize("failure_kind", ["partial_rejection", "ambiguous_first"])
def test_partial_and_ambiguous_enqueue_poison_and_drain_exact_pending_prefix(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    stack = _open_stack(monkeypatch, restart_dimension=1, max_iterations=2)
    context = stack["global"].context
    loaded = stack["loaded"]
    baseline = stack["baseline"]
    if failure_kind == "partial_rejection":

        def reject_after_first(record_count: int) -> None:
            if record_count == baseline + 1:
                loaded.launch_status = 7

        loaded.launch_callback = reject_after_first
    else:
        loaded.launch_exception = True
    try:
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.enqueue_remaining_global_recurrence()
        assert failed.value.code == "hip_fgmres_global_recurrence_enqueue_failed"
        assert failed.value.pending is not None
        receipt = context.receipt()
        assert receipt.status == "poisoned_pending_fence"
        if failure_kind == "partial_rejection":
            assert receipt.telemetry.kernel_launch_attempt_count == 2
            assert receipt.telemetry.kernel_launch_accept_lower_bound == 1
            assert receipt.telemetry.kernel_launch_accept_upper_bound == 1
        else:
            assert receipt.telemetry.kernel_launch_attempt_count == 1
            assert receipt.telemetry.kernel_launch_accept_lower_bound == 0
            assert receipt.telemetry.kernel_launch_accept_upper_bound == 1
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as poisoned:
            context.synchronize(failed.value.pending)
        assert poisoned.value.code == "hip_fgmres_global_recurrence_poisoned"
        fenced = context.receipt()
        assert fenced.status == "poisoned_fenced"
        assert fenced.telemetry.fence_success_count == 1
        assert (
            stack["kernel"]._checkpoint_pending_snapshot(
                stack["live"].context._checkpoint_token
            )
            == ()
        )
    finally:
        loaded.launch_status = 0
        loaded.launch_exception = False
        loaded.launch_callback = None
        _close_stack(stack)


def test_ack_retry_never_refences_or_double_consumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    launch_count = len(loaded.launch_records)
    original_pending_mint = context._mint_pending
    pending_mint_calls = 0

    def interrupted_pending_mint() -> HipFgmresGlobalRecurrencePendingV1:
        nonlocal pending_mint_calls
        pending_mint_calls += 1
        if pending_mint_calls == 1:
            raise KeyboardInterrupt("interrupted before pending mint")
        pending_capability = original_pending_mint()
        if pending_mint_calls == 2:
            raise RuntimeError("interrupted after durable pending mint")
        return pending_capability

    monkeypatch.setattr(context, "_mint_pending", interrupted_pending_mint)
    with pytest.raises(KeyboardInterrupt, match="before pending mint"):
        context.enqueue_remaining_global_recurrence()
    unpublished = context.receipt()
    validate_hip_fgmres_global_recurrence_receipt_v1(
        unpublished,
        expected_context=context,
    )
    assert unpublished.status == "pending_publication_pending"
    assert unpublished.telemetry.kernel_launch_attempt_count == 1
    assert len(loaded.launch_records) == launch_count + 1

    with pytest.raises(RuntimeError, match="durable pending mint"):
        context.enqueue_remaining_global_recurrence()
    still_unpublished = context.receipt()
    validate_hip_fgmres_global_recurrence_receipt_v1(
        still_unpublished,
        expected_context=context,
    )
    assert still_unpublished.status == "pending_publication_pending"
    assert still_unpublished.telemetry.kernel_launch_attempt_count == 1
    assert len(loaded.launch_records) == launch_count + 1

    pending = context.enqueue_remaining_global_recurrence()
    assert context.enqueue_remaining_global_recurrence() is pending
    assert pending_mint_calls == 3
    assert context.receipt().status == "recurrence_pending"
    assert len(loaded.launch_records) == launch_count + 1
    kernel_type = type(kernel)
    original = kernel_type._consume_checkpoint_pending_after_fence
    calls = 0

    def interrupted(owner: Any, token: object, stream: Any) -> int:
        nonlocal calls
        calls += 1
        consumed = original(owner, token, stream)
        if calls == 1:
            raise RuntimeError("interrupted after pending-map pop")
        return consumed

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        interrupted,
    )
    original_mint = context._mint_completion
    mint_calls = 0

    def interrupted_mint() -> HipFgmresGlobalRecurrenceCompletionCapabilityV1:
        nonlocal mint_calls
        mint_calls += 1
        if mint_calls == 1:
            raise KeyboardInterrupt("interrupted before completion mint")
        completion = original_mint()
        if mint_calls == 2:
            raise RuntimeError("interrupted after durable completion mint")
        return completion

    monkeypatch.setattr(context, "_mint_completion", interrupted_mint)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.synchronize(pending)
        assert failed.value.code == (
            "hip_fgmres_global_recurrence_pending_consume_failed"
        )
        retryable = context.receipt()
        assert retryable.status == "fence_observed_ack_pending"
        assert retryable.telemetry.fence_attempt_count == 1
        assert retryable.telemetry.fence_success_count == 1
        assert retryable.telemetry.pending_consume_attempt_count == 1
        assert len(loaded.sync_streams) == sync_count + 1

        with pytest.raises(KeyboardInterrupt):
            context.synchronize(pending)
        publication_pending = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            publication_pending,
            expected_context=context,
        )
        assert publication_pending.status == "completion_publication_pending"
        assert publication_pending.claims.fixed_suffix_fenced
        assert not publication_pending.claims.completion_capability_issued
        assert context.completion_capability is None
        assert publication_pending.telemetry.pending_consume_attempt_count == 2
        assert len(loaded.sync_streams) == sync_count + 1

        with pytest.raises(RuntimeError, match="durable completion mint"):
            context.synchronize(pending)
        durable_pending = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            durable_pending,
            expected_context=context,
        )
        assert durable_pending.status == "completion_publication_pending"
        assert durable_pending.claims.fixed_suffix_fenced
        assert not durable_pending.claims.completion_capability_issued
        assert context.completion_capability is None
        assert durable_pending.telemetry.pending_consume_attempt_count == 2
        assert len(loaded.sync_streams) == sync_count + 1

        completion = context.synchronize(pending)
        assert completion.fenced_launch_count == 1
        fenced = context.receipt()
        assert fenced.status == "recurrence_fenced"
        assert fenced.telemetry.fence_attempt_count == 1
        assert fenced.telemetry.fence_success_count == 1
        assert fenced.telemetry.pending_consume_attempt_count == 2
        assert fenced.telemetry.consumed_launch_count == 1
        assert fenced.claims.completion_capability_issued
        assert context.completion_capability is completion
        assert mint_calls == 3
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        _close_stack(stack)


def test_reserve_and_release_return_interruptions_reconcile_exact_parent_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    first = stack["global"].context
    sealed = stack["sealed"].context
    continuation = stack["continuation"]
    parent_type = type(sealed)
    original_reserve = parent_type._reserve_global_recurrence_child
    original_release = parent_type._release_global_recurrence_child
    release_calls = 0

    def release_then_error(owner: Any, token: object) -> None:
        nonlocal release_calls
        release_calls += 1
        original_release(owner, token)
        raise RuntimeError("interrupted after child release")

    monkeypatch.setattr(
        parent_type,
        "_release_global_recurrence_child",
        release_then_error,
    )
    try:
        first.close()
        assert first.closed
        assert first._child_released
        assert sealed._global_recurrence_child_token is None
        assert release_calls == 1

        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            original_release,
        )

        lost_context: weakref.ReferenceType[Any] | None = None

        def cancel_after_successful_open() -> None:
            nonlocal lost_context
            opened = open_hip_fgmres_global_recurrence_context_v1(
                sealed,
                continuation,
            )
            lost_context = weakref.ref(opened.context)
            raise KeyboardInterrupt("cancelled before open result assignment")

        try:
            cancel_after_successful_open()
        except KeyboardInterrupt:
            pass
        gc.collect()
        assert lost_context is not None and lost_context() is None
        abandoned_reference = sealed._global_recurrence_child_token
        assert abandoned_reference is not None
        assert abandoned_reference() is None

        def reserve_then_interrupt(
            owner: Any,
            token: object,
            capability: Any,
        ) -> object:
            original_reserve(owner, token, capability)
            raise KeyboardInterrupt("interrupted after child reserve")

        monkeypatch.setattr(
            parent_type,
            "_reserve_global_recurrence_child",
            reserve_then_interrupt,
        )

        def rollback_release_then_interrupt(owner: Any, token: object) -> None:
            original_release(owner, token)
            raise KeyboardInterrupt("interrupted after open rollback child release")

        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            rollback_release_then_interrupt,
        )
        with pytest.raises(KeyboardInterrupt, match="open rollback child release"):
            open_hip_fgmres_global_recurrence_context_v1(sealed, continuation)
        assert sealed._global_recurrence_child_token is None
        assert not sealed._global_recurrence_child_terminal

        monkeypatch.setattr(
            parent_type,
            "_reserve_global_recurrence_child",
            original_reserve,
        )
        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            original_release,
        )
        reopened = open_hip_fgmres_global_recurrence_context_v1(
            sealed,
            continuation,
        )
        stack["global"] = reopened
        pending = reopened.context.enqueue_remaining_global_recurrence()
        reopened.context.synchronize(pending)

        def release_then_interrupt(owner: Any, token: object) -> None:
            original_release(owner, token)
            raise KeyboardInterrupt("interrupted after terminal child release")

        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            release_then_interrupt,
        )
        with pytest.raises(KeyboardInterrupt, match="terminal child release"):
            reopened.context.close()
        assert not reopened.context.closed
        assert reopened.context._child_released
        assert sealed._global_recurrence_child_token is None
        assert sealed._global_recurrence_child_terminal

        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            original_release,
        )
        reopened.context.close()
        assert reopened.context.closed
    finally:
        monkeypatch.setattr(
            parent_type,
            "_reserve_global_recurrence_child",
            original_reserve,
        )
        monkeypatch.setattr(
            parent_type,
            "_release_global_recurrence_child",
            original_release,
        )
        _close_stack(stack)


def test_parent_close_reaps_abandoned_unconsumed_factory_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    first = stack["global"].context
    sealed = stack["sealed"].context
    continuation = stack["continuation"]
    lost_context: weakref.ReferenceType[Any] | None = None
    try:
        first.close()

        def cancel_after_successful_open() -> None:
            nonlocal lost_context
            opened = open_hip_fgmres_global_recurrence_context_v1(
                sealed,
                continuation,
            )
            lost_context = weakref.ref(opened.context)
            raise KeyboardInterrupt("cancelled before open result assignment")

        with pytest.raises(KeyboardInterrupt, match="open result assignment"):
            cancel_after_successful_open()
        gc.collect()
        assert lost_context is not None and lost_context() is None
        abandoned_reference = sealed._global_recurrence_child_token
        assert abandoned_reference is not None
        assert abandoned_reference() is None

        sealed.close()
        assert sealed.closed
        assert sealed._global_recurrence_child_token is None
        assert not sealed._global_recurrence_child_terminal
    finally:
        _close_stack(stack)


def test_parent_recovers_abandoned_consumed_no_work_without_fence_or_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    context_type = type(stack["global"].context)
    original_capture = context_type._capture_submission

    def fail_before_first_launch(*_arguments: Any, **_keywords: Any) -> Any:
        raise RuntimeError("injected consumed-no-work failure")

    monkeypatch.setattr(context_type, "_capture_submission", fail_before_first_launch)

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.enqueue_remaining_global_recurrence()
        assert failed.value.pending is not None
        before = sealed._global_recurrence_recovery_snapshot()
        assert before is not None
        assert before.continuation_consumed
        assert before.poisoned
        assert before.launch_attempt_count == 0
        assert before.launch_accept_lower_bound == 0
        assert before.launch_accept_upper_bound == 0
        return reference

    reference = enqueue_then_abandon()
    monkeypatch.setattr(context_type, "_capture_submission", original_capture)
    gc.collect()
    assert reference() is None
    abandoned = sealed._global_recurrence_recovery_snapshot()
    assert abandoned is not None and abandoned.abandoned
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.released and recovered.terminal
        assert recovered.fence_attempt_count == 0
        assert not recovered.fence_observed
        assert not recovered.ack_started
        assert recovered.acknowledged_launch_count is None
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


def test_consume_store_interruption_is_reconciled_by_abandoned_parent_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    parent_type = type(sealed)

    def consume_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                parent_type._consume_global_recurrence_continuation_capability,
                "_continuation_consumed",
                lambda: sealed._consume_global_recurrence_continuation_capability(
                    context._token,
                    stack["continuation"],
                ),
            )
        interrupted = sealed._global_recurrence_recovery_snapshot()
        assert interrupted is not None
        assert sealed._continuation_consumed
        assert not interrupted.continuation_consumed
        return reference

    reference = consume_then_abandon()
    gc.collect()
    assert reference() is None
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.continuation_consumed
        assert recovered.terminal and recovered.released
        assert recovered.fence_attempt_count == 0
        assert not recovered.ack_started
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


@pytest.mark.parametrize(
    ("target_name", "forged", "repairable"),
    (
        ("cell", False, True),
        ("cell", 0.0, False),
        ("parent", 1.0, False),
        ("cell", 1, False),
    ),
)
def test_global_recurrence_consumed_bits_require_exact_bool_before_repair(
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
    forged: object,
    repairable: bool,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    sealed._consume_global_recurrence_continuation_capability(
        context._token,
        stack["continuation"],
    )
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    target = cell if target_name == "cell" else sealed
    attribute = (
        "continuation_consumed" if target_name == "cell" else "_continuation_consumed"
    )
    original = getattr(target, attribute)
    launch_count = len(loaded.launch_records)
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        setattr(target, attribute, forged)
        if repairable:
            assert sealed._global_recurrence_continuation_capability_consumed(
                context._token
            )
            assert cell.continuation_consumed is True
        else:
            with pytest.raises(Exception) as failed:
                sealed._global_recurrence_continuation_capability_consumed(
                    context._token
                )
            assert getattr(failed.value, "code", "") == (
                "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid"
            )
        assert len(loaded.launch_records) == launch_count
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
    finally:
        setattr(target, attribute, original)

    context.close()
    receipt = context.receipt()
    validate_hip_fgmres_global_recurrence_receipt_v1(
        receipt,
        expected_context=context,
    )
    assert context.closed
    assert len(loaded.launch_records) == launch_count
    assert len(loaded.query_streams) == query_count
    assert len(loaded.sync_streams) == sync_count
    _close_stack(stack)


def test_pre_enqueue_recovery_authority_drift_fails_before_device_work_and_restores_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    pop_calls = 0

    def count_pop(owner: Any, token: object, stream: int) -> int:
        nonlocal pop_calls
        pop_calls += 1
        return original_consume(owner, token, stream)

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        count_pop,
    )
    mutations = (
        ("kernel", object()),
        ("checkpoint_owner_token", object()),
        ("stream_pointer", cell.stream_pointer + 1),
        ("stream_pointer", float(cell.stream_pointer)),
    )
    launch_count = len(loaded.launch_records)
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        for field, forged in mutations:
            original = getattr(cell, field)
            setattr(cell, field, forged)
            try:
                with pytest.raises(Exception) as failed:
                    context.enqueue_remaining_global_recurrence()
                assert getattr(failed.value, "code", "") == (
                    "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid"
                )
                assert getattr(failed.value, "cleanup_owner", None) is sealed
                assert context._state == "context_ready"
                assert context._telemetry.continuation_capability_consume_count == 0
                assert sealed._continuation_consumed is False
                assert cell.continuation_consumed is False
                assert sealed._global_recurrence_child_token is not None
                assert sealed._global_recurrence_child_token() is context._token
                assert sealed._global_recurrence_recovery_cell is cell
                assert len(loaded.launch_records) == launch_count
                assert len(loaded.query_streams) == query_count
                assert len(loaded.sync_streams) == sync_count
                assert pop_calls == 0
            finally:
                setattr(cell, field, original)

        context.close()
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert context.closed
        assert context._completion is None
        assert context.completion_capability is None
        assert not receipt.claims.completion_capability_issued
        assert len(loaded.launch_records) == launch_count
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
        assert pop_calls == 0
    finally:
        monkeypatch.setattr(
            kernel_type,
            "_consume_checkpoint_pending_after_fence",
            original_consume,
        )
        _close_stack(stack)


def test_launch_start_authority_drift_records_fail_safe_poison_without_device_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    stream = cell.stream_pointer
    parent_type = type(sealed)
    original_consume = parent_type._consume_global_recurrence_continuation_capability

    def consume_then_drift(owner: Any, token: object, capability: Any) -> None:
        original_consume(owner, token, capability)
        cell.stream_pointer = stream + 1

    monkeypatch.setattr(
        parent_type,
        "_consume_global_recurrence_continuation_capability",
        consume_then_drift,
    )
    launch_count = len(loaded.launch_records)
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(Exception) as failed:
            context.enqueue_remaining_global_recurrence()
        assert getattr(failed.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid"
        )
        progress = sealed._global_recurrence_recovery_snapshot()
        assert progress is not None
        assert progress.continuation_consumed
        assert progress.poisoned
        assert progress.launch_attempt_count == 0
        assert progress.launch_accept_lower_bound == 0
        assert progress.launch_accept_upper_bound == 0
        assert len(loaded.launch_records) == launch_count
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == ()

        cell.stream_pointer = stream
        monkeypatch.setattr(
            parent_type,
            "_consume_global_recurrence_continuation_capability",
            original_consume,
        )
        context.close()
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert context.closed
        assert context._completion is None
        assert context.completion_capability is None
        assert receipt.reason is not None
        assert receipt.telemetry.kernel_launch_attempt_count == 0
        assert not receipt.claims.completion_capability_issued
        assert len(loaded.launch_records) == launch_count
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
    finally:
        cell.stream_pointer = stream
        monkeypatch.setattr(
            parent_type,
            "_consume_global_recurrence_continuation_capability",
            original_consume,
        )
        _close_stack(stack)


def test_parent_launch_success_return_interruption_reconciles_live_cleanup_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    parent_type = type(sealed)
    original_success = parent_type._record_global_recurrence_launch_succeeded

    def success_then_interrupt(owner: Any, token: object) -> None:
        original_success(owner, token)
        raise _InjectedOpcodeInterruption(
            "interrupted after parent accepted-lower update"
        )

    monkeypatch.setattr(
        parent_type,
        "_record_global_recurrence_launch_succeeded",
        success_then_interrupt,
    )
    with pytest.raises(_InjectedOpcodeInterruption):
        context.enqueue_remaining_global_recurrence()
    monkeypatch.setattr(
        parent_type,
        "_record_global_recurrence_launch_succeeded",
        original_success,
    )
    assert context._telemetry.kernel_launch_accept_lower_bound == 1
    assert context._telemetry.kernel_launch_accept_upper_bound == 1
    parent_progress = sealed._global_recurrence_recovery_snapshot()
    assert parent_progress is not None
    assert parent_progress.launch_accept_lower_bound == 1
    assert parent_progress.launch_accept_upper_bound == 1
    assert parent_progress.poisoned
    sync_count = len(loaded.sync_streams)
    try:
        context.close()
        assert context.closed
        assert context._completion is None
        assert context.completion_capability is None
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.telemetry.kernel_launch_accept_lower_bound == 1
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 1
        assert not receipt.claims.completion_capability_issued
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == ()
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        _close_stack(stack)


def test_parent_launch_success_return_interruption_never_mints_stale_pending_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    live = stack["live"].context
    assert live is not None
    parent_type = type(sealed)
    original_success = parent_type._record_global_recurrence_launch_succeeded

    def success_then_fail(owner: Any, token: object) -> None:
        original_success(owner, token)
        raise RuntimeError("failed after authoritative launch success")

    monkeypatch.setattr(
        parent_type,
        "_record_global_recurrence_launch_succeeded",
        success_then_fail,
    )
    try:
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.enqueue_remaining_global_recurrence()
        pending = failed.value.pending
        assert type(pending) is HipFgmresGlobalRecurrencePendingV1
        assert pending is context._pending
        assert pending.attempted_launch_count == 1
        assert pending.accepted_launch_count_lower_bound == 1
        assert pending.accepted_launch_count_upper_bound == 1
        progress = sealed._global_recurrence_recovery_snapshot()
        assert progress is not None
        assert progress.launch_attempt_count == 1
        assert progress.launch_accept_lower_bound == 1
        assert progress.launch_accept_upper_bound == 1
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == (
            (live._stream_pointer_snapshot, 1),
        )
        assert context.completion_capability is None

        context.close()
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert context._completion is None
        assert context.completion_capability is None
        assert not receipt.claims.completion_capability_issued
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == ()
    finally:
        monkeypatch.setattr(
            parent_type,
            "_record_global_recurrence_launch_succeeded",
            original_success,
        )
        _close_stack(stack)


def test_parent_poison_return_interruption_rebuilds_valid_no_work_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    context_type = type(context)
    parent_type = type(sealed)
    original_capture = context_type._capture_submission
    original_poison = parent_type._record_global_recurrence_poisoned

    def fail_before_first_launch(*_arguments: Any, **_keywords: Any) -> Any:
        raise RuntimeError("injected no-work enqueue failure")

    def poison_then_interrupt(owner: Any, token: object) -> None:
        original_poison(owner, token)
        raise _InjectedOpcodeInterruption(
            "interrupted after parent poison ledger return"
        )

    monkeypatch.setattr(context_type, "_capture_submission", fail_before_first_launch)
    monkeypatch.setattr(
        parent_type,
        "_record_global_recurrence_poisoned",
        poison_then_interrupt,
    )
    with pytest.raises(_InjectedOpcodeInterruption):
        context.enqueue_remaining_global_recurrence()
    monkeypatch.setattr(context_type, "_capture_submission", original_capture)
    monkeypatch.setattr(
        parent_type,
        "_record_global_recurrence_poisoned",
        original_poison,
    )
    assert context._state == "recurrence_pending"
    assert context._reason is None
    assert context._pending is None
    parent_progress = sealed._global_recurrence_recovery_snapshot()
    assert parent_progress is not None and parent_progress.poisoned
    sync_count = len(loaded.sync_streams)
    try:
        context.close()
        assert context.closed
        assert context._completion is None
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.reason is not None
        assert receipt.telemetry.fence_attempt_count == 0
        assert receipt.telemetry.pending_consume_attempt_count == 0
        assert not receipt.claims.completion_capability_issued
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


@pytest.mark.parametrize("publication_store", ("_state", "_reason", "_pending"))
def test_local_poison_publication_store_interruptions_rebuild_valid_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    publication_store: str,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    context_type = type(context)
    original_capture = context_type._capture_submission

    def fail_before_first_launch(*_arguments: Any, **_keywords: Any) -> Any:
        raise RuntimeError("injected local poison publication failure")

    monkeypatch.setattr(context_type, "_capture_submission", fail_before_first_launch)
    with pytest.raises(_InjectedOpcodeInterruption):
        _interrupt_immediately_after_store_attr(
            context_type._poison_after_enqueue_failure,
            publication_store,
            context.enqueue_remaining_global_recurrence,
        )
    monkeypatch.setattr(context_type, "_capture_submission", original_capture)
    parent_progress = sealed._global_recurrence_recovery_snapshot()
    assert parent_progress is not None and parent_progress.poisoned
    sync_count = len(loaded.sync_streams)
    try:
        context.close()
        assert context.closed
        assert context._completion is None
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.reason is not None
        assert receipt.telemetry.fence_attempt_count == 0
        assert not receipt.claims.fixed_suffix_fenced
        assert not receipt.claims.completion_capability_issued
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


def test_parent_recovers_full_pending_abandoned_child_with_one_successful_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        pending = context.enqueue_remaining_global_recurrence()
        assert pending.accepted_launch_count_lower_bound == 1
        assert pending.accepted_launch_count_upper_bound == 1
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    before = sealed._global_recurrence_recovery_snapshot()
    assert before is not None and before.abandoned
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.released and recovered.terminal
        assert recovered.fence_attempt_count == 1
        assert recovered.fence_observed and recovered.ack_started
        assert recovered.acknowledged_launch_count == 1
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == ()
    finally:
        _close_stack(stack)


def test_parent_does_not_reap_live_consumed_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    pending = context.enqueue_remaining_global_recurrence()
    pending_snapshot = kernel._checkpoint_pending_snapshot(live._checkpoint_token)
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(Exception) as active:
            sealed.close()
        assert getattr(active.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_global_child_active"
        )
        assert sealed._global_recurrence_child_token is not None
        assert sealed._global_recurrence_child_token() is context._token
        assert kernel._checkpoint_pending_snapshot(live._checkpoint_token) == (
            pending_snapshot
        )
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
        context.synchronize(pending)
        context.close()
    finally:
        _close_stack(stack)


@pytest.mark.parametrize(
    ("field", "forged"),
    (
        ("launch_limit", 1.0),
        ("launch_attempt_count", True),
        ("launch_accept_lower_bound", 1.0),
        ("fence_attempt_count", True),
    ),
)
def test_parent_progress_type_tamper_fails_before_hip_or_public_receipt(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    forged: object,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    pending = context.enqueue_remaining_global_recurrence()
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    original = getattr(cell, field)
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        setattr(cell, field, forged)
        with pytest.raises(Exception) as receipt_failed:
            context.receipt()
        assert getattr(receipt_failed.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_global_recovery_state_invalid"
        )
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as close_failed:
            context.close()
        assert close_failed.value.code == (
            "hip_fgmres_global_recurrence_cleanup_failed"
        )
        assert close_failed.value.cleanup_owner is context
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count

        setattr(cell, field, original)
        context.synchronize(pending)
        context.close()
    finally:
        setattr(cell, field, original)
        _close_stack(stack)


def test_abandoned_recovery_pop_interruption_converges_without_refence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def pop_then_interrupt(owner: Any, token: object, stream: int) -> int:
        nonlocal consume_calls
        consume_calls += 1
        consumed = original_consume(owner, token, stream)
        if consume_calls == 1:
            raise RuntimeError("interrupted after abandoned pending-map pop")
        return consumed

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        pop_then_interrupt,
    )
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(RuntimeError, match="abandoned pending-map pop"):
            sealed.close()
        retryable = sealed._global_recurrence_recovery_snapshot()
        assert retryable is not None
        assert retryable.ack_started
        assert retryable.acknowledged_launch_count is None
        assert not retryable.terminal
        assert (
            kernel._checkpoint_pending_snapshot(
                retryable and kernel._checkpoint_owner_token
            )
            == ()
        )

        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.terminal and recovered.released
        assert recovered.acknowledged_launch_count == 1
        assert consume_calls == 1
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        _close_stack(stack)


def test_recovered_terminal_release_interruption_and_concurrent_retries_are_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    parent_type = type(sealed)
    original_release = parent_type._terminally_release_abandoned_global_recurrence
    release_calls = 0

    def release_then_interrupt(owner: Any, cell: Any) -> None:
        nonlocal release_calls
        release_calls += 1
        original_release(owner, cell)
        raise RuntimeError("interrupted after recovered terminal release")

    monkeypatch.setattr(
        parent_type,
        "_terminally_release_abandoned_global_recurrence",
        release_then_interrupt,
    )
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(RuntimeError, match="recovered terminal release"):
            sealed.close()
        interrupted = sealed._global_recurrence_recovery_snapshot()
        assert interrupted is not None
        assert interrupted.terminal and interrupted.released
        assert not sealed.closed

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.submit(sealed.close) for _ in range(2))
            for result in results:
                assert result.result() is None
        assert sealed.closed
        assert release_calls == 1
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        _close_stack(stack)


@pytest.mark.parametrize(
    "release_store",
    (
        "released",
        "terminal",
        "_global_recurrence_child_terminal",
        "_global_recurrence_child_token",
    ),
)
def test_live_no_work_release_is_resumable_after_every_authoritative_store(
    monkeypatch: pytest.MonkeyPatch,
    release_store: str,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    context_type = type(context)
    original_capture = context_type._capture_submission

    def fail_before_first_launch(*_arguments: Any, **_keywords: Any) -> Any:
        raise RuntimeError("injected no-work failure before release")

    monkeypatch.setattr(context_type, "_capture_submission", fail_before_first_launch)
    with pytest.raises(HipFgmresGlobalRecurrenceV1Error):
        context.enqueue_remaining_global_recurrence()
    monkeypatch.setattr(context_type, "_capture_submission", original_capture)
    assert context.receipt().status == "poisoned_no_work"
    sync_count = len(loaded.sync_streams)
    parent_type = type(sealed)
    try:
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                parent_type._release_global_recurrence_child,
                release_store,
                context.close,
            )
        assert not context.closed
        assert context.completion_capability is None

        context.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.released and recovered.terminal
        assert context.closed
        assert context._completion is None
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


@pytest.mark.parametrize("phase", ("context_ready", "recurrence_fenced"))
def test_release_token_store_interruption_never_publishes_ready_or_bound_receipt_before_close_retry(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    stack = _open_stack(monkeypatch)
    opening = stack["global"]
    context = opening.context
    sealed = stack["sealed"].context
    completion = None
    if phase == "recurrence_fenced":
        pending = context.enqueue_remaining_global_recurrence()
        completion = context.synchronize(pending)
        assert context.completion_capability is completion
    assert opening.ready
    parent_type = type(sealed)
    try:
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                parent_type._release_global_recurrence_child,
                "_global_recurrence_child_token",
                context.close,
            )
        assert context._child_released
        assert not context.closed
        assert not opening.ready
        assert context.completion_capability is None

        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as receipt_failed:
            context.receipt()
        assert receipt_failed.value.code == (
            "hip_fgmres_global_recurrence_close_incomplete"
        )
        assert receipt_failed.value.cleanup_owner is context
        if completion is not None:
            with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as invalid:
                validate_hip_fgmres_global_recurrence_completion_capability_v1(
                    completion,
                    expected_context=context,
                )
            assert invalid.value.code == (
                "hip_fgmres_global_recurrence_close_incomplete"
            )
            assert invalid.value.cleanup_owner is context

        context.close()
        receipt = context.receipt()
        validate_hip_fgmres_global_recurrence_receipt_v1(
            receipt,
            expected_context=context,
        )
        assert receipt.status == "context_closed"
        assert not opening.ready
        assert not receipt.claims.sealed_checkpoint_parent_bound
        assert not receipt.claims.continuation_capability_reserved
        assert not receipt.claims.direct11_csr3_scratch2_physical16_bound
        assert not receipt.claims.same_kernel_runtime_device_stream_checkpoint_bound
        assert not receipt.claims.canonical_continuation_suffix_bound
        assert not receipt.claims.one_pending_stream_map_bound
    finally:
        _close_stack(stack)


@pytest.mark.parametrize(
    "release_store",
    (
        "released",
        "terminal",
        "_global_recurrence_child_terminal",
        "_global_recurrence_child_token",
    ),
)
def test_abandoned_terminal_release_resumes_after_every_authoritative_store(
    monkeypatch: pytest.MonkeyPatch,
    release_store: str,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    parent_type = type(sealed)
    try:
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                parent_type._terminally_release_abandoned_global_recurrence,
                release_store,
                sealed.close,
            )
        assert not sealed.closed

        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.released and recovered.terminal
        assert sealed.closed
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        _close_stack(stack)


def test_abandoned_unknown_query_and_malformed_pending_retain_owner_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    stream = live._stream_pointer_snapshot

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    kernel_type = type(kernel)
    original_snapshot = kernel_type._checkpoint_pending_snapshot
    try:
        loaded.query_status = 7
        with pytest.raises(Exception):
            sealed.close()
        after_unknown = sealed._global_recurrence_recovery_snapshot()
        assert after_unknown is not None and not after_unknown.terminal
        assert sealed._global_recurrence_child_token is not None
        assert sealed._global_recurrence_child_token() is None
        assert len(loaded.query_streams) == query_count + 1
        assert len(loaded.sync_streams) == sync_count

        loaded.query_status = None

        def malformed_pending(_owner: Any, _token: object) -> Any:
            return ((stream, 0),)

        monkeypatch.setattr(
            kernel_type,
            "_checkpoint_pending_snapshot",
            malformed_pending,
        )
        with pytest.raises(Exception) as malformed:
            sealed.close()
        assert getattr(malformed.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_cleanup_failed"
        )
        assert getattr(malformed.value, "cleanup_owner", None) is sealed
        after_malformed = sealed._global_recurrence_recovery_snapshot()
        assert after_malformed is not None and not after_malformed.terminal
        assert len(loaded.query_streams) == query_count + 1
        assert len(loaded.sync_streams) == sync_count

        monkeypatch.setattr(
            kernel_type,
            "_checkpoint_pending_snapshot",
            original_snapshot,
        )
        assert original_snapshot(kernel, live._checkpoint_token) == ((stream, 1),)
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None and recovered.terminal
    finally:
        loaded.query_status = None
        monkeypatch.setattr(
            kernel_type,
            "_checkpoint_pending_snapshot",
            original_snapshot,
        )
        _close_stack(stack)


def test_abandoned_recovery_frozen_authority_tamper_fails_before_hip_and_retains_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    pop_calls = 0

    def count_pop(owner: Any, token: object, stream: int) -> int:
        nonlocal pop_calls
        pop_calls += 1
        return original_consume(owner, token, stream)

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        count_pop,
    )
    mutations = (
        ("kernel", object()),
        ("checkpoint_owner_token", object()),
        ("stream_pointer", cell.stream_pointer + 1),
        ("stream_pointer", float(cell.stream_pointer)),
    )
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        for field, forged in mutations:
            original = getattr(cell, field)
            setattr(cell, field, forged)
            try:
                with pytest.raises(Exception) as failed:
                    sealed.close()
                assert getattr(failed.value, "code", "") == (
                    "hip_fgmres_sealed_checkpoint_transaction_cleanup_failed"
                )
                assert getattr(failed.value, "cleanup_owner", None) is sealed
                assert not sealed.closed
                assert sealed._global_recurrence_child_token is not None
                assert sealed._global_recurrence_child_token() is None
                assert sealed._global_recurrence_recovery_cell is cell
                assert not cell.released and not cell.terminal
                assert len(loaded.query_streams) == query_count
                assert len(loaded.sync_streams) == sync_count
                assert pop_calls == 0
            finally:
                setattr(cell, field, original)

        sealed.close()
        assert sealed.closed
        assert cell.released and cell.terminal
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
        assert pop_calls == 1
    finally:
        monkeypatch.setattr(
            kernel_type,
            "_consume_checkpoint_pending_after_fence",
            original_consume,
        )
        _close_stack(stack)


def test_abandoned_recovery_query_baseexception_propagates_and_retry_drains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    cell = sealed._global_recurrence_recovery_cell
    assert cell is not None
    kernel_type = type(kernel)
    original_query = kernel_type._query_checkpoint_stream_completion
    original_consume = kernel_type._consume_checkpoint_pending_after_fence
    query_calls = 0
    pop_calls = 0

    def interrupt_once(owner: Any, token: object, stream: int) -> bool:
        nonlocal query_calls
        query_calls += 1
        if query_calls == 1:
            raise KeyboardInterrupt("injected abandoned recovery query interruption")
        return original_query(owner, token, stream)

    def count_pop(owner: Any, token: object, stream: int) -> int:
        nonlocal pop_calls
        pop_calls += 1
        return original_consume(owner, token, stream)

    monkeypatch.setattr(
        kernel_type,
        "_query_checkpoint_stream_completion",
        interrupt_once,
    )
    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        count_pop,
    )
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(KeyboardInterrupt, match="query interruption"):
            sealed.close()
        assert query_calls == 1
        assert pop_calls == 0
        assert not sealed.closed
        assert sealed._active_operation is None
        assert sealed._global_recurrence_child_token is not None
        assert sealed._global_recurrence_child_token() is None
        assert sealed._global_recurrence_recovery_cell is cell
        assert not cell.released and not cell.terminal
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count

        monkeypatch.setattr(
            kernel_type,
            "_query_checkpoint_stream_completion",
            original_query,
        )
        sealed.close()
        assert sealed.closed
        assert cell.released and cell.terminal
        assert pop_calls == 1
        assert len(loaded.query_streams) == query_count + 2
        assert len(loaded.sync_streams) == sync_count + 1
    finally:
        monkeypatch.setattr(
            kernel_type,
            "_query_checkpoint_stream_completion",
            original_query,
        )
        monkeypatch.setattr(
            kernel_type,
            "_consume_checkpoint_pending_after_fence",
            original_consume,
        )
        _close_stack(stack)


@pytest.mark.parametrize("failure_kind", ("query", "sync", "pop"))
def test_parent_recovery_runtime_failures_preserve_stable_cleanup_owner(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    if failure_kind == "query":
        loaded.query_status = 7
    elif failure_kind == "sync":
        loaded.sync_fail_count = 1
    else:
        kernel_type = type(kernel)
        original_consume = kernel_type._consume_checkpoint_pending_after_fence
        pop_failures = 1

        def fail_before_pop(owner: Any, token: object, stream: int) -> int:
            nonlocal pop_failures
            if pop_failures:
                pop_failures -= 1
                raise RuntimeError("injected parent recovery pop failure")
            return original_consume(owner, token, stream)

        monkeypatch.setattr(
            kernel_type,
            "_consume_checkpoint_pending_after_fence",
            fail_before_pop,
        )
    try:
        with pytest.raises(Exception) as failed:
            sealed.close()
        assert type(failed.value).__name__ == (
            "HipFgmresSealedCheckpointTransactionV1Error"
        )
        assert getattr(failed.value, "code", "") == (
            "hip_fgmres_sealed_checkpoint_transaction_cleanup_failed"
        )
        assert getattr(failed.value, "cleanup_owner", None) is sealed
        retained = sealed._global_recurrence_recovery_snapshot()
        assert retained is not None and not retained.terminal
        assert not sealed.closed

        loaded.query_status = None
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None and recovered.terminal
    finally:
        loaded.query_status = None
        _close_stack(stack)


def test_normal_terminal_release_is_not_reclassified_as_abandoned_after_gc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]

    def finish_then_drop() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        pending = context.enqueue_remaining_global_recurrence()
        context.synchronize(pending)
        context.close()
        before = sealed._global_recurrence_recovery_snapshot()
        assert before is not None
        assert before.released and before.terminal
        assert not before.abandoned
        return reference

    reference = finish_then_drop()
    gc.collect()
    assert reference() is None
    after_gc = sealed._global_recurrence_recovery_snapshot()
    assert after_gc is not None
    assert after_gc.released and after_gc.terminal
    assert not after_gc.child_live
    assert not after_gc.abandoned
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        sealed.close()
        assert len(loaded.query_streams) == query_count
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


def test_abandoned_query_ready_path_acks_without_another_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]
    live = stack["live"].context
    assert live is not None
    stream = live._stream_pointer_snapshot

    def enqueue_ready_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        loaded._stream_completion[stream] = True
        return reference

    reference = enqueue_ready_then_abandon()
    gc.collect()
    assert reference() is None
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.terminal and recovered.released
        assert recovered.fence_attempt_count == 0
        assert recovered.fence_observed
        assert recovered.acknowledged_launch_count == 1
        assert len(loaded.query_streams) == query_count + 1
        assert len(loaded.sync_streams) == sync_count
    finally:
        _close_stack(stack)


def test_live_retry_queries_complete_after_successful_sync_return_was_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]
    pending = context.enqueue_remaining_global_recurrence()
    kernel_type = type(kernel)
    original_sync = kernel_type._synchronize_checkpoint_stream
    sync_calls = 0

    def sync_then_interrupt(owner: Any, token: object, stream: int) -> None:
        nonlocal sync_calls
        sync_calls += 1
        original_sync(owner, token, stream)
        raise RuntimeError("successful sync return was lost")

    monkeypatch.setattr(
        kernel_type,
        "_synchronize_checkpoint_stream",
        sync_then_interrupt,
    )
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            context.synchronize(pending)
        assert failed.value.code == "hip_fgmres_global_recurrence_fence_failed"
        interrupted = sealed._global_recurrence_recovery_snapshot()
        assert interrupted is not None
        assert interrupted.fence_attempt_count == 1
        assert not interrupted.fence_observed

        completion = context.synchronize(pending)
        assert completion.fenced_launch_count == 1
        receipt = context.receipt()
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        reconciled = sealed._global_recurrence_recovery_snapshot()
        assert reconciled is not None and reconciled.fence_observed
        assert sync_calls == 1
        assert len(loaded.sync_streams) == sync_count + 1
        assert len(loaded.query_streams) == query_count + 1
    finally:
        _close_stack(stack)


def test_abandoned_recovery_retries_only_after_query_proves_sync_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    loaded = stack["loaded"]

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        context.enqueue_remaining_global_recurrence()
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    loaded.sync_fail_count = 1
    query_count = len(loaded.query_streams)
    sync_count = len(loaded.sync_streams)
    try:
        with pytest.raises(Exception):
            sealed.close()
        first = sealed._global_recurrence_recovery_snapshot()
        assert first is not None
        assert first.fence_attempt_count == 1
        assert not first.fence_observed
        assert not first.ack_started

        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.terminal and recovered.released
        assert recovered.fence_attempt_count == 2
        assert recovered.fence_observed
        assert len(loaded.query_streams) == query_count + 3
        assert len(loaded.sync_streams) == sync_count + 2
    finally:
        _close_stack(stack)


def test_abandoned_ambiguous_pop_loss_releases_without_inventing_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    sealed = stack["sealed"].context
    kernel = stack["kernel"]
    loaded = stack["loaded"]

    def interrupt_after_accepted_launch(_count: int) -> None:
        raise RuntimeError("ambiguous accepted launch interruption")

    loaded.launch_callback = interrupt_after_accepted_launch

    def enqueue_then_abandon() -> weakref.ReferenceType[Any]:
        opened = stack.pop("global")
        context = opened.context
        reference = weakref.ref(context)
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error):
            context.enqueue_remaining_global_recurrence()
        snapshot = sealed._global_recurrence_recovery_snapshot()
        assert snapshot is not None
        assert snapshot.launch_accept_lower_bound == 0
        assert snapshot.launch_accept_upper_bound == 1
        assert snapshot.poisoned
        loaded.launch_callback = None
        return reference

    reference = enqueue_then_abandon()
    gc.collect()
    assert reference() is None
    kernel_type = type(kernel)
    original_consume = kernel_type._consume_checkpoint_pending_after_fence

    def pop_then_interrupt(owner: Any, token: object, stream: int) -> int:
        original_consume(owner, token, stream)
        raise RuntimeError("ambiguous count lost after pop")

    monkeypatch.setattr(
        kernel_type,
        "_consume_checkpoint_pending_after_fence",
        pop_then_interrupt,
    )
    try:
        with pytest.raises(RuntimeError, match="ambiguous count lost"):
            sealed.close()
        retryable = sealed._global_recurrence_recovery_snapshot()
        assert retryable is not None and retryable.ack_started
        assert retryable.acknowledged_launch_count is None

        sealed.close()
        recovered = sealed._global_recurrence_recovery_snapshot()
        assert recovered is not None
        assert recovered.terminal and recovered.released
        assert recovered.poisoned
        assert recovered.acknowledged_launch_count is None
    finally:
        loaded.launch_callback = None
        _close_stack(stack)


def test_physical_drift_schedule_forgery_and_receipt_forgery_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_stack(monkeypatch)
    context = stack["global"].context
    canonical = stack["canonical"].context
    original_pointer = canonical._pointers["reduction_ping"]
    try:
        canonical._pointers["reduction_ping"] = original_pointer + 4096
        with pytest.raises(Exception) as drift:
            context.enqueue_remaining_global_recurrence()
        assert getattr(drift.value, "code", "") in {
            "hip_fgmres_sealed_checkpoint_transaction_global_child_authority_invalid",
            "hip_fgmres_global_recurrence_binding_changed",
        }
        ready = context.receipt()
        assert ready.status == "context_ready"
        assert ready.telemetry.continuation_capability_consume_count == 0
        canonical._pointers["reduction_ping"] = original_pointer

        binding = context._require_binding()
        first = binding.launches[0]
        original_epoch = first.expected_schedule_epoch
        object.__setattr__(first, "expected_schedule_epoch", original_epoch + 1)
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as schedule:
            context.enqueue_remaining_global_recurrence()
        assert schedule.value.code in {
            "hip_fgmres_global_recurrence_binding_invalid",
            "hip_fgmres_global_recurrence_schedule_changed",
        }
        object.__setattr__(first, "expected_schedule_epoch", original_epoch)

        forged = replace(
            ready,
            claims=replace(ready.claims, commercial_ready=True),
        )
        forged = replace(
            forged,
            receipt_hash=ready.receipt_hash,
        )
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as invalid:
            validate_hip_fgmres_global_recurrence_receipt_v1(forged)
        assert invalid.value.code in {
            "hip_fgmres_global_recurrence_receipt_hash_invalid",
            "hip_fgmres_global_recurrence_claim_invalid",
        }

        for field_name in (
            "recurrence_kernel_abi_hash",
            "combined_recurrence_abi_hash",
            "kernel_source_sha256",
        ):
            identity_forged = replace(
                ready,
                bindings=replace(
                    ready.bindings,
                    **{field_name: "sha256:" + "f" * 64},
                ),
            )
            identity_forged = replace(
                identity_forged,
                receipt_hash=canonical_hash(
                    _receipt_payload(identity_forged, include_hash=False)
                ),
            )
            with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as identity:
                validate_hip_fgmres_global_recurrence_receipt_v1(identity_forged)
            assert identity.value.code == (
                "hip_fgmres_global_recurrence_abi_identity_invalid"
            )

        schema_forged = replace(
            ready,
            bindings=replace(ready.bindings, architecture="not-gfx"),
        )
        schema_forged = replace(
            schema_forged,
            receipt_hash=canonical_hash(
                _receipt_payload(schema_forged, include_hash=False)
            ),
        )
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as schema_invalid:
            validate_hip_fgmres_global_recurrence_receipt_v1(schema_forged)
        assert schema_invalid.value.code == (
            "hip_fgmres_global_recurrence_schema_invalid"
        )
        assert schema_invalid.value.path == "/bindings/architecture"

        pending = context.enqueue_remaining_global_recurrence()
        object.__setattr__(
            pending,
            "attempted_launch_count",
            pending.attempted_launch_count + 1,
        )
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as changed:
            context.synchronize(pending)
        assert changed.value.code == "hip_fgmres_global_recurrence_pending_invalid"
        object.__setattr__(
            pending,
            "attempted_launch_count",
            pending.attempted_launch_count - 1,
        )
        completion = context.synchronize(pending)
        original_count = completion.fenced_launch_count
        object.__setattr__(completion, "fenced_launch_count", original_count + 1)
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as completion_changed:
            validate_hip_fgmres_global_recurrence_completion_capability_v1(
                completion,
                expected_context=context,
            )
        assert completion_changed.value.code == (
            "hip_fgmres_global_recurrence_completion_capability_invalid"
        )
        object.__setattr__(completion, "fenced_launch_count", original_count)
    finally:
        canonical._pointers["reduction_ping"] = original_pointer
        _close_stack(stack)


def test_capability_types_are_not_publicly_constructible() -> None:
    with pytest.raises(TypeError):
        HipFgmresGlobalRecurrencePendingV1()
    with pytest.raises(TypeError):
        HipFgmresGlobalRecurrenceCompletionCapabilityV1()
