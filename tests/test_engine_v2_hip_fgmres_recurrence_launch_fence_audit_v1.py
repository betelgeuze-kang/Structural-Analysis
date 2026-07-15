from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_recurrence_launch_fence_audit_v1 as audit_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_launch_fence_audit_v1 import (
    HipFgmresRecurrenceLaunchFenceAuditV1Error,
    open_hip_fgmres_recurrence_launch_fence_audit_v1,
    validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1,
    validate_hip_fgmres_recurrence_launch_fence_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_launch_fence_ledger_v1 import (
    _HipFgmresRtcLaunchFenceLedgerStateV1,
    _capture_rtc_launch_fence_ledger_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1

from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _prepare_live_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_recurrence_launch_fence_audit_v1.schema.json"
)


def _open_chain(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    (
        _runtime,
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
    policy = compile_fgmres_policy_v1(restart_dimension=1, max_iterations=2)
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
    canonical = sealed = global_open = ordinal = None
    try:
        assert live.context is not None
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        ordinal = open_hip_fgmres_recurrence_launch_fence_audit_v1(canonical.context)
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
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        return {
            "parent_open": parent_open,
            "resident_open": resident_open,
            "free_open": free_open,
            "primitive_open": primitive_open,
            "live": live,
            "canonical": canonical,
            "sealed": sealed,
            "global": global_open,
            "ordinal": ordinal,
            "loaded": loaded,
        }
    except BaseException:
        if ordinal is not None:
            ordinal.context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)
        raise


def _close_chain(stack: dict[str, object]) -> None:
    ordinal = stack["ordinal"].context
    ordinal.close()
    global_context = stack["global"].context
    if not global_context.closed:
        global_context.close()
    sealed = stack["sealed"].context
    if not sealed.closed:
        sealed.close()
    canonical = stack["canonical"].context
    if not canonical.closed:
        canonical.close()
    _cleanup(
        stack["live"],
        stack["primitive_open"],
        stack["free_open"],
        stack["resident_open"],
        stack["parent_open"],
    )


def _fence_and_seal(stack: dict[str, object]):
    global_context = stack["global"].context
    pending = global_context.enqueue_remaining_global_recurrence()
    completion = global_context.synchronize(pending)
    return stack["ordinal"].context.seal_terminal_fence(
        global_context,
        completion,
    )


def _rehash(receipt, **changes):
    forged = replace(receipt, **changes)
    return replace(
        forged,
        receipt_hash=canonical_hash(
            audit_module._receipt_payload(forged, include_hash=False)
        ),
    )


def test_full_fixed_recurrence_launch_fence_chain_is_sealed() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            result = _fence_and_seal(stack)
            validate_hip_fgmres_recurrence_launch_fence_audit_result_v1(
                result,
                expected_context=stack["ordinal"].context,
            )
            receipt = result.receipt
            dimensions = receipt.dimensions
            assert receipt.actual_backend == "test_double"
            assert dimensions.prelaunch_memset_count == 8
            assert dimensions.sealed_checkpoint_launch_count == 4
            assert (
                dimensions.canonical_launch_count
                + dimensions.sealed_checkpoint_launch_count
                + dimensions.continuation_launch_count
                == dimensions.full_program_launch_count
            )
            assert receipt.telemetry.memset.attempt_count == 8
            assert (
                receipt.telemetry.launch.attempt_count
                == dimensions.full_program_launch_count
            )
            assert receipt.telemetry.fence.attempt_count == 3
            assert receipt.window.terminal_fence_ordinal == (
                receipt.window.end_operation_ordinal
            )
            assert receipt.claims.device_kernel_execution_success_proven is False
            assert receipt.claims.iteration_host_copy_zero_proven is False
            assert receipt.claims.commercial_ready is False
            assert Draft202012Validator(json.loads(SCHEMA.read_text())).is_valid(
                receipt.to_dict()
            )
        finally:
            _close_chain(stack)


def test_ledger_snapshot_is_unchanged_by_detached_receipt_serialization() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            result = _fence_and_seal(stack)
            before = _capture_rtc_launch_fence_ledger_v1(
                stack["ordinal"].context._kernel,
                stack["ordinal"].context._checkpoint_owner_token,
            ).snapshot
            result.to_manifest()
            after = _capture_rtc_launch_fence_ledger_v1(
                stack["ordinal"].context._kernel,
                stack["ordinal"].context._checkpoint_owner_token,
            ).snapshot
            assert after == before
        finally:
            _close_chain(stack)


def test_duplicate_audit_owner_is_rejected() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:

            class _ForeignOwner:
                pass

            with pytest.raises(HipFgmresRecurrenceLaunchFenceAuditV1Error) as caught:
                audit_module._reserve_ledger_audit_owner(
                    stack["ordinal"].context._start_capture.state,
                    _ForeignOwner(),
                )
            assert caught.value.code == (
                "hip_fgmres_recurrence_launch_fence_audit_ledger_busy"
            )
        finally:
            _close_chain(stack)


def test_extra_owned_ledger_event_breaks_expected_chain() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            state = stack["ordinal"].context._start_capture.state
            ticket = state.begin(
                "launch",
                canonical_hash({"injected": "extra-owned-event"}),
            )
            state.finish(ticket, disposition="success")
            global_context = stack["global"].context
            pending = global_context.enqueue_remaining_global_recurrence()
            completion = global_context.synchronize(pending)
            with pytest.raises(HipFgmresRecurrenceLaunchFenceAuditV1Error) as caught:
                stack["ordinal"].context.seal_terminal_fence(
                    global_context,
                    completion,
                )
            assert caught.value.code in {
                "hip_fgmres_recurrence_launch_fence_audit_chain_mismatch",
                "hip_fgmres_recurrence_launch_fence_audit_seal_failed",
            }
        finally:
            _close_chain(stack)


def test_detached_rehash_cannot_promote_false_claim() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            receipt = _fence_and_seal(stack).receipt
            claims = replace(receipt.claims, commercial_ready=True)
            forged = _rehash(receipt, claims=claims)
            with pytest.raises(HipFgmresRecurrenceLaunchFenceAuditV1Error) as caught:
                validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(forged)
            assert caught.value.code in {
                "hip_fgmres_recurrence_launch_fence_audit_schema_invalid",
                "hip_fgmres_recurrence_launch_fence_audit_claim_invalid",
            }
        finally:
            _close_chain(stack)


def test_detached_rehash_cannot_break_recomputable_ledger_invariants() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            receipt = _fence_and_seal(stack).receipt
            for forged in (
                _rehash(receipt, context_id=canonical_hash({"forged": "context"})),
                _rehash(
                    receipt,
                    bindings=replace(
                        receipt.bindings,
                        completion_receipt_hash=canonical_hash(
                            {"forged": "completion"}
                        ),
                    ),
                ),
                _rehash(
                    receipt,
                    window=replace(
                        receipt.window,
                        start_event_sequence=(receipt.window.start_event_sequence + 2),
                        end_event_sequence=receipt.window.end_event_sequence + 2,
                    ),
                ),
            ):
                with pytest.raises(HipFgmresRecurrenceLaunchFenceAuditV1Error):
                    validate_hip_fgmres_recurrence_launch_fence_audit_receipt_v1(forged)
        finally:
            _close_chain(stack)


def test_ledger_rejects_event_sequence_overflow_before_attempt() -> None:
    state = _HipFgmresRtcLaunchFenceLedgerStateV1()
    max_json_safe_integer = (1 << 53) - 1
    state._event_sequence = max_json_safe_integer - 1

    with pytest.raises(OverflowError, match="event sequence exhausted"):
        state.begin("fence", canonical_hash({"descriptor": "fence"}))

    assert state._operation_ordinal == 0
    assert state._event_sequence == max_json_safe_integer - 1
    assert state._in_flight == {}


def test_schema_rejects_unknown_nested_property() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        stack = _open_chain(monkeypatch)
        try:
            payload = _fence_and_seal(stack).receipt.to_dict()
            payload["window"]["unknown"] = 1
            with pytest.raises(ValidationError):
                Draft202012Validator(json.loads(SCHEMA.read_text())).validate(payload)
        finally:
            _close_chain(stack)
