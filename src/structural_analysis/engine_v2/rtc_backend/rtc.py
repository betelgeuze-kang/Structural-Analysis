"""Fixed-source HIPRTC toolchain for the Engine v2 fused CSR kernel.

Only a plain AMD ``gfx`` architecture and an optional HIPRTC library path are
accepted. Source text, compiler options, headers, and symbols are package
owned. Serialized identities contain hashes and versions, never live handles.
"""

from __future__ import annotations

from collections.abc import Sequence
import ctypes
import ctypes.util
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re
from typing import Any

from structural_analysis.engine_v2.backends.hip.types import (
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

HIP_RTC_CSR_KERNEL_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-csr-kernel-identity.v1"
)
HIP_RTC_CSR_KERNEL_ABI_VERSION = 1
HIP_RTC_CSR_KERNEL_NAME = "engine_v2_csr_residual_jvp_v1"
HIP_RTC_CSR_KERNEL_SYMBOL = HIP_RTC_CSR_KERNEL_NAME
HIP_RTC_CSR_KERNEL_BLOCK_SIZE = 256

_SOURCE_RESOURCE = "kernels/engine_v2_csr_residual_jvp_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_ARCHITECTURE_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17")
_INT32_MAX = (1 << 31) - 1
_MAX_COMPILE_LOG_BYTES = 16_384


class HipRtcError(RuntimeError):
    """Stable fail-closed error for the fixed HIPRTC pipeline."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.compile_log = _bounded_text(compile_log, _MAX_COMPILE_LOG_BYTES)
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class HipRtcLibraryIdentity:
    discovery_source: str
    requested_name: str
    loaded_name: str
    resolved_path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "discovery_source": self.discovery_source,
            "requested_name": self.requested_name,
            "loaded_name": self.loaded_name,
            "resolved_path": self.resolved_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class HipRtcCsrKernelIdentity:
    schema_version: str
    abi_version: int
    kernel_name: str
    kernel_symbol: str
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

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class _BoundHipRtc:
    __slots__ = (
        "identity",
        "_create_program",
        "_compile_program",
        "_get_log_size",
        "_get_log",
        "_get_code_size",
        "_get_code",
        "_destroy_program",
        "_version",
        "_error_string",
    )

    def __init__(
        self,
        cdll: ctypes.CDLL,
        identity: HipRtcLibraryIdentity,
    ) -> None:
        self.identity = identity
        self._create_program = _bind_cdll(
            cdll,
            "hiprtcCreateProgram",
            [
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_char_p),
                ctypes.POINTER(ctypes.c_char_p),
            ],
            ctypes.c_int,
        )
        self._compile_program = _bind_cdll(
            cdll,
            "hiprtcCompileProgram",
            [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)],
            ctypes.c_int,
        )
        self._get_log_size = _bind_cdll(
            cdll,
            "hiprtcGetProgramLogSize",
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)],
            ctypes.c_int,
        )
        self._get_log = _bind_cdll(
            cdll,
            "hiprtcGetProgramLog",
            [ctypes.c_void_p, ctypes.c_char_p],
            ctypes.c_int,
        )
        self._get_code_size = _bind_cdll(
            cdll,
            "hiprtcGetCodeSize",
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)],
            ctypes.c_int,
        )
        self._get_code = _bind_cdll(
            cdll,
            "hiprtcGetCode",
            [ctypes.c_void_p, ctypes.c_char_p],
            ctypes.c_int,
        )
        self._destroy_program = _bind_cdll(
            cdll,
            "hiprtcDestroyProgram",
            [ctypes.POINTER(ctypes.c_void_p)],
            ctypes.c_int,
        )
        self._version = _bind_cdll(
            cdll,
            "hiprtcVersion",
            [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
            ctypes.c_int,
        )
        self._error_string = _bind_cdll(
            cdll,
            "hiprtcGetErrorString",
            [ctypes.c_int],
            ctypes.c_char_p,
        )

    def error_string(self, status: int) -> str:
        raw = self._error_string(int(status))
        if raw is None:
            return "HIPRTC error string unavailable"
        return raw.decode("utf-8", errors="replace")

    def version(self) -> tuple[int, int, int]:
        major = ctypes.c_int()
        minor = ctypes.c_int()
        status = int(self._version(ctypes.byref(major), ctypes.byref(minor)))
        return status, int(major.value), int(minor.value)

    def create_program(
        self,
        source: bytes,
        program_name: str | None = None,
    ) -> tuple[int, ctypes.c_void_p]:
        program = ctypes.c_void_p()
        status = self.create_program_into(source, program, program_name)
        return status, program

    def create_program_into(
        self,
        source: bytes,
        program: ctypes.c_void_p,
        program_name: str | None = None,
    ) -> int:
        """Create into a caller-owned box so interruption cannot lose the handle."""

        if type(program) is not ctypes.c_void_p or program.value:
            raise HipRtcError(
                "hip_rtc_program_handoff_invalid",
                "Program creation requires an exact empty caller-owned handle box.",
            )
        encoded_name = (
            HIP_RTC_CSR_KERNEL_NAME.encode("ascii") + b".hip.cpp"
            if program_name is None
            else program_name.encode("ascii")
        )
        return int(
            self._create_program(
                ctypes.byref(program),
                source,
                encoded_name,
                0,
                None,
                None,
            )
        )

    def compile_program(self, program: Any, options: Sequence[str]) -> int:
        encoded = tuple(option.encode("ascii") for option in options)
        option_array = (ctypes.c_char_p * len(encoded))(*encoded)
        return int(self._compile_program(program, len(encoded), option_array))

    def program_log(self, program: Any) -> str:
        size = ctypes.c_size_t()
        status = int(self._get_log_size(program, ctypes.byref(size)))
        if status != 0:
            raise HipRtcError(
                "hip_rtc_program_log_failed",
                f"hiprtcGetProgramLogSize failed: {self.error_string(status)}.",
            )
        if size.value == 0:
            return ""
        buffer = ctypes.create_string_buffer(int(size.value))
        status = int(self._get_log(program, buffer))
        if status != 0:
            raise HipRtcError(
                "hip_rtc_program_log_failed",
                f"hiprtcGetProgramLog failed: {self.error_string(status)}.",
            )
        return buffer.value.decode("utf-8", errors="replace")

    def code_object(self, program: Any) -> bytes:
        size = ctypes.c_size_t()
        status = int(self._get_code_size(program, ctypes.byref(size)))
        if status != 0:
            raise HipRtcError(
                "hip_rtc_code_size_failed",
                f"hiprtcGetCodeSize failed: {self.error_string(status)}.",
            )
        if size.value <= 0:
            raise HipRtcError(
                "hip_rtc_code_object_invalid",
                "HIPRTC returned an empty code object.",
            )
        buffer = ctypes.create_string_buffer(int(size.value))
        status = int(self._get_code(program, buffer))
        if status != 0:
            raise HipRtcError(
                "hip_rtc_code_get_failed",
                f"hiprtcGetCode failed: {self.error_string(status)}.",
            )
        return bytes(buffer.raw[: int(size.value)])

    def destroy_program(self, program: Any) -> int:
        if isinstance(program, ctypes.c_void_p):
            return int(self._destroy_program(ctypes.byref(program)))
        boxed = ctypes.c_void_p(_pointer_integer(program, "program"))
        return int(self._destroy_program(ctypes.byref(boxed)))


class _RuntimeModuleApi:
    __slots__ = (
        "_runtime",
        "_load_data",
        "_get_function",
        "_launch_kernel",
        "_unload",
    )

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        try:
            self._load_data = runtime.bind(
                "hipModuleLoadData",
                [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p],
                ctypes.c_int,
            )
            self._get_function = runtime.bind(
                "hipModuleGetFunction",
                [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_char_p],
                ctypes.c_int,
            )
            self._launch_kernel = runtime.bind(
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
            )
            self._unload = runtime.bind(
                "hipModuleUnload", [ctypes.c_void_p], ctypes.c_int
            )
        except Exception as exc:
            raise HipRtcError(
                "hip_rtc_runtime_symbol_missing",
                f"Required HIP module ABI could not be bound: {type(exc).__name__}.",
            ) from exc

    def error_string(self, status: int) -> str:
        try:
            return str(self._runtime.hip_error_string(int(status)))
        except Exception:
            return "HIP error string unavailable"

    def load_module(self, code_object: bytes) -> tuple[int, ctypes.c_void_p]:
        module = ctypes.c_void_p()
        status = self.load_module_into(code_object, module)
        return status, module

    def load_module_into(
        self,
        code_object: bytes,
        module: ctypes.c_void_p,
    ) -> int:
        """Load into a caller-owned box so interruption cannot lose the handle."""

        if type(module) is not ctypes.c_void_p or module.value:
            raise HipRtcError(
                "hip_rtc_module_handoff_invalid",
                "Module load requires an exact empty caller-owned handle box.",
            )
        image = ctypes.create_string_buffer(code_object, len(code_object))
        return int(
            self._load_data(ctypes.byref(module), ctypes.cast(image, ctypes.c_void_p))
        )

    def get_function(
        self, module: ctypes.c_void_p, symbol: str
    ) -> tuple[int, ctypes.c_void_p]:
        function = ctypes.c_void_p()
        status = int(
            self._get_function(ctypes.byref(function), module, symbol.encode("ascii"))
        )
        return status, function

    def launch(
        self,
        function: ctypes.c_void_p,
        *,
        grid_x: int,
        block_x: int,
        stream: ctypes.c_void_p,
        parameters: Any,
    ) -> int:
        return int(
            self._launch_kernel(
                function,
                grid_x,
                1,
                1,
                block_x,
                1,
                1,
                0,
                stream,
                parameters,
                None,
            )
        )

    def unload(self, module: ctypes.c_void_p) -> int:
        return int(self._unload(module))


class HipRtcCsrKernel:
    """Loaded fixed kernel with explicit lifetime and one launch operation."""

    __slots__ = ("_runtime", "_module", "_function", "_identity", "_closed")

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        function: ctypes.c_void_p,
        identity: HipRtcCsrKernelIdentity,
    ) -> None:
        self._runtime = runtime
        self._module = module
        self._function = function
        self._identity = identity
        self._closed = False

    @property
    def identity(self) -> HipRtcCsrKernelIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> HipRtcCsrKernel:
        if self._closed:
            raise HipRtcError("hip_rtc_kernel_closed", "HIPRTC kernel is closed.")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_residual_jvp(
        self,
        stream: Any,
        row_count: int,
        row_ptr: Any,
        column_indices: Any,
        values: Any,
        state: Any,
        load: Any,
        direction: Any,
        residual_out: Any,
        jvp_out: Any,
    ) -> None:
        """Launch one fused ``R=K*u-F`` and ``Jv=K*v`` CSR traversal."""

        if self._closed:
            raise HipRtcError("hip_rtc_kernel_closed", "HIPRTC kernel is closed.")
        if (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or not 0 < row_count <= _INT32_MAX
        ):
            raise HipRtcError(
                "hip_rtc_launch_contract_invalid",
                "row_count must be a positive signed int32 value.",
            )
        stream_storage = ctypes.c_void_p(_pointer_integer(stream, "stream"))
        pointer_inputs = (
            ("row_ptr", row_ptr),
            ("column_indices", column_indices),
            ("values", values),
            ("state", state),
            ("load", load),
            ("direction", direction),
            ("residual_out", residual_out),
            ("jvp_out", jvp_out),
        )
        pointer_storage = [
            ctypes.c_void_p(_pointer_integer(value, label))
            for label, value in pointer_inputs
        ]
        row_count_storage = ctypes.c_int(row_count)
        argument_storage = [row_count_storage, *pointer_storage]
        parameters = (ctypes.c_void_p * len(argument_storage))(
            *[
                ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                for argument in argument_storage
            ]
        )
        grid_x = (
            row_count + HIP_RTC_CSR_KERNEL_BLOCK_SIZE - 1
        ) // HIP_RTC_CSR_KERNEL_BLOCK_SIZE
        try:
            status = self._runtime.launch(
                self._function,
                grid_x=grid_x,
                block_x=HIP_RTC_CSR_KERNEL_BLOCK_SIZE,
                stream=stream_storage,
                parameters=parameters,
            )
        except HipRtcError:
            raise
        except Exception as exc:
            raise HipRtcError(
                "hip_rtc_kernel_launch_failed",
                f"hipModuleLaunchKernel raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcError(
                "hip_rtc_kernel_launch_failed",
                f"hipModuleLaunchKernel failed: {self._runtime.error_string(status)}.",
            )

    def close(self) -> None:
        """Unload the module once; successful repeated closes are no-ops."""

        if self._closed:
            return
        try:
            status = self._runtime.unload(self._module)
        except Exception as exc:
            raise HipRtcError(
                "hip_rtc_module_unload_failed",
                f"hipModuleUnload raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcError(
                "hip_rtc_module_unload_failed",
                f"hipModuleUnload failed: {self._runtime.error_string(status)}.",
            )
        self._module = ctypes.c_void_p()
        self._function = ctypes.c_void_p()
        self._closed = True


def compile_hip_rtc_csr_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcCsrKernel:
    """Compile and load the one package-owned canonical-CSR HIPRTC kernel."""

    try:
        return _compile_hip_rtc_csr_kernel_impl(
            loaded_runtime, architecture, hiprtc_library
        )
    except HipRtcError:
        raise
    except Exception as exc:
        raise HipRtcError(
            "hip_rtc_unexpected_failure",
            f"Unexpected HIPRTC pipeline failure: {type(exc).__name__}.",
        ) from exc


def _compile_hip_rtc_csr_kernel_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcCsrKernel:
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = _fixed_source()
    source_hash = _sha256_bytes(source)
    options = (
        f"--offload-arch={checked_architecture}",
        *_FIXED_OPTION_SUFFIX,
    )

    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcError(
            "hip_rtc_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcError(
            "hip_rtc_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcError(
            "hip_rtc_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcError(
            "hip_rtc_runtime_init_failed",
            f"hipInit failed: {_runtime_error_string(loaded_runtime, init_status)}.",
        )

    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(rtc, source, options)
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        raise HipRtcError(
            "hip_rtc_module_load_failed",
            f"hipModuleLoadData failed: {runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    try:
        status, function = runtime.get_function(module, HIP_RTC_CSR_KERNEL_SYMBOL)
        if status != 0 or not function.value:
            raise HipRtcError(
                "hip_rtc_kernel_symbol_missing",
                "hipModuleGetFunction failed for the fixed kernel symbol: "
                f"{runtime.error_string(status)}.",
                compile_log=compile_log,
            )
        identity = _build_identity(
            architecture=checked_architecture,
            source_hash=source_hash,
            options=options,
            rtc_version=(rtc_major, rtc_minor),
            rtc_library=rtc.identity,
            runtime_library=runtime_identity,
            code_object=code_object,
        )
        return HipRtcCsrKernel(
            runtime=runtime,
            module=module,
            function=function,
            identity=identity,
        )
    except Exception as primary:
        try:
            cleanup_status = runtime.unload(module)
        except Exception as cleanup_exc:
            raise HipRtcError(
                "hip_rtc_module_cleanup_failed",
                f"{primary}; hipModuleUnload cleanup raised "
                f"{type(cleanup_exc).__name__}.",
                compile_log=(
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
            ) from primary
        if cleanup_status != 0:
            raise HipRtcError(
                "hip_rtc_module_cleanup_failed",
                f"{primary}; hipModuleUnload cleanup failed: "
                f"{runtime.error_string(cleanup_status)}.",
                compile_log=(
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
            ) from primary
        raise


class _HipRtcProgramCleanupOwner:
    """Local persistent owner for one HIPRTC program handle."""

    __slots__ = ("rtc", "program", "disposition")

    def __init__(self, rtc: Any, program: ctypes.c_void_p) -> None:
        if type(program) is not ctypes.c_void_p or program.value:
            raise ValueError("program cleanup owner requires an empty handle box")
        self.rtc = rtc
        self.program = program
        self.disposition = "live"

    def close(self) -> None:
        if self.disposition == "terminal":
            return
        if not self.program.value:
            self._finish()
            return
        if self.disposition == "external_destroy_succeeded":
            self._finish()
            return
        if self.disposition in {"destroy_call_inflight", "destroy_outcome_uncertain"}:
            self.disposition = "destroy_outcome_uncertain"
            error = HipRtcError(
                "hip_rtc_program_destroy_outcome_uncertain",
                "A prior hiprtcDestroyProgram outcome is uncertain; the program handle will not be retried.",
            )
            error.cleanup_owner = self
            raise error
        status: int | None = None
        self.disposition = "destroy_call_inflight"
        try:
            status = int(self.rtc.destroy_program(self.program))
            if status != 0:
                self.disposition = "live"
                error = HipRtcError(
                    "hip_rtc_program_destroy_failed",
                    f"hiprtcDestroyProgram failed: {self.rtc.error_string(status)}.",
                )
                error.cleanup_owner = self
                raise error
            self.disposition = "external_destroy_succeeded"
        except HipRtcError:
            raise
        except BaseException:
            self.disposition = (
                "external_destroy_succeeded"
                if status == 0
                else ("live" if status is not None else "destroy_outcome_uncertain")
            )
            raise
        self._finish()

    def _finish(self) -> None:
        self.program.value = None
        self.disposition = "terminal"


def _destroy_rtc_program(
    owner: _HipRtcProgramCleanupOwner,
    *,
    primary: BaseException | None,
    compile_log: str,
) -> None:
    try:
        owner.close()
    except BaseException as cleanup_exc:
        if isinstance(cleanup_exc, HipRtcError):
            cleanup_error = cleanup_exc
            cleanup_error.compile_log = _bounded_text(
                (
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
                _MAX_COMPILE_LOG_BYTES,
            )
        else:
            cleanup_error = HipRtcError(
                "hip_rtc_program_destroy_failed",
                f"hiprtcDestroyProgram raised {type(cleanup_exc).__name__}.",
                compile_log=(
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
            )
            cleanup_error.cleanup_owner = owner
            cleanup_error.cleanup_recovery_required = owner.disposition == "live"
        if primary is not None:
            raise cleanup_error from primary
        raise cleanup_error from cleanup_exc


def _compile_fixed_source(
    rtc: Any,
    source: bytes,
    options: tuple[str, ...],
    *,
    program_name: str | None = None,
) -> tuple[bytes, str]:
    program = ctypes.c_void_p()
    program_owner = _HipRtcProgramCleanupOwner(rtc, program)
    try:
        return _compile_fixed_source_impl(
            rtc,
            source,
            options,
            program_owner=program_owner,
            program_name=program_name,
        )
    except BaseException as primary:
        same_cleanup_owner = (
            isinstance(primary, HipRtcError)
            and getattr(primary, "cleanup_owner", None) is program_owner
        )
        recovery_required = (
            bool(getattr(primary, "cleanup_recovery_required", False))
            or program_owner.disposition == "external_destroy_succeeded"
        )
        if same_cleanup_owner and not recovery_required:
            raise
        if program_owner.disposition != "terminal":
            _destroy_rtc_program(
                program_owner,
                primary=primary,
                compile_log=(
                    primary.compile_log if isinstance(primary, HipRtcError) else ""
                ),
            )
        raise


def _compile_fixed_source_impl(
    rtc: Any,
    source: bytes,
    options: tuple[str, ...],
    *,
    program_owner: _HipRtcProgramCleanupOwner,
    program_name: str | None,
) -> tuple[bytes, str]:
    program = program_owner.program
    create_into = getattr(rtc, "create_program_into", None)
    try:
        if callable(create_into):
            status = int(create_into(source, program, program_name))
        elif program_name is None:
            status, returned_program = rtc.create_program(source)
            program.value = _pointer_value(returned_program)
        else:
            status, returned_program = rtc.create_program(source, program_name)
            program.value = _pointer_value(returned_program)
    except BaseException as primary:
        if program.value:
            _destroy_rtc_program(program_owner, primary=primary, compile_log="")
        raise
    if status != 0 or not _pointer_value(program):
        primary = HipRtcError(
            "hip_rtc_program_create_failed",
            f"hiprtcCreateProgram failed: {rtc.error_string(status)}.",
        )
        if program.value:
            _destroy_rtc_program(program_owner, primary=primary, compile_log="")
        raise primary
    primary: BaseException | None = None
    code_object: bytes | None = None
    compile_log = ""
    try:
        compile_status = int(rtc.compile_program(program, options))
        try:
            compile_log = rtc.program_log(program)
        except Exception as log_error:
            if compile_status != 0:
                raise HipRtcError(
                    "hip_rtc_compile_failed",
                    "hiprtcCompileProgram failed and its log could not be "
                    f"read: {rtc.error_string(compile_status)}.",
                ) from log_error
            raise
        if compile_status != 0:
            raise HipRtcError(
                "hip_rtc_compile_failed",
                f"hiprtcCompileProgram failed: {rtc.error_string(compile_status)}.",
                compile_log=compile_log,
            )
        code_object = rtc.code_object(program)
    except BaseException as exc:
        primary = exc

    _destroy_rtc_program(
        program_owner,
        primary=primary,
        compile_log=compile_log,
    )
    if primary is not None:
        raise primary
    if code_object is None:
        raise HipRtcError(
            "hip_rtc_code_object_invalid",
            "No HIPRTC code object was produced.",
        )
    return code_object, _bounded_text(compile_log, _MAX_COMPILE_LOG_BYTES)


def _load_hiprtc_api(
    hiprtc_library: str | Path | None,
) -> _BoundHipRtc:
    identity, load_name = _discover_hiprtc_library(hiprtc_library)
    try:
        cdll = ctypes.CDLL(load_name, mode=getattr(ctypes, "RTLD_LOCAL", 0))
    except OSError as exc:
        raise HipRtcError(
            "hip_rtc_library_load_failed",
            f"libhiprtc could not be loaded: {type(exc).__name__}.",
        ) from exc
    return _BoundHipRtc(cdll, identity)


def _discover_hiprtc_library(
    hiprtc_library: str | Path | None,
) -> tuple[HipRtcLibraryIdentity, str]:
    if hiprtc_library is not None:
        requested = str(hiprtc_library)
        if not requested:
            raise HipRtcError(
                "hip_rtc_library_invalid", "hiprtc_library must not be empty."
            )
        resolved = _resolve_library_path(requested)
        if resolved is None:
            raise HipRtcError(
                "hip_rtc_library_not_found",
                f"Explicit HIPRTC library was not found: {requested}.",
            )
        source = "explicit"
    else:
        requested = ""
        resolved = None
        for candidate in (
            "/opt/rocm/lib/libhiprtc.so",
            "/opt/rocm/lib/libhiprtc.so.6",
            "/opt/rocm/lib64/libhiprtc.so",
            "/opt/rocm/lib64/libhiprtc.so.6",
        ):
            resolved = _resolve_library_path(candidate)
            if resolved is not None:
                requested = candidate
                break
        source = "opt_rocm"
        if resolved is None:
            loader_name = ctypes.util.find_library("hiprtc")
            if loader_name:
                requested = loader_name
                resolved = _resolve_library_path(loader_name)
                source = "system_loader"
        if resolved is None:
            raise HipRtcError(
                "hip_rtc_library_not_found",
                "No /opt/rocm or system-loader libhiprtc was found.",
            )
    digest = _sha256_path(Path(resolved))
    identity = HipRtcLibraryIdentity(
        discovery_source=source,
        requested_name=requested,
        loaded_name=resolved,
        resolved_path=resolved,
        sha256=digest,
    )
    return identity, resolved


def _resolve_library_path(raw_name: str) -> str | None:
    path = Path(raw_name)
    try:
        if path.is_file():
            return str(path.resolve(strict=True))
    except OSError:
        return None
    if "/" in raw_name:
        return None
    for directory in (
        Path("/opt/rocm/lib"),
        Path("/opt/rocm/lib64"),
        Path("/lib/x86_64-linux-gnu"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/usr/local/lib"),
    ):
        candidate = directory / raw_name
        try:
            if candidate.is_file():
                return str(candidate.resolve(strict=True))
        except OSError:
            continue
    return None


def _runtime_library_identity(runtime: Any) -> HipRuntimeLibraryIdentity:
    if not callable(getattr(runtime, "bind", None)):
        raise HipRtcError(
            "hip_rtc_runtime_invalid",
            "loaded_runtime does not expose the native bind() API.",
        )
    raw = getattr(runtime, "library_identity", None)
    if raw is None:
        raise HipRtcError(
            "hip_rtc_runtime_identity_invalid",
            "loaded_runtime has no library_identity.",
        )
    try:
        discovery_source = str(raw.discovery_source)
        requested_name = raw.requested_name
        loaded_name = raw.loaded_name
        resolved_path = raw.resolved_path
        digest = raw.sha256
    except AttributeError as exc:
        raise HipRtcError(
            "hip_rtc_runtime_identity_invalid",
            "loaded_runtime library_identity is incomplete.",
        ) from exc
    if not _valid_sha256(digest) and resolved_path:
        try:
            digest = _sha256_path(Path(resolved_path))
        except HipRtcError:
            digest = None
    if not _valid_sha256(digest):
        raise HipRtcError(
            "hip_rtc_runtime_identity_invalid",
            "The HIP runtime library requires an exact SHA-256 identity.",
        )
    if resolved_path:
        path = Path(str(resolved_path))
        if path.is_file() and _sha256_path(path) != digest:
            raise HipRtcError(
                "hip_rtc_runtime_identity_invalid",
                "The HIP runtime library SHA-256 does not match its file.",
            )
    return HipRuntimeLibraryIdentity(
        discovery_source=discovery_source,
        requested_name=None if requested_name is None else str(requested_name),
        loaded_name=None if loaded_name is None else str(loaded_name),
        resolved_path=None if resolved_path is None else str(resolved_path),
        sha256=str(digest),
    )


def _build_identity(
    *,
    architecture: str,
    source_hash: str,
    options: tuple[str, ...],
    rtc_version: tuple[int, int],
    rtc_library: HipRtcLibraryIdentity,
    runtime_library: HipRuntimeLibraryIdentity,
    code_object: bytes,
) -> HipRtcCsrKernelIdentity:
    initial = HipRtcCsrKernelIdentity(
        schema_version=HIP_RTC_CSR_KERNEL_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_CSR_KERNEL_ABI_VERSION,
        kernel_name=HIP_RTC_CSR_KERNEL_NAME,
        kernel_symbol=HIP_RTC_CSR_KERNEL_SYMBOL,
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
    _validate_identity(identity)
    return identity


def _identity_payload(
    identity: HipRtcCsrKernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbol": identity.kernel_symbol,
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


def _validate_identity(identity: HipRtcCsrKernelIdentity) -> None:
    if not isinstance(identity, HipRtcCsrKernelIdentity):
        raise HipRtcError(
            "hip_rtc_identity_invalid", "Kernel identity type is invalid."
        )
    if identity.schema_version != HIP_RTC_CSR_KERNEL_IDENTITY_SCHEMA_VERSION:
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "Kernel identity schema version is invalid.",
        )
    if (
        identity.abi_version != HIP_RTC_CSR_KERNEL_ABI_VERSION
        or identity.kernel_name != HIP_RTC_CSR_KERNEL_NAME
        or identity.kernel_symbol != HIP_RTC_CSR_KERNEL_SYMBOL
        or identity.source_resource != _SOURCE_RESOURCE
    ):
        raise HipRtcError(
            "hip_rtc_identity_invalid", "Fixed kernel ABI identity is invalid."
        )
    if identity.source_sha256 != _sha256_bytes(_fixed_source()):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "Kernel source hash does not match the package-owned source.",
        )
    _validate_architecture(identity.architecture)
    expected_options = (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    )
    if identity.compile_options != expected_options:
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "Kernel compile options are not fixed.",
        )
    _validate_rtc_library_identity(identity.hiprtc_library)
    _validate_runtime_identity(identity.runtime_library)
    hashes = (
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "Kernel identity has an invalid SHA-256.",
        )
    if (
        identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
        or identity.code_object_byte_length <= 0
    ):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "Kernel version or byte length is invalid.",
        )
    expected_hash = canonical_hash(_identity_payload(identity, include_hash=False))
    if identity.identity_hash != expected_hash:
        raise HipRtcError(
            "hip_rtc_identity_hash_mismatch",
            "Kernel identity hash is invalid.",
        )


def _validate_rtc_library_identity(identity: Any) -> None:
    if not isinstance(identity, HipRtcLibraryIdentity):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIPRTC library identity type is invalid.",
        )
    if identity.discovery_source not in {
        "explicit",
        "opt_rocm",
        "system_loader",
        "injected",
    }:
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIPRTC library discovery source is invalid.",
        )
    if any(
        not isinstance(value, str) or not value
        for value in (
            identity.requested_name,
            identity.loaded_name,
            identity.resolved_path,
        )
    ):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIPRTC library names and path must be non-empty.",
        )
    if not _valid_sha256(identity.sha256):
        raise HipRtcError(
            "hip_rtc_identity_invalid", "HIPRTC library SHA-256 is invalid."
        )
    _validate_identity_path_hash(
        discovery_source=identity.discovery_source,
        resolved_path=identity.resolved_path,
        digest=identity.sha256,
        label="HIPRTC",
    )


def _validate_runtime_identity(identity: Any) -> None:
    if not isinstance(identity, HipRuntimeLibraryIdentity):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIP runtime library identity type is invalid.",
        )
    if identity.discovery_source not in {
        "explicit",
        "opt_rocm",
        "system_loader",
        "injected",
    }:
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIP runtime library discovery source is invalid.",
        )
    if any(
        not isinstance(value, str) or not value
        for value in (identity.requested_name, identity.loaded_name)
    ):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIP runtime library names must be non-empty.",
        )
    if identity.resolved_path is not None and (
        not isinstance(identity.resolved_path, str) or not identity.resolved_path
    ):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIP runtime library path is invalid.",
        )
    if not _valid_sha256(identity.sha256):
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            "HIP runtime library SHA-256 is invalid.",
        )
    _validate_identity_path_hash(
        discovery_source=identity.discovery_source,
        resolved_path=identity.resolved_path,
        digest=identity.sha256,
        label="HIP runtime",
    )


def _validate_identity_path_hash(
    *,
    discovery_source: str,
    resolved_path: str | None,
    digest: str,
    label: str,
) -> None:
    if resolved_path is None:
        if discovery_source != "injected":
            raise HipRtcError(
                "hip_rtc_identity_invalid",
                f"{label} library requires a resolved path.",
            )
        return
    path = Path(resolved_path)
    if not path.is_file():
        if discovery_source != "injected":
            raise HipRtcError(
                "hip_rtc_identity_invalid",
                f"{label} library path is unavailable.",
            )
        return
    if _sha256_path(path) != digest:
        raise HipRtcError(
            "hip_rtc_identity_invalid",
            f"{label} library SHA-256 does not match its file.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcError(
            "hip_rtc_source_missing",
            f"The package-owned HIPRTC source is unavailable: {type(exc).__name__}.",
        ) from exc
    if not source or HIP_RTC_CSR_KERNEL_SYMBOL.encode("ascii") not in source:
        raise HipRtcError(
            "hip_rtc_source_invalid",
            "The package-owned HIPRTC source does not contain the fixed symbol.",
        )
    return source


def _validate_architecture(architecture: Any) -> str:
    if not isinstance(architecture, str) or not _ARCHITECTURE_PATTERN.fullmatch(
        architecture
    ):
        raise HipRtcError(
            "hip_rtc_architecture_invalid",
            "architecture must be one plain AMD gfx target such as gfx1030.",
        )
    return architecture


def _pointer_value(value: Any) -> int | None:
    if isinstance(value, ctypes.c_void_p):
        return None if value.value is None else int(value.value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    raw = getattr(value, "value", None)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return int(raw)
    return None


def _pointer_integer(value: Any, label: str) -> int:
    pointer = _pointer_value(value)
    if pointer is None or pointer <= 0:
        raise HipRtcError(
            "hip_rtc_launch_contract_invalid",
            f"{label} must be a non-null runtime pointer.",
        )
    return pointer


def _runtime_error_string(runtime: Any, status: int) -> str:
    try:
        return str(runtime.hip_error_string(int(status)))
    except Exception:
        return "HIP error string unavailable"


def _bind_cdll(
    cdll: ctypes.CDLL,
    symbol: str,
    argtypes: Sequence[Any],
    restype: Any,
) -> Any:
    try:
        function = getattr(cdll, symbol)
    except AttributeError as exc:
        raise HipRtcError(
            "hip_rtc_symbol_missing",
            f"Required HIPRTC symbol is missing: {symbol}.",
        ) from exc
    function.argtypes = list(argtypes)
    function.restype = restype
    return function


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1_048_576), b""):
                digest.update(block)
    except OSError as exc:
        raise HipRtcError(
            "hip_rtc_library_hash_failed",
            f"Native library could not be hashed: {type(exc).__name__}.",
        ) from exc
    return f"sha256:{digest.hexdigest()}"


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _bounded_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]
