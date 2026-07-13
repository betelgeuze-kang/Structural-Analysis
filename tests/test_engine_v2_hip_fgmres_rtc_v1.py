from __future__ import annotations

import ctypes
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import structural_analysis.engine_v2 as engine_v2  # noqa: E402
import structural_analysis.engine_v2.assembly_backend as assembly_backend  # noqa: E402
from structural_analysis.engine_v2.assembly_backend import fgmres_rtc  # noqa: E402
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    HIP_FGMRES_RECURRENCE_ABI_VERSION,
    HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES,
    HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES,
    hip_fgmres_solve_record_abi_payload_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc import (  # noqa: E402
    FGMRES_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
    FGMRES_DEVICE_ERROR_CSR_STRUCTURE,
    FGMRES_DEVICE_ERROR_INVALID_CONTROL_OR_GEOMETRY,
    FGMRES_DEVICE_ERROR_JACOBI,
    FGMRES_DEVICE_ERROR_NONE,
    FGMRES_DEVICE_ERROR_NONFINITE_INPUT,
    FGMRES_DEVICE_ERROR_RECORD_ABI,
    HIP_RTC_FGMRES_APPLY_JACOBI_SYMBOL,
    HIP_RTC_FGMRES_BLOCK_SIZE,
    HIP_RTC_FGMRES_CONTROL_TERMINAL_SYMBOL,
    HIP_RTC_FGMRES_COPY_SCALE_SYMBOL,
    HIP_RTC_FGMRES_CSR_SPMV_SYMBOL,
    HIP_RTC_FGMRES_RECORD_INITIALIZE_SYMBOL,
    HIP_RTC_FGMRES_RECORD_RESTART_SYMBOL,
    HIP_RTC_FGMRES_RESIDUAL_SYMBOL,
    HipRtcFgmresError,
    compile_hip_rtc_fgmres_kernel,
    solve_record_byte_length,
)
from structural_analysis.engine_v2.backends.hip.types import (  # noqa: E402
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    HipRtcLibraryIdentity,
)


KERNEL_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "structural_analysis"
    / "engine_v2"
    / "assembly_backend"
    / "kernels"
    / "engine_v2_fgmres_v1.hip.cpp"
)
SYMBOLS = (
    HIP_RTC_FGMRES_RECORD_INITIALIZE_SYMBOL,
    HIP_RTC_FGMRES_CSR_SPMV_SYMBOL,
    HIP_RTC_FGMRES_RESIDUAL_SYMBOL,
    HIP_RTC_FGMRES_COPY_SCALE_SYMBOL,
    HIP_RTC_FGMRES_APPLY_JACOBI_SYMBOL,
    HIP_RTC_FGMRES_CONTROL_TERMINAL_SYMBOL,
    HIP_RTC_FGMRES_RECORD_RESTART_SYMBOL,
)
ABI_KINDS = {
    HIP_RTC_FGMRES_RECORD_INITIALIZE_SYMBOL: "iiidddppp",
    HIP_RTC_FGMRES_CSR_SPMV_SYMBOL: "iipppppp",
    HIP_RTC_FGMRES_RESIDUAL_SYMBOL: "ipppp",
    HIP_RTC_FGMRES_COPY_SCALE_SYMBOL: "idppp",
    HIP_RTC_FGMRES_APPLY_JACOBI_SYMBOL: "ipppp",
    HIP_RTC_FGMRES_CONTROL_TERMINAL_SYMBOL: "ippp",
    HIP_RTC_FGMRES_RECORD_RESTART_SYMBOL: "iiiiiiidddddp",
}


class FakeRtcApi:
    def __init__(self) -> None:
        self.identity = HipRtcLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libhiprtc.so",
            loaded_name="fake-libhiprtc.so",
            resolved_path="/fake/libhiprtc.so",
            sha256="sha256:" + "2" * 64,
        )
        self.created_source = b""
        self.created_program_name: str | None = None
        self.options: tuple[str, ...] = ()

    def error_string(self, status: int) -> str:
        return f"fake HIPRTC status {status}"

    def version(self) -> tuple[int, int, int]:
        return 0, 9, 1

    def create_program(
        self, source: bytes, program_name: str | None = None
    ) -> tuple[int, ctypes.c_void_p]:
        self.created_source = source
        self.created_program_name = program_name
        return 0, ctypes.c_void_p(257)

    def compile_program(self, program: Any, options: Any) -> int:
        assert _pointer_value(program) == 257
        self.options = tuple(options)
        return 0

    def program_log(self, program: Any) -> str:
        assert _pointer_value(program) == 257
        return ""

    def code_object(self, program: Any) -> bytes:
        assert _pointer_value(program) == 257
        return b"fake-fgmres-code-object-v1"

    def destroy_program(self, program: Any) -> int:
        assert _pointer_value(program) == 257
        return 0


class FakeLoadedRuntime:
    def __init__(
        self,
        *,
        missing_symbol: str | None = None,
        launch_status: int = 0,
        launch_exception: bool = False,
        unload_statuses: tuple[int, ...] = (0,),
    ) -> None:
        self.library_identity = HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path=None,
            sha256="sha256:" + "1" * 64,
        )
        self.missing_symbol = missing_symbol
        self.launch_status = launch_status
        self.launch_exception = launch_exception
        self.unload_statuses = list(unload_statuses)
        self.function_symbols: list[str] = []
        self.launch_records: list[dict[str, Any]] = []
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
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(513)
        return 0

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
        arguments: list[int | float | None] = []
        for index, kind in enumerate(ABI_KINDS[symbol]):
            ctype = {"i": ctypes.c_int, "d": ctypes.c_double, "p": ctypes.c_void_p}[
                kind
            ]
            arguments.append(
                ctypes.cast(parameters[index], ctypes.POINTER(ctype)).contents.value
            )
        self.launch_records.append(
            {
                "symbol": symbol,
                "grid": (grid_x, grid_y, grid_z),
                "block": (block_x, block_y, block_z),
                "stream": _pointer_value(stream),
                "arguments": tuple(arguments),
                "shared": shared,
                "extra": extra,
            }
        )
        if self.launch_exception:
            raise RuntimeError("ambiguous fake launch exception")
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
    runtime: FakeLoadedRuntime | None = None,
) -> tuple[Any, FakeRtcApi, FakeLoadedRuntime]:
    rtc = FakeRtcApi()
    checked_runtime = runtime or FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc, "_load_hiprtc_api", lambda library: rtc)
    return (
        compile_hip_rtc_fgmres_kernel(checked_runtime, "gfx1030"),
        rtc,
        checked_runtime,
    )


def test_fixed_source_symbols_identity_and_exact_solve_record_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, rtc, runtime = _compile_fake(monkeypatch)
    identity = kernel.identity
    manifest = identity.to_dict()
    assert rtc.created_source == KERNEL_SOURCE.read_bytes()
    assert rtc.created_program_name == KERNEL_SOURCE.name
    assert rtc.options == (
        "--offload-arch=gfx1030",
        "-O3",
        "-std=c++17",
        "-ffp-contract=off",
    )
    assert runtime.function_symbols == list(SYMBOLS)
    assert identity.kernel_symbols == SYMBOLS
    assert tuple(manifest["kernel_symbols"].values()) == SYMBOLS
    assert manifest["recurrence_abi_version"] == HIP_FGMRES_RECURRENCE_ABI_VERSION
    record = manifest["solve_record_abi"]
    assert record["byte_order"] == "little_endian"
    assert record["header_bytes"] == HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES == 192
    assert record["restart_bytes"] == HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES == 72
    assert record["header_fields"][0] == {
        "name": "recurrence_abi_version",
        "dtype": "i32",
        "offset_bytes": 0,
    }
    assert record["header_fields"][-1] == {
        "name": "reserved_f64_0",
        "dtype": "f64",
        "offset_bytes": 184,
    }
    assert record["restart_fields"][-1] == {
        "name": "solution_update_l2",
        "dtype": "f64",
        "offset_bytes": 64,
    }
    assert record["terminal_status_codes"] == {
        "not_terminal": 0,
        "converged": 1,
        "max_iterations": 2,
        "stagnated": 3,
        "diverged": 4,
        "arnoldi_breakdown": 5,
        "numerical_failure": 6,
    }
    assert record["termination_codes"]["converged_initial_true_residual"] == 1
    assert record["termination_codes"]["restart_state_failed"] == 47
    assert record["restart_hint_codes"]["converged_true_residual"] == 3
    assert record["restart_flag_bits"]["divergence"] == 7
    assert {key: value for key, value in record.items() if key != "layout_hash"} == (
        hip_fgmres_solve_record_abi_payload_v1()
    )
    assert record["layout_hash"] == canonical_hash(
        {key: value for key, value in record.items() if key != "layout_hash"}
    )
    interface = manifest["kernel_interface"]
    assert interface["solve_record_layout_hash"] == record["layout_hash"]
    assert interface["device_error_bits"]["record_abi"] == 16
    assert interface["control_modes"] == {
        "initial_true_residual": 0,
        "candidate_true_residual": 1,
        "max_iterations_finalize": 2,
    }
    assert interface["launches"]["copy_scale"]["arguments"][1] == {
        "name": "scale",
        "abi": "f64",
        "source": "host_value",
    }
    assert interface["launches"]["record_restart"]["arguments"][-2] == {
        "name": "solution_update_l2",
        "abi": "f64",
        "source": "host_value",
    }
    assert interface["interface_hash"] == canonical_hash(
        {key: value for key, value in interface.items() if key != "interface_hash"}
    )
    with pytest.raises(FrozenInstanceError):
        identity.architecture = "gfx90a"
    forged = replace(identity, solve_record_header_bytes=200, identity_hash="")
    forged = replace(
        forged,
        identity_hash=canonical_hash(
            fgmres_rtc._identity_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcFgmresError) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_fgmres_identity_invalid"
    kernel.close()


def test_source_has_active_mask_and_explicit_little_endian_record_operations() -> None:
    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert source.count('extern "C" __global__ void') == 7
    assert source.count("engine_v2_record_active(solve_record)") == 6
    assert "engine_v2_store_i32_le" in source
    assert "engine_v2_store_f64_le" in source
    assert "kHeaderBytes = 192" in source
    assert "kRestartBytes = 72" in source
    for name, value in fgmres_rtc._source_abi_constant_bindings():
        assert source.count(f"constexpr int {name} = {value};") == 1
    assert "base + kRestartOffsetEstimatedResidualL2" in source
    assert "base + kRestartOffsetSolutionUpdateL2" in source
    assert source.count("atomicOr") == 1
    assert source.count("#pragma clang fp contract(off)") == 1
    assert source.count(
        "// engine-v2-fgmres-interface-v1: "
        + canonical_hash(fgmres_rtc._kernel_interface_payload())
    ) == 1
    assert "kOffsetRestartDimension = 60" in source
    assert "restart_index != previous_restart + 1" in source
    assert "start_iteration != previous_iteration" in source
    assert "arnoldi_step_count > restart_dimension" in source
    assert "reorthogonalization_count > arnoldi_step_count" in source
    assert "scaled_true_residual != recomputed_scaled" in source
    assert "kRestartHintRestartCompleted && both_gates_pass" in source
    assert "kTerminationConvergedRestart" in source
    assert "kErrorRecordAbi" in source
    for symbol in SYMBOLS:
        assert source.count(f'extern "C" __global__ void {symbol}(') == 1
    for forbidden in (
        "#include",
        "hipMalloc",
        "hipMemcpy",
        "hipDeviceSynchronize",
        "hipLaunchKernelGGL",
        "--use_fast_math",
        "-ffast-math",
        "lstsq",
        "pinv",
    ):
        assert forbidden not in source


def test_all_launch_wrappers_bind_exact_scalar_and_pointer_abi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    stream = 101
    kernel.launch_record_initialize(stream, 2, 5, 0.0, 1.0e-8, 1.0e-9, 201, 202, 203)
    kernel.launch_csr_spmv(stream, 513, 1026, 211, 212, 213, 214, 215, 203)
    kernel.launch_residual(stream, 513, 221, 222, 223, 203)
    kernel.launch_copy_scale(stream, 513, -0.5, 231, 232, 203)
    kernel.launch_apply_jacobi(stream, 513, 241, 242, 243, 203)
    kernel.launch_control_terminal(stream, 1, 251, 252, 203)
    kernel.launch_record_restart(
        stream,
        1,
        0,
        2,
        2,
        1,
        1,
        7,
        1.0e-5,
        2.0e-5,
        3.0e-5,
        4.0e-5,
        5.0e-5,
        203,
    )
    assert [record["symbol"] for record in runtime.launch_records] == list(SYMBOLS)
    assert runtime.launch_records[0]["arguments"][:3] == (2, 5, 3)
    assert runtime.launch_records[0]["grid"] == (1, 1, 1)
    assert runtime.launch_records[1]["arguments"][:2] == (513, 1026)
    assert runtime.launch_records[1]["grid"] == (3, 1, 1)
    assert runtime.launch_records[3]["arguments"][:2] == (513, -0.5)
    assert runtime.launch_records[-1]["arguments"][:7] == (1, 0, 2, 2, 1, 1, 7)
    assert all(record["block"] == (HIP_RTC_FGMRES_BLOCK_SIZE, 1, 1) for record in runtime.launch_records)
    assert kernel.pending_stream_count == 1
    with pytest.raises(HipRtcFgmresError) as fence_error:
        kernel.close()
    assert fence_error.value.code == "hip_rtc_fgmres_completion_fence_required"
    kernel.acknowledge_stream_completion(stream)
    kernel.close()
    assert runtime.unload_calls == 1


def test_launch_contract_and_extent_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    assert solve_record_byte_length(0) == 192
    assert solve_record_byte_length(3) == 408
    for invalid in (-1, True, 1.0, 4097):
        with pytest.raises(HipRtcFgmresError) as extent_error:
            solve_record_byte_length(invalid)  # type: ignore[arg-type]
        assert extent_error.value.code == "hip_rtc_fgmres_launch_contract_invalid"
    invalid_calls = (
        lambda: kernel.launch_record_initialize(1, 0, 5, 0.0, 0.0, 0.0, 2, 3, 4),
        lambda: kernel.launch_csr_spmv(1, 3, 2, 2, 3, 4, 5, 6, 7),
        lambda: kernel.launch_copy_scale(1, 3, float("nan"), 2, 3, 4),
        lambda: kernel.launch_control_terminal(1, 3, 2, 3, 4),
        lambda: kernel.launch_record_restart(
            1, 1, 0, 2, 1, 0, 0, 0, 1.0, 1.0, 1.0, 1.0, 1.0, 2
        ),
        lambda: kernel.launch_record_restart(
            1, 1, 0, 2, 2, 3, 1, 0, 1.0, 1.0, 1.0, 1.0, 1.0, 2
        ),
        lambda: kernel.launch_record_restart(
            1, 1, 0, 2, 2, 1, 1, 1 << 5, 1.0, 1.0, 1.0, 1.0, 1.0, 2
        ),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcFgmresError) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_launch_contract_invalid"
    kernel.close()


def test_source_interface_marker_fails_closed_on_declared_abi_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fgmres_rtc._kernel_interface_payload()
    drifted = dict(original)
    drifted["control_modes"] = {
        **original["control_modes"],
        "candidate_true_residual": 9,
    }
    monkeypatch.setattr(
        fgmres_rtc,
        "_kernel_interface_payload",
        lambda: drifted,
    )
    with pytest.raises(HipRtcFgmresError) as error:
        fgmres_rtc._fixed_source()
    assert error.value.code == "hip_rtc_fgmres_source_invalid"


def test_source_constant_drift_fails_closed_before_compile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    drifted = KERNEL_SOURCE.read_text(encoding="utf-8").replace(
        "constexpr int kOffsetRhsL2 = 64;",
        "constexpr int kOffsetRhsL2 = 65;",
        1,
    )
    drifted_path = tmp_path / "engine_v2_fgmres_v1.hip.cpp"
    drifted_path.write_text(drifted, encoding="utf-8")
    monkeypatch.setattr(fgmres_rtc, "_SOURCE_PATH", drifted_path)
    with pytest.raises(HipRtcFgmresError) as error:
        fgmres_rtc._fixed_source()
    assert error.value.code == "hip_rtc_fgmres_source_invalid"


def test_missing_symbol_and_retryable_unload_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_runtime = FakeLoadedRuntime(missing_symbol=SYMBOLS[-1])
    with pytest.raises(HipRtcFgmresError) as missing_error:
        _compile_fake(monkeypatch, missing_runtime)
    assert missing_error.value.code == "hip_rtc_fgmres_symbol_missing"
    assert missing_runtime.unload_calls == 1

    retry_runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    kernel, _, _ = _compile_fake(monkeypatch, retry_runtime)
    with pytest.raises(HipRtcFgmresError) as unload_error:
        kernel.close()
    assert unload_error.value.code == "hip_rtc_fgmres_module_unload_failed"
    assert not kernel.closed
    kernel.close()
    assert kernel.closed
    assert retry_runtime.unload_calls == 2


def test_multiple_streams_and_ambiguous_launch_exception_preserve_fences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    kernel.launch_residual(100, 3, 2, 3, 4, 5)
    kernel.launch_residual(101, 3, 2, 3, 4, 5)
    assert kernel.pending_stream_count == 2
    with pytest.raises(HipRtcFgmresError) as unknown:
        kernel.acknowledge_stream_completion(102)
    assert unknown.value.code == "hip_rtc_fgmres_launch_contract_invalid"
    kernel.acknowledge_stream_completion(100)
    with pytest.raises(HipRtcFgmresError) as pending:
        kernel.close()
    assert pending.value.code == "hip_rtc_fgmres_completion_fence_required"
    kernel.acknowledge_stream_completion(101)
    kernel.close()

    ambiguous_runtime = FakeLoadedRuntime(launch_exception=True)
    ambiguous, _, _ = _compile_fake(monkeypatch, ambiguous_runtime)
    with pytest.raises(HipRtcFgmresError) as launch_error:
        ambiguous.launch_residual(103, 3, 2, 3, 4, 5)
    assert launch_error.value.code == "hip_rtc_fgmres_kernel_launch_failed"
    assert ambiguous.pending_stream_count == 1
    with pytest.raises(HipRtcFgmresError):
        ambiguous.close()
    ambiguous.acknowledge_stream_completion(103)
    ambiguous.close()


def test_device_error_bits_are_stable_and_nonoverlapping() -> None:
    assert (
        FGMRES_DEVICE_ERROR_NONE,
        FGMRES_DEVICE_ERROR_INVALID_CONTROL_OR_GEOMETRY,
        FGMRES_DEVICE_ERROR_CSR_STRUCTURE,
        FGMRES_DEVICE_ERROR_NONFINITE_INPUT,
        FGMRES_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
        FGMRES_DEVICE_ERROR_RECORD_ABI,
        FGMRES_DEVICE_ERROR_JACOBI,
    ) == (0, 1, 2, 4, 8, 16, 32)


def test_fgmres_rtc_public_api_is_reexported_at_both_engine_boundaries() -> None:
    names = (
        "HIP_RTC_FGMRES_IDENTITY_SCHEMA_VERSION",
        "HIP_RTC_FGMRES_ABI_VERSION",
        "HIP_RTC_FGMRES_KERNEL_NAME",
        "HipRtcFgmresKernel",
        "HipRtcFgmresKernelIdentity",
        "HipRtcFgmresError",
        "compile_hip_rtc_fgmres_kernel",
        "hip_fgmres_solve_record_abi_payload_v1",
        "solve_record_byte_length",
    )
    for module in (assembly_backend, engine_v2):
        for name in names:
            assert name in module.__all__
            assert getattr(module, name) is getattr(assembly_backend, name)


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
    hiprtc = fgmres_rtc._load_hiprtc_api(library)
    status, major, minor = hiprtc.version()
    assert status == 0
    assert major >= 0 and minor >= 0
    code_object, compile_log = fgmres_rtc._compile_fixed_source(
        hiprtc,
        fgmres_rtc._fixed_source(),
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
    code_path = tmp_path / "fgmres-substrate.co"
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
