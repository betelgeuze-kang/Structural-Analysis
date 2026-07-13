"""Fixed-source HIPRTC owner for the first device FGMRES recurrence slice.

This module binds seven package-owned kernels that initialize and update the
exact little-endian FGMRES solve record, apply the reduced CSR operator, form
true residuals, copy/scale vectors, and apply positive Jacobi scaling.  It is
an ABI and module-lifetime owner only; allocation and solver scheduling belong
to the future live FGMRES child context.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field, replace
import math
from pathlib import Path
import re
from typing import Any

from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.rtc_backend.rtc import (
    HipRtcError,
    HipRtcLibraryIdentity,
    _RuntimeModuleApi,
    _compile_fixed_source,
    _load_hiprtc_api,
    _pointer_integer,
    _runtime_error_string,
    _runtime_library_identity,
    _sha256_bytes,
    _validate_architecture,
    _validate_rtc_library_identity,
    _validate_runtime_identity,
    _valid_sha256,
)

from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_MAX_RESTART_DIMENSION,
    HIP_FGMRES_RECURRENCE_ABI_VERSION,
    HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES,
    HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES,
    hip_fgmres_solve_record_abi_payload_v1,
)


HIP_RTC_FGMRES_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-fgmres-kernel-identity.v1"
)
HIP_RTC_FGMRES_ABI_VERSION = 1
HIP_RTC_FGMRES_KERNEL_NAME = "engine_v2_fgmres_v1"
HIP_RTC_FGMRES_BLOCK_SIZE = 256

HIP_RTC_FGMRES_RECORD_INITIALIZE_SYMBOL = (
    "engine_v2_fgmres_record_initialize_v1"
)
HIP_RTC_FGMRES_CSR_SPMV_SYMBOL = "engine_v2_fgmres_csr_spmv_v1"
HIP_RTC_FGMRES_RESIDUAL_SYMBOL = "engine_v2_fgmres_residual_v1"
HIP_RTC_FGMRES_COPY_SCALE_SYMBOL = "engine_v2_fgmres_copy_scale_v1"
HIP_RTC_FGMRES_APPLY_JACOBI_SYMBOL = "engine_v2_fgmres_apply_jacobi_v1"
HIP_RTC_FGMRES_CONTROL_TERMINAL_SYMBOL = (
    "engine_v2_fgmres_control_terminal_v1"
)
HIP_RTC_FGMRES_RECORD_RESTART_SYMBOL = "engine_v2_fgmres_record_restart_v1"

FGMRES_DEVICE_ERROR_NONE = 0
FGMRES_DEVICE_ERROR_INVALID_CONTROL_OR_GEOMETRY = 1 << 0
FGMRES_DEVICE_ERROR_CSR_STRUCTURE = 1 << 1
FGMRES_DEVICE_ERROR_NONFINITE_INPUT = 1 << 2
FGMRES_DEVICE_ERROR_ARITHMETIC_OVERFLOW = 1 << 3
FGMRES_DEVICE_ERROR_RECORD_ABI = 1 << 4
FGMRES_DEVICE_ERROR_JACOBI = 1 << 5

_SOURCE_RESOURCE = "kernels/engine_v2_fgmres_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17", "-ffp-contract=off")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1

_SYMBOL_ITEMS = (
    ("record_initialize", HIP_RTC_FGMRES_RECORD_INITIALIZE_SYMBOL),
    ("csr_spmv", HIP_RTC_FGMRES_CSR_SPMV_SYMBOL),
    ("residual", HIP_RTC_FGMRES_RESIDUAL_SYMBOL),
    ("copy_scale", HIP_RTC_FGMRES_COPY_SCALE_SYMBOL),
    ("apply_jacobi", HIP_RTC_FGMRES_APPLY_JACOBI_SYMBOL),
    ("control_terminal", HIP_RTC_FGMRES_CONTROL_TERMINAL_SYMBOL),
    ("record_restart", HIP_RTC_FGMRES_RECORD_RESTART_SYMBOL),
)
_DEVICE_ERROR_BITS = {
    "invalid_control_or_geometry": (
        FGMRES_DEVICE_ERROR_INVALID_CONTROL_OR_GEOMETRY
    ),
    "csr_structure": FGMRES_DEVICE_ERROR_CSR_STRUCTURE,
    "nonfinite_input": FGMRES_DEVICE_ERROR_NONFINITE_INPUT,
    "arithmetic_overflow": FGMRES_DEVICE_ERROR_ARITHMETIC_OVERFLOW,
    "record_abi": FGMRES_DEVICE_ERROR_RECORD_ABI,
    "jacobi": FGMRES_DEVICE_ERROR_JACOBI,
}
_CONTROL_MODES = {
    "initial_true_residual": 0,
    "candidate_true_residual": 1,
    "max_iterations_finalize": 2,
}
_LAUNCH_ARGUMENTS = {
    "record_initialize": (
        ("restart_dimension", "i32", "host_value"),
        ("max_iterations", "i32", "host_value"),
        ("maximum_restart_count", "i32", "host_derived_value"),
        ("absolute_tolerance", "f64", "host_value"),
        ("relative_tolerance", "f64", "host_value"),
        ("authoritative_tolerance", "f64", "host_value"),
        ("rhs_l2", "const_device_pointer_f64", "external_device_scalar"),
        ("rhs_linf", "const_device_pointer_f64", "external_device_scalar"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "csr_spmv": (
        ("n", "i32", "host_value"),
        ("nnz", "i32", "host_value"),
        ("row_ptr", "const_device_pointer_i32", "borrowed_base"),
        ("column_indices", "const_device_pointer_i32", "borrowed_base"),
        ("values", "const_device_pointer_f64", "borrowed_base"),
        ("input", "const_device_pointer_f64", "device_vector_base"),
        ("output", "device_pointer_f64", "device_vector_base"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "residual": (
        ("n", "i32", "host_value"),
        ("rhs", "const_device_pointer_f64", "borrowed_base"),
        ("operator_value", "const_device_pointer_f64", "device_vector_base"),
        ("residual", "device_pointer_f64", "device_vector_base"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "copy_scale": (
        ("n", "i32", "host_value"),
        ("scale", "f64", "host_value"),
        ("input", "const_device_pointer_f64", "device_vector_base"),
        ("output", "device_pointer_f64", "device_vector_base"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "apply_jacobi": (
        ("n", "i32", "host_value"),
        ("inverse_diagonal", "const_device_pointer_f64", "borrowed_base"),
        ("input", "const_device_pointer_f64", "device_vector_base"),
        ("output", "device_pointer_f64", "device_vector_base"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "control_terminal": (
        ("control_mode", "i32", "host_value"),
        (
            "residual_l2",
            "const_device_pointer_f64",
            "external_device_scalar",
        ),
        (
            "residual_linf",
            "const_device_pointer_f64",
            "external_device_scalar",
        ),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
    "record_restart": (
        ("restart_index", "i32", "host_value"),
        ("start_iteration", "i32", "host_value"),
        ("end_iteration", "i32", "host_value"),
        ("arnoldi_step_count", "i32", "host_value"),
        ("reorthogonalization_count", "i32", "host_value"),
        ("termination_hint", "i32", "host_value"),
        ("flags", "i32", "host_value"),
        ("estimated_residual_l2", "f64", "host_value"),
        ("true_residual_l2", "f64", "host_value"),
        ("true_residual_linf", "f64", "host_value"),
        ("scaled_true_residual", "f64", "host_value"),
        ("solution_update_l2", "f64", "host_value"),
        ("solve_record", "device_pointer_u8", "owned_record_base"),
    ),
}

class HipRtcFgmresError(HipRtcError):
    """Stable fail-closed error for the fixed FGMRES HIPRTC lane."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        cleanup_owner: _HipRtcFgmresModuleCleanupOwner | None = None,
    ) -> None:
        if cleanup_owner is not None and type(cleanup_owner) is not (
            _HipRtcFgmresModuleCleanupOwner
        ):
            raise TypeError("cleanup_owner has an invalid owner type")
        self.cleanup_owner = cleanup_owner
        super().__init__(code, message, compile_log=compile_log)


class _HipRtcFgmresModuleCleanupOwner:
    """Retryable owner for a loaded module whose eager cleanup failed."""

    __slots__ = ("_runtime", "_module", "_closed")

    def __init__(self, runtime: _RuntimeModuleApi, module: ctypes.c_void_p) -> None:
        if not module.value:
            raise ValueError("cleanup owner requires a loaded module")
        self._runtime = runtime
        self._module = module
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        try:
            status = int(self._runtime.unload(self._module))
        except Exception as exc:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_cleanup_failed",
                f"hipModuleUnload cleanup retry raised {type(exc).__name__}.",
                cleanup_owner=self,
            ) from exc
        if status != 0:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_cleanup_failed",
                "hipModuleUnload cleanup retry failed: "
                f"{self._runtime.error_string(status)}.",
                cleanup_owner=self,
            )
        self._module = ctypes.c_void_p()
        self._closed = True


@dataclass(frozen=True, slots=True)
class HipRtcFgmresKernelIdentity:
    """Handle-free identity for the fixed seven-symbol FGMRES module."""

    schema_version: str
    abi_version: int
    recurrence_abi_version: int
    kernel_name: str
    kernel_symbols: tuple[str, ...]
    block_size: int
    solve_record_header_bytes: int
    solve_record_restart_bytes: int
    solve_record_layout_hash: str
    kernel_interface_hash: str
    source_resource: str
    source_sha256: str
    compile_options: tuple[str, ...]
    architecture: str
    hiprtc_version_major: int
    hiprtc_version_minor: int
    hiprtc_library: HipRtcLibraryIdentity
    runtime_library: HipRuntimeLibraryIdentity
    code_object_byte_length: int
    code_object_sha256: str
    identity_hash: str
    _code_object_witness: bytes = field(
        default=b"", init=False, repr=False, compare=False
    )

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcFgmresKernel:
    """Loaded FGMRES recurrence module with fenced stream ownership."""

    __slots__ = (
        "_runtime",
        "_module",
        "_functions",
        "_identity",
        "_closed",
        "_pending_streams",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        functions: dict[str, ctypes.c_void_p],
        identity: HipRtcFgmresKernelIdentity,
    ) -> None:
        self._runtime = runtime
        self._module = module
        self._functions = dict(functions)
        self._identity = identity
        self._closed = False
        self._pending_streams: dict[int, int] = {}

    @property
    def identity(self) -> HipRtcFgmresKernelIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def pending_stream_count(self) -> int:
        return len(self._pending_streams)

    def __enter__(self) -> HipRtcFgmresKernel:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_record_initialize(
        self,
        stream: Any,
        restart_dimension: int,
        max_iterations: int,
        absolute_tolerance: float,
        relative_tolerance: float,
        authoritative_tolerance: float,
        rhs_l2: Any,
        rhs_linf: Any,
        solve_record: Any,
    ) -> None:
        self._require_open()
        checked_restart = _bounded_int(
            restart_dimension,
            "restart_dimension",
            minimum=1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        checked_iterations = _bounded_int(
            max_iterations,
            "max_iterations",
            minimum=0,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        maximum_restarts = (
            0
            if checked_iterations == 0
            else (checked_iterations + checked_restart - 1) // checked_restart
        )
        tolerances = (
            _nonnegative_float64(absolute_tolerance, "absolute_tolerance"),
            _nonnegative_float64(relative_tolerance, "relative_tolerance"),
            _nonnegative_float64(
                authoritative_tolerance, "authoritative_tolerance"
            ),
        )
        pointers = _pointer_arguments(
            (("rhs_l2", rhs_l2), ("rhs_linf", rhs_linf), ("solve_record", solve_record))
        )
        self._launch(
            "record_initialize",
            stream=stream,
            grid_x=1,
            arguments=(
                ctypes.c_int(checked_restart),
                ctypes.c_int(checked_iterations),
                ctypes.c_int(maximum_restarts),
                *(ctypes.c_double(value) for value in tolerances),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES solve-record initialization",
        )

    def launch_csr_spmv(
        self,
        stream: Any,
        n: int,
        nnz: int,
        row_ptr: Any,
        column_indices: Any,
        values: Any,
        input_vector: Any,
        output_vector: Any,
        solve_record: Any,
    ) -> None:
        self._require_open()
        checked_n = _positive_int32(n, "n")
        checked_nnz = _positive_int32(nnz, "nnz")
        if checked_nnz < checked_n:
            raise _launch_contract_error("nnz must be greater than or equal to n.")
        pointers = _pointer_arguments(
            (
                ("row_ptr", row_ptr),
                ("column_indices", column_indices),
                ("values", values),
                ("input_vector", input_vector),
                ("output_vector", output_vector),
                ("solve_record", solve_record),
            )
        )
        self._launch_vector(
            "csr_spmv", stream, checked_n, (ctypes.c_int(checked_nnz),), pointers
        )

    def launch_residual(
        self,
        stream: Any,
        n: int,
        rhs: Any,
        operator_value: Any,
        residual: Any,
        solve_record: Any,
    ) -> None:
        self._launch_vector_pointers(
            "residual",
            stream,
            n,
            (
                ("rhs", rhs),
                ("operator_value", operator_value),
                ("residual", residual),
                ("solve_record", solve_record),
            ),
        )

    def launch_copy_scale(
        self,
        stream: Any,
        n: int,
        scale: float,
        input_vector: Any,
        output_vector: Any,
        solve_record: Any,
    ) -> None:
        self._require_open()
        checked_n = _positive_int32(n, "n")
        checked_scale = _finite_float64(scale, "scale")
        pointers = _pointer_arguments(
            (
                ("input_vector", input_vector),
                ("output_vector", output_vector),
                ("solve_record", solve_record),
            )
        )
        self._launch_vector(
            "copy_scale",
            stream,
            checked_n,
            (ctypes.c_double(checked_scale),),
            pointers,
        )

    def launch_apply_jacobi(
        self,
        stream: Any,
        n: int,
        inverse_diagonal: Any,
        input_vector: Any,
        output_vector: Any,
        solve_record: Any,
    ) -> None:
        self._launch_vector_pointers(
            "apply_jacobi",
            stream,
            n,
            (
                ("inverse_diagonal", inverse_diagonal),
                ("input_vector", input_vector),
                ("output_vector", output_vector),
                ("solve_record", solve_record),
            ),
        )

    def launch_control_terminal(
        self,
        stream: Any,
        control_mode: int,
        residual_l2: Any,
        residual_linf: Any,
        solve_record: Any,
    ) -> None:
        self._require_open()
        checked_mode = _bounded_int(
            control_mode, "control_mode", minimum=0, maximum=2
        )
        pointers = _pointer_arguments(
            (
                ("residual_l2", residual_l2),
                ("residual_linf", residual_linf),
                ("solve_record", solve_record),
            )
        )
        self._launch(
            "control_terminal",
            stream=stream,
            grid_x=1,
            arguments=(
                ctypes.c_int(checked_mode),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES terminal control",
        )

    def launch_record_restart(
        self,
        stream: Any,
        restart_index: int,
        start_iteration: int,
        end_iteration: int,
        arnoldi_step_count: int,
        reorthogonalization_count: int,
        termination_hint: int,
        flags: int,
        estimated_residual_l2: float,
        true_residual_l2: float,
        true_residual_linf: float,
        scaled_true_residual: float,
        solution_update_l2: float,
        solve_record: Any,
    ) -> None:
        self._require_open()
        integer_values = (
            _bounded_int(
                restart_index,
                "restart_index",
                minimum=1,
                maximum=HIP_FGMRES_MAX_ITERATIONS,
            ),
            _bounded_int(
                start_iteration,
                "start_iteration",
                minimum=0,
                maximum=HIP_FGMRES_MAX_ITERATIONS,
            ),
            _bounded_int(
                end_iteration,
                "end_iteration",
                minimum=0,
                maximum=HIP_FGMRES_MAX_ITERATIONS,
            ),
            _bounded_int(
                arnoldi_step_count,
                "arnoldi_step_count",
                minimum=1,
                maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
            ),
            _bounded_int(
                reorthogonalization_count,
                "reorthogonalization_count",
                minimum=0,
                maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
            ),
            _bounded_int(
                termination_hint, "termination_hint", minimum=1, maximum=5
            ),
            _bounded_int(flags, "flags", minimum=0, maximum=255),
        )
        if integer_values[2] < integer_values[1]:
            raise _launch_contract_error(
                "end_iteration must not precede start_iteration."
            )
        if integer_values[3] != integer_values[2] - integer_values[1]:
            raise _launch_contract_error(
                "arnoldi_step_count must equal end_iteration-start_iteration."
            )
        if integer_values[4] > integer_values[3]:
            raise _launch_contract_error(
                "reorthogonalization_count must not exceed arnoldi_step_count."
            )
        if integer_values[6] & ((1 << 5) | (1 << 7)):
            raise _launch_contract_error(
                "stagnation and divergence flags require the future full "
                "recurrence control kernel."
            )
        scalar_values = tuple(
            _nonnegative_float64(value, label)
            for value, label in (
                (estimated_residual_l2, "estimated_residual_l2"),
                (true_residual_l2, "true_residual_l2"),
                (true_residual_linf, "true_residual_linf"),
                (scaled_true_residual, "scaled_true_residual"),
                (solution_update_l2, "solution_update_l2"),
            )
        )
        pointer = _runtime_pointer(solve_record, "solve_record")
        self._launch(
            "record_restart",
            stream=stream,
            grid_x=1,
            arguments=(
                *(ctypes.c_int(value) for value in integer_values),
                *(ctypes.c_double(value) for value in scalar_values),
                ctypes.c_void_p(pointer),
            ),
            operation="FGMRES restart record write",
        )

    def acknowledge_stream_completion(self, stream: Any) -> None:
        self._require_open()
        stream_value = _runtime_pointer(stream, "stream")
        if stream_value not in self._pending_streams:
            raise _launch_contract_error(
                "stream has no pending FGMRES launch to acknowledge."
            )
        del self._pending_streams[stream_value]

    def close(self) -> None:
        if self._closed:
            return
        if self._pending_streams:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_completion_fence_required",
                "HIPRTC FGMRES module has pending stream work; acknowledge an "
                "observed completion fence before unload.",
            )
        try:
            status = int(self._runtime.unload(self._module))
        except Exception as exc:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_unload_failed",
                f"hipModuleUnload raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_unload_failed",
                f"hipModuleUnload failed: {self._runtime.error_string(status)}.",
            )
        self._module = ctypes.c_void_p()
        self._functions.clear()
        self._pending_streams.clear()
        self._closed = True

    def _launch_vector_pointers(
        self,
        function_name: str,
        stream: Any,
        n: int,
        values: tuple[tuple[str, Any], ...],
    ) -> None:
        self._require_open()
        checked_n = _positive_int32(n, "n")
        self._launch_vector(
            function_name,
            stream,
            checked_n,
            (),
            _pointer_arguments(values),
        )

    def _launch_vector(
        self,
        function_name: str,
        stream: Any,
        n: int,
        scalar_arguments: tuple[Any, ...],
        pointers: tuple[int, ...],
    ) -> None:
        self._launch(
            function_name,
            stream=stream,
            grid_x=_vector_block_count(n),
            arguments=(
                ctypes.c_int(n),
                *scalar_arguments,
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation=f"FGMRES {function_name.replace('_', ' ')}",
        )

    def _launch(
        self,
        function_name: str,
        *,
        stream: Any,
        grid_x: int,
        arguments: tuple[Any, ...],
        operation: str,
    ) -> None:
        stream_value = _runtime_pointer(stream, "stream")
        parameters = (ctypes.c_void_p * len(arguments))(
            *(
                ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                for argument in arguments
            )
        )
        self._pending_streams[stream_value] = (
            self._pending_streams.get(stream_value, 0) + 1
        )
        try:
            status = int(
                self._runtime.launch(
                    self._functions[function_name],
                    grid_x=grid_x,
                    block_x=HIP_RTC_FGMRES_BLOCK_SIZE,
                    stream=ctypes.c_void_p(stream_value),
                    parameters=parameters,
                )
            )
        except Exception as exc:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            pending_count = self._pending_streams[stream_value] - 1
            if pending_count:
                self._pending_streams[stream_value] = pending_count
            else:
                del self._pending_streams[stream_value]
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
            )

    def _require_open(self) -> None:
        if self._closed:
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_kernel_closed",
                "HIPRTC FGMRES kernel is closed.",
            )


def solve_record_byte_length(maximum_restart_count: int) -> int:
    """Return the exact v1 record extent for a validated restart count."""

    checked = _bounded_int(
        maximum_restart_count,
        "maximum_restart_count",
        minimum=0,
        maximum=HIP_FGMRES_MAX_ITERATIONS,
    )
    return (
        HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES
        + HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES * checked
    )


def compile_hip_rtc_fgmres_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresKernel:
    """Compile and load the package-owned seven-symbol FGMRES module."""

    try:
        return _compile_fgmres_impl(loaded_runtime, architecture, hiprtc_library)
    except HipRtcFgmresError:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresError(
            exc.code, exc.message, compile_log=exc.compile_log
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_unexpected_failure",
            f"Unexpected HIPRTC FGMRES pipeline failure: {type(exc).__name__}.",
        ) from exc


def _compile_fgmres_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresKernel:
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = _fixed_source()
    source_hash = _sha256_bytes(source)
    options = (f"--offload-arch={checked_architecture}", *_FIXED_OPTION_SUFFIX)
    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_runtime_init_failed",
            f"hipInit failed: {_runtime_error_string(loaded_runtime, init_status)}.",
        )
    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        source,
        options,
        program_name=Path(_SOURCE_RESOURCE).name,
    )
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        _cleanup_failed_load(runtime, module, status, compile_log=compile_log)
    try:
        functions = {
            key: _required_function(runtime, module, symbol, compile_log)
            for key, symbol in _SYMBOL_ITEMS
        }
        identity = _build_identity(
            architecture=checked_architecture,
            source_hash=source_hash,
            options=options,
            rtc_version=(rtc_major, rtc_minor),
            rtc_library=rtc.identity,
            runtime_library=runtime_identity,
            code_object=code_object,
        )
        return HipRtcFgmresKernel(
            runtime=runtime,
            module=module,
            functions=functions,
            identity=identity,
        )
    except Exception as primary:
        _cleanup_loaded_module(runtime, module, primary, compile_log=compile_log)
        raise AssertionError("unreachable")


def _required_function(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    symbol: str,
    compile_log: str,
) -> ctypes.c_void_p:
    status, function = runtime.get_function(module, symbol)
    if status != 0 or not function.value:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_symbol_missing",
            f"hipModuleGetFunction failed for fixed symbol {symbol}: "
            f"{runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    return function


def _cleanup_failed_load(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    status: int,
    *,
    compile_log: str,
) -> None:
    if module.value:
        try:
            cleanup_status = int(runtime.unload(module))
        except Exception as exc:
            owner = _HipRtcFgmresModuleCleanupOwner(runtime, module)
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_cleanup_failed",
                f"hipModuleLoadData failed and cleanup raised {type(exc).__name__}.",
                compile_log=compile_log,
                cleanup_owner=owner,
            ) from exc
        if cleanup_status != 0:
            owner = _HipRtcFgmresModuleCleanupOwner(runtime, module)
            raise HipRtcFgmresError(
                "hip_rtc_fgmres_module_cleanup_failed",
                "hipModuleLoadData failed and cleanup failed: "
                f"{runtime.error_string(cleanup_status)}.",
                compile_log=compile_log,
                cleanup_owner=owner,
            )
    raise HipRtcFgmresError(
        "hip_rtc_fgmres_module_load_failed",
        f"hipModuleLoadData failed: {runtime.error_string(status)}.",
        compile_log=compile_log,
    )


def _cleanup_loaded_module(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    primary: Exception,
    *,
    compile_log: str,
) -> None:
    primary_log = (
        primary.compile_log if isinstance(primary, HipRtcError) else compile_log
    )
    try:
        cleanup_status = int(runtime.unload(module))
    except Exception as exc:
        owner = _HipRtcFgmresModuleCleanupOwner(runtime, module)
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_module_cleanup_failed",
            f"{primary}; hipModuleUnload cleanup raised {type(exc).__name__}.",
            compile_log=primary_log,
            cleanup_owner=owner,
        ) from primary
    if cleanup_status != 0:
        owner = _HipRtcFgmresModuleCleanupOwner(runtime, module)
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_module_cleanup_failed",
            f"{primary}; hipModuleUnload cleanup failed: "
            f"{runtime.error_string(cleanup_status)}.",
            compile_log=primary_log,
            cleanup_owner=owner,
        ) from primary
    raise primary


def _build_identity(
    *,
    architecture: str,
    source_hash: str,
    options: tuple[str, ...],
    rtc_version: tuple[int, int],
    rtc_library: HipRtcLibraryIdentity,
    runtime_library: HipRuntimeLibraryIdentity,
    code_object: bytes,
) -> HipRtcFgmresKernelIdentity:
    initial = HipRtcFgmresKernelIdentity(
        schema_version=HIP_RTC_FGMRES_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_FGMRES_ABI_VERSION,
        recurrence_abi_version=HIP_FGMRES_RECURRENCE_ABI_VERSION,
        kernel_name=HIP_RTC_FGMRES_KERNEL_NAME,
        kernel_symbols=tuple(symbol for _, symbol in _SYMBOL_ITEMS),
        block_size=HIP_RTC_FGMRES_BLOCK_SIZE,
        solve_record_header_bytes=HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES,
        solve_record_restart_bytes=HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES,
        solve_record_layout_hash=canonical_hash(_solve_record_layout_payload()),
        kernel_interface_hash=canonical_hash(_kernel_interface_payload()),
        source_resource=_SOURCE_RESOURCE,
        source_sha256=source_hash,
        compile_options=options,
        architecture=architecture,
        hiprtc_version_major=int(rtc_version[0]),
        hiprtc_version_minor=int(rtc_version[1]),
        hiprtc_library=rtc_library,
        runtime_library=runtime_library,
        code_object_byte_length=len(code_object),
        code_object_sha256=_sha256_bytes(code_object),
        identity_hash="",
    )
    identity = replace(
        initial,
        identity_hash=canonical_hash(_identity_payload(initial, include_hash=False)),
    )
    object.__setattr__(identity, "_code_object_witness", bytes(code_object))
    _validate_identity(identity)
    return identity


def _identity_payload(
    identity: HipRtcFgmresKernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "recurrence_abi_version": identity.recurrence_abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            key: symbol for (key, _), symbol in zip(_SYMBOL_ITEMS, identity.kernel_symbols)
        },
        "launch_geometry": {"block_size": identity.block_size},
        "solve_record_abi": {
            **_solve_record_layout_payload(),
            "layout_hash": identity.solve_record_layout_hash,
        },
        "kernel_interface": {
            **_kernel_interface_payload(),
            "interface_hash": identity.kernel_interface_hash,
        },
        "source_resource": identity.source_resource,
        "source_sha256": identity.source_sha256,
        "compile_options": list(identity.compile_options),
        "architecture": identity.architecture,
        "hiprtc_version": {
            "major": identity.hiprtc_version_major,
            "minor": identity.hiprtc_version_minor,
        },
        "hiprtc_library": identity.hiprtc_library.to_dict(),
        "runtime_library": identity.runtime_library.to_dict(),
        "code_object_byte_length": identity.code_object_byte_length,
        "code_object_sha256": identity.code_object_sha256,
    }
    if include_hash:
        payload["identity_hash"] = identity.identity_hash
    return payload


def _solve_record_layout_payload() -> dict[str, Any]:
    return hip_fgmres_solve_record_abi_payload_v1()


def _kernel_interface_payload() -> dict[str, Any]:
    vector_launches = {"csr_spmv", "residual", "copy_scale", "apply_jacobi"}
    return {
        "abi_version": HIP_RTC_FGMRES_ABI_VERSION,
        "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION,
        "solve_record_layout_hash": canonical_hash(
            _solve_record_layout_payload()
        ),
        "device_error_bits": dict(_DEVICE_ERROR_BITS),
        "control_modes": dict(_CONTROL_MODES),
        "launches": {
            key: {
                "symbol": symbol,
                "arguments": [
                    {"name": name, "abi": abi, "source": source}
                    for name, abi, source in _LAUNCH_ARGUMENTS[key]
                ],
                "block_size": HIP_RTC_FGMRES_BLOCK_SIZE,
                "grid_rule": (
                    "ceil_n_over_block_size"
                    if key in vector_launches
                    else "exactly_one_block"
                ),
                "active_masked": key != "record_initialize",
            }
            for key, symbol in _SYMBOL_ITEMS
        },
    }


def _source_abi_constant_bindings() -> tuple[tuple[str, int], ...]:
    record = _solve_record_layout_payload()
    header_offsets = {
        row["name"]: row["offset_bytes"] for row in record["header_fields"]
    }
    restart_offsets = {
        row["name"]: row["offset_bytes"] for row in record["restart_fields"]
    }
    terminal = record["terminal_status_codes"]
    termination = record["termination_codes"]
    hints = record["restart_hint_codes"]
    flags = record["restart_flag_bits"]
    return (
        ("kBlockSize", HIP_RTC_FGMRES_BLOCK_SIZE),
        ("kRecurrenceAbiVersion", HIP_FGMRES_RECURRENCE_ABI_VERSION),
        ("kHeaderBytes", record["header_bytes"]),
        ("kRestartBytes", record["restart_bytes"]),
        ("kMaximumRestartDimension", HIP_FGMRES_MAX_RESTART_DIMENSION),
        ("kMaximumIterations", HIP_FGMRES_MAX_ITERATIONS),
        (
            "kErrorInvalidControlOrGeometry",
            _DEVICE_ERROR_BITS["invalid_control_or_geometry"],
        ),
        ("kErrorCsrStructure", _DEVICE_ERROR_BITS["csr_structure"]),
        ("kErrorNonfiniteInput", _DEVICE_ERROR_BITS["nonfinite_input"]),
        ("kErrorArithmeticOverflow", _DEVICE_ERROR_BITS["arithmetic_overflow"]),
        ("kErrorRecordAbi", _DEVICE_ERROR_BITS["record_abi"]),
        ("kErrorJacobi", _DEVICE_ERROR_BITS["jacobi"]),
        ("kTerminalNotTerminal", terminal["not_terminal"]),
        ("kTerminalConverged", terminal["converged"]),
        ("kTerminalMaxIterations", terminal["max_iterations"]),
        ("kTerminalStagnated", terminal["stagnated"]),
        ("kTerminalDiverged", terminal["diverged"]),
        ("kTerminalArnoldiBreakdown", terminal["arnoldi_breakdown"]),
        ("kTerminalNumericalFailure", terminal["numerical_failure"]),
        ("kTerminationNone", termination["none"]),
        (
            "kTerminationConvergedInitial",
            termination["converged_initial_true_residual"],
        ),
        (
            "kTerminationConvergedHappyBreakdown",
            termination["converged_happy_breakdown"],
        ),
        (
            "kTerminationConvergedTrueResidual",
            termination["converged_true_residual"],
        ),
        (
            "kTerminationConvergedRestart",
            termination["converged_restart_true_residual"],
        ),
        ("kTerminationMaxIterations", termination["max_iterations_exhausted"]),
        (
            "kTerminationTrueResidualStagnated",
            termination["true_residual_stagnated"],
        ),
        (
            "kTerminationTrueResidualDiverged",
            termination["true_residual_diverged"],
        ),
        (
            "kTerminationTriangularFactorBreakdown",
            termination["arnoldi_triangular_factor_breakdown"],
        ),
        (
            "kTerminationInvariantSubspaceBreakdown",
            termination["arnoldi_invariant_subspace_breakdown"],
        ),
        ("kTerminationInvalidControl", termination["invalid_input_or_control"]),
        (
            "kTerminationNonfiniteArithmetic",
            termination["nonfinite_arithmetic"],
        ),
        (
            "kTerminationOperatorFailed",
            termination["operator_application_failed"],
        ),
        (
            "kTerminationOrthogonalizationFailed",
            termination["orthogonalization_failed"],
        ),
        (
            "kTerminationGivensRotationFailed",
            termination["givens_rotation_failed"],
        ),
        (
            "kTerminationTriangularSolveFailed",
            termination["triangular_solve_failed"],
        ),
        (
            "kTerminationTrueResidualReplayFailed",
            termination["true_residual_replay_failed"],
        ),
        (
            "kTerminationRestartStateFailed",
            termination["restart_state_failed"],
        ),
        ("kRestartHintNone", hints["none"]),
        ("kRestartHintRestartCompleted", hints["restart_completed"]),
        (
            "kRestartHintConvergedHappyBreakdown",
            hints["converged_happy_breakdown"],
        ),
        (
            "kRestartHintConvergedTrueResidual",
            hints["converged_true_residual"],
        ),
        (
            "kRestartHintInvariantBreakdown",
            hints["arnoldi_invariant_subspace_breakdown"],
        ),
        (
            "kRestartHintTriangularBreakdown",
            hints["arnoldi_triangular_factor_breakdown"],
        ),
        (
            "kRestartFlagTrueResidualReplayed",
            1 << flags["true_residual_replayed"],
        ),
        ("kRestartFlagSolverL2Passed", 1 << flags["solver_l2_passed"]),
        (
            "kRestartFlagAuthoritativeLinfPassed",
            1 << flags["authoritative_linf_passed"],
        ),
        ("kRestartFlagHappyBreakdown", 1 << flags["happy_breakdown"]),
        ("kRestartFlagInvariantBreakdown", 1 << flags["invariant_breakdown"]),
        ("kRestartFlagStagnationPlateau", 1 << flags["stagnation_plateau"]),
        ("kRestartFlagTinyUpdate", 1 << flags["tiny_update"]),
        ("kRestartFlagDivergence", 1 << flags["divergence"]),
        ("kControlInitialTrueResidual", _CONTROL_MODES["initial_true_residual"]),
        (
            "kControlCandidateTrueResidual",
            _CONTROL_MODES["candidate_true_residual"],
        ),
        (
            "kControlMaxIterationsFinalize",
            _CONTROL_MODES["max_iterations_finalize"],
        ),
        ("kOffsetAbiVersion", header_offsets["recurrence_abi_version"]),
        ("kOffsetActive", header_offsets["active"]),
        ("kOffsetTerminalStatus", header_offsets["terminal_status"]),
        ("kOffsetTerminationCode", header_offsets["termination_code"]),
        ("kOffsetDeviceErrorBits", header_offsets["device_error_bits"]),
        ("kOffsetScheduledIterations", header_offsets["scheduled_iterations"]),
        ("kOffsetEffectiveIterations", header_offsets["effective_iterations"]),
        ("kOffsetScheduledRestarts", header_offsets["scheduled_restarts"]),
        ("kOffsetEffectiveRestarts", header_offsets["effective_restarts"]),
        (
            "kOffsetEffectiveArnoldiDimension",
            header_offsets["effective_arnoldi_dimension"],
        ),
        ("kOffsetHappyBreakdownCount", header_offsets["happy_breakdown_count"]),
        (
            "kOffsetStagnationCheckpointCount",
            header_offsets["stagnation_checkpoint_count"],
        ),
        (
            "kOffsetFalseConvergenceCount",
            header_offsets["false_convergence_count"],
        ),
        ("kOffsetOperatorApplyCount", header_offsets["operator_apply_count"]),
        (
            "kOffsetPreconditionerApplyCount",
            header_offsets["preconditioner_apply_count"],
        ),
        ("kOffsetRestartDimension", header_offsets["restart_dimension"]),
        ("kOffsetRhsL2", header_offsets["rhs_l2"]),
        ("kOffsetRhsLinf", header_offsets["rhs_linf"]),
        ("kOffsetSolverToleranceL2", header_offsets["solver_tolerance_l2"]),
        (
            "kOffsetAuthoritativeTolerance",
            header_offsets["authoritative_tolerance_scaled_linf"],
        ),
        ("kOffsetInitialResidualL2", header_offsets["initial_residual_l2"]),
        ("kOffsetFinalResidualL2", header_offsets["final_residual_l2"]),
        ("kOffsetFinalResidualLinf", header_offsets["final_residual_linf"]),
        ("kOffsetFinalScaledResidual", header_offsets["final_scaled_residual"]),
        (
            "kOffsetPreviousCheckpointResidualL2",
            header_offsets["previous_checkpoint_residual_l2"],
        ),
        ("kOffsetSolutionUpdateL2", header_offsets["solution_update_l2"]),
        ("kOffsetSolutionScaleL2", header_offsets["solution_scale_l2"]),
        ("kOffsetEstimatedResidualL2", header_offsets["estimated_residual_l2"]),
        ("kOffsetArnoldiWorkL2", header_offsets["arnoldi_work_l2"]),
        (
            "kOffsetArnoldiBreakdownThreshold",
            header_offsets["arnoldi_breakdown_threshold"],
        ),
        ("kOffsetTriangularScale", header_offsets["triangular_scale"]),
        ("kOffsetReservedF64", header_offsets["reserved_f64_0"]),
        ("kRestartOffsetIndex", restart_offsets["restart_index"]),
        ("kRestartOffsetStartIteration", restart_offsets["start_iteration"]),
        ("kRestartOffsetEndIteration", restart_offsets["end_iteration"]),
        (
            "kRestartOffsetArnoldiStepCount",
            restart_offsets["arnoldi_step_count"],
        ),
        (
            "kRestartOffsetReorthogonalizationCount",
            restart_offsets["reorthogonalization_count"],
        ),
        (
            "kRestartOffsetTerminationHint",
            restart_offsets["termination_hint"],
        ),
        ("kRestartOffsetFlags", restart_offsets["flags"]),
        ("kRestartOffsetReservedI32", restart_offsets["reserved_i32_0"]),
        (
            "kRestartOffsetEstimatedResidualL2",
            restart_offsets["estimated_residual_l2"],
        ),
        ("kRestartOffsetTrueResidualL2", restart_offsets["true_residual_l2"]),
        (
            "kRestartOffsetTrueResidualLinf",
            restart_offsets["true_residual_linf"],
        ),
        (
            "kRestartOffsetScaledTrueResidual",
            restart_offsets["scaled_true_residual"],
        ),
        (
            "kRestartOffsetSolutionUpdateL2",
            restart_offsets["solution_update_l2"],
        ),
    )


def _source_symbol_argument_declarations() -> tuple[tuple[str, bytes], ...]:
    c_types = {
        "i32": "int",
        "f64": "double",
        "const_device_pointer_i32": "const int*",
        "device_pointer_i32": "int*",
        "const_device_pointer_f64": "const double*",
        "device_pointer_f64": "double*",
        "device_pointer_u8": "unsigned char*",
    }
    return tuple(
        (
            symbol,
            ", ".join(
                f"{c_types[abi]} {name}"
                for name, abi, _source in _LAUNCH_ARGUMENTS[key]
            ).encode("ascii"),
        )
        for key, symbol in _SYMBOL_ITEMS
    )


def _validate_identity(identity: Any) -> None:
    if type(identity) is not HipRtcFgmresKernelIdentity:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid", "FGMRES identity type is invalid."
        )
    integer_fields = (
        identity.abi_version,
        identity.recurrence_abi_version,
        identity.block_size,
        identity.solve_record_header_bytes,
        identity.solve_record_restart_bytes,
        identity.hiprtc_version_major,
        identity.hiprtc_version_minor,
        identity.code_object_byte_length,
    )
    string_fields = (
        identity.schema_version,
        identity.kernel_name,
        identity.solve_record_layout_hash,
        identity.kernel_interface_hash,
        identity.source_resource,
        identity.source_sha256,
        identity.architecture,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if (
        any(type(value) is not int for value in integer_fields)
        or any(type(value) is not str for value in string_fields)
        or type(identity.kernel_symbols) is not tuple
        or type(identity.compile_options) is not tuple
        or type(identity._code_object_witness) is not bytes
        or any(type(value) is not str for value in identity.kernel_symbols)
        or any(type(value) is not str for value in identity.compile_options)
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid",
            "FGMRES identity tuple or witness fields are invalid.",
        )
    expected_symbols = tuple(symbol for _, symbol in _SYMBOL_ITEMS)
    if (
        identity.schema_version != HIP_RTC_FGMRES_IDENTITY_SCHEMA_VERSION
        or identity.abi_version != HIP_RTC_FGMRES_ABI_VERSION
        or identity.recurrence_abi_version != HIP_FGMRES_RECURRENCE_ABI_VERSION
        or identity.kernel_name != HIP_RTC_FGMRES_KERNEL_NAME
        or identity.kernel_symbols != expected_symbols
        or identity.block_size != HIP_RTC_FGMRES_BLOCK_SIZE
        or identity.solve_record_header_bytes
        != HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES
        or identity.solve_record_restart_bytes
        != HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES
        or identity.solve_record_layout_hash
        != canonical_hash(_solve_record_layout_payload())
        or identity.kernel_interface_hash
        != canonical_hash(_kernel_interface_payload())
        or identity.source_resource != _SOURCE_RESOURCE
        or identity.source_sha256 != _sha256_bytes(_fixed_source())
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid", "Fixed FGMRES ABI is invalid."
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid", exc.message
        ) from exc
    if identity.compile_options != (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid",
            "FGMRES compile options are not fixed.",
        )
    hashes = (
        identity.solve_record_layout_hash,
        identity.kernel_interface_hash,
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid", "FGMRES identity hash is invalid."
        )
    if (
        len(identity._code_object_witness) != identity.code_object_byte_length
        or _sha256_bytes(identity._code_object_witness)
        != identity.code_object_sha256
        or identity.code_object_byte_length <= 0
        or identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_invalid",
            "FGMRES code-object witness or version is invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_identity_hash_mismatch",
            "FGMRES identity hash is invalid.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_source_missing",
            f"The package-owned FGMRES source is unavailable: {type(exc).__name__}.",
        ) from exc
    signatures_valid = True
    for symbol, expected_arguments in _source_symbol_argument_declarations():
        pattern = re.compile(
            rb'extern\s+"C"\s+__global__\s+void\s+'
            + re.escape(symbol.encode("ascii"))
            + rb"\s*\((.*?)\)\s*\{",
            re.DOTALL,
        )
        matches = pattern.findall(source)
        normalized = b" ".join(matches[0].split()) if len(matches) == 1 else b""
        if len(matches) != 1 or normalized != expected_arguments:
            signatures_valid = False
            break
    interface_marker = (
        "// engine-v2-fgmres-interface-v1: "
        + canonical_hash(_kernel_interface_payload())
    ).encode("ascii")
    constant_markers = tuple(
        f"constexpr int {name} = {value};".encode("ascii")
        for name, value in _source_abi_constant_bindings()
    )
    if (
        not source
        or not signatures_valid
        or source.count(interface_marker) != 1
        or any(source.count(marker) != 1 for marker in constant_markers)
    ):
        raise HipRtcFgmresError(
            "hip_rtc_fgmres_source_invalid",
            "Package-owned FGMRES source must contain every fixed symbol once "
            "and bind the exact kernel-interface hash and ABI constants.",
        )
    return source


def _positive_int32(value: Any, label: str) -> int:
    return _bounded_int(value, label, minimum=1)


def _bounded_int(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int = _INT32_MAX,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _launch_contract_error(
            f"{label} must be a signed int32 in [{minimum}, {maximum}]."
        )
    return value


def _finite_float64(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise _launch_contract_error(f"{label} must be an exact int or float.")
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise _launch_contract_error(f"{label} must fit finite float64.") from exc
    if not math.isfinite(converted):
        raise _launch_contract_error(f"{label} must be finite float64.")
    return converted


def _nonnegative_float64(value: Any, label: str) -> float:
    converted = _finite_float64(value, label)
    if converted < 0.0:
        raise _launch_contract_error(f"{label} must be nonnegative.")
    return converted


def _vector_block_count(value_count: int) -> int:
    return (value_count + HIP_RTC_FGMRES_BLOCK_SIZE - 1) // (
        HIP_RTC_FGMRES_BLOCK_SIZE
    )


def _pointer_arguments(values: tuple[tuple[str, Any], ...]) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise _launch_contract_error(exc.message) from exc
    if pointer > _UINTPTR_MAX or ctypes.c_void_p(pointer).value != pointer:
        raise _launch_contract_error(
            f"{label} does not fit the native uintptr capacity."
        )
    return pointer


def _launch_contract_error(message: str) -> HipRtcFgmresError:
    return HipRtcFgmresError(
        "hip_rtc_fgmres_launch_contract_invalid", message
    )
