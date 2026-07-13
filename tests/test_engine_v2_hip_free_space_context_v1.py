from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import free_space_rtc
from structural_analysis.engine_v2.assembly_backend.free_space import (
    HipFreeSpaceContextError,
    _context_payload,
    open_hip_free_space_execution_context,
    validate_hip_free_space_context_receipt,
    validate_hip_free_space_evaluation,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity

from tests.test_engine_v2_hip_resident_csr_v1 import _open_resident

ROOT = Path(__file__).resolve().parents[1]


class FakeFreeSpaceKernel:
    def __init__(
        self,
        runtime: Any,
        *,
        fail_stage: str | None = None,
        close_failures: int = 0,
    ) -> None:
        self.runtime = runtime
        self.fail_stage = fail_stage
        self.close_failures = close_failures
        self.closed = False
        self.close_calls = 0
        self.materialize_calls: list[tuple[Any, ...]] = []
        self.direction_calls: list[tuple[Any, ...]] = []
        self.gather_calls: list[tuple[Any, ...]] = []
        self.identity = free_space_rtc._build_identity(
            architecture="gfx1030",
            source_hash=free_space_rtc._sha256_bytes(free_space_rtc._fixed_source()),
            options=("--offload-arch=gfx1030", "-O3", "-std=c++17"),
            rtc_version=(9, 1),
            rtc_library=HipRtcLibraryIdentity(
                discovery_source="injected",
                requested_name="fake-libhiprtc.so",
                loaded_name="fake-libhiprtc.so",
                resolved_path="/fake/libhiprtc.so",
                sha256="sha256:" + "2" * 64,
            ),
            runtime_library=HipRuntimeLibraryIdentity(
                discovery_source="injected",
                requested_name="fake-libamdhip64.so",
                loaded_name="fake-libamdhip64.so",
                resolved_path=None,
                sha256="sha256:" + "1" * 64,
            ),
            code_object=b"fake-free-space-code-object",
        )

    def _array(self, pointer: int, dtype: str, count: int) -> np.ndarray:
        return np.frombuffer(
            self.runtime.allocations[pointer], dtype=dtype, count=count
        )

    def launch_materialize(self, *arguments: Any) -> None:
        self.materialize_calls.append(arguments)
        if self.fail_stage == "materialize":
            raise RuntimeError("injected materialize failure")
        (
            _,
            global_count,
            full_nnz,
            free_count,
            reduced_nnz,
            free_pointer,
            map_pointer,
            full_values_pointer,
            full_state_pointer,
            full_load_pointer,
            reduced_values_pointer,
            reduced_state_pointer,
            reduced_load_pointer,
            _,
        ) = arguments
        free = self._array(free_pointer, "<i4", free_count)
        mapping = self._array(map_pointer, "<i4", reduced_nnz)
        full_values = self._array(full_values_pointer, "<f8", full_nnz)
        full_state = self._array(full_state_pointer, "<f8", global_count)
        full_load = self._array(full_load_pointer, "<f8", global_count)
        self._array(reduced_values_pointer, "<f8", reduced_nnz)[:] = full_values[
            mapping
        ]
        self._array(reduced_state_pointer, "<f8", free_count)[:] = full_state[free]
        self._array(reduced_load_pointer, "<f8", free_count)[:] = full_load[free]

    def launch_residual_direction(self, *arguments: Any) -> None:
        self.direction_calls.append(arguments)
        if self.fail_stage == "direction":
            raise RuntimeError("injected direction failure")
        (
            _,
            global_count,
            free_count,
            reduced_nnz,
            global_to_free_pointer,
            row_pointer,
            column_pointer,
            values_pointer,
            state_pointer,
            load_pointer,
            direction_pointer,
            residual_pointer,
            full_direction_pointer,
            _,
        ) = arguments
        global_to_free = self._array(global_to_free_pointer, "<i4", global_count)
        row = self._array(row_pointer, "<i4", free_count + 1)
        columns = self._array(column_pointer, "<i4", reduced_nnz)
        values = self._array(values_pointer, "<f8", reduced_nnz)
        state = self._array(state_pointer, "<f8", free_count)
        load = self._array(load_pointer, "<f8", free_count)
        reduced_direction = self._array(direction_pointer, "<f8", free_count)
        reduced_residual = self._array(residual_pointer, "<f8", free_count)
        full_direction = self._array(full_direction_pointer, "<f8", global_count)
        full_direction[:] = 0.0
        for global_index, reduced_row in enumerate(global_to_free):
            if int(reduced_row) < 0:
                continue
            begin, end = int(row[reduced_row]), int(row[reduced_row + 1])
            value = load[reduced_row] - np.dot(
                values[begin:end], state[columns[begin:end]]
            )
            reduced_direction[reduced_row] = value
            reduced_residual[reduced_row] = value
            full_direction[global_index] = value

    def launch_gather_jvp(self, *arguments: Any) -> None:
        self.gather_calls.append(arguments)
        if self.fail_stage == "gather":
            raise RuntimeError("injected gather failure")
        (
            _,
            global_count,
            free_count,
            free_pointer,
            full_jvp_pointer,
            reduced_jvp_pointer,
            _,
        ) = arguments
        free = self._array(free_pointer, "<i4", free_count)
        full_jvp = self._array(full_jvp_pointer, "<f8", global_count)
        self._array(reduced_jvp_pointer, "<f8", free_count)[:] = full_jvp[free]

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected free-space close failure")
        self.closed = True


def _open_free_space(**kernel_options: Any) -> tuple[Any, ...]:
    *prefix, runtime, _, _, parent_open, resident_open = _open_resident()
    resident = resident_open.context
    assert resident is not None
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime, **kernel_options)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    return *prefix, runtime, parent_open, resident_open, overlay, kernel, opened


def _close_chain(opened: Any, resident_open: Any, parent_open: Any) -> None:
    if opened.context is not None and not opened.context.closed:
        opened.context.close()
    if resident_open.context is not None and not resident_open.context.closed:
        resident_open.context.close()
    if parent_open.context is not None and not parent_open.context.closed:
        parent_open.context.close()


def test_open_materializes_reduced_values_without_numeric_h2d() -> None:
    *_, runtime, parent_open, resident_open, overlay, kernel, opened = (
        _open_free_space()
    )
    context = opened.context
    assert context is not None and opened.ready
    try:
        receipt = opened.receipt
        assert receipt.telemetry.allocation_success_count == 12
        assert receipt.telemetry.reduced_numeric_h2d_bytes == 0
        assert receipt.telemetry.state_h2d_bytes == 0
        assert receipt.telemetry.load_h2d_bytes == 0
        assert receipt.telemetry.direction_h2d_bytes == 0
        assert receipt.telemetry.h2d_operation_success_count == 6
        assert receipt.telemetry.symbolic_h2d_bytes == (
            overlay.described_array_byte_length
        )
        assert len(kernel.materialize_calls) == 1
        assert receipt.claims.reduced_csr_device_materialized
        assert receipt.claims.device_direction_producer_ready
        assert not receipt.claims.krylov_iteration_ready
        symbolic_names = (
            "free_dofs",
            "global_to_free",
            "reduced_csr_row_ptr",
            "reduced_csr_column_indices",
            "reduced_csr_global_value_indices",
        )
        for uploaded, name in zip(
            runtime.h2d_arrays[-6:-1], symbolic_names, strict=True
        ):
            assert np.array_equal(uploaded, overlay.array(name))
            assert uploaded is not overlay.array(name)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_device_direction_is_single_consumed_by_resident_jvp_with_cpu_parity() -> None:
    *_, parent_open, resident_open, _, kernel, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    assert context is not None and resident is not None
    try:
        evaluation = context.evaluate_for_verification()
        assert evaluation.receipt.status == "verified"
        assert evaluation.receipt.parity is not None
        assert evaluation.receipt.parity.passed
        assert evaluation.apply is not None
        assert evaluation.apply.status == "enqueued"
        assert evaluation.apply.telemetry_delta.h2d_operation_count == 0
        assert evaluation.apply.telemetry_delta.d2h_operation_count == 0
        assert evaluation.apply.telemetry_delta.sync_count == 0
        assert len(kernel.direction_calls) == 1
        assert len(kernel.gather_calls) == 1
        constrained = resident._plan.array("constrained_dofs")
        assert np.array_equal(
            evaluation.full_direction[constrained],
            np.zeros(constrained.size, dtype="<f8"),
        )
        assert not np.signbit(evaluation.full_direction[constrained]).any()
        validate_hip_free_space_evaluation(evaluation, expected_context=context)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_active_free_space_child_blocks_both_parent_closes_before_work() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and resident is not None and parent is not None
    resident_sync = resident._telemetry.sync_attempt_count
    parent_sync = parent._telemetry.assembly_sync_attempt_count
    with pytest.raises(Exception, match="downstream_consumer_active"):
        resident.close()
    with pytest.raises(Exception, match="resident_consumer_active"):
        parent.close()
    assert resident._telemetry.sync_attempt_count == resident_sync
    assert parent._telemetry.assembly_sync_attempt_count == parent_sync
    _close_chain(opened, resident_open, parent_open)


def test_direction_launch_failure_poison_is_shared_without_publication() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space(
        fail_stage="direction"
    )
    context = opened.context
    resident = resident_open.context
    parent = parent_open.context
    assert context is not None and resident is not None and parent is not None
    try:
        generation = resident._direction_generation
        receipt = context.enqueue_operator_apply()
        assert receipt.status == "unavailable"
        assert context.poisoned and resident.poisoned and parent.poisoned
        assert resident._direction_generation == generation
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_context_receipt_rehashed_solver_claim_is_rejected() -> None:
    *_, parent_open, resident_open, _, _, opened = _open_free_space()
    context = opened.context
    assert context is not None
    try:
        forged = replace(
            opened.receipt,
            claims=replace(opened.receipt.claims, solver_ready=True),
        )
        forged = replace(
            forged,
            context_receipt_hash=canonical_hash(
                _context_payload(forged, include_hash=False)
            ),
        )
        with pytest.raises(HipFreeSpaceContextError):
            validate_hip_free_space_context_receipt(forged)
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_materialize_failure_releases_all_child_resources_and_lease() -> None:
    *_, parent_open, resident_open, _, kernel, opened = _open_free_space(
        fail_stage="materialize"
    )
    resident = resident_open.context
    assert resident is not None
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        telemetry = opened.receipt.telemetry
        assert telemetry.allocation_success_count == 12
        assert telemetry.deallocation_success_count == 12
        assert telemetry.current_device_bytes == 0
        assert telemetry.module_close_success_count == 1
        assert telemetry.lease_release_success_count == 1
        assert kernel.closed
        assert resident._downstream_consumer_token is None
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_partial_allocation_failure_restores_preopen_runtime_ownership() -> None:
    *_, runtime, _, _, parent_open, resident_open = _open_resident()
    resident = resident_open.context
    assert resident is not None
    baseline_allocations = set(runtime.allocations)
    runtime.malloc_failure_at = runtime.malloc_calls + 3
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.telemetry.allocation_success_count == 2
        assert opened.receipt.telemetry.deallocation_success_count == 2
        assert set(runtime.allocations) == baseline_allocations
        assert kernel.closed
        assert resident._downstream_consumer_token is None
    finally:
        _close_chain(opened, resident_open, parent_open)


def test_ready_close_free_failure_is_retryable_and_releases_lease_once() -> None:
    *_, runtime, parent_open, resident_open, _, kernel, opened = _open_free_space()
    context = opened.context
    resident = resident_open.context
    assert context is not None and resident is not None
    failed_pointer = context._pointers["reduced_state"]
    runtime.free_failure_pointer_once = failed_pointer
    with pytest.raises(HipFreeSpaceContextError) as captured:
        context.close()
    assert captured.value.cleanup_owner is context
    assert context.receipt().status == "cleanup_failed"
    assert set(context._pointers) == {"reduced_state"}
    assert not kernel.closed
    assert resident._downstream_consumer_token is not None
    context.close()
    assert context.closed and kernel.closed
    assert context.receipt().telemetry.lease_release_success_count == 1
    _close_chain(opened, resident_open, parent_open)


def test_open_allocation_and_module_close_failure_returns_retryable_owner() -> None:
    *_, runtime, _, _, parent_open, resident_open = _open_resident()
    resident = resident_open.context
    assert resident is not None
    runtime.malloc_failure_at = runtime.malloc_calls + 2
    overlay = compile_hip_free_space_operator_plan_v1(resident._plan)
    kernel = FakeFreeSpaceKernel(runtime, close_failures=1)
    opened = open_hip_free_space_execution_context(
        resident,
        overlay,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert context is not None
    assert opened.receipt.status == "cleanup_failed"
    assert not context._pointers
    assert resident._downstream_consumer_token is not None
    context.close()
    assert context.closed and kernel.closed
    assert context.receipt().telemetry.lease_release_success_count == 1
    _close_chain(opened, resident_open, parent_open)
