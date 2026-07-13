from __future__ import annotations

import ctypes
from dataclasses import FrozenInstanceError, fields, replace
import dis
import inspect
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import krylov_primitives_rtc
from structural_analysis.engine_v2.assembly_backend.krylov_primitives_rtc import (
    HIP_RTC_KRYLOV_AFFINE_SYMBOL,
    HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL,
    HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_FILL_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL,
    HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE,
    HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK,
    HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL,
    KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
    KRYLOV_DEVICE_ERROR_CSR_STRUCTURE,
    KRYLOV_DEVICE_ERROR_INVALID_COUNT_OR_GEOMETRY,
    KRYLOV_DEVICE_ERROR_INVALID_LASSQ_PAIR,
    KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL,
    KRYLOV_DEVICE_ERROR_NONE,
    KRYLOV_DEVICE_ERROR_NONFINITE_INPUT,
    HipRtcKrylovPrimitivesError,
    compile_hip_rtc_krylov_primitives_kernel,
    reduction_output_count,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity

KERNEL_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "structural_analysis"
    / "engine_v2"
    / "assembly_backend"
    / "kernels"
    / "engine_v2_krylov_primitives_v1.hip.cpp"
)

SYMBOLS = (
    HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL,
    HIP_RTC_KRYLOV_FILL_SYMBOL,
    HIP_RTC_KRYLOV_AFFINE_SYMBOL,
    HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL,
    HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL,
    HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL,
)

ABI_KINDS = {
    HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL: "iippppp",
    HIP_RTC_KRYLOV_FILL_SYMBOL: "idpp",
    HIP_RTC_KRYLOV_AFFINE_SYMBOL: "idpdppp",
    HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL: "ipppp",
    HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL: "ipppp",
    HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL: "ippp",
    HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL: "ippp",
    HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL: "ippp",
    HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL: "ppp",
}


class FakeRtcApi:
    def __init__(
        self,
        *,
        compile_status: int = 0,
        compile_log: str = "",
        destroy_status: int = 0,
    ) -> None:
        self.identity = HipRtcLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libhiprtc.so",
            loaded_name="fake-libhiprtc.so",
            resolved_path="/fake/libhiprtc.so",
            sha256="sha256:" + ("2" * 64),
        )
        self.compile_status = compile_status
        self.compile_log = compile_log
        self.destroy_status = destroy_status
        self.created_source = b""
        self.created_program_name: str | None = None
        self.options: tuple[str, ...] = ()
        self.destroy_calls = 0

    def error_string(self, status: int) -> str:
        return f"fake HIPRTC status {status}"

    def version(self) -> tuple[int, int, int]:
        return 0, 9, 1

    def create_program(
        self,
        source: bytes,
        program_name: str | None = None,
    ) -> tuple[int, ctypes.c_void_p]:
        self.created_source = source
        self.created_program_name = program_name
        return 0, ctypes.c_void_p(257)

    def compile_program(self, program: Any, options: Any) -> int:
        assert _pointer_value(program) == 257
        self.options = tuple(options)
        return self.compile_status

    def program_log(self, program: Any) -> str:
        assert _pointer_value(program) == 257
        return self.compile_log

    def code_object(self, program: Any) -> bytes:
        assert _pointer_value(program) == 257
        return b"fake-krylov-primitives-code-object-v1"

    def destroy_program(self, program: Any) -> int:
        assert _pointer_value(program) == 257
        self.destroy_calls += 1
        return self.destroy_status


class FakeLoadedRuntime:
    def __init__(
        self,
        *,
        load_status: int = 0,
        missing_symbol: str | None = None,
        launch_status: int = 0,
        unload_statuses: tuple[int, ...] = (0,),
    ) -> None:
        self.library_identity = HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path=None,
            sha256="sha256:" + ("1" * 64),
        )
        self.load_status = load_status
        self.missing_symbol = missing_symbol
        self.launch_status = launch_status
        self.unload_statuses = list(unload_statuses)
        self.function_symbols: list[str] = []
        self.launch_records: list[dict[str, Any]] = []
        self.load_calls = 0
        self.unload_calls = 0
        self._symbol_handles = {
            symbol: 769 + index for index, symbol in enumerate(SYMBOLS)
        }
        self._handle_symbols = {
            handle: symbol for symbol, handle in self._symbol_handles.items()
        }

    def hip_init(self) -> int:
        return 0

    def hip_error_string(self, status: int) -> str:
        return f"fake HIP status {status}"

    def bind(self, symbol: str, argtypes: Any, restype: Any) -> Any:
        del argtypes, restype
        return {
            "hipModuleLoadData": self._load,
            "hipModuleGetFunction": self._function,
            "hipModuleLaunchKernel": self._launch,
            "hipModuleUnload": self._unload,
        }[symbol]

    def _load(self, output: Any, image: Any) -> int:
        del image
        self.load_calls += 1
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(513)
        return self.load_status

    def _function(self, output: Any, module: Any, symbol: bytes) -> int:
        assert _pointer_value(module) == 513
        decoded = symbol.decode("ascii")
        self.function_symbols.append(decoded)
        if decoded == self.missing_symbol:
            return 7
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(
            self._symbol_handles[decoded]
        )
        return 0

    def _launch(
        self,
        function: Any,
        grid_x: int,
        grid_y: int,
        grid_z: int,
        block_x: int,
        block_y: int,
        block_z: int,
        shared: int,
        stream: Any,
        parameters: Any,
        extra: Any,
    ) -> int:
        symbol = self._handle_symbols[_pointer_value(function)]
        arguments: list[int | float] = []
        for index, kind in enumerate(ABI_KINDS[symbol]):
            ctype = {
                "i": ctypes.c_int,
                "d": ctypes.c_double,
                "p": ctypes.c_void_p,
            }[kind]
            arguments.append(
                ctypes.cast(parameters[index], ctypes.POINTER(ctype)).contents.value
            )
        self.launch_records.append(
            {
                "symbol": symbol,
                "grid": (grid_x, grid_y, grid_z),
                "block": (block_x, block_y, block_z),
                "shared": shared,
                "stream": _pointer_value(stream),
                "arguments": tuple(arguments),
                "extra": extra,
            }
        )
        return self.launch_status

    def _unload(self, module: Any) -> int:
        assert _pointer_value(module) == 513
        self.unload_calls += 1
        if len(self.unload_statuses) > 1:
            return self.unload_statuses.pop(0)
        return self.unload_statuses[0]


def _pointer_value(value: Any) -> int | None:
    raw = value.value if isinstance(value, ctypes.c_void_p) else value
    return None if raw is None else int(raw)


class _SingleFireRtcLineInterrupt:
    def __init__(self, target: Any, source_fragment: str) -> None:
        source, start_line = inspect.getsourcelines(target)
        matching_lines = [
            start_line + index
            for index, line in enumerate(source)
            if source_fragment in line
        ]
        assert len(matching_lines) == 1
        self._filename = target.__code__.co_filename
        self._line = matching_lines[0]
        self._previous_trace: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if (
            not self.fired
            and event == "line"
            and frame.f_code.co_filename == self._filename
            and frame.f_lineno == self._line
        ):
            self.fired = True
            sys.settrace(self._previous_trace)
            raise KeyboardInterrupt("injected RTC handoff line interruption")
        return self._trace

    def __enter__(self) -> _SingleFireRtcLineInterrupt:
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous_trace)


class _SingleFireAfterStoreInterrupt:
    def __init__(self, target: Any, source_fragment: str) -> None:
        source, start_line = inspect.getsourcelines(target)
        matching_lines = [
            start_line + index
            for index, line in enumerate(source)
            if source_fragment in line
        ]
        assert len(matching_lines) == 1
        target_line = matching_lines[0]
        current_line = target.__code__.co_firstlineno
        matching_offsets: list[int] = []
        for instruction in dis.get_instructions(target):
            if instruction.starts_line is not None:
                current_line = instruction.starts_line
            if (
                current_line == target_line
                and instruction.opname == "STORE_FAST"
                and instruction.argval == "status"
            ):
                matching_offsets.append(instruction.offset)
        assert len(matching_offsets) == 1
        self._target_code = target.__code__
        self._store_offset = matching_offsets[0]
        self._store_seen = False
        self._previous_trace: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if frame.f_code is self._target_code:
            frame.f_trace_opcodes = True
            if event == "opcode":
                if self._store_seen:
                    self.fired = True
                    sys.settrace(self._previous_trace)
                    raise KeyboardInterrupt("injected after RTC load status STORE")
                if frame.f_lasti == self._store_offset:
                    self._store_seen = True
        return self._trace

    def __enter__(self) -> _SingleFireAfterStoreInterrupt:
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous_trace)


class _SingleFireAfterAttributeStoreInterrupt:
    def __init__(self, target: Any, source_fragment: str, attribute: str) -> None:
        source, start_line = inspect.getsourcelines(target)
        matching_lines = [
            start_line + index
            for index, line in enumerate(source)
            if source_fragment in line
        ]
        assert len(matching_lines) == 1
        target_line = matching_lines[0]
        current_line = target.__code__.co_firstlineno
        matching_offsets: list[int] = []
        for instruction in dis.get_instructions(target):
            if instruction.starts_line is not None:
                current_line = instruction.starts_line
            if (
                current_line == target_line
                and instruction.opname == "STORE_ATTR"
                and instruction.argval == attribute
            ):
                matching_offsets.append(instruction.offset)
        assert len(matching_offsets) == 1
        self._target_code = target.__code__
        self._store_offset = matching_offsets[0]
        self._store_seen = False
        self._previous_trace: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if frame.f_code is self._target_code:
            frame.f_trace_opcodes = True
            if event == "opcode":
                if self._store_seen:
                    self.fired = True
                    sys.settrace(self._previous_trace)
                    raise KeyboardInterrupt("injected after Krylov ownership transfer")
                if frame.f_lasti == self._store_offset:
                    self._store_seen = True
        return self._trace

    def __enter__(self) -> _SingleFireAfterAttributeStoreInterrupt:
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous_trace)


def _compile_fake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_rtc: FakeRtcApi | None = None,
    runtime: FakeLoadedRuntime | None = None,
) -> tuple[Any, FakeRtcApi, FakeLoadedRuntime]:
    fake_rtc = fake_rtc or FakeRtcApi()
    runtime = runtime or FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    return (
        compile_hip_rtc_krylov_primitives_kernel(runtime, "gfx1030"),
        fake_rtc,
        runtime,
    )


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_fixed_compile_binds_nine_symbols_and_exact_hashed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, fake_rtc, runtime = _compile_fake(monkeypatch)
    identity = kernel.identity
    manifest = identity.to_dict()
    assert fake_rtc.created_source == KERNEL_SOURCE.read_bytes()
    assert fake_rtc.created_program_name == KERNEL_SOURCE.name
    assert fake_rtc.options == (
        "--offload-arch=gfx1030",
        "-O3",
        "-std=c++17",
        "-ffp-contract=off",
    )
    assert runtime.function_symbols == list(SYMBOLS)
    assert identity.kernel_symbols == SYMBOLS
    assert tuple(manifest["kernel_symbols"].values()) == SYMBOLS
    assert manifest["launch_geometry"] == {
        "block_size": 256,
        "reduction_values_per_block": 512,
    }
    assert identity.source_sha256 == krylov_primitives_rtc._sha256_bytes(
        KERNEL_SOURCE.read_bytes()
    )
    assert identity.code_object_byte_length > 0
    assert identity.identity_hash.startswith("sha256:")
    witness_field = next(
        item for item in fields(type(identity)) if item.name == "_code_object_witness"
    )
    assert not witness_field.init
    assert not witness_field.repr
    assert not witness_field.compare
    assert "_code_object_witness" not in repr(identity)
    assert "_code_object_witness" not in manifest
    assert not {
        "handle",
        "pointer",
        "module",
        "function",
        "stream",
    } & _all_keys(manifest)
    with pytest.raises(FrozenInstanceError):
        identity.architecture = "gfx90a"

    forged = replace(identity, fill_symbol="forged", identity_hash="")
    forged = replace(
        forged,
        identity_hash=canonical_hash(
            krylov_primitives_rtc._identity_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcKrylovPrimitivesError) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_krylov_primitives_identity_invalid"

    for forged_values in (
        {"code_object_byte_length": identity.code_object_byte_length + 1},
        {"code_object_sha256": "sha256:" + ("f" * 64)},
    ):
        forged = replace(identity, **forged_values, identity_hash="")
        forged = replace(
            forged,
            identity_hash=canonical_hash(
                krylov_primitives_rtc._identity_payload(forged, include_hash=False)
            ),
        )
        with pytest.raises(HipRtcKrylovPrimitivesError) as witness_error:
            forged.to_dict()
        assert witness_error.value.code == "hip_rtc_krylov_primitives_identity_invalid"
    with pytest.raises(ValueError):
        replace(identity, _code_object_witness=b"forged")
    kernel.close()


def test_public_surface_source_and_device_error_contract() -> None:
    assert tuple(
        inspect.signature(compile_hip_rtc_krylov_primitives_kernel).parameters
    ) == ("loaded_runtime", "architecture", "hiprtc_library")
    assert tuple(inspect.signature(reduction_output_count).parameters) == (
        "value_count",
    )
    assert HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE == 256
    assert HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK == 512
    assert (
        KRYLOV_DEVICE_ERROR_NONE,
        KRYLOV_DEVICE_ERROR_INVALID_COUNT_OR_GEOMETRY,
        KRYLOV_DEVICE_ERROR_CSR_STRUCTURE,
        KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL,
        KRYLOV_DEVICE_ERROR_NONFINITE_INPUT,
        KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
        KRYLOV_DEVICE_ERROR_INVALID_LASSQ_PAIR,
    ) == (0, 1, 2, 4, 8, 16, 32)

    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert source.count('extern "C" __global__ void') == 9
    assert source.count("atomicOr") == 1
    assert source.count("#pragma clang fp contract(off)") == 1
    assert "kReductionValuesPerBlock = 512" in source
    assert source.count("const unsigned long long promoted_count") == 2
    assert source.count("static_cast<unsigned long long>(count)") == 2
    assert "(count + kBlockSize" not in source
    assert "(count + kReductionValuesPerBlock" not in source
    assert "for (unsigned int offset = kBlockSize / 2" in source
    assert "value == 0.0 ? 0.0 : value" in source
    assert "diagonal_count != 1" in source
    assert "diagonal > 0.0" in source
    assert "1.0 / diagonal" in source
    assert "left.scale >= right.scale" in source
    assert "ratio * ratio" in source
    for symbol in SYMBOLS:
        signature = f'extern "C" __global__ void {symbol}('
        assert source.count(signature) == 1
    for forbidden in (
        "#include",
        "hipLaunchKernelGGL",
        "hipMalloc",
        "hipMemcpy",
        "atomicAdd",
        "__shfl",
        "--use_fast_math",
        "-ffast-math",
        "clamp",
        "shift",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    "phase",
    ("after_isolated_set", "after_kernel_publish", "at_frame_disarm"),
)
def test_handoff_interruptions_preserve_caller_context_and_exact_owner(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    sentinel_target = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    sentinel = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoffFrame(
        sentinel_target
    )
    context_token = krylov_primitives_rtc._KERNEL_HANDOFF.set(sentinel)
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    published: list[Any] = []
    compiler_calls = 0
    interruption = KeyboardInterrupt(f"interrupt Krylov handoff at {phase}")

    def compile_then_interrupt(
        loaded_runtime: Any,
        architecture: str,
        hiprtc_library: str | Path | None,
    ) -> Any:
        nonlocal compiler_calls
        compiler_calls += 1
        kernel = compile_hip_rtc_krylov_primitives_kernel(
            loaded_runtime,
            architecture,
            hiprtc_library,
        )
        published.append(kernel)
        assert handoff.kernel is kernel
        if phase == "after_kernel_publish":
            raise interruption
        return kernel

    try:
        if phase == "after_kernel_publish":
            with pytest.raises(KeyboardInterrupt) as caught:
                krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                    compile_then_interrupt,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert caught.value is interruption
        else:
            source_fragment = (
                "return compiler("
                if phase == "after_isolated_set"
                else "frame.disarm()"
            )
            with (
                _SingleFireRtcLineInterrupt(
                    krylov_primitives_rtc._compile_krylov_primitives_with_handoff,
                    source_fragment,
                ) as line_interrupt,
                pytest.raises(KeyboardInterrupt),
            ):
                krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                    compile_then_interrupt,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert line_interrupt.fired

        assert krylov_primitives_rtc._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is None
        assert compiler_calls == int(phase != "after_isolated_set")
        assert handoff.kernel is (None if not published else published[0])
        if handoff.kernel is not None:
            owned_kernel = handoff.kernel
            unload_calls = runtime.unload_calls
            owned_kernel.close()
            owned_kernel.close()
            assert runtime.unload_calls == unload_calls + 1
            assert handoff.kernel is None

        direct_kernel = compile_hip_rtc_krylov_primitives_kernel(
            runtime,
            "gfx1030",
        )
        assert krylov_primitives_rtc._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is direct_kernel
        unload_calls = runtime.unload_calls
        direct_kernel.close()
        direct_kernel.close()
        assert runtime.unload_calls == unload_calls + 1
    finally:
        krylov_primitives_rtc._KERNEL_HANDOFF.reset(context_token)


def test_same_handoff_concurrent_publication_is_one_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtimes = (FakeLoadedRuntime(), FakeLoadedRuntime())
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    publish_barrier = threading.Barrier(2)
    handoff_type = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff
    original_publish = handoff_type.publish_module_owner

    def synchronized_publish(target: Any, owner: Any) -> None:
        publish_barrier.wait(timeout=5.0)
        original_publish(target, owner)

    monkeypatch.setattr(
        handoff_type,
        "publish_module_owner",
        synchronized_publish,
    )
    kernels: list[Any] = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def compile_one(runtime: FakeLoadedRuntime) -> None:
        try:
            kernel = krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                compile_hip_rtc_krylov_primitives_kernel,
                handoff,
                runtime,
                "gfx1030",
                None,
            )
        except BaseException as exc:
            with result_lock:
                errors.append(exc)
        else:
            with result_lock:
                kernels.append(kernel)

    threads = [
        threading.Thread(target=compile_one, args=(runtime,)) for runtime in runtimes
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()

    assert len(kernels) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HipRtcKrylovPrimitivesError)
    assert errors[0].code == "hip_rtc_krylov_primitives_kernel_handoff_invalid"
    assert sum(runtime.load_calls for runtime in runtimes) == 1
    assert handoff._publication_state == "published"
    assert handoff.kernel is kernels[0]
    kernels[0].close()
    assert sum(runtime.unload_calls for runtime in runtimes) == 1
    assert handoff.kernel is None


def test_module_cleanup_owner_is_published_before_native_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    native_load = runtime._load
    observed_owner: list[Any] = []

    def assert_prepublished(output: Any, image: Any) -> int:
        assert handoff._cell is not None
        owner = handoff._cell.owner
        assert type(owner) is (
            krylov_primitives_rtc._HipRtcKrylovPrimitivesModuleCleanupOwner
        )
        assert not owner.owns_module
        observed_owner.append(owner)
        return native_load(output, image)

    monkeypatch.setattr(runtime, "_load", assert_prepublished)
    kernel = krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
        compile_hip_rtc_krylov_primitives_kernel,
        handoff,
        runtime,
        "gfx1030",
        None,
    )
    stale_owner = observed_owner[0]
    assert handoff.kernel is kernel
    assert stale_owner._ownership_cell is kernel._ownership_cell is handoff._cell
    assert not stale_owner.owns_module
    stale_owner.close()
    stale_owner.close()
    assert runtime.unload_calls == 0
    kernel.close()
    kernel.close()
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_published_empty_owner_close_prevents_native_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    owner_type = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff
    original_publish = owner_type.publish_module_owner

    def publish_then_close(target: Any, owner: Any) -> None:
        original_publish(target, owner)
        owner.close()

    monkeypatch.setattr(owner_type, "publish_module_owner", publish_then_close)
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    with pytest.raises(HipRtcKrylovPrimitivesError) as caught:
        krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
            compile_hip_rtc_krylov_primitives_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert caught.value.code == ("hip_rtc_krylov_primitives_module_ownership_invalid")
    assert runtime.load_calls == 0
    assert runtime.unload_calls == 0
    assert handoff.kernel is None
    assert handoff._cell is not None
    assert handoff._cell.owner is None
    assert handoff._cell.preowner is None
    assert handoff._cell.unload_disposition == "terminal"
    assert _pointer_value(handoff._cell.module) is None


def test_terminal_owner_store_interruption_cannot_be_stolen_by_preowner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    kernel = krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
        compile_hip_rtc_krylov_primitives_kernel,
        handoff,
        runtime,
        "gfx1030",
        None,
    )
    assert handoff._cell is not None
    stale_owner = handoff._cell.preowner
    assert type(stale_owner) is (
        krylov_primitives_rtc._HipRtcKrylovPrimitivesModuleCleanupOwner
    )

    with (
        _SingleFireAfterAttributeStoreInterrupt(
            type(kernel)._finish_unload_success,
            "cell.owner = None",
            "owner",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        kernel.close()
    assert interruption.fired
    assert runtime.unload_calls == 1
    stale_owner.close()
    assert runtime.unload_calls == 1
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 1
    assert handoff.kernel is None
    assert handoff._cell.owner is None
    assert handoff._cell.preowner is None
    assert handoff._cell.unload_disposition == "terminal"
    assert _pointer_value(handoff._cell.module) is None


@pytest.mark.parametrize("phase", ("before_transfer", "after_transfer"))
def test_ownership_transfer_interruption_retains_exactly_one_authority(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    if phase == "before_transfer":
        interruption_context: Any = _SingleFireRtcLineInterrupt(
            krylov_primitives_rtc._transfer_krylov_primitives_module_ownership,
            "cell.owner = kernel",
        )
    else:
        interruption_context = _SingleFireAfterAttributeStoreInterrupt(
            krylov_primitives_rtc._transfer_krylov_primitives_module_ownership,
            "cell.owner = kernel",
            "owner",
        )

    with interruption_context as interruption, pytest.raises(KeyboardInterrupt):
        krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
            compile_hip_rtc_krylov_primitives_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert interruption.fired
    assert handoff._cell is not None
    if phase == "before_transfer":
        assert handoff._cell.owner is None
        assert handoff.kernel is None
        assert runtime.unload_calls == 1
    else:
        kernel = handoff.kernel
        assert type(kernel) is (krylov_primitives_rtc.HipRtcKrylovPrimitivesKernel)
        stale_owner = handoff._cell.preowner
        assert stale_owner is not None
        assert not stale_owner.owns_module
        stale_owner.close()
        assert runtime.unload_calls == 0
        kernel.close()
        assert runtime.unload_calls == 1
        assert handoff.kernel is None


def test_preowner_unload_serializes_with_ownership_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    unload_entered = threading.Event()
    release_unload = threading.Event()
    native_unload = runtime._unload

    def blocking_unload(module: Any) -> int:
        unload_entered.set()
        assert release_unload.wait(timeout=5.0)
        return native_unload(module)

    monkeypatch.setattr(runtime, "_unload", blocking_unload)
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    original_transfer = (
        krylov_primitives_rtc._transfer_krylov_primitives_module_ownership
    )

    def coordinated_transfer(owner: Any, kernel: Any) -> None:
        cleanup_errors: list[BaseException] = []
        transfer_errors: list[BaseException] = []
        transfer_started = threading.Event()

        def unload_preowner() -> None:
            try:
                owner.close()
            except BaseException as exc:
                cleanup_errors.append(exc)

        def transfer_owner() -> None:
            transfer_started.set()
            try:
                original_transfer(owner, kernel)
            except BaseException as exc:
                transfer_errors.append(exc)

        cleanup_thread = threading.Thread(target=unload_preowner)
        transfer_thread = threading.Thread(target=transfer_owner)
        cleanup_thread.start()
        transfer_was_blocked = False
        try:
            assert unload_entered.wait(timeout=5.0)
            transfer_thread.start()
            assert transfer_started.wait(timeout=5.0)
            transfer_thread.join(timeout=0.05)
            transfer_was_blocked = transfer_thread.is_alive()
        finally:
            release_unload.set()
            cleanup_thread.join(timeout=5.0)
            if transfer_thread.ident is not None:
                transfer_thread.join(timeout=5.0)
        assert transfer_was_blocked
        assert not cleanup_thread.is_alive()
        assert not transfer_thread.is_alive()
        assert cleanup_errors == []
        assert len(transfer_errors) == 1
        assert isinstance(
            transfer_errors[0],
            krylov_primitives_rtc.HipRtcKrylovPrimitivesError,
        )
        assert transfer_errors[0].code == (
            "hip_rtc_krylov_primitives_module_ownership_invalid"
        )
        raise transfer_errors[0]

    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_transfer_krylov_primitives_module_ownership",
        coordinated_transfer,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    with pytest.raises(krylov_primitives_rtc.HipRtcKrylovPrimitivesError) as caught:
        krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
            compile_hip_rtc_krylov_primitives_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert caught.value.code == ("hip_rtc_krylov_primitives_module_ownership_invalid")
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_known_failed_preowner_unload_remains_transferable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    original_transfer = (
        krylov_primitives_rtc._transfer_krylov_primitives_module_ownership
    )

    def fail_once_then_transfer(owner: Any, kernel: Any) -> None:
        with pytest.raises(krylov_primitives_rtc.HipRtcKrylovPrimitivesError) as failed:
            owner.close()
        assert failed.value.code == ("hip_rtc_krylov_primitives_module_cleanup_failed")
        assert owner.owns_module
        assert owner._ownership_cell.unload_disposition == "live"
        original_transfer(owner, kernel)

    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_transfer_krylov_primitives_module_ownership",
        fail_once_then_transfer,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    kernel = krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
        compile_hip_rtc_krylov_primitives_kernel,
        handoff,
        runtime,
        "gfx1030",
        None,
    )
    assert handoff.kernel is kernel
    assert runtime.unload_calls == 1
    kernel.close()
    assert runtime.unload_calls == 2
    assert handoff.kernel is None


@pytest.mark.parametrize(
    "phase",
    ("after_native_load", "after_status_store", "at_first_status_check"),
)
def test_module_load_interruptions_recover_preallocated_module_owner(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    if phase == "after_native_load":
        native_load = runtime._load

        def load_then_interrupt(output: Any, image: Any) -> int:
            assert native_load(output, image) == 0
            raise KeyboardInterrupt("injected after native module load")

        monkeypatch.setattr(runtime, "_load", load_then_interrupt)

    sentinel_target = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    sentinel = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoffFrame(
        sentinel_target
    )
    context_token = krylov_primitives_rtc._KERNEL_HANDOFF.set(sentinel)
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    try:
        if phase == "after_status_store":
            with (
                _SingleFireAfterStoreInterrupt(
                    krylov_primitives_rtc._compile_krylov_primitives_impl,
                    "status = runtime.load_module_into",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                    compile_hip_rtc_krylov_primitives_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        elif phase == "at_first_status_check":
            with (
                _SingleFireRtcLineInterrupt(
                    krylov_primitives_rtc._compile_krylov_primitives_impl,
                    "if status != 0 or not module.value:",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                    compile_hip_rtc_krylov_primitives_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        else:
            with pytest.raises(KeyboardInterrupt):
                krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
                    compile_hip_rtc_krylov_primitives_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )

        assert runtime.load_calls == 1
        assert runtime.unload_calls == 1
        assert handoff.kernel is None
        assert krylov_primitives_rtc._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is None
    finally:
        krylov_primitives_rtc._KERNEL_HANDOFF.reset(context_token)


@pytest.mark.parametrize(
    "phase",
    ("before_cleanup_helper_call", "at_cleanup_helper_first_line"),
)
def test_prepublished_module_owner_survives_cleanup_entry_interruption(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(
        missing_symbol=HIP_RTC_KRYLOV_FILL_SYMBOL,
    )
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = krylov_primitives_rtc._HipRtcKrylovPrimitivesKernelHandoff()
    if phase == "before_cleanup_helper_call":
        trace_target = krylov_primitives_rtc._compile_krylov_primitives_impl
        source_fragment = "_cleanup_loaded_module("
    else:
        trace_target = krylov_primitives_rtc._cleanup_loaded_module
        source_fragment = "primary_log = ("

    with (
        _SingleFireRtcLineInterrupt(
            trace_target,
            source_fragment,
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        krylov_primitives_rtc._compile_krylov_primitives_with_handoff(
            compile_hip_rtc_krylov_primitives_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.function_symbols == [
        HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL,
        HIP_RTC_KRYLOV_FILL_SYMBOL,
    ]
    assert runtime.unload_calls == 0

    owner = handoff.kernel
    assert type(owner) is (
        krylov_primitives_rtc._HipRtcKrylovPrimitivesModuleCleanupOwner
    )
    assert owner.owns_module
    assert not owner.closed
    owner.close()
    owner.close()
    assert owner.closed
    assert not owner.owns_module
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_direct_compiler_recovers_cleanup_entry_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(missing_symbol=HIP_RTC_KRYLOV_FILL_SYMBOL)
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with (
        _SingleFireRtcLineInterrupt(
            krylov_primitives_rtc._compile_krylov_primitives_impl,
            "_cleanup_loaded_module(",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_krylov_primitives_kernel(runtime, "gfx1030")
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.unload_calls == 1


def test_direct_compiler_reclaims_kernel_after_transfer_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with (
        _SingleFireAfterAttributeStoreInterrupt(
            krylov_primitives_rtc._transfer_krylov_primitives_module_ownership,
            "cell.owner = kernel",
            "owner",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_krylov_primitives_kernel(runtime, "gfx1030")
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.unload_calls == 1


def test_reduction_output_count_has_exact_int32_capacity_contract() -> None:
    assert reduction_output_count(1) == 1
    assert reduction_output_count(511) == 1
    assert reduction_output_count(512) == 1
    assert reduction_output_count(513) == 2
    assert reduction_output_count(2**31 - 1) == 4_194_304
    for value in (0, -1, True, 1.0, 2**31):
        with pytest.raises(HipRtcKrylovPrimitivesError) as error:
            reduction_output_count(value)  # type: ignore[arg-type]
        assert error.value.code == "hip_rtc_krylov_primitives_launch_contract_invalid"


def test_int32_max_launch_geometry_matches_overflow_safe_device_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    kernel.launch_fill(100, 2**31 - 1, 0.0, 1, 2)
    kernel.launch_sum_stage(101, 2**31 - 1, 3, 4, 5)
    assert [record["grid"] for record in runtime.launch_records] == [
        (8_388_608, 1, 1),
        (4_194_304, 1, 1),
    ]
    assert [record["arguments"][0] for record in runtime.launch_records] == [
        2**31 - 1,
        2**31 - 1,
    ]
    kernel.acknowledge_stream_completion(100)
    kernel.acknowledge_stream_completion(101)
    kernel.close()


def test_nine_launch_methods_pack_exact_abis_geometry_and_safe_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    kernel.launch_prepare_positive_jacobi(100, 513, 1000, 1, 2, 3, 4, 5)
    kernel.launch_fill(101, 513, -0.0, 6, 7)
    kernel.launch_affine(102, 513, 2.5, 8, -3.0, 9, 8, 10)
    kernel.launch_apply_jacobi(103, 513, 11, 12, 13, 14)
    kernel.launch_dot_stage(104, 1025, 15, 16, 17, 18)
    kernel.launch_sum_stage(105, 513, 19, 20, 21)
    kernel.launch_lassq_stage(106, 512, 22, 23, 24)
    kernel.launch_lassq_combine_stage(107, 1, 25, 26, 27)
    kernel.launch_lassq_finalize(108, 28, 29, 30)
    assert runtime.launch_records == [
        {
            "symbol": SYMBOLS[0],
            "grid": (3, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 100,
            "arguments": (513, 1000, 1, 2, 3, 4, 5),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[1],
            "grid": (3, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 101,
            "arguments": (513, -0.0, 6, 7),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[2],
            "grid": (3, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 102,
            "arguments": (513, 2.5, 8, -3.0, 9, 8, 10),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[3],
            "grid": (3, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 103,
            "arguments": (513, 11, 12, 13, 14),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[4],
            "grid": (3, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 104,
            "arguments": (1025, 15, 16, 17, 18),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[5],
            "grid": (2, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 105,
            "arguments": (513, 19, 20, 21),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[6],
            "grid": (1, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 106,
            "arguments": (512, 22, 23, 24),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[7],
            "grid": (1, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 107,
            "arguments": (1, 25, 26, 27),
            "extra": None,
        },
        {
            "symbol": SYMBOLS[8],
            "grid": (1, 1, 1),
            "block": (256, 1, 1),
            "shared": 0,
            "stream": 108,
            "arguments": (28, 29, 30),
            "extra": None,
        },
    ]
    for stream in range(100, 109):
        kernel.acknowledge_stream_completion(stream)
    kernel.close()


def test_launch_preflight_rejects_counts_pointers_and_nonfinite_scalars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    invalid_calls = (
        lambda: kernel.launch_prepare_positive_jacobi(100, 10, 9, 1, 2, 3, 4, 5),
        lambda: kernel.launch_fill(100, 0, 1.0, 1, 2),
        lambda: kernel.launch_fill(100, 1, float("nan"), 1, 2),
        lambda: kernel.launch_affine(100, 1, float("inf"), 1, 1.0, 2, 3, 4),
        lambda: kernel.launch_affine(100, 1, True, 1, 1.0, 2, 3, 4),
        lambda: kernel.launch_dot_stage(0, 1, 1, 2, 3, 4),
        lambda: kernel.launch_sum_stage(100, True, 1, 2, 3),
        lambda: kernel.launch_lassq_finalize(100, 0, 2, 3),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcKrylovPrimitivesError) as error:
            call()
        assert error.value.code == "hip_rtc_krylov_primitives_launch_contract_invalid"
    uintptr_overflow = 1 << (8 * ctypes.sizeof(ctypes.c_void_p))
    with pytest.raises(HipRtcKrylovPrimitivesError) as overflow:
        kernel.launch_apply_jacobi(100, 1, uintptr_overflow, 2, 3, 4)
    assert overflow.value.code == "hip_rtc_krylov_primitives_launch_contract_invalid"
    assert runtime.launch_records == []
    kernel.close()


@pytest.mark.parametrize("missing_symbol", SYMBOLS)
def test_missing_any_fixed_symbol_unloads_module(
    monkeypatch: pytest.MonkeyPatch,
    missing_symbol: str,
) -> None:
    runtime = FakeLoadedRuntime(missing_symbol=missing_symbol)
    with pytest.raises(HipRtcKrylovPrimitivesError) as error:
        _compile_fake(monkeypatch, runtime=runtime)
    assert error.value.code == "hip_rtc_krylov_primitives_symbol_missing"
    assert runtime.unload_calls == 1


def test_compile_and_load_failures_release_native_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi(
        compile_status=6,
        compile_log="Krylov primitive compile failure",
    )
    monkeypatch.setattr(
        krylov_primitives_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with pytest.raises(HipRtcKrylovPrimitivesError) as compile_error:
        compile_hip_rtc_krylov_primitives_kernel(
            FakeLoadedRuntime(),
            "gfx1030",
        )
    assert compile_error.value.code == "hip_rtc_compile_failed"
    assert compile_error.value.compile_log == "Krylov primitive compile failure"
    assert fake_rtc.destroy_calls == 1

    runtime = FakeLoadedRuntime(load_status=11)
    with pytest.raises(HipRtcKrylovPrimitivesError) as load_error:
        _compile_fake(monkeypatch, runtime=runtime)
    assert load_error.value.code == "hip_rtc_krylov_primitives_module_load_failed"
    assert runtime.unload_calls == 1


def test_failed_load_nonzero_cleanup_preserves_owner_for_known_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11, unload_statuses=(9, 0))
    with pytest.raises(HipRtcKrylovPrimitivesError) as caught:
        _compile_fake(monkeypatch, runtime=runtime)
    error = caught.value
    assert error.code == "hip_rtc_krylov_primitives_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert not owner.closed
    assert runtime.unload_calls == 1

    owner.close()
    owner.close()
    assert owner.closed
    assert runtime.unload_calls == 2


def test_failed_load_cleanup_side_effect_exception_is_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11)
    native_unload = runtime._unload

    def unload_then_raise(module: Any) -> int:
        assert native_unload(module) == 0
        raise RuntimeError("interrupt after native module unload")

    monkeypatch.setattr(runtime, "_unload", unload_then_raise)
    with pytest.raises(HipRtcKrylovPrimitivesError) as caught:
        _compile_fake(monkeypatch, runtime=runtime)
    error = caught.value
    assert error.code == "hip_rtc_krylov_primitives_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert not owner.closed
    assert runtime.unload_calls == 1

    with pytest.raises(HipRtcKrylovPrimitivesError) as uncertain:
        owner.close()
    assert uncertain.value.code == (
        "hip_rtc_krylov_primitives_module_cleanup_outcome_uncertain"
    )
    assert uncertain.value.cleanup_owner is owner
    assert not owner.closed
    assert runtime.unload_calls == 1


def test_symbol_bind_cleanup_failure_preserves_retryable_module_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(
        missing_symbol=HIP_RTC_KRYLOV_FILL_SYMBOL,
        unload_statuses=(9, 8, 0),
    )
    with pytest.raises(HipRtcKrylovPrimitivesError) as caught:
        _compile_fake(monkeypatch, runtime=runtime)
    error = caught.value
    assert error.code == "hip_rtc_krylov_primitives_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert not owner.closed
    assert runtime.unload_calls == 1

    with pytest.raises(HipRtcKrylovPrimitivesError) as retry:
        owner.close()
    assert retry.value.cleanup_owner is owner
    assert not owner.closed
    assert runtime.unload_calls == 2

    owner.close()
    owner.close()
    assert owner.closed
    assert runtime.unload_calls == 3


def test_failed_close_preserves_owner_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    with pytest.raises(HipRtcKrylovPrimitivesError) as error:
        kernel.close()
    assert error.value.code == "hip_rtc_krylov_primitives_module_unload_failed"
    assert not kernel.closed
    kernel.launch_fill(100, 1, 0.0, 1, 2)
    with pytest.raises(HipRtcKrylovPrimitivesError) as pending:
        kernel.close()
    assert pending.value.code == "hip_rtc_krylov_primitives_completion_fence_required"
    assert runtime.unload_calls == 1
    kernel.acknowledge_stream_completion(100)
    kernel.close()
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 2
    with pytest.raises(HipRtcKrylovPrimitivesError) as closed:
        kernel.launch_fill(100, 1, 0.0, 1, 2)
    assert closed.value.code == "hip_rtc_krylov_primitives_kernel_closed"


@pytest.mark.parametrize(
    ("phase", "error_type"),
    [
        ("known_success_finalize", KeyboardInterrupt),
        ("runtime_side_effect", KeyboardInterrupt),
        ("runtime_side_effect", RuntimeError),
        ("before_call", KeyboardInterrupt),
    ],
)
def test_unload_interruption_never_retries_uncertain_or_known_success(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    error_type: type[BaseException],
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    runtime_api_type = type(kernel._runtime)
    original_unload = runtime_api_type.unload
    injected_error = error_type(f"injected {phase} unload interruption")
    injected = False
    original_finish = type(kernel)._finish_unload_success

    def interrupting_unload(runtime_api: Any, module: Any) -> int:
        nonlocal injected
        if not injected:
            injected = True
            if phase == "before_call":
                raise injected_error
            status = original_unload(runtime_api, module)
            assert status == 0
            assert runtime.unload_calls == 1
            raise injected_error
        return original_unload(runtime_api, module)

    def interrupting_finish(target: Any) -> None:
        nonlocal injected
        if not injected:
            injected = True
            assert target._unload_disposition == "external_unload_succeeded"
            assert runtime.unload_calls == 1
            raise injected_error
        original_finish(target)

    if phase == "known_success_finalize":
        monkeypatch.setattr(
            type(kernel),
            "_finish_unload_success",
            interrupting_finish,
        )
    else:
        monkeypatch.setattr(runtime_api_type, "unload", interrupting_unload)
    if error_type is RuntimeError:
        with pytest.raises(HipRtcKrylovPrimitivesError) as first:
            kernel.close()
        assert first.value.code == ("hip_rtc_krylov_primitives_module_unload_failed")
        assert isinstance(first.value.__cause__, RuntimeError)
    else:
        with pytest.raises(KeyboardInterrupt) as first:
            kernel.close()
        assert first.value is injected_error

    assert injected
    if phase == "known_success_finalize":
        assert kernel._unload_disposition == "external_unload_succeeded"
        assert runtime.unload_calls == 1
        kernel.close()
        kernel.close()
        assert kernel.closed
        assert runtime.unload_calls == 1
        assert _pointer_value(kernel._module) is None
        assert kernel._functions == {}
    else:
        assert kernel._unload_disposition == "unload_outcome_uncertain"
        expected_calls = int(phase == "runtime_side_effect")
        assert runtime.unload_calls == expected_calls
        with pytest.raises(HipRtcKrylovPrimitivesError) as uncertain:
            kernel.close()
        assert uncertain.value.code == (
            "hip_rtc_krylov_primitives_module_unload_outcome_uncertain"
        )
        assert not kernel.closed
        assert runtime.unload_calls == expected_calls
        assert _pointer_value(kernel._module) == 513


def test_native_launch_failure_is_wrapped_without_closing_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(launch_status=12)
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    with pytest.raises(HipRtcKrylovPrimitivesError) as error:
        kernel.launch_lassq_finalize(100, 1, 2, 3)
    assert error.value.code == "hip_rtc_krylov_primitives_kernel_launch_failed"
    assert not kernel.closed
    assert len(runtime.launch_records) == 1
    kernel.close()


def test_close_requires_exact_completion_fence_for_every_launched_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    kernel.launch_fill(100, 1, 0.0, 1, 2)
    kernel.launch_fill(101, 1, 0.0, 3, 4)
    assert kernel.pending_stream_count == 2

    with pytest.raises(HipRtcKrylovPrimitivesError) as pending:
        kernel.close()
    assert pending.value.code == "hip_rtc_krylov_primitives_completion_fence_required"
    assert runtime.unload_calls == 0
    with pytest.raises(HipRtcKrylovPrimitivesError) as unknown:
        kernel.acknowledge_stream_completion(102)
    assert unknown.value.code == "hip_rtc_krylov_primitives_launch_contract_invalid"

    kernel.acknowledge_stream_completion(100)
    with pytest.raises(HipRtcKrylovPrimitivesError):
        kernel.close()
    kernel.acknowledge_stream_completion(101)
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 1


def test_actual_hiprtc_compiles_all_fixed_symbols(tmp_path: Path) -> None:
    candidates = sorted(
        {
            *Path("/opt").glob("rocm*/lib/libhiprtc.so*"),
            *Path("/opt").glob("rocm*/lib64/libhiprtc.so*"),
        },
        key=str,
    )
    library = next((path for path in candidates if path.is_file()), None)
    if library is None:
        pytest.skip("a native libhiprtc binary is unavailable")
    hiprtc = krylov_primitives_rtc._load_hiprtc_api(library)
    status, major, minor = hiprtc.version()
    assert status == 0
    assert major >= 0 and minor >= 0
    code_object, compile_log = krylov_primitives_rtc._compile_fixed_source(
        hiprtc,
        krylov_primitives_rtc._fixed_source(),
        (
            "--offload-arch=gfx1030",
            "-O3",
            "-std=c++17",
            "-ffp-contract=off",
        ),
    )
    assert code_object
    assert compile_log == ""

    llvm_nm = next(
        (
            executable
            for executable in (
                shutil.which("llvm-nm"),
                "/opt/rocm/lib/llvm/bin/llvm-nm",
                "/opt/rocm-6.0.2/lib/llvm/bin/llvm-nm",
            )
            if executable and Path(executable).is_file()
        ),
        None,
    )
    if llvm_nm is None:
        pytest.skip("HIPRTC compiled, but llvm-nm is unavailable")
    code_path = tmp_path / "krylov-primitives.co"
    code_path.write_bytes(code_object)
    symbols = subprocess.run(
        [llvm_nm, str(code_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    for symbol in SYMBOLS:
        assert symbol in symbols
