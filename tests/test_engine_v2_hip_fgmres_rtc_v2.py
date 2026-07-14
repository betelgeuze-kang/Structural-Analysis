from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import dis
import gc
import inspect
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from typing import Any
import weakref

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_rtc_v2,
)
import structural_analysis.engine_v2 as engine_v2  # noqa: E402
import structural_analysis.engine_v2.assembly_backend as assembly_backend  # noqa: E402
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (  # noqa: E402
    compile_hip_fgmres_global_schedule_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_first_column_candidate_preparation_schedule_payload_v2,
    hip_fgmres_first_column_candidate_residual_schedule_payload_v2,
    hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_first_column_completion_schedule_payload_v2,
    hip_fgmres_first_column_predecessor_validation_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (  # noqa: E402
    HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE,
    HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
    HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL,
    HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
    HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK,
    HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE,
    HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
    FgmresV2FirstColumnCandidatePreparationLaunch,
    FgmresV2FirstColumnCandidateResidualLaunch,
    FgmresV2FirstColumnCandidateScaleMetricsLaunch,
    FgmresV2FirstColumnCheckpointTransactionLaunch,
    FgmresV2FirstColumnCompletionLaunch,
    FgmresV2FirstColumnPredecessorValidationLaunch,
    FgmresV2FirstColumnReductionLaunch,
    HipRtcFgmresV2Error,
    compile_hip_rtc_fgmres_v2_kernel,
    first_column_candidate_preparation_launches_v2,
    first_column_candidate_residual_launches_v2,
    first_column_candidate_scale_metrics_launches_v2,
    first_column_checkpoint_transaction_launches_v2,
    first_column_completion_launches_v2,
    first_column_predecessor_validation_launch_v2,
    first_column_reduction_launches_v2,
    initial_reduction_launches_v2,
    reduction_stage_output_counts_v2,
    solve_record_byte_length_v2,
)
from structural_analysis.engine_v2.backends.hip.types import (  # noqa: E402
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    LoadedHipRuntime,
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    HipRtcLibraryIdentity,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (  # noqa: E402
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
    replay_fgmres_gpu_tree_initial_v2,
)


KERNEL_SOURCE = (
    SRC_ROOT
    / "structural_analysis"
    / "engine_v2"
    / "assembly_backend"
    / "kernels"
    / "engine_v2_fgmres_v2.hip.cpp"
)
SYMBOLS = (
    HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
    HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
    HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL,
    HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
)
ABI_KINDS = {
    HIP_RTC_FGMRES_V2_CONTROL_SYMBOL: "i" * 11 + "d" * 5 + "p" * 3,
    HIP_RTC_FGMRES_V2_VECTOR_SYMBOL: "i" * 7 + "p" * 11,
    HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL: "i" * 7 + "p" * 9,
    HIP_RTC_FGMRES_V2_REDUCE_SYMBOL: "i" * 8 + "p" * 9,
}

_SEALED_NATIVE_RUNTIME_SOURCE = r"""
#include <stdint.h>
#include <string.h>

typedef void (*test_hook_t)(int);

static int current_device = 0;
static int load_calls = 0;
static int function_calls = 0;
static int launch_calls = 0;
static int memset_calls = 0;
static int sync_calls = 0;
static int query_calls = 0;
static int unload_calls = 0;
static int get_device_calls = 0;
static test_hook_t test_hook = 0;

int hipInit(unsigned int flags) { (void)flags; return 0; }
int hipGetDeviceCount(int *count) { *count = 1; return 0; }
int hipDeviceGetName(void *name, int length, int ordinal) {
    (void)ordinal;
    const char *value = "sealed-native-fixture";
    if (length <= 0) return 1;
    strncpy((char *)name, value, (size_t)length - 1);
    ((char *)name)[length - 1] = '\0';
    return 0;
}
int hipRuntimeGetVersion(int *version) { *version = 60000000; return 0; }
int hipDriverGetVersion(int *version) { *version = 60000000; return 0; }
const char *hipGetErrorString(int status) { (void)status; return "sealed error"; }
int hipGetDevice(int *ordinal) {
    get_device_calls += 1;
    if (test_hook) test_hook(3);
    *ordinal = current_device;
    return 0;
}
int hipSetDevice(int ordinal) { current_device = ordinal; return 0; }
int hipMemGetInfo(size_t *free_bytes, size_t *total_bytes) {
    *free_bytes = (size_t)1 << 30;
    *total_bytes = (size_t)2 << 30;
    return 0;
}
int hipStreamCreateWithFlags(void **stream, unsigned int flags) {
    (void)flags;
    *stream = (void *)(uintptr_t)1025;
    return 0;
}
int hipStreamDestroy(void *stream) { (void)stream; return 0; }
int hipMalloc(void **pointer, size_t byte_length) {
    (void)byte_length;
    *pointer = (void *)(uintptr_t)2049;
    return 0;
}
int hipFree(void *pointer) { (void)pointer; return 0; }
int hipMemcpyAsync(
    void *destination,
    void *source,
    size_t byte_length,
    int kind,
    void *stream
) {
    (void)destination; (void)source; (void)byte_length; (void)kind; (void)stream;
    return 0;
}
int hipMemcpy(
    void *destination,
    void *source,
    size_t byte_length,
    int kind
) {
    (void)destination; (void)source; (void)byte_length; (void)kind;
    return 0;
}
int hipMemsetAsync(
    void *destination,
    int value,
    size_t byte_length,
    void *stream
) {
    (void)destination; (void)value; (void)byte_length; (void)stream;
    if (test_hook) test_hook(5);
    memset_calls += 1;
    return 0;
}
int hipModuleLoadData(void **module, void *image) {
    (void)image;
    load_calls += 1;
    *module = (void *)(uintptr_t)513;
    return 0;
}
int hipModuleGetFunction(void **function, void *module, const char *symbol) {
    (void)module;
    (void)symbol;
    function_calls += 1;
    *function = (void *)(uintptr_t)(768 + function_calls);
    return 0;
}
int hipModuleLaunchKernel(
    void *function,
    unsigned int grid_x,
    unsigned int grid_y,
    unsigned int grid_z,
    unsigned int block_x,
    unsigned int block_y,
    unsigned int block_z,
    unsigned int shared,
    void *stream,
    void **parameters,
    void **extra
) {
    (void)function; (void)grid_x; (void)grid_y; (void)grid_z;
    (void)block_x; (void)block_y; (void)block_z; (void)shared;
    (void)stream; (void)parameters; (void)extra;
    if (test_hook) test_hook(1);
    launch_calls += 1;
    return 0;
}
int hipStreamSynchronize(void *stream) {
    (void)stream;
    if (test_hook) test_hook(2);
    sync_calls += 1;
    return 0;
}
int hipStreamQuery(void *stream) {
    (void)stream;
    if (test_hook) test_hook(6);
    query_calls += 1;
    return 0;
}
int hipModuleUnload(void *module) {
    (void)module;
    if (test_hook) test_hook(4);
    unload_calls += 1;
    return 0;
}
void testSetHook(test_hook_t hook) { test_hook = hook; }
int testLoadCalls(void) { return load_calls; }
int testFunctionCalls(void) { return function_calls; }
int testLaunchCalls(void) { return launch_calls; }
int testMemsetCalls(void) { return memset_calls; }
int testSyncCalls(void) { return sync_calls; }
int testQueryCalls(void) { return query_calls; }
int testUnloadCalls(void) { return unload_calls; }
int testGetDeviceCalls(void) { return get_device_calls; }
"""


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
        return 0

    def program_log(self, program: Any) -> str:
        assert _pointer_value(program) == 257
        return ""

    def code_object(self, program: Any) -> bytes:
        assert _pointer_value(program) == 257
        return b"fake-fgmres-recurrence-v2-code-object"

    def destroy_program(self, program: Any) -> int:
        assert _pointer_value(program) == 257
        return 0


class FakeLoadedRuntime:
    def __init__(
        self,
        *,
        load_status: int = 0,
        missing_symbol: str | None = None,
        launch_status: int = 0,
        launch_exception: bool = False,
        unload_statuses: tuple[int, ...] = (0,),
        current_device: int = 0,
        get_device_status: int = 0,
        get_device_exception: bool = False,
        query_status: int | None = None,
        query_exception: bool = False,
    ) -> None:
        self.library_identity = HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path=None,
            sha256="sha256:" + "1" * 64,
        )
        self.load_status = load_status
        self.missing_symbol = missing_symbol
        self.launch_status = launch_status
        self.launch_exception = launch_exception
        self.unload_statuses = list(unload_statuses)
        self.current_device = current_device
        self.get_device_status = get_device_status
        self.get_device_exception = get_device_exception
        self.query_status = query_status
        self.query_exception = query_exception
        self.get_device_calls = 0
        self.load_calls = 0
        self.function_symbols: list[str] = []
        self.launch_records: list[dict[str, Any]] = []
        self.memset_streams: list[int] = []
        self.sync_streams: list[int] = []
        self.query_streams: list[int] = []
        self._stream_completion: dict[int, bool] = {}
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
            "hipGetDevice": self._get_device,
            "hipMemsetAsync": self._memset_async,
            "hipStreamSynchronize": self._synchronize,
            "hipStreamQuery": self._query,
        }[symbol]

    def _get_device(self, output: Any) -> int:
        self.get_device_calls += 1
        if self.get_device_exception:
            raise RuntimeError("injected hipGetDevice exception")
        if self.get_device_status:
            return self.get_device_status
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = ctypes.c_int(
            self.current_device
        )
        return 0

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
        stream_value = _pointer_value(stream)
        if self.launch_exception:
            assert stream_value is not None
            self._stream_completion[stream_value] = False
            raise RuntimeError("ambiguous fake launch exception")
        if self.launch_status == 0:
            assert stream_value is not None
            self._stream_completion[stream_value] = False
        return self.launch_status

    def _memset_async(
        self,
        destination: Any,
        value: Any,
        byte_length: Any,
        stream: Any,
    ) -> int:
        del destination, value, byte_length
        stream_value = _pointer_value(stream)
        assert stream_value is not None
        self.memset_streams.append(stream_value)
        self._stream_completion[stream_value] = False
        return 0

    def _synchronize(self, stream: Any) -> int:
        stream_value = _pointer_value(stream)
        assert stream_value is not None
        self.sync_streams.append(stream_value)
        self._stream_completion[stream_value] = True
        return 0

    def _query(self, stream: Any) -> int:
        stream_value = _pointer_value(stream)
        assert stream_value is not None
        self.query_streams.append(stream_value)
        if self.query_exception:
            raise RuntimeError("injected hipStreamQuery exception")
        if self.query_status is not None:
            return self.query_status
        return 0 if self._stream_completion.get(stream_value, True) else 600

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
            raise KeyboardInterrupt("injected FGMRES v2 RTC line interruption")
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
                    raise KeyboardInterrupt("injected after FGMRES v2 status STORE")
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
                        "injected after FGMRES v2 ownership transfer"
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
    runtime: FakeLoadedRuntime | None = None,
) -> tuple[Any, FakeRtcApi, FakeLoadedRuntime]:
    rtc = FakeRtcApi()
    checked_runtime = runtime or FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    return (
        compile_hip_rtc_fgmres_v2_kernel(checked_runtime, "gfx1030"),
        rtc,
        checked_runtime,
    )


def _compile_sealed_native_runtime_library(
    tmp_path: Path,
    *,
    stem: str = "sealed_native_runtime",
) -> Path:
    compiler = shutil.which("cc")
    assert compiler is not None, "a C compiler is required for the native ABI test"
    source = tmp_path / f"{stem}.c"
    library = tmp_path / f"lib{stem}.so"
    source.write_text(_SEALED_NATIVE_RUNTIME_SOURCE, encoding="utf-8")
    completed = subprocess.run(
        [
            compiler,
            "-shared",
            "-fPIC",
            "-O0",
            "-o",
            str(library),
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return library


def _launch_control(
    kernel: Any,
    stream: int,
    mode: int,
    schedule_epoch: int,
    *,
    n: int = 513,
    expected_restart: int = -1,
    expected_column: int = -1,
    row_index: int = -1,
    pass_index: int = -1,
    checkpoint_owner_token: object | None = None,
    expected_prior_pending_count: int | None = None,
) -> None:
    kernel.launch_control(
        stream,
        mode,
        schedule_epoch,
        expected_restart,
        expected_column,
        row_index,
        pass_index,
        n,
        2,
        5,
        3,
        2,
        0.0,
        1.0e-8,
        1.0e-9,
        1.0e-8,
        1.0e8,
        201,
        202,
        203,
        _checkpoint_owner_token=checkpoint_owner_token,
        _checkpoint_expected_prior_pending_count=expected_prior_pending_count,
    )


def _launch_vector(
    kernel: Any,
    stream: int,
    mode: int,
    schedule_epoch: int,
    *,
    n: int = 513,
    expected_restart: int = -1,
    expected_column: int = -1,
    logical_index: int = 0,
    gate: int | None = None,
    pointers: tuple[int, ...] = tuple(range(211, 222)),
    checkpoint_owner_token: object | None = None,
    expected_prior_pending_count: int | None = None,
) -> None:
    gates = hip_fgmres_control_state_abi_payload_v2()["vector_gate_codes"]
    kernel.launch_vector(
        stream,
        mode,
        gates["ACTIVE"] if gate is None else gate,
        schedule_epoch,
        expected_restart,
        expected_column,
        n,
        logical_index,
        *pointers,
        _checkpoint_owner_token=checkpoint_owner_token,
        _checkpoint_expected_prior_pending_count=expected_prior_pending_count,
    )


def _launch_spmv(
    kernel: Any,
    stream: int,
    schedule_epoch: int,
    *,
    n: int = 513,
    mode: int | None = None,
    expected_restart: int = -1,
    expected_column: int = -1,
    logical_index: int = 0,
    pointers: tuple[int, ...] = tuple(range(231, 240)),
    checkpoint_owner_token: object | None = None,
    expected_prior_pending_count: int | None = None,
) -> None:
    modes = hip_fgmres_control_state_abi_payload_v2()["spmv_mode_codes"]
    kernel.launch_csr_spmv_indexed(
        stream,
        modes["INITIAL"] if mode is None else mode,
        schedule_epoch,
        expected_restart,
        expected_column,
        n,
        n * 2,
        logical_index,
        *pointers,
        _checkpoint_owner_token=checkpoint_owner_token,
        _checkpoint_expected_prior_pending_count=expected_prior_pending_count,
    )


def _launch_reduction(
    kernel: Any,
    stream: int,
    *,
    mode: int,
    target: int,
    schedule_epoch: int,
    reduction_epoch: int,
    value_count: int,
    expected_restart: int = -1,
    expected_column: int = -1,
    logical_index: int = 0,
    input_pointer: int = 246,
    output_pointer: int = 247,
    checkpoint_owner_token: object | None = None,
    expected_prior_pending_count: int | None = None,
) -> None:
    kernel.launch_reduction(
        stream,
        mode,
        target,
        schedule_epoch,
        expected_restart,
        expected_column,
        reduction_epoch,
        value_count,
        logical_index,
        241,
        242,
        243,
        244,
        245,
        input_pointer,
        output_pointer,
        248,
        249,
        _checkpoint_owner_token=checkpoint_owner_token,
        _checkpoint_expected_prior_pending_count=expected_prior_pending_count,
    )


def test_public_compiler_signature_remains_three_arguments() -> None:
    assert tuple(inspect.signature(compile_hip_rtc_fgmres_v2_kernel).parameters) == (
        "loaded_runtime",
        "architecture",
        "hiprtc_library",
    )


@pytest.mark.parametrize(
    "phase",
    ("after_isolated_set", "after_kernel_publish", "at_frame_disarm"),
)
def test_handoff_interruptions_preserve_caller_context_and_exact_owner(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    sentinel_target = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    sentinel = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoffFrame(sentinel_target)
    context_token = fgmres_rtc_v2._KERNEL_HANDOFF.set(sentinel)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    published: list[Any] = []
    compiler_calls = 0
    interruption = KeyboardInterrupt(f"interrupt FGMRES v2 handoff at {phase}")

    def compile_then_interrupt(
        loaded_runtime: Any,
        architecture: str,
        hiprtc_library: str | Path | None,
    ) -> Any:
        nonlocal compiler_calls
        compiler_calls += 1
        kernel = compile_hip_rtc_fgmres_v2_kernel(
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
                fgmres_rtc_v2._compile_v2_with_handoff(
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
                    fgmres_rtc_v2._compile_v2_with_handoff,
                    source_fragment,
                ) as line_interrupt,
                pytest.raises(KeyboardInterrupt),
            ):
                fgmres_rtc_v2._compile_v2_with_handoff(
                    compile_then_interrupt,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert line_interrupt.fired

        assert fgmres_rtc_v2._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is None
        assert compiler_calls == int(phase != "after_isolated_set")
        assert handoff.kernel is (None if not published else published[0])
        if handoff.kernel is not None:
            owned_kernel = handoff.kernel
            unload_calls = runtime.unload_calls
            owned_kernel.close()
            owned_kernel.close()
            assert runtime.unload_calls == unload_calls + 1

        direct_kernel = compile_hip_rtc_fgmres_v2_kernel(runtime, "gfx1030")
        assert fgmres_rtc_v2._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is direct_kernel
        unload_calls = runtime.unload_calls
        direct_kernel.close()
        direct_kernel.close()
        assert runtime.unload_calls == unload_calls + 1
    finally:
        fgmres_rtc_v2._KERNEL_HANDOFF.reset(context_token)


def test_same_handoff_concurrent_publication_is_one_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtimes = (FakeLoadedRuntime(), FakeLoadedRuntime())
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    publish_barrier = threading.Barrier(2)
    handoff_type = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff
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
            kernel = fgmres_rtc_v2._compile_v2_with_handoff(
                compile_hip_rtc_fgmres_v2_kernel,
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
    assert isinstance(errors[0], HipRtcFgmresV2Error)
    assert errors[0].code == "hip_rtc_fgmres_v2_kernel_handoff_invalid"
    assert sum(runtime.load_calls for runtime in runtimes) == 1
    assert handoff._publication_state == "published"
    assert handoff.kernel is kernels[0]
    kernels[0].close()
    assert sum(runtime.unload_calls for runtime in runtimes) == 1
    assert handoff.kernel is None


def test_module_cleanup_owner_is_published_before_native_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    native_load = runtime._load
    observed_owner: list[Any] = []

    def assert_prepublished(output: Any, image: Any) -> int:
        assert handoff._cell is not None
        owner = handoff._cell.owner
        assert type(owner) is fgmres_rtc_v2._HipRtcFgmresV2ModuleCleanupOwner
        assert not owner.owns_module
        observed_owner.append(owner)
        return native_load(output, image)

    monkeypatch.setattr(runtime, "_load", assert_prepublished)
    kernel = fgmres_rtc_v2._compile_v2_with_handoff(
        compile_hip_rtc_fgmres_v2_kernel,
        handoff,
        runtime,
        "gfx1030",
        None,
    )
    stale_owner = observed_owner[0]
    assert handoff.kernel is kernel
    assert not stale_owner.owns_module
    stale_owner.close()
    stale_owner.close()
    assert runtime.unload_calls == 0
    kernel.close()
    kernel.close()
    assert runtime.unload_calls == 1


@pytest.mark.parametrize("phase", ("before_transfer", "after_transfer"))
def test_ownership_transfer_interruption_retains_exactly_one_authority(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    if phase == "before_transfer":
        interruption_context: Any = _SingleFireRtcLineInterrupt(
            fgmres_rtc_v2._transfer_fgmres_v2_module_ownership,
            "cell.owner = kernel",
        )
    else:
        interruption_context = _SingleFireAfterAttributeStoreInterrupt(
            fgmres_rtc_v2._transfer_fgmres_v2_module_ownership,
            "cell.owner = kernel",
            "owner",
        )

    with interruption_context as interruption, pytest.raises(KeyboardInterrupt):
        fgmres_rtc_v2._compile_v2_with_handoff(
            compile_hip_rtc_fgmres_v2_kernel,
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
        assert type(kernel) is fgmres_rtc_v2.HipRtcFgmresV2Kernel
        stale_owner = handoff._cell.preowner
        assert stale_owner is not None
        assert not stale_owner.owns_module
        stale_owner.close()
        assert runtime.unload_calls == 0
        assert handoff._cell.owner is kernel
        kernel.close()
        assert runtime.unload_calls == 1
        assert handoff._cell.owner is None


def test_unload_and_promotion_are_serialized_by_shared_ownership_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    native_unload = runtime._unload
    unload_entered = threading.Event()
    allow_unload = threading.Event()
    promotion_waiting = threading.Event()
    cleanup_threads: list[threading.Thread] = []

    def blocking_unload(module: Any) -> int:
        unload_entered.set()
        assert allow_unload.wait(timeout=5.0)
        return native_unload(module)

    monkeypatch.setattr(runtime, "_unload", blocking_unload)
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    original_promote = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff.promote

    def unload_then_promote(target: Any, owner: Any, kernel: Any) -> None:
        cleanup_thread = threading.Thread(target=owner.close, daemon=True)
        cleanup_threads.append(cleanup_thread)
        cleanup_thread.start()
        assert unload_entered.wait(timeout=5.0)
        promotion_waiting.set()
        original_promote(target, owner, kernel)

    monkeypatch.setattr(
        fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff,
        "promote",
        unload_then_promote,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        compilation = executor.submit(
            fgmres_rtc_v2._compile_v2_with_handoff,
            compile_hip_rtc_fgmres_v2_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
        assert promotion_waiting.wait(timeout=5.0)
        assert not compilation.done()
        allow_unload.set()
        with pytest.raises(HipRtcFgmresV2Error) as caught:
            compilation.result(timeout=5.0)
    for cleanup_thread in cleanup_threads:
        cleanup_thread.join(timeout=5.0)
        assert not cleanup_thread.is_alive()
    assert caught.value.code == "hip_rtc_fgmres_v2_kernel_handoff_invalid"
    assert runtime.unload_calls == 1
    assert handoff.kernel is None
    assert handoff._cell is not None
    assert handoff._cell.owner is None
    assert handoff._cell.unload_disposition == "terminal"


@pytest.mark.parametrize(
    "phase",
    ("after_native_load", "after_status_store", "at_first_status_check"),
)
def test_module_load_interruptions_recover_preallocated_module_owner(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    if phase == "after_native_load":
        native_load = runtime._load

        def load_then_interrupt(output: Any, image: Any) -> int:
            assert native_load(output, image) == 0
            raise KeyboardInterrupt("injected after native FGMRES v2 module load")

        monkeypatch.setattr(runtime, "_load", load_then_interrupt)

    sentinel_target = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    sentinel = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoffFrame(sentinel_target)
    context_token = fgmres_rtc_v2._KERNEL_HANDOFF.set(sentinel)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    try:
        if phase == "after_status_store":
            with (
                _SingleFireAfterStoreInterrupt(
                    fgmres_rtc_v2._compile_v2_impl,
                    "status = runtime.load_module_into",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                fgmres_rtc_v2._compile_v2_with_handoff(
                    compile_hip_rtc_fgmres_v2_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        elif phase == "at_first_status_check":
            with (
                _SingleFireRtcLineInterrupt(
                    fgmres_rtc_v2._compile_v2_impl,
                    "if status != 0 or not module.value:",
                ) as interruption,
                pytest.raises(KeyboardInterrupt),
            ):
                fgmres_rtc_v2._compile_v2_with_handoff(
                    compile_hip_rtc_fgmres_v2_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )
            assert interruption.fired
        else:
            with pytest.raises(KeyboardInterrupt):
                fgmres_rtc_v2._compile_v2_with_handoff(
                    compile_hip_rtc_fgmres_v2_kernel,
                    handoff,
                    runtime,
                    "gfx1030",
                    None,
                )

        assert runtime.load_calls == 1
        assert runtime.unload_calls == 1
        assert handoff.kernel is None
        assert fgmres_rtc_v2._KERNEL_HANDOFF.get() is sentinel
        assert sentinel_target.kernel is None
    finally:
        fgmres_rtc_v2._KERNEL_HANDOFF.reset(context_token)


@pytest.mark.parametrize(
    "phase",
    ("before_cleanup_helper_call", "at_cleanup_helper_first_line"),
)
def test_prepublished_module_owner_survives_cleanup_entry_interruption(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(missing_symbol=SYMBOLS[1])
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    if phase == "before_cleanup_helper_call":
        trace_target = fgmres_rtc_v2._compile_v2_impl
        source_fragment = "_cleanup_loaded_module("
    else:
        trace_target = fgmres_rtc_v2._cleanup_loaded_module
        source_fragment = "primary_log = ("

    with (
        _SingleFireRtcLineInterrupt(trace_target, source_fragment) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        fgmres_rtc_v2._compile_v2_with_handoff(
            compile_hip_rtc_fgmres_v2_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.function_symbols == list(SYMBOLS[:2])
    assert runtime.unload_calls == 0

    owner = handoff.kernel
    assert type(owner) is fgmres_rtc_v2._HipRtcFgmresV2ModuleCleanupOwner
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
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime(missing_symbol=SYMBOLS[1])
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    with (
        _SingleFireRtcLineInterrupt(
            fgmres_rtc_v2._compile_v2_impl,
            "_cleanup_loaded_module(",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_fgmres_v2_kernel(runtime, "gfx1030")
    assert interruption.fired
    assert runtime.load_calls == 1
    assert runtime.function_symbols == list(SYMBOLS[:2])
    assert runtime.unload_calls == 1


def test_direct_compiler_reclaims_kernel_after_transfer_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    with (
        _SingleFireAfterAttributeStoreInterrupt(
            fgmres_rtc_v2._transfer_fgmres_v2_module_ownership,
            "cell.owner = kernel",
            "owner",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        compile_hip_rtc_fgmres_v2_kernel(runtime, "gfx1030")
    gc.collect()
    assert interruption.fired
    assert runtime.unload_calls == 1
    assert list(fgmres_rtc_v2._KERNEL_BINDINGS.items()) == []


def test_bind_interruption_recovers_the_prepublished_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    native_bind = runtime._function

    def bind_then_interrupt(output: Any, module: Any, symbol: bytes) -> int:
        assert native_bind(output, module, symbol) == 0
        raise KeyboardInterrupt("injected after native FGMRES v2 symbol bind")

    monkeypatch.setattr(runtime, "_function", bind_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        fgmres_rtc_v2._compile_v2_with_handoff(
            compile_hip_rtc_fgmres_v2_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    assert runtime.load_calls == 1
    assert runtime.function_symbols == [SYMBOLS[0]]
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_constructor_registry_publication_interruption_leaves_no_strong_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InterruptingRegistry(weakref.WeakKeyDictionary[Any, Any]):
        def __init__(self) -> None:
            super().__init__()
            self.fired = False

        def __setitem__(self, key: Any, value: Any) -> None:
            super().__setitem__(key, value)
            if not self.fired:
                self.fired = True
                raise KeyboardInterrupt(
                    "injected after FGMRES v2 binding registry publication"
                )

    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    registry = InterruptingRegistry()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    monkeypatch.setattr(fgmres_rtc_v2, "_KERNEL_BINDINGS", registry)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    with pytest.raises(KeyboardInterrupt):
        fgmres_rtc_v2._compile_v2_with_handoff(
            compile_hip_rtc_fgmres_v2_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    gc.collect()
    assert registry.fired
    assert list(registry.items()) == []
    assert runtime.unload_calls == 1
    assert handoff.kernel is None


def test_promotion_interruption_hands_off_the_exact_registered_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rtc = FakeRtcApi()
    runtime = FakeLoadedRuntime()
    monkeypatch.setattr(fgmres_rtc_v2, "_load_hiprtc_api", lambda library: rtc)
    handoff = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff()
    original_promote = fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff.promote

    def promote_then_interrupt(
        target: Any,
        owner: Any,
        kernel: Any,
    ) -> None:
        original_promote(target, owner, kernel)
        raise KeyboardInterrupt("injected after exact FGMRES v2 kernel promotion")

    monkeypatch.setattr(
        fgmres_rtc_v2._HipRtcFgmresV2KernelHandoff,
        "promote",
        promote_then_interrupt,
    )
    with pytest.raises(KeyboardInterrupt):
        fgmres_rtc_v2._compile_v2_with_handoff(
            compile_hip_rtc_fgmres_v2_kernel,
            handoff,
            runtime,
            "gfx1030",
            None,
        )
    kernel = handoff.kernel
    assert type(kernel) is fgmres_rtc_v2.HipRtcFgmresV2Kernel
    assert fgmres_rtc_v2._KERNEL_BINDINGS.get(kernel) is not None
    assert runtime.unload_calls == 0
    kernel.close()
    assert runtime.unload_calls == 1
    assert fgmres_rtc_v2._KERNEL_BINDINGS.get(kernel) is None


def test_failed_load_cleanup_owner_retries_only_known_nonzero_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11, unload_statuses=(9, 0))
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        _compile_fake(monkeypatch, runtime)
    error = caught.value
    assert error.code == "hip_rtc_fgmres_v2_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert owner.owns_module
    assert not owner.closed
    assert runtime.unload_calls == 1

    owner.close()
    owner.close()
    assert owner.closed
    assert not owner.owns_module
    assert runtime.unload_calls == 2


def test_cleanup_side_effect_exception_is_uncertain_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11)
    native_unload = runtime._unload

    def unload_then_raise(module: Any) -> int:
        assert native_unload(module) == 0
        raise RuntimeError("interrupt after native FGMRES v2 module unload")

    monkeypatch.setattr(runtime, "_unload", unload_then_raise)
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        _compile_fake(monkeypatch, runtime)
    error = caught.value
    assert error.code == "hip_rtc_fgmres_v2_module_cleanup_failed"
    owner = error.cleanup_owner
    assert owner is not None
    assert owner.owns_module
    assert runtime.unload_calls == 1

    with pytest.raises(HipRtcFgmresV2Error) as uncertain:
        owner.close()
    assert uncertain.value.code == (
        "hip_rtc_fgmres_v2_module_cleanup_outcome_uncertain"
    )
    assert uncertain.value.cleanup_owner is owner
    assert runtime.unload_calls == 1


def test_cleanup_known_success_finalize_interruption_does_not_double_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11, unload_statuses=(9, 0))
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        _compile_fake(monkeypatch, runtime)
    owner = caught.value.cleanup_owner
    assert owner is not None
    original_finish = type(owner)._finish_unload_success
    interruption = KeyboardInterrupt(
        "injected before FGMRES v2 cleanup-owner finalization"
    )
    fired = False

    def interrupt_finish(target: Any) -> None:
        nonlocal fired
        if not fired:
            fired = True
            assert target._unload_disposition == "external_unload_succeeded"
            raise interruption
        original_finish(target)

    monkeypatch.setattr(type(owner), "_finish_unload_success", interrupt_finish)
    with pytest.raises(KeyboardInterrupt) as interrupted:
        owner.close()
    assert interrupted.value is interruption
    assert runtime.unload_calls == 2
    assert owner._unload_disposition == "external_unload_succeeded"

    owner.close()
    owner.close()
    assert owner.closed
    assert runtime.unload_calls == 2


@pytest.mark.parametrize("phase", ("after_closed_prefix", "after_owner_release"))
def test_cleanup_terminalization_prefix_is_retryable_without_double_unload(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    runtime = FakeLoadedRuntime(load_status=11, unload_statuses=(9, 0))
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        _compile_fake(monkeypatch, runtime)
    owner = caught.value.cleanup_owner
    assert owner is not None
    if phase == "after_closed_prefix":
        interruption_context: Any = _SingleFireAfterAttributeStoreInterrupt(
            type(owner)._finish_unload_success,
            "self._closed = True",
            "_closed",
        )
    else:
        interruption_context = _SingleFireAfterAttributeStoreInterrupt(
            type(owner)._finish_unload_success,
            "cell.owner = None",
            "owner",
        )

    with interruption_context as interruption, pytest.raises(KeyboardInterrupt):
        owner.close()
    assert interruption.fired
    assert runtime.unload_calls == 2
    assert owner._unload_disposition == "terminal"
    assert owner._module.value is None
    owner.close()
    owner.close()
    assert owner.closed
    assert owner._ownership_cell.owner is None
    assert owner._ownership_cell.preowner is None
    assert runtime.unload_calls == 2


@pytest.mark.parametrize(
    ("phase", "error_type"),
    [
        ("known_success_finalize", KeyboardInterrupt),
        ("after_status_store", KeyboardInterrupt),
        ("runtime_side_effect", KeyboardInterrupt),
        ("runtime_side_effect", RuntimeError),
        ("before_call", KeyboardInterrupt),
    ],
)
def test_main_unload_disposition_never_retries_success_or_uncertain_outcome(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    error_type: type[BaseException],
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    injected_error = error_type(f"injected {phase} FGMRES v2 unload interruption")
    original_unload = runtime._unload
    original_finish = type(kernel)._finish_unload_success
    fired = False

    def interrupting_unload(module: Any) -> int:
        nonlocal fired
        if not fired:
            fired = True
            if phase == "before_call":
                raise injected_error
            status = original_unload(module)
            assert status == 0
            assert runtime.unload_calls == 1
            raise injected_error
        return original_unload(module)

    def interrupting_finish(
        target: Any,
        *,
        expected_witness: Any = None,
    ) -> None:
        nonlocal fired
        if not fired:
            fired = True
            assert target._unload_disposition == "external_unload_succeeded"
            assert runtime.unload_calls == 1
            raise injected_error
        original_finish(target, expected_witness=expected_witness)

    if phase == "known_success_finalize":
        monkeypatch.setattr(
            type(kernel),
            "_finish_unload_success",
            interrupting_finish,
        )
    elif phase != "after_status_store":
        witness = fgmres_rtc_v2._KERNEL_BINDINGS[kernel]
        fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = replace(
            witness,
            unload_callable=interrupting_unload,
        )
        monkeypatch.setattr(kernel._runtime, "_unload", interrupting_unload)

    if phase == "after_status_store":
        with (
            _SingleFireAfterStoreInterrupt(
                type(kernel).close,
                "status = int(",
            ) as interruption,
            pytest.raises(KeyboardInterrupt),
        ):
            kernel.close()
        assert interruption.fired
        fired = True
    elif error_type is RuntimeError:
        with pytest.raises(HipRtcFgmresV2Error) as first:
            kernel.close()
        assert first.value.code == "hip_rtc_fgmres_v2_module_unload_failed"
        assert isinstance(first.value.__cause__, RuntimeError)
    else:
        with pytest.raises(KeyboardInterrupt) as first:
            kernel.close()
        assert first.value is injected_error

    assert fired
    if phase in {"known_success_finalize", "after_status_store"}:
        assert kernel._unload_disposition == "external_unload_succeeded"
        assert runtime.unload_calls == 1
        kernel.close()
        kernel.close()
        assert kernel.closed
        assert runtime.unload_calls == 1
        assert kernel._module_pointer == 0
        assert kernel._function_pointers == ()
    else:
        assert kernel._unload_disposition == "unload_outcome_uncertain"
        expected_calls = int(phase == "runtime_side_effect")
        assert runtime.unload_calls == expected_calls
        with pytest.raises(HipRtcFgmresV2Error) as uncertain:
            kernel.close()
        assert uncertain.value.code == (
            "hip_rtc_fgmres_v2_module_unload_outcome_uncertain"
        )
        assert not kernel.closed
        assert runtime.unload_calls == expected_calls
        assert kernel._module_pointer == 513


def test_identity_binds_canonical_v2_control_record_and_four_symbol_interface(
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
    assert manifest["kernel_symbols"] == list(SYMBOLS)
    assert manifest["recurrence_abi_version"] == (HIP_FGMRES_RECURRENCE_ABI_VERSION_V2)
    control = manifest["control_state_abi"]
    record = manifest["solve_record_abi"]
    interface = manifest["kernel_interface"]
    assert control["byte_length"] == HIP_FGMRES_CONTROL_STATE_BYTES_V2 == 256
    assert next(
        row for row in control["fields"] if row["name"] == "schedule_epoch"
    ) == {"name": "schedule_epoch", "dtype": "i32", "offset_bytes": 112}
    assert control["post_init_values"]["schedule_epoch"] == 1
    assert (
        control["post_init_values"]["phase"]
        == control["phase_codes"]["rhs_metrics"]
        == 1
    )
    assert control["reduction_target_codes"]["NONE"] == 0
    assert "NONE" not in control["reduction_valid_bits"]
    assert record["recurrence_abi_version"] == 2
    assert record["producer_contract"] == "single_v2_code_object_only"
    assert record["header_initial_values"] == {"recurrence_abi_version": 2}
    assert interface == {
        **hip_fgmres_recurrence_kernel_abi_payload_v2(),
        "interface_hash": canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2()),
    }
    assert control["abi_hash"] == canonical_hash(
        hip_fgmres_control_state_abi_payload_v2()
    )
    assert record["abi_hash"] == canonical_hash(
        hip_fgmres_solve_record_abi_payload_v2()
    )
    assert interface["device_error_masks"] == {
        "invalid_control_or_geometry": 1,
        "csr_structure": 2,
        "nonfinite_input": 4,
        "arithmetic_overflow": 8,
        "record_abi": 16,
        "jacobi_inverse": 32,
        "invalid_reduction_pair": 64,
    }
    implemented = manifest["implemented_slice"]
    assert implemented["initial_dual_gate"] is True
    assert implemented["initial_final_guard"] is False
    assert implemented["first_arnoldi_column_partial"] is True
    assert implemented["first_arnoldi_column_complete"] is True
    assert implemented["first_pass_mgs_row0"] is True
    assert implemented["device_dgks_decision"] is True
    assert implemented["dgks_second_pass"] is True
    assert implemented["h_next_reduction"] is True
    assert implemented["v_next_normalization"] is True
    assert implemented["full_arnoldi_column"] is True
    assert implemented["first_column_candidate_state_published"] is True
    assert implemented["candidate_envelope_implemented"] is False
    assert (
        implemented["first_column_partial_schedule_hash"]
        == interface["first_column_partial_schedule_hash"]
    )
    assert (
        implemented["first_column_completion_schedule_hash"]
        == (interface["first_column_completion_schedule_hash"])
    )
    assert (
        implemented["first_column_candidate_preparation_schedule_hash"]
        == interface["first_column_candidate_preparation_schedule_hash"]
    )
    assert (
        implemented["first_column_candidate_residual_schedule_hash"]
        == interface["first_column_candidate_residual_schedule_hash"]
    )
    assert (
        implemented["first_column_candidate_scale_metrics_schedule_hash"]
        == interface["first_column_candidate_scale_metrics_schedule_hash"]
    )
    assert (
        implemented["first_column_checkpoint_transaction_schedule_hash"]
        == interface["first_column_checkpoint_transaction_schedule_hash"]
    )
    assert implemented["candidate_preparation_implemented"] is True
    assert implemented["candidate_preparation"] is True
    assert implemented["candidate_backsubstitute_implemented"] is True
    assert implemented["candidate_trial_vector_build_implemented"] is True
    assert implemented["candidate_solution_update_l2_implemented"] is True
    assert implemented["candidate_vector_accept_implemented"] is True
    assert implemented["candidate_spmv_implemented"] is True
    assert implemented["candidate_spmv"] is True
    assert implemented["candidate_true_residual_implemented"] is True
    assert implemented["candidate_true_residual"] is True
    assert implemented["candidate_residual_l2_implemented"] is True
    assert implemented["candidate_residual_linf_implemented"] is True
    assert implemented["candidate_residual_metrics_implemented"] is True
    assert implemented["candidate_residual_metrics"] is True
    assert implemented["trial_and_committed_norms_implemented"] is True
    assert implemented["candidate_scale_metrics_implemented"] is True
    assert implemented["candidate_scale_metrics"] is True
    assert implemented["device_scale_metrics_priority_predicate_implemented"] is True
    assert implemented["checkpoint_transaction_planner_implemented"] is True
    assert implemented["checkpoint_transaction_raw_launch_owner_implemented"] is True
    assert implemented["checkpoint_transaction_rtc_owner_implemented"] is False
    assert implemented["checkpoint_transaction_kernel_numerical_implemented"] is True
    assert (
        implemented["checkpoint_transaction_valid_predecessor_path_implemented"] is True
    )
    assert (
        implemented["checkpoint_transaction_authoritative_owner_implemented"] is False
    )
    assert implemented["checkpoint_commit_source_preflight_implemented"] is True
    assert (
        implemented["checkpoint_transaction_invalid_source_all_or_nothing_proven"]
        is True
    )
    assert implemented[
        "checkpoint_transaction_invalid_source_all_or_nothing_scope"
    ] == (
        "fixed_same_stream_four_launch_transaction_under_exclusive_"
        "source_and_destination_ownership"
    )
    assert (
        implemented["checkpoint_transaction_range_overlap_validation_implemented"]
        is False
    )
    assert (
        implemented["checkpoint_transaction_atomic_host_enqueue_implemented"] is False
    )
    assert (
        implemented["checkpoint_transaction_xscale_failure_oracle_state_parity"]
        is False
    )
    assert implemented["checkpoint_decide_implemented"] is True
    assert implemented["checkpoint_commit_implemented"] is True
    assert implemented["checkpoint_finalize_implemented"] is True
    assert implemented["checkpoint_decide"] is True
    assert implemented["checkpoint_commit"] is True
    assert implemented["full_recurrence_implemented"] is False
    assert implemented["backsolve"] is True
    assert implemented["single_pending_stream_enforced"] is True
    assert implemented["full_solver"] is False
    assert implemented["arnoldi"] is True
    assert implemented["arnoldi_scope"] == ("restart_one_column_zero_through_givens")
    assert implemented["native_numerical_parity_scope"] == (
        "gfx1030_valid_predecessor_restart_one_column_zero_through_"
        "checkpoint_transaction"
    )
    assert implemented["dgks"] is True
    assert implemented["dgks_scope"] == (
        "restart_one_column_zero_conditional_second_pass"
    )
    assert implemented["givens"] is True
    assert implemented["native_numerical_parity"] is True
    assert implemented["epoch_semantics"] == (
        "admission_order_only_not_global_numeric_success"
    )
    with pytest.raises(FrozenInstanceError):
        identity.architecture = "gfx90a"
    forged = replace(identity, recurrence_abi_version=1, identity_hash="")
    forged = replace(
        forged,
        identity_hash=canonical_hash(
            fgmres_rtc_v2._identity_payload(forged, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcFgmresV2Error) as error:
        forged.to_dict()
    assert error.value.code == "hip_rtc_fgmres_v2_identity_invalid"

    forged_interface = replace(
        identity,
        kernel_interface_hash="sha256:" + "0" * 64,
        identity_hash="",
    )
    forged_interface = replace(
        forged_interface,
        identity_hash=canonical_hash(
            fgmres_rtc_v2._identity_payload(
                forged_interface,
                include_hash=False,
            )
        ),
    )
    with pytest.raises(HipRtcFgmresV2Error) as interface_error:
        forged_interface.to_dict()
    assert interface_error.value.code == "hip_rtc_fgmres_v2_identity_invalid"
    kernel.close()


def test_fixed_binding_snapshot_detects_every_identity_value_drift_without_rehash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    identity = kernel.identity
    witness = fgmres_rtc_v2._KERNEL_BINDINGS[kernel]
    assert witness.identity_value_snapshot == (
        fgmres_rtc_v2._kernel_identity_value_snapshot(identity)
    )
    assert kernel._identity_value_snapshot is witness.identity_value_snapshot

    def drift(value: Any) -> Any:
        if type(value) is int:
            # Equal numeric values with different exact types must not alias.
            return float(value)
        if type(value) is str:
            return value + ":drift"
        if type(value) is tuple:
            return (*value, "drift")
        if type(value) is bytes:
            return value + b"\x00"
        if value is None:
            return "/drift"
        raise AssertionError(f"uncovered identity value type: {type(value)!r}")

    nested_names = {"hiprtc_library", "runtime_library"}
    top_level_fields = tuple(identity.__dataclass_fields__)
    assert set(top_level_fields) == {
        "schema_version",
        "abi_version",
        "recurrence_abi_version",
        "control_abi_version",
        "kernel_name",
        "kernel_symbols",
        "control_block_size",
        "vector_block_size",
        "reduction_values_per_block",
        "control_state_abi_hash",
        "solve_record_abi_hash",
        "kernel_interface_hash",
        "source_resource",
        "source_sha256",
        "compile_options",
        "architecture",
        "hiprtc_version_major",
        "hiprtc_version_minor",
        "hiprtc_library",
        "runtime_library",
        "code_object_byte_length",
        "code_object_sha256",
        "identity_hash",
        "_code_object_witness",
    }
    for field_name in top_level_fields:
        if field_name in nested_names:
            continue
        original = getattr(identity, field_name)
        object.__setattr__(identity, field_name, drift(original))
        try:
            with pytest.raises(HipRtcFgmresV2Error) as changed:
                kernel._validated_binding()
            assert changed.value.code == "hip_rtc_fgmres_v2_binding_changed"
        finally:
            object.__setattr__(identity, field_name, original)
        assert kernel._validated_binding() is witness

    for library_name in sorted(nested_names):
        library = getattr(identity, library_name)
        for field_name in library.__dataclass_fields__:
            original = getattr(library, field_name)
            object.__setattr__(library, field_name, drift(original))
            try:
                with pytest.raises(HipRtcFgmresV2Error) as changed:
                    kernel._validated_binding()
                assert changed.value.code == "hip_rtc_fgmres_v2_binding_changed"
            finally:
                object.__setattr__(library, field_name, original)
            assert kernel._validated_binding() is witness

    def forbidden_rehash(_identity: Any) -> Any:
        raise AssertionError("the repeated binding path must not rebuild identity JSON")

    monkeypatch.setattr(type(identity), "to_dict", forbidden_rehash)
    assert kernel._validated_binding() is witness
    kernel.close()


def test_checkpoint_expected_prior_count_is_atomic_exact_and_covers_all_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    original_bind = runtime.bind

    def bind_checkpoint_symbol(symbol: str, argtypes: Any, restype: Any) -> Any:
        if symbol in {"hipStreamSynchronize", "hipMemsetAsync"}:
            return lambda *_arguments: 0
        return original_bind(symbol, argtypes, restype)

    monkeypatch.setattr(runtime, "bind", bind_checkpoint_symbol)
    token = object()
    acquired, _ = kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
        0,
        _checkpoint_owner_token=token,
    )
    assert acquired is token
    stream = 181
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    vector_modes = hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"]
    reduction_modes = hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"]
    targets = hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"]

    with pytest.raises(HipRtcFgmresV2Error) as empty_mismatch:
        _launch_control(
            kernel,
            stream,
            control_modes["INIT"],
            0,
            checkpoint_owner_token=token,
            expected_prior_pending_count=1,
        )
    assert empty_mismatch.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert empty_mismatch.value.launch_disposition == "not_attempted"
    assert kernel._checkpoint_pending_snapshot(token) == ()
    assert runtime.launch_records == []

    _launch_control(
        kernel,
        stream,
        control_modes["INIT"],
        0,
        checkpoint_owner_token=token,
        expected_prior_pending_count=0,
    )
    _launch_vector(
        kernel,
        stream,
        vector_modes["COPY_INITIAL_X"],
        1,
        checkpoint_owner_token=token,
        expected_prior_pending_count=1,
    )
    _launch_spmv(
        kernel,
        stream,
        7,
        checkpoint_owner_token=token,
        expected_prior_pending_count=2,
    )
    _launch_reduction(
        kernel,
        stream,
        mode=reduction_modes["LASSQ_LOAD"],
        target=targets["NONE"],
        schedule_epoch=2,
        reduction_epoch=0,
        value_count=513,
        checkpoint_owner_token=token,
        expected_prior_pending_count=3,
    )
    assert len(runtime.launch_records) == 4
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 4),)

    for invalid_count in (3, 0, False, -1, 1.5):
        with pytest.raises(HipRtcFgmresV2Error) as mismatch:
            _launch_control(
                kernel,
                stream,
                control_modes["INIT"],
                0,
                checkpoint_owner_token=token,
                expected_prior_pending_count=invalid_count,  # type: ignore[arg-type]
            )
        assert mismatch.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
        assert mismatch.value.launch_disposition == "not_attempted"
        assert len(runtime.launch_records) == 4
        assert kernel._checkpoint_pending_snapshot(token) == ((stream, 4),)

    with pytest.raises(HipRtcFgmresV2Error) as wrong_stream:
        _launch_control(
            kernel,
            stream + 1,
            control_modes["INIT"],
            0,
            checkpoint_owner_token=token,
            expected_prior_pending_count=4,
        )
    assert wrong_stream.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert len(runtime.launch_records) == 4
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 4),)

    kernel._synchronize_checkpoint_stream(token, stream)
    assert kernel._consume_checkpoint_pending_after_fence(token, stream) == 4
    assert kernel._checkpoint_pending_snapshot(token) == ()
    kernel.close(_checkpoint_owner_token=token)


def test_checkpoint_stream_query_distinguishes_pending_and_completed_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    token = object()
    acquired, snapshot = (
        kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
            0,
            _checkpoint_owner_token=token,
        )
    )
    assert acquired is token
    witness = fgmres_rtc_v2._KERNEL_BINDINGS[kernel]
    assert witness.stream_query_callable is not None
    assert id(witness.stream_query_callable) in snapshot

    stream = 182
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    _launch_control(
        kernel,
        stream,
        control_modes["INIT"],
        0,
        checkpoint_owner_token=token,
        expected_prior_pending_count=0,
    )
    assert kernel._query_checkpoint_stream_completion(token, stream) is False
    assert runtime.query_streams == [stream]
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 1),)

    kernel._synchronize_checkpoint_stream(token, stream)
    assert kernel._query_checkpoint_stream_completion(token, stream) is True
    assert runtime.sync_streams == [stream]
    assert runtime.query_streams == [stream, stream]
    assert kernel._consume_checkpoint_pending_after_fence(token, stream) == 1
    kernel.close(_checkpoint_owner_token=token)


def test_checkpoint_stream_query_rejects_wrong_authority_device_stream_and_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    token = object()
    kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
        0,
        _checkpoint_owner_token=token,
    )
    stream = 183
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    _launch_control(
        kernel,
        stream,
        control_modes["INIT"],
        0,
        checkpoint_owner_token=token,
        expected_prior_pending_count=0,
    )

    with pytest.raises(HipRtcFgmresV2Error) as wrong_token:
        kernel._query_checkpoint_stream_completion(object(), stream)
    assert wrong_token.value.code == "hip_rtc_fgmres_v2_checkpoint_lease_token_invalid"

    with pytest.raises(HipRtcFgmresV2Error) as wrong_stream:
        kernel._query_checkpoint_stream_completion(token, stream + 1)
    assert (
        wrong_stream.value.code == "hip_rtc_fgmres_v2_checkpoint_query_stream_invalid"
    )

    runtime.current_device = 1
    with pytest.raises(HipRtcFgmresV2Error) as wrong_device:
        kernel._query_checkpoint_stream_completion(token, stream)
    assert wrong_device.value.code == "hip_rtc_fgmres_v2_device_mismatch"
    runtime.current_device = 0

    original_witness = fgmres_rtc_v2._KERNEL_BINDINGS[kernel]
    fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = replace(
        original_witness,
        stream_query_callable=lambda _stream: 0,
    )
    try:
        with pytest.raises(HipRtcFgmresV2Error) as binding_drift:
            kernel._query_checkpoint_stream_completion(token, stream)
        assert binding_drift.value.code == "hip_rtc_fgmres_v2_binding_changed"
    finally:
        fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = original_witness

    for forged_witness in (
        replace(
            original_witness,
            module_pointer=float(original_witness.module_pointer),
        ),
        replace(
            original_witness,
            function_pointers=(
                (
                    original_witness.function_pointers[0][0],
                    float(original_witness.function_pointers[0][1]),
                ),
                *original_witness.function_pointers[1:],
            ),
        ),
        replace(
            original_witness,
            module_device_ordinal=float(original_witness.module_device_ordinal),
        ),
    ):
        fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = forged_witness
        try:
            with pytest.raises(HipRtcFgmresV2Error) as type_drift:
                kernel._query_checkpoint_stream_completion(token, stream)
            assert type_drift.value.code == "hip_rtc_fgmres_v2_binding_changed"
        finally:
            fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = original_witness

    assert runtime.query_streams == []
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 1),)
    kernel._synchronize_checkpoint_stream(token, stream)
    assert kernel._consume_checkpoint_pending_after_fence(token, stream) == 1
    kernel.close(_checkpoint_owner_token=token)


@pytest.mark.parametrize(
    ("query_status", "query_exception"),
    ((7, False), (None, True), (True, False)),
)
def test_checkpoint_stream_query_unknown_status_and_exception_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    query_status: Any,
    query_exception: bool,
) -> None:
    runtime = FakeLoadedRuntime(
        query_status=query_status,
        query_exception=query_exception,
    )
    kernel, _, _ = _compile_fake(monkeypatch, runtime)
    token = object()
    kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
        0,
        _checkpoint_owner_token=token,
    )
    stream = 184
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    _launch_control(
        kernel,
        stream,
        control_modes["INIT"],
        0,
        checkpoint_owner_token=token,
        expected_prior_pending_count=0,
    )
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        kernel._query_checkpoint_stream_completion(token, stream)
    assert caught.value.code == "hip_rtc_fgmres_v2_checkpoint_query_failed"
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 1),)

    runtime.query_status = None
    runtime.query_exception = False
    kernel._synchronize_checkpoint_stream(token, stream)
    assert kernel._query_checkpoint_stream_completion(token, stream) is True
    assert kernel._consume_checkpoint_pending_after_fence(token, stream) == 1
    kernel.close(_checkpoint_owner_token=token)


def test_checkpoint_stream_query_recovers_known_success_after_sync_status_store_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    token = object()
    kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
        0,
        _checkpoint_owner_token=token,
    )
    stream = 185
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    _launch_control(
        kernel,
        stream,
        control_modes["INIT"],
        0,
        checkpoint_owner_token=token,
        expected_prior_pending_count=0,
    )

    with (
        _SingleFireAfterStoreInterrupt(
            type(kernel)._synchronize_checkpoint_stream,
            "status = int(",
        ) as interruption,
        pytest.raises(KeyboardInterrupt),
    ):
        kernel._synchronize_checkpoint_stream(token, stream)
    assert interruption.fired
    assert runtime.sync_streams == [stream]
    assert kernel._checkpoint_pending_snapshot(token) == ((stream, 1),)
    assert kernel._query_checkpoint_stream_completion(token, stream) is True
    assert kernel._consume_checkpoint_pending_after_fence(token, stream) == 1
    kernel.close(_checkpoint_owner_token=token)


def test_checkpoint_lease_requires_exact_stream_query_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime()
    kernel, _, _ = _compile_fake(monkeypatch, runtime)
    original_bind = runtime.bind

    def missing_query(symbol: str, argtypes: Any, restype: Any) -> Any:
        if symbol == "hipStreamQuery":
            raise RuntimeError("injected missing hipStreamQuery")
        return original_bind(symbol, argtypes, restype)

    monkeypatch.setattr(runtime, "bind", missing_query)
    token = object()
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
            0,
            _checkpoint_owner_token=token,
        )
    assert caught.value.code == "hip_rtc_fgmres_v2_checkpoint_query_unavailable"
    assert kernel._checkpoint_owner_token is None
    assert kernel.pending_stream_count == 0
    kernel.close()


def test_checkpoint_lease_registry_cas_rejection_rolls_back_provisional_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    original_witness = fgmres_rtc_v2._KERNEL_BINDINGS[kernel]
    replacement_witness = replace(original_witness)
    original_bind = runtime.bind
    injected = False

    def drift_before_registry_cas(
        symbol: str,
        argtypes: Any,
        restype: Any,
    ) -> Any:
        nonlocal injected
        result = original_bind(symbol, argtypes, restype)
        if symbol == "hipMemsetAsync" and not injected:
            injected = True
            fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = replacement_witness
        return result

    monkeypatch.setattr(runtime, "bind", drift_before_registry_cas)
    rejected_token = object()
    with pytest.raises(HipRtcFgmresV2Error) as rejected:
        kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
            0,
            _checkpoint_owner_token=rejected_token,
        )
    assert injected
    assert rejected.value.code == "hip_rtc_fgmres_v2_binding_changed"
    assert kernel._checkpoint_owner_token is None
    assert kernel._checkpoint_owner_binding_snapshot is None
    assert not kernel._checkpoint_owner_poisoned
    assert kernel.pending_stream_count == 0

    fgmres_rtc_v2._KERNEL_BINDINGS[kernel] = original_witness
    monkeypatch.setattr(runtime, "bind", original_bind)
    recovery_token = object()
    acquired, snapshot = (
        kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
            0,
            _checkpoint_owner_token=recovery_token,
        )
    )
    assert acquired is recovery_token
    assert snapshot == kernel._checkpoint_binding_snapshot(recovery_token)
    kernel._release_checkpoint_transaction_owner_without_work(recovery_token)
    kernel.close()


def test_compiler_requires_exact_hip_get_device_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeLoadedRuntime(current_device=3)
    kernel, _, _ = _compile_fake(monkeypatch, runtime)
    assert runtime.get_device_calls >= 1
    kernel.close()

    class MissingHipGetDeviceRuntime(FakeLoadedRuntime):
        def bind(self, symbol: str, argtypes: Any, restype: Any) -> Any:
            if symbol == "hipGetDevice":
                raise RuntimeError("injected missing hipGetDevice")
            return super().bind(symbol, argtypes, restype)

    missing = MissingHipGetDeviceRuntime()
    with pytest.raises(HipRtcFgmresV2Error) as caught:
        _compile_fake(monkeypatch, missing)
    assert caught.value.code == "hip_rtc_fgmres_v2_device_query_unavailable"
    assert missing.unload_calls == 1


def test_loaded_native_runtime_is_loader_issued_and_identity_is_read_only(
    tmp_path: Path,
) -> None:
    library = _compile_sealed_native_runtime_library(tmp_path)
    cdll = ctypes.CDLL(str(library))
    arbitrary_identity = FakeLoadedRuntime().library_identity
    with pytest.raises(TypeError, match="loader"):
        LoadedHipRuntime(cdll, arbitrary_identity)

    loaded = load_hip_native_runtime(library)
    original_identity = loaded.library_identity
    with pytest.raises((AttributeError, TypeError)):
        loaded.library_identity = arbitrary_identity
    assert loaded.library_identity is original_identity


def test_native_callable_prototypes_are_sealed_from_public_ctypes_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    library = _compile_sealed_native_runtime_library(tmp_path)
    loaded = load_hip_native_runtime(library)
    public_cdll = loaded.cdll
    mutation_count = 0

    def poison(function: Any) -> None:
        nonlocal mutation_count
        function.argtypes = [ctypes.c_void_p]
        function.restype = ctypes.c_void_p
        function.errcheck = lambda result, _function, _arguments: 7
        mutation_count += 1

    cached_load = public_cdll.hipModuleLoadData
    cached_get_function = public_cdll.hipModuleGetFunction
    poison(cached_load)
    poison(cached_get_function)
    public_cdll.hipModuleLoadData = lambda *_arguments: 7
    public_cdll.hipModuleGetFunction = lambda *_arguments: 7

    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    token = object()
    acquired_token, _ = (
        kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot(
            0,
            _checkpoint_owner_token=token,
        )
    )
    assert acquired_token is token

    public_get_device = public_cdll.hipGetDevice
    public_launch = public_cdll.hipModuleLaunchKernel
    public_memset = public_cdll.hipMemsetAsync
    public_sync = public_cdll.hipStreamSynchronize
    public_query = public_cdll.hipStreamQuery
    public_unload = public_cdll.hipModuleUnload
    public_functions = (
        public_get_device,
        public_launch,
        public_memset,
        public_sync,
        public_query,
        public_unload,
    )
    decoy_functions = (
        loaded.bind(
            "hipGetDevice",
            [ctypes.POINTER(ctypes.c_int)],
            ctypes.c_int,
        ),
        loaded.bind(
            "hipModuleLaunchKernel",
            [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_void_p),
            ],
            ctypes.c_int,
        ),
        loaded.bind(
            "hipMemsetAsync",
            [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_size_t,
                ctypes.c_void_p,
            ],
            ctypes.c_int,
        ),
        loaded.bind("hipStreamSynchronize", [ctypes.c_void_p], ctypes.c_int),
        loaded.bind("hipStreamQuery", [ctypes.c_void_p], ctypes.c_int),
        loaded.bind("hipModuleUnload", [ctypes.c_void_p], ctypes.c_int),
    )
    for function in (*public_functions, *decoy_functions):
        poison(function)
    public_cdll.hipGetDevice = lambda *_arguments: 7
    public_cdll.hipModuleLaunchKernel = lambda *_arguments: 7
    public_cdll.hipMemsetAsync = lambda *_arguments: 7
    public_cdll.hipStreamSynchronize = lambda *_arguments: 7
    public_cdll.hipStreamQuery = lambda *_arguments: 7
    public_cdll.hipModuleUnload = lambda *_arguments: 7

    hook_stages: list[int] = []

    def mutate_reentrantly(stage: int) -> None:
        hook_stages.append(int(stage))
        for function in (*public_functions, *decoy_functions):
            poison(function)

    hook_type = ctypes.CFUNCTYPE(None, ctypes.c_int)
    hook = hook_type(mutate_reentrantly)
    set_hook = public_cdll.testSetHook
    set_hook.argtypes = [hook_type]
    set_hook.restype = None
    set_hook(hook)

    stop_mutation = threading.Event()
    mutation_started = threading.Event()

    def mutate_concurrently() -> None:
        mutation_started.set()
        while not stop_mutation.is_set():
            for function in (*public_functions, *decoy_functions):
                poison(function)
            stop_mutation.wait(0.0001)

    mutator = threading.Thread(target=mutate_concurrently, daemon=True)
    mutator.start()
    assert mutation_started.wait(timeout=2.0)
    try:
        for _ in range(32):
            kernel._checkpoint_binding_snapshot(token)
        kernel._checkpoint_memset_zero(token, 77, 201, 4)
        control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
        kernel.launch_control(
            77,
            control_modes["INIT"],
            0,
            -1,
            -1,
            -1,
            -1,
            3,
            2,
            5,
            3,
            2,
            0.0,
            1.0e-8,
            1.0e-9,
            1.0e-8,
            1.0e8,
            201,
            202,
            203,
            _checkpoint_owner_token=token,
        )
        kernel._synchronize_checkpoint_stream(token, 77)
        assert kernel._query_checkpoint_stream_completion(token, 77) is True
        assert kernel._consume_checkpoint_pending_after_fence(token, 77) == 2
        kernel.close(_checkpoint_owner_token=token)
    finally:
        stop_mutation.set()
        mutator.join(timeout=2.0)
    assert not mutator.is_alive()
    assert kernel.closed
    assert mutation_count > 0
    assert {1, 2, 3, 4, 5, 6}.issubset(hook_stages)

    def counter(symbol: str) -> int:
        function = getattr(public_cdll, symbol)
        function.argtypes = []
        function.restype = ctypes.c_int
        return int(function())

    assert counter("testLoadCalls") == 1
    assert counter("testFunctionCalls") == len(SYMBOLS)
    assert counter("testLaunchCalls") == 1
    assert counter("testMemsetCalls") == 1
    assert counter("testSyncCalls") == 1
    assert counter("testQueryCalls") == 1
    assert counter("testUnloadCalls") == 1
    assert counter("testGetDeviceCalls") >= 4


def test_recurrence_v2_plan_and_rtc_public_api_is_reexported() -> None:
    names = (
        "HIP_FGMRES_CONTROL_STATE_BYTES_V2",
        "HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION",
        "HIP_RTC_FGMRES_V2_KERNEL_NAME",
        "FgmresV2FirstColumnCandidatePreparationLaunch",
        "FgmresV2FirstColumnCompletionLaunch",
        "FgmresV2FirstColumnReductionLaunch",
        "FgmresV2InitialReductionLaunch",
        "HipFgmresRecurrencePlanV2",
        "HipRtcFgmresV2Kernel",
        "compile_hip_fgmres_recurrence_plan_v2",
        "compile_hip_rtc_fgmres_v2_kernel",
        "hip_fgmres_control_state_abi_payload_v2",
        "hip_fgmres_first_column_candidate_preparation_schedule_payload_v2",
        "hip_fgmres_first_column_completion_schedule_payload_v2",
        "hip_fgmres_first_column_partial_schedule_payload_v2",
        "hip_fgmres_recurrence_kernel_abi_payload_v2",
        "hip_fgmres_solve_record_abi_payload_v2",
        "first_column_candidate_preparation_launches_v2",
        "first_column_completion_launches_v2",
        "first_column_reduction_launches_v2",
        "initial_reduction_launches_v2",
        "reduction_stage_output_counts_v2",
        "solve_record_byte_length_v2",
        "validate_hip_fgmres_recurrence_plan_v2",
    )
    for name in names:
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(assembly_backend, name)


def test_source_exact_constants_signatures_active_masks_and_claim_boundary() -> None:
    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    assert source.count('extern "C" __global__ void') == 4
    for symbol in SYMBOLS:
        assert source.count(f'extern "C" __global__ void {symbol}(') == 1
    for name, value in fgmres_rtc_v2._source_abi_constant_bindings():
        assert source.count(f"constexpr int {name} = {value};") == 1
    predecessor_bindings = {
        name: value
        for name, value in fgmres_rtc_v2._source_abi_constant_bindings()
        if name.startswith("kPredecessorValidation")
    }
    assert predecessor_bindings == {
        "kPredecessorValidationEmpty": 0,
        "kPredecessorValidationArmed": 1,
        "kPredecessorValidationConsumed": 2,
        "kPredecessorValidationCommitPreflighted": 3,
    }
    assert (
        source.count(
            "// engine-v2-fgmres-recurrence-interface-v2: "
            + canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
        )
        == 1
    )
    assert "control_prestate_zero" in source
    assert "control_state_base, kControlOffsetPhase, kPhaseRhsMetrics" in source
    assert "kControlOffsetScheduleEpoch" in source
    assert "engine_v2_claim_schedule_or_fail" in source
    assert "engine_v2_claim_reduction_or_fail" in source
    assert "blockIdx.x == 0u && threadIdx.x == 0u" in source
    assert "__shared__ int shared_stage_admitted;" in source
    assert "if (shared_stage_admitted == 0)" in source
    assert "const bool epoch_in_range" in source
    assert (
        "required_target = final_stage ? final_target : kReductionTargetNone" in source
    )
    assert "stage == 0 ? kReductionModeLassqLoad" in source
    assert "stage == 0 ? kReductionModeLinfLoad" in source
    assert "kTerminationRestartStateFailed" in source
    assert "kRecurrenceAbiVersion = 2" in source
    assert "shared_first[threadIdx.x + offset]" in source
    assert "second_index =" in source
    assert "kVectorBlockSize / 2" in source
    for forbidden in (
        "#include",
        "hipMalloc",
        "hipMemcpy",
        "hipDeviceSynchronize",
        "hipStreamSynchronize",
        "hipLaunchKernelGGL",
        "atomicAdd",
        "--use_fast_math",
        "-ffast-math",
        "lstsq",
        "pinv",
        "fallback",
    ):
        assert forbidden not in source


def test_fake_launches_bind_exact_full_abi_geometry_and_fenced_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    vector_modes = hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"]
    reduction_modes = hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"]
    targets = hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"]
    stream = 101
    _launch_control(kernel, stream, control_modes["INIT"], 0)
    _launch_vector(kernel, stream, vector_modes["COPY_INITIAL_X"], 1)
    _launch_spmv(kernel, stream, 7)
    _launch_reduction(
        kernel,
        stream,
        mode=reduction_modes["LASSQ_LOAD"],
        target=targets["NONE"],
        schedule_epoch=2,
        reduction_epoch=0,
        value_count=513,
    )
    _launch_reduction(
        kernel,
        stream,
        mode=reduction_modes["COMBINE_LASSQ"],
        target=targets["RHS_L2"],
        schedule_epoch=3,
        reduction_epoch=1,
        value_count=2,
    )
    records = runtime.launch_records
    assert [row["symbol"] for row in records] == [
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[2],
        SYMBOLS[3],
        SYMBOLS[3],
    ]
    assert records[0]["arguments"][:11] == (
        control_modes["INIT"],
        0,
        -1,
        -1,
        -1,
        -1,
        513,
        2,
        5,
        3,
        2,
    )
    assert records[0]["grid"] == (1, 1, 1)
    assert records[0]["block"] == (
        HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE,
        1,
        1,
    )
    assert records[1]["arguments"][:7] == (
        vector_modes["COPY_INITIAL_X"],
        0,
        1,
        -1,
        -1,
        513,
        0,
    )
    assert records[1]["grid"] == (3, 1, 1)
    assert records[2]["grid"] == (3, 1, 1)
    assert records[3]["arguments"][:8] == (
        reduction_modes["LASSQ_LOAD"],
        targets["NONE"],
        2,
        -1,
        -1,
        0,
        513,
        0,
    )
    assert records[3]["grid"] == (2, 1, 1)
    assert records[4]["grid"] == (1, 1, 1)
    assert all(
        row["block"] == (HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE, 1, 1)
        for row in records[1:]
    )
    assert kernel.pending_stream_count == 1
    with pytest.raises(HipRtcFgmresV2Error) as fence_error:
        kernel.close()
    assert fence_error.value.code == "hip_rtc_fgmres_v2_completion_fence_required"
    kernel.acknowledge_stream_completion(stream)
    kernel.close()
    assert runtime.unload_calls == 1


@pytest.mark.parametrize("free_dof_count", [1, 255, 256, 511, 512])
def test_single_stage_boundaries_match_independent_gpu_tree_oracle(
    free_dof_count: int,
) -> None:
    values = np.array(
        [(-1.0 if index % 2 else 1.0) * (index + 1) for index in range(free_dof_count)],
        dtype="<f8",
    )
    assert reduction_stage_output_counts_v2(free_dof_count) == (1,)
    assert fgmres_gpu_tree_l2_v2(values).stage_output_counts == (1,)
    assert fgmres_gpu_tree_linf_v2(values).stage_output_counts == (1,)
    rows = initial_reduction_launches_v2(free_dof_count)
    assert len(rows) == 4
    assert all(row.final_stage for row in rows)
    assert all(row.output_count == 1 for row in rows)


def test_multistage_none_target_and_true_three_stage_schedule_match_oracle() -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    targets = control["reduction_target_codes"]
    assert reduction_stage_output_counts_v2(513) == (2, 1)
    rows = initial_reduction_launches_v2(513)
    assert len(rows) == 8
    assert [row.expected_schedule_epoch for row in rows] == [
        2,
        3,
        4,
        5,
        10,
        11,
        12,
        13,
    ]
    assert [row.expected_reduction_epoch for row in rows] == list(range(8))
    assert all(
        row.reduction_target == targets["NONE"] for row in rows if not row.final_stage
    )
    assert all(
        row.reduction_target != targets["NONE"] for row in rows if row.final_stage
    )

    count = 262_145
    values = np.ones(count, dtype="<f8")
    expected_counts = (513, 2, 1)
    assert reduction_stage_output_counts_v2(count) == expected_counts
    assert fgmres_gpu_tree_l2_v2(values).stage_output_counts == expected_counts
    assert fgmres_gpu_tree_linf_v2(values).stage_output_counts == expected_counts
    three_stage_rows = initial_reduction_launches_v2(count)
    assert len(three_stage_rows) == 12
    assert [row.output_count for row in three_stage_rows[:3]] == [513, 2, 1]
    assert [row.reduction_target for row in three_stage_rows[:3]] == [
        targets["NONE"],
        targets["NONE"],
        targets["RHS_L2"],
    ]

    exact_order = fgmres_gpu_tree_l2_v2(np.array([3.0, -2.0], dtype="<f8"))
    assert exact_order.value == 3.6055512754639896


def test_first_column_reduction_planner_expands_the_canonical_partial_schedule() -> (
    None
):
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    rows = first_column_reduction_launches_v2(513)

    assert len(rows) == 6
    assert all(type(row) is FgmresV2FirstColumnReductionLaunch for row in rows)
    assert [row.metric for row in rows] == [
        "work_before",
        "work_before",
        "dot_first_pass_row0",
        "dot_first_pass_row0",
        "after_first",
        "after_first",
    ]
    assert [row.expected_reduction_epoch for row in rows] == list(range(8, 14))
    assert [row.expected_schedule_epoch for row in rows] == [21, 22, 23, 24, 27, 28]
    assert [row.value_count for row in rows] == [513, 2, 513, 2, 513, 2]
    assert [row.output_count for row in rows] == [2, 1, 2, 1, 2, 1]
    assert [row.reduction_mode for row in rows] == [
        modes["LASSQ_WORK_W"],
        modes["COMBINE_LASSQ"],
        modes["DOT_W_VI"],
        modes["COMBINE_SUM"],
        modes["LASSQ_WORK_W"],
        modes["COMBINE_LASSQ"],
    ]
    assert [row.reduction_target for row in rows] == [
        targets["NONE"],
        targets["WORK_BEFORE"],
        targets["NONE"],
        targets["DOT"],
        targets["NONE"],
        targets["AFTER_FIRST"],
    ]
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    assert all(row.logical_index == 0 for row in rows)
    with pytest.raises(FrozenInstanceError):
        rows[0].expected_schedule_epoch = 99

    three_stage = first_column_reduction_launches_v2(262_145)
    assert len(three_stage) == 9
    assert [row.expected_reduction_epoch for row in three_stage] == list(range(12, 21))
    assert [row.output_count for row in three_stage[:3]] == [513, 2, 1]
    assert [row.expected_schedule_epoch for row in three_stage] == [
        25,
        26,
        27,
        28,
        29,
        30,
        33,
        34,
        35,
    ]


def test_completion_planner_is_exact_immutable_and_dgks_flag_independent() -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]

    rows = first_column_completion_launches_v2(513)
    assert rows == first_column_completion_launches_v2(513)
    assert all(type(row) is FgmresV2FirstColumnCompletionLaunch for row in rows)
    assert [row.name for row in rows] == [
        "REDUCE_DOT_SECOND_PASS_ROW0",
        "REDUCE_DOT_SECOND_PASS_ROW0",
        "CONTROL_DOT_ACCEPT_ROW0_PASS1",
        "VECTOR_MGS_SUBTRACT_ROW0_PASS1",
        "REDUCE_H_NEXT",
        "REDUCE_H_NEXT",
        "VECTOR_NORMALIZE_V1",
        "CONTROL_ARNOLDI_GIVENS_COLUMN0",
    ]
    assert [row.expected_schedule_epoch for row in rows] == list(range(30, 38))
    assert [
        row.expected_reduction_epoch
        for row in rows
        if row.submission_kind == "reduction"
    ] == [14, 15, 16, 17]
    assert [rows[index].mode for index in (0, 1, 4, 5)] == [
        modes["DOT_W_VI"],
        modes["COMBINE_SUM"],
        modes["LASSQ_WORK_W"],
        modes["COMBINE_LASSQ"],
    ]
    assert [rows[index].reduction_target for index in (0, 1, 4, 5)] == [
        targets["NONE"],
        targets["DOT"],
        targets["NONE"],
        targets["H_NEXT"],
    ]
    assert rows[2].mode == controls["DOT_ACCEPT"]
    assert (rows[2].row_index, rows[2].pass_index) == (0, 1)
    assert rows[3].mode == vectors["MGS_SUBTRACT_INDEXED"]
    assert rows[3].vector_gate == gates["DGKS_SECOND_PASS"]
    assert rows[6].mode == vectors["NORMALIZE_V_NEXT"]
    assert rows[6].logical_index == 1
    assert rows[7].mode == controls["ARNOLDI_GIVENS"]
    assert (rows[7].row_index, rows[7].pass_index) == (-1, -1)
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    assert [row.device_gate_source for row in rows[:4]] == [
        "dgks_reorth_required",
        "dgks_reorth_required",
        "dgks_reorth_required",
        "dgks_reorth_required",
    ]
    with pytest.raises(FrozenInstanceError):
        rows[0].expected_schedule_epoch = 99

    three_stage = first_column_completion_launches_v2(262_145)
    assert len(three_stage) == 10
    assert [row.expected_schedule_epoch for row in three_stage] == list(range(37, 47))
    assert [
        row.expected_reduction_epoch
        for row in three_stage
        if row.submission_kind == "reduction"
    ] == list(range(21, 27))


def test_candidate_preparation_planner_is_exact_immutable_and_flag_independent() -> (
    None
):
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]

    assert tuple(
        inspect.signature(first_column_candidate_preparation_launches_v2).parameters
    ) == ("free_dof_count",)
    rows = first_column_candidate_preparation_launches_v2(513)
    assert rows == first_column_candidate_preparation_launches_v2(513)
    assert all(
        type(row) is FgmresV2FirstColumnCandidatePreparationLaunch for row in rows
    )
    assert [row.name for row in rows] == [
        "CONTROL_BACKSUBSTITUTE_COLUMN0",
        "VECTOR_BUILD_TRIAL_X_COLUMN0",
        "REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
        "REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
        "CONTROL_VECTOR_ACCEPT_TRIAL_COLUMN0",
    ]
    assert [row.expected_schedule_epoch for row in rows] == list(range(38, 43))
    assert [
        row.expected_reduction_epoch
        for row in rows
        if row.submission_kind == "reduction"
    ] == [18, 19]
    assert rows[0].mode == controls["BACKSUBSTITUTE"]
    assert (rows[0].row_index, rows[0].pass_index) == (-1, -1)
    assert rows[1].mode == vectors["BUILD_TRIAL_X"]
    assert rows[1].logical_index == 0
    assert rows[1].vector_gate == gates["CANDIDATE_REQUIRED"] == 2
    assert [rows[index].mode for index in (2, 3)] == [
        reductions["LASSQ_WORK_W_MINUS_X"],
        reductions["COMBINE_LASSQ"],
    ]
    assert [rows[index].reduction_target for index in (2, 3)] == [
        targets["NONE"],
        targets["UPDATE_L2"],
    ]
    assert [rows[index].value_count for index in (2, 3)] == [513, 2]
    assert [rows[index].output_count for index in (2, 3)] == [2, 1]
    assert rows[4].mode == controls["VECTOR_ACCEPT"]
    assert (rows[4].row_index, rows[4].pass_index) == (-1, -1)
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    assert rows[0].device_gate_source == "candidate_required"
    assert all(
        row.device_gate_source == "candidate_required_and_not_triangular_breakdown"
        for row in rows[1:]
    )
    with pytest.raises(FrozenInstanceError):
        rows[0].expected_schedule_epoch = 99

    three_stage = first_column_candidate_preparation_launches_v2(262_145)
    assert len(three_stage) == 6
    assert [row.expected_schedule_epoch for row in three_stage] == list(range(47, 53))
    assert [
        row.expected_reduction_epoch
        for row in three_stage
        if row.submission_kind == "reduction"
    ] == [27, 28, 29]


@pytest.mark.parametrize(
    ("free_dof_count", "restart_dimension", "expected_length", "schedule_start"),
    ((1, 1, 5, 33), (513, 4, 7, 43), (262_145, 16, 9, 53)),
)
def test_candidate_residual_planner_is_exact_immutable_and_gate_independent(
    free_dof_count: int,
    restart_dimension: int,
    expected_length: int,
    schedule_start: int,
) -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    spmvs = control["spmv_mode_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]

    assert tuple(
        inspect.signature(first_column_candidate_residual_launches_v2).parameters
    ) == ("free_dof_count", "restart_dimension")
    rows = first_column_candidate_residual_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    assert rows == first_column_candidate_residual_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    assert len(rows) == expected_length
    assert all(type(row) is FgmresV2FirstColumnCandidateResidualLaunch for row in rows)
    assert [row.expected_schedule_epoch for row in rows] == list(
        range(schedule_start, schedule_start + expected_length)
    )
    assert [row.name for row in rows[:3]] == [
        "SPMV_CANDIDATE_COLUMN0",
        "CONTROL_OPERATOR_ACCEPT_CANDIDATE_COLUMN0",
        "VECTOR_FORM_CANDIDATE_RESIDUAL_COLUMN0",
    ]
    stage_count = len(reduction_stage_output_counts_v2(free_dof_count))
    assert [row.name for row in rows[3 : 3 + stage_count]] == [
        "REDUCE_CANDIDATE_L2_COLUMN0"
    ] * stage_count
    assert [row.name for row in rows[3 + stage_count :]] == [
        "REDUCE_CANDIDATE_LINF_COLUMN0"
    ] * stage_count
    assert rows[0].mode == spmvs["CANDIDATE"]
    assert rows[1].mode == controls["OPERATOR_ACCEPT"]
    assert (rows[1].row_index, rows[1].pass_index) == (-1, -1)
    assert rows[2].mode == vectors["FORM_CANDIDATE_RESIDUAL"]
    assert rows[2].vector_gate == gates["CANDIDATE_REQUIRED"]
    assert all(
        row.logical_index == restart_dimension
        for row in rows
        if row.submission_kind != "control"
    )
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    assert all(
        row.device_gate_source == "candidate_required_and_not_triangular_breakdown"
        for row in rows
    )
    reduction_rows = rows[3:]
    assert [row.expected_reduction_epoch for row in reduction_rows] == list(
        range(10 * stage_count, 12 * stage_count)
    )
    assert reduction_rows[0].mode == reductions["LASSQ_V_M"]
    assert reduction_rows[stage_count].mode == reductions["LINF_V_M"]
    assert reduction_rows[stage_count - 1].reduction_target == targets["CANDIDATE_L2"]
    assert reduction_rows[-1].reduction_target == targets["CANDIDATE_LINF"]
    assert all(
        row.reduction_target == targets["NONE"]
        for row in reduction_rows
        if not row.final_stage
    )
    with pytest.raises(FrozenInstanceError):
        rows[0].logical_index = 0


@pytest.mark.parametrize("restart_dimension", (False, 0, 17))
def test_candidate_residual_planner_rejects_noncanonical_restart_dimension(
    restart_dimension: object,
) -> None:
    with pytest.raises(HipRtcFgmresV2Error) as error:
        first_column_candidate_residual_launches_v2(513, restart_dimension)  # type: ignore[arg-type]
    assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"


@pytest.mark.parametrize(
    ("free_dof_count", "stage_count", "schedule_start"),
    ((1, 1, 38), (513, 2, 50), (262_145, 3, 62)),
)
def test_candidate_scale_metrics_planner_is_exact_and_predicate_independent(
    free_dof_count: int,
    stage_count: int,
    schedule_start: int,
) -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    assert tuple(
        inspect.signature(first_column_candidate_scale_metrics_launches_v2).parameters
    ) == ("free_dof_count",)
    rows = first_column_candidate_scale_metrics_launches_v2(free_dof_count)
    assert rows == first_column_candidate_scale_metrics_launches_v2(free_dof_count)
    assert len(rows) == 2 * stage_count
    assert all(
        type(row) is FgmresV2FirstColumnCandidateScaleMetricsLaunch for row in rows
    )
    assert [row.name for row in rows[:stage_count]] == [
        "REDUCE_TRIAL_X_L2_COLUMN0"
    ] * stage_count
    assert [row.name for row in rows[stage_count:]] == [
        "REDUCE_COMMITTED_X_L2_COLUMN0"
    ] * stage_count
    assert [row.expected_schedule_epoch for row in rows] == list(
        range(schedule_start, schedule_start + 2 * stage_count)
    )
    assert [row.expected_reduction_epoch for row in rows] == list(
        range(12 * stage_count, 14 * stage_count)
    )
    assert rows[0].mode == modes["LASSQ_WORK_W"]
    assert rows[stage_count].mode == modes["LASSQ_SOLUTION_X"]
    assert rows[stage_count - 1].reduction_target == targets["TRIAL_X_L2"]
    assert rows[-1].reduction_target == targets["COMMITTED_X_L2"]
    assert all(
        row.mode == modes["COMBINE_LASSQ"]
        for row in (*rows[1:stage_count], *rows[stage_count + 1 :])
    )
    assert all(
        row.reduction_target == targets["NONE"] for row in rows if not row.final_stage
    )
    assert all(row.logical_index == 0 for row in rows)
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    assert all(row.device_gate_source == "scale_metrics_required" for row in rows)
    with pytest.raises(FrozenInstanceError):
        rows[0].logical_index = 1


@pytest.mark.parametrize(
    ("free_dof_count", "expected_schedule_epoch", "expected_reduction_epoch"),
    ((1, 40, 14), (513, 54, 28), (262_145, 68, 42)),
)
def test_predecessor_validation_planner_is_exact_nonadvancing_and_device_only(
    free_dof_count: int,
    expected_schedule_epoch: int,
    expected_reduction_epoch: int,
) -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["control_mode_codes"]

    assert modes["PREDECESSOR_VALIDATE"] == 14
    assert tuple(
        inspect.signature(first_column_predecessor_validation_launch_v2).parameters
    ) == ("free_dof_count",)
    row = first_column_predecessor_validation_launch_v2(free_dof_count)
    assert row == first_column_predecessor_validation_launch_v2(free_dof_count)
    assert type(row) is FgmresV2FirstColumnPredecessorValidationLaunch
    assert row.name == "PREDECESSOR_VALIDATE_COLUMN0"
    assert row.submission_kind == "control"
    assert row.kernel_symbol == HIP_RTC_FGMRES_V2_CONTROL_SYMBOL
    assert row.mode == modes["PREDECESSOR_VALIDATE"]
    assert row.expected_schedule_epoch == expected_schedule_epoch
    assert row.expected_reduction_epoch == expected_reduction_epoch
    assert (row.expected_restart, row.expected_column) == (1, 0)
    assert (row.row_index, row.pass_index) == (-1, -1)
    assert row.admitted_mask_domain == (0, 1792, 7936)
    assert row.schedule_epoch_advances is False
    assert row.reduction_epoch_advances is False
    assert control["predecessor_validation_contract"] == {
        "validator_control_mode": "PREDECESSOR_VALIDATE",
        "validator_control_mode_code": 14,
        "admitted_mask_domain": [0, 1792, 7936],
        "validator_preserves_schedule_epoch": True,
        "validator_preserves_reduction_epoch": True,
        "validator_arms_exact_mask_snapshot": True,
        "checkpoint_decide_consumes_armed_state": True,
        "checkpoint_preflight_vector_mode": "PREFLIGHT_COMMIT_SOURCE",
        "checkpoint_preflight_vector_mode_code": 9,
        "checkpoint_preflight_transitions_consumed_or_legacy_empty_to_commit_preflighted": True,
        "checkpoint_preflight_preserves_mask_and_reduction_epoch_snapshots": True,
        "commit_preflighted_state_is_standalone_success_verdict": False,
        "checkpoint_commit_requires_commit_preflighted_state": True,
        "checkpoint_finalize_clears_commit_preflighted_state": True,
        "legacy_caller_attested_empty_state_retained_through_checkpoint_decide": True,
        "legacy_commit_preflighted_snapshots_are_exact_zero": True,
        "actual_mask_host_observed": False,
    }
    with pytest.raises(FrozenInstanceError):
        row.expected_schedule_epoch = 0


@pytest.mark.parametrize("free_dof_count", (False, 0, -1, 2**31))
def test_predecessor_validation_planner_rejects_invalid_free_dof_count(
    free_dof_count: object,
) -> None:
    with pytest.raises(HipRtcFgmresV2Error) as error:
        first_column_predecessor_validation_launch_v2(free_dof_count)  # type: ignore[arg-type]
    assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"


@pytest.mark.parametrize(
    ("free_dof_count", "restart_dimension", "schedule_start", "reduction_epoch"),
    ((1, 1, 40, 14), (513, 4, 54, 28), (262_145, 16, 68, 42)),
)
def test_checkpoint_transaction_planner_is_exact_and_host_predicate_independent(
    free_dof_count: int,
    restart_dimension: int,
    schedule_start: int,
    reduction_epoch: int,
) -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    assert tuple(
        inspect.signature(first_column_checkpoint_transaction_launches_v2).parameters
    ) == ("free_dof_count", "restart_dimension")
    rows = first_column_checkpoint_transaction_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    assert rows == first_column_checkpoint_transaction_launches_v2(
        free_dof_count,
        restart_dimension,
    )
    assert all(
        type(row) is FgmresV2FirstColumnCheckpointTransactionLaunch for row in rows
    )
    assert [row.name for row in rows] == [
        "CHECKPOINT_DECIDE_COLUMN0",
        "PREFLIGHT_COMMIT_SOURCE_COLUMN0",
        "COMMIT_CHECKPOINT_COLUMN0",
        "CHECKPOINT_FINALIZE_COLUMN0",
    ]
    assert [row.submission_kind for row in rows] == [
        "control",
        "vector",
        "vector",
        "control",
    ]
    assert [row.expected_schedule_epoch for row in rows] == [
        schedule_start,
        schedule_start + 1,
        schedule_start + 1,
        schedule_start + 2,
    ]
    assert [row.expected_reduction_epoch for row in rows] == [reduction_epoch] * 4
    assert [row.mode for row in rows] == [
        controls["CHECKPOINT_DECIDE"],
        vectors["PREFLIGHT_COMMIT_SOURCE"],
        vectors["COMMIT_CHECKPOINT"],
        controls["CHECKPOINT_FINALIZE"],
    ]
    assert rows[1].vector_gate == gates["COMMIT_REQUIRED"]
    assert rows[1].logical_index == restart_dimension
    assert rows[2].vector_gate == gates["COMMIT_REQUIRED"]
    assert rows[2].logical_index == restart_dimension
    assert (rows[0].row_index, rows[0].pass_index) == (-1, -1)
    assert (rows[3].row_index, rows[3].pass_index) == (-1, -1)
    assert [row.device_gate_source for row in rows] == [
        "always",
        "commit_required",
        "commit_required",
        "always",
    ]
    assert all(row.expected_restart == 1 for row in rows)
    assert all(row.expected_column == 0 for row in rows)
    with pytest.raises(FrozenInstanceError):
        rows[0].mode = controls["FINAL_GUARD"]


@pytest.mark.parametrize("restart_dimension", (False, 0, 17))
def test_checkpoint_transaction_planner_rejects_noncanonical_restart_dimension(
    restart_dimension: object,
) -> None:
    with pytest.raises(HipRtcFgmresV2Error) as error:
        first_column_checkpoint_transaction_launches_v2(513, restart_dimension)  # type: ignore[arg-type]
    assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"


def test_checkpoint_transaction_owner_is_reexported() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.assembly_backend as assembly_backend

    assert (
        assembly_backend.FgmresV2FirstColumnCheckpointTransactionLaunch
        is FgmresV2FirstColumnCheckpointTransactionLaunch
    )
    assert (
        engine_v2.FgmresV2FirstColumnCheckpointTransactionLaunch
        is FgmresV2FirstColumnCheckpointTransactionLaunch
    )
    assert (
        assembly_backend.first_column_checkpoint_transaction_launches_v2
        is first_column_checkpoint_transaction_launches_v2
    )
    assert (
        engine_v2.first_column_checkpoint_transaction_launches_v2
        is first_column_checkpoint_transaction_launches_v2
    )


def test_predecessor_validation_planner_and_mode_are_reexported() -> None:
    assert (
        assembly_backend.FgmresV2FirstColumnPredecessorValidationLaunch
        is FgmresV2FirstColumnPredecessorValidationLaunch
    )
    assert (
        engine_v2.FgmresV2FirstColumnPredecessorValidationLaunch
        is FgmresV2FirstColumnPredecessorValidationLaunch
    )
    assert (
        assembly_backend.first_column_predecessor_validation_launch_v2
        is first_column_predecessor_validation_launch_v2
    )
    assert (
        engine_v2.first_column_predecessor_validation_launch_v2
        is first_column_predecessor_validation_launch_v2
    )
    assert (
        hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"][
            "PREDECESSOR_VALIDATE"
        ]
        == 14
    )


def test_fake_owner_accepts_exact_predecessor_validation_and_rejects_bad_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    row = first_column_predecessor_validation_launch_v2(513)

    _launch_control(
        kernel,
        73,
        row.mode,
        row.expected_schedule_epoch,
        expected_restart=row.expected_restart,
        expected_column=row.expected_column,
        row_index=row.row_index,
        pass_index=row.pass_index,
    )
    assert runtime.launch_records[-1]["symbol"] == HIP_RTC_FGMRES_V2_CONTROL_SYMBOL
    assert runtime.launch_records[-1]["arguments"][:11] == (
        14,
        54,
        1,
        0,
        -1,
        -1,
        513,
        2,
        5,
        3,
        2,
    )

    invalid_coordinates = (
        (53, 1, 0, -1, -1, 513),
        (54, -1, 0, -1, -1, 513),
        (54, 1, -1, -1, -1, 513),
        (54, 1, 0, 0, -1, 513),
        (54, 1, 0, -1, 0, 513),
        (54, 1, 0, -1, -1, 1),
    )
    for schedule, restart, column, row_index, pass_index, n in invalid_coordinates:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            _launch_control(
                kernel,
                73,
                row.mode,
                schedule,
                n=n,
                expected_restart=restart,
                expected_column=column,
                row_index=row_index,
                pass_index=pass_index,
            )
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"

    assert len(runtime.launch_records) == 1
    kernel.acknowledge_stream_completion(73)
    kernel.close()


def test_fake_owner_accepts_every_candidate_preparation_submission_without_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    stream = 120
    n = 513
    rows = first_column_candidate_preparation_launches_v2(n)
    for row in rows:
        if row.submission_kind == "reduction":
            assert row.reduction_target is not None
            assert row.expected_reduction_epoch is not None
            assert row.value_count is not None
            _launch_reduction(
                kernel,
                stream,
                mode=row.mode,
                target=row.reduction_target,
                schedule_epoch=row.expected_schedule_epoch,
                reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index or 0,
            )
        elif row.submission_kind == "vector":
            assert row.logical_index is not None
            assert row.vector_gate is not None
            _launch_vector(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
                gate=row.vector_gate,
            )
        else:
            assert row.row_index is not None
            assert row.pass_index is not None
            _launch_control(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                row_index=row.row_index,
                pass_index=row.pass_index,
            )

    assert [record["symbol"] for record in runtime.launch_records] == [
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[3],
        SYMBOLS[3],
        SYMBOLS[0],
    ]
    assert runtime.launch_records[1]["arguments"][:7] == (
        hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"]["BUILD_TRIAL_X"],
        hip_fgmres_control_state_abi_payload_v2()["vector_gate_codes"][
            "CANDIDATE_REQUIRED"
        ],
        39,
        1,
        0,
        513,
        0,
    )
    assert runtime.launch_records[2]["arguments"][:8] == (
        hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"][
            "LASSQ_WORK_W_MINUS_X"
        ],
        hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"]["NONE"],
        40,
        1,
        0,
        18,
        513,
        0,
    )
    assert (
        runtime.launch_records[3]["arguments"][1]
        == (
            hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"][
                "UPDATE_L2"
            ]
        )
    )
    kernel.acknowledge_stream_completion(stream)
    kernel.close()


def test_fake_owner_accepts_every_candidate_residual_submission_without_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    stream = 134
    n = 513
    restart_dimension = 4
    rows = first_column_candidate_residual_launches_v2(n, restart_dimension)
    for row in rows:
        if row.submission_kind == "spmv":
            assert row.logical_index is not None
            _launch_spmv(
                kernel,
                stream,
                row.expected_schedule_epoch,
                n=n,
                mode=row.mode,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
            )
        elif row.submission_kind == "control":
            assert row.row_index is not None
            assert row.pass_index is not None
            _launch_control(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                row_index=row.row_index,
                pass_index=row.pass_index,
            )
        elif row.submission_kind == "vector":
            assert row.logical_index is not None
            assert row.vector_gate is not None
            _launch_vector(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
                gate=row.vector_gate,
            )
        else:
            assert row.logical_index is not None
            assert row.reduction_target is not None
            assert row.expected_reduction_epoch is not None
            assert row.value_count is not None
            _launch_reduction(
                kernel,
                stream,
                mode=row.mode,
                target=row.reduction_target,
                schedule_epoch=row.expected_schedule_epoch,
                reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
            )

    assert [record["symbol"] for record in runtime.launch_records] == [
        SYMBOLS[2],
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[3],
        SYMBOLS[3],
        SYMBOLS[3],
        SYMBOLS[3],
    ]
    assert runtime.launch_records[0]["arguments"][:7] == (
        hip_fgmres_control_state_abi_payload_v2()["spmv_mode_codes"]["CANDIDATE"],
        43,
        1,
        0,
        513,
        1026,
        4,
    )
    assert runtime.launch_records[2]["arguments"][:7] == (
        hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"][
            "FORM_CANDIDATE_RESIDUAL"
        ],
        hip_fgmres_control_state_abi_payload_v2()["vector_gate_codes"][
            "CANDIDATE_REQUIRED"
        ],
        45,
        1,
        0,
        513,
        4,
    )
    assert [record["arguments"][:8] for record in runtime.launch_records[3:]] == [
        (
            hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"][
                "LASSQ_V_M"
            ],
            hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"]["NONE"],
            46,
            1,
            0,
            20,
            513,
            4,
        ),
        (
            hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"][
                "COMBINE_LASSQ"
            ],
            hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"][
                "CANDIDATE_L2"
            ],
            47,
            1,
            0,
            21,
            2,
            4,
        ),
        (
            hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"][
                "LINF_V_M"
            ],
            hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"]["NONE"],
            48,
            1,
            0,
            22,
            513,
            4,
        ),
        (
            hip_fgmres_control_state_abi_payload_v2()["reduction_mode_codes"][
                "COMBINE_MAX"
            ],
            hip_fgmres_control_state_abi_payload_v2()["reduction_target_codes"][
                "CANDIDATE_LINF"
            ],
            49,
            1,
            0,
            23,
            2,
            4,
        ),
    ]
    kernel.acknowledge_stream_completion(stream)
    kernel.close()


def test_fake_owner_accepts_every_candidate_scale_metric_without_host_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    rows = first_column_candidate_scale_metrics_launches_v2(513)
    for row in rows:
        assert row.reduction_target is not None
        assert row.expected_reduction_epoch is not None
        assert row.value_count is not None
        _launch_reduction(
            kernel,
            137,
            mode=row.mode,
            target=row.reduction_target,
            schedule_epoch=row.expected_schedule_epoch,
            reduction_epoch=row.expected_reduction_epoch,
            value_count=row.value_count,
            expected_restart=row.expected_restart,
            expected_column=row.expected_column,
            logical_index=0,
        )
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    assert [record["symbol"] for record in runtime.launch_records] == [SYMBOLS[3]] * 4
    assert [record["arguments"][:8] for record in runtime.launch_records] == [
        (modes["LASSQ_WORK_W"], targets["NONE"], 50, 1, 0, 24, 513, 0),
        (modes["COMBINE_LASSQ"], targets["TRIAL_X_L2"], 51, 1, 0, 25, 2, 0),
        (modes["LASSQ_SOLUTION_X"], targets["NONE"], 52, 1, 0, 26, 513, 0),
        (
            modes["COMBINE_LASSQ"],
            targets["COMMITTED_X_L2"],
            53,
            1,
            0,
            27,
            2,
            0,
        ),
    ]
    kernel.acknowledge_stream_completion(137)
    kernel.close()


def test_fake_owner_accepts_exact_checkpoint_transaction_without_host_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    rows = first_column_checkpoint_transaction_launches_v2(513, 4)
    for row in rows:
        if row.submission_kind == "control":
            assert row.row_index is not None
            assert row.pass_index is not None
            _launch_control(
                kernel,
                140,
                row.mode,
                row.expected_schedule_epoch,
                expected_restart=1,
                expected_column=0,
                row_index=row.row_index,
                pass_index=row.pass_index,
            )
        else:
            assert row.vector_gate is not None
            assert row.logical_index is not None
            _launch_vector(
                kernel,
                140,
                row.mode,
                row.expected_schedule_epoch,
                expected_restart=1,
                expected_column=0,
                logical_index=row.logical_index,
                gate=row.vector_gate,
            )
    control = hip_fgmres_control_state_abi_payload_v2()
    assert [record["symbol"] for record in runtime.launch_records] == [
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[1],
        SYMBOLS[0],
    ]
    assert runtime.launch_records[0]["arguments"][:6] == (
        control["control_mode_codes"]["CHECKPOINT_DECIDE"],
        54,
        1,
        0,
        -1,
        -1,
    )
    assert runtime.launch_records[1]["arguments"][:7] == (
        control["vector_mode_codes"]["PREFLIGHT_COMMIT_SOURCE"],
        control["vector_gate_codes"]["COMMIT_REQUIRED"],
        55,
        1,
        0,
        513,
        4,
    )
    assert runtime.launch_records[2]["arguments"][:7] == (
        control["vector_mode_codes"]["COMMIT_CHECKPOINT"],
        control["vector_gate_codes"]["COMMIT_REQUIRED"],
        55,
        1,
        0,
        513,
        4,
    )
    assert runtime.launch_records[3]["arguments"][:6] == (
        control["control_mode_codes"]["CHECKPOINT_FINALIZE"],
        56,
        1,
        0,
        -1,
        -1,
    )
    kernel.acknowledge_stream_completion(140)
    kernel.close()


def test_fake_owner_accepts_every_completion_submission_without_host_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    stream = 119
    n = 513
    for row in first_column_completion_launches_v2(n):
        if row.submission_kind == "reduction":
            assert row.reduction_target is not None
            assert row.expected_reduction_epoch is not None
            assert row.value_count is not None
            _launch_reduction(
                kernel,
                stream,
                mode=row.mode,
                target=row.reduction_target,
                schedule_epoch=row.expected_schedule_epoch,
                reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index or 0,
            )
        elif row.submission_kind == "vector":
            assert row.logical_index is not None
            assert row.vector_gate is not None
            _launch_vector(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
                gate=row.vector_gate,
            )
        else:
            assert row.row_index is not None
            assert row.pass_index is not None
            _launch_control(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                row_index=row.row_index,
                pass_index=row.pass_index,
            )

    assert [record["symbol"] for record in runtime.launch_records] == [
        SYMBOLS[3],
        SYMBOLS[3],
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[3],
        SYMBOLS[3],
        SYMBOLS[1],
        SYMBOLS[0],
    ]
    assert runtime.launch_records[3]["arguments"][:7] == (
        hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"][
            "MGS_SUBTRACT_INDEXED"
        ],
        hip_fgmres_control_state_abi_payload_v2()["vector_gate_codes"][
            "DGKS_SECOND_PASS"
        ],
        33,
        1,
        0,
        513,
        0,
    )
    kernel.acknowledge_stream_completion(stream)
    kernel.close()


def test_fake_owner_accepts_exact_first_column_partial_modes_and_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    spmvs = control["spmv_mode_codes"]
    stream = 111
    n = 513

    _launch_control(
        kernel,
        stream,
        controls["RESTART_BEGIN"],
        15,
        n=n,
        expected_restart=1,
    )
    _launch_vector(
        kernel,
        stream,
        vectors["NORMALIZE_V0"],
        16,
        n=n,
        expected_restart=1,
        expected_column=0,
    )
    _launch_vector(
        kernel,
        stream,
        vectors["APPLY_JACOBI_INDEXED"],
        17,
        n=n,
        expected_restart=1,
        expected_column=0,
    )
    _launch_control(
        kernel,
        stream,
        controls["PRECONDITION_ACCEPT"],
        18,
        n=n,
        expected_restart=1,
        expected_column=0,
    )
    _launch_spmv(
        kernel,
        stream,
        19,
        n=n,
        mode=spmvs["ARNOLDI"],
        expected_restart=1,
        expected_column=0,
    )
    _launch_control(
        kernel,
        stream,
        controls["OPERATOR_ACCEPT"],
        20,
        n=n,
        expected_restart=1,
        expected_column=0,
    )
    reduction_rows = first_column_reduction_launches_v2(n)
    for row in reduction_rows[:4]:
        _launch_reduction(
            kernel,
            stream,
            mode=row.reduction_mode,
            target=row.reduction_target,
            schedule_epoch=row.expected_schedule_epoch,
            reduction_epoch=row.expected_reduction_epoch,
            value_count=row.value_count,
            expected_restart=row.expected_restart,
            expected_column=row.expected_column,
            logical_index=row.logical_index,
        )
    _launch_control(
        kernel,
        stream,
        controls["DOT_ACCEPT"],
        25,
        n=n,
        expected_restart=1,
        expected_column=0,
        row_index=0,
        pass_index=0,
    )
    _launch_vector(
        kernel,
        stream,
        vectors["MGS_SUBTRACT_INDEXED"],
        26,
        n=n,
        expected_restart=1,
        expected_column=0,
    )
    for row in reduction_rows[4:]:
        _launch_reduction(
            kernel,
            stream,
            mode=row.reduction_mode,
            target=row.reduction_target,
            schedule_epoch=row.expected_schedule_epoch,
            reduction_epoch=row.expected_reduction_epoch,
            value_count=row.value_count,
            expected_restart=row.expected_restart,
            expected_column=row.expected_column,
            logical_index=row.logical_index,
        )
    _launch_control(
        kernel,
        stream,
        controls["DGKS_DECIDE"],
        29,
        n=n,
        expected_restart=1,
        expected_column=0,
        pass_index=0,
    )

    assert [row["symbol"] for row in runtime.launch_records[:6]] == [
        SYMBOLS[0],
        SYMBOLS[1],
        SYMBOLS[1],
        SYMBOLS[0],
        SYMBOLS[2],
        SYMBOLS[0],
    ]
    assert runtime.launch_records[0]["arguments"][:6] == (
        controls["RESTART_BEGIN"],
        15,
        1,
        -1,
        -1,
        -1,
    )
    assert runtime.launch_records[4]["arguments"][:7] == (
        spmvs["ARNOLDI"],
        19,
        1,
        0,
        513,
        1026,
        0,
    )
    kernel.acknowledge_stream_completion(stream)
    kernel.close()


def test_initial_gpu_tree_gate_oracle_covers_dual_gate_and_i_zero() -> None:
    common = {
        "row_ptr": np.array([0, 1, 2], dtype="<i4"),
        "column_indices": np.array([0, 1], dtype="<i4"),
        "values": np.array([1.0, 1.0], dtype="<f8"),
        "rhs": np.array([1.0, 1.0], dtype="<f8"),
        "absolute_tolerance": 0.0,
        "relative_tolerance": 1.0e-12,
        "authoritative_tolerance": 1.0e-12,
    }
    converged = replay_fgmres_gpu_tree_initial_v2(
        **common,
        initial_solution=np.array([1.0, 1.0], dtype="<f8"),
        max_iterations=5,
    )
    assert converged.terminal_status == "converged"
    assert converged.termination_code == "converged_initial_true_residual"
    max_zero = replay_fgmres_gpu_tree_initial_v2(
        **common,
        initial_solution=np.array([0.0, 0.0], dtype="<f8"),
        max_iterations=0,
    )
    assert max_zero.terminal_status == "max_iterations"
    assert max_zero.termination_code == "max_iterations_exhausted"
    assert max_zero.operator_apply_count == 1


def test_launch_contract_rejects_unsupported_modes_bad_epochs_and_target_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    invalid_calls = (
        lambda: _launch_control(
            kernel,
            1,
            control["control_mode_codes"]["FINAL_GUARD"],
            1,
        ),
        lambda: _launch_control(
            kernel,
            1,
            control["control_mode_codes"]["RESTART_BEGIN"],
            15,
        ),
        lambda: _launch_vector(
            kernel,
            1,
            control["vector_mode_codes"]["NORMALIZE_V0"],
            16,
        ),
        lambda: _launch_spmv(
            kernel,
            1,
            19,
            mode=control["spmv_mode_codes"]["ARNOLDI"],
        ),
        lambda: kernel.launch_vector(
            1,
            control["vector_mode_codes"]["COPY_INITIAL_X"],
            control["vector_gate_codes"]["ACTIVE"],
            -1,
            -1,
            -1,
            3,
            0,
            *range(10, 21),
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["DOT_W_VI"],
            target=targets["DOT"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=1,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["LASSQ_LOAD"],
            target=targets["RHS_L2"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=513,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["COMBINE_LASSQ"],
            target=targets["NONE"],
            schedule_epoch=3,
            reduction_epoch=1,
            value_count=2,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["COMBINE_LASSQ"],
            target=targets["RHS_L2"],
            schedule_epoch=3,
            reduction_epoch=1,
            value_count=2,
            input_pointer=246,
            output_pointer=246,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["LASSQ_LOAD"],
            target=targets["RHS_L2"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=1,
            output_pointer=241,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["LASSQ_WORK_W"],
            target=targets["WORK_BEFORE"],
            schedule_epoch=17,
            reduction_epoch=4,
            value_count=1,
            expected_restart=1,
            expected_column=0,
            output_pointer=244,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["DOT_W_VI"],
            target=targets["DOT"],
            schedule_epoch=18,
            reduction_epoch=5,
            value_count=1,
            expected_restart=1,
            expected_column=0,
            output_pointer=245,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["LASSQ_LOAD"],
            target=targets["RHS_L2"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=1,
            output_pointer=248,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["LASSQ_LOAD"],
            target=targets["RHS_L2"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=1,
            output_pointer=249,
        ),
        lambda: _launch_reduction(
            kernel,
            1,
            mode=modes["COMBINE_SUM"],
            target=targets["DOT"],
            schedule_epoch=1_000_013,
            reduction_epoch=1_000_000,
            value_count=1,
            expected_restart=1,
            expected_column=0,
        ),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    for invalid in (-1, True, 1.5, 2**31):
        with pytest.raises(HipRtcFgmresV2Error):
            reduction_stage_output_counts_v2(invalid)  # type: ignore[arg-type]
    assert solve_record_byte_length_v2(0) == 192
    assert solve_record_byte_length_v2(3) == 408
    kernel.close()


def test_completion_reverse_validation_rejects_wrong_gate_epoch_and_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    invalid_calls = (
        lambda: _launch_control(
            kernel,
            130,
            controls["DOT_ACCEPT"],
            32,
            expected_restart=1,
            expected_column=0,
            row_index=0,
            pass_index=0,
        ),
        lambda: _launch_control(
            kernel,
            130,
            controls["ARNOLDI_GIVENS"],
            36,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_vector(
            kernel,
            130,
            vectors["MGS_SUBTRACT_INDEXED"],
            33,
            expected_restart=1,
            expected_column=0,
            gate=gates["ACTIVE"],
        ),
        lambda: _launch_vector(
            kernel,
            130,
            vectors["NORMALIZE_V_NEXT"],
            36,
            expected_restart=1,
            expected_column=0,
            logical_index=0,
        ),
        lambda: _launch_reduction(
            kernel,
            130,
            mode=reductions["DOT_W_VI"],
            target=targets["NONE"],
            schedule_epoch=31,
            reduction_epoch=14,
            value_count=513,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_reduction(
            kernel,
            130,
            mode=reductions["COMBINE_LASSQ"],
            target=targets["AFTER_FIRST"],
            schedule_epoch=35,
            reduction_epoch=17,
            value_count=2,
            expected_restart=1,
            expected_column=0,
        ),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    kernel.close()


def test_completion_reductions_preserve_exact_active_output_alias_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    calls = (
        # Second-pass DOT first stage: work_w and basis_v are both active.
        dict(
            mode=modes["DOT_W_VI"],
            target=targets["NONE"],
            schedule_epoch=30,
            reduction_epoch=14,
            value_count=513,
            output_pointer=244,
        ),
        dict(
            mode=modes["DOT_W_VI"],
            target=targets["NONE"],
            schedule_epoch=30,
            reduction_epoch=14,
            value_count=513,
            output_pointer=245,
        ),
        # Every combine stage requires distinct input and output bases.
        dict(
            mode=modes["COMBINE_SUM"],
            target=targets["DOT"],
            schedule_epoch=31,
            reduction_epoch=15,
            value_count=2,
            input_pointer=246,
            output_pointer=246,
        ),
        # H_NEXT first stage reads work_w.
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=34,
            reduction_epoch=16,
            value_count=513,
            output_pointer=244,
        ),
        dict(
            mode=modes["COMBINE_LASSQ"],
            target=targets["H_NEXT"],
            schedule_epoch=35,
            reduction_epoch=17,
            value_count=2,
            input_pointer=246,
            output_pointer=246,
        ),
    )
    for arguments in calls:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            _launch_reduction(
                kernel,
                131,
                expected_restart=1,
                expected_column=0,
                **arguments,
            )
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"

    for output_pointer in (248, 249):
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_reduction(
                kernel,
                131,
                mode=modes["LASSQ_WORK_W"],
                target=targets["NONE"],
                schedule_epoch=34,
                reduction_epoch=16,
                value_count=513,
                expected_restart=1,
                expected_column=0,
                output_pointer=output_pointer,
            )
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_preparation_reverse_validation_is_exact_and_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    spmvs = control["spmv_mode_codes"]
    invalid_calls = (
        lambda: _launch_control(
            kernel,
            132,
            controls["BACKSUBSTITUTE"],
            39,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_control(
            kernel,
            132,
            controls["VECTOR_ACCEPT"],
            41,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_vector(
            kernel,
            132,
            vectors["BUILD_TRIAL_X"],
            39,
            expected_restart=1,
            expected_column=0,
            gate=gates["ACTIVE"],
        ),
        lambda: _launch_vector(
            kernel,
            132,
            vectors["BUILD_TRIAL_X"],
            39,
            expected_restart=1,
            expected_column=0,
            logical_index=1,
            gate=gates["CANDIDATE_REQUIRED"],
        ),
        lambda: _launch_reduction(
            kernel,
            132,
            mode=reductions["LASSQ_WORK_W_MINUS_X"],
            target=targets["NONE"],
            schedule_epoch=41,
            reduction_epoch=18,
            value_count=513,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_reduction(
            kernel,
            132,
            mode=reductions["COMBINE_LASSQ"],
            target=targets["H_NEXT"],
            schedule_epoch=41,
            reduction_epoch=19,
            value_count=2,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_spmv(
            kernel,
            132,
            43,
            mode=spmvs["CANDIDATE"],
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_control(
            kernel,
            132,
            controls["CHECKPOINT_DECIDE"],
            43,
            expected_restart=1,
            expected_column=0,
        ),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    kernel.close()


def test_candidate_residual_reverse_validation_rejects_wrong_coordinates_and_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    spmvs = control["spmv_mode_codes"]
    invalid_calls = (
        lambda: _launch_spmv(
            kernel,
            135,
            42,
            mode=spmvs["CANDIDATE"],
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_spmv(
            kernel,
            135,
            43,
            mode=spmvs["CANDIDATE"],
            expected_restart=1,
            expected_column=0,
            logical_index=0,
        ),
        lambda: _launch_spmv(
            kernel,
            135,
            43,
            mode=spmvs["CANDIDATE"],
            expected_restart=1,
            expected_column=0,
            logical_index=17,
        ),
        lambda: _launch_control(
            kernel,
            135,
            controls["OPERATOR_ACCEPT"],
            43,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_vector(
            kernel,
            135,
            vectors["FORM_CANDIDATE_RESIDUAL"],
            45,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
            gate=gates["ACTIVE"],
        ),
        lambda: _launch_vector(
            kernel,
            135,
            vectors["FORM_CANDIDATE_RESIDUAL"],
            45,
            expected_restart=1,
            expected_column=0,
            logical_index=0,
            gate=gates["CANDIDATE_REQUIRED"],
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["LASSQ_V_M"],
            target=targets["NONE"],
            schedule_epoch=47,
            reduction_epoch=20,
            value_count=513,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["COMBINE_LASSQ"],
            target=targets["CANDIDATE_LINF"],
            schedule_epoch=47,
            reduction_epoch=21,
            value_count=2,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["LINF_V_M"],
            target=targets["NONE"],
            schedule_epoch=48,
            reduction_epoch=22,
            value_count=513,
            expected_restart=1,
            expected_column=0,
            logical_index=0,
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["COMBINE_MAX"],
            target=targets["CANDIDATE_L2"],
            schedule_epoch=49,
            reduction_epoch=23,
            value_count=2,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["COMBINE_LASSQ"],
            target=targets["TRIAL_X_L2"],
            schedule_epoch=47,
            reduction_epoch=21,
            value_count=2,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_reduction(
            kernel,
            135,
            mode=reductions["COMBINE_LASSQ"],
            target=targets["COMMITTED_X_L2"],
            schedule_epoch=47,
            reduction_epoch=21,
            value_count=2,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
        ),
        lambda: _launch_control(
            kernel,
            135,
            controls["CHECKPOINT_DECIDE"],
            50,
            expected_restart=1,
            expected_column=0,
        ),
    )
    for call in invalid_calls:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_residual_base_pointer_and_alias_contracts_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    spmvs = control["spmv_mode_codes"]
    reductions = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]

    spmv_signature = inspect.signature(kernel.launch_csr_spmv_indexed).parameters
    assert "logical_index" in spmv_signature
    assert "work_w_base" in spmv_signature
    assert "basis_v_base" in spmv_signature
    assert all("offset" not in name and "shift" not in name for name in spmv_signature)
    vector_signature = inspect.signature(kernel.launch_vector).parameters
    assert tuple(name for name in vector_signature if name == "basis_v_base") == (
        "basis_v_base",
    )

    spmv_aliases = []
    for left, right in ((4, 5), (5, 7), (5, 8)):
        pointers = list(range(231, 240))
        pointers[right] = pointers[left]
        spmv_aliases.append(tuple(pointers))
    for pointers in spmv_aliases:
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_spmv(
                kernel,
                136,
                43,
                mode=spmvs["CANDIDATE"],
                expected_restart=1,
                expected_column=0,
                logical_index=4,
                pointers=pointers,
            )

    for left, right in ((1, 6), (6, 9), (6, 10)):
        pointers = list(range(211, 222))
        pointers[right] = pointers[left]
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_vector(
                kernel,
                136,
                vectors["FORM_CANDIDATE_RESIDUAL"],
                45,
                expected_restart=1,
                expected_column=0,
                logical_index=4,
                gate=gates["CANDIDATE_REQUIRED"],
                pointers=tuple(pointers),
            )

    for mode, target, schedule, epoch, count, output in (
        (reductions["LASSQ_V_M"], targets["NONE"], 46, 20, 513, 245),
        (reductions["LINF_V_M"], targets["NONE"], 48, 22, 513, 245),
        (reductions["COMBINE_LASSQ"], targets["CANDIDATE_L2"], 47, 21, 2, 246),
        (reductions["COMBINE_MAX"], targets["CANDIDATE_LINF"], 49, 23, 2, 246),
    ):
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_reduction(
                kernel,
                136,
                mode=mode,
                target=target,
                schedule_epoch=schedule,
                reduction_epoch=epoch,
                value_count=count,
                expected_restart=1,
                expected_column=0,
                logical_index=4,
                output_pointer=output,
            )
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_scale_metrics_reverse_validation_and_scope_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    invalid = (
        dict(
            mode=modes["LASSQ_SOLUTION_X"],
            target=targets["NONE"],
            schedule_epoch=50,
            reduction_epoch=24,
            value_count=513,
        ),
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=49,
            reduction_epoch=24,
            value_count=513,
        ),
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=50,
            reduction_epoch=23,
            value_count=513,
        ),
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=50,
            reduction_epoch=24,
            value_count=513,
            logical_index=1,
        ),
        dict(
            mode=modes["COMBINE_LASSQ"],
            target=targets["COMMITTED_X_L2"],
            schedule_epoch=51,
            reduction_epoch=25,
            value_count=2,
        ),
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=52,
            reduction_epoch=26,
            value_count=513,
        ),
        dict(
            mode=modes["COMBINE_LASSQ"],
            target=targets["TRIAL_X_L2"],
            schedule_epoch=53,
            reduction_epoch=27,
            value_count=2,
        ),
        dict(
            mode=modes["LASSQ_V_M"],
            target=targets["NONE"],
            schedule_epoch=50,
            reduction_epoch=24,
            value_count=513,
        ),
    )
    for arguments in invalid:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            _launch_reduction(
                kernel,
                138,
                expected_restart=1,
                expected_column=0,
                **arguments,
            )
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_scale_metrics_reject_active_source_and_ping_pong_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    calls = (
        dict(
            mode=modes["LASSQ_WORK_W"],
            target=targets["NONE"],
            schedule_epoch=50,
            reduction_epoch=24,
            value_count=513,
            output_pointer=244,
        ),
        dict(
            mode=modes["LASSQ_SOLUTION_X"],
            target=targets["NONE"],
            schedule_epoch=52,
            reduction_epoch=26,
            value_count=513,
            output_pointer=242,
        ),
        dict(
            mode=modes["COMBINE_LASSQ"],
            target=targets["TRIAL_X_L2"],
            schedule_epoch=51,
            reduction_epoch=25,
            value_count=2,
            output_pointer=246,
        ),
        dict(
            mode=modes["COMBINE_LASSQ"],
            target=targets["COMMITTED_X_L2"],
            schedule_epoch=53,
            reduction_epoch=27,
            value_count=2,
            output_pointer=246,
        ),
    )
    for arguments in calls:
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_reduction(
                kernel,
                139,
                expected_restart=1,
                expected_column=0,
                **arguments,
            )
    for output_pointer in (248, 249):
        with pytest.raises(HipRtcFgmresV2Error):
            _launch_reduction(
                kernel,
                139,
                mode=modes["LASSQ_WORK_W"],
                target=targets["NONE"],
                schedule_epoch=50,
                reduction_epoch=24,
                value_count=513,
                expected_restart=1,
                expected_column=0,
                output_pointer=output_pointer,
            )
    assert runtime.launch_records == []
    kernel.close()


def test_checkpoint_transaction_raw_reverse_validation_is_exact_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    controls = control["control_mode_codes"]
    vectors = control["vector_mode_codes"]
    gates = control["vector_gate_codes"]
    invalid = (
        lambda: _launch_control(
            kernel,
            141,
            controls["CHECKPOINT_DECIDE"],
            53,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_control(
            kernel,
            141,
            controls["CHECKPOINT_DECIDE"],
            54,
            expected_restart=1,
            expected_column=0,
            row_index=0,
        ),
        lambda: _launch_control(
            kernel,
            141,
            controls["CHECKPOINT_FINALIZE"],
            55,
            expected_restart=1,
            expected_column=0,
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["PREFLIGHT_COMMIT_SOURCE"],
            54,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
            gate=gates["COMMIT_REQUIRED"],
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["PREFLIGHT_COMMIT_SOURCE"],
            55,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
            gate=gates["ACTIVE"],
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["COMMIT_CHECKPOINT"],
            54,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
            gate=gates["COMMIT_REQUIRED"],
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["COMMIT_CHECKPOINT"],
            55,
            expected_restart=1,
            expected_column=0,
            logical_index=4,
            gate=gates["ACTIVE"],
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["COMMIT_CHECKPOINT"],
            55,
            expected_restart=1,
            expected_column=0,
            logical_index=0,
            gate=gates["COMMIT_REQUIRED"],
        ),
        lambda: _launch_vector(
            kernel,
            141,
            vectors["COMMIT_CHECKPOINT"],
            55,
            expected_restart=1,
            expected_column=0,
            logical_index=17,
            gate=gates["COMMIT_REQUIRED"],
        ),
        lambda: _launch_control(
            kernel,
            141,
            controls["FINAL_GUARD"],
            57,
            expected_restart=1,
            expected_column=0,
        ),
    )
    for call in invalid:
        with pytest.raises(HipRtcFgmresV2Error) as error:
            call()
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert runtime.launch_records == []
    kernel.close()


def test_raw_launch_reverse_validation_accepts_exact_later_slot_and_final_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    n = 513
    restart_dimension = 3
    max_iterations = 7
    plan = compile_hip_fgmres_global_schedule_plan_v1(
        n,
        restart_dimension,
        max_iterations,
    )
    stream = 142
    padded_restart = plan.restarts[-1]
    later_column = padded_restart.columns[-1]
    selected_launches = (
        padded_restart.preamble_launches
        + later_column.launches
        + (plan.final_guard_launch,)
    )

    for row in selected_launches:
        assert row is not None
        if row.submission_kind == "control":
            kernel.launch_control(
                stream,
                row.mode,
                row.expected_schedule_epoch,
                row.expected_restart,
                row.expected_column,
                row.row_index,
                row.pass_index,
                n,
                restart_dimension,
                max_iterations,
                plan.maximum_restart_count,
                2,
                0.0,
                1.0e-8,
                1.0e-9,
                1.0e-8,
                1.0e8,
                201,
                202,
                203,
            )
        elif row.submission_kind == "vector":
            _launch_vector(
                kernel,
                stream,
                row.mode,
                row.expected_schedule_epoch,
                n=n,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
                gate=row.vector_gate,
            )
        elif row.submission_kind == "spmv":
            _launch_spmv(
                kernel,
                stream,
                row.expected_schedule_epoch,
                n=n,
                mode=row.mode,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
            )
        else:
            assert row.submission_kind == "reduction"
            _launch_reduction(
                kernel,
                stream,
                mode=row.mode,
                target=row.reduction_target,
                schedule_epoch=row.expected_schedule_epoch,
                reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
            )

    assert len(runtime.launch_records) == len(selected_launches)
    final_guard = plan.final_guard_launch
    assert final_guard is not None
    assert runtime.launch_records[-1]["arguments"][:6] == (
        final_guard.mode,
        final_guard.expected_schedule_epoch,
        plan.maximum_restart_count,
        restart_dimension - 1,
        -1,
        -1,
    )
    kernel.acknowledge_stream_completion(stream)
    accepted_count = len(runtime.launch_records)

    with pytest.raises(HipRtcFgmresV2Error) as error:
        kernel.launch_control(
            stream,
            final_guard.mode,
            final_guard.expected_schedule_epoch,
            final_guard.expected_restart,
            restart_dimension - 2,
            -1,
            -1,
            n,
            restart_dimension,
            max_iterations,
            plan.maximum_restart_count,
            2,
            0.0,
            1.0e-8,
            1.0e-9,
            1.0e-8,
            1.0e8,
            201,
            202,
            203,
        )
    assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"

    mgs = next(
        row
        for row in later_column.launches
        if row.submission_kind == "vector"
        and row.mode
        == hip_fgmres_control_state_abi_payload_v2()["vector_mode_codes"][
            "MGS_SUBTRACT_INDEXED"
        ]
        and row.vector_gate
        == hip_fgmres_control_state_abi_payload_v2()["vector_gate_codes"]["ACTIVE"]
    )
    with pytest.raises(HipRtcFgmresV2Error) as error:
        _launch_vector(
            kernel,
            stream,
            mgs.mode,
            mgs.expected_schedule_epoch,
            n=n,
            expected_restart=mgs.expected_restart,
            expected_column=mgs.expected_column,
            logical_index=mgs.expected_column + 1,
            gate=mgs.vector_gate,
        )
    assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert len(runtime.launch_records) == accepted_count
    kernel.close()


def test_checkpoint_commit_source_does_not_recompute_or_read_reduction_targets() -> (
    None
):
    source = fgmres_rtc_v2._fixed_source().decode("utf-8")
    vector_start = source.index(
        'extern "C" __global__ void engine_v2_fgmres_vector_v2('
    )
    vector_end = source.index(
        'extern "C" __global__ void engine_v2_fgmres_csr_spmv_indexed_v2(',
        vector_start,
    )
    vector_source = source[vector_start:vector_end]
    assert "solve_record_base, kRecordOffsetDeviceErrorBits) != 0" in vector_source
    assert "engine_v2_checkpoint_decision(" not in vector_source
    commit_start = vector_source.index("if (commit_checkpoint_mode) {")
    commit_end = vector_source.index("if (normalize_v0_mode)", commit_start)
    commit_source = vector_source[commit_start:commit_end]
    for target_name in (
        "kControlOffsetCandidateL2",
        "kControlOffsetCandidateLinf",
        "kControlOffsetSolutionUpdateL2",
        "kControlOffsetCommittedXL2",
        "kControlOffsetTrialXL2",
        "kControlOffsetXScaleL2",
    ):
        assert target_name not in commit_source


def test_checkpoint_preflight_is_read_only_nonadvancing_and_commit_is_pure_copy() -> (
    None
):
    source = fgmres_rtc_v2._fixed_source().decode("utf-8")
    terminal_publish_start = source.index("void engine_v2_publish_terminal_failure(")
    terminal_publish_end = source.index(
        "void engine_v2_terminal_failure(", terminal_publish_start
    )
    terminal_publish_source = source[terminal_publish_start:terminal_publish_end]
    assert "kControlOffsetCommitRequired), 0" in terminal_publish_source
    assert "kControlOffsetContinuationRequired), 0" in terminal_publish_source
    first_error_start = source.index("bool engine_v2_terminal_failure_if_error_clear(")
    first_error_end = source.index(
        "EngineV2LassqPair engine_v2_lassq_zero()", first_error_start
    )
    first_error_source = source[first_error_start:first_error_end]
    assert "atomicCAS(" in first_error_source
    assert "record + kRecordOffsetDeviceErrorBits" in first_error_source
    assert "if (previous != 0u)" in first_error_source
    assert "return false;" in first_error_source
    assert "engine_v2_publish_terminal_failure(" in first_error_source
    vector_start = source.index(
        'extern "C" __global__ void engine_v2_fgmres_vector_v2('
    )
    vector_end = source.index(
        'extern "C" __global__ void engine_v2_fgmres_csr_spmv_indexed_v2(',
        vector_start,
    )
    vector_source = source[vector_start:vector_end]
    preflight_guard = "if (preflight_commit_source_mode) {"
    first_preflight_guard = vector_source.index(preflight_guard)
    preflight_start = vector_source.index(
        preflight_guard,
        first_preflight_guard + len(preflight_guard),
    )
    preflight_end = vector_source.index(
        "if (blockIdx.x == 0u && threadIdx.x == 0u &&\n"
        "      !engine_v2_claim_schedule_or_fail(",
        preflight_start,
    )
    preflight_source = vector_source[preflight_start:preflight_end]
    assert "atomicCAS(" in preflight_source
    assert "kPredecessorValidationEmpty" in preflight_source
    assert "kPredecessorValidationConsumed" in preflight_source
    assert "kPredecessorValidationCommitPreflighted" in preflight_source
    assert "work_w_base[preflight_index]" in preflight_source
    assert "basis_v_base[" in preflight_source
    assert "engine_v2_isfinite(trial)" in preflight_source
    assert "engine_v2_isfinite(candidate_residual)" in preflight_source
    assert "kErrorNonfiniteInput" in preflight_source
    assert "kFailureOriginVector" in preflight_source
    assert "kTerminationRestartStateFailed" in preflight_source
    assert "engine_v2_terminal_failure_if_error_clear(" in preflight_source
    assert "engine_v2_terminal_failure(" not in preflight_source
    assert "engine_v2_claim_schedule_or_fail(" not in preflight_source
    assert "solution_x_base[" not in preflight_source
    assert "true_residual_base[" not in preflight_source

    commit_start = vector_source.index("if (commit_checkpoint_mode) {", preflight_end)
    commit_end = vector_source.index("if (normalize_v0_mode)", commit_start)
    commit_source = vector_source[commit_start:commit_end]
    assert "work_w_base[index]" in commit_source
    assert "basis_v_base[" in commit_source
    assert "solution_x_base[index]" in commit_source
    assert "true_residual_base[index]" in commit_source
    assert "engine_v2_isfinite" not in commit_source
    assert "engine_v2_terminal_failure" not in commit_source

    finalize_start = source.index(
        "if (control_mode == kControlModeCheckpointFinalize) {\n"
        "    const EngineV2CheckpointDecision"
    )
    finalize_end = source.index(
        "if (control_mode == kControlModeBindRhs)", finalize_start
    )
    finalize_source = source[finalize_start:finalize_end]
    cleanup_start = finalize_source.rindex("kControlOffsetPredecessorMaskSnapshot")
    assert (
        cleanup_start
        < finalize_source.rindex("kControlOffsetPredecessorReductionEpochSnapshot")
        < finalize_source.rindex("kControlOffsetPredecessorValidationState")
    )


def test_full_final_cycle_checkpoint_handoff_is_exact_and_postvalidated() -> None:
    source = fgmres_rtc_v2._fixed_source().decode("utf-8")
    required_start = source.index(
        "bool\nengine_v2_checkpoint_requires_final_guard_handoff("
    )
    valid_start = source.index(
        "bool\nengine_v2_checkpoint_final_guard_handoff_prestate_valid("
    )
    valid_end = source.index("\n}\n\n}  // namespace", valid_start) + 2
    required_source = source[required_start:valid_start]
    valid_source = source[valid_start:valid_end]
    for required in (
        "max_iterations % restart_dimension != 0",
        "max_iterations / restart_dimension != maximum_restart_count",
        "decision.pending_terminal_status == kTerminalMaxIterations",
        "decision.pending_termination_code == kTerminationMaxIterationsExhausted",
        "expected_restart == maximum_restart_count",
        "expected_column == restart_dimension - 1",
    ):
        assert required in required_source
    for required in (
        "kControlOffsetScheduleEpoch",
        "engine_v2_global_final_schedule_epoch(",
        "kControlOffsetReductionEpoch",
        "engine_v2_global_final_reduction_epoch(",
        "kControlOffsetReorthogonalizationCount",
        "kControlOffsetDgksReorthRequired",
        "kControlOffsetFailureOrigin",
        "kRecordOffsetScheduledIterations",
        "kRecordOffsetEffectiveIterations",
        "kRecordOffsetScheduledRestarts",
        "kRecordOffsetEffectiveRestarts",
        "kRecordOffsetOperatorApplyCount",
        "kRecordOffsetPreconditionerApplyCount",
        "kRecordOffsetRestartDimension",
        "kRecordOffsetEstimatedResidualL2",
    ):
        assert required in valid_source

    finalize_start = source.index(
        "if (control_mode == kControlModeCheckpointFinalize) {\n"
        "    const EngineV2CheckpointDecision"
    )
    finalize_end = source.index(
        "if (control_mode == kControlModeBindRhs)", finalize_start
    )
    finalize_source = source[finalize_start:finalize_end]
    required_call = finalize_source.index(
        "engine_v2_checkpoint_requires_final_guard_handoff("
    )
    validity_call = finalize_source.index(
        "!engine_v2_checkpoint_final_guard_handoff_prestate_valid("
    )
    fail_closed = finalize_source.index(
        "A malformed mandatory handoff must never masquerade"
    )
    restart_row_publish = finalize_source.index("kRestartOffsetStartIteration")
    result_header_publish = finalize_source.index(
        "solve_record_base, kRecordOffsetFinalResidualL2, candidate_l2"
    )
    handoff_branch = finalize_source.index("if (final_guard_handoff) {")
    checkpoint_terminal_branch = finalize_source.index(
        "else if (decision.pending_terminal_status != kTerminalNotTerminal)"
    )
    clear_predecessor = finalize_source.rindex(
        "kControlOffsetPredecessorValidationState"
    )
    postcondition = finalize_source.rindex("!engine_v2_final_guard_exhausted_shape(")
    assert required_call < validity_call < fail_closed < restart_row_publish
    assert fail_closed < result_header_publish
    assert (
        "kTerminationRestartStateFailed"
        in finalize_source[validity_call:restart_row_publish]
    )
    assert restart_row_publish < handoff_branch
    assert handoff_branch < checkpoint_terminal_branch
    assert clear_predecessor < postcondition
    assert (
        "kControlOffsetPhase, kPhaseArnoldi"
        in finalize_source[handoff_branch:checkpoint_terminal_branch]
    )
    assert "kTerminationRestartStateFailed" in finalize_source[postcondition:]


def test_checkpoint_preflight_and_commit_reject_every_active_allocation_base_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    gate = control["vector_gate_codes"]["COMMIT_REQUIRED"]
    for mode_name in ("PREFLIGHT_COMMIT_SOURCE", "COMMIT_CHECKPOINT"):
        mode = control["vector_mode_codes"][mode_name]
        for left, right in (
            (5, 3),
            (6, 4),
            (5, 4),
            (6, 3),
            (3, 4),
            (3, 9),
            (4, 10),
        ):
            pointers = list(range(211, 222))
            pointers[right] = pointers[left]
            with pytest.raises(HipRtcFgmresV2Error) as error:
                _launch_vector(
                    kernel,
                    142,
                    mode,
                    55,
                    expected_restart=1,
                    expected_column=0,
                    logical_index=4,
                    gate=gate,
                    pointers=tuple(pointers),
                )
            assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    signature = inspect.signature(kernel.launch_vector).parameters
    assert "commit_required" not in signature
    assert "candidate_outcome" not in signature
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_update_reduction_rejects_every_active_output_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, runtime = _compile_fake(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    modes = control["reduction_mode_codes"]
    targets = control["reduction_target_codes"]
    for output_pointer in (242, 244, 248, 249):
        with pytest.raises(HipRtcFgmresV2Error) as error:
            _launch_reduction(
                kernel,
                133,
                mode=modes["LASSQ_WORK_W_MINUS_X"],
                target=targets["NONE"],
                schedule_epoch=40,
                reduction_epoch=18,
                value_count=513,
                expected_restart=1,
                expected_column=0,
                output_pointer=output_pointer,
            )
        assert error.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    with pytest.raises(HipRtcFgmresV2Error):
        _launch_reduction(
            kernel,
            133,
            mode=modes["COMBINE_LASSQ"],
            target=targets["UPDATE_L2"],
            schedule_epoch=41,
            reduction_epoch=19,
            value_count=2,
            expected_restart=1,
            expected_column=0,
            input_pointer=246,
            output_pointer=246,
        )
    assert runtime.launch_records == []
    kernel.close()


def test_candidate_preparation_forgery_and_combined_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    forged["launches"][1]["gate"] = "ACTIVE"
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_candidate_preparation_schedule_payload_v2",
        lambda: forged,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_candidate_preparation_launches_v2(513)
    assert planner_error.value.code == (
        "hip_rtc_fgmres_v2_candidate_preparation_schedule_invalid"
    )
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_candidate_preparation_schedule_hash"] = (
        "sha256:" + "0" * 64
    )
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_candidate_residual_forgery_and_combined_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    forged["launches"][2]["gate"] = "ACTIVE"
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_candidate_residual_schedule_payload_v2",
        lambda: forged,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_candidate_residual_launches_v2(513, 4)
    assert planner_error.value.code == (
        "hip_rtc_fgmres_v2_candidate_residual_schedule_invalid"
    )
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_candidate_residual_schedule_hash"] = (
        "sha256:" + "0" * 64
    )
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_candidate_scale_metrics_forgery_and_combined_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    forged["launches"][0]["numeric_gate"] = "active_candidate"
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2",
        lambda: forged,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_candidate_scale_metrics_launches_v2(513)
    assert planner_error.value.code == (
        "hip_rtc_fgmres_v2_candidate_scale_metrics_schedule_invalid"
    )
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_candidate_scale_metrics_schedule_hash"] = (
        "sha256:" + "0" * 64
    )
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_predecessor_validation_forgery_and_combined_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    forged["predecessor_contract"]["admitted_reduction_valid_masks"] = [0, 1792]
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_predecessor_validation_schedule_payload_v2",
        lambda: forged,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_predecessor_validation_launch_v2(513)
    assert planner_error.value.code == (
        "hip_rtc_fgmres_v2_predecessor_validation_schedule_invalid"
    )
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_predecessor_validation_schedule_hash"] = (
        "sha256:" + "0" * 64
    )
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_checkpoint_transaction_forgery_and_combined_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    forged["launches"][1]["vector_gate"] = "ACTIVE"
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2",
        lambda: forged,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_checkpoint_transaction_launches_v2(513, 4)
    assert planner_error.value.code == (
        "hip_rtc_fgmres_v2_checkpoint_transaction_schedule_invalid"
    )
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_checkpoint_transaction_schedule_hash"] = (
        "sha256:" + "0" * 64
    )
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_completion_schedule_forgery_and_combined_source_hash_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged_completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    forged_completion["launches"][0]["expected_schedule_epoch"] = "17+q"
    monkeypatch.setattr(
        fgmres_rtc_v2,
        "hip_fgmres_first_column_completion_schedule_payload_v2",
        lambda: forged_completion,
    )
    with pytest.raises(HipRtcFgmresV2Error) as source_error:
        fgmres_rtc_v2._fixed_source()
    assert source_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    with pytest.raises(HipRtcFgmresV2Error) as planner_error:
        first_column_completion_launches_v2(513)
    assert planner_error.value.code == ("hip_rtc_fgmres_v2_completion_schedule_invalid")
    monkeypatch.undo()

    forged_interface = hip_fgmres_recurrence_kernel_abi_payload_v2()
    forged_interface["first_column_completion_schedule_hash"] = "sha256:" + "0" * 64
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: forged_interface)
    with pytest.raises(HipRtcFgmresV2Error) as hash_error:
        fgmres_rtc_v2._fixed_source()
    assert hash_error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_source_interface_constant_and_signature_drift_fail_before_compile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_interface = fgmres_rtc_v2._kernel_abi()
    drifted_interface = dict(original_interface)
    drifted_interface["pointer_contract"] = "shifted_pointer_allowed"
    monkeypatch.setattr(fgmres_rtc_v2, "_kernel_abi", lambda: drifted_interface)
    with pytest.raises(HipRtcFgmresV2Error) as interface_error:
        fgmres_rtc_v2._fixed_source()
    assert interface_error.value.code == "hip_rtc_fgmres_v2_source_invalid"
    monkeypatch.undo()

    source = KERNEL_SOURCE.read_text(encoding="utf-8")
    variants = (
        source.replace(
            "constexpr int kControlOffsetScheduleEpoch = 112;",
            "constexpr int kControlOffsetScheduleEpoch = 116;",
            1,
        ),
        source.replace(
            "int control_mode,\n    int expected_schedule_epoch,",
            "int control_mode,\n    int schedule_epoch_guess,",
            1,
        ),
        source.replace(
            "constexpr int kRecurrenceAbiVersion = 2;",
            "constexpr int kRecurrenceAbiVersion = 1;",
            1,
        ),
    )
    for index, drifted in enumerate(variants):
        path = tmp_path / f"drifted-{index}.hip.cpp"
        path.write_text(drifted, encoding="utf-8")
        monkeypatch.setattr(fgmres_rtc_v2, "_SOURCE_PATH", path)
        with pytest.raises(HipRtcFgmresV2Error) as error:
            fgmres_rtc_v2._fixed_source()
        assert error.value.code == "hip_rtc_fgmres_v2_source_invalid"


def test_missing_symbol_retryable_unload_and_ambiguous_launch_preserve_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_runtime = FakeLoadedRuntime(missing_symbol=SYMBOLS[-1])
    with pytest.raises(HipRtcFgmresV2Error) as missing_error:
        _compile_fake(monkeypatch, missing_runtime)
    assert missing_error.value.code == "hip_rtc_fgmres_v2_symbol_missing"
    assert missing_runtime.unload_calls == 1

    retry_runtime = FakeLoadedRuntime(unload_statuses=(9, 0))
    retry, _, _ = _compile_fake(monkeypatch, retry_runtime)
    with pytest.raises(HipRtcFgmresV2Error) as unload_error:
        retry.close()
    assert unload_error.value.code == "hip_rtc_fgmres_v2_module_unload_failed"
    assert not retry.closed
    retry.close()
    assert retry.closed

    ambiguous_runtime = FakeLoadedRuntime(launch_exception=True)
    ambiguous, _, _ = _compile_fake(monkeypatch, ambiguous_runtime)
    control_modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    with pytest.raises(HipRtcFgmresV2Error) as launch_error:
        _launch_control(ambiguous, 77, control_modes["INIT"], 0, n=3)
    assert launch_error.value.code == "hip_rtc_fgmres_v2_kernel_launch_failed"
    assert ambiguous.pending_stream_count == 1
    with pytest.raises(HipRtcFgmresV2Error):
        ambiguous.close()
    ambiguous.acknowledge_stream_completion(77)
    ambiguous.close()


def test_pending_recurrence_is_bound_to_one_stream_until_completion_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel, _, _ = _compile_fake(monkeypatch)
    modes = hip_fgmres_control_state_abi_payload_v2()["control_mode_codes"]
    _launch_control(kernel, 80, modes["INIT"], 0, n=3)
    with pytest.raises(HipRtcFgmresV2Error) as cross_stream:
        _launch_control(kernel, 81, modes["INIT"], 0, n=3)
    assert cross_stream.value.code == "hip_rtc_fgmres_v2_launch_contract_invalid"
    assert kernel.pending_stream_count == 1
    with pytest.raises(HipRtcFgmresV2Error):
        kernel.acknowledge_stream_completion(82)
    kernel.acknowledge_stream_completion(80)
    _launch_control(kernel, 81, modes["INIT"], 0, n=3)
    kernel.acknowledge_stream_completion(81)
    kernel.close()


def test_actual_gfx1030_hiprtc_compile_exports_exactly_four_fixed_kernels(
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
    hiprtc = fgmres_rtc_v2._load_hiprtc_api(library)
    status, major, minor = hiprtc.version()
    assert status == 0
    assert major >= 0 and minor >= 0
    fixed_source = fgmres_rtc_v2._fixed_source()
    assert b"constexpr int kControlModePredecessorValidate = 14;" in fixed_source
    assert b"kControlOffsetPredecessorValidationState" in fixed_source
    assert b"kControlOffsetPredecessorMaskSnapshot" in fixed_source
    assert b"kControlOffsetPredecessorReductionEpochSnapshot" in fixed_source
    assert b"kPredecessorValidationArmed" in fixed_source
    assert b"kPredecessorValidationConsumed" in fixed_source
    code_object, compile_log = fgmres_rtc_v2._compile_fixed_source(
        hiprtc,
        fixed_source,
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
    code_path = tmp_path / "fgmres-recurrence-v2.co"
    code_path.write_bytes(code_object)
    symbol_text = subprocess.run(
        [llvm_nm, str(code_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    exported_kernels = {
        match.group(1)
        for line in symbol_text.splitlines()
        if (match := re.search(r"\bT (engine_v2_fgmres_[A-Za-z0-9_]+_v2)$", line))
    }
    assert exported_kernels == set(SYMBOLS)
    assert HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK == 512
