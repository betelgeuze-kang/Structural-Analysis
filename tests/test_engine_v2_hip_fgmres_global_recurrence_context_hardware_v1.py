"""Actual-gfx1030 integration evidence for the global recurrence owner.

The three-node serial cantilever needs the second Arnoldi column to converge.
That column is outside the sealed first-column prefix, so the test observes a
numerically active sealed-continuation -> global-suffix handoff rather than an
already-terminal padded program.  The product-path probes cover the global
owner only; verification D2H is deliberately performed after those probes and
after the immutable product receipt has been captured.

The five-node cases separately prove active later restarts, partial-final-cycle
checkpoint terminalization, and an exact full-final-cycle handoff whose active
``FINAL_GUARD`` claims the last schedule epoch.  Product receipts remain
outcome-free; verification-only D2H never upgrades their claims.
"""

from __future__ import annotations

import copy
import gc
import json
import os
from typing import Any
import weakref

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
    validate_hip_fgmres_global_recurrence_completion_capability_v1,
    validate_hip_fgmres_global_recurrence_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
    validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.model_ir import parse_model_ir_v2

from tests.test_engine_v2_hip_fgmres_initial_hardware_v2 import (
    _f64,
    _field_offsets,
    _i32,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    FIXTURE,
    _download_bytes,
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_GLOBAL_RECURRENCE_CONTEXT_HARDWARE",
        )
    )


def _serial_cantilever_model(node_count: int) -> Any:
    assert node_count >= 2
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["model_id"] = f"global-recurrence-owner-{node_count}-node-cantilever"
    payload["provenance"]["source_ref"] = (
        f"generated:global-recurrence-owner-{node_count}-node-cantilever"
    )

    node_template = payload["nodes"][0]
    payload["nodes"] = []
    for index in range(node_count):
        node = copy.deepcopy(node_template)
        node.update(
            id=f"N{index + 1}",
            index=index,
            coordinates_m=[float(2 * index), 0.0, 0.0],
            source_id=f"generated:N{index + 1}",
        )
        payload["nodes"].append(node)

    element_template = payload["elements"][0]
    payload["elements"] = []
    for index in range(node_count - 1):
        element = copy.deepcopy(element_template)
        element.update(
            id=f"E{index + 1}",
            index=index,
            node_ids=[f"N{index + 1}", f"N{index + 2}"],
            source_id=f"generated:E{index + 1}",
        )
        payload["elements"].append(element)

    axial_pattern = payload["load_patterns"][0]
    axial_pattern["nodal_loads"][0].update(
        id=f"L_AXIAL_N{node_count}",
        node_id=f"N{node_count}",
        source_id=f"generated:L_AXIAL_N{node_count}",
    )
    payload["load_patterns"] = [axial_pattern]
    return parse_model_ir_v2(payload)


def _three_node_serial_cantilever_model() -> Any:
    return _serial_cantilever_model(3)


def test_native_gfx1030_sealed_continuation_executes_active_global_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = _three_node_serial_cantilever_model()
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=2,
        relative_tolerance=1.0e-15,
    )
    execution_plan = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    )
    oracle = solve_cpu_fgmres_reference_v1(execution_plan, policy)
    assert oracle.status == "converged"
    assert oracle.termination_code == "converged_happy_breakdown"
    assert oracle.iteration_count == 2
    assert oracle.restart_count == 1
    assert oracle.operator_apply_count == 4
    assert oracle.preconditioner_apply_count == 2

    chain, predecessor_capability = _open_canonical_chain(
        model=model,
        architecture=architecture,
        required=required,
        policy=policy,
    )
    sealed = global_open = None
    try:
        canonical_receipt = chain.canonical.receipt()
        assert canonical_receipt.telemetry.fence_success_count == 1
        assert canonical_receipt.telemetry.h2d_operation_count == 0
        assert canonical_receipt.telemetry.d2h_operation_count == 0
        assert canonical_receipt.telemetry.intermediate_sync_count == 0

        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        sealed_receipt = sealed.context.receipt()
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            sealed_receipt,
            expected_context=sealed.context,
        )
        assert sealed_receipt.telemetry.kernel_launch_attempt_count == 4
        assert sealed_receipt.telemetry.consumed_launch_count == 4
        assert sealed_receipt.telemetry.fence_success_count == 1
        assert sealed_receipt.telemetry.h2d_operation_count == 0
        assert sealed_receipt.telemetry.d2h_operation_count == 0
        assert sealed_receipt.telemetry.intermediate_sync_count == 0

        partition = compile_hip_fgmres_global_sealed_continuation_v1(12, 2, 2)
        assert partition.plan.reduction_stage_count == 1
        assert partition.plan.maximum_restart_count == 1
        assert partition.plan.final_schedule_epoch == 79
        assert partition.plan.final_reduction_epoch == 26
        assert partition.plan.schedule_end_epoch == 80
        assert partition.full.launch_count == 84
        assert partition.sealed_prefix.launch_count == 45
        assert partition.continuation.launch_count == 39
        assert partition.continuation.launches[0].name == (
            "APPLY_JACOBI_RESTART1_COLUMN1"
        )
        assert partition.continuation.launches[0].expected_schedule_epoch == 43
        assert partition.continuation.launches[0].expected_restart == 1
        assert partition.continuation.launches[0].expected_column == 1
        assert partition.continuation.launches[-1].name == "FINAL_GUARD"
        assert partition.continuation.launches[-1].expected_schedule_epoch == 79
        assert partition.continuation.launches[-1].expected_reduction_epoch == 26

        kernel = chain.live._kernel
        runtime = chain.live._runtime
        assert kernel is not None and runtime is not None
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()
        live_telemetry_before = chain.live.receipt().telemetry
        assembly_telemetry_before = chain.assembly.receipt().telemetry

        product_runtime_calls: list[str] = []
        product_fences: list[tuple[bool, int]] = []
        runtime_type = type(runtime)
        kernel_type = type(kernel)
        original_malloc = runtime_type.malloc
        original_copy_h2d = runtime_type.copy_h2d_async
        original_copy_d2h = runtime_type.copy_d2h_async
        original_runtime_sync = runtime_type.synchronize
        original_checkpoint_fence = kernel_type._synchronize_checkpoint_stream

        def probed_malloc(owner: Any, byte_length: int) -> Any:
            product_runtime_calls.append("malloc")
            return original_malloc(owner, byte_length)

        def probed_copy_h2d(
            owner: Any,
            pointer: Any,
            array: np.ndarray,
            stream: Any,
        ) -> None:
            product_runtime_calls.append("h2d")
            original_copy_h2d(owner, pointer, array, stream)

        def probed_copy_d2h(
            owner: Any,
            array: np.ndarray,
            pointer: Any,
            stream: Any,
        ) -> None:
            product_runtime_calls.append("d2h")
            original_copy_d2h(owner, array, pointer, stream)

        def probed_runtime_sync(owner: Any, stream: Any) -> None:
            product_runtime_calls.append("runtime_sync")
            original_runtime_sync(owner, stream)

        def probed_checkpoint_fence(
            owner: Any,
            token: object,
            stream: Any,
        ) -> None:
            product_fences.append((owner is kernel, int(stream)))
            original_checkpoint_fence(owner, token, stream)

        # Only the final checkpoint-owner fence is allowed inside this scope.
        # Verification copies and their synchronization occur after restoration.
        with monkeypatch.context() as product_probe:
            product_probe.setattr(runtime_type, "malloc", probed_malloc)
            product_probe.setattr(runtime_type, "copy_h2d_async", probed_copy_h2d)
            product_probe.setattr(runtime_type, "copy_d2h_async", probed_copy_d2h)
            product_probe.setattr(runtime_type, "synchronize", probed_runtime_sync)
            product_probe.setattr(
                kernel_type,
                "_synchronize_checkpoint_stream",
                probed_checkpoint_fence,
            )

            global_open = open_hip_fgmres_global_recurrence_context_v1(
                sealed.context,
                continuation,
            )
            opening_receipt = global_open.receipt
            validate_hip_fgmres_global_recurrence_receipt_v1(
                opening_receipt,
                expected_context=global_open.context,
            )
            assert global_open.ready
            assert opening_receipt.actual_backend == "hip"
            assert opening_receipt.dimensions.free_dof_count == 12
            assert opening_receipt.dimensions.reduced_csr_nnz == 144
            assert opening_receipt.dimensions.restart_dimension == 2
            assert opening_receipt.dimensions.max_iterations == 2
            assert opening_receipt.dimensions.maximum_restart_count == 1
            assert opening_receipt.dimensions.reduction_stage_count == 1
            assert opening_receipt.dimensions.full_program_launch_count == 84
            assert opening_receipt.dimensions.sealed_prefix_launch_count == 45
            assert opening_receipt.dimensions.continuation_launch_count == 39
            assert opening_receipt.bindings.global_full_schedule_hash == (
                partition.full.canonical_sha256
            )
            assert opening_receipt.bindings.sealed_prefix_schedule_hash == (
                partition.sealed_prefix.canonical_sha256
            )
            assert opening_receipt.bindings.continuation_schedule_hash == (
                partition.continuation.canonical_sha256
            )

            pending = global_open.context.enqueue_remaining_global_recurrence()
            assert pending.attempted_launch_count == 39
            assert pending.accepted_launch_count_lower_bound == 39
            assert pending.accepted_launch_count_upper_bound == 39
            assert kernel._checkpoint_pending_snapshot(
                chain.live._checkpoint_token
            ) == ((chain.live._stream_pointer_snapshot, 39),)
            assert product_runtime_calls == []
            assert product_fences == []

            completion = global_open.context.synchronize(pending)
            assert (
                validate_hip_fgmres_global_recurrence_completion_capability_v1(
                    completion,
                    expected_context=global_open.context,
                )
                is completion
            )
            assert completion.fenced_launch_count == 39
            assert (
                kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()
            )
            assert product_runtime_calls == []
            assert product_fences == [(True, chain.live._stream_pointer_snapshot)]

            product_receipt = global_open.context.receipt()
            validate_hip_fgmres_global_recurrence_receipt_v1(
                product_receipt,
                expected_context=global_open.context,
            )
            assert product_receipt.status == "recurrence_fenced"
            assert (
                product_receipt.telemetry.continuation_capability_reservation_count == 1
            )
            assert product_receipt.telemetry.continuation_capability_consume_count == 1
            assert product_receipt.telemetry.kernel_launch_attempt_count == 39
            assert product_receipt.telemetry.kernel_launch_accept_lower_bound == 39
            assert product_receipt.telemetry.kernel_launch_accept_upper_bound == 39
            assert product_receipt.telemetry.fence_attempt_count == 1
            assert product_receipt.telemetry.fence_success_count == 1
            assert product_receipt.telemetry.pending_consume_attempt_count == 1
            assert product_receipt.telemetry.consumed_launch_count == 39
            assert product_receipt.telemetry.allocation_count == 0
            assert product_receipt.telemetry.allocation_borrow_count == 0
            assert product_receipt.telemetry.checkpoint_owner_acquire_count == 0
            assert product_receipt.telemetry.module_load_count == 0
            assert product_receipt.telemetry.module_unload_count == 0
            assert product_receipt.telemetry.h2d_operation_count == 0
            assert product_receipt.telemetry.d2h_operation_count == 0
            assert product_receipt.telemetry.intermediate_sync_count == 0
            assert product_receipt.telemetry.fallback_count == 0
            assert product_receipt.telemetry.live_state_host_read_count == 0
            assert product_receipt.telemetry.live_state_host_branch_count == 0
            assert product_receipt.claims.fixed_suffix_fenced
            assert product_receipt.claims.completion_capability_issued
            assert product_receipt.claims.no_additional_allocation_or_borrow
            assert product_receipt.claims.no_h2d_or_d2h_copy
            assert product_receipt.claims.no_intermediate_synchronization
            assert product_receipt.claims.no_live_state_host_read_or_branch
            assert not product_receipt.claims.actual_terminal_outcome_host_observed
            assert not product_receipt.claims.authoritative_terminal_status_proven
            assert not product_receipt.claims.numerical_parity_verified
            assert not product_receipt.claims.solution_ready
            assert not product_receipt.claims.performance_or_speedup_proven
            assert not product_receipt.claims.commercial_ready
            assert not product_receipt.claims.promotion_eligible

        assert (
            canonical_receipt.telemetry.fence_success_count
            + sealed_receipt.telemetry.fence_success_count
            + product_receipt.telemetry.fence_success_count
            == 3
        )
        assert chain.live.receipt().telemetry == live_telemetry_before
        assert chain.assembly.receipt().telemetry == assembly_telemetry_before

        # Verification-only observation: these calls are outside the product
        # probe scope and are never reflected in the owner receipt or claims.
        observed = _download_bytes(
            runtime,
            chain.live._stream,
            chain.canonical._pointers,
            chain.canonical._owned_byte_lengths,
            (
                "solution_x",
                "true_residual",
                "fgmres_control_state_v2",
                "solve_record",
            ),
        )
        control_abi = hip_fgmres_control_state_abi_payload_v2()
        record_abi = hip_fgmres_solve_record_abi_payload_v2()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        control = observed["fgmres_control_state_v2"].tobytes()
        record = observed["solve_record"].tobytes()

        assert (
            _i32(control, control_offsets, "phase")
            == (control_abi["phase_codes"]["terminal"])
        )
        assert _i32(control, control_offsets, "restart_index") == 1
        assert _i32(control, control_offsets, "cycle_start_iteration") == 0
        assert _i32(control, control_offsets, "cycle_width") == 2
        assert _i32(control, control_offsets, "column_index") == 1
        assert _i32(control, control_offsets, "arnoldi_step_count") == 2
        assert _i32(control, control_offsets, "reorthogonalization_count") == 2
        assert _i32(control, control_offsets, "commit_required") == 0
        assert _i32(control, control_offsets, "continuation_required") == 0
        assert _i32(control, control_offsets, "failure_origin") == 0
        assert _i32(control, control_offsets, "next_expected_restart") == 2
        assert _i32(control, control_offsets, "schedule_epoch") == 79
        assert _i32(control, control_offsets, "reduction_epoch") == 26

        assert _i32(record, record_offsets, "active") == 0
        assert (
            _i32(record, record_offsets, "terminal_status")
            == (record_abi["terminal_status_codes"]["converged"])
        )
        assert (
            _i32(record, record_offsets, "termination_code")
            == (record_abi["termination_codes"]["converged_happy_breakdown"])
        )
        assert _i32(record, record_offsets, "device_error_bits") == 0
        assert _i32(record, record_offsets, "scheduled_iterations") == 2
        assert _i32(record, record_offsets, "effective_iterations") == 2
        assert _i32(record, record_offsets, "scheduled_restarts") == 1
        assert _i32(record, record_offsets, "effective_restarts") == 1
        assert _i32(record, record_offsets, "effective_arnoldi_dimension") == 2
        assert _i32(record, record_offsets, "happy_breakdown_count") == 1
        assert _i32(record, record_offsets, "stagnation_checkpoint_count") == 0
        assert _i32(record, record_offsets, "false_convergence_count") == 0
        assert _i32(record, record_offsets, "operator_apply_count") == 4
        assert _i32(record, record_offsets, "preconditioner_apply_count") == 2
        assert _f64(record, record_offsets, "initial_residual_l2") == (
            oracle.initial_residual_l2
        )
        assert _f64(record, record_offsets, "final_residual_l2") == (
            oracle.final_residual_l2
        )
        assert _f64(record, record_offsets, "final_residual_linf") == (
            oracle.final_residual_linf
        )
        assert _f64(record, record_offsets, "final_scaled_residual") == (
            oracle.scaled_true_residual
        )

        solution = observed["solution_x"].view("<f8")
        residual = observed["true_residual"].view("<f8")
        assert np.array_equal(solution, oracle.reduced_solution)
        assert np.array_equal(residual, oracle.true_residual)

        receipt_after_observation = global_open.context.receipt()
        assert receipt_after_observation == product_receipt
        assert receipt_after_observation.receipt_hash == product_receipt.receipt_hash
        assert receipt_after_observation.telemetry.d2h_operation_count == 0
        assert receipt_after_observation.telemetry.intermediate_sync_count == 0
        assert (
            not receipt_after_observation.claims.actual_terminal_outcome_host_observed
        )
        assert not receipt_after_observation.claims.numerical_parity_verified
    finally:
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()


def test_native_gfx1030_parent_recovers_abandoned_consumed_global_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = _three_node_serial_cantilever_model()
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=2,
        relative_tolerance=1.0e-15,
    )
    chain, predecessor_capability = _open_canonical_chain(
        model=model,
        architecture=architecture,
        required=required,
        policy=policy,
    )
    sealed = None
    try:
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        partition = compile_hip_fgmres_global_sealed_continuation_v1(12, 2, 2)
        assert partition.continuation.launch_count == 39

        kernel = chain.live._kernel
        runtime = chain.live._runtime
        token = chain.live._checkpoint_token
        stream = chain.live._stream_pointer_snapshot
        assert kernel is not None and runtime is not None
        assert kernel._checkpoint_pending_snapshot(token) == ()

        runtime_calls: list[str] = []
        query_observations: list[tuple[bool, bool, int, bool]] = []
        successful_syncs: list[tuple[bool, bool, int]] = []
        runtime_type = type(runtime)
        kernel_type = type(kernel)
        original_malloc = runtime_type.malloc
        original_copy_h2d = runtime_type.copy_h2d_async
        original_copy_d2h = runtime_type.copy_d2h_async
        original_runtime_sync = runtime_type.synchronize
        original_query = kernel_type._query_checkpoint_stream_completion
        original_checkpoint_sync = kernel_type._synchronize_checkpoint_stream

        def probed_malloc(owner: Any, byte_length: int) -> Any:
            runtime_calls.append("malloc")
            return original_malloc(owner, byte_length)

        def probed_copy_h2d(
            owner: Any,
            pointer: Any,
            array: np.ndarray,
            target_stream: Any,
        ) -> None:
            runtime_calls.append("h2d")
            original_copy_h2d(owner, pointer, array, target_stream)

        def probed_copy_d2h(
            owner: Any,
            array: np.ndarray,
            pointer: Any,
            target_stream: Any,
        ) -> None:
            runtime_calls.append("d2h")
            original_copy_d2h(owner, array, pointer, target_stream)

        def probed_runtime_sync(owner: Any, target_stream: Any) -> None:
            runtime_calls.append("runtime_sync")
            original_runtime_sync(owner, target_stream)

        def probed_query(
            owner: Any,
            checkpoint_token: object,
            target_stream: Any,
        ) -> bool:
            result = original_query(owner, checkpoint_token, target_stream)
            query_observations.append(
                (
                    owner is kernel,
                    checkpoint_token is token,
                    int(target_stream),
                    result,
                )
            )
            return result

        def probed_checkpoint_sync(
            owner: Any,
            checkpoint_token: object,
            target_stream: Any,
        ) -> None:
            original_checkpoint_sync(owner, checkpoint_token, target_stream)
            successful_syncs.append(
                (
                    owner is kernel,
                    checkpoint_token is token,
                    int(target_stream),
                )
            )

        with monkeypatch.context() as product_probe:
            product_probe.setattr(runtime_type, "malloc", probed_malloc)
            product_probe.setattr(runtime_type, "copy_h2d_async", probed_copy_h2d)
            product_probe.setattr(runtime_type, "copy_d2h_async", probed_copy_d2h)
            product_probe.setattr(runtime_type, "synchronize", probed_runtime_sync)
            product_probe.setattr(
                kernel_type,
                "_query_checkpoint_stream_completion",
                probed_query,
            )
            product_probe.setattr(
                kernel_type,
                "_synchronize_checkpoint_stream",
                probed_checkpoint_sync,
            )

            def open_enqueue_and_abandon() -> weakref.ReferenceType[Any]:
                opened = open_hip_fgmres_global_recurrence_context_v1(
                    sealed.context,
                    continuation,
                )
                context = opened.context
                context_reference = weakref.ref(context)
                opening_receipt = opened.receipt
                assert opening_receipt.actual_backend == "hip"
                assert opening_receipt.dimensions.free_dof_count == 12
                assert opening_receipt.dimensions.restart_dimension == 2
                assert opening_receipt.dimensions.max_iterations == 2
                assert opening_receipt.dimensions.continuation_launch_count == 39
                assert opening_receipt.telemetry.allocation_count == 0
                assert opening_receipt.telemetry.h2d_operation_count == 0
                assert opening_receipt.telemetry.d2h_operation_count == 0
                assert opening_receipt.telemetry.fallback_count == 0

                pending = context.enqueue_remaining_global_recurrence()
                assert pending.attempted_launch_count == 39
                assert pending.accepted_launch_count_lower_bound == 39
                assert pending.accepted_launch_count_upper_bound == 39
                assert kernel._checkpoint_pending_snapshot(token) == ((stream, 39),)
                recovery = sealed.context._global_recurrence_recovery_snapshot()
                assert recovery is not None
                assert recovery.continuation_consumed
                assert recovery.launch_attempt_count == 39
                assert recovery.launch_accept_lower_bound == 39
                assert recovery.launch_accept_upper_bound == 39
                assert not recovery.released
                assert not recovery.terminal
                return context_reference

            context_reference = open_enqueue_and_abandon()
            for _ in range(3):
                gc.collect()
            assert context_reference() is None
            abandoned = sealed.context._global_recurrence_recovery_snapshot()
            assert abandoned is not None
            assert abandoned.abandoned
            assert not abandoned.child_live
            assert abandoned.continuation_consumed
            assert kernel._checkpoint_pending_snapshot(token) == ((stream, 39),)

            sealed.context.close()
            recovered = sealed.context._global_recurrence_recovery_snapshot()
            assert recovered is not None
            assert recovered.abandoned
            assert not recovered.child_live
            assert recovered.continuation_consumed
            assert recovered.launch_limit == 39
            assert recovered.launch_attempt_count == 39
            assert recovered.launch_accept_lower_bound == 39
            assert recovered.launch_accept_upper_bound == 39
            assert recovered.fence_observed
            assert recovered.ack_started
            assert recovered.acknowledged_launch_count == 39
            assert recovered.released
            assert recovered.terminal
            assert kernel._checkpoint_pending_snapshot(token) == ()

        assert runtime_calls == []
        assert query_observations
        assert all(
            owner_matches and token_matches and observed_stream == stream
            for owner_matches, token_matches, observed_stream, _ in query_observations
        )
        query_results = tuple(row[3] for row in query_observations)
        assert query_results in {(True,), (False, True)}
        assert len(successful_syncs) <= 1
        assert all(
            owner_matches and token_matches and observed_stream == stream
            for owner_matches, token_matches, observed_stream in successful_syncs
        )
        assert len(successful_syncs) == (0 if query_results == (True,) else 1)
        assert recovered.fence_attempt_count == len(successful_syncs)

        # No verification D2H, numerical comparison, completion capability, or
        # terminal solver claim is produced by this lifecycle-only evidence.
    finally:
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()


@pytest.mark.parametrize(
    "max_iterations",
    (5, 4),
    ids=("partial_final_cycle", "active_final_guard_full_cycle"),
)
def test_native_gfx1030_global_owner_executes_active_later_restarts(
    monkeypatch: pytest.MonkeyPatch,
    max_iterations: int,
) -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = _serial_cantilever_model(5)
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=max_iterations,
        absolute_tolerance=0.0,
        relative_tolerance=1.0e-30,
    )
    execution_plan = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    )
    oracle = solve_cpu_fgmres_reference_v1(execution_plan, policy)
    assert len(execution_plan.free_dofs) == 24
    assert execution_plan.reduced_nnz == 360
    assert oracle.status == "max_iterations"
    assert oracle.termination_code == "max_iterations_exhausted"
    expected = {
        5: {
            "restart_count": 3,
            "operator_count": 9,
            "preconditioner_count": 5,
            "plan_final_schedule": 215,
            "plan_final_reduction": 70,
            "plan_schedule_end": 216,
            "full_launches": 228,
            "suffix_launches": 183,
            "cycle_start": 4,
            "cycle_width": 1,
            "column_index": 0,
            "observed_schedule": 179,
            "observed_reduction": 58,
            "active_final_guard": False,
        },
        4: {
            "restart_count": 2,
            "operator_count": 7,
            "preconditioner_count": 4,
            "plan_final_schedule": 147,
            "plan_final_reduction": 48,
            "plan_schedule_end": 148,
            "full_launches": 156,
            "suffix_launches": 111,
            "cycle_start": 2,
            "cycle_width": 2,
            "column_index": 1,
            "observed_schedule": 148,
            "observed_reduction": 48,
            "active_final_guard": True,
        },
    }[max_iterations]
    expected_restarts = int(expected["restart_count"])
    expected_suffix_launches = int(expected["suffix_launches"])
    assert oracle.iteration_count == max_iterations
    assert oracle.restart_count == expected_restarts
    assert oracle.operator_apply_count == expected["operator_count"]
    assert oracle.preconditioner_apply_count == expected["preconditioner_count"]
    assert tuple(row.restart_index for row in oracle.history) == tuple(
        range(1, expected_restarts + 1)
    )

    chain, predecessor_capability = _open_canonical_chain(
        model=model,
        architecture=architecture,
        required=required,
        policy=policy,
    )
    sealed = global_open = None
    try:
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        sealed_receipt = sealed.context.receipt()
        assert sealed_receipt.telemetry.fence_success_count == 1

        partition = compile_hip_fgmres_global_sealed_continuation_v1(
            24, 2, max_iterations
        )
        assert partition.plan.reduction_stage_count == 1
        assert partition.plan.maximum_restart_count == expected_restarts
        assert partition.plan.final_schedule_epoch == expected["plan_final_schedule"]
        assert partition.plan.final_reduction_epoch == expected["plan_final_reduction"]
        assert partition.plan.schedule_end_epoch == expected["plan_schedule_end"]
        assert partition.full.launch_count == expected["full_launches"]
        assert partition.sealed_prefix.launch_count == 45
        assert partition.continuation.launch_count == expected_suffix_launches
        assert partition.continuation.launches[0].name == (
            "APPLY_JACOBI_RESTART1_COLUMN1"
        )
        assert any(
            row.name == "RESTART_BEGIN_RESTART2"
            for row in partition.continuation.launches
        )
        assert any(
            row.name == "RESTART_BEGIN_RESTART3"
            for row in partition.continuation.launches
        ) == (expected_restarts == 3)
        assert partition.continuation.launches[-1].name == "FINAL_GUARD"

        kernel = chain.live._kernel
        runtime = chain.live._runtime
        assert kernel is not None and runtime is not None
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()
        product_runtime_calls: list[str] = []
        product_fences: list[tuple[bool, int]] = []
        runtime_type = type(runtime)
        kernel_type = type(kernel)
        original_malloc = runtime_type.malloc
        original_copy_h2d = runtime_type.copy_h2d_async
        original_copy_d2h = runtime_type.copy_d2h_async
        original_runtime_sync = runtime_type.synchronize
        original_checkpoint_fence = kernel_type._synchronize_checkpoint_stream

        def probed_malloc(owner: Any, byte_length: int) -> Any:
            product_runtime_calls.append("malloc")
            return original_malloc(owner, byte_length)

        def probed_copy_h2d(
            owner: Any,
            pointer: Any,
            array: np.ndarray,
            stream: Any,
        ) -> None:
            product_runtime_calls.append("h2d")
            original_copy_h2d(owner, pointer, array, stream)

        def probed_copy_d2h(
            owner: Any,
            array: np.ndarray,
            pointer: Any,
            stream: Any,
        ) -> None:
            product_runtime_calls.append("d2h")
            original_copy_d2h(owner, array, pointer, stream)

        def probed_runtime_sync(owner: Any, stream: Any) -> None:
            product_runtime_calls.append("runtime_sync")
            original_runtime_sync(owner, stream)

        def probed_checkpoint_fence(
            owner: Any,
            token: object,
            stream: Any,
        ) -> None:
            product_fences.append((owner is kernel, int(stream)))
            original_checkpoint_fence(owner, token, stream)

        with monkeypatch.context() as product_probe:
            product_probe.setattr(runtime_type, "malloc", probed_malloc)
            product_probe.setattr(runtime_type, "copy_h2d_async", probed_copy_h2d)
            product_probe.setattr(runtime_type, "copy_d2h_async", probed_copy_d2h)
            product_probe.setattr(runtime_type, "synchronize", probed_runtime_sync)
            product_probe.setattr(
                kernel_type,
                "_synchronize_checkpoint_stream",
                probed_checkpoint_fence,
            )

            global_open = open_hip_fgmres_global_recurrence_context_v1(
                sealed.context,
                continuation,
            )
            opening_receipt = global_open.receipt
            validate_hip_fgmres_global_recurrence_receipt_v1(
                opening_receipt,
                expected_context=global_open.context,
            )
            assert opening_receipt.actual_backend == "hip"
            assert opening_receipt.dimensions.free_dof_count == 24
            assert opening_receipt.dimensions.reduced_csr_nnz == 360
            assert opening_receipt.dimensions.restart_dimension == 2
            assert opening_receipt.dimensions.max_iterations == max_iterations
            assert opening_receipt.dimensions.maximum_restart_count == expected_restarts
            assert (
                opening_receipt.dimensions.full_program_launch_count
                == expected["full_launches"]
            )
            assert opening_receipt.dimensions.sealed_prefix_launch_count == 45
            assert (
                opening_receipt.dimensions.continuation_launch_count
                == expected_suffix_launches
            )

            pending = global_open.context.enqueue_remaining_global_recurrence()
            assert pending.attempted_launch_count == expected_suffix_launches
            assert pending.accepted_launch_count_lower_bound == expected_suffix_launches
            assert pending.accepted_launch_count_upper_bound == expected_suffix_launches
            assert kernel._checkpoint_pending_snapshot(
                chain.live._checkpoint_token
            ) == ((chain.live._stream_pointer_snapshot, expected_suffix_launches),)
            assert product_runtime_calls == []
            assert product_fences == []

            completion = global_open.context.synchronize(pending)
            assert (
                validate_hip_fgmres_global_recurrence_completion_capability_v1(
                    completion,
                    expected_context=global_open.context,
                )
                is completion
            )
            assert completion.fenced_launch_count == expected_suffix_launches
            assert (
                kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()
            )
            assert product_runtime_calls == []
            assert product_fences == [(True, chain.live._stream_pointer_snapshot)]

            product_receipt = global_open.context.receipt()
            validate_hip_fgmres_global_recurrence_receipt_v1(
                product_receipt,
                expected_context=global_open.context,
            )
            assert product_receipt.status == "recurrence_fenced"
            assert (
                product_receipt.telemetry.kernel_launch_attempt_count
                == expected_suffix_launches
            )
            assert (
                product_receipt.telemetry.kernel_launch_accept_lower_bound
                == expected_suffix_launches
            )
            assert (
                product_receipt.telemetry.kernel_launch_accept_upper_bound
                == expected_suffix_launches
            )
            assert (
                product_receipt.telemetry.consumed_launch_count
                == expected_suffix_launches
            )
            assert product_receipt.telemetry.fence_success_count == 1
            assert product_receipt.telemetry.allocation_count == 0
            assert product_receipt.telemetry.h2d_operation_count == 0
            assert product_receipt.telemetry.d2h_operation_count == 0
            assert product_receipt.telemetry.intermediate_sync_count == 0
            assert product_receipt.telemetry.fallback_count == 0
            assert product_receipt.telemetry.live_state_host_read_count == 0
            assert product_receipt.telemetry.live_state_host_branch_count == 0
            assert product_receipt.claims.fixed_suffix_fenced
            assert product_receipt.claims.no_additional_allocation_or_borrow
            assert product_receipt.claims.no_h2d_or_d2h_copy
            assert product_receipt.claims.no_intermediate_synchronization
            assert product_receipt.claims.no_live_state_host_read_or_branch
            assert not product_receipt.claims.actual_terminal_outcome_host_observed
            assert not product_receipt.claims.numerical_parity_verified
            assert not product_receipt.claims.performance_or_speedup_proven
            assert not product_receipt.claims.commercial_ready

        observed = _download_bytes(
            runtime,
            chain.live._stream,
            chain.canonical._pointers,
            chain.canonical._owned_byte_lengths,
            (
                "solution_x",
                "true_residual",
                "fgmres_control_state_v2",
                "solve_record",
            ),
        )
        control_abi = hip_fgmres_control_state_abi_payload_v2()
        record_abi = hip_fgmres_solve_record_abi_payload_v2()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        control = observed["fgmres_control_state_v2"].tobytes()
        record = observed["solve_record"].tobytes()

        assert (
            _i32(control, control_offsets, "phase")
            == control_abi["phase_codes"]["terminal"]
        )
        assert _i32(control, control_offsets, "restart_index") == expected_restarts
        assert (
            _i32(control, control_offsets, "cycle_start_iteration")
            == expected["cycle_start"]
        )
        assert _i32(control, control_offsets, "cycle_width") == expected["cycle_width"]
        assert (
            _i32(control, control_offsets, "column_index") == expected["column_index"]
        )
        assert (
            _i32(control, control_offsets, "arnoldi_step_count")
            == expected["cycle_width"]
        )
        assert (
            _i32(control, control_offsets, "next_expected_restart")
            == expected_restarts + 1
        )
        observed_schedule = _i32(control, control_offsets, "schedule_epoch")
        assert observed_schedule == expected["observed_schedule"]
        assert (
            _i32(control, control_offsets, "reduction_epoch")
            == expected["observed_reduction"]
        )
        if expected["active_final_guard"]:
            assert observed_schedule == partition.plan.schedule_end_epoch
            assert observed_schedule == partition.plan.final_schedule_epoch + 1
        else:
            assert observed_schedule < partition.plan.final_schedule_epoch

        assert _i32(record, record_offsets, "active") == 0
        assert (
            _i32(record, record_offsets, "terminal_status")
            == record_abi["terminal_status_codes"]["max_iterations"]
        )
        assert (
            _i32(record, record_offsets, "termination_code")
            == record_abi["termination_codes"]["max_iterations_exhausted"]
        )
        assert _i32(record, record_offsets, "device_error_bits") == 0
        assert _i32(record, record_offsets, "scheduled_iterations") == max_iterations
        assert _i32(record, record_offsets, "effective_iterations") == max_iterations
        assert _i32(record, record_offsets, "scheduled_restarts") == expected_restarts
        assert _i32(record, record_offsets, "effective_restarts") == expected_restarts
        assert (
            _i32(record, record_offsets, "effective_arnoldi_dimension")
            == expected["cycle_width"]
        )
        assert (
            _i32(record, record_offsets, "operator_apply_count")
            == expected["operator_count"]
        )
        assert (
            _i32(record, record_offsets, "preconditioner_apply_count")
            == expected["preconditioner_count"]
        )

        np.testing.assert_allclose(
            observed["solution_x"].view("<f8"),
            oracle.reduced_solution,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
        np.testing.assert_allclose(
            observed["true_residual"].view("<f8"),
            oracle.true_residual,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
        receipt_after_observation = global_open.context.receipt()
        assert receipt_after_observation == product_receipt
        assert (
            not receipt_after_observation.claims.actual_terminal_outcome_host_observed
        )
        assert not receipt_after_observation.claims.numerical_parity_verified
    finally:
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()
