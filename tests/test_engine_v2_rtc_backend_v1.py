from __future__ import annotations

import ctypes
from dataclasses import FrozenInstanceError, replace
import inspect
from pathlib import Path
import shutil
import subprocess
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.backends.hip.native import (
    load_hip_native_runtime,
    probe_hip_capability,
)
from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend import rtc
from structural_analysis.engine_v2.rtc_backend.rtc import (
    HIP_RTC_CSR_KERNEL_BLOCK_SIZE,
    HIP_RTC_CSR_KERNEL_NAME,
    HipRtcError,
    HipRtcLibraryIdentity,
    compile_hip_rtc_csr_kernel,
)

KERNEL_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "structural_analysis"
    / "engine_v2"
    / "rtc_backend"
    / "kernels"
    / "engine_v2_csr_residual_jvp_v1.hip.cpp"
)


def test_engine_v2_root_exports_the_isolated_rtc_surface() -> None:
    import structural_analysis.engine_v2 as engine_v2

    assert engine_v2.compile_hip_rtc_csr_kernel is compile_hip_rtc_csr_kernel
    assert callable(engine_v2.open_hip_rtc_csr_execution_context)
    assert engine_v2.RTC_CSR_CAPABILITY_PROFILE == (
        "phase0_hiprtc_canonical_csr_residual_jvp"
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
        return 0, 9, 0

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
        return b"fake-amdgpu-code-object-v1"

    def destroy_program(self, program: Any) -> int:
        assert _pointer_value(program) == 257
        self.destroy_calls += 1
        return self.destroy_status


class FakeLoadedRuntime:
    def __init__(
        self,
        *,
        function_status: int = 0,
        launch_status: int = 0,
        unload_status: int = 0,
        runtime_sha: str | None = "sha256:" + ("1" * 64),
    ) -> None:
        self.library_identity = HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path=None,
            sha256=runtime_sha,
        )
        self.function_status = function_status
        self.launch_status = launch_status
        self.unload_status = unload_status
        self.load_calls = 0
        self.function_calls = 0
        self.launch_calls = 0
        self.unload_calls = 0
        self.launch_record: dict[str, Any] = {}

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
        return 0

    def _function(self, output: Any, module: Any, symbol: bytes) -> int:
        self.function_calls += 1
        assert _pointer_value(module) == 513
        assert symbol == HIP_RTC_CSR_KERNEL_NAME.encode("ascii")
        if self.function_status == 0:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(
                769
            )
        return self.function_status

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
        self.launch_calls += 1
        row_count = ctypes.cast(
            parameters[0], ctypes.POINTER(ctypes.c_int)
        ).contents.value
        pointers = tuple(
            ctypes.cast(
                parameters[index], ctypes.POINTER(ctypes.c_void_p)
            ).contents.value
            for index in range(1, 9)
        )
        self.launch_record = {
            "function": _pointer_value(function),
            "grid": (grid_x, grid_y, grid_z),
            "block": (block_x, block_y, block_z),
            "shared": shared,
            "stream": _pointer_value(stream),
            "row_count": row_count,
            "pointers": pointers,
            "extra": extra,
        }
        return self.launch_status

    def _unload(self, module: Any) -> int:
        assert _pointer_value(module) == 513
        self.unload_calls += 1
        return self.unload_status


def _pointer_value(value: Any) -> int | None:
    raw = value.value if isinstance(value, ctypes.c_void_p) else value
    return None if raw is None else int(raw)


def _compile_fake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_rtc: FakeRtcApi | None = None,
    runtime: FakeLoadedRuntime | None = None,
) -> tuple[Any, FakeRtcApi, FakeLoadedRuntime]:
    fake_rtc = fake_rtc or FakeRtcApi()
    runtime = runtime or FakeLoadedRuntime()
    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    return (
        compile_hip_rtc_csr_kernel(runtime, "gfx1030"),
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


def test_fixed_source_compile_builds_immutable_handle_free_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, fake_rtc, runtime = _compile_fake(monkeypatch)
    manifest = kernel.identity.to_dict()
    assert fake_rtc.created_source == KERNEL_SOURCE.read_bytes()
    assert fake_rtc.options == (
        "--offload-arch=gfx1030",
        "-O3",
        "-std=c++17",
    )
    assert runtime.load_calls == runtime.function_calls == 1
    assert kernel.identity.architecture == "gfx1030"
    assert kernel.identity.kernel_symbol == HIP_RTC_CSR_KERNEL_NAME
    assert kernel.identity.source_resource == (
        "kernels/engine_v2_csr_residual_jvp_v1.hip.cpp"
    )
    assert kernel.identity.hiprtc_version_major == 9
    assert kernel.identity.code_object_byte_length > 0
    assert kernel.identity.identity_hash.startswith("sha256:")
    assert not {
        "handle",
        "pointer",
        "module",
        "function",
        "stream",
    } & _all_keys(manifest)
    with pytest.raises(FrozenInstanceError):
        kernel.identity.architecture = "gfx90a"
    with pytest.raises(HipRtcError) as tamper:
        replace(kernel.identity, architecture="gfx90a").to_dict()
    assert tamper.value.code == "hip_rtc_identity_invalid"
    kernel.close()


def test_rehashed_forged_source_identity_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    forged = replace(
        kernel.identity,
        source_sha256="sha256:" + ("3" * 64),
        identity_hash="",
    )
    forged = replace(
        forged,
        identity_hash=canonical_hash(rtc._identity_payload(forged, include_hash=False)),
    )
    with pytest.raises(HipRtcError) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_identity_invalid"
    kernel.close()


def test_public_compile_surface_accepts_no_source_or_options() -> None:
    assert tuple(inspect.signature(compile_hip_rtc_csr_kernel).parameters) == (
        "loaded_runtime",
        "architecture",
        "hiprtc_library",
    )
    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert source.count("__global__") == 1
    assert f'extern "C" __global__ void {HIP_RTC_CSR_KERNEL_NAME}' in source
    for forbidden in (
        "#include",
        "hipLaunchKernelGGL",
        "hipMalloc",
        "hipMemcpy",
    ):
        assert forbidden not in source


def test_launch_packs_exact_fused_kernel_abi_and_close_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    pointers = tuple(range(1025, 1033))
    kernel.launch_residual_jvp(ctypes.c_void_p(1024), 513, *pointers)
    assert runtime.launch_calls == 1
    assert runtime.launch_record == {
        "function": 769,
        "grid": (3, 1, 1),
        "block": (HIP_RTC_CSR_KERNEL_BLOCK_SIZE, 1, 1),
        "shared": 0,
        "stream": 1024,
        "row_count": 513,
        "pointers": pointers,
        "extra": None,
    }
    kernel.close()
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 1
    with pytest.raises(HipRtcError) as closed:
        kernel.launch_residual_jvp(ctypes.c_void_p(1024), 1, *pointers)
    assert closed.value.code == "hip_rtc_kernel_closed"


@pytest.mark.parametrize(
    "architecture",
    [
        "",
        "gfx",
        "gfx1030 --save-temps",
        "gfx1030\n-O0",
        "gfx1030:xnack+",
        "sm_80",
        None,
    ],
)
def test_architecture_is_plain_target_and_cannot_inject_options(
    monkeypatch: pytest.MonkeyPatch,
    architecture: Any,
) -> None:
    monkeypatch.setattr(
        rtc,
        "_load_hiprtc_api",
        lambda library: pytest.fail("HIPRTC must not load"),
    )
    with pytest.raises(HipRtcError) as error:
        compile_hip_rtc_csr_kernel(FakeLoadedRuntime(), architecture)
    assert error.value.code == "hip_rtc_architecture_invalid"


def test_launch_contract_rejects_bad_count_and_null_runtime_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    pointers = tuple(range(1025, 1033))
    for row_count in (0, -1, True, 2**31):
        with pytest.raises(HipRtcError) as error:
            kernel.launch_residual_jvp(1024, row_count, *pointers)
        assert error.value.code == "hip_rtc_launch_contract_invalid"
    with pytest.raises(HipRtcError):
        kernel.launch_residual_jvp(0, 1, *pointers)
    with pytest.raises(HipRtcError):
        kernel.launch_residual_jvp(1024, 1, 0, *pointers[1:])
    assert runtime.launch_calls == 0
    kernel.close()


def test_compile_failure_preserves_log_and_always_destroys_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi(compile_status=6, compile_log="fixed compile failure")
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    with pytest.raises(HipRtcError) as error:
        compile_hip_rtc_csr_kernel(runtime, "gfx1030")
    assert error.value.code == "hip_rtc_compile_failed"
    assert error.value.compile_log == "fixed compile failure"
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == 0


def test_compile_base_exception_preserves_primary_and_destroys_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    interruption = KeyboardInterrupt("injected HIPRTC compile interruption")

    def interrupt_compile(program: Any, options: Any) -> int:
        del program, options
        raise interruption

    monkeypatch.setattr(fake_rtc, "compile_program", interrupt_compile)
    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    with pytest.raises(KeyboardInterrupt) as caught:
        compile_hip_rtc_csr_kernel(runtime, "gfx1030")
    assert caught.value is interruption
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == 0


@pytest.mark.parametrize("create_outcome", ("interrupt", "nonzero_status"))
def test_create_program_into_never_loses_a_written_program_handle(
    monkeypatch: pytest.MonkeyPatch,
    create_outcome: str,
) -> None:
    class IntoRtcApi(FakeRtcApi):
        def create_program(self, source: bytes) -> tuple[int, ctypes.c_void_p]:
            del source
            pytest.fail("compatibility tuple creation must not be used")

        def create_program_into(
            self,
            source: bytes,
            program: ctypes.c_void_p,
            program_name: str | None = None,
        ) -> int:
            del program_name
            self.created_source = source
            assert program.value is None
            program.value = 257
            if create_outcome == "interrupt":
                raise interruption
            return 7

    fake_rtc = IntoRtcApi()
    runtime = FakeLoadedRuntime()
    interruption = KeyboardInterrupt(
        "injected after native hiprtcCreateProgram output write"
    )
    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    if create_outcome == "interrupt":
        with pytest.raises(KeyboardInterrupt) as caught:
            compile_hip_rtc_csr_kernel(runtime, "gfx1030")
        assert caught.value is interruption
    else:
        with pytest.raises(HipRtcError) as caught:
            compile_hip_rtc_csr_kernel(runtime, "gfx1030")
        assert caught.value.code == "hip_rtc_program_create_failed"
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == 0


def test_outer_program_owner_recovers_final_cleanup_call_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    interruption = KeyboardInterrupt(
        "injected immediately before final HIPRTC program cleanup"
    )
    original_destroy = rtc._destroy_rtc_program
    helper_calls = 0

    def interrupt_once(*args: Any, **kwargs: Any) -> None:
        nonlocal helper_calls
        helper_calls += 1
        if helper_calls == 1:
            raise interruption
        original_destroy(*args, **kwargs)

    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    monkeypatch.setattr(rtc, "_destroy_rtc_program", interrupt_once)
    with pytest.raises(KeyboardInterrupt) as caught:
        compile_hip_rtc_csr_kernel(runtime, "gfx1030")
    assert caught.value is interruption
    assert helper_calls == 2
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == 0


def test_outer_program_owner_recovers_cleanup_entry_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    interruption = KeyboardInterrupt("injected at program owner cleanup entry")
    original_close = rtc._HipRtcProgramCleanupOwner.close
    close_calls = 0

    def interrupt_close_once(owner: Any) -> None:
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise interruption
        original_close(owner)

    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    monkeypatch.setattr(
        rtc._HipRtcProgramCleanupOwner,
        "close",
        interrupt_close_once,
    )
    with pytest.raises(HipRtcError) as caught:
        compile_hip_rtc_csr_kernel(runtime, "gfx1030")
    assert caught.value.code == "hip_rtc_program_destroy_failed"
    assert close_calls == 2
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == 0


def test_missing_kernel_symbol_unloads_module_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(function_status=7)
    monkeypatch.setattr(rtc, "_load_hiprtc_api", lambda library: fake_rtc)
    with pytest.raises(HipRtcError) as error:
        compile_hip_rtc_csr_kernel(runtime, "gfx1030")
    assert error.value.code == "hip_rtc_kernel_symbol_missing"
    assert fake_rtc.destroy_calls == 1
    assert runtime.load_calls == runtime.function_calls == runtime.unload_calls == 1


def test_runtime_requires_exact_library_hash_before_compilation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rtc,
        "_load_hiprtc_api",
        lambda library: pytest.fail("HIPRTC must not load without runtime identity"),
    )
    with pytest.raises(HipRtcError) as error:
        compile_hip_rtc_csr_kernel(FakeLoadedRuntime(runtime_sha=None), "gfx1030")
    assert error.value.code == "hip_rtc_runtime_identity_invalid"


def test_kernel_launch_failure_and_unload_failure_have_stable_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(launch_status=8, unload_status=9)
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    pointers = tuple(range(1025, 1033))
    with pytest.raises(HipRtcError) as launch_error:
        kernel.launch_residual_jvp(1024, 1, *pointers)
    assert launch_error.value.code == "hip_rtc_kernel_launch_failed"
    with pytest.raises(HipRtcError) as unload_error:
        kernel.close()
    assert unload_error.value.code == "hip_rtc_module_unload_failed"
    assert not kernel.closed


def _actual_architecture() -> str | None:
    for command in ("rocm_agent_enumerator", "offload-arch"):
        executable = shutil.which(command)
        if executable is None:
            continue
        completed = subprocess.run(
            [executable],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            continue
        targets = [
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip().startswith("gfx") and line.strip() != "gfx000"
        ]
        if targets:
            return targets[0]
    return None


def _bind(runtime: Any, symbol: str, argtypes: list[Any]) -> Any:
    return runtime.bind(symbol, argtypes, ctypes.c_int)


def test_actual_host_hiprtc_compiles_loads_and_executes_fused_kernel() -> None:
    capability = probe_hip_capability()
    if capability.status != "ready":
        pytest.skip(
            f"native HIP unavailable: {capability.status_code}: {capability.message}"
        )
    architecture = _actual_architecture()
    if architecture is None:
        pytest.skip("AMD gfx architecture enumerator is unavailable")
    runtime = load_hip_native_runtime()
    kernel = compile_hip_rtc_csr_kernel(runtime, architecture)
    hip_malloc = _bind(
        runtime,
        "hipMalloc",
        [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t],
    )
    hip_free = _bind(runtime, "hipFree", [ctypes.c_void_p])
    hip_memcpy = _bind(
        runtime,
        "hipMemcpy",
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int],
    )
    stream_create = _bind(
        runtime,
        "hipStreamCreate",
        [ctypes.POINTER(ctypes.c_void_p)],
    )
    stream_sync = _bind(runtime, "hipStreamSynchronize", [ctypes.c_void_p])
    stream_destroy = _bind(runtime, "hipStreamDestroy", [ctypes.c_void_p])
    stream = ctypes.c_void_p()
    assert stream_create(ctypes.byref(stream)) == 0
    matrix = np.array(
        [[4.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 2.0]],
        dtype=np.float64,
    )
    host_inputs = (
        np.array([0, 2, 5, 7], dtype=np.int32),
        np.array([0, 1, 0, 1, 2, 1, 2], dtype=np.int32),
        np.array([4.0, 1.0, 1.0, 3.0, 1.0, 1.0, 2.0]),
        np.array([1.0, 2.0, 3.0]),
        np.array([1.0, 1.0, 1.0]),
        np.array([2.0, -1.0, 0.5]),
    )
    pointers: list[ctypes.c_void_p] = []
    try:
        for array in host_inputs:
            pointer = ctypes.c_void_p()
            assert hip_malloc(ctypes.byref(pointer), array.nbytes) == 0
            pointers.append(pointer)
            assert (
                hip_memcpy(
                    pointer,
                    ctypes.c_void_p(array.ctypes.data),
                    array.nbytes,
                    1,
                )
                == 0
            )
        for _ in range(2):
            pointer = ctypes.c_void_p()
            assert hip_malloc(ctypes.byref(pointer), 24) == 0
            pointers.append(pointer)
        kernel.launch_residual_jvp(stream, 3, *pointers)
        assert stream_sync(stream) == 0
        outputs = []
        for pointer in pointers[-2:]:
            output = np.empty(3, dtype=np.float64)
            assert (
                hip_memcpy(
                    ctypes.c_void_p(output.ctypes.data),
                    pointer,
                    output.nbytes,
                    2,
                )
                == 0
            )
            outputs.append(output)
        np.testing.assert_allclose(outputs[0], matrix @ host_inputs[3] - host_inputs[4])
        np.testing.assert_allclose(outputs[1], matrix @ host_inputs[5])
        assert kernel.identity.architecture == architecture
        assert kernel.identity.runtime_library.sha256.startswith("sha256:")
        assert kernel.identity.hiprtc_library.sha256.startswith("sha256:")
        assert kernel.identity.code_object_sha256.startswith("sha256:")
    finally:
        for pointer in reversed(pointers):
            assert hip_free(pointer) == 0
        assert stream_destroy(stream) == 0
        kernel.close()
