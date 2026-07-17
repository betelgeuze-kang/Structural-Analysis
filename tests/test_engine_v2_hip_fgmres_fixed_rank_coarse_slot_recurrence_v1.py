from __future__ import annotations

# ruff: noqa: E402

import ctypes
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1 as slot_receipt_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_slot_rtc_v1 as slot_rtc_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 as guard_rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_context_v1 import (
    open_hip_fgmres_fixed_rank_coarse_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (
    compile_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_recurrence_v1 import (
    HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
    open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION,
    HipFgmresFixedRankCoarseSlotRecurrenceReasonV1,
    HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1,
    HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
    validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseSlotKernelV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceV1Error,
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    _VECTOR_MODE_CODES,
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)

from tests.test_engine_v2_hip_fgmres_fixed_rank_coarse_context_v1 import (
    _coarse_kernel,
)
from tests.test_engine_v2_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1 import (
    _run_recurrence,
)
from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _prepare_live_inputs,
)


SCHEMA = (
    SRC_ROOT
    / "structural_analysis"
    / "schemas"
    / "hip_fgmres_fixed_rank_coarse_slot_recurrence_v1.schema.json"
)


def _coherently_rehash_slot_receipt(
    receipt: HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1,
    **changes: Any,
) -> HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1:
    draft = replace(
        receipt,
        **changes,
        receipt_hash=slot_receipt_module._ZERO_HASH,
    )
    return replace(
        draft,
        receipt_hash=slot_receipt_module.canonical_hash(
            slot_receipt_module._receipt_payload(draft, include_hash=False)
        ),
    )


class _SlotRuntime:
    def __init__(self, loaded_runtime: Any) -> None:
        self._runtime = loaded_runtime
        self.launch_outcomes: list[int | BaseException] = []
        self.launches: list[dict[str, Any]] = []
        self.unloads = 0

    def launch(self, function: Any, **keywords: Any) -> int:
        self.launches.append({"function": function, **keywords})
        outcome = self.launch_outcomes.pop(0) if self.launch_outcomes else 0
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def unload(self, _module: Any) -> int:
        self.unloads += 1
        return 0

    def error_string(self, status: int) -> str:
        return f"status={status}"


class _SlotIdentity:
    architecture = "gfx1030"
    identity_hash = "sha256:" + "4" * 64
    kernel_abi_hash = "sha256:" + "6" * 64
    combined_source_sha256 = "sha256:" + "7" * 64


class _GuardIdentity:
    architecture = "gfx1030"
    identity_hash = "sha256:" + "5" * 64
    kernel_abi_hash = "sha256:" + "8" * 64
    combined_source_sha256 = "sha256:" + "9" * 64


def _slot_kernel(
    monkeypatch: pytest.MonkeyPatch,
    loaded_runtime: Any,
) -> tuple[HipRtcFgmresFixedRankCoarseSlotKernelV1, _SlotRuntime]:
    monkeypatch.setattr(
        slot_rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1",
        lambda identity: identity,
    )
    runtime = _SlotRuntime(loaded_runtime)
    functions = {
        symbol: ctypes.c_void_p(index + 9001)
        for index, symbol in enumerate(
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
        )
    }
    return (
        HipRtcFgmresFixedRankCoarseSlotKernelV1(
            runtime=runtime,  # type: ignore[arg-type]
            module=ctypes.c_void_p(9000),
            functions=functions,
            identity=_SlotIdentity(),  # type: ignore[arg-type]
            _mint=slot_rtc_module._KERNEL_MINT,
        ),
        runtime,
    )


def _guard_kernel(
    monkeypatch: pytest.MonkeyPatch,
    loaded_runtime: Any,
) -> tuple[HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1, _SlotRuntime]:
    monkeypatch.setattr(
        guard_rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1",
        lambda identity: identity,
    )
    runtime = _SlotRuntime(loaded_runtime)
    return (
        HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1(
            runtime=runtime,  # type: ignore[arg-type]
            module=ctypes.c_void_p(9100),
            function=ctypes.c_void_p(9101),
            identity=_GuardIdentity(),  # type: ignore[arg-type]
            _mint=guard_rtc_module._KERNEL_MINT,
        ),
        runtime,
    )


def _open_slot_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    open_slot: bool = True,
) -> dict[str, Any]:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        primitive_open,
        _,
        recurrence_kernel,
        loaded,
    ) = _prepare_live_inputs(monkeypatch)
    primitive = primitive_open.context
    assert primitive is not None
    policy = compile_fgmres_policy_v1(restart_dimension=2, max_iterations=4)
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
        rtc_kernel=recurrence_kernel,
    )
    coarse = slot = canonical = None
    try:
        assert live.context is not None
        live_source_plan = live.context._source_plan
        assert live_source_plan is not None
        execution = live_source_plan._source_execution_plan
        basis = np.eye(live_source_plan.free_dof_count, 2, dtype="<f8")
        coarse_space = build_cpu_fgmres_fixed_rank_coarse_space_v1(
            execution,
            basis,
            rank_cap=2,
        )
        coarse_plan = compile_hip_fgmres_fixed_rank_coarse_plan_v1(
            live_source_plan,
            coarse_space,
        )
        coarse_kernel, coarse_api = _coarse_kernel(runtime, coarse_plan)
        coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
            live.context,
            coarse_plan,
            rtc_kernel=coarse_kernel,
        )
        assert coarse.context is not None
        slot_api = guard_api = None
        if open_slot:
            slot_kernel, slot_api = _slot_kernel(monkeypatch, loaded)
            guard_kernel, guard_api = _guard_kernel(monkeypatch, loaded)
            slot = open_hip_fgmres_fixed_rank_coarse_slot_recurrence_v1(
                coarse.context,
                rtc_kernel=slot_kernel,
                terminal_guard_kernel=guard_kernel,
            )
            assert slot.context is not None
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        return {
            "runtime": runtime,
            "parent_open": parent_open,
            "resident_open": resident_open,
            "free_open": free_open,
            "primitive_open": primitive_open,
            "loaded": loaded,
            "recurrence_kernel": recurrence_kernel,
            "live": live,
            "coarse": coarse,
            "coarse_api": coarse_api,
            "slot": slot,
            "slot_api": slot_api,
            "guard_api": guard_api,
            "canonical": canonical,
            "sealed": None,
            "global": None,
        }
    except BaseException:
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        if slot is not None and slot.context is not None and not slot.context.closed:
            slot.context.close()
        if (
            coarse is not None
            and coarse.context is not None
            and not coarse.context.closed
        ):
            coarse.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)
        raise


def _close_slot_stack(stack: dict[str, Any]) -> None:
    global_open = stack.get("global")
    sealed = stack.get("sealed")
    canonical = stack.get("canonical")
    slot = stack.get("slot")
    coarse = stack.get("coarse")
    if global_open is not None and not global_open.context.closed:
        global_open.context.close()
    if sealed is not None and not sealed.context.closed:
        sealed.context.close()
    if canonical is not None and not canonical.context.closed:
        canonical.context.close()
    if slot is not None and slot.context is not None and not slot.context.closed:
        slot.context.close()
    if coarse is not None and coarse.context is not None and not coarse.context.closed:
        coarse.context.close()
    _cleanup(
        stack["live"],
        stack["primitive_open"],
        stack["free_open"],
        stack["resident_open"],
        stack["parent_open"],
    )


def test_all_jacobi_rows_are_replaced_by_one_logical_five_launch_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch)
    context = stack["slot"].context
    recurrence_kernel = stack["recurrence_kernel"]
    assert context is not None
    jacobi_launches = 0
    original_launch_vector = type(recurrence_kernel).launch_vector

    def observe_vector(
        self: Any, _stream: Any, vector_mode: int, *args: Any, **kwargs: Any
    ) -> Any:
        nonlocal jacobi_launches
        if vector_mode == _VECTOR_MODE_CODES["APPLY_JACOBI_INDEXED"]:
            jacobi_launches += 1
        return original_launch_vector(self, _stream, vector_mode, *args, **kwargs)

    monkeypatch.setattr(type(recurrence_kernel), "launch_vector", observe_vector)
    try:
        opening = validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
            stack["slot"].receipt,
            expected_context=context,
        )
        assert stack["slot"].ready
        assert opening.schema_version == (
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_RECURRENCE_RECEIPT_V1_SCHEMA_VERSION
        )
        assert opening.status == "context_ready"
        assert opening.dimensions.expected_application_count == 4
        assert opening.dimensions.total_physical_launches_per_application == 5
        assert not opening.claims.all_scheduled_jacobi_rows_replaced
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        opening_payload = opening.to_dict()
        Draft202012Validator(schema).validate(opening_payload)
        serialized = json.dumps(opening_payload, sort_keys=True)
        for forbidden in (
            "pointer_snapshot",
            "stream_pointer",
            "module_pointer",
            "function_pointer",
            "owner_identity",
            "lease_id",
            "process_token",
        ):
            assert forbidden not in serialized
        assert opening.claims.pointer_values_serialized is False
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(
                {**opening_payload, "unexpected": True}
            )
        shortened_dimensions = replace(
            opening.dimensions,
            expected_application_count=3,
            global_suffix_application_count=2,
        )
        shortened_schedule = _coherently_rehash_slot_receipt(
            opening,
            dimensions=shortened_dimensions,
            context_id=slot_receipt_module._context_id_for(
                opening.bindings,
                shortened_dimensions,
                opening.actual_backend,
            ),
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="receipt_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                shortened_schedule
            )
        forged_rank_dimensions = replace(
            opening.dimensions,
            retained_rank=opening.dimensions.free_dof_count + 1,
        )
        forged_rank = _coherently_rehash_slot_receipt(
            opening,
            dimensions=forged_rank_dimensions,
            context_id=slot_receipt_module._context_id_for(
                opening.bindings,
                forged_rank_dimensions,
                opening.actual_backend,
            ),
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="receipt_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                forged_rank
            )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="nested_type_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                _coherently_rehash_slot_receipt(opening, applications=[])
            )
        forged_reason = _coherently_rehash_slot_receipt(
            opening,
            status="poisoned",
            reason=HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
                "forged_reason",
                "safe detail",
            ),
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="receipt_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                forged_reason
            )
        redacted_forgery = _coherently_rehash_slot_receipt(
            opening,
            status="poisoned",
            reason=HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
                "forged_pointer_detail",
                "unredacted pointer 0xdeadbeef",
            ),
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="receipt_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                redacted_forgery
            )
        oversized_reason = _coherently_rehash_slot_receipt(
            opening,
            status="poisoned",
            reason=HipFgmresFixedRankCoarseSlotRecurrenceReasonV1(
                "hip_fgmres_coarse_slot_recurrence_poisoned",
                "x" * 321,
            ),
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="schema_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                oversized_reason
            )

        _run_recurrence(stack)
        assert jacobi_launches == 0
        assert [
            (row.restart_index, row.column_index, row.logical_index)
            for row in context.applications
        ] == [(1, 0, 0), (1, 1, 1), (2, 0, 0), (2, 1, 1)]
        telemetry = context.telemetry
        assert telemetry.application_attempt_count == 4
        assert telemetry.application_success_count == 4
        assert telemetry.logical_recurrence_launch_count == 4
        assert telemetry.retained_jacobi_launch_count == 0
        assert telemetry.physical_slot_launch_accept_count == 16
        assert telemetry.physical_slot_launch_ack_count == 16
        assert telemetry.physical_terminal_guard_launch_accept_count == 4
        assert telemetry.physical_terminal_guard_launch_ack_count == 4
        assert telemetry.parent_fence_ack_count == 2
        assert context.state == "global_receipt_bound"
        assert all(row.physical_launch_count == 5 for row in context.applications)
        receipt = validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
            context.receipt(),
            expected_context=context,
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="context_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                opening,
                expected_context=context,
            )
        assert receipt.status == "global_receipt_bound"
        assert receipt.application_sequence_hash != slot_receipt_module._ZERO_HASH
        assert [row.schedule_epoch for row in receipt.applications] == sorted(
            row.schedule_epoch for row in receipt.applications
        )
        assert all(
            row.logical_recurrence_launch_count == 1 for row in receipt.applications
        )
        assert all(row.legacy_jacobi_launch_count == 0 for row in receipt.applications)
        assert all(row.physical_slot_launch_count == 4 for row in receipt.applications)
        assert all(
            row.physical_terminal_guard_launch_count == 1
            for row in receipt.applications
        )
        assert receipt.claims.global_recurrence_receipt_bound
        assert receipt.claims.all_scheduled_jacobi_rows_replaced
        assert receipt.claims.one_logical_row_per_five_physical_launches
        assert receipt.claims.same_stream_slot_then_terminal_guard_order_bound
        assert receipt.claims.both_physical_owners_parent_fenced
        assert receipt.claims.device_terminal_status_binding_contract
        assert receipt.claims.application_window_host_copy_zero_contract
        assert receipt.claims.legacy_jacobi_launch_zero_observed
        assert not receipt.claims.actual_integrated_device_execution_proven
        assert not receipt.claims.authoritative_numerical_parity_proven
        assert not receipt.claims.full_iteration_host_copy_zero_proven
        assert not receipt.claims.end_to_end_o_n_proven
        assert not receipt.claims.speedup_proven
        assert not receipt.claims.commercial_ready
        global_receipt = stack["global"].context.receipt()
        assert receipt.global_context_id == global_receipt.context_id
        assert receipt.global_receipt_hash == global_receipt.receipt_hash

        for forged in (
            _coherently_rehash_slot_receipt(receipt, status="context_ready"),
            _coherently_rehash_slot_receipt(
                receipt,
                context_id="sha256:" + "e" * 64,
            ),
            _coherently_rehash_slot_receipt(
                receipt,
                telemetry=replace(
                    receipt.telemetry,
                    physical_terminal_guard_launch_ack_count=3,
                ),
            ),
        ):
            with pytest.raises(HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error):
                validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(forged)
        assert len(stack["slot_api"].launches) == 16
        assert len(stack["guard_api"].launches) == 4
        assert len(stack["coarse_api"].launches) == 0
        assert not context.slot_kernel.pending
        assert not context.terminal_guard_kernel.pending
    finally:
        _close_slot_stack(stack)


def test_slot_context_rejects_close_between_canonical_and_global_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch)
    context = stack["slot"].context
    canonical = stack["canonical"].context
    assert context is not None
    try:
        pending = canonical.enqueue_canonical_predecessor()
        canonical.synchronize_canonical_predecessor(pending)
        assert context.state == "canonical_fenced"
        forged_closed = _coherently_rehash_slot_receipt(
            context.receipt(),
            status="context_closed",
        )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceReceiptV1Error,
            match="receipt_invalid",
        ):
            validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
                forged_closed
            )
        with pytest.raises(
            HipFgmresFixedRankCoarseSlotRecurrenceV1Error,
            match="incomplete",
        ):
            context.close()
    finally:
        context._state = "poisoned"
        _close_slot_stack(stack)


def test_partial_physical_prefix_is_one_ambiguous_logical_row_until_parent_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_slot_stack(monkeypatch)
    context = stack["slot"].context
    canonical = stack["canonical"].context
    assert context is not None
    try:
        canonical_pending = canonical.enqueue_canonical_predecessor()
        capability = canonical.synchronize_canonical_predecessor(canonical_pending)
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical,
            capability,
        )
        stack["sealed"] = sealed
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        stack["global"] = global_open
        stack["slot_api"].launch_outcomes = [0, 7]
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            global_open.context.enqueue_remaining_global_recurrence()
        assert failed.value.pending is not None
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error, match="poisoned"):
            global_open.context.synchronize(failed.value.pending)
        telemetry = context.telemetry
        assert context.state == "poisoned"
        assert telemetry.application_attempt_count == 2
        assert telemetry.application_success_count == 1
        assert telemetry.logical_recurrence_launch_count == 1
        assert telemetry.retained_jacobi_launch_count == 0
        assert telemetry.physical_slot_launch_accept_count == 5
        assert telemetry.physical_slot_launch_ack_count == 5
        assert telemetry.physical_terminal_guard_launch_accept_count == 1
        assert telemetry.physical_terminal_guard_launch_ack_count == 1
        assert telemetry.parent_fence_ack_count == 2
        assert not context.slot_kernel.pending
        assert not context.terminal_guard_kernel.pending
        receipt = validate_hip_fgmres_fixed_rank_coarse_slot_recurrence_receipt_v1(
            context.receipt(),
            expected_context=context,
        )
        assert receipt.status == "poisoned"
        assert receipt.reason is not None
        assert receipt.telemetry.application_attempt_count == 2
        assert receipt.telemetry.application_success_count == 1
        assert receipt.telemetry.physical_slot_launch_accept_count == 5
        assert receipt.telemetry.physical_terminal_guard_launch_accept_count == 1
        assert receipt.telemetry.physical_slot_launch_ack_count == 5
        assert receipt.telemetry.physical_terminal_guard_launch_ack_count == 1
        assert not receipt.claims.global_recurrence_receipt_bound
        assert not receipt.claims.all_scheduled_jacobi_rows_replaced
        assert not receipt.claims.actual_integrated_device_execution_proven
    finally:
        _close_slot_stack(stack)
