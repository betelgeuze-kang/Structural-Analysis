"""Actual-gfx1030 evidence for completion-only raw buffer export.

The product receipt remains outcome-free.  CPU comparison happens only after
the immutable three-buffer export receipt has been captured and therefore does
not promote terminal status, parity, or solution readiness claims.
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
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.model_ir import load_model_ir_v2

from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    FIXTURE,
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_COMPLETION_EXPORT_HARDWARE",
        )
    )


class _NativeMemcpyProbe:
    def __init__(self, prior_errcheck: Any) -> None:
        self._prior_errcheck = prior_errcheck
        self.calls: list[tuple[int, int, int]] = []

    def __call__(self, result: int, function: Any, arguments: tuple[Any, ...]) -> int:
        source = arguments[1]
        pointer = getattr(source, "value", source)
        self.calls.append((int(pointer), int(arguments[2]), int(arguments[3])))
        if self._prior_errcheck is not None:
            return self._prior_errcheck(result, function, arguments)
        return result


class _NativeMemcpyErrcheck:
    def __init__(self, operation: Any, probe: _NativeMemcpyProbe) -> None:
        self._operation = operation
        self._probe = probe
        self._prior = getattr(operation, "errcheck", None)

    def __enter__(self) -> None:
        self._operation.errcheck = self._probe

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        if self._prior is None:
            del self._operation.errcheck
        else:
            self._operation.errcheck = self._prior


def test_native_gfx1030_completion_export_materializes_exact_three_raw_buffers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    model = load_model_ir_v2(FIXTURE)
    policy = compile_fgmres_policy_v1(
        restart_dimension=1,
        max_iterations=1,
        relative_tolerance=1.0e-15,
    )
    execution_plan = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    )
    oracle = solve_cpu_fgmres_reference_v1(execution_plan, policy)
    assert len(execution_plan.free_dofs) == 6
    assert oracle.status == "converged"
    assert oracle.iteration_count == 1

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
        live_telemetry = chain.live.receipt().telemetry
        runtime_type = type(runtime)
        kernel_type = type(kernel)
        native_memcpy = runtime._memcpy
        copy_probe = _NativeMemcpyProbe(getattr(native_memcpy, "errcheck", None))
        forbidden_runtime_calls: list[str] = []
        forbidden_fences: list[int] = []

        original_malloc = runtime_type.malloc
        original_h2d = runtime_type.copy_h2d_async
        original_async_d2h = runtime_type.copy_d2h_async
        original_sync = runtime_type.synchronize
        original_fence = kernel_type._synchronize_checkpoint_stream

        def probed_malloc(owner: Any, byte_count: int) -> Any:
            forbidden_runtime_calls.append("malloc")
            return original_malloc(owner, byte_count)

        def probed_h2d(
            owner: Any,
            pointer: Any,
            array: np.ndarray,
            stream: Any,
        ) -> None:
            forbidden_runtime_calls.append("h2d")
            original_h2d(owner, pointer, array, stream)

        def probed_async_d2h(
            owner: Any,
            array: np.ndarray,
            pointer: Any,
            stream: Any,
        ) -> None:
            forbidden_runtime_calls.append("async_d2h")
            original_async_d2h(owner, array, pointer, stream)

        def probed_sync(owner: Any, stream: Any) -> None:
            forbidden_runtime_calls.append("runtime_sync")
            original_sync(owner, stream)

        def probed_fence(owner: Any, token: object, stream: Any) -> None:
            forbidden_fences.append(int(stream))
            original_fence(owner, token, stream)

        with _NativeMemcpyErrcheck(
            native_memcpy,
            copy_probe,
        ), monkeypatch.context() as product_probe:
            product_probe.setattr(runtime_type, "malloc", probed_malloc)
            product_probe.setattr(runtime_type, "copy_h2d_async", probed_h2d)
            product_probe.setattr(runtime_type, "copy_d2h_async", probed_async_d2h)
            product_probe.setattr(runtime_type, "synchronize", probed_sync)
            product_probe.setattr(
                kernel_type,
                "_synchronize_checkpoint_stream",
                probed_fence,
            )

            opened = open_hip_fgmres_completion_export_context_v1(
                global_open.context,
                completion,
            )
            export_context = opened.context
            assert opened.ready
            result = export_context.export_completion_buffers()
            validate_hip_fgmres_completion_export_result_v1(
                result,
                expected_context=export_context,
            )

            expected_pointers = tuple(
                int(chain.canonical._pointers[role])
                for role in ("solution_x", "true_residual", "solve_record")
            )
            assert tuple(pointer for pointer, _size, _kind in copy_probe.calls) == (
                expected_pointers
            )
            assert tuple(size for _pointer, size, _kind in copy_probe.calls) == (
                48,
                48,
                264,
            )
            assert tuple(kind for _pointer, _size, kind in copy_probe.calls) == (
                2,
                2,
                2,
            )
            assert forbidden_runtime_calls == []
            assert forbidden_fences == []

            receipt = result.receipt
            assert receipt.status == "exported"
            assert receipt.actual_backend == "hip"
            assert receipt.telemetry.d2h_operation_attempt_count == 3
            assert receipt.telemetry.d2h_operation_success_count == 3
            assert receipt.telemetry.d2h_bytes_attempted == 360
            assert receipt.telemetry.d2h_bytes_succeeded == 360
            assert receipt.telemetry.blocking_copy_completion_count == 3
            assert receipt.telemetry.device_allocation_count == 0
            assert receipt.telemetry.h2d_operation_count == 0
            assert receipt.telemetry.kernel_launch_count == 0
            assert receipt.telemetry.explicit_stream_sync_count == 0
            assert receipt.telemetry.fallback_count == 0
            assert receipt.telemetry.numerical_content_branch_count == 0
            assert receipt.claims.raw_completion_buffers_host_materialized
            assert not receipt.claims.solve_record_semantics_interpreted
            assert not receipt.claims.actual_terminal_outcome_host_observed
            assert not receipt.claims.authoritative_terminal_status_proven
            assert not receipt.claims.numerical_parity_verified
            assert not receipt.claims.solution_ready
            assert not receipt.claims.result_ir_ready
            assert not receipt.claims.iteration_host_copy_zero_proven
            assert not receipt.claims.performance_or_speedup_proven
            assert not receipt.claims.commercial_ready
            assert not receipt.claims.promotion_eligible

            # Verification-only interpretation occurs after receipt publication.
            assert np.array_equal(result.solution_x_array, oracle.reduced_solution)
            assert np.array_equal(result.true_residual_array, oracle.true_residual)
            assert len(result.solve_record) == 264
            assert global_open.context.receipt() == global_receipt
            assert chain.live.receipt().telemetry == live_telemetry

            export_context.close()
            assert validate_hip_fgmres_completion_export_result_v1(result) is result
    finally:
        if export_context is not None and not export_context.closed:
            export_context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()
