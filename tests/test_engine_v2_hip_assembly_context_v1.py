from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

import structural_analysis.engine_v2 as engine_v2
from structural_analysis.engine_v2.assembly_backend import rtc as assembly_rtc
from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyDimensions,
    HipAssemblyTelemetry,
    HipAssemblyContextError,
    HipAssemblyEvaluationReceipt,
    _context_payload,
    _evaluation_payload,
    _kernel_binding,
    _operator_view_payload,
    open_hip_assembly_execution_context,
    validate_hip_assembly_context_receipt,
    validate_hip_assembly_evaluation,
    validate_hip_assembly_evaluation_receipt,
)
from structural_analysis.engine_v2.assembly_backend.plan import (
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.backends.hip.context import (
    HipContextError,
    HipFreeKnownNotFreedError,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity
from structural_analysis.model_ir import load_model_ir_v2

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMAS = ROOT / "src/structural_analysis/schemas"


def test_root_public_api_exports_device_assembly_v1() -> None:
    assert engine_v2.compile_hip_assembly_plan_v1 is compile_hip_assembly_plan_v1
    assert (
        engine_v2.open_hip_assembly_execution_context
        is open_hip_assembly_execution_context
    )
    assert (
        engine_v2.compile_hip_rtc_linear_frame_truss_assembly_kernel
        is assembly_rtc.compile_hip_rtc_linear_frame_truss_assembly_kernel
    )
    assert engine_v2.HipAssemblyEvaluationReceipt is HipAssemblyEvaluationReceipt
    assert (
        engine_v2.validate_hip_assembly_evaluation_receipt
        is validate_hip_assembly_evaluation_receipt
    )
    assert engine_v2.HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION == (
        "structural-analysis-hip-assembly-plan.v1"
    )


class FakeRuntime:
    library_name = "fake-libamdhip64"

    def __init__(
        self,
        *,
        free_failure_pointer_once: int | None = None,
        device_count: int = 1,
        malloc_failure_at: int | None = None,
        d2h_failure_at: int | None = None,
        sync_failure_at: int | None = None,
        failure_message: str = "injected runtime failure",
    ) -> None:
        self.free_failure_pointer_once = free_failure_pointer_once
        self.device_count = device_count
        self.malloc_failure_at = malloc_failure_at
        self.d2h_failure_at = d2h_failure_at
        self.sync_failure_at = sync_failure_at
        self.failure_message = failure_message
        self.allocations: dict[int, bytearray] = {}
        self.h2d_arrays: list[np.ndarray] = []
        self.h2d_pointers: list[int] = []
        self.d2h_pointers: list[int] = []
        self.sync_calls = 0
        self.free_calls = 0
        self.malloc_calls = 0
        self.d2h_calls = 0
        self.device_ordinal: int | None = None
        self._next = 0x10000000
        self.total_memory = 8 * 1024**3
        self._blocking_d2h_copy = self.copy_d2h

    def hip_init(self) -> int:
        return 0

    def hip_get_device_count(self) -> tuple[int, int]:
        return 0, self.device_count

    def hip_device_get_name(self, ordinal: int) -> tuple[int, str]:
        del ordinal
        return 0, "Fake AMD GPU"

    def hip_runtime_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_driver_get_version(self) -> tuple[int, int]:
        return 0, 60000000

    def hip_error_string(self, status: int) -> str:
        return f"fake status {status}"

    def set_device(self, ordinal: int) -> None:
        self.device_ordinal = ordinal

    def mem_info(self) -> tuple[int, int]:
        used = sum(len(value) for value in self.allocations.values())
        return self.total_memory - used, self.total_memory

    def create_stream(self) -> object:
        return object()

    def malloc(self, byte_length: int) -> int:
        self.malloc_calls += 1
        if self.malloc_calls == self.malloc_failure_at:
            raise HipContextError("hip_allocation_failed", self.failure_message)
        pointer = self._next
        aligned_extent = max(8, (byte_length + 7) & ~7)
        self._next = pointer + aligned_extent
        self.allocations[pointer] = bytearray(byte_length)
        return pointer

    def copy_h2d_async(self, pointer: int, array: np.ndarray, stream: object) -> None:
        del stream
        self.h2d_arrays.append(array)
        self.h2d_pointers.append(pointer)
        self.allocations[pointer][:] = memoryview(array).cast("B")

    def copy_d2h_async(self, array: np.ndarray, pointer: int, stream: object) -> None:
        del stream
        self._copy_d2h(array, pointer)

    def copy_d2h(self, array: np.ndarray, pointer: int) -> None:
        self._copy_d2h(array, pointer)

    def completion_export_copy_binding(self) -> Any:
        return self._blocking_d2h_copy

    def _copy_d2h(self, array: np.ndarray, pointer: int) -> None:
        self.d2h_calls += 1
        self.d2h_pointers.append(pointer)
        if self.d2h_calls == self.d2h_failure_at:
            raise HipContextError("hip_copy_failed", self.failure_message)
        memoryview(array).cast("B")[:] = self.allocations[pointer]

    def synchronize(self, stream: object) -> None:
        del stream
        self.sync_calls += 1
        if self.sync_calls == self.sync_failure_at:
            raise HipContextError("hip_copy_failed", self.failure_message)

    def free(self, pointer: int) -> None:
        self.free_calls += 1
        if pointer == self.free_failure_pointer_once:
            self.free_failure_pointer_once = None
            raise HipFreeKnownNotFreedError(
                "hip_device_access_failed",
                self.failure_message,
            )
        del self.allocations[pointer]

    def destroy_stream(self, stream: object) -> None:
        del stream


def test_fake_runtime_uses_selected_device_and_disjoint_aligned_addresses() -> None:
    runtime = FakeRuntime()
    runtime.set_device(3)
    first = runtime.malloc(1)
    second = runtime.malloc(9)

    assert runtime.device_ordinal == 3
    assert first % 8 == 0 and second % 8 == 0
    assert second >= first + len(runtime.allocations[first])
    assert runtime._next >= second + len(runtime.allocations[second])
    assert runtime._next % 8 == 0


class MutableIdentity:
    def __init__(self) -> None:
        self.identity = assembly_rtc._build_identity(
            architecture="gfx1030",
            source_hash=assembly_rtc._sha256_bytes(assembly_rtc._fixed_source()),
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
            code_object=b"fake-assembly-code-object",
        )
        self.manifest = self.identity.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.manifest))


class FakeKernel:
    def __init__(
        self,
        runtime: FakeRuntime,
        source_plan: Any,
        *,
        bias: float = 0.0,
        device_error: int = 0,
        fail_launch: bool = False,
        close_failures: int = 0,
        failure_message: str = "injected kernel failure",
    ) -> None:
        self.runtime = runtime
        self.source_plan = source_plan
        self.bias = bias
        self.device_error = device_error
        self.fail_launch = fail_launch
        self.close_failures = close_failures
        self.failure_message = failure_message
        self.identity = MutableIdentity()
        self.closed = False
        self.close_calls = 0
        self.element_arguments: tuple[Any, ...] | None = None
        self.gather_arguments: tuple[Any, ...] | None = None

    def launch_element_contributions(self, *arguments: Any) -> None:
        self.element_arguments = arguments
        if self.fail_launch:
            raise RuntimeError(self.failure_message)
        error_pointer = int(arguments[-1])
        np.frombuffer(self.runtime.allocations[error_pointer], dtype="<i4", count=1)[
            0
        ] = self.device_error

    def launch_csr_gather(self, *arguments: Any) -> None:
        self.gather_arguments = arguments
        if self.fail_launch:
            raise RuntimeError(self.failure_message)
        csr_pointer = int(arguments[-2])
        target = np.frombuffer(
            self.runtime.allocations[csr_pointer],
            dtype="<f8",
            count=self.source_plan.nnz,
        )
        target[:] = self.source_plan.array("global_stiffness_csr_values")
        if self.bias:
            target[0] += self.bias

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError(self.failure_message)
        self.closed = True


def _contracts() -> tuple[Any, Any, Any]:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )
    source_plan = compile_execution_plan_v2(buffers)
    return (
        buffers,
        source_plan,
        compile_hip_assembly_plan_v1(buffers, source_plan),
    )


def _open(
    *,
    verify: bool = True,
    runtime: FakeRuntime | None = None,
    **kernel_options: Any,
) -> tuple[Any, Any, Any, FakeRuntime, FakeKernel, Any]:
    buffers, source_plan, assembly_plan = _contracts()
    runtime = runtime or FakeRuntime()
    kernel = FakeKernel(runtime, source_plan, **kernel_options)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        verify_cpu_parity=verify,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    return buffers, source_plan, assembly_plan, runtime, kernel, opened


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_open_executes_two_kernels_without_host_csr_upload() -> None:
    buffers, source_plan, assembly_plan, runtime, kernel, opened = _open()
    assert opened.ready, opened.receipt.reason
    assert opened.evaluation.receipt.status == "verified"
    assert opened.evaluation.receipt.parity is not None
    assert opened.evaluation.receipt.parity.passed
    assert opened.receipt.evidence_scope == "injected_test_double"
    assert opened.receipt.actual_backend == "test_double"
    assert opened.receipt.telemetry.host_csr_values_h2d_bytes == 0
    forbidden = array_data_hash(source_plan.array("global_stiffness_csr_values"))
    assert all(array_data_hash(array) != forbidden for array in runtime.h2d_arrays)
    assert len(opened.receipt.child_buffers) == 8
    assert kernel.element_arguments is not None
    assert (
        kernel.element_arguments[11]
        == opened.context._base_context._pointers["material_law_code"]
    )
    assert (
        kernel.element_arguments[13]
        == opened.context._base_context._pointers["section_family_code"]
    )
    validate_hip_assembly_context_receipt(
        opened.receipt,
        expected_buffers=buffers,
        expected_source_plan=source_plan,
        expected_assembly_plan=assembly_plan,
        expected_kernel=kernel,
    )
    validate_hip_assembly_evaluation(
        opened.evaluation,
        expected_context=opened.context,
        expected_buffers=buffers,
        expected_source_plan=source_plan,
        expected_assembly_plan=assembly_plan,
        expected_kernel=kernel,
    )
    opened.context.close()
    assert not runtime.allocations


def test_output_only_children_have_no_host_backing() -> None:
    from structural_analysis.engine_v2.assembly_backend.context import (
        _child_arrays,
    )

    _, source_plan, assembly_plan = _contracts()
    specs = _child_arrays(source_plan, assembly_plan)
    assert specs["element_contributions"].host_backing is None
    assert specs["csr_values"].host_backing is None
    assert all(
        specs[name].host_backing is not None
        for name in (
            "csr_row_ptr",
            "csr_column_indices",
            "reference_axis_code",
            "reverse_segment_offsets",
            "reverse_contribution_indices",
            "error_flag",
        )
    )


def test_output_specs_do_not_allocate_host_c_or_z_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    _, source_plan, assembly_plan = _contracts()
    real_zeros = context_module.np.zeros
    requested: list[Any] = []

    def spy(shape: Any, *args: Any, **kwargs: Any) -> np.ndarray:
        requested.append(shape)
        return real_zeros(shape, *args, **kwargs)

    monkeypatch.setattr(context_module.np, "zeros", spy)
    specs = context_module._child_arrays(source_plan, assembly_plan)
    assert requested == [1]
    assert specs["element_contributions"].byte_length == (
        8 * assembly_plan.contribution_count
    )
    assert specs["csr_values"].byte_length == 8 * source_plan.nnz


def test_no_verification_download_keeps_device_operator_ready() -> None:
    *_, runtime, _, opened = _open(verify=False)
    assert opened.ready
    assert opened.evaluation.receipt.status == "assembled_unverified"
    assert opened.evaluation.csr_values is None
    assert opened.receipt.telemetry.d2h_bytes == 4
    assert opened.receipt.telemetry.verification_csr_d2h_bytes == 0
    assert len(runtime.d2h_pointers) == 1
    assert opened.context.operator_view().verification_data_hash is None
    opened.context.close()


@pytest.mark.parametrize("mode", ["error", "launch", "parity"])
def test_device_failure_paths_poison_without_fallback(mode: str) -> None:
    options: dict[str, Any] = {}
    if mode == "error":
        options["device_error"] = 4
    elif mode == "launch":
        options["fail_launch"] = True
    else:
        options["bias"] = 1.0e12
    *_, opened = _open(**options)
    assert not opened.ready
    assert opened.context is not None and opened.context.poisoned
    assert opened.receipt.status == "poisoned"
    assert opened.receipt.telemetry.fallback_count == 0
    assert opened.evaluation.receipt.telemetry_delta.fallback_count == 0
    with pytest.raises(HipAssemblyContextError):
        opened.context.operator_view()
    opened.context.close()


def test_operator_view_and_receipts_never_serialize_runtime_terms() -> None:
    *_, opened = _open()
    payloads = (
        opened.receipt.to_dict(),
        opened.evaluation.to_dict(),
        opened.context.operator_view().to_dict(),
    )
    for payload in payloads:
        keys = _all_keys(payload)
        assert not {
            key
            for key in keys
            if any(
                term in key.lower()
                for term in ("pointer", "address", "stream", "handle")
            )
        }
    opened.context.close()


@pytest.mark.parametrize("bad_key", ["module_handle", "kernel_function"])
def test_nested_runtime_key_forgery_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bad_key: str
) -> None:
    from structural_analysis.engine_v2.assembly_backend.context import (
        HipAssemblyBindings,
    )

    *_, opened = _open()
    original = HipAssemblyBindings.to_dict

    def forged(self: Any) -> dict[str, Any]:
        return {**original(self), "nested": {bad_key: 7}}

    monkeypatch.setattr(HipAssemblyBindings, "to_dict", forged)
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(opened.receipt)
    monkeypatch.setattr(HipAssemblyBindings, "to_dict", original)
    opened.context.close()


def test_context_uses_detached_authoritative_witnesses() -> None:
    buffers, source_plan, _, _, _, opened = _open()
    assert opened.context._buffers is not buffers
    assert opened.context._source_plan is not source_plan
    opening_hash = opened.receipt.context_receipt_hash
    object.__setattr__(buffers, "artifact_hash", "sha256:" + "a" * 64)
    object.__setattr__(source_plan, "plan_hash", "sha256:" + "b" * 64)
    assert opened.context.receipt().context_receipt_hash == opening_hash
    assert (
        opened.context.operator_view().source_execution_plan_hash
        != source_plan.plan_hash
    )
    opened.context.close()


def test_rehashed_telemetry_and_claim_forgery_is_rejected() -> None:
    *_, opened = _open()
    forged = replace(
        opened.receipt,
        telemetry=replace(
            opened.receipt.telemetry,
            host_csr_values_h2d_bytes=8,
        ),
        context_receipt_hash="sha256:" + "0" * 64,
    )
    forged = replace(
        forged,
        context_receipt_hash=canonical_hash(
            _context_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(forged)

    forged_eval = replace(
        opened.evaluation.receipt,
        bindings=replace(
            opened.evaluation.receipt.bindings,
            kernel_identity_hash="sha256:" + "9" * 64,
        ),
        receipt_hash="sha256:" + "0" * 64,
    )
    forged_eval = replace(
        forged_eval,
        receipt_hash=canonical_hash(
            _evaluation_payload(forged_eval, include_hash=False)
        ),
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_evaluation(
            replace(opened.evaluation, receipt=forged_eval),
            expected_kernel=opened.context._rtc_kernel,
        )
    opened.context.close()


def test_child_cleanup_failure_retains_retry_owner() -> None:
    runtime = FakeRuntime()
    *_, opened = _open(runtime=runtime)
    pointer = opened.context._pointers["csr_values"]
    runtime.free_failure_pointer_once = pointer
    with pytest.raises(HipAssemblyContextError):
        opened.context.close()
    assert opened.context.receipt().status == "cleanup_failed"
    assert pointer in runtime.allocations
    opened.context.close()
    assert opened.context.closed
    assert not runtime.allocations


def test_kernel_only_cleanup_owner_survives_foundation_unavailable() -> None:
    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime(device_count=0)
    kernel = FakeKernel(runtime, source_plan, close_failures=1)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert not opened.ready
    assert opened.context is not None
    assert opened.context.receipt().status == "cleanup_failed"
    assert not kernel.closed
    opened.context.close()
    assert kernel.closed
    assert opened.context.closed


def test_injected_objects_cannot_spoof_native_evidence() -> None:
    *_, opened = _open()
    assert opened.receipt.evidence_scope == "injected_test_double"
    assert not opened.receipt.claims.native_hiprtc_kernel_loaded
    opened.context.close()


def test_receipt_schemas_are_current_and_strict() -> None:
    *_, opened = _open()
    validate_hip_assembly_evaluation_receipt(opened.evaluation.receipt)
    rows = (
        (
            SCHEMAS / "hip_assembly_context_receipt_v1.schema.json",
            opened.receipt.to_dict(),
        ),
        (
            SCHEMAS / "hip_assembly_evaluation_receipt_v1.schema.json",
            opened.evaluation.to_dict(),
        ),
    )
    for path, payload in rows:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        with pytest.raises(Exception):
            Draft202012Validator(schema).validate({**payload, "extra": 1})
    opened.context.close()


def test_kernel_binding_snapshot_detects_identity_mutation() -> None:
    *_, kernel, opened = _open()
    original = _kernel_binding(kernel, "gfx1030")
    kernel.identity.manifest["code_object_sha256"] = "sha256:" + "a" * 64
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(opened.receipt, expected_kernel=kernel)
    kernel.identity.manifest = kernel.identity.identity.to_dict()
    assert _kernel_binding(kernel, "gfx1030") == original
    opened.context.close()


def test_open_detaches_forged_mapping_proxy_witness() -> None:
    buffers, source_plan, assembly_plan = _contracts()
    external_arrays = dict(source_plan._source_buffers._arrays)
    aliased_buffers = replace(
        source_plan._source_buffers,
        _arrays=MappingProxyType(external_arrays),
    )
    aliased_plan = replace(source_plan, _source_buffers=aliased_buffers)
    aliased_assembly = replace(
        assembly_plan,
        _source_buffers=aliased_buffers,
        _source_execution_plan=aliased_plan,
    )
    validate_execution_plan_v2(aliased_plan, expected_buffers=aliased_buffers)
    runtime = FakeRuntime()
    kernel = FakeKernel(runtime, aliased_plan)
    opened = open_hip_assembly_execution_context(
        aliased_buffers,
        aliased_plan,
        aliased_assembly,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert opened.ready
    assert opened.context._buffers is not aliased_buffers
    assert opened.context._source_plan is not aliased_plan
    opening_hash = opened.receipt.context_receipt_hash
    corrupted = np.array(external_arrays["node_coordinates_m"], copy=True)
    corrupted[0, 0] += 123.0
    external_arrays["node_coordinates_m"] = immutable_array(corrupted, dtype="<f8")
    with pytest.raises(Exception):
        validate_execution_plan_v2(aliased_plan)
    assert opened.context.receipt().context_receipt_hash == opening_hash
    assert opened.context.operator_view().metadata_hash.startswith("sha256:")
    opened.context.close()


class _CompileRuntime:
    def __init__(self, events: list[tuple[str, int]]) -> None:
        self.events = events

    def set_device(self, ordinal: int) -> None:
        self.events.append(("set_device", ordinal))

    def bind(self, *args: Any) -> Any:
        raise AssertionError(args)


@pytest.mark.parametrize("close_failures", [0, 1])
def test_post_kernel_base_exception_preserves_ownership(
    monkeypatch: pytest.MonkeyPatch, close_failures: int
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    buffers, source_plan, assembly_plan = _contracts()
    events: list[tuple[str, int]] = []
    compile_runtime = _CompileRuntime(events)
    kernel = FakeKernel(FakeRuntime(), source_plan, close_failures=close_failures)

    def compile_kernel(*args: Any, **kwargs: Any) -> FakeKernel:
        del args, kwargs
        events.append(("compile", -1))
        assert events[0] == ("set_device", 2)
        return kernel

    monkeypatch.setattr(
        context_module,
        "compile_hip_rtc_linear_frame_truss_assembly_kernel",
        compile_kernel,
    )
    monkeypatch.setattr(
        context_module,
        "open_device_execution_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("base open failed")),
    )
    if close_failures == 0:
        with pytest.raises(HipAssemblyContextError) as caught:
            open_hip_assembly_execution_context(
                buffers,
                source_plan,
                assembly_plan,
                device_ordinal=2,
                architecture="gfx1030",
                runtime=compile_runtime,
            )
        assert caught.value.code == "hip_assembly_context_open_failed"
        assert kernel.closed
    else:
        opened = open_hip_assembly_execution_context(
            buffers,
            source_plan,
            assembly_plan,
            device_ordinal=2,
            architecture="gfx1030",
            runtime=compile_runtime,
        )
        assert opened.context is not None
        assert opened.receipt.status == "cleanup_failed"
        assert not kernel.closed
        opened.context.close()
        assert kernel.closed
    assert events[:2] == [("set_device", 2), ("compile", -1)]


def test_verification_host_oom_precedes_kernel_and_device_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    buffers, source_plan, assembly_plan = _contracts()
    compile_calls = 0

    def should_not_compile(*args: Any, **kwargs: Any) -> Any:
        nonlocal compile_calls
        compile_calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(
        context_module,
        "_allocate_host_staging",
        lambda *args: (_ for _ in ()).throw(MemoryError("verification staging OOM")),
    )
    monkeypatch.setattr(
        context_module,
        "compile_hip_rtc_linear_frame_truss_assembly_kernel",
        should_not_compile,
    )
    with pytest.raises(MemoryError):
        open_hip_assembly_execution_context(
            buffers,
            source_plan,
            assembly_plan,
            architecture="gfx1030",
            runtime=_CompileRuntime([]),
        )
    assert compile_calls == 0


def test_no_verification_mode_never_allocates_host_z_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime()
    kernel = FakeKernel(runtime, source_plan)
    original = context_module._allocate_host_staging
    calls: list[tuple[int, bool]] = []

    def spy(csr_nnz: int, verify: bool) -> tuple[np.ndarray, np.ndarray | None]:
        calls.append((csr_nnz, verify))
        return original(csr_nnz, verify)

    monkeypatch.setattr(context_module, "_allocate_host_staging", spy)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        verify_cpu_parity=False,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert calls == [(source_plan.nnz, False)]
    opened.context.close()


@pytest.mark.parametrize(
    ("failure_at", "attempts", "successes"),
    [(17, 1, 0), (20, 4, 3)],
)
def test_allocation_failure_reports_observed_not_planned_peak(
    failure_at: int, attempts: int, successes: int
) -> None:
    runtime = FakeRuntime(malloc_failure_at=failure_at)
    *_, opened = _open(runtime=runtime)
    delta = opened.evaluation.receipt.telemetry_delta
    assert not opened.ready
    assert delta.child_allocation_attempt_count == attempts
    assert delta.child_allocation_success_count == successes
    assert delta.current_device_payload_bytes == 0
    expected_peak = (
        sum(view.byte_length for view in opened.receipt.child_buffers[:successes])
        if opened.receipt.child_buffers
        else sum(
            [
                4 * (_contracts()[1].dof_count + 1),
                4 * _contracts()[1].nnz,
                _contracts()[1].element_count,
            ][:successes]
        )
    )
    assert delta.peak_device_payload_bytes == expected_peak


def test_partial_cleanup_reports_only_retained_child_bytes() -> None:
    runtime = FakeRuntime(
        malloc_failure_at=20,
        free_failure_pointer_once=0x10000440,
    )
    *_, opened = _open(runtime=runtime)
    assert opened.context is not None
    assert opened.receipt.status == "cleanup_failed"
    delta = opened.evaluation.receipt.telemetry_delta
    axis_bytes = opened.receipt.child_buffers[2].byte_length
    first_three = sum(view.byte_length for view in opened.receipt.child_buffers[:3])
    assert delta.child_allocation_attempt_count == 4
    assert delta.child_allocation_success_count == 3
    assert delta.current_device_payload_bytes == axis_bytes
    assert delta.peak_device_payload_bytes == first_three
    opened.context.close()


def test_huge_finite_parity_error_is_stable_and_cleanup_reachable() -> None:
    *_, opened = _open(bias=1.0e308)
    assert opened.receipt.status == "poisoned"
    parity = opened.evaluation.receipt.parity
    assert parity is not None
    assert np.isfinite(parity.csr_values.relative_l2_error)
    assert np.isfinite(parity.csr_values.max_abs_error)
    opened.context.close()


def test_forced_postprocess_exception_fully_cleans_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime()
    kernel = FakeKernel(runtime, source_plan)
    monkeypatch.setattr(
        context_module,
        "_parity_report",
        lambda *args: (_ for _ in ()).throw(RuntimeError("postprocess failed")),
    )
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert opened.context is None
    assert opened.receipt.status == "unavailable"
    assert not runtime.allocations
    assert kernel.closed


@pytest.mark.parametrize("failure_at", [1, 2])
def test_d2h_failure_records_attempt_and_success_counts(failure_at: int) -> None:
    runtime = FakeRuntime(
        d2h_failure_at=failure_at,
        failure_message="device pointer 0xdeadbeef stream 0xcafebabe",
    )
    *_, opened = _open(runtime=runtime)
    delta = opened.evaluation.receipt.telemetry_delta
    assert opened.receipt.status == "poisoned"
    assert delta.d2h_operation_attempt_count == failure_at
    assert delta.d2h_operation_success_count == failure_at - 1
    assert delta.d2h_operation_count == failure_at - 1
    assert "0xdeadbeef" not in opened.receipt.reason.detail
    assert "0xcafebabe" not in opened.receipt.reason.detail
    opened.context.close()


def test_sync_failure_records_attempt_without_success() -> None:
    runtime = FakeRuntime(
        sync_failure_at=2,
        failure_message="stream 0xcafebabe failed at address 0xdeadbeef",
    )
    *_, opened = _open(runtime=runtime)
    delta = opened.evaluation.receipt.telemetry_delta
    assert opened.receipt.status == "poisoned"
    assert delta.assembly_sync_attempt_count == 1
    assert delta.assembly_sync_success_count == 0
    assert delta.assembly_sync_count == 0
    assert "0x" not in opened.receipt.reason.detail
    opened.context.close()


def _rehash_context(receipt: Any) -> Any:
    draft = replace(receipt, context_receipt_hash="sha256:" + "0" * 64)
    return replace(
        draft,
        context_receipt_hash=canonical_hash(
            _context_payload(draft, include_hash=False)
        ),
    )


def test_expected_inputs_replay_all_six_upload_hashes() -> None:
    buffers, source_plan, assembly_plan, _, kernel, opened = _open()
    for index in (0, 1, 2, 3, 4, 7):
        views = list(opened.receipt.child_buffers)
        views[index] = replace(views[index], data_hash="sha256:" + "9" * 64)
        forged = _rehash_context(replace(opened.receipt, child_buffers=tuple(views)))
        with pytest.raises(HipAssemblyContextError):
            validate_hip_assembly_context_receipt(
                forged,
                expected_buffers=buffers,
                expected_source_plan=source_plan,
                expected_assembly_plan=assembly_plan,
                expected_kernel=kernel,
            )
    opened.context.close()


def test_exact_nested_and_scalar_types_reject_rehashed_forgeries() -> None:
    *_, opened = _open()
    mutable = _rehash_context(
        replace(opened.receipt, child_buffers=list(opened.receipt.child_buffers))
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(mutable)

    class TelemetrySubclass(HipAssemblyTelemetry):
        pass

    subclass = TelemetrySubclass(**opened.receipt.telemetry.to_dict())
    forged_subclass = _rehash_context(replace(opened.receipt, telemetry=subclass))
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(forged_subclass)

    forged_dimensions = replace(opened.receipt.dimensions, node_count=True)
    assert isinstance(forged_dimensions, HipAssemblyDimensions)
    forged_bool_int = _rehash_context(
        replace(opened.receipt, dimensions=forged_dimensions)
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(forged_bool_int)
    opened.context.close()


def _rehash_evaluation(receipt: Any) -> Any:
    draft = replace(receipt, receipt_hash="sha256:" + "0" * 64)
    return replace(
        draft,
        receipt_hash=canonical_hash(_evaluation_payload(draft, include_hash=False)),
    )


def test_expected_context_replays_full_dimensions_and_operator_identity() -> None:
    buffers, source_plan, assembly_plan, _, kernel, opened = _open()
    forged_dimensions = _rehash_context(
        replace(
            opened.receipt,
            dimensions=replace(
                opened.receipt.dimensions,
                material_count=opened.receipt.dimensions.material_count + 7,
                section_count=opened.receipt.dimensions.section_count + 9,
            ),
        )
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(
            forged_dimensions,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=kernel,
        )

    operator_draft = replace(
        opened.receipt.operator_view,
        operator_id="HipAssemblyOperator:" + "f" * 24,
        metadata_hash="sha256:" + "0" * 64,
    )
    forged_operator = replace(
        operator_draft,
        metadata_hash=canonical_hash(
            _operator_view_payload(operator_draft, include_hash=False)
        ),
    )
    forged_receipt = _rehash_context(
        replace(opened.receipt, operator_view=forged_operator)
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(
            forged_receipt,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=kernel,
        )
    opened.context.close()


@pytest.mark.parametrize(
    "field",
    ["source_operator_hash", "operator_id", "execution_id"],
)
def test_expected_evaluation_replays_all_bindings_and_ids(field: str) -> None:
    buffers, source_plan, assembly_plan, _, kernel, opened = _open()
    receipt = opened.evaluation.receipt
    if field == "source_operator_hash":
        receipt = replace(
            receipt,
            bindings=replace(
                receipt.bindings,
                source_operator_hash="sha256:" + "e" * 64,
            ),
        )
    elif field == "operator_id":
        receipt = replace(receipt, operator_id="HipAssemblyOperator:" + "e" * 24)
    else:
        receipt = replace(receipt, execution_id="HipAssemblyEvaluation:" + "e" * 24)
    forged = replace(opened.evaluation, receipt=_rehash_evaluation(receipt))
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_evaluation(
            forged,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=kernel,
        )
    opened.context.close()


def test_standalone_injected_kernel_cannot_forge_native_evidence() -> None:
    *_, kernel, opened = _open()
    receipt = opened.evaluation.receipt
    forged = _rehash_evaluation(
        replace(
            receipt,
            evidence_scope="native_hiprtc",
            actual_backend="hip",
            claims=replace(receipt.claims, native_hiprtc_kernel_loaded=True),
        )
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_evaluation(
            replace(opened.evaluation, receipt=forged),
            expected_kernel=kernel,
        )
    opened.context.close()


def test_small_decimal_runtime_references_are_redacted() -> None:
    message = "device pointer 1 stream 7 module 12 function 3"
    *_, opened = _open(fail_launch=True, failure_message=message)
    detail = opened.receipt.reason.detail
    assert "pointer 1" not in detail
    assert "stream 7" not in detail
    assert "module 12" not in detail
    assert "function 3" not in detail
    opened.receipt.to_dict()
    opened.evaluation.to_dict()
    opened.context.close()


def test_unavailable_context_id_replays_without_device_record() -> None:
    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime(malloc_failure_at=17)
    closed_kernel = FakeKernel(runtime, source_plan)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=closed_kernel,
    )
    assert opened.receipt.device is None
    live_kernel = FakeKernel(FakeRuntime(), source_plan)
    forged = _rehash_context(
        replace(
            opened.receipt,
            context_id="HipAssemblyContext:" + "d" * 24,
        )
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(
            forged,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=live_kernel,
        )
    live_kernel.close()


def test_kernel_identity_bool_abi_is_not_coerced() -> None:
    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime()
    kernel = FakeKernel(runtime, source_plan)
    kernel.identity.manifest["abi_version"] = True
    with pytest.raises(HipAssemblyContextError):
        open_hip_assembly_execution_context(
            buffers,
            source_plan,
            assembly_plan,
            architecture="gfx1030",
            runtime=runtime,
            rtc_kernel=kernel,
        )
    assert kernel.closed
    assert not runtime.allocations


def test_closed_and_cleanup_success_receipts_replay_closed_kernel_snapshot() -> None:
    buffers, source_plan, assembly_plan, _, kernel, opened = _open()
    opened.context.close()
    validate_hip_assembly_context_receipt(
        opened.context.receipt(),
        expected_buffers=buffers,
        expected_source_plan=source_plan,
        expected_assembly_plan=assembly_plan,
        expected_kernel=kernel,
    )

    runtime = FakeRuntime(malloc_failure_at=17)
    failed_kernel = FakeKernel(runtime, source_plan)
    failed = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=failed_kernel,
    )
    assert failed.context is None and failed_kernel.closed
    validate_hip_assembly_context_receipt(
        failed.receipt,
        expected_buffers=buffers,
        expected_source_plan=source_plan,
        expected_assembly_plan=assembly_plan,
        expected_kernel=failed_kernel,
    )


@pytest.mark.parametrize("field", ["shape", "byte_length", "device_ordinal"])
def test_operator_view_self_consistency_rejects_rehashed_fields(field: str) -> None:
    *_, opened = _open()
    operator = opened.receipt.operator_view
    changes: dict[str, Any]
    if field == "shape":
        changes = {"shape": (operator.csr_nnz + 1,)}
    elif field == "byte_length":
        changes = {"byte_length": operator.byte_length + 8}
    else:
        changes = {"device_ordinal": operator.device_ordinal + 1}
    draft = replace(
        operator,
        **changes,
        metadata_hash="sha256:" + "0" * 64,
    )
    forged_operator = replace(
        draft,
        metadata_hash=canonical_hash(_operator_view_payload(draft, include_hash=False)),
    )
    forged = _rehash_context(replace(opened.receipt, operator_view=forged_operator))
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(forged)
    opened.context.close()


@pytest.mark.parametrize("verify", [True, False])
def test_operator_verification_hash_matches_mode(verify: bool) -> None:
    *_, opened = _open(verify=verify)
    operator = opened.receipt.operator_view
    replacement = None if verify else "sha256:" + "7" * 64
    draft = replace(
        operator,
        verification_data_hash=replacement,
        metadata_hash="sha256:" + "0" * 64,
    )
    forged_operator = replace(
        draft,
        metadata_hash=canonical_hash(_operator_view_payload(draft, include_hash=False)),
    )
    forged = _rehash_context(replace(opened.receipt, operator_view=forged_operator))
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_context_receipt(forged)
    opened.context.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"h2d_bytes": 0},
        {
            "allocation_count": 0,
            "child_allocation_attempt_count": 0,
            "child_allocation_success_count": 0,
        },
        {"current_device_payload_bytes": 0, "peak_device_payload_bytes": 0},
        {
            "child_initial_h2d_attempt_count": 0,
            "child_initial_h2d_success_count": 0,
            "h2d_operation_count": 0,
            "h2d_bytes": 0,
        },
    ],
)
def test_expected_evaluation_replays_complete_success_telemetry(
    changes: dict[str, int],
) -> None:
    buffers, source_plan, assembly_plan, _, kernel, opened = _open()
    forged_receipt = _rehash_evaluation(
        replace(
            opened.evaluation.receipt,
            telemetry_delta=replace(
                opened.evaluation.receipt.telemetry_delta, **changes
            ),
        )
    )
    with pytest.raises(HipAssemblyContextError):
        validate_hip_assembly_evaluation(
            replace(opened.evaluation, receipt=forged_receipt),
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=kernel,
        )
    opened.context.close()


class _BadStringError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("string conversion forbidden")


def test_bad_exception_string_from_launch_keeps_owner_reachable() -> None:
    buffers, source_plan, assembly_plan = _contracts()
    runtime = FakeRuntime()

    class BadLaunchKernel(FakeKernel):
        def launch_element_contributions(self, *arguments: Any) -> None:
            del arguments
            raise _BadStringError()

    kernel = BadLaunchKernel(runtime, source_plan)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert opened.context is not None and opened.context.poisoned
    assert "BadStringError" in opened.receipt.reason.detail
    opened.context.close()
    assert not runtime.allocations and kernel.closed


def test_bad_exception_string_from_malloc_and_postprocess_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        context as context_module,
    )

    buffers, source_plan, assembly_plan = _contracts()

    class BadMallocRuntime(FakeRuntime):
        def malloc(self, byte_length: int) -> int:
            if self.malloc_calls == 16:
                self.malloc_calls += 1
                raise _BadStringError()
            return super().malloc(byte_length)

    runtime = BadMallocRuntime()
    kernel = FakeKernel(runtime, source_plan)
    failed = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert failed.context is None
    assert not runtime.allocations and kernel.closed

    runtime2 = FakeRuntime()
    kernel2 = FakeKernel(runtime2, source_plan)
    monkeypatch.setattr(
        context_module,
        "_parity_report",
        lambda *args: (_ for _ in ()).throw(_BadStringError()),
    )
    post = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime2,
        rtc_kernel=kernel2,
    )
    assert post.context is None
    assert not runtime2.allocations and kernel2.closed


def test_resident_consumer_lease_blocks_parent_close_atomically() -> None:
    *_, runtime, _, opened = _open(verify=False)
    context = opened.context
    assert context is not None
    token = context._acquire_resident_consumer()
    sync_before = runtime.sync_calls
    free_before = runtime.free_calls

    with pytest.raises(
        HipAssemblyContextError,
        match="hip_assembly_resident_consumer_active",
    ):
        context.close()

    assert runtime.sync_calls == sync_before
    assert runtime.free_calls == free_before
    assert not context.closed
    context._release_resident_consumer(token)
    context.close()
    assert context.closed


def test_resident_consumer_lease_is_exclusive_and_epoch_is_monotonic() -> None:
    *_, opened = _open(verify=False)
    context = opened.context
    assert context is not None
    first = context._acquire_resident_consumer()
    first_epoch = context._resident_consumer_epoch(first)

    with pytest.raises(
        HipAssemblyContextError,
        match="hip_assembly_resident_consumer_active",
    ):
        context._acquire_resident_consumer()
    with pytest.raises(
        HipAssemblyContextError,
        match="hip_assembly_resident_consumer_token_invalid",
    ):
        context._require_resident_consumer(object())

    context._release_resident_consumer(first)
    second = context._acquire_resident_consumer()
    assert context._resident_consumer_epoch(second) == first_epoch + 1
    with pytest.raises(
        HipAssemblyContextError,
        match="hip_assembly_resident_consumer_token_invalid",
    ):
        context._require_resident_consumer(first)
    context._release_resident_consumer(second)
    context.close()


def test_resident_consumer_failure_poison_is_shared_with_parent() -> None:
    *_, opened = _open(verify=False)
    context = opened.context
    assert context is not None
    token = context._acquire_resident_consumer()
    context._poison_resident_consumer(token, "downstream launch failed")
    assert context.poisoned
    with pytest.raises(
        HipAssemblyContextError,
        match="hip_assembly_context_poisoned",
    ):
        context.operator_view()
    context._release_resident_consumer(token)
    context.close()
    assert context.closed


def test_resident_consumer_lease_acquire_is_atomic_across_threads() -> None:
    *_, opened = _open(verify=False)
    context = opened.context
    assert context is not None
    barrier = threading.Barrier(3)
    tokens: list[object] = []
    errors: list[HipAssemblyContextError] = []

    def acquire() -> None:
        barrier.wait()
        try:
            token = context._acquire_resident_consumer()
        except HipAssemblyContextError as exc:
            errors.append(exc)
        else:
            tokens.append(token)

    threads = [threading.Thread(target=acquire) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert len(tokens) == 1
    assert len(errors) == 1
    assert errors[0].code == "hip_assembly_resident_consumer_active"
    assert context._resident_consumer_token is tokens[0]
    assert context._resident_consumer_epoch(tokens[0]) == 1
    context._release_resident_consumer(tokens[0])
    context.close()


def test_bad_exception_string_from_copy_and_close_preserves_retry_owner() -> None:
    buffers, source_plan, assembly_plan = _contracts()

    class BadCopyRuntime(FakeRuntime):
        def copy_d2h_async(
            self, array: np.ndarray, pointer: int, stream: object
        ) -> None:
            del array, pointer, stream
            raise _BadStringError()

    runtime = BadCopyRuntime()
    kernel = FakeKernel(runtime, source_plan)
    opened = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime,
        rtc_kernel=kernel,
    )
    assert opened.context is not None and opened.context.poisoned
    assert "BadStringError" in opened.receipt.reason.detail
    opened.context.close()

    class BadCloseKernel(FakeKernel):
        def close(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise _BadStringError()
            self.closed = True

    runtime2 = FakeRuntime()
    kernel2 = BadCloseKernel(runtime2, source_plan)
    opened2 = open_hip_assembly_execution_context(
        buffers,
        source_plan,
        assembly_plan,
        architecture="gfx1030",
        runtime=runtime2,
        rtc_kernel=kernel2,
    )
    with pytest.raises(HipAssemblyContextError):
        opened2.context.close()
    assert opened2.context.receipt().status == "cleanup_failed"
    opened2.context.close()
    assert kernel2.closed and not runtime2.allocations
