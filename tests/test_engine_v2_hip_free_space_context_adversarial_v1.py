from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceApplyClaims,
    HipFreeSpaceContextError,
    _apply_payload,
    _context_payload,
    _evaluation_payload,
    open_hip_free_space_execution_context,
    validate_hip_free_space_apply_receipt,
    validate_hip_free_space_context_receipt,
    validate_hip_free_space_evaluation,
    validate_hip_free_space_evaluation_receipt,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    open_hip_resident_csr_execution_context,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.state_ir import (
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)

from tests.test_engine_v2_hip_free_space_context_v1 import (
    FakeFreeSpaceKernel,
    _close_chain,
    _open_free_space,
)
from tests.test_engine_v2_hip_resident_csr_v1 import (
    FakeResidualKernel,
    _open_parent,
)


_FORGED_HASH = "sha256:" + "a" * 64


def _rehash_context(receipt: Any) -> Any:
    return replace(
        receipt,
        context_receipt_hash=canonical_hash(
            _context_payload(receipt, include_hash=False)
        ),
    )


def _rehash_apply(receipt: Any) -> Any:
    return replace(
        receipt,
        receipt_hash=canonical_hash(_apply_payload(receipt, include_hash=False)),
    )


def _rehash_evaluation(receipt: Any) -> Any:
    return replace(
        receipt,
        receipt_hash=canonical_hash(_evaluation_payload(receipt, include_hash=False)),
    )


def test_public_committed_state_rejects_nonzero_constrained_dof_before_child_work() -> (
    None
):
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None

    accepted = create_initial_state(plan)
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    constrained = plan.array("constrained_dofs")
    assert constrained.size > 0
    displacement[int(constrained[0])] = 1.25
    trial = open_trial_state(accepted, displacement, expected_plan=plan)
    committed = commit_trial_state(accepted, trial, expected_plan=plan)
    assert committed.role == "committed"
    residual_kernel = FakeResidualKernel(runtime)
    resident_open = open_hip_resident_csr_execution_context(
        parent,
        committed,
        architecture="gfx1030",
        rtc_kernel=residual_kernel,
    )
    resident = resident_open.context
    assert resident is not None and resident_open.ready
    overlay = compile_hip_free_space_operator_plan_v1(plan)
    free_space_kernel = FakeFreeSpaceKernel(runtime)
    before = (
        runtime.malloc_calls,
        runtime.sync_calls,
        resident._downstream_consumer_epoch_value,
    )
    try:
        with pytest.raises(HipFreeSpaceContextError) as caught:
            open_hip_free_space_execution_context(
                resident,
                overlay,
                architecture="gfx1030",
                rtc_kernel=free_space_kernel,
            )
        assert caught.value.code == (
            "hip_free_space_nonzero_constrained_state_unsupported"
        )
        assert (
            runtime.malloc_calls,
            runtime.sync_calls,
            resident._downstream_consumer_epoch_value,
        ) == before
        assert resident._downstream_consumer_token is None
        assert not free_space_kernel.materialize_calls
        assert not free_space_kernel.closed
    finally:
        if not resident.closed:
            resident.close()
        if not parent.closed:
            parent.close()


def test_public_state_ir_canonicalizes_negative_zero_to_positive_zero() -> None:
    _, plan, _, _, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    try:
        accepted = create_initial_state(plan)
        displacement = np.zeros(plan.dof_count, dtype="<f8")
        constrained = plan.array("constrained_dofs")
        displacement[int(constrained[0])] = -0.0
        trial = open_trial_state(accepted, displacement, expected_plan=plan)
        committed = commit_trial_state(accepted, trial, expected_plan=plan)
        assert committed.displacement_si[int(constrained[0])] == 0.0
        assert not np.signbit(committed.displacement_si[int(constrained[0])])
    finally:
        parent.close()


def test_verification_reports_exact_negative_full_residual_free_relation() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        parity = evaluation.receipt.parity
        assert evaluation.receipt.status == "verified"
        assert parity is not None
        metric = parity.residual_direction_vs_negative_full_residual_free
        free = context._plan.array("free_dofs")
        assert evaluation.residual_direction is not None
        assert evaluation.full_residual is not None
        expected = -evaluation.full_residual[free]
        assert np.array_equal(evaluation.residual_direction, expected)
        assert np.allclose(
            evaluation.residual_direction, expected, atol=1.0e-8, rtol=1.0e-8
        )
        assert metric.count == context._overlay.free_dof_count
        assert metric.max_abs_error == 0.0
        assert metric.max_scaled_error == 0.0
        assert metric.passed
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_caller_overlay_mutation_cannot_rebind_live_context_receipt() -> None:
    *_, parent_open, resident_open, overlay, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    opening = opened.receipt
    original_hash = overlay.plan_hash
    try:
        object.__setattr__(overlay, "plan_hash", _FORGED_HASH)
        assert context._overlay is not overlay
        current = context.receipt()
        assert current.bindings == opening.bindings
        assert current.context_id == opening.context_id
        assert current.context_receipt_hash == opening.context_receipt_hash
        validate_hip_free_space_context_receipt(current, expected_context=context)
        assert context.evaluate_for_verification().receipt.status == "verified"
    finally:
        object.__setattr__(overlay, "plan_hash", original_hash)
        _close_chain(opened, resident_open, parent_open)


@pytest.mark.parametrize("mutation", ("owned-overlay", "owned-pointer"))
def test_live_authority_mutation_fails_closed_before_direction_launch(
    mutation: str,
) -> None:
    *_, parent_open, resident_open, _, kernel, opened = _open_free_space()
    context = opened.context
    assert context is not None
    restore: tuple[str, Any] | None = None
    try:
        if mutation == "owned-overlay":
            restore = ("overlay", context._overlay.plan_hash)
            object.__setattr__(context._overlay, "plan_hash", _FORGED_HASH)
        else:
            restore = ("pointer", context._pointers["reduced_direction"])
            context._pointers["reduced_direction"] = context._pointers[
                "reduced_residual"
            ]

        with pytest.raises(HipFreeSpaceContextError) as caught:
            context.enqueue_operator_apply()
        assert caught.value.code in {
            "hip_free_space_runtime_authority_changed",
            "hip_free_space_owned_pointer_changed",
        }
        assert not kernel.direction_calls
        assert context.poisoned
    finally:
        if restore is not None and restore[0] == "overlay":
            object.__setattr__(context._overlay, "plan_hash", restore[1])
        elif restore is not None:
            context._pointers["reduced_direction"] = restore[1]
        _close_chain(opened, resident_open, parent_open)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("name", "renamed_reduced_state"),
        ("dtype", "<i4"),
        ("access", "read_write"),
    ),
)
def test_rehashed_standalone_context_work_buffer_forge_is_rejected(
    field: str,
    value: str,
) -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        buffers = list(opened.receipt.owned_buffers)
        index = next(
            index for index, view in enumerate(buffers) if view.name == "reduced_state"
        )
        buffers[index] = replace(buffers[index], **{field: value})
        forged = _rehash_context(replace(opened.receipt, owned_buffers=tuple(buffers)))
        with pytest.raises(HipFreeSpaceContextError) as caught:
            validate_hip_free_space_context_receipt(forged)
        assert caught.value.code == ("hip_free_space_context_buffer_semantics_invalid")
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_rehashed_apply_generation_forge_needs_live_context_witness() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        receipt = context.enqueue_operator_apply()
        assert receipt.status == "enqueued"
        assert receipt.direction_generation is not None
        generation = receipt.direction_generation + 1
        draft = replace(
            receipt,
            direction_generation=generation,
            apply_id=canonical_hash(
                {
                    "context_id": receipt.context_id,
                    "sequence": receipt.sequence,
                    "direction_generation": generation,
                }
            ),
        )
        forged = _rehash_apply(draft)
        validate_hip_free_space_apply_receipt(forged)
        with pytest.raises(HipFreeSpaceContextError) as caught:
            validate_hip_free_space_apply_receipt(forged, expected_context=context)
        assert caught.value.code == ("hip_free_space_apply_context_binding_mismatch")
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_gather_failure_preserves_completed_stage_claims_and_nested_receipt() -> None:
    *_, parent_open, resident_open, _, kernel, opened = _open_free_space(
        fail_stage="gather"
    )
    context = opened.context
    assert context is not None
    try:
        receipt = context.enqueue_operator_apply()
        assert receipt.status == "unavailable"
        assert receipt.reason is not None
        assert receipt.reason.code == "hip_free_space_gather_launch_failed"
        assert receipt.direction_generation is not None
        assert receipt.resident_enqueue is not None
        assert receipt.resident_enqueue.status == "enqueued"
        assert receipt.resident_enqueue_receipt_hash == (
            receipt.resident_enqueue.receipt_hash
        )
        assert receipt.resident_enqueue_sequence == receipt.resident_enqueue.sequence
        assert receipt.telemetry_delta.producer_launch_success_count == 1
        assert receipt.telemetry_delta.resident_launch_success_count == 1
        assert receipt.telemetry_delta.gather_launch_attempt_count == 1
        assert receipt.telemetry_delta.gather_launch_success_count == 0
        assert receipt.claims == HipFreeSpaceApplyClaims(True, True, True, False)
        assert len(kernel.direction_calls) == 1
        assert len(kernel.gather_calls) == 1
        validate_hip_free_space_apply_receipt(receipt, expected_context=context)
    finally:
        _close_chain(opened, resident_open, parent_open)


@pytest.mark.parametrize("field", ("shape", "byte_length", "data_hash"))
def test_rehashed_evaluation_descriptor_forge_is_rejected(field: str) -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        entries = list(evaluation.receipt.arrays)
        index = next(
            index for index, entry in enumerate(entries) if entry[0] == "reduced_state"
        )
        name, descriptor = entries[index]
        value: Any
        if field == "shape":
            value = (descriptor.shape[0] + 1,)
        elif field == "byte_length":
            value = descriptor.byte_length + 8
        else:
            value = _FORGED_HASH
        entries[index] = (name, replace(descriptor, **{field: value}))
        forged_receipt = _rehash_evaluation(
            replace(evaluation.receipt, arrays=tuple(entries))
        )
        forged = replace(evaluation, receipt=forged_receipt)
        with pytest.raises(HipFreeSpaceContextError):
            validate_hip_free_space_evaluation(forged, expected_context=context)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_rehashed_evaluation_parity_count_and_transfer_byte_forges_are_rejected() -> (
    None
):
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        receipt = evaluation.receipt
        assert receipt.parity is not None

        forged_metric = replace(
            receipt.parity.reduced_state,
            count=receipt.parity.reduced_state.count + 1,
        )
        forged_parity = replace(receipt.parity, reduced_state=forged_metric)
        forged_count = _rehash_evaluation(replace(receipt, parity=forged_parity))
        with pytest.raises(HipFreeSpaceContextError) as count_error:
            validate_hip_free_space_evaluation_receipt(forged_count)
        assert count_error.value.code == (
            "hip_free_space_evaluation_parity_count_invalid"
        )

        forged_delta = replace(
            receipt.telemetry_delta,
            d2h_bytes_attempted=receipt.telemetry_delta.d2h_bytes_attempted + 8,
            d2h_bytes_succeeded=receipt.telemetry_delta.d2h_bytes_succeeded + 8,
        )
        forged_bytes = _rehash_evaluation(
            replace(receipt, telemetry_delta=forged_delta)
        )
        with pytest.raises(HipFreeSpaceContextError) as byte_error:
            validate_hip_free_space_evaluation_receipt(forged_bytes)
        assert byte_error.value.code == "hip_free_space_evaluation_byte_count_invalid"
    finally:
        _close_chain(opened, resident_open, parent_open)
