"""Actual-gfx1030 evidence for terminal-outcome observation.

The observer runs only after the completion exporter has published its exact
three-buffer receipt.  Runtime and kernel probes cover the complete observer
call, while CPU comparison is deliberately delayed until the independent
observation receipt has been published and validated.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    open_hip_fgmres_completion_export_context_v1,
    validate_hip_fgmres_completion_export_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    observe_hip_fgmres_terminal_outcome_v1,
    validate_hip_fgmres_terminal_outcome_observation_receipt_v1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)

from tests.test_engine_v2_hip_fgmres_completion_export_hardware_v1 import (
    _NativeMemcpyErrcheck,
    _NativeMemcpyProbe,
)
from tests.test_engine_v2_hip_fgmres_global_recurrence_context_hardware_v1 import (
    _serial_cantilever_model,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_TERMINAL_OUTCOME_HARDWARE",
        )
    )


@pytest.mark.parametrize(
    (
        "node_count",
        "max_iterations",
        "relative_tolerance",
        "expected_observation_status",
        "expected_outcome_class",
        "expected_terminal_status",
        "expected_termination_code",
        "expected_restart_count",
        "expected_operator_count",
        "expected_record_bytes",
    ),
    (
        (
            3,
            2,
            1.0e-15,
            "terminal_converged",
            "converged",
            "converged",
            "converged_happy_breakdown",
            1,
            4,
            264,
        ),
        (
            5,
            4,
            1.0e-30,
            "terminal_not_converged",
            "not_converged",
            "max_iterations",
            "max_iterations_exhausted",
            2,
            7,
            336,
        ),
    ),
    ids=("later_column_convergence", "active_final_guard_max_iterations"),
)
def test_native_gfx1030_observer_publishes_terminal_outcome_without_device_calls(
    monkeypatch: pytest.MonkeyPatch,
    node_count: int,
    max_iterations: int,
    relative_tolerance: float,
    expected_observation_status: str,
    expected_outcome_class: str,
    expected_terminal_status: str,
    expected_termination_code: str,
    expected_restart_count: int,
    expected_operator_count: int,
    expected_record_bytes: int,
) -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = _serial_cantilever_model(node_count)
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=max_iterations,
        absolute_tolerance=0.0,
        relative_tolerance=relative_tolerance,
    )
    execution_plan = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    )
    free_dof_count = 6 * (node_count - 1)
    assert len(execution_plan.free_dofs) == free_dof_count

    chain, predecessor_capability = _open_canonical_chain(
        model=model,
        architecture=architecture,
        required=required,
        policy=policy,
    )
    sealed = global_open = export_context = None
    try:
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
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
        global_receipt = global_open.context.receipt()

        runtime = chain.live._runtime
        kernel = chain.live._kernel
        assert runtime is not None and kernel is not None
        native_memcpy = runtime._memcpy
        native_copy_probe = _NativeMemcpyProbe(getattr(native_memcpy, "errcheck", None))

        with _NativeMemcpyErrcheck(native_memcpy, native_copy_probe):
            opened = open_hip_fgmres_completion_export_context_v1(
                global_open.context,
                completion,
            )
            export_context = opened.context
            assert opened.ready
            export_result = export_context.export_completion_buffers()
            validate_hip_fgmres_completion_export_result_v1(
                export_result,
                expected_context=export_context,
            )

            vector_bytes = free_dof_count * 8
            assert tuple(size for _pointer, size, _kind in native_copy_probe.calls) == (
                vector_bytes,
                vector_bytes,
                expected_record_bytes,
            )
            assert tuple(kind for _pointer, _size, kind in native_copy_probe.calls) == (
                2,
                2,
                2,
            )
            export_receipt = export_result.receipt
            export_receipt_identity = id(export_receipt)
            export_manifest = export_receipt.to_dict()
            assert export_receipt.status == "exported"
            assert export_receipt.actual_backend == "hip"
            assert export_receipt.dimensions.free_dof_count == free_dof_count
            assert export_receipt.dimensions.solve_record_byte_count == (
                expected_record_bytes
            )
            assert export_receipt.telemetry.d2h_operation_attempt_count == 3
            assert export_receipt.telemetry.d2h_operation_success_count == 3
            assert export_receipt.telemetry.d2h_bytes_attempted == (
                2 * vector_bytes + expected_record_bytes
            )
            assert export_receipt.telemetry.d2h_bytes_succeeded == (
                2 * vector_bytes + expected_record_bytes
            )
            assert export_receipt.telemetry.blocking_copy_completion_count == 3
            assert export_receipt.telemetry.device_allocation_count == 0
            assert export_receipt.telemetry.h2d_operation_count == 0
            assert export_receipt.telemetry.kernel_launch_count == 0
            assert export_receipt.telemetry.explicit_stream_sync_count == 0
            assert not export_receipt.claims.solve_record_semantics_interpreted
            assert not export_receipt.claims.actual_terminal_outcome_host_observed

            observer_calls: list[str] = []
            runtime_type = type(runtime)
            kernel_type = type(kernel)

            def probe_method(label: str, original: Any) -> Any:
                def probed(owner: Any, *args: Any, **kwargs: Any) -> Any:
                    observer_calls.append(label)
                    return original(owner, *args, **kwargs)

                return probed

            monitored_methods = (
                (runtime_type, "malloc", "device_alloc"),
                (runtime_type, "copy_h2d_async", "h2d"),
                (runtime_type, "copy_d2h_async", "d2h_async"),
                (runtime_type, "copy_d2h", "d2h_blocking"),
                (runtime_type, "synchronize", "runtime_sync"),
                (kernel_type, "launch_control", "kernel_control"),
                (kernel_type, "launch_vector", "kernel_vector"),
                (kernel_type, "launch_csr_spmv_indexed", "kernel_spmv"),
                (kernel_type, "launch_reduction", "kernel_reduction"),
                (
                    kernel_type,
                    "_synchronize_checkpoint_stream",
                    "checkpoint_sync",
                ),
            )
            with monkeypatch.context() as observer_probe:
                for owner_type, method_name, label in monitored_methods:
                    original = getattr(owner_type, method_name)
                    observer_probe.setattr(
                        owner_type,
                        method_name,
                        probe_method(label, original),
                    )

                observation = observe_hip_fgmres_terminal_outcome_v1(
                    export_result,
                    expected_export_context=export_context,
                )
                validate_hip_fgmres_terminal_outcome_observation_result_v1(
                    observation,
                    expected_export_result=export_result,
                    expected_export_context=export_context,
                )

            assert observer_calls == []
            assert len(native_copy_probe.calls) == 3

        receipt = observation.receipt
        validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
            receipt,
            expected_export_result=export_result,
            expected_export_context=export_context,
        )
        assert receipt.status == expected_observation_status
        assert receipt.actual_backend == "hip"
        assert receipt.outcome.outcome_class == expected_outcome_class
        assert receipt.outcome.terminal_status == expected_terminal_status
        assert receipt.outcome.termination_code == expected_termination_code
        assert receipt.outcome.active == 0
        assert receipt.outcome.device_error_bits == 0
        assert receipt.outcome.record_metrics_authoritative
        assert receipt.outcome.metrics is not None
        assert receipt.outcome.true_residual_record_metrics_match
        assert receipt.outcome.counters.scheduled_iterations == max_iterations
        assert receipt.outcome.counters.effective_iterations == max_iterations
        assert receipt.outcome.counters.scheduled_restarts == expected_restart_count
        assert receipt.outcome.counters.effective_restarts == expected_restart_count
        assert receipt.outcome.counters.operator_apply_count == expected_operator_count
        assert receipt.outcome.counters.preconditioner_apply_count == max_iterations
        assert len(receipt.outcome.restart_rows) == expected_restart_count
        assert all(row.populated for row in receipt.outcome.restart_rows)
        assert receipt.telemetry.additional_d2h_operation_count == 0
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.device_allocation_count == 0
        assert receipt.telemetry.allocation_borrow_count == 0
        assert receipt.telemetry.kernel_launch_count == 0
        assert receipt.telemetry.explicit_stream_sync_count == 0
        assert receipt.telemetry.fallback_count == 0
        assert receipt.claims.raw_export_receipt_preserved
        assert receipt.claims.solve_record_semantics_interpreted
        assert receipt.claims.actual_terminal_outcome_host_observed
        assert receipt.claims.process_local_export_provenance_verified
        assert receipt.claims.authoritative_terminal_status_proven
        assert receipt.claims.no_additional_device_operation
        assert not receipt.claims.authoritative_completion_or_solution_receipt
        assert not receipt.claims.numerical_parity_verified
        assert not receipt.claims.solution_ready
        assert not receipt.claims.result_ir_ready
        assert not receipt.claims.iteration_host_copy_zero_proven
        assert not receipt.claims.performance_or_speedup_proven
        assert not receipt.claims.commercial_ready
        assert not receipt.claims.promotion_eligible

        assert id(export_result.receipt) == export_receipt_identity
        assert export_result.receipt is export_receipt
        assert export_result.receipt.to_dict() == export_manifest
        assert not export_result.receipt.claims.solve_record_semantics_interpreted
        assert not export_result.receipt.claims.actual_terminal_outcome_host_observed
        assert global_open.context.receipt() == global_receipt

        # Test-only CPU verification occurs strictly after observer publication.
        oracle = solve_cpu_fgmres_reference_v1(execution_plan, policy)
        assert oracle.status == expected_terminal_status
        assert oracle.termination_code == expected_termination_code
        assert oracle.iteration_count == max_iterations
        assert oracle.restart_count == expected_restart_count
        np.testing.assert_allclose(
            export_result.solution_x_array,
            oracle.reduced_solution,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
        np.testing.assert_allclose(
            export_result.true_residual_array,
            oracle.true_residual,
            rtol=2.0e-13,
            atol=2.0e-15,
        )
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()
