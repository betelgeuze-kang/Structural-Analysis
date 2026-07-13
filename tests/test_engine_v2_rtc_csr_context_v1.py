from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.backends.hip.context import HipContextError
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan import (
    compile_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.rtc_backend import rtc as rtc_core
from structural_analysis.engine_v2.rtc_backend import csr_context as context_module
from structural_analysis.engine_v2.rtc_backend.csr_context import (
    HipRtcCsrContextError,
    _context_payload,
    _result_payload,
    open_hip_rtc_csr_execution_context,
    validate_hip_rtc_csr_context_receipt,
    validate_hip_rtc_residual_jvp_evaluation,
    validate_hip_rtc_residual_jvp_receipt,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (
    HipRtcLibraryIdentity,
)
from structural_analysis.model_ir import load_model_ir_v2

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA_ROOT = REPO_ROOT / "src/structural_analysis/schemas"


class FakeHipRuntime:
    library_name = "fake-libamdhip64"

    def __init__(
        self,
        *,
        malloc_failure_at: int | None = None,
        free_failure_pointer_once: int | None = None,
        free_failure_pointer_always: int | None = None,
        d2h_failure_at: int | None = None,
    ) -> None:
        self.malloc_failure_at = malloc_failure_at
        self.free_failure_pointer_once = free_failure_pointer_once
        self.free_failure_pointer_always = free_failure_pointer_always
        self.d2h_failure_at = d2h_failure_at
        self.init_calls = 0
        self.malloc_calls = 0
        self.free_calls = 0
        self.h2d_calls = 0
        self.d2h_calls = 0
        self.sync_calls = 0
        self.stream_destroy_calls = 0
        self.allocations: dict[int, bytearray] = {}
        self._next_pointer = 1
        self.total_memory = 8 * 1024**3

    def hip_init(self) -> int:
        self.init_calls += 1
        return 0

    def hip_get_device_count(self) -> tuple[int, int]:
        return 0, 1

    def hip_device_get_name(self, ordinal: int) -> tuple[int, str]:
        del ordinal
        return 0, "Fake AMD GPU"

    def hip_runtime_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_driver_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_error_string(self, status: int) -> str:
        return f"fake HIP status {status}"

    def set_device(self, ordinal: int) -> None:
        del ordinal

    def mem_info(self) -> tuple[int, int]:
        used = sum(len(value) for value in self.allocations.values())
        return self.total_memory - used, self.total_memory

    def create_stream(self) -> object:
        return object()

    def malloc(self, byte_length: int) -> int:
        self.malloc_calls += 1
        if self.malloc_failure_at == self.malloc_calls:
            raise HipContextError(
                "hip_allocation_failed", "injected allocation failure"
            )
        pointer = self._next_pointer
        self._next_pointer += 1
        self.allocations[pointer] = bytearray(byte_length)
        return pointer

    def copy_h2d_async(
        self, pointer: int, array: np.ndarray, stream: object
    ) -> None:
        del stream
        self.h2d_calls += 1
        self.allocations[pointer][:] = memoryview(array).cast("B")

    def copy_d2h_async(
        self, array: np.ndarray, pointer: int, stream: object
    ) -> None:
        del stream
        self.d2h_calls += 1
        if self.d2h_failure_at == self.d2h_calls:
            raise HipContextError(
                "hip_copy_failed", "injected D2H failure"
            )
        memoryview(array).cast("B")[:] = self.allocations[pointer]

    def synchronize(self, stream: object) -> None:
        del stream
        self.sync_calls += 1

    def free(self, pointer: int) -> None:
        self.free_calls += 1
        if self.free_failure_pointer_once == pointer:
            self.free_failure_pointer_once = None
            raise HipContextError(
                "hip_device_access_failed", "injected free failure"
            )
        if self.free_failure_pointer_always == pointer:
            raise HipContextError(
                "hip_device_access_failed", "persistent injected free failure"
            )
        del self.allocations[pointer]

    def destroy_stream(self, stream: object) -> None:
        del stream
        self.stream_destroy_calls += 1


class MutableIdentity:
    def __init__(self) -> None:
        rtc_library = HipRtcLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libhiprtc.so",
            loaded_name="fake-libhiprtc.so",
            resolved_path="/fake/libhiprtc.so",
            sha256="sha256:" + ("2" * 64),
        )
        runtime_library = HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path=None,
            sha256="sha256:" + ("1" * 64),
        )
        identity = rtc_core._build_identity(
            architecture="gfx1030",
            source_hash=rtc_core._sha256_bytes(rtc_core._fixed_source()),
            options=("--offload-arch=gfx1030", "-O3", "-std=c++17"),
            rtc_version=(9, 0),
            rtc_library=rtc_library,
            runtime_library=runtime_library,
            code_object=b"fake-amdgpu-code-object-v1",
        )
        self.manifest = identity.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.manifest))


class FakeRtcKernel:
    def __init__(
        self,
        runtime: FakeHipRuntime,
        *,
        output_bias: float = 0.0,
        fail_launch: bool = False,
    ) -> None:
        self.runtime = runtime
        self.output_bias = output_bias
        self.fail_launch = fail_launch
        self.launch_calls = 0
        self.close_calls = 0
        self.closed = False
        self.identity = MutableIdentity()

    def launch_residual_jvp(
        self,
        stream: Any,
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
        del stream
        self.launch_calls += 1
        if self.fail_launch:
            raise RuntimeError("injected kernel failure")

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
            start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
            indices = columns[start:stop]
            row_values = values[start:stop]
            residual[row] = np.dot(row_values, state[indices]) - load[row]
            jvp[row] = np.dot(row_values, direction[indices])
        if self.output_bias:
            residual[0] += self.output_bias
            jvp[0] += self.output_bias

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True


def _contracts(load_pattern_id: str = "LC_AXIAL"):
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    plan = compile_execution_plan(buffers)
    return buffers, plan, create_initial_state(plan)


def _open(
    *,
    runtime: FakeHipRuntime | None = None,
    kernel: FakeRtcKernel | None = None,
):
    buffers, plan, state = _contracts()
    runtime = runtime or FakeHipRuntime()
    kernel = kernel or FakeRtcKernel(runtime)
    opened = open_hip_rtc_csr_execution_context(
        buffers,
        plan,
        state,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    return buffers, plan, state, runtime, kernel, opened


def test_open_binds_exact_plan_state_and_eight_child_allocations() -> None:
    buffers, plan, state, runtime, kernel, opened = _open()
    assert opened.ready, opened.receipt.reason
    assert opened.context is not None
    receipt = opened.receipt
    assert receipt.evidence_scope == "injected_test_double"
    assert receipt.actual_backend == "test_double"
    assert not receipt.promotion_eligible
    assert receipt.bindings.load_source == "execution_plan_global_load"
    assert receipt.bindings.state_load_factor_applied is False
    assert receipt.bindings.state_hash == state.state_hash
    assert receipt.bindings.execution_plan_hash == plan.plan_hash
    assert tuple(view.name for view in receipt.child_buffers) == (
        "csr_row_ptr",
        "csr_column_indices",
        "csr_values",
        "global_load",
        "state_displacement",
        "direction_workspace",
        "residual_workspace",
        "jvp_workspace",
    )
    assert receipt.telemetry.child_allocation_attempt_count == 8
    assert receipt.telemetry.child_allocation_success_count == 8
    assert receipt.telemetry.child_initial_h2d_attempt_count == 5
    assert receipt.telemetry.child_initial_h2d_success_count == 5
    assert receipt.telemetry.fallback_count == 0
    assert runtime.malloc_calls == 16 + 8
    assert runtime.h2d_calls == 16 + 5
    assert runtime.sync_calls == 2
    validate_hip_rtc_csr_context_receipt(
        receipt,
        expected_buffers=buffers,
        expected_plan=plan,
        expected_state=state,
        expected_kernel=kernel,
    )
    serialized = json.dumps(receipt.to_dict()).lower()
    for forbidden in ("pointer", "address", "stream", "handle", "0x"):
        assert forbidden not in serialized
    opened.context.close()


def test_monkeypatched_loader_and_compiler_cannot_assert_native_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffers, plan, state = _contracts()
    runtime = FakeHipRuntime()
    kernel = FakeRtcKernel(runtime)
    monkeypatch.setattr(context_module, "load_hip_native_runtime", lambda _: runtime)
    monkeypatch.setattr(
        context_module,
        "compile_hip_rtc_csr_kernel",
        lambda *args, **kwargs: kernel,
    )
    opened = open_hip_rtc_csr_execution_context(
        buffers, plan, state, architecture="gfx1030"
    )
    assert opened.ready
    assert opened.receipt.evidence_scope == "injected_test_double"
    assert not opened.receipt.claims.native_hiprtc_kernel_loaded
    assert opened.context is not None
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert result.receipt.status == "verified"
    assert result.receipt.evidence_scope == "injected_test_double"
    assert not result.receipt.promotion_eligible
    opened.context.close()


def test_evaluation_has_exact_transfer_delta_parity_and_work_receipt() -> None:
    _, plan, _, runtime, kernel, opened = _open()
    assert opened.context is not None
    direction = np.arange(plan.dof_count, dtype="<f8")
    evaluation = opened.context.evaluate_residual_jvp(direction)
    assert evaluation.receipt.status == "verified"
    assert not evaluation.receipt.promotion_eligible
    assert kernel.launch_calls == 1
    assert runtime.h2d_calls == 16 + 5 + 1
    assert runtime.d2h_calls == 2
    assert runtime.sync_calls == 3
    delta = evaluation.receipt.telemetry_delta
    assert delta.h2d_operation_count == 1
    assert delta.d2h_operation_count == 2
    assert delta.kernel_launch_attempt_count == delta.kernel_launch_count == 1
    assert delta.explicit_sync_count == 1
    assert delta.fallback_count == 0
    parity = evaluation.receipt.parity
    assert parity is not None and parity.passed
    for metric in (
        parity.residual_full,
        parity.residual_free,
        parity.residual_constrained,
        parity.jvp_full,
        parity.jvp_free,
        parity.jvp_constrained,
    ):
        assert metric.max_abs_error <= 1.0e-8
        assert metric.relative_l2_error <= 1.0e-8
    g = plan.dof_count
    z = int(plan.array("csr_column_indices").size)
    work = evaluation.receipt.work.to_dict()
    assert work["multiplication_count"] == 2 * z
    assert work["accumulation_count"] == 2 * z
    assert work["flop_equivalent_count"] == 4 * z + g
    assert work["logical_source_bytes"] == 28 * z + 32 * g
    assert work["physical_dram_bytes"] == "not_instrumented"
    assert work["end_to_end_o_n_claim"] is False
    for array in (
        evaluation.direction,
        evaluation.residual,
        evaluation.jvp,
    ):
        assert array is not None and not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    validate_hip_rtc_residual_jvp_evaluation(
        evaluation, expected_context=opened.context
    )
    opened.context.close()


def test_zero_direction_jvp_is_bit_exact_zero() -> None:
    _, plan, _, _, _, opened = _open()
    assert opened.context is not None
    evaluation = opened.context.evaluate_residual_jvp(
        np.zeros(plan.dof_count)
    )
    assert evaluation.receipt.parity is not None
    assert evaluation.receipt.parity.zero_direction_exact is True
    assert np.array_equal(evaluation.jvp, np.zeros(plan.dof_count))
    opened.context.close()


def test_preflight_rejects_cross_plan_trial_and_budget_before_probe() -> None:
    buffers, plan, state = _contracts("LC_AXIAL")
    _, other_plan, _ = _contracts("LC_WEAK")
    runtime = FakeHipRuntime()
    kernel = FakeRtcKernel(runtime)
    with pytest.raises(HipRtcCsrContextError) as error:
        open_hip_rtc_csr_execution_context(
            buffers,
            other_plan,
            state,
            architecture="gfx1030",
            runtime=runtime,
            rtc_kernel=kernel,
        )
    assert error.value.code == "hip_rtc_binding_invalid"
    trial = open_trial_state(
        state, np.zeros(plan.dof_count), expected_plan=plan
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        open_hip_rtc_csr_execution_context(
            buffers,
            plan,
            trial,
            architecture="gfx1030",
            runtime=runtime,
            rtc_kernel=kernel,
        )
    assert error.value.code == "hip_rtc_state_role_invalid"
    with pytest.raises(HipRtcCsrContextError) as error:
        open_hip_rtc_csr_execution_context(
            buffers,
            plan,
            state,
            architecture="gfx1030",
            memory_budget_bytes=1,
            runtime=runtime,
            rtc_kernel=kernel,
        )
    assert error.value.code == "hip_rtc_memory_budget_exceeded"
    assert runtime.init_calls == runtime.malloc_calls == 0


def test_validation_accepts_expected_plan_state_without_private_buffers() -> None:
    _, plan, state, _, _, opened = _open()
    validate_hip_rtc_csr_context_receipt(
        opened.receipt,
        expected_plan=plan,
        expected_state=state,
    )
    assert opened.context is not None
    opened.context.close()


def test_biased_device_result_fails_parity_and_never_promotes() -> None:
    runtime = FakeHipRuntime()
    kernel = FakeRtcKernel(runtime, output_bias=1.0e-4)
    _, plan, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert result.receipt.status == "parity_failed"
    assert result.receipt.parity is not None
    assert not result.receipt.parity.passed
    assert not result.receipt.promotion_eligible
    assert result.receipt.claims.residual_jvp_executed
    assert not result.receipt.claims.cpu_reference_parity_verified
    opened.context.close()


def test_live_kernel_identity_change_poisoning_precedes_direction_transfer() -> None:
    _, plan, _, runtime, kernel, opened = _open()
    assert opened.context is not None
    initial_h2d = runtime.h2d_calls
    kernel.identity.manifest["code_object_sha256"] = "sha256:" + ("9" * 64)
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert result.receipt.status == "unavailable"
    assert result.receipt.reason is not None
    assert result.receipt.reason.code == "hip_rtc_kernel_binding_changed"
    assert opened.context.poisoned
    assert runtime.h2d_calls == initial_h2d
    assert kernel.launch_calls == 0
    with pytest.raises(HipRtcCsrContextError) as error:
        opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert error.value.code == "hip_rtc_csr_context_poisoned"
    opened.context.close()


def test_kernel_failure_poisoning_never_calls_cpu_oracle_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeHipRuntime()
    kernel = FakeRtcKernel(runtime, fail_launch=True)
    _, plan, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    monkeypatch.setattr(
        "structural_analysis.engine_v2.rtc_backend.csr_context._cpu_csr_oracle",
        lambda *args: pytest.fail("CPU oracle cannot substitute a failed kernel"),
    )
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert result.receipt.status == "unavailable"
    assert result.residual is result.jvp is None
    assert result.receipt.telemetry_delta.kernel_launch_attempt_count == 1
    assert result.receipt.telemetry_delta.kernel_launch_count == 0
    assert result.receipt.telemetry_delta.fallback_count == 0
    assert opened.context.receipt().status == "poisoned"
    opened.context.close()


def test_partial_d2h_failure_is_counted_without_cpu_substitution() -> None:
    runtime = FakeHipRuntime(d2h_failure_at=2)
    _, plan, _, _, _, opened = _open(runtime=runtime)
    assert opened.context is not None
    baseline = opened.context.receipt().telemetry
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert result.receipt.status == "unavailable"
    assert result.receipt.telemetry_delta.d2h_operation_count == 1
    assert result.receipt.telemetry_delta.explicit_sync_count == 0
    poisoned = opened.context.receipt()
    assert poisoned.telemetry.d2h_operation_count == baseline.d2h_operation_count + 1
    assert poisoned.telemetry.d2h_bytes == baseline.d2h_bytes + 8 * plan.dof_count
    assert poisoned.telemetry.fallback_count == 0
    opened.context.close()


def test_partial_open_failure_cleans_children_kernel_and_foundation() -> None:
    runtime = FakeHipRuntime(malloc_failure_at=16 + 4)
    kernel = FakeRtcKernel(runtime)
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert not opened.ready
    assert opened.context is None
    assert opened.receipt.status == "unavailable"
    assert opened.receipt.telemetry.child_allocation_attempt_count == 4
    assert opened.receipt.telemetry.child_allocation_success_count == 3
    assert opened.receipt.telemetry.child_deallocation_success_count == 3
    assert opened.receipt.telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations
    assert kernel.closed
    assert runtime.stream_destroy_calls == 1


def test_nonready_base_cleanup_owner_is_closed_or_returned_reachable() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=4, free_failure_pointer_once=3
    )
    kernel = FakeRtcKernel(runtime)
    _, _, _, _, _, recovered = _open(runtime=runtime, kernel=kernel)
    assert recovered.context is None
    assert recovered.receipt.status == "unavailable"
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1
    assert kernel.closed

    persistent = FakeHipRuntime(
        malloc_failure_at=4, free_failure_pointer_always=3
    )
    persistent_kernel = FakeRtcKernel(persistent)
    _, _, _, _, _, retained = _open(
        runtime=persistent, kernel=persistent_kernel
    )
    assert retained.context is not None
    assert retained.receipt.status == "cleanup_failed"
    assert retained.receipt.telemetry.current_device_payload_bytes > 0
    assert set(persistent.allocations) == {3}
    persistent.free_failure_pointer_always = None
    retained.context.close()
    assert retained.context.receipt().status == "context_closed"
    assert not persistent.allocations


def test_open_cleanup_failure_retains_pointer_owner_and_retries() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=16 + 4, free_failure_pointer_once=19
    )
    kernel = FakeRtcKernel(runtime)
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert not opened.ready
    assert opened.context is not None
    assert opened.receipt.status == "cleanup_failed"
    assert opened.receipt.telemetry.current_device_payload_bytes > 0
    assert set(runtime.allocations) == {19, *range(1, 17)}
    with pytest.raises(HipRtcCsrContextError):
        opened.context.evaluate_residual_jvp(np.zeros(12))
    opened.context.close()
    assert opened.context.receipt().status == "context_closed"
    assert opened.context.receipt().telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations


def test_close_failure_keeps_unreleased_payload_and_allows_retry() -> None:
    runtime = FakeHipRuntime(free_failure_pointer_once=24)
    _, _, _, _, kernel, opened = _open(runtime=runtime)
    assert opened.context is not None
    with pytest.raises(HipRtcCsrContextError) as error:
        opened.context.close()
    assert error.value.code == "hip_rtc_context_cleanup_failed"
    failed = opened.context.receipt()
    assert failed.status == "cleanup_failed"
    assert failed.telemetry.current_device_payload_bytes > 0
    assert set(runtime.allocations) == {*range(1, 17), 24}
    assert not kernel.closed
    opened.context.close()
    closed = opened.context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations
    assert kernel.closed


def test_foundation_close_failure_keeps_conservative_payload_until_retry() -> None:
    runtime = FakeHipRuntime(free_failure_pointer_once=16)
    _, _, _, _, _, opened = _open(runtime=runtime)
    assert opened.context is not None
    base_payload = opened.context._base_current_bytes_observed
    with pytest.raises(HipRtcCsrContextError) as error:
        opened.context.close()
    assert error.value.code == "hip_rtc_foundation_cleanup_failed"
    failed = opened.context.receipt()
    assert failed.status == "cleanup_failed"
    assert failed.telemetry.current_device_payload_bytes >= base_payload > 0
    assert set(runtime.allocations) == {16}
    opened.context.close()
    closed = opened.context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations


def test_context_and_result_stale_or_rehashed_semantic_tamper_fail() -> None:
    _, plan, _, _, _, opened = _open()
    assert opened.context is not None
    stale = replace(
        opened.receipt, context_receipt_hash="sha256:" + ("0" * 64)
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_csr_context_receipt(stale)
    assert error.value.code == "hip_rtc_context_receipt_hash_mismatch"

    bad_bindings = replace(
        opened.receipt.bindings, state_load_factor_applied=True
    )
    forged = replace(
        opened.receipt,
        bindings=bad_bindings,
        context_receipt_hash="",
    )
    forged = replace(
        forged,
        context_receipt_hash=canonical_hash(
            _context_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError):
        validate_hip_rtc_csr_context_receipt(forged)

    native_claim = replace(
        opened.receipt,
        evidence_scope="native_hiprtc",
        actual_backend="hip",
        claims=replace(
            opened.receipt.claims, native_hiprtc_kernel_loaded=True
        ),
        context_receipt_hash="",
    )
    native_claim = replace(
        native_claim,
        context_receipt_hash=canonical_hash(
            _context_payload(native_claim, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_csr_context_receipt(native_claim)
    assert error.value.code == "hip_rtc_context_native_evidence_invalid"

    bad_view = replace(opened.receipt.child_buffers[0], shape=(1,), byte_length=4)
    bad_views_receipt = replace(
        opened.receipt,
        child_buffers=(bad_view, *opened.receipt.child_buffers[1:]),
        context_receipt_hash="",
    )
    bad_views_receipt = replace(
        bad_views_receipt,
        context_receipt_hash=canonical_hash(
            _context_payload(bad_views_receipt, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_csr_context_receipt(bad_views_receipt)
    assert error.value.code == "hip_rtc_context_child_descriptor_invalid"

    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    stale_result = replace(result.receipt, receipt_hash="sha256:" + ("0" * 64))
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_residual_jvp_receipt(stale_result)
    assert error.value.code == "hip_rtc_result_receipt_hash_mismatch"
    promoted = replace(result.receipt, promotion_eligible=True, receipt_hash="")
    promoted = replace(
        promoted,
        receipt_hash=canonical_hash(_result_payload(promoted, include_hash=False)),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_residual_jvp_receipt(promoted)
    assert error.value.code in {
        "hip_rtc_result_schema_invalid",
        "hip_rtc_result_promotion_invalid",
    }

    native_result = replace(
        result.receipt,
        evidence_scope="native_hiprtc",
        actual_backend="hip",
        receipt_hash="",
    )
    native_result = replace(
        native_result,
        receipt_hash=canonical_hash(
            _result_payload(native_result, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_residual_jvp_receipt(native_result)
    assert error.value.code == "hip_rtc_result_native_evidence_invalid"
    opened.context.close()


def test_evaluation_recomputes_descriptors_and_parity_against_live_context() -> None:
    runtime = FakeHipRuntime()
    kernel = FakeRtcKernel(runtime, output_bias=1.0e-4)
    _, plan, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    bad = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    assert bad.receipt.status == "parity_failed"

    cpu_residual, cpu_jvp = context_module._cpu_csr_oracle(
        opened.context._plan,
        opened.context._state.displacement_si,
        bad.direction,
    )
    good_parity = context_module._parity_report(
        opened.context._plan,
        cpu_residual,
        cpu_jvp,
        cpu_residual,
        cpu_jvp,
        bad.direction,
    )
    borrowed = replace(
        bad.receipt,
        status="verified",
        parity=good_parity,
        claims=replace(
            bad.receipt.claims, cpu_reference_parity_verified=True
        ),
        receipt_hash="",
    )
    borrowed = replace(
        borrowed,
        receipt_hash=canonical_hash(
            _result_payload(borrowed, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_residual_jvp_evaluation(
            replace(bad, receipt=borrowed), expected_context=opened.context
        )
    assert error.value.code == "hip_rtc_evaluation_parity_mismatch"

    wrong_direction = replace(
        bad.receipt.direction, shape=(1,), byte_length=8
    )
    wrong_descriptor = replace(
        bad.receipt, direction=wrong_direction, receipt_hash=""
    )
    wrong_descriptor = replace(
        wrong_descriptor,
        receipt_hash=canonical_hash(
            _result_payload(wrong_descriptor, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcCsrContextError) as error:
        validate_hip_rtc_residual_jvp_receipt(wrong_descriptor)
    assert error.value.code == "hip_rtc_result_descriptor_invalid"
    opened.context.close()


def test_both_receipts_match_strict_schemas_and_reject_extra_keys() -> None:
    _, plan, _, _, _, opened = _open()
    assert opened.context is not None
    result = opened.context.evaluate_residual_jvp(np.ones(plan.dof_count))
    payloads = {
        "rtc_csr_context_receipt_v1.schema.json": opened.receipt.to_dict(),
        "rtc_residual_jvp_receipt_v1.schema.json": result.receipt.to_dict(),
    }
    for name, payload in payloads.items():
        schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        assert not list(validator.iter_errors(payload))
        payload["device_pointer"] = "0x1234"
        assert list(validator.iter_errors(payload))
    opened.context.close()
