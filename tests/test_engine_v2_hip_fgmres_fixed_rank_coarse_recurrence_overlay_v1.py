from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_completion_export_v1 as completion_export_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_recurrence_overlay_v1 as overlay_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    open_hip_fgmres_completion_export_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_context_v1 import (
    HipFgmresFixedRankCoarseContextV1Error,
    open_hip_fgmres_fixed_rank_coarse_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (
    compile_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_recurrence_overlay_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION,
    HipFgmresFixedRankCoarseRecurrenceOverlayV1Error,
    open_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1,
    validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    HipFgmresGlobalRecurrenceV1Error,
    open_hip_fgmres_global_recurrence_context_v1,
    validate_hip_fgmres_global_recurrence_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointContextV1Error,
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
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    observe_hip_fgmres_terminal_outcome_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)

from tests.test_engine_v2_hip_fgmres_fixed_rank_coarse_context_v1 import (
    _coarse_kernel,
)
from tests.test_engine_v2_hip_fgmres_completion_export_v1 import (
    _BlockingCopyProbe,
    _completion_sources,
)
from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _prepare_live_inputs,
)
from tests.test_engine_v2_hip_fgmres_global_recurrence_context_v1 import (
    _InjectedOpcodeInterruption,
    _interrupt_immediately_after_store_attr,
)
from tests.test_engine_v2_hip_fgmres_terminal_outcome_observation_v1 import (
    _terminal_payloads,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1.schema.json"
)


def _coherently_rehash_overlay_receipt(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=overlay_module._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=overlay_module.canonical_hash(
            overlay_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _open_overlay_stack(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
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
    coarse = overlay = canonical = sealed = global_open = None
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
        overlay = open_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1(
            coarse.context
        )
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        return {
            "runtime": runtime,
            "parent_open": parent_open,
            "resident_open": resident_open,
            "free_open": free_open,
            "primitive_open": primitive_open,
            "loaded": loaded,
            "live": live,
            "coarse": coarse,
            "coarse_api": coarse_api,
            "overlay": overlay,
            "canonical": canonical,
            "sealed": sealed,
            "global": global_open,
        }
    except BaseException:
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        if overlay is not None and not overlay.context.closed:
            overlay.context.close()
        if (
            coarse is not None
            and coarse.context is not None
            and not coarse.context.closed
        ):
            coarse.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)
        raise


def _run_recurrence(stack: dict[str, Any]) -> None:
    canonical = stack["canonical"]
    pending = canonical.context.enqueue_canonical_predecessor()
    capability = canonical.context.synchronize_canonical_predecessor(pending)
    sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
        canonical.context,
        capability,
    )
    sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
    continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
        sealed_pending
    )
    global_open = open_hip_fgmres_global_recurrence_context_v1(
        sealed.context,
        continuation,
    )
    global_pending = global_open.context.enqueue_remaining_global_recurrence()
    completion = global_open.context.synchronize(global_pending)
    stack["sealed"] = sealed
    stack["global"] = global_open
    stack["completion"] = completion


def _close_overlay_stack(stack: dict[str, Any]) -> None:
    export = stack.get("export")
    global_open = stack.get("global")
    sealed = stack.get("sealed")
    canonical = stack.get("canonical")
    overlay = stack.get("overlay")
    coarse = stack.get("coarse")
    if export is not None and not export.context.closed:
        export.context.close()
    if global_open is not None and not global_open.context.closed:
        global_open.context.close()
    if sealed is not None and not sealed.context.closed:
        sealed.context.close()
    if canonical is not None and not canonical.context.closed:
        canonical.context.close()
    if overlay is not None and not overlay.context.closed:
        overlay.context.close()
    if coarse is not None and coarse.context is not None and not coarse.context.closed:
        coarse.context.close()
    _cleanup(
        stack["live"],
        stack["primitive_open"],
        stack["free_open"],
        stack["resident_open"],
        stack["parent_open"],
    )


def test_overlay_interleaves_all_fixed_coordinates_and_reuses_parent_fences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    coarse = stack["coarse"].context
    runtime = stack["runtime"]
    assert overlay is not None and coarse is not None
    try:
        opening = validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
            stack["overlay"].receipt,
            expected_context=overlay,
        )
        assert opening.schema_version == (
            HIP_FGMRES_FIXED_RANK_COARSE_RECURRENCE_OVERLAY_V1_SCHEMA_VERSION
        )
        assert opening.status == "context_ready"
        assert opening.dimensions.expected_application_count == 4
        assert not opening.claims.coarse_output_consumed_by_recurrence

        with pytest.raises(
            HipFgmresFixedRankCoarseContextV1Error,
            match="recurrence_overlay_active",
        ):
            coarse.enqueue_application(0)
        coarse_sync_before = len(runtime.sync_streams)
        recurrence_sync_before = len(stack["loaded"].sync_streams)
        _run_recurrence(stack)
        assert len(runtime.sync_streams) - coarse_sync_before == 0
        assert len(stack["loaded"].sync_streams) - recurrence_sync_before == 3

        receipt = validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
            overlay.receipt(),
            expected_context=overlay,
        )
        assert receipt.status == "recurrence_fenced"
        assert [
            (row.restart_index, row.column_index, row.logical_index)
            for row in receipt.applications
        ] == [(1, 0, 0), (1, 1, 1), (2, 0, 0), (2, 1, 1)]
        assert receipt.telemetry.application_success_count == 4
        assert receipt.telemetry.canonical_prefix_application_count == 1
        assert receipt.telemetry.global_suffix_application_count == 3
        assert receipt.telemetry.retained_jacobi_launch_count == 4
        assert receipt.telemetry.coarse_kernel_launch_count == 16
        assert receipt.telemetry.external_parent_fence_ack_count == 2
        assert receipt.telemetry.externally_acknowledged_coarse_launch_count == 16
        assert receipt.telemetry.additional_h2d_copy_count == 0
        assert receipt.telemetry.additional_d2h_copy_count == 0
        assert receipt.telemetry.additional_synchronization_count == 0
        assert receipt.telemetry.additional_csr_apply_count == 0
        assert receipt.claims.fixed_schedule_coordinates_bound
        assert receipt.claims.same_stream_overlay_order_bound
        assert receipt.claims.coarse_output_consumed_by_recurrence
        assert receipt.claims.application_window_host_copy_zero
        assert receipt.claims.no_additional_intermediate_synchronization
        assert receipt.claims.canonical_jacobi_row_retained
        assert not receipt.claims.canonical_jacobi_row_replaced
        assert not receipt.claims.coarse_device_status_directly_terminal_bound
        assert len(stack["coarse_api"].launches) == 16
        assert coarse._kernel is not None and not coarse._kernel.pending
        assert coarse.receipt().telemetry.fence_success_count == 1
        assert coarse.receipt().telemetry.fence_acknowledged_launch_count == 16

        global_receipt = validate_hip_fgmres_global_recurrence_receipt_v1(
            stack["global"].context.receipt(),
            expected_context=stack["global"].context,
        )
        assert global_receipt.status == "recurrence_fenced"
        assert receipt.global_context_id == global_receipt.context_id
        assert receipt.global_receipt_hash == global_receipt.receipt_hash
    finally:
        _close_overlay_stack(stack)


def test_overlay_lifetime_is_exclusive_and_coordinate_forgery_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    coarse = stack["coarse"].context
    live = stack["live"].context
    assert overlay is not None and coarse is not None and live is not None
    try:
        with pytest.raises(
            HipFgmresFixedRankCoarseRecurrenceOverlayV1Error,
            match="coarse_overlay_pristine_context_required|coarse_overlay",
        ):
            open_hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1(coarse)
        with pytest.raises(
            HipFgmresFixedRankCoarseContextV1Error,
            match="recurrence_overlay_child_active",
        ):
            coarse.close()
        with pytest.raises(
            HipFgmresFixedRankCoarseRecurrenceOverlayV1Error,
            match="coordinate_invalid",
        ):
            live._enqueue_fixed_rank_coarse_overlay_after_jacobi(
                phase="canonical_prefix",
                owner=stack["canonical"].context,
                expected_restart=1,
                expected_column=1,
                logical_index=1,
            )
        assert len(stack["coarse_api"].launches) == 0
        _run_recurrence(stack)
        assert overlay.receipt().status == "recurrence_fenced"
        with pytest.raises(
            HipFgmresLiveCheckpointContextV1Error,
            match="canonical_child_active|coarse_child_active|coarse_overlay_active",
        ):
            live.close()
    finally:
        _close_overlay_stack(stack)


def test_overlay_schema_and_hash_forgery_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    assert overlay is not None
    try:
        _run_recurrence(stack)
        receipt = overlay.receipt()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        payload = receipt.to_dict()
        Draft202012Validator(schema).validate(payload)
        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in (
            "pointer_snapshot",
            "owner_identity",
            "lease_id",
            "stream_pointer",
            "module_pointer",
            "function_pointer",
        ):
            assert forbidden not in serialized
        forged = dict(payload)
        forged["unexpected"] = True
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(forged)
        with pytest.raises(HipFgmresFixedRankCoarseRecurrenceOverlayV1Error):
            validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
                replace(receipt, application_sequence_hash="sha256:" + "f" * 64)
            )
        for forged_receipt in (
            _coherently_rehash_overlay_receipt(receipt, status="context_ready"),
            _coherently_rehash_overlay_receipt(
                receipt,
                terminal_observation_receipt_hash="sha256:" + "1" * 64,
                terminal_outcome_hash="sha256:" + "2" * 64,
            ),
            _coherently_rehash_overlay_receipt(
                receipt,
                reason=overlay_module.HipFgmresFixedRankCoarseRecurrenceOverlayReasonV1(
                    "forged_reason",
                    "healthy receipts cannot carry a poison reason",
                ),
            ),
        ):
            with pytest.raises(
                HipFgmresFixedRankCoarseRecurrenceOverlayV1Error,
                match="receipt_invalid",
            ):
                validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
                    forged_receipt
                )
    finally:
        _close_overlay_stack(stack)


def test_overlay_can_close_before_recurrence_without_integrated_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    assert overlay is not None
    try:
        overlay.close()
        receipt = validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
            overlay.receipt(),
            expected_context=overlay,
        )
        assert receipt.status == "context_closed"
        assert receipt.applications == ()
        assert not receipt.claims.fixed_schedule_coordinates_bound
        assert not receipt.claims.same_stream_overlay_order_bound
        assert not receipt.claims.coarse_output_consumed_by_recurrence
        assert not receipt.claims.terminal_observation_bound
    finally:
        _close_overlay_stack(stack)


def test_overlay_rejects_healthy_close_until_parent_fence_acknowledges_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    coarse = stack["coarse"].context
    canonical = stack["canonical"].context
    assert overlay is not None and coarse is not None
    pending = None
    try:
        pending = canonical.enqueue_canonical_predecessor()
        coarse_sync_before = len(stack["runtime"].sync_streams)
        with pytest.raises(
            HipFgmresFixedRankCoarseRecurrenceOverlayV1Error,
            match="parent_fence_required",
        ):
            overlay.close()
        assert not overlay.closed
        assert overlay.receipt().status == "canonical_overlay_pending"
        assert len(stack["runtime"].sync_streams) == coarse_sync_before

        canonical.synchronize_canonical_predecessor(pending)
        pending = None
        assert overlay.receipt().status == "canonical_fenced"
        assert len(stack["runtime"].sync_streams) == coarse_sync_before
        overlay.close()
        assert overlay.closed
    finally:
        if pending is not None and coarse._stream_work_requires_fence:
            canonical.synchronize_canonical_predecessor(pending)
        _close_overlay_stack(stack)


def test_overlay_binds_the_exact_downstream_terminal_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    assert overlay is not None
    try:
        _run_recurrence(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        export = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            stack["completion"],
        )
        stack["export"] = export
        policy = completion_export_module._completion_export_policy_snapshot(
            export.context._authority
        )
        sources = _completion_sources(stack)
        payloads = _terminal_payloads(
            policy,
            sources[0].nbytes // 8,
            "converged_initial_true_residual",
        )
        for source, payload in zip(sources, payloads, strict=True):
            stack["runtime"].allocations[int(source.pointer_snapshot)][:] = payload
        exported = export.context.export()
        observed = observe_hip_fgmres_terminal_outcome_v1(
            exported,
            expected_export_context=export.context,
        )
        receipt = overlay.bind_terminal_observation(observed)
        assert receipt.status == "terminal_bound"
        assert receipt.claims.terminal_observation_bound
        assert (
            receipt.terminal_observation_receipt_hash == observed.receipt.receipt_hash
        )
        assert receipt.terminal_outcome_hash == observed.receipt.outcome_hash
        assert receipt.global_context_id == observed.receipt.bindings.global_context_id
        assert (
            receipt.global_receipt_hash == observed.receipt.bindings.global_receipt_hash
        )
        assert not receipt.claims.coarse_device_status_directly_terminal_bound
        assert not receipt.claims.full_iteration_host_copy_zero_proven
    finally:
        _close_overlay_stack(stack)


def test_overlay_external_fence_ack_store_interruption_recovers_monotonically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    coarse = stack["coarse"].context
    canonical = stack["canonical"].context
    assert overlay is not None and coarse is not None
    try:
        pending = canonical.enqueue_canonical_predecessor()
        capabilities: list[Any] = []
        _interrupt_immediately_after_store_attr(
            type(coarse)._acknowledge_recurrence_overlay_fence,
            "_stream_work_requires_fence",
            lambda: capabilities.append(
                canonical.synchronize_canonical_predecessor(pending)
            ),
        )
        capability = capabilities[0]
        assert capability is not None
        assert overlay.receipt().status == "canonical_fenced"
        assert coarse.receipt().telemetry.fence_acknowledged_launch_count == 4

        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical,
            capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        global_pending = global_open.context.enqueue_remaining_global_recurrence()
        stack["completion"] = global_open.context.synchronize(global_pending)
        stack["sealed"] = sealed
        stack["global"] = global_open
        receipt = overlay.receipt()
        assert receipt.status == "recurrence_fenced"
        assert receipt.telemetry.externally_acknowledged_coarse_launch_count == 16
    finally:
        _close_overlay_stack(stack)


def test_overlay_partial_global_application_poison_is_fenced_and_not_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _open_overlay_stack(monkeypatch)
    overlay = stack["overlay"].context
    coarse = stack["coarse"].context
    canonical = stack["canonical"].context
    assert overlay is not None and coarse is not None
    try:
        canonical_pending = canonical.enqueue_canonical_predecessor()
        capability = canonical.synchronize_canonical_predecessor(canonical_pending)
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical,
            capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        stack["sealed"] = sealed
        stack["global"] = global_open
        stack["coarse_api"].launch_outcomes = [0, 1]
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error) as failed:
            global_open.context.enqueue_remaining_global_recurrence()
        assert failed.value.pending is not None
        with pytest.raises(_InjectedOpcodeInterruption):
            _interrupt_immediately_after_store_attr(
                type(coarse)._acknowledge_recurrence_overlay_fence,
                "_stream_work_requires_fence",
                lambda: global_open.context.synchronize(failed.value.pending),
            )
        interrupted_receipt = coarse.receipt()
        assert interrupted_receipt.telemetry.fence_acknowledged_launch_count == 5
        assert (
            overlay.receipt().telemetry.externally_acknowledged_coarse_launch_count == 4
        )
        with pytest.raises(HipFgmresGlobalRecurrenceV1Error, match="poisoned"):
            global_open.context.synchronize(failed.value.pending)
        receipt = validate_hip_fgmres_fixed_rank_coarse_recurrence_overlay_receipt_v1(
            overlay.receipt(),
            expected_context=overlay,
        )
        assert receipt.status == "poisoned"
        assert receipt.telemetry.application_success_count == 1
        assert receipt.telemetry.retained_jacobi_launch_count == 2
        assert receipt.telemetry.coarse_kernel_launch_count == 5
        assert receipt.telemetry.external_parent_fence_ack_count == 2
        assert receipt.telemetry.externally_acknowledged_coarse_launch_count == 5
        assert len(stack["coarse_api"].launches) == 6
        coarse_receipt = stack["coarse"].context.receipt()
        assert coarse_receipt.telemetry.kernel_launch_success_count == 5
        assert coarse_receipt.telemetry.fence_acknowledged_launch_count == 5
        assert not receipt.claims.fixed_schedule_coordinates_bound
        assert not receipt.claims.coarse_output_consumed_by_recurrence
        assert not receipt.claims.terminal_observation_bound
    finally:
        _close_overlay_stack(stack)
