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
    validate_hip_context_receipt,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    SolverModelBufferError,
    pack_solver_model_buffers,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/hip_context_receipt_v1.schema.json"


class FakeHipRuntime:
    library_name = "fake-libamdhip64"

    def __init__(
        self,
        *,
        malloc_failure_at: int | None = None,
        free_failure_pointer_once: int | None = None,
        free_failure_pointer: int | None = None,
        stream_destroy_failures_remaining: int = 0,
    ) -> None:
        self.malloc_failure_at = malloc_failure_at
        self.free_failure_pointer_once = free_failure_pointer_once
        self.free_failure_pointer = free_failure_pointer
        self.stream_destroy_failures_remaining = stream_destroy_failures_remaining
        self.init_calls = 0
        self.set_device_calls: list[int] = []
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
        return 0, "Fake AMD GPU"

    def hip_runtime_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_driver_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_error_string(self, status: int) -> str:
        return f"fake HIP status {status}"

    def set_device(self, ordinal: int) -> None:
        self.set_device_calls.append(ordinal)

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
        if self.free_failure_pointer == pointer:
            raise HipContextError(
                "hip_device_access_failed", "injected persistent free failure"
            )
        if self.free_failure_pointer_once == pointer:
            self.free_failure_pointer_once = None
            raise HipContextError(
                "hip_device_access_failed", "injected free failure"
            )
        del self.allocations[pointer]

    def destroy_stream(self, stream: object) -> None:
        del stream
        self.stream_destroy_calls += 1
        if self.stream_destroy_failures_remaining:
            self.stream_destroy_failures_remaining -= 1
            raise HipContextError(
                "hip_device_access_failed", "injected stream destroy failure"
            )


def _buffers():
    return pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )


def test_context_uploads_all_buffers_once_and_emits_strict_receipt() -> None:
    buffers = _buffers()
    runtime = FakeHipRuntime()
    result = open_device_execution_context(buffers, runtime=runtime)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert result.ready
    assert result.context is not None
    assert result.receipt.status == "context_ready"
    assert not list(Draft202012Validator(schema).iter_errors(result.receipt.to_dict()))
    assert len(result.receipt.buffer_views) == len(buffers.descriptors) == 16
    assert tuple(view.name for view in result.receipt.buffer_views) == tuple(
        row.name for row in buffers.descriptors
    )
    expected_bytes = sum(row.byte_length for row in buffers.descriptors)
    telemetry = result.receipt.telemetry
    assert telemetry.h2d_bytes == expected_bytes
    assert telemetry.d2h_bytes == 0
    assert telemetry.h2d_operation_count == 16
    assert telemetry.d2h_operation_count == 0
    assert telemetry.allocation_count == 16
    assert telemetry.current_device_payload_bytes == expected_bytes
    assert telemetry.peak_device_payload_bytes == expected_bytes
    assert telemetry.explicit_sync_count == 1
    assert telemetry.kernel_launch_count == 0
    assert telemetry.fallback_count == 0
    assert runtime.malloc_calls == runtime.h2d_calls == 16
    assert result.receipt.claims.model_buffers_device_resident
    assert not result.receipt.claims.operator_bound
    assert not result.receipt.claims.solver_ready
    validate_hip_context_receipt(result.receipt, expected_buffers=buffers)
    assert "0x" not in json.dumps(result.receipt.to_dict())

    result.context.close()


def test_explicit_verification_download_is_counted_and_close_invalidates_context() -> None:
    buffers = _buffers()
    runtime = FakeHipRuntime()
    result = open_device_execution_context(buffers, runtime=runtime)
    assert result.context is not None
    context = result.context

    downloaded = context.export_for_verification("load_vector_si")
    np.testing.assert_array_equal(downloaded, buffers.array("load_vector_si"))
    ready_after_export = context.receipt()
    assert ready_after_export.telemetry.d2h_bytes == downloaded.nbytes
    assert ready_after_export.telemetry.d2h_operation_count == 1
    assert ready_after_export.telemetry.explicit_sync_count == 2
    assert runtime.d2h_calls == 1

    context.close()
    closed = context.receipt()
    assert closed.status == "context_closed"
    assert not closed.claims.model_buffers_device_resident
    assert closed.telemetry.current_device_payload_bytes == 0
    assert closed.telemetry.deallocation_count == 16
    assert runtime.free_calls == 16
    assert runtime.stream_destroy_calls == 1
    assert not runtime.allocations
    validate_hip_context_receipt(closed, expected_buffers=buffers)
    with pytest.raises(HipContextError) as error:
        context.buffer("load_vector_si")
    assert error.value.code == "hip_context_closed"


def test_missing_runtime_returns_unavailable_without_cpu_fallback(tmp_path: Path) -> None:
    missing = tmp_path / "libamdhip64-missing.so"
    result = open_device_execution_context(_buffers(), runtime_library=missing)

    assert not result.ready
    assert result.context is None
    assert result.capability_receipt.status == "unavailable"
    assert result.receipt.status == "unavailable"
    assert result.receipt.actual_backend is None
    assert result.receipt.reason is not None
    assert result.receipt.reason.code == "hip_native_library_missing"
    assert result.receipt.telemetry.h2d_bytes == 0
    assert result.receipt.telemetry.fallback_count == 0
    assert not result.receipt.claims.model_buffers_device_resident
    assert not result.receipt.claims.solver_ready


def test_memory_budget_blocks_before_allocation() -> None:
    runtime = FakeHipRuntime()
    result = open_device_execution_context(
        _buffers(), runtime=runtime, memory_budget_bytes=1
    )

    assert not result.ready
    assert result.receipt.reason is not None
    assert result.receipt.reason.code == "hip_memory_budget_exceeded"
    assert runtime.malloc_calls == 0
    assert runtime.h2d_calls == 0
    assert not runtime.allocations


def test_buffer_tamper_is_rejected_before_native_probe() -> None:
    runtime = FakeHipRuntime()
    forged = replace(_buffers(), artifact_hash="sha256:" + ("0" * 64))

    with pytest.raises(SolverModelBufferError) as error:
        open_device_execution_context(forged, runtime=runtime)
    assert error.value.code == "solver_buffer_artifact_hash_mismatch"
    assert runtime.init_calls == 0
    assert runtime.malloc_calls == 0


def test_partial_allocation_failure_frees_every_successful_allocation() -> None:
    runtime = FakeHipRuntime(malloc_failure_at=4)
    result = open_device_execution_context(_buffers(), runtime=runtime)

    assert not result.ready
    assert result.context is None
    assert result.receipt.reason is not None
    assert result.receipt.reason.code == "hip_allocation_failed"
    assert runtime.malloc_calls == 4
    assert runtime.free_calls == 3
    assert not runtime.allocations
    assert result.receipt.telemetry.allocation_count == 3
    assert result.receipt.telemetry.deallocation_count == 3
    assert result.receipt.telemetry.current_device_payload_bytes == 0
    assert result.receipt.telemetry.h2d_operation_count == 3


def test_failed_open_cleanup_retains_pointer_owner_and_retries_exactly() -> None:
    buffers = _buffers()
    runtime = FakeHipRuntime(
        malloc_failure_at=4,
        free_failure_pointer_once=3,
    )
    result = open_device_execution_context(buffers, runtime=runtime)

    assert not result.ready
    assert result.context is not None
    owner = result.context
    assert result.receipt.status == "unavailable"
    assert result.receipt.reason is not None
    assert "cleanup incomplete" in result.receipt.reason.detail
    assert result.receipt.telemetry.current_device_payload_bytes > 0
    assert set(runtime.allocations) == {3}
    assert runtime.stream_destroy_calls == 0
    with pytest.raises(HipContextError) as error:
        owner.buffer("load_vector_si")
    assert error.value.code == "hip_context_cleanup_only"

    owner.close()
    assert owner.closed
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1
    cleaned = owner.receipt()
    assert cleaned.status == "unavailable"
    assert cleaned.telemetry.current_device_payload_bytes == 0
    assert cleaned.telemetry.deallocation_count == 3
    validate_hip_context_receipt(cleaned, expected_buffers=buffers)


def test_failed_open_persistent_free_remains_owned_until_later_retry() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=4,
        free_failure_pointer=3,
    )
    result = open_device_execution_context(_buffers(), runtime=runtime)
    assert result.context is not None
    owner = result.context

    with pytest.raises(HipContextError):
        owner.close()
    assert not owner.closed
    assert set(runtime.allocations) == {3}
    assert owner.receipt().telemetry.current_device_payload_bytes > 0
    assert runtime.stream_destroy_calls == 0

    runtime.free_failure_pointer = None
    owner.close()
    assert owner.closed
    assert not runtime.allocations
    assert owner.receipt().telemetry.current_device_payload_bytes == 0


def test_failed_open_stream_destroy_remains_owned_until_retry() -> None:
    runtime = FakeHipRuntime(
        malloc_failure_at=4,
        stream_destroy_failures_remaining=1,
    )
    result = open_device_execution_context(_buffers(), runtime=runtime)
    assert result.context is not None
    owner = result.context
    assert not runtime.allocations
    assert result.receipt.telemetry.current_device_payload_bytes == 0
    assert runtime.stream_destroy_calls == 1
    before_hash = result.receipt.context_receipt_hash

    owner.close()
    assert owner.closed
    assert runtime.stream_destroy_calls == 2
    cleaned = owner.receipt()
    assert cleaned.status == "unavailable"
    assert "cleanup recovered" in cleaned.reason.detail
    assert cleaned.context_receipt_hash != before_hash


def test_close_failure_retains_foundation_pointer_and_stream_until_retry() -> None:
    buffers = _buffers()
    runtime = FakeHipRuntime(free_failure_pointer_once=16)
    result = open_device_execution_context(buffers, runtime=runtime)
    assert result.context is not None
    context = result.context

    with pytest.raises(HipContextError) as error:
        context.close()
    assert error.value.code == "hip_device_access_failed"
    assert not context.closed
    assert runtime.stream_destroy_calls == 0
    assert set(runtime.allocations) == {16}
    assert set(context._pointers.values()) == {16}
    assert context._telemetry.current_device_payload_bytes == len(
        runtime.allocations[16]
    )
    assert context._telemetry.deallocation_count == 15
    with pytest.raises(HipContextError) as error:
        context.receipt()
    assert error.value.code == "hip_context_close_failed"
    with pytest.raises(HipContextError) as error:
        context.buffer("load_vector_si")
    assert error.value.code == "hip_context_close_failed"

    context.close()
    assert context.closed
    assert not runtime.allocations
    assert runtime.stream_destroy_calls == 1
    closed = context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.deallocation_count == 16
    assert closed.telemetry.current_device_payload_bytes == 0


def test_context_receipt_tampering_and_unknown_runtime_handle_fail_closed() -> None:
    result = open_device_execution_context(_buffers(), runtime=FakeHipRuntime())
    assert result.context is not None
    forged = replace(
        result.receipt, context_receipt_hash="sha256:" + ("0" * 64)
    )
    with pytest.raises(HipContextError) as error:
        validate_hip_context_receipt(forged)
    assert error.value.code == "hip_context_receipt_hash_mismatch"

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with_handle = result.receipt.to_dict()
    with_handle["device_pointer"] = "0x1234"
    assert not Draft202012Validator(schema).is_valid(with_handle)
    result.context.close()


def test_local_hardware_probe_and_context_are_ready_or_explicitly_unavailable() -> None:
    capability = probe_hip_capability()
    result = open_device_execution_context(_buffers())

    if capability.status == "ready":
        assert result.ready
        assert result.context is not None
        assert result.receipt.device is not None
        assert result.receipt.device.name == capability.device.name
        assert result.receipt.telemetry.h2d_bytes > 0
        assert result.receipt.telemetry.d2h_bytes == 0
        result.context.close()
    else:
        assert not result.ready
        assert result.context is None
        assert result.receipt.status == "unavailable"
        assert result.receipt.reason is not None
