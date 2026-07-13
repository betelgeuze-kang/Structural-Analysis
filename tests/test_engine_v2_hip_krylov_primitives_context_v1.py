from __future__ import annotations

import ctypes
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import krylov_primitives_rtc
from structural_analysis.engine_v2.assembly_backend import (
    krylov_primitives as primitives,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (
    HipKrylovPrimitivesContextError,
    HipKrylovPrimitivesReason,
    _batch_claims,
    _batch_payload,
    _classify_trusted_jacobi_diagonal,
    _context_payload,
    _evaluation_payload,
    _metric,
    open_hip_krylov_primitives_execution_context,
    validate_hip_krylov_primitives_context_receipt,
    validate_hip_krylov_primitives_batch_receipt,
    validate_hip_krylov_primitives_evaluation,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity

from tests.test_engine_v2_hip_free_space_context_v1 import (
    _close_chain,
    _open_free_space,
)


class FakeKrylovPrimitivesKernel:
    def __init__(
        self,
        runtime: Any,
        *,
        fail_stage: str | None = None,
        close_failures: int = 0,
        ack_failures: int = 0,
    ) -> None:
        self.runtime = runtime
        self.fail_stage = fail_stage
        self.close_failures = close_failures
        self.ack_failures = ack_failures
        self._pending_stream_count = 0
        self.closed = False
        self.close_calls = 0
        self.calls: list[str] = []
        self.identity = krylov_primitives_rtc._build_identity(
            architecture="gfx1030",
            source_hash=krylov_primitives_rtc._sha256_bytes(
                krylov_primitives_rtc._fixed_source()
            ),
            options=(
                "--offload-arch=gfx1030",
                "-O3",
                "-std=c++17",
                "-ffp-contract=off",
            ),
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
            code_object=b"fake-krylov-primitives-code-object",
        )

    @property
    def pending_stream_count(self) -> int:
        return self._pending_stream_count

    def acknowledge_stream_completion(self, stream: Any) -> None:
        del stream
        if self.ack_failures:
            self.ack_failures -= 1
            raise RuntimeError("injected completion acknowledgement failure")
        self._pending_stream_count = 0

    def _array(self, pointer: int, dtype: str, count: int) -> np.ndarray:
        return np.frombuffer(
            self.runtime.allocations[pointer], dtype=dtype, count=count
        )

    def _record(self, stage: str) -> None:
        self.calls.append(stage)
        if self.fail_stage == stage:
            raise RuntimeError(f"injected {stage} failure")

    def launch_prepare_positive_jacobi(self, *arguments: Any) -> None:
        self._pending_stream_count = 1
        self._record("prepare")
        (
            _,
            n,
            nnz,
            row_pointer,
            column_pointer,
            values_pointer,
            inverse_pointer,
            error_pointer,
        ) = arguments
        row = self._array(row_pointer, "<i4", n + 1)
        columns = self._array(column_pointer, "<i4", nnz)
        values = self._array(values_pointer, "<f8", nnz)
        inverse = self._array(inverse_pointer, "<f8", n)
        error = self._array(error_pointer, "<i4", 1)
        for index in range(n):
            begin, end = int(row[index]), int(row[index + 1])
            locations = np.flatnonzero(columns[begin:end] == index)
            if locations.size != 1:
                error[0] |= krylov_primitives_rtc.KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL
                continue
            diagonal = float(values[begin + int(locations[0])])
            if not np.isfinite(diagonal):
                error[0] |= krylov_primitives_rtc.KRYLOV_DEVICE_ERROR_NONFINITE_INPUT
            elif diagonal <= 0.0:
                error[0] |= krylov_primitives_rtc.KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL
            else:
                with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
                    reciprocal = np.float64(1.0) / np.float64(diagonal)
                if not np.isfinite(reciprocal) or reciprocal <= 0.0:
                    error[0] |= (
                        krylov_primitives_rtc.KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW
                    )
                else:
                    inverse[index] = reciprocal

    def launch_fill(self, *arguments: Any) -> None:
        self._record("fill")
        _, n, value, output_pointer, _ = arguments
        self._array(output_pointer, "<f8", n)[:] = value

    def launch_affine(self, *arguments: Any) -> None:
        _, n, alpha, x_pointer, beta, y_pointer, output_pointer, _ = arguments
        stage = "affine_x" if self.calls.count("affine_x") == 0 else "affine_y"
        self._record(stage)
        x = self._array(x_pointer, "<f8", n).copy()
        y = self._array(y_pointer, "<f8", n).copy()
        self._array(output_pointer, "<f8", n)[:] = alpha * x + beta * y

    def launch_apply_jacobi(self, *arguments: Any) -> None:
        self._record("jacobi")
        _, n, inverse_pointer, x_pointer, output_pointer, _ = arguments
        inverse = self._array(inverse_pointer, "<f8", n)
        x = self._array(x_pointer, "<f8", n)
        self._array(output_pointer, "<f8", n)[:] = inverse * x

    def launch_dot_stage(self, *arguments: Any) -> None:
        self._record("dot_stage")
        _, n, x_pointer, y_pointer, partial_pointer, _ = arguments
        x = self._array(x_pointer, "<f8", n)
        y = self._array(y_pointer, "<f8", n)
        p = krylov_primitives_rtc.reduction_output_count(n)
        partial = self._array(partial_pointer, "<f8", p)
        for block in range(p):
            begin, end = 512 * block, min(n, 512 * (block + 1))
            partial[block] = np.dot(x[begin:end], y[begin:end])

    def launch_sum_stage(self, *arguments: Any) -> None:
        self._record("sum_stage")
        _, n, input_pointer, output_pointer, _ = arguments
        source = self._array(input_pointer, "<f8", n).copy()
        count = krylov_primitives_rtc.reduction_output_count(n)
        output = self._array(output_pointer, "<f8", count)
        for block in range(count):
            begin, end = 512 * block, min(n, 512 * (block + 1))
            output[block] = np.sum(source[begin:end], dtype=np.float64)

    def launch_lassq_stage(self, *arguments: Any) -> None:
        self._record("lassq_stage")
        _, n, x_pointer, partial_pointer, _ = arguments
        x = self._array(x_pointer, "<f8", n)
        count = krylov_primitives_rtc.reduction_output_count(n)
        output = self._array(partial_pointer, "<f8", 2 * count)
        for block in range(count):
            begin, end = 512 * block, min(n, 512 * (block + 1))
            scale, sumsq = _lassq(x[begin:end])
            output[2 * block : 2 * block + 2] = (scale, sumsq)

    def launch_lassq_combine_stage(self, *arguments: Any) -> None:
        self._record("lassq_combine")
        _, n, input_pointer, output_pointer, _ = arguments
        source = self._array(input_pointer, "<f8", 2 * n).copy()
        count = krylov_primitives_rtc.reduction_output_count(n)
        output = self._array(output_pointer, "<f8", 2 * count)
        for block in range(count):
            begin, end = 512 * block, min(n, 512 * (block + 1))
            scale, sumsq = 0.0, 1.0
            for index in range(begin, end):
                scale, sumsq = _combine_lassq(
                    scale, sumsq, source[2 * index], source[2 * index + 1]
                )
            output[2 * block : 2 * block + 2] = (scale, sumsq)

    def launch_lassq_finalize(self, *arguments: Any) -> None:
        self._record("lassq_finalize")
        _, pair_pointer, norm_pointer, _ = arguments
        pair = self._array(pair_pointer, "<f8", 2)
        self._array(norm_pointer, "<f8", 1)[0] = (
            0.0 if pair[0] == 0.0 else pair[0] * np.sqrt(pair[1])
        )

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected primitive close failure")
        self.closed = True


def _lassq(values: np.ndarray) -> tuple[float, float]:
    scale, sumsq = 0.0, 1.0
    for value in np.abs(values):
        scale, sumsq = _combine_lassq(scale, sumsq, float(value), 1.0)
    return scale, sumsq


def _combine_lassq(
    scale_a: float, sumsq_a: float, scale_b: float, sumsq_b: float
) -> tuple[float, float]:
    if scale_b == 0.0:
        return scale_a, sumsq_a
    if scale_a == 0.0:
        return scale_b, sumsq_b
    if scale_a < scale_b:
        ratio = scale_a / scale_b
        return scale_b, sumsq_b + sumsq_a * ratio * ratio
    ratio = scale_b / scale_a
    return scale_a, sumsq_a + sumsq_b * ratio * ratio


def _open_primitives(**kernel_options: Any) -> tuple[Any, ...]:
    *prefix, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    assert source_apply.status == "enqueued"
    kernel = FakeKrylovPrimitivesKernel(runtime, **kernel_options)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    return (
        *prefix,
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        kernel,
        opened,
    )


def _close_all(
    opened: Any, free_open: Any, resident_open: Any, parent_open: Any
) -> None:
    if opened.context is not None and not opened.context.closed:
        opened.context.close()
    _close_chain(free_open, resident_open, parent_open)


def test_context_raw_batch_and_verification_have_exact_transfer_boundary() -> None:
    *_, runtime, parent_open, resident_open, free_open, _, kernel, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None and opened.ready
    try:
        receipt = opened.receipt
        assert receipt.telemetry.allocation_success_count == 9
        assert receipt.telemetry.h2d_operation_success_count == 1
        assert receipt.telemetry.h2d_bytes_succeeded == 4
        assert receipt.claims.positive_jacobi_inverse_ready
        assert receipt.claims.affine_primitive_ready
        assert receipt.claims.dot_primitive_ready
        assert receipt.claims.stable_l2_primitive_ready
        assert not receipt.claims.pcg_ready
        assert not receipt.claims.krylov_solver_ready
        with pytest.raises(Exception, match="krylov_consumer_active"):
            free.close()

        h2d_before = runtime.h2d_attempt_count
        d2h_before = len(runtime.d2h_streams)
        sync_before = len(runtime.sync_streams)
        malloc_before = runtime.malloc_calls
        batch = context.enqueue_primitive_batch()
        assert batch.status == "enqueued"
        assert batch.telemetry_delta.h2d_operation_count == 0
        assert batch.telemetry_delta.d2h_operation_count == 0
        assert batch.telemetry_delta.sync_count == 0
        assert batch.telemetry_delta.allocation_count == 0
        assert runtime.h2d_attempt_count == h2d_before
        assert len(runtime.d2h_streams) == d2h_before
        assert len(runtime.sync_streams) == sync_before
        assert runtime.malloc_calls == malloc_before

        evaluation = context.evaluate_for_verification()
        assert evaluation.receipt.status == "verified"
        assert evaluation.receipt.parity is not None
        assert evaluation.receipt.parity.passed
        assert evaluation.receipt.telemetry_delta.d2h_operation_success_count == 7
        assert evaluation.receipt.telemetry_delta.sync_success_count == 1
        validate_hip_krylov_primitives_evaluation(evaluation, expected_context=context)
        assert kernel.calls.count("fill") == 2
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_caller_kernel_requires_idle_completion_fence_protocol_before_lease() -> None:
    *_, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    kernel.acknowledge_stream_completion = None  # type: ignore[method-assign]
    try:
        with pytest.raises(HipKrylovPrimitivesContextError) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert caught.value.code == "hip_krylov_primitives_kernel_contract_invalid"
        assert free._krylov_consumer_token is None
        assert not free.poisoned
        assert not kernel.closed
    finally:
        kernel.close()
        _close_chain(free_open, resident_open, parent_open)


def test_latest_apply_check_and_child_lease_are_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    kernel = FakeKrylovPrimitivesKernel(runtime)
    original_buffer_views = primitives._buffer_views
    interleaved: dict[str, Any] = {}

    def interleave_new_apply(parent: Any) -> Any:
        views = original_buffer_views(parent)
        interleaved["apply"] = free.enqueue_operator_apply()
        return views

    monkeypatch.setattr(primitives, "_buffer_views", interleave_new_apply)
    try:
        with pytest.raises(Exception) as caught:
            open_hip_krylov_primitives_execution_context(
                free,
                source_apply,
                architecture="gfx1030",
                rtc_kernel=kernel,
            )
        assert (
            getattr(caught.value, "code", "")
            == "hip_free_space_krylov_source_apply_not_latest"
        )
        assert interleaved["apply"] is free._last_apply
        assert interleaved["apply"].sequence == source_apply.sequence + 1
        assert free._krylov_consumer_token is None
        assert not free.poisoned
        assert not kernel.closed
    finally:
        kernel.close()
        _close_chain(free_open, resident_open, parent_open)


def test_device_diagonal_mismatch_poison_is_shared_and_not_normalized() -> None:
    *_, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    values = np.frombuffer(
        runtime.allocations[free._pointers["reduced_csr_values"]], dtype="<f8"
    )
    row = free._overlay.array("reduced_csr_row_ptr")
    columns = free._overlay.array("reduced_csr_column_indices")
    location = int(row[0]) + int(np.flatnonzero(columns[row[0] : row[1]] == 0)[0])
    values[location] = -1.0
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free, source_apply, architecture="gfx1030", rtc_kernel=kernel
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.reason is not None
        assert opened.receipt.reason.code == "hip_krylov_primitives_context_open_failed"
        assert "prepare_device_mismatch" in opened.receipt.reason.detail
        assert free.poisoned
        assert free._krylov_consumer_token is None
        assert opened.receipt.telemetry.deallocation_success_count == 9
        assert kernel.closed
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_trusted_diagonal_classifier_preserves_legitimate_unsupported_cases() -> None:
    row = np.asarray([0, 1, 2], dtype="<i4")
    columns = np.asarray([0, 1], dtype="<i4")
    positive = np.asarray([2.0, 3.0], dtype="<f8")
    nonpositive = np.asarray([2.0, -0.0], dtype="<f8")
    reciprocal_overflow = np.asarray([2.0, np.nextafter(0.0, 1.0)], dtype="<f8")
    missing_columns = np.asarray([0, 0], dtype="<i4")
    assert _classify_trusted_jacobi_diagonal(row, columns, positive, 2) == "positive"
    assert (
        _classify_trusted_jacobi_diagonal(row, columns, nonpositive, 2) == "unsupported"
    )
    assert (
        _classify_trusted_jacobi_diagonal(row, columns, reciprocal_overflow, 2)
        == "unsupported"
    )
    assert (
        _classify_trusted_jacobi_diagonal(row, missing_columns, positive, 2)
        == "unsupported"
    )


def test_reciprocal_overflow_device_bit_is_clean_when_source_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()

    class ReciprocalOverflowKernel(FakeKrylovPrimitivesKernel):
        def launch_prepare_positive_jacobi(self, *arguments: Any) -> None:
            super().launch_prepare_positive_jacobi(*arguments)
            error_pointer = arguments[-1]
            self._array(error_pointer, "<i4", 1)[0] |= (
                krylov_primitives_rtc.KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW
            )

    monkeypatch.setattr(
        primitives,
        "_trusted_jacobi_diagonal_status",
        lambda parent: "unsupported",
    )
    kernel = ReciprocalOverflowKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free,
        source_apply,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.reason is not None
        assert opened.receipt.reason.code == (
            "hip_krylov_primitives_positive_jacobi_unsupported"
        )
        assert not free.poisoned
        assert free._krylov_consumer_token is None
        assert kernel.closed
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_partial_affine_failure_receipt_is_exact_and_poison_shared() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives(
        fail_stage="affine_y"
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    try:
        batch = context.enqueue_primitive_batch()
        assert batch.status == "unavailable"
        assert batch.telemetry_delta.fill_launch_success_count == 1
        assert batch.telemetry_delta.affine_launch_attempt_count == 2
        assert batch.telemetry_delta.affine_launch_success_count == 1
        assert batch.telemetry_delta.jacobi_launch_attempt_count == 0
        assert batch.claims.fill_enqueued
        assert not batch.claims.affine_program_enqueued
        assert context.poisoned and free.poisoned
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_allocation_failure_cleans_without_poisoning_parent() -> None:
    *_, runtime, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()
    baseline = set(runtime.allocations)
    runtime.malloc_failure_at = runtime.malloc_calls + 3
    kernel = FakeKrylovPrimitivesKernel(runtime)
    opened = open_hip_krylov_primitives_execution_context(
        free, source_apply, architecture="gfx1030", rtc_kernel=kernel
    )
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.telemetry.allocation_success_count == 2
        assert set(runtime.allocations) == baseline
        assert not free.poisoned
        assert free._krylov_consumer_token is None
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_rehashed_solver_claim_and_owned_pointer_mutation_are_rejected() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    try:
        forged = replace(
            opened.receipt,
            claims=replace(opened.receipt.claims, pcg_ready=True),
        )
        forged = replace(
            forged,
            context_receipt_hash=canonical_hash(
                _context_payload(forged, include_hash=False)
            ),
        )
        with pytest.raises(HipKrylovPrimitivesContextError):
            validate_hip_krylov_primitives_context_receipt(forged)
        context._pointers["work_x"] = object()
        with pytest.raises(Exception, match="owned_pointer_changed"):
            context.enqueue_primitive_batch()
    finally:
        context._pointers["work_x"] = context._owned_pointer_snapshot["work_x"]
        _close_all(opened, free_open, resident_open, parent_open)


def test_prepare_queue_failure_cleans_and_poison_is_shared() -> None:
    *_, parent_open, resident_open, free_open, _, kernel, opened = _open_primitives(
        fail_stage="prepare"
    )
    free = free_open.context
    assert free is not None
    try:
        assert opened.context is None
        assert opened.receipt.status == "unavailable"
        assert opened.receipt.telemetry.deallocation_success_count == 9
        assert opened.receipt.telemetry.lease_release_success_count == 1
        assert kernel.closed
        assert free.poisoned
    finally:
        _close_chain(free_open, resident_open, parent_open)


def test_ready_close_free_failure_is_retryable_and_releases_lease_once() -> None:
    *_, runtime, parent_open, resident_open, free_open, _, kernel, opened = (
        _open_primitives()
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    pointer = context._pointers["work_x"]
    runtime.free_failure_pointer_once = pointer
    with pytest.raises(HipKrylovPrimitivesContextError) as captured:
        context.close()
    assert captured.value.cleanup_owner is context
    assert context.receipt().status == "cleanup_failed"
    assert set(context._pointers) == {"work_x"}
    assert not kernel.closed
    assert free._krylov_consumer_token is not None
    context.close()
    assert context.closed and kernel.closed
    assert context.receipt().telemetry.lease_release_success_count == 1
    _close_chain(free_open, resident_open, parent_open)


def test_internal_compile_cleanup_owner_is_retained_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_, parent_open, resident_open, _, _, free_open = _open_free_space()
    free = free_open.context
    assert free is not None
    source_apply = free.enqueue_operator_apply()

    class ModuleRuntime:
        def __init__(self) -> None:
            self.calls = 0

        def unload(self, _: Any) -> int:
            self.calls += 1
            return 1 if self.calls == 1 else 0

        def error_string(self, _: int) -> str:
            return "injected unload failure"

    module_runtime = ModuleRuntime()
    owner = krylov_primitives_rtc._HipRtcKrylovPrimitivesModuleCleanupOwner(
        module_runtime, ctypes.c_void_p(123)
    )

    def fail_compile(*_: Any, **__: Any) -> Any:
        raise krylov_primitives_rtc.HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_symbol_missing",
            "injected compile cleanup owner",
            cleanup_owner=owner,
        )

    monkeypatch.setattr(
        primitives, "compile_hip_rtc_krylov_primitives_kernel", fail_compile
    )
    opened = open_hip_krylov_primitives_execution_context(
        free, source_apply, architecture="gfx1030"
    )
    context = opened.context
    try:
        assert context is not None
        assert opened.receipt.status == "cleanup_failed"
        assert opened.receipt.telemetry.module_owner_acquired_count == 1
        assert not free.poisoned
        assert free._krylov_consumer_token is not None
        context.close()
        assert context.closed and owner.closed
        assert not free.poisoned
        assert free._krylov_consumer_token is None
    finally:
        if context is not None and not context.closed:
            context.close()
        _close_chain(free_open, resident_open, parent_open)


def test_open_completion_ack_failure_returns_retryable_cleanup_owner() -> None:
    *_, parent_open, resident_open, free_open, _, kernel, opened = _open_primitives(
        ack_failures=2
    )
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    try:
        assert opened.receipt.status == "cleanup_failed"
        assert opened.receipt.telemetry.allocation_success_count == 9
        assert opened.receipt.telemetry.deallocation_success_count == 0
        assert opened.receipt.telemetry.sync_attempt_count == 2
        assert opened.receipt.telemetry.sync_success_count == 2
        assert opened.receipt.telemetry.current_device_bytes > 0
        assert free._krylov_consumer_token is not None
        assert free.poisoned
        assert not kernel.closed

        context.close()
        assert context.closed
        closed = context.receipt()
        assert closed.telemetry.current_device_bytes == 0
        assert closed.telemetry.deallocation_success_count == 9
        assert closed.telemetry.sync_attempt_count == 3
        assert closed.telemetry.sync_success_count == 3
        assert closed.telemetry.module_close_success_count == 1
        assert closed.telemetry.lease_release_success_count == 1
        assert free._krylov_consumer_token is None
    finally:
        if not context.closed:
            context.close()
        _close_chain(free_open, resident_open, parent_open)


def test_rehashed_parity_forgery_is_rejected_against_live_cpu_witness() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        parity = evaluation.receipt.parity
        assert parity is not None
        forged_metric = replace(
            parity.dot_result,
            max_abs_error=1.0,
            relative_l2_error=1.0,
            max_scaled_error=2.0,
            passed=False,
        )
        forged_parity = replace(parity, dot_result=forged_metric, passed=False)
        forged_receipt = replace(
            evaluation.receipt,
            status="parity_failed",
            parity=forged_parity,
        )
        forged_receipt = replace(
            forged_receipt,
            receipt_hash=canonical_hash(
                _evaluation_payload(forged_receipt, include_hash=False)
            ),
        )
        forged = replace(evaluation, receipt=forged_receipt)
        with pytest.raises(
            HipKrylovPrimitivesContextError,
            match="parity_witness_mismatch",
        ):
            validate_hip_krylov_primitives_evaluation(forged, expected_context=context)
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_observed_cpu_parity_failure_poison_is_shared_and_stops_reuse() -> None:
    *_, parent_open, resident_open, free_open, _, kernel, opened = _open_primitives()
    context = opened.context
    free = free_open.context
    assert context is not None and free is not None
    original_affine = kernel.launch_affine

    def corrupt_affine(*arguments: Any) -> None:
        original_affine(*arguments)
        _, n, _, _, _, _, output_pointer, _ = arguments
        kernel._array(output_pointer, "<f8", n)[0] += 1.0

    kernel.launch_affine = corrupt_affine
    try:
        evaluation = context.evaluate_for_verification()
        assert evaluation.receipt.status == "parity_failed"
        assert evaluation.receipt.parity is not None
        assert not evaluation.receipt.parity.passed
        assert context.poisoned
        assert free.poisoned
        with pytest.raises(
            HipKrylovPrimitivesContextError,
            match="context_poisoned",
        ):
            context.enqueue_primitive_batch()
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_large_reduction_stage_count_and_failed_prefix_are_bound() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    original_dimensions = context._dimensions_snapshot
    try:
        complete = context.enqueue_primitive_batch()
        large_dimensions = replace(
            original_dimensions,
            free_dof_count=512 * 512 + 1,
            reduction_partial_count=513,
        )
        context._dimensions_snapshot = large_dimensions
        with pytest.raises(HipKrylovPrimitivesContextError):
            validate_hip_krylov_primitives_batch_receipt(
                complete, expected_context=context
            )

        partial_delta = replace(
            complete.telemetry_delta,
            sum_stage_launch_attempt_count=2,
            sum_stage_launch_success_count=1,
            lassq_stage_launch_attempt_count=0,
            lassq_stage_launch_success_count=0,
            lassq_combine_launch_attempt_count=0,
            lassq_combine_launch_success_count=0,
            lassq_finalize_launch_attempt_count=0,
            lassq_finalize_launch_success_count=0,
        )
        partial = replace(
            complete,
            status="unavailable",
            sequence=complete.sequence + 100,
            reason=HipKrylovPrimitivesReason(
                "hip_krylov_primitives_sum_stage_launch_failed",
                "injected second-stage failure",
            ),
            telemetry_delta=partial_delta,
            claims=_batch_claims(partial_delta, large_dimensions),
        )
        partial = replace(
            partial,
            batch_id=canonical_hash(
                {
                    "context_id": partial.context_id,
                    "source_apply_receipt_hash": partial.source_apply_receipt_hash,
                    "sequence": partial.sequence,
                }
            ),
        )
        partial = replace(
            partial,
            receipt_hash=canonical_hash(_batch_payload(partial, include_hash=False)),
        )
        context._batch_witnesses[partial.sequence] = partial.receipt_hash
        validate_hip_krylov_primitives_batch_receipt(partial, expected_context=context)

        bad_delta = replace(
            partial_delta,
            lassq_stage_launch_attempt_count=1,
        )
        bad = replace(
            partial,
            telemetry_delta=bad_delta,
            claims=_batch_claims(bad_delta, large_dimensions),
        )
        bad = replace(
            bad,
            receipt_hash=canonical_hash(_batch_payload(bad, include_hash=False)),
        )
        with pytest.raises(
            HipKrylovPrimitivesContextError,
            match="batch_stage_order_invalid",
        ):
            validate_hip_krylov_primitives_batch_receipt(bad, expected_context=context)
    finally:
        context._batch_witnesses.pop(complete.sequence + 100, None)
        context._dimensions_snapshot = original_dimensions
        _close_all(opened, free_open, resident_open, parent_open)


def test_detached_evaluation_validation_binds_every_exported_array() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        assert evaluation.receipt.status == "verified"
        assert evaluation.work_x is not None
        forged_work_x = evaluation.work_x.copy()
        forged_work_x[0] += 1.0
        forged_work_x.flags.writeable = False
        forged = replace(evaluation, work_x=forged_work_x)
        with pytest.raises(HipKrylovPrimitivesContextError) as caught:
            validate_hip_krylov_primitives_evaluation(forged, expected_context=context)
        assert caught.value.code == "hip_krylov_primitives_evaluation_array_invalid"
        assert caught.value.path == "/work_x"

        with pytest.raises(HipKrylovPrimitivesContextError) as detached:
            validate_hip_krylov_primitives_evaluation(evaluation)
        assert (
            detached.value.code == "hip_krylov_primitives_evaluation_context_required"
        )
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_evaluation_requires_recorded_batch_and_derived_execution_id() -> None:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    try:
        evaluation = context.evaluate_for_verification()
        batch = evaluation.batch
        assert batch is not None

        bad_id_receipt = replace(
            evaluation.receipt,
            execution_id="sha256:" + "f" * 64,
        )
        bad_id_receipt = replace(
            bad_id_receipt,
            receipt_hash=canonical_hash(
                _evaluation_payload(bad_id_receipt, include_hash=False)
            ),
        )
        with pytest.raises(
            HipKrylovPrimitivesContextError,
            match="evaluation_execution_id_mismatch",
        ):
            validate_hip_krylov_primitives_evaluation(
                replace(evaluation, receipt=bad_id_receipt),
                expected_context=context,
            )

        unrecorded_batch = replace(batch, sequence=batch.sequence + 100)
        unrecorded_batch = replace(
            unrecorded_batch,
            batch_id=canonical_hash(
                {
                    "context_id": unrecorded_batch.context_id,
                    "source_apply_receipt_hash": (
                        unrecorded_batch.source_apply_receipt_hash
                    ),
                    "sequence": unrecorded_batch.sequence,
                }
            ),
        )
        unrecorded_batch = replace(
            unrecorded_batch,
            receipt_hash=canonical_hash(
                _batch_payload(unrecorded_batch, include_hash=False)
            ),
        )
        unrecorded_receipt = replace(
            evaluation.receipt,
            batch=unrecorded_batch,
            execution_id=canonical_hash(
                {
                    "context_id": evaluation.receipt.context_id,
                    "opening_context_receipt_hash": (
                        evaluation.receipt.opening_context_receipt_hash
                    ),
                    "batch_receipt_hash": unrecorded_batch.receipt_hash,
                }
            ),
        )
        unrecorded_receipt = replace(
            unrecorded_receipt,
            receipt_hash=canonical_hash(
                _evaluation_payload(unrecorded_receipt, include_hash=False)
            ),
        )
        with pytest.raises(
            HipKrylovPrimitivesContextError,
            match="batch_witness_mismatch",
        ):
            validate_hip_krylov_primitives_evaluation(
                replace(
                    evaluation,
                    receipt=unrecorded_receipt,
                    batch=unrecorded_batch,
                ),
                expected_context=context,
            )
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_extreme_finite_metric_is_fail_closed_with_finite_sentinels() -> None:
    maximum = np.finfo(np.float64).max
    metric = _metric(
        np.asarray([maximum], dtype="<f8"),
        np.asarray([-maximum], dtype="<f8"),
    )
    assert not metric.passed
    assert metric.max_abs_error == maximum
    assert metric.relative_l2_error == maximum
    assert metric.max_scaled_error == maximum
