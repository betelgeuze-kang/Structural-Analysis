from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip.context import (  # noqa: E402
    HipContextError,
    open_device_execution_context,
)
from structural_analysis.engine_v2.backends.hip.kernel_artifact import (  # noqa: E402
    LoadedHipCsrKernel,
)
from structural_analysis.engine_v2.backends.hip.operator_context import (  # noqa: E402
    HipOperatorContextError,
    _execution_evidence_kind,
    open_hip_operator_execution_context,
    validate_hip_operator_context_receipt,
    validate_hip_residual_jvp_parity_receipt,
    validate_hip_residual_jvp_result,
    validate_hip_residual_jvp_result_receipt,
    verify_hip_residual_jvp_parity,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    compile_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
    open_trial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA_ROOT = REPO_ROOT / "src/structural_analysis/schemas"


class FakeHipRuntime:
    library_name = "fake-libamdhip64"

    def __init__(
        self,
        *,
        malloc_failure_at: int | None = None,
        free_failure_pointer_once: int | None = None,
    ) -> None:
        self.malloc_failure_at = malloc_failure_at
        self.free_failure_pointer_once = free_failure_pointer_once
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
            raise HipContextError("hip_allocation_failed", "injected allocation failure")
        pointer = self._next_pointer
        self._next_pointer += 1
        self.allocations[pointer] = bytearray(byte_length)
        return pointer

    def copy_h2d_async(self, pointer: int, array: np.ndarray, stream: object) -> None:
        del stream
        self.h2d_calls += 1
        self.allocations[pointer][:] = memoryview(array).cast("B")

    def copy_d2h_async(self, array: np.ndarray, pointer: int, stream: object) -> None:
        del stream
        self.d2h_calls += 1
        memoryview(array).cast("B")[:] = self.allocations[pointer]

    def synchronize(self, stream: object) -> None:
        del stream
        self.sync_calls += 1

    def free(self, pointer: int) -> None:
        self.free_calls += 1
        if self.free_failure_pointer_once == pointer:
            self.free_failure_pointer_once = None
            raise HipContextError("hip_device_access_failed", "injected free failure")
        del self.allocations[pointer]

    def destroy_stream(self, stream: object) -> None:
        del stream
        self.stream_destroy_calls += 1


class FakeFusedKernel:
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
        artifact_hash = "sha256:" + ("1" * 64)
        self.artifact_receipt = {
            "schema_version": "structural-analysis-hip-csr-kernel-artifact.v1",
            "artifact_hash": artifact_hash,
            "source_hash": "sha256:" + ("2" * 64),
            "library_hash": artifact_hash,
            "abi_hash": "sha256:" + ("3" * 64),
            "build_target_hash": "sha256:" + ("4" * 64),
            "entrypoint": "engine_v2_hip_csr_launch",
            "abi_version": 1,
            "block_size": 256,
            "targets": ["gfx1030"],
            "flags": ["-O3", "-fno-fast-math", "-ffp-contract=off"],
        }

    def launch_residual_jvp(self, **request: object) -> None:
        self.launch_calls += 1
        if self.fail_launch:
            raise RuntimeError("injected kernel failure")
        row_count = int(request["row_count"])
        nnz_count = int(request["nnz_count"])

        def array(name: str, dtype: str, count: int) -> np.ndarray:
            pointer = int(request[name])
            return np.frombuffer(
                self.runtime.allocations[pointer], dtype=dtype, count=count
            )

        row_ptr = array("row_ptr", "<i4", row_count + 1)
        columns = array("column_indices", "<i4", nnz_count)
        values = array("values", "<f8", nnz_count)
        load = array("load", "<f8", row_count)
        state = array("state", "<f8", row_count)
        direction = array("direction", "<f8", row_count)
        residual = array("residual_out", "<f8", row_count)
        jvp = array("jvp_out", "<f8", row_count)
        for row in range(row_count):
            start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
            indices = columns[start:stop]
            row_values = values[start:stop]
            residual[row] = np.dot(row_values, state[indices]) - load[row]
            jvp[row] = np.dot(row_values, direction[indices])
        if self.output_bias:
            residual[0] += self.output_bias
            jvp[0] += self.output_bias


def _buffers(load_pattern_id: str = "LC_AXIAL"):
    return pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )


def _contracts(load_pattern_id: str = "LC_AXIAL"):
    buffers = _buffers(load_pattern_id)
    plan = compile_execution_plan(buffers)
    return buffers, plan, create_initial_state(plan)


def _open(*, runtime: FakeHipRuntime | None = None, kernel: FakeFusedKernel | None = None):
    buffers, plan, state = _contracts()
    runtime = runtime or FakeHipRuntime()
    kernel = kernel or FakeFusedKernel(runtime)
    opened = open_hip_operator_execution_context(
        buffers, plan, state, kernel=kernel, runtime=runtime
    )
    return buffers, plan, state, runtime, kernel, opened


def test_operator_context_persistently_binds_csr_state_and_strict_test_double_receipt() -> None:
    buffers, plan, state, runtime, kernel, opened = _open()
    assert opened.ready, opened.receipt.reason
    assert opened.context is not None
    receipt = opened.receipt
    assert receipt.execution_evidence_kind == "test_double"
    assert receipt.actual_backend == "test_double"
    assert receipt.kernel_artifact.artifact_kind == "test_double"
    assert tuple(view.name for view in receipt.device_views) == (
        "csr_row_ptr",
        "csr_col_ind",
        "csr_values",
        "load_vector",
        "committed_displacement",
        "direction",
        "residual_output",
        "jvp_output",
    )
    assert receipt.telemetry.allocation_attempt_count == 8
    assert receipt.telemetry.allocation_success_count == 8
    assert receipt.telemetry.h2d_operation_attempt_count == 5
    assert receipt.telemetry.h2d_operation_success_count == 5
    assert receipt.telemetry.kernel_launch_success_count == 0
    assert receipt.telemetry.fallback_count == 0
    assert runtime.malloc_calls == 16 + 8
    assert runtime.h2d_calls == 16 + 5
    assert runtime.sync_calls == 2
    assert receipt.claims.canonical_csr_operator_bound
    assert receipt.claims.committed_state_bound
    assert receipt.claims.residual_jvp_ready
    assert not receipt.claims.native_hip_kernel_execution_proven
    assert not receipt.claims.solver_ready
    validate_hip_operator_context_receipt(
        receipt,
        expected_buffers=buffers,
        expected_plan=plan,
        expected_state=state,
        expected_kernel=kernel,
    )
    serialized = json.dumps(receipt.to_dict())
    for forbidden in ("pointer", "address", "stream", "handle", "0x"):
        assert forbidden not in serialized.lower()
    opened.context.close()


def test_fused_evaluation_has_exact_transfer_delta_immutable_outputs_and_narrow_parity() -> None:
    _, plan, state, runtime, kernel, opened = _open()
    assert opened.context is not None
    direction = np.arange(plan.dof_count, dtype="<f8")
    result = opened.context.evaluate_for_verification(direction)

    assert kernel.launch_calls == 1
    assert runtime.h2d_calls == 16 + 5 + 1
    assert runtime.d2h_calls == 2
    assert runtime.sync_calls == 3
    delta = result.receipt.transfer_delta
    assert delta.h2d_operation_attempt_count == delta.h2d_operation_success_count == 1
    assert delta.d2h_operation_attempt_count == delta.d2h_operation_success_count == 2
    assert delta.kernel_launch_attempt_count == delta.kernel_launch_success_count == 1
    assert delta.explicit_sync_attempt_count == delta.explicit_sync_success_count == 1
    assert result.receipt.complexity.complexity_class == "O(nnz)"
    assert result.receipt.complexity.csr_entry_visits == plan.array(
        "global_stiffness_csr_values"
    ).size
    assert not result.receipt.native_hip_kernel_execution_proven
    for array in (result.direction, result.residual, result.jvp):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    validate_hip_residual_jvp_result(result, expected_plan=plan, expected_state=state)
    parity = verify_hip_residual_jvp_parity(
        result, plan=plan, committed_state=state
    )
    assert parity.status == "pass"
    manifest = parity.to_dict()
    assert manifest["claims"]["narrow_case_result_cpu_parity_proven"]
    assert not manifest["claims"]["native_hip_narrow_case_parity_proven"]
    assert not manifest["claims"]["cpu_hip_global_parity_proven"]
    opened.context.close()


def test_all_three_manifests_validate_against_strict_schemas() -> None:
    _, plan, state, _, _, opened = _open()
    assert opened.context is not None
    result = opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    parity = verify_hip_residual_jvp_parity(result, plan=plan, committed_state=state)
    payloads = {
        "hip_operator_context_v1.schema.json": opened.context.receipt().to_dict(),
        "hip_residual_jvp_result_v1.schema.json": result.to_dict(),
        "hip_residual_jvp_parity_v1.schema.json": parity.to_dict(),
    }
    for name, payload in payloads.items():
        schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert not list(Draft202012Validator(schema).iter_errors(payload))
        payload["device_pointer"] = "0x1234"
        assert list(Draft202012Validator(schema).iter_errors(payload))
    opened.context.close()


def test_cross_plan_and_trial_state_are_rejected_before_runtime_probe() -> None:
    buffers, plan, state = _contracts("LC_AXIAL")
    other_buffers, other_plan, _ = _contracts("LC_WEAK")
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime)
    with pytest.raises(HipOperatorContextError) as error:
        open_hip_operator_execution_context(
            buffers, other_plan, state, kernel=kernel, runtime=runtime
        )
    assert error.value.code == "hip_operator_binding_invalid"
    assert runtime.init_calls == 0

    trial = open_trial_state(
        state, np.zeros(plan.dof_count), expected_plan=plan
    )
    with pytest.raises(HipOperatorContextError) as error:
        open_hip_operator_execution_context(
            buffers, plan, trial, kernel=kernel, runtime=runtime
        )
    assert error.value.code == "hip_operator_state_role_invalid"
    assert runtime.init_calls == 0
    assert other_buffers.artifact_hash != buffers.artifact_hash


def test_committed_state_hash_tamper_is_rejected_before_runtime_probe() -> None:
    buffers, plan, state = _contracts()
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime)
    stale = replace(state, state_hash="sha256:" + ("0" * 64))
    with pytest.raises(HipOperatorContextError) as error:
        open_hip_operator_execution_context(
            buffers, plan, stale, kernel=kernel, runtime=runtime
        )
    assert error.value.code == "hip_operator_binding_invalid"
    assert runtime.init_calls == 0
    assert runtime.malloc_calls == 0


def test_kernel_receipt_tamper_is_detected_before_any_evaluation_transfer() -> None:
    _, plan, _, runtime, kernel, opened = _open()
    assert opened.context is not None
    initial_h2d = runtime.h2d_calls
    kernel.artifact_receipt["source_hash"] = "sha256:" + ("9" * 64)
    with pytest.raises(HipOperatorContextError) as error:
        opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    assert error.value.code == "hip_operator_kernel_binding_mismatch"
    assert runtime.h2d_calls == initial_h2d
    assert kernel.launch_calls == 0
    opened.context.close()


def test_operator_partial_allocation_failure_cleans_operator_and_foundation() -> None:
    runtime = FakeHipRuntime(malloc_failure_at=16 + 4)
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=FakeFusedKernel(runtime))
    assert not opened.ready
    assert opened.context is None
    assert opened.receipt.status == "unavailable"
    assert opened.receipt.reason is not None
    assert opened.receipt.reason.code == "hip_allocation_failed"
    assert opened.receipt.telemetry.allocation_attempt_count == 4
    assert opened.receipt.telemetry.allocation_success_count == 3
    assert opened.receipt.telemetry.deallocation_success_count == 3
    assert opened.receipt.telemetry.current_device_payload_bytes == 0
    assert runtime.free_calls == 16 + 3
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1


def test_foundation_failed_open_cleanup_owner_is_propagated_without_handles() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=4,
        free_failure_pointer_once=3,
    )
    _, _, _, _, _, opened = _open(
        runtime=runtime,
        kernel=FakeFusedKernel(runtime),
    )

    assert not opened.ready
    assert opened.context is None
    assert opened.cleanup_owner is not None
    assert opened.receipt.status == "unavailable"
    assert opened.receipt.actual_backend is None
    assert opened.receipt.telemetry.current_device_payload_bytes == 0
    assert set(runtime.allocations) == {3}
    foundation_receipt = opened.cleanup_owner.receipt()
    assert foundation_receipt.status == "unavailable"
    assert foundation_receipt.telemetry.current_device_payload_bytes > 0
    assert "pointer" not in json.dumps(opened.receipt.to_dict()).lower()

    opened.cleanup_owner.close()
    assert opened.cleanup_owner.closed
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1
    assert (
        opened.cleanup_owner.receipt().telemetry.current_device_payload_bytes
        == 0
    )


def test_open_cleanup_failure_retains_pointer_owner_and_close_can_retry() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=16 + 4,
        free_failure_pointer_once=19,
    )
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=FakeFusedKernel(runtime))
    assert not opened.ready
    assert opened.context is not None
    assert opened.receipt.status == "cleanup_failed"
    assert opened.receipt.telemetry.current_device_payload_bytes > 0
    assert set(runtime.allocations) == {19}
    with pytest.raises(HipOperatorContextError) as error:
        opened.context.evaluate_for_verification(np.zeros(12))
    assert error.value.code == "hip_operator_cleanup_failed"

    opened.context.close()
    assert opened.context.receipt().status == "context_closed"
    assert opened.context.receipt().telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations


def test_kernel_failure_poisoning_never_returns_a_cpu_fallback_result() -> None:
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime, fail_launch=True)
    _, plan, _, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    with pytest.raises(HipOperatorContextError):
        opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    assert opened.context.poisoned
    poisoned = opened.context.receipt()
    assert poisoned.status == "poisoned"
    assert poisoned.telemetry.kernel_launch_attempt_count == 1
    assert poisoned.telemetry.kernel_launch_success_count == 0
    assert poisoned.telemetry.fallback_count == 0
    assert not poisoned.claims.residual_jvp_ready
    with pytest.raises(HipOperatorContextError) as error:
        opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    assert error.value.code == "hip_operator_context_poisoned"
    opened.context.close()


def test_cleanup_failure_preserves_unreleased_bytes_and_can_be_retried() -> None:
    runtime = FakeHipRuntime(free_failure_pointer_once=24)
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=FakeFusedKernel(runtime))
    assert opened.context is not None
    with pytest.raises(HipOperatorContextError) as error:
        opened.context.close()
    assert error.value.code == "hip_operator_cleanup_failed"
    failed = opened.context.receipt()
    assert failed.status == "cleanup_failed"
    assert failed.telemetry.current_device_payload_bytes > 0
    assert failed.telemetry.deallocation_attempt_count == 8
    assert failed.telemetry.deallocation_success_count == 7
    assert len(runtime.allocations) == 1

    opened.context.close()
    closed = opened.context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.current_device_payload_bytes == 0
    assert not runtime.allocations


def test_foundation_close_failure_remains_reachable_through_operator_retry() -> None:
    runtime = FakeHipRuntime(free_failure_pointer_once=16)
    _, _, _, _, _, opened = _open(runtime=runtime, kernel=FakeFusedKernel(runtime))
    assert opened.context is not None
    with pytest.raises(HipOperatorContextError) as error:
        opened.context.close()
    assert error.value.code == "hip_operator_cleanup_failed"
    assert opened.context.receipt().status == "cleanup_failed"
    assert not opened.context._base.closed
    assert set(opened.context._base._pointers.values()) == {16}
    assert set(runtime.allocations) == {16}
    assert runtime.stream_destroy_calls == 0

    opened.context.close()
    assert opened.context.receipt().status == "context_closed"
    assert opened.context._base.closed
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1


def test_total_memory_budget_blocks_before_foundation_allocation() -> None:
    buffers, plan, state = _contracts()
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime)
    foundation_bytes = sum(row.byte_length for row in buffers.descriptors)
    operator_bytes = (
        plan.array("csr_row_ptr").nbytes
        + plan.array("csr_column_indices").nbytes
        + plan.array("global_stiffness_csr_values").nbytes
        + plan.array("global_load").nbytes
        + state.displacement_si.nbytes
        + 3 * state.dof_count * np.dtype("<f8").itemsize
    )
    opened = open_hip_operator_execution_context(
        buffers,
        plan,
        state,
        kernel=kernel,
        runtime=runtime,
        memory_budget_bytes=foundation_bytes + operator_bytes - 1,
    )
    assert not opened.ready
    assert opened.receipt.reason is not None
    assert opened.receipt.reason.code == "foundation_context_not_ready"
    assert runtime.malloc_calls == 0
    assert not runtime.allocations


def test_biased_test_double_yields_fail_receipt_without_global_parity_claim() -> None:
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime, output_bias=1.0e-4)
    _, plan, state, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    result = opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    parity = verify_hip_residual_jvp_parity(
        result,
        plan=plan,
        committed_state=state,
        residual_absolute_tolerance=1.0e-8,
        residual_relative_tolerance=1.0e-8,
        jvp_absolute_tolerance=1.0e-8,
        jvp_relative_tolerance=1.0e-8,
    )
    assert parity.status == "fail"
    assert not parity.residual.passed
    assert not parity.jvp.passed
    claims = parity.to_dict()["claims"]
    assert not claims["narrow_case_result_cpu_parity_proven"]
    assert not claims["native_hip_narrow_case_parity_proven"]
    assert not claims["cpu_hip_global_parity_proven"]
    opened.context.close()


def test_v1_foundation_receipt_still_rejects_every_kernel_and_solver_claim() -> None:
    buffers = _buffers()
    runtime = FakeHipRuntime()
    opened = open_device_execution_context(buffers, runtime=runtime)
    assert opened.context is not None
    assert opened.receipt.telemetry.kernel_launch_count == 0
    assert not opened.receipt.claims.operator_bound
    assert not opened.receipt.claims.state_bound
    assert not opened.receipt.claims.residual_jvp_ready
    assert not opened.receipt.claims.solver_ready
    opened.context.close()


def test_context_receipt_and_result_hash_tamper_fail_closed() -> None:
    _, plan, _, _, _, opened = _open()
    assert opened.context is not None
    forged_context = replace(
        opened.receipt, context_receipt_hash="sha256:" + ("0" * 64)
    )
    with pytest.raises(HipOperatorContextError) as error:
        validate_hip_operator_context_receipt(forged_context)
    assert error.value.code == "hip_operator_context_hash_mismatch"

    result = opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    forged_result = replace(
        result,
        receipt=replace(
            result.receipt, result_hash="sha256:" + ("0" * 64)
        ),
    )
    with pytest.raises(HipOperatorContextError) as error:
        validate_hip_residual_jvp_result(forged_result)
    assert error.value.code == "hip_residual_jvp_result_hash_mismatch"
    opened.context.close()


def test_every_context_attempted_byte_and_device_memory_field_is_hash_bound() -> None:
    _, _, _, _, _, opened = _open()
    assert opened.context is not None
    receipt = opened.receipt
    assert receipt.device is not None
    mutations = (
        replace(
            receipt,
            telemetry=replace(
                receipt.telemetry,
                h2d_bytes_attempted=receipt.telemetry.h2d_bytes_attempted + 8,
            ),
        ),
        replace(
            receipt,
            telemetry=replace(
                receipt.telemetry,
                d2h_bytes_attempted=receipt.telemetry.d2h_bytes_attempted + 8,
            ),
        ),
        replace(
            receipt,
            device=replace(
                receipt.device,
                total_memory_bytes=receipt.device.total_memory_bytes + 1,
            ),
        ),
        replace(
            receipt,
            device=replace(
                receipt.device,
                free_memory_bytes_after_upload=(
                    receipt.device.free_memory_bytes_after_upload - 1
                ),
            ),
        ),
    )
    for stale in mutations:
        with pytest.raises(HipOperatorContextError) as error:
            validate_hip_operator_context_receipt(stale)
        assert error.value.code == "hip_operator_context_hash_mismatch"
    opened.context.close()


def test_every_result_binding_complexity_and_attempted_byte_field_is_hash_bound() -> None:
    _, plan, _, _, _, opened = _open()
    assert opened.context is not None
    result = opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    receipt = result.receipt
    stale_receipts = (
        replace(
            receipt,
            execution_plan=replace(
                receipt.execution_plan,
                free_dof_count=receipt.execution_plan.free_dof_count + 1,
            ),
        ),
        replace(
            receipt,
            committed_state=replace(
                receipt.committed_state,
                epoch=receipt.committed_state.epoch + 1,
            ),
        ),
        replace(
            receipt,
            kernel_artifact=replace(
                receipt.kernel_artifact,
                source_hash="sha256:" + ("8" * 64),
            ),
        ),
        replace(
            receipt,
            direction=replace(
                receipt.direction,
                byte_length=receipt.direction.byte_length + 8,
            ),
        ),
        replace(
            receipt,
            complexity=replace(
                receipt.complexity,
                multiply_count=receipt.complexity.multiply_count + 1,
            ),
        ),
        replace(
            receipt,
            complexity=replace(
                receipt.complexity,
                load_subtraction_count=(
                    receipt.complexity.load_subtraction_count + 1
                ),
            ),
        ),
        replace(
            receipt,
            transfer_delta=replace(
                receipt.transfer_delta,
                h2d_bytes_attempted=(
                    receipt.transfer_delta.h2d_bytes_attempted + 8
                ),
            ),
        ),
    )
    for stale in stale_receipts:
        with pytest.raises(HipOperatorContextError):
            validate_hip_residual_jvp_result_receipt(stale)
    opened.context.close()


def test_parity_fallback_is_hash_bound_and_derived_scope_is_not_mutable_state() -> None:
    _, plan, state, _, _, opened = _open()
    assert opened.context is not None
    result = opened.context.evaluate_for_verification(np.ones(plan.dof_count))
    parity = verify_hip_residual_jvp_parity(
        result, plan=plan, committed_state=state
    )
    assert "case_scope" not in parity.__dataclass_fields__
    assert "cpu_oracle" not in parity.__dataclass_fields__
    stale = replace(parity, fallback_used=True)
    with pytest.raises(HipOperatorContextError):
        validate_hip_residual_jvp_parity_receipt(stale)
    opened.context.close()


def test_parity_relative_error_is_componentwise_with_declared_floor() -> None:
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime, output_bias=1.0e-12)
    _, plan, state, _, _, opened = _open(runtime=runtime, kernel=kernel)
    assert opened.context is not None
    result = opened.context.evaluate_for_verification(np.zeros(plan.dof_count))
    parity = verify_hip_residual_jvp_parity(
        result,
        plan=plan,
        committed_state=state,
        residual_absolute_tolerance=1.0,
        residual_relative_tolerance=1.0,
        jvp_absolute_tolerance=1.0,
        jvp_relative_tolerance=1.0,
    )
    # The biased JVP component is compared against an exact zero CPU value;
    # componentwise relative error therefore uses the declared 1e-300 floor.
    assert parity.jvp.max_relative_error == pytest.approx(1.0e288)
    assert not parity.jvp.passed
    manifest = parity.to_dict()
    assert manifest["tolerances"]["relative_error_denominator_floor"] == 1.0e-300
    opened.context.close()


def test_test_double_cannot_self_assert_native_execution_evidence() -> None:
    _, _, _, _, _, opened = _open()
    assert opened.context is not None
    assert opened.receipt.execution_evidence_kind == "test_double"
    manifest = opened.receipt.to_dict()
    manifest["execution_evidence_kind"] = "native_hip"
    manifest["actual_backend"] = "hip_native"
    manifest["kernel_artifact"]["artifact_kind"] = "native_hip"
    unhashed = dict(manifest)
    del unhashed["context_receipt_hash"]
    manifest["context_receipt_hash"] = canonical_hash(unhashed)
    schema = json.loads(
        (SCHEMA_ROOT / "hip_operator_context_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    # JSON shape alone cannot authenticate process-local execution.  The
    # public builder is the trust boundary and derived test_double above;
    # no API accepts this plain dictionary as a receipt object.
    assert Draft202012Validator(schema).is_valid(manifest)
    with pytest.raises(HipOperatorContextError) as error:
        validate_hip_operator_context_receipt(manifest)  # type: ignore[arg-type]
    assert error.value.code == "hip_operator_receipt_type_invalid"
    opened.context.close()


def test_public_engine_v2_package_reexports_operator_replay_contract() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.backends.hip as hip

    names = (
        "open_hip_operator_execution_context",
        "validate_hip_operator_context_receipt",
        "validate_hip_residual_jvp_result",
        "validate_hip_residual_jvp_result_receipt",
        "validate_hip_residual_jvp_parity_receipt",
        "verify_hip_residual_jvp_parity",
    )
    for name in names:
        assert getattr(engine_v2, name) is getattr(hip, name)


def test_native_class_name_spoof_cannot_create_native_execution_evidence() -> None:
    runtime = FakeHipRuntime()
    spoof = FakeFusedKernel(runtime)
    spoof.__class__.__module__ = (
        "structural_analysis.engine_v2.backends.hip.kernel_artifact"
    )
    spoof.__class__.__name__ = "LoadedHipCsrKernel"
    try:
        assert _execution_evidence_kind(spoof, None) == "test_double"
    finally:
        spoof.__class__.__module__ = __name__
        spoof.__class__.__name__ = "FakeFusedKernel"


def test_loaded_kernel_subclass_cannot_create_native_execution_evidence() -> None:
    class LaunchOverride(LoadedHipCsrKernel):
        def launch_residual_jvp(self, **request: object) -> None:
            del request

    spoof = object.__new__(LaunchOverride)
    assert _execution_evidence_kind(spoof, None) == "test_double"


def test_stale_explicit_kernel_receipt_hash_is_rejected_before_probe() -> None:
    buffers, plan, state = _contracts()
    runtime = FakeHipRuntime()
    kernel = FakeFusedKernel(runtime)
    kernel.artifact_receipt["receipt_hash"] = "sha256:" + ("0" * 64)
    with pytest.raises(HipOperatorContextError) as error:
        open_hip_operator_execution_context(
            buffers, plan, state, kernel=kernel, runtime=runtime
        )
    assert error.value.code == "hip_kernel_artifact_receipt_hash_mismatch"
    assert runtime.init_calls == 0
