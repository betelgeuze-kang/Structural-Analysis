from __future__ import annotations

import ctypes
from dataclasses import FrozenInstanceError, replace
import dis
import inspect
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import free_space_rtc
from structural_analysis.engine_v2.assembly_backend.free_space_rtc import (
    HIP_RTC_FREE_SPACE_BLOCK_SIZE,
    HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
    HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
    HipRtcFreeSpaceError,
    compile_hip_rtc_free_space_operator_kernel,
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
    / "engine_v2_free_space_operator_v1.hip.cpp"
)


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
        self.options: tuple[str, ...] = ()
        self.destroy_calls = 0

    def error_string(self, status: int) -> str:
        return f"fake HIPRTC status {status}"

    def version(self) -> tuple[int, int, int]:
        return 0, 9, 1

    def create_program(self, source: bytes) -> tuple[int, ctypes.c_void_p]:
        self.created_source = source
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
        return b"fake-free-space-operator-code-object-v1"

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
        handles = {
            HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL: 769,
            HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL: 770,
            HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL: 771,
        }
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(
            handles[decoded]
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
        function_value = _pointer_value(function)
        shape = {
            769: (4, 9),
            770: (3, 10),
            771: (2, 4),
        }[function_value]
        scalar_count, pointer_count = shape
        scalars = tuple(
            ctypes.cast(
                parameters[index],
                ctypes.POINTER(ctypes.c_int),
            ).contents.value
            for index in range(scalar_count)
        )
        pointers = tuple(
            ctypes.cast(
                parameters[scalar_count + index],
                ctypes.POINTER(ctypes.c_void_p),
            ).contents.value
            for index in range(pointer_count)
        )
        self.launch_records.append(
            {
                "function": function_value,
                "grid": (grid_x, grid_y, grid_z),
                "block": (block_x, block_y, block_z),
                "shared": shared,
                "stream": _pointer_value(stream),
                "scalars": scalars,
                "pointers": pointers,
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
                    raise KeyboardInterrupt(
                        "injected after free-space ownership transfer"
                    )
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    return (
        compile_hip_rtc_free_space_operator_kernel(runtime, "gfx1030"),
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


def test_fixed_source_compile_binds_three_symbols_and_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, fake_rtc, runtime = _compile_fake(monkeypatch)
    identity = kernel.identity
    manifest = identity.to_dict()
    assert fake_rtc.created_source == KERNEL_SOURCE.read_bytes()
    assert fake_rtc.options == (
        "--offload-arch=gfx1030",
        "-O3",
        "-std=c++17",
    )
    assert runtime.function_symbols == [
        HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    ]
    assert identity.kernel_symbols == tuple(runtime.function_symbols)
    assert manifest["kernel_symbols"] == {
        "materialize": HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        "residual_direction": HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        "gather_jvp": HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    }
    assert manifest["launch_geometry"] == {"block_size": 256}
    assert identity.source_sha256 == free_space_rtc._sha256_bytes(
        KERNEL_SOURCE.read_bytes()
    )
    assert identity.code_object_byte_length > 0
    assert identity.identity_hash.startswith("sha256:")
    assert not {
        "handle",
        "pointer",
        "module",
        "function",
        "stream",
    } & _all_keys(manifest)
    with pytest.raises(FrozenInstanceError):
        identity.architecture = "gfx90a"

    forged = replace(identity, materialize_symbol="forged", identity_hash="")
    forged = replace(
        forged,
        identity_hash=canonical_hash(
            free_space_rtc._identity_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcFreeSpaceError) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_free_space_identity_invalid"
    kernel.close()


def test_public_surface_and_fixed_source_contract() -> None:
    assert tuple(
        inspect.signature(compile_hip_rtc_free_space_operator_kernel).parameters
    ) == ("loaded_runtime", "architecture", "hiprtc_library")
    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    symbols = (
        HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    )
    assert source.count('extern "C" __global__ void') == 3
    assert source.count("atomicCAS") == 1
    assert source.count("#pragma clang fp contract(off)") == 1
    assert "value == 0.0 ? 0.0 : value" in source
    assert "full_direction[global_index] = 0.0;" in source
    assert "const double residual = load - internal_force;" in source
    assert "const int reduced_row = global_to_free[global_index];" in source
    assert "*error_flag" not in source
    for symbol in symbols:
        assert source.count(symbol) == 1
    for forbidden in (
        "#include",
        "hipLaunchKernelGGL",
        "hipMalloc",
        "hipMemcpy",
        "atomicAdd",
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    sentinel_target = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    sentinel = free_space_rtc._HipRtcFreeSpaceKernelHandoffFrame(sentinel_target)
    context_token = free_space_rtc._KERNEL_HANDOFF.set(sentinel)
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    published: list[Any] = []
    compiler_calls = 0
    interruption = KeyboardInterrupt(f"interrupt free-space handoff at {phase}")

    def compile_then_interrupt(
        loaded_runtime: Any,
        architecture: str,
        hiprtc_library: str | Path | None,
    ) -> Any:
        nonlocal compiler_calls
        compiler_calls += 1
        kernel = compile_hip_rtc_free_space_operator_kernel(
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
                free_space_rtc._compile_free_space_operator_with_handoff(
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
                    free_space_rtc._compile_free_space_operator_with_handoff,
                    source_fragment,
                ) as line_interrupt,
                pytest.raises(KeyboardInterrupt),
            ):
                free_space_rtc._compile_free_space_operator_with_handoff(
                    compile_then_interrupt,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert line_interrupt.fired

        assert free_space_rtc._KERNEL_HANDOFF.get() is sentinel
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

        direct_kernel = compile_hip_rtc_free_space_operator_kernel(
            runtime,
            "gfx1030",
        )
        assert free_space_rtc._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is direct_kernel
        unload_calls = runtime.unload_calls
        direct_kernel.close()
        direct_kernel.close()
        assert runtime.unload_calls == unload_calls + 1
    finally:
        free_space_rtc._KERNEL_HANDOFF.reset(context_token)


def test_same_handoff_concurrent_publication_is_one_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtimes = (FakeLoadedRuntime(), FakeLoadedRuntime())
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    publish_barrier = threading.Barrier(2)
    handoff_type = free_space_rtc._HipRtcFreeSpaceKernelHandoff
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
            kernel = free_space_rtc._compile_free_space_operator_with_handoff(
                compile_hip_rtc_free_space_operator_kernel,
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
    assert isinstance(errors[0], HipRtcFreeSpaceError)
    assert errors[0].code == "hip_rtc_free_space_kernel_handoff_invalid"
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    native_load = runtime._load
    observed_owner: list[Any] = []

    def assert_prepublished(output: Any, image: Any) -> int:
        assert handoff._cell is not None
        owner = handoff._cell.owner
        assert type(owner) is free_space_rtc._HipRtcFreeSpaceModuleCleanupOwner
        assert not owner.owns_module
        observed_owner.append(owner)
        return native_load(output, image)

    monkeypatch.setattr(runtime, "_load", assert_prepublished)
    kernel = free_space_rtc._compile_free_space_operator_with_handoff(
        compile_hip_rtc_free_space_operator_kernel,
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    owner_type = free_space_rtc._HipRtcFreeSpaceKernelHandoff
    original_publish = owner_type.publish_module_owner

    def publish_then_close(target: Any, owner: Any) -> None:
        original_publish(target, owner)
        owner.close()

    monkeypatch.setattr(owner_type, "publish_module_owner", publish_then_close)
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    with pytest.raises(HipRtcFreeSpaceError) as caught:
        free_space_rtc._compile_free_space_operator_with_handoff(
            compile_hip_rtc_free_space_operator_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert caught.value.code == "hip_rtc_free_space_module_ownership_invalid"
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    kernel = free_space_rtc._compile_free_space_operator_with_handoff(
        compile_hip_rtc_free_space_operator_kernel,
        handoff,
        runtime,
        "gfx1030",
        None,
    )
    assert handoff._cell is not None
    stale_owner = handoff._cell.preowner
    assert type(stale_owner) is free_space_rtc._HipRtcFreeSpaceModuleCleanupOwner

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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    if phase == "before_transfer":
        interruption_context: Any = _SingleFireRtcLineInterrupt(
            free_space_rtc._transfer_free_space_module_ownership,
            "cell.owner = kernel",
        )
    else:
        interruption_context = _SingleFireAfterAttributeStoreInterrupt(
            free_space_rtc._transfer_free_space_module_ownership,
            "cell.owner = kernel",
            "owner",
        )

    with interruption_context as interruption, pytest.raises(KeyboardInterrupt):
        free_space_rtc._compile_free_space_operator_with_handoff(
            compile_hip_rtc_free_space_operator_kernel,
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
        assert type(kernel) is free_space_rtc.HipRtcFreeSpaceOperatorKernel
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    original_transfer = free_space_rtc._transfer_free_space_module_ownership

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
        assert isinstance(transfer_errors[0], HipRtcFreeSpaceError)
        assert transfer_errors[0].code == (
            "hip_rtc_free_space_module_ownership_invalid"
        )
        raise transfer_errors[0]

    monkeypatch.setattr(
        free_space_rtc,
        "_transfer_free_space_module_ownership",
        coordinated_transfer,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    with pytest.raises(HipRtcFreeSpaceError) as caught:
        free_space_rtc._compile_free_space_operator_with_handoff(
            compile_hip_rtc_free_space_operator_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert caught.value.code == "hip_rtc_free_space_module_ownership_invalid"
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_known_failed_preowner_unload_remains_transferable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    original_transfer = free_space_rtc._transfer_free_space_module_ownership

    def fail_once_then_transfer(owner: Any, kernel: Any) -> None:
        with pytest.raises(HipRtcFreeSpaceError) as failed:
            owner.close()
        assert failed.value.code == "hip_rtc_free_space_module_cleanup_failed"
        assert owner.owns_module
        assert owner._ownership_cell.unload_disposition == "live"
        original_transfer(owner, kernel)

    monkeypatch.setattr(
        free_space_rtc,
        "_transfer_free_space_module_ownership",
        fail_once_then_transfer,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    kernel = free_space_rtc._compile_free_space_operator_with_handoff(
        compile_hip_rtc_free_space_operator_kernel,
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
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    if phase == "after_native_load":
        native_load = runtime._load

        def load_then_interrupt(output: Any, image: Any) -> int:
            assert native_load(output, image) == 0
            raise KeyboardInterrupt("injected after native module load")

        monkeypatch.setattr(runtime, "_load", load_then_interrupt)

    sentinel_target = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    sentinel = free_space_rtc._HipRtcFreeSpaceKernelHandoffFrame(sentinel_target)
    context_token = free_space_rtc._KERNEL_HANDOFF.set(sentinel)
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    try:
        if phase == "after_status_store":
            with (
                _SingleFireAfterStoreInterrupt(
                    free_space_rtc._compile_free_space_operator_impl,
                    "status = runtime.load_module_into",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                free_space_rtc._compile_free_space_operator_with_handoff(
                    compile_hip_rtc_free_space_operator_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        elif phase == "at_first_status_check":
            with (
                _SingleFireRtcLineInterrupt(
                    free_space_rtc._compile_free_space_operator_impl,
                    "if status != 0 or not module.value:",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                free_space_rtc._compile_free_space_operator_with_handoff(
                    compile_hip_rtc_free_space_operator_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        else:
            with pytest.raises(KeyboardInterrupt):
                free_space_rtc._compile_free_space_operator_with_handoff(
                    compile_hip_rtc_free_space_operator_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )

        assert runtime.load_calls == 1
        assert runtime.unload_calls == 1
        assert handoff.kernel is None
        assert free_space_rtc._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is None
    finally:
        free_space_rtc._KERNEL_HANDOFF.reset(context_token)


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
        missing_symbol=HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
    )
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    handoff = free_space_rtc._HipRtcFreeSpaceKernelHandoff()
    if phase == "before_cleanup_helper_call":
        trace_target = free_space_rtc._compile_free_space_operator_impl
        source_fragment = "_cleanup_loaded_module("
    else:
        trace_target = free_space_rtc._cleanup_loaded_module
        source_fragment = "primary_log = ("

    with (
        _SingleFireRtcLineInterrupt(
            trace_target,
            source_fragment,
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        free_space_rtc._compile_free_space_operator_with_handoff(
            compile_hip_rtc_free_space_operator_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.function_symbols == [HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL]
    assert runtime.unload_calls == 0

    owner = handoff.kernel
    assert type(owner) is free_space_rtc._HipRtcFreeSpaceModuleCleanupOwner
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
    runtime = FakeLoadedRuntime(
        missing_symbol=HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
    )
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with (
        _SingleFireRtcLineInterrupt(
            free_space_rtc._compile_free_space_operator_impl,
            "_cleanup_loaded_module(",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_free_space_operator_kernel(runtime, "gfx1030")
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.unload_calls == 1


def test_direct_compiler_reclaims_kernel_after_transfer_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with (
        _SingleFireAfterAttributeStoreInterrupt(
            free_space_rtc._transfer_free_space_module_ownership,
            "cell.owner = kernel",
            "owner",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_free_space_operator_kernel(runtime, "gfx1030")
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.unload_calls == 1


def test_three_launch_methods_pack_exact_fixed_abis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    materialize_pointers = tuple(range(1001, 1010))
    kernel.launch_materialize(
        1000,
        700,
        1000,
        513,
        769,
        *materialize_pointers,
    )
    residual_pointers = tuple(range(2001, 2011))
    kernel.launch_residual_direction(
        2000,
        700,
        513,
        769,
        *residual_pointers,
    )
    gather_pointers = tuple(range(3001, 3005))
    kernel.launch_gather_jvp(
        3000,
        700,
        513,
        *gather_pointers,
    )
    assert runtime.launch_records == [
        {
            "function": 769,
            "grid": (4, 1, 1),
            "block": (HIP_RTC_FREE_SPACE_BLOCK_SIZE, 1, 1),
            "shared": 0,
            "stream": 1000,
            "scalars": (700, 1000, 513, 769),
            "pointers": materialize_pointers,
            "extra": None,
        },
        {
            "function": 770,
            "grid": (3, 1, 1),
            "block": (HIP_RTC_FREE_SPACE_BLOCK_SIZE, 1, 1),
            "shared": 0,
            "stream": 2000,
            "scalars": (700, 513, 769),
            "pointers": residual_pointers,
            "extra": None,
        },
        {
            "function": 771,
            "grid": (3, 1, 1),
            "block": (HIP_RTC_FREE_SPACE_BLOCK_SIZE, 1, 1),
            "shared": 0,
            "stream": 3000,
            "scalars": (700, 513),
            "pointers": gather_pointers,
            "extra": None,
        },
    ]
    kernel.close()


def test_launch_contracts_fail_closed_before_native_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    materialize_pointers = tuple(range(1001, 1010))
    for bad_count in (0, -1, True, 2**31):
        with pytest.raises(HipRtcFreeSpaceError) as error:
            kernel.launch_materialize(
                1000,
                bad_count,
                1000,
                513,
                769,
                *materialize_pointers,
            )
        assert error.value.code == ("hip_rtc_free_space_launch_contract_invalid")
    with pytest.raises(HipRtcFreeSpaceError):
        kernel.launch_materialize(
            1000,
            10,
            20,
            11,
            19,
            *materialize_pointers,
        )
    with pytest.raises(HipRtcFreeSpaceError):
        kernel.launch_residual_direction(
            2000,
            10,
            11,
            20,
            *tuple(range(2001, 2011)),
        )
    with pytest.raises(HipRtcFreeSpaceError):
        kernel.launch_gather_jvp(3000, 10, 5, 0, 2, 3, 4)
    with pytest.raises(HipRtcFreeSpaceError):
        kernel.launch_gather_jvp(0, 10, 5, 1, 2, 3, 4)
    uintptr_overflow = 1 << (8 * ctypes.sizeof(ctypes.c_void_p))
    with pytest.raises(HipRtcFreeSpaceError) as overflow:
        kernel.launch_gather_jvp(
            3000,
            10,
            5,
            uintptr_overflow,
            2,
            3,
            4,
        )
    assert overflow.value.code == "hip_rtc_free_space_launch_contract_invalid"
    assert runtime.launch_records == []
    kernel.close()


@pytest.mark.parametrize(
    "missing_symbol",
    [
        HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    ],
)
def test_missing_any_fixed_symbol_unloads_module(
    monkeypatch: pytest.MonkeyPatch,
    missing_symbol: str,
) -> None:
    runtime = FakeLoadedRuntime(missing_symbol=missing_symbol)
    with pytest.raises(HipRtcFreeSpaceError) as error:
        _compile_fake(monkeypatch, runtime=runtime)
    assert error.value.code == "hip_rtc_free_space_symbol_missing"
    assert runtime.unload_calls == 1


def test_compile_and_load_failures_release_native_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi(
        compile_status=6,
        compile_log="free-space compile failure",
    )
    monkeypatch.setattr(
        free_space_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with pytest.raises(HipRtcFreeSpaceError) as compile_error:
        compile_hip_rtc_free_space_operator_kernel(
            FakeLoadedRuntime(),
            "gfx1030",
        )
    assert compile_error.value.code == "hip_rtc_compile_failed"
    assert compile_error.value.compile_log == "free-space compile failure"
    assert fake_rtc.destroy_calls == 1

    runtime = FakeLoadedRuntime(load_status=11)
    with pytest.raises(HipRtcFreeSpaceError) as load_error:
        _compile_fake(monkeypatch, runtime=runtime)
    assert load_error.value.code == "hip_rtc_free_space_module_load_failed"
    assert runtime.unload_calls == 1


def test_failed_load_nonzero_cleanup_preserves_owner_for_known_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11, unload_statuses=(9, 0))
    with pytest.raises(HipRtcFreeSpaceError) as caught:
        _compile_fake(monkeypatch, runtime=runtime)
    error = caught.value
    assert error.code == "hip_rtc_free_space_module_cleanup_failed"
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
    with pytest.raises(HipRtcFreeSpaceError) as caught:
        _compile_fake(monkeypatch, runtime=runtime)
    error = caught.value
    assert error.code == "hip_rtc_free_space_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert not owner.closed
    assert runtime.unload_calls == 1

    with pytest.raises(HipRtcFreeSpaceError) as uncertain:
        owner.close()
    assert uncertain.value.code == (
        "hip_rtc_free_space_module_cleanup_outcome_uncertain"
    )
    assert uncertain.value.cleanup_owner is owner
    assert not owner.closed
    assert runtime.unload_calls == 1


def test_failed_close_preserves_owner_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    with pytest.raises(HipRtcFreeSpaceError) as error:
        kernel.close()
    assert error.value.code == "hip_rtc_free_space_module_unload_failed"
    assert not kernel.closed
    kernel.launch_gather_jvp(3000, 10, 5, 1, 2, 3, 4)
    kernel.close()
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 2
    with pytest.raises(HipRtcFreeSpaceError) as closed:
        kernel.launch_gather_jvp(3000, 10, 5, 1, 2, 3, 4)
    assert closed.value.code == "hip_rtc_free_space_kernel_closed"


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
        with pytest.raises(HipRtcFreeSpaceError) as first:
            kernel.close()
        assert first.value.code == "hip_rtc_free_space_module_unload_failed"
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
        assert _pointer_value(kernel._materialize_function) is None
        assert _pointer_value(kernel._residual_direction_function) is None
        assert _pointer_value(kernel._gather_jvp_function) is None
    else:
        assert kernel._unload_disposition == "unload_outcome_uncertain"
        expected_calls = int(phase == "runtime_side_effect")
        assert runtime.unload_calls == expected_calls
        with pytest.raises(HipRtcFreeSpaceError) as uncertain:
            kernel.close()
        assert uncertain.value.code == (
            "hip_rtc_free_space_module_unload_outcome_uncertain"
        )
        assert not kernel.closed
        assert runtime.unload_calls == expected_calls
        assert _pointer_value(kernel._module) == 513


def test_native_launch_failure_is_wrapped_without_closing_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(launch_status=12)
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    with pytest.raises(HipRtcFreeSpaceError) as error:
        kernel.launch_gather_jvp(3000, 10, 5, 1, 2, 3, 4)
    assert error.value.code == "hip_rtc_free_space_kernel_launch_failed"
    assert not kernel.closed
    assert len(runtime.launch_records) == 1
    kernel.close()


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
    hiprtc = free_space_rtc._load_hiprtc_api(library)
    status, major, minor = hiprtc.version()
    assert status == 0
    assert major >= 0 and minor >= 0
    code_object, compile_log = free_space_rtc._compile_fixed_source(
        hiprtc,
        free_space_rtc._fixed_source(),
        ("--offload-arch=gfx1030", "-O3", "-std=c++17"),
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
    code_path = tmp_path / "free-space.co"
    code_path.write_bytes(code_object)
    symbols = subprocess.run(
        [llvm_nm, str(code_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    assert HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL in symbols
    assert HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL in symbols
    assert HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL in symbols
