from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    HipResidentCsrContextError,
    HipResidentCsrReason,
    _bounded_detail,
    _context_payload,
    _enqueue_payload,
    _evaluation_payload,
    _has_runtime_value,
    open_hip_resident_csr_execution_context,
    validate_hip_resident_csr_context_receipt,
    validate_hip_resident_csr_enqueue_receipt,
    validate_hip_resident_csr_evaluation,
    validate_hip_resident_csr_evaluation_receipt,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIRError,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.rtc_backend import rtc as rtc_core
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.model_ir import load_model_ir_v2

from tests.test_engine_v2_hip_assembly_context_v1 import (
    FakeKernel as FakeAssemblyKernel,
    FakeRuntime as AssemblyFakeRuntime,
    _contracts,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "src/structural_analysis/schemas"
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"


def test_root_public_api_exports_resident_csr_consumer_v1() -> None:
    import structural_analysis.engine_v2 as engine_v2

    assert (
        engine_v2.open_hip_resident_csr_execution_context
        is open_hip_resident_csr_execution_context
    )
    assert engine_v2.HIP_RESIDENT_CSR_CAPABILITY_PROFILE == (
        "phase0_hiprtc_assembly_resident_csr_residual_jvp_consumer"
    )
    assert callable(engine_v2.validate_hip_resident_csr_enqueue_receipt)
    assert callable(engine_v2.validate_hip_resident_csr_evaluation_receipt)


class TrackingRuntime(AssemblyFakeRuntime):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.stream_create_count = 0
        self.streams: list[object] = []
        self.h2d_streams: list[object] = []
        self.d2h_streams: list[object] = []
        self.sync_streams: list[object] = []
        self.selected_devices: list[int] = []
        self.h2d_attempt_count = 0
        self.h2d_failure_at: int | None = None

    def set_device(self, ordinal: int) -> None:
        super().set_device(ordinal)
        self.selected_devices.append(ordinal)

    def create_stream(self) -> object:
        self.stream_create_count += 1
        stream = object()
        self.streams.append(stream)
        return stream

    def copy_h2d_async(self, pointer: int, array: np.ndarray, stream: object) -> None:
        self.h2d_attempt_count += 1
        self.h2d_streams.append(stream)
        if self.h2d_attempt_count == self.h2d_failure_at:
            raise RuntimeError("injected resident H2D failure")
        super().copy_h2d_async(pointer, array, stream)

    def copy_d2h_async(self, array: np.ndarray, pointer: int, stream: object) -> None:
        self.d2h_streams.append(stream)
        super().copy_d2h_async(array, pointer, stream)

    def synchronize(self, stream: object) -> None:
        self.sync_streams.append(stream)
        super().synchronize(stream)


def test_tracking_runtime_preserves_selected_device_authority() -> None:
    runtime = TrackingRuntime()
    runtime.set_device(2)

    assert runtime.device_ordinal == 2
    assert runtime.selected_devices == [2]


class MutableResidualIdentity:
    def __init__(self) -> None:
        identity = rtc_core._build_identity(
            architecture="gfx1030",
            source_hash=rtc_core._sha256_bytes(rtc_core._fixed_source()),
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
            code_object=b"fake-resident-csr-code-object",
        )
        self.manifest = identity.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.manifest))


class FakeResidualKernel:
    def __init__(
        self,
        runtime: TrackingRuntime,
        *,
        bias: float = 0.0,
        fail_launch: bool = False,
        close_failures: int = 0,
    ) -> None:
        self.runtime = runtime
        self.bias = bias
        self.fail_launch = fail_launch
        self.close_failures = close_failures
        self.identity = MutableResidualIdentity()
        self.closed = False
        self.close_calls = 0
        self.launches: list[tuple[Any, ...]] = []

    def launch_residual_jvp(
        self,
        stream: object,
        row_count: int,
        row_ptr_pointer: int,
        columns_pointer: int,
        values_pointer: int,
        state_pointer: int,
        load_pointer: int,
        direction_pointer: int,
        residual_pointer: int,
        jvp_pointer: int,
    ) -> None:
        arguments = (
            stream,
            row_count,
            row_ptr_pointer,
            columns_pointer,
            values_pointer,
            state_pointer,
            load_pointer,
            direction_pointer,
            residual_pointer,
            jvp_pointer,
        )
        self.launches.append(arguments)
        if self.fail_launch:
            raise RuntimeError("injected resident launch failure")

        def array(pointer: int, dtype: str, count: int) -> np.ndarray:
            return np.frombuffer(
                self.runtime.allocations[pointer], dtype=dtype, count=count
            )

        row_ptr = array(row_ptr_pointer, "<i4", row_count + 1)
        nnz = int(row_ptr[-1])
        columns = array(columns_pointer, "<i4", nnz)
        values = array(values_pointer, "<f8", nnz)
        state = array(state_pointer, "<f8", row_count)
        load = array(load_pointer, "<f8", row_count)
        direction = array(direction_pointer, "<f8", row_count)
        residual = array(residual_pointer, "<f8", row_count)
        jvp = array(jvp_pointer, "<f8", row_count)
        for row in range(row_count):
            begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
            indices = columns[begin:end]
            coefficients = values[begin:end]
            residual[row] = np.dot(coefficients, state[indices]) - load[row]
            jvp[row] = np.dot(coefficients, direction[indices])
        if self.bias:
            residual[0] += self.bias
            jvp[0] += self.bias

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected resident close failure")
        self.closed = True


def _open_parent(*, runtime: TrackingRuntime | None = None) -> tuple[Any, ...]:
    buffers, plan, assembly_plan = _contracts()
    runtime = runtime or TrackingRuntime()
    assembly_kernel = FakeAssemblyKernel(runtime, plan)
    opened = open_hip_assembly_execution_context(
        buffers,
        plan,
        assembly_plan,
        verify_cpu_parity=False,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=assembly_kernel,
    )
    assert opened.ready
    return buffers, plan, assembly_plan, runtime, assembly_kernel, opened


def _open_resident(
    *,
    runtime: TrackingRuntime | None = None,
    bias: float = 0.0,
    fail_launch: bool = False,
    close_failures: int = 0,
) -> tuple[Any, ...]:
    *contracts, runtime, assembly_kernel, parent_open = _open_parent(runtime=runtime)
    plan = contracts[1]
    state = create_initial_state(plan)
    residual_kernel = FakeResidualKernel(
        runtime,
        bias=bias,
        fail_launch=fail_launch,
        close_failures=close_failures,
    )
    opened = open_hip_resident_csr_execution_context(
        parent_open.context,
        state,
        architecture="gfx1030",
        rtc_kernel=residual_kernel,
    )
    return (
        *contracts,
        state,
        runtime,
        assembly_kernel,
        residual_kernel,
        parent_open,
        opened,
    )


def _other_committed_state(load_pattern_id: str = "LC_WEAK") -> tuple[Any, Any]:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    plan = compile_execution_plan_v2(buffers)
    return plan, create_initial_state(plan)


def _rehash_context(receipt: Any) -> Any:
    return replace(
        receipt,
        context_receipt_hash=canonical_hash(
            _context_payload(receipt, include_hash=False)
        ),
    )


def _rehash_enqueue(receipt: Any) -> Any:
    return replace(
        receipt,
        receipt_hash=canonical_hash(_enqueue_payload(receipt, include_hash=False)),
    )


def _rehash_evaluation(receipt: Any) -> Any:
    return replace(
        receipt,
        receipt_hash=canonical_hash(_evaluation_payload(receipt, include_hash=False)),
    )


def _close_resident_pair(context: Any, parent: Any) -> None:
    if context is not None and not context.closed:
        context.close()
    if parent is not None and not parent.closed:
        parent.close()


def _write_device_direction(context: Any, values: np.ndarray) -> None:
    """Emulate one same-stream child producer in the byte-addressable fake runtime."""

    destination = np.frombuffer(
        context._runtime.allocations[context._pointers["direction_workspace"]],
        dtype="<f8",
        count=context._plan.dof_count,
    )
    destination[:] = np.asarray(values, dtype="<f8")


def test_open_borrows_parent_csr_load_stream_and_owns_only_four_vectors() -> None:
    buffers, plan, _, state, runtime, _, _, parent_open, opened = _open_resident()
    assert opened.ready, opened.receipt.reason
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    assert runtime.stream_create_count == 1
    assert len(opened.receipt.owned_buffers) == 4
    assert opened.receipt.telemetry.owned_allocation_success_count == 4
    assert opened.receipt.telemetry.h2d_operation_success_count == 1
    assert opened.receipt.telemetry.h2d_bytes_succeeded == state.displacement_si.nbytes
    assert opened.receipt.telemetry.consumer_csr_symbolic_h2d_bytes == 0
    assert opened.receipt.telemetry.consumer_csr_numeric_h2d_bytes == 0
    assert opened.receipt.telemetry.consumer_load_h2d_bytes == 0
    assert opened.receipt.bindings.residual_kernel_origin == "caller_supplied"
    assert runtime.h2d_arrays[-1] is state.displacement_si
    assert runtime.h2d_streams[-1] is parent._stream
    assert array_data_hash(plan.array("global_load")) == array_data_hash(
        buffers.array("load_vector_si").reshape(-1)
    )
    with pytest.raises(HipAssemblyContextError, match="resident_consumer_active"):
        parent.close()
    validate_hip_resident_csr_context_receipt(opened.receipt, expected_context=context)
    context.close()
    parent.close()


def test_enqueue_is_zero_transfer_allocation_and_fence_on_parent_stream() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    runtime = context._runtime
    priming = context.evaluate_for_verification(
        np.zeros(context._plan.dof_count, dtype="<f8")
    )
    assert priming.receipt.status == "verified"
    before = (
        len(runtime.h2d_streams),
        len(runtime.d2h_streams),
        len(runtime.sync_streams),
        runtime.malloc_calls,
    )
    first = context.enqueue_residual_jvp()
    second = context.enqueue_residual_jvp()
    after = (
        len(runtime.h2d_streams),
        len(runtime.d2h_streams),
        len(runtime.sync_streams),
        runtime.malloc_calls,
    )
    assert before == after
    assert (first.sequence, second.sequence) == (2, 3)
    assert first.telemetry_delta.to_dict() == {
        "h2d_operation_count": 0,
        "h2d_bytes": 0,
        "d2h_operation_count": 0,
        "d2h_bytes": 0,
        "allocation_count": 0,
        "sync_count": 0,
        "kernel_launch_attempt_count": 1,
        "kernel_launch_success_count": 1,
        "fallback_count": 0,
    }
    arguments = residual_kernel.launches[-1]
    assert arguments[0] is parent._stream
    assert arguments[2] == parent._pointers["csr_row_ptr"]
    assert arguments[3] == parent._pointers["csr_column_indices"]
    assert arguments[4] == parent._pointers["csr_values"]
    assert arguments[5] == context._pointers["state_displacement"]
    assert arguments[6] == parent._base_context._pointers["load_vector_si"]
    assert arguments[7] == context._pointers["direction_workspace"]
    assert arguments[8] == context._pointers["residual_workspace"]
    assert arguments[9] == context._pointers["jvp_workspace"]
    assert set(context._pointers.values()).isdisjoint(parent._pointers.values())
    assert set(context._pointers.values()).isdisjoint(
        parent._base_context._pointers.values()
    )
    context.close()
    parent.close()


def test_raw_enqueue_rejects_uninitialized_direction_without_device_work() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    before = context.receipt().telemetry
    try:
        with pytest.raises(HipResidentCsrContextError) as caught:
            context.enqueue_residual_jvp()
        assert caught.value.code == "hip_resident_direction_uninitialized"
        assert not residual_kernel.launches
        assert context._enqueue_sequence == 0
        assert context.receipt().telemetry == before
        assert not context.poisoned and not parent.poisoned
    finally:
        _close_resident_pair(context, parent)


def test_downstream_lease_is_exact_exclusive_and_monotonic_across_threads() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    barrier = threading.Barrier(3)
    successes: list[object] = []
    failures: list[HipResidentCsrContextError] = []

    def acquire() -> None:
        barrier.wait(timeout=5)
        try:
            successes.append(context._acquire_downstream_consumer())
        except HipResidentCsrContextError as exc:
            failures.append(exc)

    threads = tuple(threading.Thread(target=acquire, daemon=True) for _ in range(2))
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert len(successes) == len(failures) == 1
    assert failures[0].code == "hip_resident_downstream_consumer_active"
    first = successes[0]
    assert context._downstream_consumer_epoch(first) == 1
    context._release_downstream_consumer(first)

    second = context._acquire_downstream_consumer()
    assert context._downstream_consumer_epoch(second) == 2
    with pytest.raises(HipResidentCsrContextError) as stale:
        context._require_downstream_consumer(first)
    assert stale.value.code == "hip_resident_downstream_consumer_token_invalid"
    context._release_downstream_consumer(second)
    _close_resident_pair(context, parent)


def test_downstream_foreign_release_does_not_steal_owner_and_exact_retry_succeeds() -> (
    None
):
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    foreign = object()
    try:
        for operation in (
            lambda: context._require_downstream_consumer(foreign),
            lambda: context._downstream_consumer_epoch(foreign),
            lambda: context._publish_device_direction(foreign),
            lambda: context._release_downstream_consumer(foreign),
        ):
            with pytest.raises(HipResidentCsrContextError) as caught:
                operation()
            assert caught.value.code == (
                "hip_resident_downstream_consumer_token_invalid"
            )
        assert context._downstream_consumer_token is token
        context._require_downstream_consumer(token)
        context._release_downstream_consumer(token)
        assert context._downstream_consumer_token is None
    finally:
        _close_resident_pair(context, parent)


def test_downstream_child_blocks_both_owner_closes_before_device_work() -> None:
    *_, runtime, _, _, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    telemetry_before = context.receipt().telemetry
    sync_before = tuple(runtime.sync_streams)
    allocations_before = dict(runtime.allocations)
    try:
        with pytest.raises(HipResidentCsrContextError) as resident_close:
            context.close()
        assert resident_close.value.code == "hip_resident_downstream_consumer_active"
        assert context.receipt().telemetry == telemetry_before
        assert tuple(runtime.sync_streams) == sync_before
        assert runtime.allocations == allocations_before
        with pytest.raises(HipAssemblyContextError) as assembly_close:
            parent.close()
        assert assembly_close.value.code == "hip_assembly_resident_consumer_active"
        assert runtime.allocations == allocations_before
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_device_direction_generation_is_child_bound_current_and_single_consume() -> (
    None
):
    _, plan, _, _, _, _, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    try:
        first_values = np.linspace(-0.25, 0.25, plan.dof_count, dtype="<f8")
        _write_device_direction(context, first_values)
        first_generation = context._publish_device_direction(token)
        second_values = np.linspace(0.5, -0.5, plan.dof_count, dtype="<f8")
        _write_device_direction(context, second_values)
        second_generation = context._publish_device_direction(token)
        assert (first_generation, second_generation) == (1, 2)

        with pytest.raises(HipResidentCsrContextError) as stale:
            context._enqueue_residual_jvp_from_device(token, first_generation)
        assert stale.value.code == "hip_resident_device_direction_stale_or_consumed"
        assert not residual_kernel.launches

        receipt = context._enqueue_residual_jvp_from_device(token, second_generation)
        assert receipt.status == "enqueued" and receipt.sequence == 1
        assert len(residual_kernel.launches) == 1
        actual_jvp = np.frombuffer(
            context._runtime.allocations[context._pointers["jvp_workspace"]],
            dtype="<f8",
            count=plan.dof_count,
        )
        assert np.allclose(actual_jvp, plan.jvp(second_values), rtol=0.0, atol=1e-12)

        with pytest.raises(HipResidentCsrContextError) as consumed:
            context._enqueue_residual_jvp_from_device(token, second_generation)
        assert consumed.value.code == "hip_resident_device_direction_stale_or_consumed"
        assert len(residual_kernel.launches) == 1
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_downstream_authority_is_separate_from_legacy_host_verification() -> None:
    *_, runtime, _, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    before = (
        len(runtime.h2d_streams),
        len(runtime.d2h_streams),
        len(runtime.sync_streams),
        len(residual_kernel.launches),
    )
    try:
        with pytest.raises(HipResidentCsrContextError) as verification:
            context.evaluate_for_verification(np.ones(context._plan.dof_count))
        assert verification.value.code == "hip_resident_downstream_consumer_active"
        with pytest.raises(HipResidentCsrContextError) as raw_enqueue:
            context.enqueue_residual_jvp()
        assert raw_enqueue.value.code == "hip_resident_downstream_consumer_active"
        assert before == (
            len(runtime.h2d_streams),
            len(runtime.d2h_streams),
            len(runtime.sync_streams),
            len(residual_kernel.launches),
        )
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_child_reported_producer_failure_poison_is_shared_without_publication() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    generation_before = context._direction_generation
    context._poison_downstream_consumer(
        token, "injected downstream direction launch failure"
    )
    try:
        assert context.poisoned and parent.poisoned
        assert context._direction_generation == generation_before
        assert context._active_device_direction_generation is None
        with pytest.raises(HipResidentCsrContextError) as publish:
            context._publish_device_direction(token)
        assert publish.value.code == "hip_resident_context_poisoned"
        with pytest.raises(HipResidentCsrContextError) as consume:
            context._enqueue_residual_jvp_from_device(token, generation_before)
        assert consume.value.code == "hip_resident_context_poisoned"
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_residual_launch_failure_does_not_consume_device_generation() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    _write_device_direction(context, np.ones(context._plan.dof_count, dtype="<f8"))
    generation = context._publish_device_direction(token)
    residual_kernel.fail_launch = True
    try:
        failed = context._enqueue_residual_jvp_from_device(token, generation)
        assert failed.status == "unavailable"
        assert context.poisoned and parent.poisoned
        assert context._direction_generation == generation
        assert context._active_device_direction_generation == generation
        with pytest.raises(HipResidentCsrContextError) as retry:
            context._enqueue_residual_jvp_from_device(token, generation)
        assert retry.value.code == "hip_resident_context_poisoned"
        assert len(residual_kernel.launches) == 1
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_downstream_token_and_generation_never_enter_v1_receipts() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    token = context._acquire_downstream_consumer()
    generation = context._publish_device_direction(token)
    try:
        payload = context.receipt().to_dict()
        encoded = json.dumps(payload, sort_keys=True)
        assert "downstream_consumer" not in encoded
        assert "device_direction_generation" not in encoded
        with pytest.raises(TypeError):
            json.dumps(token)
        assert generation == 1
    finally:
        context._release_downstream_consumer(token)
        _close_resident_pair(context, parent)


def test_verification_wrapper_replays_full_free_constrained_parity() -> None:
    _, plan, _, _, runtime, _, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    direction = np.linspace(-0.5, 0.5, plan.dof_count)
    evaluation = context.evaluate_for_verification(direction)
    assert evaluation.receipt.status == "verified"
    assert evaluation.receipt.parity is not None
    assert evaluation.receipt.parity.passed
    assert evaluation.receipt.telemetry_delta.h2d_operation_success_count == 1
    assert evaluation.receipt.telemetry_delta.d2h_operation_success_count == 2
    assert evaluation.receipt.telemetry_delta.kernel_launch_success_count == 1
    assert evaluation.receipt.telemetry_delta.sync_success_count == 1
    assert evaluation.receipt.telemetry_delta.allocation_count == 0
    assert evaluation.receipt.telemetry_delta.fallback_count == 0
    assert all(stream is parent._stream for stream in runtime.h2d_streams[-1:])
    assert all(stream is parent._stream for stream in runtime.d2h_streams[-2:])
    assert runtime.sync_streams[-1] is parent._stream
    assert residual_kernel.launches[-1][0] is parent._stream
    validate_hip_resident_csr_evaluation(evaluation, expected_context=context)
    context.close()
    parent.close()


def test_parity_failure_poison_is_shared_and_never_falls_back() -> None:
    *_, parent_open, opened = _open_resident(bias=1.0)
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(np.ones(context._plan.dof_count))
    assert evaluation.receipt.status == "parity_failed"
    assert context.poisoned and parent.poisoned
    assert evaluation.receipt.telemetry_delta.fallback_count == 0
    poisoned = context.receipt()
    assert poisoned.status == "poisoned"
    assert poisoned.claims.exclusive_parent_lease_active
    assert poisoned.claims.borrowed_assembly_csr
    assert poisoned.telemetry.owned_current_device_bytes > 0
    with pytest.raises(HipAssemblyContextError, match="resident_consumer_active"):
        parent.close()
    with pytest.raises(HipResidentCsrContextError, match="context_poisoned"):
        context.enqueue_residual_jvp()
    context.close()
    parent.close()


@pytest.mark.parametrize(
    ("failure", "failure_index", "expected", "reason_code"),
    (
        (
            "h2d",
            1,
            {
                "h2d_operation_attempt_count": 1,
                "h2d_operation_success_count": 0,
                "d2h_operation_attempt_count": 0,
                "d2h_operation_success_count": 0,
                "kernel_launch_attempt_count": 0,
                "kernel_launch_success_count": 0,
                "sync_attempt_count": 0,
                "sync_success_count": 0,
            },
            "hip_resident_direction_upload_failed",
        ),
        (
            "launch",
            1,
            {
                "h2d_operation_attempt_count": 1,
                "h2d_operation_success_count": 1,
                "d2h_operation_attempt_count": 0,
                "d2h_operation_success_count": 0,
                "kernel_launch_attempt_count": 1,
                "kernel_launch_success_count": 0,
                "sync_attempt_count": 0,
                "sync_success_count": 0,
            },
            "hip_resident_enqueue_failed",
        ),
        (
            "d2h",
            1,
            {
                "h2d_operation_attempt_count": 1,
                "h2d_operation_success_count": 1,
                "d2h_operation_attempt_count": 1,
                "d2h_operation_success_count": 0,
                "kernel_launch_attempt_count": 1,
                "kernel_launch_success_count": 1,
                "sync_attempt_count": 0,
                "sync_success_count": 0,
            },
            "hip_resident_result_export_failed",
        ),
        (
            "d2h",
            2,
            {
                "h2d_operation_attempt_count": 1,
                "h2d_operation_success_count": 1,
                "d2h_operation_attempt_count": 2,
                "d2h_operation_success_count": 1,
                "kernel_launch_attempt_count": 1,
                "kernel_launch_success_count": 1,
                "sync_attempt_count": 0,
                "sync_success_count": 0,
            },
            "hip_resident_result_export_failed",
        ),
        (
            "sync",
            1,
            {
                "h2d_operation_attempt_count": 1,
                "h2d_operation_success_count": 1,
                "d2h_operation_attempt_count": 2,
                "d2h_operation_success_count": 2,
                "kernel_launch_attempt_count": 1,
                "kernel_launch_success_count": 1,
                "sync_attempt_count": 1,
                "sync_success_count": 0,
            },
            "hip_resident_result_export_failed",
        ),
    ),
)
def test_device_stage_failure_poison_has_exact_delta_and_never_calls_oracle(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    failure_index: int,
    expected: dict[str, int],
    reason_code: str,
) -> None:
    *_, runtime, _, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    if failure == "h2d":
        runtime.h2d_failure_at = runtime.h2d_attempt_count + 1
    elif failure == "launch":
        residual_kernel.fail_launch = True
    elif failure == "d2h":
        runtime.d2h_failure_at = runtime.d2h_calls + failure_index
    else:
        runtime.sync_failure_at = runtime.sync_calls + 1

    monkeypatch.setattr(
        type(context._plan),
        "residual",
        lambda *args, **kwargs: pytest.fail("CPU oracle replaced failed HIP work"),
    )
    monkeypatch.setattr(
        type(context._plan),
        "jvp",
        lambda *args, **kwargs: pytest.fail("CPU oracle replaced failed HIP work"),
    )
    try:
        evaluation = context.evaluate_for_verification(np.ones(context._plan.dof_count))
        assert evaluation.receipt.status == "unavailable"
        assert evaluation.residual is evaluation.jvp is None
        assert evaluation.receipt.reason is not None
        assert evaluation.receipt.reason.code == reason_code
        delta = evaluation.receipt.telemetry_delta
        for name, value in expected.items():
            assert getattr(delta, name) == value
        assert delta.allocation_count == 0
        assert delta.fallback_count == 0
        assert context.poisoned and parent.poisoned
        assert context.receipt().telemetry.fallback_count == 0
    finally:
        _close_resident_pair(context, parent)


def test_direct_launch_failure_receipt_is_not_cpu_fallback() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    priming = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    assert priming.receipt.status == "verified"
    residual_kernel.fail_launch = True
    try:
        receipt = context.enqueue_residual_jvp()
        assert receipt.status == "unavailable"
        assert receipt.reason is not None
        assert receipt.reason.code == "hip_resident_kernel_launch_failed"
        assert receipt.telemetry_delta.kernel_launch_attempt_count == 1
        assert receipt.telemetry_delta.kernel_launch_success_count == 0
        assert receipt.telemetry_delta.fallback_count == 0
        assert receipt.sequence == 2
        assert context._enqueue_sequence == 1
        assert context.poisoned and parent.poisoned
    finally:
        _close_resident_pair(context, parent)


def test_trial_state_is_rejected_before_parent_lease_or_device_work() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    initial = create_initial_state(plan)
    trial = open_trial_state(initial, np.zeros(plan.dof_count), expected_plan=plan)
    malloc_before = runtime.malloc_calls
    sync_before = runtime.sync_calls
    kernel = FakeResidualKernel(runtime)
    with pytest.raises(HipResidentCsrContextError, match="state_role_invalid"):
        open_hip_resident_csr_execution_context(parent, trial, rtc_kernel=kernel)
    assert runtime.malloc_calls == malloc_before
    assert runtime.sync_calls == sync_before
    assert parent._resident_consumer_token is None
    assert not kernel.closed
    parent.close()


def test_cross_plan_state_is_rejected_before_lease_or_device_work() -> None:
    _, _, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    _, other_state = _other_committed_state()
    kernel = FakeResidualKernel(runtime)
    malloc_before = runtime.malloc_calls
    sync_before = runtime.sync_calls
    with pytest.raises(StateIRError) as caught:
        open_hip_resident_csr_execution_context(
            parent,
            other_state,
            architecture="gfx1030",
            rtc_kernel=kernel,
        )
    assert caught.value.code == "state_plan_binding_mismatch"
    assert runtime.malloc_calls == malloc_before
    assert runtime.sync_calls == sync_before
    assert parent._resident_consumer_token is None
    assert not kernel.closed
    parent.close()


def test_wrong_architecture_is_rejected_before_lease_or_device_work() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    kernel = FakeResidualKernel(runtime)
    state = create_initial_state(plan)
    before = (
        runtime.malloc_calls,
        runtime.sync_calls,
        tuple(runtime.selected_devices),
    )
    with pytest.raises(HipResidentCsrContextError) as caught:
        open_hip_resident_csr_execution_context(
            parent,
            state,
            architecture="gfx1100",
            rtc_kernel=kernel,
        )
    assert caught.value.code == "hip_resident_architecture_mismatch"
    assert (
        runtime.malloc_calls,
        runtime.sync_calls,
        tuple(runtime.selected_devices),
    ) == before
    assert parent._resident_consumer_token is None
    assert not kernel.closed
    parent.close()


def test_non_reclaimable_caller_kernel_is_rejected_before_parent_lease() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    before = (runtime.malloc_calls, runtime.sync_calls)
    with pytest.raises(HipResidentCsrContextError) as caught:
        open_hip_resident_csr_execution_context(
            parent,
            create_initial_state(plan),
            architecture="gfx1030",
            rtc_kernel=object(),
        )
    assert caught.value.code == "hip_resident_kernel_contract_invalid"
    assert (runtime.malloc_calls, runtime.sync_calls) == before
    assert parent._resident_consumer_token is None
    parent.close()


def test_closed_caller_kernel_is_rejected_before_parent_lease() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    kernel = FakeResidualKernel(runtime)
    kernel.closed = True
    before = (runtime.malloc_calls, runtime.sync_calls)
    with pytest.raises(HipResidentCsrContextError) as caught:
        open_hip_resident_csr_execution_context(
            parent,
            create_initial_state(plan),
            architecture="gfx1030",
            rtc_kernel=kernel,
        )
    assert caught.value.code == "hip_resident_kernel_closed"
    assert (runtime.malloc_calls, runtime.sync_calls) == before
    assert parent._resident_consumer_token is None
    assert kernel.close_calls == 0
    parent.close()


def test_mutated_parent_plan_is_rejected_before_lease() -> None:
    _, _, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    original = parent._source_plan
    other_plan, _ = _other_committed_state()
    parent._source_plan = other_plan
    try:
        with pytest.raises(HipAssemblyContextError, match="live_binding"):
            open_hip_resident_csr_execution_context(
                parent,
                create_initial_state(other_plan),
                architecture="gfx1030",
                rtc_kernel=FakeResidualKernel(runtime),
            )
        assert parent._resident_consumer_token is None
    finally:
        parent._source_plan = original
        parent.close()


@pytest.mark.parametrize("failure_at", (1, 2, 3, 4))
def test_partial_owned_allocation_failure_cleans_module_and_releases_lease(
    failure_at: int,
) -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    state = create_initial_state(plan)
    kernel = FakeResidualKernel(runtime)
    parent_allocations = set(runtime.allocations)
    runtime.malloc_failure_at = runtime.malloc_calls + failure_at
    opened = open_hip_resident_csr_execution_context(
        parent,
        state,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    assert not opened.ready and opened.context is None
    telemetry = opened.receipt.telemetry
    assert telemetry.owned_allocation_attempt_count == failure_at
    assert telemetry.owned_allocation_success_count == failure_at - 1
    assert telemetry.owned_deallocation_attempt_count == failure_at - 1
    assert telemetry.owned_deallocation_success_count == failure_at - 1
    assert telemetry.owned_current_device_bytes == 0
    assert telemetry.module_close_attempt_count == 1
    assert telemetry.module_close_success_count == 1
    assert telemetry.lease_release_attempt_count == 1
    assert telemetry.lease_release_success_count == 1
    assert telemetry.fallback_count == 0
    assert kernel.closed
    assert parent._resident_consumer_token is None
    assert set(runtime.allocations) == parent_allocations
    parent.close()


def test_partial_open_free_failure_returns_owner_and_retry_cleans_exactly_once() -> (
    None
):
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    state = create_initial_state(plan)
    kernel = FakeResidualKernel(runtime)
    first_child_pointer = runtime._next
    runtime.malloc_failure_at = runtime.malloc_calls + 2
    runtime.free_failure_pointer_once = first_child_pointer
    opened = open_hip_resident_csr_execution_context(
        parent,
        state,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert not opened.ready and context is not None
    assert opened.receipt.status == "cleanup_failed"
    assert set(context._pointers) == {"state_displacement"}
    assert parent._resident_consumer_token is context._lease_token
    assert not kernel.closed
    with pytest.raises(HipAssemblyContextError, match="resident_consumer_active"):
        parent.close()
    context.close()
    assert context.closed and kernel.closed
    assert parent._resident_consumer_token is None
    closed = context.receipt().telemetry
    assert closed.owned_deallocation_attempt_count == 2
    assert closed.owned_deallocation_success_count == 1
    assert closed.module_close_attempt_count == closed.module_close_success_count == 1
    assert closed.lease_release_attempt_count == closed.lease_release_success_count == 1
    parent.close()


def test_ready_close_partial_free_failure_preserves_borrowed_parent_and_retries() -> (
    None
):
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    parent_owned = set(parent._pointers.values()) | set(
        parent._base_context._pointers.values()
    )
    failed_pointer = context._pointers["jvp_workspace"]
    context._runtime.free_failure_pointer_once = failed_pointer
    with pytest.raises(HipResidentCsrContextError) as caught:
        context.close()
    assert caught.value.code == "hip_resident_cleanup_failed"
    assert caught.value.cleanup_owner is context
    assert set(context._pointers) == {"jvp_workspace"}
    assert parent_owned.issubset(context._runtime.allocations)
    assert not residual_kernel.closed
    assert parent._resident_consumer_token is context._lease_token
    context.close()
    telemetry = context.receipt().telemetry
    assert telemetry.owned_deallocation_attempt_count == 5
    assert telemetry.owned_deallocation_success_count == 4
    assert telemetry.owned_current_device_bytes == 0
    assert (
        telemetry.module_close_attempt_count
        == telemetry.module_close_success_count
        == 1
    )
    assert (
        telemetry.lease_release_attempt_count
        == telemetry.lease_release_success_count
        == 1
    )
    assert residual_kernel.closed
    assert parent._resident_consumer_token is None
    parent.close()


def test_allocation_failure_and_module_close_failure_keep_retryable_owner() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    state = create_initial_state(plan)
    kernel = FakeResidualKernel(runtime, close_failures=1)
    runtime.malloc_failure_at = runtime.malloc_calls + 2
    opened = open_hip_resident_csr_execution_context(
        parent,
        state,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert not opened.ready and context is not None
    assert opened.receipt.status == "cleanup_failed"
    assert not context._pointers
    assert not kernel.closed
    assert parent._resident_consumer_token is context._lease_token
    context.close()
    telemetry = context.receipt().telemetry
    assert telemetry.module_close_attempt_count == 2
    assert telemetry.module_close_success_count == 1
    assert (
        telemetry.lease_release_attempt_count
        == telemetry.lease_release_success_count
        == 1
    )
    assert kernel.closed
    parent.close()


def test_live_kernel_identity_mutation_precedes_launch_and_does_not_advance_sequence() -> (
    None
):
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    first = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    assert first.receipt.status == "verified"
    launches_before = len(residual_kernel.launches)
    residual_kernel.identity.manifest["code_object_sha256"] = "sha256:" + "9" * 64
    try:
        failed = context.enqueue_residual_jvp()
        assert failed.status == "unavailable"
        assert failed.reason is not None
        assert failed.reason.code == "hip_resident_kernel_binding_changed"
        assert failed.sequence == 2
        assert failed.telemetry_delta.kernel_launch_attempt_count == 0
        assert failed.telemetry_delta.kernel_launch_success_count == 0
        assert failed.telemetry_delta.fallback_count == 0
        assert len(residual_kernel.launches) == launches_before
        assert context._enqueue_sequence == 1
        assert context.receipt().telemetry.kernel_launch_attempt_count == 1
        assert context.poisoned and parent.poisoned
    finally:
        _close_resident_pair(context, parent)


@pytest.mark.parametrize(
    ("target", "expected_code"),
    (
        ("borrowed_pointer", "hip_resident_borrowed_pointer_changed"),
        ("stream", "hip_resident_runtime_authority_changed"),
    ),
)
def test_live_borrowed_pointer_and_stream_identity_change_fail_before_launch(
    target: str,
    expected_code: str,
) -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    priming = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    assert priming.receipt.status == "verified"
    launches_before = len(residual_kernel.launches)
    if target == "borrowed_pointer":
        saved = parent._pointers["csr_values"]
        parent._pointers["csr_values"] = object()
    else:
        saved = context._stream
        context._stream = object()
    try:
        with pytest.raises(HipResidentCsrContextError) as caught:
            context.enqueue_residual_jvp()
        assert caught.value.code == expected_code
        assert len(residual_kernel.launches) == launches_before
        assert context._enqueue_sequence == 1
        assert context.poisoned and parent.poisoned
    finally:
        if target == "borrowed_pointer":
            parent._pointers["csr_values"] = saved
        else:
            context._stream = saved
        _close_resident_pair(context, parent)


def test_lease_epoch_and_enqueue_sequence_are_monotonic_and_context_bound() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    state = create_initial_state(plan)

    first_kernel = FakeResidualKernel(runtime)
    first_open = open_hip_resident_csr_execution_context(
        parent,
        state,
        architecture="gfx1030",
        rtc_kernel=first_kernel,
    )
    first_context = first_open.context
    assert first_context is not None
    first_prime = first_context.evaluate_for_verification(
        np.ones(plan.dof_count, dtype="<f8")
    )
    assert first_prime.receipt.status == "verified"
    first_rows = (
        first_context.enqueue_residual_jvp(),
        first_context.enqueue_residual_jvp(),
    )
    assert [row.sequence for row in first_rows] == [2, 3]
    assert len({row.enqueue_id for row in first_rows}) == 2
    first_epoch = first_open.receipt.bindings.lease_epoch
    first_context_id = first_context.context_id
    first_context.close()

    second_kernel = FakeResidualKernel(runtime)
    second_open = open_hip_resident_csr_execution_context(
        parent,
        state,
        architecture="gfx1030",
        rtc_kernel=second_kernel,
    )
    second_context = second_open.context
    assert second_context is not None
    second_prime = second_context.evaluate_for_verification(
        np.ones(plan.dof_count, dtype="<f8")
    )
    assert second_prime.receipt.status == "verified"
    second = second_context.enqueue_residual_jvp()
    assert second.sequence == 2
    assert second_open.receipt.bindings.lease_epoch == first_epoch + 1
    assert second_context.context_id != first_context_id
    assert second.context_id == second_context.context_id
    second_context.close()
    parent.close()


def test_rehashed_enqueue_sequence_forgery_is_rejected_against_live_context() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    try:
        priming = context.evaluate_for_verification(
            np.ones(context._plan.dof_count, dtype="<f8")
        )
        assert priming.receipt.status == "verified"
        receipt = context.enqueue_residual_jvp()
        forged = replace(receipt, sequence=receipt.sequence + 7)
        forged = _rehash_enqueue(forged)
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_enqueue_receipt(forged, expected_context=context)
    finally:
        _close_resident_pair(context, parent)


def test_context_and_evaluation_receipts_are_strict_and_rehashed_tamper_fails() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(
        np.arange(context._plan.dof_count, dtype="<f8")
    )
    rows = (
        (
            SCHEMAS / "hip_resident_csr_context_v1.schema.json",
            opened.receipt.to_dict(),
        ),
        (
            SCHEMAS / "hip_resident_csr_evaluation_v1.schema.json",
            evaluation.to_dict(),
        ),
    )
    for path, payload in rows:
        Draft202012Validator(json.loads(path.read_text())).validate(payload)

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
    with pytest.raises(HipResidentCsrContextError):
        validate_hip_resident_csr_context_receipt(forged)

    forged_eval = replace(
        evaluation.receipt,
        claims=replace(evaluation.receipt.claims, iteration_host_copy_zero=True),
    )
    forged_eval = replace(
        forged_eval,
        receipt_hash=canonical_hash(
            _evaluation_payload(forged_eval, include_hash=False)
        ),
    )
    with pytest.raises(HipResidentCsrContextError):
        validate_hip_resident_csr_evaluation(
            replace(evaluation, receipt=forged_eval), expected_context=context
        )
    context.close()
    parent.close()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: replace(row, telemetry=replace(row.telemetry, fallback_count=True)),
        lambda row: replace(row, bindings=replace(row.bindings, lease_epoch=True)),
        lambda row: replace(
            row,
            dimensions=replace(row.dimensions, borrowed_buffer_count=5),
        ),
        lambda row: replace(row, kernel=replace(row.kernel, abi_version=True)),
        lambda row: replace(
            row,
            claims=replace(row.claims, same_runtime_device_stream=False),
        ),
        lambda row: replace(
            row,
            dimensions=replace(
                row.dimensions, free_dof_count=0, constrained_dof_count=0
            ),
        ),
        lambda row: replace(
            row,
            owned_buffers=(
                replace(row.owned_buffers[0], shape=(1,), byte_length=8),
                *row.owned_buffers[1:],
            ),
        ),
    ),
)
def test_rehashed_context_nested_and_scalar_forgery_is_rejected(mutate: Any) -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    try:
        forged = _rehash_context(mutate(opened.receipt))
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_context_receipt(forged)
    finally:
        _close_resident_pair(context, parent)


def test_ready_receipt_rejects_teardown_or_missing_backend_forgery() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    try:
        for forged in (
            replace(
                opened.receipt,
                telemetry=replace(
                    opened.receipt.telemetry,
                    owned_deallocation_attempt_count=1,
                ),
            ),
            replace(
                opened.receipt,
                telemetry=replace(
                    opened.receipt.telemetry, module_close_attempt_count=1
                ),
            ),
            replace(
                opened.receipt,
                telemetry=replace(
                    opened.receipt.telemetry, lease_release_attempt_count=1
                ),
            ),
            replace(
                opened.receipt,
                telemetry=replace(opened.receipt.telemetry, owned_peak_device_bytes=0),
            ),
            replace(
                opened.receipt,
                telemetry=replace(opened.receipt.telemetry, h2d_bytes_attempted=0),
            ),
            replace(
                opened.receipt,
                telemetry=replace(
                    opened.receipt.telemetry,
                    d2h_operation_attempt_count=1,
                    d2h_operation_success_count=1,
                    d2h_bytes_attempted=0,
                    d2h_bytes_succeeded=999,
                ),
            ),
            replace(opened.receipt, actual_backend=None),
        ):
            with pytest.raises(HipResidentCsrContextError):
                validate_hip_resident_csr_context_receipt(_rehash_context(forged))
    finally:
        _close_resident_pair(context, parent)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: replace(
            row,
            telemetry_delta=replace(row.telemetry_delta, fallback_count=True),
        ),
        lambda row: replace(row, direction=replace(row.direction, byte_length=True)),
        lambda row: replace(row, work=replace(row.work, csr_nnz=True)),
        lambda row: replace(
            row,
            claims=replace(row.claims, zero_consumer_csr_h2d=False),
        ),
        lambda row: replace(
            row,
            parity=replace(
                row.parity,
                residual_full=replace(row.parity.residual_full, count=True),
            ),
        ),
    ),
)
def test_rehashed_evaluation_nested_and_scalar_forgery_is_rejected(
    mutate: Any,
) -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(
        np.arange(context._plan.dof_count, dtype="<f8")
    )
    assert evaluation.receipt.parity is not None
    try:
        forged = _rehash_evaluation(mutate(evaluation.receipt))
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_evaluation(
                replace(evaluation, receipt=forged), expected_context=context
            )
    finally:
        _close_resident_pair(context, parent)


def test_completed_evaluation_rejects_rehashed_unavailable_nested_enqueue() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    enqueue = evaluation.enqueue
    assert enqueue is not None and enqueue.status == "enqueued"
    forged_enqueue = replace(
        enqueue,
        status="unavailable",
        reason=HipResidentCsrReason("forged_failure", "forged failure"),
        telemetry_delta=replace(enqueue.telemetry_delta, kernel_launch_success_count=0),
        residual_jvp_enqueued=False,
    )
    forged_enqueue = _rehash_enqueue(forged_enqueue)
    forged_receipt = _rehash_evaluation(
        replace(evaluation.receipt, enqueue=forged_enqueue)
    )
    try:
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_evaluation(
                replace(
                    evaluation,
                    receipt=forged_receipt,
                    enqueue=forged_enqueue,
                ),
                expected_context=context,
            )
    finally:
        _close_resident_pair(context, parent)


def test_evaluation_receipt_live_validation_binds_nested_enqueue() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    enqueue = evaluation.enqueue
    assert enqueue is not None
    mutations = (
        replace(enqueue, kernel_identity_hash="sha256:" + "9" * 64),
        replace(enqueue, sequence=enqueue.sequence + 100),
    )
    try:
        for mutated in mutations:
            mutated = replace(
                mutated,
                enqueue_id=canonical_hash(
                    {
                        "context_id": mutated.context_id,
                        "sequence": mutated.sequence,
                        "state_hash": mutated.state_hash,
                    }
                ),
            )
            mutated = _rehash_enqueue(mutated)
            forged = replace(
                evaluation.receipt,
                enqueue=mutated,
                execution_id=canonical_hash(
                    {
                        "context_id": evaluation.receipt.context_id,
                        "opening_context_receipt_hash": (
                            evaluation.receipt.opening_context_receipt_hash
                        ),
                        "direction_hash": evaluation.receipt.direction.data_hash,
                        "next_sequence": mutated.sequence,
                    }
                ),
            )
            forged = _rehash_evaluation(forged)
            with pytest.raises(HipResidentCsrContextError):
                validate_hip_resident_csr_evaluation_receipt(
                    forged, expected_context=context
                )
    finally:
        _close_resident_pair(context, parent)


def test_completed_evaluation_receipt_binds_bytes_descriptors_and_counts() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    evaluation = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    receipt = evaluation.receipt
    assert receipt.parity is not None and receipt.residual is not None
    mutations = (
        replace(
            receipt,
            telemetry_delta=replace(
                receipt.telemetry_delta,
                h2d_bytes_attempted=0,
                h2d_bytes_succeeded=0,
            ),
        ),
        replace(
            receipt, direction=replace(receipt.direction, shape=(1,), byte_length=8)
        ),
        replace(receipt, residual=replace(receipt.residual, shape=(1,), byte_length=8)),
        replace(
            receipt,
            parity=replace(
                receipt.parity,
                residual_full=replace(receipt.parity.residual_full, count=1),
            ),
        ),
        replace(
            receipt,
            parity=replace(
                receipt.parity,
                residual_full=replace(receipt.parity.residual_full, passed=False),
            ),
        ),
        replace(
            receipt,
            parity=replace(
                receipt.parity,
                residual_full=replace(
                    receipt.parity.residual_full,
                    max_abs_error=1.0e30,
                    relative_l2_error=1.0e30,
                    max_scaled_error=1.0e30,
                ),
            ),
        ),
    )
    try:
        for mutated in mutations:
            mutated = _rehash_evaluation(mutated)
            with pytest.raises(HipResidentCsrContextError):
                validate_hip_resident_csr_evaluation_receipt(
                    mutated, expected_context=context
                )
    finally:
        _close_resident_pair(context, parent)


def test_unavailable_evaluation_receipt_enforces_stage_prefix() -> None:
    *_, runtime, _, _, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    runtime.h2d_failure_at = runtime.h2d_attempt_count + 1
    evaluation = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    receipt = evaluation.receipt
    assert receipt.status == "unavailable" and receipt.enqueue is None
    vector_bytes = 8 * context._plan.dof_count
    mutations = (
        replace(
            receipt,
            telemetry_delta=replace(
                receipt.telemetry_delta,
                h2d_operation_attempt_count=5,
                h2d_bytes_attempted=5 * vector_bytes,
            ),
        ),
        replace(
            receipt,
            telemetry_delta=replace(
                receipt.telemetry_delta,
                d2h_operation_attempt_count=1,
                d2h_bytes_attempted=vector_bytes,
            ),
        ),
    )
    try:
        for mutated in mutations:
            with pytest.raises(HipResidentCsrContextError):
                validate_hip_resident_csr_evaluation_receipt(
                    _rehash_evaluation(mutated), expected_context=context
                )
    finally:
        _close_resident_pair(context, parent)


def test_closed_receipt_rejects_rehashed_incomplete_cleanup_telemetry() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    context.close()
    closed = context.receipt()
    try:
        for telemetry in (
            replace(closed.telemetry, owned_current_device_bytes=8),
            replace(closed.telemetry, module_close_success_count=0),
            replace(closed.telemetry, lease_release_success_count=0),
        ):
            forged = _rehash_context(replace(closed, telemetry=telemetry))
            with pytest.raises(HipResidentCsrContextError):
                validate_hip_resident_csr_context_receipt(forged)
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_context_receipt(
                _rehash_context(replace(closed, actual_backend=None))
            )
    finally:
        parent.close()


def test_rehashed_runtime_handle_text_in_reason_is_rejected() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    priming = context.evaluate_for_verification(
        np.ones(context._plan.dof_count, dtype="<f8")
    )
    assert priming.receipt.status == "verified"
    residual_kernel.fail_launch = True
    failed = context.enqueue_residual_jvp()
    assert failed.status == "unavailable"
    poisoned = context.receipt()
    assert poisoned.reason is not None
    try:
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_context_receipt(
                _rehash_context(replace(poisoned, actual_backend=None))
            )
        forged = replace(
            poisoned,
            reason=HipResidentCsrReason(
                poisoned.reason.code,
                "pointer=123 stream=456 handle=789 address=0xdeadbeef",
            ),
        )
        forged = _rehash_context(forged)
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_context_receipt(forged)
    finally:
        _close_resident_pair(context, parent)


@pytest.mark.parametrize(
    "value",
    (
        "c_void_p(123456789)",
        "ctypes.c_void_p(123456789)",
        "device_ptr(123456789)",
        "CUdeviceptr(123456789)",
    ),
)
def test_decimal_runtime_pointer_text_is_detected_and_redacted(value: str) -> None:
    assert _has_runtime_value(value)
    redacted = _bounded_detail(value)
    assert "123456789" not in redacted
    assert not _has_runtime_value(redacted)


def test_long_decimal_detail_is_redacted_without_rejecting_numeric_identifier() -> None:
    assert not _has_runtime_value("LC_123456789")
    assert not _has_runtime_value("123456789")
    assert "123456789" not in _bounded_detail("failure 123456789")


def test_kernel_close_failure_preserves_parent_lease_for_retry() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident(close_failures=1)
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    with pytest.raises(HipResidentCsrContextError, match="kernel_cleanup_failed"):
        context.close()
    failed_receipt = context.receipt()
    failed = failed_receipt.telemetry
    assert failed.module_close_attempt_count == 1
    assert failed.module_close_success_count == 0
    assert failed.lease_release_attempt_count == 0
    assert failed.lease_release_success_count == 0
    with pytest.raises(HipResidentCsrContextError):
        validate_hip_resident_csr_context_receipt(
            _rehash_context(replace(failed_receipt, actual_backend=None))
        )
    assert parent._resident_consumer_token is not None
    with pytest.raises(HipAssemblyContextError, match="resident_consumer_active"):
        parent.close()
    context.close()
    assert residual_kernel.closed
    assert parent._resident_consumer_token is None
    closed = context.receipt().telemetry
    assert closed.module_close_attempt_count == 2
    assert closed.module_close_success_count == 1
    assert closed.lease_release_attempt_count == 1
    assert closed.lease_release_success_count == 1
    parent.close()


def test_receipt_waits_for_concurrent_close_snapshot_boundary() -> None:
    *_, runtime, _, _, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    first_free_complete = threading.Event()
    continue_close = threading.Event()
    receipt_complete = threading.Event()
    close_errors: list[BaseException] = []
    receipt_errors: list[BaseException] = []
    receipts: list[Any] = []
    original_free = runtime.free
    free_count = 0

    def blocking_free(pointer: int) -> None:
        nonlocal free_count
        original_free(pointer)
        free_count += 1
        if free_count == 1:
            first_free_complete.set()
            if not continue_close.wait(timeout=5):
                raise RuntimeError("test close barrier timed out")

    def close_context() -> None:
        try:
            context.close()
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            close_errors.append(exc)

    def read_receipt() -> None:
        try:
            receipts.append(context.receipt())
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            receipt_errors.append(exc)
        finally:
            receipt_complete.set()

    runtime.free = blocking_free
    close_thread = threading.Thread(target=close_context, daemon=True)
    receipt_thread = threading.Thread(target=read_receipt, daemon=True)
    close_thread.start()
    barrier_reached = first_free_complete.wait(timeout=5)
    if barrier_reached:
        receipt_thread.start()
        receipt_was_blocked = not receipt_complete.wait(timeout=0.05)
    else:
        receipt_was_blocked = False
    continue_close.set()
    close_thread.join(timeout=5)
    if receipt_thread.ident is not None:
        receipt_thread.join(timeout=5)
    runtime.free = original_free
    assert barrier_reached and receipt_was_blocked
    assert not close_thread.is_alive() and not receipt_thread.is_alive()
    assert not close_errors and not receipt_errors
    assert len(receipts) == 1 and receipts[0].status == "context_closed"
    parent.close()


def test_cleanup_sync_failure_preserves_all_ownership_for_retry() -> None:
    *_, residual_kernel, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    owned = dict(context._pointers)
    context._runtime.sync_failure_at = context._runtime.sync_calls + 1
    with pytest.raises(HipResidentCsrContextError) as caught:
        context.close()
    assert caught.value.code == "hip_resident_cleanup_sync_failed"
    assert caught.value.cleanup_owner is context
    assert context._pointers == owned
    assert not residual_kernel.closed
    assert parent._resident_consumer_token is context._lease_token
    failed = context.receipt().telemetry
    assert failed.sync_attempt_count == failed.sync_success_count + 1
    assert failed.owned_deallocation_attempt_count == 0
    assert failed.module_close_attempt_count == 0
    assert failed.lease_release_attempt_count == 0
    context.close()
    assert context.closed and residual_kernel.closed
    assert parent._resident_consumer_token is None
    parent.close()


def test_native_identity_late_unavailable_receipt_allows_no_executed_backend() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    kernel = FakeResidualKernel(runtime)
    runtime.malloc_failure_at = runtime.malloc_calls + 1
    opened = open_hip_resident_csr_execution_context(
        parent,
        create_initial_state(plan),
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    assert opened.context is None and opened.receipt.status == "unavailable"
    assert opened.receipt.kernel is not None
    native = replace(
        opened.receipt,
        actual_backend=None,
        evidence_scope="native_hiprtc_composite",
        bindings=replace(
            opened.receipt.bindings,
            parent_evidence_scope="native_hiprtc",
            residual_kernel_origin="internally_compiled",
        ),
        kernel=replace(
            opened.receipt.kernel,
            runtime_library_discovery_source="explicit",
            hiprtc_library_discovery_source="explicit",
        ),
    )
    native = replace(
        native,
        context_receipt_hash=canonical_hash(
            _context_payload(native, include_hash=False)
        ),
    )
    validate_hip_resident_csr_context_receipt(native)
    parent.close()


def test_invalid_kernel_binding_and_first_close_failure_preserve_owner_receipt() -> (
    None
):
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    kernel = FakeResidualKernel(runtime, close_failures=1)
    kernel.identity.manifest["kernel_symbol"] = "forged_symbol"
    opened = open_hip_resident_csr_execution_context(
        parent,
        create_initial_state(plan),
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    context = opened.context
    assert context is not None and opened.receipt.status == "cleanup_failed"
    assert opened.receipt.kernel is None
    assert opened.receipt.telemetry.module_owner_acquired_count == 1
    assert opened.receipt.telemetry.module_close_attempt_count == 1
    assert opened.receipt.telemetry.module_close_success_count == 0
    context.close()
    closed = context.receipt()
    assert closed.status == "context_closed"
    assert closed.kernel is None
    assert closed.telemetry.module_owner_acquired_count == 1
    assert closed.telemetry.module_close_attempt_count == 2
    assert closed.telemetry.module_close_success_count == 1
    validate_hip_resident_csr_context_receipt(closed)
    parent.close()


def test_unavailable_receipt_requires_complete_cleanup_telemetry() -> None:
    _, plan, _, runtime, _, parent_open = _open_parent()
    parent = parent_open.context
    assert parent is not None
    kernel = FakeResidualKernel(runtime)
    runtime.malloc_failure_at = runtime.malloc_calls + 2
    opened = open_hip_resident_csr_execution_context(
        parent,
        create_initial_state(plan),
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    receipt = opened.receipt
    assert receipt.status == "unavailable" and opened.context is None
    assert receipt.telemetry.owned_allocation_success_count == 1
    for telemetry in (
        replace(receipt.telemetry, module_close_success_count=0),
        replace(receipt.telemetry, lease_release_success_count=0),
        replace(
            receipt.telemetry,
            owned_deallocation_success_count=0,
            owned_current_device_bytes=8 * plan.dof_count,
        ),
        replace(
            receipt.telemetry,
            module_owner_acquired_count=0,
            module_close_success_count=0,
        ),
    ):
        forged = _rehash_context(replace(receipt, telemetry=telemetry))
        with pytest.raises(HipResidentCsrContextError):
            validate_hip_resident_csr_context_receipt(forged)
    parent.close()


def test_cleanup_failed_receipt_cannot_claim_fully_released_ownership() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    context.close()
    closed = context.receipt()
    active_claims = replace(
        closed.claims,
        exclusive_parent_lease_active=True,
        same_runtime_device_stream=True,
        borrowed_assembly_csr=True,
        borrowed_foundation_load=True,
        host_csr_reupload_avoided=True,
    )
    forged = replace(
        closed,
        status="cleanup_failed",
        reason=HipResidentCsrReason("forged_cleanup_failed", "forged"),
        claims=active_claims,
    )
    forged = _rehash_context(forged)
    with pytest.raises(HipResidentCsrContextError):
        validate_hip_resident_csr_context_receipt(forged)
    parent.close()


def test_poisoned_receipt_cannot_claim_fully_released_ownership() -> None:
    *_, parent_open, opened = _open_resident()
    context = opened.context
    parent = parent_open.context
    assert context is not None and parent is not None
    context.close()
    closed = context.receipt()
    active_claims = replace(
        closed.claims,
        exclusive_parent_lease_active=True,
        same_runtime_device_stream=True,
        borrowed_assembly_csr=True,
        borrowed_foundation_load=True,
        host_csr_reupload_avoided=True,
    )
    forged = replace(
        closed,
        status="poisoned",
        reason=HipResidentCsrReason("forged_poisoned", "forged"),
        claims=active_claims,
    )
    forged = _rehash_context(forged)
    with pytest.raises(HipResidentCsrContextError):
        validate_hip_resident_csr_context_receipt(forged)
    parent.close()
