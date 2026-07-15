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

from structural_analysis.engine_v2.assembly_backend import rtc as assembly_rtc
from structural_analysis.engine_v2.assembly_backend.rtc import (
    HIP_RTC_CSR_GATHER_BLOCK_SIZE,
    HIP_RTC_CSR_GATHER_SYMBOL,
    HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE,
    HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
    HipRtcAssemblyError,
    REFERENCE_AXIS_GLOBAL_Y,
    REFERENCE_AXIS_GLOBAL_Z,
    compile_hip_rtc_linear_frame_truss_assembly_kernel,
)
from structural_analysis.engine_v2.assembly_backend import plan as assembly_plan
from structural_analysis.engine_v2.elements.linear_frame_truss_v1 import (
    frame_local_stiffness_v1,
    frame_reference_axis_v1,
    frame_transform_v1,
    truss_local_stiffness_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (
    load_hip_native_runtime,
    probe_hip_capability,
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
    / "engine_v2_linear_frame_truss_assembly_v1.hip.cpp"
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
        return b"fake-frame-truss-assembly-code-object-v1"

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
        self.load_calls = 0
        self.function_symbols: list[str] = []
        self.launch_records: list[dict[str, Any]] = []
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
        handle = 769 if decoded == HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL else 770
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(
            handle
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
        scalar_count = 4 if function_value == 769 else 2
        pointer_count = 14 if function_value == 769 else 5
        scalars = tuple(
            ctypes.cast(parameters[index], ctypes.POINTER(ctypes.c_int)).contents.value
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


def _compile_fake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_rtc: FakeRtcApi | None = None,
    runtime: FakeLoadedRuntime | None = None,
) -> tuple[Any, FakeRtcApi, FakeLoadedRuntime]:
    fake_rtc = fake_rtc or FakeRtcApi()
    runtime = runtime or FakeLoadedRuntime()
    monkeypatch.setattr(
        assembly_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    return (
        compile_hip_rtc_linear_frame_truss_assembly_kernel(
            runtime,
            "gfx1030",
        ),
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


def test_fixed_source_compile_binds_both_symbols_and_exact_identity(
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
    assert runtime.function_symbols == [
        HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
        HIP_RTC_CSR_GATHER_SYMBOL,
    ]
    assert manifest["kernel_symbols"] == {
        "element_contribution": HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
        "csr_gather": HIP_RTC_CSR_GATHER_SYMBOL,
    }
    assert manifest["launch_geometry"] == {
        "element_contribution_block_size": 144,
        "csr_gather_block_size": 256,
    }
    assert kernel.identity.architecture == "gfx1030"
    assert kernel.identity.hiprtc_version_major == 9
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
    forged = replace(kernel.identity, csr_gather_symbol="forged", identity_hash="")
    forged = replace(
        forged,
        identity_hash=canonical_hash(
            assembly_rtc._identity_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcAssemblyError) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_assembly_identity_invalid"
    kernel.close()


def test_rehashed_identity_rejects_bool_and_nonexact_scalar_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TextSubclass(str):
        pass

    kernel, _, _ = _compile_fake(monkeypatch)
    mutations = (
        {"abi_version": True},
        {"hiprtc_version_major": True},
        {"hiprtc_version_minor": True},
        {"code_object_byte_length": True},
        {"architecture": TextSubclass("gfx1030")},
        {"schema_version": TextSubclass(kernel.identity.schema_version)},
        {
            "compile_options": (
                TextSubclass("--offload-arch=gfx1030"),
                "-O3",
                "-std=c++17",
            )
        },
    )
    for mutation in mutations:
        forged = replace(kernel.identity, **mutation, identity_hash="")
        forged = replace(
            forged,
            identity_hash=canonical_hash(
                assembly_rtc._identity_payload(forged, include_hash=False)
            ),
        )
        with pytest.raises(HipRtcAssemblyError) as error:
            forged.to_dict()
        assert error.value.code == "hip_rtc_assembly_identity_invalid"
    kernel.close()


def test_fixed_identity_is_accepted_by_the_assembly_context_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from structural_analysis.engine_v2.assembly_backend.context import (
        _kernel_binding,
    )

    kernel, _, _ = _compile_fake(monkeypatch)
    binding = _kernel_binding(kernel, "gfx1030")
    assert binding.abi_version == 1
    assert binding.element_kernel_symbol == HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL
    assert binding.gather_kernel_symbol == HIP_RTC_CSR_GATHER_SYMBOL
    assert binding.element_block_size == 144
    assert binding.gather_block_size == 256
    assert binding.identity_hash == kernel.identity.identity_hash
    kernel.close()


def test_public_compile_surface_has_no_source_options_or_symbols() -> None:
    assert tuple(
        inspect.signature(compile_hip_rtc_linear_frame_truss_assembly_kernel).parameters
    ) == ("loaded_runtime", "architecture", "hiprtc_library")
    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert source.count('extern "C" __global__ void') == 2
    assert source.count("atomicCAS") == 1
    assert "__shared__ double transform[144]" in source
    assert "__shared__ double local_stiffness[144]" in source
    assert source.count("__syncthreads()") >= 2
    assert "#pragma clang fp contract(off)" in source
    assert "value == 0.0 ? 0.0 : value" in source
    assert "expected_axis" not in source
    assert "fabs(local_x[2]) > 0.9" not in source
    assert "*error_flag" not in source
    for forbidden_index_product in (
        "element * 144",
        "element * 2",
        "node_i * 3",
        "node_j * 3",
        "material * 3",
        "section * 6",
    ):
        assert forbidden_index_product not in source
    for required_u64_product in (
        "element_offset * 2ull",
        "element_offset * 144ull",
        "static_cast<unsigned long long>(node_i) * 3ull",
        "static_cast<unsigned long long>(node_j) * 3ull",
        "static_cast<unsigned long long>(material) * 3ull",
        "static_cast<unsigned long long>(section) * 6ull",
    ):
        assert required_u64_product in source
    for forbidden in (
        "#include",
        "hipLaunchKernelGGL",
        "hipMalloc",
        "hipMemcpy",
        "atomicAdd",
    ):
        assert forbidden not in source


def test_axis_threshold_boundary_is_host_owned_and_not_rederived_on_device() -> None:
    threshold = assembly_plan.REFERENCE_AXIS_SWITCH_THRESHOLD
    exact = np.float64(threshold)
    below = np.nextafter(exact, np.float64(0.0))
    above = np.nextafter(exact, np.float64(np.inf))

    def host_axis(local_x_z: np.float64) -> int:
        return (
            assembly_plan.REFERENCE_AXIS_GLOBAL_Y
            if abs(float(local_x_z)) > threshold
            else assembly_plan.REFERENCE_AXIS_GLOBAL_Z
        )

    assert host_axis(below) == REFERENCE_AXIS_GLOBAL_Z
    assert host_axis(exact) == REFERENCE_AXIS_GLOBAL_Z
    assert host_axis(above) == REFERENCE_AXIS_GLOBAL_Y
    assert host_axis(-above) == REFERENCE_AXIS_GLOBAL_Y
    assert assembly_plan.REFERENCE_AXIS_GLOBAL_Y == REFERENCE_AXIS_GLOBAL_Y
    assert assembly_plan.REFERENCE_AXIS_GLOBAL_Z == REFERENCE_AXIS_GLOBAL_Z
    compiler_source = inspect.getsource(assembly_plan._compile_reference_axis_codes)
    assert "frame_reference_axis_v1" in compiler_source
    semantics_source = inspect.getsource(frame_reference_axis_v1)
    assert "> REFERENCE_AXIS_SWITCH_THRESHOLD_V1" in semantics_source
    device_source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert "REFERENCE_AXIS_SWITCH_THRESHOLD" not in device_source
    assert "fabs(local_x[2])" not in device_source


def test_two_launch_methods_pack_exact_fixed_abis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    element_pointers = tuple(range(2001, 2015))
    kernel.launch_element_contributions(
        2000,
        3,
        4,
        2,
        2,
        *element_pointers,
    )
    gather_pointers = tuple(range(3001, 3006))
    kernel.launch_csr_gather(3000, 513, 432, *gather_pointers)
    assert runtime.launch_records == [
        {
            "function": 769,
            "grid": (3, 1, 1),
            "block": (
                HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE,
                1,
                1,
            ),
            "shared": 0,
            "stream": 2000,
            "scalars": (3, 4, 2, 2),
            "pointers": element_pointers,
            "extra": None,
        },
        {
            "function": 770,
            "grid": (3, 1, 1),
            "block": (HIP_RTC_CSR_GATHER_BLOCK_SIZE, 1, 1),
            "shared": 0,
            "stream": 3000,
            "scalars": (513, 432),
            "pointers": gather_pointers,
            "extra": None,
        },
    ]
    kernel.close()


def test_launch_contracts_reject_bad_int32_and_null_pointers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    element_pointers = tuple(range(2001, 2015))
    for count in (0, -1, True, 2**31):
        with pytest.raises(HipRtcAssemblyError) as error:
            kernel.launch_element_contributions(
                2000,
                count,
                4,
                2,
                2,
                *element_pointers,
            )
        assert error.value.code == ("hip_rtc_assembly_launch_contract_invalid")
    with pytest.raises(HipRtcAssemblyError):
        kernel.launch_element_contributions(
            0,
            1,
            4,
            2,
            2,
            *element_pointers,
        )
    with pytest.raises(HipRtcAssemblyError):
        kernel.launch_element_contributions(
            2000,
            1,
            4,
            2,
            2,
            0,
            *element_pointers[1:],
        )
    with pytest.raises(HipRtcAssemblyError):
        kernel.launch_csr_gather(3000, 1, 1, 0, 2, 3, 4, 5)
    uintptr_overflow = 1 << (8 * ctypes.sizeof(ctypes.c_void_p))
    with pytest.raises(HipRtcAssemblyError) as stream_overflow:
        kernel.launch_element_contributions(
            uintptr_overflow,
            1,
            4,
            2,
            2,
            *element_pointers,
        )
    assert stream_overflow.value.code == ("hip_rtc_assembly_launch_contract_invalid")
    overflow_pointers = (uintptr_overflow, *element_pointers[1:])
    with pytest.raises(HipRtcAssemblyError) as pointer_overflow:
        kernel.launch_element_contributions(
            2000,
            1,
            4,
            2,
            2,
            *overflow_pointers,
        )
    assert pointer_overflow.value.code == ("hip_rtc_assembly_launch_contract_invalid")
    assert runtime.launch_records == []
    kernel.close()


def test_element_launch_caps_144e_and_accepts_large_reference_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    element_pointers = tuple(range(2001, 2015))
    maximum_element_count = ((1 << 31) - 1) // 144
    kernel.launch_element_contributions(
        2000,
        maximum_element_count,
        (1 << 31) - 1,
        (1 << 31) - 1,
        (1 << 31) - 1,
        *element_pointers,
    )
    assert runtime.launch_records[0]["scalars"] == (
        maximum_element_count,
        (1 << 31) - 1,
        (1 << 31) - 1,
        (1 << 31) - 1,
    )
    with pytest.raises(HipRtcAssemblyError) as overflow:
        kernel.launch_element_contributions(
            2000,
            maximum_element_count + 1,
            4,
            2,
            2,
            *element_pointers,
        )
    assert overflow.value.code == "hip_rtc_assembly_launch_contract_invalid"
    assert len(runtime.launch_records) == 1
    kernel.close()


def test_compile_failure_destroys_program_and_missing_gather_unloads_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rtc = FakeRtcApi(compile_status=6, compile_log="assembly compile fail")
    monkeypatch.setattr(
        assembly_rtc,
        "_load_hiprtc_api",
        lambda library: fake_rtc,
    )
    with pytest.raises(HipRtcAssemblyError) as compile_error:
        compile_hip_rtc_linear_frame_truss_assembly_kernel(
            FakeLoadedRuntime(),
            "gfx1030",
        )
    assert compile_error.value.code == "hip_rtc_compile_failed"
    assert compile_error.value.compile_log == "assembly compile fail"
    assert fake_rtc.destroy_calls == 1

    missing_runtime = FakeLoadedRuntime(missing_symbol=HIP_RTC_CSR_GATHER_SYMBOL)
    with pytest.raises(HipRtcAssemblyError) as symbol_error:
        _compile_fake(monkeypatch, runtime=missing_runtime)
    assert symbol_error.value.code == "hip_rtc_assembly_gather_symbol_missing"
    assert missing_runtime.unload_calls == 1

    failed_load_runtime = FakeLoadedRuntime(load_status=11)
    with pytest.raises(HipRtcAssemblyError) as load_error:
        _compile_fake(monkeypatch, runtime=failed_load_runtime)
    assert load_error.value.code == "hip_rtc_assembly_module_load_failed"
    assert failed_load_runtime.unload_calls == 1


def test_failed_unload_preserves_owner_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    kernel, _, _ = _compile_fake(monkeypatch, runtime=runtime)
    with pytest.raises(HipRtcAssemblyError) as error:
        kernel.close()
    assert error.value.code == "hip_rtc_assembly_module_unload_failed"
    assert not kernel.closed
    kernel.launch_csr_gather(3000, 1, 1, 1, 2, 3, 4, 5)
    kernel.close()
    kernel.close()
    assert kernel.closed
    assert runtime.unload_calls == 2
    with pytest.raises(HipRtcAssemblyError) as closed:
        kernel.launch_csr_gather(3000, 1, 1, 1, 2, 3, 4, 5)
    assert closed.value.code == "hip_rtc_assembly_kernel_closed"


def _actual_architecture() -> str | None:
    for executable in (
        shutil.which("rocm_agent_enumerator"),
        "/opt/rocm/bin/rocm_agent_enumerator",
        "/opt/rocm-6.0.2/bin/rocm_agent_enumerator",
    ):
        if not executable or not Path(executable).is_file():
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
        for token in completed.stdout.split():
            if token.startswith("gfx") and token != "gfx000":
                return token
    return None


def test_actual_hiprtc_compiles_fixed_gfx1030_source_without_device_fallback(
    tmp_path: Path,
) -> None:
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
    hiprtc = assembly_rtc._load_hiprtc_api(library)
    status, major, minor = hiprtc.version()
    assert status == 0
    assert major >= 0 and minor >= 0
    code_object, compile_log = assembly_rtc._compile_fixed_source(
        hiprtc,
        assembly_rtc._fixed_source(),
        ("--offload-arch=gfx1030", "-O3", "-std=c++17"),
    )
    assert code_object
    assert compile_log == ""
    assert assembly_rtc._sha256_bytes(code_object).startswith("sha256:")
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
    code_path = tmp_path / "assembly.co"
    code_path.write_bytes(code_object)
    symbols = subprocess.run(
        [llvm_nm, str(code_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    assert HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL in symbols
    assert HIP_RTC_CSR_GATHER_SYMBOL in symbols


def _bind(runtime: Any, symbol: str, argtypes: list[Any]) -> Any:
    return runtime.bind(symbol, argtypes, ctypes.c_int)


def test_actual_hiprtc_assembly_frame_truss_and_stable_gather() -> None:
    capability = probe_hip_capability()
    architecture = _actual_architecture()
    if capability.status != "ready" or architecture is None:
        pytest.skip(
            "native HIP device unavailable; no CPU result substitutes for "
            "the skipped compile/module/launch evidence"
        )

    runtime = load_hip_native_runtime()
    kernel = compile_hip_rtc_linear_frame_truss_assembly_kernel(
        runtime,
        architecture,
    )
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
    stream_sync = _bind(
        runtime,
        "hipStreamSynchronize",
        [ctypes.c_void_p],
    )
    stream_destroy = _bind(runtime, "hipStreamDestroy", [ctypes.c_void_p])

    coordinates = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 2.0],
        ],
        dtype="<f8",
    )
    connectivity = np.array([[0, 1], [2, 3], [4, 5]], dtype="<i4")
    element_type = np.array([2, 1, 2], dtype="u1")
    formulation = np.array([2, 1, 2], dtype="u1")
    material_index = np.array([0, 0, 0], dtype="<i4")
    section_index = np.array([0, 1, 0], dtype="<i4")
    material_law = np.array([1], dtype="u1")
    materials = np.array([[210.0e9, 0.3, 7850.0]], dtype="<f8")
    section_family = np.array([2, 1], dtype="u1")
    sections = np.array(
        [
            [0.02, 8.0e-6, 6.0e-6, 1.0e-5, 0.015, 0.015],
            [0.01, 0.0, 0.0, 0.0, 0.0, 0.0],
        ],
        dtype="<f8",
    )
    rolls = np.array([0.2, -0.1, 0.35], dtype="<f8")
    reference_axes = np.array([2, 2, 1], dtype="u1")
    assert frame_reference_axis_v1(coordinates[0], coordinates[1]) == "global_z"
    assert frame_reference_axis_v1(coordinates[4], coordinates[5]) == "global_y"
    host_inputs = (
        coordinates,
        connectivity,
        element_type,
        formulation,
        material_index,
        section_index,
        material_law,
        materials,
        section_family,
        sections,
        rolls,
        reference_axes,
    )
    stream = ctypes.c_void_p()
    pointers: list[ctypes.c_void_p] = []
    assert stream_create(ctypes.byref(stream)) == 0
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
        contribution_pointer = ctypes.c_void_p()
        assert hip_malloc(ctypes.byref(contribution_pointer), 432 * 8) == 0
        pointers.append(contribution_pointer)
        error_pointer = ctypes.c_void_p()
        assert hip_malloc(ctypes.byref(error_pointer), 4) == 0
        pointers.append(error_pointer)
        host_error = np.zeros(1, dtype="<i4")
        assert (
            hip_memcpy(
                error_pointer,
                ctypes.c_void_p(host_error.ctypes.data),
                host_error.nbytes,
                1,
            )
            == 0
        )
        kernel.launch_element_contributions(
            stream,
            3,
            6,
            1,
            2,
            *pointers,
        )
        assert stream_sync(stream) == 0
        contributions = np.empty((3, 12, 12), dtype="<f8")
        assert (
            hip_memcpy(
                ctypes.c_void_p(contributions.ctypes.data),
                contribution_pointer,
                contributions.nbytes,
                2,
            )
            == 0
        )
        assert (
            hip_memcpy(
                ctypes.c_void_p(host_error.ctypes.data),
                error_pointer,
                host_error.nbytes,
                2,
            )
            == 0
        )
        assert host_error.tolist() == [0]

        frame_transform, frame_length = frame_transform_v1(
            coordinates[0], coordinates[1], rolls[0]
        )
        truss_transform, truss_length = frame_transform_v1(
            coordinates[2], coordinates[3], rolls[1]
        )
        global_y_frame_transform, global_y_frame_length = frame_transform_v1(
            coordinates[4], coordinates[5], rolls[2]
        )
        expected_frame = (
            frame_transform.T
            @ frame_local_stiffness_v1(materials[0], sections[0], frame_length)
            @ frame_transform
        )
        expected_truss = (
            truss_transform.T
            @ truss_local_stiffness_v1(materials[0], sections[1], truss_length)
            @ truss_transform
        )
        expected_global_y_frame = (
            global_y_frame_transform.T
            @ frame_local_stiffness_v1(materials[0], sections[0], global_y_frame_length)
            @ global_y_frame_transform
        )
        np.testing.assert_allclose(
            contributions[0], expected_frame, rtol=2.0e-13, atol=1.0e-6
        )
        np.testing.assert_allclose(
            contributions[1], expected_truss, rtol=2.0e-13, atol=1.0e-6
        )
        np.testing.assert_allclose(
            contributions[2], expected_global_y_frame, rtol=2.0e-13, atol=1.0e-6
        )

        offsets = np.arange(0, 433, 3, dtype="<i4")
        reverse = np.column_stack(
            (
                np.arange(144, dtype="<i4"),
                np.arange(144, 288, dtype="<i4"),
                np.arange(288, 432, dtype="<i4"),
            )
        ).reshape(-1)
        for array in (offsets, reverse):
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
        csr_pointer = ctypes.c_void_p()
        assert hip_malloc(ctypes.byref(csr_pointer), 144 * 8) == 0
        pointers.append(csr_pointer)
        kernel.launch_csr_gather(
            stream,
            144,
            432,
            contribution_pointer,
            pointers[-3],
            pointers[-2],
            csr_pointer,
            error_pointer,
        )
        assert stream_sync(stream) == 0
        gathered = np.empty(144, dtype="<f8")
        assert (
            hip_memcpy(
                ctypes.c_void_p(gathered.ctypes.data),
                csr_pointer,
                gathered.nbytes,
                2,
            )
            == 0
        )
        np.testing.assert_allclose(
            gathered.reshape(12, 12),
            expected_frame + expected_truss + expected_global_y_frame,
            rtol=2.0e-13,
            atol=1.0e-6,
        )
    finally:
        for pointer in reversed(pointers):
            assert hip_free(pointer) == 0
        assert stream_destroy(stream) == 0
        kernel.close()
